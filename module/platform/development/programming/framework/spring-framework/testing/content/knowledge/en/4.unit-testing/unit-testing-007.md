# Verifying Side Effects Through a Port

A unit test often focuses on the return value or the state of an object after invoking a method. However, many important business operations also produce side effects: persisting data, deducting inventory, sending payment requests, publishing messages, sending emails, or writing files. Because these outcomes occur outside the object under test, checking only the return value is not enough.

One way to structure code so side effects are easy to test is to route them through **ports**. In Ports and Adapters (commonly called Hexagonal Architecture), the application defines interfaces describing the capabilities the business logic needs; external adapters implement those interfaces using databases, HTTP clients, message brokers, or other services. Unit tests replace real adapters with mocks or fakes to observe side effects at the application boundary.

In a Spring application, Spring injects real adapters into services at runtime. Yet in unit tests, we typically instantiate the use case directly and pass in test doubles for the ports. This keeps tests fast, isolated, and focused on business decisions. Separate integration tests verify that adapters and Spring configuration work properly with real infrastructure.

## 1. What Is a Side Effect?

A side effect is an observable change or interaction beyond the return value of a call. Examples include:

- Writing an order to a database.
- Sending a stock reservation command to a warehouse system.
- Calling a payment gateway API.
- Publishing an event or sending a message to a broker.
- Sending a confirmation email or push notification.
- Writing a file, calling a storage service, or updating a shared cache.
- Recording an audit entry that must be persisted.

Distinguish side effects from pure computation results. A total-calculation function can return a number without altering external systems. A place-order function may return an order ID while also saving the order, reserving stock, and requesting payment. A test checking only the order ID could miss that the system failed to reserve stock.

Not every dependency call is a side effect. A read query is also an interaction across a boundary, yet the test goal may be verifying the returned result rather than asserting call counts. Determine what belongs to the core business contract before choosing assertions.

## 2. Ports in Application Architecture

A port is an interface describing a capability the application requires or exposes. When testing side effects, we usually focus on **outbound ports**: interfaces a use case calls to interact with the outside world.

For example, an order placement use case may depend on these ports:

```java
public interface OrderRepository {
    void save(Order order);
}

public interface PaymentPort {
    PaymentResult charge(PaymentRequest request);
}

public interface InventoryPort {
    ReservationResult reserve(ReservationRequest request);
}

public interface OrderNotificationPort {
    void sendConfirmation(OrderConfirmation confirmation);
}
```

These interfaces belong to the application or domain layer, where needs are defined. Adapters implement them:

| Port | Possible Adapter |
| --- | --- |
| `OrderRepository` | Spring Data JPA repository and entity mapping adapter |
| `PaymentPort` | HTTP client calling a payment gateway |
| `InventoryPort` | REST client or message producer calling an inventory service |
| `OrderNotificationPort` | SMTP client, email service, or notification gateway |

The use case only knows the port's contract. It does not need to know whether the adapter uses `RestClient`, `WebClient`, JDBC, JPA, Kafka, or a specific SDK. Thus, unit tests can swap out real adapters for mocks or fakes without spinning up a database or network connection.

### Inbound ports and outbound ports

An inbound port describes how an external actor asks the application to execute a use case, such as `PlaceOrderUseCase`. A Spring MVC controller or message listener acts as an adapter calling the inbound port. Outbound ports describe capabilities the application requires from external systems, such as persisting orders or calculating shipping fees.

```text
HTTP request
    |
    v
Controller adapter
    |
    v
PlaceOrderUseCase (inbound port)
    |
    v
PlaceOrderService
    |          |             |
    v          v             v
OrderStore  PaymentPort  InventoryPort (outbound ports)
    |          |             |
    v          v             v
Database   Payment API   Warehouse API
```

The diagram shows the direction of dependencies: application logic calls interfaces it owns; external adapters implement those interfaces. This makes test boundaries clear and keeps unit tests decoupled from infrastructure technologies.

## 3. Defining the Side-Effect Contract Before Writing Tests

Do not start by asking "which mock should I verify?". Start from business requirements: under what conditions must the system produce which external changes, with what data, how many times, and at what point?

For example, an order placement workflow might carry these expectations:

| Condition | Side Effect to Verify |
| --- | --- |
| Valid order and approved payment | Send payment request with right amount; save order as paid; request stock reservation |
| Payment declined | Do not save order as paid; do not send confirmation email; handle stock reservation per chosen rule |
| Empty cart | Do not call payment gateway; do not save order |
| Warehouse declines stock reservation | Do not proceed to charge if the flow requires reserving first; return appropriate business error |
| Duplicate request with same idempotency key | Do not create two payment transactions or two orders |

Expectations must reflect the real business contract. The ordering between reserving stock and charging payment varies across systems. If payment happens before reservation, the design needs a refund or compensation workflow when reservation fails. Tests should verify the chosen policy rather than imposing arbitrary ordering.

A side effect must be described specifically enough. For example, "send email" may be insufficient if the contract requires sending it to the customer's address, including the exact order ID, and sending it only after the order is created successfully.

## 4. Example Use Case Depending on Ports

Suppose the application has an order placement use case. Ports are passed into the constructor to make dependencies explicit:

```java
public interface OrderRepository {
    void save(Order order);
}

public interface PaymentPort {
    PaymentResult charge(PaymentRequest request);
}

public interface OrderNotificationPort {
    void sendConfirmation(OrderConfirmation confirmation);
}
```

Application service using the ports:

```java
public class PlaceOrderService {

    private final OrderRepository orders;
    private final PaymentPort payments;
    private final OrderNotificationPort notifications;

    public PlaceOrderService(
            OrderRepository orders,
            PaymentPort payments,
            OrderNotificationPort notifications) {
        this.orders = orders;
        this.payments = payments;
        this.notifications = notifications;
    }

    public OrderId place(PlaceOrderCommand command) {
        Order order = Order.create(command.customerId(), command.items());

        PaymentResult payment = payments.charge(
            new PaymentRequest(order.id(), order.total(), command.paymentToken())
        );

        if (!payment.approved()) {
            throw new PaymentDeclinedException(order.id());
        }

        order.markPaid(payment.reference());
        orders.save(order);
        notifications.sendConfirmation(
            new OrderConfirmation(order.id(), command.customerEmail())
        );

        return order.id();
    }
}
```

This is an illustrative example; types like `Order`, `PaymentRequest`, and `PaymentResult` represent application models. The key point is that the service calls only interfaces. It never directly constructs HTTP clients, repository implementations, or email senders.

In Spring, real adapters can be registered as beans:

```java
@Component
class HttpPaymentAdapter implements PaymentPort {
    // Uses an HTTP client to call the payment gateway
}

@Repository
class JpaOrderRepositoryAdapter implements OrderRepository {
    // Maps and persists the entity using Spring Data JPA
}
```

Constructor injection lets Spring supply real adapters at runtime and lets unit tests pass mocks or fakes when testing application logic.

## 5. Verifying Port Calls with Mockito

Mockito lets you assert that a port was invoked with the expected arguments. Use `verify()` to check interactions meaningful to the contract.

```java
@ExtendWith(MockitoExtension.class)
class PlaceOrderServiceTest {

    @Mock
    OrderRepository orders;

    @Mock
    PaymentPort payments;

    @Mock
    OrderNotificationPort notifications;

    @InjectMocks
    PlaceOrderService service;

    @Test
    void savesOrderAndSendsConfirmationWhenPaymentIsApproved() {
        when(payments.charge(any(PaymentRequest.class)))
            .thenReturn(PaymentResult.approved("payment-123"));

        PlaceOrderCommand command = validCommand();

        OrderId orderId = service.place(command);

        verify(payments).charge(argThat(request ->
            request.amount().equals(command.expectedTotal())
                && request.paymentToken().equals(command.paymentToken())
        ));
        verify(orders).save(argThat(order ->
            order.id().equals(orderId) && order.isPaid()
        ));
        verify(notifications).sendConfirmation(argThat(message ->
            message.orderId().equals(orderId)
                && message.email().equals(command.customerEmail())
        ));
    }
}
```

In this example, the test asserts three side effects: charging the right amount and token, saving a paid order, and sending confirmation to the right address. Assertions focus on business-meaningful data rather than merely checking that mocks were called.

`@InjectMocks` is convenient when Mockito can instantiate the object with the matching mocks. If construction or setup is complex, instantiating the service directly in `@BeforeEach` is often clearer because it shows exactly which dependencies are passed in.

## 6. Verifying That Side Effects Do Not Occur

Many critical bugs involve an action that should not have happened. Mockito provides `never()` to verify a port was not called:

```java
@Test
void doesNotSaveOrderOrSendConfirmationWhenPaymentIsDeclined() {
    when(payments.charge(any(PaymentRequest.class)))
        .thenReturn(PaymentResult.declined("insufficient-funds"));

    assertThrows(
        PaymentDeclinedException.class,
        () -> service.place(validCommand())
    );

    verify(payments).charge(any(PaymentRequest.class));
    verify(orders, never()).save(any(Order.class));
    verify(notifications, never())
        .sendConfirmation(any(OrderConfirmation.class));
}
```

This test confirms that when payment is declined, the service calls the payment gateway yet does not save the order as successful and does not send a confirmation email. This is crucial evidence because checking only the exception does not prove downstream side effects were prevented.

Other situations where you should assert a port is not called:

- Do not send emails when input data is invalid.
- Do not call the payment gateway when the cart is empty.
- Do not publish a success event when saving data fails.
- Do not call an external service when access is denied.
- Do not send a second message when an idempotency key has already been processed.

Use `never()` only for interactions forbidden by the contract. There is no need to assert every other dependency was untouched if that is irrelevant to the rule under test.

## 7. Checking Data Sent Through a Port

Side effects often matter both in whether a call happened and in what payload was sent. When the argument is a complex object, `ArgumentCaptor` captures the actual value so you can inspect multiple fields.

```java
@Captor
ArgumentCaptor<OrderConfirmation> confirmationCaptor;

@Test
void sendsConfirmationContainingTheCreatedOrderId() {
    when(payments.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    OrderId orderId = service.place(validCommand());

    verify(notifications).sendConfirmation(confirmationCaptor.capture());

    OrderConfirmation sent = confirmationCaptor.getValue();
    assertEquals(orderId, sent.orderId());
    assertEquals("customer@example.test", sent.email());
}
```

`ArgumentCaptor` is especially helpful when checking payloads sent to a message broker, commands dispatched to external systems, or events carrying a snapshot of data at emission time. For simpler conditions, `argThat()` or `eq()` may be more concise.

Avoid comparing entire objects when many fields are unrelated to the behavior. Assert the fields covered by the port's contract. If a new field is added to a model without affecting business behavior, tests should not fail just because that field changed.

## 8. Verifying Call Counts and Idempotency

How many times a side effect executes can be part of the contract. Mockito supports `times(n)`, `atLeastOnce()`, and `never()`.

```java
verify(payments, times(1)).charge(any(PaymentRequest.class));
verify(orders, times(1)).save(any(Order.class));
verify(notifications, never()).sendConfirmation(any());
```

For example, if a command is retried with the same idempotency key, the system may have to return the previous result without creating a new payment transaction. A test can invoke the use case twice and assert only one call reached the payment gateway, depending on where the idempotency key is stored.

```java
@Test
void doesNotChargeTwiceWhenSameIdempotencyKeyIsSubmittedAgain() {
    when(payments.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    PlaceOrderCommand command = commandWithKey("request-abc");

    service.place(command);
    service.place(command);

    verify(payments, times(1)).charge(any(PaymentRequest.class));
}
```

This snippet illustrates the goal. To guarantee true idempotency across multiple instances or restarts, persisting keys and results usually needs integration testing against shared storage. A mocked unit test does not prove uniqueness in a distributed database.

Do not assume every port must be called exactly once. Retries can be valid behavior for transient errors. When asserting call counts, base expectations on retry policies, idempotency, and the nature of the side effect. A duplicate email or charge can be dangerous; re-reading configuration once may be harmless.

## 9. Verifying Interaction Order When Ordering Is a Business Rule

Some side effects must occur in a specific sequence. Mockito `InOrder` verifies ordering across ports:

```java
@Test
void reservesInventoryBeforeChargingPayment() {
    when(inventory.reserve(any()))
        .thenReturn(ReservationResult.reserved("reservation-7"));
    when(payments.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    service.place(validCommand());

    InOrder order = inOrder(inventory, payments, orders);
    order.verify(inventory).reserve(any(ReservationRequest.class));
    order.verify(payments).charge(any(PaymentRequest.class));
    order.verify(orders).save(any(Order.class));
}
```

Use this check only when order is part of the requirement, such as succeeding in reserving inventory before charging payment. If call ordering does not affect the contract, asserting order makes tests brittle during refactoring without increasing confidence.

When a multi-step flow includes compensation, test failure branches too. For example, if payment is declined after reserving stock, the system must release the reservation:

```java
@Test
void releasesInventoryWhenPaymentIsDeclined() {
    when(inventory.reserve(any()))
        .thenReturn(ReservationResult.reserved("reservation-7"));
    when(payments.charge(any()))
        .thenReturn(PaymentResult.declined("insufficient-funds"));

    assertThrows(PaymentDeclinedException.class,
        () -> service.place(validCommand()));

    verify(inventory).reserve(any(ReservationRequest.class));
    verify(inventory).release("reservation-7");
    verify(orders, never()).save(any(Order.class));
}
```

This illustrates a business flow with compensation. If the application uses a saga or asynchronous workflow, compensation may be executed by another component; in that case, test the port or published event that hands off the compensation request.

## 10. Using Fakes to Check State Instead of Calls

Mocks fit when controlling responses or asserting interactions. Fakes fit when you want a lightweight stateful implementation to check outcomes without real infrastructure.

Example in-memory fake repository:

```java
class InMemoryOrderRepository implements OrderRepository {

    private final Map<OrderId, Order> stored = new HashMap<>();

    @Override
    public void save(Order order) {
        stored.put(order.id(), order.copy());
    }

    Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(stored.get(id));
    }
}
```

Tests can execute the use case and read data back from the fake:

```java
@Test
void storesPaidOrderAfterPaymentIsApproved() {
    InMemoryOrderRepository repository = new InMemoryOrderRepository();
    PaymentPort payment = request -> PaymentResult.approved("payment-123");
    OrderNotificationPort notifications = confirmation -> { };

    PlaceOrderService service = new PlaceOrderService(
        repository, payment, notifications
    );

    OrderId id = service.place(validCommand());

    Order stored = repository.findById(id).orElseThrow();
    assertTrue(stored.isPaid());
}
```

Fakes make inspecting stored state feel natural. However, a fake only simulates part of the real adapter's contract. It does not prove JPA mappings, transactions, constraints, serialization, or database connectivity are correct. Those behaviors require integration tests against the real adapter.

A good fake stays simple, readable, and faithful to the contract the unit test relies on. Avoid turning a fake into a homegrown database with a full query engine, locking, and transactions. Once a fake grows complex, consider Testcontainers or a dedicated adapter test.

## 11. When to Use Mocks, Fakes, or Spies?

| Test Double | When to Use | Points to Watch |
| --- | --- | --- |
| Mock | Need to control return values or assert side effects across a port | Avoid verifying internal calls outside the contract |
| Fake | Need to simulate simple state and check behavior-based outcomes | Keep the fake consistent with the real adapter's contract |
| Stub | Only need to provide fixed responses for a dependency | Do not use stubs as proof that a side effect occurred |
| Spy | Need to observe a real object or keep most of its real behavior | Can couple tests to implementation; use cautiously |

In use case unit tests, mocking outbound ports is usually the most direct way to assert outbound commands. For repositories or read ports, fakes can make tests easier to read when state checks are needed. There is no rule forcing every dependency to use the same kind of double.

## 12. Separating Business Decision Tests from Adapter Tests

A common design mistake is writing unit tests that assert HTTP request details, SQL, or broker configuration when the actual goal is business rules. Divide responsibilities cleanly:

- Use case unit tests: verify when ports are called, with what data, how many times, and when they are not called.
- Adapter tests: verify the adapter translates data and communicates properly with external technology.
- Integration tests: verify Spring wiring, transactions, serialization, and connectivity between adapters and infrastructure.

For example, `PaymentPort` may be implemented using `RestClient`. The `PlaceOrderService` unit test only needs to verify it sends a `PaymentRequest` with the right order ID and amount. A separate test for `HttpPaymentAdapter` checks URL, HTTP method, headers, JSON body, response mapping, and error handling. Do not force service unit tests to know a provider's endpoint names or JSON structure.

Similarly, unit tests can assert `OrderRepository.save(order)` was called. `@DataJpaTest` or another integration test verifies the entity maps and persists properly to the database. The two testing layers supply different, complementary evidence.

## 13. Side Effects and Transactions in Spring

In Spring applications, `@Transactional` is typically applied via proxies. Unit tests instantiating services with `new` do not trigger Spring-managed transactions. Therefore, unit tests can verify decisions to call ports and handle errors, yet cannot prove a transaction actually committed or rolled back.

Example:

```java
@Service
class PlaceOrderService {

    @Transactional
    public OrderId place(PlaceOrderCommand command) {
        // Calls ports and updates order state
    }
}
```

A unit test calling `new PlaceOrderService(...).place(command)` directly does not pass through the Spring proxy. It remains a valid test for method logic, yet not evidence of transaction manager behavior.

To test transactions, run an integration test through a Spring-managed bean and check data from an independent transaction. When publishing messages after commit, you can use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` or a transactional outbox depending on architecture. Unit tests verify the decision to publish an event or write an outbox record; integration tests verify events are dispatched only at the intended commit point.

Do not treat `verify(eventPublisher).publish(...)` as proof that the broker received the message or that the transaction committed. It only proves code called the publisher port. Successful delivery, retries, acknowledgements, and durability belong to adapter and integration tests.

## 14. Side Effects via Spring ApplicationEvent and Message Ports

Spring provides `ApplicationEventPublisher` for publishing events within the same application. When business logic needs to broadcast information to external systems, a dedicated outbound port usually keeps boundaries clearer. For example, `OrderEventPort` can be implemented by an adapter using Kafka or RabbitMQ.

```java
public interface OrderEventPort {
    void publish(OrderPlaced event);
}
```

Unit tests can verify the event is constructed properly:

```java
@Test
void publishesOrderPlacedEventWhenOrderIsAccepted() {
    when(payments.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    service.place(validCommand());

    verify(orderEvents).publish(argThat(event ->
        event.orderId() != null
            && event.customerId().equals("customer-42")
    ));
}
```

This test verifies the use case publishes an event with the required data. It does not check serialization, topics, routing keys, partitions, broker availability, or delivery guarantees. Those belong to adapter and integration tests.

If an event must only be emitted after commit, the port design should express clear semantics. One option is writing an outbox record in the same transaction while another worker forwards records to the broker. Unit tests check that the outbox port receives the event; integration tests confirm writing the outbox record and updating business data share the same transaction. This avoids assuming calling a publisher means the broker durably persisted the message.

## 15. Avoiding Over-Verification of Interactions

Interaction tests are great for side effects, yet asserting every internal call makes tests fragile. A refactor might reorder helpers or combine two calls without altering external behavior, causing tests to fail even though business logic remains right.

What to verify:

- Which ports must or must not be called under business conditions.
- Important data sent across ports.
- Call counts when count is part of the contract, such as idempotency or avoiding duplicate emails.
- Ordering when ordering carries business meaning or safety guarantees.
- Compensating side effects when a multi-step workflow fails.

What usually needs no verification:

- Every getter or internal helper call.
- How many times a private method was invoked.
- Ordering among ports when the contract does not require it.
- Every field of an object when only a few fields matter to the side effect.
- Calling `verifyNoMoreInteractions()` on all mocks just to force an exact match with the implementation.

A helpful rule of thumb is to test boundaries meaningful to the application or external systems. When a call is merely an internal code-structuring detail inside the service, prefer asserting business outcomes.

## 16. Designing Ports to Make Side-Effect Testing Easy

Ports should express business intent rather than exposing infrastructure library APIs. Compare:

```java
// Technology-specific port
public interface KafkaTemplatePort {
    void send(String topic, String key, byte[] payload);
}

// Port describing application intent
public interface OrderEventPort {
    void publishOrderPlaced(OrderPlaced event);
}
```

The second port lets the use case state its need without knowing topics, keys, or serialization details. The Kafka adapter takes responsibility for mapping `OrderPlaced` to a message structure.

A well-designed port typically has these traits:

- A name expressing a business capability or intent.
- Only operations the application actually needs.
- Stable data types belonging to the application or domain layer.
- Clear error semantics: return values, thrown exceptions, or rejection states.
- No leaking of framework or vendor SDK types unless necessary.
- Small enough for an adapter to implement cleanly and a unit test to verify easily.

Do not create an interface for every class. A port adds value when it marks a boundary of change, an external dependency, or a capability that needs substitution in tests. Wrapping a pure, side-effect-free helper in an interface adds architectural noise without benefit.

## 17. Testing Errors and Retries at Ports

Ports are often where infrastructure errors enter the application. Unit tests must verify how the use case reacts to responses a port can return or exceptions an adapter can throw.

For example, with a payment gateway:

| Port Outcome | Application Behavior to Define |
| --- | --- |
| Approved | Mark payment successful and continue flow |
| Declined | Reject business operation; do not create success confirmation |
| Timeout | Unknown whether transaction occurred; requires lookup or idempotency |
| Service unavailable | May retry according to policy and limits |
| Invalid response | Record integration error and handle safely |

Tests can configure mocks to return each outcome and cover all branches. Especially for timeouts, never assume the request definitely did not run. If the payment system processed the request and the response was lost, retrying without an idempotency key could charge twice. Port contracts and tests should reflect this uncertainty.

If retry logic lives inside the HTTP adapter, use case unit tests do not need to count HTTP requests. Test retry policies in dedicated adapter tests. When retries are a business policy driven by the use case, use case tests can assert port call counts and stopping conditions.

## 18. Clocks, IDs, and Dependencies Producing Non-Deterministic Side Effects

Databases and HTTP services are not the only dependencies. Reading system time, generating random IDs, or reading environment variables can also make results hard to reproduce. Route these capabilities through ports or small abstractions.

Example using Java's `Clock`:

```java
public class ExpirationService {

    private final Clock clock;

    public ExpirationService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !expiresAt.isAfter(Instant.now(clock));
    }
}
```

Test passing a fixed clock:

```java
@Test
void considersTokenExpiredWhenExpiryEqualsCurrentTime() {
    Instant now = Instant.parse("2026-01-10T10:00:00Z");
    Clock fixedClock = Clock.fixed(now, ZoneOffset.UTC);
    ExpirationService service = new ExpirationService(fixedClock);

    assertTrue(service.isExpired(now));
}
```

Here `Clock` is not an outbound port to an external service, yet it illustrates the same principle: inject dependencies that can vary outcomes via the constructor so tests control them. For ID generation, inject an `OrderIdGenerator` so tests can verify the use case passes the right ID across ports or produces deterministic data.

## 19. Testing Adapters with Spring

Once unit tests confirm the use case calls ports properly, verify real adapters at the right level. Examples include:

| Adapter | Appropriate Test | What to Verify |
| --- | --- | --- |
| JPA repository adapter | `@DataJpaTest` or integration test | Mappings, queries, constraints, saving and reading data |
| HTTP payment adapter | Mock server or `@RestClientTest` | URL, method, headers, body, response mapping, and timeouts |
| Message producer | Broker test with Testcontainers or suitable broker double | Topic, key, serialization, acks, and send errors |
| Email adapter | Adapter test with SMTP sandbox or fake server | Recipients, content, encoding, and send errors |
| File storage adapter | Test with temporary filesystem or storage emulator | Paths, contents, permissions, and error handling |

Afterward, an application-level integration test can verify Spring injects the right adapters into the service. Unit tests do not need to boot an `ApplicationContext` just to pass mocks into constructors. Conversely, integration tests pull beans from Spring to check configuration, proxies, and wiring.

## 20. A Complete Example of a Use-Case Test Suite

For the order placement use case, scenarios can be organized by side effect:

| Scenario | Business Outcome | Ports Called |
| --- | --- | --- |
| Payment approved | Return order ID | Payment, repository, notification |
| Payment declined | Throw decline error | Payment; do not save order, do not send confirmation |
| Invalid input data | Throw business validation error | Do not call external ports |
| Saving order fails after payment | Return error or trigger compensation per design | Payment and repository; possibly refund/compensation port |
| Duplicate request with same idempotency key | Return existing result | Read idempotency store; produce no duplicate side effects |

Sample tests:

```java
@Test
void doesNotCallExternalPortsWhenCommandIsInvalid() {
    PlaceOrderCommand invalid = commandWithNoItems();

    assertThrows(InvalidOrderException.class,
        () -> service.place(invalid));

    verifyNoInteractions(payments, notifications);
    verify(orders, never()).save(any());
}

@Test
void sendsConfirmationOnlyAfterPaymentIsApproved() {
    when(payments.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    service.place(validCommand());

    verify(payments).charge(any(PaymentRequest.class));
    verify(notifications).sendConfirmation(any(OrderConfirmation.class));
}
```

`verifyNoInteractions()` fits the first test if the contract specifies invalid commands are rejected before any interaction with those ports. In other tests, use `never()` for specific side effects rather than locking down every unrelated interaction.

## 21. Common Mistakes

- **Asserting return values while ignoring side effects:** a use case might return an order ID yet fail to save data or send required requests.
- **Mocking concrete adapters instead of ports:** tests become coupled to HTTP, JPA, or broker libraries, making application logic hard to test in isolation.
- **Verifying every call:** tests break when internal details are refactored even though the external contract has not changed.
- **Not checking arguments:** a port is called, yet receives the wrong amount, ID, recipient, or payload.
- **Forgetting to verify non-invocation cases:** business errors might still trigger payments, emails, or messages.
- **Confusing calling a publisher with a delivered message:** verifying a port does not prove the broker received and persisted the message.
- **Confusing unit tests with transaction tests:** calling a service directly does not activate Spring proxies and proves nothing about commit/rollback.
- **Using fakes that deviate from the contract:** tests pass against the fake while the real adapter behaves differently.
- **Checking call counts inconsistent with retry policies:** a valid retry gets flagged as an error, or a non-idempotent side effect repeats unnoticed.
- **Putting too many responsibilities into one test:** a single test verifying payment, order persistence, email, transactions, and serialization makes root-cause diagnosis difficult on failure.

## 22. Workflow for Designing Port-Based Side-Effect Tests

When testing a use case with external interactions, follow these steps:

1. **Identify boundaries:** list databases, APIs, brokers, emails, caches, or external systems the use case calls.
2. **Define ports:** create interfaces expressing application intent and exchanged data.
3. **Specify business rules:** determine when side effects must occur, are forbidden, are retried, or require compensation.
4. **Select test doubles:** use mocks to control responses and verify interactions; use fakes when checking simple state.
5. **Inspect payloads:** assert key fields of requests, events, or commands sent across ports.
6. **Test failure branches:** confirm unwanted side effects do not occur and compensation runs when needed.
7. **Keep tests at the right layer:** unit tests verify use case decisions; adapter and integration tests verify real communication, Spring wiring, and transactions.

A unit test is valuable when it proves the application's decision at a boundary: under given conditions, the application issues the right command, with the right data, the right number of times, and without forbidden side effects. Ports keep that boundary clear, while mocks and fakes offer fast verification without starting up full infrastructure.
