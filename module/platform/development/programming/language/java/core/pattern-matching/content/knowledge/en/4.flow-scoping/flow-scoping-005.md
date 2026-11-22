# Variable Scope After the Negation Operator in Java Flow Scoping

**Topic:** Java Core Pattern Matching → Flow scoping  
**Version:** Java 17 and later. Pattern matching for `instanceof` has been a standard feature since Java 16.

## 1. The Core Problem

With the expression `value instanceof String text`, the pattern variable `text` is only meaningful at points where the compiler can prove that the object has matched the `String` type. When the negation operator `!` is added, the boolean result is inverted:

```java
value instanceof String text       // true  => matched String
!(value instanceof String text)    // false => matched String
```

Therefore, **after a negated expression**, the valid scope of `text` depends on which control-flow branch definitely proves that the original `instanceof` condition is `true`. This is the *flow scoping* rule (control-flow-based scoping), not merely scoping determined by curly braces.

Key point to remember: `!` only inverts the **boolean value** of the check; it does not turn a non-`String` value into a `String` and does not make the pattern variable available in every branch.

## 2. Analyzing the Two Branches of a Negated `if`

Consider the code snippet where `value` is an `Object`:

```java
if (!(value instanceof String text)) {
    System.out.println("Không phải String");
    // Cannot use text here.
} else {
    System.out.println(text.length()); // Valid.
}
```

Reasoning table:

| Result of `value instanceof String text` | Negated result | Branch executed | Can `text` be used? |
| --- | --- | --- | --- |
| `true` | `false` | `else` | Yes: the pattern matched |
| `false` | `true` | `if` | No: the pattern did not match |

If `value == null`, `instanceof String text` evaluates to `false`, so the negated condition is `true`. In the example above, `null` enters the `if` branch; in that branch, `text` has no value to use.

The parenthesized syntax `!(value instanceof String text)` is crucial. It negates the entire `instanceof` check. Writing `!value instanceof String text` does not express the intended logic and is invalid when `value` has type `Object`.

## 3. Why Can the Pattern Variable Be Used **After** `if`?

This is the most important case:

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length(); // Valid in Java 17+.
}
```

If `value` is not a `String` (including `null`), the program executes `return -1`; there is no path from this branch to the `return text.length()` line. To reach the line after the `if`, the negated condition must be `false`, which means `instanceof` matched. The compiler therefore allows using `text`.

This is not an arbitrary exception. Java has a rule: for the form `if (condition) statement`, a pattern variable introduced when `condition` is `false` can be brought into scope for the statements that follow if **the `statement` branch cannot complete normally** (*cannot complete normally*). An unconditional `return` or `throw` statement is a typical example.

Variant using `throw`:

```java
static String requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Cần String");
    }
    return text.trim(); // Valid.
}
```

With `throw`, the non-matching path terminates with an exception, so the continuing path has also proven that the pattern matched.

This technique is commonly called a **guard clause**: check for invalid input at the beginning of a method, exit early, and then write the main logic with shallow nesting.

## 4. When Is the Variable Still **Invalid** After `if`?

If the negated condition branch can complete normally, control flow can still continue without the pattern having matched:

```java
// Example that DOES NOT COMPILE:
static int invalid(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Không phải chuỗi");
    }
    return text.length(); // Error: text is not guaranteed to be assigned a value.
}
```

The `if` branch above only prints a line and then continues. With `value = 42` or `null`, the program would reach `return text.length()` even though `text` never matched. Java rejects this code at compile time.

Similarly, inside **the negated `if` branch itself**, `text` cannot be accessed:

```java
// Example that DOES NOT COMPILE:
if (!(value instanceof String text)) {
    // System.out.println(text.length()); // text is out of scope.
}
```

Having curly braces `{ ... }` does not automatically bring the pattern variable into existence. Variable scope depends on which branch guarantees that the type check succeeded.

## 5. Effect of `!` When Combined with `||` and `&&`

Short-circuit logical operators must be read according to **the condition under which the right-hand operand is evaluated**.

### 5.1. Negation combined with `||`: valid

```java
static boolean isNonBlankText(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return false;
    }
    return true;
}
```

The right-hand side of `||` is only evaluated when the left-hand side is `false`. With the left-hand side `!(value instanceof String text)`, that means `value` **has matched** `String text`. Thus `text.isBlank()` is valid and will not be called on a value of another type. If `value` is `null`, the left-hand side is `true` and Java does not evaluate the right-hand side.

You can leverage this reasoning after a guard:

```java
static String normalizeNonBlank(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "INVALID";
    }
    return text.strip(); // Valid: the || condition above must be false.
}
```

To reach `return text.strip()`, both sides of `||` must be `false`. That proves `text` is a non-blank `String`.

### 5.2. Negation combined with `&&`: completely different

```java
// Example that DOES NOT COMPILE:
// if (!(value instanceof String text) && text.isBlank()) {
//     System.out.println("Không hợp lệ");
// }
```

The right-hand side of `&&` only runs when the left-hand side is `true`: that is, `instanceof` **did not match**, so the variable `text` cannot be used there.

If the goal is to check for a String with content, the non-negated form is also very clear:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
```

In this example, `&&` only evaluates `!text.isBlank()` after `value instanceof String text` succeeds.

### 5.3. Easy-to-remember rules

| Expression on the left | Operator | When does the right-hand side run? | Is `text` valid on the right-hand side? |
| --- | --- | --- | --- |
| `value instanceof String text` | `&&` | When `String` matches | Yes |
| `value instanceof String text` | `\|\|` | When `String` does not match | No |
| `!(value instanceof String text)` | `\|\|` | When `String` matches | Yes |
| `!(value instanceof String text)` | `&&` | When `String` does not match | No |

This analysis applies to `&&` and `||`, which have short-circuit behavior; it should not be assumed to apply similarly to `&` or `|`, which evaluate both sides.

## 6. Complete Java 17+ Program Example

Create the file **`NegatedInstanceofScopeDemo.java`**:

```java
public class NegatedInstanceofScopeDemo {
    static String normalize(Object value) {
        if (!(value instanceof String text)) {
            return "NOT_STRING";
        }
        return "TEXT:" + text.trim().toUpperCase(java.util.Locale.ROOT);
    }

    static int lengthOrMinusOne(Object value) {
        if (!(value instanceof String text)) {
            return -1;
        }
        return text.length();
    }

    static boolean isNonBlankText(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return false;
        }
        return true;
    }

    static void showElse(Object value) {
        if (!(value instanceof String text)) {
            System.out.println("OTHER");
        } else {
            System.out.println("MATCH=" + text.length());
        }
    }

    public static void main(String[] args) {
        System.out.println(normalize("  java  "));
        System.out.println(normalize(42));

        System.out.println("len=" + lengthOrMinusOne("abc"));
        System.out.println("len=" + lengthOrMinusOne(null));

        System.out.println("nonBlank=" + isNonBlankText("   "));
        System.out.println("nonBlank=" + isNonBlankText("Java"));

        showElse("abc");
        showElse(null);
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 NegatedInstanceofScopeDemo.java
java NegatedInstanceofScopeDemo
```

Exact output:

```text
TEXT:JAVA
NOT_STRING
len=3
len=-1
nonBlank=false
nonBlank=true
MATCH=3
OTHER
```

**Matching each group of results:**

1. `normalize("  java  ")` passes the guard, is allowed to use `text` after `if`, trims leading and trailing whitespace, and converts it to `JAVA`. `42` does not match `String`, so it returns `NOT_STRING`.
2. `lengthOrMinusOne("abc")` returns `3`, while `lengthOrMinusOne(null)` returns `-1` because `instanceof` with `null` is `false`.
3. `isNonBlankText("   ")` returns `false` because `isBlank()` is `true`; `"Java"` yields `true`.
4. In `showElse`, only the `else` branch can use the `text` variable; `"abc"` prints `MATCH=3`, while `null` prints `OTHER`.

The program uses type patterns for `instanceof` and standard methods available in JDK 17; no preview features need to be enabled.

## 7. `continue`, `break`, and Scope Inside Loops

The reason a guard clause works is that the non-matching path **cannot reach the subsequent statements in that same flow**. Inside a loop, `continue` is also useful: it jumps to the next iteration.

Illustrative example placed inside a method:

```java
for (Object item : items) {
    if (!(item instanceof String text)) {
        continue;
    }
    System.out.println(text.length()); // Valid in this iteration.
}
```

In each iteration, if `item` is not a `String`, `continue` skips the print statement. If execution reaches the print statement, `text` has matched. The closing brace of the loop defines the end of this usage scope; `text` is not carried over to another iteration.

With `break`, you need to look at the exact exit target: `break` can terminate the loop, but it does not guarantee that the variable exists outside the enclosing construct. Reason based on the actual execution paths rather than guessing solely from the presence of the `break` or `continue` keyword.

## 8. Common Mistakes

- **Confusing the branches:** assuming `text` exists inside `if (!(value instanceof String text))`. In reality, this branch represents the pattern **not matching**.
- **Omitting the exit condition:** changing `return` to `println` in the guard while still using `text` after `if`. When the non-matching branch can fall through, the compiler does not allow the variable.
- **Confusing `&&` with `||`:** after a negation, `||` is what allows the right-hand side to use the matched pattern variable; `&&` does not.
- **Forgetting `null`:** `null` never matches the type pattern `instanceof String text`, so the negated condition evaluates to `true`.
- **Using the variable across arbitrary blocks:** flow scoping is tied to proving the type along each path; you cannot extend a variable's scope simply by widening curly braces.
- **Confusing with the traditional type check:** `value instanceof String` does not declare `text` on its own; only the `value instanceof String text` syntax introduces a pattern variable.
- **Relying on runtime values to fix compile errors:** even if the author knows a parameter is "always a String", the compiler must still verify it from the control-flow structure and static types.

## 9. Self-Practice

1. Predict which branch executes when passing `"hello"`, `10`, and `null` to the condition `if (!(value instanceof String s))`. In which branch can `s.length()` be called?
2. Change `return -1` in `lengthOrMinusOne` to `System.out.println("invalid")`; try compiling and explain why the line `return text.length()` is invalid.
3. Write a guard using `throw new IllegalArgumentException(...)` when the object is not a `String`, then return the trimmed string (`trim()`) at the end of the method.
4. Compare `!(value instanceof String s) || s.isBlank()` with `!(value instanceof String s) && s.isBlank()`; determine which expression compiles and why.
5. Write a `for (Object item : items)` loop, use `continue` to skip non-`String` values, and then print the length of each valid string.

**Passing criteria:** be able to explain why `!` moves the *pattern matched* condition to the `false` branch, prove when the variable exists after a guard, and identify scoping errors in compound `&&`/`||` conditions.

**Official references:** [Java Language Specification, §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3) and [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394).
