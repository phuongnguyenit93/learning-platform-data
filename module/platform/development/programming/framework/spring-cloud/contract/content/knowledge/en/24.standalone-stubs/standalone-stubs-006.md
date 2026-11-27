# Using Stubs for Local Development or Ephemeral Environments

## 1. Why Run a Stub Independently?

In microservices systems, a team often wants to develop or test a **consumer** before the **producer** is finished, or when the producer depends on databases, brokers, and external services not present in the test environment. With **Spring Cloud Contract**, both sides agree on behavior using the **Groovy/YAML DSL**: the producer generates and runs contract verification tests, then packages the stubs. The consumer can use those stubs to make HTTP calls or receive messages in a test environment.

For example, **Checkout Service** needs to call **Inventory Service** to check stock:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

Response expected by Checkout:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

When developing locally on a workstation, the Checkout developer does not necessarily need to start the real Inventory Service. Instead, they can run a **standalone HTTP stub server** on `localhost:10080` and point Checkout's `InventoryClient` at it. An **ephemeral environment** for a pull request can use the same approach: deploy only Checkout alongside its required stubs, then run smoke/integration tests.

This lesson belongs to the **Standalone Stubs** chapter of the `SPRING_CLOUD_CONTRACT` module. The focus is **using stubs in local development or ephemeral environments**: preparing data, launching Stub Runner Boot or mapping-based WireMock, wiring consumers to stubs, managing versions, isolating environments, and reclaiming resources.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **embedded Stub Runner** running inside JUnit from **Stub Runner Boot** running as a standalone application.
2. Prepare a stub JAR from verified producer contracts.
3. Choose `LOCAL` or `REMOTE` for standalone stubs and know when classpath sources apply.
4. Distinguish **Stub Runner Boot's management port** from **WireMock stub ports**.
5. Use Docker to provision an isolated stub server for a workstation or pull-request environment.
6. Route a consumer's HTTP client to the right address from the host, a container, or an internal network.
7. Verify readiness, mappings, and the success/error branches the consumer actually relies on.
8. Design a controlled create–use–cleanup stub lifecycle without exposing servers to the internet.
9. Understand the boundaries: stubs do not replace producer verification, database integration, brokers, or end-to-end tests.

> **Principle:** use stubs to **isolate dependencies and verify interfaces**, not as proof that the real producer or the entire distributed system is working properly.

## 2. How Does a Standalone Stub Differ from Stub Runner in JUnit?

Components that are easily confused:

| Component | Where Does It Run? | Role |
|---|---|---|
| **Contract DSL** | Producer source or contract repository | Defines committed requests/responses or messages |
| **Generated producer tests** | Producer build/test context | Verifies whether the real implementation satisfies the contract |
| **Stub JAR** | Maven local repo or artifact repository | Contains packaged mappings and contracts |
| **Embedded Stub Runner in JUnit** | Inside the consumer test process | Downloads stubs, starts WireMock, and supplies ports to tests |
| **Stub Runner Boot (standalone)** | A separate process/container | Downloads stubs and runs WireMock servers callable by external consumers |
| **Direct standalone WireMock** | A separate process/container | Uses existing HTTP mappings without Stub Runner's full Maven stub resolution |

**Embedded Stub Runner** typically uses `@AutoConfigureStubRunner` or `StubRunnerExtension` in tests. The test framework manages the stub lifecycle and can inject dynamic ports via `@StubRunnerPort`.

**Stub Runner Boot** fits when you need a server living **outside the JUnit process**, so an IDE, manually launched apps, browsers/`curl`, or a group of apps in an ephemeral environment can all share it.

**Standalone WireMock** fits when you already have JSON mappings and simply want to serve them directly. However, if you want to pull stubs by Maven coordinates from Nexus/Artifactory or `~/.m2`, Stub Runner Boot provides the dedicated Spring Cloud Contract workflow.

### 2.1. "Standalone" Does Not Mean "Real Producer"

Stub Runner Boot can start WireMock without loading Inventory Service's controllers, services, repositories, or database. It returns responses based on mappings generated from contracts. A request lacking a matching mapping can return `404` even though the real producer would respond differently.

To detect drift between mappings and implementation, **the producer must keep running generated contract tests** in its own build.

## 3. Flow from Contract to Test Environment

~~~mermaid
flowchart TD
    A["Producer: Groovy/YAML contract"] --> B["Generate producer tests"]
    B --> C{"Producer verification passed?"}
    C -- "No" --> X["Do not publish stub"]
    C -- "Yes" --> D["Package -stubs.jar"]
    D --> E["Maven local or shared repository"]
    E --> F["Stub Runner Boot: LOCAL / REMOTE"]
    F --> G["WireMock: one HTTP port per producer"]
    G --> H["Checkout points InventoryClient to stub"]
    H --> I["Manual test / smoke test / integration test"]
    I --> J["Clean up after use"]
~~~

The two testing tracks remain independent yet complementary:

- **Producer verification:** Contract Verifier generates producer-side tests and checks responses from real producer code / producer test context.
- **Consumer verification:** Consumer sends real requests from its own client to the stub and verifies business outcomes when receiving sample responses.

**A running stub server** does not mean both tracks ran. Therefore, when provisioning an ephemeral environment, record **which artifact version** the stub is using and which checks that artifact passed in the producer pipeline.

## 4. End-to-End Example: One Inventory API with Two Scenarios

To use a stub meaningfully, start with source contracts representing what Checkout genuinely needs.

### 4.1. Groovy Contract for an In-Stock SKU

Example file `src/test/resources/contracts/inventory/get_available_inventory.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_available_inventory')

    request {
        method GET()
        urlPath('/api/inventory/SKU-100')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-100',
            available: true,
            quantity: 8
        )
    }
}
~~~

This interaction generates a WireMock mapping matching `GET /api/inventory/SKU-100` and returning the corresponding JSON.

### 4.2. Groovy Contract for a Missing SKU

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_not_found')

    request {
        method GET()
        urlPath('/api/inventory/SKU-404')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'INVENTORY_NOT_FOUND',
            message: 'SKU not found'
        )
    }
}
~~~

Checkout can use the `404` response with `code` to display a business error. Simply seeing HTTP `404` because WireMock failed to match a request is **not** proof that the producer exposes an `INVENTORY_NOT_FOUND` error.

### 4.3. Equivalent YAML DSL

~~~yaml
name: get_available_inventory
request:
  method: GET
  urlPath: /api/inventory/SKU-100
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-100
    available: true
    quantity: 8
~~~

The Groovy and YAML examples are only for learning how to read contracts. In a real project, never keep **duplicate active definitions for the same interaction** unintentionally. Maintain **one canonical contract source**.

### 4.4. What Does the Stub Represent?

With the contracts above, the stub typically enforces **request matching** and **sample responses**:

- Method `GET`.
- Path `/api/inventory/SKU-100`.
- `Accept` header when constrained by the contract.
- Status `200`, JSON media type, body containing `available`/`quantity`.
- Case `SKU-404` with `404` and error body.

The stub does not compute stock from a database and does not recognize arbitrary SKUs beyond declared matchers. If the consumer needs dynamic values or multiple edge cases, design appropriate contracts/matchers/stub scenarios rather than assuming it executes Inventory Service business logic.

## 5. Preparing the Stub Artifact from the Producer

With Spring Cloud Contract, the producer build can produce an artifact such as:

~~~text
com.example:inventory-producer:1.2.3:stubs
~~~

The Maven classifier filename is typically:

~~~text
inventory-producer-1.2.3-stubs.jar
~~~

Usually the JAR places mappings and contracts in a layout supported by the plugin and Stub Runner, such as under `META-INF/.../mappings`. The primary `inventory-producer-1.2.3.jar` file is **not** the stub classifier JAR.

### 5.1. What to Confirm Before Using

1. The producer has Groovy/YAML contract sources for the interactions under test.
2. The plugin and generator actually produced **generated producer tests**.
3. Those tests **executed**; the build is not green because of skipped tests or 0 tests.
4. Mappings were generated and packaged into `-stubs.jar` under the right Maven coordinates.
5. The artifact version and classifier are known, e.g., `1.2.3:stubs`.
6. The artifact has been **installed locally** or **published** matching the chosen mode.

Example Maven commands **valid only if the producer configured the plugin and attached the stub artifact**:

~~~bash
# Verify producer; do not treat BUILD SUCCESS with 0 tests as sufficient.
./mvnw -B clean verify

# If the project is configured to install the stub artifact:
./mvnw -B install
~~~

A standard Java project will not automatically produce `-stubs.jar` merely by running `mvn install`. If the artifact is missing, inspect the producer plugin configuration rather than tweaking Stub Runner to mask the issue.

### 5.2. Never Put Artifacts Lacking Provenance Into Ephemeral Environments

If someone writes a WireMock JSON file by hand to test a UI, that can still be useful for development, but label it clearly as a **manual stub**. Never label it "verified by producer verification" if it did not originate from contracts or pass producer tests. Keeping this distinction prevents false confidence during demos or PR reviews.

## 6. Choosing the Stub Source: CLASSPATH, LOCAL, and REMOTE

Stub Runner uses `StubRunnerProperties.StubsMode` to decide where to fetch stubs:

| Mode | Source | Best Fit |
|---|---|---|
| `CLASSPATH` | Stub JAR/mappings already on the classpath | Embedded tests where test dependencies are already resolved |
| `LOCAL` | Local Maven repository such as `~/.m2/repository` | Developer built/installed the producer on the same machine |
| `REMOTE` | External repository like Nexus/Artifactory or supported location | CI, cross-team artifact sharing, ephemeral environments |

**CLASSPATH is the documented default**, but in a standalone Stub Runner Boot container, your project's stub JAR is **not automatically on the image's classpath**. Therefore, standalone workflows typically select `LOCAL` or `REMOTE` explicitly.

Stub IDs normally follow the convention:

~~~text
groupId:artifactId:version:classifier:port
com.example:inventory-producer:1.2.3:stubs:10080
~~~

- `groupId` and `artifactId` identify the producer artifact.
- `version` pins the interface version.
- `classifier` is usually `stubs`.
- `port` is the **WireMock** port started for that producer, not Stub Runner Boot's management port.

Version, classifier, and port can be omitted using default rules; omitting version often causes the resolver to use `+` to fetch the latest version. **In CI and reproducible preview environments, pin an explicit version** instead of `+`.

### 6.1. Do Not Confuse REMOTE with the Producer's URL

If `repositoryRoot` is `https://repo.example.test/repository/maven-releases/`, that is the **artifact repository**. It is not the real Inventory Service URL, nor is it where Checkout sends inventory requests.

Checkout must point to the **WireMock HTTP port** opened by Stub Runner Boot.

### 6.2. When to Use stubs://file://?

Spring Cloud Contract can use `stubs://file://...` to load stub definitions from a directory via a supported downloader, yet the mode required is still **REMOTE**, not Maven `LOCAL`. You must adhere to the layout and URI syntax supported by your plugin version; do not assume any arbitrary folder of JSON files will be recognized by the resolver.

## 7. Standalone Execution Options: Docker, Boot App, or WireMock

There are three common options:

| Approach | Advantages | Limitations |
|---|---|---|
| **Stub Runner Boot Docker image** | Runtime isolation, easy creation and teardown, fits local/preview | Must supply artifact access, manage ports, and container networking |
| **Self-built/run Stub Runner Boot** | Customizable Spring config and service discovery | Requires packaging a compatible app; version-dependent |
| **Standalone WireMock with direct mappings** | Simple when JSON mappings already exist | You manage mapping sources, versioning, and copy/sync yourself |

**Important version note:** Current Spring Cloud Contract documentation states that **the executable Stub Runner Boot JAR is not published from version 4.1.6 onward** due to artifact publishing tooling limits; the documentation recommends using the Docker image or building the application from source. Accordingly, **do not write modern guides assuming a fresh fat JAR can always be downloaded from Maven Central**.

Legacy `java -jar stub-runner.jar ...` commands apply only when you have a **compatible existing JAR** or built the Boot application yourself. Spring Cloud CLI `spring cloud stubrunner` is a historical option whose CLI/version availability must also be confirmed before use.

### 7.1. Why Does Docker Usually Fit Ephemeral Environments Well?

A container can:

- Pull the exact pinned version of stubs.
- Run one or more WireMock servers.
- Expose HTTP ports to Checkout or test tools.
- Be recreated declaratively from pipeline configuration.
- Be deleted when a pull request closes or a job finishes.

**There is no need to keep stub servers running forever.** For preview environments, tie their lifetime to the PR, CI job, or developer work session.

## 8. Using Stub Runner Boot Docker with REMOTE Stubs

Illustrative environment parameters:

| Value | Meaning |
|---|---|
| `com.example:inventory-producer:1.2.3:stubs` | Artifact verified and published by the producer |
| `https://repo.example.test/repository/maven-releases/` | Repository storing stub artifacts (sample URL) |
| `10080` | Inventory stub's WireMock HTTP port |
| `8750` | Stub Runner Boot management port per docs examples |
| `springcloud/spring-cloud-contract-stub-runner` | Image name used in some official Docker examples; verify active registry/tags |

Example command for Bash/POSIX shell (replace `<compatible-tag>` and the repository URL with real values; **illustrative** command, not executed in this lesson):

~~~bash
docker run --rm --name inventory-stubs \
  -e SPRING_CLOUD_CONTRACT_STUBRUNNER_IDS="com.example:inventory-producer:1.2.3:stubs:10080" \
  -e SPRING_CLOUD_CONTRACT_STUBRUNNER_STUBS_MODE=REMOTE \
  -e SPRING_CLOUD_CONTRACT_STUBRUNNER_REPOSITORY_ROOT="https://repo.example.test/repository/maven-releases/" \
  -p 127.0.0.1:8750:8750 \
  -p 127.0.0.1:10080:10080 \
  springcloud/spring-cloud-contract-stub-runner:<compatible-tag>
~~~

**Explanation:**

1. `SPRING_CLOUD_CONTRACT_STUBRUNNER_IDS` selects the artifact and WireMock port `10080`.
2. `...STUBS_MODE=REMOTE` tells the resolver to fetch stubs from the repository.
3. `...REPOSITORY_ROOT` is the artifact distribution repository.
4. `-p 127.0.0.1:8750:8750` maps the **management port** to the host loopback.
5. `-p 127.0.0.1:10080:10080` maps the **stub port** to loopback.
6. `--rm` removes the container on stop; `--name` makes it easy to inspect logs or stop it.
7. `<compatible-tag>` must be an actually existing image tag compatible with your project's repository/plugin.

Spring Cloud Contract documentation shows both `spring-cloud/spring-cloud-contract-stub-runner` and `springcloud/spring-cloud-contract-stub-runner` in examples. **Verify the exact repository name, registry, and tag used by your organization before copying commands**, rather than treating an example as a guarantee of artifact availability.

**Never put artifact repository usernames/passwords into shell history or source code**. When authentication is required, use secrets/credential injection provided by your container platform or CI. The command above assumes a test repository requiring no authentication.

### 8.1. Why Map Two Ports?

This is a very common point of confusion:

~~~text
localhost:8750         → Stub Runner Boot management REST API
localhost:10080        → Inventory WireMock HTTP API
~~~

Checkout sends:

~~~http
GET http://localhost:10080/api/inventory/SKU-100
~~~

and **does not** send inventory HTTP calls to `localhost:8750`. Port `8750` serves management/inspection endpoints like `/stubs` and `/triggers`.

If you publish port `8750` in Docker without publishing port `10080`, the host can list stubs yet **cannot call WireMock** from the host. For consumers on the same Docker network, you may not need to publish WireMock to the host, provided DNS/container networking is configured correctly.

### 8.2. What About LOCAL Mode in Docker?

`LOCAL` searches the **container's own local Maven repository**, not `~/.m2` on the host. To use local artifacts, mount the host repository to the exact path inside the image and ensure read permissions.

Illustrative example for an image using `/home/scc`:

~~~bash
docker run --rm --name inventory-stubs-local \
  -v "$HOME/.m2:/home/scc/.m2:ro" \
  -e SPRING_CLOUD_CONTRACT_STUBRUNNER_IDS="com.example:inventory-producer:1.2.3:stubs:10080" \
  -e SPRING_CLOUD_CONTRACT_STUBRUNNER_STUBS_MODE=LOCAL \
  -p 127.0.0.1:8750:8750 \
  -p 127.0.0.1:10080:10080 \
  springcloud/spring-cloud-contract-stub-runner:<compatible-tag>
~~~

The Docker documentation gives an example mounting `.m2` to `/home/scc/.m2`. If your image/version uses a different user or local Maven path, **check and adjust the path** instead of assuming all images are identical.

Attaching `:ro` protects the local Maven repo from unintended writes; however, if the image needs to write resolution/cache metadata, you may need a writable volume with proper ownership management. Never mount your entire home directory or sensitive tokens into a container unnecessarily.

### 8.3. Do Not Assume Commands Have Already Been Executed

All examples in this lesson are guides. Only after **you run the container and verify the image, artifact, and ports** can you claim the stub server is working. A conceptually valid command does not guarantee the artifact at the sample URL exists.

## 9. Checking Whether Stub Runner Boot Is Ready

Once the container starts, verify in independent steps:

~~~mermaid
flowchart TD
    A["Start Stub Runner Boot"] --> B{"Management API responds?"}
    B -- "No" --> C["Check startup logs, port 8750, image"]
    B -- "Yes" --> D{"Does /stubs list Inventory?"}
    D -- "No" --> E["Check coordinates/repository/classifier"]
    D -- "Yes" --> F{"Is WireMock port 10080 reachable?"}
    F -- "No" --> G["Check Docker port mapping/network"]
    F -- "Yes" --> H{"Does request match contract?"}
    H -- "No" --> I["Check method/path/headers/mappings"]
    H -- "Yes" --> J["Run consumer tests"]
~~~

Instead of `sleep 30` and assuming startup finished, **wait for an observable condition with a finite timeout**.

### 9.1. Checking the Management API

Stub Runner Boot exposes management HTTP endpoints per the docs:

~~~bash
# List running stubs.
curl --fail --silent --show-error http://localhost:8750/stubs
~~~

An example response may be a JSON object mapping stub coordinates to ports:

~~~json
{
  "com.example:inventory-producer:1.2.3:stubs": 10080
}
~~~

**This is illustrative JSON**, not a live response from a real server. If `/stubs` returns empty, inspect artifact resolution and startup logs rather than merely checking if the container status is running.

To query the port by ID (URL-encoding characters if required by your client/HTTP library):

~~~bash
curl --fail --silent --show-error \
  "http://localhost:8750/stubs/inventory-producer"
~~~

The `GET /stubs/{ivy}` endpoint accepts Ivy notation or bare `artifactId` per the documentation and returns the running stub's port. If not found, it errors and you must investigate the ID.

### 9.2. Calling WireMock Directly

~~~bash
curl --fail --silent --show-error \
  -H "Accept: application/json" \
  "http://localhost:10080/api/inventory/SKU-100"
~~~

The response should contain `sku: SKU-100`, `available: true`, and `quantity: 8` per the sample contract. `curl --fail` exits non-zero on HTTP `4xx`; when checking an **intentional 404 branch**, use options that print status/headers instead of treating every 404 as an infrastructure error.

### 9.3. Verifying a 404 Branch Returns the Right Body

~~~bash
curl --silent --show-error \
  -H "Accept: application/json" \
  -i "http://localhost:10080/api/inventory/SKU-404"
~~~

Verify **both HTTP 404 and JSON `code: INVENTORY_NOT_FOUND`**. A request failing to match any WireMock mapping also returns 404, which does not mean the consumer encountered the intended business error.

### 9.4. Inspecting Active Mappings

WireMock's admin API typically provides:

~~~http
GET /__admin/mappings HTTP/1.1
Host: localhost:10080
~~~

Use this endpoint **in a trusted test environment** to confirm the expected mapping exists; never expose the admin API to the internet. Never edit mappings through the admin API assuming changes persist back into the stub JAR; runtime edits are lost when the container restarts.

## 10. Connecting Checkout to the Network-Appropriate Stub Address

One of the most common reasons a "running" stub causes `Connection refused` in an app is **misunderstanding `localhost`**.

| Where Does Checkout Run? | Typical Inventory Stub Address Needed |
|---|---|
| Checkout on host, Docker stub published to loopback | `http://localhost:10080` |
| Checkout on same Docker Compose network as `stubrunner` | `http://stubrunner:10080` (via service DNS name) |
| Checkout in another container on a different network | Must connect via a shared network or configured gateway; `localhost` will not reach the stub container |
| Checkout in another Kubernetes pod in the preview namespace | Use Kubernetes Service DNS or internal stub address |
| Tests running from a user's browser | Account for origin, CORS, browser-reachable URLs; never expose management API externally |

If Checkout runs inside its own container, its `localhost` is **the Checkout container**, not the host machine and not the Stub Runner container. Therefore `INVENTORY_BASE_URL=http://localhost:10080` is only valid when the client genuinely runs on the host or inside a matching network namespace.

### 10.1. Wiring Base URLs Through Configuration Without Editing Business Code

Example Checkout configuration:

~~~yaml
inventory:
  base-url: http://localhost:10080
~~~

In a preview environment using service discovery or a container network, the value might be:

~~~yaml
inventory:
  base-url: http://stubrunner:10080
~~~

The key `inventory.base-url` is an **application convention defined by Checkout**, not a built-in Spring Cloud Contract property. Checkout must bind it properly into its `WebClient`/`RestClient`/`Feign` client.

**Never hard-code URLs inside business code**; a configuration flag or Spring profile lets you switch between the real producer and the stub per environment without rebuilding the app.


## 11. Using Docker Compose for Multi-Stub Local Development

If Checkout Service depends on two producers, typing multiple `docker run` commands becomes hard to maintain. One Stub Runner Boot container can host two WireMock instances:

~~~text
com.example:inventory-producer:1.2.3:stubs:10080
com.example:pricing-producer:2.1.0:stubs:10081
~~~

Illustrative `compose.yaml` (replace repository address and image tag):

~~~yaml
services:
  stubrunner:
    image: springcloud/spring-cloud-contract-stub-runner:<compatible-tag>
    environment:
      SPRING_CLOUD_CONTRACT_STUBRUNNER_STUBS_MODE: REMOTE
      SPRING_CLOUD_CONTRACT_STUBRUNNER_REPOSITORY_ROOT: "https://repo.example.test/repository/maven-releases/"
      SPRING_CLOUD_CONTRACT_STUBRUNNER_IDS: "com.example:inventory-producer:1.2.3:stubs:10080,com.example:pricing-producer:2.1.0:stubs:10081"
    ports:
      - "127.0.0.1:8750:8750"
      - "127.0.0.1:10080:10080"
      - "127.0.0.1:10081:10081"
~~~

In `ids`, each coordinate specifies a producer artifact and stub port. Check the list-parsing mechanism of the image version you run. **Do not assume both stubs loaded just because Compose accepted the file**; verify `GET /stubs` and call both WireMock ports.

Start and stop with:

~~~bash
docker compose up -d stubrunner
docker compose logs --follow stubrunner
docker compose down
~~~

`up -d` only starts the container; it **does not wait for all mappings to finish loading**. A proper workflow waits until `/stubs` lists all required artifacts before running consumer tests. When cleaning up, avoid blindly passing `-v` or deleting shared volumes if your project keeps persistent data there.

### 11.1. Checkout on Host vs. Checkout in a Container Use Different URLs

When Checkout runs on the host using published ports:

~~~text
INVENTORY_BASE_URL=http://localhost:10080
PRICING_BASE_URL=http://localhost:10081
~~~

When Checkout also runs on the **same Docker Compose network**:

~~~text
INVENTORY_BASE_URL=http://stubrunner:10080
PRICING_BASE_URL=http://stubrunner:10081
~~~

The Checkout container's `localhost` does not route to the Stub Runner container. This is a frequent cause of `Connection refused`. On a shared Docker network, the service name `stubrunner` serves as internal DNS.

### 11.2. Do Not Expose the Management API Publicly When Unnecessary

If both Checkout and the test runner communicate over an internal network, there is no need to publish port `8750` to the internet. The `127.0.0.1` bindings in the example only allow host loopback access. In shared environments, prefer network isolation, firewalls, and internal-only services.

## 12. Ephemeral Environments Per Pull Request

An **ephemeral preview environment** is provisioned for a pull request/commit and torn down once testing finishes. It can run Checkout alongside Inventory and Pricing stubs without deploying both real producers.

~~~mermaid
flowchart LR
    PR["Checkout Pull Request"] --> PREV["Preview namespace/network"]
    PREV --> APP["Checkout application"]
    PREV --> RUN["Stub Runner Boot"]
    RUN --> INV["Inventory WireMock"]
    RUN --> PRI["Pricing WireMock"]
    APP --> INV
    APP --> PRI
    PREV --> TEST["Smoke/consumer tests"]
    TEST --> CLEAN["Teardown + TTL"]
~~~

### 12.1. Reproducible Preview Provisioning Flow

1. Identify the Checkout commit and **producer-verified stub versions** for its dependencies.
2. Create an isolated namespace, Docker network, or Compose project per PR/run ID.
3. Start Stub Runner Boot with a pinned image tag and pinned stub coordinates.
4. Wait for the management API and verify `GET /stubs` lists **the exact Inventory/Pricing artifacts**.
5. Supply internal base URLs to Checkout's HTTP clients.
6. Wait for Checkout readiness and run smoke/consumer behavior tests.
7. Collect logs, stub versions, HTTP failures, and test results on failure.
8. Stop processes/containers and delete the namespace after the job; enforce a TTL for orphaned resources.

Example environment naming:

~~~text
checkout-pr-4821
checkout-pr-4821-stubs
checkout-pr-4821-network
~~~

These names exist strictly to isolate resources. Never allow two PRs to mutate a shared WireMock scenario state or shared mock database unintentionally.

### 12.2. What Does a Preview Verify?

A stubbed preview can prove that Checkout starts up, reads configuration, routes HTTP clients properly, parses JSON, and handles representative success/error cases. It **does not prove**:

- The real Inventory Service handles database transactions properly.
- End-to-end production security mechanisms are valid.
- Broker redelivery, ordering, or exactly-once semantics were tested.
- Real-world latency and load capacity are reproduced.
- The deployed producer uses the exact same version, config, and runtime data.

Hence previews fit **consumer-boundary smoke/integration testing**, without replacing E2E, performance, or reliability tests.

## 13. Stub Lifecycle and State

A stub server needs full lifecycle management from creation to teardown:

| Phase | Check | Outcome |
|---|---|---|
| Prepare | Artifact JAR, classifier, version, release source | Clear provenance |
| Start | Container/image, repository access, ports | Boot starts cleanly |
| Ready | Does `/stubs` list all mappings? | Ready to accept requests |
| Use | Consumer client calls the right WireMock port | Business assertions pass |
| Observe | Logs, unmatched requests, HTTP statuses | Actionable debug data |
| Stop | Process/container terminated | Ports released |
| Cleanup | Namespace, secrets, temporary volumes removed | No orphaned resources |

### 13.1. Stateless vs. Stateful Stubs

A basic stub is **stateless**: identical requests receive fixed sample responses.

~~~text
GET /api/inventory/SKU-100 → 200, quantity=8
~~~

Do not assume interactions like the following share state automatically:

~~~text
POST /api/reservations
GET /api/reservations/RES-123
DELETE /api/reservations/RES-123
~~~

With static mappings alone, the stub will not create a record after POST. WireMock supports **Scenarios** and response templating for stateful simulation when explicitly configured; Spring Cloud Contract does not automatically turn standalone contracts into a mock database.

For stateful tests, avoid sharing a single WireMock state across parallel PRs or tests; use dedicated instances or deliberate state resets.

### 13.2. Can Errors and Latency Be Simulated?

Mappings/fault scenarios can introduce delays, `500` responses, invalid bodies, or connection faults within WireMock/test setup capabilities. Still, tests must explicitly verify **the consumer's** retry, timeout, or circuit-breaker branches; never assume a sample stub reproduces production latency distributions or failure rates.

For latency SLAs, outage resilience, or load testing, use dedicated test suites outside contract samples.

## 14. Using Multiple Stubs and Messaging Triggers

Beyond HTTP stubs, Stub Runner Boot provides endpoints for **messaging labels** in supported integrations. These endpoints live on the **management port**, not on WireMock ports.

| Method/Path | Meaning |
|---|---|
| `GET /stubs` | List running stubs and ports |
| `GET /stubs/{ivy}` | Find the port for an artifact |
| `GET /triggers` | List triggerable messaging labels |
| `POST /triggers/{label}` | Trigger a label |
| `POST /triggers/{ivy}/{label}` | Trigger a label for a specific artifact |

Example messaging contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'paymentCaptured'

    input {
        triggeredBy('publishCapturedPayment()')
    }

    outputMessage {
        sentTo('payments.captured')
        body(
            eventType: 'PaymentCaptured',
            paymentId: 'PAY-123'
        )
    }
}
~~~

With messaging integration and broker/binder properly configured, you can invoke:

~~~bash
curl --silent --show-error http://localhost:8750/triggers

curl --request POST --fail --silent --show-error \
  http://localhost:8750/triggers/paymentCaptured
~~~

**Do not infer** from an accepted POST trigger that the broker finished delivery, the consumer acknowledged it, or business effects occurred once. Delivery, retries, and idempotency require tests at their respective layers.

## 15. Security: Only Run Stub Runner Boot on Trusted Networks

Official documentation warns that **Stub Runner Boot has no access protection by default and is not meant for production or untrusted environments**. This matters even more in preview environments, which can accidentally be exposed behind a public ingress.

### 15.1. Risks to Avoid

- Unauthorized users accessing the management API can inspect stubs or trigger messaging labels.
- WireMock's admin API can leak or allow mutating mappings if exposed improperly.
- Test data accidentally containing PII, access tokens, or production payloads.
- Repository credentials leaking via environment variables, logs, or image layers.
- Orphaned containers lingering after PRs close and turning into unmanaged endpoints.
- Consumers under a test profile accidentally still pointing at a dependency's live production URL.

### 15.2. Safeguards

1. Keep the management port and WireMock admin **internal**; bind host ports to `127.0.0.1` for local use.
2. Use isolated Docker networks/namespaces and network policies blocking external access in previews.
3. Use synthetic fixtures, never real production data or tokens.
4. Inject repository credentials via secret managers/CI secrets with least privilege.
5. Pin image tags and artifact versions; use approved registries and repositories.
6. Attach TTLs and teardown hooks to PR/job lifecycles.
7. Verify consumer base URLs can never fall back to production unintentionally.
8. If shared access is required, add a separately managed auth/network control layer; never rely on Stub Runner Boot's defaults for security.

**Never make management endpoints public** just for the convenience of opening `GET /stubs` in a browser. Access them over internal networks or authorized tooling.


## 16. Common Errors in Local and Preview Environments

| Symptom | Possible Cause | Check |
|---|---|---|
| Cannot pull image | Wrong image repo/tag or registry lacks auth | Image name, version, registry access |
| Stub Runner Boot fails to start | Incompatible config/dependencies | Container startup logs, image/Java compatibility |
| `GET /stubs` refuses connection | Boot not ready yet or wrong management port | Port `8750`, port mapping, process status |
| `/stubs` returns empty list | Wrong `ids` or artifact failed to resolve | Effective environment, resolver logs |
| Artifact download returns `404` | Wrong version, group/artifact, or classifier | Maven coordinates, `repositoryRoot` |
| Artifact download returns `401/403` | Missing or invalid repository credentials | Secrets, permission scope |
| LOCAL cannot find stub in Docker | `.m2` not mounted or mounted to wrong user path | Image home directory, local Maven layout |
| WireMock unreachable from host | Port not published or bound differently | `docker ps`, `-p`, firewall |
| Checkout container gets Connection refused | Used `localhost` inside wrong container | Service DNS, Docker network |
| WireMock returns `404` on success path | Wrong method, path, Accept header, or mapping | Request logs, `/__admin/mappings` |
| Stub response right yet Checkout fails | DTO/deserializer or use-case bug | Consumer stack trace and assertions |
| Stub serves stale data | Cache or updated artifact version | Coordinates, artifact checksum, restart |
| CI passes with no stubs loaded | Checks/contract tests skipped or fail-on-no-stubs disabled | Test counts and `/stubs` |
| Preview passes yet production fails | Real behavior outside stub scope | Integration, E2E, performance tests |

### 16.1. Three Types of HTTP 404 to Distinguish

~~~text
Repository HTTP 404:
    Stub Runner could not download the artifact; no mappings loaded.

WireMock unmatched request HTTP 404:
    Stub server is running, but the request matched no rule.

Contract business HTTP 404:
    Request matched a mapping intentionally returning 404,
    usually with a JSON code such as INVENTORY_NOT_FOUND.
~~~

If Checkout displays "SKU does not exist" after accidentally calling `/api/inventories/SKU-404`, you risk a **false-positive test** because unmatched stubs were not distinguished from business errors.

### 16.2. Layer-by-Layer Isolation Process

1. **Image/process:** Did Stub Runner Boot start cleanly?
2. **Artifact:** Do the coordinates and version exist in the local/remote repository?
3. **Loaded stubs:** Does `GET /stubs` list the right artifact and port?
4. **Network:** From Checkout's network namespace, is WireMock reachable?
5. **Matching:** Does the mapping match method, path, headers, query/body?
6. **Response:** Do status, Content-Type, and JSON schema match the commitment?
7. **Consumer:** Does Checkout code actually handle the response properly?
8. **Provenance:** Did the artifact come from a producer version that passed verification?

When one step fails, fix that specific layer rather than loosening contract matchers or bending business logic to fit a broken response.

### 16.3. Avoid Fixed Sleeps for Readiness Checks

~~~bash
docker compose up -d stubrunner
sleep 30
# Runs tests after 30 seconds, even if mappings are not loaded yet.
~~~

This approach both wastes time and flakes when repository networks slow down. Replace it with **polling `GET /stubs` and a sample WireMock endpoint under a finite timeout**, failing clearly if the expected artifact or port is missing. Never wait forever when an image or artifact is unavailable.

## 17. CI, Versioning, and Release Gates

A reliable workflow separates the **producer pipeline** from the **consumer/preview pipeline**.

~~~mermaid
flowchart TD
    A["Producer source + contracts"] --> B["Generate and run producer tests"]
    B --> C{"Verification passed?"}
    C -- "No" --> X["Block publish"]
    C -- "Yes" --> D["Package + publish stubs artifact"]
    D --> E["Consumer/preview pins stub version"]
    E --> F["Start Stub Runner Boot"]
    F --> G["Check /stubs + WireMock readiness"]
    G --> H["Checkout smoke/integration tests"]
    H --> I["Archive logs, teardown"]
~~~

Gates to enforce:

| Gate | What Must Be Confirmed |
|---|---|
| **Producer verification** | Generated tests were actually created, compiled, and executed; never 0 tests |
| **Artifact packaging** | `-stubs` JAR contains the right mappings, `groupId`, `artifactId`, `version` |
| **Artifact publish** | Publish only approved builds; release artifacts are never silently overwritten |
| **Preview provisioning** | Docker image, repository credentials, network, and ports are valid |
| **Stub readiness** | `/stubs` lists the exact artifacts and each sample endpoint responds |
| **Consumer behavior** | Checkout client/use cases handle 2xx and committed error responses properly |
| **Cleanup** | Containers, namespaces, and temporary credentials do not linger |

### 17.1. Pin Versions

Prefer:

~~~text
com.example:inventory-producer:1.2.3:stubs:10080
~~~

Instead of always using:

~~~text
com.example:inventory-producer:+:stubs:10080
~~~

`+` can resolve a newer artifact between two runs. Thus the exact same Checkout commit can end up testing two different contract versions, making bugs hard to reproduce. For CI, previews, and bug reproduction, **pin both the stub artifact version and the Docker image tag**.

### 17.2. Which Tests Belong Outside Stub Runner?

| Need | Appropriate Test |
|---|---|
| Producer satisfies real contracts | Spring Cloud Contract generated producer tests |
| Checkout sends requests/parses responses properly | Consumer tests using stubs |
| Inventory DB performs atomic reservations | Producer integration/transaction tests |
| Checkout retries/circuit breakers | Controlled fault simulation and resilience tests |
| Kafka event ordering, redelivery | Broker integration/failure tests |
| P99 latency under real load | Performance/load tests |
| End-to-end authentication/authorization | Security/integration tests |
| Deployment compatibility with real infrastructure | Appropriate smoke/E2E tests |

**Never report "done" just because a Stub Runner Boot process is running**. Reliability rests on assertions at the right boundaries and gates that were actually executed.

## 18. Hands-On Exercise: Creating an Ephemeral Checkout Environment

### 18.1. Problem Statement

Inventory Service provides:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

with response:

~~~json
{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

When the SKU does not exist:

~~~http
GET /api/inventory/SKU-404 HTTP/1.1
Accept: application/json
~~~

it responds `404` with JSON `{"code":"INVENTORY_NOT_FOUND"}`.

Checkout Service must read the quantity, reject orders requesting more than 8, and distinguish a missing-SKU error.

### 18.2. Task A — Prepare the Artifact

1. Write or select both Groovy/YAML contracts per Section 4.
2. Configure the Spring Cloud Contract plugin in the producer.
3. Generate and **run** producer verification.
4. Package the `stubs` classifier artifact.
5. Choose `LOCAL` (if installed in local Maven) or `REMOTE` (if published to an artifact repo).
6. Record the exact coordinates `com.example:inventory-producer:1.2.3:stubs`.

**Question:** Why is a hand-built stub JAR insufficient to prove the producer implementation delivers what the consumer needs?

### 18.3. Task B — Run the Standalone Server

Start Stub Runner Boot Docker per Section 8 with ports:

~~~text
Management: 8750
Inventory:  10080
~~~

Record the actual image name and tag, stub coordinates, mode, and `repositoryRoot` (without credentials). Then check:

~~~bash
curl --silent --show-error http://localhost:8750/stubs

curl --fail --silent --show-error \
  -H "Accept: application/json" \
  http://localhost:10080/api/inventory/SKU-100
~~~

Do not consider a `200` from `/stubs` sufficient on its own: the Inventory artifact must appear and WireMock must return the expected status/body.

### 18.4. Task C — Verify Not-Found Handling

~~~bash
curl --silent --show-error --include \
  -H "Accept: application/json" \
  http://localhost:10080/api/inventory/SKU-404
~~~

Verify **both status 404 and code `INVENTORY_NOT_FOUND`**, then intentionally call the wrong path `/api/inventories/SKU-404`. Explain how a matched business 404 differs from an unmatched WireMock 404.

### 18.5. Task D — Run Checkout on Host and in Container

When Checkout runs on the host:

~~~text
INVENTORY_BASE_URL=http://localhost:10080
~~~

When Checkout runs in a container on the same network:

~~~text
INVENTORY_BASE_URL=http://stubrunner:10080
~~~

Use the **real `InventoryClient` and Checkout use case** to verify:

- Requesting 3 items when quantity is 8 succeeds (assuming other conditions pass).
- Requesting 9 items is rejected.
- `SKU-404` is recognized as not-found, not out-of-stock.
- Checkout never accidentally calls production Inventory Service.

### 18.6. Task E — Move to a PR Preview

1. Create an environment named after the PR/run ID.
2. Pin the image tag and stub version `1.2.3`.
3. Restrict management API access to the internal network.
4. Wait for readiness, run smoke tests, and save results.
5. Tear down after the PR/job or via TTL.

**Question:** What could cause a PR to start failing even when code did not change if the image tag or stub version is not pinned?

### 18.7. Self-Assessment

| Statement | True/False |
|---|---|
| Standalone Stub Runner can run separately from JUnit and the real producer | **True** |
| Boot's management port and WireMock's port serve the same purpose | **False** |
| Using `LOCAL` in Docker automatically reads the host's Maven repo without mounting | **False** |
| A stubbed preview replaces all E2E and integration tests | **False** |
| Stub Runner Boot should be exposed publicly since it contains no real business code | **False** |
| WireMock unmatched requests can return HTTP `404` | **True** |
| Producer verification must run separately before publishing | **True** |
| Pinning artifact versions helps keep CI results reproducible | **True** |

### 18.8. Deliverables

A short report covering: artifact version; image/mode; management and WireMock ports; tested requests/responses; consumer behavior assertions; error logs if any; verification boundaries; cleanup status.

## 19. Checklist Before Using Standalone Stubs

- [ ] Consumer needs are captured in Groovy/YAML contracts.
- [ ] Producer generated tests were actually generated and executed.
- [ ] Stub artifact has valid `groupId`/`artifactId`/`version`/`classifier`/mappings.
- [ ] Tooling chosen: Stub Runner Boot Docker, self-built Boot, or direct WireMock.
- [ ] Did not assume newer executable Stub Runner Boot JARs are always available.
- [ ] Selected `LOCAL`/`REMOTE` and `repositoryRoot` appropriately.
- [ ] Stub version and Docker image tag are pinned in CI/previews.
- [ ] Boot management port and WireMock port are clearly separated.
- [ ] `GET /stubs` lists the exact artifacts and ports.
- [ ] Smoke requests verify mappings return expected status/headers/body.
- [ ] Consumer client points to the right URL for the host/container network.
- [ ] Error branch 404 checks the error body to avoid false passes from unmatched requests.
- [ ] Management/admin endpoints are never exposed publicly.
- [ ] No PII, production data, or secrets appear in stubs.
- [ ] Repository credentials are supplied via secrets with least privilege.
- [ ] Ephemeral environments are isolated per PR with TTLs and teardown.
- [ ] Readiness uses real conditions with a timeout, not just a fixed sleep.
- [ ] Consumer tests exercise real consumer code rather than merely pinging the stub.
- [ ] Separate tests exist for performance, security, DB transactions, and messaging delivery.
- [ ] Stubs are never published from producers that failed verification.

## 20. References

- [Spring Cloud Contract — Using the Stub Runner Boot Application](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): standalone Boot, `/stubs` and `/triggers` APIs, security, and executable JAR status.
- [Spring Cloud Contract — Docker Project](https://docs.spring.io/spring-cloud-contract/reference/docker-project.html): Stub Runner Docker image, environment variables, ports, messaging.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): `CLASSPATH`, `LOCAL`, `REMOTE`, and how mappings are retrieved.
- [Spring Cloud Contract — Common Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html): `ids`, classifier, port range, `repositoryRoot`, and defaults.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): defining Groovy/YAML requests and responses.
- [WireMock — Documentation](https://wiremock.org/docs/): request matching, JSON mappings, scenarios, and admin API.

**Remember:** standalone stubs make it easy to develop Checkout or run previews without deploying every real producer dependency. Results are only trustworthy when stubs originate from producer-verified contracts, artifacts carry explicit versions, Stub Runner Boot runs on a trusted network, and consumer tests genuinely exercise application behavior. Separate the management port from HTTP stub ports, verify readiness, keep networks and credentials secure, and clean up afterward. **A green stubbed environment never replaces producer verification evidence and necessary integration tests.**
