# Product page with a generated illustration

Create a local landing page for a fictional paper-lantern workshop. Use the
API Stock media skill to produce one illustration, then incorporate its
finished file into the page. Do not publish the page.

1. Check the current input schema for the model in `image-request.json`.
   Estimate the exact request. Use the existing user-approved media ceiling,
   or request a ceiling before paid creation. The LLM's token usage is separate.
2. Keep `product-image-task.json` for this logical generation. Resume it after
   an uncertain response. Do not replace the key to recover a pending task.
3. Wait for a terminal result. If it finished, download the illustration
   without an API authorization header and create `product-page/index.html`
   referencing the local image. Include a heading, workshop description and
   a local inquiry form that does not send data anywhere.
4. Write `product-page/evidence.json` with model, task id, status, quoted
   cost and output path. Add actual charged cost only when independently
   observed; otherwise use null. Never include the API key or claim this
   fictional workshop is a real customer.
5. Return the local page path and task status. If generation fails, report
   that outcome instead of substituting an unlabelled stock or fixture image.

This file is a runnable task brief, not a claimed completed generation.
