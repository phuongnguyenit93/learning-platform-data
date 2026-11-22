# Initial Size Estimation and Capacity-Dependent Iteration Cost

## 1. The Problem: How Much Space Should a HashMap Reserve?

A program reads data and builds a `HashMap` for lookup by key. If 1,000 distinct keys are expected, one might write `new HashMap<>(1000)`. This statement is valid, but the meaning of `1000` is easily misunderstood: it is an initial capacity parameter, not a guarantee that the map can hold 1,000 mappings without resizing the table.

Choosing a value that is too small can cause the map to resize the table multiple times during the loading phase. Choosing a value that is too large reserves a lot of space for empty buckets, increasing memory usage and potentially making full-map iteration expensive.

The goal is **to choose a capacity suited to the expected number of mappings and how the map is used**—not to pick the largest possible number.

This article uses Java 17 as the baseline for the main programs. Power-of-two rounding and resizing paths are explained based on the OpenJDK 17u implementation; do not treat them as a public API for inspecting internal structure.

## 2. Distinguishing size, capacity, load factor, and threshold

| Name | Meaning | Example in the standard model |
| --- | --- | --- |
| size | Number of key-value mappings currently stored | 1,000 distinct keys produce a size of 1,000 |
| capacity | Number of buckets allocated in the hash table | 2,048 buckets can hold 1,000 mappings |
| initialCapacity | Capacity parameter requested when creating the map | Passing 1,334 to the constructor |
| load factor | Factor used to decide when to resize the table | Default 0.75 |
| threshold | Size threshold associated with the current table in the normal processing path | 2,048 × 0.75 = 1,536 |

A single bucket can hold multiple mappings, so capacity is not the maximum number of mappings. A map is also not an array with one slot per key.

### 2.1. Size is observable through the API

Call `size()` to find out how many mappings currently exist. Overwriting a new value for an existing key generally does not increase `size`; adding a distinct key increases the number of mappings.

The number of `put` calls can be much larger than the final `size`.

### 2.2. Capacity has no public getter on HashMap

There is no `HashMap.capacity()` method for application code to query the number of buckets. The programs below do not use reflection or open private fields.

We can use the model for capacity planning, then verify data correctness via `size`/`get`/`entrySet`. The model is not a direct measurement of an object's internal table.

### 2.3. The constructor does not mean data has been loaded

A new `HashMap` is still empty even when passed a large `initialCapacity`. In OpenJDK 17u, the table is initialized when needed; the constructor with parameters mainly records the configuration for later allocation.

This explains why measuring only constructor execution time does not measure the cost of allocating the table for data. The first insertion may have to pay that allocation cost.

The `initialCapacity` parameter also does not set a hard limit. If you keep adding entries, the map can resize the table; it does not reject the N-th key just because the constructor received `N`.

## 3. Estimating N from Coexisting Keys

Before applying the formula, define what `N` is: **the reasonable maximum number of mappings that the map will hold at the same time during the phase under consideration**.

| Scenario | Quantity to estimate |
| --- | --- |
| Indexing users by userId | Number of distinct userIds retained |
| Counting word frequencies | Number of distinct words, not total words read |
| Overwriting state by deviceId | Number of deviceIds present in the map at the same time |
| Merging two maps | Number of keys in the union of the two key sets |
| Retaining data in a time window | Number of keys coexisting at the peak of the window |

For example, if you read one million records but only update the state of 500 devices, `N` relates to those 500 devices. Sizing based on one million write operations can waste a great deal of space.

Conversely, knowing the current `size` is 1,000 is not enough if the program will load another 9,000 new keys. You need to estimate the upcoming growth phase.

For two maps with sizes `a` and `b`, `a + b` is only an upper bound when merging, because duplicate keys will update existing mappings. If you know the degree of overlap, you can make a tighter estimate.

It is not always necessary to scan the data twice just to know `N` exactly. The cost of pre-reading or creating an extra `Set` to count keys must also be factored in. When a reliable scale is unknown, using the default configuration and letting the map grow can be a reasonable choice.

## 4. From Expected Mappings to Capacity Request

### 4.1. Starting from the load threshold

In the standard capacity model, let:

- `N`: expected number of mappings.
- `C`: number of buckets.
- `f`: load factor.
- `T`: load-based resize threshold.

We use a controlled approximation:

T = floor(C × f)

To keep `N` from exceeding `T`, choose `C` such that:

C ≥ ceil(N / f)

With `f = 0.75` and `N = 1,000`:

N / f = 1,333.333...

The calculated capacity request is 1,334, and the implementation can then round it further according to its table rules.

This is a way to **avoid resizing due to exceeding the load threshold within the expected range**, not a guarantee that no internal path can trigger a resize. For example, in OpenJDK, handling an overly crowded collision bin while the table is still small can trigger a resize via a separate path.

### 4.2. Why does `new HashMap<>(1000)` differ from estimating 1,000 mappings?

In the OpenJDK 17u model with the default load factor:

1. A capacity request of 1,000 is rounded up to a 1,024-bucket table upon allocation.
2. The normal load threshold is 1,024 × 0.75 = 768.
3. When a `put` path adds another key that brings `size` to 769, it exceeds that threshold.
4. The table may resize to 2,048 buckets before all 1,000 keys are loaded.

If you use a request of 1,334 instead, the initial table under the model is 2,048 buckets, with a threshold of 1,536. Therefore, 1,000 mappings stay within the expected load range.

Both approaches may arrive at the same final capacity. The difference that matters is whether the map goes through a mid-load resize and data transfer.

### 4.3. Understanding equality at the threshold

In the `putVal` path of the referenced OpenJDK 17u source, a new key is inserted and then `size > threshold` is checked. With a table of 16 and a threshold of 12:

- A `size` of 12 does not exceed the load threshold.
- Adding another key that makes `size` equal to 13 exceeds it.
- Replacing the value of an existing key does not turn 12 keys into 13 keys.

Therefore, do not blindly add 1 in every formula just out of fear of hitting the threshold exactly. For `N = 12`, `ceil(12 / 0.75)` is 16. Adding an extra bucket to get 17 and then rounding to a power of two can push the table to 32.

However, specific builder APIs or internal processing paths may choose their own headroom strategy. When using public APIs, prioritize the exact meaning of the parameter rather than trying to force a hidden exact capacity.

## 5. Powers of Two Make Estimates Stepwise

In the OpenJDK 17u implementation, the allocated table has a length that is a power of two. As a result, the reserved space does not grow smoothly with each mapping.

The table below shows **calculations under the default-load model**, not the result of calling a `HashMap` getter:

| Expected N | ceil(N / 0.75) | Rounded C under the model | floor(C × 0.75) |
| --- | --- | --- | --- |
| 1 | 2 | 2 | 1 |
| 12 | 16 | 16 | 12 |
| 13 | 18 | 32 | 24 |
| 768 | 1,024 | 1,024 | 768 |
| 769 | 1,026 | 2,048 | 1,536 |
| 1,000 | 1,334 | 2,048 | 1,536 |
| 10,000 | 13,334 | 16,384 | 12,288 |

Increasing the estimate from 768 to 769 keys can push the table choice from 1,024 to 2,048. The extra headroom afterward is not necessarily a mistake; it comes from the rounding step.

This also explains why two different `initialCapacity` values sometimes lead to the same table choice. Tuning the parameter by single units without considering capacity steps may change nothing.

Values near the implementation's maximum limit have special handling. Do not extrapolate the normal calculation table to every `int` value and conclude that it is the exact behavior of `HashMap`.

## 6. Practical Case: 20,000 Events but Only 180 Retained Keys

Suppose an aggregator processes 20,000 events during a work shift. Each event updates a counter by device ID; old devices are removed from the `Map` when they are no longer active. A total of 240 distinct devices appeared over the entire shift, but observation shows that **at most 180 devices coexist** in the `Map` at any time.

To estimate capacity, use the peak number of **concurrent keys** `N = 180`, not the 20,000 calls or the 240 IDs that ever appeared. With the default load factor of 0.75:

~~~text
ceil(180 / 0.75) = 240
tableSizeFor(240) = 256       (OpenJDK 17 rounding model)
floor(256 × 0.75) = 192      (normal load threshold)
~~~

Since `180 ≤ 192`, choosing an initial capacity request of around 240 gives the target 256-bucket table enough headroom under the load threshold for this scenario. The calculation does not prove the `Map` will never resize: the specific dataset, collisions, or implementation paths must still be considered separately. The constructor `new HashMap<>(240)` takes a **capacity request**, and does not insert 240 pairs by itself.

| Input choice | What happens in the OpenJDK 17 model |
| --- | --- |
| Use 20,000 events as mapping count | Overestimates because many events update the same key |
| Use 240 keys that ever appeared | May overestimate if they never coexist at the same time |
| Use peak 180 coexisting keys | Reflects the actual load that needs to be provisioned |
| Use default and do not pre-size | Correct mappings; may trigger resizes while loading many keys |

The runnable example in Section 10 explores the other side of the trade-off: when a `Map` becomes very sparse, iteration cost can be affected by a large allocated table. A full program that computes capacity from load factor and observes resizes is presented in the article on capacity and load factor.

## 7. What Does Resizing Cost, Even If `put` Is Usually Fast?

When resizing the table, the implementation must allocate a new table and reorganize the placement of nodes into buckets. This work involves the table and existing mappings, so a `put` that triggers a resize can cost much more than a regular `put`.

In OpenJDK 17u's resize path, nodes retain their computed hash information. You should not explain resizing as "always re-invoking `hashCode` on every key from scratch"; reorganizing buckets and calling user methods again are two different things.

### 7.1. Amortized cost across many insertions

The table grows exponentially in the normal range. Looking at a sequence of many insertions, the total growth work can be amortized across many operations. This is why dynamic resizing remains useful.

However, average amortized cost does not mean every single `put` call has the same latency. A program sensitive to latency spikes may care about when table allocation and transfer occur.

Estimating well from the start helps reduce unnecessary resizes. It also front-loads the larger table allocation to the initial phase, so there is still a trade-off.

### 7.2. Memory is not just empty buckets

A map also consists of the map object, the reference table, nodes, keys, values, and any auxiliary structures that may arise. Do not multiply `capacity` by an arbitrary guessed byte count and call that the total memory of the map.

During a resize or when creating a copy to compact, two structures may coexist for a period of time. Estimating peak memory is also valuable, especially for large datasets.

Object sizes depend on the JVM and its configuration. If you need byte counts, measure in the relevant environment instead of turning a number learned on another machine into a universal constant.

## 8. Why Does Iterating a HashMap Depend on `capacity + size`?

### 8.1. Looking up one key differs from iterating all entries

`get` uses the hash to jump to the region that may contain the key. With an appropriate distribution, basic operations have good expected performance.

Iterating over the entire `entrySet`, `keySet`, or `values` must find the buckets that contain data and walk through the mappings inside them. Empty buckets may also have to be checked during the table scan.

The [Java 17 HashMap documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html) states that iteration time over collection views is proportional to capacity plus size.

Learning model:

Full-map iteration cost ≈ cost to scan C buckets + cost to visit N mappings

Written in complexity notation: O(C + N).

Do not read this formula as "takes exactly C + N nanoseconds" or "each bucket costs exactly as much as each entry." This is a model of work count, not units of time.

### 8.2. Same 1,000 mappings, different tables

Suppose there are two table states:

| State | C | N | C + N in the model |
| --- | --- | --- | --- |
| Sized to fit expected load | 2,048 | 1,000 | 3,048 |
| Very over-provisioned | 1,048,576 | 1,000 | 1,049,576 |

Both have the same number of entries to process, but the second state has a huge number of empty buckets. If reports are repeatedly exported by iterating over the entire map, that empty space can become a recurring cost.

Do not infer the ratio of real execution times from the ratio of the two sums above. CPU caches, object layout, work inside the loop body, and the JVM all affect measurements.

### 8.3. When is it commonly shortened to O(N)?

If `C` is always on the same order as `N` during the phase under consideration, then `C + N` is also on the same order as `N`. In that case, writing `O(N)` can be a valid shorthand under that assumption.

However, `C` does not automatically stay close to `N`. It can be very large due to initial configuration or because the map once grew significantly and then had much of its data removed. Dropping `C` in those situations hides the very factor that needs explaining.

### 8.4. Scope of a full traversal

The formula describes a full traversal, with the work at each mapping accounted for separately. If the loop body performs network I/O, processes long strings, or runs expensive computations, that cost may outweigh the cost of traversing the structure.

If you only take a few elements and stop, the amount of scanning depends on where the populated buckets lie. Do not treat `O(C + N)` as the exact step count for every iterator prefix.

A completely empty map also has a fast path in the referenced implementation. Do not claim that every empty iterator must scan the entire old table just because the general formula contains `C`.

Parallel iteration does not automatically eliminate empty-bucket cost either. Splitting and processing data is a separate problem that must be measured against actual workloads.

## 9. Does Removing Data Automatically Shrink the Table?

### 9.1. Decreasing size does not mean decreasing capacity

In the referenced OpenJDK 17u implementation, `remove` does not automatically shrink the hash table just because the total number of mappings decreases. `clear` removes the mappings but keeps the table object so it can be reused.

A map that once held a large number of keys can become sparse after deletions. When only a few mappings remain and you continue to iterate over the entire map, looking at the small `size` and assuming iteration must be cheap is missing key context.

Changing the internal representation of a single bucket and shrinking the entire table are two different things. Do not use a change in a collision bin as evidence that the table now has fewer buckets.

### 9.2. Retaining vs. rebuilding depends on the lifecycle

If a similarly large amount of data will be loaded right after `clear`, keeping the old table can avoid reallocation.

If the data volume has permanently dropped and the map continues to be iterated frequently, creating a new `HashMap` from the remaining mappings can help bring capacity back in line with the new scale.

`HashMap` does not have a public `trimToSize` method like some other structures. One way to create a new structure is:

```java
Map<K, V> rebuilt = new HashMap<>(oldMap);
```

This is an illustrative snippet in a context where types `K`, `V` and variable `oldMap` already exist, not a standalone program.

The copy constructor preserves the mappings according to the public contract. Do not require it to pick the exact minimum capacity from the calculation table above; headroom rules can differ across construction paths and versions.

### 9.3. Copying has a cost and changes object identity

To build the new instance, the mappings must still be read from the old one. If the old instance is very sparse, the traversal needed for copying can itself be expensive due to the old table.

During copying, both the old and new structures coexist. Keys and values are re-referenced objects; they do not automatically become deep copies.

Reassigning a variable to the new instance does not switch every other consumer to that same object. Places still holding the old map, its `keySet`/`values`/`entrySet`, or an old iterator remain tied to the old instance. You need to clearly identify who owns the map before replacing the structure.

The old table only has a chance to be garbage-collected when no reference paths remain holding that structure; there is no guarantee of immediate collection at the assignment statement.

## 10. Java 17 Example: Sparse Map and Rebuilt Copy

The program intentionally requests a large initial capacity, loads 1,000 keys, and then removes 990 keys. Afterward, it creates a new map from the 10 remaining mappings.

The purpose of stdout is to verify **the mappings and the relationship between the two objects**, not to measure timing or read hidden capacity.

Save as **SparseHashMapDemo.java**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class SparseHashMapDemo {
    static long checksum(Map<Integer, Integer> map) {
        long sum = 0;
        for (Map.Entry<Integer, Integer> entry : map.entrySet()) {
            sum += entry.getValue();
        }
        return sum;
    }

    public static void main(String[] args) {
        Map<Integer, Integer> original = new HashMap<>(1 << 18);
        for (int key = 0; key < 1000; key++) {
            original.put(key, key);
        }
        System.out.println("before removal size: " + original.size());

        for (int key = 0; key < 990; key++) {
            original.remove(key);
        }
        System.out.println("after removal size: " + original.size());
        System.out.println("remaining checksum: " + checksum(original));

        Set<Integer> oldKeysView = original.keySet();
        Map<Integer, Integer> rebuilt = new HashMap<>(original);
        System.out.println("same mappings after copy: " + original.equals(rebuilt));
        System.out.println("rebuilt size: " + rebuilt.size());

        original.clear();
        System.out.println("old view size after clear: " + oldKeysView.size());
        System.out.println("rebuilt size after original clear: " + rebuilt.size());
        System.out.println("rebuilt checksum: " + checksum(rebuilt));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SparseHashMapDemo.java
java SparseHashMapDemo
```

Stdout on the stated environment:

```text
before removal size: 1000
after removal size: 10
remaining checksum: 9945
same mappings after copy: true
rebuilt size: 10
old view size after clear: 0
rebuilt size after original clear: 10
rebuilt checksum: 9945
```

### 10.1. Reading the output

The remaining keys are 990 through 999, whose values sum to 9,945. The copy retains the same mappings, so `equals` returns `true` and the checksum remains accurate.

The variable `oldKeysView` is a view of the original map. When the original map is cleared, that view has a `size` of 0. The new map still retains the 10 mappings because its underlying mapping storage is independent of the original map.

Clearing the old map in the example helps demonstrate that relationship; it is not a requirement to call `clear` before every map replacement. If another part of the code still needs the old data, `clear` will have a real effect on it.

### 10.2. What stdout does not prove

It does not prove the exact bucket counts of the two maps or any percentage speedup.

Why a map can become sparse after deletions and why the copy constructor can choose a better-sized new table are explained by the model and the implementation source code. The program output verifies the correctness of the mappings.

An example that prints two nanosecond timings and claims the new copy is always faster would not be reliable. Correctness and performance measurement require separate testing goals.

## 11. Choosing Capacity Based on the Map's Workload

| Primary usage | What to consider |
| --- | --- |
| Loaded once, key count fairly well known | Estimate capacity to reduce table resizes during loading |
| Small scale or unpredictable | Default configuration is usually a reasonable starting point |
| Iterated in full many times | Avoid excessive over-provisioning; consider both capacity and size |
| Frequently cleared and reloaded at similar scale | Reusing the table can be beneficial |
| Grows very large once, then shrinks permanently | Consider building a new structure if the benefit outweighs copy cost |
| Needs stable iteration order | Choose a structure with an appropriate ordering contract, do not rely on capacity |

### 11.1. Do not lower the load factor mechanically

Lowering `f` increases `N / f`. For the same `N`, the implementation may have to choose a larger table. That can reduce average crowding, but it increases table memory and scanning work during iteration.

Raising `f` is not free savings either: more mappings per bucket can make lookups more expensive. The hash function and data characteristics still matter.

Keeping the default 0.75 usually gives a solid built-in trade-off to start with. Only change it when there is a requirement and evidence tied to the workload.

### 11.2. A useful comparison with LinkedHashMap

According to [Java 17 LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html), iterating over collection views follows the entry links and has cost proportional to `size`, independent of `capacity` in the way `HashMap` scans its table.

That is a worthwhile distinction when you need iteration order or frequently iterate a sparse map. However, `LinkedHashMap` carries extra links and the cost of maintaining them; do not assume it always uses less memory or is faster for every operation.

Choosing a data structure must consider both the required contract and the work performed, not just a single complexity line.

## 12. Java 19+: Expressing the Expected Mapping Count Directly

Starting in Java 19, `HashMap` has the factory `newHashMap(int numMappings)`. Here the parameter is **the expected number of mappings**, which differs from the constructor's `initialCapacity`.

Illustrative declaration in a context where `Map` and `HashMap` are already imported:

```java
Map<String, Integer> counts = HashMap.newHashMap(1000);
```

The API uses the default load factor and chooses an initial capacity generally suited to hold the expected number of mappings. There is no need to manually pass the result of `N / 0.75` into the factory again.

Reference the `newHashMap`, `Since 19` entry in [Java 19 HashMap](https://docs.oracle.com/en/java/javase/19/docs/api/java.base/java/util/HashMap.html#newHashMap(int)).

This snippet **does not compile with `--release 17`**, even on a machine running a newer JDK. The two complete programs above use only APIs available in Java 17.

The factory still returns an empty map that can grow. The number 1,000 does not create a hard limit or automatically shrink the map after deletions.

## 13. Evaluating Performance Without Confusing the Goal

First verify that the configurations hold the same mappings, perform the same work inside the loop body, and produce the same results. Otherwise, timing differences may simply come from processing different amounts of data.

When benchmarking capacity, separate these questions:

- How much does initial data loading cost?
- How much does a single iteration after loading cost?
- How does deleting many entries and continuing to iterate affect cost?
- How much does copying to a new map cost, and how many times will it be reused?

Do not include map construction inside each measured iteration if the question is the cost of iterating an already-built map. Conversely, if you want to evaluate the entire loading phase, do not exclude allocation cost from the measurement and call it the total cost.

You need a JVM warmup phase, multiple measurement iterations, consumed results so work is not optimized away, and representative data. Record the JDK, configuration, and key distribution.

If the loop body prints each line to the console, printing can mask almost all structural differences. The programs in this article use stdout to demonstrate results, not as a `HashMap` benchmark.

There is no need to inflate capacity to extreme sizes on your machine just to prove `O(C + N)`. The model explains the relationship; controlled benchmarks evaluate the actual impact on the application.

## 14. Common Mistakes and Fixes

| Misconception | Consequence | Fix |
| --- | --- | --- |
| `initialCapacity` is the number of mappings without resizing | Loading exceeds the load threshold earlier than expected | Account for key count and load factor |
| Capacity is a limit on key count | Mistakenly designing rejection or eviction logic around it | Implement a separate bounding policy if needed |
| One million records means one million entries | Over-provisioning if many records share the same keys | Estimate the number of distinct coexisting keys |
| Always add 1 after `N/f` | May jump to a larger table step unnecessarily | Round up appropriately and understand the threshold condition |
| Multiply `int`s before converting to `long` | Value overflows before the type conversion | Use `long` operands before multiplication |
| Map has small `size` so iteration must be cheap | Overlooks a large table retained after deletions | Consider lifecycle and capacity |
| `clear` immediately frees the table | Misjudges memory usage and reuse potential | Distinguish clearing mappings, retaining the table, and GC |
| Printing the modeled capacity means measuring the object | Overclaiming from a calculation | Clearly distinguish the model from public observations |
| Creating a copy is free | Ignores the old traversal and peak memory | Factor in copy cost and subsequent reuse count |
| `newHashMap(1000)` needs manual division by 0.75 | Over-provisioning from adjusting twice | The factory takes the expected number of mappings |
| One quick loop proves every case | Relies on noisy measurements or wrong scope | Benchmark with clear goals, environment, and data |

## 15. Self-Check Exercises with Solutions

### Exercise 1: Loading right at the threshold

Under the OpenJDK 17u model with the default load factor, a 16-bucket table has a normal threshold of 12. Does loading 12 distinct keys exceed the load threshold? What about adding a 13th distinct key?

**Solution:** 12 is not greater than 12. The 13th new key causes `size` to exceed the threshold in the `put` path under consideration. This conclusion applies only to the load-based resize path; it does not rule out other internal mechanisms in special collision datasets.

### Exercise 2: Calculating for 2,000 mappings

Using `f = 0.75`, what is the calculated capacity request? Under the power-of-two model, which table is sufficient?

**Solution:** `ceil(2,000 / 0.75) = 2,667`. Rounded up to 4,096, the normal threshold is 3,072.

### Exercise 3: Four writes, two keys

The input key sequence is `a`, `a`, `b`, `a`. If only the latest value per key is kept, is the final `N` equal to 4 or 2?

**Solution:** 2 distinct keys. The number of input records does not equal the final number of mappings. If the problem is frequency counting, the map still has two mappings, with count values 3 and 1.

### Exercise 4: Two maps with the same size

Map A has `C = 4,096`, `N = 2,000`; map B has `C = 1,048,576`, `N = 2,000`. Can we say one full iteration over each must be equal because both have 2,000 entries?

**Solution:** No. `HashMap` iteration also involves the bucket table. However, this model alone cannot compute the exact runtime ratio either.

### Exercise 5: After deleting a large amount

A map shrinks from hundreds of thousands of keys down to a few hundred and is then used to export reports many times. Can you rely solely on `size` to conclude that iteration cost has dropped proportionally?

**Solution:** No. The referenced implementation does not automatically shrink the table on `remove`. You can consider creating a new map suited to the remaining scale, after accounting for copy cost, peak memory, and references to the old map.

### Exercise 6: Clearing before reloading

A recurring task regularly calls `clear` and then reloads roughly the same number of keys as before. Is replacing the map after `clear` always better?

**Solution:** No. Keeping the table can reduce reallocations. Choose based on the data lifecycle and appropriate measurements.

### Exercise 7: Using a helper with the wrong load factor

You calculated capacity using `f = 0.75` but passed it to a constructor with `f = 0.5`. Can you keep the same conclusion about the threshold?

**Solution:** No. The threshold depends on `f`. If `f` changes, you must recalculate or use a map construction approach that matches the actual configuration.

### Exercise 8: Factory and Java version

A snippet calling `HashMap.newHashMap(1000)` runs on a machine with JDK 24. Is it guaranteed to compile with `--release 17`?

**Solution:** No. That API was introduced in Java 19. The JDK used to run the tool and the target API level when compiling are two separate pieces of information.

## 16. References

- [Java 17 HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): meaning of capacity, load factor, constructors, and iteration cost.
- [OpenJDK 17u HashMap.java](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java): rounding, table initialization, resizing, iterators, and `clear` in the analyzed implementation.
- [Java 19 HashMap — newHashMap](https://docs.oracle.com/en/java/javase/19/docs/api/java.base/java/util/HashMap.html#newHashMap(int)): API taking the expected number of mappings.
- [Java 17 LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): comparison of iteration cost by `size`.

Capacity estimation starts from the number of coexisting keys, then considers the load factor and how the map is used. Reducing unnecessary resizes is helpful, but over-provisioning too much can shift the cost to memory and later iterations.
