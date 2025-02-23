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
import re
from typing import TYPE_CHECKING, List, Literal, Tuple

from pydantic import BaseModel, Field

from nemoguardrails import RailsConfig
from nemoguardrails.actions import action
from nemoguardrails.library.clavata.request import clavata_create_job
from nemoguardrails.rails.llm.config import ClavataRailConfig, ClavataRailOptions

from .errs import ClavataPluginAPIError, ClavataPluginValueError

if TYPE_CHECKING:
    from .request import Report, SectionReport

log = logging.getLogger(__name__)

VALID_RAILS = ["input", "output"]


is_uuid = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


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


def _pre_run_checks(rail: str) -> None:
    """
    Perform pre-run checks to ensure the Clavata integration is configured correctly.
    """
    if rail not in VALID_RAILS:
        raise ClavataPluginValueError(
            f"Clavata can only be defined in the following flows: {VALID_RAILS}. "
            f"The current flow, '{rail}', is not allowed."
        )


def _get_configs(
    rail: str, config: RailsConfig
) -> Tuple[ClavataRailConfig, ClavataRailOptions]:
    """Get the Clavata config and flow config for the given source."""
    clavata_config: ClavataRailConfig = getattr(config.rails.config, "clavata")
    flow_cfg: ClavataRailOptions = getattr(clavata_config, rail)
    return clavata_config, flow_cfg


async def _get_policy_result(
    text: str,
    rail_config: ClavataRailOptions,
    clavata_config: ClavataRailConfig,
) -> PolicyResult:
    """Get the policy result for the given source."""
    endpoint = f"{clavata_config.server_endpoint}/v1/jobs"
    job = await clavata_create_job(text, rail_config.policy_id, endpoint)

    reports = [res.report for res in job.results]

    try:
        return [PolicyResult.from_report(report) for report in reports][0]
    except IndexError as e:
        raise ClavataPluginAPIError("No policy results in API response.") from e


@action(name="DetectPolicyMatchAction", is_system_action=True, execute_async=True)
async def detect_policy_match(
    rail: Literal["input", "output"], text: str, config: RailsConfig
) -> bool:
    """Checks whether the provided text matches the specified Clavata policy ID.

    Args:
        source: The source for the text, i.e. "input", "output", "retrieval".
        text: The text to check.
        config: The rails configuration object.

    Returns:
        True if the text matches the specified Clavata policy ID, False otherwise.
    """
    _pre_run_checks(rail)
    clavata_config, rail_config = _get_configs(rail, config)
    policy_result = await _get_policy_result(text, rail_config, clavata_config)

    if policy_result.failed:
        raise ClavataPluginAPIError("Policy evaluation failed.")

    labels = rail_config.labels
    if len(labels) == 0:
        # When labels is empty, we consider any match to be a match
        return policy_result.policy_matched

    # If labels are provided we need to match sure those specific labels are matched
    labels_to_match = set(labels)
    labels_matched = set(
        lbl.label for lbl in policy_result.label_matches if lbl.matched
    )
    return labels_to_match.issubset(labels_matched)
