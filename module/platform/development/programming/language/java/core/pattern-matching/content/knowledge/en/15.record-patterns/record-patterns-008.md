# Record Patterns in `switch` (Java 21+)

## 1. Objectives and Prerequisites

**Record patterns in `switch`** allow you to both select a branch based on an object's type and **directly deconstruct the components of a `record`** into variables for processing. This syntax is well-suited when a program receives multiple structured data types, such as geometric shapes, events, messages, or business results.

The two related features — **Record Patterns (JEP 440)** and **Pattern Matching for `switch` (JEP 441)** — both became standard features in **Java 21**. The examples below require JDK 21 or later and **do not need `--enable-preview`**. Java 17 has `record` and some forms of `switch`, but does not yet provide stable support for record pattern syntax in `switch`.

After this lesson, you will be able to:
- Recognize the `case RecordType(pattern1, pattern2, ...)` syntax and how variables are bound.
- Use `when`, nested record patterns, and `switch` expressions/statements.
- Control branch ordering, `null`, exhaustiveness, and common compilation errors.
- Combine `record` with `sealed` to handle data types with a fixed set of variants.

## 2. Syntax and Mechanism

Given a record:

```java
record Point(int x, int y) {}
```

When the input has type `Object`, a `switch` branch can be written as:

```java
case Point(int x, int y) -> "x=" + x + ", y=" + y
```

Meaning of `Point(int x, int y)`:

1. Checks whether the input value is a matching `Point` object; `null` does not match a record pattern.
2. Extracts the two components of `Point`, in the **exact declaration order** `x` then `y`, via the corresponding accessors.
3. Matches each component against its nested sub-pattern: here `int x` and `int y` declare two variables of type `int`.
4. If all patterns match, executes the branch to the right of `->`; variables `x` and `y` are in scope within that branch.

You can use `var` to infer types from the record declaration:

```java
case Point(var x, var y) -> "x=" + x + ", y=" + y
```

With `record Point(int x, int y)`, both variables still have type `int`. Using `var` here **does not turn them into `Object`**. Distinguish the three forms:

| Form | Check / value received |
| --- | --- |
| `case Point p` | Type pattern: receives the entire `Point` object via variable `p`; to get coordinates, call `p.x()`, `p.y()`. |
| `case Point(int x, int y)` | Record pattern: immediately deconstructs the two components into `x` and `y`. |
| `case Point(var x, var y)` | Same deconstruction mechanism, letting the compiler infer each component's type. |

A record pattern does not copy the record, mutate data on its own, or invoke a new constructor. It performs a type check and reads existing components. **The number of sub-patterns must equal the number of components**, and each pattern must be valid for its corresponding component type.

## 3. Complete Example: Record Patterns, `when`, and Nested Patterns

Create the file **`RecordSwitchDemo.java`**:

```java
public class RecordSwitchDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "Không có dữ liệu";

            case Point(int x, int y) when x == 0 && y == 0 ->
                "Gốc tọa độ";

            case Point(var x, var y) ->
                "Điểm(" + x + ", " + y + ")";

            case Segment(
                    Point(var x1, var y1),
                    Point(var x2, var y2)) ->
                "Đoạn: (" + x1 + ", " + y1 + ") -> ("
                    + x2 + ", " + y2 + ")";

            case Segment s -> "Đoạn thiếu điểm đầu hoặc cuối";

            default -> "Không hỗ trợ: "
                + input.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(0, 0)));
        System.out.println(describe(new Point(3, -2)));
        System.out.println(describe(
            new Segment(new Point(1, 2), new Point(4, 6))));
        System.out.println(describe(
            new Segment(null, new Point(4, 6))));
        System.out.println(describe("abc"));
        System.out.println(describe(null));
    }
}
```

Compile and run in the directory containing the file using **JDK 21+**:

```bash
javac --release 21 -encoding UTF-8 RecordSwitchDemo.java
java RecordSwitchDemo
```

Output:

```text
Gốc tọa độ
Điểm(3, -2)
Đoạn: (1, 2) -> (4, 6)
Đoạn thiếu điểm đầu hoặc cuối
Không hỗ trợ: String
Không có dữ liệu
```

Reading each branch:

- `case null` handles when `input` itself is `null`. Therefore, the `default` branch can safely call `input.getClass()`.
- `case Point(int x, int y) when x == 0 && y == 0` only runs if it is a `Point` **and** both coordinates are 0.
- `case Point(var x, var y)` handles the remaining `Point` values; both variables are inferred as `int`.
- `case Segment(Point(...), Point(...))` is a **nested record pattern**: it deconstructs the two `Point`s inside `Segment`, then further deconstructs the four coordinates. Every level must match.
- If one endpoint of `Segment` is `null`, the nested `Point(...)` at that position does not match. The subsequent `case Segment s` branch still receives the `Segment` object and handles the missing-data case.
- `default` covers other types such as `String`.

The example uses a `switch` **expression**, so the entire `switch` returns a `String` for the `describe` method without needing an auxiliary variable or `break`. This is also a way to dispatch processing based on data structure without manual chains of casts.

## 4. `when` Guards and Branch Ordering

`when` adds a Boolean condition **after** the pattern matches. The newly deconstructed variables can be used immediately in the guard:

```java
case Point(var x, var y) when x == y -> "Nằm trên đường x = y"
case Point(var x, var y) when x > 0 -> "Phía bên phải trục Oy"
case Point(var x, var y) -> "Điểm còn lại"
```

These three branches are evaluated **in order of appearance**. For example, `Point(2, 2)` matches the first branch and does not proceed further; `Point(3, 1)` matches the second branch. Because a guard can evaluate to `false`, the general record pattern branch at the end is still needed to cover the remaining cases.

**Dominance rule:** if an earlier branch already matches every value that a later branch could match, the later branch is considered unreachable and the code **will not compile**. An *intentionally invalid* example:

```java
// Example that does NOT compile: the type pattern dominates the subsequent record pattern.
return switch (input) {
    case Point p -> "Mọi Point";
    case Point(var x, var y) -> "Không thể tới"; // dominated
    default -> "Khác";
};
```

Place specific/guarded patterns first, and general patterns afterward. Do not put `case Object o` at the top when you still want to match `Point` or `Segment` below: `Object o` covers all other non-null objects. In the complete example, `case Point(...) when ...` is placed before `case Point(var x, var y)`, and the nested `Segment(...)` is placed before `case Segment s`.

A guard is a runtime check; do not mistake it for Java inferring arbitrary guard expressions to reorder branches for you. Write case ordering transparently, especially when two guards could both be true.

## 5. `null`: Distinguishing the Selector from Components Inside a Record

There are **two levels of `null`** to distinguish:

1. **Selector `null`**: `switch (input)` with `input == null` throws `NullPointerException` if there is no appropriate `case null` branch, even when `default` is present. When you want to accept `null` as a business case, write `case null -> ...` explicitly.
2. **Component `null`**: a record can contain null reference values if its constructor does not forbid them. A sub-pattern like `Point(var x, var y)` does not match a `null` component. Therefore, `Segment(Point(...), Point(...))` does not match `new Segment(null, p)`, even though the `Segment` itself is a valid object.

You can combine a deep-deconstruction branch with a fallback type pattern branch:

```java
case Segment(Point(var ax, var ay), Point(var bx, var by)) ->
    "Hai đầu mút đầy đủ";
case Segment s -> "Một hoặc cả hai đầu mút có thể bị null";
```

The `case Segment s` branch does not deconstruct `Point` itself, so it still accepts a `Segment` with null components. If you want to reject missing data right when creating the object, you can validate in the record's compact constructor:

```java
record NonNullSegment(Point start, Point end) {
    NonNullSegment {
        java.util.Objects.requireNonNull(start, "start");
        java.util.Objects.requireNonNull(end, "end");
    }
}
```

Then, missing data is rejected immediately at `NonNullSegment` creation time. Do not treat record patterns as a full business validation mechanism: they only check the type and structure according to the described pattern.

## 6. `sealed` + Record Patterns: Exhaustiveness Without `default`

When data has a closed set of variants, a `sealed interface` tells the compiler the valid subtypes. Record patterns allow extracting different information for each variant.

Create the file **`ShapeSwitchDemo.java`**:

```java
public class ShapeSwitchDemo {
    sealed interface Figure permits Square, Rect {}

    record Square(int edge) implements Figure {}
    record Rect(int width, int height) implements Figure {}

    static int area(Figure figure) {
        return switch (figure) {
            case null -> throw new IllegalArgumentException("figure is null");
            case Square(var edge) -> edge * edge;
            case Rect(var width, var height) -> width * height;
        };
    }

    public static void main(String[] args) {
        System.out.println(area(new Square(4)));
        System.out.println(area(new Rect(3, 5)));
    }
}
```

Run:

```bash
javac --release 21 -encoding UTF-8 ShapeSwitchDemo.java
java ShapeSwitchDemo
```

Output:

```text
16
15
```

`Figure` only permits `Square` and `Rect`, and the corresponding record patterns cover all non-null values of these two types. Therefore, the `switch` expression is **exhaustive without needing `default`**. The `case null` branch expresses a clear error-reporting policy when input is missing. If you add a new permitted subtype to `Figure` and recompile, the compiler can require adding the corresponding branch — a benefit of not masking variants with `default`.

A `switch` expression must be able to produce a result or throw an exception on every path. A `switch` statement using patterns must also cover the cases of the selector type according to enhanced switch rules; therefore, when the selector is `Object`, use `default` or a sufficiently general branch.

**Runtime note:** exhaustiveness assumptions are checked at compile time. If a `sealed` hierarchy changes between compiled/runtime artifacts without recompiling the old `switch` code, a `MatchException` may occur at runtime. A nested record pattern encountering uncovered null data is also a situation to guard against, as illustrated in the previous section.

## 7. `switch` Expression, `switch` Statement, and Variable Scope

Record patterns can be used in both forms.

- **Expression** returns a value: `String result = switch (value) { ... };`. If a branch has multiple statements, use a block `{ ... yield result; }`; `yield` returns the branch's result.
- **Statement** performs an action, such as logging, without needing to return a value. The arrow syntax `->` does not fall through to the next branch.

Statement example using the `Point` declared above:

```java
static void printPoint(Object value) {
    switch (value) {
        case null -> System.out.println("null");
        case Point(var x, var y) ->
            System.out.println("x=" + x + ", y=" + y);
        default -> System.out.println("Không phải Point");
    }
}
```

This is a **snippet to add to a class that has `record Point`**, not a standalone runnable file. For an expression, you can use a block:

```java
static String horizontalSide(Point point) {
    return switch (point) {
        case Point(var x, var y) -> {
            String side = x < 0 ? "trái" : (x > 0 ? "phải" : "trên trục Oy");
            yield side + ", y=" + y;
        }
    };
}
```

The variables `x` and `y` declared by each `case` are only in scope within the corresponding guard and branch body. They cannot be used after exiting the `switch`. You can reuse variable names in other branches when there is no scope conflict.

## 8. Common Errors and Fixes

| Issue | Cause | Fix |
| --- | --- | --- |
| `javac` reports `case Point(var x, var y)` syntax as invalid | Using an older Java version or mistaking a standard feature for a preview feature | Use JDK 21+ and check `javac -version`; no preview flag is needed for Java 21. |
| Fails to match a record of the right type when one component is `null` | Nested record patterns require each sub-pattern to match, whereas reference patterns do not match null | Add a fallback type pattern branch, check/normalize data, or reject null in the constructor. |
| A lower branch fails with `dominated case label` | A general branch is placed before a specialized branch | Move specialized guards/record patterns earlier; place broad type patterns later. |
| `switch` expression reports not exhaustive | Missing data type cases, guards do not cover all values, or missing `default` on an open selector | Cover all `sealed` variants, add a fallback pattern, or add an intentional `default`. |
| Wrong number/order of components | Record patterns must follow the record's **declaration order**, not display names | Check the `record` declaration; use `var` when you want the compiler to infer types. |
| Trying to deconstruct a POJO or `List` with `Type(...)` | Record pattern syntax applies to **record classes**, not arbitrary classes/collections | Use type patterns and the class's API, or model the data with a record when appropriate. |
| Trying to distinguish `Box<String>` and `Box<Integer>` at runtime | Generic type arguments undergo type erasure; you cannot rely on record patterns to check all generic parameters | Design branches around runtime-checkable types or check inner values separately. |
| Using `_` to ignore a component fails to compile on standard Java 21 | Unnamed patterns/variables are a **preview feature in Java 21**, not part of the stable syntax used in this lesson | Use named variables on Java 21 or explicitly choose a version/configuration that supports `_`. |

One point to remember: a record pattern only deconstructs components according to the `record` declaration; it does not automatically validate values such as "coordinates must be positive" or "name must not be empty". To add conditions when selecting a branch, use `when`; to preserve data invariants, validate in the constructor or business logic.

Additionally, deconstructing components invokes the record's **accessors**. If a custom accessor throws an exception, pattern matching may terminate abnormally with a `MatchException` wrapping the root cause. Therefore, keep records/accessors simple without unexpected side effects.

## 9. When to Choose Record Patterns in `switch`?

Use them when data comes from multiple **records** or nested records and each form needs a different processing branch. With `sealed`, the compiler also helps ensure all branches are covered. If you only have one fixed object and want to read a single field, calling the accessor directly (for example, `point.x()`) is usually clearer. If the structure is too deep and makes a `case` long and hard to read, you can extract a small helper method or move validation to where the data is created.

To practice on your own, try:
1. Adding a `Point(var x, var y) when x == y` branch to `describe` and deciding the right position so the origin branch still has the desired priority.
2. Modifying `Segment` into a record that rejects null components and observing the difference between **validation at object creation** and **matching during processing**.
3. Adding `record Triangle(int base, int height) implements Figure` to the `sealed` example, updating `permits`, and seeing how the compiler requires handling the new branch.

**Key takeaways:** `case RecordType(...)` simultaneously checks the type and deconstructs data; `when` filters by condition; branch order determines priority; `case null` handles a null selector; `sealed` helps verify exhaustiveness.

## Official Documentation

- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
