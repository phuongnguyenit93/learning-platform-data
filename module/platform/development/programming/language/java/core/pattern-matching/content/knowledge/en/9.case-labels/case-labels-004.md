# Constant and Pattern `case` Labels in Java

## 1. Why Are There Two Kinds of `case` Labels?

A `case` label specifies the branch that a `switch` selects for execution. In traditional Java, the common labels are **constants**, such as `case 0`, `case "OK"`, or an `enum` constant name. Since **Java 21**, *pattern matching for switch* became a standard feature (JEP 441), allowing **patterns** to be used in labels: `case String text`, `case Integer n`, `case Number n when n > 0`...

The two forms serve different purposes:

- **Constant label**: checks a **specific** value using the comparison rules defined by Java for the corresponding `switch` type. For example, `case 0` applies only to the numeric value 0; `case "OK"` applies only to a string equal to `"OK"`.
- **Pattern label**: checks whether a value **matches a type or structure**. For example, `case Integer n` matches any runtime value that is an `Integer`, then initializes the pattern variable `n` for use in the branch. A pattern can have an additional `when` condition.

Example combining constants and patterns with an `Integer` selector:

```java
static String describe(Integer value) {
    return switch (value) {
        case null -> "missing";
        case 0 -> "zero";
        case 1, 2 -> "one or two";
        case Integer n when n < 0 -> "negative: " + n;
        case Integer n -> "another integer: " + n;
    };
}
```

For `0`, Java selects the constant label `case 0`. For `-7`, Java evaluates `case Integer n when n < 0` and selects this rule. For `9`, Java selects the last rule. In the two pattern rules, the variable `n` **can only be used in the guard and RHS of the rule that declares it**.

In the example, there is no `default` because `case Integer n` is an unconditional pattern covering every non-`null` `Integer`; `case null` handles `null` separately. Java 21 allows writing a switch expression like this.

## 2. Constant Labels: Fixed Values, No New Variable Declarations

Constant labels have the form:

```java
case 10 -> ...
case "OPEN" -> ...
case MONDAY -> ...
case 1, 2, 3 -> ...
```

These are **syntax fragments** that must be placed inside a switch with a compatible selector type. `case 1, 2, 3` groups multiple **constants** into a single label sharing the same body; this is different from pattern declarations.

### 2.1. How Are Constants Accepted?

In Java 21, `case` can use:

- An appropriate **constant expression**, such as `3`, `2 + 3`, `'A'`, `"READY"`.
- A **constant variable** with a compatible type and value (for example, `static final int LIMIT = 10;`, where the value is a constant expression at declaration).
- An **`enum` constant** in a switch on a compatible enum, such as `case PENDING`, `case DONE`.

Not every `final` variable is a compile-time constant:

```java
final int constant = 2 + 3;     // Constant variable: valid as a case label.
final int runtime = Math.abs(-5); // Value computed via a method call.

// In a switch on an int:
case 5 -> System.out.println("five");
// case constant -> ...         // Duplicates the value of case 5: error if placed together.
// case runtime -> ...          // ERROR: not a constant expression.
```

The `case` lines above are only illustrative within an `int` switch context. A switch cannot have **two constant cases with the same value**, even if written with two different expressions. `case 2 + 3` and `case 5` have the same value, so they are treated as duplicate labels.

### 2.2. Selector Compatibility Requirements

**Java 21 does not allow placing arbitrary constants in every `switch(Object)`**. For constant cases that are constant expressions, JLS 21 requires the selector to have one of the types: `char`, `byte`, `short`, `int`, their corresponding wrappers (`Character`, `Byte`, `Short`, `Integer`), or `String`, and the constant must be assignment-compatible with the selector type. An `enum` constant must be compatible with the corresponding enum selector.

Example that **does not compile** in Java 21:

```java
static String wrong(Object x) {
    return switch (x) {
        // case "YES" -> "known";  // ERROR: String constant is invalid with an Object selector.
        case String s -> "text: " + s;
        default -> "other";
    };
}
```

Fix it by using a `switch` with a **`String`** selector when `case "YES"` is needed, or by using `case String s when s.equals("YES")` when the selector must be **`Object`**:

```java
static String fromObject(Object x) {
    return switch (x) {
        case String s when s.equals("YES") -> "known";
        case String s -> "text: " + s;
        case null -> "null";
        default -> "other";
    };
}
```

With a `String` selector, string constants and the type pattern `String s` can be used together, as long as the label order and dominance rules are valid.

### 2.3. Comparing Strings and Numbers

With `switch(String)` and `case "OK"`, Java uses content comparison via `String.equals`, **not** requiring the two references to point to the same string object as with `==` between two objects.

With a selector of `int`/smaller integer types or their corresponding wrappers, Java applies the numeric constant case selection rules of switch. With wrappers like `Integer`, a non-`null` value can be compared against an `int` constant; `null` must be handled separately if allowed, or the switch will throw a `NullPointerException`.

A constant label **does not create a pattern variable**. In `case "OK" -> ...`, a local variable named `s` does not automatically exist; to get a type-checked variable, a pattern such as `case String s` is needed.

## 3. Pattern Labels: Type Checking, Variable Creation, and Optional `when`

Example in Java 21:

```java
static String kind(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "String length: " + text.length();
        case Integer number -> "Integer: " + number;
        case Number number -> "Other Number: " + number;
        default -> "Other";
    };
}
```

Key points to remember:

1. `case String text` matches if the selector refers to a `String`; when matched, `text` has **static type `String`**, so `length()` can be called without casting.
2. `case Integer number` matches `Integer` values; `case Number number` matches other subclasses of `Number`, such as `Double`.
3. Pattern variables can **have the same name across independent rules**. In the example, `number` in the `Integer` branch and `number` in the `Number` branch are two distinct variables.
4. `case null` is a **special** label, not a type pattern, and does not declare a variable.
5. `default` handles the remaining types, but does not implicitly handle `null` if `case null` is absent.

### 3.1. `when`: Guard Condition Used Only with Pattern Labels

```java
static String size(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() >= 5 -> "long: " + s;
        case String s -> "short: " + s;
        case null -> "null";
        default -> "not text";
    };
}
```

`String s` must match first, and then Java evaluates the condition `when s.isBlank()` or `when s.length() >= 5`. `s` is in scope **directly within the case's own guard** and in that rule's RHS. If the pattern does not match or the guard evaluates to `false`, Java continues testing the remaining labels.

**Do not** write `case "OK" when condition -> ...` in Java 21: a label consisting only of a constant **cannot have `when` attached**. If you want to combine a constant and an additional condition:

- Put `case "OK" -> ...` to handle the constant first;
- Or switch to `case String s when s.equals("OK") && ... -> ...` if the additional condition is truly needed and the selector is appropriate.

An important ordering note: an unguarded `case String s` catches all remaining strings; if placed before `case String s when ...`, the guarded label is dominated and Java reports a compile-time error.

### 3.2. Record Patterns (Java 21+)

In addition to type patterns, Java 21 also has **record patterns**, used to check and extract components:

```java
record Point(int x, int y) {}

static String pointKind(Object input) {
    return switch (input) {
        case Point(int x, int y) when x == y -> "diagonal";
        case Point(int x, int y) -> "point: " + x + "," + y;
        case null -> "null";
        default -> "other";
    };
}
```

The variables `x`, `y` in each rule are declared by the **record pattern**, not passed from a previous branch. The guard `when x == y` can use them because deconstruction has already matched before the guard is evaluated.

**Difference from constant labels:** `case new Point(1, 2) -> ...` is not a valid constant expression label; to classify records by their contents, use a record pattern with `when`, or a variable pattern `Point p when ...`.

## 4. Combining Constants and Patterns in One Switch: Ordering Rules

This is the most important practical rule:

> **Place specific constant cases before general patterns**, and guarded patterns before unguarded patterns of the same type.

Consider an `Integer` selector:

```java
static String score(Integer value) {
    return switch (value) {
        case null -> "null";
        case 0 -> "zero";
        case 1, 2 -> "one-or-two";
        case Integer n when n < 0 -> "negative";
        case Integer n -> "other integer";
    };
}
```

For `0`, Java selects the constant 0. For `2`, Java selects the constant group 1 or 2. For `-5`, the rule with the guard `n < 0` is selected. For `8`, the general rule `case Integer n` handles it.

### 4.1. Dominance: A Later Label Is Completely Covered

Java checks **dominance** at compile time to prevent labels that can never be selected because an earlier label already covers them.

**Invalid** example:

```java
// In switch(Integer value):
case Integer n -> System.out.println("any integer");
case 42 -> System.out.println("special 42"); // ERROR: dominated by case Integer n.
```

Here `case Integer n` is an unguarded pattern matching every non-`null` `Integer` value; the constant `42` no longer has a chance to be selected. Reordering makes it valid:

```java
case 42 -> System.out.println("special 42");
case Integer n -> System.out.println("other integer " + n);
```

An example of pattern dominance:

```java
// In switch(Object value):
case Number n -> System.out.println(n);
case Integer i -> System.out.println(i); // ERROR: Integer is a subtype of Number.
```

`Integer` must be placed before `Number` if you want specialized handling.

**Subtlety:** Java does not attempt to solve every `when` expression by mathematical deduction. For example, `case Integer n when n < 10` before `case 5` may not be rejected for dominance, but when `5` occurs, the guarded rule matches it first; the constant label 5 will not execute. Therefore, you should still put **constants before guards** to avoid surprising behavior, even when the code compiles.

### 4.2. "Catch-All" Patterns and `default`

In `switch(Integer value)`, the pattern `case Integer n` is an **unconditional pattern** for all non-`null` `Integer` values. When it is present, do not also place `default` in the same switch block: this can cause an error because both labels have the meaning of covering the entire selector type.

Complete approach:

```java
return switch (value) {
    case null -> "missing";
    case 42 -> "answer";
    case Integer n -> "integer " + n;
};
```

If the selector is `Object`, you can write specific type patterns and then `default` to cover the remaining types:

```java
return switch (value) {
    case null -> "missing";
    case String s -> "text: " + s;
    case Integer n -> "integer: " + n;
    default -> "other";
};
```

In the second example, `case String s` cannot be replaced directly with `case "hello"` because the selector has static type `Object`.

## 5. `case null`, `default`, and Label Grouping

### 5.1. `null` Is Not Like a Regular Constant

In Java 21, a reference-type selector can use `case null`. This is a special case:

```java
static String label(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s -> "text";
        default -> "other";
    };
}
```

`case String s` does not match `null`; a regular `default` does not catch `null` automatically either. If the selector is `null` and there is **no** label handling `null`, the switch normally throws a `NullPointerException`.

Java 21 also allows a special syntax:

```java
static String labelOrOther(Object value) {
    return switch (value) {
        case String s -> "text";
        case null, default -> "not text (including null)";
    };
}
```

`case null, default` is an **explicitly allowed** combination, unlike arbitrarily combining `null` with a pattern that declares a variable.

**Invalid:**

```java
// case null, String s -> System.out.println(s); // ERROR in Java 21.
// case 0, Integer n -> System.out.println(n);   // ERROR in Java 21.
```

In Java 21, a regular `case` label contains **a list of constants**, **a special `null`**, or **a single pattern** (optionally with `when`). These kinds cannot be mixed arbitrarily in the same comma-separated list. `case null, default` is a dedicated special syntax.

### 5.2. Grouping Constants vs. Grouping Patterns

**Valid** if all are compatible constant expressions:

```java
switch (code) {                // code has type int
    case 200, 201, 202 -> System.out.println("success");
    case 400, 404 -> System.out.println("client error");
    default -> System.out.println("other");
}
```

Conversely, `case String s, Integer n -> ...` is **not standard Java 21 syntax**. When two types need shared handling, use separate rules calling the same helper method, or a more general pattern appropriate for the selector.

With the colon syntax `case ...:`, Java has statement groups and possible fall-through; however, if control enters a group with an **uninitialized pattern variable**, the compiler rejects it. The `case ... ->` form avoids most of this confusion because it does not fall through.

## 6. Switch Statements, Switch Expressions, and Exhaustiveness

Both forms of `switch` can contain both constants and patterns:

- **Switch statement**: executes statements, such as `System.out.println(...)`; does not itself produce a value for an enclosing expression.
- **Switch expression**: produces a value; each rule has an RHS that is a value expression, a block using `yield`, or a `throw` statement.

Switch statement example:

```java
static void announce(Integer value) {
    switch (value) {
        case null -> System.out.println("null");
        case 42 -> System.out.println("answer");
        case Integer n -> System.out.println("other: " + n);
    }
}
```

Switch expression example:

```java
static String category(Integer value) {
    return switch (value) {
        case null -> "null";
        case 42 -> "answer";
        case Integer n -> "other: " + n;
    };
}
```

Note: `case 42` appears **before** `case Integer n`. In both examples, all non-`null` `Integer` values match one of the two rules; `null` is handled separately.

In Java 21, **a switch expression must always be exhaustive**. An **enhanced switch statement** (for example, a switch statement using a pattern case or `case null`, or a selector whose type is not one of the traditional types) must also be exhaustive. With an `Integer` selector, if you only list `case 0` and `case 1` while still using a pattern or `case null`, you typically need to add `default` or a general pattern covering the rest.

A **traditional switch statement** that only uses constant cases on a classic selector type may omit `default` for backward compatibility. Do not confuse this behavior with an enhanced switch statement.

With enums, constants can exhaustively cover all non-`null` values on their own:

```java
enum Stage { TODO, DOING, DONE }

static String stageName(Stage stage) {
    return switch (stage) {
        case null -> "missing";
        case TODO -> "To do";
        case DOING -> "In progress";
        case DONE -> "Done";
    };
}
```

This is an exhaustive switch expression because it handles all three enum constants and has a separate label for `null`. No `default` is needed. If the enum is later extended with more values, the switch code may need to be updated accordingly to preserve exhaustiveness.

## 7. Complete Runnable Java 21 Program: Constants and Patterns Coexisting

Save with the exact file name **`CaseConstantPatternDemo.java`**:

```java
public class CaseConstantPatternDemo {
    enum Stage { TODO, DOING, DONE }

    static String classifyNumber(Integer value) {
        return switch (value) {
            case null -> "null number";
            case 0 -> "zero";
            case 1, 2 -> "one/two: " + value;
            case Integer n when n < 0 -> "negative: " + n;
            case Integer n when n % 2 == 0 -> "even: " + n;
            case Integer n -> "odd: " + n;
        };
    }

    static String classifyText(String value) {
        return switch (value) {
            case null -> "null text";
            case "" -> "empty text";
            case "OK", "YES" -> "approved: " + value;
            case String s when s.isBlank() -> "blank text";
            case String s when s.length() >= 5 -> "long text: " + s;
            case String s -> "short text: " + s;
        };
    }

    static String classifyObject(Object value) {
        return switch (value) {
            case null -> "null object";
            case String s -> "String length: " + s.length();
            case Number n when n.doubleValue() < 0 -> "negative Number";
            case Number n -> "Number: " + n;
            default -> "other";
        };
    }

    static String stageName(Stage stage) {
        return switch (stage) {
            case null -> "missing";
            case TODO -> "To do";
            case DOING -> "In progress";
            case DONE -> "Done";
        };
    }

    static void announce(Integer value) {
        switch (value) {
            case null -> System.out.println("ANNOUNCE null");
            case 42 -> System.out.println("ANNOUNCE answer");
            case Integer n when n > 100 ->
                    System.out.println("ANNOUNCE large " + n);
            case Integer n -> System.out.println("ANNOUNCE other " + n);
        }
    }

    public static void main(String[] args) {
        System.out.println(classifyNumber(null));
        System.out.println(classifyNumber(0));
        System.out.println(classifyNumber(2));
        System.out.println(classifyNumber(-3));
        System.out.println(classifyNumber(8));
        System.out.println(classifyNumber(7));

        System.out.println(classifyText(null));
        System.out.println(classifyText(""));
        System.out.println(classifyText("OK"));
        System.out.println(classifyText("  "));
        System.out.println(classifyText("hello"));
        System.out.println(classifyText("Hi"));

        System.out.println(classifyObject("X"));
        System.out.println(classifyObject(-2.5));
        System.out.println(classifyObject(3.5));
        System.out.println(classifyObject(true));

        System.out.println(stageName(Stage.DOING));

        announce(42);
        announce(150);
        announce(9);
        announce(null);
    }
}
```

**Compile and run with JDK 21 or later** (pattern matching for switch is a standard feature, no preview flags needed):

```bash
javac CaseConstantPatternDemo.java
java CaseConstantPatternDemo
```

**Exact output:**

```text
null number
zero
one/two: 2
negative: -3
even: 8
odd: 7
null text
empty text
approved: OK
blank text
long text: hello
short text: Hi
String length: 1
negative Number
Number: 3.5
other
In progress
ANNOUNCE answer
ANNOUNCE large 150
ANNOUNCE other 9
ANNOUNCE null
```

**Explanation:**

1. `classifyNumber` takes `Integer`: the constants `0`, `1`, `2` are checked first; then the guarded `Integer n` patterns check negative numbers, even numbers, and finally odd numbers. Because `n` is always an `Integer` when the pattern matches, the expression `n % 2` and comparison `n < 0` are valid in the guard.
2. `classifyText` takes `String`: the constant `""` and the constant group `"OK", "YES"` are handled first. Other strings are then evaluated by the guarded type patterns. `"  "` is whitespace so the `isBlank()` branch is selected; `"hello"` has length 5, matching the guard `length() >= 5`.
3. `classifyObject` takes `Object`: here there are only type patterns, `case null`, and `default`; **no string/numeric constants** are placed directly in the `Object` switch. `-2.5` and `3.5` are boxed into `Double` when passed in, and both are `Number`. The guard selects the negative case.
4. `stageName` uses enum constants of the right type, covering all three declared constants along with the `null` case.
5. `announce` is a **switch statement**, not a switch expression: each branch executes `println`. `case 42` is placed before the pattern `Integer n`, so it is not dominated by the general branch.

The program uses a single file, one public class, and a nested enum so the entire example can be compiled easily.

## 8. Comparison Table of `case` Labels

| Label kind | Example | Check | New pattern variable? |
| --- | --- | --- | --- |
| Integer constant | `case 42` | Corresponding numeric value equals 42 | No |
| `String` constant | `case "OK"` | String has content equal to `"OK"` | No |
| Constant group | `case 1, 2` | One of the listed values | No |
| Enum constant | `case DONE` | Exact enum constant `DONE` | No |
| Type pattern | `case String s` | Value has runtime type compatible with `String` | Yes: `s` |
| Guarded type pattern | `case Integer n when n < 0` | Matches `Integer` **and** `n < 0` | Yes: `n` |
| Record pattern | `case Point(int x, int y)` | Matches record and deconstructs components | Yes: `x`, `y` |
| `null` | `case null` | Selector is `null` | No |
| Fallback label | `default` | Unhandled non-`null` values | No |
| Special label | `case null, default` | Handles both `null` and remaining values | No |

**Version note:** Type/record patterns in switch, `when`, and `null` handling with the syntax shown here are standard features of **Java 21**. Constant-only switch forms have existed since earlier Java versions.

## 9. Common Compilation Errors and Misconceptions

### 9.1. Assuming `case "A"` Is Valid with an `Object` Selector

In Java 21, a `String` constant case cannot be placed in a switch whose static selector type is `Object`. Change the selector to `String` if the logic allows, or use `case String s when s.equals("A")` for `Object`.

### 9.2. Placing a General Pattern Before a Constant

`case Integer n` before `case 42` is a dominance error. Place the constant `42` before the pattern. Similarly, `case Number n` before `case Integer i` dominates the `Integer` branch.

### 9.3. Using `when` with a Constant Case

`case 10 when flag` is not valid Java 21 syntax. `when` goes with a **pattern case**. To add an extra condition, use a guarded pattern or an `if` check inside the constant branch's block.

### 9.4. Mixing Patterns and Constants in the Same Label

`case 1, Integer n` and `case null, String s` are both invalid in Java 21. Use separate rules; do not confuse this with `case null, default`.

### 9.5. Two Constants for the Same Value

`case 5` and `case 2 + 3` in the same switch cause an error because both have value 5. Different constant variable names or different expression forms do not create a new label if the value is duplicated.

### 9.6. Assuming `default` Automatically Catches `null`

Without `case null`, a `null` selector can throw `NullPointerException` even when `default` is present. If you want to combine the fallback branch including `null`, use `case null, default` when appropriate.

### 9.7. Using a Pattern Variable Outside Its Declaring Rule

The variable of `case String s` can only be used in the guard and RHS of its corresponding rule, not in a constant branch, `default`, or after the switch. If you need an aggregated value, take the result of a switch expression or assign to a variable declared outside the switch statement.

### 9.8. Confusing Exhaustiveness Requirements

An enhanced switch statement with patterns/`case null` must be exhaustive. With an `Object` selector, `String` and `Integer` patterns typically need `default` to handle other types. With an `Integer` selector, `case Integer n` can cover the remaining non-null values; `case null` handles null.

### 9.9. Forgetting the No-Fall-Through Rule of `->`

A `case 1 -> ...` rule does not automatically fall through into `case Integer n -> ...`. With `case ...:` syntax, fall-through is possible, but you cannot fall through into code that uses an uninitialized pattern variable; use `break` or switch to `->`.

### 9.10. Using Java 17 as If It Already Supported Standard Pattern Matching for Switch

Pattern matching for `instanceof` became standard in Java 16, but **pattern matching for switch** is a standard feature starting in Java 21. Compile the examples combining constant and pattern labels here with JDK 21+.

## 10. Practice Exercises

1. **Constant before pattern:** Write `switch(Integer status)` with `case null`, `case 200`, `case 404`, `case Integer n when n >= 500`, and `case Integer n` last. Return `"missing"`, `"OK"`, `"not found"`, `"server error"`, or `"other"`; explain the order of each rule.
2. **`String` constant vs. Object:** Write `switch(String command)` with `case "START", "GO"`, `case "STOP"`, a guarded `case String s when s.isBlank()`, and `case String s`. Then try changing the selector to `Object` and observe the constant error; fix it using a guarded type pattern.
3. **Dominance:** In `switch(Integer code)`, place `case Integer n` before `case 42`. Explain the compilation error; swap the order to fix it. Try `case Integer n when n < 100` before `case 42`, and see which branch is selected for the value 42 and why.
4. **Duplicate constants:** Create `static final int TARGET = 5;`, then place `case TARGET` and `case 2 + 3` in the same switch. Predict the compiler message and fix it so the labels do not duplicate.
5. **Null:** Write `switch(Object x)` with `case String s` and `case null, default` to handle all inputs. Compare with a standalone `default` when the selector is `null`.
6. **Record pattern:** Create `record Pair(int a, int b)`; write two pattern branches: `case Pair(int a, int b) when a == b` and `case Pair(int a, int b)`. Use `when` to distinguish pairs of two equal numbers.
7. **Enum:** Create an enum `Mode { AUTO, MANUAL, OFF }`, and write a switch expression with the three constant cases and `case null`. Do not use `default`; explain why the expression is already exhaustive.
8. **Variable scope:** Place `case String s -> ...` and `case Integer n -> ...` in one switch. Try referencing `s` in the `Integer` branch, then fix it by moving the shared logic into a method that takes a parameter.
9. **Statement vs. expression:** Convert a switch expression returning `String` into a switch statement that only prints the result. Check the difference between an RHS that is a value expression and an RHS that is a `println` call.

**Summary:** Constants in `case` classify **specific values**; patterns classify **types/structures** and create local variables along the matching branch. When combining them in Java 21, ensure the selector type is compatible with constants, place **specific constants before guarded patterns and general patterns**, handle `null` explicitly, and check dominance and exhaustiveness.

## References

- [Java Language Specification 21, §14.11 — Switch Statements, Case Labels, and Switch Compatibility](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21, §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [Java Language Specification 21, §6.3.3 — Scope of Pattern Variables in Case Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3).
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
