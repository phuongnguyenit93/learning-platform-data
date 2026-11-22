# What is a Guarded Pattern Label in Java?

> **Module:** Java Core Pattern Matching → Guard when. This lesson uses **Java 21+** syntax, where *pattern matching for `switch`* was standardized (JEP 441). Snippets annotated with **ERROR** are used to explain compilation errors, not standalone runnable programs. The complete program and stdout are presented in section 8.

## Learning Objectives

After this lesson, you will:

- Understand that a **guarded pattern label** is a `case` label containing a **pattern** and a `when` condition, distinguishing it from an ordinary type pattern, constant label, and `default`.
- Know the evaluation order: check the pattern first, then evaluate the guard; if the guard is false, `switch` can try the next label.
- Use pattern variables within the proper scope inside the guard and branch body without manual casting.
- Order guarded and unguarded labels to avoid **dominance** errors, while ensuring **exhaustiveness** and handling `null`.
- Recognize common pitfalls: constant `true`/`false` guards, guards with side effects, conditions that throw exceptions, and precedence with constant labels.

## 1. Concept and Official Syntax

A **guarded pattern label** is a `case` label with the structure:

~~~text
case Pattern when BooleanExpression -> Result
~~~

Where:

- **`Pattern`**: describes the type/structure that the selector value must match; for example, `String text`.
- **`when`**: contextual keyword placing a *guard* condition immediately after the pattern in the `case` label.
- **`BooleanExpression`**: a conditional expression returning `boolean` (or a `Boolean` value unboxed to `boolean`); it can use variables just bound by the pattern.
- **`-> Result`**: the branch body when both the pattern and the guard succeed. For `:`-style switch statements, the corresponding syntax is `case Pattern when BooleanExpression:`.

Basic example:

~~~java
static String describe(Object input) {
    return switch (input) {
        case String text when text.length() > 5 -> "long text";
        case String text -> "other text";
        default -> "not a string";
    };
}
~~~

This is an **illustrative method** placed inside a Java 21+ class, not yet a standalone runnable file.

The label `case String text when text.length() > 5` has **two conditions that must both be true**:

1. The selector `input` must match the type pattern `String text`.
2. The variable `text` has been bound, and then the expression `text.length() > 5` must evaluate to `true`.

If `input` is `"abcdef"`, the first branch is selected. If `input` is `"cat"`, the `String` pattern still matches, but the guard is false, so the next `case String text` branch receives the value. If it is `Integer.valueOf(3)`, the guard `text.length() > 5` is **not executed** because the `String` pattern itself does not match.

**Terminology distinction:** `String text` is a **type pattern**; the entire `case String text when ...` is a **guarded pattern label**. `when` does not turn a boolean expression into a new type pattern, and it does not change the type of the selector.

## 2. Evaluation Mechanism of a `when` Label

For `switch (selectorExpression)`, in the normal case Java 21 executes in the following order:

1. **Evaluate the selector expression once** to obtain the value to match.
2. Examine the `case` labels in the order written (when the compiler accepts the switch structure).
3. If a type pattern does not match, **skip the guard of that label** and continue examining other labels.
4. If the pattern matches, initialize the **pattern variables** and then evaluate the guard.
5. If the guard is `true`, select the branch and execute its body. If it is `false`, continue trying the next applicable label.
6. If no label matches, handle via `default` if defined. `null` is a special case and must be considered separately (section 6).

Example:

~~~java
static String category(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() >= 5 -> "long";
        case String s -> "short nonblank";
        default -> "different type";
    };
}
~~~

| Selector value | Pattern and guard | Result |
| --- | --- | --- |
| `"  "` | Matches `String`, `isBlank() == true` | `"blank"` |
| `"Hello"` | First guard false, `length() >= 5` guard true | `"long"` |
| `"Go"` | Both guards false, final `String` label matches | `"short nonblank"` |
| `42` | Does not match `String`, `String` guards are not evaluated | `"different type"` |

**Key point:** A guard returning `false` does not mean the entire `switch` fails. It only means that label is **not selected** and the matching process can continue.

### Does a guard throwing an exception "try another label"?

No. If a guard expression **throws an exception**, `switch` processing is interrupted along that exception flow; Java does not treat an exception as a `false` result.

~~~java
static String fragile(Object value) {
    return switch (value) {
        case String s when s.charAt(0) == 'A' -> "starts with A";
        case String s -> "other string";
        default -> "other";
    };
}
~~~

If an empty string `""` is passed, `s.charAt(0)` throws `StringIndexOutOfBoundsException`. It does **not** automatically fall through to the `"other string"` branch. A safer way to write this:

~~~java
case String s when !s.isEmpty() && s.charAt(0) == 'A' -> "starts with A";
~~~

Or more concisely:

~~~java
case String s when s.startsWith("A") -> "starts with A";
~~~

The two lines above are **illustrative labels** and need to be placed inside a valid `switch` with other branches.

## 3. Pattern Variables Are in Scope for the Guard

Variables declared by the pattern are already initialized **before the guard runs**:

~~~java
static String normalize(Object value) {
    return switch (value) {
        case String text when !text.isBlank() -> text.trim().toUpperCase();
        case String text -> "(blank)";
        default -> "(not text)";
    };
}
~~~

In the first branch, the variable `text` has static type `String` in **both the guard and the expression after `->`**. No `(String) value` cast is needed.

Two `String text` declarations in two independent arms can reuse the name `text`, because a pattern variable's scope belongs to its corresponding label/branch. In the `default` branch or outside the `switch`, that `text` variable cannot be used.

The following code **intentionally does not compile** when written inside a method:

~~~java
String result = switch (value) {
    case String text when text.length() > 3 -> text;
    default -> "other";
};
System.out.println(text); // ERROR: text is out of scope.
~~~

If you want to use the processed value after the `switch`, store the **result** in the variable `result`; do not access a pattern variable from an arm that has already ended.

### A guard can have multiple conditions

~~~java
case String text when !text.isBlank() && text.length() <= 20 -> "valid text";
~~~

After `when` is an **ordinary Java boolean expression**. You can use `&&`, `||`, method calls, comparisons, conditions based on outer variables, etc., as long as they are valid in type and scope. `&&` performs short-circuiting like other Java expressions.

In official Java 21, the standard syntax is:

~~~java
case String text when text.length() > 3 -> "long";
~~~

Do not copy guard syntax from some older preview versions that wrote conditions directly after the pattern using `&&` instead of `when`. However, `&&` **inside** a `when` expression is still completely valid.

## 4. Guards Help Split One Type into Specific Cases

Without guards, the same type is often handled using `if/else` inside a branch:

~~~java
static String before(Object input) {
    return switch (input) {
        case String s -> {
            if (s.isBlank()) {
                yield "blank text";
            }
            yield "text: " + s.trim();
        }
        default -> "different type";
    };
}
~~~

With guards, each business condition can be turned into a clear label:

~~~java
static String after(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> "blank text";
        case String s -> "text: " + s.trim();
        default -> "different type";
    };
}
~~~

Both methods are **illustrative code inside a Java 21+ class**, and both return the same result for non-null `input` values across the stated branches.

**Why is the latter approach useful?**

- Looking at the label immediately tells you the condition required to enter the branch; no need to read `if` logic inside the body.
- Each branch body focuses on handling a successful match.
- Multiple guards for the same type can be placed in priority order: special cases first, general case later.

**Not every `if` needs to be converted into a guard.** If the condition is long, has multiple steps, or has side effects, consider a clearly named boolean helper (and avoid side effects) or keep the logic inside the branch for readability.

## 5. `case` Ordering, Dominance, and Constant Guards

In a pattern switch, the compiler checks the **dominance** rule: you cannot place a label that is already completely covered by an earlier label, leaving the later label with no chance of being selected.

### 5.1. Unguarded branch before guarded branch: error

~~~java
static String badOrder(Object value) {
    return switch (value) {
        case String s -> "any string";
        case String s when s.isBlank() -> "blank"; // ERROR: dominated by the branch above.
        default -> "other";
    };
}
~~~

Every `String` already matches the earlier `case String s`. The later `String s when ...` branch is unreachable, so the compiler rejects it.

**Correct ordering:**

~~~java
static String goodOrder(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "any other string";
        default -> "other";
    };
}
~~~

Similarly, if an unguarded `case CharSequence cs` appears before `case String s when ...`, the later branch is also dominated because every `String` is a `CharSequence`.

### 5.2. General guards are not used to prove dominance in general

~~~java
static String withGuards(Object value) {
    return switch (value) {
        case String s when s.length() > 5 -> "long";
        case String s when s.startsWith("A") -> "starts with A";
        case String s -> "other string";
        default -> "other";
    };
}
~~~

This snippet is **valid**, even though the first two guards can both be true for the same value. **The first matching label is selected**. For example, `"ABCDEF"` satisfies both guards, but the `"long"` branch runs first.

The compiler does not attempt to solve arbitrary logical relationships between guards. Therefore, **guard order determines business priority**; two conditions can overlap without necessarily causing a dominance error.

### 5.3. Exception: `when true` and `when false`

The following code **intentionally does not compile**:

~~~java
static String redundant(Object value) {
    return switch (value) {
        case String s when true -> "any string";
        case String s -> "never reached"; // ERROR: dominated.
        default -> "other";
    };
}
~~~

A guard that is the constant expression `true` does not narrow the pattern's value set; it can dominate a subsequent label of the same type.

The following code also **intentionally does not compile**, because the guard is the constant expression `false`:

~~~java
static String unreachable(Object value) {
    return switch (value) {
        case String s when false -> "never"; // ERROR: constant false guard.
        case String s -> "string";
        default -> "other";
    };
}
~~~

Do not use `when true`/`when false` as a way to toggle branches on or off; fix the `case` design or configure a proper runtime condition.

### 5.4. Interaction with constant labels

For a `switch` on `Integer`, a guarded pattern branch such as `case Integer n when n > 0` can match the value `1` before reaching the constant label `case 1` if written in that order. The compiler generally **does not treat an arbitrary guard as evidence of dominance** over a constant label, even though at runtime the guard may intercept the value first.

To prioritize a special value, place **constant labels before guards**, followed by the general pattern:

~~~java
static String classifyInteger(Integer value) {
    return switch (value) {
        case null -> "null";
        case 1 -> "exactly one";
        case Integer n when n > 0 -> "positive";
        case Integer n -> "zero or negative";
    };
}
~~~

This is a Java 21+ **illustrative method**. `classifyInteger(1)` returns `"exactly one"`; `classifyInteger(3)` returns `"positive"`; `classifyInteger(-1)` returns `"zero or negative"`. This ordering makes priority predictable.

## 6. Exhaustiveness and `null` Handling

A **switch expression** and an **enhanced switch statement** containing patterns/`null` must have enough labels to cover the cases the selector can belong to according to its static type.

The following example **intentionally does not compile**:

~~~java
static String incomplete(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long text";
        // ERROR: there are still short Strings and countless non-String Objects.
    };
}
~~~

A guarded pattern only covers **values that match the pattern and simultaneously satisfy the guard**. The compiler does not treat an arbitrary runtime guard as representing all values of the selector type.

**Fix with appropriate fallbacks:**

~~~java
static String complete(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long text";
        case String s -> "short text";
        default -> "other";
    };
}
~~~

The unguarded `case String s` catches the remaining strings; `default` covers non-null objects of other types. This makes the `switch` expression exhaustive for non-null objects that may appear.

### `null` does not match an ordinary type pattern

~~~java
static String classifyNullable(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when s.isEmpty() -> "empty";
        case String s -> "text";
        default -> "other";
    };
}
~~~

`case null` is a separate label, **not a guarded pattern label**. Without `case null`, an ordinary pattern switch receiving a `null` selector will throw `NullPointerException` before `default` receives the value. `default` does not automatically handle null.

You can use `case null, default -> ...` if business requirements want to combine the two cases. However, writing a separate `case null -> ...` is usually clearer when distinguishing missing data from wrong-type values.

**Remember:** Exhaustiveness for non-null reference types and `null` handling are two separate concerns. A switch expression considered exhaustive by the compiler can still throw `NullPointerException` if the selector value is null and you have not declared a handling branch.

## 7. Designing Safe and Maintainable Guards

### 7.1. Prefer short, side-effect-free expressions

A guard is evaluated during **branch selection**. Avoid putting state updates, I/O, collection mutations, or complex operations in `when`. Side effects make code unpredictable when a guard is false and matching moves on to the next label.

~~~java
case String s when s.startsWith("ID-") -> "identifier";
~~~

This is easier to understand than a guard that invokes multiple operations and mutates shared state.

### 7.2. Guards must not throw unexpected exceptions

Check string or data bounds before accessing elements:

~~~java
case String s when s.length() >= 2 && s.charAt(1) == ':' -> "prefixed";
~~~

Thanks to short-circuiting `&&`, `charAt(1)` does not run on strings shorter than 2. If you use a helper in `when`, clearly document whether the helper accepts all objects of the pattern type.

### 7.3. Avoid hard-to-read overlapping conditions

~~~java
case Integer n when n > 0 && n % 2 == 0 -> "positive even";
case Integer n when n > 0 -> "positive odd";
case Integer n -> "nonpositive";
~~~

The first branch is for positive even numbers, the second leaves positive odd numbers, and the final one catches nonpositive numbers. Even though both the first and second guards are true for positive even numbers as standalone expressions, **branch order** produces a consistent result.

### 7.4. One selector, multiple guards

The expression in `switch (expression)` is evaluated **once** to obtain the value to match. However, multiple guards may be evaluated in sequence if their corresponding patterns match while earlier guards are `false`. Therefore, do not confuse "selector evaluated once" with "only one guard condition is tested".

To demonstrate, the program in section 8 counts how many times the selector and guard are evaluated: with input `"ab"`, the selector is called exactly once and the guard is called exactly once; when the guard is false, the unguarded `String` branch takes the value.

### 7.5. Should you use `when` or `if` inside the arm?

Use `when` when the condition is short and **decides which branch should be selected**. Keep `if` inside the arm when, after selecting the input type, you need multiple state-dependent steps or want to avoid creating too many branches with overlapping conditions. There is no rule forcing every boolean check into `when`.

## 8. Complete Java 21 Program

Save all the following code as **`GuardedLabelDemo.java`**:

~~~java
public class GuardedLabelDemo {
    private static int selectorCalls = 0;
    private static int guardCalls = 0;

    static String classify(Object value) {
        return switch (value) {
            case null -> "null";

            case String s when s.isBlank() -> "blank text";
            case String s when s.length() >= 5 ->
                    "long text: " + s.toUpperCase();
            case String s -> "short text: " + s;

            case Integer n when n > 0 && n % 2 == 0 ->
                    "positive even: " + n;
            case Integer n when n > 0 -> "positive odd: " + n;
            case Integer n -> "nonpositive: " + n;

            default -> "other";
        };
    }

    static Object nextValue() {
        selectorCalls++;
        return "ab";
    }

    static boolean longerThanThree(String text) {
        guardCalls++;
        return text.length() > 3;
    }

    static String probe() {
        return switch (nextValue()) {
            case Integer i -> "integer";
            case String s when longerThanThree(s) -> "long";
            case String s -> "short";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("   "));
        System.out.println(classify("Hello"));
        System.out.println(classify("Go"));
        System.out.println(classify(8));
        System.out.println(classify(7));
        System.out.println(classify(0));
        System.out.println(classify(-2));
        System.out.println(classify(3.14));
        System.out.println(classify(null));

        String result = probe();
        System.out.println(
                "probe=" + result
                + ", selector=" + selectorCalls
                + ", guard=" + guardCalls
        );
    }
}
~~~

Compile/run on **JDK 21 or later**, verifying Java 21 source syntax:

~~~bash
javac --release 21 GuardedLabelDemo.java
java GuardedLabelDemo
~~~

**Exact stdout:**

~~~text
blank text
long text: HELLO
short text: Go
positive even: 8
positive odd: 7
nonpositive: 0
nonpositive: -2
other
null
probe=short, selector=1, guard=1
~~~

**Output explanation:**

1. `"   "`: first `String` label matches, `isBlank()` is true → `blank text`.
2. `"Hello"`: `isBlank()` guard is false, `length() >= 5` guard is true → `long text: HELLO`.
3. `"Go"`: both `String` guards are false → unguarded `case String s` label → `short text: Go`.
4. `8`: `Integer` value, positive and even → `positive even: 8`.
5. `7`: positive-even guard is false; positive guard is true → `positive odd: 7`.
6. `0` and `-2`: do not pass the `n > 0` guard, but match the final `Integer` → `nonpositive`.
7. `3.14`: runtime type `Double`, matches neither `String` nor `Integer` → `default` → `other`.
8. `null`: handled directly by the `case null` label.
9. `probe()`: `nextValue()` produces `"ab"` and increments `selectorCalls` once; the `Integer` pattern is skipped; the guard `longerThanThree(s)` is called once and returns `false`; the next `String` branch returns `short`. No casts, no re-evaluation of the selector.

This program uses standard Java 21 syntax; `--enable-preview` is not needed.

## 9. Common Mistakes: Symptoms and Fixes

| Mistake | Cause | Fix |
| --- | --- | --- |
| `case String s ->` placed before `case String s when condition ->` | Unguarded branch covers all `String`s; later branch is dominated | Place the guarded branch first |
| `case CharSequence cs ->` before `case String s when ... ->` | More general type dominates subtype | Place the more specific pattern first |
| `case String s when s.length() ->` | `length()` is `int`, not boolean | `when s.length() > 0` |
| `case String s when false ->` | Guard is constant expression `false`; compiler rejects it | Remove the dead branch or use a meaningful runtime condition |
| `case String s when true ->` then `case String s ->` | Constant `true` guard filters nothing; later branch is dominated | Remove the guard / merge branches |
| Only guarded cases for an `Object` selector | Does not cover all inputs | Add an unguarded pattern or appropriate `default` |
| Using variable `s` after the `switch` ends | Pattern variable is out of scope | Use the `switch` result variable |
| Guard calls `charAt(0)` on an empty string | Guard throws an exception, does not fall back | Check `isEmpty()` or use `startsWith` |
| Expecting `default` to catch `null` | `null` is handled separately in Java 21 pattern switch | Add `case null` |
| Copying preview syntax `case String s && ...` | Syntax from an older preview | Java 21 uses `case String s when ...` |
| Putting side effects in `when` | Condition may evaluate and then fail, making side effects hard to track | Use a clear predicate with minimal/no side effects |

### Two separate ERROR examples

**Wrong guard type** (compilation error):

~~~java
static String badGuardType(Object value) {
    return switch (value) {
        case String s when s.length() -> "text"; // ERROR: int is not boolean.
        default -> "other";
    };
}
~~~

**Missing coverage branch** (compilation error):

~~~java
static String missingFallback(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long";
        // ERROR: short Strings and other Objects still have no case.
    };
}
~~~

These methods are illustrative examples and **must not be pasted into** the complete demo class if you want to keep the program runnable. Having `default` so the compiler accepts the switch does not guarantee the program handles `null` per business requirements; `case null` is still needed when null may be received.

## 10. Checklist for Reading/Writing a Guarded Pattern Label

When encountering `case T t when condition -> branch`, ask yourself:

1. **What is the static type of the selector?** Can it receive a value compatible with `T`?
2. **Where is the pattern bound?** `t` has type `T` and exists only in the scope of the guard and the matching branch.
3. **Is the guard safe for every value matching `T`?** Does it check bounds before index access, division, or dereferencing nullable data?
4. **Does any earlier label cover this pattern?** If an unguarded label of the same type or a supertype appears earlier, the compiler may report dominance.
5. **If the guard returns `false`, which label receives the value?** There should be a broader same-type branch or `default`.
6. **If the guard returns `true`, is there a higher-priority constant/guarded branch placed earlier?** Label order affects behavior.
7. **What if the selector is null?** Add `case null` when needed.
8. **Is the switch exhaustive?** The compiler must be able to verify that every valid input type has a handling path.

**Real-world example:** a parameter `Object payload` can receive a string, an integer, or another type. If the requirement is "prioritize blank strings, then long strings, then remaining strings; for integers, prioritize positive even, then positive odd, then the rest", the corresponding `case ... when ...` labels are clearer than a deeply nested block of `if` statements.

## 11. Practice Questions

**Question 1.** In `case String name when name.startsWith("A") -> ...`, which conditions must be true for the branch to run? When does `name` exist and what is its type?

**Question 2.** For `switch (Object value)` with three labels in order:

~~~java
case String s when s.length() > 4 -> "long";
case String s when s.startsWith("A") -> "starts A";
case String s -> "other string";
~~~

Which branch does `"ABCDEF"` enter? What about `"Ax"` and `"xy"`?

**Question 3.** Why does the compiler reject:

~~~java
case String s -> "all";
case String s when s.isBlank() -> "blank";
~~~

**Question 4.** Why is `case String s when s.length() -> ...` wrong? Rewrite a guard that checks for a non-empty string.

**Question 5.** A guard throws an exception when accessing `s.charAt(0)` on an empty string. Does Java fall through to `case String s` below it? How can this error be avoided?

**Question 6.** A `switch` expression on `Object` only has `case Integer n when n > 0`. Why does it not compile? What kinds of labels need to be added?

**Question 7.** `default` is already present. What normally happens in Java 21 when passing `null` into a pattern `switch` without `case null`?

**Question 8.** Does placing `case Integer i when i > 0` before `case 1` necessarily cause the compiler to report dominance? In terms of organizing priority, which label should be placed first?

**Question 9.** Why can a constant `false` guard be rejected at compile time, while a guard depending on a runtime parameter can evaluate to `false` and still be valid?

**Question 10.** In the `probe()` example in section 8, why are `selectorCalls == 1` and `guardCalls == 1` even though there are multiple `case` labels?

### Suggested Answers

1. The selector must match `String` and `name.startsWith("A")` must be `true`. `name` has type `String`, is bound after the pattern matches, and is in scope in the guard and its corresponding arm.
2. `"ABCDEF"` enters `"long"` (the first branch, even though it also starts with A); `"Ax"` enters `"starts A"`; `"xy"` enters `"other string"`.
3. The unguarded branch already catches every `String`, so the guarded case below it is **dominated**.
4. `s.length()` is `int`; write `when !s.isEmpty()` or `when s.length() > 0`.
5. No. The exception from the guard is thrown; fix it with `!s.isEmpty() && s.charAt(0) == 'A'` or `s.startsWith("A")`.
6. Not **exhaustive**: nonpositive numbers, strings, and other types remain. Add an unguarded `Integer` branch if needed, and `default` or a general pattern to cover all remaining types.
7. Normally throws `NullPointerException`; `default` does not replace `case null`.
8. Not necessarily: general guards are hard to analyze statically, but at runtime `1` may be intercepted by the earlier guarded case. Usually place `case 1` first, then the guarded pattern, then the unguarded pattern.
9. Constant `false` is a dead branch known at compile time; a runtime guard depends on input values and may be true in other executions.
10. The selector expression `nextValue()` is evaluated only once. The guard is called once because the `String` pattern matches, while the `Integer` label does not match and therefore triggers no guard.

## Official References

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), especially *When Clauses*, *Pattern Label Dominance*, *Type Coverage*, and *Scope of Pattern Variable Declarations*.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): final design and `when` syntax standardized in JDK 21.
- [Java Language Specification 21 — `14.11 The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): `case` syntax, guards, dominance, and coverage requirements.
- [Java Language Specification 21 — `15.28 switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): switch expression semantics and exhaustiveness.
- [Java Language Specification 21 — `6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): scope of pattern variables in guards and branches.
