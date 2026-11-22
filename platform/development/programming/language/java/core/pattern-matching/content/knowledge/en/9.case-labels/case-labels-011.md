# Duplicate and Overlapping Case Labels in Java Pattern `switch`

## 1. "Redundant" Means More Than Repeating the Same `case` Line

Starting in Java 21, `switch` officially supports **pattern matching**: a `case` branch can be a constant, a type pattern, a record pattern, or a pattern with a `when` guard. As a result, two `case` labels can overlap or be redundant in several ways:

1. **Duplicate constant value** (*duplicate case constant*): two labels refer to the same constant value, even if the expressions are written differently.
2. **Duplicate special labels**: two `default` labels or two `case null` labels in the same `switch`.
3. **Covered by a preceding branch** (*dominated case label*): every value that the later branch could accept is already accepted by an earlier branch with no restricting guard; the later branch can never run.
4. **Overlapping match sets that the compiler does not forbid**: two patterns may both match certain values, or their guards may be logically equivalent. In this case, **branch order** affects the result, and the compiler does not necessarily detect the logic error.

It is important to distinguish **compile-time errors** from **business-logic redundancy**. Java enforces clear rules for constants, `null`, `default`, pattern dominance, and exhaustiveness; Java does **not** prove whether arbitrary `when` expressions are logically equivalent.

General example:

```java
static String category(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "text";
        case Integer n -> "integer";
        case null -> "null";
        default -> "other";
    };
}
```

The two `String` labels **do not conflict under the dominance rule**: the first branch only accepts empty/whitespace-only `String` values, and the second branch accepts the remaining `String` values. Conversely, if you place the unguarded `case String s` first, the guarded `String` branch becomes unreachable and is rejected by the compiler.

## 2. Duplicate Constants: `duplicate case label`

In a `switch` using constant labels, Java does not allow two constants with the **same value** in the same `switch` block.

```java
// ERROR: both constant labels have the value 1.
static String invalid(int value) {
    return switch (value) {
        case 1 -> "first";
        case 1 -> "second"; // duplicate case label
        default -> "other";
    };
}
```

The rule compares **compile-time constant values**, not just the source text. Therefore, this is also an error:

```java
// ERROR: 1 + 0 is a constant expression with value 1.
static String invalidExpression(int value) {
    return switch (value) {
        case 1 -> "one";
        case 1 + 0 -> "still one"; // duplicate case label
        default -> "other";
    };
}
```

Grouping multiple constants into a single branch is only valid when the values are **distinct**:

```java
static String valid(int value) {
    return switch (value) {
        case 1, 2 -> "small";
        case 3 -> "three";
        default -> "other";
    };
}
```

Writing `case 1, 1 -> "small";` is still a **duplicate constant**; placing two values in the same label does not make repetition valid.

For enums, a `case RED` label and another `case RED` label in the same block are also duplicates. Java checks for the **same enum constant**, not the variable name used in the branch body.

**How to fix:** combine the values that share handling into **one** non-duplicate label, or remove the repeated label. Do not try to resolve the error by changing the branch body: the same constant cannot appear twice even if the actions differ.

## 3. Duplicate `null` and `default`

In Java 21, `case null` is a special label for a selector equal to `null`. A `switch` cannot declare `case null` twice:

```java
// ERROR: duplicate case null.
static String invalidNull(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s -> s;
        case null -> "still missing"; // duplicate case label
        default -> "other";
    };
}
```

Similarly, you cannot write two `default` labels:

```java
// ERROR: duplicate default label.
static String invalidDefault(Object value) {
    return switch (value) {
        case String s -> s;
        default -> "other";
        default -> "again"; // duplicate default label
    };
}
```

You can handle `null` and the fallback in **the same special branch**:

```java
static String fallback(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        case null, default -> "unsupported or null";
    };
}
```

`case null, default` accepts `null` and any remaining values not handled by the `String` branch. If you already use this label, do not add another standalone `case null` or `default`.

**Do not confuse this:** a standalone `default` **does not catch `null`** in a Java 21 pattern `switch`. If the selector is `null` and there is no `case null`, the program throws `NullPointerException`, even when `default` is present.

```java
static String withoutNull(Object value) {
    return switch (value) {
        case String s -> s;
        default -> "other";
    };
}

// withoutNull(42)   -> "other"
// withoutNull(null) -> throws NullPointerException
```

Having a single `default` alongside a single `case null` is not a "duplicate"; they handle two different domains. To handle them together, write `case null, default`.

## 4. Pattern Dominance: A Later Branch Covered by an Earlier One

In a pattern `switch`, **dominance** is the rule that detects a branch that can never be selected because an earlier branch already covers all of its cases. Cases are matched in order of appearance; therefore, Java rejects dominated labels.

Consider:

```text
CharSequence
    ^
    |
  String
```

Every `String` implements `CharSequence`. If you place the general pattern first:

```java
// ERROR in Java 21: String is dominated by the preceding CharSequence.
static String invalidOrder(Object value) {
    return switch (value) {
        case CharSequence cs -> "sequence";
        case String s -> "string"; // dominated case label
        default -> "other";
    };
}
```

Because every value that can match `case String s` also matches `case CharSequence cs`, the `String` branch never gets a chance to run. The compiler message typically contains wording such as *this case label is dominated by a preceding case label*.

**How to fix: place the specific type before the broader type**:

```java
static String validOrder(Object value) {
    return switch (value) {
        case String s -> "String";
        case CharSequence cs -> "CharSequence";
        default -> "Other";
    };
}
```

For `"Java"`, the `String` branch is selected; for `new StringBuilder("x")`, the `CharSequence` branch is selected.

The same rule applies to class hierarchies:

```java
// ERROR: Number dominates Integer.
static String invalidNumberOrder(Object value) {
    return switch (value) {
        case Number n -> "number";
        case Integer i -> "integer"; // dominated
        default -> "other";
    };
}
```

Reordering to `case Integer i` first and then `case Number n` is valid: the `Integer` branch handles integers, and the `Number` branch handles other numeric types.

**Important:** dominance checks the **set of matchable values**, not the name of the pattern variable. Renaming `case String s` to `case String text` does not avoid dominance.

## 5. Two `case` Labels of the Same Type: Guards Determine Dominance

### 5.1. Unguarded pattern before a pattern of the same type: error

```java
// ERROR: the String branch below can never be selected.
static String invalidGuardOrder(Object value) {
    return switch (value) {
        case String s -> "any string";
        case String s when s.isBlank() -> "blank"; // dominated
        default -> "other";
    };
}
```

The unguarded `case String s` already accepts **every non-null String**, including blank strings. Thus, the `when` branch below it has no values left to match.

### 5.2. Guarded pattern first, unguarded pattern second: valid

```java
static String validText(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "text";
        default -> "other";
    };
}
```

The first branch only accepts strings satisfying `isBlank()`; when the guard is false, the next `String` branch can be selected. This is the standard pattern for **specialized classification followed by a same-type fallback**.

### 5.3. A `when true` guard is treated as unguarded

```java
// ERROR: when true is a constant expression true.
static String invalidTrueGuard(Object value) {
    return switch (value) {
        case String s when true -> "string";
        case String s -> "also string"; // dominated
        default -> "other";
    };
}
```

Do not assume that adding `when` automatically separates two labels. In Java 21, a guard that is the **constant expression `true`** is treated as having no restricting condition for dominance purposes. A guard that is the constant expression `false` is also invalid.

## 6. Logical Overlap in `when` Guards May Still Compile

Unlike subtype relationships, Java generally **does not prove** whether one arbitrary `when` condition implies or is equivalent to another.

For example:

```java
static String confusing(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "positive";
        case Integer n when n > 10 -> "large";
        case Integer n -> "zero or negative";
        default -> "not integer";
    };
}
```

The code above **compiles**, but logically, any value with `n > 10` always satisfies `n > 0` first. Therefore, the `"large"` branch **can never be selected** at runtime, even though the compiler does not report dominance for this kind of guard.

Place the **narrower condition first and the broader condition later**:

```java
static String correct(Object value) {
    return switch (value) {
        case Integer n when n > 10 -> "large";
        case Integer n when n > 0 -> "positive";
        case Integer n -> "zero or negative";
        default -> "not integer";
    };
}
```

Similarly, two branches with the **exact same guard condition** can also be accepted by the compiler:

```java
static String repeatedGuards(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "first";
        case Integer n when n > 0 -> "second"; // May compile!
        case Integer n -> "not positive";
        default -> "other";
    };
}
```

For every positive `Integer`, the `"first"` branch is selected; the `"second"` branch never runs. This is **logical redundancy, not necessarily a syntax error**.

The Java 21 JLS rules for dominance mainly handle labels **without restricting guards**; an arbitrary guard is generally not used as proof that it dominates a later label. The clear exception is `when true`. For this reason, **successful compilation does not prove that `case` branches do not overlap in business logic**.

When you have multiple conditions, order them from **specific to general**, and write tests for boundary values: `-1`, `0`, `1`, `10`, `11`.

## 7. Pattern Dominating a Constant: Duplicate Value vs. Dominated Constant

For a `switch` with an `Integer` selector, an unguarded `Integer n` type pattern accepts every non-null `Integer` value. Placing the constant `case 1` after it therefore causes a dominance error:

```java
// ERROR: case 1 is dominated by Integer n above.
static String invalidConstant(Integer value) {
    return switch (value) {
        case Integer n -> "an integer";
        case 1 -> "one"; // dominated by preceding pattern
    };
}
```

To handle the number `1` specially, place the constant first:

```java
static String validConstant(Integer value) {
    return switch (value) {
        case 1 -> "one";
        case Integer n when n > 0 -> "positive";
        case Integer n -> "zero-or-negative";
    };
}
```

The labels above are exhaustive for all non-null `Integer` values; no `default` is needed. If `value == null`, the `switch` still throws `NullPointerException` because there is no `case null`.

There is a subtle distinction:

```java
static String guardBeforeConstant(Integer value) {
    return switch (value) {
        case Integer n when n > 0 -> "positive";
        case 1 -> "one";
        case Integer n -> "other integer";
    };
}
```

This snippet **compiles**, because the guard `n > 0` is not considered unconditional for dominance checking. However, when `value == 1`, the first branch is selected and `case 1` never receives this value at runtime.

**Tip:** when combining constants with type patterns, prefer **constants first → guarded patterns → unguarded patterns**. This order makes intent clear and prevents specific values from being shadowed.

Note: the numeric label examples use an `Integer` selector; do **not** arbitrarily use `Object` as the selector and add `case 1`: whether a constant case is valid also depends on the static type of the selector under Java 21 `switch` rules.

## 8. Two Patterns That Can Both Match Are Not Necessarily Forbidden

Consider two interfaces:

```java
CharSequence
java.io.Serializable
```

A `String` implements both interfaces, so the object `"Java"` can match both patterns. However, not every `CharSequence` is `Serializable`, and not every `Serializable` is a `CharSequence`. The compiler has no basis to say that one pattern **completely covers** the other.

```java
static String classify(Object value) {
    return switch (value) {
        case CharSequence seq -> "sequence";
        case java.io.Serializable serializable -> "serializable";
        default -> "other";
    };
}
```

This code is valid in Java 21. For `"Java"`, the earlier `CharSequence` branch is selected; if you swap the two branches, a `String` enters the `Serializable` branch first.

**Takeaway:** *overlap* (having values that match both) **does not mean** *dominance* (an earlier branch covering **every** value of a later branch). When overlap is permitted, branch order becomes part of the program's behavior.

This also applies when two different guards have overlapping value ranges. If both `n > 0` and `n % 2 == 0` are true for `n = 2`, only the first branch whose guard is satisfied is selected. Order branches by business priority rather than expecting the compiler to pick a "better" branch.

## 9. `default` and an Unconditional Pattern Can Also Overlap in Role

A pattern that is **unconditional for the selector type** can act as the catch-all branch. With a selector of static type `Object`:

```java
// ERROR: Object o is an unguarded pattern covering every non-null Object,
// so you cannot add default as a separate fallback branch.
static String invalidFallback(Object value) {
    return switch (value) {
        case Object o -> "object";
        default -> "other"; // unconditional pattern + default
    };
}
```

Similarly, if `case Object o` appears before `case String s`, the `String` branch is dominated.

How to handle this:

- Use **`default`** if you only need a fallback and do not need to bind a specific pattern variable.
- Use **`case Object o`** to bind a variable `o` in the catch-all branch for non-null values.
- If you need to handle `null`, add **`case null`** explicitly; a normal type pattern does not match `null`.
- Do not combine an unconditional catch-all pattern with a separate `default` in the same block.

A `case null, default` label already combines both special cases into one label; do not add another `case null` or `default` afterward.

**Exhaustiveness** is a separate question: a `switch` expression or enhanced `switch` statement must cover every possible non-null value of the selector type. Adding `default` often helps achieve exhaustiveness, but it does not make dominated branches valid. With an adequately covered enum or sealed hierarchy, many `switch` expressions do not need `default`.

## 10. Standalone Java 21 Program: Valid Cases

Save the entire program to **`CaseLabelOverlapDemo.java`**:

```java
public class CaseLabelOverlapDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank";
            case String s -> "text:" + s;
            case Integer n when n > 0 -> "positive:" + n;
            case Integer n -> "integer:" + n;
            default -> "other";
        };
    }

    static String byType(Object value) {
        return switch (value) {
            case String s -> "String";
            case CharSequence cs -> "CharSequence";
            default -> "Other";
        };
    }

    static String guarded(Object value) {
        return switch (value) {
            case Integer n when n > 10 -> "big";
            case Integer n when n > 0 -> "positive";
            case Integer n -> "nonpositive";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {null, " ", "Java", 12, -2, 3.14};

        for (Object value : inputs) {
            System.out.println(classify(value));
        }

        System.out.println(byType("abc"));
        System.out.println(byType(new StringBuilder("x")));

        System.out.println(guarded(20));
        System.out.println(guarded(5));
        System.out.println(guarded(0));
    }
}
```

Compile and run with **JDK 21+**, without enabling preview:

```bash
javac --release 21 CaseLabelOverlapDemo.java
java CaseLabelOverlapDemo
```

Output:

```text
null
blank
text:Java
positive:12
integer:-2
other
String
CharSequence
big
positive
nonpositive
```

Explanation of the output:

1. `null` enters `case null`, not `default`.
2. `" "` has type `String` and satisfies `isBlank()`, so the guarded `String` branch is selected.
3. `"Java"` does not satisfy `isBlank()` but is still a `String`, so the unguarded `String` branch is selected.
4. `12` enters `Integer n when n > 0`; `-2` enters the unguarded `Integer n`.
5. `3.14` is a `Double` and matches none of the patterns above, so it goes to `default`.
6. In `byType`, `String` is placed before `CharSequence`; each branch keeps a meaningful scope.
7. `guarded(20)` produces `big`, `guarded(5)` produces `positive`, and `guarded(0)` produces `nonpositive` because the guards are ordered **narrower first, broader later**.

This program contains valid overlapping cases and uses separate pattern variables per branch; the output shows that ordering is not merely cosmetic.

The snippets marked **ERROR** in sections 2–9 are examples *intentionally written not to compile* to illustrate the rules. Do not merge them into the standalone runnable file in this section.

## 11. Quick Comparison Table of Overlap Types

| Situation | Allowed in Java 21? | Reason / How to fix |
| --- | --- | --- |
| `case 1`, then `case 1` | No | Duplicate constant value; keep only one |
| `case 1`, then `case 1 + 0` | No | Both constant values equal 1 |
| `case 1, 1` | No | Duplicate constant within the same label |
| Two `case null` labels | No | Cannot repeat `null` |
| Two `default` labels | No | Cannot repeat `default` |
| `case CharSequence c`, then `case String s` | No | Later pattern is dominated; reverse order |
| `case String s`, then `case CharSequence c` | Yes | Specific `String` first, broader `CharSequence` later |
| `case String s`, then `case String t` | No | First unguarded pattern covers all `String` values |
| `case String s`, then `case String t when t.isBlank()` | No | Later branch is dominated |
| `case String s when s.isBlank()`, then `case String s` | Yes | Guarded first, `String` fallback later |
| `case String s when true`, then `case String s` | No | Constant `true` guard is treated as unconditional |
| Two `case Integer n when n > 0` | Possibly | Java does not solve all guard relationships; later branch is logically dead |
| `case Integer n` then `case 1` (`Integer` selector) | No | Constant is dominated by the earlier pattern |
| `case 1` then `case Integer n` (`Integer` selector) | Yes | Constant is checked before the broader pattern |
| `case Object o` and `default` (`Object` selector) | No | Duplicate catch-all branch |
| `case null` and one `default` | Yes | Two distinct purposes |
| `case null, default` | Yes | Special combined label; do not repeat `null` or `default` again |

Exact compiler error messages may vary by JDK version, but the classification rules here are based on Java SE 21.

## 12. How to Troubleshoot Compiler Errors

When the compiler reports `duplicate case label`, `duplicate default label`, or `dominated by a preceding case label`, do not just rename variables. Follow this sequence:

1. **Identify the selector type** of the `switch` and the Java version in use. Pattern `switch` with `when` became final in Java 21. Java 17 only had some pattern `switch` features in preview, so do not run Java 21 examples under `javac --release 17`.
2. **Check constants**: do any labels use the same value, including a constant expression like `1 + 0` or the same enum constant?
3. **Check special labels**: how many `case null`, `default`, or `case null, default` labels are present?
4. **Inspect pattern types from top to bottom**: is an earlier pattern a supertype or an unconditional pattern covering a later pattern? For example, `CharSequence` before `String`.
5. **Inspect guards**: does the earlier pattern have `when`? If the guard is the constant `true`, it does not restrict the branch. If the guard is arbitrary, the compiler usually does not prove logical implication, so review the conditions yourself.
6. **Check constants vs. patterns**: on a compatible selector, is a constant placed after an unconditional pattern that dominates it?
7. **Preserve exhaustiveness**: after removing or reordering branches, a `switch` expression or enhanced `switch` must still cover all cases. Add a fallback when needed; if using a sealed hierarchy and you want the compiler to warn about new subtypes, consider omitting `default`.
8. **Run boundary tests**: for numeric conditions, test `0`, `1`, `10`, `11`; for `String`, test `""`, `" "`, `"Java"`; for types, test the superclass, subclass, and `null`.

### About `switch` with `:` vs. `->`

The examples in this article use `->` branches so each label has its own body with no fall-through. With traditional `case A:` syntax, multiple labels can intentionally share a group of statements; this still does **not** allow repeating the same constant, `null`, or `default`.

```java
// Group multiple distinct constants into the same handling block:
static String describe(int value) {
    String result;
    switch (value) {
        case 1:
        case 2:
            result = "small";
            break;
        default:
            result = "other";
    }
    return result;
}
```

This is a valid switch statement pattern. However, if you write `case 1:` twice, the compiler still reports a duplicate constant. With pattern variables, flow scoping and fall-through rules can also cause other compile errors; prefer `->` when learning pattern `switch`.

## 13. Self-Check Questions

**Question 1.** Are `case 1 ->` and `case 1 + 0 ->` different?

**Answer:** Not in constant value. Java evaluates constant expressions at compile time; the two labels have the same value and are rejected.

**Question 2.** Why is `case CharSequence c` followed by `case String s` invalid, while reversing the order is valid?

**Answer:** Because `String` is a subtype of `CharSequence`. Placing the general pattern first matches every `String`, causing the specific branch below it to be dominated. Placing the specific one first keeps both branches useful.

**Question 3.** If the compiler allows `case Integer n when n > 0` and `case Integer n when n > 10`, does that mean they do not overlap?

**Answer:** No. The value `11` matches both conditions, but the earlier `n > 0` branch is selected. The later branch is never selected for any number, even though the compiler may not detect this logically.

**Question 4.** Is `case String s when true` before `case String s` valid?

**Answer:** No. A constant `true` guard is treated as not restricting the pattern, so the second `String` branch is dominated.

**Question 5.** With an `Object` selector, are `case CharSequence c` and `case java.io.Serializable s` guaranteed to be an error?

**Answer:** No. Both interfaces can be implemented by the same object (for example, `String`), but neither interface covers the entirety of the other. Both patterns can be valid, and **order** determines which branch is selected for overlapping values.

**Question 6.** Does adding `default` after `case Object o` on an `Object` selector fix a missing-branch error?

**Answer:** No. An unconditional `case Object o` already accepts all non-null objects, so another `default` is considered redundant in role. If you need to handle `null`, write `case null` separately.

**Question 7.** If there are both `case null` and `default` in the same `switch`, is that redundant?

**Answer:** No. `case null` handles a `null` selector; a standalone `default` handles non-null values not matched by other cases. You can use the special label `case null, default` to combine both paths.

## 14. Key Takeaways

- **Duplicate constant:** repeating a constant *value*, even with differently written constant expressions → compile-time error.
- **Duplicate `null`/`default`:** repeating special labels → compile-time error.
- **Dominance:** an earlier branch without a restricting guard covering all values that a later branch can accept → compile-time error.
- **Guards:** place specific guarded patterns before unguarded patterns. A constant `true` guard is treated as unguarded; general guards can overlap logically without compiler detection.
- **Valid overlap:** two patterns that both match some objects do not necessarily cause an error; the first matching branch wins.
- **Generally safe order:** constant cases → specific patterns → guarded patterns → broader unguarded patterns → fallback, depending on the actual relationships between labels.
- **`default` does not replace `case null`**. Maintain proper exhaustiveness, and do not use `default` to hide cases that should be handled explicitly.

**Conclusion:** When you see "redundant" `case` labels, ask whether they **repeat the exact same constant**, **one branch covers the entire later branch**, or **they only overlap on certain values**. These three different situations lead to three different fixes: removing the repeated label, reordering or narrowing the pattern, or reviewing business priority and testing guards.

### Official Documentation

- [Java SE 21 JLS §14.11 — The switch Statement / Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 JLS §14.30.3 — Properties of Patterns / Dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [Java SE 21 JLS §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
