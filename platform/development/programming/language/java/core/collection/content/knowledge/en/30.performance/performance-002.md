# Amortized Cost, Average Case, and Worst Case

## 1. Why Can the Same Operation Be Described with Multiple Cost Levels?

When reading that `ArrayList.add(element)` has amortized constant cost, we might ask: if the list is full, Java has to allocate a larger array and copy the elements; so is that operation really `O(1)`?

The answer depends on **what is being evaluated**:

- The most expensive single call when the collection currently has `n` elements: **worst-case** analysis.
- A single call averaged over a stated input distribution: **average-case** analysis.
- An entire sequence of operations, then distributing the total cost across the operations in the sequence: **amortized** analysis.

These three perspectives answer different questions. An operation can simultaneously have an amortized cost of `O(1)` and a worst-case cost of `O(n)`. There is no contradiction: a few expensive calls are offset by many cheap calls in a sequence whose total cost still grows linearly.

The goal of this article is to accurately read the performance statements of Java Collections, state the assumptions behind them, and avoid extrapolating a single Big-O number into a latency promise for every call.

## 2. Defining the Cost Model Before Talking About Big-O

### 2.1. What Is `n`, and What Are We Counting?

In this article:

- `n` is typically the number of elements currently in the collection before an operation.
- `m` is the number of operations in a sequence.
- When key length needs to be analyzed, an additional `L` is used instead of hiding all costs inside `n`.
- A unit of cost may be an element comparison, an element write, or a reference copy. The model being used must be stated clearly.

For example, copying `n` references from an old array to a new array is work linear in `n`. It does not deep-copy every object pointed to by those references. Having an object with many fields does not mean that each `ArrayList` capacity expansion must clone all of those objects.

Analysis typically assumes that accessing an array slot and manipulating a reference have constant cost. For `HashMap`, we must also consider assumptions about `hashCode()` and `equals()`. For `TreeMap`, the cost of `Comparator.compare()` or `compareTo()` must also be counted if comparisons are not constant-time.

### 2.2. Big-O Is Not a Synonym for the Worst Case

`O(f(n))` is an upper bound on the growth rate of a cost quantity. That quantity can be a worst-case cost, an expected cost, or an amortized cost. The `O` notation by itself does not indicate which one is being considered.

`Θ(f(n))` expresses a tight bound on the order of growth, while `Ω(f(n))` expresses a lower bound. Consequently, a constant cost also has an upper bound of `O(n)`, though describing it as `Θ(1)` provides tighter information.

In everyday discussions, people often say for short that "this operation is `O(1)`". When that affects design, ask further: for what kind of data, for a single call or an entire sequence, and under what assumptions about keys or operation positions?

## 3. Worst Case: The Most Expensive Call at a Given Size

Given an operation and the set of valid states/inputs at size `n`, the worst-case cost is the maximum cost within that set.

It can be written as:

```text
W(n) = max cost of an operation over inputs/states of size n
```

For example, linear search in a list of `n` elements:

- If the target element is at the beginning: only one comparison may be needed.
- If it is at the end: `n` comparisons are needed.
- If it does not exist: all `n` elements must be checked.

The worst-case cost of this search is `Θ(n)`. There is no need to know what users "usually search for" to establish that bound.

With a dynamic array that is full, adding an element may require copying `n` old elements and then writing the new element. In the element-by-element copying model, that individual addition has a cost of `Θ(n)`.

**Value of worst-case analysis:** it helps identify calls that can be expensive and verify the stability of the algorithmic step count. However, a Big-O bound on step count is not a guarantee of milliseconds on the JVM. Memory allocation, garbage collection, JIT compilation, thread scheduling, and OS state still affect actual execution time.

It is also important to distinguish between:

- The worst case of **a single operation** when there are currently `n` elements.
- The worst case of **an entire sequence** of `m` valid operations.

It is not always possible to construct a sequence in which every operation hits the maximum cost of a single call. This constraint is an essential foundation of amortized analysis.

## 4. Average Case: Requires an Input Distribution

### 4.1. Average Over What?

Average-case analysis computes the expected cost when the input or state is drawn from a defined probability distribution.

```text
A(n) = sum of [probability of input x × cost of processing x]
       over inputs of size n
```

We cannot simply say "normal data" and implicitly treat that as a probability model. The conclusion depends on how frequently different cases occur.

Consider linear search in a list of `n` distinct values, under two assumptions:

1. The search definitely looks for a value currently present in the list.
2. Each position has an equal probability of being searched: `1/n`.

The expected number of comparisons is:

```text
A(n) = (1 + 2 + ... + n) / n
     = [n(n + 1) / 2] / n
     = (n + 1) / 2
     = Θ(n)
```

Half the number of elements is still linear. "Searching half the list on average" does not turn the algorithm into `O(1)`.

### 4.2. Changing the Distribution Can Change the Result

If most queries target the first few elements of the list, the expected cost can be smaller. If queries frequently fail to find a match, each such query must still scan the entire list.

Suppose the probability of a successful query is `p`; when successful, the target position is uniformly distributed. When unsuccessful, all `n` elements must be checked. We have:

```text
E[number of comparisons] = p × (n + 1) / 2 + (1 - p) × n
```

Under this model, the cost remains `Θ(n)` as `n` grows. The formula clearly shows the impact of unsuccessful queries rather than silently omitting them from the calculation.

We should also distinguish between:

- **Theoretical average:** the expected value under a probability model.
- **Measured average:** the mean of timing samples on the machine and dataset that were executed.

A measured average is evidence about that sample set. It does not by itself prove that a probability model is correct, does not prove an algorithmic bound, and does not provide a bound for the slowest call.

## 5. Amortization: Evaluating the Whole Sequence Without Randomness Assumptions

### 5.1. Total Cost Is the Starting Point

Suppose a sequence of `m` operations has actual costs `c1, c2, ..., cm`, respectively.

```text
T(m) = c1 + c2 + ... + cm
```

If we can prove that every sequence within the scope under consideration satisfies `T(m) = O(m)`, then the amortized cost per operation is `O(1)`.

This is a distribution of costs within a proof. Not every operation actually takes the same number of steps. There is no need to assume that inputs are random or lucky, or that expensive calls have low probability.

A classic example: a dynamic array grows its capacity by a fixed factor greater than `1`. After a capacity expansion, many empty slots become available. Subsequent additions consume those slots before another copy is needed. It is the state-transition rule itself that creates the total cost guarantee.

### 5.2. "Dividing the Total by the Number of Operations" Is Not Enough for a Proof

We can divide the total time of any single run by the number of operations. That is merely an average for that run.

To establish an amortized conclusion, we must prove a total bound for **every allowed sequence of operations in the model**, or use an equivalent method. We must state:

- The initial state.
- The set of allowed operations.
- How the collection grows or shrinks its capacity.
- Which costs are counted.

For instance, an `O(m)` bound for `m` additions starting from an empty dynamic array cannot be applied verbatim to a single addition into an array that is already full with `n` elements. If there is only one operation, the cost of copying `n` elements cannot vanish. When starting from a pre-populated structure, the total bound must account for the initial cost or state, such as `O(n + m)` under the corresponding growth model.

## 6. Proof with a Doubling Dynamic Array

To make the mechanism clear, let us use an **explanatory model**:

- Start with capacity `0`.
- The first addition allocates an array of capacity `1`.
- When the array is full, allocate a new array with double the capacity.
- Cost of an addition = number of old elements copied + one write for the new element.

This model does not claim that `ArrayList` in every JDK always grows by an exact factor of two. The specific growth policy of `ArrayList` is not mandated by the API specification; the published guarantee is amortized constant addition cost. [Java 17 ArrayList Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 6.1. Tracing 16 Additions

| Addition | Prior Capacity | Capacity Expanded? | Elements Copied | Total Cost Units |
| --- | --- | --- | --- | --- |
| 1 | 0 | Yes, to 1 | 0 | 1 |
| 2 | 1 | Yes, to 2 | 1 | 2 |
| 3 | 2 | Yes, to 4 | 2 | 3 |
| 4 | 4 | No | 0 | 1 |
| 5 | 4 | Yes, to 8 | 4 | 5 |
| 6–8 | 8 | No | 0 each | 1 each |
| 9 | 8 | Yes, to 16 | 8 | 9 |
| 10–16 | 16 | No | 0 each | 1 each |

There are `16` writes of new values. The total number of copied elements is:

```text
1 + 2 + 4 + 8 = 15
```

The total cost is `16 + 15 = 31`, whereas the most expensive addition costs `9` units. A small total does not eliminate the expensive call.

### 6.2. Aggregating Cost for `m` Additions

The copy sizes are powers of `2`:

```text
1 + 2 + 4 + ... + 2^k = 2^(k + 1) - 1
```

For `m` additions, the largest power of two that needs to be copied is strictly less than `m`. Therefore, the total number of copied elements is less than `2m`, and:

```text
T(m) < m + 2m = 3m
```

Conclusion:

- The total cost of `m` additions is `Θ(m)` in this model: at least `m` new elements must be written.
- The amortized cost per addition is `Θ(1)`.
- A single addition when the array is full still has a worst-case cost of `Θ(n)`.

The cost of allocating and initializing the new array is omitted in the simple count above. If we count them as linear in the new array's capacity, the sum of allocated capacities is still a geometric series. The overall order of growth remains linear in `m`; only the specific constant factors change.

### 6.3. Why Is Growing by One Slot Different?

If each full array only increases its capacity by `1`, then to add `m` elements we must copy:

```text
0 + 1 + 2 + ... + (m - 1) = m(m - 1) / 2
```

The total is `Θ(m²)`, so the amortized cost per addition is `Θ(m)`, which is no longer constant.

What creates the guarantee is not merely that "copying happens occasionally", but that **capacity grows fast enough so that the gap between copies also grows**. A fixed factor greater than `1` enables geometric series aggregation; the closer the factor is to `1`, the different the trade-off between copying cost and unused memory overhead.

### 6.4. Thinking in Terms of a Credit Reserve

We can imagine each addition paying a fixed amortized fee: part of it pays for the current write, and the remainder is stored as credit to pay for a future copy.

The credit reserve is a mathematical tool, not a monetary field or a mandatory counter inside the program. A proof using this accounting method must ensure that the credit balance never becomes negative. We cannot pick an arbitrary value and call it an amortized cost.

The aggregate method above is already sufficient to prove the doubling model. The accounting reserve method helps explain the intuition: cheap operations pre-pay for the expensive one; this requires no input distribution.

## 7. Java Program: Counting Operations and Verifying the Math

The program below runs on Java 17+. The `DoublingBuffer` class is a custom dynamic array model written to observe the number of copied elements. It does not inspect internal capacity or measure execution time of `ArrayList`.

The search section at the end of the program counts comparisons for five successful positions, then calculates the mean when all five positions are equally weighted.

Save the entire code as `CostModelsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class CostModelsDemo {
    private static final class DoublingBuffer {
        private int[] elements = new int[0];
        private int size;
        private long copied;
        private long writes;

        int add(int value) {
            int copiedNow = 0;
            if (size == elements.length) {
                int newCapacity = elements.length == 0
                        ? 1
                        : elements.length * 2;
                copiedNow = size;
                elements = Arrays.copyOf(elements, newCapacity);
                copied += copiedNow;
            }
            elements[size++] = value;
            writes++;
            return copiedNow + 1;
        }
    }

    private static int comparisonsUntilFound(List<Integer> values, int target) {
        int comparisons = 0;
        for (int value : values) {
            comparisons++;
            if (value == target) {
                return comparisons;
            }
        }
        return comparisons;
    }

    public static void main(String[] args) {
        DoublingBuffer buffer = new DoublingBuffer();
        List<Integer> costs = new ArrayList<>();
        int worst = 0;
        for (int i = 0; i < 16; i++) {
            int cost = buffer.add(i);
            costs.add(cost);
            worst = Math.max(worst, cost);
        }

        System.out.println("append costs = " + costs);
        System.out.println("writes = " + buffer.writes);
        System.out.println("copied = " + buffer.copied);
        System.out.println("total units = " + (buffer.writes + buffer.copied));
        System.out.println("worst append = " + worst);

        List<Integer> values = List.of(10, 20, 30, 40, 50);
        int successfulTotal = 0;
        for (int target : values) {
            successfulTotal += comparisonsUntilFound(values, target);
        }
        System.out.println("successful search total = " + successfulTotal);
        System.out.println("uniform successful mean = "
                + (double) successfulTotal / values.size());
        System.out.println("unsuccessful search = "
                + comparisonsUntilFound(values, 99));
    }
}
```

Compile and run:

```shell
javac --release 17 CostModelsDemo.java
java CostModelsDemo
```

Stdout:

```text
append costs = [1, 2, 3, 1, 5, 1, 1, 1, 9, 1, 1, 1, 1, 1, 1, 1]
writes = 16
copied = 15
total units = 31
worst append = 9
successful search total = 15
uniform successful mean = 3.0
unsuccessful search = 5
```

How to read the output:

1. The peaks `2`, `3`, `5`, and `9` show that the actual cost per addition is not fixed.
2. `31` units for `16` additions matches the total bound of less than `3m`.
3. `15 / 5 = 3` is the average under the assumption that the five targets occur uniformly; the number `3` is not a worst-case bound.
4. An unsuccessful query still checks all five elements.

The program uses small data to illustrate the mechanism, rather than being a general-purpose collection that handles capacity limits or all error conditions. A single run is a concrete demonstration; the geometric series proof is what explains why the amortized bound holds for any number of additions in the model.

## 8. Accurately Reading Java Collections Performance Statements

### 8.1. `ArrayList`: Distinguishing Appending, Middle Insertion, and Searching

`ArrayList.add(element)` appends to the end. A single call may need to expand capacity; a sequence of appends has an amortized constant guarantee. The API also allows pre-sizing capacity via a constructor or `ensureCapacity()`, which helps reduce reallocations when the number of elements to be added is known in advance. Do not infer a specific growth factor from that guarantee. [Java 17 ArrayList Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

Do not transfer this guarantee to every method with the same name:

- `add(0, element)` on a list with `n` elements must shift `n` elements to the right, even if spare capacity remains.
- `remove(0)` must shift subsequent elements to the left.
- `contains(value)` must search for the value; there is no free index lookup.
- `get(index)` accesses a known position, so it does not perform a linear search step.

If we repeatedly insert `m` elements at the head of an empty `ArrayList`, the number of elements shifted is `0 + 1 + ... + (m - 1)`. The `Θ(m²)` total comes from shifting, even though the capacity expansion cost is well amortized.

### 8.2. `HashMap`: Hash Dispersion Assumptions and Table Resizing Costs

The `HashMap` documentation states constant-time performance for `get` and `put` assuming the hash function disperses elements properly among the buckets. The table is resized when the number of mappings exceeds a threshold related to capacity and load factor. Initial capacity and load factor also affect performance, not just the number of mappings. [Java 17 HashMap Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

Here we need to keep two sources of cost separate:

1. **Key distribution across buckets:** affects how many candidates must be checked when looking up a key. If a random model is used for hashing/keys, we can analyze the expected cost under that model.
2. **Capacity expansion:** a `put` call may have to reorganize the table. This expensive cost is distributed across a sequence of insertions via amortized analysis.

Therefore, a rigorous statement typically reads: "Insertion has an amortized expected cost of `O(1)` under the assumptions of well-dispersed hashing, a controlled load factor, and constant-time key hashing and comparison." The word "expected" refers to bucket distribution; the word "amortized" refers to the sequence of table resizes. They can appear together because they address two distinct aspects.

Do not treat `HashMap.get` or `put` as a constant-time promise for every key. Many colliding keys, an expensive `hashCode()`, or an `equals()` method that traverses large data structures all make the simple description inaccurate. Likewise, do not infer a worst-case bound of `O(log n)` for arbitrary keys simply because an implementation can use tree bins; that is not a general guarantee stated by the API specification for all situations.

### 8.3. `ArrayDeque`: Operations at Both Ends Differ from Value Lookups

Common operations at both ends of an `ArrayDeque` have amortized constant cost. However, `contains`, value-based removal, and several other operations must perform linear work; do not apply double-ended characteristics to every method. [Java 17 ArrayDeque Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

When tasks need to be enqueued at the back and dequeued from the front, this mechanism avoids shifting all elements as `ArrayList.remove(0)` does.

### 8.4. `TreeMap`: Tree-Based Bounds and Comparison Costs

`TreeMap` provides guaranteed `O(log n)` time cost for `containsKey`, `get`, `put`, and `remove`. When translating this into key processing time, the cost of the comparison operation must also be included if it is not constant. [Java 17 TreeMap Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

For example, if each key comparison costs at most `O(L)`, the bound under that model becomes `O(L log n)`. "The tree has logarithmic height" does not eliminate the work inside application-supplied comparison code.

### 8.5. Quick Reference Table by Operation

The table below assumes that single-element manipulation, hashing, and relevant comparisons have constant cost, unless stated otherwise.

| Collection and Operation | Appropriate Description | What to Keep in Mind |
| --- | --- | --- |
| `ArrayList.get(index)` | `O(1)` | Valid index already known; no value search required |
| `ArrayList.add(element)` | Amortized `O(1)`; a single array expansion can be `O(n)` | Applies to appending at the end and the analyzed sequence |
| `ArrayList.add(0, element)` | `O(n)` | Must shift elements even without array expansion |
| `ArrayList.contains(value)` | Worst-case `O(n)` | Average case depends on query distribution |
| `HashMap.get(key)` | Constant assuming well-dispersed hashing | No constant-time guarantee for arbitrary keys |
| Sequence of `HashMap.put(key, value)` | Typically analyzed as amortized expected `O(1)` under stated assumptions | Consider collisions and table resizing separately |
| Adding/removing at both ends of `ArrayDeque` | Amortized `O(1)` | Do not extrapolate to searching or value-based removal |
| `TreeMap.get/put/remove` | Guaranteed `O(log n)` in number of comparison steps | Cost of a single comparison may depend on key data |

## 9. The Scope of the Operation Sequence Can Change the Conclusion

### 9.1. Do Not Ignore Operations That Actively Modify Capacity

The amortized analysis of appending at the end relies on retaining spare slots after a capacity expansion. If an application actively breaks that condition, the entire sequence must be re-analyzed.

Consider this illustrative snippet placed inside an existing method:

```java
ArrayList<Integer> values = new ArrayList<>();
for (int i = 0; i < limit; i++) {
    values.add(i);
    values.trimToSize();
}
```

`trimToSize()` requests shrinking the capacity to the current size. Calling it after every addition can repeatedly discard spare capacity and reintroduce linear copying work. We cannot take the amortized bound of an append-only sequence and apply it to this new sequence while ignoring the cost and impact of `trimToSize()`. In an array model that performs linear copying to shrink capacity, this sequence can incur quadratic total cost.

The snippet above is not a memory-optimization guide. It illustrates how **adding another type of operation to a sequence can invalidate the proof**.

### 9.2. Pre-sizing Capacity Shifts When the Cost Is Paid

If we know that roughly `expectedCount` elements will be added:

```java
List<String> names = new ArrayList<>(expectedCount);
```

The constructor creates a list with **size `0`**; the initial capacity is not the number of elements currently present. Pre-allocating memory carries a cost and can reduce the number of array expansions during the addition phase. It does not mean that all preparation work becomes free.

For `HashMap`, the initial capacity parameter relates to the number of buckets and is not identical to the expected number of mappings because of the load factor. Do not copy the `ArrayList` reasoning directly to `HashMap` while ignoring that condition.

## 10. From Complexity to Design Decisions and Measurement

### 10.1. Total Work vs. Single-Call Latency

The following two requirements are not identical:

- "Load one million elements with total work growing linearly."
- "No single addition may incur a linear work spike."

Amortized constant cost is appropriate for reasoning about the total work of a loading process. It does not automatically satisfy a strict per-call latency requirement.

When latency matters, consider pre-sizing capacity upfront, bounding data sizes, or choosing a data structure suited to the access pattern. Afterward, measurement on the target JVM and realistic workload is still required. There is no universally best collection based solely on a Big-O label.

### 10.2. Do Not Infer Complexity from a Single Stopwatch Reading

A single measurement with `System.nanoTime()` can be dominated by JVM warm-up, JIT compilation, GC pauses, allocation, system noise, or test harness overhead. A short elapsed time also does not tell us whether we observed the non-resizing branch or the copying branch.

A useful evaluation should specify:

1. **Workload:** appending at the end, inserting at the head, successful lookups, unsuccessful lookups, or a mix of operations?
2. **State:** a fresh collection, pre-populated data, nearly full capacity, or pre-allocated capacity?
3. **Data:** number of elements, key size, hash quality, and query frequency?
4. **Metrics:** total throughput time, operations per second, or per-operation latency distribution?
5. **Comparison method:** identical functionality, identical starting conditions, and multiple dataset sizes?

Counting operations as in the demo program helps verify the underlying mechanism without timing noise. Benchmarking reveals how that mechanism manifests in a concrete runtime environment. The two approaches complement each other.

## 11. Common Misconceptions

| Misleading Statement | More Accurate Phrasing |
| --- | --- |
| "Amortized is the average case." | Amortization distributes the total cost of a sequence; average case requires an input probability distribution. |
| "`ArrayList.add` is `O(1)`, so every call is equally fast." | Appending is amortized `O(1)`; a call that expands the array can be linear. |
| "Searching scans half the list on average, so it is `O(1)`." | `(n + 1) / 2` is still `Θ(n)`. |
| "Every operation has a worst case of `O(n)`, so the total is definitely `Θ(mn)`." | Multiplying upper bounds can yield a loose bound; finding a tight bound requires checking whether expensive states can repeat after every step. |
| "Measuring a thousand runs and taking the mean proves amortization." | That is a measurement on one sequence; a proof must cover all sequences within the stated scope. |
| "`HashMap` is always constant-time because it uses trees against collisions." | You must state hashing assumptions, key characteristics, and key method costs; do not assign guarantees absent from the API specification. |
| "Capacity was pre-allocated, so all memory costs have disappeared." | The work is shifted to the preparation phase; allocation cost and retained memory must still be accounted for. |
| "One million appends at the end and one million insertions at the head are the same problem." | Inserting at the head also shifts elements; amortized capacity growth does not eliminate that cost. |

## 12. Self-Check on Reasoning

### Question 1: A doubling dynamic array has a single addition that costs `n + 1` units. Does this refute amortized constant cost?

No. You must consider the total cost across the entire sequence. The capacity expansions copy `1, 2, 4, ...` elements, whose sum is linear in the number of additions. The expensive call still exists, but it cannot occur on every addition in an append-only sequence.

### Question 2: Searching for an existing element where every position is equally likely. Is the average case faster than the worst case in order of growth?

No. The average case requires `(n + 1) / 2` comparisons while the worst case requires `n`; both have linear order of growth. The different constant factors matter in practice, but they do not change the asymptotic order of growth.

### Question 3: A program receives untrusted data and performs lookups using `HashMap`. Is there sufficient basis to promise that every query is `O(1)`?

No. You must consider the possibility of hash collisions, key processing costs, and implementation characteristics. A statement predicated on well-dispersed hashing is not a worst-case guarantee for arbitrary inputs.

### Question 4: Why does `ArrayList.add(0, value)` not enjoy linear total cost when repeated many times starting from an empty list?

Because each insertion must shift the existing elements. The total number of shifted elements is `0 + 1 + ... + (m - 1) = Θ(m²)`. A good capacity growth mechanism only handles reallocation costs, not positional shifting costs.

### Practice Exercises

1. Change the number of additions in `CostModelsDemo` from `16` to `17`. Predict the number of copied elements, the total cost, and the cost of the final addition before running it.
2. Calculate the expected number of comparisons if the target is the first element with probability `0.9` and the last element with probability `0.1` in a list of `n` elements.
3. Write a single performance description sentence for a real task of yours, stating the operation, size, analysis type, and assumptions.

Reference Answers:

- With `17` additions: the `17`th addition copies `16` elements; total copied is `31`, total cost is `48`, and the final addition cost is `17`.
- The query model in exercise 2 has an expected cost of `0.9 × 1 + 0.1 × n = 0.9 + 0.1n`, which is still `Θ(n)` as `n` grows.
- Example description sentence: "When loading `m` elements by appending to a fresh `ArrayList`, the total addition cost is `O(m)` under the amortized guarantee; an individual array expansion can still incur linear work in the current size."

When evaluating a collection, clearly identify **whether you mean a single call or an entire sequence**, **what distribution applies if speaking of an average**, and **what state and costs are being counted**. These three questions turn a Big-O label into a verifiable argument.