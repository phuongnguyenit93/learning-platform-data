# Choosing a Testable `case` Structure in Java Pattern Matching

**Topic:** Java Core Pattern Matching → Case label  
**Version:** Java 21 and later. Pattern matching for `switch` is finalized in Java 21 (JEP 441); the examples in this lesson do not require `--enable-preview`.

## 1. Goal: Write `case` Branches to Easily Test Each Behavior

A `switch` with type patterns solves the problem of classifying multiple data shapes: `case String s`, `case Number n`, `case SomeRecord r`, etc. However, **syntactically valid does not mean easy to test**. A `switch` becomes hard to test when multiple branches overlap, guards contain side effects, `null` data is handled implicitly, or a branch both makes a decision and calls a database/network.

A good structure creates a **clear mapping from input to output**. Given the same input value, the classification function returns an observable, deterministic result; tests can call that function directly without starting a web server, mocking a database, or waiting for console output.

After this lesson, you can:

- Choose between a `switch` expression using `->` and a `switch` statement using `case ...:`.
- Design `case` branches by type groups, `when` conditions, general branches, and `null` boundaries.
- Avoid **dominance** errors and control **exhaustiveness** with a sealed hierarchy.
- Turn the branch table into tests with concrete expected results, including boundary cases.
- Separate classification from I/O and side effects for independent testing.

## 2. Prefer a `switch` Expression Returning a Clear Result

When the goal is to **transform one input into one output**, a `switch` expression is usually easier to test than a long `switch` statement that mutates local variables and invokes multiple services.

Example with an `Object` input:

```java
static String describe(Object input) {
    return switch (input) {
        case null -> "MISSING";
        case String text when text.isBlank() -> "BLANK";
        case String text -> "TEXT:" + text.length();
        case Integer number -> "INT:" + number;
        default -> "OTHER";
    };
}
```

Each `case` label represents one branch selection condition and **one return value**. Simply calling `describe(input)` and comparing the actual string with the expected string already gives a useful test.

Characteristics that keep tests simple:

1. `input` is the sole parameter, independent of global state.
2. `switch` is evaluated to produce a single value; no `result` variable is updated from multiple places.
3. Each branch has a distinguishable result, avoiding situations where many test cases "all return the same value" and make branch-ordering bugs hard to detect.
4. The `case null` branch states the `null` handling policy explicitly.
5. `default` covers unlisted input types.

If a branch needs multiple statements to build the result, use a block with `yield`:

```java
case String text -> {
    int length = text.length();
    yield "TEXT:" + length;
}
```

The snippet above is **an illustrative branch**, not a standalone runnable program. In a `switch` expression, `yield` provides the value for the expression itself; do not use `break` with a value in place of `yield`.

### When to use a `switch` statement?

A `switch` statement is appropriate when the operation is truly control flow or performing actions, though it usually has to be tested by observing side effects. For classification problems, consider splitting into two steps:

```java
Decision decision = classify(event); // Pure function, easy to unit test.
applyDecision(decision);             // Separate I/O or business action.
```

Here `Decision` is a data result; `applyDecision` is only an **architectural illustration** that needs to be defined by the real application and is not included in the sample runnable program below. This separation does not forbid `switch` statements, but helps you pick the form that matches what you need to test.

## 3. Design Branches by Type: Specific First, General Later

A type pattern `case Type variable` checks the type and provides a typed variable for that branch. The **dominance** rule prevents branches from being completely shadowed by earlier branches.

Example that **does not compile**:

```java
// Part of switch(Object input), INVALID due to dominance:
case Number n -> "NUMBER";
case Integer i -> "INTEGER";
```

Because `Integer` is a `Number`, the later `Integer` branch never has a chance to be selected. Fix:

```java
case Integer i -> "INTEGER";
case Number n -> "NUMBER";
```

In tests, there should be at least one `Integer` and one `Double` to prove both branches can be selected, rather than only testing an arbitrary `Number`.

A readable structure is:

- **Special branches:** `case Type x when condition` for invalid or boundary data.
- **General type branch:** `case Type x` to cover the rest of that type.
- **Supertype branch:** for example `case Number n` after specialized numeric types.
- **Remaining policy:** `default` or the type patterns of a sealed hierarchy.

The bullets above represent a design order, not a requirement that every `switch` must have all label forms.

## 4. `when` Guards: Partition the Data Domain into Testable Groups

A `when` guard is evaluated **only after the type pattern matches**. Use short guards without side effects and with easy-to-construct test data.

Example:

```java
case Integer n when n < 0 -> "NEGATIVE";
case Integer n when n == 0 -> "ZERO";
case Integer n -> "POSITIVE";
```

These three branches partition `Integer` values into three clear domains. The natural test suite is **-1, 0, 1**; you can add `Integer.MIN_VALUE` and `Integer.MAX_VALUE` if the business logic handles numbers at the boundaries.

Note: the final `case Integer n` must appear **after** the two guarded branches so it does not shadow them. Even though the three integer domains are disjoint, placing `when` branches in a readable order helps testers see the partitioning logic.

Avoid guards that both check and perform I/O:

```java
// Example to avoid in classification logic:
// case Order o when repository.save(o) -> ...
```

If a guard mutates data, tests must control external state, and reordering branches can change side effects. Replace it with a pure condition such as `o.total() > 0` and move the persistence operation to the processing layer after `switch` returns a decision.

For complex guards, you can use a pure helper `isEligible(order)`. The helper must still produce deterministic results and be tested separately. **Do not write `when` like a complex query language**: the shorter the condition, the easier each case is to isolate.

## 5. `null` Must Be a Separate Test Case

A type pattern `case String s` does not match when the selector is `null`. In a Java 21 pattern `switch`, without an appropriate `null`-handling label, a `null` selector usually causes the `switch` to throw a `NullPointerException` before entering regular branches. **`default` alone does not catch `null`**.

Both policies can be valid if designed intentionally:

```java
case null -> new Decision("MISSING", "null input");
```

Or check `null` before calling `switch` and reject the input according to the API contract. The choice depends on requirements, but tests must clearly state whether `null` is valid or an error.

For record objects, distinguish between an **outer record being `null`** and an **inner component being `null`**. For example, `new TextEvent(null)` is still a `TextEvent` object and matches `case TextEvent t`; however, `t.text()` returns `null`. Place the component guard before any guard that calls `isBlank()`:

```java
case TextEvent t when t.text() == null -> "MISSING_TEXT";
case TextEvent t when t.text().isBlank() -> "BLANK_TEXT";
case TextEvent t -> "TEXT";
```

These are **illustrative branches of a `switch`**; the `TextEvent` definition will appear in the complete example. If the `isBlank()` branch is placed first, the input `new TextEvent(null)` can throw a `NullPointerException`. A test for this input will catch branch-ordering mistakes.

## 6. Exhaustiveness: Use Sealed Types When the Set of Variants Is Closed

For an API with a fixed set of events, a `sealed interface` lets the compiler know which subtypes are permitted and check whether the `switch` expression covers all of them.

```java
sealed interface Event permits TextEvent, PaymentEvent, PingEvent {}

record TextEvent(String text) implements Event {}
record PaymentEvent(int cents) implements Event {}
record PingEvent() implements Event {}
```

A `switch` over `Event` that has an unguarded branch for **each permitted subtype** is exhaustive without requiring `default`. `when` branches subdivide a subtype by condition; because a guard can evaluate to `false`, they **do not replace** the catch-all branch for the remaining values of that subtype.

Maintenance and testing benefit: if you later add a subtype to `permits` and recompile, the compiler can require updating any `switch` missing a branch. If you leave an unconditional `default -> "UNKNOWN"`, a new subtype can be silently absorbed and existing tests will not notice that dedicated business behavior is missing.

Therefore:

- For **open type sets** like `Object`, `default` is usually necessary to make the expression exhaustive.
- For **closed sealed hierarchies**, consider listing all subtypes and letting the compiler help catch new cases, while handling `null` explicitly per contract.
- Do not remove `default` mechanically when requirements genuinely call for a fallback policy, or when the compiler cannot prove exhaustiveness.

Note: exhaustiveness of type patterns and the policy for a `null` selector are two separate concerns. A `switch` that is exhaustive over all subtypes can still throw `NullPointerException` if no `null` branch is designed.

## 7. Complete Java 21 Program: One Function, Eight Transparent Tests

Problem: classify three event types `TextEvent`, `PaymentEvent`, `PingEvent`, as well as `null` input. We return `Decision`, an immutable record with two fields `code` and `detail`, so tests can compare both accurately.

**Create the file `TestableCaseDesignDemo.java`:**

```java
public class TestableCaseDesignDemo {
    sealed interface Event permits TextEvent, PaymentEvent, PingEvent {}

    record TextEvent(String text) implements Event {}
    record PaymentEvent(int cents) implements Event {}
    record PingEvent() implements Event {}

    record Decision(String code, String detail) {}

    static Decision classify(Event event) {
        return switch (event) {
            case null -> new Decision("MISSING_EVENT", "null");

            case TextEvent t when t.text() == null ->
                    new Decision("MISSING_TEXT", "null");
            case TextEvent t when t.text().isBlank() ->
                    new Decision("BLANK_TEXT", "blank");
            case TextEvent t ->
                    new Decision("TEXT_LENGTH",
                            String.valueOf(t.text().length()));

            case PaymentEvent p when p.cents() < 0 ->
                    new Decision("NEGATIVE_PAYMENT",
                            String.valueOf(p.cents()));
            case PaymentEvent p when p.cents() == 0 ->
                    new Decision("ZERO_PAYMENT", "0");
            case PaymentEvent p ->
                    new Decision("POSITIVE_PAYMENT",
                            String.valueOf(p.cents()));

            case PingEvent p -> new Decision("PING", "pong");
        };
    }

    static void check(String label, Event input, Decision expected) {
        Decision actual = classify(input);
        if (!expected.equals(actual)) {
            throw new AssertionError(label
                    + ": expected " + expected + ", got " + actual);
        }
        System.out.println(label + " => "
                + actual.code() + ":" + actual.detail());
    }

    public static void main(String[] args) {
        check("null event", null,
                new Decision("MISSING_EVENT", "null"));
        check("null text", new TextEvent(null),
                new Decision("MISSING_TEXT", "null"));
        check("blank text", new TextEvent("   "),
                new Decision("BLANK_TEXT", "blank"));
        check("text", new TextEvent("Java"),
                new Decision("TEXT_LENGTH", "4"));
        check("negative", new PaymentEvent(-5),
                new Decision("NEGATIVE_PAYMENT", "-5"));
        check("zero", new PaymentEvent(0),
                new Decision("ZERO_PAYMENT", "0"));
        check("positive", new PaymentEvent(150),
                new Decision("POSITIVE_PAYMENT", "150"));
        check("ping", new PingEvent(),
                new Decision("PING", "pong"));

        System.out.println("ALL TESTS PASSED");
    }
}
```

Run with JDK 21+:

```bash
javac --release 21 TestableCaseDesignDemo.java
java TestableCaseDesignDemo
```

**Exact standard output:**

```text
null event => MISSING_EVENT:null
null text => MISSING_TEXT:null
blank text => BLANK_TEXT:blank
text => TEXT_LENGTH:4
negative => NEGATIVE_PAYMENT:-5
zero => ZERO_PAYMENT:0
positive => POSITIVE_PAYMENT:150
ping => PING:pong
ALL TESTS PASSED
```

The `check` method uses the record-generated `Decision.equals` to compare **the contents of both components**, rather than just checking printed output. If a branch returns the wrong `code` or `detail`, the program throws `AssertionError` and therefore **does not print** `ALL TESTS PASSED`. This is a self-test suite runnable with only the JDK; no external JUnit library is required.

### Why is this structure easy to test?

1. **Each case has a single intent:** missing event, missing text, blank text, valid text, negative payment, zero payment, positive payment, ping.
2. **Guards are deterministic:** they call record accessors and compare values without logging, sending HTTP requests, or mutating external variables.
3. **There is an unguarded branch** for each subtype: `TextEvent`, `PaymentEvent`, `PingEvent`; the compiler can prove the `switch` is exhaustive for sealed `Event`.
4. **No gratuitous `default`:** adding a new subtype and recompiling forces the developer to consider the corresponding behavior.
5. **`null` is distinguished at two levels:** null selector via `case null`; null text component via a dedicated guard.
6. **Explicit and immutable result:** `Decision` lets tests compare a single value without capturing console output or mocking dependencies.
7. **Tests verify both logic and ordering:** if the general `TextEvent` branch is placed before the guards, the program fails with a dominance error; if the two text guards are swapped, the null text case can throw an NPE.

## 8. Test Matrix: Branch and Boundary Coverage

The table below turns the cases into observable conditions. It helps quickly review what the test suite might still be missing.

| Input | Expected Branch | `Decision.code` | `Decision.detail` |
| --- | --- | --- | --- |
| `null` | `case null` | `MISSING_EVENT` | `null` |
| `new TextEvent(null)` | TextEvent with null text | `MISSING_TEXT` | `null` |
| `new TextEvent("   ")` | TextEvent with blank text | `BLANK_TEXT` | `blank` |
| `new TextEvent("Java")` | Remaining TextEvent | `TEXT_LENGTH` | `4` |
| `new PaymentEvent(-5)` | Negative payment | `NEGATIVE_PAYMENT` | `-5` |
| `new PaymentEvent(0)` | Zero payment | `ZERO_PAYMENT` | `0` |
| `new PaymentEvent(150)` | Positive payment | `POSITIVE_PAYMENT` | `150` |
| `new PingEvent()` | PingEvent | `PING` | `pong` |

Valuable additional cases:

- `new TextEvent("")`: confirms an empty string is also blank.
- `new TextEvent("\t")`: confirms tab characters are also recognized by `isBlank()`.
- `new TextEvent("A")`: length 1.
- `new PaymentEvent(-1)`, `new PaymentEvent(1)`: boundaries adjacent to 0.
- `new PaymentEvent(Integer.MIN_VALUE)` and `new PaymentEvent(Integer.MAX_VALUE)`: if numeric handling involves sensitive conversions or calculations.
- Separately test passing a new subtype when changing the hierarchy, to verify `switch` exhaustiveness at compile time.

**Branch coverage** is a starting point, not proof that all logic is correct. A guard like `n >= 0` may execute for many values, yet you still need to test `-1`, `0`, and `1` to catch comparison-operator bugs. Likewise, testing both blank and non-blank strings helps catch mistakes in `when` branch ordering.

## 9. Choosing Between `case ->` and `case :` for Testability

Java 21 still supports `switch` statements with colon labels:

```java
static String legacyStyle(Object input) {
    String result;
    switch (input) {
        case null:
            result = "MISSING";
            break;
        case String text:
            result = "TEXT:" + text;
            break;
        default:
            result = "OTHER";
            break;
    }
    return result;
}
```

This is a valid **illustrative method** when placed inside a Java 21 class. It can also be tested by expected return value. However, with many branches, managing `result`, `break`, fall-through, and pattern variable scope usually makes the code longer. For computing a single result, a `switch` expression and arrow rules usually express intent more clearly.

If you must use colon labels for compatibility with legacy code, apply the same criteria: each branch has a clear result/effect, `null` is handled transparently, there is no unintended fall-through, and tests cover the exit paths of every branch. There is no need to convert all code to expressions just to satisfy a particular style.

## 10. Organizing Production Code to Keep Tests Independent

A simple way to separate responsibilities:

```text
Input data
    |
    v
classify(input)     <-- unit test with input and expected Decision
    |
    v
Decision            <-- immutable data, no I/O
    |
    v
execute(decision)   <-- integrates with DB, HTTP, logger; separate integration test
```

Here `execute` represents an application-defined execution layer, not a built-in Java API. Separating layers keeps unit tests free of external resources, while integration tests focus on real actions.

Some principles:

- **Clear input:** prefer domain-specific interfaces/records rather than an `Object` carrying anything without a contract.
- **Semantic output:** return an enum, record, sealed result, or clear value instead of hard-to-test magic numbers.
- **Minimal overlapping branches:** place specific guards before general type branches; let ordering reflect business priority.
- **Immutability and pure functions:** do not mutate state in guards or classification branches; invoke side effects after the decision is made.
- **Do not swallow unexpected errors:** if unknown input should fail, design a branch that returns an error result or throws an intentional exception, and test that behavior.
- **Refactor when needed:** multiple guards sharing complex logic can extract a pure helper and test it separately, but avoid extracting every single `case` into its own method if it only scatters the code.

## 11. Mistakes That Make `case` Hard to Test

| Problematic Design | Why It Is Hard to Test | How to Improve |
| --- | --- | --- |
| Each case calls the database or sends HTTP requests | Tests depend on external resources and side-effect ordering | Return a decision; move I/O to another layer |
| Guard both checks and mutates data | Same input can yield different results depending on external state | Use pure helpers without side effects |
| General `case` placed before specific `case` | Specific branch is shadowed by dominance and may fail to compile | Place specific/guarded branches first |
| Multiple consecutive guards with no final type branch | Easy to miss a result when all guards evaluate to false | Include an unguarded type branch or valid fallback |
| `default` returns a success value for all errors | Easily hides invalid data or new subtypes | Define intentional error/fallback handling; leverage sealed types where appropriate |
| Not testing `null` | `switch` may throw NPE or null components may be missed | Test both null selector and null components |
| Testing only the "happy path" | Fails to verify boundary behaviors `< 0`, `== 0`, `> 0` | Use a case matrix + boundary values |
| Using `case String s && guard` | Not valid Java 21 syntax | Use `case String s when guard` |
| Checking console output only by eye | Hard to automate, easy to miss discrepancies | Compare `Decision` or return values with assertions |
| Overly long `switch` with multiple processing layers | Hard to see which branch decides which behavior | Classify first, process later; use descriptively named helpers |

## 12. Practice Exercises for Design and Testing

1. Change `TextEvent` to `record TextEvent(String text, boolean urgent)`. Add a dedicated branch for `urgent` when text is valid; write tests for both urgent and non-urgent. Ensure the `text == null` guard is checked before calling methods on `text`.
2. Add `record CancelEvent(String reason) implements Event {}` to the `permits` list, recompile, and observe the exhaustiveness requirement; add `case CancelEvent c` and test the new input.
3. Replace the string `Decision.code` result with an `enum`. Verify that tests can still compare outputs deterministically.
4. Write tests for `-1`, `0`, `1`, `Integer.MIN_VALUE`, `Integer.MAX_VALUE` to verify `PaymentEvent` classification. Explain why the three `when` branches must end with an unguarded `PaymentEvent` branch.
5. Refactor the classification function so part of the processing uses a `-> { ... yield ...; }` block without I/O; keep all expected results unchanged.
6. Write a `switch` statement version using colons, `break`, and a `result` variable; compare the number of control-flow points you must manage against the `switch` expression version.
7. Intentionally place `case TextEvent t` before the `when` branches and compile. Read the dominance error and fix it; explain why this is a compiler-caught error, unlike flawed classification logic that still compiles.
8. Create a version using `Object` and `default`; test an unknown subtype case. Compare with a sealed hierarchy without `default` in terms of the compiler reminding you to update branches.

**Completion criteria:** ability to design a Java 21 `switch` with clearly partitioned `case` branches, safe guards, an explicit `null` policy, appropriate exhaustiveness, observable tests for every branch, and classification logic separated from external side effects.

**Official sources:**

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — Switch Statements (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21 — Switch Expressions (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).