#!/usr/bin/env python3
"""API Stock media tools for agents. Python 3.10+, standard library only."""
import argparse
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import hashlib
import http.client
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

SITES = {'api-stock': 'https://api.api-stock.com'}
MAX_RESPONSE = 8 * 1024 * 1024
TERMINAL = {"finished", "failed", "expired"}


class ToolError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A bearer credential must never follow a redirect to another host.
        return None


def micro_usd(value):
    try:
        amount = Decimal(str(value)) * 1_000_000
        if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value() or amount > 2**53 - 1:
            raise ValueError()
        return int(amount)
    except (InvalidOperation, ValueError):
        raise ToolError("Use a non-negative USD ceiling with at most six decimal places.") from None


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Client:
    def __init__(self, origin, key, timeout=30):
        url = urllib.parse.urlsplit(origin)
        local_fixture = url.scheme == "http" and url.hostname == "127.0.0.1" and key == "test-only-key"
        if origin not in SITES.values() and not (local_fixture and url.path in ("", "/") and not url.query and not url.fragment and not url.username):
            raise ToolError("Use an official HTTPS API origin.")
        if not key or "\n" in key or "\r" in key:
            raise ToolError("Set API_STOCK_KEY in the agent runtime; never put it in a prompt.")
        self.origin, self.key, self.timeout = origin.rstrip("/"), key, timeout
        self.http = urllib.request.build_opener(NoRedirect())

    def request(self, path, body=None, headers=None, timeout=None):
        req = urllib.request.Request(self.origin + "/api/v1" + path,
            data=dump(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + self.key, "Accept": "application/json",
                "Content-Type": "application/json", "User-Agent": "api-stock-openclaw/1.0",
                **(headers or {})}, method="POST" if body is not None else "GET")
        try:
            with self.http.open(req, timeout=timeout or self.timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            hints = {401: "Check the API key and storefront.", 402: "Check balance or the cost ceiling.",
                409: "This idempotency key belongs to another request.", 429: "Rate limited; wait before resuming the same state."}
            raise ToolError(f"API HTTP {status}. " + hints.get(status, "Resume the same state if creation was attempted.")) from None
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError):
            raise ToolError("API transport failed. Creation may have succeeded; resume the same state file.") from None
        if len(raw) > MAX_RESPONSE:
            raise ToolError("API response exceeded the size limit.")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ToolError("API returned invalid JSON. Resume the same state if creation was attempted.") from None
        if not isinstance(result, (dict, list)):
            raise ToolError("API returned an unexpected response.")
        return result

    def estimate(self, request):
        response = self.request("/generation/estimate", request)
        value = response.get("cost") if isinstance(response, dict) else None
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ToolError("API returned an invalid estimate.")
        return value

    def status(self, task_id, timeout=None):
        if not isinstance(task_id, str) or not task_id or len(task_id) > 128 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in task_id):
            raise ToolError("Invalid task id.")
        result = self.request("/task/status/" + task_id, timeout=timeout)
        task = result.get("data") if isinstance(result, dict) else None
        if not isinstance(task, dict) or task.get("status") not in TERMINAL | {"not_started", "processing"}:
            raise ToolError("API returned an invalid task status.")
        return {k: task.get(k) for k in ("taskId", "status", "files", "output", "errorMessage")}


def save_state(path, state):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with open(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
            file.write(dump(state) + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
        if os.name == "posix":
            # fsync(file) does not persist the rename's directory entry.
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def state_lock(path):
    lock = path.with_name(path.name + ".lock")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ToolError("State is locked. Check the other process before removing a stale .lock file.") from None
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def run_generation(client, request, ceiling, path, confirm_paid=False, timeout=0, interval=3):
    if not confirm_paid:
        raise ToolError("Creation requires --confirm-paid and the user's authorization for this request and ceiling.")
    if not isinstance(request, dict) or not isinstance(request.get("model"), str) or not isinstance(request.get("input"), dict):
        raise ToolError("Request must contain model and input. Use catalog inputSchema for model parameters.")
    if not path.parent.is_dir():
        raise ToolError("Create the state directory before running a generation.")
    # Server idempotency is scoped to a user. Refuse replay after a credential
    # change, including rotation, rather than risk submitting under another user.
    key_digest = hashlib.sha256(client.key.encode()).hexdigest()
    fingerprint = hashlib.sha256(dump({"origin": client.origin, "request": request,
        "keyDigest": key_digest}).encode()).hexdigest()
    with state_lock(path):
        if path.exists():
            try:
                state = json.loads(path.read_text())
            except (ValueError, OSError):
                raise ToolError("State is unreadable; preserve it and investigate before creating another request.") from None
            if isinstance(state, dict) and state.get("version") == 1:
                raise ToolError("State format 1 predates credential binding. Preserve it and recover any existing task with the original account; do not create a replacement.")
            if not isinstance(state, dict) or (state.get("version"), state.get("requestHash")) != (2, fingerprint):
                raise ToolError("State belongs to another request, origin or credential. Preserve it.")
            if not isinstance(state.get("idempotencyKey"), str) or not state["idempotencyKey"]:
                raise ToolError("State has no idempotency key; do not create a replacement task.")
            if state.get("maxCostMicroUsd") != ceiling:
                if state.get("taskId") or state.get("submissionAttempted"):
                    raise ToolError("State was submitted with another ceiling. Preserve it.")
                state["maxCostMicroUsd"] = ceiling
                save_state(path, state)
        else:
            state = {"version": 2, "origin": client.origin, "requestHash": fingerprint,
                "maxCostMicroUsd": ceiling, "idempotencyKey": "openclaw-" + str(uuid.uuid4())}
            # Persist before POST. A timeout or interruption must not lose the key.
            save_state(path, state)
        if not state.get("taskId"):
            if not state.get("submissionAttempted"):
                estimate = client.estimate(request)
                if estimate > ceiling:
                    raise ToolError("Estimate exceeds the authorized ceiling; no generation was submitted.")
                state["estimateMicroUsd"] = estimate
                state["submissionAttempted"] = True
            # Re-establish durability on replays too: a previous save may have
            # renamed the state but failed to sync its directory before POST.
            save_state(path, state)
            # On an uncertain POST, replay immediately. A fresh quote may have
            # changed or become unavailable while the first task is running.
            # The server still enforces the original ceiling if it must create.
            created = client.request("/generation/create-idempotent", request, {
                "Idempotency-Key": state["idempotencyKey"], "X-Max-Cost-Micro-Usd": str(ceiling)})
            data = created.get("data") if isinstance(created, dict) else None
            task_id = data.get("taskId") if isinstance(data, dict) else None
            if not isinstance(task_id, str) or not task_id:
                raise ToolError("Creation returned no taskId. Resume the same state; do not create a new key.")
            state["taskId"] = task_id
            save_state(path, state)
        if timeout <= 0:
            return {"taskId": state["taskId"], "status": "submitted", "state": str(path),
                "estimateMicroUsd": state.get("estimateMicroUsd")}
        result = wait_task(client, state["taskId"], timeout, interval)
        state["lastStatus"] = result["status"]
        save_state(path, state)
        return result


def wait_task(client, task_id, timeout, interval=3):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {"taskId": task_id, "status": "waiting", "resume": "Poll this task; do not create another generation."}
        task = client.status(task_id, timeout=min(client.timeout, remaining))
        if task["status"] in TERMINAL:
            return task
        time.sleep(min(interval, max(0, deadline - time.monotonic())))


def provider_config(site, model, context_window=32000, max_tokens=4096):
    if not model or "/" in model or any(c.isspace() for c in model):
        raise ToolError("Use the exact model id from doctor, without a provider prefix.")
    if max_tokens < 1 or context_window <= max_tokens:
        raise ToolError("The context window must exceed max tokens.")
    # These are conservative client budgets, not advertised model capabilities.
    return {"models": {"mode": "merge", "providers": {site: {
        "baseUrl": SITES[site] + "/api/v1", "apiKey": "${API_STOCK_KEY}",
        "api": "openai-completions", "models": [{"id": model, "name": model,
            "input": ["text"], "reasoning": False, "contextWindow": context_window,
            "maxTokens": max_tokens}]}}}, "agents": {"defaults": {"model": {"primary": site + "/" + model}}}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", choices=SITES, default="api-stock")
    sub = parser.add_subparsers(dest="command", required=True)
    config = sub.add_parser("config", help="Print an OpenClaw config fragment; no credentials or network calls")
    config.add_argument("--model", required=True)
    config.add_argument("--context-window", type=int, default=32000)
    config.add_argument("--max-tokens", type=int, default=4096)
    sub.add_parser("doctor", help="Read-only credential, catalog and model discovery check")
    catalog = sub.add_parser("catalog", help="Read media parameters and current prices")
    catalog.add_argument("--model")
    estimate = sub.add_parser("estimate", help="Quote a request without creating a paid task")
    estimate.add_argument("--request", type=Path, required=True)
    run = sub.add_parser("run", help="Create once, or resume the same paid generation")
    run.add_argument("--request", type=Path, required=True)
    run.add_argument("--state", type=Path, required=True)
    run.add_argument("--max-cost-usd", required=True)
    run.add_argument("--confirm-paid", action="store_true")
    run.add_argument("--timeout", type=int, default=0)
    for name in ("status", "wait"):
        command = sub.add_parser(name)
        command.add_argument("task_id")
        if name == "wait":
            command.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)
    if args.command == "config":
        return provider_config(args.site, args.model, args.context_window, args.max_tokens)
    client = Client(SITES[args.site], os.environ.get("API_STOCK_KEY", ""))
    if args.command == "doctor":
        response = client.request("/models")
        models = response.get("data") if isinstance(response, dict) else None
        if not isinstance(models, list):
            raise ToolError("Model discovery failed.")
        return {"ok": True, "site": args.site, "baseUrl": client.origin + "/api/v1",
            "adapter": "openai-completions", "models": [{"id": m["id"], "pricing": m.get("pricing")} for m in models if isinstance(m, dict) and isinstance(m.get("id"), str)],
            "scope": "Read-only discovery; does not prove tool calling or streaming compatibility."}
    if args.command == "catalog":
        catalog = client.request("/catalog")
        if args.model:
            models = catalog if isinstance(catalog, list) else []
            match = next((m for m in models if m.get("id") == args.model), None)
            if match is None:
                raise ToolError("Model not found in the current media catalog.")
            return match
        return catalog
    if args.command in ("estimate", "run"):
        try:
            request = json.loads(args.request.read_text())
        except (ValueError, OSError):
            raise ToolError("Read the generation request from a valid UTF-8 JSON file.") from None
        if args.command == "estimate":
            amount = client.estimate(request)
            return {"costMicroUsd": amount, "costUsd": str(Decimal(amount) / 1_000_000), "createsTask": False}
        if not 0 <= args.timeout <= 600:
            raise ToolError("Use a timeout between 0 and 600 seconds.")
        return run_generation(client, request, micro_usd(args.max_cost_usd), args.state, args.confirm_paid, args.timeout)
    if args.command == "status":
        return client.status(args.task_id)
    if not 1 <= args.timeout <= 600:
        raise ToolError("Use a timeout between 1 and 600 seconds.")
    return wait_task(client, args.task_id, args.timeout)


if __name__ == "__main__":
    try:
        result = main()
        print(dump(result))
        if isinstance(result, dict) and result.get("status") in {"failed", "expired"}:
            sys.exit(2)
    except (ToolError, OSError) as exc:
        # Only our messages are emitted; transport errors can contain credentials.
        print(dump({"error": str(exc) if isinstance(exc, ToolError) else "Local file operation failed."}), file=sys.stderr)
        sys.exit(1)
