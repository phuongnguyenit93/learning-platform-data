# The `canEqual()` Pattern in Inheritance: Purpose, Cooperation Requirements, and Limitations

## 1. Why Is `canEqual()` Needed When Overriding `equals()`?

In Java, `Object.equals(Object)` must obey **reflexivity**, **symmetry**, **transitivity**, **consistency**, and `x.equals(null)` must always be `false` for non-`null` `x`. Whenever two objects are considered equal, they must also share the same `hashCode()`.

Inheritance makes building an equality relation harder because parent class and subclass can **differ in the fields that determine logical identity**. A `Point` class has only coordinates (`x`, `y`); a `ColoredPoint` class inherits from `Point` and adds `color`. If the parent class uses `instanceof Point` to compare coordinates while the subclass accepts only `ColoredPoint` and also checks color, the same pair of objects can yield two opposite answers:

| Comparison | Result Under Wrong Implementation | Cause |
| --- | --- | --- |
| `point.equals(coloredPoint)` | `true` | Parent sees the child object as a `Point` and checks only coordinates |
| `coloredPoint.equals(point)` | `false` | Subclass rejects an object that is not a `ColoredPoint` |

That is a **symmetry** violation: for two non-null references `a` and `b`, `a.equals(b)` must equal `b.equals(a)`. Fixing only the subclass is not enough if the parent class's `equals` method still unilaterally accepts subclass objects.

**`canEqual()` is a supporting design pattern**, defined by the programmer, that allows the right-hand object to answer the question: *“Do I agree to be compared for equality with the type of the left-hand object?”* It is **not** a built-in method on `java.lang.Object` and Java does **not** automatically generate it for regular classes.

## 2. Mechanism: Both Objects Must Agree

In a simple version of the pattern, the parent class implements:

```java
protected boolean canEqual(Object other) {
    return other instanceof Point;
}

@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof Point that)) return false;
    return that.canEqual(this) && x == that.x && y == that.y;
}
```

This is an **illustrative snippet inside the `Point` class**, assuming the class already declared fields `x`, `y` and the `canEqual` method as shown; it is not yet a standalone Java file.

The key point is the call **`that.canEqual(this)`**:

1. `this` is the object on which `equals` is invoked (the left-hand side).
2. `that` is the right-hand object already confirmed to be a `Point` or a subclass.
3. The call `that.canEqual(this)` uses **dynamic dispatch**: the JVM selects the `canEqual` implementation of **`that`'s runtime type**, not necessarily the implementation in `Point`.
4. If `that` is a `ColoredPoint`, it can reject `this` when `this` is only a `Point`. The parent class then returns `false` before comparing coordinates.

This pattern lets a subclass with additional equality criteria prevent the parent class from treating it as the same value as the parent class. In return, **every participating class must follow the convention together**. If a subclass adds state to `equals` without adjusting `canEqual`, the parent class can still accept it in one direction and break symmetry.

## 3. Complete Java 17+ Program

Save the following code into **`CanEqualDemo.java`**. `Point` has coordinates; `ColoredPoint` adds color and overrides `canEqual`, `equals`, and `hashCode` in sync. The program checks pairs in both directions.

```java
import java.util.Objects;

public class CanEqualDemo {
    static class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        protected boolean canEqual(Object other) {
            return other instanceof Point;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Point that)) return false;
            return that.canEqual(this)
                    && x == that.x
                    && y == that.y;
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
        protected boolean canEqual(Object other) {
            return other instanceof ColoredPoint;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof ColoredPoint that)) return false;
            return that.canEqual(this)
                    && super.equals(that)
                    && color.equals(that.color);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + color.hashCode();
        }
    }

    static void check(String label, Object a, Object b) {
        boolean forward = Objects.equals(a, b);
        boolean reverse = Objects.equals(b, a);

        System.out.printf("%s: forward=%s, reverse=%s%n",
                label, forward, reverse);

        if (forward != reverse) {
            throw new AssertionError("Broken symmetry: " + label);
        }
    }

    public static void main(String[] args) {
        Point base = new Point(2, 5);
        Point baseCopy = new Point(2, 5);
        ColoredPoint red = new ColoredPoint(2, 5, "red");
        ColoredPoint redCopy = new ColoredPoint(2, 5, "red");
        ColoredPoint blue = new ColoredPoint(2, 5, "blue");

        check("Point vs ColoredPoint", base, red);
        check("ColoredPoint copies", red, redCopy);
        check("Different colors", red, blue);
        check("Point copies", base, baseCopy);
        check("Point vs null", base, null);

        System.out.println("equal red objects share hash: "
                + (red.hashCode() == redCopy.hashCode()));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac CanEqualDemo.java
java CanEqualDemo
```

Standard output:

```text
Point vs ColoredPoint: forward=false, reverse=false
ColoredPoint copies: forward=true, reverse=true
Different colors: forward=false, reverse=false
Point copies: forward=true, reverse=true
Point vs null: forward=false, reverse=false
equal red objects share hash: true
```

**Why do those lines appear?**

- **`base.equals(red)`**: `red` satisfies `instanceof Point`, yet `red.canEqual(base)` invokes the override in `ColoredPoint`. Since `base` is not a `ColoredPoint`, that call returns `false`. The parent rejects cross-type comparison even though coordinates match.
- **`red.equals(base)`**: the `base instanceof ColoredPoint` condition is `false`, so the subclass also returns `false`. Both directions agree.
- **`red.equals(redCopy)`**: both are `ColoredPoint`; `that.canEqual(this)` accepts, `super.equals(that)` confirms coordinates, and `color.equals(that.color)` confirms matching colors. The reverse direction is also `true`.
- **`red.equals(blue)`**: coordinates match but colors differ; both directions are `false`.
- **`base.equals(baseCopy)`**: both are `Point` with matching coordinates; both directions are `true`.
- `Objects.equals(base, null)` and `Objects.equals(null, base)` are both `false`, helping test the reversed direction safely against `null`.
- Two equal `ColoredPoint` instances must share the same `hashCode`; the example verifies that. Two **unequal** objects are still allowed to have matching hashes.

In `ColoredPoint.equals`, the `that.canEqual(this)` condition explicitly expresses the right-hand object's consent. Calling `super.equals(that)` also checks `that.canEqual(this)` in the parent class and then checks coordinates; in this single-level example, asking again is computationally redundant, yet it keeps the parent class always maintaining its own contract.

## 4. Requirements for Cooperation Between Parent Class and Subclass

### 4.1. The Parent Class Must Consult the Right-Hand Object

`Point.equals` must check `other.canEqual(this)` **before concluding** equality based on parent fields. If the parent simply writes `other instanceof Point` and compares coordinates, the `canEqual` method on the subclass will never be used and the pattern fails to resolve the original issue.

### 4.2. A Subclass Adding Equality State Must Override `canEqual`

If color participates in deciding `equals`, `ColoredPoint.canEqual` should accept exactly the group of objects it is prepared to compare under that definition. In the example, it accepts only `ColoredPoint`.

If a subclass only adds presentation data and does **not** add fields participating in the equality definition, it may not need to alter the parent's rule; however, that decision must be clearly documented in the model. There is no rule that “every subclass must differ from its parent” for every problem.

### 4.3. The Subclass Must Coordinate `equals` with Inherited Equality

The subclass must combine the checks: matching type, acceptance by the right-hand object, equality of the parent's data (for example `super.equals(that)`), and equality of the new data. Omitting `super.equals` could cause two points with different coordinates to be considered equal merely because they share the same color.

Overriding only `canEqual` is not enough: **`equals` itself must still perform the full attribute comparison**. Conversely, overriding `equals` without overriding `canEqual` in a subclass that adds equality state easily reintroduces the symmetry bug.

### 4.4. `hashCode` Must Follow the Same Equality Relation

Whenever `a.equals(b)` is `true`, `a.hashCode() == b.hashCode()` is mandatory. In the example, `Point` uses coordinates and `ColoredPoint` combines the parent's hash with color. Both equal `ColoredPoint` objects have equal hashes.

Do not reason in reverse: two equal hashes do **not** imply two objects are equal. If different types are allowed to be equal, you must ensure the hash calculation across **all compatible types** is consistent, not merely valid within each individual class.

### 4.5. The Convention Must Apply Across the Entire Hierarchy

For a multi-level hierarchy (`Point → ColoredPoint → LabeledColoredPoint`), every level adding attributes that participate in equality must consider updating `canEqual`, `equals`, and `hashCode`. Intermediate classes must also maintain the consent check; if one class skips it, asymmetry can return.

In the example, `ColoredPoint` is marked `final` so that no new inheritance level can arise and arbitrarily alter the rule. That is a helpful design safeguard, not a strict requirement for every use of `canEqual`.

## 5. What `canEqual()` Solves and What It Does **Not** Solve

| Topic | Practical Role of `canEqual` |
| --- | --- |
| Symmetry when parent/child have different value rules | **Can support**: subclass rejects comparison with parent; parent respects that decision |
| Reflexivity | Not automatically guaranteed; `equals` must still return `true` for the same object |
| Transitivity | Not automatically guaranteed; if `a=b` and `b=c`, the design must ensure `a=c` |
| Consistency | Not automatically guaranteed if fields used in comparison mutate without clear rules |
| Comparison with `null` | Not automatically guaranteed; `equals(null)` must return `false` |
| `hashCode` contract | Not automatically guaranteed; must be implemented and tested separately |
| Correctness of the domain model | Does not replace business decisions on which objects can represent the same value |

**Biggest limitation:** `canEqual` is a *cooperative convention*. It has no power to force every subclass to implement it properly, cannot prove the equality relation is transitive, and cannot prevent other code from overriding `equals` improperly. If the left side concludes equality using field set A while the right side relies on an incompatible field set B, a single intent-checking method cannot reconcile the two definitions on its own.

**Mutable objects:** If `x`, `y`, or `color` can be modified after inserting the object into a `HashSet` or using it as a `HashMap` key, its hash value can change and break lookups unexpectedly. The example uses `final` fields to eliminate this risk within the program itself, yet immutable design should also apply to component objects where relevant.

**Unfamiliar types or proxies:** Checking via `instanceof`, `getClass()`, and `canEqual` expresses different type-compatibility policies. If a framework generates subclasses at runtime, the equality policy must account for runtime types and representative data; there is no single right choice for every proxy or entity kind.

## 6. Comparison with Other Design Options

| Approach | When Suitable | Trade-Offs |
| --- | --- | --- |
| `getClass() == other.getClass()` | Only objects of the **exact same runtime class** may be equal | Easy to understand, but always rejects parent/child equality even under shared criteria |
| Plain `instanceof` | Hierarchy has a unified equality definition; subclasses do not add equality-determining state | Easily breaks symmetry/transitivity when subclasses add criteria |
| `instanceof` combined with `canEqual` | Need to let each type control comparability across the hierarchy | More flexible, but every involved class must cooperate and be carefully tested |
| `final class` or `record` | Value object has clear logical identity and needs no inheritance variants | Lower contract risk; `record` auto-generates `equals`/`hashCode` by components |
| Composition | New type **contains** the old value and adds components such as color | Separates equality domains, avoiding parent–child coordination |

For example, instead of designing `ColoredPoint extends Point`, you can create two separate `record` types:

```java
record PointValue(int x, int y) {}
record ColoredPointValue(PointValue point, String color) {}
```

This is a **standalone type declaration snippet**, not a full runnable program. The colored type holds the coordinate type, and Java generates component-based comparison. A `PointValue` is not equal to a `ColoredPointValue` by default in either direction; when cross-type equality is unnecessary, that is usually a simpler design.

`canEqual` is useful when inheritance is genuinely required by the model and you do not want a rigid “exact same class only” policy. It is not a ceremony that every Java class must adopt.

## 7. Thorough Testing and Common Mistakes

When inheritance is present, do not write assertions only for `a.equals(b)`. Test **the reverse direction** and compare all potentially related class groups:

- Same reference; two distinct references with equal values; same type with different values.
- Parent–child in both directions; two subclasses of the same type; two subclasses of different types.
- `null` and unrelated objects; reversed call orders.
- Triples of objects to check **transitivity**; repeated comparisons without state mutation to check **consistency**.
- Two objects determined equal must share the same `hashCode()`; test as keys in `HashMap`/`HashSet` if that is a real use case.

Notable mistakes:

1. **Forgetting `other.canEqual(this)` in the parent class:** even a subclass that overrides `canEqual` cannot refuse when the parent initiates the comparison.
2. **Subclass adds fields to `equals` without overriding `canEqual`:** can restore the bug where the parent accepts the subclass in one direction while the subclass rejects the parent in the other.
3. **Not calling `super.equals` when inherited fields must be compared:** two objects with different parent data could still be evaluated as equal.
4. **Not synchronizing `hashCode`:** equal objects can land in different buckets in hash structures, violating the contract.
5. **Assuming `canEqual` checks every `equals` property by itself:** it only helps control type compatibility; transitivity, reflexivity, and consistency still need testing.
6. **Writing `equals(Point)` instead of `equals(Object)`:** that is an overload, not a proper override of the `Object.equals` contract. Using `@Override` helps catch signature mistakes at compile time.

**Self-check exercise:** Suppose `Point.equals` compares only coordinates and calls `other.canEqual(this)`, yet `ColoredPoint` overrides `equals` to also compare color while **forgetting to override `canEqual`**. When `point` and `coloredPoint` share the same coordinates, evaluate both directions: `point.equals(coloredPoint)` can be `true` because `ColoredPoint` inherits `Point.canEqual`; `coloredPoint.equals(point)` is `false` because the parent object is not a `ColoredPoint`. This is why **parent class and subclass must cooperate** for the pattern to preserve symmetry.

In summary, `canEqual()` delegates acceptance of the equality relation to the compared object. Use it when managing equality in an open hierarchy; ensure every layer combines `canEqual`, `equals`, and `hashCode` consistently, then test the full contract. If cross-type equality is not genuinely needed, `final` value classes, `record`s, and composition generally simplify the design.