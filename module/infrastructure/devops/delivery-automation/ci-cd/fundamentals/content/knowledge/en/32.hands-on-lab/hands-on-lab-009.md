# Rehearsing a Rollback and Verifying Service Recovery

A technically complete deployment does not guarantee a properly functioning service. A container may be running and the pipeline may report green, yet a critical business flow still returns errors or latency has breached acceptable thresholds. Therefore, safe release capability must include the ability to roll back to a known-good version and verify with evidence that the service has truly recovered.

In this hands-on lab, you will deploy a sample service, record the running version, introduce a simulated faulty release, identify the signals to halt the release, revert to the previous artifact, and run multi-layered post-rollback verification. The entire lab runs locally using Docker Compose; no Kubernetes cluster or cloud account is required.

## Lab Objectives

After completing this lab, you will be able to:

- Distinguish between a successful deployment status and a genuinely recovered service state.
- Record the running artifact identifier so you can revert to the exact released build.
- Use health checks, smoke tests, and business signals to detect a faulty release.
- Perform a rollback using an existing stored artifact rather than rebuilding from current source code.
- Verify version, readiness, business flows, and post-rollback stability.
- Record timelines, root causes, actions, and evidence to improve the CI/CD process.

## Context and Completion Criteria

You are responsible for `orders-api`, a small HTTP service. Version `1.0.0` is operating normally. The team prepares to release `1.1.0`, but this version contains a defect causing the readiness endpoint to return HTTP 503 and the order-creation operation to return HTTP 500. The process continues running, so the liveness check still succeeds. This is a common real-world scenario: checking process liveness alone is not enough to prove business functionality is healthy.

| Phase | What Must Be Proven |
|---|---|
| Before release | Artifact `1.0.0` exists, its exact image ID is known, and all business checks pass |
| After faulty release | Readiness or business flow failure is detected even while the container reports healthy |
| During rollback | Service is restarted from the saved `1.0.0` artifact without rebuilding |
| After rollback | Image ID matches, readiness and business operations succeed consecutively, and service stays stable over an observation window |

A rollback command returning exit code 0 only tells you the tool finished its own operation. Mark recovery complete only when post-deployment checks confirm the service is running the expected version, serving business requests, and no longer breaching operational thresholds.

## Preparation

You need:

- Docker Engine running and Docker Compose v2 (`docker compose version`).
- PowerShell, Bash, or an equivalent shell terminal.
- `curl` for sending HTTP requests. On Windows, use `curl.exe` to avoid PowerShell's `curl` alias.
- Permission to create directories and run containers locally.

Verify tools:

```bash
docker --version
docker compose version
curl --version
```

In PowerShell, use `curl.exe --version` on the last line.

Create the workspace for the lab:

```text
rollback-drill/
├── compose.yaml
└── app/
    ├── Dockerfile
    └── server.js
```

Create the `rollback-drill` directory, then create `app` inside it. The code snippets below provide the exact contents of each file. If using PowerShell, create the directory with `New-Item -ItemType Directory -Force app`; in Bash, use `mkdir -p app`.

## 1. Creating the Simulated Service

Create `app/server.js`:

```javascript
const http = require("node:http");

const version = process.env.APP_VERSION || "unknown";
const failMode = process.env.FAIL_MODE === "true";

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, {
    "content-type": "application/json; charset=utf-8",
  });
  response.end(JSON.stringify(payload));
}

const server = http.createServer((request, response) => {
  const pathname = new URL(request.url || "/", "http://localhost").pathname;

  if (pathname === "/health/live") {
    return sendJson(response, 200, { live: true, version });
  }

  if (pathname === "/health/ready") {
    return sendJson(response, failMode ? 503 : 200, {
      ready: !failMode,
      version,
    });
  }

  if (pathname === "/orders") {
    return sendJson(response, failMode ? 500 : 200, {
      service: "orders-api",
      version,
      result: failMode ? "simulated_failure" : "accepted",
    });
  }

  if (pathname === "/") {
    return sendJson(response, 200, { service: "orders-api", version });
  }

  return sendJson(response, 404, { error: "not_found", version });
});

server.listen(8080, "0.0.0.0", () => {
  console.log(`orders-api ${version} listening on port 8080; failMode=${failMode}`);
});
```

The application has three endpoint types serving distinct purposes:

- `/health/live` indicates the HTTP process is alive. This endpoint always returns 200 while the server accepts requests.
- `/health/ready` indicates whether the release is ready to receive traffic. In failure mode, it returns 503.
- `/orders` simulates a business operation. In failure mode, it returns 500.

The `/` endpoint returns the service name and version so you can verify which artifact is running. `FAIL_MODE` is strictly a simulation toggle for this lab; in real systems, failures arise from code, configuration, dependencies, migrations, or data.

Create `app/Dockerfile`:

```dockerfile
FROM node:22-alpine

WORKDIR /app

ARG APP_VERSION=1.0.0
ARG FAIL_MODE=false

ENV APP_VERSION=${APP_VERSION}
ENV FAIL_MODE=${FAIL_MODE}

COPY server.js ./server.js

EXPOSE 8080

CMD ["node", "server.js"]
```

Both build arguments are baked into the image. As a result, `1.0.0` and `1.1.0` are two separately tagged artifacts; the faulty release is not produced by toggling an environment variable on the same running container.

Create `compose.yaml` at the root of `rollback-drill`:

```yaml
services:
  api:
    image: rollback-drill/orders-api:${APP_VERSION:-1.0.0}
    build:
      context: ./app
      args:
        APP_VERSION: ${APP_VERSION:-1.0.0}
        FAIL_MODE: ${FAIL_MODE:-false}
    ports:
      - "127.0.0.1:8080:8080"
    healthcheck:
      test:
        - CMD
        - node
        - -e
        - "require('node:http').get('http://127.0.0.1:8080/health/live', (response) => process.exit(response.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"
      interval: 5s
      timeout: 2s
      retries: 3
      start_period: 3s
    restart: unless-stopped
```

Port 8080 binds only to the loopback interface of the machine running the lab. Compose's healthcheck intentionally checks liveness only; it does not check readiness or business flows. This lets you observe a container marked `healthy` while the release still fails smoke tests. In real environments, design liveness and readiness for their proper roles, and enforce business checks in post-deployment quality gates.

## 2. Releasing a Good Version and Saving Baseline Evidence

Open a terminal in the directory containing `compose.yaml`. Set the version and operating mode for the initial release.

PowerShell:

```powershell
$env:APP_VERSION = "1.0.0"
$env:FAIL_MODE = "false"
docker compose config
docker compose up -d --build --wait --wait-timeout 60
```

Bash:

```bash
export APP_VERSION=1.0.0
export FAIL_MODE=false
docker compose config
docker compose up -d --build --wait --wait-timeout 60
```

`docker compose config` validates the configuration after variable interpolation. `up` builds the `rollback-drill/orders-api:1.0.0` image, starts the container, and waits for the liveness healthcheck to pass. If your Docker Compose version does not support `--wait`, run `docker compose up -d --build`, then monitor `docker compose ps` until the container reaches `healthy`.

Verify status and endpoints:

```bash
docker compose ps
curl -fsS http://127.0.0.1:8080/
curl -fsS http://127.0.0.1:8080/health/live
curl -fsS http://127.0.0.1:8080/health/ready
curl -fsS http://127.0.0.1:8080/orders
```

On Windows, replace `curl` with `curl.exe`. All four requests must return HTTP 200. The `/` response body must show `version` as `1.0.0`; `/orders` must report `result` as `accepted`.

Record the image ID of the good artifact. This command works in both PowerShell and Bash:

```bash
docker image inspect rollback-drill/orders-api:1.0.0 --format '{{.Id}}'
```

Save this value in your lab log along with the release timestamp. Tags help humans reference versions; the image ID or digest is the exact identifier of the built artifact. In a real registry, store the immutable digest alongside the commit, pipeline run, and deployment environment.

Fill in the baseline record:

| Recorded Field | Value to Save |
|---|---|
| Service | `orders-api` |
| Environment | local lab |
| Current version | `1.0.0` |
| Image tag | `rollback-drill/orders-api:1.0.0` |
| Image ID | Output from `docker image inspect` |
| Liveness | HTTP 200 |
| Readiness | HTTP 200 |
| Business `/orders` | HTTP 200, `accepted` |

This serves as the baseline for post-rollback comparison. Without saving the artifact and evidence of the good version, you lack a solid basis to restore the exact pre-release state.

## 3. Releasing a Controlled Faulty Version

Simulate the faulty `1.1.0` release. In this step, `FAIL_MODE=true` is baked into the new image.

PowerShell:

```powershell
$env:APP_VERSION = "1.1.0"
$env:FAIL_MODE = "true"
docker compose config
docker compose up -d --build --wait --wait-timeout 60
```

Bash:

```bash
export APP_VERSION=1.1.0
export FAIL_MODE=true
docker compose config
docker compose up -d --build --wait --wait-timeout 60
```

Compose builds `rollback-drill/orders-api:1.1.0` and replaces the container with the new version. `up --wait` can still complete successfully because the healthcheck calls only `/health/live`, and the process stays alive. This demonstrates that deployment platform status alone is insufficient to conclude a release is healthy.

Check each endpoint:

```bash
docker compose ps
curl -i http://127.0.0.1:8080/health/live
curl -i http://127.0.0.1:8080/health/ready
curl -i http://127.0.0.1:8080/orders
```

Expected results:

| Endpoint | Expected HTTP | Interpretation |
|---|---:|---|
| `/health/live` | 200 | Process is still alive |
| `/health/ready` | 503 | Service is not ready to accept traffic |
| `/orders` | 500 | Critical business flow is failing |

Use `curl -i` here so you can see the status codes. Omit `-f`, because `curl -f` exits non-zero on HTTP 4xx or 5xx; we want to inspect the simulated error payloads directly.

Save the faulty build's image ID as proof that the two artifacts are distinct:

```bash
docker image inspect rollback-drill/orders-api:1.1.0 --format '{{.Id}}'
```

## 4. Making the Rollback Decision

In a real release workflow, rollback criteria must be agreed upon before deployment. Do not wait until an incident occurs to debate which failures are severe enough. A minimal set of criteria can include:

| Signal | Example Stop-Release Condition |
|---|---|
| Critical check fails | Smoke test for login, payment, or order creation fails |
| Error rate spikes | HTTP 5xx rate breaches defined threshold within an observation window |
| Latency rises | p95 or p99 exceeds SLO continuously |
| Readiness fails | Instances fail readiness or are repeatedly removed from traffic |
| Data impact | Incorrect writes, data loss, or business invariant violations detected |

For this lab, either readiness returning 503 or `/orders` returning 500 is sufficient to trigger a rollback. Do not wait for both conditions simultaneously. Once you confirm the error belongs to the new release, record the detection timestamp and trigger reason. If the system supports traffic management, drain or stop traffic to the faulty version while recovering.

Distinguish three decisions:

1. **Application rollback:** shift traffic or workloads back to a known-good application artifact.
2. **Data recovery:** repair data that was written incorrectly. Rolling back a binary does not automatically reverse transactions or migrations.
3. **Forward fix:** release a new patched version when rolling back is unsafe or incompatible with the current data state.

This lab simulates an application rollback only. In production, determine backward compatibility of schemas, configuration, messages, and data ahead of time before choosing to roll back.

## 5. Reverting to the Saved Good Artifact

Switch the Compose configuration back to the `1.0.0` tag. Crucially, use `--no-build` so Compose reuses the older image already built and stored in step 2. Never rebuild source code at rollback time and re-apply an old tag, as that can produce an artifact different from the previously verified build.

PowerShell:

```powershell
$env:APP_VERSION = "1.0.0"
$env:FAIL_MODE = "false"
docker compose config
docker compose up -d --no-build --wait --wait-timeout 60
```

Bash:

```bash
export APP_VERSION=1.0.0
export FAIL_MODE=false
docker compose config
docker compose up -d --no-build --wait --wait-timeout 60
```

If the command reports the image is missing, stop and verify the tag and image ID recorded in step 2. Do not automatically build a new image and treat that as a successful rollback. In registry-backed systems, previous artifacts must be retained and pullable by saved digest; image cleanup policies must ensure versions still needed for rollback are not deleted.

Verify container and artifact state:

```bash
docker compose ps
docker compose images
docker image inspect rollback-drill/orders-api:1.0.0 --format '{{.Id}}'
```

The final image ID must match the image ID recorded before releasing `1.1.0`. If the tag points to a different ID, you have not proven you reverted to the exact artifact.

## 6. Verifying True Service Recovery

Do not end the drill simply because the container turns healthy or the rollback command returns success. Verify across multiple layers, from infrastructure to service behavior.

### 6.1. Verifying Process and Version

```bash
docker compose ps
curl -fsS http://127.0.0.1:8080/
curl -fsS http://127.0.0.1:8080/health/live
```

The container must be running and healthy. The `/` endpoint must return `version` as `1.0.0`. If the container reports healthy while `/` still returns `1.1.0`, the rollback configuration has not moved the workload back to the proper version.

### 6.2. Verifying Readiness and Business Operations

```bash
curl -fsS http://127.0.0.1:8080/health/ready
curl -fsS http://127.0.0.1:8080/orders
```

Both requests must succeed. Readiness must return `ready: true`; `/orders` must return `result: accepted`. This serves as evidence that the service is ready and the simulated business path is operational again.

In PowerShell, you can additionally assert the version with:

```powershell
$body = curl.exe -fsS http://127.0.0.1:8080/
if ($LASTEXITCODE -ne 0 -or $body -notmatch '"version":"1\.0\.0"') {
    throw "Rollback did not restore exact version 1.0.0"
}
```

In Bash:

```bash
body="$(curl -fsS http://127.0.0.1:8080/)"
printf '%s\n' "$body"
printf '%s' "$body" | grep -q '"version":"1.0.0"' || {
  echo "Rollback did not restore exact version 1.0.0" >&2
  exit 1
}
```

### 6.3. Consecutive Checks Over a Stability Window

A single successful request could be transient. Repeat critical checks to uncover intermittent failures or incomplete startup.

PowerShell:

```powershell
1..10 | ForEach-Object {
    curl.exe -fsS http://127.0.0.1:8080/health/ready | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Readiness failed on attempt $_" }

    curl.exe -fsS http://127.0.0.1:8080/orders | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Business check failed on attempt $_" }

    Start-Sleep -Seconds 2
}
```

Bash:

```bash
for attempt in $(seq 1 10); do
  curl -fsS http://127.0.0.1:8080/health/ready >/dev/null || exit 1
  curl -fsS http://127.0.0.1:8080/orders >/dev/null || exit 1
  sleep 2
done
```

Ten checks represent the minimum for this lab, not a standard production SLO window. For real services, observe long enough to cover traffic rhythms, background jobs, and critical dependencies. Compare error rates, latency, saturation, queue lag, and related alerts in your monitoring system.

### 6.4. Inspecting Logs and Anomalies

```bash
docker compose logs --since 5m --tail 100 api
```

Look for startup errors, connection failures, restart loops, or messages indicating the process is still handling requests under faulty configuration. In production, correlate logs with metrics and traces by release ID or correlation ID to verify traffic has genuinely shifted back to the good version.

Confirm recovery only when all of the following verification layers pass:

| Verification Layer | Required Evidence |
|---|---|
| Artifact | Image ID or digest matches the known-good artifact |
| Workload | Instances running, no restart loops, health checks passing |
| Readiness | Instances ready to receive traffic |
| Business | Smoke tests on critical paths succeed |
| Stability | Consecutive checks pass; error rate and latency return within thresholds |
| Data and dependencies | No abnormal backlog, write errors, or degraded dependencies |

If any layer has not passed, keep the status as **recovering** or **rollback unverified**. Continue investigating, switch to a forward fix, or follow the appropriate recovery runbook; never close an incident simply because the deployment tool reported success.

## 7. Recording the Drill and Measuring Recovery Time

A drill is valuable when the team can reconstruct what happened and identify which steps need improvement. Record at least the following milestones:

| Milestone | Description |
|---|---|
| T0 | Start deploying `1.1.0` |
| T1 | First check detects readiness or business failure |
| T2 | Decision made to halt release and trigger rollback |
| T3 | Begin shifting workload back to `1.0.0` |
| T4 | Artifact `1.0.0` running and readiness passing |
| T5 | Business smoke tests and stability window both pass |

The interval from incident detection to initiating rollback is the detection-and-decision time. The interval from triggering rollback to reaching T5 reflects actual drill recovery time. Agree on measurement conventions before comparing across drills; do not measure only how long `docker compose up` takes to exit.

Log template:

| Field | Value Recorded During Drill |
|---|---|
| Faulty release | `1.1.0` and its image ID |
| Rollback artifact | `1.0.0` and its pre-release image ID |
| Trigger | Readiness 503 and/or `/orders` 500 |
| Detection time (T1) | Timestamp with timezone |
| Rollback trigger time (T2) | Timestamp with timezone |
| Recovery verified time (T5) | Timestamp with timezone |
| Smoke test results | Passed attempts / total attempts |
| Post-rollback status | Error rate, latency, alerts, and backlog if any |
| Coordinator | Role responsible for decision and sign-off |
| Follow-up improvements | Concrete actions, owner, and due date |

For example, if T1 is 10:02, T2 is 10:04, and T5 is 10:09 on the same day, the team took 2 minutes to decide and 5 minutes from triggering rollback to verifying recovery. This is a single-drill measurement; multiple measurements under a consistent convention are needed before setting operational targets.

## 8. Integrating Rollback into the CI/CD Process

A pipeline can model a safe release flow as follows:

```text
Verified commit
        |
        v
Build once -> Tag version + commit -> Store immutable artifact
        |
        v
Record current artifact as rollback target
        |
        v
Deploy candidate
        |
        v
Wait for workload readiness
        |
        v
Smoke tests + post-deploy metric checks
        |
        +---- pass ----> Observe stability ----> Complete release
        |
        +---- fail ----> Stop/drain traffic -> Deploy previous artifact
                                      |
                                      v
                          Re-run smoke tests + observe
                                      |
                            +---------+---------+
                            |                   |
                           pass               failed
                            |                   |
                       Confirm recovery    Escalate to incident runbook
```

In a real pipeline, save `PREVIOUS_IMAGE_DIGEST` before updating the workload. The rollback step must use that exact digest, possess registry access, and be protected against artifact cleanup jobs. Never rely on the `latest` tag because it may already point to a newer build. For canary or blue-green releases, you can shift traffic back to the old instance group before terminating or replacing it.

A post-deployment gate should proceed sequentially:

1. Wait for workload readiness via readiness probes.
2. Invoke smoke tests for critical business paths.
3. Read metrics within the defined observation window.
4. If a rollback condition triggers, record the trigger and revert to the saved artifact.
5. Re-run all recovery checks on the rolled-back version.
6. Close the pipeline only once recovery is confirmed; if rollback or verification fails, preserve failed status and page the on-call operator.

Rollback step conditions must reflect actual state: roll back only when the candidate has already been deployed or traffic has shifted to it. The pipeline should also distinguish smoke test failures, deployment infrastructure failures, and rollback execution failures so operators pick the right runbook.

## 9. Scenarios Rollback Cannot Solve on Its Own

Rollback is a vital recovery tool, yet it does not undo every effect of a release.

| Scenario | Risk | How to Prepare |
|---|---|---|
| Backward-incompatible database migration | Old code cannot read the new schema or transformed data | Use expand-contract pattern; isolate destructive migrations into separate phases and drop columns only after old versions are gone |
| Changed configuration or secrets | Old binary running with new configuration may still fail | Version configuration, retain known-good configs, and test compatibility |
| Transactions with side effects | Written orders, payments, or messages do not vanish when reverting code | Design idempotency, reconciliation, and compensating transactions; never assume app rollback equals data rollback |
| Old artifact deleted | Cannot start the exact previous version | Enforce retention policy by release count and age; verify pullability before releasing |
| External dependency failing | Previous application version also fails | Check dependencies, circuit breakers, fallbacks, and independent runbooks |
| Rollback in wrong environment | May disrupt another service or push old code to the wrong target | Verify account, cluster, namespace, service, and release ID before acting; use guards and proper permissions |
| Rollback operation itself fails | System remains in faulty or indeterminate state | Prepare manual runbooks, break-glass access, clear owners, and traffic isolation plans |

For destructive data changes, evaluate beforehand whether rollback is safe or a forward fix is required. If data integrity is in doubt, prioritize preserving evidence, halt further writes, and invoke data recovery procedures; never run an arbitrary reverse command.

## 10. Common Troubleshooting in This Lab

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Docker Compose cannot find Docker daemon | Docker Engine is not running | Start Docker Desktop or the daemon and test `docker info` |
| Port 8080 already in use | Another application occupies the port | Stop the conflicting process or update both port mapping and test URLs consistently |
| `up --wait` succeeds but smoke tests fail | Healthcheck checks liveness only | Inspect readiness and business endpoints; this is the intentional lab failure scenario |
| `up --no-build` reports missing image | Tag `1.0.0` was not built or was deleted | Check `docker image ls` and baseline image ID; never re-tag a fresh build as the old version |
| Still seeing version `1.1.0` after rollback | `APP_VERSION` not reset in the active terminal or container not replaced | Run `docker compose config`, inspect `docker compose ps`, and check `/` response |
| Readiness passes while business calls fail | Readiness probe is too shallow or business dependency not ready | Add smoke tests for critical paths and check dependent services |
| `curl` exits non-zero | HTTP 4xx/5xx or connection failure | Use `curl -i` to inspect status and logs; use `-f` only for checks expecting HTTP 2xx |

## 11. Environment Cleanup

After saving your logs and drill results, stop the containers:

```bash
docker compose down
```

If you want to reclaim the lab images once evidence is no longer needed, remove the two created tags:

```bash
docker image rm rollback-drill/orders-api:1.0.0 rollback-drill/orders-api:1.1.0
```

Do not run image deletion commands before recording the image IDs and results. In real systems, clean up artifacts only per approved retention policies; always retain enough artifacts to meet recovery needs.

## 12. Completion Checklist

- [ ] Deployed `1.0.0` and confirmed liveness, readiness, and `/orders` all pass.
- [ ] Recorded the image ID of `1.0.0` before releasing the new version.
- [ ] Deployed `1.1.0` and observed liveness 200 alongside readiness 503 or business 500.
- [ ] Recorded the reason and timestamp for triggering rollback.
- [ ] Reverted to `1.0.0` using `--no-build`.
- [ ] Post-rollback image ID matches the initially recorded image ID.
- [ ] Readiness and business flow succeeded across consecutive checks.
- [ ] Inspected logs and related operational signals.
- [ ] Documented recovery time, evidence, and follow-up improvements.
- [ ] Cleaned up the environment after completing documentation.

## Self-Assessment Questions

1. Why can `docker compose up --wait` succeed while the release still fails requirements?
2. How do an image tag and an image ID differ? Why must rollbacks use the saved artifact instead of rebuilding source code?
3. Which checks prove a process is alive, a service is ready, and a business flow works? How do they complement one another?
4. If smoke tests pass while error rate or p95 still exceeds SLO, what decision would you make and what else would you inspect?
5. Why can an application rollback not automatically recover data altered by destructive migrations or emitted side effects?
6. What information would you store in a pipeline so rollbacks are automated, auditable, and verifiable?

## Expected Outcome

You complete this lab when you have demonstrated the full cycle: deploy a good version and save its artifact identifier; release a faulty version; detect the failure via readiness or business checks; revert to the exact saved artifact; and confirm service version, health, business functionality, and stability. Your drill log must show detection time, rollback trigger time, recovery verification time, and concrete follow-up improvement actions.
