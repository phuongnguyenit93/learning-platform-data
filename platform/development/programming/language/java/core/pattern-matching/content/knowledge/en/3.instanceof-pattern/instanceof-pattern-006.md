# Multiple Consecutive `instanceof` Branches in Java

**Scope:** Java 17 and later; the main examples use **pattern matching for `instanceof`**, a feature stabilized in Java 16. The goal is to understand how Java processes **multiple `instanceof` checks on the same object** in order, the difference between independent `if` statements and `if / else if` chains, how to choose type ordering, pattern variable scoping, and common pitfalls. This is a runtime type-checking technique, not a polymorphic dispatch mechanism that replaces every Java method.

## 1. An object can match multiple `instanceof` checks

The `instanceof` operator checks whether a reference value is compatible with a specified type. With a **type pattern**, the check also binds the matched value to a variable:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

In `value instanceof String text`:

- `value` is the expression being tested; its static type is `Object`.
- `String text` is the type pattern: it requires the value to be a `String` and declares the variable `text`.
- When it matches, the `instanceof` expression evaluates to `true` and the variable `text` can be used within the scope where the compiler determines it has definitely matched.
- When it does not match, the expression evaluates to `false`; the pattern variable cannot be used on the unmatched path.

**Do not assume that each object matches only one type.** A `String` is simultaneously a `CharSequence`, `Comparable<?>`, `Serializable`, and `Object`; an `Integer` is simultaneously a `Number`. Therefore, two separate checks can both evaluate to true.

Illustrative example:

```java
Object value = "Java";

System.out.println(value instanceof CharSequence); // true
System.out.println(value instanceof String);       // true
System.out.println(value instanceof Number);       // false
```

All three expressions above are valid because the static type `Object` allows checking against those target types. The result depends on the **runtime type** of the value, not merely on the static type `Object`.

## 2. Case 1: multiple consecutive independent `if` statements

When writing `if` statements **not chained with `else`**, Java evaluates **each `if` statement from top to bottom**. One true condition does not automatically skip the subsequent `if` statements.

```java
Object value = "Java";

if (value instanceof CharSequence chars) {
    System.out.println("CharSequence: " + chars.length());
}

if (value instanceof String text) {
    System.out.println("String: " + text.toUpperCase());
}
```

Output:

```text
CharSequence: 4
String: JAVA
```

Both branches execute, because `"Java"` satisfies both types. This is useful if **each branch represents an independent task**, such as recording different capabilities that an object supports.

With this structure:

1. Java checks the condition of the first `if`.
2. If true, Java executes the body of the first branch.
3. Upon exiting the first branch body normally, Java **continues** to the second `if` statement and checks its condition.
4. The process repeats for subsequent `if` statements.

An important detail: if an earlier branch contains `return`, `throw`, or another control transfer that prevents execution from continuing, later branches will not run. And if code in an earlier branch modifies state that a later branch reads, the later condition is evaluated against the state **at that moment**, not a snapshot from before the check sequence.

**When to use:** when you need to perform **all applicable actions** for the types/interfaces that the object satisfies; when you want conditions that are not mutually exclusive.

**When not to use:** when you expect only a single classification or a single handling branch. Using multiple independent `if` statements in this case easily leads to overwritten results, actions running twice, or duplicate logs.

## 3. Case 2: `if / else if / else` chain

An `if / else if` chain is a structure that **selects the first branch whose condition is true**:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println("String: " + text.length());
} else if (value instanceof CharSequence chars) {
    System.out.println("CharSequence: " + chars.length());
} else if (value instanceof Number number) {
    System.out.println("Number: " + number.doubleValue());
} else {
    System.out.println("Unknown");
}
```

Output:

```text
String: 4
```

Java evaluates the conditions from top to bottom. As soon as it encounters a true branch, Java runs that branch's body and **skips all remaining `else if` and `else` branches**. An object may satisfy multiple types, but in **a single** `if / else if` chain, at most **one branch** is executed.

Comparison of the two structures:

| Characteristic | Independent `if` statements | `if / else if` chain |
| --- | --- | --- |
| Number of branches that can run | Not limited to one branch; multiple branches can run | At most one branch |
| Are later branches checked if an earlier branch is true? | Yes, if control flow continues to them | No |
| How does ordering affect behavior? | Affects the order of actions and observed state | Directly affects which branch is selected |
| Best suited for | Independent actions that can apply simultaneously | Classification or selecting a single handler |
| Fallback branch | Each `if` must be considered separately | `else` handles when all preceding conditions are false |

### Why should specific types usually be checked before general types?

`Integer` inherits from `Number`. If `Number` is checked first in an `else if` chain, an `Integer` will immediately be caught by the `Number` branch:

```java
Object value = 7;

// Syntactically valid, but the Integer branch does not run for this value:
if (value instanceof Number n) {
    System.out.println("Number");
} else if (value instanceof Integer i) {
    System.out.println("Integer");
}
```

Output:

```text
Number
```

If you want to handle `Integer` separately, reverse the order:

```java
Object value = 7;

if (value instanceof Integer i) {
    System.out.println("Integer");
} else if (value instanceof Number n) {
    System.out.println("Number");
}
```

Output:

```text
Integer
```

Practical rule: **place specific types/conditions first, and broader types/conditions later** in a single-branch selection chain. For example, handle `String` before `CharSequence`, or `Integer` before `Number`. If business requirements intentionally prioritize a general rule, you can place it first; in that case, you must understand that it will block the specific branches it covers.

Note: `if / else if` does not require all types to be related to each other. You can check `String`, `Number`, and `Runnable` consecutively on a value of type `Object` as long as each `instanceof` expression is type-valid.

## 4. Case 3: consecutive `if` statements with early `return`

In a method that returns a value, independent `if` statements can be organized as **guard clauses**:

```java
static String classify(Object value) {
    if (value instanceof Integer i) {
        return "Integer: " + i;
    }
    if (value instanceof Number n) {
        return "Number: " + n;
    }
    if (value instanceof String s) {
        return "String: " + s;
    }
    return "Other";
}
```

Whenever a branch matches, `return` terminates the method. Therefore, in terms of **result selection** behavior, this form is similar to an `if / else if` chain, without needing nested `else` levels. Later branches are only evaluated when all preceding branches have been passed without returning.

Do not apply this reasoning if a branch body is not guaranteed to terminate the method. For example:

```java
if (value instanceof Number n) {
    System.out.println(n);
}
if (value instanceof Integer i) {
    System.out.println(i + 1);
}
```

For `value = 7`, **both** lines are printed; there is no `return`, so there is no single-branch selection behavior.

## 5. Branches with additional conditions: `&&` and classifying the same type

Sometimes multiple consecutive branches check the **same type** but distinguish further based on content conditions. Use the `&&` operator so the pattern variable is available on the right-hand side:

```java
Object value = "  ";

if (value instanceof String s && !s.isBlank()) {
    System.out.println("Non-blank string");
} else if (value instanceof String s2) {
    System.out.println("Blank string");
} else {
    System.out.println("Not a string");
}
```

Output:

```text
Blank string
```

Explanation:

- In the first branch, `value instanceof String s` is true, but `!s.isBlank()` is false, so **the entire condition** is false; Java evaluates the next branch.
- In the second branch, `value instanceof String s2` is still true, so this branch handles the blank string.
- If `value` is not a `String`, both conditions are false and execution reaches `else`.
- `s` and `s2` are **two different pattern variables**, each in its own scope.

With `&&`, the right-hand side only runs after the left-hand side is true (*short-circuit*), so `s` can be used safely. Conversely, the following snippet **does not compile**:

```java
// INVALID: the right-hand side of || can run when the pattern has not matched.
// if (value instanceof String s || s.isBlank()) {
//     System.out.println(s);
// }
```

When conditions on different types are mutually exclusive, you can use `&&` to put filtering logic directly into the appropriate branch; there is no need for manual casting or calling `getClass()`.

## 6. Scope of a pattern variable across multiple branches

The variable in `instanceof` is called a **pattern variable**; its scope is defined by the JLS according to **control flow** (*flow scoping*), not just by curly braces.

### Inside the matching branch

```java
static void printIfString(Object value) {
    if (value instanceof String text) {
        System.out.println(text.toUpperCase()); // Valid
    } else if (value instanceof Integer number) {
        System.out.println(number + 1); // Valid
    }
    // text and number cannot be used here.
}
```

`text` is in scope in the body of the `String` branch; `number` is in scope in the body of the `Integer` branch. One branch cannot arbitrarily use a variable declared by another branch.

### After the non-matching branch exits the method

```java
static void requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }
    // By this point, all normal execution paths have matched String text.
    System.out.println(text.length()); // Valid
}
```

The negation `!` combined with `throw` guarantees that execution only continues when the pattern has matched. This is another example of flow scoping, particularly useful when you want to reduce nesting depth.

### Typical scoping error

```java
// DOES NOT COMPILE:
// if (value instanceof String text) {
//     System.out.println(text);
// }
// System.out.println(text); // Not guaranteed that the pattern has matched.
```

Avoid creating multiple pattern variables with the same name in overlapping scopes, or assuming a variable from an upper branch can still be used in a lower branch. When each branch has a distinct role, naming them `text`, `integer`, `number` improves readability and reduces confusion.

## 7. Handling `null`, non-matching types, and overlapping types

### The `null` value

In the `instanceof` examples here, `null` does not match any type pattern:

```java
Object value = null;

System.out.println(value instanceof String); // false
System.out.println(value instanceof Number); // false
```

In an `if / else if` chain with an `else`, `null` falls through to `else` if there is no preceding `value == null` check. If you need to distinguish `null` from an unknown object, add a separate `value == null` branch, usually at the start of the chain when it is a prioritized business case. Do not call methods on `value` before checking for null.

### Overlapping matching types

Not only class inheritance, but also **interfaces** create overlapping matches. `String` matches both `String` and `CharSequence`; `StringBuilder` matches `CharSequence` but does not match `String`.

| Input value (static type `Object`) | `instanceof String` | `instanceof CharSequence` | `instanceof Number` | `instanceof Integer` |
| --- | --- | --- | --- | --- |
| `"Java"` | `true` | `true` | `false` | `false` |
| `new StringBuilder("Hi")` | `false` | `true` | `false` | `false` |
| `7` (boxed as `Integer`) | `false` | `false` | `true` | `true` |
| `2.5` (boxed as `Double`) | `false` | `false` | `true` | `false` |
| `null` | `false` | `false` | `false` | `false` |

This table helps predict outcomes when **multiple checks use the same object**. In an `else if` chain, even though multiple columns may be `true`, only the earliest matching branch runs.

## 8. Complete Java 17 example: multi-branch chain and multiple independent `if` statements

Create the file **`InstanceofBranchesDemo.java`** with the following content:

```java
public class InstanceofBranchesDemo {
    static String describe(Object value) {
        // Choose one branch: the first branch whose condition is true wins.
        if (value instanceof String text && !text.isBlank()) {
            return "String: " + text + " (" + text.length() + ")";
        } else if (value instanceof String blankText) {
            return "String blank";
        } else if (value instanceof Integer integer) {
            // Integer is checked before Number because Integer is a Number.
            return "Integer: " + (integer + 1);
        } else if (value instanceof Number number) {
            return "Number: " + number.doubleValue();
        } else if (value instanceof CharSequence chars) {
            // StringBuilder enters this branch, not the String branch.
            return "CharSequence: " + chars.length();
        } else if (value == null) {
            return "null";
        } else {
            return "Other";
        }
    }

    static void independentChecks(Object value) {
        // Both if statements can run for a String.
        if (value instanceof CharSequence chars) {
            System.out.println("CharSequence: " + chars.length());
        }
        if (value instanceof String text) {
            System.out.println("String: " + text.toUpperCase());
        }
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe("   "));
        System.out.println(describe(7));
        System.out.println(describe(2.5));
        System.out.println(describe(new StringBuilder("Hi")));
        System.out.println(describe(null));
        System.out.println(describe(true));
        independentChecks("abc");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 -encoding UTF-8 InstanceofBranchesDemo.java
java InstanceofBranchesDemo
```

Output:

```text
String: Java (4)
String blank
Integer: 8
Number: 2.5
CharSequence: 2
null
Other
CharSequence: 3
String: ABC
```

Step-by-step explanation in order:

1. `"Java"` matches `String text` and is not blank, so it returns from the first branch.
2. `"   "` matches the `String` type but fails `!text.isBlank()`; the second `String blankText` branch is selected.
3. The integer `7` is boxed into `Integer`; the `Integer` branch is prioritized before `Number` and adds 1.
4. The floating-point number `2.5` is boxed into `Double`; it does not match `Integer` but matches `Number`.
5. `StringBuilder("Hi")` is not a `String`, but is a `CharSequence`, so it returns length 2.
6. `null` does not match any type pattern and enters the `value == null` check branch.
7. `true` is boxed into `Boolean`, matches none of the checked types, and falls into `else`.
8. `independentChecks("abc")` runs both the `CharSequence` branch and the `String` branch, printing the last two lines.

The example uses stable Java 17 features and does not require `--enable-preview`. Each branch uses the pattern variable directly; no manual casting like `(String) value` or `(Number) value` is needed.

## 9. Common mistakes when ordering multiple branches

**Mistake 1 — using multiple `if` statements while expecting only one branch to run.** A `String` can match both `CharSequence` and `String`. Replace them with an `else if` chain or add `return` when you truly want only one choice.

**Mistake 2 — placing a general superclass/interface before a specific type.** For example, placing `Number` before `Integer` in an `else if` chain causes an `Integer` value to enter the `Number` branch immediately, never reaching the specific branch. Ordering is even more important when multiple branches check interfaces or superclasses.

**Mistake 3 — assuming `else if` always runs after the previous branch.** It is only evaluated when all preceding conditions are false; if the first branch is already true, the rest of the chain is skipped.

**Mistake 4 — using a pattern variable in a branch where it is not guaranteed to have matched.** `text` can only be used where the compiler proves it has been initialized; do not take a variable from the first `if` branch and use it directly in another `else if` branch.

**Mistake 5 — confusing `&&` and `||`.** With `obj instanceof String s && s.length() > 0`, `s` is valid on the right-hand side; with `||`, that is not true because the right-hand side runs when the left-hand pattern may have failed.

**Mistake 6 — missing `null` and unknown type cases.** Add `else`/a default value; add an `obj == null` condition if `null` needs special handling.

**Mistake 7 — checking types that are impossible to convert to even from the static type.** The following example is **invalid** in terms of types because `String` is a `final` class and cannot simultaneously be an `Integer`:

```java
// DOES NOT COMPILE:
// String value = "Java";
// if (value instanceof Integer n) { // Incompatible types
//     System.out.println(n);
// }
```

If an input must accept multiple data types, use an appropriate general static type (such as `Object` or a suitable interface/superclass) and check at runtime.

**Mistake 8 — thinking `instanceof` supports arbitrary concrete generic type arguments.** Due to *type erasure*, `Object value; value instanceof java.util.List<String> strings` is an invalid example. When you need to determine whether an object is a list, you can check `List<?> list` and then validate each element individually if business logic requires it.

**Mistake 9 — using `instanceof` instead of all polymorphic designs.** If every subtype needs an action with the same meaning, an overridden method on the class/interface may express it more clearly. An `instanceof` chain is most useful when code needs to classify uncontrolled input data, at API boundaries, or in operations adapting across multiple types.

## 10. How to choose a structure and self-check exercises

Before writing multiple branches, answer three questions:

1. **Do you need to perform multiple tasks on the same object?** If yes, consider multiple independent `if` statements; if you only choose one task, use `if / else if / else` or early `return`.
2. **Do the types overlap?** Check `extends` and `implements` relationships. For a single-branch selection chain, place the specific conditions that need priority first.
3. **Where do you need to use the matched variable?** Place the code using the variable inside valid flow scoping regions; use `&&` for additional conditions or exit early on the non-matching path.

**Exercise 1.** Predict the output, then verify:

```java
Object value = new StringBuilder("xy");

if (value instanceof CharSequence chars) {
    System.out.println(chars.length());
}
if (value instanceof String text) {
    System.out.println(text);
}
```

Answer: only prints `2`. `StringBuilder` is a `CharSequence` but not a `String`.

**Exercise 2.** Replace `value` with `7` and try two `else if` versions: checking `Number` before `Integer`, then reversing them. Answer: the first order selects the `Number` branch; the reversed order selects the `Integer` branch. Explain why both branches never run together.

**Exercise 3.** Consider `value = " "` when writing:

```java
if (value instanceof String s && !s.isBlank()) {
    System.out.println("A");
} else if (value instanceof String other) {
    System.out.println("B");
} else {
    System.out.println("C");
}
```

Answer: prints `B`. The `String` type matches in both places, but the first branch fails because of the `!s.isBlank()` condition; only the second `else if` branch runs. This is the difference between **pattern matching** and **the entire conditional expression matching**.

**When should you consider `switch`?** If there are many input types, code using Java 21 or later can consider *pattern matching for `switch`*, `when` guards, and exhaustiveness checking. However, you need to understand `switch`'s own rules (dominance and `null` handling); do not mechanically convert independent `if` statements into `switch` because `switch` selects branches with different semantics.

## References

- [JLS Java SE 17 `15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type checking and pattern matching with `instanceof`.
- [JLS Java SE 17 `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): scope of a pattern variable and flow analysis.
- [JLS Java SE 17 `14.9 — The `if` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.9): `if`/`else` branch selection.
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): design rationale and stable status since Java 16.
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441): extension in Java 21 when switching to `switch`-based branching.
