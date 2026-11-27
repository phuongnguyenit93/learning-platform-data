# Version Matrices and Evidence Required for Each Combination

## Lesson Objectives

In **Spring Cloud Contract**, **Groovy DSL** or **YAML DSL** contracts describe HTTP/messaging behavior between **producer** and **consumer**. Contract Verifier generates producer-side tests; from the same contracts, the system can build and publish a **stub artifact** for consumers to use via **Stub Runner**. Both sides having had green tests separately is not enough to conclude all deployed versions are compatible: **you must verify the exact version pairs** and retain corresponding evidence.

Within the **Versioning and Compatibility** chapter, **"Version Matrices and Evidence Required for Each Combination"** answers four questions:

1. Which producer versions must work with which consumer versions?
2. What does a cell `Pᵢ × Cⱼ` actually test?
3. How should **producer contract test results, stub versions/checksums, contract revisions, and consumer test reports** be recorded so a PASS claim has solid grounding?
4. When a cell is FAIL, unexecuted, or no longer supported, how do you decide to **deploy, roll back, or delay**?

After this lesson, you will be able to build a matrix across multiple producer/consumer versions, distinguish backward and forward compatibility by dependency direction, construct a Stub Runner testing pipeline, compile evidence records for each cell, and identify gaps not covered by contracts.

## 1. What Problem Does a Version Matrix Solve?

Suppose:

- **Order Service** is the producer of `GET /api/orders/{id}`.
- **Checkout Service** and **Sales Portal** are consumers of Order Service.
- Order Service `2.4.0` returns JSON field `status`.
- Order Service `2.5.0` plans to switch to `paymentStatus`.
- Some deployed Checkout versions **still read `status`**.

If Checkout tests against stub `2.4.0` and PASSES, that **does not prove** Checkout will work with producer `2.5.0`. Likewise, Order Service `2.5.0` PASSING producer contract tests does not prove **all old consumers** can handle the new response if their expectations are not fully expressed in contracts.

~~~mermaid
flowchart LR
    P1["Order Service 2.4.0"] --> C1["Checkout 1.8.0"]
    P2["Order Service 2.5.0"] --> C1
    P2 --> C2["Checkout 2.0.0"]
    P1 --> C2
    P2 --> C3["Sales Portal 4.1.0"]
~~~

Connecting lines represent **pairs requiring evaluation**, not claims that they PASS. Every edge must carry its own status and evidence.

A **version matrix** is a map of `producer version × consumer version` combinations that can coexist in production or in a rollout plan, paired with verification results and support decisions.

## 2. Identifying Exactly Which "Version" You Mean

In Spring Cloud Contract, multiple kinds of versions appear side by side with distinct roles.

| Version / Identifier Type | Example | Role |
| --- | --- | --- |
| **Producer service version** | `order-service:2.5.0` | Producer build planned or deployed |
| **Consumer service version** | `checkout-service:1.8.0` | Consumer build running, preparing to deploy, or eligible for rollback |
| **Contract revision** | `contracts@def456` | Exact DSL contents used for verification |
| **Stub artifact version** | `2.5.0:stubs` | Stub bundle representing published producer behavior |
| **Stub artifact checksum** | SHA-256 computed from JAR | Actual bytes consumed |
| **Producer Git commit** | `order-service@abc123` | Producer source built and tested |
| **Consumer Git commit** | `checkout-service@cde789` | Consumer source tested |
| **Verifier/Stub Runner version** | Spring Cloud Contract version in build | Test tooling version, not business API version |
| **Schema/message version** | `schemaVersion: 2` | Payload/protocol version, not necessarily equal to Maven version |

**Do not equate** `order-service:2.5.0` with `schemaVersion: 2` or the Spring Cloud Contract plugin version. These versions evolve independently and must be recorded whenever they affect a check.

Also never assume Docker image tags, Maven artifact versions, and Git tags always point to identical contents. The release pipeline must verify the mapping among them.

## 3. A Matrix Has Two Main Axes, Plus Necessary Metadata

Basic matrix:

- **Rows:** producer versions `P₁, P₂, ...`.
- **Columns:** consumer versions `C₁, C₂, ...`.
- **Cells:** outcome and evidence when **consumer Cⱼ interacts with producer Pᵢ's behavior** under agreed scenarios.

Purely **hypothetical example for learning to read the table**, not executed test results:

| Producer \ Consumer | Checkout 1.8.0 (old) | Checkout 2.0.0 (new) |
| --- | --- | --- |
| **Order 2.4.0 (old)** | Sample PASS | NOT_RUN |
| **Order 2.5.0 (transitional)** | Sample PASS | Sample PASS |
| **Order 2.6.0 (drops old field)** | Sample FAIL | Sample PASS |

From this illustrative table:

- `Order 2.5.0 × Checkout 1.8.0` **deserves focus** to protect the old consumer when upgrading the producer.
- `Order 2.4.0 × Checkout 2.0.0` matters if the consumer may deploy before the producer, or if the producer may **roll back**.
- `Order 2.6.0 × Checkout 1.8.0` illustrates a breaking-compatibility risk if old Checkout still depends on the deleted field.
- `NOT_RUN` cannot be treated as PASS or FAIL; it is **missing evidence**.

A status table is only a summary view. Each PASS cell must link to a record holding the real **producer verification, stub identity, and consumer run**.

## 4. Explicitly Defining Compatibility Direction

Phrases like "backward compatible" and "forward compatible" cause confusion unless subjects are named. This lesson defines them by **producer–consumer relationship**:

| Check | Question | When It Matters |
| --- | --- | --- |
| **New producer × old consumer** | Does the new producer still serve previously deployed consumers? | Producer-first upgrade, backward compatibility |
| **Old producer × new consumer** | Can the new consumer work with an un-upgraded or rolled-back producer? | Consumer-first upgrade, producer rollback, consumer-side forward compatibility |
| **New producer × new consumer** | Do both target versions work together? | Target deployment state |
| **Old producer × old consumer** | Is the old baseline verified? | Baseline reference and regression analysis |

If your organization uses different "forward/backward" naming conventions, **write the exact versions on both sides** instead of relying on labels alone. Technically, what matters is **which P version interacts with which C version**.

### Especially Critical During Phased Rollouts

In a distributed system, two services rarely upgrade simultaneously:

~~~text
Time T0:    P_old + C_old
Time T1:    P_new + C_old
Time T2:    P_new + C_new
Rollback P: P_old + C_new
~~~

If producer rollback is possible after upgrading the consumer, **P_old × C_new** cannot be omitted from the matrix merely because the primary plan updates the producer first.

## 5. Running Example: Changing a JSON Field Without Breaking Old Consumers

Suppose consumer Checkout 1.8.0 reads:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

A new producer wants to rename `status` to `paymentStatus`.

### The Breaking Approach

Producer 2.5.0 returns only:

~~~json
{
  "id": "ORD-1001",
  "paymentStatus": "PAID"
}
~~~

If Checkout 1.8.0 requires the `status` field, `P2.5 × C1.8` risks FAILING. Adding a new field and deleting an old field in the same release are two distinct impacts.

### Temporary Expansion for Transition

Producer 2.5.0 can return both simultaneously:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID",
  "paymentStatus": "PAID"
}
~~~

Checkout 1.8.0 continues reading `status`; Checkout 2.0.0 reads `paymentStatus`. For a transition window, both consumers operate cleanly.

**Do not assume "adding a field is always compatible."** A consumer with a strict JSON deserializer, tight schema validation, or confused handling when both fields appear may reject the response. Therefore, you must still **test the old consumer** against the new response.

### YAML Contract for the Transition Phase

~~~yaml
description: "Returns both old status and new paymentStatus"
name: get_paid_order_transition
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
    paymentStatus: PAID
~~~

The contract describes behavior the real producer must satisfy. Do not edit a contract to an idealized response and **mock the entire controller returning sample JSON** just to pass generated producer tests; that skips the producer logic needing verification.

### Three-Phase Plan

1. **Expand:** producer emits both `status` and `paymentStatus`; verify against consumers using either schema.
2. **Migrate:** consumers move one by one to `paymentStatus`, while still checking older producer versions if rollback is possible.
3. **Contract:** drop `status` only when no supported consumer depends on it and both the matrix and rollout policy permit it.

This is the **expand–migrate–contract** strategy, not a mandatory Spring Cloud Contract syntax rule.

## 6. Statuses Needed Inside Each Cell

A matrix can use the following status set. These are **team-designed governance conventions**, not built-in enums of Contract Verifier:

| Status | Meaning | Counts as Verified Compatibility? |
| --- | --- | --- |
| **PASS** | Real consumer tests ran against the right producer/version stub and PASSED; matching producer verification has evidence | Yes, **within executed scenario scope** |
| **FAIL** | A check executed and failed | No; requires investigation |
| **NOT_RUN** | Not yet executed or report missing | No; unknown |
| **BLOCKED** | Could not run due to missing artifact, test infra, or permissions | No; unknown |
| **SKIPPED** | Test/cell skipped by config | No, unless explicit policy clarifies why |
| **NOT_APPLICABLE** | Combination lies outside architecture or proven deployment constraints prevent coexistence | Not PASS; requires explanation |
| **UNSUPPORTED** | Combination no longer covered under published version-support policy | Not PASS; excluded from release gate only with approval |
| **STALE** | Passed against a different/older artifact, commit, or report than the candidate under evaluation | No for current release |

In particular, **NOT_RUN ≠ PASS** and **BLOCKED ≠ FAIL**. A cell blocked by a broken repository does not prove consumer code is wrong, yet neither does it permit claiming compatibility.

### Store Statuses with Reasons

~~~yaml
# Illustrative record designed by the team.
producer_version: "2.5.0"
consumer_version: "1.8.0"
status: NOT_RUN
reason: "Consumer build for version 1.8.0 not yet available"
required_for_release: true
~~~

If this cell is mandatory during the rollout phase, the release gate should **block or require authorized risk acceptance**, never automatically flip `NOT_RUN` to `PASS`.

## 7. Evidence Required for Each Matrix Cell

A cell `Pᵢ × Cⱼ` needs more than an "X" or "✓". Include at least these evidence groups:

| Group | Fields to Record | Purpose |
| --- | --- | --- |
| **Producer identity** | Service/version/Git commit/build ID | Know which implementation was evaluated |
| **Contract identity** | Repo/contract revision/contract IDs or paths | Know which commitments were used |
| **Producer verification** | CI run ID/report, count of generated tests actually executed, PASS/FAIL/SKIPPED | Verify producer fulfills contract |
| **Stub provenance** | GAV + classifier, repository, SHA-256, source build | Ensure stub came from the matching producer verification |
| **Consumer identity** | Service/version/Git commit/build configuration | Know which consumer code ran |
| **Consumer verification** | Run ID/report, assertions, and status | Know how the consumer handled those scenarios |
| **Scope** | Scenario IDs, protocol, flags, test environment | Know what was and was not proven |
| **Decision** | PASS/FAIL/NOT_RUN, `required_for_release`, timestamp | Used for release gates and audits |

**Critical link:** the stub artifact in the consumer test must be produced from **the exact same contract input and producer build that passed matching producer verification**. A stub JAR of unknown origin makes a PASS cell untrustworthy.

### Sample Evidence Record for One Cell

~~~yaml
# Team-defined format, not default SCC output.
schema: "compatibility-cell/v1"
producer:
  service: order-service
  version: "2.5.0"
  git_commit: "abc123_FULL_COMMIT"
  build_id: "producer-ci-7824"
contracts:
  repository: "order-contracts"
  revision: "def456_FULL_COMMIT"
  scenarios:
    - get_paid_order_transition
    - get_missing_order
producer_verification:
  run_id: "producer-ci-7824"
  generated_tests_executed: true
  passed: true
  skipped: 0
  report_uri: "ci://producer-ci-7824/reports"
stub:
  coordinate: "com.example.orders:order-service:2.5.0:stubs"
  repository: "https://repo.example.test/maven/releases"
  sha256: "SHA256_COMPUTED_FROM_REAL_JAR"
consumer:
  service: checkout-service
  version: "1.8.0"
  git_commit: "cde789_FULL_COMMIT"
consumer_verification:
  run_id: "consumer-ci-8812"
  resolved_stub_sha256: "SHA256_VERIFIED"
  passed: true
  skipped: 0
  report_uri: "ci://consumer-ci-8812/reports"
decision:
  status: PASS
  required_for_release: true
  scope: "GET paid/missing order via HTTP stub"
~~~

These values merely illustrate structure. To create **real evidence**, CI must capture Git revisions, test results, artifact bytes, and resolved stubs from real runs. Never write `passed: true` before tests complete or paste placeholder strings like `SHA256_...` as valid checksums.

## 8. Why Store Both Producer Tests and Consumer Tests?

Both test types complement each other:

~~~mermaid
flowchart LR
    C["YAML/Groovy contract"] --> PT["Generated producer tests"]
    C --> ST["Stub JAR"]
    P["Producer implementation P_i"] --> PT
    PT --> V["Producer verification result"]
    ST --> SR["Stub Runner"]
    SR --> CT["Consumer C_j integration tests"]
    CT --> R["Consumer result"]
    V --> E["Evidence for cell P_i × C_j"]
    R --> E
~~~

- **Producer contract tests**: check that the producer implementation fulfills the described behavior.
- **Stub Runner consumer tests**: check that the consumer handles the corresponding stub scenarios.
- **Artifact provenance**: ties both branches to the exact same contract source and build.

If producer tests did not run, consumer PASS proves only that the consumer handles a **mock/stub**. If consumer tests did not run, producer PASS fails to prove a specific consumer application handles the new behavior.

### An Important Limitation

Producer contract tests and consumer stub tests protect only behaviors explicitly captured in contracts and genuinely exercised. If Checkout uses an uncontracted header or a JSON field bypassed by a matcher, both sides may stay green while production integration fails.

Matrices do not replace designing **contract coverage** and supplementary integration tests.

## 9. Stub Artifacts Must Match Producer Versions

In Spring Cloud Contract, HTTP stubs are typically packaged as a Maven artifact with classifier `stubs`:

~~~text
groupId      : com.example.orders
artifactId   : order-service
version      : 2.5.0
classifier   : stubs

Maven coordinate:
com.example.orders:order-service:2.5.0:stubs

Typical filename:
order-service-2.5.0-stubs.jar
~~~

Four components identify an artifact. Additionally, record the **SHA-256** of the published JAR, because `SNAPSHOT` versions are mutable and misconfigured repositories may allow overwriting releases.

### Tracing from Contract to Stub

~~~text
contract repository revision
        |
        +--> generated producer tests --> producer verification PASS
        |
        +--> stub mappings --> order-service-2.5.0-stubs.jar
                                      |
                                      +--> GAV/classifier
                                      +--> SHA-256
                                      +--> repository URL
                                              |
                                              +--> Checkout's Stub Runner
~~~

Never "copy some JAR with a similar name" into consumer tests and report `P2.5 × C1.8 PASS`. Prove the **exact GAV/checksum** resolved from the exact source.

### Testing Release Candidates vs. Final Releases

If a producer has:

~~~text
2.5.0-rc1:stubs
2.5.0:stubs
~~~

these two coordinates are **not automatically equivalent**. Consumer PASS against `rc1` does not automatically carry over to `2.5.0` if the final artifact was rebuilt or has different bytes. To promote results, use a pipeline that promotes the exact verified artifact with matching checksum/provenance evidence; otherwise, re-run tests against the final build.

## 10. Consumers Use Stub Runner to Verify One Exact Cell

A consumer test using Spring Cloud Contract Stub Runner can be configured as:

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
class CheckoutAgainstOrder250ContractTest {

    @Test
    void checkoutHandlesPaidOrder() {
        // Configure Checkout's HTTP client to call stub port 8090.
        // Execute Checkout business logic.
        // Assert statuses/branches Checkout depends on.
    }
}
~~~

This is an **illustrative test skeleton**, not a complete test. It requires real client wiring, dependencies, and assertions. This test class can execute against **Checkout 1.8.0's source/tag** or 2.0.0 depending on the pair under evaluation, rather than testing only consumer HEAD.

In the Stub Runner ID:

~~~text
com.example.orders:order-service:2.5.0:stubs:8090
        group            artifact  version classifier port
~~~

**Port 8090 is not part of the Maven artifact coordinates.** It is purely a runtime parameter for the stub server in this ID syntax.

### Key Point When Checking P2.5 × C1.8

If the consumer test uses:

~~~text
com.example.orders:order-service:2.4.0:stubs:8090
~~~

then that is evidence for **P2.4 × C1.8**, not **P2.5 × C1.8**. Renaming a report or CI job does not turn an old stub into the new one.

### Do Not Use `latest` for Release Decisions

If your Stub Runner version permits dynamic versions such as `+`:

~~~text
com.example.orders:order-service:+:stubs:8090
~~~

the exact same consumer commit can download two different artifacts across two runs. For **release gates**, pin an explicit version, log the actually resolved version, and verify checksums where policy requires.

## 11. Minimum Matrix When Upgrading One Side at a Time

Suppose current deployment is:

~~~text
P_old = Order 2.4.0
C_old = Checkout 1.8.0

Target:
P_new = Order 2.5.0
C_new = Checkout 2.0.0
~~~

A basic 2 × 2 matrix:

| Combination | Why Test It? | Concrete Evidence |
| --- | --- | --- |
| **P_old × C_old** | Currently running baseline | Historical producer verification P_old + consumer test C_old against stub P_old |
| **P_new × C_old** | Upgrade producer before consumer | Producer verification P_new + C_old against stub P_new |
| **P_old × C_new** | Upgrade consumer before producer or producer rollback | Producer verification P_old + C_new against stub P_old |
| **P_new × C_new** | Target state | Producer verification P_new + C_new against stub P_new |

**Not every combination is always mandatory.** If the organization proves P_old and C_new **cannot coexist** and no rollback plan can create that pair, you may mark it `NOT_APPLICABLE` with an approved reason. Never skip a cell merely because it wasn't mentioned in the primary rollout plan.

### When Multiple Consumers Exist

Suppose Order Service serves:

- Checkout `1.8.0` (deployed).
- Checkout `2.0.0` (preparing to deploy).
- Sales Portal `4.1.0` (deployed).
- Analytics `1.3.0` (scheduled job still calling the API).

When upgrading the producer, the matrix expands to include columns for each **consumer service/version**, not just "the newest consumer."

| Producer | Checkout 1.8 | Checkout 2.0 | Sales 4.1 | Analytics 1.3 |
| --- | --- | --- | --- | --- |
| Order 2.4 | Historical PASS | Test if rollback possible | Historical PASS | Historical PASS |
| Order 2.5 | **Mandatory** | **Mandatory** | **Mandatory** | **Mandatory** if still supported |

An unexecuted row should never be filled in as PASS just because nobody reported production errors. **Absence of alerts** is not **CI evidence**.

## 12. A Matrix Does Not Mean Running Infinite Combinations

In large organizations, cells multiply quickly: many producer releases, consumer releases, protocol versions, and feature flags. Running every historical version ever built is infeasible.

Scope the matrix by **support policy and realistic coexistence**, not brute-force count.

### Minimum Scope to Consider

1. **Target producer × every active and still-supported consumer version.**
2. **Currently running producer × target consumer**, if the consumer can deploy first or the producer can roll back.
3. **Target × target** for the desired end state.
4. Pairs required by **canary, blue/green, rolling upgrades**, regions, tenants, or offline mobile apps.
5. Pairs with prior FAILs or breaking changes requiring re-verification after fixes.

### Scope That May Be Excluded from Release Gates

- Consumer versions past end-of-support with **zero live instances/clients** per operational evidence.
- Producer versions past support windows, no longer in rollback/canary paths.
- Combinations prevented by proven deployment constraints.

For exclusions, record **reason, approver/approval method, timestamp, and deployment evidence**. Never mark `NOT_APPLICABLE` lightly just to turn the matrix green.

### Mobile and External Clients

Consumers like mobile apps or external partners do not upgrade simultaneously with the producer. Sometimes it is **impossible to know or control every live consumer version precisely**.

In those cases, API versioning, backward compatibility, and deprecation windows must reflect reality; the CI matrix covers the versions for which the team maintains representative tests/SDKs, and must explicitly document that boundary.

## 13. Every Cell Needs Scenarios, Not Just Version Numbers

Even when the matrix has the right versions, a PASS cell is weak if consumer tests check only "HTTP 200."

For Checkout, scenarios may include:

| Scenario ID | Request/Event | What Consumer Depends On |
| --- | --- | --- |
| `get_paid_order` | GET /api/orders/ORD-1001 → 200 | Reads `id` and `PAID` state |
| `get_missing_order` | GET /api/orders/ORD-9999 → 404 | Handles not-found cleanly |
| `get_pending_order` | GET pending order → 200 | Prevents premature checkout completion |
| `order_service_error` | Protocol error response | Safe retry or error display |
| `order_paid_event` | `ORDER_PAID` message | Consumer handles event format/destination properly |

Cell-level evidence should name **which scenarios** ran and which assertions mattered. Multiple consumer test methods may cover one contract file; do not assume `1 contract = 1 test` across all setups.

Example scope record:

~~~yaml
# Illustrative scenario list managed by the team.
producer_version: "2.5.0"
consumer_version: "1.8.0"
scenarios:
  get_paid_order: PASS
  get_missing_order: PASS
  get_pending_order: NOT_RUN
overall_status: NOT_RUN
reason: "Required scenario get_pending_order has not run yet"
~~~

**A cell should PASS only if all its required scenarios are verified** under published policy.

## 14. Do Not Equate "Added a Field" with "Non-Breaking"

API changes can impact multiple directions and versions.

| Change on Producer | Primary Risk | Must Verify |
| --- | --- | --- |
| Remove/rename JSON field | Old consumers fail to read it | P_new × C_old |
| Change `amount` type from number to string | Mapping/deserializer errors | P_new × C_old and C_new |
| Add optional JSON field | Strict-parsing consumers may reject it | P_new × C_old |
| Change HTTP 404 to 200 + error body | Consumer branches misclassify | Every consumer relying on status |
| Change URL/path/query/required header | Consumer requests fail to match | P_new × C_old |
| Alter semantics of the same field | Type-only tests miss it | Scenarios with business assertions |
| Change default pagination/sorting | Consumers process lists differently | Paginating consumers |
| Change error schema | Retries/UI affected | Consumer error scenarios |
| Change message destination/topic | Consumers miss events | P_new × C_old via messaging integration |
| Change enum/event type | Consumer switch-case may fail | Message contracts and consumer tests |
| Change serializer/schema version | Incompatible deserializers | Message/wire-level tests |
| Switch HTTP to HTTPS/mTLS | Clients lack trust/client certificates | Separate HTTP/TLS integration tests |

**A contract describing only data types without semantics** can PASS even when real behavior changed. Therefore, the matrix must tie together contract scenarios and consumer assertions, not just schema snapshots.

## 15. Message Contracts Need a Matrix Too

For message-driven integration:

~~~text
Order Service 2.5.0
    -- ORDER_PAID --> Shipping Service 3.1.0
~~~

A contract might describe:

~~~yaml
description: "Paid order emits ORDER_PAID"
label: order_paid
input:
  triggeredBy: markTestOrderAsPaid()
outputMessage:
  sentTo: orders.events
  body:
    eventType: ORDER_PAID
    orderId: ORD-1001
    schemaVersion: 2
  headers:
    correlationId: CORR-TEST-1001
~~~

This is a **DSL example**; `markTestOrderAsPaid()` must exist in the producer base test and emit a real message; it is not executed by consumer Stub Runner.

Matrix components match HTTP, yet evidence scope must also address:

- Did the producer actually emit the event to the logical destination?
- Do message body, headers, and schema version match the contract?
- Can old consumer versions read the new event schema?
- Did the suite use a fake binder or a real broker? Were real topics/queues/routing keys verified?
- Does the consumer handle duplicates, out-of-order events, or retries if required?

**A passing message contract does not automatically prove exactly-once, ordering, retention, retries, or DLQs.** When those properties govern whether two versions can coexist, run separate integration tests and attach them to the corresponding evidence.

## 16. Matrices May Need Extra Dimensions Beyond P × C

A 2D grid is easy to read, yet real environments have more variables:

~~~text
(P_version, C_version,
 contract_revision, stub_digest,
 protocol/schema, feature_flags,
 environment, config_profile)
~~~

Do not build an unwieldy eight-dimensional table. Practical approach:

- Maintain a **2D `producer × consumer` table** for fast decision-making.
- Link each cell to a **complete record** holding flags, protocols, schemas, configs, and artifacts.
- If two profiles behave differently and both require support, create **cell/scenario variants** or a dedicated matrix for that profile.
- Never extrapolate `C_new over HTTP` results as proof for `C_new over HTTPS with mTLS`.

Example:

| P | C | Profile | Stub | Status |
| --- | --- | --- | --- | --- |
| 2.5.0 | Checkout 1.8 | default HTTP | 2.5.0:stubs | Sample PASS |
| 2.5.0 | Checkout 1.8 | strict JSON | 2.5.0:stubs | NOT_RUN |
| 2.5.0 | Checkout 2.0 | HTTPS/mTLS | 2.5.0:stubs + TLS test | NOT_RUN |

If production consumers run the `strict JSON` profile, a PASS in the default cell **does not substitute** for the strict JSON cell.

## 17. Every Combination Needs Trustworthy Evidence Sources

A `PASS` cell should include at least:

1. **Producer commit + build ID** that executed generated producer tests.
2. **Contract revision** that generated tests and stub mappings.
3. **Test report** confirming producer tests executed without unexpected skips.
4. **Pinned stub artifact coordinates**, `stubs` classifier, and checksum computed from actual bytes.
5. **Consumer commit/version** executed.
6. **Stub Runner resolution logs** or metadata proving the consumer loaded the exact artifact.
7. **Consumer test report**, scenario list, and results.
8. **Timestamp, profile, and configuration** recording test conditions.
9. **Support/release decision** and status computed from evidence rather than entered manually.

A helpful self-check question: **if someone else had only that cell's record, could they pinpoint the exact code, contracts, artifact, and test run used?**

If not, the matrix is merely a memo table, not auditable release evidence.

## 18. Reusing Producer Verification Across Consumer Tests

You do not need to re-run **the exact same producer contract test suite** per consumer version if all of them use **the exact same immutable stub artifact** from **the exact same verified producer build**.

Example:

~~~text
Producer P2.5:
  source commit abc123
  contract revision def456
  verification run producer-7824 = PASS
  stub artifact SHA-256 = H_P25

Consumer C1.8:
  consumer run checkout-8812 uses H_P25 = PASS

Consumer C2.0:
  consumer run checkout-8813 uses H_P25 = PASS
~~~

Both cells `P2.5 × C1.8` and `P2.5 × C2.0` can **reference the same producer verification record and stub checksum**, while requiring **separate consumer runs** for each version.

This eliminates duplicate work without sacrificing traceability. However, whenever producer code or contract revision changes, old verification results may be reused only if source/artifact identity demonstrably still matches.

## 19. Never Use Stale Stubs to Paint a False Green

Common reasons a matrix gets mislabeled:

| Situation | Why Evidence Is Wrong or Insufficient |
| --- | --- |
| Checkout 1.8 PASSES with `P2.4:stubs`, reported PASS for P2.5 | Did not use the new stub |
| Producer P2.5 tests PASS yet stub JAR was built from P2.4 | Mismatched contract/build |
| Stub coordinate `2.5.0-SNAPSHOT` with no checksum logged | Different bytes may have been downloaded |
| Consumer tests run against hand-copied WireMock mappings | May diverge from verified producer artifact |
| Test runner reports 0 tests | No real consumer assertions ran |
| Generated producer tests skipped | Implementation was never verified |
| Only happy-path GET 200 PASSES | Missing error/other semantic coverage |
| CI checks only that stub server started | Consumer logic was never exercised |
| New consumer works with new producer yet rollback untested | Missing `P_old × C_new` if rollback can occur |
| Reports PASS from historical run before code changed | Stale evidence relative to release candidate commit |

Whenever an outcome looks suspicious, compare **producer/contract revisions**, **stub checksums**, **consumer revisions**, and **run IDs** before tweaking DSL matchers.

## 20. Release Gate: Deciding from Mandatory Cells

For a producer upgrade, the release gate can be modeled as:

~~~mermaid
flowchart TD
    A["Identify target producer + still-supported consumers"] --> B["Build required P × C pairs"]
    B --> C["Target producer contract verification"]
    C --> D{"PASS, zero skips, exact contract revision?"}
    D -->|No| X["BLOCK"]
    D -->|Yes| E["Publish immutable stub artifact + checksum"]
    E --> F["Run required consumer versions against new stub"]
    F --> G{"All required cells PASS?"}
    G -->|No| X
    G -->|Yes| H["Verify rollback/rolling pairs"]
    H --> I{"Coexisting pairs verified?"}
    I -->|No| X
    I -->|Yes| J["Archive evidence and evaluate deploy"]
~~~

**Fundamental rule:** a producer release must never be marked "proven compatible with all supported consumers" while any **required cell** is `FAIL`, `NOT_RUN`, `BLOCKED`, or `STALE`.

Of course, an organization may have a **formal risk-acceptance process** for emergency deployments. Even then, record the decision, accountable approver, blast radius, and remediation plan; **never falsify a PASS status**.

### Status Evaluation Algorithm (Pseudocode)

~~~text
requiredCells = fetch list of P × C requiring support at release

for each cell:
    if missing producer verification:
        cell = BLOCKED
    else if stub provenance mismatches producer build:
        cell = STALE
    else if consumer test did not execute:
        cell = NOT_RUN
    else if assertions FAIL:
        cell = FAIL
    else:
        cell = PASS

if any required cell != PASS:
    releaseCompatibility = NOT_VERIFIED
else:
    releaseCompatibility = VERIFIED_WITHIN_DECLARED_SCOPE
~~~

This snippet is a **logical model**, not an official Spring Cloud Contract API. In practice, condition order and states can be expanded to distinguish infrastructure failures from contract failures.

## 21. How Does CI Build the Matrix?

A typical pipeline needs two inputs:

1. **Producer target release** and its producer-verified stub artifacts.
2. **List of mandatory consumer versions**, sourced from support policies, deployment inventories, and rollout/rollback plans.

Example **team-designed input matrix file**:

~~~yaml
# This is NOT a default Spring Cloud Contract config file.
release_target:
  producer: order-service
  version: "2.5.0"
required_consumers:
  - service: checkout-service
    version: "1.8.0"
    reason: "currently in production"
  - service: checkout-service
    version: "2.0.0"
    reason: "upcoming deployment version"
  - service: sales-portal
    version: "4.1.0"
    reason: "currently in production"
rollback_pairs:
  - producer: "2.4.0"
    consumer: "checkout-service:2.0.0"
~~~

A pipeline can:

1. Verify the producer build/contract revision and build stub artifact `2.5.0:stubs`.
2. Compute/record checksums post-packaging and verify the repository copy.
3. For each mandatory consumer version, check out its exact Git tag/commit, load stub `2.5.0`, and run consumer integration tests.
4. For rollback pairs, load verified stubs of the old producer version and run the matching new consumer version.
5. Reconcile reports, resolved-artifact logs, and scenario coverage.
6. Generate the compatibility matrix and attach evidence links per cell.
7. Block publish/rollout or route to risk acceptance if any required cell is missing.

A consumer can test against **multiple producer versions** by passing versions via configuration rather than duplicating test classes per version.

### Separating Configuration from Business Code

A consumer `RestClient` can receive the stub base URL via config:

~~~yaml
orders:
  api:
    base-url: "${ORDER_STUB_BASE_URL:http://localhost:8090}"
~~~

Each matrix job picks the right stub version and exports `ORDER_STUB_BASE_URL` for the consumer app. Never hard-code `2.5.0` or port `8090` inside business code just for tests.

If the consumer uses Feign/DiscoveryClient rather than a static URL, configure Spring Cloud Stub Runner and service-ID mapping properly; the matrix cell must record how routing was tested.

## 22. Checking Out the Exact Consumer Source Version per Cell

A common mistake: naming a CI job "checkout 1.8" while still checking out `main` of Checkout 2.0. That provides zero evidence for C1.8.

For each cell, record:

~~~text
Producer stub coordinate: order-service:2.5.0:stubs
Consumer source:          checkout-service tag/v1.8.0
Consumer resolved commit: cde789...
Test run:                 checkout-ci-8812
Resolved stub digest:     H_P25
Result:                   PASS/FAIL
~~~

If tags are mutable, record the actual **commit SHA** checked out. For better reproducibility, lock test dependencies/toolchains matching that consumer source version.

**Never patch consumer 1.8.0 code to call methods introduced in 2.0.0** and still label it a test of production 1.8.0. If an external test harness is needed outside the old consumer repo, document the harness version and real logic executed so you do not inadvertently alter the behavior under test.

## 23. Simulated Scenario Outcomes and Decision-Making

Suppose the team populates cells with **illustrative** statuses:

| Combination | Illustrative Status | Interpretation |
| --- | --- | --- |
| P2.4 × Checkout 1.8 | PASS | Legacy baseline within test scope |
| P2.5 × Checkout 1.8 | FAIL | New producer may break old consumer |
| P2.4 × Checkout 2.0 | PASS | New consumer supports rollback to old producer |
| P2.5 × Checkout 2.0 | PASS | Target state works |
| P2.5 × Sales 4.1 | NOT_RUN | Missing evidence for a still-active consumer |

If producer P2.5 plans to deploy immediately while Checkout 1.8 and Sales 4.1 remain in production, the default decision is **insufficient evidence for a safe rollout**.

Reasonable next steps:

1. Identify why `P2.5 × Checkout 1.8` FAILED; e.g., P2.5 removed `status`.
2. Apply a transition strategy keeping `status` temporarily or upgrading the old consumer first.
3. Re-run producer tests after fixing producer/contracts and publish a **new stub from the exact build**.
4. Re-run Checkout 1.8 against the new stub; never keep the stale PASS report from an older build.
5. Run Sales 4.1 against stub P2.5 or confirm sufficient grounds to drop that pair from support.
6. Verify rollback pairs if C2.0 is deployed.
7. Record the updated matrix and evidence before making a release decision.

**A PASS cell for Checkout 2.0 never compensates for a FAIL cell on Checkout 1.8** while 1.8 remains a supported consumer.

## 24. Which Results Can Be Reused?

Certain evidence may be reused when **the subject under test has not changed**:

| Evidence | Reusable When | Not Reusable When |
| --- | --- | --- |
| Producer verification | Identical producer build, contract revision, and test scope; matching stub bytes | Producer code/contracts changed |
| Stub checksum | Identical artifact file bytes | JAR rebuilt or overwritten |
| Consumer test report | Identical consumer commit/config, stub digest, scenarios, and matching environment | Consumer or stub changed |
| Historical matrix baseline | For comparison/regression reference | As a substitute for testing a new release |
| Load/performance or TLS integration tests | While scope assumptions hold and policy allows | When relevant runtime/server/transport changed |

Cases like "same semantic version yet different commit or different JAR" are usually **insufficient** to reuse evidence without additional verification.

## 25. Asynchrony and Deployment Order Complicate Matrices Further

In HTTP, one request normally receives one response. In event-driven architectures:

- A new producer may emit `schemaVersion` 2 while an old consumer understands only version 1.
- Topics may hold **lingering old messages** after the producer upgrades.
- A new consumer may receive events emitted by an old producer or older queued events.
- A producer rollback may resume emitting old schema events while the new consumer is already deployed.
- Duplicates, ordering, retries, and DLQs can govern the safety of a version transition.

Hence, a message-based matrix may require an extra dimension:

~~~text
Producer event version × Consumer handler version × In-flight schema versions
~~~

A test triggering only the new event and seeing the new consumer process it **does not prove** it handles older queued message versions properly. If rollout requires that, add matching scenarios and integration tests.

**Spring Cloud Contract message stubs** simulate contracted event payloads/headers, yet do not fully simulate production broker semantics.

## 26. Avoiding "Green" Matrices of Low Value

Items to audit:

| Issue | Symptom | Fix |
| --- | --- | --- |
| Wrong version pair | CI job labeled P2.5 yet Stub Runner ID uses P2.4 | Inspect resolved artifacts |
| Tests never executed | Reports 0 tests or skipped | Fail gate, inspect test runner |
| Unprovenanced stub | Hand-copied JAR | Attach contract revision/producer build/checksum |
| Weak assertions | Asserts only HTTP 200 | Assert consumer logic and critical fields |
| Missing error scenarios | Tests happy path only | Add 400/404/5xx and timeouts per need |
| Consumers omitted | Tests only Checkout latest | Pull list from support/deployment inventory |
| Same version, different bytes | Repo allows overwrites | Immutable artifacts and hash checks |
| Rollback untested | Tests only `P_new × C_new` | Run `P_old × C_new` when rollback is possible |
| Feature-flag mismatch | CI runs flag OFF, prod runs flag ON | Record and test mandatory profiles |
| Mock infra differs from prod | Stub PASSES yet TLS/broker/routing fails | Dedicated integration tests, document limits |
| Stale matrix | Links to run before latest commit | Check SHA/version/run ID per cell |
| Production data in fixtures | Fixtures hold tokens/PII | Replace with synthetic data |

A PASS cell is never an absolute guarantee; it is a **scoped, point-in-time result**.

## 27. Practice Exercises

### Exercise A — Identify Cells to Execute

Producer Order runs `2.4.0` and is upgrading to `2.5.0`. Checkout `1.8.0` is in production, Checkout `2.0.0` is preparing to deploy, and producer rollback is possible.

**Task:** build a 2 × 2 matrix, explain why each cell must run, and list minimum evidence.

**Hint:** cover both `P_new × C_old` and `P_old × C_new`, not just `P_new × C_new`.

### Exercise B — Old Stub Creating a False PASS

CI reports "Order 2.5 × Checkout 1.8 PASS", yet Stub Runner logs show `order-service:2.4.0:stubs`.

**Task:** correct the cell status, identify missing evidence, and propose re-execution steps.

**Hint:** that result does not apply to P2.5; fetch the new stub tied to P2.5 producer verification and re-run consumer version 1.8.

### Exercise C — Does Adding a Field Break Compatibility?

Producer 2.5 emits both `status` and `paymentStatus`. An old consumer uses a deserializer rejecting unknown properties.

**Task:** explain why it can still FAIL, and what test is needed?

**Hint:** test `P2.5 × C_old` using the exact old consumer code and JSON settings.

### Exercise D — Rollback After Consumer Upgrade

Checkout 2.0 deployed reading only `paymentStatus`. Producer Order 2.5 hits an operational incident and must roll back to 2.4 (`status` only).

**Task:** identify the missing matrix cell and a safe consumer upgrade pattern.

**Hint:** `P_old × C_new`; Checkout 2.0 may need to read both old and new fields during transition.

### Exercise E — Create an Evidence Manifest

Given:

~~~text
Producer commit: abc123
Contract revision: def456
Producer CI run: 7824 (PASS)
Stub artifact: com.example.orders:order-service:2.5.0:stubs
Consumer: checkout-service 1.8.0 @ cde789
Consumer CI run: 8812 (PASS)
~~~

**Task:** design a record for this matrix cell, listing additional missing fields that CI must measure for real.

**Hint:** artifact SHA-256, repository, generated tests executed/skipped, scenario IDs, resolved stub bytes, and test report URLs.

### Exercise F — How Does `NOT_RUN` Differ from `FAIL`?

Cell Sales Portal 4.1 × Order 2.5 failed to execute because remote repository credentials expired.

**Task:** choose the cell status and release decision if Sales Portal remains mandatory.

**Hint:** `BLOCKED` or `NOT_RUN` per convention; missing evidence, not proof of incompatibility. Fix repository access and re-run.

### Exercise G — Avoiding Matrix Explosion

There are 12 historical producer versions and 25 consumer versions. The organization supports only the three latest producer versions and consumer versions active within the past 60 days.

**Task:** define how to select policy-required cells, record exclusion rationales, and document residual risk.

**Hint:** prioritize coexisting combinations, rolling/rollback pairs, active APIs, and consumers unable to upgrade together.

### Exercise H — Message Compatibility

Order 2.5 emits `ORDER_PAID` schemaVersion 2; Shipping 3.0 reads both versions 1 and 2, while Shipping 2.9 understands only version 1. The broker still holds some version 1 events.

**Task:** list additional cells and message scenarios to verify.

**Hint:** new producer with old consumer, new consumer with in-flight old events, schema/headers/destination, and matching broker tests.

## 28. Matrix Checklist Before Release Decisions

- [ ] Clearly identified producer service/version and consumer service/version for every cell.
- [ ] Defined both directions: **P_new × C_old** and **P_old × C_new** when rollout/rollback applies.
- [ ] Confirmed active/supported consumer list rather than testing only `latest`.
- [ ] Every cell holds `PASS`, `FAIL`, `NOT_RUN`, `BLOCKED`, `SKIPPED`, or an approved exclusion rationale.
- [ ] Never marked `NOT_RUN`, `BLOCKED`, or `STALE` as PASS.
- [ ] Recorded producer Git commit and artifact contract revision.
- [ ] Generated producer contract tests actually generated, compiled, and PASSED.
- [ ] Zero `0 contract tests` runs or unapproved skips.
- [ ] Stub JAR was built from the exact contract/build that passed producer verification.
- [ ] Stub coordinates include complete group/artifact/version/classifier with pinned version.
- [ ] Artifact checksum computed from the final JAR and verified post-publish where needed.
- [ ] Consumer Stub Runner actually resolved the exact artifact/checksum, not an older build.
- [ ] Consumer source commit/tag matches the exact version claimed by the matrix cell.
- [ ] Consumer tests include business assertions and appropriate scenario coverage.
- [ ] Critical error cases, boundaries, and protocol/message schemas evaluated.
- [ ] Feature flags, client serialization profiles, and test environments recorded in evidence.
- [ ] Canary/rolling-deploy/rollback scenarios included in required cells where possible.
- [ ] `UNSUPPORTED` or `NOT_APPLICABLE` cells carry supporting rationale and evidence.
- [ ] Matrix refreshes whenever producer/consumer/contract/stub digest changes.
- [ ] Pairs lacking sufficient evidence are blocked or routed through authorized risk acceptance.
- [ ] Compatibility results are stated **within exact scope**, without claiming beyond what contract tests prove.
- [ ] CI reports retain complete links to producer reports, consumer reports, artifacts, and revisions for auditability.

## Conclusion

A **version matrix** is not merely a checklist of "which versions are green." It is an evidence dossier describing **which producer–consumer pairs can coexist**, **which stubs were tested**, and **what evidence confirms both producer implementation and consumer behavior**. With Spring Cloud Contract, a trustworthy cell links **Groovy/YAML contracts**, **generated producer tests**, **stub artifacts with explicit versions/checksums**, **Stub Runner**, and **consumer assertions**. When those links remain intact in CI, teams catch incompatible API changes before rollout rather than discovering them after production consumers fail.

**Key Takeaway:** *Missing evidence for a combination means its compatibility is unknown; PASSING with an old stub never proves compatibility with a new producer.*
