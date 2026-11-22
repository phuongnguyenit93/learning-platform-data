# Multiple Patterns in the Same Java `switch` Branch

## 1. "Multiple patterns in the same branch" can mean three different things

In Java, a `switch` chooses how to handle execution based on the value of the **selector** (the expression in `switch (...)`). A branch is identified by a `case` label; a label can contain **constants** or **patterns**, depending on the syntax and Java version.

When you want multiple cases to perform the same action, you need to distinguish between:

1. **Multiple constants in a single `case` label**, for example `case "N", "NORTH" -> ...`. This is the way to group constants that Java already supports as a stable feature.
2. **Multiple `case` labels sharing one `:` statement group**, for example `case Ping(): case Pong(): ... break;`. In Java 21, this is valid for record patterns that do not declare pattern variables.
3. **Multiple comma-separated patterns directly within the same `case` label**, for example `case Ping(), Pong() -> ...`. This is an extended syntax in **Java 23–26 preview** releases; it is **not part of standard Java 21**. With this preview syntax, the grouped patterns **must not declare pattern variables**.

Regardless of how it is written, each selector value leads to the action of the matching branch according to `switch` rules. "Merging branches" means the cases share a **common action**, not that all patterns are evaluated successfully together or that multiple branches execute together.

**Version milestones:** pattern matching for `switch` has been an official feature since **Java 21** (JEP 441). Extending `case` labels to support a list of multiple patterns in the same label was introduced in the preview series of JEP 455 (Java 23), JEP 488 (Java 24), JEP 507 (Java 25), and JEP 530 (Java 26). The Java 21 program section below uses **stable** syntax, while the example of a multi-pattern list in a single label is separated and requires enabling preview.

## 2. Multiple constants sharing a branch: different from multiple patterns

With a `String`, multiple constants can share one `->` rule:

```java
static String direction(String word) {
    return switch (word) {
        case "N", "NORTH" -> "UP";
        case "S", "SOUTH" -> "DOWN";
        case null, default -> "UNKNOWN";
    };
}
```

This is an **illustrative method** placed inside a Java 21 class. `direction("N")` and `direction("NORTH")` both return `"UP"`; `direction("SOUTH")` returns `"DOWN"`; `direction(null)` returns `"UNKNOWN"`.

The values `"N"` and `"NORTH"` are **case constants**, not patterns. The compiler compares the selector against the constants in the group and then executes only **one branch**.

Similarly, with an `int` selector you can write `case 1, 2, 3 -> ...`. You must not take an example of grouping constants for a `String` or `int` selector and assume those constants are valid for any `Object` selector: the selector type and the constant types must still satisfy the compatibility rules of `switch`.

### `case null, default` is a special form of grouping

```java
return switch (value) {
    case String text -> "TEXT: " + text;
    case null, default -> "OTHER";
};
```

This is an **illustrative snippet inside a method returning `String`** with a selector `value` of type `Object`. The `case null, default` branch handles both a `null` selector and all remaining values that do not match the preceding branches.

**Limitation:** Java 21 allows combining `null` with `default` using this syntax, but it does **not** allow combining `case null, String text -> ...`. That is not a safe way to declare the variable `text` for a `null` value.

## 3. Java 21: multiple record patterns without variable declarations in the same `:` group

A **record pattern** such as `Ping()` or `Pong()` can test whether an object belongs to the corresponding record type. If the record has no components, the pattern does not need to declare any variables.

```java
record Ping() {}
record Pong() {}

static String grouped(Object value) {
    String result;

    switch (value) {
        case Ping():
        case Pong():
            result = "SIGNAL";
            break;

        case null:
            result = "NULL";
            break;

        default:
            result = "OTHER";
    }

    return result;
}
```

The record declarations and method above are **illustrative code placed inside a class**. The `switch` syntax is valid in Java 21:

- The `case Ping():` label checks for a `Ping` record.
- The `case Pong():` label checks for a `Pong` record.
- Both labels are attached to the same statement group `result = "SIGNAL"; break;`. If the value matches **either one**, the same code block runs.
- `break` prevents execution from continuing into the next `case` statement group.
- Neither pattern in this group declares a variable that needs to be initialized. That is why they can safely share a statement group.

This is called a **switch-labeled statement group** with `:`. It is different from a **switch rule** with `->`. In Java 21, you cannot replace the block above with `case Ping(), Pong() -> "SIGNAL";` and expect Java 21 source level to accept it; the comma-separated multi-pattern list syntax belongs to newer preview extensions.

### Why is grouping multiple labels containing pattern variables invalid?

Trying to write:

```java
// INTENTIONALLY INVALID example, does not compile:
switch (value) {
    case String text:
    case Integer number:
        System.out.println(text); // If value is Integer, text is not bound.
        break;
    default:
        break;
}
```

If the selector is `Integer`, control flow could enter the shared statement group via the `case Integer number:` label, leaving the `text` variable from the `String text` label uninitialized. Java prevents falling into a statement group containing an unbound pattern variable. This is a **variable safety and scoping** restriction, not merely because the type names are different.

With the `:` syntax, you must also avoid a statement group **falling through** to a subsequent label that declares a pattern variable without having performed the match. When patterns have variables, using separate `->` branches is usually easier to read and less error-prone.

## 4. Java 21: what to do when multiple patterns have variables and the same action?

Suppose you want to handle both `String` and `Integer` with shared normalization logic. The following syntax is **invalid** in Java 21:

```java
// Does not compile in Java 21:
return switch (value) {
    case String text, Integer number ->
        "Value: " + value;
    default -> "Other";
};
```

The first problem is that **Java 21 does not have comma-separated multiple case patterns**. Furthermore, even in preview releases that support that syntax, this is still **invalid** because each pattern declares a different variable: in the branch body there would be no guarantee whether `text` or `number` is bound.

### Approach 1 — separate `case` labels, share a handler method

```java
static String format(Object value) {
    return switch (value) {
        case String text -> common(text);
        case Integer number -> common(number);
        case null, default -> "Other";
    };
}

static String common(Object value) {
    return "Value: " + value;
}
```

These are **two illustrative methods in a class**. Each independent branch binds a variable with a clear type, while both call `common(...)`. There is no need to duplicate business logic; `common` accepts `Object`, so it can take either `String` or `Integer`.

In a short example, the result could be built directly from `value`. However, when business logic requires validation, logging, formatting, or service calls, a shared method helps avoid duplicating logic and keeps pattern variable scopes clear.

### Approach 2 — use a common supertype or interface, if appropriate

If multiple classes already implement a common interface with the required behavior, you can use **a single type pattern** for that supertype:

```java
interface Printable {
    String display();
}

static String display(Object value) {
    return switch (value) {
        case Printable printable -> printable.display();
        case null, default -> "Not printable";
    };
}
```

This is an illustrative example placed in a class; declaring the classes that implement `Printable` depends on the application.

A `case Printable printable` handles **every runtime value** that implements `Printable`. If you only want a few subtypes rather than all of them, you need a guard or specific branches; you should not use a broad supertype just to shorten code and accidentally accept unwanted data types.

### Approach 3 — multiple branches with `when` for the same type

```java
static String describe(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "Blank";
        case String text -> "Text: " + text;
        case null, default -> "Other";
    };
}
```

These are **two separate `String text` patterns**, which are allowed to reuse the variable name because their scopes are in different branches. The `when` guard of the first branch is checked after the pattern matches; the second branch handles the remaining strings.

**Order matters:** the branch with the specific guard comes before the general branch. If you put `case String text -> ...` before `case String text when ... -> ...`, the guarded branch below is shadowed and causes a compile-time error (*dominated case label*).

## 5. Complete Java 21 program: grouping multiple labels and reusing actions

Save in the file **`MultiplePatternsInCase.java`**:

```java
public class MultiplePatternsInCase {
    record Ping() {}
    record Pong() {}

    static String grouped(Object value) {
        String result;

        switch (value) {
            case Ping():
            case Pong():
                result = "SIGNAL";
                break;
            case String text:
                result = "TEXT:" + text.toUpperCase();
                break;
            case Integer number:
                result = "INT:" + (number + 1);
                break;
            case null:
                result = "NULL";
                break;
            default:
                result = "OTHER";
        }
        return result;
    }

    static String shared(Object value) {
        return switch (value) {
            case String text -> handle(text);
            case Integer number -> handle(number);
            case null, default -> "OTHER";
        };
    }

    static String handle(Object value) {
        return "SHARED:" + value;
    }

    static String direction(String word) {
        return switch (word) {
            case "N", "NORTH" -> "UP";
            case "S", "SOUTH" -> "DOWN";
            case null, default -> "UNKNOWN";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
            new Ping(), new Pong(), "java", 4, null, 3.5
        };

        for (Object input : inputs) {
            System.out.println(grouped(input));
        }

        System.out.println(shared("abc"));
        System.out.println(shared(12));
        System.out.println(shared(null));

        System.out.println(direction("N"));
        System.out.println(direction("SOUTH"));
        System.out.println(direction(null));
    }
}
```

Compile with the **Java 21** language level:

```bash
javac --release 21 MultiplePatternsInCase.java
java MultiplePatternsInCase
```

Exact stdout:

```text
SIGNAL
SIGNAL
TEXT:JAVA
INT:5
NULL
OTHER
SHARED:abc
SHARED:12
OTHER
UP
DOWN
UNKNOWN
```

Output explanation:

- `Ping` and `Pong` match the two record pattern labels without variable declarations and then execute the **same statement group** `result = "SIGNAL"`.
- `"java"` goes through the `String text` branch, calls `toUpperCase()`, and returns `TEXT:JAVA`.
- The number `4` is autoboxed into `Integer` when placed into `Object[]`, and the `Integer number` branch adds 1 to produce `INT:5`.
- `null` is handled in `case null:`, while `3.5` is a `Double` and goes to `default`.
- `shared("abc")` and `shared(12)` call the **same method** `handle` from two independent pattern branches, returning `SHARED:abc` and `SHARED:12`.
- `direction("N")` and `direction("SOUTH")` illustrate grouping **constants** with commas. `direction(null)` enters `case null, default`.

This entire section uses **official Java 21** syntax, without needing `--enable-preview`.

## 6. Multiple patterns in a single `case` label: newer Java preview releases

The preview releases for primitive patterns and `switch` from **Java 23 through Java 26** add the form:

```java
case PatternA, PatternB -> sharedAction;
```

A simple use case is grouping record patterns **without variable declarations**:

```java
case Ping(), Pong() -> "SIGNAL";
```

In this example, `Ping()` and `Pong()` are two record patterns, each with an empty record structure and **no bound variables**. If the selector matches either one, the same `->` rule is selected. This is a concise syntax corresponding to the two labels `case Ping(): case Pong():` in the Java 21 program.

### Standalone runnable example with JDK 24, preview enabled

Create the file **`MultiCasePreview24.java`**:

```java
public class MultiCasePreview24 {
    record Ping() {}
    record Pong() {}

    static String describe(Object value) {
        return switch (value) {
            case Ping(), Pong() -> "SIGNAL";
            case String text -> "TEXT:" + text;
            case null, default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Ping()));
        System.out.println(describe(new Pong()));
        System.out.println(describe("hi"));
        System.out.println(describe(null));
    }
}
```

Compile/run using **JDK 24**, enabling preview features for that version:

```bash
javac --enable-preview --release 24 MultiCasePreview24.java
java --enable-preview MultiCasePreview24
```

Stdout:

```text
SIGNAL
SIGNAL
TEXT:hi
OTHER
```

**Note:** Do not use `javac --release 21` with this example. On a different JDK, preview must be enabled for **that JDK's own language level**; `--enable-preview` does not arbitrarily unlock preview features of older versions. This feature remains in the preview series through Java 26, so prefer stable Java 21 syntax when a project requires long-term compatibility.

### Why can't patterns with variables still be grouped with commas?

Even though preview allows **multiple patterns in one label**, the following example is still rejected:

```java
// INTENTIONALLY INVALID, even with preview enabled:
return switch (value) {
    case String text, Integer number -> "Mixed";
    default -> "Other";
};
```

If `String text` matches, then `number` is unbound; if `Integer number` matches, then `text` is unbound. Because a shared rule must have a consistent variable scope, the preview rules **forbid a list of multiple case patterns from declaring pattern variables**, even when the branch body does not directly use them.

Similarly, two deconstructing record patterns like `case Point(int x, int y), Pair(int a, int b) -> ...` are also invalid because each subpattern declares variables. Do not infer from `case Ping(), Pong()` being valid that every record pattern can be grouped this way.

### Distinguishing `case null, default` from a pattern list

`case null, default -> ...` is a **special label pair** stably supported in Java 21; it does not mean `null` is a pattern that can be placed arbitrarily in a list. The syntax `case null, String text -> ...` is not allowed, even in the preview versions mentioned above. Handle `null` explicitly or use the `null, default` pair when the two cases genuinely need the same action.

## 7. Limitations of `switch` when multiple conditions could match

### Only one matching branch is chosen per evaluation

When multiple labels could match a value, Java evaluates them according to `switch` matching rules and label order. **It does not run a branch for every matching pattern**. With `->` rules, there is no fall-through to the next rule.

Illustrative example:

```java
return switch (value) {
    case String s when s.isBlank() -> "Blank";
    case String s -> "Text";
    case null, default -> "Other";
};
```

If `value` is an empty string, the `Blank` branch is chosen and `Text` does not run. If `value` is `"ok"`, the guard is false, so the `Text` branch is chosen.

### Detecting shadowed branches (*dominance*)

**Invalid** example:

```java
return switch (value) {
    case CharSequence sequence -> "Sequence";
    case String text -> "Text"; // Dominated by the branch above.
    case null, default -> "Other";
};
```

`String` is a subtype of `CharSequence`, so the `String` branch can never be chosen after an unguarded `CharSequence` branch. The compiler rejects dominated branches. Place specific branches before general ones, or remove the redundant branch if the handling purpose is the same.

### A `switch` expression must be exhaustive

With a selector of type `Object`, listing only `String` and `Integer` does not cover other types. In a `switch` expression, you must add `default`, `case null, default`, or a set of labels proven exhaustive by the compiler, such as on an appropriate sealed hierarchy.

**Type exhaustiveness does not mean `null` is automatically handled.** If `null` can be received, explicitly choose `case null` or `case null, default`. Do not expect a regular `default` branch to always catch a `null` selector in a pattern switch.

## 8. Summary table of rules by version

| Syntax | Standard Java 21 | Java 24 with preview enabled | Meaning |
| --- | --- | --- | --- |
| `case "A", "B" -> ...` with `String` selector | Valid | Valid | Multiple **constants**, one rule |
| `case null, default -> ...` | Valid | Valid | Groups `null` and fallback branch |
| `case Ping(): case Pong(): ... break;` | Valid | Valid | Two **case labels**, one `:` statement group |
| `case Ping(), Pong() -> ...` | Not supported | Valid with preview | Two **patterns** without variable declarations in the same label |
| `case String s, Integer i -> ...` | Not supported | Compile error | Pattern lists with variables are not allowed |
| `case String s -> common(s); case Integer i -> common(i);` | Valid | Valid | Two independent pattern branches calling a shared method |
| `case null, String s -> ...` | Compile error | Compile error | Not an allowed label combination |

The table above assumes the necessary types and declarations exist, the selector is compatible, no branch is dominated, and the `switch` body satisfies exhaustiveness requirements.

## 9. Common mistakes and how to fix them

**Mistake 1 — confusing grouping constants with grouping patterns:** `case "A", "B"` has multiple constants, which does not prove `case String s, Integer i` is valid. Check whether **each part in the label is a constant or a pattern** and whether it declares a variable.

**Mistake 2 — using commas with two record patterns in a Java 21 project:** `case Ping(), Pong() ->` belongs to newer preview syntax. Use consecutive `:` labels with `break`, or split into two `->` rules calling a shared method.

**Mistake 3 — grouping cases with pattern variables into one statement group:** if a variable is only initialized for one specific label, the shared group could be entered from another label. The safe approach is for **each branch to bind its own variable and call a shared handler function**.

**Mistake 4 — forgetting `break` in a `case:` group:** without `break`, control flow can continue into the next group. For pattern cases with variables, the compiler also enforces rules blocking unsafe fall-through. With `->` rules, Java does not fall through.

**Mistake 5 — placing a general branch before a specific branch:** `case CharSequence c` before `case String s` dominates the `String` branch. Order specific branches first, or use a targeted guard.

**Mistake 6 — ignoring `null` and exhaustiveness:** a `switch` expression on `Object` needs to cover other types and should handle `null` explicitly; `default` does not mean every data type including `null` is handled as expected.

**Mistake 7 — confusing preview features with standard features:** code running on a newer JDK with preview enabled does not prove it will compile under `--release 21`. Always check the project's source configuration and compile/runtime flags.

## 10. Self-check

**Exercise 1.** In Java 21, is a `switch` expression with `case "GET", "HEAD" -> "READ";` on a `String` selector valid?

**Answer:** Yes. These are multiple `String` constants in the same label, not multiple patterns. The `READ` branch is chosen if the selector equals either constant.

**Exercise 2.** In Java 21, how can `Ping()` and `Pong()` both print `"SIGNAL"` without declaring variables?

**Answer:** Use two labels `case Ping(): case Pong():` attached to a shared statement group containing `System.out.println("SIGNAL"); break;`. This is stable syntax in Java 21.

**Exercise 3.** In JDK 24 with preview enabled, can `case Ping(), Pong() -> ...` be used?

**Answer:** Yes, provided the two record patterns do not declare variables, the selector is compatible, and it is not dominated by a preceding branch. You must use JDK 24's source level and preview flags; do not write this syntax and compile it as standard Java 21.

**Exercise 4.** Why is `case String s, Integer i -> ...` invalid, even if both branches want to call a shared function?

**Answer:** A single branch cannot assume both `s` and `i` exist at the same time. Preview versions that support multi-pattern lists still forbid declaring pattern variables in the list. Split it into `case String s -> common(s);` and `case Integer i -> common(i);`.

**Key takeaway:** *Multiple cases sharing one action* is the goal; how you express it depends on **constants vs. patterns**, **whether variables are declared**, and **the Java version**. For Java 21, prefer separate pattern rules calling a shared method or grouping variable-free labels in a switch statement. For newer Java preview versions, a comma-separated list of multiple patterns is more concise when **no pattern variables need to be bound**.

## Official references

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — §14.11, Switch Statement and switch labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JEP 488 — Primitive Types in Patterns, instanceof, and switch (Second Preview, Java 24)](https://openjdk.org/jeps/488).
- [Oracle Java 26 — JEP 530 Fourth Preview specification](https://docs.oracle.com/en/java/javase/26/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html).
