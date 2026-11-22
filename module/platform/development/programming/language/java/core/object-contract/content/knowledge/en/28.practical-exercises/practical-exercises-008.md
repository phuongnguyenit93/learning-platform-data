# Reviewing Inheritance Hierarchies That Break equals() Symmetry

## 1. The Issue to Detect

The `Object.equals()` contract in Java requires **symmetry**: for two non-`null` references `x` and `y`, the result of `x.equals(y)` must equal the result of `y.equals(x)`.

```text
x.equals(y) == y.equals(x)
```

A common bug arises when a subclass adds a new attribute: the superclass uses `instanceof Parent` and thus still accepts subclass instances, whereas the subclass uses `instanceof Child` and thus rejects superclass instances. The two calls invoke two different `equals()` implementations due to Java's **dynamic dispatch**.

Keep these distinctions clear:
- `a == b` on two reference variables checks for **the exact same object**.
- `a.equals(b)` compares for **logical equality per the type's contract**.
- `Object.equals()` by default treats only identical identity as equal; a class overriding `equals()` can define data-based equality.

The goal of this review exercise is to locate the parent/child pair breaking symmetry, trace the root cause, check risks to transitivity and hashing, apply a consistent fix policy, and then write regression tests.

## 2. Bug Example: Point and ColoredPoint

Suppose `Point` defines equality using two coordinates `x, y`, while `ColoredPoint extends Point` adds a `color` field included in equality.

This is an **illustrative excerpt**, not a standalone Java file:

```java
class Point {
    final int x, y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof Point other)) return false;
        return x == other.x && y == other.y;
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(x, y);
    }
}

class ColoredPoint extends Point {
    final String color;

    ColoredPoint(int x, int y, String color) {
        super(x, y);
        this.color = java.util.Objects.requireNonNull(color);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof ColoredPoint other)) return false;
        return super.equals(other) && color.equals(other.color);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(super.hashCode(), color);
    }
}
```

With `Point point = new Point(2, 3);` and `ColoredPoint red = new ColoredPoint(2, 3, "red");`, check one by one:

| Call | Implementation selected | Type check | Result |
| --- | --- | --- | --- |
| `point.equals(red)` | `Point.equals` | `red instanceof Point` is true | `true`: coordinates match |
| `red.equals(point)` | `ColoredPoint.equals` | `point instanceof ColoredPoint` is false | `false` |
| `point == red` | Identity operator | Two distinct objects | `false` |

`instanceof Point` admits objects belonging to subclasses of `Point`; the reverse does not hold. Hence:

```text
point.equals(red) = true
red.equals(point) = false
```

**This is a direct counterexample to symmetry.** Changing only the `super.equals(other)` line in the subclass will not solve the fact that the two classes have two different object-acceptance policies.

## 3. Impact and Contracts to Review Simultaneously

A valid `equals()` must satisfy all rules when data used for comparison does not change:

| Property | Requirement |
| --- | --- |
| Reflexive | `x.equals(x)` is always `true` for `x != null` |
| Symmetric | `x.equals(y)` and `y.equals(x)` yield the same result |
| Transitive | If `x.equals(y)` and `y.equals(z)` are true, then `x.equals(z)` is true |
| Consistent | Result remains stable across calls if relevant data does not change |
| Non-`null` | `x.equals(null)` returns `false` |
| Matching hash | If `x.equals(y)` is true, then `x.hashCode() == y.hashCode()` |

In the buggy example, `Point`'s hash uses only coordinates while `ColoredPoint`'s hash also uses color. When `point.equals(red)` returns `true`, the system must guarantee equal hashes; the differing formulas above **can** produce different hashes and additionally violate the `equals()` / `hashCode()` contract.

`HashSet` and `HashMap` depend on both methods. For a class violating the contract, adding/removing/finding keys can behave inconsistently. Avoid treating a `HashSet.size()` measurement on an arbitrary dataset as proof that the contract holds. **Different objects do not have to have different hashes**: hash collisions are permitted, whereas equality under `equals()` requires matching hashes.

## 4. Bad Fix Trap: Symmetry Restored, Transitivity Lost

A seemingly reasonable fix might allow `ColoredPoint` to equal `Point` if coordinates match, while also comparing color when both are `ColoredPoint`.

Given three objects:

```text
base = Point(2, 3)
red  = ColoredPoint(2, 3, "red")
blue = ColoredPoint(2, 3, "blue")
```

If color is ignored when one side is a `Point`, yet checked when both are `ColoredPoint`, we get:

```text
red.equals(base)  = true
base.equals(blue) = true
red.equals(blue)  = false
```

Thus **transitivity** is broken. Even fixing hashes so all three objects use the same coordinate hash cannot rescue transitivity. To let `Point` equal every `ColoredPoint` at the same coordinates, two differently colored `ColoredPoint` instances at those coordinates must also equal each other; if color distinguishes logical value, choose a different parent/child policy.

## 5. Standalone Runnable Java 17+ Program

The program below illustrates all three states: broken symmetry, a flawed patch breaking transitivity, and a consistent fix policy. Save **verbatim** into `EqualityInheritanceReview.java`.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualityInheritanceReview {
    static class LoosePoint {
        private final int x;
        private final int y;

        LoosePoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof LoosePoint other)) return false;
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class RestrictedColoredPoint extends LoosePoint {
        private final String color;

        RestrictedColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof RestrictedColoredPoint other)) {
                return false;
            }
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    static final class BridgeColoredPoint extends LoosePoint {
        private final String color;

        BridgeColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof LoosePoint)) return false;
            if (!(obj instanceof BridgeColoredPoint other)) {
                return super.equals(obj);
            }
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            // Consistent with LoosePoint when treating them as equal.
            return super.hashCode();
        }
    }

    static class ExactPoint {
        private final int x;
        private final int y;

        ExactPoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }
            ExactPoint other = (ExactPoint) obj;
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ExactColoredPoint extends ExactPoint {
        private final String color;

        ExactColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }
            ExactColoredPoint other = (ExactColoredPoint) obj;
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        LoosePoint point = new LoosePoint(2, 3);
        RestrictedColoredPoint restricted =
                new RestrictedColoredPoint(2, 3, "red");

        System.out.println("=== Broken symmetry ===");
        System.out.println("parent -> child: " + point.equals(restricted));
        System.out.println("child -> parent: " + restricted.equals(point));

        BridgeColoredPoint red = new BridgeColoredPoint(2, 3, "red");
        BridgeColoredPoint blue = new BridgeColoredPoint(2, 3, "blue");

        System.out.println("=== Broken transitivity ===");
        System.out.println("red -> parent: " + red.equals(point));
        System.out.println("parent -> blue: " + point.equals(blue));
        System.out.println("red -> blue: " + red.equals(blue));

        ExactPoint exact = new ExactPoint(2, 3);
        ExactColoredPoint exactRed = new ExactColoredPoint(2, 3, "red");
        ExactColoredPoint sameRed = new ExactColoredPoint(2, 3, "red");
        ExactColoredPoint exactBlue = new ExactColoredPoint(2, 3, "blue");

        System.out.println("=== Corrected policy ===");
        System.out.println("parent -> child: " + exact.equals(exactRed));
        System.out.println("child -> parent: " + exactRed.equals(exact));
        System.out.println("equal colored points: " + exactRed.equals(sameRed));
        System.out.println("different colors: " + exactRed.equals(exactBlue));
        System.out.println("equal hash: " +
                (exactRed.hashCode() == sameRed.hashCode()));

        Set<ExactPoint> set = new HashSet<>();
        set.add(exact);
        set.add(exactRed);
        set.add(sameRed);
        set.add(exactBlue);
        System.out.println("HashSet size: " + set.size());
    }
}
```

Compile and run from the directory containing the file:

```bash
javac EqualityInheritanceReview.java
java EqualityInheritanceReview
```

Deterministic output:

```text
=== Broken symmetry ===
parent -> child: true
child -> parent: false
=== Broken transitivity ===
red -> parent: true
parent -> blue: true
red -> blue: false
=== Corrected policy ===
parent -> child: false
child -> parent: false
equal colored points: true
different colors: false
equal hash: true
HashSet size: 3
```

**Code explanation:**

- `LoosePoint.equals()` uses `instanceof LoosePoint`, so it treats any subclass object with matching coordinates as equal.
- `RestrictedColoredPoint.equals()` accepts only the same subclass, so the two parent/child calls return opposite results.
- `BridgeColoredPoint` accepts the parent by coordinates and accepts the same subclass by coordinates + color: `red` with `point` and `point` with `blue` are equal, whereas `red` with `blue` are not.
- `ExactPoint` uses `getClass()`, requiring the exact same runtime class. `ExactColoredPoint` applies the same rule and then compares `color`. Therefore, `exact.equals(exactRed)` and the reverse **are both `false`**.
- Inside `ExactColoredPoint.equals()`, `super.equals(other)` still works: both compared objects have runtime class `ExactColoredPoint`, passing the `getClass()` check in `ExactPoint`.
- `sameRed` has identical content to `exactRed` and the same hash; `HashSet` therefore holds exactly three logical values: the plain point, the red point, and the blue point.

The program intentionally **prints the violations** rather than throwing on the first violation, so all three parts can be observed in a single run.

## 6. Three Business-Valid Design Strategies

### A. Equal only when sharing the exact runtime class

Use `getClass()` in participating classes, such as the `ExactPoint`/`ExactColoredPoint` pair. This makes sense when `Point(2,3)` is **a different value type** from `ColoredPoint(2,3,"red")`. All fields contributing to equality in each class must be included in `equals()` and `hashCode()`.

Trade-off to consider: framework-generated subclass/proxy objects may have a different runtime class from the original object. For instance, in some ORM mechanisms, a specific policy matching proxies and entity identity is required. Do not mechanically replace every `instanceof` with `getClass()`.

### B. Use composition or final value types

If color is not a subtype meant to substitute for a plain point under class contracts, use **composition**:

```java
record PointValue(int x, int y) {}

record ColoredPointValue(PointValue point, String color) {
    ColoredPointValue {
        java.util.Objects.requireNonNull(point);
        java.util.Objects.requireNonNull(color);
    }
}
```

This is an **illustrative type-definition snippet** (not a standalone program). In Java 17, `record` generates `equals()` and `hashCode()` from components and cannot be subclassed. Two `PointValue(2,3)` instances are equal; two `ColoredPointValue` instances are equal when both `point` and `color` match. `PointValue` is not a superclass of `ColoredPointValue`, so parent/child symmetry conflicts are designed away.

Records do not guarantee **deep immutability** if a component contains a mutable object; here `int`, `String`, and `PointValue` are used, so the data serving equality is stable.

### C. All classes compare the exact same set of data

If business requirements genuinely care only about coordinates, the subclass can omit `color` from equality logic, and its `hashCode()` must likewise follow coordinates. Then **two differently colored points at the same coordinates are equal**. This can be a valid choice, provided its consequence is accepted.

Complex inheritance hierarchies sometimes use a bidirectional compatibility check such as `canEqual`. This is not an automatic fix; a consistent policy must be designed for the whole hierarchy and tested for symmetry, transitivity, and hashing afterward.

## 7. Workflow for Reviewing a Real Class Hierarchy

1. **Map the inheritance tree.** Locate all related superclasses/subclasses and overridden `equals(Object)`/`hashCode()` methods. Note which new fields subclasses add and whether they participate in equality.
2. **Finalize the equality policy.** Should a plain point and a colored point at the same coordinates be considered equal? If so, can color still distinguish colored points? The answer must form an equivalence relation.
3. **Create three groups of objects:** same reference; two separate instances with equal values; two separate instances with differing values. Then create parent/child pairs at the same coordinates, subclasses with same/different `color`, and plain/red/blue triples to test relations.
4. **Test both directions.** For each pair `a, b`, evaluate `a.equals(b)` and `b.equals(a)`. Do not test only `child.equals(parent)` and draw conclusions.
5. **Test triples.** For any `a, b, c` where `a.equals(b)` and `b.equals(c)` are true, require `a.equals(c)` to be true.
6. **Test hashes and collections.** Every equal pair must share equal hashes; test `HashSet`, `HashMap`, and callers relying on value-based deduplication.
7. **Check mutable state.** If a hash collection key has a field used in `equals()`/`hashCode()` mutated, lookup can break. Prefer immutable keys.
8. **Add regression tests.** Cover grandchild classes or proxies if the real system uses them.

Suggested dataset table:

| Pair or triple | What to verify |
| --- | --- |
| `p` and `alias = p` | Same identity, reflexive |
| `new Point(2,3)`, `new Point(2,3)` | Two parent instances equal by value |
| Two `ColoredPoint(2,3,"red")` | Two child instances equal by value and hash |
| `Point(2,3)`, `ColoredPoint(2,3,"red")` | Both parent/child directions |
| Red point and blue point at same coordinates | `color` attribute |
| Red point, plain point, blue point | Transitivity |
| Any instance and `null` | `equals(null)` returns `false` |

## 8. Automated Symmetry and Transitivity Matrix Testing

Add the following **inside `main`** of the Java 17 program above (not a standalone file). `ExactPoint` and `ExactColoredPoint` are already present in the example:

```java
Object[] samples = {
        new ExactPoint(2, 3),
        new ExactPoint(2, 3),
        new ExactColoredPoint(2, 3, "red"),
        new ExactColoredPoint(2, 3, "red"),
        new ExactColoredPoint(2, 3, "blue")
};

for (Object a : samples) {
    for (Object b : samples) {
        if (a.equals(b) != b.equals(a)) {
            throw new AssertionError("Symmetry violated");
        }
        if (a.equals(b) && a.hashCode() != b.hashCode()) {
            throw new AssertionError("Hash contract violated");
        }
    }
}

for (Object a : samples) {
    for (Object b : samples) {
        for (Object c : samples) {
            if (a.equals(b) && b.equals(c) && !a.equals(c)) {
                throw new AssertionError("Transitivity violated");
            }
        }
    }
}
```

With the **fixed** samples, no exception is thrown. When buggy objects are placed into the matrix, the corresponding checks can uncover counterexamples. In real projects, move this check into JUnit 5 tests and expand samples along class/value boundaries. This tests over **the chosen sample set**, not an automatic proof over all states of all objects.

## 9. Common Mistakes

- **Checking only one direction:** `child.equals(parent)` returning true or false does not tell whether `parent.equals(child)` matches.
- **Treating `instanceof` as exact class comparison:** the operator actually admits subtypes, making it easy for a superclass to define broader equality than its subclass.
- **Fixing symmetry without checking transitivity:** the red/plain/blue point pattern shows that patching with "ignore color when comparing against parent" can break.
- **Overriding `equals()` while forgetting `hashCode()`:** hash-based collections require the contract between both methods.
- **Demanding unequal objects have unequal hashes:** collisions remain valid.
- **Mutating a key residing in `HashMap`/`HashSet`:** if fields used to compute the hash change, lookups may fail.
- **Applying one fix style to every hierarchy:** equality policy must reflect business semantics and may be affected by ORM proxies, dynamic subclasses, or specific value types.

## 10. Self-Check

**Q:** Why can `Point.equals(ColoredPoint)` be true while `ColoredPoint.equals(Point)` is false?  
**A:** The superclass accepts any `instanceof Point`, whereas the subclass accepts only `instanceof ColoredPoint`.

**Q:** If `red.equals(base)` and `base.equals(blue)` are true yet `red.equals(blue)` is false, what is violated?  
**A:** Transitivity.

**Q:** Why does the `getClass()` fix make `ExactPoint` and `ExactColoredPoint` with the same coordinates unequal?  
**A:** The equality policy requires **the exact same runtime class** before comparing attributes.

**Q:** If `x.equals(y)` is true, how must the two objects' hashes relate?  
**A:** They must be equal; the converse is not required.

**Key takeaway:** When a subclass adds state participating in `equals()`, review **the entire class hierarchy**, test both comparison directions as well as transitive triples, choose a consistent equality policy, synchronize `hashCode()`, and test collections. A fix that merely makes one pair of objects symmetric is not enough to guarantee the `Object` contract.