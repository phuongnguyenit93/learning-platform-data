# Regression Testing the Stub Publish and Download Pipeline

## Learning Objectives

**Spring Cloud Contract** helps producers and consumers agree on HTTP or messaging behavior using the **Groovy/YAML DSL**. Producers generate tests verifying the implementation and package a **stub artifact**; consumers use **Stub Runner** to download stubs and test their clients/handlers. In CI/CD, the stub publish-and-download chain needs regression testing so changes to build tools, plugins, repositories, or versions do not silently lose artifacts or cause consumers to run against stale builds.

This lesson belongs to the **Tool Compatibility** chapter and focuses on **regression testing the stub publish and download pipeline**. After this lesson, you can:

- Design end-to-end regression tests covering publish → resolve → Stub Runner → consumer verification.
- Distinguish contract definitions JARs, producer application JARs, and producer stubs JARs.
- Verify Maven/Gradle publications, the `stubs` classifier, POM/metadata, and repository layouts.
- Build compatibility matrices across JDK, Maven/Gradle, Spring Boot/Cloud, Spring Cloud Contract, and repository managers.
- Separate failures in contract discovery, generated tests, packaging, publishing, download, extraction, startup, and request matching.
- Use versions, digests, and provenance to make pipelines reproducible.
- Design smoke tests, negative tests, upgrade tests, and release gates.
- Diagnose green builds where consumers still pull old stubs or miss mappings.

> **Principle:** regression tests must verify the **exact artifact consumers actually download and run**, not just files sitting in the producer's build directory. Separately green producer and consumer builds prove nothing if both sides do not share the same coordinates, version, and digest.

## 1. Context: One Tool Change Can Break the Entire Stub Chain

Suppose **Inventory Service** is the producer and **Checkout Service** is the consumer. The contract defines:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-101","available":true,"quantity":8}
~~~

The producer builds and publishes:

~~~text
com.example:inventory-producer:2.3.0:stubs
~~~

Checkout downloads the stub via Stub Runner, starts WireMock, and tests its HTTP client.

A pipeline upgrade can alter the Spring Cloud Contract plugin, Maven/Gradle publication, Spring Boot/Cloud BOM, JDK, wrapper, generated mapping layout, repository credentials, snapshot metadata, or how Stub Runner resolves classifiers.

The outcome can be:

~~~text
Producer build: SUCCESS
Application JAR: published
Stub JAR: missing or stale

Consumer build: SUCCESS
Stub Runner: resolves old cached artifact
Consumer tests: PASS
Production producer: changed behavior
~~~

This is a **false green**: there is zero evidence that the consumer tested stubs from the new producer revision.

### Chain to Verify

~~~mermaid
flowchart LR
    A["Contract source + revision"] --> B["Producer discovery"]
    B --> C["Generate producer tests"]
    C --> D["Run against producer"]
    D --> E{"PASS?"}
    E -->|No| X["Block publish"]
    E -->|Yes| F["Package :stubs JAR"]
    F --> G["Publish exact coordinates"]
    G --> H["Resolve from clean consumer"]
    H --> I["Stub Runner starts"]
    I --> J["Consumer tests"]
    J --> K{"PASS?"}
    K -->|No| X
    K -->|Yes| L["Record digest + toolchain"]
~~~

Every arrow represents a boundary that can break. In particular, you must prove published artifacts can be downloaded from the **consumer's environment**.

## 2. Three Artifact Types and Version Chains

| Artifact | Example coordinates | Contents and purpose |
|---|---|---|
| **Contract definitions JAR** | `com.example.contracts:inventory-contracts:1.6.0` | Groovy/YAML DSL for producer test generation |
| **Producer application JAR** | `com.example:inventory-producer:2.3.0` | Inventory application |
| **Producer stubs JAR** | `com.example:inventory-producer:2.3.0:stubs` | Mappings/fixtures or message stub definitions for consumers |

A pipeline may use distinct versions:

~~~text
Contract definitions: com.example.contracts:inventory-contracts:1.6.0
Producer application:  com.example:inventory-producer:2.3.0
Producer stubs:        com.example:inventory-producer:2.3.0:stubs
~~~

The contract JAR `1.6.0` does not have to share producer version `2.3.0`. What must be preserved is **traceability**: which producer revision verified which contract revision, and which stub artifact came from that verification run.

A publication can succeed for the main artifact while omitting the classifier:

~~~text
Published:
  inventory-producer-2.3.0.pom
  inventory-producer-2.3.0.jar

Missing:
  inventory-producer-2.3.0-stubs.jar
~~~

If you check only the application JAR, the pipeline turns green even though consumers cannot resolve stubs. Conversely, a JAR named `*-stubs.jar` can still be empty or contain stale mappings; inspect both contents and consumer runtime behavior.

## 3. What Must Pipeline Regression Tests Prove?

This is an integration scenario spanning the producer build, artifact repository, and consumer build—not just a unit test of one script.

1. The producer discovers the right contract files.
2. Generated tests match expected counts and actually execute.
3. Tests run against the producer implementation using the right base class and test mode.
4. The stub JAR is built with the right classifier.
5. The JAR holds required mappings, fixtures, and message definitions.
6. Publication uses exact coordinates, repository, and metadata.
7. The consumer downloads the artifact in a clean environment.
8. The consumer loads the exact published version and digest.
9. Stub Runner starts the HTTP server or message stubs.
10. The real consumer client/handler interacts and runs meaningful assertions.
11. Deliberate misconfigurations make the pipeline fail at the right layer.
12. Toolchain upgrades cause no unintended behavioral drift.

| Test type | Scope | Value |
|---|---|---|
| Build logic test | Small task/script/plugin config | Catches local mistakes |
| Producer contract test | DSL → generated test → producer | Proves producer honors contracts |
| Packaging test | JAR/classifier/entries | Proves packaging output is sound |
| Publication test | Upload + metadata | Proves registry received exact coordinates |
| Resolution test | Consumer resolve | Proves resolver downloads artifact |
| Stub Runner smoke | Resolve/extract/start | Proves runtime loads mappings |
| Consumer compatibility | Client/handler calls stub | Proves consumer handles the interface |
| Toolchain test | Version matrix | Catches upgrade regressions |

You can run fast checks on PRs and the full matrix on a schedule or pre-release. Never drop end-to-end tests completely just because they are slower.

## 4. Sample Contract for the Regression Pipeline

### Groovy DSL

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Inventory returns deterministic stock for SKU-101'

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

### Equivalent YAML DSL

~~~yaml
description: 'Inventory returns deterministic stock for SKU-101'
request:
  method: GET
  url: /api/inventory/SKU-101
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-101
    available: true
    quantity: 8
~~~

Keep only one definition for the same request in the demo pipeline to avoid duplicate mappings. Deterministic fixtures ensure results do not depend on clocks, UUIDs, or database state.

Regressions should keep stable:

- Contract discovery from the exact source path.
- Request method, path, and headers unchanged unintentionally.
- JSON boolean `true` and number `8` preserving their types.
- Producer tests continuing to assert status `200` and body.
- Stub mappings retaining request matchers and response fixtures.
- Consumer receiving exact JSON via Stub Runner.
- Artifact version and classifier unchanged unintentionally.

## 5. Toolchain Compatibility Matrix

Do not upgrade JDK, Spring Boot, Spring Cloud Contract plugin, Gradle, and repository simultaneously if you need to pinpoint regression causes.

| Tool layer | Variants to manage | What to verify |
|---|---|---|
| JDK | Major version/distribution | Compilation, test runtime, encoding |
| Maven | Wrapper/version | Lifecycle, plugin goals, attached artifacts |
| Gradle | Wrapper/version | Task graph, caching, publication |
| Spring Boot | Release line | Test context, dependency alignment |
| Spring Cloud | BOM/release train | Compatibility with Boot |
| Spring Cloud Contract | Maven/Gradle plugin | DSL parser, generated tests, stubs |
| Test framework | JUnit 4/5, Spock if used | Generated test source/engine |
| Stub Runner | Compatible version | Resolver and server startup |
| WireMock/binder | Dependency version | Mapping and message behavior |
| Repository manager | Nexus/Artifactory/config | Metadata, snapshots, auth, checksums |
| CI runner | OS/image/architecture | Paths, permissions, TLS, networking |

Do not run every permutation. Partition the matrix into:

- **Supported baseline:** combination officially supported by the project.
- **Current release:** combination currently building and releasing.
- **Upgrade candidate:** target combination to adopt.
- **Compatibility boundary:** legacy/new versions needing cross-compatibility.
- **Negative cases:** deliberate misconfigurations verifying clear failures.

Only test combinations supported by the frameworks or committed to by your organization. Passing a build on a random combination does not certify compatibility.

## 6. Identify the Toolchain Actually Running

### Maven

Verify the Maven Wrapper, `spring-cloud-contract-maven-plugin`, Spring Boot/Cloud BOM, Surefire/Failsafe, JUnit engine, repositories, and CI profiles.

~~~bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
~~~

These commands reveal Maven/JDK, the effective POM, and the dependency graph. A parent POM does not guarantee which plugin version runs if a child module overrides it or a different profile activates.

### Gradle

Verify the Gradle Wrapper, Spring Cloud Contract plugin, plugin repositories, dependency constraints, `maven-publish`, test source sets, and build cache.

~~~bash
./gradlew --version
./gradlew :inventory-producer:tasks --all
./gradlew :inventory-producer:dependencies
~~~

In multi-project builds, inspect the **subproject** publishing the artifact. Root `version`/`group` do not guarantee every subproject uses the same values.

### Record Before/After Upgrade

~~~text
Before:
  JDK: <version-A>
  Gradle: <version-A>
  SCC plugin: <version-A>
  Producer tests: <count-A>
  Stub artifact: <coordinate-A>
  Stub digest: <digest-A>

After:
  JDK: <version-B>
  Gradle: <version-B>
  SCC plugin: <version-B>
  Producer tests: <count-B>
  Stub artifact: <coordinate-B>
  Stub digest: <digest-B>
~~~

A changed digest does not automatically prove a regression because metadata, timestamps, or generated sources may shift. Compare **coordinates, mapping contents, and consumer behavior**.

## 7. Producer Regression: From DSL to Stub JAR

~~~mermaid
flowchart TD
    A["Pinned contract revision"] --> B["Pinned toolchain"]
    B --> C["Discover contract files"]
    C --> D{"Expected contracts > 0?"}
    D -->|No| X["Fail"]
    D -->|Yes| E["Generate producer tests"]
    E --> F["Compile and execute"]
    F --> G{"Tests executed and PASS?"}
    G -->|No| X
    G -->|Yes| H["Generate mappings"]
    H --> I["Package classifier stubs"]
    I --> J["Inspect archive and metadata"]
    J --> K["Publish to staging"]
~~~

### Gate A — Discovery

Check paths and contract counts. If a module is expected to hold contracts yet the plugin discovers 0 files, fail the pipeline instead of packaging an empty JAR.

Common causes:

- Wrong `contractsDslDir` (Gradle) or `contractsDirectory` (Maven).
- External contract JAR has wrong `contractsPath`.
- `includedFiles`/`ignoredFiles` filter out all DSL files.
- Multi-module build runs tasks on the wrong subproject.
- Source/resource paths changed after a plugin upgrade.

### Gate B — Producer Verification

Generated tests must come from the exact revision, compile under the test framework, extend the right base class, call the producer implementation, actually run, and PASS.

**Having generated sources on disk is not producer verification.** `BUILD SUCCESS` with 0 tests is no proof either.

### Gate C — Packaging

Verify the stub packaging task/goal ran, the `stubs` classifier is attached, mappings/fixtures/message definitions are complete, body files are included, and the artifact matches the revision whose tests PASSED.

## 8. Maven Producer: Lifecycle and Attached Classifier

In a Maven producer configured with `spring-cloud-contract-maven-plugin`:

~~~bash
./mvnw -B -ntp clean verify
~~~

Install into the local Maven repository:

~~~bash
./mvnw -B -ntp install
~~~

Push artifacts to a remote repository:

~~~bash
./mvnw -B -ntp deploy
~~~

| Goal/lifecycle | Primary outcome |
|---|---|
| `verify` | Executes configured verification goals |
| `install` | Installs main and attached artifacts into local Maven |
| `deploy` | Uploads attached artifacts to remote repository |

The Maven lifecycle only runs bound plugin goals. If the contract plugin isn't bound to the right phase, `verify` can still succeed without generating producer tests or stubs.

Regression assertions:

- Effective POM shows the expected plugin version.
- Plugin is enabled in the producer module.
- Generated tests are discovered by the test runner.
- Output contains the stub JAR.
- `install` puts the `stubs` classifier into the local repo.
- `deploy` uploads main JAR, POM, and stub JAR.
- A separate consumer build resolves the classifier.

You can test resolution with the Maven Dependency Plugin:

~~~bash
./mvnw -B -ntp dependency:get -Dartifact=com.example:inventory-producer:2.3.0:jar:stubs -Dtransitive=false
~~~

This single-line command works in PowerShell, CMD, or Bash. The CLI coordinate format is `group:artifact:version:packaging:classifier`. It does not start Stub Runner and does not prove the JAR contains mappings.


## 9. Gradle Producer: Task Graph and Publication

With modern Gradle plugins, common tasks include `contractTest` and `verifierStubsJar`; **verify task availability on your actual plugin version**.

~~~bash
./gradlew --version
./gradlew :inventory-producer:tasks --all
./gradlew :inventory-producer:contractTest
./gradlew :inventory-producer:verifierStubsJar
~~~

Inspect the task graph, outputs, and exit codes—do not run one task name and assume everything passed.

### Publication with Maven Publish

Illustrative publication:

~~~groovy
plugins {
    id 'java'
    id 'maven-publish'
    // Spring Cloud Contract plugin/version configured separately.
}

group = 'com.example'
version = '2.3.0'

publishing {
    publications {
        verifiedStubs(MavenPublication) {
            groupId = 'com.example'
            artifactId = 'inventory-producer'
            version = project.version.toString()
            artifact(tasks.named('verifierStubsJar'))
        }
    }
}
~~~

This is an **illustrative snippet**, not a complete build file. Task `verifierStubsJar` must exist, the artifact must carry the `stubs` classifier per plugin/version, and publication also needs repository upload config.

If the publication is named `verifiedStubs`, Gradle may create a task like `publishVerifiedStubsPublicationToMavenLocal`. Check `tasks --all` instead of assuming task names across all projects.

Gradle regression assertions:

- `contractTest` runs in the right subproject.
- Test reports record executed counts and PASS results.
- `verifierStubsJar` emits the JAR in the output directory.
- The JAR has the right classifier and expected entries.
- Publication specifies the exact group/artifact/version.
- The publish task runs and the repository receives the exact file.
- A clean consumer job resolves the artifact via the same coordinates.

**`mavenLocal()` in `repositories` only lets Gradle read from the local Maven repository; it does not publish artifacts into it.**

## 10. Inspecting Archives and Maven Metadata

The regression pipeline must inspect the artifact **after packaging and before promotion**.

~~~bash
jar tf inventory-producer-2.3.0-stubs.jar
~~~

A common Spring Cloud Contract layout:

~~~text
META-INF/
META-INF/MANIFEST.MF
META-INF/com.example/inventory-producer/2.3.0/
META-INF/com.example/inventory-producer/2.3.0/mappings/
META-INF/com.example/inventory-producer/2.3.0/mappings/stockAvailable.json
~~~

Actual layouts depend on plugin/configuration, consumer-specific stubs, and contract types. This is an example, not a mandatory schema for every version.

In a Maven repository, files typically appear as:

~~~text
com/example/inventory-producer/2.3.0/
  inventory-producer-2.3.0.pom
  inventory-producer-2.3.0.jar
  inventory-producer-2.3.0-stubs.jar
~~~

Verify:

1. The `-stubs.jar` file exists.
2. POM/metadata match the publication.
3. The JAR contains mappings for the contracts under test.
4. External fixtures referenced by mappings are present.
5. It is not confused with the application fat JAR.
6. Checksum/digest is recorded to compare against consumer downloads.

A JAR holding many mappings does not prove the `GET /api/inventory/SKU-101` mapping is included. Regression tests should check specific entries or run a consumer smoke test confirming the mapping loads.

If a mapping references `bodyFileName`, the corresponding response file must also exist in the archive per Stub Runner/WireMock conventions. Never hand-edit a published archive; if contents are wrong, fix the DSL/build and build a new artifact.

## 11. Publish to a Staging Repository Before Release

Never run end-to-end PR tests by writing directly into an immutable release repository on every run.

~~~text
Producer PR / candidate commit
    |
    v
Producer verification PASS
    |
    v
Package stub JAR
    |
    v
Publish to isolated staging repository
    |
    v
Consumer smoke test resolves exact candidate
    |
    v
Compatibility tests PASS
    |
    v
Approval
    |
    v
Promote the same artifact to release repository
~~~

### Why Promote the Tested Artifact?

If the release job rebuilds from source after consumer tests, outputs can differ due to commits, dynamic dependencies, toolchains, contract DSL, timestamps/metadata, or caches/repositories.

Best practice is to **promote the exact candidate artifact by digest**, rather than rebuilding and relying solely on a matching version string.

| Attribute | Staging | Release |
|---|---|---|
| Target | PR/build candidate | Approved artifact |
| Version | Build ID/RC/unique candidate | Release version |
| Write access | Restricted CI pipeline | Protected release job |
| Overwrites | Discouraged per policy | Should be immutable |
| Consumers | Smoke/compatibility tests | Official consumer builds |
| Evidence | Test reports + digest | Promotion record + identical digest |

Never reuse a mutable version across parallel PRs. Candidates must carry unique IDs so jobs cannot overwrite one another's artifacts.

## 12. Consumer Resolution Regression: Download in a Clean Environment

A successful producer publish is not enough. Consumers must resolve the artifact in an **environment matching real CI**, not relying on local developer Maven caches.

### Stub Runner `REMOTE`

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/staging-stubs"
)
class CheckoutStubPipelineSmokeTest {

    @StubRunnerPort("inventory-producer")
    int inventoryPort;

    @Test
    void stubRunnerStartsInventoryStub() {
        // Use the consumer's HTTP client to call:
        // http://localhost:<inventoryPort>/api/inventory/SKU-101
        // Assert status and body per contract.
    }
}
~~~

This is a skeleton; adapt URLs, dependencies, client calls, and assertions to your project. `example.invalid` is a placeholder.

### What Does "Clean Environment" Mean?

- Empty local Maven repository or isolated cache per run.
- No manually copied old stub JARs.
- No dependency resolution from IDE caches.
- Read-only credentials pulled from the CI secret manager.
- Repository root pointing to the exact staging repository holding the candidate.
- Explicit pinned version, never `+` or `latest`.
- Downloaded artifact digest recorded.

You can create a temporary local Maven repository with `-Dmaven.repo.local=...` during diagnostics; Gradle maintains its own cache and needs matching isolation. Never wipe shared global caches indiscriminately; give regression jobs fresh cache namespaces.

Consumer smoke tests should assert:

- Stub Runner resolved the exact coordinates and classifier.
- The server started and exposed a port.
- Requests reached the right URL/method.
- Response status/headers/body match expectations.
- JSON types are accurate (boolean/number/string).
- Error cases return specific error codes when tested.
- The real consumer client parses and handles the response.

**Starting the test context cleanly is not enough** if the test never sends a request against the actual mapping.

## 13. Three Stub Loading Modes and Their Regression Meaning

| Mode | Source | What regression tests must prove |
|---|---|---|
| `LOCAL` | Local Maven repository | Stub was installed into the exact local repo used by the consumer process |
| `REMOTE` | Maven-compatible repository | Consumer downloads from the right repository with real credentials/permissions |
| `CLASSPATH` | Test runtime classpath | Stub artifact/resources actually exist on the classpath with valid layout |

### `LOCAL`

The producer can run `install` to place the artifact in local Maven. However, if producer and consumer run on **different runners**, the producer job's local repository will not appear in the consumer job automatically.

~~~text
Producer contractTest
    |
    v
Producer verifierStubsJar
    |
    v
Publish/install stubs to Maven local
    |
    v
Consumer test with stubsMode=LOCAL
~~~

Verify the actual local path because Maven settings can override `localRepository`. If the pipeline uses separate containers/jobs, use remote staging or pass artifacts with explicit provenance.

### `REMOTE`

`repositoryRoot` must point to the **Maven repository root**, not an application URL, a specific JAR file, or a version folder. Regression tests should use the same identity and network policies as consumer CI to catch 401/403 errors, TLS issues, proxies, and permission gaps.

### `CLASSPATH`

Having a stub JAR on the test runtime classpath is not the same as merely seeing a file in `build/libs` or `~/.m2`. Regression tests check test dependency resolution and archive layout. This mode fits projects configured to bundle stubs directly on the classpath.

Modes select the stub source; none of them waive the requirement that the stub hold valid mappings/definitions.

## 14. Verifying Stub Runner Ports and Request Matching

After downloading successfully, Stub Runner starts stub servers or configures messaging stubs. For HTTP, use the runtime port:

~~~java
@StubRunnerPort("inventory-producer")
int inventoryPort;
~~~

Never hardcode `localhost:8080` or `localhost:0` when Stub Runner assigns a dynamic port. Consumers must read the live port via `@StubRunnerPort` or `StubFinder`.

A smoke test might use Spring `RestClient` (Spring Framework 6.1+):

~~~java
import org.springframework.web.client.RestClient;

RestClient client = RestClient.builder()
    .baseUrl("http://localhost:" + inventoryPort)
    .build();

String body = client.get()
    .uri("/api/inventory/SKU-101")
    .header("Accept", "application/json")
    .retrieve()
    .body(String.class);
~~~

This is an illustrative snippet; full tests must assert status, parse JSON, and check fields/types.

### WireMock 404 Is Not Maven 404

- **Maven 404:** the resolver could not find the artifact file in the repository.
- **WireMock 404:** the server is running, yet the request matched no mapping (or a mapping intentionally returned a business 404).

When a consumer receives 404, log the full URL (host/port/path), method, query, headers, and body; inspect the unmatched request journal. Never immediately republish an artifact if the mapping is present and the consumer sent the wrong path.

If a test only asserts `status == 404`, a URL typo can make WireMock return an unmatched 404 and leave the test falsely green. For business not-found cases, also assert the error body/code such as `SKU_NOT_FOUND`.

## 15. Consumer Compatibility Testing Against the Exact Artifact

Meaningful regressions prove **the consumer actually ran against the newly published artifact**, not just any artifact sharing the name.

~~~text
Requested Stub Runner ID:
  com.example:inventory-producer:2.3.1:stubs:0

Resolved artifact:
  com.example:inventory-producer:2.3.1:stubs

Repository:
  staging-stubs

SHA-256:
  <digest>

Consumer:
  checkout source revision <consumer-sha>

Result:
  GET /api/inventory/SKU-101 -> 200
  JSON sku=SKU-101
  JSON available=true
  JSON quantity=8
~~~

Digest/SHA placeholders must be populated by the pipeline.

Consumer tests prove the artifact resolves, Stub Runner loads and starts it, the client sends the expected interaction, and the consumer handles simulated responses/messages.

Consumer tests **do not prove** the live producer is deployed at that revision, producer tests PASSED, transactions/concurrency hold outside the contract, or provenance exists unless recorded.

**Consumer tests do not replace producer verification.** Pipelines need both pieces of evidence linked by version, revision, and digest.

## 16. Negative Regression Tests: Prove Gates Catch Failures

A strong pipeline tests more than the happy path. It needs controlled failure scenarios confirming gates trip at the exact right stage.

| Negative scenario | Simulated change | Expected outcome |
|---|---|---|
| No stub JAR built | Skip stubs packaging task | Packaging gate fails |
| Wrong classifier | Publish main JAR without `stubs` | Artifact resolution fails |
| Wrong version | Consumer requests unpublished version | Resolution fails without fallback |
| Wrong group/artifact | ID points to different coordinates | Clear coordinate resolution failure |
| Wrong repository root | Point to app URL/different repo | Resolution fails |
| Missing mapping | JAR lacks required mapping | Archive/smoke gate fails |
| Missing body file | Mapping references absent file | Packaging/runtime gate fails |
| Request mismatch | Change path/method/header | WireMock unmatched request; test fails |
| Skipped tests | Producer tests do not run | Producer gate fails despite build success |
| Stale cached stub | Consumer resolves old version/digest | Digest/version assertion fails |
| Invalid credentials | Token lacks read permission | Download fails 401/403 |
| Mutable snapshot | Same coordinates serve different bytes | Provenance/digest check detects drift |

Run negative tests inside a test repository harness or isolated staging area. **Never intentionally corrupt the official release repository** to test failures.

If producer tests fail, the pipeline must not publish. If publishing fails, consumer tests must not fall back to cached stubs to produce a false PASS. If consumer tests fail, block release promotion per policy.


## 17. Contract Definitions, Producer Stubs, and Consumers in One Pipeline

An organization may maintain a shared contract repository:

~~~text
shared-contracts:
  com/example/inventory-producer/checkout-consumer/stockAvailable.groovy
~~~

The producer pulls definitions, generates tests, verifies its code, and publishes producer stubs. The consumer downloads the **producer stub artifact**.

~~~mermaid
sequenceDiagram
    participant CR as Contract repository
    participant P as Inventory producer CI
    participant R as Maven staging repository
    participant C as Checkout consumer CI
    participant Q as Release gate
    CR->>P: Contract definitions revision
    P->>P: Generate + run producer tests
    alt Producer PASS
        P->>P: Package classifier stubs
        P->>R: Publish candidate with digest
        C->>R: Resolve exact producer stubs
        C->>C: Stub Runner + consumer tests
        alt Consumer PASS
            C->>Q: Compatibility evidence
            Q->>R: Promote same artifact
        else Consumer FAIL
            C->>Q: Block and report
        end
    else Producer FAIL
        P->>Q: Block publication
    end
~~~

### Versions Do Not Need to Match

~~~text
Contract definitions: shared-contracts:1.6.0
Producer application: inventory-producer:2.3.1
Producer stubs:       inventory-producer:2.3.1:stubs
Consumer:             checkout-service:4.8.0
~~~

These differing versions are intentional. Record that producer stubs `2.3.1` were generated from contract definitions `1.6.0` at a specific revision after producer tests PASSED.

Consumers should log the **resolved producer stub version**, not merely Checkout's own version.

## 18. Regression Testing Artifact Repository Metadata

Downloading a JAR does not guarantee the publication is complete. Maven resolution may require valid POMs and type/version metadata.

### Minimum Checks

- Main POM published with exact group/artifact/version.
- Stub JAR attached with classifier `stubs`.
- Packaging/extension is JAR per project configuration.
- Release versions have stable metadata and paths.
- Snapshot versions include `maven-metadata.xml` and resolvers fetch exact timestamped snapshots.
- Repository checksums/signatures (if enabled by policy) exist and verify.
- Consumer read credentials can access both POM and JAR.
- No redirects to a login page returning HTTP 200 HTML instead of a JAR.
- Repository mirrors/proxies do not serve stale cached artifacts.

### Why Test Using the Consumer Identity?

Producer CI usually holds write access while consumer CI holds read-only access. A publish job can upload cleanly while the consumer identity still fails to read due to differing ACLs.

Run resolution regressions using the consumer's **read-only identity**. Never test downloads with a publish token and assume consumer permissions work.

### Byte Verification

Linux/macOS:

~~~bash
sha256sum inventory-producer-2.3.1-stubs.jar
~~~

PowerShell:

~~~powershell
Get-FileHash .\inventory-producer-2.3.1-stubs.jar -Algorithm SHA256
~~~

Compare the digest against the producer job's output/provenance. Hashing confirms **identical bytes**, though it does not by itself prove content validity or safety; archive inspection and test reports are still needed.

## 19. Git SCM vs. Maven Repository: Two Different Compatibility Pipelines

Some Spring Cloud Contract setups use Git SCM to store contracts/mappings, typically with `git://` URLs and layout:

~~~text
META-INF/
  com.example/
    inventory-producer/
      2.3.1/
        contracts/
        mappings/
~~~

This is not a Maven repository layout. Regression tests must verify the right resolver:

| Source | Evidence to check |
|---|---|
| Maven REMOTE | Repository root, coordinates, POM, classified JAR |
| Maven LOCAL | Local Maven path and installed artifact |
| CLASSPATH | Test runtime classpath and resource layout |
| Git SCM | URL/commit/ref, `META-INF/group/artifact/version`, `contracts`/`mappings` |

If a pipeline migrates from Git SCM to a Maven repository, test the transition: are mappings published as a producer stub JAR with new coordinates/classifier? Are consumer IDs/configs updated? You cannot simply swap URLs assuming both storage formats behave identically.

## 20. Upgrading the Spring Cloud Contract Plugin: Check Output and Semantics

Plugin upgrades can change:

- DSL parsing/validation.
- Generated test sources or test framework integration.
- Task/goal names and lifecycle bindings.
- Output directories and stub packaging.
- Mapping/fixture layouts.
- Default values or matcher behavior.
- Verifier/Stub Runner dependency graphs.
- Compatibility with Spring Boot/Cloud/JDK.

### Safe Upgrade Strategy

1. Lock the current toolchain as the baseline.
2. Save contract revision, producer test counts/reports, stub JAR entries, and consumer test results.
3. Work on a dedicated upgrade branch.
4. Upgrade only one major layer at a time when possible.
5. Re-run producer verification.
6. Compare generated tests and mapping semantics.
7. Publish to staging under a distinct version/digest.
8. Run consumer tests against the staging artifact in a clean environment.
9. Run a minimal compatibility matrix.
10. Promote only after diff review and verified evidence.

### Do Not Compare Generated Sources Only by Line Count

A newer plugin may alter imports, whitespace, generated class names, or JSON key ordering without changing behavior. Conversely, a tiny change in one matcher can break consumer matching despite a minimal file diff.

Prioritize comparing:

- Request method/path/query/header/body matchers.
- Response status/headers/body.
- Regex/type/date/JSONPath matchers.
- Message label/destination/headers/payload.
- Producer test counts and assertions.
- Consumer runtime behavior.

If output bytes changed while semantics held steady, document the reason and update the baseline after review; never ignore all diffs automatically.

## 21. Upgrading Maven, Gradle, JDK, and Repositories

### Maven Upgrade

- Verify plugin compatibility with the Maven version.
- Inspect effective POM, lifecycle ordering, and attached artifacts.
- Check Surefire/Failsafe/JUnit test discovery.
- Check deploy plugin and repository credentials.
- Run resolution tests from an independent consumer project.

### Gradle Upgrade

- Verify Spring Cloud Contract plugin compatibility.
- Check task configurations and configuration cache.
- Check task inputs/outputs so build caches do not serve stale outputs.
- Check `maven-publish` classifier/artifact attachment.
- Check multi-project publication coordinates.
- Verify the actual publish task and remote repository contents.

### JDK Upgrade

- Check compiler and test runtime toolchains.
- Check Groovy/Gradle/Maven/plugin compatibility.
- Check encoding, timezone, and locale if fixtures depend on them.
- Check generated test compilation and runtime behavior.
- Check Docker/Testcontainers images for matching architecture/runtime needs.

### Repository Manager Upgrade

- Maven metadata and snapshot resolution.
- Release immutability/overwrite policies.
- Classifier artifact retention.
- Checksum/signature behavior.
- Authentication/authorization and token rotation.
- TLS certificates/truststores/proxies.
- Cache invalidation and cross-node replication.
- Downloads from the consumer CI's region/network.

**Never upgrade everything at once** without a regression baseline. If the build fails, you will struggle to tell whether the culprit is the plugin, toolchain, repository, or source code.

## 22. Caching: Optimizing Speed Without Losing Correctness

### Local Maven Repository

- Never share local repositories between untrusted PR jobs and release jobs.
- For clean-resolution regressions, use a dedicated local repo or fresh cache key.
- Never rely on manually installed artifacts from a developer's laptop.
- For SNAPSHOTs, verify metadata/update policies and digests.
- Pin immutable release coordinates.

### Gradle Dependency/Build Cache

- Dependency cache and task output cache are two distinct things.
- Task output caching is safe only when task inputs/outputs are declared accurately.
- If contract JARs/paths or plugin config are omitted from inputs, tasks may reuse stale generated outputs.
- Isolate cache namespaces by toolchain, branch, and trust level.
- Never let untrusted PRs populate caches consumed by protected release jobs.

### A Cache Diagnostic Test

~~~bash
./gradlew :inventory-producer:contractTest --rerun-tasks --no-build-cache
~~~

This forces re-execution while bypassing the build cache for that invocation. It **does not fix** broken input declarations long-term and does not resolve a Maven repository serving stale artifacts.

For Maven, use a temporary local repo or clean workspace for resolution regressions instead of wiping every developer's global cache.

## 23. Versioning and Provenance: Linking Producer Verification to Consumer Downloads

A minimal regression report:

~~~text
Contract source:
  repository: <contract-repository>
  revision: <contract-sha>
  artifact: com.example.contracts:inventory-contracts:1.6.0
  digest: <contract-digest>

Producer:
  repository: <producer-repository>
  revision: <producer-sha>
  toolchain: <jdk/maven-or-gradle/scc-versions>
  contract tests: 12 executed / 12 passed

Stub artifact:
  coordinate: com.example:inventory-producer:2.3.1:stubs
  repository: <staging-repository>
  digest: <stub-sha256>

Consumer:
  revision: <consumer-sha>
  resolved coordinate: com.example:inventory-producer:2.3.1:stubs
  downloaded digest: <downloaded-sha256>
  Stub Runner startup: PASS
  compatibility tests: 6 executed / 6 passed
~~~

Values in `<...>` are placeholders that CI must populate from real logs/provenance.

### Relationships to Preserve

- The contract source revision is what producer verification actually ran against.
- The producer source revision is the code generated tests exercised.
- The stub artifact came from that exact build.
- The consumer download digest matches the published candidate digest.
- The consumer report records the exact resolved coordinates and digest.

Never record only a version string; two builds under a mutable version can carry different bytes.

## 24. Separating Smoke Tests, Compatibility Tests, and Full Regressions

| Level | When to run | Contents |
|---|---|---|
| **Static/fast validation** | Every PR | Diffs, DSL discovery, build config |
| **Producer verification** | Producer PRs / protected branches | Generated tests + implementation |
| **Packaging smoke** | After producer verification | Classifier, JAR entries, metadata |
| **Publish/resolve smoke** | Pre-merge/release or staging | Upload, download with consumer identity |
| **Consumer compatibility** | New stub candidate | Stub Runner + client/handler tests |
| **Full toolchain matrix** | Scheduled or upgrade PRs | JDK/build/plugin/repository matrix |
| **Repository failover** | Periodic / infra changes | Mirrors, auth, replication, caches |

Select tests by risk:

- DSL edits: producer tests + consumer compatibility.
- Publication/classifier edits: packaging + remote resolution + Stub Runner.
- Gradle/Maven upgrade: producer lifecycle + publication + clean consumer resolution.
- Stub Runner/WireMock upgrade: startup + mapping behavior.
- Repository changes: auth, metadata, snapshots, digests, clean downloads.
- JDK/Spring Boot/Cloud upgrade: full toolchain subset per supported matrix.

Never eliminate end-to-end tests solely due to runtime; schedule them at the right pipeline tier, such as nightly or pre-release.

## 25. Reference CI Workflow Across Two Repositories

~~~mermaid
flowchart TD
    A["Producer PR / approved commit"] --> B["Pinned toolchain"]
    B --> C["Generate + run producer tests"]
    C --> D{"PASS and count valid?"}
    D -->|No| X["Block publish"]
    D -->|Yes| E["Package :stubs JAR"]
    E --> F["Inspect classifier, mappings, digest"]
    F --> G["Publish unique candidate to staging"]
    G --> H["Clean consumer job"]
    H --> I["Resolve exact candidate"]
    I --> J["Stub Runner + consumer tests"]
    J --> K{"PASS?"}
    K -->|No| X
    K -->|Yes| L["Store provenance"]
    L --> M["Protected approval"]
    M --> N["Promote same artifact"]
~~~

### Illustrative Producer Job

~~~yaml
name: Producer contract pipeline

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify-and-package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: gradle

      - name: Verify producer contracts
        run: ./gradlew :inventory-producer:contractTest

      - name: Package stub artifact
        run: ./gradlew :inventory-producer:verifierStubsJar

      - name: Inspect stub archive
        run: |
          jar tf inventory-producer/build/libs/inventory-producer-2.3.0-stubs.jar
~~~

This is an **illustrative workflow**: actions should be pinned by SHA per policy, and JDK, plugins, versions, task names, paths, and outputs must match real configuration. The publish step is omitted here because credentials/permissions belong in a protected post-verification job.

### Illustrative Consumer Job

~~~yaml
name: Consumer stub compatibility

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  consume-candidate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Run consumer tests against staging stub
        run: ./mvnw -B -ntp clean verify
~~~

The consumer project must configure `StubRunnerProperties.StubsMode.REMOTE`, the staging `repositoryRoot`, and the candidate version/digest. `workflow_dispatch` is only an example trigger; it does not pass artifacts between workflows automatically.

Both jobs must exchange candidate coordinates/digests via artifact metadata, workflow outputs, or trusted release records. Never guess versions from branch names.

## 26. Promotion: Do Not Rebuild After Compatibility PASSES

Suppose candidate:

~~~text
com.example:inventory-producer:2.3.1-rc.4:stubs
SHA-256 = abc...
~~~

Consumer compatibility tests PASSED on those exact bytes. The release job should **promote/copy the exact tested artifact** by digest instead of rebuilding from source and assuming identical output because the version matches.

### Promotion Record

~~~text
Candidate:
  staging coordinate: com.example:inventory-producer:2.3.1-rc.4:stubs
  digest: <digest-A>

Validation:
  producer tests: PASS
  archive inspection: PASS
  consumer tests: PASS

Release:
  release coordinate: com.example:inventory-producer:2.3.1:stubs
  promoted digest: <digest-A>
  approval: <release-approval>
~~~

If release policy requires renaming the version coordinate on promotion, the repository can copy the exact bytes under the new release coordinate. The payload digest must remain identical; auxiliary POM/metadata updates per policy must be recorded separately.

Never promote if producer reports do not belong to the candidate build or consumer tests downloaded an artifact with a different digest.

## 27. Compatibility Regression Across Multiple Consumers

A producer often serves multiple consumers:

~~~text
inventory-producer
  ├── checkout-consumer
  ├── reporting-consumer
  └── warehouse-consumer
~~~

A shared stub JAR may hold mappings for multiple consumers, or the producer may publish stubs-per-consumer depending on configuration. Regressions must test the **exact consumer context** and selected mappings.

| Consumer | Scenarios to verify |
|---|---|
| Checkout | GET stock, POST reservation, insufficient stock error |
| Reporting | Inventory snapshots and statistical fields |
| Warehouse | Stock changed events and message headers |

If the producer changes a response field, one consumer may PASS while another FAILS. Testing only Checkout proves nothing about compatibility with Reporting or Warehouse.

- Critical consumers: run compatibility tests on every producer release candidate.
- Low-churn consumers: run on schedule or when relevant contract paths change.
- Deprecated consumers: still test while policy commits to supporting them.
- New consumers: validate against candidate stubs before producer release.

With stubs-per-consumer, regressions should verify each consumer's dedicated artifact/filter. A JAR containing Checkout mappings does not prove Reporting mappings were published.

## 28. Regression Testing for Breaking Changes

Old response:

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

New response:

~~~json
{"sku":"SKU-101","availability":"IN_STOCK","units":8}
~~~

New generated producer tests may PASS if both DSL and code changed together. Yet legacy consumers still read `available` and `quantity`.

Regressions must:

1. Run pinned consumer tests against the **new stub version** to expose breaking changes.
2. Keep compatibility tests against legacy stubs if the producer commits to supporting old behavior.
3. Review schema/type/status/header/message changes.
4. Maintain migration, versioning, and deprecation plans.
5. Promote only when required consumers pass or an approved release decision authorizes it.

**Contract tests do not automatically know every deployed consumer.** Maintain a dependency map or consumer registry governed by the organization.

## 29. Cache and Snapshot Regressions

Symptom:

~~~text
Producer published 2.3.1-SNAPSHOT with new mapping
Consumer job reports PASS
But downloaded JAR still has old mapping
~~~

Possible culprits include Maven metadata/update policies, proxy caches, local repos, or Gradle dependency caches.

How to check:

- Record resolved artifact path, version, and digest.
- Compare checksums with the producer candidate.
- Inspect Maven `maven-metadata.xml` and timestamped snapshots.
- Use a fresh local repo/cache namespace for regression runs.
- Never use dynamic versions on release gates.
- Check which bytes mirrors/proxies are serving.

Release rules:

- Use immutable release versions for verified stubs.
- Use unique build IDs/RCs for candidates.
- Never overwrite release coordinates.
- If an artifact needs fixes, bump the version or roll back/reissue per policy.
- Retain digests of both producer-verified and consumer-tested artifacts.

**Never treat cache clearing as a permanent fix** while versions stay mutable or publications lack provenance.

## 30. Negative Regression Tests for Repository Access and Metadata

A regression suite should test controlled failures in a staging/test repository:

| Case | Simulated setup | Expected result |
|---|---|---|
| Invalid read token | Consumer uses expired token | Download fails 401 |
| Insufficient permissions | Token only reads a different repository | Download fails 403 or policy error |
| Missing artifact | Unpublished version ID | Clear coordinate resolution failure |
| Missing classifier | Only main JAR published | Stub resolution fails |
| POM present, JAR missing | Metadata uploaded without payload | Fails when downloading JAR |
| Empty JAR | JAR published with zero mappings | Archive/smoke validation fails |
| Missing mapping | Required endpoint omitted | Mapping assertion fails |
| Digest mismatch | Candidate bytes altered | Provenance check fails |
| Wrong TLS CA | Runner lacks trusted CA | Clear TLS download failure |
| Misconfigured mirror | Repo root differs from staging | Repository assertion fails |

Run negative tests in a test repository harness or isolated staging area. **Never intentionally corrupt the official release repository** to test failures.

## 31. Observability and Storing Pipeline Evidence

A useful report connects producer and consumer:

~~~text
Run:
  pipeline-id: <pipeline-id>
  started-at: <timestamp>

Toolchain:
  JDK: <jdk-version>
  Maven/Gradle: <build-tool-version>
  SCC plugin: <plugin-version>
  Stub Runner: <stub-runner-version>

Contract:
  repository/revision: <contract-source-sha>
  coordinates: <contract-group:artifact:version>
  digest: <contract-digest>
  discovered contracts: <count>

Producer:
  source revision: <producer-sha>
  generated tests: <executed>/<passed>/<failed>/<skipped>
  stub task: <task-or-goal>
  artifact coordinate: <group:artifact:version:stubs>
  published repository: <staging-root>
  artifact digest: <stub-digest>

Consumer:
  source revision: <consumer-sha>
  stubsMode: <LOCAL|REMOTE|CLASSPATH>
  resolved coordinate: <group:artifact:version:stubs>
  downloaded digest: <downloaded-digest>
  Stub Runner startup: <PASS/FAIL>
  consumer tests: <executed>/<passed>/<failed>

Decision:
  <PROMOTE/BLOCK/INVESTIGATE>
~~~

Values inside `<...>` are placeholders. Never print credentials, tokens, or URLs with embedded passwords into logs.

Metrics to track:

- Rate of producer builds with 0 generated contract tests.
- Rate of builds where publish succeeds yet consumer resolution fails.
- Rate of consumer tests using an older stub version than the candidate.
- Rate of artifact digest mismatches.
- Number of releases blocked by compatibility tests.
- Lead time from producer candidate publish to consumer verification.
- Flaky test / retry rates classified by root cause.

Metrics do not replace tests, yet they expose recurring pipeline regressions after tooling upgrades.

## 32. Symptom-Based Troubleshooting

| Symptom | Possible cause | What to check |
|---|---|---|
| Producer build green, no stub JAR | Generation/packaging task didn't run | Task graph, output directory |
| Main JAR published, stubs JAR missing | Classifier not attached | POM/publication/artifact list |
| Local consumer PASSES, remote consumer FAILS | Not published or wrong ACL/repository | Repository root, read identity |
| Consumer resolves old version | Pin/cache/snapshot metadata | Resolved coordinate + digest |
| JAR downloads yet misses mapping | Wrong contracts path/filter/packaging | Archive listing |
| Stub Runner context fails | Dependency/config/server startup | Startup logs, port conflicts |
| Context PASSES yet HTTP 404 | Request mismatches mapping | Unmatched request journal |
| Consumer PASSES with old stub | Candidate not passed to consumer job | Pipeline output coordinates |
| JDK upgrade breaks generated test compile | Plugin/test framework incompatibility | Compatibility matrix/dependency tree |
| Gradle upgrade skips `contractTest` | Task/source set/plugin change | `tasks --all`, plugin config |
| Maven upgrade fails to attach stub | Lifecycle/plugin execution changed | Effective POM, deploy logs |
| Repository upgrade returns HTML | Proxy/login/SSO redirect | `Content-Type`, response status |
| Multi-module publishes wrong coordinates | Subproject group/artifact/version override | Publication metadata |
| Stale snapshot mappings | Metadata/cache | Clean repo, timestamped snapshot, digest |
| Another consumer misses mappings | Stubs-per-consumer filter | Artifact entries per consumer |

### Diagnostic Procedure

1. Identify run ID and producer/consumer source revisions.
2. Confirm producer tests actually executed and PASSED.
3. Inspect stub JAR outputs and archive entries.
4. Check publication coordinates and repository responses.
5. Re-download the artifact using the consumer identity into a clean environment.
6. Compare the digest with the producer candidate.
7. Confirm Stub Runner startup and port assignment.
8. Match actual requests against mappings.
9. Only then conclude whether the issue lies in the contract, producer, consumer, or infrastructure.

Never edit consumer requests when the artifact doesn't exist yet; never republish artifacts when the error is merely a URL/port mismatch.

## 33. Practice Exercise 1 — Publish Succeeds but Classifier Is Missing

Producer CI log:

~~~text
BUILD SUCCESS
Uploaded:
  inventory-producer-2.5.0.pom
  inventory-producer-2.5.0.jar
~~~

Consumer ID:

~~~text
com.example:inventory-producer:2.5.0:stubs:0
~~~

The consumer fails to resolve the artifact.

**Q1. Primary cause?**

Publication included only the main JAR; the `stubs` classifier was never attached/uploaded.

**Q2. Where to inspect?**

- Maven: plugin stub generation/attachment, effective POM, and deploy logs.
- Gradle: `verifierStubsJar` output, publication artifact list, and publish task.
- Registry: does `inventory-producer-2.5.0-stubs.jar` actually exist?

**Q3. Should you drop the classifier from the consumer ID?**

No. The resolver might download the main application artifact instead of stub mappings. Fix producer publication and re-run consumer regression tests.

## 34. Practice Exercise 2 — Consumer PASSES Yet Downloads Old Stub

Producer candidate 2.5.1 adds a new mapping `GET /api/inventory/SKU-202`. The consumer job reports PASS, yet resolution logs show:

~~~text
Resolved:
  inventory-producer:2.5.0:stubs
~~~

**Q1. Did the consumer test candidate 2.5.1?**

No. The consumer only tested stub 2.5.0.

**Q2. Possible causes?**

Candidate coordinates were not passed to the consumer job, the ID still pins 2.5.0, cache/version alias interference, or stale pipeline outputs.

**Q3. How to fix?**

Use exact coordinates `2.5.1`, download from staging, verify the digest, and assert version/digest in the report. Never switch to `latest`.

## 35. Practice Exercise 3 — Right JAR Yet Stub Runner Returns 404

- Artifact resolution: PASS.
- Archive holds mapping `GET /api/inventory/SKU-101`.
- Stub Runner binds port 14321.
- Consumer sends `GET /inventory/SKU-101`.
- WireMock returns 404.

**Q1. Is the publish/download pipeline broken?**

Publish/download/startup already proved PASS; the request missed the mapping because the `/api` prefix was omitted.

**Q2. Where to fix?**

If the contract locks `/api/inventory/...`, fix the consumer base path. If the contract genuinely changed paths, update the DSL and re-run producer/consumer verification.

**Q3. Why is the unmatched request journal needed?**

It shows exactly which requests failed to match, separating WireMock's 404 from a business 404 returned by a matched mapping.

## 36. Practice Exercise 4 — Upgrading Gradle and the Spring Cloud Contract Plugin

After upgrading:

~~~text
Before:
  contractTest executed: 12
  stubs JAR published: yes
  consumer remote smoke: PASS

After:
  build SUCCESS
  contractTest executed: 0
  application JAR published: yes
  stubs JAR: missing
~~~

**Q1. Can this upgrade be accepted?**

No. A green build with zero producer tests and a missing stub artifact is a critical regression.

**Q2. What needs inspection?**

- Plugin version and Gradle compatibility.
- Task graph `tasks --all`.
- Project path, source set, and contract DSL directory.
- `verifierStubsJar` task and outputs.
- Whether publication attaches the right artifact/task.
- Test reports and CI task dependencies.

**Q3. Which quality gates catch this failure?**

Require generated producer test count > 0 (when the module owns contracts), passing tests, stub artifact existence, mappings present in archive, consumer remote resolution, and passing Stub Runner smoke tests.

## 37. Stub Publish and Download Pipeline Regression Checklist

### Producer Contract Verification

- [ ] Contract source revision/version is pinned and recorded.
- [ ] JDK/Maven/Gradle/SCC plugin toolchain is compatible.
- [ ] The right producer module/task executed.
- [ ] Discovered contract count matches expectations—no unexpected 0 contracts.
- [ ] Generated producer tests compiled and executed.
- [ ] Test reports list executed/passed/failed/skipped counts.
- [ ] Producer tests PASSED prior to publishing.
- [ ] No `skipTests` or unauthorized task exclusions active.

### Packaging and Publication

- [ ] Stub JAR was built from the exact producer/contract revision.
- [ ] `stubs` classifier is attached.
- [ ] JAR contains required mappings/message definitions.
- [ ] Fixtures/body files are packaged.
- [ ] Group/artifact/version/extension/classifier are accurate.
- [ ] POM and repository metadata are valid.
- [ ] Artifact published to the right staging/repository.
- [ ] Consumer read identity can download the artifact.
- [ ] Candidate version is unique; releases are immutable.
- [ ] Digest/provenance are archived.

### Consumer Resolution and Runtime

- [ ] Consumer ID matches publication coordinates.
- [ ] `stubsMode` matches LOCAL/REMOTE/CLASSPATH as intended.
- [ ] Remote repository root is accurate; credentials are read-only.
- [ ] Consumer tests run in a clean environment/isolated cache.
- [ ] Downloaded artifact digest matches the producer candidate.
- [ ] Stub Runner loads mappings and opens port/label.
- [ ] Client uses the runtime port, not a hardcoded port.
- [ ] HTTP requests/message triggers match mappings.
- [ ] Consumer assertions check status/body/types/error codes.
- [ ] Never confuse WireMock unmatched 404 with business 404.
- [ ] Consumer tests actually executed against the new candidate version.

### Toolchain Compatibility and Release

- [ ] Supported baseline and upgrade candidate are explicitly documented.
- [ ] Maven/Gradle wrapper, JDK, and Spring Boot/Cloud/SCC versions are pinned.
- [ ] Upgrade tests compare semantics of generated tests and mappings.
- [ ] Caching never causes consumers to run old stubs.
- [ ] Negative tests confirm gates fail when artifacts/classifiers/mappings are missing.
- [ ] Compatibility across critical consumer groups has been tested.
- [ ] Artifact promotion reuses the exact tested bytes without arbitrary rebuilds.
- [ ] Release records link producer SHA, contract SHA, consumer SHA, and stub digest.
- [ ] Clear owners exist for flaky tests and artifact resolution failures.

## 38. Key Takeaways and References

**Regression testing the stub publish and download pipeline** must verify the entire chain: producer discovers contracts → generates/runs tests → packages `stubs` classifier → publishes → consumer resolves → Stub Runner starts → consumer compatibility tests pass.

Distinguish three artifact types: **contract definitions JAR**, **producer application JAR**, and **producer stubs JAR**. Publishing the main JAR does not prove the `stubs` classifier uploaded; green consumer tests against stale cached stubs do not prove the new candidate is compatible.

When upgrading Maven/Gradle/JDK/Spring Cloud Contract plugins or repository managers, run an appropriate compatibility matrix, inspect archives/metadata, and download artifacts in a clean consumer environment. Pin versions, digests, and provenance; promote the **exact verified artifact**.

### References

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): DSL, verifier, stub generation, and Stub Runner.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): Gradle plugin, `contractTest`, and `verifierStubsJar`.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): Maven plugin, lifecycle, and stub artifacts.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): configuring Stub Runner in consumer tests.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): resolving and starting stub artifacts.
- [Spring Cloud Contract — Git as Storage](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-use-git-as-storage.html): storing contracts/mappings via Git SCM.
- [Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): coordinates, local/remote repositories, and metadata.
- [Maven Dependency Plugin — dependency:get](https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html): resolving artifacts/classifiers.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): Maven-compatible publications from Gradle.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): dependency caching and resolution.
- [SLSA — Supply-chain Levels for Software Artifacts](https://slsa.dev/): provenance and artifact integrity.

**Practical conclusion:** whenever the pipeline reports PASS, prove the producer verified the contracts, the stub artifact with the right classifier/version was published, the consumer downloaded the exact digest, and Stub Runner executed the corresponding mappings. Only then do you have true regression proof for the stub publish and download chain.
