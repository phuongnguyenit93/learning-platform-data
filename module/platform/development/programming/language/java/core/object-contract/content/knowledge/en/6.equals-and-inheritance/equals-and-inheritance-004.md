# Impact of Type-Checking Choices on Parent-Subclass Relationships When Implementing `equals()` in Java

When overriding `equals(Object)`, type checking determines not only whether a cast is safe: it also decides **which classes are allowed to consider each other's objects equal**. The difference between `instanceof` and `getClass()` is especially important in inheritance relationships, where a subclass may add state unknown to the parent class.

This lesson focuses on the impact of type-checking choices on **parent and subclass equality**, **symmetry** and **transitivity** bugs, and how to choose a design with a consistent `equals()`/`hashCode()` contract.

## 1. The `equals()` Contract to Preserve Under Inheritance

For non-`null` references, `equals()` must satisfy:

1. **Reflexive:** `a.equals(a)` is `true`.
2. **Symmetric:** `a.equals(b)` and `b.equals(a)` always return the same result.
3. **Transitive:** if `a.equals(b)` and `b.equals(c)` are true, `a.equals(c)` must also be true.
4. **Consistent:** the result does not change across calls when the state used for comparison does not change.
5. **Non-null:** `a.equals(null)` is always `false`.

At the same time, **if `a.equals(b)` is `true`, the hash codes `a.hashCode()` and `b.hashCode()` must be equal**. Conversely, two equal hash codes do not prove two objects are equal.

In inheritance, the difficulty is that the parent class only knows its own fields, while the subclass may add a field important to the value definition. If the parent allows comparison against the subclass while the subclass applies stricter conditions, the comparison easily loses symmetry. If you try to reconcile the two, the comparison can lose transitivity.

## 2. `instanceof` and `getClass()` Check Two Different Relationships

### Checking with `instanceof`

~~~java
if (!(other instanceof Point point)) {
    return false;
}
~~~

This is an illustrative snippet located **inside** the `equals(Object other)` method. Java 17 supports pattern matching with `instanceof`: when the condition succeeds, the `point` variable has type `Point` for immediate use.

The condition is true when the object belongs to class `Point` **or a subclass of `Point`** (and can also apply to an implemented interface). With `other == null`, `instanceof` returns `false`. Thus, using `instanceof` in `Point.equals` allows `Point` to compare coordinates of inherited classes as well, if they can be cast to `Point`.

### Checking with `getClass()`

~~~java
if (other == null || getClass() != other.getClass()) {
    return false;
}
~~~

This is also an illustrative snippet inside `equals(Object other)`. Checking `getClass()` requires the **exact same runtime class**: a `Point` instance and a `ColorPoint extends Point` instance are two different runtime types, so `Point.equals(colorPoint)` returns `false`, even when their coordinates are identical.

Checking `null` before `other.getClass()` is mandatory to avoid a `NullPointerException`. Inside an instance method, `getClass()` is equivalent to `this.getClass()`.

| Question | `other instanceof Point` | `getClass() == other.getClass()` in `Point.equals` |
|---|---|---|
| `other` is `Point` | `true` | `true` |
| `other` is `ColorPoint extends Point` | `true` | `false` |
| `other` is outside the `Point` family | `false` | `false` |
| `other == null` | `false` | Must check `null` first |

**Core difference:** `instanceof` treats *membership in a type hierarchy* as the condition to enter comparison; `getClass()` requires the *same runtime class*. Both are only the **type-checking step**, not sufficient by themselves for `equals()` to be correct: field comparisons, `hashCode()`, and subclass overrides must still follow the contract.

## 3. Symmetry Bug When the Parent Uses `instanceof` but the Subclass Adds a Field

Suppose `Point` has `x`, `y`; subclass `ColorPoint` adds `color`. The parent class wants to treat two points with the same coordinates as equal, while the subclass wants colors to also match.

- `Point.equals` uses `instanceof Point`, so it accepts a `ColorPoint` object based solely on `x`, `y`.
- `ColorPoint.equals` accepts only `ColorPoint` and requires matching colors.
- With `p = Point(1, 2)` and `red = ColorPoint(1, 2, "red")`, we get `p.equals(red) == true` yet `red.equals(p) == false`.

This is a **symmetry violation**: the same two objects produce different results depending on call order. The subclass adding a meaningful field is the deeper cause; `instanceof` allows the parent to compare against the subclass without letting the parent know the condition the subclass requires.

This bug also causes trouble for `hashCode()`. If `Point.hashCode()` uses coordinates while `ColorPoint.hashCode()` adds color, you can get a pair where `Point.equals(ColorPoint)` returns `true` yet their hashes differ, violating the hash contract as well. **Adding `hashCode()` to the subclass does not fix an asymmetric `equals()` bug**; the two methods must be designed together.

## 4. Trying to Fix Symmetry Can Break Transitivity

A common patch is to tell the subclass: if the other object is only the parent class, compare coordinates; if it is a subclass of the same kind, also compare color.

Then with the same coordinates:

- `red = ColorPoint(1, 2, "red")` equals `plain = Point(1, 2)`.
- `plain = Point(1, 2)` equals `blue = ColorPoint(1, 2, "blue")`.
- Yet `red` **does not equal** `blue` because their colors differ.

Result: `red.equals(plain)` is true **and** `plain.equals(blue)` is true, yet `red.equals(blue)` is false. The comparison has **lost transitivity**. Symmetry and consistent hashing can be made to work in this example, yet you still do not have a valid equality relation. “Compare by parent class when not the same subclass” is not a general solution.

The fundamental issue lies in the definition: if you want a colorless `Point` to equal two differently colored `ColorPoint` instances, then by transitivity those two colored points would also have to equal each other; that contradicts the requirement that color is part of the value. This definitional contradiction cannot be solved by swapping `instanceof` syntax.

## 5. Runnable Java 17 Example: Symmetry Bug, Transitivity Bug, and Fixes

Save the following entire program as **`EqualsInheritanceDemo.java`**. The nested classes use distinct names so the three scenarios do not interfere with one another.

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Objects;

public class EqualsInheritanceDemo {

    // 1) Parent class uses instanceof: lets subclass pass.
    static class NaivePoint {
        final int x, y;

        NaivePoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof NaivePoint p)) return false;
            return x == p.x && y == p.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    // Subclass tightens condition: causes symmetry bug.
    static class NaiveColorPoint extends NaivePoint {
        final String color;

        NaiveColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof NaiveColorPoint p)) return false;
            return super.equals(other)
                    && Objects.equals(color, p.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    // 2) Version trying to reconcile parent and subclass.
    static class FlexiblePoint {
        final int x, y;

        FlexiblePoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof FlexiblePoint p)) return false;
            return x == p.x && y == p.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static class FlexibleColorPoint extends FlexiblePoint {
        final String color;

        FlexibleColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof FlexiblePoint)) return false;
            if (!(other instanceof FlexibleColorPoint p)) {
                return super.equals(other); // Only compare coordinates with parent class.
            }
            return super.equals(other)
                    && Objects.equals(color, p.color);
        }

        // Intentionally inherits coordinate-based hashCode so equal
        // parent/child pairs have the same hash code.
        // This CANNOT fix the transitivity bug.
    }

    // 3) Exact runtime class solution: getClass().
    static class StrictPoint {
        final int x, y;

        StrictPoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (other == null || getClass() != other.getClass()) {
                return false;
            }
            StrictPoint p = (StrictPoint) other;
            return x == p.x && y == p.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static class StrictColorPoint extends StrictPoint {
        final String color;

        StrictColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (other == null || getClass() != other.getClass()) {
                return false;
            }
            StrictColorPoint p = (StrictColorPoint) other;
            return super.equals(other)
                    && Objects.equals(color, p.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    // 4) Composition/value type: no value inheritance.
    record ColoredPoint(int x, int y, String color) {}

    public static void main(String[] args) {
        NaivePoint p = new NaivePoint(1, 2);
        NaiveColorPoint red = new NaiveColorPoint(1, 2, "red");
        System.out.println("naive parent -> child: " + p.equals(red));
        System.out.println("naive child -> parent: " + red.equals(p));

        FlexiblePoint plain = new FlexiblePoint(1, 2);
        FlexibleColorPoint flexibleRed =
                new FlexibleColorPoint(1, 2, "red");
        FlexibleColorPoint flexibleBlue =
                new FlexibleColorPoint(1, 2, "blue");
        System.out.println("flexible red -> plain: "
                + flexibleRed.equals(plain));
        System.out.println("flexible plain -> blue: "
                + plain.equals(flexibleBlue));
        System.out.println("flexible red -> blue: "
                + flexibleRed.equals(flexibleBlue));

        StrictPoint strictPlain = new StrictPoint(1, 2);
        StrictColorPoint strictRed = new StrictColorPoint(1, 2, "red");
        StrictColorPoint sameRed = new StrictColorPoint(1, 2, "red");
        StrictColorPoint strictBlue = new StrictColorPoint(1, 2, "blue");
        System.out.println("strict parent -> child: "
                + strictPlain.equals(strictRed));
        System.out.println("strict child -> parent: "
                + strictRed.equals(strictPlain));
        System.out.println("strict red -> red copy: "
                + strictRed.equals(sameRed));
        System.out.println("strict red -> blue: "
                + strictRed.equals(strictBlue));
        System.out.println("strict set size: "
                + new HashSet<>(List.of(
                        strictPlain, strictRed, sameRed, strictBlue)).size());

        ColoredPoint valueA = new ColoredPoint(1, 2, "red");
        ColoredPoint valueB = new ColoredPoint(1, 2, "red");
        System.out.println("record value equality: "
                + valueA.equals(valueB));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac EqualsInheritanceDemo.java
java EqualsInheritanceDemo
~~~

Expected output:

~~~text
naive parent -> child: true
naive child -> parent: false
flexible red -> plain: true
flexible plain -> blue: true
flexible red -> blue: false
strict parent -> child: false
strict child -> parent: false
strict red -> red copy: true
strict red -> blue: false
strict set size: 3
record value equality: true
~~~

**Reading the output across the three problem layers:**

- **Naive:** `NaivePoint` accepts `NaiveColorPoint`; the reverse direction is rejected. One direction `true`, one direction `false`: **symmetry fails**.
- **Flexible:** both `red` and `blue` equal `plain`, yet do not equal each other: **transitivity fails**. This strategy should not be used.
- **Strict:** cross-type comparisons return `false` in both directions; two `StrictColorPoint` objects with the same coordinates and color are equal. `HashSet` holds 3 distinct values: the plain point, the red point, and the blue point.
- **Record:** `ColoredPoint` is an immutable value type and is implicitly `final`; Java generates `equals()`/`hashCode()` from its components. No `ColoredPoint` subclass exists to silently alter the meaning of equality.

Important note in the **Strict** example: the subclass calls `super.equals(other)`, yet both parent and subclass check the exact runtime class before comparing fields. If you omit the `getClass()` check in the parent class, or override inconsistently between classes, the result can differ.

## 6. When to Use `getClass()`?

Use `getClass()` when **two objects should only be equal if they have the exact same runtime type**. This is often a clear choice when a base class **can be inherited**, and subclasses are allowed to add fields meaningful to equality.

Pattern for the parent class:

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (other == null || getClass() != other.getClass()) {
        return false;
    }
    Point p = (Point) other;
    return x == p.x && y == p.y;
}
~~~

This is a snippet placed inside a `Point` class that already has fields `x`, `y`; not a standalone program. A subclass adding equality data can check `getClass()` again, call `super.equals(other)`, then compare its own fields and override `hashCode()` accordingly.

**Advantages:** clear equality boundaries between classes; parent and subclass are not automatically treated as the same value merely because they share fields.

**Trade-offs:** two entities with the same business data but **two different runtime types** will not be equal. This can cause surprises when using dynamically generated **proxy subclasses** from libraries (such as certain ORM mechanisms). If an application uses proxies, you should investigate the framework's identity/equality rules and design specifically for that entity model; it cannot be safely fixed merely by replacing `getClass()` with `instanceof`.

`getClass()` also **does not automatically guarantee** the contract: you still must avoid mutable fields in hash keys, write compatible hashes, and maintain equality when subclasses add state.

## 7. When to Use `instanceof`?

`instanceof` makes sense when there is **one shared value concept across the entire hierarchy**, and subclasses must not alter the equality criterion, or when the class **does not allow inheritance**.

Example for an immutable, `final` class:

~~~java
final class Point {
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
        return java.util.Objects.hash(x, y);
    }
}
~~~

This is a complete class declaration, though without `main`; it can be used alongside other classes in a project. Because `Point` is `final`, there is no `ColorPoint extends Point`, so the pitfall of a subclass adding fields does not arise. `record Point(int x, int y) {}` is also a concise option when it fits the data design.

If the class still allows inheritance and uses `instanceof`, you must answer the question: **is a subclass allowed to add fields affecting equality?** If not, consistent design conventions and constraints are needed—for example, subclasses that only add behavior without changing value identity. Relying solely on a promise that “subclasses will not override equals” does not protect against unintended changes later.

## 8. The `canEqual` Pattern for Hierarchies Needing Extensibility

Another technique is to let both sides **agree to comparability**. The parent class asks whether the other object agrees to belong to the same equality domain via `canEqual`. A subclass adding state can refuse equality with the parent class to preserve symmetry.

Illustration of the essentials (two classes used in a hierarchy, without `main`):

~~~java
import java.util.Objects;

class CanPoint {
    private final int x, y;

    CanPoint(int x, int y) {
        this.x = x;
        this.y = y;
    }

    protected boolean canEqual(Object other) {
        return other instanceof CanPoint;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof CanPoint p)) return false;
        return p.canEqual(this) && x == p.x && y == p.y;
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y);
    }
}

class CanColorPoint extends CanPoint {
    private final String color;

    CanColorPoint(int x, int y, String color) {
        super(x, y);
        this.color = color;
    }

    @Override
    protected boolean canEqual(Object other) {
        return other instanceof CanColorPoint;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof CanColorPoint p)) return false;
        return p.canEqual(this)
                && super.equals(other)
                && Objects.equals(color, p.color);
    }

    @Override
    public int hashCode() {
        return Objects.hash(super.hashCode(), color);
    }
}
~~~

Here `new CanPoint(1,2).equals(new CanColorPoint(1,2,"red"))` returns `false`: the subclass object does not `canEqual` the parent class. The reverse direction is also `false` because the `instanceof CanColorPoint` check fails. Two `CanColorPoint` instances with the same data are equal and share the same hash.

`canEqual` is useful when you genuinely need an **open hierarchy** with a controlled equality contract, yet **it does not automatically solve every inheritance branch**. Other subclasses that add meaningful state still must coordinate `canEqual`, `equals`, and `hashCode`, and preserve transitivity across types. When there is no specific requirement for inheritance, `final`, `record`, or **composition** usually reduces risk.

## 9. Alternative Designs: Composition and Distinguishing Entities from Value Objects

Data inheritance is not always the right relationship. If `ColorPoint` is essentially “a value consisting of a point and a color”, you can use composition:

~~~java
record Point(int x, int y) {}
record ColoredPoint(Point point, String color) {}
~~~

These are two independent record types. `ColoredPoint` **contains** a `Point` rather than **being a subclass of** `Point`. There is no requirement for `Point.equals(ColoredPoint)` because the two types represent two different value domains. Record-generated equality relies on the components; immutability and having no subclasses make the contract predictable.

For **entities**, you must carefully examine whether business identity is stable. Two subclasses representing the same persisted entity may need a different policy from value objects, especially with an ORM/proxies. If equality is by ID, you must decide behavior for unassigned IDs, differing runtime classes, and how to keep hashes constant over the entity lifecycle. Do not use `instanceof` as a blanket patch for all entities.

## 10. Direct Impact on Collections

A mistake when writing `equals()` does not stop at an `if` statement:

- `HashSet.add`/`contains` and `HashMap.put`/`get` require `equals()` **and** `hashCode()` to follow the contract. If `a.equals(b)` depends on call direction, key recognition can depend on lookup order and implementation details; if hashes are also inconsistent, logically “equal” objects may be stored in different buckets.
- `List.contains` uses equality to search for elements; with an asymmetric relation, results can defy intuition when swapping the search object and the element stored in the list.
- `TreeSet`/`TreeMap` use `compareTo` or `Comparator` to determine key equivalence; `compare == 0` does not necessarily imply `equals == true`. When coordinating equality and ordering, both contracts must be designed together, yet **switching `getClass`/`instanceof` does not automatically fix a comparator**.

If fields participating in equality/hash can mutate after insertion into a hash collection, even an otherwise correct `equals` implementation can cause lookups to fail. For value objects, prefer immutability.

## 11. Checklist Before Deciding on Type Checking

| Design Question | Choice Guidance |
|---|---|
| Can the class be inherited? | If unnecessary: consider `final` or `record` |
| Does the subclass add fields determining equality? | Avoid having `instanceof` in the parent accept the child under a broader definition |
| Is equality across different runtime classes a business requirement? | Allow only when cross-class equivalence is unified and preserves all contracts |
| Does every subclass need its own equality over full state? | Consider `getClass()` and coordinated overrides in each class |
| Are there framework-generated proxy classes? | Verify the framework's identity rules before choosing runtime-class equality |
| Is data inheritance actually needed? | Consider composition for value objects |
| Is the hash code derived from the exact fields used for comparison? | Test that equal objects share the same hash |
| Will it be used as a `HashMap`/`HashSet` key? | Prefer immutable state and a clear equality contract |

**Test the relation**, not just a few isolated pairs: check `a.equals(a)`, `a.equals(b) == b.equals(a)`, the triangle `a → b → c`, `null` cases, objects with different coordinates/different subclass fields, and hash codes of equal pairs. When the hierarchy is deep or has multiple branches, also test objects from sibling classes, not only one parent and one child.

## 12. Self-Check

**Question 1.** Parent class `Shape` uses `other instanceof Shape` and compares only `id`. Subclass `ColoredShape` adds color to `equals`. What risk appears?  
**Answer:** Symmetry can break: the parent considers two objects equal by ID while the subclass rejects the parent object. If the subclass's hash also considers color, there is also a risk of violating the hash contract.

**Question 2.** Does switching the parent class to `getClass()` automatically make every `equals()` in the hierarchy correct?  
**Answer:** No. It only rejects equality between different runtime classes. Field comparisons, hashing, immutability, and overrides in subclasses must still be right.

**Question 3.** Why should we not make `ColorPoint(red)` equal `Point` and `Point` equal `ColorPoint(blue)` while saying `red` differs from `blue`?  
**Answer:** Because it breaks transitivity of `equals()`. If A equals B and B equals C, then A must equal C.

**Question 4.** When a value class does not need inheritance and all fields must participate in equality, what is a simple choice?  
**Answer:** A `record` or an immutable `final` class, with `equals`/`hashCode` based on all meaningful state.

**Conclusion:** Choosing `instanceof` means allowing comparison within a **type family**; choosing `getClass()` means requiring the **exact same runtime class**. With inheritance, the most important question is: **does the subclass add state that changes the meaning of “equal”?** If so, set clear equality boundaries or change the data model to avoid symmetry, transitivity, and hash violations.