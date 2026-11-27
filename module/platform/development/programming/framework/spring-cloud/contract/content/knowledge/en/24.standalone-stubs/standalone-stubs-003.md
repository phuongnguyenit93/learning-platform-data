# Running Stubs in Containers Using Supported Tooling

## Learning Objectives

In **Spring Cloud Contract**, producers and consumers agree on communication using **Groovy/YAML DSL** contracts for HTTP or messaging. From those contracts, the tooling can **generate producer tests** and **package stubs**, allowing consumers to run tests via **Stub Runner**; CI uses those results to catch incompatible API changes.

The **Standalone Stubs** chapter addresses a practical need: sometimes the consumer does not run inside a Spring Boot JVM test, but instead is a Node.js, Python, or Go application, an end-to-end test suite, or a group of services in Docker Compose. In those cases, you want to run the **stub as an independent containerized service** so the consumer can call it over HTTP or receive messages **without starting the real producer**.

This lesson helps you:

- Distinguish the **Stub Runner Boot Docker image** from the **WireMock Docker image** and the **Docker image used for producer verification**.
- Run HTTP stubs from a Spring Cloud Contract `*-stubs.jar` artifact via Stub Runner Boot with a `REMOTE` or `LOCAL` repository.
- Configure `STUBRUNNER_IDS`, `STUBRUNNER_STUBS_MODE`, `STUBRUNNER_REPOSITORY_ROOT`, and expose the right **two port types**.
- Use `docker compose` to organize a test environment, pointing containerized consumers to the **service name** and host consumers to **published ports**.
- Run plain WireMock via its official image with `mappings` and `__files` directories when only HTTP is needed.
- Verify readiness, stub lists, request matchers, error responses, and unmatched mapping cases.
- Understand limitations around **messaging**, security, artifact versions, broker configuration, stub state, and parallel tests.
- Build CI pipelines that only use **producer-verified candidate stubs**, avoiding accidental runs against stale artifacts.

> **Core principle:** a container is only a mechanism to **run and distribute** stubs. It **does not verify the producer by itself**. Producer contract tests must succeed against the real implementation before a stub is treated as a trustworthy published contract.

## 1. What Does "Standalone Stub" Mean?

Imagine **Inventory Service** as the producer providing an inventory API, and **Checkout Service** as the consumer.

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

In production, Checkout calls an address such as `https://inventory.internal.example`. In tests, Checkout needs to send the same request to a **stub server**, for example `http://inventory-stub:9876`, and receive the contract-defined response.

The flow can be illustrated as follows:

~~~mermaid
flowchart TD
    A["Groovy/YAML Contract"] --> B["Generated producer tests"]
    A --> C["Generated HTTP mappings/message definitions"]
    B --> D{"Did producer tests actually PASS?"}
    D -->|No| X["Do not publish verified stub"]
    D -->|Yes| E["Package :stubs artifact"]
    C --> E
    E --> F["Repository/local Maven cache"]
    F --> G["Stub Runner Boot container"]
    G --> H["HTTP stub on port 9876"]
    H --> I["Consumer sends HTTP request"]
    I --> J["Assert consumer behavior"]
~~~

The **Stub Runner Boot container** can automatically download artifacts by Maven/Ivy coordinates, resolve mappings, and launch WireMock servers. A **plain WireMock container** is not responsible for fetching a Spring Cloud Contract Maven artifact by `group:artifact:version:classifier`: you must prepare the mapping and body files for it to read.

It is also important to distinguish another image in the Spring Cloud Contract ecosystem used to **generate/run producer contract tests** for non-JVM applications. That image does not replace Stub Runner Boot when the goal is running **consumer-side stubs**.

## 2. Choosing the Right Tool

| Tool | Primary Input | Advantages | Limitations / Caveats |
|---|---|---|---|
| **Spring Cloud Contract Stub Runner Boot Docker** | Stub artifact with `group:artifact:version:stubs` | Downloads and runs multiple stubs; provides HTTP API for stub management and message triggers | Needs proper repository/cache; never use as a public production server |
| **WireMock OSS Docker** | JSON `mappings` + `__files` | Conceptually lightweight; works for clients in any language; fault/latency testing | Does not resolve Spring Cloud Contract artifacts/versions automatically |
| **Stub Runner in test JVM** | `@AutoConfigureStubRunner` dependency/annotation | Convenient for JUnit/Spring Boot; injects port via `@StubRunnerPort` | Tied to the test JVM lifecycle; not a standalone server for non-JVM apps |
| **Spring Cloud Contract verifier Docker** | Contract DSL + running producer app | Generates/runs producer contract tests over real protocols | Not a drop-in replacement for consumer-side Stub Runner |

For the scenario "a Checkout container needs to call a simulated Inventory built from a producer-published artifact", **Stub Runner Boot Docker** usually preserves the contract link best.

For the scenario "just run a few pre-built WireMock mappings without Maven artifacts or messaging", **WireMock Docker** is typically simpler.

### Why Not Drop Any Arbitrary DSL File Into WireMock?

Groovy/YAML **Spring Cloud Contract DSL is not** WireMock mapping JSON. Stub generation must convert the DSL into configuration WireMock understands. Putting `stockAvailable.groovy` directly inside WireMock's `mappings` folder will not cause WireMock to compile Spring Cloud Contract DSL.

## 3. Preparing Contracts and Artifacts on the Producer Side

Example contract file on the producer side:

~~~text
src/test/resources/contracts/inventory/stockAvailable.groovy
~~~

Groovy DSL content:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'SKU-101 has 8 items in stock'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 8
        )
    }
}
~~~

If the team uses YAML DSL, **the same scenario** can be described as:

~~~yaml
description: 'SKU-101 has 8 items in stock'
request:
  method: GET
  url: '/api/inventory/SKU-101'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
    available: true
    quantity: 8
~~~

In a real project, **choose one canonical contract** for this scenario; do not create two files with identical request matchers just to keep both Groovy and YAML.

### Artifact Used by the Consumer

With a producer using a properly configured Spring Cloud Contract Maven/Gradle plugin, verification and packaging produce coordinates such as:

~~~text
groupId    = com.example
artifactId = inventory-producer
version    = 1.1.0-rc.1
classifier = stubs
type       = jar
~~~

Typical coordinates:

~~~text
com.example:inventory-producer:1.1.0-rc.1:stubs
~~~

Illustrative filename:

~~~text
inventory-producer-1.1.0-rc.1-stubs.jar
~~~

Inside, metadata typically follows a structure like:

~~~text
META-INF/
└── com.example/
    └── inventory-producer/
        └── 1.1.0-rc.1/
            ├── contracts/
            │   └── inventory/stockAvailable.groovy
            └── mappings/
                └── <generated-mapping>.json
~~~

Exact paths and filenames **depend on the plugin/version and build configuration**. If the contract references external body files, the artifact must also include those fixtures.

### Never Skip Producer Verification

Reference Maven command in a producer configured with the verifier plugin:

~~~bash
./mvnw -B -ntp clean verify
~~~

To install the artifact into the Maven local repository for `LOCAL` mode:

~~~bash
./mvnw -B -ntp install
~~~

With Gradle, run the contract test and stub JAR tasks provided by your plugin version. Do not conclude the producer is verified just because `*-stubs.jar` exists; verify **generated producer tests were created, executed, and PASSED**. Avoid publishing artifacts built while `-DskipTests`, `-x test`, or similar test-skipping flags are active.

## 4. Two Different Ports in Stub Runner Boot

Stub Runner Boot exposes at least two distinct types of endpoints:

| Port | Purpose | Example in This Lesson |
|---|---|---|
| **Stub Runner Boot admin port** | GET stub list, look up ports, trigger messages | `8750` |
| **WireMock stub HTTP port** | Consumer calls the Inventory API described by the producer | `9876` |

**Consumers call `http://...:9876/api/inventory/SKU-101`, not `:8750/api/inventory/SKU-101`.** Port `8750` is Stub Runner Boot's admin/trigger server in this example configuration.

If you have two producers, such as Inventory and Pricing, each producer may need its own stub port:

~~~text
Stub Runner admin :8750
Inventory stub    :9876
Pricing stub      :9877
~~~

### Why Are Dynamic Ports Harder to Use with Docker?

In JUnit, `@StubRunnerPort` or `StubFinder` can inspect runtime ports. However, if a containerized stub picks a random port on its own, declaring `-p 9876:9876` will **not** map to that random port automatically.

For Docker Compose and consumers outside the Stub Runner process, **assigning a fixed port per stub** is usually simpler to understand and configure. Prevent collisions by creating an isolated CI/container environment; never run multiple stub sets competing for the same host ports.

## 5. Running Stub Runner Boot Docker with a REMOTE Repository

Spring Cloud Contract documentation describes the standalone Stub Runner Boot image using **environment variables** for configuration. The Docker naming convention typically converts properties to uppercase and dots to underscores:

~~~text
stubrunner.ids             -> STUBRUNNER_IDS
stubrunner.repositoryRoot  -> STUBRUNNER_REPOSITORY_ROOT
stubrunner.stubsMode       -> STUBRUNNER_STUBS_MODE
~~~

This applies to the documented Docker Stub Runner Boot setup; for custom-built apps or older/newer configuration styles, check the exact properties of the image/version you are running.

### Bash Example on Linux/macOS

Hypothetical setup:

- Artifact `com.example:inventory-producer:1.1.0-rc.1:stubs` is published to a test/artifact repository.
- The repository URL is reachable **from inside the container**.
- The stub runs inside the container on port `9876`.
- The Admin API listens on the example Stub Runner Boot default port `8750`.

~~~bash
# Pick a REAL image tag compatible with your project's artifacts.
# Replace the value below before running.
export SCC_IMAGE_TAG="REPLACE_WITH_AVAILABLE_TAG"

# Fictional repository: replace with a real URL reachable from inside the container.
export STUB_REPO_URL="https://artifacts.example.invalid/repository/stubs"

docker run --rm --name inventory-stub \
  -e "STUBRUNNER_IDS=com.example:inventory-producer:1.1.0-rc.1:stubs:9876" \
  -e "STUBRUNNER_STUBS_MODE=REMOTE" \
  -e "STUBRUNNER_REPOSITORY_ROOT=${STUB_REPO_URL}" \
  -p "127.0.0.1:8750:8750" \
  -p "127.0.0.1:9876:9876" \
  "springcloud/spring-cloud-contract-stub-runner:${SCC_IMAGE_TAG}"
~~~

**Values to replace before running:** image tag, artifact coordinates, and repository URL. `artifacts.example.invalid` is intentionally a placeholder, not a reachable service. Some documentation differs in how the image namespace is written between descriptions and command examples; verify the **official image, registry, and available tags** for your Spring Cloud Contract release line, and pin a tag or digest instead of guessing `latest`.

The Docker command above binds both ports to `127.0.0.1` on the **host** to avoid accidentally exposing the admin API externally. If the consumer also runs in another container, place them on the same Docker network and address it by **service name** without exposing the admin port to the internet.

### Reading the Command

| Component | Meaning |
|---|---|
| `STUBRUNNER_IDS=...:stubs:9876` | Selects artifact and internal WireMock port |
| `STUBRUNNER_STUBS_MODE=REMOTE` | Resolves stubs from a remote repository |
| `STUBRUNNER_REPOSITORY_ROOT=...` | Repository location |
| `-p 127.0.0.1:8750:8750` | Allows the host machine to reach the admin API on localhost |
| `-p 127.0.0.1:9876:9876` | Allows the host machine to call the HTTP stub on localhost |
| `springcloud/...:TAG` | Compatible Stub Runner Boot image with pinned version |
| `--rm` | Cleans up the container on stop; does not delete artifacts from external repositories |

**Never hardcode repository passwords in source code, Dockerfiles, committed Compose files, or documentation examples.** When authentication is needed, configure the secret/credentials mechanism supported by your CI environment and Stub Runner version. Environment variables can also be inspected via container management tools; manage them per your organization's security policy.

### Configuring the Admin Port

Stub Runner Boot docs commonly use default admin port `8750`. If your image or config changes this port, you must update both the **container port** and port publishing. Do not change only the host side of `-p HOST:CONTAINER` assuming the server inside automatically changes its port.

## 6. Verifying That Stub Runner Loaded and Started the Right Artifact

Once the container actually starts, inspect the logs:

~~~bash
docker logs inventory-stub
~~~

Look for:

- Stub Runner Boot application is ready.
- Coordinates `com.example:inventory-producer:1.1.0-rc.1:stubs` were resolved.
- Mappings/contracts were discovered.
- WireMock HTTP stub was created and is listening on port `9876`.
- No repository connection errors or mapping deserialization errors.

### Using the Admin API

Stub Runner Boot provides HTTP endpoints to query stubs:

~~~bash
curl -i http://127.0.0.1:8750/stubs
~~~

Per the Stub Runner Boot API, `GET /stubs` returns the list of running stubs. You can query a specific artifact's port via `GET /stubs/{ivy}`, where the identifier can be a bare artifact ID in unambiguous cases:

~~~bash
curl -i http://127.0.0.1:8750/stubs/inventory-producer
~~~

From the output, confirm the exact producer/version and port rather than merely checking whether the container status is `running`.

### Smoke-Testing the HTTP Stub

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://127.0.0.1:9876/api/inventory/SKU-101
~~~

Expected **if the artifact is right and the mapping matches**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-101","available":true,"quantity":8}
~~~

WireMock may vary whitespace formatting, extra headers, or JSON field order; what matters is verifying status, Content-Type, and data according to the contract, not byte-for-byte identity with the example.

### Three Levels of Readiness

~~~text
1. Container process is running
2. Stub Runner Boot has started and downloaded artifacts
3. Inventory's WireMock mapping returns the expected response
~~~

**Do not equate 1 with 3.** For CI, wait until both `GET /stubs` and a **real smoke request** succeed before running consumer tests. Some repositories can be slow to download or require auth; a fixed `sleep 5` is usually unreliable.

## 7. Running LOCAL Stubs From a Mounted Maven Cache

In local development or when CI has installed a candidate artifact into the Maven local repository, you can use `LOCAL` mode.

Per the Stub Runner Boot Docker guide, the host's Maven cache directory is typically mounted to `/home/scc/.m2` inside the image:

~~~bash
# On host: the :stubs artifact has been installed into ~/.m2/repository.
export SCC_IMAGE_TAG="REPLACE_WITH_AVAILABLE_TAG"

docker run --rm --name inventory-stub-local \
  -e "STUBRUNNER_IDS=com.example:inventory-producer:1.1.0-rc.1:stubs:9876" \
  -e "STUBRUNNER_STUBS_MODE=LOCAL" \
  -v "${HOME}/.m2:/home/scc/.m2:ro" \
  -p "127.0.0.1:8750:8750" \
  -p "127.0.0.1:9876:9876" \
  "springcloud/spring-cloud-contract-stub-runner:${SCC_IMAGE_TAG}"
~~~

**Path and permission notes:**

- The example above uses Bash shell syntax. On Windows/PowerShell or Docker Desktop, adapt environment variable and volume path syntax accordingly.
- `LOCAL` reads the **Maven local repository inside the container**, not the producer's `target/*-stubs.jar` directly from the host.
- Mounting `:ro` makes the volume read-only; if the resolver needs to write metadata or missing dependencies to the cache, read-only mounts may fail. Prepare a complete cache beforehand or use an isolated writable environment.
- Do not assume every image/version uses the `/home/scc` home directory. Verify against the documentation for the image you run.
- Avoid stale stubs sharing the same version in the cache. For CI candidates, use unique versions/build IDs or an isolated temporary repository.

### LOCAL Does Not Guarantee Quality

A broken artifact can still be installed into `~/.m2`. Producer verification and version consistency are build/CI responsibilities, not properties of `STUBRUNNER_STUBS_MODE=LOCAL`.

## 8. Using Docker Compose for Consumer and Stub

When the consumer also runs in a separate container, Docker Compose makes networking and lifecycle management convenient.

Example `compose.yaml` for the **stub service**:

~~~yaml
services:
  inventory-stub:
    image: "springcloud/spring-cloud-contract-stub-runner:${SCC_IMAGE_TAG:?set SCC_IMAGE_TAG}"
    environment:
      STUBRUNNER_IDS: "com.example:inventory-producer:1.1.0-rc.1:stubs:9876"
      STUBRUNNER_STUBS_MODE: "REMOTE"
      STUBRUNNER_REPOSITORY_ROOT: "${STUB_REPO_URL:?set STUB_REPO_URL}"
    ports:
      - "127.0.0.1:8750:8750"
      - "127.0.0.1:9876:9876"
~~~

Note: `${VAR:?message}` is **Docker Compose environment variable interpolation**, not Spring Cloud Contract configuration. If `SCC_IMAGE_TAG` or `STUB_REPO_URL` is unset, Compose will error immediately rather than silently using a bad value.

Run with:

~~~bash
export SCC_IMAGE_TAG="REPLACE_WITH_AVAILABLE_TAG"
export STUB_REPO_URL="https://artifacts.example.invalid/repository/stubs"

docker compose up -d
docker compose logs inventory-stub
~~~

Both variables **must be replaced with real values**. Do not use a placeholder repository to evaluate artifact download success.

### If the Consumer Runs on the Host

Use:

~~~properties
inventory.base-url=http://127.0.0.1:9876
~~~

Consumer tests/applications running directly on the host call the port published by the container.

### If the Consumer Runs in the Same Docker Compose Network

Use:

~~~properties
inventory.base-url=http://inventory-stub:9876
~~~

Within the Compose network, the service name `inventory-stub` routes to the stub container. **Do not use `localhost:9876` inside the consumer container**, because `localhost` there refers to the consumer container itself, not the Stub Runner container.

| Where the Consumer Runs | Appropriate URL in Example | Condition |
|---|---|---|
| Host running `curl`/JUnit/Node.js | `http://127.0.0.1:9876` | Stub port is published to the host |
| Consumer container in same Compose network | `http://inventory-stub:9876` | Both services share the same network |
| Container on a different Docker network | None of the above automatically | Needs network attachment or explicit routing |
| Consumer on another machine | Do not use the other machine's `127.0.0.1` | Needs a secured test endpoint and proper network routing |

Never expose admin port `8750` to the internet or untrusted multi-party networks to work around connectivity issues. Stub Runner Boot is a **testing utility without production-grade security**.

### Adding a Consumer Service

Example fragment if Checkout is packaged in a container and supports `INVENTORY_BASE_URL`:

~~~yaml
services:
  checkout-test:
    image: "checkout-consumer-test:${CHECKOUT_TEST_TAG:?set CHECKOUT_TEST_TAG}"
    environment:
      INVENTORY_BASE_URL: "http://inventory-stub:9876"
    depends_on:
      - inventory-stub
~~~

This snippet is a **fragment**, not a complete standalone compose file; it must be merged into the same `services` block as `inventory-stub`. The `checkout-consumer-test` image is an illustrative internal image and does not exist out of the box.

Basic `depends_on` only orders **container startup**, not artifact download completion or mapping readiness. Consumer tests still need a **bounded readiness wait** or a real healthcheck verifying the target endpoint.

## 9. Adding Multiple Producers to One Stub Runner Boot Container

Suppose Checkout also uses Pricing Service. You can declare multiple stub IDs in the same configuration with different fixed ports according to your version's list-parsing support:

~~~text
com.example:inventory-producer:1.1.0-rc.1:stubs:9876
com.example:pricing-producer:2.0.0-rc.2:stubs:9877
~~~

Under `stubrunner.ids`, the list is supplied as a collection; in containerized environments, how collections are encoded in environment variables depends on how the Spring Boot binder reads configuration. **Check resolved IDs in the logs** rather than passing a comma-separated string and assuming every version parses it identically.

An indexed Spring Boot property format you can apply **if supported by your image/version**:

~~~yaml
environment:
  STUBRUNNER_IDS_0: "com.example:inventory-producer:1.1.0-rc.1:stubs:9876"
  STUBRUNNER_IDS_1: "com.example:pricing-producer:2.0.0-rc.2:stubs:9877"
~~~

To avoid depending on array-binding details, you can run **a separate Stub Runner Boot container per producer**, especially when they have different lifecycles, credentials, or versions.

When running multiple stubs in one container:

- Publish both ports `9876` and `9877` if the consumer runs on the host.
- On the same Docker network, consumers call `inventory-stub:9876` and `inventory-stub:9877` (when sharing the same server container).
- Ensure no two stubs claim the same port.
- Check `GET /stubs` to verify all artifacts started.
- Pin the version for each producer; never use `+`/`latest`, which can pull unexpected newer artifacts into tests.

## 10. Using WireMock Docker When You Only Have HTTP Mappings

Another option **officially supported by WireMock OSS** is the `wiremock/wiremock` image. It starts a standalone WireMock server and reads mappings from the filesystem.

Unlike Stub Runner Boot, **WireMock does not automatically download `:stubs` by Maven coordinates**. You need:

~~~text
wiremock/
├── mappings/
│   └── stock-available.json
└── __files/
    └── stock-available-body.json
~~~

Sample mapping JSON `wiremock/mappings/stock-available.json`:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-101",
    "headers": {
      "Accept": {
        "contains": "application/json"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "bodyFileName": "stock-available-body.json"
  }
}
~~~

File `wiremock/__files/stock-available-body.json`:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

### Running the WireMock Image

~~~bash
# Example version from WireMock docs;
# choose an actual tag vetted and pinned by your organization.
docker run --rm --name inventory-wiremock \
  -p "127.0.0.1:8080:8080" \
  -v "${PWD}/wiremock:/home/wiremock:ro" \
  wiremock/wiremock:3.13.2
~~~

Per WireMock Docker docs, `/home/wiremock` is the root directory containing `mappings` and `__files`. This uses Bash volume syntax; adapt the path when running in PowerShell/Docker Desktop.

Smoke test:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://127.0.0.1:8080/api/inventory/SKU-101
~~~

To inspect loaded mappings:

~~~bash
curl -i http://127.0.0.1:8080/__admin/mappings
~~~

**Security note:** the WireMock admin API can also manage stubs. Never expose it to the internet during these tests. When only static mappings are needed, mounting resources read-only reduces the risk of containers modifying host files, though admin operations that write to disk will not work like in a writable mount.

### Converting an SCC Stub JAR to a WireMock Filesystem

If you already have a Spring Cloud Contract `*-stubs.jar`, you can **extract and select compatible HTTP mappings/fixtures** to place under `wiremock/mappings` and `wiremock/__files`.

**Do not assume** mounting the JAR directly into `/home/wiremock` automatically exposes mappings. You need to:

1. Inspect entries in the JAR.
2. Locate `META-INF/.../mappings` directories and body files referenced by those mappings.
3. Copy/extract them into the root filesystem layout WireMock expects.
4. Preserve relative paths used by `bodyFileName`.
5. Confirm your WireMock version supports the generated mapping syntax.
6. Run smoke tests to prove requests match and responses are accurate.

Host command to inspect the artifact:

~~~bash
jar tf inventory-producer-1.1.0-rc.1-stubs.jar
~~~

**Avoid flattening all directories when copying** if mappings use relative body file paths. For messaging contracts, merely copying HTTP mappings into WireMock **does not provide label-triggered messaging**. Use Stub Runner Boot with an appropriate messaging adapter/broker.

## 11. Stub Runner Docker vs. WireMock Docker: Selection Criteria

| Requirement | Preferred Choice | Why |
|---|---|---|
| Consumer needs `group:artifact:version:stubs` from Maven repo | **Stub Runner Boot Docker** | Resolves artifacts and starts stubs by coordinates |
| Multiple consumers/languages need an HTTP test endpoint | **Either** | Both can serve standalone HTTP stubs |
| Need message label `StockChanged` | **Stub Runner Boot Docker** with messaging integration | Provides trigger API and messaging integration |
| Only have JSON `mappings` and `__files` | **WireMock Docker** | No Spring Boot Stub Runner needed |
| Need consumer-controlled WireMock faults/delays | **WireMock Docker** | Well-suited for service virtualization and resilience tests |
| Need producer verification from Groovy/YAML DSL | **Producer verifier/test pipeline** | Docker stubs do not verify producers |
| Want minimal containers for a small set of HTTP mappings | **WireMock Docker** | Direct setup with a filesystem volume |
| Need traceability of which artifact version is mocked | **Stub Runner Boot Docker** or mappings with CI metadata | Stub Runner ties directly to artifact coordinates |

A practical strategy uses **Stub Runner Boot** for consumer-driven contract tests and **WireMock Docker** for consumer-designed fault/timeout tests. The key is knowing **which mapping source** is serving each request.

## 12. Messaging Contracts in Containers: Real Brokers or Proper Test Adapters Required

With Spring Cloud Contract messaging DSL, a contract can look like:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_changed'

    input {
        triggeredBy('emitStockChanged()')
    }

    outputMessage {
        sentTo('stock-events')
        body(eventType: 'StockChanged', sku: 'SKU-101', quantity: 0)
        headers {
            messagingContentType(applicationJson())
        }
    }
}
~~~

Producer generated tests must call `emitStockChanged()`, capture the real producer message in the test environment, and assert payload/headers.

On the consumer side, Stub Runner Boot provides an HTTP API to trigger labels:

~~~bash
curl -i http://127.0.0.1:8750/triggers

curl -i -X POST \
  http://127.0.0.1:8750/triggers/stock_changed
~~~

**Important:** a successful POST trigger alone does not prove the consumer processed the message. Consumer tests must wait for business state—such as an inventory projection dropping to 0—within a bounded timeout.

### Configuring Messaging in Stub Runner Docker

Per the Spring Cloud Contract Docker Project docs, the Stub Runner image supports the `MESSAGING_TYPE` variable for supported broker/integration types, such as:

~~~text
MESSAGING_TYPE=rabbit
MESSAGING_TYPE=kafka
~~~

Typical connection settings:

~~~text
SPRING_RABBITMQ_ADDRESSES=rabbitmq:5672
SPRING_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
~~~

`rabbitmq` and `kafka` here are **service names on an illustrative Docker network**; they do not create brokers automatically. The corresponding broker container, authentication, listeners, topics/queues, and binders must all be properly configured for your technology stack.

**Do not use `localhost:9092` from inside the Stub Runner container** to reach another Kafka container: `localhost` is the Stub Runner container itself. In addition, Kafka advertised listeners must return an address **reachable by all clients on the test network**; changing only bootstrap servers without configuring advertised listeners can let the initial connection succeed while subsequent metadata redirects fail.

### Limitations of Docker Messaging Tests

Even when Stub Runner emits a message successfully:

- It does not prove producer publisher code emits properly (that requires producer contract tests).
- It does not prove production brokers meet throughput, partition ordering, or durability requirements.
- It does not prove the consumer committed state (requires post-processing assertions).
- It does not verify duplicate delivery, retries, transactional outbox, or DLQ behavior.

Those aspects require integration/resilience tests targeting the real broker technology.

## 13. Connecting Consumers with Environment-Appropriate URLs

A common mistake is continuing to hit a production URL because you "started a stub" without **updating HTTP client configuration**.

### Consumer Running on the Host

~~~bash
# Example for an app reading INVENTORY_BASE_URL.
export INVENTORY_BASE_URL="http://127.0.0.1:9876"

# Run consumer tests only after the stub is ready.
./mvnw test
~~~

### Consumer Running Inside a Docker Network

~~~yaml
environment:
  INVENTORY_BASE_URL: "http://inventory-stub:9876"
~~~

Note: `INVENTORY_BASE_URL` assumes the consumer supports it, e.g., Spring Boot property `inventory.base-url` bound from the environment. If the consumer ignores that property when building its client, setting the env var **will not change the URL**.

**Do not use `@StubRunnerPort` inside a standalone consumer container app** expecting port injection like in a Spring JUnit test, unless an embedded Stub Runner is configured there. When Stub Runner runs as an **external container** service, the consumer should use that container's URL and port.

### Consumer Health and Readiness

If the consumer app starts at the same time Stub Runner is downloading Maven artifacts:

- `depends_on` may only guarantee the stub container process started, not that mappings are ready.
- The consumer needs bounded retries at test bootstrap, or the pipeline must wait for readiness before launching tests.
- If the production app includes real retry logic, separate **product resilience logic** from the test runner "waiting for infrastructure startup".

Never let a test flake simply because the consumer sent a request 200 ms before Stub Runner finished loading mappings.

## 14. Writing a Bounded Smoke Check for CI

In a host environment with `curl`, you can verify readiness on both admin and stub HTTP endpoints:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

admin="http://127.0.0.1:8750/stubs"
api="http://127.0.0.1:9876/api/inventory/SKU-101"

ready=0
for attempt in $(seq 1 30); do
  if curl --fail --silent "$admin" >/dev/null &&
     curl --fail --silent \
       -H "Accept: application/json" "$api" >/dev/null; then
    ready=1
    break
  fi
  sleep 2
done

if [ "$ready" -ne 1 ]; then
  echo "Stub Runner not ready; inspect container logs" >&2
  exit 1
fi

echo "Stub is ready for consumer tests"
~~~

This is an **example Bash script** requiring `curl`, `seq`, and `sleep` on the runner. On PowerShell/Windows, translate it into an equivalent loop. While bounded by retry count, this script **only** verifies a successful HTTP status on one request. For stricter checks, validate the JSON body with a JSON parser/consumer test and confirm the artifact version via Stub Runner logs or API.

**Avoid using a fixed `sleep 30`** instead of readiness checks: if the stub is ready in 3 seconds, it wastes time; if the repo takes 40 seconds to download, it still fails. A deadline-bounded loop makes diagnostics far clearer.

## 15. A CI Workflow Using Containerized Stubs

Example pipeline layout, independent of any specific CI vendor:

~~~mermaid
sequenceDiagram
    participant PR as Pull request
    participant P as Producer verification
    participant A as Candidate stub artifact
    participant D as Docker / Stub Runner
    participant C as Consumer test
    PR->>P: Generate + run producer contract tests
    alt Producer test PASS
      P->>A: Package candidate stubs from same revision
      A->>D: Resolve artifact with pinned version
      D->>D: Start HTTP stub 9876
      C->>D: Smoke-check /stubs and /api/inventory/SKU-101
      C->>D: Send real consumer HTTP requests
      C->>C: Assert business behavior
    else Producer test FAIL
      P-->>PR: Block publish
    end
~~~

For a consumer job running on the host, an illustrative generic script:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# SCC_IMAGE_TAG and STUB_REPO_URL must be set beforehand.
# compose.yaml should follow section 8.
cleanup() {
  docker compose down --remove-orphans
}
trap cleanup EXIT

docker compose up -d inventory-stub

# Call the bounded readiness script from section 14.
./wait-for-inventory-stub.sh

# Example Spring Boot consumer reading inventory.base-url from env.
INVENTORY_BASE_URL="http://127.0.0.1:9876" \
  ./mvnw -B -ntp test
~~~

This is **adaptable pipeline pseudocode**, not a set of files pre-created by this lesson. You must supply the readiness script, Compose file, test config, and candidate artifact wiring for your actual environment.

### Five Things to Verify in CI

1. **Producer tests actually ran and PASSED**, not skipped/disabled, and not green with `0 tests`.
2. **Stub container uses the right candidate artifact**, not `latest` or stale cache.
3. **Container can reach the repository**, without leaking credentials in logs.
4. **Ports/URLs match where the consumer runs** (host vs. Docker network).
5. **Consumer tests use a real HTTP client**, asserting status, error codes, JSON, or message handlers rather than merely checking that the stub container booted.

If the producer modifies both the contract and implementation simultaneously, generated producer tests against the new contract may PASS while older consumers break. Therefore, consumer tests must run against **that revision's candidate stub**, and breaking changes must be evaluated before release.

## 16. Versioning and Stub Sources

A containerized environment can source stubs in three common ways, depending on Stub Runner configuration:

| Mode | Stub Source | Container Usage |
|---|---|---|
| `REMOTE` | Maven/Artifactory/Nexus or supported artifact store | Fits CI or multi-team environments; requires network and read access |
| `LOCAL` | Maven local repository mounted into container | Fits when developer/CI already installed candidate into a dedicated cache |
| `CLASSPATH` | Artifacts/resources on the Stub Runner app classpath | Requires an image/custom runtime containing those resources; not arbitrary JAR mounts |

For **Docker Stub Runner Boot**, `REMOTE` and `LOCAL` are generally more direct. `CLASSPATH` requires matching image/version packaging and configuration; do not expect mounting a directory of `*.jar` files to automatically put them on Stub Runner's classpath.

### Immutable Versions

Version markers like `+` or an alias like `latest` are convenient for experimentation, but unsuitable as CI evidence:

~~~text
Producer commit A -> candidate 1.1.0-rc.1
Consumer test    -> must use 1.1.0-rc.1

Avoid:
Producer commit A -> candidate 1.1.0-rc.1
Consumer test    -> picks any newest/latest
~~~

With mutable `SNAPSHOT`s, prevent situations where the artifact bytes change for the same version string between verification and consumer testing. Attach a commit/build ID or checksum, record the resolved version, and consume the candidate artifact from the exact producer job.

## 17. Security: Never Put Stub Runner Boot in Untrusted Environments

Spring Cloud Contract documentation warns that Stub Runner Boot is **not secure by design**, as it is a testing tool; do not run it in production or environments with untrusted clients.

Recommendations:

- Bind the admin port to `127.0.0.1` on the host or isolate it in a dedicated test Docker network.
- Never create an ingress or public load balancer for `/stubs` and `/triggers`.
- Do not mount the Docker socket `/var/run/docker.sock` into the stub container unless strictly necessary.
- Avoid putting repository passwords/secrets in Dockerfiles, command lines stored in shell history, or committed Compose files.
- Never use fixtures containing real tokens, customer data, or sensitive internal URLs.
- Run containers with the least privilege allowed by the image and filesystem.
- Restrict volume write permissions and do not share mutable state across unrelated test suites.
- Serve HTTP stubs only to authorized test clients on an isolated test network.
- Never turn Stub Runner Boot into a proxy handling production traffic.

For WireMock OSS Docker as well, `/__admin` is an administrative API. Similar network restrictions are good practice even with static test mappings.

## 18. Common Errors When Running Stubs in Containers

| Symptom | Common Cause | How to Check |
|---|---|---|
| Image fails to pull | Wrong image repo/tag, missing registry auth, or non-existent version | Verify against official image docs and actual available tags |
| Container runs but `/stubs` is empty | Artifact failed to resolve, no mappings, wrong `ids` config | Check Stub Runner logs, coordinates, and JAR contents |
| `/stubs` is unreachable | Wrong admin port or `-p` mapping | Check actual server port and Docker published ports |
| `/stubs` lists stub but `:9876` fails from host | WireMock port not published or port mismatch in `ids` | Check `STUBRUNNER_IDS` and `docker port` |
| Consumer container cannot reach `localhost:9876` | `localhost` refers to consumer container itself | Use Compose service name `inventory-stub` |
| Stub returns unexpected `404` | Request does not match method/path/header/body | Inspect mapping, request journal, and actual URL |
| Stub returns wrong fixture | Stale artifact version or overlapping mappings | Pin version/digest and inspect contracts/mappings |
| Repo reachable from host but not container | Different DNS, proxy, network, CA, or credentials | Test connectivity from inside the test network/container |
| `LOCAL` cannot find stub | Wrong `~/.m2` mount or artifact never installed | Check volume path, artifact/pom, and permissions |
| `LOCAL` keeps serving stale build | Cache holds mutable version with same coordinates | Use unique versions or an isolated cache |
| `bodyFileName` errors | Missing `__files` or broken relative path | Check mapping and filesystem root |
| WireMock container uses wrong JAR | Mounted raw `*-stubs.jar` instead of mappings | Extract the mapping/body files properly |
| Messaging trigger exists but consumer receives nothing | Missing broker/binder, wrong destination, or inactive listener | Check `MESSAGING_TYPE`, broker routing, and consumer handler |
| CI flakes randomly at startup | Relied solely on `depends_on` or fixed sleep | Add a deadline-bounded readiness probe |
| Container exits or port conflicts | Multiple suites sharing host ports | Isolate environments/test networks or vary port mappings |
| Unsafe POST hits production | Consumer base URL not overridden | Inject stub URL and block unnecessary egress |

### Why `404` Does Not Necessarily Mean "Not Found" Per Contract

WireMock returns `404` when a request **matches no mapping**. If consumer tests intend to test a `SKU_NOT_FOUND` business case, there must be a mapping returning `404` with a specific error code, and the test must assert **the error body/code**. Asserting only status 404 can produce false positives from mistyped URLs.

### Why Increasing Timeouts Does Not Fix Routing Bugs

If `STUBRUNNER_IDS` binds port `9877` while the consumer calls `9876`, waiting longer will not change the destination. Likewise, if a consumer container calls `localhost` instead of the service name, increasing read timeouts will not bridge into another container.

**Debugging order:** artifact → Stub Runner startup → container port → published port/network → request matcher → response/assertions.

## 19. Hands-On Exercises

### Scenario A — Choosing the Right Tool

Your team has a producer-verified `inventory-producer-1.1.0-rc.1-stubs.jar` and wants a Python application in Compose to call the simulated HTTP API.

**What to choose?** Stub Runner Boot Docker, because it understands how to resolve artifacts and launch HTTP stubs. If using WireMock Docker instead, you would first need to extract mappings and body files from the artifact.

**Question:** Which port does the consumer call?

**Answer:** The HTTP stub port, e.g., `9876`, not the admin port `8750`.

### Scenario B — Container Calls the Wrong localhost

Compose defines two services: `checkout-test` and `inventory-stub`. Checkout configures:

~~~properties
inventory.base-url=http://localhost:9876
~~~

Checkout gets connection refused, even though `curl http://127.0.0.1:9876` succeeds from the host.

**Cause:** `localhost` inside the checkout container points to the checkout container itself.

**Fix:**

~~~properties
inventory.base-url=http://inventory-stub:9876
~~~

Both services must share **the same Docker network**, and Stub Runner must actually have a stub listening on port `9876`.

### Scenario C — Producer Changes While Consumer Tests Stay Green

The producer just changed `quantity` from number `8` to string `"8"`, yet consumer tests running `wiremock/wiremock` with an old hand-written mapping still return number `8`. Tests stay green.

**Problem:** hand-written mappings do not stay in sync with producer contracts/implementations. You need generated producer contract tests and consumer tests running against the **candidate stub from the same revision**, never treating a green run on an old mapping as proof of compatibility.

### Scenario D — Docker Compose Using Only depends_on

Checkout starts after the Stub Runner container process begins, but before Stub Runner finishes downloading its artifact; initial requests fail with 404 or connection refused.

**Solution:** add a real readiness check against the stub endpoint (or a meaningful healthcheck) with a bounded wait. Start consumer tests only after the stub returns the expected smoke response.

### Scenario E — Messaging Trigger Does Not Fire

Stub Runner Boot lists the `stock_changed` label, but the consumer never receives the event after `POST /triggers/stock_changed`.

Check:

1. Does `MESSAGING_TYPE` match the broker/binder in use?
2. Can the Stub Runner container reach the broker via its **internal Docker network address**?
3. Are the destination/topic/queue, headers, and message converter correct?
4. Is the consumer listener running and subscribed to the right destination?
5. Does the consumer test wait for asynchronous processing with a finite timeout?

### Advanced Exercise

Design a `compose.yaml` with two HTTP stubs:

- Inventory on `9876` and Pricing on `9877`.
- A host-based consumer needs to reach both via `127.0.0.1`.
- A Compose-based consumer container needs to reach them by service name.
- Admin API `8750` is accessible only within the test scope.
- Both artifacts must use explicit versions and have passed producer tests.

Explain how you prove **the right versions are loaded**, ports do not collide, and production services cannot be called by mistake.

## 20. Containerized Stub Deployment Checklist

- [ ] Clearly decided: **Stub Runner Boot** for Spring Cloud Contract artifacts or **WireMock Docker** for JSON mappings.
- [ ] Producer Groovy/YAML contracts and generated tests have genuinely been verified.
- [ ] Candidate stub artifacts have traceable coordinates/versions, without vague `latest` aliases.
- [ ] Image repository/tag exists, is compatible, and is pinned.
- [ ] `STUBRUNNER_IDS` specifies the right group/artifact/version/classifier/**container port**.
- [ ] `STUBRUNNER_STUBS_MODE` and repository/cache are properly configured without stale artifacts.
- [ ] Stub Runner admin port and HTTP stub port are clearly separated.
- [ ] Docker port publishing/binding matches host needs and never opens the admin API to the internet.
- [ ] If the consumer runs in Compose, URLs use the **service name**, not a misdirected localhost.
- [ ] If using WireMock Docker, `mappings`/`__files` and relative paths are properly arranged.
- [ ] Repository credentials, broker credentials, and fixtures contain no exposed secrets.
- [ ] For messaging, broker/binder/destinations are properly wired; triggers do not replace consumer processing assertions.
- [ ] Readiness wait has a deadline rather than bare `sleep` or `depends_on`.
- [ ] Consumer tests exercise a real HTTP client and assert response/error bodies per contract.
- [ ] CI treats a candidate as verified only after producer tests PASS.
- [ ] Stub containers are cleaned up after tests, with necessary logs/metadata archived for investigation.

## 21. Key Takeaways and References

**Running stubs in containers is a way to distribute simulated producer environments for consumer testing, not a step that validates producer code.** With Spring Cloud Contract, choose **Stub Runner Boot Docker** when you need to fetch versioned `:stubs` artifacts, manage multiple stubs, and trigger messages by label. Choose **WireMock Docker** when you already have HTTP mapping JSON and want a simple mock HTTP server with controllable errors and latency.

Whichever option you choose, verify **both addresses**: the tool's admin port and the API port the consumer actually calls; and distinguish the **host's localhost** from a **container's localhost**. Run consumer tests only once the stub has loaded the right artifact and mappings are ready, keep versions immutable, and never expose test management endpoints to production or public networks.

### Official Documentation

- [Spring Cloud Contract — Docker Project](https://docs.spring.io/spring-cloud-contract/reference/docker-project.html): images for producer verification and consumer-side Stub Runner Docker, environment variables, LOCAL/REMOTE, and messaging.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): `/stubs` and `/triggers` HTTP endpoints and security warnings.
- [Spring Cloud Contract — Configuration Properties](https://docs.spring.io/spring-cloud-contract/reference/configprops.html): stubrunner properties, source modes, `fail-on-no-stubs`, and runtime options.
- [WireMock OSS — Running in Docker](https://wiremock.org/docs/standalone/docker/): `wiremock/wiremock` image, mounting `mappings` and `__files`, and Docker Compose.
- [WireMock OSS — Stubbing](https://wiremock.org/docs/stubbing/): JSON mapping syntax, body files, request matching, and responses.
- [Docker — Networking in Compose](https://docs.docker.com/compose/how-tos/networking/): routing by service name on a Compose network.

**Conclusion:** a trustworthy containerized stub test answers three questions: **which artifact/mapping is running**, **where the consumer is actually sending requests**, and **whether the producer proved that contract with tests**. When all three are verified, containerizing Stub Runner or WireMock enables polyglot systems to test independently while preserving compatibility between producer and consumer.
