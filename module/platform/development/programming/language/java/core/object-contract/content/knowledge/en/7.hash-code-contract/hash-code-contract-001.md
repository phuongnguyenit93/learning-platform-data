# `hashCode()` Returns `int` to Support Hash-Based Data Structures

## 1. What Is `hashCode()` and Why Is Its Return Type `int`?

In Java, every class inherits the `public int hashCode()` method from `java.lang.Object` (which can be overridden). The method returns a **signed 32-bit hash value** so that hash-table-based data structures, such as `HashMap` and `HashSet`, can organize and look up elements efficiently.

- **The `int` type is part of the method signature in Java**, not an arbitrary choice in subclasses. Its range is from `-2_147_483_648` to `2_147_483_647` (a total of `2^32` bit patterns). Negative numbers, 0, and positive numbers are all valid results.
- **A hash code is not a unique ID.** The 32-bit space is finite, so completely different objects can share the same hash code (a hash collision).
- **A hash code is not a direct bucket index.** The hash structure still has to map the hash value to a position in its current storage area. The mapping algorithm and bucket count depend on the implementation; they can change when the structure resizes.
- **A hash code is also not a guaranteed memory address.** The default `Object.hashCode()` is tied to object identity equality, but Java does not guarantee that it is an address, unique, or constant across JVM runs.

Returning an `int` creates a common interface so Java libraries can hash any object. This value helps *narrow down the candidates to check*; determining whether two keys are actually equal still relies on `equals()`.

## 2. How Do `HashMap` and `HashSet` Use the Hash Value?

Adding and looking up a non-`null` key in `HashMap` can be understood conceptually as follows:

1. Call `hashCode()` on the key to obtain the hash integer; the implementation may further mix the bits.
2. Convert the hash value into a bucket position in the current table.
3. Search the bucket for candidate entries. When a matching hash is encountered, compare key equality, usually via `equals()`; if multiple keys land in the same bucket, the structure must distinguish them.
4. If an equivalent key according to `equals()` is found, `put` updates the value; if not found, it adds a new entry. On `get`, it returns only the value corresponding to the matching key.

`HashSet` uses a similar idea to decide whether an element is already in the set; the standard implementation is backed by an internal `HashMap`. In particular, **identical hash codes do not mean identical elements**. Two different keys with the same hash are still stored separately if `equals()` returns `false`.

Bucket details, collision-handling mechanisms, and resizing policies are implementation matters; programs should not rely on a specific bucket formula, iteration order, or fixed element positions.

With a reasonable hash distribution and appropriate load factor, typical hash table operations have an average cost close to `O(1)`. If too many keys collide or distribution is poor, the cost of processing within a bucket increases; `hashCode()` does not guarantee every operation is always `O(1)`.

## 3. The Mandatory Contract Between `equals()` and `hashCode()`

According to the `Object` contract:

- During a single execution of a Java application, when the data used to determine `equals()` on an object does not change, repeated calls to `hashCode()` on that object must return the same result.
- **If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be `true`** (assuming `a` and `b` are non-`null`).
- If `a.equals(b)` is `false`, **there is no requirement** that the two hash codes be different. Collisions are valid.
- Two independent runs of the same program do not necessarily produce the same hash code for every object.

Therefore, **a class that overrides `equals()` needs to override `hashCode()` consistently**. If two keys are considered equal but produce different hashes, `HashMap.get()` or `HashSet.contains()` may fail to find the stored element.

The reverse direction is not true:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
a.hashCode() == b.hashCode()  =/=>  a.equals(b) == true
```

## 4. A Java 17+ Program Demonstrating a Hash Collision

Save the complete program as `HashCodeDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class HashCodeDemo {
    static final class Key {
        private final String value;

        Key(String value) {
            this.value = Objects.requireNonNull(value);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Key other)) return false;
            return value.equals(other.value);
        }

        @Override
        public int hashCode() {
            return value.hashCode();
        }
    }

    public static void main(String[] args) {
        Key first = new Key("FB");
        Key second = new Key("Ea");

        Map<Key, String> map = new HashMap<>();
        map.put(first, "first");
        map.put(second, "second");

        System.out.println("hash(FB): " + first.hashCode());
        System.out.println("hash(Ea): " + second.hashCode());
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("map.size(): " + map.size());
        System.out.println("lookup new FB: " + map.get(new Key("FB")));
        System.out.println("lookup new Ea: " + map.get(new Key("Ea")));
    }
}
```

Compile and run:

```bash
javac HashCodeDemo.java
java HashCodeDemo
```

Exact output:

```text
hash(FB): 2236
hash(Ea): 2236
first.equals(second): false
map.size(): 2
lookup new FB: first
lookup new Ea: second
```

Explanation:

- In Java, `String.hashCode()` is computed using the accumulation formula `31 * h + char`. `"FB"` and `"Ea"` both yield `2236`: `70 * 31 + 66 = 2236`, `69 * 31 + 97 = 2236`.
- Both `Key` instances use `value.hashCode()`, so they also produce the same hash code. However, `value.equals(...)` returns `false` because `"FB"` differs from `"Ea"`.
- `HashMap` keeps **two** separate keys. A new `new Key("FB")` key has the same meaning as `first` according to `equals()` and has the same hash code, so it retrieves the value `"first"`.
- Nothing in the example requires knowing the internal buckets of `HashMap`; the output simply demonstrates that the hash code is used to find candidates while `equals()` determines equality.

## 5. Designing `hashCode()` for a Custom Class

To uphold the contract, choose the data fields that participate in `equals()` as the basis for computing the hash. The example below is a standalone class-syntax snippet for illustration (without `main`):

```java
import java.util.Objects;

final class ProductKey {
    private final String sku;
    private final int version;

    ProductKey(String sku, int version) {
        this.sku = Objects.requireNonNull(sku);
        this.version = version;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof ProductKey other)) return false;
        return version == other.version && sku.equals(other.sku);
    }

    @Override
    public int hashCode() {
        int result = sku.hashCode();
        return 31 * result + Integer.hashCode(version);
    }
}
```

In the example, `equals()` inspects `sku` and `version`; `hashCode()` also inspects both. `int` multiplication/addition can overflow according to Java integer rules, which is **allowed** for hash codes. This is a common combination formula, not the only one.

Helper tools:

- `Objects.hash(sku, version)` helps combine multiple fields; it allocates a varargs array and performs boxing in some cases, so weigh that in high-performance paths.
- `Objects.hashCode(reference)` returns `0` if the argument is `null`, otherwise it calls `reference.hashCode()`.
- If a field is an array and you want to compare by **array contents**, use the pair `Arrays.equals(...)` / `Arrays.hashCode(...)` (or the appropriate deep variant for nested arrays); arrays themselves do not compare contents via `Object.equals()`.
- A Java `record` automatically generates appropriate `equals()` and `hashCode()` based on the record components. You can prefer records for value objects when they fit your design requirements.

## 6. Common Mistakes and How to Avoid Them

| Mistake | Consequence or Correct Understanding |
| --- | --- |
| Overriding only `equals()` and omitting `hashCode()` | Two equal objects may have different hashes; lookups in hash structures fail |
| Thinking matching hashes mean equal objects | Matching hashes are a normal collision; `equals()` is still needed to distinguish them |
| Using a hash number as a global ID or unique database key | `int` is finite, collisions are allowed, and stability across runs is not guaranteed |
| Always returning the same number (such as `1`) | Does not necessarily violate the contract, but gives very poor distribution and hurts performance |
| Mutating fields used in `equals()` / `hashCode()` after placing the key into a `HashMap` | The key may be looked up in a different bucket than where it was stored, causing `get`/`containsKey` to fail |
| Assuming hash codes are always non-negative | `int` hash codes are signed; hash libraries must handle negative values as well |
| Assuming `HashMap` iteration order determined by hashes is stable | `HashMap` does not guarantee iteration order, including after additions/removals or resizing |

**Recommendation:** Use immutable keys (fields involved in comparison are `final` and component values are not mutated). Test in both directions: equal objects must have the same hash; distinct objects must still be managed properly by hash structures even when they accidentally collide.

## 7. Self-Check Questions

1. Two different objects both return hash `42`. Must `HashSet` keep only one object? **No**; it must inspect `equals()` to determine whether elements are equal.
2. Two objects are considered equal by `equals()` but have different hashes. Is that valid? **No**; that is a contract violation and can break lookup logic.
3. Can a valid object return a negative hash? **Yes**; `hashCode()` returns a signed `int`.
4. Can you derive the bucket directly from `hashCode()` to store outside `HashMap`? **You should not**; the bucket depends on capacity and implementation, and is not part of the `Object.hashCode()` contract.

**Takeaway:** `hashCode()` returns an `int` to support fast mapping from a key to a group of candidates; `equals()` determines whether keys are actually equal. **Equal ⇒ same hash; same hash ⇏ equal.**
