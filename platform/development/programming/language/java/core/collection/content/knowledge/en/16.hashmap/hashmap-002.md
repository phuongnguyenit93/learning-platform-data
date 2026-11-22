# Coordinating hashCode and equals on put, get, remove

## 1. Two tasks: locating candidate regions and identifying the exact key

A HashMap needs to answer the question: "Is the queried key the same logical key as an already stored mapping?". If it had to compare against every key on every read, lookup would take a lot of effort when the data is large.

HashMap coordinates two tools:

- `hashCode()` helps direct the search to a candidate storage region.
- `equals()` determines logical equality when candidate keys need to be distinguished.

For example, consider a key object carrying customer code C01. Two separately created objects that both represent C01 must be able to find the same mapping, if the application's identity model specifies so.

Conversely, two customers C01 and C02 may happen to produce the same hash code. HashMap must still keep them as two distinct keys if equals returns false.

This article explains the path of put, get, and remove, distinguishes types of collisions, and shows why a key that violates the contract or is mutated after insertion easily causes lookups to no longer behave as expected.

## 2. The contract must be right before considering the algorithm

### 2.1. Equality implies the same hash code

Two important rules:

```text
a.equals(b) == true  →  a.hashCode() == b.hashCode()
same hashCode        ↛  equals must be true
```

When information relevant to equality does not change, calls to hashCode on the same object within a single execution must also be consistent. A hashCode that changes on its own based on call count or randomness will make the lookup path unstable.

The second direction is not guaranteed. A hash code is an integer with a finite value range, not a unique identifier that cannot collide.

A hashCode function that always returns 7 can still satisfy the condition "two equal keys have the same hash code". However, that distribution is poor and can make lookups slow. Being contract-compliant and having good performance are two requirements that need to be distinguished.

The original contract is described in [Object.equals and Object.hashCode Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).

### 2.2. equals must be a consistent relation

When building value-based keys, equals needs to satisfy properties such as reflexivity, symmetry, transitivity, consistency when identity information does not change, and returning false when compared with null.

Do not write a class where a equals b but b does not equal a and expect HashMap to fix that contradiction. The direction in which equals is called can make the result confusing if the relation itself is broken.

If you override equals, you must also ensure hashCode is consistent with it. Overriding only hashCode while still using Object's reference equality does not automatically create a content-based key.

### 2.3. Same reference vs. same logical key

`a == b` checks whether two references point to the same object. `a.equals(b)` can define that two different objects still represent the same logical identity.

A regular class that has not overridden equals inherits reference-equality behavior from Object. In that case, two objects with identical fields are not necessarily the same key.

Records can help when the record's components are precisely the identity data needed. A record's default equality and hash code are based on its components; you still need to care about whether the data inside is mutable.

## 3. From hashCode to bucket in OpenJDK

### 3.1. A bucket is a candidate container

HashMap organizes a table of containers, commonly called **buckets**. A bucket can hold zero, one, or multiple mappings.

Model:

```text
key to operate on
    ↓ hashCode
key's hash code
    ↓ bit mixing
hash used in the structure
    ↓ index selection
candidate bucket
    ↓ check hash and key
matching mapping or not found
```

HashMap does not use a hash code as a single slot that can only hold one entry. Collisions are a normal case that the structure must handle.

### 3.2. The formula is an implementation detail, not an API for callers to compute

In OpenJDK 17u, for a non-null key, a mixing operation is used of the form:

```java
int h = key.hashCode();
int hash = h ^ (h >>> 16);
```

When the table has been allocated and has length n as a power of 2:

```java
int index = (n - 1) & hash;
```

These are illustrative expressions from the internal mechanism, not a standalone program. Callers of HashMap do not need to compute the index themselves before put/get/remove.

You can refer to the [OpenJDK 17u HashMap source code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/HashMap.java). The public contract for keys and map operations does not force every implementation version to keep the exact same internal formula.

A hash code can be a negative number. Key authors do not have to turn hashCode into a non-negative number for HashMap to use it. Nor should Math.abs be used as a mandatory requirement of the hashCode contract.

### 3.3. Same bucket does not necessarily mean same hash

Suppose n is 16 and the mixed hashes are 1 and 17:

```text
15 & 1  = 1
15 & 17 = 1
```

Both map to bucket 1, yet the two hashes are still different. The table only uses part of the information to select the container; each node also stores its hash to help filter candidates.

Therefore, you must distinguish:

| Relationship | What can be inferred |
| --- | --- |
| Two keys are equal and contract-compliant | They have the same hashCode and are routed consistently to find each other |
| Same hashCode | Could still be two different keys |
| Same mixed hash | Key equality check may still be needed |
| Same bucket index | Even less sufficient to conclude same key |

"Bucket collision" is broader than the case of "two keys returning the same hashCode".

## 4. How a candidate is confirmed

In the normal OpenJDK processing path, the check condition has the conceptual form:

```text
hash stored in node equals the searched hash
AND
(
    stored key is the same reference as the searched key
    OR
    searched key is non-null and equals the stored key via equals
)
```

Points to keep in mind:

1. Hash filters regions and candidates; it does not replace the definition of equality.
2. Reference equality can serve as a fast confirmation path.
3. If equals needs to be called, key comparison happens after the routing conditions have matched.
4. A lookup does not mean equals must be called against every stored key.

In typical OpenJDK lookup paths, equals is called from the operation's key to the stored key, in the form `lookupKey.equals(storedKey)`. When equals properly satisfies symmetry, that direction does not change the logical conclusion.

Do not write business tests that require an exact number of equals/hashCode calls or a fixed internal call order. The structure may optimize, change the lookup path, or treeify buckets when appropriate.

A bucket with multiple elements is not always just a linked list. List/tree details help the implementation handle collisions, but do not change the meaning of "same logical key under the contract".

## 5. put: updating an existing key or adding a different key

### 5.1. Key already exists by equality

Suppose we have stored:

```text
Key("A") → first-A
```

Calling put with another Key("A") object that is equal and has a contract-compliant hash:

```text
put(new Key("A"), updated-A)
```

HashMap finds the candidate mapping, confirms it is the same key, and replaces the value. Size does not increase. The returned value is first-A, which is the value before the operation.

There is no requirement to keep the exact original reference in the calling code in order to update it. That is the benefit of the value-based key model.

### 5.2. Same hash but equals is false

Suppose Key("A") and Key("B") both have hashCode 7, but are not equal. Putting B must keep a separate mapping:

```text
Key("A") → first-A
Key("B") → first-B
```

B does not overwrite A just because they share the same hash or bucket. HashMap handles the collision and adds an entry for the other key.

### 5.3. Value does not determine key uniqueness

HashMap selects mappings by key. Two equal values do not merge two keys; two different values do not split an already equal key into two keys.

If put appears to "lose" data, check the key's equals/hashCode rules and identity domain rather than looking only at the value being written.

Put behavior and key uniqueness can be referenced in [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

## 6. get: same identification path, but read-only

Get performs candidate lookup by hash and key identification. If found, it returns the entry's value. If not found, it returns null.

A newly created key object can still retrieve data if it equals the stored key and has the matching hash code. Conversely, an object with the same hash that does not equal the key is not a match.

Given a map with keys A and B sharing the same hash:

```text
get(Key("A")) → value of A
get(Key("B")) → value of B
get(Key("C")) → not found, if C differs from both A and B
```

Get does not look up by the value's hashCode. If you need to find keys by value, that is a different problem from HashMap's key lookup path.

### Null alone does not prove a key is absent

HashMap allows null values. Therefore, get returning null can mean:

- There is no matching entry.
- There is a matching entry, but its value is null.

ContainsKey helps distinguish existence in contexts where you need to know that. Finding the right key and having a non-null value are two separate matters.

## 7. remove: finding the right key and detaching its mapping

The single-argument remove uses the key to find the entry as above, then removes the matching mapping and returns the old value.

If A and B have the same hash but are not equal, remove(A) must not delete B just because B is in the same bucket. If the searched key is not present, remove returns null and does not delete other keys.

With a null value, remove can also return null after successfully removing the entry. Do not rely solely on a null return value to conclude that the operation did not find the key.

The `remove(key, expectedValue)` variant adds a condition on the value after locating the mapping by key. That does not turn the key lookup process into a lookup by the value's hashCode.

If remove fails because the key mutated itself or violated the contract, calling it repeatedly with similar-looking objects will not fix the key design. You need to inspect where the identity data and hash code are being computed from.

## 8. Runnable program: valid collisions and equal keys

Save as **HashLookupDemo.java**:

```java
import java.util.HashMap;
import java.util.Map;

public class HashLookupDemo {
    record CollisionKey(String code) {
        @Override
        public int hashCode() {
            return 7;
        }
    }

    public static void main(String[] args) {
        CollisionKey a = new CollisionKey("A");
        CollisionKey equalA = new CollisionKey("A");
        CollisionKey b = new CollisionKey("B");
        Map<CollisionKey, String> map = new HashMap<>();

        System.out.println("same reference A: " + (a == equalA));
        System.out.println("equal logical A: " + a.equals(equalA));
        System.out.println("A and B same hash: " + (a.hashCode() == b.hashCode()));
        System.out.println("A equals B: " + a.equals(b));
        System.out.println("first put A old: " + map.put(a, "first-A"));
        System.out.println("first put B old: " + map.put(b, "first-B"));
        System.out.println("size with collision: " + map.size());
        System.out.println("get equal A: " + map.get(equalA));
        System.out.println("equal A put old: " + map.put(equalA, "updated-A"));
        System.out.println("size after equal-key put: " + map.size());
        System.out.println("get original A: " + map.get(a));
        System.out.println("get B: " + map.get(new CollisionKey("B")));

        System.out.println("remove equal A: " + map.remove(new CollisionKey("A")));
        System.out.println("A still present: " + map.containsKey(a));
        System.out.println("B still present: " + map.containsKey(b));
        System.out.println("remove missing C: " + map.remove(new CollisionKey("C")));
        System.out.println("size after removals: " + map.size());

        map.put(null, "first-null");
        System.out.println("get null key: " + map.get(null));
        System.out.println("second null-key put old: " + map.put(null, "second-null"));
        System.out.println("size with null key: " + map.size());
        System.out.println("remove null key: " + map.remove(null));

        CollisionKey n = new CollisionKey("N");
        map.put(n, null);
        System.out.println("get mapped null: " + map.get(new CollisionKey("N")));
        System.out.println("contains mapped-null key: " + map.containsKey(n));
        System.out.println("remove mapped null old: " + map.remove(new CollisionKey("N")));
        System.out.println("mapped-null key remains: " + map.containsKey(n));
        System.out.println("final size: " + map.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 HashLookupDemo.java
java HashLookupDemo
```

Exact stdout:

```text
same reference A: false
equal logical A: true
A and B same hash: true
A equals B: false
first put A old: null
first put B old: null
size with collision: 2
get equal A: first-A
equal A put old: first-A
size after equal-key put: 2
get original A: updated-A
get B: first-B
remove equal A: updated-A
A still present: false
B still present: true
remove missing C: null
size after removals: 1
get null key: first-null
second null-key put old: first-null
size with null key: 2
remove null key: second-null
get mapped null: null
contains mapped-null key: true
remove mapped null old: null
mapped-null key remains: false
final size: 1
```

CollisionKey is a record with a `code` component. The record's default equals distinguishes A from B and recognizes two A instances as equal. HashCode intentionally always returns 7 to create observable collisions.

The constant hash function here is for experimentation; it is not a recommended hash distribution for application keys.

The results can be explained by the same model:

- `a` and `equalA` have different references but are logically equal keys.
- A and B have the same hash but are two distinct keys, so size is 2.
- Putting `equalA` replaces A's value and keeps size unchanged.
- Get/remove using a new A instance still finds the right mapping.
- Removing A does not affect B.
- The null key is stored/updated/removed as a separate key supported by HashMap.
- A null value is still a real mapping, and removing a null value can return null even though the key was removed.

The programs in this article were compiled with `--release 17` and run on OpenJDK 24.0.2. That flag checks the target Java 17 language/API and generates corresponding bytecode; the JVM running the examples is still the version noted.

## 9. Null key takes a separate branch

HashMap accepts one null key. Because `null.hashCode()` cannot be called, the OpenJDK implementation uses hash 0 for the null-key branch.

This does not mean bucket 0 can only hold null. A non-null key with a matching hash can still share the bucket, but key identification must distinguish it from null.

Under a valid equals contract, a non-null object must not consider null equal to itself. Therefore, a normal key with hash 0 does not automatically become the null key.

Multiple `put(null, value)` calls update the same null mapping rather than creating multiple null keys. Other map classes may forbid null; this is HashMap's policy, not something every Map allows.

## 10. Two key-design bugs and observable symptoms

### 10.1. Intended equals, but inconsistent hashCode

Suppose two objects with the same code `"same"` have equals returning true, but hashCode returning 1 and 2 respectively.

The key definition has violated the contract. HashMap may route operations to different regions and not call equals between the two objects as the author expects. Get with an "equal" instance may fail to find it; put may leave entries that appear to duplicate the same logical identity.

Do not fix this by forcing HashMap to scan every key. You need to fix hashCode so that all equal keys have the same hash code per the contract.

### 10.2. Key mutated after being stored

Suppose a key has id 1 when inserted into the map, and hashCode is based on id. Later, id is changed to 17.

The node was placed into the structure according to the hash at insertion time. A new get/remove operation computes the hash from the key's new state. The two states are no longer consistent with each other.

Even holding the exact same reference is not a guarantee that saves the lookup: the hash filter may not even reach the reference-equality check.

In OpenJDK's 16-slot table model, hashes 1 and 17 may even land in the same bucket, yet the full hash stored in the node and the searched hash still differ. Thus, "still in the same bucket" is also not enough for a mutated key to work properly.

Map warns that behavior is undefined if a key is mutated in a way that affects equality comparisons while it is a key in the map. See [Map Java 17 mutable key note](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

## 11. Bug observation program: not a contract to rely on

Save as **BrokenHashKeyObservation.java**:

```java
import java.util.HashMap;
import java.util.Map;

public class BrokenHashKeyObservation {
    static final class BadHashKey {
        private final String code;
        private final int forcedHash;

        BadHashKey(String code, int forcedHash) {
            this.code = code;
            this.forcedHash = forcedHash;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BadHashKey key && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return forcedHash;
        }
    }

    static final class MutableKey {
        int id;

        MutableKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key && id == key.id;
        }

        @Override
        public int hashCode() {
            return id;
        }
    }

    public static void main(String[] args) {
        BadHashKey first = new BadHashKey("same", 1);
        BadHashKey equalButDifferentHash = new BadHashKey("same", 2);
        Map<BadHashKey, String> invalid = new HashMap<>();
        invalid.put(first, "stored");

        System.out.println("bad keys equals: " + first.equals(equalButDifferentHash));
        System.out.println("bad keys same hash: "
                + (first.hashCode() == equalButDifferentHash.hashCode()));
        System.out.println("observed bad lookup: " + invalid.get(equalButDifferentHash));
        invalid.put(equalButDifferentHash, "second");
        System.out.println("observed bad map size: " + invalid.size());

        MutableKey key = new MutableKey(1);
        Map<MutableKey, String> mutable = new HashMap<>(16);
        mutable.put(key, "payload");
        System.out.println("before key change: " + mutable.get(key));
        key.id = 17;
        System.out.println("observed changed-key get: " + mutable.get(key));
        System.out.println("observed changed-key remove: " + mutable.remove(key));
        System.out.println("observed changed-key size: " + mutable.size());
        System.out.println("observed entry still holds reference: "
                + (mutable.keySet().iterator().next() == key));
    }
}
```

Run command:

```shell
javac --release 17 -encoding UTF-8 BrokenHashKeyObservation.java
java BrokenHashKeyObservation
```

Stdout observed on the test environment:

```text
bad keys equals: true
bad keys same hash: false
observed bad lookup: null
observed bad map size: 2
before key change: payload
observed changed-key get: null
observed changed-key remove: null
observed changed-key size: 1
observed entry still holds reference: true
```

BadHashKey intentionally violates the contract: equals only checks `code`, while hashCode also depends on a separately passed number. Two `"same"` keys have equals true but different hashes.

MutableKey intentionally modifies `id` after insertion. In this observation, get and remove fail to find it, yet size remains 1 and the entry still holds that exact key reference. This helps show that data is not necessarily removed from the structure just because a lookup fails to find it.

**These observed lines illustrate consequences on the stated environment, not guaranteed behavior for contract-violating or mutated keys across all Java 17+ runtimes.** Do not write production tests requiring HashMap to reproduce those exact failure outputs.

Do not use these two classes as proper design templates. They are experiments to understand why the requirements on keys must be respected.

## 12. Designing a key that works for all three operations

### 12.1. Choosing the right identity components

Example of a composite key:

```java
// Illustrative declaration placed inside a class:
record CustomerKey(String organization, long customerId) {}
```

Two CustomerKey instances with the same `organization` and `customerId` are the same logical key. Different organizations can represent two different customers even with the same `customerId` number.

These components must accurately reflect the data domain, rather than being chosen arbitrarily to produce different hashes. A good hash function cannot fix an equals model that merges two distinct entities into one.

### 12.2. Keeping identity information stable

Prefer String, numbers, enums, or suitable, stable value types as key components.

A `final` field only prevents reassigning the field's reference; it does not automatically make the object inside immutable. If a key contains a mutable List and equals/hashCode depends on the List's contents, modifying the List can still change the key's meaning.

When identity must change, design a workflow to remove the mapping under the old key and add the mapping with the new key according to application policy. Do not mutate a key already inside the map and expect resizing to fix everything on its own.

### 12.3. Do not include frequently changing fields in the key if they are not identity

Display names, counters, session state, or update timestamps can change during use. If they are not part of the identity that needs to be distinguished, they should not be included in the key's equals/hashCode just because they are present in the class.

You can keep the identifier as the key and place mutable data in the value. When the value changes, the key identification path remains stable.

However, if the business logic genuinely requires a full snapshot as a key, you must create a stable snapshot value and understand that meaning. There is no rule that every multi-field class must compare all fields or only one field; the identity model decides.

## 13. Performance and testing: do not test an optimization detail by mistake

HashMap has good lookup performance when hash codes are distributed appropriately. Many keys sharing the same hash increase the work of distinguishing candidates. Collision-handling mechanisms can help in some cases, but they do not turn a constant hash function into a good choice for all data.

A complex equals/hashCode call also has its own cost. Do not treat "O(1) average lookup" as zero work or always fast regardless of how the key is defined.

Meaningful tests for a key type include:

- Two objects with the same identity: equals is true and hashCode values are equal.
- Two different identities: not mistakenly treated as equal by equals; hashes are still allowed to collide.
- Put with an equivalent key updates one mapping, and size does not increase.
- Get and remove with an equivalent key both find the right mapping.
- Colliding keys are still stored/found/removed independently.
- Identity components are not mutated during their lifecycle as a key.

There is no need to require every pair of distinct keys to have different hashCode values. Nor should you require hashCode to be identical across all program runs if that type has no such contract.

Do not rely on HashMap iteration order or exact equals call counts to validate the key model. Test business outcomes and the equality contract instead.

HashMap is also not thread-safe for concurrent updates on its own. A correct equals/hashCode does not replace the need to choose an appropriate structure or synchronization when multiple threads modify data concurrently.

## 14. Common mistakes and how to diagnose them

| Symptom | Cause to check | How to reason about the fix |
| --- | --- | --- |
| Two keys with the same hash code appear to overwrite each other | Confusing hash with identity | Check equals, not just hashCode |
| Creating a new key object and get returns nothing | Missing value-based equals or mismatched hash | Check both methods |
| Equals is true, but map has two seemingly duplicate entries | HashCode may violate the contract | Ensure equality implies the same hash code |
| Put updates value and size does not increase | Equivalent key already exists | This may be expected Map behavior |
| Same reference, yet get/remove fails | Key's identity information changed | Keep keys stable |
| Data still appears when iterating, yet get misses | Possibly a mutable key | Do not treat remaining entry as proof the lookup path is still valid |
| Remove returns null, mistaken for not deleted | Old value could be null | Distinguish key existence from value |
| Same bucket, assumed equals must be called | Node also has a hash check | Separate bucket index from full hash |
| Constant hash function "is valid so it must be fast" | Contract-compliant, but poor distribution | Design a hash suited to the data |
| Key has a final List, yet hash still changes | Internal object contents changed | Consider deep stability of identity data |

## 15. Self-check exercises with solutions

### Exercise 1: Same hash, different keys

A and B have hashCode 7, but equals is false. If both are put into a HashMap, must it keep only one entry?

**Solution:** No. Collision is not equality. The map keeps two mappings if the two keys are distinct under the contract.

### Exercise 2: Different references, same key

A and A2 are different objects, equals is true, and they have the same hashCode. Put A, then put A2 with a new value. What happens to size and the value for A?

**Solution:** Still one mapping for that logical key; `get(A)` returns the new value. The same reference is not required to update.

### Exercise 3: Bucket and hash

With a 16-slot table, which bucket do mixed hashes 1 and 17 both go into? Is that enough to say the two keys are equal?

**Solution:** Both go into bucket 1 because mask 15 is used. Not enough; the full hashes still differ, and keys must have a valid identity relation.

### Exercise 4: Half a contract

A class overrides equals so that two identical codes are equal, but hashCode also inspects a display name that can differ. Is this safe?

**Solution:** No, if the name causes two equal objects to have different hashCode values. You must align hashCode's components and rules with equals.

### Exercise 5: Mutated key

A key uses `id` in equals/hashCode, was put when `id` was 1, and then `id` was changed to 17. Can you rely on still holding the exact same reference for get to surely succeed?

**Solution:** No. The hash computed at lookup time may not match the initial storage path. This is mutating a key while it is used as a key, which has no normal usage guarantees.

### Exercise 6: Null value

A map has K → null. Both `get(K)` and `remove(K)` return null. Can you conclude that K never existed?

**Solution:** No. Get may have found the entry whose value is null; remove may have deleted that entry. When you need to know existence, check the appropriate key information.

### Exercise 7: Composite key

Two organizations have the same `customerId` 42. If only `customerId` is used as the key, one value is replaced after the second put. Did HashMap violate key uniqueness?

**Solution:** No. The key model is treating the two entities as the same key. If you need to distinguish by organization, use an appropriate composite key such as `CustomerKey`.

### Exercise 8: Testing hash

A test requires all distinct keys to have different hashCode values. Does this match the hashCode contract?

**Solution:** No. Two distinct keys are still allowed to collide in hash. Tests should require equal keys to have the same hash and verify that the map handles distinct keys—including collisions—with the right results.

## 16. References

- [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): class contract and operations.
- [Object Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): equals and hashCode.
- [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): key uniqueness, null, and restrictions on mutable keys.
- [HashMap in OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/HashMap.java): reference for hash, getNode, putVal, and removeNode.

Hash helps find the candidate region; equals helps identify the right logical key. Put, get, and remove only coordinate effectively when the key's two methods are consistent with each other and identity information is kept stable while the key resides in the map.
