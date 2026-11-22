# MatchException and Root Causes in Java Pattern Matching

## 1. What is MatchException?

Since **Java 21**, `java.lang.MatchException` is a `RuntimeException` used to indicate an **abnormal failure during pattern matching**. This is not a normal "this pattern did not match" signal. A non-matching pattern can evaluate to `false` in `instanceof` or cause a `switch` to try another label; `MatchException` occurs in situations where the matching process **cannot complete normally as the program expected**.

Two categories of causes are particularly important:

1. **Failure when extracting record components:** a record pattern invokes an accessor to retrieve a component, and the accessor throws an exception. Java throws `MatchException` and sets the original exception as `getCause()`.
2. **A `switch` considered exhaustive by the compiler has no matching branch at runtime:** this can happen when a hierarchy or enum changes between compilations, or when `null` appears in a **nested component**, causing the record patterns not to match even though the pattern set was considered exhaustive. In the "no matching label" case, `getCause()` is typically `null` because there is no accessor exception to wrap.

API declaration in Java 21:

```java
public final class MatchException extends RuntimeException {
    // Public constructor:
    public MatchException(String message, Throwable cause);
}
```

This is a **condensed signature description**, not the full JDK source code. `MatchException` is in `java.lang`, so no `import` is needed; the class was introduced in Java 21. It is an **unchecked exception**, so the compiler does not require declaring `throws` or catching it with `catch`.

**Key takeaway of this lesson:** when you see `MatchException`, you must find the **root cause**. Do not assume every `MatchException` is caused by a missing `default`, and do not assume `getCause()` is always non-`null`.

## 2. Inspection Sequence to Distinguish Causes

Conceptual decision tree:

```text
A matching operation or switch fails
  |
  +-- Is there a MatchException?
  |     |
  |     +-- Is there a getCause()?
  |     |     |
  |     |     +-- Yes: inspect exception type, message, stack trace,
  |     |     |        and which record accessor threw the error
  |     |     |
  |     |     +-- No: check runtime switch exhaustiveness:
  |     |             nested record/null, nested sealed/null,
  |     |             enum or sealed hierarchy different from compile time
  |     |
  |     +-- Cross-check running source code and dependency versions
  |
  +-- No: classify the actual exception:
        NullPointerException, IllegalArgumentException from a guard,
        exception from a branch body, cast error, other errors...
```

This diagram helps **narrow down** the issue; it is not an absolute inference rule based solely on `getCause()`. Callers can construct `MatchException` directly via its constructor, and logging data may be incomplete. Read the stack trace alongside the code and deployment state.

Comparison table:

| Symptom | Typical exception / behavior | What to inspect |
| --- | --- | --- |
| `record` accessor throws during deconstruction | `MatchException`, `getCause()` holds the original exception | Accessor, component, data source, side effects |
| Exhaustive `switch` encounters an instance no longer covered by the current cases | `MatchException`, not necessarily with a cause | Class/enum/sealed hierarchy versions, modules/JARs, and build setup |
| Exhaustive `switch` by type coverage, but a nested record component is `null` so all branches miss | `MatchException`, typically no cause | Nullable component and fallback pattern |
| `switch` selector is `null` with no matching null label | `NullPointerException` | `case null`, null contract |
| `when` guard throws `IllegalArgumentException` | Typically propagates the `IllegalArgumentException` itself | Guard method or expression |
| `->` branch body throws an exception | Exception from the branch body propagates out | Logic executed after branch selection |
| `value instanceof SomeType` does not match | `false` | Normal matching result |
| `switch` expression lacks exhaustiveness at compile time | Compile-time error | Add appropriate cases/default before running |

**Distinguishing "does not match" from "abnormal match failure":** for example, `obj instanceof String s` with an `Integer` returns `false`. That is not a reason to throw `MatchException`.

## 3. Cause 1 — Record Accessor Throws an Exception

A record pattern both checks the type and extracts components using accessors. Every record component has a corresponding accessor, which may be compiler-generated or explicitly declared by the developer.

Example:

```java
record Broken(String text) {
    @Override
    public String text() {
        throw new IllegalStateException("accessor failed");
    }
}
```

When matching the pattern:

```java
// Illustrative snippet inside a method receiving Object value:
return switch (value) {
    case Broken(String text) -> "text:" + text;
    case null -> "missing";
    default -> "other";
};
```

Java must invoke `Broken.text()` to extract the `text` component. Because the accessor throws `IllegalStateException`, record pattern matching completes abnormally and Java throws `MatchException` with **cause** `IllegalStateException("accessor failed")`.

This is not a case of `case Broken(...)` "not matching, so try `default`". **The exception is not turned into a normal match failure.**

JLS 21 section `14.30.2` requires that when an accessor invocation in a record pattern completes abnormally, matching throws `MatchException` whose root cause is that exception. The same mechanism can affect record patterns in `instanceof` as well; it is not limited to `switch`.

### Why can this happen in real systems?

- A custom accessor checks an invalid state and throws an exception.
- An accessor performs computation, reads external data, or relies on mutable state.
- A nested record accessor throws an error during deep deconstruction.
- A dependency changes an accessor's implementation, or the data violates an invariant assumed by the accessor.

**Recommendation:** record accessors should be simple, stable, and have minimal side effects. If invariants must be validated, consider doing so in the record constructor or at the data ingress boundary rather than waiting until deconstruction. Moving validation can change **when** an exception occurs, so confirm the contract before refactoring.

## 4. Cause 2 — Exhaustive Switch with a Nested Record Containing null

This case is subtle because the program **still compiles**.

```java
record Inner(String content) {}
record Outer(Inner inner) {}

static String nested(Outer value) {
    return switch (value) {
        case Outer(Inner(String content)) -> "inner:" + content;
    };
}
```

The compiler can consider the pattern set **type-exhaustive**: `Outer` has a component of type `Inner`, and the nested record pattern covers that type. At runtime, however, the method may receive:

```java
nested(new Outer(null));
```

`Outer` is non-null, but the `inner` component is `null`. The nested record pattern `Inner(...)` **does not match `null`**. There is no other branch, so the `switch` was considered exhaustive at compile time yet finds no applicable label at runtime: Java throws **`MatchException`**.

Comparing three inputs:

| Input | Result |
| --- | --- |
| `new Outer(new Inner("hi"))` | `inner:hi` |
| `new Outer(new Inner(null))` | `inner:null` — `Inner` itself exists; the `String` component inside it is `null` and can still be bound |
| `new Outer(null)` | `MatchException` — the nested record pattern `Inner(...)` cannot match `null` |

The second row is especially important: **`null` for the nested record** differs from **`null` for a component inside an existing nested record**. The *null-matching type pattern* rules in Java 21 explain why `String content` here can be bound to `null`, whereas `Inner(...)` does not match `null`.

### Intentional fixes

If the domain allows `Outer.inner == null`, add a broader record branch:

```java
static String nestedSafe(Outer value) {
    return switch (value) {
        case Outer(Inner(String content)) -> "inner:" + content;
        case Outer(var inner) -> "empty inner";
        case null -> "outer null";
    };
}
```

The `Outer(var inner)` branch is placed **after** the specific nested branch to handle the remaining case. Here, `case null` handles the selector `value == null` itself, not the `inner == null` component.

If the contract **forbids** `inner == null`, instead of silently returning a fallback, consider enforcing the invariant in the constructor:

```java
record StrictOuter(Inner inner) {
    StrictOuter {
        java.util.Objects.requireNonNull(inner, "inner");
    }
}
```

This is a **separate design-change example**, not a drop-in replacement for `Outer`. It shifts the failure from matching time to construction time; decide based on domain requirements.

## 5. Cause 3 — Nested Sealed Patterns and null

A similar situation occurs when a record has a component of a `sealed interface` type:

```java
sealed interface Kind permits Cash, Card {}
record Cash(int cents) implements Kind {}
record Card(String last4) implements Kind {}
record Payment(Kind kind) {}

static String sealedNested(Payment payment) {
    return switch (payment) {
        case Payment(Cash cash) -> "cash:" + cash.cents();
        case Payment(Card card) -> "card:" + card.last4();
    };
}
```

`Kind` has two permitted subtypes, so the compiler can consider the two patterns exhaustive for `Payment`. However:

```java
sealedNested(new Payment(null));
```

matches neither `Cash` nor `Card`: the `kind` component is `null`. The `switch` has no applicable branch, resulting in **`MatchException`**, typically **with no cause**. This is **not** a `NullPointerException` from the selector, because the `Payment` selector itself is non-null.

If `null` is valid, you can use a fallback branch:

```java
static String safePayment(Payment payment) {
    return switch (payment) {
        case Payment(Cash cash) -> "cash:" + cash.cents();
        case Payment(Card card) -> "card:" + card.last4();
        case Payment(var kind) -> "missing kind";
        case null -> "missing payment";
    };
}
```

Do not add a default just to silence the exception without knowing how the domain wants to handle `Payment(null)`. A payment system may need to reject the data rather than replacing it with a default transaction.

## 6. Cause 4 — Separate Compilation Makes a Switch Non-Exhaustive at Runtime

**Exhaustiveness** is typically analyzed **at compile time** based on the enum/sealed subtypes visible to the compiler. A deployment may run classes compiled at different times.

Conceptual scenario:

1. A library initially defines `sealed interface Event permits Created, Cancelled`.
2. A client module is compiled with a switch expression containing `case Created` and `case Cancelled`, so the compiler recognizes it as exhaustive and does not require `default`.
3. The library is upgraded to add the subtype `Updated` and **only the library** is recompiled, while the class containing the switch remains the old build.
4. At runtime, an `Updated` instance arrives. The cases in the old client bytecode do not know about the new subtype; **`MatchException` may be thrown**.

Similarly, adding a new constant to an enum can cause a previously compiled exhaustive switch to fail to match when it encounters the new constant.

Code example **illustrating the old state**, not a standalone program:

```java
// Library v1:
sealed interface Event permits Created, Cancelled {}
record Created() implements Event {}
record Cancelled() implements Event {}

// Client v1, compiled against Library v1:
static String describe(Event e) {
    return switch (e) {
        case Created c -> "created";
        case Cancelled c -> "cancelled";
    };
}
```

If Library v2 adds `record Updated() implements Event` and runs with Client v1 bytecode, the exhaustiveness **checked when Client v1 was compiled** no longer reflects the new set of subtypes. Do not assume that compile-time safety of an older build is a contract covering all future library versions.

**Diagnosis:** compare JAR versions, module path/classpath, build artifacts, container images, the actual loaded classes, and deployment order. **Recompile modules containing switches** against the updated hierarchy/enum and run integration tests on the exact set of artifacts to be deployed. Adding `default` to swallow new subtypes can hide contract violations; only use a fallback if the domain genuinely intends to allow unrecognized cases.

**Note:** not every binary change produces only `MatchException`. Incompatible hierarchy changes can cause other linkage errors, such as `IncompatibleClassChangeError`. Read the specific error type rather than assuming every deployment error is a switch mismatch.

## 7. Complete Java 21 Program to Distinguish Causes

The following code demonstrates **accessor failure**, **nested null**, **nested sealed null**, and exceptions easily mistaken for `MatchException`. To keep the lesson self-contained, the separate compilation scenario in section 6 is presented conceptually; it requires two library/bytecode versions and cannot be reproduced in a single file.

Save as **`MatchExceptionCausesDemo.java`**:

```java
public class MatchExceptionCausesDemo {
    record Broken(String text) {
        @Override
        public String text() {
            throw new IllegalStateException("accessor failed");
        }
    }

    record Inner(String content) {}
    record Outer(Inner inner) {}

    sealed interface Kind permits Cash, Card {}
    record Cash(int cents) implements Kind {}
    record Card(String last4) implements Kind {}
    record Payment(Kind kind) {}

    static String broken(Object value) {
        return switch (value) {
            case Broken(String text) -> "text:" + text;
            case null -> "missing";
            default -> "other";
        };
    }

    static String nested(Outer value) {
        return switch (value) {
            case Outer(Inner(String content)) -> "inner:" + content;
        };
    }

    static String nestedSafe(Outer value) {
        return switch (value) {
            case Outer(Inner(String content)) -> "inner:" + content;
            case Outer(var inner) -> "empty inner";
            case null -> "outer null";
        };
    }

    static String sealedNested(Payment payment) {
        return switch (payment) {
            case Payment(Cash cash) -> "cash:" + cash.cents();
            case Payment(Card card) -> "card:" + card.last4();
        };
    }

    static boolean guard(int value) {
        throw new IllegalArgumentException("guard failed");
    }

    static String guarded(Object value) {
        return switch (value) {
            case Integer x when guard(x) -> "ok";
            case Integer x -> "other integer";
            case null -> "missing";
            default -> "not integer";
        };
    }

    static String noNull(Object value) {
        return switch (value) {
            case String s -> s;
            default -> "other";
        };
    }

    static void show(
            String label, java.util.function.Supplier<String> operation) {
        try {
            System.out.println(label + " => " + operation.get());
        } catch (RuntimeException ex) {
            Throwable cause = ex.getCause();
            String description = cause == null
                    ? "none"
                    : cause.getClass().getSimpleName()
                            + ":" + cause.getMessage();

            System.out.println(
                    label + " => " + ex.getClass().getSimpleName()
                            + " | cause=" + description);
        }
    }

    public static void main(String[] args) {
        show("normal", () -> broken("hello"));
        show("accessor", () -> broken(new Broken("data")));

        show("nested-ok",
                () -> nested(new Outer(new Inner("hi"))));
        show("nested-inner-value-null",
                () -> nested(new Outer(new Inner(null))));
        show("nested-null",
                () -> nested(new Outer(null)));
        show("nested-safe",
                () -> nestedSafe(new Outer(null)));

        show("sealed-ok",
                () -> sealedNested(new Payment(new Cash(10))));
        show("sealed-null",
                () -> sealedNested(new Payment(null)));

        show("guard", () -> guarded(1));
        show("selector-null", () -> noNull(null));
        show("explicit-null", () -> broken(null));
    }
}
```

Compile and run with JDK 21+:

```bash
javac --release 21 MatchExceptionCausesDemo.java
java MatchExceptionCausesDemo
```

**Stdout:**

```text
normal => other
accessor => MatchException | cause=IllegalStateException:accessor failed
nested-ok => inner:hi
nested-inner-value-null => inner:null
nested-null => MatchException | cause=none
nested-safe => empty inner
sealed-ok => cash:10
sealed-null => MatchException | cause=none
guard => IllegalArgumentException | cause=none
selector-null => NullPointerException | cause=none
explicit-null => missing
```

### From Output to Root Cause

- **`accessor`:** `Broken.text()` throws `IllegalStateException`. The record pattern wraps it in `MatchException`; `getCause()` points to the original error.
- **`nested-null`:** the selector `new Outer(null)` exists, but `Inner(...)` does not match. Because the switch has no other cases and was considered exhaustive by the compiler, `MatchException` is thrown **without a cause**.
- **`nested-inner-value-null`:** `Inner` exists and its accessor returns `content == null`; the component type pattern can bind `null`, so the result is `inner:null` with no exception.
- **`nested-safe`:** the fallback `Outer(var inner)` branch handles the case where the nested record component is `null`.
- **`sealed-null`:** `Payment(null)` matches neither `Payment(Cash ...)` nor `Payment(Card ...)`, resulting in `MatchException` with no cause.
- **`guard`:** `when guard(x)` calls a method that throws `IllegalArgumentException`; the exception propagates as-is and is not wrapped in `MatchException`.
- **`selector-null`:** missing `case null` causes a `null` selector to throw `NullPointerException`, not `MatchException`.
- **`explicit-null`:** `case null` is declared, so the method returns `missing` normally.

The `show` helper catches `RuntimeException` for **demonstration** purposes to print concise results. This is not a recommended production strategy: it intentionally swallows exceptions so the program can continue through each test case. In a real application, handle or propagate errors according to the contract while preserving the stack trace.

## 8. Distinguishing MatchException from Similar Errors

### 8.1. `NullPointerException` from a `null` Selector

A pattern switch selector does not automatically match `default` when it is `null`. Example:

```java
Object value = null;

// May throw NullPointerException:
String result = switch (value) {
    case String s -> "text";
    default -> "other";
};
```

Fix according to the domain:

```java
String result = switch (value) {
    case String s -> "text";
    case null -> "missing";
    default -> "other";
};
```

**Do not confuse:** `case null` at the selector level **does not fix** `new Outer(null)` when the selector is a non-null `Outer`.

### 8.2. Exceptions from Guards, Selector Expressions, and Branch Bodies

Suppose:

```java
case Integer x when validate(x) -> "approved";
```

If `validate(x)` throws an exception, that exception itself normally propagates rather than being treated as the guard returning `false`. If the selector is a method `source()` and `source()` throws, evaluating the selector has failed **before** any case is tested. If the `->` branch is selected and then calls `process(...)` which throws, the failure is in the **branch's processing**, and is not automatically wrapped in `MatchException`.

Therefore, when reading a stack trace, determine whether **the failure occurred before matching, inside a record accessor, inside a guard, or inside a branch body**.

### 8.3. `ClassCastException` and Compile-Time Type Errors

`(SomeType) value` can throw `ClassCastException` if the runtime type cannot be cast to `SomeType`. By contrast, `instanceof SomeType s` simply returns `false` when it does not match.

Meanwhile, if a pattern label is not applicable to the static type of the selector, the compiler rejects the code; that error **does not exist at runtime to produce `MatchException`**. For example, a selector of type `String` with `case Integer i` is an incompatible type error.

### 8.4. `IncompatibleClassChangeError`

This is an `Error` related to binary/linkage consistency, distinct from `MatchException`. Upgrading a class hierarchy can produce different failure modes depending on the kind of change. Do not lump all "binary drift" errors together as `MatchException`, and do not try to fix `IncompatibleClassChangeError` by adding an arbitrary `case`.

## 9. Tracing the Root Cause in a Real Application

### Step 1 — Preserve the Exception and Stack Trace

In a centralized error-handling point, you can use:

```java
try {
    return dispatch(value);
} catch (MatchException ex) {
    Throwable root = ex.getCause();
    if (root != null) {
        // Log the type and stack trace of the accessor cause.
        logger.error("Pattern matching failed in accessor", ex);
    } else {
        // Investigate value/shape and potential exhaustive-runtime mismatch.
        logger.error("No matching pattern at runtime", ex);
    }
    throw ex;
}
```

This is **illustrative code**, not a standalone snippet: `dispatch` and `logger` are assumed application components. Do not log sensitive data when inspecting selectors or records.

Do not log only `ex.getMessage()` and discard `ex.getCause()`. The root exception can reveal which accessor threw, the call site, and the object whose invariant was violated. At the same time, **a `null` cause is a valid data point**, not proof that a message was lost.

### Step 2 — Classify the Active Pattern Kind

- Is there a **record pattern** (including nested ones) invoking a custom accessor?
- Is there a **sealed switch** or exhaustive enum switch omitting `default` because the compiler inferred coverage?
- Is there a **nested record** or **nested sealed component** that allows `null`?
- Does `when` call an impure method, or does a branch body perform a transformation that can throw?

Set breakpoints in the record accessor, before/at the start of the guard, and in the selected branch to pinpoint the failing stage.

### Step 3 — Inspect the Actual Runtime Classes

For errors suspected to be caused by separate compilation, compare:

- The source and compiled classes of the module containing the `switch`.
- The versions of the enum/sealed library at compile time and runtime.
- JAR/classpath/module path order, dependency tree, shaded artifacts, or container images.
- History of added enum constants or permitted subtypes.
- Tests against the exact set of artifacts to be deployed, not just unit tests using the IDE classpath.

If `getCause()` clearly points to an accessor throwing, investigate the accessor first. If the cause is `null` and the case involves nested records, check for `null` components before hunting for a build issue.

### Step 4 — Fix the Cause, Not the Symptom

| Actual cause | Remediation |
| --- | --- |
| Accessor throws an error | Fix the invariant/data or accessor logic; preserve the cause trace; avoid unnecessary side effects |
| Nested `null` record component is allowed | Add an accurate fallback branch or adjust the pattern to match the schema |
| Nested `null` component is forbidden | Validate explicitly at the boundary/constructor; test invalid inputs |
| Sealed/enum extended while switch was built against an older version | Recompile and re-release dependent modules against the same version, adding the new branches |
| Error from `when` or branch body | Fix the condition/business logic where the exception is actually thrown |
| `null` selector not accounted for | Define the null contract and use `case null` / appropriate input validation |

**Do not default to adding `default -> "other"` to every exhaustive switch.** For a sealed hierarchy, a switch without `default` can be a valuable mechanism for the compiler to remind you to update handling when a subtype is added. For nullable components, a more specific pattern at the right level can preserve subtype checking better than an overly broad fallback.

## 10. Common Mistakes When Debugging MatchException

1. **"MatchException means `instanceof` returned false."** False; a normal type mismatch simply evaluates to `false` or moves to the next case.
2. **"Every MatchException has a cause in `getCause()`."** False; an exhaustive switch mismatch may have no cause.
3. **"Just adding `case null` fixes nested null."** False; a `null` selector and a `null` component belong to two different levels.
4. **"`default` always handles a `null` selector."** False in Java 21 pattern switches; missing a matching null label can throw NPE.
5. **"Adding a subtype to a sealed hierarchy is always picked up automatically by old clients."** False; already-compiled switches may not be exhaustive at runtime.
6. **"If an accessor throws, the switch tries the next case."** False; an accessor error in a record pattern is wrapped in `MatchException` rather than falling through to the next case.
7. **"If a guard throws, it gets wrapped in MatchException."** Incorrect under normal guard semantics; the exception from the guard propagates out.
8. **"Every runtime type-classification issue causes MatchException."** False; bad casts, linkage errors, `null` selectors, and compile-time errors are fundamentally different.
9. **"Returning a default value is a safe fix."** Not if the domain needs to reject the transaction or detect unhandled subtypes.
10. **"Testing a single non-null record is enough."** No; test `null` selectors, `null` components, nested `null`, throwing accessors, and dependency evolution where applicable.
11. **"Reading just the message line is enough."** No; inspect the cause, stack trace, and deployment metadata.
12. **"Catching RuntimeException and continuing is fine."** No; the demo does this for illustration, whereas production must follow the error contract, logging, and rollback rules.

## 11. Prevention Checklist

Before merging Java 21+ pattern-matching code, ask yourself:

- [ ] For every record pattern, can the accessor throw an exception or have unexpected side effects?
- [ ] To what extent is `null` allowed at the **selector**, **nested record**, and **components inside nested records**?
- [ ] Are exhaustive switches over sealed hierarchies/enums built and deployed in sync with the current definitions?
- [ ] If a subtype or enum constant is added, is there a process to rebuild dependent modules and run integration tests?
- [ ] Are there test cases for `new Outer(null)`, `new Outer(new Inner(null))`, and a `null` selector when the domain allows them?
- [ ] When debugging `MatchException`, do you inspect `getCause()`, the stack trace, and identify the failing stage?
- [ ] Do guards and branch bodies throw their own exceptions that need handling at the business layer?
- [ ] Is any fallback/`default` true to the contract rather than added merely to hide errors?
- [ ] Is the error type monitored with sufficient context without leaking sensitive data?

**Remember:** `MatchException` is a sign of an **abnormal matching failure**, not a pattern check returning `false`. The two most important causes are **a record accessor throwing (with a cause)** and **an exhaustive switch failing to match at runtime (possibly without a cause)**. Identify the right `null` level, verify binary compatibility of sealed types and enums, and handle errors according to the domain contract rather than catching and ignoring them.

### References

- Oracle Java 21 API — `java.lang.MatchException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html
- Java Language Specification SE 21 — `14.30.2 Pattern Matching` and `14.11.3 Execution of switch`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html
- Oracle Java 21 — Pattern Matching for switch Expressions and Statements: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
