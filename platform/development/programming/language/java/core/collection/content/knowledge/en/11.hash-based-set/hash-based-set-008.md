# Comparing HashSet and LinkedHashSet in Time and Memory

## 1. Choose by Workload, Not Just by Structure Name

`HashSet` and `LinkedHashSet` are both hash-based sets: they deduplicate elements and support adding, checking membership, and removing by value. The main difference is that `LinkedHashSet` also maintains insertion order so that iteration order is guaranteed.

The selection question is not just "which class is faster?" but includes:

1. Does the result need to preserve insertion order?
2. Does the program mostly perform lookups or frequently iterate over the entire set?
3. How many distinct elements are there, and is the hash table sparse?
4. Is the structural overhead memory significant compared to the element data?
5. Do you need complexity analysis or an actual measurement on a specific JVM?

Initial guidelines:

- No ordering needed and mostly membership checks: `HashSet` is usually the direct choice, avoiding unnecessary ordering links.
- Insertion order must be preserved: `LinkedHashSet` provides that exact behavior.
- Frequent iteration, especially when the hash table is sparse: consider `LinkedHashSet`'s advantage of iterating by element count.
- Need exact bytes or nanoseconds: you must measure under specific conditions; class names and Big-O notation are not enough.

These are reasoning guidelines derived from structure and contracts, not claims that one class wins every benchmark. [HashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [LinkedHashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

## 2. What Structural Difference Matters?

### 2.1. Shared Foundation: Hash Table for Membership

Both rely on hashing to narrow down the search space:

```text
query value
    → hashCode
    → candidate region in table
    → equality comparison
    → found or not found
```

`LinkedHashSet` is not a `LinkedList` where every `contains` call has to walk from start to end. The word "Linked" here refers to the additional links used for iteration order; membership lookup still relies on hashing.

Therefore, both require:

- Consistent `equals` and `hashCode`.
- Stable identifying data in elements while they are in the set.
- Well-distributed hash codes across values.
- Controllable cost for computing hash codes and equality comparisons.

Switching from `HashSet` to `LinkedHashSet` does not fix a key with a broken `hashCode`, one that always returns a constant, or one that mutates after insertion.

### 2.2. What LinkedHashSet Adds: Ordering Links

You can picture the ordering structure as a doubly-linked chain between entries:

```text
head → first entry ↔ second entry ↔ third entry ← tail
```

Those links allow iterating over stored elements in insertion order. When adding a new entry or removing an existing one, the implementation needs to update the corresponding links.

`HashSet` does not need to provide this insertion-order chain. It makes no guarantee about iteration order, even if a small example happens to print elements in the order they were added.

What `LinkedHashSet` adds has two sides:

- It consumes resources to store and maintain the order.
- It allows iteration without having to scan for elements across every empty bucket in the table.

That is why a structure with extra management metadata can still be a better fit for a specific workload.

## 3. Time Comparison by Operation

Let:

- `n`: number of stored elements.
- `C`: capacity, i.e., the number of buckets in the backing table.
- The cost of `hashCode` and `equals` is considered separately when keys are complex.

The following table describes the typical model with well-distributed hashing:

| Operation | HashSet | LinkedHashSet | Interpretation |
| --- | --- | --- | --- |
| `contains` | O(1) expected | O(1) expected | Both use hashing; no need to scan the whole set |
| `add` | O(1) expected/amortized in typical insertion sequences | Similar, with extra link maintenance on new insertions | A single resize can still do significant work |
| `remove` | O(1) expected | O(1) expected, with extra unlinking from order chain | Does not imply one class is always faster for every key |
| Full iteration | O(n + C) per the class model | O(n) per the class model | Noticeable difference when C is much larger than n |
| `size` | O(1) | O(1) | Element count is tracked directly |

Constant-time claims for basic operations depend on hash distribution assumptions. O(1) notation is not an absolute timing guarantee for every input or every single call. [HashSet: operations and iteration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [LinkedHashSet: operations and iteration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

### 3.1. Membership Lookup

With the same data and reasonable configuration, both share the same hash-based lookup model. `LinkedHashSet.contains` does not need to modify insertion order.

Do not conclude that the actual execution times of both methods must be identical just because both are O(1). They can be affected by object layout, how much data resides in memory, and the work the JVM performs.

Conversely, do not conclude that `LinkedHashSet.contains` is O(n) just because you see a linked chain in the structural description.

### 3.2. New Insertion, Duplicate Insertion, and Resizing

Inserting a new element is different from attempting to insert an element that is already present:

- A new insertion requires creating a new entry in the structure; for `LinkedHashSet`, it must also be placed into the ordering chain.
- A duplicate insertion returns `false` and does not increase the element count.
- A new insertion may trigger a hash table resize.

Therefore, a benchmark that calls `add("java")` repeatedly after the set already contains `"java"` does not represent inserting many distinct values.

The cost of resizing explains the term "amortized" when analyzing insertion sequences: some calls do more work, so you must not assume every individual insertion has the same latency. Both structures still have a backing hash table affected by capacity and load factor.

### 3.3. Element Removal

After locating an entry, `LinkedHashSet` needs to unlink it from the ordering chain. With doubly-linked pointers and a reference to the located entry, it does not need to scan the entire chain just to find the predecessor.

This extra work usually makes the constant factor different from `HashSet`. However, to know the exact difference on a specific workload, you must measure—you cannot deduce a fixed ratio such as "20% slower."

### 3.4. Iteration Must Be Considered Separately

For `HashSet`, the iteration model includes both the number of table buckets and the present elements. For `LinkedHashSet`, the iterator follows the chain of elements.

If `C` is always proportional to `n`, both `n + C` and `n` can be simplified to O(n). However, that does not erase the difference when the actual table is very sparse or when constant factors differ.

Conceptual example:

```text
n = 1_000 elements
C much larger than n

HashSet:
    iteration work involves both the table buckets and the elements

LinkedHashSet:
    iteration work follows the chain of 1_000 elements
```

This is not a calculation of exact nanoseconds or memory accesses. It points out the factors to include in your analysis and benchmark design.

## 4. Capacity and Load Factor Connect Time and Memory

`size` is the number of elements; `capacity` is the number of buckets. These two quantities are not the same.

Load factor relates to how full the table is allowed to get before resizing. The default constructors of both classes use default parameters of `16` and `0.75`, respectively.

Tuning configuration involves trade-offs:

| Choice | Time Aspect | Memory Aspect |
| --- | --- | --- |
| Initial capacity sufficient for expected elements | Can reduce the number of resizes during construction | Needs to allocate space for the corresponding table |
| Capacity too large | Does not fix poor hashing; HashSet iteration is affected by the sparse table | Can leave many empty buckets |
| Lower load factor | Can make the table sparser; not guaranteed to be faster for all workloads | Typically requires more table space |
| Higher load factor | Can increase candidate lookup work | Can reduce relative table space in some configurations |

`LinkedHashSet` does not have to scan empty buckets in the same way, but a sparse table still carries storage cost. An iteration advantage does not mean a large capacity is free in memory.

The argument in `new HashSet<>(1_000)` or `new LinkedHashSet<>(1_000)` is an initial capacity hint, not a command to pre-populate 1,000 elements or a cap limiting the set to that count.

When comparing, keep configurations equivalent. A `HashSet` with an oversized table and a `LinkedHashSet` with a right-sized table differ in more than just ordering links. [HashMap: capacity, load factor, and resizing](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

## 5. Memory Comparison: Element Data and Management Structure Are Two Different Parts

### 5.1. Neither Deep-Copies Element Objects

If you put the same key object into two sets, both sets can hold references to that same object. They do not automatically clone the key's entire data.

When asking "how much memory does a set use?", you must clarify whether you are counting:

1. The `Set` object itself.
2. The backing table and management entries.
3. The element objects referenced by the set.
4. Any other objects reachable from those elements.
5. Temporary memory allocated during construction versus live memory retained after construction.

Without separating these meanings, two numbers both labeled "memory" may be measuring two completely different things.

### 5.2. A Qualitative Model

For typical entries, you can picture it as:

```text
HashSet memory
    ≈ management object
      + reference array sized by capacity
      + entries per element count
      + element object graph included in the measurement

LinkedHashSet memory
    ≈ corresponding components
      + ordering link metadata in the management structure and each entry
```

In terms of asymptotic growth, both require memory for the number of buckets and the number of elements: O(C + n), excluding element data size. When `C` scales linearly with `n`, both are commonly described as O(n).

Being the same O(n) does not mean the same number of bytes. `LinkedHashSet` stores additional ordering metadata, so under equivalent configurations and typical entries, it generally has higher structural overhead.

However, do not use "LinkedHashSet uses more memory" to compare two completely different configurations. A `HashSet` with an enormous capacity can waste more table space than a properly sized `LinkedHashSet`. Keep comparison conditions clear.

### 5.3. Why Two Extra Links per Entry Are Often Mentioned

In the OpenJDK 17 implementation, a standard entry of the backing linked structure has extra `before` and `after` references compared to a standard hash entry. The backing map also maintains head and tail references for the chain.

That is the basis for saying there is per-element overhead. This is an implementation detail used for explanation, not an object layout guaranteed by the Java interface. [Linked entry in OpenJDK 17 source](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedHashMap.java)

Do not directly translate "two extra references" into "always exactly 8 bytes more" or "always exactly 16 bytes more" per element on every JVM. The actual byte count also depends on:

- Reference representation size on the JVM in use.
- Object headers and field layout.
- Object size alignment.
- The actual entry type used by the implementation when handling collisions.
- Management fields on the backing object.

The two-link model specifically describes standard entries. Some collision-handling entry types have different structures; do not use a simplified model to claim every internal object always differs by the exact same number of bytes.

### 5.4. A Hypothetical Calculation to Understand Scale

Suppose we only consider two extra reference fields, each taking `r` bytes, across `n` entries:

```text
modeled extra field size = n × 2 × r
```

If we **assume** `n = 100_000` and `r = 4`:

```text
100_000 × 2 × 4 = 800_000 bytes
```

This is purely a calculation of a reference-field model under the stated assumptions. It is not a heap measurement, does not include alignment, other management objects, or element data, and is not a guaranteed difference.

The takeaway is that a small per-entry cost can become noticeable when there are many entries; the exact byte count must be verified in the target runtime environment.

### 5.5. Large Element Data Can Mask Relative Differences

If each element is a very small object, set management overhead can make up a noticeable percentage. If each element holds a large object graph, the proportion of the linking overhead in the total footprint may be smaller.

That does not make the linking cost disappear. It only explains why the same absolute increase can represent a different percentage when the data type changes.

A comparison using small keys does not automatically represent an application with large keys and many associated objects.

## 6. Complete Program: Same Set Value, Different Ordering Guarantees

Save the code to **HashSetChoiceDemo.java**:

```java
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class HashSetChoiceDemo {
    public static void main(String[] args) {
        List<String> input = List.of("sql", "java", "sql", "http");
        Set<String> hashed = new HashSet<>(input);
        Set<String> linked = new LinkedHashSet<>(input);

        System.out.println("HashSet size: " + hashed.size());
        System.out.println("LinkedHashSet size: " + linked.size());
        System.out.println("same members: " + hashed.equals(linked));
        System.out.println("linked order: " + linked);
        System.out.println("hash contains java: " + hashed.contains("java"));
        System.out.println("linked contains java: " + linked.contains("java"));
        System.out.println("hash add duplicate: " + hashed.add("sql"));
        System.out.println("linked add duplicate: " + linked.add("sql"));
        System.out.println("hash remove java: " + hashed.remove("java"));
        System.out.println("linked remove java: " + linked.remove("java"));
        System.out.println("linked after removal: " + linked);

        hashed.add("java");
        linked.add("java");
        System.out.println("linked after re-add: " + linked);
        System.out.println("same members again: " + hashed.equals(linked));
        System.out.println("same set hash: "
                + (hashed.hashCode() == linked.hashCode()));
    }
}
```

Compile targeting Java 17 and run:

```shell
javac --release 17 -encoding UTF-8 HashSetChoiceDemo.java
java HashSetChoiceDemo
```

Stdout:

```text
HashSet size: 3
LinkedHashSet size: 3
same members: true
linked order: [sql, java, http]
hash contains java: true
linked contains java: true
hash add duplicate: false
linked add duplicate: false
hash remove java: true
linked remove java: true
linked after removal: [sql, http]
linked after re-add: [sql, http, java]
same members again: true
same set hash: true
```

The program only prints the contents of `LinkedHashSet` directly, because its order is guaranteed. It does not print `HashSet` and rely on an accidental order for stdout.

The results show:

- Both sets have the same size and the same members.
- Both reject adding a duplicate of an existing value.
- Both find and remove elements by value.
- `LinkedHashSet` provides observable insertion order.
- Removing and re-adding `java` places it at the end in the linked set.
- Different iteration order does not make two sets with the same members have different set values.

This program verifies behavior. It contains no timing or memory measurements, so stdout lines cannot be read as a speed comparison result.

## 7. Preparing Equivalent Data Before Measuring

A common mistake is comparing two sets with different element counts, using two key sets generated differently, or accidentally feeding more duplicates to one side.

To prepare a meaningful comparison, control for:

| Factor | How to Keep Equivalent |
| --- | --- |
| Contents | Same distinct key values |
| Key type | Same class, same `equals`/`hashCode` rules |
| Element objects | Can share input objects when comparing only the set structures |
| Configuration | Same capacity hint and load factor within each pair |
| State | Same element count before the operation |
| Workload | Same query sequence or same insertion/removal mix |
| Outcome | Verify neither side does less work due to invalid data |

Passing the same capacity hint is not an API for reading the actual bucket count. If a conclusion depends on the actual heap structure, you must inspect that structure with an appropriate tool.

### Program Preparing Two Pairs of Sets

Save the code to **SetComparisonSetupDemo.java**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Set;

public class SetComparisonSetupDemo {
    private static Set<Integer> fill(Set<Integer> target, Integer[] keys) {
        target.addAll(Arrays.asList(keys));
        return target;
    }

    private static long checksum(Set<Integer> values) {
        long result = 0;
        for (Integer value : values) {
            result += value;
        }
        return result;
    }

    public static void main(String[] args) {
        int count = 1_000;
        Integer[] keys = new Integer[count];
        for (int value = 0; value < count; value++) {
            keys[value] = Integer.valueOf(value);
        }

        Set<Integer> hashDense =
                fill(new HashSet<>(2_048, 0.75f), keys);
        Set<Integer> linkedDense =
                fill(new LinkedHashSet<>(2_048, 0.75f), keys);
        Set<Integer> hashSparse =
                fill(new HashSet<>(262_144, 0.75f), keys);
        Set<Integer> linkedSparse =
                fill(new LinkedHashSet<>(262_144, 0.75f), keys);

        System.out.println("shared input keys: " + keys.length);
        System.out.println("hash dense size: " + hashDense.size());
        System.out.println("linked dense size: " + linkedDense.size());
        System.out.println("hash sparse size: " + hashSparse.size());
        System.out.println("linked sparse size: " + linkedSparse.size());
        System.out.println("dense sets equal: " + hashDense.equals(linkedDense));
        System.out.println("sparse sets equal: " + hashSparse.equals(linkedSparse));
        System.out.println("hash dense checksum: " + checksum(hashDense));
        System.out.println("linked dense checksum: " + checksum(linkedDense));
        System.out.println("hash sparse checksum: " + checksum(hashSparse));
        System.out.println("linked sparse checksum: " + checksum(linkedSparse));
        System.out.println("all contain 999: "
                + (hashDense.contains(999) && linkedDense.contains(999)
                && hashSparse.contains(999) && linkedSparse.contains(999)));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SetComparisonSetupDemo.java
java SetComparisonSetupDemo
```

Stdout:

```text
shared input keys: 1000
hash dense size: 1000
linked dense size: 1000
hash sparse size: 1000
linked sparse size: 1000
dense sets equal: true
sparse sets equal: true
hash dense checksum: 499500
linked dense checksum: 499500
hash sparse checksum: 499500
linked sparse checksum: 499500
all contain 999: true
```

The program creates a shared array of key objects, then inserts those same objects into four sets. Both pairs use the same element count, but with two different capacity hints.

The names `Dense` and `Sparse` express the configuration intent of the example: one hint closer to the scale of the data, and one hint very large relative to 1,000 elements. They are not measurements of fill ratio or capacity properties read from an API.

The checksum verifies that all iteration loops process the same contents. The sum from `0` to `999` is `499_500`, independent of iteration order.

There are no timing or byte measurements in stdout. This program is a data preparation and verification step before measuring, not a benchmark.

Both standalone programs in this article were compiled with `--release 17` and run against the expected stdout. This option checks the language/API level and produces Java 17-compatible bytecode; it does not assert that the executing JVM itself is JDK 17.

## 8. Measuring Time: Separate Each Question

[OpenJDK JMH](https://github.com/openjdk/jmh) is the tool used to build and run benchmarks on the JVM. The tool does not replace choosing the right workload.

A measurement plan can be separated into:

| Measurement | State and Operations to Prepare | Conclusion It Can Support |
| --- | --- | --- |
| Present lookup | Pre-built set, query keys that exist | Successful lookup cost |
| Absent lookup | Pre-built set, query keys that do not exist | Failed lookup cost |
| New insertion | Ensure keys are absent and control resizing | Set modification cost under new-insertion workload |
| Duplicate insertion | Keys already present | Cost of attempting duplicate insertion |
| Present removal | Re-prepare elements for subsequent iterations per design | Successful removal cost |
| Iteration | Same pre-built set, process all elements | Impact of element count and sparseness |
| Construction | Create set and populate with same data | Overall initialization cost, including allocation |

Biases to avoid:

- Placing `println` inside the section meant to measure only set operations.
- Measuring `add` on the same key repeatedly and calling it new insertion.
- Removing once and then measuring absent removals as if every iteration succeeded.
- Generating data or rebuilding the set inside a measurement described as `contains`-only.
- Discarding results without properly consuming them in the benchmark.
- Measuring only one size or one key type and generalizing to all applications.

On the JVM, startup, JIT compilation, allocation, and garbage collection can make ad-hoc measurements hard to interpret. Use appropriate warmup, measurement iterations, and independent forks as guided by the tool; still verify that the data is representative.

If the goal is to evaluate per-request latency that may trigger a resize, do not look only at an average that blends in normal insertions. If the goal is repeated iteration over a pre-built set, separate construction time from the iteration phase.

A report should state the JDK/JVM, run configuration, key type, set size, capacity configuration, query distribution, and units of measurement. Do not write "LinkedHashSet is always faster" just because it won one iteration benchmark on a sparse table.

## 9. Measuring Memory: Inspect the Object Graph, Not Just the Set Shell

### 9.1. Shallow Size and Footprint Are Different

An object's shallow size describes only that object itself, without automatically summing all the objects it references.

Measuring only the `HashSet` and `LinkedHashSet` shells may fail to show most of the difference, because the backing table and entries live in other objects in the graph.

To understand the structure's memory, inspect the objects reachable from the set and clearly state whether element data is included.

### 9.2. Use Tools to Observe Instead of Pulling a Fixed Number from Memory

[OpenJDK JOL](https://github.com/openjdk/jol) helps inspect object layout and footprint on the JVM. Details such as reference size and object alignment should be recorded alongside results.

With the data prepared in the second program, a workflow could be:

1. Set up JOL in a separate measurement program following the tool's instructions.
2. Record the JVM configuration and the object types being measured.
3. Inspect the graphs starting from `hashDense` and `linkedDense` using graph analysis capabilities such as `GraphLayout.parseInstance`.
4. Read both the total size and the breakdown of object classes in each graph, rather than only a single total number.
5. Repeat with the large-capacity-hint pair to see how the table portion affects the footprint.
6. Be explicit about how shared keys between sets are accounted for.

`GraphLayout.totalSize()` reports the total footprint of the graph analyzed by the tool. This article does not provide hypothetical JOL output as a measurement: you must run the tool in your actual environment to obtain corresponding results. [GraphLayout in JOL](https://github.com/openjdk/jol/blob/master/jol-core/src/main/java/org/openjdk/jol/info/GraphLayout.java)

### 9.3. Do Not Add Two Separate Footprints and Treat Them as Exclusive Total Memory

In the example, multiple sets share the same key objects. If you analyze each set separately, each set's graph may include those keys.

Simply adding two separate totals can double-count shared objects. If you measure both as roots in a single graph, shared objects are counted differently. State clearly which question the measurement is answering.

The footprint of reachable objects also does not automatically mean all those bytes will be freed when a single set is discarded, because the keys or other objects may still be referenced elsewhere.

### 9.4. Live Memory and Allocation Rate Are Two Different Metrics

A post-construction measurement can show the live objects in the observed structure. It does not describe all temporary allocations during resizing or query key creation.

If you care about GC pressure under continuous add/remove workloads, evaluate allocation rate and object lifetimes accordingly. If you care about the steady-state footprint of a rarely changing lookup table, the post-construction footprint is closer to your question.

Do not subtract free memory before and after a small run and treat that as an exact per-entry size. Other JVM activity and GC state make that interpretation unfounded.

## 10. Concrete Selection Scenarios

### 10.1. Primarily Checking Seen Keys, No Ordering Needed

If a program keeps a set of keys, calls `contains` heavily, rarely iterates over the whole set, and has no ordered output requirement, `HashSet` is usually the right starting point.

It avoids the cost of maintaining insertion order that the problem does not use. You still need to check scale, capacity configuration, and key quality.

### 10.2. Deduplicating and Outputting in First-Seen Order

If the input has an order and the output must preserve first-seen order, `LinkedHashSet` provides the exact behavior in a single structure.

Choosing `HashSet` and trying to infer insertion order from its output does not satisfy the contract. Saving some memory does not compensate for returning incorrect results.

### 10.3. Heavily Iterated Sets with a Sparse Table

`LinkedHashSet` has an iteration model proportional to element count, so it is worth evaluating in this scenario. However, compare both the memory of the links and the table, and check whether `HashSet` can be reconfigured more appropriately.

You cannot guarantee concrete speed on every dataset from the O(n) model alone. Memory layout and per-element work still affect real-world results.

### 10.4. Many Elements Where Memory Is the Primary Constraint

When ordering is not needed, the extra linking metadata can be a cost worth avoiding. Measure the structure with the real key type and the same capacity conditions.

If the keys themselves occupy most of the heap, optimizing key representation or data lifecycle may have a larger impact than switching between the two set types. This must be based on application profiling, not a blanket assumption for every system.

## 11. Common Conditions That Must Not Be Ignored

Neither structure is thread-safe for concurrent modification by multiple threads. Comparing time in a multithreaded problem requires incorporating proper synchronization or an appropriate concurrent structure into the design; do not compare a properly guarded structure against a misused one and call that an inherent difference between the two classes.

Both require stable element contracts. Switching set classes does not solve mutating fields used in `equals`/`hashCode` while an element is stored in the set.

Both can suffer from poor hash distribution. Ordering links do not eliminate collisions in hash lookups.

These points belong to correctness and analysis preconditions. A fast measurement of an incorrect program is not a valid basis for choosing a data structure.

## 12. Common Misconceptions

| Misconception | Why It Is Incorrect | Correction |
| --- | --- | --- |
| Same O(1) means equally fast | Big-O does not determine all constant factors or JVM overhead | Benchmark the specific operation when numbers are needed |
| LinkedHashSet contains a linked list so `contains` is O(n) | Links serve ordering; membership lookup still uses hashing | Separate the lookup path from the iteration path |
| HashSet always iterates faster because it has fewer links | Iteration also depends on capacity | Consider both n and C, especially when the table is sparse |
| LinkedHashSet is always faster because iteration is O(n) | The application may mostly add/remove or look up | Compare against the actual workload |
| LinkedHashSet always adds a fixed number of bytes on every JVM | Object layout, references, and entry types vary | Record the environment and measure the footprint |
| Measuring just the Set object is enough | The table and entries live in the graph behind it | Define the memory measurement scope |
| Two sets with the same size must use the same backing memory | Capacity and entry types can differ | Keep configuration consistent and inspect the structure |
| Adding the footprints of two sets sharing keys equals actual total heap | Shared objects may be counted multiple times | Define roots and counting rules |
| A loop calling `add` with the same key measures new insertion cost | Most iterations are duplicate insertions | Prepare state matching the question |
| Switching to LinkedHashSet fixes a poor `hashCode` | Both still use hashing | Fix key contracts and hash distribution |

## 13. Self-Practice and Verification

### Exercise 1: Reading the Two Iteration Formulas Correctly

Suppose two sets both have `n = 2_000`. One table has capacity on the same scale as the element count; the other has a much larger capacity.

1. Why is knowing `n` alone not enough to describe `HashSet` iteration work?
2. According to the document's model, how does capacity affect `LinkedHashSet`'s iteration path?
3. Can you conclude from this how many nanoseconds an iteration takes?

Check: `HashSet` has an O(n + C) model; `LinkedHashSet` iterates along the element chain with an O(n) model; the formulas do not provide concrete timing numbers.

### Exercise 2: Checking a Memory Calculation

Someone says: "There are 100,000 entries. Assuming 4 bytes per reference, two extra references equal 800,000 bytes, so the total heap difference is guaranteed to be exactly 800,000 bytes."

The field calculation under the stated assumptions is correct. The conclusion about the exact total heap difference is unfounded because it ignores alignment, management structures, entry types, JVM configuration, and whether element data is included.

### Exercise 3: Spotting a Non-Equivalent Comparison

A benchmark creates a `HashSet` with a very large capacity hint and a `LinkedHashSet` with the default configuration, then inserts the same 1,000 values and measures iteration.

The results may be useful for observing those two specific configurations. However, it does not separate the effect of "set type" from the effect of "table configuration." For a controlled comparison, add pairs with equivalent configurations and clearly state the goal.

### Exercise 4: Choosing by Requirement

- A key set that only needs membership checks, no ordering: start by considering `HashSet`.
- A deduplicated result that must follow first-seen order: `LinkedHashSet` satisfies the ordering requirement.
- A heavily iterated set with signs of an overly sparse table: check capacity/configuration and evaluate both under the iteration workload.
- A decision constrained by heap limits: measure with the same data, same configuration, and clearly state how shared objects are counted.

Every choice should be justified by requirements and evidence, not by a slogan like "this structure is always better."

## 14. Reference Documentation

- [HashSet Java 17 — performance conditions and iteration cost](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
- [LinkedHashSet Java 17 — ordering links, operations, and iteration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)
- [HashMap Java 17 — capacity and load factor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)
- [OpenJDK 17 LinkedHashMap — linked entry details used to explain overhead](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedHashMap.java)
- [OpenJDK JMH — designing and running benchmarks on the JVM](https://github.com/openjdk/jmh)
- [OpenJDK JOL — object layout and footprint](https://github.com/openjdk/jol)
