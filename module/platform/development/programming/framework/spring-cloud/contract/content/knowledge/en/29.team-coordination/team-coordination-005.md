# Evolving Contracts and How to Prevent False Verification

## 1. Context: "green tests" does not mean "both teams agree"

In a microservices system, a **producer** exposes HTTP APIs or emits messages, while a **consumer** calls or processes those interactions. **Spring Cloud Contract (SCC)** lets teams describe behavior using **Groovy/YAML DSL**, from which it generates **producer verification tests**, builds **stub artifacts**, and lets consumers run **Stub Runner** for compatibility testing. When organized properly, these checks catch incompatible API changes before deployment.

However, when multiple teams evolve in parallel, a contract may be in a **proposed**, **unimplemented**, **unapproved by producer**, or **transitioning for backward compatibility** state. The dangerous case is when a pipeline reports PASS without having checked the right version, real code, or negotiated behavior. That is **false verification** (*false assurance / false-positive validation*): an "all safe" signal unsupported by adequate test evidence.

A realistic scenario in a retail system:

- The Checkout team wants the Inventory API to return an `available` field.
- The Inventory team plans to replace it with `inStock`.
- The Checkout team rewrites its local fixture/stub with the new field; tests with WireMock pass.
- The real producer implementation still returns only the old field, or runs against a different contract version.
- Checkout CI reports success, yet **proves nothing** about whether the two services can communicate after deployment.

Conversely, the producer could edit both code and contract at once: newly generated producer tests turn green, yet the currently running Checkout version can no longer parse the response. Both situations show the need for **technical and process coordination**, not just syntactically valid DSL.

This lesson belongs to the **Team Coordination** chapter and answers: **how should evolving contracts be managed, verified, and published to prevent false PASS states?**

### Learning outcomes

After this lesson, you will be able to:

1. Distinguish **proposed**, **approved**, **producer-implemented**, **stub-published**, and **consumer-verified** contract states.
2. Assign responsibilities among the producer team, consumer team, QA, and CI/repository owners.
3. Design a contract review workflow for both compatible and breaking changes.
4. Detect forms of false green: **self-written stubs**, **fake producers**, **skipped tests**, **overly broad matchers**, **stale artifacts**, and **weak assertions**.
5. Use SCC generated producer tests and Stub Runner to produce two **independent pieces of evidence linked to the same revision**.
6. Pin candidate artifacts by version/commit and inspect mappings and runtime logs rather than trusting a `BUILD SUCCESS` line alone.
7. Organize negative/mutation tests to prove the suite can turn red.
8. Establish release gates, ownership, compatibility matrices, and expand–migrate–contract workflows.

## 2. Three distinct questions that are often conflated

When told "the contract has been verified", ask clearly:

| Question | Appropriate evidence | Insufficient to prove |
|---|---|---|
| **Do both teams agree on behavior?** | Contract PR approved by owners/reviewers, semantics and migration documented | Valid YAML file or a single "LGTM" comment from one team |
| **Does the producer execute the committed behavior?** | Generated producer tests running against the **real implementation**, PASS with valid test count | Consumer test with a stub or a test base returning fake responses |
| **Can the running consumer understand the candidate behavior?** | **Real** consumer client/handler running against **stubs from the exact candidate**, asserting outcomes | Green producer tests or a consumer unit test using Mockito |

These three questions are related but **not interchangeable**. A contract may be agreed upon before implementation is done. An implementation may satisfy a new contract while breaking an old consumer. A consumer test may pass while Stub Runner is still downloading an old artifact.

A useful definition for teams:

> **A contract is verified for a version pair** when there is evidence that the producer candidate satisfies the contract and the supported consumer version properly processes stubs generated from **that exact contract candidate**.

This definition **does not equate to proving full production end-to-end safety**. Auth, networking, databases, broker topology, timeouts, concurrency, and operational quality still require other testing layers.

## 3. A running example: Inventory and Checkout

Suppose Checkout needs to query stock for SKU-123:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Contract **v1** specifies:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

The Inventory team wants to switch to **v2**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "inStock": true,
  "quantity": 12
}
~~~

If Checkout deserializes `available` into `Boolean available` and requires it to be non-null, removing this field can be a **breaking change**. Just looking at v2's reasonable-looking response does not reveal whether old Checkout can understand it.

A safer path is a **transition phase**:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "inStock": true,
  "quantity": 12
}
~~~

After legacy consumers upgrade and stop depending on `available`, the producer can consider removing that field per the deprecation schedule. However, **adding a new field is not always harmless either**: consumers using a strict unknown-property policy or closed schemas may fail. You must test **real consumers within the supported scope**.

This lesson uses this example to compare proposed contracts, producer tests, candidate stubs, consumer tests, and release gates.

## 4. Contract lifecycle states: a coordination convention, not built-in SCC states

A team should publish an easy-to-understand set of states:

| Proposed workflow state | Meaning | Who confirms? |
|---|---|---|
| **Draft** | Idea or draft contract, semantics not yet agreed | Proposer |
| **Proposed** | PR exists with API examples and consumer requirements | Consumer owner |
| **Reviewed** | Producer and consumer reviewed request/response, errors, versioning | Both sides |
| **Accepted** | Agreement on how the contract will work and migration milestones | API/contract owners |
| **Producer-verified** | Generated tests run on producer candidate code and pass | Producer CI |
| **Stub-published** | Candidate stubs artifact packaged with traceable provenance | Producer pipeline |
| **Consumer-verified** | Supported consumer versions run against exact candidate stub and pass | Consumer CI/owners |
| **Release-approved** | All gates and deployment constraints passed | Release owner |
| **Deprecated/Retired** | Legacy contract has a retirement plan and evidence of zero dependent consumers | API owner + consumers |

These are **team conventions**, **not a built-in status list in Spring Cloud Contract**. Do not invent these statuses inside a DSL schema if the tool does not support them; manage them via PR labels, tickets, external metadata, or release records.

Never flip a label from **Draft -> Verified** just because YAML parses cleanly or one consumer wrote a self-made stub and got green tests. Every state transition must carry **matching evidence**.

## 5. Ownership: who is responsible for what?

| Role | Primary responsibility | Should not do unilaterally |
|---|---|---|
| **Producer team** | Implement API/message, maintain generated producer tests, publish stubs matching implementation | Delete a field still used by consumers |
| **Consumer team** | State interface requirements, test real client/handler, warn on migration needs | Edit contract and assume the producer implemented it |
| **Contract/API owner** | Coordinate schemas, versioning, compatibility policy | Approve breaking changes without checking consumers |
| **QA/contract test maintainer** | Review coverage, mutations, negative tests, prevent zero-tests | Replace real code with mocks and declare production safe |
| **CI/repository owner** | Provide artifact identity, publish/read permissions, retention, traceability | Leave candidate SNAPSHOTs mutable or silently fall back |
| **Release owner** | Make rollout/rollback decisions from complete gates | Rely solely on a PASS lacking provenance |

One producer serves multiple consumers. Therefore, "consumer A accepted the new contract" **does not prove** consumers B/C remain compatible. Maintain a **list of supported consumers**, including versions running in production or deployed at customer sites if system policy requires.

## 6. Single source of truth for evolving contracts

There are several models for organizing contracts:

1. **Producer-owned contracts:** contracts live inside the producer repository; consumers submit PRs proposing behavior.
2. **Consumer-driven contracts:** consumers contribute contracts and producers verify them through an approval workflow.
3. **Shared contract repository:** both sides use one versioned contract source, accurately synced/consumed by CI.

No single choice fits every organization. Whichever model you pick, ensure:

- There is **one canonical revision** for a candidate/release.
- Everyone knows which contract commit/version applies.
- Contract PRs receive **producer + consumer review** when changing the interface.
- Generated producer tests and published stubs trace back to the **same revision**.
- Consumer tests use the **exact candidate stubs artifact**, not a manually tweaked local fixture.
- Two Groovy/YAML copies never silently diverge while both claim to be the same contract.

**Counter-example:** consumer saves its own `contracts/new-inventory.yml`, producer saves its own `contracts/old-inventory.groovy`, and both suites go green against their own fixtures. There is zero evidence the two sides are testing **the same agreement**.

## 7. Distinguishing "in progress" from "published"

A change may be described in DSL before it belongs in a stub artifact that other teams treat as stable.

For example:

~~~text
Contract PR A (draft):
  GET /api/inventory/SKU-123 -> {"inStock":true}

Current producer release:
  GET /api/inventory/SKU-123 -> {"available":true}
~~~

If Stub Runner automatically fetches `latest` or a SNAPSHOT from a development branch and consumer tests run with A, results may reflect **unimplemented APIs**. Conversely, consumer tests running against stable stub v1 cannot evaluate draft v2.

Recommended convention:

- **Draft/proposed:** for review, examples, and design; may generate **experimental** stubs, but must be labeled **unverified**.
- **Producer-verified candidate:** only after generated tests pass against producer implementation on the same commit can it become a **candidate compatibility artifact**.
- **Released:** passed compatibility gates and publication policy; immutable artifact, never overwritten.
- **Deprecated:** continues to be served throughout the committed migration window, not deleted merely because a new API appeared.

Never allow a consumer's experimental stub to be mistaken for a producer-verified artifact.

## 8. Separating design-assumption tests from compatibility-proof tests

A consumer may use a self-written stub to build a feature **before the producer finishes**. That is reasonable if labeled honestly:

| Test type | Data used | Valid conclusion |
|---|---|---|
| **Design/mock test** | Consumer-crafted future response | Client/UI can handle the assumption if the producer later provides it |
| **Producer contract verification** | Tests generated from contract, running real producer candidate | Producer implementation satisfies the agreement |
| **Consumer compatibility test** | Stubs from producer-verified contract, running real consumer client | Consumer is compatible with the specific artifact behavior |
| **Deployment/E2E test** | Real systems and infrastructure | Integrated behavior within the test environment scope |

A **design stub** is not bad; the mistake is **labeling it "contract verified"**. Establish a clear handoff gate: once the producer finishes, replace the design stub with **producer-published candidate stubs** and re-run the same consumer tests.

## 9. Two-team coordination flow from idea to release

~~~mermaid
sequenceDiagram
    participant C as Checkout Team
    participant P as Inventory Team
    participant R as Contract/Artifact Repository
    participant CI as Consumer CI
    C->>P: Propose inStock field + error cases
    P-->>C: Review semantics and compatibility
    C->>P: Agree on contract PR/revision
    P->>P: Implement + generated producer tests
    P->>R: Publish candidate stubs for exact commit
    R-->>CI: Exact artifact + provenance
    CI->>CI: Stub Runner + real Checkout client
    CI-->>C: Compatibility report PASS/FAIL
    C-->>P: Review failures/migration if needed
    P->>P: Release gate/rollout after passing
~~~

Every arrow needs an **artifact or piece of evidence**:

- Proposal: API examples, request/response, errors, owners, and deadline.
- Review: confirm field types, nullability, versioning, negative cases.
- Producer build: test reports with **executed contract tests > 0**.
- Publish: artifact coordinates + checksum + commit.
- Consumer CI: test report, client target URL, stubs version.
- Release: matrix of supported consumers, rollout/rollback, and deprecation plan.

## 10. Contract parts that must be agreed during review

An HTTP contract is more than a sample JSON body. Review checklist:

| Part | Questions |
|---|---|
| HTTP method/path | GET/POST? Are URL or path variables changing? |
| Query parameters | Required or optional? Default values/encoding? |
| Request headers | `Accept`, `Content-Type`, auth headers, and version headers? |
| Request body | Field names, JSON types, nullability, validation, defaults? |
| Success status | 200, 201, 202, 204, or another response? |
| Response headers | Content-Type, caching headers, correlation IDs? |
| Response body | Required fields, number/string, enums, timestamps, money format? |
| Error schema | Status + error code + message, retryability? |
| Compatibility | Are old fields preserved? Do old consumers understand new fields? |
| Idempotency | On POST retry, is a request idempotency key required? |
| Auth/security | Contracts do not implicitly verify the entire security topology |
| Messaging | Event name, destination, headers, key, schema version, retry/DLQ? |
| Dynamic data | Are matchers tight enough or accidentally accepting bad data? |

**Reviewing only one happy-path response is rarely sufficient.** A consumer can also break due to error code changes, HTTP 204 instead of 200, enum values, content types, or missing-data behavior.

## 11. Example of an incompatible candidate Groovy contract

Suppose both teams propose an API response containing only `inStock`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Inventory candidate checks SKU-123 stock'

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
            inStock: true,
            quantity: 12
        )
    }
}
~~~

This contract **does not prove by itself that the new producer code already returns `inStock`**. It is only a behavioral declaration. The producer must run generated tests against real code; if not yet implemented, generated tests must fail—the right signal preventing publication of a verified artifact.

Meanwhile, a consumer using DTO:

~~~java
public record StockResponse(
        String sku,
        Boolean available,
        Integer quantity) {
}
~~~

may parse the new body with `available == null`. If the consumer used primitive `boolean`, a missing field might default to `false` depending on Jackson config, masking the breaking change. Consumer contract tests should include **validation of required fields**, not just asserting HTTP 200.

## 12. Transition-phase YAML contract

A migration-friendly candidate can temporarily keep the old field while adding the new field:

~~~yaml
description: Inventory during field transition
name: inventory_stock_migration

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    inStock: true
    quantity: 12
~~~

Goals of the transition phase:

- Old consumers can still read `available`.
- New consumers can read `inStock`.
- Producer verification ensures **both fields** are present and consistent, if that is the agreed contract.
- Consumer compatibility matrix verifies versions still requiring support.
- Only after no consumer depends on `available` and the deprecation schedule is approved is removing it considered.

**Yet adding a field is not always compatible with every consumer:** some JSON deserializers are configured strictly against unknown properties. So **never just assume**—run consumer tests against candidate stubs.

## 13. Which changes commonly cause breaking changes?

| Producer change | Risk level | Required check |
|---|---|---|
| Add optional response field | Usually compatible | Consumer unknown-field policy |
| Remove/rename required field | **High** | Consumer DTO/validation |
| Change number to string | **High** | Strict serialization/deserialization types |
| Add enum value | Potentially breaking | Consumer unknown-enum handling |
| Change 200 to 204 | Potentially breaking | Does consumer require a body? |
| Change error code while keeping status | Potentially breaking | Consumer error mapping |
| Add required request header | **High** | Does consumer send the header? |
| Add required request body field | **High** | Do old consumers send the field? |
| Tighten input validation | **High** for old requests | Negative/request compatibility tests |
| Relax input validation | Usually easier to stay compatible | Security/business invariants |
| Change message event name/destination | **High** | Consumer binding/listener |
| Add field in message | Depends on schema policy | Schema evolution and converters |
| Change timestamp/locale/timezone semantics | **High** | Boundary time tests |
| Change authentication/version header | **High** | Security/integration tests |

There is no rule that "every added field is non-breaking" or "every version bump is breaking". Evaluate against **consumer contracts** and published compatibility policies.

## 14. False verification type A: consumer test using a self-written stub

A misleading kind of test:

~~~java
// Conceptual example: test stub configured by the consumer itself.
stubFor(get(urlEqualTo("/api/inventory/SKU-123"))
    .willReturn(okJson("""
        {"sku":"SKU-123","inStock":true,"quantity":12}
    """)));
~~~

If the Checkout client reads `inStock` and the test passes, the valid conclusion is:

> Checkout code is compatible with **the assumed self-configured response**.

The **invalid** conclusion is:

> Inventory producer has implemented and committed to that response.

To close the gap:

1. Place the proposal in the contract source/revision agreed by both teams.
2. Producer runs SCC generated tests against the real implementation.
3. Publish the stubs artifact from the **same revision** after producer tests pass.
4. Consumer re-runs its **real client** against that candidate artifact via Stub Runner.
5. Record results and provenance.

Self-written stubs can still help **TDD and design exploration**, but must be classified as **design tests**, not producer-confirming release gates.

## 15. False verification type B: producer verifier running on a fake implementation

In Spring MVC, the test base can be misconfigured:

~~~java
// Counter-example: fake controller returning the exact sample body.
@BeforeEach
void wrongSetup() {
    RestAssuredMockMvc.standaloneSetup(
        new FakeInventoryController()
    );
}
~~~

If `FakeInventoryController` returns the contract's exact JSON, generated producer tests can always stay green even when the production controller is broken.

The right target:

~~~java
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class InventoryContractBase {
    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Here, generated tests must actually exercise the **Spring context and production controller/service** that the contract protects. External dependencies may be substituted or data fixtures prepared, but **never mock the very behavior being published**.

**Control check:** intentionally change the implementation so `available` returns the wrong value; the generated producer test must turn red. If not, check the base test, mock beans, and executed test count.

## 16. False verification type C: skipped tests or zero generated tests

A build might show:

~~~text
BUILD SUCCESS
Tests run: 0
~~~

or run only unit tests unrelated to contracts. Causes:

- Maven plugin not activated or `contractsDirectory` points to the wrong path.
- Gradle plugin applied at parent/root instead of the producer module.
- Contract files not parsed/generated, yet the build does not fail per policy.
- JUnit version/test runner mismatched with generated Java.
- Surefire/Failsafe patterns miss generated test names.
- Tests skipped by `-DskipTests`, `-Dmaven.test.skip=true`, `-DskipITs`, Gradle exclusions, or profiles.
- Pipeline runs `mvn package`/`gradle build` with skip flags, then publishes stubs.
- Reports count only **total unit tests**, without checking **executed contract tests**.

A sound guard needs at least three pieces of evidence:

1. **Contract sources discovered > 0** if the producer module requires contracts.
2. **Generated producer test sources** appear and compile cleanly.
3. **Executed generated producer tests > 0**, with zero failures and no unintended skips.

Reference commands for a producer with the plugin configured:

~~~bash
# With Maven:
./mvnw clean verify

# With Gradle:
./gradlew clean test
~~~

These commands **do not prove by themselves** that tests executed; always inspect Surefire/Failsafe or Gradle test reports and generated sources. Do not run commands during authoring of this lesson.

## 17. False verification type D: overly broad matchers

A contract/stub checking only method/path while ignoring the request body can accept wrong requests.

Example of an **overly broad** WireMock mapping:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations"
  },
  "response": {
    "status": 201,
    "jsonBody": {
      "reservationId": "R-1001",
      "status": "RESERVED"
    }
  }
}
~~~

A consumer could send:

~~~json
{"productCode":"SKU-123","quantity":"2"}
~~~

while the producer requires:

~~~json
{"sku":"SKU-123","quantity":2}
~~~

Both requests still receive HTTP 201 from that broad mapping. The consumer test goes green, yet **never tested DTO serialization**.

A **tighter contract-aligned** mapping may require semantic JSON matching:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {
        "contains": "application/json"
      }
    },
    "bodyPatterns": [
      {
        "equalToJson": "{\"sku\":\"SKU-123\",\"quantity\":2}"
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "reservationId": "R-1001",
      "status": "RESERVED"
    }
  }
}
~~~

This is an **illustrative WireMock mapping**; SCC may generate different predicates depending on DSL/plugin version. Inspect the actual generated mapping rather than assuming the generator always emits `equalToJson`.

If the API allows dynamic data, use JSONPath/regex matchers **tight enough for types and value ranges**. Regex `.*` is not a meaningful constraint if an important field must conform to a pattern or format. Conversely, **do not over-constrain arbitrary values** such as request IDs or timestamps to the point of flakiness: matchers should protect **real commitments**, not unimportant internal details.

## 18. False verification type E: mocked consumer client

Example:

~~~java
// Counter-example: testing a business branch, not compatibility.
when(inventoryClient.getStock("SKU-123"))
    .thenReturn(new StockResponse("SKU-123", true, 12));

CheckoutPreview result = checkout.preview("SKU-123", 2);
assertThat(result.canCheckout()).isTrue();
~~~

This test can be useful for **orchestration unit testing**, yet never traverses the real HTTP client. Thus it misses:

- Client sending the wrong HTTP method/path/query;
- Incorrect `Content-Type`/`Accept` headers;
- JSON serialization renaming fields;
- Response deserialization mishandling nulls or wrong types;
- Misunderstood 404/503 error mappings;
- Which version Stub Runner is loading.

To qualify as a **consumer compatibility test**, keep the **production client** and replace the **producer runtime** with stubs. When using WebClient/RestClient/Feign or a message consumer, test the application's real adapter/handler.

**Principle:** mock **outside the consumer's HTTP/message boundary** when appropriate; never mock the very boundary being verified.

## 19. False verification type F: stale stub for a new contract

A very common pattern across multiple repositories:

~~~text
Inventory commit A:
  Contract A returns available
  Stubs JAR: inventory-service:1.3.0:stubs

Inventory commit B:
  Contract B returns inStock
  Stubs JAR: inventory-service:1.4.0-rc.pr173:stubs

Checkout CI:
  Still declares inventory-service:1.3.0:stubs
  Result: PASS
~~~

PASS here only proves Checkout is compatible with **A**, not B. Artifact B's coordinates must flow from the producer PR pipeline to the consumer job.

With mutable SNAPSHOTs, the issue is subtler:

~~~text
com.example:inventory-service:1.4.0-SNAPSHOT:stubs
~~~

Logical coordinates look identical, yet Maven metadata, local caches, repository proxies, or WireMock processes can cause the consumer to load a different version. Verify **resolved timestamp/digest/commit**, not just the SNAPSHOT name.

**Release gate recommendation:** use **unique candidate versions tied to commit/build** and configure the repository to forbid redeploying different bytes under the same coordinates. Never use uncontrolled `latest`/`+` to prove a specific PR was tested.

## 20. False verification type G: producer edits the contract to match buggy code

During an upgrade, the producer accidentally changes the response from `quantity:12` to `quantity:"12"`. A team might immediately change the contract to string to turn tests green without consulting consumers.

That is not merely "fixing a test"; it is **changing a public interface**. The proper workflow:

1. Determine whether the failure stems from an implementation regression or a genuine contract requirement change.
2. If the code is wrong: fix the code to satisfy the **accepted contract**.
3. If the API must change: open a **contract change proposal**, documenting rationale and migration.
4. Consumer owners review deserialization/validation impact.
5. Producer and consumer tests run against the same candidate.
6. The release gate opens only once the change is approved with compatibility evidence.

Never let one person edit expected responses to turn tests green without a **contract diff**, **review**, and **downstream impact check**.

## 21. False verification type H: testing only the happy path

An API may work on 200 yet fail on error scenarios:

~~~http
GET /api/inventory/SKU-404 HTTP/1.1
Accept: application/json
~~~

Contract business error:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"SKU_NOT_FOUND","message":"SKU does not exist"}
~~~

If the producer changes `code` to `ITEM_UNKNOWN` while the consumer still maps `SKU_NOT_FOUND`, HTTP status 404 **is not enough to declare compatibility**.

Risk-driven scenarios are needed:

| Scenario | Behavior to test |
|---|---|
| `200` in stock | DTO is right and required fields exist |
| `200` out of stock | False/zero is distinguished from missing/null |
| `404 SKU_NOT_FOUND` | Consumer returns a "SKU missing" error |
| `503 INVENTORY_UNAVAILABLE` | Consumer handles unavailable, not confused with not found |
| `422 INVALID_QUANTITY` | Validation response matches schema |
| Timeout/connection refused | Transport error is not turned into business 404 |
| Unmatched WireMock 404 | Not treated as business 404 |
| Duplicate message / unknown enum | Consumer behaves per policy |

**Not every network fault belongs in the standard contract artifact.** Contracts should capture behaviors the producer commits to; resilience/negative protocol cases may live in separate suites. What matters is not mistaking a happy-path PASS for evidence that every error path is handled.

## 22. Business 404 vs. unmatched WireMock 404

WireMock returns HTTP 404 when no mapping matches a request with a wrong path/header/body. That differs from a **business 404** from the contract.

| HTTP response | Cause | How the consumer should interpret it |
|---|---|---|
| 404 + `{"code":"SKU_NOT_FOUND"}` | Producer commits SKU does not exist | Domain NotFound |
| 404 + WireMock diagnostic body | Request did not match any stub | Test/protocol mismatch |
| 404 + another code | Different API error or wrong schema | Do not treat as `SKU_NOT_FOUND` |
| Connection refused | No HTTP response | Transport failure |
| 503 + `INVENTORY_UNAVAILABLE` | Producer/gateway reports unavailable per contract | Retry/fallback per policy |

If the client writes:

~~~java
// Counter-example: conflating every HTTP 404.
if (status == 404) {
    throw new InventoryNotFoundException("No stock");
}
~~~

then when the client sends the **wrong URL**, the test may silently translate it into "SKU not found" instead of failing on request mismatch.

In consumer tests, assert **status + error code + body** and, when needed, inspect WireMock's request journal/near misses to verify the request actually matched the contract.

## 23. Coordinate via contract PRs rather than scattered chat messages

A contract PR can use a description template:

~~~text
Title: Inventory response adds inStock, deprecates available

Owner: Inventory API team
Affected consumers: Checkout v3, Cart v2, Analytics v1
Proposed behavior:
  GET /api/inventory/{sku}
  200 JSON: sku, quantity, available, inStock

Existing behavior:
  200 JSON: sku, quantity, available

Compatibility:
  - Keep available during migration.
  - Do not remove it before supported clients migrate.

Error contract:
  - 404: SKU_NOT_FOUND
  - 503: INVENTORY_UNAVAILABLE

Producer verification:
  - Contract tests generated/executed: pending
  - Commit/revision: pending

Candidate stubs:
  - Artifact/version/digest: pending

Consumer compatibility:
  - Checkout v3: pending
  - Cart v2: pending
  - Analytics v1: pending

Rollout/rollback:
  - Deploy additive fields first.
  - Move consumers to inStock.
  - Remove available only after explicit approval.
~~~

The `pending` statuses in the PR reflect **missing evidence so far** and must not be replaced with PASS before jobs finish. Field names, consumer lists, and policies above are **examples**, not fixed SCC standards.

### What should PR review ask?

- Has the proposer specified the concrete **wire format**?
- Are there sample **requests** and **success/error responses**?
- Which consumers are impacted and which versions are they running?
- Have backward and forward compatibility been evaluated?
- Are there sufficient fixtures/producer states for generated tests to run **real code**?
- Was the candidate stub built from the same revision?
- Does CI prove supported consumer versions are compatible?
- Is the rollback plan feasible once the producer emits new messages/state?

## 24. Expand–migrate–contract: reducing breaking change risk

For renaming a field, a common sequence:

~~~mermaid
flowchart LR
    A["Expand: Producer adds inStock, keeps available"] --> B["Verify producer + consumers"]
    B --> C["Migrate: Consumers gradually switch to inStock"]
    C --> D["Monitor and confirm no consumer still uses available"]
    D --> E["Contract: End support for available per plan"]
    E --> F["Re-verify all supported consumers"]
~~~

### Phase 1 — Expand

The producer still returns `available` and adds `inStock` per reviewed semantics. Contracts are updated and generated producer tests guard both fields. Old and new consumers run against corresponding candidate stubs.

### Phase 2 — Migrate

Consumer teams upgrade DTOs/handlers and roll out incrementally. CI checks **both consumer candidates and still-running consumer versions** per policy. Monitoring/telemetry confirms adoption where possible.

### Phase 3 — Contract

Only when the deprecation window, consumer list, and migration criteria are met is `available` removed. Once removed, new generated producer tests guard the new interface; consumer tests must run against the **new stub**.

**Risk to manage:** for message brokers retaining older events, new consumers may still read messages written with the **old schema sitting in topics/queues**. Testing only new events is insufficient; examine backward/forward schema compatibility, replay, and retention.

## 25. Compatibility matrix for multiple consumer versions

One producer may serve multiple consumer versions:

| Producer candidate | Checkout v3 | Cart v2 | Analytics v1 | Conclusion |
|---|---|---|---|---|
| V1, field `available` | PASS | PASS | PASS | Currently supported |
| V2 additive, both fields | PASS | PASS | Expected PASS after testing | Can proceed if genuinely verified |
| V3, `inStock` only | PASS with new Checkout | FAIL with old Cart | Analytics not run | Not ready to drop field |

**PASS/FAIL values in the table are illustrative examples**, not a real project's test report. How to use the matrix:

1. List **supported consumer versions**, not just each repo's main branch.
2. Tie each column to a **specific consumer build/commit**.
3. Tie each producer row to a **specific candidate artifact**.
4. Run each consumer's real client/handler against the candidate.
5. Record status per cell: PASS, FAIL, NOT RUN, NOT APPLICABLE, BLOCKED.
6. Never convert **NOT RUN** into PASS.
7. Define policy: must every production consumer PASS, or only a supported subset under explicit terms?

The matrix exposes a classic hazard: the producer team tests against the latest Checkout yet skips Analytics v1 still running in production.

## 26. Control tests: introduce a wrong change to prove tests turn red

A valuable test suite must be **sensitive to the bugs it claims to guard against**.

### Producer control check

On a test branch, change the producer implementation from:

~~~java
return new StockResponse("SKU-123", true, 12);
~~~

to:

~~~java
// Intentionally wrong to test fault detection:
return new StockResponse("SKU-123", false, 12);
~~~

If the contract still commits to `available=true`, generated producer tests must fail. If tests stay green, check test counts, fake base classes, mocks, and test modes.

### Consumer control check

Keep the candidate stub, but change the path in the client:

~~~text
Right: GET /api/inventory/SKU-123
Wrong: GET /api/stock/SKU-123
~~~

Consumer tests must fail because the request does not match, rather than silently mapping an unmatched WireMock 404 to a business NotFound.

### Schema evolution control check

Have a producer candidate drop `available`; run the **old consumer** against the candidate stub. Tests must catch the missing required field or wrong behavior. If they pass, check primitive DTO defaults, assertions, and artifact identity.

### Cache/stub control check

Change a request/response fingerprint in the candidate and confirm the stub returns the new data; if the old response still appears, investigate caches, resolvers, or processes.

**Note:** perform mutations only on test branches/environments, never merge intentionally broken code; revert the mutation and re-run tests.

## 27. Protect tests with business-meaningful assertions

A test such as:

~~~java
assertThat(response).isNotNull();
~~~

is usually too weak to catch breaking changes. It does not prove quantity, availability, error mapping, or matching IDs.

For Checkout preview, verify:

~~~java
CheckoutPreview preview = checkout.preview("SKU-123", 2);

assertThat(preview.sku()).isEqualTo("SKU-123");
assertThat(preview.canCheckout()).isTrue();
assertThat(preview.requestedQuantity()).isEqualTo(2);
assertThat(preview.subtotalVnd()).isEqualTo(300_000L);
~~~

This snippet assumes `CheckoutPreview` exposes those accessors and is an **illustrative application type**, not an SCC API.

Assertions should reflect **what the consumer actually depends on**:

- Required fields exist and are non-null;
- Number/boolean/string retain exact types;
- Error codes map to the right domain exceptions;
- Responses match the requested ID/SKU;
- Price/quantity calculations make sense;
- Unknown enum/field policies are respected;
- Message handlers do not silently drop schema-invalid events.

Do not write assertions by copying the entire stub expected body into the test and comparing raw responses when the goal is verifying **consumer behavior**. Raw JSON comparisons can supplement, but real DTO/business logic must be exercised.

## 28. Messaging contracts: why is false verification even easier to trigger?

Spring Cloud Contract supports message contracts, e.g., a producer emitting `InventoryChanged`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')

        body(
            eventId: 'evt-demo-101',
            eventType: 'InventoryChanged',
            sku: 'SKU-123',
            available: true
        )
    }
}
~~~

For producer verification to be meaningful:

- Generated tests must call the **trigger method** from the base test or test support.
- The trigger must invoke **production application logic** that genuinely emits the message.
- The message verifier/test binder must receive the **output emitted by the producer**, not a payload constructed by the test itself.
- Destination/header/body matchers must reflect the interaction the consumer needs.
- Test timeouts and cleanup must be clean to avoid picking up stray messages from other tests.

**False verification:** `triggerInventoryChanged()` directly sends the sample JSON to a test sink without calling the business service. Generated tests pass, yet the producer runtime is unproven to emit that event.

The consumer side must also test the **real handler** deserializing the event and updating state/errors properly—not merely assert that a sample payload parses with an `ObjectMapper` unit test.

## 29. Limits that must be stated clearly when tests pass

Even with both producer and consumer gates passing, the following risks remain outside contract test scope:

| Layer | Why contract stubs are not enough | Additional testing typically needed |
|---|---|---|
| TLS, proxy, DNS, service discovery | Stubs typically run on localhost/test networks | Deployment/network integration |
| Authentication/authorization | Tests may bypass security filters or use test tokens | Security integration |
| Database state and transactions | Stub responses do not depend on a real DB | Producer integration/E2E |
| API performance/latency | WireMock responds instantaneously | Performance/resilience |
| Timeouts, retries, circuit breakers | Stubs do not simulate faults by default | Fault injection tests |
| Message broker topology | Message stubs do not prove real exchanges/partitions | Broker integration |
| Event ordering/duplicate delivery | A sample message does not prove distributed semantics | Messaging concurrency tests |
| Runtime config drift | Consumer test URL differs from production | Configuration validation |
| Compatibility across all versions | CI runs only the configured matrix | Consumer version inventory/support policy |

**Never claim a pair of contract tests guarantees the entire system is safe.** The accurate conclusion is **compatibility within the verified contract, versions, scenarios, and test environment**.

## 30. When contracts change fast: avoid turning review into a bottleneck

Development teams want fast feedback without abandoning review. A balanced workflow:

1. **Design preview:** consumer proposes Groovy/YAML and sample requests/responses with a temporary design stub; labeled unverified.
2. **Producer feasibility check:** confirm paths, schemas, validation, error cases, and implementation feasibility.
3. **Automated syntax/generation check:** CI ensures contracts parse and generated tests are created.
4. **Producer implementation PR:** code and contract belong to the same verified revision.
5. **Candidate artifact publication:** unique version, clear provenance, no mutable latest.
6. **Targeted consumer checks:** run affected consumers first; never omit in-scope production versions.
7. **Compatibility gate:** block if consumers fail or mandatory evidence is missing.
8. **Release coordination:** deploy additive producer before consumer migration, monitor, then remove deprecated fields after deprecation.

For fast feedback, run a **targeted group of affected consumers** based on API dependencies, then run the full matrix before release. However, the affected consumer list must be **sourced and kept up to date**, never guessed from the nearest repo.

Unrelated contract changes (such as adding a brand-new endpoint no consumer uses yet) may follow a different policy from breaking changes on production endpoints—provided the rules are **explicitly codified**, not ad-hoc gate skipping whenever the pipeline feels slow.

## 31. CI/CD gates to prevent evolving contracts from false verification

A CI workflow should clearly separate **design validation**, **producer verification**, and **consumer compatibility**:

~~~mermaid
flowchart TD
    A["Contract proposal / PR"] --> B["Review and breaking-change analysis"]
    B --> C["Producer code + contract same revision"]
    C --> D["SCC generates producer tests"]
    D --> E{"Generated tests executed > 0 and PASS?"}
    E -- "No" --> X["BLOCK or keep Draft"]
    E -- "Yes" --> F["Build candidate stubs JAR"]
    F --> G["Publish unique coordinate + commit + checksum"]
    G --> H["Consumer CI resolves exact artifact"]
    H --> I["Stub Runner loads candidate mappings"]
    I --> J["Real consumer client/handler runs tests"]
    J --> K{"Affected consumer versions PASS?"}
    K -- "No" --> X
    K -- "Yes" --> L{"Any unapproved breaking changes?"}
    L -- "Yes" --> X
    L -- "No" --> M["Release-approved"]
~~~

### Evidence at each gate

| Gate | Minimum requirement | What is insufficient? |
|---|---|---|
| **Contract review** | Producer + affected consumer owners review behavior | YAML/Groovy lint only |
| **Producer verification** | Generated tests run on real code, count > 0, pass | Generated files merely exist |
| **Artifact verification** | Stubs JAR has mappings/fixtures matching candidate revision | `-stubs.jar` filename exists |
| **Repository verification** | Immutable version or resolved snapshot identity, matching checksum | Untraceable `SNAPSHOT` / `latest` |
| **Consumer compatibility** | Real client/handler runs against candidate, business assertions | Mockito returning a sample response |
| **Release decision** | Compatibility matrix and migration policy satisfied | One random test suite turning green |

**Blocking on missing evidence** differs from blocking on test failures. Never treat `NOT_RUN` or `NO_ARTIFACT` as `PASS` just because of a transient network glitch or job timeout.

## 32. Transparent reporting: PASS must bind to an artifact pair

A record may have this structure:

~~~text
contractChangeId: INV-173
contractRevision: a1b2c3d4
contractStatus: Producer-verified
producerService: inventory-service
producerCommit: a1b2c3d4
producerArtifact: com.example:inventory-service:1.4.0-rc.pr173.a1b2c3d4:stubs
producerArtifactSha256: <verified digest>
producerContractTestsExecuted: <count of executed tests>
consumerService: checkout-service
consumerVersion: 3.8.2
consumerCommit: <SHA of tested consumer>
consumerContractTestsExecuted: <count of executed tests>
stubRunnerPort: <port in use>
stubMappingsLoaded: <mapping count>
result: PASS | FAIL | NOT_RUN | BLOCKED
reviewers: <producer owner + consumer owner>
migrationDecision: <approved decision>
~~~

Values in `<...>` are fields **to pull from CI**, never fabricated metrics. When using snapshots, add resolved timestamp/digest because a logical `-SNAPSHOT` name does not identify exact bytes.

Never collapse multiple consumer versions into one `PASS` line without corresponding per-version reports. Release decisions require knowing **who was tested against which artifact**, not just "the pipeline succeeded".

## 33. When producer and consumer disagree: resolve with contract diffs and evidence

Suppose the Inventory team wants to drop `available` to keep only `inStock`, while Checkout still needs the old field.

A coordination approach:

1. **Specify the contract diff**: which fields are added/removed/retyped? Before/after API examples?
2. **List consumers** using that field and their deployed versions.
3. **Evaluate backward compatibility**: can both fields be returned temporarily?
4. **Test with code**: run current consumer versions against the new candidate stub.
5. **Compare costs**: maintaining the field during a deprecation window vs. upgrading all consumers simultaneously.
6. **Agree on ownership and migration milestones**: who updates clients, who provides telemetry, who approves removal?
7. **Use feature flags or API versioning** if two behaviors must coexist.
8. **Never loosen matchers or delete assertions** just to turn red CI green without resolving the real interaction.
9. **Record technical decisions** in PRs/tickets rather than leaving requirements in private messages.

If compatibility cannot be kept and a breaking change is unavoidable, you may need a **new API version** or coordinated synchronized deployment with a rollback plan. However, synchronized deploys across microservices fail easily in distributed systems; avoid making them the default.

## 34. Distinguish schema changes from semantic changes

An API can keep its JSON identical and still introduce a breaking change.

For example, the producer always returns:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

Previously `available=true` meant "at least 1 unit left"; now the producer changes semantics to "enough stock for a default pack of 5". Old Checkout still parses the JSON, and tests checking only field presence may stay green.

To prevent **semantic drift** false verification:

- Contracts must have **meaningful scenarios** distinguishing behavior, not just one easy sample response.
- Use multiple request inputs or producer states, e.g., quantities 0, 1, 4, 5 and `available` per policy.
- Consumer tests assert **business decisions** (allow checkout or not) per scenario.
- Producer verification exercises real implementation logic rather than echoing sample bodies.
- Contract reviews document field **meaning**, units, defaults, rounding, timezones, idempotency, and edge cases.
- When semantics change, mark it as an **API behavior change** even if the wire format is unchanged.

**Schema compatibility does not equal semantic compatibility.** This is why teams must discuss business semantics, not just review JSON diffs.

## 35. Provider state: fixtures must reflect real producer behavior

A contract may describe:

~~~text
Given SKU-123 exists with quantity=12
When GET /api/inventory/SKU-123
Then 200 {available:true, quantity:12}
~~~

To make generated producer tests reproducible:

- Prepare data fixtures/DB state `SKU-123 quantity=12` via an appropriate test mechanism.
- Invoke the real production controller/service.
- Ensure query logic, mapping, and serialization all execute.
- Clean up data after tests; avoid execution-order dependencies.
- Use a fixed clock/test ID when responses contain timestamps or correlation IDs.
- When a real backend is out of contract scope, mock **minimal external dependencies**, never the business response itself.

**False verification:** the base test directly mocks `InventoryService.getStock()` to return the contract's `StockResponse`; generated tests only prove the controller serializes the mock to JSON, without testing inventory logic. A controller-only test may be acceptable if its scope is explicitly documented, but never call it complete proof of Inventory's real behavior.

## 36. Disagreements on failing tests: halt or grant an exception?

Sometimes an urgent deployment is mandatory even though a consumer compatibility test failed. An exception workflow must be **transparent and approved**, never disguising `FAIL` as `PASS`.

A minimal exception record:

~~~text
contractChange: INV-173
failedConsumer: analytics-service v1
failure: Renamed field available -> inStock
risk: Analytics v1 cannot deserialize the new response
decision: BLOCK / CONDITIONAL_WAIVER
approver: <authorized role name>
expiry: <when the exception expires>
mitigation: <dual-field response / API v2 / rollout flag>
rollback: <producer rollback plan>
followUp: <ticket + owner + deadline>
evidence: <test logs + candidate artifact digest>
~~~

If a waiver is granted, the final status must read **"approved to proceed with constraints"**, never disguised as "all consumer tests PASS". For financial, safety-critical, or high-risk systems, policy may demand **zero waivers** for breaking changes.

Above all, avoid "making the dashboard green" by disabling tests, skipping consumer v1, or editing contract expected bodies without recording the risk.

## 37. Contract quality metrics when multiple teams develop together

Useful metrics:

| Metric | What it tells you | Avoid misinterpretation |
|---|---|---|
| **Producer contract tests executed** | Are generated tests actually running? | High counts alone do not guarantee scenario coverage |
| **Consumer compatibility coverage** | How many supported consumer versions were tested? | Do not assume unregistered consumers are safe |
| **Candidate artifact provenance** | Share of runs with clear commit/version/digest | Checksum without comparing to producer is not enough |
| **Mutation detection rate** | Does the suite turn red on intentional code/request faults? | Useful mutations do not replace semantic reviews |
| **Contract breaking changes caught pre-release** | How many issues were caught early | Low counts may indicate weak tests |
| **Stale-stub incidents** | Are consumer runs using old/wrong artifacts? | Measuring build passes alone hides this |
| **Unreviewed contract changes** | Were interface changes merged without owner approval? | Casual "LGTM" from another team does not replace role review |
| **Deprecation lead time** | Do consumers get enough migration time? | Time elapsed does not prove consumers stopped using the field |
| **Flaky contract test rate** | Do tests depend on unstable clocks/networks/data? | Never delete tests without fixing root causes |

Do not optimize "% green tests" by dropping assertions or loosening request matchers. The most important KPI is **catching interface-breaking changes before users hit errors**.

## 38. Comprehensive case study: checkout breaks even though both pipelines are green

### Context

Inventory v1 returns:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

Checkout v3 uses `available` to decide whether ordering is allowed. Inventory v2 replaces it with `inStock`.

### What happened

1. The Inventory PR changes both code and contract simultaneously.
2. Generated producer tests v2 pass because they assert the new response.
3. Checkout runs tests against old `inventory-service:1.3.0:stubs`, which still exposes `available`.
4. Checkout tests pass because v3 code remains compatible with v1.
5. Inventory v2 releases returning `inStock` without `available`.
6. Checkout v3 fails to parse the missing field; with a primitive `boolean`, the value may default to `false`.
7. Users cannot place orders despite 12 units in stock.

### Where was the mistake?

Not necessarily in Groovy/YAML syntax or generated producer tests. The failure lay in **missing artifact linkage between the producer candidate and consumer verification**, compounded by assertions/validation that did not catch missing fields.

### How to fix the workflow

- Build candidate stubs v2 from the exact Inventory PR commit.
- Pass the exact coordinates/digest to Checkout CI.
- Run **supported Checkout v3** against candidate v2.
- Validate required fields instead of relying on primitive defaults.
- Wire compatibility results into the release gate.
- On failure, apply dual-field migration or appropriate API versioning.
- Remove `available` only after consumer migration completes.

### Proof that the fix works

Create a mutation intentionally omitting `available`, run old Checkout against the candidate stub, and verify the test **turns red** with the proper schema/behavior error. Then test the transition-phase contract containing both fields and verify it **turns green** when business logic aligns.

**Lesson:** two independent green pipelines **are not enough** unless they jointly verify the **real producer candidate and consumer version pair**.

## 39. Lab A — Propose a contract and prevent a design stub from being treated as verified

**Goal:** practice multi-team coordination when the producer has not finished implementation.

1. Checkout proposes adding `inStock`; opens a Groovy or YAML contract PR.
2. Document API examples, status codes, error schemas, and affected consumers.
3. Use a temporary design stub to develop consumer DTOs and business logic.
4. Label temporary tests/fixtures `UNVERIFIED DESIGN STUB`.
5. Inventory reviews and accepts the behavior or requests changes.
6. Once producer code is implemented, run generated producer tests against the real implementation.
7. Publish a commit-tied candidate stubs artifact with a digest.
8. Replace the design stub with Stub Runner using the candidate and run consumer tests.
9. Apply the release-approved label only after both producer and consumer gates pass.

**Evidence to store:** contract diff, review approval, generated producer test report, candidate coordinates/digest, and consumer results.

## 40. Lab B — Deliberately trigger four kinds of false greens

**Goal:** prove the test suite detects testing-process flaws, not just API bugs.

1. **Fake producer:** base test uses a fake controller returning the right body -> tests stay green. Swap in the real context and test a mutation to turn it red.
2. **Mocked consumer client:** mock `InventoryClient` returning a DTO -> tests stay green even with no stub running. Switch to the real client and verify HTTP calls hit Stub Runner.
3. **Overly broad matcher:** use a WireMock mapping matching only method/path -> wrong client request body is still accepted. Add contract body matchers and negative tests.
4. **Stale stub:** run old Checkout against the stable artifact after the Inventory candidate changed schema -> observe false PASS. Pass new candidate coordinates and observe failure.
5. Configure the runner so generated tests are not discovered (on a test branch) -> CI guard must block zero-tests.
6. Revert all intentional faults and re-run the main test suite.

**Evidence to store:** comparison of false PASS -> root cause -> test/gate fix -> expected FAIL -> PASS after fixing production behavior.

## 41. Lab C — Migrate a field without breaking consumers

1. Build a compatibility matrix with Checkout v3 and another hypothetical consumer like Analytics v1.
2. Producer implements `available` and `inStock` in parallel during the Expand phase.
3. Generate contracts and generated tests guarding both fields.
4. Publish uniquely versioned candidate stubs.
5. Old and new consumers run tests against the **same candidate**.
6. Analytics/Checkout update to read `inStock`, checking identical field semantics.
7. Record deprecation date and criteria permitting removal of `available`.
8. Once criteria are met, build a candidate with `inStock` only and re-run the compatibility matrix.
9. Decide to release or continue dual-field support based on results.

**Evidence:** matrix with PASS/FAIL/NOT_RUN, contract versions, stubs artifacts, test reports, and rollback plan.

## 42. Review and release gate checklist

- [ ] Is the contract Draft/Proposed or Accepted? Does the status have evidence?
- [ ] Have producer and affected consumer owners reviewed field types, semantics, and error cases?
- [ ] Is there one clear canonical contract revision with no diverging copies?
- [ ] Are generated producer tests **generated, compiled, and executed > 0**?
- [ ] Does the test base call the **real producer implementation** instead of faking contract responses?
- [ ] Does a producer mutation turn tests red when behavior is violated?
- [ ] Does the stubs JAR contain matching mappings/fixtures from the exact candidate revision?
- [ ] Is the artifact published with clear group/artifact/version/classifier and provenance?
- [ ] Are mutable SNAPSHOT/latest/uncontrolled `+` excluded from release gates?
- [ ] Does consumer CI download the exact candidate stub, checking version and digest?
- [ ] Does Stub Runner actually start with candidate mappings on the right host/port?
- [ ] Is the consumer's production client/handler tested rather than mocked at the boundary?
- [ ] Are request matchers strict enough for important fields/headers?
- [ ] Are there negative tests for bad requests, missing/mistyped schema fields, and business errors?
- [ ] Is a business 404 distinguished from an unmatched WireMock 404?
- [ ] Do consumer assertions reflect key business behavior rather than only not-null/status?
- [ ] Does the compatibility matrix include all consumer versions still under support?
- [ ] Are `NOT_RUN`/`BLOCKED` never treated as PASS?
- [ ] Do breaking changes have an expand–migrate–contract or versioning plan?
- [ ] Does migration have owners, deadlines, rollout, rollback, and deprecation policies?
- [ ] For message contracts, do triggers invoke production logic and verifiers observe real output?
- [ ] Are limits outside stub tests (auth, network, broker, performance) verified at the right layer?
- [ ] Do all waivers have approvals/risks/expiries without silently deleting logs or disabling tests?
- [ ] Do reports record commit, artifact, test counts, and release decisions?

## 43. Self-check questions

**1. Why is a consumer writing a WireMock stub and getting green tests not enough to prove the producer accepted the contract?**

Because the consumer is testing **assumed behavior**. You need a contract PR/review, generated producer tests running on real code, and a stubs artifact from a producer-verified revision.

**2. Do green generated producer tests prove older consumers remain compatible?**

No. The producer may have changed both code and contract; you must run **older consumers** against the new candidate stub.

**3. Why can a test count of 0 cause false verification?**

Because a pipeline can report `BUILD SUCCESS` even though zero assertions checked the API. Gates must verify contract discovery and executed generated tests.

**4. What is wrong with a WireMock matcher that only checks method and path?**

It can accept invalid request bodies/headers and still return a success response. The test fails to protect the serialization contract.

**5. Why are mutation tests needed?**

To confirm the test suite **actually fails** when protected behavior is intentionally violated, rather than always passing due to fakes, mocks, or weak assertions.

**6. How do Draft, Accepted, and Producer-verified contracts differ?**

Draft is only a proposal; Accepted has agreed semantics; Producer-verified has evidence that the real implementation satisfies the contract. These are **team workflow conventions**, not built-in SCC statuses.

**7. Is adding a new field to JSON always compatible?**

No. Strict consumer decoders may reject unknown fields, or the new field may alter semantics. Affected consumer versions must be tested.

**8. When a consumer cannot upgrade in time, can the producer delete the old field?**

Only under an approved compatibility/migration policy with testing and a breaking-change plan; normally delay removal or use API versioning/dual fields.

**9. Why must PASS bind to a producer commit and consumer version?**

Because a "PASS" for version pair A/X does not prove pair B/Y is safe. Artifact provenance and matrices prevent mix-ups.

**10. Are contract tests enough to guarantee production will never fail?**

No. They protect declared behaviors in a test environment. Networking, authentication, brokers, concurrency, and many runtime risks need additional testing.

## 44. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): producer/consumer contract testing, generated tests, and stubs.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML, HTTP/message behaviors, and matchers.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): downloading stubs JARs, LOCAL/REMOTE modes, artifact resolution.
- [Spring Cloud Contract — Maven](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): producer-generated tests and stub packaging.
- [Spring Cloud Contract — Gradle](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): plugin generation, test execution, and publishing.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): request matchers and near misses.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): response mappings and HTTP stub behavior.
- [Martin Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html): consumer-driven contracts and multi-team coordination.
- [Martin Fowler — Patterns of Distributed Systems](https://martinfowler.com/articles/patterns-of-distributed-systems/): coordination risks in distributed systems.
- [Pact Documentation — Provider Verification](https://docs.pact.io/provider): an additional reference for another consumer-driven contract verification approach; do not conflate Pact APIs with SCC.

**Note on versions and scope:** Annotation names, DSL methods, test mode configurations, publishing, and resolution mechanisms in Spring Cloud Contract vary by Spring Boot–Spring Cloud Release Train–SCC version. Governance states (Draft/Accepted/Verified), PR templates, and compatibility matrices are **recommended team processes**, not built-in framework features. Code/contract snippets are self-study examples; **no build or specialized Content QA was executed during authoring of this lesson**.

---

**Key takeaway:** Evolving contracts only become **compatibility evidence** when (1) teams agree on semantics, (2) generated producer tests run against **real** provider code, (3) stub artifacts are generated from the **same contract revision/candidate** with provenance, (4) **real** consumer clients/handlers run against that artifact, and (5) supported consumer versions pass release gates. Verify that tests can turn **red** when communication breaks, rather than trusting the green badge of a pipeline lacking evidence.
