# Mockito: Limiting Over-Mocking and Tests That Only Mirror Implementation

## Goal

In Spring Boot, Mockito lets you test a component without calling a real database, HTTP service, or notification system. However, mocking too much can reduce a test to proving merely that **a mock returns the exact value you just told it to return**, or asserting that the implementation called specific internal methods. When the design changes while external behavior stays right, such tests break easily; when a business bug exists, they can keep passing.

After this lesson, you will be able to:

- Distinguish **testing observable behavior** from **testing internal call structure**.
- Recognize over-mocking and tests that merely repeat implementation assumptions or production bugs.
- Identify when mocks belong: at I/O boundaries, hard-to-control collaborators, external side effects, or contractually required interactions.
- Combine Mockito with JUnit Jupiter to verify meaningful return values and persistence requests.
- Structure a test suite mixing unit tests with **real logic** and integration tests for behaviors mocks cannot prove.
- Use the question “which test fails on a business bug yet stays green across a refactoring?” to review assertion quality.

**Main takeaway:** A mock is a dependency-control tool. Test quality depends on **the contract being verified and the evidence assertions provide**, not on how many `@Mock`, `when`, or `verify` calls you write.

## 1. Mock, Stub, Fake, Spy, and System Under Test

**SUT (System Under Test)** is the component being verified. **Collaborators** are objects the SUT uses. You can test a service with real collaborators, fakes, or mocks depending on the goal. A Mockito “mock” can both be **stubbed** to return data and **verified** to check interactions.

| Concept | Primary role | Example |
| --- | --- | --- |
| **Real SUT** | Executes the logic under verification | `PriceCalculator`, `OrderService` |
| **Stub** | Supplies controlled responses | Repository configured to return a specific `Customer` |
| **Mock** | Test double created by Mockito, supporting stubbing and verification | `@Mock OrderRepository repository` |
| **Fake** | Simplified implementation with working behavior | `InMemoryOrderRepository` storing orders in a list |
| **Spy** | Wraps a real object to observe or selectively override calls | `spy(realService)` in special cases |

In Mockito, `when(repository.findById(42L)).thenReturn(Optional.of(customer))` is **stubbing** a mock. `verify(repository).save(order)` is **verifying an interaction**. Both are useful, yet neither replaces assertions on data, state, and business rules.

A pragmatic rule:

> **Run real logic when the goal is to test that logic; replace boundaries you do not need to run for real when the goal is to test how the SUT uses those boundaries.**

For instance, unit testing price calculation does not need to mock multiplication, discount rules, or a data-holding `record`. Yet testing an email-sending flow can mock `MailGateway` to avoid sending real emails and verify the right message was requested. Testing an order-saving service can mock the repository to verify the save call, while proving SQL, JPA mappings, or real transactions requires an appropriate integration test.

## 2. What Is “Over-Mocking”?

**Over-mocking** happens when tests mock so aggressively that they replace the core logic under test or lock down excessive internal details. There is no fixed threshold like “more than three mocks is wrong”; what matters is **what the mocks replace and what the assertions prove**.

Warning signs:

1. **Mocking pure-logic objects** such as calculators, validators, I/O-free mappers, and value objects—stubbing the very computation that ought to run for real.
2. **Stubbing intermediate steps** and `verify`ing the exact order of private/implementation-level calls; tests break on refactorings even though public outputs stay unchanged.
3. **Repeating implementation assumptions inside expected values** (the same off-by-one condition, the same flawed formula), making both test and production return the same wrong answer.
4. Many `when(...).thenReturn(...)` lines paired with few assertions on outputs, state, or meaningful effects; the test mainly proves mocks behave as configured.
5. Calling `verifyNoMoreInteractions(...)` or `InOrder` on every collaborator just to freeze implementation structure even though **call order and count are not part of the contract**.
6. Every controller/service test mocks every lower layer, leaving no tests that exercise real logic together with critical persistence or serialization.

These signs are **review prompts**, not absolute bans. If the contract says “a transaction must send a charge request at most once,” `times(1)` is a vital business assertion. If “write audit before publishing event” is a requirement, `InOrder` makes sense. Without such requirements, verifying every helper call only raises refactoring costs.

## 3. Two Test Patterns That Create a False Sense of Security

### 3.1. Stubbing Away the Result of the Logic Under Test

Suppose the rule is “buying 2 items at 120 units each yields a total of 240.” A test might write:

~~~java
// PATTERN TO REVIEW: illustrative snippet, not a standalone runnable class.
PriceCalculator calculator = mock(PriceCalculator.class);
OrderRepository repository = mock(OrderRepository.class);

when(calculator.total(2, 120)).thenReturn(240);

OrderService service = new OrderService(calculator, repository);
Order result = service.place("BOOK", 2, 120);

assertEquals(240, result.amount());
verify(calculator).total(2, 120);
~~~

This test runs the **real `OrderService`**, yet **`PriceCalculator.total` never runs at all**. If the real formula accidentally changed from `quantity * unitPrice` to `quantity + unitPrice`, this test would still pass because the mocked `calculator` returns 240. `verify(calculator).total(2, 120)` only proves the call occurred, **not that the calculation is right**.

It still has a valid narrow purpose if the goal is specifically “`OrderService` passes the right inputs to `PriceCalculator`,” but never report it as proof of the **pricing rule**. To test that rule, use a real `new PriceCalculator()` and assert against an expected figure derived from requirements.

### 3.2. Computing Expected Values Using the Same Flawed Formula as Production

Suppose business rules specify **orders of 500 or more get free shipping**, while smaller orders pay 30. If both production code and test code mistakenly write `> 500` instead of `>= 500`, the test below misses the bug at the 500 boundary:

~~~java
// FLAWED ORACLE PATTERN; assumes service.shippingFee exists.
int subtotal = 500;
int expected = subtotal > 500 ? 0 : 30; // copied buggy condition
assertEquals(expected, service.shippingFee(subtotal));
~~~

If the SUT also uses `>`, `expected` is 30 and `actual` is 30, so the test passes even though **the true requirement is 0**. This is **mirroring implementation**: the test lacks an independent source of truth.

The fix is deriving inputs and expected results directly from the specification:

~~~java
// Illustrative: expectations derived from the “500 or more” rule.
assertEquals(0, service.shippingFee(500));
assertEquals(30, service.shippingFee(499));
assertEquals(0, service.shippingFee(501));
~~~

The `shippingFee` snippets illustrate boundary rules; the lesson's runnable program in Sections 5–6 uses a simpler pricing domain. Computing expected values programmatically is not **always wrong**, provided you prove the expectation derives from the specification **independently** of the SUT's code path. For multi-step logic, use vetted example tables or an independent reference calculation rather than copying production logic into tests.

### 3.3. Verifying Implementation Steps Instead of External Outcomes

Suppose a service splits its work into `normalize()`, `calculate()`, and `map()` before returning an `Order`. If a test forces all three helpers to be called in sequence simply because the current code does so, merging two helpers or caching intermediate values breaks the test even though the API remains valid. Better contracts usually state: “right amount, right order saved, invalid input never saved.”

**Which effects are contract?** For a repository in a “place order” use case, **saving the order** is likely part of the service contract, making `verify(repository).save(...)` a sound assertion. By contrast, “the service must call `calculator.total` exactly once” is normally an implementation detail unless cost, idempotency, side effects, or consistency requirements tie external behavior to call count.

## 4. Choosing Mock Boundaries Intentionally

Ask what each dependency represents before mocking:

| Dependency | Typical choice | Why |
| --- | --- | --- |
| Pure Java `PriceCalculator`/`DiscountPolicy` | **Run for real** | Core logic to protect; fast and deterministic |
| `Order` record, value objects | **Run for real** | Simple data with no I/O |
| `OrderRepository` backed by a real DB | **Mock in service unit tests** or use a fitting fake | Isolates I/O and checks save intent; integration tests still prove real persistence |
| HTTP client calling an external provider | **Stub/mock at the adapter boundary** | Avoids real network, fees, and flakiness |
| `Clock` | **Real `Clock.fixed(...)`** | Controls time without Mockito |
| Injectable `Random`/ID generator | **Fake or deterministic seed/ID stub** | Prevents randomness from making tests flaky |
| Spring MVC serialization and HTTP mapping | **`MockMvc` with real controller/serializer** | Verifies status codes, JSON bodies, validation, and mappings |
| JPA mapping/SQL/transactions | **Appropriate DB test** | Mocked repositories execute neither SQL nor transactions |

Do not mock every collaborator merely because it sits outside the SUT class. Pure Java objects and fast dependencies can run for real to reduce setup and exercise more meaningful business paths.

**Fakes and mocks answer different questions.** An in-memory fake repository can test save-then-read flows at the service level, yet proves nothing about JPA mappings, SQL constraints, or real DB transactions. A mock can verify “which order `repository.save` was called with,” yet proves nothing about rows committed. To verify persistence adapters, write integration tests wired to real-like infrastructure.

## 5. Java 17 + JUnit Jupiter + Mockito Example: Mocking Only the Persistence Boundary

Design a small problem:

- An item has `sku`, `quantity` (positive integer), and `unitPrice` (non-negative unit price).
- Total is **`quantity × unitPrice`**; if multiplication overflows `int`, reject it rather than silently wrapping.
- `OrderService.place(...)` returns the right order and requests the repository to save it.
- Blank `sku`, invalid quantity, or negative unit price must be rejected; invalid data **must not be saved**.

Here **`PriceCalculator` is real logic to verify**; `OrderRepository` is the I/O boundary replaced by a mock in unit tests. We do not need to boot a Spring `ApplicationContext` to test a plain Java service.

### 5.1. Project Structure

~~~text
mock-boundary-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/com/example/testing/
    │   ├── PriceCalculator.java
    │   ├── Order.java
    │   ├── OrderRepository.java
    │   └── OrderService.java
    └── test/java/com/example/testing/
        ├── PriceCalculatorTest.java
        └── OrderServiceTest.java
~~~

The example needs no Spring Boot module to run, so it uses the `java` plugin to highlight mock boundaries clearly; **the exact same pattern applies in Spring Boot projects**. If a repo already has a Wrapper, use it. For a new project, generate the Wrapper with a compatible Gradle version and commit the Wrapper files.

**`settings.gradle`**

~~~groovy
rootProject.name = 'mock-boundary-demo'
~~~

**`build.gradle`** uses Gradle Groovy DSL with JUnit 5.10.2 and Mockito 5.12.0 to give concrete illustrative versions, without forcing other Spring Boot projects to match these exact numbers:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'org.mockito:mockito-junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`mockito-junit-jupiter` provides Mockito integration for Jupiter and brings in Mockito core. `@ExtendWith(MockitoExtension.class)` creates fresh mocks per test and enables unused-stub checks. `useJUnitPlatform()` tells Gradle to run tests on JUnit Platform. When a project **already has** `spring-boot-starter-test`, check existing dependencies before adding JUnit/Mockito directly; the starter normally manages compatible versions via the Spring Boot BOM.

### 5.2. Production Code: Real Logic and One Output Port

**`src/main/java/com/example/testing/PriceCalculator.java`**

~~~java
package com.example.testing;

public final class PriceCalculator {

    public int total(int quantity, int unitPrice) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        if (unitPrice < 0) {
            throw new IllegalArgumentException(
                    "unitPrice must not be negative");
        }

        return Math.multiplyExact(quantity, unitPrice);
    }
}
~~~

`Math.multiplyExact(int, int)` throws `ArithmeticException` on `int` overflow. That is an explicit requirement in this example: tests guard against silently returning wrapped numbers on overflow. In real monetary systems, specify appropriate units and numeric types, such as `BigDecimal` or smallest-unit integers rather than plain `int`.

**`src/main/java/com/example/testing/Order.java`**

~~~java
package com.example.testing;

public record Order(String sku, int quantity, int amount) {
}
~~~

**`src/main/java/com/example/testing/OrderRepository.java`**

~~~java
package com.example.testing;

public interface OrderRepository {
    void save(Order order);
}
~~~

`OrderRepository` is an illustrative interface representing a persistence port. It is not a Spring Data JPA repository itself and has no real implementation yet; this is intentional so service tests stay independent of infrastructure. In Spring Boot, a real adapter can wrap `JpaRepository`, while service unit tests focus solely on the output port's contract.

**`src/main/java/com/example/testing/OrderService.java`**

~~~java
package com.example.testing;

import java.util.Objects;

public final class OrderService {

    private final PriceCalculator calculator;
    private final OrderRepository repository;

    public OrderService(
            PriceCalculator calculator,
            OrderRepository repository) {
        this.calculator = Objects.requireNonNull(calculator);
        this.repository = Objects.requireNonNull(repository);
    }

    public Order place(String sku, int quantity, int unitPrice) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }

        int amount = calculator.total(quantity, unitPrice);
        Order order = new Order(sku, quantity, amount);
        repository.save(order);
        return order;
    }
}
~~~

Observable flow: validate SKU; compute amount using the real calculator; construct `Order`; call port `save`; return the order. On invalid input, the method throws before calling `save`. Because this implementation touches no database directly, tests need neither a Spring context nor transactions.

### 5.3. Testing Pricing Logic with the Real Object

**`src/test/java/com/example/testing/PriceCalculatorTest.java`**

~~~java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {

    private final PriceCalculator calculator = new PriceCalculator();

    @Test
    void multipliesQuantityByUnitPrice() {
        // Arrange: well-defined business example
        int quantity = 2;
        int unitPrice = 120;

        // Act
        int amount = calculator.total(quantity, unitPrice);

        // Assert: independent expected value from specification
        assertEquals(240, amount);
    }

    @Test
    void zeroUnitPriceProducesZeroAmount() {
        assertEquals(0, calculator.total(3, 0));
    }

    @ParameterizedTest
    @ValueSource(ints = {0, -1})
    void rejectsNonPositiveQuantity(int quantity) {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.total(quantity, 120));
    }

    @Test
    void rejectsNegativeUnitPrice() {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.total(2, -1));
    }

    @Test
    void rejectsIntegerOverflow() {
        assertThrows(ArithmeticException.class,
                () -> calculator.total(Integer.MAX_VALUE, 2));
    }
}
~~~

This test class uses zero `@Mock` fields because it tests **calculation logic directly**. The two `@ValueSource` values create two separate invocations; the other `@Test` methods create four invocations, totaling **6 test invocations**. Changing multiplication to addition fails `multipliesQuantityByUnitPrice`. Removing the `quantity<=0` check fails the validation test. Replacing `multiplyExact` with raw `*` fails the overflow test. These provide **evidence of business rules**, not helper call counts.

Note: `assertEquals(240, amount)` uses a **predetermined expected value**—it never calls `calculator.total` to compute expectations nor mocks a return value of 240. Boundary cases come directly from the opening requirements.

### 5.4. Testing the Service with a Single Mock at the Output Port

**`src/test/java/com/example/testing/OrderServiceTest.java`**

~~~java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository repository;

    private final PriceCalculator calculator = new PriceCalculator();

    @Test
    void placeReturnsCorrectOrderAndRequestsPersistence() {
        // Arrange: real service, real calculator, mocked repository
        OrderService service = new OrderService(calculator, repository);

        // Act
        Order result = service.place("BOOK", 2, 120);

        // Assert: observable business result
        assertEquals(new Order("BOOK", 2, 240), result);

        // Assert: saving the exact created order is part of the use-case contract
        ArgumentCaptor<Order> captured =
                ArgumentCaptor.forClass(Order.class);
        verify(repository).save(captured.capture());
        assertEquals(result, captured.getValue());
    }

    @Test
    void invalidQuantityDoesNotSaveAnOrder() {
        OrderService service = new OrderService(calculator, repository);

        assertThrows(IllegalArgumentException.class,
                () -> service.place("BOOK", 0, 120));

        verifyNoInteractions(repository);
    }

    @Test
    void blankSkuDoesNotSaveAnOrder() {
        OrderService service = new OrderService(calculator, repository);

        assertThrows(IllegalArgumentException.class,
                () -> service.place("   ", 1, 120));

        verifyNoInteractions(repository);
    }
}
~~~

The first test provides two **distinct** pieces of evidence:

1. `assertEquals(new Order("BOOK", 2, 240), result)` checks the use case's return value while the real calculator executes.
2. `verify(repository).save(captured.capture())` and `assertEquals(result, captured.getValue())` verify the requirement to save **the exact returned order**, without asserting internal helpers or calculation steps.

`ArgumentCaptor` helps when the contract requires **the payload sent across the boundary** to match specific data. Because `Order` is a record with component-based `equals`, a simple case could also write `verify(repository).save(new Order("BOOK", 2, 240))`; the captor is shown here to illustrate payload inspection independent of repository internals.

The two invalid-input tests use `verifyNoInteractions(repository)` because the requirement explicitly states **invalid input must not be saved**. If buggy code calls `save` before validating, this assertion catches a meaningful defect. Do not attach `verifyNoMoreInteractions` to every mock just to forbid unforeseen calls; that couples tests to structure outside the contract.

**Total runnable tests:** `PriceCalculatorTest` has 6 invocations and `OrderServiceTest` has 3 invocations, totaling **9 invocations** expected to pass with the files above. With no `System.out.println`, there is **no business stdout**. If any test fails, read the stack trace and HTML/XML reports rather than expecting nine “PASS” lines on stdout.

### 5.5. Running with the Gradle Wrapper

When the project includes `gradlew`, `gradlew.bat`, and `gradle/wrapper/...`, from the root directory:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run a single class:

~~~bash
./gradlew test --tests 'com.example.testing.OrderServiceTest'
~~~

Gradle Java test reports are normally generated under `build/reports/tests/test/index.html` and `build/test-results/test/`. In multi-project builds, look inside the `build` folder of the executed module. If a task reports `UP-TO-DATE` or `FROM-CACHE`, it may reuse prior results; to force re-execution while investigating, run `./gradlew test --rerun-tasks`.

In a **Spring Boot module that already includes testing dependencies**, you normally do not declare standalone JUnit/Mockito versions when `spring-boot-starter-test` supplies them. Keep `useJUnitPlatform()` on the Gradle test task and let the Spring Boot BOM/dependency management coordinate compatible versions. The corresponding configuration typically looks like:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

This is a **snippet for integrating into a `build.gradle` that already applies the Spring Boot plugin and dependency management**, not a standalone project file. For the runnable example above, use the **full `build.gradle` in Section 5.1**.

## 6. Refactorings Should Keep Tests Green; Behavioral Bugs Must Turn Them Red

A good test balances **sensitivity to business bugs** with **resilience across valid refactorings**. You can evaluate this mentally or on a scratch branch by introducing deliberate mutations:

| Hypothetical change | Desired outcome | Which test should catch it? |
| --- | --- | --- |
| Change `Math.multiplyExact` to addition | **Fail**: 2 × 120 is no longer 240 | `PriceCalculatorTest` and `OrderServiceTest` |
| Remove `repository.save(order)` | **Fail**: order persistence requirement lost | `OrderServiceTest` via `verify(save)` |
| Save an order with an amount differing from the returned order | **Fail**: wrong payload saved | Captor and order comparison |
| Remove invalid-quantity check | **Fail**: invalid input could be saved | Validation tests and `verifyNoInteractions` |
| Rename helpers or split/merge calculation steps while keeping results identical | **Pass** | Tests should not mandate helper call counts |
| Switch repository implementation from JPA to an equivalent adapter | **Pass in service unit tests** | Service contract does not depend on SQL |
| Break JPA mapping or unique constraint | **Fail in persistence integration tests** | Mocked repo cannot detect this directly |

This table describes **the goals of the test suite**, not mutations claimed to have been executed on this workspace. In practice, you can temporarily introduce a small fault in the SUT, confirm the right test fails, and revert it—a manual check of your assertions' bug-catching power.

### Mutation Testing Is a Complementary Tool, Not the Sole Metric

Mutation testing mutates operators, conditions, or statements in production code to check whether tests “kill” each mutant. If changing `<=` to `<` on a boundary leaves tests green, boundary test cases may be missing. Still, not every surviving mutant represents a real bug: code may be semantically equivalent, or the mutant may sit outside the scope of that test's contract. Focus on mutants reflecting rules worth protecting.

## 7. When Verifying Interactions Is Right vs. Unnecessary

**Meaningful `verify`:** when an external effect is part of the published behavior:

- Send only one charge request per transaction to avoid double billing.
- Do not send emails when an address is invalid or consent is missing.
- Do not persist records when validation fails.
- Publish a business event with the right ID/payload when an order is created.
- Use the authorized partner/tenant context per security contract.

**Brittle `verify`:** when locked onto implementation mechanics:

- `verify(mapper).toDto(entity)` when callers only care about the right JSON response.
- `verify(service, times(1)).privateLikeHelper(...)` merely because code currently factors a helper that way.
- `verifyNoMoreInteractions` on every mock in a test with no real “forbid extra interactions” rule.
- `InOrder` across pure-computation collaborators whose order does not alter results.

Do not conclude **all `verify` calls are over-mocking**. Instead ask: “If this call were skipped or altered while other outputs stayed right, would the contract be violated?” If yes, verifying it makes sense. If not, asserting observable outputs is usually enough.

### `times(1)`, `never`, `verifyNoInteractions`, and `verifyNoMoreInteractions`

`verify(repository).save(order)` defaults to **exactly once** for that matching call; `verify(repository, times(1)).save(order)` states the same count explicitly when cardinality is a requirement. `verify(repository, never()).save(any())` verifies `save` was not called with any matching argument; `verifyNoInteractions(repository)` is stricter, requiring **zero interactions of any kind** on that mock. If the repository legitimately performs a read check before validation, `verifyNoInteractions` can be too strict; choose `never().save(any())` when the contract only forbids saving.

`verifyNoMoreInteractions(repository)` checks that **no other unverified interactions** occurred. Use it only when side-effect policy genuinely demands it; it should rarely be the default assertion in every unit test. Avoid making “mock cleanliness” a goal above business accuracy.

## 8. MockMvc and Spring Boot: How Deep Should You Mock?

A Spring Boot project spans multiple testing layers:

| Layer | Keep real | Can fake/mock | Question answered |
| --- | --- | --- | --- |
| **Domain unit** | Pure Java policies, calculators, validators | Usually no mocks needed | Are the business rules right? |
| **Service unit** | Service + pure collaborators under test | Repositories, HTTP clients, email gateways | What does the use case return and request externally? |
| **MVC slice (`@WebMvcTest`)** | Controller, binding, validation, serialization, HTTP mapping | Dependencies below the controller as appropriate | Does the API map requests/responses accurately? |
| **Integration (`@SpringBootTest`, `@DataJpaTest` where appropriate)** | Real beans/infrastructure needing proof | Only out-of-scope external boundaries | Do layers collaborate, persist/read, and handle transactions properly? |

For example, a `@WebMvcTest` mocking a service to return a canned JSON DTO proves **the controller serializes and maps HTTP properly**, even though it does not prove the service calculates amounts properly. That is completely fine when the test's scope is the HTTP contract. Pair it with domain/service unit tests for business rules, and integration tests across layers wherever integration bugs pose high risk.

Conversely, using `@SpringBootTest` for simple arithmetic boots an expensive Spring context and drags in unneeded infrastructure. Place tests at the right level so **every major risk class has a clear place to fail**, without repeating identical scenarios needlessly across every layer.

### Mocking a Repository Differs from Verifying Persistence

In the example, `verify(repository).save(order)` checks **intent to call the save port**. It **does not prove**:

- Entities map accurately to JPA tables and columns.
- Database constraints and transactions behave properly.
- Data actually commits and can be queried back.
- Adapter layers translate DB failures into the right business exceptions.

Those belong to adapter integration tests or use-case flows against an isolated test database. In-memory fakes speed up use-case tests, yet cannot replace real DB tests wherever SQL or JPA behavior is required.

## 9. Designing Expected Values Independently of Implementation

A **test oracle** is the basis for deciding “what outcome is right.” Good oracles come from one or more sources:

1. **Concrete business examples:** “2 items × 120 = 240”, “orders from 500 upward get free shipping.”
2. **API contracts:** HTTP status codes, JSON schemas, required fields, validation errors.
3. **Invariants:** non-negative totals, totals equal sum of line items, idempotency, no duplicate charges.
4. **Independent properties:** under normal pricing rules, increasing quantity must not reduce total; invalid orders must never be saved.
5. **Vetted reference data:** boundary case tables agreed upon by the team and versioned with tests.

An expected value copied straight from production logic **is not an independent oracle**. For instance, computing expected values with the same `PriceCalculator` that `OrderService` uses can verify wiring consistency between the two, yet fails to prove the amount itself is right. That may check orchestration, whereas proving “the amount is right” demands concrete examples or independent invariants.

### Boundaries and Counter-Examples

For the “500 or more” rule, test `499`, `500`, and `501`. Edge cases catch bugs that a “typical order of 1,000” misses. For `int` multiplication, testing `Integer.MAX_VALUE × 2` catches overflow missed by small numbers. For “never save invalid orders,” testing zero/negative inputs alongside `verifyNoInteractions` catches misplaced validation order.

Large input volumes do not equal strong coverage. A compact test suite covering **rules, boundaries, and error paths** beats hundreds of lines whose expectations duplicate the implementation.

## 10. Common Mockito Pitfalls and Remedies

| Symptom | Cause | Improvement |
| --- | --- | --- |
| Test passes despite broken domain logic | Calculator/validator was mocked | Run real domain logic in at least one test layer |
| Tests break whenever renaming helpers or splitting methods | Internal calls verified too tightly | Assert contract outputs and external effects |
| Very long tests with dozens of `when` calls | Mocking entire chains the test does not need | Trim fixtures; use real objects or focused fakes |
| `UnnecessaryStubbingException` | Mockito strict stubbing caught an unused stub | Delete the redundant stub; use `lenient` only intentionally rather than disabling checks globally |
| Unexpected stubbing triggers `PotentialStubbingProblem` | Stub arguments mismatch actual call under strict stubbing | Inspect real data/path; adjust stub or use right argument matchers |
| `Wanted but not invoked` | Call never occurred or SUT used another instance | Confirm SUT received the mock via constructor and contract requires the call |
| `verifyNoMoreInteractions` fails after valid refactoring | Test forbade calls outside the contract | Remove excess assertion or narrow it to prohibited side effects |
| `@Mock`/`@InjectMocks` uninitialized | Missing Mockito Jupiter extension or setup | Add `@ExtendWith(MockitoExtension.class)` and proper dependency |
| `NullPointerException` from collaborator | SUT received null dependency or uninjected field | Prefer constructor injection and explicit SUT construction |
| `when(spy.method())` runs real method during stubbing | Spies execute real methods in that stubbing style | Use `doReturn(...).when(spy).method()` when spies are genuinely needed; minimize partial mocks |
| Test mocks repository yet assumes SQL is tested | Mocks never execute real persistence | Add repository/adapter integration tests against a real DB |
| Flaky tests due to time/randomness/network | Uncontrolled external dependencies | Use `Clock.fixed`, deterministic seeds, fakes/mocks at external gateways, independent fixtures |
| Expected values generated by the SUT itself | Oracle coupled to implementation | Use specs, case tables, invariants, or independent oracles |
| Test asserts only the exception without checking side effects | Buggy code may persist data before throwing | Combine `assertThrows` with “never saved” checks when required |

### Is `@InjectMocks` Bad?

No. `@InjectMocks` can instantiate the SUT and wire declared mocks, which is handy for classes with several dependencies. Still, when clarity matters about which dependencies run for real, **explicit constructor injection** as in the example is easier to read. If a test needs four mocks and two are unused in a test case, ask whether the service holds too many responsibilities or the test fixture is too broad.

### Should You Use Spies?

Spies execute real behavior except where stubbed. They help occasionally when overriding one collaborator behavior that cannot yet be extracted, though they tend to couple tests to implementation internals. Never spy on a service just to prove “method A called method B” when the user-facing contract is the final outcome. Prefer extracting real dependencies behind clear contracts and asserting outputs/effects.

### Should You Mock Static Methods or Constructors?

Mockito supports scoped static/construction mocking, yet heavy reliance on them often hides implicit dependencies in design. For clocks, UUIDs, external APIs, or factories, consider **dependency injection** or controllable standard types like `Clock.fixed(...)`. Reserve static mocking for legacy code that cannot reasonably be isolated, keeping scopes tight.

## 11. Checklist for Reviewing Mockito Tests

Before merging a new test, ask:

1. **What is the real SUT?** Does the test actually run the logic its name claims to test, or was that logic mocked out?
2. **Which contract is protected?** State the return value, exception, state change, payload/event, or allowed/forbidden side effects.
3. **Where do expected values come from?** Are they from business specs or independent invariants rather than copied from production formulas?
4. **Which mocks are truly needed?** Repositories, network, email, clocks, randomness—or only pure Java helpers?
5. **Why is each `verify` valuable?** If an internal call changed while external results remained correct, should the test still pass?
6. **If I introduce a bug, does a test fail?** Try dropping `save`, changing multiplication, skipping validation, or altering payloads.
7. **Across valid refactorings, does the test stay green?** Renaming helpers, extracting mappers, restructuring internals without changing contracts.
8. **What can mocks not verify?** Are integration tests needed for persistence, HTTP mapping, transactions, or external protocols?
9. **Is the test isolated and clear?** No order dependence, shared mock state, uncontrolled randomness, or real networks.
10. **Do failure messages point to the broken rule?** Test names and assertions should highlight meaningful inputs and expected outcomes.

### Practice Exercises

**Exercise A — Reviewing a mock-heavy test:** Pick a test with multiple `@Mock` fields. Classify each mock as pure domain, I/O port, or internal helper. Replace one pure dependency with a real object, trim unused stubs, and keep meaningful assertions intact.

**Exercise B — Checking boundaries:** In Section 5's example, temporarily delete `repository.save(order)`. Expect `placeReturnsCorrectOrderAndRequestsPersistence` to fail at `verify`, while `PriceCalculatorTest` keeps passing. Revert afterward. This demonstrates each test protects its own contract.

**Exercise C — Catching logic bugs:** Temporarily replace `Math.multiplyExact(quantity, unitPrice)` with `quantity + unitPrice`. Expect the pricing test to fail; if the test had mocked the calculator to return 240, it would **miss** the bug completely. Revert.

**Exercise D — Boundary tests:** Change `quantity <= 0` to `quantity < 0`. Expect the `quantity=0` case to fail. If tests only checked `quantity=2`, this boundary bug would slip through.

**Exercise E — Spotting integration gaps:** Suppose the output port connects to a real `JpaRepository`. Propose at least one integration test that saves and reads back to catch mapping/constraint bugs Mockito cannot observe, and distinguish unit test results from real DB evidence.

**Key takeaway:** Limit mocks to collaborators tests must control or whose contract interactions must be observed. Keep business logic running for real; choose expected values independently of implementations; and judge tests by their ability to **fail when behavior breaks and survive valid refactorings**. A trustworthy test suite combines complementary evidence at the right boundaries, not a set of `verify` calls mirroring the production code line for line.
