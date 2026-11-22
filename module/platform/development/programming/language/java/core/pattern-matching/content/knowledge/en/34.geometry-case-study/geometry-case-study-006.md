# Adding a New Subtype and Compiler Feedback — Geometry Case Study (Java 21)

## 1. Real-world problem: one new shape affects many operations

Suppose a geometry application initially only accepts **Circle** and **Rectangle**. The code uses a `sealed interface Shape` and `switch expression`s to calculate area, perimeter, or classify shapes. After some time, the product needs to support **Triangle** as well.

In Java 21, this is a good opportunity to use **compiler feedback** as a maintenance guardrail: when adding a subtype to a sealed hierarchy, pattern `switch`es that do not yet handle the new subtype can **fail at compile time**, instead of silently falling into an unintended branch at runtime.

This lesson follows the entire change cycle:

1. Start with `Shape` having two subtypes: `Circle` and `Rectangle`.
2. Add `Triangle` to `permits` while **intentionally not updating the `switch`es yet**.
3. Read the `javac` diagnostic about **non-exhaustive switch**.
4. Add `case Triangle(...)` branches for area, perimeter, and classification.
5. Read another diagnostic about **case dominance** when guards are ordered incorrectly.
6. Complete the Java 21 program, run **13 test cases**, and evaluate what the compiler guarantees versus what must be covered by business-logic tests.

**Version:** `sealed classes/interfaces` have been standard since Java 17 (JEP 409). **Record patterns** (JEP 440) and **pattern matching for `switch`** (JEP 441) have been standard since **Java 21**, so any example with `case Circle(double r)` or `when` guards requires JDK 21 or later, without `--enable-preview`.

**Goals:** Know how to add a subtype while preserving correct behavior, use compiler diagnostics as a change checklist, write exhaustive pattern `switch`es, recognize dominated-case errors, build tests for the new subtype, and understand the limits of compile-time exhaustiveness.

## 2. Initial model: Shape has only Circle and Rectangle

We choose `record` because these are value objects carrying simple geometric data, and `sealed interface` to control the set of subtypes.

```text
Shape (sealed interface)
├── Circle(radius)           record, final
└── Rectangle(width, height) record, final
```

Concise declarations:

```java
// Illustrative snippet of the model before extension.
// Declarations should be placed in the appropriate matching class/package scope.
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
```

A switch expression to calculate area:

```java
// Illustrative snippet: shape has type Shape inside a method.
return switch (shape) {
    case Circle(double radius) -> Math.PI * radius * radius;
    case Rectangle(double width, double height) -> width * height;
};
```

Together, the two `case`s cover all declared subtypes. Java 21 can prove the `switch` is **exhaustive** without a `default`, because all direct permitted subtypes are records, i.e., `final` types; there are no further extensible subclasses below them.

Similarly, perimeter can be written as:

```java
return switch (shape) {
    case Circle(double r) -> 2.0 * Math.PI * r;
    case Rectangle(double w, double h) -> 2.0 * (w + h);
};
```

**Why is `default` not needed?** In this system, we **want the compiler to warn us with an error** if a new geometric subtype is introduced but an operation has not been updated yet. Omitting `default` is an intentional design decision, not an oversight.

Keep the distinction clear: the compiler only knows which types can appear. It **does not know** whether the formula `Math.PI*r*r` matches business requirements and does not automatically check that radius > 0.

## 3. New requirement: adding a triangle

The product needs a general triangle with three sides `a`, `b`, `c`. We extend the model:

```text
Shape (sealed interface)
├── Circle(radius)
├── Rectangle(width, height)
└── Triangle(a, b, c)   <-- new subtype
```

The first two changes:

```java
// Illustrative snippet of the state AFTER adding the subtype, BEFORE
// updating the switches in existing code.
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record Triangle(double a, double b, double c) implements Shape {}
```

When using an explicit `permits` clause, `Triangle` must be added to the list of direct permitted subtypes. Since `Triangle` is a `record`, it is implicitly `final` and valid as a subtype of a sealed interface.

**Do not immediately patch everything with `default`:** Let your IDE/build run `javac` to reveal every place that relies on the old subtype set. In a domain with many classification methods, these compiler errors serve as a **checklist of places to review**.

Another essential detail: a triangle must have valid data. Any three positive sides **do not necessarily** form a triangle; the necessary condition according to the triangle inequality is:

\[
a+b>c,\qquad a+c>b,\qquad b+c>a.
\]

At the step where we observe compile errors, we can use the simple record declaration above. Before shipping to production, add validation in the constructor; the complete program in section 7 does that.

## 4. Compiler feedback #1: non-exhaustive switch expression

After updating `Shape permits ... Triangle` while **keeping** the area formula for the two old shapes unchanged:

```java
// INTENTIONALLY MISSING Triangle — not complete code.
static double area(Shape shape) {
    return switch (shape) {
        case Circle(double radius) ->
            Math.PI * radius * radius;
        case Rectangle(double width, double height) ->
            width * height;
    };
}
```

To Java 21, `Shape` now has three subtypes that can match. The two `case`s only cover `Circle` and `Rectangle`. When recompiling, `javac` can report:

```text
error: the switch expression does not cover all possible input values
```

This is an **error**, not a warning. The compiler rejects the expression because it needs a result value for every valid selector, yet `Triangle` has no handling branch.

### What the compiler is saying

- `Shape` is the static selector type.
- `Triangle` is a permitted subtype of `Shape`.
- No type/record pattern case in the old switch covers `Triangle`.
- There is no `default` or broad pattern that could accept it.
- Therefore, exhaustiveness cannot be verified.

**Proper fix:** Add a specific case for `Triangle` and compute the area as required. Do not work around it with `default -> 0`, because returning an area of 0 for a valid triangle is a hidden business bug.

### Area formula for Triangle(a, b, c)

Because the record stores **the lengths of three sides** rather than vertex coordinates or height, the appropriate formula is Heron's formula:

\[
s=\frac{a+b+c}{2},\qquad
S=\sqrt{s(s-a)(s-b)(s-c)}.
\]

A case with a block and `yield`:

```java
case Triangle(double a, double b, double c) -> {
    double s = (a + b + c) / 2.0;
    yield Math.sqrt(s * (s - a) * (s - b) * (s - c));
}
```

`yield` returns a value from a block branch of a **switch expression**. It is not a `return` from the enclosing method, and should be distinguished from `break` in a switch statement.

Example of a 3–4–5 triangle:

\[
s=6,\qquad S=\sqrt{6\cdot3\cdot2\cdot1}=6.
\]

**Numerical note:** With extremely large `double` values or nearly degenerate triangles, a naive Heron calculation can suffer from overflow/underflow or loss of precision. The formula here is suitable for teaching pattern matching and testing small inputs; high-precision geometry systems require numerically stable algorithms and well-defined input domains.

## 5. Compiler feedback #2: an enhanced switch statement can also be non-exhaustive

It is not only `switch expression`s that need updating. In Java 21, an **enhanced switch statement** with pattern labels is also required to be exhaustive.

For example, a method that only prints the shape type:

```java
// INTENTIONALLY MISSING Triangle.
static void printShape(Shape shape) {
    switch (shape) {
        case Circle(double r) ->
            System.out.println("circle");
        case Rectangle(double w, double h) ->
            System.out.println("rectangle");
    }
}
```

With the hierarchy after adding `Triangle`, the compiler can report:

```text
error: the switch statement does not cover all possible input values
```

The fix is to add `case Triangle(...)` or an appropriate covering branch according to the contract.

**Important distinction:** Some traditional `switch statement`s using only constant case labels have different rules regarding exhaustiveness. Do not apply the “statements don't need default” reasoning to enhanced switches with pattern labels.

**In a large codebase:** There may be many switches over the same `Shape` across mapping layers, pricing calculations, report formatting, JSON export, UI classification, etc. Each switch has its own semantics. The compile errors after adding a subtype are a signal to **review each operation**, rather than blindly adding `Triangle -> "other"` everywhere.

## 6. Compiler feedback #3: case dominated when guards are ordered incorrectly

The new requirement also wants to classify triangles:
- All three sides equal: `EQUILATERAL`.
- Exactly two sides equal: `ISOSCELES`.
- All three sides different: `TRIANGLE`.

A newcomer might write:

```java
// INTENTIONALLY WRONG ORDER in the same switch:
case Triangle(double a, double b, double c) -> "TRIANGLE";
case Triangle(double a, double b, double c)
    when a == b && b == c -> "EQUILATERAL";
```

The **unguarded** `Triangle` case comes first and already covers every `Triangle`. Thus, the guarded case after it can never be selected. `javac` can emit:

```text
error: this case label is dominated by a preceding case label
```

**How to fix:** Put more specific conditional branches first, and the general branch last:

```java
// Illustrative cases in a switch over Shape:
case Triangle(double a, double b, double c)
    when a == b && b == c -> "EQUILATERAL";
case Triangle(double a, double b, double c)
    when a == b || b == c || a == c -> "ISOSCELES";
case Triangle(double a, double b, double c) -> "TRIANGLE";
```

For an equilateral triangle, the isosceles condition is also true, so **the equilateral case must precede the isosceles case** to produce the desired result. Only when the first guard evaluates to `false` does Java proceed to check subsequent matching cases.

Here the sides are `double` values entered directly such as 2.0, 3.0, 5.0; the `==` comparison illustrates classification by **exact equality**. For geometric measurements obtained from empirical calculations, you must define a tolerance/comparison strategy and write corresponding tests; do not invent an arbitrary epsilon as a substitute for business requirements.

### Dominance is not a “performance error”

A dominated case is an error about **matchability / branch selection order**, not a compiler warning that the code might be slow. Fix it by examining the subsumption relationship of patterns/guards, **not** by casting, preview flags, or suppressing warnings.

## 7. Complete Java 21 program after adding Triangle

Create the file **`GeometrySubtypeEvolutionDemo.java`**. The program below includes:
- A sealed hierarchy with three records.
- Validation for finite positive sides and the triangle inequality.
- `area` and `perimeter` using exhaustive switch expressions without `default`.
- `kind` with three triangle guards/cases and `case null`.
- A small **13-case** test suite based on expected values and expected exceptions.

```java
import java.util.Locale;

public class GeometrySubtypeEvolutionDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    static void requirePositive(String field, double value) {
        if (!Double.isFinite(value) || value <= 0) {
            throw new IllegalArgumentException(
                field + " must be finite and positive");
        }
    }

    record Circle(double radius) implements Shape {
        Circle {
            requirePositive("radius", radius);
        }
    }

    record Rectangle(double width, double height) implements Shape {
        Rectangle {
            requirePositive("width", width);
            requirePositive("height", height);
        }
    }

    record Triangle(double a, double b, double c) implements Shape {
        Triangle {
            requirePositive("a", a);
            requirePositive("b", b);
            requirePositive("c", c);
            if (a + b <= c || a + c <= b || b + c <= a) {
                throw new IllegalArgumentException(
                    "triangle inequality violated");
            }
        }
    }

    static double area(Shape shape) {
        return switch (shape) {
            case Circle(double r) -> Math.PI * r * r;
            case Rectangle(double w, double h) -> w * h;
            case Triangle(double a, double b, double c) -> {
                double s = (a + b + c) / 2.0;
                yield Math.sqrt(s * (s - a) * (s - b) * (s - c));
            }
        };
    }

    static double perimeter(Shape shape) {
        return switch (shape) {
            case Circle(double r) -> 2.0 * Math.PI * r;
            case Rectangle(double w, double h) -> 2.0 * (w + h);
            case Triangle(double a, double b, double c) -> a + b + c;
        };
    }

    static String kind(Shape shape) {
        return switch (shape) {
            case Circle(double r) -> "CIRCLE";
            case Rectangle(double w, double h) -> "RECTANGLE";
            case Triangle(double a, double b, double c)
                when a == b && b == c -> "EQUILATERAL";
            case Triangle(double a, double b, double c)
                when a == b || b == c || a == c -> "ISOSCELES";
            case Triangle(double a, double b, double c) -> "TRIANGLE";
            case null -> "NONE";
        };
    }

    static int passed;

    static void expectClose(String name, double expected, double actual) {
        if (!Double.isFinite(actual)
                || Math.abs(expected - actual) > 1e-9) {
            throw new AssertionError(
                name + ": expected " + expected + ", got " + actual);
        }
        passed++;
        System.out.println("PASS " + name);
    }

    static void expectText(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                name + ": expected " + expected + ", got " + actual);
        }
        passed++;
        System.out.println("PASS " + name);
    }

    static void expectIllegalArgument(String name, Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            passed++;
            System.out.println("PASS " + name);
            return;
        }
        throw new AssertionError(
            name + ": expected IllegalArgumentException");
    }

    static void expectNullPointer(String name, Runnable action) {
        try {
            action.run();
        } catch (NullPointerException expected) {
            passed++;
            System.out.println("PASS " + name);
            return;
        }
        throw new AssertionError(
            name + ": expected NullPointerException");
    }

    public static void main(String[] args) {
        Shape circle = new Circle(2);
        Shape rectangle = new Rectangle(3, 4);
        Shape triangle = new Triangle(3, 4, 5);

        for (Shape s : new Shape[]{circle, rectangle, triangle}) {
            System.out.printf(Locale.ROOT,
                "%s area=%.2f perimeter=%.2f%n",
                kind(s), area(s), perimeter(s));
        }

        System.out.println("equilateral="
            + kind(new Triangle(2, 2, 2)));
        System.out.println("isosceles="
            + kind(new Triangle(2, 2, 3)));
        System.out.println("null=" + kind(null));

        expectClose("circle-area", 4 * Math.PI, area(circle));
        expectClose("circle-perimeter", 4 * Math.PI,
            perimeter(circle));
        expectClose("rectangle-area", 12, area(rectangle));
        expectClose("rectangle-perimeter", 14,
            perimeter(rectangle));
        expectClose("triangle-area", 6, area(triangle));
        expectClose("triangle-perimeter", 12,
            perimeter(triangle));

        expectText("triangle-guard", "TRIANGLE", kind(triangle));
        expectText("equilateral-guard", "EQUILATERAL",
            kind(new Triangle(2, 2, 2)));
        expectText("isosceles-guard", "ISOSCELES",
            kind(new Triangle(2, 2, 3)));
        expectText("null-kind", "NONE", kind(null));

        expectIllegalArgument("invalid-triangle",
            () -> new Triangle(1, 2, 3));
        expectIllegalArgument("invalid-circle",
            () -> new Circle(0));
        expectNullPointer("null-area", () -> area(null));

        System.out.println("TESTS=" + passed);
    }
}
```

Compile and run with JDK 21 or later from the directory containing the file:

```bash
javac --release 21 GeometrySubtypeEvolutionDemo.java
java GeometrySubtypeEvolutionDemo
```

**Exact stdout:**

```text
CIRCLE area=12.57 perimeter=12.57
RECTANGLE area=12.00 perimeter=14.00
TRIANGLE area=6.00 perimeter=12.00
equilateral=EQUILATERAL
isosceles=ISOSCELES
null=NONE
PASS circle-area
PASS circle-perimeter
PASS rectangle-area
PASS rectangle-perimeter
PASS triangle-area
PASS triangle-perimeter
PASS triangle-guard
PASS equilateral-guard
PASS isosceles-guard
PASS null-kind
PASS invalid-triangle
PASS invalid-circle
PASS null-area
TESTS=13
```

The program uses only Java SE, with no JUnit or external dependencies. The `expect...` helpers throw `AssertionError` directly when a result is incorrect, so `java -ea` is not needed.

## 8. Code analysis: where the compiler helps, where tests must help

### 8.1. Area and perimeter: one case per shape

`area(Shape)` and `perimeter(Shape)` both list three record patterns. Once `Triangle` is added to the hierarchy and the corresponding case is added, the compiler verifies coverage. If `Pentagon` is added later, any switches without a branch covering `Pentagon` will fail to compile on rebuild.

**However, ensuring the formula is right is the job of tests.** For example, the compiler will accept this mistake:

```java
// BUSINESS LOGIC error, but still valid in syntax/types:
case Triangle(double a, double b, double c) -> a * b;
```

Such a `case` makes the switch exhaustive, yet the area of a general triangle is not `a*b`. Testing a 3–4–5 triangle with expected area = 6 catches this bug.

Similarly, if rectangle perimeter were written as `w+h` instead of `2*(w+h)`, the compiler would still compile it; the `rectangle-perimeter` test is what proves correct behavior.

### 8.2. Constructor validation: valid data before matching

In the `Triangle` record:

```java
Triangle {
    requirePositive("a", a);
    requirePositive("b", b);
    requirePositive("c", c);
    if (a + b <= c || a + c <= b || b + c <= a) {
        throw new IllegalArgumentException(
            "triangle inequality violated");
    }
}
```

The rule is checked **upon object creation**. Because of that, `area` does not need to repeat the triangle inequality check in every case.

The `invalid-triangle` test creates `Triangle(1,2,3)` to test the degenerate case (1+2 is not greater than 3). The `invalid-circle` test verifies that radius 0 is rejected.

**Limitation:** For extremely large `double` sides, addition and Heron's formula can lose precision or overflow even when every side is finite. This is an illustrative model for normal-sized values. If strict numerical robustness is required, enforce input domain limits or use a more stable formula/algorithm along with dedicated numerical tests.

### 8.3. Pattern guards: the compiler does not decide shape taxonomy

In `kind`, the triangle cases are written from specific to general:

1. Three equal sides → `EQUILATERAL`.
2. At least one pair of equal sides (but not equilateral because the preceding case already matched it) → `ISOSCELES`.
3. Remaining triangles → `TRIANGLE`.

`javac` checks which case is shadowed, but it **does not know** the desired business naming. If the first and second guards are swapped, the program may still be type-valid, yet an equilateral triangle will be labeled `ISOSCELES` because that guard returns true first. The `equilateral-guard` test protects the business-required order.

In the example, using `double == double` is exact comparison, suitable for integer-literal side inputs (2, 3, 5). For measured coordinates or numbers resulting from floating-point arithmetic, tolerance-based classification rules must be defined more explicitly.

### 8.4. Null selector: the compiler does not read your business conventions for you

`kind(null)` returns `NONE` because it has `case null`. However, `area(null)` **does not** have a null case, so by Java 21 pattern switch rules, a null selector throws `NullPointerException`. The `null-area` test confirms this.

A real application needs to decide:
- Is `null` valid data with its own meaning?
- Or must it be rejected immediately at the boundary with `Objects.requireNonNull(shape)`?
- Should a custom business exception be thrown for a missing shape?

**Do not** add `default` assuming it will automatically handle a null selector. Null handling must be written according to the contract; `case null` is specifically for a null selector.

## 9. Reading javac diagnostics accurately

For the non-exhaustive example, the diagnostic format typically looks like this (file name/line/caret are **illustrative**, depending on the JDK version):

```text
Geometry.java:XX: error: the switch expression does not cover all possible input values
        return switch (shape) {
               ^
1 error
```

What to read:
- **File/line:** Which `switch`'s code is missing coverage?
- **Message:** Is it a `switch expression` or `switch statement` error?
- **Selector type:** Which new subtype can `Shape` receive?
- **Case list:** Which cases already cover the subtypes? Is there a broad/default case masking an omission?
- **Hierarchy change point:** Was `permits` just edited? Was a subtype moved to another branch or opened up as `non-sealed`?

When the compiler says:

```text
error: this case label is dominated by a preceding case label
```

you usually need to inspect the **preceding case**, not just the underlined one. For example, a `case Shape s` placed before `case Triangle(...)` will cover triangles as well and cause the later case to be dominated.

### Errors easily confused with exhaustiveness

| Message/symptom | Common cause | How to handle |
| --- | --- | --- |
| `switch expression does not cover...` | Missing subtype/covering case | Add the case, review logic and tests |
| `switch statement does not cover...` | Enhanced switch statement missing coverage | Add the corresponding case |
| `case label is dominated...` | General case or unguarded case placed earlier | Put specific/guarded cases first |
| `cannot find symbol: Triangle` | Type not declared/imported or wrong scope | Fix declaration/import, do not add default |
| `class is not allowed to extend sealed class...` | Subtype not permitted or `permits`/module/package mismatch | Update direct permits and subtype relationship |
| `invalid permits clause` | `permits` lists an incorrect direct subclass/subinterface | Check direct inheritance/implements relationship |
| `cannot be converted to...` | Incompatible pattern/record component type | Fix component or pattern type |
| `NullPointerException` at runtime | Null selector not handled | Standardize null policy |
| `MatchException` at runtime | No matching case in a situation the compiler once considered exhaustive; may involve separate compilation/nested patterns | Synchronize builds and review invariants/nulls |

Do not apply **a single one-size-fits-all fix** to every diagnostic. A compile-time coverage error is different from a runtime exception and different from an incorrect area result.

## 10. Behavior when adding a subtype across multiple modules

In a small project, `Shape` and the `switch`es may live in the same module, so adding a subtype and recompiling triggers immediate compiler feedback.

In a multi-module system:
- **Model module:** Contains the sealed `Shape` and the records.
- **Geometry service:** Calculates area/perimeter.
- **Rendering module:** Produces text, JSON, SVG, or UI for each shape.
- **Analytics module:** Aggregates shape types and statistics.
- **Integration module:** Maps to partner data formats.

If only the model module is recompiled **without** recompiling the consumers, you cannot rely on the compiler to ensure every handler has been updated. An old switch compiled against the old hierarchy may throw `MatchException` at runtime when encountering a variant it does not yet recognize, depending on binary compatibility and runtime conditions.

Therefore, after adding a subtype:
1. **Rebuild all consumers** that use `Shape`.
2. Run unit/integration tests across compatible artifacts.
3. Review affected serialization, database mappings, UI, and public APIs.
4. Avoid deploying the new model before consumers that need to handle the new type are ready, unless the contract has an explicit fallback.

**Compile-time feedback only applies to the units compiled in that build.** “One module built successfully” is not the same as “the multi-module system has handled the new subtype everywhere.”

## 11. When should you not keep a sealed hierarchy completely closed?

`sealed` fits when you control the set of variants, it is relatively stable, and operations need exhaustive matching. However, if the application needs third-party plugins to define new shapes themselves, the list of types may be **open**.

For example, a direct permitted subtype that is `non-sealed`:

```java
// Separate illustrative snippet, not combined with the program in section 7.
sealed interface Shape permits BuiltInShape, PluginShape {}

sealed interface BuiltInShape extends Shape
        permits Circle, Rectangle {}
non-sealed interface PluginShape extends Shape {}
```

Third parties can implement subtypes of `PluginShape`. A switch that wants to be exhaustive needs to cover **the entire `PluginShape` branch** with a type pattern or an intentional fallback; it cannot enumerate in advance the infinite implementations provided by plugins.

**Design tips:**
- If area/perimeter calculation is a contract for every shape and plugins must define their own logic, consider `double area()`/`double perimeter()` on the interface (polymorphism) rather than having every consumer enumerate types.
- If the type set is closed and independent operations are frequently added (formatters, exporters, renderers), pattern switches on sealed types are very useful.
- Choose between a sealed or open hierarchy based on desired extensibility, not just because compiler feedback feels convenient.

### Another option: an intentional generic fallback

For a logging operation that only needs the class name, a generic fallback is acceptable. In that case, a branch like `case Shape s -> ...` makes sense. But for **area calculation**, a silent fallback to `0` usually hides business bugs; every subtype should have a proper formula.

## 12. Test matrix when adding Triangle

Do not stop once `javac` reports zero errors. Add tests for the **new subtype** and regression tests for existing subtypes.

| Item | Input/condition | Expected |
| --- | --- | --- |
| Circle area | `Circle(2)` | `4π` |
| Circle perimeter | `Circle(2)` | `4π` |
| Rectangle area | `Rectangle(3,4)` | `12` |
| Rectangle perimeter | `Rectangle(3,4)` | `14` |
| Triangle area | `Triangle(3,4,5)` | `6` |
| Triangle perimeter | `Triangle(3,4,5)` | `12` |
| Triangle general | `Triangle(3,4,5)` | `TRIANGLE` |
| Triangle equilateral | `Triangle(2,2,2)` | `EQUILATERAL` |
| Triangle isosceles | `Triangle(2,2,3)` | `ISOSCELES` |
| Null selector for kind | `null` | `NONE` |
| Invalid triangle | `Triangle(1,2,3)` | `IllegalArgumentException` |
| Invalid circle | `Circle(0)` | `IllegalArgumentException` |
| Null selector for area | `null` | `NullPointerException` |

These are the exact 13 test cases in the runnable program. For production, add more cases:
- Negative, zero, NaN, Infinity for radius/width/height.
- Triangles violating the inequality across all side permutations.
- Nearly degenerate triangles; very large/very small sides to test numerical stability.
- Input values leading to non-finite area/perimeter.
- UI/API/serialization behaviors for the new subtype.
- Regression tests for all existing subtypes, not just Triangle.

**Before-and-after testing:** When adding `Triangle`, you don't just modify new logic; operations may share branches or use guards whose ordering could accidentally change old results. Tests for Circle and Rectangle help catch regressions.

### Compiler feedback is not test coverage

The compiler can verify that each subtype is covered by **a case**. It does not check:
- Which guarded branch actually executes?
- Is the formula written correctly?
- Does validation reject all forms of invalid data?
- Does any case intentionally return a business error even though it compiles?
- Does the code match UI/partner requirements?
- Do tests cover the boundary values of the domain?

Therefore, you must combine **compile-time exhaustiveness + runtime tests + business review**.

## 13. Can reflection be used to guard the subtype set?

Java provides `Class::isSealed` and `Class::getPermittedSubclasses`. In a dedicated test, you can verify the exact direct permitted types:

```java
// Illustrative snippet in the same class containing Shape/Circle/Rectangle/Triangle:
if (!Shape.class.isSealed()) {
    throw new AssertionError("Shape must stay sealed");
}

java.util.Set<Class<?>> expected = java.util.Set.of(
    Circle.class, Rectangle.class, Triangle.class);

java.util.Set<Class<?>> actual =
    java.util.Set.of(Shape.class.getPermittedSubclasses());

if (!expected.equals(actual)) {
    throw new AssertionError("Shape hierarchy changed");
}
```

`getPermittedSubclasses()` returns the **direct permitted subclasses/subinterfaces**. For hierarchies with multiple sealed/non-sealed levels, you must inspect intermediate nodes to know all leaf variants owned by the application.

Reflection tests help detect when a new type is introduced without updating the test matrix. They **do not** prove mathematical correctness. When a valid subtype is added, the expected set must be updated alongside the relevant tests and handlers.

Some IDEs/CI tools check exhaustiveness early, but **`javac` is the foundational check at build time**. Reflection tests are an extra layer, not a replacement for compile-time checking.

## 14. Common design mistakes when adopting a new subtype

### 14.1. “Fixing all compiler errors” with a broad default

```java
// Behavior that can mask a missing implementation:
return switch (shape) {
    case Circle(double r) -> Math.PI * r * r;
    case Rectangle(double w, double h) -> w * h;
    default -> 0.0;
};
```

Once Triangle exists, the code compiles but returns 0.0. If behavior must be accurate for every shape, this is a business bug.

**Choice:** Add `case Triangle(...)` that actually computes the right result, or throw an explicit exception if the type is not yet supported under a controlled transition policy. Never treat dummy values as valid results.

### 14.2. Forgetting the second operation

A developer only fixes `area` because the compiler flagged it, but forgets `perimeter` in another module that wasn't built. As a result, area works, while perimeter may fail at runtime on Triangle.

**Choice:** Find all consumers of `Shape`, build everything, and apply a checklist to audit all related operations.

### 14.3. Placing a specific case after a general case

`case Shape s` at the top of a switch makes the subsequent Circle/Rectangle/Triangle cases dominated. Similarly, an unguarded `case Triangle(...)` before the `EQUILATERAL` guard causes dominance.

**Choice:** Order specialized branches before broad fallbacks; write tests for guards with overlapping values.

### 14.4. Changing the data model while ignoring invariants

Adding `Triangle` with just three `double`s does not mean every triple is a triangle. `Triangle(1,2,3)` is invalid; so is `Triangle(0,4,5)`.

**Choice:** Validate in the constructor or in the factory/domain service that owns the rule. When the application receives untrusted data from JSON/APIs, validate at the boundary and ensure domain objects cannot be constructed in an invalid state.

### 14.5. Expecting the compiler to catch every numerical error

`sqrt(s*(s-a)*(s-b)*(s-c))` can suffer from rounding errors or overflow. The compiler does not prove numerical stability from the `double` type alone.

**Choice:** Use meaningful numerical tests, contract-aligned tolerances, and appropriate algorithms if handling extreme values.

### 14.6. Assuming exhaustive means no runtime exceptions ever

Pattern `switch` exhaustiveness is based on type structure at compile time. Runtime can still throw `NullPointerException` for a null selector, or `MatchException` in unusual situations such as separate compilation or nested record patterns failing to match due to null. Guards/case bodies can also throw their own exceptions.

**Choice:** Design clear null policies and business errors; build and test with the exact artifacts/dependencies that will be deployed.

## 15. Team workflow: changing a sealed model without missing consumers

A reliable workflow for adding a subtype:

1. **Define the subtype's business rules:** Triangle has three sides, area/perimeter formulas, invariants, and specific classification rules.
2. **Update the hierarchy:** Add the record subtype to `permits` with the right direct relationship. Decide whether the subtype is final/sealed/non-sealed by design.
3. **Build immediately:** Note the exhaustive/dominance errors from `javac` before fixing them. These are the consumer points to review.
4. **Update each operation:** Add real formulas, without adding a `default` that hides missing logic. Order guards properly.
5. **Add tests:** Test the new subtype, boundary values, invalid data; keep Circle/Rectangle tests.
6. **Rebuild all dependent modules:** Ensure no consumer is running against stale bytecode.
7. **Review APIs and integrations:** DTOs, serialization, persistence, UI, reports, and external systems must understand Triangle according to the contract.
8. **Test deployment:** With multiple services running different versions, verify how the new subtype is handled during rolling updates.
9. **Evaluate extensibility:** If shape plugins are constantly added and require editing dozens of switches, consider polymorphism/domain services or an appropriate extension point.
10. **Release only after QA:** Compile-time feedback is the first line of defense, not the only condition.

### Example scenario of extending with one more type

If after Triangle you want to add `Square(double side)`, decide whether `Square` is a separate subtype or a kind of `Rectangle` in the domain. If choosing a separate record subtype:
- Add `Square` to the hierarchy and `permits`.
- `javac` will likely report missing coverage in `area`/`perimeter`/`kind`.
- Add formulas `side*side`, `4*side`, and the appropriate label.
- Test negative/0/positive side values.
- Check whether consumers have any policy treating Square like Rectangle.

Do not create a new subtype just because you can: the hierarchy structure must reflect **domain concepts and expected axes of change**.

## 16. Practice exercises

**Exercise 1 — Reproduce non-exhaustive error:** Copy the `Shape` snippet with Circle/Rectangle/Triangle but intentionally omit `case Triangle(...)` from `area`. Compile with `javac --release 21` and record the message. Then add the Heron case and run `Triangle(3,4,5)`.

**Exercise 2 — Fix perimeter:** Temporarily remove `case Triangle(...)` from `perimeter`. What does the compiler say? Add the case returning `a+b+c`, and verify expected 12 with sides 3–4–5.

**Exercise 3 — Dominance and guards:** Place the unguarded Triangle case before `case ... when a==b && b==c`. Observe the dominated error. Restore the order; then swap the isosceles/equilateral guards to see which logic test fails even though the compiler still accepts it.

**Exercise 4 — Add Square:** Add `record Square(double side) implements Shape` with finite-positive validation. Update `permits`, the switches, and the tests. List the compile errors discovered before fixing them.

**Exercise 5 — Null policy:** Compare `kind(null)` with `area(null)`. Why does one method return `NONE` while the other throws `NullPointerException`? Propose a unified contract for the application and write corresponding tests.

**Exercise 6 — Nearly degenerate data:** Create a triangle where the sum of two sides is only slightly greater than the third side. Observe validation behavior and the stability of Heron's formula. Define a suitable data domain for production and a rounding/tolerance strategy.

**Exercise 7 — Multi-module:** Separate `Shape` and the records into a domain module, `area/perimeter` into a service module, and `kind` into an adapter. Add `Square` and compile only the domain module. Explain why building one module does not guarantee all consumers were checked; update CI to build everything.

## 17. Summary

**Sealed hierarchies + pattern switches in Java 21 create an important feedback loop when evolving a domain model.** When adding `Triangle` to `Shape`, the compiler can report errors in `switch expression`s or enhanced `switch statement`s that do not yet handle the new subtype. This is a very useful way to enforce **compile-time exhaustiveness** for controlled sets of variants.

However, the compiler **does not prove that area/perimeter formulas are right**, nor does it automatically check the triangle inequality, business guards, or all runtime conditions. You need to combine **updating `permits` → addressing compiler feedback → adding accurate cases → testing both new and existing subtypes → rebuilding all consumers**.

Do not treat `default` as the fastest way to get a green build. When an operation must explicitly handle each shape, having the compiler force you back to write a case for the new subtype is a design benefit.

## References

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Sealed Classes and Interfaces: https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html
- Java Language Specification SE 21 — `14.11 switch Statements`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11
- Java Language Specification SE 21 — `15.28 switch Expressions`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- OpenJDK JEP 409 — Sealed Classes: https://openjdk.org/jeps/409
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
