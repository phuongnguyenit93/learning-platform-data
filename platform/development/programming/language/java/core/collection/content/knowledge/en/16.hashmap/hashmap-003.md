# Capacity, Load Factor, Resize Threshold, and Rehash

## 1. Why Does HashMap Need a Resizing Policy?

A `HashMap<K, V>` stores key–value mappings in a hash table. The table has entry slots called **buckets**. From a key's hash code, the implementation determines the bucket and searches for the corresponding mapping inside it.

Multiple keys can land in the same bucket. Therefore, a hash table is not an array where "each slot holds exactly one mapping, and more can only be added once every slot is full." A single bucket can manage multiple mappings; conversely, some buckets may be empty.

As the number of mappings grows, keeping a small table can cause more keys to concentrate in buckets and increase lookup work. Expanding the table provides more room for distribution, but requires allocating and reorganizing data. `HashMap` must balance these two costs.

The four concepts of this lesson relate as follows:

```text
Current number of mappings: size
             ↓ compared against
Resize threshold: threshold
             ↑ influenced by
Number of buckets: capacity × load factor policy
             ↓ when expansion is needed
Larger table + redistribution of mappings
             = resize / rehash in context
```

This lesson clearly separates two layers: **the HashMap API contract** and **OpenJDK implementation details**. Bucket counts, internal fields, and bucket-splitting algorithms are explained according to the referenced OpenJDK 17u source code. The programs are compiled with Java 17 compatibility and verified on JDK 24.0.2; internal observations are explicitly marked so they are not mistaken for a stable public API across all Java runtimes.

## 2. Four Quantities That Must Be Distinguished

| Quantity | Meaning | Can it be read directly via public API? |
|---|---|---|
| `size` | Number of mappings currently present | Yes: `map.size()` |
| `capacity` | Number of buckets in the allocated table | No public `HashMap.capacity()` |
| `load factor` | Policy parameter influencing load level before expansion | Chosen when constructing the map; no corresponding public getter/setter |
| `threshold` | Size threshold used by the implementation to decide when to expand | No public getter |

### Capacity Is Not the Maximum Number of Elements

A table with capacity `16` does not mean the map can store at most `16` mappings. When the policy requires it, it can expand and continue holding more. Even when the number of mappings exceeds the number of buckets, the model of multiple mappings per bucket can still represent the data.

Similarly, `new HashMap<>(100)` does not pre-create `100` mappings. The new map has `size() == 0`. This argument relates to initial capacity, not adding keys, nor is it a hard limit blocking the `101`st insertion.

### Size Changes with New Keys, Not with put Calls

A million `put` calls for the same logical key can still leave only one mapping. If each call merely replaces the value of an existing key, the size does not increase.

When estimating capacity, what needs to be estimated is the number of distinct logical keys coexisting at one time, typically the expected peak. The cumulative number of processed requests or method calls is not by itself the number of buckets needed.

## 3. Load Factor Is a Load Policy, Not the Percentage of Occupied Buckets

Let:

- `n`: current number of mappings.
- `m`: number of allocated buckets.
- `α = n / m`: current load level, once the table exists.
- `f`: chosen load factor.

`α` is the current state; `f` is a policy parameter. They are not two names for the same quantity.

With `n = 12`, `m = 16`, we have an average load of `α = 0.75`. That **does not guarantee that exactly 12 buckets contain data**. If multiple keys collide, the number of non-empty buckets can be smaller.

The default load factor of `HashMap` is `0.75f`. It balances the table's memory cost against lookup work within buckets across many common scenarios.

| Load factor choice | Trade-off tendency |
|---|---|
| Lower | Expands at a lower load; usually requires more buckets for the same number of mappings |
| Higher | May use fewer buckets; on average may increase processing work inside buckets |
| Default `0.75f` | Reasonable starting point when there is no measurement data requiring a change |

These are tendencies, not a guarantee that one choice is always faster. The hash function, key type, access pattern, iteration frequency, memory, and value cost can all have an impact.

Load factor is not conceptually restricted to the range "0 to 1" like a percentage of filled slots. A value greater than `1` does not mean the map cannot function, because a bucket can hold multiple mappings. However, you should not pick an extreme factor just to delay resizing while ignoring lookup cost.

Constructors reject negative capacities and non-positive load factors; OpenJDK source code also checks for `NaN`. An initial capacity of `0` is allowed, but does not turn the map into a structure where data cannot be added. Very small configurations and boundary values must follow the implementation's rounding rules.

## 4. Resize Threshold: Reaching the Threshold vs. Exceeding the Threshold

The commonly used model is:

```text
threshold ≈ capacity × load factor
```

For power-of-two capacities and the default factor in typical examples, the thresholds are:

| Allocated capacity | Load factor | Threshold |
|---:|---:|---:|
| 4 | 0.75 | 3 |
| 8 | 0.75 | 6 |
| 16 | 0.75 | 12 |
| 32 | 0.75 | 24 |
| 64 | 0.75 | 48 |

Considering OpenJDK's normal `put` path, assuming no other collision policy triggers early expansion and the capacity limit has not been reached: after inserting a **new key**, the implementation increments `size` and then checks whether the threshold is exceeded.

With capacity `16`, threshold `12`:

- After the `12`th key: `size == 12`, not yet exceeding this threshold.
- After the `13`th key: `size == 13 > 12`, expansion is needed along the load-check path.
- Overwriting an existing key only replaces the value, without incrementing `size` to follow that new-insertion path.

Do not use `>=` instead of `>` when predicting the exact `put` sequence in this example. At the same time, do not turn this model into an assumption that every other method checks at the exact same place in the source code: bulk operations and compute/update methods may take different implementation paths.

### Why Use an Approximation Sign Instead of an Absolute Formula for Every Configuration?

The threshold is an integer. The implementation has rounding steps, can double the old threshold in one resize path, and has special handling at the limit.

For example, with load factor `0.6f`, a table of `16` can have an initial threshold of `9`. When expanding to `32` via the path that doubles the old threshold, the threshold becomes `18`, rather than necessarily recomputing `floor(32 × 0.6)` to get `19`.

Therefore:

- Use the product `capacity × load factor` to understand the policy and for general planning.
- Use the known values of the default configuration when solving specific problems.
- When you need exact internal numbers for a custom configuration, check the actual implementation rather than deducing every case from a simplified formula.

## 5. Initial Capacity, Rounding, and Lazy Allocation

OpenJDK organizes hash table lengths as powers of two, within the implementation's limits. Constructor arguments are converted to an appropriate target capacity.

Examples of common target capacities:

| `initialCapacity` argument | Target capacity per OpenJDK rounding |
|---:|---:|
| 4 | 4 |
| 13 | 16 |
| 16 | 16 |
| 17 | 32 |
| 100 | 128 |
| 134 | 256 |

This does not mean the table is allocated immediately in the constructor. In the constructors observed in OpenJDK, allocating the bucket array is deferred until data insertion is needed.

With `new HashMap<>(17)`:

```text
Just constructed:
    size = 0
    no bucket array yet
    holds target capacity info 32

After the first put:
    table of length 32 exists
    typical threshold = 24 with default factor
```

### The Internal Field Named `threshold` May Hold Other Information Before Allocation

Before the table exists, OpenJDK may use the `threshold` field to hold the target capacity. Therefore, reading `thresholdField = 32` when `tableLength = 0` does not mean an empty table is allowing `32` mappings before resizing.

Only after the table is allocated does this field take on the threshold role corresponding to the table state in the examples under consideration.

This is one reason not to turn private fields into a business interface. An internal field's name is not a contract for a single meaning across every lifecycle state.

### What Does Default Capacity 16 Mean?

The API describes the default initial capacity as `16` and load factor as `0.75`. With lazy allocation, that corresponds to the first table typically having length `16` when it needs to be created, rather than requiring a newly constructed map to already have a 16-bucket array in memory.

These two statements do not contradict each other: one is about initial configuration, and the other is about when the implementation allocates.

### No Infinite Expansion

OpenJDK 17u source code uses the limit `MAXIMUM_CAPACITY = 1 << 30` for table length. Once the maximum capacity is reached, the implementation does not keep doubling the array indefinitely and has a corresponding threshold-adjustment path.

This limit refers to the number of buckets, not a promise that that many objects can be stored in the heap, nor a way to equate capacity with maximum mappings. Memory may run out long before hitting that limit. There is no need—and it is not advisable—to allocate a massive table just to verify the formulas in this lesson.

The planning function in a later section proactively rejects requests outside its range. Arithmetic checks only protect the calculation and model domain; they do not guarantee an actual allocation will succeed.

## 6. Complete Experiment: Observing Resize Milestones

The program below uses reflection to observe two private fields of the `HashMap` implementation: `table` and `threshold`.

This is an **experiment about the implementation**, not how to write capacity-dependent application code. `HashMap` does not expose these two fields publicly. The run command includes `--add-opens java.base/java.util=ALL-UNNAMED` to allow the experiment program in that process reflective access to the corresponding package. Compiling alone and omitting that option at runtime may be rejected by module encapsulation.

OpenJDK 17u source code is used to explain the mechanism; the results below were measured on JDK 24.0.2. Private field names and observed numbers are not guaranteed interfaces across all implementations or all versions.

```java
import java.lang.reflect.Field;
import java.util.HashMap;

public class HashMapCapacityObservationDemo {
    private static final Field TABLE;
    private static final Field THRESHOLD;

    static {
        try {
            TABLE = HashMap.class.getDeclaredField("table");
            THRESHOLD = HashMap.class.getDeclaredField("threshold");
            TABLE.setAccessible(true);
            THRESHOLD.setAccessible(true);
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private static void show(String label, HashMap<?, ?> map)
            throws IllegalAccessException {
        Object[] table = (Object[]) TABLE.get(map);
        int length = table == null ? 0 : table.length;
        System.out.println(label + ": size=" + map.size()
                + ", tableLength=" + length
                + ", thresholdField=" + THRESHOLD.getInt(map));
    }

    record SameHashKey(int id) {
        @Override
        public int hashCode() {
            return 0;
        }
    }

    public static void main(String[] args) throws IllegalAccessException {
        HashMap<Integer, String> map = new HashMap<>(4, 0.75f);
        show("beforeAnyPut", map);
        map.put(1, "v1");
        show("afterPut1", map);
        map.put(2, "v2");
        map.put(3, "v3");
        show("afterPut3", map);
        map.put(1, "updated");
        show("afterOverwrite", map);
        map.put(4, "v4");
        show("afterPut4", map);
        map.put(5, "v5");
        map.put(6, "v6");
        show("afterPut6", map);
        map.put(7, "v7");
        show("afterPut7", map);
        map.remove(7);
        show("afterRemove", map);
        map.clear();
        show("afterClear", map);

        HashMap<Integer, Integer> defaults = new HashMap<>();
        show("defaultBeforePut", defaults);
        defaults.put(1, 1);
        show("defaultAfterPut", defaults);

        HashMap<Integer, Integer> rounded = new HashMap<>(17);
        show("requested17BeforePut", rounded);
        rounded.put(1, 1);
        show("requested17AfterPut", rounded);

        for (float factor : new float[] {0.5f, 0.75f, 1.0f}) {
            HashMap<Integer, Integer> sample = new HashMap<>(16, factor);
            sample.put(1, 1);
            show("factor" + factor, sample);
        }

        HashMap<Integer, Integer> fractional = new HashMap<>(16, 0.6f);
        for (int i = 0; i < 10; i++) {
            fractional.put(i, i);
        }
        show("factor0.6After10", fractional);

        HashMap<SameHashKey, Integer> collision = new HashMap<>(16);
        for (int i = 0; i < 9; i++) {
            collision.put(new SameHashKey(i), i);
        }
        show("collisionAfter9", collision);
    }
}
```

Save as `HashMapCapacityObservationDemo.java`, compile and run:

```shell
javac --release 17 -encoding UTF-8 HashMapCapacityObservationDemo.java
java --add-opens java.base/java.util=ALL-UNNAMED HashMapCapacityObservationDemo
```

Verified output:

```text
beforeAnyPut: size=0, tableLength=0, thresholdField=4
afterPut1: size=1, tableLength=4, thresholdField=3
afterPut3: size=3, tableLength=4, thresholdField=3
afterOverwrite: size=3, tableLength=4, thresholdField=3
afterPut4: size=4, tableLength=8, thresholdField=6
afterPut6: size=6, tableLength=8, thresholdField=6
afterPut7: size=7, tableLength=16, thresholdField=12
afterRemove: size=6, tableLength=16, thresholdField=12
afterClear: size=0, tableLength=16, thresholdField=12
defaultBeforePut: size=0, tableLength=0, thresholdField=0
defaultAfterPut: size=1, tableLength=16, thresholdField=12
requested17BeforePut: size=0, tableLength=0, thresholdField=32
requested17AfterPut: size=1, tableLength=32, thresholdField=24
factor0.5: size=1, tableLength=16, thresholdField=8
factor0.75: size=1, tableLength=16, thresholdField=12
factor1.0: size=1, tableLength=16, thresholdField=16
factor0.6After10: size=10, tableLength=32, thresholdField=18
collisionAfter9: size=9, tableLength=32, thresholdField=24
```

### 6.1. Capacity Sequence 4 → 8 → 16

Before the first `put`, there is no table yet, so `tableLength=0`; `thresholdField=4` is the preparation info for the target capacity.

After the first insertion, the table length is `4` and the threshold is `3`. Three keys stay in the length-`4` table; overwriting key `1` does not increase size.

The `4`th key causes size to exceed threshold `3`, so the table grows to `8` with threshold `6`. The `6`th key does not exceed `6`, whereas the `7`th key causes the table to grow to `16` with threshold `12`.

### 6.2. Remove and Clear Do Not Shrink the Table in This Observation

After `remove`, size decreases, but table length remains `16`. After `clear`, the map is empty, yet it still retains the allocated table.

In the referenced OpenJDK implementation, `remove` and `clear` do not automatically perform a table-shrinking mechanism symmetric to table expansion. `clear` drops references to mappings in the buckets, which does not mean all memory of the structure is immediately freed.

Therefore, do not use `size() == 0` to infer that a map has not allocated or has released all hash table memory.

### 6.3. Load Factor 0.6 and the Rounding Path

The three factors `0.5`, `0.75`, and `1.0` produce thresholds `8`, `12`, and `16` for a length-`16` table in the sample.

The line `factor0.6After10` shows the table is now length `32` and the threshold field is `18`. This illustrates that the product-rounding formula is not strictly reapplied on every capacity increase.

### 6.4. Resizing Has More Than One Cause

The line `collisionAfter9` has size `9`, table length `32`, and threshold `24`. The keys have the same hash code and therefore concentrate in a single bucket.

In OpenJDK, when a bucket has too many nodes, the path for converting to a tree structure also checks the minimum table capacity. If the table is still small, it may choose to expand first. In the source code under review, `MIN_TREEIFY_CAPACITY` is `64`; this is a completely different threshold from the whole-map load threshold.

Thus, a table can grow in capacity even when `size` has not exceeded the load threshold we calculated. Do not conflate the whole-map threshold with the node count inside a single bucket as the same concept.

This lesson does not go deep into treeification algorithms. The takeaway for this topic is that **having enough capacity according to the load factor does not eliminate all possibilities of collision-related resizing**.

## 7. Estimating Capacity When the Expected Number of Mappings Is Known

Suppose at most `N` distinct logical keys are expected to coexist, using load factor `f`. The usual goal is to choose a table whose load threshold is at least `N`.

One planning approach is:

```text
Capacity to consider ≈ ceil(N / f)
        ↓
Choose a table capacity matching the implementation's rounding
        ↓
Verify whether the actual threshold of that configuration meets N
```

With the default factor `0.75`, you can use:

```text
ceil(N / 0.75) = ceil(4N / 3)
```

This is planning to avoid resizing **due to exceeding the load threshold** under normal configurations—not a proof that no operation can ever resize for any reason. Collisions, bulk operations, implementation limits, and data usage patterns must still be considered.

### 7.1. Why Might `new HashMap<>(100)` Not Suffice for 100 Keys Without Resizing?

In the implementation under consideration:

```text
Argument 100
    → target capacity 128
    → default threshold 96

Inserting 100 distinct keys via put:
    → insertions past 96 can trigger load-based resizing
```

If `ceil(100 / 0.75) = 134` is passed as the argument:

```text
Argument 134
    → target capacity 256
    → default threshold 192
```

The second approach allocates a larger table on the first allocation, avoiding the step from `128` to `256` caused by exceeding `96` keys. Both may eventually end up with a table of length `256`, but the allocation and data reorganization process differs.

Do not compare `100` and `134` and conclude the final memory differs by only `34` slots. The implementation rounds to powers of two, so capacity steps are discrete.

### 7.2. Meeting the Threshold Does Not Require Mechanically Adding One

For `N=12`, passing `16` gives a table with threshold `12` at the default factor. In the normal `put` sequence described, the `12`th key has not exceeded the threshold; simply reaching the threshold does not force a resize.

A conservative formula may add extra margin, but you should know why you are adding it. Arbitrarily adding `1` can push the target capacity past a power-of-two boundary and significantly increase the allocated table.

Conversely, casting `(int)(N / 0.75)` truncates downward and cannot arbitrarily substitute for ceiling division. Check the arithmetic, value domain, and constructor rounding rather than blindly copying an expression.

### 7.3. `N` Is the Number of Concurrent Keys, Not the Number of Writes

If you process one million updates while keeping only `500` distinct item codes, there is no automatic basis for sizing capacity for one million updates.

If the key count rises to one million and then drops to a few hundred, that is a different lifecycle problem: the expanded capacity may be retained. You need to consider peak size, map lifetime, and iterations after the data shrinks.

Overestimating capacity is not free. It can make the initial allocation more expensive and make table iteration less efficient even when `size` is small.

## 8. Complete Program: Planning with the Default Factor

The following program uses `long` integer arithmetic to compute `ceil(4N/3)`, avoiding `int` multiplication overflow before division.

`modeledTable` and `modeledThreshold` are **modeled values computed according to OpenJDK rules within the example's scope**, not internal fields read from the program. `actualSize` is the mapping count obtained from the real map via public API.

The cases run are all small with `N>0`. The planning range check is not a guarantee that the system has enough heap for every accepted value.

```java
import java.util.HashMap;

public class HashMapSizingDemo {
    private static int capacityArgumentForDefaultFactor(int expected) {
        if (expected < 0) {
            throw new IllegalArgumentException("negative expected count");
        }
        long requested = (4L * expected + 2) / 3;
        long maximumCapacity = 1L << 30;
        if (requested > maximumCapacity) {
            throw new IllegalArgumentException("outside planning range");
        }
        return (int) requested;
    }

    private static int modeledTableLength(int requested) {
        int capacity = 1;
        while (capacity < requested) {
            capacity <<= 1;
        }
        return capacity;
    }

    public static void main(String[] args) {
        for (int expected : new int[] {1, 3, 4, 12, 13, 100, 1000}) {
            int requested = capacityArgumentForDefaultFactor(expected);
            int tableLength = modeledTableLength(requested);
            int threshold = (int) (3L * tableLength / 4);

            HashMap<Integer, Integer> map = new HashMap<>(requested);
            for (int i = 0; i < expected; i++) {
                map.put(i, i);
            }
            System.out.println("expected=" + expected
                    + ", argument=" + requested
                    + ", modeledTable=" + tableLength
                    + ", modeledThreshold=" + threshold
                    + ", actualSize=" + map.size());
        }

        try {
            capacityArgumentForDefaultFactor(-1);
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("negativeExpected=IllegalArgumentException");
        }
    }
}
```

Save as `HashMapSizingDemo.java`, compile and run:

```shell
javac --release 17 -encoding UTF-8 HashMapSizingDemo.java
java HashMapSizingDemo
```

Verified output:

```text
expected=1, argument=2, modeledTable=2, modeledThreshold=1, actualSize=1
expected=3, argument=4, modeledTable=4, modeledThreshold=3, actualSize=3
expected=4, argument=6, modeledTable=8, modeledThreshold=6, actualSize=4
expected=12, argument=16, modeledTable=16, modeledThreshold=12, actualSize=12
expected=13, argument=18, modeledTable=32, modeledThreshold=24, actualSize=13
expected=100, argument=134, modeledTable=256, modeledThreshold=192, actualSize=100
expected=1000, argument=1334, modeledTable=2048, modeledThreshold=1536, actualSize=1000
negativeExpected=IllegalArgumentException
```

### Explaining the Milestones

- `N=3`: argument `4`, modeled table `4`, threshold `3`.
- `N=4`: computed argument `6`, modeled table rounds up to `8`, threshold `6`.
- `N=12`: modeled table `16`, threshold `12`.
- `N=13`: argument `18`, modeled table `32`, threshold `24`.
- `N=100`: argument `134`, modeled table `256`, threshold `192`.
- `N=1000`: argument `1334`, modeled table `2048`, threshold `1536`.

Having `N` mappings in the real map confirms the insertion loop and created data. The `actualSize` line alone **does not prove the map did not resize**; observing actual capacity requires a suitable observation mechanism like the separate experiment in Section 6.

For `N=0`, an empty map may not need to allocate a table yet. Do not use the example's rounding model function to infer an existing table when no data has been inserted.

### Why Not Allocate a Huge Table "Just to Be Safe"?

Because the costs involved are not just the number of resizes:

- A larger table holds more bucket references.
- Iterating a `HashMap` has costs related to both capacity and size.
- Allocation timing can create memory allocation pressure.
- A large overestimate can waste memory for the entire lifetime of the map.
- Key and value objects still require their own memory.

Pre-sizing capacity is a targeted optimization, not a "bigger is always better" rule. For small or unpredictable counts, the default configuration is usually simpler; change it when you have specific requirements and evidence.

## 9. What Do Resize and Rehash Actually Do?

In hash table contexts, "rehash" is often used to mean rebuilding the distribution of mappings when capacity changes. However, this word is easily misunderstood as "calling `hashCode` again on every key."

In the OpenJDK version under review, each node stores processed hash information. When growing the table, the implementation can use that stored information to determine new positions without re-invoking `key.hashCode()` for each existing key.

Conceptual steps:

1. Determine the new capacity and corresponding threshold.
2. Allocate a new bucket array.
3. Traverse the old table.
4. Place nodes or groups of nodes into the appropriate buckets in the new table.
5. Have the map continue accessing mappings through the new table.

Key and value objects are not deep-copied just because of a resize. For normal chains, the implementation reuses node structures; tree branches have their own handling. Do not describe resizing as recreating all business objects.

### 9.1. Why Is Doubling Convenient for Power-of-Two Capacities?

In the OpenJDK implementation under review, with a spread hash `h` and a power-of-two table length `m`, the index is computed in the form:

```java
// Implementation formula, not a general Map API.
int index = h & (m - 1);
```

When growing from `m` to `2m`, the mask gains exactly one additional bit to inspect. An element from old bucket `j` can either:

- Stay in bucket `j` if the extra bit is `0`.
- Move to bucket `j + m` if the extra bit is non-zero.

This grouping can be expressed using `h & m`.

This is not random splitting, and it does not mean all elements in a bucket stay together. Elements that collided in the smaller table may separate when the new distinguishing bit is added.

### 9.2. Example from Capacity 4 to 8

For small hash codes `1`, `5`, `9`, `13`, OpenJDK's illustrative spreading does not change them because their upper bits are `0`.

```text
Old table 4: mask 3 = ...0011
New table 8: mask 7 = ...0111
Extra bit:        4 = ...0100
```

| h | Old index: h & 3 | Extra bit: h & 4 | New index: h & 7 |
|---:|---:|---:|---:|
| 1 | 1 | 0 | 1 |
| 5 | 1 | 4 | 5 |
| 9 | 1 | 0 | 1 |
| 13 | 1 | 4 | 5 |

All four elements were in bucket `1` previously. After growing the table, two are at `1` and two are at `5`.

Being able to split like this does not guarantee all collisions will disappear. If multiple keys share the exact same processed hash code, adding more indexing bits still cannot distinguish them by hash. Therefore, increasing capacity does not replace a well-distributed hash code.

### 9.3. Raw Hash, Spread Hash, and Bucket Index Are Different

OpenJDK performs a hash-spreading step of the form `h ^ (h >>> 16)` for non-null keys. The information stored and used for distribution should not be confused with a fixed bucket index.

- `key.hashCode()` is the hash code provided by the key class.
- The map's processing produces the hash information used internally.
- The table length together with that information determines the bucket index.

The bucket index can change when capacity changes, even though key identity and `key.hashCode()` remain unchanged. Mask-based indexing is also not `hashCode % size`; using `size` instead of capacity or using an unhandled negative remainder are incorrect models.

## 10. Complete Program: Modeling Bucket Splitting on Doubling

This program **does not read or modify a real HashMap**. It computes indices using the formula to illustrate the grouping step when growing a table from `4` to `8`.

```java
public class HashMapResizeSplitDemo {
    private static int spread(int rawHash) {
        return rawHash ^ (rawHash >>> 16);
    }

    public static void main(String[] args) {
        int oldCapacity = 4;
        int newCapacity = oldCapacity * 2;

        for (int rawHash : new int[] {1, 5, 9, 13}) {
            int storedHash = spread(rawHash);
            int oldIndex = storedHash & (oldCapacity - 1);
            int newIndex = storedHash & (newCapacity - 1);
            int extraBit = storedHash & oldCapacity;
            System.out.println("raw=" + rawHash
                    + ", oldIndex=" + oldIndex
                    + ", extraBit=" + extraBit
                    + ", newIndex=" + newIndex);
        }
    }
}
```

Save as `HashMapResizeSplitDemo.java`, compile and run:

```shell
javac --release 17 -encoding UTF-8 HashMapResizeSplitDemo.java
java HashMapResizeSplitDemo
```

Verified output:

```text
raw=1, oldIndex=1, extraBit=0, newIndex=1
raw=5, oldIndex=1, extraBit=4, newIndex=5
raw=9, oldIndex=1, extraBit=0, newIndex=1
raw=13, oldIndex=1, extraBit=4, newIndex=5
```

The two rows with `extraBit=0` keep index `1`; the two rows with `extraBit=4` move to `5 = 1 + 4`.

This model helps explain the algorithm, not an API for applications to manage buckets manually. When using `HashMap` normally, applications only interact via keys and values; there is no need to precompute buckets for lookup.

Iteration order can change when the table structure changes. `HashMap` does not guarantee order anyway; the fact that a group of nodes preserves relative order in an internal processing branch creates no whole-map ordering guarantee.

## 11. Complete Program: Does Resize Re-Invoke `hashCode` on Existing Keys?

The example below uses a key with a `hashCode` call counter. The returned hash code remains the immutable `id`; the counter is only for observation and does not participate in equality or the hash code value.

This is an experiment about call counts on the running implementation, not a call count permanently guaranteed by the `HashMap` API. Do not write business logic that depends on a hash method being called an exact number of times.

```java
import java.util.HashMap;

public class HashMapStoredHashDemo {
    static final class TrackedKey {
        private final int id;
        private int hashCalls;

        TrackedKey(int id) {
            this.id = id;
        }

        @Override
        public int hashCode() {
            hashCalls++;
            return id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof TrackedKey key && id == key.id;
        }
    }

    public static void main(String[] args) {
        TrackedKey[] keys = {
            new TrackedKey(1),
            new TrackedKey(5),
            new TrackedKey(9),
            new TrackedKey(13)
        };
        HashMap<TrackedKey, String> map = new HashMap<>(4, 0.75f);

        for (int i = 0; i < 3; i++) {
            map.put(keys[i], "v" + keys[i].id);
        }
        System.out.println("sizeBeforeFourth=" + map.size());

        map.put(keys[3], "v13");
        System.out.println("sizeAfterFourth=" + map.size());
        for (TrackedKey key : keys) {
            System.out.println("id=" + key.id
                    + ", observedHashCalls=" + key.hashCalls);
        }

        boolean allPresent = true;
        for (TrackedKey key : keys) {
            String value = map.get(new TrackedKey(key.id));
            allPresent &= ("v" + key.id).equals(value);
        }
        System.out.println("allMappingsPresent=" + allPresent);
    }
}
```

Save as `HashMapStoredHashDemo.java`, compile and run:

```shell
javac --release 17 -encoding UTF-8 HashMapStoredHashDemo.java
java HashMapStoredHashDemo
```

Verified output:

```text
sizeBeforeFourth=3
sizeAfterFourth=4
id=1, observedHashCalls=1
id=5, observedHashCalls=1
id=9, observedHashCalls=1
id=13, observedHashCalls=1
allMappingsPresent=true
```

### What Was Observed

The map is created with target capacity `4` and load factor `0.75f`. Inserting four distinct keys crosses the load-based resize milestone explained in earlier sections.

After the fourth insertion, each key object still records only one `hashCode` call from when it was inserted. Existing keys did not have their hash function re-invoked just to redistribute them during this resize.

Subsequent `get` calls use new probe objects. The counters of those new objects are not mixed into the printed counter lines of the original key objects. `allMappingsPresent=true` confirms the mappings remain retrievable after the insertion sequence.

From this result, we can properly understand the term "rehash" in the implementation under review: reorganizing buckets based on stored hash information, without necessarily recomputing the business hash function of every existing key.

### Resize Does Not Fix a Key with a Broken Contract

If a key object's data participating in `equals` or `hashCode` is mutated after being placed in the map, do not expect a resize to recompute it and fix the state for the application.

In fact, the use of stored hash information is all the more reason not to rely on that expectation. What you must do is keep key identity stable while it serves as a key, rather than hoping a resize will repair a design flaw.

The counter in the example is a single-threaded experimental tool. A `hashCode` implementation used in normal applications should be simple, stable, and free of business side effects based on call count.

## 12. Expansion Cost and the Meaning of Amortized O(1)

A single `put` does not always modify just one node. If it triggers an expansion, the map may have to allocate a new table and traverse the old buckets and mappings.

The cost of a single resize relates to the old table capacity and the number of mappings to reorganize. It can be significant compared to a normal insertion.

Because capacity typically grows exponentially, expansions do not happen on every insertion. Across a sequence of insertions under reasonable hash distribution conditions, the total resize cost is spread across many operations. That is what **amortized** means when speaking of normal insertion cost.

Example of the sum of table lengths across a doubling sequence:

```text
16 + 32 + 64 + ... + M
```

This sum is of the same order as `M`, rather than every insertion having to move all data from scratch. Still, a specific operation at a resize milestone can be noticeably slower than the one immediately before it.

Distinguish carefully:

- The assumption of good hash distribution concerns how keys spread across buckets.
- Amortization concerns how the cost of resize bursts is spread across a sequence of operations.
- Neither turns every individual `put` into a constant-time guarantee regardless of data and `hashCode`/`equals` work.

If an application is sensitive to a single latency spike, reducing resizes via capacity estimation can help. To draw conclusions about actual latency, you still need to measure under realistic load, including allocation and garbage collection.

### Peak Memory Also Matters

During resizing, the new table is allocated while transferring data from the old table is still in progress. Thus, both bucket arrays can temporarily coexist, making peak memory demand higher than the steady state afterward.

Do not infer that all keys and values are deep-duplicated; that is not the mechanism described. At the same time, do not look only at the final capacity and ignore the transition cost.

Actual byte counts depend on the implementation structure, reference size, key/value objects, JVM configuration, and data. Capacity is a bucket count, not a unit of bytes.

## 13. Choosing Load Factor and Map Lifecycle by Requirements

### When to Consider Initial Capacity

It is helpful when the number of mappings to be loaded is fairly well known, the map is of significant size, or you want to reduce resize bursts during a latency-sensitive processing phase.

Estimates should be based on the number of coexisting keys with a justified safety margin. Do not size for the total cumulative number of events if they repeatedly update the same small set of keys.

### When Not to Customize Load Factor Yet

If there is no measured problem, changing the default factor may merely trade an unmeasured cost for a different one.

- Lowering the factor can increase bucket count and table iteration cost.
- Raising the factor can reduce table memory but increase work inside buckets.
- Poor hash codes or many keys with the same hash are not cured simply by changing the factor.
- A key with a broken contract remains broken regardless of the factor.

If you choose a different factor, test map construction, lookups, updates, iteration, and memory usage appropriate to your application, rather than relying on a single micro-measurement.

### When a Map Was Once Very Large and Then Shrinks

In the OpenJDK version under review, removing mappings does not automatically shrink the table. If a long-lived map drops from very many keys to very few and continues to be iterated frequently, the large table can remain a cost.

One option to consider after measuring is building a new map sized to the current data scale and transferring the mappings that still need to be kept. This is not a public "trim" call on `HashMap`.

Illustrative snippet when holding exclusive ownership of the source:

```java
HashMap<K, V> rebuilt = new HashMap<>(source);
```

The snippet above uses type parameters `K`, `V` and a variable `source` available in the application context; it is not a standalone program. It copies mappings into another map, does not deep-copy keys/values, and does not automatically update references or views still pointing to the old map.

The copy constructor has its own policy; do not assume all custom parameters of the source map are preserved. Moving to a new map also incurs allocation and copying costs, so it should not be done mechanically after every deletion.

### Resizing Is Not a Synchronization Mechanism

`HashMap` does not provide built-in synchronization for multiple threads modifying its structure. Choosing a large capacity "to be sure it won't resize" does not make it safe for concurrent access.

A single new insertion is already a structural modification, whether or not a resize occurs. When multiple threads share data, you must design coordination or choose a structure with an appropriate contract. The examples in this lesson use a single thread to focus on capacity policy.

## 14. Misconceptions to Avoid

| Misconception | Accurate understanding |
|---|---|
| Capacity is size | Capacity counts buckets; size counts mappings |
| `HashMap<>(N)` pre-adds N elements | The map is still empty; N relates to initial capacity |
| Load factor 0.75 means 75% of buckets definitely have data | It is a load factor of mappings to capacity, not a count of non-empty buckets |
| Reaching the exact threshold always resizes | The normal `put` sequence checks for exceeding the threshold; other implementation paths must be examined separately |
| Only exceeding the load threshold triggers resize | Collision handling can trigger expansion when the table is still small |
| Rehash always re-invokes `hashCode` on every old key | OpenJDK can redistribute using stored hash information |
| `HashMap` automatically shrinks capacity after `remove`/`clear` | The observed implementation retains the table; there is no symmetric automatic shrink in those operations |
| Larger capacity is always faster | Memory and iteration costs can increase |
| Avoiding resize is enough to make `HashMap` thread-safe | Synchronization is a separate requirement and is not solved by capacity |
| Changing load factor fixes broken `equals`/`hashCode` | The key contract must be fixed in the key class and its usage |

## 15. Self-Check Before Running the Examples

### Question 1: Capacity 16, Factor 0.75

In a normal `put` sequence of new keys, assuming no early collision-triggered expansion, the threshold is `12`. Is a load-based resize required after the `12`th key? What about after the `13`th key?

**Answer:** The `12`th key only reaches the threshold without exceeding it. The `13`th key exceeds the threshold and goes through the load-based resize path described.

### Question 2: Writing One Key Many Times

A map has `size=12`, threshold `12`. You call `put` a thousand times only to replace the value of an existing key. Can you conclude the number of mappings increases by one thousand?

**Answer:** No. Overwriting an existing logical key replaces its value, does not create a thousand new mappings, and does not follow the size-increment path of adding new keys.

### Question 3: Load Factor Is Not Occupancy

A map has `12` mappings and a table length of `16`. Is it guaranteed that exactly `12` buckets are non-empty?

**Answer:** No. Multiple mappings can reside in the same bucket. An average load of `12/16` does not equal the number of non-empty buckets.

### Question 4: Argument 100

Under the OpenJDK rules examined, what target table length and default threshold does an initial capacity argument of `100` typically lead to?

**Answer:** Target table `128`, typical threshold `96` after allocation. Therefore, you cannot treat argument `100` as a promise to hold `100` distinct keys without load-based resizing.

### Question 5: Planning for 100 Keys

With load factor `0.75`, what is `ceil(100/0.75)`? What is the modeled capacity after rounding?

**Answer:** Estimated argument `134`, modeled table `256`, default threshold `192`. This plans for load, without ruling out every other cause of resizing.

### Question 6: Array Does Not Exist Yet

Reflection shows `tableLength=0`, `thresholdField=32` right after `new HashMap<>(17)`. Should this be interpreted as an already-allocated table of length `32`?

**Answer:** No. That is pre-allocation target capacity information in this implementation. You must distinguish internal field states before and after the table exists.

### Question 7: Old Bucket 1, Capacity 4

A processed hash code has `h & 3 = 1` and `h & 4 = 4`. When the table grows from `4` to `8`, what is the new index?

**Answer:** `1 + 4 = 5`. The extra bit determines moving to the upper half.

### Question 8: All Hashes Identical

If distinct keys have the exact same processed hash code, will doubling the table necessarily spread them into different buckets?

**Answer:** No. Identical hash information leads to identical bits used for indexing. You must distinguish between adding capacity and hash code distribution quality.

### Question 9: Does Rehash Fix a Mutated Key?

A key has its hash-determining data mutated while inside the map. Should you insert more data hoping a resize will re-invoke `hashCode` and fix the issue?

**Answer:** No. The implementation can use the stored hash code, and the key stability requirement has already been violated. You must fix the key design and usage.

### Question 10: `clear` Then Size 0

After a map has been large, `clear()` brings size back to `0`. Does that guarantee the bucket array also returns to an unallocated state?

**Answer:** No. Experiments and OpenJDK source code show the table can be retained. A logical size of 0 is not enough to describe structural memory.

### Question 11: Factor 0.6

A table of `16` has threshold `9`, and then the resize path doubles the old threshold when the table grows to `32`. Must the threshold be `floor(32 × 0.6)=19`?

**Answer:** No. The doubling path under review produces `18`. The product formula is a policy model; the exact internal number depends on the implementation steps.

### Question 12: One Slow `put` at a Resize Milestone

Does that contradict saying insertion cost is typically analyzed as amortized O(1) under suitable conditions?

**Answer:** No. Amortization spreads the cost of resize bursts across a sequence of operations; it does not promise every individual insertion takes the same time.

## 16. Practice: Build a Prediction Table and Verify

### Part A — Default Configuration

Do not use reflection before making predictions. Consider a sequence of inserting distinct keys with `put`, with no collision handling triggering early expansion:

1. Current table length is `8`, load factor `0.75`.
2. Write the corresponding threshold.
3. Predict the table length when size is `5`, `6`, and `7` respectively.
4. After size `7`, replace the value of an existing key and then remove one key.
5. State what changes in `size`, and what does not automatically change in `capacity` in the implementation under review.

**Expected result:** initial threshold `6`; sizes `5` and `6` stay in table `8`; the insertion reaching `7` moves to table `16`. Overwriting a key does not increase size; removing decreases size without automatically shrinking the table per the lesson's OpenJDK description.

Afterward, you can modify the observation program to verify against the runtime you are using, still noting clearly that this is private-field observation.

### Part B — Capacity for a Batch Load

Expecting `500` distinct keys, default factor:

1. Compute `ceil(500/0.75)`.
2. Round the target capacity up to a power of two.
3. Compute the default threshold of that table.
4. Compare with passing `500` directly as initial capacity.

**Answer:** estimated argument `667`, target table `1024`, threshold `768`. Passing `500` directly aims at table `512`, threshold `384`, so a batch of `500` keys may need to resize due to load.

### Part C — Measuring Without Misreading What Was Measured

If you use a timing program to compare two configurations, state clearly:

- Does the time include map creation, table allocation, key insertion, or only lookups?
- Does the data have the same number of logical keys and the same hash characteristics?
- Are you comparing a short run affected by startup/JIT/GC?
- Are you observing memory and iterations after loading?
- Which data and environment does the conclusion apply to, or is it overgeneralizing?

The goal of this practice is to understand and verify capacity policy, not to turn a random measurement into a claim that every program must use the same configuration.

## References

- [Java 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): capacity, load factor, rehash policy, constructors, and iteration cost.
- [OpenJDK 17u Source — HashMap.java](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/HashMap.java): lazy allocation, `tableSizeFor`, `putVal`, `resize`, bucket splitting, and minimum capacity handling when treeifying buckets.

Programs include full compile/run commands. Code was verified with `javac --release 17 -encoding UTF-8` and run on JDK 24.0.2. Modeling formulas, call-count measurements, and private access are marked within their proper scope; do not treat them as public API of every `Map` or every Java runtime.
