# Pattern Matching in `switch` Statements (Java 21+)

## 1. Overview: `switch` Is No Longer Just for Constants

In traditional versions of Java, `switch` typically branched on `int`, `String`, or `enum` constants. **Pattern matching for switch**, finalized in **Java 21 (JEP 441)**, extends this mechanism: `case` labels can check the **type and structure** of a value at runtime while declaring strongly typed **pattern variables**.

Minimal example:

```java
static void describe(Object value) {
    switch (value) {
        case null -> System.out.println("No value");
        case String text -> System.out.println("Text: " + text.toUpperCase());
        case Integer number -> System.out.println("Integer: " + number);
        default -> System.out.println("Another type");
    }
}
```

When `"java"` is passed, `case String text` matches, Java creates the `text` variable of type `String`, and it prints `Text: JAVA` **without needing a cast**. When `42` is passed, the `Integer number` branch runs. `null` has its own branch.

In this snippet:

- `switch (value)` is a **switch statement**: it executes statements and does not directly produce a value to assign or `return`.
- `case String text` is a **type pattern**: it checks the runtime type and binds the object to the variable `text` if it matches.
- `->` defines a **switch rule**: when the rule is selected, only that branch runs and control leaves the `switch` normally, **with no automatic fall-through** to the next branch.
- `default` handles **non-null** values that do not match any preceding branch. `null` does not automatically match `default`.

Pattern matching syntax for `instanceof` has been stable since Java 16; **pattern matching in `switch`** only became final in **Java 21**. The standalone runnable examples below use JDK 21 or later, with no preview flags required.

## 2. Two `switch statement` Syntaxes: `->` and `:`

Java supports two ways to structure the body of a `switch`.

### 2.1. Switch Rules Using the Arrow `->` (Preferred)

```java
switch (value) {
    case String s -> System.out.println("Length = " + s.length());
    case Integer n -> System.out.println("Number = " + n);
    default -> System.out.println("Other");
}
```

The `String` branch runs only when the object matches type `String`; after printing, it does not execute the body of the `Integer` branch. Therefore, no `break` is needed after each branch.

The right-hand side of `->` in a **switch statement** can be:

1. A valid **statement expression**, such as a `System.out.println(s)` call, an assignment, or an increment operation;
2. A **block** `{ ... }` when multiple statements are needed;
3. A **`throw` statement**.

Block example:

```java
case String s -> {
    String normalized = s.trim();
    System.out.println("Normalized: " + normalized);
    System.out.println("Length: " + normalized.length());
}
```

This is a **code snippet inside a switch**, not a standalone program. The variable `s` matched by the `case` label is in scope throughout the entire block of that rule.

### 2.2. Switch-Labeled Statement Groups Using the Colon `:`

```java
switch (value) {
    case String s:
        System.out.println("Text: " + s);
        break;
    case Integer n:
        System.out.println("Integer: " + n);
        break;
    default:
        System.out.println("Other");
}
```

This is the syntax for **statement groups** under `case` labels. Unlike `->`, groups using `:` can continue executing statements in the next group if no appropriate terminating statement is encountered (*fall-through*). With **pattern variables**, Java enforces rules to **prevent falling through into a label that declares an uninitialized pattern variable**.

Both forms can use pattern matching starting in Java 21, but **you cannot mix `->` switch rules and `:` labeled statement groups in the same switch block**.

### 2.3. Distinguishing a Switch Statement from a Switch Expression

A **switch statement** is used to execute actions:

```java
switch (value) {
    case String s -> System.out.println(s);
    default -> System.out.println("Other");
}
```

A **switch expression** produces a value:

```java
String result = switch (value) {
    case String s -> "Text: " + s;
    case null -> "(null)";
    default -> "(other)";
};
System.out.println(result);
```

In a switch expression, the RHS can be a value-producing expression or a block using `yield` to return the value of the entire switch expression. In a switch statement, the RHS is a **statement**, and not every Java expression is valid as a standalone statement. The following example **does not compile** when placed in a switch statement:

```java
// INVALID in a switch statement:
// case String s -> "Text: " + s;
```

String concatenation `"Text: " + s` is not a *statement expression*. If you want to use it as a result, place it in a switch expression or pass it to a call such as `System.out.println(...)`.

**Do not use `yield` to "return a result" from a switch statement**: that is the job of a switch expression. Inside a switch statement, you can assign to an outer variable, call a method, `return` from the enclosing method, or `throw` an exception.

## 3. Type Patterns: Handling Different Runtime Types

A `switch` with an `Object` selector can branch based on the actual runtime type of the value:

```java
static void printKind(Object value) {
    switch (value) {
        case null -> System.out.println("null");
        case String s -> System.out.println("String length: " + s.length());
        case Integer n -> System.out.println("Integer: " + n);
        case Number n -> System.out.println("Number: " + n.doubleValue());
        default -> System.out.println("Other");
    }
}
```

You do not need to use `new Integer` directly; if you call `printKind(7)`, Java *autoboxes* the argument to `Integer`, and the `Integer n` branch matches. If you call `printKind(2.5)`, the argument is boxed to `Double`; it does not match `Integer`, but it matches `Number`.

The pattern variables `s` and `n` have **the exact static type of their pattern**, so you can directly call `s.length()` or `n.doubleValue()`. The variable `n` in the `Integer` and `Number` branches represents **two independent declarations**, not a single shared variable.

### 3.1. Subclass/Superclass Ordering Matters

`Integer` is a subclass of `Number`. If you write:

```java
// INVALID when placed in the same switch:
case Number n -> System.out.println(n);
case Integer i -> System.out.println(i); // Completely dominated by the Number branch.
```

`case Number n` already matches every value of type `Integer`; the subsequent `case Integer i` label has no chance of ever being selected, so Java reports a **dominated case label** at compile time.

Valid ordering:

```java
case Integer i -> System.out.println("Integer " + i);
case Number n -> System.out.println("Other Number " + n);
```

These are **two case label snippets inside a switch**, not a standalone program. Similarly, `case CharSequence cs` must appear **after** `case String s` if you want to handle `String` specifically, because `String` implements `CharSequence`.

### 3.2. Generics and Array Types

You can check a generic container at the **reifiable type** level:

```java
case java.util.List<?> items ->
        System.out.println("List size = " + items.size());
case int[] numbers ->
        System.out.println("Array size = " + numbers.length);
```

`List<?>` only indicates that the object is a `List`; it does not verify that all elements are `String` or any other specific type. If needed, iterate over the elements and check `item instanceof String text`. With an `Object` selector, you cannot replace `List<?>` with `List<String>` and expect the JVM to check generic type arguments: Java generics use *type erasure*.

An `int[]` array has a known array type at runtime, so a type pattern can be used for it directly.

## 4. `when` Guards: Selecting Branches with Additional Conditions

A **guarded case label** has the syntax:

```java
case String text when text.isBlank() -> System.out.println("Blank");
```

The check executes in this order:

1. Java checks whether the selector matches `String text`;
2. If it matches, the variable `text` is initialized with type `String`;
3. Java then evaluates the boolean expression after `when`;
4. If the guard evaluates to `true`, the RHS executes; if `false`, testing continues with the next matching label.

Because of this, `text` can be used **directly inside `when`**:

```java
switch (value) {
    case null -> System.out.println("null");
    case String s when s.isBlank() ->
            System.out.println("Blank string");
    case String s when s.length() >= 5 ->
            System.out.println("Long text: " + s);
    case String s ->
            System.out.println("Short text: " + s);
    default -> System.out.println("Not text");
}
```

Pay attention to **ordering**: the unguarded `case String s` rule must come **after** the guarded `String` branches. If `case String s` were placed first, it would match all `String` values and dominate the specialized branches below it.

You can declare the same name `s` across multiple rules because **each rule has its own pattern variable scope**. Java does not "reuse" the `s` variable declared in an earlier rule.

Use `when` when the extra condition is part of the **case selection criteria**, such as a blank string, a positive age, or a record with a special value. Use `if` inside the RHS when you only want to branch **after the case has already been selected**.

**Note:** The guard is evaluated after the pattern matches. It can call methods on the pattern variable, but if the guard itself throws an exception, that exception does not mean "the guard is false"; the `switch` statement completes abruptly with that exception.

## 5. `null`: Does Not Automatically Match `default` or Type Patterns

This is an important rule in Java 21:

```java
static void showNull(Object value) {
    switch (value) {
        case null -> System.out.println("null");
        case String s -> System.out.println(s);
        default -> System.out.println("Other");
    }
}
```

- If `value == null`, the `case null` branch is selected.
- `case String s` **does not match `null`**.
- If there is no label handling `null` and the selector is `null`, `switch` throws `NullPointerException` **even when `default` is present**.
- If you do not need to separate `null` from unmatched types, Java 21 allows the special label `case null, default -> ...`.

Do not write:

```java
// DOES NOT COMPILE:
// case null, String s -> System.out.println(s);
```

Java does not allow combining a `null` label with a type pattern like that. Separate them into `case null` and `case String s`, or use the `case null, default` combination when you genuinely want shared handling for `null` and all other values.

## 6. `switch` Statements with Patterns Must Be Exhaustive

According to **JLS 21 §14.11.2**, an **enhanced switch statement** must be *exhaustive* (covering all values of the possible types being switched on).

A `switch` statement is considered enhanced when:

- The selector has a type other than the traditional types `char`, `byte`, `short`, `int` (and their corresponding wrappers), `String`, or `enum`; **or**
- It has a `case` label that is a **pattern** or `null`.

Therefore, this example **does not compile** on Java 21:

```java
static void incomplete(Object value) {
    switch (value) {
        case String s -> System.out.println(s);
        // ERROR: missing coverage for the remaining Object types.
    }
}
```

A simple fix is:

```java
static void complete(Object value) {
    switch (value) {
        case String s -> System.out.println(s);
        default -> System.out.println("Other");
    }
}
```

`default` provides the missing branch for non-`null` values. If the value is actually `null`, `complete(null)` still throws `NullPointerException` because there is no `case null`. **Type exhaustiveness does not mean `null` is automatically handled.**

### 6.1. When `default` Is Not Needed: Sealed Hierarchies

When the selector has a `sealed` type, the compiler knows all permitted subtypes and can verify that the branches are exhaustive:

```java
sealed interface Shape permits Circle, Square {}

record Circle(double radius) implements Shape {}

record Square(double side) implements Shape {}

static void printShape(Shape shape) {
    switch (shape) {
        case Circle c -> System.out.println("Circle: " + c.radius());
        case Square s -> System.out.println("Square: " + s.side());
    }
}
```

This is an **illustrative snippet**: place the declarations in a valid Java file with appropriate access modifiers. `Circle` and `Square` are the two permitted subtypes of `Shape`, so the `switch` statement is considered exhaustive for all non-`null` values of the `Shape` selector. If `shape == null`, there is no `case null`, so `NullPointerException` is still thrown.

Unlike enhanced `switch` statements, **traditional `switch` statements** that use only constant labels and legacy selector types are allowed to be non-exhaustive for backward compatibility. Do not assume that every `switch` statement in every Java version requires a `default`.

## 7. Scope of Pattern Variables

Pattern variable scope is not the same as a local variable declared at the top of a method. According to JLS 21, for a label `case String s`, the variable `s` is in scope in:

- The `when` guard expression **of that `case` label itself**.
- The expression/statement, block, or `throw` **to the right of `->`** in that switch rule.
- The statement group **attached to the `case String s:` label** when using colon syntax.

It is **not** in scope in another rule, in `default`, or after the entire `switch` simply because it was declared in one branch.

Example:

```java
static void scopeExample(Object value) {
    switch (value) {
        case String text when !text.isEmpty() -> {
            System.out.println(text.toUpperCase()); // Valid.
        }
        case Integer number -> {
            System.out.println(number + 1);
            // System.out.println(text); // ERROR: text is out of scope.
        }
        default -> {
            // System.out.println(number); // ERROR: number is out of scope.
            System.out.println("Other");
        }
    }
    // System.out.println(text); // ERROR: outside the switch.
}
```

In the `Integer number` branch, `text` from the `String` branch is unavailable. Likewise, `number` cannot be used in `default`. You cannot use a branch's pattern variable as shared result storage after the `switch`.

If you need a value **after** the `switch` statement, you can:

- Declare a variable outside the `switch` and assign to it in each branch, ensuring it is definitely assigned before being read;
- Or use a **switch expression** to produce the value and assign it to a result variable.

Example:

```java
static String result(Object value) {
    return switch (value) {
        case null -> "null";
        case String s -> "String(" + s.length() + ")";
        default -> "Other";
    };
}
```

`String s` is only used inside its branch; the method returns the result **without exposing `s` outside its scope**.

## 8. `case ...:` and the Fall-Through Error into an Uninitialized Pattern

The colon `:` normally allows one statement group to fall through into the next if `break` is omitted. However, when the next label declares a pattern variable, a *fall-through* path could reach the next group **without ever matching its label**. Java detects and rejects this at compile time.

**Invalid** example (illustrative only):

```java
switch (value) {
    case String s:
        System.out.println("String: " + s);
        // No break or terminating statement here.
    case Integer n: // ERROR: may fall through into case Integer n.
        System.out.println("Integer: " + n);
        break;
    default:
        System.out.println("Other");
}
```

If `value` is a `String`, execution could continue into the `Integer n` branch where `n` **was never initialized**. The compiler therefore forbids this.

How to fix it: insert `break` where needed, or better yet, use `->`:

```java
switch (value) {
    case String s -> System.out.println("String: " + s);
    case Integer n -> System.out.println("Integer: " + n);
    default -> System.out.println("Other");
}
```

In a `:` `switch` with patterns, **variable scope** is confined to the corresponding group; do not rely on fall-through to pass variables to another branch. When `case` labels contain only traditional constants, Java still permits fall-through under the legacy rules.

## 9. Complete Java 21 Program: Switch Statements with Rules and Groups

Save the file with the exact name **`SwitchStatementPatternDemo.java`**:

```java
import java.util.List;

public class SwitchStatementPatternDemo {
    record Point(int x, int y) {}

    static void inspect(Object value) {
        switch (value) {
            case null -> System.out.println("NULL");

            case String s when s.isBlank() ->
                    System.out.println("BLANK TEXT");

            case String s when s.length() > 5 -> {
                System.out.println("LONG TEXT: " + s
                        + " (" + s.length() + ")");
            }

            case String s -> System.out.println("TEXT: " + s);

            case Integer n when n >= 0 ->
                    System.out.println("NONNEGATIVE INTEGER: " + n);

            case Integer n -> System.out.println("NEGATIVE INTEGER: " + n);

            case Number n -> System.out.println("OTHER NUMBER: " + n);

            case Point(int x, int y) when x == y ->
                    System.out.println("DIAGONAL POINT: " + x);

            case Point(int x, int y) ->
                    System.out.println("POINT: " + x + "," + y);

            case List<?> items -> {
                int strings = 0;
                for (Object item : items) {
                    if (item instanceof String text) {
                        strings++;
                    }
                }
                System.out.println("LIST: " + items.size()
                        + " items, " + strings + " strings");
            }

            default -> System.out.println(
                    "OTHER: " + value.getClass().getSimpleName());
        }
    }

    static void inspectColon(Object value) {
        switch (value) {
            case String s:
                System.out.println("COLON STRING: " + s.toUpperCase());
                break;
            case Integer n:
                System.out.println("COLON INTEGER: " + n);
                break;
            case null:
                System.out.println("COLON NULL");
                break;
            default:
                System.out.println("COLON OTHER");
        }
    }

    public static void main(String[] args) {
        inspect(null);
        inspect("  ");
        inspect("pattern");
        inspect("Java");
        inspect(0);
        inspect(-2);
        inspect(2.5);
        inspect(new Point(3, 3));
        inspect(new Point(2, 5));
        inspect(List.of("A", 5, "B"));
        inspect(true);

        inspectColon("java");
        inspectColon(7);
        inspectColon(null);
        inspectColon(false);
    }
}
```

Run with **JDK 21 or later**, no preview flags needed:

```bash
javac SwitchStatementPatternDemo.java
java SwitchStatementPatternDemo
```

**Standard output:**

```text
NULL
BLANK TEXT
LONG TEXT: pattern (7)
TEXT: Java
NONNEGATIVE INTEGER: 0
NEGATIVE INTEGER: -2
OTHER NUMBER: 2.5
DIAGONAL POINT: 3
POINT: 2,5
LIST: 3 items, 2 strings
OTHER: Boolean
COLON STRING: JAVA
COLON INTEGER: 7
COLON NULL
COLON OTHER
```

**Explanation in execution order:**

1. `inspect(null)` selects `case null`. It does not throw `NullPointerException` because `null` is handled explicitly.
2. `"  "` is a `String` containing only spaces, so the `isBlank()` guard is true; it prints `BLANK TEXT`. `"pattern"` has length 7 and selects the `length() > 5` guard, while `"Java"` goes to the general `case String s`.
3. Both `0` and `-2` are boxed to `Integer`; the `n >= 0` guard separates nonnegative from negative values. `2.5` is a `Double`, which matches `Number n` and prints `OTHER NUMBER: 2.5`.
4. `Point` is a `record` with two components `x` and `y`. **Record patterns** in Java 21 deconstruct those two components into pattern variables `int x` and `int y`. `Point(3, 3)` matches the `x == y` guard; `Point(2, 5)` goes to the remaining `Point` branch.
5. `List.of("A", 5, "B")` matches `List<?> items`; the list has three elements, two of which match `instanceof String text`.
6. `true` is boxed to `Boolean`, which does not match any preceding pattern; `default` prints `OTHER: Boolean`.
7. `inspectColon` uses `case ...:` syntax with `break` to prevent fall-through: it handles `"java"`, `7`, `null`, and any type outside those two groups in turn.

**What this program clearly demonstrates:** pattern variables are bound per matched branch; guards are evaluated after the pattern matches; arrow rules do not fall through; `case null` is a special case; and a `switch` statement can combine both type patterns and record patterns.

## 10. Quick Reference Table

| Situation | Rule in Java 21 |
| --- | --- |
| `case String s -> ...` | Checks type `String`, declares `s` for the rule |
| `case String s when ... -> ...` | Evaluates guard after `String s` matches; `s` is in scope in the guard |
| `case Point(int x, int y) -> ...` | Deconstructs the record and declares variables `x` and `y` |
| `case List<?> list -> ...` | Matches `List`, does not verify individual element types |
| Multiple `case`s sharing name `s` | Valid when they are independent pattern declarations in separate rules |
| `->` in a switch statement | No fall-through; RHS must be a statement expression, block, or `throw` |
| `:` in a switch statement | Can fall through, but cannot fall through **into** an uninitialized pattern variable |
| `case null -> ...` | Catches `null` explicitly; if omitted, a `null` selector throws `NullPointerException` |
| `default` | Catches values not selected by preceding labels; does not replace `case null` |
| Enhanced switch statement | Must be exhaustive; use `default` when patterns do not cover all cases |
| `case Number n` before `case Integer i` | `Integer` is *dominated* and therefore invalid |
| Pattern variable after `switch` | Not in scope outside the branch where it was declared |
| Switch expression | Produces a value; blocks use `yield` to return a result, unlike a switch statement |

## 11. Common Mistakes

### 11.1. Using Pattern Matching for `switch` on JDK 17 Without Preview

`case String s -> ...` in `switch` is a standard feature starting in Java 21. JDK 17 does not support it as a default feature. **JDK 21+ is recommended** for new code following this guide; do not confuse it with pattern matching for `instanceof`, which became standard in Java 17.

### 11.2. Assuming `default` Also Handles `null`

Even when `default` is present, a `null` selector still throws `NullPointerException` if there is no `case null` (or the valid combined label `case null, default`). When an API allows `null`, express the null policy explicitly.

### 11.3. Placing a Superclass Before a Subclass

`case Number n` placed before `case Integer i` dominates the second branch completely. Likewise, an unguarded `String s` branch must come after guarded `String` branches if those guarded branches are meant to run.

### 11.4. Accessing Another Case's Pattern Variable

`String s` in one rule cannot be referenced in `default` or in `case Integer i`. If you need a result after the `switch`, assign to an outer variable or use a switch expression.

### 11.5. Missing `default` When the Selector Is `Object` and Patterns Are Not Exhaustive

Enhanced `switch` statements must be exhaustive. Branches that only catch `String` and `Integer` without `default` typically cause a compile-time error. A `sealed` selector where all permitted subtypes are covered is a useful exception.

### 11.6. Missing `break` in a `:` Statement Group

A `case String s:` group can fall through into the next pattern label and cause a compile-time error if the next branch's variable would be uninitialized. Use `break` or switch to `->` to avoid this error.

### 11.7. Writing a Plain Expression on the RHS of a Switch Statement

Not every expression is valid standing alone as a statement. `"Text " + s` is not a statement expression. Use `System.out.println(...)`, an assignment, a block, or a switch expression if you want to produce a value.

### 11.8. Using `yield` Without a Switch Expression

`yield` is for blocks in a **switch expression**; a switch statement does not directly produce a value. In a switch statement, perform actions or update state explicitly.

### 11.9. Assuming `List<?>` Means All Elements Share One Type

`case List<?> items` checks the container type but does not verify generic type arguments. Check each element individually when runtime type safety is required.

## 12. Practice Exercises

1. Write `static void show(Object x)` using a `switch` statement with `case null`, `case String s`, `case Integer n`, and `default`. Test with `null`, `"hi"`, `6`, and `3.14`.
2. Add `case String s when s.isBlank()` **before** `case String s` in exercise 1. Predict the selected branch for `""`, `" "`, and `"Java"`; explain at which step `s` is initialized.
3. Add `case Number n` after `case Integer n`. Swap the order of the two branches and observe the dominance error; fix it according to the rule of specific types before general types.
4. Write a Java 21 program using `case List<?> list -> { ... }` to print how many elements are `String` and how many are `Number`. Do not cast the whole list to `List<String>`.
5. Write a `switch` statement using `case ...:` syntax with `String` and `Integer`. Intentionally omit `break` before the `Integer` label with a pattern variable and observe the compiler message; then fix it with `break` or `->`.
6. Create a `record Pair(int left, int right)` and two `case` branches: one `when left == right`, and one unguarded. Print the pair using the two pattern variables extracted from the record.
7. Replace `System.out.println` in a `switch` statement with string expressions on the RHS and explain why it does not compile; convert it to a switch expression and assign the result to a variable.
8. Write a `sealed` interface with two implementing `record`s and create an exhaustive `switch` statement without `default`. Try adding a third subtype and observe the requirement to update the `switch`.

**Self-check question:** Can you distinguish *selecting a case by runtime type*, *additional filtering with `when`*, *pattern variable scope*, *dominance*, *fall-through*, and *exhaustiveness*? These six points determine most of the correctness of `switch` statements with patterns in Java 21.

## Official References

- [Oracle Java 21 — Pattern Matching for `switch` Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21, §14.11 — The `switch` Statement](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21, §6.3.3 — Scope for Pattern Variables in `case` Labels](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3).
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
