# Draft a content kit with a cover and optional video

Prepare a local draft announcing a fictional paper-lantern workshop. Produce
three short post variants and one cover through the API Stock media skill.
Include the video only when the user explicitly includes it in the task and
budget. Keep all content local; sending or publishing needs its own instruction.

Discover current model inputs and estimate each requested asset. Show the
combined media estimate, and preserve the user's authorized ceiling for each
asset. LLM token spend is separate. Never assume a trial covers a video.

Use `image-request.json` as the cover request and `cover-task.json` as its
state file. For an authorized video, use `video-request.json` as the request
and `video-task.json` as its state file. Reuse each state file when recovering
that request. Wait for
finished results and use their returned file URLs; do not call a queued task
a completed asset. Download without sending the API bearer key to storage.

Save `content-kit/posts.md`, finished media and `content-kit/evidence.json`.
Record model, task id, terminal status, estimate and actual charge when known
for each asset. Keep an unobserved final charge null. Report failures and
missing assets explicitly. Never describe this sample task as a real customer
case or fixture media as a production output.
