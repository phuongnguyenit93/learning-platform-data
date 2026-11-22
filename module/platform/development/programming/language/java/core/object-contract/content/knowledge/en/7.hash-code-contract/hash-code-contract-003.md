# Equal Hash Codes Do Not Imply `equals()`

## Lesson Objectives

In Java, `hashCode()` and `equals(Object)` work together to determine how objects behave in hash-based structures such as `HashMap` and `HashSet`. However, **two objects having the same hash code are not necessarily equal**. This is the direction of inference that is very easy to reverse when reading the `hashCode` contract.

After this lesson, you will be able to:

- State accurately the **mandatory** direction and the **disallowed** inference between `equals()` and `hashCode()`.
- Explain why hash collisions are a valid phenomenon and not synonymous with a bug.
- Predict the outcome of `String` examples that share a hash code while `equals() == false`.
- Understand why `HashMap`/`HashSet` can still hold two distinct keys or elements even when they have the same `hashCode()`.
- Implement `equals`/`hashCode` consistently, spot bugs in the mandatory direction, and avoid false assumptions about hash uniqueness.

## 1. Two Non-Equivalent Directions of Inference

The `Object.hashCode()` contract specifies: **if two objects are equal according to `equals(Object)`, they must have the same hash code**.

Written as an implication:

```text
a.equals(b) == true
           ↓ required
a.hashCode() == b.hashCode()
```

The reverse direction is **not guaranteed**:

```text
a.hashCode() == b.hashCode()
           ↓ insufficient to conclude
a.equals(b) can be true or false
```

The table below helps distinguish them:

| `a.equals(b)` | `a.hashCode() == b.hashCode()` | Contract |
| --- | --- | --- |
| `true` | `true` | Valid and mandatory |
| `true` | `false` | **Invalid:** violates the `hashCode` contract |
| `false` | `true` | **Valid:** two distinct objects sharing a hash |
| `false` | `false` | Valid |

The common phrasing is **“equal objects must have equal hash codes”**, not “equal hash codes mean equal objects”.

This also means that from `a.hashCode() != b.hashCode()` you can conclude `a.equals(b)` **cannot** be `true` if both classes obey the contract. Even so, in business logic you should still use `equals()` when the actual question is “are these two objects equal or not?”.

Operational note: comparisons and hashes must be evaluated while the objects are in a consistent state under the `equals`/`hashCode` contract, rather than assuming results remain meaningful after mutating fields involved in equality.

## 2. Why Are Hash Collisions Inevitable?

`hashCode()` returns an `int`, which is a 32-bit signed value. Meanwhile, the number of distinct strings, field combinations, and object states can be far greater than the number of available `int` values. Therefore, **it is impossible to assign a unique hash code to every possible value**.

When two different objects produce the same output from a hash function, we call it a **hash collision**. A collision only means that two objects share the same hash code value; it **does not prove** that the two objects have the same contents, the same identity, or the same business meaning.

An intuitive example: imagine a toy hash code that is simply the remainder when dividing a customer number by 10. Customers 21 and 31 both have hash 1, yet they are still two different customers. This is a conceptual example, not the algorithm of `Object.hashCode()` or `HashMap`.

Even when a class uses a high-quality hash function, collisions can still occur. Hash quality primarily affects key distribution and performance, **not the definition of equality** of the object.

## 3. Collisions Are Reproducible with `String`

`String.hashCode()` has a specified algorithm in Java, based on the sequence of UTF-16 code units. Two distinct strings can certainly produce the same hash number. The pair `"FB"` and `"Ea"` is a famous example:

```java
String first = "FB";
String second = "Ea";

System.out.println(first.hashCode());           // 2236
System.out.println(second.hashCode());          // 2236
System.out.println(first.hashCode()
        == second.hashCode());                   // true
System.out.println(first.equals(second));       // false
System.out.println(first == second);            // false
```

This is an illustrative snippet placed inside a Java method, not a standalone program. `String.equals()` checks character contents, so `"FB"` and `"Ea"` are not equal. Meanwhile `==` on two references asks whether they are the same object; these two literals with different contents do not point to the same object. Equal hash results **do not interfere** with those two comparisons.

You can calculate the hash results yourself using `String`'s formula for two characters:

```text
"FB": 'F' = 70, 'B' = 66  → 70 × 31 + 66 = 2236
"Ea": 'E' = 69, 'a' = 97  → 69 × 31 + 97 = 2236
```

Two different character pairs yielding the same result is a valid collision of `String.hashCode()`. You do not need `new String(...)` to construct this example, nor do you need to rely on a JVM environment with special object allocation behavior.

**Key takeaway:** even the hash code of a standard class like `String` cannot be used as a unique identifier or proof that two strings are equal.

## 4. Complete Java 17+ Example: Two Objects with the Same Hash That Are Not `equals`

In the `Customer` class below, both `id` and `name` participate in determining equality. However, `hashCode()` intentionally returns only the hash code of `id` to demonstrate a predictable collision case.

This is a **contract-valid implementation that can have poor hash distribution** if many customers share the same `id`. In real applications, you should generally compute the hash from all fields involved in `equals` to reduce unnecessary collisions.

Save the file as `HashCollisionDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashCollisionDemo {
    static final class Customer {
        private final int id;
        private final String name;

        Customer(int id, String name) {
            this.id = id;
            this.name = name;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Customer other)) {
                return false;
            }
            return id == other.id
                    && Objects.equals(name, other.name);
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Customer a = new Customer(7, "Lan");
        Customer b = new Customer(7, "Mai");
        Customer copyOfA = new Customer(7, "Lan");

        System.out.println("a hash: " + a.hashCode());
        System.out.println("b hash: " + b.hashCode());
        System.out.println("same hash a/b: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("a equals b: " + a.equals(b));
        System.out.println("a equals copy: " + a.equals(copyOfA));
        System.out.println("same hash a/copy: "
                + (a.hashCode() == copyOfA.hashCode()));

        String first = "FB";
        String second = "Ea";
        System.out.println("string hashes: "
                + first.hashCode() + ", " + second.hashCode());
        System.out.println("string equals: " + first.equals(second));

        Set<Customer> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(copyOfA);
        System.out.println("set size: " + set.size());

        Map<Customer, String> map = new HashMap<>();
        map.put(a, "first");
        map.put(b, "second");
        System.out.println("map size: " + map.size());
        System.out.println("lookup by equal key: " + map.get(copyOfA));
        System.out.println("lookup colliding key: " + map.get(b));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac HashCollisionDemo.java
java HashCollisionDemo
```

Exact output:

```text
a hash: 7
b hash: 7
same hash a/b: true
a equals b: false
a equals copy: true
same hash a/copy: true
string hashes: 2236, 2236
string equals: false
set size: 2
map size: 2
lookup by equal key: first
lookup colliding key: second
```

Explanation:

1. `a` and `b` share `id == 7`, so they have the same hash `7`, but their names differ, so `a.equals(b)` is `false`.
2. `a` and `copyOfA` are two separately created objects. Although `a == copyOfA` is `false`, `a.equals(copyOfA)` is `true` because the fields participating in `equals` have the same values; therefore their hashes must be equal.
3. `"FB"` and `"Ea"` have the same hash `2236` but different contents, so `equals()` is `false`.
4. `HashSet` keeps `a` and `b` as two distinct elements. `copyOfA` equals `a`, so it does not create a third element.
5. `HashMap` stores `a` and `b` as two distinct keys. Looking up with `copyOfA` still finds `a`'s value because `copyOfA.equals(a)` is `true` and the hashes match.

The example prints direct lookups rather than iterating over collections, so it does not depend on the iteration order of `HashMap` or `HashSet`.

## 5. How Does `HashMap` Handle Collisions?

You can picture a lookup by `key` in a hash-based structure through these conceptual steps:

1. Obtain the key's hash code; the structure may process the bits further and map to a storage location.
2. Identify where the target entry might reside based on the hash code.
3. If multiple keys land in the same location, the structure must **distinguish the keys** via equality checks, rather than treating every key with the same hash as one key.
4. Return the entry corresponding to the equal key, or conclude there is no matching key.

This is a conceptual diagram, not mandatory internal code of every `HashMap` implementation version:

```text
Key to look up
    │
    ▼
Compute/match hash
    │
    ▼
Identify candidate group
    │
    ▼
Compare keys in group
    │
    ├─ equals == true  → same logical key
    │
    └─ equals == false → different key, even if hash may match
```

More technical note: Java's `HashMap` implementation can also use a **same-reference** check (`==`) to quickly recognize the exact key object before calling `equals()` when needed. Whether buckets are organized as lists or trees is an implementation and performance detail that does not alter the critical rule: **matching hashes alone are not enough to consider two keys equal**.

In the example, two `Customer` objects with hash 7 still coexist in `HashMap` because `a.equals(b) == false`. If the table used hash as the sole proof of equality, the data for `a` and `b` would be wrongly overwritten/merged.

`HashSet` relies on a similar hashing and equality-checking mechanism to determine whether an element already exists. Therefore, two elements with the same hash but `equals() == false` are both added to the set.

## 6. Distinguishing Valid Collisions from Contract Violations

Two reasoning errors are often confused with each other.

### Case A — Valid Collision

```text
a.equals(b) == false
a.hashCode() == b.hashCode()
```

This is **not a bug**. The collection must still distinguish `a` and `b`. A high collision count can affect performance, but by itself it does not prove that `equals()` or `hashCode()` is written incorrectly.

### Case B — Contract Violation

```text
a.equals(b) == true
a.hashCode() != b.hashCode()
```

This is a real implementation bug. When two keys are evaluated as equal but their hash codes do not match, a hash-based structure may look for the key in incompatible places, causing `contains`, `get`, or insertion operations to produce unexpected results.

Design bug example (illustrative snippet inside a class with fields `id` and `name`):

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return id == other.id; // Only id determines equality
}

@Override
public int hashCode() {
    return Objects.hashCode(name); // WRONG: depends on name instead
}
```

The snippet above is not a standalone program. It illustrates a mistake: if two `Customer` objects have the same `id` but different `name` values, `equals()` returns `true` while `hashCode()` can differ. Treat it as a **counterexample**, not code to copy into an application.

In a valid implementation where only `id` determines equality, `hashCode` should be computed from `id`, such as `Integer.hashCode(id)`. When both `id` and `name` determine `equals`, `Objects.hash(id, name)` is a more natural choice than hashing only from `id`.

## 7. What `hashCode()` Actually Requires

Besides the mandatory direction “`equals` equal ⇒ hash equal”, the `hashCode()` contract also requires:

- For the same object, when no information used in `equals` comparisons changes, repeated calls to `hashCode()` during a single execution of the program must return a consistent value. The value is not required to stay the same across separate runs of the application.
- If `a.equals(b) == true`, they must have the same `hashCode()`.
- If `a.equals(b) == false`, distinct hash codes are not required. **Producing more distinct hashes can yield better performance**, but it is not a correctness requirement of the contract.

Therefore, a simple implementation like:

```java
@Override
public int hashCode() {
    return 1;
}
```

can still be **contract-compliant** when paired with a valid and stable `equals()`: every object has the same hash, including equal objects. However, this is almost always a **terrible performance choice** when many distinct objects are placed in `HashMap`/`HashSet` because it creates constant collisions. The purpose of the example is to demonstrate that “different hashes” is not a requirement for unequal objects.

Conversely, a `hashCode()` that varies randomly across calls on the same object no longer obeys the consistency contract and can cause hash collections to misbehave.

## 8. Which Fields Should Be Used in the Implementation?

For a simple value class with immutable fields:

```java
private final int id;
private final String name;

@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return id == other.id && Objects.equals(name, other.name);
}

@Override
public int hashCode() {
    return Objects.hash(id, name);
}
```

These are illustrative members inside a `Customer` class; `Objects` requires `import java.util.Objects` and the `instanceof` pattern uses syntax supported in Java 17.

**Practical rule:** first determine which set of fields participates in `equals()`, then compute the hash from that same significant information. `Objects.hash(id, name)` has the advantage of readability and helps ensure equal objects receive the same hash when field data and their contracts are sound. It **does not promise** that unequal objects will have different hashes; collisions can still happen.

The `equals` and `hashCode` methods do not need to have the same number of comparisons or computations. What matters is that the relationship between their results holds. In the first `Customer` example, `equals` uses both `id` and `name` while `hashCode` uses only `id`, which is still valid because whenever two objects are equal they are guaranteed to share the same `id`. Using fewer fields simply risks increasing collisions.

Do not use `System.identityHashCode(obj)` as a substitute for content-based `hashCode()` in a value class with a custom `equals`: identity hash codes are not designed to ensure that two objects with equal contents have the same hash. Even identity hash codes are not guaranteed to be unique per object.

### Fields Used as Keys Must Be Stable

If an object is used as a `HashMap` key or `HashSet` element, be especially careful with mutable fields that participate in `equals`/`hashCode`.

Suppose a key is added to a `HashSet` while its hash is 7. Then the program mutates data, changing that key's hash to 8; a `contains` call may look in a different group and fail to find the stored element. This is a bug caused by **mutating hash-relevant state after insertion**, not a collision.

Prefer immutable key objects or manage the key lifecycle so that fields determining equality and hash do not change while the key is inside a hash collection.

## 9. Common Misconceptions

1. **“Same hash means same object.”** False: `hashCode()` is neither an address nor a unique ID. Two different objects can receive the same hash.
2. **“Same hash means `equals` always returns `true`.”** False: `"FB"` and `"Ea"` both have hash `2236`, yet `String.equals` returns `false`.
3. **“A hash collision causes `HashMap` to overwrite the wrong key.”** False for a properly working `HashMap` and contract-compliant keys. Two keys that differ according to `equals` can share a hash while remaining two independent entries.
4. **“Two unequal objects must have different hashes.”** There is no such requirement in the contract.
5. **“As long as `equals` is right, there is no need to care about `hashCode`.”** False: equal `equals` must imply equal hashes, especially when working with hash collections.
6. **“All keys having the same hash means the program is buggy.”** Not necessarily wrong in logic, though very poor hash distribution can hurt performance.
7. **“Checking that `hashCode` is equal is enough to replace `equals`.”** False. Only look at the hash to narrow down candidates; use the appropriate logical comparison to conclude equality.
8. **“`Objects.hash(...)` generates hash codes that never collide.”** False. It is a convenient way to build a hash from fields, still returning an `int` with a finite number of results.

## 10. Self-Check Questions

Decide whether each statement is **true** or **false**, then compare with the explanation:

| Statement | Answer | Explanation |
| --- | --- | --- |
| If `x.equals(y)` is `true`, then `x.hashCode() == y.hashCode()`. | True | This is the mandatory direction of the contract. |
| If `x.hashCode() == y.hashCode()`, then `x.equals(y)` must be `true`. | False | Collisions can occur. |
| If `x.hashCode() != y.hashCode()`, then `x.equals(y)` can be `true` in a contract-compliant class. | False | Equality must imply equal hashes. |
| Two `Customer` objects with the same `id` but different `name` can coexist in a `HashSet` when `equals` compares both fields. | True | Hashes may match; `equals` distinguishes elements. |
| Overriding `hashCode()` to always return 1 definitely breaks `equals()`. | False | A constant hash still satisfies the mandatory direction, though distribution is very poor. |
| Using `Objects.hash(id, name)` guarantees every pair of distinct `Customer` objects has different hashes. | False | There is no guarantee against collisions. |

Try modifying the `HashCollisionDemo` example yourself: change `Customer.hashCode()` to `Objects.hash(id, name)` and rerun. `a` and `copyOfA` must still produce equal hashes; `a` and `b` may produce different hashes. **Do not treat distinct hashes for the last pair as the criterion of correctness**: `equals` and the contract are the foundation.

## Key Takeaway

**`equals(a, b) == true` mandates the same `hashCode`; having the same `hashCode` cannot be reversed to infer `equals(a, b) == true`.** Collisions are a normal phenomenon of hash functions returning `int`. `HashMap` and `HashSet` still distinguish distinct keys/elements even when they share a hash code, as long as the key's `equals`/`hashCode` contract is upheld. When concluding equality by data, rely on `equals()` and the type's contract—do not treat a hash as identity or a unique fingerprint.
