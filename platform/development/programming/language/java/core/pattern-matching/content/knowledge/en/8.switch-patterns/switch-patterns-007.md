# `default` in Java Pattern `switch`

## 1. What Is the Role of `default`?

In **pattern matching for `switch`** (finalized in Java 21), `case` branches can match object types, record patterns, and `when` guards. The `default` label provides a **fallback branch** when no other `case` label applies to the selector value.

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Other value";
    };
}
```

For **non-`null`** values:
- `"Java"` selects `case String text`.
- `42` selects `case Integer number`.
- `3.14` (a `Double`) does not match either listed pattern, so `default` is selected.

**Important exception:** in Java 21, `default` **does not handle a `null` selector on its own**. If the selector is `null` and there is no `case null`, the `switch` throws a `NullPointerException`. To handle `null` explicitly, you must add `case null` or use the combined form `case null, default`.

`default` does not declare a pattern variable; therefore, there is no variable such as `text` or `number` available in its body. When a general value is needed, you can still reference the selector stored in an outer variable (after accounting for `null` and side effects).

## 2. Distinguishing Three Steps: Pattern Matching, Guard Evaluation, and Selecting `default`

A pattern `switch` evaluates labels according to the language's applicability rules. For a label with `when`, both the pattern must match **and** the guard must evaluate to `true` for that label to be selected.

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s when s.isBlank() -> "blank text";
        case String s -> "text:" + s;
        case Integer n when n > 0 -> "positive int:" + n;
        default -> "other";
    };
}
```

Key points to understand:

1. `case null` handles a selector equal to `null`.
2. `case String s when s.isBlank()` applies only when the value is a `String` and all its characters are whitespace according to `String.isBlank()`, including the empty string.
3. If the selector is `"Java"`, the `String s` pattern in the first `String` branch matches, but the guard `s.isBlank()` is false, so `switch` proceeds to `case String s` **without a guard**. That branch is selected.
4. If the selector is a positive integer such as `7`, `case Integer n when n > 0` is selected.
5. If the selector is `-2`, the type pattern `Integer n` matches, but the guard is false; because no other label applies, `default` is selected.
6. If the selector is `3.14`, neither the `String` nor the `Integer` pattern matches, so `default` is selected.

Do not think of `default` as “only running when every type check fails.” The `default` branch can also run when **a type pattern matches, its guard fails, and no other branch accepts the value**.

| Selector value | Selected branch | Result |
| --- | --- | --- |
| `null` | `case null` | `null` |
| `"   "` | `case String s when s.isBlank()` | `blank text` |
| `"Java"` | `case String s` | `text:Java` |
| `7` | `case Integer n when n > 0` | `positive int:7` |
| `-2` | `default` after failed guard | `other` |
| `3.14` | `default` due to no pattern match | `other` |

`case String s` **is not considered a duplicate or dominated by the preceding branch** in this example: the preceding branch has `when s.isBlank()`, so it only accepts a subset of strings; the subsequent branch accepts the rest.

## 3. Standalone Java 21 Program

Save the full code to **`PatternSwitchDefaultDemo.java`**:

```java
public class PatternSwitchDefaultDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank text";
            case String s -> "text:" + s;
            case Integer n when n > 0 -> "positive int:" + n;
            default -> "other";
        };
    }

    static String combined(Object value) {
        return switch (value) {
            case String s -> "string:" + s;
            case null, default -> "other-or-null";
        };
    }

    static String withoutNullCase(Object value) {
        return switch (value) {
            case String s -> "string:" + s;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {null, "   ", "Java", 7, -2, 3.14};

        for (Object value : inputs) {
            System.out.println(classify(value));
        }

        System.out.println(combined(null));
        System.out.println(combined(123));

        try {
            System.out.println(withoutNullCase(null));
        } catch (NullPointerException ex) {
            System.out.println("NullPointerException");
        }
    }
}
```

Compile and run with JDK 21 or newer:

```bash
javac --release 21 PatternSwitchDefaultDemo.java
java PatternSwitchDefaultDemo
```

Exact output:

```text
null
blank text
text:Java
positive int:7
other
other
other-or-null
other-or-null
NullPointerException
```

The program demonstrates four rules at once: a guard can lead to a fallback; `default` handles non-null values not accepted by other branches; `case null, default` handles `null` as well; and `default` on its own **does not** prevent a `NullPointerException` caused by a `null` selector.

## 4. Does `default` Catch `null`?

**No, if you use `default` alone.** Java 21 preserves backward-compatible behavior with earlier `switch` constructs: a `null` selector without a `case null` label still causes a `NullPointerException`, even when `default` is present.

```java
static String label(Object value) {
    return switch (value) {
        case String s -> s;
        default -> "other";
    };
}

// label(12)   => "other"
// label(null) => NullPointerException
```

This differs from the common assumption that “default catches everything.” The fallback scope of a standalone `default` is **non-null values** not handled by other branches.

There are two ways to handle `null`:

**Option A: Standalone `case null`**, when you want to clearly distinguish missing data from data of another type:

```java
return switch (value) {
    case null -> "missing value";
    case String s -> "text:" + s;
    default -> "unsupported type";
};
```

**Option B: Combined `case null, default`**, when `null` and the remaining types share the **same handling policy**:

```java
return switch (value) {
    case String s -> "text:" + s;
    case null, default -> "anything else";
};
```

`case null, default` is a special combined label that applies to `null` and any value not accepted by earlier labels. This is valid syntax in Java 21. You cannot combine `null` with a pattern that declares a variable, such as `case null, String s ->`: that combination is invalid because the `null` branch would have no value to initialize `s`.

**Selection rule:** if you want to report an error or handle `null` separately, write `case null`; if you want to share a single handling path, write `case null, default`. Never overlook the possibility of `null` just because `default` is present.

## 5. `default` and `switch` Exhaustiveness

### 5.1. `switch` Expressions Must Be Exhaustive

A `switch` expression must be able to produce a value (or throw an exception) for every value in the type domain that the compiler considers possible. For example:

```java
// INVALID in Java 21: non-exhaustive switch expression.
// static String classify(Object value) {
//     return switch (value) {
//         case String s -> "text";
//         case Integer n -> "integer";
//     };
// }
```

The static type `Object` still leaves many possibilities such as `Double`, `Boolean`, `List`, and so on. Without a sufficiently broad pattern or `default`, the compiler rejects the code because it does not cover all cases.

Adding `default` allows it to compile:

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "text";
        case Integer n -> "integer";
        default -> "other";
    };
}
```

At **compile time**, `default` helps prove exhaustiveness for the remaining non-null values. That **does not** replace handling `null` if `null` can be passed at runtime.

### 5.2. Enhanced `switch` Statements Must Also Be Exhaustive

In Java 21, a `switch` statement is **enhanced** if it uses a pattern label, `case null`, or a selector whose type is outside the legacy `switch`-supported types. This kind of statement is also **required to be exhaustive**.

```java
static void printType(Object value) {
    switch (value) {
        case String s -> System.out.println("String: " + s);
        case Integer n -> System.out.println("Integer: " + n);
        default -> System.out.println("Other");
    }
}
```

If you remove `default`, the statement above has no branch to handle the many remaining `Object` types and fails to compile.

By contrast, a **legacy `switch` statement** that does not use patterns/`null` on a traditional selector type such as `int`, `String`, or an enum can omit `default` and still compile:

```java
static void printNumber(int n) {
    switch (n) {
        case 1 -> System.out.println("one");
        case 2 -> System.out.println("two");
        // Legacy statement: default is not required.
    }
}
```

Therefore, you should not mechanically apply legacy `switch` rules to the new pattern `switch`. `switch` expressions always require exhaustiveness, and enhanced `switch` statements do as well.

## 6. Not Every Pattern `switch` Needs `default`

If the patterns or constants already **completely cover the selector type**, a `switch` can still be exhaustive without `default`.

The classic example is a **sealed hierarchy**: the compiler knows the permitted subtypes. In Java 21:

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(int radius) implements Shape {}

record Rectangle(int width, int height) implements Shape {}

static String kind(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle:" + c.radius();
        case Rectangle r -> "rectangle:" + (r.width() * r.height());
    };
}
```

Even without `default`, the compiler sees that all direct permitted concrete subtypes of `Shape` are covered. The snippet above shows declarations that must be placed within a valid Java program context (or use the complete program directly below).

**Standalone Java 21 program** (`ShapeSwitchDemo.java`):

```java
public class ShapeSwitchDemo {
    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}

    record Rectangle(int width, int height) implements Shape {}

    static String describe(Shape shape) {
        return switch (shape) {
            case Circle c -> "circle:" + c.radius();
            case Rectangle r -> "rectangle:" + (r.width() * r.height());
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Circle(2)));
        System.out.println(describe(new Rectangle(3, 4)));

        try {
            System.out.println(describe(null));
        } catch (NullPointerException ex) {
            System.out.println("null => NullPointerException");
        }
    }
}
```

Run:

```bash
javac --release 21 ShapeSwitchDemo.java
java ShapeSwitchDemo
```

Output:

```text
circle:2
rectangle:12
null => NullPointerException
```

There are three lessons here:

1. **Exhaustive does not mean `default` is required:** a sealed hierarchy can be covered by specific patterns.
2. **Exhaustive does not automatically handle `null`:** passing `null` without `case null` still causes a `NullPointerException`.
3. **Omitting `default` is sometimes better for maintainability:** if a new permitted subtype is later added to `Shape` and the source is recompiled, the compiler can require updating the `switch` to handle the new subtype. An overly broad `default` would hide that signal. For binary changes that occur without recompiling, the Java 21 runtime may throw `MatchException` when a value does not match the branch set that the older binary assumed was exhaustive; do not treat `default` as a mechanism for checking the evolution of a sealed hierarchy.

Similarly, a `switch` expression on an `enum` may omit `default` if all enum constants are listed:

```java
enum State { NEW, DONE }

static String name(State state) {
    return switch (state) {
        case NEW -> "new";
        case DONE -> "done";
    };
}
```

Adding `default` is not always wrong, but it can suppress useful warnings when new constants or subtypes are added. The decision should depend on whether you want to handle future cases with a fallback or update each branch explicitly.

## 7. `default` Does Not Replace Dominance Rules

In a pattern `switch`, an earlier branch can **cover** a later branch: the compiler reports an error if a branch can never be selected because it is *dominated* by a preceding branch.

```java
// INVALID: String is also a CharSequence; case String is dominated by the preceding case.
// static String invalid(Object value) {
//     return switch (value) {
//         case CharSequence cs -> "sequence";
//         case String s -> "string";
//         default -> "other";
//     };
// }
```

**Fix:** place the specific pattern before the broader pattern:

```java
static String describe(Object value) {
    return switch (value) {
        case String s -> "string";
        case CharSequence cs -> "sequence";
        default -> "other";
    };
}
```

In the valid example, `String` is selected by the first branch; other `CharSequence` instances such as `StringBuilder` can be accepted by the second branch.

An unguarded pattern that is **unconditional for the selector type** can serve a covering role similar to `default`. Therefore, you cannot write both an unconditional `case Object obj` on an `Object` selector and a separate `default` as two fallback branches; the compiler rejects it because the fallback branch is dominated:

```java
// INVALID: two catch-all branches overlap on non-null values.
// return switch (value) {
//     case Object obj -> "object";
//     default -> "other";
// };
```

Also note the **position of `default`**: in a pattern `switch`, `default` should be placed after patterns and `case null`. Under the Java 21 JLS, `default` cannot appear before a `case` branch that has a pattern or a `null` literal. The form `case null, default` must also be the last branch. Organizing in the order *specific → general → fallback* keeps code readable and avoids dominance errors.

## 8. A `when` Guard Cannot Be Replaced by `default` to Keep a Pattern Variable

The following example classifies integers:

```java
static String sign(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "positive: " + n;
        case Integer n when n < 0 -> "negative: " + n;
        case Integer n -> "zero";
        default -> "not integer";
    };
}
```

Here the unguarded `Integer n` accepts the `0` case; `default` only receives non-null values that are not `Integer`. A separate branch is required if you need access to `n` for another guarded case. You cannot write:

```java
// INVALID: n is not declared in default.
// return switch (value) {
//     case Integer n when n > 0 -> "positive: " + n;
//     default -> "zero or other: " + n;
// };
```

Reason: `default` can be selected when `value` is a `String`, `Boolean`, or any other type, so `n` from a failed pattern cannot be used there. If you want all `Integer` values to share the same variable name, add an unguarded `case Integer n` after the guarded branches.

A `switch` consisting only of **guarded patterns** may not be exhaustive because the compiler cannot guarantee that the guard conditions will evaluate to `true` for all values. `default` is one way to resolve this; another is to add an unguarded pattern covering all remaining cases.

**Keep them separate:** “a branch rejected by a guard” is a runtime logical outcome; “non-exhaustive” is a compile-time type-coverage error. `default` can satisfy the coverage requirement while also receiving any leftover concrete values, but it does not turn a false `when` guard into true.

## 9. Record Patterns: Unmatched Components Can Also Reach `default`

In Java 21, record patterns let you check both the record type and its components. A value can have the right record type while the nested pattern inside fails to match:

```java
record Envelope(Object content) {}

static String unpack(Object input) {
    return switch (input) {
        case Envelope(String s) -> "text:" + s;
        case Envelope(Integer n) -> "number:" + n;
        case null -> "null input";
        default -> "unsupported content or type";
    };
}
```

This is an illustrative snippet placed within a valid record declaration context and requires Java 21.

- `new Envelope("Java")` matches `Envelope(String s)`.
- `new Envelope(5)` matches `Envelope(Integer n)`.
- `new Envelope(null)` is a **non-null** record, but its `null` component does not match the `String` or `Integer` type pattern; it goes to `default`.
- `new Envelope(3.14)` also goes to `default`.
- A `null` selector goes to `case null`.

This shows that `default` can receive a **record of the right type whose inner data does not satisfy the specific patterns**, not just classes completely unrelated to the record.

When classifying arbitrary input data, use a meaningful fallback message (for example, “unsupported payload”) so learners do not mistakenly assume every `Envelope` is valid.

## 10. Use `default ->` or `default:`?

Pattern `switch` supports **switch rules** (`->`) and **switch labeled statement groups** (`:`), but their control flow differs.

**The `->` form** is usually clearer and avoids fall-through:

```java
static String name(Object value) {
    return switch (value) {
        case String s -> "string:" + s;
        default -> "other";
    };
}
```

If the branch is a block inside a `switch` expression, use `yield` to return a value:

```java
static int score(Object value) {
    return switch (value) {
        case String s -> s.length();
        default -> {
            int fallback = -1;
            yield fallback;
        }
    };
}
```

In a `switch` statement, `default ->` can contain a method call or a regular statement block:

```java
static void print(Object value) {
    switch (value) {
        case String s -> System.out.println(s);
        default -> System.out.println("Unsupported");
    }
}
```

**The `:` form** is the traditional statement group; you must manage `break` and fall-through. With pattern branches that declare variables, falling through into a branch that requires an uninitialized pattern variable can be a **compile-time error**. For that reason, the examples in this article use `->` to make clear that a selected value leads to a single branch.

`default` does not automatically produce a value for a `switch` expression. If a `default -> { ... }` branch uses a block, it must `yield` a suitable value or complete abruptly with an exception; a block that only logs and finishes without returning a value will fail to compile.

## 11. Handling Fallbacks in Practice: Return a Value, Throw an Exception, or Log Unknown Types?

The choice of behavior for `default` depends on the meaning of the data:

**Return a substitute value** when other types are an expected case:

```java
static String display(Object value) {
    return switch (value) {
        case null -> "(missing)";
        case String s -> s;
        case Number n -> n.toString();
        default -> "(unsupported)";
    };
}
```

**Throw an intentional exception** when other types indicate a contract violation:

```java
static String requiredText(Object value) {
    return switch (value) {
        case String s -> s;
        case null -> throw new IllegalArgumentException("Missing text");
        default -> throw new IllegalArgumentException(
            "Unsupported type: " + value.getClass().getName()
        );
    };
}
```

`value.getClass()` is safe in the `default` branch here because `case null` already handles `null`, and a standalone `default` only receives non-null values.

**Log anomalous data types** (telemetry/logging) when data crosses system boundaries, but avoid silently swallowing real errors. If `default` simply returns `"unknown"` for every unexpected type, an API can lose visibility into a new or malformed payload. Conversely, in a UI rendering path, a fallback value is a good choice so the application keeps running.

A practical rule of thumb: for an **open** type hierarchy like `Object`, `default` is usually necessary. For a **closed** type hierarchy such as a sealed hierarchy with a controlled set of subtypes, consider omitting `default` so the compiler helps detect new cases.

## 12. Common Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Assuming `default` handles `null` automatically | A `null` selector does not go to a standalone `default` | Add `case null` or `case null, default` |
| Omitting `default` in `switch(Object)` with only a few patterns | Not exhaustive | Add a fallback branch or a sufficiently broad pattern |
| Using `default` to access variable `s` declared in `case String s` | `default` does not have `s` in scope | Add a separate `case String s` branch or use the outer selector |
| Placing `case CharSequence` before `case String` | The earlier pattern dominates the later one | Place the more specific type first |
| Placing `default` before a pattern in Java 21 | Violates label ordering rules | Place `default` last |
| Using an unguarded `case Object o` and adding `default` on `Object` | An unconditional pattern already covers non-null values | Choose one fallback approach |
| Thinking a failing guard is a compile-time error | Guards are generally evaluated at runtime | Add an unguarded branch or `default` for failed guard outcomes |
| Unconditionally adding `default` to a sealed `switch` | Can hide missing handling for new subtypes on recompile | Weigh the specific exhaustiveness benefits |
| Using `case null, String s` | Cannot bind `s` on the `null` path | Use a separate `case null` or `case null, default` |
| Confusing legacy and enhanced `switch` statements | Exhaustiveness rules differ | Check whether pattern/`null` labels and selector type make it enhanced |

## 13. Exercises and Answers

**Exercise 1.** Does the following snippet compile, and what does `classify(-1)` return?

```java
static String classify(Object x) {
    return switch (x) {
        case Integer n when n > 0 -> "positive";
        default -> "other";
    };
}
```

**Answer:** Yes (Java 21+). `-1` is an `Integer`, the pattern matches but the guard is false; `default` returns `"other"`. If called with `null`, it still throws `NullPointerException` because there is no `case null`.

**Exercise 2.** Why does the following snippet fail to compile?

```java
// return switch (obj) {
//     case String s -> "string";
//     case Integer n -> "integer";
// };
```

**Answer:** If `obj` has static type `Object`, the `switch` expression is not exhaustive; many other types are missing. Add `default` or another pattern covering the remaining cases.

**Exercise 3.** In `switch (obj) { case String s -> ...; case null, default -> ...; }`, which values does the second branch receive?

**Answer:** It receives a `null` selector and any value not accepted by `case String s`, such as `new Object()` or `12`. This is a valid combined label.

**Exercise 4.** Given `sealed interface Shape permits Circle, Rectangle`, with two unguarded branches `case Circle` and `case Rectangle`, is it mandatory to add `default`?

**Answer:** No, if the two branches cover all permitted subtypes and the compiler confirms exhaustiveness. However, `null` still requires `case null` if you want to handle it without throwing `NullPointerException`.

**Exercise 5.** In `switch(Object)`, is it valid to place `case CharSequence cs` before `case String s` and add `default`?

**Answer:** No. `String` is always a `CharSequence`, so the `String` branch is dominated by the preceding branch; adding `default` does not fix the error. Place `case String s` first.

**Exercise 6.** Does `new Envelope(null)` enter `default` in a `switch` with `case Envelope(String s)`, `case null`, and `default`?

**Answer:** Yes, because the selector is a non-null record object, but its `null` component does not match `String s`. `case null` is only for a `null` selector.

## 14. Rules to Remember

- `default` is the fallback for **non-null values not accepted by any `case`**.
- A false `when` guard can lead to another `case` or `default`; the guard is evaluated when the corresponding pattern matches at runtime.
- `case null` handles a `null` selector separately; `case null, default` combines `null` handling with the remaining values.
- `switch` expressions and enhanced `switch` statements must be exhaustive. `default` is one way to satisfy this requirement, while sealed hierarchies and fully covered enum constant sets may not need it.
- `default` has no pattern variables; place specific patterns first and the fallback branch last to avoid dominance.
- Choose the appropriate fallback behavior: return a default value for expected data, or throw a clear error when a value violates the contract.

### Official Documentation

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Switch Expressions](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html)
- [Java SE 21 JLS §14.11 — The switch Statement](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 JLS §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
