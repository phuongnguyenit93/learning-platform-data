# Responding When a Producer Does Not Yet Satisfy a New Interaction

## Learning objectives

In **Spring Cloud Contract**, the producer exposes HTTP APIs or emits messages; the consumer relies on that behavior to execute business logic. Both sides describe expectations using **Groovy/YAML DSL**, generate **producer contract tests**, build stubs for **Stub Runner**, and integrate CI to detect incompatible changes.

A common challenge arises when **a consumer needs an interaction that the producer has not yet implemented**. A red generated producer test in that moment does not necessarily mean the contract is wrong; it can be the first piece of evidence that a proposal has not yet become a supported commitment.

This lesson belongs to the **Team Coordination** chapter and focuses on how to respond to a new proposal that the producer does not yet satisfy. After this lesson, you will be able to:

- Distinguish **proposed**, **accepted**, **implemented**, **verified**, and **published**.
- Write an HTTP/message contract proposal clear enough for the producer to review.
- Read a failing generated producer test and distinguish missing implementation, wrong DSL, wrong test setup, or infrastructure error.
- Respond with **evidence, decision, rationale, owner, and next steps** instead of merely saying "not supported yet".
- Choose among **accept, negotiate, phase, defer, or reject**.
- Keep a **candidate stub** for consumer development without mistakenly publishing it as a verified stub.
- Design CI keeping producer tests as a quality gate and checking consumer compatibility before release.
- Analyze HTTP, messaging, breaking change, retry, and safe rollout scenarios.

> **Principle:** a consumer-proposed contract is a **requirement to be reviewed**. Only when the producer implements it, generated producer tests actually execute and PASS, does that contract have evidence of support within the verified scope.

## 1. Running scenario: Checkout needs a new reservation API

Suppose there are two services:

- **Checkout Service**: consumer, handles order placement.
- **Inventory Service**: producer, manages stock quantities.

Currently Checkout can only check inventory:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

However, the read result is a **snapshot**. Two orders could simultaneously see eight items in stock and oversell actual inventory. Checkout wants a reservation operation:

~~~http
POST /api/inventory/reservations HTTP/1.1
Content-Type: application/json
Idempotency-Key: checkout-req-1001

{"sku":"SKU-101","quantity":2}
~~~

Proposed response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "reservationId": "RSV-1001",
  "sku": "SKU-101",
  "reservedQuantity": 2,
  "status": "ACTIVE"
}
~~~

**Problem:** the producer does not yet have `POST /api/inventory/reservations`. When the consumer submits a contract PR, the producer generates tests and gets **404 instead of 201**.

Teams should not automatically "change 201 to 404", drop tests, or publish stubs. They must confirm:

1. Does reservation belong to Inventory's responsibility?
2. Which endpoint and schema are appropriate?
3. Do reserved stock units need atomic guarantees under concurrent load?
4. How are idempotency and retries defined?
5. In which version will the producer implement it, or is there an alternative?
6. How does the consumer behave while it is not yet supported?
7. What criteria permit marking this interface as verified/published?

### Coordination flow

~~~mermaid
flowchart TD
    A["Consumer submits contract proposal"] --> B["Review use case and DSL"]
    B --> C["Producer runs generated test"]
    C --> D{"Test PASS?"}
    D -->|Yes| E["Producer verified"]
    D -->|No| F["Triage: code / DSL / fixture / CI"]
    F --> G{"Two-team decision"}
    G -->|Accept| H["Implement + rerun producer tests"]
    G -->|Negotiate| I["Revise agreed scope"]
    G -->|Defer| J["Keep proposal, do not publish"]
    G -->|Reject| K["Rationale + alternative"]
    H --> C
    I --> C
    E --> L["Candidate stub from exact revision"]
    L --> M["Stub Runner consumer tests"]
    M --> N["Compatibility + release gate"]
~~~

A failure signal is **useful feedback on a proposal branch**, whereas on a release branch, committed producer contract tests must PASS.

## 2. Proposed contracts differ from supported contracts

| Coordination status | Meaning | Can we say the producer supports it? |
|---|---|---|
| **PROPOSED** | Consumer just stated need and DSL | **No** |
| **UNDER_REVIEW** | Teams are clarifying semantics and ownership | **No** |
| **ACCEPTED_PENDING** | Producer agrees on scope but implementation is unfinished | **Not yet** |
| **IMPLEMENTED_UNVERIFIED** | Code written but no passing producer tests yet | **Insufficient evidence** |
| **VERIFIED** | Generated producer tests executed and PASSED | **Yes, within test scope** |
| **PUBLISHED** | Stub from verified revision published | Consumers can download to test |
| **DEFERRED / REJECTED** | Not committed or another approach chosen | **No** |

**These labels are suggested work statuses for issues/PRs**, not built-in status values in the Spring Cloud Contract DSL or lesson metadata.

### Why does the distinction matter?

- `PROPOSED` lets consumers express expectations and receive feedback.
- `ACCEPTED_PENDING` indicates producer agreement on the goal, **not a promise that the API already runs**.
- `IMPLEMENTED_UNVERIFIED` is not enough for consumers to enable production features.
- `VERIFIED` requires generated producer tests to **actually execute**.
- `PUBLISHED` requires additional quality gates for artifacts, versions, and permissions.
- `DEFERRED` and `REJECTED` require clear reasons and an explicit next direction.

Without this distinction, consumers might interpret "contract PR merged" as "producer endpoint is ready".

## 3. Turning the requirement into concrete Groovy DSL

A proposal file, e.g., `contracts/inventory/reservationCreated.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout reserves 2 units of SKU-101'

    request {
        method 'POST'
        url '/api/inventory/reservations'
        headers {
            contentType(applicationJson())
            header('Idempotency-Key', 'checkout-req-1001')
        }
        body(
            sku: 'SKU-101',
            quantity: 2
        )
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: 'RSV-1001',
            sku: 'SKU-101',
            reservedQuantity: 2,
            status: 'ACTIVE'
        )
    }
}
~~~

Alternative YAML version:

~~~yaml
description: 'Checkout reserves 2 units of SKU-101'
request:
  method: POST
  url: /api/inventory/reservations
  headers:
    Content-Type: application/json
    Idempotency-Key: checkout-req-1001
  body:
    sku: SKU-101
    quantity: 2
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: RSV-1001
    sku: SKU-101
    reservedQuantity: 2
    status: ACTIVE
~~~

Both examples describe **a single scenario**; do not place both in the same build if that produces duplicate mappings.

### What has been described?

- `POST` request to the right path.
- Meaningful `Content-Type` and `Idempotency-Key`.
- `quantity` is a **number**, not a string.
- `201` response and fields needed by Checkout.
- Fixed `reservationId` is a fixture; production IDs are usually dynamic and need appropriate matchers in real contracts.

### What has not been described yet?

One sample request/response does not tell the whole story:

- When does a reservation expire?
- Does sending the same key twice return the same result or an error?
- What if the same key is reused with a different payload?
- If stock is insufficient, what response/error code is returned?
- If Checkout times out after the producer already created the reservation, how does the client retry?
- Is authentication, authorization, or a correlation ID required?

These are **review questions to settle**, not reasons to loosen matchers and call it done.

## 4. Reading a red generated producer test as a signal

Spring Cloud Contract generates producer-side tests from the contract above. Meaning of the generated test:

~~~text
WHEN:
  POST /api/inventory/reservations
  Content-Type: application/json
  Idempotency-Key: checkout-req-1001
  body = {"sku":"SKU-101","quantity":2}

THEN:
  HTTP status = 201
  Content-Type = application/json
  $.reservationId = "RSV-1001"
  $.reservedQuantity = 2
  $.status = "ACTIVE"
~~~

This is **pseudocode**, not verbatim Java output from a specific verifier version.

Since the producer does not have the route yet, logs may show:

~~~text
Test: ReservationContractTest.shouldReserveSku
Expected status: 201
Actual status:   404
Result: FAILED
~~~

**Insufficient response:** "Contract is red, consumer wrote it wrong."

**Constructive response:** "On producer commit A, the generated test from proposal B called `POST /api/inventory/reservations` on the real controller and received 404 instead of 201. The route is not implemented yet. We suggest reviewing idempotency semantics and opening an implementation issue, keeping the contract in proposal status until tests PASS."

### Do not jump to conclusions on seeing 404

A `404` can also happen because the base test did not register the controller properly, the URL is missing a context path, or the test is hitting the wrong version. Before writing "not supported", check:

1. Confirm the **exact contract revision**.
2. Inspect the generated test and actual request.
3. Confirm the base test runs the **real producer controller/application**.
4. Check controller mapping, HTTP method, and path.
5. Inspect fixtures, test security, and exception handlers.
6. Separate implementation gaps from test setup gaps.

## 5. Triage table when producer tests fail

| Symptom | Possible cause | How to check |
|---|---|---|
| HTTP 404 instead of 201 | Route does not exist, wrong path/base test | Controller mapping + generated request |
| HTTP 405 | Route exists but HTTP method unsupported | Method contract and routing |
| HTTP 400 | Body/schema/validation not aligned | DTO required fields and JSON types |
| HTTP 401/403 | Security not set up or contract lacks auth | Filter chain, test identity, and API policy |
| HTTP 500 | Route exists but logic/fixture/service failed | Stack trace and test context |
| HTTP 201 but missing field | Producer does not return full response | Assertions / actual body |
| Wrong `quantity` type | Producer returns string instead of number | Generated JSON assertions |
| Message receive timeout | Publisher missing or wrong receiver | Trigger/destination/binder |
| No tests generated | DSL undiscovered or plugin misconfigured | Contract path, source set, test report |
| Test compile failure | Wrong base class/test framework | Generated test imports and base class |
| Build SUCCESS yet `0 tests` | Skips/filters/wrong source set | Test discovery logs and reports |

When concluding, state clearly what is **verified** versus **hypothesis to check**. Do not blame every failure on the producer implementation.

## 6. Essential elements of a response

| Element | Example response |
|---|---|
| **Acknowledged** | "Reviewed Checkout's reservation proposal." |
| **Evidence** | "Generated test at commit A received 404, expected 201." |
| **Current state** | "Route is not implemented on the current branch." |
| **Decision** | "Accept goal, but idempotency is not yet finalized." |
| **Rationale** | "Need atomic reservation guarantees to avoid overselling." |
| **Owner** | "Inventory team opens implementation issue and design review." |
| **Open items** | "Duplicate key behavior, insufficient-stock error, expiration." |
| **Timeline** | "Implementation milestone TBD; will update after review." |
| **Interim plan** | "Checkout keeps feature flag off; candidate stub is for testing only." |
| **Done criteria** | "Producer tests PASS, versioned stub, consumer compatibility PASS." |

Never promise a release date without confirmation from the accountable owner. If no milestone exists, **explicitly say no milestone is set** and state the next decision step.

### Example PR comment

> Reviewed the `POST /api/inventory/reservations` proposal. The producer currently returns **404** whereas the contract expects **201**; generated tests from the proposal do not PASS yet. The Inventory team agrees atomic reservation is needed, but we still need to finalize `Idempotency-Key`, reservation TTL, and insufficient-stock error codes. For now, keep the contract on the proposal branch and do not publish the stub as verified. Checkout may use the candidate to develop its client locally, but must not enable this flow in production yet.

The snippet above is an **illustrative example**, not a real sent notification or roadmap commitment.

## 7. Choosing the right decision for a new requirement

| Decision | When appropriate? | Next action |
|---|---|---|
| **ACCEPT / IMPLEMENT** | Valid need within producer ownership | Finalize DSL, owner, tests, implementation plan |
| **NEGOTIATE** | Schema, status, semantics, or SLA not yet aligned | Exchange request/response examples, revise DSL by consensus |
| **PHASE** | One slice can safely be implemented first | Separate contract for supported slice, keep remainder as proposal |
| **DEFER** | Blocked by dependency, roadmap, or risk | Record blocker, owner, reopen criteria, and consumer wait plan |
| **REJECT** | Outside ownership or cannot guarantee correctness/security | State rationale + alternative interface/architecture |
| **FIX TEST SETUP** | Implementation exists but base class/fixture is wrong | Fix setup and re-run generated tests before marking verified |

**Do not alter reality just to turn tests green.** For instance, changing a reservation request into `GET /inventory/{sku}` does not provide atomic hold guarantees. If phasing, the consumer must **accept the narrowed scope** and code must not assume capabilities not yet provided.


## 8. Finalize acceptance criteria before implementation

An HTTP contract only describes a few interaction examples. Once the producer agrees to support reservations, both teams must clarify **acceptance criteria**.

### Happy path

- `POST /api/inventory/reservations` accepts valid `sku` and `quantity`.
- `quantity` is a positive number; the producer does not rely on parser coercion from a string.
- `Idempotency-Key` is handled according to the agreed policy.
- Producer returns status `201` and a `reservationId` usable to confirm or cancel the reservation.
- `reservedQuantity` and `status` have stable semantics for consumers.

### Error branches

- If stock is insufficient, both sides agree on status and error code, e.g., `409` + `INSUFFICIENT_STOCK`.
- If the SKU does not exist, return an error code distinct from insufficient stock.
- If the request body fails schema validation, return a validation error per API policy.
- If the producer is unavailable, the consumer must distinguish transient errors from "out of stock".
- On retries with the same idempotency key, the producer must follow agreed semantics; never silently create two reservations.

### Limits of contract tests

Contract tests verify HTTP method, path, headers, request/response shapes, and error examples. However, **atomicity under concurrent load**, transaction isolation, and database failure behavior typically require integration/concurrency tests.

Do not declare "safe reservation supported" merely because one `201` contract test PASSES if the implementation still has a race condition allowing oversells.

### Suggested Definition of Done

~~~text
Contract review: ACCEPTED
Producer implementation: MERGED
Generated contract tests: EXECUTED and PASS
Additional concurrency/idempotency tests: PASS as required
Verified stubs artifact: created from same revision
Consumer Stub Runner tests: PASS
Compatibility review: PASS
Rollout ownership: agreed
~~~

This is a **process checklist**, not fields automatically generated by Spring Cloud Contract.

## 9. Anti-pattern: changing the contract to match missing code

Suppose the test currently reports:

~~~text
Expected HTTP status: 201
Actual HTTP status: 404
~~~

**Wrong fix:** change the DSL to expect `404` so the test PASSES, then tell Checkout "the contract is producer-verified".

Why is it wrong? Because the consumer needs a **reservation** operation, and a `404` response does not provide that capability. Turning a test green by lowering expectations does not make the implementation valid.

Other variants:

| Hasty edit | Problem |
|---|---|
| Remove `reservationId` assertion | Checkout has no ID to confirm/cancel |
| Change `quantity` from number to string | Breaks typed clients/deserializers |
| Use regex `.*` for all response fields | Fails to detect missing meaningful data |
| Drop `Idempotency-Key` header | Loses duplicate-protection requirement needed by consumer |
| Accept any status in `2xx/4xx` | Test stops protecting the happy-path flow |
| Edit mock to return right JSON without hitting real controller | Producer verification does not test implementation |

**Adjusting a contract is only valid when both teams agree to change requirements**, not because someone wants CI to turn green.

## 10. Distinguishing proposal tests from verified release gates

You can maintain **two verification tracks** with distinct goals.

| Track | Goal | When generated test for new requirement is red |
|---|---|---|
| **Proposal validation** | Consumer and producer discuss future API | Report **NOT SUPPORTED YET** with evidence, continue review |
| **Producer release verification** | Prove producer satisfies committed contracts | **Block publish/release** |

Proposals can live in unmerged PRs, separate branches, or temporary CI artifacts. While scope is unfinalized and unimplemented, it **must not accidentally enter release publications as verified**.

### About inProgress and ignored

Spring Cloud Contract provides mechanisms for in-progress or ignored contracts in certain DSL/plugin versions, and options like `failOnInProgress`.

However, **how a specific version handles test/stub generation, skipping, and build failures must be verified in the docs/plugin you use**. Do not treat `inProgress` as proof of producer support, and do not use `ignored` as a shortcut to turn releases green.

Safe operational rules:

1. Maintain an **issue/PR tracking the proposal**, owner, and reason it is unmet.
2. Never place unverified candidates in the release artifact repository.
3. Quality gates must explicitly know which contracts are committed.
4. Once the producer finishes, re-run generated producer tests before promoting to verified.

### Why separate them?

If teams merge every proposed DSL into the release branch, the producer can stay perpetually red. The bad outcome is someone adding `skipTests` or disabling the entire contract suite to meet a release deadline, stripping protection **even from already-supported legacy contracts**.

Separating the proposal track preserves early feedback without breaking quality gates for committed interfaces.

## 11. Candidate stubs for consumers to develop ahead

While Inventory is still implementing, Checkout may want to write its HTTP client, DTOs, and UI. Spring Cloud Contract can generate stubs from DSL even when the real producer does not satisfy them yet.

That helps **if labeled clearly**:

~~~text
Artifact kind: experimental candidate
Contract revision: proposal-branch@commit-X
Producer verification: FAIL / NOT YET RUN
Eligible for verified release: NO
Allowed use: isolated consumer prototype / diagnostic tests
~~~

Never give an unverified candidate the same immutable version as an official stub. Keep it in CI artifacts, a restricted staging repository, or a local Maven repository with a unique version/build ID.

### What does Stub Runner check?

Consumer tests with Stub Runner prove **the consumer can send requests and handle responses simulated from the DSL**. They do not prove production Inventory already has that endpoint.

Example skeleton for a Spring Boot consumer configured with the Stub Runner dependency:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.5.0-rc.1:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutReservationContractTest {

    @StubRunnerPort("inventory-producer")
    int stubPort;

    @Autowired
    RestClient.Builder restClientBuilder;

    record ReserveRequest(String sku, int quantity) {}

    record ReserveResponse(
        String reservationId,
        String sku,
        int reservedQuantity,
        String status
    ) {}

    @Test
    void readsProposedReservationResponse() {
        RestClient client = restClientBuilder
            .baseUrl("http://localhost:" + stubPort)
            .build();

        ReserveResponse result = client.post()
            .uri("/api/inventory/reservations")
            .header("Idempotency-Key", "checkout-req-1001")
            .body(new ReserveRequest("SKU-101", 2))
            .retrieve()
            .body(ReserveResponse.class);

        assertThat(result.reservationId()).isNotBlank();
        assertThat(result.reservedQuantity()).isEqualTo(2);
        assertThat(result.status()).isEqualTo("ACTIVE");
    }
}
~~~

This example is a **conditional illustrative test**: it requires a Spring test context, the matching candidate artifact in the Maven local repo, dependencies, and proper serialization setup. `RestClient` exists in Spring Framework 6.1+, not every Spring Boot version.

**Note:** `:0` in the Stub Runner ID requests a dynamic port; the test must obtain the actual port via `@StubRunnerPort`. Never use `localhost:0` as the base URL.

### Conclusion when consumer test PASSES

~~~text
Valid:
  Checkout client handles the response provided by the candidate stub.

Invalid:
  Inventory Service has implemented and will return that response in production.
~~~

The second conclusion requires **passing generated producer tests on the real implementation**, tied to the verified artifact/version.

## 12. If the producer agrees to implement, what is the workflow?

An auditable workflow:

1. Producer confirms use case, request/response semantics, error cases, and owner.
2. Checkout and Inventory lock the DSL revision and acceptance criteria.
3. Producer implements controller/publisher, service logic, and required data handling.
4. Base test sets up the real producer test environment: real MockMvc/controller, HTTP runtime, or messaging binder.
5. Spring Cloud Contract generates tests from the **same DSL revision**.
6. Generated tests are **compiled, executed, and PASS**; test count matches expectations.
7. Supplementary integration tests for idempotency, concurrency, and authorization run as needed.
8. Stub artifact is packaged from the **same producer and DSL revision**.
9. Checkout runs Stub Runner with the **exact candidate version**, testing the real client/handler.
10. Release gate verifies impact on older consumers and the rollout plan.

**Merging code is not Done** if tests were skipped or consumers still run against old stubs.

### Keep a revision record

~~~text
Contract source SHA: <contract-sha>
Producer source SHA: <producer-sha>
Producer generated tests: 6 executed / 6 passed
Candidate stub: com.example:inventory-producer:2.5.0-rc.1:stubs
Candidate artifact SHA-256: <digest>
Consumer tests: 4 executed / 4 passed
Release decision: eligible after required review
~~~

Values inside `<...>` are placeholders. They must be recorded by CI, never filled in without evidence.

## 13. If the producer can only implement part of it

Suppose Inventory can create reservations but does not yet support **Idempotency-Key**.

| Decision | Condition | Communication responsibility |
|---|---|---|
| Hold request and wait | Idempotency is mandatory to avoid duplicate reservations | Producer cannot commit to the interface yet |
| Phase delivery | Checkout has another reviewed safe mitigation | Phase-1 contract accurately reflects limitations |
| Change model | Synchronous reservation does not fit architecture | Propose command/event with clear semantics |
| Reject partial element | Header/schema makes no sense per API policy | Propose an alternative rule |

**Never delete the `Idempotency-Key` matcher and still write "API guarantees idempotency".** That creates drift between contract and reality, not test optimization.

A clean contract split:

~~~text
stockAvailable        -> verified existing GET
reservationCreated    -> proposed / implementing
reservationNoStock    -> planned error scenario after agreement
reservationCancelled  -> separate interaction when consumer needs it
~~~

Each contract should represent one clear scenario; do not force the producer to commit to an entire future roadmap through one current test.

## 14. When the producer defers or rejects

### Defer

A complete response should state:

- **Blocker**: transaction model, database migration, ownership, security, or engineering capacity.
- **Impact**: which Checkout flows cannot be enabled.
- **Owner**: who evaluates and provides updates.
- **Reopen criteria**: which technical conditions or product decisions must be met.
- **Consumer plan**: feature flag/fallback or agreed alternative.
- **Review checkpoint**: if no date is set, state clearly it is unscheduled rather than inventing a deadline.

### Reject with rationale

Rejecting a request like `POST /api/inventory/reservations` can be right if reservations belong to another service. The producer should provide:

1. Exact ownership boundary.
2. Risks of placing the requirement inside Inventory.
3. Alternative APIs/events worth considering.
4. Which parts of the contract need adjustment.
5. Point of contact to help the consumer move the dependency.

Rejecting **one proposed solution** does not reject the **business need**. Discussion must return to preventing oversells, not merely an endpoint name.

## 15. What can the consumer do while waiting?

Do not send new requests to production just because a stub in tests returns `201`. Safe options:

- **Feature flag** keeping the unavailable reservation flow turned off.
- **Isolated candidate tests** to build client and UI code ahead of time.
- **Display a safe state** when reservation is unavailable, rather than pretending reservation succeeded.
- **Existing APIs** used strictly within their real guarantees. Inventory GET is not an atomic hold.
- **Versioned rollout**: producer ready first, consumer enabled second.
- **Controlled fallback**: never fabricate a fake `reservationId` to pass down to payment/cancellation steps.

### Rollout pseudocode

~~~text
if producer capability has been verified and deployed:
    enable Checkout reservation flow
else:
    keep new flow disabled or show safe unavailable state
~~~

This is a design policy, not logic automatically provided by Spring Cloud Contract. Real systems need an appropriate capability/configuration mechanism.

## 16. Protecting existing consumers

A new endpoint may be additive; however, modifying an existing API to serve the new interaction can still break older consumers.

Old response:

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

Proposed replacement response:

~~~json
{"sku":"SKU-101","availability":"IN_STOCK","units":8}
~~~

If the producer updates code and the new contract simultaneously, new generated tests can PASS. Yet old Checkout still reads `available` and `quantity` and may fail.

| Change | Risk | Appropriate response |
|---|---|---|
| Add endpoint, keep old endpoint | Usually low, still needs ordered rollout | Deploy producer first, enable consumer after |
| Add response field | Depends on client tolerance for unknown fields | Run consumer compatibility tests |
| Remove/rename field | Breaking | Migration / keep old field / new version |
| Change number to string | Breaking for typed clients | Preserve schema or version |
| Change status/error body | Can break error handling | Separate contracts for error cases |
| Add required header | Can break old consumer requests | Transition policy / versioning |
| Change message destination/event schema | Can cause listeners to stop receiving | Dual publish / migration when appropriate |

Never assume a consumer proposing an interface edit has authority to decide on behalf of all other consumers. Identify the **list of deployed consumers and fields they rely on**.


## 17. Responding to a message contract not yet supported by the producer

New interaction proposals are not limited to HTTP. Suppose Checkout wants to receive a **StockReserved** event when Inventory confirms a hold.

Illustrative Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_reserved'

    input {
        triggeredBy('emitStockReserved()')
    }

    outputMessage {
        sentTo('stock-reservations')
        body(
            eventType: 'StockReserved',
            reservationId: 'RSV-1001',
            sku: 'SKU-101',
            quantity: 2
        )
        headers {
            messagingContentType(applicationJson())
        }
    }
}
~~~

In producer tests, the base class must provide `emitStockReserved()` and a suitable messaging adapter/receiver so generated tests trigger **real** publisher code and observe the message.

If the producer does not emit the event yet, you may get:

~~~text
Expected:
  destination = stock-reservations
  eventType = StockReserved
  reservationId = RSV-1001

Actual:
  No matching message received before timeout

Result: FAILED
~~~

### Before concluding "event not implemented yet"

Distinguish among:

1. Publisher is not implemented yet.
2. `triggeredBy` calls a base-class method that does not trigger the real producer.
3. Test binder/receiver listens on the wrong destination.
4. Broker or routing failed to start properly.
5. Message was sent late or consumed by another test.
6. Payload/headers differ from DSL so the receiver does not match.

Respond by separating **implementation gaps** from **test infrastructure gaps**, citing logs, destinations, and received messages (if any). **Increasing timeouts hugely** does not prove the publisher works.

### Consumer StubTrigger only tests the consumer

Checkout can use `StubTrigger.trigger("stock_reserved")` to emit a simulated message and test its handler; doing so does not prove real Inventory publishes `StockReserved`.

A message contract qualifies for a verified release only when generated producer tests run against the real publisher and PASS. Producer and consumer must also agree on **event timing**, correlation, duplicate delivery, schema versioning, ordering, and retry/DLQ as needed. Transactional guarantees and broker durability require appropriate integration tests beyond basic contract tests.

## 18. Two-track CI workflow: proposal and verified release

A CI design that gives fast feedback without compromising release gates:

~~~mermaid
flowchart TD
    A["Consumer contract proposal PR"] --> B["Validate DSL + review scope"]
    B --> C["Optional producer test with proposal"]
    C --> D{"Satisfied?"}
    D -->|Not yet| E["Feedback: NOT SUPPORTED YET"]
    D -->|Yes| F["Candidate ready for full verification"]
    F --> G["Producer release CI"]
    G --> H["Generate + execute committed producer tests"]
    H --> I{"Required producer tests PASS?"}
    I -->|No| X["Block verified stub publish"]
    I -->|Yes| J["Package :stubs from same revision"]
    J --> K["Consumer Stub Runner compatibility tests"]
    K --> L{"Required consumers PASS?"}
    L -->|No| M["Investigate breaking change"]
    L -->|Yes| N["Publish according to release policy"]
~~~

### Proposal CI

Checks DSL syntax, fixtures, test generation, and trial runs against the current producer. A failure because a new endpoint does not exist yet is **feedback** for a joint decision.

Ensure you:

- Explicitly mark that the producer **does not support it yet**.
- Never convert that failure into a passing release gate.
- Never use a proposal artifact as a verified version.
- Never mark `PUBLISHED` when producer tests have not PASSED.
- Keep the issue/owner and unresolved questions visible.

### Release CI

Recommended quality gate:

~~~text
CAN_PUBLISH_VERIFIED_STUB =
    CONTRACT_FILES_DISCOVERED
    AND GENERATED_PRODUCER_TESTS_EXECUTED
    AND GENERATED_PRODUCER_TESTS_PASSED
    AND REQUIRED_BUILD_CHECKS_PASSED
    AND STUB_MATCHES_VERIFIED_REVISION
    AND RELEASE_AUTHORIZED
~~~

If the organization requires consumer compatibility before release, add the consumer tests PASS condition.

**Never treat "build SUCCESS, 0 generated contract tests" as proof the producer passes.** Never enable `-DskipTests`, `-Dmaven.test.skip=true`, or Gradle `-x contractTest` on the official release path.

Reference commands in a plugin-configured module:

~~~bash
# Maven producer:
./mvnw -B -ntp clean verify

# Gradle producer, if the plugin has this task:
./gradlew :inventory-producer:contractTest
~~~

These commands were not run during this lesson; verify plugin versions, task graphs, reports, and skipped tests in your real project.

## 19. Versions and artifacts: when is the new interface published?

Once the producer implements it and contract tests PASS, produce:

~~~text
Producer source SHA: <producer-sha>
Contract source SHA: <contract-sha>
Generated producer tests: 6 executed / 6 passed

Candidate stub:
  com.example:inventory-producer:2.5.0-rc.1:stubs
  sha256: <artifact-digest>

Checkout consumer:
  Stub Runner loaded: inventory-producer:2.5.0-rc.1:stubs
  consumer tests: 4 executed / 4 passed
~~~

Information inside `<...>` is a placeholder to be populated by CI from actual results.

### Candidate vs. published stub

| Attribute | Internal CI candidate | Published verified stub |
|---|---|---|
| Purpose | Test changes/compatibility | Downloaded by other consumers for testing |
| Producer status | May be proposal or tested, must be clearly labeled | Producer contract tests must PASS |
| Scope | Controlled branch/job/staging | Authorized release repository |
| Version | Unique build/commit ID | Traceable and ideally immutable coordinates/version |
| Publish rights | Test job needs no release secrets | Protected release job |
| Records to keep | Contract revision, test results | Producer source SHA, stub digest, release decision |

### Caching and `latest`

A consumer test may stay green if it loads a stale stub even after the producer changed the contract. Never use `latest` aliases or mutable SNAPSHOTs as hard proof for a proposal. Pin artifact versions, log resolved coordinates, and consider recording checksums/digests.

If CI spans two repositories, pass the **exact candidate artifact** (or immutable version) from the producer job to the consumer job. Never verify the producer at commit A and then publish a stub rebuilt uncontrollably from commit B.

## 20. Handoff flow between Checkout and Inventory

~~~mermaid
sequenceDiagram
    participant C as Checkout team
    participant R as Contract PR / issue
    participant P as Inventory team
    participant CI as Producer CI
    participant A as Artifact repository
    participant T as Consumer CI
    C->>R: Propose POST /reservations
    R->>P: Request review
    P->>CI: Run generated producer tests
    CI-->>P: FAIL 404 instead of 201
    P->>R: Evidence + ACCEPTED_PENDING + owner
    P->>P: Implement route/idempotency/error cases
    P->>CI: Rerun producer tests
    CI-->>P: PASS
    P->>A: Publish candidate stub from exact revision
    A->>T: Stub Runner load exact version
    T-->>C: Consumer tests PASS or feedback
    C->>R: Confirm readiness/compatibility
~~~

`ACCEPTED_PENDING` is a **recommended internal coordination label**, not a built-in Spring Cloud Contract status.

### A decision table to avoid dropped items

| Decision | Owner | Evidence | Close condition |
|---|---|---|---|
| Accept request/schema | Both teams | DSL review/acceptance criteria | Contract finalized |
| Implement reservation | Inventory | Code PR + producer tests | Generated tests PASS |
| Handle retry/idempotency | Inventory and Checkout | Integration tests + agreed semantics | No double reservations |
| Publish candidate verified stub | Inventory CI | Test report + digest | Artifact matches revision |
| Test consumer behavior | Checkout CI | Stub Runner results | Client/flow PASS |
| Enable feature | Checkout/product + Inventory readiness | Deployment/version confirmation | Safe rollout |

Real milestones and owners must be recorded in project issues/PRs; never infer a team approved just because its name appears in an example.

## 21. When red is a test setup bug, the response must differ

Suppose Inventory actually has the reservation endpoint, yet the generated test base class only registers an old controller:

~~~text
Production:
  POST /api/inventory/reservations exists

Test setup:
  MockMvc standaloneSetup(OldInventoryController)
  ReservationController not registered

Observed:
  HTTP 404
~~~

**Do not** conclude "Inventory does not support the route yet" when the test setup failed to target the right implementation.

How to handle:

- Inspect `baseClassForTests`/`baseClassMappings`.
- Inspect application context, MockMvc setup, or test mode.
- Verify authentication/security configuration.
- Check fixtures: does `SKU-101` exist in the test environment?
- Check that the generated test sends the expected URL/headers/body.
- Fix setup, **re-run tests**, and only then mark verified.

Similarly, a producer returning `409` because the fixture is out of stock may be **correct business logic with the wrong happy-path fixture**, not a rejected reservation requirement. Feedback must rest on the actual request and data state in the test.

## 22. Common anti-patterns in cross-team responses

| Anti-pattern | Why dangerous | Replacement |
|---|---|---|
| "Consumer Stub Runner PASSES, so producer supports it" | Stub does not run real producer code | Producer verification PASS |
| Deleting red test without an issue | Loses track of unmet requirement | Keep proposal, tracking, and owner |
| Changing status 201 to 404 to go green | Breaks the actual use case | Negotiate or implement behavior |
| Removing critical header/field from DSL | Consumer loses needed guarantee | Review semantics between both teams |
| Merging proposal into verified contracts and skipping all tests | Disables release gate | Separate proposal and verified tracks |
| Using `inProgress`/`ignored` with unclear semantics | Can mask failures | Verify plugin version and governance |
| Publishing failing candidate to release repo | Consumers may mistake it for verified | Separate staging and unverified label |
| Using `latest` or mutable SNAPSHOT | Does not prove tested bytes | Version + digest/commit |
| Replying "coming soon" with no owner | Consumer cannot plan | Issue/decision/next review |
| Producer meets new schema by deleting old schema | Can break old consumers | Compatibility review and migration |
| Consumer enables feature before producer deploys | Calls nonexistent endpoint | Producer-first rollout and feature flag |
| Testing only HTTP happy path | Misses critical errors/side effects | Error contracts + integration tests |
| Treating every HTTP 404 as business `NOT_FOUND` | Might be unmatched WireMock request | Assert body/error code and request |
| Sharing logs missing commit and contract version | Hard to reproduce | Expected/actual + source SHA + test name |
| Blaming producer when base test is wrong | Delays resolution and sparks conflict | Triage test setup before concluding |

### When both sides disagree

Do not decide by "whose tests are greener". Start from the use case and business guarantees, use concrete request/response or event payload examples, lay out options and trade-offs, and record the decision owner. Until agreed, **there is no commitment of support**.

## 23. Lab 1: responding when the endpoint does not exist yet

### Prompt

Checkout submits contract:

~~~text
POST /api/inventory/reservations
body = {"sku":"SKU-101","quantity":2}
expected = HTTP 201 + reservationId
~~~

Generated producer test returns:

~~~text
actual = HTTP 404
~~~

Inventory has no plan to implement reservations in the current release.

**Q1. Should we change expected 201 to 404 so the test goes green?**

No. That erases the behavior the consumer requested. Keep the proposal outside verified releases, state clearly the producer does not support it yet, and discuss options.

**Q2. What should the response contain?**

Contract path/version, producer SHA, generated test name, expected/actual, verified root cause, accept/defer/reject decision, owner, blocker, next action, and Done criteria.

**Q3. Can Checkout use a candidate stub to build its client ahead of time?**

Yes, in an **isolated test environment** labeled unverified. Never use that result as proof Inventory implemented it or to enable production features.

**Q4. What if the producer simply suggests continuing to use Inventory GET?**

GET lacks atomic hold guarantees. Both teams must clarify whether that actually addresses overselling or if an architectural change is required.

### Reference response template

> Inventory ran the generated contract test for `POST /api/inventory/reservations` and got **404** instead of **201**. The endpoint is not yet supported in the target release. We suggest keeping the proposal unverified while clarifying idempotency, expiration, and insufficient-stock rules; implementation decisions and milestones will be updated after design review. Checkout may try the candidate stub in tests, but must keep the feature flag disabled until both producer tests and consumer compatibility pass.

## 24. Lab 2: consumer wants a new message

### Prompt

Checkout wants to receive a `StockReserved` event on destination `stock-reservations`. The DSL uses `label 'stock_reserved'` and `triggeredBy('emitStockReserved()')`. The generated producer test times out.

Check:

1. Has the publisher been implemented yet?
2. Does the trigger method invoke the real producer?
3. Does the binder/receiver listen on the right destination?
4. Do payload/headers match the contract?
5. Is the event emitted after transaction commit?
6. Does the consumer test wait for the handler to update state with a finite timeout?

**Key question:** Is a passing Stub Runner `StubTrigger` test enough for the producer to publish a verified message stub?

**No.** `StubTrigger` lets the consumer receive a simulated message from the DSL, whereas the producer needs generated message tests actually observing the publisher and PASSING.

### Advanced exercise: when the producer only partially accepts

The producer agrees to build the reservation API but declines the `Idempotency-Key` header in phase 1.

Produce a reviewable decision:

- Can the consumer genuinely run safely without idempotency?
- Is there an alternative preventing duplicate reservations?
- What will the v1 contract describe and what remains unsupported?
- Which feature flags, retry policies, and tests must be added?
- When is phase 2 considered verified?

Do not alter the DSL unilaterally and assume the consumer agreed.

## 25. Checklist before responding to the consumer

- [ ] Understood the use case, not just the URL or event name.
- [ ] Identified the contract revision and proposing team.
- [ ] Read the generated producer test and expected/actual output.
- [ ] Separated implementation gaps from test setup/fixture/broker failures.
- [ ] Communicated which producer version supports the interaction, if any.
- [ ] Chose accept/negotiate/phase/defer/reject or setup investigation.
- [ ] Documented rationale, owner, and next steps.
- [ ] Listed open semantic questions clearly.
- [ ] If no release milestone exists, made no premature promises.
- [ ] Kept unsupported proposals separate from verified releases.
- [ ] Labeled any candidate stubs as unverified with distinct versions.
- [ ] Blocked publishing verified stubs when generated producer tests fail, skip, or run 0.
- [ ] Confirmed consumer has safe feature flags/fallbacks while waiting.
- [ ] Reviewed HTTP request/status/body/headers and messaging destination/payload.
- [ ] Added supplementary tests for out-of-contract guarantees like concurrency/idempotency.
- [ ] Verified generated tests hit the real producer implementation, not a fake endpoint.
- [ ] Matched stub artifact to the verified revision with clear coordinates/digest.
- [ ] Ran consumer tests with the exact candidate version via Stub Runner.
- [ ] Reviewed legacy consumers to prevent breaking changes.
- [ ] Communicated decisions and status back to dependent teams.

## 26. Key takeaways and references

**Responding when a producer does not yet satisfy a new interaction** is a vital part of consumer-driven contract testing. A red generated producer test can be an accurate signal that a consumer-proposed contract **is not yet implemented by the producer**, or has a setup bug needing investigation. Instead of weakening matchers to turn green, deleting tests, or publishing unverified stubs, teams should turn that result into a **clear decision backed by evidence and an owner**.

Distinguish **proposed**, **accepted**, **implemented**, **verified**, and **published**. Candidate stubs help consumers build early, but never replace producer verification. Release CI must protect all committed contracts, while consumer CI should use the exact verified stub revision.

### References

- [Spring Cloud Contract — Reference](https://docs.spring.io/spring-cloud-contract/reference/): producer/consumer model, Groovy/YAML DSL, Verifier, and Stub Runner.
- [Spring Cloud Contract — Consumer Driven Contracts](https://docs.spring.io/spring-cloud-contract/reference/using/cdc.html): roles in proposing contracts and verification.
- [Spring Cloud Contract — CDC with External Repository](https://docs.spring.io/spring-cloud-contract/reference/using/cdc-external-repo.html): coordinating consumer and producer via a contract repository.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): generating producer tests, build lifecycle, and stub packaging.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): `contractTest` task and build integration.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consumer testing against producer stub artifacts.
- [Martin Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html): using consumer requirements to establish interface commitments.

**Practical conclusion:** a good response does not stop at "the test is red". It states **what the consumer needs, what the producer does not yet satisfy, what the evidence is, what both teams decided, and what conditions turn the proposal into a verified contract**. That coordination lets Spring Cloud Contract catch incompatibilities early while keeping CI and published artifacts trustworthy.
