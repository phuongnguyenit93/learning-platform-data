# Abrupt Completion of Pattern Matching (Java 21)

## 1. Concept: Non-Matching vs. Abrupt Completion

**Pattern matching** is the process of testing a value at runtime against a *pattern*, such as a type pattern `String s` or a record pattern `Point(int x, int y)`. If it matches, the pattern variables are bound for use within their valid scope.

According to the Java Language Specification (JLS) 14.30.2, there are two categories of outcomes at the **matching process** level:

- **Normal completion:** Matching finishes without throwing an exception; the result can be either a **match** or a **non-match**.
- **Abrupt completion:** While determining whether there is a match, an evaluation involved throws an exception, causing the matching process to stop. At the **pattern matching** level, the reason for abrupt completion is **`throw`**, not a `false` value.

This is especially important in Java 21 because **record patterns** can implicitly invoke accessors to read components. If an accessor throws an error, Java has the `MatchException` mechanism. A `when` guard and a `switch` selector expression can also throw exceptions, though they are not always converted into `MatchException`.

| Scenario | Outcome | Is the next branch tried? |
| --- | --- | --- |
| `Object` is not a `String` when testing `instanceof String s` | Matching completes normally, **non-match** | With `switch`, the next case can be evaluated |
| `null` selector in `instanceof SomeRecord(...)` | Completes normally, **non-match** | `instanceof` returns `false` |
| Nested record component is `null` before an inner record pattern | Inner record pattern **does not match** normally | Other cases can be evaluated; runtime exhaustiveness risk still applies |
| Record component accessor throws an exception | **Abrupt completion**, throws `MatchException` | Does **not** continue to a fallback case |
| `when` guard throws an exception | Case selection completes **abruptly** with the original exception | Does **not** continue to a fallback case |
| `when` guard returns `false` | That branch does not apply, not an exception | **Yes**, evaluates the next case |
| `switch` selector throws an exception | `switch` terminates abruptly with the original exception | Matching does not start |
| `null` selector when `switch` has no branch accepting `null` | `NullPointerException` during branch selection | A plain `default` does not catch `null` |
| No pattern matches in a switch deemed exhaustive | May throw `MatchException` at runtime | No normal result |

**Version scope:** Type patterns with `instanceof` have been a standard feature since Java 16. **Record patterns** (JEP 440) and **pattern matching for `switch`** (JEP 441) became standard in **Java 21**, without needing `--enable-preview`. This article uses Java 21 syntax, where `java.lang.MatchException` is available.

## 2. Different Places Where Exceptions Can Be Thrown

To analyze accurately, pattern processing should be divided into stages:

1. **Evaluating the input expression (*selector / operand*)**. For example, `getValue() instanceof String s` must call `getValue()` first; `switch (getValue())` must also evaluate `getValue()` first.
2. **Matching the pattern**. For a regular type pattern, Java checks the type; for a record pattern, the runtime must access the record components via accessors and then continue checking the component patterns, including nested record patterns.
3. **Evaluating the `when` guard** of a `switch` case, if the pattern matched and the case has a guard.
4. **Executing the selected branch body**. The body can compute values, call methods, `throw`, `return`, or transfer control flow.

When an exception occurs at each location, what is observed differs:

- An exception from the **input expression** is propagated as that exact exception; the pattern has not been matched yet.
- An exception from a **record accessor implicitly invoked during deconstruction** is wrapped in a `MatchException` whose `cause` is the original exception, per JLS 14.30.2.
- An exception from a **guard** is propagated with the same reason, following `switch` branch selection rules; it is not automatically converted into `MatchException`.
- An exception thrown by the **case body** itself is an error while executing the already-selected business logic, not a pattern matching failure. It propagates according to standard Java rules.

Not every exception arising around a `switch` should be lumped together as a "pattern error": a failure from business code in the case body is different from a failure during matching or case selection.

## 3. Runnable Java 21 Example: Simulating Each Case

Create the file **`AbruptPatternDemo.java`**:

```java
public class AbruptPatternDemo {
    sealed interface Choice permits Yes, No {}

    record Yes() implements Choice {}
    record No() implements Choice {}
    record Wrapper(Choice choice) {}

    record Item(String text) {}
    record Outer(Item item) {}

    record Fragile(String text) {
        @Override
        public String text() {
            throw new IllegalStateException("accessor failed");
        }
    }

    static boolean guard(String text) {
        throw new IllegalArgumentException("guard failed");
    }

    static Object selector() {
        throw new IllegalArgumentException("selector failed");
    }

    static String guarded(Object value) {
        return switch (value) {
            case String text when guard(text) -> "guarded";
            case String text -> "plain";
            case null -> "null";
            default -> "other";
        };
    }

    static String noNullCase(Object value) {
        return switch (value) {
            case String text -> "text";
            default -> "other";
        };
    }

    static String nested(Wrapper value) {
        return switch (value) {
            case Wrapper(Yes yes) -> "yes";
            case Wrapper(No no) -> "no";
        };
    }

    static String bodyThrows(Object value) {
        return switch (value) {
            case String text ->
                throw new UnsupportedOperationException("body failed");
            case null -> "null";
            default -> "other";
        };
    }

    static void test(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": completed");
        } catch (RuntimeException ex) {
            String cause = ex.getCause() == null
                ? "none" : ex.getCause().getClass().getSimpleName();
            System.out.println(label + ": "
                + ex.getClass().getSimpleName() + ", cause=" + cause);
        }
    }

    public static void main(String[] args) {
        Object wrong = new Item("hello");
        Object missing = null;
        Object innerNull = new Item(null);
        Object nestedNull = new Outer(null);

        System.out.println("differentType="
            + (wrong instanceof Fragile(String s)));
        System.out.println("nullType="
            + (missing instanceof Item(String s)));
        System.out.println("nullComponent="
            + (innerNull instanceof Item(String s)));
        System.out.println("nullNested="
            + (nestedNull instanceof Outer(Item(String s))));

        test("accessor", () -> {
            Object value = new Fragile("demo");
            boolean matches = value instanceof Fragile(String s);
        });
        test("guard", () -> guarded("hello"));
        test("selector", () -> guarded(selector()));
        test("nullSelector", () -> noNullCase(null));
        test("nestedExhaustive", () -> nested(new Wrapper(null)));
        test("caseBody", () -> bodyThrows("hello"));

        System.out.println("normalNested="
            + nested(new Wrapper(new Yes())));
    }
}
```

Use **JDK 21 or later**:

```bash
javac --release 21 AbruptPatternDemo.java
java AbruptPatternDemo
```

**Exact stdout:**

```text
differentType=false
nullType=false
nullComponent=true
nullNested=false
accessor: MatchException, cause=IllegalStateException
guard: IllegalArgumentException, cause=none
selector: IllegalArgumentException, cause=none
nullSelector: NullPointerException, cause=none
nestedExhaustive: MatchException, cause=none
caseBody: UnsupportedOperationException, cause=none
normalNested=yes
```

The example intentionally throws exceptions in some cases, but `test` catches them so the program continues running through the remaining scenarios. The code in `main` does not open files, access the network, or depend on libraries outside the JDK.

## 4. Normal Non-Match: `false` Is Not an Exception

In the first four lines:

**`differentType=false`:** `wrong` holds an `Item`, not a `Fragile`. `wrong instanceof Fragile(String s)` returns `false`. There is no exception, and no pattern variable `s` is in scope outside the matching branch.

**`nullType=false`:** `missing` is `null`. An `instanceof Item(String s)` with a null selector returns `false`; a record pattern does not match a null reference.

**`nullComponent=true`:** `innerNull` is `new Item(null)`, meaning the outer record exists, but its `text` component is `null`. `Item(String s)` is a record pattern with an **unconditional type pattern `String s` at a component position declared with type `String`**. In Java 21, a type pattern that is unconditional for the corresponding component type is **null-matching** at this position, so `s` can be bound to `null`. Do not infer from this that `null instanceof String` would evaluate to `true`.

**`nullNested=false`:** `nestedNull` is `new Outer(null)`. The pattern `Outer(Item(String s))` requires the `item` component to match an actual `Item` record. `item == null` causes the nested **record pattern** not to match; the result of the entire `instanceof` is `false`, rather than throwing an exception.

Key takeaway: **`null` in the selector**, **`null` in a component with an unconditional type pattern**, and **`null` in a nested record pattern** can produce three different results. You must read the exact position of `null` in the structure.

## 5. Record Accessor Throws an Exception: `MatchException` with `cause`

In the code, the `Fragile` record overrides the `text()` accessor:

```java
record Fragile(String text) {
    @Override
    public String text() {
        throw new IllegalStateException("accessor failed");
    }
}
```

When matching `value instanceof Fragile(String s)`, the runtime needs to read the `text` component to test the corresponding pattern. Reading a component of a record pattern uses the **accessor method**. The accessor throws `IllegalStateException`, so Java 21 causes the matching process to complete abruptly with a **`MatchException`** whose `cause` is the original error.

Result:

```text
accessor: MatchException, cause=IllegalStateException
```

This is not:
- `false` from a record pattern not matching;
- a `ClassCastException` from a manual cast;
- something a `default` branch can catch instead;
- an exception thrown from a case body.

You can inspect the cause with:

```java
// Illustrative snippet assuming Object value is already defined:
try {
    if (value instanceof Fragile(String text)) {
        System.out.println(text);
    }
} catch (MatchException ex) {
    Throwable root = ex.getCause();
    System.err.println("Pattern matching failed: " + root);
    throw ex; // Or handle according to the application contract.
}
```

The code above is an **illustrative snippet**, requiring the `Fragile` type from the program and the `value` variable. `MatchException` is an unchecked exception (`RuntimeException`), so `catch (RuntimeException ex)` also catches it, but in practice you should identify the exact error type before deciding how to handle it.

**Note:** Default record accessors typically only return the component. Overriding an accessor to throw exceptions or cause side effects makes matching unpredictable. Avoid accessors with side effects; validate invariants in the constructor or an appropriate domain API. Do not catch all `MatchException`s and pretend the pattern did not match: doing so hides a real bug.

According to Java 21, a `MatchException` caused by an accessor throwing an error preserves that exception in `getCause()`. However, **not every `MatchException` has a cause**, as shown in the runtime coverage failure example in section 8.

## 6. `when` Guard Throws an Exception: Not Converted to `false`

A `switch` with a pattern and a guard:

```java
// Illustrative snippet inside a method with an Object variable named value:
return switch (value) {
    case String text when check(text) -> "accepted";
    case String text -> "fallback";
    case null -> "null";
    default -> "other";
};
```

The case selection order is:

1. Check whether the selector matches `String text`.
2. Only when the pattern matches is `check(text)` evaluated.
3. If the guard returns `true`, the case applies.
4. If the guard returns `false`, evaluate the next branch.
5. If the guard **throws an exception**, the entire branch selection process terminates abruptly **with that exception**; `case String text -> "fallback"` is **not** tried.

In `AbruptPatternDemo`, `guard(text)` always throws `IllegalArgumentException` and the output is:

```text
guard: IllegalArgumentException, cause=none
```

There is no automatic conversion of a `when` exception into `MatchException`. To see a guard fail normally and allow fallback, write a condition that returns a boolean:

```java
// Illustrative snippet inside the same switch expression:
case String text when text.length() > 5 -> "long";
case String text -> "short";
```

If `text` has length 3, the first guard returns `false` and the second branch is selected normally. If a guard contains an expression that dereferences a potentially null component, you must explicitly check for `null` first; a `NullPointerException` thrown by a guard will propagate and is **not** treated as `false`.

**Another distinction:** A guard expression of type `Boolean` can also throw `NullPointerException` if a `null` value is unboxed to test the condition. The compiler accepting type `Boolean` does not guarantee that evaluating the guard is always safe.

## 7. Exception While Evaluating the Selector: Pattern Has Not Run Yet

In the line:

```java
test("selector", () -> guarded(selector()));
```

The `selector()` method throws `IllegalArgumentException` before `guarded(...)` receives its argument. No case selection step in `guarded` is executed. Output:

```text
selector: IllegalArgumentException, cause=none
```

A similar situation:

```java
// Illustrative snippet, assuming getValue() may throw an exception:
if (getValue() instanceof String text) {
    System.out.println(text);
}
```

Evaluating the left-hand operand of `instanceof` happens before pattern matching. If `getValue()` throws an error, the `instanceof` expression completes abruptly with the original error, rather than returning `false`.

**Lesson:** When you see a stack trace from a statement containing a pattern, you need to determine whether the error occurred in the **selector**, **record accessor**, **guard**, or **case body**. Knowing that they are on the same source line is not enough to conclude the cause.

## 8. `null` in `switch` and `MatchException` When Runtime Exhaustiveness Fails

### 8.1. `null` Selector Without a `case null`

The `noNullCase` method:

```java
static String noNullCase(Object value) {
    return switch (value) {
        case String text -> "text";
        default -> "other";
    };
}
```

With `value == null`, Java throws `NullPointerException`. `default` does not automatically accept `null`. Output:

```text
nullSelector: NullPointerException, cause=none
```

If you want a dedicated result, add:

```java
case null -> "no value";
```

You can use `case null, default -> ...` in appropriate cases, but a separate `case null` is often clearer when the logic for missing data differs from the logic for unsupported types.

### 8.2. A `switch` Deemed Exhaustive That Has No Matching Branch at Runtime

This is a particularly important case of pattern matching over a **sealed hierarchy** combined with record patterns:

```java
sealed interface Choice permits Yes, No {}
record Yes() implements Choice {}
record No() implements Choice {}
record Wrapper(Choice choice) {}

static String nested(Wrapper value) {
    return switch (value) {
        case Wrapper(Yes yes) -> "yes";
        case Wrapper(No no) -> "no";
    };
}
```

This is an **illustrative snippet extracted from the complete program**. `Choice` is sealed and has exactly two subtypes, `Yes` and `No`. Therefore, the compiler can treat the two nested record patterns as exhaustive for `Wrapper`.

However, `new Wrapper(null)` can still be constructed because the record component `choice` is not automatically prohibited from being `null`. When executed:

```java
nested(new Wrapper(null));
```

- The `Wrapper` selector is non-null.
- `case Wrapper(Yes yes)` does not match because the `choice` component is `null`, and the `Yes` type pattern is not null-matching at a position with declared type `Choice`.
- `case Wrapper(No no)` also does not match.
- Even though the compiler proved coverage based on the hierarchy, no actual branch accepts this value. The runtime throws **`MatchException`**.

Output:

```text
nestedExhaustive: MatchException, cause=none
```

Unlike an accessor failure, `MatchException` here can have **no cause**. This is one of the scenarios documented in the official Java 21 API documentation for `java.lang.MatchException`.

Another cause of this "unexpected non-match" kind of `MatchException` is **separate compilation**: the `switch` is compiled against an older set of subtypes/enum constants, and then run against a modified hierarchy definition without recompiling the `switch`. The compiler guarantees exhaustiveness for the model it sees at compile time, which does not completely eliminate incompatible changes at runtime.

### 8.3. Proper Fixes: Control `null` at the Boundary or Add an Appropriate Fallback

There are at least two design approaches:

**Option A — Disallow `null` components when creating the record.** If `Wrapper.choice` is required, add a canonical/compact constructor that validates it:

```java
record Wrapper(Choice choice) {
    Wrapper {
        java.util.Objects.requireNonNull(choice, "choice");
    }
}
```

This is an **alternative design choice** for the record definition in the example; do not put both `Wrapper` declarations in the same file. `new Wrapper(null)` then fails immediately in the constructor with `NullPointerException`, instead of throwing `MatchException` later during matching.

**Option B — Accept `null` and handle it first.** If `null` is valid data, place a guarded case that catches the `null` component:

```java
// Illustrative snippet of an alternative method:
static String safeNested(Wrapper value) {
    return switch (value) {
        case null -> "missing wrapper";
        case Wrapper(var choice) when choice == null -> "missing choice";
        case Wrapper(Yes yes) -> "yes";
        case Wrapper(No no) -> "no";
    };
}
```

At the component position of `Wrapper`, `var choice` accepts `null` as well, while the guard `choice == null` filters specifically for that value. The `Yes`/`No` patterns continue handling the remaining variants. Do not place an **unguarded** `Wrapper(var choice)` case before the more specific cases, because it would dominate them and cause a *dominance* compile error.

**Do not** blindly catch `MatchException` and return `"other"` for every case: that can hide both broken accessors and hierarchy changes that require source updates.

## 9. Case Body Throws an Exception: Not a Matching Failure

The `bodyThrows` method already selected the `String text` case:

```java
static String bodyThrows(Object value) {
    return switch (value) {
        case String text ->
            throw new UnsupportedOperationException("body failed");
        case null -> "null";
        default -> "other";
    };
}
```

Output when called with `"hello"`:

```text
caseBody: UnsupportedOperationException, cause=none
```

Here, the pattern matched successfully; the exception only occurs **afterward** due to the statement in the branch. Java does not wrap every case body exception in `MatchException`. Another branch in the same `switch` is not tried as a fallback mechanism after a body has been selected.

This helps with debugging: a `MatchException` when reading a record component is distinct from an `UnsupportedOperationException` thrown by the message-handling service itself.

## 10. Pattern Abrupt Completion vs. Statement Abrupt Completion

The JLS uses the term **abrupt completion** for both expressions and statements. At the **statements** level, `return`, `break`, `continue`, `yield`, and `throw` can transfer control flow; for instance, a `return` can abruptly complete the currently executing method in the sense that subsequent statements do not execute sequentially.

However, at the **pattern matching process** level (JLS 14.30.2), abrupt completion is described by **`throw`**. A `break` executed inside a case body is not called a "pattern non-match". For example:

```java
// Traditional switch statement where branches use case type patterns:
switch (value) {
    case String text:
        System.out.println(text);
        break;
    case null:
        System.out.println("null");
        break;
    default:
        System.out.println("other");
}
```

When `case String text` matches, `break` exits the switch statement. This is post-matching control flow; there is no `MatchException`.

With a **switch expression**, `yield` in a case block is used to produce a result:

```java
// value has type Object:
String result = switch (value) {
    case String text -> {
        String cleaned = text.trim();
        yield cleaned;
    }
    case null -> "null";
    default -> "other";
};
```

`yield` does not represent a pattern failure either. It transfers the branch's value out of the switch expression.

**In summary:** "Pattern matching completes abruptly" should be understood primarily as **an exception while testing a pattern**. Statement/expression control-flow mechanisms are a related topic, but differ in timing and meaning.

## 11. Handling Exceptions Safely in Applications

A solid strategy consists of the following steps:

1. **Define the null contract:** Can the selector be `null`? Which record components are required? Enforce invariants in the constructor if that makes sense for the domain.
2. **Keep accessors simple:** Record accessors should return predictable data, avoiding I/O, state mutation, or intentionally throwing exceptions during deconstruction.
3. **Keep guards pure and null-safe:** `when` guards should be boolean checks with minimal side effects. Handle `null` / invalid values explicitly.
4. **Use fallback cases for valid but non-matching data:** Fallbacks handle *non-matches*, not catching exceptions.
5. **Use `try/catch` at appropriate boundaries:** Distinguish `MatchException`, `IllegalArgumentException`, `NullPointerException`, and business errors. Preserve `getCause()` and stack traces when diagnostics are needed.
6. **Recompile together after hierarchy changes:** Sealed/enum exhaustive switches can encounter mismatches when modules are built and deployed out of sync.
7. **Test success, `false`, and `throw` cases:** Do not test only the happy-path matched case; include nullable components, throwing guards, abnormal accessors, and unexpected subtypes.

**Example of handling a branch without swallowing errors:**

```java
// Illustration: do not arbitrarily turn MatchException into "no match".
try {
    String answer = nested(input);
    System.out.println(answer);
} catch (MatchException ex) {
    System.err.println("Unexpected pattern failure");
    if (ex.getCause() != null) {
        System.err.println("Root cause: " + ex.getCause());
    }
    throw ex; // Or translate into an error at the application boundary per contract.
}
```

In this snippet, `input` must be a variable of type `Wrapper`, and `nested` is the method defined in the program. This is an example of an **error-reporting policy**, not a requirement to catch every `MatchException` in all code.

### Common Mistakes

| Misconception | Consequence | Correct Understanding / Fix |
| --- | --- | --- |
| "When a pattern doesn't match, it throws an exception" | Catching exceptions for a normal outcome | A non-match normally just returns `false` or evaluates another case |
| "Whatever a record accessor throws, the pattern throws as-is" | Wrongly catching `IllegalStateException` outside the record pattern | Java 21 wraps accessor errors into `MatchException` with the original `cause` |
| "If a guard throws an exception, the next case is tried" | Hiding errors or expecting fallback that never happens | A throwing guard ends case selection abruptly; only a guard returning `false` moves on |
| "`default` catches `null` too" | `NullPointerException` on a `null` selector | Add `case null` or handle `null` before the `switch` |
| "Sealed exhaustive means `MatchException` can never happen" | Overlooking nested `null` and separate compilation | Validate `null`/invariants, keep builds in sync; test runtime behavior |
| "Exceptions cannot occur in `instanceof`" | Ignoring that the operand or accessor can throw | Distinguish operand evaluation from record accessor invocation |
| "An exception in a case body is a pattern error" | Misdiagnosing which layer failed | The case body runs after matching has already succeeded |
| "Catching `MatchException` covers all errors" | Missing guard, selector, and case body exceptions | Categorize by stage and contract |
| "`MatchException.getCause()` is always non-null" | Can cause an NPE when reporting errors | Check `cause` before using it |

## 12. Testing and Exercises

### Recommended Test Cases

- Input of the right type with valid components: pattern matches normally.
- Input of a different type: `instanceof` returns `false`, no exception thrown.
- `null` selector: `instanceof` is `false`; `switch` with `case null` handles it, while missing `case null` can throw `NullPointerException`.
- Unconditional type pattern in a reference-type record component: verify `null`-binding behavior.
- `null` nested record component: nested pattern does not match; test fallback case or invariant.
- Custom record accessor throwing `IllegalStateException`: inspect `MatchException.getCause()`.
- Guard returns `false`: subsequent case is evaluated; guard throws exception: subsequent case does not run.
- Exhaustive `switch` based on sealed nested patterns with a `null` component: test `MatchException`.
- Case body throws an error: original error propagates, not wrapped in `MatchException`.
- Sealed subtype changes across modules: rebuild and retest consumers with exhaustive switches.

### Exercise 1 — Distinguish `false` from `throw`

Create `record User(String name) {}`. With a variable `Object value`, run:
- `value = "hello"` and test `value instanceof User(String name)`;
- `value = null` and test the same pattern;
- `value = new User(null)` and test the same pattern.

Predict `true`/`false` before running, and explain why a `null` component does not necessarily cause the record pattern to fail.

### Exercise 2 — Fix a Guard That Can Throw NPE

Create `record Text(String value) {}`, then write `case Text(String s) when s.isBlank()`. Pass `new Text(null)` to observe the exception. Fix it by placing `case Text(String s) when s == null` before it, or by using a null-safe guard condition; retest with `null`, empty, and non-empty strings.

### Exercise 3 — `MatchException` and `cause`

Create a record with a custom accessor that throws `IllegalStateException`, then match it using `instanceof` with a record pattern. Catch `MatchException` and print `ex.getCause().getClass().getSimpleName()`. Explain why catching the original exception outside the pattern would not catch it directly.

### Exercise 4 — Exhaustiveness and Nested `null`

Starting from `AbruptPatternDemo`, update `nested` so it also handles `new Wrapper(null)`. Try both approaches:
- Validate that `choice` is non-null in `Wrapper`'s constructor.
- Add `case Wrapper(var choice) when choice == null` before the `Yes`/`No` cases, and also add `case null` if `Wrapper` itself may be `null`.

Explain why a fallback case for a `null` component is not the same as a `case null` for the selector.

### Exercise 5 — Errors at Four Stages

Cause an error to occur in turn at the selector, record accessor, guard, and case body. For each run, record the caught exception class, the value of `getCause()`, and whether a branch was executed or not. Compare your results with the table in section 1.

## 13. Summary

A pattern **non-match** is a normal outcome of matching; it is **not equivalent** to "abrupt completion". In Java 21, the matching process can complete abruptly when a record accessor throws an exception, in which case Java uses **`MatchException`** holding the original exception in `cause`. In a `switch`, exceptions from the **selector**, **guard**, and **case body** are handled by their own rules, typically propagating as the original exception.

Even a `switch` that the compiler has deemed exhaustive can encounter `MatchException` at runtime, typically when a **nested record pattern fails to match a `null` component** or due to **mismatches between separately compiled modules**. Proper design requires proactively defining invariants and null policies, keeping accessors and guards predictable, testing thoroughly, and never conflating exceptions with case fallbacks.

## References

- Java Language Specification SE 21 — `14.30.2 Pattern Matching`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2
- Java Language Specification SE 21 — `14.11.3 Execution of a switch Statement`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3
- Java Language Specification SE 21 — `15.28 switch Expressions`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- Java SE 21 API — `java.lang.MatchException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
