# When to Use `when` Instead of Nested `if` in Java Pattern Matching?

In Java 21+, `when` is a **guard** attached to a **pattern case label** of a `switch`. It adds a boolean condition **after the pattern matches** and decides whether that `case` branch is selected. Conversely, a nested `if` inside a `case` body checks a condition **after the branch has already been selected**.

Here is the most important difference:

- Use **`when`** when the condition needs to participate in **deciding which branch** of the `switch` is selected: if the guard is false, Java can try another `case`, and then `default` if needed.
- Use **nested `if`** when the type/pattern has already determined the branch and you want to **perform processing steps inside that branch**: secondary business checks, calculations, logging, choosing a result, or multiple actions.
- Use **plain `if` without `switch`** when you only need a single type test and a condition, for example `if (value instanceof String text && !text.isBlank())`.

Do not choose `when` just because the syntax is shorter. Choose based on whether the intent is **branch routing** or **post-routing processing**.

> **Version:** `when` in pattern matching for `switch` was finalized in **Java 21**. Java 17 supports pattern matching for `instanceof`, but does not yet support the `case String s when ...` syntax as a standard feature.

## 1. Putting `when` and Nested `if` Side by Side

Consider an input `Object value`, with two rules:

1. If it is a string starting with the letter `A`, return `"starts-with-A"`.
2. If it is any other string, return `"other-string"`; if it is not a string, return `"not-string"`.

**Using `when` — the condition is part of selecting the `case`:**

```java
static String usingWhen(Object value) {
    return switch (value) {
        case String text when text.startsWith("A") -> "starts-with-A";
        case String text -> "other-string";
        default -> "not-string";
    };
}
```

Java checks `String text`, and only then checks `text.startsWith("A")`. If the value is `"Java"`, the type pattern still matches, but the guard is false; Java continues to the subsequent `case String text` and returns `"other-string"`.

**Using nested `if` — the `String` branch is selected first:**

```java
static String usingNestedIf(Object value) {
    return switch (value) {
        case String text -> {
            if (text.startsWith("A")) {
                yield "starts-with-A";
            }
            yield "other-string";
        }
        default -> "not-string";
    };
}
```

The two approaches above can produce **the same result**, but they organize logic differently:

- `when` expresses **two string classification cases** as two `case` branches.
- `if` expresses **one branch for strings**, inside which a secondary decision is made to choose the final value.
- In a `switch expression`, a `case ... -> { ... }` block must use `yield` to supply a normal result; you cannot use `return` instead of `yield` for a `switch expression` returned from a method in this way.

The equivalence in **result** only holds because the nested `if` branch explicitly handles both the true and false cases. Without an `else` or a fallback `yield`, the behavior differs immediately.

## 2. Exact Mechanics of a Guarded Pattern

Java 21+ syntax:

```java
switch (selector) {
    case SomeType variable when booleanExpression -> action;
    case SomeType variable -> fallbackForSameType;
    default -> generalFallback;
}
```

In a `case SomeType variable when booleanExpression` label:

1. Java evaluates the **selector expression** of the `switch` to obtain the value to match against.
2. Java tests the **type pattern** `SomeType variable`. If it does not match, the guard is **not evaluated**.
3. If the pattern matches, the **pattern variable** is bound and can be used immediately in the guard.
4. Java evaluates the **boolean expression** after `when`. If the result is `true`, that branch is selected and executed.
5. If the guard returns `false`, that branch is not selected; the search for an appropriate branch continues. The value may match another pattern, a broader pattern, or fall into `default`.
6. If the guard **throws an exception**, the exception propagates according to normal rules; Java does not treat an exception as `false` and does not automatically fall back to `default`.

```text
Evaluate selector once
            |
            v
    Test case pattern
       /            \
   no match        match -> bind variable
      |                         |
      v                         v
  try next case         evaluate when guard
                        /       |       \
                     true     false    exception
                       |        |          |
                  select case  try next  propagate
                                case
```

Example:

```java
case String text when !text.isBlank() && text.length() >= 5 -> "long text";
```

A guard is a boolean expression; it can use `&&`, `||`, method calls, and valid comparisons. Because the `String text` pattern has already matched, `text` has static type `String` and is in scope for the guard. For a `null` or `Integer` selector, the guard on the `String` branch does not run.

**Pitfall to avoid:** there is no mechanism to “run `default` from inside a `case` body if an `if` returns `false`”. `default` is only considered during **case selection**, not as an `else` mechanism for an `if` already inside a selected branch.

## 3. Runnable Java 21+ Example: Multiple Condition Groups with `when`

Save the following content as **`GuardWhenDemo.java`**:

```java
public class GuardWhenDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "missing";

            case String text when text.isBlank() -> "blank";
            case String text when text.length() >= 5 ->
                    "long:" + text.toUpperCase();
            case String text -> "short:" + text;

            case Integer number when number < 0 ->
                    "negative:" + number;
            case Integer number -> "number:" + number;

            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify("   "));
        System.out.println(classify("Java"));
        System.out.println(classify("Spring"));
        System.out.println(classify(-2));
        System.out.println(classify(7));
        System.out.println(classify(2.5));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac GuardWhenDemo.java
java GuardWhenDemo
```

Exact output:

```text
missing
blank
short:Java
long:SPRING
negative:-2
number:7
unsupported
```

Breakdown:

| Input | Pattern/guard | Final branch |
| --- | --- | --- |
| `null` | `case null` | `"missing"` |
| `"   "` | `String` matches, `isBlank()` is true | `"blank"` |
| `"Java"` | `String` matches; `isBlank()` is false, length 4 is less than 5 | unguarded `case String text`, `"short:Java"` |
| `"Spring"` | `String` matches; `isBlank()` is false, length 6 reaches 5 | `"long:SPRING"` |
| `-2` | `Integer` matches, `number < 0` is true | `"negative:-2"` |
| `7` | `Integer` matches, negative guard is false | unguarded `case Integer number`, `"number:7"` |
| `2.5` | Neither `String` nor `Integer` | `default`, `"unsupported"` |

**Why is `when` a good fit here?** The `case` lines form an **input classification rule table**. Reading from top to bottom immediately shows: blank string, long string, remaining strings, negative integer, remaining integers, unsupported type. If all that logic were placed inside a single `case String` with multiple `if`s, selecting among string cases would be harder to see as independent branches.

At the same time, having unguarded `case String text` and `case Integer number` afterward ensures both types are completely handled even when no guard matches.

## 4. Same Result, Different Organization: Complete Example

Save **`BranchChoiceDemo.java`**:

```java
public class BranchChoiceDemo {
    static String usingWhen(Object value) {
        return switch (value) {
            case String text when text.startsWith("A") -> "starts-with-A";
            case String text -> "other-string";
            default -> "not-string";
        };
    }

    static String usingNestedIf(Object value) {
        return switch (value) {
            case String text -> {
                if (text.startsWith("A")) {
                    yield "starts-with-A";
                }
                yield "other-string";
            }
            default -> "not-string";
        };
    }

    public static void main(String[] args) {
        System.out.println(usingWhen("Apple"));
        System.out.println(usingNestedIf("Apple"));
        System.out.println(usingWhen("Java"));
        System.out.println(usingNestedIf("Java"));
        System.out.println(usingWhen(42));
        System.out.println(usingNestedIf(42));
    }
}
```

```bash
javac BranchChoiceDemo.java
java BranchChoiceDemo
```

```text
starts-with-A
starts-with-A
other-string
other-string
not-string
not-string
```

### When `when` Reads More Clearly

If the rule is essentially “a string starting with `A` is a distinct input category,” expressing it directly on the `case` label gives the code the meaning *pattern + branch-selection condition*:

```java
case String text when text.startsWith("A") -> "starts-with-A";
case String text -> "other-string";
```

You can add multiple conditions for the same type in priority order (as long as you do not create a dominated branch), or reserve the `default` branch for unsupported data.

### When Nested `if` Reads More Clearly

If, after knowing the input is a `String`, the program needs to perform a sequence of actions specific to `String` and check conditions only to adjust a secondary outcome, putting the logic in **a single block** is usually more natural:

```java
case String text -> {
    String normalized = text.strip();
    if (normalized.isEmpty()) {
        yield "empty";
    }
    yield normalized.toUpperCase();
}
```

This is **a single branch for handling `String`** with a normalization flow and an internal decision. There is no need to turn every small step into a guarded case.

*The snippet above is part of a Java 21+ `switch expression`, not a standalone Java class.*

## 5. Important Trap: Nested `if` Does Not Fall Back to `default`

The following two snippets are **not equivalent**.

**Option A: `if` inside an already-selected `case String`:**

```java
switch (value) {
    case String text -> {
        if (text.length() > 4) {
            System.out.println("inside: long");
        }
    }
    default -> System.out.println("inside: fallback");
}
```

If `value = "Go"`, the `String` case is already selected because the value is a string. `text.length() > 4` is `false`, so nothing is printed. After the branch finishes, **Java does not proceed to `default`**. That is normal behavior: a nested `if` only controls statements inside the branch.

**Option B: `when` is a condition for the case to apply:**

```java
switch (value) {
    case String text when text.length() > 4 ->
            System.out.println("guard: long");
    default -> System.out.println("guard: fallback");
}
```

If `value = "Go"`, the `String` pattern matches, but the `length() > 4` guard is false, so this case **is not selected**. There are no other cases, so `default` is selected and prints `guard: fallback`.

### Run It to Prove It

Save **`NestedIfPitfallDemo.java`**:

```java
public class NestedIfPitfallDemo {
    static void nested(Object value) {
        switch (value) {
            case String text -> {
                if (text.length() > 4) {
                    System.out.println("inside: long");
                }
            }
            default -> System.out.println("inside: fallback");
        }
    }

    static void guarded(Object value) {
        switch (value) {
            case String text when text.length() > 4 ->
                    System.out.println("guard: long");
            default -> System.out.println("guard: fallback");
        }
    }

    public static void main(String[] args) {
        nested("Go");
        guarded("Go");
        nested(42);
        guarded(42);
    }
}
```

```bash
javac NestedIfPitfallDemo.java
java NestedIfPitfallDemo
```

Output:

```text
guard: fallback
inside: fallback
guard: fallback
```

**No line is printed from `nested("Go")`.** The program prints three lines in total because the first call selects the `String` branch, where the nested `if` condition is false. This is precisely the situation where you should use `when` if you genuinely want a **`switch`-level fallback branch** to handle short strings.

Do not assume that an `if` inside a case can change the case selection after the `switch` has already chosen a branch.

## 6. Cases Where You Should Choose `when`

### 6.1. Classification Rules Depend on Both Type and Additional Conditions

```java
return switch (value) {
    case Integer score when score >= 90 -> "excellent";
    case Integer score when score >= 60 -> "passed";
    case Integer score -> "failed";
    default -> "not a score";
};
```

*This is an illustrative Java 21+ switch expression snippet.*

The branches clearly express **priority order**. A score of 95 satisfies both `>= 90` and `>= 60`, but the `>= 90` branch comes first and is selected. A score of 75 skips the first branch and selects the second. A score of 40 enters the remaining `Integer` branch. This pattern fits **distinct status groups**, such as grading or routing processing strategies.

### 6.2. You Need to Continue Trying Subsequent Branches When a Condition Fails

```java
return switch (value) {
    case String text when text.startsWith("admin:") -> "admin";
    case String text when text.startsWith("user:") -> "user";
    case String text -> "unrecognized string";
    default -> "unsupported";
};
```

The strength of `when` is that **a false guard allows trying another case**. Using nested `if` without a proper `else` loses the ability to fall back at the `switch` level.

### 6.3. You Want to Express the Guard Right Next to the Pattern for Readability

```java
case String command when !command.isBlank() -> handle(command);
```

This shows that a value only belongs to this case if it is **both a `String` and non-blank**. The reader does not need to open a long block to find the routing condition. This works well when the condition is short, pure, and clearly describes the essence of the case.

### 6.4. Record Patterns Need Additional Business Condition Checks

Illustrative Java 21+ example:

```java
record Purchase(String category, int amount) {}

static String route(Object value) {
    return switch (value) {
        case Purchase(String category, int amount) when amount >= 100 ->
                "priority: " + category;
        case Purchase(var category, var amount) ->
                "standard: " + category;
        case null -> "missing";
        default -> "unsupported";
    };
}
```

Record patterns test the structure and bind components; `when amount >= 100` adds the priority condition. If the amount is under 100, the priority pattern does not apply and the general `Purchase` branch can receive that transaction.

**Note:** `String category` is a type pattern for a component; if the `category` component is `null`, it does not match that priority branch. Conversely, `var category` in a record component pattern can bind a `null` component. Therefore, do not attribute every difference between the two branches solely to `amount >= 100` if record data can contain null. This is an **illustrative code snippet inside a Java 21+ class**, not a standalone file.

## 7. Cases Where You Should Keep Nested `if` or Use Plain `if`

### 7.1. Only One Type Test and One Condition

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

If there are not multiple cases to branch on, `switch` with `when` usually adds unnecessary complexity. The `instanceof` syntax with a pattern variable and `&&` is already a good fit and works in Java 17+.

### 7.2. Once a Branch Is Selected, You Want to Finish the Work Inside That Branch

```java
switch (value) {
    case String text -> {
        System.out.println("Received a string");
        if (text.isBlank()) {
            System.out.println("Warning: blank input");
        }
        System.out.println("String handling finished");
    }
    case Integer number -> System.out.println("Number: " + number);
    case null -> System.out.println("Missing");
    default -> System.out.println("Unsupported");
}
```

Here, `if` only controls printing a warning. **Whether the string is blank or not, the `String` branch still needs to run the finishing step**. Using `when` just to print a warning could force duplicating the shared handling or make the logic harder to follow.

### 7.3. Long Logic, Multiple Steps, or Internal Checks

```java
case String text -> {
    String normalized = text.strip();
    if (normalized.length() > 100) {
        normalized = normalized.substring(0, 100);
    }
    yield normalized;
}
```

If multiple statements serve a single case after the type is identified, a block with `if` can be more readable than a series of repeated `case` branches. With a `switch expression`, `yield` is required when completing normally from a block.

### 7.4. You Do Not Want to Use Java 21 or Must Support Java 17

Java 17 supports:

```java
static String classify(Object value) {
    if (value instanceof String text) {
        if (text.isBlank()) {
            return "blank";
        }
        return "text:" + text;
    }
    return "other";
}
```

This is a valid method in a Java 17 class without preview features. Java 17 does not have the standard `case String text when ...` syntax. When a library or project is locked to `--release 17`, nested `if` or `if/else if` is the better choice.

### 7.5. The Logic Is a Side Action, Not a Case-Selection Condition

Operations such as logging, updating metrics, normalizing data, calling services, or performing multi-step dependency checks should usually go in the branch body or a separate method. Guards describe **case-selection conditions**, not a place to execute an entire business workflow.

## 8. Flow Scoping: `when` Can Only Use Variables After the Pattern Matches

Example:

```java
case String text when text.length() >= 5 -> text.toUpperCase();
```

`text` is a pattern variable, not a variable declared before the `switch`. Java allows using `text` in the guard because **the `String text` type pattern has already matched**; it is also in scope on the right-hand side of `->` when the case is selected.

The condition in `when` must have type **`boolean`**. A call returning `int` is not a valid guard:

```java
// Invalid: text.length() is int, not boolean.
// case String text when text.length() -> "long";
```

Correct way:

```java
case String text when text.length() > 4 -> "long";
```

`when` is not a connector that replaces every `if`. You do not write:

```java
// Invalid: when is not syntax for a regular if.
// if (value instanceof String text) when text.length() > 4 { ... }
```

Nor do you attach `when` to labels without a pattern, such as `case null` or `default`:

```java
// Invalid: guards are only for cases with a pattern.
// case null when someCondition -> ...;
// default when someCondition -> ...;
```

If you need secondary logic for `null`, use `case null -> { if (...) ... }` or handle it before the `switch`.

## 9. Case Ordering and Dominance Errors

When patterns can match the same type, **label ordering matters**. An unguarded type pattern can cover all values of that type. Therefore, the following order is **correct**:

```java
switch (value) {
    case String text when text.length() >= 5 ->
            System.out.println("long");
    case String text ->
            System.out.println("other string");
    default ->
            System.out.println("not a string");
}
```

However, the following order is rejected by the compiler:

```java
// DOES NOT COMPILE:
// switch (value) {
//     case String text -> System.out.println("any string");
//     case String text when text.length() >= 5 ->
//             System.out.println("long");
//     default -> System.out.println("other");
// }
```

Because the unguarded `case String text` already applies to every `String`, the guarded `String` case after it is **dominated** and can never be selected. This is a compile-time error; Java does not try to work around it by inspecting the condition's contents.

Practical rule: **place specific guarded patterns before a general unguarded pattern**, and end with a valid fallback branch when needed. For patterns of different types or inheritance hierarchies, Java also has dominance rules; do not assume every reordering is valid.

A guard is also not a post-check after a case is already chosen: it genuinely affects *whether the case applies*, which is why the compiler must consider coverage and dominance.

## 10. Exhaustiveness: A Guard Does Not Automatically Cover the Whole Type

In a `switch expression`, the compiler must prove that normal values have a handling branch (*exhaustive*). A guard can be `false`, so writing only a guarded case is usually **not enough**:

```java
// DOES NOT COMPILE: switch expression is not exhaustive.
// static String bad(Object value) {
//     return switch (value) {
//         case String text when text.length() >= 5 -> text;
//     };
// }
```

You can fix it with another case for `String` and `default` for other types:

```java
static String good(Object value) {
    return switch (value) {
        case String text when text.length() >= 5 -> "long";
        case String text -> "short";
        default -> "other";
    };
}
```

*This is an illustrative Java 21+ method.* Note that `good(null)` still **throws `NullPointerException`** because there is no `case null`. `default` does not automatically catch a null selector in Java 21. If null is a valid input, add:

```java
case null -> "missing";
```

in an appropriate position inside the `switch` block.

For an **enhanced switch statement** with patterns, you also need to pay attention to exhaustiveness rules. Do not infer from traditional constant-only `switch statement`s that any `switch` with patterns is allowed to omit remaining coverage branches.

## 11. Guards Should Be Clear, Safe, and Free of Unexpected Side Effects

`when` can call regular methods:

```java
case String text when isEligible(text) -> process(text);
```

*This snippet assumes `isEligible` returns `boolean` and `process` is already defined.*

However:

- A guard only runs **if its corresponding pattern matches**. Do not put a task inside a guard that the program must perform for *all* input types.
- If a guard returns `false`, Java continues checking other cases. If a guard **throws an exception**, the exception propagates; `default` is not a `catch` block.
- Side effects such as writing to a database, sending an HTTP request, updating state, or mutating shared variables in a guard make case selection order hard to reason about. Prefer simple, stable conditions with little or no side effects.
- For complex conditions, consider extracting a meaningfully named predicate method, such as `isEligible(text)`, or performing necessary validation **before** the `switch`.
- When multiple guards on the same type can be true simultaneously, the first matching branch is selected. Rule ordering is part of the logic; do not reorder branches for aesthetic reasons without testing.
- `when` is not guaranteed to be faster than nested `if`. Actual performance depends on the source code, branch structure, JIT, and predicate cost. Choose based on semantics and maintainability first.

In particular, if most of the processing is internal logic for one case and the guard only acts as an “on/off switch for an action,” nested `if` can make the intent clearer and avoid repeating conditions.

## 12. Quick Comparison During Code Review

| Question | Prefer `when` | Prefer nested `if` |
| --- | --- | --- |
| Does the condition decide which case is selected? | Yes | No, the case is already selected |
| If the condition is false, do you want to try another case/default? | Yes | Not automatically |
| Are there multiple rules on the same type to separate into clear branches? | Often yes | Not necessarily |
| Are there many shared steps after recognizing a type? | Easy to duplicate code | Usually reasonable |
| Is there only one `instanceof` test? | Can be overkill | Use `if`/`&&` directly |
| Need to run on Java 17 without preview? | Not suitable | Suitable |
| Does the guard contain many side effects? | Avoid | Put logic in the branch body/separate method |
| Need `yield` in a `switch expression` block? | No if using an expression arm | Yes when a block needs to return a value |
| Is a failing rule treated as a “different” kind of input? | Easy to express with the next case | Must write an explicit `else` branch |

There is no rule that “`when` is always better than nested `if`.” A `switch` expression with three simple cases often reads well with guards, whereas a case with a long workflow often reads better as a single case organized internally with `if`.

## 13. Common Mistakes and How to Fix Them

**Mistake 1 — Thinking a false nested `if` will jump to `default`.**

```java
case String text -> {
    if (text.isBlank()) {
        System.out.println("blank");
    }
}
default -> System.out.println("fallback");
```

If `text` is not blank, the `String` branch is already selected; `default` does not run. If you want the `switch` fallback branch to receive non-blank strings, use `case String text when text.isBlank() -> ...; default -> ...;` or add handling after the condition.

**Mistake 2 — Placing a broad case before a guarded case.**

```java
// Invalid: the guarded String below is dominated.
// case String text -> "any";
// case String text when text.isBlank() -> "blank";
```

Swap the order: guarded case first, unguarded case after.

**Mistake 3 — Thinking `when` is a null check.**

```java
// Cannot catch a null selector:
// case String text when text == null -> "null";
```

The type pattern `String text` does not match null, so the guard never runs for a null selector. Use a separate `case null`.

**Mistake 4 — Thinking `when` works on `case null` or `default`.**

```java
// Invalid:
// case null when true -> "null";
// default when true -> "other";
```

Guards only attach to pattern case labels, not to the labels above.

**Mistake 5 — Writing a `switch expression` with a block and forgetting `yield`.**

```java
case String text -> {
    String result = text.trim();
    yield result;
}
```

*This is an illustrative block of a `switch expression`.* You cannot write a block that computes `result` and falls off the end without providing a normal result for the expression.

**Mistake 6 — Thinking an exception in a guard means the guard is false.**

```java
case String text when text.charAt(0) == 'A' -> "A";
```

For an empty string, `text.charAt(0)` throws `StringIndexOutOfBoundsException`, rather than falling back to default. Use:

```java
case String text when !text.isEmpty() && text.charAt(0) == 'A' -> "A";
```

The right-hand side of `&&` only runs when `text` is non-empty.

**Mistake 7 — Using `when` to perform steps with side effects.**

Separate **case determination** (predicate) from **business execution** inside the case body, so it is easy to test and does not depend on the evaluation order of multiple guards.

## 14. Practical Decision Guide

When deciding between `when` and nested `if`, ask in order:

1. **What categories should the input be classified into?** If each branch is a distinct meaningful category, a `switch` with patterns may fit.
2. **Does the condition decide which case is selected, or only a processing step inside the case?** The first leans toward `when`; the second leans toward `if`.
3. **If the condition is false, must it move to the next rule?** If yes, `when` expresses this directly. If not, a single `case` with an internal `if` is usually enough.
4. **Do the cases overlap?** Put specific guards before general cases; avoid dominance and test the ordering.
5. **Is the fallback branch clear?** Is there an unguarded case for the same type or a `default` when needed? Is there a `case null` if null is valid?
6. **What is the Java target?** Only use `switch` `when` on Java 21+; on Java 17 use `instanceof` combined with `if`/`&&`.
7. **Is the guard safe?** Check boolean conditions, empty-string cases, exceptions, execution cost, and side effects.
8. **Write tests for both true and false guards.** Test the next branch, `default`, other input types, and null; do not test only the happy path.

### Conclusion

**Use `when` when you want the extra condition to be part of *selecting the case*: if the pattern matches but the guard is false, that branch is not selected and Java continues looking for another branch.** Use **nested `if`** when the case is already selected and the condition only splits work **inside the case**; `if` does not automatically make Java go back and pick another case.

Keeping this distinction clear helps avoid the two biggest mistakes: thinking a nested `if` will trigger `default`, and placing a guarded case after a same-type case that already covers all data.

### References

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): `when` guards, dominance, exhaustive switches, and null handling.
- [Oracle Java 21 — Switch Expressions](https://docs.oracle.com/en/java/javase/21/language/switch-expressions.html): `->` arm syntax, blocks, and `yield`.
- [Java Language Specification 21 — Switch Statements `14.11](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-14.html#jls-14.11): label selection rules, pattern guards, and switch.
