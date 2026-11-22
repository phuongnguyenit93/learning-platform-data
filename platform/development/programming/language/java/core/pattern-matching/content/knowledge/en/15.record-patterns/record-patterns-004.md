# Component patterns in record patterns (Java 21+)

## 1. What is a component pattern?

A `record` describes data using **record components** in its declaration. For example, `record Point(int x, int y) {}` has two components `x` and `y`, along with the accessor methods `x()` and `y()`.

A **record pattern** lets you check whether a value matches a record and extract its components through pattern matching. A **component pattern** is a *pattern placed at a component position* inside the parentheses of a record pattern; it determines what condition the value at that position must satisfy and whether it is bound to a pattern variable.

For example:

~~~java
record Point(int x, int y) {}

Object value = new Point(3, 5);
if (value instanceof Point(int horizontal, int vertical)) {
    System.out.println(horizontal + vertical); // 8
}
~~~

In `Point(int horizontal, int vertical)`, the two patterns `int horizontal` and `int vertical` are the two component patterns. They receive values from components `x` and `y`, respectively. Pattern variable names do not need to match the declared component names; **position and order** determine the correspondence.

The ability to use record patterns in `instanceof` and `switch` became a standard feature in **Java 21**. `record` declarations existed in earlier versions, but deconstructing records with pattern syntax as shown above requires Java 21+.

## 2. Reading the syntax from outside in

Consider two nested records:

~~~java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
~~~

The pattern:

~~~java
Segment(Point(int sx, int sy), Point(var ex, var ey))
~~~

has the following layers:

1. `Segment(...)` is the outermost record pattern, with **two component patterns** corresponding to `start` and `end`.
2. `Point(int sx, int sy)` is a **nested record pattern** at the `start` position. Inside it, `int sx` and `int sy` match `x` and `y` of `Point`, respectively.
3. `Point(var ex, var ey)` is a nested record pattern at the `end` position. The types of `ex` and `ey` are inferred as `int` because `Point` declares two components of type `int`.

In other words, a component pattern can be a pattern with an **explicit type** (such as `int sx` or `String text`), a `var` pattern (such as `var ex`), or **another record pattern** (such as `Point(int sx, int sy)`). Nesting patterns lets you traverse multiple layers of records without chained calls like `segment.start().x()`.

A pattern must have a number of positions matching the number of declared record components. `Point(int x)` is invalid for `record Point(int x, int y)` because one position is missing.

## 3. Conditions for a component pattern to match

When evaluating `value instanceof Segment(Point(int sx, int sy), Point(var ex, var ey))`, Java semantically performs the following:

- The outermost value must be non-`null` and match the record type `Segment`.
- The two component values are extracted in **record declaration order**, meaning `start` first and then `end`; each value must match its corresponding component pattern.
- For the nested pattern `Point(...)`, the component value must be non-`null` and match the type `Point`, after which its `x` and `y` components are matched.
- **Only when all sub-patterns match** does the outermost record pattern match; the variables `sx`, `sy`, `ex`, `ey` are in scope in the matching branch.

If `start` is `null`, `Point(int sx, int sy)` does not match and the entire `Segment(...)` pattern fails. This differs from calling `segment.start().x()` directly when `start()` returns `null`: a manual call can throw a `NullPointerException`.

A component pattern with a specific type also performs a runtime type check. With `record Box(Object value) {}`, the pattern `Box(String text)` only matches when the component value is a non-`null` `String`. In contrast, `Box(var other)` infers the type of `other` as `Object` from the declaration of `Box`; a `var` pattern can also accept a component whose value is `null`.

## 4. A runnable Java 21 program

Save the following program to `ComponentPatternDemo.java`:

~~~java
public class ComponentPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record Box(Object value) {}

    static String describe(Object input) {
        return switch (input) {
            case Box(String text) -> "String: " + text;
            case Box(Integer number) -> "Integer: " + number;
            case Box(var other) -> "Other: " + other;
            case null -> "null";
            default -> "not a Box";
        };
    }

    public static void main(String[] args) {
        Object segment = new Segment(
                new Point(2, 3),
                new Point(8, 13)
        );

        if (segment instanceof Segment(
                Point(int sx, int sy),
                Point(var ex, var ey))) {
            System.out.printf("start=(%d,%d)%n", sx, sy);
            System.out.printf("end=(%d,%d)%n", ex, ey);
            System.out.printf("delta=(%d,%d)%n", ex - sx, ey - sy);
        }

        System.out.println(describe(new Box("hi")));
        System.out.println(describe(new Box(42)));
        System.out.println(describe(new Box(null)));
        System.out.println(describe(null));
    }
}
~~~

Compile and run with JDK 21 or later:

~~~bash
javac --release 21 ComponentPatternDemo.java
java ComponentPatternDemo
~~~

Output:

~~~text
start=(2,3)
end=(8,13)
delta=(6,10)
String: hi
Integer: 42
Other: null
null
~~~

Explanation:

- The pattern `Segment(Point(int sx, int sy), Point(var ex, var ey))` deconstructs `Segment` through two `Point`s. We get `(sx, sy) = (2, 3)` and `(ex, ey) = (8, 13)`, so the delta is `(6, 10)`.
- In `switch`, `Box(String text)` matches `Box("hi")`; `Box(Integer number)` matches `Box(42)`. This is an example of a component pattern both checking the actual type of the component and creating a narrowed-type variable.
- `Box(var other)` handles the remaining `Box` instances, including `Box(null)`, because the `var other` component pattern receives `null`. `case null` is the case where **the switched object itself** is `null`, which is different from an existing `Box` containing a `null` value.
- Place the specific patterns `Box(String text)` and `Box(Integer number)` **before** the catch-all pattern `Box(var other)`: reversing the order would make the specific branches unreachable.

## 5. Comparison with accessing components via accessors

Without using record patterns, data can be extracted with explicit calls:

~~~java
if (segment instanceof Segment s) {
    Point from = s.start();
    Point to = s.end();

    if (from != null && to != null) {
        int sx = from.x();
        int sy = from.y();
        int ex = to.x();
        int ey = to.y();
        // Use the four coordinates here
    }
}
~~~

This is an **illustrative snippet**, assuming `segment` and the two records `Point` and `Segment` are defined as in the program above. Record patterns make extracting values more concise and express the matching condition inline; accessors remain useful when you need to process each component independently, reuse values, or keep branching conditions easier to read.

Key distinctions:

| Syntax | Meaning |
| --- | --- |
| `record Point(int x, int y) {}` | Declares two record components: `x` and `y`. |
| `Point(int a, int b)` | Record pattern with two `int` component patterns, binding pattern variables `a` and `b`. |
| `Point(var a, var b)` | Record pattern with two `var` component patterns, inferring both variables as `int`. |
| `Box(String text)` | Checks that the `Object` component actually holds a `String` and binds `text` of type `String`. |
| `Box(var content)` | Binds `content` of type `Object` according to the component's declared type; does not automatically cast to `String`. |

## 6. Common mistakes

**Confusing variable names with record component names.** In `Point(int y, int x)`, the variable `y` receives the *first* component and the variable `x` receives the *second* component. Java does not match by name; name variables consistently to avoid mixing up coordinates.

**Missing a component or using an incompatible type.** For a `Point` with two components, you must provide exactly two patterns. A component pattern must also be type-compatible: for example, `Point(String x, int y)` is invalid when the first component is the primitive type `int`.

**Assuming `var` checks the runtime type like `String`.** With `Box(var content)`, the static type of `content` is `Object`; you cannot call `content.length()` as if it were a `String` without an appropriate check or cast. Use `Box(String content)` when the goal is to handle only string data.

**Not handling `null` and nested patterns.** A `Segment` with `start == null` does not match `Segment(Point(...), ...)`. The pattern `Box(String text)` does not match `Box(null)`; you need another pattern or branch if that case is valid in your problem.

**Using pattern variables out of scope.** Variables declared by component patterns are only definitely assigned on control-flow paths where the pattern has matched, such as the body of the corresponding `if` or `case` branch. Do not use `sx` after the `if` statement as if it were always bound.

**Applying record patterns to regular classes.** The `Point(...)` syntax is a record pattern and requires a corresponding `record` type. A class with record-like getters does not automatically become deconstructible with a record pattern.

**Using the wrong Java version.** `record` and record patterns are two features with different version milestones. Use JDK **21+** for this example; in Java 21, `--enable-preview` is not needed for record patterns.

## 7. When should you use it?

Component patterns are well suited when your data model uses records and you need to quickly read component values, especially with nested records (`Segment` containing `Point`) or when choosing behavior based on a component's actual runtime type (`Box(Object)` holding `String`/`Integer`). Deeply nested patterns can become hard to read; when the processing logic is long, split the checks or use accessors with intermediate variables.

**Remember:** A record pattern specifies the *record shape* to match; each **component pattern** specifies the *matching condition for each component value in declaration order*. Nested patterns allow going deeper, `var` patterns infer the component's type, and explicitly typed patterns can check and narrow the value's type.
