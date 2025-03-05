# Clavata Integration

[Clavata](https://clavata.ai) provides content moderation capabilities to detect and filter inappropriate content. This integration enables NeMo Guardrails to use Clavata for content moderation in input and output flows.

To request access to Clavata please visit: https://www.clavata.ai/requestaccess or email hello@clavata.ai

## Setup

1. Ensure you have access to the Clavata platform and have configured your content moderation policies. You'll need:
   - Your Clavata API key
   - Policy IDs for the content types you want to moderate
   - (Optional) A custom server endpoint if provided by Clavata.ai

2. Set the `CLAVATA_API_KEY` environment variable with your Clavata API key.

3. Update your `config.yml` file to include the Clavata settings:

```yaml
rails:
  config:
    clavata:
      # Only provide this if you've been told to by Clavata.ai
      server_endpoint: "https://some-alt-endpoint.com"
      policies:
        - alias: "Violence"
          id: "00000000-0000-0000-0000-000000000000"
        - alias: "Weapons"
          id: "00000000-0000-0000-0000-000000000000"
      input:
        policy: "Violence"
        # Optional: Specify labels to require specific matches
        labels:
          - "Violence"
          - "Weapons"
          - "Drugs"
        label_match_logic: ALL  # Can be "ALL" or "ANY"
      output:
        policy: "Weapons"
  input:
    flows:
      - clavata check input
  output:
    flows:
      - clavata check output
```

## Configuration Details

- `server_endpoint`: The Clavata API endpoint (only if provided by Clavata.ai)
- `policies`: List of policy configurations with aliases and IDs
- `input/output`: Flow-specific configurations
  - `policy`: The policy alias to use for this flow
  - `labels`: (Optional) List of specific labels to check for
  - `label_match_logic`: (Optional) "ALL" requires all specified labels to match, "ANY" requires at least one match

## Usage

Once configured, the Clavata integration can automatically:

1. Check user inputs against specified content moderation policies before they are processed by the LLM
2. Check LLM outputs against specified content moderation policies before they are sent back to the user

The `detect_policy_match` action in `nemoguardrails/library/clavata/actions.py` handles the content moderation checks.

## Customization

You can customize the content moderation behavior by:

1. Configuring different policies for input and output flows
2. Specifying which labels must match within a policy
3. Setting the label match logic to either "ALL" (all specified labels must match) or "ANY" (at least one label must match)

## Error Handling

If the Clavata API request fails, the system will raise a `ClavataPluginAPIError`. The integration will also raise a `ClavataPluginValueError` if there are configuration issues, such as:

- Invalid policy aliases
- Missing required configuration
- Invalid flow types

## Notes

- Ensure that your Clavata API key is properly set up and accessible
- The integration currently supports content moderation checks for input and output flows
- You can configure different policies and label requirements for input and output flows
- If no labels are specified for a policy, any label match will be considered a hit

For more information on Clavata and its capabilities, please refer to the [Clavata documentation](https://clavata.helpscoutdocs.com).
