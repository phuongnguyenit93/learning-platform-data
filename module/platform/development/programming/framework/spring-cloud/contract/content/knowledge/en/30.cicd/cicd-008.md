# Distinguishing test results from deployment authorization decisions

## 1. Why is a green pipeline not yet a license to deploy an API to production?

In a microservices system, a **producer** exposes an HTTP API or emits messages, while a **consumer** calls that API or handles those messages. **Spring Cloud Contract (SCC)** lets both sides define behavior using **Groovy/YAML DSL**, generate **producer-side tests**, package a **stubs JAR**, and let consumers use **Stub Runner** to detect incompatible API changes.

When adopting CI/CD, a common misinterpretation is:

> "All tests in this job PASSED, so we can deploy right now."

That reasoning holds only if **the system's deployment policy is defined** and every mandatory condition of that policy was actually checked. A green test can be solid evidence for a specific behavior, yet does not by itself prove that:

- The producer implementation being deployed is the exact code that was tested.
- The stubs used by consumers were generated from the **current candidate contract/version**, not an older release.
- **Every consumer version requiring support** is compatible with the producer candidate.
- Generated producer tests actually executed, rather than being skipped or running 0 tests.
- The test base invokes the **real producer implementation**, not a fake controller returning expected bodies.
- Consumers run **real HTTP clients/message handlers**, not merely a Mockito stub.
- Other requirements such as security, database migrations, infrastructure, operational observability, rollback readiness, or approvals are complete.

This lesson belongs to the **CI/CD** chapter, focusing on **"Distinguishing test results from deployment authorization decisions"**. It builds evidence-based decision thinking rather than equating test status with release authorization.

### Learning objectives

After this lesson, you will be able to:

1. Explain the differences between **test execution result**, **test evidence**, **quality gate**, **release approval**, and **deployment authorization**.
2. Analyze a pipeline with green producer tests that is still **not authorized to deploy**.
3. Build an SCC evidence matrix: generated producer tests, candidate stubs, Stub Runner consumer tests, and verification scope.
4. Distinguish `PASS`, `FAIL`, `ERROR`, `SKIPPED`, `NOT_RUN`, `STALE`, and `UNKNOWN` when making decisions.
5. Design **policy gates** requiring exact artifact identity, test counts, consumer compatibility, and approvals.
6. Understand why deploying to staging, publishing artifacts, deploying to production, and shifting traffic can be **separate decisions**.
7. Handle waivers, flaky tests, canary rollouts, and rollbacks without turning failures into fake PASSes.
8. Create an auditable **decision record** template and use it to explain why a deployment was allowed or blocked.

## 2. Five concepts that must be kept distinct

| Concept | Question answered | Example |
|---|---|---|
| **Test execution** | Which tests ran, with what inputs and environment? | JUnit generated producer test calls GET inventory |
| **Test result** | What outcome did the executed test produce? | PASS, FAIL, ERROR, SKIPPED |
| **Test evidence** | What does that result prove, and from which version? | 42 tests, commit A, stubs JAR digest B, report C |
| **Quality/release gate** | Does the evidence satisfy policy criteria? | Required consumers PASS, no stale artifacts |
| **Deployment authorization** | Who/which mechanism permits deploying which artifact to which environment? | Allow build 173 to staging; production requires approval |

Two easily confused ideas:

**A test result is an observation.** It describes a single execution at a specific time, scope, and set of conditions. **Authorization is a policy-based decision.** It may consume test results, yet cannot be collapsed into a single Boolean from an arbitrary job.

One downstream distinction matters too: **authorized to deploy** does not mean **successfully deployed**. Deployment still needs execution, rollout checks, monitoring, and potential rollback if real-time conditions change.

## 3. Three decision layers: build, release, and deployment

~~~mermaid
flowchart TD
    A["Code + contracts + version"] --> B["Build and run tests"]
    B --> C{"Test evidence passes?"}
    C -- "No / missing evidence" --> X["BLOCK or REVIEW per policy"]
    C -- "Yes" --> D["Identified candidate artifact"]
    D --> E{"Release quality gate passes?"}
    E -- "No" --> X
    E -- "Yes" --> F["Approved release candidate"]
    F --> G{"Does production environment permit deploy?"}
    G -- "No" --> W["Hold candidate awaiting conditions"]
    G -- "Yes" --> H["Controlled deployment and rollout"]
    H --> I["Observe health/SLO"]
    I --> J{"Safe post-deploy?"}
    J -- "No" --> K["Halt/Rollback per runbook"]
    J -- "Yes" --> L["Continue or complete rollout"]
~~~

Examples:

- Build and contract tests PASS, yet operations froze changes during peak hours: **not yet authorized for production deploy**.
- Artifact is approved for release, yet secrets or migrations are not ready: **not yet authorized to deploy to the target environment**.
- Staging deployment succeeded, yet consumer compatibility for a production app has not run: **do not convert staging PASS into production approval**.
- Canary reached 5% traffic and health metrics degraded: **halt rollout**, even though all pre-deployment tests still PASS.

Contract testing is an important layer inside the **quality gate**, not the sole decision source.

## 4. Running example: Inventory Service and Checkout Service

Suppose Checkout (consumer) calls Inventory (producer):

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Currently operating contract (v1):

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","available":true,"quantity":12}
~~~

Producer candidate (v2) wants to replace `available` with `inStock`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","inStock":true,"quantity":12}
~~~

Possible results:

| Check | Result | Accurate conclusion |
|---|---|---|
| Generated producer test v2 against Inventory v2 | PASS | Producer v2 satisfies **contract v2** |
| Checkout v3 using Inventory v1 stub | PASS | Checkout v3 is compatible with **contract v1**, says nothing about v2 |
| Checkout v3 using Inventory v2 stub | FAIL | Potential **breaking change** for consumer v3 |
| Checkout v4 with updated DTO using v2 stub | PASS | Checkout v4 is compatible with tested v2 scenarios |
| Security/infrastructure readiness | NOT_RUN | Lacks evidence for a production decision |

**Conclusion:** you cannot authorize deploying Inventory v2 merely because v2 producer tests are green and some consumer test is green if they **did not test the same candidate** or missed a still-supported consumer.

## 5. Test result models need richer states than green/red

A real pipeline typically has multiple states:

| Status | Meaning | How to feed into release gate? |
|---|---|---|
| **PASS** | Tests executed and assertions passed | Valid only for the tested scope and verified artifact |
| **FAIL** | Assertions caught wrong behavior | Usually **BLOCK** if test is mandatory |
| **ERROR** | Test broke due to setup, dependencies, compile, timeout... | Never count as PASS; investigate/re-run |
| **SKIPPED** | Tests were discovered yet skipped | Fails the "actually executed" requirement |
| **NOT_RUN** | No run occurred or report is missing | Never default to PASS |
| **STALE** | Report exists yet used an old artifact/commit or expired past policy window | Never use to authorize a new candidate |
| **UNKNOWN** | Cannot determine outcome, source, or scope | Fail closed or require review |
| **CANCELLED** | Job cancelled before concluding | No passing evidence |

**Safety rule:** if a **mandatory** check lacks valid PASS evidence, the pipeline must not allow automated deployment. An **approved exception** mechanism may exist, yet it must appear explicitly as an exception, never disguised as PASS.

For flaky tests, re-running helps classify environment issues, yet **PASS on retry does not erase the fact that the first attempt FAILED**. Gates need explicit policies on retries, flakiness thresholds, and when investigation is mandatory.

## 6. A "meaningful PASS" carries full context

A test result should be linked with:

~~~text
testSuite: inventory-producer-contract-tests
result: PASS
testsExecuted: 18
testsFailed: 0
testsSkipped: 0
producerCommit: a1b2c3d4
contractRevision: a1b2c3d4
artifactVersion: 1.4.0-rc.pr173.a1b2c3d4
artifactSha256: <SHA-256 collected from build>
testRunner: JUnit Jupiter + Maven Surefire
testEnvironment: producer-ci
executedAt: <actual timestamp>
reportUri: <real test report location>
~~~

The `<...>` fields must be populated from the real pipeline, **not treated as verified metrics from an actual project**.

At minimum, you need to know: **which tests, which version, which environment, when, how many tests ran, and within what scope**. A screenshot displaying the word PASS is insufficient to bind to an artifact about to be deployed.

### Passing tests do not self-expand their scope

- 18 HTTP producer tests do not prove message contracts if no message tests ran.
- Testing `GET /api/inventory/SKU-123` does not prove every SKU, error path, or race condition.
- Consumer compatibility with Checkout v4 does not prove Checkout v3 was upgraded.
- Testing under JDK and config A does not automatically prove runtime deployment with config B works.
- Testing against WireMock does not prove brokers, load balancers, or production networks are ready.

**Never swap "tests ran cleanly" for "all deployment conditions are satisfied".**

## 7. Mapping Spring Cloud Contract evidence in CI

A quality gate for API changes needs at least these layers:

| Evidence | Source | Risk if missing |
|---|---|---|
| Contract source revision | Git commit, contract artifact | Unknown which contracts were verified |
| Generated producer tests | SCC Contract Verifier | No verification of producer implementation |
| Executed producer test reports | Surefire/Failsafe/Gradle | Test files may exist without executing |
| Candidate stubs JAR | SCC build/package | Consumers might use hand-written or stale mappings |
| Resolved artifact provenance | Repository + SHA/commit | Consumer tests not tied to the candidate |
| Consumer integration tests | Real client/handler + Stub Runner | New producer could break consumers |
| Compatibility matrix | Supported consumer versions | A consumer group may be left out |
| Required extra gates | Security, deploy readiness, migrations... | Contract tests do not cover these risks |
| Approval/audit record | CI policy + environment owner | Unclear who authorized deploy and under what rule |

One or two PASS rows in this table are **insufficient** to automatically assign `RELEASE_APPROVED`.

## 8. Generated producer tests must run against real code

Groovy DSL contract for Inventory v1:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout reads SKU-123 stock'

    request {
        method GET()
        url '/api/inventory/SKU-123'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

In a Maven/Gradle producer configured with SCC, Contract Verifier generates tests, invokes the endpoint via the corresponding adapter/test mode, and asserts responses against the contract.

Example **Spring MVC test base** you can use:

~~~java
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class ContractTestBase {
    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

The base test routes generated tests to the **production Spring MVC controller/service**. If the base class instead wires a `FakeInventoryController` returning hardcoded contract bodies, tests pass green even when the real producer implementation is broken.

**Quality gates must verify:** contracts are discovered, generated sources compile, **executed generated tests > 0**, and tests actually exercise the target code. Test with a mutation on a trial branch: change the producer to return `available=false` while the contract keeps `true`; tests must turn red.

## 9. Difference between existing test sources and executed tests

Cases that can create a "false green":

- Maven generates Java tests, yet Surefire/Failsafe misses them due to naming or JUnit version.
- Gradle plugin generates tests, yet the `test` source set/task does not run them.
- CI enables `-DskipTests`, `-Dmaven.test.skip=true`, or a profile skipping generation.
- Stale test reports remain in a cached workspace.
- Pipeline counts only **total unit tests**, ignoring that contract tests = 0.
- Generated tests are annotated `@Disabled` or excluded by environment conditions.
- Base tests mock all producer behavior, rendering assertions meaningless.

Example practice command for a Maven producer:

~~~bash
./mvnw clean verify
~~~

For a Gradle producer:

~~~bash
./gradlew clean test
~~~

Those commands **do not guarantee every task is wired properly**; inspect generated sources, execution reports, and artifact outputs. If policy requires contracts, block **zero-contract** or **zero-executed-contract-test** runs.

## 10. Consumer Stub Runner tests have a different role than producer tests

A Checkout test can run against a candidate stub:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.4.0-rc.pr173.a1b2c3d4:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutInventoryCompatibilityTest {

    @Autowired
    InventoryClient inventoryClient;

    @Test
    void checkoutCanReadInventoryCandidate() {
        StockResponse response = inventoryClient.getStock("SKU-123");

        assertThat(response.sku()).isEqualTo("SKU-123");
        assertThat(response.available()).isTrue();
        assertThat(response.quantity()).isEqualTo(12);
    }
}
~~~

`InventoryClient` and `StockResponse` here are **hypothetical Checkout classes**. The snippet omits full bean wiring and artifacts; `LOCAL` works only when the stubs JAR for those coordinates already exists in a runner-supported local source.

Key point: tests must use the **real HTTP client**. If you mock `InventoryClient.getStock()` to return a sample `StockResponse`, you are only testing orchestration—**not method/path/headers/serialization/error handling** or the Stub Runner artifact.

**Conclusion from PASS:** this consumer class/version understands the **tested response scenarios** of **this exact stub artifact**. It does not prove the real producer implementation, because Stub Runner serves contract-simulated responses.

## 11. Why two green test suites still may not permit deployment

~~~mermaid
flowchart LR
    A["Producer test B PASS with contract B"] --> C["Summary report: 2 jobs PASS"]
    D["Consumer test PASS with old stub A"] --> C
    C --> E{"Do both jobs share the same candidate artifact?"}
    E -- "No" --> X["BLOCK: unlinked evidence"]
    E -- "Yes" --> F["Continue evaluating other policies"]
~~~

In the example where Inventory renames `available` to `inStock`:

- Producer code B + contract B may be completely valid.
- Legacy consumer Checkout + stub A may be completely valid.
- Yet **the boundary between B and legacy Checkout may break**.

Quality gates must compare the **producer candidate** against the **stub artifact resolved in the consumer job**, not just count green jobs.

If consumer code uses primitive `boolean available`, a missing field can silently default to `false` depending on Jackson config, allowing a naive "response not null" test to pass. Write meaningful assertions checking mandatory fields, and test breaking changes to gauge your suite's detection power.

## 12. Test status and deployment decision status must live in two separate tables

An illustrative reporting model:

| Producer tests | Consumer tests | Valid artifact? | Other approvals/policies | Decision |
|---|---|---|---|---|
| PASS | PASS | Exact candidate | Satisfied | **ALLOW** |
| PASS | PASS | Stale stub / wrong commit | Even if reviewed | **BLOCK** |
| PASS | FAIL | Exact candidate | No valid exception | **BLOCK** |
| PASS | NOT_RUN | Exact candidate | Incomplete | **BLOCK/WAIT** |
| PASS | PASS | Exact candidate | Production approval pending | **WAIT_APPROVAL** |
| FAIL | PASS | Exact candidate | No waiver | **BLOCK** |
| PASS | PASS | Exact candidate | Production environment frozen | **WAIT_WINDOW** |
| PASS | PASS | Exact candidate | Abnormal runtime canary | **HALT/ROLLBACK** |

**ALLOW/BLOCK/WAIT_APPROVAL/WAIT_WINDOW** are **team-defined policy decision states**, not mandatory enums provided by Spring Cloud Contract. Nor does the table imply every organization must apply identical rules: compliance strictness and release processes vary.

What must never change is: **never infer missing evidence into PASS**, and **never flip a FAILED report to PASSED just to get green**.

## 13. Choose mandatory test scope by change risk, not dashboard color

Not every change needs the same test matrix, yet policy must define **minimum criteria per risk class**:

| Change type | Minimum tests to consider | Approval checkpoints |
|---|---|---|
| Producer internal refactor, contract unchanged | Generated producer tests + related regressions | Did undocumented semantics change? |
| Add new endpoint | Producer contract for new endpoint, identified consumers | Does unused endpoint affect auth/routing? |
| Add response field | Producer verification + affected consumer tests | Is unknown-field policy strict? |
| Remove/rename field | Producer tests + **currently supported consumer versions** | Breaking change and migration plan |
| Change error status/code | Error contracts + consumer error mapping | Do consumers retry/fallback on old codes? |
| Change request validation/required header | Producer negative tests + consumer request tests | Do legacy clients send all required inputs? |
| Change message schema/destination | Messaging contract tests + handler tests + needed broker integration | Are backlog events, replays, or un-upgraded consumers affected? |
| Change networking/security config | Contract tests + security/config integration | Are authentication and production routes verified? |

**Test scope is an owned decision.** Never let pipelines skip unregistered consumers just because tests are "slow". Maintain a dependency map from API/message contracts to consuming teams.

Quality gates can optimize by running **affected suites** on PRs and the **full supported matrix** before production release. Crucially, policy must verify the affected-consumer list rather than turning "not run" into "unrelated" by guesswork.

## 14. Contracts cover more than the happy path

To build a strong gate, inspect what requests/responses consumers genuinely depend on:

- HTTP methods, path variables, and query encoding;
- `Accept`/`Content-Type` and required headers;
- Request body fields and JSON types;
- Response status, body fields, and nullability;
- Business error codes, such as `SKU_NOT_FOUND`;
- Retryable errors like `INVENTORY_UNAVAILABLE`;
- Enums, numeric precision, and timestamp/timezone semantics;
- Message event type, destination, headers, schema version, and keys where applicable.

A green `GET SKU-123 -> 200` producer test does not protect consumers if a 404 body changes or a success response drops a mandatory field. Therefore **a PASS must never be interpreted beyond the declared and executed scenarios**.

At the same time, contract suites should not attempt to simulate all infrastructure faults: separate **promised producer behavior** from **resilience tests** such as latency, connection refused, broker redelivery, and circuit breakers.

## 15. YAML error contract example and its gate impact

A dedicated HTTP error contract:

~~~yaml
description: Inventory returns error when SKU does not exist
name: inventory_sku_not_found

request:
  method: GET
  url: /api/inventory/SKU-404
  headers:
    Accept: application/json

response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: SKU_NOT_FOUND
    message: SKU does not exist
~~~

For the producer candidate, generated tests must verify the **real implementation** returns the exact status and body. On the consumer, tests must confirm the client distinguishes:

| Response | Meaning | Client behavior to test |
|---|---|---|
| 404 + `SKU_NOT_FOUND` | Promised business error | Map to `InventoryNotFoundException` or equivalent |
| 404 unmatched WireMock | Request matched no mapping | **Do not** treat as `SKU_NOT_FOUND` based on status alone |
| 503 + `INVENTORY_UNAVAILABLE` | Contractual upstream unavailability | Retry/fallback per policy |
| Connection refused | No valid HTTP response | Separate transport failure |
| HTTP 200 + missing mandatory field | Protocol/schema mismatch | Never silently default business values |

Thus, a consumer compatibility gate checking only HTTP status 200 is too narrow when clients drive business logic from other fields and error codes.

## 16. The tested artifact must be the artifact slated for deployment

An error-prone pipeline pattern:

~~~text
Producer CI:
  build commit A
  test A PASS

Release job:
  rebuild from HEAD commit B
  deploy artifact B
~~~

Test evidence for A does not automatically prove artifact B is safe, even on the same branch name. The same hazard occurs when:

- Consumer tests ran against stub `inventory-service:1.3.0:stubs`, while production plans to deploy producer `1.4.0-rc1`.
- The pipeline republishes the same logical SNAPSHOT version after consumer tests finish.
- A Docker image is rebuilt with newer dependencies without regenerating test evidence.
- A step modifies a package/JAR post-test without recording a new checksum.

Safer model: **build once, verify once, promote the same immutable artifact** per project policy:

~~~text
commit A + contract A
    ↓
build producer artifact A + stubs artifact A
    ↓
producer verification A
    ↓
consumer compatibility with stubs A
    ↓
store digests and quality evidence
    ↓
promote exact artifact A
    ↓
deploy exact artifact A to target environment
~~~

If a pipeline must rebuild, prove equivalence and re-run required gates on the new output. A version label on a Docker image or JAR is insufficient if the registry permits tag overwrites.

## 17. Snapshots, caches, and evidence freshness

A Stub Runner ID may contain:

~~~text
com.example:inventory-service:1.4.0-SNAPSHOT:stubs:18081
~~~

Yet `-SNAPSHOT` is a **mutable** version. Maven metadata, Gradle caching, repository proxies, or a Stub Runner started prior to publishing can leave the consumer reading **stale mappings**.

To confirm freshness:

1. Record **producer commit**, contract revision, and candidate build ID.
2. Record **group/artifact/version/classifier** coordinates of the stubs artifact.
3. If using SNAPSHOTs, capture the resolved timestamped build or JAR digest.
4. Confirm Stub Runner actually **loaded those mappings**, rather than keeping an old server/process alive.
5. Verify the consumer HTTP client targets the right server/port.
6. Run assertions sensitive to candidate behavior.
7. Block automatically whenever provenance cannot be determined.

`mvn -U` and `gradle --refresh-dependencies` help refresh their respective resolvers, yet **do not force an already-running WireMock server to reload mappings**. For release gates demanding reproducibility, **commit-unique candidate versions with repository immutability** beat mutable SNAPSHOTs.

## 18. Compatibility matrix: do not test only the newest consumer

A producer may serve Checkout v3, Cart v2, and Analytics v1. **Illustrative matrix example, not real test results:**

| Producer candidate | Checkout v3 | Cart v2 | Analytics v1 | Decision |
|---|---|---|---|---|
| A: `available` | PASS | PASS | PASS | Eligible for remaining gates |
| B: `available` + `inStock` | PASS | PASS | NOT_RUN | **WAIT/BLOCK** per policy |
| C: `inStock` only | FAIL | PASS | FAIL | **BLOCK** if those versions remain supported |
| D: dual-field after fix | PASS | PASS | PASS | Eligible to advance release gate |

A compatibility matrix is valid when:

- Rows are **specific producer artifacts/versions** with digests.
- Columns are **specific consumer versions/commits**, not just app names.
- PASS/FAIL/NOT_RUN each link to a **dedicated test report**.
- The list of supported consumers is confirmed by owners.
- Production consumer upgrades rolled out or migration criteria passed before dropping old fields.

**Producer contract PASS cannot substitute for the full matrix.** If a consumer has not been tested, record `NOT_RUN` rather than assuming compatibility.

## 19. Distinguishing unconditional rules from risk-based conditions

Not every organization needs an identical deployment checklist. Policies often have two tiers:

**Unconditional automation requirements**, for example:

- Deployed artifact and test evidence have reconcilable provenance.
- Zero required producer/consumer tests failed or were skipped without an authorized decision.
- All required jobs completed; zero `UNKNOWN` states.
- Caller is authorized to request deployment to the target environment.
- Environment is not locked by a change freeze or incident policy.

**Risk-based conditions**, for example:

- Does a breaking API change require manual review?
- Does a migration require DBA approval?
- Are extra load, security, or compliance tests required?
- Are canary stages, traffic caps, and rollback plans required?
- Are active consumers still blocking removal of old fields?

Risk-based conditions **do not mean optional or arbitrary**. Express them with explicit criteria, owners, scope, and rationale when inapplicable.

## 20. Policy rules expressed as explicit logic

A logical model for **automated deployment**:

~~~text
ALLOW_AUTOMATED_DEPLOY =
    candidate_is_immutable
    AND evidence_matches_candidate
    AND producer_contract_tests_executed
    AND producer_contract_tests_pass
    AND required_consumer_tests_executed
    AND required_consumer_tests_pass
    AND required_security_and_operational_gates_pass
    AND deployment_window_allows
    AND environment_authorization_satisfied
~~~

This is **policy pseudocode**, not pre-built SCC code.

Whenever any fact is `UNKNOWN`, the decision is typically **BLOCK or WAIT_FOR_REVIEW**—never coerce UNKNOWN to true. For waivers, policy needs an **explicit branch** approved by an authorized role/mechanism, recording reason, expiration, and scope.

Every gate also needs an approved **"not applicable"** concept. Message tests may be N/A for an HTTP-only service, provided the policy owner has evidence the service truly has no message contracts.

## 21. Decision inputs must be independent of the desire to deploy

A simple yet critical rule:

> Never let the deployment job hardcode `testsPassed=true` without reading/verifying reports from the corresponding test jobs.

An illustrative evaluation record:

~~~json
{
  "candidate": {
    "service": "inventory-service",
    "commit": "a1b2c3d4",
    "version": "1.4.0-rc.pr173.a1b2c3d4",
    "artifactDigest": "sha256:<actual-digest>"
  },
  "evidence": {
    "producerContractTests": "PASS",
    "producerContractTestsExecuted": 18,
    "checkoutV3Compatibility": "PASS",
    "cartV2Compatibility": "NOT_RUN",
    "securityGate": "PASS"
  },
  "authorization": {
    "environment": "production",
    "decision": "BLOCK",
    "reason": "Required consumer cart-v2 was not tested"
  }
}
~~~

This is an **illustrative schema**, not a formal attestation. `sha256:<actual-digest>` is a placeholder to populate from the real build artifact. The sample shows distinct states: producer tests PASS, Checkout PASS, Cart NOT_RUN, production conclusion **BLOCK**. There is no contradiction because **the decision evaluates a broader condition set than a single test result**.

## 22. Manual approval: supplementary evidence, not a substitute for testing

An organization may require authorized approvers (release manager, service owner, DBA, security owner) before production deployment.

Approval should inspect:

- Candidate artifact ID/digest and Git commit;
- Contract diff and consumer impact;
- Test reports, coverage, and key negative/mutation test outcomes;
- Unexecuted jobs, flakiness, failures, and exceptions;
- Migration/rollback/monitoring plans;
- Target environment, deployment window, and requester permissions.

**Approval does not turn a failed test into a passed test.** It is an accountable risk decision (when policy allows), explicitly documenting waivers/limits and rationale. For non-waivable mandatory gates, even approval **cannot override** them.

Distinguish **code/contract PR review** from **deployment authorization**. Code reviewers confirm the change is sound; production approvers may also evaluate operational conditions arising after the PR merged.

## 23. From policy to CI implementation: look beyond job dependencies

A CI/CD workflow may define logical jobs:

~~~text
producer-contract-verification
    |
    v
candidate-build-and-attach-stubs
    |
    v
consumer-compatibility-matrix
    |
    +----> security-and-ops-readiness
                 |
                 v
          policy-evaluation
                 |
                 v
       production-approval
                 |
                 v
       controlled-deployment
                 |
                 v
       post-deploy-observation
~~~

**Note:** CI `needs`/job dependencies only enforce ordering and job-level status. They do not automatically verify:

- Executed generated producer tests > 0;
- Artifact digests match across jobs;
- The consumer matrix includes all required columns;
- Stub Runner loaded the exact candidate;
- A PASS job did not skip tests internally.

Enforce those via **explicit quality checks** and persist them as structured inputs to policy evaluation.

### Rerunning jobs must not corrupt provenance

A CI system can rerun a job days later. If the consumer job uses `1.4.0-SNAPSHOT` or `latest`, the rerun may download a different artifact than the original run. Thus **rerunning the same workflow does not mean rerunning the same candidate** unless artifacts are pinned.

## 24. Architecture-level GitHub Actions example

A **skeleton workflow illustrating orchestration** (real build, stub publishing, and consumer test steps must be implemented per repository; do not run verbatim before completing):

~~~yaml
name: inventory-contract-release-gate

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  producer_contracts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Configure Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Run producer verification
        run: ./mvnw -B clean verify
      # REQUIRED: verify generated tests > 0,
      # confirm no skips, save reports and candidate commit/digest.

  candidate_and_consumers:
    needs: producer_contracts
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Publish candidate and run affected consumers
        run: |
          echo "DEMO ONLY: integrate artifact publishing and compatibility matrix"
          exit 1
      # Do not replace 'exit 1' with a fake PASS.
      # Produce an immutable artifact version from the producer commit.
      # Pass version/digest to consumer jobs and inspect reports.

  deploy_production:
    needs: [producer_contracts, candidate_and_consumers]
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Production release gate
        run: |
          echo "DEMO ONLY: policy decision and deployment go here"
          exit 1
      # Environment protection, reviewers, and secrets
      # must be configured in repository/org settings.
~~~

Because this is a skeleton, it **intentionally fails** unimplemented jobs so echoing text never gives the illusion of verified compatibility or safe deployment.

In real implementation, add steps to publish candidate stubs **after producer verification**, run the consumer matrix with the exact artifact, compare digests, and publish a decision record. `environment: production` **merely references the environment**; required reviewers and branch restrictions must be configured in GitHub repository/org settings. An environment name in YAML **does not create an approval policy by itself**.

JDK `21` and action versions here are illustrative choices, not universal requirements across all Spring Boot/SCC lines.

## 25. Branch protection and environment protection are two separate layers

- **Branch protection:** guards merges into key branches via required status checks, reviews, signed commits, or project rules.
- **Environment protection:** guards deployments to specific environments, e.g., production requiring reviewers and/or restricting deployable branches.
- **Runtime access control:** determines which jobs/identities may use credentials to mutate clusters/clouds; prefer least privilege and workload identity where possible.
- **Contract-specific release gate:** verifies producer verification, consumer compatibility, and artifact provenance.

A PR merged thanks to status checks **does not automatically gain permission to deploy to production**. Conversely, someone authorized to click deploy **should not bypass mandatory compatibility gates**.

To reduce bypass risk, enforce policies on the **CI/registry/environment platform**, not just YAML comments. Production secrets should be granted only to jobs that passed proper authorization.

## 26. Distinguishing artifact publish, release, deploy, and traffic exposure

These are four actions that can occur at different times:

| Action | Target | Risk when conflated |
|---|---|---|
| **Publish artifact** | Push JAR/stubs/image to registry | Does not mean authorized to run in production |
| **Release approval** | Approve candidate per policy | Does not mean deployment has occurred |
| **Deploy** | Roll build onto staging/prod environment | Does not mean all traffic hits that build |
| **Expose/rollout** | Shift traffic / toggle feature flag for users | Requires runtime monitoring, kill switch, and rollback |

For example, a producer can publish `1.4.0-rc1-stubs.jar` so consumer CI tests it **before** authorizing deployment of the new API. That makes zero production traffic changes.

Similarly, you can deploy a new app to production behind a **disabled** feature flag, enabling new field behavior only after approvals and canary checks. Yet flipping a flag is still **a user-impacting change**, requiring its own policy if it could break consumers.

## 27. Security and operational readiness are not wholly inside SCC

Spring Cloud Contract excels at verifying documented interactions, yet does not replace:

- Secret scanning, dependency vulnerability checks, and container image scanning;
- Real authorization/tenant isolation and security configurations;
- Database migrations, data schema compatibility, and migration rollbacks;
- Readiness/liveness, rate limiting, timeouts/retries, and load/capacity;
- Broker topology, event ordering/duplicate delivery, and DLQs;
- SLO plans, observability, alerts, incident response, and change windows;
- Internal or regulatory compliance requirements where applicable.

A release policy may require these gates **based on risk level**. When inapplicable, record **N/A per approved rule** instead of faking PASS.

Never extrapolate "contract tests PASS" into "security and runtime behavior are verified". Document clearly in reports **what SCC protects** and which supplementary checks completed.

## 28. Canary and progressive delivery: pre-deploy PASS does not guarantee traffic PASS

Even after a candidate passes policy gates, deployment can still hit issues from production data, service discovery, networking, or traffic patterns.

A controlled rollout might include:

~~~mermaid
flowchart TD
    A["Release approved: artifact digest A"] --> B["Deploy 5% canary"]
    B --> C["Observe errors, latency, business metrics"]
    C --> D{"SLOs and guardrails met?"}
    D -- "No" --> X["Halt rollout + rollback/disable flag"]
    D -- "Yes" --> E["Increase to 25%"]
    E --> F{"Metrics met?"}
    F -- "No" --> X
    F -- "Yes" --> G["Proceed to 100%"]
    G --> H["Post-rollout monitoring"]
~~~

The 5%/25% splits are illustrative; projects must pick percentages suited to traffic scale and risk. Low-traffic systems may need longer observation windows or synthetic checks.

Keep these distinct:

- **Contract test PASS:** API/message behavior verified against fixtures.
- **Release approval:** quality and governance criteria met.
- **Canary health PASS:** live rollout stays within runtime guardrails during observation.
- **Rollout complete:** all traffic/feature flags shifted and post-cutover health confirmed.

A canary failure **does not retroactively turn earlier producer contract tests into FAIL**; it shows a **different category of evidence** failed. The right decision is to halt/rollback per policy while preserving test reports for investigation.

## 29. Rollback also requires accurate artifact-to-contract alignment

Suppose Inventory v2 deployed alongside a data schema migration. Rolling back to v1 can fail if:

- v2 wrote fields/database rows that v1 cannot read;
- producer v1 cannot understand newly published event formats;
- a consumer already upgraded to v2 depends on a new endpoint absent in v1;
- API gateway routing/caches still hold the new config;
- old-field removal was deployed before consumer migrations finished.

Therefore, a rollback plan must specify:

1. **Which prior artifact** is eligible for redeploy (exact digest);
2. Which consumer versions are compatible with that prior artifact;
3. Whether data/DB/schema versions are backward-compatible;
4. Which feature flags must be disabled or switched;
5. Whether already-emitted events/messages affect replays;
6. Monitoring checkpoints and rollout-halt criteria;
7. Who/which mechanism holds authority to execute rollback.

**Rollback is a conditional operational decision**, not an automatic consequence of a contract test failure. Sometimes disabling a flag or rolling forward with a hotfix is safer than reverting to a binary incompatible with current data.

## 30. Decisions have expiration and can become invalidated

A quality gate that PASSED yesterday does not necessarily authorize deploying today if conditions changed:

- The artifact was rebuilt or a tag was overwritten;
- A new production consumer was deployed without being tested in the matrix;
- A new security advisory affects one of the artifact's dependencies;
- Production entered an incident or change freeze;
- Migration prerequisites are incomplete or data state shifted;
- A waiver expired;
- Deployment configuration diverged from the approved candidate.

Policy should define **evidence freshness** and **reevaluation triggers**. When a trigger fires, the deployment job must **reevaluate** the affected conditions rather than blindly reusing a stale `ALLOW` saved in an old file.

An example decision record:

~~~yaml
candidate:
  service: inventory-service
  commit: a1b2c3d4
  imageDigest: sha256:ACTUAL_DIGEST_FROM_BUILD
decision:
  environment: production
  state: APPROVED_FOR_DEPLOY
  approvedAt: PLACEHOLDER_TIME
  expiresAt: PLACEHOLDER_TIME
  policyRevision: release-policy-v3
  invalidatedBy:
    - artifact_digest_changed
    - supported_consumer_matrix_changed
    - security_gate_changed
    - waiver_expired
~~~

This is an **illustrative decision-record schema**, not a built-in SCC/GitHub Actions config. Replace placeholders with real values. Upon expiration or condition changes, status should transition to **REVIEW_REQUIRED** or **BLOCKED** per policy.

## 31. Flaky tests, retries, and "red first, green second"

A test can fail intermittently from port collisions, unstable database fixtures, or Stub Runner startup races. The fix must never be "rerun until green".

| Observation | Reasonable interpretation |
|---|---|
| PASS on first attempt | Passing evidence for that run |
| FAIL then PASS on retry | **Flaky incident** to record; decide per policy |
| Consistently FAILS on new candidate | Real regression or setup bug |
| ERROR because repo failed to serve artifact | No compatibility evidence yet |
| SKIPPED because test is `@Disabled` | Does not prove protected behavior |
| Test ran yet hit a different server | Result unrelated to candidate |
| Test green thanks to stale stub | Stale/invalid evidence for the new change |

How to manage it:

1. Preserve logs and causes for both the FAIL and PASS attempts.
2. Cap retry counts; never retry indefinitely.
3. Investigate fixtures, port lifecycles, clocks, eventual consistency, and data isolation.
4. If a critical test is unreliable, **never use an accidental PASS to enable auto-deploy**.
5. If quarantining a test, the quality gate must record the excluded requirement plus owner/deadline to fix.
6. For real-network integration tests, distinguish infrastructure outages from producer/consumer regressions.

**A retry PASS is a new test result, not erasure of failure history.** When information is insufficient to conclude safely, hold deployment in review-pending per policy.

## 32. Writing a simple policy guard that fails closed on missing data

The example below illustrates an **evidence-verification gate** prior to automated deployment. It is a sample Bash + `jq` CI component and does not replace deployment permissions, security reviews, or full business policies.

Suppose `ci-evidence.json` is produced **by trusted jobs** with structure:

~~~json
{
  "candidate": {
    "commit": "a1b2c3d4",
    "imageDigest": "sha256:example",
    "stubsDigest": "sha256:example-stub"
  },
  "producer": {
    "result": "PASS",
    "executed": 18,
    "failed": 0,
    "skipped": 0
  },
  "consumers": {
    "required": [
      {
        "name": "checkout-v3",
        "result": "PASS",
        "executed": 12,
        "stubDigest": "sha256:example-stub"
      }
    ]
  },
  "security": {
    "result": "PASS"
  }
}
~~~

Illustrative Bash guard:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# CI must supply commit and digests of the artifact ready to deploy.
: "${EXPECTED_COMMIT:?missing expected commit}"
: "${EXPECTED_IMAGE_DIGEST:?missing expected image digest}"
: "${EXPECTED_STUB_DIGEST:?missing expected stubs digest}"

jq -e \
  --arg commit "$EXPECTED_COMMIT" \
  --arg image "$EXPECTED_IMAGE_DIGEST" \
  --arg stub "$EXPECTED_STUB_DIGEST" \
  '
    (.candidate.commit == $commit)
    and (.candidate.imageDigest == $image)
    and (.candidate.stubsDigest == $stub)
    and (.producer.result == "PASS")
    and (.producer.executed > 0)
    and (.producer.failed == 0)
    and (.producer.skipped == 0)
    and ((.consumers.required | length) > 0)
    and (.consumers.required |
      all(.[];
        .result == "PASS"
        and .executed > 0
        and .stubDigest == $stub
      )
    )
    and (.security.result == "PASS")
  ' ci-evidence.json
~~~

On `FAIL`, `NOT_RUN`, `null`, or digest mismatch, `jq -e` returns a non-zero exit code and `set -e` causes the job to **fail closed**. This is intentional: **missing evidence is never treated as success**.

### Limitations of this example

- JSON must come from a **tamper-protected data source**; if an untrusted job writes `PASS` itself, the guard cannot verify truth.
- The mandatory consumer list must come from a dependency registry/policy; checking only the submitted array can omit another consumer.
- Verify **report sources, executed test names, timestamps, coverage, and signatures/attestations** if required, not just counts.
- Production policy may demand approvals, change windows, migrations, and canary rules outside this script.
- Sample digest fields are placeholders, not production digests.

The snippet's purpose is demonstrating that **deployment decisions evaluate structured evidence**, rather than grepping `Tests passed` from a log.

## 33. Waivers: controlled exceptions are not PASS

Sometimes a team must decide with incomplete testing—for instance, an internal consumer scheduled for decommissioning whose compatibility job is currently broken.

If policy **permits exceptions**, record at minimum:

~~~yaml
waiver:
  id: WAIVER-2026-014
  appliesTo:
    candidate: inventory-service:1.4.0-rc.pr173.a1b2c3d4
    environment: staging
    failedOrMissingGate: analytics-v1-compatibility
  status: APPROVED_WITH_RISK
  reason: Job unavailable due to broken test environment
  mitigation: Do not expose new API to Analytics v1
  expiresAt: PLACEHOLDER_TIME
  approverRole: ReleaseManager
  ownerRole: AnalyticsTeam
  remediationTicket: FIX-1234
~~~

This is a **governance example**, not an actual approved exception. A sound waiver has these traits:

- Applies **strictly to the exact artifact, environment, gate, and expiration**.
- Carries an authorized approver and documented reason.
- Defines risk bounds, mitigation, rollback, or remediation deadline.
- Never mutates a test report from FAIL to PASS.
- Never bypasses gates designated by the organization as **non-waivable**.
- Triggers re-review if the artifact or deployment scope changes.

**Key distinction:** `Test status = FAIL/NOT_RUN` stays intact; `Deployment decision = APPROVED_WITH_RISK` can exist **separately** if policy permits and guardrails hold. Never call that state "all tests passed".

## 34. Audit trail: "who decided what based on which data?"

A decision record should answer:

1. **Artifact:** which commit, image digest, JAR/stubs coordinates, and checksum?
2. **Contract:** which revision, which endpoints/messages changed?
3. **Producer tests:** which generated tests ran, any failures/skips?
4. **Consumers:** which versions are in support scope, what was each version's result?
5. **Extra gates:** which security/compliance/operational readiness checks were needed and passed?
6. **Policy:** which rules and policy version applied?
7. **Approval:** who or what mechanism approved, when, for which environment, and expiry?
8. **Waiver:** if present, which risk was accepted and who owns it?
9. **Deployment:** which artifact actually deployed, timestamp, and environment?
10. **Runtime:** canary metrics, rollout status, incidents, and rollback actions?

This separates **test reports** from **deployment authorization records**. Both link via ID/commit/digest, yet should never be mashed together until "observations" and "decisions" are indistinguishable.

Never put tokens, PII, sensitive secrets, or raw production payloads into reports; logs must be **sufficient for traceability** while obeying data-handling policies.

## 35. Case study: two green pipelines, deployment still blocked

### Context

Inventory v1 returns:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

The Inventory team prepares v2 returning only:

~~~json
{"sku":"SKU-123","inStock":true,"quantity":12}
~~~

Checkout v3 still uses `available`. An Analytics v1 team also reads Inventory yet lacks a CI compatibility job.

### Observed data

| Evidence | Result |
|---|---|
| Inventory v2 generated producer tests | PASS |
| Inventory v2 stubs JAR | Candidate published |
| Checkout v3 tests against Inventory v1 stable stub | PASS |
| Checkout v3 tests against Inventory v2 candidate stub | NOT_RUN |
| Analytics v1 compatibility with candidate | NOT_RUN |
| Breaking-change review | Not approved |
| Deployment window | Open |

There is **no contradiction** when multiple jobs are green while deployment stays BLOCKED. The reason is **no evidence shows the candidate is compatible with active consumers**, and the breaking change lacks approval.

### Fixing the process

1. Point Checkout v3 at the exact v2 candidate stub using the real client.
2. Add Analytics v1 to the compatibility matrix.
3. If either fails, keep `available` alongside `inStock` using expand–migrate–contract.
4. Regenerate producer contract tests and candidate artifact; never hand-write stubs.
5. Re-run consumers against the new candidate and save artifact digests.
6. Review release/rollback and remaining gates.
7. Once all mandatory gates pass, deploy with canary/monitoring per policy.

### Takeaway

**Incomplete test results are not a failure of the test runner itself; they represent missing evidence for a decision.** A good quality gate surfaces that gap and holds deployment at BLOCK/WAIT rather than issuing false approval.

## 36. Case study: contract tests passed yet canary still rolled back

Inventory v2 was thoroughly verified against consumer candidates, test reports carried complete provenance, the security gate PASSED, and release was approved. After canary deployment, p95 latency spiked due to a new DB query missing an index.

**Accurate interpretation:**

- Producer/consumer contract tests remain PASS within the HTTP behavior scope tested.
- **Operational canary gate FAILED** because runtime latency breached guardrails.
- Rollout decision transitions from ALLOW to **HALT/ROLLBACK**.
- Remaining production traffic must not ramp up under the old plan.

Do not delete test reports or declare SCC "wrong". Add appropriate performance/regression tests, optimize the query, refine canary policies, and retest the new candidate through the process.

This shows **deployment decisions can change as new data arrives**, while historical test results stay intact.

## 37. Lab A — Creating separate test status and deployment decision tables

**Goal:** practice separating technical observations from authorization decisions.

1. Simulate producer candidate Inventory `1.4.0-rc1` with generated tests PASS (18/18).
2. Run Checkout v3 against stub v1 PASS, without testing the candidate yet.
3. Record each result accurately: producer PASS, Checkout-stable PASS, Checkout-candidate NOT_RUN.
4. Create the production decision record: **BLOCK due to missing consumer candidate evidence**.
5. Next, simulate Checkout-candidate PASS while Analytics v1 is NOT_RUN.
6. Keep BLOCK if Analytics is in the required consumers policy.
7. Simulate Analytics PASS, matching artifact digests, and completed security/approvals.
8. Only then transition to `ALLOW`, recording the exact policy revision.

**Deliverables:** two separate tables, decision rationale, and artifact IDs per round.

## 38. Lab B — Injecting intentional faults to test quality gates

**Goal:** prove policies catch false-green scenarios.

1. On a producer test branch, make the test base return a fake contract-matching response; mutate production code. If tests stay green, record that tests do not protect real code.
2. Restore the real base class; mutation must turn generated tests red.
3. Enable a test skip flag on a trial branch; the pipeline guard must catch **executed tests = 0**.
4. Point consumer tests at a stale stub version; provenance checks must block.
5. Mock the consumer HTTP client directly; tests pass without sending HTTP requests. Restore the real client.
6. Make a request body matcher overly permissive; send a wrong-type request and observe it match.
7. Tighten the matcher back; negative tests must catch invalid requests.
8. Confirm policy never permits deployment when a required check is `SKIPPED`, `NOT_RUN`, or `STALE`.

**Deliverables:** a table of "false PASS → cause → detection → remediation", plus logs/test reports for each case.

## 39. Lab C — Adding approval and canary conditions

1. Design a simulated pipeline with three gates: producer contracts, consumer compatibility, and security readiness.
2. Define policy requiring all three PASS proofs plus matching artifact digests.
3. Add a production approval step with an authorized reviewer.
4. When approval is missing, hold state at `WAIT_APPROVAL` even when tests PASS.
5. Once approval is granted, simulate a 5% traffic canary.
6. If error rate exceeds an illustrative threshold, transition to `HALT` and log the rollback action.
7. Keep test reports as PASS; record canary health FAIL **separately**.
8. Try a waiver for a non-mandatory gate only if policy allows; record scope, expiry, and owner.

**Deliverables:** decision matrix, decision record, status transition log, and rollback/mitigation diagram.

## 40. Troubleshooting: why is the job green while the deploy gate still blocks?

| Symptom | What to inspect | Avoid jumping to this conclusion |
|---|---|---|
| Producer tests green, deploy BLOCKED | Does the consumer matrix cover required versions? | "CI is broken because it doesn't trust tests" |
| Consumer tests green, artifact mismatch | Which candidate did Stub Runner resolve? | "Tests already proved the new candidate" |
| Test report shows 0 tests | Generator/runner/skip flags | "Zero errors means PASS" |
| Status `SKIPPED` | Were tests disabled by a profile? | "Tests practically PASSED" |
| Build report stale | Cache/workspace/test report timestamps | "This is the current commit's result" |
| Candidate digest changed post-build | Was there a rebuild or tag overwrite? | "Same version means safe" |
| Many consumers PASS, one NOT_RUN | Is that consumer required or N/A? | "Majority passed so ship it" |
| Missing approval | Environment protection and owners | "Merge access implies deploy access" |
| Deployment freeze | Change window / incident policy | "Contract tests failed" |
| Bad canary metrics | SLO guardrails and runtime evidence | "Contract tests are useless" |
| Rerun PASS after FAIL | Flaky cause and retry policy | "The earlier FAIL no longer matters" |
| Expired waiver | Scope, expiry, and approver | "Permanent exception" |

Sensible investigation order:

~~~text
1. Identify the exact candidate artifact
2. Identify the blocking gate and policy revision
3. Inspect reports: PASS/FAIL/ERROR/SKIPPED/NOT_RUN/STALE
4. Verify producer contract and consumer compatibility provenance
5. Check supplementary gates, approvals, and environment restrictions
6. Inspect runtime rollout/canary if partially deployed
7. Create action items with owners and additional evidence to collect
~~~

Each layer carries a distinct meaning. Never "fix deployment" by deleting a required check when the root issue lies in artifact provenance or approvals.

## 41. Release authorization review checklist

- [ ] **Test status** is separated from **deployment decision** in reports.
- [ ] Groovy/YAML contracts belong to the exact producer commit and were reviewed.
- [ ] Generated producer tests were generated, compiled, executed **> 0**, and passed.
- [ ] Test base invokes the real producer implementation, not fake responses.
- [ ] Stubs JAR was generated from the same contract revision with the right classifier.
- [ ] Stubs artifact version/digest matches the producer candidate.
- [ ] Consumer tests exercise the **real client/message handler** via Stub Runner.
- [ ] Stub Runner loaded the exact candidate, not a stale SNAPSHOT or old mapping.
- [ ] Required consumer versions list is confirmed by owners.
- [ ] Compatibility matrix covers all supported consumers without substituting PASS for NOT_RUN.
- [ ] Tests cover success/error cases and key breaking scenarios.
- [ ] Where needed, mutation/negative tests confirm the suite catches regressions.
- [ ] Evidence carries commit, digest, test count, timestamp, and report URI.
- [ ] Deployed artifact is the **approved artifact**, never silently rebuilt.
- [ ] Security, migration, config, and operational gates are evaluated per policy.
- [ ] `SKIPPED`, `ERROR`, `STALE`, and `UNKNOWN` states are handled explicitly.
- [ ] Flaky test retries log causes and enforce limits.
- [ ] No required check was disabled just to make the dashboard green.
- [ ] Deployment window and environment permissions are satisfied.
- [ ] If manual approval is required, an authorized approver signed off.
- [ ] Waivers (if permitted) specify scope, risk, owner, expiry, and mitigation.
- [ ] Rollout has health checks, guardrails, and a rollback/disable-flag plan.
- [ ] Decision record separates ALLOW/BLOCK/WAIT and preserves raw test results.
- [ ] CI leaks no tokens/PII/secrets in fixtures, logs, or evidence artifacts.
- [ ] Untested areas are documented explicitly, without extrapolating beyond scope.

## 42. Self-check questions

**1. Do passing producer contract tests authorize deploying a new producer API?**

No. They prove the producer implementation satisfies the tested contracts; they do not prove older consumers remain compatible or operational requirements are met.

**2. If consumer tests PASS using a stub from a previous commit, is the current candidate proven safe?**

No. Results belong to the older artifact and must be treated as **STALE/unrelated to the candidate** in the release gate.

**3. Can a `SKIPPED` job count as PASS if it shows no failures?**

No. If it is a required check, missing execution evidence must block/hold the gate or go through a valid exception workflow.

**4. Why store manual approvals separately from test PASSes?**

Because a test PASS is a technical observation, whereas an approval is an authorized decision on scope, risk, and environment. Approval never turns failed tests into passed tests.

**5. Once production approval is granted, will deployment always succeed?**

No. Deployment can still fail, or canary/health gates can fail. Monitor rollouts and halt/rollback per policy.

**6. If one required consumer is NOT_RUN while a hundred others PASS, what then?**

Never convert NOT_RUN to PASS. Policy must choose BLOCK/WAIT or a controlled exception; a majority passing never overrides a mandatory condition.

**7. Why bind artifact digests to test evidence?**

To guarantee the tested artifact is the artifact evaluated for deployment; version strings/tags can be overwritten, especially SNAPSHOTs or mutable image tags.

**8. Can a waiver override a compatibility failure?**

Only if organizational policy permits, with scope, risk, owner, expiry, and mitigation explicitly recorded. Failing tests must still be recorded as FAIL, never disguised as PASS.

**9. Do contract tests automatically catch a missing DB index that slows down a canary?**

Usually no. That is a performance/runtime risk requiring dedicated testing, monitoring, and rollout gates.

**10. What is the difference between `RELEASE_APPROVED` and `DEPLOYED_HEALTHY`?**

`RELEASE_APPROVED` indicates policy permits using the candidate in a given environment/time; `DEPLOYED_HEALTHY` requires post-deployment evidence that rollout succeeded and health metrics satisfy operational thresholds.

## 43. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): generated producer tests, Groovy/YAML DSL, stubs, and Stub Runner.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): HTTP/message contracts, matchers, and source structure.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): downloading artifacts and running consumer compatibility tests.
- [Spring Cloud Contract — Maven](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): generating producer tests and packaging stubs JARs.
- [Spring Cloud Contract — Gradle](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): Gradle plugin and build integration.
- [GitHub Actions — Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): jobs, needs, environments, and conditions.
- [GitHub — Deployments and environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments): protection rules, reviewers, and deployment configuration.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): test discovery/execution/reporting.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): checking client requests and unmatched calls.
- [Martin Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html): consumer-driven contract thinking.
- [Martin Fowler — BlueGreenDeployment](https://martinfowler.com/bliki/BlueGreenDeployment.html): a controlled deployment and rollback strategy.

**Version/scope note:** SCC Contract Verifier syntax, Stub Runner, Maven/Gradle plugins, and CI platform features may vary by version. Artifact values, digests, test counts, and deployments in this lesson are **illustrative examples**, not executed against a real repository. `ALLOW/BLOCK/WAIT` rules, waivers, compatibility matrices, and approvals are **policy proposals to adapt per organization**, not default SCC enums. Authoring this lesson did not run Maven/Gradle, perform releases, or execute dedicated Content QA.

---

**Key takeaway:** **Test results answer "what was verified, at which version and scope?"; deployment authorization answers "are all evidence, policies, authority, and operational conditions satisfied for the target artifact and environment?"**. Use Spring Cloud Contract to verify real producer code, use Stub Runner to verify real consumers against exact-revision candidate stubs, and then evaluate full quality gates, approvals, and rollout risks. Only then does a green pipeline become **trustworthy evidence**, rather than an over-inferred license to deploy.
