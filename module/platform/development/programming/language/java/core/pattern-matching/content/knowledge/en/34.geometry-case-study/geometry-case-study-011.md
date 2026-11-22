# Separating Calculation from the Model When Needed: A Geometry Case Study with Java 21 Pattern Matching

## 1. The Design Problem: Is Geometry Data or Computation?

A mapping, CAD, or rendering application has objects such as circles, rectangles, and triangles. Each shape carries **the data describing it**: center and radius, origin and dimensions, or three vertices. The application also has to compute **area, perimeter, bounding box, intersection, proximity**, and may apply different rounding rules or unit systems.

A common design is to place all calculation methods directly on each model:

```java
record Circle(double radius) {
    double area() {
        return Math.PI * radius * radius;
    }

    double perimeter() {
        return 2 * Math.PI * radius;
    }
}
```

This approach is **not wrong**. When a formula is simple, immutable, and tightly bound to a single value, putting pure methods on a record can be very easy to understand. However, if calculations grow in complexity, algorithms vary by context, or multiple shape types must be coordinated, the model risks becoming a dumping ground for too many policies and technical concerns.

An alternative direction:

- **Model:** defines what a shape is, the state it must store, and the invariants required to construct a valid shape.
- **Pure calculator/service:** computes values from the model, with explicit input assumptions and numerical policies.
- **Pattern matching:** dispatches to the formula corresponding to the shape type.
- **Application boundary:** selects the unit system, formats results, persists data, caches, or handles infrastructure errors.

Example:

```java
// Illustrates the structure inside a class/service.
double area(Shape shape) {
    return switch (shape) {
        case Circle circle -> circleArea(circle.radius());
        case Rectangle rect -> rect.width() * rect.height();
        case Triangle triangle -> triangleArea(
            triangle.a(), triangle.b(), triangle.c());
    };
}
```

The snippet above assumes `Shape` is a sealed hierarchy with these three subtypes and that the helpers are already declared. Each case **selects a formula** rather than embedding repositories, HTTP calls, logging, or state mutation. The model can be used across many algorithms without forcing every record to contain all algorithms.

**Lesson goal:** understand **when to separate calculation from the model and when to keep it inside**, how to design value records with invariants, how to use Java 21 `switch` pattern matching exhaustively, how to test formulas, and how to handle numerical concerns such as units, degenerate values, and floating-point precision errors.

Version note: `record` has been a standard feature since **Java 16**; pattern matching for `switch` (JEP 441) and record patterns (JEP 440) have been stable since **Java 21**. The standalone runnable example uses **JDK 21+** and does not require `--enable-preview`.

## 2. Distinguishing State, Invariant, Calculation, and Presentation

Four responsibilities are frequently mixed together:

| Responsibility | Question | Geometry Example | Typically Suitable Location |
| --- | --- | --- | --- |
| **State** | What is the object? | `Circle(center, radius)` | Record/model |
| **Invariant** | What data constitutes a valid object? | Positive, finite radius; non-null center | Canonical constructor/factory |
| **Calculation** | What can be derived from the state? | Area, perimeter, distance, intersection | Pure method in model **or** separate calculator |
| **Presentation / I/O** | How is the result used/displayed/stored? | Round to 2 decimal places, write JSON, draw on screen | UI/application/adapter |

The easiest part to confuse is **invariant versus calculation**. Invariants must be checked at object creation time to prevent meaningless state; calculations can be performed afterward for a specific request.

For example, the `Circle` constructor checking `radius > 0` is part of the model, even though it evaluates a comparison. Not every arithmetic operator needs to be moved to a calculator. Conversely, computing the intersection area of two polygons depends on a complex algorithm and may need to account for tolerance; that is usually better placed in a separate service.

### Why shouldn't you separate mechanically?

If you only have:

```java
record Square(double side) {
    double area() {
        return side * side;
    }
}
```

and no calculation policy varies, calling `square.area()` can be clearer than `squareAreaCalculator.calculate(square)`. Splitting into dozens of one-line classes or functions just to obey a slogan like "models only hold data" sometimes creates an **anemic domain model** and unnecessary layers of indirection.

**The right criterion is responsibility and axis of change**, not "a model must never have methods."

## 3. When Should Calculation Be Moved to a Separate Component?

Practical signs:

1. **Many algorithms over the same set of shapes.** Not just area/perimeter, but also rasterization, intersection, collision detection, SVG export, clipping, hit testing.
2. **Policies have multiple versions.** Planar Euclidean calculations differ from geographic coordinate calculations; approximate results differ from results requiring controlled error bounds.
3. **Calculations involve multiple objects.** Distance between two shapes, intersection, polygon union/difference; there is no single natural "owner" of the logic.
4. **High cost or external resources.** Intersection analysis over large shape sets, mesh generation, elevation data queries, GPU, I/O.
5. **Need to test algorithms independently.** Comparing multiple implementations or benchmarking without standing up the full application system.
6. **Pulling framework dependencies into the model.** A value model should only reflect state/invariants; it should not be forced to know about a DB, logger, mapper, UI, or specific graphics library.
7. **A record has to know about too many unrelated objects.** Adding a new algorithm always requires modifying many records even though their state has not changed.
8. **Caching/precision has its own lifecycle.** Caches keyed by zoom level, coordinate system, tolerance, or device should have a clear owner and invalidation strategy.

However, each sign must be evaluated in context. A pure, stable method on a value type does not by itself create a "bad architecture." When moving logic out, ask **which object owns the policy** and **what measurable benefit will be gained** (testability, reuse, cohesion, dependency control).

## 4. Designing the Geometry Model with a Sealed Hierarchy and Records

With Java 21, a concise option is:

```java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Point(double x, double y) {}

record Circle(Point center, double radius) implements Shape {}

record Rectangle(Point origin, double width, double height)
        implements Shape {}

record Triangle(Point a, Point b, Point c) implements Shape {}
```

This is a **sketch of type definitions**, without validation yet. The `sealed interface` expresses a known set of subtypes. Each `record` holds the state needed to describe the shape; components have compiler-generated accessors (`center()`, `radius()`, `a()`, ...).

Useful properties:
- Records provide component-based value equality and a default `toString`.
- Component state is final; changing dimensions means creating a new record.
- A sealed hierarchy supports **exhaustive `switch`** over the permitted subtypes.
- Pattern matching dispatches by type without manual `instanceof` followed by casting.

However, **you should not declare bare records for a domain with invariants**. `new Circle(null, -1)` still compiles and creates an object if the constructor does not validate. The model must decide what is valid.

### Constructors protect invariants; calculators protect calculation contracts

Example:

```java
record Circle(Point center, double radius) implements Shape {
    Circle {
        java.util.Objects.requireNonNull(center, "center");
        if (!Double.isFinite(radius) || radius <= 0) {
            throw new IllegalArgumentException(
                "radius must be positive and finite");
        }
    }
}
```

This is the model's exact responsibility: **never construct a Circle with a null center or an invalid radius**.

For `Point`, check `Double.isFinite(x)` and `Double.isFinite(y)` if the problem requires finite coordinates. Only checking `x < min || x > max` can let `NaN` slip through because comparisons with `NaN` return `false`.

**Important:** Even when coordinates and dimensions are finite, a very large multiplication can still overflow to `Infinity`. A constructor that rejects `NaN`/`Infinity` inputs **does not automatically guarantee** that every calculation result is finite. The calculator must have a policy for numeric ranges and tolerances if the domain requires high precision.

## 5. Java 21 Pattern Matching at the Calculation Boundary

A calculator can use a `switch` expression over `Shape`:

```java
static double area(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    return switch (shape) {
        case Circle c ->
            Math.PI * c.radius() * c.radius();

        case Rectangle r ->
            r.width() * r.height();

        case Triangle t ->
            triangleArea(t.a(), t.b(), t.c());
    };
}
```

This illustrative snippet assumes `Shape` is sealed and `triangleArea` already exists.

### Why is a type pattern often enough?

`case Circle c` binds a `Circle` with a more specific type than `Shape`; `c.radius()` is type-checked by the compiler. If you only need `radius`, there is no need to write `Circle(var center, var radius)` to deconstruct `center` as well. Avoiding an overly deep record pattern helps:
- Reduce coupling to the entire record header;
- Avoid accidentally adding unnecessary nested deconstruction or null checks;
- Keep the calculation close to the formula being read.

On the other hand, a **record pattern** can be very clear when all extracted components are actually used:

```java
// Illustrative case label; must be placed inside a switch taking a Shape.
case Triangle(Point(var ax, var ay),
              Point(var bx, var by),
              Point(var cx, var cy)) ->
    Math.abs((bx - ax) * (cy - ay)
           - (by - ay) * (cx - ax)) / 2.0;
```

Here the coordinate variables are the direct inputs to the shoelace/determinant formula for a triangle. For a simple formula, the reader immediately sees the inputs and the computation. However, when tolerance handling, overflow checks, or a more stable algorithm is needed, it is better to call a clearly named `triangleArea` helper.

**Avoid the rule "always deconstruct as deeply as possible"**: a pattern is not an end in itself. Extract only the components truly relevant to the branch.

### Exhaustiveness and model evolution

With `sealed interface Shape permits Circle, Rectangle, Triangle`, the three cases `Circle`, `Rectangle`, and `Triangle` are exhaustive for every non-null `Shape` in the hierarchy. No `default` branch is needed:

```java
return switch (shape) {
    case Circle c -> circleArea(c.radius());
    case Rectangle r -> r.width() * r.height();
    case Triangle t -> triangleArea(t.a(), t.b(), t.c());
};
```

When a permitted subtype such as `Polygon` is added without a covering case, the compiler will remind you to update the `switch` expression. That is an **important trade-off**:
- Good when **the set of variants is relatively stable** and new algorithms are expected to be added frequently;
- More work when **new `Shape` subtypes are added frequently**, because many calculators/switches must be updated.

If the system is plugin-based and allows `Shape` types to be added from external modules, a closed sealed hierarchy may not fit. In that case, consider polymorphism, visitor, a class-keyed registry, or an abstraction that supports extensibility, rather than forcing every requirement into a `switch`.

### Null is a separate API contract

In the calculator example, `Objects.requireNonNull(shape, "shape")` rejects a `null` selector with an NPE carrying a clear message **before the `switch`**. This is a valid choice when `null` input is disallowed.

If the application wants to return a default value or an error `Result`, it can use `case null` inside `switch` instead of throwing an exception; however, **do not assume `default` will catch `null`** in an enhanced `switch`. Stay consistent with the method's contract.

## 6. Triangle Case Study: Where Should the Formula Live for Clarity?

A triangle is defined by three vertices on a plane:

```java
record Triangle(Point a, Point b, Point c) implements Shape {}
```

Area can be computed using the determinant (2D cross product):

\[
A = \frac{1}{2}\left| (x_b-x_a)(y_c-y_a) - (y_b-y_a)(x_c-x_a) \right|
\]

Perimeter:

\[
P = d(a,b) + d(b,c) + d(c,a),
\quad d(u,v)=\sqrt{(u_x-v_x)^2+(u_y-v_y)^2}
\]

In Java:

```java
static double triangleArea(Point a, Point b, Point c) {
    double dx1 = b.x() - a.x();
    double dy1 = b.y() - a.y();
    double dx2 = c.x() - a.x();
    double dy2 = c.y() - a.y();
    return Math.abs(dx1 * dy2 - dy1 * dx2) / 2.0;
}

static double distance(Point a, Point b) {
    return Math.hypot(b.x() - a.x(), b.y() - a.y());
}
```

**`Math.hypot`** is usually preferable to writing `Math.sqrt(dx * dx + dy * dy)` by hand because it is designed to reduce intermediate overflow/underflow in certain value ranges. However, if coordinate differences have already overflowed or inputs are extreme, geometric computations can still produce non-finite values. Do not claim `Math.hypot` solves every numerical issue.

### Degenerate triangles are a domain decision

Three collinear points yield an area of `0`. A drawing application might allow a "degenerate triangle" as a temporary editing state; a material-volume calculation application might **forbid** it.

Two different contracts:

- **The model allows any three vertices** (non-null, finite): the calculator can return area `0`.
- **The model requires a triangle with positive area**: the constructor or factory must reject coincident/collinear points according to a defined numerical criterion.

Checking "three non-collinear vertices" requires geometric calculation, yet because it is a **model invariant**, calling a validation helper from the constructor/factory is still appropriate. "Separating calculation" does not mean forbidding the model from enforcing invariants.

### Tolerance is not just a fixed EPS constant

With `double`, checking `cross == 0` can be sensitive to rounding error, yet replacing it with `Math.abs(cross) < 1e-9` is not always right across all scales either. An absolute error threshold means very different things at centimeter coordinates versus millions-of-meters coordinates.

If an application needs robust geometry handling:
- Define the coordinate system, units, and coordinate domain.
- Choose a scale-dependent tolerance or a more accurate algorithm.
- Check for overflow/underflow and numerical cancellation.
- Separate the precision policy from the `Point`/`Triangle` types when multiple contexts exist.
- Write tests for nearly collinear points, very large/very small dimensions, and permuted vertex order.

This article's demo uses basic formulas with small coordinates so the output is deterministic and easy to verify.

## 7. Area and Perimeter: Shared Domain, Different Operations

Both area and perimeter operate on the same set of shapes, yet they are **two distinct operations**. Both methods can live in `PlanarCalculator`:

```java
double area(Shape shape) { /* switch by shape type */ }

double perimeter(Shape shape) { /* switch by shape type */ }
```

If the model contains both calculations:

```java
record Rectangle(Point origin, double width, double height)
        implements Shape {
    double area() { return width * height; }
    double perimeter() { return 2.0 * (width + height); }
}
```

that works fine when the model is small and each shape only has a few formulas. But when the app needs to add **bounding box**, **point containment**, **intersection**, **distance to edge**, **transform**, **rasterize**, **serialize to SVG**, and so on, you should not have to edit every record each time a new feature is added.

**Design along the axis of variation:**
- **Adding many operations, rarely adding `Shape` subtypes:** sealed hierarchy + calculator + `switch` is usually the clearest choice.
- **Adding many `Shape` subtypes, rarely adding operations:** polymorphism with `Shape.area()`/`Shape.perimeter()` can be simpler, because each new subtype implements them itself.
- **Both dimensions change frequently:** consider visitor, double dispatch, strategy, or a registry; evaluate the complexity instead of automatically picking one technique.

Pattern matching makes calculator dispatch concise, but it does not eliminate this trade-off.

## 8. Complete Java 21 Program: Pure Model and Calculation Service

This is a **self-contained program with no external libraries**, representing three shape types using records and a sealed interface. The records have constructors that protect basic state. A `PlanarCalculator` handles area/perimeter; the application uses it to produce a report.

File: **`GeometryCalculationSeparationDemo.java`**

```java
import java.util.Locale;
import java.util.Objects;

public class GeometryCalculationSeparationDemo {

    sealed interface Shape permits Circle, Rectangle, Triangle {}

    record Point(double x, double y) {
        Point {
            if (!Double.isFinite(x) || !Double.isFinite(y)) {
                throw new IllegalArgumentException(
                    "Coordinates must be finite");
            }
        }
    }

    record Circle(Point center, double radius) implements Shape {
        Circle {
            Objects.requireNonNull(center, "center");
            if (!Double.isFinite(radius) || radius <= 0) {
                throw new IllegalArgumentException(
                    "Radius must be positive and finite");
            }
        }
    }

    record Rectangle(Point origin, double width, double height)
            implements Shape {
        Rectangle {
            Objects.requireNonNull(origin, "origin");
            if (!Double.isFinite(width) || width <= 0
                    || !Double.isFinite(height) || height <= 0) {
                throw new IllegalArgumentException(
                    "Width and height must be positive and finite");
            }
        }
    }

    // Contract: three non-null, finite points.
    // Collinear points are allowed to support editing tools.
    record Triangle(Point a, Point b, Point c) implements Shape {
        Triangle {
            Objects.requireNonNull(a, "a");
            Objects.requireNonNull(b, "b");
            Objects.requireNonNull(c, "c");
        }
    }

    // Calculation separated from the state-holding records.
    static final class PlanarCalculator {

        double area(Shape shape) {
            Objects.requireNonNull(shape, "shape");
            return switch (shape) {
                case Circle circle ->
                    Math.PI * circle.radius() * circle.radius();

                case Rectangle rectangle ->
                    rectangle.width() * rectangle.height();

                case Triangle triangle ->
                    triangleArea(
                        triangle.a(), triangle.b(), triangle.c());
            };
        }

        double perimeter(Shape shape) {
            Objects.requireNonNull(shape, "shape");
            return switch (shape) {
                case Circle circle ->
                    2.0 * Math.PI * circle.radius();

                case Rectangle rectangle ->
                    2.0 * (rectangle.width() + rectangle.height());

                case Triangle triangle ->
                    distance(triangle.a(), triangle.b())
                    + distance(triangle.b(), triangle.c())
                    + distance(triangle.c(), triangle.a());
            };
        }

        private double triangleArea(Point a, Point b, Point c) {
            double dx1 = b.x() - a.x();
            double dy1 = b.y() - a.y();
            double dx2 = c.x() - a.x();
            double dy2 = c.y() - a.y();

            return Math.abs(dx1 * dy2 - dy1 * dx2) / 2.0;
        }

        private double distance(Point a, Point b) {
            return Math.hypot(
                b.x() - a.x(),
                b.y() - a.y());
        }
    }

    // Record pattern used only when reading the structure is needed.
    static String describe(Shape shape) {
        Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(Point(var x, var y), var radius) ->
                String.format(
                    Locale.ROOT,
                    "Circle center=(%.0f,%.0f) radius=%.0f",
                    x, y, radius);

            case Rectangle rectangle ->
                "Rectangle has width and height";

            case Triangle triangle ->
                "Triangle has three vertices";
        };
    }

    static void show(String label, Shape shape,
                     PlanarCalculator calculator) {
        System.out.printf(
            Locale.ROOT,
            "%s: area=%.2f, perimeter=%.2f%n",
            label,
            calculator.area(shape),
            calculator.perimeter(shape));
    }

    public static void main(String[] args) {
        PlanarCalculator calculator = new PlanarCalculator();

        Shape circle = new Circle(new Point(0, 0), 2);
        Shape rectangle = new Rectangle(new Point(1, 1), 3, 4);
        Shape triangle = new Triangle(
            new Point(0, 0),
            new Point(3, 0),
            new Point(0, 4));
        Shape degenerate = new Triangle(
            new Point(0, 0),
            new Point(1, 1),
            new Point(2, 2));

        show("Circle", circle, calculator);
        show("Rectangle", rectangle, calculator);
        show("Triangle", triangle, calculator);
        show("Degenerate", degenerate, calculator);

        System.out.println(describe(circle));
        System.out.println(describe(triangle));

        System.out.println("Equivalent value: "
            + circle.equals(new Circle(new Point(0, 0), 2)));

        try {
            new Circle(new Point(0, 0), -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid radius rejected");
        }

        try {
            calculator.area(null);
        } catch (NullPointerException ex) {
            System.out.println("Null shape rejected");
        }
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 GeometryCalculationSeparationDemo.java
java GeometryCalculationSeparationDemo
```

**Expected output:**

```text
Circle: area=12.57, perimeter=12.57
Rectangle: area=12.00, perimeter=14.00
Triangle: area=6.00, perimeter=12.00
Degenerate: area=0.00, perimeter=5.66
Circle center=(0,0) radius=2
Triangle has three vertices
Equivalent value: true
Invalid radius rejected
Null shape rejected
```

### Why is the output correct?

**Circle:** radius is `2`, so area is `π × 2² = 4π ≈ 12.5664`; perimeter is `2π × 2 = 4π ≈ 12.5664`. `printf(Locale.ROOT, "%.2f")` formats both as `12.57`, using a dot as the decimal separator regardless of the machine's default locale.

**Rectangle:** width `3`, height `4`; area `3×4=12`, perimeter `2×(3+4)=14`. The `origin` component describes the shape's position, but does not participate in the area/perimeter formulas for an axis-aligned rectangle in this model.

**Triangle:** the three vertices `(0,0)`, `(3,0)`, `(0,4)` form a right triangle. Area is `3×4/2=6`, and the sides are `3`, `5`, `4`, giving perimeter `12`.

**Degenerate:** the three points `(0,0)`, `(1,1)`, `(2,2)` are collinear; the determinant is `0` and the area is `0`. Perimeter computed as **the sum of the three segments connecting the vertices** is still `√2 + √2 + 2√2 = 4√2 ≈ 5.65685`, formatted as `5.66`. Another domain might reject degenerate triangles; this program intentionally allows them to illustrate the policy.

**describe(circle):** the nested record pattern deconstructs the `Point` center because the description needs the coordinates, not because every formula must unpack every component. For `Rectangle`/`Triangle`, simple type patterns are used. This is an example of **choosing the deconstruction depth according to the goal**.

**Equivalent value:** both `Circle` records hold `Point(0,0)` and radius `2`, so record `equals` compares components meaningfully in this case. With `double`, special cases such as `-0.0` and `NaN` require care; here the model validates finite inputs and the demo data is small.

**Invalid radius / Null shape:** the record rejects a negative radius upon creation; the calculator rejects a `null` `Shape` before computing. These are two distinct contract layers.

**This is a simple planar math example**; it does not yet handle polygon intersection, rotation, geographic coordinate systems, map projections, dimensional units, strict rounding errors, or robust arithmetic in extreme ranges.

## 9. When Should Calculation Results Have Their Own Types?

`double` is convenient for demos, but many systems need a clearer contract:

```java
record Area(double squareMeters) {
    Area {
        if (!Double.isFinite(squareMeters)
                || squareMeters < 0) {
            throw new IllegalArgumentException(
                "Area must be finite and non-negative");
        }
    }
}

record Length(double meters) {
    Length {
        if (!Double.isFinite(meters) || meters < 0) {
            throw new IllegalArgumentException(
                "Length must be finite and non-negative");
        }
    }
}
```

These records help prevent mixing up **meters** and **square meters**, while also rejecting non-finite results. This is an **illustrative declaration pattern**, not part of the main program.

A strict calculator can return `Area`/`Length` instead of `double`, but must account for operations that could overflow before constructing the object. For example:

```java
double computed = /* area formula */;
if (!Double.isFinite(computed)) {
    throw new ArithmeticException("Non-finite geometry result");
}
Area area = new Area(computed);
```

The snippet above is a structural pattern inside a method with appropriate variables and formulas. Whether to throw an exception or return a typed error depends on business requirements.

**Do not mix units:** If a `Point` has pixel coordinates, computed lengths are in pixels and areas are in square pixels. If coordinates are latitude/longitude, applying Euclidean formulas directly to degrees usually **does not** produce true area/perimeter in meters. GIS systems require an appropriate coordinate reference system/projection or dedicated geodesic algorithms.

When unit or precision policies vary by context, that is a strong reason to separate calculation from pure records.

## 10. Different Calculation Policies: Strategy Instead of Stuffing into the Model

Suppose the application has two policies:
- **Planar geometry:** computes area/perimeter on a flat plane.
- **GIS/geodesic geometry:** computes on a curved surface with a specific coordinate reference system.

`Circle.area()` should not have to guess which system it is in if the model only stores `x,y` coordinates with no geographic semantics. An abstraction could be:

```java
interface GeometryCalculator {
    double area(Shape shape);
    double perimeter(Shape shape);
}
```

In a real system, `PlanarCalculator` and `GeodesicCalculator` implementations need **matching data contracts**: you must not silently treat planar `Point` coordinates as latitude/longitude or apply a geodesic formula without a datum/projection. You can use a separate `GeoPoint` model and a service with an explicit coordinate reference policy.

Example of injecting a calculator into a use case:

```java
// Application pattern, not a standalone program.
double calculateArea(Shape shape, GeometryCalculator calculator) {
    return calculator.area(shape);
}
```

**Benefits:** the same model value can be evaluated under different policies, and services can be tested independently. **Limitation:** this abstraction adds unnecessary complexity if in reality there is only one stable formula; do not introduce a strategy interface before a real need for variation arises.

### Integration notes

A pure calculator can return results without:
- Writing to a database;
- Making HTTP calls;
- Emitting sensitive logs;
- Mutating shape coordinates;
- Mutating static state.

This makes unit tests deterministic and easy to parallelize. If caching is needed for expensive computations, the cache should have a clear owner, key, and invalidation policy. An immutable record makes a good key if all its components have stable equality/hash semantics; if any component is a mutable array or collection, be careful.

## 11. Precision, NaN, Infinity, and Overflow

`double` values do not automatically make geometry accurate in every range.

### 11.1. Finite inputs can still produce overflowing outputs

`radius = 1e308` is a finite, positive `double`; however, `Math.PI * radius * radius` can become `Infinity`. If the domain forbids non-finite results, the calculator must check the output or apply an appropriate formula, representation, and input range.

### 11.2. Cancellation errors from subtracting nearly equal values

The determinant for three nearly collinear points can suffer from **catastrophic cancellation**, especially when coordinates are large and differences are small. Rounding the final output only hides the display artifact; it does not fix the numerical error in the computation.

### 11.3. Tolerance must be context-aware

A fixed epsilon such as `1e-9` is not a universal "correct standard" across all measurement systems. If coordinates are in meters with large magnitudes, relative norms, scale-aware tolerances, or robust geometric predicates may be more appropriate. Such policies should be tested independently—another clear motivation for separating calculation from the model.

### 11.4. `double` arithmetic is not `BigDecimal` for every situation

`BigDecimal` is useful for decimal problems requiring exact base-10 precision control, but geometric operations (square roots, π, trigonometry) require a clear numerical policy; converting every `double` to `BigDecimal` does not automatically yield exact solutions. Choose libraries/algorithms based on requirements rather than applying a single numeric type blindly.

### 11.5. Rounding is a presentation or reporting decision

In the main program, `PlanarCalculator` returns unrounded `double` values. Only `show` formats with `%.2f`. Rounding inside the calculator and then feeding that rounded value into subsequent calculations can amplify accumulated error. Business reporting policies sometimes require rounding at a specific stage; document that contract clearly.

## 12. Performance Optimization: Compute When Needed and Measure Before Caching

Separating calculation helps identify **where resources are actually spent**:

- Circle/rectangle area is a tiny arithmetic operation; do not cache blindly.
- Triangle formulas with a few arithmetic operations are relatively cheap; recomputing can be simpler than maintaining a cache.
- Intersection between large polygons, clipping, or spatial indexing can be expensive; in those cases use a profiler and realistic data.
- Across thousands of shapes, allocating intermediate objects or hitting external systems in every branch can create overhead.
- Input-based caching must account for equality/hashing and shape lifecycle. A shape with mutable components is a dangerous cache key if its contents change.

**Do not use source-code line count as a benchmark.** A `switch` being shorter than `if` does not prove it is faster. In Java, benchmarks should account for warmup/JIT/GC, diverse shape datasets, and actual consumption of outputs. Use JMH or an appropriate profiler, and avoid timing `println`.

### Accessors and record patterns also have a cost

Record patterns read components via accessors. With default accessors, this is usually negligible, but if a record defines a custom accessor that performs heavy computation or I/O, deconstruction is no longer "free." Keep value-record accessors stable and side-effect-free, and only deconstruct components you actually need. If a helper reads components repeatedly, consider binding them to locals or snapshotting according to consistency requirements.

Optimizations must preserve behavior for normal inputs, `null`, degenerate shapes, and future variants.

## 13. Testing the Model and Calculator Separately

A major advantage of separation is that each test suite answers a distinct set of questions.

### 13.1. Model invariant tests

- `new Point(Double.NaN, 0)` is rejected under the finiteness contract.
- `new Circle(new Point(0,0), 0)` is rejected because radius must be positive.
- `new Rectangle(new Point(0,0), -1, 2)` is rejected.
- `new Triangle(null, b, c)` is rejected.
- Three collinear points **are allowed in the demo model**, and the area service returns `0`.

These tests do not need to invoke the calculator to verify that constructors protect state.

### 13.2. Formula tests

| Shape and Parameters | Expected Area | Expected Perimeter |
| --- | ---: | ---: |
| Circle radius 2 | `4π` | `4π` |
| Rectangle width 3, height 4 | 12 | 14 |
| Triangle (0,0),(3,0),(0,4) | 6 | 12 |
| Collinear Triangle (0,0),(1,1),(2,2) | 0 | `4√2` |

For floating-point values, use a reasonable tolerance comparison rather than `expected == actual` for formulas involving π or square roots. In the demo, output is formatted to 2 decimal places for readability, but **algorithm tests** should compare the raw `double` values before formatting.

### 13.3. Property tests (property-based or systematic example-based)

- Translating all vertices by the same vector does not change area or perimeter.
- Swapping two vertices of a triangle does not change its absolute area.
- For a positive scale factor `k`, lengths scale by `k` and areas scale by `k²` when there is no overflow and the geometry stays within the numeric range.
- A rectangle with swapped width/height preserves area and perimeter.
- Valid shapes have non-negative area and perimeter within the numeric range supported by the algorithm.

These are **mathematical properties**, not absolute laws for every extreme `double` value; set tolerances and validate inputs appropriately.

### 13.4. Exhaustiveness tests as the model evolves

If `Polygon implements Shape` is added to the `sealed` interface's `permits` list, `switch` expressions for `area`/`perimeter`/`describe` may no longer be exhaustive. The compiler forces updates if no covering case exists. This is an advantage for ensuring new shapes are not silently introduced without formulas.

Using `default -> 0` as a fallback can mask a shape missing its formula: the app still runs but returns the wrong area. For a sealed hierarchy with a known set of subtypes, **avoiding arbitrary `default` branches** is worth considering.

## 14. Refactoring from a Fat Model to a Calculator

Suppose each model currently has `area()` and `perimeter()`, and the team wants to extract them because many new algorithms are coming.

A behavior-preserving workflow:

**Step 1. Inventory current formulas and policies.** Note units, precision, rounding, degenerate-shape rules, exceptions, and whether any side effects exist.

**Step 2. Lock down model contracts.** Constructors should protect valid shape data; do not alter validation just because methods are moving.

**Step 3. Create a separate calculator with a clear API.** For example, `double area(Shape)`/`double perimeter(Shape)`. If policies are needed, decide on the abstraction here; do not add a strategy interface if there is only one policy.

**Step 4. Move formulas while preserving semantics.** Use `switch` over subtypes, and extract helpers for triangles or long formulas. Do not change formulas and rounding rules at the same time unless explicitly required by the business.

**Step 5. Keep presentation out of the calculator.** Move `printf`/`String.format` to a reporter/adapter so numeric values can be tested before formatting.

**Step 6. Write regression tests.** Compare before/after on normal shapes, boundary cases, `null`, degenerate shapes, and different units, including exceptions on invalid input.

**Step 7. Update call sites and public APIs deliberately.** Removing `shape.area()` from a public interface can be a breaking change; consider deprecating or keeping a delegating adapter for a transition period if external callers exist.

**Step 8. Measure when there is a specific performance target.** Avoid mixing a clean-code refactor with complex numerical optimizations in the same change.

Do not declare a refactor successful merely because `Circle` is down to three lines. Success means **logic is in the right place, behavior is clear, and independent testing is easier**.

## 15. Common Pitfalls

| Pitfall | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| "Extract every calculation from the model" | Simple, pure methods get pushed through pointless indirection | Extract only when there is clear variation or complexity |
| Treating the model as a bag of fields without invariants | Allows `Circle(-1)`, `Rectangle(NaN)` | Validate in canonical constructor/factory |
| Calculator computes area and also writes to the database | Mixes numeric logic with side effects | Separate the application boundary; keep calculation pure |
| Using Euclidean formulas on lat/lon and calling the result m² | Wrong unit/coordinate system | Define a projection/geodesic policy |
| Using `default -> 0` for any unknown `Shape` | Hides missing algorithms when a subtype is added | Use sealed/exhaustive `switch` or explicit errors |
| Deeply nesting record patterns when only `radius` is needed | Unnecessary coupling and null constraints | Use a type pattern and only the needed accessors |
| Guards with side effects or I/O | Dispatching can mutate state or time out | Precompute in a service; keep guards pure |
| Assuming finite constructor inputs guarantee finite outputs | Multiplication can still overflow | Check outputs or bound input ranges/algorithms |
| Using a fixed epsilon across all dimensions | Fails at different scales | Use a context-aware tolerance policy |
| Rounding area inside the calculator and reusing it in further math | Unnecessary precision loss | Format only at the boundary when appropriate |
| Leaving degenerate-triangle validity unspecified | Code and tests have conflicting expectations | Document the contract; validate if the domain forbids it |
| Caching by a shape with mutable components | Key/hash can change, causing stale/wrong cache hits | Use immutable snapshots, clear ownership, and invalidation |
| Refactoring without testing formula changes | Refactor accidentally alters results or exceptions | Add regression + property tests |
| Adding a new `Shape` and forgetting some algorithms | An operation is left incomplete | Use exhaustive `switch` without arbitrary `default` |
| Benchmarking with `println` or a single input | Misleading performance conclusions | Use JMH/profiler and multiple input sizes |

## 16. Practice Exercises

**Exercise 1 — Classify responsibilities.** For `Circle(center, radius)`, identify the responsibilities of the constructor, `PlanarCalculator.area`, `show`, and a database persistence class. Why does radius validation still belong in the model even though it performs a numeric comparison?

**Exercise 2 — Add Square.** Add `record Square(Point origin, double side) implements Shape` with positive, finite `side` invariants. Update `permits`, area, and perimeter. Observe which `switch` expressions the compiler requires you to update before adding the new case.

**Exercise 3 — Compare designs.** In an app with only `Circle` and one simple area formula, explain the pros and cons of `circle.area()` versus `calculator.area(circle)`. Do not use "clean architecture always forbids domain methods" as a reason.

**Exercise 4 — Degenerate triangle.** Run `GeometryCalculationSeparationDemo.java`. Replace vertex `(2,2)` with `(2,3)` so the triangle is no longer collinear; compute the new area and perimeter. If degenerate triangles must be forbidden, would you enforce the check in the constructor, a factory, or a service? State the contract.

**Exercise 5 — Units.** `Point` currently uses pixel coordinates. If a new system reports distances in meters, what information and conversion steps are needed? Why can't you simply rename `perimeter()` to `perimeterMeters()`?

**Exercise 6 — Precision.** Test a `Circle` with a large radius near `Double.MAX_VALUE`. Check `Double.isFinite(calculator.area(circle))`. Propose an error policy or input domain for an API that does not allow infinite areas.

**Exercise 7 — Record patterns.** Write a case for `Triangle(Point(var ax,var ay),Point(var bx,var by),Point(var cx,var cy))` to extract coordinates and compute area. Compare it with `case Triangle t -> triangleArea(t.a(),t.b(),t.c())` as the formula grows more complex.

**Exercise 8 — Property test.** Create a new triangle by adding `(+100, -50)` to all three vertices. Do area and perimeter change? Use an appropriate tolerance when comparing `double` values.

**Exercise 9 — Add a new operation.** Implement `boundingBox(Shape)` in a separate calculator or the same service, without modifying the records if unnecessary. Provide sample inputs and expected outputs for all three shape types, and specify whether rectangles can be rotated or are always axis-aligned.

**Exercise 10 — Multi-policy design.** A mapping app uses both planar points and geographic points. Propose a way to distinguish the models or calculators to avoid mixing units; explain when a strategy interface provides real value.

## 17. Summary

**Separating calculation from the model when needed** is a decision driven by responsibility, rate of change, and testability—not a rule forcing every record to contain only fields.

In this Java 21 geometry case study:

- **Record models** store data and enforce invariants (finite `Point`, positive `Circle` radius, positive `Rectangle` width/height).
- **Pure calculators** implement area/perimeter formulas, can be extended by policy, and are tested independently.
- **`switch` pattern matching** over a sealed `Shape` selects the right algorithm, avoids casts, and provides exhaustiveness when the shape set is closed.
- **Record patterns** are used when component deconstruction is genuinely needed; avoid unpacking unrelated layers.
- **Nulls, degenerate triangles, units, tolerances, overflow, and formatting** must have explicit contracts rather than vague defaults.
- **Do not over-separate:** a simple, stable method on the model is sometimes still the best choice.

### References

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Java SE 21 — `Math.hypot`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#hypot(double,double)).
