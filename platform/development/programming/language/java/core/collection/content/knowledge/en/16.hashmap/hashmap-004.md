# Expected Performance, Worst Cases, and Hash Function Quality

## 1. Why Is "HashMap Is O(1)" Not Enough?

HashMap is widely used because it can look up keys and update mappings very efficiently. However, if you only memorize "get is O(1)" without the conditions, it is easy to be surprised when a different dataset makes the program noticeably slower.

Time complexity does not depend solely on the class name. It also depends on key distribution, the number of mappings relative to table capacity, the cost of `hashCode`/`equals`, when resizing occurs, and the search path inside a bucket.

The HashMap documentation states constant-time performance for basic operations when the hash function disperses the elements properly among the buckets. This is an essential condition for understanding usage expectations. [HashMap Documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

In this lesson, we will separate three questions:

- When data is properly distributed, how many candidates does each operation typically need to examine?
- When many keys cluster in one place, how much can the work grow?
- How do we design and verify a hash function without confusing comparison counts with runtime?

The examples will count calls to `hashCode`, `equals`, and `compareTo`. This is evidence of part of the algorithmic work, not a measurement of system latency.

## 2. Cost Model and Key Quantities

Let:

| Symbol | Meaning |
| --- | --- |
| N | Number of mappings in the Map |
| C | Number of buckets in the table once the table has been allocated |
| L | Number of candidates concentrated in a bucket under consideration |
| α = N/C | Average number of mappings per bucket |
| H | Cost of computing the hash code of the lookup key |
| E | Cost of one key equality comparison |
| P | Cost of one ordering comparison if used |

Do not read α as the mandatory number of elements in every bucket. A table with N = 8 and C = 16 has α = 0.5, yet all eight mappings could still land in a single bucket while leaving the other 15 buckets empty.

A lookup can be visualized as:

~~~text
compute key hash code
+ select bucket
+ filter candidates using hash code information
+ compare equality or ordering when needed
+ read value if the key is found.
~~~

Locating the bucket is usually just a few small bitwise operations. The expensive part can lie in the number of candidates or in the methods provided by the key itself.

If we temporarily treat H, E, and P as small constants, we can focus on the number of nodes that need to be examined. If a key contains long strings or complex structures, we must go back and account for the cost of the key itself.

O(1) notation with respect to N also does not mean the operation takes zero work or allocates no memory. It only describes how the work grows relative to the chosen quantity in the model.

## 3. Expected Performance and Amortized Cost Are Different

### Expected: Based on Data Distribution

If keys are distributed across buckets evenly enough and the load is controlled, a lookup typically encounters only a small group of candidates. In a chained hash table model assuming uniform distribution, the average number of candidates is related to α; when α is kept within a constant bound, lookup work also has constant expectation.

This does not mean every bucket always has length α, or that every `get` checks exactly one node. It is an evaluation over a distribution and usage conditions, not an absolute guarantee for a specific key.

Evenly distributed data does not have to be randomly generated either. For instance, with a suitable integer domain and a hash code that uses enough information, consecutive codes can distribute well. What matters is the actual distribution after passing through the bucket selection mechanism.

### Amortized: Spreading Expensive Work Across a Sequence of Operations

A `put` that adds a new key may need to resize the table, allocate memory, and reposition nodes. That single call can take much more work than ordinary insertions.

If capacity grows in appropriate steps and hashing is well distributed, the total work of resizing passes is spread across many insertions. Therefore, `put` is commonly described as amortized expected O(1) under a suitable model.

"Amortized" does not mean every `put` is equally fast. A single request can still hit a resize and experience higher latency.

These two concepts do not replace each other:

| Term | What Does It Explain? |
| --- | --- |
| Expected cost | Key distribution conditions that keep the average number of examined candidates small |
| Amortized cost | A few expensive operations spread across an entire sequence of operations |
| Worst-case cost | How much work a single operation or an adverse dataset can demand |

When evaluating an API by single-request latency, do not take average throughput as proof that there will never be a slow update.

## 4. HashMap Operations Do Not All Have the Same Cost

The table below is a practical model for keys with constant-cost `hashCode`/`equals`, under clearly stated distribution conditions:

| Operation | Common Assessment | What to Keep in Mind |
| --- | --- | --- |
| `get`, `containsKey`, `remove` by key | Expected O(1) when well distributed | Adverse collision cases may have to examine O(N) candidates |
| `put` adding a mapping | Amortized expected O(1) when well distributed | A single call may have to resize the table or handle a crowded bucket |
| `put` replacing an existing key's value | Must find the matching key first | Cannot be called free just because `size` does not increase |
| `containsValue` | May have to scan the table and nodes | Does not have the same hash index by value |
| Iterating the entire Map | Depends on O(C + N) | Over-allocating a sparse table can make iteration more expensive |
| `size` | O(1) in this standard implementation | Does not need to traverse to recount every mapping |

During a table resize, allocation and redistribution work can depend on C + N. With controlled load, C typically grows at the same order as N, so we often summarize resize cost as O(N). If the caller explicitly requests a very large initial capacity, allocation cost must also be evaluated against the requested capacity, not just the current number of mappings.

A loop like "for each value to find, call `containsValue`" can turn a problem into multiple full scans. Do not apply the O(1) conclusion of key lookup to a value-side query.

When you need to read both keys and values, iterating `entrySet` retrieves them from the same mapping, avoiding an extra `get` per key. Even so, a HashMap traversal still depends on both the table and the number of nodes, rather than becoming a constant-time lookup.

## 5. Hash Function Quality: Correct Contract First, Good Distribution Second

### Mandatory Correctness Condition

If two objects are equal according to `equals`, their `hashCode` values must be equal. Conversely, unequal objects are still allowed to have the same hash code.

A hash function that returns 0 for every key can satisfy this mandatory condition. It is not wrong merely because it causes collisions; the issue is that performance can be very poor. [Object.hashCode Contract, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).

Meanwhile, if `equals` treats two keys as the same business object but `hashCode` produces two different codes, that is a correctness bug. HashMap may look in the wrong places before ever having a chance to call `equals`. Do not treat this bug as a speed optimization issue.

### Useful Distribution for Real Data

A suitable hash function needs to use meaningful identifying information and create enough differentiation across the actual key domain. The following choices often produce poor distributions:

~~~text
Returning a constant for every key.
Using only a boolean flag for millions of keys.
Using only name length when most names have the same length.
Ignoring the sequence number part in a key composed of group and sequence number.
Combining multiple fields with an operation that has too much symmetry on real data.
~~~

For example, consider a key with two fields `x` and `y`. If the hash is just `x + y`, then pairs `(1, 9)`, `(2, 8)`, and `(3, 7)` all produce code 10. This does not by itself violate the contract, but structured data like this can cause far more collisions than expected.

The goal is not "a distinct hash code for every key." That cannot be guaranteed for an object domain larger than the `int` domain. The goal is to uphold the contract and avoid a hashing scheme that discards most of the distinguishing information of the stored data.

### Different Codes Can Still Share a Bucket

The table has a finite number of buckets. Two different codes can still map to the same index. Evaluating quality solely by counting distinct `hashCode` values does not fully describe bucket distribution.

OpenJDK applies bit-mixing to part of the hash code before selecting a position. That mechanism can help differences in higher bits participate in distribution, but it cannot create differences when every key returns the same code. An internal mixing step cannot replace a proper `hashCode` design.

### Key Data Must Be Stable

Both correctness and performance become hard to reason about if a key mutates the fields involved in `equals`/`hashCode` after being placed in a Map. In that case, you do not just face a slow lookup; you may fail to find the mapping through normal lookup paths.

Using immutable keys or stable identifying data keeps distribution analysis meaningful. A `record` with a `String` field and an integer is a simple example; a `record` containing a mutable collection still requires examining its inner contents.

## 6. Worst Case: When Many Keys Share One Code

In a chained bucket, if there are L keys to distinguish, looking up a non-existent key may have to examine all L candidates. When L = N, the number of candidates to examine can grow linearly with the total number of mappings.

It is not only shared bucket indices that matter. If many candidates share the exact same internal hash code, the hash comparison step cannot eliminate them, requiring further key identification. A constant hash function creates that exact situation.

The difference as N grows:

~~~text
Good distribution:
N grows, but the average candidate group stays small
-> expected lookup cost does not grow with N.

All share the same code:
N grows, making the hard-to-distinguish group larger
-> a missing-key lookup may have to examine nearly the entire group.
~~~

If adding each new key must also rule out many existing keys before confirming it is not already present, the total work to build the Map on an adverse dataset can grow sharply, even quadratically. You cannot take the expected cost of a single `put` under good conditions and promise that total time for systematically colliding data.

Increasing capacity does not by itself solve the case where all keys have the same code. They continue to select the same bucket at every capacity. To understand improvements from resizing, you must distinguish collisions caused by bucket masking from identical full hash codes.

## 7. What Do Tree Buckets Help With and What Do They Not Guarantee?

OpenJDK can convert a crowded bucket into a tree structure under implementation-defined conditions. A balanced tree reduces height, but searching down a single branch also requires enough information to decide which way to go.

When hash codes differ, or when keys have a suitable `Comparable` relationship to distinguish keys with the same code, the algorithm can use that information to choose a direction. For keys with the same code that are not comparable and not equal to the target key, a search may have to visit multiple branches so as not to miss an equal key.

The `TreeNode.find` search path in OpenJDK 17 shows branches probing multiple subtrees when a suitable comparison direction cannot be determined. Therefore, "the bucket became a tree" does not automatically imply "every `get` is guaranteed O(log N)" for all key types. [HashMap Source Code, OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java).

An illustration:

~~~text
                  many keys with the same code
                               |
           +-------------------+-------------------+
           |                                       |
distinguishable ordering                no distinguishing direction
           |                                       |
can pick one branch                     may have to examine multiple branches
at each search step                     to rule out equal keys
~~~

This is how to read the algorithm, not a claim that `Comparable` should always be added to every key just to optimize HashMap.

If `Comparable` is used, the ordering relation must be correct and fit the data. A `compareTo` that always returns 0 for distinct keys does not provide the directional guidance needed. Do not add an arbitrary or contract-violating ordering and expect it to fix a poor hash function.

In our experiment, the ordered key class uses `id`, which is also the data that defines `equals`. This provides a clear example of both same-code cases: without distinguishing order and with distinguishing order.

## 8. A Java 17+ Program to Count Lookup Work

The file `HashMapCostDemo.java` creates three immutable key types:

| Class | Hashing Strategy | Implements Comparable? |
| --- | --- | --- |
| SpreadKey | Returns `id` | No |
| SameHashKey | Always returns 0 | No |
| OrderedSameHashKey | Always returns 0 | Yes, compares `id` |

The program uses `id` values from 0 to N - 1, then looks up `id` -1, which is not in the Map. Before this lookup, the counters are reset so they do not include the cost of building the Map. Afterward, the program also checks a present key to ensure the experiment does not merely create an unsearchable dataset.

An initial capacity of 64 is chosen so the cases with many same-code keys can enter OpenJDK 17's tree bucket mechanism. No reflection is used to access private tables. The specific counts are experimental observations cross-checked against the source code, not a fixed call-count contract across all JVM versions.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.function.IntFunction;

public class HashMapCostDemo {
    static long hashCalls;
    static long equalsCalls;
    static long compareCalls;

    record SpreadKey(int id) {
        @Override
        public int hashCode() {
            hashCalls++;
            return id;
        }

        @Override
        public boolean equals(Object other) {
            equalsCalls++;
            return other instanceof SpreadKey key && id == key.id;
        }
    }

    record SameHashKey(int id) {
        @Override
        public int hashCode() {
            hashCalls++;
            return 0;
        }

        @Override
        public boolean equals(Object other) {
            equalsCalls++;
            return other instanceof SameHashKey key && id == key.id;
        }
    }

    record OrderedSameHashKey(int id) implements Comparable<OrderedSameHashKey> {
        @Override
        public int hashCode() {
            hashCalls++;
            return 0;
        }

        @Override
        public boolean equals(Object other) {
            equalsCalls++;
            return other instanceof OrderedSameHashKey key && id == key.id;
        }

        @Override
        public int compareTo(OrderedSameHashKey other) {
            compareCalls++;
            return Integer.compare(id, other.id);
        }
    }

    static void resetCounts() {
        hashCalls = 0;
        equalsCalls = 0;
        compareCalls = 0;
    }

    static <K> void measure(
            String label, int n, IntFunction<K> keyFactory) {
        Map<K, Integer> map = new HashMap<>(64);
        for (int id = 0; id < n; id++) {
            map.put(keyFactory.apply(id), id);
        }

        resetCounts();
        Integer missing = map.get(keyFactory.apply(-1));
        long missHash = hashCalls;
        long missEquals = equalsCalls;
        long missCompare = compareCalls;

        Integer found = map.get(keyFactory.apply(n - 1));
        boolean correct = map.size() == n
                && missing == null
                && found != null
                && found == n - 1;
        if (!correct) {
            throw new AssertionError("Unexpected map result");
        }

        System.out.println(label + " n=" + n
                + " missingHash=" + missHash
                + " missingEquals=" + missEquals
                + " missingCompare=" + missCompare
                + " correct=" + correct);
    }

    public static void main(String[] args) {
        for (int n : new int[] {32, 64, 128}) {
            measure("spread", n, SpreadKey::new);
            measure("sameHash", n, SameHashKey::new);
            measure("orderedSameHash", n, OrderedSameHashKey::new);
        }

        Map<SameHashKey, Integer> small = new HashMap<>(64);
        for (int id = 0; id < 4; id++) {
            small.put(new SameHashKey(id), id);
        }
        resetCounts();
        Integer missing = small.get(new SameHashKey(-1));
        System.out.println("small collision n=4 missing=" + missing
                + " equals=" + equalsCalls);

        Map<SpreadKey, Integer> map = new HashMap<>();
        map.put(new SpreadKey(7), 10);
        Integer previous = map.put(new SpreadKey(7), 20);
        System.out.println("equal key replacement old=" + previous
                + " size=" + map.size()
                + " value=" + map.get(new SpreadKey(7)));
    }
}
~~~

Compile and run with JDK 17 or newer supporting the target version:

~~~shell
javac --release 17 -encoding UTF-8 HashMapCostDemo.java
java HashMapCostDemo
~~~

The program uses Java 17-compatible syntax and APIs. It requires no external libraries, does not measure time, and does not print Map iteration order.

Exact stdout:

~~~text
spread n=32 missingHash=1 missingEquals=0 missingCompare=0 correct=true
sameHash n=32 missingHash=1 missingEquals=33 missingCompare=0 correct=true
orderedSameHash n=32 missingHash=1 missingEquals=5 missingCompare=3 correct=true
spread n=64 missingHash=1 missingEquals=0 missingCompare=0 correct=true
sameHash n=64 missingHash=1 missingEquals=65 missingCompare=0 correct=true
orderedSameHash n=64 missingHash=1 missingEquals=6 missingCompare=4 correct=true
spread n=128 missingHash=1 missingEquals=0 missingCompare=0 correct=true
sameHash n=128 missingHash=1 missingEquals=129 missingCompare=0 correct=true
orderedSameHash n=128 missingHash=1 missingEquals=7 missingCompare=5 correct=true
small collision n=4 missing=null equals=4
equal key replacement old=10 size=1 value=20
~~~

### Column Explanations

`missingHash` is the number of `hashCode` calls during the missing-key lookup. `missingEquals` is the number of key `equals` calls. `missingCompare` is the number of `compareTo` calls. They are captured before running the present-key check.

`correct=true` confirms the size is N, key -1 is not found, and key N - 1 still retrieves the right value. It does not mean the data has good performance.

Static counters are only for observation in a single-threaded program. Do not put this counting approach into a multi-threaded benchmark and assume it has no impact on execution.


## 9. Reading the Results: Which Data Causes Work to Grow?

### Well-Distributed Keys

With `SpreadKey`, the example `id`s produce sufficiently distinct hash codes for the tables used. Looking up -1 yields `missingEquals=0` across all three sizes.

Do not conclude that the lookup did no work. It still called `hashCode` once, computed the position, and checked information in the table. In the example, the missing key's code did not match the stored codes at the selected slot, so `equals` was not needed to rule out candidates.

The valuable observation is that as N grows in these sets, equality comparison work does not grow with N. This aligns with expectations for a well-distributed table, though it does not prove that every key set whose `hashCode` returns `id` can never collide.

### Same-Code Keys Without Ordering

With `SameHashKey`:

| N | missingEquals |
| --- | --- |
| 32 | 33 |
| 64 | 65 |
| 128 | 129 |

The number of equality comparisons grows nearly linearly with N. A missing-key lookup must rule out the same-code keys rather than being guided directly by a distinguishing ordering relation.

Why N + 1 instead of N? In the search path observed in this implementation, there is a check on the root node before entering the tree search method; that node can be equality-checked again along the tree search path. An extra constant of one does not change the conclusion about the growth rate.

The small case N = 4 has four `equals` calls, consistent with scanning a small chain. From these numbers, do not deduce the exact node count required for every Map to treeify. Conversion also depends on implementation conditions, and we do not directly measure all internal events with an `equals` counter.

### Same-Code Keys With Consistent Ordering

With `OrderedSameHashKey`:

| N | missingEquals | missingCompare |
| --- | --- | --- |
| 32 | 5 | 3 |
| 64 | 6 | 4 |
| 128 | 7 | 5 |

In the experiment, when the number of keys doubles, the number of comparisons grows slowly. The `compareTo` relation on `id` allows choosing a direction instead of probing multiple branches.

This demonstrates the effect of ordering information in a specific scenario. It is not a recommendation to write a constant `hashCode` and then add `Comparable` to turn it into a good hashing design. The entire group still piles into one bucket, and operations also incur ordering comparisons.

To state a guarantee for an application, you need to specify the key type, comparison relations, data domain, and implementation version. Three measurement lines here do not replace that analysis.

### Replacing a Value by an Equal Key

The final line shows that putting a new key equal to an existing key keeps `size` at one and replaces the value from 10 to 20. A key-based insertion must detect an existing key; hash quality must not alter the "one mapping per key" semantics.

Result correctness and amount of work are two separate criteria. The `SameHashKey` group still looks up keys accurately, but requires far more comparisons.

## 10. Designing a Practical Hash Key

### Choose the Right Identifying Data

For example, a customer identified by region and customer number:

~~~java
record CustomerKey(String region, long number) {
}
~~~

With suitable component data, a `record` generates `equals`/`hashCode` based on its components. This is often an easier starting point to verify than a hand-written class missing one of the two methods.

If you implement `hashCode` yourself, use the same identifying semantics as `equals`. A hash function that only uses `region.length()` and ignores `number` can cause many customers in the same region to collapse into very few codes.

Do not add non-identifying data just to "diversify the code": if `equals` ignores that field while `hashCode` depends on it, two equal objects can produce different codes. Distribution optimization must not break correctness.

If business logic compares a string case-insensitively or normalizes a code, that rule must be applied consistently when constructing the key and computing both `equals` and `hashCode`. Normalizing on one side but not the other creates data that is hard to look up or falsely equates keys.

### Combine Fields Purposefully

`Objects.hash` or a `record`'s generated code can help implement a multi-field key using a familiar pattern. They do not guarantee zero collisions on every dataset, and must still be applied to the exact identifying fields.

Do not tweak `hashCode` with an arbitrary formula just because a small test shows fewer collisions. Keep a design with a clear contract, test on representative data, and only optimize further when a significant problem is observed.

For structured data, pay attention to common clusters: codes with shared prefixes, many consecutive numbers, many keys of the same category, or multiple fields with fixed values. Quality should be evaluated on those clusters, not just on a randomly generated set.

### Being Equal Is Not Enough If Comparison Is Expensive

A key with well-distributed codes whose `hashCode` must traverse thousands of elements every time can still make `get` slow. Likewise, `equals` may have to inspect a lot of data even when called only once.

You can choose a more compact immutable identifier if it genuinely represents the same lookup identity. Do not strip away necessary information and treat merging two distinct entities into one as a performance improvement.

For immutable keys where computing the hash is genuinely expensive, a design can safely compute and cache the code. That approach must ensure the relevant data cannot change; caching an old code in a mutable key causes a contract bug, not a valid optimization.

Also do not assume every key type recomputes the same amount of data on every `hashCode` call. For instance, some classes have internal optimizations; to evaluate the specific cost, you must read the contract or implementation of the exact type being used.

## 11. Capacity and Load Factor: Optimizing for Both Time and Memory

The load factor relates to when the table resizes. Keeping the table too tight can increase the number of candidates; keeping it too sparse wastes more slots and affects operations that traverse the table.

If you expect N mappings and load factor f, the model for the capacity needed to avoid hitting the threshold is approximately:

~~~text
C needs to be at least approximately N / f.
~~~

For example, N = 1000, f = 0.75:

~~~text
1000 / 0.75 ≈ 1333.33.
~~~

In OpenJDK 17, table capacity follows powers of two, so the actual suitable capacity can be larger than this quotient. This is why you should not equate the initial capacity argument with "the number of elements that can be stored with a guarantee of no resize."

When working with Java 17, the constructor `new HashMap<>(initialCapacity)` takes a requested initial capacity. It is not a mapping quota and does not make the Map reject new keys when `size` reaches that argument.

Choosing capacity should be based on real metrics and workload patterns:

| Primary Workload | What to Consider |
| --- | --- |
| Bulk-loading many mappings of known scale | Appropriate capacity can reduce resize passes |
| Small and frequently changing Map | Very large pre-allocation is usually unwarranted |
| Frequent report iterations | An overly sparse table can require scanning many empty slots |
| Data with complete hash collisions | Increasing capacity alone will not separate those keys |
| Single-request latency-sensitive systems | Observe resizes, allocations, and garbage collection, not just averages |

Pre-allocating more can reduce some later work, but increases upfront memory and allocation cost. No arbitrarily chosen capacity or load factor is optimal for every application.

In heap-allocated structures, node objects, table slots, and key/value data all contribute to total memory. Do not evaluate memory usage by `size` alone.

If a Map has grown far larger than actual needs, consider its lifecycle and replacing the structure when appropriate. That is a data-management decision; do not clear and rebuild it while others are using it, or assume a cleanup operation provides any capacity guarantees.

## 12. Measuring Time to Answer the Right Question

Method counters help reveal how many candidates must be compared, but they do not reflect total runtime. A very cheap `equals` call can be vastly different from an `equals` call over large data; identical call counts also exclude CPU caches, allocations, JIT compilation, and garbage collection.

When you need to measure speed in the JVM, JMH is the tool developed by OpenJDK to build benchmarks at various scales. [JMH Project](https://github.com/openjdk/jmh).

A meaningful benchmark should clearly define:

- Are you measuring successful lookups, missing-key lookups, or a mixed ratio?
- Are you measuring `get` on an already-built Map, or including key creation and Map construction?
- Are you measuring `put` adding new keys, replacing old values, or a batch that triggers resizing?
- Is the input key the exact same reference already stored, or a new object equal to the stored key?
- Are key sizes and distributions representative of the application?
- Do you need to observe per-operation latency and memory usage in addition to throughput?

Separate the data-building step from the measured section if the goal is lookup. If the goal is data ingestion, construction must be included in the measured section. The same code can answer two different questions depending on where the measurement boundary is placed.

For interpretable results, you need warmup phases, appropriate independent runs, keeping results consumed (preventing dead-code elimination), and controlling off-target work such as printing text inside the measured section. Record the JDK, configuration, and test data so comparisons have a solid basis.

Do not draw a general conclusion about HashMap from timing a few operations on a very small Map. A sample where all data fits in CPU cache with no resize describes a specific favorable condition.

The lesson's program intentionally avoids `System.nanoTime` so it does not present an absolute-looking nanosecond figure. It chooses a narrower, clearly testable question: how the number of key method calls changes as distribution and ordering capability change.

If timing results do not match predictions from `equals` counts, look for the missing cost component in the model. Do not rush to conclude complexity analysis is wrong just because a small dataset has different constant factors.

## 13. Fallacies to Avoid

| Fallacy | What Is Overlooked | More Accurate Statement |
| --- | --- | --- |
| Every `get` is O(1) on all data | Distribution conditions and key cost | Expected constant time when conditions are suitable |
| `put` is O(1), so there are no slow calls | Resizing and allocation costs | Amortized evaluation and per-call observation |
| Bucket treeification makes all lookups O(log N) | Ability to direct search by hash/ordering | State the key type and supported search path |
| A constant `hashCode` violates the contract | Contract only requires equal keys to share a code | Can be semantically valid but perform poorly |
| Many distinct codes mean no bucket collisions | Codes still map into a finite number of buckets | Evaluate distribution after bucket selection |
| Increasing capacity fixes all collisions | Identical full hash codes | Revisit key code design and data |
| Few `equals` calls means low total cost | Hashing, ordering, memory, and other work | Use the full cost model |
| `correct=true` means fast | Only verifies functional output | Evaluate correctness and performance separately |
| `Comparable` is a substitute for a good `hashCode` | Ordering only helps in some cases | Keep hash quality as the primary goal |
| HashMap is thread-safe because lookups are fast | Concurrency is independent of complexity | Use an appropriate concurrency contract |
| Benchmarking `get` with the same stored object represents all queries | Same reference can skip `equals` | Test both identical-reference and new equal keys |
| Random data is all you need | Real data has structure and collision clusters | Combine representative data and adverse cases |

Performance metrics must be tied to specific conditions. A system with many missing-key queries can expose collisions differently from one that mostly looks up a few hot keys. A Map rebuilt repeatedly also differs from a Map built once and then read-only.

## 14. Exercises and Solutions

### Exercise 1 — Explaining O(1) With Proper Conditions

Someone says: "HashMap.get always takes the same number of steps regardless of the data." How should this statement be corrected?

**Solution:** `get` has constant expected cost when hash codes distribute well and key operation costs are properly accounted for. A crowded bucket or an expensive `hashCode`/`equals` can make a lookup costlier. O(1) also does not claim every call takes the exact same number of steps.

### Exercise 2 — Does α Bound the Longest Bucket?

N = 8, C = 16, α = 0.5. Can we conclude that each bucket holds at most one element?

**Solution:** No. α is an average across the whole table; data can pile many or all mappings into a single bucket. To assess the worst case, you must examine the distribution rather than just the average ratio.

### Exercise 3 — Expectation and Amortization

A `put` call hits a table resize and becomes noticeably slower. Does this contradict the description of `put` having amortized expected constant cost?

**Solution:** No. Amortization spreads expensive calls across an entire sequence of operations; it does not promise every single operation is cheap. Expectation over key distribution is another condition that must hold.

### Exercise 4 — Does a Constant Hash Always Produce Wrong Results?

Every key returns a `hashCode` of 0, while `equals` properly compares immutable data. Must the Map return incorrect results?

**Solution:** No. Equal keys still share the same code, so the required condition can hold. Results can still be correct, but lookups must do more work. The program shows `correct=true` for `SameHashKey`, while `equals` counts grow linearly.

### Exercise 5 — Interpreting N + 1

At N = 128, `SameHashKey` has `missingEquals` equal to 129. Is HashMap storing 129 keys?

**Solution:** No; `size` is still 128. The implementation's search path can re-check a node at a different stage, producing one extra `equals` call. Call count is not the number of distinct nodes stored.

### Exercise 6 — Is a Tree Enough to Guarantee Logarithmic Time?

Two unequal keys have the same hash code and are not comparable. Why does a balanced tree still not guarantee following only one search branch per step?

**Solution:** Small height alone does not tell you which side an equal key lies on when hash code and ordering information cannot distinguish them. To avoid missing an equal key, the algorithm may have to search multiple branches. You must consider the branching rule, not just the tree shape.

### Exercise 7 — Designing a Multi-Field Key

`CustomerKey` has `region` and `number`, and `equals` checks both. `hashCode` only uses `region.length()`. Is this a correctness bug or primarily a performance risk?

**Solution:** If equal objects always have the same `region` and `number`, then `region.length()` is also equal, so the hashing scheme may still uphold the mandatory contract. However, it loses almost all distinguishing information between customers and can distribute very poorly. A design using the appropriate identifying components will achieve a much more useful distribution.

### Exercise 8 — Hash Function Using a Field Ignored by equals

`equals` only checks the customer ID, whereas `hashCode` also includes the update timestamp. What problem can occur for two objects with the same ID but different timestamps?

**Solution:** They are equal according to `equals` but can have different hash codes, violating the contract. This is a correctness bug, not merely a collision or slowdown. Eliminate the inconsistency before optimizing speed.

### Exercise 9 — Choosing Capacity

You expect 1000 mappings and a load factor of 0.75. Why should you not assume a constructor argument of 1000 is the exact number of mappings guaranteed to fit before resizing?

**Solution:** The argument is a requested capacity, while the resize threshold depends on the actual capacity and load factor. The model needs roughly N/f, plus the implementation's capacity rules. You must also consider memory, rather than arbitrarily increasing it to a very large number.

### Exercise 10 — Measuring the Wrong Work

A benchmark builds a Map, generates keys, calls `get`, and prints results on every iteration. Can that entire duration be called the `get` latency of a pre-built Map?

**Solution:** No. It includes a lot of work other than lookup. If you need to measure `get`, prepare the data outside the measured section and consume results using an appropriate method. If you want to measure the whole pipeline, describe the result as that pipeline's duration.

### Exercise 11 — Zero equals Count

`SpreadKey` yields `missingEquals` equal to 0. Can we conclude the lookup did not read the table or had no cost?

**Solution:** No. It still computes `hashCode`, computes the slot position, and performs internal checks. The counter only indicates that calling `equals` was not needed in the observed case.

### Exercise 12 — Value Structure and Expensive Keys

A Map has a very small N, but the key's `hashCode` must traverse a list of M elements every time. When saying `get` is O(1) in N, what is missing?

**Solution:** The cost in M of the key itself is missing. A complete model must account for H, not just the number of nodes in a bucket. If the list can also mutate while the key is stored, that is additionally a risk of violating key stability.

## 15. A Grounded Performance Evaluation Process

First, verify `equals`/`hashCode` and key stability to ensure correct results. Next, characterize the real data: number of mappings, key clusters, hit/miss query ratios, update frequency, and iteration needs.

Use a controlled experiment to observe work counts when you need to explain mechanisms. When you need timing numbers, create a benchmark with clear boundaries suitable for the JVM. Separate conclusions about a specific dataset from promises for the entire application.

HashMap delivers strong expected performance when hash codes uphold the contract, distribute appropriately, and key costs are controlled. Worst cases still need to be understood, especially when many keys share a code or when an update must perform extra allocation and resizing work.
