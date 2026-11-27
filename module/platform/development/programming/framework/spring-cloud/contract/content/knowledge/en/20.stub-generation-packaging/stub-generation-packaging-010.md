# Preventing Stub Publication When Producer Tests Fail

## Learning objectives

In **Spring Cloud Contract**, a producer defines HTTP or messaging behavior using **Groovy/YAML DSL**. From that contract, the tooling generates **generated producer tests** to verify the code serving the real API and generates **stubs** so consumers can run tests with **Stub Runner**. In multi-service systems, placing these steps in the right order inside **CI** is part of contract test design, not merely build configuration.

This lesson belongs to the **Stub Generation and Packaging** chapter, focusing on the core rule:

> **Never publish a stub as a producer-verified contract unless its corresponding generated producer tests ran and passed.**

After this lesson, you will be able to:

- Distinguish **generating stubs**, **packaging stubs**, **installing stubs into a local repository**, and **publishing stubs to an artifact repository**.
- Explain why an existing `*-stubs.jar` file **does not prove** the producer satisfies the contract.
- Design **quality gates** based on generated producer test outcomes, test discovery, and revision consistency.
- Configure release workflows with **Maven**, **Gradle**, and CI without accidentally skipping tests.
- Separate **CI candidate stubs used for trial checks** from **published stubs released for consumers**.
- Analyze failure modes: red tests, 0 generated tests, `skipTests`, stale artifacts, mutable versions, and standalone publish jobs.
- Bind producer test results, stub artifacts, and consumer tests to **the exact same commit/version** to catch incompatible API changes early.

## 1. Why generating a stub does not mean verification happened

Suppose **Inventory Service** is the producer and **Checkout Service** is the consumer. Checkout sends:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

The contract agreed by both teams:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

The producer team writes the DSL for this scenario. When running the proper build steps, Spring Cloud Contract can generate:

1. **Producer contract test:** calls the Inventory implementation with the described request and asserts the response.
2. **HTTP stub mapping:** describes requests the stub accepts and the simulated response it returns.
3. **Stub artifact:** packages mappings/contracts with metadata so Stub Runner can locate and run them.

Suppose Inventory code has a bug and returns:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": "8"
}
~~~

In this response, `quantity` is a **string** instead of a **number**. A consumer deserializing into a numeric field may crash or exhibit unexpected behavior.

The danger is that **stubs generated from the contract still return `quantity: 8`**, because stubs reflect the contract description rather than the real producer code's response. If the team publishes that stub without running passing producer tests, Checkout can:

- Run tests with Stub Runner and **pass** because the stub returns numeric `8`.
- Deploy against the real producer and **fail** because the producer returns string `"8"`.

This is an example of **a stub describing a promise without proving the promise was kept**.

### Distinguishing sources of evidence

| Component | What does it prove? | What does it NOT prove by itself? |
|---|---|---|
| Groovy/YAML contract | Agreed behavior between producer and consumer | Real producer code works properly |
| Generated producer test exists | Generator produced tests from DSL | Tests ran and passed |
| Generated producer test **PASSES** | Producer satisfies executed contract scenarios in test env | All live cases or all legacy consumers remain compatible |
| Stub mapping generated | Simulation config exists for Stub Runner | Producer implemented it properly |
| `*-stubs.jar` created | Stubs were packaged | Quality gate was satisfied |
| Consumer test against stub **PASSES** | Consumer handles the running stub | Stub matches producer revision or real producer works |
| Artifact publish succeeds | Consumers can fetch the artifact from repository | Publish workflow followed quality controls |

**Conclusion:** artifact file status and test execution status must be treated as **two independent pieces of evidence**. Only a quality gate decides whether an artifact may be released to consumers as a trusted version.

## 2. Four distinct actions often lumped together as "publish stub"

These terms carry different meanings:

| Action | Typical output | Scope of impact |
|---|---|---|
| **Generate** | Generates WireMock mappings, contract definitions, and test code | Temporary output in build workspace |
| **Package** | Builds `inventory-producer-1.0.0-stubs.jar` | Artifact exists in workspace; not necessarily published |
| **Install local** | Installs artifact into local Maven repository (`~/.m2/repository`) | Tests on that machine/runner can resolve the artifact |
| **Deploy/publish remote** | Uploads artifact to Nexus/Artifactory/Maven repository | Other consumers can download the artifact if authorized |

In Spring Cloud Contract, stubs are usually published as a Maven artifact with the **`stubs` classifier** alongside the normal application artifact.

Illustrative coordinates:

~~~text
groupId    = com.example
artifactId = inventory-producer
version    = 1.0.0
classifier = stubs
type       = jar

Maven notation:
com.example:inventory-producer:1.0.0:stubs
~~~

These coordinates help Stub Runner find the stub. They are not test evidence; an artifact with the exact same layout can be produced from a broken contract or a build that skipped generated tests.

### File existence differs from a published artifact

~~~text
Producer workspace
  ├── generated contract tests
  ├── reports/ test results
  ├── generated stubs / mappings
  └── inventory-producer-1.0.0-stubs.jar
          |
          | Publish allowed only when quality gate PASSES
          v
Artifact repository
  └── com/example/inventory-producer/1.0.0/
        inventory-producer-1.0.0-stubs.jar
~~~

Paths, task names, and directories can vary by Maven/Gradle plugin and build setup. The invariant to keep is **never infer permission to publish merely because a JAR file appeared**.

## 3. Minimum quality gate: necessary and sufficient conditions to publish

A recommended policy can be expressed as:

~~~text
CAN_PUBLISH_STUB =
    CONTRACT_FILES_DISCOVERED
    AND GENERATED_PRODUCER_TESTS_EXECUTED
    AND GENERATED_PRODUCER_TESTS_PASSED
    AND REQUIRED_BUILD_CHECKS_PASSED
    AND STUB_BUILT_FROM_SAME_REVISION
    AND PUBLICATION_AUTHORIZED
~~~

An organization may add **consumer compatibility tests passed** or release approvals. Yet **producer tests passing** must never be waived.

| Gate | What it checks | If failed |
|---|---|---|
| **G1 — Contract discovery** | Plugin finds DSL in the right module plus required fixtures | Block publish |
| **G2 — Test generation** | Generated tests are created and compiled for current code version | Block publish |
| **G3 — Test execution** | Tests actually run; not accidentally skipped/disabled/filtered | Block publish |
| **G4 — Assertions pass** | Producer tests verify status/headers/body or message payload/headers | Block publish |
| **G5 — Required build checks pass** | Compilation, mandatory tests, and project checks | Block publish |
| **G6 — Artifact consistency** | Stub matches contracts, same revision, and verified version | Block publish |
| **G7 — Release authorization** | Valid branch/tag/approval/credentials | Block publish |

**G1 and G3 are especially critical:** a build reporting success when zero generated tests were discovered can be a false positive. Likewise, builds using `-DskipTests` still emit outputs without providing proof that producer tests passed.

### Never equate "all tests green" with "producer contract tests green"

A repository can have 500 passing unit tests while **running zero generated contract tests**. If a build configuration excludes the Spring Cloud Contract test source set, the job's green status proves nothing about the interface.

Cross-check generated test names, test runner reports, executed test counts, and targeted modules. Until confirmed, the honest state is **UNVERIFIED**, not **PASSED**.

## 4. Sample HTTP contract for the gate

A Groovy contract file on the producer, such as `src/test/resources/contracts/inventory/stockAvailable.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'SKU-101 is in stock and quantity is a number'

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

Equivalent YAML DSL alternative:

~~~yaml
description: 'SKU-101 is in stock and quantity is a number'
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

**Do not create both versions in the same build for one scenario**; the examples illustrate that Spring Cloud Contract supports both DSLs.

A valid generated producer test must perform the equivalent of:

~~~text
WHEN:
  GET /api/inventory/SKU-101
  Accept: application/json

THEN:
  HTTP status == 200
  Content-Type indicates application/json
  JSON $.sku == "SKU-101"
  JSON $.available == true
  JSON $.quantity == 8 (number)
~~~

This is **pseudocode**, not verbatim Java output from a specific generator version. Open the **actual generated test** to verify assertions preserve data types, especially for numbers, booleans, nulls, and dynamic matchers.

### Base tests must execute real producer code

The producer can configure `baseClassForTests` to set up:

- The real controller backed by a fake service with fixture `SKU-101`.
- A Spring application context with a dedicated test/seeded database.
- The application over real HTTP if `EXPLICIT` test mode is chosen.

Regardless of approach, tests must send requests into **the producer code under verification**. If the base class replaces the entire endpoint with a mock returning the exact expected JSON, a green result proves nothing about Inventory's real implementation.

If the generated test fails because the producer returns `"quantity":"8"`, that is a signal to **block publishing**, not an excuse to change the contract to a string to match the buggy implementation without consulting consumers.

## 5. Distinguishing producer and consumer checks

~~~mermaid
sequenceDiagram
    participant Dev as Pull request
    participant DSL as Contract DSL
    participant P as Producer test
    participant Jar as Candidate stubs.jar
    participant C as Consumer test
    participant Repo as Remote repository
    Dev->>DSL: Change API/message contract
    DSL->>P: Generate tests, run real producer
    alt Producer test fails
        P-->>Dev: Block publish
    else Producer test passes
        DSL->>Jar: Build stub from same revision
        Jar->>C: Stub Runner uses candidate
        alt Consumer test fails and policy requires pass
            C-->>Dev: Block publish, assess compatibility
        else Required gates pass
            Jar->>Repo: Publish verified version
        end
    end
~~~

**Why do consumer tests normally follow producer tests?** Because consumers need a trustworthy candidate stub from the producer. In CI, you can build a candidate stub earlier for internal trial checks, yet **never advertise it as a valid published artifact** when producer tests have not passed.

Note on actual build order: some plugins generate or package stubs in different phases/tasks. **Physical file-generation order does not dictate trust order.** The publish gate is the boundary that must not be crossed.

## 6. Maven: using the lifecycle as a safety boundary

In Maven, the standard lifecycle runs phases roughly in this order:

~~~text
validate
   ↓
compile
   ↓
test
   ↓
package
   ↓
verify
   ↓
install
   ↓
deploy
~~~

`mvn verify` runs required phases through `verify`. `mvn install` and `mvn deploy` also run preceding phases **when invoked via the standard lifecycle**. Therefore, a publish command executing the full lifecycle without skipping tests is generally safer than invoking a direct artifact-upload goal.

### Illustrative plugin configuration

In the **producer's** POM:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
      <extensions>true</extensions>
      <configuration>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>
          com.example.inventory.contract.InventoryContractBase
        </baseClassForTests>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

This is an illustrative snippet only. `REPLACE_WITH_COMPATIBLE_VERSION` must be replaced with a Spring Cloud Contract version compatible with your project's Spring Boot/Spring Cloud stack. Dependencies such as `spring-cloud-starter-contract-verifier`, starter web, `spring-boot-starter-test`, and repository version management must also be properly configured.

### Verification commands before publishing

~~~bash
# Verify producer and lifecycle-bound checks.
./mvnw -B -ntp clean verify

# Execute only during an authorized release step,
# without skipping tests and on the exact source revision to release.
./mvnw -B -ntp clean deploy
~~~

The second command re-runs verification phases prior to deploying per lifecycle. In CI, you may choose **a single `clean deploy` command inside a gated release job**, or split verify/release jobs where **the release job re-verifies or publishes only the exact immutable artifact that passed the gate**.

**Never default to:**

~~~bash
# ANTI-PATTERN example only, do not use for releases.
./mvnw deploy -DskipTests
~~~

`-DskipTests` skips test execution; `-Dmaven.test.skip=true` can skip compiling tests too. In addition, some plugins have their own skip flags. Those modes let artifacts get created with **zero evidence that producer tests ran**.

### The Maven lifecycle is not magic

If a build configures:

- Excluding generated test sources.
- Binding generated tests to an inactive profile.
- Setting `maven.test.failure.ignore=true`.
- Running `deploy:deploy-file` or `install:install-file` directly on an existing JAR.
- A custom script uploading a file from `target` without checking exit codes.
- Binding a publishing plugin to an ungated phase.

then **you cannot assume `mvn deploy` means producer contract tests passed**. Review the POM, profiles, test reports, and actual CI commands.

### Difference between `test` and `verify`

Some integration tests use Maven Failsafe or other plugins bound to phases after `test`. Thus `mvn test` may not run every verification check placed in `verify`.

For contract tests, check which runner the plugin uses to generate/compile/run generated tests. If a project uses Failsafe for tests needing a full context or broker, the quality gate must cover that phase.

## 7. Maven: inspecting the stub artifact before deploy

Typical outputs of the Spring Cloud Contract Maven plugin can include:

~~~text
target/
├── generated-test-sources/contracts/
├── stubs/
└── inventory-producer-1.0.0-stubs.jar
~~~

Exact names vary by module, classifier, packaging, and plugin version. Never hardcode paths when projects customize build directories.

Inspect JAR contents before deploying:

~~~bash
jar tf target/inventory-producer-1.0.0-stubs.jar
~~~

An **illustrative** layout of an HTTP stub:

~~~text
META-INF/com.example/inventory-producer/1.0.0/
├── contracts/
│   └── inventory/stockAvailable.groovy
└── mappings/
    └── inventory_stockAvailable.json
~~~

Some builds also include fixtures in the artifact. For **messaging contracts**, verify that required contract/message definitions and labels are packaged, rather than looking solely for HTTP WireMock JSONs.

### What to inspect inside the JAR?

1. **Right artifact coordinates:** `groupId`, `artifactId`, `version`, and `stubs` classifier.
2. **Fresh from the current commit:** not a leftover JAR from an older build.
3. **Contracts/mappings actually exist:** not an empty JAR or missing critical scenarios.
4. **Accurate version:** no mixed versions inside the artifact.
5. **Required fixtures packaged:** external body files, XMLs, or binaries stubs depend on.
6. **Zero secrets:** no tokens, passwords, real user data, or sensitive internal endpoints in fixtures.

**Note:** inspecting JAR contents is a **packaging and integrity** gate, not a replacement for the **producer tests passed** gate.

## 8. Gradle: publication tasks must depend on required tests

In Gradle, calling `publish` does not automatically run **every test in the project**. Enforcement depends on plugins and configured task graphs.

Common tasks in the Spring Cloud Contract Gradle ecosystem relate to `generateContractTests`, `contractTest`, `generateClientStubs`, or `verifierStubsJar`. **Exact names and dependencies must be verified via `./gradlew tasks --all` and your version's plugin configuration.**

### Gate pattern in the task graph

If the project already defines `contractTest` and `check` with mandatory checks, you can make Maven repository publication tasks depend on both:

~~~groovy
import org.gradle.api.publish.maven.tasks.PublishToMavenRepository

tasks.withType(PublishToMavenRepository).configureEach {
    dependsOn(tasks.named('check'))
    dependsOn(tasks.named('contractTest'))
}
~~~

This is a **conditional example**: use it verbatim only when your real project has a `contractTest` task and `maven-publish`; if the contract test task is named differently, substitute the actual task name. This snippet binds only **`PublishToMavenRepository`** tasks; if CI uses `publishToMavenLocal`, custom uploaders, or external jobs, build equivalent gates rather than assuming this snippet protects every publish path.

The invariant to check in the task graph is:

~~~text
publish remote stub
    depends on
all required producer contract tests
    depends on
contract generation + compilation + correct test environment
~~~

### Distinguishing task outcomes

| Task/result | What it proves | Still insufficient to publish when… |
|---|---|---|
| `generateContractTests` succeeds | Generator created tests | Tests were not executed |
| `generateClientStubs` succeeds | Generator created stubs | Producer tests have not passed |
| `verifierStubsJar` succeeds | Stub JAR created | Tests were not run or were skipped |
| `test` succeeds | Tests in `test` task passed | Contract tests live in another unexecuted task |
| `contractTest` succeeds | Contract test task passed if properly wired | Task discovered 0 tests, filtered them out, or missed contracts |
| `check` succeeds | Verification tasks wired to `check` passed | Contract tests are outside `check`'s graph |
| `publish` succeeds | Publication tasks ran | Missing dependencies on quality gates |

Verify the project's actual task graph and logs. **Never treat a task name as proof**: a `contractTest` task can exist and execute zero generated tests if input configuration is wrong.

### About `--continue` and skipping

Gradle can keep running independent tasks after a failure when using `--continue`, though the build still exits failed. Crucially, CI **must never convert a failed build into success** and trigger publishing. Similarly, passing `-x test` or excluding contract test tasks can bypass gates unless publication tasks enforce strict dependencies.

Avoid shell patterns that swallow exit codes—for example, proceeding to publish after a test command failed without checking status.

## 9. Two pipeline patterns: single-job and multi-job

### Pattern A — Single release job running tests before deploy

~~~mermaid
flowchart TD
    A["Checkout exact commit/tag"] --> B["Maven clean verify<br/>or Gradle checks + contract tests"]
    B --> C{"Did producer tests run and PASS?"}
    C -->|No| D["FAIL: do not publish"]
    C -->|Yes| E["Package and inspect stub JAR"]
    E --> F{"Metadata/contracts match revision?"}
    F -->|No| D
    F -->|Yes| G["Publish with release permissions"]
~~~

Pros: fewer file transfers between jobs; easy to link test results to artifacts. Cons: jobs holding release permissions must be tightly protected, and secrets must never be exposed to untrusted PR code.

With Maven, a single lifecycle command `clean deploy` inside an **authorized release job** traverses required phases automatically. Still verify there are no skip flags, test-skipping plugins, and that generated tests actually executed.

### Pattern B — Separate verify and publish jobs

~~~text
Job VERIFY (no repository upload permissions)
  checkout commit A
  generate + run producer contract tests
  assert test count > 0
  package candidate stub
  checksum candidate stub
  attach artifact + test reports to CI

Job CONSUMER CHECK (per policy)
  download candidate stub from commit A's VERIFY
  Stub Runner runs candidate
  run consumer tests
  record results

Job PUBLISH (release credentials)
  needs VERIFY (+ CONSUMER CHECK if gated)
  runs only for authorized branches/tags
  uses exact candidate artifact from commit A
  verify checksum, metadata, version
  upload to repository
~~~

Pros: clean separation of privileges, avoids exposing release credentials on PRs, and reuses the exact verified artifact. Cons: you must **guarantee artifact immutability** across jobs instead of silently rebuilding or pulling unrelated files from caches.

### Two ways to guarantee the same revision

- **Reuse the exact JAR from verify:** archive it as a CI artifact with a SHA-256 checksum; the publish job downloads it and verifies digest/commit.
- **Rebuild inside publish:** check out **the exact commit/tag** and re-run all producer tests before deploying. This takes longer yet avoids carrying JARs across jobs.

Avoid verifying commit A while publishing a JAR built from commit B, or verifying `1.0.1` while uploading a leftover `1.0.0-stubs.jar` from the workspace.

## 10. GitHub Actions example: publish only after producer verification

This is an **illustrative workflow** for a Maven module with `mvnw` and the Spring Cloud Contract plugin configured; adjust JDK, Maven repository, credentials, and test-count checks for real projects.

~~~yaml
name: contract-stub-gate

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Verify producer contracts
        run: ./mvnw -B -ntp clean verify

      - name: Require stub JAR
        shell: bash
        run: |
          jar_path="$(find target -maxdepth 1 -type f -name '*-stubs.jar' -print -quit)"
          test -n "$jar_path"
          entries="$(jar tf "$jar_path")"
          [[ "$entries" == *META-INF/* ]]
          echo "Candidate stub: $jar_path"

  publish:
    needs: verify
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
          server-id: internal-releases
          server-username: MAVEN_USERNAME
          server-password: MAVEN_PASSWORD

      - name: Reverify exact commit and publish
        env:
          MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
          MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
        run: ./mvnw -B -ntp clean deploy
~~~

### Reading the workflow

- `verify` runs on both PRs and pushes; **it holds no publish credentials**.
- `publish` has `needs: verify`; if `verify` fails, `publish` never runs.
- `publish` runs only on pushes to `main`; PRs get no publish path.
- `publish` checks out the triggering commit again and runs `clean deploy`, meaning **it re-runs checks through the Maven lifecycle** rather than uploading an untracked JAR.
- `setup-java` configures the Maven server ID and pulls credentials from secrets; `internal-releases` must match the repository declared in your project's `distributionManagement`/settings.
- The `Require stub JAR` step checks only **artifact existence**, not test counts. Projects must add a gate confirming **generated producer tests actually executed** via appropriate build/report checks.

This example **omits** a consumer compatibility job. If release policy requires consumer tests to pass before publishing, add a job using the candidate stub and make `publish.needs` depend on both `verify` and the consumer job.

> When applying this workflow in production, also verify **generated test discovery and test reports**, credential config, release job permissions, and Maven plugin versions. The JAR check above does not replace proof that producer contract tests actually executed.

## 11. Security aspect of gates: PRs have no publish permissions

Why separate verification jobs from publishing jobs?

1. Unmerged PRs can contain code from untrusted contributors and must not have default access to repository credentials.
2. If build scripts can read release tokens, a malicious change could try uploading an ungated artifact.
3. Publish triggers should be restricted to protected branches/tags, reviewed workflows, and least-privilege permissions.
4. Artifact repositories should restrict overwrite/deploy rights, especially for immutable release versions.

CI steps must **fail closed**: whenever test results cannot be verified, artifacts are missing, or versions cannot be validated, stop publishing. Never catch/ignore errors just to "get the release out on time".

You can add environment protections, approvals, tag signing, and provenance/SBOM checks per organizational rules. Those are additional governance layers, **not replacements for producer contract tests**.

## 12. Candidate stubs used in CI are not published releases

To test consumers prior to release, teams can produce a **candidate stub** in one of these places:

- Temporary CI job artifact accessible only within the same pipeline.
- Staging repository with narrow access permissions and unique versions.
- Isolated cache/workspace for test runners inside the same pipeline.

Consumers use Stub Runner to exercise the candidate against their real client.

**Distinguishing rules:**

| Attribute | CI candidate | Published stub |
|---|---|---|
| Purpose | Pre-release compatibility check | Contract downloaded by other consumers |
| Producer status | May still be under verification, never treated as a release until passing | Producer quality gate MUST PASS |
| Scope | Isolated CI/staging with controlled TTL | Official artifact repository |
| Version | Commit/build-specific; never overwrites other candidates | Traceable version governed by release policy |
| Replaceability | Cleaned up on failure | Immutable releases must never be overwritten |

If consumer tests run against a candidate **before producer tests pass**, consumer test results are diagnostic only; **never allow publishing** even if consumer tests are green.

### Why avoid `latest`?

Suppose consumer tests rely on `latest`, which currently points to yesterday's stub while the producer edited the contract today. If tests pass, you still do not know whether the consumer is compatible with today's change.

Pin explicit coordinates or artifact IDs:

~~~text
Producer commit: a1b2c3d
Contract revision: a1b2c3d
Candidate stub:
  com.example:inventory-producer:1.1.0-rc.1:stubs

Consumer test:
  run Stub Runner with exact 1.1.0-rc.1
~~~

Commits and versions are examples. With mutable `SNAPSHOT`s, guard against stale caches or the same version updating mid-run. Prefer per-candidate build IDs/digests or immutable versions.

## 13. What does Stub Runner protect after the producer gate?

On the consumer, Stub Runner downloads the artifact by coordinates and starts the matching HTTP/message stub. Example test skeleton for Checkout:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.1.0-rc.1:stubs:10000",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutInventoryContractTest {

    @Test
    void handlesStockAvailable() {
        // Call Checkout's real InventoryClient, pointing to stub port 10000.
        // Verify client parses sku, available, quantity
        // and business logic permits ordering.
    }
}
~~~

This is a **skeleton**, not immediately runnable: it needs `InventoryClient`, stub base URL config, and assertions. `LOCAL` assumes the artifact exists in the test environment's local Maven repository; in CI you can use a staging repository or an appropriate candidate-stub distribution mechanism.

### Consumer tests are not proof of producer tests

A green consumer test running Stub Runner proves the consumer handles **the loaded stub**. It does not prove:

- The stub came from the newly reviewed commit.
- The real producer returns the same body/status.
- Uncontracted branches work.
- Schema changes remain compatible with all older consumers.

Thus, **gating on producer tests before publishing** remains a prerequisite; running consumer tests prior to release adds an extra verification layer when required by policy.

## 14. Messaging stubs must also pass producer tests

This principle applies equally to message contracts. For example, Inventory emits an event:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_changed'

    input {
        triggeredBy('emitStockChanged()')
    }

    outputMessage {
        sentTo('stock-events')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-101',
            quantity: 0
        )
        headers {
            messagingContentType(applicationJson())
        }
    }
}
~~~

Generated producer tests must invoke `emitStockChanged()` on the base test, receive the message from the destination, and assert payload/headers. If the real publisher fails to emit or sends string `quantity: '0'` when consumers expect a number, producer tests must fail accordingly.

In that case, **never publish the new message stub** merely because label `stock_changed` exists in the artifact. Consumers calling `StubTrigger.trigger("stock_changed")` would receive a simulated event matching the DSL while the real producer remains broken.

For messaging, pay special attention to:

- Generated producer tests **actually receive the message**, not merely invoke the trigger method.
- Destination/binder/receiver observe the right channel.
- Payload and headers have exact types.
- No stale messages bleed over from earlier tests.
- Fixtures and async wait timeouts are tightly controlled.
- Stub artifacts contain the required **labels and contract definitions**, not solely WireMock HTTP mappings.

Broker reliability, transactional outboxes, retries, and duplicate delivery still require proper integration tests; contract gates do not prove those properties by themselves.

## 15. Blocking publication on red tests: three branch examples

### Branch A — Producer test fails due to type mismatch

~~~text
Contract:
  quantity: 8         # number

Producer actual response:
  "quantity": "8"     # string

Generated producer test:
  FAIL — type/value mismatch at $.quantity

Decision:
  BLOCK PUBLISH
~~~

Right action: investigate whether the producer broke the schema or the contract misstated the agreement; never loosen matchers just to turn the build green without consulting consumers.

### Branch B — Zero generated producer tests

~~~text
Build log:
  Build SUCCESS
  Unit tests: 74 passed
  Contract tests: 0 discovered / 0 executed

Output:
  inventory-producer-1.1.0-stubs.jar exists

Decision:
  BLOCK PUBLISH
~~~

Causes can include a wrong DSL path, unconfigured plugin, filtered test source sets, JUnit version mismatches, or skipped tasks. **Having a JAR is not enough**.

### Branch C — Producer tests pass and artifact matches revision

~~~text
Commit: A
Contract tests discovered: 6
Contract tests executed: 6
Failed: 0
Skipped: 0
Stub JAR: built from commit A
JAR metadata/contracts/mappings: verified
Release authorization: approved

Decision:
  ELIGIBLE FOR PUBLISH
~~~

If organization policy requires consumer compatibility tests prior to release, status remains **eligible** only until consumer gates pass. "Eligible to publish" does not mean already published.

## 16. Shortcuts that break quality gates

| Anti-pattern | Why it is dangerous | How to fix |
|---|---|---|
| `mvn deploy -DskipTests` for releases | Skips producer verification | Do not skip; inspect test reports and generated test counts |
| Script uploading `target/*-stubs.jar` right after `package` | JAR may be created before required tests pass | Upload only after quality gates using the exact revision's artifact |
| `gradle publish` not depending on contract tests | Artifact can publish without running `contractTest` | Wire task graph and check CI dependencies |
| Publish job using `if: always()` | Runs even when verification fails | Use explicit success conditions and `needs` |
| Enabling `testFailureIgnore` | Build proceeds despite failing tests | Fail builds on any contract test failure |
| Test job uses branch HEAD; publish uses a newer HEAD | Sources diverge | Pin exact SHA/tag or pass immutable artifacts |
| Using stale JARs from cache | Artifact exists yet comes from an older commit | Clean workspace; compare versions/digests |
| Reusing and overwriting a release version | Consumers cannot tell which bytes they run against | Enforce immutable repository versions |
| Checking only whether CI is green | Can be green with 0 contract tests | Mandate checking test discovery/execution |
| Running only consumer tests against stubs | Consumers miss real producer bugs | Run generated producer tests |
| Hand-editing stub mappings after producer tests | Artifact diverges from verified DSL | Rebuild and re-run gates on the final artifact |
| PRs holding deploy permissions | Risk of out-of-process releases | Protect branches/tags; restrict credentials to release jobs |
| Swallowing exit codes in scripts | Tests fail yet publish continues | Propagate failures; fail closed |
| Publishing a broken stub so "consumers can work ahead" | Consumers may adopt unverified stubs | Share candidates only in clearly labeled CI/staging envs |

### Be careful with automatic job retries

Retrying CI jobs for transient infrastructure faults can make sense if logged clearly. However, a flaky test caused by race conditions or shared data should never be "fixed" by retrying until green and publishing.

Release gate quality depends on **reproducible results**, not lucky single-run probabilities.

## 17. When should a failed candidate stub be retained?

A candidate stub from a failing producer PR can still help with **debugging**:

- Compare generator-produced mappings against expected contracts.
- Preview planned schema changes for consumer teams before finishing producer work.
- Run exploratory consumer tests to uncover undocumented assumptions.

However, enforce strict rules:

1. Candidates **must never be pushed to official release repositories** or aliases consumed by production/official consumer CI.
2. Metadata must clearly mark **UNVERIFIED / producer tests failed**.
3. Version or build ID must never collide with published releases.
4. Enforce appropriate cleanup/expiration lifecycles.
5. Never leak secrets through fixtures or mappings.

Retaining failed candidates is solely for **coordination**, never for bypassing gates.

## 18. Guarding against breaking changes before publishing

Even when all generated producer tests against the **new** contract are green, the API may still break existing consumers.

For example, Inventory previously returned:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

The new contract changes it to:

~~~json
{
  "sku": "SKU-101",
  "availability": "IN_STOCK",
  "units": 8
}
~~~

If both producer code and contract update together, producer tests still PASS. Yet an older Checkout release still reads `available` and `quantity`, putting it at risk of breaking.

Therefore, beyond producer test gates, you must:

- Run consumer tests against **the exact versioned candidate stub**.
- Audit deployed consumers and the fields they depend on.
- Provide transition periods, new API versions, or compatibility policies when changing fields/types.
- Never overwrite old stub versions with artifacts representing an incompatible new interface.

**Producer PASS is a necessary condition to publish a stub; consumer compatibility is the additional safety check when multiple versions coexist across services.**

## 19. Checklist for pipelines and reviewers

Before authorizing a stub release, verify:

- [ ] Groovy/YAML contracts live in the right module, branch, and revision.
- [ ] Spring Cloud Contract plugin discovered all required contracts and fixtures.
- [ ] Generated producer tests are created, compiled, and **actually executed**.
- [ ] No required tests are accidentally skipped, disabled, or filtered out.
- [ ] Producer contract tests **PASS** with traceable reports and logs.
- [ ] Tests exercise real producer code in scope rather than calling a self-mocking stub.
- [ ] Assertions enforce status/headers/body, message headers/payloads, and data types.
- [ ] Stub JAR contains needed mappings/contracts/fixtures; is non-empty and free of secrets.
- [ ] JAR was built from **the exact commit/version** verified by producer tests.
- [ ] Publication jobs depend on verification with no backdoor upload paths.
- [ ] Maven/Gradle builds do not enable `skipTests` or bypass `contractTest`.
- [ ] Artifact version is explicit; immutable releases are never overwritten.
- [ ] Release credentials are restricted to authorized jobs/branches/tags.
- [ ] If consumer tests are gated, they run against the exact candidate stub via Stub Runner and PASS.
- [ ] Potentially breaking changes are reviewed with deployed consumers.
- [ ] Whenever any mandatory condition is uncertain, the pipeline **does not publish**.

## 20. Practice exercise: analyzing a broken pipeline

### Scenario

A team uses Maven to build stubs for Inventory Service:

~~~text
Step 1: mvn package -DskipTests
Step 2: find target -name '*-stubs.jar'
Step 3: upload JAR to remote Maven repository
Step 4: notify Checkout to update Stub Runner version
~~~

The next day, Checkout tests pass against the new stub yet fail deserialization in live deployment because the producer returns `quantity` as a string.

Answer the following:

1. Which steps in the pipeline are wrong?
2. Why does an existing stub and passing consumer test fail to prove the producer is right?
3. What minimum condition must be added before the upload step?
4. How do you prevent accidentally publishing stale artifacts after fixing the pipeline?
5. If producer tests PASS while consumer tests against the candidate FAIL, what should you do?

### Reference answers

**Question 1:** Step 1 intentionally skips tests; step 3 uploads an artifact with zero evidence generated producer tests passed. This is a release gate failure.

**Question 2:** Stubs are generated from DSL and return contract-described responses, not necessarily reflecting buggy live producer responses.

**Question 3:** Generate and execute generated producer tests, confirm they ran and passed, and only then permit publishing. Check exit codes, test reports, and generated test counts.

**Question 4:** Run a clean build from a pinned commit; record revision/version and checksum; promote immutable artifacts or rebuild and re-test the exact commit inside the release job.

**Question 5:** Do not auto-publish if policy requires consumer compatibility. Investigate whether it is a breaking change, wrong client assumption, or flawed stub matcher; fix the contract/producer/consumer or plan a migration, then re-run the gate.

### Extension exercise: two-job design

Sketch a two-job workflow:

~~~text
verify:
  input: commit SHA
  output: tests PASS + candidate JAR + checksum
  permission: read source, no deploy secret

publish:
  dependsOn: verify
  conditions: approved main/tag + all required gates PASS
  input: same candidate JAR and checksum
  action: remote publish
  permission: limited deployment credential
~~~

**Food for thought:** if the `publish` job pulls a fresh JAR via `latest` instead of using `verify`'s artifact, does the "exact verified artifact" guarantee still hold? **No.** There is no longer a binding link between producer test results and published contents.

## 21. Takeaways and references

**Stub generation and stub publication must be separated by an explicit quality gate.** Spring Cloud Contract generating WireMock mappings or `*-stubs.jar` proves only that tooling processed the DSL—not that the producer implements the behavior. Before an artifact is released to consumers, CI must confirm generated producer tests **were discovered, executed, and passed** on the same revision, and only then package and push that exact artifact to the repository.

Once producer tests pass, still run consumer tests against the **candidate stub** via Stub Runner to verify compatibility for scenarios consumers depend on. Never publish ungated builds, never skip tests to ship faster, and never let `latest` or caches blur version boundaries.

### References

- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): plugin, producer test generation, and stub artifacts.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): tasks related to contract tests and stub packaging.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): how consumers fetch and run stubs by coordinates/version.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): meaning of `test`, `package`, `verify`, `install`, and `deploy`.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publication tasks and how to configure publications.

**Practical takeaway:** let tooling **generate stubs for testing**, but **publish stubs only after the producer has proven its contract promise**. That boundary lets consumers trust that stubs simulate an interface the producer can actually deliver.
