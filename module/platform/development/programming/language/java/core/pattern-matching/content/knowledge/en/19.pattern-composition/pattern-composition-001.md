# Combining Type Patterns with the `&&` Operator in Java 17+

## 1. Goal and Core Idea

When a value has a broad declared type such as `Object`, we often need to check its **actual type** before using methods that only exist on a specific type. Since Java 16, *pattern matching for `instanceof`* (JEP 394) allows checking the type and declaring a type-checked variable at the same time:

~~~java
Object input = "Java";
if (input instanceof String text) {
    System.out.println(text.length()); // 4
}
~~~

When combined with the **short-circuit AND operator `&&`**, we can immediately use the pattern variable in subsequent conditions without manual casting:

~~~java
Object input = "Java";

if (input instanceof String text && text.length() >= 4) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

How to understand this accurately:

- `input instanceof String text` is a **type pattern**. If it succeeds, the variable `text` is bound to the matched `String` object.
- `&&` evaluates from left to right and **only evaluates the right-hand side if the left-hand side returns `true`**.
- Therefore, when execution reaches `text.length() >= 4`, Java knows for certain that `input` matched `String` and `text` has been assigned a value.
- The `if` body only runs when **both** the type check and the length condition are true. Inside that body, `text` has the static type `String`.

This is the **flow scoping** rule: the scope in which a pattern variable can be used depends on the control flow guaranteeing that the match succeeded. This lesson uses Java 17+ syntax; this feature was standardized in Java 16, so `--enable-preview` is **not** needed on Java 17.

## 2. Comparison with the Traditional Approach

Before type patterns existed, programs were commonly written as:

~~~java
Object value = "Spring";

if (value instanceof String) {
    String text = (String) value;
    if (!text.isBlank() && text.length() >= 4) {
        System.out.println(text.toUpperCase()); // SPRING
    }
}
~~~

With a type pattern and `&&`, the entire condition can be expressed more clearly:

~~~java
Object value = "Spring";

if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 4) {
    System.out.println(text.toUpperCase()); // SPRING
}
~~~

The key difference is not just fewer lines: the compiler connects the **type match result** to the **existence of the pattern variable** in subsequent operands. There is no need to write `(String) value` again.

**Note:** `instanceof String text` returns `false` when `value == null`. Therefore, you do not need to add `value != null` before `instanceof` to guard this expression itself.

## 3. Why Does `&&` Allow Using the Variable on the Right-Hand Side?

The `&&` operator has three important characteristics:

1. It evaluates the **left operand first**, and only then decides whether to run the right operand.
2. If the left operand is `false`, the result of the entire expression is `false`; the right operand is **completely skipped** (*short-circuit*).
3. When the right operand is evaluated, a type pattern on the left that returned `true` has already bound its pattern variables.

Consider:

~~~java
Object value = "JVM";

boolean valid = value instanceof String s
        && s.startsWith("J")
        && s.length() >= 3;

System.out.println(valid); // true
~~~

Actual execution order:

- Step 1: `value instanceof String s` matches; `s` holds the value `"JVM"`.
- Step 2: `s.startsWith("J")` returns `true`.
- Step 3: `s.length() >= 3` returns `true`.
- The result `valid` is `true`.

If `value` is `42` or `null`, step 1 returns `false`; the two method calls on `s` **do not run**. If `value` is `"Go"`, step 1 succeeds but step 2 returns `false`; step 3 does not run.

You can add parentheses for clarity: `(value instanceof String s) && s.length() >= 3`. Parentheses only aid readability; `instanceof` is already parsed before `&&` according to operator precedence.

## 4. Flow Scoping: Where Can a Pattern Variable Appear?

### 4.1. Right-hand side of `&&` and the true branch of `if`

~~~java
static void printUpper(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        // Both the type match and the additional condition are true.
        System.out.println(text.toUpperCase());
    }
}
~~~

`text` is allowed to appear on the right-hand side of `&&` and in the `if` body. In both places, a successful match is guaranteed.

### 4.2. Not automatically usable in `else`

~~~java
// Intentionally WRONG example — do not include in a runnable program.
if (input instanceof String text && text.length() > 3) {
    System.out.println(text);
} else {
    // System.out.println(text); // Compile error: text is not guaranteed to have matched.
}
~~~

The `else` branch may execute either because `input` is not a `String`, or because `input` is a `String` that is too short. The compiler cannot guarantee that `text` is bound on **every** path entering `else`.

### 4.3. Not automatically usable after the `if` statement

~~~java
// Intentionally WRONG example.
if (input instanceof String text && text.length() > 3) {
    System.out.println(text);
}
// System.out.println(text); // No match guarantee after a normal if statement.
~~~

A variable declared by a type pattern does not become a local variable scoped across the whole method. It follows the *definitely matched* rule, not just the placement of curly braces.

### 4.4. Special case: early-return guard

If the control flow **eliminates all non-matching cases**, the variable can be used after the `if`:

~~~java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "Không phải chuỗi";
    }
    // Reaching here means instanceof String text succeeded.
    return text.trim();
}
~~~

This example is valid because the branch where the match could fail always exits the method with `return`. It illustrates that flow scoping is based on paths that can continue, not merely on line count.

## 5. Combining Multiple Type Patterns with `&&`

A single condition can introduce **multiple pattern variables**, each introduced at its respective position:

~~~java
Object left = "Go";
Object right = "Java";

if (left instanceof String a
        && right instanceof String b
        && a.length() < b.length()) {
    System.out.println(a + " ngắn hơn " + b); // Go ngắn hơn Java
}
~~~

Execution flow:

1. `left instanceof String a` must succeed; otherwise it stops immediately.
2. `right instanceof String b` only runs after step 1; if it matches, `b` is bound.
3. At `a.length() < b.length()`, both `a` and `b` are guaranteed to have matched and have type `String`.
4. Inside the `if` body, both variables are usable.

Pattern variable names are chosen by the programmer; they do not have to match the input variable names. You should choose distinct names for variables appearing together in the same scope, such as `a`/`b` or `firstText`/`secondText`.

This is a useful combination when you need to check **two independent data sources** and then apply a condition involving both.

## 6. Combining Type Checks with Guards to Protect Subsequent Operations

`&&` is also useful for checking each precondition before an operation that could fail on invalid input.

Example with a list of unknown generic type:

~~~java
Object candidate = java.util.List.of("Spring", 42);

if (candidate instanceof java.util.List<?> list
        && !list.isEmpty()
        && list.get(0) instanceof String first
        && first.length() > 3) {
    System.out.println(first.toUpperCase()); // SPRING
}
~~~

- `candidate instanceof List<?> list`: only continues if the input is a `List`.
- `!list.isEmpty()`: ensures there is an element at index 0 before calling `get(0)`. Without this step, an empty list would cause `IndexOutOfBoundsException`.
- `list.get(0) instanceof String first`: checks the actual type of the first element and declares the pattern variable `first`.
- `first.length() > 3`: only runs after the first element is actually a `String`.

Here `List<?>` is used because generic type arguments cannot be verified directly with `instanceof List<String>` at runtime (*type erasure*). Verifying that the first element is a `String` is done separately with a type pattern.

If the list is empty or the first element is not a string, the entire expression is `false` and the `if` branch does not run. If the first element is `null`, `instanceof String first` returns `false`.

**Guard limitation:** short-circuiting only avoids running unnecessary operands. It does not automatically handle exceptions thrown inside an operand that has already been executed; for example, `get(0)` can still fail if the list contents are modified concurrently in an unsafe way between operations. When sharing data across multiple threads, proper synchronization and consistency rules are still required.

## 7. Comparing `&&`, `&`, and `||` in Conditions with Pattern Variables

| Operator | Evaluation Behavior | Can the pattern variable from the left type pattern be used in the right operand in the form below? |
| --- | --- | --- |
| `&&` | Short-circuit: right side only runs when left side is `true`. | **Yes**: `obj instanceof String s && s.length() > 0`. |
| `&` on booleans | Evaluates both operands; no short-circuiting. | **No**: `obj instanceof String s & s.length() > 0` does not guarantee `s` is bound. |
| `||` | Short-circuit: right side only runs when left side is `false`. | **No**: `obj instanceof String s || s.length() > 0`, because the right side runs when the left pattern did not match. |

The following snippets are **intentionally wrong** and do not belong in a runnable program:

~~~java
// Wrong: with ||, the right-hand side can run when it is not a String.
// if (obj instanceof String s || s.isEmpty()) { ... }

// Wrong: & does not short-circuit, s is not guaranteed to have matched on the right-hand side.
// if (obj instanceof String s & s.length() > 0) { ... }

// Wrong: s appears before it is introduced.
// if (s.length() > 0 && obj instanceof String s) { ... }
~~~

The key rule to remember is to **only use a pattern variable after the point where the corresponding type match is proven to have succeeded**. Do not replace `&&` with `&` thinking "it is still an AND operator"; the two operators have different evaluation behavior and different scoping rules.

`||` is not always unusable with pattern matching. For example, `!(obj instanceof String s) || s.isEmpty()` has a different flow structure: when the right side runs, the negation on the left was `false`, so the original pattern succeeded. However, in this lesson, the most readable and common pattern for checking a type and adding conditions remains `instanceof T variable && predicate(variable)`.

## 8. Static Type of a Pattern Variable and `null` Checks

A pattern variable has the **type declared in the type pattern**, and does not automatically expose all methods of a more specific runtime class:

~~~java
Object value = new StringBuilder("JVM");

if (value instanceof CharSequence seq
        && seq.length() >= 3
        && seq.charAt(0) == 'J') {
    System.out.println(seq); // JVM
}
~~~

Here `seq` has static type `CharSequence`. It can use `length()` and `charAt()` from that interface, but cannot arbitrarily call methods specific to `StringBuilder` without an appropriate type check or cast.

When the object on the left is `null`, `instanceof CharSequence seq` returns `false`, so no method calls are made on `seq`. Therefore, the following expression is null-safe for **the object being tested itself**:

~~~java
static boolean isLongString(Object value) {
    return value instanceof String s && s.length() >= 4;
}
~~~

However, if a later operand accesses **another value** that might be `null`, you still need to check it. For example:

~~~java
static boolean equalsIgnoreCase(Object input, String expected) {
    return input instanceof String s
            && expected != null
            && s.equalsIgnoreCase(expected);
}
~~~

The `instanceof` on `input` provides no guarantee about `expected`; the `expected != null` check is a rule for that separate input. (`String.equalsIgnoreCase(null)` itself returns `false`; the example includes the check to illustrate the principle of guarding another reference.)

## 9. Complete Runnable Example in Java 17+

Create the file **`TypePatternAndDemo.java`** with the following full contents:

~~~java
import java.util.List;

public class TypePatternAndDemo {
    static String describe(Object value) {
        if (value instanceof String text
                && !text.isBlank()
                && text.length() >= 4) {
            return "Chuỗi hợp lệ: " + text.toUpperCase();
        }
        return "Không đạt điều kiện";
    }

    static String compare(Object left, Object right) {
        if (left instanceof String a
                && right instanceof String b
                && a.length() < b.length()) {
            return a + " ngắn hơn " + b;
        }
        return "Không so sánh được";
    }

    static String firstLongString(Object value) {
        if (value instanceof List<?> list
                && !list.isEmpty()
                && list.get(0) instanceof String first
                && first.length() > 3) {
            return "Phần tử đầu: " + first;
        }
        return "Không có chuỗi đầu phù hợp";
    }

    static String classify(Object value) {
        if (value instanceof CharSequence seq
                && seq.length() > 2
                && seq.charAt(0) == 'J') {
            return "Bắt đầu bằng J: " + seq;
        }
        return "Khác";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe("  "));
        System.out.println(describe(null));
        System.out.println(compare("Go", "Java"));
        System.out.println(compare("Java", 5));
        System.out.println(firstLongString(List.of("Spring", 7)));
        System.out.println(firstLongString(List.of()));
        System.out.println(firstLongString(List.of(42)));
        System.out.println(classify(new StringBuilder("JVM")));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 TypePatternAndDemo.java
java TypePatternAndDemo
~~~

Output:

~~~text
Chuỗi hợp lệ: JAVA
Không đạt điều kiện
Không đạt điều kiện
Go ngắn hơn Java
Không so sánh được
Phần tử đầu: Spring
Không có chuỗi đầu phù hợp
Không có chuỗi đầu phù hợp
Bắt đầu bằng J: JVM
~~~

Function-by-function explanation:

- **`describe`** checks `String`, filters out whitespace-only strings, and then checks the length. For `null`, the `instanceof` operand is `false`, so the methods on `text` do not run.
- **`compare`** requires both objects to be `String` and then uses the two pattern variables `a` and `b` in the same condition.
- **`firstLongString`** ensures there is a list, there is a first element, and the first element is a string of sufficient length before returning the result.
- **`classify`** demonstrates that a type pattern can be used with the `CharSequence` interface, not only with the `String` class.

The example uses features available in Java 17; `String.isBlank()` was introduced in Java 11 and `List.of()` in Java 9.

## 10. Common Mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Reading a pattern variable on the right side of `||` after a positive `instanceof` | The right side of `||` runs when the left type check fails; the variable is not bound. | Use `&&` when you want to check the type first and then use the variable in the next condition. |
| Using `&` instead of `&&` | `&` does not short-circuit, leading to invalid variable scope and potentially evaluating an unsafe condition. | Use `&&` to ensure the subsequent condition only runs when the prior condition is true. |
| Referencing a pattern variable in the `else` of `if (obj instanceof T t && guard)` | The `else` branch does not guarantee `obj` matched `T`. | Only use `t` where control flow guarantees a match; restructure branches or use an early return. |
| Using a pattern variable after a normal `if` statement | There is no guarantee across all paths. | Restrict usage to the true branch or use a guard where the non-matching path exits immediately. |
| Checking `list.get(0) instanceof String s` before `!list.isEmpty()` | May throw `IndexOutOfBoundsException` on an empty list. | Place the existence check before the access operation. |
| Assuming the pattern variable has a more specific runtime type than declared | Calling methods not present on the static type causes a compile error. | Choose the appropriate type pattern (e.g., `String s`) or perform an additional type check before using specialized APIs. |
| Assuming `&&` automatically catches all exceptions | Operands that do execute can still throw exceptions. | Check all preconditions thoroughly and manage shared data properly. |
| Casting again after `instanceof T t` succeeds | Makes the code verbose and unnecessarily error-prone. | Use `t` directly, as it already has static type `T`. |

## 11. Self-Check Exercises

**Exercise 1.** Given `Object value`, write a boolean expression that returns `true` when `value` is a string with at least 5 characters and starts with `"A"`, using **one** type pattern with `&&`.

**Exercise 2.** Given `Object left, right`, print their sum only when both are `Integer` and the sum is greater than 10. Use two type patterns and `&&`, then explain where both variables can be used simultaneously.

**Exercise 3.** Identify the error in the following snippet and fix it:

~~~java
// Intentionally does not compile:
if (value instanceof String s || s.length() > 2) {
    System.out.println("OK");
}
~~~

**Exercise 4.** Why is the condition `value instanceof List<?> list && !list.isEmpty() && list.get(0) instanceof String first` safer than calling `list.get(0)` before checking `isEmpty()`? What happens if the first element is `null`?

**Suggested Answers:**

~~~java
// 1
boolean accepted = value instanceof String text
        && text.length() >= 5
        && text.startsWith("A");

// 2
if (left instanceof Integer a
        && right instanceof Integer b
        && a + b > 10) {
    System.out.println(a + b);
}

// 3
if (value instanceof String s && s.length() > 2) {
    System.out.println("OK");
}
~~~

In Exercise 2, `a` and `b` can be used in the third condition and inside the `if` body after both respective matches succeed. For Exercise 4, short-circuiting ensures `get(0)` is not called on an empty list; if the first element is `null`, then `instanceof String first` is `false` and `first` is not used afterward.

## 12. Summary of Applied Knowledge

The general pattern to remember is:

~~~java
if (expression instanceof TargetType variable
        && conditionUsing(variable)) {
    // variable is bound and has static type TargetType.
}
~~~

When combining multiple type patterns, place **type checks and preconditions** first, and **operations using the pattern variable** afterward. `&&` guarantees short-circuiting; *flow scoping* ensures the variable can only be used in places where the corresponding type match is guaranteed to have succeeded.

### References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): standardizes the type pattern syntax in `instanceof` since Java 16.
- [Java Language Specification 17 — §6.3: Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): scoping rules for pattern variables.
- [Java Language Specification 17 — §15.23: Conditional-And Operator `&&`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.23): short-circuit evaluation of `&&`.
- [Oracle Java — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): examples of using type patterns and flow scoping.
