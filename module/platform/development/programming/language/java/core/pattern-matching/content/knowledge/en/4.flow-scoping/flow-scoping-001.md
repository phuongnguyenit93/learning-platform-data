# What is Flow Scoping in Java 21?

**Flow scoping** is the rule that determines **the scope of a pattern variable based on control flow**. When you write a *type pattern* such as `value instanceof String text`, Java only allows using `text` in places where the compiler can prove that the match succeeded. As a result, the program cannot accidentally read an unassigned pattern variable because the object is of the wrong type.

This topic is especially important when using pattern matching with `instanceof`, the `&&`, `||`, `!` operators, `if` statements, and `switch` branches. Java 21 also supports pattern matching in `switch` and record patterns; flow scoping still governs where a pattern variable is in scope.

## 1. Why is flow scoping needed?

With the traditional syntax, programmers check the type first and then manually cast:

```java
static void oldWay(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        System.out.println(text.length());
    }
}
```

A type pattern combines the check and the declaration:

```java
static void newWay(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

Both snippets are illustrative methods that must be placed inside a class. In `newWay`, `text` only exists in the branch where `value instanceof String text` returned `true`. If `value` is an `Integer` or `null`, the check fails and Java does not allow using `text` on that branch.

Unlike a regular local variable, the scope of a pattern variable **does not depend solely on curly braces**. The compiler analyzes which paths through expressions and statements have established that the pattern matched. This mechanism is sometimes described as a variable being *definitely matched* at the point of use.

## 2. Flow scoping with `if` and `else`

Consider the following code:

```java
static void inspect(Object value) {
    if (value instanceof String text) {
        System.out.println(text.toUpperCase()); // valid
    } else {
        System.out.println("Not a String");
        // System.out.println(text); // invalid
    }

    // System.out.println(text); // invalid
}
```

In the `if` branch, the condition evaluates to `true`, so `text` is guaranteed to have received a `String`. In the `else` branch, the pattern has failed; after the entire `if/else`, the two paths merge and not every path produced `text`. Therefore, the variable is not in scope at those locations.

With negation, the path where the match is guaranteed **reverses direction**:

```java
static void inspectNegated(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Not a String");
    } else {
        System.out.println(text.toUpperCase()); // valid
    }
}
```

When `!(value instanceof String text)` is `false`, the inner `instanceof` expression must be `true`; hence `text` is in scope in the `else` branch.

## 3. Guard clauses: using a pattern variable after `if`

A useful pattern is **early exit** if the pattern does not match:

```java
static String normalized(Object value) {
    if (!(value instanceof String text)) {
        return "not text";
    }

    return text.trim().toLowerCase(); // valid
}
```

If the negated condition is true, the method has already `return`ed; every path that continues to the last line guarantees `value` is a `String`. The compiler allows using `text` after the `if` without having to put all the logic inside an `else` block.

The same rule applies if the non-matching branch always `throw`s an exception. However, if that branch can still complete normally, it cannot be concluded that the pattern matched:

```java
// Example THAT DOES NOT COMPILE: the if branch can complete normally.
static int wrong(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("not text");
    }
    return text.length(); // text is not guaranteed to have been created
}
```

Therefore, the effect of a guard clause comes from both **the condition** and the fact that the failing branch **does not continue**.

## 4. The `&&` operator: the right-hand side knows the left-hand side matched

The `&&` operator uses **short-circuit** evaluation: Java only evaluates the right-hand side when the left-hand side is `true`. If the left-hand side is a type pattern, the pattern variable can be used immediately on the right-hand side:

```java
static boolean hasLongName(Object value) {
    return value instanceof String name && name.length() >= 5;
}
```

When `name.length()` runs, the `instanceof` check is guaranteed to have succeeded; therefore no additional cast is needed. Multiple conditions can be chained:

```java
if (value instanceof String text
        && !text.isBlank()
        && text.length() <= 100) {
    System.out.println(text.strip());
}
```

This snippet illustrates code inside a method that has a `value` variable. The `text` variable is usable in both subsequent conditions and the `if` body when **the entire condition is true**.

Note the distinction: if the entire `&&` expression is `false`, we do not know which side failed. Either `instanceof` was false or the length check was false. Thus, `text` cannot automatically be inferred as in scope in any branch handling the `false` result.

## 5. The `||` operator: does not guarantee the pattern matched

The `||` operator evaluates the right-hand side when the left-hand side is `false`. If the left-hand side is `value instanceof String text`, once execution reaches the right-hand side, the pattern has **failed**, so `text` cannot be used there.

```java
// Example THAT DOES NOT COMPILE:
static boolean wrongOr(Object value) {
    return value instanceof String text || text.isBlank();
}
```

Changing `||` to `&&` only makes sense when you want both conditions to be true. If you need to accept either case, write the independent logic explicitly, for example:

```java
static boolean acceptable(Object value) {
    return value == null
            || (value instanceof String text && !text.isBlank());
}
```

This approach is safe: the `null` case is handled by the first operand; in the second branch, `text` is only used after `instanceof` succeeds.

A subtle point: when negating the pattern before `||`, the right-hand side can use the pattern variable, because to reach it, the negation must be false:

```java
static boolean isMissingOrBlank(Object value) {
    return !(value instanceof String text) || text.isBlank();
}
```

The result is `true` when the value is not a `String` **or** is an empty/whitespace-only string. `text.isBlank()` only runs when `value` is actually a `String`. The rule here is based on the **true/false** paths of the expression, not a mechanical rule that `||` always forbids pattern variables.

## 6. Path reference table

| Expression / Path | Where can the pattern variable be used? | Reason |
| --- | --- | --- |
| `x instanceof String s` evaluates to `true` | Branch receiving the true result | Pattern matched |
| `x instanceof String s` evaluates to `false` | Cannot use `s` from this pattern | Pattern did not match |
| `!(x instanceof String s)` evaluates to `false` | Branch receiving the false result | Inner `instanceof` is true |
| `x instanceof String s && s.length() > 0` | Right-hand side of `&&`; `if` body when overall condition is true | Short-circuiting guarantees `instanceof` is true |
| `x instanceof String s || ...` | Cannot use `s` on the right-hand side from the left condition alone | Right-hand side runs when `instanceof` is false |
| `!(x instanceof String s) || s.isBlank()` | Right-hand side of `||` | Right-hand side runs when the negation is false, meaning the pattern matched |

This table describes typical rules when `s` is declared by the pattern directly in the expression. For complex conditions, you must consider early-exit branches, negations, and specific paths; do not guess scope based on where the identifier `s` appears in the source code.

## 7. Flow scoping in loops

A loop's condition expression can also contain a pattern. In the following example, the `while` body only runs when the pattern matches:

```java
static void printOnce(Object value) {
    while (value instanceof String text && !text.isEmpty()) {
        System.out.println(text);
        break;
    }

    // System.out.println(text); // invalid outside the loop
}
```

The `text` variable can be used inside the loop body; after the loop, the program may not have entered the body at all, so it cannot be relied upon. Do not confuse this with `do ... while`: the `do` body executes **before** the loop-end condition is checked, so you cannot use a pattern variable from that condition and assume it exists in the loop body.

When a condition has multiple patterns or multiple branches, splitting the checks into separate statements often makes the scope easier to read.

## 8. Flow scoping in Java 21 `switch` pattern matching

A pattern variable in a `case` label is in scope in its **`when` guard** and the corresponding body when the pattern matches; it does not automatically carry over to other `case` branches.

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text when !text.isBlank() -> "text: " + text.strip();
        case String ignored -> "blank text";
        case Integer number -> "number: " + number;
        default -> "other";
    };
}
```

- In the first `String text` branch, `text` is already a `String`, so it can be used directly in `when` and the result expression.
- If the `when` guard is not satisfied, the `switch` continues evaluating subsequent matching branches; `ignored` in the next `String` branch is **a different pattern variable**.
- In the `Integer number` branch, there is no `text` variable. Each pattern's name and scope are tied to its respective branch.
- `case null` explicitly handles a `null` selector; if this branch is omitted, a pattern switch on a reference value normally throws `NullPointerException` when the selector is `null`, even if `default` is present.

With **record patterns**, for example `case Point(var x, var y)`, the variables `x` and `y` are also brought into the scope of that branch when the record pattern matches. Flow scoping decides **where** variables can be used; the record pattern itself decides **which data** is extracted.

## 9. Common mistakes

**Using a pattern variable outside a definitely matched path.** If you use `text` in an `else` block after `if (value instanceof String text)`, or after an `if` where execution can continue from both sides, the compiler will reject it.

**Confusing `&&` with `||`.** For `value instanceof String text && text.length() > 0`, the right-hand side is guarded by the match. For `value instanceof String text || text.length() > 0`, the right-hand side runs when the match fails.

**Ignoring the effect of `!`.** The condition `!(value instanceof String text)` is true when the pattern does *not* match. After a negated guard clause with `return` or `throw`, the statements that continue executing are the ones guaranteed to have `text`.

**Thinking flow scoping validates business data.** `value instanceof String text` confirms the string type, not that the string is non-empty, a valid email format, or satisfies business rules. Those still require additional conditions or validation.

**Trying to use a variable from one `switch` branch in another.** Each branch has its own pattern scope; extracting shared logic into a method is cleaner.

**Assuming Java 21 requires preview flags.** Type patterns for `instanceof` have been a standard feature since Java 16; pattern matching for `switch` and record patterns are finalized in Java 21. The corresponding examples below do not need `--enable-preview`.

## 10. Complete runnable program on JDK 21

Create the file **`FlowScopingDemo.java`**:

```java
public class FlowScopingDemo {
    static String normalize(Object value) {
        if (!(value instanceof String text)) {
            return "not a string";
        }
        if (text.isBlank()) {
            return "blank";
        }
        return text.trim().toUpperCase();
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String text when !text.isBlank() -> "text:" + text.trim();
            case String ignored -> "blank string";
            case Integer number -> "int:" + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object value = "  Java  ";
        if (value instanceof String text && !text.isBlank()) {
            System.out.println("if=" + text.trim());
        }

        System.out.println("guard=" + normalize(value));
        System.out.println("mismatch=" + normalize(42));
        System.out.println("blank=" + normalize(" "));
        System.out.println("switch=" + classify("  scope  "));
        System.out.println("switchBlank=" + classify(""));
        System.out.println("switchNull=" + classify(null));
    }
}
```

Compile and run:

```bash
javac --release 21 FlowScopingDemo.java
java FlowScopingDemo
```

Exact stdout:

```text
if=Java
guard=JAVA
mismatch=not a string
blank=blank
switch=text:scope
switchBlank=blank string
switchNull=null
```

Execution flow explanation:

1. `value instanceof String text` is true; `&& !text.isBlank()` is evaluated and allows printing `text.trim()`.
2. In `normalize`, the negated condition is false so the `return "not a string"` branch is skipped; from there `text` is in scope for the rest of the code.
3. `normalize(42)` does not match `String`, so it exits early. `normalize(" ")` matches the type but fails the `isBlank()` check.
4. In `classify`, `text` is only in scope in the guarded `String` case; the fallback `String ignored` branch handles empty/blank strings. `case null` explicitly returns `"null"`.

## 11. Quick way to reason about scope

When unsure whether a pattern variable can be used on a given line, answer in order:

1. **Which expression introduces the variable?** For example, `value instanceof String text` or `case String text`.
2. **To reach the current line, what must necessarily be true?** If a path exists where the pattern has not matched, you cannot use that variable.
3. **Are there short-circuiting, negation, or early exits?** `&&`, `||`, `!`, `return`, and `throw` can change which paths are proven safe.
4. **Which branch are we in?** A pattern variable from one `switch` branch or one `if` body is not automatically shared with other branches.

Flow scoping helps Java maintain type safety even in complex branching conditions: **a pattern variable only appears where the compiler knows the pattern succeeded**. Understanding this rule helps you leverage pattern matching to reduce casts, write concise guard clauses, and avoid compilation errors when combining multiple conditions.
