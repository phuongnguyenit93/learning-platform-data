# LinkedHashMap: Iteration Cost, Storage, and Choosing Between LinkedHashMap and HashMap

A map can serve two different tasks: looking up a value by key and sequentially processing all entries. When choosing between `HashMap` and `LinkedHashMap`, you need to consider both tasks, along with ordering requirements and memory limits.

For example, a product counter used only to answer "how many times does this code appear?" may not need ordering. A report that must output codes in the order they first appeared has a different requirement: order is part of the result. `LinkedHashMap` in its default mode expresses that requirement directly.

After this lesson, you should be able to explain why iterating over a `LinkedHashMap` depends on the number of entries, what additional storage is incurred, and when those characteristics justify choosing it over `HashMap`. You should not turn a single Big O line into a promise about speed on all data.

This lesson uses the Java 17 API. Details from the OpenJDK 17 source code are marked as implementation-specific, not general requirements for every JVM.

## 1. The Mental Model: Hash Table and Order Chain

### 1.1. The Hash Table Serves Lookups

`HashMap` uses a hash table structure to find an entry from a key. `LinkedHashMap` still has that foundation; it does not replace lookups by walking sequentially from the first element to the last.

Therefore, `hashCode` quality, consistency with `equals`, and key immutability still matter. Switching to `LinkedHashMap` does not fix a key with broken equality rules, nor does it give every hash distribution the same lookup time.

### 1.2. The Linked Chain Serves Iteration Order

`LinkedHashMap` additionally maintains a doubly-linked chain running through the entries. You can view the same map from two directions:

~~~text
Key lookup path:
key -> hash value -> table slot -> matching entry

LinkedHashMap iteration path by order:
head -> entry A <-> entry B <-> entry C -> tail
~~~

This is a conceptual diagram. The entries accessed via the table and via the chain are not two separate, full copies of all keys and values. The extra information is what holds and maintains the ordering relationship.

The default mode preserves insertion order. Reassigning the value of an existing key does not move that key to the end. Removing a key and adding it back is a new insertion, so its position becomes the end of the chain.

If created with the constructor taking `accessOrder=true`, the chain maintains access order according to the operations specified by the API. A successful `get` can change position. Operations on collection views do not themselves generate this kind of access. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

### 1.3. Ordered Does Not Mean Sorted

Inserting `30, 10, 20` into a default `LinkedHashMap` gives the iteration order `30, 10, 20`. It does not automatically sort them into `10, 20, 30`.

Before choosing a structure, name the requirement accurately:

| Requirement | Meaning |
|---|---|
| By first appearance | Insertion order can satisfy this |
| By most recent access | Access-order mode may be needed |
| By ascending key | Requires key order, such as TreeMap or a separate sorting step |
| No ordering requirement | Can start with HashMap |

Naming the requirement first helps avoid paying the cost to maintain an order the application does not use, or picking an ordered structure with the wrong kind of order.

## 2. Two Quantities That Determine How to Read Complexity

Let:

- `N` be the current number of entries, i.e., `map.size()`.
- `C` be the number of slots in the hash table in the implementation under consideration.
- `M` be the number of times the application iterates over the entire map during the analysis window.

`N` and `C` are not the same number. A map with few entries can still be backed by a large table, for example due to a large initial capacity request. Current data size alone is not enough to describe every cost of the table structure.

The public API of `HashMap` has no method that returns the internal array capacity. The constructor parameter is an initialization request; you should not use the passed number alone to claim you observed the exact number of allocated slots. Rounding rules and allocation timing belong to the implementation.

The Java 17 documentation states that the cost of iterating over the collection views of `HashMap` is proportional to capacity plus size. For `LinkedHashMap`, this cost is proportional to size, regardless of capacity. This is the basis for the two models:

~~~text
Full HashMap iteration:        O(C + N)
Full LinkedHashMap iteration:  O(N)
~~~

[Java 17: HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

These are growth models, not time formulas in nanoseconds. They do not say that each empty table slot and each entry cost exactly one unit of work.

## 3. Why Does LinkedHashMap Have O(N) Iteration Cost?

### 3.1. HashMap Is Affected by Empty Table Slots

To find all entries, the `HashMap` iterator must traverse the table's data organization structure. Slots without data affect finding the next slot that holds an entry. Therefore, the model contains both `C` and `N`.

When the table is kept proportional to the data, you can treat `C = Θ(N)`. In that case, `O(C + N)` is also `O(N)` in terms of N. Thus, there is no contradiction between the statement "HashMap iterates linearly when capacity is proportional" and the full formula `O(C + N)`.

If the table is very sparse, dropping `C` from the analysis can miss a significant factor. Two maps with the same `size()` do not necessarily experience the same impact from scanning through the table.

### 3.2. LinkedHashMap Follows the Entry Chain

The `LinkedHashMap` iterator can walk from the first entry to the last entry via links. It does not need to find the next entry by scanning empty table slots. The number of entries along the path is N.

This explains why excessive capacity penalizes the iteration path itself less than in `HashMap`. However, the iterator still reads objects and follows references. Object layout, CPU cache, JIT, and the work inside the loop body still affect actual time.

`O(N)` does not mean every map with N entries always takes the exact same iteration time on every machine or at every moment.

### 3.3. Big O Does Not Give a Speedup Ratio

Suppose a model has `N = 100` and `C = 1,000,000`. `C + N` shows that table scanning can be much larger than the amount of data to process. `LinkedHashMap`'s chain eliminates that empty-slot scanning component from the iteration path.

However, you cannot say it is exactly `(1,000,000 + 100) / 100 = 10,001` times faster. The two kinds of steps do not necessarily have the same cost; the algorithm and execution environment have many other differences.

If there are M iterations, the modeled part is `M × (C + N)` or `M × N`. The formula helps identify iteration-sensitive workloads, but it does not fully account for map construction, updates, allocation, garbage collection, and per-element processing.

| Context | What Can Be Concluded |
|---|---|
| C is on the same order as N | Both iteration paths are linear in N |
| C is much larger than N | LinkedHashMap has a structural advantage by not scanning empty table slots |
| Loop body processing is very heavy | The structural iteration difference may be only a small fraction of total time |
| Concrete speed numbers are needed | Must measure on a representative workload and environment |

A loop summing integers and a loop calling a network service for each entry do not have the same weight of data-structure cost. The map choice must be placed in the context of the whole task.

## 4. Maintaining Order Also Has Work to Do

Basic operations such as `get`, `put`, and `remove` on `LinkedHashMap` are still based on the hash table. The documentation notes constant-time performance when hash values are well distributed, while describing that maintaining links usually makes these operations do more work than `HashMap`. The notable exception is the advantage on the iteration path. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

Distinguish between:

- Expected constant time under good hash distribution versus a guarantee for all data.
- Amortized average cost across many insertions versus a single insertion that triggers table resizing.
- Same Big O order versus same actual runtime.

Adding a few steps to link or unlink nodes may not change the complexity class, but it still adds work.

| Task | HashMap | LinkedHashMap |
|---|---|---|
| Lookup by key | Hash table | Still a hash table |
| Insert new entry | Update hash structure, possibly resize | Plus linking into the order chain |
| Remove entry | Remove from hash structure | Plus unlinking from the order chain |
| Full view iteration | O(C + N) | O(N) |
| Ordering | Not guaranteed | According to the chosen mode |
| Order-keeping state | No order chain like LinkedHashMap | Has link information and additional state |

In access-order mode, a successful `get` can move the entry to the end. If the entry is already at the end, no move is needed; if not, the linked structure may have to change.

This alone is not enough to design a bounded cache. The topic here is cost and selection: choose `accessOrder=true` only when you need those exact semantics, and remember that "reading by key" can trigger order-maintenance work.

## 5. Storage Cost: Same Order Does Not Mean Same Byte Count

### 5.1. Separating Map Structure from Referenced Data

A rough storage model consists of:

~~~text
map object
+ hash table reference array
+ entry representation objects
+ referenced key and value objects
~~~

If we temporarily separate key and value sizes, the structural part of both maps can be modeled as `O(C + N)`. `LinkedHashMap` adds chain-keeping information, so it can cost more in storage factor despite having the same growth order.

With millions of small entries, the extra structural part can be significant. If each value references a very large object graph, the ratio of the structural part to total footprint may be smaller. You must state clearly whether you are counting only the structure or all retained live data.

### 5.2. What Can Be Seen in OpenJDK 17?

In the OpenJDK 17 source code, the regular node `LinkedHashMap.Entry` extends `HashMap.Node` and adds `before` and `after`. The map maintains both the head and tail of the chain. These fields concretely explain why preserving order requires extra information. [OpenJDK 17: LinkedHashMap.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/LinkedHashMap.java)

Do not turn that observation into a fixed byte count per entry across all JVMs. Object headers, reference width, compressed references, alignment, and node types can all affect it.

Even within OpenJDK 17, `HashMap` tree nodes have an inheritance relationship with `LinkedHashMap.Entry`. Therefore, the statement "every LinkedHashMap node is always larger than every HashMap node by exactly two references" is too broad. You can describe the two extra references when comparing regular nodes in this implementation, and measure the specific environment if you need byte counts. [OpenJDK 17: HashMap.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java)

### 5.3. Not Scanning C During Iteration Does Not Mean Not Storing C

`LinkedHashMap` still uses a hash table for lookups. Thus, an overly large capacity request can still increase the array footprint and affect the memory subsystem, even though the iteration path does not walk through those empty slots.

These are two independent questions:

1. Which components must be traversed to iterate over everything?
2. Which components must be kept in memory?

The answer to the first question must not be used in place of the second.

The load factor and expected entry count help with capacity planning. In the resize-threshold model, to hold about N entries with load factor f, you can consider a level around `N / f` before rounding and allocation rules. This is not an API formula guaranteeing exact array size.

Do not assume a constructor taking 100,000 is guaranteed to hold 100,000 entries without resizing. Also do not pass an enormous number just to avoid thinking about expected data.

### 5.4. Copying Can Temporarily Increase Memory

Creating a `LinkedHashMap` from an existing map creates a new map structure containing the corresponding entries. Copying entries reuses key and value references; it does not automatically deep-copy all objects.

While both maps coexist, the application holds both structures. If converting a large map just to export once, account for allocation and peak memory usage, not only the loop time at the end.

Copying a `HashMap` into a `LinkedHashMap` also does not recover insertion history that was never stored. The new map keeps the sequence it encounters when iterating over the source. If the source has no guaranteed business order, copying does not make that order appear.

## 6. Choosing Based on Requirements and Workload

### 6.1. Lookup-Heavy, No Ordering Requirement

A counter that is only queried by individual code and almost never iterated in full can start with `HashMap`. The application does not need to maintain insertion order throughout the table's lifetime.

If you only need to output in ascending code order once at the end, you can sort the result at the export step. It is not necessary to maintain an insertion order only to discard it when sorting.

This is a reasonable starting point based on requirements, not a promise that `HashMap` is always fastest.

### 6.2. First-Appearance Order Required

If each code should appear only once and in the order first seen, default `LinkedHashMap` is a good fit. The following is a partial illustrative snippet, assuming `codes` is an existing list of codes:

~~~java
Map<String, Integer> counts = new LinkedHashMap<>();
for (String code : codes) {
    counts.merge(code, 1, Integer::sum);
}
for (Map.Entry<String, Integer> entry : counts.entrySet()) {
    System.out.println(entry.getKey() + ": " + entry.getValue());
}
~~~

Updating the count of an existing key does not change insertion order. With input `B, A, B, C, A`, the keys are output as `B, A, C`.

If input data comes from a source with no guaranteed order, you must define the input rule first. An order-preserving structure can only preserve the sequence the program actually feeds it.

### 6.3. Many Iterations Over a Sparse Table

This is a situation worth considering `LinkedHashMap` because the iteration path does not scan empty table slots. However, you should also examine why the table is sparse: an overly large initial configuration may be the problem to fix.

Weigh together the number of entries, sparsity, iteration count, update ratio, work in the loop body, and memory limits. If requirements allow, fixing how the map is created may address the root waste better than merely switching classes.

### 6.4. Key Order or Concurrent Access Needed

Ascending key order is a different problem from insertion order. `TreeMap` fits many needs for maintaining key order; sorting a result list can fit when only a final export is needed. Distinguish between maintaining order throughout a lifetime and producing an ordered result at a single point in time.

Neither `HashMap` nor `LinkedHashMap` provides synchronization on its own. Choosing an order-preserving class does not solve concurrent access.

In particular, in access-order mode, `get` can structurally modify the order. A "read-only threads" argument must be revisited if those reads are such accesses. Synchronization rules must cover actual usage, including iteration. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

If a concurrency contract is needed, choose a design that satisfies that requirement first and then re-evaluate ordering. No single map class automatically solves all requirements at once.

## 7. Iterating According to the Data Needed

### 7.1. Need Both Key and Value: Prefer entrySet

The following two partial snippets compute the sum over a `scores` map with no null values:

~~~java
int total = 0;
for (String key : scores.keySet()) {
    total += scores.get(key);
}
~~~

~~~java
int total = 0;
for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    total += entry.getValue();
}
~~~

The first snippet already has the key from the iterator and then requests a lookup by key to get the value. The second snippet reads directly from the entry being iterated.

You should not call the first snippet quadratic just because of the extra `get`: under good hashing, the extra lookups still have expected constant cost per lookup. Nevertheless, they are unnecessary work when you already have the entry.

If you only need keys, choose `keySet()`. If you only need values, choose `values()`. If you need both, `entrySet()` expresses the intent clearly.

### 7.2. The keySet-Then-get Pattern Can Alter Access Order

On a `LinkedHashMap` with `accessOrder=true`, `get(key)` can move the entry to the end while the iterator is active. That loop pattern can encounter `ConcurrentModificationException`.

Do not build program correctness on expecting an exception to reliably appear. The iterator's modification detection is only best-effort, not a synchronization tool. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

Iterating `entrySet` and reading `entry.getValue()` avoids both the redundant lookup and the key-based access that can alter order. This does not allow another thread to freely modify the map at the same time; that remains a separate issue.

When you need to observe the current order, also avoid calling `get` repeatedly just to print values on an access-order map. The act of observing itself can change the order you care about.

## 8. Complete Program and Verified Output

Save the following code to `LinkedHashMapCostDemo.java`. This Java 17+ program requires no external libraries.

It tests the same data across four maps, records `hashCode` calls in two iteration styles, and then compares insertion order and access order. This is a functional example, not a timing measurement.

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class LinkedHashMapCostDemo {
    private static final class Key {
        private static int hashCalls;
        private final int id;

        private Key(int id) {
            this.id = id;
        }

        @Override
        public int hashCode() {
            hashCalls++;
            return id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Key key && id == key.id;
        }
    }

    private static void fill(Map<Key, Integer> map) {
        map.put(new Key(30), 3);
        map.put(new Key(10), 1);
        map.put(new Key(20), 2);
    }

    private static List<Integer> ids(Map<Key, Integer> map) {
        List<Integer> result = new ArrayList<>();
        for (Key key : map.keySet()) {
            result.add(key.id);
        }
        return result;
    }

    private static int entrySum(Map<Key, Integer> map) {
        int sum = 0;
        for (Map.Entry<Key, Integer> entry : map.entrySet()) {
            sum += entry.getValue();
        }
        return sum;
    }

    private static void inspect(String label, Map<Key, Integer> map) {
        fill(map);
        Key.hashCalls = 0;
        int fromEntries = entrySum(map);
        int iteratorHashCalls = Key.hashCalls;

        Key.hashCalls = 0;
        int fromKeys = 0;
        for (Key key : map.keySet()) {
            fromKeys += map.get(key);
        }
        int keyThenGetHashCalls = Key.hashCalls;

        if (map.size() != 3 || fromEntries != 6 || fromKeys != 6) {
            throw new AssertionError("Unexpected mappings");
        }
        System.out.println(label + ": size=" + map.size()
                + ", sum=" + fromEntries
                + ", iteratorHashCalls=" + iteratorHashCalls
                + ", keyThenGetHashCalls=" + keyThenGetHashCalls);
    }

    private static void requireIds(Map<Key, Integer> map, List<Integer> expected) {
        if (!ids(map).equals(expected)) {
            throw new AssertionError("Unexpected LinkedHashMap order");
        }
    }

    public static void main(String[] args) {
        inspect("HashMap(requested=16)", new HashMap<Key, Integer>(16));
        inspect("HashMap(requested=4096)", new HashMap<Key, Integer>(4096));
        inspect("LinkedHashMap(requested=16)",
                new LinkedHashMap<Key, Integer>(16));
        inspect("LinkedHashMap(requested=4096)",
                new LinkedHashMap<Key, Integer>(4096));

        LinkedHashMap<Key, Integer> insertion = new LinkedHashMap<>();
        fill(insertion);
        requireIds(insertion, List.of(30, 10, 20));
        System.out.println("insertion/start=" + ids(insertion));
        insertion.put(new Key(30), 30);
        requireIds(insertion, List.of(30, 10, 20));
        System.out.println("insertion/replace=" + ids(insertion));
        insertion.remove(new Key(10));
        insertion.put(new Key(10), 10);
        requireIds(insertion, List.of(30, 20, 10));
        System.out.println("insertion/reinsert=" + ids(insertion));

        LinkedHashMap<Key, Integer> access =
                new LinkedHashMap<>(16, 0.75f, true);
        fill(access);
        System.out.println("access/start=" + ids(access));
        access.get(new Key(10));
        requireIds(access, List.of(30, 20, 10));
        System.out.println("access/afterGet10=" + ids(access));
        Key.hashCalls = 0;
        int accessSum = entrySum(access);
        int accessIteratorHashCalls = Key.hashCalls;
        requireIds(access, List.of(30, 20, 10));
        if (accessSum != 6) {
            throw new AssertionError("Unexpected access-order sum");
        }
        System.out.println("access/entrySum=" + accessSum
                + ", iteratorHashCalls=" + accessIteratorHashCalls);
        System.out.println("access/afterEntries=" + ids(access));
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 LinkedHashMapCostDemo.java
java LinkedHashMapCostDemo
~~~

Stdout from the verification run:

~~~text
HashMap(requested=16): size=3, sum=6, iteratorHashCalls=0, keyThenGetHashCalls=3
HashMap(requested=4096): size=3, sum=6, iteratorHashCalls=0, keyThenGetHashCalls=3
LinkedHashMap(requested=16): size=3, sum=6, iteratorHashCalls=0, keyThenGetHashCalls=3
LinkedHashMap(requested=4096): size=3, sum=6, iteratorHashCalls=0, keyThenGetHashCalls=3
insertion/start=[30, 10, 20]
insertion/replace=[30, 10, 20]
insertion/reinsert=[30, 20, 10]
access/start=[30, 10, 20]
access/afterGet10=[30, 20, 10]
access/entrySum=6, iteratorHashCalls=0
access/afterEntries=[30, 20, 10]
~~~

The code compiled with `--release 17` and ran successfully. The checks in the program verify the entry count, sums, and required orders. The `--release 17` option specifies the compatible API level and bytecode target; it does not mean the executing JVM must be strictly JDK 17.

### 8.1. Why Do All Four Sums Equal Six?

`fill` adds three pairs: `30 -> 3`, `10 -> 1`, and `20 -> 2`. All four maps hold the same data. Summing checks the contents without assuming `HashMap` iteration order.

In this run, iterating `entrySet` to get values does not call `hashCode` on the keys again; the counter is zero. Iterating `keySet` and then calling `get` for each key produces three `hashCode` calls.

This is an observation about calls to the key's method on the implementation that ran. The `Map` contract does not require every implementation to have the exact same counter as the example.

More importantly, the counter does not observe how many table slots were scanned. An iterator can walk internal structures without calling `hashCode` again. Therefore, two lines printing zero do not prove the two maps have equal iteration cost.

The program does not measure actual capacity, byte count, time, or speed ratios. The `requested` label intentionally states that this is a requested parameter, not the result of reading a private array.

### 8.2. When Does Insertion Order Change?

The three `insertion` lines show:

1. After inserting three keys, the order is `[30, 10, 20]`.
2. Replacing the value for key `30` keeps that order.
3. Removing key `10` and adding it back changes the order to `[30, 20, 10]`.

The map does not add a new position for every `put` call regardless of outcome. It still has only one entry per equal key. Link maintenance must match the entries actually added, removed, or updated.

`requireIds` only checks the order of `LinkedHashMap`. There is no check imposing a similar order on `HashMap`.

### 8.3. Reading by Key Differs from Iterating Entries

The `access` map uses access-order mode. `get(10)` moves key `10` to the end. `entrySum` then reads values from the entries without calling `get` on the map; the order does not change.

`ids` iterates `keySet` and only reads the id inside the key, without calling `map.get`. Thanks to this, printing the order does not itself generate a key-based access.

The program intentionally avoids iterating while calling `get` on the access-order map. The example keeps behavior deterministic to clearly demonstrate that the two kinds of reads have different effects, rather than depending on when an exception is thrown.

### 8.4. Why Not Use a hashCode-Counting Key to Measure Speed?

Incrementing the counter itself adds work to `hashCode`. The simple key in the example helps observe a mechanism, but does not necessarily represent real application keys.

An example that verifies sums, order, and observed calls does not automatically become a generalizable performance benchmark. Use the example to understand, then use an appropriate measurement methodology when you need data-driven decisions.

## 9. When a Decision Requires Time or Memory Numbers

### 9.1. Write a Clear Question Before Measuring

"Which class is faster?" is an under-specified question. You can replace it with:

- With N entries and a specific key distribution, how does full iteration time change with how the table is prepared?
- With the service's read, write, and iteration ratio, how does changing the map affect the overall task?
- With the same key and value objects, how much memory does the map structure retain on a specific JVM?

Measuring iteration alone differs from measuring both construction and iteration. Measuring the structural part differs from counting the entire referenced object graph. The measurement scope must accompany the result.

### 9.2. Timing on the JVM Has Many Confounding Factors

A `System.nanoTime` loop around a very short snippet can be affected by JVM warmup, JIT compilation, dead-code elimination, and system load. If you both create and iterate the map, the measurement includes allocation and construction.

When micro-experiments are needed, JMH is OpenJDK's toolkit for building and running JVM benchmarks. The tool does not fix flawed hypotheses or bad data, but it supports structuring measurements properly for the JVM environment. [OpenJDK: JMH](https://github.com/openjdk/jmh)

You need to record the JVM version, data, key type, hashing strategy, entry count, map configuration, operation mix, how results are consumed, and whether the scope includes allocation. Measure both options under equivalent conditions and interpret within that exact scope.

### 9.3. Byte Counts Require Observing Actual Layout

OpenJDK's JOL provides tools to analyze Java object layout and size. If you need byte counts, tie the results to the JVM version, configuration, and how shared objects are accounted for. [OpenJDK: JOL](https://github.com/openjdk/jol)

Do not take a single `Runtime.freeMemory` difference before and after creating a map once and treat it as the exact size. Garbage collection, JVM memory regions, and out-of-scope objects can affect it.

This lesson does not require installing those tools. The goal is to distinguish knowledge you can reason about from contracts and structure from results that must be measured in a specific environment.

## 10. Common Misconceptions

| Misconception | Correction |
|---|---|
| LinkedHashMap is always faster because iteration is O(N) | It has an iteration path that avoids scanning empty table slots; other operations and constants still matter |
| HashMap is always slow to iterate | When C is proportional to N, its iteration path is also linear in N; a concrete workload is needed |
| LinkedHashMap does not need to care about capacity | Iteration does not depend on scanning C, but the table still occupies memory |
| Same O(C + N) means equal memory | Same complexity order does not mean same constant factors or byte counts |
| Every entry always costs a fixed extra number of bytes | Must specify node type, layout, and JVM configuration |
| Preserving order means sorting keys | Must distinguish insertion order, access order, and key order |
| Copying to LinkedHashMap restores insertion history | Only preserves the order encountered in the source; it does not recover lost information |
| get is read-only so it cannot modify structure | In access-order mode, get can change the order |
| hashCode not being called means no table scan occurred | That counter does not observe all internal steps |
| One measurement decides for all data | Results are tied to the measured data, task, and environment |

## 11. Practice and Solutions

### Exercise 1. Size Is Not Capacity

A map has `size() = 200` but was prepared for a much larger amount of data. Why can't you replace every quantity in the iteration cost with 200?

**Solution:** `size()` only gives N, not C. The `HashMap` model includes both C + N, so knowing N is not enough to describe the impact of a sparse table. `LinkedHashMap`'s iteration path follows N, but its storage still contains a hash table. You must not use a conclusion about the iteration path in place of a conclusion about memory footprint.

### Exercise 2. Lookup-Heavy Workload

An application only queries total occurrences per code, rarely iterates in full, and has no ordering requirement. What is a reasonable starting point? When should you revisit it?

**Solution:** You can start with `HashMap` because ordering serves no requirement. Revisit if output later needs insertion order, the workload shifts to many iterations over a sparse table, or representative metrics point to an optimization need. If concurrent access exists, the concurrency contract must be evaluated separately.

### Exercise 3. First-Appearance Order

The input is `B, A, B, C, A`. You need to count and output in order of first appearance. What do you choose and in what order is the result?

**Solution:** Default `LinkedHashMap` gives the order `B, A, C` with counts `2, 2, 1`. Updating counts does not change insertion position. Do not choose access-order mode if you want to preserve first appearance regardless of subsequent updates.

### Exercise 4. Simplifying the Model

In a family of data where `C = 2N`, simplify the HashMap iteration cost. Can you conclude its runtime equals LinkedHashMap's?

**Solution:** `O(C + N) = O(3N) = O(N)`. Both iteration paths have the same linear order under that assumption. You cannot conclude equal runtime because Big O ignores constant factors and memory access patterns.

### Exercise 5. Model Ratio Is Not Speedup Ratio

With `N = 100` and `C = 1,000,000`, someone says LinkedHashMap is exactly 10,001 times faster. Correct that statement.

**Solution:** You can say the HashMap model has a table-scanning component that is very large relative to the number of entries; LinkedHashMap lacks that empty-slot scanning part when iterating. You cannot turn a ratio of model terms into a time ratio. You must measure if you need a speed number.

### Exercise 6. Fixing a Loop with Redundant Work

You need both key and value on an access-order `LinkedHashMap`, but are currently iterating `keySet` and calling `get`. State two reasons to switch to `entrySet`.

**Solution:** You can get both key and value directly from the entry, avoiding a redundant lookup. At the same time, `get` can alter order while the iterator is active; `entry.getValue()` does not generate such an access. Changing the iteration style does not by itself solve modifications from another thread.

Illustrative snippet:

~~~java
for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    System.out.println(entry.getKey() + ": " + entry.getValue());
}
~~~

### Exercise 7. Iteration and Storage Are Two Questions

A report says: "LinkedHashMap iterates independently of capacity, so setting capacity to one million for a few dozen entries costs nothing extra." Where is this wrong?

**Solution:** The report conflates iteration-path cost with storage cost. The chain avoids scanning empty table slots, but the table still exists for lookups. Excessive capacity can increase structural footprint and impact the memory subsystem.

### Exercise 8. Limits of the Counter

The program prints `iteratorHashCalls=0` for both capacity requests. What was observed and what was not measured?

**Solution:** It observed the number of calls to `Key`'s `hashCode` method during the counted section and verified the data via the sum. It did not measure scanned slots, actual capacity, time, byte count, or garbage collection. A zero result does not prove equal iteration cost.

### Exercise 9. Copying Does Not Restore History

You only receive a HashMap, with no history, and create a LinkedHashMap from it. Can you promise output in the original input order?

**Solution:** No. The new map keeps the order encountered when iterating over the source. The source does not guarantee that order is the input history. To promise input order, you must record the information at input time or have separate ordering data.

### Exercise 10. Workload-Driven Decision

A service keeps a small map, reads by key very frequently, exports everything once per hour, and has no ordering requirement. A coworker wants to switch solely because "LinkedHashMap iterates in O(N)." What needs to be checked?

**Solution:** Identify where the service spends significant time, the number of entries, sparsity, operation mix, work inside the export, and memory limits. One export per hour may not be the place to optimize. If there is a real issue, measure a representative task. If an ordering requirement appears later, that is a new functional reason to re-evaluate.

## 12. Self-Check Your Selection Reasoning

Before proposing to change a map class, fill in this sentence:

"The application needs ... regarding order, mainly performs ... with about ... entries, iterates ... times, and has a memory limit of ...; therefore, we choose ... and will measure ... if numbers are needed."

`LinkedHashMap` provides an ordering contract and an entry-count-based iteration path, while requiring extra link information and maintenance work. `HashMap` remains suitable for many lookup tables without ordering requirements. The right choice connects requirements, cost models, and evidence within the exact scope of use.
