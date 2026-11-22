# Combining `instanceof` with Return Expressions in Java

## 1. Why does `instanceof` often appear directly inside `return`?

When receiving a value with a broad declared type such as `Object`, a program may need to answer two questions: **does the value belong to a specific type?** and **if so, what result should be returned?** Java allows combining the type check directly within a return expression. This approach works well for short methods such as validating input, normalizing a string, getting a length, or choosing a default value.

Let us distinguish three concepts:

- **`instanceof` is an operator that produces a boolean expression.** For example, `value instanceof String` evaluates to `true` or `false`; by itself, it does not return a string.
- **A type pattern** in `value instanceof String text` still produces a boolean value, but also declares the variable `text` of type `String` when the pattern matches.
- **`return` returns the value of the expression that follows it.** That expression can be an `instanceof` check, a combined `&&` expression, or a conditional `?:` expression. The result type must match the method's return type.

A minimal example that can be placed inside a Java class:

```java
static boolean isString(Object value) {
    return value instanceof String;
}
```

With `isString("Java")`, the result is `true`; with `isString(17)` or `isString(null)`, the result is `false`. When only a yes/no answer is needed, there is no need to declare a pattern variable and leave it unused.

The goal of this lesson is to understand **how the expression is evaluated, where the pattern variable is in scope, what type the `return` result has, and how to avoid errors with `null`**. All main practical examples use features stable since Java 16 and run on Java 17 or later.

## 2. Returning the Result of a Type Check Directly

### 2.1. Methods returning `boolean`

The verbose way:

```java
static boolean isText(Object value) {
    if (value instanceof String) {
        return true;
    }
    return false;
}
```

The same behavior can be expressed more concisely:

```java
static boolean isText(Object value) {
    return value instanceof String;
}
```

Here, `instanceof` itself returns a `boolean`; there is no need to write `? true : false`. The examples above illustrate **two alternative implementations of the same method**, and should not be placed together in the same class with the same signature.

Note: `instanceof` checks the runtime type relationship of the object, not the string's content. `"Java"`, `""`, and `"   "` are all `String` instances, so `isText` returns `true`. Checking whether the value is useful requires adding another condition in a later step.

### 2.2. Combining with `&&` to return a more meaningful condition

Java allows using a **pattern variable** on the right-hand side of `&&` after the left-hand side confirms the type:

```java
static boolean hasNonBlankText(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

The expression executes in order:

1. Check `value instanceof String text`.
2. If it **does not match**, `&&` immediately returns `false`; Java **does not** call `text.isBlank()`.
3. If it **matches**, `text` is guaranteed to be a `String`, and the right-hand side checks its content.
4. `return` returns the boolean value of the entire expression.

Because `instanceof` does not match `null`, `hasNonBlankText(null)` returns `false` without throwing a `NullPointerException`. With `""` or `"  "`, the result is also `false` because `String.isBlank()` treats empty strings or strings containing only whitespace characters as blank.

This is an example of **short-circuit evaluation**: the right-hand side of `&&` only runs when the left-hand side is `true`. Pattern variable syntax helps you avoid manual casting and directly links the type check with the data validation condition.

### 2.3. Adding multiple constraints while keeping the condition safe

```java
static boolean isValidAge(Object value) {
    return value instanceof Integer age && age >= 0 && age <= 120;
}
```

If `value` is `"18"` (a string), the method returns `false`, even though the content looks like a number. Pattern matching **does not automatically parse** a string into an integer. If `value` is `Integer.valueOf(18)`, all three conditions evaluate to `true`.

The advantage of this style is that the return expression accurately reflects the rule: *it must be an `Integer` and within the allowed range*. When rules have multiple branches or require distinct error messages, split them into `if` statements for better readability and testability.

## 3. Using `instanceof` in the Conditional Operator `?:`

If a method needs to return a **non-boolean** value, you can use the conditional operator:

```java
static int textLengthOrZero(Object value) {
    return value instanceof String text ? text.length() : 0;
}
```

In the expression `condition ? whenTrue : whenFalse`:

- `value instanceof String text` is the boolean condition.
- The branch after `?` is chosen when the pattern matches; at this point `text` is in scope and `text.length()` returns an `int`.
- The branch after `:` is chosen when the pattern does not match, including for `null`; the result is `0`.
- Both branches return a type compatible with the method's `int` return type.

For example, `textLengthOrZero("Java")` returns `4`, `textLengthOrZero(42)` returns `0`, and `textLengthOrZero(null)` returns `0`. The value `0` here is **a default chosen by the programmer**, not an automatic behavior of `instanceof`.

### 3.1. A pattern variable is only available in the branch proven to match

```java
static String label(Object value) {
    return value instanceof String text
            ? "Chuỗi: " + text.strip()
            : "Không phải chuỗi";
}
```

`text` can be used in the `?` branch because execution can only enter that branch when `instanceof` returns `true`. You cannot assume `text` exists in the `:` branch.

An **invalid example that does not compile**:

```java
static int invalidLength(Object value) {
    return value instanceof String text ? 0 : text.length();
    // WRONG: the ':' branch runs when value does not match String.
}
```

If you need to handle both cases using a single variable, declare a shared variable with an appropriate type and value, or use `if` with two independent return paths. Do not try to use a pattern variable outside the path where the type has been confirmed.

### 3.2. Combining `&&` with `?:` to choose the returned data

```java
static String displayName(Object value) {
    return (value instanceof String text && !text.isBlank())
            ? text.strip()
            : "(không có tên hợp lệ)";
}
```

Both the type check and the content check must be true for the `?` branch to run. Adding parentheses around the condition helps readers clearly see the entire condition of the `?:` operator. `String.strip()` removes leading and trailing whitespace according to Java's rules; it only runs after Java has confirmed that `text` is a `String`.

The `?:` expression is suitable when both branches are short and express a single decision. If the branches are long, deeply nested, or throw different exceptions, `if/else` is usually clearer.

## 4. Combining `instanceof` with Early `return`

You do not always need to use the `?:` operator. When a value of the wrong type needs to exit immediately, use a **guard clause** and return early:

```java
static int lengthAfterGuard(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

Because the non-matching branch already executes `return`, every execution path reaching the final statement is guaranteed to have matched `value` as a `String`. Therefore, `text` is valid after the `if`. This control-flow-based scoping mechanism is called **flow scoping**.

Compare with the single-expression style:

```java
static int lengthWithConditional(Object value) {
    return value instanceof String text ? text.length() : 0;
}
```

Both return the length if the input is a `String`, and `0` otherwise. They are **two differently named methods** to illustrate stylistic choices:

- Use `?:` when the choice is very short.
- Use `if` + early `return` when you need to explain why an input is rejected or when there are multiple processing steps after the check.

Note the pattern variable scope after a standard condition:

```java
static int simpleIf(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
}
```

`text` is in scope inside the matching `if` branch. The code below is **invalid** because the last line can run even when the pattern does not match:

```java
static int invalidScope(Object value) {
    if (value instanceof String text) {
        System.out.println("Đã khớp");
    }
    return text.length(); // WRONG: text is not guaranteed to be definitely assigned here.
}
```

The difference lies in which paths can reach the `return` statement, not just the position of the curly braces.

## 5. How Do `&&`, `||`, and `!` Affect Pattern Variables?

Beginners often assume that simply seeing `instanceof String text` makes `text` usable everywhere afterward. In reality, Java only allows using the variable in locations where the execution path is guaranteed to have matched the pattern.

| Expression | Valid? | Why? |
| --- | --- | --- |
| `return value instanceof String text && text.length() > 2;` | Yes | When evaluating the right-hand side of `&&`, the left-hand side is already true |
| `return value instanceof String text ? text.length() : 0;` | Yes | The `?` branch only runs when the pattern matches |
| `return !(value instanceof String text) || text.isBlank();` | Yes | The right-hand side of `||` only runs when the negation is false, meaning the pattern matched |
| `return value instanceof String text || text.isBlank();` | No | When the left-hand side is false, `text` is not bound |
| `return value instanceof String text ? 0 : text.length();` | No | The `:` branch runs when the pattern does not match |

A **valid** example with negation and `||`:

```java
static boolean shouldReject(Object value) {
    return !(value instanceof String text) || text.isBlank();
}
```

Explanation: reject if the value is not a `String` **or** if it is a `String` that is blank. When `value` has the wrong type, the left-hand side of `||` is true and Java does not evaluate the right-hand side. When the value has the right type, the negation is false, so the right-hand side runs and `text` is already in scope.

An **invalid** example:

```java
static boolean invalidOr(Object value) {
    return value instanceof String text || text.isBlank();
    // WRONG: if the left-hand side is false, the right-hand side tries to use an unbound text.
}
```

It can be fixed as:

```java
static boolean isStringOrFallback(Object value, boolean fallback) {
    return value instanceof String || fallback;
}
```

If you only need to combine two independent booleans, there is no need to use a pattern variable. In particular, avoid mechanically replacing `&&` with `&` or `||` with `|`: non-short-circuiting operators evaluate both sides and do not provide the same variable scoping guarantees.

## 6. Complete Example Running on Java 17

The following program brings together four cases: returning a boolean, returning the result of `?:`, leveraging an interface broader than `String`, and exiting early with `return`. It uses Java 17 and does not require `--enable-preview`.

Save the entire code as **`InstanceofReturnDemo.java`**:

```java
public class InstanceofReturnDemo {
    static boolean isNonBlankText(Object value) {
        return value instanceof String text && !text.isBlank();
    }

    static String display(Object value) {
        return (value instanceof String text && !text.isBlank())
                ? text.strip()
                : "(trống hoặc sai kiểu)";
    }

    static int textLength(Object value) {
        return value instanceof CharSequence text ? text.length() : 0;
    }

    static String describe(Object value) {
        if (value instanceof Integer number) {
            return "int=" + number;
        }
        if (value instanceof String text) {
            return "str=" + text.strip();
        }
        return "other";
    }

    static boolean shouldReject(Object value) {
        return !(value instanceof String text) || text.isBlank();
    }

    static int lengthAfterGuard(Object value) {
        if (!(value instanceof String text)) {
            return 0;
        }
        return text.length();
    }

    public static void main(String[] args) {
        System.out.println(isNonBlankText("  Java  "));
        System.out.println(isNonBlankText(" \t "));
        System.out.println(isNonBlankText(null));

        System.out.println(display("  Java  "));
        System.out.println(display(12));
        System.out.println(textLength(new StringBuilder("xyz")));

        System.out.println(describe(7));
        System.out.println(describe("  A  "));
        System.out.println(describe(null));

        System.out.println(shouldReject("  "));
        System.out.println(shouldReject("OK"));

        System.out.println(lengthAfterGuard("Hello"));
        System.out.println(lengthAfterGuard(25));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 InstanceofReturnDemo.java
java InstanceofReturnDemo
```

Expected output:

```text
true
false
false
Java
(trống hoặc sai kiểu)
3
int=7
str=A
other
true
false
5
0
```

Explanation of notable lines:

- `isNonBlankText(null)` is `false` because the `instanceof` operator does not match `null` and `&&` short-circuits.
- `display("  Java  ")` returns `Java`: the input is a non-blank `String`; then `strip()` removes leading and trailing whitespace.
- `textLength(new StringBuilder("xyz"))` returns `3`: `StringBuilder` implements `CharSequence`. Pattern matching is not limited to `String`; the variable `text` has the static type `CharSequence`.
- `describe(7)` returns `int=7` via the `Integer` branch. `describe(null)` reaches `return "other"`.
- `shouldReject("  ")` is `true` because the string is blank; `shouldReject("OK")` is `false`.
- `lengthAfterGuard(25)` returns `0` immediately at the guard branch, without calling `text.length()` on the wrong-typed value.

You can try replacing `new StringBuilder("xyz")` with `"abc"` and `42` to observe both matching and non-matching branches. Remember that `text` in `textLength` has the type `CharSequence`, so only methods declared by that interface can be called.

## 7. Comparing Code Before and After Type Patterns

### 7.1. Avoiding a type check followed by a manual cast

The old style:

```java
static int lengthOld(Object value) {
    return value instanceof String
            ? ((String) value).length()
            : 0;
}
```

The pattern style:

```java
static int lengthNew(Object value) {
    return value instanceof String text
            ? text.length()
            : 0;
}
```

Both methods behave identically for `String` arguments, wrong-typed arguments, and `null`. The pattern version eliminates the repetitive cast and lets the compiler track that the variable already has the right type. This is an appropriate refactoring when the goal is actually to use the value after confirming its type.

### 7.2. Not every method should be written on one line

Suppose you need to return different messages for a wrong-typed value, a blank string, and a valid string:

```java
static String explain(Object value) {
    if (!(value instanceof String text)) {
        return "Đầu vào không phải String";
    }
    if (text.isBlank()) {
        return "Chuỗi không có nội dung";
    }
    return "Nội dung: " + text.strip();
}
```

This situation is well suited to multiple early `return` statements. A chain of nested `?:` expressions would be harder to follow and could cause readers to miss conditions. Furthermore, if an operation can throw an exception or needs contextual logging, splitting into `if` statements keeps the control flow clear.

### 7.3. Matching the return type completes the condition

For `boolean`, return the condition directly:

```java
static boolean isInteger(Object value) {
    return value instanceof Integer;
}
```

For `int`, you need an expression that produces an `int` in both branches:

```java
static int integerOrZero(Object value) {
    return value instanceof Integer number ? number : 0;
}
```

For `String`, choose two results that can be used as `String`:

```java
static String stringOrFallback(Object value) {
    return value instanceof String text ? text : "(mặc định)";
}
```

You cannot assume `instanceof` automatically turns into the required return type. The following example has the **wrong return type**:

```java
static String invalidReturn(Object value) {
    return value instanceof String;
    // WRONG: the expression has type boolean, but the method requires String.
}
```

When combining branches in `?:`, pay attention to type inference, numeric promotions, auto-boxing/unboxing, and the fact that one branch may be `null`. Do not mix unrelated results just to shorten code.

## 8. Reading Behavior with `null` and Non-Matching Values Correctly

Common scenarios:

| Input | `value instanceof String text` | Is `text` usable in the matching branch? | `return value instanceof String text ? text.length() : 0;` |
| --- | --- | --- | --- |
| `"Java"` | `true` | Yes, as `"Java"` | `4` |
| `""` | `true` | Yes, as the empty string | `0` |
| `"  "` | `true` | Yes, as a whitespace string | `2` |
| `Integer.valueOf(5)` | `false` | No | `0` |
| `null` | `false` | No | `0` |

Key point to remember: **`instanceof` checks the type, while `isBlank()` checks the content**. An empty `String` still matches the `String` pattern. Additionally, the `?:` operator only evaluates the selected branch; an expression in the other branch does not execute.

Pattern matching **is not an exception-handling mechanism**. If you call a method inside the matching branch and that method throws an exception for another reason, `instanceof` does not handle that exception automatically. Use appropriate conditions or explicit error handling when business logic requires it.

## 9. Common Mistakes and How to Fix Them

| Mistake | Fix |
| --- | --- |
| Writing `return value instanceof String text;` in a method returning `String` | An `instanceof` expression has type `boolean`; change the return type to `boolean` or select a `String` using `?:` |
| Using `text` after `instanceof` when a match is not guaranteed | Analyze flow scoping; place the variable usage inside the matching branch or after an early-return guard |
| Using `value instanceof String text \|\| text.isBlank()` | `text` is not in scope when the left-hand side of `\|\|` is false; use `&&` or invert the logic with negation if appropriate |
| Putting `text.length()` in the `:` branch when the condition is `instanceof String text` | The `:` branch is where the pattern did not match; return a default or use an independent expression |
| Assuming `instanceof` automatically converts `"12"` to `Integer` | Patterns do not auto-parse; if you need to convert a string to a number, use a dedicated conversion API with error handling |
| Assuming `instanceof` treats `null` as a `String` | Type patterns in `instanceof` never match `null` |
| Confusing `String.isBlank()` with checking whether a value has type `String` | Type and content are two independent conditions; order them with `&&` to avoid calling it on the wrong type |
| Writing multiple nested `?:` operators to handle complex logic | Choose `if/else` and early `return` statements with clear condition names |
| Using a type pattern on an expression whose static type is already guaranteed to be the target type | Avoid redundant patterns; some cases are rejected by Java because the pattern is statically guaranteed to match |
| Thinking the first `return` makes the next branch safe when it does not rule out all wrong-typed values | Check all paths reaching the subsequent statement and why the compiler knows the pattern has matched |

In the "wrong" examples in this lesson, the code is intentionally marked so you can read the compiler errors. When running code yourself, only copy examples marked valid or the complete program in Section 6.

## 10. Practice Exercises with Verification Criteria

**Exercise 1 — Boolean check:** Write `static boolean isPositiveInteger(Object value)` using a single `return` statement and `instanceof Integer n`. The method should return `true` when `n > 0`, and `false` otherwise. Test with `5`, `0`, `-3`, `"5"`, and `null`. Explain why the string `"5"` is not accepted.

**Exercise 2 — Choosing a result with `?:`:** Write `static String upperOrUnknown(Object value)`. When the input is a non-blank `String`, return the string after calling `strip()` and converting to uppercase with `toUpperCase(java.util.Locale.ROOT)`. If it is the wrong type or blank, return `"UNKNOWN"`. Use one clear `return` expression with `instanceof` and `&&`.

**Exercise 3 — Guard clause:** Write `static int countChars(Object value)`. If the input is not a `CharSequence`, return `0` immediately. If it is the right type, return `length()`. Do not use manual casting; test with `"ab"`, `new StringBuilder("abc")`, `new Object()`, and `null`.

**Exercise 4 — Reading compiler errors:** Given the expressions:
- `return input instanceof String text && text.length() > 1;`
- `return input instanceof String text || text.length() > 1;`
- `return !(input instanceof String text) || text.isBlank();`

Assume they are inside three `boolean` methods taking `Object input`. Classify them as valid or invalid, explain under what conditions each side runs, and then test them with the compiler. The key is to state **the execution path that guarantees the pattern variable is bound**.

**Exercise 5 — Choosing a style:** A method needs to return distinct messages for `null`, wrong type, blank string, and valid string. Write two versions: (a) using `?:` if it can remain clear, (b) using `if` + early `return`. Explain which version is easier to extend when more validation conditions are added and why.

Self-check hint: each method should have test cases for **valid type**, **wrong type**, **`null`**, and an appropriate **boundary** case. For methods returning `String`, verify both the value, letter casing, and whitespace. For booleans, avoid writing `? true : false` after a boolean expression.

## 11. Mastery Checklist Before Moving On

You have understood how to combine `instanceof` with return expressions when you can clearly explain:

1. Why `return value instanceof String;` is valid in a `boolean` method but invalid in a `String` method?
2. Does `value instanceof String text` produce a boolean or a `String`? Under what condition does `text` receive a value?
3. Why does `&&` prevent calling `text.isBlank()` on wrong-typed inputs and `null`?
4. Which branch of `condition ? x : y` can use the pattern variable, and why?
5. When is `!(value instanceof String text)` combined with `||` valid?
6. How does using an early `return` affect the scope of a pattern variable after an `if` statement?
7. When is a single `return` with `?:` easier to read, and when should multiple early `return` statements be used?

If you can answer these by reasoning through the execution flow and verify the Java 17 examples yourself, you are ready to move on to flow scoping or branching across multiple types. The core mindset here is **a type pattern check returns a boolean; control branches determine when the pattern variable is safe; `return` takes the result of an expression that matches the method's contract**.

## 12. References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): rules for type patterns and flow scoping, finalized in Java 16.
- [Java Language Specification, Java SE 17 — `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): semantics of the type comparison operator.
- [Java Language Specification, Java SE 17 — `?:`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.25): condition, evaluated branch, and result type.
- [Java Language Specification, Java SE 17 — Pattern variable scope](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): flow-scoped pattern variables.
