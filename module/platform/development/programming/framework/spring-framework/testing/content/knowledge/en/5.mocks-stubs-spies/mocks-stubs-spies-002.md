# Choosing Components to Replace at Test Boundaries

When writing tests, an important decision is determining which components should run for real and which should be replaced with a mock, stub, spy, or fake. This decision directly affects what the test proves. If too much is replaced, the test may only verify how mocks are called without proving application behavior. If all external dependencies are kept, tests can become slow, hard to repeat, and fail due to network, time, or shared systems.

There is no rule such as "always mock repositories" or "never mock services." The right choice depends on the behavioral boundary under test, the required confidence level, and the type of evidence needed. A component may be kept real in an integration test while replaced with a fake in a unit test of the same business logic.

This lesson focuses on making that decision in the context of Spring Framework Testing: identifying the system under test, classifying dependencies, choosing test double types, designing tests at each Spring layer, and avoiding replacements that weaken evidence.

## 1. Start with the question: what does the test need to prove?

Before creating mocks or configuring a Spring context, write one sentence describing the behavior to verify. For example:

> When a customer orders an in-stock product and payment is approved, the system saves the order and publishes an OrderPlaced event.

From this requirement, we can identify:

- The object under test is the application service handling order placement.
- Key outcomes include saving the order with correct data and publishing the event.
- Payment depends on an external system.
- Product and order data may come from a persistence adapter.
- Order creation time may depend on the system clock.

If the goal is solely to verify the business decisions of the application service, we do not need to start a real database or call a real payment gateway. However, if the goal is to verify entity mapping, transactions, or queries, replacing the repository with a mock removes the exact part that needs testing.

Clearly identify three elements:

1. **System under test (SUT):** the component whose behavior is the focus.
2. **Collaborators:** the components the SUT needs to complete the behavior.
3. **Boundary:** the point where the behavior under test crosses to interact with another system, such as a database, HTTP service, message broker, file system, or clock.

A test boundary does not have to match a single class boundary. A unit test can test a service together with several real domain objects. An integration test can test a controller, service, repository, and database working together. The boundary must be chosen according to what you want to prove.

### 1.1. Distinguishing the object under test from collaborators

Suppose a service has the following dependencies:

~~~java
class OrderApplicationService {
    private final ProductCatalog productCatalog;
    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;
    private final OrderEventPublisher eventPublisher;
    private final Clock clock;

    // Constructor and business methods
}
~~~

When testing order placement rules, OrderApplicationService is the SUT. The remaining interfaces are collaborators. However, not all collaborators have to be replaced in the same way:

| Collaborator | Characteristics | Potentially suitable choice |
| --- | --- | --- |
| ProductCatalog | Provides product data | Fake or stub in unit tests; real adapter in integration tests |
| PaymentGateway | Calls external payment system | Stub responses and mock meaningful interactions; mock server in adapter tests |
| OrderRepository | Saves and reads orders | Fake for application logic tests; real database for persistence tests |
| OrderEventPublisher | Publishes events outward | Recording fake or mock; real broker in integration tests where needed |
| Clock | Provides current time | Fixed Clock for deterministic results |

This table is not a fixed configuration. If a test aims to prove that the repository generates the right SQL or relationship mapping, OrderRepository must be tested with the real persistence implementation. If a test aims to confirm how the service reacts when payment is declined, a stubbed response from PaymentGateway is sufficient.

### 1.2. Write test criteria before choosing tools

Concrete criteria help avoid picking mocks simply because a tool is available. For example:

- When payment is approved, the service creates an order with the right customer, product, and total amount.
- When payment is declined, the service does not save the order in a paid state.
- The OrderPlaced event is published only after the order reaches the state specified by business rules.
- The order creation timestamp comes from the provided Clock.

From these criteria, we know we need to control the payment outcome, observe saved data, observe events, and fix time. We do not yet need to decide that everything is a Mockito mock. An in-memory repository and an event-recording publisher can provide stronger evidence than a complex chain of mocks.

## 2. What is a test double?

A test double is an object that replaces a real collaborator in a test. It plays a role similar to a stunt double: providing the portion of behavior needed so the test can focus on its chosen goal.

Common types include:

- **Dummy:** an object passed to satisfy a method signature but never used in that scenario.
- **Stub:** returns pre-prepared data or results.
- **Mock:** records interactions and allows checking expected calls.
- **Spy:** observes or wraps a real object, sometimes overriding part of its behavior.
- **Fake:** implements a simplified yet working version of a collaborator, such as an in-memory repository.

In practice, a library like Mockito can create stubs, mocks, and spies. The annotation or API name does not determine the test's intent. What matters is whether the test uses that object to supply results, verify interactions, or observe behavior.

### 2.1. Stub: controlling collaborator answers

A stub is suitable when the SUT needs to receive a specific result to traverse a business branch. For example, PaymentGateway can return payment approved or declined.

~~~java
when(paymentGateway.charge(any(PaymentRequest.class)))
    .thenReturn(PaymentResult.approved("PAY-100"));
~~~

In this situation, what matters is that the SUT reacts properly to the provided result. If the test does not need to verify exactly how many times the collaborator was called, adding verify may add no value.

You can stub:

- Success or error responses from external services.
- Query results needed for a business branch.
- Fixed times or pre-prepared data.
- Rare situations that are hard to reproduce with real systems.

A stub should not re-implement the SUT's own algorithm. If a stub computes the same formula as production code, the test risks confirming a wrong result in the same way.

### 2.2. Mock: verifying meaningful interactions

A mock is suitable when an outgoing call is part of the behavior to protect. For example, when requirements specify that the system must send a payment command with the exact amount and idempotency key, we can verify the command sent to PaymentGateway.

~~~java
ArgumentCaptor<PaymentRequest> requestCaptor =
    ArgumentCaptor.forClass(PaymentRequest.class);

verify(paymentGateway).charge(requestCaptor.capture());

assertThat(requestCaptor.getValue().amount())
    .isEqualByComparingTo(expectedTotal);
~~~

Mocks are often also configured to return data, so a mock can simultaneously act as a stub. However, separate the two intents when reading a test:

- Setup: providing responses for the SUT to process.
- Verification: confirming an important interaction occurred or did not occur.

Not every call needs verify. If the test verifies that the final order has the right data and no contract requires a specific call sequence, verifying every getter, mapper, or repository method couples the test to implementation details.

### 2.3. Spy: observing a real object

A spy wraps a real object so calls can be observed or a specific method overridden. It is useful in certain transitional situations or when you need to observe a real collaborator without easily introducing another observation point.

~~~java
List<String> names = new ArrayList<>();
List<String> namesSpy = spy(names);

namesSpy.add("Spring");

verify(namesSpy).add("Spring");
assertThat(namesSpy).containsExactly("Spring");
~~~

Spies can make tests harder to understand when they mix real logic with overridden methods. With Mockito, writing when(spy.method()) can invoke the real method during setup. When you need to avoid that call, the doReturn(...).when(spy)... API may be more appropriate.

Spies also introduce risks when used with classes that have complex state, final methods, internal self-calls, or side effects. If you need to replace a collaborator, consider creating a clear interface/port or using a fake. If you need to test a class, prefer calling its public API and observing the outcome.

### 2.4. Fake: a simplified version with behavior

A fake is useful when you need a working collaborator without depending on real infrastructure. For example, InMemoryOrderRepository can store orders in a Map:

~~~java
class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.id(), order);
        return order;
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }

    int count() {
        return orders.size();
    }
}
~~~

Fakes can make service tests fast and readable. However, they only prove service behavior when working against the OrderRepository contract implemented by the fake. They do not prove JPA mappings, SQL, transactions, constraints, or real database locking.

A good fake needs to stay simple, have clear limits, and not turn into a second production implementation. If a fake increasingly has to simulate transactions, concurrency, query languages, and every database rule, it is time to use a real test database.

### 2.5. Dummy: merely filling a slot

A dummy is an object that is never used in the test scenario. A null constant or an empty implementation can be used if the signature permits, though you should avoid dummies producing confusing errors if the SUT accidentally calls them.

If a collaborator is unrelated to the behavior, constructor injection helps create a simple test fixture. When a dependency is required, an explicit dummy named something like unusedAuditPort clarifies intent better than a mock created and never used.

## 3. How to choose components to replace

Walk through the following questions in order. Each question narrows the scope and helps select the right type of test double.

### 3.1. Is the collaborator's behavior part of what needs to be proven?

If yes, keep the real collaborator at an appropriate level. For example:

- Testing repository queries: use a real repository and a test database.
- Testing JSON binding, validation, or exception mapping: keep real MVC infrastructure.
- Testing transaction rollback: run through a real transaction manager and persistence.
- Testing domain algorithms: use real domain objects.

If no, you can replace the collaborator so the test focuses on the SUT's behavior. For example, when testing how a service reacts to payment declined, there is no need to call a real payment gateway.

### 3.2. Is the collaborator outside the application's boundary of control?

Components like third-party HTTP services, email providers, shared brokers, the system clock, or the filesystem usually need to be controlled in tests. They can be slow, flaky, costly, or difficult to force into desired error states.

For these components, replace them at the adapter or port owned by the application. Keep the request/response translation logic of the real adapter in a separate test, using an HTTP stub server or container to control the partner system.

### 3.3. Do you need to control data or verify an action?

If you only need the SUT to receive a specific answer, use a stub.

If you need to confirm that an important command was sent, use a mock or recording fake.

If you need to manipulate data through a simple API, a fake may be suitable.

If you need to prove interactions across multiple adapters and infrastructure, keep the relevant components real in an integration test.

### 3.4. Does replacing it lose critical evidence?

This is the highest-priority question. Mocking a repository in a test meant to verify a SQL query removes the evidence. Mocking a validator in a test meant to verify Bean Validation leaves the test no longer checking the real validator. Mocking the Security filter chain in a test meant to verify access control bypasses the exact protective layer under test.

Conversely, if a service only needs to know whether the payment gateway returns approved or declined, replacing the real gateway with a stub helps control business branches without losing evidence of the service.

### 3.5. What are the cost and reliability of the real option?

A real dependency can be suitable if it is lightweight, runs locally, and is part of the goal. A Testcontainers database may be worthwhile in integration tests. A production payment system is not suitable to call in regular automated tests.

Consider:

- Startup time and execution time.
- Ability to run offline and in parallel.
- Repeatability of data and results.
- Ability to simulate errors and timeouts.
- Fidelity to the production environment.
- Maintenance cost of fakes or mocks.

Do not optimize for speed by replacing a component that the test needs to verify. Nor is it necessary to spin up the entire production infrastructure for every unit test.

## 4. Decision matrix by collaborator type

The following matrix is a starting point for selection, not an absolute rule:

| Collaborator | SUT unit test | Adapter or integration test |
| --- | --- | --- |
| Value object, domain entity | Keep real | Keep real |
| Pure domain service | Keep real if it has no side effects | Keep real |
| Repository | Fake or stub if only data is needed; avoid mocking query details | Real repository and database |
| HTTP client to external service | Stub/mock port to control outcome | Real adapter + HTTP stub server |
| Message publisher | Recording fake or mock to check events | Real broker/container if protocol and configuration verification is needed |
| Clock | Fixed Clock | Fixed Clock or test time source |
| File storage | Fake filesystem or simulated adapter | Real filesystem in a temp directory if semantics need checking |
| Email/SMS provider | Mock/recording fake | Real adapter with mock server or sandbox |
| Security filter chain | Irrelevant in pure service unit tests | Keep real filter chain when testing authorization at the web layer |
| Random/id generator | Fixed generator can replace it | Adapter test if integration verification is needed |

### 4.1. When should you keep the repository real?

Keep the repository and database real when the goal involves:

- Table names, columns, data types, and entity relationships.
- JPQL, Criteria, native SQL, or query derivation.
- Lazy/eager loading and cascades.
- Unique constraints, foreign keys, and optimistic locking.
- Transactions, rollback, and isolation.
- Pagination, sorting, or queries dependent on a database dialect.

A mock repository can return the right entity to a service, but it does not prove those queries run. For these goals, use @DataJpaTest or @SpringBootTest with a test database. If production uses PostgreSQL, MySQL, or a specific database, Testcontainers helps test closer to that engine than an embedded database.

### 4.2. When should you replace the repository?

In unit tests of an application service, if the goal is business decisions and the repository is merely a storage port, an in-memory fake is usually enough. A fake lets the test verify final state via read APIs.

Mocking a repository can also fit when the service needs to react to a specific persistence failure or when verifying a meaningful save command. However, avoid over-verifying detailed find/save sequences just to assert that the implementation called internal methods.

### 4.3. When should you keep the HTTP adapter real?

If the goal is testing how a service handles partner responses, replacing the partner port with a stub keeps the focus on business logic. If the goal is testing the HTTP adapter, keep the real HTTP client, serialization, headers, authentication mapping, and error mapping, and use an HTTP stub server to control responses.

For example, a test of PaymentHttpAdapter can start WireMock or MockWebServer, configure a local URL, and verify:

- The HTTP method and path sent.
- Authentication or idempotency headers are set properly.
- The request body contains the right amount and currency.
- Success responses are converted into PaymentResult.
- HTTP 4xx/5xx, timeouts, or malformed responses are mapped according to the contract.

In service tests, there is no need to repeat all these HTTP checks. Let adapter tests take responsibility for protocol details and service tests take responsibility for application rules.

## 5. Running example: testing an order service

Suppose OrderApplicationService receives an order request, checks the product, requests payment, saves the order, and publishes an event. Interfaces are defined at the application boundary:

~~~java
interface ProductCatalog {
    Optional<Product> findById(long productId);
}

interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}

interface OrderRepository {
    Order save(Order order);
    Optional<Order> findById(String orderId);
}

interface OrderEventPublisher {
    void publish(OrderPlaced event);
}
~~~

In the service's unit tests, we can choose:

- ProductCatalog: fake to supply deterministic products and prices.
- PaymentGateway: mock to stub the payment result and verify the critical charge command.
- OrderRepository: fake to store orders in memory and inspect state after the action.
- OrderEventPublisher: recording fake to capture published events.
- Clock: Clock.fixed so order creation time is always deterministic.

Each choice has a reason. The fake repository allows checking order state, the recording publisher allows checking events, and the mock payment gateway fits because the payment command is an external side effect.

### 5.1. Preparing fakes and recording fakes

~~~java
class InMemoryProductCatalog implements ProductCatalog {
    private final Map<Long, Product> products = new HashMap<>();

    void add(Product product) {
        products.put(product.id(), product);
    }

    @Override
    public Optional<Product> findById(long productId) {
        return Optional.ofNullable(products.get(productId));
    }
}

class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.id(), order);
        return order;
    }

    @Override
    public Optional<Order> findById(String orderId) {
        return Optional.ofNullable(orders.get(orderId));
    }
}

class RecordingOrderEventPublisher implements OrderEventPublisher {
    private final List<OrderPlaced> published = new ArrayList<>();

    @Override
    public void publish(OrderPlaced event) {
        published.add(event);
    }

    List<OrderPlaced> publishedEvents() {
        return List.copyOf(published);
    }
}
~~~

These fakes contain only the minimal behavior needed for tests. They do not try to simulate JPA or a message broker. When a test needs to prove those properties, use the real adapter in a separate test.

### 5.2. Unit test for the approved payment branch

The following example shows how to combine fakes, mocks, and a fixed Clock. Constructor names, factories, and domain types are illustrative; what matters are the boundaries and evidence of the test.

~~~java
@ExtendWith(MockitoExtension.class)
class OrderApplicationServiceTest {

    @Mock
    PaymentGateway paymentGateway;

    InMemoryProductCatalog productCatalog;
    InMemoryOrderRepository orderRepository;
    RecordingOrderEventPublisher eventPublisher;
    OrderApplicationService service;

    @BeforeEach
    void setUp() {
        productCatalog = new InMemoryProductCatalog();
        orderRepository = new InMemoryOrderRepository();
        eventPublisher = new RecordingOrderEventPublisher();

        Clock clock = Clock.fixed(
            Instant.parse("2026-01-15T10:00:00Z"),
            ZoneOffset.UTC
        );

        productCatalog.add(ProductFixtures.product(7L, "BOOK", "120.00"));

        service = new OrderApplicationService(
            productCatalog,
            paymentGateway,
            orderRepository,
            eventPublisher,
            clock
        );
    }

    @Test
    void saves_order_and_publishes_event_when_payment_is_approved() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
            .thenReturn(PaymentResult.approved("PAY-100"));

        PlaceOrderResult result = service.placeOrder(
            new PlaceOrderCommand("CUSTOMER-1", 7L, 2)
        );

        assertThat(result.isSuccessful()).isTrue();
        Order saved = orderRepository.findById(result.orderId())
            .orElseThrow();
        assertThat(saved.paymentReference()).isEqualTo("PAY-100");
        assertThat(saved.createdAt())
            .isEqualTo(Instant.parse("2026-01-15T10:00:00Z"));
        assertThat(eventPublisher.publishedEvents())
            .extracting(OrderPlaced::orderId)
            .containsExactly(saved.id());

        ArgumentCaptor<PaymentRequest> requestCaptor =
            ArgumentCaptor.forClass(PaymentRequest.class);
        verify(paymentGateway).charge(requestCaptor.capture());
        assertThat(requestCaptor.getValue().amount())
            .isEqualByComparingTo("240.00");
    }
}
~~~

This test confirms that the service creates the order properly given the payment response, uses deterministic time, and publishes the corresponding event. PaymentGateway is stubbed to control the outcome and verified to confirm the amount sent. The repository and event publisher are fakes whose final state can be observed.

If the contract does not require exactly one charge call, verifying the call count can be omitted. If idempotency or preventing duplicate charges is a requirement, the call count and idempotency key become critical evidence and should be checked explicitly.

### 5.3. Unit test for declined payment

A failure scenario must confirm that the system does not produce downstream effects that violate the rules:

~~~java
@Test
void does_not_save_order_or_publish_event_when_payment_is_declined() {
    when(paymentGateway.charge(any(PaymentRequest.class)))
        .thenReturn(PaymentResult.declined("INSUFFICIENT_FUNDS"));

    PlaceOrderResult result = service.placeOrder(
        new PlaceOrderCommand("CUSTOMER-1", 7L, 2)
    );

    assertThat(result.isSuccessful()).isFalse();
    assertThat(orderRepository.count()).isZero();
    assertThat(eventPublisher.publishedEvents()).isEmpty();
}
~~~

The example above assumes the business contract specifies not saving the order and not publishing OrderPlaced when payment is declined. If the actual system has a PENDING_PAYMENT status or must record a failed payment attempt, the assertions must reflect that contract. A test must not impose an unconfirmed policy.

### 5.4. Why not mock every collaborator?

If ProductCatalog, OrderRepository, and OrderEventPublisher were replaced with mocks, the test would have to stub many calls and verify many interactions:

- findById returns the product.
- save was called with which order.
- publish was called with which event.
- how PaymentGateway charge was called.

Such a test can be useful in certain cases, but it is usually harder to read and easily becomes tightly coupled to internal call ordering. A fake repository and recording publisher allow checking resulting state directly. Only PaymentGateway is mocked because it is the external boundary the test needs to control and verify.

## 6. Choosing boundaries by Spring layer

A Spring application can be tested at multiple layers. The same dependency can be real in one test and replaced in another.

### 6.1. Unit tests without starting a Spring context

For pure domain logic or application services, instantiate the SUT directly via its constructor. This approach:

- Makes actual required dependencies explicit.
- Avoids ApplicationContext startup time.
- Lets the test control each collaborator.
- Is unaffected by bean configuration or component scanning.

MockitoExtension can create mocks and manage strict stubbing. However, annotations are not mandatory. Creating mocks with Mockito.mock or using plain Java fakes are both valid.

Prefer constructor injection in production code. It helps tests supply all dependencies and catches early when a class has too many responsibilities or hard-to-replace dependencies.

### 6.2. Web slice with @WebMvcTest

In controller tests, the goal is usually HTTP mapping, request binding, validation, response serialization, and web-layer security behavior.

Keep real Spring MVC infrastructure. Replace the application service at the controller boundary with a mock or stub if the test only focuses on the web contract:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderApplicationService orderService;

    @Test
    void returns_created_response_when_service_accepts_order()
            throws Exception {
        when(orderService.placeOrder(any(PlaceOrderCommand.class)))
            .thenReturn(PlaceOrderResult.success("ORDER-10"));

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId": 7, "quantity": 2}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.orderId").value("ORDER-10"));
    }
}
~~~

Here, the mock service is an intentional boundary: the controller test does not prove order placement business logic. It proves that an HTTP request is translated into an application call and the result is translated into the right response.

If you need to verify that the real service handles the request, write a separate service test or integration test. Do not infer that a controller test proved the entire flow just because it returns status 201.

### 6.3. Data slice with @DataJpaTest

In repository tests, keep entity mapping, the repository implementation, and the test database real. Do not replace the repository with a mock because it is the object under test.

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orderRepository;

    @Test
    void finds_orders_by_customer_id() {
        orderRepository.save(OrderFixtures.forCustomer("CUSTOMER-1"));
        orderRepository.save(OrderFixtures.forCustomer("CUSTOMER-2"));

        List<Order> result =
            orderRepository.findAllByCustomerId("CUSTOMER-1");

        assertThat(result)
            .extracting(Order::customerId)
            .containsExactly("CUSTOMER-1");
    }
}
~~~

This example illustrates the persistence boundary. If the test replaced OrderRepository with a mock, the findAllByCustomerId query would never execute and the test would no longer prove what needs checking.

### 6.4. Application integration with @SpringBootTest

When you need to verify multiple real beans collaborating, use @SpringBootTest. Replace dependencies outside the scope under test, such as a payment gateway or email-sending service.

In Spring Boot 3.3, @MockBean is commonly used to replace a bean in the ApplicationContext. In newer Spring Framework versions that support bean override, @MockitoBean is the corresponding choice. Use the annotation suited to your project version.

An order integration test might keep the controller, service, repository, and a Testcontainers database real while replacing PaymentGateway with a mock or a mock server. The choice depends on the goal:

- If you need to test how the service reacts to approved/declined: mocking the payment port is enough.
- If you need to test that PaymentHttpAdapter builds the right request: use the real adapter and an HTTP stub server.
- If you need to test the full flow over the payment protocol: use a sandbox or controlled contract environment with dedicated data policies.

Do not replace every bean just to get the ApplicationContext to start. If a critical bean fails to be created due to misconfiguration, mocking that bean can hide wiring errors.

### 6.5. Security and authentication

If a test needs to prove that an endpoint permits or denies users by role, keep the real Security filter chain. You can use a test principal such as @WithMockUser to control identity without calling an external identity provider.

If the goal is testing OAuth2 login, token decoding, or claim mapping, you need a test at the right adapter/security boundary with a simulated token or issuer. Do not mock the entire security layer in a test meant to prove authorization.

### 6.6. Reactive web with WebFlux

With WebFlux, keep real WebFlux infrastructure in @WebFluxTest and use WebTestClient. Replace the application service if the goal is the web contract. When testing a reactive service, you can provide simulated publishers or mock ports, then assert on signals, errors, and completion as required.

If the goal is backpressure, cancellation, or interacting with a reactive broker, simple test doubles may not be enough. Choose tools that can produce and observe the required signals, or run integration tests with the real adapter.

## 7. Replacing on the right side of the adapter

A useful principle is to replace dependencies at a boundary controlled by the application, typically an interface/port called by the application layer. This keeps business logic from depending directly on HTTP libraries, databases, or vendor SDKs.

For example:

~~~text
OrderApplicationService
    |
    +-- ProductCatalog
    |       |
    |       +-- JpaProductCatalogAdapter
    |
    +-- PaymentGateway
    |       |
    |       +-- PaymentHttpAdapter
    |
    +-- OrderRepository
    |       |
    |       +-- JpaOrderRepositoryAdapter
    |
    +-- OrderEventPublisher
            |
            +-- KafkaOrderEventPublisher
~~~

Unit tests of OrderApplicationService replace the ports. Tests of PaymentHttpAdapter keep the real adapter and HTTP client while controlling the server side. Tests of JpaOrderRepositoryAdapter keep real JPA and database. Tests of KafkaOrderEventPublisher can use a broker container or a suitable adapter test.

Thus, each test focuses on one boundary and provides distinct evidence. A fake at the application layer does not replace adapter tests; adapter tests do not need to repeat all business rules.

### 7.1. Do not mock libraries instead of application boundaries

Directly mocking a framework class or vendor SDK can couple tests to library internals. For example, mocking EntityManager in a service test often creates verbose setup that does not reflect business contracts.

Wrap external capabilities with an interface meaningful to the application, such as PaymentGateway or DocumentStorage. The adapter implements that interface using the concrete library. Then:

- Unit tests replace the port.
- Adapter tests verify mapping to the library/protocol.
- Integration tests verify configuration and needed real interactions.

You do not need an interface for every class. Introduce an abstraction only when it represents a boundary, a substitution policy, or a meaningful contract.

## 8. Signs of replacing the wrong things

### 8.1. Tests pass but the real system does not run

If every repository, HTTP client, event publisher, and security component is a mock, tests can pass even if queries are broken, URLs are wrong, beans are misconfigured, or transactions do not work.

Review the test goal. If you need to prove an adapter or Spring configuration, keep that part real and replace what lies outside scope.

### 8.2. Mock setup is longer than the logic under test

A test requiring dozens of when and verify calls is often testing too deeply into an implementation graph. You can convert some collaborators to fakes, use meaningful fixtures, or split tests along boundaries.

Not every long setup is wrong: a complex protocol may require many steps. But if a test only proves a simple rule while configuring many internal details, re-evaluate the design.

### 8.3. Verifying call order that is not part of the contract

A service might swap the order of calling two internal methods and still produce the same right outcome. VerifyInOrder or verifyNoMoreInteractions can make tests brittle if that order is not a business commitment.

Only check ordering when it is meaningful, such as verifying authorization before executing a sensitive action, reserving inventory before confirming an order, or publishing an event only after commit according to the chosen contract.

### 8.4. Spies hiding a hard-to-test design

If you need to spy on a service to intercept a private helper or skip half a method, the class may be merging multiple responsibilities. Consider extracting meaningful collaborators or testing via the public API.

Do not use spies to invoke private methods just to achieve coverage. The goal is testing public behavior, not exposing every internal detail to tests.

### 8.5. Fakes differ from production in critical ways

An in-memory repository may not match database case sensitivity, lack constraints, lack transactions, and lack concurrency. If business logic relies on those properties, the fake has insufficient fidelity.

Document what a fake guarantees and what it does not guarantee. Add integration tests with suitable infrastructure for the properties the fake does not simulate.

### 8.6. Mocking a collaborator without knowing why

A mock should not appear merely because a class has a dependency. Before each mock, be able to answer:

- What data does it help control?
- What effect does it help observe?
- Why not use the real collaborator or a fake?
- Does replacing it lose part of the behavior that needs verification?

If there is no clear answer, a mock may not be needed.

## 9. Managing state and side effects in tests

Choosing the right test double is still not enough if state is shared between tests or side effects are uncontrolled.

### 9.1. Create fresh test doubles per test

Stateful fakes such as in-memory repositories or recording publishers should be instantiated fresh in each test's setup. Do not share a mutable fake across tests running in parallel unless intentional and properly synchronized.

With Mockito, each test should have a clear mock lifecycle. MockitoExtension helps initialize mocks and check stubbing. Avoid holding static mocks or test data that can mutate across runs.

### 9.2. Fix time

If a service reads the current time, inject java.time.Clock instead of calling Instant.now() directly in multiple places. In tests, use Clock.fixed:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

This lets tests verify expiration, record creation timestamps, or date/time rules without depending on the machine clock.

### 9.3. Control randomness and IDs

If a random ID is part of the output, you can inject an ID generator to produce deterministic values. However, do not replace an ID generation algorithm in every test if that algorithm is not the target. Format or uniqueness can be verified in a dedicated test.

### 9.4. Side effects need boundaries

Sending email, charging payments, or publishing events are effects that can leave the process. In unit tests, a recording fake can retain sent payloads for inspection. In adapter tests, a mock server or broker confirms the protocol. In integration tests, a container or sandbox can prove wiring and serialization.

If requirements specify publishing events only after a transaction commits, a recording fake called directly inside the same transaction is not enough to prove post-commit semantics. You must test the actual transaction event mechanism or relevant adapter/broker.

## 10. Designing maintainable test doubles

Test doubles are code too and require quality.

### 10.1. Prefer role-revealing names

Names like InMemoryOrderRepository, FixedClock, RecordingEventPublisher, or DecliningPaymentGateway tell the reader what the object does. Generic names like MockHelper or TestUtil often obscure intent.

### 10.2. Keep fakes small and faithful to the contract

A fake should implement the portion of the contract needed for the test group. If an interface is too broad and forces the fake to implement many unrelated methods, the interface may combine too many responsibilities.

Do not add business logic into a fake to make tests pass. A fake repository can store and find entities; it should not compute shipping fees or decide ordering eligibility on behalf of the SUT.

### 10.3. Use fixtures for domain data

A Fixture or Object Mother can create valid objects with clear defaults:

~~~java
Product product = ProductFixtures.availableProduct()
    .withId(7L)
    .withPrice(new BigDecimal("120.00"));
~~~

Factories must make tests easier to read. If a fixture hides properties that determine the outcome, pass them explicitly in the test or use a builder with recognizable defaults.

### 10.4. Avoid unused stubbing

Stubbing a method that the SUT never calls may indicate redundant setup or a test path different from what was expected. MockitoExtension with strict stubbing usually detects unused stubs. When lenient is needed, apply it only to a specific stub and with a reason.

Do not apply lenient to an entire test suite just to silence warnings. Warnings may indicate overly broad fixtures or tests no longer exercising the intended branch.

## 11. Some tool choices in the Spring ecosystem

The following tools help realize the chosen boundaries:

| Need | Commonly used tool | Role |
| --- | --- | --- |
| Mock/stub/spy Java objects | Mockito | Controls responses and observes interactions |
| Test MVC controllers | @WebMvcTest, MockMvc | Keeps real MVC infrastructure, replaces services when appropriate |
| Test WebFlux | @WebFluxTest, WebTestClient | Keeps real reactive web stack |
| Test JPA | @DataJpaTest | Keeps real mappings and repositories |
| Test multiple beans | @SpringBootTest | Builds ApplicationContext and chooses real/fake dependencies by goal |
| Replace beans in context | @MockBean in Spring Boot 3.3; @MockitoBean in newer supporting Spring versions | Replaces a bean with a Mockito mock |
| Configure fake beans | @TestConfiguration, @Import | Registers test-specific adapters/fakes |
| Real database in container | Testcontainers | Tests real database engine and configuration |
| Mock HTTP service | WireMock, MockWebServer, or equivalent | Controls responses and verifies HTTP requests |
| Test MVC without server | MockMvc | Sends requests through Spring MVC in tests |
| Test running HTTP server | @SpringBootTest with RANDOM_PORT and appropriate client | Tests across a real HTTP boundary |

You do not need to use every tool in one project. Choose tools based on the identified boundaries and actual Spring version.

### 11.1. Using @TestConfiguration for fakes

When an integration test needs to keep most of the real ApplicationContext while replacing one adapter, you can declare a test configuration:

~~~java
@TestConfiguration
class FakePaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }
}
~~~

Then import this configuration into the relevant test. This approach can be more readable than replacing a bean with a mock if the fake has stable behavior and needs reuse. Make sure the test configuration is not accidentally component-scanned into the production application.

### 11.2. Using @MockBean or @MockitoBean intentionally

When you need to test another bean in the Spring context and want to replace a collaborator with a Mockito mock, bean override is a convenient option. But every time you replace a bean, identify clearly what the test is bypassing.

For example, replacing PaymentGateway in an OrderApplicationService test helps control payment responses. Replacing OrderRepository in an OrderRepository test removes the very implementation under test. Do not use the annotation just to make the context start successfully.

## 12. Decision workflow before writing a test

You can apply the following workflow for each test case:

**Step 1 – Write the behavior to prove.** State initial conditions, action, and expected outcome in business language.

**Step 2 – Identify the SUT.** Specify which class, adapter, or application flow is under test.

**Step 3 – List collaborators.** Note which dependencies participate and which parts of the contract matter to the test.

**Step 4 – Mark boundaries to keep real.** Components whose behavior needs proving must run for real at an appropriate level.

**Step 5 – Choose replacement types per dependency.** Use stubs to control outcomes, mocks to verify meaningful interactions, fakes to provide simple behavior, spies when genuinely needing to observe real objects, and dummies for unused parameters.

**Step 6 – Check fidelity.** Check whether the test double omits critical transactions, queries, serialization, security, concurrency, or semantics.

**Step 7 – Write outcome-based assertions.** Assert on state and output first; assert on interactions when they are part of the contract.

**Step 8 – Choose the right Spring layer.** Unit test, web slice, data slice, or application integration.

**Step 9 – Add adapter tests when needed.** Ensure adapters replaced in unit tests still have dedicated tests with suitable infrastructure.

**Step 10 – Run standalone and in the suite.** Confirm tests do not depend on execution order, shared data, or leaked state.

## 13. Self-review table for replacement decisions

Before finalizing a test, ask yourself:

| Question | If the answer is Yes |
| --- | --- |
| Is this component the exact thing the test needs to verify? | Keep the real implementation at the appropriate test layer |
| Is this an external system that is hard to control? | Replace at the port or use a mock server/container |
| Only need a specific result to traverse a branch? | Use a stub |
| Need to prove an important command or side effect? | Use a mock or recording fake |
| Need a simple working collaborator with state? | Consider a fake |
| Need to verify adapter protocol, mapping, or configuration? | Keep the adapter real, simulate the partner side |
| Fake cannot simulate the property under consideration? | Use real infrastructure in an integration test |
| Mock setup is describing too many internal details? | Revisit boundaries, fakes, or collaborator structure |

A test can combine multiple approaches. For example, an application service test can use real domain objects, a fake repository, a stub payment gateway, a recording event publisher, and a fixed clock. That is a good choice if each test double serves a clear purpose and the test still fully proves the SUT's behavior.

## 14. Conclusion

Choosing components to replace starts with identifying what the test needs to prove. Keep components real when their behavior falls within the scope under test; replace external dependencies or collaborators that the test only needs to control. Stubs provide answers, mocks verify interactions, spies observe real objects, and fakes provide simple working implementations.

In Spring, these boundaries are expressed through unit tests, web slices, data slices, and integration tests. @WebMvcTest should keep real MVC infrastructure, @DataJpaTest should keep real persistence, and @SpringBootTest allows combining real beans with test doubles at chosen boundaries. A trustworthy test suite is not measured by having few or many mocks; it is judged by whether each test produces the right evidence for the behavior it claims to verify.
