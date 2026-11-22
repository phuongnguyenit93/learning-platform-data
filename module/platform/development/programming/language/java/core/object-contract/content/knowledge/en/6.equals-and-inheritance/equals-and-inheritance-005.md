# Calling `super.equals()` and What That Does Not Automatically Guarantee

When a Java class inherits from another class, calling `super.equals(other)` in the subclass's `equals()` looks like a way to reuse the common comparison logic. **It only calls the parent class's `equals()` implementation; it does not automatically guarantee the `equals()` contract across the entire inheritance tree.** In particular, parent class and subclass can disagree on what kinds of objects are allowed to be equal; this breaks **symmetry** or **transitivity** even when each individual field check looks reasonable.

This lesson focuses on how `super.equals()` works, typical bugs when adding state to a subclass, and safe design alternatives.

## 1. What Does `super.equals(other)` Actually Do?

Inside a subclass method, the statement:

```java
@Override
public boolean equals(Object other) {
    return super.equals(other);
}
```

calls the `equals(Object)` implementation inherited from the parent class. The meaning of the statement depends on **how the parent class implemented `equals()`**:

- If the parent class did not override `equals()`, the call ultimately uses `Object.equals()`: only two references pointing to the same object are equal (`this == other`).
- If the parent class overrode `equals()` to compare certain fields, the call checks the exact conditions the parent class wrote, including its type-checking policy (`instanceof` or `getClass()`).
- If the parent class has an overridden helper method called from `equals()`, execution inside can still be affected by polymorphism. Calling `super.equals()` does not mean the entire execution is isolated from the subclass.

Example:

```java
class Parent {
    final int id;

    Parent(int id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof Parent other && id == other.id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }
}

class Child extends Parent {
    final String label;

    Child(int id, String label) {
        super(id);
        this.label = label;
    }

    // Does not override equals/hashCode:
    // label does not participate in equality.
}
```

`new Child(1, "A").equals(new Child(1, "B"))` returns `true` because the subclass inherits the rule that considers only `id`. This may be intentional if `label` is merely auxiliary info, but wrong if `label` is also part of the value that must be compared. **Inheriting `equals()` does not automatically decide which new fields matter.**

Conversely, having the subclass write `return super.equals(obj) && ...` only adds a condition in the **direction called from the subclass**. The parent class still uses its old definition when comparing itself against the subclass.

## 2. The `equals()` Contract to Preserve Under Inheritance

For non-null objects `x`, `y`, `z`, a valid equality relation must satisfy:

1. **Reflexive:** `x.equals(x)` is `true`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` have the same value.
3. **Transitive:** if `x.equals(y)` and `y.equals(z)`, then `x.equals(z)`.
4. **Consistent:** when the state used for comparison does not change, repeated calls must return the same result.
5. **Against null:** `x.equals(null)` is `false`.

When overriding `equals()`, you must also preserve the contract with `hashCode()`: if `x.equals(y)` is `true`, then `x.hashCode() == y.hashCode()`. The converse is not required. Having a parent class with a valid `hashCode()` implementation for **the parent class's own equality rule** does not mean that rule remains valid if the subclass redefines equality.

**Core point:** `equals()` is a relation between **two objects**, so you must examine both parent → child and child → parent directions, as well as chains of **three objects** when evaluating transitivity.

## 3. Symmetry Bug: Parent Accepts Subclass, Subclass Rejects Parent

Suppose `Point` only has coordinates `(x, y)` and uses `instanceof Point` in `equals()`. `ColoredPoint` adds color. The subclass only allows comparisons with `ColoredPoint`, then calls `super.equals(other)` and compares color as well.

- `point.equals(coloredPoint)` can be `true` because a `ColoredPoint` **is also** a `Point` and has the same coordinates.
- `coloredPoint.equals(point)` is `false` because the `point` object is not a `ColoredPoint`.

Both methods accurately read the fields they care about, yet **symmetry is violated**. Having `super.equals()` return `true` for two subclass objects with the same coordinates cannot make the parent class magically aware of the new color condition.

## 4. Transitivity Bug: Trying to Let Subclass Compare Equal to Parent When Appropriate

A tempting patch is to let the subclass compare like `Point` if the other object is only a `Point`, while also comparing color if both are `ColoredPoint`. Then:

- `red.equals(point)` is `true`, because coordinates match.
- `point.equals(blue)` is `true`, because coordinates match.
- `red.equals(blue)` is `false`, because colors differ.

Symmetry for these three comparisons may hold, yet **transitivity is broken**: from `red == point` and `point == blue`, `red == blue` ought to follow.

### 4.1. Running Both Bugs with Java 17+

Save as file **`EqualsInheritancePitfall.java`**:

```java
import java.util.Objects;

class Point {
    private final int x;
    private final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof Point other
                && x == other.x
                && y == other.y;
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y);
    }
}

// Version 1: accepts only the exact subclass group.
// Breaks symmetry while Point still accepts every instanceof Point.
class StrictColorPoint extends Point {
    private final String color;

    StrictColorPoint(int x, int y, String color) {
        super(x, y);
        this.color = Objects.requireNonNull(color);
    }

    @Override
    public boolean equals(Object obj) {
        if (!(obj instanceof StrictColorPoint other)) {
            return false;
        }
        return super.equals(obj) && color.equals(other.color);
    }

    // Intentionally keeps coordinate-based hashCode to isolate the symmetry bug.
    // Matching hashes are still valid; they cannot rescue a broken equals.
}

// Version 2: compares like Point when meeting a regular Point.
// Breaks transitivity when two subclasses have different colors.
class FlexibleColorPoint extends Point {
    private final String color;

    FlexibleColorPoint(int x, int y, String color) {
        super(x, y);
        this.color = Objects.requireNonNull(color);
    }

    @Override
    public boolean equals(Object obj) {
        if (!(obj instanceof Point)) {
            return false;
        }
        if (!(obj instanceof FlexibleColorPoint other)) {
            return super.equals(obj);
        }
        return super.equals(obj) && color.equals(other.color);
    }

    // Also uses coordinate-based hashCode, sufficient to illustrate
    // that a valid hashCode does not imply a valid equals.
}

public class EqualsInheritancePitfall {
    public static void main(String[] args) {
        Point point = new Point(2, 3);
        StrictColorPoint redStrict =
                new StrictColorPoint(2, 3, "red");

        System.out.println("point -> strict: "
                + point.equals(redStrict));
        System.out.println("strict -> point: "
                + redStrict.equals(point));

        FlexibleColorPoint red =
                new FlexibleColorPoint(2, 3, "red");
        FlexibleColorPoint blue =
                new FlexibleColorPoint(2, 3, "blue");

        System.out.println("red -> point: "
                + red.equals(point));
        System.out.println("point -> blue: "
                + point.equals(blue));
        System.out.println("red -> blue: "
                + red.equals(blue));
    }
}
```

Run:

```bash
javac EqualsInheritancePitfall.java
java EqualsInheritancePitfall
```

Output:

```text
point -> strict: true
strict -> point: false
red -> point: true
point -> blue: true
red -> blue: false
```

Both examples are **intentional counterexamples**, not `equals()` patterns to use in a project. In both, the subclasses inherit coordinate-based hashing to avoid introducing an additional hash discrepancy; **even when hash codes match, the symmetry/transitivity bugs still exist**. Do not assume updating `hashCode()` can fix these logic bugs.

## 5. Does `getClass()` Help?

A straightforward option is for the parent class to allow equality only for the **exact same runtime class**:

```java
if (obj == null || getClass() != obj.getClass()) {
    return false;
}
```

When both parent and subclass respect that policy, `Point` will **not equal** `ColoredPoint` even with matching coordinates. Thus there is no situation where the parent accepts a subclass while the subclass rejects the parent.

If the parent class uses `getClass()` and the subclass overrides `equals()`, the subclass **can still call `super.equals()`** to reuse the coordinate comparison. For two objects of the same subclass, `getClass()` inside the parent method is still the runtime class of both objects, so the same-class check can succeed.

### 5.1. Safe Pattern: Same-Class Policy, Immutable State

Create the file **`SafeSuperEqualsDemo.java`**:

```java
import java.util.Objects;

class Coordinate {
    private final int x;
    private final int y;

    Coordinate(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (obj == null || getClass() != obj.getClass()) {
            return false;
        }
        Coordinate other = (Coordinate) obj;
        return x == other.x && y == other.y;
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y);
    }
}

final class ColorCoordinate extends Coordinate {
    private final String color;

    ColorCoordinate(int x, int y, String color) {
        super(x, y);
        this.color = Objects.requireNonNull(color);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!super.equals(obj)) {
            return false;
        }
        ColorCoordinate other = (ColorCoordinate) obj;
        return color.equals(other.color);
    }

    @Override
    public int hashCode() {
        return 31 * super.hashCode() + color.hashCode();
    }
}

public class SafeSuperEqualsDemo {
    public static void main(String[] args) {
        Coordinate point = new Coordinate(2, 3);
        ColorCoordinate red =
                new ColorCoordinate(2, 3, "red");
        ColorCoordinate redCopy =
                new ColorCoordinate(2, 3, "red");
        ColorCoordinate blue =
                new ColorCoordinate(2, 3, "blue");

        System.out.println("point -> red: "
                + point.equals(red));
        System.out.println("red -> point: "
                + red.equals(point));
        System.out.println("red -> redCopy: "
                + red.equals(redCopy));
        System.out.println("red -> blue: "
                + red.equals(blue));
        System.out.println("equal hashes: "
                + (red.hashCode() == redCopy.hashCode()));
    }
}
```

Run:

```bash
javac SafeSuperEqualsDemo.java
java SafeSuperEqualsDemo
```

Output:

```text
point -> red: false
red -> point: false
red -> redCopy: true
red -> blue: false
equal hashes: true
```

**Why is this example consistent?**

1. `Coordinate.equals()` compares `getClass()` first, so it rejects objects of a different class. Calls from either side return `false` between `Coordinate` and `ColorCoordinate`.
2. For two `ColorCoordinate` objects, `super.equals()` compares coordinates (and enforces the same-class policy); then `ColorCoordinate.equals()` compares `color`.
3. `ColorCoordinate.hashCode()` combines the parent's hash code with `color`, matching the attributes examined by the subclass's `equals()`.
4. All data fields are `final`; the `ColorCoordinate` class is also `final`, so no new subclass can further extend its comparison logic.

**Limitation:** the `getClass()` policy defines *different runtime class means not equal*. This may not fit if the application intentionally needs polymorphic equality or has framework-generated proxies/subclasses. In addition, `Coordinate` in the example still permits inheritance; every new subclass with state participating in value must continue respecting the `equals()`/`hashCode()` policy. `super.equals()` cannot force future subclasses to do so automatically.

## 6. Other Ways to Structure the Design

### 6.1. Prefer Immutability, `final` Classes, `record`, or Composition

If subclasses only differ in value data, it is usually easier to preserve the contract by **not using inheritance to extend value identity**. Use two independent records:

```java
record PointValue(int x, int y) {}

record ColoredPointValue(int x, int y, String color) {}
```

Java automatically generates `equals()` and `hashCode()` for each record based on **that record's own** components, with comparison rules tied to each record type. Two `ColoredPointValue` instances with the same `x`, `y`, `color` will be equal; `PointValue` and `ColoredPointValue` are two independent types.

If you need to reuse shared data without inheriting an equality relation, use **composition**:

```java
record ColoredPointValue(PointValue point, String color) {}
```

This makes clear that color and coordinates jointly determine the value. However, if the domain treats color purely as auxiliary info and equality relies solely on coordinates, you must intentionally choose a different definition; do not mechanically compare all fields.

### 6.2. `final equals()` on the Parent Class

If all subclasses **genuinely share a single equality definition** (for example, all are identified solely by an immutable ID), the parent class can declare `equals()`/`hashCode()` as `final`, preventing subclasses from changing them:

```java
@Override
public final boolean equals(Object obj) {
    // Compares strictly according to a single chosen common rule.
}
```

This is appropriate only if no subclass needs to add attributes to equality; if a subclass needs to additionally distinguish color, making the parent's `equals()` `final` prevents color from participating in equality. `final` prevents overriding; **it does not by itself prove the rule in the parent class is right**.

### 6.3. The `canEqual` Pattern for Polymorphic Hierarchies

Some designs use a method like `canEqual(Object)` so both sides agree whether equality is permitted before checking fields:

1. The parent class checks that the other object is of a suitable type, then asks `other.canEqual(this)` to agree.
2. A subclass that adds state changes `canEqual()` to reject equality with a parent class that lacks that state.
3. The subclass checks new fields after calling `super.equals(other)`; every class in the hierarchy must implement the same convention.

This pattern helps build certain extensible hierarchies while preserving symmetry, but is harder to maintain: a single subclass ignoring the convention can break the contract. Merely adding a `canEqual()` call does not automatically guarantee all transitivity relations or hashing policies. When there is no explicit requirement for polymorphic inheritance, composition or immutable classes are usually easier to reason about.

## 7. What `super.equals()` Does Not Automatically Guarantee

| Common Misconception | Reality |
| --- | --- |
| “The parent already compares properly, so the subclass is surely right.” | The subclass may add state that alters equality, causing disagreement with the parent class. |
| “Calling `super.equals()` is enough to guarantee symmetry.” | It only checks one direction; the parent may accept the subclass while the subclass rejects the parent. |
| “If it is symmetric, transitivity must also hold.” | The type-flexible comparison version in Example 4 can still break transitivity. |
| “Since `super.equals()` was called, there is no need for `hashCode()`.” | If the subclass adds fields to equality, hashing must be designed consistently with the final definition. |
| “Adding `instanceof` in the subclass fixes it.” | Often only makes the subclass reject the parent without addressing how the parent views the subclass. |
| “Using `getClass()` is always better than `instanceof`.” | Fits exact class equality, but can be inconvenient with proxies and polymorphic semantics. |
| “If parent `equals()` uses reference equality, the subclass automatically compares data.” | If `super.equals()` ultimately resolves to `Object.equals()`, two distinct objects are rejected even when fields match. |
| “Two identical hashes prove the equals design is right.” | Hash collisions are allowed; hash codes do not prove symmetry or transitivity. |

`super.equals()` also does not automatically solve null comparison, avoiding cycles between object references, consistency when data mutates, or issues when parent/subclass contracts evolve across versions. All of those remain responsibilities of the value model and concrete implementation.

## 8. Checklist When Reviewing `equals()` with Inheritance

1. **Identify which implementation the parent actually invokes:** `Object.equals()`, an `instanceof`-based `equals()`, or a `getClass()`-based one? Do intermediate classes override it?
2. **Define equality clearly:** same ID, same value attributes, or only same concrete type? Do new subclass attributes participate?
3. **Test both directions:** `parent.equals(child)` and `child.equals(parent)` must match. Test both matching and differing coordinate/ID cases.
4. **Test three objects:** one parent and two subclasses matching in shared parts while differing in added fields; check transitivity.
5. **Audit the hash pair:** if the subclass's `equals()` extends the condition, the subclass's `hashCode()` must ensure two equal objects share the same hash; do not rely on hash collisions to cover up an `equals` bug.
6. **Check `null`, self, repeated calls, and mutable state.** Use immutable fields if objects are placed into a `HashSet` or used as `HashMap` keys.
7. **Examine consequences on collections:** when `equals()` is asymmetric or non-transitive, `HashSet.contains()`, `HashMap.get()`, or key deduplication can become unpredictable. `TreeSet`/`TreeMap` also have their own ordering contract via `compareTo()`/`Comparator`.
8. **Decide the inheritance policy:** `final`/record/composition, `getClass()`, or a cooperative contract like `canEqual`; do not mix incompatible rules across classes.

**Knowledge takeaway:** `super.equals(other)` is a call to reuse the parent-part comparison. To design `equals()` properly under inheritance, you must determine *whether both objects agree on the equality relation*, check symmetry and transitivity across class combinations, and keep `hashCode()` consistent. If adding state in a subclass makes the equality rule hard to express, consider separating values into immutable types or using composition.