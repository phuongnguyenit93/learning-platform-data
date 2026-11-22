# Compiler Error Due to Dominated `case` in Java

> **Module:** Java Core Pattern Matching → Dominance. This lesson is based on **Java 21**, the first version in which pattern matching for `switch` became a standard feature (JEP 441). Snippets marked **ERROR** are intentionally written to be rejected by the compiler; only the snippet with a filename and `javac` command in section 9 is a standalone runnable program.

## Objectives

You will understand the cause of the **`this case label is dominated by a preceding case label`** error, know how to identify which branch shadows which, properly order patterns, constants, and `when` clauses, and distinguish dominance from duplicate label errors, invalid guards, or non-exhaustive `switch` statements/expressions. After this lesson, you will be able to analyze the error directly from **static types and `case` label order**, without having to guess by testing input values.

## 1. What does the “dominated case” error mean?

With pattern matching for `switch` in Java 21, a selector value can be compatible with **multiple `case` labels**. Java selects the **first applicable label** in declaration order. The compiler forbids labels when it can determine that **every value that label could receive will already be matched by a preceding label**.

That is a **dominated** label (completely covered/shadowed by a preceding label). The compiler typically reports:

~~~text
error: this case label is dominated by a preceding case label
~~~

Example that **intentionally does not compile**:

~~~java
static String broken(Object input) {
    return switch (input) {
        case CharSequence sequence -> "a character sequence";
        case String text -> "a string"; // ERROR: dominated.
        default -> "other";
    };
}
~~~

**Why?**

- A `String` object always implements `CharSequence`.
- The preceding `case CharSequence sequence` label matches every non-null `String` object.
- Therefore, the subsequent `case String text` will have no values left to handle.
- The compiler detects this subtype relationship at compile time, regardless of whether you intend to run the program with a `String`.

**Fix: place the specific pattern first, and the broader pattern after.**

~~~java
static String corrected(Object input) {
    return switch (input) {
        case String text -> "a string: " + text;
        case CharSequence sequence -> "a character sequence";
        default -> "other";
    };
}
~~~

Now `String` is matched first; `StringBuilder` and other `CharSequence` implementations can fall into the second branch.

> **Rule of thumb:** If label A can match **all** values that label B matches, and A precedes B, then B is at risk of being **dominated**. The compiler applies the specific dominance rules of the JLS rather than attempting to deduce all arbitrary logical propositions.

## 2. Distinguishing compile-time dominance from runtime label selection

Do not confuse two concepts:

- **Dominance:** the compiler determines that a label is completely shadowed by a preceding label according to static rules; this is a **compile-time** error and the code does not run.
- **First applicable label:** if multiple valid labels could handle the same value, the runtime selects the **first** applicable label.

Valid example:

~~~java
static String kind(Object value) {
    return switch (value) {
        case String s -> "string";
        case Integer i -> "integer";
        default -> "other";
    };
}
~~~

`String` and `Integer` are two classes with no subtype relationship between them, so neither label covers the entire set of objects matched by the other. `default` handles other types.

However, the following example **fails**:

~~~java
static String brokenNumber(Object value) {
    return switch (value) {
        case Number n -> "number";
        case Integer i -> "integer"; // ERROR: Integer is a Number.
        default -> "other";
    };
}
~~~

Every `Integer` is a `Number`. Simply swap them:

~~~java
static String fixedNumber(Object value) {
    return switch (value) {
        case Integer i -> "integer";
        case Number n -> "number";
        default -> "other";
    };
}
~~~

**Typical order:** `Integer` → `Number` → `Object`/`default`, or `String` → `CharSequence` → `Object`/`default`.

## 3. Static type of the selector and type relationships are the starting point

In:

~~~java
Object input = "Java";
String result = switch (input) {
    case String text -> text.toUpperCase();
    case CharSequence sequence -> "Other sequence";
    default -> "Other";
};
~~~

- `input` is the **selector**, with **static type `Object`**.
- The `case` labels contain **type patterns**; at runtime `input` may be determined to be a `String`, `StringBuilder`, or another type.
- The variable `text` has static type `String` in the selected arm; `sequence` has static type `CharSequence` in its own arm.
- Dominance checking is based on **type relationships and label rules** at compile time, not on the fact that `input` happens to hold the string `"Java"` today.

If the selector has static type `Integer`, a `case String s` label will instead be rejected because the **pattern is not applicable to the selector type**, which is a **type compatibility error**, not dominance:

~~~java
static String invalidSelector(Integer value) {
    return switch (value) {
        case String s -> "text"; // ERROR: String pattern is incompatible.
        default -> "other";
    };
}
~~~

A compiler diagnostic should only be called dominance when a branch **is applicable** but is covered by a preceding branch under the JLS rules. This is an important distinction when finding the root cause.

## 4. Same-type cases: how does a `when` guard affect dominance?

A **guarded pattern label** has the form:

~~~text
case Type variable when booleanCondition -> result
~~~

The pattern must match first, and then the `when` condition is evaluated. **A guard can narrow** the set of values that the branch actually accepts.

### 4.1. Unguarded branch first: the guarded branch is dominated

~~~java
static String wrongGuardOrder(Object value) {
    return switch (value) {
        case String s -> "any string";
        case String s when s.isBlank() -> "blank"; // ERROR: dominated.
        default -> "other";
    };
}
~~~

The first `case String s` label already matches **every string**. The subsequent label has no chance, even though the `s.isBlank()` condition is true for some strings.

**Fix: specific guard first, general same-type branch after.**

~~~java
static String rightGuardOrder(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "nonblank";
        default -> "other";
    };
}
~~~

- For `"  "`, the `isBlank()` guard is true → `"blank"`.
- For `"Java"`, the guard is false, but the `String` pattern still matches at the next label → `"nonblank"`.
- For `42`, the `String` pattern does not match; the `String` guard is not evaluated → `"other"`.

### 4.2. Non-constant guards usually do **not** cause the compiler to infer dominance

~~~java
static String overlappingGuards(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long";
        case String s when s.startsWith("A") -> "starts A";
        case String s -> "other string";
        default -> "other";
    };
}
~~~

This code is **valid**. `"ABCD"` satisfies both of the first two conditions but enters the `"long"` branch because it is checked first. The compiler does not prove all logical relationships between two arbitrary guard expressions.

In other words, **not getting a dominance error does not mean a branch is guaranteed to execute for some data**. You still need to consider business priority and testing.

### 4.3. `when true` is treated as an unguarded branch for dominance

~~~java
static String badTrueGuard(Object value) {
    return switch (value) {
        case String s when true -> "all strings";
        case String s -> "another string"; // ERROR: dominated.
        default -> "other";
    };
}
~~~

The guard is a **constant expression `true`**, which does not narrow the pattern. Java 21 treats it as equivalent to an **unguarded** label when checking dominance.

### 4.4. `when false` causes an error, but not a dominance error

~~~java
static String badFalseGuard(Object value) {
    return switch (value) {
        case String s when false -> "never"; // ERROR: constant false guard.
        default -> "other";
    };
}
~~~

The JLS forbids a guard that is a **constant expression `false`**. The compiler may report:

~~~text
this case label has a guard that is a constant expression with value 'false'
~~~

This is a **guard validity error**, and should not be mislabeled as dominance.

**Suggested fix:** Remove the unreachable case, or replace it with a runtime predicate that actually has business meaning. Do not add `when true`/`when false` just to “toggle” logic on or off.

## 5. A type pattern can also dominate a constant label

Dominance does not only occur between two type patterns.

### 5.1. `case Integer i` shadows `case 1`

The following code **intentionally does not compile**:

~~~java
static String badConstant(Integer value) {
    return switch (value) {
        case Integer i -> "an integer";
        case 1 -> "one"; // ERROR: case 1 dominated.
    };
}
~~~

Because the selector has reference type `Integer`, `case Integer i` covers every non-null `Integer` value, including `1`.

**Proper ordering:**

~~~java
static String goodConstant(Integer value) {
    return switch (value) {
        case 1 -> "exactly one";
        case Integer i -> "some other integer";
    };
}
~~~

`case 1` takes precedence first, followed by the general pattern. `case Integer i` also helps cover the remaining `Integer` values so that the switch expression is exhaustive.

Note: `null` is still a separate case; if `null` is passed and there is no `case null`, Java 21's pattern switch will throw a `NullPointerException`.

### 5.2. An enum's type pattern can shadow an enum constant

~~~java
enum Color { RED, GREEN, BLUE }

static String badEnum(Color color) {
    return switch (color) {
        case Color c -> "some color";
        case RED -> "red"; // ERROR: RED dominated.
    };
}
~~~

`case Color c` is a **type pattern**; every non-null `Color` constant matches this pattern. Therefore, the subsequent `case RED` label cannot apply.

**Fix:**

~~~java
static String goodEnum(Color color) {
    return switch (color) {
        case RED -> "red";
        case Color c -> "other color";
    };
}
~~~

Distinction:

- `case RED`: **enum constant label**, does not declare a pattern variable.
- `case Color c`: **type pattern**, binds `c` as `Color` when matched.

### 5.3. A guarded pattern usually does not dominate a subsequent constant label

This is **valid** code in Java 21:

~~~java
static String legalButSurprising(Integer value) {
    return switch (value) {
        case Integer i when i > 0 -> "positive";
        case 1 -> "one";
        case Integer i -> "nonpositive";
    };
}
~~~

`legalButSurprising(1)` returns `"positive"`, not `"one"`, because the first branch's guard is true. The compiler does **not** use the arbitrary guard `i > 0` to conclude that the constant label `1` is dominated.

**Ordering advice:** Place **specific constant labels → guarded patterns → unguarded patterns**. That way, the special value `1` is not captured by the “positive” branch at runtime.

~~~java
static String preferred(Integer value) {
    return switch (value) {
        case 1 -> "one";
        case Integer i when i > 0 -> "positive";
        case Integer i -> "nonpositive";
    };
}
~~~

This rule has exceptions depending on business requirements, but it is an easy-to-understand and least-surprising default.

## 6. Overly general labels: `Object`, `default`, and `null`

### 6.1. Placing an `Object` pattern first shadows subsequent type patterns

~~~java
static String badObject(Object value) {
    return switch (value) {
        case Object any -> "object";
        case String text -> "string"; // ERROR: dominated.
    };
}
~~~

With a selector of type `Object`, `case Object any` covers all **non-null** objects, including `String`. Place specific type patterns first:

~~~java
static String goodObject(Object value) {
    return switch (value) {
        case String text -> "string";
        case Object any -> "other object";
    };
}
~~~

This is an exhaustive switch expression for non-null objects with a selector of type `Object`. However, it **does not automatically match `null`**; to handle `null` instead of letting the switch throw a `NullPointerException`, add `case null -> ...`.

### 6.2. `null` is not an object that matches a type pattern

~~~java
static String safeObject(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "string";
        case Object any -> "other object";
    };
}
~~~

`case null` is a **special label**, not an `Object` type pattern. Therefore, `case Object any` does not dominate `case null`.

Do not assume that a general type pattern will handle all values including null. In Java 21, if the selector is `null` and there is no `case null` label, the switch may throw a `NullPointerException`.

### 6.3. `default` does not replace dominance reasoning

`default` is used to handle values that do not match other labels according to switch rules. With the code:

~~~java
static String categorize(Object value) {
    return switch (value) {
        case String text -> "text";
        case Number number -> "number";
        default -> "other";
    };
}
~~~

Placing `String` and `Number` before `default` is readable. `default` has no pattern variable and does not narrow to a specific type; it simply provides a fallback branch.

However, you cannot use `default` to “rescue” a previously dominated label: if `case CharSequence` precedes `case String`, adding `default` at the end still leaves the error intact.

**Do not conflate them:** Dominance, type coverage/exhaustiveness, `default`, and null handling are related but **distinct** checks.

## 7. Errors that look like dominance but are fundamentally different

| Error | Example | Nature | How to fix |
| --- | --- | --- | --- |
| **Dominated case** | `case CharSequence c` before `case String s` | Every string is already captured by the preceding branch | Move `String` earlier |
| **Dominated constant** | `case Integer i` before `case 1` | The pattern also matches the constant value | Move the specific constant earlier |
| **Duplicate constant** | Two `case 1` labels | Two constants with the same value | Merge/remove one label |
| **Guard constant false** | `case String s when false` | Guard is false at compile time | Remove the dead branch |
| **Incompatible pattern** | Selector `Integer`, `case String s` | Type is not applicable to the selector | Fix the selector/pattern type |
| **Non-exhaustive switch** | Selector `Object`, only `case String s` | Missing handling for other values | Add `default` or a general pattern |
| **Local variable name clash** | `String s` in outer scope, `case String s` in overlapping scope | Name declaration rules | Rename the binding |
| **Unsafe fall-through** | Colon-style `switch` falling into a branch with an uninitialized pattern binding | Control-flow rules | Use `->` or terminate the branch properly |

**Duplicate constant example (intentionally does not compile):**

~~~java
static String duplicate(Integer n) {
    return switch (n) {
        case 1 -> "first";
        case 1 -> "second"; // ERROR: duplicate case label.
        default -> "other";
    };
}
~~~

This error is different from a dominated pattern: you declared **the same constant value twice**.

**Non-exhaustive example (intentionally does not compile):**

~~~java
static String missing(Object input) {
    return switch (input) {
        case String text -> text;
        // ERROR: Object has many other types besides String.
    };
}
~~~

This is not dominance because there is only one label. The compiler requires a switch expression to cover the selector type. Add `default` or an appropriate general pattern.

## 8. How to resolve a compiler dominated case error

A short, reliable workflow:

1. **Read the flagged label.** For example, `case String text` or `case 1`.
2. **Look up at the preceding labels.** Look for a supertype/interface (`Object`, `CharSequence`, `Number`), an unguarded pattern of the same type, or a pattern that also matches the failing constant label.
3. **Check the value-set relationship.** Is every `String` a `CharSequence`? Is every boxed `1` an `Integer`? If so, the preceding label may completely shadow the subsequent one.
4. **Check `when`.** If the preceding label is unguarded or has `when true`, it does not filter values by a guard. If it has a runtime-dependent guard, the compiler usually does not use it to conclude dominance; you should still review the order to avoid surprising logic.
5. **Reorder by specificity.** Prioritize constant labels, then specific patterns / specialized guards, and finally broader patterns, unguarded patterns, or `default`.
6. **Do not fix by mechanically casting or renaming the pattern variable.** Casting does not eliminate the subtype relationship that makes the subsequent label inapplicable.
7. **Check exhaustiveness after fixing.** Reordering may be valid, but removing a broad branch or `default` could leave the switch unable to cover the entire selector domain.
8. **Recompile with the right Java version.** The `case T x when ...` examples use Java 21. In Java 17, pattern switch is not yet a standard feature; do not attribute every preview/version error to dominance.
9. **Test multiple runtime cases.** Verify values matching specific branches, other subtypes, values making guards true/false, `null`, and the fallback.

### Quick diagnostic checklist

| Question | If “yes” |
| --- | --- |
| Is there a `case Object any` earlier? | Subsequent type patterns matching non-null objects are very likely shadowed |
| Is there a `case CharSequence` before `case String`? | `String` is dominated |
| Is there a `case Number` before `case Integer`? | `Integer` is dominated |
| Is there an unguarded `case String` before a guarded `case String when ...`? | The guarded case is dominated |
| Is there a `when true` on an earlier branch of the same type? | The subsequent label may be dominated |
| Is there an unguarded `case Integer` before the constant `case 1`? | The constant label `1` is dominated |
| Are there two `case 1` labels? | That is a duplicate constant, not a dominance error |
| Is there a `when false`? | Invalid constant `false` guard, which is a separate error |

## 9. Complete, runnable Java 21 program

Save the file as **`DominanceLessonDemo.java`**:

~~~java
public class DominanceLessonDemo {

    enum Color {
        RED, GREEN, BLUE
    }

    // Labels are ordered from specific cases to broader ones.
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank";
            case String s -> "text=" + s.trim();
            case Integer n when n == 0 -> "zero";
            case Integer n -> "integer=" + n;
            case Number n -> "number=" + n;
            case CharSequence cs -> "chars=" + cs.length();
            default -> "other";
        };
    }

    // Place the specific constant before the general pattern.
    static String rank(Integer n) {
        return switch (n) {
            case null -> "no number";
            case 1 -> "one";
            case Integer value when value > 0 -> "positive";
            case Integer value -> "nonpositive";
        };
    }

    // Place the enum constant before the type pattern that matches all Color values.
    static String color(Color c) {
        return switch (c) {
            case RED -> "red";
            case Color any -> "other color";
        };
    }

    public static void main(String[] args) {
        Object[] values = {
                "  ",
                " Java ",
                0,
                7,
                2.5,
                new StringBuilder("ok"),
                new Object(),
                null
        };

        for (Object value : values) {
            System.out.println(classify(value));
        }

        System.out.println(
                "rank=" + rank(1) + "," + rank(3) + "," + rank(-1)
        );
        System.out.println("color=" + color(Color.BLUE));
    }
}
~~~

**Compile and run** with JDK 21 or later:

~~~bash
javac --release 21 DominanceLessonDemo.java
java DominanceLessonDemo
~~~

**Exact stdout:**

~~~text
blank
text=Java
zero
integer=7
number=2.5
chars=2
other
null
rank=one,positive,nonpositive
color=other color
~~~

**Branch-by-branch explanation:**

1. `"  "` matches `String` and `isBlank()` is true → `blank`.
2. `" Java "` matches `String` but the guard is false → `text=Java` after `trim()`.
3. `0` is autoboxed to `Integer` when placed in the `Object[]` array. The guard `n == 0` is true → `zero`.
4. `7` matches `Integer` but the equal-to-0 guard is false → `integer=7`; it is not captured by the subsequent `Number` branch.
5. `2.5` is a `Double`, which is also a `Number` → `number=2.5`.
6. `StringBuilder("ok")` is not a `String`, but it is a `CharSequence` → `chars=2`.
7. `new Object()` only matches `default` → `other`.
8. `null` matches the dedicated `case null` label → `null`.
9. `rank(1)` enters the constant label `case 1`, `rank(3)` passes the `value > 0` guard, and `rank(-1)` enters the unguarded `Integer` branch.
10. `Color.BLUE` is not `RED`, so it enters the `case Color any` type pattern → `other color`.

**Verification point:** If you move `case CharSequence cs` before `case String s`, or `case Integer n` before the constant `case 1`, Java 21 will no longer compile — this is the exact dominance error analyzed in this lesson.

## 10. Self-check exercises

**Question 1.** Does the following snippet compile? If not, which label is dominated?

~~~java
return switch (value) {
    case Number n -> "number";
    case Double d -> "double";
    default -> "other";
};
~~~

**Question 2.** Why is `case String s` placed after `case CharSequence cs` an error? What is the minimal change to fix it?

**Question 3.** Is this snippet valid? With `value == "ABCD"`, which branch is selected?

~~~java
return switch (value) {
    case String s when s.length() > 3 -> "long";
    case String s when s.startsWith("A") -> "starts A";
    case String s -> "string";
    default -> "other";
};
~~~

**Question 4.** Does `case String s when true` before `case String t` cause a dominance error in Java 21? Explain.

**Question 5.** Why does `case String s when false` produce a compile error, yet it is not a typical “dominated” message?

**Question 6.** With a selector of type `Integer`, why is placing `case Integer i` before `case 1` an error? Fix it with the appropriate order.

**Question 7.** Given the code:

~~~java
return switch (n) {
    case Integer i when i > 0 -> "positive";
    case 1 -> "one";
    case Integer i -> "other";
};
~~~

Does it compile? What does it return for `n == 1`? How would you prioritize returning `"one"`?

**Question 8.** Given an enum `Color { RED, GREEN, BLUE }`, why can `case Color c` dominate `case RED` when placed before it?

**Question 9.** Does `case Object o` handle a `null` selector? If you want to print `"missing"` for null, which label should you add?

**Question 10.** What error do two identical `case 1` labels produce? Is it a “dominated pattern” error in the usual sense?

**Question 11.** A switch expression on `Object` has only `case String s -> ...`. Does the compiler reject it as dominated or non-exhaustive?

**Question 12.** Distinguish between the compiler rejecting `case String s` because the selector is `Integer` versus rejecting `case String s` because `case CharSequence cs` precedes it.

### Suggested answers

1. **No.** `case Double d` is dominated because every `Double` is a `Number`. Place `Double` before `Number`.
2. `String implements CharSequence`, so the general branch catches all strings. Place `String` first.
3. **Valid.** `"ABCD"` returns `"long"` because the first branch's guard is true and it precedes the `startsWith("A")` guard.
4. **Yes.** A constant `true` guard is treated as unguarded; it already matches every `String` before the next branch.
5. The JLS forbids a constant `false` guard, so the error is an invalid guard; no preceding label is needed to trigger the error.
6. `case Integer i` matches every non-null `Integer`, including `1`. Place `case 1` first, then `case Integer i`.
7. **Valid.** It returns `"positive"` when `n == 1` because the first branch's guard is true. To return `"one"`, place `case 1` before the guarded pattern.
8. `case Color c` matches every non-null `Color` constant, including `RED`. Place `case RED` first.
9. **No.** A type pattern does not match null. Add `case null -> "missing"` if you want to handle it explicitly.
10. **Duplicate case label**, because the same constant value appears twice; do not confuse it with a subtype dominance error.
11. **Non-exhaustive**, because `Object` has many types besides `String`. Add `default` or a pattern covering the remaining cases.
12. The `Integer` selector case is a **pattern incompatible with the selector type**; the `CharSequence` before `String` case is a **dominated case** due to label ordering.

## Official references

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): sections on *Pattern Label Dominance*, *When Clauses*, *Null case Labels*, and pattern variable scope.
- [Java Language Specification 21 — `14.11.1 The switch Block](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-14.html#jls-14.11.1): rules for switch compatibility, guards, dominance, and duplicate labels.
- [Java Language Specification 21 — `14.11.1.2 Determining which Switch Label Applies at Run Time](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): runtime label selection rules.
- [Java Language Specification 21 — `15.28 Switch Expressions](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-15.html#jls-15.28): switch expressions and exhaustiveness requirements.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): Java 21 design, case ordering, guarded patterns, and null.
