# Review Conventions and Change Acceptance Criteria

## Lesson objectives

In **Spring Cloud Contract**, producer and consumer can agree on HTTP or messaging behavior using **Groovy/YAML DSL**. The tool generates producer-side tests, packages stub artifacts for consumers to use with **Stub Runner**, and integrates checks into CI. Yet tooling solves only part of the problem: **who is allowed to edit contracts, who must review, and what evidence is required to accept a change?**

This lesson belongs to the **Team Coordination** chapter, designed for systems with multiple consumers, multiple concurrently deployed versions, and teams that do not release at the same time.

After this lesson, you will be able to:

- Define responsibilities of the producer team, consumer team, contract owner, and release approver.
- Write change proposals/PRs describing before/after behavior, impact analysis, migration, and rollback.
- Classify compatible, conditional, or breaking changes for HTTP/message contracts.
- Define **testable acceptance criteria**, not just "does not affect consumers".
- Require the right evidence: generated producer tests, stub GAV/checksums, Stub Runner, and consumer tests per version.
- Organize reviews, deprecations, and cross-team conflict resolution without hiding failing or unexecuted tests.

## 1. Why do contracts need review conventions?

Suppose **Order Service** returns JSON:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

**Checkout Service** relies on `status` to allow fulfillment. The Order team wants to rename this field to `paymentStatus`:

~~~json
{
  "id": "ORD-1001",
  "paymentStatus": "PAID"
}
~~~

To the producer, this might look like renaming a DTO property. To Checkout, removing `status` can be a **breaking change**. If the producer runs only its own unit tests, Checkout can still break after deployment. If Checkout mocks hand-written JSON that the producer never verified, consumer tests can still PASS against behavior the real producer never provides.

~~~mermaid
flowchart LR
    A["Consumer expects<br/>status = PAID"] --> C["Agreed contract"]
    B["Producer implementation"] --> PT["Generated producer tests"]
    C --> PT
    C --> S["Stub artifact"]
    S --> CT["Stub Runner + consumer tests"]
    PT --> E["Producer evidence"]
    CT --> F["Consumer evidence"]
    E --> R["Review/release decision"]
    F --> R
~~~

A **reviewed contract** is a specification of observable behavior that parties agree to protect: HTTP method, path, headers, body, status, data types, semantics, message destinations, and event schemas where needed. It does **not** force the producer to expose database structure or internal implementation details.

The goal of the review process is catching risks **before rollout**, not discovering bugs after production consumers stop working.

## 2. Terms to agree upon

| Concept | Meaning |
| --- | --- |
| **Producer** | Service implementing the contracted HTTP API or emitting the contracted message |
| **Consumer** | Application calling the API / receiving the message and depending on producer behavior |
| **Contract** | Groovy/YAML DSL describing verifiable behavior |
| **Contract owner** | Team/role governing contract conventions, quality, and history |
| **Change proposal** | Change proposal with rationale, scope, impact, and transition plan |
| **Review** | Process of checking semantics, compatibility, test data, and evidence |
| **Approval** | Authorized sign-off; distinct from passing tests |
| **Acceptance criteria** | Concrete, observable/testable conditions to accept a change |
| **Producer verification** | Results of generated contract tests running against producer implementation |
| **Stub artifact** | Stub bundle generated from contracts, usually with classifier `stubs` |
| **Consumer verification** | Results of consumer tests running against the exact stub bundle |
| **Release gate** | Gate blocking merge/publish/rollout when mandatory conditions are unmet |
| **Deprecation** | Notice and schedule to end support for an old behavior/interface |

**Approval does not replace testing.** A reviewer clicking "Approve" does not prove every running consumer version remains compatible. Conversely, a test PASS against the wrong stub version does not prove the change proposal was accepted by stakeholders.

## 3. Assigning responsibilities across teams

An authorization/responsibility model might look like this:

| Activity | Producer team | Consumer team | Contract owner | Release/CI owner |
| --- | --- | --- | --- | --- |
| Propose new behavior | Propose or challenge | State real need | Guard spec standards | Consulted |
| Identify producer code paths | **Accountable** | Consulted | Review scope | Does not replace developers |
| Identify fields/events consumer needs | Consulted | **Accountable** | Aggregate dependencies | Support inventory |
| Review DSL and compatibility | Co-review | Co-review | **Guard conventions** | Check automation |
| Generated producer tests | **Execute** | Monitor | Verify evidence | Operate CI |
| Stub generation/publishing | **Execute** | Consume right build | Track provenance | Control publish |
| Consumer tests with new stub | Support | **Execute** | Track coverage | Operate CI |
| Rollout/rollback decision | Co-participate | Co-participate | Record decision | Per release authority |

This is a **workflow suggestion**, not built-in Spring Cloud Contract permissions. Organizations may use RACI or other formats, as long as each change has **one final accountable person** and a consumer feedback path.

### Do not treat the producer as a unilateral decision-maker

- The producer confirms **which behaviors it can implement** and proves the implementation.
- Consumers confirm **which behaviors they genuinely use**, avoiding locking contracts to internal producer details.
- The contract owner oversees naming, matchers, review rules, and traceability.
- The release owner verifies gates and release authorization without assuming one green test resolves every risk.

If a producer has multiple consumers, maintain a list of owners and live versions. Asking only one familiar consumer does not guarantee batch jobs, mobile apps, or partners are unaffected.

## 4. Which contract source is the source of truth?

Contracts can be stored:

1. **In the producer repository**, e.g., `src/test/resources/contracts`.
2. In a **separate contract repository** with shared pull-request rules.
3. In a **Maven contract dependency** resolved by builds by version.

No single model is mandatory for every system. However, review conventions must specify:

- The **actual path** Contract Verifier will read.
- The **repository and revision** of contracts.
- Who has authority to review/approve DSL changes.
- Which revision producer CI is using.
- Whether the stub artifact is generated from the **exact same revision** as producer tests.
- From which artifact/repository consumer CI fetches stubs.

Example layout:

~~~text
order-service/
└── src/
    └── test/
        └── resources/
            └── contracts/
                └── orders/
                    ├── get_paid_order.yml
                    ├── get_missing_order.yml
                    └── create_order.yml
~~~

A PR should specify **contract path and commit**, not just filename `get_paid_order.yml`, because duplicate filenames may exist across modules or repositories.

If contracts live in a separate repo, **the producer Git commit does not substitute for the contract Git commit**; record both and lock the corresponding dependency.

## 5. Review observable behavior rather than implementation

An HTTP YAML contract:

~~~yaml
description: "Get paid order"
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

Reviewers should ask:

- Do URL, HTTP method, and status match the agreement?
- Are headers and content type important to consumers?
- Is `PAID` an official enum or merely a sample string?
- Are error scenarios that consumers depend on also covered?
- Is fixture `ORD-1001` synthetic data rather than production data?
- Are dynamic values like IDs/timestamps controlled via fixtures or appropriate matchers?
- Does the base test for generated producer tests genuinely invoke the producer code to verify?
- Will stubs generated from this contract be fetched by consumers using the exact artifact/version?

**Do not stuff every internal entity attribute into the contract** if consumers do not use it. At the same time, do not use overly broad matchers like `any string` for enum `PAID` when Checkout branches on that exact enum.

## 6. Classify changes before reviewing

| Change | Initial assessment | What must be verified |
| --- | --- | --- |
| Add new endpoint | Usually compatible | Route conflicts, authorization, new consumer |
| Add optional response field | Conditional | Strict JSON parsers may reject unknown fields |
| Remove or rename response field | Usually breaking for dependent consumers | Every consumer using the old field |
| Change number to string | Usually breaking | Schemas/deserializers and calculations |
| Change HTTP status 404 to 200 | Potentially breaking | Consumer error-handling branches |
| Add required request header | Usually breaking | Older consumers not yet sending the header |
| Change semantics while keeping field name | Potentially severely breaking | Consumer business logic and assertions |
| Change event type or enum | Potentially breaking | Message handlers, switch-cases |
| Change message destination/topic | Potentially breaking | Subscribers stop receiving events |
| Change `schemaVersion` / content type | Potentially breaking | Consumer deserialization |
| Add optional message header | Conditional | Adapters/schemas/header filters |
| Refactor internal controller/service method, keeping API | Usually non-impacting | Producer contract tests guard against regressions |
| Change retry/ordering/delivery guarantees | Requires additional testing | Out-of-contract broker/integration behavior |

**"Usually compatible" does not mean "PASSED".** If a consumer uses strict deserialization, even adding one response field can break it.

A change proposal can be tagged `additive`, `behavioral`, `breaking`, or `deprecation`; those labels are **review-process metadata**, not built-in Spring Cloud Contract DSL fields.

## 7. Acceptance criteria must be specific and testable

A statement like "API does not affect consumers" is **insufficient** because it names neither consumers, versions, nor evidence.

A criterion can be structured in four parts:

| Component | Question |
| --- | --- |
| **Given** | Which producer/consumer versions, contract revision, and profile? |
| **When** | Which request/event or CI job is executed? |
| **Then** | Which behavior/response/consumer outcome must hold? |
| **Evidence** | Which test report, build ID, artifact checksum, and status prove it? |

Example:

~~~text
AC-PRODUCER-01
Given: Order Service 2.5.0, contract revision def456.
When: generated producer tests for get_paid_order run.
Then: response contains id, status, and paymentStatus with agreed values.
Evidence: producer CI run; skipped required tests = 0.

AC-CONSUMER-01
Given: Checkout 1.8.0 and stub Order 2.5.0:stubs.
When: Checkout calls GET /api/orders/ORD-1001 via Stub Runner.
Then: Checkout processes the PAID order without deserialization errors.
Evidence: consumer test report + resolved stub GAV/checksum.
~~~

This format is a **team-designed convention**, not a special Contract Verifier API.

### Acceptance criteria must define scope

- Which active/supported consumers must PASS?
- Which happy-path and error-path scenarios are mandatory?
- Which version combinations can arise during rolling deploys or rollbacks?
- Are any feature flags, client serialization modes, or message schemas changing?
- Which evidence is still missing and how are gaps handled?

You cannot sign off on the entire change based on one `HTTP 200` test if consumers depend on specific body fields, status enums, or error behavior.

## 8. Breaking change example and review strategy

Initially Order Service returns:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

The Order team proposes returning only:

~~~json
{
  "id": "ORD-1001",
  "paymentStatus": "PAID"
}
~~~

If Checkout 1.8.0 reads `status`, this is a breaking change for that consumer. Reviewers can propose **expand–migrate–contract**.

### Expand: keep the old field and add the new field

~~~json
{
  "id": "ORD-1001",
  "status": "PAID",
  "paymentStatus": "PAID"
}
~~~

Transition YAML contract:

~~~yaml
description: "Keep status while adding paymentStatus"
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

Generated producer tests must prove the **real producer** returns both fields; the new stub must reach consumer tests.

### Migrate: upgrade consumers on schedule

Checkout 2.0.0 can switch to reading `paymentStatus`, while temporarily supporting `status` if it might still call an old producer during rollback. Sales Portal/Analytics or other clients must also confirm how they use those fields.

### Contract: remove old behavior

Remove `status` only when:

1. No supported consumer still depends on it per inventory and evidence.
2. Any rollout/rollback combinations that could still occur have been tested.
3. Deprecation window and migration plan per policy are complete.
4. Producer tests and required consumer cells PASS with the new artifact.
5. Release decision explicitly records scope and limits.

**Adding fields must never be assumed safe by default**: an older consumer with a strict parser can still FAIL when `paymentStatus` appears in JSON, so real consumer testing is required.

## 9. Rules for reviewing Groovy and YAML DSL

Same idea expressed in **Groovy DSL**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Keep both status fields during transition"
    request {
        method GET()
        url "/api/orders/ORD-1001"
        headers {
            header("Accept", "application/json")
        }
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: "ORD-1001",
            status: "PAID",
            paymentStatus: "PAID"
        )
    }
}
~~~

This is **Spring Cloud Contract** Groovy DSL, not direct producer test code. Generating/running tests requires compatible plugin and base test class configuration.

Reviewers check:

- Is there a real change in observable behavior?
- Are any matchers too weak or too strict?
- Are there unintended duplicate Groovy/YAML contracts for the same scenario?
- Are implementation details leaking into the DSL?
- Are there random fixtures making CI flaky?
- Does it generate stubs that consumers actually use?

**Both Groovy and YAML should not coexist for the same case** if that produces duplicate mappings and generated tests.

## 10. Do not overlook error contracts and negative cases

A PR touching only `GET /api/orders/ORD-1001 -> 200` may miss responses consumers depend on:

- `404` when an order does not exist.
- `400` on invalid requests.
- `409` on state conflicts.
- `401/403` on missing permissions.
- `429` or timeouts if consumers have an agreed retry policy.
- `5xx` and error body structures consumers parse.

Example 404 contract:

~~~yaml
description: "Order does not exist"
name: get_missing_order
request:
  method: GET
  url: /api/orders/ORD-NOT-FOUND
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: ORDER_NOT_FOUND
    message: "Order not found"
~~~

These values are an **illustrative business protocol**, not an SCC default error schema.

A 404 returned because WireMock found no matching stub **is not equivalent** to a producer committing to a specific 404 error schema. If a consumer requires body `code`, add the contract scenario and corresponding producer test.

## 11. Message contracts need dedicated review criteria

For messaging, changing **destination, event type, schema, or headers** can break subscribers even when HTTP APIs are untouched.

Example YAML message contract:

~~~yaml
description: "Successful payment emits ORDER_PAID"
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

Here:

- `triggeredBy` invokes a **producer-side** base test method.
- `sentTo` specifies the logical destination per configured messaging adapter.
- `body` and `headers` are the content consumers observe.
- `label` helps identify or trigger the message stub when integration supports it.

`label` is **not** a Kafka topic; `sentTo` does not automatically create a broker destination. Reviewers must understand how adapters/binders/brokers interpret that name.

### Questions message contract reviewers must ask

1. Is this an **event** that happened or a **command** asking the producer to act?
2. Do older consumers understand `schemaVersion: 2`?
3. Will changing `eventType` or `sentTo` cause subscribers to miss events?
4. Do headers commit to correlation ID / content type?
5. Might older messages still sit in the broker when new consumers deploy?
6. Do producer tests genuinely exercise the publish logic under test?
7. Do Stub Runner messaging consumer tests use the right label/artifact/version?
8. Do retries, ordering, DLQs, and idempotency need separate tests beyond contracts?

**A passing message contract does not prove** exactly-once semantics, delivery guarantees, retries, ordering, or real broker routing. If those belong to acceptance criteria, write separate integration tests and cite their evidence source.

## 12. Matchers, fixtures, and data must be reviewed

| Component | Recommended rule | Risk if missing |
| --- | --- | --- |
| Order ID | Appropriate format/type; synthetic data | Overly broad matcher |
| Status enum | Business-valid `PAID`/`PENDING` values | Consumer fails to recognize new enum |
| Amount | Numeric type, units, rounding | Uncaught currency or precision change |
| Timestamp | Agreed format/timezone | CI depends on clock/timezone |
| Optional field | Agreed absent/null/required rule | Parsing breaks on deletion/change |
| Error code | Specific value when consumer branches on code | Wrong business branch |
| Correlation ID | Format and input/output relation when needed | Regex only proves some string exists |
| Event destination | Right binding/route per adapter | Events arrive on wrong topic |

Use **synthetic** test data, avoiding production tokens or PII. If responses contain generated IDs or timestamps, control clocks/fixtures or use appropriate matchers rather than making expected bodies depend on unstable values.

Flaky generated tests erode trust in the review process. **Do not fix flakiness by turning every assertion into "any string"** if consumers rely on concrete invariants.

## 13. Producer-side criteria: genuine testing required

Producer-side acceptance criteria typically include:

| Criterion | Evidence |
| --- | --- |
| Contracts discovered | Logs/manifests from exact source root and revision |
| Generated producer tests created | Generated source/test metadata |
| Generated tests compile and **execute** | Test runner reports |
| Zero unintended skips | Skipped required tests equal 0 |
| Tests PASS on producer code | CI run ID and test reports |
| Base test genuinely triggers behavior | Fixture/code-path review |
| Stub mappings generated | Mapping files / scenario list |
| Stub JAR attached/published | Maven GAV/classifier + repository |
| Artifact contains no production data | Payload/header review/scan |
| Stub has provenance | Contract revision, producer commit, checksum |

**`BUILD SUCCESS` is insufficient** if tests were skipped or the plugin discovered zero contracts. Nor does a JAR named `-stubs.jar` prove by itself that it contains expected mappings.

### Illustrative producer record

~~~yaml
# Metadata built by team/CI; NOT default SCC output.
producer:
  service: order-service
  version: "2.5.0"
  commit: "abc123_FULL_COMMIT"
contracts:
  revision: "def456_FULL_COMMIT"
  required_scenarios:
    - get_paid_order_transition
    - get_missing_order
verification:
  run_id: "producer-ci-7824"
  generated_tests_executed: true
  skipped: 0
  failed: 0
  result: PASS
stub:
  coordinate: "com.example.orders:order-service:2.5.0:stubs"
  sha256: "CHECKSUM_FROM_REAL_ARTIFACT"
~~~

Record `PASS` only after CI reads actual results. Never replace placeholders with fabricated SHA-256 hashes.

## 14. Consumer-side criteria: must test against the exact new stub

Example consumer using Stub Runner:

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
class CheckoutContractIntegrationTest {

    @Test
    void checkoutHandlesPaidOrder() {
        // Point Checkout's real HTTP client to stub port 8090.
        // Invoke Checkout business logic and assert the outcome.
    }
}
~~~

This is an **illustrative skeleton**, requiring matching client/dependencies/assertions; the repository URL is also an example.

Reviewers must verify:

- **Consumer Git commit/version** matches the supported version, not substituting HEAD for an old release.
- **Stub Runner ID** targets the changing producer version, not an old one.
- **Artifact checksum** downloaded by the consumer matches the producer-verified artifact when tracing is needed.
- The real HTTP client points to the stub, not falling back to staging/production.
- Assertions check **consumer logic**, not merely that the stub server booted.
- Critical scenarios ran and reports are archived.

Consumer PASS with `order-service:2.4.0:stubs` **does not prove** compatibility with producer `2.5.0`.

## 15. Version matrix is part of the review

Suppose:

~~~text
P_old = Order 2.4.0
P_new = Order 2.5.0
C_old = Checkout 1.8.0
C_new = Checkout 2.0.0
~~~

Combination table:

| Producer × Consumer | Why needed? |
| --- | --- |
| `P_old × C_old` | Current baseline |
| `P_new × C_old` | Upgrading producer while old consumer still runs |
| `P_old × C_new` | Consumer upgrades first or producer rolls back |
| `P_new × C_new` | Target state |

When multiple consumers exist, add columns/required pairs for Sales Portal, Analytics, Shipping, or supported partner clients.

### Status per cell

| Status | Meaning |
| --- | --- |
| `PASS` | Producer verification and consumer tests completed for exact pair within scope |
| `FAIL` | Tests executed and failed |
| `NOT_RUN` | Not yet tested |
| `BLOCKED` | Could not run due to infra, dependencies, permissions |
| `STALE` | Old results do not match new revision/artifact |
| `UNSUPPORTED` | No longer supported under an evidence-backed policy |
| `NOT_APPLICABLE` | Combination cannot coexist with a clear reason |

**Never count `NOT_RUN`, `BLOCKED`, or `STALE` as PASS.** An untested required pair is an evidence gap, not a sign of safety.

## 16. Recommended PR review and release gate flow

~~~mermaid
flowchart TD
    A["Propose API/event change"] --> B["Describe before/after and consumer impact"]
    B --> C["Review contract DSL + semantics"]
    C --> D["Update producer code and fixtures"]
    D --> E["Generate/run generated producer tests"]
    E --> F{"Producer PASS and all required scenarios?"}
    F -->|No| X["BLOCK / revise PR"]
    F -->|Yes| G["Generate, inspect, lock stub artifact"]
    G --> H["Consumer CI runs right versions against new stub"]
    H --> I{"Required consumer tests PASS?"}
    I -->|No| X
    I -->|Yes| J["Review migration, rollout, rollback"]
    J --> K{"Sufficient approvals and evidence?"}
    K -->|No| X
    K -->|Yes| L["Merge/Release per policy"]
~~~

This is a **recommended workflow**, not a mandatory SCC pipeline. Gates must be wired into the organization's real CI tooling.

### Step 1 — Change proposal

The author presents rationale, before/after behavior, producer version, consumers needing protection, data model, and breaking risks.

### Step 2 — Contract review

Teams align on Groovy/YAML DSL, matchers, error cases, semantics, message destinations, and deprecation plans if needed.

### Step 3 — Producer verification

CI executes generated producer tests on the exact producer commit and contract revision, without skipping mandatory checks.

### Step 4 — Stub packaging

Produce the `stubs`-classifier artifact, verify mappings, version, and checksum, and publish to a governed repository.

### Step 5 — Consumer verification

Required consumer versions run via Stub Runner against the **new stub** with business assertions.

### Step 6 — Decision

Reviewers and the release owner inspect the compatibility matrix, exceptions, remaining risks, and rollback plan before approving release.

## 17. Change proposal PR template

This is a **text template**, not a Contract DSL file:

~~~markdown
## Goal
- Interface: Order Service — GET /api/orders/{id}
- Rationale: separate paymentStatus from generic status
- Classification: conditional additive during transition phase

## Before / After behavior
- Before: returns status
- After (expand): returns status and paymentStatus
- Final: consider removing status only when evidence suffices

## Affected consumers
- Checkout 1.8.0: currently uses status
- Checkout 2.0.0: planned to use paymentStatus
- Sales Portal 4.1.0: needs parser verification
- Other clients: inventory/owner contact verification needed

## Contract and producer
- DSL path and revision: ...
- Producer commit/build: ...
- Generated producer test reports: ...
- Stub GAV/classifier/checksum: ...

## Acceptance criteria
- [ ] Producer tests execute and PASS, zero skips
- [ ] Stub artifact matches revision and contains all mappings
- [ ] Checkout 1.8 PASSES with new stub
- [ ] Checkout 2.0 PASSES with new stub
- [ ] Sales Portal verified or holds valid exception
- [ ] Rollback combinations evaluated
- [ ] No sensitive production data included

## Rollout
- Order: ...
- Deprecation window: ...
- Rollback criteria: ...
- Monitor owner: ...

## Review/Decision
- Producer reviewer: ...
- Consumer reviewers: ...
- Contract owner: ...
- Release owner: ...
- Status: DRAFT / ACCEPTED / BLOCKED
~~~

Self-checked boxes are not evidence. Attach CI run links and real metadata with an appropriate retention policy.

## 18. Sample CI-measured acceptance criteria

A **separate** governance file can define mandatory cells:

~~~yaml
# Not a default Spring Cloud Contract configuration.
change_id: "ORDER-API-2026-017"
producer:
  service: order-service
  target_version: "2.5.0"
required_consumer_cells:
  - consumer: checkout-service
    version: "1.8.0"
    stub_version: "2.5.0"
  - consumer: checkout-service
    version: "2.0.0"
    stub_version: "2.5.0"
  - consumer: sales-portal
    version: "4.1.0"
    stub_version: "2.5.0"
gates:
  generated_producer_tests: required
  stub_provenance: required
  consumer_tests: required
  rollback_review: required
~~~

Pipelines use this config to **execute and gather results**, never treating author-typed `required` or `true` strings as PASS proof.

Example evidence for one cell:

~~~yaml
# Illustrative example only of information to collect.
producer_commit: "abc123_FULL_COMMIT"
contract_revision: "def456_FULL_COMMIT"
producer_ci_run: "producer-ci-7824"
producer_tests: PASS
stub_coordinate: "com.example.orders:order-service:2.5.0:stubs"
stub_sha256: "SHA256_COMPUTED_BY_CI"
consumer: "checkout-service:1.8.0"
consumer_commit: "cde789_FULL_COMMIT"
consumer_ci_run: "checkout-ci-8812"
resolved_stub_sha256: "VERIFIED_SHA256"
consumer_tests: PASS
compatibility_scope: "GET paid/missing order"
~~~

SHAs and build IDs are placeholders, not proof of a real build. Release gates require values computed from actual job artifacts/reports.

## 19. Merge gates differ from release gates

Some organizations allow merging draft contracts or feature-flagged changes **before** releasing. Others auto-deploy on merge. Clarify explicitly:

| Scenario | Review decision |
| --- | --- |
| Unagreed DSL draft | Do not treat as accepted behavior |
| Producer generated tests FAIL | BLOCK per quality gate |
| Test suite skipped or 0 required tests | BLOCK for missing evidence |
| Stub artifact wrong revision/version | BLOCK because consumer tested wrong artifact |
| Required consumer FAILS with new stub | BLOCK or authorized exception process |
| CI failed to run due to repository outage | `BLOCKED`, do not conclude compatibility |
| Consumer retired with evidence | May remove from required set per policy |
| Documentation-only edit with no behavior impact | May use a lighter review tier |
| Sensitive production data put into stub | BLOCK and handle security incident |

If merging triggers auto-deploy, the merge gate must meet full release-gate criteria. If releasing is a separate step, require **release evidence** and never assume an old PR review remains valid after newer commits.

**Exceptions do not turn a FAIL test into PASS.** If releasing with missing evidence is unavoidable, document the decision, accountable owner, risk scope, monitoring, and rollback.

## 20. Rollout and rollback must be reviewed

A system may go through:

~~~text
T0: P_old + C_old
T1: P_new + C_old
T2: P_new + C_new
Producer rollback: P_old + C_new
~~~

Even when `P_new × C_new` PASSES, `P_old × C_new` can FAIL if the new consumer only understands the new field while the old producer does not supply it.

Reviews must consider:

- Service deployment ordering.
- Whether rolling/blue–green/canary deploys create mixed versions.
- If the producer rolls back, can the new consumer still run?
- Do feature flags produce multiple response/event shapes?
- Can the new consumer process older messages still in the broker?
- Is there a deadline and owner for retiring the old API/event?

If a pair is declared **unable to coexist**, provide evidence from orchestration/rollout policies rather than ignoring it as "not in the main plan".

## 21. Cross-team notification rules

Spring Cloud Contract **does not impose a deadline** for consumers to respond to reviews. Organizations must agree on reasonable timelines per change type.

A workflow:

1. Author opens a proposal **before** removing fields, endpoints, or changing topics.
2. Contract owner notifies consumer owners from the inventory.
3. Consumers confirm dependencies, scenarios, and migration schedules.
4. For breaking changes, hold a joint review to choose versioning or a transition roadmap.
5. If a reviewer has not responded, status stays **PENDING/BLOCKED**—never treat silence as consent.
6. After building the new stub, consumer CI jobs run across the matrix.
7. Update changelogs/deprecation notices and record release decisions in writing.

With external clients, the consumer list may be incomplete. Enforce API versioning, deprecation windows, privacy-respecting telemetry, and representative test suites; **never declare all consumers PASS** when unverified.

## 22. Resolving conflicts: producer needs to change, consumer is not ready

For example, the producer wants to drop `status` immediately, yet old Checkout stays in production for two more weeks.

A collaborative review can:

- Producer states technical rationale and cost of maintaining both fields.
- Consumer supplies code paths/tests proving dependency and upgrade schedule.
- Contract owner compares compatibility options.
- Release owner evaluates rollback, business impact, and risk acceptance accountability.
- Parties record the decision and exit criteria for the transition phase.

| Option | Suitable when | Caveat |
| --- | --- | --- |
| Keep both fields temporarily | API can be extended easily | Needs tests and deprecation deadline |
| Version endpoints `/v1`/`/v2` | Large schema/semantics shift | Must maintain routes and support policy |
| Consumer adapter | Can handle both schemas | Must test both old/new data |
| Parallel message event/topic | Subscribers cannot upgrade together | Needs routing/broker integration tests |
| Feature flag/canary | Controlled rollout exists | Test both flag ON/OFF when supported |
| Defer breaking change | Mandatory consumer cannot migrate yet | Record blocker and revisit later |

**Never edit a contract just to legitimize new producer output** if consumers have not agreed to the behavior change.

## 23. Ensuring evidence stays traceable

~~~mermaid
flowchart TD
    A["Contract path + revision"] --> B["Producer commit + CI build"]
    B --> C["Generated producer test reports"]
    A --> D["Stub mappings"]
    C --> E["Stub JAR GAV + checksum"]
    D --> E
    E --> F["Artifact repository"]
    F --> G["Consumer Stub Runner resolved artifact"]
    G --> H["Consumer commit + CI test report"]
    H --> I["Acceptance decision and scope"]
~~~

A trustworthy record captures:

- Contract repository, path, and commit.
- Producer source commit and generated producer test CI run.
- Stub coordinate `groupId:artifactId:version:stubs` and SHA-256.
- Repository where the artifact was published.
- Consumer Git commit/tag and resolved stub checksum.
- Consumer test reports/scenarios.
- Review decision and supported teams/versions.

**A checksum identifies bytes, not a digital signature.** If publisher authentication and tamper resistance are required, add attestations/signatures per supply-chain policy.

Never include tokens, private keys, or real production data in reports, contracts, or stub JARs.

## 24. Diagnosing CI FAIL reports

If consumer tests FAIL against a new stub, check layer by layer:

1. **Artifact identity:** Were the right GAV/version/classifier downloaded?
2. **Provenance:** Did the JAR come from the verified contract revision and producer build?
3. **Runtime:** Is Stub Runner running and is the client hitting the right port/service ID?
4. **HTTP matching/message routing:** Did method/path/headers/body or destination change?
5. **Consumer behavior:** Does an older version rely on removed behavior?
6. **Producer implementation:** Which code paths did generated tests actually run and verify?
7. **Classification:** Real breaking change, fixture bug, flaky test, or CI infrastructure issue?
8. **Resolution:** Keep compatibility, upgrade consumer, version endpoint/event, or fix tests if expectations were wrong.
9. **Fresh evidence:** After fixing, re-run required producer and consumer tests; never reuse old reports.

### Common root causes

| Symptom | Cause | Action |
| --- | --- | --- |
| Producer tests PASS yet consumer FAILS | Consumer expects out-of-contract behavior or breaking change | Inspect scenarios and agreements |
| Producer tests never appear | Plugin/contract root or skip flags | Block gate, fix build |
| Stub Runner only loads old version | Version/cache/repository | Pin version and checksum |
| Stub server returns 404 | Request mismatch or wrong server | Check mappings and client URL |
| Messaging test misses event | Wrong destination/adapter | Verify binder and routing |
| Test alternates PASS/FAIL | Fixture/clock/concurrency | Make tests deterministic |
| CI fails to download artifact | Credentials/network | `BLOCKED`, do not conclude compatibility |
| Old consumer code yet test code changed | Test no longer reflects production version | Run matching consumer source/behavior |

**Never rewrite Checkout 1.8.0 tests to mimic Checkout 2.0.0 behavior** and still cite those results as proof the new producer is compatible with live Checkout 1.8.0.

## 25. What contract review cannot prove on its own

A properly scoped review conclusion should never claim "100% safe". Spring Cloud Contract does not prove by itself:

- Every endpoint was documented and tested.
- Every production consumer version was included in the matrix.
- Production TLS, authentication, and authorization are correct.
- Broker exactly-once, ordering, DLQ, retries, or retention are verified.
- Performance, throughput, latency, and failover meet requirements.
- Artifact repositories were not overwritten unless checksums/provenance are verified.
- Rolling deployments are always safe without testing coexisting versions.

An evidence-backed conclusion states:

> "Order Service 2.5.0 at commit abc123 PASSED generated producer contract tests for revision def456. Stub 2.5.0:stubs with recorded checksum was exercised by Checkout 1.8.0 and 2.0.0 via Stub Runner for scenarios get_paid_order/get_missing_order; required tests PASSED. Consumers and scenarios outside this list remain unverified."

This is an **illustrative phrasing example**, not confirmation of an actual executed pipeline.

## 26. Hands-on exercises

### Exercise A — Write acceptance criteria

Order wants to switch `status` to `paymentStatus`, yet Checkout 1.8.0 remains in production.

**Task:** write at least five acceptance criteria with concrete tests/evidence before removing `status`.

**Hint:** producer tests, new stub artifact, Checkout 1.8, Checkout 2.0, rollout/rollback, deprecation state.

### Exercise B — Review missing error scenario

A PR has contract `GET /api/orders/ORD-1001 -> 200`. Checkout depends on body `404 ORDER_NOT_FOUND`.

**Task:** write a review comment and propose an additional contract scenario.

**Hint:** HTTP 404 with explicit body/schema and both producer/consumer tests.

### Exercise C — Silent consumer

Sales Portal has not responded to a breaking change notice within the internal deadline.

**Task:** should this be treated as approved? What escalation or evidence is needed?

**Hint:** no; status PENDING/BLOCKED, locate owner, verify dependencies, and record risk decision.

### Exercise D — Skipped tests

Maven reports `BUILD SUCCESS`, yet zero generated contract tests appear in the test report.

**Task:** evaluate whether evidence is sufficient for release.

**Hint:** not yet; inspect plugin executions, contracts root, test runner, and skip flags.

### Exercise E — Consumer using wrong stub version

Checkout 1.8 PASSES with `order-service:2.4.0:stubs`. Producer prepares to release 2.5.0.

**Task:** which cell is unverified and how to fix the pipeline?

**Hint:** `P2.5 × C1.8`; pin stub 2.5.0 and verify the resolved checksum.

### Exercise F — Message destination changed

Producer changes `sentTo("orders.events")` to `sentTo("orders.events.v2")` while Shipping still subscribes to the old destination.

**Task:** classify the breaking change and write migration acceptance criteria.

**Hint:** parallel publishing or versioned events, verify consumers and routing, consider backlogged messages.

### Exercise G — Missing rollback pair

New Checkout reads only `paymentStatus`. Old producer returns only `status` and may be rolled back.

**Task:** name the matrix pair requiring testing and a safe consumer design approach.

**Hint:** `P_old × C_new`; support both fields during transition.

### Exercise H — PR template

Design a PR template for Order, Checkout, Sales Portal, and Analytics.

**Task:** include before/after, consumer inventory, DSL paths, producer evidence, stub version/checksum, consumer matrix, deprecation, and approvals.

**Hint:** use the template in Section 17 and record actual status per cell.

### Exercise I — Overly broad matcher

Generated producer tests FAIL due to a dynamic timestamp. A reviewer wants to replace the ISO-8601 UTC assertion with "any string".

**Task:** why does this fail consumer acceptance criteria?

**Hint:** control the clock or use a matcher constraining the agreed format/timezone.

### Exercise J — Exception during repository outage

A mandatory consumer could not run because the remote artifact repository returned 503; business wants to release immediately.

**Task:** pick the status, who must accept risk, and what must be recorded?

**Hint:** `BLOCKED`, not PASS; authorized decision, risks, monitoring, rollback, and re-run plan.

## 27. Review checklist before accepting a change

### Scope and responsibilities

- [ ] Change proposal clearly states need, before/after behavior, and risks.
- [ ] Producer, consumers, contract owner, and release owner are identified.
- [ ] List of still-supported consumers is verified.
- [ ] Relevant consumers have a clear review channel and response deadline.
- [ ] Silence is never treated as consent.
- [ ] Migration/deprecation plan exists if needed.

### Contract quality

- [ ] Groovy/YAML DSL accurately describes observable behavior.
- [ ] HTTP method/path/status/headers/body or message input/output are explicit.
- [ ] Matchers protect semantics consumers genuinely rely on.
- [ ] Happy path and mandatory negative/error scenarios are present.
- [ ] Test data is synthetic, containing no production secrets/PII.
- [ ] No unintended duplicate contract scenarios exist.
- [ ] Fixtures are deterministic, avoiding flaky tests.

### Producer verification

- [ ] Contracts are fully discovered at the right revision.
- [ ] Generated producer tests are generated, compiled, and executed.
- [ ] Zero required tests skipped and no unintended zero test counts.
- [ ] Producer tests PASS against the implementation to be released.
- [ ] Stub JAR has the right classifier/version and complete mappings.
- [ ] Producer commit, contract revision, CI run, and checksum are recorded.
- [ ] Results from a different producer build are never reused to validate a new stub.

### Consumer verification

- [ ] Stub Runner uses the exact new GAV/classifier/version.
- [ ] Source repository and checksum verified where needed.
- [ ] Consumer source matches the version still under support.
- [ ] Tests hit the right stub server/adapter with business assertions.
- [ ] Required consumer matrix cells PASS.
- [ ] `NOT_RUN`, `BLOCKED`, and `STALE` are never recorded as PASS.
- [ ] Rollout/rollback and residual old message schemas considered if applicable.
- [ ] Consumer reports trace back to producer verification.

### Decision

- [ ] Authorized approver is identified.
- [ ] Required release gates executed, or any exception has a transparent decision.
- [ ] Rollout/rollback, observability criteria, and remediation steps are clear.
- [ ] Scope and limits of contract testing evidence are documented.
- [ ] No silent breaking changes published to supported consumers.

## Conclusion

**Review conventions** help teams agree on who can propose changes, who must participate, which semantics to review, and how to handle disagreements. **Acceptance criteria** turn that agreement into measurable conditions: generated producer tests genuinely execute and PASS, stub artifacts carry clear provenance, relevant consumer versions PASS against the **new stub**, and rollout/rollback plans are evaluated.

In Spring Cloud Contract, review does not end when a Groovy/YAML file merges; it ends when there is **a decision backed by version-accurate, properly scoped evidence**.

**Remember:** *Approval does not replace testing; passing against an old stub does not prove a new producer is compatible; and a change is only accepted when impacted consumers have a verified transition path.*
