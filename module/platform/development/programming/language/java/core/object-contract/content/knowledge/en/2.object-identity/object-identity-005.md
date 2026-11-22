# `Object.equals()` Defaults to Identity

## 1. Objective and Concepts

When a Java class does not override `equals(Object)`, the method inherited from `java.lang.Object` only checks **object identity**. This explains why two instances with the exact same field values can still return `false` when calling `equals()`.

We must distinguish:

- **Identity:** whether two references point to **the exact same object**.
- **Value:** the data an object stores, such as a point with `x = 2` and `y = 3`.
- **Value equality:** a rule explicitly defined by a class to treat two objects with relevant matching values as equal.

`Point p1 = new Point(2, 3);` and `Point p2 = new Point(2, 3);` create **two separate objects**. If the `Point` class does not redefine `equals()`, `p1.equals(p2)` is `false`, even though the coordinates match. Conversely, `Point alias = p1;` only copies the reference; `p1` and `alias` point to one object.

## 2. The Default Mechanism of `Object.equals()`

Every regular Java class inherits from `Object` directly or indirectly. When a class does not override `equals(Object)`, the default behavior is equivalent to:

```java
public boolean equals(Object obj) {
    return this == obj;
}
```

The snippet above illustrates the method body of `Object`, **not a standalone program**. For two references, `==` checks whether they point to **the same object**. It does not automatically inspect all fields, does not compare `toString()`, and does not check whether two objects have “identical content”.

| Expression with non-null `a` | Result if using `Object.equals()` | Explanation |
| --- | --- | --- |
| `a.equals(a)` | `true` | An object is identical to itself. |
| `a.equals(alias)` when `alias = a` | `true` | Two variables hold the same reference. |
| `a.equals(b)` when `b` is a new object | `false` | Two entities with different identities, even if fields are equal. |
| `a.equals(null)` | `false` | No object is identical to null. |
| `a == alias` | `true` | `==` compares reference identity. |

**Note on dynamic dispatch:** `a.equals(b)` executes the `equals` implementation of `a`'s actual runtime class. Therefore `equals()` is synonymous with `==` only when the invoked implementation is `Object`'s default method (or an override that intentionally keeps the same logic). Classes like `String` have different rules.

## 3. Complete Java 17+ Example

Create the file `ObjectEqualsDemo.java` with the exact public class name:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ObjectEqualsDemo {
    // Inherits Object's default equals/hashCode.
    static final class PlainPoint {
        final int x;
        final int y;

        PlainPoint(int x, int y) {
            this.x = x;
            this.y = y;
        }
    }

    // Explicitly defines equality based on the two coordinates.
    static final class ValuePoint {
        final int x;
        final int y;

        ValuePoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof ValuePoint point)) {
                return false;
            }
            return x == point.x && y == point.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    public static void main(String[] args) {
        PlainPoint first = new PlainPoint(2, 3);
        PlainPoint alias = first;
        PlainPoint second = new PlainPoint(2, 3);

        System.out.println("first == alias: " + (first == alias));
        System.out.println("first.equals(alias): " + first.equals(alias));
        System.out.println("first == second: " + (first == second));
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("first.equals(null): " + first.equals(null));

        ValuePoint v1 = new ValuePoint(2, 3);
        ValuePoint v2 = new ValuePoint(2, 3);
        Set<ValuePoint> points = new HashSet<>();
        points.add(v1);

        System.out.println("v1 == v2: " + (v1 == v2));
        System.out.println("v1.equals(v2): " + v1.equals(v2));
        System.out.println("points.contains(v2): " + points.contains(v2));

        String s1 = new String("java");
        String s2 = new String("java");
        System.out.println("s1 == s2: " + (s1 == s2));
        System.out.println("s1.equals(s2): " + s1.equals(s2));
        System.out.println("Objects.equals(null, null): " +
                Objects.equals(null, null));
    }
}
```

Compile and run commands:

```bash
javac ObjectEqualsDemo.java
java ObjectEqualsDemo
```

Output:

```text
first == alias: true
first.equals(alias): true
first == second: false
first.equals(second): false
first.equals(null): false
v1 == v2: false
v1.equals(v2): true
points.contains(v2): true
s1 == s2: false
s1.equals(s2): true
Objects.equals(null, null): true
```

Analysis:

1. `first` and `alias` point to the same `PlainPoint`, so both `==` and the default `equals()` are `true`.
2. `first` and `second` are two independent `new` creations: the coordinates match, but the identities differ, so both comparisons are `false`.
3. `v1` and `v2` are two separate `ValuePoint`s: `==` is `false`, while `equals()` is `true` because the class compares `x` and `y`.
4. `HashSet` finds `v2` even though only `v1` was added because `ValuePoint`'s `equals()` and `hashCode()` are consistent.
5. Two `new String("java")` calls create two separate `String` objects. `String` overrides `equals()` to compare string content, so `==` is `false` and `equals()` is `true`.
6. `Objects.equals(null, null)` returns `true`, demonstrating a null-safe comparison unlike calling a method directly on null.

## 4. When Should You Keep or Override `equals()`?

**Keep the default** when the distinction between instances is meaningful: two independent objects must be distinguished even if some attributes match. This is a valid design choice, not a Java flaw.

**Override** when the class represents a value, such as coordinates, monetary amounts (including currency unit), identifier keys, or a value object with clear rules. In that case, decide which fields truly constitute equality. In `ValuePoint`:

- `this == other` quickly answers the same-reference case.
- `instanceof ValuePoint point` properly handles null or mismatched types before accessing fields; this pattern matching syntax is supported in Java 17.
- `x == point.x && y == point.y` compares the components that form the value.
- `hashCode()` uses those exact same components, staying compatible with `equals()`.

A Java record can be suitable for simple value objects. For example, `record Point(int x, int y) {}` has `equals()`/`hashCode()` generated by Java based on its components; **that is record-specific behavior**, not the default `Object.equals()`.

### The `equals` Contract

A proper `equals` implementation must guarantee:

1. **Reflexivity:** `x.equals(x)` is `true` if `x` is non-null.
2. **Symmetry:** if `x.equals(y)` is `true`, then `y.equals(x)` is also `true`.
3. **Transitivity:** if `x.equals(y)` and `y.equals(z)` are `true`, then `x.equals(z)` is `true`.
4. **Consistency:** when state involved in the comparison does not change, repeated calls do not arbitrarily yield different results.
5. **For null:** `x.equals(null)` is `false` if `x` is non-null.

`Object`'s default identity comparison satisfies all five properties. When overriding it yourself, you must consider inheritance and mutable fields to avoid breaking the contract.

### The Contract Between `equals` and `hashCode`

When `a.equals(b)` returns `true`, `a.hashCode() == b.hashCode()` **must** also be `true`. The converse is not true: two unequal objects can still share the same hash (a collision). Therefore, equal hashes **do not prove** two objects are identical.

If you only override `equals()` by value while continuing to use `Object.hashCode()`, two objects considered equal may receive different hashes and break the assumptions of `HashMap`/`HashSet`. Consequently, when changing equality logic, you must design `hashCode()` accordingly. Avoid mutating fields involved in equality/hashing while an object is serving as a key in a hash collection.

The default `Object.hashCode()` supports the contract for identity-based equality. The returned value **is not guaranteed to be a memory address** or globally unique. `System.identityHashCode(obj)` retrieves the identity-based hash even when the class overrides `hashCode()`, yet hash collisions are still possible, so it cannot replace `==`.

## 5. Easily Misunderstood Situations

| Situation | Correct Understanding |
| --- | --- |
| `new String("A").equals(new String("A"))` | `true` because `String` overrides it by content, not default behavior. |
| Two separately created `new int[]{1, 2}` arrays | Arrays inherit `Object.equals()`, so the two arrays have different identities. Use `Arrays.equals(a, b)` to compare one-dimensional array elements; consider `Arrays.deepEquals` for nested arrays. |
| Two `List`s containing equal corresponding sequences of elements | Standard `List` implementations compare element by element; this cannot be inferred from `Object`'s default behavior. |
| `a.equals(null)` | `false` if `a` is non-null. However, `null.equals(a)` throws `NullPointerException`, because null has no method to call. |
| `Objects.equals(a, b)` | Two nulls are considered equal, one null and one non-null are unequal, otherwise `a.equals(b)` is called. |
| `==` with primitive types | Compares **primitive values**, not identity. Only when operands are references does it check for the same object. |
| `==` with wrapper objects or strings | Results can be affected by boxing, caching, or string interning. When the goal is value comparison, use `equals()` appropriately. |

**Do not rely on `toString()`, `hashCode()`, or assumed addresses** to evaluate identity. `hashCode()` is not a unique identifier key. Nor should you assume two new objects always have all different state; two separate objects can share the same value, and this very point highlights the difference between identity and equality.

## 6. Choosing the Right Comparison Tool

| Need | Use | What to Check |
| --- | --- | --- |
| Do two variables point to the exact same object? | `a == b` | Compares references; also use `a == null`. |
| Are two objects equal by the class's rules? | `a.equals(b)` | `a` must be non-null; read the class's `equals` contract. |
| Comparison that might encounter null? | `Objects.equals(a, b)` | Two nulls are considered equal. |
| Writing your own value object? | Override `equals()` and `hashCode()` together, or use a record | Clearly choose the components participating in equality. |
| Lookup in `HashMap`/`HashSet`? | By `equals()` combined with `hashCode()` | Equal objects must have equal hashes; keys should not mutate state affecting the hash. |

## 7. Self-Check

**Question 1:** If `PlainPoint b = a;`, what do `a.equals(b)` and `a == b` return when `PlainPoint` does not override `equals`?

**Answer:** Both are `true` because they share the same reference.

**Question 2:** Are two `new PlainPoint(2, 3)` calls equal according to `Object.equals()`?

**Answer:** No. Two separate objects have different identities, even though their fields match.

**Question 3:** Why is `new String("x").equals(new String("x"))` `true`?

**Answer:** `String` has an `equals()` implementation that compares string content; it does not use the default identity comparison.

**Question 4:** If two objects have equal hash codes, are they guaranteed to be equal by `equals()` or `==`?

**Answer:** No. Hash collisions can happen. Only the direction “`equals()` is equal ⇒ hash codes are equal” is required by the contract.

**Remember:** The default `Object.equals()` answers the question **“is it the same object?”**. The question **“do they have the same meaningful value?”** requires a class's own `equals()` definition.