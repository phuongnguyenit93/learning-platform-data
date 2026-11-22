# Distinguishing Correctness Testing From Hash Distribution or Performance Evaluation

When writing `equals()` and `hashCode()` in Java, there are two distinct questions:

1. **Correctness:** do two objects considered equal obey the `equals()` and `hashCode()` contract? Do `HashSet`/`HashMap` look up equivalent keys properly?
2. **Distribution and performance:** do hash codes spread keys of a realistic dataset relatively evenly? What are the collision counts, lookup/insert/remove times, hash computation cost, and memory footprint?

**A valid hash function does not necessarily distribute well; a hash function with a nice-looking distribution is not necessarily contract-compliant.** Correctness testing is a prerequisite before performance optimization.

## 1. Two Evaluation Types Measure Different Things

| Aspect | Correctness testing | Distribution/performance evaluation |
| --- | --- | --- |
| Question | Do the equality relation and hash obey the Java contract? | How does the hash spread keys; are collection operations fast? |
| Unit of inspection | Objects, pairs/groups of objects, key-based lookup behavior | Sufficiently large datasets, simulated bucket groups, timed workloads |
| Result | PASS/FAIL, with clear counterexamples | Quantitative metrics depending on data, size, and environment |
| Core criterion | `a.equals(b) ⇒ a.hashCode() == b.hashCode()` | Empty bucket ratio, load per bucket, collisions, throughput, latency |
| Hash collisions | **Permitted** for two unequal objects | Many collisions can degrade performance |
| Tools | Unit/property-based tests, assertions, `HashSet`/`HashMap` | Histogram analysis; benchmarks with warmup and workload control, typically via JMH |
| Typical bug | Equal keys with different hashes; asymmetric `equals()` | All keys landing in one bucket; hash computation too CPU-expensive |

A `hashCode()` value is a 32-bit `int`, so it cannot assign a distinct code to every possible object that could exist. Collisions are normal. The contract does not require two unequal keys to produce two different hash codes.

## 2. Which Contracts Must Be Tested?

### 2.1. The `equals()` Contract

For non-`null` references, `equals()` must implement an equivalence relation:

- **Reflexive:** `x.equals(x)` is `true`.
- **Symmetric:** `x.equals(y)` and `y.equals(x)` return the same result.
- **Transitive:** if `x.equals(y)` and `y.equals(z)` are both true, then `x.equals(z)` must be true.
- **Consistent:** repeated calls for the same two objects must yield the same result when information used for comparison has not changed.
- **Against null:** `x.equals(null)` is `false`.

For a value-based data type, clearly decide **which fields define equality**. For example, with `UserKey(tenantId, userId)`, if both fields participate in `equals()`, then `hashCode()` must be compatible with that exact criterion.

### 2.2. The `hashCode()` Contract

- **Mandatory condition:** if `x.equals(y)`, then `x.hashCode() == y.hashCode()`.
- **State-based consistency:** when properties used in `equals()` have not changed, calls to `hashCode()` within a single Java run must yield the same value.
- **No converse requirement:** `x.hashCode() == y.hashCode()` does **not** imply `x.equals(y)`. Two unequal objects are allowed to collide.

Summarized relations to verify:

```text
equals(x, y) == true  =>  hash(x) == hash(y)      REQUIRED
hash(x) == hash(y)    =>  equals(x, y) == true    NOT GENERALLY TRUE
equals(x, y) == false =>  hash(x) != hash(y)      NOT REQUIRED
```

If you override `equals()` to change the notion of equality, you must normally override `hashCode()` to match. Do not write a broken test such as `assertNotEquals(a.hashCode(), b.hashCode())` merely because `a` and `b` differ: that check is not part of the contract.

### 2.3. Verifying Collection Semantics

For two distinct instances that are equal under `equals()`, test at least:

- Add `a` to a `HashSet`, then `contains(b)` must be true, and `add(b)` must not increase the element count.
- Calling `map.put(a, value)` requires `map.get(b)` to return the right value; subsequently putting an equivalent key must update the corresponding entry.
- A non-equivalent key must not be mistakenly treated as the same key due to an overly broad `equals()`. **A hash collision alone does not make `HashMap` merge two unequal keys**: the collection still compares with `equals()`.

These tests complement direct contract checks. They do not replace checking symmetry, transitivity, and type boundaries.

## 3. Runnable Java 17+ Example: Contract-Compliant Yet Very Poorly Distributed

The program below has three key types:

- `GoodKey`: compares by `id`; hashes by `id`. Consecutive IDs in the example spread evenly across a 16-bucket model.
- `ConstantHashKey`: also compares by `id`, yet every instance has hash 7. **The contract remains valid**, though all elements collide.
- `BrokenKey`: compares only by `id`, whereas hash returns `salt`; two equal keys can carry different hashes. **Violates the contract**, regardless of how good its distribution looks.

Save as **`HashCorrectnessVsDistribution.java`**:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class HashCorrectnessVsDistribution {
    record GoodKey(int id) {
        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    record ConstantHashKey(int id) {
        @Override
        public int hashCode() {
            return 7;
        }
    }

    static final class BrokenKey {
        final int id;
        final int salt;

        BrokenKey(int id, int salt) {
            this.id = id;
            this.salt = salt;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BrokenKey key && id == key.id;
        }

        @Override
        public int hashCode() {
            return salt; // WRONG: salt does not participate in equals().
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static int occupied(int[] counts) {
        int result = 0;
        for (int count : counts) {
            if (count > 0) {
                result++;
            }
        }
        return result;
    }

    static int maxLoad(int[] counts) {
        int max = 0;
        for (int count : counts) {
            max = Math.max(max, count);
        }
        return max;
    }

    static void checkGoodKeyContract() {
        GoodKey a = new GoodKey(42);
        GoodKey b = new GoodKey(42);
        GoodKey c = new GoodKey(42);
        GoodKey distinct = new GoodKey(99);

        check(a.equals(a), "reflexive");
        check(a.equals(b) && b.equals(a), "symmetric");
        check(a.equals(b) && b.equals(c) && a.equals(c),
                "transitive");
        check(!a.equals(null), "null");
        check(!a.equals(distinct), "different ids");
        check(a.hashCode() == b.hashCode(), "hash agreement");

        Set<GoodKey> set = new HashSet<>();
        check(set.add(a), "first insert");
        check(set.contains(b), "lookup equal key");
        check(!set.add(b) && set.size() == 1, "no duplicate");

        Map<GoodKey, String> map = new HashMap<>();
        map.put(a, "found");
        check("found".equals(map.get(b)), "map lookup");
        System.out.println("GoodKey contract: PASS");
    }

    static void checkConstantHashContract() {
        ConstantHashKey a = new ConstantHashKey(42);
        ConstantHashKey b = new ConstantHashKey(42);
        check(a.equals(b), "equal ids");
        check(a.hashCode() == b.hashCode(), "same hash");

        Set<ConstantHashKey> set = new HashSet<>();
        for (int i = 0; i < 64; i++) {
            check(set.add(new ConstantHashKey(i)), "distinct ids");
        }
        check(set.size() == 64, "collision is not equality");
        check(set.contains(new ConstantHashKey(42)),
                "lookup despite collisions");
        System.out.println("ConstantHashKey contract: PASS");
    }

    static void showBrokenContract() {
        BrokenKey a = new BrokenKey(42, 1);
        BrokenKey b = new BrokenKey(42, 2);

        check(a.equals(b) && b.equals(a), "equal ids");
        check(a.hashCode() != b.hashCode(), "different salts");
        System.out.println(
                "BrokenKey: equal=true, hashesEqual=false -> VIOLATION");
    }

    static void showBucketModel() {
        int[] good = new int[16];
        int[] constant = new int[16];

        for (int id = 0; id < 64; id++) {
            int h1 = new GoodKey(id).hashCode();
            int h2 = new ConstantHashKey(id).hashCode();
            good[Math.floorMod(h1, good.length)]++;
            constant[Math.floorMod(h2, constant.length)]++;
        }

        System.out.println("Model 64 keys / 16 buckets:");
        System.out.println("GoodKey used=" + occupied(good)
                + ", max=" + maxLoad(good));
        System.out.println("ConstantHashKey used=" + occupied(constant)
                + ", max=" + maxLoad(constant));
    }

    public static void main(String[] args) {
        checkGoodKeyContract();
        checkConstantHashContract();
        showBrokenContract();
        showBucketModel();
    }
}
```

Run commands:

```bash
javac HashCorrectnessVsDistribution.java
java HashCorrectnessVsDistribution
```

Output:

```text
GoodKey contract: PASS
ConstantHashKey contract: PASS
BrokenKey: equal=true, hashesEqual=false -> VIOLATION
Model 64 keys / 16 buckets:
GoodKey used=16, max=4
ConstantHashKey used=1, max=64
```

**Why is this example noteworthy?**

1. `ConstantHashKey` reports PASS: 64 distinct keys are still stored separately in `HashSet`, and can be found via a newly created equivalent key instance. Collisions force the collection to distinguish keys using `equals()`, so they do not by themselves produce wrong results.
2. On the 16-bucket **illustrative model**, `GoodKey` with IDs 0–63 fills all 16 buckets, 4 elements per bucket. `ConstantHashKey` piles all 64 elements into a single bucket. This is a difference in distribution, not contract.
3. `BrokenKey(42,1)` and `BrokenKey(42,2)` are equal under `equals()` yet have hashes 1 and 2 respectively, failing the mandatory condition. You do not need timing measurements or reliance on incidental `HashMap` behavior to prove the violation.
4. The `Math.floorMod(hash,16)` expression here is a **simplified bucket-partitioning model**, **not an exact description of how Java 17 `HashMap` mixes bits, computes bucket indices, resizes, or handles collisions**. Do not use the numbers from this model as a `HashMap` benchmark.

Therefore, a test report can state simultaneously: "contract PASS, distribution quality on this workload is poor." The two conclusions do not contradict each other.

## 4. Designing Correctness Tests With Bug-Finding Power

### 4.1. Choosing Data Intentionally

Do not just create 100 random objects and confirm no exceptions are thrown. Prepare object groups matching the **equality semantics** declared by the class:

| Situation | Expected result |
| --- | --- |
| Same reference `a` | `a.equals(a)` is true |
| Two independent instances with the same identity field set | `equals()` is true and hashes match |
| Differing in exactly one field that **does** participate in `equals()` | Normally `equals()` is false per class rules |
| Differing in a field that **does not** participate in `equals()` | `equals()` must not change solely due to this field |
| Different-type object, parent/subclass if inheritance exists | Does not break symmetry or transitivity |
| `null`, empty, Unicode, negative numbers, integer boundary values | No incorrect behavior or unexpected exceptions |
| Create multiple instances with equal data, then use as keys | Set/map still finds the equivalent key |
| Different keys that share the same hash | Set/map still keeps them as separate keys if not `equals()` |

If `equals()` depends on arrays, note that `array.equals(otherArray)` defaults to array identity, whereas `Arrays.equals`/`Arrays.deepEquals` compare contents in their own ways. Comparison and hashing rules must be compatible, for example pairing `Arrays.equals` with `Arrays.hashCode` for appropriate 1D arrays.

If a key uses `double`, `BigDecimal`, or a class with special equality rules, test NaN, `-0.0`/`0.0` values, or differing scales when relevant to that type's equality criteria. Do not assume all numeric types share one definition of "equal".

### 4.2. Property-Based Tests and Data Generation Rules

With an object generator, you can check many triples `(a,b,c)` to find symmetry/transitivity counterexamples. However, pure randomness rarely produces two equal instances. You must **intentionally clone the same semantic key**, generate variants differing in one identity field, and generate variants differing in fields that do not participate in `equals()`.

Pseudocode for checking pairs:

```text
for each pair (a, b):
    assert a.equals(b) == b.equals(a)
    if a.equals(b):
        assert a.hashCode() == b.hashCode()
    // Do not assert differing hashes when equals is false.

for each triple (a, b, c):
    if a.equals(b) and b.equals(c):
        assert a.equals(c)
```

Add checks for `equals(null)`, reflexivity, repeated calls when state does not change, and real map/set behavior. When generating large datasets, save the seed and the minimal counterexample so bugs are reproducible.

**Limits of evidence:** tests passing all selected cases only prove behavior within the tested domain. They do not mathematically prove every equality relationship holds for all possible values. The soundness of the `equals()` definition still needs design-level review.

### 4.3. Mutable Key Trap

Even when `equals()`/`hashCode()` are written consistently at any single moment, mutating fields participating in equality after placing an instance into a `HashSet` or using it as a `HashMap` key can cause lookups to fail: the key sits at a bucket based on its old hash. Tests should enforce one of two design rules:

- Prefer immutable keys, such as a `record` with suitable components and no exposed mutable state affecting comparison.
- Or ensure the application never mutates state participating in equality/hashing while the key resides in a hash structure; to change a key, remove and reinsert it in a controlled manner.

With a `record`, components referencing lists/arrays can still point to mutable data. A `record` does not automatically make the entire inner object graph immutable.

## 5. Evaluating Hash Distribution: Measuring the Right Object and Data

Once correctness passes, evaluate hash quality on the **actual key set expected in production**. A hash function with good distribution on consecutive IDs may perform poorly on structured IDs, such as ones whose low bits are always 0; likewise, a benchmark over a few dozen keys does not represent a system with millions of keys.

You can run a simulated bucket experiment following these steps:

1. Construct meaningful input data: consecutive IDs, fixed-step IDs, strings with common prefixes, random data with saved seeds, and key distributions resembling real workloads.
2. Choose a bucket count for the model and a `hash → bucket` mapping rule, stating that rule explicitly. Distinguish the model from `HashMap` internals.
3. Count elements in each bucket; compute occupied buckets, average load `N / B`, maximum load, and a bucket load histogram.
4. Count collisions **according to the chosen definition**, such as elements beyond the first in each bucket `sum(max(0, bucketSize - 1))`. Do not equate "identical hash codes" with "landing in the same bucket after mapping".
5. Repeat across multiple sizes and data patterns; compare using the exact same key set, mapping rule, and bucket count.

For example, with 64 keys and 16 buckets:

- `GoodKey` in the program: 16 occupied buckets, average load 4, maximum load 4; elements beyond the first slot per the definition above equal `64 - 16 = 48`.
- `ConstantHashKey`: 1 occupied bucket, average load across all 16 buckets is still 4, yet maximum load is 64; elements beyond the first slot equal `64 - 1 = 63`.

**Identical average load does not mean identical distribution.** You must examine the histogram/variance/max load. Even a fairly uniform `int` hash still produces bucket collisions because the bucket count is smaller than the hash space and element count.

To examine actual `HashMap`/`HashSet` behavior, simple bucket metrics are insufficient. Table layout, capacity, load factor, bit mixing, and collision handling depend on implementation and JDK version. Do not rely on unguaranteed internal details and treat them as the Java API contract.

## 6. Measuring Collection Performance: A Different Problem From Distribution

A good histogram may **suggest** better lookup speed, yet does not prove it on its own. Real cost also includes computing `hashCode()`, `equals()`, allocations, memory locality, table size, insert/get/remove operations, GC, JIT, and data characteristics.

For `HashMap` or `HashSet`, specify:

- **Workload:** how many keys inserted, read/write ratio, hit/miss lookup ratio, concurrent size, and access key distribution.
- **Metrics:** throughput (ops/sec), per-operation latency, percentiles such as p50/p95/p99 when meaningful, plus allocation/GC when relevant.
- **Setup:** JDK and JVM flags, machine, heap size, co-running processes, warmup strategy, multiple iterations/forks, and result variance.
- **Fair comparison:** keep the exact same key set, `equals()` semantics, element count, and operation sequence. If a candidate breaks the contract, exclude it from optimization comparisons.
- **Reliable benchmarking:** prefer JMH, designing `@State`, `@Setup`, `@Benchmark`, and suitable measurement modes. Avoid drawing conclusions from a single `System.nanoTime()` wrapping one loop.

For example, a noisy measurement is creating `new HashMap<>()`, allocating thousands of keys, inserting them, measuring total time, and calling that "`hashCode` time". That mixes allocation, resizing, collection traversal, and bytecode/JIT execution; the result does not answer the question accurately.

With Java `HashMap`, under suitable hashing and load, get/put typically has expected near-constant time per operation; severe collisions can slow it down markedly. The exact behavior of a colliding bucket also depends on keys, insertion order, size, and implementation details, so do not claim a specific factor or timing without measuring.

A hash function with more arithmetic operations yet better distribution may be faster or slower overall, depending on lookup frequency and collection size. **Distribution metrics and benchmarks must be read together**, rather than letting one metric replace everything.

## 7. Recommended Verification Order

```text
Define key semantics
             |
             v
Test equals + hashCode contract
             |
       FAIL? +-- Yes --> Fix definition/implementation and re-test
             |
            No
             v
Test HashSet / HashMap behavior
             |
             v
Analyze distribution on representative data
             |
             v
Run JMH on critical workloads
             |
             v
Evaluate trade-offs: correctness, speed, memory, complexity
```

When reviewing results, interpret each scenario:

| Correctness | Distribution/performance | Action |
| --- | --- | --- |
| FAIL | Any | Fix the contract first. Benchmarks cannot legitimize broken keys. |
| PASS | Good for target workload | Keep design, monitor as workload changes. |
| PASS | Poor on realistic workload | Try a different hash while preserving the same `equals()` semantics and re-running all correctness tests. |
| PASS | Not yet measured | Insufficient evidence to claim the hash is fast/slow; only conclude contract correctness on tested data. |

Do not optimize so that "every object has a unique hash": this is not required by Java, and is impossible for key domains larger than the number of `int` values. The meaningful goal is **guaranteeing contract correctness** and then achieving performance suited to real data and workloads.

## 8. Common Mistakes

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Asserting unequal keys must have different hashes | Hash collisions are valid | Only require equal keys to share equal hashes |
| Seeing a nice histogram and concluding `equals()` is right | Distribution does not verify reflexivity/symmetry/transitivity | Write independent contract tests |
| Calling a constant `hashCode()` a functional bug | It can be completely contract-compliant | Label as a performance risk, check workload |
| Returning random values from `hashCode()` to look "uniform" | Unstable, breaks the contract and lookups | Hashes must remain stable while equality state is unchanged |
| Using mutable keys and mutating identity fields while in a map | Lookups can fail even if code looked fine earlier | Use immutable keys or remove/reinsert properly |
| Benchmarking once without warmup | JIT, GC, allocation, and system noise dominate | Use JMH with proper setup and iterations |
| Measuring modulo buckets and claiming internal `HashMap` numbers | The model does not fully reflect the implementation | State clearly that it is an illustrative histogram |
| Optimizing hash and skipping equality tests | Can break compatibility between `equals` and hashing | Re-run correctness suite after every change |
| Treating throughput alone as everything | Can hide tail latency, memory, or GC issues | Measure metrics suited to usage goals |

## 9. Pre-Conclusion Checklist

1. Have you explicitly stated the **business key** and which fields belong to `equals()`?
2. Have you tested reflexivity, symmetry, transitivity, null, consistency, boundary cases, and value-equal key pairs that are two distinct instances?
3. Have you tested `equals ⇒ same hash`, while **not forcing** unequal keys to have different hashes?
4. Have you confirmed `HashSet`/`HashMap` recognize and retrieve an equivalent key accurately, even under collisions?
5. Have you addressed the risk of mutating keys after insertion into collections?
6. If making claims about distribution quality: have you clearly specified the dataset, bucket model, metrics, and differences from `HashMap` internals?
7. If making claims about performance: do you have reliable benchmarks, representative workloads, iteration counts, environment, warmup, and fair comparison results?

**Remember:** `equals()`/`hashCode()` tests answer **"is it correct?"**; distribution analysis and benchmarks answer **"how well does it perform on this data and environment?"**. Having many collisions in a hash function does not by itself break the contract, and a seemingly well-distributed hash function cannot compensate for a wrongly defined equality relation.
