# Pattern Variables in `switch` Rules (Java 21+)

## 1. What are a `switch` rule and a pattern variable?

Starting in **Java 21**, pattern matching for `switch` is a standard feature (JEP 441). A `case` label can check an object's type and immediately declare a **pattern variable**; when the `case` label matches, the variable is initialized and can be used in the corresponding handling body.

```java
Object value = "hello";
switch (value) {
    case String text -> System.out.println(text.length());
    default -> System.out.println("Not a string");
}
```

This snippet prints `5`. The construct `String text` is a **type pattern**: `String` is the type to match, and `text` is the newly declared variable. If `value` actually refers to a `String`, `text` holds that same reference with static type `String`. No cast `(String) value` is needed inside the branch body.

A line `case String text -> ...` is a **switch rule**: a `case` label plus the arrow `->` and the body on the right-hand side. Once a rule is selected, Java executes only that corresponding body and exits the branch; there is no automatic *fall-through* from one rule to the next as in the classic `case ...:` form.

A `switch` using arrow rules can be either a **switch statement** (performing actions, such as printing information) or a **switch expression** (producing a value). Both can use pattern variables in `case` labels.

**Version distinction:** pattern matching for `instanceof` has been standard since Java 16, whereas pattern matching for `switch` only became standard in **Java 21**. In Java 17, `switch` patterns were still a *preview* feature requiring preview flags; the examples in this lesson use Java 21+ syntax and will not compile by default on JDK 17.

## 2. When is a pattern variable created and initialized?

Consider a switch expression with an `Object` selector:

```java
static String describe(Object value) {
    return switch (value) {
        case String s -> "String length = " + s.length();
        case Integer n -> "Integer value = " + n;
        default -> "Other";
    };
}
```

At `case String s`, Java checks whether the runtime value matches the `String` type. If it matches, Java initializes the variable `s` of type `String` before executing the expression to the right of `->`. For `case Integer n`, the variable `n` of type `Integer` is initialized only for that rule. `String` and `Integer` are two separate matching paths; the program does not have to cast `value` manually.

`case` labels are evaluated in order and Java selects the first matching label, also taking into account any `when` condition if the label has a guard. Therefore, the ordering between types with a parent–child relationship or between guarded and unguarded patterns must be designed carefully.

**`null` must be handled explicitly.** With an `Object` selector, you can write:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s -> "text: " + s;
        default -> "other";
    };
}
```

`case String s` does not automatically catch `null`. If the selector is `null` and there is no label handling `null`, a normal `switch` throws `NullPointerException`, even when `default` is present. Do not assume `default` acts as an `instanceof` test or automatically matches `null`.

## 3. Scope of a pattern variable in a switch rule

According to **JLS 21**, the *scope* of a pattern variable declared in a `case` label includes:

1. **The `when` expression (guard) of that same label**, when a guard is present.
2. **The expression, block, or `throw` statement to the right of `->`** in that same rule.

This variable is **not** in scope in another rule, in `default`, or after the entire `switch` simply because it is inside the same method. This is the core takeaway of this lesson.

### 3.1. An expression to the right of `->`

```java
static String label(Object value) {
    return switch (value) {
        case String text -> "Length " + text.length();
        case Integer number -> "Number " + number;
        default -> "Unknown";
    };
}
```

`text` is usable in the expression `"Length " + text.length()` because this rule is only selected after the pattern `String text` matches. In the `case Integer number` rule, only `number` is declared by that label; it cannot reference the `text` variable from the preceding branch.

### 3.2. A block `{ ... }` to the right of `->`

If multiple statements are needed, use a block and access the pattern variable throughout the rule's block:

```java
static void printStringInfo(Object value) {
    switch (value) {
        case String s -> {
            int length = s.length();
            String upper = s.toUpperCase();
            System.out.println(upper + " / " + length);
        }
        default -> System.out.println("Not a String");
    }
}
```

In this example, `s` is validly used by both `s.length()` and `s.toUpperCase()` within the same block. The local variables `length` and `upper` also follow normal Java block scoping. Neither `s`, `length`, nor `upper` can be used in the `default` rule or after the rule's block.

The braces `{}` create a statement block, but the underlying condition allowing `s` to be used is still that the corresponding rule **definitely matched the pattern**.

### 3.3. A `throw` statement to the right of `->`

A rule can throw an exception directly and still use the pattern variable in the expression that constructs the exception:

```java
static int nonEmptyLength(Object value) {
    return switch (value) {
        case String s when s.isEmpty() ->
                throw new IllegalArgumentException("Empty String: " + s);
        case String s -> s.length();
        case null -> 0;
        default -> -1;
    };
}
```

In the first rule, `s` is usable both in `when s.isEmpty()` and in the exception message `"Empty String: " + s`. The next rule has its **own separate declaration** also named `s` and handles other strings. If the value is not a `String`, neither rule declaring `s` is used.

In a switch expression, the right-hand side of a rule can be a value-producing expression, a block ending with `yield`, or a `throw` statement as shown here. `throw` does not produce a normal value; it completes abruptly with an exception.

## 4. Pattern variables in a `when` guard

A **guarded case label** has the form:

```java
case String s when s.length() >= 5 -> "Long text"
```

The evaluation order is:

1. Check whether the value matches the type pattern `String s`.
2. If it matches, initialize `s` and then evaluate the condition `when s.length() >= 5`.
3. Only if the guard returns `true` does the right-hand side of the arrow execute.
4. If the pattern does not match or the guard is false, try the next `case` label.

Because the guard is evaluated **after matching**, you can call methods on `s` without casting.

```java
static String sizeLabel(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "Blank";
        case String s when s.length() >= 5 -> "Long: " + s;
        case String s -> "Short: " + s;
        case null -> "Null";
        default -> "Not text";
    };
}
```

The three `case String s` labels **can use the same name `s`** because each variable belongs only to the scope of the rule containing its declaration; the variable in the first rule does not carry over into the second rule. This is not a single variable being reassigned across multiple branches.

In the example, `case String s -> ...` **must appear after** the `case String s when ...` labels: an unguarded `String` label catches all remaining strings and would *dominate* a `String` label appearing after it. In that case, a completely shadowed label causes a compile-time error.

**Note on `when`:** this is Java 21's guard syntax, not an `if` inside the rule body. Use `when` if the extra condition determines whether the `case` label is selected; use `if` inside a block when the condition only determines how to handle the case after the label has already been selected.

## 5. Complete, compilable, runnable Java 21+ program

Save with the exact filename **`SwitchRulePatternDemo.java`**:

```java
public class SwitchRulePatternDemo {
    static String describe(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank text";
            case String s -> "text(" + s.length() + "): " + s.toUpperCase();
            case Integer n when n >= 0 -> "nonnegative int: " + n;
            case Integer n -> "negative int: " + n;
            default -> "other: " + value.getClass().getSimpleName();
        };
    }

    static int measure(Object value) {
        return switch (value) {
            case null -> 0;
            case String s -> {
                String trimmed = s.trim();
                yield trimmed.length();
            }
            case Number n -> n.intValue();
            default -> throw new IllegalArgumentException(
                    "Unsupported: " + value.getClass().getSimpleName());
        };
    }

    static void printType(Object value) {
        switch (value) {
            case null -> System.out.println("NULL");
            case String s -> System.out.println("STRING: " + s);
            case Number n -> {
                double twice = 2 * n.doubleValue();
                System.out.println("NUMBER x2: " + twice);
            }
            default -> System.out.println("OTHER");
        }
    }

    public static void main(String[] args) {
        System.out.println(describe(""));
        System.out.println(describe("Java"));
        System.out.println(describe(-3));
        System.out.println(describe(5));
        System.out.println(describe(true));

        System.out.println("measure(\" ab \"): " + measure(" ab "));
        System.out.println("measure(12.8): " + measure(12.8));
        System.out.println("measure(null): " + measure(null));

        printType("Hi");
        printType(2.5);
        printType(false);
    }
}
```

Using **JDK 21 or later**, from the directory containing the file:

```bash
javac SwitchRulePatternDemo.java
java SwitchRulePatternDemo
```

Output:

```text
blank text
text(4): JAVA
negative int: -3
nonnegative int: 5
other: Boolean
measure(" ab "): 2
measure(12.8): 12
measure(null): 0
STRING: Hi
NUMBER x2: 5.0
OTHER
```

**Group-by-group breakdown:**

- `describe("")`: the object matches `String s` and the guard `s.isBlank()` is true, so `blank text` is chosen. `describe("Java")` does not pass the blank guard and moves to the next `String s` rule; the `s` variable in the second rule is a different variable and `s.length()` equals 4.
- `describe(-3)` and `describe(5)`: both are `Integer`, but the guard `n >= 0` decides whether the nonnegative branch or the remaining `Integer` branch is chosen. The variable `n` is scoped to its respective rule.
- `describe(true)`: the runtime value is `Boolean`, matching neither `String` nor `Integer`; `default` calls `value.getClass().getSimpleName()`, yielding `Boolean`. The `null` branch was already handled earlier, so `value` is guaranteed non-null here.
- `measure(" ab ")`: the `String s` rule creates a local variable `trimmed` inside the block and uses **`yield`** to produce the result `2` for the switch expression. `measure(12.8)` matches `Number n` (runtime value is `Double`), and `n.intValue()` returns `12`. `measure(null)` returns `0`. For other unsupported types, `default -> throw ...` throws an exception.
- `printType("Hi")`: a switch **statement**, where the right-hand side of `->` simply runs `println`; no `yield` is needed. `printType(2.5)` enters the `Number n` block and doubles it to `5.0`; `false` goes to `default`. Each pattern variable exists only within the rule in which it is declared.

An important rule: in a **switch expression**, when the RHS is a block, use `yield` to provide the value for the entire `switch` expression (or complete abruptly with an exception); do not use `break` to return a value. In a **switch statement**, the RHS can be a single statement or a normal block and does not need to return a value.

## 6. Comparing switch rules with colon-labeled statement groups

Java has two ways to structure a switch body:

**Switch rule (arrow):**

```java
switch (value) {
    case String s -> System.out.println("Text: " + s);
    case Integer i -> System.out.println("Int: " + i);
    default -> System.out.println("Other");
}
```

Each rule has its own execution boundary and **does not automatically fall through** to the next rule. The variable `s` is only available in the `String` label's body; `i` is only available in the `Integer` label's body.

**Switch labeled statement group (colon):**

```java
switch (value) {
    case String s:
        System.out.println("Text: " + s);
        break;
    case Integer i:
        System.out.println("Int: " + i);
        break;
    default:
        System.out.println("Other");
}
```

The colon `:` form creates `case`-labeled statement groups. A pattern variable is scoped to its corresponding statement group, and this form has strict rules to prevent *falling through* into a pattern label when its variable would be uninitialized. For exercises and new code that are easy to reason about, **prefer `->` rules** when classic statement-group syntax is not needed. The two forms must not be mixed within the same switch block.

## 7. Dominated `case` labels and ordering rules

Patterns often have a supertype–subtype relationship. If an earlier label matches every value that a later label could match, the later label is **dominated** and Java reports a compile-time error.

Example that **does not compile**:

```java
// In a switch(value), where value has type Object:
// case CharSequence text -> System.out.println(text.length());
// case String s -> System.out.println(s.toUpperCase()); // Dominated
// default -> System.out.println("Other");
```

Because every `String` is a `CharSequence`, the first label already catches all strings. Reorder them:

```java
// Valid in switch(value):
// case String s -> System.out.println(s.toUpperCase());
// case CharSequence text -> System.out.println(text.length());
// default -> System.out.println("Other");
```

An unguarded pattern (`case String s`) can also dominate guarded cases of the same type placed after it. Therefore, a sensible ordering is usually:

1. Subtypes or specialized cases, and constant cases if needed;
2. Patterns of the same type with `when` guards;
3. More general, unguarded patterns;
4. `default` when a fallback branch is needed.

Do not rely on "by the next rule, the previous rule's variable is still around" when writing logic: **every rule has an independent scope**, and switch rules do not fall through.

## 8. Common scope-related mistakes

### 8.1. Accessing a variable from another rule or from `default`

The following snippet **illustrates errors** and is not a standalone program:

```java
switch (value) {
    case String s -> System.out.println(s.length());
    case Integer n -> {
        // System.out.println(s); // ERROR: s belongs to the String rule
        System.out.println(n);
    }
    default -> {
        // System.out.println(s); // ERROR: s is not in scope in default
        System.out.println("Other");
    }
}
// System.out.println(s); // ERROR: case variable does not escape switch
```

After `switch`, if you need to use a value from the selected branch, **return the result from a switch expression** and store it in a variable declared outside:

```java
String result = switch (value) {
    case String s -> s.toUpperCase();
    case Integer n -> Integer.toString(n);
    case null -> "(null)";
    default -> "(other)";
};
System.out.println(result); // Valid; result is a variable outside switch.
```

`result` is not a pattern variable; it is a local variable receiving the result of the entire switch expression.

### 8.2. Combining `null` with a pattern that declares a variable in the same label

This code **does not compile** on Java 21:

```java
// INVALID:
// case null, String s -> System.out.println(s);
```

Not every combined label initializes `s`; in the `null` case there is no string to assign. Write them as separate rules:

```java
case null -> System.out.println("null");
case String s -> System.out.println(s);
```

These are two **labels inside a switch block**; the two lines only illustrate label syntax, not a standalone Java program.

### 8.3. Using a variable on the wrong side of `when`

```java
case String s when s.length() > 3 -> s.toUpperCase();
```

This is valid because `s` has already been declared by the pattern before `when`. However, `when` is not a place to use a pattern variable declared in **another `case`**; there is no cross-rule scope.

### 8.4. Missing exhaustiveness in a switch expression

When `switch` is an **expression**, every possible value must be handled by a branch (*exhaustive*). With an `Object` selector, having only `case String s` and `case Integer n` does not cover all types; you need `default` or a set of labels sufficient to cover the entire input type. A switch statement with patterns or a `null` label must also obey Java 21's exhaustiveness rules.

As explained earlier, `default` in `switch(value)` **does not automatically catch `null`**. You can use `case null -> ...` to handle `null` explicitly when `value` might be `null`.

### 8.5. Using the wrong JDK version or `yield` statement

- `case String s -> ...` and `when` guards in `switch` are standard syntax starting in **Java 21**, not default JDK 17 syntax.
- In a switch expression: if the RHS block needs to return a value, use `yield value;`.
- In a switch statement: arrow rules perform actions; `yield` is not needed.
- The right-hand side of `->` can be an expression/method call, a block, or a `throw` depending on context; do not use `break` to produce the value of a switch expression.

## 9. Scope quick-reference table

| Location | Can you use pattern variable `s` from `case String s`? |
| --- | --- |
| Inside `when s.isBlank()` of **that same case** | **Yes**, after the pattern matches |
| Inside the expression after `case String s ->` | **Yes** |
| Inside the block after `case String s -> { ... }` | **Yes** |
| Inside the exception message in `case String s -> throw ...` | **Yes** |
| Inside another `case Integer n -> ...` | **No** |
| Inside `default -> ...` | **No** |
| After the entire `switch` | **No** |
| Another rule also written `case String s` | **Has a new `s` variable for that rule**, not the previous one |

To determine scope accurately, ask: **Which label declared the variable, and is the location in question inside the guard or RHS of that exact label?**

## 10. Practice exercises

1. Write a method `static String category(Object x)` using a **switch expression** with the rules: `null` → `"null"`; `String s` with length 0 → `"empty"`; other strings → `"text: " + s`; `Number n` → `"number: " + n`; everything else → `"other"`. Use `when s.isEmpty()` for the empty case.
2. For exercise 1, try declaring the same name `s` in both `case String s` rules; explain why there is no conflict and why each `s` is only valid within its own rule.
3. Convert the `case String s` branch into a block with two statements: store `s.trim()` in a variable `trimmed`, then `yield trimmed.length()`. Explain why a switch expression requires `yield` when the RHS is a block.
4. Create a **switch statement** to print `"String length = ..."` or `"Number = ..."`; use arrow rules and access the pattern variables directly. Then try using the variable in `default` and explain the scope error.
5. Write two labels `case CharSequence cs` and `case String s`. Try reversing their order to observe the *dominated case* error, then explain it based on the class/type hierarchy.
6. Write `case String s when s.isBlank() -> throw new IllegalArgumentException(s);` inside a switch expression. Point out the two places where `s` is valid and why.

**Remember:** In a **switch rule**, a pattern variable belongs only to **the `when` guard and the right-hand side of `->` of the exact `case` label that declares it**. Once you move to another rule, `default`, or after `switch`, you cannot continue using that variable. Java 21 checks scope, label ordering, and exhaustiveness to prevent using an unmatched variable.

## References

- [Oracle Java 21 — Pattern Matching for `switch` Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21, §6.3.3 — Scope for Pattern Variables in `case` Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3).
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441).
- [Java Language Specification 21 — `switch` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
