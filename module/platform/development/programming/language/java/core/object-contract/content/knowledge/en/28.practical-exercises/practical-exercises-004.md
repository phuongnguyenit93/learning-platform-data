# Experimenting with Hash Collisions on Unequal Objects

A **hash collision** occurs when two objects have the same `hashCode()` value but **`equals()` returns `false`**. This is a valid situation under the Java contract. A structure such as `HashMap` or `HashSet` must handle collisions so that distinct keys are still kept separate.

This practice answers three questions with runnable code: how to create and observe collisions; why two keys with the same hash still coexist in a collection; and where the boundary lies between the **correctness** of `equals/hashCode` and the **distribution quality** of a hash function.

## 1. The Contract to Understand Before Experimenting

For two non-`null` object references `a` and `b`:

- If `a.equals(b) == true`, then `a.hashCode() == b.hashCode()` **must** hold.
- If `a.hashCode() == b.hashCode()`, **you cannot conclude** `a.equals(b) == true`.
- If `a.hashCode() != b.hashCode()` and the methods obey the contract, you can conclude `a` and `b` are not equal.
- While the data used for comparison does not change, `equals()` and `hashCode()` must yield consistent results. Avoid mutating fields participating in the hash while the object serves as a `HashMap` key or `HashSet` element.

You can visualize this as:

```text
                a.hashCode() == b.hashCode() ?
                           |
              +------------+------------+
              |                         |
             No                        Yes
              |                         |
       Two unequal keys        Equality unknown yet
                                        |
                                  Check equals()
                                    /        \
                                  true       false
                                   |           |
                               Same key   Hash collision
```

The implication **`equals == true → equal hashCode`** is one-way. A hash function maps a very large object value space down to a 32-bit `int`, so many distinct values can share a single hash number. Even a function returning the same constant for every object can still *obey the contract*, albeit with terrible hash distribution.

## 2. Natural Collisions Reproducible with `String`

In Java, the two distinct strings `"Aa"` and `"BB"` have the exact same hash code:

```text
"Aa": 31 × 65 + 97 = 2112
"BB": 31 × 66 + 66 = 2112
```

Here 65/97/66 are the UTF-16 character values of `A`, `a`, `B`; the simple formula for a two-character string is `31 * c0 + c1`. For longer strings, `String.hashCode()` accumulates via a polynomial with multiplier 31 in 32-bit integers, allowing overflow per `int` arithmetic rules.

Yet `"Aa".equals("BB")` is `false` because the string contents differ. This is **a real collision of `String.hashCode()`**, requiring no JDK modifications, memory tricks, or external libraries.

## 3. Standalone Runnable Java 17+ Program

The program contains two experiments:

1. **Natural collision:** directly use `String` `"Aa"` and `"BB"` as keys.
2. **Intentional collision:** define `ProductKey` whose `equals()` compares `sku` while `hashCode()` always returns `7` to force distinct keys to collide on hash.

Save the following content as **`HashCollisionDemo.java`**:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashCollisionDemo {
    public static void main(String[] args) {
        // Experiment 1: real collision with String.
        String a = "Aa";
        String b = "BB";

        System.out.println("String hash: "
                + a.hashCode() + " / " + b.hashCode());
        System.out.println("String equals: " + a.equals(b));
        System.out.println("Wrong if comparing hash only: "
                + (a.hashCode() == b.hashCode()));

        Set<String> stringSet = new HashSet<>();
        stringSet.add(a);
        stringSet.add(b);
        System.out.println("String set size: " + stringSet.size());

        Map<String, Integer> stringMap = new HashMap<>();
        stringMap.put(a, 10);
        stringMap.put(b, 20);
        System.out.println("String map values: "
                + stringMap.get(a) + " / " + stringMap.get(b));

        // Experiment 2: intentionally make every ProductKey share the same hash.
        ProductKey first = new ProductKey("SKU-A");
        ProductKey second = new ProductKey("SKU-B");
        ProductKey sameAsFirst = new ProductKey("SKU-A");

        System.out.println("Custom hash: "
                + first.hashCode() + " / " + second.hashCode());
        System.out.println("Distinct keys equal: "
                + first.equals(second));
        System.out.println("Equivalent keys equal: "
                + first.equals(sameAsFirst));

        Set<ProductKey> productSet = new HashSet<>();
        productSet.add(first);
        productSet.add(second);
        productSet.add(sameAsFirst);
        System.out.println("Custom set size: " + productSet.size());

        Map<ProductKey, String> productMap = new HashMap<>();
        productMap.put(first, "value A");
        productMap.put(second, "value B");
        System.out.println("Custom map size: " + productMap.size());
        System.out.println("Lookup equivalent: "
                + productMap.get(sameAsFirst));
        System.out.println("Lookup second: "
                + productMap.get(second));
    }

    // Example intentionally using a poor hashCode to observe collisions.
    // Do not copy a constant-hash strategy into production code.
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
            return 7; // Intentionally cause collisions for experimentation.
        }
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac HashCollisionDemo.java
java HashCollisionDemo
```

**Exact stdout:**

```text
String hash: 2112 / 2112
String equals: false
Wrong if comparing hash only: true
String set size: 2
String map values: 10 / 20
Custom hash: 7 / 7
Distinct keys equal: false
Equivalent keys equal: true
Custom set size: 2
Custom map size: 2
Lookup equivalent: value A
Lookup second: value B
```

The output does not depend on the iteration order of `HashMap` or `HashSet`: the program only prints direct lookup results and `size()`. If you replace this with a `for` loop to print the entire collection, **do not assume a stable element order**.

## 4. Interpreting the Experiment Results

### Experiment 1: Same hash yet both strings remain present

`"Aa"` and `"BB"` share the hash `2112`, yet `String.equals()` confirms they are distinct. `HashSet.add(a)` and `HashSet.add(b)` both add separate keys, so `stringSet.size() == 2`.

With `HashMap`, the two calls `put("Aa", 10)` and `put("BB", 20)` keep **two separate mappings**. `get("Aa")` returns `10`; `get("BB")` returns `20`. A collision **does not automatically overwrite** another key's value.

Conversely, the following wrong statement treats the two strings as equal just because their hashes match:

```java
boolean incorrect = "Aa".hashCode() == "BB".hashCode();
// incorrect == true, even though "Aa".equals("BB") == false.
```

**Do not use a hash code as a unique ID or as a substitute for `equals()`.** A hash is useful to narrow down comparison candidates, not to prove two objects have equal content.

### Experiment 2: Distinguishing "colliding hash" from "equivalent key"

`first`, `second`, and `sameAsFirst` all return hash `7`. However:

| Object pair | `equals` result | Meaning |
| --- | --- | --- |
| `first` / `second` | `false` | Different SKUs; this is a collision. |
| `first` / `sameAsFirst` | `true` | Identical SKU; two instances of the same logical key. |
| `second` / `sameAsFirst` | `false` | Different SKUs; another collision. |

`productSet.size() == 2` because two SKU values are distinct, while the third object is equivalent to the first and does not create a new logical element. Likewise, `productMap.size() == 2`; querying with a new object having SKU `"SKU-A"` still finds the value attached to `first`.

This proves **equal hashes are not enough to count as duplicate elements**. Hash-based collections also evaluate equivalence via `equals()` (or the corresponding key equivalence relation per contract).

## 5. How Do Collections Resolve Collisions?

Conceptually, a lookup in `HashMap` follows these steps:

1. Compute the hash from the provided key; `HashMap` may further transform this hash to pick a storage slot in its internal table.
2. Locate the candidate slot/group from the hash.
3. Within the candidate group, compare hashes and key equality. Keys with the same hash where `equals() == false` remain distinct keys.
4. If an equivalent key exists, `get` returns its associated value; if `put` is called with an equivalent key, the existing mapping's value is replaced. Otherwise, `put` creates a new mapping.

`HashSet` uses a hash-backed structure, so it likewise distinguishes elements sharing a hash using the equality relation.

Illustrative diagram (not describing the exact memory layout of any specific JDK release):

```text
hashCode("Aa") = 2112 ─┐
                       ├── Candidate group with colliding hash
hashCode("BB") = 2112 ─┘          |
                                  +-- equals("Aa", "BB") -> false
                                  +-- Can store/look up two separate keys

hashCode(ProductKey("SKU-A")) = 7 ─┐
                                   ├── Candidate group with same hash
hashCode(ProductKey("SKU-A")) = 7 ─┘          |
                                              +-- equals -> true
                                              +-- One logical key
```

Some `HashMap` implementations may convert a group containing many colliding elements into a tree structure under certain conditions. This is an **implementation optimization detail**, not a reason to depend on specific buckets, iteration order, `equals` call counts, or fixed execution time in application code.

## 6. A Good Hash Function Differs from a Contract-Compliant Hash Function

`ProductKey.hashCode()` returning `7` in all cases **does not violate** the rule "equal objects must have equal hashes." However, it fails to spread distinct SKU values out, forcing many operations to process a single candidate group.

In production code, a more reasonable version derives from the exact field participating in `equals`:

```java
@Override
public int hashCode() {
    return sku.hashCode();
}
```

The snippet above is **a replacement method inside the `ProductKey` class in the example**, not a standalone `main` program. Because `sku` is a non-`null`, immutable `String`, this approach obeys the contract and typically distributes keys far better than the constant `7`. It can still collide, as `"Aa"` and `"BB"` demonstrated.

Criteria to keep separate:

| Criterion | Requirement |
| --- | --- |
| **Contract-compliant** | Any two objects with `equals == true` have equal hashes. |
| **Consistent** | While comparison data does not change, the hash does not change across calls per contract. |
| **Reasonable distribution** | On real data, minimize having too many unequal keys share a hash to improve average performance. |
| **Uniqueness not required** | It is impossible to guarantee every object value gets its own unique 32-bit `int` hash. |

Hash distribution quality depends on the data used. In an application exposed to adversarial input, many keys could be chosen to trigger mass collisions; this is a performance concern to monitor, even though lookup results remain correct as long as the contract holds.

## 7. Common Mistakes When Experimenting

### Mistake 1: Claiming two objects are equal merely because their hashes match

Wrong:

```java
boolean same = a.hashCode() == b.hashCode();
```

Right when checking object equality per contract:

```java
boolean same = Objects.equals(a, b);
```

For potentially `null` references, `Objects.equals` handles `null` and calls `equals` when needed. It does not turn a broken `equals` implementation into a correct one.

### Mistake 2: Trying to tweak `equals()` to "avoid collisions"

Collisions do not mean `equals()` has a bug. `equals()` must express the class's **meaningful equality relation**; `hashCode()` must stay consistent with that relation. Folding hash checks into `equals()` conditions can make equality depend on a hash code that is inherently non-unique.

### Mistake 3: Overriding one method and forgetting the other

If you override `equals()` so two objects at different memory addresses are considered equal, you must also override a compatible `hashCode()`. Otherwise, `HashMap` or `HashSet` may fail to find an equivalent key, or hold two elements that `equals()` declares equal.

### Mistake 4: Mutating a key after adding it to a hash collection

If a mutable field is used in `equals/hashCode`, updating that field can change the hash and cause lookups to fail. `HashMap` does not automatically move an already-stored entry to a new slot just because the key object was mutated. In the example, `sku` is `final` to prevent this mistake.

### Mistake 5: Using single-run timing to draw performance conclusions

This lesson proves **correctness under collisions**, not benchmarking. Timing results from a short single run are affected by JIT compilation, JVM warmup, GC, table size, and input data. If you need to evaluate speed between a constant hash function and a good hash function, use a sufficiently large key set, a defined input distribution, and an appropriate benchmarking tool (e.g., JMH) after verifying correctness.

## 8. Extended Checks

You can modify the program to test additional scenarios:

1. **Re-adding an equivalent key:** call `productMap.put(sameAsFirst, "new value A")`. The map size stays `2`; looking up with `first` returns the new value because `first.equals(sameAsFirst) == true`.
2. **Adding a third unequal key that also has hash `7`:** use `new ProductKey("SKU-C")`. The map size increases to `3` when that key is `put`; all three keys still look up independently.
3. **Switching `hashCode()` to `sku.hashCode()`:** rerun the same example. Equality, collection sizes, and lookup results remain identical. The `"SKU-A"`/`"SKU-B"` pair no longer needs to share a hash.
4. **Testing two other colliding string keys:** replace the SKUs with `"Aa"` and `"BB"` in the `sku.hashCode()` version; both have hash `2112` yet `equals()` still distinguishes the two objects.

There is no need to inspect bucket sizes or access internal `HashMap` structures to confirm these conclusions. The most valuable checks are **`equals`, `hashCode`, `size`, `get`, and the resulting value when updating an equivalent key**.

**Technical takeaway:** `hashCode()` helps organize and narrow down candidate groups; **`equals()` determines logical equality**. Collisions between unequal objects are normal; a correct hash structure must keep each distinct key separate, while good hash design aims to reduce the cost of handling collisions.