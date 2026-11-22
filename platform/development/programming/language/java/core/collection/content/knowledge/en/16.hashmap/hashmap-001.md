# Hash Table, Buckets, and the Key Lookup Process

## 1. How Does HashMap Solve the Lookup Problem?

Suppose you need to look up a product name from a product code. With a list of pairs, the simple approach is to scan sequentially until you find a matching code. If the data is large and lookups happen frequently, always starting from the beginning of the list is expensive.

A hash table uses information computed from the key to narrow down where to search. Instead of checking every mapping, it selects a region containing candidates and only inspects the keys in that region.

In `HashMap`, that region is commonly called a **bucket**: a slot in the table that holds the mappings assigned to that position. You can picture a bucket as a filing drawer, and the hash code as the data that helps pick the drawer. Once at the right drawer, you still have to inspect the actual file; the drawer number does not replace key identity.

`HashMap` is a hash-table-based `Map` implementation. Lookup efficiency depends on keys being distributed appropriately across buckets. It does not guarantee insertion order or a stable iteration order. [HashMap documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

After this lesson, you should be able to trace the path:

~~~text
key to look up
    -> hash code from the key
    -> internally processed hash
    -> bucket index
    -> inspect candidates in the bucket
    -> find the exact key or conclude it is absent.
~~~

The focus is not on memorizing a formula and computing buckets manually in application code. When using `HashMap`, your application still calls `put`, `get`, or `containsKey`; understanding the mechanism helps you design keys properly and diagnose lookup bugs.

## 2. Concepts to Keep Separate

| Concept | Meaning |
| --- | --- |
| Key | Object used to identify the mapping to look up |
| Value | Data associated with the key |
| Hash code | An integer provided by the key's `hashCode()` |
| Internal hash | Value processed by `HashMap` for use in the table |
| Capacity | Number of bucket slots in the table |
| Bucket index | Specific slot selected in the table |
| Node | Unit holding a mapping and metadata for searching |
| Size | Number of key–value pairs currently stored |

Capacity is not the same as size. A table with 16 buckets might currently hold only four mappings. Those four mappings could sit in four different buckets or all land in the same bucket.

A hash code is not a bucket index either. `hashCode()` returns an `int` value, whereas the table only has a finite number of slots. A step is required to map the hash code into the valid index range.

In OpenJDK 17, a regular node holds the computed internal hash, the key, the value, and a link to the next node when a bucket has a chain of nodes. Buckets converted to tree form use a node type with additional tree fields. This is the implementation model used to explain the mechanism, not public fields for application code to access.

Do not confuse `HashMap` with an array indexed by integer keys. A key `Integer.valueOf(100)` is not required to be stored at index 100, and `HashMap` does not automatically allocate 101 elements just because the key 100 is present.

## 3. hashCode and equals Have Different Responsibilities

The hash code helps select and filter where to search. `equals` determines whether two objects are considered the same key according to how the data is defined.

The contract to uphold:

- If two objects are equal according to `equals`, they must have the same `hashCode`.
- Two objects with the same hash code may still be unequal.
- The fields that affect equality and the hash code must be used consistently.

The contract does not require every distinct object to have a distinct hash code. Multiple different keys can share the same hash code; the hash table structure must handle this case. [Object.hashCode and Object.equals contract, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).

Illustrative example:

~~~text
Key A: hashCode = 1
Key C: hashCode = 1
A.equals(C) = false

Conclusion: A and C are two different keys, even though their hash codes collide.
~~~

Conversely, a new object representing the same key data as a stored object must be found during lookup if `equals`/`hashCode` are implemented correctly and the key's data has not been mutated.

You do not need the same object reference to find the same key. The `==` check can quickly recognize the exact same object instance, but it does not replace data-based equality.

A hash code is not a unique identifier, not a sort order, and not a cryptographic security value. A hash code of 0 also does not mean the key does not exist.

## 4. From a Key's Hash Code to the Internal Hash in OpenJDK 17

The details below are referenced against OpenJDK 17's `HashMap`. The formula, node layout, and optimizations can change across implementations or versions; the contract for accurate key lookup via `equals`/`hashCode` is what application code should rely on. [HashMap source code, OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java).

For a non-null key, the hash-processing model is:

~~~java
int mixed = rawHash ^ (rawHash >>> 16);
~~~

Where:

- `rawHash` is the code returned by `key.hashCode()`.
- `>>> 16` performs an unsigned right shift by 16 bits, bringing the upper bits down to the lower positions.
- `^` is the bitwise XOR operator.
- `mixed` is the hash value used further in the table mechanics.

Because the bucket index at a power-of-two capacity depends on only a few low bits, mixing the high bits downward allows differences in the upper bits to participate in bucket selection. It does not produce a unique code for every key and cannot fix a `hashCode` method that always returns the same number for all objects.

Example:

~~~text
rawHash = 65536 = 0x00010000
rawHash >>> 16 = 1
mixed = 65536 XOR 1 = 65537 = 0x00010001
~~~

If you only look at the lowest four bits of `rawHash`, they are all 0; after mixing, the lowest four bits incorporate information from the upper bits.

For a `null` key, OpenJDK uses an internal hash of 0 without calling `hashCode()` on `null`. This allows `HashMap` to support a `null` key, though it does not mean bucket 0 is reserved exclusively for `null`. Other keys whose internal hash maps to index 0 can still share the same bucket.

A hash code can be negative. This is not an error condition; all 32 bits of the `int` can still participate in slot selection.

## 5. Selecting a Bucket Using the Current Capacity

In the OpenJDK 17 model, when the table capacity `n` is a power of two, the index is computed as:

~~~java
int index = mixedHash & (n - 1);
~~~

This is a bitwise AND, not the logical `&&` operator. With `n = 16`:

~~~text
n - 1 = 15 = 0b1111

mixedHash & 15 keeps the lowest four bits.
The result is in the range 0 to 15.
~~~

Examples:

| Initial hashCode | Mixed hash | Bucket if n = 16 | Bucket if n = 32 |
| --- | --- | --- | --- |
| 1 | 1 | 1 | 1 |
| 17 | 17 | 1 | 17 |
| 65536 | 65537 | 1 | 1 |
| 2 | 2 | 2 | 2 |
| -1 | -65536 | 0 | 0 |

Two takeaways from the table:

**Same bucket does not imply same hash code.** Internal hashes 1, 17, and 65537 all land in bucket 1 when `n = 16`.

**The bucket depends on capacity.** Hash 17 is in bucket 1 when `n = 16` but moves to bucket 17 when `n = 32`. A bucket index cannot be treated as a fixed property of a key.

For `-1`, the unsigned right shift brings the 16 high 1-bits down to `65535`; XOR yields `-65536`. Bitwise AND with `15` or `31` still produces a valid index of `0`. There is no need to call `Math.abs` to handle negative numbers in this formula.

Do not replace the formula above with `Math.abs(hashCode) % n` and claim it accurately describes OpenJDK. That is a different algorithm, and `Math.abs(Integer.MIN_VALUE)` remains negative because the `int` range does not contain the corresponding positive value. When using a real `HashMap`, let the implementation compute the slot.

The `bucket` method in the demo program only simulates the formula for the chosen capacities 16 and 32. It checks the power-of-two precondition and does not use reflection to read the private table of a `HashMap` instance.

## 6. Collisions: Reaching the Right Bucket Is Still Not Finding the Key

Suppose four keys are added in the order A, B, C, D:

~~~text
A: rawHash 1      -> mixed 1
B: rawHash 17     -> mixed 17
C: rawHash 1      -> mixed 1
D: rawHash 65536  -> mixed 65537
~~~

With capacity 16, all four land in bucket 1. A corresponding node-chain diagram for this small example:

~~~text
table[0]  -> empty
table[1]  -> [hash=1, A, alpha]
            -> [hash=17, B, beta]
            -> [hash=1, C, gamma]
            -> [hash=65537, D, delta]
table[2]  -> empty
...
table[15] -> empty
~~~

This diagram illustrates the chain structure of the example against the OpenJDK implementation; it is not a direct dump of private fields. `HashMap` makes no API guarantee about the insertion order of internal chains or iteration order.

You can distinguish two levels of collision:

1. Different internal hashes that fall into the same bucket, such as A and B.
2. Identical internal hashes where the keys are not equal, such as A and C.

The first level can reject candidates early by comparing internal hashes. The second level also requires distinguishing by the key itself. Therefore, matching bucket indices—and even matching hash codes—are not enough to conclude that the mapping has been found.

`HashMap` does not overwrite every key that shares a bucket. A mapping's value is replaced only when the key is recognized as equal to an existing key. If A and C differ according to `equals`, they coexist even if their hash codes are identical.

## 7. The get(key) Procedure on a Chained Bucket

You can read the procedure in these steps:

1. Locate the table; if a table with a valid capacity exists, compute the target slot.
2. Fetch the first node of the selected bucket.
3. If the bucket is empty, conclude the key is not found here.
4. If a node exists, compare the internal hash stored in the node with the hash of the lookup key.
5. Only when the hashes match do we check reference equality or key `equals`.
6. If the current node does not match, inspect the subsequent candidates in the bucket.
7. If a matching node is found, return its value; if all candidates are exhausted without a match, return `null`.

The key check at a node has two main branches:

~~~text
internal hash matches
    and
    (stored key is the same reference as the lookup key
     or lookup key is non-null and equals the stored key)
~~~

This is a logical model, not a requirement that an application observe a fixed number of `equals` calls. `HashMap` is free to skip equality checks when an earlier filter has already ruled out a candidate.

### Finding the Exact Stored Object A Again

The internal hash matches and the key reference matches right at the first node. There is no need to call `A.equals(A)` to know it is the same object.

### Finding a New Object A Equal to the Stored Key

The two references differ while the hash codes match, so `equals` must be used to confirm it is the same key. The result is still `alpha` when the key contract is upheld.

### Finding C Using a New Object

Node A has the same internal hash 1, but `equals` returns `false`. Node B has internal hash 17, which differs from 1, so `equals` does not need to be called on B. Node C has hash 1 and its key equals the lookup key, so `gamma` is found.

### Not Found Even Though the Bucket Contains Data

For key X with internal hash 1 that differs from A and C, the algorithm must reject the candidates whose hashes match. For key Z with hash 33, bucket 1 still holds data, but no node has hash 33, so it can conclude there is no match without calling `equals` for those keys.

Therefore, a trace showing "no `equals` calls were made" does not prove the bucket is empty. It may also contain nodes that were filtered out by their hash code.

### If the Bucket Is a Tree

Some buckets may be converted into a tree structure instead of always being traversed as a chain. In that case, lookup follows the tree-node mechanism. Do not describe every `HashMap` as an array of linked lists forever, and do not treat the chain trace from a small example as a guarantee for treeified buckets.

## 8. Java 17+ Program to Observe hashCode and equals

The file `HashMapLookupDemo.java` uses an immutable `Key` record. In this mechanism-learning example, both `id` and `rawHash` are data participating in `equals`; `hashCode` returns the `rawHash` field deliberately chosen to produce collision cases.

This design preserves the contract: if two `Key` instances are equal, their `rawHash` values are equal. Different `id` values can still share the same `rawHash`. It is an experimental tool, not a recommendation to put a "user-supplied hash code" into every business key.

The `events` list only records calls in a single-threaded program. Trace recording does not participate in `equals` decisions; this is not a thread-safe logging mechanism shared across threads.

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class HashMapLookupDemo {
    private static final List<String> events = new ArrayList<>();

    record Key(String id, int rawHash) {
        Key {
            Objects.requireNonNull(id, "id");
        }

        @Override
        public int hashCode() {
            events.add("hash(" + id + ")=" + rawHash);
            return rawHash;
        }

        @Override
        public boolean equals(Object other) {
            if (!(other instanceof Key that)) {
                return false;
            }
            events.add("equals(" + id + "," + that.id + ")");
            return rawHash == that.rawHash && id.equals(that.id);
        }
    }

    static int spread(int rawHash) {
        return rawHash ^ (rawHash >>> 16);
    }

    static int bucket(int mixedHash, int capacity) {
        if (capacity <= 0 || (capacity & (capacity - 1)) != 0) {
            throw new IllegalArgumentException("capacity must be a power of two");
        }
        return mixedHash & (capacity - 1);
    }

    static void lookup(Map<Key, String> map, String label, Key key) {
        events.clear();
        String value = map.get(key);
        System.out.println(label + " get=" + value + " events=" + events);
    }

    public static void main(String[] args) {
        for (int raw : new int[] {1, 17, 65536, 2, -1}) {
            int mixed = spread(raw);
            System.out.println("raw=" + raw + " mixed=" + mixed
                    + " bucket16=" + bucket(mixed, 16)
                    + " bucket32=" + bucket(mixed, 32));
        }

        Key a = new Key("A", 1);
        Key b = new Key("B", 17);
        Key c = new Key("C", 1);
        Key d = new Key("D", 65536);
        Map<Key, String> map = new HashMap<>(16);
        map.put(a, "alpha");
        map.put(b, "beta");
        map.put(c, "gamma");
        map.put(d, "delta");

        System.out.println("initial size=" + map.size());
        lookup(map, "same reference A", a);
        lookup(map, "equal new A", new Key("A", 1));
        lookup(map, "equal new C", new Key("C", 1));
        lookup(map, "missing same hash X", new Key("X", 1));
        lookup(map, "missing other hash Z", new Key("Z", 33));
        lookup(map, "empty bucket E", new Key("E", 2));

        String previous = map.put(new Key("B", 17), "beta2");
        System.out.println("replace B previous=" + previous
                + " size=" + map.size());
        lookup(map, "B after replacement", new Key("B", 17));

        map.put(null, "nil");
        lookup(map, "null key", null);
        System.out.println("size with null key=" + map.size());

        map.put(new Key("C", 1), null);
        String cValue = map.get(new Key("C", 1));
        boolean cPresent = map.containsKey(new Key("C", 1));
        String missingValue = map.get(new Key("missing", 1));
        boolean missingPresent = map.containsKey(new Key("missing", 1));
        System.out.println("C value=" + cValue + " present=" + cPresent);
        System.out.println("missing value=" + missingValue
                + " present=" + missingPresent);

        Key aCopy = new Key("A", 1);
        Key cCopy = new Key("C", 1);
        events.clear();
        System.out.println("A equals new A=" + a.equals(aCopy));
        System.out.println("A equals C=" + a.equals(cCopy));
        System.out.println("A raw hash equals C raw hash="
                + (a.rawHash() == c.rawHash()));
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 HashMapLookupDemo.java
java HashMapLookupDemo
~~~

Use JDK 17 or newer supporting target release 17. The program is compatible with Java 17 APIs and syntax. The trace below is referenced against the chained lookup path in the OpenJDK 17 source code; exact call-count details are not a universal guarantee across all `HashMap` implementations or versions.

Exact stdout:

~~~text
raw=1 mixed=1 bucket16=1 bucket32=1
raw=17 mixed=17 bucket16=1 bucket32=17
raw=65536 mixed=65537 bucket16=1 bucket32=1
raw=2 mixed=2 bucket16=2 bucket32=2
raw=-1 mixed=-65536 bucket16=0 bucket32=0
initial size=4
same reference A get=alpha events=[hash(A)=1]
equal new A get=alpha events=[hash(A)=1, equals(A,A)]
equal new C get=gamma events=[hash(C)=1, equals(C,A), equals(C,C)]
missing same hash X get=null events=[hash(X)=1, equals(X,A), equals(X,C)]
missing other hash Z get=null events=[hash(Z)=33]
empty bucket E get=null events=[hash(E)=2]
replace B previous=beta size=4
B after replacement get=beta2 events=[hash(B)=17, equals(B,B)]
null key get=nil events=[]
size with null key=5
C value=null present=true
missing value=null present=false
A equals new A=true
A equals C=false
A raw hash equals C raw hash=true
~~~

### How to Read the Evidence

The first five lines are outputs from the bucket model calculation for two capacities, not from reading the `Map`'s actual capacity through a public API.

`same reference A` records only one `hashCode` call. `equal new A` also includes an `equals` call. The pair of `A` labels in `equals(A,A)` are two `id` values with the same letter `A`, not a claim that the two objects share the same reference.

`equal new C` checks `equals` against A and then C; B is skipped due to a different hash code. `missing other hash Z` has no `equals` calls even though its modeled bucket is also 1. `empty bucket E` also has no `equals` calls, but for a different reason: the selected slot has no candidates.

`replace B` returns the previous value `beta` and the size remains 4, confirming that replacing a value for an equal key does not add a duplicate key. The `null` key is looked up without invoking any method on a `Key` object. The last two lines with `null` values show why you must distinguish "found a node holding `null`" from "found no node".


## 9. Null in Lookup Results

On the `get(key)` path, there are two different internal outcomes: no matching node is found, or a matching node is found whose value is `null`. The `get` API can return `null` in both cases. When you need to know whether a key is present, use `containsKey` instead of inferring solely from `get`.

~~~text
C → null, already in Map         get(C) → null; containsKey(C) → true
X not in Map                     get(X) → null; containsKey(X) → false
~~~

The `null` key is also supported by `HashMap`: the OpenJDK implementation chooses internal hash 0 to locate it, yet still checks for the exact key in the bucket. The rule of at most one `null` key, multiple `null` values, and the behavior of update methods are the focus of a separate lesson on null policy.

## 10. Mutating Keys Can Break the Lookup Path

When a mapping is inserted, the node stores the computed hash code; when looking it up later, `HashMap` computes the hash from the query key. If fields participating in `hashCode` or `equals` are modified while the object is serving as a key, the lookup path may fail to recognize the old mapping.

For example, in the OpenJDK model with a 16-bucket table: the node stored hash 1, and after mutating the key, the query hash becomes 17. Both still select bucket 1, yet the stored hash and the lookup hash differ, so even the exact same key reference can be rejected before the equality check. Do not rely on any specific failure outcome for a key that violates the contract; design stable identity data instead. The lesson on mutable keys analyzes these bugs and their fixes in greater detail.

## 11. Resizing Changes Bucket Positions

The bucket index depends on the current table capacity. For instance, internal hash 17 selects bucket `17 & 15 = 1` at capacity 16, but selects `17 & 31 = 17` at capacity 32. When the table grows, the implementation must relocate the mappings; application code must never store a self-computed bucket index as a fixed identifier.

Increasing capacity can separate keys with different hashes that happened to share a bucket, but it cannot separate keys that have identical internal hashes. The expansion threshold, bucket splitting, and resize cost are covered in detail in the capacity/load factor lesson.

## 12. Cost of a Single Lookup

With a suitable hash distribution and reasonable `hashCode`/`equals` cost, lookup has expected constant-time performance. That does not promise that every `get` call performs exactly one comparison or takes the same amount of time.

~~~text
lookup cost = compute hashCode + select bucket + inspect candidates + compare equals when needed
~~~

A chained bucket with `L` nodes may need to inspect up to `L` candidates; different hash codes can be rejected before `equals`. In a treeified bucket, the lookup path also depends on implementation conditions and key comparability. The call-counting example above only demonstrates a specific execution trace, not a timing benchmark. The performance and bucket-treeification lessons examine these bounds in depth.

## 13. Diagnosing Lookup Anomalies

| Wrong observation or assumption | More accurate check |
| --- | --- |
| `hashCode` is the bucket itself | Hash mixing and table capacity also determine the index |
| Two keys in the same bucket must be the same mapping | Compare internal hashes and keys via `equals` |
| Same `hashCode` means `equals` must be true | Different keys are allowed to collide |
| No `equals` calls means the bucket is empty | Candidates may have been rejected by different hash codes |
| Using the same mutated key reference will always `get` it | The hash stored in the node may differ from the new hash |
| `get` returning `null` definitely means the key is absent | `containsKey` distinguishes a `null`-valued mapping from absence |

When a key that ought to be present is not found, check the identity definition, `equals`/`hashCode` consistency, whether the key was mutated after insertion, and the distinction between `null` and absence. You do not need reflection to read private fields in order to diagnose these issues.

## 14. Exercises and Solutions

### Exercise 1 — Distinguishing size and capacity

A `HashMap` has four mappings, and the modeled table has capacity 16. Can you conclude there are 12 empty buckets?

**Solution:** No. The four mappings may land in the same bucket or across different buckets. Only if they are in four distinct buckets are there 12 empty slots; if all four are in one bucket, there are 15 empty slots. `size` counts mappings, not occupied buckets.

### Exercise 2 — Computing the index

The internal hash is 17. For capacities 16 and 32, what indices are computed in the OpenJDK model?

**Solution:** `17 & 15 = 1` and `17 & 31 = 17`. The same hash does not imply a fixed index when capacity changes.

### Exercise 3 — Same bucket, different hashes

A has `mixedHash` 1 and B has `mixedHash` 17. In a 16-bucket table, which bucket do they share? When looking up a key with hash 1, is `equals` required to be called on B?

**Solution:** They share bucket 1. Calling `equals` on B is not required in the described lookup path, because hash 17 stored in B's node differs from the lookup hash 1 and can rule B out early.

### Exercise 4 — Same hash, different keys

A and C both have `hashCode` 1, but `equals` is false. Does inserting A and then C overwrite A's value?

**Solution:** Not merely because their hash codes are the same. They are two distinct keys under the chosen contract, so they can coexist. Only when a key is recognized as equal does `put` replace the value for that mapping.

### Exercise 5 — Reading the lookup trace for C

Why does the program print `equals(C,A)` and then `equals(C,C)` without `equals(C,B)`?

**Solution:** A and C have internal hash 1, so key equality must be checked; B has hash 17, so it is rejected before calling `equals`. The two `C`s in the second trace entry are the identical `id` values of two objects with different references.

### Exercise 6 — Does no equals call prove no candidates?

Looking up Z with hash 33, which shares the modeled bucket with A/B/C/D at capacity 16, only logs `hashCode`. Is the table broken?

**Solution:** No. The bucket contains nodes, but none of them holds internal hash 33, so the nodes can be rejected without calling `equals`. The lookup path is working properly via the hash-code filter.

### Exercise 7 — New key equal to an old key

`Key("A", 1)` is stored. When using a new object `Key("A", 1)` for `get`, does it need the same reference address?

**Solution:** No. The two `Key` objects are equal according to `equals` and have consistent hash codes; `HashMap` can find the entry through the equality check when the two references differ. Using `==` to decide whether a key can be looked up would bypass this mechanism.

### Exercise 8 — Two null results

C is mapped to `null`, while X is absent. Both `get(C)` and `get(X)` return `null`. What result distinguishes them, and how does this relate to internal nodes?

**Solution:** `containsKey(C)` is `true` and `containsKey(X)` is `false` when the source is unchanged. C finds a node whose value is `null`; X has no matching node.

### Exercise 9 — Negative hashes and Math.abs

Do you need to convert a negative hash code to positive before using `HashMap`? Why should you not simulate it yourself with `Math.abs` followed by modulo?

**Solution:** No. `HashMap` handles `int` values through its internal mechanism; masking with `n - 1` produces a valid index in this model. `Math.abs` followed by modulo is a different formula, and `Math.abs` of `Integer.MIN_VALUE` is still negative.

### Exercise 10 — Mutated key without changing bucket

When inserted, a key had internal hash 1; later, the key's data is modified so its hash becomes 17. Both hashes still map to bucket 1 at capacity 16. Is `get` guaranteed to find it since it is in the same bucket?

**Solution:** No. The node still holds hash 1 and can be rejected by the lookup's hash 17 before checking reference equality or `equals`. This is a reason to avoid mutable keys, not a valid state for an application to depend on a specific outcome.

### Exercise 11 — Table growth and identical hash codes

There are many distinct keys, but all of their `hashCode` values are 7. Will simply increasing the table capacity automatically spread them across multiple buckets?

**Solution:** Not under the formula discussed: the same initial hash produces the same mixed hash and the same index at every capacity. You need to revisit the hashing logic and key model, not just increase the number of slots.

### Exercise 12 — Extending the experiment

Add two keys with different `rawHash` values that land in the same bucket at capacity 16, then look up one of them using a new object equal to that key. What must you preserve for the experiment to be meaningful?

**Solution:** You could choose `rawHash` 3 and 19, which yield mixed hashes 3 and 19 respectively and both land in bucket 3 at capacity 16. Use two distinct `id` values, keep `rawHash` in the equality data as the program's `Key` does, and do not mutate the keys after insertion. Observe the trace to see that a candidate with a different hash can be skipped. Do not infer that call counts or node ordering are an API guarantee across all versions.

## 15. Self-Check on the Key Lookup Model

Try explaining a `get` call in three layers: narrowing the scope with the hash code, filtering and comparing keys inside the bucket, and then reading the value of the matched node. If you blur these three layers together, it is easy to confuse a bucket with a key, or a `null` value with a missing key.

When designing keys, prioritize the correctness of `equals`/`hashCode` and the stability of identifying data. When evaluating performance, consider both bucket distribution and the cost of the key's methods. When reading source code, note the version and separate implementation details from the public contract.

Buckets narrow down where to search; hash codes filter candidates; key identity determines which mapping actually matches. All three roles working together form `HashMap`'s key lookup process.
