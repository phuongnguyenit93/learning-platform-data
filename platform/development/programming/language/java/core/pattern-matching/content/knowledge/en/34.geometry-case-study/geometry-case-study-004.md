# Calculating Area with Record Patterns

## 1. The Geometry Problem and Case Study Goals

Suppose a Java application needs to represent multiple planar shapes and calculate their **area** based on shape type: circle, rectangle, and triangle. The traditional approach might use a chain of `if (shape instanceof ...)`, manual casting, and then retrieving the corresponding radius or sides. With **record patterns** in Java 21, we can express the structure of each shape directly in a `switch`.

The idea:

```java
return switch (shape) {
    case Circle(var center, double radius) ->
            Math.PI * radius * radius;
    case Rectangle(double width, double height) ->
            width * height;
    // Other cases ...
};
```

This is only an illustrative snippet inside a method; the `Circle` and `Rectangle` types will be declared in full below.

This case study targets five skills:

1. **Modeling a geometry domain** using a `sealed interface` and `record` types.
2. **Using record patterns** to perform type checks while extracting components without manual casting.
3. **Using nested record patterns** to extract the coordinates of a triangle's three vertices.
4. **Writing correct area formulas** and handling `null`, negative numbers, `NaN`, infinity, degenerate cases, and overflow.
5. **Testing semantics properly**, including boundary values and floating-point error, rather than merely checking whether the code runs.

In this article, coordinates, radii, sides, and areas all use `double`. Units can be understood as meters and square meters if all input data uses meters. A correct formula still produces meaningless results if centimeters are mixed with meters without conversion.

## 2. Area Formulas to Know

| Shape | Input Data | Formula | Important Conditions |
| --- | --- | --- | --- |
| Circle | Radius `r` | `A = πr²` | `r > 0` and finite; center does not affect area. |
| Rectangle | Width `w`, height `h` | `A = w × h` | `w > 0`, `h > 0`, and finite. |
| Triangle from base/height | Base `b`, perpendicular height `h` | `A = b × h / 2` | `h` must be the **altitude**, not a slanted side. |
| Triangle from three points | `P₁(x₁,y₁)`, `P₂(x₂,y₂)`, `P₃(x₃,y₃)` | `A = \| (x₂-x₁)(y₃-y₁) - (y₂-y₁)(x₃-x₁) \| / 2` | All three vertices must have finite coordinates; three collinear vertices give `A = 0`. |

In the three-point triangle case, the expression inside the absolute value bars is the **2D determinant / cross product** of the two vectors `P₁P₂` and `P₁P₃`. The signed value depends on the vertex ordering direction, but standard geometric area must be **non-negative**, so `Math.abs` is required.

Example with three vertices `(0,0)`, `(4,0)`, and `(0,3)`:

```text
A = abs((4 - 0) * (3 - 0) - (0 - 0) * (0 - 0)) / 2
  = abs(12 - 0) / 2
  = 6
```

This is a right triangle with legs of length `4` and `3`. If all three vertices are translated by the same vector, the area remains `6`. Translation invariance is a useful property for testing.

## 3. Designing Shape with a Sealed Interface and Records

A minimal model for this case study:

```java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Point(double x, double y) {}

record Circle(Point center, double radius) implements Shape {}

record Rectangle(double width, double height) implements Shape {}

record Triangle(Point a, Point b, Point c) implements Shape {}
```

These are illustrative declarations **without validation**. The complete program section will add constructors to reject invalid data.

### Why Choose Records?

A record describes data with fixed components: `Point` has `x` and `y`, `Circle` has `center` and `radius`, `Rectangle` has `width` and `height`, and `Triangle` has three points. Java automatically generates a constructor, accessors, `equals`, `hashCode`, and `toString` suited to the record, unless we customize the permitted members.

Accessors share the component names, for example:

```java
Point p = new Point(2, 3);
double x = p.x();
double y = p.y();
```

In Java 21, **record patterns** use the record's metadata and corresponding accessors to match and extract component values.

### Why Choose a Sealed Interface?

`Shape` is the common type and directly permits only the three records `Circle`, `Rectangle`, and `Triangle` to implement it. Since records are implicitly `final`, the set of subtypes in the example is controlled.

The compiler can check the **exhaustiveness** of a `switch expression` when all permitted branches are handled. If the domain later adds `Ellipse`, any `switch` without a `default` that is missing the new branch will be flagged by the compiler when recompiled. This helps avoid silently assigning an area of `0` to a new shape.

However, `sealed` **does not automatically validate** that width is positive, coordinates are finite, or three triangle vertices form a non-degenerate shape. That is the responsibility of constructors or the data input layer.

## 4. Calculating Area with switch and Record Patterns

The core function in Java 21 can be written as follows:

```java
static double area(Shape shape) {
    double result = switch (shape) {
        case Circle(var center, double radius) ->
                Math.PI * radius * radius;

        case Rectangle(double width, double height) ->
                width * height;

        case Triangle(
                Point(double ax, double ay),
                Point(double bx, double by),
                Point(double cx, double cy)) ->
                Math.abs((bx - ax) * (cy - ay)
                        - (by - ay) * (cx - ax)) / 2.0;

        case null ->
                throw new IllegalArgumentException(
                        "shape must not be null");
    };

    if (!Double.isFinite(result)) {
        throw new ArithmeticException("area is not finite");
    }
    return result;
}
```

This is a logically standalone method, though it requires the records/interface to be declared in the same context. The full version in Section 7 adds validation.

### The Circle Branch

`case Circle(var center, double radius)` is a **record pattern** with two components. The `center` variable is inferred as `Point`, while `radius` has type `double`. The formula only uses the radius because **moving the center does not change the area of a circle**.

The source code does not need a cast like `(Circle) shape`. When the case matches, the compiler knows the `radius` component has type `double`.

Performance note: this pattern still deconstructs `center` even though its value is unused in the formula. For a task that only needs the radius, a type pattern `case Circle circle -> Math.PI * circle.radius() * circle.radius()` can also be appropriate; do not force record patterns in every situation if they do not make the code clearer.

### The Rectangle Branch

`case Rectangle(double width, double height)` checks for the `Rectangle` record and extracts its two components in declaration order. `width * height` returns the area; positive dimensions are enforced by the constructor in the full example.

Do not confuse `record Rectangle(double width, double height)` with a rotated rectangle or two diagonal points without a clear geometric definition. In this article, `width` and `height` are the lengths of the two given perpendicular sides.

### The Triangle Branch: Nested Record Pattern

`Triangle` has three components of type `Point`. We write:

```java
case Triangle(
        Point(double ax, double ay),
        Point(double bx, double by),
        Point(double cx, double cy)) ->
        Math.abs((bx - ax) * (cy - ay)
                - (by - ay) * (cx - ax)) / 2.0;
```

This is a **nested record pattern**: Java checks the `Triangle` type, then deconstructs each `Point` to bind six coordinates. The names `ax`, `ay`, `bx`, `by`, `cx`, `cy` are only in scope within the matched branch.

There is no `new Point(...)` syntax here because a pattern **does not create new objects**. It tests the existing object and extracts components via accessors.

In the complete program, the `Triangle` constructor requires all three `Point` arguments to be non-null, and `Point` requires finite coordinates. This guarantees that valid model input works cleanly with the nested pattern.

### The null Branch and Exhaustiveness

`case null` expresses the policy of **rejecting a null Shape** with an exception carrying a clear message. Do not assume `default` would handle null the same way.

With a `sealed` `Shape` and three record subtypes, a `switch expression` can cover all variants. We do not need `default -> 0.0`, because returning an area of 0 for an unhandled shape would hide a design bug or domain change.

## 5. Validation: Valid Shapes Are a Precondition for the Formula

An accurate area formula can still receive geometrically meaningless input.

### Finite Coordinates

A `Point` using `double` can contain `Double.NaN` or infinity if unchecked. These values cause area calculations to produce results unusable as geometric real numbers. We can validate right inside the compact constructor:

```java
record Point(double x, double y) {
    Point {
        if (!Double.isFinite(x) || !Double.isFinite(y)) {
            throw new IllegalArgumentException(
                    "coordinates must be finite");
        }
    }
}
```

The snippet above is an illustrative record declaration. The compact constructor runs when creating the record normally and rejects non-finite values before a valid object can be constructed.

### Positive Radius and Sides

`Circle` requires a non-null center and `radius > 0`; `Rectangle` requires both sides `> 0`:

```java
record Circle(Point center, double radius) implements Shape {
    Circle {
        java.util.Objects.requireNonNull(center, "center");
        if (!Double.isFinite(radius) || radius <= 0.0) {
            throw new IllegalArgumentException(
                    "radius must be positive and finite");
        }
    }
}

record Rectangle(double width, double height) implements Shape {
    Rectangle {
        if (!Double.isFinite(width) || width <= 0.0
                || !Double.isFinite(height) || height <= 0.0) {
            throw new IllegalArgumentException(
                    "rectangle dimensions must be positive and finite");
        }
    }
}
```

Forbidding zero radius and zero dimensions is a **domain decision in this article**. A CAD application might allow degenerate shapes to represent an in-progress drag state, in which case the validation contract would differ.

### Three Triangle Vertices and the Degenerate Case

`Triangle` requires all three points to be present:

```java
record Triangle(Point a, Point b, Point c) implements Shape {
    Triangle {
        java.util.Objects.requireNonNull(a, "a");
        java.util.Objects.requireNonNull(b, "b");
        java.util.Objects.requireNonNull(c, "c");
    }
}
```

If the three points are collinear, the determinant formula yields an area of `0.0`. In this example, **degenerate triangles are accepted** and `area` returns `0.0`; this is a reasonable illustrative policy for geometric data problems. If the domain requires triangles to have strictly positive area, validation must be added using a well-defined criterion, while also accounting for floating-point error when checking collinearity.

Do not lump all errors into `default -> 0`; you must distinguish a **valid shape whose area is 0 by contract** from an **unknown shape or invalid input**.

## 6. Floating-Point Details: Double, Overflow, and Rounding Error

### Double Does Not Represent Every Number Exactly

`double` uses IEEE 754 binary floating-point arithmetic. Some decimal values have no exact binary representation; `Math.PI` is an approximation of π; and multiplication/subtraction can accumulate rounding error.

Therefore, when comparing calculated areas, **do not mechanically use `expected == actual`** for formulas involving π or multiple `double` operations. Compare errors against a tolerance that makes sense for the units and scale of the data.

Example in tests:

```java
static void assertNear(double expected, double actual) {
    double tolerance = 1e-9 * Math.max(1.0, Math.abs(expected));
    if (!Double.isFinite(actual)
            || Math.abs(expected - actual) > tolerance) {
        throw new AssertionError(
                "expected " + expected + ", actual " + actual);
    }
}
```

This helper is a suitable test pattern for the medium-sized areas in this article; the tolerance value should be chosen based on the application's precision requirements. For computational geometry problems requiring high numerical robustness, more stable orientation/determinant algorithms may be needed rather than just tuning a fixed epsilon.

### Finite Component Values Do Not Guarantee a Finite Area

`new Rectangle(1e308, 1e308)` has two sides that are finite according to `Double.isFinite`, yet the product `width * height` overflows to `Infinity`. Therefore, the example checks the final result:

```java
if (!Double.isFinite(result)) {
    throw new ArithmeticException("area is not finite");
}
```

This check does not make the arithmetic exact by itself; it simply **prevents an infinite or NaN result from being returned as a valid area**.

### The Triangle Formula Can Lose Precision with Extremely Large Coordinates

The expression:

```java
Math.abs((bx - ax) * (cy - ay)
        - (by - ay) * (cx - ax)) / 2.0
```

is simple and accurate for data in normal ranges. With very large coordinates or nearly parallel vectors, subtraction and multiplication can cause **catastrophic cancellation**, overflow, or loss of significant digits. Ultimately, `Math.abs` cannot recover lost information.

If an application handles large-scale maps, high-precision CAD, or nearly degenerate shapes, consider a geometry library with robust orientation predicates, an appropriate coordinate system, and normalized data. This is a numerical issue, not an issue with record patterns themselves.

### Avoiding Integer Overflow Before Converting to double

If components use `int` and we write:

```java
int width = 100_000;
int height = 100_000;
double area = width * height;
```

then the multiplication of two `int` values happens **first**, which can overflow even though the target variable is `double`. We can cast one operand to `double` **before multiplying**:

```java
double area = (double) width * height;
```

In the main case study, `Rectangle` declares `double width` and `double height`, so it does not encounter that `int` overflow, though `double` still has range limits.

## 7. A Complete Java 21 Program

Save the following as **`ShapeAreaRecordPatternDemo.java`**. This file compiles standalone with JDK 21, requiring no preview flags or external libraries.

```java
import java.util.Locale;
import java.util.Objects;

public class ShapeAreaRecordPatternDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    record Point(double x, double y) {
        Point {
            if (!Double.isFinite(x) || !Double.isFinite(y)) {
                throw new IllegalArgumentException(
                        "coordinates must be finite");
            }
        }
    }

    record Circle(Point center, double radius) implements Shape {
        Circle {
            Objects.requireNonNull(center, "center");
            if (!Double.isFinite(radius) || radius <= 0.0) {
                throw new IllegalArgumentException(
                        "radius must be positive and finite");
            }
        }
    }

    record Rectangle(double width, double height) implements Shape {
        Rectangle {
            if (!Double.isFinite(width) || width <= 0.0
                    || !Double.isFinite(height) || height <= 0.0) {
                throw new IllegalArgumentException(
                        "rectangle dimensions must be positive and finite");
            }
        }
    }

    record Triangle(Point a, Point b, Point c) implements Shape {
        Triangle {
            Objects.requireNonNull(a, "a");
            Objects.requireNonNull(b, "b");
            Objects.requireNonNull(c, "c");
        }
    }

    static double area(Shape shape) {
        double result = switch (shape) {
            case Circle(var center, double radius) ->
                    Math.PI * radius * radius;

            case Rectangle(double width, double height) ->
                    width * height;

            case Triangle(
                    Point(double ax, double ay),
                    Point(double bx, double by),
                    Point(double cx, double cy)) ->
                    Math.abs((bx - ax) * (cy - ay)
                            - (by - ay) * (cx - ax)) / 2.0;

            case null ->
                    throw new IllegalArgumentException(
                            "shape must not be null");
        };

        if (!Double.isFinite(result)) {
            throw new ArithmeticException("area is not finite");
        }
        return result;
    }

    static void printArea(String label, Shape shape) {
        System.out.printf(
                Locale.ROOT, "%s = %.2f%n", label, area(shape));
    }

    public static void main(String[] args) {
        printArea("Circle",
                new Circle(new Point(1, 2), 2));

        printArea("Rectangle", new Rectangle(3, 4));

        printArea("Triangle",
                new Triangle(
                        new Point(0, 0),
                        new Point(4, 0),
                        new Point(0, 3)));

        printArea("Triangle translated",
                new Triangle(
                        new Point(10, 10),
                        new Point(14, 10),
                        new Point(10, 13)));

        printArea("Degenerate triangle",
                new Triangle(
                        new Point(0, 0),
                        new Point(1, 1),
                        new Point(2, 2)));

        printArea("Circle moved",
                new Circle(new Point(100, 200), 2));

        try {
            area(null);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "null -> IllegalArgumentException: "
                            + ex.getMessage());
        }

        try {
            new Circle(new Point(0, 0), -1);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "bad radius -> IllegalArgumentException: "
                            + ex.getMessage());
        }

        try {
            area(new Rectangle(1e308, 1e308));
        } catch (ArithmeticException ex) {
            System.out.println(
                    "overflow -> ArithmeticException: "
                            + ex.getMessage());
        }
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 ShapeAreaRecordPatternDemo.java
java ShapeAreaRecordPatternDemo
```

**Standard output:**

```text
Circle = 12.57
Rectangle = 12.00
Triangle = 6.00
Triangle translated = 6.00
Degenerate triangle = 0.00
Circle moved = 12.57
null -> IllegalArgumentException: shape must not be null
bad radius -> IllegalArgumentException: radius must be positive and finite
overflow -> ArithmeticException: area is not finite
```

### Accurate Analysis of Each Case

**Circle:** radius `2` gives area `Math.PI × 4 ≈ 12.56637`, formatted with `%.2f` as `12.57`. Whether the center is `(1,2)` or `(100,200)` does not change the formula.

**Rectangle:** sides `3` and `4` produce an exact area of `12` in this example, printed as `12.00`.

**Triangle:** points `(0,0)`, `(4,0)`, `(0,3)` give a determinant of `12`, divided by two for `6`. The translated triple `(10,10)`, `(14,10)`, `(10,13)` also has a determinant of `12`, so it remains `6`.

**Degenerate triangle:** the three points `(0,0)`, `(1,1)`, `(2,2)` are collinear. The two vectors are parallel, the determinant is `0`, and the area is `0.00`; this case is permitted by the article's validation rules.

**Null:** `area(null)` selects `case null` and throws `IllegalArgumentException` with a specific message. This is an intentional input error, not a new `Shape` subtype.

**Bad radius:** the `Circle` constructor detects `radius <= 0` and rejects it before any area calculation is needed. It does not create a valid `Circle` object with a negative radius.

**Overflow:** `1e308` is still a finite `double`, so the `Rectangle` constructor accepts it. However, the product of the two sides exceeds the finite range of `double`; `area` throws `ArithmeticException` instead of returning infinity.

The examples display areas to two decimal places for readability; in business logic, the `area` method still returns an unrounded `double`. Do not use the formatted string for further precise calculations.

## 8. Why Do Record Patterns Fit This Case Study?

### Reading the Data Shape Directly at Each Case

Looking at:

```java
case Rectangle(double width, double height) -> width * height;
```

the reader immediately sees: this is a rectangle, requiring two dimensions and multiplication. There is no need to scan through multiple lines of casts, intermediate variable declarations, or accessor calls.

For triangles:

```java
case Triangle(
        Point(double ax, double ay),
        Point(double bx, double by),
        Point(double cx, double cy)) -> ...
```

the nested pattern shows that all three vertices are `Point` instances and deconstructs them into coordinates. This representation maps directly to the 2D determinant formula.

### The Compiler Tracks Pattern Variables

`width`, `height`, `ax`, `ay`, etc. have type `double` thanks to the record structure. They only exist within the scope of their respective case. You cannot take `radius` from the `Circle` case and use it in the `Rectangle` case.

The cases are **switch rules** using `->`, with no fall-through; once one case is selected, the area calculation of other cases does not run.

### Easy to Spot Missing Subtypes When Extending the Domain

If `Shape` is extended with `Ellipse`, an exhaustive `switch` without `default` allows the compiler to flag the missing handler. That is why we avoid writing:

```java
// Do not use 0 as a fallback for an unhandled shape type.
default -> 0.0;
```

The snippet above is an illustrative branch example, not a standalone program. In geometry problems, an area of 0 has its own meaning (a degenerate shape), so using it to mean "unknown shape" is especially dangerous.

### Record Patterns Are Not Mandatory for Every Behavior

Another option is to declare `double area()` in the `Shape` interface and let each record implement its own method. That is **polymorphism**, which can also be a good design if calculating area is a core behavior of every shape and there is no need to inspect all subtypes in one place.

Pattern matching is well-suited when we want to write an **external transformation or classification** over a closed set of records; polymorphism may make more sense if the types have many stable behaviors and new subtypes are added frequently. This case study uses record patterns because the focus is **matching geometric structure in Java 21**, not claiming it is always the only right architecture.

## 9. Improvements and Extensions

### 9.1. Triangle from Base and Height

If the domain already knows the base and **perpendicular height** rather than three coordinates, it can be modeled separately:

```java
record BaseHeightTriangle(double base, double height) {}
```

With:

```java
case BaseHeightTriangle(double base, double height) ->
        base * height / 2.0;
```

this is an illustrative branch in a `switch` with a suitably typed selector. To make it an official `Shape`, you must update `permits`, validation, and every place handling the hierarchy—not just arbitrarily add a case that does not match the type system.

Note: `height` must be the altitude perpendicular to the base. If a slanted side is passed under the name `height`, the formula produces a geometrically wrong result even though the code compiles.

### 9.2. Classifying Shapes by Area Using Guards

You can combine `when` when size-based classification is needed, such as a large rectangle:

```java
return switch (shape) {
    case Rectangle(double width, double height)
            when width * height >= 100.0 -> "LARGE_RECTANGLE";
    case Rectangle rectangle -> "OTHER_RECTANGLE";
    case null -> "MISSING";
    default -> "OTHER_SHAPE";
};
```

This illustrates a method returning a string, not the main `area` function. The guard is evaluated after the record pattern matches. For non-`Rectangle` inputs, the guard does not run. The unguarded `Rectangle rectangle` branch follows to handle rectangles with smaller areas.

If area calculation is expensive, avoid repeating the calculation across multiple guards; consider computing `area(shape)` once and classifying the result, while preserving separate error policies for invalid values or overflow.

### 9.3. Shapes with Holes or Composite Shapes

The area of an annulus (ring) can be `π(R²-r²)` when `R >= r >= 0`; the area of a composite shape may require adding or subtracting overlapping regions. Do not assume that summing all component areas is always right: if sub-shapes overlap, a naive sum can **double-count the intersection**.

When adding subtypes such as `Ring` or `CompositeShape`, clearly define the subtype's invariants and formula, then update the sealed hierarchy and tests. This illustrates why a controlled set of subtypes helps identify the impact of domain changes.

## 10. Testing Formulas, Patterns, and Invariants

A good test suite should check **multiple aspects**:

| Test Case | Input | Expected Result / Meaning to Verify |
| --- | --- | --- |
| Circle, small radius | `Circle(center, 2)` | Area close to `4π`. |
| Circle translated center | Same radius `2`, different center | Area unchanged. |
| Rectangle | `Rectangle(3,4)` | Area `12`. |
| Swapped sides | `Rectangle(4,3)` | Area still `12`. |
| Right triangle | `(0,0),(4,0),(0,3)` | Area `6`. |
| Triangle reversed vertex order | Swap `b` and `c` | Area still `6` due to `Math.abs`. |
| Translated triangle | Add same vector to all three points | Area unchanged. |
| Degenerate triangle | `(0,0),(1,1),(2,2)` | `0` per this article's policy. |
| Null center/vertex | `Circle(null, 2)` or `Triangle(null, b, c)` | Rejected when constructing the record. |
| Negative/zero radius | `radius = -1` or `0` | `IllegalArgumentException`. |
| Infinite/NaN coordinates | `Point(Double.NaN, 0)` | `IllegalArgumentException`. |
| Null Shape object | `area(null)` | `IllegalArgumentException`. |
| Area product overflow | `Rectangle(1e308,1e308)` | `ArithmeticException`. |

### Sample Unit Tests with JUnit Jupiter

The example below assumes the `ShapeAreaRecordPatternDemo` class from Section 7 is in the same package as the test file. JUnit Jupiter must be added to the build; this is **not** a file that can be compiled standalone with `javac` when dependencies are missing.

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShapeAreaRecordPatternDemoTest {
    @Test
    void rectangleArea() {
        var rectangle =
                new ShapeAreaRecordPatternDemo.Rectangle(3, 4);
        assertEquals(12.0,
                ShapeAreaRecordPatternDemo.area(rectangle),
                1e-9);
    }

    @Test
    void triangleAreaIsTranslationInvariant() {
        var t1 = new ShapeAreaRecordPatternDemo.Triangle(
                new ShapeAreaRecordPatternDemo.Point(0, 0),
                new ShapeAreaRecordPatternDemo.Point(4, 0),
                new ShapeAreaRecordPatternDemo.Point(0, 3));
        var t2 = new ShapeAreaRecordPatternDemo.Triangle(
                new ShapeAreaRecordPatternDemo.Point(10, 10),
                new ShapeAreaRecordPatternDemo.Point(14, 10),
                new ShapeAreaRecordPatternDemo.Point(10, 13));

        assertEquals(6.0,
                ShapeAreaRecordPatternDemo.area(t1), 1e-9);
        assertEquals(ShapeAreaRecordPatternDemo.area(t1),
                ShapeAreaRecordPatternDemo.area(t2), 1e-9);
    }

    @Test
    void negativeRadiusIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new ShapeAreaRecordPatternDemo.Circle(
                        new ShapeAreaRecordPatternDemo.Point(0, 0),
                        -1));
    }

    @Test
    void nullShapeIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> ShapeAreaRecordPatternDemo.area(null));
    }
}
```

JUnit provides the overload `assertEquals(double expected, double actual, double delta)`, which allows testing floating-point numbers within a tolerance rather than comparing objects or rounded strings.

### Property-Based Testing

In addition to concrete examples, general properties can be tested:

- **Non-negativity:** the area of a valid shape is non-negative by contract.
- **Translation invariance:** moving the circle's center or all three triangle vertices does not change the area.
- **Order symmetry:** swapping rectangle width/height does not change the product; swapping two triangle vertices does not change the absolute area.
- **Uniform scaling:** if all lengths are multiplied by a factor `k > 0`, the ideal area is multiplied by `k²`, within arithmetic bounds that avoid overflow or significant precision loss.

These properties often catch formula bugs that a test with "nice" data misses. When using floating-point numbers, choose an appropriate tolerance and avoid extreme values if the test is not designed to handle them.

## 11. Common Mistakes When Calculating Area with Record Patterns

### 11.1. Forgetting Math.abs for Triangles

`(bx - ax) * (cy - ay) - (by - ay) * (cx - ax)` can be negative when vertex order is reversed. If the goal is a **non-negative** geometric area, you must take the absolute value before dividing by `2`.

### 11.2. Using Wrong Input Data: Height Not Perpendicular to the Base

`base * height / 2` is only correct when `height` is the perpendicular altitude. If the user provides an arbitrary side length, a different formula or vertex coordinates are needed. Record patterns help read components with the right names, but they **do not prove the semantic meaning of a component**.

### 11.3. Treating a Record Pattern as a Constructor

`case Rectangle(double width, double height)` does not create a new `Rectangle` and does not replace constructor validation. It tests the runtime object and accesses the record's components.

### 11.4. Confusing a null Selector with a null Component

`case null` handles `shape == null` itself. Meanwhile, `Triangle(Point(...), ...)` requires the corresponding `Point` components to match; a `null` vertex will cause the nested pattern not to match. In our example, the `Triangle` constructor already rejects null vertices upfront, so valid model data does not hit that case.

A record with a `var` pattern can bind a null reference; do not call `center.x()` without being sure `center` is non-null if the model allows a missing center.

### 11.5. Using default = 0 for Unknown Shapes

That easily hides bugs. If a subtype is added without a formula yet, prefer updating the `switch` or throwing a meaningful error rather than returning a fake area of 0.

### 11.6. Using Integers and Overflowing Before Casting

`double area = width * height` when `width`/`height` are `int` can receive an already overflowed value. Cast one operand to `double` before the multiplication or choose an appropriate data type.

### 11.7. Forgetting That double Has NaN/Infinity

Checking `value > 0` alone is not enough to express all floating-point policies. `Double.isFinite` excludes `NaN` and infinity on input; checking the final result is also necessary when operations can overflow.

### 11.8. Comparing double with == in All Tests

A calculation involving π or multiple multiplications/subtractions often introduces floating-point error. Use a tolerance meaningful for the scale of the data.

### 11.9. Overusing Nested Patterns

In domains with deeply nested records where only one component is needed, a long nested pattern can hurt readability or deconstruct unused components. You can use a type pattern and the needed accessors; good design prioritizes **code clarity and correctness** before syntactic cleverness.

### 11.10. Confusing Record Pattern Performance with Formula Performance

A benchmark showing that an area function is slow does not prove the pattern is at fault: the cost may come from floating-point math, object allocation, complex guards, or the test workload. Use a profiler or JMH if you genuinely need performance analysis; do not guess from lines of Java code.

## 12. Self-Check Exercises

**Question 1.** A circle has radius `3`. What is the area formula and its approximate value?

**Answer:** `A = π × 3² = 9π ≈ 28.27433388`. Formatted to two decimal places, this is `28.27`.

**Question 2.** Do the three vertices `(0,0)`, `(0,4)`, `(3,0)` yield a negative or positive value before `Math.abs`?

**Answer:** With `a=(0,0)`, `b=(0,4)`, `c=(3,0)`: `(bx-ax)(cy-ay)-(by-ay)(cx-ax) = 0*0 - 4*3 = -12`. Taking the absolute value and dividing by two gives an area of `6`.

**Question 3.** Why is `case Triangle(Point(double ax, double ay), ... )` called a nested record pattern?

**Answer:** Because the outer pattern matches the `Triangle` record, and each `Point` component is further matched by an **inner record pattern** to extract its coordinates.

**Question 4.** What needs to be done when adding `record Ellipse(double a, double b) implements Shape` to the domain?

**Answer:** First, extend `permits` on `Shape`, define the invariant `a,b > 0`, add the formula `A = πab` to the `switch`, and add tests. With a sealed hierarchy, failing to handle the new subtype in a `switch expression` without `default` will be caught by the compiler upon recompilation.

**Question 5.** Is `Triangle(0,0),(1,1),(2,2)` an error?

**Answer:** These are three collinear points, giving an area of `0`. Whether it is rejected depends on the domain contract. The demo program accepts degenerate triangles and returns `0.00`.

**Question 6.** Does `case Circle(var center, double radius)` guarantee `center != null`?

**Answer:** By itself, `var center` can bind a null reference. In this program, it is the **`Circle` constructor** with `Objects.requireNonNull(center)` that ensures valid objects have a non-null center. Record patterns do not replace validation.

## 13. Practical Application Checklist

Before implementing an area calculator using record patterns:

1. Establish a consistent coordinate system, length unit, and area unit.
2. Define shape subtypes and clear **data invariants**; choose `sealed` when the set of shapes is under your control.
3. Write the right mathematical formulas; for a triangle from three points, use the determinant and `Math.abs`.
4. Choose record patterns / nested record patterns when they help readers see the data structure being handled.
5. Check for `null` on the selector and on reference components that might be missing.
6. Do not use `default -> 0.0` just to paper over a subtype that lacks a formula yet.
7. Check `Double.isFinite` for inputs and results when the contract requires a finite area.
8. Test sample values, degenerate shapes, vertex order swaps, translations, and invalid inputs.
9. Use a well-reasoned tolerance when comparing `double` areas.
10. Compile with JDK 21 and run tests; record patterns and pattern matching for `switch` have been standard since Java 21, requiring no `--enable-preview`.

**Remember:** In Java 21, record patterns let you write area calculations close to the mathematical model: `Circle(radius)` uses `πr²`, `Rectangle(width,height)` uses `width×height`, and `Triangle(Point,Point,Point)` uses the coordinate determinant. **Getting the formula right** is only part of the job; **getting types, nulls, validation, and arithmetic right** is what makes an area calculator reliable.
