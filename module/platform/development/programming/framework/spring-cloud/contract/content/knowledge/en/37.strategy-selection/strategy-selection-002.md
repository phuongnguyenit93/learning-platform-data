# When Integration or End-to-End Testing Is a Better Fit

## Learning Objectives

**Spring Cloud Contract** helps producers and consumers agree on HTTP or messaging behavior using **Groovy/YAML DSL**. The producer uses contracts to generate tests verifying its implementation; the consumer uses stub artifacts and **Stub Runner** to test its client/handler against the published provider behavior.

However, contract tests do not prove that the entire system works properly when databases, brokers, gateways, authentication, networks, and multiple services participate together. There are questions that only **integration tests** or **end-to-end (E2E) tests** can reliably answer.

This article belongs to the **Strategy Selection** chapter, focusing on **when integration or end-to-end testing is a better fit**. After this article, you will be able to:

- Distinguish contract tests, integration tests, and E2E tests by the boundaries each type verifies.
- Recognize when generated producer tests and consumer stubs are sufficient.
- Choose integration tests when verifying databases, transactions, security filters, serialization, brokers, retries, outboxes, or multiple collaborating components.
- Choose E2E when verifying business workflows across a gateway and multiple services in a production-like environment.
- Combine Spring Cloud Contract with Spring Boot Test, Testcontainers, and controlled test environments.
- Avoid turning E2E into the sole test suite or using stubs to hide failures in real infrastructure.
- Design a test strategy suited to risk, cost, and feedback time.

> **Selection principle:** use the smallest testing layer that can prove the risk under consideration. When the risk lies in how real components collaborate, integration or E2E testing is a better fit than testing only one contract boundary with a stub.

## 1. Scenario: contracts PASS yet the order still fails to complete

Suppose an e-commerce system has:

- **Checkout Service:** receives order requests.
- **Inventory Service:** reserves stock.
- **Payment Service:** captures payment.
- **Order Service:** records order status.
- **Message broker:** publishes events so services coordinate.
- **API Gateway:** routes requests and enforces authentication.

The contract between Checkout and Inventory describes:

~~~http
POST /api/inventory/reservations HTTP/1.1
Content-Type: application/json

{"sku":"SKU-101","quantity":2}
~~~

Inventory returns:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"reservationId":"RSV-1001","status":"ACTIVE"}
~~~

Producer contract tests PASS. Consumer tests also PASS when Checkout calls the stub provided by Stub Runner.

Yet in a production-like environment, the order still fails because:

- The transaction recording the reservation committed, but the message was never published.
- Checkout and Inventory used the wrong broker topic.
- A database constraint rejects the SKU when real data differs from the fixture.
- The gateway strips an authentication header required by the service.
- A payment timeout leaves the workflow holding stock without releasing the reservation.
- Order Service receives the event but fails to deserialize a different schema version.

**Contract tests may still PASS** because they only prove the interactions described at the boundary. They do not automatically verify transactions, broker topology, gateways, or the full workflow.

This is when **integration tests** or **E2E tests** are needed.

## 2. Three test types answer three different questions

| Test type | Core question | Typical boundary | Real components |
|---|---|---|---|
| **Contract test** | Do two services adhere to the agreed interface? | One provider-consumer boundary | Producer implementation or consumer + stub |
| **Integration test** | Do real components collaborate properly? | One service and its dependencies, or a component group | DB, broker, web stack, adapters, services |
| **End-to-end test** | Can a user/system complete a workflow across services? | From entry point to business outcome | Multiple services and production-like infrastructure |

### Contract testing with Spring Cloud Contract

There are two main directions:

1. **Producer verification:** contract DSL generates tests that call the provider implementation and assert responses/messages against expectations.
2. **Consumer-side stub tests:** consumers use stub artifacts via Stub Runner to test clients/handlers against published provider behavior.

Contract tests catch **drift between producer and consumer** without starting the entire system on every run.

### Integration testing

Integration tests put real components into the same scenario. For example:

- Real Spring controller → real service → real PostgreSQL in Testcontainers.
- Application service → transactional outbox → real Kafka broker.
- Consumer listener → message converter → database projection.
- Security filter chain → JWT decoder/test identity → endpoint.

A test may mock a dependency outside its scope, but the boundaries being verified must run for real.

### End-to-end testing

E2E verifies a workflow across multiple services, typically starting at a public API/UI/gateway and ending at an observable business state.

For example: submitting a checkout request, reserving stock, capturing payment, receiving order confirmation, and verifying the final result.

E2E does not necessarily need full production infrastructure, but the environment must be close enough to verify the boundaries the test promises to check.

## 3. Contract tests are not miniature integration tests

A consumer test using Stub Runner may look like an integration test:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutInventoryClientContractTest {
    // Checkout client calls the HTTP stub.
}
~~~

The test may boot a Spring context and Checkout's real client. Yet Inventory is still replaced by a **stub**, so the test does not verify:

- The deployed Inventory controller.
- Inventory's database and its transactions.
- Inventory's security/filter chain.
- Inventory's broker or downstream dependencies.
- Network, DNS, gateway, and deployment routing between the two services.

It is a consumer-side contract/stub test, not a real integration test between Checkout and Inventory.

Similarly, a generated producer test may run the provider implementation in MockMvc or another test mode, which does not automatically prove that the database, broker, and supporting services are integrated.

**Annotation names or using `@SpringBootTest` do not determine the test type on their own.** Look at which dependencies are real, which are stubs/mocks, and which boundary the assertions prove.

## 4. Rules for selecting the testing layer

Use the following questions to select tests:

1. **Does the risk lie at an HTTP/message boundary already described by a contract?** Contract testing is usually the direct, fast choice.
2. **Does the outcome depend on multiple real components collaborating inside one service?** Choose integration testing.
3. **Does the failure only surface when multiple services, a gateway, a broker, and business processes operate together?** E2E or system-level integration testing is needed.
4. **Do you need to verify transactions, isolation, commit/rollback, or constraints?** Use database integration tests with a suitable real DB.
5. **Do you need to verify message publishing/consumption, retries, ordering, or dead-letter handling?** Use messaging integration tests with the appropriate broker/binder; if the workflow spans services, add E2E.
6. **Do you only need to ensure the consumer accepts a contract-compliant response?** A Stub Runner test is usually enough; no need to spin up the real producer just to repeat the assertion.
7. **Do you need to prove a complete user journey?** Select a handful of critical E2E scenarios instead of turning every data variation into E2E.

### Quick decision matrix

| Verification need | Contract | Integration | E2E |
|---|---:|---:|---:|
| HTTP method/path/status/body | **Very suitable** | Possible | Possible |
| Producer response satisfies DSL | **Very suitable** | Possible | Not the first choice |
| Consumer handles stub response | **Very suitable** | Possible | Possible |
| SQL constraints/transactions | Insufficient | **Very suitable** | Possible, but hard to diagnose |
| Spring security filter chain | Partially testable | **Very suitable** | Possible |
| Broker delivery/ack/retry | Message contracts help partially | **Very suitable** | When cross-service workflow is needed |
| Gateway routing/DNS/TLS | Insufficient | Possible in gateway integration | **Very suitable** |
| Multi-service workflow coordination | Insufficient alone | Possible by group | **Very suitable** |
| Critical user journeys | Insufficient | Possible | **Very suitable** |

This is a selection guide, not a rigid boundary. A test can combine multiple techniques; what matters is explicitly stating what it verifies.

## 5. When integration tests are a better fit: database and transactions

A contract describing request/response does not prove data is written correctly to the database or that transactions commit/roll back properly.

For example, a reservation needs to:

1. Read stock.
2. Check available-to-sell quantity.
3. Create the reservation.
4. Update reserved quantity.
5. Write an outbox event in the same transaction.

A contract test expecting `201` can PASS even when step 3 or step 5 is broken if the test base class mocks the service.

### Questions database integration tests must answer

- Are entities persisted with the right relationships and column mappings?
- Do unique constraints prevent duplicate reservations?
- Does the transaction roll back when a mid-flight operation fails?
- Does the isolation level allow overselling under two concurrent requests?
- Is the current migration schema-compatible?
- Does optimistic/pessimistic locking behave as intended?
- Do the outbox row and business row commit atomically?

### Example of a transactional service

~~~java
@Service
public class ReservationService {

    private final InventoryRepository inventoryRepository;
    private final ReservationRepository reservationRepository;
    private final OutboxRepository outboxRepository;

    @Transactional
    public Reservation reserve(String sku, int quantity) {
        Inventory item = inventoryRepository.findBySkuForUpdate(sku)
            .orElseThrow(() -> new SkuNotFoundException(sku));

        if (item.availableToSell() < quantity) {
            throw new InsufficientStockException(sku);
        }

        item.reserve(quantity);

        Reservation reservation =
            reservationRepository.save(
                Reservation.create(sku, quantity)
            );

        outboxRepository.save(
            OutboxEvent.stockReserved(reservation)
        );

        return reservation;
    }
}
~~~

This is an illustrative example; repository/entity/locking methods must be defined in the application.

Contract tests can verify the endpoint returns `201` and the response schema. Integration tests need to verify that **the inventory update, reservation row, and outbox row** are written properly in the same transaction.

### Why use a real DB in tests?

Mocking repositories can prove the service calls `save()`, but does not prove:

- Real SQL executes.
- Constraints are enforced.
- Transaction boundaries work.
- Locking/isolation is enforced by the database.
- Migrations create the right schema.

Using Testcontainers with a production-compatible database engine generally provides better evidence than H2 when behavior depends on PostgreSQL/MySQL-specific features.

## 6. Database integration test example with Testcontainers

This example assumes the project uses Spring Boot, Spring Data JPA, PostgreSQL, and Testcontainers JUnit integration. Dependencies/versions must be managed with a compatible BOM.

~~~java
@Testcontainers
@SpringBootTest
class ReservationDatabaseIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    ReservationService reservationService;

    @Autowired
    InventoryRepository inventoryRepository;

    @Autowired
    ReservationRepository reservationRepository;

    @Autowired
    OutboxRepository outboxRepository;

    @Test
    void reservationAndOutboxArePersisted() {
        inventoryRepository.save(
            Inventory.withStock("SKU-101", 10, 2)
        );

        Reservation reservation =
            reservationService.reserve("SKU-101", 2);

        assertThat(reservation.getId()).isNotNull();
        assertThat(inventoryRepository.findBySku("SKU-101"))
            .get()
            .extracting(Inventory::availableToSell)
            .isEqualTo(6);
        assertThat(reservationRepository.findById(reservation.getId()))
            .isPresent();
        assertThat(outboxRepository.findByAggregateId(reservation.getId()))
            .isNotEmpty();
    }
}
~~~

The example uses illustrative factory/repository methods; adjust them to your actual domain model. Tests need explicit migration/schema initialization, cleanup, and transaction setup.

### Assertions should focus on invariants

~~~text
availableToSell = stockOnHand - reserved
reservation.quantity = requested quantity
outbox.aggregateId = reservation.id
business row and outbox row commit together
~~~

If atomicity is required, add a test that forces an operation after updating inventory to fail and verifies the transaction rolls back both the business row and the outbox row.

**Never mock the outbox repository in a test claimed to verify transactionality between business state and the outbox.**

## 7. When transaction rollback is the focus

A contract can describe the status/error body when a request fails. However, a contract does not verify database state after failure.

For example, when an outbox insert fails:

~~~text
Before:
  SKU-101 stockOnHand = 10
  reserved = 2

Attempt:
  reserve SKU-101 quantity = 3
  update inventory succeeds
  insert outbox fails

Expected after rollback:
  reserved = 2
  no reservation row
  no outbox row
~~~

An integration test needs to:

1. Use a real database with a real transaction manager.
2. Seed baseline data.
3. Inject a controlled failure at the outbox step (e.g., a constraint/DB fault).
4. Invoke the transactional service.
5. Verify the exception is thrown.
6. Re-read the database in a new transaction/session.
7. Verify all changes were rolled back.

Only checking an exception from a mock does not prove rollback. Reading back inside the same persistence context/cache may show stale entity state; flush/clear or use a fresh transaction as appropriate.

## 8. When concurrency and locking are risks

A single HTTP contract request cannot prove the system prevents overselling when two requests arrive concurrently.

~~~text
Initial available stock = 5

Request A reserves 4
Request B reserves 4

Expected:
  at most one reservation succeeds
  final reserved quantity <= 5
  no negative available stock
~~~

An integration test can use two transactions/threads waiting on a barrier and calling the service concurrently, then assert database invariants afterward.

Things to be careful of:

- Use a real database engine compatible with production.
- Synchronize request start times instead of using sleep.
- Do not share an EntityManager/session across threads.
- Use finite timeouts and clean up data.
- Assert the final business outcome without depending on which request wins.
- Repeat in a dedicated test if races are rare; do not rely on a single run.

Contract tests remain useful to verify agreed success/conflict responses. Integration tests check real locking/transactions.

## 9. When the security filter chain and real identity matter

A contract can describe header/token assumptions or 401/403 responses. Yet a consumer stub does not prove authentication/authorization is configured properly in the service.

Integration tests are appropriate when verifying:

- The JWT decoder checks signature/issuer/audience.
- The Spring Security filter chain applies the right matchers.
- Roles/scopes map properly to authorities.
- Method security blocks unauthorized operations.
- CSRF/CORS/session behavior is correct.
- Service-to-service authentication works with the right identity.

### Security integration test example

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class InventorySecurityIT {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousRequestIsRejected() throws Exception {
        mockMvc.perform(get("/api/inventory/SKU-101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void inventoryReaderCanReadStock() throws Exception {
        mockMvc.perform(
                get("/api/inventory/SKU-101")
                    .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_inventory.read")
                    ))
            )
            .andExpect(status().isOk());
    }
}
~~~

This is an example of Spring Security test support. It verifies filter chain/authorization behavior within the test context, though `jwt()` typically creates an authentication object via test support; **it does not necessarily verify JWT signature validation from a real issuer**.

If the risk involves key rotation, a JWKS endpoint, issuer/audience validation, or TLS between the service and identity provider, add integration tests against a test issuer/JWKS or a controlled verification environment.

### When is E2E necessary?

If the goal is verifying a user logging in through an API Gateway, with tokens propagated through the gateway and multiple services, E2E through the gateway is more appropriate. A single filter-chain test does not test routing/forwarded headers across the whole system.

## 10. When serialization and framework integration are the focus

Contracts check schemas and matchers at boundaries. Yet bugs can emerge when framework components interact:

- Unregistered Jackson modules/custom serializers.
- Enum naming strategy differing between application and test.
- Missing `JavaTimeModule` or timezone configuration.
- Content negotiation selecting the wrong media type.
- Validation annotations not running through the right request pipeline.
- Global exception handlers mapping exceptions to the wrong body/status.
- Multipart/binary bodies or compression behaving differently.
- Message converters failing to read payloads/headers.

If generated producer tests use a test mode that does not boot the full web stack, integration tests with a real Spring application context may be necessary.

### Example checking JSON through the HTTP stack

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InventoryHttpSerializationIT {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void returnsExpectedJsonTypes() {
        ResponseEntity<JsonNode> response =
            restTemplate.getForEntity(
                "/api/inventory/SKU-101",
                JsonNode.class
            );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody().path("sku").asText())
            .isEqualTo("SKU-101");
        assertThat(response.getBody().path("available").isBoolean())
            .isTrue();
        assertThat(response.getBody().path("quantity").isIntegralNumber())
            .isTrue();
    }
}
~~~

The test runs the HTTP server and serialization/deserialization stack inside the Spring context. It does not by itself test gateways or deployment networking outside the process.

**Choosing a test mode:** use MockMvc/WebApplicationContext or random-port HTTP depending on risk. Not every contract needs an open TCP port; however, if the bug is in the server connector, servlet filters, compression, or the real HTTP stack, testing through the server is better.

## 11. When messaging delivery, retry, and dead-lettering are risks

Message contracts can verify payloads, headers, destinations/labels, and generated producer behavior in test setup. However, they do not by themselves guarantee the broker operates properly.

Integration tests with a real broker or broker test container are appropriate when verifying:

- Actual messages are published to the right topic/queue.
- Consumer groups receive the right messages.
- Acknowledgment/offset/ack modes are correct.
- Retry policies and backoff work.
- Dead-letter queues receive messages after the configured retry count.
- Ordering/partition keys are preserved within broker guarantees.
- Serialization/schema registry integration works properly.
- Transactional publishing/consumer acknowledgment.
- Redelivery does not create unintended duplicate side effects.

### Message workflow example

~~~mermaid
sequenceDiagram
    participant API as Inventory API
    participant DB as PostgreSQL
    participant O as Outbox publisher
    participant K as Kafka
    participant C as Checkout consumer
    API->>DB: Update stock + insert outbox
    O->>DB: Read pending outbox
    O->>K: Publish StockChanged
    K->>C: Deliver event
    C->>DB: Update checkout projection
    C-->>K: Commit offset/ack
~~~

Contract tests can verify the shape of `StockChanged`. Integration tests must verify **publish/delivery/ack** across the real broker and persistence.

### When is E2E better?

If the requirement is that checking out an order causes a StockChanged event to update a projection in Reporting Service, that is a cross-service workflow. You can use separate integration tests for publisher and consumer, plus an E2E scenario verifying the key business flow.

Not every message schema requires E2E. Use contract tests for schemas/boundaries and integration tests for broker mechanics.

## 12. When retry, timeout, and resilience behavior are the focus

A stub can simulate 500/timeout responses to test consumer error handling. Yet simple stub responses do not prove the full resilience configuration at runtime.

Integration tests are suitable for checking:

- Real HTTP client timeouts are enforced.
- Retries are bounded and only retry appropriate errors.
- Circuit breakers transition states properly.
- Bulkheads/connection pools are bounded.
- Fallbacks do not mask data errors or business rejections.
- Idempotency keys prevent duplicate side effects.
- Cancellation/timeouts do not leave dangling transactions.

| Question | Suitable layer |
|---|---|
| How does the consumer handle a 503 response per contract? | Consumer contract/stub test |
| Does the real HTTP client have properly configured timeout/retry/circuit breaker? | Integration test with controllable server |
| When Payment is slow, does the entire checkout workflow complete/compensate properly? | E2E or workflow integration test |

WireMock can serve as a controllable HTTP server in integration tests to inject response delays/failures. If verifying actual downstream service behavior is required, an appropriate environment is needed.

## 13. When gateway, DNS, TLS, and network topology are risks

Contract tests typically call the producer directly or a local stub. They do not verify:

- API Gateway routes to the right service.
- Path rewrites/prefix stripping work properly.
- TLS handshakes, certificate chains, and hostname verification.
- DNS/service discovery.
- Ingress/network policies.
- Reverse proxy headers and forwarded scheme/host.
- Load balancer/session behavior.
- Service-to-service mTLS.
- Rate limiting at the gateway.

Choosing the layer:

- **Gateway integration test:** real gateway + test upstream service to verify routes, filters, auth, and header forwarding.
- **E2E:** gateway + required services + production-like infrastructure to verify external workflows.
- **Contract test:** continues checking each service's API boundary independently of topology.

Do not use E2E to test every path-rewrite permutation when it can be checked quickly in a gateway integration suite. Keep a few representative flows traversing the gateway in E2E.

## 14. When multiple services coordinate a business workflow

E2E is a better fit when the requirement is **the end outcome of a chain of services**, rather than a single request/response.

Checkout example:

1. Client submits POST checkout through the gateway.
2. Checkout creates a pending order.
3. Inventory reserves stock.
4. Payment captures funds.
5. Order transitions to confirmed.
6. Notification is emitted.
7. Client queries the order and observes the final state.

Contract tests between Checkout–Inventory, Checkout–Payment, and Checkout–Order are still necessary to detect interface drift. Yet they do not prove the overall orchestration works.

Failures that only emerge when multiple services run together:

- Saga fails to trigger compensation when Payment fails.
- Inventory reservation expires while Order remains confirmed.
- Late or duplicate events cause state regressions.
- Correlation ID is dropped across a service hop.
- Retries between services create duplicate payments.
- A service publishes an event before its transaction commits.
- End-to-end timeout exceeds SLA even though individual calls pass.
- Service discovery/gateway routes to the wrong instance or version.

An E2E test should verify **key business outcomes and side effects**, such as order state, payment status, reservation state, and event notifications. Avoid asserting every internal log or call ordering that is not a business guarantee.
## 15. E2E should test workflows, not repeat every contract

A common mistake is writing E2E tests for every request/response variation of every service. The result is:

- Slow suites because many services must start.
- A single bug in one service breaks hundreds of tests at once.
- Hard to pinpoint which service caused the failure.
- Tests depend on shared seed data and shared environments.
- Teams avoid running tests frequently due to long feedback cycles.

Instead, use contract tests to cover interface variations at each boundary; integration tests to verify coordination mechanics inside each service; and keep E2E to **a small set of high-risk representative business journeys**.

Checkout example:

| Scenario | Preferred layer | Reason |
|---|---|---|
| Inventory returns 404 for unknown SKU | Contract | One clear provider-consumer interaction |
| Checkout parses wrong quantity type in response | Consumer contract/stub | Checks client schema handling |
| Inventory reservation and outbox must commit together | Integration | Needs real DB transaction |
| Kafka listener retry and dead-lettering | Messaging integration | Needs broker semantics |
| User checks out successfully via gateway, inventory, payment, and order | E2E | Needs cross-service workflow |
| Payment is declined and reservation is released | Integration + one critical E2E | Needs real compensation, though not every error code needs full E2E |

## 16. When E2E is a better fit than single-service integration tests

Integration tests inside one service can verify many internal components, but do not cover the full deployment topology.

E2E is worth using when requirements depend on:

- Real API Gateway or ingress routes.
- Service discovery/DNS and network policies.
- Authentication propagated across multiple services.
- Multiple services with differing versions/configurations.
- Sagas/orchestration/compensation.
- Eventual consistency across multiple datastores.
- Verifying overall business SLAs.
- Critical user journeys needing verification before release.

For example, Checkout's integration test can use a Payment stub and verify Checkout updates state when Payment succeeds. Yet only E2E with the real Payment service in a test environment checks that **Checkout calls the right endpoint, Payment records the transaction, and Order ultimately reaches the right state**.

### Selecting E2E by business risk

Not every workflow needs E2E. Prioritize:

1. Revenue-generating or transaction-critical flows.
2. Flows involving multiple services and compensation.
3. Flows that previously caused production incidents.
4. Flows with complex gateway/security/deployment routing.
5. Flows with critical data consistency/eventual consistency.
6. Flows required to verify a release candidate prior to promotion.

## 17. Designing E2E around observable business state

A good E2E test does not need to know every internal call. It needs to:

- Send input through a supported entry point.
- Obtain a correlation/order ID.
- Wait for the final outcome using a time-bounded condition.
- Read state through a public API or a controlled test observation interface.
- Verify business invariants.
- Clean up test data afterward.

For example:

~~~text
Given:
  SKU-101 has available stock 8
  test payment account is authorized

When:
  client submits checkout for quantity 2

Then:
  order becomes CONFIRMED
  payment becomes CAPTURED
  reservation becomes ACTIVE
  available stock becomes 6
  orderId is returned and can be queried
~~~

This is a **business-level scenario**. It does not force the test to assert Checkout calls Inventory before Payment in a fixed internal order, unless that ordering is a business requirement or consistency guarantee.

### Assertions to avoid

- Asserting internal thread names.
- Asserting log ordering.
- Asserting call counts on an internal helper that is not a contract.
- Asserting specific auto-increment IDs like `orderId=1`.
- Asserting an internal service must be called first if orchestration does not guarantee that order.
- Asserting fine-grained database schemas in E2E if integration tests already verify schemas.

These assertions make E2E brittle and turn internal refactorings into false breaking changes.

## 18. Handling eventual consistency in E2E

Many messaging workflows do not finish immediately when the HTTP request returns. Checkout may return `202 Accepted` or a `PENDING` status before consumers process events.

Do not write:

~~~java
Thread.sleep(5000);
assertThat(orderClient.get(orderId).status())
    .isEqualTo("CONFIRMED");
~~~

Fixed sleeps do not guarantee the system finished processing and lengthen the suite when events arrive early.

Use a **condition-based wait** with a deadline:

~~~java
await()
    .atMost(20, SECONDS)
    .untilAsserted(() -> {
        OrderView order = orderClient.getOrder(orderId);
        assertThat(order.status()).isEqualTo("CONFIRMED");
    });
~~~

The example requires the Awaitility dependency and a configured client. The `20 seconds` deadline is illustrative only and must be chosen based on the test environment SLA.

### Choosing the right wait condition

- Wait for the final business state, not a log message.
- Correlate by order ID/test ID, do not grab “the latest event”.
- Wait on the exact condition; avoid polling the whole database if a public API suffices.
- Use finite timeouts and report final state upon timeout.
- Do not turn long timeouts into a way to mask dead-lettering or stopped consumers.

### When should events be inspected directly?

If the goal of a test is broker delivery or event contracts, write a dedicated messaging integration test. User-journey E2E tests should focus on final outcomes observable by users/systems.

## 19. Test data and isolation in integration/E2E

Tests can pass in isolation yet fail in a suite due to shared databases, broker topics, or accounts.

### Data principles

- Give each test a unique correlation/order ID.
- Seed data has clear names and provenance.
- Never depend on records created by another test.
- Use dedicated accounts/SKUs/test tenants for the suite.
- Clean up by namespace or test run ID.
- Never use real production data.
- Never let a test suite delete data from a shared environment.

### Database isolation

- Testcontainers creates dedicated DBs per suite or class as appropriate.
- Migrations run just like the real application.
- Test data builders construct meaningful data.
- Rollback works only when requests run inside the same transaction context; separate HTTP server threads may commit independently.
- Parallel tests need separate schemas/databases or namespaces/locks.

### Broker isolation

- Separate topics/queues or consumer groups.
- Correlation IDs per test.
- Controlled offset/ack resets.
- Do not consume messages from other tests.
- Clean up topics/namespaces after tests per policy.

### Service environment isolation

If multiple E2E runs execute in parallel, use separate namespaces or deployments. One E2E test must not depend on a shared service whose state is mutated by another test.

## 20. Testcontainers keeps integration tests close to real dependencies

Testcontainers is helpful when running real dependencies without maintaining shared servers.

For example, you can launch:

- Production-compatible PostgreSQL/MySQL.
- Kafka or an appropriate broker.
- Redis.
- LocalStack or emulated cloud dependencies.
- WireMock containers when a controllable HTTP dependency is needed.

### When should Testcontainers be used?

| Need | Is Testcontainers useful? |
|---|---|
| SQL dialect/constraints/transactions | **Yes** |
| Broker semantics/serialization | **Yes** |
| Engine-dependent cache behavior | **Yes** |
| Testing an API client with custom responses | WireMock/Test server may suffice |
| Full production cluster with many services | Often needs a dedicated E2E environment |
| Testing real gateway/ingress/load balancers | Production-like deployed test environment is better |

Using containers alone does not make a test a good integration test. You must run the right dependencies and check the right invariants.

### Kafka container example (illustrative)

~~~java
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class InventoryMessagingIT {

    @Container
    static KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse("apache/kafka-native:3.8.0")
        );

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers
        );
    }

    @Test
    void publishesStockChangedEvent() {
        // Seed inventory, invoke application service,
        // consume event from the test topic and assert payload/headers.
    }
}
~~~

This is an illustrative skeleton. Container images/APIs and Kafka client versions must be chosen compatibly with the Testcontainers version and project environment; tests require real consumer/producer setup, topics, timeouts, cleanup, and assertions.

## 21. Integrating Spring Cloud Contract into the test strategy

Spring Cloud Contract remains central at service boundaries even when integration/E2E tests are added.

~~~mermaid
flowchart TD
    A["Contract DSL"] --> B["Producer generated tests"]
    A --> C["Consumer Stub Runner tests"]
    B --> D["Producer boundary verified"]
    C --> E["Consumer boundary verified"]
    D --> F["Integration tests with real dependencies"]
    E --> F
    F --> G["E2E critical business journeys"]
    G --> H["Release confidence"]
~~~

### What do contract tests protect?

- HTTP method/path/status/headers/body.
- Message destination/label/headers/payload.
- Dynamic values via matchers.
- Consumer assumptions about responses/messages.
- Producer compatibility with published contracts.

### What do integration tests add?

- Persistence/transactions.
- Spring application context, web stack, and security.
- Broker, serialization, retry/ack.
- Adapter/client configuration.
- Component interactions inside a service.

### What does E2E add?

- Gateway/network/service discovery.
- Multiple services and workflows.
- Business outcomes, compensation, and eventual consistency.
- Runtime configuration in a production-like environment.

**Do not delete contract tests after adding integration/E2E.** Integration/E2E tests are slower and harder to localize failures; contract tests remain fast feedback for interface drift.

## 22. Combining generated producer tests and integration tests

Generated producer tests can use a base class to prepare dependencies/state. Choose the base class/test mode according to the boundary you want to verify.

### Boundary-focused producer contract tests

For example, generated producer tests use MockMvc with prepared service dependencies so responses are reproducible. This fits verifying contracts at the controller/provider boundary.

### Producer integration tests checking real services

Add a separate test suite using a Spring context, real DB, and real repositories to verify transactions/persistence. There is no need to turn every generated contract test into a heavy container-backed test if most assertions only need the HTTP boundary.

### Why separate the two suites?

- Generated contract tests provide fast feedback and stay focused on contracts.
- Integration tests verify infrastructure/component interactions.
- When integration fails, the team can isolate DB/broker/config issues.
- When contracts fail, the team knows provider behavior drifted from the agreement.
- E2E covers only a small number of critical workflows.

### Illustrative source set layout

~~~text
src/
  main/
  test/
    java/
      ... unit and fast tests
  contractTest/
    java/
      ... generated Spring Cloud Contract tests
  integrationTest/
    java/
      ... database, broker, security integration tests
  e2eTest/
    java/
      ... deployed workflow tests
~~~

Source set/task names are project conventions, not generated automatically by Spring Cloud Contract. Gradle/Maven needs corresponding plugin/source-set/test-lifecycle configuration.

## 23. When is E2E unnecessary?

Do not write E2E just because a test sounds “more realistic”.

Contract or integration tests are usually enough when:

- Only schema/headers/status at a single boundary need verification.
- Only one service computing a business rule needs checking.
- The bug can be reproduced using DB/broker test containers within a single service.
- Request variants can be verified independently with contracts/stubs.
- No topology/deployment or cross-service workflow risks are involved.

For instance, 30 validation cases on the Inventory endpoint do not need 30 E2E tests. Use unit/contract/provider tests for input variations; add an integration test for the persistence/validation pipeline; keep one critical E2E happy path and one critical failure/compensation path.

### Costs of E2E

- Long environment setup.
- Many dependencies and many failure points.
- Complex test data.
- Flakiness from networking/timing.
- Hard to separate application bugs from infrastructure issues.
- High debugging and rerun time.
- Sensitivity to deployment versions/configurations.

E2E is valuable when the verified risk justifies those costs.

## 24. When contract testing remains the best choice

Use contract tests when the question is:

- Does the producer return status/body/headers per DSL?
- Does the consumer handle the provider's published response?
- Does the message payload preserve key fields/types/headers?
- Does a producer change break consumer expectations?
- Is the consumer relying on unagreed behavior?

There is no need to boot the entire system just to check a JSON response. Contract tests catch breaking changes early and allow producers/consumers to evolve independently.

### Example of a contract bug that should be caught

Producer changes:

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

to:

~~~json
{"sku":"SKU-101","availability":"IN_STOCK","units":8}
~~~

If the consumer expects `available`/`quantity`, consumer contract tests must fail against the new stub. This is a clear interface drift signal; no E2E is needed to discover it.

### Yet contract tests do not check all behavior

If the producer returns the right JSON while writing the wrong quantity to the DB, the contract can still PASS. That is an integration risk; verify persistence/invariants with integration tests.

## 25. When integration tests are still insufficient and E2E is needed

Integration tests in a single service or component group do not fully verify deployment topology and cross-service orchestration.

Choose E2E when:

- Gateway routes, auth propagation, or service discovery are mandatory conditions.
- Multiple services deploy independently with varying versions.
- Eventual consistency across multiple datastores must be verified.
- Sagas/compensation span multiple services.
- User journeys or business SLAs must be confirmed prior to release.
- A past production bug only occurred in an integrated environment.

For example, a Payment integration test can prove Payment service captures transactions successfully. It does not prove Checkout, Payment, and Order coordinate so an order is only confirmed after payment capture completes.

E2E verifies end-to-end outcomes across the chain, while contract tests protect each API/message boundary and integration tests protect internals inside each service.

## 26. Designing a layered pipeline

A balanced CI pipeline can be structured as:

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Unit + static checks"]
    B --> C["Producer contract tests"]
    B --> D["Consumer Stub Runner tests"]
    C --> E["Integration tests"]
    D --> E
    E --> F{"Critical integration PASS?"}
    F -->|No| X["Block"]
    F -->|Yes| G["Build deployable candidate"]
    G --> H["Deploy isolated test environment"]
    H --> I["Critical E2E journeys"]
    I --> J{"E2E PASS?"}
    J -->|No| X
    J -->|Yes| K["Release candidate"]
~~~

### PR feedback

- Unit/fast tests.
- Generated producer contract tests.
- Consumer tests with matching stub artifacts.
- Selective integration tests for recently changed code paths/risks.

### Main branch/nightly

- Full integration suite with DB/broker containers.
- Consumer compatibility against new candidate stubs.
- E2E critical journeys in an isolated environment.
- Smoke checks for gateway/network/deployment.

### Pre-release

- E2E critical business journeys.
- Contract compatibility with critical consumers.
- Migration/rollback tests if the release changes persistence.
- Operational smoke tests, auth, and networking.
- Artifact/version/provenance checks.

Not every organization needs these exact three stages; adjust them according to release velocity and environment cost.

## 27. Managing test flakiness and diagnosing failures by layer

When a suite fails, test names and logs should make it clear which layer failed.

| Failure | Symptoms | Investigation direction |
|---|---|---|
| Contract producer test | Generated assertion mismatch | DSL, producer response, matchers |
| Consumer stub test | Unmatched stub/request or client assertion | Stub version, mapping, consumer URL/body |
| DB integration | SQL/constraint/transaction failure | Migrations, DB engine, transactions, seed data |
| Messaging integration | Timeout/duplicate/ack failure | Broker, topic, consumer group, offset |
| Security integration | Unexpected 401/403 | Filter chain, test identity, JWT config |
| E2E | Workflow never reaches final state | Service logs, correlation ID, event flow, environment |
| Deployment smoke | Connection/routing/TLS failure | Gateway, DNS, certificates, network policy |

### Principles for reducing flakiness

- Use unique test data/correlation IDs.
- Never use fixed sleeps for asynchronous workflows.
- Use bounded awaits with deadlines.
- Do not share state across parallel tests.
- Do not depend on test execution order.
- Pin container images and toolchains.
- Use dedicated environments or namespaces.
- Retain logs, traces, and IDs for reproduction.
- Never retry until green and ignore the first failure.

**Never loosen contract matchers to fix integration/E2E failures.** If business behavior requires an exact quantity/status, keep that assertion; find the real state/broker/network root cause.

## 28. Practice exercise: choosing the appropriate test layer

### Case A — Producer changes a response field

Inventory changes `quantity` from number to string.

**Choice:** contract test.

Reason: this is a schema change at a provider-consumer boundary. Generated producer tests and consumer Stub Runner tests can detect it directly.

### Case B — Reservation DB write and outbox are not atomic

When the outbox insert fails, the reservation still exists.

**Choice:** database integration test.

Reason: a real transaction manager, database, and rollback are required. A single contract response does not prove atomicity.

### Case C — Two concurrent requests oversell stock

**Choice:** concurrency integration test with a production-compatible DB; supplement with a contract for status/conflict responses.

Reason: real locking/isolation and final business invariants need verification.

### Case D — Gateway strips Authorization header

**Choice:** gateway integration test; E2E if authentication propagation across multiple services must be verified.

Reason: testing the controller directly bypasses gateway routing/header forwarding.

### Case E — Payment fails yet order stays confirmed

**Choice:** E2E critical workflow, plus integration tests for Payment/Order state transitions.

Reason: the bug lies in cross-service orchestration/compensation.

### Case F — Consumer fails to parse stub response

**Choice:** consumer contract test with Stub Runner.

Reason: verifies the consumer handles the provider's published schema/behavior; no need to spin up all services.

### Case G — Kafka consumer fails to ack and message is redelivered

**Choice:** messaging integration test with an appropriate broker.

Reason: broker delivery/ack semantics must be verified. Only use E2E if redelivery breaks a cross-service business workflow.

### Case H — A checkout happy path needs pre-release verification

**Choice:** E2E critical journey.

Reason: business outcomes across gateway, Checkout, Inventory, Payment, and Order working together must be proven.

## 29. Test strategy review checklist

### Selecting the right boundaries

- [ ] Test questions are clearly stated in terms of behavior/risk.
- [ ] Contract tests are used for agreed API/message boundaries.
- [ ] Integration tests are used when real components/dependencies are needed.
- [ ] E2E is reserved only for critical workflows/topology/business risks.
- [ ] Annotation names are not used to infer test levels.
- [ ] Real dependencies, mocked/stubbed dependencies, and assertion scope are explicitly documented.

### Integration tests

- [ ] DB engine matches the production behavior under test.
- [ ] Migrations/schemas initialize just like the application.
- [ ] Transaction rollback/commit is read from durable state.
- [ ] Brokers/destinations/consumer groups are isolated.
- [ ] Retries/acks/DLQs are tested when required.
- [ ] Security filter chains/serialization/client configs run the real stack.
- [ ] Test data has clear seeding/cleanup.
- [ ] Tests can run safely both standalone and in parallel.

### E2E

- [ ] Starts from the real entry point under verification.
- [ ] Environment includes the required services/gateway/configuration.
- [ ] Tests use unique IDs/correlations.
- [ ] Eventual consistency is awaited via deadline-bounded conditions.
- [ ] Asserts business outcomes, not internal implementation.
- [ ] Has timeouts and diagnostics when workflows fail to complete.
- [ ] Cleans up data/environments safely.
- [ ] Covers only critical journeys rather than repeating masses of contract cases.

### CI and maintenance

- [ ] Contract tests run early to detect drift.
- [ ] Integration tests run on PR/main according to risk.
- [ ] E2E critical suite runs in an isolated environment.
- [ ] Toolchains, container images, and stub artifacts are pinned.
- [ ] Test reports clearly indicate the failing layer.
- [ ] Logs/traces include correlation IDs.
- [ ] Flaky failures are investigated, not masked by retries.
- [ ] Release gates combine contract + integration + E2E evidence by risk.

## 30. Key takeaways and references

**Contract tests, integration tests, and E2E tests complement one another.**

Spring Cloud Contract is a strong choice when verifying whether producers/consumers adhere to HTTP/message agreements. Integration tests fit better when risks lie in databases, transactions, security filters, serialization, brokers, retries, or collaborating real components. E2E fits when verifying gateways, networks, multiple services, sagas/compensation, eventual consistency, and business journeys.

Wider tests are not automatically better. Contract tests provide fast feedback at boundaries; integration tests verify real mechanisms; E2E verifies a small set of critical workflows in a production-like environment. Choose the layer based on **the risk to prove**, and keep assertions stable and diagnosable.

### References

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): contract DSL, producer verification, and Stub Runner.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): generated contract tests and stub generation.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consumer-side stubs.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): Spring Boot test support and application context.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): Testcontainers integration.
- [Testcontainers for Java](https://java.testcontainers.org/): running databases, brokers, and dependencies in tests.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): testing authentication/authorization in tests.
- [Awaitility](https://github.com/awaitility/awaitility): bounded waiting for asynchronous conditions.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): simulating HTTP dependencies in consumer/integration tests.

**Practical takeaway:** before writing a test, ask **“what bug do I need to catch, and which real components are needed to prove it?”** If it is interface drift, use a contract test. If it is transaction, broker, or security integration, use an integration test. If it is the outcome of a workflow spanning multiple services, choose E2E for the critical journey.
