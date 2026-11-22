# Variable Scope in `while` Loops with Java Pattern Matching

## 1. The Problem: Where Does a Pattern Variable Exist in a Loop?

Since Java 16 (and in Java 17+), `instanceof` can use a **type pattern** to both test an object's type and declare a variable of the tested type:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

When placing that test into a `while` loop, two different questions must be answered:

1. **Inside the loop body**, when the condition is true, is the pattern variable usable?
2. **After the loop**, when the condition is false and causes the loop to stop, is the pattern variable usable?

The answer depends on *flow scoping*: Java analyzes control flow to determine whether a pattern variable is **definitely matched** at the point of use. Scope is not simply "from the point of declaration to the closing curly brace." In a `while` loop, the true or false result of the condition along with the exit paths from the loop determine this scope.

This lesson uses standard Java 17+ `instanceof` type patterns. The main rules are specified in the **Java Language Specification (JLS) 17, §6.3.2.3 — `while` Statements**.

## 2. Matching `while` Condition: Variable Usable in the Loop Body

Example:

```java
Object value = "hello";
while (value instanceof String text) {
    System.out.println(text.toUpperCase());
    value = 10;
}
// System.out.println(text); // Compile ERROR: text is not in scope
```

Execution flow:

1. `value instanceof String text` is evaluated. The initial object is `"hello"`, so the result is `true` and the variable `text` is assigned a reference to that string.
2. The `while` body runs only when the condition is `true`, so **`text` is definitely matched** and can be validly used inside the loop body. The program prints `HELLO`.
3. The assignment `value = 10` makes `value` reference an `Integer` due to autoboxing. The variable `text` of the **current iteration** still references `"hello"`; changing the source variable does not change the value already assigned to the pattern variable for that iteration.
4. At the start of the next iteration, `value instanceof String text` returns `false`, and the loop terminates.
5. **After this `while` loop, `text` cannot be used**: the termination condition is that the test **did not match**. The variable is only brought into scope inside the loop body when the condition is true.

In this context, `while (value instanceof String text)` can be understood as: "As long as the current value is still a `String`, run the loop body with a variable `text` of type `String`." Each time the condition evaluates to true, the value from that iteration's match is used in the corresponding body.

Note: without modifying `value`, the example above would loop infinitely because the condition remains true. Always ensure the condition can become `false`, or have an appropriate termination mechanism.

## 3. `&&` in the Condition: Using the Variable on the Right-Hand Side and in the Body

The `&&` operator evaluates from left to right and **does not evaluate the right-hand side when the left-hand side is false** (*short-circuiting*). This allows testing the type and then immediately applying an additional condition to the pattern variable.

```java
Object value = "Java";
while (value instanceof String text && !text.isEmpty()) {
    System.out.println(text.length()); // text is valid
    value = "";
}
```

First iteration: `value` is `"Java"`, the type pattern `String text` matches, and only then is `text.isEmpty()` called. Second iteration: `value` is `""`, which still matches `String`, but `!text.isEmpty()` is `false`, so the loop stops. The output prints only `4`.

Guard conditions can be placed **before** the test to avoid out-of-bounds access:

```java
Object[] values = {"Hi", "Java", 7};
int index = 0;

while (index < values.length
        && values[index] instanceof String text
        && !text.isBlank()) {
    System.out.println(text + ": " + text.length());
    index++;
}
// text cannot be used here.
```

On each check:

- First, `index < values.length` must be true, so accessing `values[index]` is safe.
- Next, the element must match `String text`.
- Finally, `text.isBlank()` is called; at this point `text` has type `String` and is initialized.
- The loop body executes when **the entire expression is true**, so `text` can be used.

The code prints:

```text
Hi: 2
Java: 4
```

It stops at index 2 because the element `7` is an `Integer`, not a `String`. The string `"Java"` has length 4.

**Common mistake with `||`:**

```java
// DOES NOT compile:
while (value instanceof String text || text.isEmpty()) {
    System.out.println("...");
}
```

The right-hand side of `||` is evaluated when the left-hand side is **false**, meaning when `text` is not guaranteed to have matched. Therefore, Java does not allow calling `text.isEmpty()` at that position. With a positive test pattern `value instanceof String text`, use `&&` if the subsequent condition needs to access `text`.

## 4. Negated Condition `!`: Variable Can Be Used **After** `while`

This is the most easily misunderstood case. Consider:

```java
static String ensureString(Object value) {
    while (!(value instanceof String text)) {
        value = "ready";
    }
    return text.toUpperCase(); // VALID in Java 17+
}
```

Control-flow analysis:

- If `value` is initially already a `String`, `value instanceof String text` is true, and the negation `!` makes the `while` condition false. The body does not execute; **`text` has matched** and is used after `while`.
- If `value` is initially not a `String` or is `null`, the initial test is false so `while` executes. At this point **`text` cannot be used inside the body**, because the `String` test itself failed.
- Inside the body, `value` is assigned `"ready"`. When the condition is re-evaluated, the `String text` test is true, and the negation causes `while` to terminate. After the loop, `text` references `"ready"`.

**Why does this compile?** According to JLS 17, a `while` statement can bring a pattern variable into scope **after the `while` statement itself** if:

1. The pattern variable is introduced by the condition expression **when that expression is false** (*introduced when false*).
2. The loop body **does not contain a reachable `break` that exits this loop** (precisely according to the JLS: no *reachable break* statement whose break target contains the loop body).

In `while (!(value instanceof String text))`, the condition expression can only be false when the `instanceof String text` test is true. Because there is no early exit via `break`, every normal path reaching `return text.toUpperCase()` guarantees that `text` has matched.

This **does not apply** to `while (value instanceof String text)`: when that loop terminates because the condition is false, the type test did not succeed.

### 4.1. `break` Can Remove the Variable from Scope After `while`

The following example **only illustrates a compile error** and is not a standalone program:

```java
static void maybeBreak(Object value, boolean stopEarly) {
    while (!(value instanceof String text)) {
        if (stopEarly) {
            break;
        }
        value = "ready";
    }

    // System.out.println(text.length()); // Compile ERROR if uncommented
}
```

When `stopEarly` is `true`, `break` can exit `while` while the `String text` test is still false. Java therefore **does not bring `text` into scope after the loop**. Scope at compile time cannot rely on reasoning such as "in a particular run, `stopEarly` is usually `false`."

Conversely, `continue` jumps to the next evaluation of the condition, so `continue` itself is **not** an exit path that bypasses the check. Even so, you must still ensure the loop can terminate.

### 4.2. Negation Combined with `||` Can Be Valid

Not every `||` with a pattern variable is invalid. The following example is valid in Java 17:

```java
static String requireNonBlankString(Object value) {
    while (!(value instanceof String text) || text.isBlank()) {
        value = "fallback";
    }
    return text;
}
```

If the left-hand side `!(value instanceof String text)` is `true`, the right-hand side is not evaluated. If the left-hand side is `false`, the object **has matched** `String text`, so the right-hand side `text.isBlank()` validly uses `text`. When the entire `while` condition is `false`, it guarantees the value is already a non-blank string. With no `break`, `text` is also usable after the loop.

Trace the logic:

| Input value | Execution flow | Return value |
| --- | --- | --- |
| `"abc"` | Already a non-blank string, does not enter the body | `"abc"` |
| `""` | Matches `String` but is blank; assigns `"fallback"`, checks again | `"fallback"` |
| `7` | Not a `String`; assigns `"fallback"`, checks again | `"fallback"` |
| `null` | Does not match `String`; assigns `"fallback"`, checks again | `"fallback"` |

Pay attention to **which outcome causes the right-hand side to be evaluated**: `instanceof String text && ...` uses `text` on the right-hand side when the positive test is true; whereas `!(instanceof String text) || ...` also uses `text` when the original test is true, because in that case the negated left-hand side is false.

## 5. Complete Runnable Java 17+ Program

Create the file `WhilePatternScopeDemo.java`:

```java
public class WhilePatternScopeDemo {
    static void printLeadingStrings(Object[] values) {
        int index = 0;

        while (index < values.length
                && values[index] instanceof String text
                && !text.isBlank()) {
            System.out.println("String " + index + ": "
                    + text + " (" + text.length() + ")");
            index++;
        }
        System.out.println("Stopped at index " + index);
        // System.out.println(text); // Not in scope after this while loop.
    }

    static String ensureString(Object value) {
        while (!(value instanceof String text)) {
            System.out.println("Replacing non-string");
            value = "ready";
        }
        return text.toUpperCase(); // In scope after negated while loop.
    }

    static void showSnapshot() {
        Object value = "first";
        while (value instanceof String text) {
            value = 100;
            System.out.println("Old match: " + text);
        }
    }

    public static void main(String[] args) {
        printLeadingStrings(new Object[] {"Hi", "Java", 123, "later"});
        System.out.println("Converted: " + ensureString(42));
        System.out.println("Already: " + ensureString("ok"));
        showSnapshot();
    }
}
```

Run with JDK 17 or later:

```bash
javac WhilePatternScopeDemo.java
java WhilePatternScopeDemo
```

Exact output:

```text
String 0: Hi (2)
String 1: Java (4)
Stopped at index 2
Replacing non-string
Converted: READY
Already: OK
Old match: first
```

**Explanation:**

1. `printLeadingStrings` processes only the leading prefix of non-blank strings. The third element is `123` (`Integer`), so the condition expression becomes false and it stops at `index = 2`.
2. `ensureString(42)` enters the loop body once, prints `Replacing non-string`, and changes the value to `"ready"`. On the next check, `String text` matches, the loop stops, and it returns `"READY"`.
3. `ensureString("ok")` does not run the loop body; `text` is still matched during the initial condition check and the result is `"OK"`.
4. `showSnapshot` matches `"first"`, then assigns `value = 100`. The variable `text` in the current iteration still points to `"first"` so it prints `Old match: first`; the next check fails and the loop ends.

This program demonstrates **both directions of flow scoping**: a positive condition allows using the variable inside the loop body, while a negated condition whose only normal exit path is through the failed check allows using the variable after the loop.

## 6. Comparison of `while` Constructs

| Condition / loop body | Use `s` in body? | Use `s` after loop? | Explanation |
| --- | --- | --- | --- |
| `while (x instanceof String s) { ... }` | **Yes** | **No** | Body runs when matched; exits normally when not matched |
| `while (x instanceof String s && !s.isBlank()) { ... }` | **Yes** | **No** | `s` is usable on the RHS of `&&` and in the body when the condition is true |
| `while (!(x instanceof String s)) { x = "ok"; }` | **No** | **Yes** | Body runs when not yet matched; exits normally when matched |
| `while (!(x instanceof String s)) { if (flag) break; x = "ok"; }` | **No** | **No** | `break` can exit before the pattern matches |
| `while (!(x instanceof String s) || s.isBlank()) { x = "ok"; }` | **No** | **Yes** | RHS of `||` only runs when `s` has matched; no `break` |

In the table rows, `x` and `flag` are hypothetical variables already declared with appropriate types, and `{ ... }` represents the loop body. The table only compares **whether the pattern variable `s` can be used**; it does not guarantee that every loop terminates for all input values.

### Variable Names Do Not Automatically Exist Everywhere

If a pattern variable is not in scope after `while`, a local variable with the same name can be declared at an appropriate location according to Java's naming rules. Conversely, when a negated `while` brings `s` into scope after the loop, another local variable also named `s` cannot be declared in that same scope:

```java
static void example(Object value) {
    while (!(value instanceof String text)) {
        value = "ok";
    }
    System.out.println(text); // Valid.
    // String text = "another"; // ERROR: name text is already in scope.
}
```

When reading code, identify **the point where the program is guaranteed to match the pattern**, rather than just scanning for `{` and `}` braces.

## 7. Common Mistakes and Fixes

1. **Using the pattern variable inside the body of a negated `while`.** In `while (!(obj instanceof String s))`, the body runs when the object is **not** a `String`; `s` cannot be used there. Only use `s` after the loop if the JLS allows it.
2. **Using the variable after a positive `while`.** `while (obj instanceof String s) { ... }` exits normally when the test is false; at that point `s` is not in scope.
3. **Adding `break` to a negated `while` and still using `s` afterward.** The early exit path can bypass matching; the compiler rejects it. If early termination is needed, handle the result separately instead of assuming `s` is available.
4. **Confusing `&&` and `||`.** The right-hand side of `&&` runs when the left-hand side is true; the right-hand side of `||` runs when the left-hand side is false. Whether using `s` on the right-hand side is valid depends on the condition form and negation.
5. **Forgetting a progress condition.** A type pattern does not change `obj` on its own; if `obj` remains a `String` in a positive condition, `while` can run forever. If `obj` never becomes a `String` in a negated condition, the loop can also fail to terminate.
6. **Forgetting the `null` case.** In Java 17, `null instanceof String s` is `false`. A positive loop skips the body; a negated loop enters the body. Calling methods on `s` is only safe when `s` has matched.
7. **Confusing changing the source variable with changing the pattern variable in the current iteration.** Once the condition matches, the pattern variable holds the reference assigned for that iteration; reassigning `obj` does not change the reference already held in `s`.
8. **Using the syntax with an unsupported JDK.** Pattern matching for `instanceof` has been a standard feature since Java 16; use JDK 17+ to compile the examples in this lesson.

## 8. Practice Exercises

1. Predict the output and explain the scope of `s`:

   ```java
   Object x = "abc";
   while (x instanceof String s && s.length() > 1) {
       System.out.println(s);
       x = 0;
   }
   ```

2. Write `static String normalize(Object x)` using `while (!(x instanceof String text))` to turn non-string values into `"unknown"`, and then return `text.trim()`. Test with `null`, `123`, and `" hi "`.
3. Add an `if (stopEarly) break;` to the `while` body in exercise 2. Explain why `text.trim()` is no longer valid outside the loop afterward.
4. Write a loop over an `Object[]` containing strings and numbers that stops at the first element that is not a `String`, while printing the length of each string. Ensure there is no out-of-bounds array access.
5. Explain why `while (!(x instanceof String s) || s.isBlank()) { x = "ok"; }` is valid, whereas `while (x instanceof String s || s.isBlank()) { ... }` is invalid.

**Self-check:** You have understood this topic when you can answer both questions: "When is the `while` body guaranteed to have the pattern variable?" and "When is every execution path exiting `while` guaranteed to have matched the pattern?" The second question explains the special role of negated conditions and `break`.

## References

- [Java Language Specification SE 17, §6.3.2.3 — Scope in `while` statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.2.3).
- [Java Language Specification SE 17, §6.3.1 — Pattern variables in expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1).
- [Oracle Java 17 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html).
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394).
