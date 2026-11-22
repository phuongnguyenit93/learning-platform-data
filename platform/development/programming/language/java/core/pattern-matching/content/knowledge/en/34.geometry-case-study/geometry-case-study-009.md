# Testing All Shapes with Pattern Matching in Java 21

## 1. Case Study Objectives

In a geometry program, we often have multiple shape types but want to provide **a unified processing interface**: accept a shape object, compute its area and perimeter, classify it, detect invalid data, and return verifiable results.

Java 21 supports this model with **sealed interfaces**, **records**, **record patterns**, **pattern matching for switch**, and **`when` guards**. However, writing a clean `switch` does not automatically mean it is thoroughly tested. A reliable test suite must answer:

1. **Is every shape type handled?** Are `Circle`, `Rectangle`, `Square`, or `Triangle` omitted?
2. **Are the formulas correct?** Do area and perimeter match known examples and geometric relationships?
3. **Are boundary inputs defined?** Zero or negative radius, negative side, collinear triangle, or duplicate vertices?
4. **How are special `double` values handled?** `NaN`, `Infinity`, overflow, loss of precision?
5. **Is `null` handled in the selector or nested records?**
6. **Are patterns ordered properly and exhaustive?** Does the compiler detect dominated cases or missing subtypes?
7. **Do the tests prove observable behavior?** Return values, exceptions, guarded branches, and invariant properties?

This article builds a **standalone test suite, runnable on JDK 21**, for four concrete shape types. This is a self-contained example model; if a real project has a different set of shapes, you should extend it using the same principles and test according to each shape's own contract.

**Java requirement:** `record patterns` (JEP 440) and `pattern matching for switch` (JEP 441) have been standard since **Java 21**; `--enable-preview` is not needed. `sealed` types have been standard since Java 17.

## 2. Domain Model: Four Bounded Shape Types

First, declare a sealed interface and four record subtypes:

```java
sealed interface Shape permits Circle, Rectangle, Square, Triangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record Square(double side) implements Shape {}
record Point(double x, double y) {}
record Triangle(Point a, Point b, Point c) implements Shape {}
```

In this article, the declarations are placed inside the `GeometryPatternTest` class in the complete program, so each record is not in a separate file.

| Shape | Data | Area | Perimeter |
| --- | --- | --- | --- |
| Circle — `Circle` | Radius `r` | \(\pi r^2\) | \(2\pi r\) |
| Rectangle — `Rectangle` | Width `w`, height `h` | \(wh\) | \(2(w+h)\) |
| Square — `Square` | Side `s` | \(s^2\) | \(4s\) |
| Triangle — `Triangle` | Three points `A,B,C` in the plane | \(\lvert (B-A)\times(C-A)\rvert/2\) | \(\lvert AB\rvert+\lvert BC\rvert+\lvert CA\rvert\) |

**Why are `Square` and `Rectangle` two different records?** This is a modeling decision to thoroughly test every branch of the sealed hierarchy. Records are implicitly `final`, so you cannot write `record Square(...) extends Rectangle`. Two types can share formulas or helpers, but there is no record-to-record inheritance relationship in this example.

**Why use `Point` in `Triangle`?** To test **nested record patterns**, for example:

```java
case Triangle(
        Point(var ax, var ay),
        Point(var bx, var by),
        Point(var cx, var cy)) -> ...
```

Java only enters this branch when the selector is a `Triangle` and all three `Point` components match the nested record pattern. If any vertex is `null`, the record pattern at that position **does not match**; a subsequent `Triangle t` branch is needed to handle the missing-vertex case.

## 3. Defining the Contract Before Writing Tests

Mathematical geometry and computer geometry have several differences. We need to clearly specify **valid inputs**, **precision**, and **error types** instead of letting tests guess.

### 3.1. Data Policy of This Article

- `Circle`: radius must be **finite and greater than 0**; computed area and perimeter must be finite and positive.
- `Rectangle`: width and height must be **finite and greater than 0**; area and perimeter must be finite and positive.
- `Square`: side must be **finite and greater than 0**; area and perimeter must be finite and positive.
- `Triangle`: all three vertices must be **non-`null`**, all coordinates must be finite numbers; both computed area and perimeter must be finite and positive. Collinear triangles or duplicate vertices are considered **degenerate** and invalid.
- A `null` selector in the area/perimeter measurement method is explicitly handled with `IllegalArgumentException("null shape")`.
- Invalid shape data throws `IllegalArgumentException("invalid circle")`, `"invalid rectangle"`, `"invalid square"`, or `"invalid triangle"` respectively.
- The `classify` method only **classifies by runtime type/guard** and does not validate shape dimensions; validation belongs to `measure`.

This policy is an **example convention**, not a mandatory rule for every geometry library. In CAD or graphics, line segments, zero-area shapes, or "incomplete objects" may be valid; in that case, change the contract rather than silently changing expected results.

### 3.2. Invalid Data Is Different from Missing Subtypes

This is an important distinction:

- **Pattern switch exhaustiveness:** Does the compiler see all permitted subtypes of `Shape`?
- **Geometric validation:** Does each instance of a subtype have valid radius, sides, coordinates, and arithmetic results according to the contract?

A `switch` that handles all four types can still return `NaN` for area if it does not validate data. Conversely, the formula for each type might be correct, yet the `switch` expression fails to compile because a subtype is missing.

## 4. Writing the Processor with Record Patterns and Switch Expressions

### 4.1. Floating-Point Validation Helper

```java
static boolean positiveFinite(double x) {
    return Double.isFinite(x) && x > 0.0;
}
```

This check rejects `Double.NaN`, both infinities, negative numbers, `0.0`, and `-0.0`. For this article, a positive dimension whose **computed area underflows to 0** is also rejected in the final result check.

Never use `x <= 0` alone to detect all bad values: for `NaN`, the comparison `NaN <= 0` evaluates to `false`, so bad data can slip through if `Double.isFinite` is not called.

### 4.2. Using an Explicit Result Type

```java
record Metrics(double area, double perimeter) {}
```

Returning a `Metrics` record lets tests read both quantities by name without confusing the first/second element of a `double[]` array. This article does not require every shape object to store `area` and `perimeter`; they are **computed** data.

### 4.3. Guarding Arithmetic Results

```java
static Metrics checked(String kind, double area, double perimeter) {
    if (!positiveFinite(area) || !positiveFinite(perimeter)) {
        throw invalid(kind);
    }
    return new Metrics(area, perimeter);
}
```

This is a crucial step: input dimensions can be finite and positive, yet multiplication can still exceed the range of `double`. For example, `1e308 * 1e308` becomes `Infinity`; validating inputs alone is not enough.

### 4.4. Pattern Switch Dispatching to the Appropriate Formula

```java
static Metrics measure(Shape shape) {
    return switch (shape) {
        case Circle(var radius) -> circle(radius);
        case Rectangle(var w, var h) -> rectangle(w, h);
        case Square(var side) -> square(side);
        case Triangle(Point(var ax, var ay),
                      Point(var bx, var by),
                      Point(var cx, var cy)) ->
                triangle(ax, ay, bx, by, cx, cy);
        case Triangle t -> throw invalid("triangle");
        case null -> throw new IllegalArgumentException("null shape");
    };
}
```

Thanks to `sealed Shape`, the compiler knows all permitted subtypes and checks exhaustiveness of the switch expression **without needing `default`**.

Note the ordering of the two triangle branches:

1. The nested record pattern attempts to extract all three `Point`s. If it matches, it computes area/perimeter and validates them.
2. `case Triangle t` is the remaining branch for a `Triangle` that does not match the nested structure, such as `a == null`.

If `case Triangle t` were placed first, the nested branch after it would be **dominated** and rejected by the compiler. If only the nested case were written without the `Triangle t` fallback, handling a triangle with a `null` vertex would not be guaranteed; the switch might also fail exhaustiveness for all possible `Triangle` values.

## 5. Testing Formulas per Shape

Each shape needs at least one sample with an independent, mathematically easy-to-verify answer:

| Case Name | Input | Expected Area | Expected Perimeter |
| --- | --- | --- | --- |
| Standard Circle | `Circle(1)` | \(\pi\) | \(2\pi\) |
| Standard Rectangle | `Rectangle(2,3)` | \(6\) | \(10\) |
| Standard Square | `Square(2)` | \(4\) | \(8\) |
| 3–4–5 Triangle | `(0,0),(3,0),(0,4)` | \(6\) | \(12\) |
| Reversed Triangle | `(0,4),(3,0),(0,0)` | \(6\) | \(12\) |
| Translated Triangle | `(10,20),(13,20),(10,24)` | \(6\) | \(12\) |

### 5.1. Triangle: Checking Multiple Quantities

From three points `A(ax,ay)`, `B(bx,by)`, `C(cx,cy)`:

\[
2S = \left|(b_x-a_x)(c_y-a_y) - (b_y-a_y)(c_x-a_x)\right|.
\]

With `A(0,0)`, `B(3,0)`, and `C(0,4)`, the determinant has absolute value `12`, so the area is `6`. The sides have lengths `3,4,5`, so the perimeter is `12`.

In Java, use `Math.hypot(dx,dy)` for 2D length instead of manually writing `Math.sqrt(dx*dx + dy*dy)`. `Math.hypot` is designed to avoid unnecessary overflow/underflow when computing the square root of a sum of squares, though it **does not guarantee that every coordinate problem is numerically stable**.

### 5.2. Do Not Compare `double` with `==` When Testing Formulas

Because `Math.PI`, multiplications/divisions, and summing lengths use binary floating-point arithmetic, test formulas with a **tolerance** instead of requiring different computation paths to produce identical bits.

A simple helper used in the program:

```java
static void near(String name, double actual, double expected) {
    if (!Double.isFinite(actual) || !Double.isFinite(expected)
            || Math.abs(actual - expected)
                > 1e-10 * Math.max(1.0, Math.abs(expected))) {
        throw new AssertionError(name + ": got " + actual
                + ", expected " + expected);
    }
    assertions++;
}
```

Here, the tolerance is relative to the expected magnitude with an absolute floor of `1e-10`. It is suitable for the small numbers in this article's examples, **not a safe default rule for all scientific simulations**, especially when results are near 0, require ULP control, or have specialized error bounds.

In addition to approximate comparison, the test checks `Double.isFinite` to prevent `NaN` from slipping past the error comparison in an unexpected way.

## 6. Testing All Subtypes and Guarded Branches

A sealed hierarchy enables compile-time exhaustiveness checking, but **tests must still verify the behavior of every subtype**:

```java
static String classify(Shape shape) {
    return switch (shape) {
        case Circle(var radius) when radius > 10.0 -> "large-circle";
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case Square s -> "square";
        case Triangle t -> "triangle";
        case null -> "missing";
    };
}
```

The test suite verifies six labels/results:

| Input | Output |
| --- | --- |
| `Circle(11)` | `"large-circle"` |
| `Circle(1)` | `"circle"` |
| `Rectangle(1,2)` | `"rectangle"` |
| `Square(2)` | `"square"` |
| `Triangle(...)` | `"triangle"` |
| `null` | `"missing"` |

**The guarded branch is placed before the general Circle branch:** If `case Circle c` were written before `case Circle(var radius) when radius > 10`, the guarded branch would be dominated. That is a compiler error, distinct from an incorrect area test.

**`classify` does not perform validation:** `Circle(-1)` is still classified as `"circle"` even though `measure` will reject it. Classifying types and verifying valid dimensions are two separate responsibilities. Do not use `classify` tests to conclude that `measure` is correct.

### 6.1. Why Have Both Compile Tests and Runtime Tests?

- Compile-time: ensures the switch expression is accepted by the compiler, no required subtype is missing, and no pattern is dominated.
- Runtime: ensures each branch returns the expected result, throws exceptions, and computes according to the contract, including boundary data.

The compiler accepting an exhaustive switch **does not verify** that `Rectangle(2,3)` has a perimeter of 10. Testing that perimeter is correct on a Rectangle **does not verify** that Triangle is also handled.

## 7. Invalid Cases to Test

### 7.1. Circle

- `Circle(0)`: zero radius is rejected.
- `Circle(Double.NaN)`: non-finite data is rejected.
- `Circle(Double.POSITIVE_INFINITY)`: infinity is rejected.
- You can also add `Circle(-1)`, `Circle(-0.0)`, and an extremely large positive radius that causes overflow.
- An extremely small radius can cause the area to underflow to 0 in `double`; per this article's policy, any non-finite or non-positive result is invalid.

### 7.2. Rectangle and Square

- `Rectangle(-1,2)`: one negative dimension.
- `Rectangle(1e308,1e308)`: inputs are positive finite numbers, but area/perimeter overflow.
- `Square(-0.0)`: the negative sign on zero does not make it a valid dimension; `> 0` returns false.
- `Square(Double.POSITIVE_INFINITY)`: infinity is rejected.
- Extended tests can include one zero dimension, very small magnitudes, and `NaN` in each dimension.

### 7.3. Triangle

- **Three collinear points:** area is 0, e.g., `(0,0),(1,1),(2,2)`.
- **Two duplicate vertices:** area is 0, e.g., `(0,0),(0,0),(1,0)`.
- **One null vertex:** nested `Point(...)` does not match; `case Triangle t` reports invalid.
- **NaN/infinite coordinates:** rejected before applying the formula.
- **Extreme magnitudes:** for example, two sides using `1e308` coordinates can cause the determinant or total side length to exceed `double` range.
- **Nearly collinear triangles:** add numerical error tests per your contract if the application actually handles these.

A triangle with three non-null vertices and finite coordinates is **not necessarily valid**. For example, three collinear points still form a `Triangle` record that can be constructed normally; a record is a data carrier, not an automatic enforcer of geometric axioms.

### 7.4. Null Selector

Testing `measure(null)` must verify **`IllegalArgumentException("null shape")`**, because the example intentionally includes `case null -> throw ...`. If the `case null` branch is removed, behavior changes; do not assume `default` handles null automatically.

Another API might choose `NullPointerException` or Optional/Result; what matters is that **the contract is clear** and tests reflect that decision accurately.

## 8. Negative Compiler Tests: Verifying Examples That Must Be Rejected

The runnable test suite only contains valid code. To teach Java rules, keep **intentionally wrong** snippets separate and verify that the compiler rejects them.

### 8.1. Omitting a Subtype of Sealed Shape

```java
// INTENTIONALLY WRONG: Shape also has Triangle, but the switch expression does not handle it.
static String missing(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case Square s -> "square";
    };
}
```

Java 21 reports an error equivalent to: `the switch expression does not cover all possible input values`. This is proof of the **exhaustiveness check**. When adding `Ellipse` or a new shape type to the permitted subtypes list, recompiling helps detect existing `switch` expressions that do not yet handle that subtype, provided no general branch is already covering the new case.

### 8.2. General Branch Dominating a Specific Branch

```java
// INTENTIONALLY WRONG:
return switch (shape) {
    case Shape any -> "any";
    case Circle c -> "circle"; // dominated
    case null -> "null";
};
```

Every `Circle` is a `Shape`. Placing an unguarded `case Shape any` first makes the subsequent Circle branch unreachable. The Java 21 compiler reports `this case label is dominated by a preceding case label`.

**Fix:** place the specific branch before the supertype branch, or remove the unnecessary branch. Do not try to fix dominance using `->`/`break`: this is a pattern coverage rule.

### 8.3. Record Pattern with Wrong Component Count

```java
// INTENTIONALLY WRONG: Circle has one component, radius.
case Circle(var radius, var extra) -> "circle";
```

The compiler reports `incorrect number of nested patterns`. The number of component patterns must match the record header. If a record adds or removes components, related record patterns may need to be updated at compile time.

### 8.4. Patterns Are Not Automatic Validators

The snippet below **compiles** but can return `NaN`:

```java
static double unsafeArea(Shape s) {
    return switch (s) {
        case Circle(var r) -> Math.PI * r * r;
        case Rectangle(var w, var h) -> w * h;
        case Square(var a) -> a * a;
        case Triangle t -> 0.0; // Wrong if this is supposed to be the actual area of a triangle!
        case null -> 0.0;
    };
}
```

This is an example of **wrong logic with valid syntax**, not a negative compilation test. The compiler checks structure and types, not geometric formulas. Behavioral tests must catch the `Triangle t -> 0.0` bug and `NaN`/Infinity values.

## 9. Complete Java 21 Program

Create the file **`GeometryPatternTest.java`**. This is a self-contained test program using only the JDK. It has no JUnit dependency: checks throw `AssertionError` directly, so it runs even when the JVM **does not have `-ea` enabled**.

The program includes: a four-shape sealed hierarchy; area/perimeter computation with finite-number checks; guarded classification; 6 valid shape cases; 6 classification cases; 13 invalid cases; 8 property checks (**39 assertions** total).

```java
import java.util.Locale;
import java.util.Objects;

public class GeometryPatternTest {
    sealed interface Shape permits Circle, Rectangle, Square, Triangle {}

    record Circle(double radius) implements Shape {}
    record Rectangle(double width, double height) implements Shape {}
    record Square(double side) implements Shape {}
    record Point(double x, double y) {}
    record Triangle(Point a, Point b, Point c) implements Shape {}
    record Metrics(double area, double perimeter) {}

    static int assertions;

    static boolean positiveFinite(double x) {
        return Double.isFinite(x) && x > 0.0;
    }

    static IllegalArgumentException invalid(String kind) {
        return new IllegalArgumentException("invalid " + kind);
    }

    static Metrics checked(String kind, double area, double perimeter) {
        if (!positiveFinite(area) || !positiveFinite(perimeter)) {
            throw invalid(kind);
        }
        return new Metrics(area, perimeter);
    }

    static Metrics circle(double radius) {
        if (!positiveFinite(radius)) throw invalid("circle");
        return checked("circle", Math.PI * radius * radius,
                2 * Math.PI * radius);
    }

    static Metrics rectangle(double width, double height) {
        if (!positiveFinite(width) || !positiveFinite(height)) {
            throw invalid("rectangle");
        }
        return checked("rectangle", width * height, 2 * (width + height));
    }

    static Metrics square(double side) {
        if (!positiveFinite(side)) throw invalid("square");
        return checked("square", side * side, 4 * side);
    }

    static Metrics triangle(double ax, double ay, double bx, double by,
                            double cx, double cy) {
        if (!Double.isFinite(ax) || !Double.isFinite(ay)
                || !Double.isFinite(bx) || !Double.isFinite(by)
                || !Double.isFinite(cx) || !Double.isFinite(cy)) {
            throw invalid("triangle");
        }
        double twiceArea = Math.abs((bx - ax) * (cy - ay)
                - (by - ay) * (cx - ax));
        double perimeter = Math.hypot(ax - bx, ay - by)
                + Math.hypot(bx - cx, by - cy)
                + Math.hypot(cx - ax, cy - ay);
        return checked("triangle", twiceArea / 2.0, perimeter);
    }

    static Metrics measure(Shape shape) {
        return switch (shape) {
            case Circle(var radius) -> circle(radius);
            case Rectangle(var w, var h) -> rectangle(w, h);
            case Square(var side) -> square(side);
            case Triangle(Point(var ax, var ay),
                          Point(var bx, var by),
                          Point(var cx, var cy)) ->
                    triangle(ax, ay, bx, by, cx, cy);
            case Triangle t -> throw invalid("triangle");
            case null -> throw new IllegalArgumentException("null shape");
        };
    }

    static String classify(Shape shape) {
        return switch (shape) {
            case Circle(var radius) when radius > 10.0 -> "large-circle";
            case Circle c -> "circle";
            case Rectangle r -> "rectangle";
            case Square s -> "square";
            case Triangle t -> "triangle";
            case null -> "missing";
        };
    }

    static void near(String name, double actual, double expected) {
        if (!Double.isFinite(actual) || !Double.isFinite(expected)
                || Math.abs(actual - expected) >
                    1e-10 * Math.max(1.0, Math.abs(expected))) {
            throw new AssertionError(name + ": got " + actual
                    + ", expected " + expected);
        }
        assertions++;
    }

    static void equal(String name, Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(name + ": got " + actual
                    + ", expected " + expected);
        }
        assertions++;
    }

    static Metrics testValid(
            String name, Shape shape, double area, double perimeter) {
        Metrics result = measure(shape);
        near(name + ".area", result.area(), area);
        near(name + ".perimeter", result.perimeter(), perimeter);
        System.out.printf(Locale.ROOT,
                "%s -> area=%.2f, perimeter=%.2f%n",
                name, result.area(), result.perimeter());
        return result;
    }

    static void testInvalid(String name, Shape shape, String message) {
        try {
            measure(shape);
            throw new AssertionError(
                    name + ": expected IllegalArgumentException");
        } catch (IllegalArgumentException ex) {
            equal(name + ".message", ex.getMessage(), message);
            System.out.println(name + " -> " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        Metrics circle = testValid(
                "circle", new Circle(1), Math.PI, 2 * Math.PI);
        Metrics rectangle = testValid(
                "rectangle", new Rectangle(2, 3), 6, 10);
        Metrics square = testValid(
                "square", new Square(2), 4, 8);
        Triangle abc = new Triangle(
                new Point(0, 0), new Point(3, 0), new Point(0, 4));
        Metrics triangle = testValid("triangle", abc, 6, 12);
        Triangle cba = new Triangle(
                new Point(0, 4), new Point(3, 0), new Point(0, 0));
        Metrics reversed = testValid("reversed", cba, 6, 12);
        Triangle translated = new Triangle(
                new Point(10, 20), new Point(13, 20), new Point(10, 24));
        Metrics shifted = testValid("translated", translated, 6, 12);

        equal("classify-guard", classify(new Circle(11)), "large-circle");
        equal("classify-fallback", classify(new Circle(1)), "circle");
        equal("classify-rectangle",
                classify(new Rectangle(1, 2)), "rectangle");
        equal("classify-square", classify(new Square(2)), "square");
        equal("classify-triangle", classify(abc), "triangle");
        equal("classify-null", classify(null), "missing");
        System.out.println("CLASSIFY PASS: 6");

        testInvalid("circle-zero", new Circle(0), "invalid circle");
        testInvalid("circle-nan",
                new Circle(Double.NaN), "invalid circle");
        testInvalid("circle-infinite",
                new Circle(Double.POSITIVE_INFINITY), "invalid circle");
        testInvalid("rectangle-negative",
                new Rectangle(-1, 2), "invalid rectangle");
        testInvalid("rectangle-overflow",
                new Rectangle(1e308, 1e308), "invalid rectangle");
        testInvalid("square-zero", new Square(-0.0), "invalid square");
        testInvalid("square-infinite",
                new Square(Double.POSITIVE_INFINITY), "invalid square");
        testInvalid("triangle-collinear",
                new Triangle(new Point(0, 0),
                        new Point(1, 1), new Point(2, 2)),
                "invalid triangle");
        testInvalid("triangle-duplicate",
                new Triangle(new Point(0, 0),
                        new Point(0, 0), new Point(1, 0)),
                "invalid triangle");
        testInvalid("triangle-null-vertex",
                new Triangle(null, new Point(1, 0), new Point(0, 1)),
                "invalid triangle");
        testInvalid("triangle-nan",
                new Triangle(new Point(Double.NaN, 0),
                        new Point(1, 0), new Point(0, 1)),
                "invalid triangle");
        testInvalid("triangle-overflow",
                new Triangle(new Point(0, 0),
                        new Point(1e308, 0), new Point(0, 1e308)),
                "invalid triangle");
        testInvalid("null-selector", null, "null shape");
        System.out.println("INVALID CASES PASS: 13");

        near("triangle-winding.area",
                reversed.area(), triangle.area());
        near("triangle-winding.perimeter",
                reversed.perimeter(), triangle.perimeter());
        near("triangle-translation.area",
                shifted.area(), triangle.area());
        near("triangle-translation.perimeter",
                shifted.perimeter(), triangle.perimeter());
        near("square-vs-rectangle.area",
                square.area(), measure(new Rectangle(2, 2)).area());
        near("square-vs-rectangle.perimeter",
                square.perimeter(),
                measure(new Rectangle(2, 2)).perimeter());
        Metrics scaledCircle = measure(new Circle(2));
        near("circle-scale.area",
                scaledCircle.area(), 4 * circle.area());
        near("circle-scale.perimeter",
                scaledCircle.perimeter(), 2 * circle.perimeter());
        System.out.println("PROPERTIES PASS: 8");
        System.out.println("ALL ASSERTIONS PASS: " + assertions);
    }
}
```

### 9.1. Compiling and Running

In the directory containing the file, using JDK 21+:

```bash
javac --release 21 GeometryPatternTest.java
java GeometryPatternTest
```

**Verified stdout output:**

```text
circle -> area=3.14, perimeter=6.28
rectangle -> area=6.00, perimeter=10.00
square -> area=4.00, perimeter=8.00
triangle -> area=6.00, perimeter=12.00
reversed -> area=6.00, perimeter=12.00
translated -> area=6.00, perimeter=12.00
CLASSIFY PASS: 6
circle-zero -> invalid circle
circle-nan -> invalid circle
circle-infinite -> invalid circle
rectangle-negative -> invalid rectangle
rectangle-overflow -> invalid rectangle
square-zero -> invalid square
square-infinite -> invalid square
triangle-collinear -> invalid triangle
triangle-duplicate -> invalid triangle
triangle-null-vertex -> invalid triangle
triangle-nan -> invalid triangle
triangle-overflow -> invalid triangle
null-selector -> null shape
INVALID CASES PASS: 13
PROPERTIES PASS: 8
ALL ASSERTIONS PASS: 39
```

**No benchmark lines.** This program verifies correctness, not performance.

### 9.2. How to Read the Output

- The first six lines confirm **the area and perimeter of all four shapes**, plus two triangle variants.
- `CLASSIFY PASS: 6` confirms the type patterns, guard, and `null` branches in the classification method.
- All 13 invalid cases throw **`IllegalArgumentException` with the exact message**. The tests do not merely check for "any exception".
- `PROPERTIES PASS: 8` confirms that translating and reversing triangle vertices preserve area/perimeter, a square matches a rectangle with equal sides, and circle scaling holds.
- A total of **39 assertions** are actually counted: \(6\times2+6+13+8=39\).
- Any check failure throws `AssertionError`. The final line is only printed when all checks run to completion.

## 10. Property-Based and Metamorphic Testing for Geometry

A concrete set of examples is very useful, but geometry also has **invariant relationships** that can generate much stronger tests. This helps catch formula bugs even when we do not have precomputed area values for every shape.

### 10.1. Reversing Triangle Vertex Order

For a non-degenerate triangle, permuting the order of the three vertices does not change the geometric triangle, so **the area does not change**. The perimeter also does not change because the set of three sides is the same.

If `Math.abs` were omitted from the determinant, reversing `A,B,C` to `C,B,A` could flip the sign of the area; the `reversed` test catches this bug.

**Do not confuse orientation with area:** In this article, area is always non-negative; if an application needs *signed area* to determine clockwise/counterclockwise orientation, that is a different API and should not share the same expectation.

### 10.2. Translation

Shifting all three vertices by the same vector \((u,v)\) does not change side lengths or area/perimeter:

\[
S(A+v,B+v,C+v)=S(A,B,C).
\]

With the small integer coordinates in this article, adding 10/20 introduces no significant error risk. However, with very large or very small numbers, `double` arithmetic can still lose precision; practical property tests should generate inputs within a controlled finite range.

### 10.3. Scaling a Circle

If the radius is multiplied by a factor \(k>0\), the area is multiplied by \(k^2\) and the perimeter by \(k\). The article tests `Circle(1)` to `Circle(2)`:

- `area(2r) ≈ 4 × area(r)`.
- `perimeter(2r) ≈ 2 × perimeter(r)`.

This is a very useful relationship for catching formula bugs that confuse radius, diameter, and squaring.

### 10.4. Relationship Between Square and Rectangle

`Square(2)` has the same area and perimeter as `Rectangle(2,2)`. This test checks consistency between **two different pattern branches** in the sealed hierarchy, even though they are two independent record types.

### 10.5. Adding Constrained Generators

If using a property-based testing library, you can generate data for:

- Positive finite radius/sides not too large so as to avoid overflow.
- Triangles with three non-collinear points.
- Points permuted or translated by small vectors.
- **Intentionally invalid** datasets: negative radius, infinite coordinates, null vertex, collinear points.

Keep the random seed to reproduce failures and save a minimal failing case for regression testing. Do not generate completely random inputs and only check "no exception thrown": a wrong formula can still return a valid number.

## 11. JUnit 5 Integration for Real Projects

The program in Section 9 runs on the plain JDK. When a project already uses JUnit Jupiter, convert the tests into test methods or parameterized tests so CI reports clearly which test failed. The following snippet is **illustrative**, requires test dependencies, and is placed in the same package as the production class `GeometryPatternTest`:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class GeometryPatternJUnitTest {
    @Test
    void circleHasCorrectAreaAndPerimeter() {
        var value = GeometryPatternTest.measure(
                new GeometryPatternTest.Circle(1));
        assertEquals(Math.PI, value.area(), 1e-10);
        assertEquals(2 * Math.PI, value.perimeter(), 1e-10);
    }

    @Test
    void nullVertexIsRejected() {
        var invalid = new GeometryPatternTest.Triangle(
                null,
                new GeometryPatternTest.Point(1, 0),
                new GeometryPatternTest.Point(0, 1));
        var ex = assertThrows(IllegalArgumentException.class,
                () -> GeometryPatternTest.measure(invalid));
        assertEquals("invalid triangle", ex.getMessage());
    }

    @Test
    void allPermittedShapesProduceMetrics() {
        GeometryPatternTest.Shape[] shapes = {
            new GeometryPatternTest.Circle(1),
            new GeometryPatternTest.Rectangle(2, 3),
            new GeometryPatternTest.Square(2),
            new GeometryPatternTest.Triangle(
                new GeometryPatternTest.Point(0, 0),
                new GeometryPatternTest.Point(3, 0),
                new GeometryPatternTest.Point(0, 4))
        };
        for (var shape : shapes) {
            var metrics = GeometryPatternTest.measure(shape);
            assertTrue(Double.isFinite(metrics.area()));
            assertTrue(metrics.area() > 0);
            assertTrue(Double.isFinite(metrics.perimeter()));
            assertTrue(metrics.perimeter() > 0);
        }
    }
}
```

**Snippet limitations:** This assumes `GeometryPatternTest` and the test are in the same package, JUnit Jupiter is configured, and the records/methods remain at an accessible visibility level. If the production class is moved to another package, expose the APIs under test or reorganize packages/test fixtures. Do not add JUnit imports to the plain-JDK file in Section 9 without declaring the dependency.

### 11.1. Parameterized Tests

The four shape types and multiple invalid cases fit well with data tables via `@MethodSource`/`@CsvSource`. Cases involving nested records, null, and exceptions should use `@MethodSource` with named test cases rather than CSV strings that are awkward for representing complex objects.

**Case organization example:** create a `ValidCase(String name, Shape input, double area, double perimeter)` or `InvalidCase(String name, Shape input, String message)` record in the test. Use a single helper to check results or exceptions instead of duplicating inconsistent assertions.

### 11.2. Test Coverage Does Not Equal Formula Correctness

A test can execute all four branches and achieve 100% branch coverage yet miss bugs if it only asserts `result != null`. For each shape, there must be an **independent oracle** for the formula, error thresholds, and rejection cases.

Conversely, testing only the formulas of `Circle` and `Triangle` does not guarantee the other two subtypes are handled; **behavioral coverage** must be combined with **exhaustiveness/compiler gates**.

## 12. Numerical Precision and Limitations of the Example

### 12.1. Floating-Point Is Not Exact Geometry

`double` values use the IEEE 754 standard with a finite set of representable numbers. When computing a triangle's determinant, multiplications and subtractions can suffer rounding; subtracting two nearly equal numbers can cause loss of significant digits. For extremely thin triangles or coordinates around `1e308`, results can overflow or become 0 due to underflow/cancellation.

The processor in this article actively **rejects non-finite or non-positive results**, yet it can still experience large relative errors on some nearly degenerate triangles. Therefore:

- Do not use this code as an exact geometry engine for CAD/GIS without further evaluation.
- For domains requiring robust orientation, consider *adaptive precision* algorithms or dedicated exact geometric predicates.
- Test coordinate range limits and acceptable error; do not set a single fixed epsilon for all scales.
- For monetary values or decimal precision requirements, `BigDecimal` may suit certain calculations, though general geometry (square roots, angles, determinants) still requires dedicated methods and error definitions.

### 12.2. Overflow Does Not Only Occur with Infinity Inputs

`Rectangle(1e308,1e308)` has two **finite** dimensions, yet the multiplied area is not finite. Separate tests for output overflow help distinguish input validation bugs from arithmetic bugs.

`Math.hypot` can avoid intermediate overflow better than `Math.sqrt(dx*dx + dy*dy)`, but if the **true mathematical distance exceeds `double` range**, the result can still be Infinity; therefore, `checked(...)` must still verify the output.

### 12.3. Negative Zero

`-0.0` differs from `0.0` in its sign bit but compares equal under `==`; both are **not greater than 0**. The article tests `Square(-0.0)` as an invalid case. If a system allows degenerate shapes, the contract must clearly specify how zero/negative zero is represented.

### 12.4. Exceptions and Side Effects from Record Accessors

Records have simple default accessors, but Java allows records to declare explicit accessors. Record deconstruction can invoke accessors; if an accessor causes side effects or throws an exception, runtime pattern matching can behave differently from a type-only check. For production geometry with custom records, test invocation counts and exceptions (which may involve `MatchException` during deconstruction) rather than comparing area alone.

In this article, `record Point/Circle/...` use default accessors with no side effects. The observations here only demonstrate logic on this model.

## 13. Common Mistakes When Testing All Shapes

### Mistake 1 — Testing Only One Shape Type

A `Circle(1)` returning \(\pi\) accurately does not prove `Rectangle`, `Square`, or `Triangle` are correct. A matrix covering all subtypes and various invalid cases is required.

### Mistake 2 — Assuming `sealed` Automatically Validates Dimensions

`sealed` only restricts subtypes. It does not forbid `Circle(-1)` or `Triangle(null,...)`. Validation and domain policy must still be designed explicitly.

### Mistake 3 — Forgetting the Null Nested Record Branch

`case Triangle(Point(...),Point(...),Point(...))` does not match when a `Point` vertex is null. Without a `case Triangle t` branch after it, the switch may fail to handle all Triangle values per the contract.

### Mistake 4 — Placing a Broad Pattern Before a Narrow Pattern

`case Shape any` before `case Circle c` makes Circle dominated. Similarly, `case Triangle t` before `case Triangle(Point(...))` shadows the nested pattern. The Java 21 compiler rejects these cases.

### Mistake 5 — Comparing Areas with `==`

`double` has rounding; exact comparison with `==` can cause flaky tests or obscure hard-to-diagnose errors. Use an appropriate tolerance and check for `NaN`/Infinity.

### Mistake 6 — Testing Only Positive Numbers and Ignoring Overflow

Positive radii or sides that are too large can produce Infinity. Test outputs after computation, not just the initial inputs.

### Mistake 7 — Catching Any Exception and Treating the Test as Passing

If a test expects `IllegalArgumentException` but the code throws `NullPointerException`, that may be a bug that needs catching. Use `assertThrows(IllegalArgumentException.class, ...)` or catch the exact type and compare the message if the message is part of the contract.

### Mistake 8 — Only Printing to stdout Without Asserting

A program that prints wrong results still exits with code 0 if nothing is checked. Use assertions that actually run; the demo throws `AssertionError` when expected differs from actual.

### Mistake 9 — Treating All Shapes with Zero Perimeter as Valid

This article's contract does not allow degenerate shapes. If an application needs line segments, points, or collinear triangles, build separate types/contracts instead of silently altering test expectations.

### Mistake 10 — Using Test Coverage as Proof of Geometric Correctness

Coverage does not verify formulas. You need tests with independent oracles and geometric transformation properties.

## 14. Workflow for Extending the Test Suite When Adding a New Shape

Suppose a requirement adds an `Ellipse` or `Parallelogram`. Do not simply add one `case` branch and consider it done.

**Workflow:**

1. Define the new subtype and sufficient geometric parameters to compute metrics.
2. Update `permits` on `sealed Shape`.
3. Compile: inspect which `switch` expressions are missing the subtype. This is a key benefit of sealed types + exhaustive switches.
4. Define the valid input contract (sides, axes, angles, coordinates, precision).
5. Add documented formulas and unit tests with independent expected values.
6. Add invalid cases: zero, negative, NaN, Infinity, overflow, and shape-specific degenerate cases.
7. Add property/metamorphic tests where invariant properties exist.
8. Check `null`, dominance, and guard ordering after updating the switch.
9. Re-run the full-shape test suite and CI on JDK 21.
10. If performance optimization is needed, benchmark separately; **do not replace correctness tests with benchmarks**.

**Warning:** Changing the list of permitted subtypes is an API model change. For libraries distributed across multiple binary versions, check compatibility when modules are recompiled at different times; compile-time exhaustiveness does not automatically solve all runtime/binary evolution issues.

## 15. Full-Shape Testing Checklist

- [ ] The permitted subtypes of `Shape` are explicitly listed; every subtype has tests.
- [ ] Each shape has at least one area and perimeter example with an independent oracle.
- [ ] Nested record patterns handle both three non-null vertices and `null` vertices.
- [ ] `switch` expressions are exhaustive and have no dominated branches.
- [ ] Guarded branches appear before general branches of the same type.
- [ ] Null selector has explicit behavior/exception; do not assume `default` catches null.
- [ ] Negative, 0, `-0.0`, NaN, and Infinity radii/sides/lengths are tested.
- [ ] Arithmetic output overflow is tested, not just finite input checks.
- [ ] Collinear, duplicate-vertex, and nearly degenerate triangles are tested if needed.
- [ ] Vertex permutation, translation, or other appropriate geometric properties are tested.
- [ ] `double` comparisons use an appropriate tolerance and verify finiteness.
- [ ] Exception tests verify the exact exception type and message if part of the contract.
- [ ] Code uses `javac --release 21` with no preview dependencies.
- [ ] Unit/regression tests run automatically rather than relying on manual stdout inspection.
- [ ] When adding a new subtype, recompile all switch handlers and expand the test matrix.
- [ ] Limitations of the `double` model are clearly documented for API users.

**Completion criteria:** The test suite must cover **all permitted shape types**, formulas, valid/invalid data, `null`/guard behavior, and key numerical properties. The program must compile and run on the target JDK; new geometric changes must have tests proving correctness.

## 16. Self-Check Questions

**1. How does `sealed Shape` help test all shapes?**  
The compiler knows the permitted subtypes and checks exhaustiveness of `switch` expressions; when a new subtype is added, switches missing that branch can be flagged at compile time.

**2. Does the compiler know that `Circle(-1)` is invalid data?**  
No. That is a domain condition and must be validated and tested.

**3. Why is `case Triangle t` placed after the nested Triangle case?**  
Because it handles Triangles that do not match the nested structure, such as a null vertex. If placed before it, the nested case would be dominated.

**4. `Rectangle(1e308, 1e308)` has two finite inputs. Why is it still rejected?**  
Because area/perimeter computed in `double` can overflow to Infinity; this article checks the results as well.

**5. Why use `Math.hypot` for triangle side lengths?**  
It helps avoid unnecessary overflow/underflow when computing the square root of a sum of squares, though it does not eliminate all numerical issues.

**6. Why should a triangle with reversed vertex order have the same area?**  
Geometric area is the absolute value of the determinant and does not depend on the orientation order of vertices.

**7. Is `Double.NaN > 0` true?**  
No. To ensure valid inputs, check `Double.isFinite` along with sign and dimension conditions.

**8. If `classify(Circle(-1))` returns `"circle"`, is that a bug?**  
Not under the example contract: `classify` only identifies the type, while `measure` validates dimensions. If the API needs to classify invalid states, update the contract and add tests.

**9. Why is `assertEquals(6.0, area)` not always a good numerical test?**  
Because floating-point operations have rounding errors; use an appropriate delta/ULP and test `isFinite` when needed.

**10. Does a test suite outputting `ALL ASSERTIONS PASS: 39` prove every triangle on Earth is handled correctly?**  
No. That conclusion applies within the tested domain and the 39 assertions; computational geometry still has precision, scale, and unexamined structural edge cases.

**11. If `Ellipse` is added to `Shape` but a switch expression is not updated, what happens?**  
When recompiling related code against the updated sealed hierarchy, the compiler can report that the switch is not exhaustive; a new branch and formula tests must be added.

**12. Why are both negative compiler tests and runtime unit tests needed?**  
The compiler catches language-level violations such as dominated cases, missing subtypes, and wrong record arity; runtime tests catch incorrect formulas, exceptions, and values.

## References

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JLS SE 21 §14.11 — Switch Blocks, exhaustiveness/dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS SE 21 §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java SE 21 API — Double.isFinite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html#isFinite(double))
- [Java SE 21 API — Math.hypot](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#hypot(double,double))
- [JUnit 5 User Guide — Assertions and Test Interfaces](https://junit.org/junit5/docs/current/user-guide/)
