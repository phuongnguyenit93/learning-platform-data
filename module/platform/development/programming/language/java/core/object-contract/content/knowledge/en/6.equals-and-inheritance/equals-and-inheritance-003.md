# Type Checking with `instanceof` or `getClass()` When Implementing `equals()` in Java

## 1. Why Does Type Checking Affect `equals()`?

In Java, `equals(Object other)` determines when two **objects** are considered equal according to the meaning of the class. Before comparing data fields, the method usually checks whether the right-hand object belongs to the **domain of objects allowed to be compared for equality** with the left-hand object.

When a class can be inherited, two checking approaches lead to different policies:

- `other instanceof Point`: accepts instances of `Point` **and any subclass** of `Point` (if non-`null`). This is a **same-type or subtype** check.
- `getClass() == other.getClass()`: accepts only two objects that have the **exact same runtime class**. This is an **identical actual-class** check.

The most important difference emerges when a subclass adds data fields or overrides `equals()`. A parent class may consider a subclass equal based on the parent's fields, while the subclass also needs to compare its own field. If implemented inconsistently, `equals()` can violate **symmetry** or **transitivity**.

This topic is about **choosing the type-comparison domain in `equals()`**. The `==` operator between two reference variables still checks **object identity**, not the equality criterion defined by `equals()`.

## 2. Precisely Distinguishing `instanceof` and `getClass()`

### `instanceof`: Accepts Inheritance or Interface Implementation

For the expression `obj instanceof T`, the result is `true` if the runtime object is an instance of `T`, a subclass of `T`, or a class implementing interface `T` (under the appropriate type relationship); if `obj == null`, the result is always `false`.

Java 17 supports **pattern matching for `instanceof`**:

```java
if (other instanceof Point point) {
    // point already has type Point, no manual cast needed.
}
```

Pattern matching only declares the `point` variable where the compiler determines the check has succeeded. For example, `if (!(other instanceof Point point)) return false;` allows using `point` after the `if` statement because the failing branch has returned.

### `getClass()`: Requires an Exact Runtime Class Match

`Object.getClass()` returns a `Class<?>` object representing the **actual runtime class**, not the declared type of the variable. Comparing two `Class` objects with `==` is appropriate because the same class in the same class-loading context is represented by the same `Class` object.

```java
if (other == null || getClass() != other.getClass()) {
    return false;
}
```

You must check `other == null` before calling `other.getClass()`; otherwise a `NullPointerException` will occur. By contrast, `null instanceof Point` simply returns `false`.

### Runnable Example: Declared Type Does Not Determine `getClass()`

Create the file `TypeCheckDemo.java`:

```java
public class TypeCheckDemo {
    interface Identified {}

    static class Parent implements Identified {}

    static final class Child extends Parent {}

    public static void main(String[] args) {
        Parent polymorphic = new Child();
        Parent parent = new Parent();
        Object nothing = null;

        System.out.println("is Parent: " + (polymorphic instanceof Parent));
        System.out.println("is Child: " + (polymorphic instanceof Child));
        System.out.println("is Identified: " + (polymorphic instanceof Identified));
        System.out.println("exact Parent: " + (polymorphic.getClass() == Parent.class));
        System.out.println("exact Child: " + (polymorphic.getClass() == Child.class));
        System.out.println("parent exact Parent: " + (parent.getClass() == Parent.class));
        System.out.println("null instanceof Parent: " + (nothing instanceof Parent));
    }
}
```

Compile and run (Java 17+):

```bash
javac -encoding UTF-8 TypeCheckDemo.java
java TypeCheckDemo
```

Stdout:

```text
is Parent: true
is Child: true
is Identified: true
exact Parent: false
exact Child: true
parent exact Parent: true
null instanceof Parent: false
```

The `polymorphic` variable is declared as `Parent` but holds a `Child` object. Therefore `instanceof Parent` is `true`, whereas `polymorphic.getClass() == Parent.class` is `false`. In this case, `getClass()` yields `Child.class`.

## 3. Reviewing the `equals()` Contract Before Choosing a Type Check

For non-`null` object references, a correct `equals()` implementation must satisfy:

1. **Reflexive:** `x.equals(x)` is always `true`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` always have the same value.
3. **Transitive:** if both `x.equals(y)` and `y.equals(z)` are `true`, then `x.equals(z)` must also be `true`.
4. **Consistent:** repeated comparisons return the same result when relevant state does not change.
5. **Against `null`:** `x.equals(null)` is `false`.

The companion contract of `hashCode()`: **if `x.equals(y)` is `true`, then `x.hashCode() == y.hashCode()` must hold**. The converse is not required: two unequal objects may still share the same hash code.

Collections such as `HashSet` and `HashMap` require both `equals()` and `hashCode()` to operate consistently. Choosing `instanceof` or `getClass()` alone is not enough to guarantee the entire contract: you must also consider which fields participate in comparison, data immutability, and how subclasses override methods.

## 4. Risk When the Parent Uses `instanceof` and the Subclass Adds Equality Criteria

Suppose class `Point` only cares about coordinates `x, y`. Subclass `ColoredPoint` adds `color` and wants color to also participate in the equality definition.

Create the file `BadInstanceofDemo.java`:

```java
import java.util.Objects;

public class BadInstanceofDemo {
    static class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (!(obj instanceof Point other)) return false;
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
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
            if (!(obj instanceof ColoredPoint other)) return false;
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + color.hashCode();
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColoredPoint red = new ColoredPoint(1, 2, "red");

        System.out.println("plain.equals(red): " + plain.equals(red));
        System.out.println("red.equals(plain): " + red.equals(plain));
    }
}
```

```bash
javac -encoding UTF-8 BadInstanceofDemo.java
java BadInstanceofDemo
```

Stdout:

```text
plain.equals(red): true
red.equals(plain): false
```

This is an **INTENTIONALLY WRONG example** to make the bug visible:

- `plain.equals(red)` checks `red instanceof Point`, which is true, and then compares only `x, y`: result is `true`.
- `red.equals(plain)` checks `plain instanceof ColoredPoint`, which is false: result is `false`.
- The **symmetry** contract is broken. The two `hashCode()` values can also differ even though the comparison from `plain`'s side returned `true`, making the design even more unsuitable for hash-based collections.

You should not merely “patch” the bug by letting the subclass ignore color when encountering a `Point`. If `Point(1,2)` is considered equal to both a red point and a blue point, while the two differently colored points are not equal to each other, **transitivity** can also be broken. You must choose a consistent equality policy for the entire class hierarchy.

## 5. Solution Using `getClass()`: Equal Only When Actual Classes Match

When `Point` and `ColoredPoint` represent **two distinct value types**, disallowing equality across class boundaries is a clear option. Each class first compares `getClass()`, and only then compares the fields that define that class's value.

Create the file `ExactClassEqualityDemo.java`:

```java
import java.util.Objects;

public class ExactClassEqualityDemo {
    static class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (obj == null || getClass() != obj.getClass()) return false;
            Point other = (Point) obj;
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
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
            if (this == obj) return true;
            if (obj == null || getClass() != obj.getClass()) return false;
            ColoredPoint other = (ColoredPoint) obj;
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + color.hashCode();
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColoredPoint red = new ColoredPoint(1, 2, "red");
        ColoredPoint redCopy = new ColoredPoint(1, 2, "red");
        ColoredPoint blue = new ColoredPoint(1, 2, "blue");

        System.out.println("plain.equals(red): " + plain.equals(red));
        System.out.println("red.equals(plain): " + red.equals(plain));
        System.out.println("red.equals(redCopy): " + red.equals(redCopy));
        System.out.println("red.equals(blue): " + red.equals(blue));
        System.out.println("equal hash: " + (red.hashCode() == redCopy.hashCode()));
    }
}
```

```bash
javac -encoding UTF-8 ExactClassEqualityDemo.java
java ExactClassEqualityDemo
```

Stdout:

```text
plain.equals(red): false
red.equals(plain): false
red.equals(redCopy): true
red.equals(blue): false
equal hash: true
```

Here:

- `Point` and `ColoredPoint` **are never equal** even when their coordinates match. Both comparison directions return `false`, avoiding the symmetry bug in the previous example.
- Two `ColoredPoint` instances are compared by both `x, y` (via `super.equals(other)`) and `color`.
- `ColoredPoint`'s `hashCode()` combines the exact data parts that `equals()` uses. Two equal colored points are guaranteed to have equal hash codes.
- Calling `super.equals(other)` remains valid in this example because both `this` and `other` are `ColoredPoint` when the `Point` method runs; the `getClass()` check in the parent class therefore succeeds.

**Design note:** `getClass()` does not automatically make `equals()` correct. If a subclass has state affecting value identity yet simply inherits the parent's `equals()`, two instances of the same subclass may still be treated as equal despite differing in the added state. The subclass must redefine the comparison policy and `hashCode()` consistently, or the hierarchy must be designed so subclasses cannot add data affecting equality.

## 6. When Is `instanceof` a Valid Choice?

`instanceof` **is not inherently wrong**. It is useful when the domain policy wants objects in the same hierarchy to be considered equal based on **a shared set of attributes**, regardless of the concrete subclass. However, subclasses cannot be allowed to arbitrarily change the equality criterion.

One way to guarantee that is for the parent class to define `equals()` and `hashCode()` as `final`, while explicitly specifying that extra subclass fields **do not contribute to equality**.

Create the file `HierarchyEqualityDemo.java`:

```java
public class HierarchyEqualityDemo {
    static class Coordinate {
        final int x;
        final int y;

        Coordinate(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public final boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Coordinate other)) return false;
            return x == other.x && y == other.y;
        }

        @Override
        public final int hashCode() {
            return 31 * x + y;
        }
    }

    static final class LabeledCoordinate extends Coordinate {
        final String label;

        LabeledCoordinate(int x, int y, String label) {
            super(x, y);
            this.label = label;
        }
    }

    public static void main(String[] args) {
        Coordinate plain = new Coordinate(1, 2);
        LabeledCoordinate a = new LabeledCoordinate(1, 2, "A");
        LabeledCoordinate b = new LabeledCoordinate(1, 2, "B");

        System.out.println("plain.equals(a): " + plain.equals(a));
        System.out.println("a.equals(plain): " + a.equals(plain));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("same hash: " + (plain.hashCode() == a.hashCode()));
    }
}
```

```bash
javac -encoding UTF-8 HierarchyEqualityDemo.java
java HierarchyEqualityDemo
```

Stdout:

```text
plain.equals(a): true
a.equals(plain): true
a.equals(b): true
same hash: true
```

Here two coordinates are equal when they share `x, y`, **and label is merely display information**. Because equality in the parent class is `final`, the subclass cannot override it with its own rule and break symmetry. This is only appropriate when requirements genuinely allow ignoring `label`; if the label distinguishes values, a different equality policy is required.

For a **`final` class with no subclasses**, the two type checks usually have an equivalent acceptance domain when comparing against that class itself: `other instanceof MyFinalType` and `other != null && other.getClass() == MyFinalType.class`. In this case, `instanceof` is usually more concise; the choice mainly requires careful thought when the class can be inherited.

## 7. Situations to Consider Before Deciding

### Runtime Type, Proxies, and Frameworks

Some frameworks may generate **proxy subclasses** of entity or domain classes. `getClass()` compares runtime classes strictly, so a proxy object and a real object of the base class may be evaluated as different classes even with identical data. However, immediately switching to `instanceof` does not automatically solve the entire entity equality problem either (such as unsaved identity, proxies, and mutable state). When using a framework like an ORM, follow an equality policy aligned with the framework's proxy/identity mechanism and test both comparison directions.

### Comparing Against an Interface or Multiple Inheritance Branches

`instanceof` can accept objects belonging to different runtime classes that implement the same interface. This is useful for **checking an object's capability**, but does not by default mean every implementation of the interface has the same **equality semantics**. Before using it in `equals()`, you must determine which fields/properties are compared and ensure all branches follow the same criterion.

### Stability of Data Participating in Equality

Regardless of which type check you choose, using **mutable** fields as the basis for both `equals()` and `hashCode()` can cause issues after inserting the object into a `HashSet` or using it as a `HashMap` key: mutating a field can cause its hash code or logical bucket to change. For value objects, prefer immutable data and consistent equality. For entities, define a specific policy aligned with the identity lifecycle.

### `equals()` Does Not Replace `==`

`this == other` at the start of `equals()` is a valid optimization: the same object is always equal to itself if the contract is respected. It does not replace type checking and field comparison for **two distinct objects**. Conversely, `getClass() == other.getClass()` compares the **runtime class representation**, not whether two data objects share the same identity.

## 8. Quick Selection Table: `instanceof` vs `getClass()`

| Design Question | Selection Guidance |
| --- | --- |
| May two different classes in the hierarchy be considered equal? | If **no**, exact class checking with `getClass()` is an easy policy to express. |
| Are all subclasses merely different representations of the same underlying value? | `instanceof` can be used with shared equality in the parent; consider `final equals()` and `final hashCode()`. |
| Does a subclass need to add a field participating in equality? | Avoid having the parent use `instanceof` to accept subclasses while the subclass narrows the comparison; a hierarchy-wide contract-preserving policy is needed. |
| Is the class `final` and non-inheritable? | `instanceof` is usually simple; `getClass()` can also be correct but brings no clear extra benefit. |
| Are there framework-generated proxies/runtime subclasses? | Verify the framework-appropriate way to obtain class/identity before using `getClass()` directly. |
| Can the right-hand object be `null`? | `instanceof` returns `false` automatically; with `getClass()`, you must check `null` first. |

## 9. Testing Checklist for `equals()` in an Inheritance Hierarchy

With classes `Base`, `ChildA`, and `ChildB`, test at least:

1. **Same object:** `a.equals(a)` is `true`.
2. **Null:** `a.equals(null)` is `false`.
3. **Same class:** distinct objects with matching value fields have the expected equality result.
4. **Different classes:** compare both `base.equals(child)` **and** `child.equals(base)`; they must be consistent.
5. **Two subclasses:** compare two instances of the same subclass and instances of two different subclasses according to the chosen policy.
6. **Transitivity:** form triples `x, y, z` across different runtime types; if the first two relations are `true`, the third must be `true`.
7. **Hash:** for every pair where `x.equals(y)` is true, check `x.hashCode() == y.hashCode()`; also test operations with `HashSet`/`HashMap` when applicable.
8. **State:** test how objects behave if data participating in equality can be mutated, especially after being used as hash keys.
9. **Proxies (if any):** test real/proxy object pairs according to the framework's actual policy.

**Takeaway:** `instanceof` answers “does this object belong to the requested type or a compatible subtype/implementation?”, whereas `getClass()` answers “what is the exact runtime class?”. When writing `equals()`, what decides the design is **equality semantics across the entire class hierarchy**. The right approach must preserve symmetry, transitivity, and the `hashCode()` contract, even when subclasses are added later.