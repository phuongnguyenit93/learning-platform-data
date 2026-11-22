# Overusing `default` Breaks Exhaustive Checks in Java Pattern Matching

## Lesson Objectives

In the **Common Pitfalls** category, one notable design mistake is **adding `default` to every `switch` "just to be safe."** For a closed set of variants such as an `enum` or a `sealed interface`, this practice can stop the compiler from **forcing you to explicitly handle a new variant** as the codebase evolves. The program still compiles, but the new behavior is routed into a generic branch with little meaning, causing business logic to be missed.

This lesson helps you:
- Understand `switch` **exhaustiveness** and the value of compile-time checking.
- Compare a `switch` without `default` against a `switch` with `default` on an `enum` and a `sealed hierarchy`.
- Prove with `javac --release 21` that adding an `enum` value or a permitted subtype forces the version without `default` to be updated, while the version using `default` still passes compilation.
- Distinguish `default` from `case null`, `when` guards, and cases where a fallback is genuinely needed.
- Choose a strategy that preserves branch exhaustiveness while still handling open inputs, errors, and version compatibility.

**Version scope:** Examples use **Java 21**. Pattern Matching for `switch` and Record Patterns became standard in Java 21 (JEP 441 and JEP 440). In Java 17, pattern matching in `switch` was a preview feature; to run these examples, use JDK 21 or later.

## 1. What Is an Exhaustive `switch`?

A `switch` is considered **exhaustive** when its case labels sufficiently cover every input value that the language rules require to be handled. For a `switch expression`, this is an important compile-time condition: an expression must be able to produce a value (or throw an exception) on every applicable path.

Consider:

```java
enum Phase { QUEUED, RUNNING, DONE }

static String phaseName(Phase phase) {
    return switch (phase) {
        case QUEUED -> "QUEUE";
        case RUNNING -> "RUN";
        case DONE -> "FINISH";
    };
}
```

This is an **illustrative snippet** that can be placed inside a Java class. The three branches explicitly list all three constants of `Phase`, so the `switch expression` is exhaustive **without needing `default`**.

The strength of this style is not that it saves a line of code: it expresses a type-level commitment.

> If the set of `Phase` states changes, every place that classifies states must be reviewed.

If `PAUSED` is added later, when the codebase is recompiled, the `switch` above is no longer exhaustive and `javac` reports an error. This is a **policy update signal** right during the build, before the application runs.

Conversely:

```java
return switch (phase) {
    case QUEUED -> "QUEUE";
    case RUNNING -> "RUN";
    case DONE -> "FINISH";
    default -> "OTHER";
};
```

The `default` branch covers the remainder of the selector (except for special `null` handling discussed below). When `PAUSED` is added, the compiler does not force you to update the `switch`: the program keeps running and returns `OTHER`. That may be the right policy **if you truly want to group all future states together**; however, it is usually a bug when each state needs its own handling.

## 2. Why Does `default` Weaken the Compiler's Signal?

Suppose an application has jobs moving through phases:

| Phase | Expected Behavior |
|---|---|
| `QUEUED` | Display `QUEUE` |
| `RUNNING` | Display `RUN` |
| `DONE` | Display `FINISH` |
| `PAUSED` (added later) | **Requires a new decision**, e.g., whether to display `PAUSE` |

Initially, the two `switch` versions — listing all cases, and listing all cases plus `default` — produce the exact same results for the three existing values. That **does not mean they have the same ability to detect future changes**.

| When a Variant Is Added | Without `default` | With `default` |
|---|---|---|
| Add `enum Phase.PAUSED` | Compiler requires updating the branches in the `switch expression` | `PAUSED` silently falls into `default`; build still passes |
| Add a subtype to a `sealed interface` | `switch expression` is missing a case for the new subtype; compiler reports an error | The `default` branch may catch the new subtype without changing logic |
| Add an overly narrow `when` guard | Must ensure an unguarded branch or other branches cover the remainder | `default` hides a missing path for an existing variant |
| `null` input | Not automatically handled by type patterns | **`default` does not automatically handle `null` either** |

Therefore, the code review question is not "Is `default` valid?" but rather:

**"If the list of variants changes tomorrow, do I want the build to force me to review this logic, or do I want it handled automatically by a fallback?"**

In a closed domain model, the answer is usually **wanting the compiler to prompt an update**.

## 3. The `enum` Case: A Default Can Hide New States

Initially:

```java
enum Phase { QUEUED, RUNNING, DONE }

static String classify(Phase phase) {
    return switch (phase) {
        case QUEUED -> "QUEUE";
        case RUNNING -> "RUN";
        case DONE -> "FINISH";
    };
}
```

When `PAUSED` is added:

```java
enum Phase { QUEUED, RUNNING, DONE, PAUSED }
```

The old `classify` version **fails to compile** when rebuilt with `--release 21`, because the `switch expression` does not cover `PAUSED`. This is not an accidental inconvenience: it points out a place where business requirements need to be updated.

If it had been written as:

```java
static String classify(Phase phase) {
    return switch (phase) {
        case QUEUED -> "QUEUE";
        case RUNNING -> "RUN";
        case DONE -> "FINISH";
        default -> "UNKNOWN_PHASE";
    };
}
```

that version still compiles when `PAUSED` is added to `Phase`, but the result will be `UNKNOWN_PHASE`. Elsewhere in the application proper pause handling may have been added, while this screen silently turns it into an "unknown" state.

**Omitting `default` does not guarantee runtime safety when a class/jar changes without recompiling.** The primary advantage here is **compile-time exhaustiveness when compiling dependent code against the new type definition**. When using multiple binaries/jars of different versions, separate compatibility testing is still required.

## 4. The `sealed interface` Case: Let Closed Types Help the Compiler

A `sealed interface` restricts the list of direct subtypes permitted to implement it. For example:

```java
sealed interface Event permits Started, Stopped, Failed {}

record Started(String service) implements Event {}
record Stopped(String service) implements Event {}
record Failed(String service, int code) implements Event {}
```

Because the three records above are the permitted direct subtypes in this example, you can write:

```java
static String classify(Event event) {
    return switch (event) {
        case Started(var service) -> "STARTED:" + service;
        case Stopped(var service) -> "STOPPED:" + service;
        case Failed(var service, var code) -> "FAILED:" + code;
    };
}
```

**The snippet above has no `case null`:** with a `null` selector, a pattern switch throws `NullPointerException`, rather than branching to any subtype. If you want to handle null, add `case null` as in the standalone program in Section 6.

When a new permitted subtype is added:

```java
record Retried(String service) implements Event {}
```

and the sealed declaration is updated to `permits Started, Stopped, Failed, Retried`, the compiler requires the `switch expression` to list matching branches (unless an existing branch already covers it). This is one of the key advantages of combining `sealed` with pattern matching.

However, if the original code ended with:

```java
default -> "UNRECOGNIZED_EVENT";
```

`Retried` will be grouped into `default` at runtime. Important domain actions such as recording retry state, displaying details, or emitting dedicated metrics could be lost.

### Closed Means Exhaustiveness Can Be Checked, Not That Every Pattern Is Automatically Exhaustive

It is important to distinguish:

- `sealed` closes the list of permitted subtypes, allowing the compiler to reason about the variants.
- **Record pattern** deconstructs components; a record pattern with a `when` guard only matches values that satisfy the condition.
- **A guarded branch** does not replace a branch covering all values of that subtype. If you have `case Started s when ...`, you still need a path for `Started` values that fail the guard, unless another branch already covers them.
- `case Event event` is a **total type pattern for non-null `Event` values**, but it only makes sense when every subtype genuinely shares the exact same handling. It can also hide the need to distinguish a new subtype just like `default` does.

Using `sealed` is most valuable when the set of variants is part of the domain design and the handler **is responsible for knowing all of them**.

## 5. Three Kinds of "Completeness" Not to Confuse

### 5.1. Compile-Time Value Coverage

The compiler checks the set of `case` labels against the **static type of the selector**, pattern types, subtype relationships, and exhaustiveness. Accepting `default` only means there is a path covering the remainder; it does not prove that every variant is handled properly in terms of business logic.

### 5.2. Satisfying All Business Behavior

A `default -> "OTHER"` can make a `switch` exhaustive according to language rules, yet **incomplete from a business perspective**. When the domain gains a new variant, the code does not force the author to decide on its specific handling. This is the **core pitfall of overusing `default`**.

### 5.3. Handling `null`

With pattern matching `switch` in Java 21, **a regular `default` does not catch a `null` selector**. If the selector can be null and you want to handle it, use an explicit `case null` or check before invoking `switch`.

For example:

```java
return switch (phase) {
    case null -> "PHASE_NULL";
    case QUEUED -> "QUEUE";
    case RUNNING -> "RUN";
    case DONE -> "FINISH";
};
```

This set of cases clearly expresses both the policy for the three `Phase` states and the policy when the selector is null. Conversely, `default -> "OTHER"` at the end of a `switch` without `case null` **does not** prevent a `NullPointerException` when the input is null.

## 6. Java 21 Program: Two Ways to Write for the Same Current State

Create the file **`ExhaustivenessDemo.java`**:

```java
import java.util.Objects;

public class ExhaustivenessDemo {
    sealed interface Event permits Started, Stopped, Failed {}
    record Started(String service) implements Event {}
    record Stopped(String service) implements Event {}
    record Failed(String service, int code) implements Event {}
    enum Phase { QUEUED, RUNNING, DONE }

    // Without default: the compiler tracks all permitted subtypes.
    static String eventNoDefault(Event e) {
        return switch (e) {
            case null -> "EVENT_NULL";
            case Started(var service) -> "STARTED:" + service;
            case Stopped(var service) -> "STOPPED:" + service;
            case Failed(var service, var code) -> "FAILED:" + code;
        };
    }

    // With default: if the sealed hierarchy grows, this branch may hide missed cases.
    static String eventWithDefault(Event e) {
        return switch (e) {
            case null -> "EVENT_NULL";
            case Started(var service) -> "STARTED:" + service;
            case Stopped(var service) -> "STOPPED:" + service;
            case Failed(var service, var code) -> "FAILED:" + code;
            default -> "UNRECOGNIZED_EVENT";
        };
    }

    static String phaseNoDefault(Phase phase) {
        return switch (phase) {
            case null -> "PHASE_NULL";
            case QUEUED -> "QUEUE";
            case RUNNING -> "RUN";
            case DONE -> "FINISH";
        };
    }

    static String phaseWithDefault(Phase phase) {
        return switch (phase) {
            case null -> "PHASE_NULL";
            case QUEUED -> "QUEUE";
            case RUNNING -> "RUN";
            case DONE -> "FINISH";
            default -> "UNKNOWN_PHASE";
        };
    }

    static String defaultDoesNotCatchNull(Phase phase) {
        return switch (phase) {
            case QUEUED -> "QUEUE";
            default -> "OTHER";
        };
    }

    static void eventCheck(String title, Event event, String expected) {
        String strict = eventNoDefault(event);
        String broad = eventWithDefault(event);
        if (!Objects.equals(strict, expected) || !Objects.equals(broad, expected)) {
            throw new AssertionError("Mismatch " + title);
        }
        System.out.println(title + " -> " + strict);
    }

    static void phaseCheck(String title, Phase phase, String expected) {
        String strict = phaseNoDefault(phase);
        String broad = phaseWithDefault(phase);
        if (!Objects.equals(strict, expected) || !Objects.equals(broad, expected)) {
            throw new AssertionError("Mismatch " + title);
        }
        System.out.println(title + " -> " + strict);
    }

    public static void main(String[] args) {
        eventCheck("started", new Started("billing"), "STARTED:billing");
        eventCheck("stopped", new Stopped("billing"), "STOPPED:billing");
        eventCheck("failed", new Failed("billing", 503), "FAILED:503");
        eventCheck("null component", new Started(null), "STARTED:null");
        eventCheck("null event", null, "EVENT_NULL");

        phaseCheck("queued", Phase.QUEUED, "QUEUE");
        phaseCheck("running", Phase.RUNNING, "RUN");
        phaseCheck("done", Phase.DONE, "FINISH");
        phaseCheck("null phase", null, "PHASE_NULL");

        try {
            defaultDoesNotCatchNull(null);
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println("default without case null -> NullPointerException");
        }
    }
}
```

Compile and run:

```bash
javac --release 21 ExhaustivenessDemo.java
java ExhaustivenessDemo
```

**Verified exact stdout:**

```text
started -> STARTED:billing
stopped -> STOPPED:billing
failed -> FAILED:503
null component -> STARTED:null
null event -> EVENT_NULL
queued -> QUEUE
running -> RUN
done -> FINISH
null phase -> PHASE_NULL
default without case null -> NullPointerException
```

In this program:

1. Both versions — with `default` and without `default` — return the same result for **all existing variants**; `eventCheck` and `phaseCheck` compare both against the independent `expected` value.
2. `Started(null)` still matches the pattern `Started(var service)`: the `Started` record exists, while its reference-typed `service` component can be null. The `STARTED:null` result comes from string concatenation, not an exception.
3. `case null` handles a null selector when declared.
4. `defaultDoesNotCatchNull` intentionally omits `case null`, and at runtime it throws `NullPointerException` even though `default` is present. The `try/catch` confirms this instead of failing the entire demo.

**Limitation of this test:** Two implementations producing the same output today does not prove they will be updated properly when the set of variants changes. To observe the difference, you need to test the **evolve type + recompile** cycle, as shown in the next sections.

## 7. Compiler Experiment: Adding an Enum Value

Create a separate file **`EnumNoDefaultAfterChange.java`**, intentionally declaring `PAUSED` without a corresponding branch:

```java
public class EnumNoDefaultAfterChange {
    enum Phase { QUEUED, RUNNING, DONE, PAUSED }

    static String classify(Phase phase) {
        return switch (phase) {
            case QUEUED -> "QUEUE";
            case RUNNING -> "RUN";
            case DONE -> "FINISH";
        };
    }
}
```

Compile:

```bash
javac --release 21 EnumNoDefaultAfterChange.java
```

**Expected result:** the compiler **rejects** the code because the `switch expression` does not cover all `Phase` values after `PAUSED` was added. Do not rely on the exact wording of the error message, as phrasing can vary across `javac` versions.

The following version with `default` compiles:

```java
public class EnumWithDefaultAfterChange {
    enum Phase { QUEUED, RUNNING, DONE, PAUSED }

    static String classify(Phase phase) {
        return switch (phase) {
            case QUEUED -> "QUEUE";
            case RUNNING -> "RUN";
            case DONE -> "FINISH";
            default -> "UNKNOWN_PHASE";
        };
    }

    public static void main(String[] args) {
        System.out.println("new enum value -> " + classify(Phase.PAUSED));
    }
}
```

Run:

```bash
javac --release 21 EnumWithDefaultAfterChange.java
java EnumWithDefaultAfterChange
```

**Stdout:**

```text
new enum value -> UNKNOWN_PHASE
```

Key takeaway: **`PAUSED` is a new valid state**, yet the program accidentally lumps it into an "unknown" state. The compiler cannot ask you whether `PAUSED` needs its own label, action, or permissions, because `default` suppressed the missing-case signal.

**Proper fix when the new requirement arrives:** add `case PAUSED -> "PAUSE";` to the `switch` without `default`; update expected test assertions; recompile. That is domain implementation work, not "fixing the compiler so it runs."

## 8. Compiler Experiment: Adding a Permitted Subtype to a Sealed Type

Create the file **`SealedNoDefaultAfterChange.java`**:

```java
public class SealedNoDefaultAfterChange {
    sealed interface Event permits Started, Stopped, Failed {}
    record Started() implements Event {}
    record Stopped() implements Event {}
    record Failed() implements Event {}

    static String classify(Event value) {
        return switch (value) {
            case Started s -> "STARTED";
            case Stopped s -> "STOPPED";
        };
    }
}
```

Here there are three permitted subtypes, but the `switch expression` only handles two. Compile:

```bash
javac --release 21 SealedNoDefaultAfterChange.java
```

**Result:** `javac` rejects it because the `switch expression` does not cover the remaining `Failed` case.

Version with `default`:

```java
public class SealedWithDefaultAfterChange {
    sealed interface Event permits Started, Stopped, Failed {}
    record Started() implements Event {}
    record Stopped() implements Event {}
    record Failed() implements Event {}

    static String classify(Event value) {
        return switch (value) {
            case Started s -> "STARTED";
            case Stopped s -> "STOPPED";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("new subtype -> " + classify(new Failed()));
    }
}
```

Run:

```bash
javac --release 21 SealedWithDefaultAfterChange.java
java SealedWithDefaultAfterChange
```

**Stdout:**

```text
new subtype -> OTHER
```

This is the same issue as with `enum`, only with a closed class/interface hierarchy as the domain type. When evolving a sealed model, a `switch` without `default` is a tool that helps maintainers locate every place that needs to be updated for the new variant.

If you genuinely have a policy that "all remaining subtypes are handled the same way," express **the reason explicitly** in code review or a domain method rather than adding `default` just to bypass the compiler.

## 9. `default` Is Not the Enemy: When Should It Be Used?

A default branch is appropriate if **the set of input values is open by design** or you have a clearly defined fallback policy:

### 9.1. Selector Is `Object` with Many Out-of-Domain Types

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case String s -> "text:" + s.length();
        case Number n -> "number:" + n;
        default -> "unsupported type";
    };
}
```

This is an **illustrative method**, not part of the program in Section 6. Here `Object` has an unbounded number of subtypes; the goal is not to exhaustively handle every subtype. `default` has valid semantics: return a generic label for all other types.

### 9.2. Business Logic Intentionally Groups All Remaining States

Suppose the rule only needs to distinguish `DONE` from **all** unfinished states; then:

```java
boolean finished = switch (phase) {
    case DONE -> true;
    default -> false;
};
```

may be the right choice **if the requirement genuinely defines any new state as implicitly "not finished."** Usually, though, it is simpler and clearer to write:

```java
boolean finished = phase == Phase.DONE;
```

The latter boolean expression also naturally evaluates `null` to `false` via reference comparison, whereas the `switch` above (without `case null`) can throw `NullPointerException` when `phase == null`. So **do not call them equivalent if the input is nullable**.

### 9.3. Fallback Is Part of the Contract, Not "Hiding Errors"

In systems processing external inputs, the catalog of incoming values may be broader than the types or labels supported by the application. A named fallback such as `UNSUPPORTED` or a purposefully designed exception is reasonable.

However, for domains that are **closed and owned by the application**, consider letting the compiler do the work for you. If you want unknown-type behavior, also consider logging, metrics, and testing so important situations are not silently ignored.

### 9.4. Throwing Inside `default` Still Hides the Compile-Time Obligation

```java
default -> throw new IllegalStateException("Unexpected variant");
```

looks "safer" because it does not silently return `OTHER`, yet it **still makes the switch exhaustive at compile time**. When a new subtype or constant is added, the compiler will not force you to add an explicit case; the error only surfaces when that runtime path is executed. For a sealed hierarchy or enum you own, omitting `default` usually catches missing branches earlier.

## 10. A `when` Guard Does Not Guarantee Exhaustiveness on Its Own

Consider a `sealed interface` with only `Success` and `Failure` subtypes:

```java
sealed interface Result permits Success, Failure {}
record Success(int code) implements Result {}
record Failure(String reason) implements Result {}
```

If you only have:

```java
case Success(var code) when code >= 200 -> "GOOD";
case Failure f -> "FAILED";
```

then `Success` with `code < 200` has no handling branch. Do not use `default -> "OTHER"` just to silence the error if that case still needs its own decision.

A more meaningful expression is:

```java
return switch (result) {
    case Success(var code) when code >= 200 -> "GOOD";
    case Success s -> "SUCCESS_OTHER";
    case Failure f -> "FAILED";
};
```

These are **illustrative snippets** used in a method taking `Result result` with no null-handling requirement. Order matters: the guarded `Success` branch comes before the general one. If reversed, the guarded branch is *dominated* and can cause a compile-time error.

Do not treat a `when` guard as a promise that every `Success` value satisfies it. The compiler must account for values failing the guard, except in cases explicitly specified by the language.

## 11. Are `switch expression` and `switch statement` the Same?

**Not entirely.** The main examples above are all **`switch expression`s**: `return switch (...) { ... };`. A `switch expression` must be exhaustive.

With a traditional `switch statement` using only `enum` constants, Java has historically allowed omitting cases without a `default`:

```java
switch (phase) {
    case DONE:
        System.out.println("Completed");
        break;
}
```

Because this is just a statement, when `phase` is a constant other than `DONE`, the program may execute no branch at all. This **does not provide the same exhaustive checking guarantee as a switch expression**.

In Java 21, there is also the concept of an **enhanced switch statement**, which covers cases using patterns or selector types outside the legacy switch group. Enhanced switch statements have corresponding exhaustiveness requirements. Therefore, do not make the blanket statement that "every switch without default forces the compiler to check all enum values."

**Practical recommendation:** if a domain decision must return a value for each variant, using a **switch expression** with explicit cases is the most direct way to get exhaustiveness checking. If you are refactoring a legacy switch statement, verify the exact switch form before relying on the compiler.

## 12. Limitations to Understand When Relying on Exhaustive Checks

### 12.1. Compile Time Does Not Replace Runtime Testing

Classes can be compiled separately, and a library can change while a dependent binary has not been rebuilt. A `switch` that was exhaustive when compiled against one set of variants does not automatically prove runtime safety across all version combinations. When updating dependencies or modules, recompile and run regression tests.

### 12.2. Sealed Types with Generics and Complex Hierarchies

The compiler evaluates the **selector type, permitted subtypes, and generic constraints**, rather than simply counting classes by hand. Certain parameterizations of a sealed generic hierarchy mean only a subset of permitted subtypes are actually possible. Rely on `javac` and the JLS rules instead of applying mechanical branch-counting rules.

### 12.3. Null Is a Separate Concern

A `switch` can be exhaustive for all non-null values of an enum or sealed type and still throw `NullPointerException` if the selector is null without a `case null`. Do not "add `default`" and assume null is handled.

### 12.4. Branch Names and Ordering Remain the Author's Responsibility

The compiler can prove all cases are covered, but it cannot prove that `case FAILED -> "OK"` is business-correct. Exhaustiveness is a safety net, not a replacement for tests and code review.

## 13. Code Review Checklist: Should `default` Be Allowed?

| Question | If the Answer Is "Yes" |
|---|---|
| Is the selector an `enum` owned by the team? | Consider listing all constants and omitting `default` in the `switch expression` |
| Is the selector a `sealed interface/class`? | Explicitly list the subtypes that need to be distinguished |
| Does adding a new variant require a business decision? | **Do not hide that event behind a generic `default`** |
| Is there a contractual fallback that applies to all future values? | `default` may be reasonable, but explain and test it |
| Can the selector be null? | Decide whether you need `case null`, a non-null precondition, or an exception |
| Does a branch have a `when` guard? | Ensure values **failing the guard** are also properly covered |
| Is the code a traditional statement or a switch expression? | Check the exact exhaustiveness rules for that switch form |
| Are there multiple jars/modules with different versions? | Recompile and run integration/regression tests |
| Does `default` just `throw`? | Remember the compiler still won't force new cases; consider removing it |
| Is the data an open set of types (such as `Object`)? | `default` is usually justified and meaningful |

### Safe Refactoring Workflow

1. Identify whether the selector's **variant set is closed or open**.
2. Determine the business contract: must new variants be handled individually or grouped together?
3. If closed and requiring individual handling, **remove `default` from the `switch expression`** and list all cases explicitly.
4. Add `case null` if null must be handled by a dedicated branch.
5. Use `javac --release 21` to confirm the compiler accepts the current set of cases.
6. Write regression tests for each enum constant/sealed subtype and for guards/boundaries.
7. Try adding a new variant on a test branch to confirm the compiler forces updates at handling sites — this is a very effective design verification check.
8. Keep `default` only if it represents a **named, testable policy**, not to "silence a compiler error."

## 14. Self-Check Questions

**1. Why is `default` risky in a `switch` over an enum with three values?**

Because when a fourth value is added, the program can still compile and route the new value into the generic branch, even when the business logic needs to evaluate it separately.

**2. Does removing `default` always cause the compiler to reject any `switch statement` with missing cases?**

No. You must distinguish a traditional switch statement from a switch expression or enhanced switch statement; this lesson relies primarily on the exhaustiveness of a **switch expression**.

**3. In a sealed hierarchy, does `default -> throw ...` preserve the compiler's ability to force updates when a new subtype is added?**

No. It may throw a runtime error when encountering the new subtype, but it still acts as a catch-all branch at compile time.

**4. If you have `case Started s when s.service() != null`, does the compiler consider that as covering all `Started` instances?**

No. `Started` instances with a null service still remain and need an appropriate branch to be exhaustive.

**5. Does `default -> "OTHER"` catch a null selector?**

Not in the Java 21 pattern switches demonstrated in this lesson. To handle null as part of the contract, use `case null` or check beforehand.

**6. When is `default` useful?**

When the input is an open set of types, or when the requirements explicitly state that **all** remaining and future variants go through the same fallback policy.

**7. Does "the compiler accepts it" mean "the logic is correct"?**

No. The compiler enforces type rules and language-level exhaustiveness; it does not verify the meaning of returned labels or the side effects of each case.

## Conclusion

For `enum` and `sealed` domains that you control, **do not add `default` out of habit**. A `switch expression` that explicitly lists variants allows the compiler to warn you when the domain expands, turning type changes into a prompt to review code. `default` has its place when a fallback is genuinely part of the contract, especially with open inputs; but using it to fill gaps forfeits one of the biggest benefits of pattern matching: **compile-time exhaustiveness checking**.

Always separate **exhaustiveness of non-null variants**, **`null` handling**, and **business logic correctness** — those are three distinct questions.

## References

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JLS Java SE 21 — Switch Statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS Java SE 21 — Switch Expressions §15.28](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [JLS Java SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
