# Naming Test Cases by Scenario and Expected Outcome

## 1. A Test Name Is a Short Specification of the Behavior Being Proven

In a Spring Boot project, test names appear in source code, JUnit result trees, CI logs, and failure reports. A good name tells the reader **what state or situation the system is in**, **what action is performed**, and **what must happen**, even before opening the test body.

Examples:

- `test1()`: unclear which feature is tested.
- `testReserve()`: shows the operation, but neither the scenario nor the expected outcome.
- `reserve_whenStockIsSufficient_decreasesStockAndReturnsTrue()`: clearly states the `reserve` action, the sufficient-stock condition, and the expected outcome.
- `reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock()`: clearly shows rejection behavior and data preservation.

A test name should act as a **verifiable behavior specification**: when the test fails, readers recognize which rule broke without guessing.

The goal is not cramming every statement or assertion into the method name. Highlight the **distinguishing condition** and the **most important business outcome**. When more context helps, use `@DisplayName`, `@Nested` group names, parameterized test formatting, or test documentation.

## 2. Naming Formula: Scenario + Action + Expected Outcome

A test case generally has three parts: Given/Arrange (initial condition), When/Act (action), and Then/Assert (expected outcome). Test names reflect these parts concisely.

Two common patterns, both valid:

1. **`<action>_when<Scenario>_<ExpectedResult>`** — for example `reserve_whenQuantityExceedsStock_returnsFalse`.
2. **`should<ExpectedResult>_when<Scenario>`** — for example `shouldRejectReservation_whenStockIsInsufficient`. The action is sometimes implied by the test class name or context.

If a team prefers Given–When–Then order, you can use `given<Context>_when<Action>_then<Outcome>`, such as `givenNoStock_whenReservingOne_thenReturnsFalse`. This pattern is explicit but can grow long; use it when rich context genuinely improves clarity.

| Component | Question to Answer | Example |
| --- | --- | --- |
| **Scenario** | What specific data/state/condition defines this case? | `whenStockIsInsufficient` |
| **Action** | Which method, endpoint, or behavior is exercised? | `reserve` |
| **Expected outcome** | What does the system return, mutate, or preserve? | `returnsFalseWithoutChangingStock` |

A name like `reserve_whenStockIsInsufficient` states only the scenario; adding the outcome distinguishes whether the system rejects, throws, or queues. Conversely, `reserve_returnsFalse` lacks the scenario and does not explain **when** returning `false` is correct.

**Crucial rule:** the name must match the contract verified by assertions. If the name claims “without changing stock,” the test body must assert the stock count afterward; if the name says “throws exception,” the test must assert the expected exception.

## 3. From Business Rules to a List of Test Names

Suppose an inventory service has this requirement:

> Reserve a positive quantity. If stock is sufficient, accept and deduct stock; if stock is insufficient, reject without deducting stock; zero or negative quantity is invalid input.

From this rule, separate independent scenarios:

| ID | Pre-action Situation | Action | Expected Outcome | Meaningful Test Name |
| --- | --- | --- | --- | --- |
| TC-01 | 5 in stock, reserve 2 | `reserve(2)` | Returns `true`, 3 left | `reserve_whenStockIsSufficient_returnsTrueAndDecreasesStock` |
| TC-02 | 1 in stock, reserve 2 | `reserve(2)` | Returns `false`, still 1 left | `reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock` |
| TC-03 | 2 in stock, reserve exact 2 | `reserve(2)` | Returns `true`, 0 left | `reserve_whenQuantityEqualsStock_depletesStock` |
| TC-04 | 5 in stock, request 0 | `reserve(0)` | Throws `IllegalArgumentException`, still 5 left | `reserve_whenQuantityIsZero_throwsIllegalArgumentException` |
| TC-05 | 5 in stock, request negative | `reserve(-1)` | Throws `IllegalArgumentException`, still 5 left | `reserve_whenQuantityIsNegative_throwsIllegalArgumentException` |

Each name emphasizes a **triggering condition** and **what must hold afterward**. Avoid naming every happy case `reserve_success()`, because “normal sufficient stock” and “quantity matching exact remaining stock” exercise different boundary behaviors.

When names grow too long, highlight one representative outcome in the name and keep related assertions in the body; for instance, `reserve_whenQuantityEqualsStock_depletesStock` can still assert the return value is `true`. You only need enough specificity to **locate the broken behavior**.

## 4. Complete Java 17 + JUnit 5 Example in a Spring Boot Project

Assume a Spring Boot project using Java 17+, Spring Boot Starter Test, and JUnit Jupiter. The service class below is self-contained business logic to illustrate scenario/outcome naming. This is a **unit test**; there is no need to start a full Spring `ApplicationContext` just to test plain Java logic.

**File `src/main/java/com/example/testing/StockReservationService.java`:**

~~~java
package com.example.testing;

public final class StockReservationService {
    private int availableStock;

    public StockReservationService(int initialStock) {
        if (initialStock < 0) {
            throw new IllegalArgumentException("Initial stock must be non-negative");
        }
        this.availableStock = initialStock;
    }

    public boolean reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (quantity > availableStock) {
            return false;
        }
        availableStock -= quantity;
        return true;
    }

    public int availableStock() {
        return availableStock;
    }
}
~~~

The contract of `reserve` is explicit: invalid quantities throw an exception; insufficient stock returns `false`; sufficient stock returns `true` and deducts inventory. The test names below follow that contract.

**File `src/test/java/com/example/testing/StockReservationServiceTest.java`:**

~~~java
package com.example.testing;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StockReservationServiceTest {

    @Test
    @DisplayName("Sufficient stock: reserves successfully and decreases remaining quantity")
    void reserve_whenStockIsSufficient_returnsTrueAndDecreasesStock() {
        // Given
        StockReservationService service = new StockReservationService(5);

        // When
        boolean accepted = service.reserve(2);

        // Then
        assertTrue(accepted);
        assertEquals(3, service.availableStock());
    }

    @Test
    @DisplayName("Insufficient stock: rejects reservation and keeps stock unchanged")
    void reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock() {
        StockReservationService service = new StockReservationService(1);

        boolean accepted = service.reserve(2);

        assertFalse(accepted);
        assertEquals(1, service.availableStock());
    }

    @Test
    @DisplayName("Exact remaining quantity: depletes stock after reservation")
    void reserve_whenQuantityEqualsStock_depletesStock() {
        StockReservationService service = new StockReservationService(2);

        boolean accepted = service.reserve(2);

        assertTrue(accepted);
        assertEquals(0, service.availableStock());
    }

    @Test
    @DisplayName("Zero quantity: throws error and does not decrease stock")
    void reserve_whenQuantityIsZero_throwsIllegalArgumentException() {
        StockReservationService service = new StockReservationService(5);

        assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve(0)
        );
        assertEquals(5, service.availableStock());
    }
}
~~~

Test methods are named after behavior. The `@DisplayName` annotation adds a readable natural-language sentence in JUnit reports; Java method names still support IDE search and navigation. For instance, when `reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock` fails, readers immediately know to inspect **insufficient stock without modifying inventory**.

In a Gradle Spring Boot project with plugins and repositories configured, ensure the test dependency and test runner are set up in `build.gradle` (Groovy syntax):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

From the project directory with Gradle Wrapper, run:

~~~bash
./gradlew test --tests "com.example.testing.StockReservationServiceTest"
~~~

On Windows, run `gradlew.bat test --tests "com.example.testing.StockReservationServiceTest"`. If all assertions pass, Gradle reports the test task as successful; exact log output varies by Gradle version and project configuration, so do not rely on a fixed stdout string.

**Scope note:** the Java/JUnit example above runs in a project with JUnit 5 dependencies configured; running `javac` alone cannot compile the test class without JUnit on the classpath. The service itself uses only Java 17. Use `@SpringBootTest` or slice tests like `@WebMvcTest` when a Spring context is genuinely needed; the scenario-and-outcome naming approach remains the same.

## 5. Naming Multiple Datasets with Parameterized Tests

When **the same rule** is checked across multiple datasets, `@ParameterizedTest` avoids duplicating test bodies. The method name states the overall rule; each invocation's display name can surface the input values and expected conclusion in reports.

Example adding one method to `StockReservationServiceTest` above, importing `org.junit.jupiter.params.ParameterizedTest` and `org.junit.jupiter.params.provider.CsvSource`:

~~~java
@ParameterizedTest(
        name = "[{index}] Stock {0}, reserve {1}: rejects and keeps stock unchanged"
)
@CsvSource({
        "0, 1",
        "1, 2",
        "3, 4"
})
void reserve_whenRequestedQuantityExceedsStock_returnsFalseWithoutChangingStock(
        int initialStock,
        int quantity
) {
    StockReservationService service = new StockReservationService(initialStock);

    boolean accepted = service.reserve(quantity);

    assertFalse(accepted);
    assertEquals(initialStock, service.availableStock());
}
~~~

This is an **addition to the test class**, not a standalone Java file. Each `@CsvSource` line generates one invocation. Placeholder `{index}` is the invocation index, while `{0}` and `{1}` are parameter values formatted by JUnit into the display name—for example, “Stock 1, reserve 2: rejects and keeps stock unchanged”.

Do not lump cases with different outcomes or exceptions under one vague name. Quantity `0` throwing an exception is a different behavior from quantity exceeding stock returning `false`; give them distinct test names or datasets.

## 6. Naming HTTP and Spring Boot Tests

Service tests and HTTP tests have **different observation boundaries**. Test names should reflect the contract owned by that layer:

| HTTP Scenario | Expected Outcome | Suggested Name |
| --- | --- | --- |
| Request to fetch record with existing ID | HTTP 200 and matching payload | `getItem_whenIdExists_returns200WithItem` |
| ID does not exist | HTTP 404 | `getItem_whenIdDoesNotExist_returns404` |
| JSON body misses required field and fails validation | HTTP 400, no data created | `createItem_whenRequiredFieldIsMissing_returns400` |
| Unauthenticated user calls protected resource | HTTP 401 per security configuration | `getProfile_whenUnauthenticated_returns401` |
| Authenticated user lacks permission | HTTP 403 per active policy | `deleteItem_whenPermissionIsMissing_returns403` |

These names are **suggested patterns under assumed contracts**. Actual 401/403 codes, validation status codes, and payloads must match your Spring Security setup, controller advice, and real system requirements; never assume every application returns identical codes in all cases.

For example, with MockMvc, a test method might be named `getItem_whenIdDoesNotExist_returns404`; the body must hit the endpoint when the ID is absent and assert `status().isNotFound()`. If a dependency must be stubbed/mocked, set up the “not found” state properly in Arrange. A test name never creates initial conditions in place of real test data.

For integration tests, names should describe externally observable behavior or durable state: `createOrder_whenRequestIsValid_persistsOrderAndReturns201`. Only include “persists” if the test genuinely verifies persisted state rather than mocking `repository.save(...)` and assuming it hit the database.

## 7. Method Names and Display Names in Reports

JUnit Jupiter supports two levels of description:

- **Test method name:** a stable identifier in source code, e.g., `reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock`. Follow your team's consistent convention—typically ASCII English—for easy searching, filtering, and tooling compatibility.
- **`@DisplayName`:** a human-readable string in test reports; it can use natural prose (even non-ASCII characters), such as “Insufficient stock → rejects reservation and keeps stock unchanged”. It does not replace assertions and never turns two distinct behaviors into one case.

When many related tests exist, `@Nested` can group scenarios by feature or context—such as `@DisplayName("When reserving stock")` on the group, with child tests titled “Sufficient stock…” or “Insufficient stock…”. Even when the group establishes the action, each test name still needs its own **scenario and outcome**, so single-test runs and failure logs remain clear.

Both names do not need to be word-for-word duplicates. Keep the Java method name crisp for developers and `@DisplayName` natural for report readers.

## 8. Choosing the Right Level of Detail

Names should highlight the **distinguishing condition**, not dump the entire fixture or every setup step.

**Too vague:**

- `testService()`: reveals neither the feature, scenario, nor expectation.
- `reserve_shouldWork()`: “work” is not a measurable outcome.
- `createOrder_returnsSuccess()`: “success” omits the specific state or condition.
- `testException()`: does not specify what triggers the error or which exception type is expected.

**More specific and useful:**

- `reserve_whenStockIsSufficient_decreasesStock`.
- `reserve_whenQuantityIsZero_throwsIllegalArgumentException`.
- `createOrder_whenRequestIsValid_returns201WithOrderId`.
- `authenticate_whenPasswordIsIncorrect_rejectsCredentials`.

**Too coupled to implementation details:** `reserve_whenStockIsInsufficient_callsRepositoryFindByIdTwice`. Unless the repository call count is itself a contractual requirement, this describes internal mechanics rather than business rules. Code optimizations can break the test even when external behavior stays correct.

**Too noisy:** names listing ten data fields, every mock setup, and every assertion step. Move those details into Arrange and assertions, or leverage display names, test datasets, and nested groups. A long name is worth keeping only when every segment distinguishes a crucial rule.

Method names must be updated when the contract or expected outcome changes. If insufficient stock previously returned `false` and a new requirement mandates throwing `InsufficientStockException`, do not keep `returnsFalse` while editing only the assertion; update the name so the test suite never lies.

## 9. Common Test Naming Mistakes

1. **Sequential or historical names:** `test2()`, `newTest()`, `fixBug()`. Rename to the concrete behavior; put ticket IDs in comments or report metadata.
2. **Stating only the feature:** `calculateTotal()`. Add the scenario and outcome, such as `calculateTotal_whenCartIsEmpty_returnsZero`.
3. **Stating only the condition:** `whenUserHasNoPermission()`. Specify how the system rejects it, e.g., `deleteItem_whenPermissionIsMissing_returns403`.
4. **Stating only the outcome:** `shouldThrowException()`. Specify the error trigger and exact exception type.
5. **Name and assertions contradict:** named “doesNotModifyBalance” without checking the balance. Keep the name synchronized with what is actually verified.
6. **Hiding multiple independent cases in one test:** named “success” while testing success, failure, and exceptions in one body. Split by scenario so reports pinpoint which case failed.
7. **Coupling names to fragile technical details:** naming after mocks, internal call order, or non-contractual persistence internals. Name after externally observable outcomes instead.
8. **Inconsistency across teams:** one place uses `testSomething`, another uses `should...When...`, another uses `given...when...then...`. Standardize one primary pattern per module/team, while valuing readability over rigid conformity.

## 10. Practical Naming Workflow Before Coding

**Step 1 — Write a sentence describing the scenario:** “When requested quantity exceeds available stock.”

**Step 2 — Identify the action:** “Call `reserve(quantity)`.”

**Step 3 — Lock down the outcome to assert:** “The system returns `false` and does not deduct stock.”

**Step 4 — Assemble a searchable name:** `reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock`.

**Step 5 — Align with the test body:** Arrange sets stock lower than requested quantity; Act calls `reserve`; Assert verifies both the return value and remaining stock.

**Step 6 — Read the name imagining the test FAILS:** does the name identify the condition and violated contract? If not, refine the missing piece or split the test.

Use this self-check list:

- [ ] Name indicates the tested feature/action or the enclosing group provides clear context.
- [ ] Name specifies **when** the behavior occurs (data, state, permission, boundary, error).
- [ ] Name specifies a concrete, verifiable **expected outcome**.
- [ ] Assertions genuinely verify everything the name promises.
- [ ] Distinct cases have distinct enough names to pinpoint failures in JUnit/CI reports.
- [ ] Name describes stable business behavior, avoiding non-contractual implementation details.
- [ ] Parameterized tests use display names distinguishing individual invocations when helpful.
- [ ] Java method name, display name, and current behavior are consistent.

**Key takeaway:** naming tests by **scenario → action → outcome** turns your test suite into executable behavioral documentation. Readers know what each test proves, and when a test fails they know immediately which rule to investigate.