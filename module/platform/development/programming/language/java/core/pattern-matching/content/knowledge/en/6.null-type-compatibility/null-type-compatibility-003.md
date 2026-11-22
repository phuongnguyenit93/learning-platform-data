# `null` case in pattern switch (Java 21)

**Scope:** handling `null` values when using `switch` with patterns in Java, specifically the syntax stabilized since **Java 21** (*pattern matching for switch*, JEP 441). This article explains `case null`, `default`, `case null, default`, reference types, exhaustiveness, `when` guards, and the difference between a `null` selector object tested by `switch` and a `null` value inside a record.

In Java, a reference-type expression can hold the value `null`. When using `switch` to classify data from `Object`, an API, or a data model, you must clearly decide: **is `null` a valid case to handle, or is it an input error that should be reported?** The `case null` syntax lets you put that decision directly into `switch`.

## 1. Why is `case null` needed?

Consider handling data with a `switch` expression:

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "Text: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Other";
    };
}
```

With `classify("Java")`, the result is `"Text: Java"`. With `classify(12)`, the result is `"Integer: 12"`. However, calling **`classify(null)`** throws a **`NullPointerException`**.

What causes confusion is that the program already has `default`. In Java 21, **a standalone `default` does not handle a `null` selector**. When the selector value is `null`, Java looks for a `case null` label; if no such label exists, `switch` completes abruptly with `NullPointerException`. Java does not automatically treat `null` as a "remaining value" to fall into `default`.

The solution if `null` is allowed:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "No value";
        case String text -> "Text: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Other";
    };
}
```

Now:

| Input | Result |
| --- | --- |
| `null` | `No value` |
| `"Java"` | `Text: Java` |
| `12` | `Integer: 12` |
| `3.5` | `Other` |

`case null` is a **switch label** with its own syntax per JLS `14.11.1; it is **not** a type pattern or record pattern, and it does not declare a pattern variable.

## 2. Three labels to distinguish: `case null`, `default`, `case null, default`

### 2.1. `case null`: `null` selector only

```java
static String nullFirst(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "STRING";
        default -> "OTHER";
    };
}
```

- `nullFirst(null)` → `"NULL"`.
- `nullFirst("abc")` → `"STRING"`.
- `nullFirst(123)` → `"OTHER"`.

With a `null` selector, Java selects the `case null` label. There is no need to check `value == null` outside before entering `switch`.

### 2.2. `default`: fallback branch for non-`null` values

```java
static String withoutNullCase(Object value) {
    return switch (value) {
        case String s -> "STRING";
        default -> "OTHER";
    };
}
```

`withoutNullCase(123)` returns `"OTHER"`, but `withoutNullCase(null)` throws `NullPointerException`. `default` makes the construct cover **non-null** values that do not match any preceding label; it does not implicitly replace `case null`.

### 2.3. `case null, default`: combining `null` and the fallback branch

Java 21 allows the special syntax **`case null, default`** in **a single label**:

```java
static String groupRemainder(Object value) {
    return switch (value) {
        case String s -> "STRING: " + s;
        case null, default -> "MISSING OR OTHER";
    };
}
```

- `groupRemainder("A")` → `"STRING: A"`.
- `groupRemainder(null)` → `"MISSING OR OTHER"`.
- `groupRemainder(9)` → `"MISSING OR OTHER"`.

This syntax is very useful if `null` and unrecognized types **truly need the same handling**. If you want to distinguish a missing value from an invalid value, separate `case null` and `default` into two branches.

This is a specially specified form: **`case null, default` is not a list of two patterns**. In Java 21, you cannot generalize it to `case null, String s` or `case String s, default`.

### Decision table

| Label | Matches `null`? | Matches a non-`null` value? | Commonly used when |
| --- | --- | --- | --- |
| `case null` | Yes | No | Missing data needs its own message |
| `default` | No | Yes, if no other label applies | Value does not match specific branches |
| `case null, default` | Yes | Yes, if not handled by a preceding branch | Missing data and unknown values share the same handling |
| `case String s` | No | Yes, when the object is a `String` | Need to classify and use a variable of type `String` |
| `case Object o` | No | Yes, for every non-null `Object` | Branch matching all non-null reference values |

## 3. How does Java select a branch when the selector is `null`?

According to JLS Java SE 21 `14.11.1.2, the general sequence is:

1. Evaluate the selector expression **once**.
2. If the result is **`null`**, the `case null` (or `case null, default`) label applies if present; if there is no label handling `null`, `switch` throws `NullPointerException`.
3. If the result is **non-`null`**, Java evaluates the appropriate labels (constants, or patterns and guards) according to the branch selection rules.
4. `default` is considered when no label applies to a non-`null` value, while `case null, default` can act as the combined fallback branch.

One point to emphasize: **a universal type pattern does not catch `null`**:

```java
static String universalNonNull(Object value) {
    return switch (value) {
        case Object obj -> "non-null";
    };
}
```

`case Object obj` is a pattern that covers all **non-null** values compatible with `Object`. However:

- `universalNonNull("hello")` → `"non-null"`.
- `universalNonNull(null)` → **`NullPointerException`**.

Even an unguarded `case Object obj` does not match `null`. Pattern exhaustiveness does not mean it handles a null selector.

## 4. `case null` and exhaustiveness: two different questions

A **`switch` expression** must be *exhaustive*: the labels must cover the values required by Java under static rules. An **enhanced `switch` statement** with patterns or `case null` must also be exhaustive in Java 21.

However, **"exhaustive" does not mean "never throws `NullPointerException`"**. For example:

```java
static int stringLength(String value) {
    return switch (value) {
        case String s -> s.length();
    };
}
```

This is a valid `switch` expression in Java 21: for a selector of type `String`, the type pattern `String s` covers all **non-null** values. It still throws `NullPointerException` if `value == null`.

To handle null as well:

```java
static int safeStringLength(String value) {
    return switch (value) {
        case null -> 0;
        case String s -> s.length();
    };
}
```

`safeStringLength(null)` returns `0`; `safeStringLength("Java")` returns `4`. No `default` is needed when the set of labels is already exhaustive. In fact, adding `default` after an unguarded universal pattern that already covers all non-null values can cause a compile-time error due to dominance rules; adding `case null` is the clear way to handle null.

Conversely, **having only `case null`** is not enough for a `switch` expression with a selector of type `Object`, because non-null values remain uncovered. Appropriate patterns or `default` must be added.

## 5. Why is `case null` not a type pattern, record pattern, or guard?

In Java 21, the JLS clearly distinguishes:

- **Type pattern** such as `String s` matches a value of type `String` and initializes variable `s`.
- **Record pattern** such as `Point(int x, int y)` matches a compatible record object and deconstructs its components.
- **`case null`** is a label with the `null` literal, **not** a pattern that declares a variable.
- **`when`** is a guard placed only after a valid **case pattern**, to check an additional condition once the pattern has matched.

Example:

```java
static String inspect(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when s.isBlank() -> "blank";
        case String s -> "text: " + s;
        default -> "other";
    };
}
```

- Selector is `null` → `case null` branch.
- Selector is `"  "` → type pattern `String s` matches and guard `s.isBlank()` is true → `"blank"`.
- Selector is `"Java"` → the guarded String branch is skipped because the guard is false; the next String branch applies.
- Selector is `10` → `default`.

**Do not write `case null when ...`:** Java 21 syntax only allows `when` to be attached to a **case pattern** label. If you need to handle null based on an external condition, put that logic inside the body of `case null -> { ... }` or prepare the condition before the `switch`.

## 6. Distinguishing a null selector from a null record component

This is a common point of confusion in Java 21. Consider:

```java
record Box(String content) {}
```

There are **two completely different values**:

1. `Box outer = null;` — **the selector object itself** is `null`.
2. `Box outer = new Box(null);` — the selector is a **non-null** `Box` object, but the `content` component field has the value `null`.

With a record pattern:

```java
static String inspectBox(Object input) {
    return switch (input) {
        case null -> "outer-null";
        case Box(String content) ->
                content == null ? "inner-null" : "content: " + content;
        default -> "not-a-box";
    };
}
```

Results:

| Value | Branch | Result |
| --- | --- | --- |
| `null` | `case null` | `outer-null` |
| `new Box(null)` | `case Box(String content)` | `inner-null` |
| `new Box("x")` | `case Box(String content)` | `content: x` |
| `123` | `default` | `not-a-box` |

With `new Box(null)`, the pattern `Box(String content)` **can match** because the type pattern for the `String` component is unconditional for the component type `String` and record deconstruction allows that variable to receive `null`. However, when **the entire selector** is `null`, the record pattern `Box(...)` does not match; `case null` handles it.

Do not mechanically apply the rule "`null` does not match a type pattern on an outer selector" to **every nested pattern inside a record**. For a component with another reference type, a non-unconditional sub-pattern may not match `null`. You must check the static type of the component and the pattern resolution rules at that position.

## 7. Syntax and label ordering rules in Java 21

### The selector must be a reference type when using `case null`

```java
static String checkBoxed(Integer number) {
    return switch (number) {
        case null -> "missing";
        case 0 -> "zero";
        default -> "other number";
    };
}
```

This is valid code. `Integer` is a reference type and can hold `null`. When the selector is `null`, Java chooses `case null` before needing to handle numeric values.

Conversely:

```java
// DOES NOT COMPILE: the int selector is a primitive type.
// static String broken(int number) {
//     return switch (number) {
//         case null -> "missing";
//         default -> "number";
//     };
// }
```

A primitive `int` variable cannot hold `null`, so the `case null` label is invalid for this selector. Be careful not to confuse an `Integer` variable (nullable) with an `int` variable.

### Only one `case null` and one `default`

Within a single `switch` block, JLS Java 21 does not allow declaring more than one null label or more than one default label:

```java
// DOES NOT COMPILE:
// switch (value) {
//     case null -> System.out.println("A");
//     case null -> System.out.println("B"); // Duplicate null label
//     default -> System.out.println("C");
// }
```

### `case null, default` must come last

```java
// DOES NOT COMPILE:
// switch (value) {
//     case null, default -> System.out.println("remaining");
//     case String s -> System.out.println(s); // Cannot add labels after this
// }
```

Use `case null, default` after the specific cases:

```java
static String correct(Object value) {
    return switch (value) {
        case String s -> "text";
        case Integer n -> "int";
        case null, default -> "remaining";
    };
}
```

Under Java 21 syntax, placing `default` before a pattern label or `case null` is also an error; placing `default` at the end is consistent and readable.

### Do not combine a null label with a variable-binding pattern in a list

The following syntax is **invalid** in Java 21:

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case null, String s -> "missing-or-string";
//     default -> "other";
// };
```

Do not infer from `case null, default` that you can arbitrarily combine a `null` literal with a type pattern. Separate them:

```java
static String separate(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s -> "string: " + s;
        default -> "other";
    };
}
```

## 8. Writing with a `switch` statement vs. a `switch` expression

### `switch` expression: returning an explicit result

```java
static int parseLength(String input) {
    return switch (input) {
        case null -> 0;
        case String s -> s.length();
    };
}
```

Each branch uses `->` to return a value; the expression must be exhaustive. This style is suitable when classifying input and producing a single result.

### `switch` statement: performing actions

```java
static void printType(Object value) {
    switch (value) {
        case null -> System.out.println("missing");
        case String s -> System.out.println("text " + s.length());
        default -> System.out.println("another type");
    }
}
```

Using `->` prevents accidental *fall-through*. With the traditional colon `case ...:` syntax, if a case pattern declares a variable, the compiler prevents fall-through paths that would leave the pattern variable uninitialized. **Invalid** example:

```java
// DOES NOT COMPILE:
// switch (value) {
//     case null:
//     case String s:
//         System.out.println(s); // Execution can reach here from null with s unassigned.
//         break;
//     default:
//         break;
// }
```

Use two separate branches `case null -> ...` and `case String s -> ...`, or extract the shared handling into a method that does not require a pattern variable.

### Java versions

- **Java 17:** pattern matching for `instanceof` is stable. Pattern matching for `switch` is not yet stable in Java 17 and is in preview.
- **Java 21:** pattern matching for `switch`, including `case null`, is a stable feature. The code in this article can be compiled with `javac --release 21` without `--enable-preview`.
- Do not back-infer syntax from articles about Java 17–20 previews or previews of unnamed patterns/primitive patterns in other versions onto stable Java 21 syntax.

## 9. Complete example: null, pattern, guard, record, and default

Create a file named **`NullCasePatternSwitchDemo.java`** containing the following code. The program uses stable Java 21 features:

```java
public class NullCasePatternSwitchDemo {
    record Box(String content) {}

    static String classify(Object obj) {
        return switch (obj) {
            // A null selector has its own branch.
            case null -> "selector: null";

            // Type pattern + guard.
            case String s when s.isBlank() -> "blank String";
            case String s -> "String(" + s.length() + "): " + s;

            case Integer n -> "Integer: " + n;

            // Record pattern: Box is non-null, but its component can be null.
            case Box(String content) when content == null -> "Box(null)";
            case Box(String content) -> "Box(" + content + ")";

            default -> "Other: " + obj.getClass().getSimpleName();
        };
    }

    static String classifyRemaining(Object obj) {
        return switch (obj) {
            case String s -> "text";
            case null, default -> "other-or-null";
        };
    }

    static String requireNonNull(Object obj) {
        return switch (obj) {
            case String s -> "string";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] values = {
                null, "  ", "Java", 7,
                new Box(null), new Box("x"), 3.14
        };

        for (Object value : values) {
            System.out.println(classify(value));
        }

        System.out.println(classifyRemaining(null));
        System.out.println(classifyRemaining(5));

        try {
            System.out.println(requireNonNull(null));
        } catch (NullPointerException e) {
            System.out.println("NullPointerException");
        }
    }
}
```

**Compile and run** in the directory containing the file using JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 NullCasePatternSwitchDemo.java
java NullCasePatternSwitchDemo
```

**Output:**

```text
selector: null
blank String
String(4): Java
Integer: 7
Box(null)
Box(x)
Other: Double
other-or-null
other-or-null
NullPointerException
```

**Exact explanation for each group:**

1. The first value is `null`, so `case null` is selected. No pattern variable needs to be initialized.
2. The whitespace-only string matches `String s` and the guard `s.isBlank()` is true, returning `blank String`.
3. `"Java"` fails the first guard but matches the next `case String s`, returning length 4.
4. `7` (autoboxed to `Integer` in the `Object[]` array) matches the `Integer n` branch.
5. `new Box(null)` does not have a null selector; the record pattern matches and the guard checks for a null component, returning `Box(null)`.
6. `new Box("x")` goes to the second record pattern, returning `Box(x)`.
7. `3.14` is a `Double`, so `default` returns `Other: Double`. In this example, `obj.getClass()` is safe in `default` because the null selector already has its own branch.
8. `classifyRemaining(null)` and `classifyRemaining(5)` both reach `case null, default`.
9. `requireNonNull(null)` has no `case null`. Even with `default`, the expression still throws `NullPointerException`, and the program catches the exception to print the last line.

## 10. Designing `null` handling in real-world APIs

Explicitly choose one of the following policies:

**Policy A — null is a valid business state.** For example, no user is logged in yet, an object was not found, or an input is optional. Use `case null` and consistently return a value or object representing "no data".

```java
static String displayName(Object value) {
    return switch (value) {
        case null -> "(unknown)";
        case String name when !name.isBlank() -> name;
        default -> "(invalid name)";
    };
}
```

**Policy B — null is a contract violation.** If the API requires non-null input, you can use `Objects.requireNonNull(value)` before `switch` and let `NullPointerException` signal the error, or choose a clear exception message. Do not add `case null` just to hide invalid data.

```java
static String nonNullDescription(Object value) {
    java.util.Objects.requireNonNull(value, "value must not be null");
    return switch (value) {
        case String s -> "text " + s;
        default -> "other";
    };
}
```

**Policy C — null and unrecognized types share the same handling.** Use `case null, default` when both are genuinely equivalent in meaning.

```java
static String simpleLabel(Object value) {
    return switch (value) {
        case Integer i -> "int";
        case String s -> "string";
        case null, default -> "unknown";
    };
}
```

Whichever option you choose, write tests for at least **`null`**, a value matching a pattern, and another value not matching any pattern. For records, also test a **non-null record with a null component** to avoid missing nested cases.

## 11. Common mistakes and self-check

1. **Assuming `default` also catches `null`.** Incorrect in Java 21: without `case null`, a null selector causes `NullPointerException`.
2. **Assuming `case Object o` matches `null`.** It covers non-null objects, not a null selector.
3. **Thinking `case null` is a pattern.** It is a distinct kind of label in `switch` grammar; it does not declare a variable and cannot take a `when` guard.
4. **Mixing `null` with a pattern in one label.** `case null, default` is a special form; `case null, String s` is not valid syntax in Java 21.
5. **Placing `case null, default` before other labels.** Because this label is the combined fallback branch, no labels can follow it.
6. **Declaring `case null` multiple times.** Each switch block can have at most one null label.
7. **Using `case null` with a primitive selector.** For example, `switch (intValue)` cannot receive a null value.
8. **Confusing a null selector with a null record component.** `new Box(null)` is a non-null `Box` object; it can match `case Box(String content)` according to nested pattern rules.
9. **Ignoring exhaustiveness.** `switch` expressions and enhanced `switch` statements must cover the required cases, but exhaustiveness checking does not automatically guarantee that a null selector is handled.
10. **Mixing preview syntax with stable Java 21.** Read the JLS/JEP documentation for the exact target compilation version.

**Exercise 1.** Predict the result:

```java
Object x = null;
String result = switch (x) {
    case String s -> "text";
    case Integer i -> "number";
    default -> "other";
};
```

Answer: **throws `NullPointerException`**, does not return `"other"`.

**Exercise 2.** Fix the code above to return `"missing"` when `x == null`, while keeping `default` for values other than `String`/`Integer`. Answer: add `case null -> "missing";`.

**Exercise 3.** Given `Object x = new Box(null);` and the branch `case Box(String content)`, do you predict the selector will enter `case null`? Answer: **no**; the selector is a non-null `Box`. In the case of a `String` component, the sub-pattern can accept null; check `content == null` inside the `Box` branch.

**Exercise 4.** When should you use `case null, default` instead of two separate branches? Answer: when both null and remaining values have the same meaning, the same result, and the same handling under the business contract.

## Official references

- [JLS Java SE 21 `14.11.1 — The Switch Block](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): syntax of `case null`, `case null, default`, guards, labels, dominance, and exhaustiveness.
- [JLS Java SE 21 `14.11.1.2 — Determining Which Switch Label Applies at Run Time](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): rules for selecting labels when the selector is null/non-null.
- [JLS Java SE 21 `14.11.3 — Execution of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3): when a `switch` statement throws `NullPointerException`.
- [JLS Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type patterns, record patterns, and matching rules.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): feature stabilized in Java 21 and principles for handling `null` in pattern switch.
