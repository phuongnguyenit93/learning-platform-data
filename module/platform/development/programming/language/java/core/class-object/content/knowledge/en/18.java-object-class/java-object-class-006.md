# The `equals()` Contract and Its Relationship with `hashCode()` in Java

## Learning Objectives

After this lesson, you can:

- Distinguish **object identity** (*identity*) from **value/semantic equality** (*logical equality*).
- Explain how `Object.equals(Object)` and `Object.hashCode()` work by default, when to override them, and why you usually must override **both**.
- Recall and apply the five fundamental requirements of the `equals()` contract: **reflexive**, **symmetric**, **transitive**, **consistent**, and **not equal to `null`**.
- Understand the mandatory rule of `hashCode()`: **two objects equal according to `equals` must have equal hash codes**, and understand that the converse **is not true**.
- Design an immutable value object with correct `equals` and `hashCode`, using `Objects.equals`/`Objects.hash` or direct hash computation.
- Analyze the behavior of `HashSet`, `HashMap`, `LinkedHashMap` and why mutating a key's state after adding it to a hash collection causes lookup failures.
- Identify bugs such as **overriding only `equals`**, basing hash code on different fields, failing to handle null, comparing fields with `==`, and violating symmetry under inheritance.
- Distinguish `getClass()` from `instanceof` when implementing `equals`, considering `final` classes, sealed hierarchies, and inheritance/extensibility issues.
- Compare equality of primitive values, reference fields, arrays, nested arrays, `BigDecimal`, records, and enums; do not equate `compareTo()==0` with `equals()`.
- Write deterministic tests for reflexivity/symmetry/transitivity/hash consistency without assuming specific `hashCode()` values or `HashMap` iteration order.
- Apply this knowledge when creating keys, caches, sets, domain value objects, and APIs with clear equality contracts in Java 17+.

## 1. Three Different Questions

Consider:

~~~java
String first = new String("Java");
String second = new String("Java");
String alias = first;
~~~

The questions:

1. **`first == second`?** No. The two references point to two separate `String` objects (`new` was used twice).
2. **`first.equals(second)`?** Yes. `String` defines equality based on the character sequence.
3. **`first == alias`?** Yes. Both variables point to the same object.

Using `==` between **references** is primarily for comparing **identity**. Use `equals` when you want to apply the **equality contract published by the class**.

For example, a `Customer` has a `customerId`: should two separate objects with the same ID be considered the same customer? It depends on the domain decision. Java does not automatically know that the ID is the equality criterion. You must choose the contract, implement it correctly, and keep it consistent.

### 1.1. How `equals` Differs from `==` for Primitives

With `int a = 7; int b = 7;`, `a == b` compares primitive values and returns true. Primitives do not have an `equals` instance method.

With `Integer x`/`Integer y` being references, `x == y` compares object identity, whereas `x.equals(y)` compares numeric value according to Integer's contract. **Do not rely on `Integer == Integer` to infer value equality**, because caching/boxing can result in different identities.

### 1.2. Not Every `equals` Compares Every Field

A value object `Money(amount, currency)` might consider both amount and currency. An entity `Order(id, status)` might define equality by its stable ID while ignoring the changing status. A DTO might want equality across all data fields.

**The equality criteria are an API/domain decision**; there is no "always take all fields" formula that applies to every class.

## 2. Default `Object.equals` and `Object.hashCode`

Every regular class directly or indirectly inherits from `java.lang.Object`. Without overriding:

- `Object.equals(Object)` uses **identity equality**: an object is equal only to itself.
- `Object.hashCode()` returns an `int` value suitable for Object's hash contract; **it must not be treated as a memory address** or an absolute unique ID.
- `hashCode()` does not guarantee that all distinct objects have distinct values.
- A hash code is not a security key, digital signature, persistent ID, or a way to confirm that two objects are identical.

### 2.1. Default Demo

Save **`ObjectIdentityDemo.java`**:

~~~java
public class ObjectIdentityDemo {
    static final class Box {
        private final int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box first = new Box(7);
        Box second = new Box(7);
        Box alias = first;

        System.out.println("first==second=" + (first == second));
        System.out.println("first.equals(second)=" +
                first.equals(second));
        System.out.println("first==alias=" + (first == alias));
        System.out.println("first.equals(alias)=" +
                first.equals(alias));
    }
}
~~~

Compile and run on Java 17+:

~~~bash
javac ObjectIdentityDemo.java
java ObjectIdentityDemo
~~~

**Stdout:**

~~~text
first==second=false
first.equals(second)=false
first==alias=true
first.equals(alias)=true
~~~

Even though both Box objects have the same `value = 7`, the `Box` class has not overridden `equals`, so the result still follows **identity**.

**Do not print `first.hashCode()` and claim the output must be a specific number.** Default hash values are not fixed across JVMs or runs. The program here intentionally prints only the results guaranteed by Java.

## 3. The Formal Contract of `equals(Object)`

For **non-`null`** references, the `Object.equals` contract specifies five properties.

### 3.1. Reflexivity (*reflexive*)

For any non-null object `x`:

~~~java
x.equals(x) == true
~~~

If an object is not equal to itself, many collections and algorithms will no longer make sense.

### 3.2. Symmetry (*symmetric*)

For any non-null `x` and `y`:

~~~java
x.equals(y) == y.equals(x)
~~~

If `x` considers `y` equal to itself, `y` must also consider `x` equal to it. This is a very common bug when a superclass uses `instanceof` while a subclass adds its own fields to `equals`.

### 3.3. Transitivity (*transitive*)

For any non-null `x`, `y`, and `z`:

~~~java
if (x.equals(y) && y.equals(z)) {
    // x.equals(z) must also be true.
}
~~~

For example, if two addresses A and B are considered equal, and B and C are equal, then A and C must also be equal. An equality check with a "tolerance threshold" easily violates transitivity.

### 3.4. Consistency (*consistent*)

Multiple invocations of `x.equals(y)` must return the same result **provided no information used in the comparison changes**.

This does not require every mutable object to keep its equality forever. If a class allows modifying state that participates in equality, the result can change; this is especially dangerous when the object is currently a key in a `HashMap` or an element of a `HashSet`.

### 3.5. Comparison with `null`

For any non-null object `x`:

~~~java
x.equals(null) == false
~~~

A good implementation returns false, **and does not throw `NullPointerException`** simply because the `other` parameter is null.

### 3.6. Satisfying the Contract Is Not Enough: `equals` Must Answer the Right Domain Question

The properties above ensure a logically valid **equivalence relation**. They do not by themselves determine which equality criteria are useful. Two `Money` instances with amount 10 but different currencies should not be equal; two event logs with the same timestamp do not necessarily have the same identity.

Before writing code, state the fields and rules that participate in equality. Only then should you safeguard the five properties.

## 4. The Mandatory Relationship with `hashCode()`

The `Object.hashCode` contract has three key points:

1. During a single execution of a Java application, provided no information used in `equals` checks is modified, multiple invocations of `hashCode()` on the same object must return the same `int` (it is not required to remain the same across different program runs).
2. If `a.equals(b)` is `true`, **`a.hashCode() == b.hashCode()` must be true**.
3. If `a.equals(b)` is `false`, the hash codes **are not required to be different**. Hash collisions are valid behavior.

In short:

~~~text
a.equals(b) == true
              |
              v
a.hashCode() == b.hashCode()

However:

a.hashCode() == b.hashCode()
              |
              +-- DOES NOT imply a.equals(b)
~~~

### 4.1. Why Does Java Need This Dual Contract?

Hash-based collections use the hash code to distribute/locate candidates in the data structure and use equality to distinguish keys accurately. If two keys are considered equal yet have different hash codes, a lookup may go to the wrong bucket and return "not found" even though the domain says "same key".

On the other hand, **two unequal keys can have the same hash code**. The collection must check `equals` when necessary to still distinguish between them.

### 4.2. A Hash Code Is Not a Unique Identifier

`hashCode()` returns a 32-bit `int`; the number of possible objects or value combinations can exceed the number of possible hash codes. Collisions are theoretically unavoidable whenever the value domain is larger than the 32-bit range.

Therefore:

- Do not write `if (a.hashCode() == b.hashCode()) return true;` as a substitute for `equals`.
- Do not use a hash code as a primary key in a database.
- Do not assume `System.identityHashCode` guarantees uniqueness.
- Do not store a hash code as a safety/security verification signature; hashCode is not a cryptographic hash.

## 5. Correct Implementation for an Immutable Value Object

Suppose `StudentKey` is identified by `schoolId` and `studentNumber`. Two different references describing the same pair of values are equal.

With a **`final` class**, we can use `instanceof StudentKey` safely with respect to subtype design because the class cannot be subclassed.

### 5.1. Complete Program

Save **`ValueEqualityDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ValueEqualityDemo {
    static final class StudentKey {
        private final String schoolId;
        private final int studentNumber;

        StudentKey(String schoolId, int studentNumber) {
            this.schoolId = Objects.requireNonNull(
                    schoolId, "schoolId");
            this.studentNumber = studentNumber;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof StudentKey that)) {
                return false;
            }
            return studentNumber == that.studentNumber
                    && schoolId.equals(that.schoolId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(schoolId, studentNumber);
        }
    }

    public static void main(String[] args) {
        StudentKey a = new StudentKey("S-1", 7);
        StudentKey b = new StudentKey("S-1", 7);
        StudentKey c = new StudentKey("S-1", 8);

        System.out.println("same reference=" + (a == b));
        System.out.println("a equals b=" + a.equals(b));
        System.out.println("b equals a=" + b.equals(a));
        System.out.println("a equals c=" + a.equals(c));
        System.out.println("a equals null=" + a.equals(null));
        System.out.println("equal hashes=" +
                (a.hashCode() == b.hashCode()));

        Set<StudentKey> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(c);

        System.out.println("set size=" + set.size());
        System.out.println("contains equal key=" +
                set.contains(new StudentKey("S-1", 7)));
    }
}
~~~

Run:

~~~bash
javac ValueEqualityDemo.java
java ValueEqualityDemo
~~~

**Output:**

~~~text
same reference=false
a equals b=true
b equals a=true
a equals c=false
a equals null=false
equal hashes=true
set size=2
contains equal key=true
~~~

**Why is this implementation correct?**

- `StudentKey` is declared `final`, preventing subclasses from adding state and breaking the equality contract.
- The fields `schoolId` and `studentNumber` are private final; `String` is immutable.
- `this == other` is a valid optimization: the same reference is guaranteed to be equal in this design.
- The `instanceof StudentKey that` pattern both checks the type and binds the reference with the right type; null does not match.
- The `equals` logic compares **both fields** in the criteria.
- `hashCode` uses **the exact same two fields** that participate in equality.
- Two keys with the same values have the same hash per the contract; `HashSet` stores only one representative for the equal group.
- It does not rely on iteration order or specific hash values.

### 5.2. When to Use `Objects.equals`?

If a field can be null:

~~~java
return age == that.age
        && Objects.equals(nickname, that.nickname);
~~~

`Objects.equals(a,b)` handles null conveniently: two nulls return true, one null returns false, and two non-nulls use `a.equals(b)`.

If the constructor has already used `Objects.requireNonNull(name)` and the field is always non-null, writing `name.equals(that.name)` is reasonable, as long as the invariant is genuinely upheld.

### 5.3. Why Must the Signature Be `equals(Object)`?

Standard override:

~~~java
@Override
public boolean equals(Object other) {
    // ...
}
~~~

**Do not** write this instead:

~~~java
public boolean equals(StudentKey other) {
    // ...
}
~~~

because this is only an **overload** with a subtype parameter, not an override of `Object.equals(Object)`. Collections typically work with the `equals(Object)` API, so an overload does not fix the inherited identity-based equality.

`@Override` helps the compiler catch a wrong signature. Do not reduce access visibility to protected/private when overriding a public method of Object.

## 6. How Can `hashCode` Be Implemented?

Common options:

~~~java
@Override
public int hashCode() {
    return Objects.hash(schoolId, studentNumber);
}
~~~

`Objects.hash(Object...)` generates a hash based on the arguments by using the hashing mechanism for a sequence of values (which may involve boxing and varargs allocation). For small value objects, this style is easy to read.

A manual computation option:

~~~java
@Override
public int hashCode() {
    int result = schoolId.hashCode();
    result = 31 * result + Integer.hashCode(studentNumber);
    return result;
}
~~~

The formula combining with 31 is a common convention, **not required** by the Java contract. Both can be correct if:

- They are based on the **same data** that determines `equals`.
- They return a consistent `int` when the data does not change.
- They do not use randomness, timestamps, or identity if pure value equality requires consistent hashes.

### 6.1. Must Every Field Be Included in `hashCode`?

No, but the chosen fields must ensure that **if objects are equal, their hashes are equal**. `hashCode() { return 1; }` satisfies the contract logically, but hash collection performance is usually very poor due to collisions.

In practice, you should use the equality-relevant fields for good distribution. **Do not include an unrelated mutable field** in the hash if `equals` does not consider that field, because equal objects could carry different values in that extra field and produce different hashes — violating the contract.

### 6.2. Can the Hash Code Be Cached?

For immutable value objects, caching the hash can make sense if the computation is expensive and called frequently. However, you must properly handle both thread safety/publication and the value 0 (if 0 is used as a sentinel), avoiding races over incomplete data.

For mutable objects participating in equality, a cached hash easily becomes a **stale hash** after mutation; do not cache it unless invalidation and the contract are clearly managed.

## 7. Consequences When `equals` Is Right but `hashCode` Is Wrong

Suppose a class defines equality by `id`, but computes its hash from another field `slot` that does **not** participate in `equals`. Two objects with the same id and different slots will be equal yet have different hash codes.

This is a **contract violation**, not an ordinary collision.

### 7.1. Program Intentionally Violating the Contract

Save **`BrokenHashContractDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class BrokenHashContractDemo {
    static final class BrokenKey {
        private final int id;
        private final int slot;

        BrokenKey(int id, int slot) {
            this.id = id;
            this.slot = slot;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BrokenKey key
                    && id == key.id;
        }

        @Override
        public int hashCode() {
            return slot; // WRONG: slot is not part of equals.
        }
    }

    public static void main(String[] args) {
        BrokenKey a = new BrokenKey(7, 1);
        BrokenKey b = new BrokenKey(7, 2);

        System.out.println("equals=" + a.equals(b));
        System.out.println("hashes equal=" +
                (a.hashCode() == b.hashCode()));

        Set<BrokenKey> set = new HashSet<>();
        set.add(a);
        System.out.println("contains b=" + set.contains(b));
        set.add(b);
        System.out.println("set size=" + set.size());

        Map<BrokenKey, String> map = new HashMap<>();
        map.put(a, "found");
        System.out.println("lookup b=" + map.get(b));
    }
}
~~~

Compile and run:

~~~bash
javac BrokenHashContractDemo.java
java BrokenHashContractDemo
~~~

**Output on common JDK 17 according to the `HashMap` implementation:**

~~~text
equals=true
hashes equal=false
contains b=false
set size=2
lookup b=null
~~~

Analysis:

- `a.equals(b)` is true because both ids are 7.
- `a.hashCode()==1`, `b.hashCode()==2`, even though equality says they are equal.
- With JDK 17's hashing, these two hash values are distributed differently, so the set fails to find b via entry a and accepts both.
- The map stored a, yet `map.get(b)` fails to locate the same entry in this case.
- **The root bug is in the BrokenKey class**, not in `HashSet` or `HashMap`. When a key violates the contract, do not expect collections to produce results that are "correct according to equals" in every situation.

This is an **intentional anti-example**; do not reuse this design in production.

### 7.2. Proper Fix

If identity is based on `id`, write:

~~~java
@Override
public int hashCode() {
    return Integer.hashCode(id);
}
~~~

Or if `slot` also belongs to the meaning of equality, add it to **both `equals` and `hashCode`**. Decide on the domain semantics first, then align both methods to the same definition.

## 8. Valid Collisions: Equal Hashes but Different Objects

Some learners mistakenly conclude that "two objects with the same hash are equal." That is **not true**.

### 8.1. Program with Intentional Collisions but a Valid Contract

Save **`HashCollisionDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class HashCollisionDemo {
    static final class Key {
        private final String id;

        Key(String id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Key key
                    && java.util.Objects.equals(id, key.id);
        }

        @Override
        public int hashCode() {
            return 1; // Satisfies the contract, but distribution is very poor.
        }
    }

    public static void main(String[] args) {
        Key a = new Key("A");
        Key b = new Key("B");
        Key equalA = new Key("A");

        System.out.println("a equals b=" + a.equals(b));
        System.out.println("a equals equalA=" + a.equals(equalA));
        System.out.println("a and b hashes equal=" +
                (a.hashCode() == b.hashCode()));

        Set<Key> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(equalA);
        System.out.println("set size=" + set.size());

        Map<Key, String> map = new HashMap<>();
        map.put(a, "first");
        map.put(b, "second");

        System.out.println("map A=" + map.get(equalA));
        System.out.println("map B=" + map.get(b));
    }
}
~~~

Run:

~~~bash
javac HashCollisionDemo.java
java HashCollisionDemo
~~~

Output:

~~~text
a equals b=false
a equals equalA=true
a and b hashes equal=true
set size=2
map A=first
map B=second
~~~

**Conclusion:**

- `a` and `b` have different ids, so `equals` is false even though both hashes are 1.
- `a` and `equalA` have the same id, so they are equal and have equal hashes.
- `HashSet` still stores the two key groups A and B separately.
- `HashMap` still retrieves the correct values by equality despite the collision.
- A constant hash does not break the contract, but it causes hash collections to lose their distribution advantage; a sufficiently well-distributed hash is needed when data is large.

Do not use a collision to conclude that `hashCode` "does not matter". Collisions are **allowed**; violating equal→same-hash is the serious bug.

## 9. How Do `HashMap` and `HashSet` Use Equality?

At a conceptual level:

1. On `put`/`add`, the collection obtains the hash code of the key/element.
2. Based on the current hashing structure, it determines the candidate bucket/region.
3. When necessary, the collection uses equality to determine whether an equivalent key/element already exists.
4. On `get`/`contains`/`remove`, the lookup key must still have compatible hash/equality to locate the right entry.

**Do not hardcode assumptions in your algorithms that HashMap always uses a specific bucket count, threshold, or iteration order** across all Java implementations. The API contract matters more than runtime optimization details.

### 9.1. What Mechanism Does HashSet Use?

`HashSet` is a hash-based set; its elements are unique according to its equality contract. It does not provide a reliable iteration order as part of its contract.

`LinkedHashSet` provides iteration order under its own contract, and `TreeSet` relies on ordering/comparator rather than hashing for its notion of duplicate elements. Thus, TreeSet's equality is determined by comparison in the corresponding set operations; you need to ensure ordering is consistent with equals if you want both collections to agree on what "duplicate" means.

### 9.2. HashMap `null` Key

`HashMap` allows one `null` key per its API (and multiple null values), unlike some other implementations such as `Hashtable` or `ConcurrentHashMap` regarding null policy. No instance method is invoked on null to obtain a hashCode in the Java source-level sense; the collection handles that case according to its contract.

Do not write `key.hashCode()` yourself before `put` if the API allows nullable keys and you have not handled null.

## 10. Mutable Hash Key: When Contract Methods Are Right but *Usage* Is Wrong

The two methods `equals/hashCode` can be consistent with the **current state**, yet the key is still unsafe for `HashMap` if the state is modified after `put`. A hash collection does not track setters and does not automatically reindex entries according to new hash values.

~~~java
record StableKey(int id) {}
~~~

This is a valid record with a primitive immutable component; it avoids the bug of **changing a field used for comparison after insertion**. `final` on a reference variable does not have an equivalent effect: `final MutableKey key` still allows a setter to change the state inside the object.

| When designing a key | Outcome to ensure |
| --- | --- |
| Key based on an immutable value | Hash and equality-relevant state do not change while stored |
| Key based on an ID assigned after insertion | Risk of hash/equality changing; separate the lifecycle or assign the ID beforehand |
| Key modified while inside a Map | Do not rely on stable lookup/remove; manage remove-before-change/reinsert with synchronization if needed |
| Mutable object is only a **value** in a Map | Mutation does not change the key's hash bucket, though other state/concurrency risks exist |

The key point here is that **the comparison contract and the collection usage contract are two different layers**. The next lesson on mutable fields uses HashSet/HashMap scenarios, including the case where the hash has not changed but equality has, to clarify the consequences, fix strategies, and implementation caveats.

## 11. `getClass()` or `instanceof` in `equals`?

Two common type-checking approaches:

**Approach A — `instanceof`:**

~~~java
if (!(other instanceof Point point)) {
    return false;
}
~~~

Typically allows subclasses of Point to match. If a subclass adds state that participates in equality, a risk of **asymmetry** arises when the superclass and subclass define different criteria.

**Approach B — checking exact runtime class:**

~~~java
if (other == null || getClass() != other.getClass()) {
    return false;
}
~~~

Two objects of different subclasses will not be equal, even if they share common fields. This approach is generally easier to keep symmetric if the class hierarchy requires equality only within the exact class.

**There is no mechanical choice that is right for every domain.** What matters is the subtype equality contract and class extensibility.

### 11.1. If the Class Is `final`

With `final class Value`, there can be no valid subclasses; `instanceof Value` is sufficient to confirm the right non-null object type, significantly reducing complexity.

Immutable final value classes or Java records are generally safe choices for value semantics when subclassing is not needed.

### 11.2. If the Class Can Be Subclassed

Consider:

- Does the subclass have new fields **participating in equality**?
- Does the parent allow cross-type equality?
- How are symmetry and transitivity preserved?
- Is a sealed hierarchy or shared identity semantics needed?
- Can inheritance be avoided for value types in favor of composition?

A `canEqual` convention can support complex inheritance designs, but it must be implemented with full understanding and tested thoroughly. Another simpler approach is to use exact-class equality or forbid subclassing of the value class.

## 12. Incorrect Example: Symmetry Violation Due to Inheritance

Save **`BrokenSymmetryDemo.java`**:

~~~java
public class BrokenSymmetryDemo {
    static class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Point point
                    && x == point.x && y == point.y;
        }

        @Override
        public int hashCode() {
            return java.util.Objects.hash(x, y);
        }
    }

    static final class ColorPoint extends Point {
        private final String color;

        ColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof ColorPoint point
                    && super.equals(point)
                    && java.util.Objects.equals(color, point.color);
        }

        @Override
        public int hashCode() {
            return java.util.Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        Point base = new Point(1, 2);
        ColorPoint colored = new ColorPoint(1, 2, "red");

        System.out.println("base equals colored=" +
                base.equals(colored));
        System.out.println("colored equals base=" +
                colored.equals(base));
    }
}
~~~

Compile and run:

~~~bash
javac BrokenSymmetryDemo.java
java BrokenSymmetryDemo
~~~

Output:

~~~text
base equals colored=true
colored equals base=false
~~~

**Why is this wrong?**

- `Point.equals` uses `instanceof Point`, so a ColorPoint also matches if the coordinates are equal.
- `ColorPoint.equals` uses `instanceof ColorPoint`, rejecting a plain Point.
- `base.equals(colored)` is true while `colored.equals(base)` is false → **symmetry violation**.
- The two classes also risk violating equal→same-hash because base and colored can have different hashes, making the situation worse.

**It is not recommended** to fix this by arbitrarily removing the color comparison in the subclass if color genuinely matters to the domain. Unify the equality contract at the type hierarchy design level.

## 13. A Clear Option: Equality Only Within the Same Concrete Class

Save **`ExactClassEqualityDemo.java`**:

~~~java
public class ExactClassEqualityDemo {
    static class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (other == null || getClass() != other.getClass()) {
                return false;
            }
            Point point = (Point) other;
            return x == point.x && y == point.y;
        }

        @Override
        public int hashCode() {
            return java.util.Objects.hash(getClass(), x, y);
        }
    }

    static final class ColorPoint extends Point {
        private final String color;

        ColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            return super.equals(other)
                    && java.util.Objects.equals(
                            color, ((ColorPoint) other).color);
        }

        @Override
        public int hashCode() {
            return java.util.Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        Point p = new Point(1, 2);
        ColorPoint red = new ColorPoint(1, 2, "red");
        ColorPoint anotherRed = new ColorPoint(1, 2, "red");

        System.out.println("p equals red=" + p.equals(red));
        System.out.println("red equals p=" + red.equals(p));
        System.out.println("two red=" + red.equals(anotherRed));
        System.out.println("red hash equal=" +
                (red.hashCode() == anotherRed.hashCode()));
    }
}
~~~

Run:

~~~bash
javac ExactClassEqualityDemo.java
java ExactClassEqualityDemo
~~~

Stdout:

~~~text
p equals red=false
red equals p=false
two red=true
red hash equal=true
~~~

**Explanation:**

- `getClass()` prevents equality between a plain Point and a ColorPoint, preserving symmetry in this example.
- When `ColorPoint.equals(other)` executes, `super.equals(other)` is true only for an object whose **exact runtime class is ColorPoint**, so the subsequent cast is safe in this branch.
- ColorPoint adds `color` to equality and hash.
- This approach is only **one design option**: it states that two different subtypes are not equal, even if their shared fields match. Use it when that is what the domain wants.
- If the superclass is dynamically proxied/subclassed by a framework, an exact-class check can affect equality; you must consider the specific framework and domain identity, as there is no single solution for all ORM proxies.

### 13.1. Should Subclasses Be Allowed to Change the Meaning of Equality?

When you want extensions not to alter the equality contract, it is usually best to design the value object as **final**, or keep an immutable stable identity controlled by the superclass and explicitly stipulate that subclasses do not change equality semantics.

For complex entity hierarchies, consider composition, sealed types, or identifiers rather than competing `equals` overrides.

## 14. Null Fields and `Objects.equals`

Nullable fields need to be compared safely:

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof Contact that)) {
        return false;
    }
    return java.util.Objects.equals(nickname, that.nickname)
            && java.util.Objects.equals(email, that.email);
}

@Override
public int hashCode() {
    return java.util.Objects.hash(nickname, email);
}
~~~

This is a **method snippet** of a `Contact` class with corresponding `nickname`/`email` fields, not a standalone Java file.

`Objects.equals(null, null)` returns true; `Objects.equals(null, "A")` returns false; two non-null objects are compared using `equals` on the first object.

**Do not** write `nickname.equals(that.nickname)` if `nickname` can be null, unless you have already checked it. Null must not cause an unintended NPE in `equals(Object)`.

### 14.1. Comparison Order Can Optimize Without Changing Semantics

With multiple fields, you can compare cheap primitive/stable values first, followed by collections/strings if desired. However, if a field comparison has side effects or depends on time, the equality contract itself is already hard to maintain.

`equals` should be an observably **pure** operation: do not mutate objects, perform unexpected I/O, or alter state participating in equality.

## 15. Arrays: `Object.equals` and `Arrays.equals` Are Not the Same

Java arrays are objects. A regular array **does not override `Object.equals` to compare element by element**.

~~~java
int[] a = {1, 2, 3};
int[] b = {1, 2, 3};
~~~

`a.equals(b)` is false because they are two different array instances, even though their contents are identical.

To compare array contents:

- `Arrays.equals(int[], int[])` for one-dimensional primitive arrays.
- `Arrays.equals(Object[], Object[])` for one-dimensional object arrays, using element equality.
- `Arrays.deepEquals(Object[], Object[])` for nested object arrays needing deep content comparison according to API semantics.
- `Arrays.hashCode(...)` or `Arrays.deepHashCode(...)` respectively to compute a consistent hash.

### 15.1. Why Is Using `Objects.hash(array)` Easy to Get Wrong?

`Objects.hash(Object...)` uses varargs. If you pass an array reference, how the compiler constructs the arguments may differ from your intention and the array type; never **assume Objects.hash(array) is by default a content hash for every array**.

The safe rule when class equality relies on `int[]` contents: use **`Arrays.equals` and `Arrays.hashCode`** together. For multi-dimensional/nested arrays, use the pair of deep methods when appropriate.

## 16. Program: Arrays and Defensive Copying

Save **`ArrayEqualityDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayEqualityDemo {
    record RawRecord(int[] values) {
    }

    static final class IntArrayKey {
        private final int[] values;

        IntArrayKey(int[] input) {
            values = input.clone();
        }

        int[] values() {
            return values.clone();
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof IntArrayKey key
                    && Arrays.equals(values, key.values);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2};
        int[] b = {1, 2};

        System.out.println("array equals=" + a.equals(b));
        System.out.println("content equals=" + Arrays.equals(a, b));

        RawRecord r1 = new RawRecord(a);
        RawRecord r2 = new RawRecord(b);
        System.out.println("record arrays equal=" + r1.equals(r2));

        IntArrayKey k1 = new IntArrayKey(a);
        IntArrayKey k2 = new IntArrayKey(b);

        System.out.println("keys equal=" + k1.equals(k2));
        System.out.println("key hashes equal=" +
                (k1.hashCode() == k2.hashCode()));

        a[0] = 9;
        int[] escaped = k1.values();
        escaped[1] = 8;

        System.out.println("stored first=" + k1.values()[0]);
        System.out.println("stored second=" + k1.values()[1]);
    }
}
~~~

Run:

~~~bash
javac ArrayEqualityDemo.java
java ArrayEqualityDemo
~~~

Output:

~~~text
array equals=false
content equals=true
record arrays equal=false
keys equal=true
key hashes equal=true
stored first=1
stored second=2
~~~

**Explanation:**

- `a.equals(b)` compares the identity of the two arrays.
- `Arrays.equals(a,b)` compares the contents of the two primitive arrays.
- `RawRecord` generates `equals` by default based on component values, but an array-typed component is compared **by identity**, not deep array contents.
- `IntArrayKey` uses content equality and a content hash code.
- The constructor **clones the input array**, and the accessor also **clones the output**, so a caller modifying `a` or `escaped` does not mutate the key's internal array/hashing state.
- From the perspective of hash collections, this is a stable value key provided the internal array is not exposed elsewhere.

**Do not conclude that every record is deeply immutable just because its components are final.** With mutable array/list components, the generated accessor can expose a mutable reference; design defensive copies when needed.

## 17. Nested Arrays and `deepEquals`/`deepHashCode`

With nested arrays:

~~~java
int[][] a = {{1, 2}, {3}};
int[][] b = {{1, 2}, {3}};
~~~

`Arrays.equals(a,b)` uses element equality for each outer element. Each element is an `int[]` object, so it still compares identity unless deep semantics are used. To compare nested values, `Arrays.deepEquals(Object[],Object[])` can be applied to `int[][]` because it is an array containing `int[]` objects.

### 17.1. Nested Arrays Demo

Save **`DeepArrayEqualityDemo.java`**:

~~~java
import java.util.Arrays;

public class DeepArrayEqualityDemo {
    public static void main(String[] args) {
        int[][] first = {{1, 2}, {3}};
        int[][] second = {{1, 2}, {3}};

        System.out.println("shallow=" +
                Arrays.equals(first, second));
        System.out.println("deep=" +
                Arrays.deepEquals(first, second));
        System.out.println("deep hash equal=" +
                (Arrays.deepHashCode(first) ==
                        Arrays.deepHashCode(second)));
    }
}
~~~

Compile and run:

~~~bash
javac DeepArrayEqualityDemo.java
java DeepArrayEqualityDemo
~~~

Output:

~~~text
shallow=false
deep=true
deep hash equal=true
~~~

**Warning:** the `Arrays.deep...` methods should not be treated as a general-purpose tool for handling every **cyclic array graph**. With nested reference arrays containing cycles, recursive deep equality/hashing may fail to terminate or overflow under the API conditions. If the domain allows graphs with cycles, design traversal and equality with proper visited/identity tracking instead of blindly deep hashing.

## 18. Records Automatically Generate `equals`, `hashCode`, and `toString`

Java 17 has stable **record classes**. A simple record:

~~~java
record StudentKey(String schoolId, int studentNumber) {
}
~~~

automatically provides constructor/accessors and implements `equals`/`hashCode`/`toString` based on the **record components**.

### 18.1. When Is a Record a Good Choice?

If an object represents **a value tuple** whose components participate in equality, records reduce boilerplate, improve consistency, and make clear that data is the core.

However:

- If a record has a `List<X>` or array reference component, shallow immutability remains an issue.
- If you want to normalize data such as lowercasing an email, it must be done in a valid constructor.
- Do not replace every entity with a record if the entity has its own identity/lifecycle that does not match all components.
- Generated equality distinguishes the record type and components according to record semantics; it is not necessarily suitable for every domain equivalence that needs to ignore certain fields.

### 18.2. Immutable Record Key Program

Save **`RecordEqualityDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class RecordEqualityDemo {
    record EmailKey(String email) {
        EmailKey {
            Objects.requireNonNull(email, "email");
            email = email.trim().toLowerCase(Locale.ROOT);
            if (email.isEmpty()) {
                throw new IllegalArgumentException("empty email");
            }
        }
    }

    public static void main(String[] args) {
        EmailKey first = new EmailKey("  LAN@EXAMPLE.COM ");
        EmailKey second = new EmailKey("lan@example.com");
        EmailKey third = new EmailKey("minh@example.com");

        System.out.println("first=" + first.email());
        System.out.println("first equals second=" +
                first.equals(second));
        System.out.println("hashes equal=" +
                (first.hashCode() == second.hashCode()));

        Set<EmailKey> set = new HashSet<>();
        set.add(first);
        set.add(second);
        set.add(third);
        System.out.println("set size=" + set.size());
    }
}
~~~

Run:

~~~bash
javac RecordEqualityDemo.java
java RecordEqualityDemo
~~~

Output:

~~~text
first=lan@example.com
first equals second=true
hashes equal=true
set size=2
~~~

**Note on email normalization:** lowercasing the entire email here is only an **assumed rule for the example**. In a real mail system, equivalence criteria may depend on the local-part, domain, internationalization, and product policy. Do not use this simple normalization as a universal email validation specification.

## 19. `String`, Wrappers, Enums, and `BigDecimal`

Java library classes define equality according to their own contracts:

- `String.equals`: compares character contents case-sensitively.
- `Integer.equals`, `Long.equals`: compare values of the respective same wrapper type; `Integer.valueOf(7).equals(Long.valueOf(7))` is false because the wrapper classes differ.
- `Enum.equals`: enum instances have identity semantics per singleton enum constants; comparing enum values with `==` is usually correct and readable.
- `BigDecimal.equals`: considers both **numeric value and scale** per its contract; `compareTo` may treat values with different scales as numerically equivalent.

### 19.1. BigDecimal: `equals` Differs from `compareTo()==0`

~~~java
new java.math.BigDecimal("2.0")
        .equals(new java.math.BigDecimal("2.00"))
~~~

returns `false`, because the scales differ. However, `compareTo(...)` returns `0` because they are equal under **numeric ordering**.

This is not a bug in the `equals` contract. It is `BigDecimal`'s design decision regarding equality and ordering, which must be understood when using `HashSet` vs `TreeSet`.

### 19.2. Clear Program

Save **`BigDecimalEqualityDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("equals=" + a.equals(b));
        System.out.println("compareTo=" + a.compareTo(b));
        System.out.println("hash equal=" +
                (a.hashCode() == b.hashCode()));

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(b);

        Set<BigDecimal> treeSet = new TreeSet<>();
        treeSet.add(a);
        treeSet.add(b);

        System.out.println("HashSet size=" + hashSet.size());
        System.out.println("TreeSet size=" + treeSet.size());
    }
}
~~~

Compile and run:

~~~bash
javac BigDecimalEqualityDemo.java
java BigDecimalEqualityDemo
~~~

Stdout:

~~~text
equals=false
compareTo=0
hash equal=false
HashSet size=2
TreeSet size=1
~~~

**Interpretation:**

- `equals` distinguishes scale.
- `compareTo` evaluates numeric ordering to 0.
- `HashSet` treats the two keys as distinct.
- `TreeSet` with natural ordering uses comparison returning 0 to identify equivalent elements, so it keeps only one.
- When business logic requires comparing monetary amounts regardless of scale, **normalize to a canonical representation/form** or define a consistent value type/Comparator; do not try to force BigDecimal to alter its contract.

### 19.3. Ordering "Consistent with Equals"

A comparator or natural order is said to be *consistent with equals* when comparing to 0 corresponds to equality for objects. If inconsistent, sorted collections may differ from hash collections in what they consider duplicate elements.

Think carefully when using `TreeSet`/`TreeMap` with `BigDecimal` or a comparator that compares only one field while ignoring fields that distinguish domain identity.

## 20. Floating Point: `NaN`, `+0.0`, and `-0.0`

With primitives, `Double.NaN == Double.NaN` is false according to the floating-point equality operator. However, the `Double.equals` wrapper and the value semantics of records with double components follow a contract that treats corresponding NaN bit patterns as equal; `+0.0` and `-0.0` are distinguished under wrapper equality.

### 20.1. Comparison Program

Save **`FloatingEqualityDemo.java`**:

~~~java
public class FloatingEqualityDemo {
    record Measure(double value) {
    }

    public static void main(String[] args) {
        double nan = Double.NaN;

        System.out.println("primitive NaN==" + (nan == nan));
        System.out.println("Double NaN equals=" +
                Double.valueOf(nan).equals(Double.valueOf(nan)));

        Measure a = new Measure(Double.NaN);
        Measure b = new Measure(Double.NaN);
        Measure plus = new Measure(+0.0);
        Measure minus = new Measure(-0.0);

        System.out.println("record NaN equal=" + a.equals(b));
        System.out.println("record NaN hashes equal=" +
                (a.hashCode() == b.hashCode()));
        System.out.println("primitive zero equal=" +
                (+0.0 == -0.0));
        System.out.println("record zeros equal=" +
                plus.equals(minus));
    }
}
~~~

Run:

~~~bash
javac FloatingEqualityDemo.java
java FloatingEqualityDemo
~~~

Output:

~~~text
primitive NaN==false
Double NaN equals=true
record NaN equal=true
record NaN hashes equal=true
primitive zero equal=true
record zeros equal=false
~~~

**Why does this matter?**

If you write `equals` manually using `value == that.value` for a double field, it can cause an object containing NaN to **not equal itself** without an identity shortcut — violating reflexivity. `+0.0`/`-0.0` can be treated as equal under primitive `==` while producing different hashes if the hash is based on `Double.hashCode` — risking a violation of equal→same-hash.

For floating-point fields, use a consistent strategy, such as `Double.compare(a,b)==0` combined with `Double.hashCode(value)` if that is the desired equality semantics; test both NaN and signed zeros.

**Do not carelessly use a tolerance like `Math.abs(a-b)<epsilon` to define `equals`.** Approximate comparisons can break transitivity and are unsuitable as an equivalence relation in hash collections.

## 21. Why Can Approximate Comparison with Epsilon Break Transitivity?

An anti-pattern:

~~~java
boolean approximatelyEqual(double a, double b) {
    return Math.abs(a - b) < 0.2;
}
~~~

This is a method snippet used when comparing approximate measurements, **not a safe `equals` implementation**. Choose:

~~~text
a = 0.0
b = 0.15
c = 0.30

|a-b| = 0.15 < 0.2  => a ~ b
|b-c| = 0.15 < 0.2  => b ~ c
|a-c| = 0.30 >= 0.2 => a !~ c
~~~

Transitivity is violated. This does not prohibit you from using *approximate numeric comparison* in calculations, but **do not turn it into `Object.equals`** for a key if you cannot prove the equivalence contract.

If you need to categorize measurements into buckets, choose a normalization/quantization rule that forms **stable buckets**, then compare the buckets with transitive equality, while clearly understanding the business error margin.

## 22. `Objects.hash` and Nested Object Graphs

`Objects.hash(field1, field2, ...)` helps combine hashes, but it does not automatically perform deep hashing on any object graph.

If a field is a `List<String>`, `List.equals` per its API compares element contents in order; `List.hashCode` is defined to be compatible with content equality. If a field is a custom class that has not overridden equals/hashCode, `Objects.hash` will use identity-based semantics for that field.

If a field is a mutable collection, content equality and the hash can **change when the collection changes**. Therefore, a key intended to be stable should use an **immutable snapshot**, such as `List.copyOf(input)` combined with immutable element types.

### 22.1. Cycles in Object Graphs Must Be Handled

If object A holds B and B holds A, manually writing:

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hash(other);
}
~~~

for **both A and B** causes hashing to traverse references back and forth in potentially infinite recursion and trigger a `StackOverflowError`. `equals` carries a similar risk when recursively traversing all neighbors.

Solutions depend on the domain:

- Compare/hash by a **stable identity ID** instead of the entire graph.
- Compare immutable value components that cannot form cycles.
- For true graph equality, design an appropriate visited-pair/memoization algorithm and define equivalence strictly.
- Avoid auto-generating `equals`/`hashCode` from all bidirectional associations of entities in an ORM.

## 23. Entity Identity, Generated IDs, and Lifecycle

An entity typically has mutable state: `status`, `address`, `updatedAt`. If you include these fields in `equals`/`hashCode` and place the entity in a HashSet before mutation, the collection can suffer broken lookups.

For database-backed entities, a common choice is to use a **stable business key** or an **ID already assigned before the object is used as a hash key**. However, you must handle the case where the ID does not yet exist:

- Two transient entities both having a null id does **not** automatically mean they are equal.
- If the ID is assigned after persisting, an ID-based hash can change while the entity is inside a HashSet.
- ORM proxies can cause `getClass()` and `instanceof` to behave unexpectedly if the hierarchy is enhanced.
- Persistence identity, Java object identity, and business equality **are not always the same concept**.

There is no single equals/hashCode template that works correctly for every JPA/domain entity. Follow the specific framework's guidelines, state lifecycle, and corresponding tests.

### 23.1. For Immutable Value Objects

If an object simply represents a value such as `Coordinates`, `Money`, or `StudentKey`, a Java record or final class with immutable fields is usually easier to get right. When domain identity changes over time, do not pretend it is an immutable value key.

### 23.2. For Caches and Distributed Systems

Java's `hashCode()` is not a stable global key across nodes or processes. Do not use it for cache key serialization or long-lived sharding fingerprints without a separate stable hashing specification. Use a business identifier/serialization format and an explicitly defined hash algorithm when needed.

## 24. The Role of `equals` When Comparing Collections

Java collections define equality by collection type:

- `List.equals`: two lists are equal if their corresponding elements are equal **and in the same order**.
- `Set.equals`: two sets are equal if they contain the same elements per contract, **regardless of iteration order**.
- `Map.equals`: two maps are equal according to their corresponding mappings.
- `Arrays.equals`: one-dimensional by contents (with the appropriate overload); an array instance's `equals` is still identity.
- `Collections.unmodifiableList`: a wrapper that prevents modification through the view, **without** guaranteeing that the backing list is not mutated elsewhere.
- `List.copyOf`: a structurally unmodifiable snapshot, though the elements themselves may still be mutable references.

If you use a mutable collection as a field of a key, consider replacing it with an immutable snapshot/defensive copy; if the elements are mutable, the snapshot list is still not deeply immutable.

### 24.1. List/Set Equality Example Independent of Specific Hash Values

Save **`CollectionEqualityDemo.java`**:

~~~java
import java.util.List;
import java.util.Set;

public class CollectionEqualityDemo {
    public static void main(String[] args) {
        List<String> ab = List.of("A", "B");
        List<String> ba = List.of("B", "A");

        System.out.println("list order matters=" + ab.equals(ba));

        Set<String> first = Set.of("A", "B");
        Set<String> second = Set.of("B", "A");

        System.out.println("set order ignored=" +
                first.equals(second));
        System.out.println("set hashes equal=" +
                (first.hashCode() == second.hashCode()));
    }
}
~~~

Run:

~~~bash
javac CollectionEqualityDemo.java
java CollectionEqualityDemo
~~~

Output:

~~~text
list order matters=false
set order ignored=true
set hashes equal=true
~~~

`Set.of` may iterate in different orders across runs; the example **does not print the collection** and does not rely on that order. It prints only the equality/hash properties guaranteed by Java.

## 25. Where Is `equals` Used in Applications?

Some practical examples:

- `HashSet.contains`: checks whether an equivalent element already exists.
- `HashMap.get`: looks up a value by an equivalent key.
- `List.contains`: uses element equality to search.
- `List.indexOf`: compares elements to find the index/position.
- `Objects.equals(a,b)`: compares safely when one or both are nullable.
- Unit tests such as `assertEquals(expected,actual)`: normally invoke equality according to the framework API; if the class has not overridden it, two separate instances are not equal.
- Domain validation, deduplication, caching, and grouping by keys.

You need to know **the container's semantics**. For example, `IdentityHashMap` uses reference identity semantics rather than HashMap-style logical equality in key operations; it is useful in specialized scenarios such as tracking visited identity in a graph, but should not be used in place of HashMap out of habit.

### 25.1. When Should You Use `==` for References?

`==` is right when the question is **is it the exact same object instance?**

Examples:
- Comparing enum values, because enum constants have suitable identity semantics.
- Confirming aliasing (two variables pointing to the same object).
- Graph traversal needing an identity-based visited set.
- Checking `this == other` as a shortcut before comparing fields in `equals`.

Do not use `==` instead of logical equality for String, BigDecimal, records, or value classes unless identity is truly what you need.

## 26. How `IdentityHashMap` Differs from `HashMap`

`IdentityHashMap` compares keys using `==` and uses identity-based hashing semantics, unlike `HashMap` which relies on `equals`/`hashCode`.

### 26.1. Program Demonstrating the Difference

Save **`IdentityMapDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityMapDemo {
    public static void main(String[] args) {
        String first = new String("A");
        String second = new String("A");

        Map<String, Integer> logical = new HashMap<>();
        Map<String, Integer> identity = new IdentityHashMap<>();

        logical.put(first, 1);
        logical.put(second, 2);

        identity.put(first, 1);
        identity.put(second, 2);

        System.out.println("equals=" + first.equals(second));
        System.out.println("same identity=" + (first == second));
        System.out.println("HashMap size=" + logical.size());
        System.out.println("IdentityHashMap size=" + identity.size());
    }
}
~~~

Run:

~~~bash
javac IdentityMapDemo.java
java IdentityMapDemo
~~~

Output:

~~~text
equals=true
same identity=false
HashMap size=1
IdentityHashMap size=2
~~~

With HashMap, the keys are equal according to String.equals, so the second entry replaces the value. With IdentityHashMap, the two String instances are two distinct keys despite having equal content.

**Do not use IdentityHashMap just to "fix" a key with broken equals/hashCode.** It changes the map's notion of equality; if the business logic requires logical keys, you must fix the key.

## 27. Thread Safety and Stability

Ordinary `equals`/`hashCode` methods are not automatically synchronized. If fields participating in comparison are modified by another thread, two consecutive calls may observe different snapshots or encounter data races/visibility issues.

A safely published immutable value key is generally easier to share across threads than a mutable entity key. However:

- A `final` reference to a mutable collection does not make the collection's contents immutable.
- An `equals` method that invokes getters with side effects or depends on a clock/random source can be inconsistent.
- If an object graph changes concurrently, "comparing field by field sequentially" is not necessarily an atomic snapshot.
- `ConcurrentHashMap` gives map operations appropriate concurrency semantics; **it does not make mutable keys stable**.

In concurrent code, design equality around immutable/stable state, or use synchronization/snapshots suited to your needs.

## 28. Testing the `equals` and `hashCode` Contracts

A test suite should check:

1. **Reflexive:** `a.equals(a)`.
2. **Symmetric:** `a.equals(b) == b.equals(a)` for both equal and unequal pairs.
3. **Transitive:** if a=b and b=c, then a=c.
4. **Consistent:** invoke multiple times while fields remain unchanged.
5. **Non-null:** `!a.equals(null)`.
6. **Equal→same-hash:** if `a.equals(b)`, then their hashes are equal.
7. **Unequal:** test at least one differing field; do not require hashes to differ.
8. **HashSet/HashMap:** add equivalent keys and verify deduplication/lookup.
9. **Edge cases:** null fields, empty strings, arrays, NaN/signed zeros if relevant.
10. **Inheritance:** Parent vs Child and Child vs Parent to catch symmetry issues.
11. **Mutation:** try mutating state/elements/referents to check whether the key remains stable.
12. **Concurrency/lifecycle:** if required by the domain, test stability under realistic conditions.

**Do not assert** that "two unequal objects must have different hashes". This is not a Java requirement, and such a test will fail on completely valid collisions.

### 28.1. Self-Testing Program Without JUnit

Save **`EqualityContractCheckDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class EqualityContractCheckDemo {
    record Key(String code, int number) {
        Key {
            Objects.requireNonNull(code, "code");
        }
    }

    static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        Key a = new Key("A", 1);
        Key b = new Key("A", 1);
        Key c = new Key("A", 1);
        Key different = new Key("A", 2);

        check(a.equals(a), "reflexive");
        check(a.equals(b) && b.equals(a), "symmetric");
        check(a.equals(b) && b.equals(c) && a.equals(c),
                "transitive");
        check(!a.equals(null), "non-null");
        check(!a.equals(different), "different key");

        int hashBefore = a.hashCode();
        check(hashBefore == a.hashCode(), "consistent hash");
        check(a.hashCode() == b.hashCode(), "equal hash");

        Map<Key, String> map = new HashMap<>();
        map.put(a, "found");
        check("found".equals(map.get(b)), "map lookup");
        check("found".equals(map.get(c)), "map lookup third");

        System.out.println("all checks passed");
    }
}
~~~

Compile and run:

~~~bash
javac EqualityContractCheckDemo.java
java EqualityContractCheckDemo
~~~

Output:

~~~text
all checks passed
~~~

Unlike Java's `assert`, which is usually **disabled by default** unless `-ea` is enabled, the `check` method in the example always throws `AssertionError` if the condition is false. Thus, the command `java EqualityContractCheckDemo` verifies everything written without depending on a VM flag.

**This is a sample check** and does not by itself prove the class is correct for all inputs. Add property-based tests or a library such as EqualsVerifier (when the project already has the appropriate dependency), especially for class hierarchies and complex fields.

## 29. Code Review Checklist: Before Overriding

Before merging a class that defines `equals`/`hashCode`, answer:

1. **Is the class a value object or an entity?** What is the domain equality?
2. **Is overriding `Object.equals` necessary?** If identity semantics are already appropriate, overriding is not required.
3. **Does the method have the exact signature `public boolean equals(Object)` and `@Override`?**
4. **Does it handle `other == null` and incompatible types by returning false?**
5. **Does it preserve reflexivity, symmetry, transitivity, and consistency?**
6. **Does inheritance allow subclasses to add equality state?**
7. **Is `instanceof` or `getClass` appropriate for the domain and proxies/frameworks?**
8. **Which fields participate in equality?** Do all of them have a stable contract?
9. **Does `hashCode` use data consistent with `equals`?**
10. **Does it tolerate collisions without causing all keys to collide needlessly?**
11. **Are the fields mutable?** Will the object be used as a hash key after mutation?
12. **Are there nested mutable arrays/lists?** Are Arrays.equals/hashCode/defensive copies needed?
13. **Is there a cyclic reference graph?** Avoid infinite recursive equals/hashCode.
14. **Are there null fields, NaN, signed zeros, or BigDecimal scales?**
15. **Will it be accessed concurrently?** Is state stable/visible?
16. **Are there tests for equal pairs, unequal pairs, symmetry, transitivity, and map/set lookups?**
17. **Is toString needed?** toString is not part of the equality contract, but it should not leak secrets or traverse an infinite graph.
18. **Is there documentation accurately stating the equality semantics for clients?**

## 30. Common Misconceptions

| Misconception | Fact |
| --- | --- |
| "`==` and `equals` both compare contents." | For references, `==` compares identity; `equals` follows its implementation. |
| "Without overriding, `equals` compares all fields." | `Object.equals` compares identity by default. |
| "You only need to override `equals`." | If the new logical equality differs from Object, you normally must override `hashCode` accordingly. |
| "Two equal objects can have different hashes." | No; equal→same-hash is a mandatory requirement. |
| "Two objects with the same hash must be equal." | No; collisions are valid. |
| "A hash code is a memory address." | There is no such API guarantee. |
| "A hash code must be unique." | No; it only has a 32-bit integer range. |
| "Hash codes stay the same across runs." | Not part of the general contract. |
| "`equals(StudentKey)` overrides `Object.equals`." | No; it is an overload with a different signature. |
| "Use `==` to compare String fields." | Use `String.equals`/`Objects.equals` for logical equality. |
| "`instanceof` is always safe when a superclass is extended." | Subclass equality can break symmetry. |
| "`getClass` is always the only right choice." | An exact-class policy must also fit the domain and proxies. |
| "Every `final` field is deeply immutable." | A final reference can still point to a mutable object. |
| "Using a mutable key in a HashMap is no problem." | Changing fields participating in hash/equality can cause lookups to fail. |
| "HashMap automatically rehashes an entry when its key changes." | There is no contract to automatically relocate an entry upon key mutation. |
| "Storing two objects with different identities in a HashSet always yields size 2." | If the objects are equal by value, the set can hold only one. |
| "A record automatically deep-copies arrays." | No; array components need defensive copying if value semantics are desired. |
| "Array.equals compares contents." | Array instance equals uses identity; use Arrays.equals/deepEquals. |
| "List.copyOf deep-copies elements." | No; mutable elements can still be shared. |
| "`BigDecimal.compareTo()==0` is equivalent to equals." | Not for different scales. |
| "TreeSet always shares the same duplicate semantics as HashSet." | A sorted set uses ordering/comparator; it needs to be consistent-with-equals. |
| "Approximate floating-point equality is always valid as Object.equals." | It can break transitivity. |
| "NaN == NaN is true." | For primitive double, it is false. |
| "`+0.0` and `-0.0` make no difference in hashing." | It must be consistent with the double equality strategy. |
| "Objects.hash hashes every collection/array deeply." | No; it depends on the field's equals/hashCode and varargs semantics. |
| "Any chain of bidirectional references can be deep-compared." | It can cause infinite recursion in equals/hashCode. |
| "IdentityHashMap fixes any broken key." | It changes equality semantics to identity rather than fixing the domain key. |
| "`hashCode` is a cryptographic checksum." | It is unsuitable for security or integrity. |
| "A thread-safe map makes mutable keys safe." | You must still keep equality and hash stable. |

## 31. Review Questions with Answers

**Question 1.** Will two `new Box(7)` objects without an overridden equals be equal?  
**Answer:** No. Object.equals defaults to identity.

**Question 2.** If two references `a` and `b` point to the same object, what is `a == b`?  
**Answer:** True, because they share the same reference identity.

**Question 3.** What is `new String("A").equals(new String("A"))`?  
**Answer:** True, because String compares contents.

**Question 4.** Which property requires `a.equals(a)` to hold?  
**Answer:** Reflexivity; true for non-null a.

**Question 5.** `a.equals(b)` being true while `b.equals(a)` is false violates what property?  
**Answer:** Symmetry.

**Question 6.** a=b and b=c yet a≠c violates what property?  
**Answer:** Transitivity.

**Question 7.** What must `a.equals(null)` return if a is non-null?  
**Answer:** False.

**Question 8.** Can `equals` change its result if fields participating in equality are mutated?  
**Answer:** Yes; consistency only requires the same result when information participating in equality does not change. However, avoid using mutable keys in hash collections.

**Question 9.** If `a.equals(b)` is true, what must `a.hashCode()==b.hashCode()` be?  
**Answer:** True.

**Question 10.** If `a.hashCode()==b.hashCode()`, does that imply `a.equals(b)`?  
**Answer:** No, because of collisions.

**Question 11.** Is it valid if every object of a class always returns hash code 1?  
**Answer:** It can satisfy the contract, though it performs very poorly in hash collections.

**Question 12.** Why is overriding only equals while keeping Object.hashCode dangerous?  
**Answer:** Two objects equal by fields can produce different hashes, violating equal→same-hash.

**Question 13.** Does `equals(StudentKey)` override Object.equals?  
**Answer:** No. You must use `equals(Object)` and `@Override`.

**Question 14.** If a HashSet adds two StudentKeys with different identities but identical fields, how many elements will it have if equals/hashCode are correct?  
**Answer:** One representative for the equal group.

**Question 15.** Why does modifying a field participating in the hash after `map.put(key,value)` easily cause lookup failures?  
**Answer:** The collection organized the entry under the previous hash; a lookup using the new hash may fail to find the right entry.

**Question 16.** Is `final List<String> tags` sufficient to prevent a mutable key?  
**Answer:** No. The List object can still be mutated if its reference is exposed.

**Question 17.** What does a `getClass` check do in equals?  
**Answer:** It requires the exact same runtime class, ruling out cross-subtype equality.

**Question 18.** What issue can `instanceof Point` in Point.equals cause when ColorPoint adds color?  
**Answer:** Subclass equality can break symmetry/transitivity or the hash contract.

**Question 19.** When is `Objects.equals(a,b)` useful?  
**Answer:** When fields can be null; it performs null-safe comparison.

**Question 20.** Does `int[].equals(int[])` compare contents?  
**Answer:** No. Array instance equals compares identity.

**Question 21.** What should you use if you want two `int[]` arrays to be equal by contents with a consistent hash?  
**Answer:** `Arrays.equals` together with `Arrays.hashCode`.

**Question 22.** Is a record with an `int[]` component automatically deeply immutable?  
**Answer:** No; input/output copying is needed if you want to prevent aliasing.

**Question 23.** Why might nested arrays require `Arrays.deepEquals`?  
**Answer:** `Arrays.equals` on the outer array uses the equality of the nested array elements (identity) rather than deeply comparing contents.

**Question 24.** Are `BigDecimal("2.0")` and `BigDecimal("2.00")` equal under equals?  
**Answer:** No; their scales differ.

**Question 25.** Do those two BigDecimals have `compareTo()==0`?  
**Answer:** Yes; they have the same numeric value.

**Question 26.** Why can HashSet and TreeSet end up with different sizes for the two BigDecimals above?  
**Answer:** HashSet relies on equals/hashCode; TreeSet uses comparison returning 0.

**Question 27.** What is `Double.NaN == Double.NaN` for primitives?  
**Answer:** False.

**Question 28.** Why must you be careful when using primitive `==` for double fields in equals?  
**Answer:** NaN and signed zeros can break reflexivity or hash compatibility depending on the implementation.

**Question 29.** Is approximate comparison `|a-b|<epsilon` suitable for Object.equals?  
**Answer:** Usually not, because it does not guarantee transitivity.

**Question 30.** If two objects A and B reference each other and equals/hashCode recursively traverses every reference, what can happen?  
**Answer:** Infinite recursion / StackOverflowError; a domain identity or graph-aware algorithm is needed.

**Question 31.** When should IdentityHashMap be used?  
**Answer:** When the primary semantics are object identity, such as in certain graph algorithms; do not use it instead of HashMap for logical value keys.

**Question 32.** What does `Objects.hashCode(null)` return?  
**Answer:** It returns 0 per the API; useful for null-safe hashing.

**Question 33.** Must `Objects.hash(name, age)` use the same field list as equals?  
**Answer:** It must ensure equal objects have equal hashes; usually the same equality-relevant fields are used.

**Question 34.** Should a hash code have a fixed value across program runs?  
**Answer:** Not a general requirement of Object.hashCode; do not use it as a persistent identifier.

**Question 35.** If two objects are not equal yet have the same hash, will HashMap store two separate keys?  
**Answer:** Yes, provided the keys' equals/hashCode contract is valid; collisions are handled according to map semantics.

**Question 36.** What unit tests are especially needed when subclassing and overriding equals?  
**Answer:** Test both `parent.equals(child)` and `child.equals(parent)`, along with transitivity and hash consistency.

## 32. References

- Java Platform API Java SE 17, [`Object.equals(Object)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): reflexive/symmetric/transitive/consistent/non-null contract.
- Java Platform API Java SE 17, [`Object.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()): equal→same hash contract and limitations.
- Java Platform API, [`Objects.equals(Object,Object)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)): null-safe comparison.
- Java Platform API, [`Objects.hash(Object...)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#hash(java.lang.Object...)): computing a hash from multiple arguments.
- Java Platform API, [`HashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): hash-based map and keys.
- Java Platform API, [`HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): hash-based set and uniqueness.
- Java Platform API, [`IdentityHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): reference identity semantics.
- Java Platform API, [`Arrays.equals`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): content equality of arrays.
- Java Platform API, [`Arrays.deepEquals`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#deepEquals(java.lang.Object%5B%5D,java.lang.Object%5B%5D)): nested arrays.
- Java Platform API, [`BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): scale-sensitive equals and compareTo.
- Java Language Specification Java SE 17, [`8.10 — Record Classes`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record equality/hash semantics.
- Java Language Specification, [`15.21 — Equality Operators`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21): `==` for primitives/references.
- Java Platform API, [`Set`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): sets and equality.
- Java Platform API, [`SortedSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html): ordering and consistency with equals.

## Conclusion

`equals(Object)` defines **in what sense two objects are considered equal**. `hashCode()` provides an appropriate hash value for hash-based structures. The most important contract: **if `a.equals(b)` is true, then `a.hashCode() == b.hashCode()` must be true**; equal hashes do **not** prove objects are equal.

A good implementation preserves the five properties of `equals`, compares the right domain fields, handles null and inheritance, uses a consistent hashing strategy, and avoids mutable key state. For arrays, use `Arrays.equals/hashCode` appropriately; for records, keep shallow immutability in mind; for BigDecimal, do not confuse equality with numeric comparison.

When designing a class to be used as a **key in a `HashMap`** or an **element in a `HashSet`**, prefer immutable value objects or records with safe components, and write tests for the reflexive/symmetric/transitive/hash contract and edge cases. Do not use a hash code as a unique identity or expect the GC/JVM to fix mutated keys automatically. **Valid equality is a contract of the type, not the luck of a single comparison.**
