# Record Patterns in `switch` `case` Labels (Java 21)

## 1. What Problem Does a Record Pattern in `case` Solve?

A `record` groups named data components with defined types. For example, `record Point(int x, int y) {}` represents a point with two components `x` and `y`.

When handling an object in a `switch`, there are two approaches:

```java
// Type pattern: take the whole object, then call accessors.
case Point p -> "x=" + p.x() + ", y=" + p.y();

// Record pattern: check Point and extract its components right in the case.
case Point(int x, int y) -> "x=" + x + ", y=" + y;
```

These two lines are **two separate illustrative branches**; do not place them together in the same `switch` because a more general branch placed first can dominate the later branch.

With the **record pattern** `Point(int x, int y)`, Java:

1. Checks whether the value being tested matches the `Point` record type.
2. Retrieves the record components through their corresponding accessors (`x()`, `y()`).
3. Matches each component against the declared nested pattern.
4. If everything matches, binds the pattern variables `x`, `y` and executes the corresponding `case` branch.

Therefore, record patterns let you write the **data structure to match** directly in the `case` label, instead of receiving the entire record and extracting its fields with multiple statements.

**Version:** Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) were both finalized in **Java 21**. The `case Point(...)` examples in this article require Java 21 or later as the language level and do not need `--enable-preview` when compiled with `--release 21`. Java 17 has records and pattern matching for `instanceof`, but does not yet provide stable support for record pattern syntax in `case`.

## 2. Syntax and Components of the `case` Label

Consider the record:

```java
record Point(int x, int y) {}
```

A `switch` branch using a record pattern:

```java
case Point(int x, int y) -> System.out.println(x + y);
```

General syntax:

```text
case RecordType(componentPattern1, componentPattern2, ...)
    [when booleanCondition] -> expression-or-statement
```

Where:

- `RecordType` must refer to a **record type**, such as `Point`; Java does not allow this deconstruction syntax for an ordinary Java class that merely has getters.
- The component pattern list is inside `(...)` and must have the **exact number of components in the exact order** matching the record declaration; a record with no components uses the pattern `Empty()`.
- `int x`, `int y` are **nested patterns** (component patterns): when matched, they declare the variables `x`, `y` for the selected branch.
- `when booleanCondition` is an optional **guard**, evaluated after the record pattern matches; the guard can use the newly bound variables.
- `->` specifies what is executed/returned when the branch is selected. In a `switch` expression, the branch can yield a value; in a `switch` statement, the branch can execute a statement or block.

Example of a properly placed guard:

```java
case Point(int x, int y) when x == y -> "Điểm nằm trên đường y=x";
```

Do not place `when` between component patterns or before `Point(...)`. The correct syntax is **`case <pattern> when <condition> ->`**.

### Using `var` to Infer Component Types

With `record Point(int x, int y) {}`, you can write:

```java
case Point(var x, var y) -> "Point: " + x + "," + y;
```

Here `x` and `y` are inferred to have type `int` from the corresponding components of `Point`. `var` **does not turn the variables into `Object`**; the compiler knows the types from the record declaration.

Use `var` when there is no need to repeat already-clear type names. Write explicit types when they help readers understand the structure or make instructional examples clearer.

## 3. Standalone Java 21 Example: `case`, `when`, and Nested Records

Create the file **`RecordPatternCaseDemo.java`**:

```java
public class RecordPatternCaseDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record NamedPoint(Point point, String label) {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";

            case Point(int x, int y) when x == y ->
                "DIAGONAL " + x;

            case Point(int x, int y) ->
                "POINT " + x + "," + y;

            case Segment(
                    Point(int sx, int sy),
                    Point(int ex, int ey)) ->
                "SEGMENT (" + sx + "," + sy
                    + ")->(" + ex + "," + ey + ")";

            case NamedPoint(Point(int x, int y), String label)
                    when label != null && !label.isBlank() ->
                "NAMED " + label + " @ " + x + "," + y;

            case NamedPoint(var point, var label) ->
                "UNNAMED";

            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Object[] values = {
            new Point(2, 2),
            new Point(2, 3),
            new Segment(new Point(0, 1), new Point(2, 4)),
            new NamedPoint(new Point(3, 4), "A"),
            new NamedPoint(new Point(3, 4), null),
            new NamedPoint(null, "B"),
            null,
            "hello"
        };

        for (Object value : values) {
            System.out.println(describe(value));
        }
    }
}
```

Compile with **JDK 21 or later** targeting the Java 21 source level:

```bash
javac --release 21 RecordPatternCaseDemo.java
java RecordPatternCaseDemo
```

Stdout output:

```text
DIAGONAL 2
POINT 2,3
SEGMENT (0,1)->(2,4)
NAMED A @ 3,4
UNNAMED
UNNAMED
NULL
OTHER
```

Why each branch is selected:

1. `Point(2, 2)` matches `Point(int x, int y)` and the guard `x == y` is true, so it returns `DIAGONAL 2`.
2. `Point(2, 3)` also matches the `Point` record, but the guard `x == y` is false. Java evaluates the next branch `case Point(int x, int y)` and returns `POINT 2,3`.
3. `Segment(Point(0, 1), Point(2, 4))` matches the **nested record pattern**, extracting the four variables `sx`, `sy`, `ex`, `ey`.
4. `NamedPoint(Point(3, 4), "A")` matches the nested record, and the guard confirms the label is non-`null` and not blank, so it returns `NAMED A @ 3,4`.
5. `NamedPoint(Point(3, 4), null)` fails the guard because `label == null`; the `NamedPoint(var point, var label)` branch catches the remaining case.
6. `NamedPoint(null, "B")` does not match the nested pattern `Point(int x, int y)` because the `point` component is `null`; the `NamedPoint(var point, var label)` branch still matches.
7. A selector value of `null` is handled by `case null`.
8. The string `"hello"` is not a `Point`, `Segment`, or `NamedPoint`, so it falls into `default`.

Here the entire `switch` is **an expression** returning a `String`. Each `->` branch provides a result string. The `switch` has a `default` because the `Object` input can be of many types beyond the declared records.

## 4. Deconstructing Record Components: Matching Mechanism and Pattern Variables

Compare two ways of checking a `Point`.

**Type pattern:**

```java
case Point point -> "x=" + point.x() + ", y=" + point.y();
```

**Record pattern:**

```java
case Point(int x, int y) -> "x=" + x + ", y=" + y;
```

Both match a `Point` value, but the record pattern also requires the **component patterns** to match and directly declares the variables `x`, `y`. This construct is very useful when a record is purely a data carrier and you want to work with its components immediately.

A record pattern is not a constructor call `new Point(...)`: it **deconstructs an existing value** by retrieving the corresponding components via accessors. Nor does it create a new `Point`.

Pattern variables are scoped to the selected case. In the expression:

```java
return switch (value) {
    case Point(int x, int y) when x > 0 && y > 0 ->
        "Quadrant I";
    case Point(int x, int y) ->
        "Other point";
    default ->
        "Not a point";
};
```

The variables `x`, `y` in the first branch and the second branch are **two distinct sets of pattern variables**; reusing the names is allowed because the rule scopes do not overlap. The first branch's guard can use `x`, `y`. In the `default` branch, these variables do not exist.

**Note:** the snippet above illustrates the **body of a method returning `String`** that has a parameter or variable `value`; it is not a standalone Java program.

## 5. Nested Record Patterns: Matching Multi-Level Structures

A record can contain another record:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
```

If you only write a type pattern:

```java
case Segment segment ->
    segment.start().x() + "," + segment.end().y();
```

You receive the whole `segment` and call the accessors yourself.

With a nested record pattern:

```java
case Segment(Point(int sx, int sy), Point(int ex, int ey)) ->
    sx + "," + sy + " -> " + ex + "," + ey;
```

Java checks `Segment`, retrieves `start` and `end`, and then continues matching them as `Point`. Only when **all nested patterns match** is the branch selected and the component variables made available in the branch body.

If `start` or `end` is `null`, the nested pattern `Point(int ..., int ...)` **does not match**. This `case Segment(...)` branch is skipped and the program looks for another matching `case` branch, such as `case Segment(var start, var end)` or `default`. This does not mean Java automatically invokes `start.x()` on a `null` value.

Deconstructing two or three levels is reasonable when it helps reveal the meaning of the data. For very deep records, a few temporary names or a dedicated helper method may be easier to read than a pattern nested with too many parentheses.

## 6. `when` Guards Filter After a Pattern Matches

A record pattern describes the **shape and data types**. A `when` guard adds a logical condition on the extracted components:

```java
return switch (value) {
    case Point(int x, int y) when x == 0 && y == 0 ->
        "Origin";
    case Point(int x, int y) when x >= 0 && y >= 0 ->
        "Nonnegative quadrant";
    case Point(int x, int y) ->
        "Other point";
    default ->
        "Not a point";
};
```

Examples:
- `Point(0, 0)` returns `Origin`.
- `Point(2, 3)` returns `Nonnegative quadrant`.
- `Point(-1, 3)` returns `Other point`.

These are three sample branches for the same record type with conditions ordered from specific to general. A guard **does not alter the record definition**, does not cast types, and does not mutate components. It only decides whether to accept the current `case` label or move on to evaluate the next branch.

With `when x > 0 && y > 0`, the condition is evaluated according to normal Java rules; if a guard calls a method with side effects, that call can actually run. Record matching can also invoke the record's accessors. Therefore, you should not assume that expressions involved in a pattern "never execute code".

**Branch ordering is especially important.** If you place an unguarded pattern that is general enough to match every `Point` **before** a guarded `Point` branch, the later branch may be rejected by the compiler as being covered by the earlier branch (*dominated case label*).

## 7. `null`: Selector and Record Components Do Not Follow the Same Rules

This is an easy point of confusion in Java 21 record patterns.

### `null` Selector

`null` itself **does not match a record pattern**:

```java
switch (value) {
    case null -> System.out.println("No value");
    case Point(int x, int y) -> System.out.println(x + y);
    default -> System.out.println("Other");
}
```

This is an illustrative snippet inside a method with `value`. If `value == null`, only the `case null` branch is selected. If `null` handling is omitted, a typical pattern `switch` with a `null` selector can throw `NullPointerException` **before** reaching `default`; `default` does not automatically replace `case null`.

### Record Components Can Be `null`

Suppose:

```java
record NamedPoint(Point point, String label) {}
```

When writing:

```java
case NamedPoint(Point(int x, int y), String label)
        when label != null && !label.isBlank() -> ...
```

There are **two different kinds of nested patterns**:

- `Point(int x, int y)` is a **nested record pattern**. It **does not match `null`** for the `point` component.
- `String label` is a **direct type pattern for the `String` component**. In Java 21, because it is an *unconditional* pattern for the component's declared type `String`, it falls under the **null-matching component pattern** case: it **can bind `label = null`**. That is why the guard must check `label != null` before calling `label.isBlank()`.

This differs from `object instanceof String s` at the top level, where `object == null` always makes `instanceof` return `false`. Do not take the `instanceof` rule for a `null` selector and apply it to every **component pattern** inside a record.

A fallback using `var` can also accept `null` component values when it is an unconditional type pattern for the component's type:

```java
case NamedPoint(var point, var label) -> "Incomplete";
```

In the standalone example above, this branch handles both records with a `null` label and records with a `null` point. If you do not want to allow null components, validate the values in the record's constructor or handle them explicitly in `case` branches.

## 8. Exhaustiveness of `switch` and Record Patterns

### `switch` Expressions Must Cover All Cases

A `switch` expression must be **exhaustive**: the compiler needs to see that all possible selector values are handled. With an `Object` selector, `default` is typically used:

```java
return switch (value) {
    case Point(int x, int y) -> "Point";
    default -> "Something else";
};
```

This snippet handles non-`Point` types via `default`, though if `value` is `null` you still need to consider `case null` as explained above.

### Exhaustiveness Without `default` When Using `sealed`

Advanced Java 21 example—place the following declarations in the same file (each record is a permitted subtype of the sealed interface):

```java
sealed interface Expr permits Literal, Sum {}
record Literal(int value) implements Expr {}
record Sum(Expr left, Expr right) implements Expr {}

static int evaluate(Expr expr) {
    return switch (expr) {
        case Literal(int value) -> value;
        case Sum(var left, var right) ->
            evaluate(left) + evaluate(right);
    };
}
```

The `evaluate` method needs to be **placed inside an enclosing class**, with the corresponding type declarations in a scope permitted by Java; this code illustrates the relationship between sealed types and record patterns, not a standalone file like the program in Section 3.

With the classes currently permitted by `Expr`, the compiler can prove that the record cases cover every valid **non-`null`** implementation type. Calling `evaluate(null)` can still lead to a `NullPointerException` from the `null` selector; if a `left`/`right` component is `null`, the recursive call must also be handled according to the data contract. Do not confuse "exhaustive over types" with "no need to care about `null` in data".

## 9. Common Mistakes When Writing Record Patterns in `case`

| Mistake or misconception | Example / cause | How to fix |
| --- | --- | --- |
| Using Java 17 as if Java 21 support were available | `case Point(int x, int y) ->` at Java 17 source level | Raise the language level to Java 21+ or use `case Point p ->` according to version-appropriate pattern switch support |
| Wrong number of components | `Point(int x)` for `record Point(int x, int y)` | Provide exactly two component patterns, in declaration order |
| Incompatible component type | `Point(String x, int y)` when the record's `x` is `int` | Use `int x` or `var x` |
| Using deconstruction on a regular class | `case NormalClass(var x) ->` when `NormalClass` is not a record | Use a type pattern `case NormalClass obj ->` and the class's accessors |
| Guard placed in the wrong position | Putting `when` inside `Point(...)` | Place `when` after the closing `)` of the record pattern |
| General case shadows specific case | `case Point(var x, var y) ->` placed before `case Point(int x, int y) when x == y ->` | Move the more specific guarded case earlier |
| Duplicate variable name in the same record pattern | `Point(int n, int n)` | Use two distinct names, such as `x` and `y` |
| Confusing `null` in nested records with type patterns | `Point(...)` does not match a `null` component, whereas a direct type pattern can be null-matching | Check for null data separately and pay attention to the nested pattern kind |
| Forgetting `default` or exhaustiveness | An `Object` selector can have many other types | Add an appropriate branch or prove exhaustiveness over a sealed hierarchy |

### Some Examples of Compile Errors

The lines below are **intentionally invalid**, solely to help recognize errors:

```java
// Point has exactly two components; one component is missing.
// case Point(int x) -> "bad";

// Point.x() returns int, which does not match the String type pattern.
// case Point(String x, int y) -> "bad";

// Two variables with the same name in the same record pattern.
// case Point(int n, int n) -> "bad";
```

If you need to validate business rules such as positive coordinates or a non-empty string, use `when` and the corresponding guard, or enforce valid invariants in the record's constructor. A record pattern **does not turn arbitrary business conditions into structural checks**.

## 10. When Should You Use `case Record(...)`?

Record patterns in `case` labels are best suited when:

1. The input can be several different record types and you need to dispatch based on **data shape**.
2. The branch needs the record components directly, rather than holding the whole object and calling accessors repeatedly.
3. The structure has one or two levels of nested records, where deconstruction makes the code easier to understand.
4. You need a guard on component values, such as `case Point(int x, int y) when x == y`.
5. You are modeling data with sealed types + records to handle variants clearly.

If you only need to pass the entire record object to another method, a **type pattern** like `case Point point -> process(point)` can be shorter and clearer. Record patterns are not mandatory for every `switch` branch; choose based on how much of the data you actually need.

## 11. Self-Check

Given the declarations:

```java
record Point(int x, int y) {}
Object value = new Point(5, 5);
```

And the expression inside a Java 21 method:

```java
String result = switch (value) {
    case null -> "null";
    case Point(int x, int y) when x > y -> "greater";
    case Point(int x, int y) when x == y -> "equal";
    case Point(int x, int y) -> "other point";
    default -> "other type";
};
```

**Question:** What is `result`? **Answer:** `"equal"`. All three `Point(...)` record patterns match structurally, but the first branch's guard is false, while the second branch's guard is true and is selected. The general branch afterward still serves to handle any `Point` that satisfies neither guard.

**Try changing `value = null`:** in that case `case null` is selected; no record pattern matches a `null` selector.

**Try changing `value = new Point(5, 3)`:** the first guard is true, so the result is `"greater"`; subsequent branches are not executed.

**Key takeaway:** `case RecordType(componentPatterns...)` combines **record type checking**, **component extraction**, and **pattern variable binding** in the same `case` label. A `when` guard checks an additional condition; branch order determines the first matching rule. Record patterns can be nested, but you must distinguish a `null` selector from a `null` record component and use Java 21+ syntax.

## Official Documentation

- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440) and [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
