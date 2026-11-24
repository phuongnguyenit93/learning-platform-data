# AssertJ: Fluent Assertions and Readable Failure Messages

## 1. What is AssertJ used for?

**AssertJ** is an assertion library for Java providing a **fluent** API: start with `assertThat(actual)` and chain meaningful checks such as `isEqualTo(...)`, `containsExactly(...)`, `hasSize(...)`, `isPresent()`, and `hasMessageContaining(...)`. In Spring Boot applications, AssertJ is usually included out of the box via the `spring-boot-starter-test` test dependency.

The goal of an assertion is to turn an observable outcome into a **clear, verifiable contract**: what must be true, for which data, and if it fails, whether the failure message gives enough information to find the root cause. AssertJ stands out in three areas:

1. **Sentence-like readability:** `assertThat(receipt.totalQuantity()).isEqualTo(5)` reads closely to "total quantity must equal 5".
2. **Type-specific assertions:** Strings, numbers, collections, maps, optionals, exceptions, files, dates/times, and more have tailored methods instead of generic boolean checks.
3. **Helpful failure diagnostics:** default messages normally display expected/actual values and diffs; you can add context via `as(...)` or collect multiple violations via soft assertions.

**AssertJ is not a test runner.** JUnit Jupiter is still responsible for discovering and running `@Test` methods, managing test lifecycle, and reporting results; AssertJ provides the assertion calls inside tests. They complement rather than compete with each other.

### 1.1. Quick look at a fluent assertion's structure

```java
assertThat(actual)
    .as("business context description")
    .isNotNull()
    .isEqualTo(expected);
```

This is a **syntax illustration snippet**, not a standalone Java program. Meaning:

- `assertThat(actual)` creates an assertion object tailored to the type of `actual`.
- `as(...)` sets a description shown in the failure message when an assertion fails; it should appear **before** the checks.
- `isNotNull()` checks an important precondition when you want a clear null failure message.
- `isEqualTo(expected)` checks equality; if it fails, AssertJ throws an `AssertionError` and the test is marked failed.

Chained calls typically return the assertion object for further chaining. However, **do not chain long assertions just because you can**: every step should express a valuable condition, and when a failure occurs it must be easy to tell which step failed.

## 2. Setting up AssertJ in a Spring Boot project

In modern Spring Boot projects, the standard test dependency already includes JUnit Jupiter, AssertJ, and related testing tools. Use the version managed by Spring Boot dependency management so libraries remain compatible.

**Gradle (Groovy DSL, relevant part in `build.gradle`):**

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven (dependency section in `pom.xml`):**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

These examples assume the project already has the Spring Boot plugin/parent or appropriate dependency management, along with the necessary repositories. Do not re-add `spring-boot-starter-test` if the project already declares it, and do not pin a custom AssertJ version unless there is a specific need and compatibility has been verified.

In a test class, you typically import:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertSoftly;
```

Distinguish `org.assertj.core.api.Assertions` from `org.junit.jupiter.api.Assertions`. JUnit has methods like `assertEquals(expected, actual)`; AssertJ uses `assertThat(actual).isEqualTo(expected)`, meaning **argument order and style differ**. Do not mix up the `expected`/`actual` order when migrating code from JUnit.

To verify the dependency via the build tool, you can run the Gradle test task or Maven test goal. If the IDE reports `Cannot resolve symbol assertThat`, inspect the test dependency, imports, and build sync instead of manually adding JARs in the IDE.

## 3. Comparing JUnit assertions and AssertJ by intent

Suppose there is a `String` variable `actualName` returned by the code under test.

| Intent | JUnit Jupiter | AssertJ |
|---|---|---|
| Equality | `assertEquals("Alice", actualName)` | `assertThat(actualName).isEqualTo("Alice")` |
| Not null | `assertNotNull(actualName)` | `assertThat(actualName).isNotNull()` |
| Contains substring | `assertTrue(actualName.contains("lic"))` | `assertThat(actualName).contains("lic")` |
| Ordered list | `assertIterableEquals(expected, actual)` | `assertThat(actual).containsExactly("A", "B")` |
| Exception | `assertThrows(IllegalArgumentException.class, action)` | `assertThatThrownBy(action).isInstanceOf(IllegalArgumentException.class)` |

Some comparisons are only equivalent for **specific data types and value sets**. For example, `assertIterableEquals` and `containsExactly` both check order, yet their failure messages and overloads differ. Choose assertions based on the contract you actually need to prove, not the shortest line count.

**Anti-pattern:**

```java
assertThat(users.size() > 0).isTrue();
```

If it fails, you mostly see a boolean `false`. A better test writes:

```java
assertThat(users)
    .as("user list returned by the service")
    .isNotEmpty();
```

Here AssertJ knows the subject is a collection and provides a failure message directly tied to the collection and the condition checked.

## 4. Runnable example: a small service and JUnit Jupiter test suite using AssertJ

This example uses **Java 17+** and does not require booting a Spring context. The service creates a receipt containing an ID, line items, and total quantity. The lesson focuses on assertions without mocks, databases, or networking obscuring the technique.

### 4.1. Production code

Create **`src/main/java/com/example/testing/assertj/ReceiptService.java`**:

```java
package com.example.testing.assertj;

import java.util.List;
import java.util.Objects;

public final class ReceiptService {

    public record Item(String sku, int quantity) {}

    public record Receipt(
            String id,
            List<Item> items,
            int totalQuantity
    ) {}

    public Receipt create(String rawId, List<Item> items) {
        if (rawId == null || rawId.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException("items must not be empty");
        }

        int total = 0;
        for (Item item : items) {
            Objects.requireNonNull(item, "item");
            if (item.sku() == null || item.sku().isBlank()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (item.quantity() <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            total = Math.addExact(total, item.quantity());
        }

        return new Receipt(rawId.trim(), List.copyOf(items), total);
    }
}
```

Service behavior:

- Receipt ID must not be null/blank and is trimmed.
- Line items list must not be null/empty; SKU must not be blank, and quantity must be positive.
- `Math.addExact` throws `ArithmeticException` if summing overflows `int`.
- `List.copyOf` stores a structurally immutable copy of the item list.
- Java `record` provides component-based `equals/hashCode`: suitable for illustrating value vs. reference equality.

### 4.2. Test suite with readable assertions

Create **`src/test/java/com/example/testing/assertj/ReceiptServiceTest.java`**:

```java
package com.example.testing.assertj;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;

import com.example.testing.assertj.ReceiptService.Item;
import com.example.testing.assertj.ReceiptService.Receipt;

import static org.assertj.core.api.Assertions.assertSoftly;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.within;

class ReceiptServiceTest {
    private final ReceiptService service = new ReceiptService();

    private Receipt sample() {
        return service.create(" R-01 ", List.of(
                new Item("BOOK", 2),
                new Item("PEN", 3)
        ));
    }

    @Test
    void createsReceiptWithFluentAssertions() {
        Receipt receipt = sample();

        assertThat(receipt.id())
                .as("normalized receipt id")
                .isEqualTo("R-01");

        assertThat(receipt.totalQuantity())
                .as("total quantity of receipt %s", receipt.id())
                .isEqualTo(5)
                .isPositive();
    }

    @Test
    void preservesLineOrderWhenRequired() {
        Receipt receipt = sample();

        assertThat(receipt.items())
                .as("line items of receipt %s", receipt.id())
                .hasSize(2)
                .extracting(Item::sku)
                .containsExactly("BOOK", "PEN");
    }

    @Test
    void comparesWithoutOrderWhenOrderIsNotPartOfContract() {
        assertThat(sample().items())
                .extracting(Item::quantity)
                .containsExactlyInAnyOrder(3, 2);
    }

    @Test
    void recordsProvideValueEquality() {
        Receipt expected = new Receipt(
                "R-01",
                List.of(new Item("BOOK", 2), new Item("PEN", 3)),
                5
        );

        assertThat(sample()).isEqualTo(expected);
    }

    @Test
    void checksExceptionTypeAndMessage() {
        assertThatThrownBy(() -> service.create(
                "   ",
                List.of(new Item("BOOK", 1))
        ))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("id must not be blank");
    }

    @Test
    void checksCodeThatShouldNotThrow() {
        assertThatCode(() -> service.create(
                "R-02",
                List.of(new Item("PEN", 1))
        )).doesNotThrowAnyException();
    }

    @Test
    void collectsRelatedChecksWithSoftAssertions() {
        Receipt receipt = sample();

        assertSoftly(softly -> {
            softly.assertThat(receipt.id())
                    .as("receipt id")
                    .isEqualTo("R-01");
            softly.assertThat(receipt.totalQuantity())
                    .as("total quantity")
                    .isEqualTo(5);
            softly.assertThat(receipt.items())
                    .as("line item count")
                    .hasSize(2);
        });
    }

    @Test
    void supportsOptionalDecimalAndTolerance() {
        assertThat(Optional.of("READY")).contains("READY");

        assertThat(new BigDecimal("10.00"))
                .isEqualByComparingTo(new BigDecimal("10.0"));

        assertThat(0.1 + 0.2)
                .isCloseTo(0.3, within(1e-10));
    }
}
```

**How to run** from the project directory (pick the build tool used by your project):

```bash
# Gradle Wrapper: run only this test class
./gradlew test --tests "com.example.testing.assertj.ReceiptServiceTest"

# Maven Wrapper: same test class with Surefire
./mvnw -Dtest=ReceiptServiceTest test
```

On Windows PowerShell, use `.\gradlew.bat test --tests "com.example.testing.assertj.ReceiptServiceTest"` or `.\mvnw.cmd "-Dtest=ReceiptServiceTest" test`. The class name and package must match the created files exactly; `ReceiptServiceTest` requires JUnit Jupiter on the test runtime classpath.

**Expectation:** the class has **8 `@Test` methods**, and all 8 pass when placed in a Java 17+ project with matching dependencies and configuration. The tests do not write to stdout intentionally. Console output and summary formatting depend on Gradle/Maven/JUnit versions, so do not assert a fixed log line. To inspect reports, Gradle typically generates `build/reports/tests/test/index.html`, and Maven Surefire typically generates `target/surefire-reports/`.

### 4.3. Reading the meaning of each test

- `createsReceiptWithFluentAssertions` uses `as(...)` to state **which property** is checked; on failure, you see the receipt context plus expected/actual.
- `preservesLineOrderWhenRequired` uses `extracting(Item::sku)` to verify exact SKU ordering rather than asserting the whole object and struggling to spot which field failed.
- `comparesWithoutOrderWhenOrderIsNotPartOfContract` uses `containsExactlyInAnyOrder`, because only the values and occurrence counts matter; it does not impose artificial ordering.
- `recordsProvideValueEquality` leverages record equality; if `Receipt` were replaced with a class not overriding `equals`, `isEqualTo` could behave differently.
- `checksExceptionTypeAndMessage` captures the invalid-input contract: not only "it throws", but also the exact type and public message.
- `checksCodeThatShouldNotThrow` is suitable for proving non-throwing behavior; when you need to check a **returned value**, it is better to capture the return value and assert on it as in the earlier tests.
- `collectsRelatedChecksWithSoftAssertions` reports multiple violations in a single pass when checks are mutually independent.
- `supportsOptionalDecimalAndTolerance` demonstrates type-specific assertions and how to avoid floating-point comparison pitfalls.

## 5. Writing fluent assertions aligned with the business contract

### 5.1. Choose type-specific assertions

Do not turn every outcome into a boolean to assert. Examples using variables already declared in a test:

```java
assertThat(name).startsWith("A").endsWith("Z");
assertThat(amount).isPositive().isLessThan(100);
assertThat(items).isNotEmpty().hasSize(3);
assertThat(statusById).containsEntry("R-01", "PAID");
assertThat(maybeId).contains("R-01");
```

These are **illustrative snippets**, not a standalone program; they assume `name` is a String, `amount` is a number, `items` is a collection, `statusById` is a map, and `maybeId` is an `Optional<String>`.

These methods express "exactly what must be true". For instance, `containsEntry` states that a key must map to a specific value; `isPositive` means strictly greater than 0; `contains("R-01")` on an `Optional` requires the optional to be present with that exact string.

Avoid redundant assertion chains like `isNotEmpty().hasSize(3)`: `hasSize(3)` already implies non-empty. Only keep `isNotEmpty` if it provides specific documentation or a distinct message in a particular test.

### 5.2. Distinguish equality, identity, and deep comparison

- `isEqualTo(expected)` normally checks equality per the type's semantics, often via `equals`. Records auto-generate `equals` by components.
- `isSameAs(expected)` checks **the exact same object reference**; useful when identity itself is the contract, such as a singleton returned intact.
- `usingRecursiveComparison().isEqualTo(expected)` deeply compares nested fields/objects, useful for DTOs without an appropriate `equals`. Understand and configure collection handling, ignored fields, and comparators as needed.

**Illustrative snippet** assuming `actualReceipt` and `expectedReceipt` exist:

```java
assertThat(actualReceipt)
        .usingRecursiveComparison()
        .isEqualTo(expectedReceipt);
```

Do not treat recursive comparison as the default solution. If you only need to verify `status` and `totalQuantity`, asserting those two fields directly states the contract clearly and is less affected by unrelated new fields. Conversely, when the goal is to verify an entire DTO, deep comparison catches omissions that scattered assertions might miss. Do not ignore `id`, `timestamp`, or critical fields just to make a test pass.

### 5.3. Exact expectations or partial matching?

Suppose an API returns SKU list `["BOOK", "PEN", "RULER"]`. These assertions **mean different things**:

| Assertion | Contract |
|---|---|
| `contains("BOOK", "PEN")` | Contains the listed elements; other elements are still allowed |
| `containsExactly("BOOK", "PEN")` | Exact count and order of those two elements, no extra elements |
| `containsExactlyInAnyOrder("PEN", "BOOK")` | Exact elements and occurrence counts; order not required |
| `containsOnly("BOOK", "PEN")` | Contains only allowed values; does not verify exact duplicate counts |
| `doesNotContain("RULER")` | Only forbids one value, says nothing about whether remaining elements are complete |

Decide whether the business requires **ordering**, **exact value set**, **occurrence counts**, and **no extra data**. Using `contains` for a contract requiring an exact match can let bugs slip through; using `containsExactly` when the database/API does not guarantee order can create flaky tests.

## 6. Making failure messages readable with `as(...)`

### 6.1. Context + expected/actual is the helpful trio

When a test fails, a reader wants to know:

1. **Context:** which object, identifier, request, or condition is being checked.
2. **Expectation:** what the system should return.
3. **Actual value:** what the system returned and where it differed.

AssertJ provides expected/actual and diffs for many assertions; you supply the context using `as("...")`:

```java
assertThat(receipt.totalQuantity())
        .as("total quantity of receipt %s", receipt.id())
        .isEqualTo(5);
```

If total quantity comes back as 4, the failure message includes a description like `"total quantity of receipt R-01"` alongside expected 5 and actual 4; **exact formatting varies by AssertJ, IDE, and test runner version**. Read the runner's diff rather than depending on a fixed rendered string.

### 6.2. Place `as(...)` before the check

**Correct:**

```java
assertThat(receipt.id())
        .as("returned receipt id")
        .startsWith("R-");
```

**Wrong placement for the description:**

```java
assertThat(receipt.id())
        .startsWith("R-")
        .as("returned receipt id");
```

If `startsWith` fails, Java never executes the trailing `as`, so the description never has a chance to appear. Always attach the description right after `assertThat(actual)`, before any check that can fail.

### 6.3. When to use `withFailMessage(...)`?

AssertJ offers custom failure message methods such as `withFailMessage(...)`. It can **replace the default expected/actual-rich message**. Use it only when you genuinely need a custom format and provide all necessary details yourself.

**Preferred option:**

```java
assertThat(total)
        .as("order %s total amount", orderId)
        .isEqualTo(expectedTotal);
```

**Be careful with:**

```java
assertThat(total)
        .withFailMessage("wrong total amount")
        .isEqualTo(expectedTotal);
```

The second pattern can lose comparison details provided by the library. If you want brevity, write concise context using `as`. Never put secrets, tokens, passwords, or sensitive personal data into assertion descriptions or CI logs.

### 6.4. Each assertion check tells one clear story

If a single assertion chain checks ID, status, quantity, buyer name, and expiration date all at once, a failure can obscure the intent of each part. Splitting into short assertions, each with its own appropriate description, is usually easier to maintain:

```java
assertThat(receipt.id())
        .as("receipt id")
        .isEqualTo("R-01");

assertThat(receipt.totalQuantity())
        .as("total quantity")
        .isEqualTo(5);
```

Do not copy a generic `"result should be correct"` message everywhere. Descriptions should add context that the expression alone does not convey, such as order ID, user role, business state, or the parameter that triggered an error branch.

## 7. Collection assertions: reading order and properties accurately

Collections are one of the places where AssertJ shines: you can assert structure instead of writing manual loops and boolean comparisons.

### 7.1. Checking completeness, ordering, and child properties

Suppose `receipt` has type `ReceiptService.Receipt` from the example:

```java
assertThat(receipt.items())
        .as("SKU list of receipt %s", receipt.id())
        .extracting(ReceiptService.Item::sku)
        .containsExactly("BOOK", "PEN");
```

`extracting(...)` transforms a list of objects into a list of field values to inspect. On failure, you immediately see which **SKU** is extra, missing, or out of order, instead of reading an entire object dump.

If ordering is not part of the contract:

```java
assertThat(receipt.items())
        .extracting(ReceiptService.Item::sku)
        .containsExactlyInAnyOrder("PEN", "BOOK");
```

If you only need to guarantee "at least one line has SKU BOOK":

```java
assertThat(receipt.items())
        .extracting(ReceiptService.Item::sku)
        .contains("BOOK");
```

These are three different contracts. Do not pick one unconsciously out of habit.

### 7.2. Filtering and verifying predicates

AssertJ supports filtering an iterable with a predicate and verifying the filtered elements. **Illustrative snippet** from the example:

```java
assertThat(receipt.items())
        .filteredOn(item -> item.quantity() >= 3)
        .extracting(ReceiptService.Item::sku)
        .containsExactly("PEN");

assertThat(receipt.items())
        .allSatisfy(item ->
                assertThat(item.quantity()).isPositive());
```

- `filteredOn` verifies the result set after a filtering rule; use it when the filtering logic itself is what you want to prove.
- `allSatisfy` applies a block of checks to **every** element. For "there must be at least one element", check non-emptiness first: a predicate holds vacuously for every element of an **empty collection** without proving any element exists.
- When you already know the exact elements expected, direct assertions on the list and fields can be simpler than a long filter chain.

### 7.3. Avoid index-based assertions when business rules do not specify an index

If a repository query has no `ORDER BY`, do not rely on an incidental database return order. The test should compare the set of properties:

```java
assertThat(actualIds)
        .containsExactlyInAnyOrder("R-01", "R-02");
```

This assumes `actualIds` is a `List` or `Collection<String>`. If the business requires sorting by creation date or priority, then assert the exact order and ensure the production query/service actually enforces that sorting rule.

## 8. AssertJ for exceptions: type, message, and non-throwing code

Exception testing is not just "this code blew up". It must prove the system **rejects invalid input according to the contract**.

### 8.1. Exception type and message

```java
assertThatThrownBy(() -> service.create(
        "",
        List.of(new ReceiptService.Item("BOOK", 1))
))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessage("id must not be blank");
```

- If the code **does not throw**, this assertion fails.
- If it throws a different type, `isInstanceOf` fails.
- If the type matches but the message differs, `hasMessage` fails.
- When the message includes valid dynamic parts, use `hasMessageContaining("...")` or an appropriate pattern matcher rather than matching the entire fixed string.

Do not use `try/catch` with an empty `catch` or swallow every exception: that can let a test pass even when behavior is wrong. With exception hierarchies, assert the type that belongs to the public contract; avoid locking down implementation details the code is free to change.

### 8.2. Checking the non-throwing path

```java
assertThatCode(() -> service.create(
        "R-02",
        List.of(new ReceiptService.Item("PEN", 1))
))
        .doesNotThrowAnyException();
```

This assertion only proves the code does not throw. If the service returns wrong data without throwing, the test still passes. When a method returns an important value, verify the output too:

```java
ReceiptService.Receipt result = service.create(
        "R-02",
        List.of(new ReceiptService.Item("PEN", 1))
);

assertThat(result.id()).isEqualTo("R-02");
assertThat(result.totalQuantity()).isEqualTo(1);
```

These two snippets illustrate the same theme; **there is no need to include both in a single test** unless doing so adds value—choose whichever matches the contract you want to protect.

## 9. Soft assertions: inspecting multiple related failures in one pass

Standard assertions are **hard assertions**: on the first failing assertion, the test method stops there. When verifying many independent fields on a DTO or large response, seeing only the first field's failure forces multiple edit-and-rerun cycles.

AssertJ provides **soft assertions** to collect failures and report them together:

```java
assertSoftly(softly -> {
    softly.assertThat(receipt.id())
            .as("receipt id")
            .isEqualTo("R-01");

    softly.assertThat(receipt.totalQuantity())
            .as("total quantity")
            .isEqualTo(5);

    softly.assertThat(receipt.items())
            .as("line item count")
            .hasSize(2);
});
```

Variable `receipt` is an instance of `ReceiptService.Receipt` from the example. With `assertSoftly(...)`, the library finalizes and aggregates failures when exiting the lambda, even when multiple assertions failed.

**When useful:** verifying multiple fields of the same outcome after Arrange and Act succeed, where each field can be evaluated independently and you want to see all mismatches in one pass.

**When inappropriate:** a later assertion depends on a precondition checked by an earlier one—for example, `result` might be `null` and you call `result.id()`; a `NullPointerException` interrupts the block before AssertJ can collect subsequent checks. Protect preconditions with hard assertions or design the test so the checked object is guaranteed to exist.

Also avoid using soft assertions to cram multiple **independent behaviors** into one oversized method; a test should still have one cohesive business objective.

## 10. Data types that deserve special care

### 10.1. Optional: present vs. absent value

```java
assertThat(Optional.of("ACTIVE")).contains("ACTIVE");
assertThat(Optional.<String>empty()).isEmpty();
```

`contains("ACTIVE")` on an `Optional` verifies that the optional is present and its value equals the expected string. That differs from `contains("ACT")` on a `String` (which checks substring containment). Always keep the **type of `actual`** in mind when reading the API.

### 10.2. BigDecimal: differing scales

In Java, `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` is `false` because `equals` considers scale; however, `compareTo` considers them numerically equal.

If the contract compares **numeric value**, you can use:

```java
assertThat(new BigDecimal("10.00"))
        .isEqualByComparingTo(new BigDecimal("10.0"));
```

If the business requires a specific scale/representation (for instance, monetary values normalized to two decimal places), assert scale/representation explicitly per the requirement. Do not replace `isEqualTo` with `isEqualByComparingTo` without understanding the contract.

### 10.3. Double/float: binary representation drift

`0.1 + 0.2` does not necessarily equal exact `0.3` as a `double`. For floating-point calculations with allowed error, use a meaningful tolerance:

```java
assertThat(0.1 + 0.2)
        .isCloseTo(0.3, within(1e-10));
```

Requires `import static org.assertj.core.api.Assertions.within`. The `1e-10` threshold here only fits this small example. Real thresholds must come from the business/algorithm's allowed error margin; do not widen tolerances arbitrarily to hide bugs.

For currency requiring exact decimal precision, prefer `BigDecimal` with explicit rounding rules instead of `double` when computing amounts.

### 10.4. String: matching the intended comparison

Common checks include `isEqualTo`, `isBlank`, `contains`, `startsWith`, `endsWith`, and `matches`. Do not use `contains` when the contract requires an exact full-string match; likewise, do not stop at `isNotNull` when an error message must be verified.

Pay attention to Unicode, diacritic normalization, case sensitivity, locale, and whitespace. When normalization is part of the business logic, clarify what is the production code's responsibility versus the test's expectation; do not accidentally trim/lowercase **both actual and expected inside the test** and mask a normalization bug.

### 10.5. Map: keys and values

When checking summary responses or configuration parameters, use `containsEntry(key, value)` to specify expected pairs; `containsKeys(...)` only checks keys without proving values are right. For unordered maps, do not rely on iterator order to compare against a list unless the contract specifies ordering.

## 11. Combining AssertJ with Spring Boot testing

AssertJ does not require a Spring context: it works in **plain Java unit tests**, slice tests, and integration tests. Pick the test scope based on what you need to prove.

### 11.1. Service unit tests: use real objects and fake/mock dependencies when needed

If the target is small business rules, test the service directly like `ReceiptServiceTest` above. Do not add `@SpringBootTest` just to call `assertThat`; booting the context slows tests down and introduces failure modes unrelated to the target logic.

For services with repositories, you can use Mockito to mock the repository to isolate logic. AssertJ still checks the result; Mockito handles setup/interaction verification **when the interaction is part of the contract**. Do not confuse outcome assertions with mock call-count verification: the two verify different aspects.

### 11.2. Web MVC tests: separate the HTTP contract from object assertions

In `@WebMvcTest` with `MockMvc`, `andExpect(status().isOk())` and `jsonPath(...)` are Spring MVC test matchers, not AssertJ. You can still use AssertJ on extracted values:

**Illustrative snippet, depending on the project's controller and MockMvc setup:**

```java
MvcResult result = mockMvc.perform(get("/api/receipts/R-01"))
        .andExpect(status().isOk())
        .andReturn();

assertThat(result.getResponse().getContentType())
        .as("receipt detail endpoint content type")
        .contains("application/json");
```

This snippet is **not standalone to compile/run**: it needs `mockMvc`, Spring MVC static imports, a controller route, and a matching test context. It illustrates intent: use matchers to verify the HTTP contract, and AssertJ for additional contextual assertions. Do not assert only HTTP status 200 and ignore important payload fields.

### 11.3. Data JPA tests: verifying returned data

In a repository integration test, you can write:

```java
assertThat(repository.findByStatus(Status.PAID))
        .extracting(Order::getId)
        .containsExactlyInAnyOrder("R-01", "R-02");
```

This is an **illustrative snippet** assuming the project declares the repository, enum, and entity. Its intent is to verify the set of IDs of records with status `PAID`, without enforcing order when the query specifies none. The test must manage its own test data setup and cleanup/rollback per real transaction rules; AssertJ does not provide database isolation.

### 11.4. Test context: distinguish assertion failures from Spring startup failures

If `@SpringBootTest` reports `Failed to load ApplicationContext`, the context usually failed to initialize so **test assertions never had a chance to run**. Investigate beans, configuration, profiles, or the database first—do not add `as(...)` or tweak assertions to "fix" a startup failure.

## 12. Common mistakes and fixes

| Anti-pattern | Why it is problematic | Better way to write / investigate |
|---|---|---|
| `assertThat(list.isEmpty()).isFalse()` | Failure only shows a boolean | `assertThat(list).isNotEmpty()` |
| `assertThat(actual).contains(expected)` when exact list is needed | Extra elements can slip through | `containsExactly` or `containsExactlyInAnyOrder` |
| Placing `as(...)` after `isEqualTo(...)` | Description never appears if check fails first | Place `as(...)` right after `assertThat(actual)` |
| Replacing all messages with `withFailMessage("wrong")` | Loses expected/actual diff | Prefer `as(...)` and type-specific assertions |
| `assertThat(object).isEqualTo(other)` on a class without value equality | Comparison may fall back to identity | Assert specific fields, define `equals`, or use intentional recursive comparison |
| Asserting whole DTO `toString` | Failures are hard to trace to differing fields | `extracting`, `satisfies`, or appropriate recursive comparison |
| `assertThatThrownBy(...)` with only `isInstanceOf(Exception.class)` | Too broad; unrelated errors still pass | Verify domain exception type and message/code as needed |
| Soft assertions on a possibly null object | May throw NPE mid-block | Hard-assert preconditions or split tests |
| Asserting collection by index when DB does not guarantee order | Flaky when query order changes | `containsExactlyInAnyOrder` or sort per contract |
| Comparing `BigDecimal("10.0")` with `BigDecimal("10.00")` when only numeric equality is needed | Scale makes `equals` false | `isEqualByComparingTo` if contract ignores scale |
| Comparing `double` with exact equality for rounded math | Binary error makes tests fail | `isCloseTo(..., within(tolerance))` |
| Only `doesNotThrowAnyException` for a function with output | Wrong return value still passes | Assert returned value and related side effects |

### 12.1. Rules to avoid "false green" tests

Do not weaken an assertion just to stop failures. For example, if a response must have exactly 3 lines, replacing `hasSize(3)` with `isNotEmpty()` makes the test pass easily while dropping the core contract. If an API must return `PAID`, using `isIn(PAID, DRAFT)` simply because the test fluctuates is a sign that the behavior has not been clarified.

When a test is flaky, inspect fixtures, clocks, databases, execution order, networking, configuration, and asynchronous flows. AssertJ gives better failure messages, but it does not solve test independence or determinism by itself.

### 12.2. "Readable failure messages" does not mean verbose ones

Compare two descriptions:

- `as("test of business logic handling the object, validating the returned result")`: generic and wordy.
- `as("status of order %s after payment", orderId)`: carries business information and a concrete identifier.

Put **the business condition + relevant identifier** into the description, and avoid copying huge inputs. Let the specialized assertion supply the expected/actual values.

## 13. Practice exercises and review checklist

### Exercise 1: replace booleans with type-specific assertions

Given a test snippet with a `List<String> ids`:

```java
assertThat(ids.size() == 2).isTrue();
assertThat(ids.contains("R-01")).isTrue();
```

Rewrite it for two different contracts:

- Must have exactly 2 elements **and** contain `R-01`.
- Must contain exact IDs `R-01`, `R-02` in any order.

**Reference solution** (two alternatives, do not combine them):

```java
assertThat(ids).hasSize(2).contains("R-01");

// If the ID set must be exact and unordered:
assertThat(ids).containsExactlyInAnyOrder("R-01", "R-02");
```

Note: the second condition is stronger; if the exact set is required, there is no need to assert `hasSize(2)` again.

### Exercise 2: improve the failure message

Given `Receipt receipt` and the statement:

```java
assertThat(receipt.totalQuantity() == 5).isTrue();
```

Replace it with an assertion that displays expected/actual and the receipt ID. **Solution:**

```java
assertThat(receipt.totalQuantity())
        .as("total quantity of receipt %s", receipt.id())
        .isEqualTo(5);
```

The new version clearly reports which field failed without weakening the check.

### Exercise 3: test an exception branch

The service must reject a line item with quantity 0 by throwing `IllegalArgumentException` with message `quantity must be positive`. **Solution:**

```java
assertThatThrownBy(() -> service.create(
        "R-03",
        List.of(new ReceiptService.Item("PEN", 0))
))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessage("quantity must be positive");
```

With the implementation in section 4, this condition is checked after validating receipt ID and the list, so the test reaches the exact branch to verify.

### Checklist

- [ ] The assertion starts from **actual** and states expected according to the contract.
- [ ] Type-specific methods (String/number/list/map/optional/exception) are used instead of reducing everything to booleans.
- [ ] For collections, ordering, occurrence counts, and whether extra elements are allowed are clearly defined.
- [ ] For objects, `equals`, identity, and when deep comparison is needed are understood.
- [ ] `as(...)` descriptions appear before checks, provide useful context, and contain no secrets.
- [ ] Default failure messages are not overridden without a clear reason.
- [ ] Exceptions are checked for the proper type and message/code when part of the contract.
- [ ] Soft assertions only group independent checks, without masking null preconditions or bloating tests.
- [ ] Comparisons for `BigDecimal`, floating-point numbers, `Optional`, and collections follow proper semantics.
- [ ] Tests run via JUnit Jupiter/build tool; assertions fail when deliberately given bad output (sanity check when needed).
- [ ] Tests do not rely on other tests' data, a shared database, or incidental ordering to pass.

## 14. Core summary

AssertJ lets you write tests as verifiable data statements: **`assertThat(actual)` + concrete condition**, paired with **`as(...)`** to attach context on failure. A good assertion has **contract-matched strength**: strict enough to catch real bugs, without pinning down ordering or implementation details the business does not require.

With Spring Boot, use AssertJ in plain JUnit tests, slice tests, and integration tests whenever you need to verify objects/results. JUnit still runs the tests; Mockito/mocks or test databases manage dependencies; AssertJ helps explain outcomes and differences. On failure, readers should immediately see **which object, which condition, what was expected, and what was actually returned**, rather than guessing from a boolean `false`.

## References

- [AssertJ — Documentation](https://assertj.github.io/doc/) — fluent assertions, collection assertions, exception assertions, soft assertions, and failure descriptions.
- [AssertJ Core — API Documentation](https://javadoc.io/doc/org.assertj/assertj-core) — API signatures and overloads for your version.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/) — starter test and how to test Spring Boot applications.
- [JUnit User Guide](https://docs.junit.org/current/user-guide/) — JUnit Jupiter, test lifecycle, and running tests.
