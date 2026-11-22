# Adding Value Fields in a Subclass and the Risk of Breaking `equals` Transitivity

## 1. The Problem: The Subclass Adds a Part of the “Value”

Consider a parent class **Point** storing coordinates x, y and defining two points as equal if they have the same coordinates. We then subclass it into **ColoredPoint**, adding a **color** field. A seemingly simple design question arises:

> Does **Point(1, 2)** equal **ColoredPoint(1, 2, "red")**?

If **yes**, because Point only cares about coordinates, then a red ColoredPoint and a blue ColoredPoint with the same coordinates could both equal the base Point. Yet if two ColoredPoints must also consider color, they are **not equal** to each other. Then the equality relation is no longer transitive.

If **no**, the subclass needs to ensure that **both directions** of comparison between Point and ColoredPoint return false. If Point uses **instanceof Point** in equals while ColoredPoint rejects Point objects, symmetry will be broken.

This is a conflict between **type inheritance** (a ColoredPoint is a Point) and **value-equality semantics** (a ColoredPoint may have more fields constituting its value than a Point). Java allows overriding equals, but **does not automatically enforce** the equals contract as the inheritance tree becomes complex.

### Distinguishing Value Fields from Display-Only Fields

Not every new field needs to participate in equals.

- If color is merely a decorative attribute that does not affect logical identity/value, both Point and ColoredPoint can continue comparing by x, y. In that case, **two ColoredPoints of different colors must still be equal** under the chosen rule.
- If color is part of the value, then two ColoredPoints of different colors **must be unequal**. In that case, you cannot simultaneously make each ColoredPoint equal a Point with the same coordinates and keep a valid equals relation.
- If the equality condition comes from a stable business key, such as id, a new field like display name may be intentionally ignored. This decision belongs to **domain semantics**, not just Java syntax.

This lesson focuses on the case where **the subclass genuinely adds a field that is meaningful to value comparison**.

## 2. The `Object.equals` Contract Must Be Preserved Under Inheritance

For non-null references, equals must satisfy five main requirements:

| Property | Statement | Consequence for Grouping/Lookup |
| --- | --- | --- |
| **Reflexive** | a.equals(a) == true | An object always equals itself |
| **Symmetric** | a.equals(b) and b.equals(a) have the same result | Swapping the two operands must not change the meaning |
| **Transitive** | If both a.equals(b) and b.equals(c) are true, then a.equals(c) must be true | Cannot have a in the same group as b, b in the same group as c, yet a in a different group from c |
| **Consistent** | Repeated results stay stable when the data used for comparison does not change | Results do not fluctuate when used in data structures |
| **Against null** | a.equals(null) == false | null is never equal to a non-null object |

**hashCode** has a linked contract: **if a.equals(b) is true then a.hashCode() must equal b.hashCode()**. The converse is not required because hash collisions are allowed.

**Note:** the **equals** contract is stronger than “the code compiles and runs” or “the fields seem to be compared properly”. Each class's method can look reasonable when read in isolation, yet the combination of parent class and subclass still violates symmetry or transitivity.

### Two Error-Prone Choices

Suppose **Point.equals** compares x, y against every object that is **instanceof Point**.

1. **ColoredPoint accepts only ColoredPoint:** Point.equals(red) returns true, while red.equals(Point) returns false. This is a **symmetry** error.
2. **ColoredPoint accepts Point but requires color when meeting ColoredPoint:** Point.equals(red) and red.equals(Point) are both true. Symmetry may hold, but with two different colors, **transitivity is broken**.

The second bug is harder to spot because pairwise Point–ColoredPoint comparisons all look reasonable.

## 3. Java 17 Example: Fixing Symmetry While Breaking Transitivity

Create the file **BrokenEqualsDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class BrokenEqualsDemo {
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

    static final class ColoredPoint extends Point {
        private final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color, "color");
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Point)) {
                return false;
            }
            if (!(obj instanceof ColoredPoint other)) {
                // Accepts plain Point to try to preserve symmetry.
                return super.equals(obj);
            }
            // If both have color, uses color as part of the value again.
            return super.equals(obj) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            // Must have the same hash as a Point with the same coordinates
            // because those two objects are considered equal.
            return super.hashCode();
        }
    }

    public static void main(String[] args) {
        ColoredPoint red = new ColoredPoint(1, 2, "red");
        Point plain = new Point(1, 2);
        ColoredPoint blue = new ColoredPoint(1, 2, "blue");

        System.out.println("red == plain by equals: " + red.equals(plain));
        System.out.println("plain == blue by equals: " + plain.equals(blue));
        System.out.println("red == blue by equals: " + red.equals(blue));

        System.out.println("plain == red by equals: " + plain.equals(red));
        System.out.println("blue == plain by equals: " + blue.equals(plain));
        System.out.println("same hash: " +
            (red.hashCode() == plain.hashCode()));

        Set<Point> firstOrder = new HashSet<>();
        firstOrder.add(red);
        firstOrder.add(blue);
        firstOrder.add(plain);

        Set<Point> secondOrder = new HashSet<>();
        secondOrder.add(plain);
        secondOrder.add(red);
        secondOrder.add(blue);

        System.out.println("red, blue, plain -> size " + firstOrder.size());
        System.out.println("plain, red, blue -> size " + secondOrder.size());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac BrokenEqualsDemo.java
java BrokenEqualsDemo
~~~

Output:

~~~text
red == plain by equals: true
plain == blue by equals: true
red == blue by equals: false
plain == red by equals: true
blue == plain by equals: true
same hash: true
red, blue, plain -> size 2
plain, red, blue -> size 1
~~~

### Exact Analysis of the Bug

Take **a = red**, **b = plain**, **c = blue**:

~~~text
a.equals(b) == true
b.equals(c) == true
a.equals(c) == false
~~~

The contract requires **a = b** and **b = c** to imply **a = c**, yet the method violates it. We can express this in terms of supposed groups:

~~~text
red   ── equals ── plain
blue  ── equals ── plain
red   ── NOT equals ── blue
~~~

No way exists to partition these three objects into valid equivalence classes while preserving all three conclusions above.

**Why does HashSet produce two different sizes?** In the example, the objects share the same hash. When red and blue arrive first, both are kept because they are unequal; when plain arrives later, it is considered equal to an existing element, leaving two elements. When plain arrives first, red and blue are each considered equal to plain, leaving only one. Insertion order changed the count of “unique values” in a way contrary to what a proper equality relation requires.

Keeping **hashCode** identical here is intentional to obey the mandatory condition when red.equals(plain) and blue.equals(plain) return true. **Modifying hashCode to include color does not solve the transitivity bug**; it would even introduce a new violation because red equals plain while their hashes might differ.

> **Conclusion for this implementation:** you cannot simultaneously have all three desires—“Point compares by coordinates”, “ColoredPoint also compares color”, and “ColoredPoint still equals Point with the same coordinates”—while preserving equals transitivity.

## 4. Another Bug: Comparing Only the Subclass Breaks Symmetry

If ColoredPoint overrides equals like this:

~~~java
@Override
public boolean equals(Object obj) {
    if (!(obj instanceof ColoredPoint other)) {
        return false;
    }
    return super.equals(obj) && color.equals(other.color);
}
~~~

This is only an **illustrative snippet** placed inside the ColoredPoint class from the previous section, not a standalone program.

With Point.equals still using **instanceof Point**:

- **plain.equals(red)** is true because red is also a Point and has the same coordinates.
- **red.equals(plain)** is false because plain is not a ColoredPoint.

Reversing the comparison yields different results. That is a **symmetry** violation. Testing with HashMap, HashSet, or a few random cases may not catch it immediately; you must test **both directions**.

## 5. First Safe Approach: Equal Only When Runtime Types Match

If a subclass adds value fields, one clear policy is: **Point and ColoredPoint are never equal**, even when their coordinates match. Within each specific type, all value fields are compared.

In this case, use **getClass()** to require the **exact runtime type** in both the parent class and subclass. Create the file **ExactClassEqualsDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ExactClassEqualsDemo {
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
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }
            Point other = (Point) obj;
            return x == other.x && y == other.y;
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
            this.color = Objects.requireNonNull(color, "color");
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }
            if (!super.equals(obj)) {
                return false;
            }
            ColoredPoint other = (ColoredPoint) obj;
            return color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + color.hashCode();
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        Point red = new ColoredPoint(1, 2, "red");
        Point redAgain = new ColoredPoint(1, 2, "red");
        Point blue = new ColoredPoint(1, 2, "blue");

        System.out.println("plain equals red: " + plain.equals(red));
        System.out.println("red equals plain: " + red.equals(plain));
        System.out.println("red equals redAgain: " + red.equals(redAgain));
        System.out.println("red equals blue: " + red.equals(blue));
        System.out.println("matching hash: " +
            (red.hashCode() == redAgain.hashCode()));

        Set<Point> values = new HashSet<>();
        values.add(plain);
        values.add(red);
        values.add(redAgain);
        values.add(blue);
        System.out.println("unique values: " + values.size());
    }
}
~~~

Run:

~~~bash
javac ExactClassEqualsDemo.java
java ExactClassEqualsDemo
~~~

Output:

~~~text
plain equals red: false
red equals plain: false
red equals redAgain: true
red equals blue: false
matching hash: true
unique values: 3
~~~

**Key points to understand:**

- **getClass()** makes both directions between Point and ColoredPoint return false. Therefore there is no “intermediate object” Point with the same coordinates bridging two ColoredPoints of different colors.
- When both objects are ColoredPoint, **super.equals(obj)** still checks coordinates: the call is made on a ColoredPoint instance, so the **getClass()** check in the parent class sees the same runtime type ColoredPoint.
- **ColoredPoint.hashCode** adds color matching the fields compared by ColoredPoint; if two ColoredPoints are equal, both coordinates and color match, so they must have the same hash.
- **Point.hashCode** and **ColoredPoint.hashCode** may still coincidentally collide. This is valid because **equal hashes do not mean equals must be true**.
- **ColoredPoint** is **final** so that no new grandchild class can arbitrarily add value fields or override equals, helping limit risk.

**Trade-offs:** Defining equality by exact runtime type is unsuitable if the domain requires **objects of two different types with the same ID to be treated as one value**. It can also cause surprises with frameworks that generate proxies/subclasses (for instance, certain ORM scenarios). In those situations, you need an equality policy based on ID or a dedicated business key aligned with entity lifecycle and proxy mechanisms; do not mechanically swap between **instanceof** and **getClass()**.

## 6. Second Safe Approach: Prefer Composition to Represent Extended Values

When a colored object is genuinely **a different kind of value**, you may not need to inherit from the Point class. Make Point a component of ColoredPoint (composition). Two Java record classes automatically provide equals/hashCode for all value components of each record.

Full example **CompositionEqualsDemo.java**:

~~~java
public class CompositionEqualsDemo {
    record Point(int x, int y) {}

    record ColoredPoint(Point position, String color) {}

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColoredPoint red = new ColoredPoint(plain, "red");
        ColoredPoint redAgain = new ColoredPoint(new Point(1, 2), "red");
        ColoredPoint blue = new ColoredPoint(new Point(1, 2), "blue");

        System.out.println("plain equals red: " + plain.equals(red));
        System.out.println("red equals redAgain: " + red.equals(redAgain));
        System.out.println("red equals blue: " + red.equals(blue));
        System.out.println("same position: " +
            red.position().equals(blue.position()));
    }
}
~~~

Run:

~~~bash
javac CompositionEqualsDemo.java
java CompositionEqualsDemo
~~~

Output:

~~~text
plain equals red: false
red equals redAgain: true
red equals blue: false
same position: true
~~~

Here **red** and **blue** share the same **position** but have different **ColoredPoint values**. The two concepts are cleanly separated, without forcing equals across an inheritance tree to both ignore and inspect color.

When you need to check whether two objects share the same position, call **red.position().equals(blue.position())**. When you need both position and color to define the value, call **red.equals(blue)**. These are two comparisons with **two distinct purposes**.

**Records do not automatically make every inner field deeply immutable.** If a component is a mutable list, array, or object, its internal contents can still be modified or have unexpected equals semantics. In the example, **Point** is a record containing two ints and color is an immutable String, so the value key is simple and stable.

## 7. Other Design Strategies and Their Limitations

### 7.1. A Common Logical Key Treated as the Unique Identifier

Suppose both parent class and subclass represent the **same business entity**, with an immutable **id** key, while additional fields are merely descriptive data. Then you may choose **equals based solely on id** for all objects in the same identity domain (with appropriate type handling).

However, in that case two instances with the same id but different colors **must still be equal** under the chosen contract. You cannot simultaneously declare that **color is part of the equals value in the subclass** while ignoring it when comparing against the parent class.

One design option is to implement **final** equals/hashCode in the parent class for the shared identity key, or use a dedicated key. Marking equals **final** only prevents overriding; the ID policy itself must still fit the domain, distinguishing namespaces/tenants and ID lifecycles.

### 7.2. The canEqual Pattern

Some class designs that intentionally allow inheriting equals use the **canEqual** pattern, where the parent class asks the other object to acknowledge comparability through a bidirectional method, and a subclass refuses equality with the parent class when it adds value fields.

The core idea is that both sides must agree they **belong to the same comparable value kind** before checking individual fields. This pattern can preserve the contract for a tightly controlled hierarchy, but it requires **every subclass** to follow the same convention and implement equals/hashCode properly. You should not add canEqual as a local patch to an inheritance tree that already has inconsistent overrides.

### 7.3. Distinct Comparison Methods for Distinct Purposes

If you need both **same position** and **same position and color**, you can provide a method like **samePosition(Point)** or use a separate comparator/key extractor. Those methods can return different results from equals without conflict because **they do not claim to fulfill the Object.equals contract**.

For example, two ColoredPoints of different colors can return true for **samePosition**, yet false for **equals**. When stored in a HashSet, only equals/hashCode determines the set's notion of unique value.

### 7.4. Avoiding Value Inheritance When Unnecessary

A **final class** or **record** prevents subclasses from extending equality state; composition works when a richer value type is needed. This is usually simpler than maintaining the equals contract across multiple inheritance layers.

## 8. Common Mistakes When Fixing equals

**Switching instanceof to getClass only in the subclass.** If the parent class still accepts the subclass, you can still end up with:

~~~text
parent.equals(child) == true
child.equals(parent) == false
~~~

The rule must be aligned across **all involved classes**, not edited independently on one side.

**Including color in hashCode while still accepting plain Point as equal.** When ColoredPoint.equals(Point) is true while its hash also factors in color, you can directly violate the hashCode contract. The right approach is to fix the **equals definition** first and then align hashCode.

**Allowing a subclass to add a field without updating equals/hashCode.** If color is genuinely part of the value yet is not compared, two differently colored objects will still be considered equal. That is a domain-semantics bug; even if the relation remains reflexive, symmetric, and transitive, the result may still fail requirements.

**Using mutable fields to compute hashCode.** If coordinates, id, or color change after the object is used as a HashMap/HashSet key, subsequent lookups can fail. Prefer immutable key components and do not mutate state affecting equals/hashCode while used as a key.

**Assuming equal hashes mean equal values.** Two unequal objects can share a hash. HashMap/HashSet rely on both hashCode and equals; hashing does not replace equals.

**Ignoring null, proxies, and calls through parent references.** Equals takes **Object** and can be called from many sources. Tests must cover objects across different classes in the hierarchy, null cases, and any subclass types that actually occur in the application.

## 9. Regression Testing Checklist for Parent and Subclass

Build a sample set containing:

- **p1, p2:** two parent-class objects with the same value; **p3:** a parent-class object with a different value.
- **c1, c2:** two subclass objects with all value fields matching.
- **c3:** a subclass object differing only in the new field, e.g., color.
- **c4:** a subclass object differing in coordinates/inherited fields.
- All parent–child pairs sharing parent data but differing in runtime type; plus null.

Then verify:

1. **Reflexivity and null:** for every a, a.equals(a) == true and a.equals(null) == false.
2. **Symmetry:** for each pair a, b, check **a.equals(b) == b.equals(a)**. Especially swap parent–child order.
3. **Transitivity:** for every triple a, b, c where **a.equals(b)** and **b.equals(c)** are true, check that **a.equals(c)** is true; especially test **child A → parent → child B with different new field**.
4. **Hash compatibility:** whenever a.equals(b) is true, **a.hashCode() == b.hashCode()**.
5. **Consistency:** repeated calls while data does not change must yield the same result.
6. **HashSet/HashMap:** insert elements in multiple orders; the count of distinct logical values and lookup behavior must match the equals definition.
7. **Different subclasses:** if multiple subclasses inherit from the same parent, also test pairs between the two subclasses; testing only one subclass is not enough.

You can implement symmetry/transitivity checks as loops over the prepared samples or use an equals/hashCode verification library already used by the project. For tests using Java **assert**, the JVM must be run with the **-ea** flag for assertions to execute; test frameworks typically provide their own assertions.

### Self-Assessment Questions

1. Why is having **red.equals(plain)** and **plain.equals(blue)** both true while **red.equals(blue)** is false a contract bug, even though each method looks reasonable on its own?
2. Why does adding **color** to hashCode not fix the situation above?
3. When do you want **Point** to differ from **ColoredPoint** even when x and y match?
4. If color is only display information, which fields should equals and hashCode examine?
5. If the domain needs both “same position” and “same position and color”, why should you use **two clearly named comparisons** or **two value types**?

## 10. Design Choice Guide

| Domain Meaning | Appropriate Design | Contract to Preserve |
| --- | --- | --- |
| Subclass adds a field that **genuinely belongs to the equals value** | Compare consistently with **getClass** across the hierarchy, or use **composition/record** | Do not equate parent and child solely because shared data matches |
| Both parent and child represent the same entity; new field is only descriptive | Can use an **immutable logical identifier**, with consistent equals/hashCode | New field must not be checked in some cases and ignored in others within equals |
| Need multiple comparison criteria at the same time | Write **named methods**, a **key extractor**, or separate value types | Do not force conflicting criteria into a single equals |
| Open inheritance tree with multiple overriding subclasses | Re-examine architecture; consider **canEqual** or avoid value inheritance | Every class in the tree must preserve reflexivity, symmetry, transitivity, and hashCode |

**Core takeaway:** When a subclass adds a **value field**, the obvious bug is **broken symmetry** caused by the two classes accepting each other differently. Trying to fix it by having the subclass also accept the parent class can create a deeper bug: **broken transitivity** between two subclasses with different values, bridged by the parent class. For reliable equals, design **one consistent equality definition across all related types**; when an added field produces a distinct value, **separating value types or rejecting cross-class equality** is the clear approach.
