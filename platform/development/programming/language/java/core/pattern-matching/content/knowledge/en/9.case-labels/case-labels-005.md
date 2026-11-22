# Qualified Enum Constants in case (Java 21+)

## 1. What is a qualified enum constant?

In Java, an `enum` declares a set of named constants, such as `Color.RED`, `Color.GREEN`, and `Color.BLUE`. A **qualified enum constant** is a way of writing an enum constant along with the name of the enum type that owns it:

```java
enum Color { RED, GREEN, BLUE }

// A case label using a qualified enum constant:
case Color.RED -> "red";
```

The label above has two parts: `Color` is the **enum type**; `RED` is **a specific constant of that enum**. In a `switch`, it only selects the branch when the selector value is exactly the constant `Color.RED`.

This lesson focuses on **qualified enum constants in case labels**, especially when combined with **pattern matching for switch** standardized in **Java 21 (JEP 441)**. Starting in Java 21, enum labels of the form `case Color.RED` can appear in more situations, including when the selector has static type `Object` or an interface implemented by the enum.

Do not confuse the following three forms:

- `case Color.RED -> ...`: a **specific enum constant** label; matches only the `RED` constant of `Color`.
- `case Color color -> ...`: a **type pattern**; matches non-`null` values of **any constant** of `Color` and declares the variable `color`.
- `case RED -> ...`: an **unqualified enum constant**, commonly used in a traditional switch when the selector already has type `Color`.

Understanding the difference between **matching a constant** and **matching a type** is essential to avoid dominance errors and selecting the wrong branch.

## 2. From traditional enum switch to pattern switch

### The familiar syntax before Java 21

When the selector's static type is the enum itself, a traditional switch usually uses constant names **without the enum name prefix**:

```java
enum Color { RED, GREEN, BLUE }

static String legacyName(Color color) {
    return switch (color) {
        case RED -> "red";
        case GREEN -> "green";
        case BLUE -> "blue";
    };
}
```

This snippet is valid on Java 17. Because the selector already has type `Color`, the compiler determines which enum `RED`, `GREEN`, and `BLUE` belong to. In Java 17, writing `case Color.RED` in that position results in a compilation error requiring the enum case label to use an **unqualified** name.

### Qualified syntax from Java 21

Java 21 accepts the qualified form even when the selector has type `Color`:

```java
static String qualifiedName(Color color) {
    return switch (color) {
        case Color.RED -> "red";
        case Color.GREEN -> "green";
        case Color.BLUE -> "blue";
    };
}
```

Both methods above match the exact same `Color` values. For `qualifiedName(Color.RED)`, the result is `"red"`.

The more important extension is a pattern switch over a **broader** type:

```java
static String describe(Object value) {
    return switch (value) {
        case Color.RED -> "red";
        case Color.GREEN -> "green";
        case Color.BLUE -> "blue";
        default -> "not a Color";
    };
}
```

The selector here has static type `Object`, so the enum type cannot be inferred from the selector. Writing `Color.RED` explicitly specifies **which type's constant** is being used as the label. For `describe(Color.RED)`, the result is `"red"`; for `describe("RED")`, the result is `"not a Color"`.

**Version requirement:** examples using `switch (Object)` with an enum-qualified `case` require **Java 21+** as standard syntax, without `--enable-preview`. Trying to force Java 17 to accept this syntax pattern will not succeed simply by switching to a different constant name.

## 3. When should you use qualified names?

Qualified names are especially useful in the following situations.

**Case 1: the selector has type `Object`.**

```java
Object input = Color.GREEN;

String text = switch (input) {
    case Color.RED -> "stop";
    case Color.GREEN -> "go";
    case Color.BLUE -> "info";
    default -> "unknown";
};
```

The selector can hold many kinds of objects. A `case Color.GREEN` label identifies the exact enum value to match. No string conversion occurs; `"GREEN"` remains distinct from `Color.GREEN`.

**Case 2: the selector has an interface type implemented by multiple enums.**

```java
sealed interface Status permits Pipeline, Ticket {}

enum Pipeline implements Status {
    READY, PAUSED
}

enum Ticket implements Status {
    READY, DONE
}
```

Because both `Pipeline` and `Ticket` have a constant named `READY`, writing `Pipeline.READY` and `Ticket.READY` lets you distinguish the two meanings right in the case label. This is particularly useful in a system with multiple independent sets of statuses.

**Case 3: keeping type names clear in a switch with multiple pattern kinds.**

```java
static String label(Object value) {
    return switch (value) {
        case Color.RED -> "special red";
        case Color c -> "other color:" + c;
        case String s -> "text:" + s;
        default -> "other";
    };
}
```

The `Color.RED` constant branch is tested first, the `Color c` type pattern branch handles the remaining `Color` values, and then come `String` and `default`. The qualified name lets the reader see immediately which branch is dedicated to a specific enum value.

Not every switch over an enum has to be rewritten in qualified form. For a switch that only accepts a `Color`, writing `case RED` remains simple and valid. Choose whether to qualify based on the selector type, clarity, and Java version.

## 4. How does enum constant matching differ from type pattern matching?

Consider the enum:

```java
enum Color { RED, GREEN, BLUE }
```

Comparison:

| Case label | Match condition against selector value | Declares a pattern variable? |
| --- | --- | --- |
| `case Color.RED` | Value is strictly the constant `Color.RED` | No |
| `case Color.GREEN` | Value is strictly the constant `Color.GREEN` | No |
| `case Color c` | Value is any non-`null` `Color` constant | Yes, variable `c` of type `Color` |
| `case Enum<?> e` | Value is any enum object matching the type pattern | Yes, variable `e` of type `Enum<?>` |
| `case null` | Selector value is `null` | No |
| `default` | Remaining cases per `switch` rules | No |

For enum constants, Java has a singleton object corresponding to each constant declared in the enum. Therefore, the `case Color.RED` label denotes **that exact enum value**, and does not match merely because another object has the string name `"RED"`.

```java
Object value = Color.RED;

String result = switch (value) {
    case Color.RED -> "exact constant";
    case Color c -> "another Color: " + c;
    default -> "other";
};
```

The result is `"exact constant"`. If `value` is changed to `Color.BLUE`, the `case Color c` branch matches and returns `"another Color: BLUE"`.

By contrast, `case Color c` is **not** a constant label, but a type pattern for the entire type. Inside that branch body you can call `c.name()`, `c.ordinal()`, or other methods of `Color`, because the compiler already knows the static type of `c`.

## 5. Complete Java 21 program: two enums sharing a READY constant

Save all of the code below to a file named **QualifiedEnumCaseDemo.java**.

```java
public class QualifiedEnumCaseDemo {
    enum Color { RED, GREEN, BLUE }

    sealed interface Status permits Pipeline, Ticket {}

    enum Pipeline implements Status { READY, PAUSED }

    enum Ticket implements Status { READY, DONE }

    static String describe(Object value) {
        return switch (value) {
            case null -> "null";

            case Color.RED -> "color:red";
            case Color c -> "color:" + c.name().toLowerCase();

            case Pipeline.READY -> "pipeline:ready";
            case Ticket.READY -> "ticket:ready";

            case Pipeline p ->
                    "pipeline:" + p.name().toLowerCase();
            case Ticket t ->
                    "ticket:" + t.name().toLowerCase();

            default -> "other";
        };
    }

    static String fromEnum(Color color) {
        return switch (color) {
            case Color.RED -> "red";
            case Color.GREEN, Color.BLUE -> "green-or-blue";
        };
    }

    static String fromStatus(Status status) {
        return switch (status) {
            case null -> "no-status";
            case Pipeline.READY -> "pipeline-ready";
            case Ticket.READY -> "ticket-ready";
            case Pipeline p -> "pipeline-other:" + p;
            case Ticket t -> "ticket-other:" + t;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(Color.RED));
        System.out.println(describe(Color.GREEN));
        System.out.println(describe(Pipeline.READY));
        System.out.println(describe(Ticket.READY));
        System.out.println(describe(Pipeline.PAUSED));
        System.out.println(describe(Ticket.DONE));
        System.out.println(describe("READY"));
        System.out.println(describe(null));
        System.out.println(fromEnum(Color.BLUE));
        System.out.println(fromStatus(Ticket.READY));
        System.out.println(fromStatus(Pipeline.PAUSED));
        System.out.println(fromStatus(null));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac QualifiedEnumCaseDemo.java
java QualifiedEnumCaseDemo
```

**Exact output:**

```text
color:red
color:green
pipeline:ready
ticket:ready
pipeline:paused
ticket:done
other
null
green-or-blue
ticket-ready
pipeline-other:PAUSED
no-status
```

Key points to note:

1. **Two enums with the same constant name `READY`:** `Pipeline.READY` selects the `case Pipeline.READY` branch; `Ticket.READY` selects the `case Ticket.READY` branch. These two constants are completely distinct.
2. **Broad selector type `Object`:** `describe(Object value)` accepts `Color`, `Pipeline`, `Ticket`, `String`, and `null`. The enum-qualified case labels still match each constant accurately.
3. **Specific constant before type pattern:** `case Color.RED` appears before `case Color c`; both `Pipeline.READY` and `Ticket.READY` appear before the type patterns for their respective entire enums.
4. **Fallback branches for remaining values:** `case Pipeline p` receives `Pipeline.PAUSED` and `case Ticket t` receives `Ticket.DONE`; these are type patterns, not constant labels.
5. **Multiple constants in a single branch:** `case Color.GREEN, Color.BLUE -> ...` lets two enum constants share the same result when the selector has type `Color`.
6. **Sealed hierarchy:** a selector of type `Status` has only two permitted implementations, `Pipeline` and `Ticket`. `fromStatus` covers both types with type patterns, so no `default` branch is needed.
7. **Difference between string and enum:** `describe("READY")` returns `"other"`; the string `"READY"` is not automatically parsed into `Pipeline.READY` or `Ticket.READY`.
8. **Null:** `case null` is included in `describe` and `fromStatus` to handle a `null` selector explicitly.

## 6. Type compatibility of enum constants with the selector

In a pattern switch, the compiler checks whether a case label can be applied to the selector type.

Valid example with an `Object` selector:

```java
Object value = Color.RED;

String text = switch (value) {
    case Color.RED -> "red";
    default -> "other";
};
```

Similarly, the `Status` selector in the program above can match `Pipeline.READY` and `Ticket.READY`, because both enums implement `Status`.

**Invalid example:** if the selector definitely has type `String`, placing the enum constant `Color.RED` in a `case` is incompatible:

```java
// Compilation error: Color cannot be converted to String.
// static String wrong(String value) {
//     return switch (value) {
//         case Color.RED -> "red";
//         default -> "other";
//     };
// }
```

This is a **type** error, not merely "this branch has no runtime data to execute." Java catches it immediately at compile time. You should not widen a selector to `Object` just to hide a design flaw; choose the input type and case labels that match the domain meaning.

**Watch out for `enum.name()` and strings:** if the input is a `String`, `case "RED"` only matches a string. To intentionally convert a string into an enum constant, you can use `Color.valueOf(text)` with `IllegalArgumentException` handling for invalid names, and then switch on the `Color` value. `valueOf` is case-sensitive and is not an implicit part of case matching.

## 7. Case ordering and dominance errors

Case labels are checked by the compiler for dominance, meaning a broader branch placed earlier can make a later branch **unreachable**.

**Incorrect** example:

```java
// Wrong: case Color.RED is dominated by the Color c pattern above.
// static String wrongOrder(Object value) {
//     return switch (value) {
//         case Color c -> "any Color";
//         case Color.RED -> "red";
//         default -> "other";
//     };
// }
```

Even though `Color.RED` is very specific, it appears **after** a type pattern that matches every `Color` constant, so the compiler reports that the `Color.RED` branch is dominated.

Correct approach:

```java
static String correctOrder(Object value) {
    return switch (value) {
        case Color.RED -> "red";
        case Color c -> "another color";
        default -> "other";
    };
}
```

For `Color.RED`, this returns `"red"`; for `Color.BLUE`, it returns `"another color"`. Place **constants needing special handling** before the type pattern that covers the entire enum.

This ordering rule also applies when using `case Object obj`: if you place a type pattern covering all non-`null` selector values before enum constants, the subsequent enum labels can be shadowed/dominated. Whether each branch should exist must be decided from the selector's value domain and the desired matching order.

## 8. Combining multiple enum constants in a single case

When multiple constants of the **same selector type** need the same action, you can write a label with multiple comma-separated constants:

```java
static String bucket(Color color) {
    return switch (color) {
        case Color.RED -> "warm";
        case Color.GREEN, Color.BLUE -> "other";
    };
}
```

For `Color.RED` this returns `"warm"`; for `Color.GREEN` or `Color.BLUE` it returns `"other"`. Grouping them this way clearly expresses that these constants enter the same branch.

In a switch with an `Object` selector, constants from multiple enums can be handled in appropriate cases under Java 21's case label rules, though it is usually better to keep constants with different domain meanings separate. Avoid grouping too many values together in a way that makes permission checks or state transitions hard to read.

The difference between **multiple constants in one branch** and **multiple patterns of different types** is worth noting: in the example above, all labels are enum constants and declare no pattern variable; if you need to bind the matched value to call methods on it, use a separate type pattern branch, such as `case Color c -> ...`.

## 9. Null and default do not replace each other

An enum constant is non-`null`, so neither `case Color.RED` nor `case Color c` handles a `null` selector value in normal usage.

```java
static String maybeColor(Object value) {
    return switch (value) {
        case null -> "missing";
        case Color.RED -> "red";
        case Color c -> "another color";
        default -> "not a Color";
    };
}
```

- `maybeColor(null)` returns `"missing"`.
- `maybeColor(Color.RED)` returns `"red"`.
- `maybeColor(Color.GREEN)` returns `"another color"`.
- `maybeColor("RED")` returns `"not a Color"`.

If you omit `case null`, `default` **does not automatically catch null** under Java 21's switch rules for reference types: the switch can throw `NullPointerException` before entering `default`.

When the selector has an enum type, listing all constant labels such as `case Color.RED`, `case Color.GREEN`, `case Color.BLUE` can make a switch expression exhaustive for non-`null` values; it does not turn `null` into an enum constant. If `null` is a valid state in your application, handle it deliberately.

## 10. Qualified constants and the `when` guard

An enum constant label is a **constant case label**, not a pattern that declares a variable. In Java 21, you cannot write a `when` guard directly after a single constant:

```java
// Syntax error: when cannot be attached directly to a constant label.
// case Color.RED when enabled -> "red and enabled";
```

The `when` guard is for **pattern case labels**. When you need to combine an enum value with an external condition, you can use a type pattern and a guard:

```java
static String classify(Object value, boolean enabled) {
    return switch (value) {
        case Color c when c == Color.RED && enabled ->
                "red enabled";
        case Color.RED -> "red disabled";
        case Color c -> "other color";
        default -> "other";
    };
}
```

For `classify(Color.RED, true)` this returns `"red enabled"`; for `classify(Color.RED, false)` it returns `"red disabled"`.

Here `c` has static type `Color` and is in scope within the `when` expression. The guard is evaluated after the `Color c` type pattern matches. When the guard is false, Java continues checking subsequent branches. This is a clear way to express a dynamic condition combined with an enum constant without assuming that a constant label has its own pattern variable.

If the condition is only used to distinguish two specific values, you can check it inside the case body instead of using `when`. Choose the form that is easiest to read and keeps branch ordering consistent.

## 11. Exhaustiveness when enums and sealed interfaces are selectors

**Exhaustiveness** is the requirement that the compiler verify a switch expression handles all possible selector values allowed by its static type. Qualified enum constants can contribute to coverage.

### Selector with an enum type

```java
static String allColors(Color color) {
    return switch (color) {
        case Color.RED -> "R";
        case Color.GREEN -> "G";
        case Color.BLUE -> "B";
    };
}
```

Because `Color` in this example has exactly three constants and all three are listed, the switch expression is exhaustive without `default`. If a new constant is added to the enum later and the code is recompiled, the compiler can require handling the additional branch, helping catch omissions early.

### Selector with an interface type

With `Status` as a sealed interface implemented by `Pipeline` and `Ticket`, listing only a few constants such as `Pipeline.READY` or `Ticket.READY` does **not** cover every value. `Pipeline.PAUSED` and `Ticket.DONE` still remain.

The complete approach, as used in the main program:

```java
static String handle(Status status) {
    return switch (status) {
        case Pipeline.READY -> "pipeline-ready";
        case Ticket.READY -> "ticket-ready";
        case Pipeline p -> "pipeline:" + p.name();
        case Ticket t -> "ticket:" + t.name();
    };
}
```

The last two type patterns cover the remaining constants of each enum, so the switch expression is exhaustive for non-`null` `Status` values. For a `null` selector, the switch in this example can still throw `NullPointerException` because no `case null` is declared.

If the selector has a broad type like `Object`, listing enum constants only covers a tiny fraction of possible object types. You will usually need `default` or an appropriate catch-all pattern to cover the remaining cases.

## 12. Common mistakes

| Mistake / misconception | Cause | How to fix |
| --- | --- | --- |
| Using `case Color.RED` and compiling with `--release 17`. | Java 17 does not have this Java 21 qualified enum case syntax. | Use JDK 21+ or a classic enum switch with `case RED` when the selector has type `Color`. |
| Using `case READY` in a switch on `Object` without specifying which enum. | The selector does not provide a single enum type to resolve the constant. | Use `case Pipeline.READY`, `case Ticket.READY` with a compatible selector type. |
| Thinking `Pipeline.READY` and `Ticket.READY` are the same constant because both are named `READY`. | Confusing constant name with constant identity. | Use a qualifier to specify the owning enum; the two constants are distinct. |
| Placing `case Color c` before `case Color.RED`. | The broader type pattern dominates the specific constant after it. | Place `case Color.RED` before `case Color c`. |
| Using `case Color.RED` in a switch on a `String` selector. | The enum type is incompatible with the selector type. | Fix the type model or switch on a validly parsed enum value. |
| Assuming `case Color.RED` automatically declares a variable `RED`. | A constant label does not declare a pattern variable. | Use `case Color c` if you need a variable `c`. |
| Writing `case Color.RED when enabled`. | `when` cannot be attached directly to this kind of constant label. | Use `case Color c when c == Color.RED && enabled`. |
| Thinking `default` handles a `null` selector. | In a Java 21 switch over reference types, `null` requires explicit handling. | Add `case null` when you want to accept null. |
| Listing only some enum constants in a switch expression without an additional branch. | Missing exhaustiveness. | List all constants or add a branch covering the rest. |
| Comparing the string `"RED"` with an enum via a case label. | `String` and enum are two different data types. | Convert the string to an enum with error checking if actually needed. |

One note on extensibility: if the program adds a new enum implementing the `Status` interface, the `sealed interface` declaration itself and the switch branches will also need to be reviewed. Qualified constants make the code clearer, but you must still keep the model of allowed states consistent.

## 13. Self-check exercises

### Exercise 1: Which constant matches?

Given the declarations:

```java
enum A { READY, WAITING }
enum B { READY, DONE }
Object input = B.READY;
```

With:

```java
String result = switch (input) {
    case A.READY -> "A";
    case B.READY -> "B";
    default -> "other";
};
```

**Answer:** `"B"`. `A.READY` and `B.READY` are two distinct constants even though both are named `READY`.

### Exercise 2: Why does this fail to compile?

```java
// Assume Color has already been declared.
static String check(Object input) {
    return switch (input) {
        case Color c -> "color";
        case Color.RED -> "red";
        default -> "other";
    };
}
```

**Answer:** `case Color.RED` is dominated by `case Color c` before it. To have the `RED` branch run separately, place the specific constant before the type pattern.

### Exercise 3: Fill in the missing branch

Given:

```java
enum Mode { AUTO, MANUAL, OFF }

static String description(Mode mode) {
    return switch (mode) {
        case Mode.AUTO -> "automatic";
        case Mode.MANUAL -> "manual";
    };
}
```

**Answer:** The switch expression is missing `Mode.OFF`. Add `case Mode.OFF -> "off";` or a branch that properly covers the remaining cases. If `mode == null`, covering all three constants does not prevent a `NullPointerException` when `null` handling is missing.

### Exercise 4: Predict the main program output

From the `QualifiedEnumCaseDemo` program:

- What does `describe(Pipeline.PAUSED)` return? **`"pipeline:paused"`**.
- What does `describe("READY")` return? **`"other"`**.
- What does `fromEnum(Color.BLUE)` return? **`"green-or-blue"`**.
- What does `fromStatus(null)` return? **`"no-status"`**.

Explanation: each result depends on the selector's type and value, case ordering, and the presence of `case null`; a string that looks like an enum constant name does not produce a match.

## 14. Key takeaways

A **qualified enum constant** has the form **`EnumType.CONSTANT`**. Starting in Java 21, it can be used in `case` labels of a pattern switch with a broad selector type such as `Object` or a compatible interface. This syntax is especially useful when multiple enums share the same constant names or when a switch handles a mix of data types.

Remember four principles when designing case labels:

1. **Match specific values:** `case Color.RED` is for the exact `Color.RED` constant; `case Color c` is a type pattern matching any non-`null` `Color` constant.
2. **Types must be compatible:** the compiler checks the constant's enum type against the selector's static type, so not every enum constant can be placed in every switch.
3. **Order matters:** place specialized constant labels before type patterns that cover them to avoid dominance.
4. **Explicit coverage and null handling:** switch expressions must be exhaustive; `default` does not automatically replace `case null`.

Official documentation:
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS Java SE 21 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS Java SE 21 — The switch Expression](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
