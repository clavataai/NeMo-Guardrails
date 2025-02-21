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
import os

from nemoguardrails import RailsConfig
from nemoguardrails.actions import action
from nemoguardrails.library.clavata.request import clavata_request
from nemoguardrails.rails.llm.config import ClavataConfig

log = logging.getLogger(__name__)


def detect_policy_match_mapping(result: bool) -> bool:
    """
    Mapping for detect_benign.

    Since the function returns True when the input is benign,
    we block if result is False.
    """
    return result


@action(is_system_action=True, output_mapping=detect_policy_match_mapping)
async def detect_policy_match(source: str, text: str, config: RailsConfig, **kwargs):
    """Checks whether the provided text matches the specified Clavata policy ID.

    Args:
        source: The source for the text, i.e. "input", "output", "retrieval".
        text: The text to check.
        config: The rails configuration object.

    Returns:
        True if the text matches the specified Clavata policy ID, False otherwise.
    """
    clavata_config: ClavataConfig = getattr(config.rails.config, "clavata")
    clavata_api_key = os.environ.get("CLAVATA_API_KEY")

    # Get the correct config based on the source
    config_section = getattr(clavata_config, source, None)
    if config_section is None:
        raise ValueError(f"No Clavata configuration found for source: {source}")

    server_endpoint = getattr(config_section, "server_endpoint", None)
    policy_id = getattr(config_section, "policy_id", None)

    if not clavata_api_key:
        raise ValueError(
            "CLAVATA_API_KEY environment variable required the Clavata integration."
        )

    if policy_id is None:
        raise ValueError("Policy ID is required for the Clavata integration.")

    if not server_endpoint:
        raise ValueError("Server endpoint is required for the Clavata integration.")

    valid_sources = ["input", "output"]
    if source not in valid_sources:
        raise ValueError(
            f"Clavata can only be defined in the following flows: {valid_sources}. "
            f"The current flow, '{source}', is not allowed."
        )

    clavata_response = await clavata_request(
        text, policy_id, server_endpoint, clavata_api_key
    )

    matches = []
    if clavata_response:
        results = clavata_response.get("job", {}).get("results", [])
        if results:
            # First result is sufficient, given we are only ever sending one content item
            first_result = results[0]
            section_reports = first_result.get("report", {}).get(
                "sectionEvaluationReports", []
            )
            matches = [
                section["name"]
                for section in section_reports
                if section.get("result") == "OUTCOME_TRUE"
            ]

    return bool(matches)
