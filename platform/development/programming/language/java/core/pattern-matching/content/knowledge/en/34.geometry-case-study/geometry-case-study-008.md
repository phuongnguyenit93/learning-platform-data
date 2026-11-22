# Comparing Legacy `instanceof` + Cast with Pattern Matching: Geometry Case Study (Java 21+)

## 1. Goal and Real-World Problem

A geometry application needs to handle multiple types of shapes: **circle**, **rectangle**, and **triangle**. Each shape carries different data:

- **Circle:** center `Point` and `radius`.
- **Rectangle:** `origin` point along with `width` and `height`.
- **Triangle:** three vertices `a`, `b`, `c`.

Common operations include computing **area**, **perimeter**, or retrieving anchor coordinates for display. In older Java, developers typically used `instanceof` followed by an **explicit cast** to access the data:

~~~java
if (shape instanceof Circle) {
    Circle circle = (Circle) shape;
    return Math.PI * circle.radius() * circle.radius();
}
~~~

This approach is correct if the type is checked before casting, but it repeats the type name and increases line count when shapes are handled repeatedly. Modern Java adds:

1. **Type patterns with `instanceof`**: check the type and declare a variable at the same time.
2. **Record patterns**: check a record and deconstruct the needed components.
3. **Pattern matching in `switch`**: express subtype branches in one centralized place; when combined with a `sealed` subtype hierarchy, the compiler can check **exhaustiveness**.

**What does not change:** all approaches must still compute the **same formulas**, obey the **same `null` contract**, and preserve the **same geometric invariants**. Pattern matching clarifies control flow, but it does not replace validation or guarantee superior performance on its own.

This article uses **Java 21+** to run stable record patterns and pattern `switch`. Type patterns for `instanceof` have been stable since Java 16; `record` since Java 16 and `sealed` since Java 17. If your project is still on Java 17, you can use type patterns and `sealed`, but you cannot copy the Java 21 record pattern syntax directly.

## 2. Modeling Shapes with `sealed` and `record`

General type design:

~~~java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Point(double x, double y) {}
record Circle(Point center, double radius) implements Shape {}
record Rectangle(Point origin, double width, double height)
        implements Shape {}
record Triangle(Point a, Point b, Point c) implements Shape {}
~~~

These are **illustrative declarations** without constructor validation yet. The complete example in section 8 adds data validation.

`Shape` permits exactly three direct subtypes. Because the three subtypes are `record`s, they are `final` by default; in this illustrative model, no other subtypes can be declared arbitrarily. This is important for a `switch expression` without a `default` branch.

### Formulas for Each Shape

| Shape | Area | Perimeter |
| --- | --- | --- |
| Circle with radius `r` | `π × r²` | `2 × π × r` |
| Rectangle with width `w`, height `h` | `w × h` | `2 × (w + h)` |
| Triangle with vertices A, B, C | `abs(cross(B-A, C-A)) / 2` | `AB + BC + CA` |

For a triangle with coordinates `A(ax,ay)`, `B(bx,by)`, `C(cx,cy)`, the 2D signed cross product is:

~~~text
cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
area  = abs(cross) / 2
~~~

To compute the side length between two points, use `Math.hypot(dx, dy)` instead of directly writing `Math.sqrt(dx*dx + dy*dy)`. `hypot` generally handles numerical scaling better across different magnitudes, though you still need to validate that the geometric data is valid.

### Why Choose `record`?

Records fit **value-like data**: Java generates accessors such as `radius()`, `center()`, `width()`, and implements `equals`, `hashCode`, and `toString` based on the components. Using a record does not automatically forbid `null` reference components, nor does it guarantee a positive radius or non-collinear points. **Constructor validation is still required.**

## 3. Legacy Approach: `instanceof` Followed by Explicit Cast

Here is the traditional version for computing area:

~~~java
static double areaLegacy(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    if (shape instanceof Circle) {
        Circle c = (Circle) shape;
        return Math.PI * c.radius() * c.radius();
    }
    if (shape instanceof Rectangle) {
        Rectangle r = (Rectangle) shape;
        return r.width() * r.height();
    }
    if (shape instanceof Triangle) {
        Triangle t = (Triangle) shape;
        return Math.abs(cross(
                t.a().x(), t.a().y(),
                t.b().x(), t.b().y(),
                t.c().x(), t.c().y())) / 2.0;
    }
    throw new IllegalStateException("Unknown shape");
}
~~~

This is an **illustrative method**; it requires `Shape` and the `cross` function in the same scope. The standalone file in section 8 has the complete code.

How it works:

1. `shape instanceof Circle` checks at runtime whether the object is a `Circle`.
2. After the check succeeds, the cast `(Circle) shape` is safe for the checked value.
3. The corresponding branch uses record accessors to compute the area.
4. If it is not a `Circle`, execution continues to check `Rectangle` and then `Triangle`.

**Advantages:** the syntax is familiar to developers used to older Java, works with ordinary inheritance hierarchies, and does not require pattern `switch`. When there is only a single simple branch, writing legacy `instanceof` is completely acceptable.

**Limitations:**

- Repeated type name: `instanceof Circle` followed by `(Circle) shape`.
- Easy to cast the wrong object or wrong type during manual edits.
- Introduces an intermediate variable solely for type conversion.
- An `if` chain does not automatically get compiler exhaustiveness checking like a pattern `switch` over `sealed Shape`. If a new subtype is added later and you forget to update the chain, the final branch may throw `IllegalStateException` **at runtime** instead of reporting a missing case **at compile time**.

Example of a cast error:

~~~java
Object value = new Circle(new Point(0, 0), 2);

// INTENTIONALLY WRONG: Circle is not a Rectangle.
// At runtime, this line throws ClassCastException.
Rectangle wrong = (Rectangle) value;
~~~

Do not confuse this cast error with using `instanceof` followed by a checked cast: the cast syntax itself is not dangerous when placed after a proper type check, but it adds an extra step that the author must maintain accurately.

## 4. First Improvement: Type Pattern with `instanceof`

A type pattern keeps the same type-check idea but removes the manual cast:

~~~java
static double areaTypePattern(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    if (shape instanceof Circle c) {
        return Math.PI * c.radius() * c.radius();
    }
    if (shape instanceof Rectangle r) {
        return r.width() * r.height();
    }
    if (shape instanceof Triangle t) {
        return Math.abs(cross(
                t.a().x(), t.a().y(),
                t.b().x(), t.b().y(),
                t.c().x(), t.c().y())) / 2.0;
    }
    throw new IllegalStateException("Unknown shape");
}
~~~

The pattern `shape instanceof Circle c` does two things **at once**:

- Checks whether the object matches `Circle`.
- When it matches, binds a pattern variable `c` with static type `Circle`.

There is no need to repeat `Circle c = (Circle) shape`; the compiler manages variable scope based on control flow (*flow scoping*).

### Flow Scoping in Practice

~~~java
Object input = new Circle(new Point(1, 2), 2);

if (input instanceof Circle c && c.radius() > 1) {
    System.out.println("large circle: " + c.radius());
}
~~~

Output:

~~~text
large circle: 2.0
~~~

The variable `c` is in scope on the right-hand side of `&&` because by the time Java evaluates that side, the pattern on the left-hand side has matched. Conversely, if `instanceof` returns false, `c` is not brought into scope.

Avoid confusing this with `||`, where the right-hand side can execute when the left-hand pattern did not match; using an out-of-scope pattern variable will be rejected by the compiler.

### What Type Patterns Do Not Solve

Type patterns still keep **sequential `if` branches** and still require calling accessors:

~~~java
if (shape instanceof Triangle t) {
    double ax = t.a().x();
    double ay = t.a().y();
    // ...
}
~~~

When the structure is a multi-level nested record and multiple components are needed, chained accessor calls can make the code verbose. That is where **record patterns** shine.

## 5. Record Patterns: Deconstructing Geometry on Match

Java 21 allows using record patterns directly inside `instanceof`:

~~~java
Object value = new Circle(new Point(1, 2), 2);

if (value instanceof Circle(Point(var x, var y), var r)) {
    System.out.println("center=" + x + "," + y + "; radius=" + r);
}
~~~

Output:

~~~text
center=1.0,2.0; radius=2.0
~~~

How to read it:

1. `Circle(...)` requires the input to be a `Circle`.
2. `Point(var x, var y)` is a **nested record pattern** that deconstructs the `center` component into `x` and `y`.
3. `var r` receives the `radius` component value, with inferred type `double`.
4. No need to cast `Circle`, call `circle.center()`, and then call `center.x()`/`center.y()` step by step.

One advantage is that **the data structure is expressed directly in the pattern**, letting readers immediately see which components are being used.

Record patterns do not require deconstructing every level: `Circle(var center, var radius)` is still valid and keeps `center` as a `Point`. **Only destructure deeply when you actually use the inner data**, rather than unpacking every component all the time.

### Record Pattern vs. Constructor Call

~~~java
new Circle(new Point(1, 2), 2);  // Creates a new record.

value instanceof Circle(Point(var x, var y), var r); // Matches an existing record.
~~~

A pattern **does not create a copy** of the record. It inspects and extracts components of an already existing object. Therefore, do not assume a record pattern triggers a `new Circle` or incurs separate allocation overhead just because the parenthesized syntax resembles a constructor.

## 6. `switch` on `sealed Shape`: Eliminating Long `if` Chains

When the subtype set is known to be closed, the area function can be expressed as a `switch expression`:

~~~java
static double areaRecordSwitch(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    return switch (shape) {
        case Circle(var center, var radius) ->
                Math.PI * radius * radius;

        case Rectangle(var origin, var width, var height) ->
                width * height;

        case Triangle(Point(var ax, var ay),
                      Point(var bx, var by),
                      Point(var cx, var cy)) ->
                Math.abs(cross(ax, ay, bx, by, cx, cy)) / 2.0;
    };
}
~~~

Each `case` maps a shape directly to its formula. `Triangle` uses nested record patterns to extract the three vertex coordinates; the cross product formula no longer needs long accessor chains.

**Why is there no `default`?** `Shape` is sealed with exactly three record subtypes: `Circle`, `Rectangle`, and `Triangle`. The unguarded branches cover all of them, so the Java 21 compiler can verify **exhaustiveness** over the currently permitted subtypes.

This brings an important maintenance benefit. If you later add an `Ellipse` subtype to `permits` and recompile, a `switch expression` missing a matching branch can be flagged by the compiler as **not exhaustive**. With a traditional `if` chain, you typically only discover a fallback behavior or runtime error if you forget to handle it.

### `switch` Is Not Always the Only Answer

- If there is only **a single check**, `if (obj instanceof Circle c)` can be shorter and easier to read.
- If there is **a closed set of variants** and you need to compute a result for every variant, a `switch expression` fits very well.
- If the behavior naturally belongs to each subtype's responsibility, you can place an abstract method on the interface and implement it via **polymorphism**, rather than putting every operation into a centralized `switch`.
- If the system needs external plugins to add shapes freely, `sealed` may not be appropriate because it intentionally restricts the subtype set.

Pattern matching is a design choice, not a mandate to eliminate every `if`/cast or every polymorphic method.

## 7. Perimeter and Anchor Coordinates: Applying Pattern Styles Flexibly

For perimeter, we can keep the triangle's three point variables instead of deconstructing all the way down to six coordinates:

~~~java
static double perimeter(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    return switch (shape) {
        case Circle(var center, var radius) ->
                2 * Math.PI * radius;

        case Rectangle(var origin, var width, var height) ->
                2 * (width + height);

        case Triangle(var a, var b, var c) ->
                Math.hypot(a.x() - b.x(), a.y() - b.y())
                + Math.hypot(b.x() - c.x(), b.y() - c.y())
                + Math.hypot(c.x() - a.x(), c.y() - a.y());
    };
}
~~~

Notice `Triangle(var a, var b, var c)` uses **shallow component patterns**: the three variables `a`, `b`, `c` have type `Point`. Because the perimeter calculation needs each point to compute distances, this is more readable than unpacking all six coordinates directly in the `case`.

On the other hand, when only anchor coordinates are needed for display, nested record patterns are helpful:

~~~java
static String anchor(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    return switch (shape) {
        case Circle(Point(var x, var y), var radius) ->
                "circle-center:" + x + "," + y;

        case Rectangle(Point(var x, var y), var w, var h) ->
                "rect-origin:" + x + "," + y;

        case Triangle(Point(var ax, var ay), var b, var c) ->
                "triangle-a:" + ax + "," + ay;
    };
}
~~~

The methods in this section are **illustrative snippets** inside a class that has the corresponding records and helper methods. The full standalone program is in section 8.

### Three Guidelines for Choosing Pattern Depth

1. **Need the whole object?** Use `var point` or a type pattern `Point p`; do not deconstruct unnecessarily.
2. **Need only a few components?** Use nested record patterns at just the required depth.
3. **Complex calculation rules?** Consider extracting a clearly named helper method instead of turning a `case` into a giant expression.

The goal is for readers to immediately recognize **shape type → extracted data → applied formula**.

## 8. Complete Java 21 Program — Comparing All Three Approaches

Save the following code into **`GeometryPatternComparisonDemo.java`**. The program requires no libraries outside the JDK.

~~~java
public class GeometryPatternComparisonDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    record Point(double x, double y) {
        Point {
            if (!Double.isFinite(x) || !Double.isFinite(y)
                    || Math.abs(x) > 1_000_000
                    || Math.abs(y) > 1_000_000) {
                throw new IllegalArgumentException("coordinates");
            }
        }
    }

    record Circle(Point center, double radius) implements Shape {
        Circle {
            requirePoint(center, "center");
            requireSize(radius, "radius");
        }
    }

    record Rectangle(Point origin, double width, double height)
            implements Shape {
        Rectangle {
            requirePoint(origin, "origin");
            requireSize(width, "width");
            requireSize(height, "height");
        }
    }

    record Triangle(Point a, Point b, Point c) implements Shape {
        Triangle {
            requirePoint(a, "a");
            requirePoint(b, "b");
            requirePoint(c, "c");
            double cross = cross(
                    a.x(), a.y(), b.x(), b.y(), c.x(), c.y());
            if (cross == 0.0 || !Double.isFinite(cross)) {
                throw new IllegalArgumentException(
                        "degenerate triangle");
            }
        }
    }

    static Point requirePoint(Point p, String field) {
        if (p == null) {
            throw new IllegalArgumentException(field);
        }
        return p;
    }

    static void requireSize(double size, String field) {
        if (!Double.isFinite(size) || size <= 0 || size > 1_000_000) {
            throw new IllegalArgumentException(field);
        }
    }

    static double cross(double ax, double ay, double bx, double by,
                        double cx, double cy) {
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
    }

    static double areaLegacy(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        if (shape instanceof Circle) {
            Circle c = (Circle) shape;
            return Math.PI * c.radius() * c.radius();
        }
        if (shape instanceof Rectangle) {
            Rectangle r = (Rectangle) shape;
            return r.width() * r.height();
        }
        if (shape instanceof Triangle) {
            Triangle t = (Triangle) shape;
            return Math.abs(cross(
                    t.a().x(), t.a().y(),
                    t.b().x(), t.b().y(),
                    t.c().x(), t.c().y())) / 2.0;
        }
        throw new IllegalStateException("Unknown shape");
    }

    static double areaTypePattern(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        if (shape instanceof Circle c) {
            return Math.PI * c.radius() * c.radius();
        }
        if (shape instanceof Rectangle r) {
            return r.width() * r.height();
        }
        if (shape instanceof Triangle t) {
            return Math.abs(cross(
                    t.a().x(), t.a().y(),
                    t.b().x(), t.b().y(),
                    t.c().x(), t.c().y())) / 2.0;
        }
        throw new IllegalStateException("Unknown shape");
    }

    static double areaRecordSwitch(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(var center, var radius) ->
                    Math.PI * radius * radius;
            case Rectangle(var origin, var width, var height) ->
                    width * height;
            case Triangle(Point(var ax, var ay),
                          Point(var bx, var by),
                          Point(var cx, var cy)) ->
                    Math.abs(cross(
                            ax, ay, bx, by, cx, cy)) / 2.0;
        };
    }

    static double perimeter(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(var center, var radius) ->
                    2 * Math.PI * radius;
            case Rectangle(var origin, var width, var height) ->
                    2 * (width + height);
            case Triangle(var a, var b, var c) ->
                    Math.hypot(a.x() - b.x(), a.y() - b.y())
                    + Math.hypot(b.x() - c.x(), b.y() - c.y())
                    + Math.hypot(c.x() - a.x(), c.y() - a.y());
        };
    }

    static String anchor(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(Point(var x, var y), var radius) ->
                    "circle-center:" + x + "," + y;
            case Rectangle(Point(var x, var y), var w, var h) ->
                    "rect-origin:" + x + "," + y;
            case Triangle(Point(var ax, var ay), var b, var c) ->
                    "triangle-a:" + ax + "," + ay;
        };
    }

    static int passed = 0;

    static void checkClose(
            String label, double actual, double expected) {
        if (!Double.isFinite(actual) ||
                Math.abs(actual - expected) > 1e-9) {
            throw new AssertionError(
                    label + ": " + actual + " != " + expected);
        }
        ++passed;
        System.out.println("PASS " + label);
    }

    static void check(String label, boolean ok) {
        if (!ok) {
            throw new AssertionError(label);
        }
        ++passed;
        System.out.println("PASS " + label);
    }

    static void invalid(String label, Runnable run) {
        try {
            run.run();
            throw new AssertionError(
                    "Expected IllegalArgumentException: " + label);
        } catch (IllegalArgumentException expected) {
            check(label, true);
        }
    }

    static void expectNull(String label, Runnable run) {
        try {
            run.run();
            throw new AssertionError(
                    "Expected NullPointerException: " + label);
        } catch (NullPointerException expected) {
            check(label, true);
        }
    }

    public static void main(String[] args) {
        Shape circle = new Circle(new Point(1, 2), 2);
        Shape rect = new Rectangle(new Point(-1, 1), 3, 4);
        Shape triangle = new Triangle(
                new Point(0, 0), new Point(3, 0),
                new Point(0, 4));

        Shape[] shapes = { circle, rect, triangle };
        String[] labels = { "circle", "rect", "triangle" };
        double[] areas = { 4 * Math.PI, 12, 6 };
        double[] perimeters = { 4 * Math.PI, 14, 12 };
        String[] anchors = {
            "circle-center:1.0,2.0",
            "rect-origin:-1.0,1.0",
            "triangle-a:0.0,0.0"
        };

        for (int i = 0; i < shapes.length; ++i) {
            String label = labels[i];

            checkClose(label + "-legacy",
                    areaLegacy(shapes[i]), areas[i]);
            checkClose(label + "-type",
                    areaTypePattern(shapes[i]), areas[i]);
            checkClose(label + "-record",
                    areaRecordSwitch(shapes[i]), areas[i]);
            checkClose(label + "-perimeter",
                    perimeter(shapes[i]), perimeters[i]);
            check(label + "-anchor",
                    anchor(shapes[i]).equals(anchors[i]));
        }

        Object unknown = "not a shape";
        check("unrelated-instanceof",
                !(unknown instanceof Circle c));

        Object missing = null;
        check("null-instanceof",
                !(missing instanceof Circle c));

        check("record-value-equality",
                new Circle(new Point(1, 2), 2).equals(circle));

        invalid("zero-radius",
                () -> new Circle(new Point(0, 0), 0));
        invalid("negative-width",
                () -> new Rectangle(new Point(0, 0), -2, 3));
        invalid("nan-height",
                () -> new Rectangle(new Point(0, 0), 2, Double.NaN));
        invalid("infinite-coordinate",
                () -> new Point(Double.POSITIVE_INFINITY, 0));
        invalid("null-center",
                () -> new Circle(null, 2));
        invalid("collinear-triangle",
                () -> new Triangle(
                        new Point(0, 0),
                        new Point(1, 1),
                        new Point(2, 2)));
        invalid("null-triangle-point",
                () -> new Triangle(
                        new Point(0, 0), null, new Point(1, 1)));
        expectNull("null-area",
                () -> areaRecordSwitch(null));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

### Compile and Run

Use JDK 21 or later:

~~~bash
javac --release 21 GeometryPatternComparisonDemo.java
java GeometryPatternComparisonDemo
~~~

**Exact output:**

~~~text
PASS circle-legacy
PASS circle-type
PASS circle-record
PASS circle-perimeter
PASS circle-anchor
PASS rect-legacy
PASS rect-type
PASS rect-record
PASS rect-perimeter
PASS rect-anchor
PASS triangle-legacy
PASS triangle-type
PASS triangle-record
PASS triangle-perimeter
PASS triangle-anchor
PASS unrelated-instanceof
PASS null-instanceof
PASS record-value-equality
PASS zero-radius
PASS negative-width
PASS nan-height
PASS infinite-coordinate
PASS null-center
PASS collinear-triangle
PASS null-triangle-point
PASS null-area
ALL PASSED: 26
~~~

### How to Read the Test Suite

Each shape has **five** checks: three area implementations, one perimeter calculation, and one anchor-coordinate check. The three shapes make up the **first 15 checks**.

The remaining checks cover:

- `unrelated-instanceof`: a string is not a circle, so `instanceof Circle` returns false.
- `null-instanceof`: a null selector with direct `instanceof` also returns false.
- `record-value-equality`: records compare equal by their components; two `Circle`s with the same center and radius are equal according to `equals`.
- `zero-radius`, `negative-width`, `nan-height`, `infinite-coordinate`: constructors reject invalid sizes/coordinates.
- `null-center` and `null-triangle-point`: constructors reject missing nested records.
- `collinear-triangle`: a triangle with three collinear points has zero area and is rejected in the model.
- `null-area`: `areaRecordSwitch(null)` explicitly rejects null via `Objects.requireNonNull`.

The `checkClose` helper uses an absolute tolerance of `1e-9` to compare floating-point values, avoiding the requirement that every floating-point operation have an exact binary representation. Failed checks throw `AssertionError`, so `ALL PASSED: 26` appears only if every case passes.

**Note:** This test suite verifies representative results and key execution paths; it does not replace a specialized computational geometry test suite for extreme-magnitude inputs.

## 9. Comparing the Three Techniques by Engineering Criteria

| Criterion | Legacy `instanceof` + cast | `instanceof` type pattern | Record pattern + `switch` |
| --- | --- | --- | --- |
| Type identification | `instanceof Circle` then cast | `instanceof Circle c` | `case Circle(...)` |
| Manual cast | Yes | No | No |
| Data extraction | Call accessors on cast object | Call accessors on pattern variable | Extract components directly via pattern |
| Nested data | Chained accessors like `t.a().x()` | May still need accessors | `Triangle(Point(var ax,...),...)` |
| Control structure | `if`/`else` chain | `if`/`else` chain | `switch` over subtypes |
| Exhaustiveness with sealed shape | Not checked automatically like `switch expression` | Not checked automatically like `switch expression` | Compiler can verify all subtypes |
| Null contract | Must be defined separately | `instanceof null` returns false; method depends on policy | Pattern switch requires explicit null handling |
| Readability with a few subtypes | Fairly clear, but repeats cast | Concise, clear | May feel syntax-heavy for a single case |
| Readability with many closed variants | Gets long and easy to miss a case | Drops casts, still many branches | Centralized and easy to review |
| Performance | Depends on bytecode/JIT | Depends on bytecode/JIT | Depends on bytecode/JIT and workload |

### Decision Summary

- **Single type-check branch:** type pattern with `instanceof` is usually a natural drop-in replacement with minimal logic change.
- **Multiple subtypes producing a single result:** pattern `switch` over `sealed` has a clear advantage in exhaustiveness.
- **Records with nested data:** record patterns pay off when they cut down accessor chains and clarify the structure being processed.
- **Behavior owned by each shape:** consider placing `area()` or `perimeter()` on each subtype via polymorphism instead of funneling everything into one utility switch.

This is a **design and maintainability** decision; do not automatically equate fewer lines of code with faster runtime performance.

## 10. Null, Validation, and Common Misconceptions

### 10.1. Null Selector with `instanceof`

~~~java
Object value = null;
System.out.println(value instanceof Circle c); // false
~~~

Direct `instanceof` returns false when the selector is null. The pattern variable `c` has no usable value in the non-matching branch.

### 10.2. Null Selector with Pattern `switch`

In Java 21:

~~~java
// Describes pattern switch behavior:
// without a case null and without a prior check,
// a null selector can lead to a NullPointerException.
~~~

The main example uses `Objects.requireNonNull(shape, "shape")` before each `switch`, because the geometry API **does not accept null as a valid shape**. You can also write `case null` when null carries a domain meaning that needs handling; do not assume `default` catches null automatically.

### 10.3. Record Components Can Be Null

Even a pattern like `Circle(Point(var x, var y), var radius)` does not replace constructor validation. If `center` is null, the nested `Point(...)` pattern **does not match**. A `String` or `Point` component bound with `var` can still receive null if the record allows it. In particular, unconditional component patterns have different null semantics from an outer `instanceof`; do not generalize that every type pattern excludes null in every position.

In the main program, `Circle`, `Rectangle`, and `Triangle` have constructors that reject null `Point`s. That allows calculation sites to rely on **domain invariants**, rather than an automatic null guarantee from record patterns.

### 10.4. Geometric Data Must Be Valid

`Point` in the example rejects `NaN`, infinities, and coordinates with magnitude greater than `1_000_000`. `Circle`/`Rectangle` require positive, finite sizes up to `1_000_000`. `Triangle` requires three valid points and a finite, non-zero cross product.

The `1_000_000` limit is a **case study data-range convention** to keep simple arithmetic within predictable bounds, not a constant of geometry or Java. Mapping, CAD, or GIS projects may need different scales and numerically stable algorithms.

## 11. Geometric Precision: Patterns Do Not Fix Floating-Point Errors

Testing geometry with `double` has pitfalls unrelated to `instanceof` syntax:

1. **Floating-point rounding error:** not every real number can be represented exactly in `double`. Use an appropriate tolerance when comparing areas/perimeters instead of blind `==`.
2. **Nearly collinear triangles:** the example checks `cross == 0.0` to reject exact collinearity within the demo's scope. Real computational geometry algorithms may need **robust orientation predicates** or scale-aware tolerance policies.
3. **Coordinate magnitude:** coordinate differences and multiplications can overflow floating-point numbers for huge inputs. The demo bounds coordinates and checks `Double.isFinite(cross)`.
4. **Sign of `cross`:** clockwise vs. counter-clockwise vertex order produces opposite signs. Use `Math.abs(cross) / 2` so area is non-negative.
5. **Triangle perimeter:** requires all three side lengths; `Math.hypot` computes Euclidean distance from two coordinate differences.
6. **Rectangles:** the example defines axis-aligned rectangles and does not model rotation angles. If rotated shapes are needed, add rotation or vertices.
7. **Units:** radii, dimensions, and coordinates must use consistent units; area is in squared units, perimeter in linear units.

Pattern matching helps organize code. **Formulas, invariants, units, and precision** remain the responsibility of the geometric algorithms.

## 12. When Adding a New Shape, Which Approach Maintains Better?

Suppose we add `Ellipse(Point center, double radiusX, double radiusY)`.

With the `if` chains in `areaLegacy` or `areaTypePattern`, the Java compiler does not warn you that you **forgot the Ellipse branch**; the methods can fall through to the `IllegalStateException` error branch.

With `areaRecordSwitch` and `perimeter` being exhaustive `switch expression`s, if you add `Ellipse` to `Shape.permits` without adding its branch, **recompiling** reports a missing case error. This is a safety benefit when evolving a closed set of variants.

An illustrative subtype—**do not copy verbatim into the section 8 program** without updating `permits` and the `switch` statements:

~~~java
record Ellipse(Point center, double radiusX, double radiusY)
        implements Shape {
    Ellipse {
        requirePoint(center, "center");
        requireSize(radiusX, "radiusX");
        requireSize(radiusY, "radiusY");
    }
}
~~~

If you add `Ellipse`, its area formula is `π × radiusX × radiusY`. A general ellipse perimeter has no simple elementary formula like a circle's circumference, so you would need to choose an appropriate approximation algorithm or library and test its error bounds.

**Do not add `default -> 0` just to silence the compiler.** Doing so can hide bugs when new subtypes are added. If a real system must handle unknown variants by contract, a fallback can make sense, but it must be explicitly designed and documented.

## 13. When to Use Polymorphism Instead of Pattern Matching?

All three approaches in this article are forms of **consumer-side type branching**. Another option is to put the behavior into the contract:

~~~java
interface MeasurableShape {
    double area();
    double perimeter();
}
~~~

This is an **illustrative interface**. Each implementation computes its own area and perimeter; callers simply invoke `shape.area()` without a `switch`. This approach usually makes sense when:

- `area()` and `perimeter()` are core responsibilities of each shape.
- Many call sites use these behaviors.
- Subtypes are expected to be added frequently, while the set of operations rarely changes.

Conversely, pattern `switch` can be a better fit when:

- The subtype set is stable and **closed**.
- There are many independent transformations/representations (rendering, serialization, exporting, reporting) and you do not want to crowd every behavioral variant onto the domain objects.
- You want to write a transformation over variants in one central place and have the compiler check exhaustiveness.

A well-designed system can combine both: core behavior on the subtypes, and reporting or UI-layer adaptation using pattern `switch`.

**There is no absolute rule that “pattern matching is better than OOP.”** They solve different design problems.

## 14. Performance: Do Not Infer Speed from Fewer Casts

Removing explicit casts from source code does not guarantee the CPU skips a corresponding runtime operation. `javac` and the JIT compiler can generate and optimize type checks, casts, and record accesses in very similar ways.

For this case study, factors that can affect performance include:

- The distribution of shape types in the input.
- CPU branch prediction and branch ordering.
- JIT inlining and accessor optimizations.
- The cost of `Math.PI`, `Math.abs`, and `Math.hypot`.
- Allocation rate, shape creation frequency, and GC.
- Data size, cache locality, and API design.

Because triangle perimeter uses relatively significant `Math.hypot` operations, any difference between type-checking syntaxes is likely to be a small fraction.

To draw conclusions about speed, you need **controlled benchmarks** (such as JMH), verifying that all three approaches **compute the exact same results**, with the same workload, warm-up, and multiple forks. This article **does not report unmeasured ns/op numbers**.

In general, unless a benchmark proves a significant difference, prioritize readable, maintainable, and less error-prone code.

## 15. Common Mistakes When Moving from Casts to Patterns

**Mistake 1 — skipping the type check while keeping a direct cast.** `(Rectangle) value` when `value` is a `Circle` throws `ClassCastException`. Type patterns eliminate the need for manual casts after matching.

**Mistake 2 — confusing a record pattern with a constructor.** `Circle(Point(var x,...),var r)` does not create a new object; it deconstructs an existing one.

**Mistake 3 — deconstructing too deeply.** If you only need `Point` to call `Math.hypot`, keeping `var a` is better than unpacking six coordinates and making the branch hard to read.

**Mistake 4 — switching on `Object` and forgetting other types.** Exhaustiveness is only easy to check when the selector is modeled with an appropriate type, such as `sealed Shape`. On `Object`, a suitable fallback is required.

**Mistake 5 — confusing a null selector with a null component.** `obj instanceof Type x` directly returns false when the selector is null, whereas record components can still be null; and pattern `switch` must handle null according to its contract.

**Mistake 6 — thinking `sealed` validates geometric data.** `sealed` restricts subtypes; it does not forbid negative radii or collinear vertices. Constructors/factories are what protect these invariants.

**Mistake 7 — unconditionally adding `default` to an exhaustive switch.** It can mask missing a new subtype. For a closed set of variants, letting the compiler warn you is an advantage.

**Mistake 8 — neglecting `double` precision.** Nearly degenerate triangles, huge coordinates, and multiplications can yield unexpected results. Test numerical behavior independently of pattern syntax.

**Mistake 9 — changing logic during refactoring.** If the old version computed area via cross product and the new version uses a formula missing `Math.abs`, differing results are not a pattern-matching bug. Equivalence testing is required.

**Mistake 10 — forcing every business rule into one giant `switch`.** If each shape has distinct core behavior, polymorphism may be clearer. Patterns should be used when they help express structure, not merely because they are new.

## 16. Code Review Checklist and Exercises

Before migrating geometric code from the legacy approach to patterns:

1. Are the `Shape` subtype set and contract clearly defined?
2. Have area/perimeter formulas been verified independently?
3. Do the cast, type pattern, and record pattern versions behave identically on null, unknown subtypes, and valid data?
4. Do constructors reject non-positive radii/dimensions, `NaN`, infinities, and degenerate triangles as required by the domain?
5. Are nested record patterns used at just the necessary depth?
6. Is the `switch expression` exhaustive without a `default` hiding missing variants?
7. If `Shape` is extended, will the compiler and tests help catch operations that need updating?
8. Are hard-to-read arithmetic rules extracted into clearly named helpers?
9. Have null cases been considered for both the selector and components?
10. Is there actual benchmark evidence before claiming the new version is faster?

### Self-Practice Exercises

- **Exercise 1:** Write a `diameter(Shape shape)` method that only accepts `Circle`; compare the legacy approach, type pattern, and how to return a result when the shape is not a `Circle`.
- **Exercise 2:** Convert `perimeter` from pattern `switch` to an `if (shape instanceof ...)` chain and verify the results against the tests in the article.
- **Exercise 3:** Add `Ellipse` to `permits`, observe the compile errors on non-exhaustive `switch`es, update area, and try a perimeter approximation formula with error bounds testing.
- **Exercise 4:** Construct a `Triangle` with nearly collinear coordinates. Explain the limitation of checking `cross == 0.0` and propose a more robust numerical check.
- **Exercise 5:** Design `translate(Shape s, double dx, double dy)` returning a translated shape; use nested record patterns to preserve the data, and test cases where translation exceeds the domain coordinate limits.
- **Exercise 6:** Move `area()` and `perimeter()` to polymorphic methods on each subtype, then compare length, clarity, and ease of adding shapes vs. operations against pattern `switch`.

**Takeaway:** legacy `instanceof` + cast is valid but repeats type conversion; type patterns eliminate explicit casts; record patterns allow deconstructing geometric data upon matching; and pattern `switch` combined with `sealed Shape` lets the compiler verify all shapes are handled. **Choose the style that fits your domain complexity, protect invariants, verify formulas, and prioritize readability over unmeasured performance assumptions.**