# Handling Null Shapes in the Geometry Case Study

**Topic:** Java Core Pattern Matching — Geometry Case Study. This article uses **Java 21 or later** to practice sealed interfaces, record patterns, and pattern matching for switch (JEP 440, JEP 441). The goal is to handle a **null shape** with proper semantics while distinguishing it from a non-null shape that contains invalid coordinate data.

## 1. The Problem: An Absent Shape vs. an Invalid Shape

Suppose the system receives shapes: **Circle**, **Rectangle**, and **Segment**. The application has two different requirements:

- **Preview screen:** If there is no shape yet, display “NO SHAPE”. If there is a shape object but it is missing coordinates, display an appropriate data error instead of crashing the application.
- **Strict calculator:** Only accept shapes with valid data to compute area; null input or shapes missing coordinates must be rejected with a clear exception.

Two APIs can use the **same geometry model**, yet do not necessarily share the same contract for null. A common mistake is trying to turn **every null into area 0**, because **no shape**, **a shape with area 0**, and **a shape with corrupted data** are three distinct states.

Let us start with a clear classification:

| Input | Meaning | Appropriate handling |
| --- | --- | --- |
| **shape == null** | No shape object | Display empty state or reject at the API |
| **new Circle(null, 1)** | Circle exists, but center is missing | Detect missing data; do not assume center (0, 0) |
| **new Rectangle(null, 2, 5)** | Rectangle exists, but origin is missing | Report missing origin error |
| **new Segment(start, null)** | Segment exists, but one endpoint is missing | Report missing start/end point error |
| **new Circle(point, 0)** | Valid Circle, radius 0 | Area 0 is a meaningful result |
| **new Segment(p1, p2)** | Segment with two points | Length can be positive; 2D planar area is 0 |

**Principle:** Do not use numeric 0 or an empty String as a generic representation for all null cases if the caller needs to distinguish these states.

## 2. Data Model: sealed Shape, Point, and Three Records

A relatively closed geometry domain can be expressed with a sealed interface:

~~~java
sealed interface Shape permits Circle, Rectangle, Segment {}

record Point(double x, double y) {}

record Circle(Point center, double radius) implements Shape {}

record Rectangle(Point origin, double width, double height) implements Shape {}

record Segment(Point start, Point end) implements Shape {}
~~~

**This is an illustrative declaration snippet**; the full version with constructor size validation is in section 6.

Because **Circle**, **Rectangle**, and **Segment** are all records (implicitly final), each type is a concrete variant. The compiler can prove that a switch handles all subtypes of Shape without needing a default branch.

Each record has a geometric meaning:

- **Circle:** center and radius, area equals π × r².
- **Rectangle:** origin, width, and height; area equals width × height.
- **Segment:** start point, end point; length equals the square root of the sum of squared coordinate differences.

**Records do not automatically forbid null** for reference components such as **Point**. Therefore, **new Circle(null, 1)** can still be constructed if the constructor does not check center. Primitive components of type double cannot hold null, but can still hold **NaN** or infinite values if not validated.

A case study must distinguish two questions:

1. Which shape type is being processed? That is the job of **type/record patterns**.
2. Is the shape data itself valid for computation? That is the job of **constructor validation**, **guards**, or **validation logic in the API**.

Do not infer that a pattern match means the domain data is valid.

## 3. Null Selectors Behave Differently in instanceof and switch

### 3.1. instanceof does not match null

~~~java
Shape shape = null;
boolean isCircle = shape instanceof Circle;  // false
~~~

If switched to a pattern variable:

~~~java
if (shape instanceof Circle circle) {
    System.out.println(circle.radius());
} else {
    System.out.println("not a circle");
}
~~~

With a null shape, the **else** branch runs. No Circle is bound and no NullPointerException is thrown just because of the instanceof operator.

### 3.2. Pattern switch requires an explicit null policy

~~~java
static String category(Shape shape) {
    return switch (shape) {
        case null -> "NO SHAPE";
        case Circle c -> "CIRCLE";
        case Rectangle r -> "RECTANGLE";
        case Segment s -> "SEGMENT";
    };
}
~~~

When **shape == null**, case null returns “NO SHAPE”. The remaining cases use **type patterns** to classify non-null objects.

If case null is omitted, the switch expression can still be exhaustive over the three subtypes, but when it receives null, it normally throws **NullPointerException**. Type exhaustiveness **does not mean** accepting null.

**default does not automatically replace case null.** If you want to group null and other types into the same branch on an open selector, Java 21 provides the syntax **case null, default**. However, on a sealed Shape whose subtypes are all known, writing **case null** separately is explicit and avoids having default hide a new subtype case.

### 3.3. Not every “null” is the selector

Consider three values:

~~~java
Shape missing = null;
Shape circleWithoutCenter = new Circle(null, 2);
Shape segmentWithoutEnd = new Segment(new Point(0, 0), null);
~~~

- **missing** is a null selector.
- **circleWithoutCenter** is a non-null Circle object.
- **segmentWithoutEnd** is a non-null Segment object.

When processing each value, **case null** only catches the first case. The other two cases require inspecting record components or each type's invariants.

## 4. Nested Record Patterns and Null Values

Record patterns are very convenient when extracting coordinates:

~~~java
case Circle(Point(double x, double y), double radius) ->
        "CIRCLE area=" + fmt(Math.PI * radius * radius);
~~~

This pattern requires:

1. The selector is actually a non-null **Circle**.
2. The **center** component must be a **Point** object so it can be deconstructed.
3. The two components of Point are **double x** and **double y**.
4. The radius is bound to **radius**.

If **center == null**, the nested pattern **Point(...)** cannot match. It **does not** automatically substitute coordinates (0,0) and is not treated as a valid Circle just because the selector is non-null.

Therefore, when the Circle constructor allows a null center, a fallback branch is needed:

~~~java
case Circle(Point(double x, double y), double radius) ->
        "CIRCLE area=" + fmt(Math.PI * radius * radius);
case Circle(var center, var radius) -> "INVALID: circle center";
~~~

**case Circle(var center, var radius)** does not require center to be non-null. It covers the remaining Circles, including a Circle with a null center. The fallback branch is not merely “fixing a compiler error”: it expresses the **business decision that shape data missing a center is invalid**.

Similarly for Segment:

~~~java
case Segment(Point(double x1, double y1),
             Point(double x2, double y2)) ->
        "SEGMENT length=" + fmt(Math.hypot(x2 - x1, y2 - y1));
case Segment(var start, var end) ->
        "INVALID: segment endpoint";
~~~

If start or end is null, the two-Point pattern does not match; the general Segment case returns the error message. In Java, **Math.hypot(dx, dy)** is a length calculation that is generally clearer and more numerically stable than computing **Math.sqrt(dx*dx + dy*dy)** directly for values with large magnitudes.

**Note:** A null selector is not the only reason a record pattern fails to match. When nesting record patterns across multiple levels, each reference component must be evaluated according to its own null contract.

## 5. Two API Policies on the Same Hierarchy

With the same Shape type, a system may need two methods.

### Lenient API for display: describe(Shape)

~~~java
// Excerpt of representative branches; the full method is in section 6.
return switch (shape) {
    case null -> "NO SHAPE";
    case Circle(Point(var x, var y), var radius) ->
            "CIRCLE area=" + fmt(Math.PI * radius * radius);
    case Circle(var center, var radius) -> "INVALID: circle center";
    // Rectangle and Segment branches are fully declared in the example.
};
~~~

The snippet above is **only an illustrative excerpt, not an exhaustive switch to copy and run standalone**. The API's intent is **not to throw an exception just because a shape or its coordinates are missing**; instead, it produces a displayable message. However, the constructor can still throw an exception at shape creation time if dimensions are invalid.

### Strict API for computation: areaStrict(Shape)

~~~java
static double areaStrict(Shape shape) {
    Objects.requireNonNull(shape, "shape");
    return switch (shape) {
        case Circle(Point(var x, var y), double r) -> Math.PI * r * r;
        case Circle(var center, var radius) ->
                throw new IllegalArgumentException("circle center");
        case Rectangle(Point(var x, var y), double w, double h) -> w * h;
        case Rectangle(var origin, var w, var h) ->
                throw new IllegalArgumentException("rectangle origin");
        case Segment(Point(var x1, var y1), Point(var x2, var y2)) -> 0.0;
        case Segment(var start, var end) ->
                throw new IllegalArgumentException("segment endpoint");
    };
}
~~~

This is code excerpted from the full example, assuming **java.util.Objects** is imported and the corresponding Shape records exist.

At the method boundary, **Objects.requireNonNull(shape, "shape")** rejects a null selector with **NullPointerException** before the switch. The remaining cases only handle non-null subtypes. If a point is missing, that subtype's branch throws **IllegalArgumentException**.

Because all three subtypes are covered, the switch expression does not need a default branch. Branches that **throw** are still valid terminations of a switch expression; not every branch has to return a double if it intentionally terminates abnormally.

**Important convention:** NullPointerException and IllegalArgumentException have different meanings in this API. While not the only rule every organization must use, distinguishing them helps documentation and callers identify the exact violated condition.

## 6. Complete, Runnable Java 21 Program

The program below includes a **null selector**, **shapes containing a null Point**, **nested record patterns**, **area**, **length**, and **constructor validation**.

Save the entire code to a file named **NullShapeDemo.java**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class NullShapeDemo {
    sealed interface Shape permits Circle, Rectangle, Segment {}

    record Point(double x, double y) {}

    record Circle(Point center, double radius) implements Shape {
        Circle {
            if (!Double.isFinite(radius) || radius < 0) {
                throw new IllegalArgumentException("radius");
            }
        }
    }

    record Rectangle(Point origin, double width, double height)
            implements Shape {
        Rectangle {
            if (!Double.isFinite(width) || !Double.isFinite(height)
                    || width < 0 || height < 0) {
                throw new IllegalArgumentException("size");
            }
        }
    }

    record Segment(Point start, Point end) implements Shape {}

    static String fmt(double value) {
        return String.format(Locale.ROOT, "%.2f", value);
    }

    /**
     * Returns a description for display; accepts a null selector.
     *
     * @param shape may be null; null means no shape yet
     * @return non-null description; shapes missing coordinates are marked INVALID
     */
    static String describe(Shape shape) {
        return switch (shape) {
            case null -> "NO SHAPE";

            case Circle(Point(double cx, double cy), double radius) ->
                    "CIRCLE area=" + fmt(Math.PI * radius * radius);
            case Circle(var center, var radius) ->
                    "INVALID: circle center";

            case Rectangle(Point(double ox, double oy),
                           double width, double height) ->
                    "RECTANGLE area=" + fmt(width * height);
            case Rectangle(var origin, var width, var height) ->
                    "INVALID: rectangle origin";

            case Segment(Point(double x1, double y1),
                         Point(double x2, double y2)) ->
                    "SEGMENT length="
                            + fmt(Math.hypot(x2 - x1, y2 - y1));
            case Segment(var start, var end) ->
                    "INVALID: segment endpoint";
        };
    }

    /**
     * Computes the area of a Shape with all required coordinates.
     *
     * @param shape must be non-null
     * @return the area; a valid segment has area 0
     * @throws NullPointerException if shape is null
     * @throws IllegalArgumentException if shape is missing
     *         the required center/origin/endpoint
     */
    static double areaStrict(Shape shape) {
        Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(Point(var x, var y), double radius) ->
                    Math.PI * radius * radius;
            case Circle(var center, var radius) ->
                    throw new IllegalArgumentException("circle center");

            case Rectangle(Point(var x, var y),
                           double width, double height) ->
                    width * height;
            case Rectangle(var origin, var width, double height) ->
                    throw new IllegalArgumentException("rectangle origin");

            case Segment(Point(var x1, var y1),
                         Point(var x2, var y2)) -> 0.0;
            case Segment(var start, var end) ->
                    throw new IllegalArgumentException("segment endpoint");
        };
    }

    public static void main(String[] args) {
        Shape[] samples = {
            null,
            new Circle(new Point(0, 0), 2),
            new Circle(null, 1),
            new Rectangle(new Point(1, 1), 3, 4),
            new Rectangle(null, 2, 5),
            new Segment(new Point(0, 0), new Point(3, 4)),
            new Segment(new Point(0, 0), null)
        };

        for (Shape shape : samples) {
            System.out.println(describe(shape));
        }

        System.out.println("AREA: " + fmt(areaStrict(
                new Circle(new Point(1, 2), 2))));

        try {
            areaStrict(null);
        } catch (NullPointerException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }

        try {
            areaStrict(new Circle(null, 1));
        } catch (IllegalArgumentException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }

        try {
            new Circle(new Point(0, 0), -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }
    }
}
~~~

### Compile and Run

Using JDK 21 or newer, in the directory containing **NullShapeDemo.java**:

~~~bash
javac NullShapeDemo.java
java NullShapeDemo
~~~

**Exact output:**

~~~text
NO SHAPE
CIRCLE area=12.57
INVALID: circle center
RECTANGLE area=12.00
INVALID: rectangle origin
SEGMENT length=5.00
INVALID: segment endpoint
AREA: 12.57
REJECTED: shape
REJECTED: circle center
REJECTED: radius
~~~

**Result explanation:**

1. **null:** describe selects case null and prints NO SHAPE, instead of letting NullPointerException occur.
2. **Circle((0,0), 2):** center is a non-null Point, the nested pattern matches; area π × 2² is approximately **12.57**.
3. **Circle(null, 1):** the selector is Circle, but the pattern containing Point does not match; the general Circle case returns INVALID: circle center.
4. **Rectangle((1,1), 3,4):** area 3 × 4 = **12.00**.
5. **Rectangle(null, 2,5):** missing Point origin, the fallback branch returns INVALID: rectangle origin.
6. **Segment((0,0),(3,4)):** differences on the two axes are 3 and 4, so the length is **5.00**.
7. **Segment((0,0),null):** missing one endpoint, the fallback branch returns INVALID: segment endpoint.
8. **areaStrict** on a valid Circle returns the area and is printed with two decimal places.
9. **areaStrict(null):** Objects.requireNonNull rejects it with NullPointerException and message shape.
10. **areaStrict(Circle(null,1)):** missing center, so it throws IllegalArgumentException with message circle center.
11. **Circle with radius -1:** the compact constructor throws IllegalArgumentException immediately on object creation; areaStrict is not even called.

The **fmt** method uses **Locale.ROOT** so that the decimal separator in the example output is a **dot**, independent of the machine's default locale.

**Precision note:** Java double is a floating-point number; the example prints two decimal places for easy inspection. When building high-precision geometry applications, you must define tolerance, NaN, Infinity, coordinate magnitude limits, and overflow issues when computing area. Checking that radius is finite does not automatically guarantee π × radius² is always finite if radius is extremely large.

## 7. Why Use a General Branch per Subtype?

In the program, the two consecutive Circle cases are:

~~~java
case Circle(Point(double cx, double cy), double radius) ->
        "CIRCLE area=" + fmt(Math.PI * radius * radius);
case Circle(var center, var radius) ->
        "INVALID: circle center";
~~~

**First branch:** describes a Circle whose center is actually a Point.  
**Second branch:** is tried if the first branch does not match, and covers all remaining Circles (here, a null center).

The second branch serves to **preserve exhaustiveness** of the switch and **explicitly report data errors**. The same rule applies to Rectangle and Segment.

If you only write a nested Point pattern for each subtype without a fallback branch, the compiler can consider the switch expression **not exhaustive**, because record objects can still contain null components. You should not solve the missing branches with a **default -> 0**: it can both hide data errors and cause future new subtype handling branches to be skipped.

### Case Ordering

Put **narrower patterns first** and **broader patterns later**. If you place **case Circle(var center, var radius)** before **Circle(Point(...), ...)**, the broader pattern will cover all Circles and make the later case dominated (unreachable).

With guarded switches, also remember:

~~~java
case Circle(Point(var x, var y), double r) when r > 0 ->
        "positive circle";
case Circle(var center, var radius) -> "another circle";
~~~

The guard **r > 0** narrows the first branch; the second branch handles the remaining cases. If a guard throws an exception instead of returning false, the exception propagates; the switch does not treat it as a non-match.

## 8. Another Option: Forbid Null Point Directly in the Constructor

In a complete domain system, a Circle missing its center or a Segment missing an endpoint is usually **not a valid state**. You can protect invariants right at object creation time:

~~~java
// Alternative model; do not combine with the Circle declaration in the main program.
record StrictCircle(Point center, double radius) {
    StrictCircle {
        Objects.requireNonNull(center, "center");
        if (!Double.isFinite(radius) || radius < 0) {
            throw new IllegalArgumentException("radius");
        }
    }
}
~~~

With such a model, **new StrictCircle(null, 1)** is rejected in the constructor, so code handling a validly created StrictCircle does not need the same level of defensiveness for a null center. However, **the selector of an API receiving StrictCircle** can still be null; a separate contract must be specified.

For Segment:

~~~java
// Alternative model; requires both endpoints.
record StrictSegment(Point start, Point end) {
    StrictSegment {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
    }
}
~~~

When data comes from JSON, a database, or an external API, you can use a **raw input** type that allows missing fields, then convert it to a **validated domain shape** with an invariant-enforcing constructor. That way, geometry algorithms do not have to check the same null condition at multiple points.

**Using records does not automatically make data valid.** Compact constructors are an option for protecting invariants, but you must also consider NaN/Infinity coordinates, magnitude bounds, width, height, and domain-specific rules.

## 9. Choosing Between case null, Early Checks, and a “No Shape” Representation Type

There are three different design approaches that should not be mixed:

| Policy | How to write it | Advantages and responsibilities |
| --- | --- | --- |
| **Display absent state** | **case null -> "NO SHAPE"** | Convenient for UI; caller clearly knows the result string |
| **Reject missing input** | **Objects.requireNonNull(shape, "shape")** | Fail fast at the computation boundary; Javadoc needs @throws |
| **Represent absence with a dedicated type** | **Optional<Shape>**, or a domain-meaningful NoShape subtype | Avoids using null as an arbitrary sentinel; must document result meaning |

If the application uses Optional, **Optional.empty()** represents no shape, while **Optional.of(shape)** requires a non-null shape. **Optional.ofNullable(shape)** converts null into Optional.empty(). However, converting between a nullable Shape and Optional does not automatically solve null components inside Circle or Segment; constructors or validation are still necessary.

If using a domain subtype such as **NoShape**, you must determine whether it is truly a **sensible kind of Shape**. Adding NoShape to the sealed hierarchy forces existing exhaustive switches to review the new case upon recompilation. You should not add a subtype solely to avoid documenting null when it has no domain meaning.

### Where to Decide?

- **UI/presentation boundary:** may choose NO SHAPE for an unselected object.
- **Domain calculation:** may reject a null selector and shapes with missing data.
- **Importer/parser:** may return a validation result instead of creating an invalid Shape.
- **Persistence/API transport:** must distinguish a missing field, a JSON null field, and a shape object with null subfields according to the data contract.

Not every boundary uses the same fallback value; consistent design means **each API publishes its own clear policy**.

## 10. Javadoc for Null Shapes

When a public method accepts Shape, do not just write “handles null”. Describe **when null is valid and the specific consequences**.

Example of how to document the program's two APIs:

~~~java
/**
 * Returns a description for display, accepting a null Shape.
 *
 * @param shape may be null; null means no shape yet
 * @return non-null String; null yields "NO SHAPE",
 *         shapes missing a Point yield a message starting with "INVALID:"
 */
static String describe(Shape shape) { /* body in section 6 */ }

/**
 * Computes the area for a non-null Shape with all required points.
 *
 * @param shape must not be null
 * @return area as a double; a valid Segment returns 0.0
 * @throws NullPointerException if shape is null
 * @throws IllegalArgumentException if the shape is missing a required Point
 */
static double areaStrict(Shape shape) { /* body in section 6 */ }
~~~

This is **illustrative Javadoc**, not standalone methods to copy verbatim into Java. To declare valid code, use the full implementation in section 6.

Keep in mind:

1. **@param:** whether the selector is nullable or nonnull.
2. **@return:** return value when null and when the shape object is missing components.
3. **@throws:** exception type and throwing condition; do not confuse with exceptions from the shape constructor that occur **before calling the API**.
4. **Result names:** NO SHAPE, INVALID, and 0.0 have different meanings; if the policy changes, update the documentation and tests.

If a project uses annotations like **@Nullable** or **@NonNull**, use the annotation system suited to the project's toolchain; Java SE does not have a single @Nullable annotation in java.lang understood uniformly by all analyzers. Annotations do not automatically generate case null branches or runtime checks.

## 11. Required Test Matrix

The following table is based on the two APIs in the example:

| Input | describe | areaStrict |
| --- | --- | --- |
| **null** | NO SHAPE | NPE: shape |
| **Circle(Point(0,0),2)** | CIRCLE area=12.57 | Area approx. 12.56637 |
| **Circle(null,1)** | INVALID: circle center | IAE: circle center |
| **Rectangle(Point(1,1),3,4)** | RECTANGLE area=12.00 | 12.0 |
| **Rectangle(null,2,5)** | INVALID: rectangle origin | IAE: rectangle origin |
| **Segment(Point(0,0),Point(3,4))** | SEGMENT length=5.00 | 0.0 |
| **Segment(Point(0,0),null)** | INVALID: segment endpoint | IAE: segment endpoint |
| **Circle(Point(0,0),0)** | CIRCLE area=0.00 | 0.0 |
| **Circle(Point(0,0),-1)** | Constructor rejects | No valid object to pass |

In the table, **NPE** = NullPointerException and **IAE** = IllegalArgumentException.

A test suite should assert **the result or exception type**, rather than just calling methods without asserting. For doubles, compare results with an appropriate tolerance instead of comparing against a formatted string across all domain logic.

### Supplemental Tests Without a Framework

The following snippet is placed **inside class NullShapeDemo** so it can access the nested types and static methods:

~~~java
// Illustrative supplemental code; do not copy verbatim outside the class.
if (!"NO SHAPE".equals(describe(null))) {
    throw new AssertionError("null selector");
}
if (!"INVALID: circle center".equals(describe(new Circle(null, 1)))) {
    throw new AssertionError("null component");
}
if (Math.abs(areaStrict(new Rectangle(new Point(0, 0), 3, 4)) - 12)
        > 1.0e-9) {
    throw new AssertionError("rectangle area");
}
try {
    areaStrict(null);
    throw new AssertionError("expected exception");
} catch (NullPointerException expected) {
    // The API rejects null by contract.
}
~~~

If using JUnit, you can replace these with **assertEquals**, **assertThrows**, and floating-point tolerance checks according to your framework version. You should also test **nested null**, **zero radius/width**, **negative dimensions**, **NaN/Infinity**, and **very large coordinates** if the application allows them.

## 12. Refactoring Legacy if-else: Preserving Null Behavior

A legacy snippet often looks like this:

~~~java
static String oldTypeName(Shape shape) {
    if (shape instanceof Circle) return "circle";
    if (shape instanceof Rectangle) return "rectangle";
    if (shape instanceof Segment) return "segment";
    return "missing";
}
~~~

**oldTypeName(null)** returns “missing”. When converting to switch:

~~~java
static String newTypeName(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case Segment s -> "segment";
        case null -> "missing";
    };
}
~~~

This preserves null behavior. If you omit case null, you can change the runtime path to NullPointerException, even though the switch is still exhaustive over subtypes.

With **nested record patterns**, you must also check how **null components** were handled by the legacy code. For example, if legacy code read **circle.center()** without checking for null, it may have thrown NPE at a different point; switching to a fallback case that returns INVALID is an **intentional behavior change** that must be tested and documented, not disguised as a pure syntax refactor.

Principles when migrating:

1. Record null inputs and legacy return values/exceptions.
2. Write tests for null selector and null center/origin/endpoint.
3. Convert logic using type/record patterns.
4. Place null and fallback branches according to the contract.
5. Verify exhaustiveness and ensure no case is dominated.
6. Confirm results, side-effect order, and exception types remain unchanged, except for approved business changes.

## 13. Common Mistakes

**Mistake 1 — Assuming default catches null.** In a Java 21 pattern switch, default normally does not replace case null; explicitly verify the null selector policy.

**Mistake 2 — Assuming a record pattern guarantees all components are non-null.** A case like Circle(var center, var radius) can receive a null center; do not immediately call center.x() without an invariant or check.

**Mistake 3 — Writing only nested Point patterns and forgetting fallbacks.** You can miss Circle(null,1), Rectangle(null,...), or a Segment with a null endpoint. The compiler may report that the switch expression is not exhaustive.

**Mistake 4 — Using 0 as a fallback for every error.** A null Shape, Circle(radius=0), a Segment with area 0, and a shape with corrupted data have different meanings; merging them can lose error signals.

**Mistake 5 — Checking only radius and forgetting Point.** The constructor may reject a negative radius while still allowing a null center. Then computing area from radius returns a number without proving the shape has a valid position.

**Mistake 6 — Using String.format without fixing the locale in examples.** Machines using a locale with a decimal comma can produce different example output. Using Locale.ROOT or explicitly specifying the locale keeps tests stable.

**Mistake 7 — Catching every NullPointerException and treating it as “no shape”.** An NPE can also come from a bug in a case body or accessor. Broad catching hides the source of bugs; handle it at the boundary where the cause is known.

**Mistake 8 — Not documenting the contract at the API boundary.** Callers do not know whether null is accepted or rejected. Changing the implementation without updating Javadoc/tests breaks implicit compatibility.

**Mistake 9 — Confusing exhaustiveness with geometric validity.** The compiler guarantees there is a branch per type/pattern; it does not prove finite radius, valid coordinates, or overflow-free area calculation.

## 14. Shape API Design Checklist

- [ ] Distinguished **null shape** from **an existing shape with a null component**?
- [ ] Does the API need to display an empty state or reject invalid data?
- [ ] Do Circle.center, Rectangle.origin, and Segment.start/end have a nonnull invariant or a clear fallback policy?
- [ ] Is there a case null (if accepted) or Objects.requireNonNull (if rejected)?
- [ ] Do nested record patterns have a fallback case for null components?
- [ ] Do narrower cases appear before broader cases to avoid dominance?
- [ ] Is the switch exhaustive over sealed Shape without hiding new subtypes behind an unnecessary default?
- [ ] Is area 0 distinguished from no shape and data errors?
- [ ] Does the constructor validate radius and width/height; have coordinates and floating-point precision been considered?
- [ ] Do @param, @return, and @throws accurately document null behavior?
- [ ] Are there tests for null selector, null component, zero dimensions, invalid dimensions, and new subtypes?

**Conclusion:** In the geometry case study, **a null shape is an API decision**, not just a case label. Java 21 makes it clear through **case null**, sealed hierarchies, and nested record patterns. When a shape is non-null but an inner Point is null, an invariant or a per-subtype fallback branch is needed. Choose between **displaying a missing state** or **rejecting with an exception** based on application semantics, document it clearly with Javadoc, and verify it with tests; do not turn every missing-data case into area 0.