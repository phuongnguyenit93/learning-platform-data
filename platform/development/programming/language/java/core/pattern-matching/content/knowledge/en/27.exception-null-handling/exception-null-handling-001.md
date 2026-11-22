# Exceptions in Record Pattern Accessors (Java 21)

## 1. The core problem: a record pattern doesn't just "peek" at fields

A **record pattern** deconstructs a record object to test and bind its components:

```java
record Label(String value) {}

Object candidate = new Label("OK");
if (candidate instanceof Label(var labelText)) {
    System.out.println(labelText);
}
```

The result is `OK`. What is easy to overlook: Java **retrieves component values by invoking the corresponding accessor**, such as `Label.value()`. In the case of a compiler-generated accessor, it simply returns the component field. However, a record **is allowed to declare an explicit accessor** with its own method body, and that body can throw an *unchecked exception*.

Therefore, with:

```java
if (candidate instanceof Label(var labelText)) {
    // ...
}
```

deconstruction can perform extra work, and can even fail **before entering the `if` branch**. You must not assume that a record pattern is merely a pure type check with no method invocations.

This is the key point of this lesson: **if an accessor invoked during record pattern matching throws an exception, pattern matching completes abruptly with `java.lang.MatchException`; the original exception is in `getCause()`**. This is the behavior specified in the Java Language Specification 21, `14.30.2. It differs from a pattern failing to match and also differs from calling the accessor directly.

## 2. What is a record accessor?

Given:

```java
record Ticket(String code, int priority) {}
```

Java provides the accessors `code()` and `priority()`. When not explicitly declared, they return the corresponding component field:

```java
Ticket ticket = new Ticket("TK-1", 3);
System.out.println(ticket.code());     // TK-1
System.out.println(ticket.priority()); // 3
```

A record can also declare an explicit accessor:

```java
record Label(String value) {
    public String value() {
        if (value == null) {
            throw new IllegalStateException("missing label");
        }
        return value.strip();
    }
}
```

The `value` field is still the record's component field, while the `value()` accessor now has **custom logic**:

- Returns the trimmed version with leading and trailing whitespace removed via `strip()` when data is present.
- Throws `IllegalStateException` if the component value is `null`.

This is an example that **deliberately creates a failure-prone accessor** to observe pattern matching behavior, not a design to prefer for ordinary data records. If a component must be non-`null` or needs normalization, it is usually better to validate/normalize **right in the constructor** so that a record in an invalid state cannot be created.

**Language restriction:** a record accessor must be a `public` instance method, take no parameters, have the same return type as the component, and **must not have a `throws` clause**. It can still throw unchecked exceptions such as `IllegalStateException`, `IllegalArgumentException`, `NullPointerException`, or `Error` under Java rules; omitting `throws` does not guarantee that the accessor cannot fail.

The following example **intentionally does not compile**:

```java
record BadAccessor(String code) {
    public String code() throws java.io.IOException {
        return code;
    }
}
```

The compiler will report an error like `throws clause not allowed for accessor method`. If an accessor needs to call an API that throws a checked exception, you cannot simply add `throws IOException`; instead, redesign where data retrieval/validation happens, or handle the exception internally according to an appropriate contract.

## 3. How are exceptions in an accessor handled during matching?

Given a record value `r` and a pattern `R(...)`, record matching needs to obtain each component value through `r`'s accessor. When an accessor is invoked and throws an exception `cause`:

```text
candidate (already an instance of R)
        │
        ▼
attempt to match R(componentPattern...)
        │
        ▼
invoke record accessor to get component
        │
        ├── returns value ──► continue matching subpatterns
        │
        └── throws exception E
                  │
                  ▼
          MatchException
          getCause() == E
                  │
                  ▼
   exit matching abruptly, do not run case/if body
```

**This is not "the pattern did not match"**. A normal pattern mismatch might cause `instanceof` to return `false` or `switch` to try another case. However, an accessor throwing an exception causes matching to **complete abruptly**, so:

- `if (obj instanceof R(...))` does not proceed to the `else` branch like an ordinary `false` case.
- `switch` does not automatically fall through to `default` or the next `case` to "skip" the faulty record.
- The `if` body or `case` body has not executed yet, so a `try/catch` **placed inside** that body cannot catch an exception that occurred while evaluating the pattern.
- To handle it, you must place `try/catch` **around the entire matching construct** (`instanceof` or `switch`) or handle the data before matching.

Java 21 uses `java.lang.MatchException` to represent an unexpected failure during pattern matching; for failures originating from an accessor, the original exception is attached as the **cause**. It does not replace every kind of exception that can occur in other parts of a program.

## 4. Minimal example: same object, three different outcomes

Suppose the `Label` record has the accessor from section 2:

```java
Label bad = new Label(null);
Object candidate = bad;
```

### 4.1. Calling the accessor directly

```java
bad.value();
```

The direct call executes the body of `value()` and throws **`IllegalStateException`** with the message `missing label`. There is no record pattern, so there is no rule wrapping it into `MatchException`.

### 4.2. Checking only the type with a type pattern

```java
if (candidate instanceof Label label) {
    System.out.println("matched type");
}
```

The pattern `Label label` only checks the object's type and binds the reference `label`; it **does not need to call `label.value()`**. Therefore, even though the internal component is `null`, this branch still runs and prints `matched type`. If the branch body later explicitly calls `label.value()`, the error from that **direct** call is still `IllegalStateException`.

### 4.3. Deconstructing with a record pattern

```java
try {
    if (candidate instanceof Label(var labelText)) {
        System.out.println(labelText);
    }
} catch (MatchException ex) {
    System.out.println(ex.getCause().getClass().getSimpleName());
}
```

Output:

```text
IllegalStateException
```

When matching `Label(var labelText)`, Java needs to call `value()`. The accessor throws `IllegalStateException`; pattern matching throws `MatchException` whose cause is the original exception. The `if` body does not run.

This is why you must not treat `candidate instanceof Label label` and `candidate instanceof Label(var labelText)` as identical in terms of **execution side effects**. Both patterns involve the same record, but the second accesses the component through the accessor.

## 5. Complete Java 21 example: nested failures, null, and guards

Save the following program as **`RecordAccessorExceptionDemo.java`**. The program demonstrates:

1. A record pattern retrieving a value through a custom accessor.
2. A type pattern not needing to access the component.
3. A nested record pattern that can produce `MatchException`.
4. `var` in a pattern receiving a `null` component when the accessor returns normally.
5. An exception in `when` differing from an exception thrown by an accessor.
6. Calling an accessor directly not being automatically wrapped.

```java
import java.util.function.Supplier;

public class RecordAccessorExceptionDemo {
    record Label(String value) {
        public String value() {
            if (value == null) {
                throw new IllegalStateException("missing label");
            }
            return value.strip();
        }
    }

    record Parcel(String parcelId, Label label) {}
    record Plain(String value) {}

    static String recordPattern(Object candidate) {
        if (candidate instanceof Label(var labelText)) {
            return "label:" + labelText;
        }
        return "not Label";
    }

    static String typePattern(Object candidate) {
        if (candidate instanceof Label label) {
            return "type:" + label.getClass().getSimpleName();
        }
        return "not Label";
    }

    static String nestedPattern(Object candidate) {
        if (candidate instanceof Parcel(
                var parcelId, Label(var labelText))) {
            return parcelId + ":" + labelText;
        }
        return "no nested match";
    }

    static String shallowPattern(Object candidate) {
        if (candidate instanceof Parcel(var parcelId, var label)) {
            return parcelId + ":label="
                    + (label == null ? "null" : "present");
        }
        return "not Parcel";
    }

    static String switchRecord(Object candidate) {
        return switch (candidate) {
            case null -> "selector:null";
            case Label(var labelText) -> "switch:" + labelText;
            default -> "other";
        };
    }

    static boolean rejectFromGuard(String labelText) {
        throw new IllegalArgumentException("guard rejected");
    }

    static String guardThrows(Object candidate) {
        return switch (candidate) {
            case Label(var labelText)
                    when rejectFromGuard(labelText) -> "blocked";
            case Label(var labelText) -> "allowed:" + labelText;
            default -> "other";
        };
    }

    static String plainPattern(Object candidate) {
        if (candidate instanceof Plain(var text)) {
            return text == null ? "plain:null" : "plain:" + text;
        }
        return "not Plain";
    }

    static void probe(String name, Supplier<String> operation) {
        try {
            System.out.println(name + "=" + operation.get());
        } catch (MatchException ex) {
            Throwable cause = ex.getCause();
            System.out.println(name + "=MatchException cause="
                    + cause.getClass().getSimpleName()
                    + ":" + cause.getMessage());
        } catch (IllegalArgumentException ex) {
            System.out.println(name + "=IllegalArgumentException:"
                    + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        Label good = new Label("  OK  ");
        Label bad = new Label(null);
        Parcel badParcel = new Parcel("P-7", bad);
        Parcel nullParcel = new Parcel("P-8", null);

        probe("record-good", () -> recordPattern(good));
        probe("type-bad", () -> typePattern(bad));
        probe("record-bad", () -> recordPattern(bad));
        probe("nested-bad", () -> nestedPattern(badParcel));
        probe("shallow-bad", () -> shallowPattern(badParcel));
        probe("nested-null", () -> nestedPattern(nullParcel));
        probe("shallow-null", () -> shallowPattern(nullParcel));
        probe("switch-bad", () -> switchRecord(bad));
        probe("switch-null", () -> switchRecord(null));
        probe("plain-null", () -> plainPattern(new Plain(null)));
        probe("guard-ex", () -> guardThrows(good));

        try {
            bad.value();
        } catch (IllegalStateException ex) {
            System.out.println("direct=IllegalStateException:"
                    + ex.getMessage());
        }
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 RecordAccessorExceptionDemo.java
java RecordAccessorExceptionDemo
```

**Exact output:**

```text
record-good=label:OK
type-bad=type:Label
record-bad=MatchException cause=IllegalStateException:missing label
nested-bad=MatchException cause=IllegalStateException:missing label
shallow-bad=P-7:label=present
nested-null=no nested match
shallow-null=P-8:label=null
switch-bad=MatchException cause=IllegalStateException:missing label
switch-null=selector:null
plain-null=plain:null
guard-ex=IllegalArgumentException:guard rejected
direct=IllegalStateException:missing label
```

These are verified values from running the Java 21 program. They illustrate the language behavior; the order of calls printed in `main` is the order in which the `probe(...)` statements are written, not a guarantee about the internal invocation order of accessors in all complex record patterns.

## 6. Analyzing the cases in the program

### 6.1. A record pattern can receive data transformed by the accessor

`record-good=label:OK`: the object `Label("  OK  ")` is deconstructed and calls the `value()` accessor; the result is the string after `strip()`. The pattern variable `labelText` receives the value **returned** by the accessor—there is no "shortcut" access to the record's private field.

This is also a design signal to consider: an accessor returning a result different from the value stored in the component can surprise users of the record and affect assumptions about the record's data invariants. If string normalization is needed, consider doing it at record construction time so the accessor keeps a stable retrieval role.

### 6.2. Type patterns are not the same as record patterns

`type-bad=type:Label`: `bad` has type `Label`, so the type pattern matches. Calling `label.getClass().getSimpleName()` does not require calling `value()`, so no error occurs.

`record-bad=MatchException cause=IllegalStateException:missing label`: the record pattern must call `value()` and encounters an error. The `if` does not return `false` and proceed to `return "not Label"`; the `recordPattern` method is aborted by the exception.

### 6.3. Accessor failure at a nested level of a pattern

`nested-bad` receives `Parcel("P-7", Label(null))`. The pattern:

```java
Parcel(var parcelId, Label(var labelText))
```

must first obtain `Parcel.label()` to evaluate the `Label(...)` pattern. When the nested `Label` object exists but `Label.value()` throws an error, the entire nested matching process terminates with `MatchException`.

Meanwhile, `shallow-bad=P-7:label=present` because:

```java
Parcel(var parcelId, var label)
```

only retrieves the components of `Parcel`. This pattern binds `label` to the `Label` reference **without calling `Label.value()`**. However, if `Parcel.label()` itself were written to throw an exception, that shallow pattern could also hit `MatchException`. Using a shallow pattern alone does not provide a general guarantee that all accessors are safe.

### 6.4. A null component is not necessarily an exception

`nested-null=no nested match`: `Parcel("P-8", null)` has a `null` `label` component. The nested record pattern `Label(...)` **does not match `null`**, so `instanceof` completes normally with `false`; there is no `Label` accessor to call.

`shallow-null=P-8:label=null`: with `var label` as a record component pattern, `null` can be bound to a reference variable. The shallow pattern still matches and treats `label == null` as an ordinary value.

`plain-null=plain:null`: `Plain` only has a compiler-generated accessor that returns `null`; the pattern `Plain(var text)` still matches and the variable `text` receives `null`. This is not an error just because the component holds `null`.

### 6.5. Switch does not swallow accessor exceptions

`switch-bad` shows that `case Label(var labelText)` also causes `MatchException` when the accessor fails. `default -> "other"` is **not** used as a catch block. Conversely, `switch-null=selector:null` runs `case null` because the **selector** is `null`; at that point, no record accessor is called.

### 6.6. Exceptions from `when` differ from accessor exceptions

`guard-ex=IllegalArgumentException:guard rejected` occurs during `guardThrows(good)`:

1. The pattern `Label(var labelText)` matches; the accessor returns the string normally.
2. The condition `when rejectFromGuard(labelText)` is evaluated.
3. `rejectFromGuard` itself throws `IllegalArgumentException`.

This is an error **in the guard**, not an error from the record pattern's accessor invocation, so the exception propagates directly under normal expression evaluation rules; it is not turned into `MatchException`. The subsequent `case Label(...)` branch also has no chance to "recover" from the error as a fallback because guard evaluation completed abruptly.

### 6.7. Direct accessor calls are not wrapped

`direct=IllegalStateException:missing label`: `bad.value()` is called directly, so `IllegalStateException` is thrown as written in the accessor. `MatchException` only appears because **pattern matching** encountered an error while implicitly invoking the accessor.

## 7. Exact comparison of easily confused cases

| Situation | What happens | Result / how it is handled |
| --- | --- | --- |
| `obj instanceof Label label`, component value would fail, but accessor not called | Type check and reference binding | Matches normally if the object has the right type and is non-`null` |
| `obj instanceof Label(var text)`, accessor returns a valid value | Accessor is called to get the component | Matches; `text` is the value returned by the accessor |
| `obj instanceof Label(var text)`, accessor throws an unchecked exception | Matching is aborted | `MatchException`, `getCause()` is the original exception |
| `Parcel(var id, Label(var text))`, `label == null` | Nested record does not match | `instanceof` is `false`, not `MatchException` |
| `Parcel(var id, var label)`, `label == null` | `var` pattern accepts a `null` reference component | Can match normally |
| `Plain(var text)`, `text == null` | Default accessor returns `null` | Can match normally |
| `switch (obj)` with `case R(...)` and failing accessor | Case matching is aborted | `MatchException`, does not fall through to `default` |
| `switch (null)` with `case null` | Selector is `null` | Runs `case null`, no accessor called |
| `switch (null)` without a matching `case null` | Null selector | Typically throws `NullPointerException`, not an accessor error |
| `when condition(...)` throws | Error evaluating the guard | Exception from the guard propagates directly |
| `recordAccessor()` called directly | Error in an ordinary method call | Throws the original exception, not wrapped in `MatchException` |
| `getCandidate()` throws before entering the pattern | Error in the input expression | Throws `getCandidate()`'s exception, not a pattern accessor error |

This table separates **match/no-match** from **abrupt completion**, and separates the **origin of the exception** from merely "having a pattern nearby".

## 8. Placing `try/catch` in the right spot

### Wrong idea: placing catch inside a branch that may never be entered

You cannot rely on a `case` body to handle an error from an accessor used **before** Java determines which case matches:

```java
// Illustrates a catch placement that does not handle matching errors.
switch (candidate) {
    case Label(var labelText) -> {
        try {
            System.out.println(labelText);
        } catch (MatchException ex) {
            System.out.println("accessor failed");
        }
    }
    default -> System.out.println("other");
}
```

The error in `Label.value()` occurs **before entering the case body**, so the `catch` inside the case cannot catch it.

### Right spot: wrapping the entire matching construct

```java
try {
    switch (candidate) {
        case Label(var labelText) ->
                System.out.println("label:" + labelText);
        default ->
                System.out.println("other");
    }
} catch (MatchException ex) {
    Throwable cause = ex.getCause();
    System.out.println("record-pattern failed: " + cause);
}
```

The two snippets above are **illustrative**, assuming `candidate` and `Label` are already declared; the second snippet is sufficient to show a valid `try/catch` placement.

Similarly with `instanceof`:

```java
try {
    if (candidate instanceof Label(var labelText)) {
        System.out.println(labelText);
    }
} catch (MatchException ex) {
    // Handle record pattern match failure; can log/inspect cause.
}
```

**Do not catch and ignore every `MatchException`**. It indicates that pattern matching failed abnormally, which is different from the caller passing a different type. Recovery should follow the business contract, preserve the root cause, and avoid misleading the system into thinking the data was processed successfully.

## 9. Designing records so errors don't arise unexpectedly during matching

The best approach is not to scatter `catch (MatchException)` everywhere, but to **avoid accessors with unstable logic**.

### 9.1. Validate in the compact constructor

```java
import java.util.Objects;

record SafeLabel(String value) {
    SafeLabel {
        value = Objects.requireNonNull(value, "value").strip();
        if (value.isBlank()) {
            throw new IllegalArgumentException("blank label");
        }
    }
}
```

This is a standalone illustrative Java snippet (it needs to be placed in a valid file/class to compile). When creating `new SafeLabel(null)`, the error occurs **right in the constructor**, before a valid object even exists to be matched; it does **not** become `MatchException` because no pattern matching has happened yet. Once constructed successfully, the compiler-generated `value()` accessor simply returns the normalized field.

**Note:** constructors can throw exceptions normally; the exception type, timing, and API contract will differ from an error raised inside an accessor during matching. Do not change this design in a running system without testing behavioral compatibility.

### 9.2. Keep accessors simple and predictable

Prefer accessors that only return the existing component without performing I/O, network/DB queries, unpredictable lazy state initialization, or throwing environment-dependent errors. Records are used with pattern matching as data models; accessors with side effects can easily cause an operation that looks like "just a type check" to mutate state.

Do not rely on the number of times or the order in which accessors are called during complex matching as an application contract. Observing a few specific runs **does not prove** that the compiler/JVM will always call them exactly once in the order business code expects. If you need a single retrieval in a controlled order, write explicit code to fetch the data and then process it.

### 9.3. If retrieval can fail, give it a dedicated named operation

Instead of stuffing service-fetching logic into an accessor:

```java
// Design illustration: a domain method whose name reflects potential failure.
record CustomerRef(String id) {}

static String loadCustomerName(CustomerRef ref) {
    // This is where the application implements retrieval that may fail.
    return ref.id();
}
```

This is not a real service implementation; it illustrates separating a fallible operation from a record accessor. The caller explicitly invokes `loadCustomerName(...)` and decides where to catch exceptions at the appropriate layer of responsibility.

### 9.4. Use a type pattern if deconstruction isn't needed yet

If you only need to know whether the input is a `Label` to decide the next step, `instanceof Label label` can be clearer and avoids calling the `value()` accessor at that moment. However, if subsequent processing needs the data, calling the accessor directly can still fail. **A type pattern does not "sanitize" a record that has an abnormal accessor.**

## 10. Regression testing and observability

When a record has a custom accessor or handles untrusted data, tests should distinguish:

1. **Valid record:** accessor returns the expected value; the record pattern binds the component correctly.
2. **Accessor throws:** assert `MatchException` and that **`getCause()` has the expected exception type/message**.
3. **Same object under a type pattern:** when only checking the type, no component access occurs; verify no exception is thrown from the accessor.
4. **Nested record:** outer record is non-`null`, inner record has a failing accessor; verify the inner-level failure is still wrapped in `MatchException`.
5. **`null` inner record:** verify the nested record pattern fails to match normally; a `var` pattern can bind `null`.
6. **`null` selector:** for `switch`, the `case null` or NPE policy must be clear; do not conflate null-selector errors with accessor errors.
7. **Guard/branch body throws:** verify it propagates according to its actual source, rather than assuming every exception in a switch is `MatchException`.
8. **Side effects:** if a custom accessor exists, test state, logs, and invocation counts, though it is better to refactor side effects out of accessors to avoid depending on implementation details.
9. **Constructor contract:** test `null`/blank/invalid inputs at record creation time rather than only discovering them during pattern matching.
10. **Java version:** run on JDK 21+ because `RecordPattern(...)` and `MatchException` in this context are Java 21 features.

JUnit 5 example (illustrative snippet; requires JUnit on the classpath and the corresponding `Label` record):

```java
// import static org.junit.jupiter.api.Assertions.*;
// @org.junit.jupiter.api.Test
void accessorFailureIsWrapped() {
    Object candidate = new Label(null);

    MatchException ex = assertThrows(MatchException.class, () -> {
        boolean matched = candidate instanceof Label(var text);
        System.out.println(matched);
    });

    assertInstanceOf(IllegalStateException.class, ex.getCause());
    assertEquals("missing label", ex.getCause().getMessage());
}
```

If you put this into a real test class, uncomment the imports/annotation and ensure `Label` is in scope. This is **not a standalone program** like `RecordAccessorExceptionDemo.java` in section 5.

## 11. Common misconceptions

### "`instanceof` only returns true or false; it cannot throw"

With a pure **type pattern**, a type check normally just returns whether it matches or not. But a **record pattern** must retrieve components via accessors; an accessor can throw an exception, causing matching to throw `MatchException`.

### "Records have `final` fields, so accessors definitely cannot fail"

Record component fields are `private final`, but a record can declare an explicit accessor with arbitrary valid code. `final` does not turn an accessor into a pure field read and does not forbid unchecked exceptions.

### "If a record pattern fails, `default` will handle it"

No. `default` handles the case where **no case applies after normal matching**, not a `catch` mechanism. An error in an accessor causes matching to complete abruptly, requiring `try/catch` if you want to handle it.

### "`null` always produces MatchException"

No. A `null` selector in `switch` has its own rules; a `null` nested record causes a nested record pattern not to match; `var` in a record pattern can bind a `null` component. The `MatchException` wrapping rule for accessor errors applies only when **an accessor is invoked and throws an exception**.

### "You only need to catch `IllegalStateException` to handle accessor failures"

If `IllegalStateException` is thrown **because an accessor was called inside a record pattern**, the exception thrown outward is `MatchException`, while `IllegalStateException` is in the cause. If the accessor is called directly, `IllegalStateException` itself propagates. Catch according to the actual execution path.

### "Errors in `when` are also always wrapped"

No. `when` is evaluated **after the pattern matches**, and an error from evaluating the guard is not an accessor error from pattern matching. In the runnable example, `IllegalArgumentException` from the guard is caught directly.

### "You can add `throws IOException` to a record accessor"

No. Java forbids a `throws` clause on record accessors, regardless of which exception type is listed in `throws`. If checked error handling is needed, you must change the design or handle it inside the method according to an appropriate contract.

### "This error is the same as every other `MatchException`"

`MatchException` can also represent unexpected runtime matching failures in certain constructs proven exhaustive at compile time (for example, differences between a type hierarchy at compile time vs. runtime). **When the cause is an accessor**, `getCause()` points to the original exception; you should not assume every `MatchException` comes from a specific accessor without checking its cause and context.

## 12. Practical diagnostic workflow

When you encounter `MatchException` around a record pattern:

1. Identify where matching happens: `instanceof RecordName(...)`, `case RecordName(...)`, or a nested pattern.
2. Check **which record** is being deconstructed and which component accessors may be invoked.
3. Inspect `ex.getCause()`, its message, and stack trace to find where the original error was thrown; do not just look at `default`.
4. Check whether the accessor is compiler-generated or hand-written. If hand-written, inspect exception conditions, I/O, and side effects.
5. Check `null`/invalid data: does it cause the pattern to simply not match, get accepted by `var`, or cause the accessor to actively throw?
6. Determine whether an exception comes from the **selector expression**, `when`, or the case body; they are not necessarily wrapped under the same rule.
7. If you must catch the error, place `try/catch` around the **pattern evaluation**, and preserve the cause when logging or reporting.
8. Prefer fixing the root cause: validate data in the constructor, keep accessors simple, and extract fallible operations into explicit methods.
9. Write regression tests for both normal and abnormal paths; use the right Java version to avoid semantics confusion.

## 13. Self-check exercises

**Exercise 1 — Type vs record pattern.** Given `Label bad = new Label(null)` with the accessor from section 2, how do `bad instanceof Label label` and `bad instanceof Label(var text)` differ?

**Answer:** the first type pattern checks the type and can match without calling `value()`; the second record pattern needs to call `value()`, so it throws `MatchException` with cause `IllegalStateException`.

**Exercise 2 — Fallback.** Why does `default -> "unknown"` not handle the case when the accessor in `case Label(var value)` throws an error?

**Answer:** matching completes abruptly, so there is no normal selection of subsequent cases. To handle it, wrap the switch in `try/catch` rather than relying on `default`.

**Exercise 3 — Null nested record.** Given `Parcel("P-1", null)`, does `Parcel(var id, Label(var text))` throw `MatchException` because of null?

**Answer:** no. `Label(...)` does not match a `null` nested record; the nested pattern simply does not match. `Parcel(var id, var label)` can match with `label == null`.

**Exercise 4 — Guard.** If `case Label(var text) when check(text)` matches the pattern and then `check(text)` throws `IllegalArgumentException`, is it wrapped in `MatchException`?

**Answer:** not under the accessor rule; an exception thrown while evaluating a guard propagates directly.

**Exercise 5 — Catch placement.** Does catching `MatchException` inside a case's block protect against an error from an accessor used to decide that very case?

**Answer:** no. The accessor can fail before entering the block. Place `try/catch` around the entire `switch` or `instanceof`.

**Exercise 6 — Accessor checked exception.** Why is `public String code() throws IOException` invalid in a record `record R(String code)`?

**Answer:** JLS `8.10.3` forbids record accessors from having a `throws` clause. This is a compile-time error; you must redesign error handling rather than adding a checked exception to the accessor signature.

**Exercise 7 — Long-term design.** For `record SafeLabel(String value)`, if you want to forbid `null` values, should you validate in the accessor or the compact constructor?

**Answer:** usually validate in the constructor to reject invalid data upon record creation, keeping the accessor stable. This is an API contract decision; if migrating from late to early validation in existing code, test the change in exception timing.

**Exercise 8 — Cause.** When catching `MatchException ex` from an accessor failure, what is `ex.getCause()` used for?

**Answer:** it reveals the original exception that caused the accessor to complete abruptly, aiding diagnosis. You must not infer that every `MatchException` has the same cause without checking.

## 14. Key takeaways

- A record pattern **invokes the record's accessors** to obtain the components to match.
- An explicit accessor can have custom logic and throw **unchecked exceptions**, even though a record accessor signature **cannot contain `throws`**.
- If an accessor throws an error during pattern matching, Java 21 throws **`MatchException`** and sets the original error as **`cause`**.
- This error is **not** a pattern mismatch; `else`, `default`, or subsequent cases will not automatically catch it.
- Distinguish **null selector**, **null nested record**, **null component**, **accessor** error, **guard** error, and **case body** error; each has different semantics.
- Catch around the entire matching expression/statement if handling is needed; do not put a catch only inside a case body that will never be entered.
- Design safe records by **validating at construction time** and keeping accessors **simple and side-effect-free** whenever possible.
- Use examples, tests, and `getCause()` to confirm the true origin of a failure instead of treating every exception near a record pattern as the same kind.

**Official documentation:**
- [Java Language Specification 21 — Pattern Matching (`14.30.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2)
- [Java Language Specification 21 — Record Members (`8.10.3)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.3)
- [Java SE 21 API — MatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
