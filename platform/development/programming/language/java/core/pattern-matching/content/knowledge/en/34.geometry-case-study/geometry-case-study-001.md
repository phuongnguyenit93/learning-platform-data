# Designing Shape with a Sealed Interface – A Geometry Case Study in Java 21

A geometry application typically handles several kinds of shapes that share the same domain meaning: **circles**, **rectangles**, and **right triangles**. All of them can have their **area** and **perimeter** computed, or be classified or displayed, yet the formulas differ for each type. Using only a single `Shape` class with many optional fields and a chain of manual type checks makes the model hard to maintain, prone to invalid states, and liable to miss computation branches.

Since Java 17, a **`sealed interface`** lets you expose a common type while **directly restricting which types are allowed to implement it**. Combining `record` types for each variant with **pattern matching for `switch`** in Java 21 yields a concise model whose core data is immutable and whose classification operations are checked by the compiler for **exhaustiveness**.

This article focuses on how to design the `Shape` domain model, not just syntax. The complete examples use **Java 21+**, `record`, `sealed`, record patterns, `when`, and `switch` expressions; `--enable-preview` is not needed.

## 1. Domain requirements and modeling choices

Suppose the geometry library initially supports three shape types:

| Shape type | Data to store | Area | Perimeter |
| --- | --- | --- | --- |
| Circle `Circle` | Radius `r` | `Math.PI * r * r` | `2 * Math.PI * r` |
| Rectangle `Rectangle` | Width `w`, height `h` | `w * h` | `2 * (w + h)` |
| Right triangle `RightTriangle` | Two legs `a`, `b` | `a * b / 2` | `a + b + Math.hypot(a, b)` |

To represent the domain accurately:

1. Only the three types above are considered a `Shape` in the initial version.
2. Each shape type stores **only the parameters** needed for that shape.
3. Dimensions must be **finite and greater than 0** floating-point numbers upon construction; `NaN`, infinity, `0`, or negative values are rejected.
4. Every operation that computes area or perimeter must handle **all three shape types**.
5. When a new shape type is added, missing handling branches must be caught early at compile time rather than silently returning an incorrect default result.
6. The `null` contract must be explicit: calculation operations reject `null`, whereas the classification function can return a `missing` label.

**Not every application needs exactly these three shape types.** This is a *case study* with an intentionally closed set of variants. If a product allows external plugins to define arbitrary shapes, a closed `sealed` hierarchy may not be appropriate.

## 2. Shape structure diagram

```text
                   sealed interface Shape
                            |
                  permits 3 record types
                /           |            \
               /            |             \
       record Circle    record Rectangle    record RightTriangle
        radius:double    width:double        legA:double
                         height:double       legB:double

       ShapeService:
         area(Shape)       -> exhaustive pattern switch
         perimeter(Shape)  -> exhaustive pattern switch
         kind(Shape)       -> guarded case / case null
```

Each record is a data-carrying **variant**; operations can live in an independent service or utility methods and use pattern matching to select the algorithm. Conceptually, this is how an **algebraic data type (ADT)** is represented: a sum of fixed variants, each with its own data structure.

There are two main benefits:

- **Clean data model:** `Circle` has no extraneous `width` or `legA` fields; `RightTriangle` does not have to invent a radius.
- **Compiler-assisted enforcement:** a `switch` over `Shape` can verify that every permitted variant has a matching case.

## 3. Declaring the sealed interface and record subtypes

The core of the model:

```java
sealed interface Shape permits Circle, Rectangle, RightTriangle {}

record Circle(double radius) implements Shape {}

record Rectangle(double width, double height) implements Shape {}

record RightTriangle(double legA, double legB) implements Shape {}
```

This is an **illustrative declaration snippet**; in a real Java program, these types must be placed within the same permitted scope/package/module according to Java's rules. The complete runnable class is in Section 9.

### What sealed means

In:

```java
sealed interface Shape permits Circle, Rectangle, RightTriangle {}
```

- The `sealed` keyword restricts **which direct subclasses or subinterfaces** are allowed to implement `Shape`.
- `permits` lists the permitted variants.
- Another class that tries to write `implements Shape` without being in the `permits` list will be rejected by the compiler.
- A direct subtype of a sealed interface must explicitly declare its extension policy: **`final`**, **`sealed`**, or **`non-sealed`** (following the corresponding rules).
- A `record` is **implicitly `final`**, so `Circle`, `Rectangle`, and `RightTriangle` here are terminal variants; no subclass can extend them.

**Important:** `sealed` does not by itself guarantee that all data components are valid. It **closes the subtype set**, rather than replacing checks such as `radius > 0` or `Double.isFinite(radius)`. Those invariants must be enforced inside each record.

### Why use records?

Records fit shapes defined by data that rarely changes:

```java
record Circle(double radius) implements Shape {}
```

Java automatically generates the canonical constructor, the `radius()` accessor, and state-based `equals`, `hashCode`, and `toString` implementations. Record components are `private final`, with no default setters.

Example:

```java
Circle c = new Circle(2.0);
System.out.println(c.radius()); // 2.0
```

In this case study, all components are primitive `double` values, so an instance's dimension data cannot be mutated through a mutable reference. However, **records in general are only shallowly immutable**: if a record has a mutable `List` component, the referenced object can still be modified; using a record does not automatically prevent that.

## 4. Enforcing invariants: finite and positive dimensions

A model using `double` values has special values: `Double.NaN`, `Double.POSITIVE_INFINITY`, and `Double.NEGATIVE_INFINITY`. Those are not valid radii or side lengths in this problem. Likewise, `0` and negative values do not represent shapes with positive dimensions in the chosen model.

Validate them right at construction time:

```java
private static void checkDimension(double value, String field) {
    if (!Double.isFinite(value) || value <= 0.0) {
        throw new IllegalArgumentException(
                field + " must be finite and positive");
    }
}
```

For a record, use a **compact constructor**:

```java
record Circle(double radius) implements Shape {
    Circle {
        checkDimension(radius, "radius");
    }
}
```

The same applies to the rectangle and right triangle:

```java
record Rectangle(double width, double height) implements Shape {
    Rectangle {
        checkDimension(width, "width");
        checkDimension(height, "height");
    }
}

record RightTriangle(double legA, double legB) implements Shape {
    RightTriangle {
        checkDimension(legA, "legA");
        checkDimension(legB, "legB");
    }
}
```

The blocks above are **members of the same demo class**: `checkDimension` is declared in the enclosing class. They are not standalone files that can compile without that helper method.

When code calls:

```java
new Circle(0.0);
new Rectangle(Double.NaN, 2.0);
new RightTriangle(3.0, Double.POSITIVE_INFINITY);
```

each call throws `IllegalArgumentException` in its respective constructor. Rejecting invalid values early saves downstream operations from repeatedly checking whether "dimensions exist and are valid" in every case.

**Numerical limitation:** checking `Double.isFinite` on **inputs** does not guarantee that multiplication or division results remain finite if huge numbers overflow `double`. In real engineering applications, you must choose an appropriate dimension range, units, tolerance, and overflow/precision policy. This article uses small dimensions with stable results to focus on modeling and pattern matching.

## 5. Computing area with an exhaustive pattern switch

A maintainable approach keeps data in the `record` types and places algorithms in methods that accept `Shape`:

```java
static double area(Shape shape) {
    Objects.requireNonNull(shape, "shape");
    return switch (shape) {
        case Circle(double r) -> Math.PI * r * r;
        case Rectangle(double w, double h) -> w * h;
        case RightTriangle(double a, double b) -> a * b / 2.0;
    };
}
```

The snippet above requires `import java.util.Objects;` or `java.util.Objects.requireNonNull`. This is an **illustrative method** with the same definition as in the complete program in Section 9.

### How pattern deconstruction works

With `case Rectangle(double w, double h)`:

1. `switch` checks whether the selector matches the `Rectangle` record type.
2. If it matches, the record pattern deconstructs the two components in declaration order.
3. `double w` and `double h` bind pattern variables whose types are inferred/checked.
4. The case body computes `w * h`; there is no need to cast `(Rectangle) shape` and call `width()` and `height()` manually.

If you do not need to deconstruct components immediately, you can still use a **type pattern** such as `case Rectangle rectangle -> rectangle.width() * rectangle.height();`. Choose a record pattern when the structure is used directly, and a type pattern when you need the whole instance or behavior on it.

### Why does the switch not need default?

Because `Shape` permits only the three `final` record subtypes listed, the compiler has enough information to prove that every **non-`null`** `Shape` value matches one of the cases. Therefore, the `switch` expression is **exhaustive**.

Omitting `default` is intentional: when a new variant is added, the compiler can immediately point out every method missing a case. If you write `default -> 0`, the area function risks silently returning `0` for a new shape instead of using the right formula.

### Why call requireNonNull before switch?

`Shape` is a reference type; callers can still pass `null`. In `area`, we decide that **`null` is invalid input** and reject it immediately with `Objects.requireNonNull(shape, "shape")`, giving a clear error message.

Even without that guard, a Java 21 pattern switch without `case null` also throws `NullPointerException` on a null selector; however, the explicit guard documents the method's contract and keeps the failure point consistent.

## 6. Computing perimeter: a second algorithm on the same sealed model

You do not need to add `area()` or `perimeter()` methods to each record just to make the model work. You can define a new operation using another pattern switch:

```java
static double perimeter(Shape shape) {
    Objects.requireNonNull(shape, "shape");
    return switch (shape) {
        case Circle(double r) -> 2.0 * Math.PI * r;
        case Rectangle(double w, double h) -> 2.0 * (w + h);
        case RightTriangle(double a, double b) ->
                a + b + Math.hypot(a, b);
    };
}
```

For `RightTriangle`, the two fields `legA` and `legB` are defined as **the two legs forming the right angle**, so the hypotenuse is `Math.hypot(a, b)` and the perimeter is `a + b + hypotenuse`. This is why naming it specifically `RightTriangle` rather than `Triangle` makes sense when storing only two sides.

`Math.hypot` computes the hypotenuse using an algorithm designed to handle floating-point arithmetic better than a naive `Math.sqrt(a*a + b*b)` in many numerical edge cases. Even so, the total perimeter can still overflow if dimensions exceed reasonable bounds.

Example for a right triangle with legs 3 and 4:

```text
area = 3 * 4 / 2 = 6
hypotenuse = hypot(3, 4) = 5
perimeter = 3 + 4 + 5 = 12
```

**Architectural strength:** adding a new operation such as `perimeter` does not require modifying the record declarations. Each operation is independently checked for exhaustiveness, making it easy to organize services and tests by behavior.

**Trade-off:** when adding a new shape type to `Shape`, you must update **all** exhaustive switches that handle it. For a closed domain, having the compiler force those updates is an advantage; for an open plugin system, it can be an unwanted cost.

## 7. `when` guards, case ordering, and shape classification

Beyond mathematical formulas, the domain may recognize **special shape categories**:

- A `Circle` with radius equal to `1.0` is a **unit circle**.
- A `Rectangle` with `width == height` is a rectangle with equal sides, corresponding to a **square** in this model.
- A `RightTriangle` with `legA == legB` is an **isosceles right triangle**.
- `null` can be classified as **missing** rather than throwing an exception, differing from the policy of `area`/`perimeter`.

```java
static String kind(Shape shape) {
    return switch (shape) {
        case null -> "missing";
        case Circle(double r) when r == 1.0 -> "unit circle";
        case Circle(double r) -> "circle r=" + r;
        case Rectangle(double w, double h) when w == h ->
                "square rectangle";
        case Rectangle(double w, double h) -> "rectangle";
        case RightTriangle(double a, double b) when a == b ->
                "isosceles right triangle";
        case RightTriangle(double a, double b) -> "right triangle";
    };
}
```

### Why must guarded `when` cases come first?

An unguarded `case Circle(double r)` matches **every** `Circle`, including radius `1.0`. If placed before `case Circle(double r) when r == 1.0`, the compiler detects that the latter branch is a **dominated case** (completely shadowed).

Similarly, the broader `case Rectangle(...)` must follow `Rectangle(...) when w == h`, and the broader `RightTriangle(...)` must follow the isosceles right triangle branch.

A `when` guard is evaluated only **after the pattern matches**, so `r`, `w`, `h`, `a`, and `b` are already bound with valid `double` types matching the record declarations.

### Floating-point comparisons in guards

`w == h` performs an **exact equality** check between two `double` values. In this case study, dimensions are supplied directly as `2.0` and `2.0`, so this matches the classification "the two stored dimensions in the record are equal."

If dimensions come from **computed or measured results**, two nearly equal values may not be bitwise equal. In that situation, use an **explicitly justified tolerance rule** (for example, based on the application's absolute/relative error budget) rather than assuming `==` is an approximate check. Do not replace `==` with an arbitrary threshold without defining units, precision, and boundary values.

### Why is null handled differently?

`kind(null)` returns `missing` because classification may be used in UI or diagnostics. `area(null)` intentionally throws `NullPointerException` because computing an area without input data violates the contract.

**There is no rule forcing every method to handle `null` identically.** What matters is documenting the contract clearly, keeping it consistent with each operation's purpose, and testing the chosen behavior.

## 8. `instanceof` with Shape and flow scoping

Not every check needs a `switch`. If you only need to detect one specific shape type, `instanceof` with a record pattern is enough:

```java
static boolean hasLargeCircle(Shape shape) {
    return shape instanceof Circle(double radius) && radius >= 2.0;
}
```

Here:

- If `shape == null`, `instanceof` evaluates to `false`.
- If `shape` is a `Rectangle` or `RightTriangle`, the record pattern `Circle(...)` does not match.
- If `shape` is a `Circle`, the variable `radius` is introduced with static type `double`.
- The right-hand side `radius >= 2.0` is evaluated only when the left-hand match succeeds due to `&&` short-circuiting, so the compiler allows `radius` to be used there.
- For `new Circle(2.0)`, the method returns `true`; for `new Circle(1.0)`, it returns `false`.

This is **flow scoping / definite matching**: the scope in which a pattern variable can be used depends on control flow proving that the pattern matched.

### When to use instanceof vs. switch

- A single question such as "is this a Circle meeting a condition?" → `instanceof` is short and clear.
- Need a result for **every Shape variant** → a `switch` expression makes exhaustiveness easier to enforce.
- Need multi-state logic inside a single subtype → use a dedicated method or Visitor; you do not have to force every algorithm into one large `switch`.

Avoid overusing `switch` for a single simple condition or writing manual casts when type/record patterns are available.

## 9. Complete Java 21 program – SealedShapeDemo.java

Save the following code into **`SealedShapeDemo.java`**. This is a self-contained example with input validation and both passing and failing test cases.

```java
import java.util.Locale;
import java.util.Objects;

public class SealedShapeDemo {
    sealed interface Shape permits Circle, Rectangle, RightTriangle {}

    record Circle(double radius) implements Shape {
        Circle {
            checkDimension(radius, "radius");
        }
    }

    record Rectangle(double width, double height) implements Shape {
        Rectangle {
            checkDimension(width, "width");
            checkDimension(height, "height");
        }
    }

    record RightTriangle(double legA, double legB) implements Shape {
        RightTriangle {
            checkDimension(legA, "legA");
            checkDimension(legB, "legB");
        }
    }

    private static void checkDimension(double value, String field) {
        if (!Double.isFinite(value) || value <= 0.0) {
            throw new IllegalArgumentException(field + " must be finite and positive");
        }
    }

    static double area(Shape shape) {
        Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(double r) -> Math.PI * r * r;
            case Rectangle(double w, double h) -> w * h;
            case RightTriangle(double a, double b) -> a * b / 2.0;
        };
    }

    static double perimeter(Shape shape) {
        Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(double r) -> 2.0 * Math.PI * r;
            case Rectangle(double w, double h) -> 2.0 * (w + h);
            case RightTriangle(double a, double b) -> a + b + Math.hypot(a, b);
        };
    }

    static String kind(Shape shape) {
        return switch (shape) {
            case null -> "missing";
            case Circle(double r) when r == 1.0 -> "unit circle";
            case Circle(double r) -> "circle r=" + r;
            case Rectangle(double w, double h) when w == h -> "square rectangle";
            case Rectangle(double w, double h) -> "rectangle";
            case RightTriangle(double a, double b) when a == b ->
                    "isosceles right triangle";
            case RightTriangle(double a, double b) -> "right triangle";
        };
    }

    static boolean hasLargeCircle(Shape shape) {
        return shape instanceof Circle(double radius) && radius >= 2.0;
    }

    static void assertClose(String name, double actual, double expected) {
        if (Math.abs(actual - expected) > 1e-9) {
            throw new AssertionError(name + ": " + actual + " != " + expected);
        }
    }

    public static void main(String[] args) {
        Shape[] shapes = {
            new Circle(2.0),
            new Rectangle(3.0, 4.0),
            new RightTriangle(3.0, 4.0)
        };
        for (Shape shape : shapes) {
            System.out.printf(
                    Locale.ROOT, "%s | area=%.2f | perimeter=%.2f%n",
                    kind(shape), area(shape), perimeter(shape));
        }
        System.out.println(kind(new Circle(1.0)));
        System.out.println(kind(new Rectangle(2.0, 2.0)));
        System.out.println(kind(new RightTriangle(3.0, 3.0)));
        System.out.println(kind(null));
        System.out.println("circle>=2: " + hasLargeCircle(shapes[0]));

        assertClose("circle", area(shapes[0]), 4.0 * Math.PI);
        assertClose("rectangle", area(shapes[1]), 12.0);
        assertClose("triangle", area(shapes[2]), 6.0);
        System.out.println("passed area checks=3");

        try {
            new Circle(0.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid circle rejected");
        }
        try {
            new Rectangle(Double.NaN, 2.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid rectangle rejected");
        }
        try {
            new RightTriangle(3.0, Double.POSITIVE_INFINITY);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid triangle rejected");
        }
        try {
            area(null);
        } catch (NullPointerException ex) {
            System.out.println("null area rejected=" + ex.getMessage());
        }
    }
}
```

Compile and run with **JDK 21+** (no preview flag required):

```bash
javac --release 21 -encoding UTF-8 -Xlint:all -Werror SealedShapeDemo.java
java SealedShapeDemo
```

**Exact stdout after running:**

```text
circle r=2.0 | area=12.57 | perimeter=12.57
rectangle | area=12.00 | perimeter=14.00
right triangle | area=6.00 | perimeter=12.00
unit circle
square rectangle
isosceles right triangle
missing
circle>=2: true
passed area checks=3
invalid circle rejected
invalid rectangle rejected
invalid triangle rejected
null area rejected=shape
```

The program compiles cleanly with `javac --release 21 -Xlint:all -Werror`, runs as shown, and produces the exact **13 lines of stdout** above. Using `Locale.ROOT` in `printf` ensures decimal points are formatted consistently regardless of the system's default locale.

### Explaining each group of results

- First three lines: compute both **area and perimeter** for `Circle(2.0)`, `Rectangle(3.0, 4.0)`, and `RightTriangle(3.0, 4.0)`; numbers are rounded to two decimal places only when printed, without rounding internal data.
- `unit circle`, `square rectangle`, and `isosceles right triangle`: confirm that `when` guards for special categories are selected **before** the general cases.
- `missing`: `kind(null)` enters `case null`.
- `circle>=2: true`: `instanceof Circle(double radius)` combined with `&&`.
- `passed area checks=3`: all three `assertClose` checks for valid areas pass within the `1e-9` tolerance on the chosen test data.
- Three `invalid ... rejected` lines: compact constructors reject `0.0`, `NaN`, and `Infinity`. In production unit tests, use `assertThrows` so a test **fails if the exception is not thrown**, rather than just printing inside `catch` as in this demo.
- `null area rejected=shape`: `area` rejects a null selector via `Objects.requireNonNull` with message `shape`.

**Note on floating-point testing:** `assertClose` in this demo fits the three small, finite test values. If a computation can return `NaN` or `Infinity`, check `Double.isFinite(actual)` or design a dedicated assertion, because `Math.abs(NaN - expected) > epsilon` evaluates to `false` and will not fail on its own. A production geometry library should use a sound comparison strategy and test extreme values.

## 10. What happens when adding a new Shape type?

Suppose the product needs to support a **parallelogram**:

```java
record Parallelogram(double base, double height, double side)
        implements Shape {}
```

That snippet is just a sketch: first you must **update `permits`** on `Shape` to allow the new subtype, and then add corresponding validation. Without listing it in `permits`, Java will not allow `Parallelogram implements Shape`.

After adding the new subtype, switch expressions such as `area`, `perimeter`, and `kind` no longer cover all variants. The Java 21 compiler reports an error:

```text
error: the switch expression does not cover all possible input values
```

To verify this independently, consider a small version that **intentionally omits the RightTriangle case**. Save it as `MissingShapeCase.java` if you want to see the error:

```java
public class MissingShapeCase {
    sealed interface Shape permits Circle, Rectangle, RightTriangle {}
    record Circle(double r) implements Shape {}
    record Rectangle(double w, double h) implements Shape {}
    record RightTriangle(double a, double b) implements Shape {}

    static double area(Shape s) {
        return switch (s) {
            case Circle(var r) -> Math.PI * r * r;
            case Rectangle(var w, var h) -> w * h;
        };
    }
}
```

Compile:

```bash
javac --release 21 -encoding UTF-8 MissingShapeCase.java
```

`javac` was tested on this code and rejects it:

```text
error: the switch expression does not cover all possible input values
1 error
```

This is a **compiler error**, not a warning. `-Xlint` or `-Werror` is not the cause; the code violates the exhaustiveness rule for a `switch` expression.

### How to update when extending the domain

1. Confirm that the new type belongs to the supported geometry domain; update `permits` intentionally.
2. Add invariants for the new parameters.
3. Add area, perimeter, and classification cases with the correct domain formulas.
4. Write tests for the new shape, covering valid inputs, invalid inputs, boundary values, and `null` where applicable.
5. Recompile at the target Java release; **do not add `default -> 0` just to hide a non-exhaustive error**.
6. Verify that guarded cases still precede broader cases to avoid a `dominated case`.

**Key point:** `sealed` closes **direct subtypes**. If a subtype is declared `non-sealed`, that branch can be extended further; here, all records are `final`, so the subtype tree genuinely terminates at the three leaves. Using `non-sealed` should be a deliberate architectural decision, not a workaround to avoid maintaining exhaustive switches.

## 11. Comparison with non-sealed designs and polymorphism

### A non-sealed Shape interface

```java
interface Shape {
    double area();
}
```

This design allows arbitrary implementations (subject to normal visibility/module rules). That is an advantage when a library needs extensibility through plugins. However, when writing an external `switch` over an open hierarchy, the compiler **cannot know every Shape type that might exist**, so it cannot verify exhaustiveness from just the initial three records.

### Placing behavior on each subtype

Another approach is classic polymorphism:

```java
interface Shape {
    double area();
    double perimeter();
}
```

In this approach, `Circle` implements its own formula, `Rectangle` implements its own, and callers invoke `shape.area()`. No switch is needed on each calculation.

**Which one should you choose?**

| Criterion | Sealed Shape + pattern switch | Interface + polymorphism |
| --- | --- | --- |
| Set of variants | Closed or intentionally bounded | Open to new implementations |
| Adding a new operation | Write a new switch/service without necessarily editing records | Usually add a method to the interface and update all implementations |
| Adding a new shape type | Update permits/cases; compiler helps detect missing branches | Add a new implementation of the interface contract |
| Geometry logic | Centralized by operation (`area`/`perimeter`) | Distributed across each shape type |
| Compiler checks all subtypes | Beneficial when the hierarchy is truly closed | Cannot reason about all future implementations |
| Best suited for | Closed domain models, DSLs, ASTs, rule engines | Open domains, plugin APIs, subtypes with distinct behavior |

Neither design is universally better for every application. If you prioritize **adding operations** over a stable set of variants, sealed + pattern switch scales cleanly along the behavior axis. If you prioritize **adding new shape types** from external modules, polymorphism may fit better.

### Visitor as a third option

With a multi-variant sealed model, the **Visitor pattern** can separate operations into a `Visitor<R>` interface and dispatch via `accept`. Visitor is useful when an existing codebase already uses Visitor or when an operation needs to be packaged as a stateful object. For three simple records in Java 21, however, pattern switches involve less boilerplate.

## 12. Common debugging issues with sealed Shape

### Error when implementing Shape outside permits

If you write:

```java
// WRONG example if Ellipse is not in Shape's permits list:
// record Ellipse(double a, double b) implements Shape {}
```

the compiler rejects it because the direct subtype is not permitted. The proper fix is to decide whether `Ellipse` truly belongs in the domain, update `permits` and related algorithms, and resolve any compile errors for missing cases.

### Dominated case error

```java
// WRONG: the general branch shadows the guarded branch.
return switch (shape) {
    case Circle(double r) -> "circle";
    case Circle(double r) when r == 1.0 -> "unit circle";
    case Rectangle(double w, double h) -> "rectangle";
    case RightTriangle(double a, double b) -> "right triangle";
};
```

The general `Circle(double r)` branch already matches every `Circle`, so the `when r == 1.0` case after it can never be selected. Place guarded cases before general cases, as shown in `kind` in the main program.

### NPE from a null selector

If you use `switch (shape)` without `case null`, a null selector throws `NullPointerException` in a Java 21 pattern switch. Either handle it explicitly like `kind` or reject it with `Objects.requireNonNull` like `area`.

### Wrong triangle formula

Two arbitrary sides of a general triangle are **not enough** to determine its area and perimeter. `RightTriangle` here has a specific geometric meaning: `legA` and `legB` are **the legs forming the right angle**, which makes `a*b/2` and `Math.hypot(a,b)` valid. To support arbitrary triangles, model all three sides (or other sufficient information) and enforce the triangle inequality.

### Floating-point overflow or non-finite results

A constructor that checks only that sides are finite and positive without bounding their magnitude can still allow values that cause `area` or `perimeter` to return `Infinity`. If that is unacceptable in a real domain, define dimension bounds, handle arithmetic accordingly, and test boundary cases.

### Confusing record equals/hashCode with "same shape kind"

`Circle(2.0)` and `Circle(2.0)` are equal according to `record.equals`; however, a `Rectangle` with the same area as a `Circle` does **not** become the same record or the same shape. Record equality reflects **the record type and component values**, not "equal area."

## 13. Testing workflow for the domain model

A test suite should combine **data validation**, **formula checks**, and **branching checks**:

| Test group | Sample input | What to verify |
| --- | --- | --- |
| Valid shapes | `Circle(2)`, `Rectangle(3,4)`, `RightTriangle(3,4)` | Formulas return expected results |
| Special guards | `Circle(1)`, `Rectangle(2,2)`, `RightTriangle(3,3)` | Correct `when` case is selected |
| Unsatisfied guards | `Circle(2)`, `Rectangle(3,4)`, `RightTriangle(3,4)` | General case runs as expected |
| Zero value | `Circle(0)` | Constructor rejects it |
| Negative value | `Rectangle(-1,2)` | Constructor rejects it |
| NaN | `Rectangle(NaN,2)` | Constructor rejects it |
| Infinity | `RightTriangle(3,+Infinity)` | Constructor rejects it |
| Null selector | `area(null)`, `kind(null)` | One intentionally throws; the other returns `missing` |
| Adding a subtype | Add a record to `permits` | Compiler requires updating non-exhaustive switches |
| Very large floats | Dimensions near maximum range | Verify overflow/precision policy |

In JUnit, use `assertEquals(expected, actual, delta)` for `double` results and `assertThrows(IllegalArgumentException.class, ...)` for invalid constructors. In real tests, do not rely on inspecting stdout; always use **assertions** so tests fail when results are wrong.

### Useful property tests

Beyond sample values, you can verify:

- **Positivity:** for valid dimensions within the system's numerical range, area and perimeter must be positive.
- **Swapping rectangle sides:** `area(Rectangle(w, h)) == area(Rectangle(h, w))` within acceptable tolerance.
- **Swapping right-triangle legs:** `perimeter(RightTriangle(a, b))` equals the result for `(b, a)` within acceptable precision.
- **Scaling homogeneity:** if all dimensions are scaled by `k > 0` without overflow, perimeter scales by `k` and area scales by `k * k`.
- **Compile-time test:** add a subtype in an auxiliary test source to confirm an incomplete switch is rejected, without keeping intentionally broken code in the production module.

## 14. Practice exercises

**Exercise 1.** Why can `sealed interface Shape` in this article use a `switch` expression without `default`?

*Answer:* Because its direct subtypes are restricted to `Circle`, `Rectangle`, and `RightTriangle`, and all three records are final classes. Every non-null `Shape` value belongs to one of those three cases.

**Exercise 2.** When adding `record Ellipse(double a, double b) implements Shape`, what should you do first?

*Answer:* Confirm it belongs in the domain, update `Shape`'s `permits` list, enforce validation for both semi-axes, and then add full handling cases (area, perimeter with an appropriate formula/algorithm and error policy, classification) along with tests. Do not just add a record and ignore compiler errors.

**Exercise 3.** Why must `case Circle(double r) when r == 1.0` appear before `case Circle(double r)`?

*Answer:* The unguarded `Circle` branch matches every `Circle`, so placing it first shadows the branch that handles only radius `1.0`. Java reports a dominance error at compile time.

**Exercise 4.** How do `kind(null)` and `area(null)` differ in the example?

*Answer:* `kind(null)` returns `missing` via `case null`; `area(null)` intentionally throws `NullPointerException` via `Objects.requireNonNull(shape, "shape")`. They represent two distinct domain contracts.

**Exercise 5.** Why is `Math.hypot(legA, legB)` used for `RightTriangle`?

*Answer:* The record's two fields are the two legs forming the right angle, so the hypotenuse is `sqrt(a² + b²)`; `Math.hypot` computes it more reliably across edge cases than squaring manually.

**Exercise 6.** In `area`, should you add `default -> 0` to avoid editing code when a new shape is added?

*Answer:* No, if the model is a closed domain and every shape must have a real formula. A broad `default` hides omitted subtypes; adding explicit cases lets the compiler and tests catch missing behavior.

**Exercise 7.** JDK 17 already has `sealed` and `record`; can this program run as-is on JDK 17?

*Answer:* No. The program uses **record patterns**, **pattern switch**, and `when` guards, which became final in Java 21. If a project must stay on Java 17, implement calculations with polymorphism or `instanceof` type patterns and accessors instead of copying Java 21 syntax directly.

**Exercise 8.** If a circle has radius `1e308` and the constructor checks only `isFinite` and positive, is it safe to compute its area?

*Answer:* Not guaranteed. The radius is finite, but `r * r` overflows `double` to `Infinity`. A real domain needs range bounds or an appropriate arithmetic policy and overflow tests.

## 15. Official documentation

- [JEP 409 – Sealed Classes (final in Java 17)](https://openjdk.org/jeps/409)
- [JEP 395 – Records (final in Java 16)](https://openjdk.org/jeps/395)
- [JEP 440 – Record Patterns (final in Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 – Pattern Matching for switch (final in Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 – Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html)
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS Java 21 `8.1.1.2 – sealed/final/non-sealed class modifiers`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2)
- [JLS Java 21 `9.1.1.4 – sealed interfaces`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4)
- [JLS Java 21 `14.11 – Switch statement`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
