# Reading Flow Scope Through Control Flow in Java 21

In Java, the **flow scope** of a *pattern variable* is determined by the **execution paths that the compiler can prove**, rather than solely by the position of curly braces. To read the scope accurately, follow the `true`/`false` branches of expressions, exit points (`return`, `throw`, `continue`), and `switch` arms, then determine at each point whether a pattern has **definitely matched**.

For example, `value instanceof String text` both checks the type and introduces the variable `text`. However, the appearance of `text` in a condition does not mean it can be used in every subsequent statement. It is only in scope where every path reaching that point confirms the `instanceof` check succeeded. This is the practical meaning of *flow scoping* and *definite matching*.

This article uses Java 21. Type patterns for `instanceof`, pattern matching for `switch`, and record patterns in the examples are all stable features, with no preview flags required.

## 1. Read from paths, not line positions

Consider the illustrative method:

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length()); // valid
    } else {
        // System.out.println(text); // compile error
    }

    // System.out.println(text); // compile error
}
```

Program control flow:

```text
                 value instanceof String text
                         /          \
                      true          false
                       |              |
                  text matched     no text
                       |              |
                   if branch     else branch
                       \              /
                         flow merges
                     text not guaranteed
```

In the `if` branch, every path originates from the `true` result, so `text` can be used. The `else` branch originates from `false`, so there is no valid `text` variable. After the `if/else`, execution can arrive from either branch; it cannot be guaranteed that the pattern matched.

This same reasoning applies when conditions contain multiple operations and when a branch exits early: we need to examine **which paths can still reach the point where the variable is used**, rather than just seeing that the variable was declared nearby.

## 2. Rules for propagating `true`/`false` state

Let `P` be the expression `value instanceof String text`. If `P` is true, `text` has definitely matched; if `P` is false, `text` is not bound by that pattern. For complex conditional expressions, you can use the following inference table:

| Construct | What is known when continuing | Consequence for the pattern variable |
| --- | --- | --- |
| `P` evaluates to `true` | `value` is a `String` | `text` can be used along that path |
| `P` evaluates to `false` | Pattern did not match | `text` cannot be used along that path |
| `!P` evaluates to `false` | `P` is actually true | `text` can be used |
| `P && C`: evaluating `C` | `P` is already true | `C` is allowed to use `text` |
| `P || C`: evaluating `C` | `P` is already false | `C` cannot use `text` based on `P` |
| `!P || C`: evaluating `C` | `!P` is false, so `P` is true | `C` is allowed to use `text` |
| `if (!P) return;` then continuing | The `!P` branch cannot continue | `text` can be used after the `if` |

The table only describes a single pattern `P` and its directly related paths. With multiple patterns, each variable has its own match state. The compiler relies on Java's control flow rules, not arbitrary inferences from the author's business logic.

## 3. `&&`: reaching the right-hand side means the left-hand side is true

`&&` uses *short-circuit evaluation*: Java **only** evaluates the right-hand side when the left-hand side has returned `true`.

```java
static boolean validName(Object value) {
    return value instanceof String name
            && !name.isBlank()
            && name.length() <= 40;
}
```

Tracing `value instanceof String name`:

1. If false, the entire `&&` returns `false`; the remaining two operands are not evaluated.
2. If true, `name` is a `String` and `!name.isBlank()` is evaluated.
3. If the name is not blank, the length check runs. Every use of `name` in the subsequent operands is safe.

However, **when the entire `&&` condition is false, you cannot infer backward that the pattern failed**: the pattern may have matched, while `isBlank()` or the length check failed.

```java
static String check(Object value) {
    if (value instanceof String name && name.length() > 3) {
        return "long:" + name; // valid
    } else {
        // name is not definitely matched: value could be "abc".
        return "not long";
    }
}
```

A common mistake is seeing `instanceof` in a condition and then using `name` in the `else` branch. To determine scope, ask **which failure outcomes** can reach the `else` branch.

## 4. `||`: reaching the right-hand side means the left-hand side is false

With `||`, Java only evaluates the right-hand side when the left-hand side is `false`. Therefore, the following code is invalid:

```java
// DOES NOT COMPILE; value is a parameter of type Object.
static boolean invalid(Object value) {
    return value instanceof String text || text.isEmpty();
}
```

When `text.isEmpty()` needs to be evaluated, `instanceof` has returned `false`; at that point, `text` is not guaranteed to have matched.

On the other hand, negating the left-hand condition flips the inference:

```java
static boolean missingOrBlank(Object value) {
    return !(value instanceof String text) || text.isBlank();
}
```

Control flow:

```text
                    !(value instanceof String text)
                         /                 \
                       true               false
                        |                   |
                   returns true      instanceof is true
                  RHS not evaluated         |
                                            v
                                       text.isBlank()
```

To reach `text.isBlank()`, the negation must be `false`, which proves `value instanceof String text` is `true`. This is a **valid** case of using a pattern variable on the right-hand side of `||`.

Do not memorize a mechanical trick like "`&&` allows it while `||` forbids it." The real rule is **along which path the right-hand side runs and what that path proves**.

## 5. The overall result of `&&` or `||` can lose information

Consider the condition:

```java
static boolean enabled(Object value, boolean fallback) {
    if ((value instanceof String text && !text.isBlank()) || fallback) {
        // System.out.println(text); // DOES NOT COMPILE
        return true;
    }
    return false;
}
```

There are **two ways** to enter the `if` body:

- `value` is a non-blank string: the `text` pattern matched.
- `fallback` is `true` even though `value` is not a string: the pattern did not match.

Consequently, at the merge point of the two paths, `text` cannot be used. Having one operand *possibly* match is not enough; **every valid path** reaching the usage site must guarantee a match.

If you need to use the string, place the operation in a branch directly guarded by `instanceof`:

```java
static void printOrFallback(Object value, boolean fallback) {
    if (value instanceof String text && !text.isBlank()) {
        System.out.println(text.trim());
    } else if (fallback) {
        System.out.println("fallback");
    }
}
```

Organizing branches this way is usually clearer than deeply nested `&&`/`||` expressions.

## 6. `!`, `return`, and `throw`: eliminating the failing path

A negated condition **swaps** the true/false outcomes of a pattern. If the non-matching path terminates, the rest of the method can only execute when the pattern matched:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "not-string";
    }

    return text.strip().toLowerCase(); // valid
}
```

Read from the end backward: to reach `text.strip()`, execution must pass the `if` without returning. That only happens if `!(value instanceof String text)` is false, meaning `instanceof` is true.

The same idea applies with `throw`:

```java
static int lengthOrThrow(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("String required");
    }
    return text.length();
}
```

The two methods above are illustrative snippets to be placed inside a class. For `null`, `instanceof String` is also `false`; the `return` or `throw` branch will be taken.

**Not every statement in a failing branch eliminates the path.** The following example does not compile:

```java
// DOES NOT COMPILE:
static int missingExit(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("wrong type"); // execution can still fall through
    }
    return text.length(); // text is not guaranteed to be matched
}
```

`System.out.println` does not stop control flow from continuing; to use `text` after the `if`, there must be a guaranteed exit, such as `return` or `throw`, in the non-matching branch.

## 7. Combining negation and short-circuiting with early return

A practical pattern is rejecting inputs of the wrong type or invalid values:

```java
static String readNonBlank(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "skip";
    }

    return "read:" + text.strip(); // valid
}
```

For the final statement to run, the `if` condition must be `false`. For `A || B` to be false, **both `A` and `B` must be false**:

- `!(value instanceof String text)` is false → the `String text` pattern matched.
- `text.isBlank()` is false → the string is not empty or whitespace-only.

In this way, code after the guard clause can safely use `text` and rely on the business validation already performed.

If the `if` branch only logs and continues, this conclusion no longer holds. During code review, distinguish clearly between a **boolean result** and **whether a statement can complete normally**.

## 8. Reading nested `if` statements as separate paths

```java
static String classify(Object value) {
    if (value instanceof CharSequence sequence) {
        if (sequence instanceof String text) {
            return "string:" + text.length();
        }
        return "other character sequence:" + sequence.length();
    }
    return "not character sequence";
}
```

In the outer `if` branch, `sequence` is definitely a `CharSequence`. In the inner `if` branch, `text` is definitely a `String`. However, when the inner `if` does not match, only `sequence` remains in scope; `text` cannot be used.

Imagine each additional pattern match as adding **local evidence** along the path. When branching onto a non-matching path, you cannot carry over evidence from the other branch. Conversely, evidence established in an enclosing branch remains available throughout its scope.

## 9. Loops: conditions and loop exit points

With a `while` loop, the body only executes when the condition is true:

```java
static void printWhile(Object value) {
    while (value instanceof String text && !text.isEmpty()) {
        System.out.println(text);
        break;
    }

    // System.out.println(text); // invalid here
}
```

Inside the `while` body, `text` is matched. After the loop, there is at least one path that never entered the body because `value` had the wrong type, so the variable cannot be relied upon. In particular, `break` can terminate a loop **without the condition becoming false**; therefore, you must trace loop exit edges rather than guessing state from the condition alone.

When looping over multiple elements, a `continue` guard can keep the code below cleaner:

```java
static void printStrings(java.util.List<?> values) {
    for (Object item : values) {
        if (!(item instanceof String text)) {
            continue;
        }
        System.out.println(text.strip());
    }
}
```

After `continue`, flow moves to the next iteration; within the **current iteration**, the statements below only execute when `item` matches `String`. The variable `text` does not stay in scope outside the `for` loop and is not carried across iterations.

For `do ... while`, the body executes before the trailing condition is evaluated, so a pattern in the trailing condition cannot serve as evidence for statements earlier in the body.

## 10. The conditional operator `?:`

In the expression `condition ? a : b`, branch `a` only runs if `condition` is true, while `b` runs if the condition is false.

```java
static String label(Object value) {
    return value instanceof String text ? text.strip() : "other";
}
```

In the `text.strip()` branch, the `instanceof` condition is definitely true, so `text` is in scope. In the `"other"` branch, the pattern may not have matched; `text` cannot be used based on the condition's pattern.

The same approach applies to a negated condition: `!(value instanceof String text) ? "other" : text.strip()`. When reaching the third operand, the negation is `false`, so the inner match is `true`.

## 11. `switch` branches and `when` guards in Java 21

Pattern matching for `switch` introduces pattern variables into **the `case` arm where the pattern matches**. With `when`, that variable can also be used to evaluate the guard of that same arm.

```java
record Point(int x, int y) {}

static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text when !text.isBlank() -> "text:" + text.strip();
        case String ignored -> "blank";
        case Point(var x, var y) when x > 0 && y > 0 -> "quadrant I";
        case Point(var x, var y) -> "point:" + x + "," + y;
        default -> "other";
    };
}
```

This is an illustrative snippet that requires placing the `record` and method inside a valid Java class/package context; it is not a standalone program.

Reading each `case` individually:

1. `case String text when ...`: before evaluating the guard, Java has already determined that the selector matches `String text`; `text` is usable in the guard and after `->`.
2. If this guard fails, `switch` can check `case String ignored`. The variable `ignored` belongs to the later arm and does not inherit the scope of `text`.
3. With `case Point(var x, var y) when x > 0 && y > 0`, both `x` and `y` have been extracted from the record before the guard is evaluated. The variables in the subsequent `case Point` are also separate declarations for that arm.
4. In `default`, there is no evidence that the selector matched `String` or `Point`, so variables from those arms cannot be used.

`switch` also has other rules such as **dominance** (a broader type arm can shadow a narrower type arm) and **exhaustiveness** (a `switch` expression must cover all possible values). These relate to whether a path can be selected, but they **do not replace** scoping rules: a pattern variable is in scope where its corresponding pattern has definitely matched. When the selector can be `null`, handle it explicitly with `case null` if desired; `default` does not match `null` by default.

## 12. Quick breakdown of a common mistake

Consider the intent: "if the input is a valid string or the user has a privileged override, proceed":

```java
// DOES NOT COMPILE:
static String incorrect(Object input, boolean privileged) {
    if (input instanceof String text && !text.isBlank() || privileged) {
        return text.strip(); // privileged could be true when input is not a String
    }
    return "rejected";
}
```

Java gives `&&` higher precedence than `||`, so the condition means `(P && nonBlank) || privileged`. When `privileged` is true, `P` can be false and execution still enters the `if` branch. There is no basis for using `text` there.

You can restructure it so "permission to proceed" is not mixed with "type checked":

```java
static String correct(Object input, boolean privileged) {
    if (input instanceof String text && !text.isBlank()) {
        return text.strip();
    }
    if (privileged) {
        return "privileged";
    }
    return "rejected";
}
```

Splitting the branches also clarifies the business requirement: the override case returns its own status instead of attempting to call a `String` method on an unchecked input.

## 13. Complete program: tracing multiple paths

Create the file **`FlowScopeControlFlowDemo.java`**:

```java
public class FlowScopeControlFlowDemo {
    record Point(int x, int y) {}

    static String normalize(Object value, boolean allowBlank) {
        if (!(value instanceof String text)) {
            return "not-string";
        }
        if (text.isBlank() && !allowBlank) {
            return "blank-rejected";
        }
        return "accepted:" + text.strip();
    }

    static String readNonBlank(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "skip";
        }
        return "read:" + text.strip();
    }

    static String describe(Object value) {
        return switch (value) {
            case null -> "missing";
            case String text when !text.isBlank() -> "text:" + text.strip();
            case String ignored -> "blank";
            case Point(var x, var y) when x > 0 && y > 0 -> "quadrant I";
            case Point(var x, var y) -> "point:" + x + "," + y;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(normalize("  Java  ", false));
        System.out.println(normalize(17, false));
        System.out.println(normalize("  ", false));
        System.out.println(normalize("", true));

        System.out.println(readNonBlank("  scope  "));
        System.out.println(readNonBlank(" "));
        System.out.println(readNonBlank(42));

        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(new Point(-1, 3)));
        System.out.println(describe(""));
        System.out.println(describe(null));
    }
}
```

Compile and run with **JDK 21**:

```bash
javac --release 21 FlowScopeControlFlowDemo.java
java FlowScopeControlFlowDemo
```

Stdout:

```text
accepted:Java
not-string
blank-rejected
accepted:
read:scope
skip
skip
quadrant I
point:-1,3
blank
missing
```

Explanation of the paths:

- `normalize("  Java  ", false)`: `instanceof` is true; the `return "not-string"` branch does not run, so `text` is in scope for the subsequent checks.
- `normalize(17, false)`: the pattern does not match and the method exits immediately; no path reaches the statements using `text` when the value has the wrong type.
- `normalize("  ", false)`: `text` matches by type but fails the non-blank rule; flow scoping guarantees the type, while `isBlank()` checks the content.
- `readNonBlank("  scope  ")`: both sides of `A || B` are false in the `if` condition, proving the pattern matched and the string is non-blank when reaching the final `return`.
- `describe(new Point(2, 3))`: the record pattern matches and the guard confirms `x` and `y` are positive; `Point(-1, 3)` falls through to the next record pattern arm. Both arms have their own separate scopes.
- `describe(null)`: `case null` handles a null selector value before any other patterns.

## 14. Checklist for reading the control flow of a new expression

Whenever you encounter a pattern variable in code, go through these steps in order:

1. **Identify the pattern that declares the variable.** For example, `input instanceof String text` or `case Point(var x, var y)`; avoid confusing it with a same-named local variable in another scope.
2. **Trace the two `true`/`false` edges.** With `!`, flip the edges. With `&&`, the right-hand side receives the `true` edge; with `||`, the right-hand side receives the `false` edge. Pay attention to parentheses and operator precedence.
3. **Follow every path to the variable's usage site.** If even one non-matching path can still reach that point, the variable is not guaranteed to be in scope.
4. **Eliminate terminated paths.** Branches with `return`, `throw`, or `continue` can rule out non-matching paths from the remaining code under consideration; branches that only log do not.
5. **Keep the scope of each `case` or loop iteration separate.** A pattern variable in one `switch` arm is not automatically in scope in another; patterns in loop conditions must be evaluated against loop entry and exit points.
6. **Check the business logic as well.** "The variable's type matched" is different from "the value is valid." Flow scoping proves the safety of using the variable, not rules such as non-blank, positive numbers, or access permissions.

When you can answer the question **"at this point, have all paths proved that the pattern matched?"**, you have a reliable way to read flow scope through control flow. This is the foundation for using pattern matching concisely and safely, especially in complex boolean expressions and guard clauses.
