# Stub Retrieval Modes: CLASSPATH, LOCAL, and REMOTE

## 1. Why does Stub Runner need multiple stub retrieval modes?

In a microservices system, a **consumer** commonly calls an HTTP API or receives messages from a **producer**. When writing consumer tests, starting all producers, databases, and related infrastructure can be both slow and hard to reproduce. **Spring Cloud Contract Stub Runner** solves part of this problem by running stubs built from contracts, allowing the consumer to send requests and receive responses according to the interface the producer published.

Suppose there are two applications:

- **Inventory Service** (producer) exposes `GET /api/inventory/SKU-100` and returns stock status.
- **Checkout Service** (consumer) needs to call that endpoint before confirming an order.

Example response the consumer expects:

~~~json
{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

The Inventory Service team writes contracts in Groovy/YAML DSL, generates producer tests, and produces an artifact containing stub mappings. The Checkout Service team uses **Stub Runner** to start a WireMock server loading those mappings. When Checkout's client calls WireMock, it receives the contract response without running the real Inventory Service.

The crucial question is: **Where does Stub Runner fetch stubs from?** Spring Cloud Contract provides three modes under `StubRunnerProperties.StubsMode`:

- `CLASSPATH` — scans stubs on the **test runtime classpath**.
- `LOCAL` — finds artifacts in a **local repository**, typically the local Maven repository `~/.m2/repository`.
- `REMOTE` — fetches artifacts from an **external repository** like Nexus/Artifactory or a location supported via a custom protocol.

Choosing the right mode prevents the consumer test suite from accidentally picking the wrong version, depending on the author's local machine, and failing to reproduce in CI.

This lesson belongs to the **Stub Runner** chapter of the `SPRING_CLOUD_CONTRACT` module. The content ties into the producer–consumer contract testing workflow using Groovy/YAML DSL, generating producer tests, publishing stubs, using Stub Runner, and integrating with CI to detect incompatible API changes.

### Objectives

After completing this lesson, you will be able to:

1. Explain how Stub Runner downloads, locates, and runs stubs.
2. Distinguish `CLASSPATH`, `LOCAL`, and `REMOTE` by **artifact source** and use case.
3. Read the `groupId:artifactId:version:classifier:port` string.
4. Prepare stub JARs for testing under each mode.
5. Intentionally configure `@AutoConfigureStubRunner`, `repositoryRoot`, and `ids`.
6. Connect the consumer client to the WireMock port provided by Stub Runner.
7. Diagnose missing-stub errors, wrong classifiers, wrong versions, unmatched requests, and repository errors.
8. Design a strategy using LOCAL for development, REMOTE for CI, and CLASSPATH for self-contained suites.

> **Remember:** The three modes differ primarily in **how stubs are located/fetched**, not in the meaning of the contract. Once mappings are found, Stub Runner can still spin up WireMock servers to serve consumer tests according to the packaged rules.

## 2. Where does Stub Runner sit in the contract lifecycle?

~~~mermaid
flowchart TD
    DSL["Producer writes Groovy/YAML contract"] --> GEN["Generate producer tests"]
    GEN --> VERIFY{"Does producer verification pass?"}
    VERIFY -- "No" --> STOP["Block release"]
    VERIFY -- "Yes" --> PACK["Generate and package stubs JAR"]
    PACK --> SRC{"Choose stub source"}
    SRC --> CP["CLASSPATH: test dependencies"]
    SRC --> LOC["LOCAL: local Maven repository"]
    SRC --> REM["REMOTE: Nexus / Artifactory / supported location"]
    CP --> RUN["Stub Runner loads mappings"]
    LOC --> RUN
    REM --> RUN
    RUN --> WM["Start WireMock HTTP stubs"]
    WM --> CT["Consumer integration tests"]
~~~

Data flow to understand:

1. **Source contract** describes agreed requests/responses or messages.
2. **Contract Verifier** generates tests sending requests to the real producer or producer test context and validates responses.
3. From contracts, the build can generate **WireMock stub mappings** and package them into a **stub artifact**.
4. **Stub Runner** finds the artifact per the mode, unpacks/registers mappings, and runs a WireMock server for each matching dependency.
5. **Consumer tests** call the stub server and verify client/consumer behavior.
6. CI should publish stubs only for producers that passed verification under project policy.

**A stub JAR is not a running producer application.** WireMock simulates the described interactions; it does not execute producer service code, repositories, transactions, or middleware. Therefore, consumer tests with stubs and generated producer tests complement rather than replace each other.

### 2.1. Stub Runner is not only for HTTP

For HTTP, Stub Runner runs WireMock mappings. For messaging, Spring Cloud Contract offers mechanisms to trigger/send messages through compatible integrations. However, **choosing stub source `CLASSPATH`, `LOCAL`, or `REMOTE` does not automatically configure a broker, message binder, or message verifier**. Those parts require separate setup when testing message-based communication.

## 3. Quick comparison of the three modes

| Property | CLASSPATH | LOCAL | REMOTE |
| --- | --- | --- | --- |
| Stub source | JARs/mappings on runtime classpath | Local artifact repository, usually `.m2` | Artifact repository like Nexus/Artifactory, or supported location |
| Enum value | `StubsMode.CLASSPATH` | `StubsMode.LOCAL` | `StubsMode.REMOTE` |
| Default mode | **Yes** | No | No |
| Needs network at test time? | Usually no, once dependencies are resolved | No, if artifact is installed in local repo | Usually yes, though caching may apply |
| How stubs enter tests | Declare stub JAR as a test dependency | Producer runs `install` / publish-to-local | Producer publishes stub artifact to shared repo |
| Common pitfall | Having dependency does not guarantee valid mappings | Artifact not `install`ed or stale version | URL/permissions/cache/version issues |
| When to use | Self-contained tests, stable fixtures | Offline dev, testing unpublished producer changes | Cross-team CI, consumer in another repo |
| Version control | Via test dependency | Via locally installed artifact/version | Via artifact/version in repository |
| Needs `repositoryRoot` | No, scans classpath | Usually no, uses local repository | Yes, when fetching from remote/custom location |

The difference between `LOCAL` and `CLASSPATH` is especially important:

- An artifact **already on the test classpath** can be scanned by `CLASSPATH`.
- An artifact only **sitting in `~/.m2/repository`** without **being added to the classpath** is not automatically scanned by `CLASSPATH`.
- `LOCAL` resolves artifacts from the local repository by Maven coordinates; you don't need to declare every stub JAR as a test dependency the same way as `CLASSPATH`.

## 4. Reading stub coordinates accurately: Ivy notation

Stub Runner accepts a list of `ids` using the convention:

~~~text
groupId:artifactId:version:classifier:port
~~~

Example:

~~~text
com.example:inventory-producer:1.2.3:stubs:8095
~~~

| Part | Illustrative value | Meaning |
| --- | --- | --- |
| `groupId` | `com.example` | Maven group |
| `artifactId` | `inventory-producer` | Producer module that published the artifact |
| `version` | `1.2.3` | Stub artifact version |
| `classifier` | `stubs` | Distinguishes stub JAR from main application JAR |
| `port` | `8095` | WireMock server port Stub Runner attempts to bind |

Per documentation, `version`, `classifier`, and `port` are **optional**; if version is omitted, the default typically uses `+` to pick the latest version per resolver mechanics; if classifier is omitted, it defaults to `stubs`; if port is omitted, Stub Runner picks a port in the configured range. Defaults and how the resolver chooses "latest" must be checked against your project's version and artifact source.

Example formats:

~~~text
com.example:inventory-producer
com.example:inventory-producer:1.2.3
com.example:inventory-producer:1.2.3:stubs
com.example:inventory-producer:1.2.3:stubs:8095
com.example:inventory-producer:+:stubs:8095
~~~

**Recommendation:** For CI or breaking-change checks, use a **pinned specific version** instead of `+`. "Latest" can shift between two runs, causing the same consumer commit to pull different stubs and trigger hard-to-reproduce failures.

### 4.1. Distinguishing port from artifact identity

`8095` is the **WireMock server port**, not Inventory Service's real production port and not the Maven repository port.

With multiple producers, each stub server needs its own port. If you don't need to pin a port, let Stub Runner choose ports and retrieve the runtime port via `@StubRunnerPort` or running-stubs properties; this avoids collisions when multiple test suites run in parallel.

### 4.2. Classifier is not an arbitrary directory

Under common packaging workflows, the producer builds:

~~~text
inventory-producer-1.2.3.jar
inventory-producer-1.2.3-stubs.jar
~~~

The second file is the **artifact with classifier `stubs`**, not a copy of the application. If the producer uses another classifier like `contract-stubs`, the consumer must specify that classifier or configure the matching default.

## 5. CLASSPATH: scanning stubs already on the test classpath

`StubsMode.CLASSPATH` is the **default**. Stub Runner does not need to resolve a new stub artifact from remote during startup if the required stubs are already placed on the classpath.

Example of a consumer declaring a Maven dependency on the producer's stub JAR:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>inventory-producer</artifactId>
    <version>1.2.3</version>
    <classifier>stubs</classifier>
    <type>jar</type>
    <scope>test</scope>
</dependency>
~~~

After Maven resolves the dependency, the JAR appears on the **test runtime classpath**. Spring Cloud Contract scans mappings/contracts locations by convention within the artifact, such as `META-INF/.../mappings` and `META-INF/.../contracts` paths matching group/artifact. **Having the right JAR on the classpath and packaging with the right layout** are key requirements.

### 5.1. Configuring consumer tests in CLASSPATH mode

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs:8095",
    stubsMode = StubRunnerProperties.StubsMode.CLASSPATH
)
class CheckoutConsumerContractTest {

    @Test
    void consumerShouldHandleInventoryResponse() {
        // Call the consumer client configured to point at stub localhost:8095.
        // Assertions must verify Checkout Service behavior.
    }
}
~~~

This is an **illustrative skeleton**: the test runner and consumer application need compatible Stub Runner/JUnit/Spring Boot dependencies. The test body must call the real client or consumer logic; seeing only the annotation does not mean the consumer has been verified.

If you omit `stubsMode`, current documentation specifies `CLASSPATH` as default. Still, **relying implicitly on the default should be noted in code review** so new team members know which stub source is used.

### 5.2. When is CLASSPATH appropriate?

- The consumer can declare the stub JAR version as a **test dependency**.
- You want relatively self-contained tests without repository access at runtime after dependency resolution.
- Modules live in the same build or CI has a clear dependency graph.
- You want to lock stub versions via dependency management instead of letting Stub Runner pick latest.
- You want to reduce remote network flakiness while running tests.

Drawback to watch: changing a stub version may require updating the build dependency; bad packaging prevents the scanner from seeing mappings even when the JAR is present.

### 5.3. Avoid two misconceptions

**Misconception 1:** Having `some-stubs.jar` in a downloads folder without declaring it on the test classpath means CLASSPATH finds it automatically.

No. It must sit on the **classpath scanned by Stub Runner**, with matching layout and coordinates.

**Misconception 2:** CLASSPATH means the network is never needed.

Not quite. Maven/Gradle may need network access **to download test dependencies before running tests**. Once the classpath is assembled, Stub Runner scans from it instead of resolving via `REMOTE`.

## 6. LOCAL: fetching artifacts from the local Maven repository

`StubsMode.LOCAL` works well for co-developing producer and consumer on a local machine or in offline environments with a prepared local repository.

Suppose the producer generated and packaged a stub JAR with coordinates:

~~~text
com.example:inventory-producer:1.2.3:stubs
~~~

On a machine with the default Maven repository, the artifact may live at:

~~~text
~/.m2/repository/com/example/inventory-producer/1.2.3/
    inventory-producer-1.2.3.pom
    inventory-producer-1.2.3.jar
    inventory-producer-1.2.3-stubs.jar
~~~

A common way to prepare this on a producer configured with the Spring Cloud Contract Maven plugin and stub artifact attachment:

~~~bash
# Inside producer repository; illustrative command for a configured Maven project
./mvnw clean install
~~~

This command **only installs the stub classifier** if the producer project is actually configured to generate/attach the stub artifact during the install lifecycle. Without the plugin or packaging task, running `install` on a regular Java app will **not automatically create** `-stubs.jar`.

### 6.1. Configuring Stub Runner LOCAL

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs:8095",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutLocalStubTest {

    @Test
    void shouldUseLocallyInstalledStub() {
        // Checkout client points to http://localhost:8095.
        // Verify business behavior based on stub response.
    }
}
~~~

Declaring `repositoryRoot` is unnecessary when using the standard local Maven repository. If the system uses a custom local Maven repository, check repository resolution behavior and settings for your Stub Runner version.

### 6.2. When is LOCAL appropriate?

- Co-developing producer and consumer repositories in parallel.
- Producer has not published an experimental version to a shared repository yet.
- You want to build new stubs, run `install`, and immediately test the consumer on the same machine.
- You want to work offline once all dependencies/artifacts are prepared.

**Weakness:** Machine A has stub `1.2.3`, while machine B has not run `install` or installed different contents under the same version; results can diverge. In CI, install artifacts controllably before consumer tests, or move to `REMOTE` with immutable versions.

### 6.3. Checking the right version in LOCAL

Suppose the new contract changes the response from:

~~~json
{"sku":"SKU-100","available":true,"quantity":8}
~~~

to:

~~~json
{"sku":"SKU-100","available":true,"quantity":0}
~~~

If the consumer still uses an old local artifact, tests won't reflect the new change. Ensure the producer build **regenerated and reinstalled stubs** with the right version, then rerun tests. Never treat green tests against stale local artifacts as proof of compatibility with the new producer.


## 7. REMOTE: fetching stubs from a shared repository

`StubsMode.REMOTE` fits when producer and consumer live in separate repositories or have separate pipelines. Once producer verification passes, the stub artifact is published to **Nexus**, **Artifactory**, or a compatible repository. Consumer CI retrieves the artifact using `groupId:artifactId:version:classifier`.

Example internal repository address:

~~~text
https://repo.example.test/repository/maven-releases/
~~~

This is an **illustrative URL**, not a live repository.

### 7.1. Configuring with @AutoConfigureStubRunner

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs:8095",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot =
        "https://repo.example.test/repository/maven-releases/"
)
class CheckoutRemoteStubTest {

    @Test
    void shouldHandleInventoryResult() {
        // Call Checkout client pointing to stub: localhost:8095
        // and verify consumer behavior.
    }
}
~~~

When the test initializes, Stub Runner locates `inventory-producer-1.2.3-stubs.jar`, downloads or uses appropriate cache, unpacks it, and registers mappings on WireMock.

**Two distinct URLs:** `repositoryRoot` is the **artifact download address**. It is **not** the real producer's HTTP URL or the base URL called by the consumer client. The client calls the **WireMock server started by Stub Runner**.

### 7.2. Configuring with Spring YAML

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: REMOTE
        repository-root: https://repo.example.test/repository/maven-releases/
        ids:
          - "com.example:inventory-producer:1.2.3:stubs"
~~~

Port is omitted, so Stub Runner chooses a port from the available range. Tests should retrieve the runtime port rather than guessing `8095`.

If you both declare `@AutoConfigureStubRunner` and set configuration properties in multiple places, verify effective values and actual precedence before diagnosing.

### 7.3. Protecting repository credentials

Internal repositories usually require authentication. Spring Cloud Contract supports username/password properties, but **never commit credentials to Git**. Use CI secrets/environment variables or supported repository auth mechanisms, granting read-only access when consumers only download.

Example environment variable naming scheme (no secrets included):

~~~text
STUB_REPOSITORY_URL
STUB_REPOSITORY_USER
STUB_REPOSITORY_PASSWORD
~~~

Those values can be mapped to `spring.cloud.contract.stubrunner.repositoryRoot`, `username`, and `password` via Spring/CI configuration mechanisms. Never print tokens in build logs.

### 7.4. When is REMOTE appropriate?

- Producer and consumer belong to different teams or repositories.
- CI needs to pull the exact published stub artifact.
- Artifacts follow a versioning/release/promotion workflow.
- Multiple consumers share one common stub source.
- You want to avoid depending on whether each developer ran `mvn install`.

Drawback: resolution can fail due to network, DNS, authentication, repository outage, caching, or missing artifact/version. That is an **artifact download failure**, not yet a contract mismatch.

## 8. REMOTE with stubs://file:// is not LOCAL

The name `REMOTE` easily leads learners to think this mode **always** downloads over HTTPS. Spring Cloud Contract also supports a downloader with `stubs://` to fetch stubs or contract definitions from a supported location, including a directory on disk.

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot =
        "stubs://file://location/to/producer/target/stubs/"
)
~~~

Meaning of the example:

1. `stubsMode` remains **REMOTE** per the downloader mechanism.
2. `repositoryRoot` points to a source directory with a compatible layout.
3. This is **not** `LOCAL` mode searching Maven artifacts in `~/.m2/repository`.
4. Not every directory containing a few JSON files works out of the box; it must satisfy the conventions/producer coordinates supported by the downloader.

### 8.1. Monorepo case

~~~text
monorepo/
├── inventory-producer/
│   └── target/stubs/
└── checkout-consumer/
    └── src/test/
~~~

The pipeline can build the producer first to produce `target/stubs`, then point the consumer at that directory using `stubs://file://...`. Paths and URI formatting must be adjusted for your environment, OS, and Stub Runner version.

**Note:** An output stubs folder does not prove producer verification passed on its own. For release pipelines, only use or publish artifacts that passed all required verification steps.

## 9. One contract, three stub sources

Inventory Service contract example:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_available')

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

The same artifact `com.example:inventory-producer:1.2.3:stubs`:

- **CLASSPATH:** Test dependency JAR sits on the runtime classpath and is read by the scanner.
- **LOCAL:** JAR is installed in the local Maven repository and read by the resolver.
- **REMOTE:** JAR is published to a shared repository and then downloaded/cached.

Switching modes **does not alter contract semantics**. If responses vary across environments despite identical coordinates/versions, inspect artifact checksums/contents, caches, or release-overwrite policies.

~~~mermaid
flowchart LR
    CP["Test classpath"] --> SR["Stub Runner"]
    LO["Local Maven repository"] --> SR
    RE["Remote repository"] --> SR
    SR --> W["WireMock HTTP stubs"]
    C["Checkout consumer client"] --> W
    T["Consumer assertions"] --> C
~~~


## 10. Obtaining the WireMock port properly

If `ids` includes port `8095`, WireMock attempts to listen on that port. In parallel CI runs, **fixed ports can collide**. Omit the port in the ID so Stub Runner picks an available port from the configured range, then retrieve it using `@StubRunnerPort`, `StubFinder`, or running-stubs properties.

### 10.1. Using @StubRunnerPort

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryStubPortTest {

    @StubRunnerPort("com.example:inventory-producer")
    int stubPort;

    @Test
    void shouldGetStubResponse() {
        RestClient restClient =
            RestClient.create("http://localhost:" + stubPort);

        String json = restClient.get()
            .uri("/api/inventory/SKU-100")
            .retrieve()
            .body(String.class);

        assertThat(json).contains("SKU-100");
    }
}
~~~

This example uses Spring Framework 6.1+ `RestClient`; older versions can use `RestTemplate`, `WebClient`, or a compatible HTTP client. This is mainly a **stub smoke test**. A more valuable consumer test must **invoke Checkout's real `InventoryClient`** with the stub base URL, then assert Checkout's logic.

### 10.2. Using StubFinder

~~~java
@Autowired
StubFinder stubFinder;

@Test
void shouldFindInventory() {
    java.net.URL url =
        stubFinder.findStubUrl("com.example", "inventory-producer");

    assertThat(url).isNotNull();
}
~~~

`StubFinder` is provided via Spring integration or the JUnit Extension/Rule depending on usage. The snippet above requires appropriate imports and test context to run in a real project.

### 10.3. Running-stubs properties

Spring integration can expose:

~~~text
spring.cloud.contract.stubrunner.runningstubs.inventory-producer.port
spring.cloud.contract.stubrunner.runningstubs.com.example.inventory-producer.port
~~~

When the consumer application reads its base URL from configuration, this port property can be referenced instead of hardcoding `8095`. If artifact IDs contain special characters, inspect the exact property name in `Environment`.

### 10.4. Testing the real client rather than just pinging the stub

Suppose Checkout uses this client:

~~~java
public final class InventoryClient {
    private final RestClient restClient;

    public InventoryClient(String baseUrl) {
        this.restClient = RestClient.create(baseUrl);
    }

    public InventoryStock findStock(String sku) {
        return restClient.get()
            .uri("/api/inventory/{sku}", sku)
            .retrieve()
            .body(InventoryStock.class);
    }
}

public record InventoryStock(
    String sku,
    boolean available,
    int quantity
) {}
~~~

This is illustrative code for Java records and Spring `RestClient`, requiring appropriate package/imports. In a test that received `stubPort`:

~~~java
InventoryClient inventory =
    new InventoryClient("http://localhost:" + stubPort);

InventoryStock stock = inventory.findStock("SKU-100");

assertThat(stock.sku()).isEqualTo("SKU-100");
assertThat(stock.available()).isTrue();
assertThat(stock.quantity()).isEqualTo(8);
~~~

A further step is invoking the **Checkout use case** that uses the real `InventoryClient` to protect order-decision logic. Only asserting HTTP output from WireMock does not prove the consumer used the response properly.

## 11. Commonly used Spring properties

| Property | Purpose | Example |
| --- | --- | --- |
| `spring.cloud.contract.stubrunner.ids` | List of artifacts | `com.example:inventory-producer:1.2.3:stubs` |
| `spring.cloud.contract.stubrunner.stubsMode` | Stub source | `CLASSPATH`, `LOCAL`, `REMOTE` |
| `spring.cloud.contract.stubrunner.repositoryRoot` | Repository/location | Nexus/Artifactory URL |
| `spring.cloud.contract.stubrunner.classifier` | Default classifier | `stubs` |
| `spring.cloud.contract.stubrunner.minPort` | Lower bound of WireMock port range | `10000` (default in docs) |
| `spring.cloud.contract.stubrunner.maxPort` | Upper bound of WireMock port range | `15000` (default in docs) |
| `spring.cloud.contract.stubrunner.username` | Repository access username | CI secret |
| `spring.cloud.contract.stubrunner.password` | Repository access password/token | CI secret |
| `spring.cloud.contract.stubrunner.stubsPerConsumer` | Select dedicated stubs per consumer | `false` by default |
| `spring.cloud.contract.stubrunner.consumerName` | Consumer name when needed | Per consumer ID |

Example `application-test.yml` for LOCAL:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: LOCAL
        ids:
          - "com.example:inventory-producer:1.2.3:stubs"
        min-port: 12000
        max-port: 12999
~~~

Spring supports kebab-case property binding in YAML. When multiple configuration sources exist (annotation/profile/env), verify the effective values.

### 11.1. Should you disable failOnNoStubs?

Per documentation, Stub Runner defaults to **failing when no stubs are found**. You can set `failOnNoStubs = false` in `@AutoConfigureStubRunner` or `withFailOnNoStubs(false)` on the Rule/Extension.

For consumer tests that **strictly require stubs**, keep this check enabled; disabling it just to get a green CI risks having **0 stubs while tests report passing**. Disable it only with a clear architectural reason and other assertions proving the required behavior.

### 11.2. When the consumer depends on multiple producers

~~~java
@AutoConfigureStubRunner(
    ids = {
        "com.example:inventory-producer:1.2.3:stubs",
        "com.example:pricing-producer:2.0.1:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot =
        "https://repo.example.test/repository/maven-releases/"
)
~~~

Stub Runner launches a separate WireMock server for each artifact; Inventory's port must be kept distinct from Pricing's. If no ports are fixed, use `@StubRunnerPort` or `StubFinder` for each dependency.

## 12. JUnit 5 Extension: SpringBootTest is not mandatory

Spring Cloud Contract supports `StubRunnerExtension` for JUnit 5 alongside `StubRunnerRule` for JUnit 4. You can use it when you don't want to load a full Spring application context solely to resolve/run stubs.

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.junit.StubRunnerExtension;

import static org.assertj.core.api.Assertions.assertThat;

class PlainJUnitStubTest {

    @RegisterExtension
    static StubRunnerExtension stubs = new StubRunnerExtension()
        .downloadStub("com.example:inventory-producer:1.2.3:stubs")
        .stubsMode(StubRunnerProperties.StubsMode.LOCAL);

    @Test
    void shouldFindRunningStub() {
        java.net.URL url =
            stubs.findStubUrl("com.example:inventory-producer");

        assertThat(url).isNotNull();
    }
}
~~~

This example illustrates recognizing the Extension API; real consumer tests must use that URL to invoke consumer logic. Method names and imports depend on the Spring Cloud Contract/JUnit versions in use.

For REMOTE, the Extension can add `repoRoot(...)` and `stubsMode(StubsMode.REMOTE)`. Choosing Spring annotations or the JUnit Extension is a test-infrastructure decision; it does not change contract semantics.

## 13. Diagnosing errors from download to consumer processing

~~~mermaid
flowchart TD
    A["Consumer test starts"] --> B{"Stub found?"}
    B -- "No" --> R["Mode, coords, repository, classifier"]
    B -- "Yes" --> C{"WireMock starts?"}
    C -- "No" --> P["Port, mappings, dependency versions"]
    C -- "Yes" --> D{"Request matches mapping?"}
    D -- "No" --> M["Method, path, headers, body"]
    D -- "Yes" --> E{"Consumer handles response properly?"}
    E -- "No" --> F["Fix consumer or negotiate contract"]
    E -- "Yes" --> G["Consumer test passes"]
~~~

**Artifact download failures differ from WireMock request-matching failures**, and both differ from consumer code mishandling JSON.

### 13.1. Inspecting loaded WireMock mappings

~~~http
GET /__admin/mappings HTTP/1.1
Host: localhost:8095
~~~

Besides the WireMock admin API, Stub Runner offers `mappingsOutputFolder` to dump mappings into a debug directory when configured. Inspect the **actual registered mappings**, not just the source contracts.

If WireMock returns `404`, common causes are calling the wrong port, mismatched method/path/header/body, or an artifact missing that mapping. An unmatched WireMock `404` is **not equivalent** to a business `404` error response carrying JSON code `ORDER_NOT_FOUND`.

### 13.2. Artifact exists but lacks the expected mapping

Check:

1. Does `ids` have the exact `groupId:artifactId:version:classifier`?
2. Does the JAR file have the right classifier and mapping contents?
3. Is the `META-INF/.../mappings` layout or corresponding format correct?
4. Is the running version hitting a stale cache or stale LOCAL artifact?
5. Did the producer run the generator and attach/publish the stub classifier?
6. Was only a subset of contracts generated due to conditions/filters?
7. Is the test targeting the right producer artifact rather than confusing two services?

With CLASSPATH, inspect **runtime classpath**; with LOCAL, inspect **local Maven repository**; with REMOTE, inspect **repository endpoint, permissions, and artifact metadata**.


## 14. Mode-by-mode troubleshooting table

| Symptom | CLASSPATH | LOCAL | REMOTE |
| --- | --- | --- | --- |
| `Stub not found` | Missing test dependency or wrong JAR layout | Right version/classifier not installed yet | Repository lacks artifact or inaccessible |
| Different version than expected | Dependency version managed/overridden | Stale local JAR or un-reinstalled snapshot | `+` picked another build, stale metadata/cache |
| `401/403` during download | Possibly build dependency resolver | Rare during local artifact lookup | Repository credentials/permissions |
| Timeout during startup | Pre-test build dependency resolution | Unusual local I/O | Network/proxy/TLS/repository |
| WireMock port conflict | Fixed port occupied | Same | Same |
| WireMock runs yet `404` | Request/mapping mismatch | Same | Same |
| Missing mapping | Artifact packaged wrongly | Local stub JAR lacks mapping | Published artifact incomplete or wrong version |
| Passes locally, fails in CI | CI classpath differs from local | CI did not install artifact | CI missing secret/cannot reach repository |

### 14.1. Useful debugging order

Start from the **source** and work toward the **application**:

1. Check the effective `stubsMode`: is it running `CLASSPATH`, `LOCAL`, or `REMOTE`?
2. Read the full `ids`, identifying `groupId`, `artifactId`, `version`, `classifier`, and `port`.
3. Prove the **artifact actually exists** at the corresponding source.
4. Prove the stub JAR contains the **expected mapping**.
5. Prove WireMock is listening on the test port being targeted.
6. Compare the consumer's request against mapping method/path/headers/body.
7. Compare the actual response against the schema agreed upon by the consumer.
8. Only then decide whether to fix **consumer**, **producer**, **contract**, or **CI configuration**.

For example, a `401` from a repository during download differs from an HTTP `401` returned by WireMock per an **authentication contract**. Do not treat them as the same kind of error.

### 14.2. Never silence errors just to make CI green

Dangerous "quick fixes":

- Setting `failOnNoStubs=false` when tests strictly require stubs.
- Switching `REMOTE` to `LOCAL` when CI hasn't installed the artifact.
- Using version `+` hoping it will fix missing-published-version errors.
- Removing request matchers so any request returns the same response.
- Copying stub JSON manually into the consumer and forgetting to sync from the producer.
- Skipping JSON body checks and asserting only HTTP `200`.

Every one of these undermines contract testing and lets breaking changes slip through.

## 15. Versioning and caching: keys to reproducibility

Stub Runner cannot reliably guard compatibility if the same consumer commit runs against stubs that **change unpredictably**.

### 15.1. Pin versions instead of always using +

Example:

~~~text
Recommended in CI:
  com.example:inventory-producer:1.2.3:stubs

Use with caution:
  com.example:inventory-producer:+:stubs
~~~

`+` is helpful when intentionally testing "latest version," yet unsuitable as a CI baseline requiring strict reproducibility. Once a new artifact is published, the same source commit could start pulling a new stub and fail with no consumer code change.

### 15.2. Snapshots and releases behave differently

- **Snapshot:** Can be republished under the same version; suitable for development, yet prone to content/cached metadata drift.
- **Immutable release:** Should be treated as never overwritten, aiding control and traceability.
- **CLASSPATH:** Versions can be locked via dependency management.
- **LOCAL:** Two machines can install different contents under identical coordinates if discipline slips.
- **REMOTE:** Requires clear artifact retention, authentication, caching, and promotion policies.

### 15.3. Three ways to limit environment drift

1. Explicitly record the stub coordinates/version used by consumer CI.
2. Never overwrite a release with different contents under the same version; store metadata/checksums when needed.
3. Run consumer contract tests against artifacts accepted by producer verification, and verify exact artifact versions at release time.

**A passing test on an old stub does not prove consumer compatibility with new producer changes.** When the producer updates its contract, update/publish the artifact and test against the matching version per release policy.

## 16. Practice: moving a consumer test across all three modes

### 16.1. Scenario and inputs

Producer `Inventory Service` exposes:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

Response contract:

~~~json
{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

Assume the producer already has valid Groovy/YAML contracts and configured Spring Cloud Contract Verifier to generate tests and attach the `stubs` classifier on build. Consumer `Checkout Service` must read `available` and `quantity` to decide whether to allow order creation.

**Common task:** For each mode, start Stub Runner, invoke Checkout's real `InventoryClient`, verify response types, and verify Checkout rejects an order when requested quantity exceeds `quantity`.

### 16.2. Exercise A — CLASSPATH

1. Ensure `inventory-producer-1.2.3-stubs.jar` can be resolved by Maven/Gradle.
2. Declare the stub JAR as a **test dependency** as in Section 5.
3. Configure:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs",
    stubsMode = StubRunnerProperties.StubsMode.CLASSPATH
)
~~~

4. Use `@StubRunnerPort` or `StubFinder` to obtain the WireMock URL.
5. Run the consumer test through the real `InventoryClient`; verify fields and Checkout logic.
6. Try removing the stub dependency from the test runtime classpath to observe the difference between **missing JAR** and **unmatched request**.

**Question:** Why does having the stub JAR inside `~/.m2/repository` without adding it to the test classpath cause `CLASSPATH` to miss mappings?

### 16.3. Exercise B — LOCAL

1. On the producer, build generated tests and the stub JAR per configured plugin/lifecycle.
2. Run the install step to the local Maven repository:

~~~bash
# Run in producer project, illustrative once plugin is configured
./mvnw -B clean install
~~~

3. Verify the local repository contains `inventory-producer-1.2.3-stubs.jar`.
4. In Checkout, remove the requirement of declaring the stub JAR as a test dependency if testing pure LOCAL.
5. Set:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

6. Run the consumer test and record the outcome.
7. Change the producer contract response, regenerate and reinstall the artifact, and test the consumer against the matching new version.

**Question:** Why can `LOCAL` pass on a developer's machine yet fail on a clean CI runner? What artifact must be prepared before running consumer tests?

### 16.4. Exercise C — REMOTE

1. Producer passes verification and publishes the stub classifier to a shared repository (e.g., Nexus/Artifactory).
2. Consumer configures:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot =
        "https://repo.example.test/repository/maven-releases/"
)
~~~

3. Supply credentials via CI secrets if the repository requires authentication.
4. Retrieve the dynamic port, invoke `InventoryClient`, and confirm Checkout handles the response properly.
5. Try a non-existent version to observe a **resolution** failure.
6. Keep the artifact valid while changing the request path on the consumer to observe a **WireMock unmatched request** error.

**Question:** Why is `REMOTE` better suited than `LOCAL` for consumer CI in a separate repository, and why pin versions instead of using `+`?

### 16.5. Evaluation table for the three exercises

| Aspect | CLASSPATH | LOCAL | REMOTE |
| --- | --- | --- | --- |
| Where were stubs proven to live? | Test dependency/classpath | Local Maven repository | Shared artifact repository |
| Depends on running producer during consumer test? | No | No | No |
| Must be published prior to test? | Artifact needed for dependency resolution | Only local install needed | Must be published to repository |
| Can run offline at runtime? | Yes, if dependencies are cached | Yes, if local artifact is complete | Should not rely on offline without cache |
| Key items to record in reports | Dependency/version | Installed artifact/version | Repository/version/credentials |

### 16.6. Adding a 404 error branch

Suppose the contract also defines `GET /api/inventory/SKU-404` returning:

~~~json
{
  "code": "INVENTORY_NOT_FOUND"
}
~~~

with HTTP `404` and `Content-Type: application/json`. Write a consumer test verifying Checkout displays or logs the "SKU not found" state per requirements. **Do not treat a 404 from an unmatched request as a business response**, since it may lack `code: INVENTORY_NOT_FOUND`.

## 17. Choosing a mode by context

| Context | Usually suitable mode | Reason |
| --- | --- | --- |
| All stubs are pinned-version test dependencies | **CLASSPATH** | Scanner reads the prepared classpath |
| Two repos co-developed on one machine for quick iteration | **LOCAL** | Build/install producer then resolve locally |
| Consumer CI separate from producer CI using shared registry | **REMOTE** | Versioned artifacts are shared |
| Monorepo with direct stubs output directory | **REMOTE + stubs://file://** | Downloader reads from non-`.m2` location |
| Tests run in network-restricted environment | **CLASSPATH** or **LOCAL** | Prepare dependencies/artifacts beforehand |
| Need to test against an approved release stub | **REMOTE** with fixed version | Artifact traceability and release promotion |

These are selection guidelines, **not rigid rules**. CI can still use CLASSPATH if dependencies are carefully managed; LOCAL can also work in a multi-module pipeline with a deterministic artifact-install step. What matters most is **clear stub sources, reproducible versions, and tests genuinely exercising them**.

## 18. Checklist before considering Stub Runner properly configured

- [ ] At least one producer contract matches the interface used by the consumer.
- [ ] Producer verification was generated and executed, not just stub mappings created.
- [ ] Stub artifact has the expected classifier/layout and version.
- [ ] `ids` specifies exact `groupId:artifactId:version:classifier[:port]`.
- [ ] `stubsMode` is chosen deliberately: `CLASSPATH`, `LOCAL`, or `REMOTE`.
- [ ] CLASSPATH: Stub JAR is present on the test runtime classpath.
- [ ] LOCAL: Artifact is installed and present in the local Maven repository.
- [ ] REMOTE: Repository URL, credentials, and artifact version are verified.
- [ ] With `stubs://file://`, compatible mode/location and layout are used; not confused with Maven LOCAL.
- [ ] WireMock port is retrievable via `@StubRunnerPort`, `StubFinder`, or properties.
- [ ] Consumer's client actually calls WireMock rather than the real producer.
- [ ] Consumer tests invoke consumer code and verify behavior, not merely pinging the stub.
- [ ] Request method, URL, headers, query, and body match mappings.
- [ ] Tests verify status codes and JSON responses of critical error branches.
- [ ] `failOnNoStubs` is not disabled without justification when tests require stubs.
- [ ] CI uses traceable stub versions, avoiding `+` when reproducibility is needed.
- [ ] Ports and test data do not collide during parallel runs.
- [ ] Repository tokens are never placed in code or build logs.
- [ ] Artifact resolution errors, WireMock matching errors, and consumer app bugs are clearly distinguished.
- [ ] Stubs are published by the pipeline only after required producer verification passes.

## 19. References

- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): the three modes `CLASSPATH`, `LOCAL`, `REMOTE`, classpath scanning, WireMock creation.
- [Spring Cloud Contract — Common Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html): `ids`, `classifier`, `minPort`, `maxPort`, `repositoryRoot`, and version defaults.
- [Spring Cloud Contract — Stub Runner JUnit Rule and JUnit 5 Extension](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-junit.html): `StubRunnerExtension`, `StubFinder`, `@StubRunnerPort`, and running stubs.
- [Spring Cloud Contract — Fetching Stubs from a Location](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-stubs-protocol.html): using `stubs://file://` with REMOTE mode.
- [Spring Cloud Contract — Fail on No Stubs](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-fail-on-no-stubs.html): behavior when stubs are not found.
- [Spring Cloud Contract — Developing Your First Application](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html): lifecycle of producer verification, stub publishing, and consumer tests.

**Remember:** **CLASSPATH** scans stubs already on the classpath; **LOCAL** looks up stub artifacts in the local Maven repository; **REMOTE** pulls from a shared repository or a supported location such as `stubs://file://`. The three modes only change the **stub resolution source**, not the contract the consumer must satisfy. Pin versions when reproducibility matters, retrieve the WireMock port accurately, invoke real consumer code, and run producer verification before publishing stubs in CI.
