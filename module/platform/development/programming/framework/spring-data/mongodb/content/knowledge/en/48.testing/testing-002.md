# Testing Business Rules Without MongoDB

## 1. Why Separate Business Testing from the Database?

A **Spring Data MongoDB** application typically has two distinct sets of responsibilities:

- **Business rules:** when an order may be cancelled, how discounts are calculated, when a request is rejected, which state transitions are allowed, and what conditions input data must satisfy.
- **Data access:** using **MongoTemplate** or **MongoRepository** to find, save, and update documents; mapping Java to BSON; executing queries, aggregations, transactions, or reactive operations.

The first group can be verified by **unit tests running entirely inside the JVM**, without MongoDB, Docker, network connections, or a Spring ApplicationContext. These tests run fast, stay stable, and pinpoint which rule broke. The second group needs separate tests because mocks cannot prove that queries, indexes, mappings, and transactions actually run properly on MongoDB.

For example, business requirement:

> An order can only be cancelled when it is in the PENDING state; an order that has already shipped must be rejected. If cancellation is valid, save the status as CANCELLED.

We can test the state transition condition and the service's request to save the order using plain Java + Mockito. To know whether a repository operation truly updates the right document in MongoDB, an integration test is still required.

### Lesson Objectives

After this lesson, you will be able to:

1. Identify which parts of a Spring Data MongoDB application should be tested **without a database**.
2. Write unit tests for pure business functions with JUnit 5, including boundary values and invalid cases.
3. Decouple services from infrastructure using an interface (port), using Mockito or a fake to simulate data access.
4. Test synchronous and reactive business flows without starting MongoDB.
5. Clearly identify when integration tests must be added for MongoTemplate/repositories.

## 2. Defining the Testing Boundary

A simple way to organize it:

~~~mermaid
flowchart TB
    UI["REST API / Message handler"]
    S["Application service<br/>Business orchestration"]
    P["Domain policy / Entity<br/>Pure Java business rules"]
    Port["OrderGateway<br/>Data access interface"]
    Adapter["MongoOrderGateway<br/>MongoTemplate / MongoRepository"]
    DB[("MongoDB")]

    UI --> S
    S --> P
    S --> Port
    Adapter -.->|"implements"| Port
    Adapter --> DB

    UT["Unit test: JUnit + Mockito/Fake"] -.-> S
    UT -.-> P
    IT["Integration test"] -.-> Adapter
    IT -.-> DB
~~~

**Dependency direction** is the key point: business rules do not need to know which collection MongoDB uses, what shard key exists, or how the driver works. The service can depend on an interface expressed in business terms such as **OrderGateway**, while the MongoDB adapter implements that interface.

| What to verify | Test without MongoDB? | Appropriate tool |
| --- | --- | --- |
| Order total, discount eligibility, shipping fee | Yes | JUnit 5, plain Java |
| Order state transitions, validation, detecting business errors | Yes | JUnit 5 |
| Service requests saving the right data when conditions hold | Yes | Mockito or fake repository |
| Service does not write when business logic rejects | Yes | JUnit + Mockito |
| MongoDB filters produce right results against real BSON | Insufficient with mocks alone | Integration test with MongoDB |
| Mapping @Document, @Id, converters, indexes | Insufficient with mocks alone | @DataMongoTest / integration test |
| Transactions, aggregations, TTL indexes, unique indexes, sharding | No | Integration test in matching environment |
| Reactor pipeline emits right value or error per business rule | Yes | StepVerifier + stub/mock reactive gateway |
| Backpressure, driver interaction, reactive transactions with real MongoDB | Insufficient with mocks alone | Reactive integration test |

**Database-independent unit tests do not mean you can skip integration tests.** The two kinds of tests prove two different things.

## 3. Example 1: Testing Order Pricing in Plain Java

Suppose an e-commerce system has these rules:

- The cart must have at least one line; **each line's quantity is greater than 0** and **unit price is non-negative**.
- If the subtotal before discount is **at least 1,000,000 VND**, apply a **5%** discount; round the discount to the nearest dong using **HALF_UP**.
- Shipping fee is **30,000 VND** if the amount **after discount** is less than **500,000 VND**; at or above that threshold, shipping is free.
- Grand total = subtotal before discount − discount + shipping fee.

These rules do not need any repository. Implement them in an object with no dependency on Spring or MongoDB.

### 3.1. Business Code

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;

record CartLine(BigDecimal unitPrice, int quantity) {
    CartLine {
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Price must not be negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}

record PriceBreakdown(
    BigDecimal subtotal,
    BigDecimal discount,
    BigDecimal shippingFee,
    BigDecimal total
) {}

final class PricingPolicy {
    private static final BigDecimal DISCOUNT_THRESHOLD =
        new BigDecimal("1000000");
    private static final BigDecimal DISCOUNT_RATE =
        new BigDecimal("0.05");
    private static final BigDecimal FREE_SHIPPING_THRESHOLD =
        new BigDecimal("500000");
    private static final BigDecimal SHIPPING_FEE =
        new BigDecimal("30000");

    PriceBreakdown quote(List<CartLine> lines) {
        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Cart must not be empty");
        }

        BigDecimal subtotal = lines.stream()
            .map(line -> line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal discount = subtotal.compareTo(DISCOUNT_THRESHOLD) >= 0
            ? subtotal.multiply(DISCOUNT_RATE)
                .setScale(0, RoundingMode.HALF_UP)
            : BigDecimal.ZERO;

        BigDecimal afterDiscount = subtotal.subtract(discount);
        BigDecimal shippingFee =
            afterDiscount.compareTo(FREE_SHIPPING_THRESHOLD) >= 0
                ? BigDecimal.ZERO
                : SHIPPING_FEE;

        return new PriceBreakdown(
            subtotal,
            discount,
            shippingFee,
            afterDiscount.add(shippingFee)
        );
    }
}
~~~

**Why use BigDecimal?** Currency should not be calculated with **double** because binary floating-point representation can introduce rounding errors. Setting explicit thresholds and rounding rules helps tests verify exact business outcomes. In this example, prices are in whole VND; a real application may also check scale, currency, tax, and other rounding rules.

### 3.2. Unit Tests with JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class PricingPolicyTest {
    private final PricingPolicy policy = new PricingPolicy();

    private PriceBreakdown quote(String unitPrice) {
        return policy.quote(
            List.of(new CartLine(new BigDecimal(unitPrice), 1))
        );
    }

    @Test
    void belowDiscountThresholdDoesNotApplyDiscount() {
        PriceBreakdown result = quote("999999");

        assertEquals(new BigDecimal("999999"), result.subtotal());
        assertEquals(BigDecimal.ZERO, result.discount());
        assertEquals(BigDecimal.ZERO, result.shippingFee());
        assertEquals(new BigDecimal("999999"), result.total());
    }

    @Test
    void atDiscountThresholdAppliesFivePercent() {
        PriceBreakdown result = quote("1000000");

        assertEquals(new BigDecimal("50000"), result.discount());
        assertEquals(new BigDecimal("950000"), result.total());
    }

    @ParameterizedTest
    @CsvSource({
        "499999, 30000, 529999",
        "500000, 0, 500000"
    })
    void shippingFeeChangesAtThreshold(
        String subtotal, String expectedFee, String expectedTotal
    ) {
        PriceBreakdown result = quote(subtotal);

        assertEquals(new BigDecimal(expectedFee), result.shippingFee());
        assertEquals(new BigDecimal(expectedTotal), result.total());
    }

    @Test
    void discountUsesHalfUpRounding() {
        PriceBreakdown result = quote("1000011");

        // 1,000,011 * 5% = 50,000.55 => rounded to 50,001 VND
        assertEquals(new BigDecimal("50001"), result.discount());
        assertEquals(new BigDecimal("950010"), result.total());
    }

    @Test
    void emptyCartIsRejected() {
        assertThrows(
            IllegalArgumentException.class,
            () -> policy.quote(List.of())
        );
    }

    @Test
    void invalidCartLineIsRejected() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new CartLine(new BigDecimal("-1"), 1)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> new CartLine(new BigDecimal("1000"), 0)
        );
    }
}
~~~

These tests simply instantiate **PricingPolicy** and call its method; there are no **@SpringBootTest**, **@DataMongoTest**, or MongoDB connections.

A good business test should prove **observable outcomes**. Do not write tests that merely mirror statements inside the method or verify private helper calls. Those tests easily stay green even when boundary conditions are wrong.

### 3.3. Finding Easily Missed Boundary Cases

For the policy above, evaluate these cases:

| Check group | Example | Why test it? |
| --- | --- | --- |
| Below, at, above discount threshold | 999,999 / 1,000,000 / 1,000,001 | Catches using **>** instead of **>=**. |
| Below, at, above free-shipping threshold | 499,999 / 500,000 / 500,001 | Verifies the boundary and currency units. |
| Discount rounding | 1,000,011 × 5% | Catches rounding bugs or double conversion. |
| Multiple line items | 2 items × 3 units | Catches mixing up quantity and unit price. |
| Invalid input | Empty cart, negative price, quantity 0 | Verifies rejection rules. |
| Order of rule application | Shipping fee calculated after discount | Prevents unintended shifts when changing the algorithm. |

Prices near the free-shipping threshold **after subtracting the discount** are easily overlooked as promotions evolve. When adding a new condition, add cases for the new behavior, not just tests for the new lines of code.

## 4. Example 2: Testing a Service That Saves Data

Not every rule is a calculation function. A service often reads existing data, makes a business decision, and saves the result. It can still be unit-tested without MongoDB by having the service depend on a **port**.

Suppose the rule is: an order may only be cancelled in status **PENDING**; if the order does not exist, throw an error; when cancellation succeeds, save status **CANCELLED**.

### 4.1. Domain and Data Access Port

~~~java
import java.util.NoSuchElementException;
import java.util.Optional;

enum OrderStatus {
    PENDING, PAID, SHIPPED, CANCELLED
}

record Order(String id, OrderStatus status) {
    Order cancel() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                "Only PENDING orders can be cancelled"
            );
        }
        return new Order(id, OrderStatus.CANCELLED);
    }
}

interface OrderGateway {
    Optional<Order> findById(String id);
    void save(Order order);
}

final class CancelOrderService {
    private final OrderGateway gateway;

    CancelOrderService(OrderGateway gateway) {
        this.gateway = gateway;
    }

    Order cancel(String id) {
        Order current = gateway.findById(id)
            .orElseThrow(
                () -> new NoSuchElementException("Order not found: " + id)
            );

        Order cancelled = current.cancel();
        gateway.save(cancelled);
        return cancelled;
    }
}
~~~

The **Order** class holds the state transition rule. **CancelOrderService** coordinates reading and saving without importing any MongoDB classes. The **OrderGateway** interface is designed in business terms; the MongoDB-backed implementation is provided when the real application runs.

### 4.2. Testing the Service with Mockito

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import java.util.NoSuchElementException;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CancelOrderServiceTest {
    private OrderGateway gateway;
    private CancelOrderService service;

    @BeforeEach
    void setUp() {
        gateway = mock(OrderGateway.class);
        service = new CancelOrderService(gateway);
    }

    @Test
    void pendingOrderCanBeCancelledAndSaved() {
        when(gateway.findById("o-100"))
            .thenReturn(Optional.of(
                new Order("o-100", OrderStatus.PENDING)
            ));

        Order actual = service.cancel("o-100");

        Order expected = new Order("o-100", OrderStatus.CANCELLED);
        assertEquals(expected, actual);
        verify(gateway).save(expected);
    }

    @Test
    void shippedOrderIsRejectedWithoutSaving() {
        when(gateway.findById("o-200"))
            .thenReturn(Optional.of(
                new Order("o-200", OrderStatus.SHIPPED)
            ));

        assertThrows(
            IllegalStateException.class,
            () -> service.cancel("o-200")
        );
        verify(gateway, never()).save(any(Order.class));
    }

    @Test
    void missingOrderIsRejectedWithoutSaving() {
        when(gateway.findById("missing"))
            .thenReturn(Optional.empty());

        assertThrows(
            NoSuchElementException.class,
            () -> service.cancel("missing")
        );
        verify(gateway, never()).save(any(Order.class));
    }
}
~~~

No MongoDB server is created in these tests:

1. **Arrange:** Mockito sets up a fake response for **findById**.
2. **Act:** the service runs the actual cancellation rule.
3. **Assert:** verify the return value or exception, and check the **save** side effect.

Verifying that **save is never called** on rejection is especially important: bugs exist where code produces the right error message yet still writes invalid data before throwing.

**Distinguish two things:** Mockito proves the service **issues the right command** to the gateway; it does not prove a real record was updated in MongoDB. That responsibility belongs to adapter testing.

### 4.3. Adapter Using Spring Data MongoDB

The following example illustrates connecting the port to a repository; this is **application runtime code** and does not need to be invoked in the unit tests above.

~~~java
import java.util.Optional;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.stereotype.Repository;

@Document(collection = "orders")
record OrderDocument(@Id String id, String status) {}

interface SpringOrderRepository
        extends MongoRepository<OrderDocument, String> {}

@Repository
class MongoOrderGateway implements OrderGateway {
    private final SpringOrderRepository repository;

    MongoOrderGateway(SpringOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<Order> findById(String id) {
        return repository.findById(id)
            .map(doc -> new Order(
                doc.id(), OrderStatus.valueOf(doc.status())
            ));
    }

    @Override
    public void save(Order order) {
        repository.save(new OrderDocument(
            order.id(), order.status().name()
        ));
    }
}
~~~

Split the code into appropriate Java files and packages when integrating into a project. The adapter is responsible for mapping documents to domain objects and back. When replacing **MongoRepository** with **MongoTemplate**, the business service still works exclusively through **OrderGateway**.

This illustration simplifies concurrency requirements. In production, the “cancel only PENDING” rule may need a **conditional atomic update** or **optimistic locking** to prevent the order from transitioning to SHIPPED after the read but before the save. Unit tests cannot prove safety against race conditions in MongoDB; that must be designed and tested at the adapter/database level.

## 5. When to Use a Fake Repository Instead of a Mock?

A **fake** is a simple in-memory implementation. Fakes are useful when many tests need basic CRUD operations or need to inspect state after a sequence of actions.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

final class InMemoryOrderGateway implements OrderGateway {
    private final Map<String, Order> orders = new HashMap<>();

    void seed(Order order) {
        orders.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CancelOrderWithFakeTest {

    @Test
    void cancellationChangesStoredOrder() {
        InMemoryOrderGateway gateway = new InMemoryOrderGateway();
        gateway.seed(new Order("o-300", OrderStatus.PENDING));
        CancelOrderService service = new CancelOrderService(gateway);

        service.cancel("o-300");

        assertEquals(
            OrderStatus.CANCELLED,
            gateway.findById("o-300").orElseThrow().status()
        );
    }
}
~~~

| Tool | Advantages | Limitations |
| --- | --- | --- |
| **Mockito mock** | Explicitly checks interactions, arguments, and non-write cases. | Easily makes tests overly coupled to how the service calls methods internally. |
| **In-memory fake** | Convenient for inspecting state across multiple steps with minimal stubbing. | Risks inaccurately simulating real MongoDB behavior. |
| **Real MongoDB via integration test** | Verifies mapping, queries, and real persistence properties. | Slower startup; requires managed test environment and test data. |

Fakes **do not inherently enforce** unique indexes, transactions, collations, aggregations, query semantics, or atomic updates the way MongoDB does. Do not use fake test results to claim those mechanisms work properly.

## 6. Do Not Start Spring Until Needed

For pure business tests, you usually only need:

~~~java
PricingPolicy policy = new PricingPolicy();
OrderGateway gateway = mock(OrderGateway.class);
CancelOrderService service = new CancelOrderService(gateway);
~~~

These statements do not build a **Spring ApplicationContext** or open a MongoDB connection. Avoid using **@SpringBootTest** for simple calculations just because a service is annotated with **@Service** in the application. Likewise, **@DataMongoTest** is an option for testing the MongoDB layer, not a prerequisite for unit tests.

A common dependency configuration in a Gradle-based Spring Boot project is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**spring-boot-starter-test** typically provides JUnit Jupiter, AssertJ, and Mockito under the versions managed by Spring Boot. Depending on your Gradle/Spring Boot version and project setup, ensure tests run on JUnit Platform (for example, **useJUnitPlatform()** if not already configured):

~~~groovy
tasks.named('test') {
    useJUnitPlatform()
}
~~~

Place test files under **src/test/java** in matching packages, then run specific test suites:

~~~bash
./gradlew test --tests "*PricingPolicyTest"
./gradlew test --tests "*CancelOrderServiceTest"
~~~

In Maven or Windows projects, equivalent commands vary according to the build tool and wrapper available. The commands above illustrate how to organize test execution, not a report that tests were executed in the current repository.

### When Decoupling from Spring Is Not Easy

An existing business class may be reading **@Value**, calling **MongoTemplate** in its constructor, or depending directly on **MongoRepository**. You can refactor incrementally:

1. Extract environment-dependent settings into parameters or a configuration object passed via the constructor.
2. Move calculations and validation into a plain Java class with no framework dependencies.
3. Place persistence calls behind an injected gateway or repository.
4. For rules needing the current time, inject **Clock**; for random IDs, supply a controllable ID generator in tests.

**You do not necessarily have to rewrite the entire architecture** to have unit tests: you can mock the **MongoRepository** interface directly in an existing service, as long as you do not confuse those results with testing MongoDB.

## 7. Testing Reactive Business Logic Without MongoDB

Spring Data MongoDB supports reactive access via **ReactiveMongoRepository** or **ReactiveMongoTemplate**. In business tests, you can define a gateway returning **Mono/Flux** and use **StepVerifier** to assert emitted values, errors, and stream completion.

The same order-cancellation rule as above:

~~~java
import java.util.NoSuchElementException;
import reactor.core.publisher.Mono;

interface ReactiveOrderGateway {
    Mono<Order> findById(String id);
    Mono<Order> save(Order order);
}

final class ReactiveCancelOrderService {
    private final ReactiveOrderGateway gateway;

    ReactiveCancelOrderService(ReactiveOrderGateway gateway) {
        this.gateway = gateway;
    }

    Mono<Order> cancel(String id) {
        return gateway.findById(id)
            .switchIfEmpty(Mono.error(
                new NoSuchElementException("Order not found: " + id)
            ))
            .map(Order::cancel)
            .flatMap(gateway::save);
    }
}
~~~

~~~java
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveCancelOrderServiceTest {

    @Test
    void pendingOrderIsSavedAndEmitted() {
        ReactiveOrderGateway gateway = mock(ReactiveOrderGateway.class);
        Order existing = new Order("o-400", OrderStatus.PENDING);
        Order cancelled = new Order("o-400", OrderStatus.CANCELLED);

        when(gateway.findById("o-400")).thenReturn(Mono.just(existing));
        when(gateway.save(cancelled)).thenReturn(Mono.just(cancelled));

        Mono<Order> result = new ReactiveCancelOrderService(gateway)
            .cancel("o-400");

        StepVerifier.create(result)
            .expectNext(cancelled)
            .verifyComplete();

        verify(gateway).save(cancelled);
    }

    @Test
    void invalidTransitionEmitsErrorWithoutSaving() {
        ReactiveOrderGateway gateway = mock(ReactiveOrderGateway.class);
        when(gateway.findById("o-401"))
            .thenReturn(Mono.just(
                new Order("o-401", OrderStatus.SHIPPED)
            ));

        StepVerifier.create(
                new ReactiveCancelOrderService(gateway).cancel("o-401")
            )
            .expectError(IllegalStateException.class)
            .verify();

        verify(gateway, never()).save(any(Order.class));
    }
}
~~~

These tests require **reactor-test** to use StepVerifier. If the project does not yet include this dependency, configure a version compatible with the Reactor version in use, usually via Spring Boot dependency management:

~~~groovy
testImplementation 'io.projectreactor:reactor-test'
~~~

**Notable trait of reactive code:** a pipeline can be assembled upfront, but logic only actually runs when subscribed to; **StepVerifier** triggers execution and observes both results and error signals. There is no need to wait with **Thread.sleep()**. For flows with delays or timeouts in business code, **StepVerifier.withVirtualTime** can be used when the code is structured appropriately.

## 8. Strategy for Building Valuable Unit Tests

### 8.1. Test Behavior from Requirements

Express tests in business language: **pendingOrderCanBeCancelledAndSaved**, **shippedOrderIsRejectedWithoutSaving**, **atDiscountThresholdAppliesFivePercent**. A good test answers:

- What are the input conditions?
- What result or error does the rule require?
- When an error occurs, what side effects must definitely not happen?

Do not mock **PricingPolicy** or **Order.cancel()** itself when the goal is to test their logic; doing so removes the very code under verification.

### 8.2. Verify State and Sufficient Interactions

Prefer asserting meaningful outputs and states. For behaviors with required side effects, add **verify** or check fake state. Avoid asserting the order of every internal call unless that ordering is a business requirement, as harmless refactoring can break such tests.

### 8.3. Include Negative Tests and Boundary Tests

Failure branches are often more critical than the “happy path”: missing orders, invalid states, negative prices, zero quantities, discount thresholds, and rounding cases. A test checking only normal inputs often fails to catch regressions when requirements change.

### 8.4. Control Non-Deterministic Data

If a service uses **Instant.now()**, **UUID.randomUUID()**, external APIs, or event publishers, pass a **Clock**, ID supplier, or suitable interface to keep tests repeatable. Avoid testing time with real waits or tight comparisons against the system clock.

### 8.5. Separate Unit Tests and Integration Tests in CI

Business unit tests should run very frequently, such as on every code change or pull request. Integration tests with MongoDB should run in an appropriate pipeline stage to verify interactions with a real database. Separating tests by purpose catches business bugs quickly while preserving confidence in persistence.

## 9. When Is Real MongoDB Mandatory for Verification?

Some behaviors **cannot be adequately verified** with mocks or fakes:

| Behavior | Why unit tests are insufficient? |
| --- | --- |
| Derived queries like **findByTenantIdAndStatus** | Mockito does not run the query parser or BSON queries on MongoDB. |
| **MongoTemplate Query/Criteria**, collation, regex | Needs to verify how the server actually evaluates filters. |
| **Aggregation pipelines** | Group, lookup, unwind stages, and BSON type handling have MongoDB-specific semantics. |
| **@Document**, **@Id**, custom converters | Java ↔ BSON mapping may differ from assumptions in domain tests. |
| **Unique indexes**, TTL indexes, compound indexes | Index enforcement and behavior come from the MongoDB server. |
| **Transactions** and rollback mechanisms | Depend on sessions, topology, and actual MongoDB deployment. |
| **Optimistic locking** via **@Version** | Requires verifying write conflicts against real persistence. |
| **Reactive MongoDB** | Driver, timeouts, backpressure, and real connections require an integration environment. |

In Spring Boot projects, **@DataMongoTest** is suitable for initializing MongoDB-related configuration and testing repositories, converters, or MongoTemplate against a suitable MongoDB environment. **Testcontainers** is a popular option for supplying MongoDB in integration tests; when testing transactions, ensure the MongoDB topology supports transactions (such as a replica set).

Do not assume simply enabling **@DataMongoTest** automatically gives you a running MongoDB instance. Test configuration must specify the actual test database, container or test infrastructure lifecycle, and data cleanup strategy.

### The Race Condition Problem

The **cancel()** example above consists of reading the status and then saving. Two concurrent threads could both read **PENDING**; one transitions the order to **SHIPPED**, while the other saves **CANCELLED**. Mock-based unit tests typically miss this risk.

One MongoDB-layer solution is a **conditional atomic update**: update only if **_id** matches and the current status is still **PENDING**; inspect the modified document count to determine success or conflict. You can use MongoTemplate with **Query** and **Update** for such operations. Unit tests can check how the service handles the “not updated” result, while integration tests must verify atomicity on real MongoDB.

## 10. Common Test Design Mistakes

| Error-prone practice | Consequence | Improvement |
| --- | --- | --- |
| Every unit test uses **@SpringBootTest** | Slow startup, dependent on configuration and infrastructure. | Instantiate the class under test directly via its constructor when testing business logic. |
| Mocking the very business logic under test | Tests always pass even when rules are broken. | Keep domain/policy objects real; mock only at the I/O boundary. |
| Testing only a single normal value | Misses boundary condition bugs. | Add below/at/above threshold, invalid input, and error branches. |
| Using **Thread.sleep()** to wait on reactive streams | Slow and flaky tests. | Use StepVerifier, and virtual time where appropriate. |
| Building a fake repository that simulates all of MongoDB | Complex fake whose semantics diverge from the real server. | Simulate only the behavior the service needs; test DB semantics with integration tests. |
| Asserting only the exception while ignoring side effects | Invalid data may still be written before throwing. | Verify **never().save(...)** or inspect fake state. |
| Comparing **BigDecimal** carelessly | **equals()** distinguishes scale, e.g., 1.0 vs 1.00. | Define explicit scale or use **compareTo()** when only numeric value matters. |
| Hiding dependencies inside static/global singletons | Hard to write independent tests; tests interfere with one another. | Inject dependencies via constructor; avoid shared mutable state. |
| Treating mock tests as proof that queries/indexes work | Persistence bugs slip past CI. | Add integration tests according to actual risks. |

## 11. Workflow for Applying This in a Project

1. **List business rules** from the use case: inputs, accept/reject conditions, outcomes, side effects.
2. **Isolate pure code:** extract calculation, state, and validation policies away from MongoTemplate/repository calls.
3. **Define I/O boundaries:** choose small, suitable interfaces when reading/saving data, publishing events, or calling external services.
4. **Write unit tests for boundary values first:** prioritize tricky, error-prone requirements and failure branches; use JUnit 5.
5. **Mock/stub minimally:** Mockito when you need to verify interactions; fakes when tracking state across multiple steps.
6. **Run tests in the JVM:** no MongoDB, Docker, or full Spring context startup for these business rules.
7. **Write integration tests for the MongoDB adapter:** mapping, filters, save/update, indexes, transactions, and data contention scenarios.
8. **Evaluate test effectiveness:** business bugs must be caught by clear unit tests; infrastructure/query bugs must be caught by integration tests.

### Self-Check Questions

**1. If a service uses MongoRepository, must we run MongoDB to test it?** No. You can inject a mock repository or extract a gateway to test business rules and service interactions. Separate integration tests are needed to prove the repository works properly with MongoDB.

**2. Is @DataMongoTest the fastest way to test a discount calculation?** No. A **PricingPolicyTest** using plain Java/JUnit directly is sufficient and more focused.

**3. Does mocking a repository to return a PENDING order prove MongoDB stores that order properly?** No. A mock is merely input data configured by the test itself.

**4. How do we verify a service does not write data when business logic rejects?** With Mockito, use **verify(gateway, never()).save(...)**. With a fake, assert the stored state remains unchanged.

**5. Does using StepVerifier to test a Mono require MongoDB?** No, if the data comes from a stub/mock reactive gateway. StepVerifier subscribes to the pipeline and verifies signals.

**6. Can a typical unit test prove safety against a race condition between reading status and writing an update?** No. You must design the write operation appropriately, such as a conditional update or optimistic locking, and then test it against real MongoDB.

## Conclusion

With **Spring Data MongoDB**, most **business rules** can be tested inside the JVM using **JUnit 5**, combined with **Mockito** or a simple fake when the service depends on persistence. Decoupling domain/policies from MongoTemplate and repositories makes tests fast, clear, and minimally environment-dependent; services still integrate with MongoDB through adapters. When you need to verify **BSON mapping, queries, aggregations, indexes, transactions, reactive drivers, or update atomicity**, you must add integration tests with MongoDB. A strong test suite maintains a clear boundary: **unit tests prove business decisions; integration tests prove real data operations**.
