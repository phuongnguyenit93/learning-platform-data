# Throwing NullPointerException When a Null Case Is Missing in Java Pattern Matching

When using `switch` with pattern matching, a very common source of confusion is **passing a `null` value into `switch`**. Many developers assume that the `default` branch will catch every value that does not match a pattern, including `null`. In Java, that assumption is **incorrect**: if the `switch` selector is `null` and the `switch` block does not have a `case null` label, `switch` throws a **`NullPointerException` (NPE)** before selecting any normal branch.

Starting in **Java 21**, pattern matching for `switch` officially supports `case null`, allowing `null` to be handled directly inside `switch`. Key points to remember:

- `null instanceof String text` returns **`false`**; an `instanceof` type pattern does not match `null`.
- `switch (value)` with `value == null` **throws `NullPointerException`** if there is no `case null`, even when `default` or other type patterns are present.
- `case null` handles the `null` value specifically. It is not a type pattern and does not declare a pattern variable.
- `default` handles **non-`null`** values that do not match any preceding branch, following `switch`'s default `null`-handling rules.

This article focuses on why the NPE occurs, the role of `case null`, and how to choose the right solution in Java 17 and Java 21+.

## 1. Symptom: `default` Is Present, Yet NPE Is Still Thrown

Consider a `switch expression` using type patterns, valid in **Java 21+**:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Other";
    };
}
```

Calls produce the following results:

| Input | Result |
| --- | --- |
| `describe("Java")` | `"String: Java"` |
| `describe(42)` | `"Integer: 42"` |
| `describe(3.14)` | `"Other"` |
| `describe(null)` | **Throws `NullPointerException`** |

`default` accepts `3.14` because `Double` does not match the `String` or `Integer` patterns. However, `null` is handled according to **the `switch` selector's own rule**. When `case null` is missing, Java throws an NPE; it does not automatically route `null` to `default`.

This is the behavior of both **`switch statement`** and **`switch expression`**. Do not interpret the NPE as a special bug caused by the `default` branch or a pattern variable. It originates from the `switch` selector evaluating to `null` without a branch dedicated to that value.

## 2. Mechanism: Selector, Patterns, and `case null`

General syntax:

```java
switch (selectorExpression) {
    case SomeType variable -> ...;
    case null -> ...;
    default -> ...;
}
```

Logical steps:

1. Java **evaluates `selectorExpression`** to obtain the value to switch on. This can be a variable, a method call, or an expression returning a type supported by `switch`.
2. If evaluating the selector itself throws an exception, `switch` aborts with that exception. For example, `lookup().getName()` can cause an NPE while computing the selector if `lookup()` is `null`.
3. If the selector evaluates normally to **`null`**, Java handles it only via a `case null` label if the `switch` block has one. **When the `case null` label is missing, an NPE is thrown**.
4. If the selector is a **non-`null` value**, Java determines the matching branch: it checks the validly declared constants/patterns/guards and then executes the selected branch; `default` is the fallback option if applicable.
5. With `case SomeType variable`, the **pattern variable** is bound only when the type pattern matches. A `null` value does not match a type pattern and is not bound to that variable.

Model:

```text
Evaluate selectorExpression
         |
         +-- Evaluation throws exception -------> Propagate exception
         |
         v
       Value
         |
         +-- null ---- has case null? -- yes ---> Execute case null
         |                          |
         |                          +-- no -----> NullPointerException
         |
         +-- non-null --------------------------> Check case/pattern/guard
                                                     |
                                                     +--> Matching branch
                                                     +--> default if needed
```

Be careful to distinguish **an error while evaluating the selector** from **an NPE caused by the selector being `null` without `case null`**. Both errors may carry the name `NullPointerException`, but they arise at different places.

## 3. Direct Fix: Add `case null` (Java 21+)

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Null input";
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Other";
    };
}
```

Now:

- `describe(null)` returns `"Null input"`, without throwing an NPE.
- `describe("Java")` returns `"String: Java"`.
- `describe(42)` returns `"Integer: 42"`.
- `describe(3.14)` returns `"Other"`.

`case null` is a **null case label**, not `case Null` or a class type named `Null`. There is no `case null n` syntax to declare a pattern variable for `null`.

### Complete Runnable Java 21+ Example

Save as **`NullCaseDemo.java`**:

```java
public class NullCaseDemo {
    static String withoutNull(Object value) {
        return switch (value) {
            case String text -> "text: " + text;
            case Integer number -> "integer: " + number;
            default -> "other";
        };
    }

    static String withNull(Object value) {
        return switch (value) {
            case null -> "null input";
            case String text when text.isBlank() -> "blank string";
            case String text -> "text: " + text;
            case Integer number -> "integer: " + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(withoutNull("Java"));
        System.out.println(withoutNull(42));
        System.out.println(withoutNull(3.14));

        try {
            System.out.println(withoutNull(null));
        } catch (NullPointerException ex) {
            System.out.println("withoutNull(null): NullPointerException");
        }

        System.out.println(withNull(null));
        System.out.println(withNull(" "));
        System.out.println(withNull("Java"));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac NullCaseDemo.java
java NullCaseDemo
```

Exact output:

```text
text: Java
integer: 42
other
withoutNull(null): NullPointerException
null input
blank string
text: Java
```

In `withoutNull`, `default` is present, yet `null` causes an NPE. The `try/catch` block catches the NPE so the example can run to completion; in real applications, you should explicitly decide whether `null` is a valid input or an error. In `withNull`, `case null` receives `null`; the `String` patterns and guards do not run on `null`.

If you remove `try/catch` and call `withoutNull(null)`, the program will terminate abnormally at that call and print a stack trace (the stack trace content depends on the runtime environment). The NPE is not a `String` return value from the method.

## 4. Why Doesn't `default` Replace `case null`?

There are two distinct concepts:

- **Not matching normal labels:** the selector is a non-`null` value, such as `Double`, that does not match the `String` or `Integer` branches. `default` can handle this case.
- **Selector is `null`:** Java applies special `null` handling to `switch`. Missing `case null` results in an NPE, even though intuitively one might think `null` "is neither a String nor an Integer".

This preserves the familiar `switch` behavior from before Java 21. Adding pattern matching does not mean Java automatically changes `default` to accept `null`.

Even a very broad type pattern cannot replace `case null`:

```java
static String broad(Object value) {
    return switch (value) {
        case Object object -> "non-null object";
    };
}
```

In Java 21+, this is an example of a `switch expression` using a catch-all `Object` pattern for non-`null` objects. **`broad(null)` still throws an NPE** because there is no `case null`. The type pattern `Object object` does not match `null`, and `Object` does not turn `null` into an object that can be bound to the `object` variable.

Therefore, when reviewing a `switch` that takes a reference-type input, explicitly check for **`case null`** if `null` is a value that can reach it.

## 5. Comparison with `instanceof`: `null` Simply Yields `false`

`instanceof` behaves differently from `switch` with respect to `null`:

```java
Object value = null;
boolean matched = value instanceof String text; // false
```

When the target `value` is `null`, the type pattern `String text` does not match, and the `instanceof` expression returns `false`. There is no binding for `text`; `text` cannot be used in the failing branch. However, this `instanceof` check **does not itself throw an NPE**.

```java
if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("no String match");
}
```

With `value == null`, the output is `no String match`. By contrast, replacing the condition with `switch (value)` without adding `case null` can cause the program to throw an NPE before entering `default`.

### Complete Runnable Java 17+ Example

Save as **`NullComparisonDemo.java`**:

```java
public class NullComparisonDemo {
    static String byIf(Object value) {
        if (value instanceof String text) {
            return "length=" + text.length();
        }
        return "no String match";
    }

    static String byOldSwitch(String value) {
        return switch (value) {
            case "yes" -> "accepted";
            default -> "different";
        };
    }

    public static void main(String[] args) {
        System.out.println(byIf(null));
        System.out.println(byIf("Hi"));

        try {
            System.out.println(byOldSwitch(null));
        } catch (NullPointerException ex) {
            System.out.println("old switch: NullPointerException");
        }
    }
}
```

Run on **Java 17 or later**:

```bash
javac NullComparisonDemo.java
java NullComparisonDemo
```

Exact output:

```text
no String match
length=2
old switch: NullPointerException
```

`byOldSwitch` uses only string constants and `default`, so this example runs on Java 17. When the selector is `null`, `default` still cannot save it: the NPE is a behavior that existed in `switch` prior to Java 21, not something that only happens with pattern matching.

## 6. `when` Guards Do Not Handle `null` in Place of `case null`

Java 21 supports **guards** for patterns in `switch`:

```java
return switch (value) {
    case String text when text.isBlank() -> "blank";
    case String text -> "not blank";
    default -> "other";
};
```

`when text.isBlank()` is evaluated only **after** the type pattern `String text` matches. If the selector is `null` and there is no `case null`, neither the pattern nor the guard becomes a default check for `null`: `switch` throws an NPE according to the rule stated above.

The correct way when you want both null handling and string checking:

```java
return switch (value) {
    case null -> "null";
    case String text when text.isBlank() -> "blank";
    case String text -> "not blank";
    default -> "other";
};
```

Even though `text.isBlank()` cannot be used if `text` is not bound, the example places it in a safe position: the guard is evaluated only when the `String text` pattern matches a non-`null` string. There is no need to write a guard like `text != null && text.isBlank()` just to guard against null in this case.

Nor should you write `case String text when text == null -> ...` expecting to catch `null`: the type pattern does not match `null` in the first place, so that guard is not a way to handle a `null` selector.

## 7. `case null, default` When Combining the Two Cases (Java 21+)

If the application's handling policy is **the same** for `null` and values that do not match other branches, Java 21 allows combining labels:

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "string: " + text;
        case null, default -> "null or other";
    };
}
```

- `classify("ok")` → `"string: ok"`.
- `classify(null)` → `"null or other"`.
- `classify(12)` → `"null or other"`.

`case null, default` is a valid combined label and should be placed at the end of the block. It is a concise way to express that null and unsupported types share the same business meaning.

You cannot arbitrarily combine `null` with another type pattern:

```java
// INVALID (Java 21):
// case null, String text -> "string or null";
```

Reason: a type pattern declares the variable `text` only when it matches; `null` does not produce that binding. The syntax allows combining `null` with `default`, not with `String text`. If the two cases require different handling, write separate branches.

## 8. Distinguishing a `null` Selector Error from Errors in the Branch Body

Not every NPE that appears near a `switch` stems from a missing `case null`.

### Case A — `null` selector, missing `case null`

```java
Object input = null;
String output = switch (input) {
    case String text -> text;
    default -> "other";
};
// Throws NullPointerException before selecting default.
```

This is the exact issue under discussion.

### Case B — The selector expression itself throws NPE

```java
String input = null;
int length = input.length(); // Throws NPE before any switch.

// Similarly: switch (input.length()) { ... } cannot receive a selector value.
```

Adding `case null` to another `switch` will not fix calling `input.length()` when `input` is `null`. You must check the value before accessing it.

### Case C — Branch selected, but code inside the branch throws NPE

```java
record Person(String name) {}

Object input = new Person(null);
String result = switch (input) {
    case Person person -> person.name().toUpperCase();
    case null -> "no person";
    default -> "other";
};
// Throws NPE at person.name().toUpperCase().
```

This is a **Java 21+ illustrative snippet**, not a standalone runnable class. The `Person person` pattern matches because `input` is a non-`null` `Person`. However, **the `name` component inside the record** is `null`; calling `toUpperCase()` on that value causes an NPE. `case null` only catches **the selector `input`**, and does not automatically handle every `null` field inside an object.

### Case D — Unboxing a `null` value

```java
Integer boxed = null;
// int count = boxed; // Throws NPE if unboxing occurs.
```

This error is caused by unboxing, not by a case label. If real-world code has multiple steps, identify which step produces the NPE instead of mechanically adding `case null`.

## 9. Three Design Strategies for Potentially `null` Inputs

### A. `null` is a valid state → handle it inside `switch`

For example, a classification function that genuinely accepts `null`:

```java
static String label(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "text";
        case Integer number -> "number";
        default -> "unsupported";
    };
}
```

Choose this approach when null has a **distinct business meaning**, such as "missing data".

### B. `null` is invalid → validate at the boundary

```java
import java.util.Objects;

static String label(Object input) {
    Objects.requireNonNull(input, "input must not be null");

    return switch (input) {
        case String text -> "text";
        case Integer number -> "number";
        default -> "unsupported";
    };
}
```

`Objects.requireNonNull` intentionally throws `NullPointerException` with a clear message when `input` is `null`. This expresses an **input contract**: the method does not accept null. It does not eliminate the NPE, but makes rejecting the input explicit. In another API, `IllegalArgumentException` may be used if that is the chosen contract convention.

### C. Need Java 17 compatibility → check before `switch`

```java
static String label(String input) {
    if (input == null) {
        return "missing";
    }

    return switch (input) {
        case "yes" -> "accepted";
        case "no" -> "rejected";
        default -> "unknown";
    };
}
```

This code runs from Java 17; it does not need `case null` (which was not yet a finalized feature in Java 17). If the project compiles with `--release 17`, you cannot use Java 21 `case null`/type pattern syntax in `switch`.

Choose a strategy based on actual requirements: allow and classify null, reject null at the boundary, or handle it before `switch` due to the Java version. Do not catch all NPEs with a broad `catch (NullPointerException)` to simulate `case null`; that easily hides real programming bugs in the selector or branch body.

## 10. Type Compatibility and `switch` Exhaustiveness

**A type pattern matches only type-compatible, non-`null` values.** For example, `case CharSequence cs` can match `String` and `StringBuilder` because they implement `CharSequence`, but it does not match `null`. `case Object o` does not match `null` either.

**`default` and exhaustive switch** are a separate topic. A `switch expression` must cover normal values according to Java's exhaustiveness rules, but that exhaustiveness does not mean `null` is automatically handled by `default`. For example:

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "String";
        default -> "Other";
    };
}
```

This expression compiles in Java 21+ because it has `default`, yet `classify(null)` still throws an NPE. To handle a `null` selector, you must add `case null` or proactively prevent `null` before evaluating `switch`.

Conversely, `case null` alone **does not replace** covering the remaining cases:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "Null";
        case String text -> "String";
        default -> "Other";
    };
}
```

Here `case null` handles null specifically, `case String text` handles strings, and `default` handles other objects. The three branches have distinct purposes.

## 11. Common Mistakes to Watch For

| Misconception | Correct Understanding |
| --- | --- |
| “`default` catches every input, including `null`.” | Without `case null`, a `null` selector causes an NPE; `default` does not handle it instead. |
| “`case Object object` definitely accepts `null` too.” | A type pattern only matches type-compatible, non-`null` objects. |
| “`instanceof` and `switch` behave the same way with `null`.” | An `instanceof` type pattern returns `false`; a `switch` missing a null case throws an NPE. |
| “A `when` guard checking `text == null` will catch a null selector.” | The guard runs only after the type pattern has matched; it does not catch a `null` selector value. |
| “Once `case null` is present, no NPE can happen.” | The selector expression, branch body, dereferencing, or unboxing can still throw an NPE. |
| “Combining `case null, String text` is valid.” | Java 21 allows combining `case null, default`; you cannot combine null with a type pattern. |
| “If a `switch` is exhaustive, it definitely handles null.” | Exhaustiveness over the considered values does not imply handling a null selector. |
| “`case null` is Java 17 syntax.” | It is a `switch` feature standardized in Java 21; on Java 17, check for null before `switch`. |

## 12. Checklist When Reviewing or Debugging

When you see a `NullPointerException` near a `switch`:

1. **Identify the selector**: what does the expression inside `switch ( ... )` actually return? Can it be `null`?
2. **Check where the NPE originates**: did the NPE occur while evaluating the selector, at the start of `switch` due to a missing `case null`, or in the code of the selected branch?
3. **Read the case labels**: is there a `case null` or only `default`? Is there a broad type pattern mistaken for handling null?
4. **Determine the Java target version**: Java 21+ can use `case null`; Java 17 should handle null before `switch`.
5. **Decide the null policy**: treat null as a valid state needing its own branch, or as an input error needing a clear message.
6. **Re-check the other branches**: adding `case null` does not change the classification logic for non-`null` values; appropriate patterns/`default` are still needed, avoiding dominated case order.
7. **Test at least three input groups**: a value matching a pattern, a non-`null` value not matching any pattern, and a `null` value. When there is a `when` guard, add an input that matches the type pattern but makes the guard return `false`.

Especially with data from JSON, databases, APIs, or methods that can return `null`, testing the null branch should be part of behavioral testing rather than just checking that it compiles.

## 13. Remember via Three Checks

```text
null instanceof String text
    -> false; does not bind text.

switch (null) { case String s -> ...; default -> ...; }
    -> NullPointerException in Java 21+; default does not catch null.

switch (null) { case null -> ...; case String s -> ...; default -> ...; }
    -> selects case null in Java 21+.
```

**Core rule:** Java preserves the `switch` behavior of throwing an NPE when the selector is `null` **if `case null` is not declared**. A type pattern is a type test for a non-`null` object; `default` handles normal unmatched values. To handle `null` as an intentional case, use `case null` in Java 21+ or check before `switch` when Java 17 support is needed.

### References

- [Oracle Java SE 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), section **Null case Labels**.
- [Oracle Java SE 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html), standardization milestone for pattern matching for `switch` in Java 21.
