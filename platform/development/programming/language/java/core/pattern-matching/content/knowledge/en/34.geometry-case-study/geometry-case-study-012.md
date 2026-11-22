# Design Choice Summary — Geometry Case Study with Java Pattern Matching

When modeling **2D geometry** in Java, the same problem—“computing the area and perimeter of multiple shape types”—can be solved in several ways: **object-oriented polymorphism** (each shape provides its own behavior), **`sealed interface` + `record` + pattern matching `switch`** (data separated from operations), or an `instanceof` chain for small cases. There is no single approach that is always best.

This lesson belongs to **Java Core Pattern Matching → Geometry Case Study**, serving as the **design choice summary**. We will use the same domain of **circles, rectangles, and right triangles** to evaluate clarity, type safety, extensibility, `switch` exhaustiveness, data validation rules, and maintenance needs. At the end of the lesson, there are **two standalone, verified Java programs**, a decision table, and practice exercises.

**Version milestones:** `record` has been stable since Java 16 (JEP 395), `sealed` since Java 17 (JEP 409), and **record patterns** and **pattern matching for `switch`** were finalized in Java 21 (JEP 440, JEP 441). The Java 21+ style comparison program **does not require `--enable-preview`**.

## 1. Start from Requirements, Not from Syntax

Suppose a geometry module needs to:

- Describe three 2D shape types: **`Circle`** by radius `r`; **`Rectangle`** by width `w` and height `h`; **`RightTriangle`** by two legs `a` and `b`.
- Compute `area` and `perimeter`, returning `double`.
- Provide a brief classification for display: large circle, square/landscape/portrait rectangle, right triangle.
- Prevent creating shapes with negative, zero, `NaN`, or `Infinity` dimensions.
- Be able to add a **new operation** in the future, or add a **new shape type**.
- Have an explicit rule when the input object is `null`.

For a simple system, the formulas are:

| Shape Type | Data to Store | Area | Perimeter |
| --- | --- | --- | --- |
| Circle | Radius `r > 0` | \(\pi r^2\) | \(2\pi r\) |
| Rectangle | Width `w > 0`, height `h > 0` | \(w h\) | \(2(w+h)\) |
| Right triangle | Two legs `a > 0`, `b > 0` | \(ab/2\) | \(a+b+\sqrt{a^2+b^2}\) |

In Java, you should compute the hypotenuse using **`Math.hypot(a, b)`** instead of writing `Math.sqrt(a*a + b*b)` manually, because `hypot` is designed to compute this length with more reliable floating-point handling for very large or very small values.

**Model limitations:** `RightTriangle` here describes a **right triangle by the lengths of its two legs**, not an arbitrary triangle by three coordinate vertices. `Rectangle` is an axis-aligned rectangle without storing a rotation angle; to support positioned shapes, rotation, or arbitrary polygons, the domain model must be extended accordingly.

A design question more important than whether you can write `case Circle(var r)` is: **does the system evolve toward adding new shapes or adding operations on existing shapes?**

## 2. Two Main Design Approaches

### A. Object-Oriented Polymorphism: Behavior Lives on Each Shape

We declare a `Shape` interface with common methods:

~~~java
// Java snippet, not a standalone program.
interface Shape {
    double area();
    double perimeter();
}
~~~

Each shape then implements its corresponding formulas. The client simply calls `shape.area()`, without knowing whether the shape is a `Circle` or a `Rectangle`. Java selects the implementation via **dynamic dispatch**.

Advantages:

- Each class/record owns the calculation rules belonging to its shape type.
- Clients depend only on a common contract and do not need a `switch` when calling `area()`.
- With an **open interface** and relatively stable common methods, adding a new shape type can be done by implementing the interface without modifying existing `shape.area()` call sites.
- Familiar to traditional object-oriented programming; suitable when shape data and behavior belong together.

Trade-offs:

- Adding a **new required operation** to the interface may require updating every implementation; API binary/source compatibility must be considered.
- If an operation belongs to the reporting, UI, file export, testing, or specialized analysis layer, placing it on the `Shape` interface can bloat the API surface and mix responsibilities.
- Polymorphism does not automatically verify that every shape uses a mathematically correct formula; unit tests are still required.

### B. `sealed` + `record` + Exhaustive `switch`: Data and Operations Separated

We define the permitted set of geometric variants:

~~~java
// Java 21+ snippet; can be placed in an appropriate scope/module.
sealed interface Shape permits Circle, Rectangle, RightTriangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record RightTriangle(double legA, double legB) implements Shape {}
~~~

And an `area` operation outside the records:

~~~java
// Java 21+ snippet; shape has type Shape, non-null.
return switch (shape) {
    case Circle(var r) -> Math.PI * r * r;
    case Rectangle(var w, var h) -> w * h;
    case RightTriangle(var a, var b) -> a * b / 2.0;
};
~~~

Advantages:

- `record` focuses on representing **geometric data** and invariants where needed.
- `switch expression` centralizes the rules of **one operation** in a single place: reviewing the entire set of area formulas is very fast.
- You can add an operation such as computing perimeter, shaded area, generating descriptions, or exporting information **without adding methods to each data type**.
- With a **closed sealed hierarchy** and cases covering all variants, the compiler checks **exhaustiveness**; when a new permitted type is added and recompiled, any `switch` missing a case will be flagged.

Trade-offs:

- When adding a **new shape type**, you must update the `permits` list and **every relevant exhaustive `switch` operation**. This is both a change cost and a benefit if you want the compiler to enforce reviewing every operation.
- `sealed` restricts direct implementations according to language/module rules, so it is not suitable as-is if external plugins need to add arbitrary subtypes.
- If each `switch` operation becomes long or full of side effects, you may need to extract it into a strategy/service or another behavior-oriented design.

**Do not default** to making every domain object a `record` or forcing every handler to use `switch`. Choose based on the stability of the shape set and the direction of business evolution.

## 3. Program 1: Geometry Using Polymorphism

A small, standalone example focused on **dynamic dispatch**. It includes only two shape types to avoid repetitive code while explaining the principle.

Create the file **`PolymorphicGeometryDemo.java`**:

~~~java
public class PolymorphicGeometryDemo {
    interface Shape {
        double area();
        double perimeter();
    }

    record Circle(double radius) implements Shape {
        public double area() {
            return Math.PI * radius * radius;
        }
        public double perimeter() {
            return 2 * Math.PI * radius;
        }
    }

    record Rectangle(double width, double height) implements Shape {
        public double area() {
            return width * height;
        }
        public double perimeter() {
            return 2 * (width + height);
        }
    }

    public static void main(String[] args) {
        Shape[] shapes = {new Circle(2), new Rectangle(3, 4)};
        for (Shape shape : shapes) {
            System.out.printf(java.util.Locale.ROOT,
                    "area=%.2f perimeter=%.2f%n",
                    shape.area(), shape.perimeter());
        }
    }
}
~~~

Run with JDK 16+ (for example, using JDK 21+ with target 21):

~~~bash
javac --release 21 -encoding UTF-8 PolymorphicGeometryDemo.java
java PolymorphicGeometryDemo
~~~

Stdout:

~~~text
area=12.57 perimeter=12.57
area=12.00 perimeter=14.00
~~~

**Explanation:**

1. `Shape` is an interface containing the common operations. It is **not `sealed`**, so the interface itself does not lock down the list of implementations.
2. Both records provide the corresponding `public` methods. On the interface, `area()` and `perimeter()` are public methods; implementations must preserve the appropriate access level.
3. The client simply iterates over `Shape[]` and calls the methods, without subtype checks or casts.
4. `Locale.ROOT` keeps the decimal separator in `printf` consistent across environments, preventing stdout from depending on the OS locale.

**Intentional simplification:** This polymorphic program **does not validate inputs yet**. When building a real API, you need to add invariants to the records as in the second program, or an equivalent validation layer. Do not compare this version against a version with validation and conclude that one design is “mathematically safer” purely because of syntax.

## 4. Program 2: `sealed record` + Pattern `switch`

The next program uses three shapes and three operations—**`area`**, **`perimeter`**, and **`label`**—to clearly illustrate separating data from functionality. It also places invariants directly in the record's **compact constructor**, so shapes with invalid dimensions are rejected upon construction.

Create the file **`GeometryDesignChoicesDemo.java`**:

~~~java
public class GeometryDesignChoicesDemo {
    sealed interface Shape permits Circle, Rectangle, RightTriangle {}

    record Circle(double radius) implements Shape {
        Circle { positive(radius, "radius"); }
    }

    record Rectangle(double width, double height) implements Shape {
        Rectangle {
            positive(width, "width");
            positive(height, "height");
        }
    }

    record RightTriangle(double legA, double legB) implements Shape {
        RightTriangle {
            positive(legA, "legA");
            positive(legB, "legB");
        }
    }

    static void positive(double value, String name) {
        if (!Double.isFinite(value) || value <= 0.0) {
            throw new IllegalArgumentException(
                    name + " must be finite and > 0");
        }
    }

    static double area(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(var r) -> Math.PI * r * r;
            case Rectangle(var w, var h) -> w * h;
            case RightTriangle(var a, var b) -> a * b / 2.0;
        };
    }

    static double perimeter(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(var r) -> 2.0 * Math.PI * r;
            case Rectangle(var w, var h) -> 2.0 * (w + h);
            case RightTriangle(var a, var b) ->
                    a + b + Math.hypot(a, b);
        };
    }

    static String label(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(var r) when r >= 3.0 -> "large circle";
            case Circle(var r) -> "circle";

            case Rectangle(var w, var h) when w == h ->
                    "square rectangle";
            case Rectangle(var w, var h) when w > h ->
                    "landscape rectangle";
            case Rectangle(var w, var h) -> "portrait rectangle";

            case RightTriangle(var a, var b) -> "right triangle";
        };
    }

    public static void main(String[] args) {
        Shape[] shapes = {
            new Circle(2),
            new Circle(3),
            new Rectangle(3, 4),
            new Rectangle(8, 3),
            new Rectangle(4, 4),
            new RightTriangle(3, 4)
        };

        for (Shape shape : shapes) {
            System.out.printf(java.util.Locale.ROOT,
                    "%s | area=%.2f | perimeter=%.2f%n",
                    label(shape), area(shape), perimeter(shape));
        }

        try {
            area(null);
        } catch (NullPointerException e) {
            System.out.println("Null rejected");
        }

        try {
            new Circle(Double.NaN);
        } catch (IllegalArgumentException e) {
            System.out.println("Invalid: " + e.getMessage());
        }
    }
}
~~~

Compile and run with JDK 21 or later:

~~~bash
javac --release 21 -encoding UTF-8 GeometryDesignChoicesDemo.java
java GeometryDesignChoicesDemo
~~~

Stdout:

~~~text
circle | area=12.57 | perimeter=12.57
large circle | area=28.27 | perimeter=18.85
portrait rectangle | area=12.00 | perimeter=14.00
landscape rectangle | area=24.00 | perimeter=22.00
square rectangle | area=16.00 | perimeter=16.00
right triangle | area=6.00 | perimeter=12.00
Null rejected
Invalid: radius must be finite and > 0
~~~

### 4.1. Why Does the Compiler Know Every Case Returns `double`?

Each `switch expression` in `area` and `perimeter` is used as the return value of a `double` method. The record patterns deconstruct components with static type `double`. Java checks value-producing capability and type compatibility across all branches. A branch intentionally returning `"unknown"` would be incompatible with a method returning `double`.

### 4.2. Why Is There No `default`?

`Shape` is a sealed interface, and the three records are the permitted types in the model. `area` and `perimeter` handle `Circle`, `Rectangle`, and `RightTriangle`. `label` also handles all variants thanks to an unguarded branch for each type following the specialized guarded branches.

Removing a general branch, such as `case RightTriangle(...)`, makes the `switch expression` no longer **exhaustive**. The compiler helps catch missing cases. A `default` returning `0.0` can hide this design omission when a new shape is added, easily turning a missing formula into an invalid result.

### 4.3. Why Do Branches with `when` Come First?

In `label`, the branch `Circle(var r) when r >= 3.0` comes before the general `Circle(var r)` branch. Similarly, the square rectangle branch comes before the landscape branch, and both come before the unguarded `Rectangle` branch.

If you place `case Circle(var r) -> "circle"` **before** the guarded case with the same pattern, the guarded branch is **dominated**, because the broader branch already covers all `Circle` instances. This is something the compiler can check.

**`when` should contain pure checks.** Here, a dimension comparison is sufficient; you should not query a database or cause side effects just to determine a display label.

### 4.4. Why Must `null` and Dimensions Be Checked in Constructors?

In Java, records by default **do not automatically forbid** `new Circle(-2)` or `new Circle(Double.NaN)`. In the example, the compact constructor calls `positive(...)` to reject non-positive or non-finite values, including `0.0`, `-0.0`, negative numbers, `NaN`, and infinity.

`Objects.requireNonNull(shape, "shape")` clearly defines **the input contract of the operations**. If a caller passes a `null` selector, the method rejects it before entering the `switch`; `null` is not treated as a “fourth shape.” If business logic requires `null` to have a specific meaning, you can choose `case null`, but it must be designed intentionally.

**Floating-point limits:** Even when dimensions are positive finite `double` values, the area or perimeter computed from very large numbers can still overflow to `Infinity`. The input validation above does not prove that every computed result is finite. For sensitive problems, additional range validation and overflow handling are needed according to the contract.

### 4.5. Why Use `Math.hypot` for a Right Triangle?

Given two legs `a` and `b`, the hypotenuse has length \(\sqrt{a^2+b^2}\). `Math.hypot(a, b)` is the dedicated Java API for this calculation, typically avoiding intermediate numerical issues present in `Math.sqrt(a*a+b*b)`. You should not use `Math.pow(a, 2)` in a minimal example when multiplication or `hypot` is clearer.

Result for `a=3`, `b=4`: hypotenuse is 5; area is 6 and perimeter is 12. This is a case that is easy to verify by hand and in tests.

## 5. When Adding a New Shape Type: Who Has to Change?

Suppose the product wants to add an **ellipse** with semi-major and semi-minor axes. In design B, you need to expand the set of permitted subtypes and add a record:

~~~java
// ILLUSTRATION of structural change, not a standalone runnable file.
// Update the permits list according to the current structure:
sealed interface Shape permits Circle, Rectangle, RightTriangle, Ellipse {}

// Add a record in the appropriate module/package.
record Ellipse(double semiMajor, double semiMinor) implements Shape {
    Ellipse {
        positive(semiMajor, "semiMajor");
        positive(semiMinor, "semiMinor");
    }
}
~~~

After that change, existing `switch expression` blocks over `Shape` that only handled the three old types are **no longer exhaustive** upon recompilation. The compiler can require updating `area`, `perimeter`, and `label`. That is **the advantage of controlling model evolution**: you cannot easily forget an operation for a new shape.

However, it is also a **maintenance cost**: every time a variant is added, multiple `switch` blocks scattered across the project may need updating. For an ellipse, the area is simply `Math.PI * semiMajor * semiMinor`, whereas **the perimeter of an ellipse has no simple elementary formula like a circle**. Therefore, the compiler is right to force the designer to decide on the approximation method, precision, and API contract before implementing. Do not “patch” it with `default -> 0.0` just to get a green build.

With design A using an **open interface** with `area()` and `perimeter()`, you can add an `Ellipse` implementation providing those two methods without modifying clients that only call those methods. That is an advantage when **the set of shape types grows frequently while the list of core operations is stable**.

**Do not overlook the “open interface” condition:** If the OOP version also declares a `sealed interface`, adding an implementation still must obey `permits`; polymorphism does not remove the restriction of a sealed hierarchy.

## 6. When Adding a New Operation: Who Has to Change?

Suppose the UI needs a shape classification for display, or an analysis module needs to compute a bounding box. In design B, you can add a new function taking `Shape` and using `switch`:

~~~java
// Java 21+, snippet adding an operation without modifying records.
// shape has type Shape and has already been checked non-null.
static String uiCategory(Shape shape) {
    return switch (shape) {
        case Circle(var r) -> "round";
        case Rectangle(var w, var h) -> "four-sided";
        case RightTriangle(var a, var b) -> "triangle";
    };
}
~~~

To add this feature, **you do not need to change the component declarations or constructors of `Circle`/`Rectangle`/`RightTriangle`**. When many independent operations are managed by different teams (rendering, pricing, reporting, analysis), this can be very useful.

In design A, if `uiCategory()` is a required behavior of **every** `Shape`, adding it to the interface affects all implementations. You can avoid modifying the interface by using an appropriate utility, service, adapter, or visitor—so you should not conclude that “OOP cannot add new operations.” The difference lies in **where changes occur and the exhaustiveness-checking mechanism**.

### Trade-offs Along the Two Axes of Evolution

| Question | Polymorphism with Open Interface | Sealed Records + Pattern `switch` |
| --- | --- | --- |
| Frequently adding new shape types with already-defined operations | Convenient: new shape implements the contract | Requires updating the hierarchy and exhaustive switches |
| Frequently adding new operations on a mostly fixed set of shapes | May require adding interface methods or using external services | Convenient: add a new `switch` function |
| Want the compiler to flag unhandled new subtypes | Open interfaces do not do this by default for external functions | Sealed + exhaustive `switch` shines here |
| Allow third-party plugins to add shapes | Open interface fits better | Direct `sealed` is usually too restrictive |
| Want domain objects to carry their own core behavior | Natural with methods on objects | Must decide whether to keep behavior in services |
| Want simple data, easy to serialize/test | Can use records, though the interface holds behavior | Records represent data clearly; serializers still need polymorphism config |
| Need many external operations, reporting/display | Can use service/visitor; consider design carefully | Cleanly separates each operation from the shape model |
| Runtime cost | Dynamic dispatch can be optimized by the JIT | Pattern checks and switches can also be optimized by the JIT |

This table is a **decision guide**, not benchmark results or immutable rules.

## 7. Where Do `instanceof`, Visitor, and `enum` Fit?

The two main designs are not the only options.

### 7.1. `instanceof` for a Single Small Check

If the code only needs to recognize one subtype:

~~~java
// Java 16+ snippet, shape has an appropriate Shape type.
if (shape instanceof Circle circle) {
    System.out.println(circle.radius());
}
~~~

The `instanceof` type pattern is **clear enough**; there is no need to create a `switch` for a single branch. However, if you have three or four `if/else if` branches handling all shapes and want the compiler to enforce handling every subtype, a `switch expression` over a sealed hierarchy is more beneficial. An `if` chain does not carry the same exhaustiveness requirement as a `switch expression`.

### 7.2. Visitor / Double Dispatch

**Visitor** can decouple operations from shapes in traditional codebases, including before Java 21. It is often useful when there are many operations, double dispatch is needed, or the team already uses visitor consistently. The trade-off is extra interfaces, overloads, and `accept` methods, which can make a three-shape case study boilerplate-heavy.

With Java 21 and a closed set of subtypes, **pattern `switch` is usually more direct than visitor** for simple branching. However, do not replace an already-stable visitor just because the new syntax is shorter; weigh compatibility, client APIs, and testability.

### 7.3. `enum` for a Small Set of States

If you only need to distinguish a few **labels** without per-variant payloads, `enum` + `switch` can be simpler than a sealed hierarchy. However, `Circle(radius)` and `Rectangle(width, height)` have different numbers and meanings of components. Forcing them into an `enum` with optional fields often creates **invalid data states** and weakens type safety.

An API might use `enum ShapeKind` for UI purposes, but that does not replace a geometric data model that needs radius/sides.

## 8. Do Not Store Every Shape in One Record with a `type` Field

The following design looks simple at first glance:

~~~java
// INTENTIONALLY ILLUSTRATING A WEAK DESIGN, not a recommended approach.
record AnyShape(
    String type,
    Double radius,
    Double width,
    Double height,
    Double legA,
    Double legB
) {}
~~~

It allows many nonsensical combinations: `type="CIRCLE"` with `radius==null`; `type="RECTANGLE"` carrying `legA`; or `type` containing an unknown string. The compiler cannot infer which fields are required for each `type`.

**Per-variant records** make the data concrete:

~~~java
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record RightTriangle(double legA, double legB) implements Shape {}
~~~

Using primitive `double` for components avoids `null` for the numeric fields themselves; it does **not** automatically guarantee positive or finite values, so constructor validation remains essential.

If data comes from JSON or an external API, you need **deserialization/validation** before converting into domain shapes; `sealed` does not automatically decode a `"type"` value and does not automatically guard against every malformed payload.

## 9. Geometric Aspects That the Compiler Cannot Decide

### 9.1. How to Represent a Square

In the example, a **square** is a `Rectangle` with `width == height`. This has the advantage of not needing a new subtype. However, if the domain treats a square as a distinct entity with its own invariants and different behavior, you can consider `record Square(double side) implements Shape` and add operations accordingly.

**Choose based on domain meaning**, not just to illustrate an extra case. If you add `Square`, every exhaustive switch will also need review—that is part of the decision to use a sealed hierarchy.

### 9.2. Floating-Point Comparison

`when w == h` in the demo is an **exact** comparison between two `double` values. It is suitable for illustration when inputs are exact values like `4.0` and `4.0`. If lengths come from physical measurements or accumulated calculations, representation error may cause two *nearly equal* values to fail `==`.

To check for “nearly square,” you need a tolerance rule appropriate to the magnitude/units and product contract; you should not blindly use `Math.abs(w-h) < 0.001` for every problem. When tolerance is an important business rule, it can be placed in a pure helper such as `isSquareLike(rectangle)`.

### 9.3. Units of Measurement and Precision

The demo assumes a single unit of length, such as centimeters, with area measured in the corresponding **square** units. If callers can pass both meters and centimeters, `double` carries no unit metadata; you need API conventions or explicit value objects with units.

`double` is suitable for many geometric calculations. If a problem requires exact arithmetic with fractions/integer coordinates or geometric proof constraints, a different numeric model and appropriate algorithms may be needed. `BigDecimal` does not automatically solve formulas involving \(\pi\) or square roots without an approximation policy.

### 9.4. Invalid Shapes and Degenerate Shapes

`Circle(0)`, `RightTriangle(-1, 4)`, and `Rectangle(Double.POSITIVE_INFINITY, 2)` are inputs rejected by the demo's compact constructors. In some mathematical applications, degenerate shapes (zero area) may be valid values. If that requirement exists, do not copy the `value > 0` invariant without checking the contract.

**The compiler checks types; constructors/validation check invariants.** `case Circle(var r)` only confirms that the record has the matching type and extracts its component; it does not prove `r > 0` without a guarantee from the constructor.

## 10. What Happens If a Case Is Omitted When Extending the Model?

With the three types `Circle`, `Rectangle`, and `RightTriangle`, the `switch expression` in `area` must handle all permitted variants. The example below **intentionally omits** the right triangle:

~~~java
// INTENTIONALLY INCORRECT, snippet inside a method returning double;
// shape has type Shape with three permitted subtypes.
return switch (shape) {
    case Circle(var r) -> Math.PI * r * r;
    case Rectangle(var w, var h) -> w * h;
    // Missing RightTriangle.
};
~~~

The Java 21 compiler will report that the switch is **not exhaustive**. This is a useful signal when controlling domain model changes.

Do not “fix” it with:

~~~java
// NOT RECOMMENDED: disguises a missing formula.
default -> 0.0;
~~~

If a new shape is added without a formula yet, returning `0.0` can silently produce wrong results. If you truly want a fallback (for example, an `Object` selector containing unknown data), state clearly that it means “unsupported” and choose an appropriate error/response mechanism rather than a seemingly valid numeric value.

**Compiler limits:** It does not prove that the formula `Math.PI*r*r` is mathematically correct, does not catch mistaking `2*Math.PI*r*r` for area, and does not prove that floating-point values are always finite. Exhaustiveness only tells you that **a branch exists**, not that **the branch is correct**.

## 11. Choosing a Design Across Three Real-World Scenarios

### Scenario A: Core Geometry Library Where Objects Provide Their Own Measurements

A public library wants to let users write `shape.area()` and `shape.perimeter()`. These two operations are part of the **core contract**; applications may create additional implementations.

**Lean toward an open interface + polymorphism** if user extensibility is genuinely needed and the list of common operations is relatively stable. Put validation in constructors/factories or appropriate data classes.

### Scenario B: Internal Engine with Three Fixed Shapes and Many Analysis Steps

An engine processes only `Circle`, `Rectangle`, and `RightTriangle`, but has many calculations: area, perimeter, rendering metadata, classification, reporting, comparison, or transformation.

**Lean toward sealed records + exhaustive switch** if the shape set is truly owned and controlled by one module. Add separate operations without modifying the records; the compiler forces reviewing every handler when a subtype is added.

### Scenario C: API Processing External Data with an Unknown Set of Shapes

A service receives JSON with a type discriminator from multiple providers; new types may appear before the module is updated.

Do not force every unknown payload into a sealed hierarchy and assume the code is always exhaustive. You need a **boundary layer** that decodes and validates, a policy for unknown types/versions, and potentially converts known data into internal domain records. At that boundary, an open model or adapter may be more suitable.

**Practical decisions are often hybrids:** a flexible external JSON layer → normalized into strongly typed internal domain records → exhaustive switch inside the processing module. There is no need to force every layer of a system into the same style.

## 12. Process for Choosing a Design in a Geometry Case Study

1. **List the shape types actually needed.** Do not create `Square` or `Polygon` just because examples are easy to write; check whether they have distinct invariants.
2. **List the core operations.** Do `area` and `perimeter` belong to the common contract for every shape? Does UI classification belong to the domain?
3. **Identify the frequent axis of change.** Adding subtypes or adding operations? Who owns extension rights?
4. **Decide open vs. closed hierarchy.** If third parties can add arbitrary shapes, an open interface is more natural. If the module needs to control the list, use `sealed`.
5. **Choose the data representation.** `record` fits geometric data acting as value objects with field-level immutability; if identity, lifecycle, or complex mutable state is needed, a regular class may be more appropriate.
6. **Define clear invariants.** Positive finite numbers, units of measurement, tolerances, degenerate shapes; do not leave these to pattern matching.
7. **Write a small implementation of each approach.** Compare clarity when writing formulas, adding a shape, and adding an operation.
8. **Test the compiler.** With a sealed switch, intentionally omit a case and confirm the build is rejected; do not use `default` just to make the build green.
9. **Test runtime and arithmetic.** Run valid inputs, invalid inputs, null, and boundary values; check overflow/precision if the domain requires it.
10. **Choose based on the team's maintenance cost.** Shorter code does not automatically guarantee readability, and the most pattern-rich design is not necessarily the simplest.

In a large codebase, do not overhaul an entire public API model just to convert an `if/else` chain into a pattern `switch`. You can roll it out incrementally: refactor pure calculations, add tests, evaluate compatibility, and only change the hierarchy when there is a real need.

## 13. Test Matrix for Both Approaches

A small test suite should cover **formulas**, **data rules**, and **extension contracts**:

| Case | Expected |
| --- | --- |
| `Circle(2)` | Area \(4\pi\); perimeter \(4\pi\) |
| `Rectangle(3,4)` | Area 12; perimeter 14 |
| `RightTriangle(3,4)` | Area 6; perimeter 12 |
| `Rectangle(4,4)` | Area 16; labeled square rectangle per demo classification |
| `Circle(3)` | Guarded branch `r >= 3` selected |
| `Rectangle(8,3)` | Branch `w > h` selected |
| `Circle(0)` or `Circle(-1)` | Rejected by demo constructor validation |
| `Circle(Double.NaN)` | Rejected by demo constructor validation |
| `area(null)` | Rejected by `Objects.requireNonNull` |
| Add a new subtype without updating exhaustive `switch` | Compiler reports missing branch on recompilation |
| Add a new operation on a sealed hierarchy | Compiler requires providing the necessary cases |
| Extremely large values | Requires separate overflow/precision policy testing |

### Assertions Should Not Rely Solely on `==` for Approximate Calculations

~~~java
// Conceptual test snippet, assuming area(...) is declared.
// Do not use bare Java assert if the project does not enable -ea.
double expected = 4.0 * Math.PI;
double actual = area(new Circle(2));
double tolerance = 1e-10;
if (Math.abs(expected - actual) > tolerance) {
    throw new AssertionError("Unexpected area: " + actual);
}
~~~

Tolerances are a testing policy, not a universal constant valid for every value or unit. For large values, relative error may be needed; with `NaN`, comparisons using `>` are especially prone to slipping through. The demos validate `NaN` at shape construction, but a real system must explicitly design for all important numerical cases.

**Do not lump multiple changes into one test:** exhaustiveness testing is compile-time testing; formula testing is runtime testing; serialization testing is integration testing. These three test layers complement one another.

## 14. Common Design Mistakes After Learning Pattern Matching

| Mistake | Why It Is Unsuitable | How to Fix |
| --- | --- | --- |
| Using `default -> 0.0` in a sealed switch | Hides missing shape types and produces wrong results | Exhaustive switch with explicit cases |
| Assuming `record` automatically blocks negative dimensions | `double` accepts many invalid values | Compact constructor with domain validation |
| Putting all UI formatting onto the `Shape` interface | Increases coupling between domain and presentation | Separate operations/services if not part of the domain |
| Converting all logic to `switch` even when just calling `shape.area()` | Unnecessary branching duplication | Keep polymorphism if behavior already belongs to the object |
| Using an open interface while expecting the compiler to list unknown subtypes | Two conflicting goals | Choose `sealed` if closed-world exhaustiveness is needed |
| Using `sealed` when plugins need to add arbitrary subtypes | Does not fit extensibility goals | Open interface or adapter/plugin boundary |
| Treating `==` on `double` as a “nearly equal” check | Fails on data with measurement error | Design an appropriate tolerance |
| Using `Math.sqrt(a*a+b*b)` for all magnitudes | Intermediate computation can overflow/underflow | Consider `Math.hypot(a,b)` |
| Trusting the compiler to prove mathematical formulas correct | Exhaustiveness only means a case exists | Unit tests and formula verification |
| Using `ShapeKind` and a bunch of nullable fields | Allows nonsensical payload combinations | Use per-variant records when appropriate |
| Refactoring from OOP to `sealed` and promising performance gains | No measurement data | Benchmark/profile after identifying hot paths |
| Adding a new shape type without reviewing domain semantics | For example, ellipse or square has its own rules | Specify invariants and formulas before extending |

## 15. Guided Practice Exercises

### Exercise 1 — Choosing Between OOP and Pattern Switch

A library lets users define `Hexagon`, `Star`, and arbitrary shapes, while every shape must provide `area()` and `perimeter()`. Which design should you lean toward?

**Suggested answer:** **Open interface + polymorphism**, because implementations come from external users and the core operations are fixed. You can use records or classes depending on the shape; validate data at construction time. A closed sealed hierarchy with a fixed subtype list does not fit an open plugin requirement.

### Exercise 2 — Choosing When Operations Are Added Frequently

An engine has only three shapes, rarely adds subtypes, and continuously adds operations for SVG export, perimeter, area, and label display. Which approach should you choose?

**Suggested answer:** **Sealed records + switch** is a strong candidate because the shape set is stable and operations can be placed separately. However, if rendering requires complex state or a visitor framework is already in place, another architecture may be chosen; analyze coupling rather than applying rules mechanically.

### Exercise 3 — Exhaustiveness Error Warning

In `area(Shape shape)`, delete `case RightTriangle(...)` and recompile. What happens?

**Answer:** The `switch expression` over the sealed hierarchy is no longer exhaustive, so the compiler rejects it. Do not add `default -> 0.0` to silence the error, because calculations for triangles would then be wrong.

### Exercise 4 — Formulas and Arithmetic

For `RightTriangle(5,12)`, what are the expected area and perimeter? Why use `Math.hypot`?

**Answer:** Area \(5\times12/2=30\); hypotenuse 13; perimeter \(5+12+13=30\). `Math.hypot` is the API dedicated to computing the square root of the sum of squares, useful for reducing intermediate numerical risks.

### Exercise 5 — Modeling a Square

The system wants to distinguish squares from rectangles for statistics, while the area and perimeter formulas are the same. Is it strictly necessary to add `record Square`?

**Suggested answer:** No. If “square” is only a **derived property** of `Rectangle` and does not need separate invariants or identity, you can keep `Rectangle` and an appropriate classification function. If the domain has a distinct contract for squares (such as requiring only one side or separate creation operations), `Square` is a reasonable design, though it will affect exhaustive switches.

### Exercise 6 — Floating-Point Error

`Rectangle(4.0, 4.0)` is labeled `square rectangle`. If width and height come from two nearly equal measurements, should you use exact `when w == h`?

**Suggested answer:** Only when the requirement is genuinely **exact equality**. For measured data, define “nearly equal” according to appropriate units and tolerance; do not default to a single fixed threshold for every problem.

## 16. Design Choice Conclusion

**Ask two questions before choosing syntax:**

1. **Is the set of shape types closed and controlled by a single module?**
2. **In the future, what changes more often: the shape types or the operations?**

If **shape types are open and common behavior is stable**, interface + polymorphism is a natural choice. If **the set of shape types is closed, there are many independent operations, and you want the compiler to catch missing cases**, `sealed` + `record` + exhaustive pattern `switch` is a strong choice. If you only need to check one type in a small method, an `instanceof` pattern may be the simplest. Visitor, adapter, or service patterns may be necessary when the architecture demands them.

Above all, **correct formulas, clear invariants, consistent geometric semantics, maintainable APIs, and reproducible tests** matter more than using new Java features everywhere. Java Pattern Matching provides a safer and more readable tool for expressing branching, but **it does not replace choosing the right domain model**.

**Official documentation:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java SE 21 — `Math.hypot`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#hypot(double,double)).
