# Combining Deconstruction with switch

## 1. Why combine these two features?

Suppose a program receives multiple forms of data: a point (`Point`), a line segment (`Segment`), or a circle (`Circle`). If you need to check the type and then retrieve the coordinates of each record for processing, the usual way is to use `switch` with a **type pattern**, and then call the record's accessors:

```java
record Point(int x, int y) {}

static String show(Object value) {
    return switch (value) {
        case Point p -> "Điểm (" + p.x() + ", " + p.y() + ")";
        case null -> "Không có dữ liệu";
        default -> "Kiểu khác";
    };
}
```

Starting in **Java 21**, you can place a **record pattern** directly after `case` to check the type and extract components right when selecting the branch:

```java
static String show(Object value) {
    return switch (value) {
        case Point(int x, int y) -> "Điểm (" + x + ", " + y + ")";
        case null -> "Không có dữ liệu";
        default -> "Kiểu khác";
    };
}
```

The two examples above are illustrative methods, assuming `Point` is declared in the same scope. When the value is `new Point(2, 5)`, both methods return `"Điểm (2, 5)"`.

**Deconstruction** is matching the structure of a record and extracting its components into variables. `switch` handles selecting the appropriate branch; the record pattern in `case` describes the data structure that must match. This combination is especially useful when each kind of record requires a different way of handling.

## 2. How to read case syntax with a record pattern

Given the record:

```java
record Point(int x, int y) {}
```

The branch:

```java
case Point(int x, int y) -> "Tọa độ: " + x + ", " + y;
```

means:

1. Check whether the `switch` selector matches a record of type `Point`.
2. Extract the first component into variable `x` and the second component into variable `y` in the declaration order of the record.
3. If all component patterns match, evaluate the expression on the right-hand side of `->` and use it as the branch result.

`Point(int x, int y)` is a **pattern**, not a constructor call. The variables `x` and `y` are only in scope within the permitted scope of that `case` branch; they do not automatically become shared variables for other branches.

You can write `case Point(var x, var y)`: the compiler infers the `int` type from the component declaration. The variable names in the pattern are chosen by the author, but **the component order remains fixed**. For example, `Point(int y, int x)` still receives the first component into variable `y` and the second component into variable `x`; the program may compile but have the wrong meaning if you assume the variable names determine the positions.

## 3. Combining nested deconstruction and when

A record can contain another record:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
```

If you only use the type pattern `case Segment segment`, you need to call `segment.start()` and `segment.end()` to get the two endpoints. With a **nested record pattern**, you extract all four coordinates directly in the branch:

```java
case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
        "Từ (" + x1 + ", " + y1 + ") đến (" + x2 + ", " + y2 + ")";
```

The outer pattern confirms `Segment`. The two inner `Point(...)` patterns continue checking and deconstructing the `start` and `end` components. If one endpoint is `null`, the corresponding `Point(...)` pattern does not match, so the entire nested branch is not selected. You can place a `case Segment segment` branch afterward to handle missing data.

In addition to record structure, you sometimes need to check an **additional condition**. Java 21 uses `when` to attach a boolean expression to a branch with a pattern:

```java
case Segment(Point(int x1, int y1), Point(int x2, int y2))
        when x1 == x2 && y1 == y2 ->
        "Đoạn suy biến";
```

The `when` condition is evaluated only when the preceding pattern matches and the variables `x1`, `y1`, `x2`, `y2` have been bound. If the condition returns `false`, `switch` continues searching for the next matching branch.

**Branch order matters.** Place the specific branch with `when` before the unguarded record pattern branch for the same data type. If you place the general `case Segment segment` branch first, the subsequent `Segment(...)` branches may be reported by the compiler as a **dominated case** because they can never be selected.

## 4. Complete Java 21 program

Save the following code as **`SwitchDeconstructionDemo.java`**:

```java
public class SwitchDeconstructionDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record Circle(Point center, int radius) {}

    static String describe(Object value) {
        return switch (value) {
            case Point(int x, int y) ->
                    "Điểm: (" + x + ", " + y + ")";

            case Segment(Point(int x1, int y1), Point(int x2, int y2))
                    when x1 == x2 && y1 == y2 ->
                    "Đoạn suy biến tại (" + x1 + ", " + y1 + ")";

            case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
                    "Đoạn từ (" + x1 + ", " + y1 + ") đến ("
                            + x2 + ", " + y2 + ")";

            case Segment segment ->
                    "Đoạn thiếu điểm đầu hoặc cuối";

            case Circle(Point(int x, int y), int radius) when radius > 0 ->
                    "Tròn: tâm (" + x + ", " + y + "), r=" + radius;

            case Circle(Point(int x, int y), int radius) ->
                    "Tròn có bán kính không dương: " + radius;

            case Circle circle ->
                    "Tròn thiếu tâm";

            case null ->
                    "Không có dữ liệu";

            default ->
                    "Kiểu không hỗ trợ";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(1, 2)));
        System.out.println(describe(
                new Segment(new Point(0, 0), new Point(0, 0))));
        System.out.println(describe(
                new Segment(new Point(0, 1), new Point(2, 3))));
        System.out.println(describe(
                new Segment(new Point(1, 2), null)));
        System.out.println(describe(
                new Circle(new Point(3, 4), 5)));
        System.out.println(describe(
                new Circle(new Point(5, 6), 0)));
        System.out.println(describe(new Circle(null, 7)));
        System.out.println(describe("khác"));
        System.out.println(describe(null));
    }
}
```

With **JDK 21 or later**, compile and run:

```bash
javac SwitchDeconstructionDemo.java
java SwitchDeconstructionDemo
```

Expected output on standard output:

```text
Điểm: (1, 2)
Đoạn suy biến tại (0, 0)
Đoạn từ (0, 1) đến (2, 3)
Đoạn thiếu điểm đầu hoặc cuối
Tròn: tâm (3, 4), r=5
Tròn có bán kính không dương: 0
Tròn thiếu tâm
Kiểu không hỗ trợ
Không có dữ liệu
```

Step-by-step execution explanation:

- `new Point(1, 2)` matches the `Point(int x, int y)` pattern and produces a string with the two coordinates.
- A `Segment` with two identical endpoints matches both the nested pattern and the `when` condition, so the “Đoạn suy biến” branch is selected.
- A `Segment` with two different endpoints does not satisfy the guard, so it matches the next `Segment(Point(...), Point(...))` branch.
- A `Segment` with `end == null` does not match the `Point(...)` pattern on the `end` component. The general `case Segment segment` branch is selected.
- A `Circle` with radius `5` and a valid center matches the nested pattern with the `radius > 0` guard.
- A `Circle` with radius `0` does not satisfy the guard and enters the unguarded `Circle(Point(...), int radius)` branch.
- A `Circle` with `center == null` does not match `Point(...)`, so the `case Circle circle` branch handles it.
- The string `"khác"` does not belong to any handled record type and falls into `default`.
- The `null` selector enters `case null`.

Note that `record Circle(Point center, int radius)` does not automatically forbid a non-positive radius or a `null` center. In a real application, you can add validation in the constructor to preserve data invariants; this example intentionally allows those cases to demonstrate branch selection.

## 5. Switch expression and switch statement

The main example uses a **switch expression**:

```java
String result = switch (value) {
    case Point(int x, int y) -> x + ", " + y;
    case null -> "null";
    default -> "kiểu khác";
};
```

This is an illustrative example with `Point` and `value` already declared. `switch` returns a value; the branches must produce results compatible with the inferred type of the expression. For a multi-statement branch, use a block and `yield` to provide the result:

```java
String result = switch (value) {
    case Point(int x, int y) -> {
        String location = "(" + x + ", " + y + ")";
        yield "Point " + location;
    }
    case null -> "null";
    default -> "kiểu khác";
};
```

If you only want to perform an action, you can use a **switch statement**:

```java
switch (value) {
    case Point(int x, int y) ->
            System.out.println("x + y = " + (x + y));
    case null ->
            System.out.println("Không có dữ liệu");
    default ->
            System.out.println("Loại khác");
}
```

These snippets are independent examples, not variants placed together in the same method. With arrow branches `->`, Java does not perform **fall-through** to the next branch. Record patterns and `when` can be used in both forms of `switch` in Java 21.

## 6. Null, variable scope, and exhaustiveness of branches

### Null in the selector vs. null in a component are different

- **Switch selector is null:** `case null` handles it. Without appropriate handling, `switch` can throw a `NullPointerException` before selecting a normal branch; `default` alone does not substitute for explicit null handling.
- **A record component is null:** the outer record may still match by type, but the nested record pattern for that component does not match. For example, `Segment(Point(...), Point(...))` does not match when `end == null`; the broader `case Segment segment` branch can still handle it.
- **A reference component is bound but null:** a record pattern does not automatically guarantee that every reference value is non-null. After binding the data, you need to check for null before calling methods or unboxing if the value could be null.

### Variables exist only in the matched branch

`x1`, `y1`, `x2`, `y2` in the `Segment(...)` branch are in scope within the `when` guard and the body of that branch. They cannot be used in the `Circle` branch or after the entire `switch` expression. Each branch has its own pattern variables, even if they share the same names as variables in another branch.

### A switch expression must be exhaustive

When the selector has type `Object` as in the main example, it cannot be proven that only `Point`, `Segment`, and `Circle` exist. Therefore, `default` covers values of other types. `case null` addresses the possibility of `null` being passed in. If the selector is a `sealed` hierarchy, branches covering all permitted subtypes can make the `switch` expression exhaustive without `default` for non-null values; whether it is exhaustive is still checked by the compiler.

## 7. Common mistakes

| Mistake | Why it is wrong or dangerous | How to fix |
| --- | --- | --- |
| Writing `case Point p` and assuming `x`, `y` are automatically available | A type pattern only binds the whole record to `p`. | Use `case Point(int x, int y)` or call `p.x()`, `p.y()`. |
| Placing `case Segment segment` before `case Segment(Point(...), Point(...))` | The broader branch covers values that the specific pattern could handle, making the specific branch **dominated**. | Place specific cases and cases with `when` before general cases. |
| Assuming `when` always runs | The guard is evaluated only when the associated pattern has matched. | Put condition checks in `when` after the pattern and provide a fallback branch when the guard is false. |
| Forgetting that a component can be null | A nested record pattern does not match if the inner record is null. | Provide a fallback branch or data rules ensuring valid components. |
| Confusing component order | Patterns bind data in the record's declaration order, not by variable name. | Check the record declaration against the order of component patterns. |
| Expecting `default` to handle a null selector | `null` must be handled according to `switch`'s specific rules. | Use `case null` when the input value can be null. |
| Using pattern variables outside the branch | Variable scope ends according to the rules of the matched case/branch. | Only use variables inside the guard and the valid body of the branch. |
| Compiling with standard Java 17 | Record patterns and pattern matching for switch became standard in Java 21. | Use JDK 21 or later; `--enable-preview` is not needed on JDK 21. |

## 8. Self-check exercise

Given:

```java
record Point(int x, int y) {}
record Rectangle(Point topLeft, Point bottomRight) {}
```

Write a `switch` expression that accepts `Object input`, using the pattern:

```java
case Rectangle(Point(int x1, int y1), Point(int x2, int y2)) ->
        "Rộng=" + (x2 - x1) + ", Cao=" + (y2 - y1);
```

Add a `case Rectangle rectangle` branch to report “Thiếu tọa độ” when an endpoint is null, along with `case null` and `default` to handle the remaining inputs.

For `new Rectangle(new Point(1, 2), new Point(6, 8))`, the returned string is **`Rộng=5, Cao=6`**. The exercise assumes the coordinates of the two corners are in the appropriate order; if you need to handle rectangles regardless of corner order, you must normalize them or compute the absolute value according to the domain requirements.

**Key takeaway:** Placing a record pattern in `case` allows `switch` to both select the data type and deconstruct its components for processing. Nested patterns express the structure of inner records; `when` adds a condition after the pattern matches; case ordering, `null`, variable scope, and exhaustiveness of a switch expression determine the correct behavior of the program.
