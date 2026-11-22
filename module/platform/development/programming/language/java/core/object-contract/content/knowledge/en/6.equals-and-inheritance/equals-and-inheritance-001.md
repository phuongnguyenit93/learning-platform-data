# Extending a Class with `equals()` and the Risk of Breaking Symmetry

## Objective

This lesson focuses on an error-prone situation when designing **object equality** in Java: a parent class already overrides `equals(Object)`, and a subclass inherits or changes the equality definition, especially when the subclass adds a field that needs to be compared. You will understand why a seemingly reasonable implementation violates **symmetry**, why a naive patch can break **transitivity**, and how to choose a safe design.

In the example, a point with coordinates `(x, y)` and a point that also has a color will help illustrate the conflict between “equal by coordinates” and “equal by both coordinates and color”.

## 1. The Contract of `equals(Object)`

`equals(Object)` is a method of `java.lang.Object`. If you override it to define **value/semantic equality**, the program must maintain the following properties for non-`null` references:

| Property | Statement | Example |
| --- | --- | --- |
| **Reflexive** | `x.equals(x)` must be `true` | An object equals itself |
| **Symmetric** | `x.equals(y)` and `y.equals(x)` must return the same result | One side cannot unilaterally recognize “equality” |
| **Transitive** | If both `x.equals(y)` and `y.equals(z)` are true, then `x.equals(z)` must be true | The equality relation does not contradict itself through an intermediate object |
| **Consistent** | When the information used for comparison does not change, repeated calls return the same result | Does not arbitrarily change results between two calls |
| **Against `null`** | `x.equals(null)` must be `false` | No object equals `null` |

**Constraint tied to `hashCode()`:** If `a.equals(b)` returns `true`, then `a.hashCode() == b.hashCode()` **must** hold. The reverse direction is **not required**: two different objects can still share the same hash. If you override `equals`, you usually must override `hashCode` in sync; otherwise, lookups in `HashMap` and `HashSet` can fail relative to expected behavior.

This contract applies **across classes** whenever an `equals` call is allowed to compare a parent-class object with a subclass object. The contract does not disappear just because the classes are in an inheritance hierarchy.

## 2. Root of the Problem: Parent Class and Subclass Want Different Comparisons

Suppose there are two types:

```text
Point(x, y)
   ▲
   │ extends
   │
ColoredPoint(x, y, color)
```

For `Point`, two points with the same `x` and `y` are considered equal. For `ColoredPoint`, the designer may want color to also participate in determining equality.

Consider:

```text
p = Point(1, 2)
r = ColoredPoint(1, 2, "red")
```

- If `p.equals(r)` is called, the parent class may treat `r` only as a `Point`, and conclude **equal** based on coordinates.
- If `r.equals(p)` is called, the subclass may require the other side **to also have a color**, and conclude **not equal**.
- The same pair of objects returns different results in the two comparison directions: **symmetry violation**.

This stems from an **information mismatch**: `Point` does not have a `color` field to compare, whereas `ColoredPoint` treats `color` as part of its value identity. Having `ColoredPoint` inherit from `Point` does not automatically resolve the difference in equality definitions.

## 3. Runnable Example: Broken Symmetry and a Patch That Breaks Transitivity

**File `BrokenEqualsDemo.java`**, run with Java 17+:

```java
import java.util.Objects;

public class BrokenEqualsDemo {
    static class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Point other)) {
                return false;
            }
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    // Intentionally WRONG to demonstrate broken symmetry.
    static final class ColoredPoint extends Point {
        final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (!(obj instanceof ColoredPoint other)) {
                return false;
            }
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    // Intentionally WRONG: tries to make subclass equal to plain Point.
    static final class LenientColoredPoint extends Point {
        final String color;

        LenientColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (obj instanceof LenientColoredPoint other) {
                return super.equals(other) && color.equals(other.color);
            }
            return obj instanceof Point && super.equals(obj);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColoredPoint red = new ColoredPoint(1, 2, "red");

        System.out.println("plain.equals(red): " + plain.equals(red));
        System.out.println("red.equals(plain): " + red.equals(plain));

        LenientColoredPoint lenientRed =
                new LenientColoredPoint(1, 2, "red");
        LenientColoredPoint lenientBlue =
                new LenientColoredPoint(1, 2, "blue");

        System.out.println(
                "plain.equals(lenientRed): " + plain.equals(lenientRed));
        System.out.println(
                "lenientRed.equals(plain): " + lenientRed.equals(plain));
        System.out.println(
                "plain.equals(lenientBlue): " + plain.equals(lenientBlue));
        System.out.println(
                "lenientRed.equals(lenientBlue): "
                        + lenientRed.equals(lenientBlue));
    }
}
```

Compile and run:

```bash
javac BrokenEqualsDemo.java
java BrokenEqualsDemo
```

**Exact output:**

```text
plain.equals(red): true
red.equals(plain): false
plain.equals(lenientRed): true
lenientRed.equals(plain): true
plain.equals(lenientBlue): true
lenientRed.equals(lenientBlue): false
```

### 3.1. Why Is `plain.equals(red)` `true`?

The method invoked is `Point.equals` because the receiver variable `plain` points to an object whose actual class is `Point`. The expression:

```java
obj instanceof Point other
```

returns `true` when `obj` is a `Point` **or an object of a subclass of `Point`**. Since `ColoredPoint` is a `Point`, the comparison only checks `x`, `y` and returns `true`. Color is not checked.

When reversing to `red.equals(plain)`, the JVM calls the overridden method in `ColoredPoint`. The check `obj instanceof ColoredPoint` returns `false` because `plain` is a plain `Point`. The result becomes `false`. This is a **symmetry** violation, not random Java behavior.

### 3.2. Why Does “Allowing Comparison with Plain Point” Not Solve It?

The `LenientColoredPoint` class tries to handle comparison against `Point` by checking only coordinates. As a result:

```text
lenientRed.equals(plain)   = true
plain.equals(lenientRed)   = true
```

However, `lenientRed` and `lenientBlue` have different colors, so when comparing two objects of the same subclass, `equals` returns `false`. We have:

```text
lenientRed  ==(equals)==  plain
plain       ==(equals)==  lenientBlue
lenientRed  !=(equals)!=  lenientBlue
```

From `lenientRed.equals(plain) == true` and `plain.equals(lenientBlue) == true`, **transitivity** requires `lenientRed.equals(lenientBlue) == true`. Yet the program returns `false`: this “symmetry patch” breaks **transitivity**.

**Note:** Both subclasses in the example are intentionally written incorrectly to demonstrate the bug; **do not copy those two implementations into production code**.

### 3.3. `hashCode` Can Also Break Its Contract

In the example above, `Point` hashes by coordinates, while the subclass hashes with color added. Yet in some directions `equals` considers `Point` and the subclass to be equal. When two objects are equal but have different hash codes, the `equals/hashCode` contract is violated. You do not need to compare or guess specific hash numbers to recognize the problem: **the set of fields participating in equality and the set of fields participating in hashing must be compatible for every pair considered equal**.

This can create hard-to-reproduce bugs when used as `HashMap` keys or `HashSet` elements: hash structures rely on `hashCode` to locate candidate buckets before calling `equals`. Moreover, because `equals` is asymmetric, even operations using `equals` directly do not have consistent meaning regardless of object order.

## 4. Why Merely Switching `instanceof` to `getClass()` Still Requires a Design Decision

There are two common class-checking approaches:

```java
// Accepts subclass instances too if it is a Point:
obj instanceof Point

// Accepts only objects with the exact runtime class of the receiver:
obj != null && getClass() == obj.getClass()
```

- `instanceof` allows **including subclasses**. This can be appropriate if every subclass must have the **same equality definition** and does not add fields that are meaningful in `equals`.
- `getClass()` requires the **exact same runtime class**. It can help isolate equality relations across types, provided **all involved classes** implement it consistently.
- With `getClass()`, a `Point` and a `ColoredPoint` are always unequal, even when their coordinates match. This is an API **semantic decision**, not just a syntax-swapping trick.
- When using framework-generated proxy classes, exact runtime-class checks may be stricter than intended. You need to define the equality policy clearly according to the domain model, rather than defaulting to `getClass()` as the answer for every case.

If subclasses are allowed to change `equals` semantics, the designer must coordinate **the entire hierarchy**, including both `equals` and `hashCode`. Patching only a single branch is usually not enough.

## 5. Safe Approach A: Prefer Composition When the Subclass Adds Equality State

When color is genuinely part of the equality definition, the clearest solution is usually **not to inherit from a class that already has an incompatible `equals` policy**. Make the coordinate point type immutable, then create a colored point type that **contains** the coordinate point via composition.

**File `CompositionEqualityDemo.java`:**

```java
import java.util.Objects;

public class CompositionEqualityDemo {
    static final class Position {
        private final int x;
        private final int y;

        Position(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Position other)) {
                return false;
            }
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint {
        private final Position position;
        private final String color;

        ColoredPoint(Position position, String color) {
            this.position = Objects.requireNonNull(position);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof ColoredPoint other)) {
                return false;
            }
            return position.equals(other.position)
                    && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(position, color);
        }
    }

    public static void main(String[] args) {
        Position p1 = new Position(1, 2);
        Position p2 = new Position(1, 2);
        ColoredPoint red1 = new ColoredPoint(p1, "red");
        ColoredPoint red2 = new ColoredPoint(p2, "red");
        ColoredPoint blue = new ColoredPoint(p1, "blue");

        System.out.println("p1.equals(p2): " + p1.equals(p2));
        System.out.println("red1.equals(red2): " + red1.equals(red2));
        System.out.println(
                "red1.hashCode() == red2.hashCode(): "
                        + (red1.hashCode() == red2.hashCode()));
        System.out.println("red1.equals(blue): " + red1.equals(blue));
        System.out.println("red1.equals(p1): " + red1.equals(p1));
    }
}
```

```bash
javac CompositionEqualityDemo.java
java CompositionEqualityDemo
```

**Exact output:**

```text
p1.equals(p2): true
red1.equals(red2): true
red1.hashCode() == red2.hashCode(): true
red1.equals(blue): false
red1.equals(p1): false
```

Characteristics of this design:

1. `Position` and `ColoredPoint` are two `final` classes, so no unexpected subclass can inherit from them and change the comparison policy.
2. Two `Position` objects are equal when their coordinates match; two `ColoredPoint` objects are equal when **both position and color** match.
3. A `ColoredPoint` does not claim to be a `Position`: there is no situation where the parent agrees and the child refuses.
4. Both types are immutable in this example: the `final` fields and held components (`Position`, `String`) are all immutable; as a result, hash values do not change after insertion into hash collections.
5. `ColoredPoint`'s `hashCode` uses the exact components that participate in `equals`; two equal objects are guaranteed to have the same hash code.

If the goal is concise value data types on Java 17+, you can use `record`; record components participate in `equals` and `hashCode` by default:

```java
record Position(int x, int y) {}
record ColoredPoint(Position position, String color) {}
```

This record snippet illustrates standalone declarations (which can be placed at an appropriate file/package scope). Each record is implicitly `final`, so it cannot be inherited to silently alter the comparison policy. If a record component is a mutable object, the record itself **does not automatically deep-copy or make that component immutable**.

## 6. Safe Approach B: Keep Inheritance but Explicitly Forbid Cross-Class Equality

In systems that already use inheritance and want `Point` to **never equal** any subclass, an exact runtime class check can be applied at the parent class; a subclass that adds fields overrides `equals` and `hashCode` consistently.

**File `StrictClassEqualityDemo.java`:**

```java
import java.util.Objects;

public class StrictClassEqualityDemo {
    static class Point {
        final int x;
        final int y;

        Point(int x, int y) {
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
            Point other = (Point) obj;
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(getClass(), x, y);
        }
    }

    static final class ColoredPoint extends Point {
        final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (!super.equals(obj)) {
                return false;
            }
            ColoredPoint other = (ColoredPoint) obj;
            return color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        Point red1 = new ColoredPoint(1, 2, "red");
        Point red2 = new ColoredPoint(1, 2, "red");
        Point blue = new ColoredPoint(1, 2, "blue");

        System.out.println("plain.equals(red1): " + plain.equals(red1));
        System.out.println("red1.equals(plain): " + red1.equals(plain));
        System.out.println("red1.equals(red2): " + red1.equals(red2));
        System.out.println("red1.equals(blue): " + red1.equals(blue));
        System.out.println(
                "equal red points have equal hashes: "
                        + (red1.hashCode() == red2.hashCode()));
    }
}
```

```bash
javac StrictClassEqualityDemo.java
java StrictClassEqualityDemo
```

**Exact output:**

```text
plain.equals(red1): false
red1.equals(plain): false
red1.equals(red2): true
red1.equals(blue): false
equal red points have equal hashes: true
```

Explanation:

- In `Point.equals`, `getClass()` returns the actual class of the receiver object. A plain `Point` and a `ColoredPoint` are always treated as different classes, **from both directions**.
- In `ColoredPoint.equals`, calling `super.equals(obj)` checks the same runtime class and coordinates first. Because that check succeeds only when both are `ColoredPoint`, casting `(ColoredPoint) obj` is safe.
- The subclass additionally checks `color` and adds `color` to `hashCode`. Objects are considered equal under the same policy.
- `Point.hashCode` includes the runtime class in its hash formula. This aligns with the decision that different classes are not considered equal. Two objects of different classes may still coincidentally have the same hash; that is fine.

**Design limitation:** This approach accepts that the parent type and child type are **not value-equal** even when they share the same coordinates. It may not fit if callers expect a polymorphic relation where “every Point with the same coordinates is equal”. You should not choose this approach without aligning on API semantics. The example makes the subclass `final` so that no grandchild class can add further equality state.

## 7. What If Polymorphic Equality Between Parent and Child Is Required?

There are cases where an `is-a` relationship goes along with an intentional shared equality definition: every object in a hierarchy is compared by the **same set of properties** defined by the parent class. In that case, a subclass **must not arbitrarily add conditions** that alter the rule for only one comparison direction.

For example, if coordinates alone define equality for the **entire hierarchy** and color is only a display attribute, then it is acceptable that:

```text
Point(1, 2) equals ColoredPoint(1, 2, "red")
ColoredPoint(1, 2, "red") equals ColoredPoint(1, 2, "blue")
```

However, if users actually expect two different colors to be two different values, this policy **does not satisfy domain requirements**; use composition or separate types instead of pretending color does not matter.

Some complex hierarchies use the `canEqual` pattern to coordinate mutual agreement between both sides. That pattern requires design and testing across all parent/child classes—merely adding one method does not automatically guarantee both symmetry and transitivity. In the colored-point problem, composition or an explicit class-isolation policy is usually easier to verify.

## 8. Review Checklist for `equals` with Inheritance

When reading or writing a class that inherits from a class overriding `equals`, check in sequence:

1. **Identify the meaning of equality:** Is this a value object or an entity with business identity? Which attributes genuinely participate in comparison?
2. **Identify the comparison scope:** Does the parent class use `instanceof` to allow subclasses, or `getClass` to require the exact same runtime class?
3. **Check whether any subclass adds new state:** Does that state belong to the equality definition, or is it merely metadata/presentation?
4. **Test both directions:** `a.equals(b)` and `b.equals(a)`, with `a` as parent and `b` as child. Do not test only two instances of the same class.
5. **Test triples:** With objects across parent/child and two different subclasses, check transitivity; triples are precisely where naive patches usually fail.
6. **Review `hashCode` and immutability:** Every pair with `equals == true` must have equal hash codes. Avoid mutating fields used in hashing while the object is a `HashSet` element or `HashMap` key.
7. **Check `null`, self, and edge values:** `a.equals(a)`, `a.equals(null)`, and cases where component fields may be `null`.

A meaningful test table for the example with `Point p`, `ColoredPoint red`, and `ColoredPoint blue`:

| Test | Broken implementation in Section 3 | Class-isolation policy in Section 6 |
| --- | --- | --- |
| `p.equals(red)` | `true` | `false` |
| `red.equals(p)` | `false` (breaks symmetry) | `false` |
| `red.equals(blue)` when colors differ | `false` | `false` |
| Two ColoredPoints with same coordinates and same color | `true` | `true` |
| Do two objects with `equals == true` share the same `hashCode`? | Not guaranteed for all pairs | Guaranteed under the given implementation |

*Table uses `ColoredPoint` (the type-restricted version), not `LenientColoredPoint`, from Section 3.*

## 9. Common Reasoning Mistakes

- **“Using `instanceof` is always good because it supports polymorphism.”** Not necessarily: `instanceof` in the parent allows comparing against subclasses, but a subclass may have stricter value rules. Type polymorphism does not mean objects of those types must be equal.
- **“Adding `color` to `ColoredPoint.equals` is enough.”** Not enough: the parent class may still return `true` in the reverse direction, breaking symmetry.
- **“Making the subclass equal the parent when coordinates match fixes it.”** Not necessarily: two subclasses with different colors may both equal a parent object yet not equal each other, breaking transitivity.
- **“`hashCode` is independent of `equals`.”** False: equal objects must have the same hash. Different hashes for an equal pair make hash structures behave unreliably.
- **“Switching everything to `getClass()` is always standard.”** Not true for every model, especially when the API needs polymorphic equality or handles proxies. This is a design choice with specific consequences.
- **“Making the `color` field `final` is enough.”** `final` keeps the reference/field unchanged, but does not resolve the equality conflict between parent class and subclass.

## Self-Check

**Question 1.** Parent class `Vehicle` checks `obj instanceof Vehicle` and compares `id`; subclass `ElectricVehicle` requires the other side to be `ElectricVehicle` and also compares `batteryModel`. What is the risk?  
**Answer:** A `Vehicle` and an `ElectricVehicle` with the same `id` can be considered equal by the parent class while rejected by the subclass, breaking symmetry.

**Question 2.** If the subclass changes `equals` to return `true` when compared with a parent class having the same `id`, while still comparing `batteryModel` when meeting another subclass, what problem can occur?  
**Answer:** Two subclasses with different `batteryModel` values can both equal a parent object without equaling each other, violating transitivity.

**Question 3.** Why can we not simply add `color` to `hashCode` and ignore `equals`?  
**Answer:** If the parent class's `equals` still treats two objects as equal based on coordinates, the subclass's hash can differ from the parent class's hash, violating the “equal objects must have equal hashes” requirement.

**Question 4.** When is composition a better fit than inheritance?  
**Answer:** When the extended object has a new equality definition that includes additional state, and that definition cannot simultaneously preserve symmetry/transitivity with the parent class's policy.

## Conclusion

**The `equals` contract applies across all objects being compared, even when they belong to classes in the same inheritance hierarchy.** A parent class comparing with `instanceof` while a subclass adds equality conditions very easily causes **broken symmetry**; trying to loosen comparisons against the parent can turn into **broken transitivity**. Decide the equality semantics upfront, use composition and `final` classes for value objects when appropriate, or enforce a consistent runtime-class policy across the hierarchy. Always check `equals`, `hashCode`, and both comparison directions together.
