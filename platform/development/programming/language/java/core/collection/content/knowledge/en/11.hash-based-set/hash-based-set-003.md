# Capacity, Load Factor, and HashSet Iteration Cost

A `HashSet` with 100 elements does not necessarily have the same iteration cost as every other `HashSet` that also has 100 elements. Beyond the number of members, you also have to consider the size of the bucket table it is currently holding.

Three related but distinct concepts:

- **Size:** how many members are present.
- **Capacity:** how many buckets the underlying table has.
- **Load factor:** the parameter that determines the load threshold used to decide when to grow the table.

Choosing a capacity that is too small can lead to frequent table resizing. Choosing one that is too large, or a load factor that is too low, can waste memory and make iterating over a sparse table expensive. This article explains how to balance those factors, with Java 17-compatible examples.

## 1. The mental model: members and buckets

`HashSet` is backed by a `HashMap`; the elements of the set are used as keys. The bucket table helps select a candidate region when looking up or adding a key.

A table with 8 buckets holding only 3 members can be visualized like this:

~~~text
bucket 0:  empty
bucket 1:  [A]
bucket 2:  empty
bucket 3:  [B] -> [C]
bucket 4:  empty
bucket 5:  empty
bucket 6:  empty
bucket 7:  empty

size = 3
capacity = 8
non-empty buckets = 2
~~~

This diagram is an explanatory model, not state read directly from a specific Java object.

### 1.1. Capacity is not an element limit

A single bucket can hold multiple keys due to collisions. When needed, the table can grow. Therefore, capacity is not "the maximum number of elements this set is allowed to contain."

Conversely, allocating a large capacity does not pre-populate the set with members. `new HashSet<>(1000)` still has a size of 0 immediately after creation.

### 1.2. Size does not tell you the current capacity

Two sets with the same three members can have different histories:

- One set was just created and had three elements added.
- One set was pre-allocated with a very wide table.
- One set once held hundreds of thousands of members and then had almost all of them removed.

Having the same current contents does not mean having the same underlying storage structure. That is why capacity must be considered when discussing iteration cost.

The [Java 17 HashSet documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) describes iteration time in terms of both the number of members and the capacity of the backing map.

## 2. Load factor: distinguishing the parameter from actual load

Let n be the size, and c be the capacity of the allocated table.

### 2.1. Actual load is n/c

We can use the ratio:

~~~text
actual load = n / c
~~~

If n = 3 and c = 16, the actual load is 0.1875. If n = 12 and c = 16, it is 0.75.

This is not the ratio of non-empty buckets. A bucket containing multiple keys increases size but contributes only one non-empty bucket.

For example, if all three keys land in the same bucket, with c = 16:

~~~text
n/c = 3/16
non-empty buckets / c = 1/16
~~~

The two ratios describe two different things.

### 2.2. Configured load factor does not always equal n/c

When creating `new HashSet<>(16, 0.75f)`, the value 0.75 is a parameter used to determine the resize threshold. It does not force the table to always be exactly 75% full.

After a few insertions, after a table resize, or after many removals, n/c can be much smaller. Do not read the configured value as a measurement of current state.

According to [Java 17 HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), capacity and load factor together affect table resizing and the trade-off between time and space.

### 2.3. Threshold is typically related to capacity × load factor

Let α be the configured load factor. In typical cases, the key-count threshold is determined approximately as:

~~~text
threshold = capacity * alpha
~~~

Implementations must handle integer conversion, rounding, and bounds. For the small default values considered here, for example c = 16, α = 0.75 gives threshold = 12.

Threshold does not count non-empty buckets. Multiple keys colliding in the same bucket still count toward size.

### 2.4. A load factor greater than 1 is not automatically an invalid parameter

Do not memorize a rule that "load factor must be between 0 and 1." In the referenced OpenJDK implementation, positive values greater than 1 can be accepted; for example, 2.0.

This means the key-count threshold can be greater than the number of buckets. The structure can still store multiple keys in a single bucket.

Zero, negative values, and NaN are rejected in the OpenJDK version under consideration. Accepting a value does not prove it is a good choice for real workloads. The default 0.75 is the standard starting point; only change it when you have a clear requirement and supporting evidence.

## 3. Table resizing: when does it happen and what work does it cost?

The numeric details in this section reference [OpenJDK 17 HashMap, build jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java), not a mandatory formula that every set implementation must use.

### 3.1. Threshold example with a 16-bucket table

In a sequence of adding distinct keys without special collision conditions triggering early resizing, the typical model is:

| Size after add | Model capacity | Model threshold |
|---:|---:|---:|
| 1 | 16 | 12 |
| 12 | 16 | 12 |
| 13 | 32 | 24 |
| 24 | 32 | 24 |
| 25 | 64 | 48 |

A new key that pushes size past the threshold can trigger a resize. Adding a key that is already present does not increase size, so it is not a "new member" that crosses the threshold in that way.

Distinguish "reaching the threshold" from "exceeding the threshold" in this model: size 12 can still stay in a 16-bucket table, while size 13 crosses the threshold of 12.

### 3.2. Capacity is typically rounded according to the backing table's rules

HashMap in this build uses power-of-two table lengths. An initial capacity request of 1000 can result in an allocated table of 1024 buckets, not an array of length exactly 1000.

Therefore, the constructor argument, the rounded capacity, and the threshold are three distinct values. Do not infer the actual capacity simply by reading back the number passed to the constructor.

The table is also allocated lazily: creating an empty set does not mean the entire bucket array is allocated at that exact moment. There is no public getter on `HashSet` to read its capacity.

### 3.3. Resizing involves allocation and redistribution

When the table grows, a new bucket array is needed and existing entries must be redistributed. Some keys move to different buckets because the index mask has changed.

As a result, adding an element can be cheap in the common case but more expensive when a resize occurs. Analyzing a sequence of operations must account for the resizing work before speaking about expected/amortized cost.

Do not interpret O(1) for `add` as meaning "every `add` never allocates and never touches existing entries."

### 3.4. The size threshold is not the only resize trigger on every path

When there are many collisions in a single bucket and the table is still small, this OpenJDK build can resize the table as part of its collision-handling mechanism before the simple size × load factor explanation accounts for the situation.

Therefore, the table above and the simulation program only illustrate the normal growth path. Do not turn them into a test asserting that every key set must have the exact same capacity after each insertion.

Pre-sizing calculations help reduce size-threshold resizes; they are not an unconditional guarantee of all internal behavior.

## 4. Why does iterating a HashSet depend on both size and capacity?

### 4.1. Looking up one element and iterating all elements are two different jobs

A single `contains(key)` computes the hash and selects a candidate bucket. It does not need to walk the entire table when keys and structure are managed normally.

An iterator must find every member. In a hash-table model, it walks through the bucket slots and the entries stored in non-empty buckets.

The general work can be split into:

~~~text
work to walk the bucket table       ~ c
work to yield/process members       ~ n

total ~ c + n
~~~

Hence, iteration cost is commonly expressed as **O(c + n)**, excluding whatever work the application performs on each element.

### 4.2. Three iterations of a for-each body do not mean only three internal steps

If a set contains exactly three elements, the `for-each` loop body runs three times. However, to find the next elements, the iterator may have to skip empty bucket regions between them.

Two sets with the same size = 3 and the same sum of values will execute the loop body the same number of times. That does not measure the work of locating entries in the backing table.

The program in the practice section prints two separate groups:

- The number of elements returned by the real iterator.
- The number of buckets and elements scanned in an intentionally fixed model.

Do not add those numbers together into a JVM timing measurement.

### 4.3. When c is on the same order as n, O(c+n) can simplify to O(n)

If the table grows proportionally with the data and has not been made sparse by heavy removals, capacity can be on the same order as the number of members. Under those conditions, describing iteration as linear in n is reasonable.

However, if c is much larger than n, dropping c from the analysis omits a major factor. This commonly happens due to:

- Pre-allocating a capacity far larger than the actual number of members.
- Choosing a very low load factor.
- A set that was once large and then had most of its data removed.
- Estimating from total input records when there are only a few distinct keys.

You do not need a new benchmark to see that "iteration always depends only on size" is an incomplete statement; the documented contract explicitly mentions capacity as well.

### 4.4. Do not treat c+n as an exact instruction count or nanosecond count

The model shows which quantities affect the amount of work. Actual runtime also depends on memory layout, key types, garbage collection, JIT compilation, and the work inside the loop body.

Implementations may also have fast paths for special cases, such as finishing quickly when there are no elements. Do not read c+n as a mandate that every empty set must scan every bucket.

The key takeaway is: when a wide table still holds data, empty buckets can create cost that counting only the yielded elements fails to show.

## 5. Choosing initial capacity from expected member count

### 5.1. A passed-in number is not automatically the expected size

If you expect to hold 1000 distinct members, `new HashSet<>(1000)` does not mean the resize threshold will be 1000.

Under the OpenJDK model being examined:

~~~text
initial request = 1000
rounded capacity = 1024
load factor = 0.75
threshold = 768
~~~

If you keep adding up to 1000 distinct keys, the size threshold will be crossed before reaching 1000.

### 5.2. Estimating to reduce size-threshold resizes

A reference calculation for small numbers, load factor α, and expected member count N is:

~~~text
initial capacity request near ceil(N / alpha)
~~~

With N = 1000, α = 0.75:

~~~text
ceil(1000 / 0.75) = 1334

round up to power of 2 -> 2048
threshold -> 1536
~~~

This explains why the actual bucket count can be noticeably larger than the expected member count. It does not mean you should always over-allocate by a fixed factor in every problem.

If you build a helper for large inputs, you must handle integer range, type conversions, and memory limits. The calculation in the program only uses the known example of 1000 and is not presented as a complete sizing function for arbitrary values.

In addition, the special collision-handling paths noted earlier can make resize conditions more complex than the size formula alone. The goal here is a grounded estimate, not a promise of absolute control over internals.

### 5.3. Estimate distinct keys, not raw record count

If a source has one million records but only a few hundred distinct codes, the set's capacity serves a few hundred members, not one million `add` calls.

Estimating from total records can make the table excessively sparse. Use the expected number of distinct members if known, or let the set grow with actual data and evaluate afterward.

The collection-taking constructor must also estimate before deduplication finishes. In [OpenJDK 17 HashSet](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashSet.java), initializing based on the source collection's size can create a table much wider than the final distinct key count if the input has heavy duplication.

Therefore, "passing the entire source into the constructor" is syntactically convenient but does not replace considering data distribution when memory and subsequent iterations matter.

### 5.4. Do not lower load factor out of habit

A lower load factor generally encourages using more buckets for the same number of keys. That can reduce some collisions when hashes distribute well, but it increases table footprint and can make iteration sparser.

A higher load factor can save buckets but places more keys in the same regions and makes lookups harder. Two keys with the same hash code do not separate just because the table is wider.

There is no rule that "a lower load factor makes every operation faster." Consider the mix of lookups, inserts/removals, full iterations, and memory budget.

## 6. After removing many elements, does capacity shrink automatically?

### 6.1. Removing members does not mean shrinking the table to the new size

In the referenced OpenJDK build, normal key removal does not automatically reduce the bucket table length on each removal.

A set that once held many keys and now has only three left can still retain a large table. Its contents have shrunk, but its growth history still affects memory and subsequent iterations.

The fact that a single bucket can change its internal organization as its entry count changes does not mean the entire table is shrunk.

### 6.2. clear empties the set but does not promise to return the bucket array

In this build, `HashSet.clear` delegates to map clearing: it removes entry links from the table and resets the member count to 0, while the bucket array can still be retained for reuse.

Do not conclude that size becoming 0 means capacity also becomes 0, or that memory is immediately returned to the OS. Reclamation timing still depends on references and the JVM.

An empty set may be detected quickly during iteration; that does not prove the backing array has disappeared. When a few members are added back, the table can still be very wide relative to its contents.

### 6.3. Rebuilding the set can make sense at a lifecycle boundary

If the data has permanently shrunk and the set will be kept for a long time, you can consider:

~~~java
Set<Integer> compacted = new HashSet<>(existing);
~~~

This creates a different set structure from the current members, without preserving the old table's capacity history. For small sets in the build under discussion, this initialization reuses the default policy suited to the source size.

However, rebuilding is not free:

- It must iterate the old set, so reading the source may still pay the c+n cost of the wide table.
- Memory is needed for the new set and new entries while the old set still exists.
- Elements are shared by reference, not deep-copied.
- Callers holding references to the old set do not automatically switch to the new set.

If the set is about to grow large again soon, frequent rebuilding only adds allocation work. Choose based on lifecycle, not after every `remove`.

`HashSet` has no public `trimToSize()` method like `ArrayList`. Do not use another collection's API to infer shrinking capabilities for a set.

## 7. Complete program: returned elements and table-scan model

The program has three separate demonstrations:

1. Real sets: checking membership, number of elements yielded by the iterator, and sum.
2. Fixed-bucket model: explicitly counting buckets and elements scanned.
3. Growth/sizing calculations: illustrating small thresholds under the stated conditions.

There is no reflection, no reading of actual capacity, and no timing measurement.

### 7.1. Source code

Save as `HashSetCapacityDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class HashSetCapacityDemo {
    record Returned(int elements, long sum) {}
    record ModelScan(int buckets, int elements, long sum) {}

    static Returned returnedByIterator(Set<Integer> values) {
        int elements = 0;
        long sum = 0;
        for (int value : values) {
            elements++;
            sum += value;
        }
        return new Returned(elements, sum);
    }

    // Fixed-bucket model, not HashSet internals or a benchmark.
    static ModelScan scanFixedBuckets(int capacity, List<Integer> input) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("positive capacity required");
        }
        List<List<Integer>> buckets = new ArrayList<>(capacity);
        for (int index = 0; index < capacity; index++) {
            buckets.add(new ArrayList<>());
        }
        for (int value : input) {
            List<Integer> bucket = buckets.get(Math.floorMod(value, capacity));
            if (!bucket.contains(value)) {
                bucket.add(value);
            }
        }
        int bucketVisits = 0;
        int elementVisits = 0;
        long sum = 0;
        for (List<Integer> bucket : buckets) {
            bucketVisits++;
            for (int value : bucket) {
                elementVisits++;
                sum += value;
            }
        }
        return new ModelScan(bucketVisits, elementVisits, sum);
    }

    // Uses only small numbers to illustrate rounding up to a power of 2.
    static int demoRoundedCapacity(int requested) {
        if (requested < 1 || requested > 1_048_576) {
            throw new IllegalArgumentException("outside demo range");
        }
        int capacity = 1;
        while (capacity < requested) {
            capacity *= 2;
        }
        return capacity;
    }

    static void showInvalid(String name, Runnable constructor) {
        try {
            constructor.run();
            throw new AssertionError("expected IllegalArgumentException");
        } catch (IllegalArgumentException exception) {
            System.out.println(name + ": IllegalArgumentException");
        }
    }

    public static void main(String[] args) {
        List<Integer> keys = List.of(1, 2, 3);
        Set<Integer> small = new HashSet<>(16);
        Set<Integer> wide = new HashSet<>(1024);
        small.addAll(keys);
        wide.addAll(keys);
        System.out.println("same members: " + small.equals(wide));
        System.out.println("actual small returned: " + returnedByIterator(small));
        System.out.println("actual wide returned: " + returnedByIterator(wide));
        System.out.println("model capacity16: " + scanFixedBuckets(16, keys));
        System.out.println("model capacity1024: " + scanFixedBuckets(1024, keys));
        System.out.printf("duplicate add: returned=%s, size=%d%n",
                small.add(2), small.size());

        int capacity = 16;
        int threshold = 12;
        for (int size = 1; size <= 25; size++) {
            if (size > threshold) {
                capacity *= 2;
                threshold = (int) (capacity * 0.75f);
            }
            if (size == 1 || size == 12 || size == 13 || size == 24 || size == 25) {
                System.out.printf("growth model: size=%d, capacity=%d, threshold=%d%n",
                        size, capacity, threshold);
            }
        }

        int expected = 1000;
        int rawRequested = expected;
        int plannedRequested = (int) Math.ceil(expected / 0.75d);
        int rawCapacity = demoRoundedCapacity(rawRequested);
        int plannedCapacity = demoRoundedCapacity(plannedRequested);
        System.out.printf("request1000 model: capacity=%d, threshold=%d%n",
                rawCapacity, (int) (rawCapacity * 0.75f));
        System.out.printf("plan1000 model: requested=%d, capacity=%d, threshold=%d%n",
                plannedRequested, plannedCapacity, (int) (plannedCapacity * 0.75f));

        Set<Integer> sparse = new HashSet<>();
        for (int value = 0; value < 1000; value++) {
            sparse.add(value);
        }
        for (int value = 3; value < 1000; value++) {
            sparse.remove(value);
        }
        Set<Integer> rebuilt = new HashSet<>(sparse);
        System.out.println("after removals: " + returnedByIterator(sparse));
        System.out.printf("rebuilt: sameMembers=%s, returned=%s%n",
                sparse.equals(rebuilt), returnedByIterator(rebuilt));
        sparse.clear();
        System.out.println("after clear: size=" + sparse.size());

        showInvalid("negative capacity", () -> new HashSet<>(-1));
        showInvalid("zero load factor", () -> new HashSet<>(16, 0.0f));
        showInvalid("NaN load factor", () -> new HashSet<>(16, Float.NaN));
        Set<Integer> greaterThanOne = new HashSet<>(16, 2.0f);
        System.out.println("load factor 2.0 accepted: size=" + greaterThanOne.size());
        System.out.println("capacity zero accepted: size=" + new HashSet<Integer>(0).size());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 HashSetCapacityDemo.java
java HashSetCapacityDemo
~~~

### 7.2. stdout output

~~~text
same members: true
actual small returned: Returned[elements=3, sum=6]
actual wide returned: Returned[elements=3, sum=6]
model capacity16: ModelScan[buckets=16, elements=3, sum=6]
model capacity1024: ModelScan[buckets=1024, elements=3, sum=6]
duplicate add: returned=false, size=3
growth model: size=1, capacity=16, threshold=12
growth model: size=12, capacity=16, threshold=12
growth model: size=13, capacity=32, threshold=24
growth model: size=24, capacity=32, threshold=24
growth model: size=25, capacity=64, threshold=48
request1000 model: capacity=1024, threshold=768
plan1000 model: requested=1334, capacity=2048, threshold=1536
after removals: Returned[elements=3, sum=3]
rebuilt: sameMembers=true, returned=Returned[elements=3, sum=3]
after clear: size=0
negative capacity: IllegalArgumentException
zero load factor: IllegalArgumentException
NaN load factor: IllegalArgumentException
load factor 2.0 accepted: size=0
capacity zero accepted: size=0
~~~

### 7.3. Explaining the output

Both real sets have the same members 1, 2, 3. The iterator yields exactly three elements summing to 6, even though the initial capacity requests differ.

The fixed model still processes three elements, but it scans 16 or 1024 buckets. This exposes the c term in the formula, not a claim that real runtime differs by exactly 64x.

`scanFixedBuckets` uses Java lists to represent buckets and a simple modulo operation. It does not reproduce HashMap's allocation, hashing, collision handling, treeification, or iterator optimizations. Object counts and byte counts in the model must not be used to estimate real `HashSet` memory usage.

Adding 2 again returns `false` and keeps size = 3. That differs from adding a new key that pushes size past the threshold.

The `growth model` lines only use a size sequence and the standard threshold condition; they do not observe a `HashSet` to count resizes. The 12→13 and 24→25 transitions verify the calculations in the explanation table.

The `request1000` and `plan1000` lines distinguish the constructor request from the rounded capacity and threshold. The rounding helper is intentionally restricted to small numbers for the lesson, not a production sizing API.

After removing 997 of the 1000 keys, the set retains 0, 1, 2, so the element count is 3 and the sum is 3. The new copy has the same members; the program does not infer from equality that the two structures have the same capacity.

The constructor checks demonstrate that negative capacity, zero load factor, and NaN are rejected, while 2.0 is accepted. Capacity 0 is also valid; it creates an empty set that can still accept additions, not a restriction forbidding future elements.

### 7.4. This output is not a benchmark

No nanosecond or byte values are measured. The model counters reflect work explicitly defined in code, while real sets are observed only through the public API.

To compare real performance, you must prepare appropriate data types, fullness/sparseness states, iteration counts, and allocation scope. A single-loop measurement can be skewed by JVM startup, JIT warmup, garbage collection, and machine load.

In particular, do not count `for-each` body executions and treat that as the iterator's total work; that is precisely the distinction this article aims to make.

## 8. When most of the work is iteration, what alternatives exist?

### 8.1. LinkedHashSet walks a chain of entries

`LinkedHashSet` maintains links between entries to provide a deterministic iteration order. The [Java 17 LinkedHashSet documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html) describes iteration time as proportional to the number of elements, independent of capacity in the way `HashSet` table scanning is.

This can be useful if an application needs both uniqueness and frequent iteration over a sparse table. However, it requires extra link storage and link maintenance work; it is not concluded to be better in every respect.

Even if ordering is not required, you can still consider it depending on access patterns, but you should measure when real performance is the deciding criterion.

### 8.2. After deduplication, a List may suffice for the read phase

If you only need a set to deduplicate while building data, and then iterate many times without membership checks afterward, you can create a result list at the boundary between the two phases.

Converting requires one pass over the current set and memory for the list. Subsequent iterations over the list do not need to scan the set's bucket table.

This approach only fits if the contract allows a structurally independent snapshot. If the source set continues to change, the list does not update automatically.

### 8.3. Keeping HashSet with sensible sizing may also be enough

You do not need to switch data structures just because you saw the c+n formula. If capacity and size have a reasonable ratio, the amount of work may already meet your goals.

Simple changes such as removing an overly large pre-size, estimating by distinct key count, or rebuilding at the right lifecycle boundary can solve the issue.

Choose based on the dominant workload: membership lookups, data construction, heavy removals, or repeated iteration. A configuration optimal for one phase is not necessarily optimal for another.

## 9. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Capacity is the current number of elements | It is the number of buckets in the allocated table |
| Capacity is the number of non-empty buckets | Collisions place multiple keys in the same bucket |
| A load factor of 0.75 means 75% of buckets are always used | It is a threshold parameter, not the ratio of non-empty buckets |
| Actual load always equals the configured load factor | n/c changes with additions, removals, and resizes |
| `new HashSet(1000)` holds 1000 keys before any resize | Table rounding, threshold, and collision-handling paths also apply |
| Load factor must be less than or equal to 1 | Positive values greater than 1 can be valid |
| Lowering load factor always makes every operation faster | It can increase memory usage and sparse-table iteration cost |
| Knowing size alone tells you the iteration cost | Capacity must also be considered |
| The for-each body runs n times, so the iterator only does n steps | It also has to locate entries across buckets |
| Removing almost everything immediately shrinks the table | The OpenJDK build discussed does not shrink on each `remove` |
| `clear` guarantees capacity becomes 0 | Emptying contents does not mean discarding the bucket array |
| Rebuilding costs nothing because the new set is small | You still have to read the source and allocate a new structure |
| An independent set copy always has independent element objects | The structure is separate, while element references may be shared |
| The c+n formula gives exact speedup ratios | It describes order of work, not a replacement for timing measurements |

## 10. Self-check exercises

### Exercise 1: actual load

Size = 20, capacity = 64, configured load factor = 0.75. Is the load ratio n/c equal to 0.75?

**Explanation:** No; 20/64 = 0.3125. The configured value is a threshold parameter, not automatically equal to the current ratio.

### Exercise 2: typical threshold

Capacity = 32, load factor = 0.75. What is the threshold in the typical model? How do size 24 and 25 differ?

**Explanation:** Threshold = 24. Size 24 has not exceeded the threshold; adding a new key to reach 25 exceeds the threshold and can trigger a resize on the path being discussed.

### Exercise 3: same size, different capacity

Two sets both have 10 members, one with a 32-bucket table and one with a 65,536-bucket table. Why can't n = 10 alone explain all iteration work?

**Explanation:** The iterator also has to locate entries across the table. When c is much larger than n, the c term can dominate. Do not infer an exact runtime ratio from those two numbers alone.

### Exercise 4: input with heavy duplication

There are 100,000 rows but only 100 distinct codes. When sizing capacity for a set of codes, should you plan for 100,000 or 100 members if the data distribution is known?

**Explanation:** The expected number of distinct members is 100. The row count affects input reading/processing work, but it does not require the set to hold 100,000 distinct keys.

### Exercise 5: shrinking after removals

A set was once very large, now has few keys left, and will be read many times over a long period. Creating a new set from the current keys can help, but what must be accounted for?

**Explanation:** Account for the cost of iterating the old table, allocating the new set, memory while both structures coexist, external references to the old set, and whether the data will soon grow again.

### Exercise 6: model output

The model scans 1024 buckets and returns 3 elements. Can we conclude that a real `HashSet` executes exactly 1027 machine instructions for that iteration?

**Explanation:** No. The counters represent two abstract kinds of work; the JVM and implementation have many other steps and optimizations. It helps visualize the capacity factor, not count machine instructions.

Capacity and load factor determine how `HashSet` allocates space and grows its table; member count determines the amount of logical data. When analyzing iterations, keep both c and n in mind, and weigh them against your application's lifecycle and access patterns.
