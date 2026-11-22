# Variable Scope with the `||` Operator in Java Pattern Matching

## 1. The problem: why can `instanceof` with a pattern variable still cause errors with `||`?

Since Java 16, `instanceof` can take a **type pattern**, for example `value instanceof String text`. When the check succeeds, it creates the variable `text` of type `String` for use at locations where the compiler knows for certain that the match succeeded.

However, this variable **does not have the same scope as an ordinary local variable declared before the `if` statement**. Its scope depends on the program's execution paths (*flow scoping*). The short-circuit OR operator `||` is an easy case to get wrong because the overall condition can be true even when the pattern does not match.

Consider this snippet that **does not compile**:

```java
// INCORRECT SNIPPET — do not use as a runnable example:
// Object value = "Java";
// boolean fallback = true;
// if (value instanceof String text || fallback) {
//     System.out.println(text.length()); // Error: text might not have matched.
// }
```

If `value` is an integer and `fallback` is `true`, the entire `if` condition is still true, yet `value instanceof String text` has failed. Java cannot allow `text` to be used because no `String` value has been bound.

**Core question:** At the point where a pattern variable is used, do **all paths reaching that point** guarantee that the pattern has matched? Only when the answer is "yes" is the pattern variable valid at that location.

This lesson focuses on how `||` affects the scope of pattern variables from `instanceof`, especially how to combine **negation `!`**, **early-exit guard conditions**, and **accessing the variable after `if`**. The examples run on **Java 17 and later**, with no preview features required.

## 2. Two foundational rules: short-circuit OR and flow scoping

### 2.1. `||` evaluates from left to right

Given the expression:

```java
left || right
```

Java does the following:

1. Evaluate `left`.
2. If `left == true`, **do not evaluate `right`**; the entire expression is `true`.
3. If `left == false`, evaluate `right` to determine the result.

Truth table:

| `left` | Is `right` evaluated? | Result of `left || right` |
| --- | --- | --- |
| `true` | No | `true` |
| `false` | Yes, result is `true` | `true` |
| `false` | Yes, result is `false` | `false` |

Important consequence: if **the entire expression `left || right` is `false`**, we are certain that **both sides evaluated to `false`**. On the other hand, if the entire expression is `true`, we cannot conclude which specific side was true.

### 2.2. A pattern variable is only usable when "definitely matched"

Basic example:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length()); // Valid: text has matched.
}
```

`value instanceof String text` returns `true` when the runtime value is a `String`; at that point `text` refers to the exact `String` object that was checked. If the value is not a `String` or is `null`, the result is `false` and `text` cannot be used on the non-matching path.

For complex expressions, Java considers **which variables are introduced when the expression is true or false** (*introduced when true/false*) to determine scope. Negation `!` reverses that direction: if `!(value instanceof String text)` is `false`, we know the inner `instanceof` is `true` and `text` has matched.

This rule explains why, with the same `||` operator, some snippets are invalid and others are valid.

## 3. The invalid case: a positive pattern on the left-hand side of `||`

Look at this example:

```java
// INVALID:
// if (value instanceof String text || text.isBlank()) {
//     System.out.println("OK");
// }
```

The right-hand side `text.isBlank()` is only evaluated when the left-hand side `value instanceof String text` is **`false`**. That is precisely when `text` **has not matched**, so the compiler rejects accessing `text` on the right-hand side.

This is the opposite of `&&`:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip()); // Valid.
}
```

With `&&`, the right-hand side only runs when `instanceof` is `true`, so `text` has matched and `isBlank()` can be called.

### You also cannot use the variable in the `if` body if OR has an alternative path

Even when the right-hand side **does not mention** the pattern variable at all, `||` still prevents the variable from being guaranteed inside the `if` branch:

```java
// INVALID:
// if (value instanceof String text || useDefault) {
//     System.out.println(text.length());
// }
```

There are two ways for the `if` branch to execute: the value is a `String`, **or** `useDefault` is `true`. In the second case, the pattern may have failed; Java does not allow accessing `text`.

It is important to distinguish:

- `||` is an OR on **boolean values**.
- Having **a pattern variable available to use** is a stronger requirement: it must be proven that the pattern matched on every path reaching the point of use.

A condition evaluating to `true` is not enough to prove that a specific type pattern has matched.

## 4. The valid case: negating the pattern before `||`

Now flip the condition toward **detecting invalid data**:

```java
if (!(value instanceof String text) || text.isBlank()) {
    System.out.println("Not a valid string");
}
```

**This snippet is valid in Java 17.** Why:

1. If `value` is not a `String` (including `null`), `value instanceof String text` is `false`, so `!(...)` is `true`. Java **skips** the right-hand side `text.isBlank()`; no unmatched variable is accessed.
2. If `value` is a `String`, `instanceof` matches and creates `text`; the negation `!(...)` is `false`. Java must evaluate the right-hand side, and at this point `text` **has definitely matched**, so `text.isBlank()` is valid.

You can read the condition in plain English:

> "If the input **is not a string**, or **is a string but contains only whitespace**, handle the error."

The `!` operator is the key. It turns the left-hand condition into a **negated** check, so that **the left-hand side being false** means **the pattern has matched**.

### Trace table for several inputs

For the expression `!(value instanceof String text) || text.isBlank()`:

| `value` | `instanceof String` | `!(...)` | Does `text.isBlank()` run? | Result of entire expression |
| --- | --- | --- | --- | --- |
| `"Java"` | `true` | `false` | Yes, `false` | `false` |
| `"   "` | `true` | `false` | Yes, `true` | `true` |
| `42` | `false` | `true` | No | `true` |
| `null` | `false` | `true` | No | `true` |

This is also a **way to avoid `null` access errors**: when `value == null`, the right-hand side does not run. In Java, `null instanceof String text` itself returns `false` and does not throw a `NullPointerException`.

### Comparing two semantically equivalent ways of writing it

**Approach 1 — keep the valid case:**

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

**Approach 2 — reject the invalid case:**

```java
if (!(value instanceof String text) || text.isBlank()) {
    System.out.println("Invalid value");
} else {
    System.out.println(text.strip());
}
```

In approach 2, the `else` branch only runs if the entire OR condition is **`false`**. When that happens:
- `!(value instanceof String text)` is `false`, so the pattern has matched.
- `text.isBlank()` is `false`, so the string is not blank.

Therefore, `text` can be used in the `else` branch. Both snippets express the same valid-data check; the difference lies in how the branches are structured.

## 5. Guard clause: using a pattern variable after `||`

A very useful application of `||` is an **early-exit guard condition** (*guard clause*). You handle the error first, `return` or `throw`, and then continue along the path that is guaranteed to be valid:

```java
static String normalize(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "INVALID";
    }

    return text.strip(); // VALID: text has definitely matched.
}
```

Why is `text` still usable **after** the `if` statement?

- If the OR condition is `true`, the method has already executed `return`, so there is no path to `text.strip()`.
- To reach `text.strip()`, the OR condition **must be `false`**.
- Making the OR condition `false` forces `!(value instanceof String text)` to be `false`; that means the pattern matched and `text` has type `String`.

This is a classic example of *flow scoping*: scope does not depend only on the curly braces of `if`, but also on which branches **can continue execution**.

### What if the `if` branch does not exit early?

The following snippet is **invalid**:

```java
// DOES NOT COMPILE:
// if (!(value instanceof String text) || text.isBlank()) {
//     System.out.println("Invalid input");
// }
// System.out.println(text.strip()); // Execution can reach here after the error branch.
```

Because the error branch only prints a message and continues, the program still has a path to `text.strip()` when `value` does not match `String`. `text` cannot be considered matched.

**Fix with `return` or `throw`:**

```java
static String requireText(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Expected non-blank String");
    }
    return text.strip();
}
```

Another solution is to place the logic that uses `text` inside the guaranteed `else` branch, as shown in the previous section.

## 6. When two patterns must be checked: negated OR condition

In practice, you may need to ensure **two inputs simultaneously** have the right types before processing. With a guard clause, you write `||` to reject if **either one** has the wrong type:

```java
static String describePair(Object first, Object second) {
    if (!(first instanceof String name)
            || !(second instanceof Integer count)) {
        return "INVALID_PAIR";
    }

    return name.strip() + " x " + count;
}
```

The snippet above is **valid** in Java 17:

1. If `first` is not a `String`, the left-hand side is `true`, the right-hand side is not evaluated, and the method returns `"INVALID_PAIR"`.
2. If `first` is a `String`, `name` has matched. The right-hand side checks `second`.
3. If `second` is not an `Integer`, the method returns the error.
4. Only when **both** objects have the right types is the entire OR condition `false`, so the error branch does not run. After the `if`, both `name` and `count` have matched.

Important note: inside the error-handling `if` body, you cannot arbitrarily use `name` or `count`. That branch can be entered because **any** of the checks failed.

### Comparing with a positive `&&` condition

The two styles below have the same validation goal:

```java
if (first instanceof String name
        && second instanceof Integer count) {
    System.out.println(name + ": " + count);
}
```

And:

```java
if (!(first instanceof String name)
        || !(second instanceof Integer count)) {
    return;
}
System.out.println(name + ": " + count);
```

The second snippet must be placed **inside the body of a `void`-returning method**, because it uses `return;`. It is an illustrative snippet, not a standalone program.

You can understand the two conditions using De Morgan's laws:

```text
A && B             : both A and B are true
!(A && B)          : at least one condition is false
!A || !B           : equivalent to !(A && B)
```

With pattern variables, beyond logical equivalence, you must also consider **which branch guarantees that the pattern has matched** and whether the statement **exits early**.

## 7. Complete Java 17 example: OR, negation, and variable scope

Create the file **`OrFlowScopingDemo.java`**:

```java
public class OrFlowScopingDemo {

    static String normalize(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "INVALID";
        }
        return "OK:" + text.strip();
    }

    static String pair(Object first, Object second) {
        if (!(first instanceof String name)
                || !(second instanceof Integer count)) {
            return "INVALID_PAIR";
        }
        return name.strip() + " x " + count;
    }

    static boolean invalidText(Object value) {
        return !(value instanceof String text) || text.isBlank();
    }

    static String classify(Object value) {
        if (value instanceof String text) {
            return "TEXT:" + text;
        }
        if (value instanceof Integer number) {
            return "INT:" + number;
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        System.out.println(normalize("  Java  "));
        System.out.println(normalize("   "));
        System.out.println(normalize(5));
        System.out.println(normalize(null));

        System.out.println(pair("  An  ", 3));
        System.out.println(pair("  An  ", "3"));

        System.out.println(invalidText("x"));
        System.out.println(invalidText(""));
        System.out.println(invalidText(null));

        System.out.println(classify("ok"));
        System.out.println(classify(12));
        System.out.println(classify(null));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 OrFlowScopingDemo.java
java OrFlowScopingDemo
```

Output:

```text
OK:Java
INVALID
INVALID
INVALID
An x 3
INVALID_PAIR
false
true
true
TEXT:ok
INT:12
OTHER
```

**Explanation of each method:**

- `normalize`: writes the error condition as `!(... instanceof String text) || text.isBlank()`. When there is no error, `text` is usable after the `if` because the error branch executed `return`.
- `pair`: combines two negated checks with `||`. To get past the guard clause, both `name` and `count` must match.
- `invalidText`: uses the OR expression directly as a boolean result. The variable `text` is only needed on the right-hand side, where it is always guaranteed to have matched.
- `classify`: two types that need different handling are separated into two separate `if` statements so each pattern variable has a clear scope. Do not try to combine positive patterns with `||` and then use a variable in the same branch.

In particular, `normalize(null)` safely returns `"INVALID"`: `null instanceof String text` is `false`, negating it yields `true`, so Java skips `text.isBlank()`.

## 8. Common mistakes related to `||`

### Mistake 1: treating "OR condition is true" as "pattern has matched"

```java
// INVALID:
// if (value instanceof String text || allowUnknown) {
//     System.out.println(text.toUpperCase());
// }
```

When `allowUnknown` is true, execution can enter the `if` even when `value` is not a string. **Fix:** separate the branch that uses `text` from the branch that uses the fallback value:

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
} else if (allowUnknown) {
    System.out.println("UNKNOWN");
}
```

The fix assumes `value` and `allowUnknown` are already suitably declared in the scope enclosing the `if`.

### Mistake 2: forgetting negation `!` when rejecting wrong-type data

```java
// DOES NOT COMPILE:
// if (value instanceof String text || text.isBlank()) {
//     return "INVALID";
// }
```

**Fix:**

```java
if (!(value instanceof String text) || text.isBlank()) {
    return "INVALID";
}
```

The fix must reside in a method with return type `String`. Negation makes reaching the right-hand side synonymous with the pattern having matched.

### Mistake 3: using the variable after `if` when the error branch falls through

```java
// INVALID:
// if (!(value instanceof String text) || text.isBlank()) {
//     System.out.println("INVALID");
// }
// System.out.println(text.length());
```

**Fix:** use `return`, `throw`, or place the statement using `text` in the corresponding `else` branch.

### Mistake 4: thinking `||` can never be used with a pattern variable

This belief is **false**: you can use a pattern variable on the right-hand side if the left-hand side being **false** proves the pattern matched. Valid example:

```java
if (!(value instanceof String text) || text.length() == 0) {
    System.out.println("No valid string");
}
```

`text.length()` only runs after the value has matched `String`. The pattern variable's name does not determine validity; **the true/false direction of the match and the evaluation order** do.

### Mistake 5: forgetting short-circuiting when calling methods

`||` does not evaluate the right-hand side when the left-hand side is true. This helps avoid calling methods on an unmatched variable in a negated pattern. However, if the right-hand side contains a function with side effects (writing state, sending a request, incrementing a counter), that function may be **skipped**. Only place side effects in a condition when you genuinely want that behavior.

## 9. Quick checklist when reading a complex condition

Ask yourself in order:

1. Is the pattern `value instanceof T variable`, or has it been negated to `!(value instanceof T variable)`?
2. If `||` needs to evaluate the right-hand side, **the left-hand side is definitely `false`**. Does that guarantee the pattern variable matched?
3. If you are inside the `if` branch of the entire OR, is there any path that makes the OR true **without the pattern matching**?
4. If you use the variable after the `if`, do the error branches exit via `return` or `throw`?
5. If there are multiple type patterns, at the point where each variable is used, have **all corresponding conditions matched**?

Comparison table:

| Way of writing | Where is the pattern variable used? | Conclusion |
| --- | --- | --- |
| `x instanceof String s && !s.isBlank()` | Right-hand side and `if` branch when expression is true | Valid |
| `x instanceof String s || s.isBlank()` | Right-hand side tries to use `s` | Compile error |
| `x instanceof String s || fallback` | `s` is not guaranteed in the `if` branch | Do not use `s` there |
| `!(x instanceof String s) || s.isBlank()` | Right-hand side | Valid |
| `if (!(x instanceof String s) || s.isBlank()) return; ... s ...` | After `if` in a `void` method when the error condition exited | Valid |
| `if (!(x instanceof String s) || s.isBlank()) { ... } else { ... s ... }` | `else` branch | Valid |
| `if (!(x instanceof String s) || s.isBlank()) { log(); } ... s ...` | After `if` while the error branch falls through | Compile error |

The `...` placeholders in the table describe control-flow structure, not Java code to copy verbatim.

## 10. Exercises and answers

### Exercise 1: which snippet compiles?

Assume `Object value` has already been declared:

**A.**

```java
if (value instanceof String s || s.length() > 2) {
    System.out.println("A");
}
```

**B.**

```java
if (!(value instanceof String s) || s.length() < 3) {
    System.out.println("B");
}
```

**C.**

```java
if (value instanceof String s && s.length() > 2) {
    System.out.println(s);
}
```

**Answer:** A does not compile because the right-hand side is evaluated when the type pattern `s` fails. B compiles because the right-hand side only runs if the inner `instanceof` has matched. C compiles because the right-hand side of `&&` only runs when the type pattern has matched.

### Exercise 2: predict the method output

```java
static String check(Object value) {
    if (!(value instanceof String s) || s.isBlank()) {
        return "BAD";
    }
    return "GOOD:" + s.strip();
}
```

- `check(" Hi ")` → `"GOOD:Hi"`
- `check("   ")` → `"BAD"`
- `check(10)` → `"BAD"`
- `check(null)` → `"BAD"`

Being able to explain both **when the right-hand side is executed** and **why `s` is usable after `if`** demonstrates a complete understanding of the topic.

### Exercise 3: fix the code to check types while avoiding errors

The original snippet does not compile:

```java
// DOES NOT COMPILE:
// if (obj instanceof String name || obj instanceof Integer number) {
//     System.out.println(name + " / " + number);
// }
```

At any given moment, `obj` is not guaranteed to be both a `String` and an `Integer` simultaneously. Instead of trying to use both `name` and `number` in one branch, handle each possibility:

```java
if (obj instanceof String name) {
    System.out.println("Name: " + name);
} else if (obj instanceof Integer number) {
    System.out.println("Number: " + number);
} else {
    System.out.println("Other");
}
```

The fix only requires `Object obj` to be available in scope. Each pattern variable is used in the branch where its corresponding check matched.

## 11. Practical takeaway

The `||` operator **does not by itself disable** pattern matching. It simply forces you to reason accurately about control flow:

- With `value instanceof String s || ...`, the right-hand side is evaluated when the `String` match **fails**, so `s` cannot be used on the right-hand side; the true branch of the whole OR also does not guarantee `s` matched.
- With `!(value instanceof String s) || s.isBlank()`, the right-hand side is only evaluated when the `String` match **succeeds**, so `s` is valid there.
- If a negated OR condition is used for early exit with `return` or `throw`, the subsequent code can use `s` because all remaining paths have proven the pattern matched.

**Rule of thumb:** With `||`, to use a pattern variable on the right-hand side, ask: "When the left-hand side is **false**, is this variable guaranteed to be bound?" To use the variable after an `if` statement, check every path that has not exited the method. That is the core of **flow scoping** in this scenario.

## References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java SE 17 Language Specification, §6.3 — Scope of Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3)
- [Java SE 17 Language Specification, §15.23–15.24 — Conditional-AND and Conditional-OR Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.24)
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
