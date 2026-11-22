# Testing Pure Functions with Input–Output Tables in Java

## 1. Goal: turning business rules into clear test cases

A **pure function** has two important characteristics:

1. **Same input, same observable result**: the result does not depend on the clock, random numbers, mutable global data, or the history of previous calls.
2. **No observable side effects**: it does not mutate mutable parameters, update global variables, write to files or databases, or make network calls as part of the computation.

Pure example:

```java
static int square(int n) {
    return n * n;
}
```

**Impure** example:

```java
static int counter = 0;

static int nextNumber() {
    return ++counter;
}
```

`nextNumber()` takes no parameters, yet each call can return a different result. Although you can write a test for a sequence of calls, that test must depend on call order and initial state; it is no longer independent input → output testing.

When a function is pure, a particularly direct testing approach is to build a **table of expected inputs and outputs**. Each row in the table is a test case. The test code can iterate over every row using the same procedure:

```text
test case = (case name, input, expected output)

for each case:
    actual = function(input)
    compare actual with expected
    if different → report failure with case name, input, expected, and actual
```

This approach is commonly called **table-driven testing** or **data-driven testing**. It fits Java Core, functional programming, data transformation rules, normalization functions, fee calculations, classification, validators, and branching computations.

After this lesson, you will know how to design test tables with meaningful coverage, run them with Java 17 without external libraries, test exception-throwing cases, organize tests with JUnit 5 when a test project is available, and distinguish a *pure function* from a *function that only happens to return the same result*.

## 2. Why are pure functions easy to test?

A pure function can be understood as a mapping:

```text
f: Input → Output
```

For determined input values:

```text
f(0)     → 0
f(2)     → 4
f(-3)    → 9
```

With no external data affecting it, each test can be run independently:

- No need to create a mock database for a pure calculation.
- No need to reset static variables before each test.
- No need to check whether another test running earlier modified state.
- No need for `Thread.sleep` to wait on time or rely on random ordering.
- The same input can be run multiple times or in parallel without side effects of **the function itself** interfering with the result.

However, **a pure function is not automatically correct**. If a wrong formula is implemented, it can still return the same wrong result every time. Therefore, the test table needs expected outputs computed **independently from the specification**, rather than copying the calculation of the code under test.

A test passing 100 times also does not mathematically prove that the function has no side effects. It provides evidence for those specific cases. Function design, inspecting reference variables, and evaluating business invariants are still necessary.

## 3. Example: a multi-branch shipping fee function

Suppose the system's rules are:

- The input `subtotal` is the **order item total in VND**, non-negative.
- `express` is a flag requesting express delivery.
- When `subtotal` is **100,000 VND or more**:
  - Regular delivery: free (`0`).
  - Express delivery: `15,000`.
- When `subtotal` is **below 100,000 VND**:
  - Regular delivery: `10,000`.
  - Express delivery: `25,000`.
- `subtotal < 0` is an invalid input and must throw `IllegalArgumentException`.

The corresponding pure function:

```java
static int shippingFee(int subtotal, boolean express) {
    if (subtotal < 0) {
        throw new IllegalArgumentException("subtotal must be nonnegative");
    }
    if (subtotal >= 100_000) {
        return express ? 15_000 : 0;
    }
    return express ? 25_000 : 10_000;
}
```

The function reads no values outside its parameters, mutates no state, and returns a result according to a deterministic rule table. Throwing an exception based on input conditions **does not by itself make a function impure**: here the exception type is determined by the input. However, tests may check only the exception type or both the type and the message, depending on the application contract.

### Input → output test case table

| ID | `subtotal` | `express` | Expected result | Meaning |
| --- | ---: | :---: | ---: | --- |
| F01 | 0 | `false` | 10000 | Minimum valid, regular delivery |
| F02 | 0 | `true` | 25000 | Minimum valid, express delivery |
| F03 | 99999 | `false` | 10000 | Just below threshold, regular delivery |
| F04 | 99999 | `true` | 25000 | Just below threshold, express delivery |
| F05 | 100000 | `false` | 0 | Exact threshold, regular delivery |
| F06 | 100000 | `true` | 15000 | Exact threshold, express delivery |
| F07 | 180000 | `false` | 0 | Above threshold, regular delivery |
| F08 | 180000 | `true` | 15000 | Above threshold, express delivery |

You can view this as an **extended truth table** across the two `express` branches and three value regions: below threshold, at threshold, and above threshold. Choosing `99,999` and `100,000` is intentional to catch a `>` instead of `>=` bug.

This table includes an additional exception case:

| ID | `subtotal` | `express` | Expected |
| --- | ---: | :---: | --- |
| E01 | -1 | `false` | `IllegalArgumentException` |

This is a data rejection policy, not a `0` result. If you simply write `expected = 0` for negative numbers, the test may hide an important bug.

### Do not write expected values from the function under test itself

Wrong for the purpose of testing:

```java
int expected = shippingFee(100_000, false);
int actual = shippingFee(100_000, false);
assertEquals(expected, actual);
```

Both sides run the same implementation, so a bug in the function can appear in both `expected` and `actual`. The expectation must come from the business specification: for `100_000` and regular delivery, it is `0`.

## 4. Designing a table for a string normalization function

In addition to numeric calculations, input–output tables are very useful for transformations.

Suppose `normalizeTag(String raw)` has these rules:

1. `null` is rejected with `NullPointerException`.
2. Trim whitespace from both ends using `String.strip()`.
3. If the trimmed string is empty, throw `IllegalArgumentException`.
4. Convert the string to uppercase using `toUpperCase(Locale.ROOT)`.
5. Do not arbitrarily remove whitespace **in the middle** of the string.

```java
static String normalizeTag(String raw) {
    Objects.requireNonNull(raw, "raw");
    String cleaned = raw.strip();
    if (cleaned.isEmpty()) {
        throw new IllegalArgumentException("tag must not be blank");
    }
    return cleaned.toUpperCase(Locale.ROOT);
}
```

`Locale.ROOT` uses rules independent of the machine's default locale for an illustrative technical code/tag. For natural language or proper-name rules, you need to choose a locale appropriate to the business domain; do not assume all text should be uppercased with `Locale.ROOT`.

### Success table

| ID | Input | Expected | Behavior aspect |
| --- | --- | --- | --- |
| T01 | `"java"` | `"JAVA"` | Convert to uppercase |
| T02 | `"  stream  "` | `"STREAM"` | Trim whitespace on both ends |
| T03 | `"a b"` | `"A B"` | Preserve internal whitespace |
| T04 | `"trà"` | `"TRÀ"` | Accented characters |
| T05 | `"API"` | `"API"` | Already normalized |
| T06 | `"\t tool \t"` | `"TOOL"` | Outer tab characters |

### Error table

| ID | Input | Expected |
| --- | --- | --- |
| E02 | `" \t "` | `IllegalArgumentException` |
| E03 | `null` | `NullPointerException` |

When recording tests in a table, represent data with invisible characters explicitly: `" \t "` is a space, a tab, then a space. If tests only display strings as plain text, whitespace-related bugs are very easy to miss.

Choosing varied input forms helps catch bugs that testing only `"java"` would miss: forgetting to trim, removing internal whitespace as well, unstable locale handling, or missing a policy for null/blank.

## 5. Implementing table-driven tests with `record` and a loop

In Java 17, `record` is well suited to represent **each row of test data**:

```java
record FeeCase(String id, int subtotal, boolean express, int expected) {}
record TagCase(String id, String input, String expected) {}
```

A `record` stores data for a case without manually writing constructors, getters, `equals`, `hashCode`, or `toString`. Although a record itself does not allow reassigning its components, it is only **shallowly immutable**: if a component holds a mutable `List`, the List's contents can still change. Examples like `int`, `boolean`, and `String` do not have that internal mutation risk.

The test suite iterates over each case:

```java
for (FeeCase test : feeCases) {
    int actual = shippingFee(test.subtotal(), test.express());
    checkEquals(test.expected(), actual, test.id());
}
```

Advantages over copying and pasting dozens of `if` statements:

- Every case goes through the same assertion logic.
- Adding a new case only requires adding one row.
- The ID helps identify the failing case.
- Expected results are easy to review visually like a specification table.
- The table can be reused in JUnit, CSV files, or another test runner when needed.

However, **a data table does not replace test design**. Twenty rows with the same value are usually worse than eight rows intentionally chosen to represent branches and boundaries.

## 6. Complete Java 17 program: success tables, error table, and pure function tests

Create the file **`PureFunctionTableTests.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.stream.Stream;

public class PureFunctionTableTests {
    // Business functions to test.
    static int shippingFee(int subtotal, boolean express) {
        if (subtotal < 0) {
            throw new IllegalArgumentException(
                    "subtotal must be nonnegative");
        }
        if (subtotal >= 100_000) {
            return express ? 15_000 : 0;
        }
        return express ? 25_000 : 10_000;
    }

    static String normalizeTag(String raw) {
        Objects.requireNonNull(raw, "raw");
        String cleaned = raw.strip();
        if (cleaned.isEmpty()) {
            throw new IllegalArgumentException(
                    "tag must not be blank");
        }
        return cleaned.toUpperCase(Locale.ROOT);
    }

    // Each record corresponds to one row in the test case table.
    record FeeCase(String id, int subtotal,
                   boolean express, int expected) {}

    record TagCase(String id, String input, String expected) {}

    record FailureCase(
            String id,
            Class<? extends RuntimeException> expectedType,
            Runnable action) {}

    static void checkEquals(Object expected, Object actual,
                            String caseId) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    caseId + ": expected=" + expected
                            + ", actual=" + actual);
        }
    }

    static void checkThrows(
            Class<? extends RuntimeException> expectedType,
            Runnable action, String caseId) {
        try {
            action.run();
        } catch (RuntimeException actual) {
            if (expectedType.isInstance(actual)) {
                return;
            }
            throw new AssertionError(
                    caseId + ": wrong exception type; expected="
                            + expectedType.getSimpleName()
                            + ", actual="
                            + actual.getClass().getSimpleName(),
                    actual);
        }
        throw new AssertionError(
                caseId + ": expected "
                        + expectedType.getSimpleName()
                        + " but no exception was thrown");
    }

    static int testFees() {
        List<FeeCase> cases = List.of(
                new FeeCase("F01", 0, false, 10_000),
                new FeeCase("F02", 0, true, 25_000),
                new FeeCase("F03", 99_999, false, 10_000),
                new FeeCase("F04", 99_999, true, 25_000),
                new FeeCase("F05", 100_000, false, 0),
                new FeeCase("F06", 100_000, true, 15_000),
                new FeeCase("F07", 180_000, false, 0),
                new FeeCase("F08", 180_000, true, 15_000));

        for (FeeCase test : cases) {
            int actual = shippingFee(
                    test.subtotal(), test.express());
            checkEquals(test.expected(), actual, test.id());

            // Check the same input again, confirming that in this case
            // no dependency on call history is detected.
            int repeated = shippingFee(
                    test.subtotal(), test.express());
            checkEquals(actual, repeated,
                    test.id() + " repeated");
        }
        return cases.size();
    }

    static int testTags() {
        List<TagCase> cases = List.of(
                new TagCase("T01", "java", "JAVA"),
                new TagCase("T02", "  stream  ", "STREAM"),
                new TagCase("T03", "a b", "A B"),
                new TagCase("T04", "trà", "TRÀ"),
                new TagCase("T05", "API", "API"),
                new TagCase("T06", "\t tool \t", "TOOL"));

        for (TagCase test : cases) {
            String actual = normalizeTag(test.input());
            checkEquals(test.expected(), actual, test.id());
            checkEquals(actual, normalizeTag(test.input()),
                    test.id() + " repeated");

            // For valid sample values, normalizing again
            // does not change the normalized result.
            checkEquals(actual, normalizeTag(actual),
                    test.id() + " normalized twice");
        }
        return cases.size();
    }

    static int testFailures() {
        List<FailureCase> cases = List.of(
                new FailureCase(
                        "E01",
                        IllegalArgumentException.class,
                        () -> shippingFee(-1, false)),
                new FailureCase(
                        "E02",
                        IllegalArgumentException.class,
                        () -> normalizeTag(" \t ")),
                new FailureCase(
                        "E03",
                        NullPointerException.class,
                        () -> normalizeTag(null)));

        for (FailureCase test : cases) {
            checkThrows(test.expectedType(),
                    test.action(), test.id());
        }
        return cases.size();
    }

    public static void main(String[] args) {
        int feeCases = testFees();
        int tagCases = testTags();
        int errorCases = testFailures();

        // Using a pure function in a pipeline: each result
        // depends only on the input tag value.
        List<String> composition = Stream.of(
                        " java ", "Stream", " api ")
                .map(PureFunctionTableTests::normalizeTag)
                .toList();
        checkEquals(List.of("JAVA", "STREAM", "API"),
                composition, "composition");

        System.out.println("feeCases=" + feeCases);
        System.out.println("tagCases=" + tagCases);
        System.out.println("errorCases=" + errorCases);
        System.out.println("composition=" + composition);
        System.out.println("tests=PASS");
    }
}
```

Run with **JDK 17 or newer**:

```bash
javac -encoding UTF-8 PureFunctionTableTests.java
java PureFunctionTableTests
```

Stdout when all cases pass:

```text
feeCases=8
tagCases=6
errorCases=3
composition=[JAVA, STREAM, API]
tests=PASS
```

The checks do not depend on the JVM `-ea` flag, because `checkEquals` and `checkThrows` directly throw `AssertionError` on mismatch. When a case fails, the message includes its ID (e.g. `F05`, `T04`, `E02`) and the corresponding expectation, making it easy to pinpoint which row in the table needs investigation.

### Why split into three tables?

- `FeeCase`: two inputs of type `int`, `boolean`, one output of type `int`.
- `TagCase`: one `String` input, one `String` output.
- `FailureCase`: instead of a return value, the expectation is an **exception type**.

There is no need to force exceptions into dummy values like `-1` or `null` if the API is designed to throw errors. The test suite verifies the existing contract; when you change the contract per product requirements, update the table and the code together.

### Role of `checkThrows`

An exception test passes only if the **exact expected exception type** is thrown. If the function throws nothing, the test fails. If it throws a different `RuntimeException` type, the test also fails with the original error attached.

Do not write:

```java
try {
    shippingFee(-1, false);
} catch (Exception ignored) {
    // Wrong: the test treats any exception as a pass.
}
```

The snippet above also has another problem: if the function **does not throw**, the test does not fail either. A proper test must verify both that an exception is thrown and its type.

### Repeated checking does not prove purity

In `testFees()` and `testTags()`, the same input is called twice and the results are compared. This can catch some bugs where state is mutated. However, a function that reads the clock and happens to return the same value on two close calls can still pass; a function that writes logs still has side effects even if its output does not change.

**Purity is a design property that must be evaluated through code and contract**, not something that can be proven solely by repeated testing on a few inputs.

## 7. Steps to build an effective input–output table

### Step 1: Write the specification in business language

Do not start from the implementation. For example:

> For orders from 100,000 VND, regular delivery is free; express delivery is 15,000 VND. Below the threshold, regular delivery is 10,000 and express delivery is 25,000. Negative totals are not accepted.

The specification is the source for computing expected values, avoiding tests that merely copy the function's mistakes.

### Step 2: List equivalence classes

The inputs for `shippingFee` can be partitioned into:

| Field | Data class |
| --- | --- |
| `subtotal` | Negative |
| `subtotal` | Non-negative and below 100,000 |
| `subtotal` | Equal to or above 100,000 |
| `express` | `false` |
| `express` | `true` |

Combine the important branches to achieve coverage. You do not need to generate lots of random data when all values in the same class are expected to behave identically; however, you must pay special attention to **boundaries**.

### Step 3: Choose boundary values

For the `100_000` threshold, typical values are:

```text
99_999     : just below
100_000    : exact threshold
100_001    : just above
```

This is the *boundary value analysis* technique. The main table uses `99_999`, `100_000`, `180_000`; you can add `100_001` when you need to explicitly verify the boundary just above. Data far away from the threshold can test normal behavior, but has less power to catch `>`/`>=` bugs than values right next to the threshold.

### Step 4: Include invalid cases as well

Error data is part of the contract. If `subtotal < 0`, state `IllegalArgumentException` as the expectation rather than letting the tester guess a default value. For strings, include `null`, empty, whitespace-only, or special-character cases depending on requirements.

### Step 5: Give cases meaningful names

`F05` is a compact ID, but for large test suites it helps to also have names like `atThresholdRegular` or `blankTagRejected`. Names help distinguish input conditions and the purpose of each case.

If a test has ten different inputs all named `"test1"`, `"test2"`, maintainers have to guess the intent when one fails. In the complete program, IDs correspond to a specific explanatory table in the README.

### Step 6: Choose the comparison based on data type

- Integer primitives, `String`, and `record` types containing only values can be compared with `Objects.equals`.
- Arrays need `Arrays.equals` or `Arrays.deepEquals` depending on dimensions, **not** `Objects.equals` alone to compare elements.
- Floating-point numbers with rounding error need an allowed *tolerance* or an official rounding rule.
- Ordered lists need to compare both **content and order**; Maps are usually compared with `equals` regardless of print order.
- When a result contains `Optional`, distinguish `Optional.empty()` from a missing Map key.
- For exceptions, check the type and, when needed, the message or error code per the contract.

### Step 7: Run the entire table, do not stop at one pretty example

One passing case does not prove the remaining branches. The test table should be run automatically on every logic change, especially when adjusting thresholds or normalization rules.

## 8. How do test tables catch specific bugs?

### Wrong comparison at the threshold

Suppose someone accidentally changes:

```java
if (subtotal > 100_000) {
    return express ? 15_000 : 0;
}
```

instead of `>=`. Cases `F05`, `F06` with `subtotal=100_000` will fail. If the table only had `0` and `180_000`, this bug might go uncaught.

### Inverted boolean condition

If a developer mistakenly writes:

```java
return express ? 10_000 : 25_000;
```

in the below-threshold branch, cases `F01`, `F02`, `F03`, `F04` will catch it. Having both boolean values in the table is a deliberate test design decision, not an accident.

### Omitting `strip()`

If `normalizeTag("  stream  ")` only calls `toUpperCase`, the result will be `"  STREAM  "` instead of `"STREAM"`, and test `T02` fails.

### Removing middle whitespace

If a refactor naively replaces all whitespace with the empty string, `normalizeTag("a b")` returns `"AB"` instead of `"A B"`, and test `T03` fails. This shows that the table needs cases that **remain unchanged by rule**, not just cases that need modification.

### `null` handling bug

If `Objects.requireNonNull(raw)` is removed and it accidentally returns `"null"` or `""`, `E03` fails. If NPE is replaced with IAE, the test also reports a deviation from the current contract. Some APIs choose IAE for null; what matters is that the policy is clearly documented and tested accordingly.

## 9. Upgrading to JUnit 5 `@ParameterizedTest`

In a real Java project, JUnit Jupiter lets you run the same test method with multiple rows of data. This is a common way to avoid writing manual loops and test runners.

The example below is an **excerpt placed inside a test class of a project already configured with JUnit Jupiter and `junit-jupiter-params`**; it is not a standalone Java file that runs with just the `java` command without dependencies. The business functions belong to the `PureFunctionTableTests` class in section 6.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;

class PureFunctionParameterizedTest {
    @ParameterizedTest(name = "subtotal={0}, express={1}, fee={2}")
    @CsvSource({
        "0, false, 10000",
        "0, true, 25000",
        "99999, false, 10000",
        "99999, true, 25000",
        "100000, false, 0",
        "100000, true, 15000",
        "180000, false, 0",
        "180000, true, 15000"
    })
    void feeMatchesTable(
            int subtotal, boolean express, int expected) {
        assertEquals(
                expected,
                PureFunctionTableTests.shippingFee(subtotal, express));
    }

    @ParameterizedTest
    @ValueSource(strings = {" ", " \t ", "\t"})
    void blankTagIsRejected(String raw) {
        assertThrows(IllegalArgumentException.class,
                () -> PureFunctionTableTests.normalizeTag(raw));
    }

    @ParameterizedTest
    @NullSource
    void nullTagIsRejected(String raw) {
        assertThrows(NullPointerException.class,
                () -> PureFunctionTableTests.normalizeTag(raw));
    }
}
```

JUnit's converters parse CSV strings into `int` and `boolean` types. For data containing commas, quotes, `null`, empty strings, or multi-field records, `@MethodSource` usually expresses it more clearly than `@CsvSource`, because it constructs argument objects directly.

Example source method (excerpt, requires importing `Stream`, `Arguments`):

```java
static Stream<Arguments> tagCases() {
    return Stream.of(
            Arguments.of("java", "JAVA"),
            Arguments.of("  stream  ", "STREAM"),
            Arguments.of("a b", "A B"),
            Arguments.of("trà", "TRÀ"));
}

@ParameterizedTest
@MethodSource("tagCases")
void normalizesTags(String raw, String expected) {
    assertEquals(expected, PureFunctionTableTests.normalizeTag(raw));
}
```

Here you need `org.junit.jupiter.params.provider.MethodSource` and `org.junit.jupiter.params.provider.Arguments` along with the JUnit imports for test methods. This illustrates the **structure** inside a test class; it is not a standalone example to copy into a shell. With JUnit, each row is reported as a separate test invocation, so CI results are usually easier to track than a hand-written `for` loop.

**You do not need JUnit to understand table-driven testing**: the complete Java 17 version in section 6 already runs standalone. JUnit is useful when integrating with a build system, lifecycle, reporting, and IDE/CI tools.

## 10. Testing multi-parameter functions and complex results

A pure function does not have to take only one primitive and return one primitive. For example:

```java
record Order(int quantity, int unitPrice) {}
record Receipt(int subtotal, int shippingFee, int total) {}
```

A function `price(Order order, boolean express)` can take an input record and return a `Receipt`; the test table can use:

```java
record PriceCase(
        String id,
        Order order,
        boolean express,
        Receipt expected) {}
```

When a record contains only primitives and `String`, the record-generated `equals` usually supports structural comparison very conveniently. If a record contains a `List` or mutable object, determine data immutability, copy policy, and whether `equals` is appropriate.

If the result is a `List`, only use `List.equals` when business requirements **depend on order**. If the result is grouped by keys, `Map.equals` compares mappings without relying on iteration order, while outputting a report in order must be tested separately via a key list or a `TreeMap`/`LinkedHashMap` structure per the contract.

The test table can also include:

| ID | Input | Expected output |
| --- | --- | --- |
| P01 | Order(2, 40000), false | Receipt(80000, 10000, 90000) |
| P02 | Order(1, 100000), false | Receipt(100000, 0, 100000) |
| P03 | Order(1, 100000), true | Receipt(100000, 15000, 115000) |

This is an **extended specification table**, not cases currently running in `PureFunctionTableTests.java`; you need to implement the `price` function and corresponding tests yourself according to the stated formula.

## 11. Testing exceptions, domain errors, and `null`

A good test table must state clearly **how each row ends**. You should not mix three outcomes without a convention:

- **Valid result**: compare against `expected`.
- **Input rejected by exception**: check the exception type, and possibly the message if the contract requires it.
- **Valid input with no result**: may return `Optional.empty()` or a dedicated `Result` type, not necessarily throwing an exception.

For example, a pure function `parsePositiveInt(String)` may return `OptionalInt.empty()` when the string cannot be parsed. In that case the table must record the exact expected type, not replace it with `0`, because the number 0 and "no number" can carry two different meanings.

Do not use tests like:

```java
try {
    functionWithInvalidInput();
} catch (RuntimeException e) {
    // Any error is accepted.
}
```

It does not verify the error type and does not fail when the function throws nothing. Better is `assertThrows` in JUnit or `checkThrows` in Java Core, as in section 6.

A subtle point: if a test requires the exact exception **message**, changing the wording of the message also breaks the test. Only pin the message when it is part of the API contract; if only the error type matters, check the type to reduce *brittle* tests.

## 12. Repeatability, test case ordering, and shared state

With pure functions, you want each case to stand on its own. If test A must run before test B to set a static variable, you are testing a stateful workflow, **no longer a pure independent input–output mapping table**.

Counterexample:

```java
static int lastSubtotal = 0;

static int shippingFeeWithState(boolean express) {
    return lastSubtotal >= 100_000
            ? (express ? 15_000 : 0)
            : (express ? 25_000 : 10_000);
}
```

`shippingFeeWithState(false)` depends on `lastSubtotal` from the previous run. A table with only `express` and `expected` columns is **missing data** to determine the result. You must refactor so `subtotal` is a parameter, or use a test style that describes both before and after state.

With pure functions, cases can be run in a different order and still produce the same individual result for each case. This is a major advantage when running tests on CI or distributing tests in parallel. However, the **test runner** can still be order-dependent if it writes shared state itself or if each case uses mutable input data. Keep the test table immutable or create fresh data appropriately for each case.

### Do not use system time or random directly inside the function under test

Example function:

```java
static boolean isExpired() {
    return java.time.Instant.now().isAfter(deadline);
}
```

This snippet is a **sketch**; `deadline` must be declared in its enclosing context. The function depends on the clock and external state, so it is not a pure function over its current parameter list. A more testable separation:

```java
static boolean isExpired(
        java.time.Instant now, java.time.Instant deadline) {
    return now.isAfter(deadline);
}
```

An input time table can test before, at, and after the deadline using fixed `Instant` values. Outer-layer code is responsible for calling `Instant.now()` and passing it into the function. This approach not only makes tests stable but also makes every dependency visible.

Similarly, instead of calling `Random` hidden inside a calculation function, pass parameters or pass the random source into the appropriate execution layer; clearly separate the **pure computation** part from the **impure data-fetching** part.

## 13. Combining test tables with function *properties*

The example table checks specific points. You can supplement it with **general invariants** that help catch bugs outside those points.

For `shippingFee` per the specification:

1. Valid inputs have fees in the set `{0, 10000, 15000, 25000}`.
2. For the same `express`, increasing `subtotal` from below to above the threshold does not **increase** the fee.
3. For the same `subtotal`, the express fee is never lower than the regular fee under the current policy.
4. Negative `subtotal` is always rejected.
5. If `subtotal >= 100000`, the regular fee is `0` and the express fee is `15000`.

This is an example of **property-based testing**: instead of checking only a few input–output pairs, we verify relationships or invariants across many inputs. This can be implemented with a loop over systematically chosen values, or with a property-based testing library when the project already has one.

Example of checking an invariant in Java Core (an excerpt inside the same class as `shippingFee`):

```java
for (int subtotal : new int[]{0, 50_000, 99_999,
                               100_000, 100_001, 180_000}) {
    int regular = shippingFee(subtotal, false);
    int express = shippingFee(subtotal, true);

    if (express < regular) {
        throw new AssertionError(
                "express fee unexpectedly lower: " + subtotal);
    }
}
```

Do not replace all **specific expected values** with invariants that are too weak. For example, a function that always returns `0` satisfies "express fee is not lower than regular fee" while still failing most of the table. Table tests and property tests complement each other.

### *Metamorphic relation*

For valid tags in the example, you can check:

```text
normalizeTag(normalizeTag(x)) == normalizeTag(x)
```

This is the expected *idempotent* property for the sample inputs and stated normalization rules. `testTags()` already checks this after each valid case.

If you add complex Unicode normalization steps or other domain rules, re-evaluate the conditions and applicable domain before claiming a property holds for all Unicode strings.

## 14. Optimizing test scope without creating hundreds of duplicate cases

An overly long table with little variety can make maintenance difficult. A reasonable approach is to categorize tests:

| Group | Goal | Example |
| --- | --- | --- |
| Happy path | Normal operation | `subtotal=50000`, `express=false` |
| Boundary | `>` / `>=` mismatches | `99999`, `100000`, `100001` |
| Equivalence classes | Business branches | Regular vs express delivery |
| Invalid input | Rejection policy | `subtotal=-1`, blank tag |
| Special characters | Whitespace/Unicode/locale | `" \t "`, `"trà"` |
| Stable/repeatable | No state dependency detected | Same input called twice |
| Composition | Using function in a pipeline | `Stream.map(PureFunctionTableTests::normalizeTag)` |
| Invariant | General rule | Express fee not lower than regular |

Choose data points **because they are meaningful**, not to hit some arbitrary minimum test count.

If the table is large, you can separate data into CSV/JSON, but you must pay attention to type parsing, Unicode characters, delimiters, error messages, and data ordering. For small tables like this lesson, writing `List.of(new FeeCase(...))` directly in the test is easy to review and avoids I/O dependencies. Testing a pure function does not have to depend on external files.

## 15. Common mistakes in table-driven testing

**Mistake 1 — deriving expectations from the implementation itself.** If expected is computed using the same buggy formula, the test loses value. Base it on business rules or an independent oracle.

**Mistake 2 — testing only the happy path.** Without negative values, null, blank, or values near the threshold, boundary bugs are often missed.

**Mistake 3 — mixing up `>` and `>=`.** Not testing right at the `100000` threshold makes the bug hard to catch.

**Mistake 4 — comparing object results with `==`.** For `String`, `List`, and `record`, understand `equals` and data structures. For arrays, use `Arrays.equals` instead of reference comparison.

**Mistake 5 — catching any exception and treating it as a pass.** A test must fail if no exception is thrown or if the wrong exception type is thrown.

**Mistake 6 — using Java's `assert` keyword without enabling `-ea`.** Java's language `assert` can be disabled; use an assertion framework or explicit check methods like in the example.

**Mistake 7 — tests depending on execution order.** Each case must carry its own complete inputs, without relying on static variables set by a previous case.

**Mistake 8 — comparing `double` results like exact integers.** Floating-point operations have rounding; use an appropriate tolerance or exact-precision rule.

**Mistake 9 — missing ID/caption for cases.** When running 200 rows, you need to identify immediately which case failed in order to debug.

**Mistake 10 — confusing "repeatable result" with "pure function".** A function with side effects that returns a constant is still impure; examine behavior beyond the output.

**Mistake 11 — confusing `null` with the string `"null"`.** They are different; tests must represent both clearly per the contract.

**Mistake 12 — packing multiple rules into one case without knowing which branch is tested.** Each row should have a clear target. You can include multiple conditions, but the case name and expected value must highlight the key behavior.

**Mistake 13 — expecting an unguaranteed Map order.** If the result is just a grouped map, `Map.equals` is usually appropriate. If key order is a requirement, construct and verify the order explicitly.

**Mistake 14 — letting tests generate random-state inputs without a seed/log.** When a failure occurs, the input must be reproducible. Table-driven tests with fixed data provide a stable baseline; random/property tests need a reproduction mechanism.

**Mistake 15 — forgetting to check side effects on mutable input objects.** A function that returns the right List while secretly mutating the source List is no longer pure. In tests, take a snapshot to compare before/after if the input can be mutated.

## 16. When can an impure function still be tested with a table?

An **impure** function can still be tested with a table, but the table must describe sufficient state or environment:

```text
(input, initial state) → (return value, final state, observable effects)
```

For example, a stateful counter needs to test state transitions; a DB service needs to test stored data and write results; a time-dependent API needs a fake clock. This is the broader topic of stateful/integration testing.

For this lesson, prioritize **separating the pure core from the impure shell**:

```text
Read input from network/file    ← I/O, impure
         │
         ▼
Parse/validate into stable data
         │
         ▼
Pure function computes result   ← input/output table
         │
         ▼
Write result to DB/UI           ← I/O, test interaction separately
```

Layering like this keeps algorithm table tests fast, repeatable, and free of system setup, while still allowing the I/O layer to be tested appropriately.

## 17. Practice exercises

1. Add `FeeCase("F09", 100_001, false, 0)` and `FeeCase("F10", 100_001, true, 15_000)`. Explain what testing just above the threshold accomplishes.
2. Temporarily change `subtotal >= 100_000` to `subtotal > 100_000`. Identify the exact cases that fail, then restore the correct code.
3. Temporarily change `normalizeTag` to omit `strip()`. Which cases catch the bug? Which cases still pass?
4. Design a `record TaxCase(int amount, int ratePercent, int expected)` table for an integer tax calculation function. Define rounding rules, overflow, and out-of-range rate handling before writing code.
5. Write `record ClassifyCase(int score, String expected)` for a score classification function. Create tests at thresholds 0, 50, 70, 90, 100 and immediately on both sides of each boundary according to rules you state.
6. Add input cases `"a b"` and `"  a b  "` for `normalizeTag`. Prove that internal whitespace is not accidentally removed.
7. Write a `@ParameterizedTest` using `@MethodSource` for `normalizeTag`; pay attention to how `null` or strings containing commas and tabs are passed.
8. Use a test case table to catch a `countDigits(int)` function that returns wrong results for `0`, negative numbers, and integer limits. Decide the policy for negative numbers before writing expected values.
9. Extract `Instant.now()` out of a deadline-checking function: pass `now` as a parameter. Write a table covering before, exactly at, and after the deadline.
10. From the shipping fee test table, add an invariant check "express fee is not lower than regular fee" for a set of valid subtotals, and compare it with checking only specific outputs.
11. Create a function that intentionally updates a static variable while still returning the right result. Explain why table-driven output tests do not automatically catch every side effect.
12. Create an unmodifiable `List<Case>` containing test cases, run them again in reverse order, and prove that each case's result stays the same when the function is pure and the environment is unchanged.

## 18. Summary

**Testing pure functions with input–output tables** is a method of turning specifications into structured test cases:

- Each row clearly states **input → expected output**, or **input → expected exception**.
- Choose data by **equivalence classes, boundary values, invalid cases, and special-character scenarios**.
- Use `record` and `List.of` to store cases in Java 17; run the same checking logic for every row.
- Attach an ID or case name for clear failure reporting, rather than just printing `true/false`.
- You can migrate the structure to JUnit 5 `@ParameterizedTest`/`@CsvSource`/`@MethodSource` when the project already uses JUnit.
- Supplement with invariant/property checks and repeated calls with the same input, but do not treat them as a **complete proof** of purity.
- Move dependencies such as time, randomness, I/O, and mutable state out of the computation core so that table tests are truly independent and stable.

Good results do not come from the number of rows in the table, but from **each row representing a rule that could go wrong**, expectations being determined independently from the specification, and failures being accurately reproducible.
