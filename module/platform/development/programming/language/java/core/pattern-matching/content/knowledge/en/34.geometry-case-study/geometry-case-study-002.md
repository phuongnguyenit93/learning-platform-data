# Representing Rectangle and Circle with Records in Java 21

## 1. The problem: a concise, clear, and invariant-preserving geometry model

Suppose we are building a 2D geometry module that needs to represent **circles (`Circle`)** and **rectangles (`Rectangle`)**, compute area/perimeter, check whether a point lies inside a shape, and classify shapes using Java Pattern Matching.

We want the geometry data to:

- Have **clear type names**: `Circle` and `Rectangle` are variants of `Shape`.
- Carry **enough data** for computation, without needing arbitrary state fields.
- **Not be mutated** after initialization; scaling creates a new object.
- Be able to **validate invariants at creation time**: radius, width, and height must be finite and greater than 0; the shape's center must not be null.
- Be easy to compare by value in tests and easy to print when debugging.
- Work with `switch` type/record patterns to deconstruct and handle all variants exhaustively.

**Record** is the right choice for such **data carriers**. Java records became a standard feature in **Java 16 (JEP 395)**. When combined with **record patterns (JEP 440)** and **pattern matching for switch (JEP 441)** — both standard since **Java 21** — we can write shape-handling logic with concise syntax, without manual casting.

This lesson establishes a concrete geometry contract:

| Object | Stored state | Meaning |
| --- | --- | --- |
| `Point` | `x`, `y` | 2D real coordinates in a Cartesian system |
| `Circle` | `center: Point`, `radius: double` | Circle and circular disk with center and radius |
| `Rectangle` | `center: Point`, `width: double`, `height: double` | Rectangle with **edges parallel to the coordinate axes**, defined by center and dimensions |
| `Shape` | A `sealed interface` | Common type for supported shapes |

**Model limitations:** `Rectangle` here has **no rotation angle**; its edges are parallel to the X/Y axes (*axis-aligned rectangle*). "Inside the shape" includes the **boundary**. Length values must use the same unit, such as meters or pixels; do not mix them implicitly. To simplify the domain, shapes with zero length are considered **invalid**. Another problem might intentionally allow degenerate shapes, in which case the contract and tests must be updated.

## 2. From traditional Java classes to records

### 2.1. Minimal record declarations

```java
record Point(double x, double y) {}
record Circle(Point center, double radius) {}
record Rectangle(Point center, double width, double height) {}
```

Each record declares **record components** inside parentheses after the type name. The compiler generates standard members for the record, including:

- Corresponding fields with `private final` semantics.
- A **canonical constructor** matching the order and types of the components (unless a matching constructor is explicitly declared).
- **Accessors** with the same name as each component: `point.x()`, `circle.radius()`, `rectangle.width()`. Records do not generate JavaBean `getWidth()` methods.
- Implementations of `equals(Object)` and `hashCode()` based on the components.
- `toString()` displaying the record type along with its component values.

Example inside a method:

```java
var a = new Point(1.0, 2.0);
var b = new Point(1.0, 2.0);

System.out.println(a.x());       // 1.0
System.out.println(a.equals(b));  // true
System.out.println(a);            // Point[x=1.0, y=2.0]
```

This snippet uses simple record syntax and does not require Java 21; however, the comprehensive example below uses Java 21 record patterns and pattern switch.

### 2.2. Record does not mean "everything is deeply immutable"

Records do not allow reassigning component fields from outside after creation:

```java
Point point = new Point(1, 2);
// point.x = 9;    // COMPILE ERROR: x is private final.
// point.x(9);     // ERROR: no setter x(double).
```

However, this is **shallow immutability**: a record can hold a reference to a mutable object. If you write `record Image(byte[] pixels) {}`, a caller can still modify elements inside the array, even though the `pixels` reference is final. This can also affect `equals`/`hashCode`, because arrays are compared by reference rather than element-by-element.

In this lesson, `Point` holds two immutable `double` values; `Circle`/`Rectangle` hold a `Point` record and `double` values. Therefore, this specific model has no nested mutable content. If `Point` were replaced by a mutable class, you would have to consider **defensive copying**, an immutable type, or stricter constraints.

### 2.3. Records fit data, not every class

Records are **implicitly final**: you cannot declare `class ColoredCircle extends Circle`. Nor can a record extend an arbitrary application class; records always extend `java.lang.Record`. However, a record **can implement interfaces** and declare methods, constructors, and static members according to the language rules.

Thus, we can use `Circle` and `Rectangle` as variants of `Shape`. If the domain needs multi-level behavioral inheritance or identity rather than value semantics, a regular class may be a better fit.

## 3. Designing invariants before writing computations

Declaring a record alone is not enough to protect geometry invariants. By default, Java allows creating:

```java
// For records WITHOUT validation yet:
new Circle(null, -10.0);
new Rectangle(new Point(0, 0), Double.NaN, 2.0);
new Rectangle(new Point(0, 0), Double.POSITIVE_INFINITY, 1.0);
```

These values make area, distance, or containment checks hard to interpret. We need a **compact canonical constructor** to reject them.

### 3.1. Compact constructor for a record

```java
record Circle(Point center, double radius) {
    Circle {
        java.util.Objects.requireNonNull(center, "center");
        if (!Double.isFinite(radius) || radius <= 0.0) {
            throw new IllegalArgumentException(
                    "radius must be finite and > 0");
        }
    }
}
```

The `Circle { ... }` syntax is a **compact constructor**, which does not redeclare the parameter list. Inside the constructor, `center` and `radius` refer to the canonical parameters. The compiler assigns the validated values to the record's fields.

Similarly, `Rectangle` should validate **both width and height**. `Point` needs to check that coordinates are finite, not positive (negative coordinates are valid).

**Rules worth remembering:**

- `Double.isFinite(x)` rejects `NaN` and both infinities.
- `x > 0.0` requires **positive** dimensions; `0.0` and `-0.0` are invalid.
- `Objects.requireNonNull(center, "center")` throws a `NullPointerException` with a clear reason when the center is null.
- A record constructor can throw exceptions; "record" **does not validate invariants by default** for you.
- Constructor validation ensures every object of this type is valid; however, subsequent calculations can still suffer from **floating-point overflow** if dimensions are extremely large.

Do not mix shape validation with external input validation: if you need to accept potentially invalid input, parse and return business errors before constructing the record, rather than creating a record with invalid state and fixing it later.

### 3.2. Designing error messages

Messages such as `radius must be finite and > 0` or `center` help developers locate the exact field in tests and logs. In a public API, constructor errors should be translated into structured responses at the boundary layer if the domain requires it, while keeping the invariant in the model to prevent invalid objects from entering the computation pipeline.

## 4. Sealed Shape: modeling two valid variants

Declaration:

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(Point center, double radius) implements Shape {}
record Rectangle(Point center, double width, double height)
        implements Shape {}
```

Here, `Circle` and `Rectangle` are **final** records, making them valid implementors of `sealed interface Shape`. `sealed` has been final since Java 17 (JEP 409); Java 21 is not required just to declare the hierarchy.

The strength when combined with Java 21:

```java
// Part of a method receiving Shape shape:
return switch (shape) {
    case Circle(var center, double radius) ->
            Math.PI * radius * radius;
    case Rectangle(var center, double width, double height) ->
            width * height;
    case null ->
            throw new IllegalArgumentException("shape required");
};
```

This is a **switch expression using record patterns**. The compiler knows the two permitted variants of `Shape` and checks **exhaustiveness**. There is no need for a `default` branch to "catch everything" once the closed `Shape` set is covered.

When adding a new variant such as `Triangle` to `permits`, switches that do not yet handle `Triangle` become **non-exhaustive** upon recompilation; the compiler will require updating them. This is a key advantage when the type domain is owned by the same module.

If the domain is open to plugins creating new shapes from external modules, a `sealed interface` can be an **unwanted restriction**. In that case, consider an open interface and a different dispatch strategy. Choose `sealed` because the domain contract is closed, not merely to reduce the number of branches.

## 5. Complete Java 21 program: declarations, computations, and pattern matching

The following program includes **the geometry model, validation, area, perimeter, contains, scale, SQUARE classification**, and invalid-input test cases. It uses only Java SE, **with no dependencies and no `--enable-preview`**.

Save as **`GeometryRecordsDemo.java`**:

```java
public class GeometryRecordsDemo {
    sealed interface Shape permits Circle, Rectangle {}

    record Point(double x, double y) {
        Point {
            checkFinite(x, "x");
            checkFinite(y, "y");
        }
    }

    record Circle(Point center, double radius) implements Shape {
        Circle {
            java.util.Objects.requireNonNull(center, "center");
            checkPositiveFinite(radius, "radius");
        }
    }

    record Rectangle(Point center, double width, double height)
            implements Shape {
        Rectangle {
            java.util.Objects.requireNonNull(center, "center");
            checkPositiveFinite(width, "width");
            checkPositiveFinite(height, "height");
        }
    }

    static void checkFinite(double value, String name) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException(name + " must be finite");
        }
    }

    static void checkPositiveFinite(double value, String name) {
        if (!Double.isFinite(value) || value <= 0.0) {
            throw new IllegalArgumentException(
                    name + " must be finite and > 0");
        }
    }

    static double finiteMeasure(double value) {
        if (!Double.isFinite(value)) {
            throw new ArithmeticException(
                    "geometry measure overflow");
        }
        return value;
    }

    static double area(Shape shape) {
        return finiteMeasure(switch (shape) {
            case Circle(Point center, double radius) ->
                    Math.PI * radius * radius;
            case Rectangle(Point center, double width, double height) ->
                    width * height;
            case null ->
                    throw new IllegalArgumentException("shape required");
        });
    }

    static double perimeter(Shape shape) {
        return finiteMeasure(switch (shape) {
            case Circle(Point center, double radius) ->
                    2.0 * Math.PI * radius;
            case Rectangle(Point center, double width, double height) ->
                    2.0 * (width + height);
            case null ->
                    throw new IllegalArgumentException("shape required");
        });
    }

    static String kind(Shape shape) {
        return switch (shape) {
            case Circle(Point center, double radius) -> "CIRCLE";

            case Rectangle(Point center, double width, double height)
                    when width == height -> "SQUARE";

            case Rectangle(Point center, double width, double height) ->
                    "RECTANGLE";

            case null -> "MISSING";
        };
    }

    static boolean contains(Shape shape, Point point) {
        java.util.Objects.requireNonNull(point, "point");

        return switch (shape) {
            case Circle(Point(double cx, double cy), double r) ->
                    Math.hypot(point.x() - cx, point.y() - cy) <= r;

            case Rectangle(
                    Point(double cx, double cy),
                    double w, double h) ->
                    Math.abs(point.x() - cx) <= w / 2.0
                            && Math.abs(point.y() - cy) <= h / 2.0;

            case null ->
                    throw new IllegalArgumentException("shape required");
        };
    }

    static Shape scale(Shape shape, double factor) {
        checkPositiveFinite(factor, "factor");

        return switch (shape) {
            case Circle(Point center, double radius) ->
                    new Circle(center, radius * factor);

            case Rectangle(Point center, double width, double height) ->
                    new Rectangle(
                            center,
                            width * factor,
                            height * factor);

            case null ->
                    throw new IllegalArgumentException("shape required");
        };
    }

    // Used only to illustrate the exception name in the example.
    static String outcome(Runnable operation) {
        try {
            operation.run();
            return "accepted";
        } catch (RuntimeException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        var origin = new Point(0.0, 0.0);

        Circle circle = new Circle(origin, 2.0);
        Rectangle rectangle = new Rectangle(
                new Point(1.0, 1.0), 4.0, 6.0);
        Rectangle square = new Rectangle(origin, 4.0, 4.0);

        System.out.printf(
                java.util.Locale.ROOT,
                "circle area=%.2f perimeter=%.2f%n",
                area(circle), perimeter(circle));

        System.out.printf(
                java.util.Locale.ROOT,
                "rectangle area=%.2f perimeter=%.2f%n",
                area(rectangle), perimeter(rectangle));

        System.out.println(
                "kinds=" + kind(circle) + ","
                        + kind(rectangle) + "," + kind(square));

        System.out.println(
                "circle boundary="
                        + contains(circle, new Point(2, 0))
                        + " outside="
                        + contains(circle, new Point(2.1, 0)));

        System.out.println(
                "rectangle corner="
                        + contains(rectangle, new Point(3, 4))
                        + " outside="
                        + contains(rectangle, new Point(3.01, 4)));

        Rectangle scaled = (Rectangle) scale(rectangle, 2.0);

        System.out.printf(
                java.util.Locale.ROOT,
                "scaled rectangle area=%.2f perimeter=%.2f%n",
                area(scaled), perimeter(scaled));

        System.out.println(
                "original width=" + rectangle.width()
                        + " scaled width=" + scaled.width());

        System.out.println(
                "records equal="
                        + circle.equals(
                                new Circle(new Point(0, 0), 2.0)));

        System.out.println(
                "invalid radius="
                        + outcome(() -> new Circle(origin, 0.0)));

        System.out.println(
                "invalid center="
                        + outcome(() -> new Circle(null, 2.0)));

        System.out.println(
                "invalid NaN="
                        + outcome(() ->
                                new Rectangle(origin, Double.NaN, 2.0)));

        System.out.println("null shape kind=" + kind(null));
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 GeometryRecordsDemo.java
java GeometryRecordsDemo
```

**Exact stdout:**

```text
circle area=12.57 perimeter=12.57
rectangle area=24.00 perimeter=20.00
kinds=CIRCLE,RECTANGLE,SQUARE
circle boundary=true outside=false
rectangle corner=true outside=false
scaled rectangle area=96.00 perimeter=40.00
original width=4.0 scaled width=8.0
records equal=true
invalid radius=IllegalArgumentException
invalid center=NullPointerException
invalid NaN=IllegalArgumentException
null shape kind=MISSING
```

This is a standalone program, verified on JDK 24 using Java 21-compatible syntax. `Locale.ROOT` is used in `printf` so the decimal separator is consistently a dot. The program only prints **two decimal places**; it does not claim that the underlying `double` values are rounded and stored that way.

**Summary of what is verified:** 2 `Shape` types, nested record patterns, `when` guard to recognize squares, geometric calculations, boundary inclusion, `scale` creating a copy, value-based equality, and validation for invalid objects.

## 6. Geometry mechanics behind the records

### 6.1. Area and perimeter formulas

For `Circle(center, radius)`:

\[
A_{\text{circle}} = \pi r^2,\qquad
P_{\text{circle}} = 2\pi r
\]

For `Rectangle(center, width, height)`:

\[
A_{\text{rectangle}} = w h,\qquad
P_{\text{rectangle}} = 2(w+h)
\]

The `center` **does not participate** in the area or perimeter of a circle or axis-aligned rectangle; it only determines position. Therefore, `area` and `perimeter` can deconstruct the whole record without using the `center` variable, or use `var` to make clear that this data is not needed for the calculation.

**Test cases:**

- Circle with `r=2` → area `4π ≈ 12.57`, perimeter `4π ≈ 12.57`.
- Rectangle with `w=4`, `h=6` → area `24`, perimeter `20`.
- Scale rectangle by factor `2` → `w=8`, `h=12`; area `96`, perimeter `40`.

### 6.2. Checking whether a point belongs to a Circle

A point `Q(x,y)` belongs to the **circular disk** with center `C(cx,cy)` and radius `r` if:

\[
\sqrt{(x-c_x)^2+(y-c_y)^2}\le r
\]

In Java:

```java
// Switch case body:
case Circle(Point(double cx, double cy), double r) ->
        Math.hypot(point.x() - cx, point.y() - cy) <= r;
```

`Math.hypot(a,b)` is designed to compute the square root of the sum of squares with better numerical stability than writing `Math.sqrt(a*a+b*b)` directly, especially for numbers with extreme magnitudes. However, **subtracting coordinates before calling `hypot`** can still overflow when two finite coordinates are very far apart; therefore, a system requiring very high precision must consider its numeric model and coordinate domain limits.

In the example, `new Point(2,0)` lies right on the boundary of a `Circle` centered at 0 with radius 2 and returns `true`; `new Point(2.1,0)` lies outside and returns `false`.

### 6.3. Checking whether a point belongs to an axis-aligned Rectangle

`Rectangle` is represented by its center, so a point lies inside the region (including edges) when:

\[
|x-c_x|\le \frac{w}{2}
\quad\land\quad
|y-c_y|\le \frac{h}{2}
\]

In Java:

```java
case Rectangle(Point(double cx, double cy), double w, double h) ->
        Math.abs(point.x() - cx) <= w / 2.0
                && Math.abs(point.y() - cy) <= h / 2.0;
```

For a `Rectangle` centered at `(1,1)` with width `4` and height `6`:

- X range is from `-1` to `3`.
- Y range is from `-2` to `4`.
- Point `(3,4)` is at the top-right corner and **is accepted** due to `<=`.
- Point `(3.01,4)` is outside along the X axis, so it is rejected.

If the domain defines a rectangle by its **top-left corner** in a screen coordinate system (Y axis pointing downward), the formula and field names must be redesigned to match. Do not mix the two conventions without coordinate conversion.

### 6.4. Scale creates a new shape without mutating the existing object

With factor `k > 0`:

- Circle: `r' = k*r`.
- Rectangle: `w' = k*w`, `h' = k*h`.
- The `center` is preserved in this scaling model.

`scale` uses `switch` to return a **new record**. There are no setters to modify `radius`, `width`, or `height` of the old record.

The example output contains the line:

```text
original width=4.0 scaled width=8.0
```

showing that the original `Rectangle` retains width `4` while the scaled copy has width `8`.

**Note:** if you need to scale around the **coordinate origin** instead of around **the shape's own center**, the center must also be scaled/moved accordingly. These are two different behaviors; the method name and contract must specify which point scaling is performed around.

## 7. From record data to Java 21 record patterns

### 7.1. Type pattern only extracts the object

With `switch` on `Shape`:

```java
return switch (shape) {
    case Circle circle ->
            Math.PI * circle.radius() * circle.radius();
    case Rectangle rectangle ->
            rectangle.width() * rectangle.height();
    case null -> 0.0; // Illustrative policy only.
};
```

These are **type patterns**: `case Circle circle` only binds the object and uses accessors. This snippet is **illustrative** inside a method with a `shape` variable of type `Shape`; returning `0.0` for a null selector is a hypothetical choice, **not** the policy of the full program in section 5 (which rejects `area(null)`).

### 7.2. Record pattern extracts components directly

```java
return switch (shape) {
    case Circle(Point center, double radius) ->
            Math.PI * radius * radius;
    case Rectangle(Point center, double width, double height) ->
            width * height;
    case null -> throw new IllegalArgumentException("missing shape");
};
```

Components are deconstructed right at the `case` label. Readers immediately see **a `Circle` has center + radius**, and **a `Rectangle` has center + width + height**. This is especially useful in a case study with multiple simple operations over the same set of records.

### 7.3. Nested record pattern extracts center coordinates

```java
case Circle(Point(double cx, double cy), double radius) ->
        Math.hypot(point.x() - cx, point.y() - cy) <= radius;
```

The `Point(double cx,double cy)` pattern is nested inside `Circle(...)`, so Java avoids manual extraction:

```java
Circle circle = (Circle) shape;
double cx = circle.center().x();
double cy = circle.center().y();
double radius = circle.radius();
```

When using record patterns, **component order must match** the record declaration. If `Rectangle` has order `(Point center, double width, double height)`, do not swap positions by intuition without updating every pattern.

### 7.4. Null selector vs. null record component

**Two distinct cases:**

- `shape == null`: `case null` at the `switch` level can catch a null selector; without an appropriate branch, it throws `NullPointerException`.
- `new Circle(null, 2)`: in this lesson, this **cannot be constructed successfully** because of `requireNonNull` in the constructor. Therefore, nested record patterns are allowed to assume `center` is non-null for valid `Circle` objects.

If you **omit validation** and manage to create a `Circle` with a null center, the nested record pattern `Circle(Point(...),r)` fails to match the `Point(...)` part. A `switch` considered exhaustive by the compiler in certain nested-pattern scenarios that finds no matching branch at runtime can throw `MatchException`. Therefore, **record invariants and case fallback strategies must be designed together**.

## 8. The `when` guard: recognizing a Square from a Rectangle

In this model, a **square** is a `Rectangle` with `width == height`. There is no mandatory need to create a separate `Square` record if `Square` has no independent behavior or validation.

```java
static String kind(Shape shape) {
    return switch (shape) {
        case Circle(Point center, double radius) -> "CIRCLE";

        case Rectangle(Point center, double width, double height)
                when width == height -> "SQUARE";

        case Rectangle(Point center, double width, double height) ->
                "RECTANGLE";

        case null -> "MISSING";
    };
}
```

**Key points during code review:**

1. The `Rectangle ... when width == height` branch must appear **before** the unguarded `Rectangle` branch, because the unguarded branch covers every valid `Rectangle`.
2. The `when` guard only runs after the `Rectangle` pattern matches and `width`/`height` are bound.
3. If the two dimensions are entered directly and the contract defines "exact equality", `==` is an intentional choice.
4. If `width`/`height` are computed from prior floating-point operations, mathematically "equal" values may differ in bits due to rounding. In that case, define a **tolerance** or switch to an appropriate measurement type/unit; **do not blindly replace `==` with a fixed epsilon** across all scales.
5. `Circle` is also a `Shape` but not a `Rectangle`; never treat shapes with equal area as having the same shape kind.

The `when` syntax in `switch` patterns has been final since Java 21. It differs from `if (shape instanceof Rectangle r && r.width() == r.height())`, where `&&` is a Boolean operator and pattern variables use flow scoping.

## 9. Equals, hashCode, and toString in the geometry case study

Records provide **value semantics** based on their components:

```java
var c1 = new Circle(new Point(0, 0), 2);
var c2 = new Circle(new Point(0, 0), 2);

System.out.println(c1.equals(c2)); // true
System.out.println(c1 == c2);      // false (two different objects)
System.out.println(c1.radius());   // 2.0
```

Two `Circle` instances are compared by **center and radius**, not radius alone. Two `Rectangle` instances are equal under record value semantics only if **center, width, and height** are equal according to component comparison rules. This fits when objects represent **geometric state**.

However, "record equality" is **not the same as** "geometric equality" in every domain:

- A `Rectangle` with `width=4,height=6` rotated 90 degrees (not modeled here) can yield the same point set as a `Rectangle` with `width=6,height=4` after an appropriate transformation, yet the two records have different components.
- Two `Circle` instances with tiny coordinate differences are usually not `equals` even if a geometric algorithm treats them as equivalent within a tolerance.
- `double` has special semantics for `NaN`, `Infinity`, and signed zero; this lesson blocks `NaN`/`Infinity` in constructors, but `0.0` and `-0.0` coordinates can still differ under value equality. Do not use `equals` as a substitute for an "approximately equal geometrically" algorithm.

**Design tip:** keep the record-generated `equals`/`hashCode` for **exact data values**; when approximate comparison is needed, write a `geometricallyEquivalent(a,b,tolerance)` method with its own contract, rather than making `equals` ignore error, which complicates hash-collection contracts.

Records also generate a debug-friendly `toString()`:

```text
Circle[center=Point[x=0.0, y=0.0], radius=2.0]
```

This is the standard representation generated by the record class in the example. However, **do not use `toString()` as a stable serialization/API format**: if component names or schemas change, the string changes too.

## 10. Why validating `double` is still not enough

There are three levels of numerical safety to distinguish:

### 10.1. Rejecting invalid numbers at the components

Constructors block:

- `0` or negative radius.
- `0` or negative width/height.
- `NaN` and `Infinity` for position and dimensions.
- Null center.

That protects **input data**.

### 10.2. Avoiding overflow during computation

A finite `double` can still be too large to square. For example, `radius = 1e200` is finite, but `π * radius * radius` overflows to `Infinity`. Therefore, the program uses:

```java
static double finiteMeasure(double value) {
    if (!Double.isFinite(value)) {
        throw new ArithmeticException("geometry measure overflow");
    }
    return value;
}
```

This function rejects **non-finite results** in `area`/`perimeter`. It does not detect **underflow** to 0 for tiny dimensions, nor every rounding error. If the domain requires high precision, you must define the allowed value range, units, and precision before implementation.

### 10.3. Choosing a domain-appropriate epsilon when comparing shapes

`width == height` makes sense for classifying exact `double` bit/value data in the demo. When data comes from continuous transformations, such as division results, an "equivalent within measurement error" rule needs a policy:

\[
|w-h|\le \varepsilon_{\text{abs}}
\]

or a combination of absolute and relative tolerances when scales vary widely. There is no universal `epsilon=1e-9` for every unit (mm, pixel, km) and data range. CAD/surveying, finance, or graphics problems each have different requirements.

**Do not reflexively use `BigDecimal` for all geometry.** Formulas involving π or square roots and geometric operations require their own precision/rounding strategies. `double` suits many standard 2D problems when invariants and tolerances are clearly designed.

## 11. Extending the design without breaking the contract

### 11.1. If only dimensions are needed, center can be omitted

A problem that only computes area/perimeter and does not care about position can simplify to:

```java
record Circle(double radius) {}
record Rectangle(double width, double height) {}
```

This is **a different model** and still needs constructor validation to reject invalid numbers. Do not add `Point center` if no operation uses position. In the full program, `center` exists because we check **point containment**.

### 11.2. If Rectangle rotation is needed

An axis-aligned rectangle cannot describe an arbitrarily rotated rectangle. Another option is:

```java
// Schema illustration only, no validation/operations yet.
record RotatedRectangle(
        Point center,
        double width,
        double height,
        double angleRadians) {}
```

You must define the rotation angle, coordinate convention, angle normalization, and coordinate-transform formulas before using this record. Do not apply the axis-aligned `Rectangle` `contains` algorithm directly to a rotated rectangle, as it will be wrong.

### 11.3. If Square needs to be an independent type

If `Square` has its own business rules (e.g., pricing, separate constraints, separate API), you can consider:

```java
// Example of a different model; sealed permits must be updated accordingly.
record Square(Point center, double side) implements Shape {}
```

**This snippet does NOT compile if pasted verbatim into the section 5 program** because sealed `Shape` currently permits only `Circle` and `Rectangle`. To add `Square`, you must update `permits`, `area`/`perimeter`/`kind`/`contains`/`scale`, and tests. That is the **desired** behavior of exhaustiveness checking: the compiler reminds you to handle a new domain variant.

### 11.4. If the model is a public API

In the demo program, `Shape`, `Point`, `Circle`, and `Rectangle` are nested package-private types so everything runs from a single file. In a real library, you would put each record in its own file with an explicit package, Javadoc comments, and `public` visibility if part of the public API. Consider:

- Binary and source compatibility of the **record component list** (changing order/types can break constructor/pattern callers).
- Serialization rules (if needed), schema versioning, JSON mappers, and module boundaries.
- Measurement units declared in the API; if needed, use a `Length` value type instead of raw `double`.
- Avoid putting heavy computation logic inside record accessors, because record patterns may invoke accessors during deconstruction.

## 12. Testing edge cases, not just formulas

A solid test suite should cover at least:

| Scenario | Expected result per lesson contract |
| --- | --- |
| Circle `r=2` | `area≈12.566` and `perimeter≈12.566` |
| Rectangle `w=4,h=6` | `area=24`, `perimeter=20` |
| Rectangle `w=h=4` | `kind(...) = "SQUARE"` |
| Circle point on boundary `(2,0)` | `contains == true` |
| Circle point outside `(2.1,0)` | `contains == false` |
| Rectangle point at corner `(3,4)` | `contains == true` |
| Rectangle point outside `(3.01,4)` | `contains == false` |
| Scale factor `2` | New record created, original unchanged; area ×4, perimeter ×2 |
| Radius `0` or negative | `IllegalArgumentException` |
| Width/height `NaN`/`Infinity` | `IllegalArgumentException` |
| Null center | `NullPointerException` right in constructor |
| Null selector in `kind` | `"MISSING"` |
| Null selector in `area`/`perimeter` | `IllegalArgumentException` |
| Null point in `contains` | `NullPointerException` |
| Finite dimensions whose product is too large | `ArithmeticException` in `area`/`perimeter` if result is non-finite |

**Floating-point note:** When testing Circle area, assert with an appropriate tolerance instead of `assertEquals(12.57, area(circle))`, because the actual value is approximately `12.5663706...` and the printed string was formatted to two decimal places.

### 12.1. Property-based tests for the record model

Some useful properties:

- For every valid `Circle`: `area > 0`, `perimeter > 0` provided the result is finite and does not underflow.
- For every valid `Rectangle`: swapping width/height **does not change area/perimeter**, even though record `equals` may differ.
- For a valid factor `k > 0` without overflow/underflow: `area(scale(s,k)) ≈ k² * area(s)`, `perimeter(scale(s,k)) ≈ k * perimeter(s)`.
- With the same center, increasing a `Circle`'s radius cannot cause a point **already inside the smaller Circle** to fall outside the larger Circle, given appropriate numerical precision.
- For an axis-aligned `Rectangle`, the point at `center` always lies inside a valid shape.

When writing property tests, generate boundary values (0, very small positive numbers, very large numbers, `NaN`, `Infinity`, values just past the threshold) and separate the **valid** input domain from the constructor-rejection test domain. Numerical property tests need clear tolerance/overflow rules to avoid false positives.

### 12.2. Do not swallow exceptions in production

The `outcome` helper in the sample program catches `RuntimeException` solely to **print the exception name in the demo**. In a real application, never swallow all errors and return a generic string. When handling external requests, map validation errors to proper API responses and preserve stack traces/logs where appropriate.

## 13. Common mistakes when representing shapes with records

1. **Not validating radius/width/height**, leading to shapes with negative/`NaN`/`Infinity` area.
2. **Assuming records are automatically deeply immutable**, while components can reference mutable arrays/lists/objects.
3. **Mixing two Rectangle representations:** `(x,y)` is the center in code but is read as the top-left corner.
4. **Not specifying whether rectangles can rotate**, then applying the axis-aligned `contains` formula to rotated rectangles.
5. **Using `double ==` for all approximate comparisons**, especially on computed or measured data.
6. **Confusing record component accessors with JavaBean getters**: `width()`, not `getWidth()`.
7. **Placing the unguarded Rectangle branch before the Square `when` branch**, causing a dominated pattern error.
8. **Unconditionally adding `default` to a sealed switch**, losing compiler warnings when a new `Shape` variant is added.
9. **Forgetting null at the selector vs. record component**, causing unexpected `NullPointerException` or `MatchException`.
10. **Scaling by trying to mutate final fields**, instead of creating a new record.
11. **Squaring with `double` multiplication without checking overflow**, then passing `Infinity` to other parts of the system.
12. **Comparing `Circle` instances by radius alone**, ignoring `center` even though the model defines both as value components.
13. **Using record `toString()` as a public JSON/schema format**, causing downstream breakage when record components change.
14. **Treating `sealed` as always better than an open interface**, even when plugins need to implement `Shape` outside the module.
15. **Trying to subclass `Rectangle` record into `Square`**, which is impossible because records are final.

## 14. Code review checklist

- [ ] Are `Circle`, `Rectangle`, position/center definition, axes, and measurement units clearly documented?
- [ ] Are the invariants of `Point`, `Circle`, and `Rectangle` protected by compact constructors?
- [ ] Are reference types inside records genuinely immutable, or is there a defensive-copy policy?
- [ ] Should `Shape` be a sealed hierarchy, or does the domain require external extensions?
- [ ] Do `area`/`perimeter`/`contains` match the model's formulas, including boundaries?
- [ ] Do Java 21 record patterns match the exact component order and types?
- [ ] Does the Square `when` branch precede the Rectangle fallback, and is `width==height` tested?
- [ ] Is the policy for null selectors and null components explicit?
- [ ] Are value equality, geometric equivalence, and tolerance clearly distinguished?
- [ ] Are overflow and precision checked when using `double` in the real domain?
- [ ] Does `scale` clarify whether the center stays fixed or scales around the origin?
- [ ] Are constructor rejections, floating-point values, extremes, fallback cases, and exhaustiveness tested?

**Conclusion:** `record` is well suited for representing shapes with **fixed data and value semantics** like `Circle` and `Rectangle`. **Define invariants first**, choose coordinate systems and units clearly, use `sealed Shape` when the shape set is closed, and leverage **Java 21 record patterns and pattern switch** to process data concisely, enforce exhaustiveness, and avoid manual casts. It is the geometric rules and numerical safety — not just record syntax — that make this model reliable.

### References

- OpenJDK JEP 395 — Records (final in Java 16): https://openjdk.org/jeps/395
- OpenJDK JEP 409 — Sealed Classes (final in Java 17): https://openjdk.org/jeps/409
- OpenJDK JEP 440 — Record Patterns (final in Java 21): https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch (final in Java 21): https://openjdk.org/jeps/441
- Oracle Java 21 — Record Classes: https://docs.oracle.com/en/java/javase/21/language/records.html
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — Record Classes `8.10: https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10
