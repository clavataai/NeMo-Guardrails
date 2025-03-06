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

import os
from unittest.mock import patch

import pytest
from aioresponses import aioresponses

from nemoguardrails import RailsConfig
from nemoguardrails.actions.actions import ActionResult, action
from nemoguardrails.library.clavata.actions import LabelResult, PolicyResult
from nemoguardrails.library.clavata.errs import ClavataPluginValueError
from tests.utils import TestChat


@action(is_system_action=True)
def retrieve_relevant_chunks():
    context_updates = {"relevant_chunks": "Mock retrieved context."}
    return ActionResult(
        return_value=context_updates["relevant_chunks"],
        context_updates=context_updates,
    )


# Base colang content used in most tests
BASE_COLANG = """
    define user express greeting
      "hi"

    define flow
      user express greeting
      bot express greeting

    define bot express greeting
      "Hello there!"

    define bot refuse to respond
      "I cannot respond to that request."
"""


@pytest.mark.unit
def test_clavata_no_active_policy_check(monkeypatch):
    """Test that without active policy checks, messages pass through."""
    monkeypatch.setenv("CLAVATA_API_KEY", "")

    config = RailsConfig.from_content(
        yaml_content="""
            models: []
            rails:
              config:
                clavata:
                  policies:
                    - alias: Violence
                      id: 00000000-0000-0000-0000-000000000000
        """,
        colang_content=BASE_COLANG,
    )

    chat = TestChat(
        config,
        llm_completions=[
            "  express greeting",
            '  "Hello there!"',
        ],
    )

    chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")
    chat >> "Hi! I want to talk about dogs barking."
    chat << "Hello there!"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clavata_input_policy_check(monkeypatch):
    """Test that input policy checks block messages about animal sounds."""
    monkeypatch.setenv("CLAVATA_API_KEY", "test_api_key")

    config = RailsConfig.from_content(
        yaml_content="""
            models: []
            rails:
              config:
                clavata:
                  policies:
                    - alias: AnimalSounds
                      id: 00000000-0000-0000-0000-000000000000
                  input:
                    policy: AnimalSounds
              input:
                flows:
                  - clavata check input
        """,
        colang_content=BASE_COLANG,
    )

    chat = TestChat(
        config,
        llm_completions=[
            "  express greeting",
            '  "Hello there!"',
        ],
    )

    # Mock response from Clavata API
    with aioresponses() as m:
        chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")

        # Use the factory to create a response with a matching policy and label
        mock_response = create_clavata_response(labels={"DogBarking": True})

        m.post(
            "https://gateway.app.clavata.ai:8443/v1/jobs",
            payload=mock_response,
            status=200,
        )

        chat >> "Woof woof"
        await chat.bot_async("I cannot respond to that request.")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clavata_output_policy_check(monkeypatch):
    """Test that output policy checks block responses about farm animals."""
    monkeypatch.setenv("CLAVATA_API_KEY", "test_api_key")

    # Custom colang for this test
    custom_colang = """
        define user ask about farm animals
          "Tell me about cows"

        define flow
          user ask about farm animals
          bot respond about farm animals

        define bot respond about farm animals
          "Cows say moo and live on farms..."

        define bot refuse to respond
          "I cannot respond to that request."
    """

    config = RailsConfig.from_content(
        yaml_content="""
            models: []
            rails:
              config:
                clavata:
                  policies:
                    - alias: FarmAnimals
                      id: 00000000-0000-0000-0000-000000000000
                  output:
                    policy: FarmAnimals
              output:
                flows:
                  - clavata check output
        """,
        colang_content=custom_colang,
    )

    chat = TestChat(
        config,
        llm_completions=[
            "  ask about farm animals",
            '  "Cows say moo and live on farms..."',
        ],
    )

    # Mock response from Clavata API
    with aioresponses() as m:
        chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")

        # Second call for output check - match found
        mock_response = create_clavata_response(labels={"CowMooing": True})

        m.post(
            "https://gateway.app.clavata.ai:8443/v1/jobs",
            payload=mock_response,
            status=200,
        )

        chat >> "Tell me about cows"
        await chat.bot_async("I cannot respond to that request.")


# Tests for label matching logic
@pytest.mark.unit
@pytest.mark.asyncio
async def test_clavata_label_match_logic_any(monkeypatch):
    """Test that label_match_logic: ANY works correctly when at least one label matches."""
    monkeypatch.setenv("CLAVATA_API_KEY", "test_api_key")

    config = RailsConfig.from_content(
        yaml_content="""
            models: []
            rails:
              config:
                clavata:
                  policies:
                    - alias: AnimalSoundsPolicy
                      id: 00000000-0000-0000-0000-000000000000
                  input:
                    policy: AnimalSoundsPolicy
                    labels:
                      - DogBarking
                      - CatMeowing
                      - CowMooing
                    label_match_logic: ANY
              input:
                flows:
                  - clavata check input
        """,
        colang_content=BASE_COLANG,
    )

    chat = TestChat(
        config,
        llm_completions=[
            "  express greeting",
            '  "Hello there!"',
        ],
    )

    # Mock response from Clavata API
    with aioresponses() as m:
        chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")

        # Create response with one matching label
        mock_response = create_clavata_response(
            failed=False,
            policy_matched=True,
            labels={"DogBarking": True, "CatMeowing": False, "CowMooing": False},
        )

        m.post(
            "https://gateway.app.clavata.ai:8443/v1/jobs",
            payload=mock_response,
            status=200,
        )

        chat >> "Hi! I want to talk about dogs barking."
        # Since DogBarking matched and we're using ANY logic, the message should be blocked
        await chat.bot_async("I cannot respond to that request.")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clavata_label_match_logic_any_no_match(monkeypatch):
    """Test that label_match_logic: ANY allows messages when no specified labels match."""
    monkeypatch.setenv("CLAVATA_API_KEY", "test_api_key")

    config = RailsConfig.from_content(
        yaml_content="""
            models: []
            rails:
              config:
                clavata:
                  policies:
                    - alias: AnimalSoundsPolicy
                      id: 00000000-0000-0000-0000-000000000000
                  input:
                    policy: AnimalSoundsPolicy
                    labels:
                      - DogBarking
                      - CatMeowing
                    label_match_logic: ANY
              input:
                flows:
                  - clavata check input
        """,
        colang_content=BASE_COLANG,
    )

    chat = TestChat(
        config,
        llm_completions=[
            "  express greeting",
            '  "Hello there!"',
        ],
    )

    # Mock response from Clavata API
    with aioresponses() as m:
        chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")

        # Create response with a different label matching
        mock_response = create_clavata_response(
            failed=False,
            policy_matched=True,
            labels={"DogBarking": False, "CatMeowing": False, "HorseNeighing": True},
        )

        m.post(
            "https://gateway.app.clavata.ai:8443/v1/jobs",
            payload=mock_response,
            status=200,
        )

        chat >> "Hi! I want to talk about horses neighing."
        # Since none of our specified labels matched, the message should pass through
        await chat.bot_async("Hello there!")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clavata_label_match_logic_all(monkeypatch):
    """Test that label_match_logic: ALL requires all specified labels to match."""
    monkeypatch.setenv("CLAVATA_API_KEY", "test_api_key")

    config = RailsConfig.from_content(
        yaml_content="""
            models: []
            rails:
              config:
                clavata:
                  policies:
                    - alias: AnimalSoundsPolicy
                      id: 00000000-0000-0000-0000-000000000000
                  input:
                    policy: AnimalSoundsPolicy
                    labels:
                      - DogBarking
                      - CatMeowing
                      - CowMooing
                    label_match_logic: ALL
              input:
                flows:
                  - clavata check input
        """,
        colang_content=BASE_COLANG,
    )

    chat = TestChat(
        config,
        llm_completions=[
            "  express greeting",
            '  "Hello there!"',
        ],
    )

    # Mock response from Clavata API
    with aioresponses() as m:
        chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")

        # Create response with all labels matching
        mock_response = create_clavata_response(
            failed=False,
            policy_matched=True,
            labels={"DogBarking": True, "CatMeowing": True, "CowMooing": True},
        )

        m.post(
            "https://gateway.app.clavata.ai:8443/v1/jobs",
            payload=mock_response,
            status=200,
        )

        chat >> "Hi! I want to talk about all animal sounds."
        # Since all specified labels matched and we're using ALL logic, the message should be blocked
        await chat.bot_async("I cannot respond to that request.")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clavata_label_match_logic_all_partial_match(monkeypatch):
    """Test that label_match_logic: ALL allows messages when only some labels match."""
    monkeypatch.setenv("CLAVATA_API_KEY", "test_api_key")

    config = RailsConfig.from_content(
        yaml_content="""
            models: []
            rails:
              config:
                clavata:
                  policies:
                    - alias: AnimalSoundsPolicy
                      id: 00000000-0000-0000-0000-000000000000
                  input:
                    policy: AnimalSoundsPolicy
                    labels:
                      - DogBarking
                      - CatMeowing
                      - CowMooing
                    label_match_logic: ALL
              input:
                flows:
                  - clavata check input
        """,
        colang_content=BASE_COLANG,
    )

    chat = TestChat(
        config,
        llm_completions=[
            "  express greeting",
            '  "Hello there!"',
        ],
    )

    # Mock response from Clavata API
    with aioresponses() as m:
        chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")

        # Create response with only some labels matching
        mock_response = create_clavata_response(
            failed=False,
            policy_matched=True,
            labels={"DogBarking": True, "CatMeowing": True, "CowMooing": False},
        )

        m.post(
            "https://gateway.app.clavata.ai:8443/v1/jobs",
            payload=mock_response,
            status=200,
        )

        chat >> "Hi! I want to talk about dogs and cats but not cows."
        # Since not all specified labels matched and we're using ALL logic, the message should pass through
        await chat.bot_async("Hello there!")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clavata_empty_labels(monkeypatch):
    """Test that when labels is empty, any policy match blocks the message."""
    monkeypatch.setenv("CLAVATA_API_KEY", "test_api_key")

    config = RailsConfig.from_content(
        yaml_content="""
            models: []
            rails:
              config:
                clavata:
                  policies:
                    - alias: AnimalSoundsPolicy
                      id: 00000000-0000-0000-0000-000000000000
                  input:
                    policy: AnimalSoundsPolicy
                    # No labels specified, so any policy match should block
              input:
                flows:
                  - clavata check input
        """,
        colang_content=BASE_COLANG,
    )

    chat = TestChat(
        config,
        llm_completions=[
            "  express greeting",
            '  "Hello there!"',
        ],
    )

    # Mock response from Clavata API
    with aioresponses() as m:
        chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")

        # Create response with a policy match
        mock_response = create_clavata_response(
            failed=False, policy_matched=True, labels={"SomeLabel": True}
        )

        m.post(
            "https://gateway.app.clavata.ai:8443/v1/jobs",
            payload=mock_response,
            status=200,
        )

        chat >> "Hi! I want to talk about something that matches the policy."
        # Since the policy matched and no specific labels were configured, the message should be blocked
        await chat.bot_async("I cannot respond to that request.")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clavata_policy_no_match(monkeypatch):
    """Test that when the policy doesn't match at all, the message passes through."""
    monkeypatch.setenv("CLAVATA_API_KEY", "test_api_key")

    config = RailsConfig.from_content(
        yaml_content="""
            models: []
            rails:
              config:
                clavata:
                  policies:
                    - alias: AnimalSoundsPolicy
                      id: 00000000-0000-0000-0000-000000000000
                  input:
                    policy: AnimalSoundsPolicy
              input:
                flows:
                  - clavata check input
        """,
        colang_content=BASE_COLANG,
    )

    chat = TestChat(
        config,
        llm_completions=[
            "  express greeting",
            '  "Hello there!"',
        ],
    )

    # Mock response from Clavata API
    with aioresponses() as m:
        chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")

        # Create response with no policy match
        mock_response = create_clavata_response(
            failed=False, policy_matched=False, labels={}
        )

        m.post(
            "https://gateway.app.clavata.ai:8443/v1/jobs",
            payload=mock_response,
            status=200,
        )

        chat >> "Hi! I want to talk about something innocent."
        await chat.bot_async("Hello there!")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clavata_evaluate_with_policy(monkeypatch):
    """Test the evaluate_with_clavata_policy action."""
    monkeypatch.setenv("CLAVATA_API_KEY", "test_api_key")

    # Custom colang for this test
    custom_colang = """
        define user ask question
          "What sounds do dogs and cats make?"

        define flow
          user ask question
          $labels = await EvaluateUserInputWithClavataPolicy(policy="AnimalSoundsPolicy")
          if "DogBarking" in $labels
            bot refuse dog sounds
          else if "CatMeowing" in $labels
            bot refuse cat sounds
          else
            bot respond to question

        define bot refuse dog sounds
          "I cannot discuss dog sounds."

        define bot refuse cat sounds
          "I cannot discuss cat sounds."

        define bot respond to question
          "I can answer your question."
    """

    config = RailsConfig.from_content(
        yaml_content="""
            models: []
            rails:
              config:
                clavata:
                  policies:
                    - alias: AnimalSoundsPolicy
                      id: 00000000-0000-0000-0000-000000000000
        """,
        colang_content=custom_colang,
    )

    chat = TestChat(
        config,
        llm_completions=[
            "  ask question",
            '  "I cannot discuss dog sounds."',
        ],
    )

    # Mock response from Clavata API
    with aioresponses() as m:
        # Register the retrieve_relevant_chunks action
        chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")

        # Create response with dog barking label match
        mock_response = create_clavata_response(
            failed=False,
            policy_matched=True,
            labels={"DogBarking": True, "CatMeowing": True},
        )

        m.post(
            "https://gateway.app.clavata.ai:8443/v1/jobs",
            payload=mock_response,
            status=200,
        )

        # Set up the context for the action
        chat.app.register_action_param(
            "EvaluateUserInputWithClavataPolicy",
            {
                "policy": "AnimalSoundsPolicy",
                "user_input": "What sounds do dogs and cats make?",
                "relevant_chunks": "Mock retrieved context.",
            },
        )

        chat >> "What sounds do dogs and cats make?"
        await chat.bot_async("I cannot discuss dog sounds.")


def create_clavata_response(failed=False, labels=None):
    """
    Create a properly formatted Clavata API response.

    Args:
        failed (bool): Whether the API call failed
        labels (dict): Dictionary of label names to match status, e.g. {"DogBarking": True, "CatMeowing": False}
                      If None, no labels will be included

    Returns:
        dict: A properly formatted Clavata API response
    """
    if labels is None:
        labels = {}

    # Determine policy_matched based on whether any label is True
    policy_matched = any(matched for matched in labels.values())

    # Create label_matches structure
    label_matches = [
        {
            "label": label_name,
            "message": f"This content contains {label_name.lower()}",
            "matched": matched,
        }
        for label_name, matched in labels.items()
    ]

    # Create the response structure
    response = {
        "job": {
            "failed": failed,
            "policy_matched": policy_matched,
            "label_matches": label_matches,
            "status": "JOB_STATUS_COMPLETED",
            "results": [
                {
                    "policy_matched": policy_matched,
                    "label_matches": label_matches,
                    "report": {
                        "policy_id": "00000000-0000-0000-0000-000000000000",
                        "policy_name": "TestPolicy",
                        "policy_matched": policy_matched,
                        "label_matches": label_matches,
                        "result": "OUTCOME_TRUE" if policy_matched else "OUTCOME_FALSE",
                        "sectionEvaluationReports": [
                            {
                                "section": "main",
                                "matched": policy_matched,
                                "name": "Main Section",
                                "message": "Section evaluation result",
                                "result": (
                                    "OUTCOME_TRUE"
                                    if policy_matched
                                    else "OUTCOME_FALSE"
                                ),
                                "labels": [
                                    {
                                        "name": label_name,
                                        "matched": matched,
                                        "message": f"This content contains {label_name.lower()}",
                                    }
                                    for label_name, matched in labels.items()
                                ],
                            }
                        ],
                    },
                }
            ],
            "created": "2023-01-01T00:00:00Z",
            "updated": "2023-01-01T00:00:01Z",
            "completed": "2023-01-01T00:00:02Z",
        }
    }

    return response
