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

"""Module for handling Clavata requests."""

import logging
from typing import List

import aiohttp
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class ContentData(BaseModel):
    """Represents the content data structure for Clavata API requests."""

    text: str


class JobRequest(BaseModel):
    """Represents the job request structure for Clavata API requests."""

    content_data: List[ContentData]
    policy_id: str
    wait_for_completion: bool = Field(default=True)


class RequestHeaders(BaseModel):
    """Represents the headers structure for Clavata API requests."""

    authorization: str = Field(serialization_alias="Authorization")


async def clavata_request(
    text: str, policy_id: str, server_endpoint: str, api_key: str
):
    """Send a request to the Clavata API.

    Args:
        text: The text to send to the Clavata API.
        policy_id: The policy ID to use for the request.
        server_endpoint: The server endpoint to use for the request.
        api_key: The Clavata API key to use for the request.

    Returns:
        The response from the Clavata API. See Clavata API reference for more details:
        https://api.docs.clavata.net/#tag/Create-Jobs/operation/GatewayService_CreateJob

    Raises:
        ValueError: If api_key is missing for cloud API, if the API call fails,
            or if the response cannot be parsed as JSON.
    """

    payload = JobRequest(
        content_data=[ContentData(text=text)],
        policy_id=policy_id,
        wait_for_completion=True,
    )

    headers = RequestHeaders(authorization=f"Bearer {api_key}").model_dump(
        by_alias=True
    )

    async with aiohttp.ClientSession() as session:
        async with session.post(
            server_endpoint, json=payload.model_dump(), headers=headers
        ) as resp:
            if resp.status != 200:
                raise ValueError(
                    f"Clavata call failed with status code {resp.status}.\n"
                    f"Details: {await resp.text()}"
                )

            try:
                return await resp.json()
            except aiohttp.ContentTypeError:
                raise ValueError(
                    f"Failed to parse Clavata response as JSON. Status: {resp.status}, "
                    f"Content: {await resp.text()}"
                )
