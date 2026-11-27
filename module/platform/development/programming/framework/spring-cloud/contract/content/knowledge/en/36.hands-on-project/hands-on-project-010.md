# Setting Up a Pipeline with Traceable Artifacts

In microservices architectures, **producers** and **consumers** are typically built, tested, and deployed by separate pipelines. A producer may pass generated contract tests while a consumer still downloads a stale stub; a deployed container image may come from a different commit; or during a production incident, the team cannot tell which `stubs` JAR verified the release. A complete pipeline must link **contract source → producer verification → stub artifact → consumer verification → producer image → deployment record**.

This hands-on lab builds a traceable CI/CD flow for two services:

- **Order Service** is the producer, exposing `GET /api/orders/{id}` and publishing an artifact containing WireMock stubs.
- **Billing Service** is the consumer, calling the Order API with a real HTTP client and testing against **Spring Cloud Contract Stub Runner**.

We will define contracts using the **Groovy DSL**, generate and run producer tests, package the `stubs` classifier JAR, record checksums and provenance, have Billing download the exact artifact, and enforce CI gates before promoting releases. At the end, a simulated incident is traced backward from deployment revision to Git commit, contract, test report, and stub artifact.

This lab belongs to the **Hands-On Project** chapter of the **SPRING_CLOUD_CONTRACT** module. The module teaches contract testing between producer and consumer over HTTP or messaging using Groovy/YAML DSL, generating producer tests, publishing stubs, using Stub Runner, and integrating CI to catch incompatible APIs. This workshop focuses on producing **verifiable evidence**, not merely a single `BUILD SUCCESS` line.

Examples use **Maven, JUnit 5, Spring Boot, and Spring Cloud Contract**. Choose compatible versions of Spring Boot, the Spring Cloud release train, Spring Cloud Contract plugin/starters, and JDK according to your project BOM. Versions such as `1.4.2` and `3.8.0` in this article are illustrative application versions, **not the latest library releases**. CI YAML snippets are vendor-neutral templates to map onto GitHub Actions, GitLab CI, Jenkins, or your existing CI platform.

## 1. Expected Workshop Outcomes

Upon completion, your team must be able to answer these questions using only the release record and artifacts:

1. Which contracts were loaded by the producer build?
2. Which producer Git SHA executed generated verification tests?
3. Which tests ran, what were the test counts, and where are the reports?
4. Which `stubs` JAR was built, and what are its Maven coordinates and SHA-256?
5. Which **exact bytes** of the stub artifact did Billing test against?
6. Which producer image digest was built from the verified source?
7. Which image digest is actually deployed in each environment/region?
8. When an error occurs, can you trace from a trace/request back to the deployment revision, build run, contract, and consumer test?

**Workshop deliverables**

- Producer Maven build with the Spring Cloud Contract Plugin and generated tests.
- Artifact `order-service:1.4.2:stubs` packaged and published to a staging repository.
- Consumer Stub Runner tests using an exact artifact version and a real client.
- Release manifest linking Git SHA, CI run, reports, stub checksum, and image digest.
- CI gates for producer, consumer, publish, deploy, and post-deploy.
- Incident drill note proving end-to-end traceability works.

## 2. Architecture and Artifact Flow

~~~mermaid
flowchart TD
    A["Order Service Git commit"] --> B["Groovy/YAML contracts"]
    B --> C["Spring Cloud Contract Maven Plugin"]
    C --> D["Generated producer tests"]
    D --> E{"Tests pass?"}
    E -->|No| X["Block publish"]
    E -->|Yes| F["Package producer + classifier stubs"]
    F --> G["Stub JAR + SHA-256 + build provenance"]
    G --> H["Staging Maven repository"]
    H --> I["Billing CI / Stub Runner"]
    I --> J["Real Billing HTTP client"]
    J --> K{"Consumer tests pass?"}
    K -->|No| Y["Block release promotion"]
    K -->|Yes| L["Promote verified artifacts"]
    L --> M["Deploy verified producer image digest"]
    M --> N["Deployment revision + runtime evidence"]
~~~

**The stub artifact and container image are two separate outputs.** The `stubs` JAR lets consumers verify the published interface; the image holds the producer runtime. Both must trace back to the same **producer source/build identity**. Rebuilding the image from another commit after consumers tested the stub breaks the chain of evidence.

## 3. Distinguishing Identities Across a Release

| Identity | Example | Answers the question |
| --- | --- | --- |
| Contract identity | `GET /api/orders/42`, `shouldReturnPaidOrder` | What behavior is committed? |
| Producer source identity | Full Git SHA `a1b2c3...` | Which source/contract was reviewed and built? |
| Consumer source identity | Full Git SHA `b2c3d4...` | Which client code was tested? |
| Producer application version | `com.acme:order-service:1.4.2` | Which application release was packaged? |
| Stub artifact coordinates | `com.acme:order-service:1.4.2:stubs` | Which stubs bundle did the consumer load? |
| Stub artifact checksum | SHA-256 of the JAR | Which exact bytes were tested? |
| Container image digest | `sha256:...` | Which image bytes were deployed? |
| CI run ID | `order-producer-483` | Which build/test run generated the evidence? |
| Deployment revision | `orders-prod-r134` | Which rollout ran in the environment? |

**Never substitute one identifier type for another.** Version `1.4.2` does not prove JAR contents if a repository allows overwrites. A Git SHA does not prove an image was deployed. Image tags may be mutable; use digests to identify exact contents.

## 4. Preparing Two Repositories

This workshop assumes two repositories:

~~~text
order-service/
├── pom.xml
├── src/
│   ├── main/java/com/acme/orders/
│   │   ├── OrderController.java
│   │   ├── OrderService.java
│   │   └── OrderRepository.java
│   └── test/
│       ├── java/com/acme/orders/contract/
│       │   └── BaseContractTest.java
│       └── resources/contracts/orders/
│           ├── get_paid_order.groovy
│           └── order_not_found.groovy
└── ...

billing-service/
├── pom.xml
├── src/
│   ├── main/java/com/acme/billing/
│   │   ├── OrderClient.java
│   │   └── BillingService.java
│   └── test/java/com/acme/billing/
│       └── OrderClientContractTest.java
└── ...
~~~

**Each repository has its own Git SHA.** The producer pipeline generates tests and publishes stubs; the consumer pipeline pins the stub version to verify its client. A monorepo layout is fine too, provided you still track per-module build/release provenance if modules release independently.

### 4.1. Tools and Access

Prepare:

- JDK and Maven Wrapper matching the project version.
- A Maven repository manager with **staging/release repositories** or equivalent artifact promotion.
- A CI identity with staging publish permissions and read-only permissions for consumer jobs.
- A container registry if deploying images.
- A test/staging environment for running producer and consumer checks.

**Never use production credentials in this lab.** Stub fixtures use synthetic data only; repository credentials are injected via CI secret stores and never committed to POMs, contracts, or logs.

## 5. Locking Build Versions

Example properties in producer and consumer POMs:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2023.0.4</spring-cloud.version>
    <spring-cloud-contract.version>4.1.5</spring-cloud-contract.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

These values only illustrate one project configuration. **Never copy standalone versions without checking compatibility** with your Spring Boot parent/BOM and Java runtime. Both the producer plugin and consumer starter must belong to the same compatible Spring Cloud Contract line.

Import the Spring Cloud BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**The BOM manages release train dependencies**, but it does not automatically pin every Maven plugin, JDK, CI image, CI action, or Docker base image. Pin those separately and record their versions/digests in the run manifest.

## 6. Declaring Spring Cloud Contract in the Producer

In `order-service/pom.xml`, add Contract Verifier in test scope:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

Declare the Maven plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>${spring-cloud-contract.version}</version>
            <extensions>true</extensions>
            <configuration>
                <baseClassForTests>
                    com.acme.orders.contract.BaseContractTest
                </baseClassForTests>
                <testFramework>JUNIT5</testFramework>
                <testMode>MockMvc</testMode>
                <contractsDirectory>
                    src/test/resources/contracts
                </contractsDirectory>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The plugin is enabled as a **lifecycle extension** to participate in generate/verify/package phases as supported by Maven. Property names and enum spellings can vary across versions; consult the documentation and plugin descriptor for your pinned version.

**Do not add the Verifier dependency to runtime scope** in the producer. It is a test generation and execution tool, not an application runtime library.

## 7. Writing HTTP Contracts for Order Service

Create `src/test/resources/contracts/orders/get_paid_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Return paid order by ID'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

The contract protects the `GET` method, path `/api/orders/42`, `Accept` request header, `200` status, JSON media type, and fixture business fields, types, and values.

Add the error contract `order_not_found.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnOrderNotFound'
    description 'Return structured error when order is not found'

    request {
        method 'GET'
        url '/api/orders/999'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 404
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND',
            message: 'Order does not exist'
        )
    }
}
~~~

These are two **intentionally distinct scenarios**. Consumers often need to differentiate success data from business errors. If error messages vary by locale, keep `code` fixed and use an appropriate matcher for `message`.

## 8. Creating the Base Class for Generated Producer Tests

Create `BaseContractTest.java`:

~~~java
package com.acme.orders.contract;

import com.acme.orders.Order;
import com.acme.orders.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class BaseContractTest {

    @Autowired
    OrderRepository orders;

    @BeforeEach
    void prepareContractData() {
        orders.deleteAll();
        orders.save(new Order(
            42L, "PAID", 125000L, "VND"
        ));
    }
}
~~~

`Order` and `OrderRepository` are illustrative domain/repository types; replace them with your project's implementation. The base class sets up **deterministic fixtures** so generated tests produce reproducible results.

Principles:

1. Every test gets an independent fixture; never depend on leftover data from prior runs.
2. Never use development or production databases.
3. Avoid unnecessary external service calls inside generated tests.
4. If the API depends on time, inject a fixed clock or test time.
5. When using test containers/databases, pin image versions and reset state.

**Generated tests must execute against the producer's real application/controller in the test context.** Never write a base class returning canned mock responses just to pass tests; that only tests the base class fixture, not the real implementation.

## 9. Running Producer Verification for the First Time

Inside the Order Service repository:

~~~bash
./mvnw -B -ntp clean verify
~~~

This command is an example for a Linux CI runner using Maven Wrapper. On Windows PowerShell, run `.\mvnw.cmd -B -ntp clean verify`.

After the build, verify:

- The plugin discovered the expected contract files.
- Generated tests appeared in the build's generated test source directory.
- The test runner actually executed the generated tests.
- Executed test counts are non-zero.
- Reports list test names matching `shouldReturnPaidOrder` and `shouldReturnOrderNotFound`.
- No unintended `skipTests` or Contract Verifier skip flags are active.

**`BUILD SUCCESS` alone is not enough.** If the plugin found zero contracts or generated tests were skipped, the pipeline can turn green without verifying any contracts.

### 9.1. Proving the Test Gate Catches Violations

On an experimental branch, alter the implementation to return:

~~~json
{
  "id": 42,
  "status": "PAID",
  "amountMinor": "125000",
  "currency": "VND"
}
~~~

The contract expects `amountMinor` to be a JSON number. The generated producer test must FAIL. Revert the implementation after confirming.

Next, change `status` from `PAID` to `CANCELLED`. This fixture test must also FAIL. If it still PASSES, inspect the generated matchers and body assertions; never loosen contracts to mask business regressions.

## 10. Packaging the Producer and Stubs JAR

When producer verification passes, the plugin produces configured outputs, including a stub artifact with **classifier `stubs`**. Example coordinates:

~~~text
com.acme:order-service:1.4.2:stubs
~~~

Coordinate breakdown:

~~~text
groupId    = com.acme
artifactId = order-service
version    = 1.4.2
classifier = stubs
extension  = jar
~~~

The stubs JAR holds the contract definitions and mappings needed by the consumer runner. Internal layout varies by plugin version. Inspect the archive with:

~~~bash
jar tf target/order-service-1.4.2-stubs.jar
~~~

The path above reflects standard naming; verify the **exact built artifact** in your build output and logs. Confirm mappings for both success and error scenarios are present.

**Never alter JAR contents after calculating checksums or publishing.** If a contract changes, produce a new build/version so consumers can pin precisely.

## 11. Publishing to a Staging Repository

In this workshop, use a Maven staging repository or equivalent mechanism:

~~~text
Repository: contract-staging
Producer coordinates: com.acme:order-service:1.4.2
Stub coordinates: com.acme:order-service:1.4.2:stubs
Policy: immutable within a staging/release build
~~~

The Maven plugin attaches the `stubs` classifier to the project artifact so the lifecycle publishes both the application and stubs. A Maven pipeline can run:

~~~bash
./mvnw -B -ntp clean deploy
~~~

`deploy` executes preceding lifecycle phases—including verification per your build configuration—and deploys the artifacts. Configure repositories and credentials via Maven settings or a CI secret store; **never commit usernames or passwords in POMs**.

If your organization uses a repository manager with staging lifecycles:

1. Publish to the **staging repository**.
2. Run consumer compatibility tests against that exact staging artifact.
3. Once all gates pass, **close/promote** the staging repository to release.
4. If any gate fails, drop staging and fix the producer, consumer, or contract.

Exact close/promote commands depend on your repository manager. Never publish an immutable release before compatibility gates pass if policy requires consumer verification first.

## 12. Computing the Stubs JAR Checksum

After creating the artifact, compute SHA-256 over the **actual bytes**:

~~~bash
sha256sum target/order-service-1.4.2-stubs.jar
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash .\target\order-service-1.4.2-stubs.jar -Algorithm SHA256
~~~

Record the output in the run record:

~~~text
stubCoordinate = com.acme:order-service:1.4.2:stubs
stubSha256     = <sha256-of-actual-jar>
producerCommit = <full-git-sha>
producerRunId  = <ci-run-id>
~~~

`<...>` entries are placeholders. **Checksums must be computed from the actual uploaded/downloaded JAR**, never inferred from filenames.

After publishing to staging, download the JAR from the repository and recompute the checksum. If it differs from the locally verified file, halt the pipeline and investigate:

- Was the artifact transformed or overwritten?
- Were versions or classifiers mismatched?
- Did the publish job pick up output from a different build?
- Did the repository serve a cached or stale mirrored artifact?

## 13. Consumer: Adding the Stub Runner Dependency

In `billing-service/pom.xml`, add:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
    <scope>test</scope>
</dependency>
~~~

The consumer does not need the Contract Verifier plugin merely to download and consume producer stubs. It needs Stub Runner in test scope and tests exercising **real clients/listeners**.

## 14. Writing Billing's HTTP Client

Example client:

~~~java
package com.acme.billing;

import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient http;

    public OrderClient(String baseUrl) {
        this.http = RestClient.create(baseUrl);
    }

    public OrderDto getOrder(long id) {
        return http.get()
            .uri("/api/orders/{id}", id)
            .accept(org.springframework.http.MediaType.APPLICATION_JSON)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(
        long id,
        String status,
        long amountMinor,
        String currency
    ) {}
}
~~~

This example uses Spring Framework's `RestClient`. If your project uses Feign, `WebClient`, or an internal client wrapper, tests must invoke **that exact production client** with the same converters, interceptors, and error handlers, changing only the base URL to point at the stub.

## 15. Writing Consumer Tests with Stub Runner

~~~java
package com.acme.billing;

import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/contract-staging"
)
class OrderClientContractTest {

    @Autowired
    StubFinder stubFinder;

    @Test
    void billingClientReadsPaidOrder() {
        URL stubUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service")
        );

        OrderClient client = new OrderClient(stubUrl.toExternalForm());
        OrderClient.OrderDto order = client.getOrder(42L);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
        assertThat(order.amountMinor()).isEqualTo(125000L);
        assertThat(order.currency()).isEqualTo("VND");
    }
}
~~~

Key points:

- `ids` pins the exact producer stub version `1.4.2`.
- `REMOTE` downloads the artifact from the Maven repository; the repository URL is illustrative and must be replaced with your real staging URL.
- `StubFinder` returns the HTTP URL of the started WireMock instance; the port may be dynamic.
- The test calls **`OrderClient`**, not a hand-rolled mock endpoint.
- Assertions check DTO and business fields rather than stopping at HTTP 200.

When using `LOCAL`, the JAR must exist in the runner's local Maven repository. `REMOTE` requires appropriate read credentials, proxy settings, and TLS configuration. **Stub Runner downloads JARs from a Maven repository; it does not turn the Maven repository itself into an API HTTP server.**

### 15.1. Testing Error Behavior

Consumers should also verify error handling:

~~~java
@Test
void mapsMissingOrderToDomainError() {
    assertThatThrownBy(() -> client.getOrder(999L))
        .isInstanceOf(OrderNotFoundException.class);
}
~~~

This snippet assumes `OrderClient` maps errors to `OrderNotFoundException`. In real implementations, verify the error body and code per contract rather than asserting "some exception was thrown." If the consumer lacks that mapping yet, implement it as part of client behavior.

## 16. Building a Consumer Compatibility Matrix

One producer release can impact multiple consumers:

| Consumer | Consumer version | Producer stub | CI result | Decision |
| --- | --- | --- | --- | --- |
| Billing | 3.7.0 | Order 1.4.1 | PASS | Baseline. |
| Billing | 3.7.0 | Order 1.4.2 | Actual PASS/FAIL | Verify backward compatibility. |
| Billing | 3.8.0 | Order 1.4.2 | Actual PASS/FAIL | Verify new client. |
| Analytics batch | 2.2.0 | Order 1.4.2 | NOT TESTED | Insufficient evidence. |

This is an **illustrative matrix**, without live CI results. Pipelines may only mark versions compatible when tests actually ran or an explicit waiver was recorded.

Prioritize:

- Consumers running in production or still under support.
- Slow-deploying consumers such as batch jobs, mobile apps, or partners.
- Consumers using fields, enums, headers, or error semantics being changed.
- Consumers still relying on API v1 during a v2 migration.

You do not need to test every historical version combination, but never treat `NOT TESTED` as `PASS`.

## 17. Creating a Release Manifest

A manifest links **source, build, tests, artifacts, and deployment**. JSON example:

~~~json
{
  "service": "order-service",
  "source": {
    "repository": "order-service",
    "commit": "a1b2c3d4e5f678901234567890abcdef12345678",
    "contractPaths": [
      "src/test/resources/contracts/orders/get_paid_order.groovy",
      "src/test/resources/contracts/orders/order_not_found.groovy"
    ]
  },
  "build": {
    "runId": "order-producer-483",
    "jdk": "17",
    "mavenWrapper": "3.9.x",
    "springCloudContract": "4.1.5",
    "producerVerification": "PASSED",
    "testReportRef": "order-producer-483/test-report"
  },
  "stubArtifact": {
    "coordinates": "com.acme:order-service:1.4.2:stubs",
    "sha256": "<actual-stubs-jar-sha256>",
    "repository": "contract-staging"
  },
  "producerImage": {
    "reference": "registry.example.org/orders/order-service",
    "digest": "sha256:<actual-image-digest>"
  },
  "consumerChecks": [
    {
      "consumer": "billing-service",
      "consumerCommit": "b2c3d4e5f678901234567890abcdef1234567890",
      "stubCoordinates": "com.acme:order-service:1.4.2:stubs",
      "stubSha256": "<actual-stubs-jar-sha256>",
      "ciRunId": "billing-contract-991",
      "result": "PASSED"
    }
  ],
  "deployment": {
    "environment": "production",
    "region": "region-a",
    "rolloutId": "orders-prod-r134",
    "imageDigest": "sha256:<actual-image-digest>",
    "status": "COMPLETED"
  }
}
~~~

This is an **illustrative internal schema**, not a mandatory Spring Cloud Contract format. `<actual-...>` entries are placeholders. Pipelines must generate manifests automatically from real Git, CI, repository, registry, and deployment metadata—never let developers manually type `PASSED`.

### 17.1. What Must Never Enter the Manifest

- Maven/Gradle repository passwords or access tokens.
- Docker registry credentials.
- Broker or database credentials.
- JWTs, private keys, or certificate private material.
- Raw customer payloads or PII.

Store only **secret references/identities** when configuration traceability is needed; keep actual secrets in a secret manager. Redact CI logs and reports before archiving.

## 18. Collecting Provenance from CI

Illustrative Linux runner commands:

~~~bash
git rev-parse HEAD
./mvnw -version
sha256sum target/order-service-1.4.2-stubs.jar
sha256sum target/order-service-1.4.2.jar
~~~

Outputs to record:

| Command / source | Data |
| --- | --- |
| Git checkout | Full source SHA and ref/PR context. |
| Maven Wrapper | Maven version and Java runtime. |
| Test reports | Generated test count, pass/fail/skip counts. |
| Stub JAR | Coordinates and SHA-256. |
| Application JAR | Checksum if package verification is needed. |
| Container build/push | Image digest returned by registry/build tool. |
| Deployment system | Environment, region, rollout revision, and running image digest. |

**Never take a Git SHA from one job and attach it to an artifact built in a different workspace.** Manifests must be generated in the same run context as the outputs, or consume signed/verified provenance metadata.

### 18.1. Image Digests

Container tags like `order-service:1.4.2` can be mutable depending on registry policies. When building/pushing images, capture the **actual digest** returned by the tool/registry and store it in the manifest. Deployment jobs must reference images by digest:

~~~text
registry.example.org/orders/order-service@sha256:<actual-digest>
~~~

Never fabricate a digest from a tag or assume a tag always points to the same bytes. During multi-image canaries, records must track digests per rollout, replica, or region.

## 19. CI Pipeline: Stages and Gates

~~~mermaid
flowchart TD
    A["Checkout immutable producer SHA"] --> B["Resolve pinned JDK/Maven/dependencies"]
    B --> C["Generate + run producer contract tests"]
    C --> D{"All required tests pass?"}
    D -->|No| X["Stop; do not publish"]
    D -->|Yes| E["Package producer JAR + stubs JAR"]
    E --> F["Calculate checksums and create provenance"]
    F --> G["Publish to staging Maven repository"]
    G --> H["Consumer CI resolves exact stub version"]
    H --> I["Run Stub Runner client tests"]
    I --> J{"Supported consumer matrix passes?"}
    J -->|No| Y["Stop promotion; investigate"]
    J -->|Yes| K["Promote immutable stubs"]
    K --> L["Build/promote verified image digest"]
    L --> M["Deploy canary and smoke test"]
    M --> N["Record deployment revision and monitor"]
~~~

**Not all stages have to run inside one job.** When splitting jobs, pass the exact verified JARs and images via artifact handoff; never re-checkout a moving branch and rebuild without re-running verification.

### 19.1. Vendor-Neutral Pipeline YAML

~~~yaml
# Pseudocode: map to your organization's actual CI provider.
producer:
  checkout:
    ref: immutable-commit-sha
  toolchain:
    jdk: pinned-version
    maven: repository-wrapper
  verify:
    command: ./mvnw -B -ntp clean verify
    require_generated_contract_tests: true
    fail_if_required_test_count_is_zero: true
  package:
    include_application_jar: true
    include_classifier_stubs_jar: true
  provenance:
    capture_git_sha: true
    capture_test_reports: true
    calculate_sha256: true
    create_release_manifest: true
  publish:
    target: staging-maven-repository
    immutable_coordinates: true

consumer:
  checkout:
    ref: immutable-consumer-commit
  resolve:
    stub: com.acme:order-service:1.4.2:stubs
    checksum: expected-stub-sha256
  test:
    command: ./mvnw -B -ntp clean verify
    use_stub_runner: true
    require_real_client_tests: true
  record:
    consumer_commit: true
    stub_coordinates_and_checksum: true
    test_report: true

release:
  require_producer_gate: true
  require_supported_consumer_matrix: true
  promote_staging_artifacts: true
  deploy_by_image_digest: true
  record_rollout_and_smoke_result: true
~~~

This is **pseudocode**, not executable on GitHub Actions, GitLab, or Jenkins as written. Keys like `require_generated_contract_tests` only take effect when implemented as real scripts and assertions. Your CI provider must genuinely block downstream jobs when a gate fails.

## 20. Order of Build, Test, and Publish

A release pipeline must decide when artifacts are published.

**Option A — Stage first, promote later**

1. Producer builds, verifies, and publishes to a staging repository.
2. Consumer jobs download staging artifacts by pinned version.
3. Compatibility matrix runs.
4. Repository manager promotes that exact staging repository once all gates pass.

Advantage: consumer tests resolve JARs through the exact Maven resolver mechanism used everywhere else, and releases remain unpublished publicly until gates finish.

**Option B — Artifact handoff**

1. Producer builds, verifies, and uploads the `stubs` JAR to a CI artifact store.
2. Consumer jobs download that exact file, verify its SHA-256, and install it into an isolated local Maven or temporary staging repo.
3. Consumer tests run.
4. Once passing, publish/promote the exact handed-off bytes.

Advantage: avoids early Maven publishing. Drawback: requires managing how Stub Runner resolves artifacts and how artifacts transfer across jobs.

**Never** build the producer once for tests and then rebuild it a second time to publish under the same coordinates without verifying identical sources, toolchains, test reports, and checksums. That easily produces two different byte streams under the same release name.

## 21. Consumer Matrix and Breaking-Change Policy

Before promoting a producer release, classify contract diffs:

| Change | Initial classification | Evidence needed |
| --- | --- | --- |
| Add optional response field | Potentially additive | Do older consumers ignore unknown fields? |
| Remove required field | Typically breaking | Which consumer versions still read it? |
| Change JSON number to string | Breaking for strict/type-safe clients | DTO/schema/parser compatibility. |
| Rename enum `PAID` to `SETTLED` | Potentially breaking | Consumer enum/switch behavior. |
| Change 200 to 202 | Potentially workflow-breaking | How do consumers handle async/pending? |
| Change error body/code | Potentially breaking | Error decoder mappings. |
| Change event destination/`schemaVersion` | Potentially breaking | Listener/topic/schema support. |

For breaking changes, follow **expand–migrate–contract**:

1. Expand: add the new API/event version while keeping the old one.
2. Migrate: update and deploy consumers.
3. Verify: run Stub Runner tests for supported consumer versions and monitor usage.
4. Contract: retire the old version once EOL policy is satisfied.

Never mark an untested consumer as PASS. Record `NOT TESTED` along with owner and explicit exception decisions.

## 22. Deploying the Producer Using the Verified Image

Once producer and consumer gates pass:

1. Promote the immutable `stubs` JAR artifact.
2. Promote the image digest built from the same verified producer source/build.
3. Create a deployment revision recording environment, region, digest, config version, and timestamp.
4. Run canary and smoke tests.
5. Monitor error rates, response schemas, latency, and consumer failures.
6. Complete the rollout or roll back to a known-good digest.

Abbreviated deployment manifest example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  annotations:
    example.org/source-commit: "a1b2c3d4e5f678901234567890abcdef12345678"
    example.org/build-run-id: "order-producer-483"
    example.org/release-version: "1.4.2"
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: registry.example.org/orders/order-service@sha256:<actual-digest>
          ports:
            - containerPort: 8080
~~~

`example.org/*` annotations are illustrative internal conventions, not added automatically by Spring Cloud Contract. The manifest declares **deployment intent**; proving runtime state also requires checking rollout status and running pods' actual image IDs/digests.

## 23. Runtime Monitoring to Close the Traceability Loop

Structured logs can emit:

~~~json
{
  "timestamp": "2026-11-24T10:00:00Z",
  "service": "order-service",
  "environment": "production",
  "releaseVersion": "1.4.2",
  "gitCommit": "a1b2c3d4...",
  "buildRunId": "order-producer-483",
  "deploymentRevision": "orders-prod-r134",
  "traceId": "trace-abc123",
  "httpMethod": "GET",
  "httpRoute": "/api/orders/{id}",
  "httpStatus": 200
}
~~~

`traceId` identifies the request/trace; `gitCommit`/`releaseVersion` identifies the code build; `deploymentRevision` identifies the rollout. **Never overload one ID for all three purposes.**

To protect sensitive data:

- Never log `Authorization` headers, cookies, JWTs, or broker tokens.
- Never log raw customer payloads or PII unnecessarily.
- Use route templates instead of raw paths containing user IDs where appropriate.
- Enforce retention and audit policies for CI reports and deployment records.
- Synchronize timestamps across CI, registries, and deployment systems.

## 24. Incident Drill: Tracing from a Billing Error Back to the Producer Contract

Suppose after a rollout, Billing reports an `amountMinor` deserialization failure.

Steps to trace:

1. Capture the **trace ID**, timestamp, environment/region, and Billing release.
2. Identify the Order Service deployment revision and image digest that served the request.
3. Look up the release manifest from the digest → producer CI run → full Git SHA.
4. Inspect the contract diff of `get_paid_order.groovy`.
5. Check the generated producer test report: did the `amountMinor` assertion verify JSON number?
6. Identify the stub coordinates and checksum used by Billing CI.
7. Compare that checksum against the artifact in the staging/release repository.
8. Inspect the consumer report: which Billing commit tested that artifact?
9. Capture the real staging response or redacted sample; confirm number vs. string.
10. Classify root cause: missing contract assertion, producer regression, artifact drift, image drift, or consumer DTO mismatch.
11. Choose fix-forward or rollback per consumer support policy.
12. Update contracts, tests, and release manifests so future traces close cleanly.

~~~mermaid
flowchart TD
    A["Billing parse failure + traceId"] --> B["Billing release / consumer commit"]
    A --> C["Order deployment revision / image digest"]
    C --> D["Release manifest"]
    D --> E["Producer Git SHA + contract diff"]
    D --> F["Stub coordinates + SHA-256"]
    E --> G["Generated producer test report"]
    F --> H["Billing Stub Runner report"]
    G --> I["Root cause and repair"]
    H --> I
~~~

If you cannot link a **producer image digest to a stub checksum and source SHA**, that is a pipeline gap to fix—not a reason to guess versions.

## 25. Failure Drills: Intentionally Breaking the Pipeline

Practice these failures on an experimental branch/fixture:

| Drill | How to inject the failure | Expected result |
| --- | --- | --- |
| Contract regression | Producer returns `amountMinor` as a string | Generated producer test FAILS. |
| Contract coverage gap | Delete the 404 contract and alter error behavior | Review/coverage gate spots missing scenario; consumer error test FAILS if behavior changed. |
| Consumer incompatibility | Billing DTO requires a field absent from the stub | Stub Runner consumer test FAILS. |
| Wrong stub version | Billing pins `1.4.1` instead of `1.4.2` | Test/report records exact version used; behavior may diverge. |
| Artifact overwrite | Attempt to overwrite released coordinates in a test repo | Repository policy rejects or checksum drift detects it. |
| Stale local cache | Install an older JAR into local repo | Checksum comparison detects mismatch against expected digest. |
| Skipped tests | Enable a skip flag on an experimental branch | Test count / report gate blocks publishing. |
| Image drift | Build image from a different commit than the stub build | Manifest source identity mismatch blocks deployment gate. |
| Wrong deployment | Deploy a tag pointing to a different digest | Runtime/deployment record detects digest mismatch. |
| Unchecked consumer | Drop a consumer from the matrix | Status stays `NOT TESTED`, never defaulting to `PASS`. |

After each drill, restore normal state and record **which layer caught the failure**. The goal is not making jobs red, but proving failures are blocked at the exact intended gate with clear evidence.

## 26. Extended Exercise: Adding a Message Contract

Once the HTTP pipeline works, extend Order Service to emit an `OrderCreated` event:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    input {
        triggeredBy('publishOrderCreated()')
    }
    outputMessage {
        sentTo('orders.created')
        headers {
            header('eventType', 'OrderCreated')
            header('schemaVersion', 1)
            header('contentType', 'application/json')
        }
        body(
            eventId: 'evt-42',
            orderId: 'ORD-42',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

Extension steps:

1. Configure a messaging verifier/integration matching your transport.
2. Have the base test trigger **the real application publisher**.
3. Have the receiver verify destination, headers, and payload.
4. Generated producer message tests must run before publishing.
5. Consumer Stub Runner triggers label `orderCreatedV1`.
6. Billing listener tests assert business side effects.
7. When using a real broker/serializer, add integration tests for wire bytes, schema registry, routing, and acks/retries.
8. Record the event contract version and adapter/broker test mode in provenance.

**Never treat fake/in-memory message tests as proof that a production broker was verified.** State the exact test scope in the manifest.

## 27. Release Checklist

| Area | Condition to proceed |
| --- | --- |
| Contract source | Groovy/YAML reviewed with explicit owner and consumer impact. |
| Producer source | Full Git SHA pinned, clean/controlled workspace. |
| Toolchain | JDK, Maven Wrapper, and plugin/BOM versions pinned or recorded accurately. |
| Generated tests | Generated, compiled, and executed; valid test counts. |
| Producer verification | All required scenarios PASS; critical mutations FAIL as expected. |
| Stub packaging | `stubs`-classifier JAR contains expected mappings and contracts. |
| Artifact identity | Coordinates, checksum, producer CI run, and source SHA link cleanly. |
| Repository | Staging/release policies immutable; consumer read credentials verified. |
| Consumer tests | Stub Runner uses exact version/checksum; real client/listener exercised. |
| Compatibility matrix | Supported consumer versions have results or explicit exemptions. |
| Image identity | Image digest built from the verified source/build. |
| Deployment | Deployed by digest with rollout revision and region recorded. |
| Runtime | Smoke tests, logs/metrics/traces include release identity and redaction. |
| Rollback | Prior known-good digest and rollback/migration plan ready. |
| Retention | Test reports, stub artifacts, and release manifests retained per policy. |

## 28. Workshop Acceptance Criteria

The workshop is considered complete only when:

1. Order Service has at least one success contract and one error contract.
2. The Maven plugin generates producer tests and the test runner executes them.
3. A schema/semantics-breaking mutation makes producer verification FAIL.
4. The build produces a `stubs`-classifier JAR with a deterministic version.
5. SHA-256 is computed from the real JAR and verified after downloading from staging.
6. Billing Stub Runner downloads the exact stub artifact, invokes the real HTTP client, and asserts DTO/business fields.
7. Consumer CI reports record consumer Git SHA, stub coordinates/checksum, and test results.
8. The release manifest links producer source, build, tests, stub, and image.
9. Deployment uses the verified image digest and creates a deployment revision.
10. The incident drill can trace from a request/trace ID back to contract source and test reports.
11. Zero credentials or PII appear in contracts, stubs, manifests, or CI logs.
12. Untested consumers are marked `NOT TESTED` or `EXEMPTED` rather than `PASS`.

## 29. Self-Check Questions

1. What does a passing producer generated test prove, and what does it not prove?
2. Why are both producer verification and consumer Stub Runner tests needed?
3. What segments make up Maven coordinates `com.acme:order-service:1.4.2:stubs`?
4. Why must JAR checksums be computed from actual bytes instead of relying on version strings?
5. How do `StubsMode.LOCAL` and `REMOTE` differ in artifact resolution?
6. Why must consumer tests invoke the real HTTP client or message listener?
7. How do you prove generated tests were neither skipped nor empty?
8. Why must the producer stub JAR and producer image share the same source/build provenance?
9. Why is an image digest more trustworthy than a mutable image tag?
10. Which identities should a release manifest contain?
11. Why must repository passwords or JWTs never be stored in manifests?
12. How does a staging repository enable consumer gates before release promotion?
13. When a consumer test receives 404, which request details should you inspect?
14. Why must a consumer compatibility matrix include older supported versions?
15. When must API v1 stay active during a v2 rollout?
16. Under what circumstances could a deployed producer image differ from the build that produced the stub?
17. How do correlation/trace IDs differ from Git SHAs and deployment revisions?
18. For messaging, why doesn't a producer test using a fake adapter prove real broker serialization?
19. When should a consumer be recorded as `NOT TESTED` instead of `PASS`?
20. If an incident cannot link an image digest to a stub checksum, what evidence is missing from the pipeline?

**Remember:** **A traceable pipeline must prove which producer source was verified, which generated tests executed, which exact `stubs` JAR bytes consumers tested against, which image digest was deployed, and which deployment revision serves traffic.** Use Groovy/YAML DSL to specify behavior; Contract Verifier to test producers; Maven classifier `stubs` to distribute mappings; Stub Runner to test real clients/listeners; checksums and release manifests to link artifacts; compatibility matrices to protect consumer versions; and deployment records to close the traceability loop. When every gate shares the same artifact identity and provenance, teams can release independently, catch incompatible APIs before rollout, and investigate incidents with hard evidence instead of guesswork.
