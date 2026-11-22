# Practice: Building an Immutable Coordinate Object with equals(), hashCode(), and toString()

## 1. Objectives and Requirements

This practice builds a **two-dimensional coordinate** data type `Point2D` in Java 17+. Each object represents a point with two integer coordinates `x` and `y`. Two independent objects must be considered **equal by value** when both `x` and `y` are equal; these objects must work properly when used as elements in a `HashSet` or as keys in a `HashMap`.

Upon completing this exercise, you should understand and be able to implement on your own:

1. **Immutability:** after being initialized, the coordinate state of a `Point2D` cannot be changed.
2. **`equals(Object)`:** properly define what it means for two coordinates to be equal; satisfy the reflexive, symmetric, transitive, consistent, and non-null properties.
3. **`hashCode()`:** equal objects must have the same hash code; a hash code is not a unique identifier.
4. **`toString()`:** output a readable, stable representation that is useful for logging/debugging.
5. **Practical usage:** create equal objects from separate `new` calls, put them into a `HashSet`/`HashMap`, and explain the results.

**Specification:** coordinates are represented using the integer type `int`; negative numbers, `0`, and the entire `int` range are allowed. The exercise only considers **2D coordinates**, without adding length, velocity, color, or extra state to the concept of equality.

## 2. Designing an Immutable Class Before Writing Code

A minimal yet correct design includes the following decisions:

| Component | Design | Why |
| --- | --- | --- |
| Class declaration | `public final class Point2D` | Prevents subclasses from changing `equals()` semantics or extending state in surprising ways. |
| Fields | `private final int x` and `private final int y` | Encapsulated, assigned once; `int` is a primitive type so there is no internal state for anyone else to mutate. |
| Constructor | Accepts `x` and `y`, assigns them to the two fields | Establishes complete state at creation time. |
| Read API | `x()` and `y()` | Only returns copies of primitive values; no setters. |
| `equals(Object)` | Compares both `x` and `y`, after checking the type | Equal by coordinate content, independent of sharing the same reference. |
| `hashCode()` | Combines the hash codes of the two coordinates using a fixed calculation | Compatible with `equals()`; the result does not change over time. |
| `toString()` | `Point2D{x=3, y=7}` | Helps identify state when printing/logging. |

There are no `setX()`, `setY()`, or any methods that reassign the two fields. Immutability is the key condition that allows a `Point2D` to maintain a stable hash code once it has been placed into a hash-based collection.

**Distinction:** `private` hides implementation details; `final` on a field prevents reassigning the field after initialization; `final` on a class prevents inheritance. By itself, `final` does not automatically create deep immutability if a field references a `List`, array, or mutable object. This example uses two `int` values, so the defensive copy problem does not arise.

## 3. Complete Implementation of Point2D.java

Create a file named exactly `Point2D.java`:

```java
public final class Point2D {
    private final int x;
    private final int y;

    public Point2D(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int x() {
        return x;
    }

    public int y() {
        return y;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof Point2D other)) {
            return false;
        }
        return x == other.x && y == other.y;
    }

    @Override
    public int hashCode() {
        int result = Integer.hashCode(x);
        result = 31 * result + Integer.hashCode(y);
        return result;
    }

    @Override
    public String toString() {
        return "Point2D{x=" + x + ", y=" + y + "}";
    }
}
```

This is **a standalone compilable Java class**: the file name and `public` class name match. `instanceof Point2D other` is pattern matching syntax supported in Java 17; if the checked object is `null` or not a `Point2D`, the conditional branch returns `false` without throwing `ClassCastException`.

### Why doesn't equals(Object) take Point2D as its parameter?

`Object` specifies the signature `public boolean equals(Object obj)`. If you only write `public boolean equals(Point2D other)`, that is an **overload**, not an override of `Object.equals(Object)`. Collections that use `equals(Object)` will continue to receive the reference comparison inherited from `Object`, defeating the purpose of comparing coordinates. `@Override` helps the compiler detect when the signature does not actually override the superclass method.

### Explaining each branch of equals

- `this == obj`: the exact same object is definitely equal to itself; this is a safe optimization, not a replacement for comparing values between two different instances.
- `!(obj instanceof Point2D other)`: returns `false` when `obj` is `null` or belongs to a different type; after the condition, the variable `other` has type `Point2D`.
- `x == other.x && y == other.y`: **both** coordinates must be identical. Since `x`/`y` are both `int`, the `==` operator accurately checks **primitive values**; if a field were a reference to a data type that needs value equality, the corresponding `equals()` must be considered.
- Because `Point2D` is `final`, there are no subclasses that need to decide whether to compare additional or fewer pieces of state; the `instanceof` check fits this design.

### Explaining hashCode

For two `int` coordinates, `Integer.hashCode(value)` returns that exact `int` value. The formula above produces the same result as:

```java
return 31 * x + y;
```

Using the multiplier `31` is a common way to combine fields. It **does not require every coordinate to have a distinct hash code**. For example, `Point2D(0, 31)` and `Point2D(1, 0)` both have `hashCode() == 31`, yet `equals() == false`.

When an `int` calculation exceeds the 32-bit integer range, Java applies integer arithmetic with overflow wrapping according to language rules; two objects with the same `x` and `y` still receive the same hash code. There is no need for exception handling on `int` addition or multiplication here.

`Objects.hash(x, y)` can be used for convenience, but its numeric result will **differ** from the formula used here due to the combining algorithm of `Objects.hash`; additionally, the varargs call may incur boxing/array allocation overhead. Choose one approach consistently and do not change the hash code while depending on old values stored/persisted elsewhere. For this exercise, the explicit formula is easy to understand and allocates no extra memory.

### Explaining toString

`toString()` returns a string stating **the exact type name and both coordinates** in a format of our choosing. Its goal is information for human readers and debugging, **not** a guaranteed data-interchange format for parsing. Do not put memory addresses, identity hash codes, or secrets into `toString()`. In this exercise, the two integer coordinates are public information and safe to display.

## 4. Runnable Demo Program (CoordinateDemo.java)

Create the file `CoordinateDemo.java` in the **same directory** as `Point2D.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class CoordinateDemo {
    public static void main(String[] args) {
        Point2D p = new Point2D(3, 7);
        Point2D sameCoordinates = new Point2D(3, 7);
        Point2D third = new Point2D(3, 7);
        Point2D otherCoordinates = new Point2D(3, 8);

        System.out.println("p = " + p);
        System.out.println("p == sameCoordinates: " + (p == sameCoordinates));
        System.out.println("p.equals(sameCoordinates): "
                + p.equals(sameCoordinates));
        System.out.println("p.equals(otherCoordinates): "
                + p.equals(otherCoordinates));
        System.out.println("p.equals(null): " + p.equals(null));
        System.out.println("p.equals(text): " + p.equals("3,7"));
        System.out.println("symmetric equality: "
                + (p.equals(sameCoordinates) == sameCoordinates.equals(p)));
        System.out.println("transitive equality: "
                + (p.equals(sameCoordinates)
                   && sameCoordinates.equals(third)
                   && p.equals(third)));
        System.out.println("hash(p): " + p.hashCode());
        System.out.println("hash(sameCoordinates): "
                + sameCoordinates.hashCode());

        Set<Point2D> set = new HashSet<>();
        System.out.println("set.add(p): " + set.add(p));
        System.out.println("set.add(sameCoordinates): "
                + set.add(sameCoordinates));
        System.out.println("set.add(otherCoordinates): "
                + set.add(otherCoordinates));
        System.out.println("set.size(): " + set.size());

        Map<Point2D, String> labels = new HashMap<>();
        labels.put(p, "checkpoint");
        System.out.println("lookup by equal key: "
                + labels.get(sameCoordinates));

        Point2D collisionA = new Point2D(0, 31);
        Point2D collisionB = new Point2D(1, 0);
        System.out.println("collision equal hashes: "
                + (collisionA.hashCode() == collisionB.hashCode()));
        System.out.println("collision equals: "
                + collisionA.equals(collisionB));

        Set<Point2D> collisionSet = new HashSet<>();
        collisionSet.add(collisionA);
        collisionSet.add(collisionB);
        System.out.println("collision set size: " + collisionSet.size());
    }
}
```

From the directory containing both files, run with JDK 17 or higher:

```bash
javac Point2D.java CoordinateDemo.java
java CoordinateDemo
```

Expected output, independent of `HashSet` iteration order:

```text
p = Point2D{x=3, y=7}
p == sameCoordinates: false
p.equals(sameCoordinates): true
p.equals(otherCoordinates): false
p.equals(null): false
p.equals(text): false
symmetric equality: true
transitive equality: true
hash(p): 100
hash(sameCoordinates): 100
set.add(p): true
set.add(sameCoordinates): false
set.add(otherCoordinates): true
set.size(): 2
lookup by equal key: checkpoint
collision equal hashes: true
collision equals: false
collision set size: 2
```

**Reading the results accurately:**

- `p == sameCoordinates` is `false` because two `new` calls create two instances; `equals` is `true` because the value pair (`3`, `7`) is the same. This is the difference between **identity** and **value**.
- Identical coordinates receive hash code `31 * 3 + 7 = 100`; different coordinates can share a hash code and still be **unequal according to `equals`**.
- `HashSet.add(sameCoordinates)` returns `false` because an equivalent element is already present; `HashSet.add(otherCoordinates)` returns `true` because it is a different coordinate.
- `HashMap.get(sameCoordinates)` retrieves the value stored with key `p`: `HashMap` uses the hash code to find candidates and `equals` to check key equality.
- Two coordinates with an intentional hash collision still coexist in `HashSet` (size 2). **Hash collision does not mean two objects are equal.** Hash codes only help organize lookup.

Quick verification table:

| Check | Expected | Reason |
| --- | --- | --- |
| `p.equals(p)` | `true` | Reflexive. |
| `p.equals(new Point2D(3, 7))` | `true` | Compares coordinates. |
| `p.equals(new Point2D(3, 8))` | `false` | Different `y`. |
| `p.equals(null)` | `false` | No object equals `null`. |
| `p.equals("3,7")` | `false` | Different type. |
| `new Point2D(-1, 0).equals(new Point2D(-1, 0))` | `true` | Negative numbers are valid values. |
| `equals` is `true` between two objects | Equal `hashCode` | Mandatory contract. |
| Equal `hashCode` between two objects | **Not enough to conclude** | Hash collisions are valid. |

## 5. Systematically Checking the Object Contract

### The equals(Object) contract

Properties to verify:

1. **Reflexive:** for any non-null reference `a`, `a.equals(a)` must be `true`.
2. **Symmetric:** `a.equals(b)` and `b.equals(a)` always yield the same result.
3. **Transitive:** if `a.equals(b)` and `b.equals(c)` are both `true`, then `a.equals(c)` must also be `true`.
4. **Consistent:** multiple calls with the same input state must return the same result.
5. **Non-null:** for any non-null reference `a`, `a.equals(null)` must be `false`.

The `Point2D` implementation satisfies these properties because the equality decision **is based solely on two immutable integer values**. Reflexivity is optimized via `this == obj`; the remaining properties are guaranteed by equality of the two integer coordinate pairs.

### The hashCode() contract

1. **If `a.equals(b) == true`, then `a.hashCode() == b.hashCode()` must hold.**
2. If no state relevant to `equals` changes, an object's hash code must remain consistent across calls within the same execution.
3. **If `a.equals(b) == false`, the two hash codes are not required to be different.** Any algorithm mapping a large value space into a 32-bit `int` can collide.

Overriding `equals` while forgetting `hashCode` causes subtle bugs in `HashSet`, `HashMap`, or other hash-based structures. Conversely, overriding only `hashCode` without overriding `equals` still will not make two different instances equal by value.

### The toString() contract

`Object.toString()` does not mandate strict equivalence properties like `equals/hashCode`. However, a useful representation should describe content, be readable, consistent, and avoid unintended ordering dependencies or side effects. Do not use `toString()` comparison instead of `equals()`: two different classes can render identically, and the string format may be changed to improve logging without changing the meaning of equality.

## 6. Why Are Immutable Objects Especially Suited as Keys?

Suppose the class had setters for `x` or `y`. After putting a key into a `HashMap`, changing its coordinates can cause `hashCode()` to change and `equals()` to no longer match the key's original slot in the hash table. Consequence: `map.get(key)` may fail to find the mapping just written, even when using **the exact same key reference**. This is a design bug, not a bug in `HashMap`.

Immutable objects prevent this class of mistake: the content participating in `equals/hashCode` is locked in at the constructor. Treat this as a rule: **every field used to compute equality/hash of a hash key must remain stable for the entire time the key resides in the collection**.

If you need to "move" a coordinate, create a new instance:

```java
Point2D oldPoint = new Point2D(3, 7);
Point2D movedPoint = new Point2D(oldPoint.x() + 1, oldPoint.y());
// oldPoint is still (3, 7); movedPoint is (4, 7).
```

The snippet above **illustrates the API, not a standalone program**; run it inside a method after compiling `Point2D.java`. Avoid mutating state internally in a mutating `translate`; if you add a translation method, it should **return a new `Point2D`**.

**Note on overflow:** `oldPoint.x() + 1` in Java uses `int` arithmetic; if the old value is `Integer.MAX_VALUE`, the result wraps around to `Integer.MIN_VALUE` according to `int` arithmetic. If your coordinate domain forbids overflow, check beforehand or use `Math.addExact` and handle `ArithmeticException`. This is independent of the `equals/hashCode` contract.

## 7. Common Implementation Mistakes

### Mistake 1: Comparing objects with == instead of equals

```java
new Point2D(3, 7) == new Point2D(3, 7) // false
```

Two `new` calls produce two distinct objects. Use `equals` to answer **whether the coordinates match**; use `==` when you truly need to check for **the same instance in memory**.

### Mistake 2: Comparing only one field

```java
// Wrong: omits y
return x == other.x;
```

Then (`3`, `7`) and (`3`, `8`) are treated as the same coordinate. The specification requires **both x and y** to participate.

### Mistake 3: Overriding only equals

```java
@Override
public boolean equals(Object obj) {
    // ... compare coordinates ...
}
// Missing hashCode(): inherits identity-based hashCode from Object.
```

This is **error-demonstrating code, not a runnable standalone class**. Objects that are equal according to `equals` may receive different hashes, causing `HashMap/HashSet` not to behave as expected.

### Mistake 4: Overriding only hashCode or using hashCode to decide equals

```java
// Wrong: a hash collision will be mistaken for equality.
return this.hashCode() == other.hashCode();
```

For example, `Point2D(0, 31)` and `Point2D(1, 0)` are two different coordinates despite sharing hash 31. `equals` must compare meaningful data, not infer equality backwards from hash.

### Mistake 5: Using mutable fields to build a hash key

Even if a field is declared `private`, a setter or returning a mutable array can allow the key's contents to change. With two `int` fields and no setters, the current class avoids that risk. If you later add a `List`, array, or `Date`, you must design defensive copies and safe getters when deep immutability is needed.

### Mistake 6: Wrong signature or forgetting @Override

`equals(Point2D)` **does not** replace `equals(Object)`. Always declare the method with the exact signature and annotate it with `@Override`. If you let an IDE auto-generate `equals/hashCode`, still verify that the selected field list matches the business requirements.

### Mistake 7: Extending the class without redesigning symmetry

A coordinate class might be subclassed as `ColoredPoint` with a color attribute. If the superclass allows subclasses to be equal when `x,y` match, while the subclass also requires the color to match, you can end up with `base.equals(colored) == true` yet `colored.equals(base) == false`. Making `Point2D` a `final class` prevents this inheritance scenario. If the problem requires a hierarchy, the equality policy must be designed consistently for **the entire hierarchy**; replacing `instanceof` with `getClass()` also has trade-offs and must be evaluated separately.

## 8. Comparison with record in Java 17+

Since Java 16, `record` is a concise declaration for an immutable group of data at the structural level. If the problem does not require practicing the three methods manually, we can write:

```java
public record Point2DRecord(int x, int y) {}
```

This snippet must be placed in `Point2DRecord.java`. The compiler automatically generates the canonical constructor, `x()`/`y()` accessors, `equals`, `hashCode`, and `toString` based on the record components. Two `Point2DRecord(3, 7)` records are equal by value; the default `toString` string has the form `Point2DRecord[x=3, y=7]`, which differs from `Point2D`'s manual format. A record's hash code is not required to match the number `100` in the `Point2D` class example.

**Record does not guarantee deep immutability:** if a component is an array or mutable type, the component reference is final, but its internal contents can still be mutated. To achieve deep immutability, you still need to consider defensive copying and how equality logic is constructed for that component.

In this practice, **implementing `Point2D` by hand** has educational value because it forces you to understand and verify the `Object` contract; `record` is a concise option to consider in real projects when appropriate.

## 9. Self-Practice Exercises and Completion Criteria

To test yourself, try the following changes in a copy of the program and predict the output beforehand:

1. Create `new Point2D(-4, 0)` twice. Are the two instances equal with `==`? What about `equals`? Do the pair of hashes match?
2. Change `otherCoordinates` to `new Point2D(3, 7)`. What does `set.add(otherCoordinates)` change from `true` to, and what is the set size then?
3. Try `Point2D(0, 31)` and `Point2D(1, 0)`. Why does `HashSet` still contain both even though `hashCode()` is equal?
4. Add a `translate(int dx, int dy)` method that returns a new point; verify the original point and its hash code remain unchanged. If you want to detect `int` overflow, you can use `Math.addExact`.
5. Temporarily delete `hashCode()` in a test copy and rerun the `HashMap` lookup using a separately created equivalent key. Explain why the program is no longer guaranteed to work properly in hash-based collections.

**Completion criteria:**

- Class `Point2D` is `final`; `x` and `y` are `private final int`; has a complete constructor, accessors, and no setters.
- `equals(Object)` checks the type properly, handles `null`, and compares **both** coordinates.
- `hashCode()` uses the exact fields that `equals()` uses; stable after initialization.
- `toString()` displays both coordinates accurately and does not mutate state.
- Two objects with the same coordinates are treated as one element by `HashSet` and can be used interchangeably for `HashMap` lookup.
- Two objects with colliding hashes but different coordinates remain two distinct elements.
- The demo compiles with Java 17+ and produces the output shown above.

## 10. Knowledge Summary

The three methods `equals()`, `hashCode()`, and `toString()` serve distinct purposes: **value comparison**, **hash-based collection support**, and **human-readable representation**. Building `Point2D` as immutable keeps equality and hash decisions stable, making it suitable for use as a value object. Whenever extending or changing the definition of a coordinate, always revisit *both* `equals` and `hashCode`, and verify the impact on `HashSet`/`HashMap`.

## References

- [Java SE 17 — Object.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): requirements for equivalence.
- [Java SE 17 — Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()): contract when using objects in hash structures.
- [Java SE 17 — Object.toString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#toString()): string representation of an object.
- [Java SE 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html) and [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): behavior of hash-based collections.
- [Java SE 17 — Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): base API for records.