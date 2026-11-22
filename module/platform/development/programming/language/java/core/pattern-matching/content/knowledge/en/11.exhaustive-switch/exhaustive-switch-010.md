# Designing Impossible Branches in Java Exhaustive Switch

**Topic:** Java Core Pattern Matching → *Exhaustive switch*. This document uses **Java SE 21** (pattern matching for `switch` finalized in JEP 441), with examples that compile on JDK 21 or later without preview features. The goal is to properly design **“impossible”** branches: when *not to write a fallback branch*, when to **intentionally throw an exception**, and when a branch is unmatched at runtime yet still poses a real risk due to code changes or library versions.

## 1. “Impossible” Has Three Different Meanings

When writing a `switch`, the statement “this case cannot happen” usually refers to **three different levels of guarantee**:

1. **Impossible according to language rules at compile time.** A label *dominated* by a preceding label or a completely unreachable statement causes a compilation error. There is no such thing as “just leave that branch there, the compiler will ignore it.”
2. **Impossible according to the current static type model.** For example, an `enum` with only three constants, or a `sealed interface` that only permits two subtypes. A `switch` that covers everything **does not need `default`**. This is often the right choice when you want the compiler to remind you to update the code if the model evolves.
3. **Impossible according to business assumptions or in the current code version.** For example, “order ID is never empty” or “elements from this adapter are always String.” The compiler **cannot prove** arbitrary business invariants. For data coming from outside, there should be explicit exception handling. Furthermore, software running with classes from different compilation versions can break the exhaustiveness that the compiler once accepted.

**General principle:** rely on the compiler to eliminate states that are *statically impossible*; use explicit checks and exceptions for states that are *representable by types but violate the contract*; do not use `default` merely to hide errors.

## 2. What Does Exhaustiveness Actually Guarantee?

JLS §14.11.1.1 defines a `switch` block as **exhaustive** when it covers the type of the selector according to specific static rules. This can be achieved with:

- A `default` label.
- A combined `case null, default` label.
- An appropriate set of constant/pattern labels—for example, listing **every enum constant**, type patterns covering the permitted subtypes of a `sealed` type, or an *unconditional* type pattern for the selector type.

A **`switch` expression** must be exhaustive. Starting in Java 21, an **enhanced `switch` statement** (such as a statement containing patterns or `case null`) must also be exhaustive. However, a traditional `switch` statement using only `int`, `String`, or `enum` constants can still be non-exhaustive for backward compatibility.

**Exhaustive does not mean it will never throw an exception.** Nor does it assert that all business data is valid. It is a guarantee **of the type system and label set at compile time**.

### Enum: Coverage Over a Finite Set of Names

```java
enum Phase { NEW, APPROVED, DECLINED }

static String phaseLabel(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
    };
}
```

The snippet above is valid: the `switch` expression covers the entire existing `Phase` enum. There is no need to add:

```java
// Unnecessary when all three enum constants are already handled:
// default -> "unknown";
```

If the enum is modified to `{ NEW, APPROVED, DECLINED, CANCELLED }` and **`phaseLabel` is recompiled against it**, the compiler detects that the `switch` expression is no longer exhaustive and requires handling `CANCELLED`.

**Benefit of omitting `default` in a closed model:** a new state forces the author to decide how to handle it instead of silently falling into a generic branch.

### Sealed: Using Subtypes to Represent Valid States

```java
sealed interface Payment permits Cash, Card {}

record Cash(int amount) implements Payment {}

record Card(String token) implements Payment {}

static String describe(Payment payment) {
    return switch (payment) {
        case Cash c -> "cash:" + c.amount();
        case Card c -> "card:" + c.token();
    };
}
```

`Payment` permits only two direct subtypes, `Cash` and `Card`, in this example. The two type patterns cover all currently valid implementations; the `switch` expression is exhaustive without `default`. If the model is later extended with `BankTransfer` and the related code is recompiled against the new hierarchy, the compiler will require revisiting `describe`.

**Caution:** do not infer that “sealed” means every class is `final` in every model. A permitted class can be `final`, `sealed`, or `non-sealed` according to JLS rules; how coverage works depends on the actual hierarchy structure. The example above uses two records (implicitly `final`), so the set of states is very clear.

## 3. Do Not Use `default` to Hide New Cases That Need Handling

A pattern that easily passes the compiler but risks hiding changes:

```java
static String phaseWithCatchAll(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case APPROVED -> "approved";
        default -> "other";
    };
}
```

This code compiles when the `Phase` enum has three values; `DECLINED` returns `other`. If `CANCELLED` is added later, it **also** returns `other` without the compiler requiring a logic update.

That is completely reasonable **if the business requirement intentionally groups the remaining states as `other`**. However, it is poor design when every state must have its own handling (such as payments, business state transitions, or access control decisions).

Comparison:

| Design Goal | Appropriate Approach | Reason |
| --- | --- | --- |
| Closed set of states, every state must have dedicated handling | List all cases completely, **do not use default** | Adding a new enum constant/subtype → re-checked on recompile |
| Unlisted states genuinely share the same meaning | `default -> fallback` | This is part of the contract, not a temporary escape hatch |
| Input of type `Object` from an external system can be anything | `default -> throw new IllegalArgumentException(...)` or explicit rejection result | No closed type model for the compiler to cover |
| Internal invariant exists, but an error state is still representable | Validate and `throw` in the appropriate branch | Avoid silently returning a “seemingly valid” value |
| Want to signal a true programming bug that must never occur | `throw new AssertionError(...)` at the point with evidence | Marks an invariant violation; not for routine business branches |

Note that **you cannot always add `default` everywhere**. In a `switch` with an unguarded pattern that is *unconditional* for the selector, a trailing `default` can be *dominated* and cause a compilation error.

## 4. Truly Abnormal Branches Should Fail Fast Instead of Swallowing Errors

Suppose an adapter receives an `Object` from an external plug-in and the application only accepts non-blank strings or integers.

```java
static String fromBoundary(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text when !text.isBlank() -> "text:" + text;
        case String text ->
                throw new IllegalArgumentException("blank-string");
        case Integer number -> "integer:" + number;
        default -> throw new IllegalArgumentException("unsupported");
    };
}
```

This design has clear semantics:

- `null` is a valid input in the example contract, with its own result.
- Non-blank strings are matched via a pattern with `when`.
- Blank strings are still `String` at the type level, but **fail the business condition**, so an explanatory exception is thrown.
- `Integer` is accepted.
- Other types (`Double`, `Boolean`, arbitrary objects) are out-of-contract data; `default` is **necessary** to cover the `Object` selector, and throws an exception instead of returning a misleading result.

Here, `default` is **not** a statically “impossible branch”: there are infinitely many objects that are neither String nor Integer. It is simply an **unexpected** case under the API contract—and therefore must be handled intentionally.

### Choosing the Right Exception

- **`IllegalArgumentException`**: the caller passed an invalid argument according to the method's contract, such as an unsupported data type or format.
- **`IllegalStateException`**: the object or system is in an invalid state for the current operation, even though its Java type is valid.
- **`AssertionError`**: asserts that a state is impossible according to an internal invariant. This is an `Error` for a serious programming/invariant bug; it should not be used to respond to ordinary invalid user input.
- **`MatchException`**: Java may throw this automatically when a `switch` was exhaustive at compile time but no label applies at runtime. Normally you should **not** throw this exception manually in place of a business error message.

There is no mandatory rule that every “unexpected value” must throw the same exception; choose based on the nature of the error and the API contract.

## 5. `default -> throw new AssertionError(...)`: When Is It Useful and When Does It Backfire?

In legacy code or APIs with insufficiently tight type bounds, a defensive branch is sometimes used:

```java
static String defensive(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
        default -> throw new AssertionError("Unexpected phase: " + phase);
    };
}
```

This snippet is valid, and with the current three enum states the `default` branch is never chosen for non-null values. However, there is an **important trade-off**:

- If the `CANCELLED` enum constant is added, the `default` branch **is already present**, so recompiling **does not force** updating the method.
- The new value will fall into `default` and throw `AssertionError` at runtime. That means an error that could have been caught **early at compile time** now only surfaces **at runtime**.
- Therefore, for an enum/sealed hierarchy controlled by the application, if the goal is to force reviewing every new subtype, **prefer omitting `default`** and let the compiler detect the change.

A throwing `default` branch can still be useful at **open boundaries** or when the contract requires rejecting unsupported values, though consider using `IllegalArgumentException`/`IllegalStateException` rather than `AssertionError` for external data.

**Do not use `assert false` as mandatory handling for an abnormal branch:**

```java
// Do not use as a mandatory fail-fast mechanism:
// default -> {
//     assert false : "unreachable";
//     yield "fallback";
// }
```

Java assertions can be **disabled by default** unless `-ea` is enabled. When disabled, the code above returns `fallback` and silently ignores the error. If you have decided a situation must fail with an error, use an explicit `throw`.

## 6. Null Is a Separate Path: Exhaustive Does Not Mean Null-Safe

A `switch` expression over an `enum` or `sealed interface` can be exhaustive **and still throw `NullPointerException`** when the selector is `null`:

```java
static String state(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
    };
}
```

`state(null)` throws `NullPointerException` because there is no `case null` label. A standalone `default` also does not automatically catch a null selector in Java 21.

If null is a **contract violation**, you can state it explicitly at the start of the method:

```java
static String requireState(Phase phase) {
    java.util.Objects.requireNonNull(phase, "phase");
    return switch (phase) {
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
    };
}
```

Or place the error directly inside the `switch`:

```java
static String requireState2(Phase phase) {
    return switch (phase) {
        case null -> throw new IllegalArgumentException("phase-required");
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
    };
}
```

The two approaches express **two different decisions about the exception type**. Use `Objects.requireNonNull` normally for `NullPointerException`; use `case null -> throw ...` if you deliberately choose a different exception type or need to handle null within the switch structure. If null is a valid state, you can use `case null -> "unknown"`.

### Why Doesn't `case Object x` Catch Null Either?

```java
static String category(Object value) {
    return switch (value) {
        case Object x -> "non-null object";
    };
}
```

The type pattern `Object x` is unconditional for non-null `Object` values, so this expression is statically exhaustive. Yet `category(null)` still throws NPE. To handle null, you must add `case null`. Exhaustiveness and null policy are two separate questions.

## 7. A Dominated Branch Is Not a “Backup” Branch

A `case` label is considered **dominated** if the compiler determines that every value it could match has already been covered by a preceding label. Java 21 reports an error instead of silently leaving that code waiting to run.

```java
// DOES NOT COMPILE:
static String dominated(Object input) {
    return switch (input) {
        case Object any -> "object";
        case String text -> "string"; // Dominated by Object any.
    };
}
```

`Object any` already matches every non-null reference of type `Object`. The subsequent `String` label can never be selected. The correct order if you want to distinguish strings:

```java
static String ordered(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "string:" + text;
        case Object any -> "object";
    };
}
```

The `Object any` label is now at the end, serving to cover the remaining non-null values and make the `switch` expression exhaustive.

### Guards Are Not Unconditional Branches

```java
static String classifyNumber(Object input) {
    return switch (input) {
        case Integer n when n < 0 -> "negative";
        case Integer n -> "other integer";
        case null -> "null";
        default -> "other";
    };
}
```

Placing the guarded branch first is valid because the guard `n < 0` can be false. Reversing the order and putting the unguarded `case Integer n` first would cause the guarded branch after it to be dominated.

**Do not assume the compiler proves arbitrary business expressions.** The two guards `n < 0` and `n >= 0` mathematically partition all integers, but the compiler does not use such arbitrary proofs to treat a pattern set as exhaustive. Add an appropriate unguarded branch when exhaustiveness is needed. The guard `when true` is a special case that the JLS treats as unguarded; a constant `when false` guard is invalid.

### Reachability Differs from Dominance

These two error snippets have different natures:

```java
// DOES NOT COMPILE: unreachable statement.
static void afterReturn() {
    return;
    // System.out.println("never"); // If uncommented: unreachable statement.
}
```

```java
// DOES NOT COMPILE: dominated switch label.
static String wrongOrder(Object input) {
    return switch (input) {
        case Object any -> "any";
        case String s -> "string";
    };
}
```

Statement **reachability** is governed by JLS §14.22; switch label **dominance** is governed by JLS §14.11.1. Both can cause compilation errors, but they are not the same rule and are not solved by adding `default` or inserting a new “impossible” branch.

## 8. Runtime: “Impossible” States Can Still Appear Due to Separate Compilation

This is why exhaustiveness must not be treated as an absolute invariant across all deployment versions.

Suppose an application is compiled when the model only has:

```java
sealed interface Payment permits Cash, Card {}
record Cash(int amount) implements Payment {}
record Card(String token) implements Payment {}
```

A function branching over the two subtypes `Cash`/`Card` does not need `default`. Later, the library is updated so `Payment` also permits `Transfer`, but the module containing the `switch` **is not recompiled**. When `Transfer` is passed into the old code at runtime, no label matches the non-null object.

In Java 21, a `switch` expression (or enhanced `switch` statement) considered exhaustive at compile time that finds no matching label at runtime may throw **`java.lang.MatchException`**. This can also happen when an enum gains a new constant or a type hierarchy changes across separately compiled modules.

**Distinguishing the four failure cases:**

| Situation | Typical Behavior in Java 21 |
| --- | --- |
| Null selector, no `case null` | `NullPointerException` |
| Non-null selector, but exhaustive switch no longer has a matching label because runtime hierarchy differs from compile time | `MatchException` |
| `default -> throw new IllegalArgumentException(...)` label is selected | Exception intentionally thrown by the application itself |
| Dominated branch or non-exhaustive switch expression at compile time | Compilation error, does not run |

The right way to handle `MatchException` caused by model changes is to **synchronize versions, recompile dependent code, and update the handling branches**. Do not turn it into a “no-op” error or always return a fallback to mask a contract change.

This is also why compatibility tests between modules or releases are needed when a sealed hierarchy/enum changes.

## 9. Switch Expression vs. Switch Statement: Do Not Confuse Exhaustiveness Requirements

### Switch Expression: Must Not Miss Required Cases

```java
// DOES NOT COMPILE: Object selector has many values other than String.
static String incomplete(Object value) {
    return switch (value) {
        case String text -> text;
    };
}
```

The compiler requires covering the remainder. When the selector is an open `Object`, you can add `default -> throw ...` if the application does not support other types.

### Enhanced Switch Statement: Must Also Be Exhaustive

```java
// DOES NOT COMPILE in Java 21:
static void incompleteStatement(Object value) {
    switch (value) {
        case String text -> System.out.println(text);
    }
}
```

This is an enhanced `switch` statement containing a pattern; sufficient labels must be added to cover all cases, for example:

```java
static void completeStatement(Object value) {
    switch (value) {
        case null -> throw new IllegalArgumentException("missing");
        case String text -> System.out.println(text);
        default -> throw new IllegalArgumentException("unsupported");
    }
}
```

### Legacy Switch Statement: Can Be Non-Exhaustive

```java
static void legacyEnumStatement(Phase phase) {
    switch (phase) {
        case NEW -> System.out.println("created");
        // APPROVED and DECLINED have no branch.
    }
}
```

This is a statement with an enum selector and traditional case constants—**not an enhanced statement**. Java still allows it to be non-exhaustive for backward compatibility. For `APPROVED` or `DECLINED`, no label applies and the statement completes normally without printing anything. When designing critical business flows, if full handling must be enforced, use a `switch` expression or a data/computation model where missing branches are caught by the compiler.

**Do not confuse `switch` statement and `switch` expression.** An expression must produce a value (or throw an exception) and is always subject to exhaustiveness checking; a statement can execute actions without producing a value.

## 10. Complete Java 21 Program

Create the file **`ImpossibleBranchDemo.java`** with the following complete content:

```java
public class ImpossibleBranchDemo {
    // The current set of valid subtypes is closed.
    sealed interface Payment permits Cash, Card {}

    record Cash(int amount) implements Payment {}
    record Card(String token) implements Payment {}

    enum Phase { NEW, APPROVED, DECLINED }

    // Cover the enum by name, no default needed.
    static String phaseLabel(Phase phase) {
        return switch (phase) {
            case null -> throw new IllegalArgumentException("phase-required");
            case NEW -> "new";
            case APPROVED -> "approved";
            case DECLINED -> "declined";
        };
    }

    // Cover the sealed hierarchy by type pattern, no default needed.
    static String describe(Payment payment) {
        return switch (payment) {
            case null -> throw new IllegalArgumentException("payment-required");
            case Cash c -> "cash:" + c.amount();
            case Card c -> "card:" + c.token();
        };
    }

    // Open data boundary: use default to reject out-of-contract types.
    static String fromBoundary(Object value) {
        return switch (value) {
            case null -> "missing";
            case String text when !text.isBlank() -> "text:" + text;
            case String text -> throw new IllegalArgumentException("blank-string");
            case Integer number -> "integer:" + number;
            default -> throw new IllegalArgumentException("unsupported");
        };
    }

    // Defensive example: default is valid, but has a trade-off.
    static String defensive(Phase phase) {
        return switch (phase) {
            case null -> "null";
            case NEW -> "new";
            case APPROVED -> "approved";
            case DECLINED -> "declined";
            default -> throw new AssertionError("Unexpected phase " + phase);
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Cash(120)));
        System.out.println(describe(new Card("T9")));
        System.out.println(phaseLabel(Phase.NEW));
        System.out.println(fromBoundary(null));
        System.out.println(fromBoundary("Java"));
        System.out.println(fromBoundary(7));

        try {
            fromBoundary(" ");
        } catch (IllegalArgumentException e) {
            System.out.println("bad:" + e.getMessage());
        }

        try {
            fromBoundary(3.14);
        } catch (IllegalArgumentException e) {
            System.out.println("bad:" + e.getMessage());
        }

        try {
            describe(null);
        } catch (IllegalArgumentException e) {
            System.out.println("bad:" + e.getMessage());
        }

        System.out.println(defensive(Phase.DECLINED));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 ImpossibleBranchDemo.java
java ImpossibleBranchDemo
```

**Expected output:**

```text
cash:120
card:T9
new
missing
text:Java
integer:7
bad:blank-string
bad:unsupported
bad:payment-required
declined
```

**Explanation:**

1. `Cash` and `Card` are distinguished by type patterns on the sealed hierarchy. There is no `default` to mask adding a new subtype.
2. `Phase.NEW` has an enum label and returns `new`.
3. `fromBoundary(null)` enters the dedicated null label; `"Java"` matches the non-blank guard; `7` matches the Integer type pattern.
4. `" "` is a String, but blank, so it enters the unguarded String label and throws `IllegalArgumentException("blank-string")`; it is not treated as “cannot be a String.”
5. `3.14` is a Double and does not match the supported patterns, so `default` throws `IllegalArgumentException("unsupported")`.
6. `describe(null)` actively throws a missing-payment contract error; unlike the implicit NPE when a null label is omitted.
7. `defensive(Phase.DECLINED)` still returns `declined`. The `default -> throw AssertionError` branch does not run today with three enum constants, but if the enum changes in the future, it can prevent the compiler from reminding you to update the branches.

This program does not demonstrate `MatchException` by fabricating a broken hierarchy. Because `MatchException` involves **separately compiled code at mismatched versions**, a real multi-version compilation test must be set up to reproduce it accurately; you should not fake the exception with `throw new MatchException(...)` and present that as natural `switch` behavior.

## 11. Designing Tests for Abnormal Branches

A good test suite must verify both valid paths and contract violations:

- **Every valid enum state:** each `Phase` returns the expected label.
- **Every valid sealed subtype:** `Cash` and `Card` are recognized, and pattern variables hold the right data.
- **Null:** test `phaseLabel(null)` and `describe(null)` directly; verify the expected exception type and message.
- **Open data boundaries:** test a non-blank String, a blank String, an Integer, an unsupported type (e.g., Double), and null.
- **Error rules:** abnormal data must produce an explicit error, not be converted into a valid business value.
- **Model changes:** in CI, recompile modules containing `switch` when adding an enum constant or sealed subtype; prefer catching compile-time errors over relying solely on runtime tests.
- **Multi-version libraries:** if the system loads separately compiled modules, run cross-version integration tests to detect `MatchException` or incompatible contract changes.

Do not write tests just to “hit an impossible branch” via reflection/abnormal bytecode if that is not a real risk for the application. Tests should prove the **contract** and **change-management process** rather than fabricating artificial states.

### Checking with the Compiler Is a Design Test

If you add `CANCELLED` to the `Phase` enum and recompile `phaseLabel` **without a default**, the compiler requiring an update is a good sign. If the method uses `default`, the compiler may stay silent and you will only see the error or fallback at runtime.

Similarly, if you change `Payment` to `permits Cash, Card, Transfer` and recompile `describe` without a default, the compiler points out where handling for the `Transfer` subtype must be added.

## 12. Common Mistakes

**Mistake 1 — always adding `default` “just to be safe.”** With a closed enum/sealed model requiring dedicated handling per case, `default` can hide newly added states and defeat useful exhaustiveness checks.

**Mistake 2 — using `default -> null`, `default -> false`, or `default -> ""` “so it doesn't crash.”** This turns abnormal data into seemingly valid results, makes errors hard to trace, and can cause incorrect business behavior. Only use a fallback when the contract genuinely allows it.

**Mistake 3 — using `assert false` for mandatory error reporting.** Java assertions can be disabled; use an explicit `throw` for cases that must fail.

**Mistake 4 — assuming exhaustiveness also handles null.** `null` does not match type patterns on outer selectors. Without `case null`, an exhaustive `switch` can still throw NPE.

**Mistake 5 — confusing guards with exhaustiveness.** `when` branches only match when the guard is true. Do not rely on “mutually complementary” dynamic conditions for the compiler to infer exhaustiveness; use an appropriate unguarded label.

**Mistake 6 — keeping a dominated label as a “backup branch.”** Java 21 reports a compilation error for dominated switch labels. Order specific branches first and general ones after.

**Mistake 7 — conflating source errors with runtime errors.** A non-exhaustive branch can be blocked by the compiler; a `MatchException` caused by a class hierarchy changing between compile time and runtime occurs while the program is running.

**Mistake 8 — using `AssertionError` for all invalid inputs.** Input from callers or external systems should be described by the contract and corresponding exceptions; `Error` is for serious programming invariant violations, not the default choice for validation.

**Mistake 9 — failing to recompile dependent modules when an enum/sealed hierarchy changes.** Types considered exhaustive in old code do not automatically update branches in already-compiled bytecode. Binary compatibility and integration tests must be managed.

**Mistake 10 — equating switch expressions with legacy switch statements.** Enhanced statements and expressions require exhaustiveness in Java 21, whereas traditional statements with enum constants can still complete normally when no label matches.

## 13. Exercises and Solutions

### Exercise A — Should There Be a Default?

Given:

```java
enum Direction { NORTH, SOUTH }

static int sign(Direction direction) {
    return switch (direction) {
        case NORTH -> 1;
        case SOUTH -> -1;
    };
}
```

If `EAST` is added, what happens on recompile? What if `default -> 0` was added before changing the enum?

**Answer:** On recompile without a default, the expression is no longer exhaustive and the compiler requires handling `EAST`. If a default is already present, the compiler does not force adding a branch, and `EAST` returns `0`. Which approach is better depends on whether `0` is genuinely the right result for the new direction; if not, avoid `default`.

### Exercise B — Detecting Broken Invariants

An adapter receives `Object x` but only accepts a non-blank `String`. Choose the appropriate implementation.

```java
static String requireText(Object x) {
    return switch (x) {
        case String s when !s.isBlank() -> s;
        case String s -> throw new IllegalArgumentException("blank");
        case null -> throw new IllegalArgumentException("missing");
        default -> throw new IllegalArgumentException("not-string");
    };
}
```

**Answer:** The method is exhaustive for `Object` thanks to `default`, without swallowing errors. Null, blank strings, and wrong types are clearly categorized. `when` does not replace the unguarded String branch because blank strings still exist.

### Exercise C — Which Error Belongs to the Compiler?

```java
// DOES NOT COMPILE:
static String wrong(Object x) {
    return switch (x) {
        case Object any -> "object";
        case String text -> "text";
    };
}
```

**Answer:** `case String text` is dominated by the preceding `Object any` label. This is a **compile-time error**, not a “never runs at runtime” case. Swap the order of the two patterns to fix it.

### Exercise D — Null in an Exhaustive Switch

```java
static String name(Phase p) {
    return switch (p) {
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
    };
}
```

**Answer:** `name(null)` throws NPE. Exhaustiveness of enum constants does not include a null-handling policy. Use `case null` or `Objects.requireNonNull` if you want to state the expected behavior explicitly.

### Exercise E — MatchException

A class containing an exhaustive `switch` over a `sealed interface` is compiled in version A. In version B, the hierarchy permits an additional subtype, but the module containing the `switch` is not recompiled. What happens when the old code receives an instance of the new subtype?

**Answer:** If no label applies to the non-null selector, the `switch` may throw `MatchException` in Java 21, even though the compiler accepted it as exhaustive in version A. Synchronize/recompile and handle the new subtype; do not treat this error as invalid data to be ignored.

### Exercise F — Choosing an Exception Type

Classify three situations: (1) the client sends an input type not accepted by the API; (2) an order is already `CANCELLED` but the system tries to ship it; (3) internal logic guarantees a `default` branch cannot be selected, yet it is selected.

**Suggested Answer:** (1) `IllegalArgumentException`; (2) `IllegalStateException`; (3) `AssertionError` if it is truly a serious programming invariant violation. These are design choices, not mandatory Java syntax requirements.

## 14. Practical Checklist

Before adding an “impossible” branch, ask yourself:

1. **Is the state set closed or open?** An enum/sealed type you control, or an `Object` receiving external data?
2. **Can all valid states be listed without `default`?** If so, recompiling helps detect type changes.
3. **What error would the compiler report?** Dominated/unreachable label? Non-exhaustive switch expression? These are design errors to fix in source code, not “backup branches.”
4. **Is null allowed?** Define a `case null` policy, validate before the switch, or allow NPE by contract.
5. **Can guards be false?** Arrange an unguarded pattern or fallback to be genuinely exhaustive.
6. **Is the abnormal case a contract violation or an internal bug?** Choose `IllegalArgumentException`, `IllegalStateException`, or `AssertionError` with clear reasoning.
7. **Should it fail fast?** If a value is disallowed, it is usually better to throw an explicit error than return a value that looks valid.
8. **Can runtime changes happen independently of compile time?** If so, check module compatibility and `MatchException` risk.
9. **Are both valid paths and error paths tested?** Test enum values, sealed subtypes, null, out-of-contract types, false guards, and cross-version integration.
10. **If a new state arrives tomorrow, who is forced to update the logic?** This is the deciding question for whether to write `default`.

**In summary:** for closed data, leverage **exhaustive switch without `default`** so the compiler protects your design. For open data boundaries, use a fallback branch but **handle abnormalities explicitly, usually with exceptions**. Do not treat `default` as “free insurance,” and do not assume exhaustiveness proves that every runtime and business state is infallible.

## Official Documentation

- [JLS Java SE 21 §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): coverage rules for types, enums, and sealed hierarchies.
- [JLS Java SE 21 §14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): dominance, case labels, and guards.
- [JLS Java SE 21 §14.11.3 — Execution of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3): null, enhanced statements, and runtime errors when no label applies.
- [JLS Java SE 21 §15.28.2 — Run-Time Evaluation of switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28.2): `NullPointerException` and `MatchException`.
- [JLS Java SE 21 §14.22 — Unreachable Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.22): distinguishing reachability from label dominance.
- [Java SE 21 API — java.lang.MatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html): why an exhaustive match can fail at runtime.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): finalized feature in Java 21.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): closed subtype set model.
