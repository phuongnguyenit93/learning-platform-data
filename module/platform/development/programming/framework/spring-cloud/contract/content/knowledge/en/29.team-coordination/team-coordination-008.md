# Keeping Contract Changes and Producer Deployments Traceable

In a microservices system, a **consumer** can fail right after a **producer** deploys: a JSON field gets renamed, a 404 returns a different schema, a header is dropped, a message destination changes, or the running producer no longer matches the `stubs` JAR that the consumer tested against. The question is not merely "did the tests pass?"—it is **answering who requested the change, which contract changed, which commit was verified, which artifact was published, which producer release was actually deployed, and which consumers were impacted**.

That is **traceability**. In **Spring Cloud Contract**, traceability must connect the **Groovy/YAML DSL** contract source, **generated producer tests**, **stub artifact**, **Stub Runner consumer tests**, deployment revision, and operational observability data. A single broken link—such as a `stubs` artifact produced from a different build than the deployed Docker image—can make two teams believe they tested the same version when they did not.

This lesson belongs to the **Team Coordination** chapter of the **SPRING_CLOUD_CONTRACT** module. The module teaches contract testing between producer and consumer over HTTP or messaging, generating producer tests, publishing stubs, using Stub Runner, and integrating CI to detect incompatible APIs. The focus here is **an evidence-backed multi-team workflow**, from contract change proposal to producer rollout, rollback, and incident investigation—not just adding a version label to a file.

## 1. What questions must traceability answer?

Imagine **Order Service** is the producer and **Billing Service** is the consumer. Billing suddenly fails to decode `GET /api/orders/42` in production.

A traceable system can answer:

| Question | Required evidence |
| --- | --- |
| **What changed?** | Contract diff in Groovy/YAML, PR, review, and semantic change description. |
| **Who approved?** | API owner, impacted consumer owners, and compatibility decision. |
| **When did it change?** | Commit/merge time, artifact publish, deploy start/end, and rollout. |
| **In which build/version?** | Producer Git SHA, release version, image digest, stub artifact coordinates. |
| **What was tested before release?** | Generated producer test reports, consumer stub tests, and CI run ID. |
| **What is running in production?** | Deployment record/manifest and runtime build identity. |
| **Which interface is the consumer calling?** | Deployed consumer release, contract version, access logs/traces if available. |
| **Where do we roll back to?** | Previously known good image/artifact and a verified rollback plan. |

**Traceability does not mean logging huge amounts of data.** It requires a **well-sourced, linkable, stable** trail that leaks neither secrets nor PII. A log saying "release 2.0" without pointing to a Git commit or image digest is insufficient for reliable investigations.

## 2. The ideal traceability chain

A contract change should follow this path:

~~~mermaid
flowchart TD
    A["Change request / issue with owner"] --> B["PR editing Groovy/YAML contract"]
    B --> C["Code review + consumer impact assessment"]
    C --> D["Merge commit with exact Git SHA"]
    D --> E["Producer CI: generate + run contract tests"]
    E --> F{"Verification passed?"}
    F -->|No| X["Block publish/deploy"]
    F -->|Yes| G["Build stubs artifact + container image"]
    G --> H["Record coordinates, checksums, and CI run ID"]
    H --> I["Immutable publish to artifact registry"]
    I --> J["Deploy producer from verified image digest"]
    J --> K["Deployment record + runtime build identity"]
    K --> L["Metrics/traces and consumer checks"]
    L --> M["Reconstruct change path during investigations"]
~~~

The critical point: **the exact source/commit that passed producer verification must lead to the exact recorded artifacts and deployment**. Rebuilding from `main` later inside a deploy job can yield different bytes. If rebuilding, you must prove it corresponds to the exact commit and checks—or better, **promote the exact already-verified artifact**.

### 2.1. Four non-interchangeable identity groups

| Identity | Example | What does it identify? |
| --- | --- | --- |
| **Contract identity** | `GET /api/v1/orders/{id}`, `OrderCreated:v2` | Committed interface and version/semantics. |
| **Source identity** | Git SHA `a1b2c3d...`, PR `#184` | Reviewed source/contract revision. |
| **Build artifact identity** | `com.acme:order-service:2.1.0:stubs` and checksum | Stub set published from a single build. |
| **Deployment identity** | Image digest `sha256:...`, env `prod-eu`, rollout ID | Actual producer build running in an environment/region. |

An artifact versioned `2.1.0` **does not prove by itself** which source/contract production is running. A Git SHA **does not tell** which regions a container image was deployed to. You need **verifiable links** across all identity types.

## 3. Running example: adding a `currency` field

Initially Order Service publishes:

~~~http
GET /api/orders/42
Accept: application/json
~~~

~~~json
{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000
}
~~~

Billing wants to add `currency` to handle multi-currency orders:

~~~json
{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

This is a **potentially compatible change** if older consumers allow extra JSON fields, old fields retain their names/types/meanings, and the contract does not forbid extra fields. Yet **you cannot conclude "adding a field is always safe"**: clients using strict deserializers, closed JSON schemas, payload signatures, or field-count checks can be affected.

Therefore, the change decision needs:

1. Business need and **currency definition** (ISO code, valid values, interaction with `amountMinor`).
2. Notification to **consumer teams** using the API.
3. Updated producer contract verified by **producer tests**.
4. **Consumer Stub Runner tests** against the new artifact, covering both old and new consumers if still supported.
5. A producer release linking **source SHA, stub artifact, and image digest**.
6. Evidence of the deployed producer build, parse-error monitoring, and canary results.

Conversely, changing `amountMinor` into `amount.minor` and removing the old field is a **breaking change** for many consumers. Version it or run a controlled expand–migrate–contract workflow instead of treating a green test on a new consumer as sufficient.

## 4. Ownership: who owns the contract and who approves changes?

In consumer-driven contracts, consumers typically describe **communication needs** while the producer is responsible for **proving the implementation complies**. File ownership models may differ: contracts may live in the producer repo, consumer repo, or a shared repo. What stays invariant is **clear decision authority and accountability**.

| Task | Producer team | Consumer team | Platform/SRE |
| --- | --- | --- | --- |
| Define public API and compatibility | **Accountable** | Consulted | Consulted |
| Propose new fields/behaviors | Reviewed | May be **Responsible** for the need | Informed |
| Accept contract DSL changes | Approver per ownership | Review impacted parts | Policy support |
| Create generated producer tests | **Responsible** | Informed | CI tooling support |
| Publish versioned `stubs` | **Responsible** | Consumes artifact | Repository/tooling |
| Run consumer tests with Stub Runner | Assist on incompatibilities | **Responsible** | Runner/network support |
| Decide production rollout | Product/API owner + release authority | Confirm readiness | Operational **Responsible** |
| Monitor and roll back | Alongside SRE | Monitor consumer impact | Incident coordination |

This table is an **illustrative responsibility model**, not mandatory org structure. Organizations may use different RACI mappings, but each decision needs an **owner, reviewers, and an evidence record**.

**Simply configuring `CODEOWNERS` in Git does not replace cross-team impact discussion.** A PR approved by a producer reviewer can still break external consumers if dependency discovery and notification are missing.

## 5. Contracts must be reviewable source in version control

Example in Order Service:

~~~text
order-service/
├── src/
│   └── test/
│       ├── java/com/acme/orders/ContractTestBase.java
│       └── resources/contracts/
│           └── orders/
│               ├── get_paid_order.groovy
│               └── order_not_found.groovy
├── pom.xml
└── ... producer source
~~~

File `get_paid_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Order Service returns published payment data'

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

**Value of source traceability:** the commit adding `currency` also contains or links to the producer implementation change, API notice, and required tests. During an investigation, teams can inspect the **exact diff** rather than just seeing a release artifact called "new order API".

### 5.1. YAML DSL for the same requirement

~~~yaml
description: Order Service returns published payment data
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
    status: PAID
    amountMinor: 125000
    currency: VND
~~~

Groovy and YAML are **two ways to express the same contract**. Within a build, keep only **one active representation** for the same scenario to avoid duplicate tests/mappings. If migrating DSL formats, record the migration commit and compare outputs before/after rather than silently swapping contract sources unchecked.

### 5.2. Keep contract names stable enough for diffs

File `orders/get_paid_order.groovy`, name `shouldReturnPaidOrder`, and the HTTP path are **three distinct identifiers**:

- Filename helps organization and review; rename only with reason.
- Contract name helps reading generated tests/reports; keep unique and recognizable.
- Method/path/body/headers are the **interface consumers actually depend on**; guard their compatibility.

Renaming `get_paid_order.groovy` to `get_order.groovy` is not an API breaking change if method/path stay unchanged. However, renaming can alter generated class/report paths or internal tooling, so still inspect build impact.

## 6. Classify contract diffs before merging

A PR should include a change assessment:

| Change | Expected classification | What must be verified |
| --- | --- | --- |
| Add optional `currency`, keep old fields | **Potentially compatible** | Do older consumers tolerate extra fields? |
| Remove `amountMinor` | **Usually breaking** | Do old consumers still use it? API v2/migration? |
| Change JSON number to string | **Breaking for many consumers** | Consumer DTOs/schemas/matchers/decoders. |
| Replace HTTP `200` with `202` | **Potentially breaking** | Consumer status-handling branches. |
| Change URL, HTTP method, required header | **Usually breaking** | Client code and request matching. |
| Add an optional response header | Usually low risk | Does the header affect signatures/caching? |
| Change enum `PAID` to `SETTLED` | **Potentially breaking** | Consumer switches/maps on status. |
| Change committed array ordering | **Breaking if order is meaningful** | Sorting/ranking/timeline tests. |
| Change `amountMinor` semantics while keeping schema | **Business-breaking** | Consumer units and financial logic. |
| Change retry/timeout/rate limit contract | **Potentially operationally breaking** | Consumer resilience and SLAs. |
| Change messaging destination/header/schemaVersion | **Potentially breaking** | Subscriptions, serializers, replay. |

**Text diffs do not decide compatibility on their own.** An "add-only field" change can hit strict parsers; a large implementation refactor can keep the contract intact. Evaluate from **the consumer's perspective**, real data, and supported versions.

### 6.1. Contract change PR description template

~~~text
Issue: ORDER-184 – add currency to Order response
Producer owner: Order Team
Affected contract: GET /api/orders/{id}
Source PR: #184
Compatibility: additive, consumer review required
Known consumers: Billing, Checkout, Analytics batch
New behavior: currency = ISO 4217 code, e.g. VND
Legacy behavior: id/status/amountMinor preserved
Producer generated tests: required
Consumer tests: Billing/Checkout stubs new release
Deployment plan: canary -> production, rollback by image digest
Open risks: strict JSON parsers and monthly batch jobs
~~~

IDs in the example are **hypothetical**, not existing issues/PRs. The goal is a **reviewable summary** linked to CI/releases rather than a generic commit title like "update contracts".

## 7. Git history and versions: source data worth preserving

A Git commit should reflect an intentional change:

~~~text
commit a1b2c3d4...
message: feat(order-contract): add currency to paid order response
source: src/test/resources/contracts/orders/get_paid_order.groovy
issue: ORDER-184
review: API owner + consumer representatives
~~~

**Never use `main` or `latest` as the identity of a published release.** Branches move; a Git SHA identifies a source snapshot. For exact traceability, store the **full SHA** in metadata/provenance, using short SHAs only for display.

However, **a Git SHA alone is not enough to identify artifact bytes** if builds depend on:

- Mutable or snapshot dependency versions.
- Different toolchains/JDKs across runners.
- Plugin/dependency resolution from non-immutable repositories.
- Build timestamps or non-deterministic file generators.
- Secrets or environment variables accidentally influencing build contents.

Therefore, record **source commit, build run ID, and artifact digest/checksum together**. Verified reproducible builds and provenance strengthen verification further; never assume a SHA in a filename guarantees provenance without a verification process.

## 8. Producer verification: what evidence is valid?

The Spring Cloud Contract plugin generates **producer verification tests** from Groovy/YAML DSL and executes them against the real producer in the configured test environment.

A typical Maven workflow is:

~~~shell
./mvnw clean verify
~~~

With Gradle:

~~~shell
./gradlew clean test
~~~

These are commands **learners run on a configured project**, not proof they were executed during this lesson. Maven `verify` runs test/package phases integrated with the plugin; Gradle `test` executes generated tests when plugin wiring is right, though it does not necessarily publish stubs. Always check actual task/plugin versions and reports.

**Minimum verification evidence:**

1. The plugin discovered the **exact contracts** belonging to the release.
2. Generated tests were emitted into test sources.
3. The test runner **actually executed** them—no `skipTests` or unintended zero test counts.
4. Tests passed against the exact producer implementation/commit.
5. Reports show which tests PASSED/FAILED and which CI run executed them.
6. Critical cases beyond the happy path were tested if the API commits to negative cases.

**`BUILD SUCCESS` alone is insufficient** when there is a risk the generator missed contracts or tests were skipped. To bind to a release, store report references in the **build record** instead of screenshotting a single log line.

### 8.1. Intentionally introduce a fault to prove the gate

On an experimental branch, change the producer implementation from:

~~~json
{"id":42,"status":"PAID","amountMinor":125000,"currency":"VND"}
~~~

to:

~~~json
{"id":42,"status":"PAID","amountMinor":"125000","currency":"VND"}
~~~

If the contract protects the **JSON number type**, generated producer tests must **FAIL**. If tests remain green, inspect matchers/DSL and generated assertions; they may be matching strings or overly loose. **Never edit the contract to match the buggy implementation just to get green tests** when consumers still require an integer.

A well-traced pipeline records: which commit caused the regression, which test caught it, why the build was blocked, and which build was ultimately published after fixing.

## 9. From producer tests to an identified stub artifact

Once producer verification passes, the producer packages a JAR with classifier `stubs`:

~~~text
com.acme:order-service:2.1.0:stubs
~~~

An illustrative layout:

~~~text
order-service-2.1.0-stubs.jar
└── META-INF/
    └── com.acme/
        └── order-service/
            └── 2.1.0/
                ├── contracts/
                │   └── orders/get_paid_order.groovy
                └── mappings/
                    └── ... WireMock JSON mappings
~~~

The **actual** layout depends on plugin version and packaging config; open the artifact to verify. For messaging-only stubs, message contracts may appear without WireMock HTTP mappings for those scenarios.

**Each release should carry these links**:

| Attribute | Example | When used |
| --- | --- | --- |
| `sourceCommit` | Full Git SHA | Locate exact contract and implementation source. |
| `buildRunId` | `ci-2027-01-15-483` | Trace test logs, plugin outputs, approvals. |
| `artifactCoordinates` | `com.acme:order-service:2.1.0:stubs` | Consumer picks the right stub. |
| `artifactChecksum` | SHA-256 of the JAR | Verify artifact bytes and detect overwrites. |
| `producerImageDigest` | `sha256:...` | Identify deployed container image. |
| `contractPaths` | `orders/get_paid_order.groovy` | Locate source of change. |
| `verificationReport` | CI report link/ID | Confirm tests ran and passed. |
| `publicationTime` | Timestamp with timezone | Distinguish publish from deploy. |

**Writing only "order-service version 2.1.0" in a wiki is not enough** if the same version can be overwritten or the image does not match the stub JAR. Releases should be **immutable** with proper checksum/digest verification.

## 10. Distinguishing application version, stub, Docker image, and API

| Identity | Example | What fact it represents |
| --- | --- | --- |
| API version | `/api/v1/orders/{id}` | Communication contract consumed by clients. |
| Maven producer version | `order-service:2.1.0` | An application build/release. |
| Stub Maven version | `order-service:2.1.0:stubs` | Contract/mapping bundle from that producer build. |
| Docker image tag | `order-service:2.1.0` | A **reference name** that can be mutable per registry policy. |
| Docker image digest | `sha256:abc...` | Exact image content identified by digest. |
| Deployment revision | `orders-prod-r134` | Rollout instance in a specific environment. |
| Consumer version | `billing:3.8.0` | Deployed/tested client build. |

**Tags are not always immutable**, so for production record the image digest and verified registry source. Stub artifact coordinates likewise need **no-overwrite release policies** or checksums/provenance to detect altered contents.

A new producer release may continue serving multiple **API versions** simultaneously. Conversely, an existing `2.1.0-stubs.jar` does not prove `/api/v1` is still live in production if the route was disabled at the gateway. You need both **contract tests** and **deployment/runtime evidence**.

## 11. Release manifest template linking all evidence

An **illustrative JSON record** that a CI/release registry might store:

~~~json
{
  "service": "order-service",
  "source": {
    "repository": "order-service",
    "commit": "a1b2c3d4e5f678901234567890abcdef12345678",
    "pullRequest": "184",
    "contractPaths": [
      "src/test/resources/contracts/orders/get_paid_order.groovy"
    ]
  },
  "build": {
    "runId": "ci-483",
    "verificationStatus": "PASSED",
    "verificationReportRef": "ci-483/test-report",
    "artifactRef": "com.acme:order-service:2.1.0:stubs",
    "artifactSha256": "<sha256-of-stubs-jar>"
  },
  "container": {
    "image": "registry.example.org/orders/order-service",
    "digest": "sha256:<image-digest>"
  },
  "deployment": {
    "environment": "production",
    "region": "region-a",
    "rolloutId": "orders-prod-r134",
    "status": "COMPLETED"
  },
  "consumerChecks": [
    {
      "consumer": "billing-service",
      "stubVersion": "2.1.0",
      "result": "PASSED",
      "ciRunId": "billing-ci-991"
    }
  ]
}
~~~

This is a **suggested internal schema**, not a mandatory format of Spring Cloud Contract, Maven, Gradle, or Kubernetes. Values in `<...>` are **placeholders**, not real digests. In a real project, records must be generated from **data confirmed by CI/registry/deployment systems**, never hand-typed from assumptions.

Notes:

- **Verification status** is the actual test runner result, not metadata manually marked `PASSED` by a developer.
- **Artifact checksum** must be computed from the bytes of the published file, not from a README.
- **Image digest** comes from the registry/build output and is verified at deploy time, never inferred from a tag name.
- **Deployment status** should include timestamp, environment/region, rollout revision, and an authoritative audit source.
- **Consumer checks** must specify which artifact version was actually tested; a green CI run against an old stub does not protect a new producer release.
- **Never store secrets** (tokens, passwords, private keys) or real user payloads in manifests.

## 12. Maven: preserving traceability when packaging and publishing

A Maven producer typically configures the plugin:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>com.acme.orders.ContractTestBase</baseClassForTests>
    </configuration>
</plugin>
~~~

The plugin creates generated tests and stub resources according to the integrated lifecycle; **actual configuration must match your plugin/Spring Boot/Spring Cloud versions**. A reference sequence:

~~~shell
./mvnw clean verify
./mvnw deploy
~~~

`deploy` runs earlier lifecycle phases and may **re-run tests**. If CI splits verify and publish into separate jobs, **pass the exact verified artifact** to the publish job or guarantee the rebuild uses the exact commit/dependencies/toolchain with a matching verification gate; never casually re-checkout `main` and publish different bytes.

### 12.1. How can coordinates and checksums be recorded?

Information to store in the release record:

~~~text
groupId: com.acme
artifactId: order-service
version: 2.1.0
classifier: stubs
extension: jar
sourceCommit: <full-git-sha>
verificationRun: <ci-run-id>
artifactChecksum: SHA-256 of published JAR
~~~

With Maven, a `stubs`-classifier JAR is **attached** to the project and published alongside the POM via the Contract Plugin. Do not assume every custom configuration or profile exports full stubs; inspect the artifact and compare coordinates/publish logs.

A command learners can run in a test environment:

~~~shell
jar tf target/order-service-2.1.0-stubs.jar
~~~

The `target/...` path is just an example for common defaults. Avoid merely checking whether a file exists from an earlier build; `clean` or artifact checksums catch stale outputs.

## 13. Gradle: keeping the same principles despite different tasks

A Gradle producer applies:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
    id 'org.springframework.cloud.contract' version '4.1.5'
    id 'maven-publish'
}

group = 'com.acme'
version = '2.1.0'

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}

contracts {
    baseClassForTests = 'com.acme.orders.ContractTestBase'
    testFramework = 'JUNIT5'
    testMode = 'MOCKMVC'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The snippet above is an **illustrative configuration fragment**, not a complete build: you must manage BOMs, repositories, Java toolchains, and publications with compatible versions. `3.3.6`/`4.1.5` are **example versions**, not claims of being the latest releases.

The Gradle plugin provides related tasks such as `generateContractTests`, `generateClientStubs`, and stub packaging tasks (names may vary by version). Inspect `./gradlew tasks --all` and the actual task graph; never blindly translate `mvn verify` to `./gradlew verify` if the Gradle project declares no such task.

**Traceability is build-tool agnostic**: whether using Maven or Gradle, store **source SHA, CI run ID, producer test reports, artifact coordinates/checksums, and deployment records**.

## 14. Stub Runner consumer tests must pinpoint the producer release

Billing uses `spring-cloud-starter-contract-stub-runner` in test scope, for example:

~~~java
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
    ids = "com.acme:order-service:2.1.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingOrderContractTest {

    @Autowired StubFinder stubFinder;

    @Test
    void readsOrderWithCurrency() {
        URL stubUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub not started"
        );

        OrderClient client = new OrderClient(stubUrl.toExternalForm());
        OrderClient.OrderDto dto = client.getOrder(42L);

        assertThat(dto.status()).isEqualTo("PAID");
        assertThat(dto.amountMinor()).isEqualTo(125000L);
        assertThat(dto.currency()).isEqualTo("VND");
    }
}
~~~

`OrderClient` and its DTO are **hypothetical Billing application code**; the example focuses on picking the right stub and verifying the response. With `LOCAL`, the artifact must be installed into the corresponding local Maven repository; in independent CI, `REMOTE` is commonly used with configured repository and read credentials.

**Do not use `latest` or an uncontrolled mutable artifact** if you want reproducible tests. Consumer CI output should record `com.acme:order-service:2.1.0:stubs`, its hash when available, and the CI run. If consumer tests fail today after passing yesterday, knowing **which stub was loaded** is essential diagnostic data.

### 14.1. Producer verification and consumer tests are complementary evidence

| Test | What does it prove? | What does it not prove? |
| --- | --- | --- |
| **Generated producer test** | Producer implementation at the tested build **complies with the contract**. | Production consumers deployed new clients. |
| **Stub Runner consumer test** | Consumer client code handles **the selected stub data**. | Producer instances run that exact commit without deployment evidence. |
| **Deploy smoke test** | Producer deployment serves sample checks. | All contracts, consumers, or edge errors work. |
| **Runtime tracing/metrics** | Which deployment receives traffic and which errors occur. | Causal proof for API changes without commit/artifact links. |

**No single test type replaces the others.** Distinguishing whether a bug comes from contract source, implementation, artifact, deployment, or client requires a **continuous chain of evidence**.

## 15. Consumer compatibility matrices need explicit data sources

When multiple teams release independently, record supported producer–consumer combinations:

| Consumer version | Producer stub release | CI result | Producer production release | Notes |
| --- | --- | --- | --- | --- |
| `billing 3.7.0` | `order 2.0.0:stubs` | PASS | Order `2.0.0` | Historical baseline. |
| `billing 3.7.0` | `order 2.1.0:stubs` | Actual PASS/FAIL | Order `2.1.0` not yet deployed | Pre-rollout compatibility check. |
| `billing 3.8.0` | `order 2.1.0:stubs` | Actual PASS/FAIL | Order `2.1.0` in canary | Billing already supports `currency`. |
| `analytics monthly job` | `order 2.1.0:stubs` | Not tested | Order `2.1.0` | Owner confirmation needed. |

This table is **illustrative, with no real CI results**. Never record `PASS` without a report. "Source branch compatible" differs from "deployed consumer binary compatible"; record each state accurately.

### 15.1. The matrix need not test every imaginable version pair

You do not need the Cartesian product of every historical release. Prioritize:

- Consumer versions still supported or running in production.
- Producer releases about to deploy or in canary.
- Changes with breaking risk (schema/headers/status/error/destination).
- Batch/offline consumers or partners with long deploy cycles.
- Versions currently undergoing deprecation/migration.

For unsupported combinations, **publish an explicit policy**. Never let "not tested" be interpreted as "compatible".

## 16. Deployment traceability: proving which producer serves production

A `PASSED` build release record **is not proof of deployment**. During rollout, capture:

~~~text
service: order-service
environment: prod
region: region-a
releaseVersion: 2.1.0
gitCommit: a1b2c3d4... (full SHA in source record)
containerImage: registry.example.org/orders/order-service@sha256:...
deploymentRevision: orders-prod-r134
deployedAt: timestamp with timezone
rolloutStrategy: canary -> full
rolloutStatus: COMPLETED / PARTIAL / ROLLED_BACK
approvedBy: change/release authority
~~~

**Recording only "deployed v2.1.0" is insufficient** if clusters run pods/regions with different digests. During a canary, **the same API request may be served by two producer versions**. Track traffic percentages, regions, time windows, and routing.

### 16.1. Helm/Kubernetes manifests are evidence of intent, not full runtime proof

Example manifest using an image digest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  annotations:
    example.org/source-commit: "a1b2c3d4e5f678901234567890abcdef12345678"
    example.org/release-version: "2.1.0"
    example.org/build-run-id: "ci-483"
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
          image: registry.example.org/orders/order-service@sha256:<digest>
          ports:
            - containerPort: 8080
~~~

Keys `example.org/*` and the digest placeholder are **illustrative conventions**, not generated by Spring Cloud Contract. In real deployments, this YAML also needs security contexts, probes, resources, secrets, policies, and proper template substitutions.

**A committed or applied manifest only proves a deployment was requested**, not that all pods are running that image. You need **deployment rollout status, pod/container image IDs/digests, and monitoring** from the deployment platform to verify runtime state.

## 17. Runtime build identity and correlation ID: two distinct purposes

A request carries a **correlation ID** to trace across the gateway, Order Service, and Billing Service. A deployment carries a **build identity** to identify which source/artifact it runs. These are **two different kinds of data**:

| Attribute | Example | Scope |
| --- | --- | --- |
| Correlation/trace ID | `traceId=9d7...` | A single trace or workflow/request. |
| Request ID | `X-Request-Id: req-001` | A single HTTP request, per convention. |
| Contract/API version | `/api/v1/orders/42` | Interface being invoked. |
| Release version | `order-service 2.1.0` | Software release. |
| Git SHA | `a1b2c3...` | Source snapshot. |
| Image digest | `sha256:...` | Container image bytes. |
| CI build/run ID | `ci-483` | Build/verification execution. |
| Deployment revision | `orders-prod-r134` | Deployment rollout instance. |

**Never use a request ID as proof of deployed source code.** Nor should you stuff software versions into `traceId` "for convenience": tracing systems provide structured span/resource attributes for that metadata.

### 17.1. HTTP-level observability

A structured log, **containing no PII or tokens**, might record:

~~~json
{
  "timestamp": "2027-01-15T10:00:00Z",
  "service": "order-service",
  "environment": "production",
  "releaseVersion": "2.1.0",
  "gitCommit": "a1b2c3d4...",
  "buildRunId": "ci-483",
  "deploymentRevision": "orders-prod-r134",
  "traceId": "9d75c42f...",
  "httpMethod": "GET",
  "httpRoute": "/api/orders/{id}",
  "httpStatus": 200,
  "contractVariant": "orders-v1"
}
~~~

This is an **example log schema**, not Spring Boot's default automatic output. `httpRoute` should use a **route template** to avoid logging raw IDs/PII or exploding metric cardinality; `contractVariant` must come from a real contract-identification mechanism, never guessed from status codes.

Safety notes:

- Never log `Authorization`, cookies, tokens, full order bodies, or sensitive data.
- Do not put Git SHAs into high-cardinality metric labels if your observability backend disallows it.
- Timestamps require timezones and clock synchronization across CI, registries, and deployment systems.
- Under log sampling, **not seeing a request** can mean it was sampled out, not zero traffic.
- Release identity attributes should be injected from **verified pipeline/metadata**, not manually typed `"2.1.0"` strings in source code.

## 18. Traceability for messaging: event versions, destinations, and replay

With messaging, contract changes are not just URLs and JSON. A producer may emit `OrderCreated`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV2'
    description 'OrderCreated schema v2 for Billing'

    input {
        triggeredBy('publishOrderCreatedV2()')
    }

    outputMessage {
        sentTo('orders.created.v2')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'OrderCreated')
            header('schemaVersion', 2)
        }
        body(
            eventId: 'evt-001',
            orderId: 'ORD-42',
            amount: [minor: 125000, currency: 'VND']
        )
    }
}
~~~

To trace a messaging incident, you need:

| Data | Role |
| --- | --- |
| Contract source path/commit | Which schema and label the producer committed to. |
| `schemaVersion` or schema registry ID | Which schema the consumer decodes with. |
| Destination/topic and partition/key | Which stream received the message, and partitioning/ordering. |
| `eventId` | Idempotency/deduplication and business event tracing. |
| Trace/correlation ID | Links producer publish to consumer processing if supported by infra. |
| Producer release/image digest | Which version emitted the message. |
| Consumer release | Which version read, processed, or routed it to DLQ. |
| Appropriate offset/delivery metadata | Trace stored/retried/replayed messages in the broker. |

**Note:** not every transport preserves headers, and `eventId` does not replace broker offsets. With Kafka/RabbitMQ/schema registries, test **actual serialization/binder mappings** and retention/replay policies via integration tests. Generated messaging contract tests may observe only `Spring Message` inside a test adapter, not necessarily proving production wire bytes.

### 18.1. Trace beyond the currently running publisher

A consumer may receive a message **published by an older producer release** due to backlogs, DLQs, or replays. Therefore:

- Never assume every event received today came from **today's running producer image**.
- If storing producer release IDs in message metadata, agree on the field convention across teams; never put sensitive environment details in public payloads.
- Keep ability to decode older schemas still appearing within retention/support policies.
- Cross-check `schemaVersion` with event time, publish time, broker metadata, and consumer processing time.
- When retiring an event version, stop publishing the old version **before** removing support for reading it.

That is why messaging traceability needs both **build identity** and **event identity**, plus broker storage metadata.

## 19. Cross-team PR workflow

A contract change should pass through clear coordination steps:

~~~mermaid
flowchart TD
    A["Consumer opens new need"] --> B["Producer assesses API + compatibility"]
    B --> C{"Breaking change?"}
    C -->|Yes| D["Design version/migration/dual support"]
    C -->|Unclear| E["Run old consumer tests + review schema"]
    C -->|No| F["Update contract/tests intentionally"]
    D --> F
    E --> F
    F --> G["PR: link issue, owners, diff, test impact"]
    G --> H["Producer + affected consumers review"]
    H --> I["CI generated producer tests"]
    I --> J["CI Stub Runner consumer compatibility"]
    J --> K{"Gates and approvals pass?"}
    K -->|No| L["Fix/defer, do not release"]
    K -->|Yes| M["Merge exact commit, build verified artifacts"]
~~~

**Do not treat "consumer review" as a rubber stamp.** Reviewers must check behaviors real clients rely on: error bodies/statuses, required headers, enums, array ordering, timeouts/retries, auth scopes, and message semantics.

A single change can impact **multiple teams**; notifications sent only in chat without PR/artifact links are easily lost. Record decisions in PRs/ADRs/issues and link them in release records.

### 19.1. Contract-first vs. producer-first

Both workflows work if executed with discipline:

- **Contract-first:** teams review DSL/semantics first, producer implements to the contract, generated tests verify the implementation.
- **Controlled producer-first:** producer proposes implementation and contract changes together in the same PR or linked PRs, running consumer compatibility before rollout.

The risk lies not in the methodology name, but in **when verification and evidence occur**. If the producer deploys a breaking API before consumers test and migrate, later commits cannot undo the downtime already caused.

## 20. Building CI gates to prevent "right stub, wrong producer"

A strong pipeline prevents:

1. Contract source from commit A while generated tests run against commit B.
2. Stub artifact built from commit A while producer image is rebuilt from commit C.
3. Consumer Stub Runner CI testing `order-service:2.0.0:stubs` while production deploys breaking `2.1.0`.
4. Producer tests skipped while the build still publishes `stubs`.
5. A release version overwritten, silently changing the JAR checksum.
6. Canary running two image digests while rollout reports record only one version.

**Recommended CI gates:**

| Gate | Mandatory condition | Evidence |
| --- | --- | --- |
| **G1. Contract source** | Contract diff + valid owners/reviews. | PR/commit links. |
| **G2. Producer verification** | Generated tests actually execute and pass. | CI run/test reports, test counts. |
| **G3. Stub packaging** | `stubs` JAR contains expected contracts/mappings. | Artifact inspection + checksum. |
| **G4. Consumer compatibility** | Supported consumer versions pass or have a migration decision. | Stub Runner CI report/version matrix. |
| **G5. Artifact provenance** | Source SHA, run ID, stub checksum, and image digest linked. | Build/release manifest, registry records. |
| **G6. Publish policy** | Immutable release artifacts, proper permissions and approvals. | Artifact registry audit. |
| **G7. Deployment controls** | Clear canary/approvals/rollback/health checks. | Deployment records and observability. |
| **G8. Post-deploy** | Runtime error rates/traffic healthy, live version confirmed. | Metrics/traces/rollout status. |

Not every gate must run in a single CI job. However, **later gates must not count as passed if evidence from earlier gates is missing or from a different version**.

### 20.1. Pipeline pseudocode illustrating linkage

~~~yaml
# Pseudocode: not a runnable configuration on a specific CI.
producer_pipeline:
  source:
    commit: <immutable-full-git-sha>
    contracts: <changed-contract-paths>

  verify:
    run_generated_contract_tests: true
    fail_if_zero_required_contract_tests: true
    publish_only_if_pass: true

  package:
    from_verified_workspace: true
    create_stubs_classifier_jar: true
    build_image_from_same_source: true
    collect_checksums_and_digest: true

  consumer_checks:
    select_supported_consumers: true
    pin_new_stub_artifact: true
    keep_run_references: true

  publish:
    require_all_gates: true
    immutable_artifact_coordinates: true
    persist_release_manifest: true

  deploy:
    use_verified_image_digest: true
    require_approval: true
    record_environment_and_rollout: true
    monitor_and_allow_rollback: true
~~~

These keys merely **illustrate policy**. They are not options in Spring Cloud Contract or a CI provider. When implementing, use the native mechanisms of GitHub Actions, GitLab, Jenkins, Argo CD, or your platform to enforce **real dependencies and permissions**, rather than trusting a YAML key `publish_only_if_pass: true` to enforce itself.

## 21. Rollout, canary, rollback, and post-deployment trails

A merged PR and passing producer verification do not guarantee zero operational failures. Post-release, track:

| Event | Trail |
| --- | --- |
| Image build | Git SHA, build run, image digest, and stub checksum. |
| Publish | Artifact coordinates, registry, timestamp, permissions. |
| Staging deploy | Environment, deploy revision, smoke tests. |
| Prod canary | Image digest, traffic percentage, region, time window. |
| Full rollout | GO decision, manifest, replica/health status. |
| Consumer regression | Consumer/service version, trace ID, API contract version, redacted log sample. |
| Rollback | Old image digest, rollback revision, reason, and completion time. |
| Fix forward | New commit, artifact, generated test report, deployment ID. |

**Rollback is not editing a version in a POM and re-running randomly.** You must know the **image digest and runtime config** of the last known good release, whether DB/schema migrations are reversible, and whether the old contract still works for running consumers.

During a canary, where part of traffic hits the old build and part hits the new build, break error metrics down **by deployment revision** before concluding a consumer failed due to a contract bug.

### 21.1. When rollback is unsafe

A new event schema may already have been published or a DB migration applied. Reverting to an older producer binary can cause:

- The old producer failing to read new data.
- Upgraded consumers rejecting old responses.
- v2 messages sitting in queues while reverted producers/consumers only handle v1.
- Changed API gateway or auth policies.

Therefore, **design the rollback plan during change review**, not after an incident happens. For breaking changes, expand–migrate–contract and dual-read/dual-write can create a safe rollback window, provided duplication/idempotency is verified when emitting multiple events.

## 22. When an incident happens: trace the chain without guessing

Suppose Billing reports a `currency` deserialization error in production after an Order Service deploy.

Investigation workflow:

1. Grab the **trace ID/request timestamp** from Billing along with affected environment and region. Do not start by guessing "it's the new commit".
2. Identify which **Billing binary/release** actually received the response and which schema it expects.
3. Determine which **Order Service deployment revision/image digest** served that request using logs/traces/gateway routing.
4. From that digest, look up the **release manifest** to get the source commit, CI run, and stub checksum/coordinates.
5. Inspect the **contract diff** between the current release and the previous good build; check fields/types/headers/error semantics.
6. Inspect the **generated producer test report**: did the corresponding test run and assert the right types/data?
7. Inspect the **consumer Stub Runner report**: which stub release did Billing test against, and does it match the deployed release?
8. Compare against a **safely redacted raw HTTP response** or structured schema evidence to confirm what the server actually sent. Never print sensitive payloads.
9. Classify the root cause: **contract bug**, **implementation bug**, **converter bug**, **wrong artifact**, **wrong deployment**, **missing CI coverage**, or **runtime issue**.
10. Choose **rollback/fix forward** based on impact and compatibility, then update contracts, tests, and release gates to prevent recurrence.

~~~mermaid
flowchart TD
    A["Billing incident + trace ID"] --> B["Consumer release / expected schema"]
    A --> C["Producer deployment revision/image digest"]
    C --> D["Release record: Git SHA + CI run"]
    D --> E["Contract diff + producer tests"]
    D --> F["Stub coordinates + checksum"]
    F --> G["Did consumer test use exact artifact?"]
    E --> H["Root cause + repair + rollback/fix-forward"]
    G --> H
~~~

**Without a record linking the stub artifact to the producer image**, investigations drag on and end in guesswork. That is a process gap solvable via release manifests and CI gates, not by dumping arbitrary extra logs.

## 23. Mistakes that destroy traceability

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Unrelated contract and implementation commits published together | Unclear whether the API version was verified by producer | Link PRs/commits, keep contract source and verified build records |
| Producer tests skipped or test count = 0 | Stub published without verified implementation | Gate on generated test execution/reports |
| Uncontrolled `latest` or mutable `-SNAPSHOT` | Same CI commit downloads different stubs over time | Pin versions/checksums, govern snapshots/caches explicitly |
| Republishing same version overwriting stub bytes | Consumer results become irreproducible | Immutable releases and artifact digests |
| Rebuilding image from a moving branch | Production producer does not match tested source | Promote the verified build's image digest |
| Recording only Docker tags without digests | Tags can later point to different images | Store image digest + registry reference |
| PR reviewed only by producer without consumer owners | Breaking change slips in before migration | Consumer inventory/ownership + compatibility review |
| Old consumer tested only against old producer stub | Current producer release breaks legacy unnoticed | Verify supported legacy contracts against current producer |
| Release manifest with manually typed `PASSED` status | Untrustworthy evidence | Have CI generate records from verified tool outputs |
| Canaries running multiple digests yet logged as one version | Cannot isolate faulty pod/region | Track rollout revision and image digest per instance |
| Mixing trace ID with release version | Hard to separate request errors from build issues | Use separate fields in logs and traces |
| Logging full request bodies/tokens to "trace" | Leaks secrets/PII, increases compliance risk | Structured logging with redaction and retention policies |
| Deleting historical artifacts immediately at EOL | Cannot reproduce older incidents | Retention/audit policy independent of API support policy |
| Teams naming versions/metadata inconsistently | Cannot join reports, registry, and deploy records | Standardize naming for service, SHA, artifact, revision |
| Rolling back with no known-good build recorded | Reverts to wrong image or breaks new consumers | Store prior digests/configs and rehearse rollbacks |

Good traceability must be **easy enough for daily work**. If it requires heavy manual effort, teams will skip it; automate collecting Git SHAs, artifact coordinates, checksums, and deploy revisions in CI/CD instead of asking humans to type them by hand.

## 24. Hands-on exercise: linking a contract change to a production release

Simulated lab with **Order Service** and **Billing Service** using Spring Cloud Contract:

1. **Create a hypothetical issue** `ORDER-184` requesting `currency` in the order response, assigning producer owner, consumer reviewers, and non-breaking criteria for the old schema.
2. **Write the Groovy or YAML contract** for `GET /api/orders/42` as in Section 5, keeping `id`, `status`, `amountMinor` and adding `currency`.
3. **Add/update producer implementation** to return matching JSON; set up the base test and generated producer verification.
4. **Run producer tests**, verify tests are generated and executed; intentionally change `amountMinor` from number to string to verify the gate FAILS, then revert.
5. **Record the full Git commit** with PR/issue link; create a record describing contract paths and compatibility decision.
6. **Package the `stubs`-classifier JAR**, e.g., `com.acme:order-service:2.1.0:stubs`; inspect the JAR for mappings/contracts and compute the byte checksum.
7. **Run Billing Stub Runner test with the exact artifact version**, using `StubFinder` for the dynamic URL and a real `OrderClient` to check `amountMinor`/`currency`.
8. **Run an older consumer too** if still supported, to check for strict parsers rejecting the new field.
9. **Record CI run ID, test reports, and artifact checksum** in a sample release manifest; do not mark `PASSED` without real reports.
10. **Build a container image from the same verified source/build**, capturing the real digest from the registry or build output.
11. **Simulate a staging/canary deploy**, recording environment, region, rollout ID, and digest; distinguish the **intended manifest** from evidence of running pods.
12. **Emit a sample structured log** with separate release identity and trace ID, free of tokens or sensitive payloads.
13. **Simulate a Billing failure** where a consumer calls the wrong API version; trace backward from trace ID -> release manifest -> source contract diff -> generated tests -> stub artifact -> deployment.
14. **Simulate a rollback**: identify the prior good image digest, verify data/consumer compatibility, and log the rollback event.
15. **Wire into CI gates**: producer tests pass -> immutable artifact -> consumer compatibility tests -> approved deploy -> post-deploy verification.

**Completion criterion:** starting solely from an incident record or deployment revision, learners can locate **the changed contract, Git commit/PR, producer verification report, `stubs` JAR with checksum, tested consumer version, container image digest, and deployment evidence** without guessing or relying on moving branch names.

## 25. Self-check questions

1. What questions does traceability in contract testing answer beyond "did tests pass or fail"?
2. How do `API contract version`, Maven artifact version, Git SHA, image digest, and deployment revision differ?
3. Why can a `stubs` artifact with the right version name still be untrustworthy if generated producer tests were skipped?
4. Why should the `main` branch never serve as the identity of a deployed release?
5. Why is a Git SHA insufficient to uniquely identify an artifact when builds are non-deterministic?
6. Why record the SHA-256 checksum of the `stubs` JAR and the image digest instead of only filenames/tags?
7. When adding an optional field to JSON, can you assume compatibility with every consumer?
8. Why does a consumer test passing against `order-service:2.0.0:stubs` not prove deployed producer `2.1.0` is compatible?
9. Which parts of proposal, verification, publishing, and rollout are owned by producer, consumer, and platform teams?
10. What information belongs in the impact assessment of a contract-editing PR?
11. Why might a producer release need to keep contract v1 even after releasing API v2?
12. Where should a release manifest originate so `verificationStatus=PASSED` is trustworthy?
13. Why is a Kubernetes manifest containing an image digest insufficient to prove all production pods run that exact build?
14. How do correlation ID and release ID differ in scope?
15. In a message-driven architecture, why might a message received today have been emitted by an already-retired producer release?
16. When using Stub Runner `REMOTE`, how does the Maven repository URL differ from the HTTP stub server URL?
17. What gates are needed before allowing publish/deploy of a potentially breaking change?
18. Why must a canary rollout record both traffic percentage and image digest per environment/region?
19. When rolling back a producer, why inspect consumer versions, DB migrations, and message schemas?
20. During incident investigation, what trace path connects a consumer error to source contracts and verified artifacts?
21. Why is keeping historical artifacts useful even after the API v1 contract has retired?
22. How do you maintain traceability while still protecting secrets and sensitive data?

## 26. Actionable release checklist template

| Check group | What to confirm | Evidence/Link |
| --- | --- | --- |
| **Contract ownership** | Owner, affected consumers, PR/ADR/issue, and compatibility review exist. | PR, issue, and review record links. |
| **Source** | Merged full Git SHA, contract paths, and related producer implementation. | Repository commit link. |
| **Producer verification** | Generated tests really executed, unskipped, cover contract cases, and passed. | CI run + test report. |
| **Stub packaging** | Classifier `stubs`, right coordinates, mappings/contracts, and checksum. | Artifact registry + digest. |
| **Consumer tests** | Supported clients tested against the exact stub version. | Stub Runner run IDs + compatibility matrix. |
| **Artifact linkage** | Image digest and stub JAR trace cleanly to source/build. | Build manifest/provenance. |
| **Publish** | Immutable artifact, repository policy, and proper write permissions. | Registry publish/audit record. |
| **Deploy** | Exact environment/region, image digest, rollout/approval. | Deployment revision + rollout status. |
| **Runtime** | Logs/metrics per deploy build, API version, errors, and redacted trace IDs. | Dashboards/traces/smoke report. |
| **Rollback** | Prior good build identified, rollback conditions, and on-call owner. | Runbook + previous image digest. |
| **Retirement** | Old contract deleted only after meeting EOL criteria. | Decision record and consumer inventory. |

**Conclusion:** **A contract change is only truly traceable when teams link DSL source -> Git commit/PR -> generated producer tests -> `stubs` artifact -> consumer Stub Runner tests -> producer image digest -> deployment revision and runtime observability.** Never infer from a version name or green CI status alone that production complies with the contract. Keep artifacts immutable, verify checksums/digests, enforce owners/approvals and compatibility gates, persist release/deploy records, and pair correlation IDs during investigations without logging secrets. When these trails are automated in CI/CD, producers and consumers can release independently while still pinpointing root causes and rolling back safely on incompatible API or message changes.
