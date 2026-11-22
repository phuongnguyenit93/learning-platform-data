# Using Composition When Extending Values via Inheritance Makes the Contract Hard to Keep

## 1. The Problem: Adding “Value” to a Subclass Can Break the equals Contract

In Java, inheritance (`extends`) is appropriate when a child object can genuinely substitute for a parent object under the guarantees of the parent type. However, **inheriting a value class solely to add a component used in equality comparisons** often creates a contradiction.

Consider `Point(x, y)`, which defines two points as equal if their coordinates match. Next we want `ColorPoint(x, y, color)` to add a color and define two colored points as equal when **both coordinates and color** match. If `ColorPoint extends Point`, the way the parent views equality and the way the subclass views equality no longer share the same criteria.

The `Object.equals(Object)` contract requires, for non-`null` objects:

- **Reflexive:** `x.equals(x)` is `true`.
- **Symmetric:** `x.equals(y)` and `y.equals(x)` have the same result.
- **Transitive:** if both `x.equals(y)` and `y.equals(z)` are `true`, then `x.equals(z)` must also be `true`.
- **Consistent:** the result is stable when state participating in comparison does not change.
- **Comparison with null:** `x.equals(null)` is `false`.

In addition, two equal objects must have the same `hashCode()`. The implementations of `equals(Object)` and `hashCode()` across both classes must be compatible, not merely correct in each class separately.

The difficulty lies not in how to write `instanceof` or Java syntax, but in **two different value definitions coexisting within one hierarchy**: `Point` ignores color, whereas `ColorPoint` wants to include color.

## 2. The Symmetry Trap When Overriding equals in a Subclass

Suppose the parent class implements:

```java
@Override
public boolean equals(Object obj) {
    return obj instanceof Point other
            && x == other.x && y == other.y;
}
```

This is an **illustrative snippet**, assuming `x`, `y` are fields of `Point` with a matching `hashCode()`. Because it uses `instanceof Point`, the parent class also accepts subclasses with matching coordinates.

If the subclass only accepts `ColorPoint` objects and additionally compares `color`, we get:

- `point.equals(redPoint)` → `true`: the parent checks only coordinates.
- `redPoint.equals(point)` → `false`: the subclass requires the object to also have a color.

The two directions differ, thus **breaking symmetry**. Changing `instanceof Point` to `getClass() == obj.getClass()` in the parent class can alter semantics so `Point` and `ColorPoint` are unequal, yet you cannot always modify an already-published parent API, and it may violate expectations users already rely on.

## 3. The Transitivity Trap When Trying to “Patch” Symmetry

A tempting patch is: if `ColorPoint` is compared with a plain `Point`, let `Point` decide; if compared with a `ColorPoint`, inspect color as well. This approach can make each `Point`–`ColorPoint` pair symmetric, yet it breaks **transitivity**.

Create the complete file `InheritanceTrapDemo.java`:

```java
import java.util.Objects;

public class InheritanceTrapDemo {
    static class Point {
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

    static final class ColorPoint extends Point {
        private final String color;

        ColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (!(obj instanceof Point)) {
                return false;
            }
            if (!(obj instanceof ColorPoint other)) {
                // Accepts plain Point according to the parent class's definition.
                return obj.equals(this);
            }
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            // Must also match plain Point if equals considers them equal.
            return super.hashCode();
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColorPoint red = new ColorPoint(1, 2, "red");
        ColorPoint blue = new ColorPoint(1, 2, "blue");

        System.out.println(red.equals(plain));
        System.out.println(plain.equals(blue));
        System.out.println(red.equals(blue));
    }
}
```

Compile and run on JDK 17+:

```bash
javac InheritanceTrapDemo.java
java InheritanceTrapDemo
```

Output:

```text
true
true
false
```

We have:

```text
red == plain   (true)
plain == blue  (true)
red == blue    (false)  <-- contradicts transitivity
```

Because `Point` treats two objects with the same coordinates as equal, it becomes a bridge between two differently colored `ColorPoint` objects. Those two `ColorPoint` objects are unequal under the new definition. This is a logical contradiction in how values are organized, not merely a buggy `if` condition.

In the example, `ColorPoint`'s `hashCode()` intentionally uses `super.hashCode()` so as not to create an additional violation of “equal ⇒ same hash code” for pairs where `equals` returns `true`. That **does not save transitivity**, nor does it mean this is an implementation to use in production. Note that calling `obj.equals(this)` only illustrates this simple `Point` case; if there are additional subclasses with their own comparison rules, delegating back and forth can also introduce other issues.

## 4. Solution: Composition Instead of `extends`

**Composition** means `ColorPoint` **contains a `Point` as a component** instead of claiming to be a subtype of `Point`.

```text
Inheritance:             Composition:

ColorPoint               ColorPoint
    extends Point            has-a Point
    + color                  + color
```

Then there are two clear value domains:

- `Point` compares coordinates with other `Point` objects.
- `ColorPoint` compares coordinates **and color** with other `ColorPoint` objects.
- `Point` and `ColorPoint` are not forced to treat each other as equal merely because they share coordinates.
- If an API only needs coordinates, `ColorPoint` can **provide the `Point` component** via `position()` or an explicit conversion method.

Create the complete file `CompositionDemo.java`:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class CompositionDemo {
    static final class Point {
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

    static final class ColorPoint {
        private final Point point;
        private final String color;

        ColorPoint(Point point, String color) {
            this.point = Objects.requireNonNull(point);
            this.color = Objects.requireNonNull(color);
        }

        Point position() {
            return point;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof ColorPoint other)) {
                return false;
            }
            return point.equals(other.point)
                    && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(point, color);
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColorPoint red = new ColorPoint(new Point(1, 2), "red");
        ColorPoint redCopy = new ColorPoint(new Point(1, 2), "red");
        ColorPoint blue = new ColorPoint(new Point(1, 2), "blue");

        System.out.println(plain.equals(red));
        System.out.println(red.equals(plain));
        System.out.println(red.equals(redCopy));
        System.out.println(red.equals(blue));
        System.out.println(red.position().equals(plain));

        Set<Object> unique = new HashSet<>();
        unique.add(plain);
        unique.add(red);
        unique.add(redCopy);
        unique.add(blue);
        System.out.println(unique.size());
    }
}
```

Compile and run:

```bash
javac CompositionDemo.java
java CompositionDemo
```

Output:

```text
false
false
true
false
true
3
```

**Explanation:**

1. `plain.equals(red)` and `red.equals(plain)` are both `false` because they are two distinct value types; no asymmetry occurs.
2. `red.equals(redCopy)` is `true`: the two positions match and the two colors match. Both `hashCode()` values are computed from the same component set `point` + `color`.
3. `red.equals(blue)` is `false` because the colors differ. There is no intermediate `Point` simultaneously equaling both `ColorPoint` objects; eliminating the transitivity trap described above.
4. `red.position().equals(plain)` is `true`: callers can still obtain the *coordinate value* when only position needs to be compared, without conflating it with equality of the whole colored point.
5. `HashSet` contains exactly three distinct values: `plain`, `red`, `blue`; `redCopy` does not create a new entry because it equals `red`.

Here both `Point` and `ColorPoint` are `final`; the data consists of two integers and an immutable `String`, so hash codes cannot change after inserting the objects into the set. Returning `point` directly is safe **in this example because `Point` is immutable**. If an internal component can be mutated, consider defensive copying or a read-only view to protect immutability and equality consistency.

## 5. Why Does Composition Preserve the Contract Better?

| Criterion | Inheriting a Value Class and Adding Fields to Equality | Composition |
| --- | --- | --- |
| Type relationship | `ColorPoint` is also a `Point` | `ColorPoint` has a `Point` |
| Equality definition | Parent and subclass risk conflicting | Two value types define equality independently |
| Symmetry, transitivity | Easy to violate if the parent allows subclasses to be equal | Easier to prove with `final` types and stable components |
| `hashCode` | Must resolve cross-class “equal” objects | Computed from each type's exact components |
| Substitutability in APIs taking `Point` | Can pass `ColorPoint` directly | Must retrieve `position()` or convert explicitly |
| Design meaning | Promises “is-a” / substitutability | Expresses “has-a” and component ownership |

Composition has a practical trade-off: `ColorPoint` can no longer be passed directly to a method expecting a `Point` parameter. This is an intentional API change. If an API only needs position, you can call `render(colorPoint.position())`; if the API genuinely needs both position and color, use an appropriate abstraction or parameter instead of pretending the two types share the same identity.

**Composition does not automatically make equality right.** You still must implement `equals(Object)` and `hashCode()` with one consistent definition, handle `null`, mutable state, and subclasses. It simply eliminates the unnecessary conflict between the equality of two classes in an inheritance relationship.

## 6. Java `record` as a Concise Option for Immutable Values

When the goal is to model immutable data by its components, Java 17 provides `record`. The following is an **illustrative declaration snippet** that can be placed in a top-level Java source file or as nested types:

```java
record Point(int x, int y) {}

record ColorPoint(Point position, String color) {
    ColorPoint {
        Objects.requireNonNull(position);
        Objects.requireNonNull(color);
    }
}
```

The snippet requires `import java.util.Objects;`. Java automatically generates `equals(Object)` and `hashCode()` for a record from its declared components, along with type checking appropriate for records. `Point(1,2)` is a position value, whereas `ColorPoint(new Point(1,2),"red")` is a colored position value: they are not conflated into the same type by inheritance.

Records are not the answer for every case. If a component references a mutable object, the record only holds that **reference** in a `final` field rather than automatically copying or making it deeply immutable. If business equality does not correspond to all components of the record, a different design is needed.

## 7. When to Choose Composition vs When to Consider Inheritance?

**Prefer composition** when:

- The subclass would **add fields participating in value equality** compared to the parent class, such as adding `color`, `currency`, or `unit`.
- The parent class already has an `equals` contract that treats subclasses as equal based on its own data.
- You do not control how the parent class implements `equals` and `hashCode` (for example, a library class).
- You want to keep a clear boundary between a base value (`Point`) and an extended value (`ColorPoint`).

**Inheritance can still be appropriate** when the subtype can genuinely substitute for the supertype without violating value guarantees. For example, a behavioral hierarchy can use polymorphism without needing data-based equality in each subclass; or the entire hierarchy is designed and controlled from the start with a unified equality rule. There is no rule saying every use of `extends` is wrong.

You can consider `getClass()` to treat only same-class objects as equal, or a carefully designed cooperative protocol between parent and child. However, those approaches change the meaning of equality and require a consistent hierarchy-wide contract; adding a single type-checking method does not automatically cure every issue. If you want multiple types to support the same behavior, a behavioral interface may fit better than sharing inheritance from a value class.

## 8. Design and Testing Checklist

1. **Define “equal” before writing code:** what determines that two values are the same? Do the types differ in identity?
2. **Check the is-a relationship:** can `ColorPoint` substitute for `Point` everywhere while keeping the contract intact? If not, choose object composition.
3. **Use the exact signature:** `public boolean equals(Object obj)` with `@Override`; write `hashCode()` from the exact fields participating in equality.
4. **Test symmetry in both directions:** `a.equals(b)` and `b.equals(a)` for both same-class and cross-class pairs.
5. **Test transitivity across three objects:** especially test `red`, `plain`, `blue` with the same position but different colors.
6. **Check consistency and state:** if objects are used as `HashMap` keys or `HashSet` elements, avoid mutating fields participating in `equals/hashCode` while they remain in the collection.
7. **Test through generic APIs:** compare under type `Object`, via `Objects.equals`, and insert values into a `HashSet` to catch contract bugs that direct calls might miss.
8. **Keep responsibilities clear:** APIs needing only coordinates accept `Point`; APIs needing color info accept `ColorPoint` or an abstraction representing the full data.

**Self-check:** If `Point(1,2)` equals both `ColorPoint(1,2,"red")` and `ColorPoint(1,2,"blue")`, while those two colored points do not equal each other, which contract property is violated? **Transitivity.** If `Point` says “equal” and `ColorPoint` says “not equal” for the same pair, **symmetry** is violated. Composition lets you define separate value domains and expose coordinates explicitly when needed.

**Takeaway:** Inheritance is a substitutability commitment, whereas equality is a logical contract enforced across calls and collections. When a subclass adds a value component that makes the parent class's equality criteria insufficient, composition is usually the clearer and more stable design.