# Mockito: Mock, Stub, Fake, and Spy in Test Design

## 1. Goals and the Problem to Solve

When testing a Spring Boot service, the object under test (system under test, **SUT**) often depends on a repository, HTTP client, payment gateway, email sender, or another bean. We need to choose which components run for real and which are replaced so that tests are **fast, repeatable, and catch the right bugs**.

The terms **mock**, **stub**, **fake**, and **spy** describe different roles of a *test double* (a substitute object in tests). Mockito provides many tools to create or observe these roles, but **an object created with `Mockito.mock()` does not automatically mean “mock” in every test**: if it is only used to return predefined data, it is acting as a *stub*. Conversely, when `verify(...)` is used to verify interactions, it acts as a *mock* in the behavioral-testing sense.

By the end of this lesson, you should be able to:

- Distinguish test doubles from production implementations, and understand dummy, stub, fake, mock, and spy.
- Choose based on the question: “Is the test checking **state/outcome** or **interaction**?”
- Know how to use `mock`, `when(...).thenReturn(...)`, `thenThrow`, `verify`, `@Mock`, `spy`, `@Spy`, and `doReturn(...).when(...)`.
- Write Java 17+ unit tests with JUnit Jupiter and Mockito where the SUT runs for real.
- Understand the limits of fakes, the risk of spies invoking real code, strict stubbing, and when Spring Boot integration tests are needed.
- Avoid tests that merely echo mock configuration or depend too tightly on implementation details.

## 2. What Is a Test Double? Distinguishing Five Concepts

**Test double** is a general term for a component that replaces a collaborator of the SUT. Not every test double is a Mockito mock.

| Type | Primary meaning | Evidence the test usually checks | Example |
| --- | --- | --- | --- |
| **Dummy** | Passed only to satisfy required parameters; the test does not use its behavior | No interactions or values of interest | An auxiliary metadata object never read in the scenario |
| **Stub** | Returns predefined results or throws predefined errors | SUT outcome when receiving inputs from the collaborator | `when(catalog.price("BOOK")).thenReturn(1500L)` |
| **Fake** | Simplified implementation that has real behavior and state | State after operations | A repository backed by a `Map` instead of a database |
| **Mock** | Object used to verify calls, arguments, and invocation counts | Whether the SUT sent the right command | `verify(payment).charge("ORD-1", 3000L)` |
| **Spy** | Wraps a real object, running real methods by default while allowing observation or selective stubbing | Both real behavior and interactions | `spy(new ArrayList<>())`; `verify(spyList).add("A")` |

**A real component** is not a test double: it is the production or actual implementation of the object you want to test. For example, when testing checkout rules, you must instantiate and run the **real `CheckoutService`**; mocking the service itself will not prove the checkout logic.

### Distinguishing Stub and Mock by What the Test Asserts

Suppose the collaborator is `ExchangeRateProvider`:

~~~java
when(rateProvider.rate("USD", "VND")).thenReturn(25_000L);
~~~

When the test invokes the SUT and calls `assertEquals(...)` on the converted total, the rate provider is acting as a **stub**: it provides controlled input. If the test also adds:

~~~java
verify(rateProvider).rate("USD", "VND");
~~~

then the test also checks the **interaction** of the SUT with the provider. The same Mockito object can both return data (stub) and have its calls verified (mock). The snippet above illustrates the API; `rateProvider` and the `rate(...)` contract are provided by the application.

The word “mock” in documentation or everyday conversation is often used loosely for any `Mockito.mock()` object; when designing tests, state clearly whether you are **stubbing data or verifying calls** to avoid losing sight of the goal.

### A Fake Is Not Just a Stub with More Data

A stub usually returns pre-programmed results. A fake implements a minimal rule set **with state**: for example, `save(order)` makes `findById(id)` return the saved order, or `delete(id)` makes the item disappear.

Fakes are convenient for testing sequences of business operations, but **a fake does not become PostgreSQL** just because it implements the `OrderRepository` interface. It does not inherently simulate unique indexes, foreign keys, SQL transactions, locking, rollback, or query dialects. Those characteristics must be verified with a real adapter/database when needed.

## 3. Deciding Based on Behavior and Risk

Before reaching for Mockito, write one sentence defining **the bug you want the test to catch**:

- “If inventory is insufficient, the system must not charge” → real service, fake inventory to set up state, mock payment port for `verifyNoInteractions`.
- “Total after discount must be 3,000 cents” → real formula, stub price list/discount as fixed data, assert return value.
- “When payment succeeds, the order must be saved” → real service, small fake repository to assert state. If the goal is to check SQL/schema, a real repository and DB are needed.
- “Only one confirmation email is requested to be sent” → mock mail port, `verify(..., times(1))` with recipient and key content.
- “A real formatter must be called while keeping original formatting” → a spy can be used, though asserting output is preferable if call verification is unnecessary.
- “Real `@Transactional` rollback and unique constraint work” → Spring-managed bean + real database in an integration test; mocks/fakes are not enough.

Rules of thumb:

1. **Keep the real implementation where the logic under test lives.** That is the SUT.
2. If you only need a fixed value or error from a collaborator, **stub**.
3. If you need state across multiple operations without caring about external system traits, **fake**.
4. If **an outgoing call is part of the contract**, **mock** and verify meaningful interactions.
5. If you need to observe a real object without replacing the whole implementation, you may **spy**, while guarding against real-execution risks.
6. If the potential bug lies in SQL, migrations, serialization, HTTP wire protocol, Redis TTL, or Kafka acknowledgement, **write an integration test with the appropriate real adapter/service or test server**.

Prefer assertions on **public outputs and state**, because tests that verify too many internal calls break during refactoring even when behavior remains correct. Verification is essential when the interaction itself is a business requirement.

## 4. Designing Seams: Replace at the Boundary, Keep the Important Parts Real

Suppose a checkout service has four collaborators:

~~~text
                +-----------------------+
  checkout() -->| REAL CheckoutService  |
                +-----------------------+
                    |    |      |     |
                    v    v      v     v
                Catalog Payment Store  Audit
                 stub    mock   fake    spy
~~~

- `Catalog` returns controlled prices so the test focuses on total calculation.
- `PaymentGateway` must be called with the right amount and order ID, so the test uses a mock.
- `OrderStore` uses a `Map`-backed fake to observe saved orders without starting a database.
- `AuditTrail` uses a spy for real internal event recording while adding the ability to verify in certain scenarios.

In production, these four interfaces might be implemented by an HTTP client, JDBC repository, logging service, etc. Unit tests **do not need to know** URLs, connection pools, networks, or bean wiring when the goal is `CheckoutService` business logic.

**Boundary ports/interfaces are useful, but do not create an interface for every class.** Value objects, records, simple entities, and pure functions should usually run for real. Creating a mock class for a `String`, DTO, or pure data-holding object makes tests more complex for little value.

One collaborator can play different roles in different tests: `OrderStore` is a fake in `CheckoutServiceTest`, while the actual `JdbcOrderStore` adapter must run for real in `JdbcOrderStoreIT` with PostgreSQL/Testcontainers. There is no contradiction: the two tests prove two different kinds of behavior.

## 5. Core Mockito APIs

### 5.1 Creating Doubles with mock() or @Mock

To create a test double directly:

~~~java
Catalog catalog = Mockito.mock(Catalog.class);
~~~

Or using the JUnit Jupiter extension:

~~~java
@ExtendWith(MockitoExtension.class)
class PriceServiceTest {
    @Mock
    Catalog catalog;

    // ... @Test methods
}
~~~

This is an **illustrative snippet in a project that has a `Catalog` interface**, not a standalone test file. `MockitoExtension` initializes and manages Mockito annotations before tests run, and helps detect unused stubbing under the corresponding strictness configuration.

Common imports:

~~~java
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
~~~

Do not confuse `@Mock` (Mockito creating a mock in a unit test) with Spring test context bean-override annotations. A plain `@Mock` **does not automatically override a bean in `ApplicationContext`**.

### 5.2 Stubbing Values or Errors: when/thenReturn, thenThrow

~~~java
when(catalog.unitPriceCents("BOOK")).thenReturn(1_500L);
when(catalog.unitPriceCents("UNKNOWN"))
        .thenThrow(new IllegalArgumentException("Unknown SKU"));
~~~

Stubbing should only describe inputs truly relevant to the scenario. If unstubbed, Mockito typically returns **default values** (such as `0` for integer types, `false` for boolean, `null` for many reference types; there are exceptions for certain special types). Do not mistake default values for production behavior.

For `void` methods, you cannot write `when(...).thenReturn(...)` as with return values. Use `doThrow(...)`:

~~~java
doThrow(new IllegalStateException("Gateway offline"))
        .when(messageSender).send("hello");
~~~

In this example, `messageSender` and `send(String)` are illustrative components. To **do nothing** when a void method is called, a Mockito mock already skips executing any real implementation by default; `doNothing()` should only be used to clarify a scenario or when handling a spy.

### 5.3 Verifying Business-Meaningful Interactions

~~~java
verify(paymentGateway).charge("ORD-1", 3_000L);
verify(paymentGateway, times(2)).charge("ORD-2", 1_500L);
verify(paymentGateway, never()).charge(anyString(), anyLong());
verifyNoInteractions(emailSender);
~~~

The calls above illustrate the API; assume `paymentGateway.charge(String,long)` and `emailSender` are declared in the test. `verify(mock).method(...)` defaults to checking **once**. `never()` requires **no matching calls**; `verifyNoInteractions(...)` checks that the mock was not interacted with at all.

**Do not verify every getter, setter, and internal sequence.** If the final outcome already expresses the contract clearly, `assertEquals`/`assertTrue` is enough. `verify` should only check meaningful interactions: charging once, not sending an email on failure, publishing the right event, calling an API with the right key.

### 5.4 Argument Matchers and Captors

Mockito provides `anyString()`, `anyLong()`, `eq(value)`, and many other matchers. If a call uses a matcher for **one parameter**, the remaining parameters must also use an appropriate matcher (for example `eq("ORD-1")`; do not mix matchers with raw literals in the same call).

~~~java
verify(paymentGateway).charge(eq("ORD-1"), anyLong());
~~~

When a complex argument needs field-by-field checks, use `ArgumentCaptor<T>` to capture the passed argument and assert on it. For simple data like `3_000L`, verifying with an exact argument is usually shorter and clearer.

## 6. Self-Contained Java 17+ Example: stub + fake + mock + spy in One Test

This example uses a **real `CheckoutService`** with small interfaces. The test only depends on JUnit Jupiter and Mockito, requiring no Spring `ApplicationContext` or database. Spring Boot projects using `spring-boot-starter-test` typically already provide both libraries and the Mockito Jupiter extension.

Place the file **`src/test/java/example/CheckoutServiceTest.java`** as follows:

~~~java
package example;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
@DisplayName("CheckoutService: choosing test doubles by responsibility")
class CheckoutServiceTest {

    @Mock
    Catalog catalog;                   // Stubs price data.

    @Mock
    PaymentGateway payment;            // Mocks payment interaction.

    @Spy
    RecordingAudit audit = new RecordingAudit(); // Runs real audit logic.

    FakeOrderStore store;               // Fake storage backed by Map.
    CheckoutService service;            // Real SUT.

    @BeforeEach
    void setUp() {
        store = new FakeOrderStore();
        service = new CheckoutService(catalog, payment, store, audit);
    }

    @Test
    @DisplayName("Charges the right amount and saves the order when valid")
    void createsOrderWhenPaymentSucceeds() {
        // Arrange: stub inputs and gateway response.
        when(catalog.unitPriceCents("BOOK")).thenReturn(1_500L);
        when(payment.charge("ORD-1", 3_000L)).thenReturn("PAY-9");

        // Act: run the real SUT.
        Order result = service.checkout("ORD-1", "BOOK", 2);

        // Assert state/output: fake state is updated.
        assertAll(
                () -> assertEquals("ORD-1", result.id()),
                () -> assertEquals(3_000L, result.totalCents()),
                () -> assertEquals("PAY-9", result.paymentId()),
                () -> assertEquals(result, store.find("ORD-1")),
                () -> assertEquals(1, store.size()));

        // Assert interaction: charge command must be issued properly.
        verify(payment).charge("ORD-1", 3_000L);

        // Spy still runs the real implementation and records the event.
        verify(audit).record("created:ORD-1");
        assertEquals(List.of("created:ORD-1"), audit.events());
    }

    @Test
    @DisplayName("Duplicate order ID is rejected before looking up price or charging")
    void rejectsDuplicateOrderWithoutCharging() {
        store.save(new Order("ORD-1", "BOOK", 1, 1_500L, "PAY-OLD"));

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> service.checkout("ORD-1", "BOOK", 2));

        assertEquals("duplicate order", error.getMessage());
        assertEquals(1, store.size());
        verifyNoInteractions(catalog, payment);
        verify(audit, never()).record(anyString());
    }

    @Test
    @DisplayName("Zero quantity triggers no I/O")
    void rejectsNonPositiveQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> service.checkout("ORD-2", "BOOK", 0));

        assertEquals(0, store.size());
        verifyNoInteractions(catalog, payment);
        verify(audit, never()).record(anyString());
    }

    @Test
    @DisplayName("Payment failure does not save order or record audit")
    void doesNotSaveWhenPaymentFails() {
        when(catalog.unitPriceCents("BOOK")).thenReturn(1_500L);
        when(payment.charge("ORD-2", 1_500L))
                .thenThrow(new IllegalStateException("declined"));

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> service.checkout("ORD-2", "BOOK", 1));

        assertEquals("declined", error.getMessage());
        assertFalse(store.exists("ORD-2"));
        assertEquals(0, store.size());
        verify(payment).charge("ORD-2", 1_500L);
        verify(audit, never()).record(anyString());
    }

    @Test
    @DisplayName("doReturn on spy avoids invoking real method during stub setup")
    void stubsSpyWithoutExecutingRealMethodDuringSetup() {
        List<String> listSpy = spy(new ArrayList<>(List.of("first")));

        // Using when(listSpy.get(9)) would invoke real get(9) and throw
        // during stub setup; doReturn does not call get(9).
        doReturn("stubbed").when(listSpy).get(9);

        assertEquals("stubbed", listSpy.get(9));
        assertEquals(1, listSpy.size()); // size() runs for real.
        verify(listSpy).get(9);
    }

    interface Catalog {
        long unitPriceCents(String sku);
    }

    interface PaymentGateway {
        String charge(String orderId, long amountCents);
    }

    interface OrderStore {
        boolean exists(String orderId);
        void save(Order order);
        Order find(String orderId);
        int size();
    }

    interface AuditTrail {
        void record(String event);
    }

    record Order(
            String id,
            String sku,
            int quantity,
            long totalCents,
            String paymentId) {
    }

    static final class CheckoutService {
        private final Catalog catalog;
        private final PaymentGateway payment;
        private final OrderStore store;
        private final AuditTrail audit;

        CheckoutService(Catalog catalog, PaymentGateway payment,
                        OrderStore store, AuditTrail audit) {
            this.catalog = catalog;
            this.payment = payment;
            this.store = store;
            this.audit = audit;
        }

        Order checkout(String orderId, String sku, int quantity) {
            if (orderId == null || orderId.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("invalid order");
            }
            if (store.exists(orderId)) {
                throw new IllegalStateException("duplicate order");
            }

            long unitPrice = catalog.unitPriceCents(sku);
            if (unitPrice <= 0) {
                throw new IllegalArgumentException("invalid price");
            }

            long amount = Math.multiplyExact(unitPrice, quantity);
            String paymentId = payment.charge(orderId, amount);

            Order order = new Order(
                    orderId, sku, quantity, amount, paymentId);
            store.save(order);
            audit.record("created:" + orderId);

            return order;
        }
    }

    static final class FakeOrderStore implements OrderStore {
        private final Map<String, Order> orders = new HashMap<>();

        @Override
        public boolean exists(String orderId) {
            return orders.containsKey(orderId);
        }

        @Override
        public void save(Order order) {
            if (orders.putIfAbsent(order.id(), order) != null) {
                throw new IllegalStateException("duplicate order");
            }
        }

        @Override
        public Order find(String orderId) {
            return orders.get(orderId);
        }

        @Override
        public int size() {
            return orders.size();
        }
    }

    static class RecordingAudit implements AuditTrail {
        private final List<String> events = new ArrayList<>();

        @Override
        public void record(String event) {
            events.add(event);
        }

        List<String> events() {
            return List.copyOf(events);
        }
    }
}
~~~

### Analyzing the Role and Evidence of Each Test

| Part | Role | Why chosen | Meaningful assertion |
| --- | --- | --- | --- |
| `CheckoutService` | **Real component** | Checkout logic is what is under test | Returned order, price, state |
| `catalog` | **Stub** on Mockito `@Mock` | Test needs stable unit prices, not testing catalog | Total = quantity × unit price |
| `payment` | **Mock** on Mockito `@Mock` | Must know whether charge command was/was not sent | `verify(payment).charge(...)` and `verifyNoInteractions(...)` |
| `store` | Hand-written **Fake** | Need to save and find orders without a database | `store.find(...)`, `store.size()` |
| `audit` | **Spy** of real implementation | Want to keep event recording and observe calls | `audit.events()` and `verify(audit).record(...)` |

**Success scenario:** stub `catalog` to return 1,500 cents; the calculation `2 × 1,500 = 3,000 cents` runs through the real service; `payment` is stubbed to return `PAY-9` and verified for the exact call. The fake store holds the record; the audit spy actually adds the event to the list.

**Duplicate order:** the fake already holds `ORD-1`, so the service rejects before querying price or charging. No extra stubs are created in setup; the test explicitly checks both state and the absence of mocked I/O calls.

**Zero quantity:** validation runs before any collaborator; the test needs no stubs. This avoids `UnnecessaryStubbingException` when using `MockitoExtension` with strict stubbing.

**Payment failure:** Mockito throws an exception per scenario; the service does not save the order and does not record audit. The assertions reflect the example's current behavior and **do not prove an external payment transaction was rolled back**.

**Spy on a list:** using `doReturn("stubbed").when(listSpy).get(9)` avoids calling `ArrayList.get(9)` when declaring the stub. Using `when(listSpy.get(9)).thenReturn("stubbed")` would invoke the real `get(9)` immediately at the stubbing step and could throw `IndexOutOfBoundsException`.

### Running with Gradle

In a Spring Boot module that already has the Gradle plugin and dependency management, `build.gradle` typically contains the following snippet (this is **not a standalone build file**):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` in compatible Spring Boot 3.x releases provides JUnit Jupiter and Mockito, including `mockito-junit-jupiter` for `MockitoExtension`. For plain Java projects without Spring Boot, declare the JUnit Jupiter engine and `org.mockito:mockito-junit-jupiter` using a compatible BOM/version.

Run from the Gradle root containing the test module:

~~~bash
./gradlew test --tests example.CheckoutServiceTest
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.CheckoutServiceTest
~~~

**Expected result:** JUnit Platform discovers **5 `@Test` methods** and all 5 PASS when the project is configured properly. There is no stdout printed by the tests themselves; Gradle normally finishes a successful task with `BUILD SUCCESSFUL`, while console verbosity depends on Gradle/IDE settings. This test requires no Docker, PostgreSQL, or Spring `ApplicationContext`.

**Model limitation:** all domain classes are placed inside the test file so the example is self-contained and compilable. In a real project, `CheckoutService`, `Order`, and the ports must be **imported from `src/main/java`**; never duplicate production logic inside tests and treat it as proof of testing production code.

## 7. Spy: Running Real Code While Observing, but Use with Care

A spy typically wraps an object that already has a real implementation:

~~~java
List<String> spyList = spy(new ArrayList<>());
spyList.add("A");

verify(spyList).add("A");
assertEquals(List.of("A"), spyList);
~~~

This is an **illustrative snippet inside a test class**; `spy`, `verify`, and `assertEquals` require appropriate static imports and `List`/`ArrayList` require `java.util` imports.

Unlike a plain mock, **a spy calls real methods by default**. That is useful when you need to preserve original behavior, but it carries two risks:

1. **Stubbing with `when(spy.method())` can execute the real method right at stub creation time.** If the method hits a DB, reads a file, or throws because parameters are not yet valid, the side effect happens before the SUT is even called. When stubbing a spy, prefer `doReturn(...).when(spy).method(...)` or `doThrow(...).when(spy).method(...)`.
2. **A spy is not always a forwarding proxy to the original instance.** Mockito can create a **copy of the state** when the spy is created; subsequent mutations to the original object will not necessarily appear in the spy and vice versa. Interact through the spy reference in tests; do not rely on both references sharing state.

If the goal is to verify the right output without needing to observe calls, **using a real object without a spy** is usually simpler. Do not spy on a service just to verify private/internal methods; test design should rely on public contracts.

**Spying on a Spring bean** differs from spying on a POJO: a Spring bean may be wrapped by proxies for transactions, caching, security, or other advice. Mockito-spying an object outside Spring does not automatically test that those advice layers work. When you need to spy a bean in a Spring test context, use the override/spy bean mechanism appropriate for your Spring Boot/Framework version and understand how it interacts with AOP proxies; for critical `@Transactional` tests, prefer assertions on real transactions and data.

## 8. @Mock, @Spy, @InjectMocks, and Test Lifecycle Management

Mockito can provide components via annotations when `MockitoExtension` is active:

- `@Mock`: creates a mock for an interface/class.
- `@Spy`: wraps a real implementation to keep most behavior and record interactions.
- `@Captor`: creates an `ArgumentCaptor<T>` to capture and inspect complex arguments.
- `@InjectMocks`: attempts to instantiate the SUT (if needed) and inject existing mocks/spies via constructor, setter, or field as supported; it **does not start Spring** and does not replace Spring Boot's real dependency injection.

Conceptual example:

~~~java
@ExtendWith(MockitoExtension.class)
class PriceServiceTest {
    @Mock
    PriceProvider provider;

    @InjectMocks
    PriceService service;

    // @Test uses the real service with provider replaced by a mock.
}
~~~

The snippet above **only illustrates how to declare annotations** and cannot compile on its own because `PriceProvider`/`PriceService` are application classes. With explicit constructors, instantiating the SUT **manually** as in `CheckoutServiceTest` is often easier to read and catches missing dependencies immediately.

Do not overuse `@InjectMocks` on a large object graph and assume “because the test passes, Spring will inject beans the same way.” Only a Spring Boot integration test verifies real configuration, bean selection, qualifiers, profiles, and AOP.

In JUnit Jupiter, `@ExtendWith(MockitoExtension.class)` is the standard way to use Mockito annotations in unit tests. If you do not use the extension, you can call `mock(...)`/`spy(...)` directly; if you want to initialize `@Mock` manually, you must manage its lifecycle via `MockitoAnnotations.openMocks(...)` and close resources appropriately. Avoid mixing multiple lifecycle mechanisms without good reason.

## 9. Writing Assertions on State and Interactions

### When to Use verify?

Suppose the requirement is “the system must send exactly one payment request”:

~~~java
verify(payment).charge("ORD-1", 3_000L);
~~~

If you only assert that the order was saved in the fake, the test **could miss** an implementation that calls the gateway twice. Because charging is an external side effect, verifying once is an important signal.

Suppose the requirement is “the order must be saved with the correct total”:

~~~java
assertEquals(3_000L, store.find("ORD-1").totalCents());
~~~

In this case, `verify(store).save(...)` is unnecessary if the fake already lets you observe the final data. Using both indiscriminately couples the test to the mechanics of saving.

### ArgumentCaptor for Complex Payloads

Suppose a method takes a `PaymentRequest` with multiple fields; you can capture the argument:

~~~java
ArgumentCaptor<PaymentRequest> captor =
        ArgumentCaptor.forClass(PaymentRequest.class);

verify(paymentPort).charge(captor.capture());

assertEquals("ORD-1", captor.getValue().orderId());
assertEquals(3_000L, captor.getValue().amountCents());
~~~

This snippet **illustrates** the API when the port has signature `charge(PaymentRequest)`, which **differs** from `charge(String,long)` in the full example. In real Java, use the interface's exact signature. If the argument is a record with proper `equals`, verifying directly with the record can be clearer than using a captor.

### Checking Order with InOrder When the Contract Truly Requires It

For example, if business rules require not writing audit before payment succeeds, you can use `InOrder` to verify interactions across two mocks/spies. However, the order between getters, mappers, or internal helpers **should not be a test contract**. When changing operation order preserves results and invariants, the test should continue to PASS.

`verifyNoMoreInteractions(...)` can make tests brittle: a harmless log or an extra lookup can fail the test. Use it only when the contract truly forbids any additional interactions, such as guaranteeing no second I/O command is issued.

## 10. Strict Stubbing, Default Answers, and Test Quality

With the Mockito JUnit Jupiter extension, strict stubbing helps detect scenarios where a stub is configured but **unused** or invoked with mismatched arguments, for example:

~~~java
when(catalog.unitPriceCents("BOOK")).thenReturn(1_500L);
// Test only checks quantity = 0 and exits before querying catalog.
~~~

If the test never calls `catalog.unitPriceCents("BOOK")`, Mockito can report `UnnecessaryStubbingException` at the end. This is usually a sign of **excess Arrange**: a test is preparing data for a code path that never executes.

Good fixes:

- Place stubbing **right inside each test** that needs it, as in Section 6.
- If multiple tests genuinely share the same stub, put it in setup, but avoid setting up the entire “happy path” for failure tests too.
- Only use `lenient()` or relax strictness with a clear reason, never to hide all unused stubs.
- Do not repeatedly call `reset(mock)` between steps just to reuse a shared mock; creating a fresh fixture per test is usually easier to manage.

### Default Answers Do Not Represent Production

An unstubbed Mockito mock can still “respond” with a default value. If `payment.charge(...)` returns `null`, that does not mean the real gateway would return null. Tests should be explicit about when null is allowed and when a response, exception, or network failure must be stubbed.

Mockito's purpose is to **control dependencies at a chosen boundary**, not to fully emulate the real service.

## 11. Mockito in Spring Boot: Unit Tests vs. Spring Context Tests

### Unit Tests: @Mock with Constructor, No ApplicationContext Needed

For pure Java business services, use `MockitoExtension` and construct the SUT via its constructor. This is usually the fastest and clearest way to test business branches.

### Spring Slice/Integration Tests: Replacing Beans in ApplicationContext

When testing controllers with `@WebMvcTest` or starting a context with `@SpringBootTest`, a plain `@Mock` field does not automatically override a bean injected by Spring. You need the Spring test override API matching your version:

- **Spring Boot 3.3 and earlier**: commonly `org.springframework.boot.test.mock.mockito.MockBean` or `SpyBean`.
- **Spring Boot 3.4 / Spring Framework 6.2 and later**: provides `org.springframework.test.context.bean.override.mockito.MockitoBean` and `MockitoSpyBean`; the older Spring Boot annotations are deprecated in 3.4. Check your actual dependency/import version before making changes.
- When upgrading projects across versions, do not copy annotations from a different release without verifying the API and bean override behavior.

Syntax example in a Spring Framework supporting `@MockitoBean` (not a standalone file, as it requires a real controller/service):

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @MockitoBean
    OrderService orderService;

    // @Test with MockMvc to verify status, JSON, and MVC mapping.
}
~~~

This Spring test verifies the web slice and context wiring, not just `OrderService` unit logic. Do not replace `OrderController` with a mock and conclude HTTP mapping works: keep the MVC layer under test real.

Similarly, when testing `@Transactional`, JPA mapping, or Spring Security method advice, keep the relevant framework/bean components running for real; avoid mocks that strip away the mechanism you need to prove. A test using a mocked repository cannot confirm SQL or transaction rollback.

## 12. Fakes Must Be Controlled Like a Simplified Contract

A `Map`-backed fake repository is easy to write, but you must explicitly state **which behaviors it guarantees**:

- `save` followed by `find` returns data by ID.
- Checks duplicate ID conditions if unit tests require that rule.
- State is independent across tests, freshly initialized in `@BeforeEach`.
- Does not guarantee locking, concurrent updates, transaction rollback, or SQL constraints.

If a fake behaves differently from the real adapter, unit tests will give false evidence. When needed, write **the same suite of contract tests** running against both the fake and the real adapter to ensure the shared contract holds; for database-specific features, add dedicated integration tests.

**Do not grow a fake into a homemade database.** Once a fake starts simulating a query optimizer, race conditions, transaction isolation, or complex pagination, using a real database in Testcontainers is more appropriate and less risky.

Example choices by bug type:

| Bug to catch | Appropriate choice |
| --- | --- |
| Calculation error or missing validation in service | Real service + stub/fake/mock at the boundary |
| Email not sent when request fails | Mock email port, `verifyNoInteractions` |
| Order written to repository port with correct data | Fake store + state assertions |
| Wrong JPQL/native SQL, entity mapping missing column | Real repository + DB container |
| HTTP client builds wrong headers/JSON | HTTP stub server/contract test over real transport |
| Redis TTL, Kafka ack/offset | Real adapter + appropriate Redis/Kafka |
| Spring transaction fails to roll back | Spring context and real DB, assert state after transaction |

Fakes and mocks isolate **logic**; they do not replace all evidence from **real protocols and infrastructure**.

## 13. Common Mistakes When Using Mockito

### 13.1 Mocking the SUT Itself

Wrong target: `CheckoutService service = mock(CheckoutService.class)`, then stubbing `checkout(...)` to return an `Order` and asserting that result. The test only proves Mockito returned the value you configured, **not the checkout logic**.

Solution: instantiate the real `CheckoutService` and only replace collaborators at necessary boundaries.

### 13.2 Over-Mocking Every Class

Mocking controller, service, mapper, entity, record, and repository makes the test mirror internal implementation and hard to refactor. Prefer real data for value objects and pure functions; mock I/O or important side effects.

### 13.3 Excessive or Overly Broad Stubbing

`when(provider.anything()).thenReturn(...)` with overly broad `any()` can hide the SUT passing the wrong SKU/key. Stub the exact inputs needed and let strict stubbing catch argument mismatches. If a response applies meaningfully to multiple inputs, express that contract clearly.

### 13.4 Overusing verifyNoMoreInteractions and InOrder

These assertions couple the test to every internal step, causing valid refactorings to break tests. Only use them when **no extra calls** or **ordering** is truly a business requirement.

### 13.5 Spy Executing Real I/O Unintentionally

`when(spyClient.fetch()).thenReturn(data)` can perform a real HTTP call during setup. Use `doReturn(...)` for spies and reconsider whether a spy is truly needed instead of just mocking the I/O interface.

### 13.6 Spying an Original Object and Continuing to Mutate the Original

A spy should not be assumed to synchronize every change with the input object because Mockito may copy state on creation. Interact through the spy reference, and manage any shared resources explicitly.

### 13.7 Using Mockito as a Database Emulator

Mockito does not reproduce transactions, constraints, SQL, or query planners. Unit testing a service with a mocked repository can be great, but the repository itself still needs real verification when risk lies in persistence.

### 13.8 Mixing @Mock with Spring Bean Overrides

A `@Mock` field in `@SpringBootTest` does not automatically swap out the bean a controller/service gets from `ApplicationContext`. Choose `@MockBean`/`@MockitoBean` according to version when a Spring test is genuinely needed.

### 13.9 Relying on Internal Details Instead of Outcomes

Verifying private-like helpers, every mapping method, or getter call counts makes tests fragile. Tests should read like a contract: “do not charge when out of stock”, “save the right order on success”.

### 13.10 Ignoring Checked Exceptions and Return Types

You cannot `thenReturn(...)` a value incompatible with the method's declared return type. Mockito also enforces rules on checked exceptions: you cannot arbitrarily stub a checked exception that the method does not validly declare. Model port contracts clearly so tests reflect production error states that can actually occur.

### 13.11 Sharing Mocks Across Tests

Mocks record interaction history; using static singleton mocks or calling `reset` repeatedly invites order-dependent tests. JUnit Jupiter + `MockitoExtension` creating fresh mocks per test lifecycle is a solid default.

### 13.12 Forgetting to Verify Cancellation or Compensation of Side Effects

`verify(payment).charge(...)` only proves a command was sent to the port; it does not prove the external payment gateway succeeded, was idempotent, or rolled back. When business criticality is high, add integration/contract tests and design transactions/compensation accordingly.

## 14. How to Build a Valuable Test with Mockito

An easy-to-follow workflow:

1. **Name the behavior:** e.g., “Do not send a charge command when quantity is invalid.”
2. **Keep the SUT real:** `CheckoutService`.
3. **Classify collaborators:** data → stub; state → fake; external command → mock; real behavior needing observation → spy if necessary.
4. **Minimal Arrange:** only stub data the test actually uses; set up fake state through contract methods.
5. **Single Act:** call the SUT's public API; do not call private/internal helpers.
6. **Assert outcomes:** return value, state, exception; add `verify` for important interactions.
7. **Review untested risks:** real queries, transactions, serialization, HTTP status, brokers… and place integration tests at the appropriate layer.
8. **Verify repeatability:** give each test an independent fixture, avoid real time/randomness/uncontrolled networks, and avoid order dependence.

A particularly important example: when publishing an event is the main effect of a use case, **mock the publisher** and `verify(publish(event))` is necessary. However, when a service returns an observable result, **asserting the output** is often sufficient. Good tests select interactions **intentionally**, rather than verifying every dependency by default.

## 15. Checklist Before Finalizing a Test

- [ ] The SUT is the real implementation under test, not mocked.
- [ ] Stubs return fixed inputs/errors for a clear reason; mock default responses are not assumed to match production.
- [ ] Fakes have a small contract and state, initialized independently per test.
- [ ] Mocks verify only business-meaningful interactions, especially outgoing side effects.
- [ ] Spies are used deliberately; default real-method execution is understood and `doReturn`/`doThrow` is considered when stubbing.
- [ ] `@Mock`/`@Spy` has `MockitoExtension` or an appropriate initialization/closing mechanism.
- [ ] Mockito unit-test annotations are not mixed with Spring bean overrides in a way that runs the SUT in an unexpected context.
- [ ] For public data, `assertEquals`/state assertions are preferred before adding internal verifications.
- [ ] `lenient`, `reset`, `verifyNoMoreInteractions`, and `InOrder` are not overused.
- [ ] Tests cover multiple cases: success, invalid input, collaborator failure, and **no side effects** when rejected.
- [ ] SQL/schema/transactions/HTTP wire protocol have corresponding integration/contract tests; fakes/mocks do not prove them on their own.
- [ ] Java 17+ tests run via JUnit Platform without requiring a network/DB when only testing unit logic.

**Concept summary:** *stub* provides programmed data; *fake* provides simplified behavior/state; *mock* verifies interactions; *spy* observes a real object (with selective stubbing). Mockito can implement several of these roles, while your test goal and assertions determine the right test double. Always keep the logic under test running for real, and add integration tests wherever real infrastructure behavior determines correctness.

### References

- Martin Fowler, [Test Double](https://martinfowler.com/bliki/TestDouble.html): terminology for dummy, stub, fake, mock, spy, and state vs. behavior verification.
- [Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html): `mock`, `spy`, stubbing, verification, and notes on real method execution on spies.
- [Mockito JUnit Jupiter extension](https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/org.mockito.junit.jupiter/org/mockito/junit/jupiter/MockitoExtension.html): managing `@Mock`/strict stubbing in JUnit 5.
- [Spring Framework Testing – Bean Override with Mockito](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): `@MockitoBean`, `@MockitoSpyBean`, and Spring test context.
- [Spring Boot Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): unit/slice/integration test types and Spring Boot starter test.
