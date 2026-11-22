# Using Guards for Conditional Shapes in Java 21

## 1. Objectives and Context

In the **Geometry Case Study**, we do not always only need to classify a value as a circle, a rectangle, or a triangle. Many requirements also depend on **geometric conditions**: the radius must be positive, whether a rectangle is a square or a wide rectangle, whether three sides form a valid triangle, whether a triangle is equilateral/isosceles/scalene, or whether numeric values are finite.

Java 21 supports pattern matching for `switch` with **`when` guards**. A guard lets you express “the object has this structure **and** satisfies an additional condition” in a single clear `case`. When combined with a **sealed hierarchy**, **record patterns**, and a sensible `case` order, the code can be both type-safe and easy to review.

After this lesson, you will be able to:

- Use `case Circle(double radius) when ...`, `case Rectangle(double width, double height) when ...`, and `case Triangle(double a, double b, double c) when ...` in a Java 21 `switch expression`.
- Separate **type/structure matching** from **guard truth/falsity**; understand that a guard is evaluated only after the pattern matches.
- Order conditions from **validity checks → special cases → general cases**, avoiding dominated branches (*dominance*) or incorrect fallbacks.
- Clearly define the handling of `null`, negative/zero dimensions, `NaN`, `Infinity`, shape aspect ratios, triangle conditions, and numeric boundaries.
- Compile and run a standalone Java 21 example with three shape types and **22 test cases** compared against independent expected values, while also knowing how to check invalid compile-time patterns.
- Distinguish guards in `switch` from `instanceof` combined with `&&` and from named business methods.

**Version:** `switch` pattern matching and record patterns are standard in **Java 21** (JEP 441, JEP 440), without needing `--enable-preview`. The type pattern `instanceof T t` has been standard since Java 16 (JEP 394); do not use `when` after `instanceof`.

## 2. Geometry Model and Classification Contract

Define a closed geometry hierarchy:

```java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record Triangle(double a, double b, double c) implements Shape {}
```

This is an **illustrative declaration**; in the complete program in Section 6, the types are placed inside a public class so only a single Java file is needed.

- `sealed Shape` restricts the permitted direct subtypes: `Circle`, `Rectangle`, `Triangle`.
- `record` automatically generates the constructor, component accessors, and basic value behavior; **the default record constructor does not automatically validate geometric validity**.
- `double` can accept `NaN` or infinity; `new Circle(-2.0)` or `new Triangle(1, 2, 3)` **can still be constructed** in this model.
- Therefore, a shape having the **right Java type** does not automatically mean the shape is **geometrically valid**.

Assumed classification policy for this lesson:

| Type | Condition | Returned Label |
|---|---|---|
| No shape | `shape == null` | `MISSING` |
| Circle | Radius is not a positive finite number | `INVALID_CIRCLE` |
| Circle | Radius is positive finite and `radius >= 10` | `LARGE_CIRCLE` |
| Circle | Radius is positive finite and under 10 | `CIRCLE` |
| Rectangle | Width or height is not positive finite | `INVALID_RECTANGLE` |
| Rectangle | Both sides valid, `width == height` | `SQUARE` |
| Rectangle | Valid, not square, `width / height >= 2` | `WIDE_RECTANGLE` |
| Rectangle | Valid, not in the two groups above | `RECTANGLE` |
| Triangle | Side is not positive finite or violates strict triangle inequality | `INVALID_TRIANGLE` |
| Triangle | Valid and `a == b == c` | `EQUILATERAL_TRIANGLE` |
| Triangle | Valid, at least two sides equal | `ISOSCELES_TRIANGLE` |
| Triangle | Valid, all three sides different | `SCALENE_TRIANGLE` |

These are **demo rules**, not a universal standard required for every geometry library. For example, the “large circle” threshold of 10 is an assumption; a real project must define its own measurement units, tolerance, and precision.

The goal of this case study is to make clear that **guards can refine a single record type into multiple conditional branches** without needing to create subtypes for every case such as `Square`, `WideRectangle`, or `InvalidCircle`.

## 3. Guard Syntax in switch

A guarded case has the form:

```java
case Pattern p when booleanExpression -> result;
```

For example:

```java
case Circle(double radius) when radius >= 10.0 -> "LARGE_CIRCLE";
```

**Execution order:**

1. The `switch` selector is evaluated.
2. The pattern `Circle(double radius)` is checked: is the object a Circle (non-null) and can the `radius` component be deconstructed?
3. If the pattern matches, the variable `radius` is in scope within the `when` guard expression.
4. If the guard `radius >= 10.0` returns `true`, the branch is selected; if `false`, the subsequent cases are evaluated.
5. If the pattern does not match, the guard is **not evaluated**.

You should think of a guarded case as **“pattern match AND guard true”**, where the guard and the pattern are **two stages**. This helps distinguish a shape of the right type that fails a condition from a shape of the wrong type altogether.

Example:

```java
return switch (shape) {
    case null -> "MISSING";
    case Circle(double radius) when radius >= 10.0 -> "LARGE_CIRCLE";
    case Circle(double radius) -> "CIRCLE";
    // Other Shape types also need to be handled if the switch expression
    // must be exhaustive, such as Rectangle and Triangle.
};
```

**This snippet is intentionally non-exhaustive** if `Shape` still includes Rectangle/Triangle, so it must not be used as a standalone runnable program. The program in Section 6 provides all required branches and has been compiled.

## 4. Defining Safe Geometric Predicates

### 4.1. Positive Finite Numbers

A valid dimension in this demo must satisfy:

```java
static boolean positiveFinite(double value) {
    return Double.isFinite(value) && value > 0.0;
}
```

Explanation:

- `Double.isFinite(value)` excludes `NaN`, `Double.POSITIVE_INFINITY`, and `Double.NEGATIVE_INFINITY`.
- `value > 0.0` excludes `0.0`, `-0.0`, and negative values.
- A comparison like `value <= 0.0` **cannot detect `NaN`**, because ordering comparisons with NaN return false.
- Real-world measurement systems may also want to constrain maximum values or units; apply additional checks at the boundary if required.

Without checking `isFinite`, for instance, `Double.POSITIVE_INFINITY >= 10.0` returns true, and an infinite radius could be labeled `LARGE_CIRCLE` even though the policy states that only finite radii are accepted.

### 4.2. Triangle Inequality

For three sides `a`, `b`, `c`, check:

```java
static boolean validTriangle(double a, double b, double c) {
    return positiveFinite(a) && positiveFinite(b) && positiveFinite(c)
            && a + b > c && a + c > b && b + c > a;
}
```

The conditions are **strict**: `1, 2, 3` does not form a triangle with positive area; degenerate cases are treated as invalid.

Because Java uses `double`, remember that addition can be affected by rounding or overflow to infinity in extreme cases. For **real-world measurement data**, a precision/tolerance policy is needed, and you may use a more numerically analyzed check or an appropriate decimal representation. This lesson only tests representative values and does not claim to solve every computational geometry problem.

A triangle-condition guard can be written as:

```java
case Triangle(double a, double b, double c)
        when !validTriangle(a, b, c) -> "INVALID_TRIANGLE";
```

Extracting a named method keeps the code concise **because the intent is clearer**, rather than cramming six comparisons into a single `when`.

### 4.3. Squares and Wide Rectangles

For a valid Rectangle:

```java
case Rectangle(double width, double height)
        when width == height -> "SQUARE";
case Rectangle(double width, double height)
        when width / height >= 2.0 -> "WIDE_RECTANGLE";
case Rectangle(double width, double height) -> "RECTANGLE";
```

**Policy-driven ordering:**

- The condition `width == height` is checked first to identify SQUARE.
- The “wide” condition uses a **width-to-height ratio of 2 or greater**; at `width=4`, `height=2`, the label is WIDE_RECTANGLE.
- The unguarded branch is the fallback for remaining valid Rectangles, such as `3×2` or `2×5`.

The ratio is evaluated only **after** the INVALID_RECTANGLE branch in the full program, so `height > 0` and finite. This avoids division by 0 and reduces the risk of feeding invalid data into classification. However, `double` division can still produce Infinity if the ratio is too large even when both dimensions are finite; if the domain requires avoiding ratio overflow, a dedicated numeric policy is needed.

It should also be clarified: `width == height` is an **exact** `double` comparison, appropriate for literal numbers in the demo. For measured or computed numbers, whether to use exact equality or approximate equality must be specified by the domain; do not attach an arbitrary epsilon on your own.

## 5. Designing Case Order for Clear Conditions

A guarded switch is not just syntax. It expresses **a priority order**. A useful order for each shape type is:

1. **Check whether the shape has valid data** to classify invalid cases first.
2. **Handle the narrowest special cases** such as large circle, square, and equilateral triangle.
3. **Handle less specific cases** such as wide rectangle or isosceles triangle.
4. **An unguarded branch of the same type** catches all remaining cases.
5. **Do not add an unnecessary `default`** if the sealed hierarchy is already handled exhaustively.

Example for Circle:

```java
case Circle(double radius) when !positiveFinite(radius)
        -> "INVALID_CIRCLE";
case Circle(double radius) when radius >= 10.0
        -> "LARGE_CIRCLE";
case Circle(double radius) -> "CIRCLE";
```

If you move `case Circle(double radius) -> "CIRCLE";` earlier, the guarded Circle branches below it become **dominated** under Java 21 rules and will prevent the code from compiling. The compiler helps catch this basic ordering mistake.

For Triangle, the order also protects the meaning:

```java
case Triangle(double a, double b, double c)
        when !validTriangle(a, b, c) -> "INVALID_TRIANGLE";
case Triangle(double a, double b, double c)
        when a == b && b == c -> "EQUILATERAL_TRIANGLE";
case Triangle(double a, double b, double c)
        when a == b || b == c || a == c -> "ISOSCELES_TRIANGLE";
case Triangle(double a, double b, double c)
        -> "SCALENE_TRIANGLE";
```

An equilateral triangle also satisfies “at least two sides equal”. If the isosceles branch is checked first, an equilateral triangle will be labeled isosceles, even though the program still compiles: **the compiler does not prove the full algebraic relationship between these two guards to force an error**. Therefore, **business tests and code review** remain essential.

## 6. Standalone, Verified Java 21 Program

Save the entire code as **`GeometryGuardDemo.java`**. The lesson uses a sealed interface and three records nested inside a public class. No external libraries are needed.

```java
import java.util.Objects;

public class GeometryGuardDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}
    record Circle(double radius) implements Shape {}
    record Rectangle(double width, double height) implements Shape {}
    record Triangle(double a, double b, double c) implements Shape {}

    static boolean positiveFinite(double value) {
        return Double.isFinite(value) && value > 0.0;
    }

    static boolean validTriangle(double a, double b, double c) {
        return positiveFinite(a) && positiveFinite(b) && positiveFinite(c)
                && a + b > c && a + c > b && b + c > a;
    }

    static String classify(Shape shape) {
        return switch (shape) {
            case null -> "MISSING";

            case Circle(double radius) when !positiveFinite(radius)
                    -> "INVALID_CIRCLE";
            case Circle(double radius) when radius >= 10.0
                    -> "LARGE_CIRCLE";
            case Circle(double radius) -> "CIRCLE";

            case Rectangle(double width, double height)
                    when !positiveFinite(width) || !positiveFinite(height)
                    -> "INVALID_RECTANGLE";
            case Rectangle(double width, double height)
                    when width == height -> "SQUARE";
            case Rectangle(double width, double height)
                    when width / height >= 2.0 -> "WIDE_RECTANGLE";
            case Rectangle(double width, double height) -> "RECTANGLE";

            case Triangle(double a, double b, double c)
                    when !validTriangle(a, b, c) -> "INVALID_TRIANGLE";
            case Triangle(double a, double b, double c)
                    when a == b && b == c -> "EQUILATERAL_TRIANGLE";
            case Triangle(double a, double b, double c)
                    when a == b || b == c || a == c -> "ISOSCELES_TRIANGLE";
            case Triangle(double a, double b, double c)
                    -> "SCALENE_TRIANGLE";
        };
    }

    // Comparison if/else: does not use guarded switch, but still uses
    // instanceof type patterns to obtain properly typed variables.
    static String withoutPatterns(Shape shape) {
        if (shape == null) return "MISSING";
        if (shape instanceof Circle circle) {
            double radius = circle.radius();
            if (!positiveFinite(radius)) return "INVALID_CIRCLE";
            if (radius >= 10.0) return "LARGE_CIRCLE";
            return "CIRCLE";
        }
        if (shape instanceof Rectangle rectangle) {
            double width = rectangle.width();
            double height = rectangle.height();
            if (!positiveFinite(width) || !positiveFinite(height)) {
                return "INVALID_RECTANGLE";
            }
            if (width == height) return "SQUARE";
            if (width / height >= 2.0) return "WIDE_RECTANGLE";
            return "RECTANGLE";
        }
        Triangle triangle = (Triangle) shape;
        double a = triangle.a();
        double b = triangle.b();
        double c = triangle.c();
        if (!validTriangle(a, b, c)) return "INVALID_TRIANGLE";
        if (a == b && b == c) return "EQUILATERAL_TRIANGLE";
        if (a == b || b == c || a == c) return "ISOSCELES_TRIANGLE";
        return "SCALENE_TRIANGLE";
    }

    static void test(String label, Shape shape, String expected) {
        String actual = classify(shape);
        String oldStyle = withoutPatterns(shape);
        if (!Objects.equals(expected, actual)
                || !Objects.equals(expected, oldStyle)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", guard=" + actual + ", ordinary=" + oldStyle);
        }
        System.out.println(label + " => " + actual);
    }

    public static void main(String[] args) {
        test("null", null, "MISSING");
        test("circle zero", new Circle(0.0), "INVALID_CIRCLE");
        test("circle negative", new Circle(-1.0), "INVALID_CIRCLE");
        test("circle NaN", new Circle(Double.NaN), "INVALID_CIRCLE");
        test("circle infinity", new Circle(Double.POSITIVE_INFINITY),
                "INVALID_CIRCLE");
        test("circle small", new Circle(9.5), "CIRCLE");
        test("circle threshold", new Circle(10.0), "LARGE_CIRCLE");
        test("circle large", new Circle(12.0), "LARGE_CIRCLE");

        test("rectangle zero", new Rectangle(0.0, 2.0),
                "INVALID_RECTANGLE");
        test("rectangle NaN", new Rectangle(2.0, Double.NaN),
                "INVALID_RECTANGLE");
        test("rectangle square", new Rectangle(3.0, 3.0), "SQUARE");
        test("rectangle wide boundary", new Rectangle(4.0, 2.0),
                "WIDE_RECTANGLE");
        test("rectangle wide", new Rectangle(5.0, 2.0),
                "WIDE_RECTANGLE");
        test("rectangle ordinary", new Rectangle(3.0, 2.0), "RECTANGLE");
        test("rectangle tall", new Rectangle(2.0, 5.0), "RECTANGLE");

        test("triangle degenerate", new Triangle(1.0, 2.0, 3.0),
                "INVALID_TRIANGLE");
        test("triangle negative", new Triangle(-3.0, 4.0, 5.0),
                "INVALID_TRIANGLE");
        test("triangle infinity",
                new Triangle(Double.POSITIVE_INFINITY, 3.0, 3.0),
                "INVALID_TRIANGLE");
        test("triangle equilateral", new Triangle(3.0, 3.0, 3.0),
                "EQUILATERAL_TRIANGLE");
        test("triangle isosceles", new Triangle(4.0, 4.0, 5.0),
                "ISOSCELES_TRIANGLE");
        test("triangle scalene", new Triangle(3.0, 4.0, 5.0),
                "SCALENE_TRIANGLE");
        test("triangle NaN", new Triangle(Double.NaN, 2.0, 3.0),
                "INVALID_TRIANGLE");
    }
}
```

In the method named `withoutPatterns`, “without patterns” means **without record patterns with `when` in `switch`**; it **still uses `instanceof` type patterns** for Circle/Rectangle and a manual cast for Triangle. The method name is kept here to match the test run output; if moved to production, it should be given a clearer name, such as `classifyImperatively`.

### How to Run

With JDK 21 or later:

```bash
javac --release 21 GeometryGuardDemo.java
java GeometryGuardDemo
```

**Verified exact stdout:**

```text
null => MISSING
circle zero => INVALID_CIRCLE
circle negative => INVALID_CIRCLE
circle NaN => INVALID_CIRCLE
circle infinity => INVALID_CIRCLE
circle small => CIRCLE
circle threshold => LARGE_CIRCLE
circle large => LARGE_CIRCLE
rectangle zero => INVALID_RECTANGLE
rectangle NaN => INVALID_RECTANGLE
rectangle square => SQUARE
rectangle wide boundary => WIDE_RECTANGLE
rectangle wide => WIDE_RECTANGLE
rectangle ordinary => RECTANGLE
rectangle tall => RECTANGLE
triangle degenerate => INVALID_TRIANGLE
triangle negative => INVALID_TRIANGLE
triangle infinity => INVALID_TRIANGLE
triangle equilateral => EQUILATERAL_TRIANGLE
triangle isosceles => ISOSCELES_TRIANGLE
triangle scalene => SCALENE_TRIANGLE
triangle NaN => INVALID_TRIANGLE
```

There are **22 test cases** in total. Each check simultaneously compares:

1. The guarded switch result `classify(shape)`.
2. The comparison if/else result `withoutPatterns(shape)`.
3. An expected string **explicitly written from the classification contract**, rather than only comparing two implementations against each other.

If any of the three disagrees, the program throws `AssertionError`. This lets you evaluate **behavioral equivalence** between the guarded switch and sequential classification, but does not claim to cover all floating-point numbers or input variants in a real application.

## 7. Reading Each Result in Guard Order

### 7.1. Circle: Check Invalidity Before Large Size

Consider:

```java
case Circle(double radius) when !positiveFinite(radius)
        -> "INVALID_CIRCLE";
case Circle(double radius) when radius >= 10.0
        -> "LARGE_CIRCLE";
case Circle(double radius) -> "CIRCLE";
```

- `Circle(0.0)` and `Circle(-1.0)`: invalid guard is true → `INVALID_CIRCLE`.
- `Circle(Double.NaN)`: `Double.isFinite` is false → `INVALID_CIRCLE`. If you omit the finiteness check and only use `radius <= 0`, NaN **is not recognized as less than or equal to 0**.
- `Circle(Double.POSITIVE_INFINITY)`: rejected before checking `radius >= 10`.
- `Circle(9.5)`: valid, not large → `CIRCLE`.
- `Circle(10.0)`: right at the boundary and recognized as `LARGE_CIRCLE`.

This is why the test suite needs **below threshold**, **at threshold**, **above threshold**, **NaN**, and **Infinity**. If you only tested radii 5 and 12, you would not catch a bug where the author replaced `>= 10` with `> 10`.

### 7.2. Rectangle: Invalid, Square, Wide, Ordinary

Consider:

```java
case Rectangle(double width, double height)
        when !positiveFinite(width) || !positiveFinite(height)
        -> "INVALID_RECTANGLE";
case Rectangle(double width, double height)
        when width == height -> "SQUARE";
case Rectangle(double width, double height)
        when width / height >= 2.0 -> "WIDE_RECTANGLE";
case Rectangle(double width, double height) -> "RECTANGLE";
```

- `Rectangle(0, 2)`: invalid; prevents classification as a valid rectangle.
- `Rectangle(3, 3)`: square; the wide guard is not evaluated after this branch is chosen.
- `Rectangle(4, 2)`: ratio is exactly 2 → wide, because the policy uses `>= 2.0`.
- `Rectangle(5, 2)`: wide.
- `Rectangle(3, 2)`: ordinary, ratio 1.5.
- `Rectangle(2, 5)`: ordinary, because the wide policy depends on **width/height**, not on whichever side is longer.

**Orientation policy:** “wide” means the width is at least twice the height. If the domain wants to check the ratio of the longest side to the shortest side, you must rewrite the predicate and add tests for tall shapes; **that is a business-rule change**, not just guard formatting.

### 7.3. Triangle: Invalid First, Equilateral Before Isosceles

Consider:

```java
case Triangle(double a, double b, double c)
        when !validTriangle(a, b, c) -> "INVALID_TRIANGLE";
case Triangle(double a, double b, double c)
        when a == b && b == c -> "EQUILATERAL_TRIANGLE";
case Triangle(double a, double b, double c)
        when a == b || b == c || a == c -> "ISOSCELES_TRIANGLE";
case Triangle(double a, double b, double c) -> "SCALENE_TRIANGLE";
```

- `Triangle(1,2,3)`: degenerate because `1 + 2 == 3`; does not satisfy the strict `>` condition.
- `Triangle(3,3,3)`: equilateral, so EQUILATERAL is chosen first.
- `Triangle(4,4,5)`: isosceles but not equilateral.
- `Triangle(3,4,5)`: scalene.
- Negative sides, NaN, Infinity: invalid even though all three variables have a valid `double` type as far as Java is concerned.

**Easy mistake:** the “two sides equal” condition is **also true for an equilateral triangle**. If you place the isosceles guarded case before the equilateral case, Java generally will not report dominance for the logical relationship between the two guards; the bug shows up in the **classification result**. This is why testing `Triangle(3,3,3)` is critical.

## 8. How Do Guards in switch Differ from && with instanceof?

In Java 21 `switch`:

```java
case Rectangle(double width, double height)
        when width == height -> "SQUARE";
```

Here `when` connects the **case label's pattern** with a boolean condition. Using `when` lets you evaluate multiple cases for the same record type inside one `switch`.

When using `instanceof`, you do not write `when` after the pattern. The valid form is:

```java
if (shape instanceof Rectangle(double width, double height)
        && width == height) {
    System.out.println("square");
}
```

**Intentionally invalid** form:

```java
// Invalid in Java 21:
if (shape instanceof Rectangle(double width, double height)
        when width == height) {
    System.out.println("square");
}
```

`javac --release 21` **rejects** `when` syntax in an `instanceof` expression; in Java 21, `when` is the guard for a `case` pattern in `switch`.

At the same time, `&&` has short-circuit behavior: if the `Rectangle(...)` pattern does not match, the right-hand side is not executed and the pattern variables cannot be used out of scope. If the right-hand side is a call that might throw an exception, keep the necessary non-null or validity guard before that call.

**Difference in purpose:** `instanceof` fits a single simple conditional check. A guarded `switch` fits when there are **multiple cases for the same type with different conditions**, or multiple variants in a sealed hierarchy.

## 9. Why Is There No default in the Full Program?

`Shape` is a `sealed interface` permitting only three direct subtypes: Circle, Rectangle, and Triangle. In the `switch expression` in Section 6, we have:

- `case null` to state the null-selector policy explicitly.
- Guarded cases and **one final unguarded record pattern** for each subtype.
- No catch-all `default`.

The compiler can prove that the unguarded record patterns cover all non-null values of the three subtypes with primitive components. When you **add a new permitted subtype** such as `Polygon` and recompile, the compiler can require you to add handling for the new type.

If you add:

```java
default -> "UNKNOWN";
```

unnecessarily, you can lose the benefit of **exhaustiveness checking**: a new shape type could silently fall into the UNKNOWN branch. Using `default` is appropriate when the domain **deliberately defines a fallback** for an open set of types, such as a selector of type `Object` or an API receiving inputs outside the geometry domain.

**Note:** record patterns in Java 21 have rules around null components and exhaustiveness that should not be guessed mechanically. This example uses primitive `double` components for simplicity. If a record contains a nested reference record, a nested pattern may fail to match when that component is null, even though the root object belongs to that subtype; a corresponding fallback is needed.

### Null in Pattern switch

A `null` selector does **not** automatically enter an ordinary `default`. Because the demo policy wants to return `MISSING`, it declares:

```java
case null -> "MISSING";
```

Contrast this with `shape instanceof Circle c`: if `shape == null`, `instanceof` returns false. Null in `switch` and `instanceof` should not be treated as having the same syntax.

## 10. Errors the Java Compiler Can Catch

### 10.1. Placing a General Case Before a Guarded Case

**Wrong:**

```java
return switch (shape) {
    case Rectangle rectangle -> "ANY";
    case Rectangle(double width, double height)
            when width == height -> "SQUARE";
    // Other branches...
};
```

This structure is shown to illustrate ordering, **not as a complete switch expression**. `javac --release 21` rejects the SQUARE branch because `case Rectangle rectangle` already covers every non-null Rectangle: the guarded case after it is a **dominated case label**.

**Fix:** place narrow/guarded branches first, and the unguarded `case Rectangle...` last. The complete example in Section 6 demonstrates this order.

### 10.2. Missing an Exhaustive Branch

If you only handle Circle and Rectangle and forget Triangle in a `switch expression` over `Shape`, the compiler can report that the expression is not exhaustive. Do not use `default` just to make the build pass; add the Triangle branch according to policy.

### 10.3. Using the Wrong Component Pattern Type

If `record Circle(double radius)`, the pattern `Circle(String radius)` is not applicable to the `double` component. That is a **compile-time error**, not “the current Circle doesn't match String” at runtime.

### 10.4. Using a Pattern Variable Outside Its Binding Scope

The `width` variable of `case Rectangle(double width, double height)` is only in scope within its guard and the body of the selected branch. You cannot arbitrarily use it in a Circle case or after the switch as a previously declared local variable.

### 10.5. Using a Java Version Lower Than 21

`when` guards in pattern `switch` and record patterns as shown here were standardized in Java 21. If a project builds with `--release 17` without enabling the corresponding preview features, the example will not compile. Do not confuse this syntax with the `instanceof` type pattern that became standard in Java 16.

## 11. Business Mistakes the Compiler Cannot Catch Automatically

### 11.1. Placing the Validity Guard After the Size Condition

`Double.POSITIVE_INFINITY >= 10.0` is true. If you check LARGE_CIRCLE before INVALID_CIRCLE, a circle with an infinite radius is misclassified.

Prevention: **validity guard first, threshold guard second**; include NaN/Infinity tests.

### 11.2. Changing >= to >

For `Circle(10.0)` or `Rectangle(4.0,2.0)`, changing `>=` to `>` changes the label. Boundary values must appear in independent tests, rather than testing only “clearly large” and “clearly small” examples.

### 11.3. Detecting Isosceles Before Equilateral

When using `a == b || b == c || a == c` before `a == b && b == c`, an equilateral triangle can be classified as isosceles. Because guards are boolean expressions carrying business meaning, the compiler cannot replace code review and tests to infer the intended order.

### 11.4. Forgetting the Difference Between Floating-Point and Integers

`double` does not mean “exact length”. Equality comparisons can be affected by measured data or arithmetic operations. If the policy requires “nearly square”, name and define an `approximatelyEqual` predicate with a tolerance based on scale and domain data, and test around the boundary. Do not replace `==` with an arbitrary epsilon without defining the requirement.

### 11.5. Overusing Long Guards

A guard with too much logic becomes hard to read, test, and maintain. `validTriangle(a,b,c)` is an example of extracting a **named rule**. However, you should also avoid splitting every single comparison operator into a pointless one-line helper; the goal is to clarify intent.

### 11.6. Putting Side Effects in Guards

For example, `when chargeCreditCard() && ...` or `when logAndChangeState(...)` can make behavior depend on evaluation order, how many cases are tested, and exceptions. Guards should be **pure, short, and predictable** whenever possible. If an operation genuinely mutates state, make it explicit in the branch body or an appropriate service.

### 11.7. Confusing “Guard Did Not Match” with “Wrong Shape Type”

`Rectangle(3,2)` is a valid Rectangle that does not satisfy the square or wide guard, so the general RECTANGLE branch is chosen. This is **correct behavior**, not a failed record pattern match. When debugging, distinguish between *root type match* and *guard false*.

## 12. Comparing if/else and Guarded switch

In Section 6, the comparison method uses:

```java
if (shape instanceof Circle circle) {
    double radius = circle.radius();
    if (!positiveFinite(radius)) return "INVALID_CIRCLE";
    if (radius >= 10.0) return "LARGE_CIRCLE";
    return "CIRCLE";
}
```

This is an excerpt from the comparison method: it **still uses an `instanceof` type pattern**, just without a guarded switch or record deconstruction. It fits well when handling only one type with a few conditions, or when targeting a different source level.

A guarded switch:

```java
case Circle(double radius) when !positiveFinite(radius)
        -> "INVALID_CIRCLE";
case Circle(double radius) when radius >= 10.0
        -> "LARGE_CIRCLE";
case Circle(double radius) -> "CIRCLE";
```

fits well when a closed set of shapes has multiple types and each type has sub-cases. The value lies not in having fewer lines, but in that:

- Shape branches read like a **decision table**.
- The compiler guarantees the types of variables inside each guard.
- Manual casts can be eliminated.
- With a sealed hierarchy and an unguarded fallback for each subtype, you can leverage exhaustiveness checking.
- Each branch can be tested with independent inputs and expected values.

However, when guards become long and deeply nested, a domain method like `rectangle.isSquare()` or `triangle.isValid()` is sometimes easier to understand. Do not use `switch` merely to shorten code.

## 13. Test Matrix by Condition Type

To help reviewers clearly see “which condition causes which branch to be selected”, maintain a test matrix:

| Case | Input | Expected Label | Purpose |
|---|---|---|---|
| Null root | `null` | MISSING | `case null` |
| Circle zero | `Circle(0)` | INVALID_CIRCLE | Zero-value boundary |
| Circle NaN | `Circle(NaN)` | INVALID_CIRCLE | Invalid number classification |
| Circle Infinity | `Circle(+Inf)` | INVALID_CIRCLE | Prevent false threshold guard match |
| Circle small | `Circle(9.5)` | CIRCLE | Below threshold |
| Circle threshold | `Circle(10)` | LARGE_CIRCLE | `>=` includes boundary point |
| Rectangle zero | `Rectangle(0,2)` | INVALID_RECTANGLE | Dimension-checking guard |
| Rectangle square | `Rectangle(3,3)` | SQUARE | Square guard first |
| Rectangle wide boundary | `Rectangle(4,2)` | WIDE_RECTANGLE | Ratio equals exactly 2 |
| Rectangle ordinary | `Rectangle(3,2)` | RECTANGLE | Unguarded branch |
| Rectangle tall | `Rectangle(2,5)` | RECTANGLE | Width/height orientation |
| Triangle degenerate | `Triangle(1,2,3)` | INVALID_TRIANGLE | Strict inequality |
| Triangle equilateral | `Triangle(3,3,3)` | EQUILATERAL_TRIANGLE | Equilateral priority |
| Triangle isosceles | `Triangle(4,4,5)` | ISOSCELES_TRIANGLE | Isosceles but not equilateral |
| Triangle scalene | `Triangle(3,4,5)` | SCALENE_TRIANGLE | Remaining valid case |

The program in Section 6 includes additional negative/NaN/Infinity/normal cases for a total of 22. **A test suite never replaces defining the numeric policy**, but named boundary cases make guard bugs easier to spot.

### Automated Testing Suggestions in a Project

With JUnit 5, each input can be passed into a `@ParameterizedTest` along with an expected label. Include assertions that invalid data does not throw unexpected exceptions. You should also test adding a new subtype if your team owns the sealed hierarchy, to protect your use of exhaustive `switch`.

Do not only compare two implementations against each other: both could share the same logic bug. The program uses **independent expected values** to avoid that risk.

## 14. Guard Review Checklist for Geometry

1. **Shapes and types:** What interface/class/record is the selector? Is Java 21 used properly for record patterns and guards?
2. **Root null:** Should it be handled explicitly or throw an exception? If handled explicitly, declare `case null`.
3. **Validation:** Are dimensions positive finite? Are NaN, Infinity, 0, and negative values blocked?
4. **Ordering:** Invalid before special, special before general; equilateral Triangle before isosceles Triangle.
5. **Short-circuiting:** Are safety conditions checked before dividing or calling methods?
6. **Boundaries:** Do `>=`, `>`, and `==` match the policy at threshold points?
7. **Exhaustiveness:** Does the sealed hierarchy have an unguarded case for every subtype? Are redundant `default` branches avoided so new variants are not hidden?
8. **Dominated branches:** Are general cases placed after guarded cases?
9. **Precision:** Have `double` units and tolerance been specified?
10. **Purity:** Do guards avoid side effects, sensitive logging, exceptions, or unnecessary external data access?
11. **Readability:** Are complex predicates given clear names like `validTriangle`?
12. **Tests:** Are valid/invalid, NaN/Infinity, both sides of thresholds, degenerate data, and unguarded fallbacks all covered?
13. **Version:** Is the code compiled and run with the right `javac --release 21` and JVM?
14. **Change review:** Was any geometric policy accidentally altered when refactoring from `if/else` to `switch`?

## 15. Self-Check Exercises

### Exercise A — Radius Boundary

Predict the results for:

```java
new Circle(9.99)
new Circle(10.0)
new Circle(Double.NaN)
```

**Answer:** CIRCLE, LARGE_CIRCLE, and INVALID_CIRCLE, respectively. The threshold uses `>=`; NaN is caught by `isFinite` first.

### Exercise B — Triangle Order

Someone writes:

```java
case Triangle(double a, double b, double c)
        when a == b || b == c || a == c -> "ISOSCELES_TRIANGLE";
case Triangle(double a, double b, double c)
        when a == b && b == c -> "EQUILATERAL_TRIANGLE";
```

The program compiles, but how does it classify `Triangle(3,3,3)`?

**Answer:** ISOSCELES_TRIANGLE because the first branch's guard evaluates to true and is selected. The two branches must be swapped, and a validation guard must be placed before both so invalid triangles are not accepted.

### Exercise C — Rectangle at Ratio Boundary

If the input is `Rectangle(4,2)`, what is the output?

**Answer:** WIDE_RECTANGLE; `4 / 2 == 2` and the policy is `>= 2.0`. For `Rectangle(2,4)`, the output is RECTANGLE because width/height is only 0.5.

### Exercise D — Wrong Place to Use when

Someone writes:

```java
if (shape instanceof Circle(double radius) when radius >= 10) {
    // ...
}
```

Is this valid in Java 21?

**Answer:** No. `when` can only be used in a guarded `case` of a pattern `switch`, not as an operator in `instanceof`. Use:

```java
if (shape instanceof Circle(double radius) && radius >= 10) {
    // ...
}
```

### Exercise E — Dominated Case

Why can you not place `case Rectangle r -> ...` before `case Rectangle(double w, double h) when w == h -> ...`?

**Answer:** The general Rectangle case covers every non-null Rectangle, making the later branch unreachable; Java 21 reports a dominated case label.

### Exercise F — Adding a New Shape

If you add `record Polygon(...) implements Shape` and update `permits`, why should you not rush to add `default -> "UNKNOWN"`?

**Answer:** If the domain needs to classify Polygon specifically, `default` can hide the need to update the switch. Add a Polygon case according to the actual policy to preserve exhaustiveness checking.

### Exercise G — Conditions Are Not Just Type Checking

Why does `new Circle(-1)` still compile even though it is classified as INVALID_CIRCLE?

**Answer:** Type checking only confirms that a value is a valid `double` at the language level. The positive-radius requirement is a domain invariant. You can enforce it inside the record constructor if the application wants to **forbid constructing** invalid shapes; however, the test program would then need to change its policy because invalid inputs would throw an exception at construction time.

## 16. Reasonable Extensions in Real Projects

- **Validate in the constructor:** If the domain does not allow invalid shapes to exist, write a compact constructor to check dimensions. Then the INVALID branches may no longer be needed for already-validated internal data, though external inputs still require clear error mapping.
- **Canonical measurement units:** If data arrives from APIs in different units, normalize to a single unit before checking thresholds; do not let `when` guess implicitly.
- **Tolerance for double:** If geometric computations are based on measurements, consider approximate equality with a tolerance suited to scale and business rules, rather than requiring exact binary equality.
- **Extract policy:** Radius thresholds and wide ratios can be configuration parameters instead of hardcoded values across multiple branches.
- **Area/perimeter operations:** Dedicated domain methods can be added; do not cram all calculation formulas and classification logic into one giant guarded switch.
- **Error observability:** Log clear diagnostics such as “invalid dimension” or “degenerate triangle” at the boundary or diagnostic layer if needed, while avoiding side effects in guards.
- **Regression test suite:** When adding a subtype to a sealed hierarchy, recompile and review every exhaustive switch; test each variant.

Keep the distinction clear between three questions: **does Java know the shape's type**, **is the shape valid under the policy**, and **do the classification branches have the right priority**. Guards solve the second and third questions, while pattern matching handles structure and type.

## Conclusion

**Using guards for conditional shapes** is a natural way to express geometric branching in Java 21: the pattern identifies the shape type and binds its components; `when` adds conditions such as positive finite dimensions, radius thresholds, squares, wide-shape ratios, or isosceles/equilateral triangles.

Write cases in the order **invalid → most specific → more specific → same-type fallback**. Keep guards short, use named helpers for geometric conditions, handle `null` explicitly, understand the limits of `double`, and test boundaries. With a sealed hierarchy and unguarded branches covering each type, the compiler also helps track new subtypes instead of hiding them behind an unnecessary `default`.

## Official References

- [JEP 441 — Pattern Matching for switch (JDK 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (JDK 21)](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes (JDK 17)](https://openjdk.org/jeps/409)
- [JEP 394 — Pattern Matching for instanceof (JDK 16)](https://openjdk.org/jeps/394)
- [Java Language Specification SE 21 — Switch Statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
