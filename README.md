# API Stock for OpenClaw

Connect chat models to OpenClaw and give an agent image, video and music tools.
This bundle contains a provider-config generator, a media skill, two task
recipes and read-only diagnostics. Python 3.10+ is the only helper dependency.

## Download and install

Download `https://api-stock.com/integrations/openclaw/api-stock-openclaw.zip`
and extract it with `unzip api-stock-openclaw.zip`. This gives
an `api-stock-openclaw` directory. Install the skill without overwriting an
existing one:

```sh
mkdir -p ~/.openclaw/skills
if mkdir ~/.openclaw/skills/api-stock-media; then
  cp -R api-stock-openclaw/skills/api-stock-media/. ~/.openclaw/skills/api-stock-media/
else
  echo "Skill already exists or cannot be created. Preserve it and compare before installing." >&2
fi
cd api-stock-openclaw
```

The archive contains no dependencies, credentials, hooks or
service installer. Keep an existing skill directory if you customized it;
compare before replacing. OpenClaw also accepts a workspace's
`skills/api-stock-media` directory.

## Credentials and discovery

Create an account and API key at `https://api-stock.com/dashboard/api-keys`.
Provide `API_STOCK_KEY` to the OpenClaw process using its environment or secret
configuration. Run the commands below from a shell or container where
`API_STOCK_KEY` is also exported by the secret manager or service environment.
Do not paste the key into chat, source control, shell history, command arguments,
generated files or logs.
Restart a running Gateway after changing its service environment.

```sh
python3 skills/api-stock-media/scripts/api_stock.py doctor
python3 skills/api-stock-media/scripts/api_stock.py catalog --model nano-banana-2.1
```

Discovery reads the API; it does not create a paid generation. It proves
credential/model discovery, not end-to-end compatibility with every model.

## OpenClaw provider

Choose an exact model id from `doctor`, then generate a fragment:

```sh
python3 skills/api-stock-media/scripts/api_stock.py config \
  --model gpt-6-luna > api-stock-provider.json
```

Merge the fragment into your OpenClaw configuration. Preserve existing agents,
providers, tools and channels; the fragment sets the default model, so retain
your current default if you only want to add a selectable model. The key stays
an `${API_STOCK_KEY}` environment reference. Run:

```sh
openclaw config validate
openclaw models list
openclaw skills check
```

The adapter is `openai-completions` and the base URL ends in `/api/v1`.
API Stock exposes Chat Completions, not the Responses API. The default
32,000-context/4,096-output values are conservative client budgets, not
claims about a model's maximum context or tool quality. Change them only to
supported values. Vision and reasoning metadata are deliberately not asserted.

## First media task

The examples contain prompts and requests, not pre-generated results. Quote
the exact request and review the user's authorization before creation:

```sh
python3 skills/api-stock-media/scripts/api_stock.py estimate \
  --request examples/product-page/image-request.json
```

For an authorized ceiling (the number here is only an example):

```sh
python3 skills/api-stock-media/scripts/api_stock.py run \
  --request examples/product-page/image-request.json \
  --state product-image-task.json --max-cost-usd 0.05 --confirm-paid --timeout 60
```

Keep the same request and state file on an uncertain response. The server
checks the cost ceiling, and the persisted idempotency key recovers the same
generation after a lost response. `waiting` is a local polling deadline, not
a failed remote task. A `.lock` left by a killed process needs inspection
before removal. Keep the JSON state. No cancellation or refund is implied
by stopping the helper; terminal failures use the API's normal refund policy.

On POSIX, the helper syncs the state file and its parent directory before
each creation attempt, including retries. Use storage that supports and
honours these sync operations; a sync error stops creation. On other
platforms, file flush and atomic replacement support process-interruption
recovery, but power-loss durability is not guaranteed.

State format 2 binds the request to the exact API key without storing the
key. Changing or rotating it blocks automatic recovery with that state.
Format 1 states are preserved and rejected; they are never auto-migrated.
For format 2, resume with the original credential. For format 1 or an
unavailable original credential, inspect the original account's dashboard
and poll a recorded task id using a key for that account. Keep an uncertain
submission's state;
never create a replacement state merely to bypass a credential mismatch.

State and request files are local to the runtime. In an OpenClaw sandbox,
make the skill, Python and API key available inside that sandbox; skill env
injection on the host is not automatically inherited by a container.

## Recipes

- `examples/product-page/TASK.md`: write a local product page with one
  generated illustration and a separate provenance/billing record.
- `examples/content-kit/TASK.md`: create local draft copy, a cover and an
  optional video, keeping publication a separate action.

Images returned by the fixture test are explicitly synthetic fixtures and do
not demonstrate model quality. Run the same task against the live API only
with spending authorization. The LLM that runs OpenClaw is billed separately
from media; the media ceiling does not cap the agent's total token spend.

## Verification

For an installed copy, use `doctor`, `openclaw config validate` and
`openclaw skills check` as shown above. The helper's tests and the real-client
fixture run in the maintained source tree before publication.

The source is public at `https://github.com/APIStock/api-stock-openclaw`.

## Sources

- [OpenClaw custom providers](https://docs.openclaw.ai/gateway/config-tools/custom-providers)
- [OpenClaw skills](https://docs.openclaw.ai/tools/skills)
- [API Stock MCP](https://docs.api-stock.com/en/docs/mcp)
- [Task status and webhooks](https://docs.api-stock.com/en/docs/tasks)

This integration is maintained by API Stock; it is not an endorsement by
OpenClaw. This repository and the download are released under the MIT license.
