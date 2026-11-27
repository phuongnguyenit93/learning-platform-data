# Rerunning pipelines with identical inputs and the exact stub version

In CI/CD, a **consumer contract test** might pass green yesterday yet turn red when a developer clicks **Rerun** today, even with zero new commits. The cause is not necessarily a source-code change: the repository may have returned a different `SNAPSHOT`, Stub Runner may have downloaded a newer `stubs` JAR at the same mutable coordinates, Gradle/Maven may have re-resolved dependencies, a data fixture may have been shared, system time changed, or two jobs collided on the same WireMock port. When that happens, the team no longer knows whether it is **reproducing the old failure** or testing a different set of inputs.

**A reproducible rerun** means identifying and controlling enough pipeline inputs that a rerun can be reliably compared with the prior run. With **Spring Cloud Contract**, critical inputs include **producer/consumer Git commits, Groovy/YAML contracts, generated producer tests, Maven/Gradle configuration, `stubs` artifact version, JAR byte contents, Stub Runner config, test fixtures, and the CI environment**.

This lesson belongs to the **CI/CD** chapter of the **SPRING_CLOUD_CONTRACT** module. The module covers HTTP and message contract testing, generating producer tests, publishing stubs, using Stub Runner, and CI integration to detect incompatible API changes. This topic focuses on an essential operational capability: **when a contract test fails, being able to rerun the exact build under test to distinguish real regressions, infrastructure failures, and flaky tests**.

## 1. What does "identical inputs" mean?

Never define "identical inputs" merely as **the same branch** or **the same `pom.xml` file**. A CI run depends on many state layers:

| Input layer | Example | What to pin or record |
| --- | --- | --- |
| **Source code** | Billing Service Git commit | Full Git SHA, submodules / checkout paths. |
| **Contract source** | `orders/get_paid_order.groovy` | Git SHA or checksum of the contract set used. |
| **Producer build** | Order Service release `1.4.2` | Git SHA, test reports, `stubs` artifact of that exact release. |
| **Stub artifact** | `com.acme:order-service:1.4.2:stubs` | Coordinates **and SHA-256 of the actual JAR**. |
| **Dependencies** | Spring Boot, Spring Cloud Contract, Jackson | Actual resolved versions; avoid dynamic/mutable versions. |
| **Build tools** | JDK, Maven Wrapper / Gradle Wrapper | Toolchain, plugin versions, container/tool image. |
| **CI definition** | Workflow revision, scripts, matrix | Workflow/action/runner versions and actual flags. |
| **Test configuration** | `StubsMode.REMOTE`, repo root, profile | Mode, allowed environment variables, resolver config. |
| **Fixtures and state** | DB, clock, fake auth tokens, message backlog | Identical initialization, reset/isolation between tests. |
| **Supporting infra** | Repository, network, proxy, broker | Access source, service state, or stable mocks. |

One run can use **identical Maven coordinates** yet **different bytes** if an artifact was overwritten. Conversely, two jobs can use the **same JAR checksum** yet produce different test outcomes because fixtures, time, or client invocation behavior differed.

Therefore, distinguish **input identity** from **execution-environment stability**. Pinning identity is necessary; isolating and controlling sources of nondeterminism is what makes outcomes consistent.

## 2. Three goals of rerunning

| Goal | How to do it | When to use |
| --- | --- | --- |
| **Rerun the same job** | Re-run with the exact Git SHA, workflow revision, and pinned stub artifact. | Check whether a CI failure reproduces. |
| **Comparable rebuild** | Recompile from the same source/toolchain/dependency graph and compare artifacts/test results. | Investigate build or supply-chain drift. |
| **Replay the exact tested artifact** | Re-fetch the exact `stubs` JAR by checksum and reuse container images/outputs from the verified run. | Reproduce an issue from a specific release or test an older consumer. |

**Do not treat these three goals as one.** Clicking `Rerun all jobs` in a CI system may reuse the commit yet **resolve newer dependencies**, pull a newer action, or hit a repository in a changed state. Running `mvn clean verify` from the exact Git SHA still might not yield byte-for-byte identical JARs if builds embed timestamps or non-deterministic plugin outputs.

Investigation conclusions should state explicitly: **"rerun same source"**, **"rerun same artifact"**, or **"byte-for-byte rebuild"**. Never claim "reproducible" merely after two green runs.

## 3. The producer → stub → consumer chain must remain immutable

~~~mermaid
flowchart TD
    A["Producer source + Groovy/YAML contracts at Git SHA P"] --> B["Contract Verifier generates producer tests"]
    B --> C{"Producer tests actually ran and PASSED?"}
    C -->|No| X["Block publish"]
    C -->|Yes| D["Package stubs artifact"]
    D --> E["Record coordinates + SHA-256 + CI run ID"]
    E --> F["Publish immutable release artifact"]
    F --> G["Consumer source at Git SHA C"]
    G --> H["Stub Runner fetches exact pinned artifact"]
    H --> I["WireMock / message adapter starts"]
    I --> J["Consumer tests run real client/listener code"]
    J --> K["Save test results + input manifest"]
~~~

Two complementary verifications:

1. **Producer verification** proves the implementation at **producer commit P** satisfies the selected contracts.
2. **Consumer tests via Stub Runner** prove the client/listener at **consumer commit C** can consume the **specific stub artifact**.

If consumer tests use only an artifact from an **overly old producer release**, passing green does not guarantee the producer release about to deploy is compatible. If the producer build skipped generated tests, the newly published stub JAR carries no implementation guarantee either. The pipeline must connect the **exact release under evaluation**, not fetch just any JAR carrying the `stubs` classifier.

## 4. Sample contract as a comparison baseline

Suppose Order Service is the producer and Billing Service is the consumer. An HTTP contract is saved at:

~~~text
src/test/resources/contracts/orders/get_paid_order.groovy
~~~

Groovy DSL content:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Order Service returns a paid order'

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
            amountMinor: 125000
        )
    }
}
~~~

Or **choose YAML DSL** to express the exact same behavior:

~~~yaml
description: Order Service returns a paid order
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
~~~

These are **two illustrative formats**, not two contracts to load simultaneously. In a producer build, keep only one active representation per case to avoid duplicate generated tests or stub mappings.

Contracts hold **method/path/request/response semantics**, not Maven repository URLs, WireMock ports, or Git SHAs. Environment metadata and provenance belong in **pipeline/release records**, never stuffed into DSL to "lock" a build.

### 4.1. Why do fixtures matter too?

Generated producer tests are meaningful only when Order Service **genuinely holds order 42 in `PAID` status** in the test environment. If one run starts with a clean database while another collides with leftover rows from an earlier test, outcomes are not reproducible.

The producer's base test can use a test profile, controlled transactions/cleanup, `@BeforeEach`/`@Sql`, Testcontainers with pinned image versions, or mocked repositories depending on desired verification depth. **Never use a shared development database** as an unpredictable data source for contract verification.

## 5. Artifact coordinates are not enough: know which JAR bytes ran

A consumer often declares Stub Runner as:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/releases"
)
~~~

Coordinates break down as:

~~~text
groupId    = com.acme
artifactId = order-service
version    = 1.4.2
classifier = stubs
extension  = jar
~~~

**Rules for reproducible CI:**

- Pin an **explicit version**; avoid time-varying selectors when rerunnability is the goal.
- Prefer **immutable release artifacts** (never overwrite the same group/artifact/version/classifier).
- Compute and store the **SHA-256 checksum** of the JAR file CI actually downloaded/built.
- Link that artifact to the **producer Git SHA, CI run, and producer verification report**.
- If mirrors/proxies exist, check metadata and checksums to catch staleness/mismatches.
- Never assume a file in `~/.m2/repository` is the right build simply because its filename matches.

Example build record:

~~~text
stubCoordinate = com.acme:order-service:1.4.2:stubs
stubSha256     = <64 hexadecimal characters of actual JAR>
producerCommit = <full Git SHA of the verified producer build>
producerRunId  = <CI build ID>
~~~

Values inside `<...>` are **placeholders**; never treat them as real checksums or verified commitments. Digests must come from the **actual bytes** of the published artifact or what the resolver downloaded.

### 5.1. Why do `-SNAPSHOT` versions make reruns diverge?

A version such as:

~~~text
com.acme:order-service:1.5.0-SNAPSHOT:stubs
~~~

can be published multiple times with **different contents**. Repository snapshot metadata can advance from timestamp/build number A to B. If CI retries the next day, identical coordinates can resolve to a different JAR.

During active development, `SNAPSHOT` remains useful for trying new changes. However, to **replay a historical failure**, you must:

1. Record the **timestamped snapshot artifact or checksum** used.
2. Archive the artifact in an immutable run-scoped build store if policy permits.
3. Or publish a **dedicated release/test-candidate version** without overwrites for compatibility CI.
4. Re-install/resolve the artifact from the **exact bytes** when rerunning, instead of re-resolving the `-SNAPSHOT` alias.

**Never pass `-U` expecting "it will fetch the exact old build"**: Maven `-U` forces checking for newer snapshot updates, which can change the resolved artifact. `-U` is a cache-policy/debugging flag, not an artifact-pinning mechanism.

## 6. Pin Git commits, not just branches or pull-request numbers

A workflow triggered on a pull request may check out:

- The PR branch's **head commit**.
- A **synthetic merge commit** created by CI to preview merge state.
- A newer commit pushed after the PR updated.

Those three are **not necessarily identical**. When rerunning, record the **exact checked-out Git SHA and hashes of submodules/external contract sources**.

| Data | Example | Meaning |
| --- | --- | --- |
| Source repository | `billing-service` | Consumer test source. |
| Full Git SHA | `abc123...` | Exact code snapshot tested. |
| Ref type | `pr-head` or `merge-ref` | How CI checked out the repo. |
| Workflow revision | Commit of `.github/workflows` / Jenkinsfile | Exact CI rules executed. |
| External contract source | Tag/commit or separate Maven coordinates | Contracts pulled from an external source. |
| Submodule commit | SHA of submodule | Source living outside the main repository. |

**Never run `git checkout main` to replay yesterday's failure**, because `main` may have advanced by many commits. Testing a newer fix on `main` is a **new test**, not a rerun with identical inputs.

When producer and consumer live in **two repositories**, record **both Git SHAs** rather than logging one generic "source version" and guessing later.

## 7. Lock build and test tool versions

Beyond source code, the build environment shapes generated tests and runtime behavior:

| Component | How to control |
| --- | --- |
| **JDK** | Declare version/toolchain; even better, record vendor and exact runtime build or CI image digest. |
| **Maven** | Use Maven Wrapper from the pinned commit; log `./mvnw -version` in the record. |
| **Gradle** | Use Gradle Wrapper from the pinned commit, Java toolchains, and fixed plugin versions. |
| **Spring Boot** | Explicit version via parent/BOM; never mix release trains arbitrarily. |
| **Spring Cloud Contract** | Compatible plugin + Verifier/Stub Runner dependencies per release train. |
| **JUnit/Spock** | Ensure framework engine and test discovery do not shift silently. |
| **Docker/CI image** | Prefer image digests or governed immutable tags. |
| **Third-party CI actions/plugins** | Pin approved revisions/versions; audit changes. |

Producer Maven `pom.xml` example:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2023.0.4</spring-cloud.version>
    <spring-cloud-contract.version>4.1.5</spring-cloud-contract.version>
</properties>

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

These versions are **merely an illustrative set**, not the latest versions or guaranteed compatible with every JDK/Maven/Gradle setup. In real deployments, select a **compatible** combination of Spring Boot, Spring Cloud release train, Spring Cloud Contract, and build tools per project requirements.

**A BOM does not automatically pin build plugin versions** when plugins are declared independently of dependencies. Likewise, selecting a Spring Cloud BOM does not make CI images, Maven Wrapper, Gradle Wrapper, or JDKs immutable.

## 8. Lock the dependency tree and inspect resolved versions

Pinning top-level dependencies in `pom.xml` or `build.gradle` can fall short when:

- Version ranges or dynamic versions are used.
- SNAPSHOTs or internal dependencies can be overwritten.
- Registries/mirrors apply differing resolution policies.
- Maven profiles or Gradle variants shift by environment.
- Plugins pull differing transitive dependencies when versions or plugin repositories change.

**Maven:** use BOMs/`dependencyManagement`, pin plugin versions, and capture the dependency tree when investigating:

~~~shell
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

**Gradle:** use version catalogs/BOMs and **dependency locking** where suitable; inspect the actual resolved graph:

~~~shell
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-contract-stub-runner \
    --configuration testRuntimeClasspath
~~~

Gradle offers lockfiles to pin dependency resolution. Yet **Gradle dependency locking does not automatically lock Maven/Gradle plugins, CI actions, container images, or artifacts fetched independently by Stub Runner**. Inspect each input layer separately.

**Never check `dependency:tree`/`dependencies` output into a repository as "proof" without knowing which environment produced it.** Prefer saving the file/report emitted by CI for that exact run, reconciled against toolchain and repository sources.

## 9. Caches: speed up runs yet can mask drift

CI commonly caches:

~~~text
~/.m2/repository/
~/.gradle/caches/
build/
target/
container image layers
Stub Runner's artifact download cache
~~~

Not all caches behave identically:

| Cache | What drift can it cause? | Recommended policy |
| --- | --- | --- |
| Maven local artifact cache | Stores `stubs` differing from remote artifact at same coordinates. | Immutable releases, checksums, deliberate cold-cache checks. |
| Maven `.lastUpdated`/metadata | Remembers stale errors/metadata, failing inconsistently across reruns. | Inspect update policy/TTL; do not wipe blindly when real error is 401. |
| Gradle dependency cache | Returns cached dynamic versions or module metadata. | Dependency locking, controlled refreshes, lockfile diffing. |
| `target/` or `build/` | Stale generated tests/mappings linger if builds omit `clean`. | Use `clean` for verification/replay when verifying source accuracy. |
| CI artifact cache | Reuses reports or JARs from another job. | Key caches on Git SHA/toolchain; verify artifact checksums. |
| Docker layer cache | Alters build bytes/paths if upstream sources or base images mutate. | Pin base image digests and record final image digest. |

**Warm-cache tests** answer "does the normal pipeline run with populated caches?"; **cold-cache tests** answer "can all dependencies/artifacts resolve from authorized sources with identical bytes?". Both are valuable. However, cold-cache **does not guarantee** identical dependencies if repositories hold mutable versions; combine version pinning with checksums/provenance.

### 9.1. Why not use `LOCAL` to conclude `REMOTE` works?

For example:

~~~java
stubsMode = StubRunnerProperties.StubsMode.LOCAL
~~~

only instructs Stub Runner to look for the artifact already in the **local Maven repository** of that environment. It **does not prove** the remote artifact repository works, tokens are unexpired, or proxies/TLS are configured cleanly.

To test **re-fetching a release artifact**, use `REMOTE` in an appropriately isolated environment/cache. To **replay exact archived artifact bytes**, use the stored file with checksum verification rather than letting a resolver pick another build.

## 10. Producer CI: verify for real before publishing stubs

A trustworthy release requires generated tests to actually be generated and run:

~~~mermaid
flowchart TD
    A["Checkout producer Git SHA P"] --> B["Restore pinned toolchain + dependencies"]
    B --> C["Generate tests from Groovy/YAML contracts"]
    C --> D["Compile generated tests"]
    D --> E["Run producer verification"]
    E --> F{"Required tests present and PASSED?"}
    F -->|No| G["Fail; do not publish"]
    F -->|Yes| H["Build stubs JAR"]
    H --> I["Compute SHA-256; record provenance"]
    I --> J["Publish immutable coordinates"]
~~~

With a Maven producer whose plugin/lifecycle is properly configured:

~~~shell
./mvnw -B -ntp clean verify
~~~

Afterward you can `install`/`deploy` or publish the verified artifact per organization-approved pipeline.

With a Gradle producer:

~~~shell
./gradlew --no-daemon clean test
./gradlew tasks --all
~~~

`tasks --all` lets you inspect the exact stub-packaging task names in your Spring Cloud Contract Gradle Plugin version. **`test` does not necessarily build or publish the classifier JAR**; run the dedicated packaging/publication tasks when handing stubs to consumer runners.

**What to verify on every build:** generated tests appear in reports, **actual test count is non-zero** when mandatory contracts exist, no skip flags are active, and **an intentional breaking change to a response causes the build to FAIL**. If producer tests did not execute, a stub artifact with a matching version name is still untrustworthy.

### 10.1. Never rebuild a different artifact after verification

Suppose job A runs `verify` on commit P and creates `order-service-1.4.2-stubs.jar`. Job B checks out a newer branch, runs packaging separately, and publishes under **the exact same coordinates**. Producer test A's result **no longer verifies the published bytes**.

Safer flow:

1. Build artifacts in the **workspace of the build that ran verification**.
2. Compute checksums and store the JAR as a **CI output/artifact**.
3. Pass **that exact verified JAR** into the publish/staging job.
4. Forbid overwriting release coordinates and verify checksums post-publish.
5. Record producer Git SHA, CI run, test report, and digest in the release manifest.

If policy mandates **rebuilding at publish time**, prove the rebuild uses identical sources/toolchain/dependencies and re-runs the appropriate verification gate; comparing filenames alone is insufficient.

## 11. Real consumer test code with a pinned Stub Runner version

Suppose Billing Service uses Spring Framework 6.1+ to call Order Service. Client code:

~~~java
package com.acme.billing;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient http;

    public OrderClient(String baseUrl) {
        this.http = RestClient.create(baseUrl);
    }

    public OrderDto getOrder(long id) {
        return http.get()
            .uri("/api/orders/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(long id, String status, long amountMinor) {}
}
~~~

A consumer JUnit 5 test:

~~~java
package com.acme.billing;

import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = OrderClientContractTest.TestApp.class)
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/releases"
)
class OrderClientContractTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {}

    @Autowired
    private StubFinder stubFinder;

    @Test
    void readsPaidOrderFromPinnedStubVersion() {
        URL url = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Required Order Service stub did not start"
        );

        OrderClient client = new OrderClient(url.toExternalForm());
        OrderClient.OrderDto dto = client.getOrder(42L);

        assertThat(dto.id()).isEqualTo(42L);
        assertThat(dto.status()).isEqualTo("PAID");
        assertThat(dto.amountMinor()).isEqualTo(125000L);
    }
}
~~~

This example requires **JDK 17+, compatible Spring Boot/Spring Cloud Contract, RestClient, AssertJ**, and an already-published `stubs` artifact; the repository URL is **illustrative**. Private repos may need read credentials and CI-configured TLS/proxies. `StubsMode.REMOTE` specifies **where to download the JAR**, not that the HTTP client calls the Maven repository directly.

Key point: the annotation pins **fixed version `1.4.2`** and the test discovers the **dynamic HTTP stub URL** via `StubFinder`. On CI reruns, keep the **exact checksum of `1.4.2-stubs.jar`**, not just the annotation string.

### 11.1. When tests must move to a new stub release

If the goal is testing Billing against **producer release 1.4.3**, update the artifact coordinates explicitly and record the tested version. That is **a new compatibility test**, not "rerunning with identical 1.4.2 inputs".

With multiple producers:

~~~java
@AutoConfigureStubRunner(
    ids = {
        "com.acme:order-service:1.4.2:stubs",
        "com.acme:inventory-service:2.1.0:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.REMOTE
)
~~~

Record **both artifact coordinates + checksums** and look up separate URLs for Order and Inventory. A rerun keeping Order v1.4.2 while upgrading Inventory to v2.1.1 **no longer shares identical inputs**.

## 12. Dynamic WireMock ports are not contract nondeterminism

A test run might log:

~~~text
Run A: Order stub URL = http://localhost:12347
Run B: Order stub URL = http://localhost:13782
~~~

Two different port numbers **do not mean different contract inputs**. Stub Runner picks an available port on each run; consumer tests must use the **actual address returned by `StubFinder`**. Hardcoding `localhost:8089` causes parallel jobs to collide or hit the wrong instance.

With a properly designed test:

~~~java
URL stubUrl = Objects.requireNonNull(
    stubFinder.findStubUrl("com.acme", "order-service")
);
OrderClient client = new OrderClient(stubUrl.toExternalForm());
~~~

**The reproducibility we want is identical HTTP semantics/responses from the same artifact**, not forcing every CI job to receive the exact same port integer. Ports are runtime environment resources to **discover**, never hardcode. Still ensure the URL uses a hostname reachable from the consumer test's network namespace; `localhost` inside container A does not reach container B.

## 13. Fixtures, databases, and test state: stabilize before every run

A pipeline can download the **exact stub JAR** and still flake due to leaked state:

| State source | Typical bug | How to isolate |
| --- | --- | --- |
| **Producer test database** | Order 42 is `PAID` in run A, `PENDING` in run B. | Seed consistent fixtures; controlled DB/transaction resets. |
| **WireMock request journal** | Run B counts requests from an earlier test. | Separate instances or safe `resetRequests()` between tests. |
| **WireMock scenarios** | State `recovered` lingers from an earlier retry test. | Reset scenarios or create independent servers. |
| **Consumer in-memory cache** | Client reads cache instead of calling the stub. | Clear cache per test or assert caching behavior explicitly. |
| **Clock/timezone** | Deadlines/expirations shift by execution time. | Inject `Clock.fixed` and deterministic timezone when testing time logic. |
| **Random IDs** | Body/keys vary unpredictably. | Use logged seeds or deterministic fixture values. |
| **Authentication** | Test JWT expires the next day. | Use fake/test tokens or reset mock decoders; avoid time-bound real tokens. |
| **Async messages** | Consumer verifies before the event arrives. | Wait with bounded timeouts; isolate queues/topics. |
| **Network dependencies** | Calls an unstable external service. | Stub/fake external boundaries or use controlled integration environments. |

**Never rely solely on `Thread.sleep(3000)` to stabilize tests.** A fixed sleep never proves a request or event arrived. For async flows, await futures/publishers or business state with bounded timeouts and clear error diagnostics.

### 13.1. Fixing time via a testable abstraction

In Java:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
    Instant.parse("2027-02-03T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

Business code should receive `Clock` via dependency injection instead of scattering `Instant.now()` calls whenever expiration/deadline logic matters in tests. The timestamp value is **illustrative** and belongs in fixture configuration.

For producer HTTP responses containing dynamic timestamps, decide explicitly whether contracts assert **format/bounds** or a **fixed value**. Never hardcode absurd timestamps outside production reality, nor make matchers so loose that malformed formats slip through.

## 14. Designing state resets without breaking stubs

In WireMock, these methods have distinct effects:

~~~java
wireMockServer.resetRequests();  // Clear request history.
wireMockServer.resetScenarios(); // Reset scenario state.
wireMockServer.resetAll();       // Clear mappings and all related state.
~~~

If Stub Runner loaded **contract mappings** from a JAR, never call `resetAll()` casually: subsequent requests will start returning 404 because **mappings were wiped**, not because the contract broke.

On a server shared across concurrent tests, one test calling `resetRequests()` can wipe journal entries another test is counting. When running in parallel, prefer **independent server instances per test/class**; if sharing, use correlation IDs and coordination rules preserving measurement accuracy.

### 14.1. No-match 404 vs. business 404

If a stub defines only:

~~~http
GET /api/orders/42
~~~

and the consumer sends `GET /api/order/42`, WireMock returns **404 because no mapping matched**. That is not proof the producer handled `ORDER_NOT_FOUND`. A reproducible 404 consumer test needs a **dedicated error contract** with explicit status and error body/code, while also asserting the exact request path/headers.

Identifying **which mapping executed** separates client regressions from stale or missing stub artifacts.

## 15. Messaging contracts: preserve versions and broker state

Spring Cloud Contract also verifies messages via Groovy/YAML DSL. Example `OrderCreated` event:

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
            header('contentType', 'application/json')
            header('schemaVersion', 1)
        }
        body(
            eventId: 'evt-001',
            orderId: 'ORD-42',
            amountMinor: 125000
        )
    }
}
~~~

With messaging, **an identical stub JAR** is insufficient for identical outcomes if:

- The broker holds **stale messages in queues/topics**.
- Consumer groups/offsets are shared and shift across runs.
- Retries/DLQs/replays resurface events from earlier runs.
- Serializers/schema registries return different versions or compatibility modes.
- Producer outputs generate random `eventId`s or uncontrolled timestamps.
- Concurrent tests steal each other's messages.

A safe pattern uses **test binders/in-memory adapters** for consumer contract tests, and **pinned broker container versions** for real transport integration tests. For broker tests:

1. Use run-isolated namespaces/topics/consumer groups when needed.
2. Set explicit offsets/start positions and purge data per policy.
3. Record schema versions, destinations, and broker image versions.
4. Await messages conditionally with timeouts instead of assuming instant delivery.
5. Use `eventId`/correlation IDs to avoid cross-talk or duplicate handling.

**`StubTrigger`/labels can fire sample messages**, yet do not prove serialization on a real broker or exactly-once processing. Reproducible messaging tests require both **contract artifacts** and **controlled transport state/environments**.

## 16. CI inputs should be persisted in a run manifest

Every critical pipeline should emit a **rerunnable manifest** (run provenance). Example:

~~~json
{
  "runId": "billing-contract-ci-991",
  "source": {
    "repository": "billing-service",
    "commit": "0123456789abcdef0123456789abcdef01234567",
    "workflowRevision": "abcdefabcdefabcdefabcdefabcdefabcdefabcd"
  },
  "build": {
    "jdk": "17",
    "mavenWrapperVersion": "3.9.x",
    "springCloudReleaseTrain": "2023.0.x",
    "testProfile": "contract"
  },
  "stubs": [
    {
      "coordinate": "com.acme:order-service:1.4.2:stubs",
      "sha256": "<actual-jar-sha256>",
      "sourceProducerRunId": "order-producer-ci-483",
      "resolutionMode": "REMOTE",
      "repositoryId": "contract-releases"
    }
  ],
  "environment": {
    "runnerImageDigest": "<actual-image-digest>",
    "timezone": "UTC",
    "testDataRevision": "fixtures-v5"
  },
  "result": {
    "producerVerificationRef": "order-producer-ci-483/report",
    "consumerTestReportRef": "billing-contract-ci-991/tests",
    "status": "FAILED"
  }
}
~~~

This manifest is an **internal design template**, not a mandatory Spring Cloud Contract or CI provider schema. `<...>` placeholders and `x` versions **do not guarantee reproducibility**; in production, populate **exact tool versions/digests and real checksums** emitted by tools.

### 16.1. Data to retain securely without putting into manifests

Some inputs are **secrets** or sensitive:

- Maven/Gradle repository tokens.
- Private keys / client certificates.
- Broker/database passwords.
- Production JWTs or real customer data.

Never store them in JSON manifests or artifact logs. Instead, record **secret references/identities and policy versions** without leaking values, ensuring authorized operators can reconstruct valid environments via the secret manager. A rotated credential can change between two runs **without altering expected contract results**, provided artifact access stays equivalent.

**Never put raw secrets into test fixtures or stubs** just to have "identical inputs". Contract data must be synthetic test data incapable of accessing real systems.

## 17. Pipeline pattern following "build once, test, promote"

A producer/consumer pipeline typically has three stages:

~~~text
PRODUCER:
  checkout immutable producer SHA
    -> restore verified toolchain/dependencies
    -> generate producer contract tests
    -> run tests, require nonzero required test count
    -> package stubs and producer application
    -> compute stub SHA-256 / image digest
    -> store artifact + producer run manifest

COMPATIBILITY:
  checkout immutable consumer SHA
    -> use exact stub artifact from producer run
    -> run Stub Runner consumer test with pinned coordinates
    -> save consumer run manifest/test reports

PUBLISH/DEPLOY:
  require producer and compatibility gates pass
    -> publish or promote immutable stubs/app artifact
    -> deploy verified image digest
    -> record deployment revision/health metrics
~~~

**Stage ordering can vary by organization:** to run consumer compatibility tests **before** publishing to the release repository, use a **staging repository/artifact handoff** or install exact JAR bytes into a local test repository. Once gates pass, promote **that exact artifact** to release. You do not need to publish an unverified release and hope red consumer tests stop it in time.

If consumers run on a separate CI runner, `LOCAL` works only when the JAR is transferred and installed properly into that runner's local Maven repo. In cross-team environments, `REMOTE` with a controlled staging/release repository is usually cleaner.

## 18. CI pseudocode keeping inputs constant

The example below is **vendor-neutral pseudocode**, not a runnable GitHub Actions/GitLab CI/Jenkins file:

~~~yaml
pipeline:
  checkout:
    source: exact-git-commit
    workflow: approved-workflow-revision

  environment:
    jdk: pinned-vendor-and-version
    build_tool: repository-wrapper
    ci_image: pinned-image-digest
    test_timezone: UTC

  inputs:
    stub_coordinate: com.acme:order-service:1.4.2:stubs
    stub_sha256: <verified-digest>
    fixture_revision: fixtures-v5
    dependency_lock: committed-or-controlled-version-graph

  producer_gate:
    generated_contract_tests_required: true
    test_count_must_be_positive: true
    fail_if_contract_tests_skipped: true

  consumer_gate:
    run_real_client_through_stub_runner: true
    assert_status_and_business_data: true
    preserve_request_matching_evidence: true

  publish:
    allowed_after_required_gates: true
    promote_verified_bytes: true
    prevent_release_overwrite: true
    save_run_manifest: true
~~~

**The keys in this YAML are not Spring Cloud Contract options.** A real CI system must map them to concrete scripts, artifact stores, job dependencies, checks, and permissions. `stub_sha256: <verified-digest>` is a **rule to enforce**, not automatic checksum computation or comparison.

### 18.1. Illustrative shell snippet for a Maven producer

On a Linux CI runner with Maven Wrapper:

~~~shell
# Verify exact source/toolchain of the run.
git rev-parse HEAD
./mvnw -version

# Generate and run producer tests per configured lifecycle.
./mvnw -B -ntp clean verify

# Only after the right artifact exists and test reports pass:
sha256sum target/order-service-1.4.2-stubs.jar
~~~

On Windows PowerShell, compute SHA-256 with `Get-FileHash -Algorithm SHA256`. Commands in this lesson are **practice guides**, not executed while authoring content. `target/order-service-1.4.2-stubs.jar` is an illustrative path; packaging configuration or plugin versions may place artifacts elsewhere.

**Compute checksums only after proving generated tests actually ran.** A stale file left in `target/` from a prior build must never count as the current run's artifact; use `clean` or isolated workspaces to rule that out.

## 19. Three rerun modes and how to interpret outcomes

### 19.1. Mode A: rerun from the current CI run

Scenario: a consumer job failed because a WireMock request returned 404. Clicking `Rerun failed job` works if the CI system preserves:

- Same **consumer source Git SHA** and workflow revision.
- Same **stub artifact coordinates/checksum**.
- Same toolchain/CI image and test profile.
- Same data fixtures/reset policy and dependency graph.

If the rerun passes, that is **insufficient** to declare "the bug is gone". It could be a flaky test or drifted inputs. Compare manifests across both runs to rule out input drift, then inspect request journals and infrastructure state.

### 19.2. Mode B: cold-cache rebuild

Scenario: suspecting the local Maven cache holds a stale stub.

Run from a **fresh, isolated workspace/repository cache**, pulling artifacts and dependencies with fixed versions. With Maven, specify a run-dedicated local Maven repository:

~~~shell
./mvnw -B -ntp \
  -Dmaven.repo.local=/tmp/contract-rerun-m2 \
  clean verify
~~~

The path `/tmp/contract-rerun-m2` fits illustrative Linux runners. This checks **clean remote resolution**, rather than guaranteeing every Maven/Stub Runner version shares that local repository automatically; inspect Stub Runner's resolver separately.

If warm-cache PASSES while cold-cache FAILS:

- An artifact or dependency may not have been published properly.
- Credentials, proxies, TLS, or metadata resolution may be failing.
- The cache was masking a local build with the wrong version or unpublished changes.
- The job may rely on files created manually on an older runner.

**Never rush to wipe all production caches** before finding the root cause: reproduce in an isolated environment and compare manifests/checksums.

### 19.3. Mode C: replay from an archived artifact

Scenario: reproducing a bug from a release weeks ago.

Download the exact **archived `stubs` JAR and verify SHA-256**; run the matching consumer source/version with the recorded toolchain/test fixtures. To avoid network dependencies in CI, install the artifact into an isolated local Maven repo and use Stub Runner `LOCAL`. Still prove the **exact JAR** was loaded; `LOCAL` does not guarantee checksums on its own.

This is useful when snapshot repositories moved on or old releases were purged per retention policy. If artifacts or dependencies are no longer recoverable, record **reproducibility limits** rather than claiming the bug never existed.

## 20. Parallel tests: "identical inputs" does not mean identical execution order

In CI, two test threads can execute in different orders. If they share global state, ports, WireMock request journals, or a single DB schema, outcomes can depend on scheduling.

Error-prone example:

~~~java
// Shared static configuration causes conflicts during parallel execution.
RestAssured.baseURI = "http://localhost";
RestAssured.port = 8089;
~~~

Another test may mutate `RestAssured.port` or bind port 8089, polluting the entire suite. Use **dedicated request specifications/client instances**, dynamic ports from `StubFinder`, or separate servers per class/context.

| Race source | Mitigation |
| --- | --- |
| Shared mutable client config | Instantiate separate clients with injected base URLs. |
| Shared WireMock mappings/journal | Separate test contexts/servers, or synchronize state/correlations properly. |
| Overlapping database transactions | Isolate schemas/databases; explicit seed/cleanup; avoid order dependence. |
| Shared message topic/consumer group | Run-scoped namespaces and groups when needed; manage offsets. |
| Fixed ports | Dynamic ports and controlled service discovery. |
| Global fake clock or RNG | Inject test-scoped instances; never mutate statics across tests. |
| External rate limits | Stub/fake or partition quotas; bounded retries. |

When a test **passes only if test A ran first**, that is a test-isolation bug, not a reason to freeze suite ordering forever. A trustworthy rerun must not depend on undeclared side effects.

## 21. When identical checksums still yield different outcomes

A `stubs` JAR with an identical SHA-256 proves only that **JAR bytes did not change**. It does not prove:

1. Every test sent the **same HTTP request**.
2. The same Java/Jackson version parsed the body identically.
3. The same Spring profile and retry configuration applied.
4. Identical broker/DB/timezone/network conditions.
5. Identical test ordering or concurrency.
6. The consumer picked up the **stub instance's** URL rather than hitting an old server.
7. Consumer tests held identical expectations/fixtures.

So when SHA-256 matches yet tests fail differently, shift focus from **artifact drift** to **source/configuration/environment/test state**. A helpful diagnostic step is verifying **actual requests** on WireMock:

~~~java
wireMockServer.verify(
    1, getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

When using Stub Runner without a `WireMockServer` bean, query the **WireMock Admin API** at the discovered stub URL to inspect the request journal. Never dump sensitive Authorization headers, cookies, or bodies to CI logs.

## 22. Diagnostic matrix for diverging reruns

| Symptom | First suspect | How to verify |
| --- | --- | --- |
| Same Git SHA yet different stub checksum | Overwritten artifact, changed SNAPSHOT/remote metadata. | Compare coordinates, source producer run, checksums, and repo audit logs. |
| Same stub checksum yet different JSON parse | Client/Jackson/toolchain or consumer source changed. | Compare consumer SHA, dependency graph, profile, DTOs, and raw payloads. |
| Warm cache green, cold cache red | Unpublished artifact, repo auth/proxy/TLS, dynamic version. | Test resolver on a clean runner with redacted logs. |
| Cold cache green, warm cache red | Stale/corrupt local cache or old snapshot metadata. | Compare local file hash with remote; isolate cache to verify. |
| Run A port 12347, run B port 13782 | Normal dynamic port assignment by Stub Runner. | Check `StubFinder` and actual request target; never force identical ports. |
| `Address already in use` | Hardcoded port or two tests sharing a server. | Dynamic ports and isolation. |
| WireMock verify count climbs each rerun | Unreset request journal or shared context. | Proper lifecycle `resetRequests()` or fresh server instances. |
| Outcome depends on time of day | Clock, token expiry, timezone. | Inject fixed clocks and test tokens; pin timezone. |
| Messaging test sees 0 or 2 events | Broker group/offset, DLQ/replay, parallel consumers. | Isolate topics/groups and await events with timeouts. |
| Consumer stub returns 404 | Wrong mapping, request method/path/headers, or stale artifact. | Inspect JAR and request journal; separate no-match from business 404. |
| Right artifact coordinates yet download gets 401/403 | Repository auth/permissions changed. | Check read identity and secret refs without printing tokens. |
| Maven `-U` changes test outcome | Snapshot/dependency metadata updated. | Compare dependency graphs and artifact hashes before/after. |
| Producer tests green yet deployed producer breaks consumers | Insufficient test coverage, wrong image digest, or mismatched publish/deploy build. | Compare generated tests, release manifest, and actual deployment. |
| Rerun job ran with a newer workflow | CI config drift / updated actions. | Compare workflow revisions, script versions, and runner images. |
| Tests fail together yet pass individually | Shared state / race / ordering. | Run parallel/isolation experiments and audit fixtures. |

**Investigate in order:** source identity → toolchain/dependencies → stub coordinates **and bytes** → CI configuration → fixtures/state → actual requests → producer/consumer implementation. Never edit contract DSL just to work around a cache or repository auth bug.

## 23. Security when collecting inputs for reruns

The goal "retain enough info to reproduce" **never permits storing everything**. Risks:

| Data | Store in CI manifest? | Rationale |
| --- | --- | --- |
| Git SHA, CI run ID | **Yes** | Identifies source and test run. |
| Artifact coordinates, SHA-256 | **Yes** | Proves exact JAR used. |
| JDK/build tool versions | **Yes** | Investigates runtime/toolchain drift. |
| Image digest, test profile | **Yes** | Identifies CI runtime. |
| Non-sensitive secret reference/identity name | **Acceptable** | Reconstructs permissions from secret manager without exposing values. |
| Repository tokens/passwords/private keys | **No** | Never store secrets in artifacts/logs. |
| Raw HTTP Authorization/Cookie | **No** | Could grant real access. |
| Real customer data in stubs/fixtures | **No** | PII leakage and data-policy violation. |
| Full environment dump | **No** | May contain tokens and sensitive internal endpoints. |

When sharing run manifests across teams, define **read permissions**, because repository names, service graphs, deployment revisions, and artifact registries can be sensitive internal info. Set retention policies and redact CI logs/test reports before uploading.

## 24. When can reruns never produce 100% identical outputs?

Some factors **cannot or should not be pinned completely**:

- Scheduler and network latency.
- Dynamic ports and process IDs.
- Short-lived rotated certificates/tokens.
- External services or brokers with live state.
- Timeouts and contention on shared CI runners.
- Overwritten SNAPSHOT artifacts with no archive.
- External integrations with irreversible side effects.

In those cases, the goal is:

1. **Pin inputs affecting semantics:** sources, contracts, stubs, dependencies, and fixtures.
2. **Isolate what can be isolated:** servers, DBs, brokers, caches, and clocks.
3. **Record what cannot be pinned:** runners, network, wall time, external service versions.
4. **Assert stable behavior:** never assert a specific port number or tight wall-clock duration unless promised by the contract.
5. **Report bounds:** state "same artifact/commit, different network environment" rather than claiming an identical rerun.

Reproducibility is **being able to explain and verify inputs and outcomes**, not demanding identical timestamps, ports, and line ordering in every log.

## 25. Hands-on lab: rerunning a consumer contract failure

Prepare two Spring Boot projects: **Order Service** with Contract Verifier, and **Billing Service** with Stub Runner.

1. **Define an HTTP contract** for `GET /api/orders/42` returning JSON `id=42`, `status=PAID`, `amountMinor=125000` in Groovy or YAML DSL.
2. **Create producer implementation + base test**, seed fixture data, and confirm generated producer tests are generated and run.
3. **Pin JDK, Maven/Gradle Wrapper, and Spring Cloud BOM/plugin versions** in build config; record them in a run manifest.
4. **Run producer verification**, inspect reports and test counts; intentionally change `amountMinor` from number to string to verify tests FAIL, then revert.
5. **Package and publish a fixed-version `stubs` JAR**, e.g. `com.acme:order-service:1.4.2:stubs`; compute the real JAR SHA-256.
6. **Write a real `OrderClient` and Stub Runner consumer test** pinned to `1.4.2`, using `StubFinder` for dynamic URLs, asserting status/body and key method/path.
7. **Save consumer Git SHA, producer release SHA, artifact coordinates/checksum, CI run ID, toolchain, and profile** in the manifest.
8. **Run consumer CI Run A**, recording results and test reports. Commit no secrets.
9. **Rerun the same source/artifact in Run B** with a warm cache; compare manifests and checksums before declaring results identical or different.
10. **Rerun from a cold cache in Run C**, confirming the repository re-fetches the exact artifact and read permissions work.
11. **Inject drift** in a test environment: publish a new SNAPSHOT at the same coordinates or change a dynamic dependency; verify checksums/dependency graphs expose the changed input. Never overwrite real releases.
12. **Inject flakiness**: share one request journal across two tests or skip scenario resets; observe unstable counts, then isolate servers/state.
13. **Test a fixed clock** via `Clock.fixed` and test tokens; compare against wall-clock dependence.
14. **Test a no-match 404** from a wrong client path; use the request journal to distinguish it from a business 404 contract.
15. **If using messaging**, use isolated topics/groups and an event with fixed `schemaVersion`/`eventId`; test replay to observe broker state effects.
16. **Write an investigation report**: classify each incident as source drift, artifact drift, environment drift, test state leak, or real regression.
17. **Wire into CI gates**: publish immutable stubs only after producer verification; consumer compatibility tests use exact versions, reports, and matching checksums.

**Passing criteria:** the learner can point to the **exact Git SHAs, `stubs` artifact, and checksums of two runs**, rerun consumer tests from a fresh environment, explain why ports can differ without contracts changing, and separate **input drift** from **contract/implementation bugs**.

## 26. Checklist for a rerunnable pipeline

| Check | Expectation |
| --- | --- |
| Source | Full producer/consumer Git SHAs and workflow revisions are traceable. |
| Contracts | Source paths/commits pinned; no duplicate Groovy/YAML definitions for one scenario. |
| Build toolchain | Maven/Gradle Wrapper, JDK, and CI images pinned or recorded with exact versions/digests. |
| Dependency resolution | BOM/plugin/lock versions accurate; no uncontrolled dynamic/mutable inputs. |
| Producer verification | Generated tests executed with valid test counts and PASSED before publishing. |
| Stub artifact | Coordinates, `stubs` classifier, SHA-256, and producer run reconcilable. |
| Publication | Immutable releases; if using SNAPSHOTs, record run-specific byte identity. |
| Consumer testing | Stub Runner fetches the exact artifact; real client/listener verified, not just WireMock. |
| HTTP runtime | Dynamic stub URL looked up properly; no hardcoded ports. |
| Messaging runtime | Schema/destination, broker/container versions, and topics/groups/offsets controlled. |
| Fixtures | DB, clock, random seeds, auth test data, and request journals/scenarios reset/isolated. |
| Concurrency | Tests do not share mutable state uncontrollably. |
| Caching | Warm/cold cache strategy with artifact checksum verification. |
| Manifest | Contains sources, toolchain, stub hashes, and test result refs with zero secrets/PII. |
| Rerun semantics | Distinguishes source rerun, rebuild, and artifact replay; states remaining variances. |
| Incident handling | Traceable path from failure log → manifest → artifact → contract → producer/consumer source. |

## 27. Self-check questions

1. Why does clicking "Rerun on the same branch" not guarantee identical inputs?
2. What is the difference between **identical Maven coordinates** and **identical artifact checksums**?
3. How can a `-SNAPSHOT` JAR change consumer CI results without any source code changes?
4. Does `StubsMode.LOCAL` prove the remote repository and credentials still work?
5. Why must you record both the producer Git SHA and the consumer Git SHA?
6. When CI runs a PR on a synthetic merge commit, what must you record to rerun accurately?
7. Does using a Spring Cloud BOM automatically lock Gradle/Maven plugin versions, the JDK, and runner images?
8. Why does a generated producer test count of 0 make a `stubs` artifact untrustworthy even on a green build?
9. Can a consumer test using the exact stub checksum still flake due to `Clock`, DB, or WireMock journals?
10. Why do differing WireMock ports between Run A and Run B not necessarily break reproducibility?
11. How does `resetRequests()` differ from `resetAll()`, and why be careful when using Stub Runner?
12. If a consumer test fails with 404, how do you tell a wrong-path no-match from a business 404?
13. Why is one warm-cache PASS insufficient to prove a remote artifact resolves from a cold cache?
14. Does `mvn -U` guarantee downloading the exact bytes of an older SNAPSHOT?
15. In messaging tests, how do broker offsets, consumer groups, and DLQs affect reruns?
16. Distinguish **rerun same job**, **rebuild same SHA**, and **replay verified artifact**.
17. What must a run manifest store, and what must it exclude?
18. With multiple producer stubs, which identities must be recorded to prove the exact version combination?
19. How does "build once, test, promote" prevent drift between the producer image and stub artifact?
20. If cold cache FAILS while warm cache PASSES, what causes should you investigate before editing code?
21. When are two runs with differing runtime details still considered to test identical contract semantics?
22. Why can green consumer CI results never replace generated producer verification?

**Conclusion:** **Rerunning a pipeline with identical inputs means more than keeping the same Git commit; you must pin the exact version and bytes of the `stubs` artifact, toolchain, dependency graph, CI configuration, fixtures, and environment state**. In Spring Cloud Contract, producers must generate and execute generated tests before publishing the `stubs` JAR; consumers use Stub Runner to load **the exact pinned artifact**, look up dynamic HTTP URLs or configure messaging adapters per contract, and test real client/listener code. Persist **run manifests with Git SHAs, artifact coordinates/checksums, toolchains, and test reports**, distinguish warm vs. cold caches, avoid mutable snapshots when replaying history, and isolate shared state. That way, when a CI job fails, teams can prove whether they are reproducing **the exact same interaction and artifact** or encountering **a new input**—instead of editing contracts or rerunning endlessly in the dark.
