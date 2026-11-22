# Distinguishing `when` from Conditions Inside a `case` Body in Java Pattern Switch

**Topic:** Java Core Pattern Matching → *Guard when*. This article uses **Java 21** syntax (JEP 441: *Pattern Matching for switch* is finalized); the focus is on the difference between **guarding a `case` label** with `when` and **an `if` statement executed inside a `case` branch**. The main example is a complete program that compiles with JDK 21 or later, without requiring `--enable-preview`.

> **Key takeaway:** `when` participates in **deciding which `case` label is selected**. An `if` inside the `case` body only participates in **processing after the label has already been selected**. When a `when` guard evaluates to `false`, Java can evaluate the next `case` label. When an `if` inside the branch evaluates to `false`, Java **does not automatically go back to look for another `case`**.

## 1. Background: how does pattern matching for switch work?

First, consider a `switch` expression on a value of type `Object`:

```java
static String describe(Object input) {
    return switch (input) {
        case null -> "missing";
        case String s -> "text: " + s;
        case Integer n -> "number: " + n;
        default -> "other";
    };
}
```

A label such as `case String s` contains a **type pattern**. When `input` is a non-null `String`, the pattern matches and the variable `s` is initialized; the program executes that branch. A `switch` with arrow branches `->` selects a matching branch and executes it, without *fall-through* to subsequent branches.

Sometimes knowing only that "this is a `String`" is not enough. We may also need to distinguish blank strings, long strings, or short strings; or for `Integer`, negative versus non-negative values. Java 21 allows placing a condition right after the pattern:

```java
case String s when s.isBlank() -> "blank";
```

`String s` is the **pattern**, and `s.isBlank()` is the **guard expression**. Both must succeed for this label to apply.

## 2. `when` is a condition on the label, not the branch body

Read the label:

```java
case String s when s.length() >= 5 -> "long string";
```

In logical sequence:

1. Java evaluates the `switch` selector expression to obtain a value.
2. Java checks whether that value **matches the pattern `String s`**.
3. Only if the pattern matches does Java evaluate the **guard `s.length() >= 5`**. At this point `s` is already initialized and type-safe.
4. If the guard evaluates to `true`, this label **applies** and Java executes the part after `->`.
5. If the guard evaluates to `false`, this label **does not apply**. Java continues searching for another matching label in the `switch`.

The point in step 5 is the core difference. A guard does not "select the branch and then run an internal check"; the guard makes the decision of **whether or not to select the current label**.

Example:

```java
static String label(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() >= 5 -> "long";
        case String s -> "short";
        case null -> "null";
        default -> "other";
    };
}
```

Expected results:

| Input | Notable steps | Result |
| --- | --- | --- |
| `"   "` | String pattern matches; `isBlank()` guard is true | `blank` |
| `"Java"` | Blank guard is false; length ≥ 5 guard is false; reaches unguarded String | `short` |
| `"Pattern"` | Blank guard is false; length ≥ 5 guard is true | `long` |
| `42` | Does not match String; reaches `default` | `other` |
| `null` | `case null` label handles null selector | `null` |

Placing **specific guarded labels first**, and the general `String s` label last, ensures classifications are evaluated in the right order.

### A guard only runs when the pattern matches

With an `Integer` selector, `case String s when s.length() > 4` does not call `s.length()`. Because the pattern already failed to match, the guard is not evaluated. Avoid misinterpreting this as Java running every `when` condition for every object type.

## 3. `if` in a `case` body only runs after the case is selected

Now move the condition into a branch body:

```java
static String bodyCheck(Object input) {
    return switch (input) {
        case String s -> {
            if (s.isBlank()) {
                yield "blank";
            }
            yield "nonblank";
        }
        case null -> "null";
        default -> "other";
    };
}
```

Here, **as soon as** `input` matches `String s`, the `case String s` branch is already selected. Then `if (s.isBlank())` is executed **inside the branch**.

If `s.isBlank()` returns `false`, Java executes the subsequent statements **in the same branch**. It does not automatically fall down to `case null` or `default`, nor does it re-evaluate other patterns.

In a `switch` expression, use `yield` to return a value from a block-bodied branch. `return` inside a switch expression is generally not used to return the value of the expression itself; when you want to produce a branch value, `yield` is the right syntax.

### Common mistake: expecting a false `if` to try the next label

Suppose we need to prioritize strings starting with `"A"`, while other `CharSequence` values are handled generically.

**Using a guard as intended:**

```java
static String guardFallback(Object input) {
    return switch (input) {
        case String s when s.startsWith("A") -> "starts-with-A";
        case CharSequence chars -> "general sequence";
        case null -> "null";
        default -> "other";
    };
}
```

- `guardFallback("Alpha")` → `starts-with-A`.
- `guardFallback("Beta")` → `general sequence`: the `String` pattern matches, but the guard is false, so Java continues to `CharSequence`.
- `guardFallback(new StringBuilder("Hi"))` → `general sequence`: not a String, but is a CharSequence.

**Using `if` in the body does not fall back to another case:**

```java
static String bodyDoesNotFallback(Object input) {
    return switch (input) {
        case String s -> {
            if (s.startsWith("A")) {
                yield "starts-with-A";
            }
            yield "String branch already selected";
        }
        case CharSequence chars -> "general sequence";
        case null -> "null";
        default -> "other";
    };
}
```

`bodyDoesNotFallback("Beta")` returns **`String branch already selected`**, **not** `general sequence`. The String label is selected as soon as the pattern matches, before the inner `if` begins executing.

**Conclusion:** When the goal is *"if the additional condition is false, try the next `case` label"*, use `when`. When the goal is *"this branch is already selected; inside the branch there are multiple distinct processing steps"*, use `if`.

## 4. Comparing nature and expressiveness

| Aspect | `case Pattern when condition ->` | `case Pattern -> { if (condition) ... }` |
| --- | --- | --- |
| Evaluation timing | During the phase of determining the applicable label | After the label has been selected |
| Must the pattern match first? | Yes; only then is the guard checked | Yes; the branch body only runs after matching |
| What if the condition is false? | The current label does not apply; searches for the next label | Continues executing the branch body; does not automatically try another label |
| Can it use the pattern variable? | Yes, within the guard's scope | Yes, within the branch body |
| Classifying multiple groups of the same type | Well-suited for consecutive guarded labels | Suitable if you want to group logic under one type branch |
| Need multiple statements, loops, try/catch | Put them in the branch body after `->` | Use directly inside the branch body block |
| Impact on dominance/exhaustiveness | Yes; the compiler considers guards in label rules | No; an internal `if` does not change the coverage of the case label |
| Exception in condition | If the guard throws an exception, case selection is aborted without fallback | If `if` throws an exception, branch execution is aborted |
| Usable with literal `case null` or constant case? | No; `when` attaches to pattern cases | Yes, an `if` can be placed inside a constant/null branch body |
| Primary role | **Case selection** | **In-case processing** |

There is no rule to "always prefer `when`". Choose based on **the semantics you need to express** and maintainability.

## 5. When do both approaches produce the same result?

If you are only subdividing within a single type and do not need another case to handle the input when the condition is false, you can write both approaches to produce equivalent results.

### Multi-label guarded form

```java
static String byGuard(Object input) {
    return switch (input) {
        case null -> "null";
        case String s when s.isBlank() -> "blank";
        case String s when s.length() >= 5 -> "long:" + s;
        case String s -> "short:" + s;
        case Integer n when n < 0 -> "negative:" + n;
        case Integer n -> "nonnegative:" + n;
        default -> "other";
    };
}
```

### Grouped form using `if` in the branch body

```java
static String byBody(Object input) {
    return switch (input) {
        case null -> "null";
        case String s -> {
            if (s.isBlank()) {
                yield "blank";
            }
            if (s.length() >= 5) {
                yield "long:" + s;
            }
            yield "short:" + s;
        }
        case Integer n -> {
            if (n < 0) {
                yield "negative:" + n;
            }
            yield "nonnegative:" + n;
        }
        default -> "other";
    };
}
```

Both methods return **the same result for the inputs in this article's demo program**, because the combined `String` branch also covers all three groups, and the combined `Integer` branch splits negative/non-negative. However, the two approaches **are not identical in how labels are determined**:

- `byGuard`: when a guard is false, Java searches for the next label. The classification boundaries are at the **switch labels**.
- `byBody`: as soon as String matches, Java enters the String block; the classification boundaries are internal **if statements**.
- With `byBody`, you cannot expect a broader type branch placed later to be automatically selected if an `if` inside String is false. To achieve that, you must reorganize the logic or use a guard.

Therefore, **same output does not mean same control semantics**. Two expressions are equivalent only when the internal branching is written exhaustively and exception behavior, side effects, and evaluation order are all preserved.

## 6. Pattern variables: scoped to both the guard and the branch body

`String s` in the label:

```java
case String s when s.length() >= 5 -> "long: " + s;
```

also declares the pattern variable `s`. When the guard runs, the pattern has already matched, so `s` is definitely matched. This variable is also available in the `->` branch body of **that same label**.

```java
static int textLength(Object input) {
    return switch (input) {
        case String s when !s.isEmpty() -> s.length();
        case String s -> 0;
        case null -> -1;
        default -> -2;
    };
}
```

The two `s` names in two different labels are **two separate pattern variable declarations**. A variable introduced by one label does not carry over to another label.

**Do not call `s.length()` before checking the type** if `input` is not yet known to be a String. `when` ensures the condition runs in a context where the pattern has already matched. Similarly, an `if` inside the selected branch body can also safely use `s`.

### Record patterns and guard conditions

`when` does not apply only to type patterns:

```java
record Order(String code, int total) {}

static String orderCategory(Object input) {
    return switch (input) {
        case Order(String code, int total) when total >= 100 ->
                "big:" + code;
        case Order(String code, int total) ->
                "small:" + code;
        case null -> "null";
        default -> "not-order";
    };
}
```

The input `new Order("A", 120)` returns `big:A`; `new Order("B", 15)` returns `small:B`. For a small total, the first record pattern still **matches structurally**, but the guard is false; therefore Java proceeds to the unguarded Order label. The condition `total >= 100` can use the variable `total` declared in the record pattern.

## 7. Label ordering and dominance

Java 21 does not simply pick the first branch with the same type name. The compiler also checks **dominance** (whether an earlier label already covers a later label).

### Valid: specific guard first, unguarded branch after

```java
static String category(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "other string";
        case null -> "null";
        default -> "non-string";
    };
}
```

Java allows a guarded String pattern before an unguarded String pattern. The guard can be false, so the later label still has a chance to apply.

### Invalid: general String pattern before a guarded String pattern

```java
// DOES NOT COMPILE in Java 21:
static String invalidOrder(Object value) {
    return switch (value) {
        case String s -> "string";
        case String s when s.isBlank() -> "blank"; // Dominated by the preceding label
        case null -> "null";
        default -> "other";
    };
}
```

The unguarded `case String s` label already handles every non-null String, so the guarded label of the same type after it is dominated. An `if` inside the String branch body does **not** give subsequent labels any extra chance to apply.

### `when true` and `when false` are special cases

According to JLS Java SE 21:

- `case String s when true` is treated as **unguarded** for the relevant rules because the guard is the constant expression `true`. It can dominate a subsequent String label.
- A guard that is a **constant expression with value `false`** causes a **compile-time error**. Do not use `when false` to temporarily disable a branch.
- For a dynamic guard like `s.isBlank()`, Java does not assume it is always true; thus, placing an unguarded String label afterward is the standard way to handle the remainder.

This rule is directly tied to how the compiler checks label structure; **`if (true)` or `if (false)` inside a case body is not an equivalent substitute** for dominance.

## 8. Guards and exhaustiveness: an internal `if` does not determine coverage

A `switch` expression must be **exhaustive**: the set of labels must cover all values required by static checking rules. Enhanced `switch` statements with pattern cases must also be exhaustive in Java 21.

Consider a selector of type `String`:

```java
// DOES NOT COMPILE: switch expression is not exhaustive.
static String incomplete(String value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long";
        case String s when s.length() <= 3 -> "short";
    };
}
```

Humans know the two conditions together cover all non-null String lengths. However, the compiler does **not** prove in general that arbitrary guard expressions are exhaustive. To make it complete, add an **unguarded** label:

```java
static String complete(String value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long";
        case String s -> "short";
    };
}
```

Note: the expression above still **throws `NullPointerException`** if `value` is null because `case null` is missing, even though it is exhaustive for type String under static rules. When null handling is needed, add `case null -> ...`.

With an `if` inside a case body, the compiler looks at the coverage of the **outer label**, without using the `if` condition to expand or narrow the label set:

```java
static String completeUsingBody(String value) {
    return switch (value) {
        case String s -> {
            if (s.length() > 3) {
                yield "long";
            }
            yield "short";
        }
    };
}
```

The unguarded `String s` label is unconditional for non-null String values, so the `switch` expression is valid. The `if` condition only determines the result **after the label has been selected**.

**Practical technique:** whenever you want multiple `when` labels, always ask yourself whether there is an unguarded label or `default` satisfying exhaustiveness. Do not rely on `when` conditions "appearing to cover everything".

## 9. Syntax constraints and guard checks in Java 21

### 9.1. `when` only attaches to pattern cases

**Valid:**

```java
case String s when s.startsWith("A") -> "A";
```

**Invalid:**

```java
// DOES NOT COMPILE:
// case null when condition -> "missing";
// case 1 when condition -> "one";
```

`case null` and constant labels like `case 1` are not pattern cases; Java 21 does not allow placing `when` directly after them. If additional conditional handling is needed, place an `if` inside the corresponding branch body, or choose a different selector design.

### 9.2. Return type must be `boolean` or `Boolean`

A guard is an **expression** of type `boolean` or `Boolean`:

```java
case String s when s.length() > 3 -> "long";
```

You cannot use an `int` expression as a guard:

```java
// DOES NOT COMPILE:
// case String s when s.length() -> "invalid";
```

If a guard has type `Boolean` and evaluates to `null`, unboxing during evaluation can throw `NullPointerException`. This does **not** cause Java to continue to the next `case` label; the error from the guard propagates out of label selection.

### 9.3. External variables in a guard must be `final` or effectively final

The JLS also requires local variables, formal parameters, and exception parameters **used in a guard but not declared in the guard** to be `final` or *effectively final*. Example:

```java
static String threshold(Object input, int minLength) {
    return switch (input) {
        case String s when s.length() >= minLength -> "long enough";
        case String s -> "too short";
        case null -> "null";
        default -> "other";
    };
}
```

`minLength` is never reassigned, so this is valid. If you modify `minLength` with an assignment so that it is no longer effectively final in the method, a guard referencing that variable will cause a compile-time error. With an `if` in the branch body, this guard-specific constraint does not apply in the exact same way; standard scope and definite assignment rules still apply.

### 9.4. Guards can call methods, but should avoid side effects

`when` is evaluated during **the process of finding an applicable label**. If a method called in a guard mutates data, performs I/O, writes logs, or throws errors, label-matching order and exception handling can become confusing:

```java
case String s when expensiveCheck(s) -> "accepted";
```

The syntax above is just an example assuming `expensiveCheck` is defined to return a boolean. It is valid, but the check cost is incurred every time the preceding pattern matches and Java needs to evaluate the guard. **A guard returning false** makes Java search for the next label; **a guard throwing an exception** terminates label selection abnormally, rather than acting as "false then fallback".

When a check is complex, needs multiple statements, updates state, or requires custom exception handling, you can choose **`if` in a case block** or extract a clearly named, pure predicate method.

## 10. Null and non-application of patterns/guards

For a `null` selector in a Java 21 pattern switch:

- A type pattern `String s` **does not match `null` at the top-level selector**.
- A `when` guard attached to `String s` **is not executed** for a null selector.
- `default` **alone does not catch null**. Without `case null`, the `switch` throws `NullPointerException`.
- You can write `case null -> ...`, or `case null, default -> ...` when null and the remaining values are handled the same way.

Valid example:

```java
static String category(Object input) {
    return switch (input) {
        case null -> "missing";
        case String s when s.isBlank() -> "blank";
        case String s -> "string";
        default -> "other";
    };
}
```

If you want to check an additional condition **after the null label has been selected**, use `if` inside the `case null` branch body, not `when`:

```java
static String missing(Object input, boolean required) {
    return switch (input) {
        case null -> {
            if (required) {
                yield "error: required value";
            }
            yield "optional missing";
        }
        case String s -> s;
        default -> "other";
    };
}
```

This is a situation where **`if` inside the case body is required by syntax**.

## 11. Complete program: two ways to classify and different fallback results

Create a file **`WhenVsCaseBodyDemo.java`** with the following content:

```java
public class WhenVsCaseBodyDemo {
    record Order(String code, int total) {}

    static String byGuard(Object input) {
        return switch (input) {
            case null -> "null";
            case String s when s.isBlank() -> "blank";
            case String s when s.length() >= 5 -> "long:" + s;
            case String s -> "short:" + s;
            case Integer n when n < 0 -> "negative:" + n;
            case Integer n -> "nonnegative:" + n;
            default -> "other";
        };
    }

    static String byBody(Object input) {
        return switch (input) {
            case null -> "null";
            case String s -> {
                if (s.isBlank()) {
                    yield "blank";
                }
                if (s.length() >= 5) {
                    yield "long:" + s;
                }
                yield "short:" + s;
            }
            case Integer n -> {
                if (n < 0) {
                    yield "negative:" + n;
                }
                yield "nonnegative:" + n;
            }
            default -> "other";
        };
    }

    static String guardFallback(Object input) {
        return switch (input) {
            case String s when s.startsWith("A") -> "starts-with-A";
            case CharSequence chars -> "general sequence";
            case null -> "null";
            default -> "other";
        };
    }

    static String wrongBody(Object input) {
        return switch (input) {
            case String s -> {
                if (s.startsWith("A")) {
                    yield "starts-with-A";
                }
                yield "String branch already selected";
            }
            case CharSequence chars -> "general sequence";
            case null -> "null";
            default -> "other";
        };
    }

    static String withRecord(Object input) {
        return switch (input) {
            case Order(String code, int total) when total >= 100 ->
                    "big:" + code;
            case Order(String code, int total) -> "small:" + code;
            case null -> "null";
            default -> "not-order";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {null, "   ", "Java", "Pattern", -3, 4, 2.5};

        for (Object input : inputs) {
            System.out.println(byGuard(input) + " | " + byBody(input));
        }

        System.out.println("guard: " + guardFallback("Beta"));
        System.out.println("body: " + wrongBody("Beta"));
        System.out.println("builder: "
                + guardFallback(new StringBuilder("Hi")));

        System.out.println(withRecord(new Order("A", 120)));
        System.out.println(withRecord(new Order("B", 15)));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 -encoding UTF-8 WhenVsCaseBodyDemo.java
java WhenVsCaseBodyDemo
```

Output:

```text
null | null
blank | blank
short:Java | short:Java
long:Pattern | long:Pattern
negative:-3 | negative:-3
nonnegative:4 | nonnegative:4
other | other
guard: general sequence
body: String branch already selected
builder: general sequence
big:A
small:B
```

Explanation:

1. **First seven lines:** `byGuard` and `byBody` classify identically because both approaches handle all required cases for each type. The null label outputs `null`, blank strings output `blank`, `Java` (4 characters) outputs `short`, `Pattern` (7 characters) outputs `long`, negative and non-negative integers are separated, and `Double` hits `default`.
2. **`guardFallback("Beta")`:** `Beta` matches the String type pattern, but `startsWith("A")` is false. Java continues and selects the `CharSequence` label, producing `general sequence`.
3. **`wrongBody("Beta")`:** the String label was already selected before `if` ran; a false `if` only moves execution to the next `yield` inside the String block. It does not fall down to the CharSequence label.
4. **`StringBuilder("Hi")`:** not a String, but is a CharSequence, so the `CharSequence` label is selected.
5. **Two Orders:** both record patterns match Order objects. The `total >= 100` guard accepts Order A; object B fails the first guard and proceeds to the unguarded Order label.

This practical example shows that **"can return the same result"** and **"can select different labels"** are two separate questions.

## 12. Common mistakes when choosing between `when` and `if`

**Mistake 1 — turning `when` into an `if` inside a branch and expecting the next case to run.** Once a label is selected, an `if` cannot make the `switch` restart label selection. To fall back between cases, move the condition into `when`.

**Mistake 2 — placing a general type case before a guarded case of the same type.** The unguarded branch can dominate the guarded branch, causing a compile error. Place specific labels first and general labels afterward.

**Mistake 3 — failing to provide a branch covering the remaining data.** Arbitrary sets of guards are not automatically considered exhaustive. Use an appropriate unguarded pattern or `default`; also handle `null` according to your API policy.

**Mistake 4 — placing `when` after `case null` or a constant.** `when` attaches to pattern cases in Java 21; place conditional checks inside the null/constant case body instead of attaching an invalid guard.

**Mistake 5 — using a non-boolean expression as a guard.** `when s.length()` has the wrong type; it must be a boolean expression, such as `when s.length() > 3`.

**Mistake 6 — assuming a guard throwing an exception is equivalent to false.** When a guard throws an exception, the `switch` is also aborted without trying the next label; handle exceptions explicitly if you want a different policy.

**Mistake 7 — putting overly complex logic inside a guard.** Predicates should be readable, low on side effects, and ideally pure; multi-step logic, logging, I/O, or try/catch belong in a separate method or the case body.

**Mistake 8 — confusing syntax across Java versions.** `when` in pattern switch is finalized syntax in Java 21. Older preview documentation may use different guard forms; compile with `--release 21` and do not blindly copy earlier preview syntax.

## 13. Self-check exercises

**Exercise A.** Predict the result for inputs `"Apple"` and `"Berry"`:

```java
static String f(Object obj) {
    return switch (obj) {
        case String s when s.startsWith("A") -> "A";
        case String s -> "other-string";
        case null -> "null";
        default -> "not-string";
    };
}
```

**Answer:** `f("Apple")` returns `A`; `f("Berry")` returns `other-string`. The guard only decides whether the first label applies.

**Exercise B.** Replace the first label with:

```java
// Example showing only a branch fragment for a switch expression:
case String s -> {
    if (s.startsWith("A")) {
        yield "A";
    }
    yield "not-A";
}
```

What happens if a `case String s -> ...` still remains after it?

**Answer:** the subsequent String label is dominated, causing a compile-time error. When using an unguarded String branch, all string sub-classifications must live inside that branch's block, or the labels must be reorganized with guards first.

**Exercise C.** The two guards `case String s when s.length() > 3` and `case String s when s.length() <= 3` mathematically "cover all" strings. Why is a `switch` expression containing only these two labels still invalid?

**Answer:** exhaustiveness checking in the JLS does not perform arbitrary logical proofs on dynamic conditions. An unguarded label or an appropriate fallback branch is required; also handle null separately if needed.

**Exercise D.** Can you write `case null when required -> ...`?

**Answer:** No. A `when` guard only attaches to pattern cases. Use `case null -> { if (required) ... }`.

**Exercise E.** In `case String s when s.length() > 3`, does Java call `length()` when the selector is an `Integer`? What if `s.length()` is replaced by a method that throws an exception?

**Answer:** It is not called when the selector is Integer because the String pattern fails. When the selector is String and the guard throws an exception, label selection is aborted by the exception, not treated as the guard returning false.

**Exercise F.** Write a `switch` expression for `Object` with the groups: negative Integer, non-negative Integer, empty/blank String, other String, null, and all other types. Then rewrite it using exactly one Integer label and one String label, with `if` statements inside the blocks. Both versions must produce the same results; explain where they differ in the label-selection step.

## 14. Checklist for choosing the construct

Before using `when`, answer:

1. Is this condition **a condition for a case label to apply**, or just **a processing decision inside an already-selected case**?
2. If the condition is false, do you actually want to **try another case**? If yes, prefer a guard.
3. If there are multiple guards for the same type, have you placed **specific guards before the unguarded pattern** to avoid dominance?
4. Is there an unguarded label/`default` satisfying exhaustiveness? Is there an explicit policy for a null selector?
5. Does the guard use the pattern variable after matching and have type `boolean`/`Boolean`? Are external variables in the guard `final`/effectively final?
6. Does the condition have side effects, potential errors, or high cost? If so, reorganize the logic for testability and readability.
7. If using a `switch` expression with block-bodied cases, have you used `yield` to return values completely along all required normal paths?

**Rule of thumb:** `when` = *condition participating in label selection*; `if` in a `case` body = *condition participating in work performed after label selection*.

## References

- [JLS Java SE 21 `14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): `case Pattern when Guard` label form, guard constraints, dominance, and compatibility.
- [JLS Java SE 21 `14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): coverage checking.
- [JLS Java SE 21 `14.11.1.2 — Determining Which Switch Label Applies at Run Time](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): sequence of testing patterns, guards, and subsequent labels.
- [JLS Java SE 21 `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): scope of pattern variables.
- [JLS Java SE 21 `15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): returning values and `yield`.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): finalized feature in Java 21 and rationale for guarded patterns.
