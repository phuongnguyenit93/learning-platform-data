# Testing True and False Guards

## 1. Why Must Both Guard Outcomes Be Tested?

Pattern matching in Java separates two decisions that often go together:

1. **Does the pattern match?** For example, is the value under inspection a `Dispatch` record with matching components?
2. **Is the guard true?** After the pattern matches, does the additional condition written with `when` accept that data?

Since **Java 21**, a `switch` branch can combine both parts:

```java
case Dispatch(var destination, int units)
        when destination != null
                && !destination.isBlank()
                && units >= 10 ->
        "EXPRESS";
```

This snippet is an illustrative example inside a `switch` with a declared `Dispatch` record. It does not mean "every `Dispatch` is EXPRESS." Only when the record pattern **matches** and the entire expression after `when` is **true** is the branch selected.

If the guard is false, Java continues checking **subsequent matching cases**; an unguarded `Dispatch` case can handle that value. If the pattern does not match, that case's guard is **not evaluated**.

Three scenarios must be clearly distinguished in tests:

| Scenario | Pattern | Guard | Behavior |
| --- | --- | --- | --- |
| `Dispatch("HN", 12)` object | Matches | `true` | The guarded branch is selected, provided no earlier branch already selected the value. |
| `Dispatch("HN", 0)` object | Matches | `false` | Continues checking subsequent cases. |
| `Cancel` object | Does not match `Dispatch` | Not evaluated | Skips the guard and the `Dispatch` branch. |

Testing only with a value that makes the guard return `true` will fail to catch defects on the `false` path, a missing fallback branch, a wrong comparison operator, or incorrect case ordering. Therefore, tests must verify **both true outcomes, false outcomes, and pattern mismatches**.

## 2. Guard Semantics in Java 21 switch

Consider the records:

```java
sealed interface Event permits Dispatch, Cancel {}
record Dispatch(String destination, int units) implements Event {}
record Cancel(String reason) implements Event {}
```

A business classification method can be written as:

```java
static String classify(Event event) {
    return switch (event) {
        case Dispatch(var destination, int units)
                when destination != null
                        && !destination.isBlank()
                        && units >= 10 ->
                "EXPRESS";

        case Dispatch(var destination, int units)
                when destination != null
                        && !destination.isBlank()
                        && units > 0 ->
                "STANDARD";

        case Dispatch ignored -> "INVALID_DISPATCH";

        case Cancel(var reason)
                when reason != null && !reason.isBlank() ->
                "CANCELLED";

        case Cancel ignored -> "INVALID_CANCEL";

        case null -> "NO_EVENT";
    };
}
```

The snippet above illustrates the complete classification logic and is included in the standalone program in a later section.

There are several key points for test design:

- `when` is evaluated only **after** the pattern of that same case matches.
- If `Dispatch("HN", 10)` satisfies the first guard, the `switch` selects `EXPRESS`; subsequent cases are not evaluated.
- `Dispatch("HN", 9)` fails the first guard, satisfies the second guard, and selects `STANDARD`.
- `Dispatch("HN", 0)` fails both guards and selects `INVALID_DISPATCH`.
- `Cancel("user")` is not a `Dispatch`, so the guards of the two `Dispatch` cases do not run; it proceeds to the `Cancel` cases.
- `null` is a **null selector**, handled by `case null`; this is different from a component inside a record being null.

The unguarded `case Dispatch ignored` branch appears after the two guarded cases. If placed **before** those two cases, it covers every non-null `Dispatch`, causing the more specialized cases after it to be *dominated* and potentially rejected by the compiler.

Because `Event` is a `sealed interface` and its direct subtypes `Dispatch` and `Cancel` are final records, the corresponding unguarded branches cover all non-null variants. `case null` expresses the null-selector policy, so the `switch expression` in this example does not need `default`.

## 3. Required Test Case Categories

### 3.1. Guard True at the Boundary

The condition `units >= 10` must be tested with **`units = 10`**, not only with a large value like `100`. This case catches the bug of replacing `>=` with `>`.

```java
classify(new Dispatch("HN", 10))  // "EXPRESS"
```

The line above is an illustration of a call and its result, not a separate Java class.

### 3.2. Guard False Just Below the Boundary

`units = 9` must fail the `EXPRESS` case while still matching the `STANDARD` case because `units > 0`.

```java
classify(new Dispatch("HN", 9))   // "STANDARD"
```

This tests **both the false-guard path and the fallthrough to the next case**. If a test only asserts that the result is not `EXPRESS` without checking `STANDARD`, it can miss bugs in the fallback branch.

### 3.3. Both Guards False

`units = 0` or negative values must route to `INVALID_DISPATCH`, not fall into `STANDARD` or return an ambiguous generic value.

```java
classify(new Dispatch("HN", 0))   // "INVALID_DISPATCH"
```

The condition `units > 0` has its own boundary: `0` is false, `1` is true. Do not test only `9` and `10` and forget the `0/1` boundary.

### 3.4. One Side of && False

The guard does not only check a numeric condition; it checks that the destination is non-null and non-blank:

```java
destination != null && !destination.isBlank() && units >= 10
```

There should be separate tests for:

- `destination == null`;
- `destination.equals("")`;
- `destination.equals("   ")`;
- valid `destination` but insufficient `units`;
- both data conditions valid.

Because `&&` uses short-circuit evaluation, when `destination == null`, Java does not call `destination.isBlank()`. If the conditions are reversed or `&` is mistakenly used, the method may throw a `NullPointerException` before returning the expected result.

### 3.5. Pattern Mismatch

Test a `Cancel` instance to ensure `Dispatch` logic is not conflated with every `Event` variant. Because the `Dispatch` pattern does not match, the guards of the `Dispatch` cases are not evaluated.

### 3.6. Guard of Another Subtype

`Cancel(var reason) when reason != null && !reason.isBlank()` has a similar pair of tests: a valid reason selects `CANCELLED`; an empty, whitespace-only, or null reason selects `INVALID_CANCEL`.

### 3.7. Null Selector vs. Null Component

The following two cases are **different**:

```java
classify(null)                   // "NO_EVENT"
classify(new Dispatch(null, 10)) // "INVALID_DISPATCH"
```

In the first case, the selector is null and `case null` is selected. In the second case, the `Dispatch` object exists and its `destination` component is null; because **`var destination`** is used, the pattern can bind the null value, and the guard then safely returns `false`.

If changed to `Dispatch(String destination, int units)`, the type pattern `String destination` **does not match** when that component is null. This is why you must identify the exact pattern and test data before concluding whether a case is a false guard or a pattern mismatch.

## 4. Test Matrix for Branches

| Input Data | Expected Branch | Meaning |
| --- | --- | --- |
| `Dispatch("HN", 10)` | `EXPRESS` | Express guard true at the boundary. |
| `Dispatch("DN", 11)` | `EXPRESS` | Express guard true above the boundary. |
| `Dispatch("HN", 9)` | `STANDARD` | Express false, standard true. |
| `Dispatch("HN", 1)` | `STANDARD` | Standard guard true at the lower boundary. |
| `Dispatch("HN", 0)` | `INVALID_DISPATCH` | Both quantity guards false. |
| `Dispatch("HN", -1)` | `INVALID_DISPATCH` | Negative value rejected. |
| `Dispatch("   ", 10)` | `INVALID_DISPATCH` | Destination contains only whitespace. |
| `Dispatch("", 100)` | `INVALID_DISPATCH` | Empty destination even when quantity is large enough. |
| `Dispatch(null, 11)` | `INVALID_DISPATCH` | Null component; guard safe thanks to `&&`. |
| `Cancel("user")` | `CANCELLED` | Different pattern and Cancel guard true. |
| `Cancel(" ")` | `INVALID_CANCEL` | Cancel guard false. |
| `Cancel(null)` | `INVALID_CANCEL` | Null component in Cancel record. |
| `null` | `NO_EVENT` | Null selector, not a record. |

This table specifies **exact outcomes**, rather than merely asserting that the method "does not fail." With overlapping guards such as `units >= 10` and `units > 0`, an input of `10` satisfies both expressions independently, but **the first matching case is selected**, so the test must assert `EXPRESS`.

Beyond data-driven test cases, you must also test **precedence order** and **fallback branch semantics**, because a false guard does not necessarily mean the entire `switch` fails.

## 5. Complete Java 21 Program with Self-Running Test Suite

Create the file **`GuardTruthTableDemo.java`**. The program below has no test-framework dependencies, uses `AssertionError` to halt when an actual result differs from expected, and prints a `PASS` message for each passing case.

```java
public class GuardTruthTableDemo {
    sealed interface Event permits Dispatch, Cancel {}

    record Dispatch(String destination, int units) implements Event {}

    record Cancel(String reason) implements Event {}

    static boolean validDestination(String destination) {
        return destination != null && !destination.isBlank();
    }

    static boolean validReason(String reason) {
        return reason != null && !reason.isBlank();
    }

    static String classify(Event event) {
        return switch (event) {
            case Dispatch(var destination, int units)
                    when validDestination(destination) && units >= 10 ->
                    "EXPRESS";

            case Dispatch(var destination, int units)
                    when validDestination(destination) && units > 0 ->
                    "STANDARD";

            case Dispatch ignored ->
                    "INVALID_DISPATCH";

            case Cancel(var reason) when validReason(reason) ->
                    "CANCELLED";

            case Cancel ignored ->
                    "INVALID_CANCEL";

            case null ->
                    "NO_EVENT";
        };
    }

    static void check(String name, Event input, String expected) {
        String actual = classify(input);
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println("PASS " + name + " -> " + actual);
    }

    public static void main(String[] args) {
        check("express-at-10", new Dispatch("HN", 10), "EXPRESS");
        check("express-above-10", new Dispatch("DN", 11), "EXPRESS");

        check("standard-at-9", new Dispatch("HN", 9), "STANDARD");
        check("standard-at-1", new Dispatch("HN", 1), "STANDARD");

        check("zero", new Dispatch("HN", 0), "INVALID_DISPATCH");
        check("negative", new Dispatch("HN", -1), "INVALID_DISPATCH");
        check("blank-destination", new Dispatch("   ", 10),
                "INVALID_DISPATCH");
        check("empty-destination", new Dispatch("", 100),
                "INVALID_DISPATCH");
        check("null-destination", new Dispatch(null, 11),
                "INVALID_DISPATCH");

        check("cancel-valid", new Cancel("user"), "CANCELLED");
        check("cancel-blank", new Cancel(" "), "INVALID_CANCEL");
        check("cancel-null", new Cancel(null), "INVALID_CANCEL");

        check("null-selector", null, "NO_EVENT");
    }
}
```

**Requirements:** JDK 21 or later. Compile and run without `--enable-preview`:

```bash
javac -encoding UTF-8 GuardTruthTableDemo.java
java GuardTruthTableDemo
```

Exact output when all tests pass:

```text
PASS express-at-10 -> EXPRESS
PASS express-above-10 -> EXPRESS
PASS standard-at-9 -> STANDARD
PASS standard-at-1 -> STANDARD
PASS zero -> INVALID_DISPATCH
PASS negative -> INVALID_DISPATCH
PASS blank-destination -> INVALID_DISPATCH
PASS empty-destination -> INVALID_DISPATCH
PASS null-destination -> INVALID_DISPATCH
PASS cancel-valid -> CANCELLED
PASS cancel-blank -> INVALID_CANCEL
PASS cancel-null -> INVALID_CANCEL
PASS null-selector -> NO_EVENT
```

### Why Does This Program Test Both True and False Guards?

- The first two lines verify that **the EXPRESS branch's guard is true** at and above the threshold. This proves the right branch is selected, not merely that a boolean expression returns true.
- The next two lines show that **the EXPRESS guard is false**, while **the STANDARD guard is true**; the result is not erroneously returned as `INVALID_DISPATCH`.
- The five lines `zero`, `negative`, `blank-destination`, `empty-destination`, and `null-destination` confirm that **neither guarded Dispatch case is selected**, and the well-defined fallback branch is triggered.
- The three `Cancel` lines confirm that a different pattern is handled independently; the `Cancel` guard has both true and false outcomes.
- The last line confirms that a null selector enters `case null`, rather than being confused with a null component.

The `check` method compares the expected value directly with the actual value. If a case fails, it throws `AssertionError` and execution stops; therefore, the program never prints "PASS" for a failing check.

Unlike relying on Java's `assert` keyword, manual checking with `if (!expected.equals(actual)) throw new AssertionError(...)` **always runs**. The standard `assert` keyword can be disabled when `-ea` is not enabled, so if you choose to use `assert`, you must know your project's test execution policy.

## 6. Testing Conditions Independently from Switch Branch Testing

Suppose the guard is:

```java
when validDestination(destination) && units >= 10
```

We have two complementary types of tests:

**A. Unit tests for the predicate.** For example, `validDestination(null)` returns `false`, `validDestination("   ")` returns `false`, and `validDestination("HN")` returns `true`. These tests verify that the condition helper works properly.

**B. Tests for case selection.** For example, `Dispatch("HN", 9)` must return `STANDARD`, not merely "not EXPRESS." The outcome also depends on **case ordering** and subsequent guards, which standalone predicate unit tests cannot verify.

Do not test only `validDestination` and assume the `switch` branch is definitely right. Likewise, do not test only a single input `Dispatch("HN", 100)` and conclude that every clause in the guard has been exercised.

Factoring predicates into **pure** functions keeps both test layers simpler: identical inputs produce identical outputs, without guessing whether internal state changed after each run.

## 7. Converting Test Cases to JUnit 5

In a project using **JUnit Jupiter (JUnit 5)**, boundary values can be converted into a parameterized test. The following example is **an illustrative test file** named `GuardTruthTableTest.java`, in the same package as `GuardTruthTableDemo.java`; it requires JUnit Jupiter and JUnit Platform dependencies configured in the project's build tool. It is **not** part of the standalone program in Section 5 and cannot be compiled with plain `javac` without JUnit.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GuardTruthTableTest {
    @ParameterizedTest
    @CsvSource({
        "0, INVALID_DISPATCH",
        "1, STANDARD",
        "9, STANDARD",
        "10, EXPRESS",
        "11, EXPRESS"
    })
    void unitsBoundaries(int units, String expected) {
        var event = new GuardTruthTableDemo.Dispatch("HN", units);
        assertEquals(expected, GuardTruthTableDemo.classify(event));
    }

    @Test
    void nullDestinationFallsBack() {
        var event = new GuardTruthTableDemo.Dispatch(null, 11);
        assertEquals("INVALID_DISPATCH",
                GuardTruthTableDemo.classify(event));
    }

    @Test
    void cancelWithoutReasonIsInvalid() {
        var event = new GuardTruthTableDemo.Cancel("   ");
        assertEquals("INVALID_CANCEL",
                GuardTruthTableDemo.classify(event));
    }

    @Test
    void nullSelectorUsesItsOwnCase() {
        assertEquals("NO_EVENT", GuardTruthTableDemo.classify(null));
    }
}
```

This test snippet has two benefits: each boundary value is declared transparently, and when a mismatch occurs, JUnit reports **expected/actual** for that specific case. In addition to the tests above, you should add tests for negative values, null reasons, and other condition combinations in a production test suite.

If a project needs to test a branch that throws an exception, `assertThrows` is appropriate for contract violations. However, **a false guard is not an exception by default**. In this article's example, a false guard selects a fallback case with a well-defined result; therefore `assertEquals` checking the branch outcome is more appropriate.

## 8. Boundary Value Testing: More Important Than "One True Case, One False Case"

Comparison operators create boundaries that can break during refactoring:

| Condition | Value just below | Value at boundary | Value just above |
| --- | --- | --- | --- |
| `units >= 10` | 9: false | 10: true | 11: true |
| `units > 0` | -1: false | 0: false | 1: true |
| `units <= 5` | 4: true | 5: true | 6: false |
| `units == 10` | 9: false | 10: true | 11: false |

For the compound condition `validDestination(destination) && units >= 10`, test each clause that can flip the decision:

- Valid destination, insufficient units: `("HN", 9)` ⇒ guard false.
- Invalid destination, sufficient units: `("", 10)` ⇒ guard false.
- Both valid: `("HN", 10)` ⇒ guard true.
- Null destination: `(null, 10)` ⇒ guard false **without throwing an exception**.

This aligns with *condition coverage* thinking: testing sub-conditions that drive both true and false outcomes. It is not a proof that an infinite number of execution paths are covered; tests are chosen based on the domain contract and error-prone boundaries.

## 9. Mistakes That Guard Tests Must Catch

### 9.1. Wrong Comparison Operator

`units > 10` instead of `units >= 10` differs only at the boundary `10`. A test case with `units = 100` does not catch that bug; `10` does.

### 9.2. Wrong Case Ordering

If two guards can both be true, Java selects the **first matching case**. Here, a quantity of `10` satisfies both `>= 10` and `> 0`. Therefore, the `EXPRESS` case must appear before `STANDARD`. If the order is reversed, `10` may be classified as `STANDARD` even though each individual guard is written correctly.

An unguarded case such as `case Dispatch ignored` placed before a guarded case will shadow subsequent branches and can cause a *dominated case* compile-time error. Runtime testing does not replace compiling with the target Java version.

### 9.3. Not Handling Null in the Guard

Calling `destination.isBlank()` when `destination == null` throws a `NullPointerException`. A guard that **throws an exception** does not mean the guard returns false and Java automatically moves to the next case; the exception interrupts evaluation through normal exception propagation. Thus, testing a null component is crucial.

The safe idiom shown here is `destination != null && !destination.isBlank()`. When a component is bound with `var`, null checking is the guard expression's responsibility if the API allows null values.

### 9.4. Only Checking That the Method Does Not Throw an Exception

Suppose a refactor causes `Dispatch("HN", 9)` to return `INVALID_DISPATCH` instead of `STANDARD`. Both results are valid strings and the program throws no exception. A "does not throw" test would still PASS; only an **expected outcome test** catches the wrong branch.

### 9.5. Overusing default and Hiding Missing Cases

A `default -> "UNKNOWN"` easily causes tests to miss new subtypes in a sealed hierarchy. If the domain is closed, list unguarded cases covering each subtype so the compiler checks exhaustiveness when the model structure changes. If the interface is open, `default` or a general case may be reasonable, but there must be an explicit policy and tests for unknown implementations.

### 9.6. Assuming a Guard Runs Only Once

When an earlier case's pattern matches but its guard is false, Java may continue trying later cases and evaluating another guard. In this example, `validDestination(destination)` can be called in two `Dispatch` cases for an object with a small `units` value. Because predicates are designed to be pure, repeated evaluation does not change the result.

Do not put data writes, event emissions, or state updates inside `when` and expect them to run only once per `switch`. If call-count monitoring is required, add a separate controlled test, but **avoid putting side effects into business guards** just for testing convenience.

## 10. Testing Throwing Predicates vs. False Guards

In Java, a **false guard** and a **throwing guard** have different consequences:

- Guard returns `false`: the case is not selected, and evaluation moves to the next applicable case.
- Guard throws an exception: `switch` evaluation is interrupted by the exception, unless handled by an enclosing exception handler.

To test a guard that can throw domain errors (such as accessing a service or performing validation), define a clear policy: should the exception propagate, be converted to an error result, or be caught at a boundary? Do not accidentally write `catch (Exception ex) { return "STANDARD"; }` and turn every error into a normal business outcome.

In your test suite, separate:

1. **Valid false cases** — e.g., `units = 9` leading to `STANDARD`;
2. **Invalid data cases** — e.g., `units = 0` leading to `INVALID_DISPATCH`;
3. **Exceptional error cases** — if a guard method can genuinely throw an exception, use `assertThrows` or equivalent to verify the exact type and reason according to the contract.

This separation prevents tests from conflating "not matching," "not qualifying," and "execution failure."

## 11. Self-Check

Suppose you have:

```java
record Score(String subject, int points) {}
```

Write a `switch` such that:

- `Score("Java", 80)` returns `PASS`;
- `Score("Java", 79)` returns `RETRY`;
- `Score("SQL", 90)` returns `OTHER_SUBJECT`;
- `null` returns `NO_SCORE`.

A Java 21 solution:

```java
static String scoreStatus(Score score) {
    return switch (score) {
        case Score(var subject, int points)
                when "Java".equals(subject) && points >= 80 ->
                "PASS";
        case Score(var subject, int points)
                when "Java".equals(subject) ->
                "RETRY";
        case Score ignored ->
                "OTHER_SUBJECT";
        case null ->
                "NO_SCORE";
    };
}
```

This snippet is an illustrative method, assuming the `Score` record is already declared in the same scope.

The four cases above test, in order: first guard true; first guard false but second guard true; both guards false; null selector. Add `Score(null, 90)` to verify null-subject handling: because `var subject` is used, `"Java".equals(subject)` safely returns false and the result is `OTHER_SUBJECT`.

In real-world testing, avoid concluding solely from "the code runs": compare the exact result against the design and place values right at the condition boundaries.

## 12. Checklist Before Concluding a Guard Is Fully Tested

1. Is there at least one **pattern match + guard true** test for every case with `when`?
2. Is there a **pattern match + guard false** test that verifies the **specific next case**?
3. Is there a **pattern mismatch** test to ensure the guard is not applied to the wrong object?
4. Have values **just below, at, and just above** every critical threshold been tested?
5. Have **null components, empty strings, whitespace-only strings, zero, and negative numbers** been tested when the domain allows them?
6. Has **case ordering** been tested when guards overlap?
7. Is there a separate test for a **null selector** if the contract supports or rejects null?
8. Are **false guards**, **invalid-data results**, and **actual exceptions** separated?
9. Are **expected/actual** values compared, rather than just checking "does not throw"?
10. Has the code been compiled with the target JDK to ensure patterns, `when`, and `switch` conform to the Java version in use?

**Remember:** Testing guards is not just passing one input that makes `when` true and one input that makes `when` false. You must verify **whether the pattern matches**, **the next case after a false guard**, **boundary and null values**, **case precedence order**, and **contract-defined outcomes or exceptions**. That way, pattern matching for `switch` in Java 21 stays both concise and reliable as business rules evolve.
