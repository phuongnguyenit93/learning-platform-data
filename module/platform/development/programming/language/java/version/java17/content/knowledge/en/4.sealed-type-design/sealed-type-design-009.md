# Testing All Variants Including `null` When Designing with `sealed` in Java 17

## 1. The Goal of Testing a `sealed` Type Family

When designing a `sealed` type, you publish **the set of permitted direct subtypes**. For example, a payment processing outcome has three states: approved, declined, and pending. Each state is a distinct Java type rather than an arbitrary status string.

~~~java
public sealed interface PaymentResult
        permits Approved, Declined, Pending {
}
~~~

This design restricts valid result branches. However, `sealed` **does not automatically test** the functions that process those results. A function can still:

- Forget to handle a newly added variant.
- Match the right object type yet return the wrong message or value.
- Fail when a `PaymentResult` reference receives `null`.
- Miss invalid or edge-case inputs inside each variant, such as blank strings or negative numbers.

Accordingly, this lesson focuses on two distinct yet complementary requirements:

1. **Test every valid variant** of the `sealed` family with expected data and outcomes.
2. **Test the `null` case separately** according to the chosen API policy, because `null` is not a subtype and does not belong to `permits`.

The examples use stable Java 17 without preview features. The tests are illustrated with **JUnit Jupiter** (JUnit 5 API) and Maven; the same principles apply to other testing frameworks.

## 2. Distinguishing "Covering All Variants" from "Covering All Inputs"

Suppose:

~~~text
PaymentResult (sealed interface)
├── Approved (record, final)
├── Declined (record, final)
└── Pending  (record, final)
~~~

There are at least three **test categories** to consider:

| Category | Goal | Example |
|---|---|---|
| Each variant of `sealed` | Ensure every subtype has at least one test verifying its distinct behavior. | `Approved("TX-17")` produces `APPROVED: TX-17`. |
| Boundary and invalid field values | Ensure subtypes cannot hold bad state or trigger unexpected behavior. | `Approved(null)`, `Approved(" ")`, `Pending(0)`. |
| `null` for the parent-type parameter | Ensure the API handles a missing object deterministically. | `format(null)` throws `NullPointerException` with a clear message. |

Testing all **three categories** does not mean testing every **possible value** of the three records. For instance, `Approved` has infinitely many valid transaction IDs. Pick representative values, key boundaries, and error conditions aligned with business rules.

An important distinction: **`null` is not a fourth variant** of `PaymentResult`. `sealed` restricts *which class/interface types may inherit*; a Java reference variable itself can still hold `null` unless the API contract explicitly prevents or handles it.

## 3. Building a `sealed` Family as the Subject Under Test

Let's build a `PaymentFormatter.format` method that formats payment results into text. The classes live in package `example.payment`.

~~~text
sealed-tests/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── example/
    │           └── payment/
    │               ├── PaymentResult.java
    │               ├── Approved.java
    │               ├── Declined.java
    │               ├── Pending.java
    │               └── PaymentFormatter.java
    └── test/
        └── java/
            └── example/
                └── payment/
                    └── PaymentFormatterTest.java
~~~

### 3.1. Parent Type `PaymentResult`

File `src/main/java/example/payment/PaymentResult.java`:

~~~java
package example.payment;

public sealed interface PaymentResult
        permits Approved, Declined, Pending {
}
~~~

The `permits` list is written **explicitly** because each subtype resides in its own `.java` file. The three records below all directly `implements PaymentResult`. Records are implicitly `final`, satisfying `sealed`'s requirement for direct subtypes.

### 3.2. Three Variants with Data Rules

File `src/main/java/example/payment/Approved.java`:

~~~java
package example.payment;

import java.util.Objects;

public record Approved(String reference) implements PaymentResult {
    public Approved {
        Objects.requireNonNull(reference, "reference");
        if (reference.isBlank()) {
            throw new IllegalArgumentException(
                    "reference must not be blank");
        }
        reference = reference.strip();
    }
}
~~~

File `src/main/java/example/payment/Declined.java`:

~~~java
package example.payment;

import java.util.Objects;

public record Declined(String reason) implements PaymentResult {
    public Declined {
        Objects.requireNonNull(reason, "reason");
        if (reason.isBlank()) {
            throw new IllegalArgumentException(
                    "reason must not be blank");
        }
        reason = reason.strip();
    }
}
~~~

File `src/main/java/example/payment/Pending.java`:

~~~java
package example.payment;

public record Pending(int queuePosition) implements PaymentResult {
    public Pending {
        if (queuePosition <= 0) {
            throw new IllegalArgumentException(
                    "queuePosition must be positive");
        }
    }
}
~~~

The compact record constructors enforce invariants:

- `Approved`'s reference and `Declined`'s reason cannot be `null` or whitespace-only.
- `Pending` requires a queue position greater than 0.
- `strip()` trims leading/trailing whitespace from accepted strings.

Concrete types clarify intent: a `Declined` object cannot be confused with an `Approved` object merely because both wrap a string; they are distinct types.

### 3.3. A Handler Covering All Three Branches

File `src/main/java/example/payment/PaymentFormatter.java`:

~~~java
package example.payment;

import java.util.Objects;

public final class PaymentFormatter {
    private PaymentFormatter() {
    }

    public static String format(PaymentResult result) {
        Objects.requireNonNull(result, "result");

        if (result instanceof Approved approved) {
            return "APPROVED: " + approved.reference();
        }
        if (result instanceof Declined declined) {
            return "DECLINED: " + declined.reason();
        }
        if (result instanceof Pending pending) {
            return "PENDING: " + pending.queuePosition();
        }

        throw new IllegalStateException(
                "Unhandled PaymentResult variant: "
                        + result.getClass().getName());
    }
}
~~~

Here, `Objects.requireNonNull(result, "result")` defines a clear policy: **`null` is rejected**; passing `null` throws `NullPointerException` with message `result`. This is a design choice of this example API, not default behavior generated by `sealed`.

`instanceof` with pattern variables, such as `result instanceof Approved approved`, is a stable Java 17 feature. For `null`, every `instanceof` check evaluates to `false`, so placing `requireNonNull` first makes the error explicit and prevents falling through into an unhandled-variant branch.

The three branches handle all records currently listed in `permits`. The final `throw` acts as a safeguard if the codebase later adds a variant and someone forgets to update the formatter.

**Java 17 limitation:** `if/else` or `if` chains with `instanceof` **are not proven exhaustive by the compiler**. Pattern matching for `switch` over `sealed` types is still a *preview* feature in Java 17; this document does not require enabling `--enable-preview`. Therefore, tests and reviewing changes whenever variants are added are especially important.

## 4. Building a Test Matrix Before Writing Tests

A clear matrix helps avoid testing only the "happy path" while missing critical cases:

| Case ID | Input | Expected result | Test category |
|---|---|---|---|
| V1 | `new Approved("TX-17")` | `"APPROVED: TX-17"` | `Approved` variant |
| V2 | `new Declined("Invalid card")` | `"DECLINED: Invalid card"` | `Declined` variant |
| V3 | `new Pending(3)` | `"PENDING: 3"` | `Pending` variant |
| N1 | `PaymentFormatter.format(null)` | Throws `NullPointerException`, message `"result"` | `null` at parent-type parameter |
| N2 | `new Approved(null)` | Throws `NullPointerException` | `null` in record data |
| N3 | `new Declined(null)` | Throws `NullPointerException` | `null` in record data |
| B1 | `new Approved("   ")` | Throws `IllegalArgumentException` | Whitespace-only string |
| B2 | `new Declined(" ")` | Throws `IllegalArgumentException` | Whitespace-only string |
| B3 | `new Pending(0)` or `new Pending(-1)` | Throws `IllegalArgumentException` | Invalid numeric boundary |
| E1 | Check `permits` list via reflection | Every direct subtype has a test fixture | Detects newly added variants missing from tests |

Several cases can be combined using **parameterized tests** when they share validation structure. Case `N1` should remain separate to make the API contract explicit when the parent reference is `null`.

## 5. Writing Tests with JUnit Jupiter

JUnit Jupiter supports `@Test` and `@ParameterizedTest`. `@MethodSource` lets you declare each variant paired with its expected output in one place, avoiding three repetitive test methods.

File `src/test/java/example/payment/PaymentFormatterTest.java`:

~~~java
package example.payment;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class PaymentFormatterTest {

    private static Stream<Arguments> validVariants() {
        return Stream.of(
                Arguments.of(
                        new Approved("TX-17"), "APPROVED: TX-17"),
                Arguments.of(
                        new Declined("Invalid card"), "DECLINED: Invalid card"),
                Arguments.of(
                        new Pending(3), "PENDING: 3")
        );
    }

    @ParameterizedTest(name = "variant {index}: {0}")
    @MethodSource("validVariants")
    void formatsEachPermittedVariant(
            PaymentResult result, String expected) {
        assertEquals(expected, PaymentFormatter.format(result));
    }

    @Test
    void rejectsNullResultExplicitly() {
        NullPointerException exception = assertThrows(
                NullPointerException.class,
                () -> PaymentFormatter.format(null));

        assertEquals("result", exception.getMessage());
    }

    @Test
    void rejectsNullFieldsInsideRecords() {
        assertAll(
                () -> assertThrows(
                        NullPointerException.class,
                        () -> new Approved(null)),
                () -> assertThrows(
                        NullPointerException.class,
                        () -> new Declined(null))
        );
    }

    @Test
    void rejectsInvalidRecordValues() {
        assertAll(
                () -> assertThrows(
                        IllegalArgumentException.class,
                        () -> new Approved("   ")),
                () -> assertThrows(
                        IllegalArgumentException.class,
                        () -> new Declined(" ")),
                () -> assertThrows(
                        IllegalArgumentException.class,
                        () -> new Pending(0)),
                () -> assertThrows(
                        IllegalArgumentException.class,
                        () -> new Pending(-1))
        );
    }

    @Test
    void normalizesAllowedWhitespace() {
        assertEquals("TX-17", new Approved("  TX-17  ").reference());
        assertEquals(
                "Invalid card",
                new Declined(" Invalid card ").reason());
    }

    @Test
    void fixturesCoverAllDirectPermittedTypes() {
        assertTrue(PaymentResult.class.isSealed());

        Set<Class<?>> permittedTypes = Arrays.stream(
                PaymentResult.class.getPermittedSubclasses())
                .collect(Collectors.toSet());

        Set<Class<?>> testedTypes = validVariants()
                .map(arguments -> arguments.get()[0].getClass())
                .collect(Collectors.toSet());

        assertEquals(permittedTypes, testedTypes);
    }
}
~~~

### 5.1. What Happens in the Parameterized Test?

`validVariants()` supplies three **input / expected output** pairs. JUnit runs `formatsEachPermittedVariant` separately for each pair. Thus, if one branch behaves incorrectly, the test report identifies exactly which variant failed expectations.

Using `assertEquals` verifies the **actual output**, rather than merely checking that no exception was thrown. For example, if someone accidentally changes the `Declined` branch to `"APPROVED: " + declined.reason()`, the test for `Declined` will fail.

### 5.2. Why Have Dedicated Tests for `null`?

`rejectsNullResultExplicitly()` verifies both the **exception type** and **message** to document the chosen contract. Using `assertThrows` makes the test pass when *rejecting null* occurs as designed.

By contrast, `rejectsNullFieldsInsideRecords()` checks **data inside the variants**. These are two separate levels:

~~~text
null                      -> no PaymentResult object at all
new Approved(null)        -> attempting to construct Approved with a null field
new Approved("TX-17")     -> valid Approved object
~~~

Do not assume that `sealed` or `record` automatically makes reference fields non-`null`. A `String` component in a record can still receive `null` unless the constructor checks it.

### 5.3. Reflection Helps Detect When the Variant Set Changes

Java 17 provides two relevant reflection APIs:

- `Class.isSealed()` checks whether a class or interface is declared `sealed`.
- `Class.getPermittedSubclasses()` returns an array of the **direct** permitted subtypes of a `sealed` type.

The `fixturesCoverAllDirectPermittedTypes()` test fetches the permitted types via reflection and compares them with the actual types of the fixtures in `validVariants()`.

For example, if a developer later adds:

~~~java
// PaymentResult.java after expansion
public sealed interface PaymentResult
        permits Approved, Declined, Pending, Cancelled {
}
~~~

and creates `record Cancelled(String reason) implements PaymentResult`, yet forgets to add a test for `Cancelled`, then `permittedTypes` has four types while `testedTypes` still has three. The guard test will **fail**, reminding the team to inspect the new branch and add it to the test data.

This test is far more useful than hardcoding a three-type list in both source and test and comparing two hardcoded lists. However, understand its limitation: the reflection guard proves **each direct subtype has a fixture**, not that every branch's logic is correct. That is why it must accompany `formatsEachPermittedVariant`.

## 6. Running Tests with Maven on Java 17

To run the example standalone, create `pom.xml` in the `sealed-tests` directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>sealed-tests</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</groupId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</groupId>
                <version>3.5.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

This is **one valid illustrative configuration** for Java 17 and JUnit Jupiter 5; you do not have to use these exact dependency versions in every project. When adopting this in a real application, manage dependency versions according to your project's upgrade policy.

Run `java -version` and `mvn -version` to verify which JDK Maven is using. In the directory containing `pom.xml`, run:

~~~bash
mvn test
~~~

Maven compiles main sources under `src/main/java`, compiles tests under `src/test/java`, and executes the test cases. The first run downloads dependencies from Maven Central, so network access or a populated local cache is required.

This example does not need `--enable-preview`. If using an IDE, set the project SDK and target release to Java 17 and import the Maven project so JUnit dependencies resolve properly.

## 7. When API Policy Allows `null`

There is no single rule forcing every API to throw on `null`. You may choose a different policy when business semantics genuinely call for it:

~~~java
public static String formatNullable(PaymentResult result) {
    if (result == null) {
        return "NO_RESULT";
    }
    return PaymentFormatter.format(result);
}
~~~

Corresponding test:

~~~java
@Test
void nullableApiReturnsMarkerForNull() {
    assertEquals("NO_RESULT", formatNullable(null));
}
~~~

In this standalone snippet, `formatNullable` is a method on a utility class you define; if placed in `PaymentFormatter`, it can be called as `PaymentFormatter.formatNullable(null)`. Stay consistent between your documented contract and tests: **either reject `null`, or handle it into a meaningful result**; avoid letting `null` accidentally fall past `instanceof` checks into an obscure exception.

Another design option is representing absence via a **named variant**:

~~~java
public sealed interface PaymentResult
        permits Approved, Declined, Pending, NotStarted {
}

public record NotStarted() implements PaymentResult {
}
~~~

This is a **structural change illustration**, not two snippets to paste alongside the original `PaymentResult.java` without updating files. When adding `NotStarted`, you need to:

1. Create `NotStarted.java` and add the record to `permits`.
2. Define formatting for `NotStarted` in the formatter.
3. Add a fixture and expected output to `validVariants()`; add boundary tests if the record holds data.
4. Still decide separately whether **`format(null)`** is permitted or rejected.

`NotStarted` is an **object of a permitted subtype**, whereas `null` remains the absence of any reference. The two concepts are not the same.

## 8. Limitations to Know When Using Tests to Assess Completeness

### 8.1. Reflection Only Inspects Direct Levels of `permits`

`getPermittedSubclasses()` lists **direct subtypes**. Suppose:

~~~java
sealed interface Event permits Completed, Retryable {
}

record Completed() implements Event {
}

non-sealed class Retryable implements Event {
}

final class NetworkRetry extends Retryable {
}
~~~

Reflection on `Event` returns `Completed` and `Retryable`, **not** `NetworkRetry`. Moreover, the `Retryable` branch is `non-sealed`, so in principle any number of subclasses can exist beneath it. A test checking "every type in `getPermittedSubclasses()` has one fixture" does not guarantee coverage of all concrete classes inside that open branch.

If you need full control over the entire variant set, consider designing the type tree to be **completely closed via `final` or further restricted `sealed` sub-branches**, then identify the leaves to test. If you intentionally choose `non-sealed` for extensibility, test against the open branch's **contract and behavioral groups**, along with key concrete implementations, rather than asserting a finite variant list.

### 8.2. One Fixture Is Not Enough for Every Boundary Condition

For example, testing `Pending(3)` proves the formatting branch works for typical positive data. It does not prove the constructor rejects `0` or `-1`. That is why the example includes both per-variant tests and invalid-input tests for each record.

Similarly, testing `Approved("TX-17")` and `Approved(" TX-17 ")` serves two different goals: formatter output and whitespace normalization in the record.

### 8.3. Adding a Variant Requires Updating Handlers, Not Just Fixtures

In Java 17, `if` combined with `instanceof` has no compile-time exhaustiveness checking. If you add `Cancelled` to `permits` and add only a test fixture without updating the formatter, the test handling `Cancelled` will hit `IllegalStateException`.

This is the desired behavior from the test suite: changing the model forces both handler code and test cases to be reviewed together. Do not attach a "silent ignore" `default` or `return null` to hide a missing branch.

### 8.4. Do Not Use `null` as a Catch-All Error Sentinel

`null` as an **input** and a method **returning `null`** are two different contracts. For example, if one formatter branch returns `null` on failure, tests should catch that it fails the requirement to return a message. For APIs returning multi-state outcomes, a named variant like `Declined` or `NotStarted` often communicates meaning far better than an unexplained `null`.

### 8.5. Distinguish Test Fixtures from Production Data

Do not try to invent an arbitrary class `implements PaymentResult` to test an "unknown type": `sealed` blocks classes outside `permits` at compile time or during subtype link checks. For a fully closed type like the initial three records, no fourth valid direct subtype can exist without editing `permits`.

To verify how the formatter reacts when **the model evolves**, add a variant in source code on a working branch and observe the guard test and formatting test fail until updated. That tests API evolution rather than forging illegal Java objects.

## 9. Practical Workflow When Adding a Variant to a `sealed` Type

Suppose the team needs a `Cancelled` state. A repeatable workflow:

1. Define `Cancelled`'s data rules and write the record or class.
2. Add `Cancelled` to `PaymentResult`'s `permits`.
3. Run tests to see the guard report the uncovered new variant.
4. Add one or more `Cancelled` fixtures with expected formatted outputs.
5. Update `PaymentFormatter.format` to handle the new variant properly.
6. Write tests for `null` or boundary inputs inside `Cancelled` if applicable.
7. Re-run all existing tests, including the `null` test on the parent parameter.

This workflow creates a clear link between the **type contract**, **handling behavior**, and **test suite**. When adding a branch, updating tests reflects the business change rather than merely inflating test counts.

## 10. Applied Exercises

### Exercise 1 — Find the Uncovered Case

Consider the declaration:

~~~java
sealed interface LoadResult permits Loaded, Failed, Loading {
}

record Loaded(String value) implements LoadResult {
}

record Failed(String message) implements LoadResult {
}

record Loading(int percent) implements LoadResult {
}
~~~

An existing test suite has only `new Loaded("data")` and `new Failed("timeout")`. List the required test cases to cover all `sealed` variants, plus a case for `format(null)` under a `null`-rejection policy.

**Hint:** `Loading` is missing. Meanwhile, `null` requires a case independent of `permits`; never count it inside `getPermittedSubclasses()`.

### Exercise 2 — Distinguish Two Kinds of `null`

Design a validating constructor for `record Loaded(String value)`. Write two separate tests: one for `format(null)` and one for `new Loaded(null)`. Explain why both tests can expect `NullPointerException` while verifying **two different contract layers**.

### Exercise 3 — Detecting a New Variant

Add `record Cancelled(String reason) implements PaymentResult` to the example project and update `permits`, without yet updating the formatter or fixtures. Predict which tests fail; then add the fixture and formatting branch so the new tests pass.

### Exercise 4 — Type Family with an Open Branch

With `sealed interface Event permits Completed, Retryable` in Section 8, explain why a test comparing `getPermittedSubclasses()` against two fixtures does not prove that every subclass of `Retryable` has been tested. When should `Retryable` be `non-sealed`, and when should it be replaced with a design having a finite set of leaves?

## 11. Key Takeaways

- `sealed` restricts the set of **permitted direct subtypes**, yet **does not eliminate `null`** from references.
- To test variants thoroughly, create **concrete fixtures for each type** paired with expected outputs and boundary conditions.
- Java 17 supports `record`, `sealed`, pattern matching for `instanceof`, and `getPermittedSubclasses()` reflection without preview mode.
- Combine **parameterized tests** with a **reflection guard** to quickly catch when someone adds a variant without adding tests.
- `getPermittedSubclasses()` returns only **direct subtypes**; indirect types beneath `non-sealed` cannot be treated as a closed list.
- Your `null` policy must be explicitly defined and separately tested: throw an exception, handle it as a special case, or model meaningful absence as a named variant.
- With Java 17, avoid relying on preview pattern matching for `switch` to teach basic testing workflows; `instanceof` and clear tests are sufficient for these examples.

### References

- [Java SE 17 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html).
- [Java SE 17 API — `Class.getPermittedSubclasses()` and `Class.isSealed()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- [Java SE 17 API — `Objects.requireNonNull()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html).
- [JUnit Jupiter — User Guide](https://junit.org/junit5/docs/current/user-guide/).
