# Identifying instanceof Followed by Manual Cast

## 1. Purpose of Identification

In Java code written before **pattern matching for `instanceof`** became a standard feature in Java 16, a common pattern was: checking an object with `instanceof`, then casting it with the `(Type)` operator to use the methods or properties of that subtype.

Example:

```java
Object value = "Java";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.toUpperCase());
}
```

The code above is valid. The test `value instanceof String` only returns a boolean value; therefore, the traditional way of writing requires an additional `(String) value` so that the compiler treats the variable as `String`.

Since Java 16, a **type pattern** combines the type check with the declaration of the cast variable:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

The output of both snippets is `JAVA`. In the second example, `text` is a pattern variable with static type `String`, usable only in the part of the program where Java knows the pattern has matched.

**The refactoring goal** is not to replace every cast in the project with a pattern, but to **find the exact places with the sequence "check with `instanceof` → cast the exact checked value → use the subtype variable"**, and then transform them while preserving the behavior, control flow, and `null`-handling rules of the original code.

## 2. Quick Identification Signs in Legacy Code

When reading legacy Java methods, look for the following structures.

### Pattern A — check and immediately cast in the branch

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

This pattern is a clear refactoring candidate because **the same expression `value`** is both checked and cast to the same type `String`.

Replace with:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

### Pattern B — repeating the cast multiple times

```java
if (value instanceof String) {
    System.out.println(((String) value).length());
    System.out.println(((String) value).toUpperCase());
}
```

Replace with:

```java
if (value instanceof String text) {
    System.out.println(text.length());
    System.out.println(text.toUpperCase());
}
```

The pattern holds a single type-checked variable and reuses it multiple times, reducing duplication. This is usually easier to read and maintain than writing `(String)` at every use.

### Pattern C — multiple subtype check branches

```java
static String classify(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return "String: " + text.length();
    } else if (value instanceof Integer) {
        Integer number = (Integer) value;
        return "Integer: " + number;
    }
    return "Khác";
}
```

Can be transformed into:

```java
static String classify(Object value) {
    if (value instanceof String text) {
        return "String: " + text.length();
    } else if (value instanceof Integer number) {
        return "Integer: " + number;
    }
    return "Khác";
}
```

The variables `text` and `number` have different scopes, tied to their respective branches; they do not become shared variables outside the `if/else if` chain.

### Pattern D — negated check, early exit, then cast

```java
static int lengthOrZero(Object value) {
    if (!(value instanceof String)) {
        return 0;
    }
    String text = (String) value;
    return text.length();
}
```

Refactor as a *guard clause*:

```java
static int lengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

This is an important application of **flow scoping**. Because the negated `if` branch ends with `return`, all remaining paths have proven that `value` matches `String`. The compiler allows using `text` after the `if`.

The snippets above are **standalone illustrations**, not intended to combine all identically named methods into a single class.

## 3. Step-by-Step Safe Refactoring Process

Before making changes:

1. **Identify the expression being checked**: is it a variable `value` or the result of a method call?
2. **Identify the checked type** in `instanceof` and the cast type on the following line.
3. **Verify that they actually refer to the same object and the same expected type**; avoid assuming this just because variable names look similar.
4. **Read all branches and exit paths**: `else` branches, `return`, `throw`, `break`, compound conditions `&&`/`||`, and `null` handling.
5. **Place the pattern variable in `instanceof`** and replace the corresponding casts with the new variable.
6. **Compile and run tests** covering matching cases, non-matching cases, `null`, and other subtypes.
7. **Consider the refactoring complete only when the behavior to be preserved remains intact**, including errors or error messages that are important to the application contract.

This process works well because type pattern syntax is usually very simple, whereas **the behavioral contract of legacy code** is sometimes not.

Basic refactoring example:

```java
// Before:
if (event instanceof TextEvent) {
    TextEvent textEvent = (TextEvent) event;
    handle(textEvent.text());
}

// After:
if (event instanceof TextEvent textEvent) {
    handle(textEvent.text());
}
```

This is only a syntax transformation example, assuming `TextEvent` has a `text()` method, `event` is already declared, and `handle` exists. The code above is not a standalone runnable program.

## 4. Flow Scoping: Why Can't a Pattern Variable Be Used Everywhere?

Consider the compound condition:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

This is valid because `&&` uses short-circuit evaluation. If `value` is not a `String`, Java does not evaluate `text.isBlank()`. If the right-hand side is evaluated, the variable `text` is already bound.

Conversely:

```java
// DOES NOT COMPILE:
// if (value instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

This is an **intentional error example**. The right-hand side of `||` is evaluated when the left-hand side is **false**, meaning the variable `text` has not been bound. Refactoring legacy code with complex conditions must respect this rule; you cannot simply replace `(String) value` with a variable name at any arbitrary position.

Another error:

```java
// DOES NOT COMPILE:
// if (value instanceof String text) {
//     System.out.println(text.length());
// }
// System.out.println(text.toUpperCase());
```

After the `if`, `value` might not be a `String`, so `text` is not in valid scope. To use the variable after the check, let the **non-matching path exit early** as in the `lengthOrZero` example, or place the processing inside the matching branch.

**Remember:** the scope of a pattern variable depends on the execution paths where the compiler proves the pattern has matched (*flow scoping*), not merely on the position of curly braces.

## 5. Do Not Replace Every Cast on Sight

### 5.1. Checked type differs from cast type

Dangerous example:

```java
Object value = Double.valueOf(1.5);

if (value instanceof Number) {
    Integer number = (Integer) value; // ClassCastException at runtime
    System.out.println(number);
}
```

This code **compiles** but throws `ClassCastException` because `Double` is a `Number` but not an `Integer`. It must not be described as a case where `instanceof Number` guarantees safety for `(Integer)`.

If the business logic only handles `Integer`, the correct condition should be:

```java
if (value instanceof Integer number) {
    System.out.println(number);
}
```

This is a **logic bug fix**, not just an equivalent refactoring: for `Double`, the old code throws an exception, whereas the new code does not enter the branch. If the exception must be preserved according to the old contract, that must be decided and expressed explicitly rather than silently skipped.

### 5.2. Checking one expression, casting another expression

```java
Object first = "Java";
Object second = 10;

if (first instanceof String) {
    // Unsafe: second is not first.
    // String text = (String) second;
}
```

An `instanceof` check only proves a property of **the value being checked**; it does not prove the type of another variable. Before refactoring, verify whether the cast actually happens on the exact same value that passed the test.

### 5.3. Calling a method multiple times may return different objects

```java
// Illustrative example, assuming getNext() can return a different value each time.
// if (getNext() instanceof String) {
//     String text = (String) getNext();
//     use(text);
// }
```

The first check statement and the subsequent cast statement may receive two different values. This is not a safe mechanical refactoring case.

A version that is easier to reason about:

```java
Object candidate = getNext();

if (candidate instanceof String text) {
    use(text);
}
```

This is an **illustrative snippet**, assuming `getNext()` and `use()` exist; it is not a standalone program. Storing the result causes `getNext()` to be called **once** instead of up to twice, which may **change side effects or the sequence of consumed values**. Business requirements must be checked before treating the two versions as equivalent.

### 5.4. Casting without a prior check

```java
String text = (String) value;
System.out.println(text.length());
```

If `value` is not a `String`, the cast throws `ClassCastException`; if `value == null`, the cast evaluates to `null` and then calling `length()` throws `NullPointerException`.

Arbitrarily replacing this with:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

changes the failure behavior into **skipping the branch** when it does not match. Only do this if the new requirement allows it; if this code must require a `String`, you can keep the cast and add a clear error message or use an appropriate input-validation API.

## 6. Null: Keep the Handling Exact

Both the traditional check:

```java
value instanceof String
```

and the type pattern:

```java
value instanceof String text
```

return `false` when `value == null`. For legacy `if` code that only performs `instanceof` and then casts in the true branch, switching to a type pattern usually preserves skipping `null` values.

However, **do not confuse that with all data inside the object being non-null**. For example:

```java
if (value instanceof TextEvent event) {
    // event is non-null, but event.text() may be null.
    String text = event.text();
    if (text != null && !text.isBlank()) {
        System.out.println(text.toUpperCase());
    }
}
```

The type pattern confirms the `TextEvent` object; it does not prove that its internal reference fields/components are non-`null`. Checking `text != null` before `text.isBlank()` is still necessary if the data model allows a `null` string.

In applications that need to distinguish a `null` object from an object of an unexpected type, you can make this explicit with a separate branch before `instanceof`. Do not expect a type pattern to replace all data validation rules on its own.

## 7. Complete Java 17+ Example: Before and After with Identical Output

Save the program as **`LegacyCastRefactorDemo.java`**:

```java
public class LegacyCastRefactorDemo {
    interface Event {}

    static final class TextEvent implements Event {
        private final String text;

        TextEvent(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }
    }

    static final class CountEvent implements Event {
        private final int count;

        CountEvent(int count) {
            this.count = count;
        }

        int count() {
            return count;
        }
    }

    // Legacy version: instanceof followed by manual cast.
    static String legacy(Object value) {
        if (value instanceof TextEvent) {
            TextEvent event = (TextEvent) value;
            if (event.text() != null && !event.text().isBlank()) {
                return "TEXT:" + event.text().toUpperCase();
            }
            return "TEXT:EMPTY";
        }

        if (value instanceof CountEvent) {
            CountEvent event = (CountEvent) value;
            return "COUNT:" + (event.count() * 2);
        }

        return "OTHER";
    }

    // Modern version: type pattern binds the variable directly.
    static String modern(Object value) {
        if (value instanceof TextEvent event) {
            String text = event.text();
            if (text != null && !text.isBlank()) {
                return "TEXT:" + text.toUpperCase();
            }
            return "TEXT:EMPTY";
        }

        if (value instanceof CountEvent event) {
            return "COUNT:" + (event.count() * 2);
        }

        return "OTHER";
    }

    // Negated condition followed by early return.
    static String lengthAfterGuard(Object value) {
        if (!(value instanceof TextEvent event)) {
            return "NOT_TEXT";
        }

        String text = event.text();
        return text == null ? "TEXT_NULL" : "LEN:" + text.length();
    }

    public static void main(String[] args) {
        Object[] cases = {
            new TextEvent("java"),
            new TextEvent(" "),
            new TextEvent(null),
            new CountEvent(6),
            "khác",
            null
        };

        for (Object item : cases) {
            System.out.println(legacy(item) + " | " + modern(item));
        }

        System.out.println(lengthAfterGuard(new TextEvent("hello")));
        System.out.println(lengthAfterGuard(new CountEvent(2)));
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac LegacyCastRefactorDemo.java
java LegacyCastRefactorDemo
```

Standard output:

```text
TEXT:JAVA | TEXT:JAVA
TEXT:EMPTY | TEXT:EMPTY
TEXT:EMPTY | TEXT:EMPTY
COUNT:12 | COUNT:12
OTHER | OTHER
OTHER | OTHER
LEN:5
NOT_TEXT
```

Case-by-case breakdown:

1. `TextEvent("java")` matches the `TextEvent` check with a non-blank string; both versions return `TEXT:JAVA`.
2. `TextEvent(" ")` has a whitespace-only string, so `isBlank()` returns `true` and both return `TEXT:EMPTY`.
3. `TextEvent(null)` is still a valid `TextEvent` object. The method checks `null` on the inner string, so both return `TEXT:EMPTY` without throwing `NullPointerException`.
4. `CountEvent(6)` is recognized with the right type and produces `COUNT:12`.
5. The string `"khác"` is not either `Event` in the two branches, so it yields `OTHER`.
6. `null` does not match any `instanceof`, so it yields `OTHER`.
7. `lengthAfterGuard(TextEvent("hello"))` binds `event` and continues past the guard to return `LEN:5`.
8. `lengthAfterGuard(CountEvent(2))` does not match the `TextEvent` pattern and immediately returns `NOT_TEXT`.

In this example, the refactoring does not require Java 21 record patterns or `switch` syntax. **Type patterns in `instanceof` have been a standard feature since Java 16**, so this program runs on Java 17 without `--enable-preview`.

Note: the `modern` version stores `event.text()` into a local variable once; in the example class, `text()` simply returns a field, so this preserves the result. For accessors or methods with side effects in real-world applications, check further before replacing multiple calls with a single call.

## 8. When Should You Keep an Explicit Cast?

Pattern matching is not meant to eliminate all casts:

- **A cast not preceded by an `instanceof` check** may be part of a contract stating "the input must be of this type, otherwise fail". Do not automatically convert it into a check that skips the branch.
- **Casts in generic/unchecked code** require separate evaluation of type information and type erasure. Not every pattern match can prove generic type arguments at runtime.
- **A cast required for a specific API** may still have a valid reason to exist; understand the static type and expected result type before removing it.
- **Numeric casts** such as `(int) doubleValue` are numeric value conversions, not `instanceof` subtype checks followed by a reference cast; they are outside the scope of this refactoring.

The goal is to remove casts that are **redundant after a type test that already guarantees safety**, not to force all legacy code into a single syntax.

## 9. Review Checklist for a Change

| Question | Meaning |
| --- | --- |
| Do `instanceof` and the cast target the exact **same value**? | Avoid checking one variable while casting another. |
| Are the type in `instanceof` and the cast type consistent? | Avoid false assumptions about inheritance relationships and actual types. |
| Does the checked expression have side effects or change between two calls? | Avoid unintentionally changing the number of evaluations. |
| What does the old code do with non-matching values and `null`? | Preserve `else` branches, `return` paths, and intentional errors. |
| Is the pattern variable within valid flow scope? | Especially important with `&&`, `||`, negation, and guard clauses. |
| Are there tests for different subtypes? | Avoid refactoring that only works for one data sample. |
| Is `null` inside the object handled when needed? | `instanceof` does not check every field or component. |
| Does the project's Java version already support type patterns? | Java 16+ supports them as a standard feature; Java 17 is a stable baseline for the example. |

**Remember:** The key sign of code to refactor is **`instanceof T` checking a value followed by `(T)` casting that exact same value** in the matched branch. Replace it with **`instanceof T variable`**, use the pattern variable within valid scope, and carefully verify `null`, subtypes, control-flow branches, side effects, and error behavior. A good refactoring **reduces casts while preserving the exact semantics of the program**.
