# Measuring Hierarchy Extensibility: A Geometry Case Study with Java Pattern Matching

## 1. Understanding "Extensibility" Properly

In a geometry system, we typically have multiple **shape variants** (circles, rectangles, triangles, etc.) and multiple **operations** (area, shape category description, parameter display, collision detection, data export). As the system evolves, two distinct kinds of requirements arise:

1. **Adding a new shape type:** for example, adding `Triangle` to a hierarchy that previously only had `Circle` and `Rectangle`.
2. **Adding a new operation:** for example, in addition to `area` and `category`, adding `describeDimensions` to present a shape's parameters.

One design may make adding operations very easy while requiring edits in many places when adding a subtype; another design may make adding a subtype easy while requiring edits to every class when adding an operation. Therefore, the question "Is the hierarchy easy to extend?" only makes sense if we **specify the direction of extension and how it is measured**.

In Java Core Pattern Matching—especially with **`sealed interface` + `record` + pattern-based `switch`**—we have a toolkit to observe these costs clearly:

- `sealed` specifies which direct subtypes are permitted.
- `record` holds the geometric components and can enforce invariants in its constructor.
- A `switch expression` over a sealed type with record/type patterns forces the programmer to handle all relevant subtypes.
- The compiler helps detect missed branches when a new variant is added.
- Tests verify both the geometric formulas and the differences between design alternatives.

**What is primarily measured in this article is source-code maintainability and extensibility**, not "how much faster the program runs when adding a subtype." Performance benchmarking is a separate problem.

**Version requirements:** `record` has been standard since Java 16 (JEP 395), `sealed` since Java 17 (JEP 409), and record patterns and pattern matching for `switch` have been standard since **Java 21** (JEP 440/441). The complete program in this article uses **JDK 21 or later**, without needing `--enable-preview`.

## 2. Experimental Model: A Deliberate Set of Shapes

Suppose the initial version has two shape types:

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
```

This is an **illustrative snippet of the initial design**, not a standalone Java program; when testing it separately, the types must be placed in the proper scope with the necessary handling code.

We need two independent operations, both depending on the variant:

- `area(Shape)` returns the area.
- `category(Shape)` returns a geometric label such as `"circle"` or `"rectangle"`.

With two variants, one Java 21 implementation is:

```java
// Illustrative methods placed in a class containing Shape, Circle, and Rectangle.
static double area(Shape shape) {
    return switch (shape) {
        case Circle(var radius) -> Math.PI * radius * radius;
        case Rectangle(var width, var height) -> width * height;
        case null -> throw new IllegalArgumentException("shape required");
    };
}

static String category(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case null -> "missing";
    };
}
```

In `area`, a **record pattern** destructures the components: `Circle(var radius)` extracts the radius; `Rectangle(var width, var height)` extracts the width and height. In `category`, a **type pattern** `Circle c` / `Rectangle r` only selects the variant; there is no need to destructure components because the result does not depend on dimensions.

This is the first measurement: with two variants and two operations containing a `switch`, there are **four subtype-handling branches** (two cases in `area`, two cases in `category`). The `case null` branches represent a separate input policy and therefore **are not counted toward the number of subtype branches**.

## 3. Extensibility Metrics Must Be Defined Up Front

Notation:

- **V** (*variants*): the number of concrete shape types the design intends to handle.
- **O** (*variant-sensitive operations*): the number of operations that actually need to branch by shape type.
- **B** (*branch implementations*): the total number of subtype cases across those operations.
- **ΔV**: the number of added subtypes.
- **ΔO**: the number of added subtype-dependent operations.
- **S** (*semantic edit sites*): the number of responsibility-independent code locations that must be added or updated in a change.
- **F** (*files touched*): the number of files actually modified in the repository; must be measured from the diff, not guessed from the case count.
- **T** (*tests affected*): the number of tests added/modified and the pass rate of test cases after the change.

When **each operation has exactly one case per subtype** and there are no combined branches, the branch cost is simply modeled by:

\[
B = V \times O
\]

This is a **structural counting model**, not a law of Java or a runtime complexity bound. In real code, an operation may use polymorphism, shared logic, a catch-all case, or require no branching at all; in those cases, you must **count actual branches** rather than applying the formula mechanically.

A useful measurement method is to execute **two change scenarios** and compare them:

| Change | Metrics to Record | Additional Checks |
| --- | --- | --- |
| Add a shape type | `ΔV`, cases added across switches, edit sites, files modified, new tests | Does the compiler detect switches missing a case? |
| Add a type-dependent operation | `ΔO`, number of cases to write, edit sites / files modified | Is there formula duplication, invariant violation, or a missed shape? |
| Modify a shared formula | Edit sites and scope of affected tests | Can logic be reused, or must edits be repeated? |
| Receive an unexpected subtype | Compile/runtime behavior, fallback policy | Does a `default` branch mask missing-subtype warnings? |

A hierarchy with many subtypes is **not necessarily bad**; what matters is how many places the domain's most common changes require editing and how many bugs are easy to miss.

## 4. Experiment A — Adding Triangle to the Hierarchy

Suppose initially `V = 2`, `O = 2`, so `B = 4` subtype branches. The new requirement is to support a triangle **with a positive base and height**, sufficient to compute the **area**, though not yet sufficient to compute the perimeter.

### 4.1. Required Changes

**(1) Extend `permits`:**

```java
sealed interface Shape permits Circle, Rectangle, Triangle {}
```

**(2) Add the record:**

```java
record Triangle(double base, double height) implements Shape {}
```

**(3) Add the case in `area`:**

```java
case Triangle(var base, var height) -> base * height / 2;
```

**(4) Add the case in `category`:**

```java
case Triangle t -> "triangle";
```

The snippets above illustrate **the changes to merge into the same model**; the program in Section 6 already contains the complete version after extension.

According to the defined way of counting `S`, this represents **four logical edit sites**: the `permits` list, the new record declaration, and the two new cases. These **do not equate to four files**: if all types and switches reside in a single learning file, then `F = 1`; in a multi-file codebase, the value of `F` depends on the project's organization.

After the change:

| Metric | Before Adding Triangle | After Adding Triangle | Delta |
| --- | ---: | ---: | ---: |
| Variants `V` | 2 | 3 | +1 |
| Operations with switch `O` | 2 | 2 | 0 |
| Subtype branches `B = V × O` | 4 | 6 | +2 |
| New branches required in switches | — | 2 | +2 |
| Meaningful code edit sites `S` | — | 4 | 4 sites |
| Tests for Triangle | None yet | Must be added | Count in actual test diff |

**Key takeaway:** every operation that branches on shape type can create an update point when a subtype is added. If there are 12 separate operations each containing an exhaustive switch, adding one subtype can require **12 new cases**, not one. However, that is the number of branches designed under this model—**not the number of files**, and not `O(12)` runtime complexity per request.

### 4.2. Why Are `sealed` + Exhaustive `switch` Useful for Measurement?

With a `switch expression` over `Shape` having three final record subtypes, if you forget `case Triangle...` in `area`, the compiler rejects the program as **not covering all possible input values**. This turns "places that need updating" from an easy-to-miss risk into an observable build error.

If you use `default -> 0.0` just to silence the compiler's missing-branch error, the code may still compile while **silently returning the wrong area** for the new subtype. Therefore, in an intentionally closed hierarchy, avoid unnecessary `default` branches if you want to leverage **exhaustiveness**.

The `case null` branch handles a null selector according to a separate policy. `null` is not a subtype listed in `permits`.

## 5. Experiment B — Adding a New Operation

Keep `V = 3` with Circle, Rectangle, and Triangle. Add `describeDimensions(Shape)` to present **the characteristic parameters of each shape**, unlike `category` which only returns the name.

An illustrative implementation:

```java
static String describeDimensions(Shape shape) {
    return switch (shape) {
        case Circle(var r) -> "radius=" + r;
        case Rectangle(var w, var h) -> "width=" + w + ",height=" + h;
        case Triangle(var b, var h) -> "base=" + b + ",height=" + h;
        case null -> "missing";
    };
}
```

This is an **additional illustrative method**, not part of the main program in Section 6. It creates **one variant-dependent operation** with **three new subtype branches**:

- Before: `V=3`, `O=2`, `B=6`.
- After: `V=3`, `O=3`, `B=9`.
- `ΔB=3`, adding **one function** and **three case branches** under the semantic edit-site counting convention.

This is the relative strength of pattern switches: you can add **a new operation centralized in one place**, reading and comparing how every subtype is handled within the same function. You do not have to open each record to add a separate method just for a new report.

**However, not every new operation needs a new switch.** For example, `isLarge(Shape shape)` can be written as `return area(shape) >= 100;`, reusing `area` without adding three new branches. When applying `B=V×O`, only count operations that **actually require separate per-variant dispatch**.

## 6. Complete Java Program for Reproduction

Create the file **`ShapeExtensibilityDemo.java`**:

```java
public class ShapeExtensibilityDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    private static void positive(double number, String component) {
        if (!Double.isFinite(number) || number <= 0) {
            throw new IllegalArgumentException(
                    component + " must be finite and positive");
        }
    }

    record Circle(double radius) implements Shape {
        public Circle {
            positive(radius, "radius");
        }
    }

    record Rectangle(double width, double height) implements Shape {
        public Rectangle {
            positive(width, "width");
            positive(height, "height");
        }
    }

    record Triangle(double base, double height) implements Shape {
        public Triangle {
            positive(base, "base");
            positive(height, "height");
        }
    }

    static double area(Shape shape) {
        return switch (shape) {
            case Circle(var r) -> Math.PI * r * r;
            case Rectangle(var w, var h) -> w * h;
            case Triangle(var b, var h) -> b * h / 2;
            case null -> throw new IllegalArgumentException("shape required");
        };
    }

    static String category(Shape shape) {
        return switch (shape) {
            case Circle c -> "circle";
            case Rectangle r -> "rectangle";
            case Triangle t -> "triangle";
            case null -> "missing";
        };
    }

    static String report(Shape shape) {
        return category(shape) + ":" +
                String.format(java.util.Locale.ROOT, "%.2f", area(shape));
    }

    static void check(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": " + actual);
        }
        System.out.println(label + " -> " + actual);
    }

    public static void main(String[] args) {
        check("circle", "circle:3.14", report(new Circle(1)));
        check("rectangle", "rectangle:6.00",
                report(new Rectangle(2, 3)));
        check("triangle", "triangle:6.00",
                report(new Triangle(4, 3)));
        check("missing", "missing", category(null));

        System.out.println("sealed:" + Shape.class.isSealed());
        System.out.println("permitted:"
                + Shape.class.getPermittedSubclasses().length);

        try {
            new Rectangle(-1, 2);
            throw new AssertionError("invalid dimensions accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid:" + expected.getMessage());
        }

        try {
            area(null);
            throw new AssertionError("null area accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("null-area:" + expected.getMessage());
        }
    }
}
```

**Compile and run with JDK 21+:**

```bash
javac --release 21 ShapeExtensibilityDemo.java
java ShapeExtensibilityDemo
```

**Exact stdout of the program:**

```text
circle -> circle:3.14
rectangle -> rectangle:6.00
triangle -> triangle:6.00
missing -> missing
sealed:true
permitted:3
invalid:width must be finite and positive
null-area:shape required
```

The program was executed with **JDK 24/JShell** and verified to produce these exact eight lines; all primary syntax features used here have been standard since Java 21. `java.util.Locale.ROOT` ensures the decimal separator in `String.format` is a dot as shown in the output, rather than depending on the machine's locale.

### 6.1. Reading the Tests and Data Guarantees

- `Circle(1)` has area `π×1×1`; rounded to two decimal places, that is `3.14`.
- `Rectangle(2,3)` has area `2×3=6.00`.
- `Triangle(4,3)` has area `4×3/2=6.00`.
- `category(null)` returns `"missing"`, whereas `area(null)` **throws `IllegalArgumentException`**, following the two chosen contracts.
- `Shape.class.isSealed()` returns `true`; `getPermittedSubclasses().length` returns `3` because there are exactly three permitted direct subtypes.
- A dimension of `-1` is rejected by the constructor. The `positive` helper also rejects `0`, `NaN`, and ±infinity via the `Double.isFinite` and `>0` checks.
- `report` does not contain a third `switch`: it **delegates to** `category` and `area`. Therefore, `O=2` in the current measurement, not `3`.

**Limitation of the triangle model:** `Triangle(base,height)` is sufficient to compute **area**, but it does not fully describe three sides or three vertices, so it is **not sufficient to compute the perimeter of an arbitrary triangle**. If the problem requires perimeter, you must change the model (for example, three valid side lengths or three vertices) and add triangle-inequality / degeneracy checks. Do not invent a perimeter formula from just base and height.

### 6.2. Why Use Constructor Validation?

If `Circle(-2)` were accepted, the formula `πr²` would still yield a positive number, masking the invalid geometric data. An extensibility experiment needs **a model with clear invariants**; otherwise, comparisons across subtypes will be distorted by invalid inputs.

In this example, only shapes with **finite and positive** dimensions are considered. A CAD application might allow zero-sized dimensions to represent degenerate shapes; in that case, the invariants and tests must be adapted to the domain rather than treating the rules here as universal truth for all geometry software.

## 7. Negative Compile Tests: Measuring How Well the Compiler Protects Extension

In addition to runtime tests, write **intentionally invalid** snippets to see how far compiler support goes. Do not place these snippets in the complete file from Section 6.

### 7.1. Missing Triangle Case in a Switch Expression

If `Triangle` has been added to `permits` but you forget to add its case in `area`:

```java
// INTENTIONALLY INVALID; placed in a class containing Shape, Circle, and Rectangle.
static double areaMissing(Shape s) {
    return switch (s) {
        case Circle(var r) -> Math.PI * r * r;
        case Rectangle(var w, var h) -> w * h;
        case null -> 0.0;
    };
}
```

With `Shape` consisting of the three permitted records, the JDK 24 compiler rejected the equivalent snippet with the message:

```text
the switch expression does not cover all possible input values
```

This is a **direct indicator of a pattern switch's ability to pinpoint edit sites** when adding a subtype. You should not write `default -> 0` to bypass the error, because the compiler may stop reporting missing cases while the operation returns wrong values.

### 7.2. Unpermitted Subtype

```java
// INTENTIONALLY INVALID: Shape.permits does not include Pentagon.
class Pentagon implements Shape {}
```

The compiler rejects this because `Pentagon` is not in the list of permitted direct subtypes of the sealed `Shape`. This is a **constraint on hierarchy extension**, not a question of whether Pentagon's internal data is valid.

In a library extensible via external plugins, a completely closed sealed model may be an **inappropriate** choice. You must explicitly decide where extension points are allowed, rather than viewing compiler errors as unconditionally beneficial.

### 7.3. Wrong Number of Components When Adding a New Record

`Triangle` has **two** components, so the following snippet is invalid:

```java
// INTENTIONALLY INVALID: Triangle requires two nested patterns.
static boolean wrongParts(Object input) {
    return input instanceof Triangle(var base);
}
```

The JDK 24 compiler rejects this because of `incorrect number of nested patterns`. When a record's structure changes, patterns that reference it directly may need updating. This is a **structural coupling cost**, not merely the cost of adding a subtype.

The negative compile tests above were verified with JDK 24 JShell. They demonstrate errors caught by the compiler; they are not runnable Java files that produce stdout.

## 8. What Does Reflection Tell Us, and What Does It Not?

Java 17+ provides reflection APIs related to sealed classes:

```java
boolean sealed = Shape.class.isSealed();
Class<?>[] direct = Shape.class.getPermittedSubclasses();
System.out.println(sealed);
System.out.println(direct.length);
```

This is an **illustrative snippet** inside a class where `Shape` is defined. In the main program, the results are printed with the prefixes `sealed:` and `permitted:`.

The value `getPermittedSubclasses().length` is the **number of direct permitted subclasses/interfaces**, not automatically:

- The total number of **indirect** subclasses at all depths.
- The number of shape types currently existing under a `non-sealed` branch that can be extended externally.
- The number of cases in every `switch` across the codebase.
- The number of tests needed for coverage or the number of files to modify when adding a shape type.

In our example, all direct subtypes are final records, so `3` is also the number of concrete variants in the model under study. For multi-level hierarchies, you must distinguish **breadth** (number of direct branches), **depth** (number of inheritance levels), and **open** points introduced by `non-sealed`.

**Important:** reflection can confirm the runtime state of the hierarchy, whereas **counting switch sites must be done at the source-code / AST / code-review level or with static analysis tools**. Do not take `permitted:3` and conclude that the compiler has necessarily checked all business logic in the application.

## 9. Comparing Pattern Switch with Polymorphism

Operations can be moved onto the shape type itself:

```java
// Illustrates an alternative design choice; not merged into the file in Section 6.
sealed interface Shape permits Circle, Rectangle, Triangle {
    double area();
    String category();
}

record Circle(double radius) implements Shape {
    @Override
    public double area() { return Math.PI * radius * radius; }

    @Override
    public String category() { return "circle"; }
}

// Rectangle and Triangle need to implement the corresponding methods.
```

This is the **polymorphism approach**. If you add a new subtype and extend `permits`, the new class must implement the promised methods, while **existing classes and a central switch dispatcher do not necessarily have to be modified**.

If you add a **new abstract operation** to `Shape`, existing subtypes will need to implement the new method (unless a suitable shared default implementation exists). This model therefore tends to favor systems that **frequently add new shape types while rarely changing the set of shared operations**.

Comparison by direction of change:

| Criterion | Sealed Hierarchy + Pattern Switches | Polymorphism Placing Methods on Shape |
| --- | --- | --- |
| Adding a new subtype | Add type, update `permits`, add a case in each switch that handles it | Add type, update `permits`, implement required methods in the new subtype |
| Adding a new subtype-dependent operation | Add one switch operation; cases are centralized in the new function | Add method to interface/abstract class and implement it across subtypes |
| Compiler's ability to flag missing handling | Exhaustiveness of switch expression reports missing cases as errors | Unimplemented interface/abstract methods also produce compile errors |
| Code organization by operation | Easy to read all shapes for one calculation in one place | Logic for a single calculation is spread across subtypes |
| Code organization by shape type | Each shape is data; some logic lives in external functions | Data and shape-specific logic usually live together in one subtype |
| Extension via external plugins | Closed `sealed` prevents arbitrary direct subtypes | Still restricted if the interface is also `sealed`; opening it requires redesign |
| Risk when adding a subtype | May require editing many switches; `default` masks warnings | May require implementing many methods; base class/interface grows large |
| Performance | Depends on compiler, workload, and JIT | Depends on dispatch, JIT, and workload; not inherently faster |

**Design selection conclusion:** Pattern matching fits best when **the set of shapes is relatively stable and new analytical operations are added frequently**. Polymorphism fits best when **many new subtypes appear while the shared set of operations remains relatively stable**. Hybrid models are also valid: keep `area()` with strong invariants on the subtype, while using centralized pattern switches for reporting or serialization operations.

Avoid arguing that "`switch` is always bad" or "pattern matching replaces OOP." Both have extension costs along two different axes.

## 10. Measuring via a Change Experiment in a Real Repository

To obtain comparable data between the two designs, conduct a controlled experiment:

1. **Choose the same baseline:** the same number of shapes, same operations, same invariants, and same test suite (e.g., `V=2`/`O=2`).
2. **Define a specific change request:** "add Triangle supporting area and category"—without simultaneously changing algorithms, renaming packages, and refactoring unrelated code.
3. **Implement on two separate Git branches** for the pattern-switch design and the polymorphism design.
4. **Measure the actual diff:** files modified, logical edit sites added/modified, number of cases/methods, lines added, and lines changed.
5. **Compile immediately after adding the subtype but before completing all handlers:** record the number of compile errors at exhaustive switches or subclasses with unimplemented methods.
6. **Complete the updates and run tests:** area formulas, null inputs, invalid values, and the new type. Measure added tests and affected tests.
7. **Repeat with a change on the other axis:** add `describeDimensions` without adding a subtype; compare the number of sites requiring edits.
8. **Review the results:** change cost, ease of error detection, readability, merge conflicts, module boundaries, and compatibility.
9. **Record metrics with context:** Java version, file structure, compiler flags, model size, and counting rules. Avoid drawing general conclusions from a toy program.

A measurement report should follow this structure:

| Metric | Baseline | Add Triangle | Add New Operation |
| --- | --- | --- | --- |
| Number of variants `V` | 2 | 3 | 3 |
| Operations with dispatch `O` | 2 | 2 | 3 |
| Theoretical subtype branches `B` | 4 | 6 | 9 |
| New branches added | 0 | 2 | 3 |
| Code edit sites | Set baseline | Count actual diff | Count actual diff |
| Files modified | Set baseline | Count actual diff | Count actual diff |
| Compile/test results | Baseline passes | Must pass after update | Must pass after update |

In the "Add New Operation" column, `O=3` assumes `describeDimensions` has three cases. If the new operation is implemented by reusing `area` without dispatching, `O` does not increase and the table must be adjusted accordingly.

### 10.1. When Variants and Operations Scale Up

If a design uses a separate switch for **each** operation and **one** case for **each** subtype, then:

- `V=10`, `O=8` leads to `B=80` subtype cases.
- Adding one subtype (`ΔV=1`) requires **8 new cases**, if all eight operations must distinguish subtypes.
- Adding one subtype-dependent operation (`ΔO=1`) requires **10 new cases**.

This is an **extrapolation from the counting model**, not a benchmark result or a measurement from a specific repository. When many cases share formulas, abstractions, or subtype-independent algorithms, the cost can be lower. In other situations, adding a subtype also requires updating serialization, validation, documentation, tests, or logic in other modules, so the total impact can be **higher** than the case count alone.

When changes repeat frequently, a more meaningful metric than "number of classes" is **the number of logical sites a business change forces a developer to remember to update**.

## 11. Exhaustiveness, Compatibility, and Compiler Limits

### 11.1. The Compiler Checks Structure, Not Formula Correctness

An exhaustive `switch` ensures all type cases are handled according to language rules, but it does not verify that `Math.PI*r*r` or `b*h/2` is the right formula for the domain. In a `Triangle` storing only base and height, the area formula is correct; if the application later interprets those fields as two non-perpendicular side lengths, the very same branch can become business-logic wrong even though the compiler is completely satisfied.

Test **boundary values, units, and invariants**, not just whether every switch has a case.

### 11.2. Impact on Clients When a Library Adds a Permitted Subtype

When a public sealed library is updated to add a subtype, clients that wrote an exhaustive `switch expression` against the old set of variants may need to recompile and update their logic. The compiler helps catch errors if the client is built against the new API; **there is no guarantee** that old client binaries will automatically understand the new variant just because the library was updated.

Depending on version mismatches between client and library at runtime, a pattern switch missing a branch can fail at runtime instead of performing meaningful handling. Therefore, changing permitted subtypes must be accompanied by **versioning, binary/source compatibility checks, regression tests, and release notes**.

### 11.3. `default`: A Policy Choice, Not Always Wrong

In a closed hierarchy, omitting `default` can be useful so the compiler points out missing branches. However, sometimes an API genuinely requires a meaningful fallback for an unfamiliar variant or an open hierarchy. In that case, `default` is a deliberate decision; you must test the fallback and accept that the compiler's ability to warn about missing subtypes will be reduced.

Do not enforce an absolute rule like "never use default"; instead ask **what happens when a new variant appears**.

### 11.4. Openness of the Hierarchy

A sealed parent can permit a `non-sealed` direct subtype; subtypes beneath that branch can then be extended further according to Java's rules. In that situation, merely reading `getPermittedSubclasses().length` **does not reveal the full number of concrete runtime types**. Multiple nested `sealed` levels also create varying inheritance depths.

In this geometry case study, all permitted subtypes are final records: the number of direct variants and the set of variants at the level under consideration coincide. That is an **intentional boundary** to keep the measurement transparent.

## 12. Common Mistakes When "Measuring Extensibility"

| Mistake | Remedy |
| --- | --- |
| Counting total classes and concluding extensibility is easy | Separate the add-subtype and add-operation axes; run an actual change experiment |
| Inferring from `permitted:3` that every hierarchy has exactly three classes | That only counts direct permitted subtypes; inspect `non-sealed` branches and deeper levels |
| Treating `B=V×O` as always exact | Only holds when each operation has a separate case per variant; count actual branches |
| Counting two new cases as two modified files | Case, edit site, and file are three distinct units; measure `F` from the diff |
| Adding `default` just to compile quickly | Can hide a new subtype that is not yet handled properly |
| Concluding the compiler guarantees correct area calculations | The compiler checks types/exhaustiveness, not mathematical formulas |
| Using `Triangle(base,height)` to compute perimeter too | Missing geometric information; requires three sides/vertices or a special triangle definition |
| Ignoring `NaN` or negative numbers | Add invariants and negative tests for dimensions |
| Using runtime benchmarks to measure extensibility | Execution speed differs from maintenance cost and change risk |
| Assuming a clean build on a newer JDK means Java 17 source compatibility | Record patterns and pattern switches became standard in Java 21; test with the actual target |
| Using `sealed` even when the system needs plugins to add subtypes | Design extension points, `non-sealed`, or an SPI if the domain requires it |
| Counting only switch cases while ignoring tests, docs, and serializers | Measure the full change impact in production |

## 13. Case Study QA Checklist

A trustworthy measurement should verify:

- **Model:** variants have meaningful names; each constructor enforces the desired invariants.
- **Source/target:** JDK 21+, no preview flags needed for standard features; build commands and stdout match.
- **Variant set:** `Shape.class.isSealed()==true`; `getPermittedSubclasses().length==3` in the experimental model.
- **Operations:** `area` has three correct formulas for valid inputs; `category` classifies the three subtypes accurately.
- **Null:** `category(null)` and `area(null)` have different policies that are clearly stated and tested.
- **Exhaustiveness:** omitting the `Triangle` case in a switch expression produces the expected compile error.
- **Permits:** a class not listed in `permits` cannot directly implement `Shape`.
- **Record arity:** the pattern `Triangle(var b)` mismatches the component count and is rejected by the compiler.
- **Measurement:** record `V`, `O`, `B`, `S`, `F`, and `T` separately; do not substitute a single number for all of them.
- **Change experiments:** measure both the add-shape and add-operation scenarios against the same baseline.
- **Product impact:** if it is a public API, check source/binary compatibility and documentation updates.

**Empirically verified in the learning environment:** the Java program in Section 6 produces the exact eight lines of stdout; the three intentionally invalid examples in Section 7 were rejected by JDK 24 for the expected reasons. Numbers such as `B=4/6/9` are structural calculations for the example, whereas the number of modified files in a real repository must be measured separately.

## 14. Practice Exercises

### Exercise 1 — Add Square

Starting from the complete program, add `Square(double side)`. Update `Shape.permits`, add the record with the invariant `side>0`, and add the two cases in `area` and `category`.

Predict the impact:

- After adding `Square`, `V` increases from `3` to `4`.
- Keeping `O=2`, `B` increases from `6` to `8`.
- The number of new cases is `2`, excluding `case null` since it is not a variant.

**Suggested test cases:** `Square(5)` yields area `25.00`; `Square(0)` is rejected by the constructor. Before adding all cases, try building to see which switch expressions the compiler flags.

### Exercise 2 — Add an Operation with Separate Dispatch

After adding `Square`, add `describeDimensions(Shape)`. With `V=4`, each shape needs a case presenting its parameters. Then, if no branches are merged and `O=3`, `B=4×3=12`. Record the **actual** number of files, cases, and added tests, then compare with the polymorphism approach.

### Exercise 3 — Avoid Unnecessary Dispatch

Write:

```java
static boolean isLarge(Shape shape) {
    return area(shape) >= 100.0;
}
```

This is an **illustrative method** placed in the class containing `Shape` and `area`. Because its logic reuses `area`, it **does not introduce a new switch**. Under this article's definition of `O`, `isLarge` does not need to increment `O` if we only count operations that branch directly by variant. Discuss whether this reuse reduces coupling when adding a subtype.

### Exercise 4 — Choose a Design for a Real Project

Suppose a geometry library has:

- 15 shape types, with only 1 new type added per year.
- 20 reporting/analysis algorithms, with several new algorithms added every quarter.

Compare pattern switch and polymorphism by **frequency of change**. Write a hypothesis based on `ΔV`/`ΔO`, then validate it with a change experiment in a sample codebase. Do not conclude solely from `V×O`; also consider reusability, encapsulation, algorithmic complexity, and testability.

## 15. Conclusion

**Measuring hierarchy extensibility means measuring the cost and risk of specific changes.** For the geometry case study:

- Initially there are **2 variants × 2 operations = 4 subtype branches**.
- When adding `Triangle`: **3 × 2 = 6**, requiring **2 new cases** and one record/`permits` change.
- When adding another subtype-dependent operation: **3 × 3 = 9**, adding **3 cases** in one new function.
- `sealed` + exhaustive `switch expression` lets the compiler report missing branches, but it **does not prove formulas are correct**, does not replace tests, and does not automatically measure modified files.
- Polymorphism tends to have an advantage when subtypes are added frequently; pattern switches tend to be convenient when the subtype set is stable while independent operations are added continuously.

Every conclusion should be grounded in **a baseline, actual diffs, tests, and the domain's extension policy**, rather than a slogan about OOP or pattern matching.

### Official References

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java SE 21 API — Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses())
