# Dominance Analysis in Pattern Matching (Java 21)

## 1. Purpose and Role of Dominance Analysis

When using pattern matching in a `switch`, a single value can match **multiple** branches: for example, a `String` is both a `String` and a `CharSequence`; a record `Point(2, 2)` can match both the pattern `Point(var x, var y)` and a guarded pattern with `when x == y`. Java selects the applicable branch in source code order. To make programs predictable and avoid branches that are guaranteed to be shadowed, **the compiler performs dominance analysis** on `case` labels.

In Java 21, **dominance** (the coverage relationship between patterns/labels) is a **compile-time check**. A later label is considered *dominated* if the compiler determines that a preceding label already covers every value to which the later label could apply. This is a compile-time error, not merely a branch that is unlikely to run.

After this lesson, you will be able to:

- Explain dominance between type patterns such as `CharSequence cs` and `String s`.
- Order constant labels, guarded `when` branches, general branches, `null`, and `default`.
- Identify the special case of `when true` and why the compiler does not attempt to prove arbitrary `when` predicates.
- Apply dominance to **record patterns**, including nested record patterns and component patterns.
- Distinguish between **dominance**, **exhaustiveness**, and **flow scoping** of pattern variables.
- Read the error `this case label is dominated by a preceding case label` and fix it according to the rules.

**Version requirement:** Pattern matching for `switch` (JEP 441) and record patterns (JEP 440) became standard in Java 21. The practical examples use `javac --release 21` and do not require enabling preview features.

## 2. What Does the Compiler Analyze?

Consider an intentionally incorrect example:

```java
static String describe(Object value) {
    return switch (value) {
        case CharSequence chars -> "sequence: " + chars.length();
        case String text -> "text: " + text; // dominance ERROR
        default -> "other";
    };
}
```

`String` is a subtype of `CharSequence`. Therefore, every non-`null` value that matches `case String text` also matches `case CharSequence chars`. The `CharSequence` branch comes first and has no guard, so it is always chosen for `String` values; the later `String` branch is dominated. The Java 21 compiler reports an error on the second branch.

The fix is to place **the specific type before the general type**:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "text: " + text;
        case CharSequence chars -> "sequence: " + chars.length();
        default -> "other";
    };
}
```

Think of the check in two steps:

1. Determine the **set of values** to which the later label can apply.
2. Check whether a **preceding, unguarded** label covers that entire set of values according to the language rules.

Qualitatively, if label A covers every value that label B can accept and A precedes B, then B has no chance of ever being selected. However, do not treat this as a solver for arbitrary boolean expressions: Java defines dominance primarily based on **type relationships**, pattern structure, and a few cases determinable at compile time.

### Why does the compiler check this before runtime?

The compiler already knows the declared type of the selector variable and the type of each pattern. It can infer subtype/coverage relationships without running the program. Rejecting dominated branches prevents confusion caused by incorrect ordering. When multiple **valid** branches can match, runtime still evaluates them top-to-bottom and picks the first applicable label.

**Note:** A branch with a dominance error is not "automatically skipped" to let the program compile. You must fix the order or the content of the labels.

## 3. Dominance Between Type Patterns

### 3.1. Supertype–Subtype Relationships

For example, `String implements CharSequence`, `Integer extends Number`:

```java
// Valid: narrow type first, wide type after.
return switch (value) {
    case String s -> "string: " + s;
    case CharSequence cs -> "char sequence";
    case Integer i -> "integer: " + i;
    case Number n -> "number: " + n;
    case null -> "null";
    default -> "other";
};
```

In the snippet above, `value` has type `Object`. The `Integer` branch precedes `Number`; the `String` branch precedes `CharSequence`. Both pairs can match the same value at runtime, but the specific branch is placed first so it is not shadowed.

Reversing the order:

```java
// INTENTIONALLY WRONG: Integer is covered by Number.
return switch (value) {
    case Number n -> "number";
    case Integer i -> "integer"; // ERROR
    default -> "other";
};
```

The error is not because `Integer` or `Number` cannot be used with `Object`; the error is that **the label order makes it impossible for the later branch to be selected**.

### 3.2. Patterns Do Not Depend on Variable Names

Two branches with the same type pattern that differ only in their variable names also trigger dominance if the first branch is unguarded:

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case String first -> "first";
    case String second -> "second"; // ERROR
    default -> "other";
};
```

The names `first`/`second` are just pattern variable names; they do not distinguish any additional state. Adding another unguarded branch with the same type creates no new condition.

### 3.3. A Broad Pattern Covering a Constant Branch

When the selector has a type compatible with a constant (for example, `Integer`), the pattern `Integer i` can cover the `case 0` label:

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case Integer i -> "integer";
    case 0 -> "zero"; // ERROR: already covered by the Integer branch
    case null -> "null";
};
```

Here `value` has type `Integer`. Fix: move the constant **before** the general branch—see the example in section 5. Duplicate constants are a separate `switch` error; do not call every duplicate-constant error dominance.

## 4. How Does the `when` Guard Affect Dominance?

A guard adds a boolean condition after the pattern has matched:

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s -> "other string";
    default -> "other type";
};
```

This example is **valid**. The first label selects a `String` only if `s.isBlank()` is `true`. The next label handles strings that did not satisfy the preceding guard. This is a very common idiom: **guarded cases on top, unguarded case below**.

Reversing the two branches:

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case String s -> "any string";
    case String s when s.isBlank() -> "blank"; // ERROR dominated
    default -> "other";
};
```

In the first branch, the unguarded `String s` covers every string, so the guarded branch below can never be selected.

### 4.1. Guards Are Generally Not Used to Prove Dominance

The following example is accepted in Java 21:

```java
return switch (value) {
    case String s when s.length() >= 0 -> "first";
    case String s -> "fallback";
    default -> "other";
};
```

For an actual `String`, its length is always non-negative, so the fallback branch has no chance of running according to the logic of this expression. **Even so, the compiler does not infer or use the general semantics of `s.length() >= 0` to mark it dominated.** Dominance rules for guards are intentionally limited; not every condition that is "always true" is proven by the compiler.

### 4.2. Important Exception: `when true`

A guard that is a **constant expression with the value `true`** is treated like an unguarded branch in dominance analysis:

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case String s when true -> "string";
    case String s -> "again"; // ERROR dominated
    default -> "other";
};
```

`when true` makes the first branch cover every `String`. Conversely, `when false` with the constant value `false` is **forbidden at compile time** in Java 21 (a separate guard error), not a trick for temporarily disabling a branch.

### 4.3. Do Not Rely on the Compiler to Prove Disjointness

Two guards like `when n > 10` and `when n > 5` can both be true. When placed consecutively, the first branch takes precedence for all `n > 10`; the second branch handles the remaining values that satisfy the second condition. The compiler does not decide for you how value ranges should be partitioned according to business intent.

An easy-to-follow practical rule: **specific constants → specific guarded patterns → general unguarded patterns**. This is a code-ordering guideline for readability; whether dominance exists must still be evaluated according to the formal rules.

## 5. Constants, `null`, and `default`

Example with a selector of type `Integer`:

```java
static String numberKind(Integer value) {
    return switch (value) {
        case 0 -> "zero";
        case Integer i when i > 0 -> "positive";
        case Integer i -> "negative";
        case null -> "null integer";
    };
}
```

- `case 0` is placed first so it is not covered by `case Integer i`.
- `case Integer i when i > 0` handles the remaining positive numbers.
- The unguarded `case Integer i` handles the remaining non-`null` integers, which at this point are negative numbers.
- `case null` handles a `null` selector.

**`null` must be handled explicitly when required by the API.** A type pattern like `case Integer i` does not replace `case null`. If `switch` encounters `null` and has no matching branch, it normally throws `NullPointerException`; a standalone `default` does not automatically become a `null`-handling branch.

### 5.1. `default` and a Pattern Covering the Selector Type

When the selector is `Object`, an unguarded `case Object o` is an **unconditional** pattern for the selector type. If you also write `default`, the compiler will report an error:

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case Object o -> "something";
    default -> "other"; // ERROR: both an unconditional pattern and default
};
```

Here, the `Object o` pattern already plays the role of the default branch for non-`null` values. Choose one clean way to express this; do not stack two catch-all labels on top of each other. `case null` remains a separate label if you want to handle `null`.

In a structure with patterns, place `default` after the specific branches. Java 21 treats placing `default` before a pattern or a `null` label as an error; there are some compatibility exceptions for legacy `switch` statements containing only constants, but that is not appropriate style for pattern matching.

### 5.2. Do Not Confuse `switch` Errors

| Situation | Issue |
| --- | --- |
| `case Integer i` before `case 0` | The later constant is dominated |
| Two `case 0` labels with the same value | Duplicate constant error, independent of pattern dominance |
| `case Object o` and `default` in `switch(Object)` | Two catch-all branches |
| Duplicate `case null` | Duplicate `null` label error |
| `switch` expression omits remaining types | **Non-exhaustive** error, distinct from dominance |
| `case String s when false` | Constant `false` guard error, not the same as dominance |

## 6. Dominance for Record Patterns and Nested Patterns

Not only type patterns, but record patterns also participate in dominance. Consider:

```java
record Point(int x, int y) {}
record Holder(Point point) {}
```

A record pattern can deconstruct its components:

```java
case Point(var x, var y) -> ...
```

In dominance analysis, a **type pattern covering the record type** can dominate a record pattern. For two record patterns of **the same record class**, Java 21 also compares their **corresponding component patterns** for coverage (see JLS §14.30.3). This creates a recursive rule for nested records.

Intentionally incorrect example:

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case Holder(var p) -> "any Holder";
    case Holder(Point(var x, var y)) -> "Holder with Point"; // ERROR
    default -> "other";
};
```

Reason: for the `Holder` record, `var p` is a general component pattern for the `Point`-typed component. Whenever the nested `Point(var x, var y)` matches, that component is also accepted by `var p`. Thus, the preceding `Holder(var p)` shadows the nested branch below it.

Correct version:

```java
return switch (value) {
    case Holder(Point(var x, var y)) -> "Holder point";
    case Holder(var p) -> "Other Holder";
    default -> "other";
};
```

You can add `when` to classify more specifically:

```java
return switch (value) {
    case Holder(Point(var x, var y)) when x == y -> "diagonal";
    case Holder(Point(var x, var y)) -> "point";
    case Holder(var p) -> "holder without point";
    default -> "other";
};
```

Here `value` has type `Object`. If `value` is `new Holder(null)`, the nested `Point(...)` does not match `null`, whereas `Holder(var p)` can match with `p == null`. If the selector itself is `null`, no record pattern matches; to handle that separately, add `case null`.

### Dominance Does Not Mean "Every Record Pattern Is Unconditional"

A record pattern is not considered unconditional for the outer type in general, because `null` does not match a record pattern. However, a record pattern that is **broader in its components** can still dominate a narrower record pattern of the same record class. Distinguishing these two rules prevents confusion with the `default` branch.

## 7. Distinguishing Dominance from Exhaustiveness

**Dominance** asks: *Is any later branch guaranteed to be shadowed by an earlier branch?*  
**Exhaustiveness** asks: *Are there enough branches to handle all values in the selector type's domain that the compiler requires?*

A `switch` expression can be:

- **Not dominated, yet not exhaustive:** only `case String s` for an `Object` selector and missing `default`.
- **Exhaustive, yet dominated:** has `default`, but places `case CharSequence cs` before `case String s`; the compiler still rejects it.
- **Both exhaustive and not dominated:** properly orders specific branches, general branches, and handles `null` as required.

For a **sealed interface**, the compiler knows the list of permitted subtypes, so it can verify completeness without `default`:

```java
sealed interface Shape permits Circle, Square {}
record Circle(int radius) implements Shape {}
record Square(int side) implements Shape {}

static String shapeKind(Shape shape) {
    return switch (shape) {
        case Circle(var r) when r <= 0 -> "invalid circle";
        case Circle(var r) -> "circle: " + r;
        case Square(var s) -> "square: " + s;
        case null -> "null shape";
    };
}
```

The guarded `Circle(var r)` precedes the general `Circle` branch, so there is no dominance. Both subtypes `Circle` and `Square` are covered: the `switch` is exhaustive for the sealed type. No `default` is needed; `case null` is simply an explicit choice to handle `null`. If the sealed hierarchy is extended later, the compiler can help point out where a new case is needed.

### Dominance and Flow Scoping Are Two Different Layers of Checking

In `case Point(var x, var y) when x == y`, the variables `x`/`y` are in scope to be used in the branch's guard and body. This belongs to **flow scoping / pattern binding**. Dominance, on the other hand, determines **whether the entire `case` branch can ever be selected**. A pattern with valid variable bindings can still be dominated if placed below a broader covering pattern.

## 8. Complete Java 21 Program

Create the file **`DominanceAnalysisDemo.java`** with the following content; this is a standalone runnable program, unlike the intentionally broken snippets above:

```java
public class DominanceAnalysisDemo {
    record Point(int x, int y) {}
    record Holder(Point point) {}

    sealed interface Shape permits Circle, Square {}
    record Circle(int radius) implements Shape {}
    record Square(int side) implements Shape {}

    static String classify(Object value) {
        return switch (value) {
            case String s when s.isBlank() -> "blank string";
            case String s when s.length() > 3 -> "long string: " + s;
            case String s -> "string: " + s;
            case CharSequence cs -> "other CharSequence: " + cs.length();
            case Point(var x, var y) when x == y -> "diagonal: " + x;
            case Point(var x, var y) -> "point: " + x + "," + y;
            case Integer i -> "integer: " + i;
            case Number n -> "number: " + n;
            case null -> "null";
            default -> "other";
        };
    }

    static String numberKind(Integer value) {
        return switch (value) {
            case 0 -> "zero";
            case Integer i when i > 0 -> "positive";
            case Integer i -> "negative";
            case null -> "null integer";
        };
    }

    static String nested(Object value) {
        return switch (value) {
            case Holder(Point(var x, var y)) when x == y ->
                    "holder diagonal: " + x;
            case Holder(Point(var x, var y)) ->
                    "holder point: " + x + "," + y;
            case Holder(var p) -> "holder without point";
            case null -> "null holder";
            default -> "not holder";
        };
    }

    static String shapeKind(Shape shape) {
        return switch (shape) {
            case Circle(var radius) when radius <= 0 -> "invalid circle";
            case Circle(var radius) -> "circle: " + radius;
            case Square(var side) -> "square: " + side;
            case null -> "null shape";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("   "));
        System.out.println(classify("Java"));
        System.out.println(classify("hi"));
        System.out.println(classify(new StringBuilder("ab")));
        System.out.println(classify(new Point(2, 2)));
        System.out.println(classify(new Point(2, 5)));
        System.out.println(classify(7));
        System.out.println(classify(2.5));
        System.out.println(classify(null));
        System.out.println(classify(new Object()));

        System.out.println(numberKind(0));
        System.out.println(numberKind(8));
        System.out.println(numberKind(-3));
        System.out.println(numberKind(null));

        System.out.println(nested(new Holder(new Point(4, 4))));
        System.out.println(nested(new Holder(new Point(4, 5))));
        System.out.println(nested(new Holder(null)));
        System.out.println(nested("hello"));

        System.out.println(shapeKind(new Circle(3)));
        System.out.println(shapeKind(new Circle(0)));
        System.out.println(shapeKind(new Square(2)));
        System.out.println(shapeKind(null));
    }
}
```

Compile and run with JDK 21 or newer:

```bash
javac --release 21 DominanceAnalysisDemo.java
java DominanceAnalysisDemo
```

**Actual stdout output:**

```text
blank string
long string: Java
string: hi
other CharSequence: 2
diagonal: 2
point: 2,5
integer: 7
number: 2.5
null
other
zero
positive
negative
null integer
holder diagonal: 4
holder point: 4,5
holder without point
not holder
circle: 3
invalid circle
square: 2
null shape
```

Explanation of the output groups:

1. **`classify`:** guarded `String` branches precede the general `String` branch, followed by the supertype `CharSequence`. `Integer` precedes `Number`. Guarded `Point` patterns precede the general record branch. The program verifies valid pattern ordering across diverse inputs.
2. **`numberKind`:** `case 0` precedes pattern branches; the positive-number guard precedes the unguarded `Integer` branch; `null` is handled separately.
3. **`nested`:** guarded and unguarded nested `Point(...)` branches precede `Holder(var p)`. For `Holder(null)`, the nested branch does not match and the broader branch accepts the record.
4. **`shapeKind`:** the sealed hierarchy makes the switch expression exhaustive without `default`; the guarded `Circle` branch does not dominate the general `Circle` branch.

The entire program uses Java 21 and has no dependencies outside the JDK.

## 9. Dominance Errors Verified with `javac`

Code that fails to compile is a useful illustration for understanding compiler rules. The following examples are **intentionally incorrect** and should not be added to the runnable program in section 8.

### 9.1. Supertype Pattern Before Subtype Pattern

```java
// Selector is Object.
return switch (obj) {
    case CharSequence cs -> "wide";
    case String s -> "narrow"; // error: dominated
    default -> "other";
};
```

**Fix:** `String` before `CharSequence`.

### 9.2. Unguarded Branch Before Guarded Branch of the Same Type

```java
return switch (obj) {
    case String s -> "all strings";
    case String s when s.isBlank() -> "blank"; // error: dominated
    default -> "other";
};
```

**Fix:** the `when` branch before the unguarded `String s` branch.

### 9.3. Guard Is Constant `true`

```java
return switch (obj) {
    case String s when true -> "all strings";
    case String s -> "again"; // error: dominated
    default -> "other";
};
```

**Fix:** remove the redundant constant `true` guard, or remove the duplicate case. Do not confuse this with `when predicate(...)`: ordinary guards are not proven always-true by the compiler to mark later branches as dominated.

### 9.4. Constant After a Covering Pattern

```java
// Selector is Integer.
return switch (value) {
    case Integer i -> "any";
    case 0 -> "zero"; // error: dominated
    case null -> "null";
};
```

**Fix:** place `case 0` before `case Integer i`.

### 9.5. General Record Pattern Before Nested Pattern

```java
return switch (obj) {
    case Holder(var p) -> "any holder";
    case Holder(Point(var x, var y)) -> "point holder"; // error
    default -> "other";
};
```

**Fix:** nested `Holder(Point(...))` before `Holder(var p)`.

### 9.6. `default` After an Unconditional Pattern

```java
return switch (obj) {
    case Object o -> "anything";
    default -> "other"; // error: already has an unconditional pattern
};
```

**Fix:** choose one appropriate way to represent the general case; if you need to catch `null` separately, use `case null`.

With JDK 21, the first five cases all produce a diagnostic of the form `this case label is dominated by a preceding case label`. The last case produces the diagnostic `switch has both an unconditional pattern and a default label`. Exact diagnostic wording may vary across `javac` versions/distributions, but the language rules remain the same.

## 10. How to Read and Resolve Dominance Errors

When the compiler reports a dominated case:

1. **Identify the selector type:** such as `Object`, `Integer`, a sealed interface, or a record.
2. **Locate the reported case:** note the pattern type, whether it has a guard, and its record/component structure.
3. **Compare preceding cases:** is there an unguarded preceding case that accepts every value the current case can accept?
4. **Check subtype and component relationships:** `CharSequence` covers `String`, `Number` covers `Integer`; `Holder(var p)` is broader than `Holder(Point(...))`.
5. **Inspect constant and guarded branches:** constants should generally precede covering pattern branches; `when true` acts like unguarded, while normal guards do not make the compiler solve arbitrary business conditions.
6. **Reorder or split conditions:** place narrower branches before broader ones, avoid duplicate cases; if multiple cases should produce the same result, consider combining them.
7. **Recompile and verify output:** test inputs that distinguish narrow branches, wide branches, true/false guard data, and `null`.

### Common Misconceptions to Avoid

- **Assuming dominance occurs whenever two cases merely "can" both match.** Partial overlap is not always dominance. For example, `String` and `CharSequence` overlap, yet placing `String` before `CharSequence` is valid because the narrower type does not cover the entire broader type.
- **Confusing it with ordinary unreachable statements.** Dominance is a rule for `switch` labels based on patterns and coverage; flow analysis for unreachable statements has its own rules.
- **Assuming the compiler analyzes every `when` clause.** Aside from the specified constant `true` case, do not expect it to solve the semantics of business predicates.
- **Thinking `when false` can be used to temporarily disable a case.** A guard that is the constant expression `false` is rejected at compile time in Java 21.
- **Confusing `default` with `case null`.** `null` is handled under separate rules; a type pattern does not automatically match `null` at the top level.
- **Equating dominance with exhaustiveness.** Having no dominated branches does not guarantee that the `switch` covers all possible value types.
- **Forgetting nested record patterns.** A record pattern that is broad in its components can shadow a narrower nested pattern after it.
- **Fixing by replacing an arbitrary guard with `when true`.** Doing so removes the classification logic and can immediately cause dominance.

### Design Principle for Readability

Order branches by specificity so readers see it immediately: **special constants → guarded type/record patterns → specific unguarded type/record patterns → supertype/general patterns → `default`**. Not every `switch` needs all of these groups. If using a sealed hierarchy and all subtypes are covered, `default` is unnecessary; when handling `null` per business logic, add `case null` as appropriate.

## 11. Self-Check Questions and Exercises

**1.** With an `Object` selector, why is `case CharSequence cs` before `case String s` an error?  
*Answer:* Every `String` is also a `CharSequence`; the preceding unguarded case covers the later case.

**2.** Does every pair of cases that can match the same value cause dominance?  
*Answer:* No. `case String s` before `case CharSequence cs` is valid; the first branch does not cover every `CharSequence`.

**3.** Why is `case String s when s.isBlank()` before `case String s` valid?  
*Answer:* The guarded branch selects only a subset of values; the unguarded branch handles the remaining values of the same type.

**4.** Does `when true` behave differently from a normal guard in dominance?  
*Answer:* Yes. A constant guard `true` is treated as unguarded, so it can dominate a later case of the same type.

**5.** In `switch(Integer)`, should `case 0` be placed before or after `case Integer i`?  
*Answer:* Before. An unguarded `Integer i` pattern would cover the constant `0` if placed first.

**6.** Can `case Holder(var p)` be placed before `case Holder(Point(var x, var y))`?  
*Answer:* No. The `var p` component covers every case that the nested `Point(...)` matches, so the later case is dominated.

**7.** Does a switch expression that handles all `Circle` and `Square` subtypes of a sealed interface always need `default`?  
*Answer:* No. If the compiler proves all subtypes are covered, the switch is exhaustive without `default`. `null` is handled separately if you want to return a result for null input.

**8.** If there are no dominated cases, but a switch expression on `Object` only contains `case String s`, what happens?  
*Answer:* The compiler reports a non-exhaustive error because non-`String` values still have no branch.

**9.** Should you replace all `when condition` guards with `when true` to make compiler checking easier?  
*Answer:* No. That removes the branch's condition, can shadow later cases, and changes business behavior.

## References

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS Java SE 21 §14.11.1 — Switch Blocks, Dominance and Exhaustiveness](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [JLS Java SE 21 §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
