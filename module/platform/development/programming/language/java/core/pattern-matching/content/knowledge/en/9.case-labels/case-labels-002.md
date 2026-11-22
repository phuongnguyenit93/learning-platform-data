# Case null and Explicit Null Handling in Java 21 switch

**Scope:** the *Case label* section of Java Core Pattern Matching. This lesson uses Java SE 21, where *pattern matching for switch* is finalized under JEP 441. The focus is on how to write and understand the `case null` label, distinguish it from `default`, decide on policies for handling missing values, and ensure code clarity when combining it with patterns, guards, and different kinds of `switch`.

## 1. The problem: the selector may be null

In a `switch`, the **selector expression** is the expression inside the parentheses of `switch (...)`. Java evaluates this expression to determine which `case` branch matches.

```java
static String classify(Object input) {
    return switch (input) {
        case String text -> "string: " + text;
        case Integer number -> "integer: " + number;
        default -> "other";
    };
}
```

This is a valid `switch` expression in Java 21. For `"Java"`, the result is `"string: Java"`; for `12`, the result is `"integer: 12"`; for `true`, the result is `"other"`. However, **`classify(null)` throws `NullPointerException`** even though `default` is present.

Reason: in a Java 21 `switch`, **a standalone `default` is only a fallback branch for non-null values** to which no other label applies; `null` requires a `case null` label if you want it to be handled.

The correct fix:

```java
static String classify(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "string: " + text;
        case Integer number -> "integer: " + number;
        default -> "other";
    };
}
```

Now, `classify(null)` returns `"missing"`. There is no need for an external `if (input == null)` check just to avoid an NPE before the `switch`.

**Key takeaway:** `case null` is **a switch label form in the language**, with syntax and behavior specified by the JLS. It is not a type pattern, nor is it an `== null` comparison automatically added by Java to every `default` branch.

## 2. Case label syntax according to the JLS

In Java SE 21, the label forms relevant to this lesson include:

```text
case CONSTANT_1 [, CONSTANT_2 ...]
case null
case null, default
case PATTERN [when GUARD]
default
```

This is a **simplified representation for learning**, not the complete formal grammar in JLS `14.11.1.

Example comparing the components:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null selector";            // null label
        case String s when s.isBlank() -> "blank"; // pattern + guard
        case String s -> "string";                // type pattern
        case Integer n when n >= 1 && n <= 3 -> "small integer"; // type pattern + guard
        default -> "other";                      // default label
    };
}
```

In this example with an `Object` selector, the branch `case Integer n when n >= 1 && n <= 3` uses a type pattern with a guard to match `Integer` values from 1 to 3. Constant labels `case 1, 2, 3` are only valid in a `switch` with a compatible selector type (such as `int` or `Integer`), and are not directly valid with a selector whose static type is `Object`. `case null` is a special label for a null selector and **does not declare a variable**. `case String s` is a type pattern and declares the variable `s` when matched. `when` is a guard that adds a condition to a **pattern**, not a general extension for all labels.

### When the selector is null, which label is selected?

According to JLS `14.11.1.2:

1. Evaluate the selector expression. If it completes abruptly with an exception, the entire `switch` completes abruptly with that exception.
2. If the selector value is `null`, a `case null` label (including the combined `case null, default`) applies if one exists.
3. If the selector value is non-null, Java determines the applicable constant or pattern label according to the language rules; the guard is checked once the pattern has matched.
4. `default` is used when no other label applies to a non-null value.

Therefore, the position of `case null` in the label group does not turn it into a branch that "only runs after all patterns." If the selector is null, the mechanism for applying the null label happens separately.

## 3. Three different options for null and the remaining branch

### 3.1. Separate case null: distinguishing missing data from wrong-type data

```java
static String label(Object input) {
    return switch (input) {
        case null -> "missing value";
        case String text -> "text: " + text;
        default -> "unsupported value";
    };
}
```

Results:

| Input | Label | Result |
| --- | --- | --- |
| `null` | `case null` | `missing value` |
| `"Hi"` | `case String text` | `text: Hi` |
| `42` | `default` | `unsupported value` |

This is the clearest approach when the business logic wants to distinguish between **no data** and **data present but in the wrong format**.

### 3.2. Standalone default: null is rejected

```java
static String strictLabel(Object input) {
    return switch (input) {
        case String text -> "text";
        default -> "other";
    };
}
```

`strictLabel(null)` throws `NullPointerException`. A `case null` label is not needed if the method contract specifies that the selector must not be null and you want the error to be caught.

If a more specific message is needed, you can still declare a null label to explicitly reject it:

```java
static String strictLabelWithMessage(Object input) {
    return switch (input) {
        case null -> throw new IllegalArgumentException("input must not be null");
        case String text -> "text";
        default -> "other";
    };
}
```

Thus, **having `case null` does not mean you must accept `null`**. It can handle it as valid, return a default value, or throw an explicit exception depending on the contract.

### 3.3. Case null, default: the same handling for null and other types

Java 21 has a special form:

```java
static String compact(Object input) {
    return switch (input) {
        case String text -> "text";
        case null, default -> "not-text";
    };
}
```

Results:

- `compact("Java")` returns `"text"`.
- `compact(null)` returns `"not-text"`.
- `compact(10)` returns `"not-text"`.

Use `case null, default` when the business policy **genuinely treats null and all remaining values the same**. If you need separate logging or a separate error code for null, split them into two labels.

**This is a specific syntax exception:** Java 21 allows `case null, default`, but does not allow writing `case null, String text` or `case String text, default` as an arbitrary combination of patterns.

### Comparison table

| Label | Null selector | Non-null value | Pattern variable |
| --- | --- | --- | --- |
| `case null` | Yes | No | No |
| `default` | No | Remaining values after other labels | No |
| `case null, default` | Yes | Remaining values after other labels | No |
| `case String s` | No | Only values matching type `String` | Yes: `s` |
| `case Object value` | No | Any object compatible with `Object` | Yes: `value` |

## 4. Case null and patterns are not interchangeable

A type pattern such as `String text` or `Object any` checks whether **a non-null object** matches the corresponding type. Therefore:

```java
static String nonNull(Object input) {
    return switch (input) {
        case Object any -> "object";
    };
}
```

This is an exhaustive `switch` expression for a selector of type `Object`, yet:

- `nonNull("Java")` returns `"object"`.
- `nonNull(7)` returns `"object"`.
- `nonNull(null)` throws `NullPointerException`.

Even an *unconditional* pattern like `Object any` does **not** automatically catch a null selector. To handle null, add `case null`:

```java
static String withNull(Object input) {
    return switch (input) {
        case null -> "missing";
        case Object any -> "object";
    };
}
```

These two branches sufficiently distinguish a null selector from any non-null object; `default` is not needed.

### Case null is not a pattern with a guard

The following code **does not compile**:

```java
// DOES NOT COMPILE:
// return switch (input) {
//     case null when true -> "missing";
//     default -> "other";
// };
```

In Java 21, `when` attaches to a **case pattern**. It does not apply to `case null` or constant-only labels.

Instead, place the required logic inside the body of the null branch:

```java
static String nullDecision(Object input, boolean optional) {
    return switch (input) {
        case null -> optional ? "optional missing" : "required missing";
        case String text -> text;
        default -> "unsupported";
    };
}
```

The program only performs the additional decision if the null selector enters the null branch.

## 5. Exhaustiveness and null: two different checks

**Exhaustiveness** means the set of `switch` labels satisfies the compiler's coverage rules. In Java 21:

- A **`switch` expression** must be exhaustive.
- An **enhanced `switch` statement** (for example, one with pattern/null labels or a reference-type selector other than traditional switch types) must also be exhaustive.
- `default` is one way to achieve exhaustiveness, or you can use patterns that cover all relevant values for the selector type, such as a catch-all type pattern.
- **Exhaustiveness does not guarantee that a null selector will not cause an NPE.**

Example:

```java
static int length(String text) {
    return switch (text) {
        case String s -> s.length();
    };
}
```

The snippet above is valid in Java 21: the type pattern `String s` covers all **non-null** values of a selector of type `String`. However, `length(null)` still throws `NullPointerException` because there is no null label.

If the policy for null is to return length 0:

```java
static int safeLength(String text) {
    return switch (text) {
        case null -> 0;
        case String s -> s.length();
    };
}
```

`safeLength(null)` returns `0`; `safeLength("abc")` returns `3`.

**Note:** if a `switch` expression on `Object` only has `case null` and `case String s`, the code is **not exhaustive**, because `Integer` and other types remain. Add `default` or a set of patterns covering all non-null values.

### Enhanced switch statements must also be exhaustive

```java
// DOES NOT COMPILE: enhanced switch statement is not exhaustive.
// static void incomplete(Object input) {
//     switch (input) {
//         case null -> System.out.println("missing");
//         case String s -> System.out.println(s);
//     }
// }
```

Fix it with an appropriate `default` branch:

```java
static void complete(Object input) {
    switch (input) {
        case null -> System.out.println("missing");
        case String s -> System.out.println(s);
        default -> System.out.println("another type");
    }
}
```

When a new branch is added to handle null, you still need to check that **all other cases are covered** according to Java 21 rules.

## 6. Using case null with String, wrappers, and enums

### String selector

```java
static String classifyText(String text) {
    return switch (text) {
        case null -> "missing";
        case "" -> "empty";
        case "OK" -> "accepted";
        default -> "other text";
    };
}
```

Distinctions:

- `null`: no `String` object.
- `""`: a `String` object exists, but it is an empty string.
- `"  "`: a string containing whitespace, not equal to the empty string; to treat it as blank, use `isBlank()` logic with a pattern guard.

### Wrapper number selector

```java
static String classifyNumber(Integer number) {
    return switch (number) {
        case null -> "missing";
        case 0 -> "zero";
        default -> "number";
    };
}
```

`Integer` can be null and allows `case null`. Conversely, primitive `int` **cannot** hold null:

```java
// DOES NOT COMPILE:
// static String wrong(int number) {
//     return switch (number) {
//         case null -> "missing"; // Selector int is a primitive type.
//         default -> "number";
//     };
// }
```

Do not unbox an `Integer` before handling null: converting a null `Integer` to `int` can throw an NPE before the `switch` can select a label.

### Enum selector

```java
enum State { OPEN, CLOSED }

static String stateLabel(State state) {
    return switch (state) {
        case null -> "unknown";
        case OPEN -> "open";
        case CLOSED -> "closed";
    };
}
```

Writing `default` is not required: all enum constants have been listed to satisfy the exhaustiveness check, and `case null` is handled separately. If the enum gains new constants later, the branches should be re-evaluated; for enum types evolving across library versions, also consider runtime compatibility.

## 7. Null selector and null inside a record pattern are two different things

Consider the record:

```java
record Ticket(String id) {}
```

The following two values are very different:

```java
Ticket missing = null;          // The selector itself can be null.
Ticket noId = new Ticket(null); // The selector is a Ticket, and the id component is null.
```

With Java 21, this can be handled explicitly:

```java
static String ticketLabel(Object input) {
    return switch (input) {
        case null -> "ticket missing";
        case Ticket(String id) when id == null -> "ticket without id";
        case Ticket(String id) -> "ticket " + id;
        default -> "not a ticket";
    };
}
```

Results:

- `ticketLabel(null)` → `"ticket missing"`.
- `ticketLabel(new Ticket(null))` → `"ticket without id"`.
- `ticketLabel(new Ticket("T7"))` → `"ticket T7"`.
- `ticketLabel("T7")` → `"not a ticket"`.

**Why can a record pattern still match a null component?** Here, the type pattern `String id` inside the record pattern is unconditional for the component type `String`. According to Java 21 record pattern rules, it can accept a `null` component value. The outer record object itself must still be non-null. With a different component type and pattern, null-matching behavior may differ; you must not conclude that all nested patterns always match null.

The guard `when id == null` is evaluated **after** the record pattern `Ticket(String id)` has matched and the variable `id` has a value (which may be null in this case). The `== null` comparison does not dereference the variable, so it is safe.

## 8. Label ordering, dominance, and compile-time errors

### The null label is unique

A `switch` block cannot have two `case null` labels. Do not use both a standalone `case null` and `case null, default`: doing so duplicates the null label.

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case null -> "first";
//     case null -> "second"; // Duplicate null label.
//     default -> "other";
// };
```

### Do not write case null, String s

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case null, String s -> "missing-or-text";
//     default -> "other";
// };
```

If two cases share the same result, you can separate the labels and return the same string; or write a shared helper and call it from each branch:

```java
static String sameMessage(Object value) {
    return switch (value) {
        case null -> "unknown";
        case String s -> "unknown";
        default -> "other";
    };
}
```

### Avoid placing default before case null or case patterns

According to the Java 21 JLS, placing `default` before a `case null` label or a pattern label is a **compile-time error**. For new code, place `default` at the end of the block for readability and consistency.

`case null, default` is a combined label: **no switch label may appear after it**. This syntax belongs to the final branch of the block.

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case null, default -> "remaining";
//     case String s -> "string"; // Label after case null, default.
// };
```

### Avoid overly broad patterns dominating remaining branches

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case Object obj -> "object";
//     default -> "other"; // Object obj already covers all non-null values.
// };
```

An unguarded pattern that is unconditional for the selector type can dominate `default`. If you need to handle null alongside a catch-all pattern, write `case null` and `case Object obj` instead of adding an unnecessary default.

### Guards do not replace the null branch

```java
static String textCategory(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when s.isBlank() -> "blank";
        case String s -> "nonblank";
        default -> "not a String";
    };
}
```

Place specific guarded conditions before the general `String s` pattern, because placing the unguarded `String s` pattern first would dominate the guarded branch following it.

## 9. Switch expressions and switch statements with a null label

### Switch expression returning a value

```java
static String normalize(String input) {
    return switch (input) {
        case null -> "(missing)";
        case String s when s.isBlank() -> "(blank)";
        case String s -> s.trim();
    };
}
```

A `switch` expression can use `case null -> "..."` directly as a value. If multiple statements are needed in the branch, use a block with `yield`:

```java
static String normalizeVerbose(String input) {
    return switch (input) {
        case null -> {
            String fallback = "(missing)";
            yield fallback;
        }
        case String s -> s.trim();
    };
}
```

`yield` returns a value from a branch of a **switch expression**. Do not use `break` with a value in place of `yield`.

### Switch statement executing an action

```java
static void printValue(String input) {
    switch (input) {
        case null -> System.out.println("missing");
        case String s when s.isBlank() -> System.out.println("blank");
        default -> System.out.println(input);
    }
}
```

With a switch statement using arrow `->` branches, each branch runs only its own action, avoiding unintended *fall-through*.

### Avoid fall-through leaving pattern variables uninitialized

With colon `:` labels, the language has *fall-through*, but control flow must not fall into a statement group that uses a pattern variable not guaranteed to be initialized:

```java
// DOES NOT COMPILE:
// switch (input) {
//     case null:
//     case String s:
//         System.out.println(s); // Path from case null does not bind s.
//         break;
//     default:
//         break;
// }
```

For null labels and pattern labels, the most readable option in most situations is to use a separate `->` for each branch, and call a shared helper if the handling is genuinely identical.

## 10. Complete Java 21 example

Create the file **`CaseNullLabelsDemo.java`**:

```java
public class CaseNullLabelsDemo {
    record Ticket(String id) {}

    enum State { OPEN, CLOSED }

    static String render(Object input) {
        return switch (input) {
            case null -> "missing";

            case String text when text.isBlank() -> "blank";
            case String text -> "text:" + text;

            case Ticket(String id) when id == null -> "ticket-without-id";
            case Ticket(String id) -> "ticket:" + id;

            default -> "unsupported:" + input.getClass().getSimpleName();
        };
    }

    static String compact(Object input) {
        return switch (input) {
            case String text -> "text";
            case null, default -> "not-text";
        };
    }

    static String statusLabel(State state) {
        return switch (state) {
            case null -> "unknown";
            case OPEN -> "open";
            case CLOSED -> "closed";
        };
    }

    static String strict(Object input) {
        return switch (input) {
            case String text -> "string";
            default -> "other";
        };
    }

    static void show(String value) {
        switch (value) {
            case null -> System.out.println("printed:missing");
            case String text when text.isBlank() ->
                    System.out.println("printed:blank");
            default -> System.out.println("printed:" + value);
        }
    }

    public static void main(String[] args) {
        Object[] values = {
                null, " ", "Java", new Ticket(null), new Ticket("T7"), 42
        };

        for (Object value : values) {
            System.out.println(render(value));
        }

        System.out.println(compact(null));
        System.out.println(compact(99));
        System.out.println(statusLabel(null));
        System.out.println(statusLabel(State.OPEN));
        show(null);

        try {
            System.out.println(strict(null));
        } catch (NullPointerException exception) {
            System.out.println("strict:NPE");
        }
    }
}
```

**Compile and run with JDK 21 or later, without needing to enable preview:**

```bash
javac --release 21 -encoding UTF-8 CaseNullLabelsDemo.java
java CaseNullLabelsDemo
```

**Exact output:**

```text
missing
blank
text:Java
ticket-without-id
ticket:T7
unsupported:Integer
not-text
not-text
unknown
open
printed:missing
strict:NPE
```

**Explanation:**

1. `null` enters `case null` and is reported as missing data.
2. A single-space string matches `String text` and the `isBlank()` guard; `"Java"` enters the remaining String branch.
3. `new Ticket(null)` is not a null selector; the record pattern matches, and the guard detects the null component. `new Ticket("T7")` enters the next record branch.
4. `42` is boxed into `Integer` and falls into `default`, where `input.getClass()` is safe because a null selector has already been intercepted.
5. `compact(null)` and `compact(99)` both return `"not-text"` via `case null, default`.
6. `statusLabel(null)` handles null for the enum; `statusLabel(State.OPEN)` uses the enum label.
7. `show(null)` demonstrates null handling in a switch statement, printing `printed:missing`.
8. `strict(null)` has no null label, so it throws an NPE which is caught in `main`.

## 11. Clear policies for real-world applications

Whether to use `case null` must come from the **data contract**. Common design approaches:

| Policy | How to write | When appropriate |
| --- | --- | --- |
| Null is a valid input | `case null -> defaultValue` | Optional value, data not yet provided |
| Null must be distinguished and reported as an error | `case null -> throw new IllegalArgumentException(...)` | API requires a meaningful value, explicit error desired |
| Null is a contract violation needing no separate branch | `Objects.requireNonNull(input)` before `switch`, or let NPE occur | Internal input with a clear non-null contract |
| Null and other types are handled identically | `case null, default -> fallback` | Goal is genuinely a shared "unusable" group |

**When returning a fallback:** choose a value that cannot be confused with valid data. For example, for string length, returning `0` for `null` can make "missing data" and "empty string" indistinguishable; if the application needs to distinguish them, return a separate state or throw an appropriate exception.

**When logging:** avoid calling `value.getClass()` in the null branch. Only call `getClass()` in branches where the input is known to be non-null.

**When working with Optional:** `Optional<T>` and `case null` address two different contract layers. `Optional.empty()` is a non-null `Optional` object; it does not enter `case null` on its own. Choose a consistent representation of absence in your API.

**When handling external data:** test null selectors, valid types, unexpected types, and records with null components. Simply "having a default" is not proof that null is handled.

## 12. Self-check exercises

**Exercise 1 — does default catch null?** Predict the behavior:

```java
Object value = null;
String result = switch (value) {
    case Integer number -> "number";
    default -> "other";
};
```

**Answer:** throws `NullPointerException`; does not return `"other"`. To return `"missing"`, add `case null -> "missing";`.

**Exercise 2 — catch-all pattern.** Predict:

```java
static String test(Object value) {
    return switch (value) {
        case Object any -> "object";
    };
}
```

**Answer:** for `"abc"` returns `"object"`; for `null` throws NPE. The compiler considers this `switch` expression exhaustive for type `Object`, but does not turn the pattern into a null-matching one.

**Exercise 3 — splitting case null, default.** Change the `compact` method into two branches so that null returns `"missing"`, while non-String types return `"unknown"`.

**Answer:**

```java
static String split(Object input) {
    return switch (input) {
        case null -> "missing";
        case String s -> "text";
        default -> "unknown";
    };
}
```

**Exercise 4 — can a guard be attached to null?** Is the syntax `case null when flag -> ...` valid?

**Answer:** Invalid in Java 21. `when` only attaches to a case pattern. Write the condition inside the body of `case null` or handle the logic before the `switch`.

**Exercise 5 — record with a null component.** Why does `new Ticket(null)` enter the `Ticket(String id)` branch instead of `case null`?

**Answer:** the selector is a non-null `Ticket` object. The `id` field has a null value and is handled by the component pattern with its corresponding matching rules; `case null` is only for when the selector value itself is null.

**Exercise 6 — enum and exhaustiveness.** With `enum State { OPEN, CLOSED }`, if a `switch` expression has both `OPEN` and `CLOSED` branches but no `case null`, what happens when the selector is null?

**Answer:** the expression can be exhaustive with respect to the enum values, yet it still throws NPE for null. Add `case null` when the business logic needs to handle it.

## Official references

- [JLS Java SE 21 `14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): case label forms, guards, null labels, dominance checks, and grammar rules.
- [JLS Java SE 21 `14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): exhaustiveness for labels in a switch.
- [JLS Java SE 21 `14.11.1.2 — Determining Which Switch Label Applies](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): how labels are determined for null selectors and non-null values.
- [JLS Java SE 21 `14.11.3 — Execution of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3): runtime behavior when there is no label for null.
- [JLS Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type/record patterns and matching rules.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): feature finalized in Java 21.