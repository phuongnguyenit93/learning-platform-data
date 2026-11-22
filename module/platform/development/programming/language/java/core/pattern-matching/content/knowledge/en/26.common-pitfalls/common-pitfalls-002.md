# Pitfall of Placing a General Case Before a Specific Case in Java Pattern Matching

When using **pattern matching for `switch`**, the order of `case` branches does not only affect runtime behavior: **the Java compiler also checks whether a branch is completely shadowed by a preceding branch**. If a later `case` can never be selected because a preceding unguarded `case` already matches every value it could match, Java reports a **dominance** error (*dominated case*).

This is a common error when refactoring `if/else if` chains into `switch`, adding subtype handling branches, or using record patterns and `when` in Java 21.

**Version:** This article uses Java 21+ because *pattern matching for switch* and *record patterns* became standard features in Java 21 (JEP 441, JEP 440). Examples run without `--enable-preview`.

## 1. Symptom: this case label is dominated by a preceding case label

Consider the following illustrative method that **does not compile**:

```java
static String bad(Object value) {
    return switch (value) {
        case CharSequence chars -> "sequence";
        case String text -> "string"; // ERROR: dominated case
        default -> "other";
    };
}
```

Why is this an error? `String` implements `CharSequence`. Therefore, **every object that matches `String text` also matches `CharSequence chars`** in the preceding case. The `String` case can never be selected.

A typical diagnostic from `javac`:

```text
error: this case label is dominated by a preceding case label
```

This is a **compile-time error**, not a `ClassCastException`, a runtime error, or merely a performance warning. Java does not run the program first and only then discover the shadowed case.

**Fix: place the specific branch before the general branch.**

```java
static String good(Object value) {
    return switch (value) {
        case String text -> "string";
        case CharSequence chars -> "sequence";
        default -> "other";
    };
}
```

With the fixed code, `"Java"` is handled by the `String` branch; a `StringBuilder` is handled by the `CharSequence` branch; all remaining types fall into `default`.

## 2. What is dominance and why does case order matter?

A **switch label** is *dominated* if, according to Java's static checking rules, every value that the label could handle is already covered by a valid preceding label.

For pattern labels, the core rule in the Java 21 JLS is: a case pattern `q` can be dominated by a preceding **unguarded** case pattern `p` if pattern `p` **dominates** pattern `q`. In practice, this usually reflects a supertype–subtype relationship or a wide–narrow record structure.

Three concepts should be distinguished:

| Concept | Question |
| --- | --- |
| **Pattern matching** | Does the value under inspection match the case's pattern? |
| **Dominance** | Is this case completely covered by a preceding case, causing the compiler to reject it? |
| **Exhaustiveness** | Does the switch handle all required possibilities of the selector? |

A switch can **cover all types** and still **fail to compile** because a case is dominated. Conversely, getting the order right does not guarantee enough branches for a switch expression. These are separate checks.

### Runtime matching order

For a non-`null` selector value, Java evaluates switch labels in order and selects the first applicable label. For a case with a `when` guard, Java requires the pattern to match first before evaluating the guard. Dominance rules prevent situations where the compiler can prove with certainty that a later label can never be selected.

Visual example:

```text
Wrong: CharSequence -> String -> default
       └──────────────┘
         String is dominated

Right: String -> CharSequence -> default
       └─narrow─┘   └── wide ──┘
```

Variable names (`chars`, `text`) do not affect narrowness or wideness. The deciding factors are types, patterns, and guards.

## 3. Type patterns: supertype placed before subtype

Suppose the input has static type `Object`. Typical type patterns are `String text`, `CharSequence chars`, `Integer number`, `Number number`, and `Object other`.

### Wrong example: Number shadows Integer

```java
// Does not compile.
static String badNumber(Object input) {
    return switch (input) {
        case Number number -> "number";
        case Integer integer -> "integer"; // Dominated by Number.
        default -> "other";
    };
}
```

`Integer` is a subtype of `Number`. Any non-`null` `Integer` matches `Number number`, so `case Integer integer` is redundant after that case.

### Correct example

```java
static String goodNumber(Object input) {
    return switch (input) {
        case Integer integer -> "integer=" + integer;
        case Number number -> "number=" + number;
        default -> "other";
    };
}
```

`goodNumber(7)` returns `integer=7`; `goodNumber(3.5)` returns `number=3.5`.

**Practical rule:** group type patterns in the order **specific subtype → broader supertype/interface → fallback**. If multiple types have no subsumption relationship, their relative order usually does not cause dominance, though it should still be arranged intentionally for readability.

### The Object type pattern covers nearly every non-null reference input

With a selector of type `Object`:

```java
// Wrong: placing case Object first dominates the following type patterns.
return switch (input) {
    case Object anything -> "some object";
    case String text -> "text";   // Dominated.
};
```

`Object anything` is a type pattern broad enough to match any **non-`null`** `Object` value, including `String`. Place it at the end of the list of specific pattern cases (and handle `null` separately if needed).

Note: this wrong snippet only illustrates a dominance error, not complete runnable code.

## 4. `when` guards: conditional branches must precede general branches

A type can appear multiple times if the cases differ in their `when` condition. This is a valid way to partition values.

### Wrong: general String case before guarded String case

```java
// Does not compile: the guarded branch is dominated by the general branch.
return switch (input) {
    case String text -> "any text";
    case String text when text.isBlank() -> "blank text";
    default -> "other";
};
```

The preceding `case String text` has no guard; every `String` is handled by it. Therefore, `case String text when text.isBlank()` will never execute.

### Right: check the special condition first, then the remaining cases

```java
return switch (input) {
    case String text when text.isBlank() -> "blank text";
    case String text -> "text=" + text;
    default -> "other";
};
```

Execution flow:

1. If it is a `String` and `text.isBlank()` is true, the first branch is selected.
2. If it is a `String` but the first guard is false, execution continues to the general `String` branch.
3. If it is not a `String`, execution proceeds to `default`.

Guards are checked **after the pattern has matched**, so `text` has static type `String` and is non-`null` when `text.isBlank()` is evaluated. There is no need to repeat `text != null`.

### Important exception: `when true`

In the Java 21 JLS, a case whose guard is the constant expression **`true`** is considered **unguarded** when determining dominance. Therefore:

```java
// Does not compile: when true is treated as equivalent to an unguarded case.
return switch (input) {
    case String text when true -> "text";
    case String text -> "another text";
    default -> "other";
};
```

Do not assume that merely having the `when` keyword prevents a preceding case from dominating a later one. The compiler has a specific rule for always-true guards. On the other hand, Java 21 also disallows guards that are a **constant `false`**.

**Note:** The compiler is not an arbitrary prover for all business conditions. For example, two complex guards can overlap logically; you must order them by intended priority and write tests to verify behavior, rather than relying solely on dominance checks.

## 5. Record patterns: a broad pattern shadows a specific record pattern

Dominance also applies to **record patterns**, not only type patterns.

Suppose:

```java
record Box(Object value) {}
```

We want to distinguish a `Box` with a `String` payload from all other `Box` instances. The following pattern is **wrong**:

```java
// Does not compile.
static String badBox(Object input) {
    return switch (input) {
        case Box(var payload) -> "any box";
        case Box(String text) -> "text box"; // Dominated by Box(var ...).
        default -> "other";
    };
}
```

Why?

- `Box(var payload)` matches **every non-`null` `Box` object**, regardless of whether the `value` component is a `String`, `Integer`, `null`, or another object.
- `Box(String text)` only matches `Box` instances whose `value` component is actually a non-`null` `String` (the component is declared as type `Object`).
- The value set of `Box(String text)` is a **subset** of the value set of `Box(var payload)`.
- Therefore, `case Box(String text)` is dominated if placed after an unguarded `case Box(var payload)`.

Fix it by placing the deeper/more specific pattern first:

```java
static String goodBox(Object input) {
    return switch (input) {
        case Box(String text) -> "text box=" + text;
        case Box(var payload) -> "other box=" + payload;
        default -> "not box";
    };
}
```

With `new Box("Hi")` the result is `text box=Hi`, while `new Box(42)` gives `other box=42` and `new Box(null)` gives `other box=null`. A `var payload` component can receive `null`; this does **not** mean an outermost `null` selector can match `Box(...)`.

### Combining record patterns with `when`

If you need to handle blank Strings, non-blank Strings, and other Boxes:

```java
static String classifyBox(Object input) {
    return switch (input) {
        case Box(String text) when text.isBlank() -> "blank box";
        case Box(String text) -> "text box=" + text;
        case Box(var payload) -> "other box=" + payload;
        default -> "not box";
    };
}
```

Here specificity decreases from top to bottom:

1. `Box` with `String` and guard `isBlank()`;
2. any `Box` with `String`;
3. any remaining `Box`.

If you move the third case to the top, the first two cases become dominated; if you move the second case before the first, the `when` case becomes dominated.

## 6. Constant cases can also be shadowed by a broad pattern

Dominance is not limited to two pattern labels. A **constant case** can also be covered by a preceding unguarded type pattern.

With a selector of type `Integer`:

```java
// Does not compile: case 42 is already covered by Integer i.
static String badInteger(Integer input) {
    return switch (input) {
        case Integer i -> "some integer";
        case 42 -> "forty-two";
    };
}
```

Place the specific constant first:

```java
static String goodInteger(Integer input) {
    return switch (input) {
        case 42 -> "forty-two";
        case Integer i -> "some integer";
    };
}
```

A similar pattern occurs with certain `enum` cases if the corresponding general type pattern is placed before specific enum constants. This is a rule about the range of covered values, unrelated to constant names or variable names.

**Do not mechanically apply "always put constants before patterns" in every situation**. The exact rule depends on the selector type, whether the pattern is *unconditional*, and the applicability of the constant case; when in doubt, use `javac` to check against the JLS.

## 7. `default`, `null`, and general cases

### `default` should usually be placed last

In a pattern switch, `default` represents the fallback branch. If `default` is placed before a pattern case, Java can report an error; with `case null, default`, no case may be placed after it.

```java
// Wrong for a pattern switch:
return switch (input) {
    default -> "other";
    case String text -> "text"; // default placed before a pattern.
};
```

At the same time, if a preceding pattern case is **unconditional for the selector type**, such as `case Object other` with selector `Object`, adding `default` is also invalid because there are two labels acting as fallback for the same selector:

```java
// Wrong: Object other already handles every non-null Object.
return switch (input) {
    case Object other -> "object";
    default -> "other";
};
```

**Language nuance:** Java still allows `default` before constant cases in legacy switch forms for backward compatibility; therefore, one should not claim that the `default` keyword *always* has to be last in every Java program. In code with pattern matching, placing it last is a clear and less error-prone convention.

### A `null` selector does not match an ordinary `Object` pattern

`case Object other` is not `case null`. If a `switch` receives a `null` selector and has no `case null`, the default behavior of a pattern switch is to throw `NullPointerException`, rather than entering `default` or `case Object`.

```java
static String nullable(Object input) {
    return switch (input) {
        case null -> "null selector";
        case String text -> "text=" + text;
        case Object other -> "other object";
    };
}
```

The snippet above handles `null` explicitly and still needs no `default` because `Object other` covers all remaining reference objects. Here `case null` is placed first purely for readability; it is a dedicated handling rule for `null`, not a subtype of `Object`.

## 8. Sealed hierarchy: exhaustiveness vs. dominance

Consider a closed domain model:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(int radius) implements Shape {}
record Rectangle(int width, int height) implements Shape {}
```

`sealed` informs the compiler of the permitted direct subtypes. When all listed subtypes are records (implicitly `final`), a `switch expression` can be exhaustive without `default`:

```java
static String describeShape(Shape shape) {
    return switch (shape) {
        case Circle(int radius) when radius == 0 -> "point-circle";
        case Circle(int radius) -> "circle radius=" + radius;
        case Rectangle(var width, var height) ->
                "rectangle area=" + (width * height);
    };
}
```

- The guarded `Circle` branch must come before the general `Circle` branch.
- The general `Circle(int radius)` branch covers all remaining `Circle` instances.
- The `Rectangle` branch handles the entire second subtype.
- No `default` is needed because every non-`null` `Shape` in the current model is handled.
- If a new permitted subtype is added, the compiler will typically require updating the switch to restore **exhaustiveness**. This is different from a dominance error caused by case ordering.
- `shape == null` is not handled by any case above; calling `describeShape(null)` will throw `NullPointerException`. If null is allowed by business logic, add `case null` with explicit behavior.

**Good design:** leverage `sealed` so the compiler catches missing variants, instead of automatically adding `default` and hiding newly added unhandled cases.

## 9. Complete runnable Java 21 example

Save the file **`CaseDominanceDemo.java`** as follows:

```java
public class CaseDominanceDemo {
    record Box(Object value) {}

    sealed interface Shape permits Circle, Rectangle {}
    record Circle(int radius) implements Shape {}
    record Rectangle(int width, int height) implements Shape {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "null selector";
            case Box(String text) when text.isBlank() -> "blank box";
            case Box(String text) -> "text box=" + text;
            case Box(var value) -> "other box=" + value;
            case String text when text.isBlank() -> "blank string";
            case String text -> "string=" + text;
            case CharSequence chars -> "chars length=" + chars.length();
            case Integer number when number == 0 -> "zero";
            case Integer number -> "integer=" + number;
            case Number number -> "number=" + number;
            case Object other -> "other=" + other.getClass().getSimpleName();
        };
    }

    static String describeShape(Shape shape) {
        return switch (shape) {
            case Circle(int radius) when radius == 0 -> "point-circle";
            case Circle(int radius) -> "circle radius=" + radius;
            case Rectangle(var width, var height) ->
                    "rectangle area=" + (width * height);
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
                new Box("  "), new Box("Hi"), new Box(42), new Box(null),
                " ", "Java", new StringBuilder("xy"),
                0, 7, 3.5, true, null
        };
        for (Object input : inputs) {
            System.out.println(describe(input));
        }
        System.out.println(describeShape(new Circle(0)));
        System.out.println(describeShape(new Circle(2)));
        System.out.println(describeShape(new Rectangle(3, 4)));
    }
}
```

Use JDK 21+ to compile and run:

```bash
javac --release 21 -encoding UTF-8 CaseDominanceDemo.java
java CaseDominanceDemo
```

**Exact stdout:**

```text
blank box
text box=Hi
other box=42
other box=null
blank string
string=Java
chars length=2
zero
integer=7
number=3.5
other=Boolean
null selector
point-circle
circle radius=2
rectangle area=12
```

How to read the output:

1. `new Box("  ")` matches the record pattern with `String`, then the `text.isBlank()` guard succeeds and returns `blank box`.
2. `new Box("Hi")` fails the first guard, then matches the general `Box(String text)`.
3. `new Box(42)` and `new Box(null)` are both handled by `Box(var value)`; the `var` component pattern does not require a non-`null` value.
4. Blank and non-blank strings are handled by the two `String` branches before the `CharSequence` branch; `StringBuilder("xy")` goes to `CharSequence`.
5. `Integer 0` is handled by the branch with `when number == 0`; `Integer 7` by the general `Integer` branch; `Double 3.5` matches `Number`.
6. `Boolean true` only matches the final `Object` branch; the `null` selector has its own branch.
7. `Shape` of kind `Circle` uses a special guard for radius 0, while `Rectangle` computes the area.

The program was verified with `javac --release 21` and executed successfully with **15 lines of stdout** exactly as shown above.

## 10. Error pattern reproducible with javac

The snippet below is **an intentionally invalid Java program** for learning how to read diagnostics. **Do not use it as a runnable example**; when compiling, dominance errors are expected in three places.

Save it as **`DominatedCases.java`** to experiment on your own:

```java
public class DominatedCases {
    record Box(Object value) {}

    static String wideTypeFirst(Object input) {
        return switch (input) {
            case CharSequence chars -> "general";
            case String text -> "specific";  // Error 1: String is dominated
            default -> "other";
        };
    }

    static String wideRecordFirst(Object input) {
        return switch (input) {
            case Box(var payload) -> "general box";
            case Box(String text) -> "text box"; // Error 2: narrower record is dominated
            default -> "not box";
        };
    }

    static String wideGuardFirst(Object input) {
        return switch (input) {
            case String text -> "any text";
            case String text when text.isBlank() -> "blank text"; // Error 3
            default -> "other";
        };
    }
}
```

Run:

```bash
javac --release 21 -encoding UTF-8 DominatedCases.java
```

`javac` refuses to compile and outputs three diagnostics of the form:

```text
error: this case label is dominated by a preceding case label
3 errors
```

Filenames, line numbers, and line wrapping in diagnostics depend on the environment. Testing with `javac --release 21` confirmed **three errors** corresponding to `case String text`, `case Box(String text)`, and `case String text when text.isBlank()`.

How to fix: swap `CharSequence/String`; place `Box(String text)` before `Box(var payload)`; place the guarded `String` case before the unguarded `String` case. The program in Section 9 is the fixed, runnable version.

## 11. Comparison with `if/else if` and reading legacy code

An `if/else if` chain is also evaluated in order:

```java
static String ifElse(Object input) {
    if (input instanceof CharSequence chars) {
        return "sequence";
    } else if (input instanceof String text) {
        return "string";
    }
    return "other";
}
```

This code compiles, but for a `String` value, the `CharSequence` branch is always true first, causing the `String` branch never to be selected in that condition chain. **Do not assume that every ordering logic bug in `if/else if` will be caught by the compiler like pattern switch dominance.**

When refactoring, fix the order right in the design:

```java
static String ifElseFixed(Object input) {
    if (input instanceof String text) {
        return "string";
    } else if (input instanceof CharSequence chars) {
        return "sequence";
    }
    return "other";
}
```

The lesson is not just "swap two lines." You need to understand the **input-set subsumption relationship** of each branch to preserve the intended logic and outcome when converting from `if` to `switch`.

## 12. Workflow for fixing dominance errors

When you see `this case label is dominated by a preceding case label`, follow this sequence:

1. **Identify the reported case.** The message usually points to the **later** case; the root cause lies in a broader **preceding** case.
2. **List every case before it.** Pay attention to type patterns based on superclasses/interfaces, record patterns using `var` or broad component patterns, and unguarded cases.
3. **Compare the matched value sets.** Ask: if a value matches the failing case, does it always match a preceding case? For `String` and `CharSequence`, the answer is yes.
4. **Check `when` guards.** A business guard can make a case more specific; place guarded branches before unguarded branches with the same pattern. Remember the `when true` exception.
5. **Reorder from narrow → wide.** Place constants or special variants first, then specific type/record patterns, and finally broad cases or fallbacks.
6. **Ensure exhaustiveness after fixing.** Reordering cases does not automatically add missing possibilities; if a `switch expression` is missing cases, add meaningful cases.
7. **Check `null` selectors separately.** `case Object other` does not catch `null`; if `null` is a valid input, define its behavior explicitly with `case null`.
8. **Recompile and run tests.** Test subtypes, interfaces, record components containing `null`, values right on guard boundaries, and types that do not match specialized cases.

### Quick identification table

| Placed first (broad) | Placed later (narrow) | Fix |
| --- | --- | --- |
| `case CharSequence cs` | `case String s` | `String` before `CharSequence` |
| `case Number n` | `case Integer i` | `Integer` before `Number` |
| `case Object o` | `case String s` | `Object` last, remove duplicate `default` if present |
| `case Box(var v)` | `case Box(String s)` | `Box(String s)` before `Box(var v)` |
| `case String s` | `case String s when s.isBlank()` | Case with `when` first |
| `case Integer i` | `case 42` | Constant `42` before general pattern |
| `default` | A pattern case | Place fallback last, check switch structure |

Not every preceding branch is a problem. If two types have no subsumption relationship, one case appearing earlier does not automatically make a later case dominated.

## 13. Self-check exercises

**Exercise 1.** Why does the following snippet fail?

```java
return switch (input) {
    case Number n -> "number";
    case Double d -> "double";
    default -> "other";
};
```

*Answer:* `Double` is a subtype of `Number`, so the unguarded `Number n` case dominates `Double d`. Fix by placing `case Double d` before `case Number n`.

**Exercise 2.** Are the following two cases valid in this order?

```java
return switch (input) {
    case String s when s.length() == 0 -> "empty";
    case String s -> "some string";
    default -> "other";
};
```

*Answer:* Yes. The `when` case first handles only empty strings; the second case handles all remaining `String` values.

**Exercise 3.** Given `record Box(Object value) {}`, why does placing `Box(var value)` before `Box(String s)` cause an error?

*Answer:* `Box(var value)` matches every non-`null` `Box`, including a `Box` with a `String` payload. Therefore `Box(String s)` can never be selected.

**Exercise 4.** Why can't `case Object o` at the end completely replace `case null`?

*Answer:* A type pattern at the selector level does not match `null`. Without `case null`, a `null` selector in a pattern switch normally throws `NullPointerException`, even when `default` is present.

**Exercise 5.** If a `switch` on `sealed interface Shape` already covers `Circle` and `Rectangle` without `default`, what is the impact of adding a new subtype?

*Answer:* When the permitted subtype set changes, exhaustive switch expressions may no longer cover all cases and the compiler requires updating them. This is an **exhaustiveness** check, not dominance. After adding the new case, you still need to place it in the right order if the new type has a subsumption relationship with another case.

**Official documentation:** [JLS Java 21 `14.11.1 – Switch Blocks, Dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1), [JLS Java 21 `14.30.3 – Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3), [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
