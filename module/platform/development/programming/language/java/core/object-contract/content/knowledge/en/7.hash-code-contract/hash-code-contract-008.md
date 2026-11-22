# A Constant Hash Code Can Satisfy the Contract but Has Poor Distribution

## 1. The Meaning of a Hash Code

In Java, the `hashCode()` method returns an `int` integer representing an object's hash result. Hash-based structures such as `HashMap` and `HashSet` use this result to guide element lookup, insertion, and deletion. **A hash code is not a unique identifier** and does not by itself decide whether two objects are equal: `equals(Object)` is the final equality check when objects have matching relevant hashes.

The `Object.hashCode()` contract has key points:

1. If `hashCode()` is called multiple times on the same object during a single application execution, when the data used by `equals` does not change, the result must be consistent.
2. **If `a.equals(b)` is `true`, `a.hashCode() == b.hashCode()` must also be `true`.** This is the most important constraint when overriding both methods.
3. If `a.equals(b)` is `false`, the two hash codes **are allowed to be equal**. Returning different hashes for unequal objects is a performance goal, not a mandatory condition for contract correctness.

Therefore, a class can define:

~~~java
@Override
public int hashCode() {
    return 1;
}
~~~

This is an **illustrative method snippet**, not a standalone program. For every pair of equal objects, both hash values are `1`, so the mandatory condition is satisfied. If the class has a valid `equals`, a constant and stable hash code can be **contractually valid**, even though that choice is usually very poor when used in a hash table.

What must be distinguished is **contract compliance** versus **good distribution**: these two requirements are related, not identical.

## 2. How Does a Constant Hash Code Cause Poor Distribution?

A hash table organizes entries into slots called *buckets* (storage groups). `HashMap` applies a bit-mixing operation to the hash code and uses the result along with the table size to determine the bucket. Different hash codes can still land in the same bucket, but **every key with the same hash code goes into the same bucket** at a given table state.

If every key returns `1`:

- `new Key(101)`, `new Key(102)`, and `new Key(103)` may all differ according to `equals`.
- They still share the same hash code, because `hashCode()` always returns `1`.
- When stored in a `HashMap` or `HashSet`, entries constantly contend for the same bucket. The structure must distinguish them via key checks (including `equals`) instead of quickly narrowing down across many different buckets.

In a well-distributed table, many `put`, `get`, `containsKey`, or `contains` operations have an average cost close to `O(1)` under typical conditions. When a bucket holds very many elements, operations may have to inspect many more candidates; with list-based collision handling, scanning a bucket with `n` elements can cost `O(n)`. Modern Java versions have a mechanism to convert some large `HashMap` buckets into tree structures to mitigate impact under suitable conditions, yet that **does not make a constant hash code strategy good**. Exact behavior depends on element count, table capacity, and the shape of the keys.

`HashSet` is implemented on top of `HashMap`, so it suffers the same impact when many elements share a hash code.

**Hash collisions do not lose elements.** A properly implemented hash collection still stores two unequal keys with the same hash; when it needs to identify the exact key, it checks equality. The main problem is that the number of candidates to inspect grows and expected performance can degrade.

## 3. Java 17 Example: Correct Results with Different Hashing Strategies

The example uses two key types with the same equality rule: two objects **of the same key type** are considered equal if they have the same `id`. The `ConstantKey` type returns `7` for every object; the `IdKey` type uses `Integer.hashCode(id)` and thus reflects the `id` value.

Save the program in **ConstantHashDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class ConstantHashDemo {
    static final class ConstantKey {
        private final int id;

        ConstantKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof ConstantKey that)) {
                return false;
            }
            return id == that.id;
        }

        @Override
        public int hashCode() {
            return 7;
        }
    }

    static final class IdKey {
        private final int id;

        IdKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof IdKey that)) {
                return false;
            }
            return id == that.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        ConstantKey one = new ConstantKey(1);
        ConstantKey sameOne = new ConstantKey(1);
        ConstantKey two = new ConstantKey(2);

        System.out.println("equal keys: " + one.equals(sameOne));
        System.out.println("equal keys share hash: "
                + (one.hashCode() == sameOne.hashCode()));
        System.out.println("different keys: " + one.equals(two));
        System.out.println("different keys collide: "
                + (one.hashCode() == two.hashCode()));

        Set<ConstantKey> constantSet = new HashSet<>();
        constantSet.add(one);
        constantSet.add(sameOne);
        constantSet.add(two);
        System.out.println("constant set size: " + constantSet.size());
        System.out.println("constant set contains id=2: "
                + constantSet.contains(new ConstantKey(2)));

        Map<ConstantKey, String> constantMap = new HashMap<>();
        constantMap.put(one, "one");
        constantMap.put(two, "two");
        System.out.println("constant map lookup id=2: "
                + constantMap.get(new ConstantKey(2)));

        IdKey idOne = new IdKey(1);
        IdKey idTwo = new IdKey(2);
        System.out.println("id hashes: "
                + idOne.hashCode() + ", " + idTwo.hashCode());

        Set<IdKey> idSet = new HashSet<>();
        idSet.add(idOne);
        idSet.add(idTwo);
        idSet.add(new IdKey(1));
        System.out.println("id set size: " + idSet.size());
        System.out.println("id set contains id=2: "
                + idSet.contains(new IdKey(2)));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac ConstantHashDemo.java
java ConstantHashDemo
~~~

Expected output:

~~~text
equal keys: true
equal keys share hash: true
different keys: false
different keys collide: true
constant set size: 2
constant set contains id=2: true
constant map lookup id=2: two
id hashes: 1, 2
id set size: 2
id set contains id=2: true
~~~

Takeaways from the output:

1. `one` and `sameOne` are equal according to `equals` and both have hash `7`. The contract is upheld.
2. `one` and `two` are not equal yet share hash `7`. This is a **valid collision**, not a contract violation.
3. `HashSet` holds two distinct elements, rather than merging all objects sharing a hash into one. Adding `sameOne` does not increase the size because it equals `one`.
4. `HashMap.get(new ConstantKey(2))` still retrieves the value `"two"`, showing that lookups remain **correct** under collisions.
5. `IdKey` produces hashes `1` and `2` for the respective `id`s; this is a better distinguishing signal for this key set. However, **two different hashes do not guarantee two different buckets**, because buckets also depend on how the table is organized.

The example above demonstrates **correctness**, not a speed benchmark. You cannot conclude timing differences from the output: a reliable measurement requires an appropriate number of keys, JVM warm-up, multiple iterations, and avoiding noise from GC, JIT, and the runtime environment. For serious Java performance analysis, use a dedicated benchmarking tool like JMH instead of inferring from a single `System.nanoTime()` run.

## 4. Distinguishing Equality and Hash Code in All Cases

| State of Two Objects | Condition on `hashCode` | Can They Be Considered Equal? |
| --- | --- | --- |
| `a.equals(b)` is `true` | **Must** have `a.hashCode() == b.hashCode()` | Yes |
| `a.equals(b)` is `false`, hashes differ | Completely valid | No |
| `a.equals(b)` is `false`, hashes match | Completely valid: collision | No |
| Hashes match, `equals` not yet called | Insufficient information to determine equality | Must use `equals` per contract |

Never replace `equals` with a hash code comparison:

~~~java
// Wrong: equal hash codes do not prove two objects are equal.
return this.hashCode() == other.hashCode();
~~~

This is an **expression illustrating a bug inside an `equals` method**, not a standalone program. It also omits checking that `other` is non-`null` and of the right type, and can lead to wrong equality semantics. For a class returning a constant hash code, this implementation makes every distinct object of the class be considered equal, destroying the meaning of `equals`.

Likewise, do not write tests like `assertNotEquals(a.hashCode(), b.hashCode())` for every unequal `a` and `b`. The contract does not require different hash codes for every pair of unequal objects. Instead, test correctness of `equals`, `hashCode` consistency under equality, and sufficiently good distribution properties on realistic data sets when performance is a requirement.

## 5. Choosing a Better `hashCode` While Preserving the Contract

### 5.1. Use the Exact Fields That Determine Equality

If `equals` is based on an `int` field `id`, you can use:

~~~java
@Override
public int hashCode() {
    return Integer.hashCode(id);
}
~~~

This is a **method that can be placed in `IdKey`**, not a standalone program. For `int`, `Integer.hashCode(id)` is simply the value `id`. Same `id` gives both equality and the same hash; different `id`s produce different hashes, reducing collisions in typical key sets compared to returning a constant.

If `equals` is based on two fields `code` and `version`, a simple way to express it is:

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hash(code, version);
}
~~~

This is an **illustrative method snippet in a class with the two corresponding fields**. `Objects.hash` handles nullable fields and combines hashes in argument order. It is readable, though it can incur varargs/boxing overhead on very hot paths; if true optimization is needed, measure first before considering manual hash combination.

A combination pattern for two reference fields is:

~~~java
@Override
public int hashCode() {
    int result = java.util.Objects.hashCode(code);
    result = 31 * result + java.util.Objects.hashCode(version);
    return result;
}
~~~

This snippet also belongs in a class with `code` and `version`. `Objects.hashCode(field)` returns `0` when the field is `null`, avoiding `NullPointerException`. The value `31` is a common multiplier, not a mandatory rule of the contract. `int` multiplication and addition can overflow under Java semantics and still yield a valid hash code. Regardless of which approach you use, **the set of fields determining `hashCode` must align with `equals`'s equality criteria**.

### 5.2. Avoid Unreliable Hashing Strategies

- **Constant:** contract-compliant if stable and `equals` is right, but creates systematic collisions across all keys.
- **Random number per call:** violates consistency even when the object does not change; lookups after insertion into a hash table can fail.
- **Current time or changing global counter:** varies across calls and does not reflect the fields determining equality.
- **`System.identityHashCode(this)` for value-equal objects:** two objects with different references that are equal according to `equals` may have different identity hashes, leading to a contract violation.
- **Mutable fields while acting as a `HashMap` key / `HashSet` element:** the hash can change after the object is already in an old bucket, causing `get`, `contains`, or `remove` to fail to find that object as expected.

Prefer attributes that serve as **stable identifiers or values aligned with `equals`**. Immutable key objects with `final` fields usually make consistency much easier to guarantee. If fields participating in `equals` are allowed to change, usage of the object as a key must be managed very carefully.

## 6. Why Not Optimize `hashCode` at All Costs?

A hash code with good distribution quality is one that spreads real-world keys relatively evenly across buckets, limiting overly crowded buckets. However, no unique `int` hash function exists for all objects: the key space can exceed the number of `int` values, so in principle **collisions are inevitable**. The goal is to reduce avoidable collisions and avoid poor distribution on the data being used, not to demand a unique code for every key.

Hash quality must be balanced against computation cost. An extremely complex hash calculation for a few keys can spend more time than the benefit gained from reducing collisions. For ordinary classes, using `Integer.hashCode`, `String.hashCode`, `Objects.hash`, or other appropriate type hash methods is usually a sensible starting point. Do not build a custom hash function without need and evidence.

In addition, data types with their own hash representations can exhibit different collisions; for example, `String.hashCode()` does not promise zero duplicates. The existence of isolated collisions does not make that hash function wrong. Only when the distribution frequently puts many entries into the same bucket is performance noticeably impacted.

## 7. Checklist for Reviewing a `hashCode` Implementation

Before using a class as a `HashSet` element or `HashMap` key, check:

1. Does every pair of objects **equal according to `equals`** have the **same hash code**?
2. Do repeated calls to `hashCode()` on an unchanged object return the same result within an execution?
3. Does the hash function rely on the fields determining equality, without depending on random numbers, time, or unintended varying information?
4. Are nullable fields handled safely?
5. Are fields related to `equals`/`hashCode` mutated while the object is inside a collection?
6. For many realistic unequal keys, is the number of colliding hash codes abnormally high? If so, review how fields are combined and measure performance instead of concluding from a tiny example.

**Takeaway to remember:** A `hashCode()` that always returns the same number can be **contract-compliant** because equal objects are guaranteed to share the same hash. Yet every key also becomes a collision case, losing the distribution advantage of hash structures. Distinguish **correct results** from **good performance**, and design `hashCode` consistently with `equals` from stable data of the object.
