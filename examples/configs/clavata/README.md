# Clavata Integration

This configuration demonstrates how to integrate with the Clavata API for content moderation.

## Configuration

To use the Clavata integration, you must:

1. Obtain your policy ID from the Clavata platform
2. Set the `CLAVATA_API_KEY` environment variable with your Clavata API key
3. Add it to your `config.yml` file:

### Example Configuration

```yaml
rails:
  config:
    clavata:
      input:
        policy_id: "00000000-0000-0000-0000-000000000000"  # Replace with your actual policy ID
      output:
        policy_id: "00000000-0000-0000-0000-000000000000"  # Replace with your actual policy ID
```

## Flows

The integration includes two main flows:

- `clavata check input`: Validates user input against the specified Clavata policy
- `clavata check output`: Validates bot responses against the specified Clavata policy

## Requirements

- A valid Clavata account
- A configured policy in the Clavata platform
- The policy ID from your Clavata configuration
- A valid Clavata API key
