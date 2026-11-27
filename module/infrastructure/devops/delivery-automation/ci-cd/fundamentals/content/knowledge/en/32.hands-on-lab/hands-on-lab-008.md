# Hands-on: Simulating Build Failures, Lost Connectivity, and Concurrent Deployments

In the **DEVOPS_CI_CD_FUNDAMENTALS** module, this hands-on lab helps you test how a pipeline reacts when three common failures occur: a build or test failure, interrupted connectivity to a service, and two versions attempting to deploy to the same environment simultaneously. The goal is to make failures easy to spot, contain the blast radius of failed runs, and protect the live state serving users.

You will intentionally trigger each failure, observe the outcome, restore the system, and apply the corresponding control mechanism. The pipeline examples use GitHub Actions and Gradle; local simulations use Bash, Node.js, and `curl`. Run the Bash commands on Linux, macOS, or WSL. If your project uses Maven or another CI/CD tool, substitute the equivalent build commands and pipeline syntax.

## Expected Outcomes

After completing this lab, you will be able to:

- Detect build/test failures via exit codes and logs, while preventing the pipeline from creating artifacts or deploying when checks fail.
- Simulate timeouts and unreachable services; configure bounded timeouts and finite retries for safe operations.
- Explain why two deployments writing concurrently to one environment can overwrite a newer version with an older one.
- Serialize deployments, deploy the exact tested artifact, and verify health after release.

## Prerequisites

You need a Java project with a Gradle Wrapper, JDK 21, Bash, Node.js, and `curl`. The file-locking exercise uses `flock`, typically available on Linux. GitHub Actions runs on `ubuntu-latest` in the examples below.

Verify tools:

```bash
java -version
./gradlew --version
node --version
curl --version
flock --version
```

If your project does not emit a JAR in `build/libs/`, adjust the artifact path in the workflow to match your project's packaging configuration. Never put real credentials or tokens into simulation scripts.

## Scenario 1: Build or Test Failure

### Introducing an Intentional Failure

Pick an existing unit test and temporarily corrupt the expected value. For example, if `Calculator.add(2, 2)` returns `4`, change the assertion to:

```java
@Test
void addsTwoNumbers() {
    assertEquals(5, Calculator.add(2, 2)); // Intentionally wrong to produce a test failure
}
```

Run build and tests:

```bash
./gradlew --no-daemon clean test
```

The expected result is that Gradle returns a non-zero exit code, reports a test failure, and identifies the failing test and assertion. In the logs, look for `FAILED`, the test name, and expected/actual values. This is the machine-readable signal used to decide whether the pipeline may proceed.

If you want to inspect the exit code explicitly in Bash:

```bash
./gradlew --no-daemon clean test
build_status=$?
printf 'build exit code: %s\n' "$build_status"
```

A non-zero value indicates the build/test step failed. In scripts with `set -e`, execution stops immediately at the failing step; that is usually the desired pipeline behavior. Never add `|| true` or `continue-on-error` just to make the pipeline display green, because doing so suppresses the failure signal.

### Observing Pipeline Impact

A pipeline should place build and tests before packaging, artifact upload, and deployment. When `clean build` fails, dependent deploy jobs must be skipped. Artifacts from a build that failed checks must never be published.

Restore the assertion to its correct value, then run again:

```bash
./gradlew --no-daemon clean build
```

Confirm the command returns `0`, all tests pass, and the artifact is created per project configuration. Keep the logs from the failed run to compare against the passing run.

**Key takeaway:** a failed build is a pipeline state, not a warning for operators to remember manually. Exit codes, job dependencies, and release conditions must automatically halt the pipeline before deployment.

## Scenario 2: Lost Connectivity or Unresponsive Service

Connection failures can occur when a runner cannot reach the host, DNS or a proxy malfunctions, the target service is still starting, or a connection succeeds but the server never responds. Two common manifestations are connection refused and request timeout. These should be distinguished from HTTP error responses such as `500` or `503`.

### Simulating a Hanging Service

Open a first terminal and start an HTTP server that never sends a response. The server accepts connections but leaves requests hanging indefinitely:

```bash
node -e 'require("http").createServer((_req, _res) => {}).listen(8080, "127.0.0.1")'
```

Open a second terminal and set time limits on the request:

```bash
curl --verbose --connect-timeout 2 --max-time 3 \
  http://127.0.0.1:8080/health
printf 'curl exit code: %s\n' "$?"
```

The request will time out; `curl` typically returns exit code `28` for a timeout. Stop the server with `Ctrl+C`, then run the `curl` command again. This time the connection is refused and `curl` typically returns exit code `7`. Thus, a timeout and an inability to establish a connection are two distinct signals, even though both cause the check step to fail.

### Restoring the Service and Re-Checking

Start a server returning HTTP 200:

```bash
node -e 'require("http").createServer((_req, res) => { res.writeHead(200, {"content-type":"text/plain"}); res.end("ok"); }).listen(8080, "127.0.0.1")'
```

In the second terminal, call the endpoint with bounded timeouts:

```bash
curl --fail --silent --show-error \
  --connect-timeout 2 --max-time 5 \
  http://127.0.0.1:8080/health
```

The expected result is `ok` and exit code `0`. Stop the server after finishing the simulation.

### Designing Bounded Retries

For an HTTP GET health check, you can retry certain transient errors. The example below limits connection time, per-request duration, and total retry time:

```bash
curl --fail --silent --show-error \
  --connect-timeout 2 --max-time 5 \
  --retry 2 --retry-delay 1 --retry-max-time 15 \
  "$HEALTH_URL/health"
```

`--retry 2` allows up to two retries after the initial attempt. When the service remains unavailable, the final command must return a failing exit code so the pipeline fails. Retries only mitigate transient glitches; they never turn a broken service into a healthy one.

Key principles when handling lost connectivity:

- Set timeouts for both connection establishment and the request itself. Never let a runner wait indefinitely.
- Use finite retries with pauses; consider exponential backoff and jitter when multiple runners may retry simultaneously.
- Prefer retrying read operations or operations explicitly designed to be idempotent. For deploy commands or write requests, a timeout does not tell you whether the server already processed the request. Check release state before retrying, or use an idempotency key.
- Log the target URL safely, along with timeouts, attempt counts, and error codes. Never print tokens, passwords, or authorization headers.
- Once retries are exhausted, halt the pipeline and keep the failed status. Never skip health checks to proceed with a release.

**Key takeaway:** retry is a conditional recovery mechanism. Timeouts, attempt limits, and idempotency must be designed together; infinite retries or blindly retrying a deployment operation can make an incident worse.

## Scenario 3: Two Concurrent Deployments

Suppose `release-A` starts deploying first but takes longer. Meanwhile, `release-B` deploys and finishes faster. If both write to a shared location, `release-A` can finish later and overwrite `release-B`. Users then see the older version even though the newer version had already been activated.

### Reproducing the Overwrite Race

In a temporary directory, create `deploy-race.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

release="${1:?Must provide release version}"
delay="${2:-0}"

printf 'Starting deployment of %s\n' "$release"
sleep "$delay"
tmp_file="current-release.$$"
printf '%s\n' "$release" > "$tmp_file"
mv "$tmp_file" current-release.txt
printf 'Activated %s\n' "$release"
```

Run two processes nearly simultaneously. Version A takes four seconds; version B starts one second later and finishes immediately:

```bash
bash deploy-race.sh release-A 4 &
pid_a=$!
sleep 1
bash deploy-race.sh release-B 0 &
pid_b=$!
wait "$pid_a" "$pid_b"
cat current-release.txt
```

The final result is usually `release-A`: B wrote first, but A finished later and overwrote it. This is a race condition. In real systems, the shared state could be a release directory, a `current` symlink, an environment tag, a database record, or a load balancer configuration.

### Serializing with a Lock

Create `deploy-locked.sh` to lock the entire deployment target. The second process must wait for the first process to release the lock:

```bash
#!/usr/bin/env bash
set -euo pipefail

release="${1:?Must provide release version}"
delay="${2:-0}"

exec 9>deploy.lock
flock 9

printf 'Acquired lock, deploying %s\n' "$release"
sleep "$delay"
tmp_file="current-release.$$"
printf '%s\n' "$release" > "$tmp_file"
mv "$tmp_file" current-release.txt
printf 'Activated %s and released lock\n' "$release"
```

Run both versions again in the same directory:

```bash
bash deploy-locked.sh release-A 4 &
pid_a=$!
sleep 1
bash deploy-locked.sh release-B 0 &
pid_b=$!
wait "$pid_a" "$pid_b"
cat current-release.txt
```

Because A acquires the lock first, B must wait until A completes. The final result is `release-B`. The lock ensures two processes do not modify deployment state at the same time. Using `mv` replaces the target file atomically within the same filesystem, preventing readers from seeing partially written content.

`flock` is suitable for simulating processes on the same host sharing a lock-capable filesystem. It does not automatically protect multiple runners on separate hosts if each runner has its own filesystem. For distributed deployments, use a lock/lease mechanism in a shared coordination store or the platform's deployment orchestration features. Leases should include expirations and fencing tokens so a stale process that lost authority cannot overwrite newer state.

### Configuring Concurrency in GitHub Actions

At the deploy job level, declare a concurrency group scoped by environment:

```yaml
deploy-production:
  needs: build-test
  if: ${{ needs.build-test.result == 'success' }}
  runs-on: ubuntu-latest
  environment: production
  concurrency:
    group: production-deploy
    cancel-in-progress: false
  steps:
    - uses: actions/checkout@v4
    - uses: actions/download-artifact@v4
      with:
        name: app-${{ github.sha }}
        path: build/libs
    - name: Deploy the verified artifact
      run: ./scripts/deploy.sh
```

Runs sharing `production-deploy` will not execute the deploy job in parallel. `cancel-in-progress: false` lets the active job finish instead of cancelling it when a new run arrives. However, GitHub Actions retains at most one running job and one pending job per concurrency group; an older pending job may be superseded by a newer one, and FIFO ordering is not guaranteed. If every version must deploy in strict FIFO order, use a dedicated release queue or an orchestrator with explicit ordering guarantees.

**Key takeaway:** locking solves concurrent writes to an environment; queuing policies solve release ordering. These are related but distinct requirements. Explicitly decide whether your system needs to serialize every version or only deploy the latest version.

## Combining Controls into One Pipeline

The example below illustrates a minimal flow for a Gradle project on GitHub Actions. The deploy job depends strictly on build/test success, downloads the artifact produced from the same commit, and checks service health post-deployment. `scripts/deploy.sh` is your project's deployment script; connect that script to your test environment.

```yaml
name: ci-cd-failure-lab

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  build-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Build and test
        run: ./gradlew --no-daemon clean build

      - name: Upload the verified artifact
        uses: actions/upload-artifact@v4
        with:
          name: app-${{ github.sha }}
          path: build/libs/*.jar
          if-no-files-found: error

  deploy-staging:
    needs: build-test
    if: ${{ needs.build-test.result == 'success' }}
    runs-on: ubuntu-latest
    environment: staging
    concurrency:
      group: staging-deploy
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          name: app-${{ github.sha }}
          path: build/libs

      - name: Confirm artifact exists
        run: test -n "$(find build/libs -maxdepth 1 -type f -name '*.jar' -print -quit)"

      - name: Deploy
        env:
          DEPLOY_TOKEN: ${{ secrets.STAGING_DEPLOY_TOKEN }}
        run: ./scripts/deploy.sh

      - name: Check service health
        env:
          HEALTH_URL: ${{ secrets.STAGING_HEALTH_URL }}
        run: |
          test -n "$HEALTH_URL"
          curl --fail --silent --show-error \
            --connect-timeout 2 --max-time 5 \
            --retry 2 --retry-delay 1 --retry-max-time 15 \
            "$HEALTH_URL/health"
```

Before using the workflow, verify your project actually generates a JAR at `build/libs/*.jar`, both secrets are configured in the repository/environment, and the deploy script accepts the right artifact. If your project does not produce a JAR, update the upload/download paths and verification command to match the actual artifact type. Never rebuild the application inside the deploy job: deploy the exact artifact that passed build/test so tested code never diverges from released code.

Failure-handling flow:

| Failure | Signal to Observe | Expected Behavior |
|---|---|---|
| Compile or test error | Non-zero Gradle exit code, error in logs | Build job fails; artifact upload and deploy do not run |
| Service unresponsive | `curl` timeout, typically code `28` | Request aborts at timeout; finite retries; if final health check fails, deploy job fails |
| Cannot connect to host | `curl` fails to open connection, typically code `7` | Connection error recorded; retried within bounds; deploy is not marked successful |
| Two deploys to same environment | Two jobs in same concurrency group | Only one deploy job runs at a time; queue policy governs pending job |
| Deploy succeeds but health check fails | Endpoint fails to return HTTP success | Release marked failed; triggers defined investigation or rollback procedure |

## Verifying Lab Results

Complete each item and record evidence in your logs or notes:

- [ ] Introduce an intentional test failure, identify the failing test, and observe a non-zero exit code.
- [ ] Confirm the deploy job is skipped when the build/test job fails.
- [ ] Simulate an unresponsive server and distinguish timeout from connection refused.
- [ ] Restore the server, call the health endpoint successfully, and verify exit code `0`.
- [ ] Demonstrate finite retries ending in failure when the service remains unavailable.
- [ ] Run two unlocked deploy scripts and observe an older version overwriting a newer version.
- [ ] Re-run with locking and confirm the two writes are serialized.
- [ ] Verify the pipeline's concurrency group uses the exact environment name and does not cancel in-progress deploys.
- [ ] Confirm the artifact is built once, tied to the commit, and reused in the deploy job.
- [ ] Verify post-deploy health checks enforce timeouts and reflect failures in pipeline status.

## Self-Assessment Questions

1. Why should a pipeline not proceed with deployment when unit tests fail, even if packaging could still produce a JAR file?
2. When `curl` times out on a data-writing request, why can immediately retrying produce duplicate side effects?
3. In the race condition simulation, why can the version that started first end up as the final activated version?
4. What problem does `flock` solve on a single host, and what is still missing when runners execute across multiple hosts?
5. How does `cancel-in-progress: false` protect a running job, and what is the limitation of a concurrency group when multiple versions are waiting?
6. Why should you deploy the already-tested artifact rather than rebuilding in the deploy job?

A reliable pipeline makes success/failure states explicit, bounds wait times, controls retry counts, and protects shared deployment targets. After this lab, apply these principles in staging first, inspect logs and release history, and only then promote verified configurations to production.
