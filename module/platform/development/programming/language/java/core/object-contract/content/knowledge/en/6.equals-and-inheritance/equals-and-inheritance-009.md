# Testing Pairs and Triples Across Multiple Inheritance Levels When Implementing `equals`

## 1. Why Test Multiple Objects Across a Hierarchy?

When implementing `equals(Object)` for classes in an inheritance relationship, a single `a.equals(b)` check is not enough to verify the equality contract. A parent class may accept a subclass, while the subclass rejects the parent because it wants to compare an additional field of its own. A quick patch to restore two-way symmetry can even cause **transitivity** to break when comparing three objects.

For example, consider a `Point` class with only coordinates and a subclass `ColoredPoint` adding color:

- If `Point` treats every `ColoredPoint` with the same coordinates as equal to itself, while `ColoredPoint` rejects `Point` for lacking color, we can get `a.equals(b) != b.equals(a)`: a **symmetry violation**.
- If `ColoredPoint` agrees to compare against `Point` by coordinates, while requiring two `ColoredPoint` instances to match in color, then a plain `Point` can become a bridge between two differently colored `ColoredPoint` instances: a **transitivity violation**.

Therefore, for a hierarchy such as `Base → Middle → Leaf`, you must test **both directions of every pair** and **every relevant ordering of triples**. The goal is to catch cases where an implementation looks right when comparing objects of the same class yet fails when comparing across inheritance levels.

This lesson focuses on the **testing methodology** for verifying `equals` correctness across multiple inheritance levels: choosing samples, building a pair matrix, testing triples, spotting counterexamples, and choosing an appropriate equality policy.

## 2. The Contract Used as the Verification Standard

For non-`null` object references, `equals` must obey:

| Property | Expression to Check | Meaning During Testing |
| --- | --- | --- |
| Reflexive | `x.equals(x) == true` | Every object must equal itself. |
| Symmetric | `x.equals(y) == y.equals(x)` | An **ordered pair** must be tested in both directions. |
| Transitive | If both `x.equals(y)` and `y.equals(z)` are true, then `x.equals(z)` is also true. | Test **ordered triples**, especially with a parent class acting as a bridge. |
| Consistent | Repeating comparisons when relevant state does not change must yield the same result. | Test repeatedly and avoid mutating state between checks. |
| Against `null` | `x.equals(null) == false` | Every real object must reject `null` without throwing an exception. |

In addition, the mandatory relationship with `hashCode` is:

```text
If a.equals(b) == true then a.hashCode() == b.hashCode().
```

The converse is **not required**: two objects may share the same hash without being equal. `equals` must return `false` for objects incompatible in type under the class policy, rather than throwing `ClassCastException` from an unchecked cast.

These conditions hold **simultaneously**. A class that passes reflexivity or symmetry tests can still fail transitivity. Tests on a finite sample set help uncover counterexamples; they cannot prove every possible case for the class is correct.

## 3. Selecting Pairs at the Same Level, Across Levels, and Across Sibling Branches

Consider a three-level hierarchy:

```text
Point
  └── NamedPoint
        └── ColoredNamedPoint
```

Suppose the parent treats coordinates as essential, the middle level also considers name, and the bottom level also considers color. To uncover flaws, construct comparable objects intentionally:

1. **Same level, same data**: two `Point` instances with equal coordinates; two `NamedPoint` instances with the same coordinates and name; two `ColoredNamedPoint` instances with all fields matching.
2. **Same level, different data**: change only one field participating in `equals` to verify `false` is returned if that field genuinely affects equality.
3. **Same reference**: `a.equals(a)` and an alias variable `b = a`; this checks reflexivity, not full symmetry.
4. **Adjacent levels**: `Point ↔ NamedPoint`, `NamedPoint ↔ ColoredNamedPoint`, always invoking both directions.
5. **Two levels apart**: `Point ↔ ColoredNamedPoint`; do not skip this because the two intermediate classes may have different rules.
6. **Different branches under the same parent**: if there are two different subclasses, test `ChildA ↔ ChildB` as well as pairs with the parent.
7. **`null` and unrelated types**: each object against `null` and a type outside the hierarchy to detect type-checking bugs.

A **pair matrix** over sample list `[p, n, c]` corresponds to nine calls:

| Left side of `equals` | `p` (Point) | `n` (NamedPoint) | `c` (ColoredNamedPoint) |
| --- | --- | --- | --- |
| `p` | `p.equals(p)` | `p.equals(n)` | `p.equals(c)` |
| `n` | `n.equals(p)` | `n.equals(n)` | `n.equals(c)` |
| `c` | `c.equals(p)` | `c.equals(n)` | `c.equals(c)` |

To verify **symmetry**, compare each cell `(i, j)` with its mirror across the diagonal `(j, i)`. For instance, `p.equals(c)` must produce the same result as `c.equals(p)`. If you only call in one direction or only compare two instances of the same class, bugs at parent/child boundaries can be missed.

You should not assume every parent/child pair **must be equal**. Depending on the data model, `Point` and `ColoredNamedPoint` can be defined as always unequal, or equal by a shared immutable key. What is mandatory is that the policy is consistent in both directions and does not break the contract.

## 4. Triples for Testing Transitivity: Order Matters

If `a.equals(b)` is true and `b.equals(c)` is true, then `a.equals(c)` must be true. This condition does not apply only when all three objects share the same runtime class.

Example:

```text
red   = ColoredPoint(5, "red")
plain = Point(5)
blue  = ColoredPoint(5, "blue")

red.equals(plain)  → true
plain.equals(blue) → true
red.equals(blue)   → false   // TRANSITIVITY VIOLATION
```

`plain` shares the same coordinates with both colored points, yet `red` and `blue` differ. You cannot accept all three rules simultaneously if `equals` is to be an equivalence relation.

For a list of `n` samples, the general check is:

```text
for each a in samples:
    for each b in samples:
        for each c in samples:
            if a.equals(b) and b.equals(c) and !a.equals(c):
                report TRANSITIVITY VIOLATION for triple (a, b, c)
```

Three loops iterate over **ordered triples**, including repeated objects. For `n` elements there are at most `n³` triples, well suited for a carefully chosen small test set. Changing the order of elements can change the premise conditions; therefore testing only `(a, b, c)` without checking the remaining permutations is insufficient.

Triples should include: three objects of the same class; a parent class between two subclasses; a middle class between parent and grandchild; three consecutive levels; two child branches with a common parent; and objects differing in value while sharing the parent's data portion.

## 5. Java 17+: Automated Program for Checking Pairs and Triples

The following example intentionally builds **two flawed implementations**, then compares them against a valid model. Everything resides in a standalone file `HierarchyEqualsAudit.java`, requiring no external testing library.

```java
import java.util.List;

public class HierarchyEqualsAudit {
    record Sample(String label, Object value) { }

    // Parent level: treats any Point with matching x as equal.
    static class Point {
        final int x;

        Point(int x) {
            this.x = x;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Point other)) return false;
            return x == other.x;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(x);
        }
    }

    // Middle level: requires the other side to be at least NamedPoint.
    static class NamedPoint extends Point {
        final String name;

        NamedPoint(int x, String name) {
            super(x);
            this.name = name;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof NamedPoint other)) return false;
            return super.equals(other) && name.equals(other.name);
        }
    }

    // Leaf level: requires the other side to be ColoredNamedPoint.
    static final class ColoredNamedPoint extends NamedPoint {
        final String color;

        ColoredNamedPoint(int x, String name, String color) {
            super(x, name);
            this.color = color;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof ColoredNamedPoint other)) return false;
            return super.equals(other) && color.equals(other.color);
        }
    }

    // Tries to fix symmetry against plain Point, but breaks transitivity.
    static final class LenientColorPoint extends Point {
        final String color;

        LenientColorPoint(int x, String color) {
            super(x);
            this.color = color;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Point other)) return false;

            if (!(obj instanceof LenientColorPoint colored)) {
                return super.equals(other);
            }
            return super.equals(colored)
                    && color.equals(colored.color);
        }
    }

    // Valid option: all levels compare by immutable ID.
    static class Entity {
        private final int id;

        Entity(int id) {
            this.id = id;
        }

        @Override
        public final boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Entity other)) return false;
            return id == other.id;
        }

        @Override
        public final int hashCode() {
            return Integer.hashCode(id);
        }
    }

    static class DetailedEntity extends Entity {
        final String description;

        DetailedEntity(int id, String description) {
            super(id);
            this.description = description;
        }
    }

    static final class ColoredEntity extends DetailedEntity {
        final String color;

        ColoredEntity(int id, String description, String color) {
            super(id, description);
            this.color = color;
        }
    }

    static void audit(String name, List<Sample> samples) {
        boolean reflexive = true;
        boolean nullRule = true;
        boolean symmetric = true;
        boolean transitive = true;
        boolean hashAgreement = true;

        for (Sample a : samples) {
            Object left = a.value();

            if (!left.equals(left)) reflexive = false;
            if (left.equals(null)) nullRule = false;

            for (Sample b : samples) {
                Object right = b.value();
                boolean ab = left.equals(right);
                boolean ba = right.equals(left);

                if (ab != ba) symmetric = false;
                if (ab && left.hashCode() != right.hashCode()) {
                    hashAgreement = false;
                }

                for (Sample c : samples) {
                    Object third = c.value();
                    if (ab && right.equals(third)
                            && !left.equals(third)) {
                        transitive = false;
                    }
                }
            }
        }

        System.out.printf(
                "%s: reflexive=%s, nullRule=%s, symmetry=%s, "
                        + "transitivity=%s, hashAgreement=%s%n",
                name, reflexive, nullRule, symmetric,
                transitive, hashAgreement);
    }

    public static void main(String[] args) {
        Point base = new Point(5);
        NamedPoint middle = new NamedPoint(5, "oak");
        ColoredNamedPoint leaf =
                new ColoredNamedPoint(5, "oak", "red");

        System.out.println("base.equals(middle): "
                + base.equals(middle));
        System.out.println("middle.equals(base): "
                + middle.equals(base));
        audit("Strict subclasses", List.of(
                new Sample("base", base),
                new Sample("middle", middle),
                new Sample("leaf", leaf)));

        Point bridge = new Point(9);
        LenientColorPoint red = new LenientColorPoint(9, "red");
        LenientColorPoint blue = new LenientColorPoint(9, "blue");

        System.out.println("red.equals(bridge): "
                + red.equals(bridge));
        System.out.println("bridge.equals(blue): "
                + bridge.equals(blue));
        System.out.println("red.equals(blue): "
                + red.equals(blue));
        audit("Lenient subclasses", List.of(
                new Sample("red", red),
                new Sample("bridge", bridge),
                new Sample("blue", blue)));

        audit("Final inherited ID", List.of(
                new Sample("root", new Entity(7)),
                new Sample("middle", new DetailedEntity(7, "A")),
                new Sample("leaf", new ColoredEntity(7, "A", "red")),
                new Sample("other", new ColoredEntity(8, "B", "blue"))));
    }
}
```

Run in the directory containing the file:

```bash
javac HierarchyEqualsAudit.java
java HierarchyEqualsAudit
```

Stdout:

```text
base.equals(middle): true
middle.equals(base): false
Strict subclasses: reflexive=true, nullRule=true, symmetry=false, transitivity=true, hashAgreement=true
red.equals(bridge): true
bridge.equals(blue): true
red.equals(blue): false
Lenient subclasses: reflexive=true, nullRule=true, symmetry=true, transitivity=false, hashAgreement=true
Final inherited ID: reflexive=true, nullRule=true, symmetry=true, transitivity=true, hashAgreement=true
```

**How to read the output:**

- **`Strict subclasses`:** `Point.equals` uses `instanceof Point`, so it accepts a `NamedPoint` with the same `x`. However, `NamedPoint.equals` requires the argument to be `NamedPoint`, so it rejects `Point`. The pair matrix catches **false symmetry**. On this specific triple of samples, transitivity happens to pass; you cannot conclude a method is valid merely because the transitivity column is `true`.
- **`Lenient subclasses`:** `LenientColorPoint` ignores color when the argument is a plain `Point` and compares color when the argument is also a `LenientColorPoint`. Every pair in the sample set is symmetric, yet the triple `(red, bridge, blue)` makes **transitivity false**.
- **`Final inherited ID`:** the levels `Entity → DetailedEntity → ColoredEntity` inherit the same `final` `equals/hashCode`, comparing solely by `id`. Under the chosen policy, subclasses cannot add conditions that make two directions or triples contradict. The description/color fields **intentionally do not participate** in equality.

In the example, the flawed classes `NamedPoint`, `ColoredNamedPoint`, and `LenientColorPoint` inherit `Point.hashCode` based on `x`. This is intentional to show that **symmetry and transitivity are independent** of hash errors: allowing two unequal objects to share the same hash is valid. In real systems, hash field selection must align with the entire `equals` policy.

## 6. Expanding Tests to Catch Counterexamples Better

### Create Samples Differing by Exactly One Field

At each level, add single-field variants to catch forgotten fields:

```text
Point(5), Point(6)
NamedPoint(5,"oak"), NamedPoint(5,"pine")
ColoredNamedPoint(5,"oak","red"),
ColoredNamedPoint(5,"oak","blue")
```

If the class policy states that color must participate in equality, two objects with different colors must not inadvertently merge. Conversely, if the entire hierarchy defines equality solely through `id`, changing descriptive fields **should not** alter the result. Expected outcomes must come from the chosen business contract, not from field names.

### Re-scan the Matrix After Each New Level

When adding a grandchild class, re-run not only the grandchild's tests, but also pairs against **every ancestor class** and sibling subclasses. Even the parent class can begin violating the contract when a new subtype appears, despite the parent's `equals` source code never changing.

You can expand sample lists via data tables or parameterized JUnit 5 tests; what matters is that the same check suite runs across **all runtime types** in scope. For instance, `List<Sample>` in the program above stores objects generically as `Object`, so calling `left.equals(right)` uses **dynamic dispatch** to the actual method of the left-hand object. That is precisely why reversing call order can produce different results under a bad override.

### Verify Hash, Null, Consistency, and Exceptions

- For every pair where `a.equals(b)` is `true`, check that hash codes match. Do not require two hash codes to differ when `equals` is `false`.
- For every sample object, test `a.equals(null)` and `a.equals(new Object())`; the normal expected result is `false`.
- Re-run checks while not mutating relevant state to see whether results stay stable.
- If fields participating in `equals/hashCode` are mutable, design additional controlled tests. Avoid mutating those fields while the object is a `HashMap` key or sits inside a `HashSet`, as that can break lookups.
- When testing implementations that might throw exceptions, clearly wrap failures by pair/triple to pinpoint which method broke. For example, the program above assumes `equals` returns a valid boolean, so it does not catch exceptions inside the loop.

A small test set can include multiple objects with the **same logical value** but distinct references, multiple objects differing by one field, one parent object, and multiple subclasses. Using only `a.equals(a)` or two instances of the same class cannot test the risks introduced by inheritance.

## 7. Choosing a Suitable Equality Policy So Testing Is Meaningful

There are three common directions:

| Policy | How to Apply | What to Watch Out For |
| --- | --- | --- |
| **Exact runtime-type equality** | Use `getClass()` to require the same class before comparing fields. | Parent and child are not equal, even if parent data matches; must be applied consistently across overrides. |
| **Shared immutable-key equality** | Parent defines `final equals/hashCode` based on a key representing the same entity at every level. | Extra fields in subclasses must not silently alter the meaning of `equals`. |
| **Remove inheritance from value classes** | Use `final` classes or `record`s for value types; compare clearly defined components. | New value types do not participate in equality across an extensible hierarchy. |

If choosing exact runtime type, a parent class can use:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (obj == null || getClass() != obj.getClass()) return false;
    Point other = (Point) obj;
    return x == other.x;
}
```

This snippet is an **illustration inside a `Point` class with field `x`**, not a standalone runnable file. If a subclass overrides `equals`, the type-checking policy and `super.equals` calls must still be designed in sync. Simply replacing `instanceof` with `getClass` in one place while keeping loose comparisons elsewhere **does not automatically** prove the hierarchy is correct.

The `final` shared-key policy in the example is appropriate only when entities with the same `id` are genuinely treated as the same value **regardless of subtype**. Do not apply it mechanically to distinct kinds where IDs might collide while business meanings differ. For data types that do not need structural variation through inheritance, `final` classes or `record`s usually reduce the number of cases requiring testing considerably.

Another extensible option is the `canEqual` pattern to coordinate equality in hierarchies with overrides. That pattern is useful only when designed and applied consistently at every level; you still need the pair matrix and triples above to verify the actual contract.

## 8. Testing Strategy and Interpreting Failure Output

Using a generic loop such as `audit` helps reveal **properties of the equality relation** without writing separate `assert` statements for every pair. However, for a test suite to have lasting value:

1. **State the expected equality rules clearly** for same-class and cross-class pairs; the axioms only say the relation must be consistent, not which pairs ought to be equal.
2. **Choose samples covering at least three levels** and relevant child branches, not just same-class objects. Use multiple values and at least one pair of distinct instances expected to be equal.
3. **Check reflexivity/null** first; then the **directed pair matrix** to catch symmetry bugs.
4. **Check all ordered triples** to catch transitivity bugs, printing the failing `(a,b,c)` names for easier debugging.
5. **Check hashes when equal**, and re-run after changing samples or design.
6. **Fix comparison rules at the appropriate level**, then re-run the entire hierarchy's test suite instead of testing only the case that just failed.

With `n` samples, pairs are `O(n²)` and triples are `O(n³)`; usually use a purposeful sample set in unit tests, combined with *property-based testing* when the model has many variants. If testing whether results change with state, ensure no other thread concurrently mutates fields during the test; the `equals` axioms assume comparison state stays stable.

### Self-Check Questions

1. If `Base.equals(Child)` is `true` yet `Child.equals(Base)` is `false`, which contract property is violated?
2. Why can testing only `a.equals(b)` without testing `b.equals(a)` miss bugs?
3. With `red.equals(plain) == true`, `plain.equals(blue) == true`, yet `red.equals(blue) == false`, what bug occurred? What is the significance of the ordering of the three objects?
4. If both sides produce equal hash codes while not being equal under `equals`, is that a violation?
5. When adding a grandchild class, why must you re-run tests of the **parent and middle classes**?
6. When is it acceptable to intentionally omit a subclass's new fields in `equals`?

**Takeaway:** With `equals` and inheritance, you must test **every pair in both directions** to verify symmetry and **every ordered triple** to verify transitivity. Prepare samples across parent, child, grandchild, and sibling branches, and clearly define the equality policy before concluding an implementation is correct.