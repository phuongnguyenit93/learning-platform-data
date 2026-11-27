# Classifier, Group ID, Artifact ID, and Version

## Lesson objectives

In **Spring Cloud Contract**, a producer declares HTTP or messaging behavior using **Groovy DSL** or **YAML DSL**. From those contracts, **Contract Verifier** generates producer-side tests and creates **stubs** for consumers to use via **Stub Runner**. When the producer is built and published, stubs are typically packaged into a **separate artifact with a classifier**, managed and resolved by coordinates much like a Maven dependency.

Stub coordinates are an essential part of a CI workflow that catches incompatible API changes. If a consumer accidentally fetches stubs from another service, another version, or an artifact without the `stubs` classifier, the test suite may fail because stubs cannot be found; worse, the consumer might PASS against a **stale stub** and falsely conclude that the new producer remains compatible.

Within the **Stub Generation and Packaging** chapter, this lesson focuses on the four coordinate components—**group ID, artifact ID, version, and classifier**—and how they connect to the stub JAR file, artifact repository, Stub Runner, and test evidence.

After this lesson, you will be able to:

- Read and explain `groupId:artifactId:version:classifier` coordinates.
- Distinguish the producer's main artifact from its stub artifact of the same version, usually carrying the `stubs` classifier.
- Understand how a contract produces generated producer tests, stub mappings, and a stub JAR.
- Configure consumer tests to pull the right stub via Stub Runner in the appropriate artifact-resolution mode.
- Troubleshoot missing artifacts, wrong classifiers, mismatched versions, or name collisions across multiple services.
- Establish release gates ensuring stubs and producer builds originate from the same tested contract revision.

## 1. Why do stubs need separate coordinates?

Imagine two services:

- **Order Service** is the producer of endpoint `GET /api/orders/{id}`.
- **Checkout Service** is the consumer, calling Order Service during the checkout flow.

When writing consumer tests, Checkout Service does not necessarily need to boot the entire Order Service along with its database, queues, and dependencies. Instead, Checkout can use an **HTTP stub** simulating the agreed requests and responses.

~~~mermaid
flowchart TD
    A["Groovy/YAML contracts<br/>Order Service"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer tests"]
    B --> D["Stub mappings + responses"]
    C --> E["Order Service build<br/>producer test PASS"]
    D --> F["Stub JAR with stubs classifier"]
    E --> G["Release gate"]
    F --> G
    G --> H["Artifact repository<br/>coordinates G:A:V:stubs"]
    H --> I["Checkout CI<br/>Stub Runner loads right stub version"]
    I --> J["Consumer integration tests"]
~~~

The **artifact repository** here can be an internal Maven repository or an artifact store compatible with Stub Runner's resolution mechanism. It is distinct from the HTTP endpoint the stub itself serves while tests run.

A stub JAR needs an identity so multiple consumers fetch the right build. A filename alone is not enough because different teams can have identically named modules or multiple releases.

## 2. The four coordinate components

Suppose the producer is declared with Maven coordinates:

~~~xml
<groupId>com.example.orders</groupId>
<artifactId>order-service</artifactId>
<version>1.4.2</version>
~~~

The stub is published under the same base coordinates with classifier `stubs`:

~~~text
groupId     = com.example.orders
artifactId  = order-service
version     = 1.4.2
classifier  = stubs

Short coordinate for stub:
com.example.orders:order-service:1.4.2:stubs
~~~

| Component | Example | Responsibility |
| --- | --- | --- |
| **group ID / groupId** | `com.example.orders` | Owning identifier namespace that distinguishes modules across different namespaces |
| **artifact ID / artifactId** | `order-service` | Specific module/artifact name being published |
| **version** | `1.4.2` | Distinguishes builds/releases that may have different behavior |
| **classifier** | `stubs` | Distinguishes the stub variant from the main artifact sharing the same group ID, artifact ID, and version |

**Remember:** a classifier is **not** part of an HTTP endpoint name, Java package, or class name. It is an attribute of the **published artifact**.

### Comparing the main artifact and the stub

~~~text
Producer main artifact:
  com.example.orders:order-service:1.4.2
  order-service-1.4.2.jar

Stub artifact:
  com.example.orders:order-service:1.4.2:stubs
  order-service-1.4.2-stubs.jar
~~~

Normally, both artifacts share `groupId`, `artifactId`, and `version` while differing in `classifier`. The main artifact holds the application/library; the stub artifact holds the content consumer tests need to simulate published behavior.

The filenames are **illustrative Maven conventions**. Exact outputs and packaging depend on the plugin, project configuration, and artifact type.

## 3. Maven coordinates are not Docker tags or stub server addresses

The following identifiers serve different purposes:

| Identifier | Example | Represents |
| --- | --- | --- |
| Maven group ID | `com.example.orders` | Artifact namespace inside the repository |
| Maven artifact ID | `order-service` | Module/artifact name |
| Maven version | `1.4.2` | Artifact version |
| Classifier | `stubs` | Stub JAR variant |
| Docker image tag | `order-service:1.4.2` | Deployment image version; not automatically a stub coordinate |
| Stub server port | `8090` | Port the stub server listens on during consumer tests |
| HTTP URL | `/api/orders/ORD-1001` | Endpoint simulated by the stub |

A consumer may use port `8090` to call stubs for producer version `1.4.2`. **`8090` is not a version**. Similarly, a Spring Boot application name or Java package is not a reliable sole source for inferring group/artifact IDs.

In multi-module systems, verify **which module actually publishes the stubs**. An `order-contracts` module might hold the contract sources, whereas the stub artifact Stub Runner needs is published under `order-service`.

## 4. What does a stub JAR normally contain?

An HTTP stub generated from contracts may contain:

- **Request mappings:** conditions matching HTTP method, URL, query parameters, headers, and body.
- **Response definitions:** status, headers, body, body files, or corresponding response components.
- **Contract sources:** a copy of the DSL or metadata for tracing contract content, depending on packaging.
- **Organizational/path structure:** helps Stub Runner locate mappings for the right artifact.

Example of a common layout under `META-INF`:

~~~text
order-service-1.4.2-stubs.jar
└── META-INF/
    └── com.example.orders/
        └── order-service/
            └── 1.4.2/
                ├── mappings/
                │   └── get-paid-order.json
                └── contracts/
                    └── get-paid-order.yml
~~~

This is an **illustrative layout**. Exact filenames, directories, and whether auxiliary resources are included depend on the version, plugin, and configuration; inspect the **actual generated JAR contents**. Never conclude a project's JAR is packaged properly based solely on an illustrative diagram.

Example condensed mapping for the endpoint:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/orders/ORD-1001"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": "ORD-1001",
      "status": "PAID"
    }
  }
}
~~~

This is a **WireMock-style illustration**, not verbatim output from a specific Contract Verifier version. Actual mappings may include extra header/body matchers, priorities, or different response formats.

**A stub JAR is not a full replica of the producer.** Stubs simulate declared scenarios and do not include the database, business logic, or full production behavior.

## 5. From contract to artifact: two things to verify separately

The producer has a contract:

~~~yaml
description: "Get paid order"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

The build must accomplish two **related yet non-interchangeable** tasks:

1. **Generate and run producer contract tests**: verify the producer build being tested satisfies requests and responses per the contract.
2. **Generate and package stubs**: build an artifact containing mappings/responses for consumers to use.

| Question | Type of evidence required |
| --- | --- |
| Does the producer return 200 and the right JSON? | Results of executed generated producer tests |
| Does the stub JAR contain that mapping? | Inspection of the packaged JAR contents |
| Did the consumer fetch the right stub? | Coordinates, version, and artifact resolution logs |
| Does the consumer handle the response properly? | Consumer integration tests with Stub Runner |
| Is the new producer compatible with all consumers? | Results across supported consumers and scenarios, not just a single stub test |

A passing producer test does not by itself prove the artifact was published to the right repository; an existing JAR does not prove the producer ran contract tests.

## 6. Generating and packaging with Maven

In Maven projects, Spring Cloud Contract is usually configured via `spring-cloud-contract-maven-plugin`.

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>APPROPRIATE_VERSION</version>
            <extensions>true</extensions>
            <configuration>
                <contractsDirectory>
                    src/test/resources/contracts
                </contractsDirectory>
                <baseClassForTests>
                    com.example.orders.contract.OrderContractBase
                </baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`APPROPRIATE_VERSION` is a placeholder to replace with a version compatible with your Spring Boot/Spring Cloud stack and project setup. This is **not yet a complete POM**, as it still requires test libraries and other configuration.

When the plugin and build lifecycle are wired properly, the build generates tests/stubs and produces an artifact with the `stubs` classifier during packaging. Specific goals/lifecycles should be checked against your plugin version. Never assume a Maven command published stubs solely because it exited with code 0.

Illustrative development workflow:

~~~text
./mvnw clean verify
  -> generate and run producer contract tests
  -> verify count of executed generated tests
  -> verify stub is generated/packaged per lifecycle

./mvnw install
  -> install packaged artifacts into local Maven repository
  -> verify the stubs classifier was also installed
~~~

In CI, publishing to an artifact repository is typically a separately controlled phase permitted only after producer checks and artifact inspections PASS. Some setups use Maven `deploy` or an organizational publishing pipeline; what matters is checking **coordinates and contents** after publishing.

### Maven dependency on a stub

If a consumer test needs to declare the stub as a Maven dependency, it can use:

~~~xml
<dependency>
    <groupId>com.example.orders</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.2</version>
    <classifier>stubs</classifier>
    <type>jar</type>
    <scope>test</scope>
</dependency>
~~~

This shows all components in a **dependency declaration**. Stub Runner has its own ID syntax to pick artifacts and ports when running tests; do not mechanically copy field ordering from one coordinate format into another.

## 7. Generating and packaging with Gradle

With Gradle, you can use the Spring Cloud Contract plugin and configure contracts:

~~~groovy
plugins {
    id 'org.springframework.cloud.contract' version 'APPROPRIATE_VERSION'
}

group = 'com.example.orders'
version = '1.4.2'

contracts {
    contractsDslDir = file('src/test/resources/contracts')
    baseClassForTests =
        'com.example.orders.contract.OrderContractBase'
}
~~~

This is **Gradle Groovy DSL**, not Kotlin DSL syntax. In addition, a real application needs dependencies, a test framework, and appropriate source set configuration.

In supported versions, the Spring Cloud Contract Gradle plugin supplies tasks for test generation and stub packaging, commonly named things like `generateContractTests` or `verifierStubsJar`. **Task names, dependencies, classifiers, and how the stub JAR enters publications must be verified against your plugin version**.

Do not assume `./gradlew build` publishes artifacts. Local building, publishing to Maven local, and publishing to a remote repository are three separate actions:

~~~text
Generate and test:
  ./gradlew clean build

Install artifact into local repo if project uses maven-publish:
  ./gradlew publishToMavenLocal

Publish remote:
  use configured and approved publication/repository task
~~~

**Before publishing**, confirm the artifact with the `stubs` classifier is actually attached to the Maven publication. If Gradle publishes only the main JAR, consumers cannot resolve `order-service:1.4.2:stubs` even if all producer tests PASS.

### Distinguishing Gradle project name from artifact ID

`group` and `version` are standard metadata in Gradle, whereas a publication's `artifactId` can depend on the project name or a configured `MavenPublication`. A project named `order-service-app` can publish artifact ID `order-service` if the publication is configured that way.

**Never guess the artifact ID from the build folder name.** Inspect the Maven publication metadata after publishing and use those exact coordinates in Stub Runner.

## 8. How does Stub Runner pick the right artifact?

On the consumer side, **Stub Runner** can fetch the stub JAR from a local Maven repository or a remote artifact repository and start a stub server.

Example consumer integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = {"com.example.orders:order-service:1.4.2:stubs:8090"},
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutContractIntegrationTest {

    @Test
    void checkoutShouldHandlePaidOrder() {
        // Configure Checkout's HTTP client to call the stub on port 8090.
        // Execute Checkout business logic and assert consumer outcome.
    }
}
~~~

This code illustrates only **how to declare Stub Runner**, not a complete test. The consumer also needs test dependencies and configuration pointing its HTTP client to the started stub server.

In this example, the Stub Runner ID has five parts:

~~~text
com.example.orders:order-service:1.4.2:stubs:8090
        |               |       |     |    |
      group           artifact version classifier port
~~~

| Component | Value | What to understand |
| --- | --- | --- |
| group | `com.example.orders` | Artifact namespace |
| artifact | `order-service` | Artifact providing stubs |
| version | `1.4.2` | Specific version under test |
| classifier | `stubs` | Selects the stub JAR rather than the main application JAR |
| port | `8090` | Stub server port used during tests |

**Port is not part of the artifact's Maven coordinates.** Port is a Stub Runner runtime parameter in this ID syntax. Changing the port to `8091` does not change the artifact's version or classifier.

### Some fields may be omitted

Stub Runner versions support ID forms with optional segments and dynamic port selection. Never guess how the parser interprets a string with missing fields in critical examples; use **complete, explicit coordinates** to reduce confusion, then adjust according to your version's documentation.

## 9. LOCAL, REMOTE, and CLASSPATH modes

Having the right coordinates is not enough; you must know **where Stub Runner fetches the artifact from**.

| Mode | General meaning | Points to watch |
| --- | --- | --- |
| **LOCAL** | Searches for stubs in the local Maven repository on the test machine | Must install/publish locally at the right version before testing |
| **REMOTE** | Resolves from a configured repository | Depends on repository URL, access rights, metadata, and caching policy |
| **CLASSPATH** | Uses stubs present on the classpath per supported mechanism | Requires the right resources/JAR on classpath and matching name/version resolution |

Example configuring a remote repository via annotation when supported by the version:

~~~java
@AutoConfigureStubRunner(
    ids = {"com.example.orders:order-service:1.4.2:stubs:8090"},
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.test/maven-releases"
)
~~~

`repo.example.test` is an **illustrative URL**, not a real repository. In practice, repository credentials should be managed via CI secrets; never commit usernames, passwords, or production tokens into contract sources.

If a consumer runs `LOCAL` when stubs were only published remotely, Stub Runner may report the artifact missing; if running `REMOTE` with a wrong `repositoryRoot` or insufficient token permissions, the error is a resolution failure rather than an API behavior failure.

## 10. How does a classified stub JAR differ from the main JAR?

A frequent error is when the consumer specifies only:

~~~text
com.example.orders:order-service:1.4.2
~~~

when what it needs to download is:

~~~text
com.example.orders:order-service:1.4.2:stubs
~~~

These two coordinates do not differ only by characters. They request **two distinct artifact variants**:

- The unclassified artifact may be the producer's application JAR.
- The artifact with classifier `stubs` is the stub bundle built for consumer testing.

Do not alter the artifact ID to `order-service-stubs` if the project properly publishes an artifact with classifier `stubs`, because that is a different coordinate. Conversely, if a team **intentionally** publishes stubs under a separate artifact ID, use the exact coordinates declared by the publication instead of guessing from default conventions.

### Resolution inside a Maven repository

Suppose `groupId` is `com.example.orders`, `artifactId` is `order-service`, and `version` is `1.4.2`. A standard Maven repository can organize them as:

~~~text
com/example/orders/order-service/1.4.2/
├── order-service-1.4.2.pom
├── order-service-1.4.2.jar
└── order-service-1.4.2-stubs.jar
~~~

Maven repository paths split dotted group IDs into directories; that is the **artifact storage convention**, distinct from how `META-INF` contents are packaged inside the JAR.

If `order-service-1.4.2.jar` exists while `order-service-1.4.2-stubs.jar` does not, check stub generation, classifier attachment, and publication. Do not jump to blaming matcher bugs.

## 11. Group ID and artifact ID in multi-module projects

Suppose a system has this structure:

~~~text
commerce-platform/
├── order-api/
├── order-domain/
├── order-service/
├── order-contracts/
└── checkout-service/
~~~

You must answer **which artifact actually publishes stubs**:

| Module | What it might do | What not to assume |
| --- | --- | --- |
| `order-api` | Holds public interfaces/DTOs | Not necessarily where stubs are published |
| `order-domain` | Business logic | Does not necessarily hold HTTP/message contracts |
| `order-service` | Producer running endpoints | May publish stubs under the service's coordinates |
| `order-contracts` | Holds shared DSL sources | Does not automatically produce a Stub Runner artifact named after the folder |
| `checkout-service` | Consumer | Does not fetch stubs using the consumer's own artifact ID |

When contracts live in a separate repository, the contract source location and published stub coordinates may differ. CI must record:

- Revision of the contracts repository.
- Producer module/build that generated and verified tests.
- Artifact with classifier `stubs` published by that build.
- Which consumer version tested against which stub artifact.

If two producers share artifactId `service-api` across two different groupIds, Stub Runner must specify **the exact group ID** to avoid fetching the wrong service.

## 12. Versioning: why avoid dynamic versions in release CI?

During development, test authors may use dynamic versions or `+` in Stub Runner syntax (if supported by the library version). That is handy for quick checks, yet unsuitable for release gates.

Example **not to use as immutable release evidence**:

~~~java
@AutoConfigureStubRunner(
    ids = {"com.example.orders:order-service:+:stubs:8090"}
)
~~~

If `+` resolves to the latest version per repository/tooling behavior, the same consumer commit can pull **two different stubs** across two runs. CI outcomes become hard to reproduce.

For pre-release verification, pick a fixed version:

~~~text
Producer build preparing release: order-service 1.4.2
Contract revision:                contracts commit def456
Stub artifact:                    com.example.orders:order-service:1.4.2:stubs
Consumer uses stub version:       1.4.2
~~~

**A fixed version alone does not guarantee artifact immutability.** If a repository allows overwriting an existing release version, the same coordinates can point to new bytes. Release gates should enforce immutable artifact policies, checksums, and provenance metadata.

### SNAPSHOT vs. release versions

| Version type | Example | Characteristics to consider |
| --- | --- | --- |
| **SNAPSHOT** | `1.4.3-SNAPSHOT` | Commonly used during development and its contents can change over time |
| **Release** | `1.4.2` | Should bind to an immutable set of bytes once published |
| **Dynamic/range** | `+` or tool-supported ranges | Can resolve to a different artifact on the next run |

There is no rule that "bumping patch/minor guarantees compatibility". **Compatibility is a property verified by contracts and active consumers**, never inferred solely from numbering conventions.

## 13. Cross-version compatibility must be tested pairwise

Suppose the producer prepares to release `1.5.0`. An older consumer `checkout-service:2.8.0` still expects the endpoints and schema of `1.4.2`.

| Producer/stub under consideration | Consumer under test | Question |
| --- | --- | --- |
| Producer 1.4.2 + stubs 1.4.2 | Checkout 2.8.0 | Does the old baseline work? |
| Producer 1.5.0 + stubs 1.5.0 | Checkout 2.8.0 | Is the old consumer still compatible with the new producer? |
| Producer 1.5.0 + stubs 1.5.0 | Checkout 2.9.0 | Does the new consumer work with the new interface? |

If Checkout 2.8.0 PASSES against stub 1.4.2, **you cannot conclude** it will PASS against producer 1.5.0. To verify backward compatibility, test Checkout 2.8.0 against **the new stub** from producer 1.5.0 alongside passing producer test evidence.

A change such as:

~~~text
Before: GET /api/orders/ORD-1001 -> {"status":"PAID"}
After:  GET /api/orders/ORD-1001 -> {"paymentStatus":"PAID"}
~~~

can break consumers even though the HTTP status and URL stayed identical. The new stub version lets consumer tests catch that difference, provided the new contract is written accurately and the consumer actually asserts the field it uses.

## 14. What must CI verify before publishing stubs?

### Recommended pipeline

~~~mermaid
flowchart TD
    A["Checkout producer + contract revision"] --> B["Verify exact G:A:V coordinates"]
    B --> C["Generate producer contract tests and stubs"]
    C --> D{"Did generated tests actually run & PASS?"}
    D -->|No| X["BLOCK"]
    D -->|Yes| E["Inspect JAR with stubs classifier"]
    E --> F{"Mappings/responses accurate & complete?"}
    F -->|No| X
    F -->|Yes| G["Publish immutable artifact/version"]
    G --> H["Consumer CI resolves G:A:V:stubs"]
    H --> I{"Correct artifact and checksum?"}
    I -->|No| X
    I -->|Yes| J["Run Stub Runner and consumer tests"]
    J --> K{"Did consumer PASS?"}
    K -->|No| X
    K -->|Yes| L["Save evidence and decide rollout"]
~~~

Things to check:

1. **Group/artifact/version** genuinely belong to the producer under verification, not an assumed module.
2. **Contracts are fully discovered**, not 0 contracts due to a wrong folder.
3. **Generated producer tests actually execute**, without being skipped or excluded.
4. **Stub JAR carries the right classifier**, not solely the application JAR.
5. **Stub JAR contains the exact mappings** from the tested contract revision and contains no sensitive production data.
6. **Artifact publishes cleanly** to the target repository with traceable metadata, version, and checksum.
7. **Consumer CI runs against the new stub**, rather than accidentally reusing a local cache or stale build.
8. **Consumer tests assert real consumer logic**, rather than only verifying the stub server booted.

### Example build evidence record

~~~yaml
# Illustrative evidence designed by the project,
# not default output from Spring Cloud Contract.
producer_module: order-service
producer_revision: "producer@abc123"
contracts_revision: "contracts@def456"
group_id: com.example.orders
artifact_id: order-service
version: "1.4.2"
classifier: stubs
expected_contracts:
  - get_paid_order
  - get_missing_order
generated_producer_tests: PASS
stub_jar_verified: true
stub_artifact: "com.example.orders:order-service:1.4.2:stubs"
consumer_version: "checkout-service:2.8.0"
consumer_stub_tests: PASS
~~~

A line saying `stub_jar_verified: true` only holds value if CI actually inspects artifact contents rather than someone writing pretty YAML by hand. Build/test reports and artifact inspection steps must back it up as evidence.

## 15. Common errors when resolving stub artifacts

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Stub Runner reports artifact not found | Wrong group ID, artifact ID, version, or classifier | Compare publication metadata with coordinates used by consumer |
| Application JAR exists, stubs JAR missing | Stub classifier not packaged/published | Inspect plugin tasks/lifecycle and publication |
| Right artifact ID, wrong service downloaded | Different group ID or name collision across namespaces | Specify the full group ID |
| Test uses `latest`/`+` and results change | Dynamic version resolved to a newer artifact | Pin version and checksum |
| Consumer CI stays green after a breaking change | Using a stale stub or not asserting the changed field | Check artifact download logs, contract revision, and assertions |
| `LOCAL` cannot find stub | Stub not installed in local Maven of the runner | Install the exact artifact or use configured `REMOTE` |
| `REMOTE` fails while `LOCAL` passes | Wrong `repositoryRoot`, permissions, or metadata | Check repo URL, credentials, proxy, and cache |
| Stub server runs yet endpoint returns 404 | Mapping fails to match request or wrong stub | Inspect method/URL/headers/body and mappings inside JAR |
| Tests pass only on author's machine | Depends on unpublished local Maven artifact | Use controlled CI repository and clean independent builds |
| No changes visible after re-publishing | Repo/cache serves stale bytes or release was overwritten | Compare checksums/metadata; avoid overwriting releases |

Do not rush to edit contracts when the problem is **artifact resolution**. Separate four questions:

- Does the artifact exist?
- Does it carry the right classifier and version?
- Does it contain the expected mappings inside?
- Does the mapping match the request the consumer sends?

If any of the first three is wrong, loosening matchers usually just masks the real failure.

## 16. Distinguishing HTTP and message contracts during packaging

For HTTP, stub artifacts typically carry mappings for a stub server to simulate responses. For **message contracts**, artifacts can contain information/stubs supported by Stub Runner messaging to emit sample messages via **labels/triggers** according to the integration.

| Aspect | HTTP contract | Message contract |
| --- | --- | --- |
| Common input | Method/URL/headers/body | `triggeredBy` or `messageFrom` |
| Output | HTTP response | `outputMessage` with body, headers, `sentTo` |
| Consumer test | Calls HTTP stub server | Triggers/receives message stub depending on adapter |
| Artifact | Can use `stubs` classifier | Also requires exact artifact/version; message triggers depend on support |
| Additional infrastructure | HTTP stub server | Binder/broker/message verifier per config |

Never infer that a stub JAR containing message contracts lets Stub Runner **automatically create** production Kafka topics, RabbitMQ exchanges, or JMS queues. Consumers must configure a test environment compatible with the adapter and message stub scenario used.

Group ID, artifact ID, version, and classifier still identify **the right stub source**, though they do not describe full broker configuration.

## 17. Security and artifact governance

Stub JARs are often shared more widely than producer source code. They can contain sample payloads, headers, response bodies, and metadata. Therefore:

- Use **synthetic data**; never copy production emails, accounts, tokens, or transactions into contracts.
- Never embed API keys, bearer tokens, passwords, or secret admin URLs in stub mappings.
- Audit packaged artifacts, not just Groovy/YAML sources.
- Manage repository read/write permissions and CI credentials on least-privilege principles.
- Never log repository access tokens in test source or failure logs when artifact resolution fails.
- Maintain retention policies and key revocation/rotation procedures if old artifacts ever leaked sensitive data.

Bumping to a new version does not automatically erase leaked data from older artifact versions. If a secret is found in a published stubs JAR, follow incident response rather than merely editing the contract file.

## 18. Practice exercises

### Exercise A — Reading coordinates

Given Stub Runner ID:

~~~text
vn.learning.platform:inventory-service:3.2.1:stubs:8100
~~~

**Task:** identify group ID, artifact ID, version, classifier, and port; explain which part is **not** part of the Maven artifact coordinates.

**Hint:** `8100` is the stub server port. The preceding four components identify the stub artifact.

### Exercise B — Finding the reason for a missing JAR

The Maven repository contains:

~~~text
inventory-service-3.2.1.pom
inventory-service-3.2.1.jar
~~~

The consumer configures `vn.learning.platform:inventory-service:3.2.1:stubs:8100` yet fails to download.

**Task:** identify the missing file and where to investigate in the producer pipeline.

**Hint:** `inventory-service-3.2.1-stubs.jar` is missing. Check stub generation, classifier attachment, publishing, and actual version.

### Exercise C — Picking the right artifact in a multi-module build

A repository has `order-api`, `order-domain`, `order-service`, and `checkout-service`. Contracts live in `order-api`, yet the `order-service` build generates and publishes stubs.

**Task:** which artifact ID must the consumer use? Why not automatically guess from the folder containing the DSL files?

**Hint:** use the coordinates of the publication that actually carries the stubs, verified via metadata and CI.

### Exercise D — Dynamic version risk

Consumer CI uses `com.example.orders:order-service:+:stubs:8090`. On Monday CI PASSES; on Tuesday a new producer version arrives and CI FAILS even though the Checkout commit did not change.

**Task:** explain the non-reproducibility and how to fix the release gate.

**Hint:** pin the stub version, verify checksums/provenance, record producer/contract revisions, and re-run consumer tests per supported version pair.

### Exercise E — Missed breaking change

Order Service 1.5.0 changes its JSON response from `status` to `paymentStatus`. Checkout 2.8.0 still tests against stub 1.4.2 and reports PASS.

**Task:** can Order Service 1.5.0 be released? What checks are required?

**Hint:** run producer tests against the matching contract revision, generate/publish stub 1.5.0, then run Checkout 2.8.0 against the new stub. Review consumers relying on the old field and establish a backward-compatibility plan.

### Exercise F — Creating an artifact inspection checklist

Design a CI check confirming:

1. Producer contract tests actually ran and PASSED.
2. Stub artifact matches `group:artifact:version:stubs`.
3. Artifact contains all expected HTTP mappings.
4. Artifact holds no sensitive production data.
5. Consumer tests pull the exact version and avoid stale caches.

**Hint:** combine test reports, contract/stub mapping inventories, Maven publication metadata, checksums, and Stub Runner resolution logs. Never treat the mere presence of a `-stubs.jar` file as enough.

## 19. Checklist before publishing a stub artifact

- [ ] Clearly identify the group ID and artifact ID of the **publication containing stubs**, rather than guessing from package or folder names.
- [ ] Version of the producer build, contract revision, and stub artifact are linked together.
- [ ] Classifier is `stubs` per project convention/configuration.
- [ ] Stub JAR is kept distinct from the application JAR sharing the same group/artifact/version.
- [ ] Maven or Gradle config actually builds and attaches the stub artifact to the publication.
- [ ] Expected contracts are fully discovered; generated producer tests actually ran and PASSED.
- [ ] Stub artifact contains the expected mappings/responses or message stubs.
- [ ] Artifact contains no sensitive production data or real credentials.
- [ ] Consumer repository URL/permissions and `stubsMode` are configured properly.
- [ ] Consumer Stub Runner uses the right coordinates, classifier, and version; ports are never confused with versions.
- [ ] Release gates do not depend on dynamic versions when reproducible results are required.
- [ ] Release coordinates are immutable or at least verified via checksums and metadata.
- [ ] Consumer tests assert real logic rather than merely verifying the stub server started.
- [ ] Existing consumers are tested against **new stubs** when the producer makes potentially breaking API changes.
- [ ] CI reports record producer build, contract revision, stub version, and tested consumer versions.

**Remember:** `group ID` identifies the namespace, `artifact ID` identifies the published module, `version` selects the exact release, and `classifier = stubs` selects **the stub bundle** instead of the main JAR. Stub Runner needs accurate coordinates and resolution modes for consumer tests to be meaningful. API compatibility only has trustworthy evidence when the stub artifact is generated from the same contract verified against the producer, published traceably, and actually tested by consumers at the intended version.
