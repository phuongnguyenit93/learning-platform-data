# Null Check Before Pattern: Debugging Java Pattern Matching (Java 21)

When debugging **`NullPointerException` (NPE)** in code that uses pattern matching, the first question is not "is there already an `instanceof`?" but rather: **at which level is `null` located, which check runs first, and is any access performed on a potentially `null` value?** Common confusing scenarios include: a `switch` selector being `null`; the outer record object being `null`; an inner nested record being `null`; a reference component of a non-`null` record holding a `null` value; and a `when` guard calling a method on an extracted value without checking it first.

This article focuses on **checking `null` before the pattern** to identify the root cause of errors, choose a safe guard order, and preserve the business contract.

**Environment:** Complete examples use **JDK 21 or later**. `instanceof` type patterns have been stable since Java 16 (JEP 394), while record patterns and pattern matching for `switch` have been stable since Java 21 (JEP 440, JEP 441). `--enable-preview` is not required.

## 1. Table Distinguishing Four Null Positions

Suppose:

```java
record Text(String value) {}
record Packet(Text nested, Object payload) {}
```

| Value under test | Pattern/expression | Result or behavior |
| --- | --- | --- |
| `null` | `input instanceof Text t` | `false`; `t` is not bound |
| `null` | `input instanceof Text(var value)` | `false`; outer record does not match |
| `new Text(null)` | `input instanceof Text(var value)` | `true`; `value == null` |
| `new Text(null)` | `input instanceof Text(String value)` | `true`; `value == null` |
| `new Packet(null, "data")` | `input instanceof Packet(Text(var x), var p)` | `false`; nested record `Text` is `null` |
| `new Packet(null, "data")` | `input instanceof Packet(var nested, var p)` | `true`; `nested == null` |
| Selector `null` | `switch (input)` without `case null` | Throws `NullPointerException` |
| Selector `null` | `switch (input)` with `case null` | The `case null` branch handles it per code |

**Key takeaway:** A pattern at the **top level** of `instanceof` does not match a `null` selector. However, a **component pattern** inside a record pattern follows its own rule: `var` or an unconditional type pattern for the component's declared type can bind a `null` value. `Text(String value)` matches `new Text(null)` because the component is declared with type `String` and `String value` is an unconditional pattern for that type.

Conversely, if we have `record Box(Object value) {}`, then `Box(String s)` does not match `new Box(null)`: `String s` is not an unconditional pattern for a component whose declared type is `Object`. When debugging, **always inspect the declared type of the component**, not just the type written in the pattern.

The snippets in the earlier sections use the corresponding record definitions; the standalone program in Section 9 declares everything in full.

## 2. instanceof: Type Checking Already Covers a Null Selector

Old style:

```java
Object input = getInput(); // getInput() is assumed to exist.

if (input != null && input instanceof String) {
    String text = (String) input;
    System.out.println(text.length());
}
```

This can be written concisely with a type pattern:

```java
if (input instanceof String text) {
    System.out.println(text.length());
}
```

If `input == null`, the expression `input instanceof String text` returns `false`, the branch does not execute, and `text` is not bound. No NPE is thrown simply from using the `instanceof` operator on a `null` value.

**When is a separate `null` check still needed?**

- When the system must distinguish `null` (missing data) from an unexpected type.
- When you want to throw an exception or return a specific message for `null`.
- When you need to record separate logs/metrics for missing input.
- When downstream logic uses a selector in a `switch` where `null` must be handled explicitly.

Example preserving three distinct branches:

```java
static String explain(Object input) {
    if (input == null) {
        return "missing input";
    }
    if (input instanceof String text) {
        return "text=" + text;
    }
    return "unexpected type";
}
```

**Do not call `input.getClass()` for debugging before knowing `input != null`:** the `getClass()` call itself will throw an NPE. To log the type safely:

```java
String kind = input == null ? "null" : input.getClass().getSimpleName();
System.out.println("type=" + kind);
```

When `input` is an expression with side effects, read it into a local variable **once** before logging and checking. Two consecutive calls to `getInput()` do not necessarily return the same object.

## 3. switch Pattern Matching: case null Is Different from default

With `instanceof`, a `null` selector returns `false`. But with a Java 21 **pattern switch**, if the selector is `null` and there is no label handling `null`, the `switch` **throws an NPE** by default. Do not assume that `default` will catch `null`.

Example that can cause an NPE:

```java
static String unsafeSwitch(Object value) {
    return switch (value) {
        case String text -> "text";
        default -> "other";
    };
}
```

`unsafeSwitch(null)` does not return `"other"`; it throws `NullPointerException`.

Option 1 — explicitly handle `null` in the switch:

```java
static String safeSwitch(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text=" + text;
        default -> "other";
    };
}
```

Option 2 — guard the selector before the switch:

```java
static String checkBeforeSwitch(Object value) {
    if (value == null) {
        return "missing";
    }
    return switch (value) {
        case String text -> "text=" + text;
        default -> "other";
    };
}
```

Both are `null`-safe. Which one to choose depends on the architecture: if `null` is a meaningful classification branch, `case null` keeps the handling centralized; if `null` is invalid input, it is often better to reject it before the `switch` or use `Objects.requireNonNull(value, "value")` with a clear message.

**Note:** `case null` handles the **selector value** of the switch itself; it does **not** automatically catch `null` components inside a record selector.

## 4. Record Pattern: Null Outer Object vs. Null Component

Consider:

```java
record Text(String value) {}
Object a = null;
Object b = new Text(null);
```

Two different checks:

```java
System.out.println(a instanceof Text(var value)); // false
System.out.println(b instanceof Text(var value)); // true
```

For `b`, the `Text` record exists so the record pattern matches, and `var value` receives `null`. **A pattern match does not mean the extracted reference variable is non-`null`.**

Example at risk of NPE:

```java
if (b instanceof Text(var text)) {
    System.out.println(text.strip()); // NPE when text == null.
}
```

Fix by checking the **`text` component** itself before dereferencing:

```java
if (b instanceof Text(var text) && text != null) {
    System.out.println(text.strip());
}
```

Or when full classification is needed:

```java
if (b instanceof Text(var text)) {
    if (text == null) {
        System.out.println("value is missing");
    } else if (text.isBlank()) {
        System.out.println("value is blank");
    } else {
        System.out.println(text.strip());
    }
}
```

This check does not redundantly duplicate the record pattern's work: the pattern checks the **structure**, whereas `text != null` checks the **component value**.

### Distinguishing String Type Patterns in Two Positions

```java
Object direct = null;
Object wrapped = new Text(null);

System.out.println(direct instanceof String s);          // false
System.out.println(wrapped instanceof Text(String text)); // true
```

The **top-level** position of `String s` and the **component** position of `String text` follow different `null`-matching rules. The component has declared type `String`, and the pattern `String text` is unconditional for that type.

This is a common reason code still enters a `case Text(String text)` and then throws an NPE at `text.length()`. When debugging, pinpoint where the dereference occurs instead of concluding that "the pattern is broken."

## 5. Nested Record Patterns: A Null Child Record Prevents Matching

Example:

```java
record Packet(Text nested, Object payload) {}
```

An outer record may exist while its child record component is `null`:

```java
Object input = new Packet(null, "data");

if (input instanceof Packet(Text(var inner), var payload)) {
    System.out.println(inner); // Does not run: nested == null.
}
```

Why doesn't it run? `Packet(...)` at the outer level matches, but the nested record pattern `Text(var inner)` requires the `nested` component to be a non-`null` `Text` object.

If you want to handle a missing child record, **do not destructure further with a nested record pattern right away**; extract the component as a whole first:

```java
if (input instanceof Packet(var nested, var payload)) {
    if (nested == null) {
        System.out.println("missing nested Text");
    } else {
        System.out.println("nested Text is present");
    }
}
```

Another case: `new Packet(new Text(null), "data")` has a non-`null` `nested` record, so `Packet(Text(var inner), var payload)` **matches**; however, `inner == null`. These are two different levels of null:

| Input | Nested record pattern `Packet(Text(var inner), var p)` | Conclusion |
| --- | --- | --- |
| `new Packet(null, "data")` | Does not match | Missing child record `Text` |
| `new Packet(new Text(null), "data")` | Matches | `Text` record exists, `inner == null` |
| `new Packet(new Text("OK"), null)` | Matches | Valid child record; `payload == null` can still be bound via `var p` |

**Debugging technique:** go from the outside in, noting at each level: whether the object exists, whether the runtime type is right, which components can be null, and which guards actually run.

## 6. Ordering case null and when Guards to Avoid NPE

We can distinguish a null selector, a null component, a blank string, and a non-blank string using a pattern switch:

```java
static String classifyText(Object input) {
    return switch (input) {
        case null -> "NULL_SELECTOR";
        case Text(String text) when text == null -> "NULL_TEXT_COMPONENT";
        case Text(String text) when text.isBlank() -> "BLANK_TEXT";
        case Text(var text) -> "TEXT=" + text;
        default -> "OTHER";
    };
}
```

The order matters:

1. `case null` catches a null selector; no accessor is invoked.
2. `case Text(String text) when text == null` catches an existing `Text` record with a null component.
3. `case Text(String text) when text.isBlank()` only calls `isBlank()` after the preceding null-component branch has handled the null case.
4. `case Text(var text)` catches all remaining `Text` instances; the broader branch must come **after** the specialized branches.
5. `default` handles other input types.

**Do not swap the first two guards** if the first guard calls a method on a potentially null value:

```java
// This snippet CAN THROW NPE with new Text(null):
// case Text(String text) when text.isBlank() -> "BLANK_TEXT";
// case Text(String text) when text == null -> "NULL_TEXT_COMPONENT";
```

The compiler checks whether the pattern binds variables validly; it does **not** prove by default that `text` is non-null just because the pattern matched the component. Any method call on `text` still carries the same NPE risk as an ordinary reference variable.

For multiple `case` labels with the same record pattern, always place **specialized guards before a broad unguarded case**. If the broad case comes first, the compiler may report a *dominated case* error. If a specialized guard comes first but performs an unsafe dereference, the compiler will allow compilation and the error will only surface at runtime.

## 7. Guards in if: && Helps Check Null in the Right Order

Safe pattern with short-circuiting:

```java
static String safeNonBlank(Object input) {
    if (input instanceof Text(var text)
            && text != null
            && !text.isBlank()) {
        return "NON_BLANK=" + text.strip();
    }
    return "OTHER_OR_BLANK";
}
```

Values are evaluated in order:

- `input == null`: `instanceof` is false; both `text != null` and `isBlank()` are skipped.
- `input` has the wrong type: also stops before evaluating the remaining clauses.
- `input == new Text(null)`: the record pattern matches, but `text != null` is false; `isBlank()` **does not run**, so it is safe.
- `input == new Text("  hello  ")`: all three conditions are true; returns `NON_BLANK=hello`.

Do not reverse the order to `!text.isBlank() && text != null`, because `isBlank()` would be called before the null check.

### Negation and Early Return

You can write out each step explicitly while debugging:

```java
static String process(Object input) {
    if (!(input instanceof Text box)) {
        return "not a Text";
    }
    String text = box.value();
    if (text == null) {
        return "missing value";
    }
    return text.strip();
}
```

After a negated guard with `return`, `box` is guaranteed to have matched and be usable. However, `box.value()` can still be null, so the subsequent check remains necessary.

Avoid confusing **flow scoping** with **null safety**: the fact that the compiler proves a pattern variable is in scope and bound does not mean all reference components are non-null.

## 8. Step-by-Step Debugging Workflow for NullPointerException

When encountering an NPE near a pattern, check in the following order.

1. **Pinpoint the exact line throwing the NPE.** Read the stack trace and locate the first stack frame in application code. The NPE may occur at `switch (selector)`, in a `when` guard, or at a call such as `text.strip()` inside a case body; each has a different cause.
2. **Capture the input expression once.** If the selector is `getInput()`, consider `Object snapshot = getInput();` so that logging and classification inspect the same value. Avoid calling a getter again if it may mutate state.
3. **Check the selector first.** Note `snapshot == null`. If the `switch` has no `case null`, this may be the direct cause.
4. **Check the outer type.** With `instanceof`, a null/wrong-type selector simply makes the condition false; with `switch`, check which case handles the selector's type.
5. **Check each record component.** Distinguish a null child record from a null field inside the child record; check reference values before calling methods on them.
6. **Trace guard evaluation order.** See which guard could receive a null variable from an unconditional pattern, or use a variable when `&&`/`||` evaluation does not yet guarantee non-nullity.
7. **Create a minimal reproduction test.** Test a null selector, null outer record, null component, null nested record, blank value, and valid value. Each case should have an independent expected result.
8. **Choose the fix policy.** Return a missing-data branch, reject with an exception carrying a clear message, or apply a default value? Follow the business contract rather than merely "silencing" the NPE.
9. **Run regression tests.** After fixing, verify that valid data still hits the right case, null does not fall into the wrong branch, and no dominated case or missing exhaustiveness errors appear.

### Controlled Logging

Example for logging the selector type:

```java
Object snapshot = obtainInput(); // Illustration; obtainInput() needs to be defined.
String typeName = snapshot == null
        ? "<null>"
        : snapshot.getClass().getSimpleName();
System.out.println("selectorType=" + typeName);
```

This is only an **illustrative snippet**, not a standalone program. In real applications, avoid logging personal data or full sensitive payloads. Log only the case code/type needed for diagnosis, along with an appropriate correlation id.

**Do not use `catch (NullPointerException e)` as a default null-handling strategy** when you know which field needs checking: catching NPE broadly can mask other programming bugs. In business code, prefer explicit null guards and tests to preserve exact semantics.

## 9. Verified Complete Java 21 Program

Save the exact contents as **`NullPatternDebugDemo.java`**:

```java
public class NullPatternDebugDemo {
    sealed interface Input permits Text, Count, Packet {}
    record Text(String value) implements Input {}
    record Count(int value) implements Input {}
    record Packet(Text nested, Object payload) implements Input {}
    record Check(String name, Input input, String expected) {}

    static String classify(Input input) {
        return switch (input) {
            case null -> "NULL_SELECTOR";
            case Text(String value) when value == null -> "NULL_TEXT_COMPONENT";
            case Text(String value) when value.isBlank() -> "BLANK_TEXT";
            case Text(var value) -> "TEXT=" + value;
            case Count(int n) when n == 0 -> "ZERO";
            case Count(int n) -> "COUNT=" + n;
            case Packet(Text(String inner), var payload) when inner == null ->
                    "NULL_NESTED_COMPONENT";
            case Packet(Text(var inner), var payload) -> "NESTED_TEXT=" + inner;
            case Packet(var nested, var payload) -> "NULL_NESTED_RECORD";
        };
    }

    static String classifyUsingIf(Input input) {
        if (input == null) return "NULL_SELECTOR";
        if (input instanceof Text(var value)) {
            if (value == null) return "NULL_TEXT_COMPONENT";
            if (value.isBlank()) return "BLANK_TEXT";
            return "TEXT=" + value;
        }
        if (input instanceof Count(int n)) {
            if (n == 0) return "ZERO";
            return "COUNT=" + n;
        }
        if (input instanceof Packet(Text(var inner), var payload)) {
            if (inner == null) return "NULL_NESTED_COMPONENT";
            return "NESTED_TEXT=" + inner;
        }
        if (input instanceof Packet(var nested, var payload)) {
            return "NULL_NESTED_RECORD";
        }
        throw new IllegalStateException("Unexpected subtype");
    }

    static String withoutNullCase(Input input) {
        return switch (input) {
            case Text(var value) -> "text";
            case Count(var n) -> "count";
            case Packet(var nested, var payload) -> "packet";
        };
    }

    static String unsafeComponentRead(Object value) {
        if (value instanceof Text(var text)) {
            return text.strip();
        }
        return "OTHER";
    }

    static String safeNonBlank(Object value) {
        if (value instanceof Text(var text)
                && text != null
                && !text.isBlank()) {
            return "NON_BLANK=" + text.strip();
        }
        return "OTHER_OR_BLANK";
    }

    static void assertEquals(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + ": expected " + expected + ", got " + actual);
        }
    }

    public static void main(String[] args) {
        Check[] tests = {
            new Check("selector-null", null, "NULL_SELECTOR"),
            new Check("text-component-null", new Text(null), "NULL_TEXT_COMPONENT"),
            new Check("text-empty", new Text(""), "BLANK_TEXT"),
            new Check("text-spaces", new Text("  "), "BLANK_TEXT"),
            new Check("text-value", new Text("Java"), "TEXT=Java"),
            new Check("count-zero", new Count(0), "ZERO"),
            new Check("count-negative", new Count(-1), "COUNT=-1"),
            new Check("packet-nested-null", new Packet(null, "data"), "NULL_NESTED_RECORD"),
            new Check("packet-inner-null", new Packet(new Text(null), "data"), "NULL_NESTED_COMPONENT"),
            new Check("packet-normal", new Packet(new Text("OK"), null), "NESTED_TEXT=OK")
        };

        for (Check test : tests) {
            assertEquals(test.name(), test.expected(), classify(test.input()));
            assertEquals("if-" + test.name(), test.expected(), classifyUsingIf(test.input()));
        }
        System.out.println("PASS cases=" + tests.length);
        System.out.println("PASS switch-if-agreement=" + tests.length);
        System.out.println("instanceof-null=" + (null instanceof Text));
        Object box = new Text(null);
        System.out.println("record-pattern-null-component="
                + (box instanceof Text(String value)));
        System.out.println("safe-guard=" + safeNonBlank(box));
        System.out.println("safe-value=" + safeNonBlank(new Text("  hello  ")));

        try {
            withoutNullCase(null);
            throw new AssertionError("Expected NPE for switch null");
        } catch (NullPointerException expected) {
            System.out.println("switch-without-case-null=NPE");
        }
        try {
            unsafeComponentRead(box);
            throw new AssertionError("Expected NPE for null component");
        } catch (NullPointerException expected) {
            System.out.println("unsafe-component-read=NPE");
        }
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 -encoding UTF-8 NullPatternDebugDemo.java
java NullPatternDebugDemo
```

**Exact stdout:**

```text
PASS cases=10
PASS switch-if-agreement=10
instanceof-null=false
record-pattern-null-component=true
safe-guard=OTHER_OR_BLANK
safe-value=NON_BLANK=hello
switch-without-case-null=NPE
unsafe-component-read=NPE
```

The results can be interpreted as follows:

1. **`PASS cases=10`**: the table of 10 inputs (null selector, null component, blank, numbers, and nested null) all match the expected results via `assertEquals`.
2. **`PASS switch-if-agreement=10`**: on the same 10 inputs, both the `switch` and `if` classifications match the oracle for each case, not merely comparing two implementations against each other.
3. **`instanceof-null=false`**: `null` does not match an outer type pattern.
4. **`record-pattern-null-component=true`**: `new Text(null)` still matches `Text(String value)` because the component pattern is unconditional for the declared type.
5. **`safe-guard=OTHER_OR_BLANK`**: `Text(null)` is filtered out at `text != null` without calling `isBlank()`.
6. **`safe-value=NON_BLANK=hello`**: a valid string passes all three `&&` conditions and gets `strip()`ped.
7. **`switch-without-case-null=NPE`**: an exhaustive `switch expression` over the subtypes of `Input` still throws an NPE because `case null` is missing.
8. **`unsafe-component-read=NPE`**: the pattern matched `Text`, but `text.strip()` dereferences a null component.

The program **intentionally catches two NPEs** at the end to demonstrate the difference between a null selector and a null component; this is not a recommendation to catch NPE broadly in production code. The actual run output consists of the exact eight lines shown above.

## 10. Null Guards or Model Invariants?

There are two different design approaches depending on business requirements.

### Allowing Nullable Components

If `new Text(null)` is a valid state (e.g., unfilled data), the model can keep `Text(String value)` and classification logic needs `value == null` branches as in Section 9. Tests must cover both a null selector and a null component.

### Forbidding Null Components in the Constructor

If text data is required to be present, define the record in a *fail-fast* manner:

```java
record RequiredText(String value) {
    RequiredText {
        java.util.Objects.requireNonNull(value, "value");
    }
}
```

Then `new RequiredText(null)` throws an NPE with the message `"value"` right at object creation; downstream logic can rely on the model's invariant. However, if part of the system already allows null as business data, applying `requireNonNull` can change the contract, so review requirements and tests before refactoring.

**Do not automatically mask missing data with an empty string**: `null` (unknown/not yet provided), `""` (empty string), and `"   "` (whitespace-only) may carry different business meanings.

## 11. Common Mistakes When Debugging Null and Patterns

1. **Adding `input != null` to every `instanceof` without checking the intent.** An outer type pattern already does not match null. A separate null guard is only needed when business behavior differs.
2. **Expecting `switch`'s `default` to catch a null selector.** A Java 21 pattern switch throws NPE by default if the selector is null and there is no `case null`.
3. **Assuming `case null` protects every record component.** It only handles the selector of the `switch` itself, not inner fields.
4. **Assuming a matching record pattern implies non-null components.** `Text(String value)` can match `Text(null)`; `value` is still null.
5. **Using a nested record pattern and missing the null child branch.** `Packet(Text(var x), var p)` does not match if `nested == null`. Use `Packet(var nested, var p)` when you need to check it separately.
6. **Writing a guard that calls a method before the null check.** `text.isBlank()` can throw an NPE before a `text == null` guard in a later case is evaluated.
7. **Confusing `&&` with `||`.** `text != null && text.isBlank()` is safe in order, whereas `text != null || text.isBlank()` can call `isBlank()` when `text` is null.
8. **Placing a general case before a specialized case.** An unguarded `case Text(var value)` at the start of the group can shadow subsequent `Text(...) when ...` branches and cause a compile-time dominated case error.
9. **Calling `getClass()`/`toString()` on an unchecked input.** Calling a method on null can trigger an NPE right inside debugging code.
10. **Lumping null outer record, null child record, and null component into one test.** They are separate paths that require separate oracles and failure descriptions.
11. **Catching all NPEs to "fix" the issue.** This can hide other bugs. Prefer pinpointing the exact dereference to guard or enforcing an invariant.
12. **Fixing only to eliminate the exception without testing the happy path.** An overly broad null guard can drop valid branches. Run tests for null, blank, and non-empty values.
13. **Changing the contract when adding `requireNonNull` to a constructor.** Rejecting null may be right for a new model, but it alters valid data in an existing system.
14. **Running record pattern examples on JDK 17.** Record patterns and pattern `switch` in this article require Java 21 or later.

## 12. Self-Check Exercises

**Question 1.** `Object value = null;`. What do the following two checks return?

```java
value instanceof Text t
value instanceof Text(var inner)
```

*Answer:* Both return `false` because the **outer object** value is `null`.

**Question 2.** `Object value = new Text(null);`. Why does `value instanceof Text(String inner)` match, yet `inner.strip()` can still throw an NPE?

*Answer:* `String inner` is an unconditional component type pattern for the `String value` field, so it can bind null; calling `strip()` on the bound-but-null variable causes an NPE.

**Question 3.** Does `new Packet(null, "data")` match `Packet(Text(var x), var p)`? Which pattern should be used to check for a missing child record?

*Answer:* No. The nested record pattern `Text(...)` does not match a null child record. Use `Packet(var nested, var p)` and then check `nested == null`.

**Question 4.** Why is adding `default -> "other"` not a reliable way to handle a null selector in a Java 21 pattern switch?

*Answer:* With a null selector, a pattern switch throws NPE by default if there is no `case null`. You must explicitly handle `null` before the switch or use a `case null` label.

**Question 5.** What is the safe order when classifying `Text` with `when`: checking `text.isBlank()` first or `text == null` first?

*Answer:* Check `text == null` first, because the `Text` component can be null. Only after the null branch is handled is the `isBlank()` guard safe.

**Question 6.** If the domain forbids `Text.value == null`, where should the fix live to avoid repeating guards in every service?

*Answer:* You can place `Objects.requireNonNull(value, "value")` in the record constructor and add a test that the constructor rejects null. However, confirm that this aligns with the business contract, as it changes the set of valid inputs.

**Official references:** [JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JLS Java 21 – Patterns `14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
