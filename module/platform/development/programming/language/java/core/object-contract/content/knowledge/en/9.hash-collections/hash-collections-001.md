# How Do HashMap and HashSet Coordinate `hashCode()` with `equals()`?

## 1. The Problem to Solve

`HashMap<K, V>` stores **key → value** pairs for lookup, insertion, or removal by key. `HashSet<E>` stores **non-duplicate elements**. To perform these operations efficiently, both structures need to answer:

1. Which **candidate group** should the key or element be searched in?
2. Within that group, is the object being searched for **equal** to an already stored object?

For ordinary Java objects, two methods cooperate to answer:

- **`hashCode()`** returns an `int` integer representing the hash value. It helps the hash structure locate the candidate group that may contain the key or element.
- **`equals(Object)`** decides whether two objects are considered **logically equal**.

`hashCode()` is the step that helps choose where to look; `equals()` is what confirms equality. **Having the same hash code is not enough to consider two objects equal.**

For example: two different product codes may coincidentally produce the same hash. `HashMap` must still distinguish them as two keys; `HashSet` must still be able to hold both elements if `equals()` returns `false`.

## 2. The Mandatory Contract Between equals and hashCode

The contract in `java.lang.Object` states:

> If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be `true`.

The converse is **not required**. Two objects with the same hash code can be completely different; that is a **hash collision**.

| Relationship between `a`, `b` | Valid? | Meaning |
| --- | --- | --- |
| `a.equals(b)` is `true`, hash codes are equal | Yes, required | Both objects are considered the same logical key/element |
| `a.equals(b)` is `false`, hash codes differ | Yes | May belong to different hash groups |
| `a.equals(b)` is `false`, hash codes are equal | Yes | Collision; `equals` must be used to distinguish them |
| `a.equals(b)` is `true`, hash codes differ | **No** | Violates the contract, causing bugs with hash structures |

Beyond compatibility with `hashCode`, `equals(Object)` must also guarantee **reflexivity, symmetry, transitivity, consistency**, and `x.equals(null)` being `false` for non-`null` `x`. `hashCode()` must return the same result across invocations within a single run when the information used by `equals` has not changed. It does not need to remain the same across different program runs.

Therefore, the practical rule is: **when overriding `equals(Object)` to define value equality, override `hashCode()` using the exact same components that form that equality.**

## 3. How Does HashMap Handle put/get Using the Two Methods?

Suppose we need to perform `map.put(key, value)` or `map.get(key)`.

### Step 1 — Obtain the hash code and determine the candidate position

`HashMap` uses the key's `hashCode()` to compute a position or candidate group in the hash table. The table can resize; the JDK may also perform bit-mixing steps on the hash. Therefore, **you should not infer the storage position solely from the displayed `hashCode()` number**.

### Step 2 — Compare keys in the candidate group

If another key with a matching hash is already present, `HashMap` must check **same reference or equality via `equals(Object)`** to know whether they represent the same logical key.

- If the new key **equals** an already stored key: `put` replaces the value associated with the existing key and returns the old value (if any).
- If the new key **does not equal** the stored key: `put` can store an additional entry, even if the two keys have the same hash code.
- When `get` is called, the structure goes to the candidates with a matching hash and uses the equality check to select the right entry; if none is found, it returns `null`.

Note that `get` returning `null` can also happen because the key **exists but is mapped to the value `null`**. Use `containsKey(key)` when you need to distinguish the two cases.

### Step 3 — Handling collisions or resizing

A group may contain multiple distinct keys with the same hash. The `HashMap` implementation in OpenJDK has mechanisms for handling collisions (and can convert a sufficiently large group into a tree-like structure), but that is an **implementation detail**, not a contract that application code is allowed to rely on.

Overview diagram:

```text
put / get
   |
   v
key.hashCode()
   |
   v
Determine candidate group in the hash table
   |
   v
Compare hash, then check same reference / equals(Object)
   |
   +-- equals stored key ------> same logical key
   |                             put: replace value; get: return value
   |
   +-- no equal key yet -------> put: add entry; get: not found
```

Not every call necessarily invokes `equals` directly: the same-reference case can be handled as a fast path. However, decisions about **equality between objects with different references** must be consistent with the `equals(Object)` contract.

## 4. How Does HashSet Rely on the Same Logic?

In terms of public behavior, `HashSet` answers the question **"does the set already contain an element equal to this element?"**:

- `set.add(x)` returns `true` if the set changed due to adding `x`.
- If an element `y` already exists such that `x.equals(y)` is `true` according to the contract, `add(x)` returns `false`; no extra logical element is created.
- `contains(x)` and `remove(x)` also need to locate by hash code and then distinguish by equality.

In the standard Java implementation, `HashSet` uses a `HashMap` internally: the set elements act as the **keys** of the map, while the associated value is merely an internal detail. Therefore, the `hashCode`/`equals` rules apply similarly to both.

| Operation | `HashMap` | `HashSet` |
| --- | --- | --- |
| Adding a new logical element | `put(k, v)` adds the key | `add(e)` adds the element, returns `true` |
| Adding a different object that equals an old key/element | `put` updates the value at the corresponding key | `add` does not add a new logical entry, returns `false` |
| Two different objects with the same `hashCode()` | Can exist as two keys if not `equals` | Can coexist if not `equals` |
| Lookup | `get`, `containsKey` | `contains` |

Both `HashMap` and `HashSet` allow `null`: `HashMap` has at most one `null` key; `HashSet` has at most one `null` element. `HashMap`/`HashSet` generally do not guarantee iteration order, so the output order during iteration must not be used as evidence of hash positions.

## 5. Java 17+ Example: Contract-Compliant and With Hash Collisions

Create the file `HashContractDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashContractDemo {
    static final class ProductKey {
        private final String sku;

        ProductKey(String sku) {
            this.sku = Objects.requireNonNull(sku);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof ProductKey other)) {
                return false;
            }
            return sku.equals(other.sku);
        }

        @Override
        public int hashCode() {
            return sku.hashCode();
        }
    }

    static final class CollisionKey {
        private final String code;

        CollisionKey(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof CollisionKey other
                    && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return 7; // Intentionally create a collision for illustration.
        }
    }

    public static void main(String[] args) {
        ProductKey first = new ProductKey("P-10");
        ProductKey same = new ProductKey("P-10");
        ProductKey other = new ProductKey("P-20");

        Map<ProductKey, String> prices = new HashMap<>();
        prices.put(first, "100");
        System.out.println(prices.put(same, "120"));
        prices.put(other, "250");
        System.out.println(prices.size());
        System.out.println(prices.get(new ProductKey("P-10")));

        Set<ProductKey> products = new HashSet<>();
        System.out.println(products.add(first));
        System.out.println(products.add(same));
        System.out.println(products.add(other));
        System.out.println(products.size());

        Set<CollisionKey> collisions = new HashSet<>();
        System.out.println(collisions.add(new CollisionKey("A")));
        System.out.println(collisions.add(new CollisionKey("B")));
        System.out.println(collisions.add(new CollisionKey("A")));
        System.out.println(collisions.size());
    }
}
```

Compile and run:

```bash
javac HashContractDemo.java
java HashContractDemo
```

Exact output:

```text
100
2
120
true
false
true
2
true
true
false
2
```

Explanation:

1. `first` and `same` are **two different instances** but `equals` is `true` because they have the same `sku`; their hashes are also equal. `put(same, "120")` updates the old entry and returns `"100"`. Thus, the map has only two logical keys (`P-10` and `P-20`).
2. A `new ProductKey("P-10")` still finds the value `"120"`: lookup relies on the **key value**, regardless of whether the exact original instance is used.
3. In `HashSet<ProductKey>`, adding `first` returns `true`; adding `same` returns `false` because an equal element is already present; adding `other` returns `true`.
4. `CollisionKey.hashCode()` always returns `7`, so `A` and `B` have the same hash code yet differ according to `equals`. `HashSet` still stores both. Adding another `A` is treated as a duplicate and returns `false`.

Intentionally using a constant hash **is valid with respect to compatibility with equality** (two equal objects still have the same hash), but yields very poor distribution when data is large. This is a way to illustrate collisions, not a recommended hashing strategy.

## 6. Dangerous Bug: equals Is Correct, but hashCode Does Not Correspond

The example below intends to consider two keys equal when `code` is the same, but computes the hash from `bucketId` — a component that **does not participate in equality**. This is a logic bug.

Create the file `BrokenHashDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class BrokenHashDemo {
    static final class BrokenKey {
        private final String code;
        private final int bucketId;

        BrokenKey(String code, int bucketId) {
            this.code = code;
            this.bucketId = bucketId;
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof BrokenKey other
                    && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return bucketId; // Wrong: two equal keys can have different hashes.
        }
    }

    public static void main(String[] args) {
        BrokenKey a = new BrokenKey("A", 1);
        BrokenKey b = new BrokenKey("A", 2);
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());

        Set<BrokenKey> set = new HashSet<>();
        set.add(a);
        set.add(b);
        System.out.println(set.size());
    }
}
```

Run with JDK 17:

```bash
javac BrokenHashDemo.java
java BrokenHashDemo
```

Output on JDK 17's `HashSet`/`HashMap` implementation:

```text
true
false
2
```

According to `equals`, `a` and `b` are one logical value; however, they have different hashes and are looked up in different groups, so the set can hold **two elements that are supposed to be considered equal**. The result no longer matches business expectations because the key class itself violates the contract. You must not rely on any specific collection behavior when an object violates this contract.

Fix this by computing `hashCode()` from the same field used by `equals`, such as `return code.hashCode();` (and ensuring `code` is non-`null` or using a consistent `null` rule). Conversely, if `bucketId` truly participates in defining whether two keys are equal, it must be included in both `equals` and `hashCode`.

**A similar mistake:** declaring only `equals(MyType)` is **overloading**, not overriding `Object.equals(Object)`. HashMap and HashSet rely on `equals(Object)`, so declare the exact signature `public boolean equals(Object obj)` with `@Override`.

## 7. Another Bug: Mutating a Key After Inserting Into HashMap

Suppose a key has a mutable `id` field and both `equals`/`hashCode` depend on `id`. We add the key with `id=10`; then change it to `id=20`.

Even though `hashCode()` computes correctly from the `id` value **at each moment**, the key may already reside in the hash group chosen when `id=10`. When searching with the hash for `id=20`, the map may look in a different group and fail to find the old entry, even if you still hold a reference to the key object.

**Safe approach:** design the fields used in a key's `equals`/`hashCode` to be immutable (`final` and with referenced state also stable). If you must change a key's value, remove the entry from the map/set **before mutating**, update the object, and then re-insert it — or create a new immutable key. If you happen to mutate it first, calling `remove` with the mutated key may fail to find the old entry.

`String`, `Integer`, or a record containing immutable components are suitable choices when the key semantics match. A record automatically generates `equals(Object)`/`hashCode()` based on its components, but a record **does not automatically make mutable objects contained inside it immutable**.

## 8. Performance and Limits to Understand Correctly

- On average, when hashing distributes well and there are no special issues, common operations of `HashMap`/`HashSet` can run with expected cost near **O(1)**. This is not a guarantee that every operation takes constant time.
- Poorly distributed hash codes create many collisions, increasing the number of candidate keys that must be checked. Two different objects having the same `hashCode` **is not a correctness bug**, but too many collisions hurt performance.
- `hashCode()` does not need to be unique, is not necessarily a memory address, and is not a stable identifier across different JVM restarts.
- `HashMap`/`HashSet` do not maintain insertion order as a public guarantee. If insertion order is needed, consider `LinkedHashMap`/`LinkedHashSet`; if sorted order is needed, look into `TreeMap`/`TreeSet` and their comparison rules.
- `HashMap`/`HashSet` are not automatically safe for concurrent modification from multiple threads without proper synchronization mechanisms; this is independent of `equals/hashCode` quality.

It is important to distinguish the **API contract** (two equal objects must have the same hash, a set has no logically duplicate elements) from **hash table structure details** (bucket capacity, bit mixing, expansion thresholds, treeification). Application code should rely on the contract, not on implementation details.

## 9. Key Design and Testing Checklist

1. **Define equality** according to business logic: product keys by `sku`, accounts by a stable code, or objects by multiple attributes?
2. **Override both methods properly:** `equals(Object)` and `hashCode()`; use `@Override` so the compiler catches wrong signatures.
3. **Use the same set of fields** in both rules. If two objects are equal, they must certainly produce the same hash code; accept matching hash codes for different objects.
4. **Keep key state stable** while the object is inside a map or set; also watch out for nested objects that may mutate.
5. **Test three kinds of pairs:** the same object, two different objects that are equal, and two different objects intentionally having the same hash but not equal.
6. **Test through the collection:** `map.put(k1,v1)` then `map.put(k2,v2)` with `k1.equals(k2)` must update the same key; `set.add(k2)` after `set.add(k1)` must return `false`.
7. **Ensure equality is symmetric and transitive**, especially if keys have an inheritance relationship. A subclass using extra fields for comparison can break the contract with its superclass.
8. **Do not confuse null with a missing key:** when you need to distinguish a `null` value, use `containsKey` instead of relying solely on `get`.

**Self-check:**

- Two keys with the same hash but `equals` is `false`: can `HashMap` hold both? **Yes.**
- Two keys where `equals` is `true` but hashes differ: is the key class valid? **No.**
- Adding a key equal to an existing key into `HashMap`: does the number of logical keys increase? **No; `put` updates the value of the corresponding key.**
- Why does `HashSet.add(x)` know to return `false` for a duplicate element? **Because it uses the same key-identification mechanism via hash code and equality.**

**Remember:** `hashCode()` helps find **where the object might be located**; `equals(Object)` decides **whether it is an object equal by value**. HashMap and HashSet only operate as expected when both methods follow a single consistent equality contract.