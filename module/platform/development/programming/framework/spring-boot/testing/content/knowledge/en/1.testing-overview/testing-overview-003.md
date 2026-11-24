# System Under Test and Dependency Boundaries

In Spring Boot, writing a useful test requires answering two questions first: **which behavior is the responsibility of the object under test?** and **where is execution handed off to another component?** The answers determine the *System Under Test* (SUT), dependency boundaries, the appropriate test type, and what must be observed to conclude pass or fail.

## 1. Understanding the “Unit” Under Test

The **unit under test** is the slice of behavior a test aims to prove. It can be a pure function, a class, a service, or a small group of objects collaborating to fulfill a single responsibility. “Unit” does not automatically mean “one method” or “one bean”. Choose boundaries so that the behavior to prove is clear, input conditions are controllable, and outcomes are verifiable.

Example in an order placement flow:

1. `OrderController` receives the HTTP request and passes data to the application.
2. `OrderService` determines valid quantity, checks stock, and requests saving the order.
3. `StockGateway` queries the inventory information source.
4. `OrderRepository` writes the order to the database.

If the goal is **“when stock is insufficient, do not save the order”**, the appropriate SUT is `OrderService`. Observable outcomes include the returned exception/semantics and *not calling* save. Neither a database, HTTP server, nor inventory system needs to run in this unit test.

If the goal changes to **“HTTP returns 400 when JSON is missing a required field”**, the SUT shifts to the Spring MVC boundary, where `@RequestBody`, `@Valid`, exception handlers, and web configuration participate. Calling a controller method directly is not enough in that case; use a web slice or integration test instead.

If the goal is **“the repository maps the entity and queries the right data”**, real JPA/JDBC with a test database is needed. Mocking the repository would eliminate the very behavior you want to test.

Distinguish three concepts:

- **SUT:** the component/behavior being verified.
- **Collaborator:** what the SUT calls to get its job done, such as a persistence port, HTTP client, `Clock`, or pricing calculator.
- **Boundary:** the point where the test decides to use a real component, substitute a test double, or move to another test level.

## 2. Draw Boundaries from Behavior, Not Class Diagrams

For each scenario, write a sentence following the pattern: **“When [condition], the SUT must [observable outcome], regardless of [details outside its responsibility].”** Then list every outbound call leaving the SUT.

| Component | What Needs Checking | Reasonable Boundary |
| --- | --- | --- |
| Pure fee/pricing calculation function | Result for specific inputs | Use real logic; no Spring context needed |
| Business service | Decision branches, result, expected effects on ports | Instantiate real service; replace external I/O with stub/mock/fake |
| Controller and HTTP binding | Status, JSON, validation, route, exception mapping | `@WebMvcTest` + `MockMvc`, configure required beans properly |
| JPA repository | Query, mapping, constraints, transactions with persistence | `@DataJpaTest` and suitable test database |
| Flows across multiple beans, security filters, transactions, or messaging | Integrated components operating together | `@SpringBootTest` or integration test with appropriate real infrastructure |

This is a choice **based on the test question**, not a ranking of which test is “better”. A service may need both unit tests for business rules and integration tests for transactions/SQL.

A good boundary has four traits:

- **Controllable inputs:** able to force out-of-stock branches, network errors, timeouts, and invalid data.
- **Observable behavior:** verifies values, exceptions, state, or commands sent to ports; does not depend on internal local variables.
- **Independent of external environments when unnecessary:** unit tests do not accidentally hit the network, DB, broker, or real system clock.
- **Real enough to prove the requirement:** does not mock away the very logic the test intends to verify.

## 3. Classifying Dependencies: Keep Real or Replace?

Not every dependency should be mocked. Decide based on **its role in the behavior under test**:

| Dependency | How to Handle in Unit Tests | When to Test with the Real Version? |
| --- | --- | --- |
| Value objects, `record`s, pure functions, deterministic calculators | Keep real to test both logic and related data | Often testable independently |
| Repository/DAO executing SQL or JPA | Use a port interface and mock/fake so the SUT reacts to specific outcomes | Separately test queries, mapping, constraints, and transactions |
| HTTP client calling an external service | Stub success results, business errors, timeouts via port/client | Test HTTP serialization, authentication, retry, and contract at the HTTP boundary |
| Clock, random, UUID | Inject `Clock`/controllable value generator | Verify real wiring/configuration when needed |
| Queue, file, cache, email | Mock/fake at the outbound side-effect port | Integration test when proving format, delivery, TTL, or durability |
| Spring proxies, `@Transactional`, `@Cacheable`, method security | Unit test internal method logic | Test with a Spring context to verify interceptors/AOP actually run |

For example: for the rule “a valid order is saved”, mocking `OrderStore` shows the service *requested* saving the right data. It **does not prove** the database committed, unique constraints were enforced, or the record survives a restart. Those claims require an integration test.

### What Types of Test Doubles Exist?

- **Stub:** returns canned data/exceptions to steer the SUT into the branch under test, such as stock = `false`.
- **Fake:** a lightweight working implementation, such as a `Map`-backed repository; useful when multiple operations require state without verifying exact real DB behavior.
- **Mock:** a collaborator that enables verifying calls, arguments, call counts, or non-invocation.
- **Spy:** wraps a real object and can override part of its behavior; use cautiously because side effects of real methods can still occur.

Mockito supports creating mocks as well as stubbing/verification; having “mock” in the library name does not make every usage a verification. Use `when(...).thenReturn(...)` primarily to control input data; use `verify(...)` when the call itself is part of the requirement. Avoid counting every internal call, because tests will break on refactoring even when external behavior does not change.

## 4. Designing Clear Boundaries in Spring Boot

Constructor injection makes dependencies directly visible, easy to swap, and avoids creating a Spring context for unit tests:

```text
JUnit/Mockito
    |
    v
OrderService (real SUT)
    |-- StockGateway (mock: decides stock response)
    \-- OrderStore   (mock: observes save command)
```

`StockGateway` and `OrderStore` are **outbound ports**: interfaces describing what the service needs from the outside world. In the real application, adapters may connect to a REST API, Kafka, Redis, or Spring Data; in unit tests, we supply test doubles. This is a technique for creating clear boundaries; it does not mean every class needs an added interface.

**Scenario:** When the quantity is valid and in stock, the service creates the order and requests saving it. When out of stock, the service throws an error and strictly does not save. When the quantity is invalid, the service rejects immediately without calling any dependency port.

Create file `src/main/java/demo/order/OrderService.java` (Java 17 or higher):

```java
package demo.order;

import java.util.Objects;

public class OrderService {
    private final StockGateway stock;
    private final OrderStore orders;

    public OrderService(StockGateway stock, OrderStore orders) {
        this.stock = Objects.requireNonNull(stock);
        this.orders = Objects.requireNonNull(orders);
    }

    public Order place(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Invalid SKU");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (!stock.isAvailable(sku, quantity)) {
            throw new OutOfStockException(sku);
        }

        Order order = new Order(sku, quantity);
        orders.save(order);
        return order;
    }
}

interface StockGateway {
    boolean isAvailable(String sku, int quantity);
}

interface OrderStore {
    void save(Order order);
}

record Order(String sku, int quantity) {}

class OutOfStockException extends RuntimeException {
    OutOfStockException(String sku) {
        super("Out of stock: " + sku);
    }
}
```

Putting the interfaces and `record` package-private in the same file keeps the example concise while still compiling as valid Java. When building larger modules, split them into appropriate files/packages. This code is **business logic independent of Spring annotations**; a real Spring Boot project can declare `OrderService` as a bean via `@Service` or `@Bean` in configuration. The unit tests below create the instance via constructor.

Create file `src/test/java/demo/order/OrderServiceTest.java`:

```java
package demo.order;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {
    @Mock StockGateway stock;
    @Mock OrderStore orders;

    private OrderService sut;

    @BeforeEach
    void setUp() {
        sut = new OrderService(stock, orders);
    }

    @Test
    void conHang_taoVaYeuCauLuuDungDon() {
        when(stock.isAvailable("BOOK-1", 2)).thenReturn(true);

        Order actual = sut.place("BOOK-1", 2);

        assertEquals(new Order("BOOK-1", 2), actual);
        ArgumentCaptor<Order> saved = ArgumentCaptor.forClass(Order.class);
        verify(orders).save(saved.capture());
        assertEquals(actual, saved.getValue());
    }

    @Test
    void hetHang_baoLoiVaKhongLuu() {
        when(stock.isAvailable("BOOK-1", 2)).thenReturn(false);

        OutOfStockException error = assertThrows(
                OutOfStockException.class,
                () -> sut.place("BOOK-1", 2));

        assertEquals("Out of stock: BOOK-1", error.getMessage());
        verifyNoInteractions(orders);
    }

    @Test
    void soLuongKhongHopLe_khongChamPhuThuoc() {
        assertThrows(IllegalArgumentException.class,
                () -> sut.place("BOOK-1", 0));

        verifyNoInteractions(stock, orders);
    }
}
```

In a Gradle Spring Boot project with dependency version management configured, these tests use JUnit Jupiter and Mockito from `spring-boot-starter-test`. If dependencies/JUnit Platform runner configuration are not present yet, the required portion in `build.gradle` (Groovy DSL) looks like:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Run from the appropriate Gradle project directory:

```bash
./gradlew test --tests demo.order.OrderServiceTest
```

On Windows, you can use `.\gradlew.bat test --tests demo.order.OrderServiceTest`. If the test task belongs to a subproject, select the right task/subproject when running. **Expected:** all three tests pass if the project has the corresponding build configuration and dependencies; there is no fixed stdout because JUnit/Gradle displays output according to the run configuration.

Meaning of each test:

1. **In stock:** stubs the response from the inventory system, then verifies the returned order and that the *save command* carries the right data. `ArgumentCaptor` observes the outbound command, not a real database.
2. **Out of stock:** observes the exception and ensures the repository is untouched, so inventory failures never create invalid orders.
3. **Invalid input:** verifies check ordering: the service rejects before querying stock or persistence.

There is no `@SpringBootTest`, `@Autowired`, server, datasource, or network connection in these tests. That is the intent of the unit test boundary. If `StockGateway`'s implementation changes from REST to gRPC, these three tests still reflect the same business contract.

## 5. Where Do Test Boundaries Lie in Spring Boot?

### 5.1. Controller: Direct Method Calls Are Not Enough to Test HTTP

Calling `new OrderController(service).create(dto)` only tests a Java method. That approach does not fully exercise JSON parsing, route selection, binding, `@Valid`, exception mapping, or Spring MVC's filter chain. For HTTP requirements, choose `@WebMvcTest(YourController.class)` with `MockMvc` and declare/mock the collaborators needed by the context. Tests send requests through the MVC infrastructure and assert actual status, response body, headers, and validation. Security/filter configuration should be included in scope according to the testing goal.

### 5.2. Service: Plain Method Calls Differ from Real Spring Proxies

A unit test instantiating a service with `new` can verify business conditions well, but **does not run Spring interceptors**. For instance, calling a `@Transactional`-annotated method directly does not prove commit/rollback, propagation, or transaction boundaries; `@Cacheable` does not prove caching; testing method security also requires the real security mechanism. Add tests with a Spring context and real adapters when framework features are what need proving.

### 5.3. Repository: Mocks Do Not Prove SQL/JPA

Mocking `JpaRepository` is suitable for forcing a service to receive `Optional.empty()` or a specific entity. It does not execute generated queries, entity mapping, lazy loading, constraints, or migrations. Use `@DataJpaTest` for the persistence slice. If queries depend on PostgreSQL/MySQL features, an in-memory database with a different dialect is not reliable proof; use the matching test database type (e.g., via Testcontainers when appropriate).

### 5.4. Outbound Communication: Separate Decisions from Protocols

Service unit tests should simulate outcomes at the port level: “payment succeeded / failed”. Meanwhile, the HTTP client adapter needs tests for request URL, method, headers, payload, and status/error mapping using a mock server or integration environment. For messaging, verify in the service that the right event is requested to be published; use integration tests to prove serialization, broker delivery, retries, or consumer behavior.

## 6. Choosing Boundaries via a Scenario Table

| Question to Prove | Recommended SUT and Test | What Is *Not* Proven Yet |
| --- | --- | --- |
| Empty cart creates no order | Real service + mock store | Transaction/DB schema |
| Discount based on membership rules | Real pricing calculator + test data | HTTP/API wiring |
| `POST /orders` missing field returns HTTP 400 | Spring MVC slice + real request via `MockMvc` | DB commit |
| `@Transactional` rolls back on error after insert | Spring context + database test | Remote service behavior if faked |
| JPA query finds orders by status | Repository slice + DB test | Full HTTP/security pipeline |
| Payment client timeout is mapped properly | Client adapter + simulated HTTP timeout | Real external service availability |
| Insufficient role blocked before business logic | Security/MVC integration test | Real identity provider if stubbed |

**Verification principle:** place assertions right at the boundary under test. Do not treat `verify(repository).save(...)` as proof of “saved to DB”, and do not treat calling a controller method directly as proof of “endpoint returns HTTP 201”.

## 7. Designing Maintainable Tests

A sharp test typically has three phases:

1. **Given:** construct the real SUT and prepare inputs; stub only the responses needed for the scenario.
2. **When:** invoke one public behavior at the boundary under test.
3. **Then:** assert return values/state or exceptions; `verify` business-meaningful interactions (e.g., never sending a charge command twice).

Choose meaningful data: quantity `0` to test validation, stock `false` to test out-of-stock, timeout errors distinct from business errors. Each case should clearly express its condition rather than merely changing the test name.

Prefer asserting outcomes and contracts with collaborators rather than checking how code is split into helper methods. `verifyNoMoreInteractions(...)` should only be used when **no further action occurring** is a real requirement; rigid overuse makes tests fragile when logging or metrics are added later.

For time, replace `Instant.now()` with an injected `Clock` and `Clock.fixed(...)` in tests to check points right around expiration dates. For UUID/random values, inject a generator or fix the inputs. For asynchronous processing, synchronize on an observable outcome/event rather than arbitrary `Thread.sleep(...)`.

Needing many dependencies to construct an SUT may signal that the service carries too many responsibilities. However, **do not split classes solely to make tests look nicer**; re-evaluate business boundaries and each collaborator's role before refactoring.

## 8. Common Mistakes and How to Fix Them

**Mistake 1 — Mocking the object under test itself.** If `sut` is a mock, `when(sut.someMethod()).thenReturn(...)` only confirms Mockito works without running the target logic. Create a real SUT; replace only collaborators outside the boundary.

**Mistake 2 — Mocking everything, including value objects and pure logic.** This hides real bugs and inflates setup code. Keep fast, deterministic components that are part of the behavior under test real.

**Mistake 3 — Booting `@SpringBootTest` for every simple calculation.** The context is slower, pulls in lots of configuration, and makes failure causes harder to isolate. Use plain JUnit when behavior needs no Spring; still use the context when wiring/proxies/transactions are the target.

**Mistake 4 — Test is green, yet the part needing verification was mocked.** For example, mocking a repository and claiming the JPA query works, or mocking an HTTP client and claiming JSON serialization works. Move the SUT to the real adapter/repository and choose the matching test level.

**Mistake 5 — Boundary leaks from hidden side effects.** Inside a service unit test, code still calls `System.currentTimeMillis()`, an HTTP singleton, a static DB utility, or a real repository. Extract side effects into explicit dependencies; verify the test needs no credentials, network, broker, or environment state.

**Mistake 6 — Over-specifying internal interactions.** The test demands calling helper A then B in exact order even though it is not part of the contract; valid refactoring turns the test red. Switch assertions to meaningful outputs and side effects, checking order only when order is a business rule.

**Mistake 7 — Equating fakes with production.** An in-memory fake may omit unique indexes, transaction isolation, network failures, or eventual consistency. Use fakes to test SUT decisions; add integration/contract tests for risky differences.

## 9. Checklist Before Finishing a Test

- Can I state **one specific behavior** that the test must prove?
- Is the SUT a real component, with controlled inputs and observable outputs/side effects?
- Is every dependency kept real or replaced for a valid reason under the chosen boundary?
- If the test only uses mocks, am I accidentally drawing conclusions about DB, HTTP, Spring proxies, or security that it has not verified?
- Have success cases, failure cases, boundary inputs, and **not executing critical side effects** been considered?
- Does the test depend on wall-clock time, network, execution order, shared data, or unnecessary internal details?
- Are there complementary slice/integration tests for framework and adapter contracts that unit tests do not cover?

**Takeaway:** a trustworthy unit test places **the real logic to prove** in the center, **controllable dependencies** at the edges, and **assertions right at the behavioral boundary**. In Spring Boot, choosing to use or omit an application context is a consequence of what needs proving, not the definition of the SUT.