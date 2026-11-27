# Managing Lifecycle, Configuration, and Versions of Standalone Stubs

## 1. What Problem Do Standalone Stubs Solve?

In **Spring Cloud Contract**, producers and consumers agree on API behavior using **Groovy DSL** or **YAML DSL**. **Spring Cloud Contract Verifier** can generate tests for the producer and build stubs; consumers use **Stub Runner** or a WireMock server to run tests without starting the real producer. Bringing those components into CI lets teams detect incompatible API changes before deployment.

Normally, a consumer test can use `@AutoConfigureStubRunner` to launch stubs right inside the test lifecycle. However, some situations call for **stubs running independently as a process or container**:

- Frontends, mobile apps, or non-Java services need a stable simulated HTTP endpoint.
- Multiple teams validate a published contract concurrently without running the real producer app.
- Integration tests must start stubs **before** launching the consumer.
- CI wants to provision, readiness-check, and tear down stubs as separate test services.
- A team needs to reproduce a bug using the exact **stub artifact/version** from an earlier build.

**Standalone stub** does not mean "running a production service in test mode." It is a server simulating declared behavior—such as WireMock accepting `GET /api/orders/42` and returning sample JSON. It **has no database or producer business logic**, unless you explicitly implement stateful simulation.

The goal of this lesson is managing **lifecycle** (start → ready → serve → reset → stop), **configuration** (artifacts, repositories, ports, networking, file roots, execution modes), and **versioning** (right contract, right classifier, traceable and reproducible).

## 2. Two Models of Running Standalone Stubs: Do Not Equate Them

Two deployment paths are common in practice:

| Model | Input Resources | Runtime | Best Suited For |
|---|---|---|---|
| **WireMock standalone** | Prepared `mappings/` and `__files/` | WireMock running in a JVM/container | Testing/mocking HTTP APIs with explicit mapping files |
| **Stub Runner Boot/standalone** | Artifact `group:artifact:version:stubs` in a compatible Maven repo | A standalone Stub Runner app loading and serving stubs | Reusing stubs published by Spring Cloud Contract producers |

They are related, yet not identical:

- WireMock standalone **does not resolve Maven artifacts** or run generated producer tests; it reads mappings from the file root you specify.
- Stub Runner is responsible for **resolving stub artifacts** by coordinates/configuration and starting the corresponding serving mechanism. For HTTP stubs, the runtime is typically WireMock.
- A `-stubs.jar` package is **not** an executable application; never assume it can run via `java -jar order-service-1.4.0-stubs.jar`.
- For **messaging** contracts, you cannot take a standalone WireMock HTTP server and expect it to emit Kafka/RabbitMQ messages; you need a messaging adapter/test binder or appropriate stubbing mechanism.

In this lesson, the primary examples are **HTTP**. Limitations around messaging and stateful scenarios are analyzed separately to prevent misconceptions.

```mermaid
flowchart LR
    A["Groovy/YAML Contract"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer tests"]
    B --> D["WireMock mappings + body files"]
    D --> E["Versioned -stubs.jar"]
    E --> F["Standalone Stub Runner"]
    D --> G["WireMock standalone<br/>after preparing file root"]
    F --> H["Consumer tests"]
    G --> H
    C --> I["Real producer"]
```

**Principle:** standalone stubs only supply a **simulated API**; proving the real producer obeys the contract still requires generated producer tests.

## 3. One Source Contract Throughout

Suppose producer `order-service` exposes:

```http
GET /api/orders/42
Accept: application/json
```

Returning:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"state":"PAID","currency":"VND"}
```

### 3.1. Groovy DSL

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Find a paid order'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            header 'Accept', 'application/json'
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            state: 'PAID',
            currency: 'VND'
        )
    }
}
```

### 3.2. Equivalent YAML DSL

```yaml
description: Find a paid order
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    state: PAID
    currency: VND
```

These are **two ways to express the same scenario**; never store both simultaneously to avoid generating duplicate contracts. Verifier generates producer tests and stub mappings according to build configuration.

For consumers to test business errors, define a separate contract—for instance `GET /api/orders/9999` returning `404` with body `{"code":"ORDER_NOT_FOUND"}`. **Do not confuse a 404 from WireMock finding no matching mapping** with a producer-committed business error response.

## 4. Lifecycle of a Standalone Stub Server

The lifecycle should be managed like a test resource, not a long-running process with no clear owner:

```mermaid
stateDiagram-v2
    [*] --> Stopped
    Stopped --> Starting: Start process/container
    Starting --> Ready: Bind port, load mappings, probe passes
    Starting --> Failed: Bind/resolve/config error
    Ready --> Serving: Consumer starts tests
    Serving --> Ready: Clean request journal/scenarios appropriately
    Ready --> Stopping: Suite/CI ends
    Serving --> Stopping: Suite/CI ends
    Failed --> Stopping: Reclaim resources
    Stopping --> Stopped: Stop and release port
```

| Phase | Tasks | Expected Evidence |
|---|---|---|
| **Resolve/configure** | Choose artifact or file root, version, repository, port | Valid, traceable coordinates and configuration |
| **Start** | Launch process/container, bind ports, load stubs | Runtime alive without startup errors |
| **Ready** | Verify server accepts requests **matching mappings** | Probe request returns expected status/body |
| **Serve** | Consumer sends HTTP calls to stub URL | Valid requests match; consumer assertions pass |
| **Reset/isolate** | Clear request history/scenarios or provision fresh instance | Later tests do not depend on earlier tests |
| **Stop/cleanup** | Stop server/container and reclaim test resources | Ports and resources released |

**An existing process does not mean the server is ready.** A Stub Runner Boot app can open its management port before resolving artifacts, or WireMock can run before loading the right mappings. An open port is only a preliminary check; probing a **sample endpoint** is far more meaningful.

### 4.1. Who Owns the Lifecycle?

There should be **one clear owner** for each stub instance:

- The test class or test suite, if the stub serves only one suite.
- The CI job, if multiple tests/processes share the stub within one job.
- Container orchestration / test environment, if the stub serves an integration environment.

The owner is responsible for starting, waiting for readiness, passing URLs to consumers, resetting appropriately, and stopping. Never let multiple test suites wipe mappings on a shared instance or shut down a server another test still needs.

## 5. Versioning, Classifier, and Artifact Reproducibility

A common coordinate format for Stub Runner:

```text
com.example:order-service:1.4.0:stubs:8090
|_________|_____________|_____|_____|____|
    group     artifact   version classifier port
```

| Field | Example | Meaning |
|---|---|---|
| Group | `com.example` | Publishing organization/module |
| Artifact | `order-service` | Producer owning the stub |
| Version | `1.4.0` | Contract version to fetch |
| Classifier | `stubs` | JAR variant containing stub mappings/resources |
| Port | `8090` | Requested HTTP port for this stub when running |

**The port is not metadata inside the JAR.** It is selected at runtime; the same `1.4.0:stubs` artifact can serve on different ports.

### 5.1. Pin Versions Instead of Always Pulling "Latest"

| Usage | Pros | Risks | Recommendation |
|---|---|---|---|
| `1.4.0` | Reproducible results | Must bump version deliberately | **Preferred** for release CI |
| `+` in supported configs | Easy to test latest version found by resolver | Changes by repository/cache/timing | Use in canary jobs; log resolved version |
| `1.5.0-SNAPSHOT` | Handy during development | Snapshot contents can mutate | Record commit/build/checksum; control cache |
| Immutable release | Auditable and rollback-safe | Requires release discipline | Fits strict pipelines |

Never assume a newer version is **backward-compatible**. Changing `state` to a new enum, changing a JSON number to a string, or changing `404` to `200` can break consumers even if the producer bumped only a minor or patch version.

### 5.2. Pick the Right Artifact Instead of the Application JAR

Suppose the producer produces:

```text
order-service-1.4.0.jar
order-service-1.4.0-stubs.jar
```

The first JAR is the producer application/library; the second is the **stub-serving artifact** via classifier `stubs`. Merely seeing `order-service-1.4.0.jar` in the repository **does not prove** `-stubs.jar` was attached and published.

For a file downloaded from an artifact repository, inspect it:

```bash
# Example inspection of an artifact already on disk.
jar tf order-service-1.4.0-stubs.jar
```

Inspect the actual JAR entries—especially `mappings`, `__files` (if needed), and artifact/version identifiers—rather than just checking the outer filename.

### 5.3. Artifact Immutability and Provenance

CI logs or test environment manifests should record:

```text
Producer       : com.example:order-service
Requested      : 1.4.0:stubs
Resolved       : 1.4.0:stubs
Artifact SHA256: <actual checksum if collected by pipeline>
Producer commit: <matching commit if available>
Repository     : <repo URL, excluding credentials>
Stub port      : <actual port>
```

The angle brackets above are **placeholders to fill with observed runtime data**, not defaults from Stub Runner. If your publisher allows overwriting releases under the same version, pinning `1.4.0` alone is not enough for full reproducibility: enforce **immutable releases** or compare checksums.

## 6. Model A: Running WireMock Standalone with a Stub Directory

When you already have WireMock mappings and want a standalone server without Maven resolution, prepare a **file root** laid out as:

```text
wiremock-root/
├── mappings/
│   ├── get-order-42.json
│   └── get-order-not-found.json
└── __files/
    └── orders/
        └── order-42.json
```

Example `mappings/get-order-42.json`:

```json
{
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/42",
    "headers": {
      "Accept": { "equalTo": "application/json" }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json; charset=utf-8"
    },
    "bodyFileName": "orders/order-42.json"
  }
}
```

Example `__files/orders/order-42.json`:

```json
{
  "id": 42,
  "state": "PAID",
  "currency": "VND"
}
```

Here `bodyFileName` is resolved **relative to `__files/`**, not as an absolute disk path. A mapping can also inline `response.body`/`jsonBody`; **not every mapping needs a body file**.

### 6.1. Starting the WireMock Standalone JAR

Once you have a **WireMock standalone runnable JAR** compatible with your Java runtime:

```bash
# Example command; adapt JAR name, root-dir, and port to your environment.
java -jar wiremock-standalone-<VERSION>.jar \
  --port 8090 \
  --root-dir ./wiremock-root
```

`<VERSION>` is a placeholder, **not** a pre-provided filename. Once the server starts, the consumer can call:

```bash
curl -i \
  -H "Accept: application/json" \
  http://127.0.0.1:8090/api/orders/42
```

The response should return `200` and the described JSON. If you get `404`, do not jump to the conclusion that the business API lacks order `42`: it may simply be **WireMock failing to match a mapping** due to a wrong file root, wrong method/path/headers, or unloaded mappings.

**Do not try to run** `order-service-1.4.0-stubs.jar` with the command above: that JAR holds stub resources, not a WireMock executable. To use a file root, prepare/extract resources in the expected structure from the published artifact or obtain mappings/body files through a controlled build step.

### 6.2. Starting via Container

Minimal Docker Compose example:

```yaml
services:
  order-stub:
    image: wiremock/wiremock:REPLACE_WITH_PINNED_VERSION
    ports:
      - "127.0.0.1:8090:8080"
    volumes:
      - ./wiremock-root:/home/wiremock:ro
```

In this example:

- Replace `REPLACE_WITH_PINNED_VERSION` with a verified valid tag/digest before running; avoid `latest` in reproducible CI.
- `/home/wiremock` is the standard file root of the official WireMock image; verify against the image/version your team deploys.
- Host `127.0.0.1:8090` maps to HTTP port `8080` **inside the container**. Consumers running on the host use `127.0.0.1:8090`.
- If a consumer runs in **another container on the same Docker Compose network**, it should usually call `http://order-stub:8080`, **not** `http://localhost:8090`.
- Mounting `:ro` prevents containers from mutating fixtures; request journals and runtime state still need isolation across the server lifecycle.

This is an **illustrative configuration**, not executed in this lesson. When using containers, CI must manage bind permissions, networking, resource cleanup, and image pull policies so a different image isn't run by mistake.

### 6.3. When Not to Use WireMock Standalone?

If the goal is to **automatically fetch newly published `group:artifact:version:stubs` artifacts from a Maven repository**, plain WireMock standalone does not handle that. You would have to add a **resolve JAR → unpack/locate mappings and body files → configure file root** step. If you prefer not to manage that step yourself, **standalone Stub Runner** is usually a better fit.

## 7. Model B: Stub Runner Boot as a Separate Application

In the Spring Cloud Contract ecosystem, you can use **Stub Runner Boot** (or a standalone runtime packaged by the project with Stub Runner support) to run stubs outside the consumer's JUnit tests. You need a **runnable application JAR/container of the right version** and valid repository/artifact configuration.

Illustrative application-level configuration:

```yaml
stubrunner:
  ids:
    - com.example:order-service:1.4.0:stubs:8090
  stubs-mode: REMOTE
  repository-root: https://repo.example.org/maven-releases
server:
  port: 8999
```

**Distinguish the two ports in this example:**

- `8090` is **inside the stub coordinates**: the HTTP port `order-service`'s WireMock instance is requested to use.
- `server.port: 8999`: the HTTP port of the **Stub Runner Boot application**, if that distribution starts its own management/HTTP server. It is **not necessarily the port receiving `GET /api/orders/42`**.

With Spring Boot relaxed binding, property names may appear in kebab-case or camelCase depending on the tool, so **verify exact names and support against your actual version**. Never copy a sample from another release assuming resolvers, ports, or REST endpoints behave identically.

### 7.1. A Meaningful Startup Command

Assuming the project has a **runnable Stub Runner Boot JAR** placed locally as `stub-runner-boot.jar`:

```bash
java -jar ./runtime/stub-runner-boot.jar \
  --stubrunner.ids=com.example:order-service:1.4.0:stubs:8090 \
  --stubrunner.stubs-mode=REMOTE \
  --stubrunner.repository-root=https://repo.example.org/maven-releases \
  --server.port=8999
```

This is a **sample command with a pre-prepared runtime artifact**, not a claim that every project automatically produces `./runtime/stub-runner-boot.jar`. Before using it, verify **how to obtain/build a launcher supported by your team's Spring Cloud Contract version**, Java requirements, dependencies, and artifact resolution capabilities.

With `LOCAL`, the runtime looks for stubs in the Maven local repository of **the running machine/container**. With `REMOTE`, a repository URL and authentication mechanism are required. With `CLASSPATH`, stub resources must **actually reside on the classpath** in a way the runtime recognizes; switching modes does not automatically download stubs over the network.

### 7.2. Loading Multiple Stubs in One Runtime

A test environment may need multiple producers:

```properties
stubrunner.ids=com.example:order-service:1.4.0:stubs:8090,com.example:payment-service:2.1.0:stubs:8091
stubrunner.stubs-mode=REMOTE
stubrunner.repository-root=https://repo.example.org/maven-releases
```

This illustrates a **comma-separated list property**; verify how your version parses it in practice. Never assign the same port `8090` to two stub servers in the same network namespace.

When loading multiple stubs, the consumer needs separate base URLs for `order-service` and `payment-service`. Never share a single `upstream.base-url` config for both merely because they share a launcher.

### 7.3. When Should You Avoid a Shared Stub Runner?

A shared process saves resources, but can cause:

- Difficulty isolating request journals and scenario state per test suite.
- One restart disrupting multiple consumer teams.
- Changing one stub's version breaking unrelated tests.
- Risk of port collisions and global resets.

If suites must run independently in parallel, **provision a dedicated stub environment per job** or guarantee separate namespaces and reset permissions per group.

## 8. Configuration Management: Separating Immutables from Runtime Settings

Good configuration separates:

| Config Group | Example | Strategy |
|---|---|---|
| **Contract provenance** | `com.example:order-service:1.4.0:stubs` | Pin version; record commit/checksum |
| **Artifact source** | `REMOTE` + Maven repository URL | Configure per environment; protect credentials |
| **Runtime network** | Hostname, port, container DNS | Allocate at runtime; pass to consumer |
| **Test behavior** | Scenarios, fixtures, response delays | Isolate per suite; reset intentionally |
| **Operations** | Readiness timeouts, logs, resource limits | Managed by CI/orchestrator |

Never put artifact repository tokens into contracts, mappings, or commits:

```text
# Wrong: credentials embedded in URL or source.
https://username:password@repo.example.org/releases

# Better: secret-free URL, with credentials injected from a
# secrets manager / CI environment via resolver-supported mechanisms.
https://repo.example.org/releases
```

For a stub runtime serving multiple apps, define **who is allowed to alter mappings, reset scenarios, and shut down the server**. WireMock's Admin API is a state-mutating interface; **never expose it to public networks** without proper protection.

### 8.1. Passing the Address to the Consumer

Suppose the consumer defines a property:

```yaml
clients:
  orders:
    base-url: http://order-stub:8080
```

In Docker Compose, `order-stub` is the service's internal hostname. In host-based tests with port mapping `127.0.0.1:8090:8080`, the base URL must be `http://127.0.0.1:8090`.

**Never hardcode URLs in production Java code**. Use configuration/property injection and set the base URL **before the HTTP client bean is constructed**. If `WebClient` or `RestClient` is built when the Spring context initializes, mutating a field in `@BeforeEach` may be too late.

### 8.2. Random Ports vs. Fixed Ports

- **Fixed ports** are convenient for a dedicated test environment with predictable addresses, but collide easily in parallel CI.
- **Dynamic ports** work well when a test harness spawns stubs per job, provided the consumer receives the real address after the server binds.
- Stub Runner Boot's `server.port` (if present) and each stub's WireMock port can be **two separate port types**.
- Never infer ports from JAR classifiers or versions; ports are **runtime** details, not baked into artifacts.

Trying to allocate ports by "find free port → close socket → start stub on that number" introduces a race condition. Let the server bind port `0` when supported and read the **actual bound port afterward**, or let orchestration assign endpoints/ports cleanly.

## 9. Readiness, Liveness, and Actual Testing Are Distinct

An environment passes through three validation levels:

| Level | Question | Illustrative Evidence |
|---|---|---|
| **Liveness** | Is the process/container alive? | Running PID / container |
| **Readiness** | Is the stub ready to serve meaningful requests? | Sample endpoint returns committed status/body |
| **Consumer verification** | Are the HTTP client and consumer logic compatible? | Consumer test report passes assertions |

Quick check against a WireMock standalone server:

```bash
curl --fail --silent --show-error \
  -H "Accept: application/json" \
  http://127.0.0.1:8090/api/orders/42
```

`curl --fail` only confirms a non-error HTTP status per curl's rules; it **does not automatically prove the JSON body has `state=PAID`**. A stricter readiness check parses/checks key fields or runs a verified probe scenario.

### 9.1. Do Not Use `sleep 10` as Readiness

```text
Wrong:
  start stub
  sleep 10
  run consumer tests

Right:
  start stub
  poll endpoint with a bounded timeout
  confirm expected status + sample response
  run consumer tests
  always clean up at end of job
```

A fixed delay wastes time on fast machines and still fails on slow CI. Bounded polling distinguishes a server that is **not ready yet** from one that **failed to start**.

### 9.2. Reliable Start/Stop Ordering

1. Provision workspace/network and pick the artifact or file root.
2. Start the stub process/container.
3. Wait for readiness up to a finite deadline; fail the job if it misses the deadline.
4. Expose the **actual URL** to the consumer.
5. Run consumer tests; save logs and request journals on failure.
6. Stop the server/container and reclaim resources in cleanup **whether tests pass or fail**.

If multiple tests share a stub, never shut down the instance after test A while test B is still running.

## 10. Statefulness: Request Journal, Mappings, and Scenarios

WireMock holds several **distinct** kinds of state:

- **Stub mappings:** request/response rules loaded from files or added dynamically.
- **Request journal:** log of received requests, useful for verifying how many times a consumer called an endpoint.
- **Scenario state:** state of WireMock scenarios simulating sequential flows.
- **Response files/templates:** data or template configs used to render responses.

Resetting the wrong kind can break your suite:

| What You Want to Clean | Approach | Risk |
|---|---|---|
| Clear only request history | Reset the request journal alone | Leaves needed mappings intact |
| Reset scenario to initial state | Reset scenarios via your library/API | Can affect other tests sharing the server |
| Undo dynamic mappings | Delete test-created mappings or launch a fresh instance | Wiping all mappings can cause unmatched 404s |
| Wipe all state | Restart a dedicated instance per test/job | Slower, but clean isolation |

**Never call reset-all indiscriminately** if mappings loaded from an artifact cannot be automatically reloaded. One test wiping all mappings can cause another test on the same server to receive `404` even with the right artifact.

### 10.1. Static Stubs Are Not a Mock Database with a State Machine

If the consumer calls:

```text
POST /api/orders/42/pay  → returns 200
GET  /api/orders/42      → expects new state PAID
```

two static mappings **do not automatically persist state changes**. To simulate stateful sequences, use **WireMock scenarios** or run an integration test against the real producer. For ordering, idempotency, and durable side-effect guarantees, never assume everything is verified by a simple stub scenario.

### 10.2. Parallel Tests with Scenario State

Two tests both using `scenarioName=payment-flow` on one server will stomp on each other's state. Even if scenarios are reset in `@AfterEach`, they can still collide **while running concurrently**.

The preferred fix is **a dedicated stub server per suite/job**, or isolated scenario/fixture namespaces if supported. If sharing a server is unavoidable, synchronize tests and assign explicit reset ownership rather than just adding delays.

## 11. Security and Network Isolation for Standalone Stubs

A stub server generally **does not have the same security layers** as the production producer. If exposed to external networks, outsiders can read fixtures, call mock endpoints, or hit admin APIs to alter mappings/responses.

Measures to apply:

1. **Bind only to loopback** when the consumer runs on the same machine; with containers, use internal networks and restrict published ports.
2. Never expose WireMock's Admin API to the public internet or untrusted networks; enforce network ACLs, reverse proxies, or proper guards.
3. **Never include real personal data**, API tokens, passwords, or sensitive internal info in stub responses.
4. Run containers with least privilege and read-only fixture volumes whenever possible.
5. Restrict artifact repository read permissions; never put credentials in URLs or logs.
6. Clean up containers, ports, and temporary files after CI so no "orphaned" test environments remain.
7. If a stub must simulate auth errors, use **fake tokens** only—never production secrets.

Stubs are **contract-based simulations**, not a public API substitute for the producer. Mock responses may lack real rate limiting, authorization, or validation unless explicitly modeled in mappings.

## 12. Keeping Stubs, Producers, and Consumers Compatible

```mermaid
sequenceDiagram
    participant P as Producer CI
    participant R as Artifact repository
    participant S as Standalone stub runtime
    participant C as Consumer CI
    P->>P: Generate and run producer contract tests
    alt Tests actually pass
        P->>R: Publish versioned -stubs.jar
        S->>R: Resolve right group/artifact/version/classifier
        S->>S: Load mappings and verify readiness
        C->>S: HTTP via real client
        S-->>C: Contract sample response
        C->>C: Assert DTO, errors, and workflow
    else Producer tests fail or are skipped
        P-->>P: Do not publish new stub
    end
```

### 12.1. Why Does a Passing Stub Not Prove the Real Producer Works?

A stub only returns data defined in its artifact. If producer code changed `{"state":"PAID"}` to `{"state":"PENDING"}` while generated producer tests were not run, the old stub still returns `PAID` and consumer tests still pass.

Therefore, verify **both pieces of evidence**:

- **Producer verification:** generated contract tests were generated, compiled, discovered, executed, and passed assertions.
- **Consumer verification:** consumer tests called the exact standalone stub version, testing deserialization and meaningful business behavior.

When a consumer targets a deployed producer version, cross-check **stub version ↔ producer build ↔ deployment manifest**. Sharing the name `order-service` alone does not guarantee the right contract version.

### 12.2. Canaries for Detecting Upcoming Changes

You can maintain two jobs:

- **Release gate:** uses pinned version `1.4.0`, archiving checksums and reports.
- **Compatibility canary:** tests `+`/snapshots or upcoming release candidates, logging the exact resolved artifact.

Never mix a "pull latest" canary job into a pinned release gate without controls; if dependencies shift between runs, tests stop being reproducible.

## 13. Writing a CI Script to Manage Standalone WireMock Lifecycle

With WireMock standalone and an existing file root, an **illustrative Linux/bash** script can manage start/ready/test/stop:

```bash
#!/usr/bin/env bash
set -euo pipefail

STUB_JAR="./runtime/wiremock-standalone.jar"
STUB_ROOT="./wiremock-root"
STUB_PORT="8090"
STUB_URL="http://127.0.0.1:${STUB_PORT}"
STUB_PID=""

cleanup() {
  if [ -n "${STUB_PID}" ]; then
    kill "${STUB_PID}" 2>/dev/null || true
    wait "${STUB_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Ensure JAR and file root were built from controlled sources.
java -jar "${STUB_JAR}" --port "${STUB_PORT}" \
  --root-dir "${STUB_ROOT}" > wiremock.log 2>&1 &
STUB_PID=$!

READY=0
for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error \
       -H "Accept: application/json" \
       "${STUB_URL}/api/orders/42" > /dev/null 2>&1; then
    READY=1
    break
  fi
  if ! kill -0 "${STUB_PID}" 2>/dev/null; then
    echo "WireMock process stopped unexpectedly" >&2
    break
  fi
  sleep 1
done

if [ "${READY}" -ne 1 ]; then
  echo "Stub not ready; inspect wiremock.log" >&2
  exit 1
fi

# Pass STUB_URL to the consumer test step per your project's build tool.
echo "Stub ready at ${STUB_URL}"
# Example: STUB_BASE_URL="${STUB_URL}" ./gradlew test
```

**Operational warnings:**

- This script illustrates **lifecycle management**—it has not been executed and omits the real consumer test command; adjust paths, tools, and pipeline integration accordingly.
- Port `8090` must be dedicated exclusively to the job; if CI runs concurrently in the same network namespace, use dynamic ports or container/service networking.
- `curl --fail` only checks for 2xx/3xx status on the sample endpoint. A strict job should **verify body/schema** or run a stronger probe test.
- `trap cleanup EXIT` catches most shell exits, yet **is not guaranteed to run on uncatchable kills**; pair it with CI/container orchestration cleanup as a safety net.
- When pipeline tests fail, archive `wiremock.log` and reports before tearing down the environment.
- `sleep 1` inside a **deadline-bounded readiness loop** is sensible—unlike a blind `sleep 10` assuming the server must be ready.

If tests run on Windows, use the matching process/cleanup mechanisms; do not paste a Bash script directly into PowerShell.

## 14. Observing and Diagnosing Failures

| Symptom | Possible Cause | What to Verify |
|---|---|---|
| `Address already in use` | Stub port occupied or old server still running | Bound PID/container, port allocation |
| Process running yet consumer gets `404` | Mappings not loaded or request mismatch | File root, method/path/query/headers |
| Stub Runner fails to fetch JAR | Wrong coordinates/classifier or repo permissions | Group/artifact/version/`stubs`, URL, auth |
| LOCAL works, REMOTE fails | Artifact unpublished or wrong repository config | Whether repo actually contains `-stubs.jar` |
| Returns old version's response | Cache, `+`, snapshot, or wrong environment | Resolved artifact version/checksum |
| Body file not found | Wrong `bodyFileName` path or JAR missing `__files` | Mapping and relative file paths |
| Consumer calls wrong port | Confused stub port with launcher/app port | Runtime URL actually used by consumer |
| Consumer container cannot reach `localhost` | Two containers have separate network namespaces | Service hostname and container port |
| Returns `404` yet test passes | Unmatched 404 mistaken for business error | Assert error code/schema |
| Single test passes, suite fails | Unreset scenario or request journal | Isolation and reset policy |
| Same artifact yields different results | Config/mapping overrides or stateful scenarios | Checksums, startup args, state |
| Stub started yet serves no mappings | Runtime passed liveness, not readiness | Probe a specific endpoint |
| Deployed producer differs from stub | Version not tied to deployment | Release manifest, producer verification |
| CI job ends yet port stays busy | Process/container not cleaned up | Trap/cleanup job, resource owner |

### 14.1. Effective Investigation Order

1. **Which runtime?** WireMock standalone or Stub Runner Boot?
2. **Which artifact?** Exact name/version/classifier/checksum, or which file root?
3. **Which startup config?** Repo mode, port, host, mappings, volumes.
4. **Is the runtime ready?** Does probing the endpoint return expected output?
5. **Which URL does the consumer see?** Right network namespace, scheme, host, and port?
6. **Does the request match the mapping?** Compare method/path/query/headers/body.
7. **Is state leaking?** Scenarios, request journal, or mapping overrides.
8. **Did producer generated tests run?** Passing stub tests never replace them.

Do not immediately edit contracts or loosen matchers upon seeing `404`; the problem may be **picking the wrong artifact or calling the wrong server**.

## 15. Hands-On Exercise: Deploying a Standalone Stub Environment for Checkout

**Context:** `checkout-service` currently calls real `order-service` during development, causing test failures whenever the producer undergoes maintenance. The team wants a stable standalone stub in CI and the ability to test newer artifacts in a compatibility job.

### 15.1. Tasks

1. Create contract `GET /api/orders/42` returning `200` with `id=42`, `state=PAID`, and `currency=VND`; add contract `GET /api/orders/9999` returning `404 + ORDER_NOT_FOUND`.
2. On the producer, run generated contract tests and confirm **tests actually executed and passed**, not merely generated mappings.
3. Package/publish `com.example:order-service:1.4.0:stubs`, recording checksum/commit or equivalent metadata.
4. **Option A:** prepare `mappings` and `__files`, run WireMock standalone in an isolated test environment, and wait for readiness.
5. **Option B:** use a compatible Stub Runner Boot runtime configured to resolve `com.example:order-service:1.4.0:stubs` from the repository and run the stub on an assigned port.
6. Configure `checkout-service` to use the **runtime stub URL**, never production DNS.
7. Verify Checkout's real HTTP client deserializes a `PAID` order and handles the `ORDER_NOT_FOUND` error body properly.
8. Archive artifact version, port, URL, logs, and test reports; rerun with the same version to confirm reproducibility.
9. If tests need stateful scenarios, reset scenario/request history between tests or give the suite its own server.
10. End the job, stop the stub, and confirm resources are reclaimed. Intentionally block the port or delete a body file in a test environment to verify readiness/CI reports failures clearly.
11. Create a canary job using upcoming release candidate `1.5.0` and rerun consumer tests; inspect schema/status diffs rather than merely checking whether the stub booted.

### 15.2. Self-Check Questions

| Question | Answer |
|---|---|
| Is `-stubs.jar` an executable HTTP server by default? | **No**, it is normally an artifact containing stub resources |
| Does WireMock standalone automatically download Maven artifacts by coordinates? | **No**, not without an additional resolver/config step |
| Is Stub Runner Boot the producer application itself? | **No**, it launches stubs from resolved resources |
| Is the launcher's `server.port` always `order-service`'s WireMock port? | **No**, distinguish both port types |
| Can you check only whether a process is alive to declare a stub ready? | **No**, probe a sample endpoint and mapping |
| Does `+` guarantee every run uses the exact same artifact? | **No**, log the resolved version or pin it |
| Does a mapping with `bodyFileName` work without `__files`? | **No**, you must provide the referenced body file |
| Is reset-all safe on a shared WireMock server? | **Not by default**, as it can wipe other tests' mappings |
| Does passing stub tests prove the real producer behaves properly? | **No**, generated producer tests are required |
| Should a standalone stub be exposed publicly on the internet for "convenient testing"? | **No**, control networking, admin access, and data |

## 16. Operations and Release Checklist for Standalone Stubs

- [ ] Chose the right **WireMock standalone or Stub Runner Boot model**, understanding how each fetches stub resources.
- [ ] Groovy/YAML source contracts are the source of truth; generated producer tests ran and passed.
- [ ] Artifacts use exact group/artifact/version/`stubs` classifier, with provenance/checksums recorded as needed.
- [ ] Versions in primary CI are pinned with immutable releases; `+`/snapshots live in separate jobs if used.
- [ ] File roots/mappings/body files are valid; `bodyFileName` never points to broken paths.
- [ ] Repository mode, URL, and permissions are properly configured; no secrets in source or logs.
- [ ] A clear **resource owner** handles start, readiness wait, URL passing, reset, and stop.
- [ ] Stub runtime ports are separated from launcher, consumer, and real producer ports to avoid collisions.
- [ ] Consumers receive the right base URL per network namespace before HTTP clients initialize.
- [ ] Readiness probes verify a meaningful endpoint rather than fixed sleeps or PID checks.
- [ ] When using scenarios, request journals and dynamic mappings are reset within the right scope.
- [ ] Parallel tests are isolated by process/container/namespace wherever possible.
- [ ] Stub servers and Admin APIs are never exposed to untrusted networks; fixtures contain no sensitive data.
- [ ] Consumer tests call real clients and assert response bodies/error schemas rather than merely starting stubs.
- [ ] CI archives resolved versions, artifact provenance, logs, and test reports for reproducibility.
- [ ] Cleanup guards exist at test, job, and container levels so no orphaned processes or ports remain.

**Remember:** managing **standalone stubs** is more than running a JAR or container. You must **pick the right contract version, load the right mappings, start and readiness-check the server, pass the right address to the consumer, isolate state, and clean up resources afterward**. When combined with producer contract verification and meaningful consumer tests, Spring Cloud Contract catches incompatible API changes in a way that is **repeatable, traceable, and operationally safe**.
