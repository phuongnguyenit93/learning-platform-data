# HashSet and Its Relationship with Hash Tables

A `HashSet` answers the question "does this element belong to the set?" and guarantees that no duplicate equivalent members are stored. To avoid scanning every element one by one on each lookup, it uses a hash table to narrow down where to search.

In Java, the relationship is even more concrete: `HashSet` is backed by a `HashMap`. Each element of the set is stored as a **key** in the map; the associated value merely serves as a marker indicating presence.

Understanding this relationship helps explain the behavior of `add`, `contains`, `remove`, `null` support, collision handling, table resizing, and the limits of the O(1) claim. The examples use Java 17 or later; internal algorithm details are tied to a specific OpenJDK 17 build where needed.

## 1. Set Is the Data Requirement; a Hash Table Is the Implementation

A set models unique members. If A is already present, adding A again does not create a second member A.

A hash table is a storage and lookup structure based on the hash code of keys. It does not inherently carry the meaning of a "set" or a "dictionary"; that meaning depends on how the structure is used.

You can view the layers in three tiers:

~~~text
Set<E>
  contract: no duplicate members

HashSet<E>
  one implementation of the Set contract

HashMap<E, marker value>
  hash table mechanism that manages unique keys
~~~

Here, "hash table" is a data-structure term. It does not mean that `HashSet` uses the Java class named `Hashtable`. The [Java 17 HashSet documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) explicitly states that the backing map is a `HashMap`.

### 1.1. Why Not Just Keep a List?

If elements are stored in a regular list, checking whether a new element already exists may require comparing it against many preceding elements.

A hash table uses a fast computation to select a smaller candidate region. Afterward, it still has to check for a matching key; a hash code does not completely replace equality determination.

In return, the structure requires memory for the table, key-storing entries, and management metadata. The lookup benefit is not free, and it depends on the distribution quality of hash codes.

### 1.2. HashSet Does Not Need a Business Value for Each Element

A `HashMap<CustomerId, Customer>` stores a mapping from an ID to customer data. A `HashSet<CustomerId>` only needs to record which IDs are present.

Therefore, the set can use the map while discarding any business meaning for the value side. Every key is mapped to the same non-`null` marker value.

This design takes advantage of the fact that `HashMap` already manages unique keys. There is no need to reinvent a hashing engine just to build a set.

## 2. HashSet Elements Live on the Key Side of HashMap

Suppose a set has the members `java` and `spring`. The backing map can be modeled as follows:

~~~text
HashSet: {java, spring}

Backing HashMap:
key       value
java      PRESENT
spring    PRESENT
~~~

`PRESENT` represents a marker object. It is not data that users of `HashSet` need to access.

In the [OpenJDK 17 HashSet source code, build jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashSet.java), the map holds keys of type `E` and a shared marker value.

### 2.1. Operation Mapping Table

| Set operation | Corresponding work on the backing map |
|---|---|
| Add element `e` | Insert `e` on the key side, attached to the marker value |
| Check if `e` is present | Check if key `e` exists |
| Remove `e` | Remove the mapping with key `e` |
| Number of members | Number of mappings in the map |
| Iterate elements | Iterate over the keys |
| Clear all | Clear the mappings |

An element is not stored on the value side to be looked up with `containsValue`. Uniqueness comes from the keys.

### 2.2. Why `add` Knows Whether This Insertion Is New

`HashMap.put` returns the previous value associated with the key, or `null` when there was no prior mapping. In `HashSet`'s internal map, every existing mapping has a non-`null` marker value.

Therefore:

~~~text
put new key:
  no previous value -> returns null
  HashSet.add -> true

put existing key:
  previous value is the PRESENT marker
  HashSet.add -> false
~~~

There is no need for a separate full-set search to determine the result after insertion. The map insertion step already knows whether the key existed.

In the learning program below, `Boolean.TRUE` is used as a marker for illustration. It does not mean that the real `HashSet` stores Boolean values; the referenced implementation uses a dedicated marker object.

### 2.3. Why Emphasize a Non-Null Marker Value?

With a general `HashMap`, the map can have a key currently mapped to `null`. When putting that key, the returned previous value is still `null`, even though the key was already present.

Hence, the rule:

~~~text
put(...) returns null -> the key definitely did not exist before
~~~

does not hold for every use of `HashMap`.

It works for detecting a new insertion in the set model because of an extra condition: every existing member always carries a non-`null` marker.

If you build a map-backed structure yourself, you must preserve the model's invariant. Do not take an expression that is valid in a controlled internal map and apply it to a map that permits arbitrary values.

### 2.4. The Backing Map Is an Internal Detail

Users do not receive the internal map to swap out values or add/remove keys through a back door. The `HashSet` API exposes set operations.

This relationship explains the mechanism; it is not an invitation to cast `HashSet` to `HashMap` or use reflection on private fields in application code. Nor does `HashSet` extend `HashMap`; it uses the map as an internal component.

## 3. How Does a Hash Table Organize Key Lookup?

A common hash table model consists of:

- An array of **buckets** — indexed storage slots.
- The hash code of each key.
- Entries storing the key and linking metadata within a bucket.
- An equality check when multiple keys land in the same region.

The general process:

~~~text
element / key
      |
      v
key's hashCode
      |
      v
process hash code, compute bucket index
      |
      v
select candidate bucket
      |
      v
check for matching key in bucket
      |
      v
conclude present / absent
~~~

The goal is to avoid inspecting every bucket and every element for a single `contains` call.

### 3.1. A Hash Code Is Not a List Index

`hashCode()` returns an `int`, which can be negative. It is not directly a position from `0` to `size - 1`.

The table must transform the hash code into an index within the current number of buckets. Table size is a structural property, separate from the number of elements.

There is no contract that an element with a hash of 100 always sits in "slot 100". Nor is there a `HashSet.get(100)` to fetch an element by bucket.

### 3.2. Example with 16 Buckets

In a model that uses low bits like the referenced OpenJDK implementation, the integers 1, 17, and 33 can all land in bucket 1 when the table length is 16.

~~~text
bucket 0:  ...
bucket 1:  [key=1] -> [key=17] -> [key=33]
bucket 2:  ...
...
bucket 15: ...
~~~

The diagram only illustrates a bucket containing multiple entries; it is not read directly from a running `HashSet` object.

If three distinct keys are stored, the set's size is 3 even though only one bucket is used in this example. A bucket is not restricted to holding a single member.

### 3.3. Size, Capacity, and Non-Empty Buckets Are Three Different Numbers

| Quantity | Meaning |
|---|---|
| `size` | Number of current members/keys |
| Capacity | Number of buckets in the backing table once allocated |
| Non-empty buckets | How many slots currently contain at least one entry |

Collisions put multiple keys in the same bucket, so the number of non-empty buckets can be smaller than `size`.

Capacity being larger than `size` does not mean there are empty or `null` members in the set. Unused buckets are internal storage slots, not elements of the set.

## 4. Bucket Collisions Differ from Duplicate Elements

### 4.1. Same Bucket Does Not Guarantee Same Hash

With 16 buckets, two different hash codes can still produce the same index after narrowing to the range `0..15`.

For example, hash 1 and hash 17 can both map to bucket 1. If the structure only compared bucket indices and declared them duplicates, it would drop many distinct values.

An implementation can check the stored hash code before needing to compare keys. Not every key in the same bucket necessarily triggers an `equals` call; internal filtering steps can quickly rule out non-matching candidates.

### 4.2. Same Hash Does Not Guarantee Equality Either

Two different objects can have the exact same hash code. This is a form of hash collision.

A correct `HashSet` must still keep both if they are not equal according to the key's contract. The program uses two test keys A and B that both have hash 7 to verify this.

~~~text
hash(A) = 7
hash(B) = 7
A does not equal B

add(A) -> true
add(B) -> true
size = 2
~~~

A hash code is not a unique identifier, not proof that two objects are identical, and not a value to use for deduplication on its own.

### 4.3. The One-Way Requirement of `equals`/`hashCode`

Two objects that are equal according to `equals` must have the same `hashCode`. The converse is not required.

This is a requirement in the [Java 17 Object.hashCode contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()).

~~~text
equals true -> hashCode must be equal
hashCode equal -> still need to check equals
~~~

If a class overrides `equals` without providing a matching `hashCode`, a hash-based set may fail to manage objects according to the author's intended definition of duplicates. The structure cannot fix a broken key contract for you.

### 4.4. Hash Stability Relative to Key Data, Not Necessarily the Entire Application Lifetime

While an element is serving as a key in a hash-based set, the fields used for comparison and hashing must remain stable. If those fields are modified while the element is still in the set, lookup and removal may no longer behave as expected; the set contract does not define behavior for mutations that affect equality in this way.

This does not mean every field in an object must be immutable in every design. What matters are the fields that participate in membership criteria.

If the table resizes, do not treat that as a self-healing mechanism for a key whose hash changed after being added.

## 5. Some OpenJDK 17 Details: Hash Spreading, Bucket Selection, and Resizing

The details below describe the referenced source code, not a mandatory requirement that every `Set` implementation use the exact same formula.

### 5.1. Bit Spreading Before Bucket Selection

In [OpenJDK 17 HashMap, build jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java), the hash of a non-`null` key is processed by combining it with an unsigned 16-bit right shift of itself.

Computation model:

~~~text
raw    = key.hashCode()
spread = raw XOR (raw >>> 16)
index  = spread AND (capacity - 1)
~~~

Capacity in this calculation is a power of 2. Bringing the influence of upper bits down into the lower bits helps avoid relying solely on a group of low bits with poor distribution.

The spreading step does not turn two equal hash codes into different ones, nor does it guarantee every key gets its own bucket. It also does not turn an ordinary `hashCode` into a cryptographic hash function.

### 5.2. Buckets Depend on Table Size

When growing from 16 to 32 buckets, one more bit is used in the mask. Key 17, which was in bucket 1 in the 16-bucket model, can move to bucket 17 in the 32-bucket model.

Key 1 stays in bucket 1; key 33 can still share a bucket with 1. Resizing can separate some collisions, but it does not eliminate all collisions.

The program computes two bucket columns with assumed capacities of 16 and 32. It does not read the actual capacity of `HashSet` and does not promise that the test objects are using those exact tables at print time.

### 5.3. Load Factor Expresses the Threshold for Growth

The **load factor** is a parameter used to determine when the table needs to grow based on the number of keys present. It is not a directly measured ratio of non-empty buckets.

With capacity $c$ and load factor $\alpha$, the key-count threshold is typically computed near $c \times \alpha$, subject to integer arithmetic and bounds in the implementation.

A typical example with $c = 16$ and $\alpha = 0.75$ gives a threshold of 12. In the implementation under consideration, adding a new key that causes `size` to exceed this threshold can trigger a table resize. Re-adding an existing key does not increase `size` in that way.

The [Java 17 HashMap documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html) explains the relationship between capacity, load factor, and table resizing.

### 5.4. Resizing Is Real Work

When growing, a larger bucket array must be allocated and entries redistributed to their new positions. The purpose is to keep lookups efficient as the number of elements grows.

In the referenced OpenJDK, the hash code already stored in the entries is reused during redistribution; one should not oversimplify and say that every resize necessarily re-invokes `hashCode()` on every object.

An insertion that triggers a resize can do significantly more work than a normal insertion. Therefore, good average/amortized performance is not a fixed worst-case time guarantee for every individual call.

### 5.5. Crowded Buckets Can Change Representation

A bucket can hold a chain of entries. When the number of entries and the table size meet appropriate internal conditions, OpenJDK can convert that bin to a tree structure; when the table is still small, resizing may be preferred instead.

Do not memorize an unqualified rule like "exactly N colliding elements always become a tree." Nor should you infer that every subsequent access is guaranteed to be O(log n) under all key and comparison scenarios.

The tree mechanism is a safeguard for certain heavy-collision scenarios. It does not replace designing a reasonable `hashCode`, does not turn `HashSet` into `TreeSet`, and does not establish a sorted order for the entire set.

## 6. Null, Iteration Order, and What Hashing Does Not Guarantee

### 6.1. Why Does HashSet Allow One `null`?

The backing map allows a `null` key. `HashSet` uses that to represent a single `null` member, still paired with a non-`null` marker value.

The first `add(null)` can return `true`; subsequent calls return `false`. Size counts only one `null` member.

In the OpenJDK bucket-selection model under discussion, `null` has an internal hash of 0. Bucket 0 is not a reserved zone off-limits to other keys: another key whose bucket index is 0 can still be managed there alongside it.

### 6.2. HashSet Preserves Neither Insertion Order Nor Ascending Order

Iteration order is affected by the table and how entries are arranged internally; the API makes no promise to preserve any particular order. When the table resizes or data changes, you must not rely on an order you happened to observe.

If you need first-seen order, choose a structure/contract that preserves order. If you need sorting, perform a sorting step or use a collection with the appropriate contract.

In the example, printing members in ascending order is done as a separate step solely to make the output easy to compare. It does not prove that `HashSet` sorts itself.

### 6.3. The Hash Code of the Whole Set Differs from Element Hash Codes

`set.hashCode()` is the hash code of the set object according to the `Set` contract, built from the hash codes of its members. It does not return an element's bucket, capacity, or size.

[Java 17 Set.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#hashCode()) defines a set's hash code as the sum of the hash codes of its members, with `null` contributing 0. This rule ensures that equal sets have equal hash codes regardless of iteration order.

Distinguish between:

| Concept | What does it help explain? |
|---|---|
| `element.hashCode()` | The hash code of the key/element |
| Internally spread hash | Assists in computing a position in a specific table |
| Bucket index | Candidate region in a table of a specific capacity |
| `set.hashCode()` | Hash code of the entire set under the set equality contract |
| `set.size()` | Number of members |

## 7. Complete Program: Comparing HashSet Against the Map Model

The example below does not implement a full hash table from scratch. It uses the public `HashMap` to model how membership is recorded, then compares the results with a real `HashSet`.

The bucket section is an explanatory OpenJDK 17 calculation for a given capacity, not an inspection of `HashSet`'s private fields.

### 7.1. Source Code

Save as `HashSetTableDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class HashSetTableDemo {
    // Test key: intentionally gives every id the same hash to force collisions.
    record SameHashKey(String id) {
        SameHashKey {
            Objects.requireNonNull(id, "id");
        }

        @Override
        public int hashCode() {
            return 7;
        }
    }

    // Model of OpenJDK 17 bucket placement, without reading internal tables.
    static int modeledBucket(Object key, int capacity) {
        if (capacity <= 0 || (capacity & (capacity - 1)) != 0) {
            throw new IllegalArgumentException("capacity must be a positive power of two");
        }
        int raw = key == null ? 0 : key.hashCode();
        int spread = raw ^ (raw >>> 16);
        return spread & (capacity - 1);
    }

    static List<String> sortedMembers(Set<String> values) {
        Set<String> ordered = new TreeSet<>(
                Comparator.nullsFirst(Comparator.naturalOrder()));
        ordered.addAll(values);
        return new java.util.ArrayList<>(ordered);
    }

    public static void main(String[] args) {
        Set<String> actual = new HashSet<>();
        Map<String, Boolean> membershipModel = new HashMap<>();
        for (String key : Arrays.asList("java", "spring", "java", null, null)) {
            boolean setAdded = actual.add(key);
            boolean modelAdded = membershipModel.put(key, Boolean.TRUE) == null;
            System.out.printf("add(%s): set=%s, model=%s, sameKeys=%s, size=%d%n",
                    key, setAdded, modelAdded,
                    actual.equals(membershipModel.keySet()), actual.size());
        }
        System.out.println("members sorted for display: " + sortedMembers(actual));
        System.out.printf("contains java: set=%s, model=%s%n",
                actual.contains("java"), membershipModel.containsKey("java"));
        boolean setRemoved = actual.remove("java");
        boolean modelRemoved = membershipModel.remove("java") != null;
        System.out.printf("remove java: set=%s, model=%s, sameKeys=%s%n",
                setRemoved, modelRemoved, actual.equals(membershipModel.keySet()));

        System.out.println("modeled buckets: key, capacity16, capacity32");
        for (Integer key : Arrays.asList(1, 17, 33, null)) {
            System.out.printf("%s, %d, %d%n", key,
                    modeledBucket(key, 16), modeledBucket(key, 32));
        }

        Set<SameHashKey> collisions = new HashSet<>();
        System.out.println("same-hash A: " + collisions.add(new SameHashKey("A")));
        System.out.println("same-hash B: " + collisions.add(new SameHashKey("B")));
        System.out.println("same-hash A again: " + collisions.add(new SameHashKey("A")));
        System.out.println("same-hash size: " + collisions.size());
        System.out.println("same-hash ids sorted: "
                + collisions.stream().map(SameHashKey::id).sorted().toList());

        Map<String, Boolean> unsafeNullValueModel = new HashMap<>();
        unsafeNullValueModel.put("present", null);
        boolean alreadyPresent = unsafeNullValueModel.containsKey("present");
        Boolean previous = unsafeNullValueModel.put("present", Boolean.TRUE);
        System.out.printf("general map: alreadyPresent=%s, previousIsNull=%s%n",
                alreadyPresent, previous == null);

        Set<Integer> resizedByImplementation = new HashSet<>();
        for (int value = 0; value < 100; value++) {
            resizedByImplementation.add(value);
        }
        boolean allFound = true;
        for (int value = 0; value < 100; value++) {
            allFound &= resizedByImplementation.contains(value);
        }
        System.out.printf("after 100 distinct adds: size=%d, allFound=%s%n",
                resizedByImplementation.size(), allFound);

        Set<String> differentSize = new HashSet<>(List.of("java", "spring"));
        System.out.println("set hashCode is not size: "
                + (differentSize.hashCode() != differentSize.size()));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 HashSetTableDemo.java
java HashSetTableDemo
~~~

### 7.2. stdout Output

~~~text
add(java): set=true, model=true, sameKeys=true, size=1
add(spring): set=true, model=true, sameKeys=true, size=2
add(java): set=false, model=false, sameKeys=true, size=2
add(null): set=true, model=true, sameKeys=true, size=3
add(null): set=false, model=false, sameKeys=true, size=3
members sorted for display: [null, java, spring]
contains java: set=true, model=true
remove java: set=true, model=true, sameKeys=true
modeled buckets: key, capacity16, capacity32
1, 1, 1
17, 1, 17
33, 1, 1
null, 0, 0
same-hash A: true
same-hash B: true
same-hash A again: false
same-hash size: 2
same-hash ids sorted: [A, B]
general map: alreadyPresent=true, previousIsNull=true
after 100 distinct adds: size=100, allFound=true
set hashCode is not size: true
~~~

### 7.3. Reading the Output by Mechanism

Each addition to `HashSet` is compared against placing the same key into the model map. `sameKeys=true` indicates that the key sets are equal; this is a membership comparison, not an order comparison.

The two additions of `java` return `true` then `false`; the two additions of `null` do the same. This comes from key uniqueness in the map, not from whether the marker values differ.

`members sorted for display` uses a `TreeSet` with a null-accepting comparator for stable printing. The original `HashSet` still has no ordering guarantee.

The `modeled buckets` columns show that 1, 17, and 33 share a bucket at capacity 16, whereas 17 splits to bucket 17 at capacity 32. Both capacities are merely input assumptions to the `modeledBucket` function.

`SameHashKey` is a record with equality by `id` and a `hashCode` that intentionally always returns 7. This hashing satisfies "equal objects have the same hash" but has terrible distribution; it is used only to force collisions in this lesson, not as a hashing design pattern for applications.

`A` and `B` have the same hash and are still kept as two distinct members. Adding another `A` returns `false` because equality by `id` recognizes that `A` is already present.

The general map near the end has the key `"present"` mapped to `null`. `containsKey` reports that the key is already there while the previous value returned by `put` is still `null`. This is why the set model must maintain a non-`null` marker value.

After 100 distinct integer additions, `size` is 100 and every value is found. The program only verifies contents through the API; it cannot read the resize count or actual capacity.

The final line uses an example whose set hash code differs from its size as a reminder that the two methods have different contracts. It does not claim they can never coincidentally produce the same number.

## 8. Performance Models Must Be Conditional

### 8.1. When Are Basic Operations Near O(1)?

With a well-distributed hash function, a reasonable number of candidates per bucket, and moderate `hashCode`/`equals` cost, lookup, insertion, and removal have good expected performance.

When adding many elements, the cost of table resizes must also be amortized across the sequence of operations. An expected/amortized conclusion must not be turned into a constant worst-case promise for every input.

One way to break down the cost is:

~~~text
compute key hash
+ select bucket
+ check necessary candidates
+ allocate/update entry
+ resizing work if needed this time
~~~

If `hashCode` scans a very long string or `equals` does heavy work, that time still counts. Being constant with respect to the number of members does not mean constant with respect to all data sizes.

### 8.2. Why Capacity Affects Both Memory and Iteration

The `HashSet` documentation describes iteration cost as proportional to the number of members plus the capacity of the backing map. A very wide table with few elements can waste memory and make traversing the table less favorable.

Setting capacity too low can increase the number of allocations/resizes; setting it too high can leave many unused buckets. Load factor is a related trade-off, not a parameter where smaller is always better.

Therefore, you should not pre-allocate an excessively large number just to claim "it will never resize." Base it on the expected number of members and actual access patterns.

### 8.3. Constructor Capacity Is Not a Pre-Populated Member Count

`new HashSet<>(16)` creates an empty set; it does not create 16 elements and does not guarantee that 16 keys must be added before a resize is considered.

With the default load factor of 0.75, you must distinguish between the intended bucket count and the key-count threshold. In the referenced OpenJDK build, allocating the bucket array is even deferred until needed; an empty constructor does not mean an array full of data entries was immediately created.

There is no public getter on `HashSet` to retrieve the actual capacity. Learning examples that use a fixed capacity must state clearly that it is a model, as the program in this lesson does.

### 8.4. Choose the Structure Based on the Data Question

`HashSet` is a good fit when you need to manage unique members and check presence/absence by equality. If you need to store a value associated with each key, a `Map` expresses the goal more directly.

If you need to track occurrence counts, a set alone does not hold that information. If you need ordering, a plain hash-based set does not satisfy that presentation contract either.

Do not use fast lookup as an excuse to skip choosing the right data model.

## 9. Usage Conditions to Uphold

### 9.1. Keys with a Correct and Stable Contract

Define `equals`/`hashCode` using the same membership criteria. Whenever possible, use keys with stable components, such as records containing immutable strings or appropriate value types.

If an element has mutable fields, know which fields participate in equality/hashing. Do not modify them while the structure is actively using the element as a key.

### 9.2. HashSet Is Not Self-Synchronizing

Using a backing map does not make `HashSet` operations safe for concurrent modification by multiple threads. Nor can you rely on fail-fast behavior to protect a concurrent workflow.

If shared writes are needed, you must use proper coordination or a structure designed for that requirement. The examples in this lesson are single-threaded and do not demonstrate concurrent behavior.

### 9.3. Read Source Code to Understand, Not to Couple Business Logic to Private Details

Hash-spreading formulas, bucket representations, and tree-conversion conditions can vary across implementations and versions. Application code should rely on the set contract and documented performance guarantees.

What endures beyond internal numbers is: elements are keys, equality/hashing must be correct, collisions do not mean duplicates, and order must not be inferred from the hash table.

## 10. Common Misconceptions

| Claim | Accurate Understanding |
|---|---|
| `HashSet` extends `HashMap` | It uses the map as an internal component |
| Set elements are map values | Elements are used as keys; the value is only a presence marker |
| Each element needs a distinct marker value | The marker can be shared; uniqueness lives in the keys |
| `put` returning `null` always means a new key | That follows only when the map never stores `null` values for existing keys |
| Equal hashes mean the same element | Equality must still be checked |
| Same bucket means hashes are definitely equal | A bucket index is a narrowed result; different hashes can map to the same bucket |
| One bucket can hold only one element | Mechanisms exist to manage multiple entries in the same bucket |
| Capacity equals size | Capacity is the number of buckets; size is the number of keys |
| `null` occupies a dedicated bucket off-limits to other keys | It is a specially handled key; its bucket can still hold other keys |
| Resizing fixes any key whose hash changed | You must not rely on resizing to repair a violated key contract |
| Treeifying a bucket sorts the whole set | Local bucket organization does not create a set-wide ordering contract |
| O(1) lookup means every call has identical latency | Hashing, comparison, collisions, allocation, and resizing all factor in |
| `set.hashCode` is a bucket position or element count | It is the hash code of the entire set under the `Set` contract |
| `new HashSet(16)` starts with 16 elements | It is still empty; the argument relates to table capacity |

## 11. Self-Check Exercises

### Exercise 1: Key/Value Relationship

A set contains three members: A, B, and C. In the backing map model, how many keys are there and how many distinct business values are needed?

**Explanation:** There are three keys; no separate business value is needed per key. The keys can all share a single presence marker object.

### Exercise 2: Hash Collisions

Two keys have hash 7, but `equals` returns `false`. Is `HashSet` forced to keep only one key?

**Explanation:** No. The table must handle collisions and retain both distinct members when the data is valid.

### Exercise 3: Same Bucket

Why can hash 1 and 17 land in bucket 1 with 16 buckets, yet land in different buckets with 32 buckets in this lesson's model?

**Explanation:** With powers of 2, the mask uses the low bits according to capacity. Growing from 16 to 32 uses one additional bit; hash 17 can be separated into index 17. This is a position in a specific table, not the key's identity.

### Exercise 4: Map with a Null Value

A map already contains `K -> null`. Calling `put` with `K` and a non-`null` marker returns `null`. Can you conclude that `K` was not previously present?

**Explanation:** No. The returned previous value can be `null` because the key was already mapped to `null`. The set model avoids this ambiguity by not using `null` as the marker value for existing members.

### Exercise 5: Size and Buckets

There are 20 members, but only 7 non-empty buckets due to collisions. Is the set's size 7 or 20?

**Explanation:** 20. The number of used buckets is not the number of members.

### Exercise 6: Mutating Input

An object was added and then a field used to compute its hash was modified. Should you wait for a resize to "recompute and fix its position"?

**Explanation:** No. Preserve the key contract for the entire time the element is held in the set. Resizing is not a mechanism to repair a data mutation that violates the set's assumptions.

### Exercise 7: Ordering

A `HashSet` of integers happens to print in ascending order. Can it be treated as a sorted set?

**Explanation:** No. You need an explicit sorting contract or sorting step. An observed order does not become a guarantee of `HashSet`.

Viewing `HashSet` as a set of keys in a hash table bridges the "unique members" contract with its concrete storage mechanism. Fast lookup comes from selecting a candidate region by hash; correctness still depends on equality, collision management, and upholding key invariants.
