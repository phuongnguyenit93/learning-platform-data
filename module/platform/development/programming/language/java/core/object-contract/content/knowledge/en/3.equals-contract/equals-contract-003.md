# Symmetry When Swapping Two Objects in the `equals()` Contract

## 1. Concept and Contract Requirement

In Java, `Object.equals(Object)` expresses whether two objects are considered **logically equal**. A mandatory requirement of the `equals` contract is **symmetry**:

> For any two non-null references `a` and `b`, `a.equals(b)` must return the same result as `b.equals(a)`.

Verification formula:

```java
a.equals(b) == b.equals(a)
```

This requirement holds when both results are `true` **or** both are `false`. If `a.equals(b)` is `true` yet `b.equals(a)` is `false`, that class violates the contract. "Swapping positions" means swapping the **receiver object** and the **argument**, not changing the order in which fields are compared within the same object.

For instance, two objects both representing coordinates (3, 4) must agree on equality in both directions. If one object also represents a color while the other has no color, the equality relation design must clearly resolve whether they are considered the same value.

Symmetry is one of the five requirements of the `equals` contract, alongside reflexivity, transitivity, consistency, and returning `false` when compared to `null`. Satisfying symmetry is **not enough** to conclude `equals` is fully valid. If overriding `equals`, you must also ensure equal objects have the same `hashCode()`.

## 2. Why Does Reversing the Direction Give a Different Result?

The bug appears most clearly when a superclass and a subclass use **two incompatible equality criteria**:

1. The superclass `Point` compares only coordinates `x` and `y` and uses `instanceof Point`, so it accepts `ColoredPoint` as a `Point`.
2. The subclass `ColoredPoint` adds a `color` field and accepts only `ColoredPoint` objects.
3. When calling `point.equals(coloredPoint)`, the superclass sees matching coordinates and returns `true`; when calling in the reverse direction, the subclass sees an incompatible type and returns `false`.

Java allows this code to compile because the compiler cannot verify every property of an equality relation.

## 3. Java 17 Example: Where It Breaks and How to Fix It

Save the following complete program in the file **`EqualsSymmetryDemo.java`**. The first example deliberately violates symmetry. The second represents a colored point via **composition**: an object holding coordinates and a color, instead of inheriting from a class with a different equality definition.

```java
import java.util.Objects;

public class EqualsSymmetryDemo {
    static class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Point p)) return false;
            return x == p.x && y == p.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint extends Point {
        private final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof ColoredPoint p)) return false;
            return super.equals(p) && color.equals(p.color);
        }

        // Inherits Point.hashCode() to isolate and demonstrate
        // the symmetry bug; hash collisions across different colors are valid.
    }

    record SafePoint(int x, int y) {}

    record SafeColoredPoint(SafePoint point, String color) {
        SafeColoredPoint {
            Objects.requireNonNull(point);
            Objects.requireNonNull(color);
        }
    }

    static void assertSymmetric(Object a, Object b) {
        boolean forward = Objects.equals(a, b);
        boolean backward = Objects.equals(b, a);
        if (forward != backward) {
            throw new AssertionError("equals is not symmetric");
        }
    }

    public static void main(String[] args) {
        Point base = new Point(3, 4);
        ColoredPoint red = new ColoredPoint(3, 4, "red");

        System.out.println("base.equals(red) = " + base.equals(red));
        System.out.println("red.equals(base) = " + red.equals(base));

        SafePoint plain = new SafePoint(3, 4);
        SafeColoredPoint colored = new SafeColoredPoint(plain, "red");
        SafeColoredPoint copy =
                new SafeColoredPoint(new SafePoint(3, 4), "red");

        System.out.println("plain.equals(colored) = " + plain.equals(colored));
        System.out.println("colored.equals(plain) = " + colored.equals(plain));
        System.out.println("colored.equals(copy) = " + colored.equals(copy));

        assertSymmetric(plain, colored);
        assertSymmetric(colored, copy);
        assertSymmetric(plain, new SafePoint(3, 4));
        assertSymmetric(plain, null);
        System.out.println("safe symmetry checks = PASS");
    }
}
```

In the directory containing the file, run:

```bash
javac EqualsSymmetryDemo.java
java EqualsSymmetryDemo
```

Output on Java 17+:

```text
base.equals(red) = true
red.equals(base) = false
plain.equals(colored) = false
colored.equals(plain) = false
colored.equals(copy) = true
safe symmetry checks = PASS
```

**Explanation:**

- `base.equals(red)` is `true` because `red instanceof Point` is true and both coordinates match. The superclass method ignores the color.
- `red.equals(base)` is `false` because `base instanceof ColoredPoint` is false. This is the exact symmetry violation: the same pair gives opposite results in the two directions.
- `plain.equals(colored)` and `colored.equals(plain)` are both `false`. The two independent `record` types represent two different kinds of values, so neither side treats the other as equal.
- `colored.equals(copy)` is `true`: the two `SafeColoredPoint` objects have matching point and color components. A `record` automatically provides `equals` and `hashCode` based on its components.
- `assertSymmetric` checks both directions including the `null` case; calling `assertSymmetric(base, red)` would throw `AssertionError`.

In the flawed section, `ColoredPoint` keeps the inherited `hashCode` based only on coordinates. Two points with different colors can share the same hash even though they are not equal, and **hash collisions are valid**; this helps isolate the symmetry bug. Still, in a complete design, choose hash components according to a valid equality model and ensure equal objects always have the same hash.

## 4. Designing `equals` to Preserve Symmetry

### Solution A: `final` Value Classes, `record`, and Composition

If an object is a value with a fixed set of properties, a `final` class prevents subclasses from altering how the equality relation is interpreted. `record` fits immutable data objects defined by their components: Java automatically generates `equals`/`hashCode` from the components and the `record` type. In the example, `SafeColoredPoint` contains a `SafePoint` so color is not mixed into `SafePoint`'s equality contract.

Composition is especially useful when a new type **adds a property that determines identity**. Inheriting from an old type just to reuse data and then modifying how comparison works can break symmetry or transitivity.

### Solution B: Verifying the Same Runtime Type with `getClass()`

If objects of **two different runtime classes must not be considered equal**, you can replace `Point.equals` in the program above with the following method:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (other == null || getClass() != other.getClass()) return false;
    Point p = (Point) other;
    return x == p.x && y == p.y;
}
```

This is a **replacement snippet inside the `Point` class**, not a standalone program. Then `Point.equals(ColoredPoint)` and `ColoredPoint.equals(Point)` both return `false`. For two objects that are both `ColoredPoint`, calling `super.equals(p)` in the subclass can still compare the coordinates and then check the color.

Note: `getClass()` treats the runtime class as part of logical identity. If the problem genuinely requires objects of different classes to be equal, strict class checking may be inappropriate. There is no mechanical one-line replacement for every hierarchy model.

### Solution C: A Unified Equality Rule Across the Entire Hierarchy

If cross-class equality must be allowed, the entire hierarchy must share how identity is defined and preserve **both symmetry and transitivity**. You cannot have the superclass treat coordinates as sufficient while the subclass both requires a color and expects comparisons via the superclass to uphold the contract in all cases.

One option is to place all equality-determining properties into a single unified value model; another is to define independent value types and convert data to a common canonical form before comparing. When there is no clear business reason for cross-type equality, `final`/`record` and composition are usually easier to maintain.

## 5. How to Test and Common Mistakes

Pairwise testing must observe **two separate calls**:

```java
boolean leftToRight = Objects.equals(a, b);
boolean rightToLeft = Objects.equals(b, a);
if (leftToRight != rightToLeft) {
    throw new AssertionError("Broken symmetry");
}
```

The snippet above uses existing `a` and `b`; the `assertSymmetric` helper in the full program is the runnable version. `Objects.equals(a, b)` only handles `null` safely and then relies on `a.equals(b)`; **it does not fix an asymmetric equality relation**. Therefore, it must be compared against `Objects.equals(b, a)`.

Build a test suite of pairs including: same class/same value; same class/different value; superclass–subclass objects in both directions; two different subclasses; an object with `null`; and two references pointing to the same object. Superclass–subclass pairs are crucial because they expose inconsistent type-checking criteria. Beyond symmetry, verify reflexivity, transitivity, consistency, and the hash condition for equal objects.

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Superclass uses broad `instanceof`, subclass accepts only the subclass | One direction is `true`, the other is `false` | Unify the type scope considered equal |
| Testing only `a.equals(b)` | Misses asymmetric reverse results | Also test `b.equals(a)` |
| Writing `equals(Point)` instead of `equals(Object)` | This is an overload, not overriding `Object`'s method | Use the exact signature and `@Override` |
| Overriding `equals` but forgetting `hashCode` | Two equal objects may yield different hashes | Build both using the same equality relation |
| Using `==` to compare objects that need value equality | Compares reference identity instead of value equality | Clarify whether identity or logical equality is intended |
| Using mutable properties in equality/hash of `HashMap` keys | Keys may become unfindable after mutation | Prefer immutable value keys |

**Self-check exercise:** `A.equals` checks only `id` and accepts `instanceof A`; subclass `B.equals` accepts only `B`, checking both `id` and `role`. With `new A(7)` and `new B(7, "admin")`, the `A → B` direction will be `true`, while the `B → A` direction will be `false`. Any fix must make both directions agree while preserving the remaining `equals` contract requirements.

Before implementing `equals`, clearly define **which two types are allowed to be equal and based on which properties**, then test every pair in both directions.