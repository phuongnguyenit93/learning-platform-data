# Tracing Stubs Back to Contracts, Commits, and Producer Verification Runs

## Lesson Objectives

With **Spring Cloud Contract**, a **Groovy DSL** or **YAML DSL** contract file can be used to **generate producer-side tests** and **create stubs** for consumers to run via **Stub Runner**. In the **Contract and Artifact Repositories** chapter, the challenge is not only where to store `-stubs.jar`, but also answering the question: **“Which contract, which commit, and which passing producer verification run produced the stub the consumer is using?”**

An HTTP stub returning valid JSON does not prove the current producer still honors the contract. Conversely, a green producer test on one commit does not prove the stub JAR in the repository was built from **that exact** tested commit and contract. Without a traceability trail, a consumer can PASS against an old stub while the upcoming producer release has already changed the API.

After this lesson, you can:

- Identify every link in **provenance** from contract source to stub artifact and consumer test.
- Distinguish **producer Git commit**, **contract revision**, **CI build/run**, **test execution**, **Maven artifact coordinates**, and **artifact checksum**.
- Understand why `BUILD SUCCESS`, a `-stubs.jar` file, and Stub Runner starting **are not enough** to declare compatibility.
- Design an evidence manifest linking an artifact to its inputs, verification run, and published release.
- Distinguish contracts living **in the same repository** as the producer from contracts living in a **separate repository/artifact**.
- Use fixed-version stub coordinates, checksums, and consumer logs to avoid version mix-ups.
- Build CI release gates, diagnose broken provenance, and evaluate the limits of test results.

## 1. Scenario: Consumer PASSes Yet New Producer Still Has a Breaking Change

Suppose:

- **Order Service** is the producer, exposing `GET /api/orders/{id}`.
- **Checkout Service** is a consumer reading the `status` field in the response.
- Producer version `2.4.0` published the stub:
  `com.example.orders:order-service:2.4.0:stubs`.
- A new producer branch preparing to release `2.5.0` renames `status` to `paymentStatus`.

Consumer CI is configured as:

~~~text
Stub Runner artifact:
com.example.orders:order-service:2.4.0:stubs

Checkout client:
GET /api/orders/ORD-1001

Sample response:
{"id":"ORD-1001","status":"PAID"}
~~~

Checkout tests can PASS because **stub 2.4.0** still has `status`, even though producer `2.5.0` will no longer return that field.

The right question before releasing `2.5.0` is not “did Checkout pass before?” but:

> **Do supported versions of Checkout PASS against the new stub generated from the contract verified on producer 2.5.0?**

To answer reliably, you must know **which stub**, **which contract**, **which producer build**, **which test run**, and **which consumer**.

## 2. End-to-End Traceability Chain

An evidence chain can be designed as follows:

~~~mermaid
flowchart TD
    A["Source contract<br/>path + contract revision"] --> B["Producer build<br/>commit + build environment"]
    B --> C["Generated producer tests<br/>generated and executed"]
    A --> D["Stub mappings<br/>converted from same contract"]
    C --> E{"Producer contract tests PASS?"}
    E -->|No| X["Block release"]
    E -->|Yes| F["Package stub JAR"]
    D --> F
    F --> G["Artifact coordinates + SHA-256"]
    G --> H["Remote artifact repository"]
    H --> I["Consumer CI uses Stub Runner<br/>downloads exact coordinates/checksum"]
    I --> J["Consumer tests + report"]
    J --> K["Scoped compatibility assessment"]
~~~

**Key point:** the arrows represent **relationships that must be proven**, not that Spring Cloud Contract automatically publishes all traceability metadata. Maven, Git, CI servers, and repositories must be configured to record evidence.

Provenance can be viewed across three layers:

1. **Source:** contract contents, location, and pinned revision.
2. **Verification:** producer source revision, build environment, generated tests, and execution results.
3. **Publication/Consumption:** published artifact bytes, repository coordinates, and the version the consumer actually downloaded and tested.

Missing any one layer makes it very hard to substantiate “the consumer is protected by a producer-verified contract.”

## 3. Identifiers Not to Confuse

| Identifier | Example | Question it answers |
| --- | --- | --- |
| **Contract path** | `contracts/orders/get_paid_order.yml` | Which scenario? |
| **Contract repository commit** | `def456...` | Which version of contract content? |
| **Producer Git commit** | `abc123...` | Which producer code ran tests? |
| **CI run / attempt ID** | `ci-run-7824/attempt-1` | Which build/test execution? |
| **Producer test report** | `surefire-reports/...` | Which tests ran and with what result? |
| **Maven groupId** | `com.example.orders` | Which artifact namespace? |
| **Maven artifactId** | `order-service` | Which module was published? |
| **Version** | `2.5.0` | Which release? |
| **Classifier** | `stubs` | Is this the stub JAR rather than the application JAR? |
| **Artifact checksum** | `sha256:<actual-digest>` | Which exact artifact bytes? |
| **Consumer commit** | `checkout@cde789...` | Which consumer code was tested? |
| **Consumer stub report** | `checkout-contract-test.xml` | Which consumer tests ran against that stub? |

A **version** is a label. A **Git commit** identifies source in a repository. A **checksum** identifies file contents. A **CI run ID** identifies an execution. These are related, yet **none substitutes for the others**.

For instance, the same `2.5.0-SNAPSHOT` coordinates can point to different bytes over time. Conversely, a single Git commit can produce different outputs if dependencies, build plugins, environment variables, or external contract artifacts change.

## 4. Starting from the Source Contract File

Suppose the producer has layout:

~~~text
order-service/
├── pom.xml
├── src/
│   └── test/
│       └── resources/
│           └── contracts/
│               └── orders/
│                   ├── get_paid_order.yml
│                   └── get_missing_order.yml
└── src/main/java/...
~~~

File `get_paid_order.yml`:

~~~yaml
description: "Read paid order"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

A minimal traceability record must capture:

- **Relative path** of the contract at the exact source revision.
- **Repository URL or source identifier** accessible by authorized team members.
- **Commit SHA** or immutable version of the contract source.
- If needed to distinguish files sharing a name or commit, the **contract file checksum**.
- How Verifier discovers files: contracts root, filters, repository config, or source sets.

### A filename alone is not an identifier

Two repositories can both have `get_paid_order.yml` with different contents. Thus:

~~~text
get_paid_order.yml
~~~

is weak evidence. A stronger reference is:

~~~text
contract_repo = order-contracts
contract_commit = def456...full-sha...
contract_path = orders/get_paid_order.yml
contract_sha256 = ACTUAL_FILE_SHA256
~~~

**Never fabricate a plausible-looking SHA-256** in a manifest just to fill a field; checksums must be computed from the real file bytes used in the build.

### When contracts and producer share a repository

In a single-repository setup, `contract_commit` usually matches or derives from the **producer commit**, provided the build runs on a clean checkout of that commit.

Still, record the **path** and verify:

- Working tree is clean or the build runs from an immutable checkout.
- No pre-test script mutates contracts on the fly.
- No extra external contracts are pulled without recording their source.
- The build system does not silently reuse stale mappings under `target`.

### When contracts live in a separate repository

Never record `producer_commit` in place of `contract_commit`. Two repositories have independent histories and lifecycles:

~~~text
producer_repo    = git.example.test/order-service.git
producer_commit  = abc123...
contract_repo    = git.example.test/order-contracts.git
contract_commit  = def456...
~~~

If the producer fetches contracts from a **Maven dependency** rather than a Git checkout, also record group/artifact/version/classifier and checksum of the **contract dependency**; record the source commit whenever traceable back to what published that dependency.

## 5. Tracing from a Contract to Generated Producer Tests

Spring Cloud Contract Verifier generates producer tests from DSLs. However, **merely seeing generated Java sources is not enough**. You must verify:

1. Which contracts the plugin actually **discovered**.
2. Generated tests were added to the **test source set**.
3. Generated tests **compiled** against the right base test class.
4. The test runner actually **executed** them.
5. The test report records **PASS/FAIL/SKIPPED**, not `0 tests`.
6. This execution ran on the exact producer source revision and exact contract revision.

Example Maven command sequence:

~~~bash
./mvnw -B clean verify
~~~

When the Spring Cloud Contract Maven plugin is bound to the lifecycle properly, the build can generate tests, convert contracts to WireMock mappings, and package stubs. Yet `verify` is just a Maven phase: tests/plugins must be configured to actually execute.

**Do not conclude all generated tests ran just because Maven reported `BUILD SUCCESS`.** If goals or the test runner were skipped, the build can succeed with zero producer verification.

### Evidence of test counts

A helpful CI report should contain:

~~~yaml
# Illustrative data, not default tool output.
expected_contracts: 12
discovered_contracts: 12
generated_producer_tests: 12
executed_producer_tests: 12
failed_producer_tests: 0
skipped_producer_tests: 0
producer_test_result: PASS
~~~

These counts **do not always have a strict 1 contract = 1 test ratio** in every configuration. Generated method/class organization, grouping, and HTTP/message scenarios can differ. Real pipelines should compare the contract/scenario inventory against generated test reports per your project version's conventions, rather than assuming one simple count always holds.

**Crucial reality check:** the number 12 in this example is hypothetical. Only record `generated_producer_tests: 12` when CI actually measured it.

## 6. Tracing to Stub Mappings and the JAR

The same contract source can be converted into WireMock mappings or resources for message stubs. Once packaged, the stub artifact usually carries the `stubs` classifier.

~~~text
Producer artifact:
com.example.orders:order-service:2.5.0

Stub artifact:
com.example.orders:order-service:2.5.0:stubs

Filename by standard Maven convention:
order-service-2.5.0-stubs.jar
~~~

Some Spring Cloud Contract versions package contracts and mappings under `META-INF`. Illustrative example:

~~~text
order-service-2.5.0-stubs.jar
└── META-INF/
    └── com.example.orders/
        └── order-service/
            └── 2.5.0/
                ├── contracts/
                │   └── orders/get_paid_order.yml
                └── mappings/
                    └── orders/get_paid_order.json
~~~

**Do not assume paths/filenames inside the JAR match this example verbatim.** Layouts can vary by plugin version, contracts root, or packaging configuration.

Use a command to inspect the generated artifact contents:

~~~bash
jar tf target/order-service-2.5.0-stubs.jar
~~~

A meaningful inspection should verify:

- A mapping exists for every expected scenario.
- Response files exist if mappings reference response files.
- Mappings match method/path/headers/body per the contract.
- No sensitive production fixtures/secrets are included.
- The JAR is actually the **published** one, not just another local file with the same name.

### Mapping names do not always equal contract names

One contract can yield multiple generated resources; generated test names, JSON mappings, and YAML contracts do not necessarily correspond **one-to-one by filename**. Therefore, for precise per-scenario traceability, teams can maintain a list of **contract IDs** and verify generated mappings during the build.

Do not claim Spring Cloud Contract **automatically generates** a manifest mapping every source contract to every mapping/test unless the project has verified that capability in its active version.

## 7. Why Do We Need the Stub Artifact's SHA-256?

Maven coordinates answer “what is the name and version?” yet do not always answer “**which bytes** were tested and published?”

For example:

~~~text
com.example.orders:order-service:2.5.0:stubs
~~~

If a repository permits **overwriting release artifacts**, a subsequent download can receive a JAR with different contents under unchanged coordinates. For `SNAPSHOT`s, publishing new builds under the same version is normal behavior.

Therefore, once packaging finishes, CI can compute SHA-256:

~~~bash
sha256sum target/order-service-2.5.0-stubs.jar
~~~

On Windows PowerShell you can use `Get-FileHash`; the snippet above is a POSIX shell example. **You do not need to run these commands to read this lesson.**

An evidence record:

~~~yaml
artifact:
  group_id: com.example.orders
  artifact_id: order-service
  version: "2.5.0"
  classifier: stubs
  extension: jar
  sha256: "ACTUAL_CI_COMPUTED_SHA256"
~~~

### Computing the checksum at the right time

1. Finish generating/packaging the stub JAR.
2. Compute the checksum from the **final artifact**.
3. Publish the artifact.
4. If you control publishing, **re-download** or compare the server-side checksum of the remote artifact.
5. The consumer verifies the checksum/artifact identity it actually fetched.

If the **JAR is modified after hashing**, the old checksum no longer identifies the bytes. Keep the provenance manifest **outside the JAR**, tied to coordinates and checksum, avoiding the paradox of embedding a file's own checksum inside itself and altering its hash.

## 8. Evidence Manifest: Linking All Evidence Together

Spring Cloud Contract provides test/stub generation tooling, whereas an **evidence manifest** is a **team-designed structure** connecting Git, CI, Maven, and consumer data.

Example:

~~~yaml
# Project-designed template; NOT a default file generated by SCC.
schema: "contract-provenance/v1"
producer:
  service: "order-service"
  repository: "git.example.test/team/order-service"
  commit: "abc123_FULL_PRODUCER_COMMIT_SHA"
  build_version: "2.5.0"

contracts:
  source_kind: git
  repository: "git.example.test/team/order-contracts"
  revision: "def456_FULL_CONTRACT_COMMIT_SHA"
  root: "contracts/orders"
  files:
    - path: "get_paid_order.yml"
      sha256: "ACTUAL_CONTRACT_SHA256"

verification:
  ci_run_id: "build-7824-attempt-1"
  ci_run_url: "https://ci.example.test/runs/7824"
  result: PASS
  generated_tests_detected: true
  producer_tests_executed: true
  producer_tests_failed: 0
  producer_tests_skipped: 0
  report_uri: "https://ci.example.test/runs/7824/reports"
  build_tool: "Maven"
  plugin_version: "LOCKED_VERSION"

stub_artifact:
  group_id: "com.example.orders"
  artifact_id: "order-service"
  version: "2.5.0"
  classifier: "stubs"
  extension: "jar"
  repository: "https://repo.example.test/maven/releases"
  sha256: "ACTUAL_JAR_SHA256"
  published: true
~~~

**Never replace placeholders with invented numbers and treat the manifest as evidence.** CI must extract values from Git, Maven, test reports, and the actual uploaded artifact.

### Distinguishing evidence from self-attestation

| Field | Appropriate source of truth |
| --- | --- |
| `producer.commit` | Git revision checked out in CI |
| `contracts.revision` | Git/dependency revision actually loaded |
| `contracts.files[].sha256` | Hash of actual contract file contents used |
| `verification.result` | Test report and verification job exit status |
| `producer_tests_executed` | Test runner reports, not assumptions |
| `stub_artifact.version` | Maven project/publication metadata |
| `stub_artifact.sha256` | Hash of packaged JAR |
| `stub_artifact.published` | Upload result and repository artifact verification |

A manifest claiming `result: PASS` **without a test report** or identifiable run ID is merely an **assertion**, not strong evidence.

### When should the manifest live outside the artifact?

Keeping the manifest outside the JAR has several benefits:

- Evidence can be signed/stored after the JAR checksum is finalized.
- CI report links can be updated without altering the JAR.
- Retention or access control for test logs can be managed separately from the artifact.
- Sensitive infrastructure info or personal details stay out of stub JARs downloaded widely by consumers.

If you want to embed build metadata **inside the JAR**, generate it **before** computing the final checksum, verify no data leaks, and still retain evidence in CI/repository systems.

## 9. Not Every Setup Uses the Same Contract Repository

Three common models:

| Model | Contract source | What to record |
| --- | --- | --- |
| **Same repository as producer** | `src/test/resources/contracts` in producer repo | Producer commit, contracts root/path, checkout state |
| **Separate contracts repository** | Contracts Git repo | Independent producer commit and contract commit |
| **Contract dependency from Maven repository** | Published artifact holding DSL | Coordinates/version/checksum of contract artifact and Git source if traceable |

### Same-repository model

~~~text
order-service@abc123
  |
  +-- src/test/resources/contracts/orders/get_paid_order.yml
  |
  +-- generated producer tests (CI build-7824)
  |
  +-- order-service:2.5.0:stubs
~~~

In this case, a fixed producer commit usually identifies the contract source. Still, if the build uses stale caches or scripts pulling external DSLs, record those additionally.

### Separate-repository model

~~~text
order-contracts@def456
          |
          v
order-service@abc123  -->  CI build-7824
          |                   |
          +-------------------+
                   |
                   v
       order-service:2.5.0:stubs
~~~

Producer CI must **pin** the contract revision it uses. Never declare `main`, `HEAD`, or `latest` and log only the producer's current commit, because the contract source can shift between two builds.

### Contract dependency as an artifact

Example following a team convention:

~~~text
com.example.contracts:order-contracts:7.3.1:contracts
~~~

These are **illustrative coordinates**; classifier `contracts` is not mandatory in every project. When the plugin resolves a contract dependency from a Maven repository, record the exact metadata of the dependency actually used.

If the contract artifact is overwritten under the same version, traceability can still break. Just like the stub JAR, checksums and immutability policies protect reproducibility.

## 10. Maven `install`/`deploy`: From Local Artifact to Remote

These phases are not identical:

| Phase | Primary output | Role in provenance |
| --- | --- | --- |
| `package` | Builds main JAR and can attach `-stubs.jar` | Establishes the build's artifact bytes |
| `verify` | Executes bound checks | Ties verification results to the build |
| `install` | Places attached artifacts in local Maven repository | Useful for testing on the same machine/agent |
| `deploy` | Publishes artifacts to remote Maven repository | Enables other consumer CI jobs to download |

Examples:

~~~bash
./mvnw -B clean verify
# Inspect test reports and stub jar in target/.

./mvnw -B install
# Put artifacts into Maven local if the build qualifies.

./mvnw -B deploy
# Run only in a pipeline with publish permissions.
~~~

These commands illustrate each step. **In practice `install`/`deploy` re-run earlier phases of the default lifecycle**, so you do not have to run all three sequentially in one release job. To guarantee the **exact same bytes** are promoted, design the pipeline so the verified artifact is archived and published **without rebuilding from mutable inputs**; or re-verify the artifact checksum after every build.

### Maven local is not a shared source

A stub `install`ed into `~/.m2/repository` on the author's laptop **does not automatically appear** on a consumer's machine or CI runner. In `LOCAL` mode, Stub Runner reads from the running process's own local environment, which may cache an older artifact.

In `REMOTE` mode, Stub Runner uses the configured repository. Evidence must therefore explicitly state **which source** it used.

### Release repositories should forbid overwrites

Release coordinates such as:

~~~text
com.example.orders:order-service:2.5.0:stubs
~~~

should point to an immutable artifact. If the system permits overwrites, verify checksums and store distinct evidence per publish; even better, change repository policy to forbid release overwrites.

## 11. A Git Commit Does Not Equal a Fully Reproducible Build

Two builds from the same commit can yield different JARs because:

- Snapshot or dynamic dependencies updated.
- Maven plugin/JDK/toolchain versions were not locked.
- Build fetched contracts from a moving branch or mutable Maven artifact.
- Test fixtures or code generators used `Instant.now()`, unseeded randomness, or external data.
- Resource ordering, build timestamps, archive metadata, or non-reproducible packaging intervened.
- Job built from a working tree with uncommitted files or post-generation edits.

Thus distinguish **provenance** from **reproducible builds**:

- **Provenance:** knowing *which artifact came from which inputs and run*.
- **Reproducibility:** regenerating byte-identical artifacts from identical inputs/toolchain per a defined process.
- **Compatibility:** producer and consumer satisfy the verified contracts/scenarios.

A good evidence manifest **does not prove byte-reproducibility by itself**. Where stronger guarantees are needed, run reproducible builds in isolated environments, compare checksums, and sign provenance per organizational supply-chain policies.

## 12. Producer Test PASS: Know Which Tests Actually Ran

A producer build can report PASS even when critical contracts were skipped. Possible reasons:

- Wrong contracts root or files excluded by filters.
- Spring Cloud Contract plugin not activated in the right Maven module.
- Generated tests omitted from the test source set.
- Test runner configured with excludes/skips.
- `-DskipTests` or `-Dmaven.test.skip=true` passed.
- Base test class mocks out the whole producer response instead of invoking the logic under verification.
- Tests assert overly broad matchers, missing fields consumers rely on.

Therefore, `verification.result: PASS` should be accompanied by:

1. List/count of **discovered contracts**.
2. List/count of **generated producer tests** per your parser/version's reporting.
3. **Test execution reports** and skipped test count.
4. Commit and run ID of the execution.
5. Link to logs/reports within an appropriate retention window.
6. Results of supplementary tests when contracts cover only part of the behavior.

**Never turn passing tests into a blanket claim that “all APIs and all consumers are compatible.”** Producer contract tests only prove the described scenarios as executed against specific fixtures/base tests.

## 13. The Consumer Must Prove It Downloaded and Used the Right Stub

After publishing, the consumer side can use:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:2.5.0:stubs:8090",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.test/maven/releases"
)
class CheckoutContractTest {

    @Test
    void checkoutHandlesPaidOrder() {
        // Configure Checkout to call the right stub server.
        // Assert Checkout logic upon receiving ORDER_PAID/PAID response.
    }
}
~~~

This is an **illustrative skeleton**; it needs classpath, Spring test setup, and real assertions. This annotation does not prove the consumer loaded the right bytes if repository/cache settings differ.

Consumer CI should record:

~~~yaml
# Team-designed record, not default tool output.
consumer:
  service: "checkout-service"
  commit: "cde789_FULL_CONSUMER_COMMIT_SHA"
  ci_run_id: "checkout-build-8812"
  result: PASS
stub_used:
  coordinate: "com.example.orders:order-service:2.5.0:stubs"
  sha256: "VERIFIED_SHA256"
  resolution_mode: "REMOTE"
  repository: "https://repo.example.test/maven/releases"
~~~

### Why record the checksum on the consumer side?

Because the same `SNAPSHOT` version or an overwritten repository can return different bytes across downloads. If the consumer only logs coordinates without verifying the actual artifact, it cannot prove it ran against the exact JAR the producer verified.

### Do not merely test that Stub Runner started

A valuable consumer result requires:

- Stub Runner actually downloaded the right artifact.
- The consumer's HTTP client called the stub server at the right host/port/service ID.
- Requests matched expected mappings.
- Consumer tests assert **application behavior**, such as Checkout state after receiving the response.
- Error scenarios the consumer relies on are also tested if part of the commitment.

Stub Runner **does not execute the producer implementation**. It simulates behavior generated from contracts, which is why linkage to producer verification must be preserved.

## 14. Two-Way Evidence: Producer and Consumer

~~~mermaid
flowchart LR
    CR["Contract revision<br/>def456"] --> PV["Producer CI<br/>commit abc123 / run 7824"]
    PV --> SJ["Stub JAR<br/>2.5.0:stubs / sha256"]
    SJ --> CV["Consumer CI<br/>Checkout cde789 / run 8812"]
    CV --> R["Compatible within<br/>tested scenario set"]
~~~

For a release, you can construct a table:

| Component | Illustrative value | Evidence |
| --- | --- | --- |
| Contract source | `order-contracts@def456` | Git commit + contract files |
| Producer implementation | `order-service@abc123` | Git commit + build metadata |
| Producer verification | `build-7824 PASS` | Test report, discovered contracts |
| Stub artifact | `order-service:2.5.0:stubs` | Published Maven coordinates |
| Artifact identity | `ACTUAL_SHA256` | Checksum |
| Consumer tested | `checkout@cde789` | Consumer Git revision |
| Consumer verification | `build-8812 PASS` | Test report + resolved stub checksum |

This is a **bidirectional relationship** because you can start from either side:

- **Producer:** “Which consumers have tested version `2.5.0`?”
- **Consumer:** “Which source/contract and producer verification run produced the stub this Checkout build downloaded?”

A solid evidence system lets you query in both directions without guessing from JAR filenames.

## 15. Trace Per Contract, Not Just Whole Artifacts

A stub artifact usually holds **multiple scenarios**. To know which contract impacts which consumer, maintain a scenario-level traceability table:

| Contract ID | Source path | Stub case | Consumer needing it |
| --- | --- | --- | --- |
| `get_paid_order` | `orders/get_paid_order.yml` | GET /api/orders/ORD-1001 → 200 | Checkout |
| `get_missing_order` | `orders/get_missing_order.yml` | GET /api/orders/ORD-9999 → 404 | Checkout |
| `create_order` | `orders/create_order.yml` | POST /api/orders → 201 | Sales Portal |

This is a **team-maintained table**, not a default feature guaranteeing one-to-one name traceability across all mappings.

Benefits:

- When `get_paid_order` changes, you know which consumers need re-running.
- When a mapping disappears from the stub JAR, missing scenarios are caught.
- When a producer test is generated yet not executed, you pinpoint the unverified contract scope.
- When assessing breaking changes, you see the impact on each interested consumer.

**Never use this table to skip unlisted consumers** if consumer registration is incomplete. The dependency list itself must be governed and kept current.

## 16. HTTP Contracts and Message Contracts Differ in Verification

Spring Cloud Contract applies to both HTTP and message-based integration.

| Perspective | HTTP contract | Message contract |
| --- | --- | --- |
| Input | Method/path/headers/body | `triggeredBy` or `messageFrom` |
| Output | HTTP status/headers/body | `outputMessage` with `sentTo`, body, headers |
| Producer verification | Generated test calls endpoint | Generated test triggers producer/sends message and checks output |
| Consumer stub | WireMock mapping | Message stub/trigger per Stub Runner integration |
| Shared provenance | Source revision, producer tests, artifact, checksum, consumer result | Same provenance components |

For message contracts, also record when consumers depend on:

- Verified topic/queue/binding name or logical destination.
- Schema/serializer and version if wire format has specific rules.
- Message stub label when the consumer triggers by label.
- Limitations of a broker test double compared to a production broker.

**A passing message stub does not prove broker delivery guarantees, ordering, or exactly-once semantics.** Those properties require additional tests/infrastructure. Evidence should explicitly state whether producer tests used a mock binder or a real broker.

## 17. Broken Provenance Scenarios

| Symptom | Likely root cause | How to investigate |
| --- | --- | --- |
| Consumer PASSes against old stub version | Version in Stub Runner ID not updated | Compare against producer release version |
| Same Maven version yet different checksum | Snapshot/overwrite or repository cache | Inspect bytes, checksum, immutability policy |
| Producer tests PASS yet stub JSON differs from reviewed contract | Generated mappings from a different contract revision | Check source root, checkout, contract dependency |
| Stub JAR has files yet producer tests didn't run | Build skipped tests or misconfigured lifecycle | Inspect test reports and executed goals |
| Manifest logs commit yet build had uncommitted changes | CI did not verify clean working tree | Use immutable checkouts/snapshots and log dirty flag |
| Producer and contracts in two repos yet only producer SHA logged | Missing contract provenance | Record contract repository + pinned revision |
| Remote deploy succeeded yet LOCAL consumer uses old JAR | Out-of-sync Maven local cache | Use REMOTE source properly or isolate local repository |
| JAR mappings missing scenario | Wrong filter/convert/package | Compare contract list against packaged mappings |
| Consumer report PASSes without identifying artifact | Resolution/version not logged | Log Stub Runner ID, repo, and checksum of used file |
| CI test report purged | Insufficient retention | Archive signed summaries or reports per policy |
| Release artifact overwritten after test | No immutable promotion | Lock releases; compare checksums before/after publish |
| Consumer test only checks stub started | Missing assertion logic | Add tests that genuinely consume stub responses |

Start debugging by asking **which arrow in the provenance chain broke**, instead of tweaking matchers or bumping versions blindly.

## 18. Security Governance and Evidence Access Control

A stub JAR may contain sample payloads, headers, or response files; CI evidence may contain internal repository paths and test logs. To share safely:

1. Put only **synthetic data** into contracts/fixtures; never copy production requests/responses containing personal data.
2. Never embed passwords, access tokens, private keys, or repository credentials in stub artifacts or manifests.
3. Store Maven repository credentials in secret managers/CI settings and restrict publish permissions.
4. Scope read/write permissions on source contracts, artifact repositories, and test reports per team/consumer needs.
5. Keep release artifacts immutable; if a buggy artifact must be revoked, follow an explicit process and record consumer impact.
6. Retain audit logs of who/which job published and when.
7. Use checksums/signatures/provenance attestations when organizational assurance levels require them.
8. Enforce sensible retention so after a release you can still retrieve the test reports behind the decision.

**A checksum is not a digital signature.** SHA-256 compares bytes; it does not prove an authorized publisher. If you need publisher authentication and anti-tampering for evidence, add signatures/attestations and key management—not merely a hash field in YAML.

## 19. Designing a Release Gate with Mandatory Provenance

A producer pipeline can be split into steps:

~~~mermaid
flowchart TD
    A["Checkout producer + pinned contract revision"] --> B["Verify working tree/inputs"]
    B --> C["Generate producer tests"]
    C --> D{"Enough tests, none skipped, PASS?"}
    D -->|No| X["BLOCK"]
    D -->|Yes| E["Generate mappings and package stub JAR"]
    E --> F{"Expected mappings present, no secrets?"}
    F -->|No| X
    F -->|Yes| G["Compute artifact checksum"]
    G --> H["Store producer verification evidence"]
    H --> I["Publish immutable artifact"]
    I --> J{"Remote artifact hash matches?"}
    J -->|No| X
    J -->|Yes| K["Consumer CI downloads exact artifact"]
    K --> L{"Consumer assertions PASS?"}
    L -->|No| X
    L -->|Yes| M["Store producer-consumer release record"]
~~~

### Rules to halt release

BLOCK whenever:

- Mandatory contracts are not discovered.
- Generated producer tests are skipped or lack execution reports.
- Producer contract tests FAIL.
- Mappings/stub JAR miss scenarios or contain sensitive data.
- Artifact coordinates or checksum mismatch the verified build.
- Supported consumers did not run against the new stub or their tests FAIL.
- The contract revision used to build the stub cannot be determined.

Distinguish **verification failures** from **infrastructure failures**. For example, a remote repository 503 error does not prove the contract is wrong, yet still blocks declaring a successful release.

### Do not leave consumer CI on an uncontrolled `latest` variable

An example unsuitable for concluding release compatibility:

~~~text
com.example.orders:order-service:+:stubs
~~~

Stub Runner versions supporting dynamic version strings can resolve different versions at different times. **Pinning versions** or recording the exact resolved version and hash is how you build reproducible evidence.

## 20. Step-by-Step Vendor-Neutral CI Script Example

This is **shell/CI pseudocode** to illustrate sequence, not a script you can copy and run directly in every repository:

~~~bash
# 1. CI checks out fixed source commit and contract revision.
#    Record producer_commit, contract_commit, run_id.

# 2. Build and verify producer.
./mvnw -B clean verify

# 3. Read Surefire/Failsafe reports or matching runner output.
#    Verify expected contract scenarios,
#    generated tests actually executed and were not skipped.

# 4. Inspect stub artifact and mappings.
jar tf target/order-service-2.5.0-stubs.jar

# 5. Compute checksum of the finalized artifact.
sha256sum target/order-service-2.5.0-stubs.jar

# 6. Generate evidence manifest from REAL metadata and reports.
#    Never mark PASS if any step lacks evidence.

# 7. Publish artifact to authorized repository.
#    Verify checksum of the copy in the remote repository.

# 8. Consumer CI resolves exact coordinates/checksum of the stub.
#    Run Stub Runner and consumer assertions.

# 9. Record consumer commit, run_id, result, and used artifact.
~~~

This lesson does not mandate Jenkins, GitHub Actions, GitLab CI, or any specific tool. What matters is **measured metadata**, **verification gates**, and **verified linkage between what was built and what was consumed**.

### What should be automated

- Extracting Git SHAs and checking for uncommitted changes in checkouts.
- Recording locked dependency/plugin versions.
- Aggregating test reports by `passed/failed/skipped`.
- Verifying contracts root and required scenario counts.
- Inspecting files/resources inside the stub JAR.
- Computing and verifying artifact checksums.
- Recording published GAV/classifier/version.
- Recording Stub Runner ID/version/repository and checksum downloaded by the consumer.
- Storing a queryable producer–consumer compatibility record.

A CI script that merely greps `BUILD SUCCESS` in logs **is not enough** to prove any of the above.

## 21. Assessing Compatibility at Release Time

Suppose the producer releases sequentially:

| Producer version | Contract revision | Stub artifact | Producer tests |
| --- | --- | --- | --- |
| `2.4.0` | `contracts@d111` | `2.4.0:stubs` | PASS on build 7001 |
| `2.5.0-rc1` | `contracts@d222` | `2.5.0-rc1:stubs` | PASS on build 7824 |
| `2.5.0` | `contracts@d222` | `2.5.0:stubs` | Needs verification for the separate release build |

**Never assume** `2.5.0` is producer-tested just because release candidate `2.5.0-rc1` PASSED. If the final artifact has different bytes, code, or build inputs, matching evidence is required—or a promotion mechanism promoting the already-verified artifact without rebuilding.

Similarly, if Checkout ran:

~~~text
checkout-service@cde789
test stub = order-service:2.4.0:stubs
result = PASS
~~~

do not relabel that result as:

~~~text
checkout-service@cde789
test stub = order-service:2.5.0:stubs
result = PASS
~~~

without actually running consumer tests against the new stub.

### Compatibility is a scoped relationship

A valid result should be interpreted as:

> Consumer commit `cde789` PASSED the tested scenarios via stub artifact `order-service:2.5.0:stubs` with the recorded checksum, produced from contract revision `d222` and its corresponding producer verification run.

It does not by itself prove:

- Every consumer in the organization ran.
- Every endpoint or production state is covered.
- Broker delivery/ordering, production TLS, performance, or security policies are verified.
- Services running in production actually run the matching artifact/version.

## 22. Practice Exercises

### Exercise A — Find the missing links

A report only records:

~~~yaml
stub_artifact: "com.example.orders:order-service:2.5.0:stubs"
consumer_test: PASS
~~~

**Task:** list the minimum fields to add so you know which contract, commit, and producer verification run produced this artifact.

**Hint:** contract repository/path/revision, producer commit, CI run ID, test report, artifact SHA-256, consumer commit, and actual downloaded version/checksum.

### Exercise B — Same version, different SHA-256

A release repository allows overwriting `2.5.0:stubs`. Producer CI has hash `H1`; consumer CI downloaded hash `H2`.

**Task:** can you claim the consumer tested the exact build the producer verified? How should this be handled?

**Hint:** no, unless the relationship between both artifacts is explicitly explained and proven; block release, investigate overwrite/cache, enforce immutable artifacts, and verify checksums.

### Exercise C — Contracts in a separate repository

Producer commit `abc123` uses contract repo commit `def456`. One job generates tests from `def456`; the stub-packaging job fetches contracts from `main`, which has advanced to `xyz789`.

**Task:** identify the risk and propose a pipeline fix.

**Hint:** pin the contract revision for both test generation and mapping generation, record input hashes, and build artifacts from the same source snapshot.

### Exercise D — Green build with no producer tests

CI logs show `BUILD SUCCESS` and `-stubs.jar`. However, Surefire reports contain no generated producer tests.

**Task:** evaluate the release gate and diagnostic steps.

**Hint:** inspect plugin executions, contracts root, test source sets, skip flags, test runners, and base class; insufficient evidence that the producer satisfies the contract.

### Exercise E — LOCAL cache differs from REMOTE repository

A Checkout developer runs Stub Runner `LOCAL` and PASSes with an old stub. Producer CI already published a new version to the remote repository.

**Task:** explain why the local result does not validate the new release and describe how to produce a traceable consumer run.

**Hint:** specify the new stub version, configure the right resolution source explicitly, clean/control caches, and record the real checksum.

### Exercise F — Artifact published yet no consumer PASS

Producer `2.5.0` PASSed contract tests, JAR checksum is valid, and it is published. Checkout `2.8.0` has not run against that stub yet; only a consumer run against `2.4.0` exists.

**Task:** how should compatibility status be reported?

**Hint:** producer-side verified and artifact published, yet **consumer compatibility not yet verified** for the new version pair. Never backfill the gap with old results.

### Exercise G — Signing provenance and secret management

A team wants to attach a manifest containing producer SHA, artifact checksum, and CI report URL. They plan to embed the repository token inside the manifest so consumers can download easily.

**Task:** revise the approach to make it safe.

**Hint:** keep credentials in secret managers/CI, put only non-sensitive metadata in manifests; if publisher authenticity must be proven, use signatures or attestations per policy.

### Exercise H — Build a verification matrix for a schema change

Order Service `2.5.0` renames `status` to `paymentStatus`. There are three consumers: Checkout `2.8`, Sales Portal `4.1`, and Analytics `1.3`.

**Task:** design a table with consumer commit, stub coordinates/checksum, test result, and used scenarios; explain why Checkout passing alone is not enough.

**Hint:** each consumer needs its own result against the new stub if still within support scope; combine with contract path/ID to see impact.

## 23. Traceability Checklist Before Declaring Compatibility

- [ ] Contracts identified by **repository + revision + path**, not filename alone.
- [ ] If contracts live outside the producer repo, exact dependency/revision is pinned.
- [ ] Producer commit and working tree/build inputs are recorded.
- [ ] Generated producer tests were generated from the exact contract revision.
- [ ] Generated producer tests were **executed** and PASSED, not merely generated in `target`.
- [ ] No `0 contract tests` or unexpected skips occurred.
- [ ] Producer CI run ID, report, and verification timestamp are saved.
- [ ] Stub mappings/response resources were generated from the same contract input.
- [ ] Stub JAR contains all expected scenarios and no sensitive production data.
- [ ] Maven **groupId:artifactId:version:classifier** coordinates are recorded explicitly.
- [ ] Final artifact SHA-256 is computed after packaging.
- [ ] Artifact bytes are never altered after computing the checksum without updating evidence.
- [ ] Stub releases are published to an immutable repository or verified strictly by hash.
- [ ] Verified the remote artifact actually exists and matches the checksum.
- [ ] Consumer Stub Runner downloads the exact version from the configured source rather than stale cache.
- [ ] Consumer tests actually invoke the stub and assert application behavior.
- [ ] Consumer commit, run ID, result, and stub checksum are saved alongside evidence.
- [ ] Supported consumers test against new stubs before release when needed.
- [ ] Limits around coverage, brokers, TLS, security, and production behavior are documented.
- [ ] Evidence manifest relies on measured data, never manually forced PASS markers.
- [ ] Tokens/secrets/private keys never enter contracts, stub artifacts, or reports.
- [ ] Queryable in both directions: **stub → producer verification** and **producer release → consumer runs**.

## Conclusion

**Tracing stubs** is more than writing `groupId:artifactId:version:stubs` in a configuration file. A trustworthy evidence chain connects **the contract file and source revision**, **the producer commit**, **an actual execution of generated producer tests**, **a stub artifact with a fixed checksum**, and **a consumer run using that exact artifact**. Only when these relationships are recorded and verified does CI have solid grounds to catch incompatible API changes instead of PASSing against a stub that happened to sit in cache.

**Takeaway:** *A stub is only valuable as compatibility evidence when you know where it came from, how the producer was verified, and which exact build the consumer tested.*
