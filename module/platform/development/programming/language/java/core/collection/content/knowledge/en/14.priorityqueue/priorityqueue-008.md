# The Top-K Problem and Choosing a Min-Heap or Max-Heap

## 1. What is Top-K and When Do We Need It?

Top-K is the problem of selecting up to K best elements according to a criterion from N input elements. "Best" can mean the largest value, shortest waiting time, highest rating score, or smallest distance. Before choosing a data structure, you must determine which direction is better: a large number may be good in a scoring problem but bad in a latency problem.

For example, from the sequence:

~~~text
7, 2, 9, 4, 9, 1, 8, 5
~~~

If each occurrence counts as an element, then:

| Requirement | Result sorted in desired order |
| --- | --- |
| Three largest elements | [9, 9, 8] |
| Three smallest elements | [1, 2, 4] |
| Third largest value, including duplicates | 8 |
| Three largest distinct values | [9, 8, 7] |

These are different requirements. A priority queue does not automatically decide whether to deduplicate, and top-K by occurrence is not synonymous with top-K distinct values.

Sorting the entire input and taking the first K elements is an easy-to-understand approach. However, if N is very large, K is small, or data arrives one element at a time, we want to keep only the candidates that still have a chance of being in the result. A size-bounded heap helps achieve that.

In this lesson, a "min-heap" is a heap with the smallest element at the root according to the ordering under consideration; a "max-heap" is a heap with the largest element at the root according to that ordering. These two names refer to the position of the extremum, not the capacity of the heap. Both can be bounded to K elements.

After this lesson, you should be able to answer three questions on your own: which element is currently the weakest in the kept group; is the new element better than it; and which element must be at the head of the heap to make replacement decisions fast?

## 2. Connection to Java's PriorityQueue

`PriorityQueue` chooses the head of the queue according to natural ordering or a provided `Comparator`. The head of the queue is the element that comes first according to that ordering. For integers, natural ordering puts the smallest number at the head; reversing the ordering puts the largest number at the head. When elements tie, the queue does not guarantee picking the element added earlier. [PriorityQueue Documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

Two basic declarations:

~~~java
PriorityQueue<Integer> minHeap = new PriorityQueue<>();
PriorityQueue<Integer> maxHeap =
        new PriorityQueue<>(Comparator.reverseOrder());
~~~

These are two ways of configuring the same class. Java does not provide two classes named `MinHeap` and `MaxHeap` for this case.

The easiest mistake to make is choosing the heap based on the name of the result: "to find the largest, use a max-heap." That rule fits when you keep all the data and want to immediately retrieve the largest element. With an algorithm that only keeps K candidates, the frequent operation is instead removing the weakest candidate. Therefore, you must choose the heap head based on the element to be evicted.

| Goal of the K-bounded heap | Weakest element in the kept group | Heap needed for integers |
| --- | --- | --- |
| Keep the K largest elements | Smallest in the group | Min-heap, natural order |
| Keep the K smallest elements | Largest in the group | Max-heap, reverse order |

Read the first row as a sentence: "Among the K largest numbers currently kept, the smallest number is the easiest to replace; put it at the head of the heap."

## 3. The Threshold Model: The Heap Head Is the Acceptance Boundary

Suppose we need the three largest numbers and the heap currently holds:

~~~text
Candidates: 7, 9, 9
Current threshold: 7
~~~

If we read 8, it is better than 7, so we evict 7 and add 8. If we read 5, there is no reason to evict any currently kept candidate to accept 5.

With a K-bounded min-heap, `peek()` returns the smallest threshold still accepted in the current group. It is not necessarily the smallest number of all data read so far, because numbers that were too small have already been evicted.

Similarly, when we need the three smallest numbers:

~~~text
Candidates: 1, 2, 4
Current threshold: 4
~~~

A new number equal to 3 will replace 4. A new number equal to 8 is skipped. A max-heap puts 4 at the head so we do not have to find the weakest candidate by scanning the entire group.

Before K elements have been received, `peek()` is only the extremum of a non-full group. Only after the group reaches K elements does it act as the boundary of the current top-K. For example, after reading only the first number, you cannot use the head of the heap to conclude that you already have the "third largest number."

In an append-only stream, once the top-K largest heap is full, the threshold is non-decreasing: each replacement accepts a number greater than the old threshold. For top-K smallest, the threshold is non-increasing. This is a consequence of the selection rule itself, not a full sort of the input.

## 4. Algorithm to Keep the K Largest Elements

Assume K > 0 and the values are integers:

~~~text
Create an empty min-heap.
For each number x:
    If the heap has fewer than K elements:
        add x.
    If the heap already has K elements:
        get the smallest threshold using peek().
        if x > threshold:
            poll() to evict the threshold;
            offer(x).
        if x <= threshold:
            skip x.
~~~

Core code, used in the full program in a later section:

~~~java
static void keepLargest(PriorityQueue<Integer> heap, int value, int k) {
    if (heap.size() < k) {
        heap.offer(value);
    } else if (value > heap.peek()) {
        heap.poll();
        heap.offer(value);
    }
}
~~~

This helper method has preconditions: `k > 0`, the heap uses natural ordering, contains no `null`, and before each call its size is no greater than K. The general function in a later section validates K and handles K = 0 before looping; do not call this helper with K = 0.

You must check whether the heap is not yet full before comparing with `peek()`. When the heap is empty, `peek()` returns `null`; if `Integer` is auto-unboxed to `int` in the `>` comparison, the program will throw a `NullPointerException`.

Why use `>` instead of `>=`? In a problem that ranks solely by numeric value, a number equal to the threshold does not improve the values in the result. Skipping it when the heap is full avoids two unnecessary heap operations. This does not eliminate all duplicate elements: equal occurrences can still be added when the heap is not yet full or when they are better than the threshold.

For example, `[9, 9, 9, 8]` with K = 2 still yields `[9, 9]`. If you need to distinguish identities among records with equal scores, you must add a tie-breaking criterion rather than inferring it from the `>` operator.

### Tracing a Complete Example

The table below sorts the kept elements in descending order for readability. This is a way to present intermediate results, not a description of the heap's internal array order.

| Step | New number | Action | Kept values | Min-heap head |
| --- | --- | --- | --- | --- |
| 1 | 7 | Not full, add | [7] | 7 |
| 2 | 2 | Not full, add | [7, 2] | 2 |
| 3 | 9 | Not full, add | [9, 7, 2] | 2 |
| 4 | 4 | 4 > 2, replace 2 | [9, 7, 4] | 4 |
| 5 | 9 | 9 > 4, replace 4 | [9, 9, 7] | 7 |
| 6 | 1 | 1 <= 7, skip | [9, 9, 7] | 7 |
| 7 | 8 | 8 > 7, replace 7 | [9, 9, 8] | 8 |
| 8 | 5 | 5 <= 8, skip | [9, 9, 8] | 8 |

The decision point is comparing against the threshold, not against the immediately preceding number and not against the largest number currently kept.

A valid min-heap shape for the final group:

~~~text
       8
      / \
     9   9
~~~

The two 9s do not need a before-or-after order relative to each other. Only the root needs to indicate that the weakest candidate is 8.

## 5. Switching to the K Smallest Elements

To keep the K smallest numbers, change two things at the same time:

1. Put the largest number in the group at the head using reverse ordering.
2. Only accept a new number if it is smaller than the heap head.

Standalone code illustrating the mechanism, not yet including input validation:

~~~java
PriorityQueue<Integer> heap =
        new PriorityQueue<>(Comparator.reverseOrder());

for (int value : input) {
    if (heap.size() < k) {
        heap.offer(value);
    } else if (value < heap.peek()) {
        heap.poll();
        heap.offer(value);
    }
}
~~~

This snippet assumes `input` is present and `k > 0`. If you only reverse the comparator while keeping the same comparison sign from the K-largest case, the algorithm will accept the wrong candidates.

With the same sequence and K = 3, the final group is `[1, 2, 4]`. A valid max-heap:

~~~text
       4
      / \
     1   2
~~~

The heap head equal to 4 is the third smallest number in the data read so far once three elements have been seen. It is not the smallest number; the smallest number is the best element, whereas the heap head is placed at the weakest element to serve replacement.

You can check the comparator direction with two very simple values. If you are looking for the smallest numbers but `peek()` of the group `[1, 2, 4]` is 1, check whether you have put the right element to evict at the head.

## 6. Why Is the Algorithm Correct?

An invariant is a condition that always holds at the boundary between loop iterations. For top-K largest, after reading t elements, the heap must:

- Have exactly `min(K, t)` elements.
- Hold a group containing the largest values among the t elements read so far, counting multiplicities.
- Have no evicted element better than the weakest element currently kept, once the heap is full.

Step-by-step proof:

**Initially:** no elements have been read, and the heap is empty. The largest group of size 0 is empty, so the invariant holds.

**When not yet full:** the number of elements read has not exceeded K. All of them must belong to the result group, so adding the new element is correct.

**When full and x is not greater than the threshold:** there are already K kept elements that are all greater than or equal to the threshold, and therefore all greater than or equal to x. There is no need to accept x to have K largest values. If x equals the threshold, replacing or not replacing may change the identity of the occurrence, but does not change the multiset of selected values.

**When full and x is greater than the threshold:** x is better than the weakest element in the group. Removing one element at the threshold and adding x yields a better group. Elements evicted earlier cannot suddenly surpass the current candidates just because x was added; old values do not change. The new group continues to be a valid top-K selection.

When the input ends, t = N, so the heap holds `min(K, N)` largest elements. Changing greater-than to less-than and swapping the heap type gives the symmetric proof for top-K smallest.

This invariant is stronger than "the heap never exceeds K." An algorithm can keep exactly K elements yet choose the wrong K elements. For example, keeping the K largest numbers in a max-heap and calling `poll()` whenever it overflows will evict the best element itself.

## 7. Two Update Styles and the Mistake of Choosing the Wrong Heap

There are two common ways to write K-largest.

**Threshold-check-first style:** when full, only `poll()` and then `offer()` if the new number is better than the threshold. The heap never exceeds K elements at any point in the loop.

**Insert-first, trim-later style:** use a min-heap, insert every element, and remove the smallest element if the size exceeds K.

~~~java
PriorityQueue<Integer> heap = new PriorityQueue<>();
for (int value : input) {
    heap.offer(value);
    if (heap.size() > k) {
        heap.poll();
    }
}
~~~

This is an illustrative snippet requiring `k >= 0`. For K = 0, each number is added and immediately removed; the result is empty, though the entire input is still traversed. For negative K, this snippet does not express a valid contract; negative K must be rejected before the loop.

The insert-first style can temporarily hold K + 1 elements, which is still O(K + 1) auxiliary space. It is short and easy to prove: among K + 1 candidates, remove the smallest number. The threshold-check-first style avoids heap operations for candidates that are guaranteed to be rejected, which is suitable when much of the data is worse than the threshold. Both use a min-heap for K-largest.

Consider the bug of using a max-heap with the insert-first, trim-later style:

~~~text
Data: 7, 2, 9, 8
K: 3
Insert all four numbers into the max-heap.
poll() removes 9.
Remaining: 8, 7, 2.
The correct result must be: 9, 8, 7.
~~~

The bug is not in the max-heap's ability to find the extremum; it finds the largest number accurately. The bug is in throwing away the best element. The choice of heap is only correct when tied to the specific role of `poll()`.

If you choose to keep all N elements and then poll K times, K-largest can use a max-heap. In that case, `poll()` serves to emit the best results, not to trim the candidate group. The two designs have different purposes and different memory usage.

## 8. Generalization: Result Order and Heap Order

With object data, writing two nearly identical algorithms makes it easy to flip a sign by mistake. We can unify them with a `Comparator` called `bestFirst`:

~~~text
bestFirst.compare(a, b) < 0  means a is better than b.
bestFirst.compare(a, b) > 0  means a is worse than b.
bestFirst.compare(a, b) == 0 means tied according to the chosen criteria.
~~~

`bestFirst` is also the sort order for the final output: the best element comes first.

To put the weakest element at the head of the heap, use the reverse order of the entire `bestFirst`:

~~~java
PriorityQueue<T> heap = new PriorityQueue<>(bestFirst.reversed());
~~~

When the heap is full, the unified check is:

~~~java
if (bestFirst.compare(value, heap.peek()) < 0) {
    heap.poll();
    heap.offer(value);
}
~~~

A candidate is accepted only if it is better than the heap head according to `bestFirst`. Do not use the heap's reversed comparator in this expression while keeping `< 0`; doing so flips the meaning of "better."

| Integer problem | bestFirst used to sort results | Heap order = bestFirst.reversed() |
| --- | --- | --- |
| K largest | `Comparator.reverseOrder()` | Natural order, min-heap |
| K smallest | `Comparator.naturalOrder()` | Reverse order, max-heap |

The `reversed()` method reverses an ordering; `thenComparing(...)` adds a secondary criterion when earlier criteria do not break a tie. These combinators keep comparison code more readable than manually negating arithmetic expressions. [Comparator Documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

### Ties and Record Identity

Suppose each candidate has an `id` and a `score`. Requirement: higher score comes first; if scores are equal, the lexicographically smaller `id` comes first.

~~~java
Comparator<Candidate> bestFirst = Comparator
        .comparingInt(Candidate::score).reversed()
        .thenComparing(Candidate::id);
~~~

The result order is descending score, ascending `id`. The heap order is the reverse of the entire chain above, namely ascending score and, when scores tie, descending `id`. Thus, within the 90-score group consisting of A, B, and C, record C is the weakest candidate when we want to keep the smaller IDs.

With the data `C:90, B:90, A:90, D:70, E:100` and K = 3, the result is `[E:100, A:90, B:90]`.

If we only compare scores, A, B, and C tie. The result may still be right by score, but the identities of the kept records have no stability guarantee. Skipping candidates equal to the threshold does not turn a heap into a stable structure: when a higher score arrives, the heap can pick any tied record at the head to evict.

If you need to prefer records that arrived earlier on a tie, attach an increasing arrival sequence number to each record and include it as a secondary criterion. If you want results independent of input order, use a stable identifier as the secondary criterion. These two requirements are not the same.

The keys used for ranking should be immutable while inside the heap. Directly mutating `score` on an already-inserted object does not re-sort the heap. A comparator that depends on configuration changing mid-loop also breaks the threshold argument.

### Do Not Use Subtraction to Reverse Order

Avoid:

~~~java
Comparator<Integer> unsafe = (a, b) -> b - a;
~~~

For example, `b = Integer.MAX_VALUE` and `a = -1` causes the subtraction to overflow the `int` range. The overflowed result can have the wrong sign, leading to an unintended comparison.

Use `Comparator.reverseOrder()`, `Integer.compare(b, a)`, or `Comparator.comparingInt(...)`. When reversing an existing comparator, use `reversed()`; do not write `-comparator.compare(a, b)` because the return value can be `Integer.MIN_VALUE`. [Integer.compare Documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#compare(int,int)).

## 9. Complete Java 17+ Program

The file `TopKHeapDemo.java` below provides a generic method that works with `Iterable`. It returns results sorted by `bestFirst`, does not modify the input structure, does not require knowing N in advance, and does not pre-allocate an array of K slots.

Contract of `topK`:

- `k < 0`: throws `IllegalArgumentException`.
- `k == 0`: returns an empty list without iterating over source elements.
- `k > N`: returns all N elements in the requested order.
- `input` and `bestFirst` must be non-`null`, even when K = 0.
- For K > 0, each read element must be non-`null` and the comparator must be able to compare them.
- Duplicate elements are counted per occurrence; the method does not deduplicate.
- The result is a list of selected values; there is no guarantee about the mutability of the returned list. In particular, the K = 0 branch uses `List.of()`.

The verification snippet compares the result against sorting a full copy and taking up to K elements. It tests both ranking directions, duplicate data, negative numbers, an empty sequence, K greater than N, and numbers at the `int` boundaries. This is a correctness check of the result, not a speed benchmark.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Random;

public class TopKHeapDemo {
    record Candidate(String id, int score) {
        @Override
        public String toString() {
            return id + ":" + score;
        }
    }

    static <T> List<T> topK(
            Iterable<? extends T> input,
            int k,
            Comparator<? super T> bestFirst) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(bestFirst, "bestFirst");
        if (k < 0) {
            throw new IllegalArgumentException("k must be >= 0");
        }
        if (k == 0) {
            return List.of();
        }

        PriorityQueue<T> heap = new PriorityQueue<>(bestFirst.reversed());
        for (T value : input) {
            Objects.requireNonNull(value, "element");
            if (heap.size() < k) {
                heap.offer(value);
            } else if (bestFirst.compare(value, heap.peek()) < 0) {
                heap.poll();
                heap.offer(value);
            }
        }
        List<T> result = new ArrayList<>(heap);
        result.sort(bestFirst);
        return result;
    }

    static void keepLargest(PriorityQueue<Integer> heap, int value, int k) {
        if (heap.size() < k) {
            heap.offer(value);
        } else if (value > heap.peek()) {
            heap.poll();
            heap.offer(value);
        }
    }

    static List<Integer> descendingSnapshot(PriorityQueue<Integer> heap) {
        List<Integer> copy = new ArrayList<>(heap);
        copy.sort(Comparator.reverseOrder());
        return copy;
    }

    static List<Integer> expected(
            List<Integer> input, int k, Comparator<Integer> order) {
        List<Integer> copy = new ArrayList<>(input);
        copy.sort(order);
        return new ArrayList<>(copy.subList(0, Math.min(k, copy.size())));
    }

    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("top-K mismatch");
        }
    }

    static int selfCheck() {
        Random random = new Random(20261019L);
        int checks = 0;
        for (int test = 0; test < 250; test++) {
            int n = random.nextInt(25);
            int k = random.nextInt(31);
            List<Integer> input = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                input.add(random.nextInt(21) - 10);
            }
            List<Integer> before = new ArrayList<>(input);
            for (Comparator<Integer> order : List.of(
                    Comparator.<Integer>naturalOrder(),
                    Comparator.<Integer>reverseOrder())) {
                check(topK(input, k, order).equals(expected(input, k, order)));
                check(input.equals(before));
                checks++;
            }
        }

        List<Integer> extremes = List.of(
                Integer.MIN_VALUE, 0, Integer.MAX_VALUE, -1, 1);
        for (int k = 0; k <= 6; k++) {
            for (Comparator<Integer> order : List.of(
                    Comparator.<Integer>naturalOrder(),
                    Comparator.<Integer>reverseOrder())) {
                check(topK(extremes, k, order).equals(expected(extremes, k, order)));
                checks++;
            }
        }
        return checks;
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(7, 2, 9, 4, 9, 1, 8, 5);
        List<Integer> before = new ArrayList<>(input);
        PriorityQueue<Integer> heap = new PriorityQueue<>();
        int step = 0;
        for (int value : input) {
            keepLargest(heap, value, 3);
            System.out.println("step=" + (++step)
                    + " value=" + value
                    + " kept=" + descendingSnapshot(heap)
                    + " boundary=" + heap.peek());
        }
        System.out.println("largest 3=" + topK(input, 3, Comparator.reverseOrder()));
        System.out.println("smallest 3=" + topK(input, 3, Comparator.naturalOrder()));
        System.out.println("source unchanged=" + input.equals(before));
        System.out.println("k=0=" + topK(input, 0, Comparator.reverseOrder()));
        System.out.println("k>n=" + topK(List.of(4, 1), 5, Comparator.reverseOrder()));
        System.out.println("empty=" + topK(List.<Integer>of(), 3, Comparator.naturalOrder()));
        System.out.println("duplicates="
                + topK(List.of(9, 9, 9, 8), 2, Comparator.reverseOrder()));

        List<Integer> extremes = List.of(
                Integer.MIN_VALUE, 0, Integer.MAX_VALUE, -1, 1);
        System.out.println("largest extremes="
                + topK(extremes, 2, Comparator.reverseOrder()));
        System.out.println("smallest extremes="
                + topK(extremes, 2, Comparator.naturalOrder()));
        System.out.println("largest 1=" + topK(input, 1, Comparator.reverseOrder()));

        List<Integer> pollOrder = new ArrayList<>();
        PriorityQueue<Integer> copy = new PriorityQueue<>(heap);
        while (!copy.isEmpty()) {
            pollOrder.add(copy.poll());
        }
        System.out.println("min-heap poll order=" + pollOrder);
        System.out.println("original heap size=" + heap.size());

        List<Candidate> candidates = List.of(
                new Candidate("C", 90),
                new Candidate("B", 90),
                new Candidate("A", 90),
                new Candidate("D", 70),
                new Candidate("E", 100));
        Comparator<Candidate> bestFirst = Comparator
                .comparingInt(Candidate::score).reversed()
                .thenComparing(Candidate::id);
        System.out.println("candidates=" + topK(candidates, 3, bestFirst));

        try {
            topK(input, -1, Comparator.naturalOrder());
        } catch (IllegalArgumentException exception) {
            System.out.println("negative k=" + exception.getMessage());
        }
        System.out.println("reference checks=" + selfCheck());
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 TopKHeapDemo.java
java TopKHeapDemo
~~~

The `javac --release 17` command requires JDK 17 or newer that supports this target version. The program uses only APIs and syntax available from Java 17 and earlier.

Exact stdout:

~~~text
step=1 value=7 kept=[7] boundary=7
step=2 value=2 kept=[7, 2] boundary=2
step=3 value=9 kept=[9, 7, 2] boundary=2
step=4 value=4 kept=[9, 7, 4] boundary=4
step=5 value=9 kept=[9, 9, 7] boundary=7
step=6 value=1 kept=[9, 9, 7] boundary=7
step=7 value=8 kept=[9, 9, 8] boundary=8
step=8 value=5 kept=[9, 9, 8] boundary=8
largest 3=[9, 9, 8]
smallest 3=[1, 2, 4]
source unchanged=true
k=0=[]
k>n=[4, 1]
empty=[]
duplicates=[9, 9]
largest extremes=[2147483647, 1]
smallest extremes=[-2147483648, -1]
largest 1=[9]
min-heap poll order=[8, 9, 9]
original heap size=3
candidates=[E:100, A:90, B:90]
negative k=k must be >= 0
reference checks=514
~~~

### Reading the Output to Verify the Mechanism

`kept` is created by copying the heap to a list and sorting in descending order, so it has an easy-to-inspect order. This is an operation for printing the trace; it does not participate in deciding whether to accept or evict an element.

The eight `step` lines match the trace table above. After step 5, the threshold is 7; step 6 sees 1 so the group stays unchanged; step 7 sees 8 so 7 is replaced. The `largest 3` and `smallest 3` lines demonstrate the same generic method with two different comparators.

`min-heap poll order=[8, 9, 9]` highlights a point to distinguish: the heap holds the three largest numbers, yet emits them in ascending order. That is a consequence of placing the weakest candidate at the head. The program polls from a copy, so `original heap size=3` confirms the original heap has not been consumed.

`candidates` checks the secondary criterion by `id`. `reference checks=514` consists of 250 random datasets with both comparison directions, plus seven K values from 0 to 6 on the boundary dataset in both directions. Any discrepancy with the full-sort result throws an `AssertionError` instead of printing a passing check count.

Random datasets help catch reversed-direction and boundary-handling bugs, while the invariant proof explains why the algorithm is correct for data beyond the test cases.


## 10. Outputting Results: Selecting the Right Elements Does Not Mean Having the Right Order

There are two separate tasks: selecting the elements to keep and sorting them in the order you want to present. In `topK`, the heap solves the first task; `result.sort(bestFirst)` solves the second.

Do not treat `heap.toString()`, a `for-each` loop, or `heap.stream().toList()` as a ranked list. They traverse the heap's elements, not simulate a sequence of `poll()` calls. If you need an explicit order, copy and sort or poll repeatedly from the heap. The program chose copy-and-sort to avoid depending on traversal order.

Three common output approaches:

| Output approach | Resulting order | Effect on heap |
| --- | --- | --- |
| Copy to a list then `sort(bestFirst)` | Best first | Preserves heap |
| Repeated `poll()` from the K-bounded heap | Weakest first | Consumes heap |
| Copy the heap, `poll()` all, then reverse the list | Best first, except order among unresolved ties | Preserves original heap |

For example, a min-heap holds the three largest numbers `[9, 9, 8]`. The `poll()` sequence is `8, 9, 9`. If you want descending order, reverse that sequence or sort a copied list in descending order.

When you only need the K-th largest value, you do not need to sort the candidates: after reading at least K elements with K > 0, `peek()` of the min-heap is the answer. For the K-th smallest value, use `peek()` of the max-heap. If the data has fewer than K elements, there is no K-th element even though the heap still has a valid head.

If you only need a group of candidates and order does not matter, you can omit the result-sorting step to save cost. Reflect that in the method contract; do not return an unsorted `List` while describing it as a leaderboard.

The method in this lesson copies object references, not deep copies of objects. Leaving the input structure unmodified does not protect the result from later mutations to those mutable objects themselves.

## 11. Cost Analysis by the Number of Elements Actually Kept

Let N be the number of input elements and M = min(K, N), with K > 0. Temporarily assume reading one element and comparing two elements each cost O(1).

The heap holds at most M elements. Comparing against the threshold does not require searching the entire heap. Moving an element up or down along a root-to-leaf path has a number of levels that grows logarithmically with the heap size; you can compare the `siftUp` and `siftDown` operations in the [OpenJDK 17 PriorityQueue source code](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/PriorityQueue.java).

| Work in the algorithm | Cost |
| --- | --- |
| Read each element and compare against threshold when full | O(1) for the decision part |
| Add or replace a candidate | O(log(M + 1)) by heap analysis |
| Traverse and select across all N elements | O(N log(M + 1)) in the worst case |
| Copy the M result elements | O(M) |
| Sort the M elements into output order | O(M log(M + 1)) |
| Auxiliary memory for heap and returned list | O(M + 1), excluding the input source |

Using `log(M + 1)` keeps the expression accurate for K = 1 as well. Writing "O(N log K)" is common shorthand when `2 <= K <= N`, but plugging in K = 1 and concluding the cost is 0 is wrong. You still have to read N elements to find the extremum.

Since M <= N, the entire method including the result-sorting step is bounded by O(N log(M + 1)) for K > 0, though separating selection cost from output cost clarifies which requirement is spending the work. For K = 0, the given method returns immediately after checking references and K; there is no input traversal.

The threshold-check-first style can perform fewer heap operations than the worst-case bound. If after the heap is full very few candidates are better than the threshold, most elements are only read and compared once. If R is the number of replacements after becoming full, the selection phase can be described in detail as O(N + (M + R) log(M + 1)). This is a way to break down the work, not a guarantee that real-world data always keeps R small.

The analyses above describe the algorithm. The queue's internal array occasionally has to grow in capacity and copy when receiving more elements; do not interpret the logarithmic notation as a promise that every `offer` call has the exact same latency. When the group is full and updates always `poll` before `offer`, the element count does not grow beyond the size already reached.

If the comparator computes an expensive quantity on every comparison, its cost must also be counted. For example, do not re-parse a JSON string or call an external service in every comparison. Precompute the ranking key once, store it alongside an immutable record, and compare keys with clear cost.

O(K) memory is the benefit of the selection process when K is small; it does not erase the memory cost of an N-element list that has already been loaded. For very large data, connect the method to a source that can be iterated one element at a time instead of always building the entire input `List`. Also, an infinite source will not let the method return: to observe top-K continuously, you must maintain an accumulator and provide a separate snapshot operation.

### Trace Printing Cost Is Not the Core Cost

In the demo program, each `step` line calls `descendingSnapshot`, which copies and sorts the kept group for pretty printing. Doing this for every element of a large stream adds roughly O(N K log(K + 1)) cost when K <= N, plus text output cost.

Therefore, do not use the runtime of the trace printing to judge the cost of top-K selection. The `topK` method only sorts once at the end. In production code, you can omit per-step printing or only take snapshots at points that need observation.

## 12. Boundary Contracts and Requirements Commonly Conflated

### K Equal to 0, Negative, or Greater Than N

K = 0 is a request to select no elements. Returning empty immediately is a convenient contract, but it also means not reading and not validating the elements inside the source. A source containing a `null` element will go undetected in this branch; do not describe the method as having validated all data when K = 0.

Negative K does not represent a number of elements to take. Rejecting it with an exception makes the caller's bug obvious. If an application wants to treat negative K as 0, it must publish a different contract rather than letting behavior fall out accidentally from a loop.

K greater than N has two common design choices: return up to K elements, or require at least K elements and fail if there are not enough. The method in this lesson chooses "up to K", so `topK([4, 1], 5, descending)` returns `[4, 1]`. For a "5th largest element" API, the same data must report that it does not exist; you must not take `peek()` and call 1 the 5th largest element.

Do not use `new PriorityQueue<>(k)` as a way to enforce a limit. That parameter is the initial capacity, not the maximum number of elements. It also does not accept 0 and can over-allocate if K comes from external input. The generic method uses the constructor taking a comparator and enforces the element limit via conditions inside the loop.

### Exactly K Elements vs. Taking All Elements Tied at the Threshold

With `[100, 90, 90, 90, 80]` and K = 2:

- "Take up to two elements" can return `[100, 90]`.
- "Take the two highest score levels" returns the levels `[100, 90]`, which are two distinct score values.
- "Take the top two and everyone tied with second place" may have to return four records.

The last requirement no longer bounds the result to K elements. If N records have the same score and policy requires keeping everyone tied at the threshold, the result size can be N. Do not promise O(K) memory for the entire result of that requirement.

Two passes may be needed: the first pass determines the threshold, and the second pass collects all records meeting the threshold, if the source allows re-reading. If only one pass is available and discarded data cannot be recovered, storage must be designed for the tie-handling policy from the start.

### Top-K Distinct Values

`PriorityQueue` is not a `Set`. With `[9, 9, 8, 7]` and K = 3, the occurrence-counting problem returns `[9, 9, 8]`; the distinct-values problem returns `[9, 8, 7]`.

A simple approach for finite data is to deduplicate with a `HashSet` first and then run selection. If there are D distinct values, memory for the deduplication step can be O(D), so you must not continue advertising the whole pipeline as using only O(K) memory.

There are designs that pair a heap with a set of currently kept values to avoid storing every value ever seen. That is an algorithm that must maintain synchronization when adding and evicting candidates; it cannot be achieved just by naming a variable "distinct." Within the scope of this lesson, the runnable method intentionally preserves each occurrence.

### Top-K by Frequency

Finding the three largest numbers is not the same as finding the three most frequent numbers. Frequency is a property of the entire counting process, not the magnitude of an individual number.

A solution for finite data usually has two phases: use a `Map` to count frequencies by value, then rank the value-frequency pairs using a K-bounded heap. Memory includes the frequency map, not just the heap. If you mutate the frequency directly on an object already inside the heap without repairing the structure, the threshold can become wrong.

### Mutating Already-Read Data, Deletions, and Sliding Windows

The top-K invariant in this lesson assumes each ranking value stays fixed and data is only added. When an old score changes or an element leaves a time window, previously evicted candidates may need to come back.

For example, with K = 2, after reading `10, 9, 8`, the heap only holds `[10, 9]`. If 10 expires, the right result is `[9, 8]`, but the heap already discarded 8 and cannot reconstruct it. You cannot solve sliding-window top-K accurately using only the state of this append-only top-K heap.

You must keep additional data, indices, or structures for elements outside the selected group. Switching to a thread-safe priority queue also does not automatically solve missing data or make the sequence "check threshold -> evict -> insert" a single atomic operation.

## 13. Choosing an Approach for Real Requirements

A K-bounded heap is a suitable tool when only a small group is needed and sequential reading is possible. It is not by default the best option for every size of K.

| Situation | Reasonable approach | Additional considerations |
| --- | --- | --- |
| K much smaller than N, single pass needed | K-bounded heap | Step to sort the K results if order is needed |
| K = 1 | Scan keeping a single extremum | O(N) time, O(1) state; a heap is not necessarily needed |
| K close to N and all results needed in order | Sort a copy of the input | Heap is still correct but may offer no benefit |
| Already need to store the full heap to continuously pull the best element | Full-data heap | O(N) memory for the heap; different goal from top-K trimming |
| Array already in memory, only one threshold selection needed | Partition-based selection algorithm may fit | Partitioning scheme, worst case, mutating array, and sorting results |
| Input already sorted in best-first order | Take up to the first K elements | Stop early only when source ordering is guaranteed |

Do not read the first K elements of an unsorted source and stop. Even if the first K numbers are all very large, a better number can still appear at the end. Without additional guarantees on the data, you must examine the entire finite source to conclude the exact top-K.

If you build a full-data heap by calling `offer` element by element, that build step alone is bounded by O(N log(N + 1)), and polling K times costs additional logarithmic operations. Do not confuse that build method with a bulk heapify algorithm that has a different analysis. To decide on a K-bounded heap, the clearest benefit is that the number of kept candidates is only around K when K is small.

Selecting by highest score, shortest distance, or fastest time can use the same generic method. Change `bestFirst` to match the semantics, then check with a pair of examples: whichever record is better must produce a negative `compare` result when passed as the first argument.

For example, with precomputed integer distances where smaller distance is better, `Comparator.comparingInt(Item::distance)` is the result order. The heap must use the reversed order so the farthest distance in the selected group sits at the head. If you compute squared distance from integer coordinates yourself, you must also handle integer overflow in the key calculation before thinking about the heap; a good comparator cannot fix a miscomputed key.

## 14. Common Mistakes and How to Spot Them

| Mistake | Observable symptom | Fix |
| --- | --- | --- |
| Keeping K largest with a max-heap and calling `poll` on overflow | The largest numbers disappear | Put the element to evict at the head: min-heap |
| Changing heap type but forgetting to flip acceptance direction | Worse candidates get added | Compare using a single `bestFirst` |
| Comparing against `peek` when heap is empty | Exception from unboxing `null` | Handle K = 0 and the not-yet-full branch first |
| Always inserting every number without trimming | Result exceeds K, memory grows with N | Maintain the size invariant after each step |
| Using `contains` to deduplicate ad hoc | Changes semantics and adds linear search | Decide explicitly between occurrences vs. distinct values |
| Using `remove(value)` to evict the threshold | Unnecessary search and possible overload confusion | Use `poll()` to remove the heap head |
| Printing the heap directly as a sorted result | Seeing a sequence not in the expected order | Copy then sort, or poll all in a controlled way |
| Calling `poll` on a heap that is still needed later | Size and state are lost | Snapshot a copy before consuming output |
| Comparator using integer subtraction | Fails at boundary values even if small examples pass | Use safe comparison methods |
| Assuming ties automatically preserve arrival order | Identities at the boundary shift | Add a secondary key matching the policy |
| Mutating score key while object is still in the heap | `peek` is no longer the right threshold | Keep keys immutable or design structural updates |
| Treating initial capacity as the K limit | Queue still accepts more than K elements | Enforce the size condition in the algorithm |

A very effective quick check is to use the data `[7, 2, 9, 8]` with K = 3, then test K = 0, K = 1, K > N, a sequence of all equal numbers, and a sequence containing `Integer.MIN_VALUE`/`Integer.MAX_VALUE`. Then compare the sorted results against a simple full-sort solution. Random data should supplement intentional boundary cases.

## 15. Exercises and Solutions

### Exercise 1 — Choose the Heap by the Element to Evict

You need to keep the five products with the highest rating scores. Higher score is better. Use a min-heap or a max-heap if you keep at most five candidates?

**Solution:** use a min-heap by score. Among the five candidates, the product with the lowest score is the weakest candidate; put it at the head to compare against new products. If you need to select by score and then product ID, you must reverse the entire result order to form the heap comparator.

### Exercise 2 — Trace K Smallest

Data `[6, 3, 8, 1, 5, 2]`, K = 3. Write down the kept values after each step and the heap head.

**Solution:** use a max-heap. Present the group in ascending order for readability:

| Number just read | Kept group | Max-heap head |
| --- | --- | --- |
| 6 | [6] | 6 |
| 3 | [3, 6] | 6 |
| 8 | [3, 6, 8] | 8 |
| 1 | [1, 3, 6] | 6 |
| 5 | [1, 3, 5] | 5 |
| 2 | [1, 2, 3] | 3 |

When full, a new candidate must be smaller than the heap head to be accepted. The final answer is `[1, 2, 3]`.

### Exercise 3 — Find a Counterexample for the Wrong-Direction Heap

A program wants to keep the two largest numbers and uses a max-heap; after each insertion, if the size exceeds two, it calls `poll()`. Give a short counterexample.

**Solution:** `[1, 2, 3]`. After the third insertion, the max-heap removes 3 and keeps 1, 2; the right answer must be 3, 2. The algorithm evicted the best element.

### Exercise 4 — The K-th Largest Element

With a min-heap currently holding the three largest numbers of the data read so far, `peek()` equals 8. Can we conclude the third largest value is 8?

**Solution:** yes, if K = 3, at least three elements have been read, the heap maintains the invariant, and duplicate occurrences are counted. If only one or two elements have been read, there is no third largest element. If the problem requires three distinct values, you must verify a different invariant that deduplicates.

### Exercise 5 — Duplicate Values and Ties

Data `[10, 10, 9, 8]`, K = 2. Compare the results of top-K occurrences and top-K distinct values.

**Solution:** occurrences yield `[10, 10]`; distinct values yield `[10, 9]`. `PriorityQueue` does not deduplicate automatically. Merely changing `>` to `>=` does not turn the first problem into the second.

### Exercise 6 — Secondary Criterion at the Boundary

Data `C:90, B:90, A:90, E:100`, K = 2. Requirement: descending score, ascending ID. What is the answer, and which element is weaker between A:90 and B:90?

**Solution:** the answer is `[E:100, A:90]`. Between the two 90-score records, B:90 is weaker than A:90 because ID B comes after ID A. If you only compare scores, the program has no basis to choose A over B under this requirement.

### Exercise 7 — Reverse the Entire Comparator or One Criterion?

Given the result order "descending score, ascending ID." If the heap uses "ascending score, ascending ID," is that correct yet?

**Solution:** not yet. Within a tied-score group, this heap puts smaller IDs at the head, which means putting the better record at the front to be evicted. The right heap must reverse the entire result order: ascending score, descending ID. Using `bestFirst.reversed()` avoids missing the secondary criterion.

### Exercise 8 — Heap Removal Order

A min-heap holds the three largest numbers, with values 12, 8, 10. What does repeated `poll()` return? What should you do to return a descending list while preserving the heap?

**Solution:** the removal sequence is `8, 10, 12`. Copy the elements to a list and sort in descending order, or copy the entire heap, poll everything from the copy, and reverse the list. Do not use `for-each` order as a ranking guarantee.

### Exercise 9 — Does K = 0 Read Elements?

With the `topK` method in this lesson, call K = 0 on a valid source whose inner elements may contain `null`. Does the method detect `null`?

**Solution:** it does not iterate over the source, so it does not detect inner `null` elements. It still checks the `input` and `bestFirst` references before returning empty. If business logic requires validating the entire source even when selecting no results, design a separate validation step or change the contract.

### Exercise 10 — Cost When K Is Very Small

N = one million, K = 10. Do you need to keep all one million elements in the heap? If you only want the tenth largest threshold, do you need to sort the result list?

**Solution:** no need to keep all of them; the bounded heap keeps at most ten elements, while the source's memory depends on how it is read. After reading everything and finishing, the threshold is `peek()` of the min-heap; there is no need to sort the ten elements if you only need the threshold value. You still must read the entire unsorted source to ensure no better number is missed.

### Exercise 11 — Why Can't It Be Reused Directly for a Sliding Window?

K = 2, you have read 10, 9, 8 and only keep 10, 9. When 10 expires, what result is needed and why is the current heap insufficient?

**Solution:** 9, 8 is needed, but 8 was already discarded. The heap cannot infer data that is no longer stored. You need an additional structure for elements in the window and a way to handle expired elements; merely removing 10 from the heap does not complete the problem.

### Exercise 12 — Extending the Cross-Check

Add a check to the program for a list of candidates with equal scores but different IDs, comparing the `topK` result against a copy sorted by `bestFirst` and sliced from the front. Name one thing you cannot conclude from a passing check.

**Solution:** reuse `candidates` and `bestFirst`, create an `ArrayList<Candidate>`, sort it with `bestFirst`, take `subList(0, Math.min(k, size))`, and compare the result lists. Loop K from 0 to greater than the number of candidates to test boundaries as well. Passing does not prove that every business comparator is right, does not measure speed, and does not allow concluding that the heap is stable if the secondary criterion was omitted.

## 16. Self-Check Before Applying

Before writing code, state aloud: "I am keeping up to K best elements according to which order; what is the weakest element in the group; and what condition must a new candidate satisfy to replace it?" If these three statements are inconsistent, choosing a heap by intuition is very easy to get wrong.

When reviewing a solution, check four things separately: does the selected group have the right values and multiplicities; does the size match the K contract; is the result order produced explicitly; and do tie cases have an appropriate policy?

The rule to remember for a K-bounded heap is to put **the weakest currently kept candidate** at the head. For the K largest numbers, that is a min-heap; for the K smallest numbers, that is a max-heap. Result output ordering is handled after the right group has been selected.
