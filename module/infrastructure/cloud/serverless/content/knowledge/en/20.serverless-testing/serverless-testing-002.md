# Unit Testing Java Business Logic Independently of the Cloud Runtime

Java functions in serverless environments are typically invoked via HTTP, queues, or event triggers. If business logic is written directly inside the handler and depends on the AWS SDK, Google Cloud clients, environment variables, or the network, every test run has to spin up multiple external components. Tests then become slow, prone to environment failures, and hard to diagnose as to whether a failure stems from a business rule or from infrastructure.

An effective design keeps **Java domain and use-case logic independent of the cloud runtime**. The handler only converts requests/events into internal commands; adapters communicate with databases, queues, or secret stores through interfaces; and business logic receives those dependencies via constructors. Unit tests can run in a plain JVM with simulated data, without requiring cloud credentials, networking, or a function emulator.

This lesson shows how to decouple business logic from AWS Lambda, Cloud Run, and event SDKs; write unit tests with JUnit 5; use fakes or mocks at boundaries; control time and IDs for deterministic tests; and recognize which guarantees require integration tests against a real database or cloud environment.

## Learning objectives

After this lesson, you will be able to:

- Explain why business-logic unit tests should not start a cloud runtime.
- Separate domain, application/use case, and infrastructure adapters.
- Design ports/interfaces so business logic does not depend on AWS/GCP SDKs.
- Write unit tests for business rules, boundary conditions, and error paths with JUnit 5.
- Use fake repositories, fake inventory, and mocks at the right boundaries.
- Inject `Clock`, ID generators, and configuration for deterministic testing.
- Test idempotency at the use-case level and understand the limits of in-memory tests.
- Distinguish unit tests, adapter tests, contract tests, and integration tests.
- Avoid tests that depend on wall-clock time, networking, execution order, or internal implementation details.
- Organize a test suite suited for a Java serverless CI pipeline.

## 1. Goals of unit testing in serverless

Unit tests verify a small unit of code in a controlled environment. For Java business logic, a unit may be:

- A domain policy computing prices, taxes, limits, or statuses.
- An aggregate validating legal state transitions.
- A use case orchestrating order creation, inventory reservation, or payment confirmation.
- A validator checking event schemas or input data.
- A mapper converting adapter data into an internal command.

Unit tests do not need to prove that AWS Lambda can receive real events, that an IAM role has permission to read SQS, or that Cloud Run can bind an HTTP port. Those belong to integration/deployment tests. Unit tests must answer the question: **given known inputs and state, do the business rules produce the right outcome?**

| Test type | Scope | Cloud runtime required? |
|---|---|---|
| Domain unit test | Pure Java rules and models | No |
| Use case unit test | Business flow with simulated ports | No |
| Adapter test | HTTP/event mapping, responses, and exceptions | Usually no; uses event DTOs or fixtures |
| Contract test | Request/response formats between services | Not necessarily; can run standalone |
| Repository/client integration test | SQL, transactions, serialization, or SDK adapters | May need a database/emulator or test service |
| Cloud integration test | IAM, triggers, event source mappings, networking, and deployment | Requires a test cloud environment |

Test layers complement one another. A fast unit test does not prove IAM permissions are right; a cloud integration test does not replace hundreds of business-rule boundary cases.

## 2. Decoupling the domain from the cloud runtime

A common architecture has three regions:

1. **Domain:** entities, value objects, policies, and business rules. Does not import AWS/GCP SDKs, Spring, or HTTP frameworks.
2. **Application:** use cases orchestrating business logic and defining required ports such as repositories, inventory, payments, or event publishers.
3. **Adapters/infrastructure:** Lambda handlers, HTTP controllers, queue listeners, database repositories, and cloud clients implementing those ports.

~~~mermaid
flowchart TD
    T["Unit tests"] --> D["Domain rules"]
    T --> U["Application use cases"]
    H["HTTP / Lambda / Pub/Sub adapter"] --> U
    Q["Queue / Event adapter"] --> U
    U --> P["Ports / interfaces"]
    R["Repository adapter"] -. "implements" .-> P
    I["Inventory / payment adapter"] -. "implements" .-> P
    E["Event publisher adapter"] -. "implements" .-> P
    R --> DB["Database"]
    I --> EXT["External services"]
    E --> BUS["Queue / Event bus"]
~~~

Dependencies point inward: adapters depend on the application layer; the application layer depends on abstractions/ports; the domain does not know the cloud exists. As a result, unit tests can instantiate use cases with fake objects without initializing a Lambda context, Spring container, or SDK client.

### Example package structure

~~~text
com.example.orders
  domain/
    Order.java
    OrderLine.java
    OrderPricingPolicy.java
    PriceBreakdown.java
  application/
    PlaceOrderCommand.java
    PlaceOrderUseCase.java
    PlaceOrderResult.java
    port/
      OrderRepository.java
      InventoryPort.java
      OrderIdGenerator.java
  adapter/
    inbound/
      lambda/
      http/
      messaging/
    outbound/
      dynamodb/
      jdbc/
      sqs/
      payment/
~~~

This is a suggested layout; packages may vary by project. What matters is that domain/application code does not import classes such as `APIGatewayProxyRequestEvent`, `SQSEvent`, `Context`, `DynamoDbClient`, or `PubSubMessage`.

## 3. Writing business rules as plain Java

Consider an order pricing rule: sum the line totals, apply a 10% discount when the subtotal reaches at least 1,000,000 VND, then compute an 8% tax on the discounted amount. Both tax and discount are rounded to the nearest VND using HALF_UP.

This rule needs no database, HTTP, or cloud. It can be expressed with value objects and a policy.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice) {

    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        Objects.requireNonNull(unitPrice, "unitPrice is required");
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice cannot be negative");
        }
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Pricing policy:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

public final class OrderPricingPolicy {
    private static final BigDecimal DISCOUNT_THRESHOLD =
            new BigDecimal("1000000");
    private static final BigDecimal DISCOUNT_RATE =
            new BigDecimal("0.10");
    private static final BigDecimal TAX_RATE =
            new BigDecimal("0.08");

    public PriceBreakdown calculate(List<OrderLine> lines) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("order must contain at least one line");
        }

        BigDecimal subtotal = lines.stream()
                .map(OrderLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal discount = subtotal.compareTo(DISCOUNT_THRESHOLD) >= 0
                ? subtotal.multiply(DISCOUNT_RATE)
                        .setScale(0, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;

        BigDecimal taxableAmount = subtotal.subtract(discount);
        BigDecimal tax = taxableAmount.multiply(TAX_RATE)
                .setScale(0, RoundingMode.HALF_UP);
        BigDecimal total = taxableAmount.add(tax);

        return new PriceBreakdown(subtotal, discount, tax, total);
    }
}
~~~

The result is returned in an immutable object:

~~~java
import java.math.BigDecimal;

public record PriceBreakdown(
        BigDecimal subtotal,
        BigDecimal discount,
        BigDecimal tax,
        BigDecimal total) {
}
~~~

This example fixes one tax/discount policy to illustrate testing. A real system may need to calculate based on currency, effective date, customer tier, tax region, or promotions. Those decisions should reside in separately tested domain policies rather than being hidden inside a Lambda handler.

### Testing business-rule boundaries

Use JUnit 5 to test below-threshold, exact-threshold, above-threshold, and invalid-input cases.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderPricingPolicyTest {
    private final OrderPricingPolicy policy = new OrderPricingPolicy();

    @Test
    void doesNotApplyDiscountBelowThreshold() {
        var result = policy.calculate(List.of(
                new OrderLine("SKU-1", 1, new BigDecimal("999999"))));

        assertMoney("999999", result.subtotal());
        assertMoney("0", result.discount());
        assertMoney("80000", result.tax());
        assertMoney("1079999", result.total());
    }

    @Test
    void appliesDiscountAtThreshold() {
        var result = policy.calculate(List.of(
                new OrderLine("SKU-1", 2, new BigDecimal("500000"))));

        assertMoney("1000000", result.subtotal());
        assertMoney("100000", result.discount());
        assertMoney("72000", result.tax());
        assertMoney("972000", result.total());
    }

    @Test
    void rejectsEmptyOrder() {
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.calculate(List.of()));
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        "SKU-1", 0, new BigDecimal("10000")));
    }

    private static void assertMoney(String expected, BigDecimal actual) {
        assertEquals(0, new BigDecimal(expected).compareTo(actual));
    }
}
~~~

Use `BigDecimal.compareTo` to compare monetary values because `equals` also checks scale. For example, `1.0` and `1.00` have the same numeric value but are not equal according to `equals`.

These tests run in a standard JVM. No AWS credentials, LocalStack, Google Cloud emulator, or Docker is needed.

## 4. Isolating use cases with ports/interfaces

Domain policies are already independent, but use cases typically need repositories, inventory, or ID generators. The application layer should define interfaces for those needs.

Example ports:

~~~java
import java.util.Optional;

public interface OrderRepository {
    Optional<Order> findByIdempotencyKey(String idempotencyKey);
    void save(Order order);
}

public interface InventoryPort {
    boolean reserve(java.util.List<OrderLine> lines);
}

public interface OrderIdGenerator {
    String nextId();
}
~~~

Internal models:

~~~java
import java.time.Instant;
import java.util.List;

public record Order(
        String id,
        String customerId,
        List<OrderLine> lines,
        PriceBreakdown price,
        String idempotencyKey,
        Instant createdAt) {

    public Order {
        lines = List.copyOf(lines);
    }
}

public record PlaceOrderCommand(
        String customerId,
        List<OrderLine> lines,
        String idempotencyKey) {

    public PlaceOrderCommand {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("order must contain lines");
        }
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new IllegalArgumentException("idempotencyKey is required");
        }
        lines = List.copyOf(lines);
    }
}

public record PlaceOrderResult(String orderId, java.math.BigDecimal total) {
}
~~~

The application defines business exceptions:

~~~java
public final class OutOfStockException extends RuntimeException {
    public OutOfStockException() {
        super("One or more order lines cannot be reserved");
    }
}
~~~

The use case depends on abstractions and receives time via `Clock`:

~~~java
import java.time.Clock;
import java.util.Optional;

public final class PlaceOrderUseCase {
    private final OrderRepository orders;
    private final InventoryPort inventory;
    private final OrderIdGenerator ids;
    private final OrderPricingPolicy pricing;
    private final Clock clock;

    public PlaceOrderUseCase(
            OrderRepository orders,
            InventoryPort inventory,
            OrderIdGenerator ids,
            OrderPricingPolicy pricing,
            Clock clock) {
        this.orders = orders;
        this.inventory = inventory;
        this.ids = ids;
        this.pricing = pricing;
        this.clock = clock;
    }

    public PlaceOrderResult execute(PlaceOrderCommand command) {
        Optional<Order> existing =
                orders.findByIdempotencyKey(command.idempotencyKey());

        if (existing.isPresent()) {
            return toResult(existing.get());
        }

        PriceBreakdown price = pricing.calculate(command.lines());

        if (!inventory.reserve(command.lines())) {
            throw new OutOfStockException();
        }

        Order order = new Order(
                ids.nextId(),
                command.customerId(),
                command.lines(),
                price,
                command.idempotencyKey(),
                clock.instant());

        orders.save(order);
        return toResult(order);
    }

    private static PlaceOrderResult toResult(Order order) {
        return new PlaceOrderResult(order.id(), order.price().total());
    }
}
~~~

The use case does not know whether it is running in Lambda, Cloud Run, or a plain JVM. It only knows the required ports.

The reserve-then-save order in this example is simplified. A real system must handle cases where inventory is reserved successfully but saving the order fails, or concurrent requests arrive with the same idempotency key. Transactions, reservation expiry, compensation/sagas, and the transactional outbox may be needed. Unit tests can check orchestration branches, but they do not prove distributed transactions or database unique constraints work properly.

## 5. Using fakes to test use cases

A **fake** is a simple implementation of a port, typically keeping data in memory or returning configured results. Fakes help test business flows without mocking every method or spinning up cloud SDKs.

Example in-memory test repository:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> byIdempotencyKey = new HashMap<>();

    @Override
    public Optional<Order> findByIdempotencyKey(String key) {
        return Optional.ofNullable(byIdempotencyKey.get(key));
    }

    @Override
    public void save(Order order) {
        byIdempotencyKey.put(order.idempotencyKey(), order);
    }

    int size() {
        return byIdempotencyKey.size();
    }
}
~~~

A fake inventory allows testing both success and out-of-stock scenarios:

~~~java
import java.util.List;

final class FakeInventory implements InventoryPort {
    private final boolean canReserve;
    private int reserveCalls;

    FakeInventory(boolean canReserve) {
        this.canReserve = canReserve;
    }

    @Override
    public boolean reserve(List<OrderLine> lines) {
        reserveCalls++;
        return canReserve;
    }

    int reserveCalls() {
        return reserveCalls;
    }
}
~~~

These fakes serve only unit tests. They do not simulate locks, transactions, consistency, or retry semantics of a real database.

### Testing the use case with a fixed Clock

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PlaceOrderUseCaseTest {
    private static final Instant NOW =
            Instant.parse("2026-11-17T10:15:30Z");

    private InMemoryOrderRepository orders;
    private FakeInventory inventory;
    private AtomicInteger idSequence;
    private Clock clock;

    @BeforeEach
    void setUp() {
        orders = new InMemoryOrderRepository();
        inventory = new FakeInventory(true);
        idSequence = new AtomicInteger();
        clock = Clock.fixed(NOW, ZoneOffset.UTC);
    }

    private PlaceOrderCommand command() {
        return new PlaceOrderCommand(
                "customer-7",
                List.of(new OrderLine(
                        "SKU-1", 2, new BigDecimal("300000"))),
                "idem-order-7");
    }

    private PlaceOrderUseCase useCase() {
        return new PlaceOrderUseCase(
                orders,
                inventory,
                () -> "order-" + idSequence.incrementAndGet(),
                new OrderPricingPolicy(),
                clock);
    }

    @Test
    void createsOrderAndReturnsCalculatedTotal() {
        PlaceOrderResult result = useCase().execute(command());

        assertEquals("order-1", result.orderId());
        assertEquals(
                0,
                new BigDecimal("648000").compareTo(result.total()));

        Order saved = orders
                .findByIdempotencyKey("idem-order-7")
                .orElseThrow();

        assertEquals("customer-7", saved.customerId());
        assertEquals(NOW, saved.createdAt());
        assertEquals(1, inventory.reserveCalls());
        assertEquals(1, orders.size());
    }

    @Test
    void rejectsOrderWhenInventoryCannotBeReserved() {
        inventory = new FakeInventory(false);

        assertThrows(
                OutOfStockException.class,
                () -> useCase().execute(command()));

        assertEquals(1, inventory.reserveCalls());
        assertEquals(0, orders.size());
        assertEquals(0, idSequence.get());
    }

    @Test
    void returnsExistingOrderForRepeatedIdempotencyKey() {
        Order existing = new Order(
                "order-existing",
                "customer-7",
                command().lines(),
                new PriceBreakdown(
                        new BigDecimal("600000"),
                        BigDecimal.ZERO,
                        new BigDecimal("48000"),
                        new BigDecimal("648000")),
                "idem-order-7",
                NOW);
        orders.save(existing);

        PlaceOrderResult result = useCase().execute(command());

        assertEquals("order-existing", result.orderId());
        assertEquals(0, inventory.reserveCalls());
        assertEquals(0, idSequence.get());
        assertEquals(1, orders.size());
    }
}
~~~

This test verifies business branches at the use-case level: order creation, out-of-stock rejection, and sequentially receiving the same idempotency key. It does not prove that two concurrent requests cannot both pass the key check. That guarantee must be enforced at the adapter/database via a unique constraint or atomic claim and verified with integration/concurrency tests.

## 6. Fakes, mocks, and stubs: choosing the right tool

Common concepts:

- **Stub:** returns preconfigured data to test a branch.
- **Fake:** a simple working implementation, such as an in-memory repository.
- **Mock:** an object recording calls to test interactions or simulate errors.
- **Spy:** a real object wrapped to observe or override part of its behavior.

Prefer fakes when business state can be described clearly. Use mocks when you need to verify an important interaction or simulate an error that is difficult to reproduce with a fake.

Example with Mockito:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Optional;
import org.junit.jupiter.api.Test;

class PlaceOrderUseCaseMockitoTest {
    @Test
    void doesNotSaveOrderWhenInventoryCannotBeReserved() {
        OrderRepository repository = mock(OrderRepository.class);
        InventoryPort inventory = mock(InventoryPort.class);
        PlaceOrderCommand command = new PlaceOrderCommand(
                "customer-7",
                java.util.List.of(new OrderLine(
                        "SKU-1", 1, new java.math.BigDecimal("100000"))),
                "idem-1");

        when(repository.findByIdempotencyKey("idem-1"))
                .thenReturn(Optional.empty());
        when(inventory.reserve(command.lines())).thenReturn(false);

        PlaceOrderUseCase useCase = new PlaceOrderUseCase(
                repository,
                inventory,
                () -> "unused",
                new OrderPricingPolicy(),
                java.time.Clock.fixed(
                        java.time.Instant.parse("2026-11-17T10:00:00Z"),
                        java.time.ZoneOffset.UTC));

        assertThrows(
                OutOfStockException.class,
                () -> useCase.execute(command));

        verify(repository).findByIdempotencyKey("idem-1");
        verify(inventory).reserve(command.lines());
        verify(repository, never()).save(any(Order.class));
    }
}
~~~

This example uses mocks to simulate inventory rejecting the reservation and verifies that the use case does not save the order. It tests a business-meaningful interaction. Avoid writing tests that merely assert a mock returns the exact value the test just configured.

Do not verify every internal call. If a test requires a private method or an unimportant call sequence to happen in an exact order, the test can break during refactoring even when external behavior remains correct. Assert results, observable state, and business-meaningful side effects.

## 7. Controlling time, IDs, and randomness

Serverless functions may be retried, run on different instances, or process delayed events. If business logic directly calls `Instant.now()`, `UUID.randomUUID()`, or `new Random()`, tests struggle to reproduce exact results.

Inject nondeterministic sources:

| Source | How to inject | Benefit |
|---|---|---|
| Current time | `Clock` | Use Clock.fixed in tests |
| IDs | `OrderIdGenerator` or Supplier | Use fixed IDs, easy to assert |
| Randomness | Interface/RandomGenerator | Use fixed seeds or fakes |
| Feature decisions | Policy/config snapshot | Test both branches clearly |
| Retry/backoff | Scheduler/Delay abstraction | Test retry counts without sleeping |

Example test for expiration time:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class ReservationExpiryTest {
    @Test
    void expiresAtConfiguredDeadline() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-17T10:00:00Z"),
                ZoneOffset.UTC);

        Instant expiresAt = clock.instant().plus(Duration.ofMinutes(15));

        assertEquals(
                Instant.parse("2026-11-17T10:15:00Z"),
                expiresAt);
    }
}
~~~

This is a test for the time calculation. If logic checks whether a timestamp is before or after a deadline, pass `Clock` into the domain service and test both sides of the boundary.

Never use `Thread.sleep()` to wait for timers in unit tests. Sleeping slows down tests and depends on the CI machine's scheduler. Control `Clock` or a simulated scheduler instead.

## 8. Testing validation and error mapping in adapters

A serverless handler is an inbound adapter. It translates platform events/requests into commands, invokes the use case, and translates results into responses or acknowledgements.

Example:

~~~text
API Gateway event
    -> Lambda handler / HTTP adapter
        -> parse path, body, headers, authenticated principal
        -> PlaceOrderCommand
            -> PlaceOrderUseCase
                -> domain rules and ports
        -> HTTP response / error response
~~~

Handlers should not contain pricing logic, inventory checks, or discount decisions. Those rules belong in the domain/application layer so they can be tested independently.

Adapter tests should verify:

- Missing idempotency key header is mapped to a 400 error.
- Invalid JSON body is mapped to a 400 error.
- Missing principal or missing required claim is rejected.
- Successful use case is mapped to HTTP 201 and the expected response schema.
- `OutOfStockException` is mapped to the appropriate business error code, e.g., 409.
- Infrastructure errors never leak stack traces or secrets to clients.
- Event messages with unsupported schema versions are handled per defined policy.

Use DTOs/fixtures matching platform events to test mapping. You do not need to spin up a Lambda runtime just to verify a handler reads a field from an event. However, mapping tests must use event structures matching the actual trigger type; adapters for API Gateway REST APIs and HTTP APIs have different schemas.

### Distinguishing business errors from infrastructure errors

| Error type | Example | Typical adapter response |
|---|---|---|
| Invalid input | Missing customerId, negative quantity | HTTP 400 or message rejection per contract |
| Business conflict | Out of stock, disallowed order state | HTTP 409 or business event result |
| Not found | Order does not exist or not visible to caller | HTTP 404 per policy |
| Unauthorized/forbidden | Missing identity or insufficient permissions | HTTP 401/403 |
| Transient infrastructure | Database timeout, service unavailable | HTTP 5xx or retry per trigger |
| Permanent infrastructure/config | IAM AccessDenied, incompatible schema | Alert, controlled failure; no infinite retry |

Do not turn every exception into HTTP 200 or a successful acknowledgement. With queues, a successful acknowledgement can prevent message redelivery. Classify retryable vs. non-retryable errors according to trigger semantics.

## 9. Idempotency: testing logic and limits of in-memory fakes

A unit test can prove that a use case receives the same idempotency key a second time and returns the saved order. But serverless often runs multiple invocations concurrently, potentially across multiple instances or JVMs.

An in-memory repository only serializes within a single test object. It does not simulate:

- Database unique constraints.
- Transaction isolation.
- Two invocations claiming the same key concurrently.
- Lock timeouts or deadlocks.
- Retries after a side effect committed but the response was lost.
- Message redeliveries from a queue or event source mapping.

Therefore, test in layers:

1. **Unit test:** if the key already exists, the use case does not repeat business actions sequentially.
2. **Repository integration test:** unique constraints/conditional inserts allow only one transaction to claim the key.
3. **Concurrency test:** send multiple concurrent requests with the same key and verify only one business outcome occurs.
4. **Failure/recovery test:** simulate crashes after side effects or after commit before acknowledgement, then test retries.

If business logic calls a payment provider, use a stable idempotency key at the provider and store operation state. Do not only assert mock call counts; verify the real adapter sends the same key per the provider's contract.

## 10. Testing transactions, outbox, and side effects

A use case may update a database and then publish an event. If the database commits successfully but publishing fails, the system may lose an event. If publishing succeeds but the database rolls back, consumers may receive an event for nonexistent data.

Unit tests can verify that orchestration calls the right ports and reacts to errors. But transaction atomicity requires integration tests with a real database and outbox adapter.

Transactional outbox pattern:

- Within the same database transaction, save the business record and the outbox event.
- A separate worker reads the outbox and publishes messages.
- After publishing succeeds, mark the event as sent.
- Consumers handle messages idempotently because publishing may repeat.

Tests should cover:
- Business record and outbox entry are saved in the same transaction.
- When the transaction rolls back, neither exists.
- When the publisher fails, the outbox entry remains for retry.
- When publishing succeeds but the worker crashes before marking sent, the event can be redelivered.
- Consumers receive duplicate events without duplicating side effects.

These tests go beyond pure unit tests and require a database/broker or corresponding test adapters.

## 11. Testing per trigger while keeping shared business logic

One use case may be invoked from multiple adapters:

| Trigger | Adapter responsibility | Shared business logic |
|---|---|---|
| HTTP | Parse path/body/headers, auth context, response | PlaceOrderUseCase |
| SQS/Pub/Sub | Parse message, schema version, ack/retry | ProcessOrderEventUseCase |
| Scheduler | Parse schedule input, check timestamp | ExpireReservationsUseCase |
| Workflow task | Map task input/output, task token | ApproveOrderUseCase |

Do not duplicate business rules inside each handler. Test them once in the use case, then test adapters separately to prove each trigger maps data properly.

For example, HTTP and a queue may both call `PlaceOrderUseCase`, while error policies differ: HTTP returns 409 for conflicts; a queue consumer may retry or route messages to a DLQ. That difference belongs to the adapter and trigger policy and should not alter pricing calculations or domain rules.

## 12. Configuring tests and dependencies in Maven

With Maven, you can use JUnit Jupiter and Mockito. Example test dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-junit-jupiter</artifactId>
        <version>5.14.2</version>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
~~~

These are example versions; projects should use versions managed centrally in dependency management/BOMs and compatible with the target JDK. With Spring Boot, prefer Spring Boot's dependency management rather than declaring standalone JUnit/Mockito versions when the test starter already provides them.

Run unit tests:

~~~bash
mvn test
~~~

Run a single test class:

~~~bash
mvn -Dtest=OrderPricingPolicyTest test
~~~

There is no need to launch a function emulator during the unit test step. CI can run unit tests first, followed by integration tests with databases/containers or a test cloud environment.

## 13. Organizing the test suite in a pipeline

A practical pipeline can be split by speed and dependency level:

~~~mermaid
flowchart TD
    A["Compile"] --> B["Domain unit tests"]
    B --> C["Use case unit tests"]
    C --> D["Adapter / mapping tests"]
    D --> E["Repository and contract tests"]
    E --> F["Cloud integration tests"]
    F --> G["Deploy / smoke tests"]
~~~

- **Domain unit tests:** run most frequently, requiring no framework or network.
- **Use case tests:** use fake/mock ports, verifying business flows and errors.
- **Adapter tests:** verify mapping, schemas, and responses.
- **Repository/contract tests:** check SQL, serialization, message contracts, or API clients.
- **Cloud integration tests:** verify IAM, triggers, VPCs, retries, DLQs, and real permissions in a test account/project.
- **Smoke test:** verifies the deployed revision/function receives requests or events as configured.

When a unit test fails, you should immediately know which test and business rule was violated. When a cloud integration test fails, you should know which resource/permission/region is involved. Clear layering reduces investigation time.

## 14. Anti-patterns to avoid

| Anti-pattern | Why it is problematic | Alternative |
|---|---|---|
| Tests require AWS/GCP credentials | Hard to run locally and account-dependent | Test domain/use cases through ports |
| Starting full Spring context for every rule | Slow and overly broad tests | Plain Java unit test classes |
| Business logic inside Lambda handler | Hard to reuse and test | Move into use cases/domain |
| Mocking every object including value objects | Tests coupled to implementation | Use real objects and simple fakes |
| Asserting order of every internal call | Refactoring easily breaks tests | Assert outcomes and critical side effects |
| Using sleep to test timeouts | Flaky and slow | Inject Clock/scheduler |
| Sharing static mutable state across tests | Tests interfere with each other | Isolated dependencies and explicit resets |
| Testing idempotency only with a Map | Does not prove distributed atomicity | Database constraints + concurrency tests |
| Testing only the happy path | Misses boundaries and failures | Add invalid, conflict, timeout, duplicate cases |
| Running integration tests for every tiny change | Slow pipeline and wastes resources | Stratify tests by risk |

Do not run tests that depend on execution order or share mutable state across tests. JUnit may run tests in an unspecified order; each test should construct its own data and dependencies.

## 15. Unit test checklist for Java serverless

- [ ] Domain models and business policies do not import AWS/GCP SDKs.
- [ ] Use cases depend only on interfaces/ports and injected dependencies.
- [ ] Handlers only parse events/requests, call use cases, and map results.
- [ ] Tests run in a standard JVM without cloud credentials or networking.
- [ ] Tests cover happy paths, boundaries, invalid inputs, and business conflicts.
- [ ] Fakes are used for simple repositories/ports; mocks only at boundaries needing interaction verification.
- [ ] Clock, ID generators, and randomness are injected when they affect results.
- [ ] Tests do not use sleep or uncontrolled wall-clock time.
- [ ] Idempotency is tested sequentially at the use case and concurrently at the integration layer.
- [ ] Transactions, unique constraints, and outbox are tested with real adapters/databases.
- [ ] HTTP/event adapters have tests for mapping and error responses/acknowledgements.
- [ ] Test fixtures contain no secrets or production data.
- [ ] CI separates unit, adapter, contract, integration, and smoke tests.
- [ ] Assertions verify business behavior without locking down implementation details.
- [ ] Tests have descriptive behavioral names and failures pinpoint violated conditions.

## Self-check

1. Why should business-logic unit tests not require a Lambda runtime or Cloud Run container?
2. How do the responsibilities of domain, application/use case, and adapter differ?
3. How do ports/interfaces make use cases easier to test?
4. When should you use a fake instead of a Mockito mock?
5. Why should `Clock` and ID generators be injected into business logic?
6. What does unit testing idempotency with an in-memory repository prove, and what does it not prove?
7. Why do IAM permissions and event source mappings require cloud integration tests?
8. How can an HTTP adapter and an SQS adapter share a use case while handling errors differently?
9. What tests does a transactional outbox require beyond unit tests?
10. Why can a test suite with high coverage still miss business bugs?

Java business-logic unit tests are most effective when code does not depend on a specific runtime. The domain holds pure Java rules; use cases orchestrate through ports; adapters translate HTTP/events and call cloud services. With JUnit 5, fake dependencies, and injected time/ID sources, most rules can be tested quickly, repeatably, and deterministically. Guarantees around IAM, networking, transactions, and distributed concurrency are then verified at the appropriate integration layer.
