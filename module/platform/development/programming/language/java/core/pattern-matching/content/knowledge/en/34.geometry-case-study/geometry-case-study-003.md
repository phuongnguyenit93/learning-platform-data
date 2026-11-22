# Calculating Perimeter with Pattern Switch in Java 21 — Geometry Case Study

## 1. Problem Statement and Goals

A geometry application may receive many kinds of shapes: circles, rectangles, and triangles. Each shape has its own data and **perimeter formula**. If we use a common `Shape` type, we need a `perimeter(Shape shape)` method that handles the right shape type at runtime, returns the perimeter as a `double`, and reports an error when the data is invalid.

With Java 21, **pattern matching for `switch`** lets us combine type-based selection with **record patterns** to extract dimensions directly. Instead of chained `instanceof` checks, casts, and accessor calls, a single `switch expression` can cleanly express the entire “shape → perimeter” mapping.

This lesson walks through:

- Modeling shapes with `record`s and a `sealed interface Shape`.
- Applying the right perimeter formulas for circles, rectangles, the square case, and triangles.
- Writing `return switch (shape) { ... };` with record patterns `Circle(var r)`, `Rectangle(var w, var h)`, and `Triangle(var a, var b, var c)`.
- Understanding `when`, case ordering, `null`, and **exhaustiveness** when the hierarchy is `sealed`.
- Guarding against invalid dimensions: negative values, zero, `NaN`, infinity, triangles violating the triangle inequality, and results that overflow to infinity.
- Testing both valid formulas and error paths; formatting floating-point numbers and choosing appropriate comparison tolerances.

**Version milestone:** `record` and type patterns for `instanceof` have been standard features since Java 16; **record patterns** (JEP 440) and **pattern matching for switch** (JEP 441) became standard features in **Java 21**. The complete program in this lesson uses `javac --release 21` and **does not require `--enable-preview`**.

## 2. Perimeter Formulas and Data Assumptions

The perimeter is the length of the boundary of a flat shape. In our examples, dimensions share a common **unit of length** (such as cm), so the resulting perimeter is in that same unit. We do not attach a fixed `cm` label to the `double` type because the API does not yet have a type representing units.

| Shape | Required Data | Perimeter Formula | Example |
| --- | --- | --- | --- |
| Circle | Radius `r > 0` | `P = 2 × π × r` | `r = 2` → `4π ≈ 12.57` |
| Rectangle | Width `w > 0`, height `h > 0` | `P = 2 × (w + h)` | `w = 3, h = 4` → `14` |
| Square | Side `s > 0` | `P = 4 × s` | `s = 5` → `20` |
| Triangle | Three sides `a, b, c > 0` satisfying the triangle inequality | `P = a + b + c` | `a = 3, b = 4, c = 5` → `12` |

A square is a special case of a rectangle where `width == height`. In the main model, we **do not declare a separate `Square` record**, but instead demonstrate how to use a `Rectangle` branch with a `when w == h` guard and apply `4 * w`. The unguarded `Rectangle` branch that follows handles all remaining rectangles.

In the example program, dimensions are treated as **positive, finite values**; triangles must be non-degenerate. This is the data policy for this lesson, not a mandatory rule for every geometry application. If you want to allow degenerate shapes or a circle of radius 0 in another application, you should explicitly adjust the contract and tests.

### 2.1. The Triangle Inequality

Three positive sides form a non-degenerate triangle when **all** of the following hold simultaneously:

```text
a + b > c
a + c > b
b + c > a
```

For example, `3, 4, 5` is valid. However, `1, 2, 3` is invalid because `1 + 2 == 3`: the three segments are merely collinear and do not form a non-degenerate triangle. Checking only that the three sides are positive is **not enough**.

### 2.2. Do Not Confuse Perimeter with Area

This is a common mistake in geometry case studies:

- Circle: **perimeter** (circumference) is `2πr`, not **area** `πr²`.
- Rectangle: **perimeter** is `2(w+h)`, not **area** `w × h`.
- Triangle: **perimeter** is `a+b+c`; neither height nor Heron's formula is needed.

Before writing a `switch`, lock down the mathematical formulas; pattern matching only decides **which formula to pick**, and does not guarantee that the formula itself is right.

## 3. Modeling Geometry with a Sealed Interface and Records

We define a common parent type:

```java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record Triangle(double a, double b, double c) implements Shape {}
```

What this means:

1. `Shape` represents a group of shapes that the API can handle.
2. `sealed` and `permits Circle, Rectangle, Triangle` specify the allowed direct implementations.
3. Each `record` holds the exact data needed for its perimeter formula and automatically provides accessors such as `radius()`, `width()`, and `a()`.
4. Records are `final` by nature, so this trio forms a clearly closed type hierarchy that the compiler can analyze for exhaustiveness.

The definition above only illustrates the structure and **does not yet include validation**. The complete program in Section 7 adds compact constructors to reject invalid dimensions as soon as a shape is created.

### Why Choose `sealed`?

If you write a `switch expression` over a `Shape` parameter and provide cases for all three records, Java 21 can conclude that all non-null `Shape` values are covered, **without needing `default`**.

If you later extend the hierarchy by adding `Polygon` to `permits` and recompile, the compiler can force you to update any `switch expression` that is missing a case. This is a significant advantage over an `if/else` chain with a silent fallback branch.

If `Shape` were an open interface allowing arbitrary implementations, the compiler could not rely on such a closed list; in that case, the `switch expression` would need a catch-all branch (such as `default`) or a different dispatch design.

## 4. Core Logic: Calculating Perimeter with Switch Expressions and Record Patterns

With the `Shape` records declared, the main method can be written as follows:

```java
static double perimeter(Shape shape) {
    return switch (shape) {
        case null -> throw new IllegalArgumentException("shape must not be null");
        case Circle(var r) -> 2.0 * Math.PI * r;
        case Rectangle(var w, var h) when w == h -> 4.0 * w;
        case Rectangle(var w, var h) -> 2.0 * (w + h);
        case Triangle(var a, var b, var c) -> a + b + c;
    };
}
```

This is a **`switch expression`**, not a traditional `switch statement`. The entire `switch (shape) { ... }` expression has result type `double`, which is returned directly via `return`. Each arrow branch `->` provides either an expression computing the perimeter or throws an exception.

### 4.1. Record Patterns Extract Dimensions Directly

- `case Circle(var r)` checks that `shape` is a `Circle` and binds `r` from the `radius` component.
- `case Rectangle(var w, var h)` extracts the two components `width` and `height`.
- `case Triangle(var a, var b, var c)` extracts all three side components.

The `var` keyword here **does not mean the data becomes dynamically typed**. The compiler infers the variables as `double` from the record declaration. Pattern variables are only in scope within the matching guard and branch, and do not leak into other cases.

A record pattern must have the **exact number of component positions in the exact order**. `Rectangle(var w)` is invalid because `Rectangle` has two components. If you only need one component, in Java 21 you can write `var ignoredHeight` for the remaining position; the unnamed pattern `_` only became standard in Java 22.

### 4.2. Why Are There Two `Rectangle` Cases?

```java
case Rectangle(var w, var h) when w == h -> 4.0 * w;
case Rectangle(var w, var h) -> 2.0 * (w + h);
```

Both type patterns match `Rectangle`. The first branch has a **`when w == h` guard** to highlight the square case. If the condition is false, Java continues checking the unguarded `Rectangle` branch below it.

Examples:

- `Rectangle(5,5)` → guard is true → `4 × 5 = 20`.
- `Rectangle(3,4)` → guard is false → `2 × (3+4) = 14`.

**Order matters:** The unguarded `Rectangle` branch must come **after** the guarded branch. If you place the general `Rectangle` case first, it covers every `Rectangle`; the guarded `when` case after it is **dominated**, and the compiler will reject it.

Keep in mind that this is meant to illustrate the `when` mechanism. In a real application, `2.0*(w+h)` is also correct for a square; if you do not need to distinguish squares, a single `Rectangle` case is **simpler without sacrificing correctness**.

**Note on floating-point comparison:** `w == h` is only suitable for demonstration when both values are constructed with exact values like `5.0` and `5.0`. For measured values with rounding or measurement error, you should not use exact equality to decide whether two sides are equal. You can either apply a tolerance rule defined by business requirements, or omit the square-specific branch altogether since the general formula is already accurate.

### 4.3. The `null` Branch

```java
case null -> throw new IllegalArgumentException("shape must not be null");
```

This is an API design decision: passing `null` is a caller error, so the method **throws an exception with a clear message**. A display-oriented API might choose to return `0` or an `OptionalDouble` instead of throwing; either way, the contract must be clearly defined and tested.

Do not assume `default` handles `null`. In Java 21, a pattern switch without explicit `null` handling throws a `NullPointerException` when the selector is `null`.

### 4.4. Exhaustiveness on Sealed `Shape`

The unguarded patterns `Circle(...)`, `Rectangle(...)`, and `Triangle(...)` together cover the entire permitted `Shape` hierarchy. The guarded `Rectangle` branch only handles a specific case; it is the **unguarded `Rectangle` branch** that guarantees rectangles with unequal sides are not missed.

If you remove the `Triangle` branch without adding another way to cover it, the `switch expression` is no longer exhaustive and the compiler reports an error. Similarly, if you keep only the `Rectangle` branch with `when w==h` and remove the general `Rectangle` branch, non-square rectangles would have no matching case, and the compiler would also detect the lack of exhaustiveness.

## 5. Why Validate Dimensions Before Computing?

A `record Circle(double radius)` does not automatically forbid `radius=-2` or `Double.NaN`. Likewise, a `record Triangle(double a,double b,double c)` does not automatically enforce the triangle inequality. Without validation, formulas could produce negative perimeters, `NaN`, or infinity, causing bugs to surface much later downstream.

In Java, a record's compact constructor is the right place to establish invariants:

```java
record Circle(double radius) implements Shape {
    Circle {
        positiveFinite("radius", radius);
        finitePerimeter(2.0 * Math.PI * radius);
    }
}
```

Helper methods in the enclosing class:

```java
static void positiveFinite(String field, double value) {
    if (!Double.isFinite(value) || value <= 0) {
        throw new IllegalArgumentException(field + " must be positive and finite");
    }
}

static void finitePerimeter(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("perimeter overflow");
    }
}
```

`Double.isFinite(value)` rejects `NaN`, `Double.POSITIVE_INFINITY`, and `Double.NEGATIVE_INFINITY`. The condition `value <= 0` rejects `0`, `-0.0`, and negative numbers according to our problem policy. We then check the perimeter to reject calculations that overflow to infinity even when each individual input dimension is finite.

For rectangles:

```java
record Rectangle(double width, double height) implements Shape {
    Rectangle {
        positiveFinite("width", width);
        positiveFinite("height", height);
        finitePerimeter(2.0 * (width + height));
    }
}
```

For triangles:

```java
record Triangle(double a, double b, double c) implements Shape {
    Triangle {
        positiveFinite("a", a);
        positiveFinite("b", b);
        positiveFinite("c", c);
        if (!(a + b > c && a + c > b && b + c > a)) {
            throw new IllegalArgumentException("triangle inequality violated");
        }
        finitePerimeter(a + b + c);
    }
}
```

These are **code snippets that make up the complete program in Section 7**, not separate standalone Java files. Placing validation in the constructors ensures that every shape object created through them is validated immediately upon instantiation.

### 5.1. Why Still Check That the Computed Result Is Finite?

A positive finite `double` can be very large. For example, `Double.MAX_VALUE` is finite, yet `2 * Math.PI * Double.MAX_VALUE` becomes infinity because it exceeds the `double` range. If you only validate the radius with `Double.isFinite`, the perimeter can still be non-finite.

This lesson's example prevents that situation with `finitePerimeter(...)`. When a system needs to handle extremely large dimensions or requires unusual precision, you may need to revisit the data domain and numeric types; you should not assume `double` can accurately represent every length.

### 5.2. Validate Upfront or Compute and Report Errors?

Two common design approaches are:

- **Validation in the constructor:** valid objects are guaranteed at creation time; the perimeter method can stay concise and focused on the formula. This is the approach used in the complete program.
- **Validation in the `perimeter` method:** convenient when receiving records whose constructors you do not control or when working with legacy APIs, but requires repeating checks if multiple operations are performed on the same shape.

You should avoid doing both unnecessarily. If the constructor is always used properly and record data is not mutated after initialization, constructor validation is a natural choice. If data can arrive via reflection, serialization/frameworks, or other mechanisms, you still need validation at the appropriate trust boundary.

## 6. How a Shape Flows Through the Pattern Switch

Consider:

```java
Shape shape = new Rectangle(3, 4);
double value = perimeter(shape);
```

Execution flow:

1. The `Rectangle(3,4)` constructor validates that both sides are positive and finite, and that the perimeter does not overflow.
2. `switch (shape)` evaluates patterns in order.
3. `case null` does not match; `Circle(...)` does not match.
4. `Rectangle(var w,var h)` matches and binds `w=3`, `h=4`.
5. The guard `w == h` is false, so Java does not select the `4*w` branch.
6. The next unguarded `Rectangle(var w,var h)` branch matches and returns `2*(3+4)=14`.
7. `return switch(...)` returns a `double` with value `14.0`.

For `new Triangle(3,4,5)`, the `Triangle` branch receives the three sides and returns `12.0`. For `new Circle(2)`, the formula returns `4π ≈ 12.566370614...`; the display layer can round it to `12.57`.

**Separate computation from formatting:** Keep the result as a `double` for any subsequent calculations. Only format to two decimal places when outputting for human readers; do not replace the real perimeter with a string or round early if the system needs to compute further with it.

## 7. Complete Java 21 Program: Calculating Perimeter and Testing Inputs

Create a single file named **`ShapePerimeterDemo.java`**:

```java
public class ShapePerimeterDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    static void positiveFinite(String field, double value) {
        if (!Double.isFinite(value) || value <= 0) {
            throw new IllegalArgumentException(field + " must be positive and finite");
        }
    }

    static void finitePerimeter(double value) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("perimeter overflow");
        }
    }

    record Circle(double radius) implements Shape {
        Circle {
            positiveFinite("radius", radius);
            finitePerimeter(2.0 * Math.PI * radius);
        }
    }

    record Rectangle(double width, double height) implements Shape {
        Rectangle {
            positiveFinite("width", width);
            positiveFinite("height", height);
            finitePerimeter(2.0 * (width + height));
        }
    }

    record Triangle(double a, double b, double c) implements Shape {
        Triangle {
            positiveFinite("a", a);
            positiveFinite("b", b);
            positiveFinite("c", c);
            if (!(a + b > c && a + c > b && b + c > a)) {
                throw new IllegalArgumentException("triangle inequality violated");
            }
            finitePerimeter(a + b + c);
        }
    }

    static double perimeter(Shape shape) {
        return switch (shape) {
            case null -> throw new IllegalArgumentException("shape must not be null");
            case Circle(var r) -> 2.0 * Math.PI * r;
            case Rectangle(var w, var h) when w == h -> 4.0 * w;
            case Rectangle(var w, var h) -> 2.0 * (w + h);
            case Triangle(var a, var b, var c) -> a + b + c;
        };
    }

    static int passed;

    static void assertNear(String label, double expected, double actual) {
        if (Math.abs(expected - actual) > 1e-9) {
            throw new AssertionError(
                label + ": expected " + expected + ", got " + actual
            );
        }
        passed++;
        System.out.println(
            "PASS " + label + " = "
            + String.format(java.util.Locale.ROOT, "%.2f", actual)
        );
    }

    static void assertReject(String label, Runnable code, String expectedMessage) {
        try {
            code.run();
            throw new AssertionError(label + ": expected rejection");
        } catch (IllegalArgumentException error) {
            if (!expectedMessage.equals(error.getMessage())) {
                throw new AssertionError(
                    label + ": wrong message " + error.getMessage()
                );
            }
            passed++;
            System.out.println("PASS " + label + " -> " + error.getMessage());
        }
    }

    public static void main(String[] args) {
        assertNear("circle r=2", 4.0 * Math.PI, perimeter(new Circle(2)));
        assertNear("rectangle 3x4", 14.0, perimeter(new Rectangle(3, 4)));
        assertNear("square rectangle 5x5", 20.0, perimeter(new Rectangle(5, 5)));
        assertNear("triangle 3-4-5", 12.0, perimeter(new Triangle(3, 4, 5)));

        assertReject(
            "zero radius", () -> new Circle(0),
            "radius must be positive and finite"
        );
        assertReject(
            "negative width", () -> new Rectangle(-2, 3),
            "width must be positive and finite"
        );
        assertReject(
            "invalid triangle", () -> new Triangle(1, 2, 3),
            "triangle inequality violated"
        );
        assertReject(
            "NaN radius", () -> new Circle(Double.NaN),
            "radius must be positive and finite"
        );
        assertReject(
            "overflow", () -> new Circle(Double.MAX_VALUE),
            "perimeter overflow"
        );
        assertReject(
            "null shape", () -> perimeter(null),
            "shape must not be null"
        );

        System.out.println("checks=" + passed);
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 ShapePerimeterDemo.java
java ShapePerimeterDemo
```

**Exact output** (decimal point fixed with `Locale.ROOT`):

```text
PASS circle r=2 = 12.57
PASS rectangle 3x4 = 14.00
PASS square rectangle 5x5 = 20.00
PASS triangle 3-4-5 = 12.00
PASS zero radius -> radius must be positive and finite
PASS negative width -> width must be positive and finite
PASS invalid triangle -> triangle inequality violated
PASS NaN radius -> radius must be positive and finite
PASS overflow -> perimeter overflow
PASS null shape -> shape must not be null
checks=10
```

This is a self-checking program **requiring no JUnit or external dependencies**. The `assertNear` helper throws `AssertionError` if the difference exceeds `1e-9` for these small-dimension examples; it prints `PASS` only when the formula matches the expected result. The `assertReject` helper verifies that constructing a shape or calling `perimeter` actually throws `IllegalArgumentException` with the expected message.

**10 checks** cover four perimeter cases and six error cases: zero radius, negative width, degenerate triangle, `NaN` radius, overflow result, and `null` selector. The `checks=10` line does not claim that the entire `double` domain or all geometric cases have been tested; it confirms the specific cases defined by the program.

### 7.1. Explaining the 4 Successful Perimeter Cases

- `Circle(2)`: `2π × 2 = 4π ≈ 12.566...` → displayed as `12.57`.
- `Rectangle(3,4)`: `2(3+4) = 14` → `14.00`.
- `Rectangle(5,5)`: guard `w==h` is true, `4 × 5 = 20` → `20.00`.
- `Triangle(3,4,5)`: valid because all three pairwise sums exceed the remaining side, `3+4+5=12` → `12.00`.

### 7.2. Explaining the 6 Invalid Input Cases

- `Circle(0)` cannot be constructed; the compact constructor rejects `0` per the positive-radius policy.
- `Rectangle(-2,3)` is rejected due to a negative width.
- `Triangle(1,2,3)` is rejected because `1+2 == 3`, failing the strict `>` check.
- `Circle(Double.NaN)` is rejected via `Double.isFinite`.
- `Circle(Double.MAX_VALUE)` has a finite radius, but `2πr` exceeds the `double` range, so it is rejected due to overflow.
- `perimeter(null)` hits `case null` and throws an error per the contract. It is **not** interpreted as a shape with perimeter `0`.

Dimension validation lives in the constructors, while `null shape` handling lives in the `switch`, because `null` is not a record instance with a constructor to run checks.

## 8. Comparing Pattern Switch with `instanceof` and Virtual Dispatch

### 8.1. The Older `instanceof` Approach

Without record patterns in `switch`, you could write:

```java
// Snippet located inside the same class as Shape/Circle/Rectangle/Triangle.
static double perimeterWithIf(Shape shape) {
    if (shape == null) throw new IllegalArgumentException("shape must not be null");
    if (shape instanceof Circle circle) {
        return 2.0 * Math.PI * circle.radius();
    }
    if (shape instanceof Rectangle rectangle) {
        return 2.0 * (rectangle.width() + rectangle.height());
    }
    if (shape instanceof Triangle triangle) {
        return triangle.a() + triangle.b() + triangle.c();
    }
    throw new IllegalStateException("Unknown shape");
}
```

This approach can be correct and is even suitable for code targeting Java 17. It uses type patterns for `instanceof` and accessors, rather than deconstruction patterns. Drawbacks: the final branch requires a manual fallback, and the compiler does not prove exhaustiveness of the `if` chain when the hierarchy changes.

The Java 21 `switch expression` lists the set of shapes at the same level and has its exhaustiveness checked by the compiler thanks to the sealed hierarchy.

### 8.2. Is Virtual Dispatch Always Worse?

No. Traditional object-oriented design can also declare `double perimeter()` on `Shape` and let each record implement its own calculation. That is **polymorphism**, which works well when computing perimeter is core behavior of each shape and the type hierarchy is frequently extended with new classes.

Pattern `switch` is especially convenient when you have **a classification or transformation over a closed set of subtypes**, or when you want to process record data in a service layer independent of the data model. If an application adds many operations such as area, perimeter, serialization, and rendering, weigh responsibilities and architecture carefully: avoid creating lots of giant `switch` statements repeating over the same hierarchy.

Choose pattern `switch` for clarity and exhaustiveness, **not because it is always faster** than virtual dispatch or `if`. If performance matters, benchmark with realistic workloads.

## 9. `when`, `yield`, and Switch Variants

In the main program, each case is a short expression, so `yield` is not needed. If a case needs multiple statements for intermediate calculations, Java 21 allows a block with `yield`:

```java
// Snippet replacing the Triangle branch in a switch expression:
case Triangle(var a, var b, var c) -> {
    double sum = a + b + c;
    yield sum;
}
```

`yield` returns a **value for the switch expression**, whereas `return` returns from the **enclosing method**. Do not use `return sum;` instead of `yield sum;` inside a switch expression block. For single-expression cases, the `-> expression` form is easier to read.

A `when` guard belongs to the **case label**, not an `if` running outside it:

```java
case Rectangle(var w, var h) when w == h -> 4.0 * w;
case Rectangle(var w, var h) -> 2.0 * (w + h);
```

If the guard is false, the general `Rectangle` branch below still gets a chance to match. Therefore, **branch coverage analysis** should test both: a square and a non-square rectangle.

### When Should You Use `default`?

With a sealed `Shape` consisting of three records that are all handled, `default` is not needed. If you add:

```java
default -> throw new IllegalArgumentException("unknown shape");
```

then the compiler will no longer force you to handle a new subtype when the hierarchy changes, because `default` would cover it. If your primary goal is **compile-time exhaustiveness**, keep cases explicit and omit `default` when the type hierarchy allows it.

Conversely, if the input is an `Object` coming from external data rather than restricted to sealed `Shape`, you need an appropriate fallback for non-`Shape` types. You cannot blindly apply the no-`default` approach of a `Shape` selector to an `Object` selector.

## 10. `double` Precision and Testing Perimeters

### 10.1. `Math.PI` Is a Floating-Point Approximation

Java provides `Math.PI` as a `double` constant approximating π. Consequently, `perimeter(new Circle(2))` is a `double` close to `12.566370614...`, not an exact number with infinitely many digits.

When displaying it:

```java
System.out.println(
    String.format(java.util.Locale.ROOT, "%.2f", 4.0 * Math.PI)
);
```

the output is `12.57`. Choosing `Locale.ROOT` in the example keeps the decimal separator and formatting consistent across environments; user-facing display settings may need the user's locale.

### 10.2. Do Not Compare `double` with `==` When Testing Approximate Math

For calculations involving π or multiple floating-point additions/subtractions, a test suite can use an allowed tolerance:

```java
double actual = perimeter(new Circle(2));
double expected = 4.0 * Math.PI;

if (Math.abs(expected - actual) > 1e-9) {
    throw new AssertionError("perimeter mismatch");
}
```

This snippet illustrates testing with small-scale values. A fixed absolute tolerance of `1e-9` **is not suitable for all scales**. For large values or many operations, you can combine absolute and relative tolerances according to your domain contract:

```java
// Illustrative snippet for two finite double results.
double tolerance = Math.max(1e-9, Math.abs(expected) * 1e-12);
if (Math.abs(actual - expected) > tolerance) {
    throw new AssertionError("perimeter mismatch");
}
```

If `actual` or `expected` could be `NaN` or infinite, check `Double.isFinite` separately; comparisons based on `Math.abs` do not automatically catch every `NaN` case. The main program places validation in the constructors to block non-finite dimensions or perimeters.

### 10.3. Keep Units Consistent

If a radius is entered in cm while a rectangle's sides are entered in m, you cannot compare their perimeters directly without converting to the same unit. The `double` type itself **carries no unit information**. In larger systems, you can create a value object representing length/unit and convert at API boundaries.

Do not confuse the perimeter formula `2πr` with `πr²` when writing tests. Testing a result like `12.57` for `r=2` helps catch a wrong formula, though you still need cases with other dimensions to avoid coincidental matches (since `2πr == πr²` when `r = 2`).

## 11. Common Pitfalls in This Case Study

| Pitfall | Consequence | Fix / How to Test |
| --- | --- | --- |
| Using `Math.PI * r * r` for perimeter | Computes the circle's area instead. | Use `2 * Math.PI * r`; test `r=2` and another radius. |
| Using `w * h` for rectangle | Computes area instead of perimeter. | Use `2 * (w+h)`; test `3×4 → 14`. |
| Using `a+b+c` without checking triangle validity | Accepts `1,2,3` as a non-degenerate triangle. | Check all three sides are positive and satisfy the triangle inequality. |
| Checking only `> 0` without checking `NaN` | With `NaN`, ordering comparisons can fail to detect invalid values. | Use `Double.isFinite(value)` together with the positive check. |
| Checking only finite inputs and ignoring result overflow | Perimeter can become infinity. | Validate `Double.isFinite(perimeter)` within the supported domain. |
| Placing general `Rectangle` before guarded `Rectangle` with `when` | The guarded case is dominated, causing a compile-time error. | Place specific guarded cases before general cases. |
| Having only `case Rectangle(...) when w==h` | Misses non-square rectangles; may be non-exhaustive. | Add an unguarded `Rectangle` branch. |
| Omitting `Triangle` without another covering case | Switch expression on sealed `Shape` is incomplete. | Handle every subtype. |
| Adding `default` to hide missing subtypes | Gives up compiler reminders when adding new shapes. | For closed hierarchies, prefer explicit cases. |
| Not handling a `null` selector per the contract | Can throw an unexpected NPE. | Use `case null` with the intended error or result, and test it. |
| Using `w == h` to classify noisy measured data | Misclassifies near-squares. | Use the general `Rectangle` formula or an explicit tolerance rule. |
| Using `return` instead of `yield` in a switch expression block | Wrong value-returning model for switch expressions. | Use `yield` for multi-statement blocks, and `-> expression` for short cases. |
| Testing against rounded strings instead of numeric values | Masks precision errors or fails under unexpected locales. | Assert `double` results with tolerance; format only in the display layer. |
| Using Java 17 to compile standard Java 21 record patterns | Compiler does not support deconstruction patterns at source 17. | Use JDK/source 21, or type patterns + accessors. |

## 12. Hands-On Exercises: Extending the Case Study

### Exercise A — Add Square as Its Own Subtype

Suppose an application wants to model `Square` as a distinct shape type rather than just a `Rectangle` with equal sides.

Requirements:

1. Add `record Square(double side) implements Shape` and validate that `side` is positive and finite, and that `4*side` is finite.
2. Add `Square` to `Shape`'s `permits` list.
3. Add `case Square(var side) -> 4.0*side;` to the perimeter `switch expression`.
4. Test that `Square(5) -> 20.0` and `Square(0)` is rejected.

Component code hint (not a standalone file; requires updating the sealed interface and switch in the main example):

```java
record Square(double side) implements Shape {
    Square {
        positiveFinite("side", side);
        finitePerimeter(4.0 * side);
    }
}

// Inside the perimeter switch expression:
case Square(var side) -> 4.0 * side;
```

**Why must `permits` also be updated?** A sealed interface only allows its declared implementations. Adding a subtype means the compiler must know about the new member, and exhaustive switches can require updates for the new subtype. That is a key benefit of a closed model.

### Exercise B — Calculating Equilateral Triangle Perimeter with a Guarded Case

An application wants to distinguish equilateral triangles in its display logic. Write:

```java
case Triangle(var a, var b, var c) when a == b && b == c -> 3.0 * a;
case Triangle(var a, var b, var c) -> a + b + c;
```

These cases are a replacement snippet for the `Triangle` case in the existing `switch expression`, not two standalone statements. For an equilateral triangle with exact equal sides in data, both formulas are equivalent. However, as with squares, exact equality should not be used to classify noisy measured values without a tolerance contract.

Tests:

- `Triangle(3,3,3)` → `9.0`, guard is true.
- `Triangle(3,4,5)` → `12.0`, guard is false, general case matches.
- `Triangle(1,2,3)` → rejected by constructor; you cannot test the perimeter of an object that cannot be created through this API.

### Exercise C — Do Not Mix Up Perimeter and Area

Write an additional `area(Shape shape)` method using its own formulas:
- Circle: `πr²`.
- Rectangle: `w×h`.
- Triangle: Heron's formula with semi-perimeter `s=(a+b+c)/2`.

**Note:** This is an extension exercise, separate from **calculating perimeter**. Heron's formula has numerical stability considerations for floating-point numbers and very thin triangles that warrant extra care. Do not use `area` in place of `perimeter`, and do not put area formulas into perimeter switch cases.

## 13. Design and Review Checklist

When finalizing a pattern-switch-based perimeter API:

1. Confirm the shape types and **perimeter formulas**, and standardize units.
2. Use `record`s to hold dimensions and consider a `sealed Shape` if the set of shapes is closed.
3. Place validation for sides/radius at the object-creation boundary or data-receiving method; do not assume a record automatically blocks negative or `NaN` dimensions.
4. Write a `switch expression` returning `double` with record patterns covering all components.
5. If using `when`, place guarded cases before unguarded cases of the same type, and ensure both true and false paths are covered.
6. With a sealed hierarchy where all subtypes have explicit cases, avoid adding an unconditional `default` if you want the compiler to flag missing new subtypes.
7. Decide clearly what happens when `shape == null`; test the exact exception or result per contract.
8. Check for overflow and `double` floating-point behavior; format only in the display layer.
9. Include tests for circles, non-square rectangles, squares, valid triangles, boundary values, and invalid dimensions.
10. Compile with Java 21 for standard record patterns, run tests on a matching runtime, and review behavior when adding new subtypes.

**Key takeaway:** Pattern `switch` turns a **`Shape` type hierarchy** into a clear **"each shape → perimeter formula"** mapping that is easy to check for exhaustiveness. Yet geometric correctness still depends on the **formulas**, **data invariants**, **units**, **floating-point limits**, and **error-case testing**. A good design leverages the compiler's strengths without equating "code compiles" with "perimeter is always right."

**References:**
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java SE 21 Language Specification — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
- [Java SE 21 Math API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html).
