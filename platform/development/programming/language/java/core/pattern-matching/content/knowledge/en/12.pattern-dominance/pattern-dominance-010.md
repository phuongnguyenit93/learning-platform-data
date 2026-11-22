# Reading Dominance Error Messages in Java Pattern `switch`

## 1. What is dominance, and why should you know how to read the error?

In **pattern matching for `switch`** (an official feature since Java 21), Java uses `case` labels to select how to handle values based on object type, constants, record patterns, and `when` conditions. Each label can match a set of values.

A `case` label is **dominated** when a **preceding** label already covers all values that the **subsequent** label can match according to the language's dominance rules. In that situation, the later branch can never be selected, so the compiler rejects the program.

Example:

```java
static String describe(Object value) {
    return switch (value) {
        case CharSequence text -> "sequence";
        case String text -> "string"; // ERROR: the later branch is dominated
        default -> "other";
    };
}
```

`String` implements `CharSequence`. Therefore, every value that matches `case String text` has already matched `case CharSequence text` before it. This is a conflict in the **set of matched values**, not a conflict in **variable names**; renaming the second variable to `s` will not fix the error.

The Java compiler message typically looks like this:

```text
error: this case label is dominated by a preceding case label
```

This message has three important clues:

- **`this case label`:** the label highlighted in the diagnostic is the **shadowed** label, usually located further down.
- **`is dominated`:** the compiler knows from the type/pattern rules that this label has no chance of being selected.
- **`by a preceding case label`:** you must look for **a label above it** that covers it; the offending label is not necessarily on the immediately preceding line.

From there, you can ask the right question: **“Which preceding case already accepts every value of the highlighted case?”** instead of only editing the statements inside the case body.

## 2. Reading a `javac` diagnostic part by part

Suppose the file `DominatedExample.java` contains:

```java
public class DominatedExample {
    static String inspect(Object value) {
        return switch (value) {
            case CharSequence cs -> "sequence";
            case String s -> "string";
            default -> "other";
        };
    }
}
```

Compile with **JDK 21 or later**:

```bash
javac --release 21 DominatedExample.java
```

This is an **intentionally non-compiling example**. The diagnostic output typically looks similar to:

```text
DominatedExample.java:5: error: this case label is dominated by a preceding case label
            case String s -> "string";
                 ^
1 error
```

*Note:* the file name, `^` caret column, display format, and exact wording may vary depending on the `javac` version and IDE interface. Identify the **underlying cause of the error** rather than relying on line numbers or exact wording.

How to read it:

1. **File name and location:** the compiler points to the file and the rejected `case` label. That is not necessarily where the ordering issue originates.
2. **Error type:** the word “dominated” indicates that the later case is covered by an earlier case.
3. **Highlighted pattern type:** here it is `String`.
4. **Trace upward through preceding cases:** `CharSequence` is a superinterface of `String`, so the preceding pattern accepts every `String`.
5. **Determine intent:** do you need to distinguish `String` from `StringBuilder` and other `CharSequence` implementations? If yes, place `String` first. If not, remove the redundant `String` branch.

Correct fix:

```java
static String inspect(Object value) {
    return switch (value) {
        case String s -> "string";
        case CharSequence cs -> "sequence";
        default -> "other";
    };
}
```

Now `"abc"` enters the `String` case; `new StringBuilder("abc")` enters the `CharSequence` case. Every branch has a chance to be selected.

**Do not apply superficial fixes:** renaming the pattern variable, adding `break` in a `->` branch, or changing the returned string **does not change** the subtype relationship that caused dominance.

## 3. Type relationships that commonly cause dominated cases

### 3.1. Superclass placed before subclass

Since `Integer extends Number`, this example fails:

```java
// ERROR: Integer is shadowed by the Number case above.
static String invalid(Object value) {
    return switch (value) {
        case Number n -> "number";
        case Integer i -> "integer";
        default -> "other";
    };
}
```

Because an `Integer` is always a `Number`, the `Integer` branch can never execute. Fix this by ordering from narrow to broad:

```java
static String valid(Object value) {
    return switch (value) {
        case Integer i -> "integer";
        case Number n -> "number";
        default -> "other";
    };
}
```

Also note: `Long`, `Double`, and other subtypes of `Number` can enter the `Number` branch, while `Integer` enters the first branch.

### 3.2. Broad interface placed before a narrower class or interface

```java
// ERROR:
return switch (value) {
    case CharSequence cs -> "char sequence";
    case String s -> "string"; // String implements CharSequence
    default -> "other";
};
```

It is not only `extends` between two classes; `implements` relationships also affect dominance. `StringBuilder` is also a `CharSequence`, but it is not a `String`; therefore, placing `String` before `CharSequence` makes sense.

### 3.3. Two identical type patterns with different variable names

```java
// ERROR:
return switch (value) {
    case String first -> "first";
    case String second -> "second"; // Dominated
    default -> "other";
};
```

Different variable names do not create two different match conditions. Both check the same type `String` (without a guard), so the later branch is shadowed.

### 3.4. Parent pattern covering a subtype branch in a sealed hierarchy

Suppose:

```java
sealed interface Shape permits Circle, Square {}
record Circle(int radius) implements Shape {}
record Square(int side) implements Shape {}
```

This is the wrong order:

```java
// ERROR in the Shape context above:
return switch (shape) {
    case Shape s -> "any shape";
    case Circle c -> "circle"; // Dominated
};
```

An unguarded `case Shape s` already accepts every non-`null` `Shape`, including `Circle`. If you want to handle `Circle` separately, place `case Circle c` first and then the general pattern. If you want to handle every subtype explicitly, use `case Circle` and `case Square` without `case Shape`.

## 4. Dominance errors when using `when`

A `when` guard is an additional condition evaluated **after the pattern matches**. It allows branches of the same type to handle different value domains, but order matters.

### 4.1. Unguarded first, guarded second: dominated

```java
// ERROR:
return switch (value) {
    case String s -> "all strings";
    case String s when s.isBlank() -> "blank"; // Dominated
    default -> "other";
};
```

The first pattern accepts **every String**, leaving no values for the later branch to handle.

### 4.2. Guarded first, unguarded second: valid

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s -> "non-blank text";
    default -> "other";
};
```

If `s.isBlank()` is false, the program continues looking for an applicable case; the unguarded `case String s` catches the remaining strings. This is the **specialized case → general case of the same type** pattern.

### 4.3. `when true` is not a way to avoid dominance

```java
// ERROR:
return switch (value) {
    case String s when true -> "first";
    case String s -> "second"; // Dominated
    default -> "other";
};
```

In Java 21, a guard with the constant expression `true` does not restrict the pattern; during dominance analysis it is treated the same as an unguarded pattern. If the compiler reports dominance in this situation, look for `when true` as the culprit.

And a guard with the **constant `false`** value is also a separate compilation error:

```java
// ERROR: guard is the constant expression false.
return switch (value) {
    case String s when false -> "never";
    default -> "other";
};
```

This is not a trick to create an unreachable fallback branch; Java does not allow a constant false guard in a case label.

### 4.4. Two logically related guards can still compile

The following snippet **can compile**, yet the second branch is logically useless:

```java
static String classify(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "positive";
        case Integer n when n > 10 -> "large";
        case Integer n -> "not positive";
        default -> "other";
    };
}
```

Every `n > 10` also satisfies `n > 0`, so the `"large"` branch is never selected. However, the Java compiler **does not perform general-purpose logical theorem proving** on arbitrary `when` expressions to report dominance.

Fix by priority:

```java
static String classify(Object value) {
    return switch (value) {
        case Integer n when n > 10 -> "large";
        case Integer n when n > 0 -> "positive";
        case Integer n -> "not positive";
        default -> "other";
    };
}
```

**Limitation to understand:** *no dominance error* does not mean *no logically dead branch*. When reviewing guards, check subsumption relationships yourself even when the compiler accepts the code.

## 5. Duplicate `case` constants are not the same kind of dominance error

An easily confused error is **duplicate case label**:

```java
// ERROR: two constant labels have the same value.
static String invalid(int x) {
    return switch (x) {
        case 1 -> "one";
        case 1 + 0 -> "one again";
        default -> "other";
    };
}
```

Because `1 + 0` is a constant expression with value `1`, the compiler detects a **duplicate constant**. The diagnostic usually contains:

```text
error: duplicate case label
```

This is different from the `CharSequence` and `String` relationship: the issue is a **repeated constant value**, not a type set covered by a preceding pattern.

How to fix:

- If two constants simply represent the same value, **remove the duplicate label** or merge the logic into one branch.
- If you want to group **different** values, use `case 1, 2 -> ...`.
- If you want to handle a subtype/specific constant before a broad branch, change the **order** rather than deleting blindly.
- Two `case null` or two `default` labels also cause duplicate label errors, not pure subtype dominance errors.

Valid example:

```java
static String category(int x) {
    return switch (x) {
        case 1, 2 -> "small";
        case 3 -> "three";
        default -> "other";
    };
}
```

`case 1, 1 ->` is still invalid because the value is duplicated within the same label.

## 6. Constants can be shadowed by a preceding type pattern

Dominance is not caused only by pattern–pattern pairs. With a selector of type `Integer`:

```java
// ERROR:
static String invalid(Integer n) {
    return switch (n) {
        case Integer value -> "any integer";
        case 1 -> "one"; // Case 1 is dominated
    };
}
```

An unguarded `case Integer value` accepts every non-`null` `Integer` value, including `1`. The compiler can report that the later constant label is dominated by the preceding branch.

Place specific constants before general patterns:

```java
static String valid(Integer n) {
    return switch (n) {
        case 1 -> "one";
        case Integer value when value > 0 -> "positive";
        case Integer value -> "other integer";
    };
}
```

This snippet is exhaustive for **non-null** `Integer` values. If `null` is passed and there is no `case null`, the `switch` still throws `NullPointerException`.

An arbitrary guard placed before a constant can create a **logic** bug even if the compiler does not report dominance:

```java
static String confusing(Integer n) {
    return switch (n) {
        case Integer value when value > 0 -> "positive";
        case 1 -> "one"; // Syntactically valid, but 1 already entered the branch above
        case Integer value -> "other";
    };
}
```

Safe and readable ordering: **prioritized constants → specially guarded patterns → broad unguarded patterns**.

## 7. Another diagnostic: conflict between an unconditional pattern and `default`

With a selector of static type `Object`, an unguarded `case Object value` pattern can accept every non-null `Object`. If you add a separate `default`, the compiler may produce:

```text
error: switch has both an unconditional pattern and a default label
```

Intentionally invalid example:

```java
static String invalid(Object input) {
    return switch (input) {
        case Object obj -> "object";
        default -> "other"; // Cannot combine fallbacks like this
    };
}
```

Unlike ordinary subtype errors, the message does not necessarily use the word `dominated`, but it still involves **two branches both trying to act as the catch-all for remaining values**.

How to fix:

```java
static String withDefault(Object input) {
    return switch (input) {
        case String s -> "text:" + s;
        default -> "other";
    };
}
```

Or, if you need a pattern variable of type `Object`:

```java
static String withTotalPattern(Object input) {
    return switch (input) {
        case String s -> "text:" + s;
        case Object obj -> "other:" + obj.getClass().getSimpleName();
    };
}
```

**Note on `null`:** an ordinary type pattern like `case Object obj` does not match `null`; a standalone `default` also does not handle `null` in a Java 21 pattern `switch`. If `input` can be null, add `case null` and define an explicit policy.

```java
static String withNull(Object input) {
    return switch (input) {
        case null -> "missing";
        case String s -> s;
        default -> "other";
    };
}
```

Do not use `case null, String s` as a way to merge branches: that combined label is invalid because the `null` path has no value to initialize `s`. The valid form when combining null with a fallback is `case null, default`.

## 8. Another diagnostic: non-exhaustive `switch`

If a `switch expression` still has unhandled values, `javac` may report:

```text
error: the switch expression does not cover all possible input values
```

Example:

```java
// ERROR: only covers String and Integer; Object has many other possibilities.
static String incomplete(Object value) {
    return switch (value) {
        case String s -> "text";
        case Integer n -> "integer";
    };
}
```

This is a **missing-branch error**, not dominance: there is no redundant shadowed branch; on the contrary, **coverage is missing** for the rest. Fix it by adding `default` (if you want a fallback) or adding patterns that fully cover the selector type.

In Java 21, `switch` expressions and **enhanced `switch` statements** with patterns must be exhaustive. A legacy `switch` statement on `int` or an enum without patterns may omit `default` and still compile, because its rules are different.

With a sealed hierarchy, a `switch` on the sealed type can be exhaustive **without `default`** if all permitted subtypes are covered. In that case, adding `default` indiscriminately can hide a useful signal if a new subtype is later added to the hierarchy and the application is recompiled.

**Quick way to distinguish:**

| Message | Primary issue | How to start fixing |
| --- | --- | --- |
| `dominated by a preceding case label` | A **later** case is already covered by an **earlier** case | Look for a broad pattern/constant above |
| `duplicate case label` | A constant or `null` label is repeated | Remove/merge labels with the same value |
| `duplicate default label` | Multiple `default` labels exist | Keep only one fallback |
| `unconditional pattern and a default label` | Two mechanisms both catch all non-null values | Choose one catch-all mechanism |
| `does not cover all possible input values` | The `switch` **lacks** coverage | Add missing branches or `default` |
| `guard ... constant expression ... false` | A case has an invalid constant false guard | Remove the branch or fix the condition |

Not every error in the table is a dominance error, but they often appear during the same `switch` edit. Reading the message accurately avoids fixing one error by introducing another.

## 9. Overlapping values that are **not** dominated

Two type patterns can sometimes match **some** of the same objects without either pattern covering **all** objects of the other. This can be valid.

```java
static String byInterface(Object value) {
    return switch (value) {
        case CharSequence cs -> "sequence";
        case java.io.Serializable serializable -> "serializable";
        default -> "other";
    };
}
```

A `String` implements both `CharSequence` and `Serializable`, so `"abc"` can match both. However, `CharSequence` is not a subtype of `Serializable` and vice versa; each interface has implementations that do not belong to the other. Therefore, there is no full-coverage dominance relationship based on types in this example.

The earlier branch is chosen when a value matches both. Reversing the order can change the result for `String`, even though the code still compiles.

**How to read this situation:** if `javac` does **not** report dominance, you should still ask:
- Can any value match multiple branches?
- Could the branch order violate business priority?
- Should you add a branch for a specific type (such as `String`) before the two general interfaces?

Dominance is an error detected by the compiler; *overlap* is an intersection that developers must understand and test.

## 10. Standalone Java 21 program after fixing dominance

Save to **`DominanceDiagnosticsDemo.java`**:

```java
public class DominanceDiagnosticsDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";

            case String s when s.isBlank() -> "blank";
            case String s -> "text:" + s;

            case Integer n when n >= 0 -> "nonnegative-int:" + n;
            case Integer n -> "negative-int:" + n;

            case Number n ->
                "other-number:" + n.getClass().getSimpleName();

            case CharSequence cs ->
                "char-sequence:" + cs.getClass().getSimpleName();

            default -> "other:" + value.getClass().getSimpleName();
        };
    }

    static String classifyGuard(Object value) {
        return switch (value) {
            case Integer n when n > 10 -> "large";
            case Integer n when n > 0 -> "positive";
            case Integer n -> "nonpositive";
            default -> "not-integer";
        };
    }

    public static void main(String[] args) {
        Object[] values = {
            null, " ", "Java", 4, -2, 3.5,
            new StringBuilder("hi"), true
        };

        for (Object value : values) {
            System.out.println(classify(value));
        }

        System.out.println("12:" + classifyGuard(12));
        System.out.println("5:" + classifyGuard(5));
        System.out.println("0:" + classifyGuard(0));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 DominanceDiagnosticsDemo.java
java DominanceDiagnosticsDemo
```

Output:

```text
null
blank
text:Java
nonnegative-int:4
negative-int:-2
other-number:Double
char-sequence:StringBuilder
other:Boolean
12:large
5:positive
0:nonpositive
```

Explanation of why the cases no longer shadow one another:

1. `case null` handles null explicitly; do not confuse `default` with null.
2. Empty/blank `String` values enter the guarded branch; other `String` values enter the unguarded `String` branch.
3. Non-negative `Integer` values enter the guarded branch; negative `Integer` values enter the unguarded branch of the same type.
4. `Number` is placed **after** `Integer`, so it handles non-`Integer` numbers such as `Double`.
5. `CharSequence` is placed **after** `String`, so it handles other character sequences such as `StringBuilder`.
6. `default` catches the remaining non-null objects, such as `Boolean`.
7. In `classifyGuard`, the `> 10` threshold comes before `> 0`, so `12` gets `large`, `5` gets `positive`, and `0` gets `nonpositive`.

This example demonstrates **both type-based dominance and guard ordering**. The program itself is complete runnable code; the snippets marked **ERROR** in earlier sections are intentionally non-compiling examples and must not be pasted into this file.

## 11. Workflow for fixing a dominance error in real code

When you encounter an error from `javac`, an IDE, or CI, use the following workflow:

**Step 1 — Note the highlighted case location.** Check which exact `switch` reports the error and which type pattern or constant is in that label. If a method has multiple `switch` blocks, do not rely on identical variable names in another block.

**Step 2 — Check the static type of the selector.** `Object`, `Number`, `Integer`, an interface, or a sealed class can lead to different type checks and dominance relationships. Do not just look at the object assigned on a single test line.

**Step 3 — Find the preceding label that covers the highlighted case.** Consider `extends`, `implements`, generic type arguments, unconditional patterns, and constant cases. A broad pattern many lines above can still be the culprit.

**Step 4 — Read guards logically.** If a preceding case has no guard or has `when true`, it can completely shadow a later case. If a preceding case has an arbitrary `when` guard, check whether the overlap is a business-logic issue that the compiler does not detect.

**Step 5 — Choose the fix based on intent:** if the specific case needs distinct behavior, order **specific first → general later**; if two cases actually do the same thing, merge or remove the redundant case; if condition priority matters, place narrower guards before broader guards; if a broad branch is no longer needed, remove it.

**Step 6 — Re-check exhaustiveness.** After reordering or removing cases, a `switch` expression or enhanced `switch` may be missing branches. If `default` is present, consider whether it hides maintenance warnings for a sealed hierarchy.

**Step 7 — Check null and runtime behavior.** `default` does not automatically handle a `null` selector. Add `case null` if a specific policy is needed. Be aware that a guard can throw an exception during case selection if guard code unsafely accesses a null field or component.

**Step 8 — Run boundary tests.** For example, with numeric guards, test `0`, `1`, `10`, `11`; with strings, test `""`, `" "`, `"abc"`; with subtypes, test the superclass, subclass, and overlapping interfaces. When multiple branches overlap, verify **which branch actually wins**.

**Step 9 — Compile with the target Java version.** The `case String s when ...` syntax is stable starting in Java 21; do not use Java 17 preview diagnostics or syntax from other Java versions to assume all messages must match. You can use `javac --release 21 -Xdiags:verbose File.java` to see extra context when short diagnostics are unclear.

A useful rule when fixing code: **don't just make the error disappear; prove that every remaining case has a target set of values, and that the case order reflects the intended processing priority.**

## 12. Common wrong fixes

- **Only renaming the pattern variable:** `case String s` and `case String text` with the same type and no guard still match the exact same set of values.
- **Putting `default` at the end and assuming everything is fixed:** `default` helps coverage, but it does not validate a dominated branch; it can also conflict with an unconditional pattern.
- **Deleting the specific case just to make it compile:** this can drop special handling for a subtype, causing everything to fall into the parent case.
- **Assuming two similar guards will always be rejected by `javac`:** non-constant guards can overlap logically without any diagnostic.
- **Seeing two overlapping interfaces and assuming it must be an error:** partial overlap alone is not enough to conclude dominance.
- **Thinking a runtime `ClassCastException` is a dominance error:** dominance is determined at compile time; a bad cast is a separate runtime issue.
- **Confusing it with `duplicate case label`:** duplicate constants follow a separate rule; reordering two equal constants does not help.
- **Putting a supertype before a subtype to “catch general cases first”:** in practice, the broad branch blocks the specific branch behind it.
- **Forgetting null:** `case Object o` does not mean a null selector matches; a standalone `default` does not handle null automatically either.
- **Using Java 17 as the main compilation baseline for pattern `switch`:** Java 21 is the stable milestone for this feature.

## 13. Diagnostic exercises with answers

**Exercise 1.** The message `this case label is dominated by a preceding case label` appears at `case Integer i`. Above it is `case Number n`. Which branch needs to be moved?

**Answer:** Move `case Integer i` before `case Number n` if integers need separate handling. `Integer` is a subtype of `Number`, so having the general branch first shadows the specific branch.

**Exercise 2.** Two labels `case 1` and `case 1 + 0` report `duplicate case label`. Can you fix this by changing their order?

**Answer:** No. Both labels always have the same constant value `1`; you must remove the duplicate label or merge the logic into one branch.

**Exercise 3.** You write `case String s -> ...` followed by `case String t when t.isBlank() -> ...`. Why does it report dominance?

**Answer:** The first pattern already accepts every `String`, including blank ones. Move the guarded branch before the unguarded branch.

**Exercise 4.** Why can `case Integer n when n > 0` before `case Integer n when n > 10` still compile?

**Answer:** `javac` does not solve all subsumption relationships between arbitrary guards. At runtime, the `n > 10` branch is never selected because every number satisfying it is already caught by `n > 0`. Place the narrower guard first.

**Exercise 5.** You have `case CharSequence cs` and `case java.io.Serializable s`. The value `"abc"` can match both. Is this necessarily a dominance error?

**Answer:** No. The two interfaces overlap, but neither is a full subtype of the other in this example. The case order determines which branch wins for `String`; the compiler can accept both.

**Exercise 6.** You have `case Object obj` and a separate `default` on an `Object` selector. What is the underlying error the compiler reports?

**Answer:** Two non-null fallback mechanisms conflict; use one of them. If you need to handle null, add a separate `case null`.

**Exercise 7.** The compiler reports `the switch expression does not cover all possible input values`. Does that mean a case is being dominated?

**Answer:** No. That is a **missing coverage error**, almost the opposite of a redundant shadowed case. Add the needed branches or an appropriate fallback.

### Key takeaways

- Reading `dominated by a preceding case label` is a signal: **look upward** to find the covering case.
- Put **specific patterns first, general patterns later**; for the same type, put **restricted guards first, unguarded later**.
- `when true` does not avoid dominance; arbitrary guards can overlap logically without a compiler warning.
- Do not equate dominance with duplicate constants, duplicate `default`, missing exhaustiveness, or runtime errors.
- After fixing, verify **coverage, priority order, null handling, and boundary cases**.

### Official documentation

- [JLS Java SE 21 §14.11 — The switch Statement, case labels, and dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS Java SE 21 §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [JLS Java SE 21 §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
