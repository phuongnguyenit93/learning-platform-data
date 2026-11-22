# Bugs When Overriding Only `equals()` or Designing an Incompatible `hashCode()`

## 1. Why Must These Two Methods Go Together?

In Java, `equals(Object)` describes the **logical equality relation** between two objects; `hashCode()` provides an integer used to support searching in hash data structures such as `HashMap` and `HashSet`. Both originate from `java.lang.Object`, yet they perform two distinct jobs:

- `equals` decides whether two keys are considered the same key.
- `hashCode` helps the hash structure pick a suitable lookup region before comparing keys. With two different hash values, a typical hash structure cannot treat those keys as the same key within the same search.

**Mandatory rule:** If `a.equals(b)` is `true` then **`a.hashCode() == b.hashCode()` must be `true`**. This is a one-way relation:

```text
a.equals(b) == true  ==>  a.hashCode() == b.hashCode()
a.hashCode() == b.hashCode()  =/=>  a.equals(b) == true
```

That means unequal objects **are allowed** to share a hash code (*hash collision*). Two objects having the same hash is not enough to conclude they are equal; after the hash-locating step, the data structure must still compare using `equals`.

Besides the rule above, within a single program run, when information used in `equals` does not change, calls to `hashCode` on the same object must produce the same result. Hash results **are not required to match across different JVM runs**. The `equals` contract also demands reflexivity, symmetry, transitivity, consistency, and `x.equals(null) == false` when `x` is non-`null`.

Several important consequences follow:

1. **Overriding `equals` by value while keeping `Object.hashCode` unchanged violates the contract** in cases where two separate objects are considered equal. `Object.hashCode` is not designed to track fields used in `equals`.
2. **Overriding both yet letting `hashCode` depend on a field ignored by `equals`** is also wrong: two equal objects can have different hashes.
3. **Overriding only `hashCode` and keeping `Object.equals`** does not necessarily violate the contract: `Object.equals` still compares same reference. However, it **does not create value equality**, even if objects have equal hashes.

## 2. How Do Hash Structures Actually Use Both Methods?

Imagine a `HashMap<Key, Value>` with two keys representing the same order code. When calling `map.put(k1, value)`, `HashMap` computes `k1`'s hash to determine a storage location. When calling `map.get(k2)`, it computes `k2`'s hash to locate the corresponding region, and then uses `equals` to distinguish candidate keys with compatible hashes.

In standard JDK `HashMap` implementations, the input hash undergoes bit mixing to determine the bucket; when searching for a key, the structure checks both the computed hash and key equality. The table below is a **behavior-explaining model**, not a promise that every internal detail of `HashMap` will remain fixed across every JDK release.

| Scenario | `equals` | `hashCode` | Expected behavior of hash structure |
| --- | --- | --- | --- |
| Same logical value, proper implementation | `true` | Equal | `get` with an equivalent key finds the entry; `Set` deduplicates |
| Different values, matching hashes | `false` | Equal | Still stores/identifies as two distinct keys; collisions must be handled |
| Same logical value, different hashes | `true` | Different | **Contract violation**; `get` may miss the key and `Set` may hold two equal elements |
| Same object, no relevant state changed | `true` | Stable | Retrieval using the exact stored key must work normally |

The accurate statement is that lookup bugs **can** occur when the contract is broken; bucket count, hash-mixing mechanism, insertion order, and collisions can affect the specific symptom. To observe the bug deterministically, the runnable example below deliberately assigns clearly distinct hash values to two objects that `equals` considers equal.

## 3. Bug 1: Overriding Only `equals()`, Forgetting `hashCode()`

Suppose a key `EqualsOnly` holds a `code`. We want two objects with the same `code` to be equal, so we write:

```java
static final class EqualsOnly {
    private final String code;

    EqualsOnly(String code) {
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        return other instanceof EqualsOnly key
                && code.equals(key.code);
    }

    // WRONG: missing hashCode() override.
}
```

This is an **illustrative nested class snippet**; the complete standalone program is in section 5. Two `new EqualsOnly("A")` objects are evaluated as equal by `equals` despite being two different objects. However, `hashCode` inherited from `Object` has no obligation to produce the same hash for those two objects.

As a consequence, the "equal implies same hash" rule **is not guaranteed**. In practice, `HashSet.contains(new EqualsOnly("A"))` or `HashMap.get(new EqualsOnly("A"))` can return unexpected results when the object was added using another instance with the same `code`.

**You should not write a test assuming two `new EqualsOnly("A")` calls are guaranteed to have different hashes.** The `Object.hashCode` contract does not guarantee that every pair of objects with different references always has different hashes; collisions can still occur. The lack of guarantee itself is the design bug, even if a single run happens to find the element.

The fix is to also override `hashCode` using **the same set of attributes that define equality**, for example:

```java
@Override
public int hashCode() {
    return code.hashCode();
}
```

With multiple fields, you can use `Objects.hash(field1, field2)` or an appropriate hash-combining formula. If using `Arrays.equals`, `Arrays.deepEquals`, or `Objects.deepEquals` for array/nested data, the hash computation must correspond (`Arrays.hashCode` or `Arrays.deepHashCode` as appropriate). Not every field of the object needs to participate in the hash; fields that determine whether two objects can be *equal* must be computed so that two equal objects always yield the same result.

## 4. Bug 2: Having `hashCode()` Yet Designing It Incompatible With `equals()`

A subtler bug: both methods exist, yet they rely on **two incompatible sets of attributes**.

For example, an object has `code` and `hash`. `equals` uses only `code`, while `hashCode` directly returns the `hash` field:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    return other instanceof IncompatibleHash key
            && code.equals(key.code);
}

@Override
public int hashCode() {
    return hash; // WRONG: can differ even though equals may be true.
}
```

These are **the two methods inside the `IncompatibleHash` class** in the complete runnable example below. When creating `new IncompatibleHash("A", 1)` and `new IncompatibleHash("A", 2)`, the two objects are equal by `code` yet their hashes are 1 and 2 respectively. The violation occurs **right at the object pair**, even before using any collection.

This is a **contract-compatibility** bug, not a Java syntax error. The compiler cannot prove all dynamic value comparisons of the application.

Another variant: `equals` ignores `lastUpdated`, yet `hashCode` uses `lastUpdated`. Two records with the same logical identity but different update timestamps can be hashed into two different positions. Conversely, if `equals` uses both `code` and `region`, while `hashCode` uses only `code`, the mandatory rule can still hold: two equal objects are guaranteed to share `code` and thus the same hash, albeit producing more collisions. **The hash is not forced to use every field in `equals`**, yet it must be strictly compatible.

## 5. Runnable Java 17+ Program: Broken and Valid Side by Side

Save the code below to **`HashContractDemo.java`**. There are three key types:

- `EqualsOnly`: intentionally overrides `equals` without overriding `hashCode`.
- `IncompatibleHash`: intentionally overrides both yet returns a hash independent of the `equals` criterion.
- `GoodKey`: properly overrides both by `code`, storing immutable data.

```java
import java.util.*;

public class HashContractDemo {
    static final class EqualsOnly {
        private final String code;

        EqualsOnly(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            return other instanceof EqualsOnly key
                    && code.equals(key.code);
        }
        // Intentionally inherits Object.hashCode(): wrong for value equality.
    }

    static final class IncompatibleHash {
        private final String code;
        private final int hash;

        IncompatibleHash(String code, int hash) {
            this.code = Objects.requireNonNull(code);
            this.hash = hash;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            return other instanceof IncompatibleHash key
                    && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return hash; // Intentionally inconsistent with equals.
        }
    }

    static final class GoodKey {
        private final String code;

        GoodKey(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            return other instanceof GoodKey key
                    && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    public static void main(String[] args) {
        EqualsOnly e1 = new EqualsOnly("A");
        EqualsOnly e2 = new EqualsOnly("A");
        System.out.println("equals-only logically equal: " + e1.equals(e2));

        IncompatibleHash b1 = new IncompatibleHash("A", 1);
        IncompatibleHash b2 = new IncompatibleHash("A", 2);
        Map<IncompatibleHash, String> brokenMap = new HashMap<>();
        brokenMap.put(b1, "stored");

        Set<IncompatibleHash> brokenSet = new HashSet<>();
        brokenSet.add(b1);
        brokenSet.add(b2);

        System.out.println("bad pair equals: " + b1.equals(b2));
        System.out.println("bad pair hashes: "
                + b1.hashCode() + " / " + b2.hashCode());
        System.out.println("broken map get original: " + brokenMap.get(b1));
        System.out.println("broken map get equal key: " + brokenMap.get(b2));
        System.out.println("broken set size: " + brokenSet.size());

        GoodKey g1 = new GoodKey("A");
        GoodKey g2 = new GoodKey("A");
        Map<GoodKey, String> goodMap = new HashMap<>();
        goodMap.put(g1, "stored");

        Set<GoodKey> goodSet = new HashSet<>();
        goodSet.add(g1);
        goodSet.add(g2);

        System.out.println("good pair equals: " + g1.equals(g2));
        System.out.println("good pair hashes equal: "
                + (g1.hashCode() == g2.hashCode()));
        System.out.println("good map get equal key: " + goodMap.get(g2));
        System.out.println("good set size: " + goodSet.size());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac HashContractDemo.java
java HashContractDemo
```

Program output:

```text
equals-only logically equal: true
bad pair equals: true
bad pair hashes: 1 / 2
broken map get original: stored
broken map get equal key: null
broken set size: 2
good pair equals: true
good pair hashes equal: true
good map get equal key: stored
good set size: 1
```

**Line-by-line analysis:**

1. `e1.equals(e2)` is `true`, because both codes are `"A"`. `EqualsOnly`'s hash is not printed because the result inherited from `Object` has no specific value guaranteed across JVMs/runs.
2. `b1.equals(b2)` is `true`, yet `b1.hashCode() == 1` and `b2.hashCode() == 2`. This is a deterministic violation without needing to guess about identity hashes.
3. `brokenMap.get(b1)` is `stored` because the exact object and hash 1 used for storage are queried.
4. `brokenMap.get(b2)` is `null`: with the hash pair 1 and 2 in this example, `HashMap` does not find the region holding the stored key. The `null` result here means **the entry was not found**, not that there is a mapping with value `null` (the example does not store `null` values).
5. `brokenSet.size()` is 2: `HashSet` stores two objects that `equals` considers equal. This is a concrete consequence of violating the contract.
6. `g1` and `g2` share `code`, so `equals` gives `true` and `hashCode` gives the same result; lookup with an equivalent key succeeds and `HashSet` keeps only one logical value.

Note: In the example code, `Map` and `Set` are **interfaces**; the actual instances are `HashMap` and `HashSet`. You should not apply conclusions about bucket mechanisms to non-hash-based structures; for instance, `TreeMap` and `TreeSet` can use `Comparator`/`compareTo` to identify keys instead of `equals/hashCode`.

## 6. Bug 3: Mutating a Key's Attribute After Adding to a Collection

Even when both methods are consistent at object creation time, **mutating a field participating in `equals`/`hashCode` after storing the key** can break lookup results.

Suppose `MutableKey` has a `code` field used in both `equals` and `hashCode`. We add an object with `code = "A"` to a `HashSet`, then change `code = "B"`. The object still resides at the location determined from `"A"`'s hash at insertion time, while the subsequent `contains` call computes the hash from `"B"`. Therefore, the key may fail to be found again, even while holding the exact same reference.

This is not an "overriding only `equals`" bug, yet it is a **bug in preserving hash stability while the key remains inside a hash structure**. `HashMap` does not automatically move an entry to a new bucket simply because a key's field was modified.

Practical solutions:

- Prefer an **immutable** key class with equality-defining fields declared `final` and the component data itself not mutating behind the scenes.
- If you need to change a key's logical identity, remove the entry using the old state first, create a new key, and re-insert.
- Do not use fields that can change over time (`updatedAt`, session state, display info) in a key's equality/hash unless there is a clear, explicit collection-update design.

Marking `final` on **a reference to an array or mutable object** does not automatically make the contents inside immutable. For example, a key holding `final List<String> values` can still suffer bugs if the elements inside the list are modified and the list is a component included in the hash.

## 7. Proper Design With Multiple Fields, Nulls, Arrays, and Inheritance

### 7.1. Shared logical identity

First, answer: by what criteria should two objects of the same type be equal? For a user key (`tenantId`, `userId`), if **both** fields define identity, they must be compared consistently in `equals` and participate compatibly in `hashCode`:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof UserKey key)) return false;
    return Objects.equals(tenantId, key.tenantId)
            && Objects.equals(userId, key.userId);
}

@Override
public int hashCode() {
    return Objects.hash(tenantId, userId);
}
```

This is an **illustrative method snippet** for a `UserKey` class already having two fields `tenantId` and `userId`; it is not a standalone file. `Objects.equals` handles `null` in **fields** safely. If the right-hand object itself is `null`, the `instanceof` condition returns `false`.

Using `Objects.hash` is not mandatory: for a single non-null `String` field, `code.hashCode()` is completely valid, as `GoodKey` illustrated. If choosing to use fewer fields to compute the hash, you must accept the cost of higher collisions, yet you must never make the hash depend on a field outside the equality criteria in a way that causes different hashes for two equal objects.

### 7.2. Arrays need content-based comparison

`Objects.equals(arrayA, arrayB)` and `arrayA.equals(arrayB)` on standard Java arrays compare by **reference**, not element-by-element. For one-dimensional arrays, use `Arrays.equals` paired with `Arrays.hashCode`. For nested arrays requiring deep comparison, consider `Arrays.deepEquals` and `Arrays.deepHashCode` matching the structure. You must clearly decide whether array contents can change when used as a hash key.

### 7.3. Inheritance can cause other bugs

If a superclass considers some subclass objects equal, yet the subclass adds an equality-participating field and rejects the superclass, a **symmetry** violation can occur even before considering hashes. If a subclass calls `super.equals` and extends criteria, you must thoroughly verify reflexivity/symmetry/transitivity and `hashCode` across all comparable types.

You cannot fix inheritance bugs merely by changing the hash formula. For value types, `final class`, `record`, and composition are usually easier to maintain when cross-type equality is unnecessary.

### 7.4. Immutable values and `record`

Since Java 16, `record` provides auto-generated `equals` and `hashCode` based on its components. In Java 17, declaring:

```java
record OrderKey(String tenantId, String orderId) {}
```

is a concise way to get component-based equality when the data type fits a value-key model. **Note**: mutable component objects can still change their internal state; for array-typed fields, `record`'s default comparison does not turn arrays into deep content equality.

## 8. Testing the Contract, Not Just Hash Outcomes

When writing `equals` and `hashCode` manually for a key type, you should verify:

| Test | Condition to confirm |
| --- | --- |
| Reflexivity | `a.equals(a)` is `true` |
| Symmetry | `a.equals(b) == b.equals(a)` |
| Transitivity | If `a.equals(b)` and `b.equals(c)`, then `a.equals(c)` |
| Null | `a.equals(null)` is `false` |
| Hash follows equality | If `a.equals(b)` then `a.hashCode() == b.hashCode()` |
| Collision | It is possible to have `hash(a) == hash(b)` while `!a.equals(b)`, yet the collection still distinguishes accurately |
| `HashMap`/`HashSet` | `get`/`contains` succeeds with an equivalent key; `Set` does not retain duplicate logical values |
| Stability | If information participating in equality does not change, the hash of the same object must remain stable |

You can add a short assertion in your test suite:

```java
if (a.equals(b) && a.hashCode() != b.hashCode()) {
    throw new AssertionError("equals/hashCode contract violated");
}
```

This is a **check snippet assuming variables `a`, `b` already exist**, not a standalone program. Tests should create many different pairs (same value, different value, different type, optional null fields, mutable fields if any), and separately test `HashMap`/`HashSet` in realistic application scenarios.

Do not test with the assumption that `!a.equals(b)` implies hashes must differ. That assumption is **false**: collisions are valid. Nor should you assert that specific hash values of `Object.hashCode` will remain fixed across machines or execution sessions.

## 9. Summary Table of Causes and Fixes

| Real-world bug | Symptom | Fix direction |
| --- | --- | --- |
| Overriding `equals` yet forgetting `hashCode` | Two objects equal by value yet lookup results with an equivalent instance are unstable | Override `hashCode` using the equality data |
| `equals` and `hashCode` use two incompatible sets of fields | `equals` is `true`, yet hashes differ | Define a single consistent logical identity |
| `equals` breaks symmetry/transitivity in inheritance | Pairs/chains of objects give contradictory results | Redesign equality relationships between classes |
| Key field mutated after insertion | `contains` or `get` fails to find the key | Use immutable keys or remove and re-insert a new key |
| Hash always returns a constant | Can still obey contract yet causes many collisions and degrades performance | Combine equality attributes into a reasonable hash distribution |
| Overriding only `hashCode` expecting value equality | Two instances have equal hashes yet `equals` stays `false` | Must override `equals` if value equality is desired |
| Checking equality with `==` when value comparison is needed | Two instances with identical data are still unequal | Use properly designed `equals`; do not confuse identity with equality |
| Array using wrong method pair | Hashing/comparing by reference while business logic needs content comparison | Use appropriate `Arrays.equals/hashCode` or `deepEquals/deepHashCode` pair |

**Self-check question:** Two objects `CustomerKey("C01", "west")` and `CustomerKey("C01", "east")` are considered equal by `equals` because it only compares customer ID. If `hashCode` hashes both customer ID and region, is that a valid implementation? **No**, because two equal objects can receive two different hashes. Either fix `equals` so region is also an identity component, or remove region from the hash formula, depending on business requirements.

The enduring design principle is to **clearly define which values form identity**, implement `equals` and `hashCode` compatible with that relation, prefer immutable keys, and verify on actual hash collections. `hashCode` helps search fast; `equals` determines equality. They must cooperate according to the contract.