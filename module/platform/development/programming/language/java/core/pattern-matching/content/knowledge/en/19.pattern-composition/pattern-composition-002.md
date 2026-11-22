# Combining Patterns with Negation in Java 21

## 1. Lesson Objectives

**Pattern matching** checks the shape/type of a value and, when it matches, binds the needed components into pattern variables. The **negation** operator `!`, on the other hand, operates on a boolean result. When combining them, the most important thing is to distinguish **which branch proves that the pattern matched** from **which branch only knows that the pattern did not match**. That distinction determines the valid scope of pattern variables and the safety of combined `&&` and `||` expressions.

After this lesson, you will be able to:

- Write conditions like `!(value instanceof String s)`, negate a **record pattern**, and apply guard clauses (early return).
- Understand **flow scoping**: why `s` can sometimes be used after an `if` statement or on the right-hand side of `||`, while at other times the compiler reports that the variable cannot be found.
- Combine `!`, `&&`, and `||` with additional conditions, apply De Morgan's laws, and avoid `NullPointerException`.
- Use negation inside **`when` guards** of pattern `switch`, while understanding that `case !Pattern` is not valid Java 21 pattern syntax.
- Distinguish between `null` input, a nested record containing `null`, a pattern mismatch, and a failed guard condition.

**Version:** Type patterns with `instanceof` have been stable since Java 16 (JEP 394). Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) were finalized in **Java 21**. This lesson uses JDK 21+ and does not require enabling preview features.

## 2. Negating a Pattern Means Negating the *Match Result*

A pattern can be tested using the `instanceof` operator:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

The condition `value instanceof String text` has two related meanings: the value actually matches the `String` type, and when it succeeds, the pattern variable `text` is bound to that value.

Place `!` outside the `instanceof` expression to invert the boolean:

```java
Object value = 42;
if (!(value instanceof String text)) {
    System.out.println("Khong phai String");
}
```

The negated expression evaluates to `true` when `value` is not a `String` **or is `null`**. However, in the true branch of the negated condition, **`text` is not guaranteed to have a value**, so it cannot be used there. `!` does not turn a "String pattern" into a negative pattern type with its own variable; it simply inverts the check result.

You can visualize this as follows:

| `value` | `value instanceof String text` | `!(value instanceof String text)` | Where can `text` be used? |
| --- | --- | --- | --- |
| `"Hi"` | `true`, binds `text` | `false` | The branch after the pattern is proven true |
| `123` | `false` | `true` | Cannot use `text` from the negated branch alone |
| `null` | `false` | `true` | Cannot use `text` from the negated branch alone |

**Correct syntax:** `!(value instanceof String text)`. Writing `!value instanceof String text` is wrong because `!` only accepts a boolean expression and cannot directly negate an `Object` variable that way.

## 3. Flow Scoping: Pattern Variables Depend on Program Control Flow

Unlike regular locally declared variables, the scope of a pattern variable is determined by the compiler based on **the execution paths where the pattern is guaranteed to have matched**.

### 3.1. Negation + Early Exit Branch

This is the most common usage:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "not a String";
    }
    // At this point, it can only be the case where String matched.
    return text.trim().toUpperCase();
}
```

When the `if` branch runs, the method returns. If execution reaches the line after the `if`, the `!(...)` condition must be `false`, meaning `value instanceof String text` was `true`. Therefore, **`text` is in valid scope after the `if`**.

Similarly, you can use `throw` in the non-matching branch:

```java
if (!(value instanceof String text)) {
    throw new IllegalArgumentException("Expected String");
}
System.out.println(text.length());
```

The snippets above are examples inside a method body. They illustrate the **guard clause** idea: handle the rejected case first so the rest does not need to be deeply nested inside a positive branch.

### 3.2. Using `else`

Returning immediately is not mandatory. If you use `else`, the pattern variable is also guaranteed to be bound in that branch:

```java
if (!(value instanceof String text)) {
    System.out.println("Different type or null");
} else {
    System.out.println(text.length());
}
```

The `else` branch only runs when the negation is `false`, meaning the actual match succeeded.

### 3.3. Invalid Positions

The following snippets **intentionally contain compilation errors**:

```java
// WRONG: the true branch of !(...) does not guarantee that text exists.
if (!(value instanceof String text)) {
    System.out.println(text.length());
}

// WRONG: the true left-hand side of || does not guarantee that text is bound.
if (value instanceof String text || text.isBlank()) {
    // ...
}

// WRONG: the true left-hand side of && is the case where the pattern did not match.
if (!(value instanceof String text) && text.isBlank()) {
    // ...
}
```

The compiler usually reports that `text` cannot be found at the invalid usage site. The real issue lies in the **flow of information about the pattern**, not just parentheses or declaration placement.

## 4. Combining Negation with `&&` and `||`

Java evaluates `&&` and `||` from left to right using **short-circuit** rules:

- `a && b`: evaluates `b` only if `a` is `true`.
- `a || b`: evaluates `b` only if `a` is `false`.

Thanks to this, you can validly write conditions that use a pattern variable when the execution path leading to the right-hand side has proven that the pattern matched.

### 4.1. Positive Pattern with `&&`

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
```

The right-hand side only runs if `value instanceof String text` is `true`. `text` already exists and is non-`null`, so `text.isBlank()` is safe.

### 4.2. Negated Pattern with `||`

```java
if (!(value instanceof String text) || text.isBlank()) {
    return "invalid";
}
return text.trim();
```

The right-hand side `text.isBlank()` only runs when `!(value instanceof String text)` is `false`, meaning the positive pattern matched. Because the `if` branch always returns when the condition is true, the code after `if` knows that `text` is a non-blank `String`.

A practical example with multiple criteria:

```java
record User(String name, int age) {}

static String check(Object value) {
    if (!(value instanceof User(String name, int age))
            || name.isBlank()
            || age < 18) {
        return "not eligible";
    }
    return "eligible: " + name;
}
```

- If `value` is not a `User`, or the `name` component is `null` so the nested `String name` does not match, the first operand is `true` and the remaining operands **do not run**.
- If the match succeeds, `name` and `age` are bound, so the additional conditions can run safely.
- If not rejected, the pattern variables remain usable after the `if` statement.

### 4.3. Condition Combination Check Table

| Condition | Use pattern variable on the right-hand side? | Reason |
| --- | --- | --- |
| `value instanceof String s && !s.isBlank()` | Yes | Right-hand side only runs after a successful match |
| `!(value instanceof String s) &#124;&#124; s.isBlank()` | Yes | Right-hand side only runs when the negation is false, meaning the match succeeded |
| `value instanceof String s &#124;&#124; s.isBlank()` | No | When the right-hand side runs, the match has failed |
| `!(value instanceof String s) && s.isBlank()` | No | When the right-hand side runs, the match has failed |

**Important:** Do not arbitrarily flip an operator while keeping the right-hand side unchanged. Before using a pattern variable, ask: *does every path reaching this expression guarantee that the original pattern has matched?*

## 5. Negating Record Patterns and Nested Patterns

Java 21 allows deconstructing record components directly in a pattern:

```java
record Point(int x, int y) {}

Object value = new Point(-1, 3);
if (!(value instanceof Point(var x, var y))) {
    // value does not match Point (or value is null).
    return;
}
// x and y can be used here.
System.out.println(x + "," + y);
```

The snippet above only illustrates this inside a `void`-returning method. `!` negates the **entire** match operation, including both the condition that the object is a `Point` record and the deconstruction of its components. If `value` is a `Point`, the negated expression is `false` and `x`/`y` are usable after the `return` branch.

With a nested record:

```java
record Segment(Point start, Point end) {}

if (!(value instanceof Segment(
        Point(var x1, var y1),
        Point(var x2, var y2)))) {
    return "not a complete Segment";
}
return x1 + "," + y1 + " -> " + x2 + "," + y2;
```

The snippet above illustrates this inside a `String`-returning method with a `value` variable of a suitable type, such as `Object`. The match fails if:

1. `value` is not a `Segment`, or `value == null`.
2. `start` or `end` is `null`, so the corresponding nested `Point(...)` pattern does not match.
3. A nested component does not satisfy the written pattern.

The negated branch handles all non-matching cases together. Only when the record and both nested `Point`s have matched successfully can the four variables `x1`, `y1`, `x2`, `y2` be used to build the result.

You must distinguish **a record pattern mismatch** from **a record that matches but whose data fails a business condition**. For example, `Point(-1, 3)` still **matches** `Point(var x, var y)`; checking for negative coordinates must be done afterward or in a `when` guard.

## 6. The `!` Operator in Pattern `switch` with `when`

Java 21 supports pattern matching for `switch` and the `when` clause to add a boolean condition after a pattern has matched:

```java
return switch (value) {
    case Point(var x, var y) when !(x >= 0 && y >= 0) ->
            "point outside quadrant";
    case Point(var x, var y) ->
            "point inside quadrant";
    case null -> "null";
    default -> "other";
};
```

Meaning:

- `case Point(var x, var y)` extracts the coordinates first.
- `when !(x >= 0 && y >= 0)` negates the **coordinate condition**, not the `Point` type.
- If it is a `Point` whose first guard evaluates to false, the more general `Point` branch below still gets a chance to match.
- `case null` handles a `null` input object; `default` does not automatically replace the `null` branch under the standard pattern `switch` rules.

An example with `String`:

```java
return switch (value) {
    case String text when !text.isBlank() -> "nonblank";
    case String text -> "blank";
    case null -> "null";
    default -> "other";
};
```

Here `!text.isBlank()` is valid because the `when` guard is only evaluated **after** `case String text` matches successfully. Placing the general `case String text` branch first would cause the more specific branch below it to be dominated.

**There is no `case !Point(...)` or `case !(String s)` syntax to create a "negative type pattern" in Java 21.** To handle values that are not of a certain type, you typically use a `default` branch (and a `null` branch if needed) or an outer `if (!(value instanceof ...))`. Use `when !condition` when you want to negate **a property of the matched value**.

## 7. Complete Java 21 Program

Create the file **`NegatedPatternDemo.java`** as follows. The program combines negating type patterns, record patterns, nested record patterns, additional conditions, and pattern `switch` in a single practice exercise.

```java
import java.util.Locale;

public class NegatedPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record User(String name, int age) {}

    static String inspectText(Object value) {
        if (!(value instanceof String text)) {
            return "not a String";
        }
        if (text.isBlank()) {
            return "blank";
        }
        return "text: " + text.trim().toUpperCase(Locale.ROOT);
    }

    static String eligible(Object value) {
        if (!(value instanceof User(String name, int age))
                || name.isBlank()
                || age < 18) {
            return "not eligible";
        }
        return "eligible: " + name;
    }

    static String inspectPoint(Object value) {
        if (!(value instanceof Point(var x, var y))) {
            return "not a Point";
        }
        if (x < 0 || y < 0) {
            return "negative coordinate";
        }
        return "point=" + x + "," + y;
    }

    static String segmentInfo(Object value) {
        if (!(value instanceof Segment(
                Point(var x1, var y1),
                Point(var x2, var y2)))) {
            return "not a complete Segment";
        }
        return x1 + "," + y1 + " -> " + x2 + "," + y2;
    }

    static String classify(Object value) {
        return switch (value) {
            case Point(var x, var y) when !(x >= 0 && y >= 0) ->
                    "point outside quadrant";
            case Point(var x, var y) -> "point inside quadrant";
            case String s when !s.isBlank() -> "nonblank string";
            case String s -> "blank string";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspectText(null));
        System.out.println(inspectText("  java  "));
        System.out.println(inspectText("  "));

        System.out.println(eligible(new User("An", 20)));
        System.out.println(eligible(new User("", 20)));
        System.out.println(eligible("other"));

        System.out.println(inspectPoint(new Point(-1, 3)));
        System.out.println(inspectPoint(new Point(2, 3)));

        System.out.println(segmentInfo(new Segment(
                new Point(1, 2), new Point(5, 6))));
        System.out.println(segmentInfo(new Segment(
                null, new Point(5, 6))));

        System.out.println(classify(new Point(-1, 2)));
        System.out.println(classify(new Point(1, 2)));
        System.out.println(classify("hi"));
        System.out.println(classify(""));
        System.out.println(classify(null));
    }
}
```

Compile and run on JDK 21 or newer:

```bash
javac --release 21 NegatedPatternDemo.java
java NegatedPatternDemo
```

**Actual output:**

```text
not a String
text: JAVA
blank
eligible: An
not eligible
not eligible
negative coordinate
point=2,3
1,2 -> 5,6
not a complete Segment
point outside quadrant
point inside quadrant
nonblank string
blank string
null
```

Analysis:

1. `inspectText(null)` returns `"not a String"` because `instanceof` on `null` is `false`; negation turns the result into `true`.
2. For `"  java  "`, the `String text` pattern matches; `text` remains accessible after the `return` branch for the non-matching case.
3. `eligible` uses `||` in order: if not a `User`, it returns immediately; only when matched does it use `name.isBlank()` and `age < 18`. There is no pattern variable access error.
4. `inspectPoint(new Point(-1, 3))` does not enter the negated type pattern branch because the object is actually a `Point`; the `"negative coordinate"` result comes from the separate data check.
5. `segmentInfo` returns `"not a complete Segment"` for `Segment(null, ...)` because the nested `Point(...)` does not match the `null` component.
6. `classify` shows that `when !(...)` is suitable when you need to negate a coordinate condition or `!s.isBlank()`, then fall through to the general pattern for the remaining cases.
7. The program runs entirely using finalized Java 21 code, with no preview flags required.

## 8. De Morgan's Laws and Readable Code

When a negated expression consists of multiple conditions, two useful logical laws are:

```text
!(A && B)  ==  !A || !B
!(A || B)  ==  !A && !B
```

Example with coordinates:

```java
!(x >= 0 && y >= 0)
```

is equivalent to:

```java
x < 0 || y < 0
```

Both expressions identify a point outside the quadrant where both coordinates are non-negative (assuming `x` and `y` are `int`). In real-world code, `x < 0 || y < 0` is usually more direct and easier to read; the negated form is useful when expressing "does not satisfy the entire rule."

However, **De Morgan's laws apply to boolean expressions, not pattern variable syntax**. Flipping part of a condition from `true` to `false` can change the point at which a variable is guaranteed to be bound. For example, both of the following forms are valid because they still check the type before calling `isBlank()`:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}

if (!(value instanceof String text) || text.isBlank()) {
    return;
}
// text is bound and non-blank.
System.out.println(text);
```

The second snippet illustrates this inside a `void`-returning method; you cannot simply change `&&` to `||` and ignore the negation logic and variable accessibility. For checks with side effects, keep the order and short-circuit structure clear.

## 9. Common Mistakes and How to Fix Them

### Mistake 1: Accessing a variable in the failed-match branch

Wrong:

```java
if (!(value instanceof String text)) {
    System.out.println(text.length()); // does not compile
}
```

Fix: handle the failed case and `return`/`throw`, or use `text` inside the `else` branch.

### Mistake 2: Using `||` after a positive pattern

Wrong:

```java
if (value instanceof String text || text.isBlank()) {
    // does not compile because text is not guaranteed to be bound on the right-hand side
}
```

Fix according to your goal: if you want to accept a non-blank string, use `value instanceof String text && !text.isBlank()`. If you want to reject non-strings or blank strings, use `!(value instanceof String text) || text.isBlank()`.

### Mistake 3: Confusing `null` with a negated pattern

`null instanceof String` and `null instanceof Point` are both `false`; `!(...)` is therefore `true`. If `null` has a distinct business meaning, handle it in an early branch or use `case null` in `switch`.

### Mistake 4: Treating negation of a nested pattern as negation of a single component

`!(value instanceof Segment(Point(...), Point(...)))` negates the entire match. It can fail because the outer object has the wrong type, because a component is `null`, or because a nested pattern does not match. If you need precise error messages for each case, split it into smaller checks.

### Mistake 5: Using negation as a standalone `case`

Writing `case !String s` or `case !Point(...)` is not valid Java 21 pattern syntax. Use `default`/`case null` for other object types and `when !predicate` for negated properties of a matched object.

### Mistake 6: Wrong order of `switch` branches

Placing `case String s` before `case String s when !s.isBlank()` makes the guarded branch unreachable due to dominance rules. Put the specific case first and the general case after.

### Mistake 7: Assuming pattern matching mutates data

`instanceof`, record patterns, and negation `!` only control execution flow and extract values; they do not automatically convert, copy, or make objects immutable. When a component is a mutable array/`List`, the pattern variable may reference that same object. If immutability is needed, design the record and defensive copies appropriately.

## 10. When Should You Use Negation?

- **Guard clauses**: use `if (!(input instanceof ExpectedType matched)) return ...;` to handle invalid input and keep the main logic less nested.
- **Exclusion rules**: use `||` and negated patterns to reject any case that fails type, format, or permission checks, in a safe evaluation order.
- **Nested records**: negate the entire record pattern when you only need to distinguish "valid structure" from "other structure"; split into multiple branches if per-component diagnostics are needed.
- **Pattern `switch`**: use `when !predicate` to define a special subset of data within a matched type, followed by a general branch.
- **Simple expressions**: if you only need to check a value like `x < 0`, write it directly; do not add patterns or negation layers if they do not improve clarity.

## 11. Self-Check Questions

1. **When `obj == null`, what is `!(obj instanceof String s)`?**  
   It is `true` because `instanceof` does not match `null`.

2. **Why can `s` appear after `if (!(obj instanceof String s)) return;`?**  
   Only the execution path where `instanceof` matched gets past the `return` statement.

3. **Why does `if (!(obj instanceof String s) && s.isBlank())` fail to compile?**  
   The right-hand side only runs when the pattern has failed; `s` is not guaranteed to be bound.

4. **If `value` is `Point(-2, 3)`, what is `!(value instanceof Point(var x, var y))`?**  
   It is `false`. The object matches the `Point` type; negative coordinates do not cause the pattern to fail.

5. **What does `when !(x >= 0 && y >= 0)` in `case Point(var x, var y)` check?**  
   After matching `Point`, the guard selects cases where at least one coordinate is negative.

6. **Can you use `case !(String s)` in Java 21?**  
   No. `!` is used in boolean expressions, such as a `when` guard, not as a standalone negated pattern form.

7. **Why does `Segment(Point(...), Point(...))` not match `Segment(null, new Point(1,2))`?**  
   The nested `Point(...)` does not match a `null` component.

## References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 Language Specification §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
- [Java SE 21 Language Specification §15.20.2 — Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
