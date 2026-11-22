# Multi-Level Nested Record Patterns in Java

## 1. Objectives and Java Version

When an object contains nested `record` instances, you often have to chain multiple accessors such as `route.segment().from().x()` and manually check types or `null` values before using them. **Nested record patterns** let you check the structure and extract components across multiple levels directly within an `instanceof` expression or a `switch` branch.

**Record patterns** were standardized in **Java 21 (JEP 440)**; pattern matching for `switch` also became final in Java 21 (JEP 441). The examples below use **JDK 21+** and do not require `--enable-preview`. A `record` is a class type used to model data; each component has an accessor with the same name, such as `point.x()`.

After this lesson, you will know how to read record patterns from the outside in, combine two or more levels of records, extract variables using `var`, use `when` with `switch`, and handle non-matching cases.

## 2. Nested Structure and Syntax

Suppose you have three records:

```java
record Point(int x, int y) {}
record Segment(Point from, Point to) {}
record Route(String name, Segment segment) {}
```

A `Route` contains a `Segment`, and a `Segment` contains two `Point` instances. When `value` is a variable of type `Object`, you can write (placing this snippet inside a method with a `value` variable):

```java
if (value instanceof Route(
        String name,
        Segment(
            Point(int x1, int y1),
            Point(int x2, int y2)))) {
    System.out.println(name + ": (" + x1 + ", " + y1
            + ") -> (" + x2 + ", " + y2 + ")");
}
```

Reading the pattern in order:

1. `Route(...)`: the outer value must be a `Route`, with two components in their exact declaration order: `name` and `segment`.
2. `String name`: binds the value of the first component to the variable `name` using a type pattern.
3. `Segment(...)`: the second component must match a `Segment` record.
4. Two `Point(...)` patterns: `from` and `to` are further deconstructed; `x1`, `y1`, `x2`, `y2` are `int` variables declared directly inside the pattern.

This is a **three-level record pattern: `Route → Segment → Point`**. Each record pattern must have the exact number of nested patterns corresponding to the record's components and in the same declaration order. The compiler uses the record's accessors to retrieve the components and attempts to match recursively. The `if` condition is true only when the entire pattern matches; only then can the variables be used in the `if` body. The syntax above does not create a new record, does not automatically compare two `Point` objects, and does not compare coordinates against constant values.

## 3. Complete, Runnable Java 21 Example

Create the file `NestedRecordPatternsDemo.java`:

```java
public class NestedRecordPatternsDemo {
    record Point(int x, int y) {}
    record Segment(Point from, Point to) {}
    record Route(String name, Segment segment) {}
    record Box<T>(T value) {}

    static String startOf(Object value) {
        if (value instanceof Route(String name,
                Segment(Point(int startX, int startY), Point(var endX, var endY)))) {
            return name + ": start=(" + startX + ", " + startY
                    + "), end=(" + endX + ", " + endY + ")";
        }
        return "No complete route";
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "Null input";
            case Route(String name,
                    Segment(Point(int x1, int y1), Point(int x2, int y2)))
                    when x1 == x2 && y1 == y2 -> name + ": same point";
            case Route(String name,
                    Segment(Point(var x1, var y1), Point(var x2, var y2)))
                    -> name + ": different points";
            default -> "No matching route";
        };
    }

    static String unwrap(Box<Box<String>> box) {
        if (box instanceof Box(Box(var text))) {
            return text;
        }
        return "No nested string";
    }

    public static void main(String[] args) {
        Object complete = new Route("R1", new Segment(new Point(1, 2), new Point(5, 8)));
        Object zero = new Route("R2", new Segment(new Point(3, 3), new Point(3, 3)));
        Object incomplete = new Route("R3", new Segment(null, new Point(9, 9)));

        System.out.println(startOf(complete));
        System.out.println(classify(complete));
        System.out.println(classify(zero));
        System.out.println(classify(incomplete));
        System.out.println(classify(null));
        System.out.println(unwrap(new Box<>(new Box<>("Java 21"))));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 NestedRecordPatternsDemo.java
java NestedRecordPatternsDemo
```

Output:

```text
R1: start=(1, 2), end=(5, 8)
R1: different points
R2: same point
No matching route
Null input
Java 21
```

Explanation of each case:

- `startOf(complete)` matches all three levels, binds the four coordinates, and returns a description of the start/end points.
- `classify(complete)` does not pass the `when` branch because the two points are different; the more general record pattern branch below is selected.
- `classify(zero)` matches the branch with `when x1 == x2 && y1 == y2` because the start and end points are the same.
- `incomplete` has `Segment.from() == null`, so the `Point(...)` pattern at that position **does not match**. The `switch` falls through to `default` instead of accessing `null.x()`.
- `classify(null)` is handled by `case null`; without this branch, switching on a `null` value normally throws a `NullPointerException`.
- `unwrap` demonstrates type inference when nesting generic records: from the parameter `Box<Box<String>>`, the compiler infers that `text` has type `String`.

## 4. Rules to Remember When Nesting Multiple Levels

### Using `var` and Type Patterns Properly

In `Point(int x, int y)`, you explicitly specify the type of each component. With `Point(var x, var y)`, the compiler automatically infers that both `x` and `y` are `int` from the `record Point(int x, int y)` declaration. `var` inside a record pattern is a variable with a **compile-time known type**; it does not turn Java into a dynamically typed language. This `var` is a component pattern, not a wildcard/discard operator.

You can mix levels: `Route(String name, Segment(Point(var x, var y), var to))`. In that example, `to` still has type `Point` because the `Segment.to` component is a `Point`, without deconstructing `to`'s coordinates yet. Only deconstruct as deeply as you actually need to keep the code readable.

### Combining `switch` and `when` Guards

`when` is evaluated **after** the pattern in the `case` branch matches, and it can use the variables declared in that pattern. Narrower branches with `when` should be placed before broader branches. If a general branch already covers a more specific branch below it, Java will report a **dominated case label** error at compile time.

A `switch` expression must cover all valid inputs; for an `Object` input as in the example, `default` ensures exhaustiveness. `case null` is a special case and is not implicitly covered by a record pattern.

### Distinguishing `null` at Each Level

A **record pattern** such as `Point(var x, var y)` never matches `null`. Therefore, if an intermediate level that you intend to deconstruct into a record is `null`, the entire nested pattern fails to match. By contrast, type patterns used for components (especially `var` or a type that covers the component) have their own `null`-matching rules; do not assume that every `null` component breaks every pattern. Identify precisely **which level is using a record pattern**.

If you need to distinguish between "wrong type", "missing nested record", and "invalid coordinates", write explicit checks or split into separate methods rather than lumping everything into a single `default`.

### Variable Scope and Accessors

Variables like `x1` and `y1` are only in scope where the compiler knows the pattern has matched: the `if` body, the right-hand side of `&&` where appropriate, `when`, and the corresponding `case` body. You cannot use them arbitrarily after an `if` if the branch might not match. Pattern matching accesses components via accessors as part of the language mechanism; it is not reading fields via reflection and does not require manual casting.

### Nested Generic Records

Given `record Box<T>(T value) {}` and a variable `Box<Box<String>> box`, the pattern `Box(Box(var text))` lets you extract the inner `String`. The compiler must be able to prove that the type can be matched safely; do not introduce an unchecked parameterized type check on a raw type and expect record patterns to bypass type erasure.

## 5. Common Mistakes

| Mistake | Cause and Fix |
| --- | --- |
| Writing `Point(int x)` when `Point` has `x, y` | Wrong number of components. Write all required patterns, e.g. `Point(int x, int y)`. |
| Swapping `from` and `to` thinking patterns match by name | Record patterns match by **declaration position**. Re-read the `record Segment(Point from, Point to)` definition. |
| Using `Point(0, 0)` syntax to check for the origin | Java 21 does not have literal record pattern syntax like this. Use `Point(int x, int y)` and check `x == 0 && y == 0` with `if` or `when`. |
| Using a record pattern to "deconstruct" a regular class | This deconstruction syntax is for **record classes**. For regular classes, use accessors or change the data structure where appropriate. |
| Accessing a pattern variable after an `if` that does not guarantee a match | The variable is not definitely assigned on all control-flow paths. Move the logic into the `if` body or a verified branch. |
| Ignoring `null` at a nested record level or in the `switch` selector | Add a branch for non-matching cases; use `case null` when the `switch` selector can be `null`. |
| Placing a general `case` before a `case` with `when` | The later branch may be dominated; place specific branches first and general branches afterward. |
| Compiling with Java 17 without preview enabled | Record patterns are not a standard feature in Java 17. Use **JDK 21+** for the examples in this lesson. |

## 6. When to Use and How to Practice

Nested record patterns are useful for immutable data structures, abstract syntax trees (ASTs), events, or processing results where multiple records are nested. Prefer them when the code wants to clearly express **"what structure does the data have?"** and **"which components need to be extracted?"**. When nesting becomes too deep or involves many business rules, splitting the pattern into multiple steps or smaller methods can make the code easier to read and test.

Exercise: Given the following three records, write an `instanceof` check to extract the `city` of an `Order` only when the customer has an `Address` and `city != null`:

```java
record Address(String city, int postalCode) {}
record Customer(String id, Address address) {}
record Order(long orderId, Customer customer) {}
```

One solution (placed inside a method receiving `Object input`):

```java
if (input instanceof Order(
        var orderId,
        Customer(var customerId, Address(var city, var postalCode)))
        && city != null) {
    System.out.println(orderId + " / " + customerId + " / " + city);
} else {
    System.out.println("Missing customer address or city");
}
```

In this example, `Address(...)` requires the address level to be a non-`null` `Address` record; the `city != null` check further validates the string component. These are two distinct conditions and both are important.

**Key takeaway:** nested record patterns match from the outer record to the inner record, following the exact order of components. `var` enables type inference, `when` handles conditions on bound data, `case null` handles a null selector, and `default` or `else` handles non-matching data. When you need to access multiple levels of data, this syntax is usually shorter and safer than a chain of manual casts.

**References:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
