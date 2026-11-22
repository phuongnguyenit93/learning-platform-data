# PriorityQueue offer, peek, poll, and Complexity

## 1. In what order does a priority queue choose the next element?

A system is waiting on jobs with different priority levels. It needs to add new jobs, inspect which job will be chosen next, and remove that job for processing.

The three core methods are:

| Method | Action | Does it change the element count? |
|---|---|---|
| `offer(e)` | Adds `e` to the priority queue | Increases by one on a successful add |
| `peek()` | Inspects the head element by priority order | No |
| `poll()` | Retrieves and removes the head element by priority order | Decreases by one if an element exists |

Unlike a FIFO queue, `PriorityQueue` does not default to selecting the element that arrived first. It selects the element that is **smallest according to the ordering in use**. The ordering can be the data type's natural order or one defined by a `Comparator`.

For example, with ascending integer order, adding `7, 1, 5` gives a `peek` of `1`. If business logic requires larger numbers to be retrieved first, a corresponding comparator is needed; there is no automatic rule that "a higher priority number is always processed first."

The [Java 17 PriorityQueue documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html) specifies the head element, null policy, ordering, and common cost bounds. This article connects those rules to the heap mechanism to explain why `offer`, `peek`, and `poll` have different costs.

## 2. The heap root explains the difference between the three operations

`PriorityQueue` uses a heap to maintain the smallest element according to the comparator at the root. `offer()` adds at the last position and sifts up when needed; `peek()` reads the root directly; `poll()` removes the root, moves the last element to the root, and sifts down. Because heap-repair paths only span the height of the tree, they are not a full sort of all `n` elements.

A min-heap can be represented by `[1, 3, 2, 8, 5, 7, 4]`: parent–child edges are valid even though the array is not in ascending order. This model does not dictate iterator order or the JDK's internal layout. The article on heap structure presents sift-up/sift-down step by step along with parent–child indices.
## 3. offer: add an element and restore the heap relation

The call:

```java
// Snippet; requires import java.util.PriorityQueue.
PriorityQueue<Integer> values = new PriorityQueue<>();
boolean accepted = values.offer(7);
```

adds one occurrence of the value `7`. With a standard `PriorityQueue`, when the operation completes successfully, `offer` returns `true`.

### 3.1. Adding at the end of the data region

In the array-based heap model, the new element is placed at the next position after the existing elements. That position preserves the shape of a complete binary tree: all levels before the last level are full, and the last level is filled from left to right.

Afterward, it may be necessary to move the element upward to restore the parent–child relation, commonly called sift-up.

Example of adding `0` to the illustrative heap:

```text
before adding:
[1, 3, 2, 8, 5, 7, 4]

place 0 at the new position:
[1, 3, 2, 8, 5, 7, 4, 0]

0 is smaller than the parents along the path:
0 passes 8, then 3, then 1

a valid heap result:
[0, 1, 2, 3, 5, 7, 4, 8]
```

The algorithm does not re-sort every pair of elements. It processes a single path from the new position toward the root, whose number of levels is logarithmic in the heap size.

### 3.2. Duplicate elements are still added

`PriorityQueue` is not a `Set`. Adding `1` twice can succeed both times and increase `size` by two.

Comparing as `0` also does not mean discarding an equivalent element like `TreeSet`. A heap can hold multiple elements with the same priority.

If duplicates must be avoided by a business key, that is an additional requirement. Do not read `offer` returning boolean `true` as "checked that this element does not already exist."

### 3.3. Offer returning boolean does not mean every failure becomes false

`PriorityQueue` does not accept `null` elements, even when a comparator is capable of comparing `null`. Offering `null` throws `NullPointerException`.

An element that cannot be compared according to the required ordering can cause `ClassCastException`. A class without `Comparable` needs a suitable comparator if used as an element.

`PriorityQueue` grows its capacity automatically, so do not use `false` as a signal that "the configured job-count limit has been reached" for this class. Initial capacity is not a business limit and does not create a blocking mechanism when full.

## 4. peek: read the head element without consuming it

`peek` returns the head element according to priority order without removing it.

```text
heap has: 1, 3, 2, 8, 5, 7, 4 in a valid arrangement
peek() -> 1
size unchanged
peek() again, with no changes in between -> still 1
```

In OpenJDK 17's array-based implementation, `peek` reads the root position. No sift-up, sift-down, or comparator calls are needed to find the smallest element again.

### 4.1. Returns null when empty

`PriorityQueue` forbids `null` elements, so `null` returned from `peek` can be used to represent the absence of elements.

If you want a missing element to be an explicit error, `Queue`'s `element` method also only inspects the head, but throws `NoSuchElementException` when empty.

Do not auto-unbox before checking the empty case:

```java
// Error-prone snippet: poll or peek can return null.
int next = values.peek();
```

When empty, unboxing `null` to `int` causes `NullPointerException` in the caller. You can keep `Integer` and check for `null`, or use a method with the appropriate failure policy.

### 4.2. Peek does not mean the work is done

If a loop keeps calling `peek` and processing without removing the element or changing the stopping condition, it can process the same element forever.

If the intent is to take the next job to consume, `poll` expresses the operation more accurately.

Similarly, `peek` followed by `poll` are two separate calls. In code with interleaved updates, do not assume `poll` always returns the exact object just inspected. Process the value actually returned by the retrieval call, with appropriate coordination if shared across multiple threads.

## 5. poll: remove the root and repair the downward path

`poll` both returns and removes the head element. When empty, it returns `null`.

In the array-based heap model, if multiple elements remain:

1. Save the root value to return.
2. Take the last element in the data region as the candidate to fill the root.
3. Decrement the element count and clear the reference in the old last slot.
4. Move the candidate down the tree to restore the heap relation.

The downward step is commonly called sift-down.

### 5.1. Must choose the appropriate child

For a min-heap, if two children exist, you must check which child is smaller. If the candidate is larger than the smaller child, move that child up and continue downward.

Comparing only against the left child and ignoring the right child can break the heap relation.

From the initial illustrative heap, `poll` `1` and use the last value `4`:

```text
before poll:
[1, 3, 2, 8, 5, 7, 4]

fill the root with 4, drop the last slot:
[4, 3, 2, 8, 5, 7]

move 2 up because 2 is the smaller child of the root:
[2, 3, 4, 8, 5, 7]
```

Candidate `4` already satisfies the relation with its child `7`, so it stops. This is a local repair process, not a re-sort of the entire sequence.

### 5.2. Empty or single element

If empty, there is no root to remove and `poll` returns `null`.

If there is only one element, after retrieving it the queue becomes empty; no long sift-down path is needed. The logarithmic bound describes general scaling, not that every call takes the exact same number of steps.

### 5.3. Poll differs from remove(Object)

`Queue`'s zero-argument `remove()` also retrieves and removes the head, but throws an exception when empty.

`remove(x)` with an argument is a different request: find an element equal to `x` according to `equals` and remove one occurrence. It may have to scan the queue and has linear cost.

Do not infer from "`poll` is O(log n)" that "every call named `remove` on `PriorityQueue` is O(log n)."

## 6. Program 1: offer, peek, poll, and duplicate elements

Save the file `PriorityQueueApiDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.PriorityQueue;

public class PriorityQueueApiDemo {
    public static void main(String[] args) {
        PriorityQueue<Integer> values = new PriorityQueue<>();
        for (int value : new int[] {7, 1, 5, 1, 3}) {
            System.out.println("offer " + value + " = " + values.offer(value));
        }

        System.out.println("size after offers = " + values.size());
        System.out.println("peek one = " + values.peek());
        System.out.println("peek two = " + values.peek());
        System.out.println("size after peeks = " + values.size());
        System.out.println("poll first = " + values.poll());
        System.out.println("size after one poll = " + values.size());

        List<Integer> output = new ArrayList<>();
        Integer next;
        while ((next = values.poll()) != null) {
            output.add(next);
        }
        System.out.println("remaining poll order = " + output);
        System.out.println("empty = " + values.isEmpty());
        System.out.println("empty peek = " + values.peek());
        System.out.println("empty poll = " + values.poll());

        try {
            values.offer(null);
        } catch (NullPointerException ex) {
            System.out.println("offer null = " + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 PriorityQueueApiDemo.java
java PriorityQueueApiDemo
```

Output of the verification run:

```text
offer 7 = true
offer 1 = true
offer 5 = true
offer 1 = true
offer 3 = true
size after offers = 5
peek one = 1
peek two = 1
size after peeks = 5
poll first = 1
size after one poll = 4
remaining poll order = [1, 3, 5, 7]
empty = true
empty peek = null
empty poll = null
offer null = NullPointerException
```

The programs in this article use language features and APIs available in Java 17 and later, compiled with `--release 17` and verified on Azul OpenJDK 24.0.2.

Five `offer` calls succeed, including the value `1` appearing twice. A `size` of `5` confirms this is a queue storing occurrences, not a deduplicating set.

Both `peek` calls return `1` and do not reduce `size`. The first `poll` removes one value `1`; subsequent `poll` calls still see the other value `1`.

Once drained, `peek` and `poll` both return `null`. However, the reason is not that they do the same thing: on a non-empty queue, `peek` only inspects whereas `poll` mutates the data.

The code collects results from `poll` into a `List` to preserve order. It does not rely on `PriorityQueue`'s iterator order.

## 7. Complexity: separating heap, array, and comparison cost

The `PriorityQueue` Javadoc states O(log n) for the basic enqueuing/dequeuing operations, O(1) for `peek`/`element`/`size`, and O(n) for `contains` or object-based `remove`.

To fully understand an actual call, separate three kinds of work:

```text
storage management
    +
heap relation repair
    +
cost per comparison
```

### 7.1. Heap repair cost

With a constant-cost comparison:

| Operation | Main work | Heap-part cost |
|---|---|---|
| `offer` | Place element then sift-up | O(log n) |
| `peek` | Read root | O(1) |
| `poll` | Remove root, fill with last element, sift-down | O(log n) |
| `size` | Read stored count | O(1) |

A complete binary tree heap has height O(log n). Sift-up walks one path upward; sift-down walks one path downward. Each level uses a constant-bounded number of comparisons.

`peek` is cheap because the work of maintaining the head element was already paid during earlier updates.

### 7.2. An offer that needs to grow the array can be O(n)

`PriorityQueue` has an auto-growing backing array. The [OpenJDK 17 PriorityQueue source code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java) shows that `offer` checks space, grows the array when needed, and then performs sift-up; growing the array copies references to a new array.

Therefore, distinguish:

- The O(log n) bound for the heap-adjustment portion.
- A specific `offer` that triggers array growth has additional O(n) work.
- Over a sequence of adds with proportional growth, the array-growth cost is amortized; heap repair still gives an overall O(log n) amortized bound per add.

Reading the complexity line in the Javadoc should not become the conclusion that "every individual `offer` has latency bounded by at most a logarithmic number of steps, including allocation."

An appropriate initial capacity can reduce early-stage resizes, but it does not change the sift-up bound and does not set a maximum element limit.

### 7.3. A comparator may not be cheap

If each comparison costs `C`, the heap-repair portion can be expressed as O(C * log n).

A comparator inspecting multiple fields or long strings can cost more than an `int` comparison. Do not put external queries or side effects that mutate priority data inside a comparator.

`peek` in this implementation model does not re-pay the comparator cost on each root inspection; however, mutating properties used by the comparator can still break the structure's correctness.

### 7.4. Retrieving all n elements is not O(n)

If you need to consume all elements via `poll`, the overall total cost is O(n log n), because each step must also maintain the heap for the remaining elements.

Iterating with an iterator can visit `n` elements but does not guarantee priority order. Do not compare the two approaches as if they return the same kind of result.

Similarly, adding `n` elements with `n` `offer` calls has an overall O(n log n) bound for heap repair. Do not lump every way of constructing from a collection into the same per-`offer` argument: an implementation can use a separate bulk heap-construction algorithm.

## 8. Program 2: counting comparisons per operation

The following program uses a comparator that counts calls, while the comparison result is still always `Integer.compare`. It pre-allocates enough space for the next element to isolate heap repair.

Save the file `PriorityQueueComparisonCostDemo.java`:

```java
import java.util.Comparator;
import java.util.PriorityQueue;

public class PriorityQueueComparisonCostDemo {
    static final class CountingComparator implements Comparator<Integer> {
        private int calls;

        @Override
        public int compare(Integer left, Integer right) {
            calls++;
            return Integer.compare(left, right);
        }

        void reset() {
            calls = 0;
        }

        int calls() {
            return calls;
        }
    }

    public static void main(String[] args) {
        for (int n : new int[] {7, 31, 127, 511}) {
            CountingComparator order = new CountingComparator();
            PriorityQueue<Integer> values =
                    new PriorityQueue<>(n + 1, order);

            for (int value = 0; value < n; value++) {
                values.offer(value);
            }

            order.reset();
            values.offer(-1);
            int offerComparisons = order.calls();

            order.reset();
            Integer head = values.peek();
            int peekComparisons = order.calls();

            order.reset();
            Integer removed = values.poll();
            int pollComparisons = order.calls();

            System.out.println("n=" + n
                    + ", offerComparisons=" + offerComparisons
                    + ", peekComparisons=" + peekComparisons
                    + ", pollComparisons=" + pollComparisons
                    + ", peek=" + head
                    + ", poll=" + removed
                    + ", next=" + values.peek());
        }
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 PriorityQueueComparisonCostDemo.java
java PriorityQueueComparisonCostDemo
```

Output of the verification run:

```text
n=7, offerComparisons=3, peekComparisons=0, pollComparisons=4, peek=-1, poll=-1, next=0
n=31, offerComparisons=5, peekComparisons=0, pollComparisons=8, peek=-1, poll=-1, next=0
n=127, offerComparisons=7, peekComparisons=0, pollComparisons=12, peek=-1, poll=-1, next=0
n=511, offerComparisons=9, peekComparisons=0, pollComparisons=16, peek=-1, poll=-1, next=0
```

### 8.1. Why does offer use more comparisons when n is larger?

The initial data consists of non-negative numbers. Offering `-1` forces the new element to travel up toward the root. When the heap is taller, the path has more levels.

At the chosen sizes, the run yields `offer` comparison counts of `3, 5, 7, 9`. This is an observation about path length, not an API-guaranteed formula for comparator call counts.

If you `offer` an element that already satisfies the relation with its parent near the end position, it can stop early. O(log n) does not mean every input traverses the full heap height.

### 8.2. Peek does not call the comparator in the example

The counter is reset right before `peek` and the result is `0`. Element `-1` is already at the root from the preceding `offer`, so `peek` just reads it.

Do not conclude that using a very slow comparator does not matter: `offer` and `poll` still need the comparator to reorganize the data.

### 8.3. Poll repairs the downward path

`poll` removes `-1` and must restore the next head, `0`. At each level, it may need to compare the two children and compare the candidate with the chosen child.

Therefore, do not compare `poll`'s call count with `offer`'s and expect them to always be equal. Both are bounded by the heap height, but they perform different work at each level.

### 8.4. This is not a timing or allocation measurement

The constructor receives `n + 1`, enough room for the initial `n` elements plus one `offer(-1)`. The counter does not measure allocation, array copying, or nanoseconds.

If another `offer` must grow the array, the counted comparator calls still do not reflect all of that work. This is why comparison counting must be separated from the total cost of a call.

The output numbers were verified on the environment noted in Program 1. Do not hardcode them as compatibility assertions across JDK versions.

## 9. Comparison rule determines the queue head

With `Integer` in natural order, `peek()` is the current smallest number; using `Comparator.reverseOrder()` makes the head the largest numeric value. The heap still selects the element that comes first under the new rule.

If two elements compare as `0`, the `Queue` still keeps both and does not guarantee FIFO order between them. When business logic requires processing in arrival order within a tied group, the comparator must compose an immutable arrival key. `contains`/`remove(Object)` search by `equals`; directly mutating the field that determines priority does not automatically re-heapify the queue. These are the conditions that apply when interpreting the results of `offer`, `peek`, and `poll`.
## 10. Scenario applying the three operations with a composite priority key

Consider `Job` items `(priority, arrival, name)`: `(5,0,routine)`, `(1,1,urgent-A)`, `(1,2,urgent-B)`, `(3,3,medium)`. The comparator compares `priority` ascending, then `arrival` ascending. After calling `offer()` for all four, `peek()` returns `urgent-A` without reducing the size of `4`.

Retrieving sequentially with `poll()` returns `urgent-A → urgent-B → medium → routine`. The two `urgent` jobs have the same `priority` but are distinguished by `arrival`; `routine`, which arrived earlier, is still not retrieved first because of its lower priority. If you only want to preview the list, `poll` a copy `new PriorityQueue<>(jobs)` instead of consuming the original queue.

This example adds a scenario for the two runnable programs in sections 6 and 8. Composite comparator rules, tied elements, and viewing results in order are covered in full in their respective articles.
## 11. Usage patterns and total cost

### 11.1. Add when new work arrives, retrieve when ready to process

A single-threaded pattern:

```java
// Snippet; Job and process are defined in the enclosing program.
PriorityQueue<Job> jobs = new PriorityQueue<>(order);
jobs.offer(newJob);

Job next = jobs.poll();
if (next != null) {
    process(next);
}
```

The value `next` is the job that was removed and is genuinely dedicated to that processing pass. Do not `peek` a job and then ignore the value returned by `poll`.

If processing can fail, ownership, retry, or job recovery is an application policy. `poll` only mutates the collection; it does not itself confirm business completion.

### 11.2. Only need to know the next job

Use `peek` when the next decision does not want to remove the job immediately, such as inspecting information on the current head.

However, do not treat a peeked reference as a reservation. If other updates occur afterward, the head can change. With multiple threads, a plain `PriorityQueue` is not thread-safe for concurrent mutating access.

A single-thread-owned queue model has different assumptions from a shared-queue system. Keep usage conditions explicit.

### 11.3. Need the entire processing order

Different approaches have different meanings:

- `poll` on the source: get the order and consume the source.
- Create a copy and `poll`: get the order while keeping the original container.
- Copy the data to a `List` and sort with the appropriate comparator: get a separate sorted sequence.

Do not use `for-each` on `PriorityQueue` as an optimization in place of the approaches above when priority order is still required.

Creating and holding a copy has memory cost for the references. Polling everything has heap-level total work; sorting also has sorting cost. There is no way to inspect all elements in order while avoiding all data-organization work.

### 11.4. Multiple peeks do not reduce size

If an application inspects the head many times between updates, `peek`'s O(1) advantage is valuable: the heap maintains the head on adds/removals, while re-inspecting requires no scan.

However, a processing loop needs progress. If the stopping condition is emptiness while the code only calls `peek`, `size` does not decrease and the loop may never terminate.

## 12. Complexities often conflated

| Need or call | Cost/behavior to remember |
|---|---|
| Inspect head with `peek` | O(1), does not remove |
| Retrieve head with `poll` | O(log n) in the general heap-part case |
| Retrieve head with `remove()` | Same head-retrieval role, different empty policy |
| Remove an object with `remove(x)` | Can be O(n) because it must search |
| Check `contains(x)` | O(n) in general, does not benefit like search-tree lookup |
| Add with `offer` | Sift-up O(log n); mind array growth |
| Iterate with iterator | Visits elements but does not promise priority order |
| Poll all `n` elements | O(n log n) overall for consuming in priority order |
| Change priority by removing object then re-adding | Includes the linear search step if using `remove(Object)` |

A heap is not a binary search tree. The parent–child relation is only enough to locate the highest-priority element, not enough to choose a single branch when searching for an arbitrary value.

That is why `contains` does not automatically become O(log n) just because the heap shape has logarithmic height.

When `n` changes during a sequence of operations, analyze the total using the corresponding sizes. Do not take a single `size` at the end and treat every call throughout the process as having the exact same cost.

## 13. Common usage mistakes

| Misconception or practice | Consequence | Fix |
|---|---|---|
| Treating `offer` like adding to a FIFO queue | Jobs can be selected by priority instead of arrival order | Define the comparator and selection contract |
| Thinking `peek` already removed the element | Can repeatedly process the same head | Use `poll` to consume |
| Assigning `poll` result directly to `int` | Empty queue can cause a `null` unboxing error | Keep the reference type and handle absence |
| Thinking `offer` returns `false` on duplicates | `PriorityQueue` keeps multiple occurrences | Manage deduplication separately if needed |
| Expecting FIFO on equal priorities | The API does not guarantee stability on ties | Add a meaningful tie-breaking criterion |
| Using iterator to print priority order | A heap is not a fully sorted sequence | `poll`, copy-and-poll, or sort appropriately |
| Mutating the priority field while in the queue | The heap does not automatically update position | Use stable data and an update workflow |
| Thinking every `remove` is logarithmic | `remove(Object)` must search by value | Distinguish method signatures |
| Treating every individual `offer` as logarithmic including allocation | Ignores array growth | Separate heap repair and storage; understand amortized cost |
| Using initial capacity as a job limit | The queue still grows when needed | Design the actual limit in the appropriate place |
| Writing a comparator using `int` subtraction | Can overflow and corrupt ordering | Use `Integer.compare` or `comparingInt` |
| Sharing `PriorityQueue` without coordination | No concurrent-mutation safety contract | Choose an appropriate concurrency model |

Priorities that change over time also need clear design. A comparator reading a clock or mutable external configuration can change the ordering relation without the heap having been updated.

Not every system needs a complex scheduling mechanism, but you must know when comparison data is kept stable and when the queue is reorganized.

## 14. Verifying the right API and the right assumptions

A test suite for code using `PriorityQueue` should be based on observable outcomes:

1. `offer` values whose input order differs from priority order.
2. `peek` multiple times, verifying `size` does not change.
3. `poll` once, verifying `size` decreases and the next head is correct.
4. `poll` all remaining elements, verifying the full count and order.
5. Add duplicate elements, confirming every occurrence that should be kept is present.
6. Verify empty and `null` handling according to policy.
7. Verify a reversed comparator if business logic selects larger numbers first.
8. Verify ties using the secondary criterion if stability is required.
9. Verify job mutation or replacement according to the designed update workflow.

Do not write a test asserting that the iterator must produce the same ascending sequence as `poll`. That is not part of the contract.

Also do not require comparator call counts to exactly match the counting program's output across all JDK versions. The counting example helps explain the work, whereas application compatibility should be tied to required behavior.

If you only check `size` or a checksum, you can miss order inversions. If you only check using a `Set`, you can also miss occurrence counts. Compare the result sequence when ordering is a core requirement.

For objects with equal priority, only assert a specific order when the comparator distinguishes them as required. If there is no secondary criterion, tests must accept any valid order within the equivalence group.

## 15. Practice exercises

### Exercise 1: distinguishing inspect and retrieve

`offer` `4, 2, 7`, call `peek` twice, then `poll` once. How does `size` change?

**Answer hint:** after `offer`, `size` is `3`; two `peek` calls do not change `size`; a successful `poll` reduces `size` to `2`. Under natural order, both inspections and the first retrieval target the value `2` if no interleaved changes occur.

### Exercise 2: duplicate elements

`offer` `1` twice. Does the second call return `false` to signal it already exists?

**Answer hint:** no. `PriorityQueue` does not deduplicate; both calls can succeed and create two occurrences.

### Exercise 3: head under reverse order

A `PriorityQueue` uses `reverseOrder` and contains `3, 9, 5`. What are the first `peek` and `poll`?

**Answer hint:** both are `9` if there are no interleaved updates; `peek` does not remove, `poll` removes.

### Exercise 4: logarithmic heap height but linear contains

Why can't you conclude `contains` is O(log n) from the heap height?

**Answer hint:** a heap does not have the rule that all smaller values lie on one side and larger ones on the other like a search tree. For an arbitrary value, it may have to inspect many positions.

### Exercise 5: a slow offer due to array growth

Does that contradict learning that `offer` is O(log n)?

**Answer hint:** you need to separate cost layers. Sift-up is logarithmic, while a single array growth can be linear; over a sequence of operations there is amortized analysis for storage.

### Exercise 6: equal priority, need first-come first-served

Two jobs have the same `priority`. Is a comparator on `priority` alone enough to guarantee FIFO within the group?

**Answer hint:** no. You need a secondary criterion expressing arrival order, such as a consistent `arrival` value that properly distinguishes the jobs.

### Exercise 7: inspect all while keeping the source

Can you `poll` the source to get the sequence and still treat it as a read-only inspection?

**Answer hint:** no. `poll` consumes the source. You can `poll` an appropriate copy or create a separate sequence and sort it with the right comparator.

### Exercise 8: changing priority directly

A job currently inside a `PriorityQueue` has its priority level changed via a setter. Does the queue automatically re-sift?

**Answer hint:** no. You need stable comparison data or a controlled update workflow; when using `remove(Object)` to remove it, you must also account for the linear search cost.

When choosing between `offer`, `peek`, and `poll`, be clear on whether you are adding, only inspecting, or consuming. When reading complexity, state clearly how the heap part, array allocation, and comparator cost are being accounted for.
