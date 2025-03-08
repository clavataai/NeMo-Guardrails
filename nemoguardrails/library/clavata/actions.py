# SPDX-FileCopyrightText: Copyright (c) 2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Check for matches against a Clavata policy."""

import logging
import textwrap
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, cast

from pydantic import BaseModel, Field

from nemoguardrails import RailsConfig
from nemoguardrails.actions import action
from nemoguardrails.library.clavata.errs import (
    ClavataPluginAPIError,
    ClavataPluginConfigurationError,
    ClavataPluginValueError,
)
from nemoguardrails.library.clavata.request import ClavataClient, Job
from nemoguardrails.rails.llm.config import ClavataRailConfig, ClavataRailOptions

if TYPE_CHECKING:
    from .request import Report, SectionReport

log = logging.getLogger(__name__)

VALID_RAILS = ["input", "output"]
ValidRailsType = Literal["input", "output"]


class LabelResult(BaseModel):
    """Result of a label evaluation"""

    label: str = Field(description="The label that was evaluated")
    message: str = Field(
        description="An arbitrary message attached to the label in the policy."
    )
    matched: bool = Field(description="Whether the label matched the policy")

    @classmethod
    def from_section_report(cls, report: "SectionReport") -> "LabelResult":
        """Convert a Clavata section report to a LabelResult"""
        return cls(
            label=report.name,
            message=report.message,
            matched=report.result == "OUTCOME_TRUE",
        )


class PolicyResult(BaseModel):
    """Result of Clavata Policy Evaluation"""

    failed: bool = Field(
        default=False, description="Whether the policy evaluation failed"
    )
    policy_matched: bool = Field(
        default=False, description="Whether any part of the policy matched the input"
    )
    label_matches: List[LabelResult] = Field(
        default=[],
        description="List of section results from the policy evaluation",
    )

    @classmethod
    def from_report(cls, report: "Report") -> "PolicyResult":
        """Convert a Clavata report to a PolicyResult"""
        return cls(
            failed=report.result == "OUTCOME_FAILED",
            policy_matched=report.result == "OUTCOME_TRUE",
            label_matches=[
                LabelResult.from_section_report(report)
                for report in report.sectionEvaluationReports
            ],
        )

    @classmethod
    def from_job(cls, job: "Job") -> "PolicyResult":
        """Convert a Clavata job to a PolicyResult"""
        failed = job.status in ["JOB_STATUS_FAILED", "JOB_STATUS_CANCELED"]
        if failed:
            return cls(failed=True)

        if job.status != "JOB_STATUS_COMPLETED":
            raise ClavataPluginAPIError(
                f"Policy evaluation is not complete. Status: {job.status}"
            )

        reports = [res.report for res in job.results]
        # We should only ever have one report per job as we're only sending one content item
        if len(reports) != 1:
            raise ClavataPluginAPIError(
                f"Expected 1 report per job, got {len(reports)}"
            )

        report = reports[0]
        return cls.from_report(report)


def get_clavata_config(config: Any) -> ClavataRailConfig:
    """Get the Clavata config and flow config for the given source."""
    if not isinstance(config, RailsConfig):
        raise ClavataPluginValueError(
            "Passed configuration object is not a RailsConfig"
        )

    if (
        not hasattr(config.rails.config, "clavata")
        or config.rails.config.clavata is None
    ):
        raise ClavataPluginConfigurationError(
            "Clavata config is not defined in the Rails config."
        )

    return cast(ClavataRailConfig, config.rails.config.clavata)


def get_policy_id(policy: str, config: ClavataRailConfig) -> uuid.UUID:
    """
    Get Policy ID will check the input policy. If the input is already a UUID, that UUID will be used. Otherwise,
    the config will be checked to try to match the input policy alias to a policy ID. If no match is found, an error
    will be raised.
    """
    try:
        return uuid.UUID(policy)
    except ValueError:
        pass

    # Not a valid UUID, try to match the provided alias to a policy ID and return that
    try:
        for p in config.policies:
            if p.alias == policy:
                return uuid.UUID(p.id)
    except ValueError as e:
        # Specifically catch the ValueError for badly formed UUIDs so we can provide a more helpful error message
        if "badly formed" in str(e):
            raise ClavataPluginConfigurationError(
                f"Policy ID '{p.id}' for alias '{policy}' is not a valid UUID. Please check the Clavata configuration."
            ) from e
        raise

    # No match found
    raise ClavataPluginValueError(f"Policy with alias '{policy}' not found.")


def get_server_endpoint(config: ClavataRailConfig) -> str:
    """Get the server endpoint from the Clavata config."""
    return str(config.server_endpoint).rstrip("/")


async def evaluate_with_policy(
    text: str,
    policy_id: str,
    clavata_config: ClavataRailConfig,
) -> PolicyResult:
    """Get the policy result for the given source."""
    client = ClavataClient(
        base_endpoint=get_server_endpoint(clavata_config),
    )

    job = await client.create_job(text, policy_id)
    rv = PolicyResult.from_job(job)

    if rv.failed:
        raise ClavataPluginAPIError("Policy evaluation failed.")

    return rv


@action()
async def clavata_check_v1(
    rail: ValidRailsType,
    text: str,
    context: Optional[dict] = None,
    config: Optional[RailsConfig] = None,
    **kwargs: Any,
) -> bool:
    """
    Works with both v1 and v2 flows
    """
    if context is None:
        raise ClavataPluginValueError("Context is required.")

    if config is None:
        raise ClavataPluginValueError("Rails config is required.")

    if rail not in VALID_RAILS:
        raise ClavataPluginValueError(f"Invalid rail: {rail}")

    clavata_config = get_clavata_config(config)

    # Grab the correct rail config based on the rail and get the policy name
    try:
        policy_name = getattr(clavata_config, rail).policy
        policy_id = get_policy_id(policy_name, clavata_config)
    except AttributeError as e:
        raise ClavataPluginConfigurationError(
            f"Policy is not defined for rail: {rail}"
        ) from e

    result = await detect_policy_match(policy_id.hex, text, config)
    labels = get_labels(clavata_config, rail=rail)
    if labels:
        # If labels are provided, we need to check whether the labels themselves matched
        return is_label_match(result, labels, clavata_config)

    return result.policy_matched


@action(name="ClavataCheckV2Action", execute_async=True)
async def clavata_check_v2(
    text: str,
    policy: str,
    labels: Optional[List[str]] = None,
    config: Optional[RailsConfig] = None,
    **kwargs: Any,
) -> bool:
    """Check for matches against a Clavata policy."""
    if not config:
        raise ClavataPluginValueError("Rails config is required.")

    clavata_config = get_clavata_config(config)
    policy_id = get_policy_id(policy, clavata_config)
    policy_result = await evaluate_with_policy(text, policy_id.hex, clavata_config)

    if labels and labels != "":
        return is_label_match(policy_result, labels, clavata_config)

    return policy_result.policy_matched


def get_labels(
    config: ClavataRailConfig,
    labels: Optional[List[str]] = None,
    rail: Optional[ValidRailsType] = None,
) -> List[str]:
    """
    Checks whether the provided text matches the specified Clavata policy ID.
    Note that this action will return True if any label in the policy matches the text.
    """
    # If labels is provided, just return them
    if labels is not None:
        return labels

    # If labels are not provided, we need to get them from the config
    if rail is None:
        raise ClavataPluginValueError("Rail is required when labels are not provided.")

    rail_config: ClavataRailOptions = getattr(config, rail)
    labels = rail_config.labels
    if labels is None:
        raise ClavataPluginValueError(f"Labels are not defined for rail: {rail}")

    return labels


def is_label_match(
    result: PolicyResult,
    labels: List[str] | str,
    clavata_config: ClavataRailConfig,
) -> bool:
    """Check whether the labels matched the policy"""
    labels_to_match = set(labels.split(",")) if isinstance(labels, str) else set(labels)
    labels_matched = set(lbl.label for lbl in result.label_matches if lbl.matched)

    match_all = clavata_config.label_match_logic == "ALL"
    if match_all:
        return labels_to_match.issubset(labels_matched)

    # If matching any of the labels is fine, then we can just check whether
    # there is any intersection between the labels to match and the labels that matched
    return bool(labels_to_match.intersection(labels_matched))


async def detect_policy_match(
    policy: str, text: str, config: RailsConfig
) -> PolicyResult:
    """
    Checks whether the provided text matches the specified Clavata policy ID.
    Note that this action will return True if any label in the policy matches the text.

    Args:
        policy: The policy ID to check.
        text: The text to check.
        config: The rails configuration object (injected by runtime)

    Returns:
        True if the text matches the specified Clavata policy ID, False otherwise.
    """
    clavata_config = get_clavata_config(config)
    policy_id = get_policy_id(policy, clavata_config)
    return await evaluate_with_policy(text, policy_id.hex, clavata_config)


@action(execute_async=True)
async def evaluate_with_clavata_policy(
    policy: str,
    text: str,
    config: Optional[RailsConfig] = None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> list[str]:
    """Evaluate the provided text against the specified Clavata policy ID and return a list of labels that matched."""
    if not config:
        raise ClavataPluginValueError("Rails config is required.")

    clavata_config = get_clavata_config(config)
    relevant_chunks = context.get("relevant_chunks", "") if context is not None else ""

    # Combine the user input and relevant chunks into a single string
    text = textwrap.dedent(
        f"""
        Context:
        {relevant_chunks}

        User input:
        {text}
        """
    )

    # Evaluate the text against the Clavata policy
    policy_id = get_policy_id(policy, clavata_config)
    policy_result = await evaluate_with_policy(text, policy_id.hex, clavata_config)

    # Return the list of labels that matched
    return [lbl.label for lbl in policy_result.label_matches if lbl.matched]
