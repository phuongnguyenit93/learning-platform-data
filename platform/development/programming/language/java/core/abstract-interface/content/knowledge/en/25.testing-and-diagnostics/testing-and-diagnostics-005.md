# Testing Invariants, Null, Exceptions, and Boundary Behavior

## Objectives

Good testing needs to verify both correct results and how a program responds when data is invalid or falls into special cases. In Java, four categories to pay attention to are object invariants, `null` inputs, exceptions, and boundary values.

This article introduces how to identify the contract to test and design meaningful test cases, and uses a standalone Java 17 example for illustration. At the end, there is an equivalent JUnit 5 sample to apply in real-world projects.

## 1. Start from the Program's Contract

Before writing tests, describe what must always be true for an object or method. A contract may include:

- **Precondition:** input conditions that must be met, such as a parameter not being `null` or a numeric range having a lower bound no greater than its upper bound.
- **Invariant:** conditions that must hold true for the valid state of an object throughout its public lifecycle.
- **Postcondition:** the result or state that must be achieved after the method completes successfully.
- **Error behavior:** the type of exception thrown when input conditions are not met, or how errors are reported according to the contract.

A useful test verifies behavior that the caller can observe. Tests should not depend on private implementation details if those details are not part of the public contract.

### Arrange–Act–Assert Structure

A test should be separated into three parts:

1. **Arrange:** create the data and objects to be tested.
2. **Act:** call the method or perform the action.
3. **Assert:** verify the expected result, state, or exception.

Separating the three parts makes a test easy to read and, when it fails, makes it easy to identify which condition was not met. Each test should focus on one primary behavior; related checks can be grouped using tools such as `assertAll` in JUnit.

## 2. Testing Invariants

An invariant is a condition that must always hold true for every valid state of an object. It is usually enforced in the constructor and in methods that mutate state. For immutable objects, the constructor is the key point because state is established once and never changes afterward.

For example, an object representing an integer range might require:

`min <= max`

If `min` is greater than `max`, the object should not be created successfully. An invariant can be tested with two groups of tests:

- **Valid cases:** the lower bound equals the upper bound, or the lower bound is less than the upper bound.
- **Invalid cases:** the lower bound is greater than the upper bound, and the constructor must throw an exception according to the contract.

When an object has multiple state-mutating methods, checking invariants after each type of public operation can detect bugs that corrupt state. There is no need to re-check every internal detail; verify the conditions that affect caller behavior.

## 3. Testing Null Inputs

In Java, reference variables can hold the value `null`. Every API must clearly specify whether `null` is valid or not:

- If `null` is a valid input, test the corresponding result and state.
- If `null` is disallowed, test to verify that the method rejects it according to the contract, typically with a `NullPointerException`.
- If an optional parameter is represented using `Optional`, test both the `Optional.empty()` case and the present-value case when both are part of the contract.

`Objects.requireNonNull(value, "value")` is a common way to reject `null` with a clear error. You should not assume by default that every parameter must reject `null`; the decision must come from the API's contract. You should also not catch `NullPointerException` and ignore it, as that can hide programming bugs.

A `null` test should call the public method directly with `null` and verify the promised behavior. If you only verify that the program does not crash on a normal execution path, the test may miss the contract for handling invalid inputs.

## 4. Testing Exceptions

When an operation cannot complete, Java can throw an exception. Tests should verify that the right type of exception is thrown in the right situation:

- Invalid data typically uses `IllegalArgumentException` or a more specific type according to the contract.
- Disallowed `null` references typically result in a `NullPointerException`.
- I/O errors can be represented by `IOException` or an appropriate subtype.
- An object state that does not permit the operation can be represented by `IllegalStateException`, if that is the chosen contract.

Do not just check that "some exception was thrown." A test that catches too broadly, such as `catch (Exception)`, can accidentally accept unrelated errors. In JUnit, `assertThrows(ExpectedType.class, executable)` verifies the expected exception type and returns the exception for further inspection if needed.

Only check the exception message when that message is part of the contract or provides real value to the caller. If the message is merely an internal detail, checking the exception type is more resilient as the code is maintained. For checked exceptions, the method signature and how the test invokes it must also follow Java's rules.

Additionally, tests must distinguish between two cases: an exception is thrown as expected, and the method completes normally. If no exception is thrown when the test requires one, the test must fail.

## 5. Testing Boundary Behavior

Bugs often appear at the boundaries of conditions, so do not test only a value in the middle of the valid domain. For a closed range from `min` to `max`, the notable values are:

- `min`: the smallest valid value.
- `max`: the largest valid value.
- `min - 1`: just below the lower bound, provided the calculation does not overflow.
- `max + 1`: just above the upper bound, provided the calculation does not overflow.

You need to clearly determine whether the boundaries include the endpoints. For a closed range, both `min` and `max` belong to the range. For a half-open range `[min, max)`, the upper bound does not belong to the range. Tests must reflect that definition accurately.

Other boundary categories depending on the data type:

| Data Type | Cases to Consider |
|---|---|
| Integers | Minimum/maximum supported values, 0, negative numbers, just inside and outside the limits |
| Strings | `null`, empty string, whitespace-only string, minimum/maximum length, Unicode characters |
| Collections | `null`, empty, one element, multiple elements |
| Dates and times | Just before/at/just after a threshold, end of month, leap year, time zone if relevant |
| Pagination | First page, last page, size 0 if allowed, out-of-range index |
| Resources | Unopened, open, and closed states; repeated operations per the contract |

Avoid creating `min - 1` or `max + 1` if those calculations could overflow. For domains near `Integer.MIN_VALUE` or `Integer.MAX_VALUE`, design tests directly for the extreme values instead of computing a value outside the data type.

## 6. Standalone Java 17 Example

The example below creates a record `IntRange` representing a closed range. Its invariant is `min <= max`. The `contains` method accepts an `Integer` to illustrate the `null` contract, and checks both bounds.

Save the entire code to `Main.java`:

~~~java
import java.util.Objects;

record IntRange(int min, int max) {
    IntRange {
        if (min > max) {
            throw new IllegalArgumentException("min must be <= max");
        }
    }

    boolean contains(Integer value) {
        Objects.requireNonNull(value, "value");
        return value >= min && value <= max;
    }
}

public class Main {
    private static int passed = 0;

    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError("FAIL: " + name);
        }
        passed++;
        System.out.println("PASS: " + name);
    }

    private static <T extends Throwable> T expectThrows(
            Class<T> expectedType, Runnable action, String name) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (expectedType.isInstance(actual)) {
                passed++;
                System.out.println("PASS: " + name);
                return expectedType.cast(actual);
            }
            throw new AssertionError(
                    name + " expected " + expectedType.getSimpleName()
                            + " but got " + actual, actual);
        }
        throw new AssertionError(
                name + " expected " + expectedType.getSimpleName()
                        + " but nothing was thrown");
    }

    public static void main(String[] args) {
        IntRange range = new IntRange(10, 20);

        check("lower boundary is included", range.contains(10));
        check("upper boundary is included", range.contains(20));
        check("below lower boundary is excluded", !range.contains(9));
        check("above upper boundary is excluded", !range.contains(21));

        expectThrows(IllegalArgumentException.class,
                () -> new IntRange(20, 10),
                "invalid range violates invariant");
        expectThrows(NullPointerException.class,
                () -> range.contains(null),
                "null input is rejected");

        System.out.println("All " + passed + " checks passed.");
    }
}
~~~

Compile and run with JDK 17 or later:

~~~text
javac Main.java
java Main
~~~

Exact standard output:

~~~text
PASS: lower boundary is included
PASS: upper boundary is included
PASS: below lower boundary is excluded
PASS: above upper boundary is excluded
PASS: invalid range violates invariant
PASS: null input is rejected
All 6 checks passed.
~~~

In the example, the constructor rejects an inverted range before an invalid object can be created. The first two tests verify that the closed range includes both the lower and upper bounds; the next two tests verify that values just outside the range are excluded. The last two tests verify that inputs violating the contract produce the right exception type.

The `expectThrows` method is just a small helper for the standalone example, not a testing library replacing JUnit. It throws an `AssertionError` if no exception is thrown or if the wrong exception type is thrown, so the program cannot print the success report when a check fails.

## 7. How to Write Similar Tests with JUnit 5

In a project using JUnit 5, place the class under test and the test class according to the project structure. The example below assumes `IntRange` is in the same package and accessible from the test:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class IntRangeTest {
    @Test
    void includesBothBoundaries() {
        IntRange range = new IntRange(10, 20);

        assertTrue(range.contains(10));
        assertTrue(range.contains(20));
    }

    @ParameterizedTest
    @ValueSource(ints = {9, 21})
    void excludesValuesOutsideRange(int value) {
        IntRange range = new IntRange(10, 20);

        assertFalse(range.contains(value));
    }

    @Test
    void rejectsInvertedRange() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new IntRange(20, 10));
    }

    @Test
    void rejectsNullValue() {
        IntRange range = new IntRange(10, 20);

        assertThrows(
                NullPointerException.class,
                () -> range.contains(null));
    }
}
~~~

`@Test` marks a test. `@ParameterizedTest` runs the same behavior with multiple inputs, in this example the two values outside the range. `@ValueSource` provides the data for each run. `assertThrows` verifies the expected exception type; if no exception is thrown or the type does not match, the test fails.

The JUnit snippet above is test code for a project already configured with JUnit 5, not a standalone program that can be run with just the default `javac`. Use the project's build system (such as Maven or Gradle) to add JUnit and run the test suite. The standalone example in the previous section requires no external libraries.

## 8. Test Quality and Failure Diagnostics

A good test should fail for a clear reason when behavior breaks. Apply the following principles:

- **Name tests after behavior:** such as `rejectsInvertedRange`, instead of `test1`.
- **Give each test a clear focus:** avoid bundling multiple unrelated behaviors into one long test.
- **Use deterministic data:** do not depend on real time, the network, or shared state unless that is the goal of the test.
- **Verify observable results:** output, public state, exception types, and side effects that are part of the contract.
- **Avoid catching exceptions too broadly:** do not let unexpected errors be treated as success.
- **Keep tests independent:** one test should not need to run after another test in order to succeed.
- **Read failure messages:** identify the input, expected value, actual value, and failure location before fixing the code.
- **Rerun related test groups:** after a fix, confirm that the new test and neighboring behaviors remain correct.

Do not write tests only for the success path. Exception and boundary tests often clarify the API's contract better, though you should also avoid asserting on details that are not guaranteed. For example, if the contract only requires rejecting invalid data, testing the exception type may be sufficient; checking the exact message string should only be done when that message carries public meaning.

## Suggested Testing Workflow

1. Write down the invariants, input conditions, expected results, and expected error behavior.
2. Create at least one valid case and one invalid case for each important contract.
3. For limits, test right at the bound and immediately outside the bound on both sides where applicable.
4. Test `null` according to the contract of each reference parameter.
5. Use `assertThrows` or an equivalent exception assertion helper to verify the error type.
6. Run the tests, read any failures, fix the cause, and then rerun the related tests.

## Key Takeaways

Invariants define which states are considered valid; `null` testing verifies the input contract; exception testing verifies how errors are reported; and boundary testing focuses on values right at and around limits. Combining these four categories helps uncover many bugs that checking only a few typical results would miss.
