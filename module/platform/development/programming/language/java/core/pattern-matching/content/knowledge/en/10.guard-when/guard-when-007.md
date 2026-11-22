# Multiple Guards on the Same Type in Pattern Switch (Java 21+)

## 1. The Problem: One Type, Multiple Processing Rules

In Java 21, a pattern `switch` can contain **multiple branches using the same type pattern**, each accompanied by a different **`when` guard**. This lets us classify values of the same type by their content or business conditions, rather than relying solely on their class.

For example, for values that are all `String`, you may want to distinguish blank/whitespace strings, error messages with a special prefix, short strings, and ordinary text:

```java
static String classify(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> "blank";
        case String s when s.startsWith("ERR:") -> "error";
        case String s when s.length() < 5 -> "short";
        case String s -> "text";
        default -> "not a String";
    };
}
```

These `case String s` branches are **not treated as simple duplicates**, because the earlier branches have `when` conditions that determine when they are selected. If the pattern matches `String` but the guard evaluates to `false`, Java continues checking the next applicable branches. The **unguarded** `case String s` branch at the end of the group handles strings that do not satisfy any of the preceding guards.

This article focuses on the **"multiple guards on the same type"** technique: syntax, matching order, pattern variable scope, dominance, exhaustiveness, common mistakes, and runnable examples.

**Version note:** `when` guards in pattern `switch` were standardized in **Java 21 (JEP 441)**. Use JDK 21+; `--enable-preview` is not required. Pattern matching for `instanceof` has existed since Java 16, but that does **not** mean Java 17 supports `case ... when ...` in a standard `switch`.

## 2. How Does a Guard Combine with a Type Pattern?

Basic syntax:

```text
case Type variableName when booleanCondition -> result;
```

Example:

```java
case String s when s.length() > 10 -> "long text";
```

Conceptually, this involves three steps:

1. **Type match:** the selector value must first match `String s`; for values that are not a `String`, the guard does not need to be evaluated.
2. **Guard evaluation:** if the pattern matches, the variable `s` has static type `String` and is in scope for the expression after `when`. The guard must be a valid boolean-typed condition.
3. **Select or continue:** if the guard is true, the branch is selected; if false, this branch is not selected and selection continues with the subsequent case labels.

An example taking `Object` with multiple branches of the same type:

```java
static String classifyInteger(Object value) {
    return switch (value) {
        case Integer n when n < 0 -> "negative";
        case Integer n when n == 0 -> "zero";
        case Integer n -> "positive";
        default -> "not an Integer";
    };
}
```

For `-5`, the first branch matches; for `0`, the first guard is false and the second guard is true; for `7`, both guards are false and then the `case Integer n` branch handles it. For `"7"`, no `Integer` pattern matches, so `default` is used. An integer literal passed to an `Object` parameter is autoboxed into `Integer`.

**Note on the selector:** the expression inside `switch (...)` is evaluated **once**. Guards may be evaluated sequentially as their corresponding branches are reached, but stepping through multiple `case` branches does not re-evaluate the selector expression.

## 3. Why Are Multiple `case String s` Branches Allowed Together?

Each `case String s when ...` is **a distinct case label with its own pattern and guard**. All variables are named `s` in this example, but it is not a single variable shared across all branches:

```java
static String examine(Object value) {
    return switch (value) {
        case String s when s.isBlank() ->
                "blank (length=" + s.length() + ")";
        case String s when s.startsWith("#") ->
                "tag=" + s.substring(1);
        case String s ->
                "plain=" + s;
        default ->
                "other";
    };
}
```

The compiler determines the static type of `s` to be `String` in **each** branch; the scope of the pattern variable is bound to that case label, its guard, and the branch body guaranteed to match. Reusing the name `s` across separate branches is valid.

Conversely, you cannot read `s` in a `default` branch, which lies outside the scope of the preceding patterns:

```java
// Invalid: default is not allowed to use variable s from earlier String cases.
// default -> "other=" + s;
```

If you want to distinguish the role of each branch, you can also give them distinct names:

```java
case String blank when blank.isBlank() -> "blank";
case String code when code.startsWith("ERR:") -> "error";
case String text -> "text";
```

Different variable names do not change the matching mechanism. What matters is the **pattern type, guard, and position** of each branch.

## 4. Case Order Determines Priority When Conditions Overlap

This is the most important practical rule: **the first applicable branch is selected**. An object can satisfy multiple guards on the same type simultaneously. If multiple branches can match, **the order of appearance** determines which branch runs.

For example, the string `"ERR:"` satisfies both conditions:

- `s.startsWith("ERR:")` is `true`.
- `s.length() < 5` is also `true` because its length is 4.

With this order:

```java
case String s when s.startsWith("ERR:") -> "error";
case String s when s.length() < 5 -> "short";
```

The string `"ERR:"` is classified as `"error"`.

If you reverse the order:

```java
case String s when s.length() < 5 -> "short";
case String s when s.startsWith("ERR:") -> "error";
```

The exact same string is classified as `"short"`. This is not a compile-time error; both guards are valid. However, it can be a **business logic bug caused by wrong priority order**.

A clear way to structure branches:

1. Place rules with the **highest priority** first, such as error data, special keywords, or safety checks.
2. Follow with **more specific** rules or rules with particular thresholds.
3. Place the **unguarded** branch of the same type after the guarded branches to catch the remainder.
4. Place `default` if the selector can hold other types and the switch is not yet exhaustively covered.

For non-overlapping conditions, such as `n < 0` and `n == 0`, the order usually does not change the result; even so, keeping a consistent order helps readability and maintenance.

## 5. Complete Java 21 Program: Multiple Guards on String, Integer, and Record

Save the entire code below as **MultipleGuardsDemo.java**:

```java
public class MultipleGuardsDemo {
    record Order(int amount, String owner) {}

    static String classify(Object value) {
        return switch (value) {
            case null -> "null";

            case String s when s.isBlank() -> "blank";
            case String s when s.startsWith("ERR:") ->
                    "error:" + s.substring(4);
            case String s when s.length() < 5 -> "short:" + s;
            case String s -> "text:" + s;

            case Integer n when n < 0 -> "negative:" + n;
            case Integer n when n == 0 -> "zero";
            case Integer n -> "positive:" + n;

            default -> "other";
        };
    }

    static String route(Object item) {
        return switch (item) {
            case Order(int amount, String owner) when amount < 0 ->
                    "invalid:" + owner;
            case Order(int amount, String owner) when amount >= 100 ->
                    "priority:" + owner;
            case Order(int amount, String owner) ->
                    "normal:" + owner;
            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("   "));
        System.out.println(classify("ERR:"));
        System.out.println(classify("hi"));
        System.out.println(classify("hello"));
        System.out.println(classify(-3));
        System.out.println(classify(0));
        System.out.println(classify(8));
        System.out.println(classify(2.5));
        System.out.println(classify(null));

        System.out.println(route(new Order(-2, "An")));
        System.out.println(route(new Order(150, "Binh")));
        System.out.println(route(new Order(20, "Chi")));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac MultipleGuardsDemo.java
java MultipleGuardsDemo
```

Exact output:

```text
blank
error:
short:hi
text:hello
negative:-3
zero
positive:8
other
null
invalid:An
priority:Binh
normal:Chi
```

Explanation of each case:

| Input value | Selected branch | Reason |
| --- | --- | --- |
| `"   "` | `String s when s.isBlank()` | Whitespace-only string; first guard is true |
| `"ERR:"` | `String s when s.startsWith("ERR:")` | Has error prefix; prioritized before length check |
| `"hi"` | `String s when s.length() < 5` | Not blank, no error prefix, length less than 5 |
| `"hello"` | `String s` | Does not satisfy the three guards, but is still a string |
| `-3` | `Integer n when n < 0` | Negative integer |
| `0` | `Integer n when n == 0` | Negative guard is false; zero guard is true |
| `8` | `Integer n` | Not negative, not zero, still an Integer |
| `2.5` | `default` | `Double` does not match `String`/`Integer` patterns |
| `null` | `case null` | Handles null value explicitly |

The `route` method uses a **record pattern** (Java 21) on the same `Order` record:

- `Order(-2, "An")`: negative amount, returns `"invalid:An"`.
- `Order(150, "Binh")`: amount greater than or equal to 100, returns `"priority:Binh"`.
- `Order(20, "Chi")`: does not satisfy the two guards, returns `"normal:Chi"`.

The component variables `amount` and `owner` are created by the record pattern **separately in each branch**, not as variables persisting across the entire `switch`. If a component can be `null`, a guard calling a method on that component needs its own null-safety check; for example, `owner != null && owner.startsWith("A")`.

## 6. What Happens When a Guard Is False?

A branch with a pattern and a guard is selected only when **both** match. When the pattern matches but the guard returns `false`, Java **does not execute that branch's body**; the search for a matching branch continues.

Consider:

```java
static String size(Object value) {
    return switch (value) {
        case String s when s.length() > 10 -> "large";
        case String s when s.length() > 5 -> "medium";
        case String s -> "small";
        default -> "other";
    };
}
```

- For a 12-character string, the `"large"` branch is selected immediately.
- For an 8-character string, the first guard is false, the second guard is true, returning `"medium"`.
- For a 3-character string, both guards are false, and the unguarded `String s` branch returns `"small"`.
- For an `Integer` object, none of the `String` patterns match, returning `"other"`.

This mechanism resembles an `if / else if / else` chain, with the added benefit of type checking and pattern variables right in the case label. However, it does **not** mean every guard is evaluated: branches after the selected branch do not run.

**A non-matching guard is different from a guard that throws an exception.** If a `when` expression throws an exception, Java does **not** treat that as `false` to try the next case. The exception propagates according to normal Java rules unless handled. For example, `case String s when Integer.parseInt(s) > 0` throws `NumberFormatException` on `"abc"`; a subsequent `case String s` branch will **not** rescue this situation automatically.

## 7. Dominance: An Early Unguarded Branch Shadows Guarded Branches

The Java 21 compiler checks **dominance** to detect branches that are already completely covered by earlier labels.

The following snippet **does not compile**:

```java
static String wrong(Object value) {
    return switch (value) {
        case String s -> "any String";
        case String s when s.length() > 3 -> "long String";
        default -> "other";
    };
}
```

Because the earlier `case String s` matches all non-`null` strings, a guarded `String` branch after it can never be selected. The compiler reports that the later case label is **dominated**.

Fix:

```java
static String correct(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long String";
        case String s -> "other String";
        default -> "other";
    };
}
```

Place the guarded branch first, and the unguarded branch of the same type after it.

### Two special cases: `when true` and `when false`

- `case String s when true -> ...` is equivalent to a guard that is always true whenever the pattern matches. It can **dominate** subsequent `String` patterns just like an unguarded branch.
- `case String s when false -> ...` is a compile-time error in Java 21: the guard is the boolean constant `false`; the branch can never be selected.

These are cases the compiler can determine statically. For dynamic conditions like `s.length() > 0` followed by `s.length() > 3`, the compiler does not necessarily prove all logical relationships between guards. For instance, placing `> 0` before `> 3` typically makes the later branch **unreachable for long strings**, even though the code may still compile.

Always review **how your conditions overlap**, rather than relying solely on the compiler to warn about dominance.

## 8. One Guard per Case; Combine Multiple Conditions with `&&` and `||`

When a branch only makes sense if multiple conditions hold simultaneously, place the combined boolean expression after **a single** `when`:

```java
static String errorKind(Object value) {
    return switch (value) {
        case String s when s.startsWith("ERR:")
                && s.length() > 4 -> "error with detail";
        case String s when s.startsWith("ERR:") -> "empty error";
        case String s -> "plain";
        default -> "other";
    };
}
```

For `"ERR:42"`, it returns `"error with detail"`; for `"ERR:"`, it returns `"empty error"`. Subconditions inside a guard follow normal Java rules, including short-circuit evaluation of `&&` and `||`.

**Do not write two consecutive `when` clauses on one label:**

```java
// Invalid:
// case String s when s.startsWith("ERR:") when s.length() > 4 -> ...
```

If you want multiple processing paths, write **multiple `case ... when ...` labels**. If you want one branch to require multiple constraints simultaneously, use `&&`. If only one of the constraints is needed, use `||` and pay attention to parentheses to clarify operator precedence.

**Do not use commas in place of a chain of guards.** Multi-constant labels like `case RED, BLUE -> ...` are for grouping *constant labels*; they do not mean "add another guard" or "chain multiple pattern variables" onto the same branch.

## 9. `null`, Exhaustiveness, and Fallback Branches

### The selector may be `null`

In a Java 21 pattern `switch`, `case String s` does not match `null`; the guard `s.isBlank()` is not evaluated if the selector is null either. If your business logic allows `null`, handle it explicitly:

```java
static String safe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when s.isBlank() -> "blank";
        case String s -> "text";
        default -> "other";
    };
}
```

In a Java 21 `switch` over a reference type, `default` does **not** automatically substitute for `case null`: if there is no label handling null and the selector receives `null`, a `NullPointerException` can occur.

### Switch expressions must be exhaustive

With an `Object` selector, having only two guarded `String` branches does not cover all possible object types:

```java
// Not exhaustive for an Object selector:
// return switch (value) {
//     case String s when s.isBlank() -> "blank";
//     case String s when s.length() > 10 -> "long";
// };
```

You need to add branches to handle the remainder, such as `case String s -> "other text";` and `default -> "other";`.

Even if the selector has static type `String`, two guards still do not guarantee covering **every string**: there could be a string that satisfies neither guard. An unguarded `case String s` branch covers all non-null `String` values, making the switch expression type-exhaustive.

**Dynamic guards do not automatically count as "sufficiently exhaustive."** Even if a programmer reasons that `s.length() > 0` and `s.length() <= 0` partition all strings mathematically, the compiler does not necessarily use that logical inference to prove exhaustiveness. Add an appropriate unguarded branch or `default`.

### Record patterns and null components

A selector can be a non-null record whose component is null. For example, `Order(1, null)` is still a valid `Order` unless the constructor forbids it. A guard `owner.isBlank()` when `owner` is null can throw an NPE; you need `owner != null && owner.isBlank()` or data invariants.

Distinguish between **a null selector** and **null inside deconstructed data**; checking `case null` only handles the first case.

## 10. Guards with Side Effects: Why Should You Avoid Them?

A guard is a Java expression that can call methods, and those methods can mutate state or throw exceptions. This is syntactically valid in many cases, but it makes understanding branch order harder.

```java
static int checks = 0;

static boolean isLong(String text) {
    checks++;
    return text.length() > 5;
}

static String classify(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s when isLong(s) -> "long";
        case String s -> "ordinary";
        default -> "other";
    };
}
```

When the selector is not a `String`, `isLong` is not called; when the `String` is blank, the first branch already matches and `isLong` is not called either; only when the `String` is non-blank does Java reach the guard calling `isLong`.

You can use an example like the one above to **observe evaluation order**, but in production code you should prefer simple, deterministic guards without side effects. Conditions that mutate a database, perform I/O, or depend on the current time can cause the same selector to be classified differently and make bugs hard to reproduce.

To reiterate: evaluating the selector expression once **does not mean every guard runs only once across the whole program**. Each new invocation of the `switch` can re-evaluate the guards it passes through; a guard can be called multiple times across different invocations.

## 11. Compared to `if / else if`: When Should You Use Which?

The same classification logic for an `Object`:

```java
static String withIf(Object value) {
    if (value instanceof String s && s.isBlank()) {
        return "blank";
    } else if (value instanceof String s && s.length() > 10) {
        return "long";
    } else if (value instanceof String s) {
        return "text";
    }
    return "other";
}
```

Expressed with a Java 21 `switch`:

```java
static String withSwitch(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() > 10 -> "long";
        case String s -> "text";
        default -> "other";
    };
}
```

Both approaches can express the same priority order. `switch` groups branches around a **single selector**, lets the compiler check dominance/exhaustiveness, and can be easier to read when multiple data types are involved.

Consider `if / else if` if the conditions do not revolve around a common selector or involve different preparation steps. Use `switch` if the task is classifying **one value** by type and additional conditions, especially with sealed hierarchies or record patterns.

Do not force multiple guards just to replace a short, simple condition. If there are no genuine classification branches, a method call or a simple `if` may be more appropriate.

## 12. Common Mistakes and How to Fix Them

| Mistake | Why it happens | How to fix |
| --- | --- | --- |
| Placing `case String s` before `String ... when ...` branches. | The unguarded branch matches all Strings, so later branches are dominated. | Move guarded branches first and the general branch to the end. |
| Assuming Java automatically prioritizes the "most specific" condition. | With multiple dynamic guards, branch order matters; the compiler does not reorder by business logic. | Order guards explicitly by priority. |
| Writing `when true` followed by another case of the same type. | A constant-true guard behaves like an unguarded branch; it can dominate later cases. | Remove the redundant guard or adjust the order/condition. |
| Writing `when false` as a fallback branch. | A constant-false guard is rejected at compile time. | Remove the unreachable branch; use a valid fallback branch. |
| Writing `when cond1 when cond2`. | A single label cannot chain multiple `when` clauses like that. | Combine with `&&` or write separate case labels. |
| Assuming a false guard throws an exception. | A guard returning false simply makes Java try the next branch. | Use a fallback branch; distinguish this from a guard that actually throws an exception. |
| Assuming a guard that throws an exception moves on to the next case. | Exceptions are not interpreted as false. | Handle errors appropriately in the logic or let the caller catch them intentionally. |
| Using variable `s` from a case inside `default`. | A pattern variable is scoped to the control flow of its own case. | Declare another variable in an outer scope if needed. |
| Having only a few guarded branches and omitting all other branches. | A switch expression may not be exhaustive. | Add an appropriate unguarded branch or `default`. |
| Using `default` expecting it to catch `null`. | Java 21 does not treat `default` as a replacement for `case null` in reference-type switches. | Add `case null` when null is an expected input. |
| Calling a method in a guard on a null component. | Type pattern matching or record deconstruction does not guarantee all components are non-null. | Check for `null` or enforce data invariants before calling. |
| Assuming Java 17 has `when` syntax for standard switch patterns. | The feature was standardized in Java 21. | Compile with Java 21+ or use Java 17-compatible constructs. |

## 13. Exercises and Solutions

### Exercise 1 — Predict priority when two guards overlap

Given:

```java
static String route(Object value) {
    return switch (value) {
        case String s when s.length() > 0 -> "non-empty";
        case String s when s.length() > 3 -> "long";
        case String s -> "empty";
        default -> "other";
    };
}
```

What does `route("hello")` return? Will the compiler necessarily report dominance for the `"long"` branch?

**Answer:** it returns `"non-empty"`. For `"hello"`, the first guard is already true, so the `"long"` branch after it is not selected. Java 21 may accept this code because proving the logical relationship between **two dynamic guards** is not the same as dominance by an unguarded type pattern. For the `"long"` branch to be meaningful, place `s.length() > 3` before `s.length() > 0`.

### Exercise 2 — Classify integers with three guards

Write a switch expression taking `Object`; when it is an `Integer`, return `"even negative"` if negative and even, `"negative"` if negative and odd, and `"non-negative"` if non-negative. Other types return `"other"`.

**Solution:**

```java
static String classifyNumber(Object value) {
    return switch (value) {
        case Integer n when n < 0 && n % 2 == 0 ->
                "even negative";
        case Integer n when n < 0 -> "negative";
        case Integer n -> "non-negative";
        default -> "other";
    };
}
```

Results: `classifyNumber(-4)` returns `"even negative"`, `classifyNumber(-3)` returns `"negative"`, `classifyNumber(0)` returns `"non-negative"`, and `classifyNumber("4")` returns `"other"`. If `case Integer n when n < 0` were placed before the even-negative branch, the even-negative branch would never be selected for negative numbers.

### Exercise 3 — Spot the dominance error

Is the following snippet valid?

```java
static String bad(Object input) {
    return switch (input) {
        case String s when true -> "any String";
        case String s when s.startsWith("A") -> "starts with A";
        default -> "other";
    };
}
```

**Answer:** no. `when true` is a constant-true condition whenever the pattern matches; the first branch covers all strings and causes the subsequent `String` branch to be dominated. Fix it by moving the `startsWith("A")` branch first and using `case String s -> "any String";`.

### Exercise 4 — Add a fallback for a record

Given the record:

```java
record Score(int points) {}
```

Handle the same record with these conditions: points 90 or higher → `"excellent"`; 60 or higher → `"pass"`; lower → `"retry"`; values that are not a `Score` → `"unknown"`.

**Solution:**

```java
static String level(Object input) {
    return switch (input) {
        case Score(int points) when points >= 90 -> "excellent";
        case Score(int points) when points >= 60 -> "pass";
        case Score(int points) -> "retry";
        default -> "unknown";
    };
}
```

Place the 90 threshold before the 60 threshold because values of 90 or higher **also** satisfy `>= 60`. `level(new Score(95))` returns `"excellent"`, `level(new Score(75))` returns `"pass"`, and `level(new Score(40))` returns `"retry"`. This demonstrates a Java 21 record pattern, with `Score` declared in a valid scope.

### Exercise 5 — Does a false guard carry the variable over to the next branch?

```java
static String describe(Object input) {
    return switch (input) {
        case String text when text.length() > 5 -> "long";
        case String text -> "other String";
        default -> "other";
    };
}
```

**Answer:** for a string of length 3, the first guard is false, Java evaluates the `String text` label on the second branch, and that branch matches. The variable `text` in the second branch is **the second branch's own pattern variable**, not a retained variable from the first guard. No single pattern variable is shared across case labels.

## 14. Key Takeaways

**Multiple guards on the same type** means placing multiple `case T x when condition` branches in a pattern `switch`, usually ending with an unguarded `case T x`. Java 21 tries branches in order: the pattern must match the type, and only then is the guard evaluated; if the guard is false, it searches for the next applicable branch.

Three principles to remember most:

1. **Clear priority:** when guards overlap, the earlier case wins; order branches from specific/important to general.
2. **Do not place a general type pattern too early:** `case String s` or `when true` can dominate subsequent `String` branches.
3. **Exhaustiveness and safety:** handle `null` intentionally, ensure the switch is exhaustive, and keep guards simple, avoiding unexpected side effects or exceptions.

Official documentation:
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification SE 21 — The switch Statement (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification SE 21 — The switch Expression (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
