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

from nemoguardrails import RailsConfig
from nemoguardrails.actions.actions import ActionResult, action
from nemoguardrails.library.clavata.actions import LabelResult, PolicyResult
from nemoguardrails.library.clavata.errs import ClavataPluginValueError
from tests.utils import TestChat


# Common test fixtures and helper functions
@action()
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
def test_clavata_no_active_policy_check():
    """Test that without active policy checks, messages pass through."""
    config = RailsConfig.from_content(
        yaml_content="""
            models: []
            rails:
              config:
                clavata:
                  policies:
                    - alias: AnimalSounds
                      id: 00000000-0000-0000-0000-000000000000
                    - alias: FarmAnimals
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
@patch("nemoguardrails.library.clavata.actions._get_policy_result")
async def test_clavata_input_policy_check(mock_get_policy_result):
    """Test that input policy checks block messages about animal sounds."""
    # Mock the policy result to indicate a policy match
    mock_policy_result = PolicyResult(
        failed=False,
        policy_matched=True,
        label_matches=[
            LabelResult(
                label="DogBarking",
                message="This content contains dog barking",
                matched=True,
            )
        ],
    )
    mock_get_policy_result.return_value = mock_policy_result

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

    chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")
    chat >> "Hi! I want to talk about dogs barking."
    chat << "I cannot respond to that request."


@pytest.mark.unit
@patch("nemoguardrails.library.clavata.actions._get_policy_result")
async def test_clavata_output_policy_check(mock_get_policy_result):
    """Test that output policy checks block responses about farm animals."""
    # First call for input check - no match
    input_policy_result = PolicyResult(
        failed=False,
        policy_matched=False,
        label_matches=[],
    )
    # Second call for output check - match found
    output_policy_result = PolicyResult(
        failed=False,
        policy_matched=True,
        label_matches=[
            LabelResult(
                label="CowMooing",
                message="This content contains cow mooing",
                matched=True,
            )
        ],
    )
    mock_get_policy_result.side_effect = [input_policy_result, output_policy_result]

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
                    - alias: AnimalSounds
                      id: 00000000-0000-0000-0000-000000000000
                    - alias: FarmAnimals
                      id: 00000000-0000-0000-0000-000000000000
                  input:
                    policy: AnimalSounds
                  output:
                    policy: FarmAnimals
              input:
                flows:
                  - clavata check input
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

    chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")
    chat >> "Tell me about cows"
    chat << "I cannot respond to that request."


# Tests for label matching logic
@pytest.mark.unit
@patch("nemoguardrails.library.clavata.actions._get_policy_result")
async def test_clavata_label_match_logic_any(mock_get_policy_result):
    """Test that label_match_logic: ANY works correctly when at least one label matches."""
    # Mock the policy result with multiple labels, only one matching
    mock_policy_result = PolicyResult(
        failed=False,
        policy_matched=True,
        label_matches=[
            LabelResult(label="DogBarking", message="Dog barking", matched=True),
            LabelResult(label="CatMeowing", message="Cat meowing", matched=False),
            LabelResult(label="CowMooing", message="Cow mooing", matched=False),
        ],
    )
    mock_get_policy_result.return_value = mock_policy_result

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

    chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")
    chat >> "Hi! I want to talk about dogs barking."
    # Since DogBarking matched and we're using ANY logic, the message should be blocked
    chat << "I cannot respond to that request."


@pytest.mark.unit
@patch("nemoguardrails.library.clavata.actions._get_policy_result")
async def test_clavata_label_match_logic_any_no_match(mock_get_policy_result):
    """Test that label_match_logic: ANY allows messages when no specified labels match."""
    # Mock the policy result with multiple labels, none of our specified ones matching
    mock_policy_result = PolicyResult(
        failed=False,
        policy_matched=True,  # Policy matched overall
        label_matches=[
            LabelResult(label="DogBarking", message="Dog barking", matched=False),
            LabelResult(label="CatMeowing", message="Cat meowing", matched=False),
            LabelResult(
                label="HorseNeighing",  # This one matched but isn't in our specified labels
                message="Horse neighing",
                matched=True,
            ),
        ],
    )
    mock_get_policy_result.return_value = mock_policy_result

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

    chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")
    chat >> "Hi! I want to talk about horses neighing."
    # Since none of our specified labels matched, the message should pass through
    chat << "Hello there!"


@pytest.mark.unit
@patch("nemoguardrails.library.clavata.actions._get_policy_result")
async def test_clavata_label_match_logic_all(mock_get_policy_result):
    """Test that label_match_logic: ALL requires all specified labels to match."""
    # Mock the policy result with all specified labels matching
    mock_policy_result = PolicyResult(
        failed=False,
        policy_matched=True,
        label_matches=[
            LabelResult(label="DogBarking", message="Dog barking", matched=True),
            LabelResult(label="CatMeowing", message="Cat meowing", matched=True),
            LabelResult(label="CowMooing", message="Cow mooing", matched=True),
        ],
    )
    mock_get_policy_result.return_value = mock_policy_result

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

    chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")
    chat >> "Hi! I want to talk about all animal sounds."
    # Since all specified labels matched and we're using ALL logic, the message should be blocked
    chat << "I cannot respond to that request."


@pytest.mark.unit
@patch("nemoguardrails.library.clavata.actions._get_policy_result")
async def test_clavata_label_match_logic_all_partial_match(mock_get_policy_result):
    """Test that label_match_logic: ALL allows messages when only some labels match."""
    # Mock the policy result with only some labels matching
    mock_policy_result = PolicyResult(
        failed=False,
        policy_matched=True,
        label_matches=[
            LabelResult(label="DogBarking", message="Dog barking", matched=True),
            LabelResult(label="CatMeowing", message="Cat meowing", matched=True),
            LabelResult(label="CowMooing", message="Cow mooing", matched=False),
        ],
    )
    mock_get_policy_result.return_value = mock_policy_result

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

    chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")
    chat >> "Hi! I want to talk about dogs and cats but not cows."
    # Since not all specified labels matched and we're using ALL logic, the message should pass through
    chat << "Hello there!"


@pytest.mark.unit
@patch("nemoguardrails.library.clavata.actions._get_policy_result")
async def test_clavata_empty_labels(mock_get_policy_result):
    """Test that when labels is empty, any policy match blocks the message."""
    # Mock the policy result with a match
    mock_policy_result = PolicyResult(
        failed=False,
        policy_matched=True,  # Overall policy matched
        label_matches=[
            LabelResult(
                label="SomeLabel",
                message="This content matches some label",
                matched=True,
            ),
        ],
    )
    mock_get_policy_result.return_value = mock_policy_result

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

    chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")
    chat >> "Hi! I want to talk about something that matches the policy."
    # Since the policy matched and no specific labels were configured, the message should be blocked
    chat << "I cannot respond to that request."


@pytest.mark.unit
@patch("nemoguardrails.library.clavata.actions._get_policy_result")
async def test_clavata_policy_no_match(mock_get_policy_result):
    """Test that when the policy doesn't match at all, the message passes through."""
    # Mock the policy result with no match
    mock_policy_result = PolicyResult(
        failed=False,
        policy_matched=False,  # Policy didn't match
        label_matches=[],
    )
    mock_get_policy_result.return_value = mock_policy_result

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

    chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")
    chat >> "Hi! I want to talk about something completely innocent."
    # Since the policy didn't match at all, the message should pass through
    chat << "Hello there!"


@pytest.mark.unit
@patch("nemoguardrails.library.clavata.actions._get_policy_result")
async def test_clavata_evaluate_with_policy(mock_get_policy_result):
    """Test the evaluate_with_clavata_policy action."""
    # Mock the policy result
    mock_policy_result = PolicyResult(
        failed=False,
        policy_matched=True,
        label_matches=[
            LabelResult(label="DogBarking", message="Dog barking", matched=True),
            LabelResult(label="CatMeowing", message="Cat meowing", matched=True),
        ],
    )
    mock_get_policy_result.return_value = mock_policy_result

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

    # Register the retrieve_relevant_chunks action
    chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")

    # Set up the context for the action
    chat.app.register_action_param(
        "EvaluateUserInputWithClavataPolicy",
        "context",
        {
            "user_input": "What sounds do dogs and cats make?",
            "relevant_chunks": "Mock retrieved context.",
        },
    )

    chat >> "What sounds do dogs and cats make?"
    chat << "I cannot discuss dog sounds."


@pytest.mark.unit
def test_clavata_missing_api_key():
    """
    Test that an error is raised when the API key is missing.

    Note: This test doesn't make actual API calls - it tests the error handling
    in the code when the API key environment variable is not set.
    """
    with patch.dict(os.environ, {"CLAVATA_API_KEY": ""}):
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

        chat.app.register_action(retrieve_relevant_chunks, "retrieve_relevant_chunks")

        with pytest.raises(
            ClavataPluginValueError,
            match="CLAVATA_API_KEY environment variable is not set",
        ):
            chat >> "Hi!"
