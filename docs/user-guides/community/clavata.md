# Clavata Integration

[Clavata](https://clavata.ai) provides content moderation capabilities to detect and filter inappropriate content. This integration enables NeMo Guardrails to use Clavata for content moderation in input and output flows.

## Getting Access

To sign up for Clavata or obtain an API key:

- [Request access](https://www.clavata.ai/requestaccess) through the website
- Contact support at <hello@clavata.ai>

## Setup

1. Ensure you have access to the Clavata platform and have configured your content moderation policies. You'll need:
   - Your Clavata API key
   - Policy IDs for the content types you want to moderate
   - (Optional) A custom server endpoint if provided by Clavata.ai

2. Set the `CLAVATA_API_KEY` environment variable with your Clavata API key:

   ```bash
   export CLAVATA_API_KEY="your-api-key"
   ```

3. Configure your `config.yml` according to the following example:

```yaml
rails:
  config:
    clavata:
      policies:
        - alias: Violence
          id: 00000000-0000-0000-0000-000000000000
        - alias: Weapons
          id: 00000000-0000-0000-0000-000000000000
      input:
        # Reference an alias above in `policies`
        policy: Violence
        # Optional: Specify labels to require specific matches
        labels:
          - Violence
          - Weapons
          - Drugs
        label_match_logic: ALL  # "ALL" | "ANY"
      output:
        policy: Weapons
      # Optional: Only provide this if you've been told to by Clavata.ai
      server_endpoint: "https://some-alt-endpoint.com"
  # Optional: reference the built-in flows
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

The Clavata integration provides two ways to implement content moderation:

### 1. Built-in Flows

Add these flows to your configuration to automatically check content:

```yaml
rails:
  input:
    flows:
      - clavata check input  # Check user input
  output:
    flows:
      - clavata check output  # Check LLM output
```

### 2. Programmatic Usage

Use the `DetectPolicyMatchAction` in your Colang flows to check content:

```colang
# Check input content
$is_match = await DetectPolicyMatchAction(rail="input", text=$user_message)

# Check output content
$is_match = await DetectPolicyMatchAction(rail="output", text=$bot_message)
```

The action returns `True` if the content matches the specified policy's criteria.

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
