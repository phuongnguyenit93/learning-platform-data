# Characteristics: `SIZED`, `SUBSIZED`, `IMMUTABLE`, and `CONCURRENT`

> **Chapter:** Spliterators and Custom Sources  
> **Module:** `JAVA_STREAM_API` — learn declarative data processing with the Java Stream API through lazy pipelines, `filter`, `map`, `reduce`, `collect`, grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers; while evaluating limits around state, resources, and performance.

When programming with the Java Stream API, we usually let `List`, `Set`, or the standard library create a `Spliterator` automatically. However, if you want to feed a custom data source into a Stream—a numeric range, record reader, tree structure, or concurrently modifiable structure—you need to describe **what characteristics the source has** so the Stream library traverses, partitions work, and optimizes properly.

Four important characteristics are `SIZED`, `SUBSIZED`, `IMMUTABLE`, and `CONCURRENT`. They are not merely performance labels: declaring them incorrectly can cause operations to produce inaccurate results or encounter undefined behavior.

Lesson objectives:

1. Accurately explain the meaning of each characteristic and how to inspect them.
2. Distinguish **exact known size**, **splittability into exact-sized parts**, **stable sources**, and **sources permitting concurrent modification**.
3. Write a custom `Spliterator.OfInt` for a fixed integer range, declare accurate characteristics, and use `StreamSupport`.
4. Understand why `CONCURRENT` does not mean a single `Spliterator` object can be called concurrently by multiple threads; recognize risks with sources modified during traversal.

## 1. What Role Does `Spliterator` Play in a Stream?

`Spliterator<T>` is an interface used to **traverse** and optionally **split** a source of elements. Its foundational methods are:

| Method | Role |
| --- | --- |
| `boolean tryAdvance(Consumer<? super T> action)` | Passes at most one element to action; returns `false` when no elements remain. |
| `void forEachRemaining(Consumer<? super T> action)` | Traverses remaining elements; has a default implementation based on `tryAdvance`. |
| `Spliterator<T> trySplit()` | Attempts to split off a portion of work for independent traversal; may return `null`. |
| `long estimateSize()` | Estimates the number of remaining elements; sometimes the exact size. |
| `int characteristics()` | Returns flags describing properties of the source and traversal. |
| `boolean hasCharacteristics(int flags)` | Checks whether **all** requested flags are present. |
| `long getExactSizeIfKnown()` | If `SIZED` is present, returns `estimateSize()`; otherwise returns `-1`. |

Data flow can be visualized as follows:

```text
Data source
     │
     ▼
 Spliterator<T> ──► trySplit() ──► child Spliterators
     │                                  │
     └──────────── tryAdvance() ◄───────┘
                        │
                        ▼
          Stream pipeline (filter/map/...)
                        │
                        ▼
            terminal operation
```

The `Spliterator` flags live in `java.util.Spliterator`. They are bit flags that can be combined with bitwise OR `|` and checked via `hasCharacteristics(...)`. They are **different from** `Collector.Characteristics`, which describe a collector rather than a source.

## 2. Overview of the Four Characteristics

| Characteristic | Core Guarantee | Must NOT Be Misunderstood As |
| --- | --- | --- |
| `SIZED` | `estimateSize()` represents the exact remaining element count per contract at that moment, absent unexpected structural interference. | Supporting random access per element or always splitting fast. |
| `SUBSIZED` | The current Spliterator **and all Spliterators produced by `trySplit()`** also have `SIZED` and `SUBSIZED`. | Splits always being balanced or guaranteed to split. |
| `IMMUTABLE` | The element source cannot be structurally modified (added, replaced, removed) during traversal. | Every element object being deeply immutable; or the traversal cursor never changing. |
| `CONCURRENT` | The element source can be modified concurrently by threads without external synchronization, per the source's contract. | A **single** Spliterator instance being safe for multiple threads calling `tryAdvance` simultaneously; or yielding a fixed snapshot. |

Characteristics represent **actual guarantees**, not desired goals. If you have not proven a flag holds for all supported cases, never declare it just chasing speedups.

## 3. `SIZED`: Exact Size

With `SIZED`, `estimateSize()` must return the exact remaining element count per contract when the source does not undergo structural interference violating traversal policy. A fixed numeric range `[1, 11)` has exactly 10 elements; after consuming 3 elements, 7 remain.

```java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> sp = List.of("A", "B", "C").spliterator();

System.out.println(sp.hasCharacteristics(Spliterator.SIZED)); // true
System.out.println(sp.getExactSizeIfKnown());                 // 3
```

`getExactSizeIfKnown()` returns `-1` when the Spliterator does not declare `SIZED`. That **does not mean the source is empty**: it merely means no exact size guarantee is provided via this API.

### Distinguishing `estimateSize()` and `getExactSizeIfKnown()`

- `estimateSize()` is always available on `Spliterator`. For unknown-size or infinite sources, the value may be `Long.MAX_VALUE`.
- `getExactSizeIfKnown()` offers a safe check when you need a size **guaranteed by the `SIZED` characteristic**.
- The remaining size may decrease as `tryAdvance` processes elements; do not treat it as a constant initial count across the entire traversal lifecycle.
- `SIZED` does not mean the element count after `filter` remains known upfront: a filter predicate can drop an unpredictable number of elements.

Example of a source providing only an `Iterator`:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;

Iterator<String> iterator = List.of("A", "B", "C").iterator();
Spliterator<String> unknown = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED | Spliterator.NONNULL
);

System.out.println(unknown.hasCharacteristics(Spliterator.SIZED)); // false
System.out.println(unknown.getExactSizeIfKnown());                 // -1
```

In this example, the underlying list actually contains 3 elements, yet the `Iterator` adapter is instructed to treat it as **unknown size**. Never attach `SIZED` without an exact counting mechanism, especially for streaming data sources.

### Impact on Stream optimizations

The Stream library can use size metadata to allocate buffers or optimize operations. For instance, certain pipelines with a known size can compute `count()` **without executing every `peek` action**.

```java
long count = List.of(10, 20, 30).stream()
        .peek(System.out::println)
        .count();

System.out.println("count = " + count); // 3
// Lines from peek may not be printed.
```

Therefore, never place mandatory side-effecting business logic in `peek` expecting every element to be visited. `SIZED` only supplies information for optimization, not a promise of a single execution strategy.

## 4. `SUBSIZED`: Every Split Branch Knows Its Exact Size

`SUBSIZED` is a stronger guarantee than `SIZED` regarding **preservation across splits**: all Spliterators created from `trySplit()`, including subsequent splits, also have `SIZED` and `SUBSIZED`.

```text
Root Spliterator [0..15]  SIZED + SUBSIZED, 16 elements
          │
       trySplit()
       ┌──┴───┐
       ▼      ▼
     [0..7] [8..15]       8 + 8 = 16
       │      │
    split    split
     │        │
   [0..3]   [8..11]       each branch knows its exact element count
```

A `SIZED` Spliterator **does not necessarily have `SUBSIZED`**. Some source structures know the total size upfront without guaranteeing that every sub-part after splitting still knows its exact remaining count. Only attach `SUBSIZED` when the `trySplit` algorithm and child branches guarantee it.

### Two practical conditions to verify

1. Whenever `trySplit()` returns a non-`null` branch, the two branches represent **non-overlapping elements with none skipped**, per the source contract.
2. Both the returned branch and remaining branch report exact sizes, and subsequent splits continue to preserve `SIZED | SUBSIZED`.

`SUBSIZED` does **not** guarantee always being able to split: `trySplit()` may return `null` if the remaining work is too small or the source does not support useful splitting. Nor does it guarantee splitting into strictly equal halves—only that resulting Spliterators all report exact sizes.

## 5. `IMMUTABLE`: Source Structure Cannot Change During Traversal

`IMMUTABLE` indicates that the element source **cannot be structurally modified** (elements added, replaced, or removed) while the Spliterator is traversing it. This frees traversal from needing to handle unexpected structural changes.

Distinguish carefully:

- **Source immutable during traversal:** the set of elements and their positions/relationships are not added to, replaced, or deleted.
- **Immutable element objects:** fields of each object cannot be changed. `IMMUTABLE` on a Spliterator **does not automatically guarantee** this second property.
- **Immutable traversal state:** the Spliterator's cursor does not change. That is **false**: `tryAdvance()` still must advance the traversal position.

For instance, a numeric range defined completely by two fixed bounds has a logically immutable source, even though the `next` cursor inside the Spliterator increments on each read.

### Do not confuse `IMMUTABLE` with `Collections.unmodifiableList`

An *unmodifiable view* only rejects modifications **through the view**, whereas the backing collection can still be modified via another reference. You cannot arbitrarily assert a source is structurally unmodifiable simply because it is wrapped with `Collections.unmodifiableList(original)`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> original = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(original);

original.add("C"); // view also observes this change.
```

Hence, examine **the actual contract of the source** rather than guessing flags from variable types. `IMMUTABLE` also does not mean reads of element objects themselves are synchronized with state mutations on other threads.

## 6. `CONCURRENT`: Source Permits Concurrent Modification

`CONCURRENT` describes **the element source's ability** to tolerate additions, replacements, or removals from other threads during traversal under the source's own mechanism, without requiring the caller to hold external locks.

A classic example is the views from `ConcurrentHashMap`:

```java
import java.util.Set;
import java.util.Spliterator;
import java.util.concurrent.ConcurrentHashMap;

Set<String> keys = ConcurrentHashMap.<String>newKeySet();
keys.add("A");
keys.add("B");
keys.add("C");

Spliterator<String> sp = keys.spliterator();
System.out.println(sp.hasCharacteristics(Spliterator.CONCURRENT)); // true
System.out.println(sp.hasCharacteristics(Spliterator.SIZED));      // false
```

Spliterators of concurrent sources typically provide **weakly consistent** traversal: they do not require an instantaneous snapshot of all data. When elements are added or removed during traversal, those changes **may or may not be observed** depending on timing and the source structure's contract.

```java
// Continuation after the snippet above:
keys.add("D");
sp.forEachRemaining(System.out::println);

// Do not write tests that depend strictly on whether "D"
// is observed by sp while the source is being modified concurrently.
```

### The `CONCURRENT` flag does NOT mean the `Spliterator` is thread-safe

It is essential to distinguish:

| Subject | Scope of Guarantee |
| --- | --- |
| A **source** with `CONCURRENT` | Allows concurrent structural modifications per the source's contract. |
| A specific **`Spliterator` object** | Has no automatic thread-safety guarantee when multiple threads concurrently call `tryAdvance()` or `trySplit()` on **the same instance**. |
| **Already-split Spliterators** | The Stream can distribute independent branches to separate tasks, following the splitting contract. |
| **Pipeline lambdas/collectors** | Must still satisfy non-interference, independence, or appropriate concurrency safety rules. |

This characteristic also differs from `Collector.Characteristics.CONCURRENT`: one flag describes the **source**, while the other describes how the **collector** accumulates results.

### Why do concurrent sources usually omit `SIZED`?

The size of the element collection can change between two reads as other threads insert or delete elements. Even though `ConcurrentHashMap.size()` returns a number, it does not mean the `Spliterator` can guarantee an exact remaining count throughout traversal under concurrent updates.

Consequently, a top-level Spliterator for a source permitting concurrent updates usually **omits** `SIZED`/`SUBSIZED`. Do not add `SIZED` just because a `size()` method exists if the actual traversed count can fluctuate.

## 7. Complete Java 17+ Example: Building a `SIZED | SUBSIZED | IMMUTABLE` Range

To see the relationship between characteristics and methods clearly, let's build a Spliterator over a non-negative integer range **`[fromInclusive, toExclusive)`** with two fixed bounds.

Save the code below into `SpliteratorCharacteristicsDemo.java`:

```java
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class SpliteratorCharacteristicsDemo {

    static final class FixedRangeSpliterator implements Spliterator.OfInt {
        private int next;
        private final int fence;

        FixedRangeSpliterator(int fromInclusive, int toExclusive) {
            if (fromInclusive < 0 || toExclusive < fromInclusive) {
                throw new IllegalArgumentException("Invalid range");
            }
            this.next = fromInclusive;
            this.fence = toExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action, "action");
            if (next >= fence) {
                return false;
            }
            action.accept(next++);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            int lo = next;
            int remaining = fence - lo;
            if (remaining < 2) {
                return null;
            }

            int mid = lo + remaining / 2;
            next = mid;
            // Returned branch is prefix [lo, mid);
            // current object retains suffix [mid, fence).
            return new FixedRangeSpliterator(lo, mid);
        }

        @Override
        public long estimateSize() {
            return (long) fence - next;
        }

        @Override
        public int characteristics() {
            return Spliterator.ORDERED
                    | Spliterator.SIZED
                    | Spliterator.SUBSIZED
                    | Spliterator.IMMUTABLE
                    | Spliterator.NONNULL
                    | Spliterator.DISTINCT;
        }
    }

    public static void main(String[] args) {
        FixedRangeSpliterator source = new FixedRangeSpliterator(1, 11);

        System.out.println("SIZED + SUBSIZED: "
                + source.hasCharacteristics(
                        Spliterator.SIZED | Spliterator.SUBSIZED));
        System.out.println("IMMUTABLE: "
                + source.hasCharacteristics(Spliterator.IMMUTABLE));
        System.out.println("Initial: "
                + source.getExactSizeIfKnown());

        Spliterator.OfInt prefix = source.trySplit();
        System.out.println("Left branch: "
                + prefix.getExactSizeIfKnown());
        System.out.println("Right branch: "
                + source.getExactSizeIfKnown());

        // Create a NEW source so we do not reuse the already-split Spliterator.
        int sum = StreamSupport.intStream(
                new FixedRangeSpliterator(1, 11), true
        ).sum();
        System.out.println("Sum 1..10: " + sum);
    }
}
```

Output:

```text
SIZED + SUBSIZED: true
IMMUTABLE: true
Initial: 10
Left branch: 5
Right branch: 5
Sum 1..10: 55
```

### Analyzing each guarantee

1. **`SIZED`:** the remaining element count is computed accurately as `fence - next`. Each time `tryAdvance` consumes a value, `next` increments accordingly.
2. **`SUBSIZED`:** `trySplit` creates two disjoint intervals. Both use the same class, so both retain `SIZED | SUBSIZED`; subsequent splits maintain that rule.
3. **`IMMUTABLE`:** the logical source is a fixed set of integers in the range; there is no API to mutate the list of values comprising the source during traversal. `next` changing is merely traversal progress, not source mutation.
4. **`ORDERED`:** the numbers have a natural order within the range, and the split-off branch is a **prefix** of the remaining portion.
5. **`NONNULL` and `DISTINCT`:** every element is a primitive int, never null, and each value in the range appears exactly once.
6. **No `CONCURRENT`:** the example does not provide a source allowing concurrent structural modification; nor does it permit multiple threads to share and call `tryAdvance` concurrently on one instance.

`StreamSupport.intStream(spliterator, parallel)` uses `Spliterator.OfInt` as the source for an `IntStream`. Setting `parallel = true` enables parallel execution; it **does not guarantee** faster execution or splitting into multiple tasks in every situation.

For ordinary integer range needs, using built-in `IntStream.range(1, 11)` is simpler; writing `FixedRangeSpliterator` here serves to clarify the contract when building custom sources.

## 8. Comparing Two Usage Scenarios

| Scenario | `SIZED` | `SUBSIZED` | `IMMUTABLE` | `CONCURRENT` |
| --- | --- | --- | --- | --- |
| Fixed integer range in `FixedRangeSpliterator` | Yes | Yes | Yes | No |
| `Iterator`-based source wrapped by `spliteratorUnknownSize` | Not guaranteed | Not guaranteed on initial Spliterator | Not implied | Not implied |
| `ConcurrentHashMap.newKeySet().spliterator()` | No | No | No | Yes |
| A custom user-written source | Only if proven | Only if proven across all branches | Only if source cannot be structurally modified | Only if source supports concurrent structural modification per contract |

Never assume from `List`, `Set`, or a generic class name that every Spliterator shares the same flag set; inspect **the implementation and how the source is provided**. You can inspect actual flags with `characteristics()` or `hasCharacteristics(...)`, but understanding the source contract is essential for writing custom Spliterators.

## 9. Late-Binding, Structural Interference, and Consistency

A Spliterator may be **late-binding**: it binds to the source's contents at a late point, typically near the first traversal or split, rather than locking in the element set the moment the Spliterator is obtained. This can narrow the window exposed to structural changes before processing begins.

However, late-binding **does not automatically imply `CONCURRENT` or `IMMUTABLE`**. When the source is modified after binding time, behavior depends on the source's specific policy: it may detect the change and throw `ConcurrentModificationException`, traverse weakly consistently, or follow another policy.

Three policies to distinguish:

- **Fail-fast, best-effort:** attempts to detect unauthorized structural interference and throw an error, though exceptions should never be relied upon for data synchronization.
- **Snapshot:** traverses a pre-captured set of elements; source modifications after snapshot time do not appear in the traversed set. Creating a snapshot may incur memory or copying overhead.
- **Weakly consistent:** allows traversal to continue while the source changes concurrently, without guaranteeing visibility of every update as of a single point in time.

`Spliterator.CONCURRENT` indicates the **source can be safely modified during traversal**, not a claim that it simultaneously provides a snapshot. Concurrent sources typically carry a weakly consistent policy, though the exact policy must come from that source structure's documentation.

### Creating a Stream from a custom source

Two common forms:

```java
// Create a Stream from an existing Spliterator:
StreamSupport.stream(spliterator, parallel)

// Create a Stream from a supplier providing a Spliterator when the terminal operation starts:
StreamSupport.stream(supplier, characteristics, parallel)
```

These two lines are **API signature illustrations**, not a standalone program. The overload accepting `Supplier<? extends Spliterator<T>>` helps minimize the gap between obtaining the Spliterator and starting source traversal. When using this overload, **the passed `characteristics` flags must match the flags of the Spliterator produced by the supplier**, otherwise behavior is not guaranteed under the API contract.

## 10. Common Mistakes

| Mistake | Risk | How to Fix |
| --- | --- | --- |
| Declaring `SIZED` because initial count is known, even though source can add/remove items during traversal | `estimateSize` ceases to be accurate; Stream may optimize on wrong metadata | Declare only when guaranteed exact per contract; otherwise omit `SIZED`. |
| Declaring `SUBSIZED` when `trySplit` creates unknown-size branches | Violates child branch guarantee | Verify both returned and remaining branches, including across multi-level splits. |
| Using `IMMUTABLE` for an unmodifiable view whose backing source still changes | Backing source can be mutated behind the view | Distinguish views from snapshots/truly stable sources. |
| Using `CONCURRENT` because you want to run `parallelStream()` | Confusing concurrent source mutation with parallel processing support | Declare only if the source supports concurrent structural updates per contract. |
| Calling one Spliterator instance from multiple threads because `CONCURRENT` is set | Race condition on traversal cursor or Spliterator state | Split via `trySplit` and use each branch per valid execution rules. |
| Treating `getExactSizeIfKnown() == -1` as an empty source | Ignoring existing data | `-1` means no exact size is declared. |
| `trySplit` creating overlapping ranges | Duplicate elements; wrong `sum`/`collect` results | Ensure disjoint splits with no omissions; preserve encounter order when `ORDERED`. |
| Assuming every `CONCURRENT` source gives a point-in-time snapshot | False expectations about observed elements | Read the exact weak-consistency/snapshot policy of each source. |
| Using `peek` for required logging then calling `count` on a known-size pipeline | `peek` may be skipped in optimization | Never rely on side effects of intermediate steps. |
| Declaring extra flags solely to optimize without tests/contracts | Can lead to undefined behavior | Declare conservatively, test sequentially and in parallel with representative data. |

## 11. Self-Check Questions

**Question 1.** Does a `SIZED` Spliterator necessarily have `SUBSIZED`?

**Answer:** No. `SIZED` only guarantees the size of the current Spliterator; `SUBSIZED` additionally guarantees all branches created by splitting also have `SIZED` and `SUBSIZED`.

**Question 2.** A source has 5 elements, yet `getExactSizeIfKnown()` returns `-1`. Is the source empty?

**Answer:** No. Returning `-1` means the Spliterator does not declare `SIZED`; `estimateSize()` may simply be an estimate.

**Question 3.** Does an `IMMUTABLE` `Spliterator` guarantee that every element object is an immutable object?

**Answer:** No. The flag states that the element source cannot be structurally modified during traversal, not that each object's internal state is immutable.

**Question 4.** Why can a `ConcurrentHashMap` source declare `CONCURRENT` without declaring `SIZED`?

**Answer:** The source supports concurrent updates, yet the element count can change during traversal, making an exact remaining count hard to guarantee.

**Question 5.** On range `[0, 8)`, one `trySplit` divides it into `[0, 4)` and `[4, 8)`. How many remaining elements does each branch report?

**Answer:** Each branch has 4 elements; total is 8. If subsequent splits continue creating disjoint ranges with exact sizes, the implementation can preserve `SIZED | SUBSIZED`.

**Question 6.** Given `CONCURRENT`, can two threads simultaneously call `sp.tryAdvance(...)` on the same `sp` object?

**Answer:** You must not deduce that. `CONCURRENT` applies to **the source**, not by default to the traversal state of `sp` itself. Respect the implementation's thread-safety contract and favor independent `trySplit` branches when processing in parallel.

## Remember

- `SIZED` asserts exact remaining size per contract; `getExactSizeIfKnown()` returns `-1` if `SIZED` is absent.
- `SUBSIZED` extends the promise: **every branch** generated by splitting also has an exact size and carries `SIZED | SUBSIZED`.
- `IMMUTABLE` means the source cannot change structurally during traversal; it **does not mean** every element object or traversal cursor is immutable.
- `CONCURRENT` refers to concurrent modification of **the source**, and **does not** guarantee a single `Spliterator` object can be called concurrently by multiple threads or yields a consistent snapshot.
- For custom sources, declare characteristics conservatively, design `trySplit` without duplicates or omissions, define clear policies for mutable sources, and optimize only after upholding the contract.
