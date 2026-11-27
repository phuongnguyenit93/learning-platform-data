# Practice Exercise: Designing a Test Strategy for a Multi-Service System

## Exercise Objectives

This exercise asks you to design an **executable test strategy** for a multi-service system using HTTP and messaging. You will apply **Spring Cloud Contract** to verify agreements between producers and consumers, then decide which parts require integration tests and which require end-to-end (E2E) tests.

The task is not to list as many tests as possible, but to pick **the right test type for each risk**, state which dependencies must run for real, which can be stubbed, which CI stage runs each test, and what evidence is sufficient to authorize a release.

After this lesson, you will be able to:

- Read a multi-service architecture and identify provider-consumer boundaries.
- Classify requirements into contract, integration, E2E, or unit tests.
- Decide which contracts should use Groovy/YAML DSL and Stub Runner.
- Design producer verification and consumer-side stub tests.
- Choose real databases, brokers, gateways, and services for integration/E2E.
- Identify business invariants spanning multiple services.
- Design test data, correlation IDs, isolation, and strategies for awaiting eventual consistency.
- Place tests across PR, main branch, nightly, and pre-release pipelines.
- Explain why E2E should not be used for every API variation.
- Deliver a test plan specifying coverage, owners, environments, and release gates.

> **Selection principle:** start from the business risks and invariants to protect. Choose the smallest test layer capable of proving that risk; expand to integration/E2E when real components must collaborate.

## 1. System context: Marketplace Checkout

You are on a platform team supporting a marketplace. The team is preparing to release a new version of the checkout flow. The system consists of multiple independent services, each with its own database, communicating via HTTP or Kafka.

| Component | Responsibility | Communication |
|---|---|---|
| **API Gateway** | Entry point, authentication, routing, rate limiting | HTTP |
| **Checkout Service** | Orchestrates checkout process and checkout state | HTTP, Kafka |
| **Inventory Service** | Reserves stock, releases reservations, manages stock | HTTP, Kafka |
| **Payment Service** | Authorizes/captures/refunds payments | HTTP |
| **Order Service** | Creates orders, manages order state | Kafka, HTTP queries |
| **Notification Service** | Sends email/SMS when orders reach eligible states | Kafka |
| **Kafka** | Transports events across services | Topics |
| **PostgreSQL** | Dedicated database per service | JDBC |

### Architecture diagram

~~~mermaid
flowchart LR
    U["Web / Mobile client"] --> G["API Gateway"]
    G --> C["Checkout Service"]
    C -->|HTTP reserve/release| I["Inventory Service"]
    C -->|HTTP authorize/capture| P["Payment Service"]
    C -->|Checkout events| K[("Kafka")]
    I -->|Stock events| K
    P -->|Payment events| K
    K --> O["Order Service"]
    O -->|OrderConfirmed| K
    K --> N["Notification Service"]
    C --- DC[("Checkout DB")]
    I --- DI[("Inventory DB")]
    P --- DP[("Payment DB")]
    O --- DO[("Order DB")]
~~~

The diagram shows the primary flows for test design. A real deployment may also include an outbox publisher, schema registry, service discovery, or external payment provider.

### Successful checkout flow

1. Client sends a request through the Gateway.
2. Gateway authenticates identity and forwards the request to Checkout.
3. Checkout asks Inventory to reserve stock.
4. Inventory creates a reservation and returns a reservation ID.
5. Checkout asks Payment to authorize/capture.
6. Checkout records the outcome and emits the corresponding event.
7. Order Service consumes the event and creates/updates the order.
8. Order Service emits the OrderConfirmed event.
9. Notification Service consumes the event and sends a notification.

### Failed payment flow

1. Checkout successfully reserves stock.
2. Payment declines or times out.
3. Checkout asks Inventory to release the reservation.
4. Checkout marks the checkout as failed or in a reconcilable state.
5. Order must NOT transition to CONFIRMED.
6. No order-confirmation success email is sent.

This flow may use a Saga/compensation pattern or an orchestration state machine. The exercise does not prescribe a specific implementation; you must identify which behaviors need testing.

## 2. Business requirements and invariants

Before picking tests, write down the rules the system must uphold. These form the basis for deciding which tests require real components.

### Checkout invariants

- A successful checkout must have a valid reservation.
- Never confirm an order unless payment is captured/authorized per policy.
- A failed payment must trigger reservation release or a trackable compensation state.
- Requests sharing the same idempotency key must never create two charges.
- Duplicate events must never create duplicate orders or duplicate notifications.
- `orderId`, `checkoutId`, and correlation IDs must be preserved across services.
- Final state must converge even when events arrive late or are retried.
- A canceled checkout must never revert to confirmed due to stale events.

### Inventory invariants

- Reservations must never make available stock negative.
- Cannot reserve more than available-to-sell quantity.
- Releasing a reservation affects only the matching reservation.
- Repeating the same release request must have defined idempotent behavior.
- Expired reservations must not count as active.

### Payment invariants

- One idempotency key must never be captured twice.
- Declined payments must never be recorded as captured.
- Refunds must reference the exact payment/order.
- Timeouts do not mean payment definitely failed; a reconcilable state is required.

### Order and Notification invariants

- An order becomes confirmed only after business preconditions are met.
- Duplicate or out-of-order events must not regress state.
- Success notifications are sent only for eligible states.
- Notification retries must not produce duplicate user messages when deduplication is required.

**Key takeaway:** HTTP contracts check statuses/bodies and event contracts check payloads/headers; transactions, idempotency, concurrency, and state convergence require appropriate integration tests or workflow tests.

## 3. Identifying provider-consumer boundaries

List each interaction and note who is the producer and who is the consumer. Roles flip according to data flow direction.

| Boundary | Producer | Consumer | Mechanism | Contract should protect |
|---|---|---|---|---|
| Reserve inventory | Inventory | Checkout | HTTP | Request, status, reservation ID, state |
| Release inventory | Inventory | Checkout | HTTP | Idempotency, not found, released state |
| Authorize payment | Payment | Checkout | HTTP | Payment ID, status, decline/error |
| Capture payment | Payment | Checkout | HTTP | Idempotency, amount, captured state |
| Checkout submitted | Checkout | Order | Kafka event | Event type, ID, checkout/order references |
| Stock reserved | Inventory | Checkout/Order if subscribed | Kafka event | Schema, headers, correlation |
| Payment captured | Payment | Order/Checkout if subscribed | Kafka event | Payment state/reference |
| Order confirmed | Order | Notification | Kafka event | Order ID, recipient reference, event version |

### Contracts do not need to exist for every internal method

Create contracts only at **boundaries consumed by multiple components/services or requiring independent compatibility**. There is no need to publish contracts for every private method or every repository call.

For each boundary, answer:

1. Does an independent consumer need to know this behavior?
2. Can consumer and producer deploy at different times?
3. Could a schema/path/status change break the consumer?
4. Are there error/edge cases the consumer depends on?
5. Are there message versioning or backward-compatibility requirements?

If the answers are mostly no, internal unit/integration tests may be a better fit.

## 4. Decomposing the test strategy by risk

| Layer | Goal | Marketplace example |
|---|---|---|
| **Unit** | Pure business rules, fast and isolated | Calculating totals, determining eligibility |
| **Contract** | Producer/consumer adhere to HTTP/message agreements | Inventory reservation, Payment response, OrderConfirmed event |
| **Integration** | Real components collaborate with DB/broker/security/web stack | Transactions/outbox, Kafka ack, DB locking |
| **E2E** | Business workflows spanning gateway and multiple services | Successful checkout, payment declined + compensation |

Do not pick a layer simply because a test is easy to write:

- Mocking a repository to test a SQL constraint is the wrong layer.
- Using Stub Runner to claim broker delivery is verified is the wrong scope.
- Using E2E to test 50 JSON validation variations makes suites slow and hard to diagnose.
- Using one service's integration test to claim gateway routes and service discovery work lacks evidence.

### Decision matrix for this system

| Risk | Unit | Contract | Integration | E2E |
|---|---:|---:|---:|---:|
| Wrong business calculation | **Primary** | Possible | Rarely needed | Selected flows |
| Inventory response schema changes | Insufficient | **Primary** | Possible | Not first choice |
| Payment client parses declined response | Possible | **Primary** | Possible | Possible |
| DB reservation transaction rollback | Insufficient | Insufficient | **Primary** | Hard to diagnose |
| Concurrency oversell | Insufficient | Insufficient | **Primary** | Selected journeys |
| Kafka serialization/delivery/ack | Insufficient | Schema contract | **Primary** | When workflow needs it |
| Gateway auth/routing | Insufficient | Partial | Gateway integration | **Primary** for journeys |
| Saga compensation | Unit for state machine | Contract for boundaries | Per-service integration | **Primary** for workflow |
| Duplicate notifications | Unit/idempotency logic | Event contract | Messaging integration | Representative E2E |

## 5. Selecting contracts to implement with Spring Cloud Contract

This exercise selects three representative contracts: Inventory HTTP, Payment HTTP, and Order messaging.

### Contract A — Inventory reservation HTTP

Inventory is the producer; Checkout is the consumer.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout can reserve two units of SKU-101'

    request {
        method 'POST'
        url '/api/inventory/reservations'
        headers {
            contentType(applicationJson())
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
            status: 'ACTIVE'
        )
    }
}
~~~

The contract protects method/path, request JSON, and the success response. Separate contracts should describe insufficient stock, unknown SKUs, or idempotent retries if consumers rely on those behaviors.

### Contract B — Payment decline HTTP

Payment is the producer; Checkout is the consumer.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Payment provider reports a declined authorization'

    request {
        method 'POST'
        url '/api/payments/authorize'
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-1001',
            amount: 250000,
            currency: 'VND',
            idempotencyKey: 'checkout-1001'
        )
    }

    response {
        status 402
        headers {
            contentType(applicationJson())
        }
        body(
            paymentId: 'PAY-1001',
            status: 'DECLINED',
            reasonCode: 'INSUFFICIENT_FUNDS'
        )
    }
}
~~~

Status and error body represent the agreed behavior in this example. If the real API uses 200 with a business status or 409/422, the contract must reflect the real agreement.

### Contract C — OrderConfirmed message

Order is the producer; Notification is the consumer.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'order_confirmed'

    input {
        triggeredBy('publishOrderConfirmed()')
    }

    outputMessage {
        sentTo('order-events')
        headers {
            messagingContentType(applicationJson())
        }
        body(
            eventType: 'OrderConfirmed',
            eventId: 'EVT-1001',
            orderId: 'ORD-1001',
            checkoutId: 'CHK-1001'
        )
    }
}
~~~

This illustrates a message contract. The producer base class must supply the trigger method and matching test messaging configuration. Destinations/headers/payloads must match the real broker abstraction.

## 6. Producer verification and consumer stub tests

For the three contracts above, design two-sided tests.

### Producer side

- Inventory runs generated tests for reservation success/error contracts.
- Payment runs generated tests for authorized/declined behavior.
- Order runs generated message tests for `order_confirmed`.
- Base classes stand up the implementation under verification.
- Producer test reports record executed test counts and PASS results.
- Stub JARs are produced from the exact same revision as the verified implementation/contracts.

### Consumer side

- Checkout uses Stub Runner to load Inventory stubs and Payment stubs.
- Notification uses message stubs/`StubTrigger` to test its handler against `order_confirmed`.
- Real application consumer clients/handlers are invoked.
- Assertions check business-relevant fields/statuses/error codes.
- Tests pin explicit versions/classifiers; never use `latest` to mask version skew.

Stub Runner ID example:

~~~java
@AutoConfigureStubRunner(
    ids = {
        "com.example:inventory-service:2.3.0:stubs:0",
        "com.example:payment-service:1.8.0:stubs:0"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutContractTest {
    // Use @StubRunnerPort or StubFinder to obtain the stub endpoint.
}
~~~

This example assumes the artifact coordinates/versions are already published/installed in the local Maven repository. In multi-job CI, use `REMOTE` with a staging repository and explicitly passed candidate versions.

**Contract tests do not need to start all of Order, Notification, Kafka, and production DBs.** They test Checkout's interface boundaries with Inventory/Payment and Notification's handler against the message contract.

## 7. Risks requiring integration tests

| Service | Real dependencies | What to verify |
|---|---|---|
| Checkout | PostgreSQL | Checkout state, idempotency keys, transactions |
| Inventory | PostgreSQL | Reservations, locking, stock invariants, rollbacks |
| Payment | PostgreSQL + payment sandbox/test server | Payment state, idempotency, timeouts/reconciliation |
| Order | PostgreSQL + Kafka | Event consumption, projections, duplicates/out-of-order |
| Notification | Kafka + email sandbox | Listeners, retries, DLQ, duplicate suppression |
| Gateway | Gateway runtime + test upstream service | Routing, auth, path rewrites, headers |

### Inventory integration tests

Use a production-compatible DB to verify:

- Successful reservations update available quantity.
- Two concurrent reservations do not oversell.
- Repeated reservation releases do not over-increment available quantity.
- Mid-transaction DB failures roll back cleanly.
- Unique/idempotency constraints are enforced.

### Checkout integration tests

Use a controllable HTTP server for Payment/Inventory or test doubles for out-of-scope dependencies, while keeping Checkout's DB and transactions real. Verify:

- Same idempotency key does not create duplicate checkouts/payments.
- Declined payment triggers reservation release.
- Timeouts put checkout into a reconcilable state.
- Events/outbox records are published only on valid committed state.

### Messaging integration tests

Use real Kafka/brokers or suitable containers to verify:

- Messages reach the right topic.
- Consumer groups receive events.
- Deserializers read schemas/headers.
- Acks/offsets/retries/DLQs follow policy.
- Duplicate events do not create duplicate orders/notifications.
- Correlation IDs are preserved.

## 8. Risks requiring E2E

Choose a few high-value business scenarios.

### E2E 1 — Successful checkout

Input:

~~~json
{
  "customerId": "CUS-101",
  "sku": "SKU-101",
  "quantity": 2,
  "paymentToken": "tok_test_approved",
  "idempotencyKey": "e2e-checkout-001"
}
~~~

Expected business outcome:

- Gateway accepts the request and routes to the right service.
- Checkout creates an order/checkout.
- Inventory holds an active reservation for quantity 2.
- Payment is captured/authorized per flow.
- Order transitions to CONFIRMED.
- Notification event is processed.
- Client can query the order using the returned ID.

### E2E 2 — Payment declined and compensation

Input uses a test payment token that declines.

Expected:

- Checkout does not transition the order to confirmed.
- Reservation is released or enters a trackable compensation state.
- No success confirmation notification is sent.
- Payment has declined status.
- Final workflow state is observable via API.

### E2E 3 — Duplicate checkout request

Send the exact same request and idempotency key twice.

Expected:

- Only one business order exists.
- Payment is not captured twice.
- Two independent reservations are not created.
- Repeated request response follows agreed semantics (same resource or replayed response).
- Events/notifications are not duplicated beyond policy.

There is no need for hundreds of E2E variants for every status code. Contract and integration tests cover the details; E2E verifies high-risk cross-service workflows.

## 9. Distinguishing real tests from stub-based tests

| Scenario | Real components | Can be stubbed/mocked |
|---|---|---|
| Checkout consumer contract | Checkout app/client | Inventory, Payment via Stub Runner |
| Inventory producer contract | Inventory provider implementation | External dependencies outside contract |
| Payment producer contract | Payment provider implementation | External payment processor |
| Inventory DB integration | Inventory + PostgreSQL | Never mock repository/DB |
| Checkout compensation integration | Checkout + DB + controllable downstream | Payment/Inventory HTTP if testing only orchestrator state |
| Kafka delivery integration | Producer/consumer + Kafka | External services outside scenario |
| E2E checkout | Gateway + Checkout + Inventory + Payment + Order + required broker | External email/payment networks may use sandboxes if not under test |

A test is trustworthy when **it clearly states what is real and what is replaced**. Never call a Checkout + Inventory-stub test a marketplace E2E test.

## 10. Exercise Part A — Build the test portfolio

Based on the architecture and invariants above, list at minimum:

- 5 unit tests for business rules.
- 4 producer contract test groups.
- 3 consumer contract test groups.
- 5 integration test groups.
- 3 E2E journeys.

For each test, record:

| Field | Question |
|---|---|
| Risk | What bug could happen? |
| Boundary | Which components/services are involved? |
| Test level | Unit, contract, integration, or E2E? |
| Real dependencies | Which DB/broker/gateway/services must be real? |
| Test doubles | Which components can be stubbed/mocked? |
| Assertion | Which invariant/behavior must hold? |
| CI stage | PR, main, nightly, or pre-release? |
| Owner | Which team is accountable? |

Hint: Inventory oversell tests need a real DB and concurrency; JSON field renames belong primarily in contracts; payment-decline compensation across Checkout–Inventory–Order needs integration plus at least one representative E2E scenario.

## 11. Exercise Part B — Classify 12 changes

Choose the primary test level and explain why. A change may need multiple layers, yet pinpoint the layer that catches the risk most directly.

| # | Change | Priority test level |
|---:|---|---|
| 1 | Inventory changes response quantity from number to string | ? |
| 2 | Inventory SQL migration changes reservation unique constraint | ? |
| 3 | Payment client fails to retry HTTP 503 per policy | ? |
| 4 | Kafka consumer group is misconfigured | ? |
| 5 | Gateway rewrites /checkout/** to the wrong path | ? |
| 6 | Order event renames the orderId field | ? |
| 7 | Duplicate OrderConfirmed sends two emails | ? |
| 8 | Two concurrent checkouts reserve the last remaining stock | ? |
| 9 | JWT scope checkout.write fails to map to an authority | ? |
| 10 | Payment is declined yet order remains confirmed | ? |
| 11 | Notification email template displays wrong currency | ? |
| 12 | Checkout request is missing a required field | ? |

## 12. Exercise Part C — Design the CI pipeline

Design a pipeline across two independent repositories: `inventory-service` (producer) and `checkout-service` (consumer).

Requirements:

1. Inventory producer tests must PASS before publishing stubs.
2. Stub JAR has an explicit version/classifier.
3. Checkout pulls the exact candidate artifact from staging.
4. Consumer tests run in a clean environment.
5. Candidate cannot promote if consumer compatibility fails.
6. Main branch runs integration tests with PostgreSQL/Kafka.
7. Pre-release runs E2E checkout success and payment decline.
8. Logs record contract revision, producer revision, consumer revision, and artifact digest.

### Suggested flow

~~~mermaid
flowchart TD
    A["Inventory PR"] --> B["Generate + run producer tests"]
    B --> C{"PASS and test count valid?"}
    C -->|No| X["Block"]
    C -->|Yes| D["Package inventory stubs"]
    D --> E["Publish unique candidate"]
    E --> F["Checkout clean consumer job"]
    F --> G["Stub Runner resolves exact candidate"]
    G --> H["Checkout consumer contract tests"]
    H --> I{"PASS?"}
    I -->|No| X
    I -->|Yes| J["Promote candidate"]
    J --> K["Main/nightly integration suites"]
    K --> L["Pre-release E2E journeys"]
~~~

Never use a mutable version or `latest` to pass artifacts between two repositories. Candidate versions/digests must be passed explicitly by CI.

## 13. Reference solution: test portfolio

A sound strategy might look like:

### Unit tests

1. Checkout calculates totals and discounts.
2. Inventory checks available quantity.
3. Payment maps external decline codes to domain statuses.
4. Order state machine rejects CANCELLED → CONFIRMED.
5. Notification deduplication key is generated properly.

### Producer contract tests

1. Inventory reservation success/error.
2. Inventory release success/idempotent behavior.
3. Payment authorize/capture success/declined.
4. Order `OrderConfirmed` message payload/headers.

Generated tests run in producer builds. Base classes must stand up implementations in the appropriate test mode.

### Consumer contract tests

1. Checkout Inventory client uses reservation stubs.
2. Checkout Payment client handles authorized/declined stubs.
3. Notification handler processes `OrderConfirmed` message stubs.

Use Stub Runner with explicit artifact coordinates; never use stubs to conclude production database/broker mechanics work.

### Integration tests

1. Inventory PostgreSQL transactions/locking/oversell.
2. Checkout idempotency + reservation/payment state transitions.
3. Checkout outbox commit/publish boundary.
4. Order Kafka consumer + database projection + duplicate events.
5. Notification Kafka retry/DLQ/deduplication.

Suites can be split by service to reduce debugging time.

### E2E tests

1. Checkout success.
2. Payment declined → reservation released, order not confirmed.
3. Duplicate checkout request → one order and one payment.

This is a reference portfolio. If the system does not yet have an outbox or Notification does not use Kafka, adapt to the real architecture.

## 14. Reference solution: classifying the 12 changes

| # | Change | Primary layer | Why |
|---:|---|---|---|
| 1 | quantity number → string | **Contract** | Schema/type changed at Inventory–Checkout boundary |
| 2 | SQL unique constraint | **Integration** | Needs real DB/migrations |
| 3 | HTTP 503 retry policy | **Integration** | Needs real HTTP client/resilience configuration |
| 4 | Wrong Kafka consumer group | **Messaging integration** | Needs broker and listener runtime |
| 5 | Wrong Gateway path rewrite | **Gateway integration/E2E** | Needs real routes/filters |
| 6 | orderId field renamed in event | **Message contract** | Event schema drift |
| 7 | Duplicate event sends two emails | **Messaging integration** | Needs real delivery/retry/dedup behavior |
| 8 | Two checkouts reserve last stock | **Concurrency integration** | Needs DB locking/isolation |
| 9 | Wrong JWT scope mapping | **Security integration** | Needs filter chain/authority mapping |
| 10 | Declined yet order confirmed | **E2E + workflow integration** | Cross-service compensation/state coordination |
| 11 | Email template wrong currency | **Component/integration test** | Renderer/template and data mapping |
| 12 | Request missing required field | **Contract/provider test** | Validation/status/error body at API boundary |

Supplemental tests: #1 adds consumer Stub Runner tests against the new candidate; #5 has gateway integration plus critical E2E journeys; #10 still needs contract tests for each error boundary.

## 15. Reference solution: CI pipeline

### Producer pull request

- Check out the exact contract revision.
- Resolve pinned JDK/build tool/plugins.
- Discover contracts; fail if count is unexpectedly zero.
- Generate and run producer contract tests.
- Package stub JAR.
- Inspect classifier, mappings, and fixtures.
- Publish candidate with unique version to staging.
- Record coordinates, producer SHA, contract SHA, and digest.

### Consumer pull request

- Receive candidate coordinates/digest from producer pipeline.
- Use REMOTE Stub Runner in consumer tests.
- Download using read-only CI credentials into a clean environment.
- Verify digest.
- Run consumer contract tests and assert behavior.
- Report exact resolved version/digest.

### Main/nightly

- Integration suites with PostgreSQL/Kafka containers.
- Verify transactions, idempotency, retries, DLQs, and projections.
- Run compatibility suite for critical consumers.
- Record traces/logs with correlation IDs.

### Pre-release

- Deploy candidates into an isolated environment.
- Run E2E success/declined/duplicate scenarios.
- Verify gateway/auth/networking and eventual consistency.
- Promote the exact artifact tested by consumers, preserving digest.
- Block release if any critical invariant fails.

## 16. Reference solution: why not use E2E for every case?

Suppose there are 30 request validation variants, 10 error responses, 5 matcher styles, and 3 business workflows. If all were E2E:

- Every test needs many services and data setups.
- One failing dependency breaks dozens of tests.
- Hard to tell whether the bug is contract, service, broker, or gateway.
- Runtime and maintenance soar.
- Developer feedback slows down.

Sensible allocation:

- 30 validation variants: unit/provider/contract tests.
- 10 error response variants: producer contracts + consumer stub tests.
- 5 matcher/schema behaviors: contract tests.
- 3 critical workflows: E2E.
- DB/broker/security mechanics: integration suites.

**E2E verifies a handful of meaningful journeys, not the entire contract matrix.**

## 17. Anti-patterns to avoid

### E2E only, no contract tests

API drift surfaces only in slow suites, making it hard to identify which provider/consumer disagreed. Keep contract tests at boundaries.

### Stub Runner only, no integration tests

Consumers may handle stubs cleanly while real database transactions, broker delivery, or security filter chains fail. Stubs do not prove real dependencies work.

### Calling consumer + stubs “E2E”

If Inventory/Payment are replaced by stubs, the test does not verify workflows through real providers. Name the scope accurately so readers understand the evidence.

### Mocking the database in transaction tests

Mocked repositories do not test SQL, constraints, isolation, or rollbacks. Use a real DB when that behavior is the risk.

### An E2E test asserting too many internal details

Asserting logs, internal call order, or auto-increment IDs makes tests brittle. Prefer business state and observable outcomes.

### Fixed sleeps for events

Sleeps do not guarantee events finished processing. Use correlation IDs and bounded condition waits.

### Shared data/topics across parallel tests

Tests can steal each other's events or mutate the same rows. Isolate data, consumer groups, topics, or namespaces.

### Using latest in compatibility pipelines

Consumers can download different versions across two runs. Pin explicit versions/digests and pass candidates unambiguously.

## 18. Reviewing a team's proposed strategy

A strong proposal should answer:

1. **Business risks:** which invariants could be violated?
2. **Service boundaries:** which producers/consumers need contracts?
3. **Test portfolio:** is each risk caught at unit, contract, integration, or E2E?
4. **Real dependencies:** which DB/broker/gateway must be real?
5. **Test doubles:** which dependencies are stubbed and why?
6. **Data isolation:** how are test IDs, seeds, cleanup, and namespaces handled?
7. **Asynchronous behavior:** how are correlation and timeouts controlled?
8. **CI placement:** what runs on PR/main/nightly/pre-release?
9. **Ownership:** which teams maintain contract/integration/E2E suites?
10. **Release gates:** what evidence must PASS before promotion?

### Review table template

| Risk | Test | Level | Real dependencies | CI stage | Owner | Pass evidence |
|---|---|---|---|---|---|---|
| Inventory schema drift | Generated producer + Checkout stub test | Contract | Producer/consumer code, stub artifact | PR | Inventory + Checkout | Reports PASS, exact stub version |
| Reservation oversell | Concurrent reservation test | Integration | Inventory + PostgreSQL | Main/nightly | Inventory | Stock invariant holds |
| Payment decline compensation | Checkout workflow test | Integration + E2E | Checkout, Inventory, Payment, Order | Pre-release | Order not confirmed, reservation released |
| Duplicate OrderConfirmed | Consumer dedup test | Integration | Kafka + Order/Notification persistence | Nightly | One business effect |
| Gateway auth propagation | Gateway test | Integration/E2E | Gateway + identity/test issuer | Pre-release | Auth policy enforced |

## 19. Exercise completion checklist

- [ ] Drew the service map and HTTP/message boundaries.
- [ ] Documented critical business invariants.
- [ ] Identified producer and consumer for each contract.
- [ ] Selected representative contracts for Spring Cloud Contract.
- [ ] Designed producer verification and consumer Stub Runner tests.
- [ ] Selected integration tests for DB/transactions/brokers/security.
- [ ] Selected a handful of critical E2E journeys.
- [ ] Distinguished real dependencies from test doubles.
- [ ] Specified data isolation, correlation IDs, and bounded waits.
- [ ] Allocated tests across PR/main/nightly/pre-release.
- [ ] Included negative/failure scenarios.
- [ ] Assigned owners and pass evidence.
- [ ] Avoided E2E for API variants testable at lower layers.
- [ ] Recorded stub versions/digests so consumers test exact candidates.

## 20. Key takeaways and references

A strategy for a multi-service system does not start with “how many tests do we need?”—it starts with **“which business invariants can break, and which real components are required to prove them?”**

- Use **Spring Cloud Contract** for HTTP/message agreements between producers and consumers.
- Use **integration tests** for databases, transactions, security, brokers, retries, idempotency, and real component interactions.
- Use **E2E tests** for selected workflows spanning gateways/multiple services, especially compensation and eventual consistency.
- Use **unit tests** for pure logic to get fast feedback.
- Tie every test to explicit risks, owners, CI stages, and evidence.

Contracts, integration, and E2E complement one another. Contract tests let services evolve independently; integration tests verify real mechanics; E2E verifies system-wide business outcomes. A strong portfolio picks the right layer instead of cramming everything into a single suite.

### References

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): DSL, producer verification, and Stub Runner.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML contracts and matchers.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): generated producer tests and stub packaging.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consumer-side stub testing.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): Spring Boot test support.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): Testcontainers integration.
- [Testcontainers for Java](https://java.testcontainers.org/): database, Kafka, and dependency containers.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): authentication/authorization tests.
- [Awaitility](https://github.com/awaitility/awaitility): deadline-bounded asynchronous condition waiting.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): HTTP stubs and request matching.

**Practical takeaway:** deliver a test strategy where every critical risk has a concrete test layer, dependencies, owner, CI stage, and PASS evidence. If an integration/E2E test checks the same schema assertion already well-caught by a contract test, explain the added value of that broader test; if there is none, push the assertion down to the faster layer.
