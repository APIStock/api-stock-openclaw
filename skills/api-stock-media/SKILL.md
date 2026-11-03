---
name: api-stock-media
description: Create images, videos or music through API Stock when the user wants media as part of an agent task. Discover current model inputs, estimate the charge, create once and retrieve the result.
metadata: {"openclaw":{"requires":{"bins":["python3"],"env":["API_STOCK_KEY"]},"primaryEnv":"API_STOCK_KEY"}}
---

# API Stock media

Use `python3 {baseDir}/scripts/api_stock.py`. The helper needs Python 3.10+
and uses only its standard library. It reads `API_STOCK_KEY` from the runtime
environment. Keep the key out of messages, commands, generated files and logs.
Use your API Stock account and API key.

## Choose and quote

Run `doctor` to check credentials and discover chat models without creating
a paid request. Run `catalog --model MODEL_ID` for current media inputs and
prices. Read `inputSchema`; never infer media parameters from an LLM model.
Public API input names are camelCase. One request asks for one generation.
A task may return multiple files in `files[]` or structured `output`.

Write the requested `model` and `input` to a local JSON file, then quote it:

```sh
python3 {baseDir}/scripts/api_stock.py estimate --request request.json
```

The quote's `costMicroUsd` is millionths of USD. `costUsd` is USD. A quote
does not create a generation. Check the user's spending authorization and
the selected request against the quote before proceeding. An existing
authorization covering this task and ceiling is sufficient.

## Create once and continue

```sh
python3 {baseDir}/scripts/api_stock.py run --request request.json \
  --state image-task.json --max-cost-usd 0.05 --confirm-paid --timeout 60
```

The ceiling above is an example, not a price promise. Use the user's actual
authorized ceiling. The helper saves an idempotency key before sending the
request and also sends the ceiling to the server. Keep the state file for
this logical generation. It contains task metadata and a request hash, not
the API key or prompt. The request file itself contains the user's input.

On POSIX, file and parent-directory sync must succeed before each creation
attempt, including retries. Use storage that honours these sync operations.
On other platforms, recovery covers process interruption; power-loss durability
is not guaranteed. Treat a sync error as a stop, never as permission to create
a new state or key.

State format 2 is bound to the exact API key through its request fingerprint.
A different or rotated key is rejected even if it belongs to the same account.
Legacy format 1 states are preserved and rejected, never auto-migrated.
For format 2, resume with the original credential. For format 1 or an
unavailable original credential, inspect the original account's dashboard and
poll a recorded task id using a key for that account. Never bypass a mismatch by creating replacement state for
an uncertain submission.

If the command times out, loses the connection or is interrupted, preserve
both files. Repeat the same command and state file to recover the same task.
Never use a new state file merely to recover an uncertain creation. If a
process was killed and left a `.lock`, check that it has stopped before
removing only that lock. Preserve the JSON state.

For an existing task:

```sh
python3 {baseDir}/scripts/api_stock.py wait TASK_ID --timeout 60
```

`waiting` means polling stopped at its local deadline; the remote generation
may still run. `finished`, `failed` and `expired` are terminal. A failed or
expired task needs a deliberate new request if the user still wants another
attempt. Insufficient balance requires a top-up by the user, not an automatic
payment. HTTP 429 requires waiting before resuming the same state.

## Return the usable result

Wait for `finished`. Read `files[].fileUrl` and `output`; some actions return
structured output with no file. Return links or use the media in the user's
requested local artifact. If downloading media, use a separate request
without the API bearer key. Do not publish the result to other services
unless the user's task authorizes that action.

Report the model, task status and estimate separately from final billing.
Never describe fixture output as a real generation or an estimate as an
observed final charge. Chat and agent reasoning use the configured LLM
provider; this skill adds media tools.
