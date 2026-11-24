# Testing Services with Constructor Injection Without Starting Spring

In Spring Boot, a service typically contains business rules and coordinates with components such as repositories, HTTP clients, clocks, or message publishers. To test **the logic of the service itself**, we can use **JUnit Jupiter + plain Java**, instantiate the real service via its constructor, and supply controllable dependencies in the test. **There is no need to initialize a Spring `ApplicationContext`** if the behavior being verified does not depend on the framework.

This is the foundational technique of **business unit tests**: fast execution, easy root-cause identification when a test fails, full control over inputs, and encouragement of clear dependency boundaries. The goal is to test the **real business code** of the service. Edge dependencies are replaced with mocks, stubs, fakes, or deterministic objects (such as `Clock.fixed`), depending on the question to be proven.

## 1. Identifying the Target and Boundaries of the Test

Suppose an ordering system has the following diagram:

```text
HTTP request
    |
    v
OrderController
    |
    v
OrderService  <--- SUT: processes real business rules
    |-- StockGateway ----> REST API / inventory system
    |-- OrderStore ------> database
    \-- Clock -----------> system clock
```

The **SUT (System Under Test)** is `OrderService`. What needs to be verified is not HTTP or the database, but the service's decisions: validating input, querying stock availability, creating the order at the right timestamp, and requesting persistence only when valid.

We can describe the requirements:

| Scenario | Given | When | Then |
| --- | --- | --- | --- |
| Valid, in stock | Inventory returns `true` | `place("BOOK-7", 2)` | Returns `Order` with exact data and requests saving once |
| Out of stock | Inventory returns `false` | `place("BOOK-7", 2)` | Throws `OutOfStockException`, does not save |
| Blank SKU | `sku = " "` | `place(" ", 2)` | Throws data error without calling inventory or store |
| Invalid quantity | `quantity = 0` | `place("BOOK-7", 0)` | Throws data error, does not call dependencies |
| Inventory failure | Inventory throws exception | `place("BOOK-7", 2)` | Per example contract, propagates error and does not save |

All of these cases can run the **real service** with fakes/mocks at the two ports and a fixed clock. The unit test proves that the service **requests** saving when appropriate; it does not by itself prove that SQL ran, the DB committed, or what HTTP status was returned.

**The right boundary depends on the question:** “When stock is insufficient, the service does not save” is a unit test question. “`@Transactional` rolls back when the repository throws an exception” is an integration test question because transactions are handled by Spring's proxy/transaction manager.

## 2. Constructor Injection Allows Constructing the Service Like Plain Java

**Constructor injection** passes required dependencies through the constructor:

```java
public OrderService(
        StockGateway stock,
        OrderStore store,
        Clock clock) {
    this.stock = Objects.requireNonNull(stock, "stock");
    this.store = Objects.requireNonNull(store, "store");
    this.clock = Objects.requireNonNull(clock, "clock");
}
```

This is a **snippet inside the full `OrderService` class in section 4**. Using `Objects.requireNonNull` fails fast if a test or production code forgets to pass a dependency. References are typically kept in `private final` fields.

In a real Spring Boot application, Spring can invoke the constructor to create the bean. In a unit test, we call it directly:

```java
OrderService sut =
        new OrderService(stockDouble, storeDouble, fixedClock);
```

There is no difference in how Java executes the `place` method. What differs is who creates the dependencies: Spring at runtime, whereas the test creates suitable doubles itself.

**Benefits of constructor injection:**

- Dependencies are listed in the constructor signature, not hidden in fields injected automatically.
- No need to start Spring to construct a complete object; no reflection is needed to assign dependencies.
- Prevents passing `null` and hitting a late failure inside a business method.
- Easy to swap I/O with mocks/fakes and the real clock with a fixed clock.
- When a new required dependency is added, constructor call sites no longer match the signature and are flagged by the compiler, helping update tests promptly.

**Compared to field injection:** a field `@Autowired private OrderStore store;` is only processed by Spring when the bean is managed. If you write `new OrderService()` for a class relying on field injection, that field is not assigned by Spring; the test may hit a `NullPointerException` or require reflection. Constructor injection solves this at the design level.

**No need to create an interface for every class.** A value `record`, pure calculation, or deterministic policy within the scope under test should generally be kept real. Interfaces/ports are especially useful at DB, network, file, messaging, or data-source boundaries whose outcomes must be controlled.

## 3. Instantiate the Real Service, Replace Only Collaborators

There are four roles to distinguish:

- **SUT:** the real service object invoked via `sut.place(...)`.
- **Stub:** a collaborator returning preconfigured data, e.g., `when(stock.available(...)).thenReturn(false)`.
- **Mock:** a collaborator used to verify interactions such as `verify(store).save(expected)` or `verifyNoInteractions(store)`.
- **Fake:** a simple working implementation, e.g., an `OrderStore` that stores items in an `ArrayList` instead of a database.

Mockito can perform both stub and mock roles. **Mockito's `@Mock` does not require a Spring context.** `@ExtendWith(MockitoExtension.class)` is a JUnit extension that creates mocks, not a command to start Spring Boot.

| Part in the example | What is used in the unit test? | Why? |
| --- | --- | --- |
| `OrderService` | Real object via `new` | Executes the actual business branches |
| `StockGateway` | Stub/mock or lambda fake | Forces in-stock/out-of-stock or inventory failure responses |
| `OrderStore` | Mock or in-memory fake | Verifies save command or absence of saving |
| `Clock` | `Clock.fixed(...)` | Independent of the test execution time |
| `Order` | Real Java record | Verifies data values |
| Spring container | Not used | No framework behavior needs to be proven in these cases |

**Critical mistake:** if you mock `OrderService` itself and stub `place(...)` to return the expected order, the test only confirms that Mockito returns what it was told. It does not test validation, out-of-stock handling, or saving in production code.

## 4. Complete Example with Java 17+: OrderService

The example below is designed to compile with JDK 17+ and run in a Spring Boot project that already includes JUnit Jupiter/Mockito. Business rules live in plain Java without needing Spring annotations for the service to function.

File layout:

```text
src/
├── main/java/example/testing/orders/
│   ├── OrderService.java
│   └── OrderServiceDemo.java
└── test/java/example/testing/orders/
    ├── OrderServiceTest.java
    └── OrderServiceFakeTest.java
```

### 4.1. Production file: OrderService.java

Create `src/main/java/example/testing/orders/OrderService.java`:

```java
package example.testing.orders;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public class OrderService {
    private final StockGateway stock;
    private final OrderStore store;
    private final Clock clock;

    public OrderService(
            StockGateway stock,
            OrderStore store,
            Clock clock) {
        this.stock = Objects.requireNonNull(stock, "stock");
        this.store = Objects.requireNonNull(store, "store");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public Order place(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        if (!stock.available(sku, quantity)) {
            throw new OutOfStockException(sku);
        }

        Order order = new Order(
                sku, quantity, Instant.now(clock));
        store.save(order);
        return order;
    }
}

interface StockGateway {
    boolean available(String sku, int quantity);
}

interface OrderStore {
    void save(Order order);
}

record Order(String sku, int quantity, Instant createdAt) {}

class OutOfStockException extends RuntimeException {
    OutOfStockException(String sku) {
        super("Out of stock: " + sku);
    }
}
```

In Java, this file is valid because there is only one `public` top-level type, `OrderService`, and the filename matches that type name. The remaining interfaces, record, and exception are **package-private**. Because the tests are in the same `example.testing.orders` package, they can access them. Larger projects can split each type into its own file and adjust visibility when adapters live in other packages.

**Execution flow:**

1. The constructor rejects any of the three dependencies being null.
2. `place` validates `sku` and `quantity` before interacting with external dependencies.
3. `StockGateway.available(sku, quantity)` determines whether stock is available.
4. Out of stock: throws `OutOfStockException`; does not call the store.
5. In stock: creates the `Order` record with `Instant.now(clock)`, calls `store.save(order)`, and returns the record.

In this example, if `stock.available` or `store.save` throws an exception, the service **neither catches nor retries**; the error propagates to the caller. This is the current behavior of the example code, not a universal rule for every system. If business requirements call for retry/idempotency/compensation, those must be designed and tested separately.

### 4.2. JUnit Jupiter test suite with Mockito

Create `src/test/java/example/testing/orders/OrderServiceTest.java`:

```java
package example.testing.orders;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    private static final Instant NOW =
            Instant.parse("2026-01-15T08:00:00Z");

    @Mock
    StockGateway stock;

    @Mock
    OrderStore store;

    private OrderService sut;

    @BeforeEach
    void setUp() {
        Clock fixedClock = Clock.fixed(NOW, ZoneOffset.UTC);
        sut = new OrderService(stock, store, fixedClock);
    }

    @Test
    void inStock_returnsAndSavesOrder() {
        when(stock.available("BOOK-7", 2)).thenReturn(true);

        Order actual = sut.place("BOOK-7", 2);

        Order expected = new Order("BOOK-7", 2, NOW);
        assertEquals(expected, actual);
        verify(store).save(expected);
    }

    @Test
    void outOfStock_throwsAndDoesNotSave() {
        when(stock.available("BOOK-7", 2)).thenReturn(false);

        OutOfStockException error = assertThrows(
                OutOfStockException.class,
                () -> sut.place("BOOK-7", 2));

        assertEquals("Out of stock: BOOK-7",
                error.getMessage());
        verifyNoInteractions(store);
    }

    @Test
    void blankSku_isRejectedBeforeDependencies() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> sut.place(" ", 2));

        assertEquals("sku must not be blank",
                error.getMessage());
        verifyNoInteractions(stock, store);
    }

    @Test
    void nonPositiveQuantity_isRejectedBeforeDependencies() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> sut.place("BOOK-7", 0));

        assertEquals("quantity must be positive",
                error.getMessage());
        verifyNoInteractions(stock, store);
    }

    @Test
    void inventoryFailure_isPropagatedWithoutSaving() {
        when(stock.available("BOOK-7", 2))
                .thenThrow(new IllegalStateException(
                        "inventory unavailable"));

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> sut.place("BOOK-7", 2));

        assertEquals("inventory unavailable",
                error.getMessage());
        verifyNoInteractions(store);
    }
}
```

**Key point:** the test class uses only JUnit and Mockito, **without** `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, `@Autowired`, or `@MockBean`. `MockitoExtension` manages `@Mock` through the JUnit lifecycle; `@BeforeEach` runs after Mockito has initialized the required mocks.

What does each test actually check?

- **`inStock_returnsAndSavesOrder`:** stubs the stock gateway to return `true`; the service creates the record with the exact SKU, quantity, and timestamp from the fixed clock. `verify(store).save(expected)` verifies one matching invocation by default.
- **`outOfStock_throwsAndDoesNotSave`:** throws the expected exception and never calls the store. This is an important business property: failure must not issue a save command.
- **`blankSku_isRejectedBeforeDependencies`:** invalid input is rejected before accessing inventory or store. It catches bugs where code performs I/O before validating.
- **`nonPositiveQuantity_isRejectedBeforeDependencies`:** quantity 0 is rejected at the boundary.
- **`inventoryFailure_isPropagatedWithoutSaving`:** when the inventory gateway fails, the service does not issue a save command; the test also confirms the exception-propagation behavior of the current code.

**Why must the clock be fixed?** If the service called `Instant.now()` without an injected `Clock`, the timestamp in expected could differ by a few milliseconds from actual or depend on when CI runs. Using `Clock.fixed(...)` guarantees `createdAt` always equals `NOW`, making the assertion deterministic.

**Why use a record?** `Order` is a `record`, so Java generates `equals` based on `sku`, `quantity`, and `createdAt`. `assertEquals(expected, actual)` protects all three. For entities/DTOs without value equality, assert the relevant fields directly rather than assuming every object has suitable `equals`.

### 4.3. Unit test with a fake: no Mockito needed

If you only want to observe the data sent to the store, a simple fake works well. Create `src/test/java/example/testing/orders/OrderServiceFakeTest.java`:

```java
package example.testing.orders;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderServiceFakeTest {

    @Test
    void savesOneOrderToAnInMemoryStore() {
        Instant fixedNow =
                Instant.parse("2026-01-15T08:00:00Z");
        Clock fixedClock =
                Clock.fixed(fixedNow, ZoneOffset.UTC);

        List<Order> saved = new ArrayList<>();

        StockGateway stock = (sku, quantity) -> true;
        OrderStore store = order -> {
            saved.add(order);
        };

        OrderService sut =
                new OrderService(stock, store, fixedClock);

        Order actual = sut.place("BOOK-7", 2);
        Order expected =
                new Order("BOOK-7", 2, fixedNow);

        assertEquals(expected, actual);
        assertEquals(List.of(expected), saved);
    }
}
```

Both `StockGateway` and `OrderStore` in this example are functional interfaces, so lambda implementations are valid. `List<Order>` exists only within the test scope, not as a real repository. It verifies that the service creates and sends the right data without needing `verify(...)` on every interaction.

**Choosing between mock and fake:** for behavior like “do not send a payment command when funds are insufficient”, a mock and `verifyNoInteractions` are very clear. For a simple sequence of operations over a collection of data, an in-memory fake and state assertions can be more readable. You do not have to maintain both test suites for the same happy path in production; these are two alternative techniques shown separately.

### 4.4. Gradle configuration for running tests

In a Spring Boot project already configured with the Gradle plugin and dependency management, the relevant configuration in `build.gradle` (Groovy DSL) might look like:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **addition snippet** for a project that already has appropriate plugins/versions, not a standalone complete build file. In standard Spring Boot setups, the test starter provides JUnit Jupiter and Mockito; `MockitoExtension` requires `mockito-junit-jupiter` on the test classpath. If the project manages test dependencies manually, ensure these artifacts/versions are compatible.

Run from a project with the Gradle wrapper:

```bash
./gradlew test --tests example.testing.orders.OrderServiceTest
./gradlew test --tests example.testing.orders.OrderServiceFakeTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.orders.OrderServiceTest"
.\gradlew.bat test --tests "example.testing.orders.OrderServiceFakeTest"
```

**Expected outcome:** five Mockito tests and one fake test all pass when the files and dependencies are set up properly. Gradle/JUnit console output depends on the test runner and logging, so there is no single fixed stdout string. The test report will show the case counts and results. In multi-subproject builds, target the test task/subproject containing the source.

### 4.5. Running production code standalone with javac/java

To see clearly that the logic needs neither Spring nor Mockito, create `src/main/java/example/testing/orders/OrderServiceDemo.java`:

```java
package example.testing.orders;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public class OrderServiceDemo {
    public static void main(String[] args) {
        List<Order> saved = new ArrayList<>();

        StockGateway stock = (sku, quantity) ->
                quantity <= 5;
        OrderStore store = order -> {
            saved.add(order);
        };
        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-01-15T08:00:00Z"),
                ZoneOffset.UTC);

        OrderService service =
                new OrderService(stock, store, fixedClock);
        Order order = service.place("BOOK-7", 2);

        System.out.println(order.sku());
        System.out.println(order.quantity());
        System.out.println(order.createdAt());
        System.out.println(saved.size());
    }
}
```

From the project root directory, using JDK 17+:

```bash
javac -d out src/main/java/example/testing/orders/OrderService.java src/main/java/example/testing/orders/OrderServiceDemo.java
java -cp out example.testing.orders.OrderServiceDemo
```

Exact stdout:

```text
BOOK-7
2
2026-01-15T08:00:00Z
1
```

The command above runs a `main` demonstration program with an in-memory fake; **it is not a JUnit test run**. Exception branches and interaction verifications must be run in a test runner as shown in section 4.4.

## 5. Who Instantiates Objects in a Unit Test?

Actual execution flow of `OrderServiceTest`:

```text
JUnit Jupiter
    |
    +-- MockitoExtension creates @Mock StockGateway and OrderStore
    |
    +-- @BeforeEach:
    |     fixedClock = Clock.fixed(...)
    |     sut = new OrderService(stock, store, fixedClock)
    |
    +-- @Test:
    |     when needed, when(stock.available(...)).thenReturn(...)
    |     call sut.place(...) on the REAL service
    |     assertEquals / assertThrows / verify(...)
    |
    \-- JUnit records the result of each case
```

In this flow, **there are no** steps where Spring scans components, creates beans, applies auto-configuration, reads a datasource, opens a web server, or creates transaction proxies.

Three tool layers that are often confused:

- **JUnit Jupiter:** runs tests, manages `@BeforeEach`, `@Test` lifecycle, and assertions.
- **Mockito:** creates mocks and provides the `when(...)/verify(...)` API; `MockitoExtension` integrates Mockito with JUnit.
- **Spring Test/Boot:** participates only when the test actually creates a Spring context or uses the corresponding configuration/test infrastructure. Having `spring-boot-starter-test` on the test classpath **does not automatically create an ApplicationContext**.

In Mockito tests, `@Mock` can be replaced by direct creation:

```java
StockGateway stock = Mockito.mock(StockGateway.class);
OrderStore store = Mockito.mock(OrderStore.class);

OrderService sut = new OrderService(
        stock,
        store,
        Clock.fixed(
                Instant.parse("2026-01-15T08:00:00Z"),
                ZoneOffset.UTC));
```

This is a **snippet inside a test method**, requiring imports for `org.mockito.Mockito` and the time types. It creates mocks via a Java method call; `MockitoExtension` is not needed merely to instantiate them. For larger test suites, the extension and `@BeforeEach` keep code tidy, but they are not a prerequisite for Spring-free unit tests.

### Should you use @InjectMocks?

`@InjectMocks` is **Mockito's** mechanism that attempts to inject mocks into an object via constructor/setter/fields, without starting Spring. It can be convenient, but for practicing constructor injection, writing explicitly:

```java
sut = new OrderService(stock, store, fixedClock);
```

is easier to review. If the constructor gains a new dependency, the compiler points out every instantiation site that needs updating. Automatic injection can obscure constructor requirements and requires care regarding unprovided dependencies. Do not use `@InjectMocks` as an excuse to avoid explicit dependency design.

## 6. Designing Valuable Tests: Output, Exceptions, Interactions

A good service unit test should check **observable behavior**, not merely whether a method finishes without crashing.

**Outputs:** the returned order has the expected data; `assertEquals(new Order("BOOK-7", 2, NOW), actual)` protects the record's attributes. For mutable objects/entities, check contract fields rather than relying on arbitrary object identity.

**Exceptions:** `assertThrows(OutOfStockException.class, ...)` confirms the error branch; `assertEquals(...)` on the message should be used only when the message is a meaningful contract. `assertThrows` accepts subtypes; if the exact exception class is required, JUnit Jupiter also provides `assertThrowsExactly(...)`.

**Side effects:** `verify(store).save(expected)` proves the service sends the right save command once. `verifyNoInteractions(store)` proves no calls at all are made to the collaborator on error paths. For collaborators with multiple methods, checking `never().save(...)` has a narrower scope than “no interactions whatsoever”; choose based on the actual contract.

**Ordering:** do not lock down the call order of every helper unless ordering is a business requirement. In this example, “validate before querying stock” is meaningful because invalid input must not touch I/O. Asserting `verifyNoInteractions(stock, store)` protects that ordering.

**Dependency failure outcomes:** when stock throws, `inventoryFailure_isPropagatedWithoutSaving` proves the store is not called. If requirements demand 3 retries or mapping to another error, add specific test cases and design accordingly rather than extrapolating from the current test.

**Determinism:** clocks/UUIDs/randomness/network must be controlled if they affect results. Inject `Clock` as in the example; ID sources can be injected via `Supplier<UUID>` or an ID generator interface when needed; avoid turning every simple constant into an interface.

### Choosing sensible fixtures and stubbing

In `@BeforeEach`, construct only the SUT and **shared** dependencies. Avoid putting every `when(...)` in setup if many tests do not use them. Mockito can report **unnecessary stubbing** in strict mode, and global stubs obscure each test's real Given conditions.

Instead:

```java
@Test
void outOfStock_throwsAndDoesNotSave() {
    when(stock.available("BOOK-7", 2)).thenReturn(false);
    // Call SUT and assert expected behavior ...
}
```

This snippet illustrates stub placement inside a test; the complete test in section 4.2 has full assertions. Placing stubs close to the case prevents logic changes from accidentally passing due to overly broad setup. Use matchers like `anyString()` only when the value truly does not matter, whereas for business-meaningful SKUs/quantities, use concrete arguments.

## 7. Behaviors Only Spring or Real Infrastructure Can Prove

An object instantiated via `new` **does not automatically pass through a Spring AOP proxy**. A service unit test can be green while runtime configuration fails due to transaction, bean wiring, security, or repository bugs. Complementary tests should match the exact claim being made:

| Claim to prove | Can a plain constructor test prove it? | Where to verify |
| --- | --- | --- |
| Validation rules, stock/out-of-stock, return values | Yes | JUnit/Mockito/fake |
| No save command sent when data is invalid | Yes, at the service boundary | JUnit + verify/fake |
| Real DB wrote rows, SQL and constraints are valid | No | Repository/DB integration test |
| `@Transactional` commit/rollback | No | Context with appropriate transaction manager and DB |
| `@Cacheable` produces cache hit/miss | No | Test with real caching proxy/config |
| Method security `@PreAuthorize` | No | Appropriate Spring Security test |
| `@Value`, `@ConfigurationProperties`, and bean wiring | No | Context/configuration test |
| HTTP binding, JSON, validation, and status | No | `@WebMvcTest`/`MockMvc` or integration test |
| HTTP client serialization, real retry, timeout | No | Client adapter/contract test |
| Multi-component end-to-end flow working together | No | `@SpringBootTest`/appropriate integration test |

**Example with `@Transactional`:** if you annotate a service method and then call an object created with `new`, the transaction interceptor does not run, so the test proves nothing about rollback. At Spring runtime, proxy-based transactions also depend on calls going **through the proxy**; self-invocation via `this.method()` typically bypasses the interceptor. If using final classes/methods with subclass-based proxies, specific proxy limitations also apply. Therefore, business tests cannot replace transaction tests.

**HTTP example:** calling `service.place(...)` does not prove that `POST /orders` returns 201/400/409 or that Spring deserializes incoming JSON into the DTO properly. If that contract needs protection, use an MVC slice or integration test sending requests through real infrastructure.

**Database example:** `verify(store).save(order)` only proves a command was emitted through the port. An in-memory fake does not test unique indexes, transaction isolation, migrations, locking, or queries. If the ordering process requires stock consistency under concurrency, appropriate infrastructure design/testing is needed.

A single feature can have **multiple layers of evidence**: thorough unit tests for business logic; adapter/repository tests for I/O; and a handful of integration tests for critical wiring/transaction/HTTP paths. Cost and risk determine the count, not a fixed ratio.

## 8. Using Constructor Injection in Production Spring Boot

A plain Java service can be managed by Spring without altering its logic. One way to register it is `@Configuration` with `@Bean`:

```java
@Configuration
class OrderConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    OrderService orderService(
            StockGateway stock,
            OrderStore store,
            Clock clock) {
        return new OrderService(stock, store, clock);
    }
}
```

This is an **illustrative snippet inside a Spring project**, requiring imports for `org.springframework.context.annotation.Configuration`, `Bean`, and `java.time.Clock`; real adapters must be registered for the two ports, and the package/config must be scanned or imported appropriately by Spring. It is **not a standalone Java file** for compiling with plain JDK. With package-private interfaces as in the example, the config must be in the same package or the interfaces promoted to an API with appropriate visibility.

Another option is annotating `OrderService` with `@Service` and providing a single matching constructor so Spring autowires the dependencies. Do not declare two service beans for the same purpose unintentionally. If AOP annotations like `@Transactional` are added, verify proxy/runtime behavior with integration tests rather than inferring it from constructor-based unit tests.

In unit tests, whether production uses `@Bean` or `@Service`, the setup line remains:

```java
OrderService sut =
        new OrderService(stockDouble, storeDouble, fixedClock);
```

This decoupling is intentional: **business logic can run and be verified in plain Java**; Spring is responsible for creating and wiring production components.

## 9. Test Boundaries Can Span More Than One Class

A “unit” does not have to be **one method** or **one bean**. If a service calls a `PriceCalculator` that is a pure, fast, I/O-free, deterministic class, you can keep the real calculator to test ordering alongside pricing behavior. Conversely, when a service invokes SQL or a remote API, you should typically separate that boundary behind a port and mock/fake it, because tests need deterministic execution and forced failure paths.

When a constructor accumulates too many dependencies, that may signal the class carries too many responsibilities. Re-examine the business logic and dependency direction rather than inventing dozens of interfaces just to reduce mock counts. The principle remains: **the logic being proven must run for real; the external environment is replaced only when doing so lets you control the exact test conditions**.

In legacy code using static singletons, hidden HTTP calls inside methods, or reading `System.currentTimeMillis()`, refactoring may be needed to extract side effects into explicit dependencies. Do so alongside tests protecting existing behavior and tests for new requirements; avoid changing rules, transactions, and I/O simultaneously without regression coverage.

## 10. Common Pitfalls

**1. Mocking the service itself.** Stubbing `when(sut.place(...)).thenReturn(...)` skips business code. Instantiate the real service and mock collaborators outside the boundary.

**2. Enabling `@SpringBootTest` for every tiny check.** `ApplicationContext` adds startup cost and unrelated failure reasons. Use plain JUnit when Spring features are unnecessary; add context tests for what genuinely needs them.

**3. Having `@Mock` without MockitoExtension or manual initialization.** Uninitialized mock fields pass null to the constructor. Use `@ExtendWith(MockitoExtension.class)` or `Mockito.mock(...)`.

**4. Using `@InjectMocks` to hide the constructor.** Calling the constructor explicitly reveals missing/extra dependencies and makes signature changes easy to update.

**5. Field injection forces reflection in tests.** Without a Spring context, `@Autowired` fields remain unassigned. Constructor injection simplifies both runtime design and unit testing.

**6. Mocking value objects and pure policies.** Mocking what you are trying to prove turns the test into a stub check; keep deterministic logic real inside an appropriate boundary.

**7. Stubbing every collaborator in `@BeforeEach`.** Unused stubs clutter tests and trigger strict-stubbing errors. Declare only the Given setup each case needs.

**8. Locking tests to every internal call.** Assertions on save/no-save commands are valuable; assertions on private helpers or non-business ordering break easily during refactoring.

**9. Using a mock repository and claiming the DB committed.** That overstates unit test evidence. Use repository/transaction integration tests when SQL/DB behavior is what needs protection.

**10. Not controlling time, randomness, or shared state.** Inject `Clock`, ID sources, or isolated fakes; tests must repeat deterministically regardless of when they run.

**11. Writing only happy paths.** If invalid input still hits the DB before throwing, success-only tests miss the bug. Add boundary cases and no-side-effect checks.

**12. Fakes are not identical to real DBs.** In-memory fakes omit transactions, constraints, and concurrency. Use fakes to verify service decisions; use real infrastructure to prove adapter properties.

## 11. Practical Checklist

Before writing tests:

- Have you identified the service behavior to prove, its inputs, and its observable outcomes?
- Does the service have a constructor listing all required dependencies?
- Which parts should run for real, and which need stubs/mocks/fakes to control data and side effects?
- Have clock, IDs, randomness, or external I/O across the boundary been controlled where needed?

Inside the test:

- **Given:** construct the real SUT via `new` and prepare exact collaborator conditions for the case.
- **When:** call a public behavior without using reflection to invoke private methods.
- **Then:** assert outputs/exceptions and business-meaningful interactions.
- Are there success, failure, boundary-input, and no-side-effect-on-error cases?
- Do the tests run under JUnit without accidentally requiring a Spring context/DB/network?

After the tests pass:

- During refactoring, do the assertions still protect behavior rather than implementation details?
- Is the claim “the service requested a save” clearly distinguished from “the DB actually saved”?
- Are there proxy/transaction/security/HTTP/DB behaviors needing separate integration tests?

**Remember:** constructor injection lets a Java service be instantiated **completely and explicitly** outside Spring. When testing business logic, instantiate the **real service**, pass controllable collaborators, and verify outputs/exceptions/side effects at the right boundary. A Spring context is needed only when **Spring's own behavior or infrastructure wiring** is what you need to prove.