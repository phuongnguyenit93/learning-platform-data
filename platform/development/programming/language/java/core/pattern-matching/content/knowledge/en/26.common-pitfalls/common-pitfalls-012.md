# Not Testing “Impossible” Branches in Java Pattern Matching

## 1. Why Is This a Dangerous Mistake?

In code using `instanceof`, record patterns, and pattern matching for `switch`, an error-handling branch is often annotated as **“this case can never happen”**. Developers may skip testing it because they assume the system already guarantees the data has the right type, the nested record always exists, or every subtype of a `sealed interface` is listed.

The problem is that **“impossible” has several different meanings**:

1. **The compiler proves a branch is shadowed or an expression is semantically invalid:** for example, `case String s` already matches every `String`, so `case String s when s.isEmpty()` afterward is *dominated*. Java reports a compile-time error; there is no runnable code to test that branch.
2. **A valid branch that is assumed to never receive data in the current system:** for example, `default` on an `Object` selector, a branch handling a `null` nested record, or a `when` guard failing. These branches **can execute** if assumptions about input data are wrong.
3. **A case excluded by type constraints or invariants:** for example, a `sealed interface` with finite subtypes, or a constructor validating data. This is a stronger guarantee than convention, yet you still need to test the **boundaries of the contract** and understand the impact of code changes, external data, or runtime versions.
4. **An abnormal branch using `throw`:** it is not the happy path, but it is still observable API behavior. Failing to test exceptions easily leads to invalid data being silently accepted, changing exception types, or returning the wrong message.

This lesson focuses on **the mistake of not testing branches assumed to be impossible** in Java Core Pattern Matching, how to distinguish the different kinds of “unreachable”, how to build a test matrix, and how to deliberately verify error branches.

**Java version:** Pattern matching for `instanceof` has been a standard feature since Java 16 (JEP 394). Record patterns and pattern matching for `switch` were standardized in **Java 21** (JEP 440, JEP 441). The runnable example in this article uses **JDK 21+**, with no preview flags required.

## 2. Distinguishing Compiler-Unreachable Branches from Runtime-Unseen Branches

### 2.1. Dominated Branch: Rejected by the Compiler

The following example **does not compile** on Java 21:

```java
// Intentionally wrong example: the guarded String case is covered by the preceding String branch.
static String dominated(Object value) {
    return switch (value) {
        case String s -> "any string";
        case String s when s.isEmpty() -> "empty";
        default -> "other";
    };
}
```

An unguarded `case String s` matches every non-null `String` object, so the subsequent `case String s when s.isEmpty()` branch can never be selected. The compiler reports an error equivalent to **“this case label is dominated by a preceding case label”**.

How to fix it:

```java
static String classifyString(Object value) {
    return switch (value) {
        case String s when s.isEmpty() -> "empty";
        case String s -> "any string";
        case null -> "null";
        default -> "other";
    };
}
```

The more specific branch comes first, and the broader branch comes after; both branches can be executed. For this kind of mistake, the first step is to **fix the code so it compiles**. You cannot write a runtime test to “enter a dominated branch” of a program that does not compile.

Similarly, a `switch expression` over a `sealed interface` without enough branches may be rejected by the compiler as **non-exhaustive**. This case is also a static checking issue and should not be confused with “a branch that compiles fine but tests never hit”.

### 2.2. Valid Fallback Branches Can Still Happen

Suppose an external input is received as type `Object`:

```java
static String display(Object value) {
    return switch (value) {
        case String s -> "text";
        case Integer n -> "number";
        case null -> "missing";
        default -> "unexpected";
    };
}
```

Even if the application currently only sends `String` and `Integer`, `default` can still **execute**, for example when a caller passes `new Object()`, `Boolean.TRUE`, or a new DTO type. Skipping tests for `default` because “the integration partner never sends another type” is an assumption about **runtime data**, not a compiler proof.

If `default` returns a default string, the test needs to verify that string. If `default` throws an exception to signal a contract violation, the test needs to verify **the exact exception type and message**, avoiding turning a data error into hard-to-trace behavior.

### 2.3. A `when` Branch Does Not Cover an Entire Type

```java
record Created(String id, int count) {}

// This is an illustrative snippet inside a method receiving Object value.
return switch (value) {
    case Created(var id, var count) when count > 0 -> "created:" + id;
    case Created(var id, var count) -> "invalid count";
    case null -> "no event";
    default -> "other";
};
```

A `Created` with `count == 0` or a negative value **does not enter the `when count > 0` branch**. It enters the unguarded `Created` branch. If you only test `new Created("A", 2)` and believe `count` is “always positive”, you have not verified the case where the guard fails.

**Lesson:** you must test both **true and false** guard outcomes, especially around boundary values. For the condition `count > 0`, inputs `0` and `-1` are usually much more valuable for testing than repeating multiple similar positive cases.

## 3. Nested Record Patterns: What Seems Impossible Happens Easily in Practice

Consider:

```java
record Envelope(Object payload) {}
record Message(String text) {}
```

A developer might believe that every `Envelope` contains a `Message` and that `text` is never null. However, the signature `Envelope(Object payload)` does not forbid any of these:

```java
new Envelope(new Message("hello"));
new Envelope(new Message(null));
new Envelope(null);
new Envelope(42);
```

Without dedicated validation in the constructor or at the data ingestion boundary, **all of these are valid record constructions at the language level**.

Consider the expression:

```java
static String extract(Object input) {
    return switch (input) {
        case Envelope(Message(var text)) when text != null && !text.isBlank()
                -> "text:" + text.trim();
        case Envelope(Message(var text)) -> "empty-text";
        case Envelope(var payload) -> "unexpected-payload";
        case null -> "null-envelope";
        default -> "unsupported";
    };
}
```

Each branch has a distinct meaning:

| Input | Branch Actually Selected | Result |
| --- | --- | --- |
| `new Envelope(new Message(" hello "))` | Nested record pattern + `when` is true | `text:hello` |
| `new Envelope(new Message(null))` | Second `Envelope(Message(...))` branch | `empty-text` |
| `new Envelope(new Message("   "))` | Second nested record branch due to `isBlank()` | `empty-text` |
| `new Envelope(null)` | `Envelope(var payload)` | `unexpected-payload` |
| `new Envelope(42)` | `Envelope(var payload)` | `unexpected-payload` |
| `null` | `case null` | `null-envelope` |
| `"not-envelope"` | `default` | `unsupported` |

The easiest point to get wrong: **a null nested record causes the nested record pattern not to match, whereas the `var text` component of an existing `Message` record can still bind to null**.

Therefore, `Envelope(Message(var text))` does not imply `text != null`. The guard `text != null && !text.isBlank()` must be kept, and the `Message(null)` case must have its own test if the input can come from external data.

With the guard `text != null && !text.isBlank()`, the `&&` operator short-circuits so `isBlank()` is not called on null. If you change it to `text == null || text.isBlank()` to express the error condition, the logic can still be safe; however, changing the order or using the wrong operator can cause a `NullPointerException`. Testing null helps catch such accidental changes.

## 4. `sealed interface` and Exhaustiveness Do Not Replace Behavioral Testing

Suppose:

```java
sealed interface Event permits Created, Deleted {}
record Created(String id, int count) implements Event {}
record Deleted(String id) implements Event {}
```

A `switch expression` can cover all currently permitted subtypes:

```java
static String handle(Event event) {
    return switch (event) {
        case null -> "no-event";
        case Created(var id, var count) when count > 0 -> "created:" + id;
        case Created(var id, var count) -> "bad-count:" + id;
        case Deleted(var id) -> "deleted:" + id;
    };
}
```

There is no `default` because the compiler knows `Event` only has the direct implementations permitted in this type hierarchy, and the branches cover `Created`/`Deleted`. The unguarded `Created` branch after `when` ensures every `Created` value is handled.

The advantage of **not writing an unconditional `default`** on a covered sealed hierarchy is that if you later modify the definition to permit a new subtype and recompile dependent code, the compiler can require updating the `switch`. A `default -> "unknown"` branch can hide that reminder.

However, exhaustive checking **does not prove the logic of each branch is correct**. It does not guarantee `count > 0`, does not guarantee `id != null`, and does not verify the quality of the returned string. Therefore, you must still test:

- `Created` with `count > 0`.
- `Created` with `count == 0` or negative, to test the branch where `when` is false.
- `Deleted`.
- `null` if the API allows it, because selector null handling is a separate concern.
- Data constraints such as `id == null` if they affect business logic.

If a sealed hierarchy changes **out of sync between compile time and runtime** (for example, binaries from modules of different versions), the old exhaustiveness assumption may no longer hold at runtime and can lead to `java.lang.MatchException` under pattern switch semantics. This is a special deployment/binary compatibility scenario: prioritize testing version compatibility when the system actually deploys modules separately, rather than trying to simulate a Java subtype that the compiler does not allow you to declare.

**Section takeaway:** the compiler checks **structural coverage**, while tests verify **business outcomes, error paths, and data boundaries**. The two layers of protection complement rather than replace each other.

## 5. Branches That “Should Throw”: Actually Verify the Exception

Some systems want to fail fast instead of returning a default value for malformed structures. For example:

```java
static String mustBeMessage(Object input) {
    if (!(input instanceof Message(var text))) {
        throw new IllegalArgumentException("expected Message");
    }
    if (text == null) {
        throw new IllegalArgumentException("missing text");
    }
    return text;
}
```

Do not only test `mustBeMessage(new Message("ok"))`. You need separate tests for:

1. `mustBeMessage(null)` throws `IllegalArgumentException` with message `expected Message`.
2. `mustBeMessage(42)` throws the same exception type and message, because of the wrong type.
3. `mustBeMessage(new Message(null))` throws `IllegalArgumentException` with message `missing text`.
4. `mustBeMessage(new Message(""))` **is not rejected by the current contract**, because the code only blocks null. If you want to forbid empty strings, you must add another condition and test.

If tests only cover the happy path, a bad refactor might change the exception to `NullPointerException`, change the message, return null, or drop the rejection altogether. All of these can be breaking changes for callers.

With JUnit 5, the idea is to use `assertThrows(IllegalArgumentException.class, () -> ...)` and then check the message if the message is part of the contract to preserve. So that this lesson can run standalone **without external test libraries**, the complete example below uses an `expectReject` helper with `Runnable` and `AssertionError`.

## 6. Runnable Java 21 Example: Testing 15 Scenarios, Including “Impossible” Branches

Create the file **`ImpossibleBranchTestDemo.java`**:

```java
public class ImpossibleBranchTestDemo {
    sealed interface Event permits Created, Deleted {}
    record Created(String id, int count) implements Event {}
    record Deleted(String id) implements Event {}
    record Envelope(Object payload) {}
    record Message(String text) {}

    static String handle(Event event) {
        return switch (event) {
            case null -> "no-event";
            case Created(var id, var count) when count > 0 -> "created:" + id;
            case Created(var id, var count) -> "bad-count:" + id;
            case Deleted(var id) -> "deleted:" + id;
        };
    }

    static String extract(Object input) {
        return switch (input) {
            case Envelope(Message(var text)) when text != null && !text.isBlank()
                    -> "text:" + text.trim();
            case Envelope(Message(var text)) -> "empty-text";
            case Envelope(var payload) -> "unexpected-payload";
            case null -> "null-envelope";
            default -> "unsupported";
        };
    }

    static String mustBeMessage(Object input) {
        if (!(input instanceof Message(var text))) {
            throw new IllegalArgumentException("expected Message");
        }
        if (text == null) throw new IllegalArgumentException("missing text");
        return text;
    }

    static int checked;

    static void expect(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + " expected " + expected + " but got " + actual);
        }
        checked++;
        System.out.println("PASS " + label + " => " + actual);
    }

    static void expectReject(String label, Runnable action, String message) {
        try {
            action.run();
            throw new AssertionError(label + " should reject input");
        } catch (IllegalArgumentException ex) {
            if (!message.equals(ex.getMessage())) {
                throw new AssertionError(label + " wrong error: " + ex.getMessage());
            }
            checked++;
            System.out.println("PASS " + label + " => rejected: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        expect("created", "created:A", handle(new Created("A", 2)));
        expect("bad-created", "bad-count:B", handle(new Created("B", 0)));
        expect("deleted", "deleted:C", handle(new Deleted("C")));
        expect("null-event", "no-event", handle(null));
        expect("nested-valid", "text:hello", extract(new Envelope(new Message(" hello "))));
        expect("null-text", "empty-text", extract(new Envelope(new Message(null))));
        expect("blank-text", "empty-text", extract(new Envelope(new Message("   "))));
        expect("null-payload", "unexpected-payload", extract(new Envelope(null)));
        expect("wrong-payload", "unexpected-payload", extract(new Envelope(42)));
        expect("null-input", "null-envelope", extract(null));
        expect("wrong-outer", "unsupported", extract("not-envelope"));
        expect("strict-success", "ok", mustBeMessage(new Message("ok")));
        expectReject("strict-null", () -> mustBeMessage(null), "expected Message");
        expectReject("strict-wrong", () -> mustBeMessage(42), "expected Message");
        expectReject("strict-missing", () -> mustBeMessage(new Message(null)), "missing text");
        System.out.println("checks=" + checked);
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 ImpossibleBranchTestDemo.java
java ImpossibleBranchTestDemo
```

**Expected output:**

```text
PASS created => created:A
PASS bad-created => bad-count:B
PASS deleted => deleted:C
PASS null-event => no-event
PASS nested-valid => text:hello
PASS null-text => empty-text
PASS blank-text => empty-text
PASS null-payload => unexpected-payload
PASS wrong-payload => unexpected-payload
PASS null-input => null-envelope
PASS wrong-outer => unsupported
PASS strict-success => ok
PASS strict-null => rejected: expected Message
PASS strict-wrong => rejected: expected Message
PASS strict-missing => rejected: missing text
checks=15
```

In this example:

- `handle` verifies valid `Created`, `Created` with count 0, `Deleted`, and null. `case Created ... when count > 0` is not treated as the only case worth testing.
- `extract` demonstrates that `Envelope(var payload)` and `default` **can execute** even when many applications assume the payload is always a `Message`.
- `mustBeMessage` tests three rejection paths: null input, wrong type, and null text component.
- The `expect` helper compares the result against the expectation and throws `AssertionError` immediately on mismatch. The `expectReject` helper ensures the operation actually throws **IllegalArgumentException** with the expected message; if the operation finishes normally, the test also fails.

The line `checks=15` proves that **15 checks in the program** passed. It is **not proof that every execution path and data value has been covered**. A real test suite needs additional boundary values, malformed data, external interactions, and new cases according to the application contract.

## 7. Designing a Test Matrix Instead of Testing Only the Happy Path

When reading a pattern `switch`, list the **selected branches** and the conditions that prevent each branch from being selected. Then use concrete values to trigger each group:

| Path Type | Suggested Input | What to Assert |
| --- | --- | --- |
| Type/record pattern matches | Valid object | The success branch produces the right value. |
| `when` is true | Value above threshold | The guarded branch is selected. |
| `when` is false, same record | Value at or below threshold | The fallback branch for the same type is selected. |
| Null selector | `null` | `case null` or exception per contract. |
| Null nested child record | `Envelope(null)` | Nested pattern does not match; the appropriate outer branch handles it. |
| Null child component | `new Message(null)` inside a valid record | `var text` can bind null; the guard does not dereference null. |
| Incompatible type | `Envelope(42)` or raw `String` | The fallback branch handles it properly. |
| Boundary data | `count == 0`, `count == -1`, blank string | Business rules hold at the boundary. |
| `throw` branch | Wrong type, missing required data | Verify exception type, message, and that no success result is returned. |
| Hierarchy change | Add a valid subtype when recompiling | Build/tests force updating handling branches if the switch has no `default` and previously relied on exhaustive matching. |

**Do not mechanically create tests for branches the compiler has already determined cannot exist.** If the compiler reports a dominated case or non-exhaustive switch, fix the source code first. The test matrix is for **valid execution paths that the compiled program can encounter**, including paths rarely seen in production.

## 8. Benefits and Limits of Branch Coverage

**Branch coverage** helps detect whether any `case`/`if` branch has not been executed in the test suite. However, a high coverage percentage does not prove all constraints have been checked:

- The same `case Created(...)` can produce the wrong value when `count == 0` even if that branch was already executed with `count == 5`.
- A `when` guard with multiple operands like `text != null && !text.isBlank()` has at least these key scenarios: null text, blank text, valid text. Measuring branch coverage alone may not be enough to catch bugs in individual sub-conditions.
- Cases involving external schema changes, incompatible versions, side effects, or exceptions may require integration tests, contract tests, or regression tests.
- A path considered unreachable may exist because an invariant is enforced elsewhere. In that case, test **where the invariant is established** and the rejection of invalid data, rather than trying to bypass the guard just to increase coverage.

A good workflow combines **a test case table by data partition**, **boundary values**, exception assertions, and coverage measurement. If a test enters a fallback branch, verify that the behavior inside that branch matches the contract rather than merely recording that it was executed.

Avoid “fixing” coverage by adding `default -> null` to every `switch`: that can mask an unexpected data state and let callers continue with an invalid result. Fallbacks should return an explicit error or `throw` when the business requirement is fail fast.

## 9. Strengthening Invariants So Branches Truly Become Harder to Hit

If the application requires `text` to always be non-blank, express that constraint right at data construction time:

```java
record NonBlankMessage(String text) {
    NonBlankMessage {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("text must not be blank");
        }
    }
}
```

The record's compact constructor checks the condition before a valid instance can be created through that constructor. As a result, normal data flowing through `NonBlankMessage` has a stronger invariant than an unvalidated `record Message(String text)`. Still, you need to test:

- `new NonBlankMessage("hello")` succeeds.
- `new NonBlankMessage(null)` is rejected.
- `new NonBlankMessage(" ")` is rejected.
- An external data ingestion path applies the validation before converting into the trusted object.

Some guarantees are provided by the **type system** (such as a sealed hierarchy), some by **constructor validation**, and some assumptions exist only in **comments or the developer's head**. The level of testing depends on the layer of protection: do not treat a “never null” comment as equivalent to executable validation code.

If a branch truly exists only to report an invariant violation with no valid path into it, use a clear message like `throw new IllegalStateException("Unexpected state")` or enforce it in the type system instead of silently returning a dummy value. Have tests at the data ingestion or state construction point to verify the invariant, along with logging/monitoring appropriate for the system.

## 10. Common Misconceptions and Mistakes

| Mistake | Why It Is Problematic | How to Check / Fix |
| --- | --- | --- |
| “`default` will never run” because the backend currently sends only two types | An `Object` selector still allows many other runtime types. | Test a type outside the expected set; use a clear fallback or error. |
| “Every `Created` has a positive count” | `record Created(String id, int count)` itself does not block 0 or negatives. | Test `0` and `-1`, and add validation if needed. |
| “If a nested record pattern matches, all components are non-null” | The child record must be non-null to deconstruct, but the `var text` component can still be null. | Test a null child record and a null component separately. |
| Only testing `when` true | A false guard can select another branch, including an error branch. | Use values on both sides of the boundary and right on the boundary. |
| Not testing `case null` | A null selector is handled differently from a null record component. | Test null as an independent input. |
| Adding `default` so a sealed switch always compiles | Easy to miss new subtypes in future compilations. | When you want the compiler to enforce subtype updates, list exhaustive cases without `default`. |
| Trying to invoke a dominated branch to raise coverage | The Java compiler rejects shadowed branches. | Fix the case order; do not try to write runtime tests for code that does not compile. |
| Treating `throw` as “unimportant because it is an error” | Exception type and message affect the caller contract. | Test with `assertThrows` or an exception-checking helper. |
| Running only the happy path and concluding a refactor is equivalent | Cannot tell if wrong-type, null, or boundary behavior changed. | Run regression tests for both success and failure cases. |
| Believing 100% coverage means correctness for all inputs | Coverage measures execution, not every value and expectation. | Combine data partitions, boundary, negative, and contract tests. |
| Calling every fallback “impossible” and returning null | Hides errors and causes a later NPE. | Document the reason, fail fast, or return a typed error. |
| Not revisiting assumptions when adding subtypes or changing schemas | Previously rare paths can become normal. | Update the test matrix when changing data contracts and the type system. |

## 11. Self-Check Exercise: Find the Forgotten Branches

Given two records:

```java
record Coordinates(int x, int y) {}
record Wrapper(Object payload) {}
```

Processing code:

```java
static String inspect(Object value) {
    return switch (value) {
        case Wrapper(Coordinates(var x, var y)) when x >= 0 && y >= 0
                -> "valid:" + x + "," + y;
        case Wrapper(Coordinates(var x, var y)) -> "negative";
        case Wrapper(var payload) -> "unknown payload";
        case null -> "null input";
        default -> "other";
    };
}
```

A team wrote only a single test case:

```java
// The test is missing many execution paths.
inspect(new Wrapper(new Coordinates(2, 3))); // "valid:2,3"
```

**Question:** Which “impossible” branches still need to be tested? Choose inputs that change the result.

Suggested answers:

1. `new Wrapper(new Coordinates(-1, 3))` → `negative`.
2. `new Wrapper(new Coordinates(2, -1))` → `negative`.
3. `new Wrapper(new Coordinates(0, 0))` → `valid:0,0`, testing the `>= 0` boundary.
4. `new Wrapper(null)` → `unknown payload`, because nested `Coordinates(...)` does not match null.
5. `new Wrapper("text")` → `unknown payload` due to wrong component type.
6. `null` → `null input`.
7. `new Object()` → `other`.

The exercise snippets are illustrative fragments using the two declared records. The complete file with `main`, run commands, and 15 checks in section 6 can be used as a template to write similar tests.

If there is an additional invariant “x, y are always non-negative” from a data validation layer, write tests for **that validation layer**; do not simply omit the `negative` branch from tests based on an unencoded claim. If `Wrapper.payload` is changed from `Object` to a specific type, update the matrix based on the new type instead of mechanically copying tests that no longer make sense.

## 12. Code Review Checklist to Prevent Mistakes

Before accepting a pattern-matching snippet with a branch called “unreachable”, answer these questions:

1. Is the branch **uncompilable because it is dominated**, or **still reachable with runtime data that differs from expectations**?
2. Can the selector be null? Is **`case null`** handled according to the contract?
3. Are there nullable child `record`s? Can `var` components be null?
4. Is `when` tested for **both true/false outcomes** and boundary values?
5. Is there a valid `default`/fallback branch, and has an input triggering it been tested?
6. For `sealed`, does the switch cover all subtypes, and was a `default` accidentally added that would mask missing cases when a subtype is added?
7. Do `throw` paths test **the exact exception type** and required message?
8. Is the “impossible” invariant guaranteed by the type system, constructor/validation, or only by assumption?
9. When data sources or deployment versions change, which tests detect contract breaks?
10. Are **branch coverage + boundary values + negative tests** combined, rather than relying solely on coverage percentages?

**Remember:** It is neither possible nor necessary to force a runtime test into a branch the compiler has already eliminated. However, every branch that **can compile and can receive type-valid data**, even if called “never happens”, must be evaluated against the business contract. Testing null branches, mismatched types, `when` false, nested records missing data, and exceptions is how you catch wrong assumptions before they become production bugs.

**References:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Java SE 21 JLS — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30), [Java SE 21 JLS — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
