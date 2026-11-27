# Network and Privilege Restrictions for the Stub-Running Process

## 1. Why does a stub serving fake data still need security?

In **Spring Cloud Contract**, producers and consumers agree on HTTP or messaging behavior using **Groovy/YAML DSL**. Tooling can generate tests to verify the producer, package the corresponding stubs, and use **Stub Runner** for consumer tests. For HTTP, **WireMock** is commonly used to serve sample requests/responses; CI combines producer verification and consumer tests to catch incompatible API changes.

A WireMock server returning fake data may seem less risky than a production service. However, **the stub-running process is still a network process** that can:

- Open a **TCP port** and accept requests from a broader scope than intended.
- Expose the **WireMock Admin API** to inspect, add, modify, or reset mappings and the request journal.
- Record **headers, URLs, and bodies** sent by consumers, which might contain cookies, bearer tokens, or private data.
- Download stubs JARs from an **artifact repository** using CI credentials.
- Read/write files, initialize extensions, and run logic governed by OS configuration and permissions.
- Interfere across tests if multiple test jobs share a port or stateful server.

Therefore, the goal of this lesson is not merely getting tests to pass, but **allowing only necessary processes to reach the stub, granting only necessary privileges to the stub, and preventing the mock server from becoming a gateway into CI networks or secrets**.

> **Principle:** A stub is **untrusted test infrastructure like any non-production component**, not a public service. Isolate it by lifetime, network, identity, filesystem, artifact access rights, and logged data.

### Learning objectives

After this lesson, you will be able to:

1. Draw accurate **trust boundaries** among consumer tests, Stub Runner, WireMock Admin API, registries, and real systems.
2. Distinguish binding to `127.0.0.1` vs `0.0.0.0`, host ports vs container ports, and ingress vs egress.
3. Restrict privileges of processes, containers, or Kubernetes Pods running stubs using the **least privilege** principle.
4. Recognize risks from the **Admin API, request journal, proxy mappings, Groovy DSL, and extensions**.
5. Use fake fixtures, keep secrets safe, and distinguish **mock authentication** from **security verification**.
6. Design tests/CI capable of confirming those security boundaries are actually enforced.

## 2. Threat model: who can communicate with the stub?

Consider `checkout-service` testing a client calling `order-service`:

```mermaid
flowchart TD
    A[Consumer test process] -->|HTTP request| B[Stub Runner / WireMock]
    B -->|Sample response| A
    C[Producer CI verified contracts] --> D[Stubs JAR repository]
    D -->|Resolve artifact| B
    E[Other people/processes on network] -.->|Should not be allowed| B
    B -.->|Must not accidentally proxy| F[Production APIs / metadata service]
    B -->|Request journal / files| G[CI workspace and logs]
    H[Test administrator] -->|Only when truly needed| I[WireMock Admin API]
    I --> B
```

The diagram shows distinct flows:

| Flow | Legitimate purpose | Boundary to protect |
| --- | --- | --- |
| **Consumer → HTTP stub** | Call mocked endpoints, receive contract responses | Only authorized clients/tests reach the port |
| **Stub Runner → artifact registry** | Fetch producer-verified stubs JAR | Access only required registry with read credentials |
| **Tester/CI → Admin API and logs** | Inspect mappings, reset scenarios, investigate mismatches | Do not expose to other hosts or outsiders |
| **Stub → other networks** | Usually **unneeded** after loading artifacts | No proxying/egress to production or metadata services |
| **Stub → filesystem/container** | Read mappings, write temp data if runtime requires | No reading out-of-scope secrets or writing whole workspace |

**A sound security model starts with scope of use**: is the stub called only within the same process, the same host, the same Docker network, or by a consumer test in another Pod? Those cases require different connection restrictions.

### Assets to protect

Beyond request bodies, consider **CI secrets**, artifact registry tokens, misconfigured production credentials, request/response logs, mounted source code or volumes, internal networks, and the ability to run untrusted extensions.

If a consumer accidentally sends a production bearer token to the mock server, it can land in the **WireMock request journal** or CI logs even when the response is just fake JSON. Test data security must start at the **client and fixtures**, not wait for a log-scrubbing step.

## 3. Bind address, port, and reachability

An HTTP application listens on an IP address and port:

| Bind address | Common meaning | Notes |
| --- | --- | --- |
| `127.0.0.1:8089` | IPv4 loopback interface within the same network namespace only | Suitable for tests running on the same host |
| `[::1]:8089` | IPv6 loopback | Verify whether clients/OS use IPv4 or IPv6 |
| `0.0.0.0:8089` | All IPv4 interfaces in the network namespace | Reachable from external networks if firewalls/routing permit |
| `<private-ip>:8089` | One specific interface | Still requires firewall and caller restrictions |

**Binding to `0.0.0.0` does not by itself prove a port is public**, yet it is **broader** than loopback: if routing or port forwarding exists, other hosts can connect. Conversely, `127.0.0.1` only limits within the **process's network namespace**; it does not isolate the process from other software already running inside the same namespace.

### When consumer and stub run on the same machine

Prefer **loopback** if supported by the framework/distribution. For example, with standalone WireMock supporting the corresponding flags:

```bash
# Illustrative example; replace JAR name and check --help for your WireMock version.
java -jar wiremock-standalone.jar \
  --bind-address 127.0.0.1 \
  --port 8089
```

After the server starts, verify the actual socket listens only on loopback. CLI flag names and binding options can vary across WireMock versions/packaging; **do not assume from this illustrative command that Stub Runner passes the exact same bind address**.

When using `@AutoConfigureStubRunner`, port and lifecycle may be managed by the framework. If the API/version does not let you set the bind address directly, use **firewalls, network namespaces, Docker/Kubernetes isolation, or run tests on a host with no public inbound access**. Do not invent a `stubrunner.bind-address` property without verifying it in that version's docs.

### Fixed ports and dynamic ports

`ids = "com.example:order-service:1.7.0:stubs:9090"` illustrates assigning a fixed port to a stub. Fixed ports are easy to understand yet can collide when tests run in parallel. Dynamic ports reduce conflicts; the consumer must retrieve the **actual port** from Stub Runner per its lifecycle instead of hardcoding `9090`.

**A dynamic port is not an authentication or authorization control.** It avoids collisions, yet another process on the same host/network namespace can still discover and call the open port. Combine it with network limits and test lifecycle cleanup.

## 4. The WireMock Admin API is a separate attack surface

When enabled, the WireMock Admin API typically sits under `/__admin` and can perform powerful operations such as:

```http
GET /__admin/mappings HTTP/1.1
GET /__admin/requests HTTP/1.1
POST /__admin/scenarios/reset HTTP/1.1
```

Depending on version/configuration, the Admin API can also add, delete, or update mappings and reset the server/request log. Therefore, if someone outside the test can reach admin:

- They can make consumer tests **receive wrong responses**, causing false positives or false negatives.
- They can inspect the request journal containing data sent by clients.
- They can alter mappings or scenario states mid-test.
- They can break **isolation** on shared servers, causing non-reproducible results.

**Do not assume the Admin API has authentication or authorization like a production API.** Many WireMock configurations expose admin endpoints for testing convenience and must be protected at the **network/proxy boundary** if a server is shared.

### Appropriate mitigations

1. Prefer **ephemeral stubs per test job** rather than long-lived shared servers.
2. Never publish the admin port to external networks. If normal HTTP APIs and `/__admin` share the same port, **you cannot rely on configuring a separate port to isolate admin**.
3. For shared remote stub servers, place an **access-controlled reverse proxy** in front with route rules blocking `/__admin` from unauthorized consumers; if the reverse proxy uses authentication, verify the actual rules.
4. If your WireMock version supports disabling/securing the Admin API in a supported way, apply it when tests do not need admin, without inventing CLI flags/properties.
5. Never use `/__admin` as a business endpoint. Tests needing state resets should do so via trusted test fixtures with restricted access.

**Warning:** If consumers can connect directly to the WireMock port, blocking `/__admin` only on a separate gateway **does not protect** admin while a direct path remains. Verify the full topology and network policy.

## 5. Request journals can hold secrets even if stubs never call production

WireMock can record **received requests** for matching diagnostics. A test request accidentally containing:

```http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer TEST_TOKEN_DO_NOT_USE_REAL
Cookie: session=SYNTHETIC_SESSION
X-Correlation-Id: req-test-001
```

uses **fake values** above. In real projects, if CI uses a production token in `Authorization` or a real user cookie, those values can end up in the journal, logs, or report artifacts.

### Data and logging rules

- Send only narrowly scoped, short-lived **test credentials** or dedicated fake tokens—never production bearer tokens.
- Never put real passwords, access keys, or API keys into Groovy/YAML contracts, stub mapping JSON, or publishable test files.
- Enable the request journal only when needed for debugging; limit data/retention and disable or control it per your version's API.
- When exporting the request journal for investigation, **redact Authorization, Cookie, Set-Cookie, and sensitive fields**, including query parameters carrying tokens.
- Never dump entire request/response bodies to public logs. CI artifacts may be retained for days or shared with anyone who has repository read access.
- Clear or reset state after each test/job per lifecycle, remembering that **resetting does not recall already-exported logs**, storage copies, or other telemetry.

### "Sample responses" can also be sensitive data

A `__files/order.json` file containing real account numbers or real customer details still poses a risk if packaged into a stubs JAR. Use **synthetic data** matching the schema for testing without reusing user-identifying data. Review fixtures like code.

## 6. HTTP security contracts: simulation differs from real authentication

Suppose `order-service` requires `orders:read` to read an order. The consumer needs to know how to handle:

| Scenario | Possible committed HTTP response | What consumer must verify |
| --- | --- | --- |
| Missing credential | `401 Unauthorized` | Client prompts login/refreshes token properly |
| Valid identity, missing permission | `403 Forbidden` | Client does not proceed with unauthorized action |
| Authorized and order exists | `200 OK` | Client parses body per schema |
| Authorized but order missing | `404 Not Found` | Client understands business error code |
| Expired token | `401` or other response per API policy | Client handles bounded retry/refresh |

These statuses are **API design examples**; not every system handles credentials identically. With OAuth2/OIDC or mTLS, statuses and headers depend on your architecture and security policy.

### 6.1. Contract DSL for the missing-token branch

Example YAML describing a request **without `Authorization`** per an agreed API scenario:

```yaml
description: Read order when unauthenticated
request:
  method: GET
  url: /api/orders/42
response:
  status: 401
  headers:
    Content-Type: application/json
  body:
    code: UNAUTHENTICATED
    message: Authentication required
```

This describes the response when a request omits credentials in the designed test. However, **a contract without a matcher requiring the header to be absent does not necessarily generate a WireMock mapping matching only requests without Authorization**. If another `200` contract shares the same method/path without distinguishing criteria, both mappings can compete.

When an API has `200/401/403` branches on the same URL, **distinguish inputs intentionally** using request header/body matchers, test scenarios, or fixtures actually used by producer verification. Never use a stub returning `401` for every GET request and conclude client auth is thoroughly tested.

### 6.2. WireMock mapping example distinguishing a fake token

An illustrative WireMock HTTP mapping showing **success only when the test sends a fixed fake token**:

```json
{
  "name": "Authorized request in the test fixture",
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/42",
    "headers": {
      "Authorization": {
        "equalTo": "Bearer SYNTHETIC_ORDERS_READ_TOKEN"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "orderId": "ord-42",
      "status": "CONFIRMED"
    }
  }
}
```

**This is a WireMock fixture, not a JWT/OAuth verifier.** WireMock only compares header strings; it does not verify signatures, issuer, audience, expiration, or scopes of a real token. To return `401` for requests missing a token, you need a separate **clearly differentiated** mapping or an explicit test setup; a request not matching the `200` mapping may receive **WireMock's default 404**, not 401.

### 6.3. What contract tests can and cannot do

- **Can do:** verify the consumer sets headers and handles 401/403/200 responses per scenario; producer contract tests can catch wrong statuses/bodies when security paths actually run in the base class.
- **Cannot do alone:** verify JWT signatures, key rotation, tenant isolation, resource-level authorization, replay protection, audit policies, or gateway/WAF behavior.
- **Other tests needed:** security integration tests exercising the real `SecurityFilterChain`/gateway, role/scope/ownership tests, expired-token tests, and negative auth cases in controlled environments.

**If the producer base class disables security filters via test configuration or mocks all authentication**, generated contract tests may still verify HTTP response schemas yet **have not verified real authentication**. Document that scope clearly; never claim "the API is secure because contract tests pass".

## 7. Separating mock API access from stub administration rights

A consumer test needing to call `GET /api/orders/42` does not mean it needs permission to:

- Call `GET /__admin/requests` to read the entire request journal;
- Call `POST /__admin/mappings` to alter responses;
- Clear another test's scenario state;
- Read CI credential files;
- Connect to production APIs from inside the stub.

If WireMock serves business routes and the Admin API **on the same listener**, there is no privilege separation simply from consumers sending tokens to `/api/orders`. Admin privileges must be restricted at the **reverse proxy, network topology, runner isolation, or supported runtime admin-disablement** layer.

### Role separation conventions in a test environment

| Role | Needed permissions | Permissions to avoid |
| --- | --- | --- |
| Consumer client | Mocked business HTTP endpoints | Calling admin, writing mappings, or browsing request logs |
| Test fixture/setup process | Load mappings, reset state when needed | Accessing production secrets, unneeded external networks |
| Stub server process | Read artifacts/mappings, listen on restricted port | OS admin rights, writing entire workspace, calling production |
| CI orchestrator | Download artifacts, manage jobs, read test reports | Sharing write-capable registry credentials across all consumer jobs |
| Artifact registry token | **Read-only** for consumer CI | Publishing/overwriting producer stub artifacts |

A team may run both test fixtures and server in the same Java process, yet still must **shrink privileges outside the process**. Sharing a JVM is no excuse to default to root privileges or unrestricted networking.

### Wrong assumptions about HTTP statuses

By default, WireMock does not automatically return `401` for requests lacking Authorization. With no matching mapping, WireMock may return `404`. If an overly broad mapping matches only the path, unauthenticated requests **can still receive `200`**. Therefore, in consumer tests, assert **the right mapping and right response**; never use mock server responses to infer production authentication enforcement.

## 8. Artifact registries and stub sources: restrict privileges before the server opens a port

Stub Runner can fetch stubs JARs from a local repository (`LOCAL`), an artifact registry (`REMOTE`), or the classpath (`CLASSPATH`). **Where artifacts come from** is part of the trust surface:

```text
Producer contract + code revision
       -> producer verification PASS
       -> stubs artifact: group:artifact:version:stubs
       -> registry with provenance/digest
       -> consumer CI resolves exact artifact
       -> Stub Runner / WireMock loads mappings
```

A malicious or wrong-revision artifact can cause the stub to serve unexpected data, inject abnormal response headers, or load/run extensions via system configuration mechanisms. **Never treat stubs JARs from untrusted sources as harmless data.**

### Minimum safeguards

1. Pin **group, artifact, version, classifier**, and allowed registries; never arbitrarily use `latest`/version ranges in release gates.
2. Verify **SHA-256 or checksum/attestation** against the artifact published by producer CI.
3. Prefer immutable release repositories; manage SNAPSHOTs/candidates separately.
4. Consumer CI holds **read-only** rights; never grant publish/overwrite access to producer artifacts.
5. Registry credentials live in CI secret stores, Maven settings, or Gradle credentials; never in contract DSL, logs, or URLs.
6. Reduce outbound privileges of the process after artifacts are downloaded, if workflow design allows.
7. Allow only explicitly reviewed **extensions, transformers, or plugin classes**.

### Groovy contracts are not static JSON data

**Groovy DSL can execute expressions/scripts during contract generation**, so untrusted Groovy sources should never be fetched and evaluated on a CI runner with access to production secrets or the full internal network. YAML DSL is more declarative data, yet **does not make the entire build tool/plugin chain automatically safe**.

When accepting contract PRs from external contributors, evaluate **source trustworthiness and CI permissions**. You can run generation/verification inside an isolated runner, withhold secrets from untrusted pull requests, control dependencies/extensions, and publish only after review + producer verification.

### `LOCAL` also carries risks

Artifacts in the local Maven repository may be left behind by another job rather than the target producer version. A stale `LOCAL` stub causes false passes, while a poisoned artifact may not come from the official publisher. Strict CI can use **per-job isolated local repositories** and verify digests instead of sharing `~/.m2` indiscriminately.

## 9. Outbound restrictions: stubs must not become proxies to real systems

WireMock includes features like **proxying** or extensions/transformers for dynamic responses. When tests only need sample responses from contracts, those features are usually **unnecessary**.

### Risks of proxy mappings

A mapping configured to forward requests to a real host can:

- Accidentally forward `Authorization` or bodies with sensitive data to production services.
- Cause consumer tests to hit real endpoints, mutating state outside the test environment.
- Hide differences between mock and producer, making tests non-reproducible.
- Open paths to internal networks, metadata endpoints, or places the test runner is forbidden to reach.

**Never blindly load mappings containing externally supplied proxy/forward URLs.** If tests need to simulate network failures or proxy a sandbox service, enforce egress allowlists, synthetic credentials, fixed hosts, and review mappings/extensions.

### Desired egress model

| Stage | Minimum egress |
| --- | --- |
| Producer/CI downloading dependencies | Only required artifact registries via managed connections |
| Stub Runner resolving stubs | Only the registry holding the exact stubs artifact |
| WireMock serving static mappings | **Usually no outbound needed** |
| Consumer tests calling stub | Internal test network/loopback only; avoid calling production |
| Test teardown/reporting | Only approved artifact/log storage endpoints, if needed |

If you separate the **artifact download step** from the **server execution step**, the container serving static mappings can have much stricter egress limits. A standard Docker `--network` or internal Kubernetes Service **does not automatically block outbound traffic**; verify actual egress policies/firewalls.

### Metadata/localhost are not test targets

A mapping/test could contain internal URLs or cloud VM metadata addresses. Keep such addresses out of proxy mappings; **block egress** to metadata services and unneeded network ranges per infrastructure policy. When debugging request forwarding is required, use an authorized sandbox endpoint without pulling tokens or config from real environments.

## 10. Process privileges on developer workstations and CI runners

Even when a mock binds only to loopback, the process still holds the permissions of the OS account running it. If the CI user can read `~/.aws/credentials`, the Docker socket, or multiple projects' source code, a buggy or malicious extension can cause damage far beyond a stub test.

### Least-privilege principles

- Run under a **non-root/non-admin account** when supported by the runtime/container.
- Never grant the Docker socket, broad Kubernetes service-account tokens, or unnecessary host filesystem mounts.
- Mount **mappings and response files read-only** when runtime modification is unneeded.
- Provide a **job-scoped temporary directory** with minimal write permissions; remove it upon completion.
- Never share writable workspaces/Maven caches with untrusted PRs.
- Cap CPU, RAM, processes, and file descriptors so a misbehaving test cannot impact shared hosts.
- Scope each test job's lifecycle rather than leaving admin servers open after jobs finish.

**Resource limits do not replace privilege limits.** A stub capped at 512 MiB RAM can still read secret files if the OS user has permission. Conversely, a read-only root filesystem does not block network access if egress is unrestricted.

### "Running non-root" also needs runtime verification

A Java image may be built to run non-root, yet some images or extensions expect to write to fixed paths. Arbitrarily forcing a UID can cause permission failures. The fix is not reverting blindly to root, but **adding minimal writable temp volumes where needed, fixing ownership at image build time, and testing startup**.

## 11. Docker: restricting host ports, filesystem, and capabilities

In a lab running standalone WireMock under Docker, separate these controls:

- **Network:** place the container in a dedicated test network and publish host ports **on loopback only**.
- **Filesystem:** read-only image/mappings; only `/tmp` writable as needed.
- **Capabilities:** drop unnecessary Linux capabilities and block privilege escalation.
- **Artifact:** use a pinned image version/digest, never accidentally `latest`.
- **Lifecycle:** remove the container when tests finish.

Example **Linux/macOS shell with a Linux Docker container**:

```bash
# Create the test network only if it does not already exist.
docker network create contract-test-net

# Illustrative deployment command; replace image digest with a verified value.
docker run --rm --name order-stub \
  --network contract-test-net \
  -p 127.0.0.1:8089:8080 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=64m \
  --memory 512m --cpus 1 \
  -v "${PWD}/wiremock:/home/wiremock:ro" \
  wiremock/wiremock@sha256:<PINNED_IMAGE_DIGEST>
```

**This is an illustrative template, not an executed command:** you must prepare `wiremock/mappings`, verify the image tag/digest, file permissions, exact writable paths needed by that image, and how Docker Desktop handles volume paths on Windows. An image might require a writable directory other than `/tmp`; if so, provide a minimal writable volume at that exact path rather than dropping `--read-only` altogether.

### Three easy misconceptions

1. `-p 127.0.0.1:8089:8080` restricts the **host-published port** to host loopback, yet **other containers on the same Docker network** can still reach **container port 8080**. Control membership of the test network.
2. `--network contract-test-net` is an isolated bridge network by default, yet **does not automatically block outbound internet access**. If zero egress is required, apply network/firewall policies or an appropriate internal network mode.
3. `--read-only` and `--cap-drop ALL` reduce privileges, yet **do not authenticate HTTP clients** or block the Admin API over the exposed port.

### Never mount the Docker socket

A mount like `/var/run/docker.sock` gives the container control over the host Docker daemon, typically equivalent to vast privileges. An HTTP stub does not need that privilege to return JSON. Never use `--privileged` or mount the entire project/host home directory just to load a few mappings.

### Docker container as a sidecar for consumer tests

If consumer tests also run inside `contract-test-net`, use the service/container name and **container port 8080** instead of the host's `127.0.0.1:8089`:

```text
Consumer running on host:
  http://127.0.0.1:8089

Consumer running in another container on the same Docker network:
  http://order-stub:8080
```

`127.0.0.1` inside the consumer container points to **the consumer container itself**, not the WireMock container or Docker host. Confusing network namespaces is a common cause of `Connection refused`.

## 12. Kubernetes: restricting ingress and egress of the stub Pod

In Kubernetes-based CI, WireMock/Stub Runner may run in a Pod alongside a consumer test Pod. Here, **loopback** only works if they share the **same Pod/network namespace**; other Pods calling it need an internal address/Service and suitable listener.

A `NetworkPolicy` for the WireMock Pod can restrict **ingress exclusively to the consumer test Pod** and **deny egress** once mappings are already present:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: order-stub-test-only
  namespace: contract-ci
spec:
  podSelector:
    matchLabels:
      app: order-stub
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: checkout-contract-test
      ports:
        - protocol: TCP
          port: 8080
  egress: []
```

**Explanation:**

- The policy applies only to Pods with `app=order-stub` in namespace `contract-ci`.
- Ingress is permitted from Pods selected by `app=checkout-contract-test` **in the same namespace** to TCP port 8080.
- `egress: []` grants no outbound paths for the selected Pod; suitable when stubs are already in the image/volume and the stub server fetches no further dependencies.

**This is an illustrative policy requiring verification against your actual CNI/network plugin.** Kubernetes NetworkPolicy only takes effect if the networking layer enforces it; Pod labels are not user authentication. Anyone permitted to create Pods and pick labels in the namespace may need additional RBAC/namespace isolation. An ingress rule for the WireMock port also **does not separate the Admin API from the business API** when they share a port.

### If Stub Runner must download artifacts at runtime

`egress: []` can cause `REMOTE` stubs JAR resolution to fail because registry/DNS calls are blocked. Two options:

1. **Pre-download** in a trusted CI step, verify checksums, and bake/bind-mount into the Pod; the serving Pod needs no egress.
2. Grant a **minimal egress allowlist** for DNS and the artifact repository during fetch, and verify the policy opens no broader external network.

Which option fits depends on your topology. Never add `to: 0.0.0.0/0` to fix artifact resolution errors when the goal is restricting outbound traffic. Inspect actual **service endpoints, DNS, proxies, and network policies**.

### Pod security context

A Pod/container running a mock server should consider settings such as:

```yaml
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL
  seccompProfile:
    type: RuntimeDefault
```

This is a **container-level `securityContext` snippet**, not a complete Kubernetes Pod manifest. `runAsNonRoot` may require an image with a non-root user or setting an explicit `runAsUser`. Writable temporary volumes, resource limits, service account permissions, and pinned image digests must still be configured. Never put Kubernetes admin credentials into container environments just so Stub Runner can read artifacts.

## 13. Shared stub servers and test isolation

Some teams want a long-running WireMock server shared across consumer jobs to cut startup time. That model raises risks:

- Test A resets mappings/scenarios, causing Test B to fail randomly.
- The request journal mixes data across teams and is easily cross-read.
- A high-priority mapping added by Test A changes Test B's responses.
- Old/new artifact versions coexist without consumers knowing which version the server is serving.
- Multiple callers can hit `/__admin` if the admin port is unprotected.

**Prefer one stub instance per job** (in-process, ephemeral container, or ephemeral Pod) with its own port/namespace and temp directory. Use a shared stub server only with clear justification and isolation controls:

| Aspect | Requirement when sharing a server |
| --- | --- |
| Artifact version | Never swap mappings mid-job without version isolation |
| Admin API | Only trusted fixtures/admins have access; consumers generally have none |
| State and request journal | Prevent one job from reading/resetting another job's state |
| Network | Only approved CI namespaces/groups |
| Data | Synthetic only; delete/bound retention |
| Logs | Separate per job/tenant and redact sensitive data |
| Fault isolation | One failing test must not mutate state for others |

Without these guarantees, speed gains rarely outweigh non-reproducible results and data leak risks.

## 14. CI security: test execution rights differ from artifact publish rights

Producer and consumer pipelines hold different responsibilities:

```mermaid
flowchart LR
    A[Producer CI] -->|Verify contracts| B[Producer tests]
    B -->|Pass| C[Publish signed/versioned stubs]
    C --> D[Artifact registry]
    D -->|Read-only token| E[Consumer CI]
    E -->|Resolve exact stub| F[Ephemeral Stub Runner]
    E -->|Run client tests| F
    F --> G[Restricted logs + reports]
```

**Separate permissions:**

- **Producer CI:** permitted to publish into the exact artifact namespace only after verification passes.
- **Consumer CI:** permitted only to read required artifacts; unable to overwrite producer stubs.
- **Pull request workflows from untrusted sources:** must not reach release secrets/production networks by default.
- **Release jobs:** verify producer verification reports, artifact digests, consumer tests, and deployed artifact identity.

### Minimal rule for GitHub Actions or similar platforms

A workflow that only checks out code/runs tests without modifying the repository can reduce token permissions to **read**:

```yaml
permissions:
  contents: read
```

This is an illustrative **GitHub Actions workflow-level permissions** snippet, insufficient on its own to protect the whole job. For private artifact registries, credentials must come from a secrets manager and be granted only to trusted jobs. Never use fork PRs to execute untrusted Groovy contracts on runners holding production credentials.

### Test reports also require control

JUnit XML reports, HTTP traces, WireMock request journals, and attachments can contain URLs, headers, payloads, and test account details. Apply masking/redaction, retention, and artifact read permissions. **Never treat uploading test reports as harmless** if reports could hold secrets from real requests.

## 15. Stub Runner consumer tests: verify the right server, not just responses

A Spring Boot consumer can use `@AutoConfigureStubRunner` to load a producer-verified stubs JAR. Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties =
    "clients.orders.base-url=http://localhost:9090")
@AutoConfigureStubRunner(
    ids = "com.example:order-service:1.7.0:stubs:9090",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderConsumerContractTest {

    @Autowired
    OrderClient orderClient;

    @Test
    void canReadOrderFromStub() {
        OrderDto result = orderClient.findById("42");
        assertThat(result.status()).isEqualTo("CONFIRMED");
    }
}
```

`OrderClient`, `OrderDto`, and `clients.orders.base-url` are **illustrative application types/properties**, not APIs auto-generated by Stub Runner. The test is meaningful when:

1. `1.7.0:stubs` passed producer verification and was installed into the local repository of **the exact test job**.
2. Stub Runner actually loaded the WireMock mapping for `GET /api/orders/42`.
3. The consumer's real HTTP client actually called server/port `9090`.
4. Assertions verify expected outcomes and error branches.
5. The stub's network is reachable only by authorized test processes.

**Limitation:** `@AutoConfigureStubRunner` is not a tool for configuring Kubernetes firewalls, Docker capabilities, OAuth2 policies, or OS privilege systems. Those security policies must be enforced in the stub runtime environment outside the annotation.

### Verify security contracts with two separate layers

| Layer | Specific test | Valid conclusion |
| --- | --- | --- |
| Consumer + stub | Client handles `401 UNAUTHENTICATED` and `403 FORBIDDEN` | Client understands simulated error responses |
| Producer + verifier | Producer implementation returns contract responses | HTTP/security behavior ran within **base class scope** |
| Security integration | JWT validation, permissions, resource ownership, gateway/filters | Real authentication/authorization rules verified |
| Infrastructure policy | Pod/firewall/container blocks unauthorized callers or egress | **Network and privilege** boundaries are effective |

Results from these four layers complement one another. Never use a `401` WireMock test to claim Kubernetes NetworkPolicies are secure or real token issuers are verified.

## 16. How to verify network and privilege boundaries with tests

**Define permitted flows upfront:**

| Actor | Target | Allowed? | Evidence |
| --- | --- | --- | --- |
| Consumer test in same job | `GET /api/orders/42` | **Yes** | Receives expected stub response |
| Other host/Pod outside test scope | Stub port | **No** | Connection refused/timed out per policy |
| Normal consumer test | `/__admin` over consumer network path | **No** | Blocked before reaching WireMock |
| Stub serving static mappings | Internet/production API | **No** | Egress test/firewall logs |
| Consumer CI | Artifact registry read endpoint | **Yes** if permitted | Resolves exact artifact digest |
| Consumer CI | Artifact registry publish endpoint | **No** | Upload permission denied |
| Stub process | Production secret files | **No** | OS permissions, mounts, and service-account scope |

### Checking the listener on the test machine

After starting standalone WireMock configured to bind to loopback:

```bash
# Linux: inspect actual processes/listeners.
ss -lnt

# Test valid mock endpoint from the authorized host itself.
curl -i --max-time 3 http://127.0.0.1:8089/api/orders/42
```

On Windows PowerShell, you can check:

```powershell
Get-NetTCPConnection -LocalPort 8089 -State Listen
```

Inspect **LocalAddress**; if it is `0.0.0.0` instead of `127.0.0.1`, review the bind address and firewall. For IPv6, inspect the corresponding listener. **Port-listing commands do not prove firewalls or container networks are blocked.**

### Negative network tests

Inside an **environment owned by your team and authorized for testing**, from an unauthorized host/Pod, attempt to connect to the **known test host/Service address**. The expected result is connection failure per network policy. Never arbitrarily scan corporate networks or endpoints outside your management scope.

When using Kubernetes, create a **test Pod from a disallowed namespace or label** and verify it cannot call the WireMock Service, while the authorized consumer Pod can. Confirm the CNI supports NetworkPolicy and inspect both ingress and egress in multi-component topologies.

### Checking file and process permissions

Inside the test container/Pod:

- Inspect actual user ID/UID and group, ensuring it does not run as root without an approved exception.
- Inspect mounted volumes: only mappings/configs, no Docker socket, host home directory, or unneeded secret mounts.
- Inspect capabilities/`securityContext` and writable directories.
- Check whether the process needs egress; if serving static mappings, cut egress and run smoke tests.
- Confirm containers/jobs terminate and temporary resources are cleaned up after tests.

**Never attempt to read a real production credential as a "security test".** Use a dummy canary file in a sandbox or policy review to verify filesystem boundaries.

## 17. Security smoke tests in CI: verify policies, not only functionality

A quality gate can run these minimum checks:

```mermaid
flowchart TD
    A[CI creates isolated test environment] --> B[Resolve exact verified stub]
    B --> C[Check SHA-256 + registry permissions]
    C --> D[Start stub non-root, restricted network]
    D --> E{Authorized consumer reaches mock?}
    E -->|No| X[Fail: network/port/config]
    E -->|Yes| F{Unauthorized caller blocked?}
    F -->|No| Y[Fail: ingress isolation]
    F -->|Yes| G{Admin API unexposed on consumer path?}
    G -->|No| Z[Fail: admin exposure]
    G -->|Yes| H{No outbound outside allowlist?}
    H -->|No| Q[Fail: egress leakage]
    H -->|Yes| I[Run consumer assertions]
    I --> J[Redact logs, tear down resources]
```

### Practical smoke-test checklist

1. **Before startup:** verify artifact digest, image version, namespaces/ports/volumes/secrets.
2. **After startup:** confirm process runs under expected UID and listener uses expected address.
3. **Positive ingress:** authorized consumer calls stub successfully with sample request.
4. **Negative ingress:** caller outside network/test scope is blocked.
5. **Admin:** consumer network cannot administer mappings; trusted fixtures/setup still reset state if needed.
6. **Egress:** serving process cannot reach production/internal resources outside allowlist.
7. **Secrets/logging:** fake tokens stay out of public test reports; no production credentials generated.
8. **Teardown:** stub server/port, namespace, temporary volumes, and test state are cleaned up.

This is not a built-in automated security scanner from Spring Cloud Contract; teams must implement job checks matching their actual Docker/Kubernetes/firewall/runtime setup. **If a network policy prevents valid tests from running**, that is a configuration bug to fix in the minimal allowlist—never open the entire network as a temporary workaround and leave it that way.

### Distinguishing functional errors from policy errors

| Outcome | Possible explanation | What to do |
| --- | --- | --- |
| Consumer call to mock fails | Wrong port, overly strict firewall, Stub Runner did not load mapping | Check listener/port and request path |
| Unauthorized caller succeeds | Bind/network policy/Service exposure too broad | Check firewall, NetworkPolicy, host-published ports |
| Consumer can call `/__admin` | Admin exposure | Block direct access or place behind auth proxy |
| Static-mapping stub reaches internet | Egress unrestricted | Inspect CNI/firewall/bridge network |
| 401 auth test passes yet real JWT test fails | Stub only simulates status | Add/fix security integration tests |
| Pipeline reports PASS without policy checks | Missing infrastructure evidence | Mark security scope as unverified |

## 18. Real-world failure case: stub accidentally opened to the entire LAN

### Symptom

A developer starts a WireMock server on a CI machine listening on `0.0.0.0:9090`. Consumer tests pass, yet another host on the internal network can also reach `http://ci-host:9090/__admin/mappings`.

If the Admin API is enabled without protection, other hosts can view/modify mappings or the request journal. This is a **test infrastructure exposure** flaw, not a Spring Cloud Contract Groovy DSL bug.

### Root cause analysis

1. **Bind address:** server listens on every interface in the network namespace.
2. **Firewall:** port `9090` does not restrict callers.
3. **Admin API:** shares the same listener with business stub endpoints.
4. **CI lifecycle:** server stays running after the job instead of tearing down.
5. **Data:** request journal may retain fake headers/tokens or prohibited data.

### Scope-appropriate remediation

- If consumer runs **on the same host**: bind loopback and block off-host inbound traffic.
- If consumer runs **in another container/Pod**: use a dedicated network/namespace, ingress allowlists, and verify admin is unreachable over the consumer network.
- If a **shared server is unavoidable**: add an authenticating reverse proxy blocking `/__admin` for ordinary callers and block direct bypass paths.
- Use read-only registry credentials, avoid storing tokens in request journals, and cap log retention.
- Add teardown/quota/timeout enforcement and negative network tests to the pipeline.

**Case takeaway:** An HTTP contract test returning `200` provides zero proof that the stub's network and privileges are restricted. Only **network/policy tests** verify that boundary.

## 19. Hands-on lab: isolating the order-service stub

### Context

`checkout-service` has a consumer test reading orders from `order-service`. The producer verified its contracts and published `com.example:order-service:1.7.0:stubs`. The team wants to practice two setups:

1. **Development:** standalone WireMock and consumer client run on the same host, blocking access from other hosts.
2. **CI:** consumer test Pod and WireMock Pod live in namespace `contract-ci`; only labeled Pods may call the stub, and the stub serves **static mappings** with no outbound access needed.

The goal is not testing real production systems. All URLs, tokens, and data are **synthetic**, and network tests run strictly inside a team-managed sandbox.

### Part A — Write a clear HTTP behavior contract

Source Groovy DSL for the producer:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Look up confirmed order'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body([
            orderId: 'ord-42',
            status: 'CONFIRMED'
        ])
    }
}
```

This contract protects the sample HTTP response; **it does not protect API authentication**, as it declares/checks no tokens or security filters. If the real endpoint requires login, producer verification must configure requests/base classes to reproduce that policy or add separate security-focused contracts/tests.

### Part B — Using a WireMock mapping for the 401 branch

To avoid confusing unmatched 404 with business 401, a **lab-specific** WireMock mapping can model **missing `Authorization`**:

```json
{
  "name": "Unauthenticated read order",
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/42",
    "headers": {
      "Authorization": {"absent": true}
    }
  },
  "response": {
    "status": 401,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "code": "UNAUTHENTICATED"
    }
  }
}
```

**This is an illustrative WireMock mapping, not auto-generated output from Part A's Groovy contract.** If two mappings share `GET /api/orders/42` on the server and the success mapping does not constrain Authorization, fix the contracts/mappings to prevent collisions. In an official Spring Cloud Contract flow, place the 401 case in the **source contract** and run producer verification rather than relying solely on a hand-written mapping and assuming the producer enforces 401.

### Part C — Local machine network verification

1. Start the mock server on **loopback** using supported standalone WireMock flags.
2. Confirm the socket listens only on `127.0.0.1` (or chosen IPv6 loopback).
3. Call the stub from the authorized client/test; confirm the response comes from the **loaded mapping**.
4. From a sandboxed caller **not sharing the host/network namespace**, confirm it cannot reach the test host's network address on that port.
5. Read `/__admin/requests` **only from an authorized admin host**, inspect recorded test data, and verify no real credentials exist.
6. Stop the process and verify the port is closed and files/logs do not outlive retention policy.

**Self-check point:** Loopback blocks inbound traffic from outside the namespace, yet **does not hide `/__admin` from another process on the same host**. Therefore, never run untrusted code under the same account/namespace as the stub when strict isolation is required.

### Part D — Docker/container restrictions

Apply `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, loopback host port, and read-only mappings volume as in section 11. Then answer:

- Is the image running non-root, or does a tailored image need building?
- Does the runtime write only to the provisioned writable temp volume?
- Does the container mount the Docker socket or host secrets?
- If the consumer is also a container, must it call `order-stub:8080` or `127.0.0.1:8089`?
- Can the stub server reach external networks? **Do not guess from `--network contract-test-net`.**

These questions force the learner to **inspect actual runtime behavior**, not just read Docker flags and mark PASS.

### Part E — NetworkPolicy in CI

1. Apply section 12's Kubernetes policy to the `app=order-stub` Pod.
2. Create an authorized consumer Pod `app=checkout-contract-test` in the appropriate namespace; verify it reaches port 8080.
3. Create a disallowed Pod in the sandbox; verify it **cannot** reach the stub.
4. Check that `egress: []` does not block unrelated pre-startup tasks; preload stubs if needed.
5. Verify the test Pod—not only the WireMock Pod—also lacks unnecessary access to production/internal services.
6. Record the CNI/plugin and enforced policies in the CI report.

To isolate network policy effects while debugging, edit only the **minimal allowlist** and revert under review. Never delete the entire policy and declare tests verified.

### Part F — Expected results

| Test | Evidence to prove |
| --- | --- |
| Authorized consumer calls HTTP stub | Receives response per loaded contract |
| Out-of-scope caller hits local-only host port | Blocked before reaching server |
| Ordinary caller hits WireMock Admin API over public/shared path | Blocked |
| Test with synthetic token | Leaks no production credentials |
| WireMock serving static mappings attempts outbound outside allowlist | Disallowed |
| Container process reads fake host secret outside granted volumes | Denied per policy |
| CI uses artifact `1.7.0:stubs` | Exact producer-verified version/digest |
| Stub returns simulated 401 | Consumer handles error code properly, **not treated as real JWT validation** |
| Post-teardown | Ports/Pods/temp state reclaimed |

## 20. Troubleshooting table for stub security issues

| Symptom | Possible cause | Investigation and fix |
| --- | --- | --- |
| Another host on LAN reaches stub | Bound to `0.0.0.0` or overly broad port publish/firewall | Check listener, host firewall, Pod Service/ingress |
| Business API blocked yet `/__admin` remains open | Filtered only business routes, admin path unrestricted | Block admin and direct bypass paths |
| WireMock request journal holds real token | Consumer CI used real credential or logs unredacted | Revoke token per policy, fix test fixture, limit retention |
| CI fails to resolve REMOTE artifact after denying egress | Registry/DNS missing from allowlist or needs preload | Separate download before serving; allowlist exact source |
| Stub server returns production data | Proxy mapping or client pointed to real backend | Check request destinations, mappings, egress, and credentials |
| Container fails to start after `--read-only` | Runtime needs a writable directory | Provide minimal writable temp volume |
| Container still runs as root | Unsuitable image user/`securityContext` | Use non-root image, UID, and proper volume permissions |
| NetworkPolicy declared yet out-of-scope caller succeeds | CNI not enforcing, wrong selector, or bypass path | Check enforcement, labels, Service/hostNetwork paths |
| Test passes on host, fails with connection refused in Docker | Wrongly used `localhost` across network namespaces | Use container DNS name/port or same Pod namespace |
| Two consumer jobs mutate the same mapping | Shared stub server and shared Admin API | Run ephemeral instances or separate jobs |
| Consumer 401 test passes while producer lacks security | WireMock simulates status; producer filters untested | Run producer/security integration tests |
| Consumer silently uses stale stub | Wrong artifact cache/version | Pin coordinates, verify digests, isolate local repo |
| Plugin/extension demands broad write or outbound rights | Custom extension violates least privilege | Review or remove extension; scope rights if needed |
| CI logs expose registry credentials | Printed URL/token in debug output | Redact, rotate credentials, narrow token scope |

### Safe investigation sequence

```text
1. Identify which process/Pod/container is serving the stub.
2. Identify the listener, host-published ports, and inbound network paths.
3. Check access to /__admin and ordinary client privileges.
4. Inspect request journal, logs, and fixtures for sensitive data.
5. Identify outbound destinations and artifact registry identity.
6. Read UID, capabilities, mounts, securityContext, and service account.
7. Verify artifact version/digest and contract verification provenance.
8. Run negative policy tests inside an authorized sandbox.
9. Fix root cause and re-run consumer + security smoke tests.
10. Revoke/rotate credentials if secret exposure is detected.
```

**Upon signs of real secret exposure, prioritize your organization's incident response process.** Clearing the local request journal cannot recall copies already written into CI logs or artifacts.

## 21. Checklist before running a stub process in CI

### Network boundaries

- [ ] Know whether consumer and stub run in the **same process, same host, same Docker network, or different Kubernetes Pods**.
- [ ] Bind address and port are verified directly, not merely assumed from configuration.
- [ ] Loopback preferred for same-host tests; minimal ingress allowlists used across hosts/Pods.
- [ ] WireMock ports are never published to the public internet or LAN without approved need.
- [ ] If business routes and `/__admin` share a port, the consumer's network path **forbids** unintended admin access.
- [ ] Checked for absence of direct bypass paths via host ports, Pod IPs, or Services.
- [ ] Negative ingress tests exist from an unauthorized caller.
- [ ] Egress checks ensure the mock server cannot accidentally proxy or call production/internal resources.
- [ ] For Kubernetes, CNI actually enforces NetworkPolicy; Pod labels, RBAC, and namespaces are controlled.
- [ ] For Docker, understand host loopback vs container networks; a test network is not an outbound firewall.

### Process and container privileges

- [ ] Stub server runs under a non-root/non-admin identity where possible.
- [ ] `--privileged`, Docker socket, `hostNetwork`, and broad service-account tokens are omitted when unneeded.
- [ ] Mappings and response files are mounted read-only if runtime updates are unneeded.
- [ ] Root filesystem is read-only or writable paths are strictly bounded to real needs.
- [ ] Linux capabilities are dropped; privilege escalation is blocked where supported.
- [ ] CPU/RAM, log retention, port lifecycle, and teardown are configured properly.
- [ ] Stub instances and request journals are never shared across untrusted jobs.

### Artifact sources and data

- [ ] Stubs JAR comes from an identified **producer contract source** with passing producer verification.
- [ ] Consumer CI fetches the exact `group:artifact:version:stubs` and checks checksum/provenance.
- [ ] Consumer registry token is read-only; publish rights belong to producer CI.
- [ ] Mutable `latest`/uncontrolled SNAPSHOTs are not used for release decisions.
- [ ] Untrusted Groovy contracts, custom WireMock extensions, or build scripts never run on runners holding broad secrets.
- [ ] Only test credentials and synthetic fixture data are used—never copied production data.
- [ ] Request journals and CI artifacts are redacted with restricted access and retention.
- [ ] If proxying/response templating exists, outbound targets and header/body leak risks are reviewed.

### Test evidence

- [ ] Real consumer client/listener actually calls **the right stub server** and asserts required responses/messages.
- [ ] `401`/`403` contracts are not mistaken for full JWT/OAuth/security verification.
- [ ] Producer contract tests traverse the intended implementation scope; security integration tests exist when needed.
- [ ] Authorized smoke tests connect, out-of-scope smoke tests are **blocked**, and Admin API is unexposed.
- [ ] CI fails or reports `INCOMPLETE` if artifacts, digests, test results, or mandatory policy tests are missing.
- [ ] Reports distinguish **contract interface quality** from **test infrastructure security**.
- [ ] After job completion, processes/ports, containers/Pods, temp files, and test state are reclaimed.

## 22. Conclusion and further reading

A Stub Runner/WireMock process can be functionally simple yet present multiple attack surfaces. Maintain **four independent boundaries**:

| Boundary | Question to answer |
| --- | --- |
| **Network** | Who can connect to the stub and Admin API? Where can the stub connect outbound? |
| **OS/container privileges** | What can the process read/write, and does it hold root, host sockets, or service accounts? |
| **Artifact sources and data** | Are stubs/extensions trustworthy? Do tests carry secrets or real responses? |
| **Scope of evidence** | Did tests merely simulate `401`, or verify real authentication/authorization? |

In practice, prefer **one short-lived stub instance per consumer test job**, load **exact-version and checksum-verified stubs artifacts**, restrict networking to job scope, never expose the Admin API publicly, run non-root with minimal filesystem access, use synthetic data, and reclaim resources immediately after tests.

Official references to check per version:

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/) — Contract Verifier, Stub Runner, contract sources, stub loading, and test configuration.
- [WireMock Documentation](https://wiremock.org/docs/) — standalone/server configuration, request matching, Admin API, request journal, and proxying.
- [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/) — ingress/egress selectors and CNI enforcement requirements.
- [Docker Networking](https://docs.docker.com/engine/network/) — network namespaces, bridge networks, and published ports.

CLI, Docker, Kubernetes, and Java examples in this lesson must be cross-checked against your project's **actual versions, network topology, and security policies**. Never substitute copying sample commands without verifying execution results for a real security policy.

**Remember:** Spring Cloud Contract helps **verify producer–consumer contracts**; WireMock/Stub Runner helps **simulate interfaces**. They **do not automatically isolate networks, enforce Admin API access control, protect secrets, or replace real security testing**. To keep mock servers safe in CI, enforce **least privilege, ingress/egress limits, trusted artifact governance, and positive/negative boundary tests**. A green consumer test is only valuable when it both consumes the right stub and avoids creating a test process with privileges or network reach beyond what is strictly necessary.
