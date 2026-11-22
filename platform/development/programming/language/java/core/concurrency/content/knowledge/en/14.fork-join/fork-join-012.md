# Applied Fork/Join: Array Aggregation, Tree Traversal, and Recursive Computation in Java

## 1. Objective and Context

Many computational problems follow the structure of "**breaking a large problem into independent parts, processing each part, and combining the results**." For example:

- Computing the sum, min/max, or statistics over a large array.
- Computing weighted sums, counting nodes, or aggregating properties of a tree.
- Sorting an array with merge sort, or processing data by region.
- Executing a recursive algorithm whose branches can be computed independently.

In Java, the **Fork/Join Framework** provides `ForkJoinPool` and `ForkJoinTask` to organize this **divide and conquer** pattern. It is especially suitable for **CPU-bound** work with independent branches that can be split into chunks large enough to offset the overhead of task creation and scheduling.

**Core idea:**

```text
                  Initial problem
                        |
                      split
                  /           \
             problem A       problem B
                |               |
        process or split  process or split
                \               /
                 combine results
                        |
                      result
```

A typical Fork/Join task has a **splitting threshold**. If the piece of work is smaller than the threshold, the task computes **sequentially**; if larger, it splits into branches. Without a reasonable threshold, splitting every element or every node into its own task can take more time than computing sequentially.

This lesson is part of the **Java Advance - concurrency → Fork/Join** module, using only **general Java concurrency**, with no dependency on Spring or any framework.

## 2. Essential API Components

| Component | Role |
| --- | --- |
| `ForkJoinPool` | Worker pool optimized for executing Fork/Join-style tasks, with work stealing support |
| `ForkJoinTask<V>` | Base class representing a unit of work producing a result of type `V` |
| `RecursiveTask<V>` | Recursive task **with a return value**; implements `compute()` |
| `RecursiveAction` | Recursive task **with no return value**; implements `compute()` |
| `fork()` | Schedules a task so that it can run asynchronously |
| `join()` | Retrieves the task result, waiting if it is not yet complete |
| `compute()` | Executes the task's work directly in the thread calling `compute()` |
| `invoke()`, `ForkJoinPool.invoke(task)` | Executes the task and waits for its result |
| `invokeAll(...)` | Executes a group of Fork/Join tasks and waits for them to complete per contract |

**Important distinction:** `fork()` generally **does not return the computed result of the task**; it returns the task itself so it can be `join()`ed later. A normal `compute()` call executes the task immediately and does not mean creating another thread on its own.

### RecursiveTask Pattern

```java
class Task extends RecursiveTask<Long> {
    @Override
    protected Long compute() {
        if (isSmallEnough()) {
            return computeSequentially();
        }

        Task left = splitLeft();
        Task right = splitRight();

        left.fork();
        Long rightValue = right.compute();
        Long leftValue = left.join();

        return combine(leftValue, rightValue);
    }
}
```

This is an **illustrative skeleton**, with helpers defined by the application. The meaning of this ordering:

1. `left.fork()`: submits the left branch to the Fork/Join scheduling mechanism so another worker can pick it up.
2. `right.compute()`: the current worker processes the right branch itself, avoiding simply spawning tasks and waiting.
3. `left.join()`: retrieves the left branch's result when needed.
4. `combine`: combines the two completed results.

**Avoid writing** `left.fork(); left.join(); right.compute();` when you want both branches to have a chance to run in parallel: calling `join()` immediately after `fork()` can force the current thread to wait for the left branch before working on the right branch, losing part of the parallelism opportunity.

## 3. Work Stealing Mechanism, Not "One Thread per Task"

`ForkJoinPool` manages a group of workers. Workers spawn many small tasks, and under suitable conditions, an idle worker can **take work from another worker's queue**. This is **work stealing**.

```text
Worker 1                         Worker 2
--------                         --------
root task
  fork(task A)  ----> queue        may steal task A
  compute(B)                      compute(A)
  join(A)     <---- result        completes A
  combine(A, B)
```

This diagram only illustrates one possible interleaving; there is **no guarantee** that task A will definitely be executed by worker 2. In a real system, worker 1 might complete A itself, or another worker might pick up the task.

**Why does it fit irregular recursive problems?** Branches can vary in size. Work stealing helps distribute the remaining work instead of hardcoding "worker 1 handles the left half, worker 2 handles the right half."

However:

- Work stealing does not make an incorrect algorithm correct.
- Work that is too small causes task-splitting, scheduling, and synchronization overhead to dominate.
- A very long sequential branch can become a **critical path** forcing many cores to wait.
- Blocking workers with long I/O or `Thread.sleep()` is not an ideal workload.
- There is no guarantee on branch execution order; results must be designed to be order-independent.

## 4. Application 1: Array Sum Using RecursiveTask<Long>

Problem: given a `long[]` array with many elements, compute its sum. Addition is a **reduction** operation with identity element `0`, so we can sum disjoint segments and add them together:

\[
\operatorname{sum}(a[l:r]) =
\operatorname{sum}(a[l:m]) +
\operatorname{sum}(a[m:r])
\]

With `m = (l + r) / 2`. Use the **half-open** interval convention `[from, to)` to avoid counting the element at the split point twice.

### Standalone Runnable Code

Create the file `ForkJoinArraySumDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinArraySumDemo {
    private static final class SumTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 2;

        private final long[] values;
        private final int from;
        private final int to;

        SumTask(long[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            int length = to - from;

            if (length <= THRESHOLD) {
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum += values[i];
                }
                return sum;
            }

            int mid = from + length / 2;
            SumTask left = new SumTask(values, from, mid);
            SumTask right = new SumTask(values, mid, to);

            left.fork();
            long rightResult = right.compute();
            long leftResult = left.join();

            return leftResult + rightResult;
        }
    }

    private static long sequentialSum(long[] values) {
        long sum = 0;
        for (long value : values) {
            sum += value;
        }
        return sum;
    }

    public static void main(String[] args) {
        long[] values = {1, 2, 3, 4, 5, 6, 7, 8};
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            long total = pool.invoke(
                    new SumTask(values, 0, values.length));

            System.out.println("parallel sum=" + total);
            System.out.println("sequential sum="
                    + sequentialSum(values));
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac ForkJoinArraySumDemo.java
java ForkJoinArraySumDemo
```

Output:

```text
parallel sum=36
sequential sum=36
```

### Step-by-Step Breakdown of the Split

With an 8-element array and threshold `2`:

```text
[1,2,3,4,5,6,7,8]           sum = 36
         /      \
[1,2,3,4]                  [5,6,7,8]
   /   \                      /   \
[1,2] [3,4]                [5,6] [7,8]
  3     7                    11    15
     10                          26
                  36
```

Segments of length ≤ 2 are computed with a regular `for` loop; larger segments continue splitting. Each `SumTask` only needs to hold **the array reference and two indices**, without copying array halves into new `long[]` arrays.

### Why Is Addition Free of Data Races?

Workers **only read** the input array. Each task uses a **local** `sum` variable inside `compute()` or holds its own `Long` return result. There is no mutable global variable like `static long total` that every worker updates concurrently with `+=`.

Calling `join()` ensures the caller only combines results after the corresponding branch finishes, along with the synchronization/memory visibility guarantees provided by the Fork/Join API. If the array must be read consistently, writers must not modify the array concurrently during summation without an appropriate synchronization protocol.

### Edge Cases

- **Empty array:** `length = 0`, the sequential branch returns `0`.
- **Single-element array:** returns the element's value itself.
- **Non-overlapping splits:** `[from, mid)` and `[mid, to)`, no double-counting or missed elements.
- **Negative numbers:** addition still works.
- **Overflow:** `long` can still overflow if the sum exceeds the `long` range. Use `Math.addExact` or `BigInteger` if the domain requires overflow detection or cannot tolerate wrap-around.
- **Mutable array:** sharing a reference to the same array is safe **for concurrent reads**, which does not mean its contents can be modified at any time.

### Choosing a Threshold for Real-World Arrays

`THRESHOLD=2` was chosen to keep the diagram easy to follow, **not as an optimal production value**. With millions of elements, a threshold that is too small creates a huge number of tasks. Test larger chunk sizes, measure with benchmarks, and consider the cost per element.

If each element only involves adding a `long`, the work per chunk is very cheap, so chunks must be large enough to offset Fork/Join overhead. If each element requires heavy computation, a smaller chunk size may be reasonable.

## 5. General Pattern: Map–Reduce on Arrays

Array summation can be generalized into:

1. **Map:** transform each element, for example `x -> x * x`.
2. **Reduce:** combine results, for example addition.
3. **Identity:** neutral value, for example `0` for sum, `1` for product.

A task computing the sum of squares can use a leaf like:

```java
long sum = 0;
for (int i = from; i < to; i++) {
    long x = values[i];
    sum += x * x;
}
return sum;
```

This is an **illustrative snippet** inside `compute()`, with `from`, `to`, and `values` managed by the task class. Branches still add results together as in the previous example.

For a parallel reduction to produce reliable results, pay attention to the **associativity** of the combining operation. For integer addition within the non-overflow range, different groupings of terms yield the same mathematical result. For `double`/`float`, floating-point addition is **not strictly associative**:

\[
(a+b)+c \ne a+(b+c)
\]

in some cases due to rounding, infinity, NaN, and precision loss. Therefore, a parallel reduction may produce slightly different results compared to a sequential loop or across different work-grouping strategies.

If exact financial results are required, consider `BigDecimal`, scaled integer values, or an appropriate numeric type/arithmetic policy. If bitwise reproducibility is required, design a fixed summation order and a stable algorithm according to requirements, rather than assuming every parallel reduction is bitwise identical.

## 6. Application 2: Aggregating Nodes in a Tree

A tree can contain a large number of nodes. At each node, if the left and right branches are **independent**, the total weight of the tree is:

\[
S(node)=value(node)+S(left)+S(right)
\]

For an empty tree, `S(null)=0`.

```text
          10
         /  \
        5    7
       / \    \
      2   3    4

Sum = 10 + 5 + 7 + 2 + 3 + 4 = 31
```

Trees differ from arrays in that branches can be **unbalanced**. Fork/Join can leverage work stealing when one branch is larger than another. However, forking a task for **every node** is usually inefficient: leaf nodes are too small, the task count explodes, and a very deep tree can cause deep recursion stacks.

A useful technique is setting a **parallel depth limit**: beyond a certain depth, remaining subtrees are computed sequentially. This is a simple threshold; for real trees, you can base it on **estimated node count**, estimated subtree work, or profiling.

### Standalone Runnable Code

Create the file `ForkJoinTreeSumDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinTreeSumDemo {
    record Node(long value, Node left, Node right) {}

    static long sequential(Node node) {
        if (node == null) {
            return 0;
        }
        return node.value()
                + sequential(node.left())
                + sequential(node.right());
    }

    static final class TreeSumTask extends RecursiveTask<Long> {
        private final Node node;
        private final int parallelDepth;

        TreeSumTask(Node node, int parallelDepth) {
            this.node = node;
            this.parallelDepth = parallelDepth;
        }

        @Override
        protected Long compute() {
            if (node == null) {
                return 0L;
            }

            if (parallelDepth <= 0
                    || (node.left() == null && node.right() == null)) {
                return sequential(node);
            }

            if (node.left() == null) {
                return node.value() + new TreeSumTask(
                        node.right(), parallelDepth - 1).compute();
            }

            if (node.right() == null) {
                return node.value() + new TreeSumTask(
                        node.left(), parallelDepth - 1).compute();
            }

            TreeSumTask left = new TreeSumTask(
                    node.left(), parallelDepth - 1);
            TreeSumTask right = new TreeSumTask(
                    node.right(), parallelDepth - 1);

            left.fork();
            long rightValue = right.compute();
            long leftValue = left.join();

            return node.value() + leftValue + rightValue;
        }
    }

    public static void main(String[] args) {
        Node tree = new Node(
                10,
                new Node(5,
                        new Node(2, null, null),
                        new Node(3, null, null)),
                new Node(7,
                        null,
                        new Node(4, null, null)));

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long result = pool.invoke(new TreeSumTask(tree, 2));
            System.out.println("parallel tree sum=" + result);
            System.out.println("sequential tree sum="
                    + sequential(tree));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinTreeSumDemo.java
java ForkJoinTreeSumDemo
```

Output:

```text
parallel tree sum=31
sequential tree sum=31
```

### Why Is the Tree Task Correct?

- `Node` is a Java `record` containing `value`, `left`, and `right`. **In this example**, the nodes are constructed before submitting the task and are not modified during computation; a record does not automatically guarantee deep immutability for all data types.
- Each task only **reads** a subtree, so there are no multiple writers contending on `value`.
- Only when **both branches have data** and `parallelDepth > 0` does the code fork one branch and compute the other.
- If there is only one child, the code continues computing on the current thread, avoiding creating a forked task just to wait for it.
- Once the depth limit is reached, `sequential(node)` processes the rest sequentially, bounding task tree expansion.
- After `left.join()`, the left branch's result is ready to be added to the right branch's result.

### Trees Are Not Always Pure Trees

Many real-world models are **graphs** or **DAGs** with shared nodes:

```text
   Root
   /  \
  A    B
   \  /
    C    (C is referenced by both A and B)
```

If we count nodes using the function above, node C could be counted **twice**, because the code recurses by **path**, without deduplicating nodes. If the graph has cycles, recursion can even run infinitely or cause a `StackOverflowError`.

To handle graphs, business semantics must be clearly defined:

- **Sum by path:** a node appearing on two paths being counted twice may be intentional.
- **Sum by unique node:** requires a parallel-safe visited/deduplication mechanism.
- **Graph with cycles:** requires cycle detection and a termination rule.
- **DAG:** memoization of immutable subproblems can be used, but contention when computing the same node concurrently must be managed.
- If aggregation depends on **traversal order**, a specific ordering contract is required rather than assuming work stealing preserves order.

Do not pass a shared `HashSet<Node> visited` to all workers and mutate it concurrently without synchronization. That causes data races and wrong results; choose an appropriate concurrent structure and atomic protocol, or handle deduplication in a separate phase.

## 7. Irregular Problems: Skewed Trees and Unbalanced Splits

With arrays, splitting by index in half usually yields two parts of nearly equal size. With trees, one subtree might contain millions of nodes while the other is just a single leaf.

```text
                   Root
                 /      \
       large subtree    leaf node
        /      \
      ...      ...
```

Work stealing can help workers pick up available tasks in the large branch. But if the algorithm only forks two branches **right at the root** and then computes all nodes of the large branch sequentially, other workers can still sit idle. The threshold and splitting strategy must generate **enough independent tasks**.

A fixed fork depth, such as `parallelDepth=2`, creates at most a bounded number of tasks, which may be unevenly distributed on a skewed tree. Possible improvements:

- Pre-store subtree sizes (`size`) if the tree is immutable and data construction allows it.
- Fork only when the estimated size exceeds the threshold.
- Split a large branch into independent frontiers/subtrees and submit them to the pool.
- Use an iterative traversal with an explicit stack if the tree can be very deep; standard Java recursion can hit `StackOverflowError`.
- Avoid forking a task for a very cheap leaf.
- Measure throughput and workload balance rather than relying on nominal core count.

**Do not assume Fork/Join automatically splits an indivisible sequential job.** The pool only schedules the tasks that the algorithm actually creates.

## 8. Application 3: Parallel Merge Sort Using RecursiveAction

`RecursiveTask<T>` is suitable when a task returns a value. However, for a sorting algorithm that **modifies the input array in place**, we can use `RecursiveAction` (no return value) because the task's effect is to leave a segment of the array sorted.

**Merge sort**:

1. If the segment is small, use `Arrays.sort` sequentially.
2. If large, split the segment into left and right.
3. Sort the two disjoint segments using subtasks.
4. Wait for both branches to finish.
5. Merge the two sorted segments into the corresponding region of an auxiliary array.
6. Copy the merged region back into the original array.

**Common pitfall:** If the parent starts merging before both subtasks finish sorting, the result will be wrong. `invokeAll`/`join` is the required synchronization boundary.

### Standalone Runnable Code

Create the file `ForkJoinMergeSortDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;

public class ForkJoinMergeSortDemo {
    private static final class SortTask extends RecursiveAction {
        private static final int THRESHOLD = 3;

        private final int[] values;
        private final int[] temp;
        private final int from;
        private final int to;

        SortTask(int[] values, int[] temp, int from, int to) {
            this.values = values;
            this.temp = temp;
            this.from = from;
            this.to = to;
        }

        @Override
        protected void compute() {
            int length = to - from;

            if (length <= THRESHOLD) {
                Arrays.sort(values, from, to);
                return;
            }

            int mid = from + length / 2;
            SortTask left = new SortTask(values, temp, from, mid);
            SortTask right = new SortTask(values, temp, mid, to);

            invokeAll(left, right);

            int i = from;
            int j = mid;
            int k = from;

            while (i < mid && j < to) {
                if (values[i] <= values[j]) {
                    temp[k++] = values[i++];
                } else {
                    temp[k++] = values[j++];
                }
            }
            while (i < mid) {
                temp[k++] = values[i++];
            }
            while (j < to) {
                temp[k++] = values[j++];
            }

            System.arraycopy(temp, from, values, from, length);
        }
    }

    public static void main(String[] args) {
        int[] values = {9, 4, 7, 2, 8, 1, 3, 6, 5};
        int[] temp = new int[values.length];

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            pool.invoke(new SortTask(
                    values, temp, 0, values.length));

            System.out.println("sorted="
                    + Arrays.toString(values));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinMergeSortDemo.java
java ForkJoinMergeSortDemo
```

Output:

```text
sorted=[1, 2, 3, 4, 5, 6, 7, 8, 9]
```

### Why Is Sharing Two Arrays Across Multiple Tasks Safe?

Every task holds references to the same `values` and `temp`, but they have **index-range ownership**:

- The left subtask may only modify `[from, mid)`.
- The right subtask may only modify `[mid, to)`.
- The two regions are **disjoint**, so the two subtasks never write to the same array slot.
- The parent only merges after `invokeAll(left, right)` completes; by then, both segments are sorted.
- The parent only writes to `temp[from:to)` and copies back to `values[from:to)` after its children complete. Tasks in other subtrees operate on disjoint ranges.

This is an example of a **shared array with clear write ownership partitioning**: you do not necessarily have to wrap every element in `AtomicIntegerArray` or use `synchronized` for every assignment. The correctness condition is that tasks must have **non-overlapping write regions** until the parent joins.

### Properties and Overhead

Merge sort has total work of approximately `O(n log n)`. With this implementation, each parent merges its segment **sequentially** after its children finish sorting, so not every phase is fully parallelized. An auxiliary array of size `O(n)` is used for merging; tasks also incur additional overhead.

**`THRESHOLD=3` is for illustration only.** For real arrays, benchmark larger thresholds. `Arrays.parallelSort`, built into Java, is an option to consider before implementing your own parallel merge sort for production; it is designed and tested for array sorting, whereas custom code requires proving correctness, stability, memory usage, and performance.

## 9. Application 4: Recursive Computation with Fibonacci and What to Avoid

Fibonacci is often used to illustrate two-branch recursion:

\[
F(n)=F(n-1)+F(n-2), \quad F(0)=0,\ F(1)=1.
\]

At first glance, the branches can be forked independently. However, **naive recursive Fibonacci is a bad performance example** because the same `F(k)` values are recomputed over and over again:

```text
                F(5)
              /      \
           F(4)      F(3)
           /  \      /  \
        F(3) F(2)  F(2) F(1)
        ...
```

`F(3)`, `F(2)`, and other subproblems repeat. Fork/Join does not perform memoization automatically and does not turn an exponential-time algorithm into a linear one.

We can still write a **hybrid example with a threshold** to see the mechanism, but it must be stated clearly: **this is a lesson on recursive tasks, not an optimal way to compute Fibonacci**.

### Standalone Runnable Code

Create the file `ForkJoinFibonacciDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinFibonacciDemo {
    private static long sequentialFib(int n) {
        long a = 0;
        long b = 1;

        for (int i = 0; i < n; i++) {
            long next = a + b;
            a = b;
            b = next;
        }
        return a;
    }

    private static final class FibTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 16;
        private final int n;

        FibTask(int n) {
            this.n = n;
        }

        @Override
        protected Long compute() {
            if (n <= THRESHOLD) {
                return sequentialFib(n);
            }

            FibTask left = new FibTask(n - 1);
            FibTask right = new FibTask(n - 2);

            left.fork();
            long rightValue = right.compute();
            long leftValue = left.join();

            return leftValue + rightValue;
        }
    }

    public static void main(String[] args) {
        int n = 20;
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long result = pool.invoke(new FibTask(n));
            System.out.println("fork/join F(20)=" + result);
            System.out.println("sequential F(20)="
                    + sequentialFib(n));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinFibonacciDemo.java
java ForkJoinFibonacciDemo
```

Output:

```text
fork/join F(20)=6765
sequential F(20)=6765
```

### Why Is This Not an Optimal Algorithm?

`FibTask` splits into `F(n-1)` and `F(n-2)` until `n <= THRESHOLD`. In the splits above the threshold, many subproblems are repeated. The sequential two-variable approach in `sequentialFib` runs in `O(n)` time and `O(1)` memory; for simply computing `F(n)`, this approach is usually easier to understand, has lower overhead, and is more efficient.

Other optimization approaches:

- **Dynamic programming/memoization:** each `F(k)` is computed only once.
- **Fast doubling:** computes Fibonacci using index-halving formulas, with complexity of approximately `O(log n)` arithmetic steps (excluding big-integer cost).
- **BigInteger:** avoids `long` overflow when `n` is large; `F(93)` already exceeds the maximum positive value of `long`.

If a real recursive problem has **independent branches without overlapping subproblems** or very high per-branch cost, Fork/Join has a much better chance of providing benefits than naive Fibonacci.

## 10. Choosing Between RecursiveTask and RecursiveAction

**Choose `RecursiveTask<V>` when each part returns a value to be reduced:**

- Array sum, node count, tree min/max.
- Computing a hash or a sub-report.
- Counting paths in a tree with a clear combining rule.
- An immutable value combined after `join()`.

**Choose `RecursiveAction` when each part performs a side effect on a data region with independent ownership:**

- Sorting a disjoint array segment.
- Transforming multiple independent regions of a buffer.
- Updating tiles of a matrix when tiles do not overlap.
- Traversing and writing results into partitioned output regions.

**Warning:** `RecursiveAction` having no return value **does not mean side effects are automatically thread-safe**. If tasks concurrently write to an `ArrayList` or an unsynchronized `long total` variable, that is still a data race. With `RecursiveTask`, returning results from tasks often helps reduce the need for shared mutable state.

## 11. Splitting by Range Instead of Copying Data

A good design usually passes **a data reference + indices**:

```java
new SumTask(values, from, mid);
new SumTask(values, mid, to);
```

This is the pattern shown in `ForkJoinArraySumDemo`.

A choice prone to performance bugs:

```java
long[] left = Arrays.copyOfRange(values, from, mid);
long[] right = Arrays.copyOfRange(values, mid, to);
```

If every recursion level copies data, total allocation, temporary memory, and copying overhead can become huge, wiping out parallelism gains. Using ranges avoids allocating subarrays; task creation overhead still exists, but it is much lower than copying the entire dataset across multiple levels.

**Not all copying is wrong.** When input data is being modified by other writers, a snapshot/copy may be necessary to ensure consistency. However, copying should be done **intentionally at ownership boundaries**, rather than indiscriminately at every split.

## 12. Threshold: The Most Important Variable in the Problem

A good threshold must balance:

- **Too small:** many tasks, high fork/join, scheduling, object allocation, and GC overhead.
- **Too large:** few tasks, not enough work to distribute evenly across cores, losing work stealing opportunities.
- **Just right:** leaf work is heavy enough for parallel execution to offset scheduling overhead; enough useful tasks exist for distribution.

A practical starting approach:

1. Measure a correct **sequential** version and keep it as a baseline.
2. Choose a sufficiently large input size.
3. Test several meaningful thresholds, such as chunks ranging from a few thousand to hundreds of thousands of elements depending on the operation.
4. Measure throughput, latency, and allocation with a reliable benchmark.
5. Observe actual core count, memory bandwidth, GC, and branch balance.
6. Choose the threshold per workload; **do not hardcode one number for all algorithms**.

In the array sum example, each leaf only performs a few additions, so the production threshold needs to be **much larger than 2** for most workloads. In image processing or heavy per-pixel operations, the threshold may differ.

### Threshold by Size or by Depth?

- **Arrays:** `to - from <= THRESHOLD` is a direct, stable criterion.
- **Balanced trees:** limiting parallel depth can help cap the number of tasks.
- **Unbalanced trees:** depth can be a very poor predictor of workload; prefer estimating subtree size/work if available.
- **Recursion with overlapping subproblems:** a threshold does not fix the repetitive nature of the algorithm; change the algorithm or use memoization.

## 13. Amdahl's Law and the Limits of "Adding More Threads"

If an algorithm has a sequential fraction `s` and a parallelizable fraction `1-s`, ideal speedup is bounded by the sequential part. Reference formula:

\[
S(p)\le \frac{1}{s+\frac{1-s}{p}}
\]

where `p` is the effective number of workers.

Suppose about `20%` of the work cannot be parallelized; even if the number of workers grows very large, ideal speedup cannot exceed roughly `5×`, before even accounting for overhead.

**In practice**, fork/join overhead, cache misses, memory bandwidth, GC, and data locality reduce speedup even further. Increasing `ForkJoinPool(64)` on a machine with few cores or a memory-bound workload can be slower than `ForkJoinPool(4)`.

**Measuring performance:** on the JVM, benchmarks require JIT warm-up, dead-code elimination prevention, identical input sizes, multiple runs, and correctness verification. Dedicated tools like JMH are usually far more reliable than a single `System.nanoTime()` before/after in `main`. Do not use small `8`-element example outputs to claim Fork/Join is faster than sequential execution.

## 14. ForkJoinPool.commonPool() vs. Dedicated Pools

Java provides `ForkJoinPool.commonPool()`, a shared pool used by many APIs, including parallel streams and asynchronous operations by default.

Example:

```java
long answer = ForkJoinPool.commonPool()
        .invoke(new SumTask(values, 0, values.length));
```

This is an **illustrative snippet** using `SumTask` from the earlier example. When using the common pool, **do not call `shutdown()` as if the application owns that pool**. The pool is shared by the JVM and libraries, and its lifecycle management contract differs from an application-created `new ForkJoinPool(...)`.

When creating a dedicated pool:

```java
ForkJoinPool pool = new ForkJoinPool(4);
try {
    Result result = pool.invoke(task);
    use(result);
} finally {
    pool.shutdown();
}
```

This is an illustrative snippet; `Result`, `task`, and `use` are defined by the application. A dedicated pool helps control parallelism level and resource scope; **whoever creates the pool must manage its shutdown**. If an application submits many asynchronous tasks, `shutdown()` alone does not prove they have finished; `awaitTermination()` or collecting task results may be needed before releasing resources.

### Parallelism Is Not an Absolute Count of Always-Running Threads

`ForkJoinPool(4)` expresses a target parallelism level. It does not guarantee four tasks are always running simultaneously or that every `compute()` call is evenly distributed. The number of useful tasks, `join()` dependencies, the scheduler, CPU availability, and blocking all affect the actual number of active workers.

## 15. Fork/Join and Parallel Streams

Some reductions can be written concisely with streams:

```java
long sum = LongStream.of(values).parallel().sum();
```

This is an illustrative snippet; it requires `import java.util.stream.LongStream;` and `values` as a `long[]`. For simple data, the standard library may optimize better than a custom implementation.

**Just because `parallel()` exists does not mean it should always be used:**

- Very small operations can be dominated by overhead.
- Operations with side effects on shared mutable state are prone to races.
- Stateful operations, ordering requirements, and data sources with uneven splitting costs can slow execution down.
- Parallel streams use Fork/Join under the hood in many cases and may share resources with other application tasks.

Incorrect example of shared mutable accumulation:

```java
List<Integer> result = new ArrayList<>();
values.parallelStream().forEach(result::add); // Not thread-safe.
```

This is an **anti-pattern snippet** where `values` is a suitable stream source. `ArrayList` is not safe for multiple concurrent writers. Prefer thread-safe/contract-compliant collectors, side-effect-free reductions, or an appropriate data structure/concurrency protocol.

## 16. Do Not Mechanically Use Fork/Join for Long Blocking I/O

Fork/Join is strongly designed for **CPU-bound and splittable tasks**. Workers blocked for long periods by:

- Network calls without timeouts.
- `Thread.sleep()` waiting for another service.
- Waiting on a lock from an unrelated system.
- `Future.get()` on a task outside the same Fork/Join structure.
- Long-blocking database queries or file reads.

can leave the pool with fewer available workers to execute unfinished tasks.

`ForkJoinPool.managedBlock(ForkJoinPool.ManagedBlocker)` exists to notify the pool of certain managed blocking operations, allowing it to consider compensating with extra workers when appropriate. **It is not magic that turns I/O into non-blocking**, and it does not replace timeouts, cancellation, or proper workload design.

When a workload is primarily I/O, consider an executor suited for blocking tasks or asynchronous I/O mechanisms. In Java 21+, virtual threads are also available, but they solve a different scheduling problem; do not equate them with Fork/Join CPU divide-and-conquer.

**Separation of concerns:** a parallel file-processing algorithm can use Fork/Join for the CPU computation part after reading data, rather than having every thread block on I/O in the same pool.

## 17. Exceptions in ForkJoinTask: Tracing Errors

A `RecursiveTask.compute()` can throw a `RuntimeException` or `Error` if it encounters a failure. When calling `join()` or `invoke()`, a subtask's error can be **propagated** according to the `ForkJoinTask` contract; unchecked exceptions are generally not wrapped the way `Future.get()` throws `ExecutionException`.

If using `ForkJoinTask.get()` (the `Future` interface), you can receive `ExecutionException` when the task completes abnormally, as well as `InterruptedException` if the waiting caller is interrupted. Therefore, distinguish which **result-waiting API** is being used:

| API | Result/Error |
| --- | --- |
| `task.join()` | Returns the result or throws an unchecked exception when the task fails |
| `pool.invoke(task)` | Returns the result or throws an unchecked exception when the task fails |
| `task.get()` | `Future` contract, with `ExecutionException` and `InterruptedException` |
| `task.get(timeout, unit)` | Can additionally throw `TimeoutException` |

If one branch fails, do not assume other branches are rolled back or that all running tasks will stop immediately. With a `RecursiveAction` modifying multiple segments, some segments may already have been updated before the error is observed. Decide on consistency, retry, rollback, or discarding results according to business requirements.

### Validation Example

In a reduction with domain constraints, validate inputs before creating tasks, or clarify which exceptions are recoverable errors. For instance, `Math.addExact` can throw `ArithmeticException` on overflow. In Fork/Join, that exception can propagate through `join()` to the caller; do not assume other branches have not performed any side effects.

## 18. Cancellation and Interruption

`ForkJoinTask.cancel(boolean mayInterruptIfRunning)` behaves differently from assuming a regular worker `Thread` will be interrupted just like a `FutureTask` in a `ThreadPoolExecutor`. Per the `ForkJoinTask` contract, **cancellation generally does not use interruption to control task execution**; the `mayInterruptIfRunning` argument is not a guarantee that the worker will stop.

Therefore:

- Do not expect `cancel(true)` to reliably interrupt a long computation inside `compute()`.
- A CPU-bound task that needs cancellation support can check an `AtomicBoolean` token/flag or an application-managed cooperative state.
- Check for cancellation at **safe points** and stop before spawning more subtasks if needed.
- Already-started branches may continue; design cleanup and result policies for cancellation.
- If a task has side effects or holds resources, use `finally` appropriately.

Illustrative pattern:

```java
if (cancelled.get()) {
    return 0L;
}
```

Here `cancelled` is an `AtomicBoolean` provided by the application. **Returning `0L` on cancellation** is only valid if the reduction contract distinguishes "cancelled" from a valid result; it is usually better to use a dedicated cancellation signal or a well-defined exception, avoiding returning `0` where the caller might mistake it for a real sum.

### Never Fork Infinite Tasks

A dangerous bug is a `compute()` that always splits without a base case, or splits a range into the exact same range (e.g., computing `mid = from` and recursing with `[from,to)` unchanged). That can spawn infinite tasks, spike allocations, and exhaust the pool. **Every recursive branch must make progress toward a base case.**

## 19. Memory Visibility During Fork and Join

For correct computation, we need data to be properly **published** to workers and worker results to be properly **observed**.

When a subtask is forked and later joined, Fork/Join's synchronization contract provides the basis for operations before submitting the task and after receiving the result to properly see relevant changes. The safest practice remains:

1. Fully initialize input references before submitting tasks.
2. Each task only reads immutable input or only modifies **independently owned data regions**.
3. Do not read a subtask's output region before `join()`/`invokeAll()` completes.
4. Combine results on the parent thread after waiting for branches.
5. If writers outside the Fork/Join tree modify data concurrently, establish a separate synchronization/ownership protocol.

**Do not misunderstand:** `join()` does not make arbitrary code writing to a shared `static long total` with `+=` thread-safe. It only provides a wait point and synchronization relation for the task, while contended updates can still suffer lost updates without atomics or locks.

## 20. Common Design Mistakes

### 20.1. Forking and Immediately Joining

```java
left.fork();
long a = left.join();
long b = right.compute();
```

This is an **anti-pattern for parallelism opportunity**. The current worker may sit waiting for `left` before starting `right`. The more appropriate pattern is usually `left.fork(); b = right.compute(); a = left.join();`.

### 20.2. Creating a Task per Element/Leaf

If an addition takes a few nanoseconds but you create millions of `RecursiveTask` objects, overhead can dominate. You must have a threshold.

### 20.3. Missing Base Case, or Splitting Without Shrinking

A recursive problem must progress toward a leaf/termination. Otherwise, it can cause `StackOverflowError`, task explosion, or never terminate.

### 20.4. Writing to the Same Mutable Sum Variable

```java
static long total;
...
total += value;
```

This is an **anti-pattern** when multiple tasks run concurrently. Addition is not atomic; the clearest approach is returning `Long` from each `RecursiveTask` and having the parent add them after `join()`.

### 20.5. Concurrently Modifying the Same Array Elements

In merge sort, the two subtasks must own disjoint ranges. If both write to `temp[k]` or the parent merges before joining, data races or logic errors occur.

### 20.6. Traversing a Cyclic Graph as a Tree

A `sum(node.left)+sum(node.right)` method can count the same node multiple times or recurse infinitely when the data is a DAG/graph. Define graph semantics and a visited protocol.

### 20.7. Assuming Fork/Join Is Always Faster Than Sequential

For small inputs, task overhead exceeds computation cost. Benchmark the actual workload and threshold; do not rely on worker count or intuition.

### 20.8. Using Naive Fibonacci and Treating Fork as Optimization

Recursive Fibonacci has overlapping subproblems and is inherently inefficient. Prefer memoization/DP/fast doubling depending on the problem.

### 20.9. Ignoring Overflow/Associativity

`long` has limits; `double` reductions involve rounding and grouping-dependent results. Choose numeric types and combination rules according to result requirements.

### 20.10. Using the Common Pool and Shutting It Down as a Private Resource

`ForkJoinPool.commonPool()` is a runtime-shared resource; do not shut it down on a whim. Only pools created via `new ForkJoinPool` have a lifecycle you own and manage.

### 20.11. Blocking Workers on Long I/O

Fork/Join suits CPU divide-and-conquer; long I/O starves workers of the ability to process tasks. Consider another pool/task model or appropriate managed blocking.

### 20.12. Assuming Future cancel(true) Always Interrupts ForkJoinTask

`ForkJoinTask`'s cancellation contract differs from many `Future` implementations. Design cooperative cancellation instead of relying on `mayInterruptIfRunning` to reliably stop execution.

### 20.13. Ignoring Child Task Exceptions

A child throwing an error can be propagated at `join()`. Do not swallow exceptions and add a bogus result that corrupts output; report the error or roll back according to the business contract.

### 20.14. Reading Results Before Joining

A result buffer still being written by subtasks is not a complete snapshot. There must be a wait point before the parent merges or a reader consumes the output.

## 21. Workflow for Applying Fork/Join in a Project

Before writing code, answer:

1. **Independence:** can subproblems run independently of each other?
2. **Combination operation:** do results have a valid identity and combine operation?
3. **Structure:** array range, tree subtree, or graph with shared nodes?
4. **Base case:** at what size should processing become sequential?
5. **Ownership:** do tasks read/write overlapping mutable state?
6. **Depth:** could recursion cause a stack overflow?
7. **Arithmetic:** do you need `long`, `BigInteger`, `BigDecimal`, or Kahan/pairwise sum?
8. **Pool:** common pool or dedicated pool? Who shuts it down?
9. **Liveness:** do tasks have blocking I/O, cyclic joins, or deadlocks?
10. **Cancellation and errors:** how are cancellation, exceptions, and partial side effects handled?
11. **Performance:** is there a measurable benefit compared to sequential code and standard libraries?

If two subproblems are **not independent**, the combine operation requires special ordering, or the data is a complex mutable graph, Fork/Join may not be the right model. A sequential algorithm, a dedicated `ExecutorService`, another pipeline, or a more suitable concurrency structure may work better.

## 22. Testing Correctness Before Benchmarking

Before measuring performance, always have a **sequential oracle** to verify:

### For Array Sum

- Empty array.
- Single element, two elements.
- Odd lengths to test `mid`.
- Negative/zero values.
- Large random data with a fixed seed.
- Overflow boundaries if the business logic must handle them.
- Compare `pool.invoke(task)` against `sequentialSum`.

### For Tree Sum

- `root == null` returns `0`.
- Single node.
- Balanced tree, left-only/right-only trees.
- Deep tree to detect stack risks.
- DAG/cycle if input is not guaranteed to be a pure tree.
- Result matches a verified sequential traversal function.

### For Merge Sort

- Empty array and single element.
- Odd/even lengths.
- Already sorted, reversed, many duplicates.
- Negative numbers.
- Compare against `Arrays.sort` on a copy.
- Verify no task writes outside `[from,to)`.

### Do Not Test with Sleep

Do not assume a task will finish within `sleep(10)` just because the machine is fast. `pool.invoke(...)` is a direct wait point for the result. If you need a test time limit, use your test framework's timeout or a `Future` mechanism with an explicit deadline, rather than replacing correctness assertions with scheduling luck.

**Correctness does not depend on worker count:** test with parallelism 1, 2, 4, or other appropriate levels. A correct algorithm must never turn wrong when there is only one worker, even though speed changes.

## 23. Practice Exercises

### Exercise 1: Max in an Array

Turn `SumTask` into `MaxTask`: leaves find the max in `[from,to)`, and parents combine with `Math.max(left,right)`. For the empty array case, **define a clear contract** (throw `IllegalArgumentException` or return `OptionalLong`), rather than arbitrarily returning `0` since the array might contain only negative numbers.

### Exercise 2: Min/Max/Count Statistics

Have each task return a record `Stats(long min, long max, long count)`; the parent combines two stats. Define an identity or handle the empty case separately to avoid wrong min/max values. Do not use three static mutable variables updated concurrently.

### Exercise 3: Counting Tree Nodes

Turn `TreeSumTask` into `NodeCountTask` with `count(null) = 0`, `count(node) = 1 + count(left) + count(right)`. Test balanced and skewed trees, comparing against a sequential function.

### Exercise 4: Sum of Squares

Replace `SumTask`'s leaf with summing `values[i]*values[i]` and check for overflow. Compare with a sequential oracle. With `double`, use an appropriate tolerance instead of demanding bitwise identical results when summation order differs.

### Exercise 5: Experimenting with Thresholds

Run on a sufficiently large array, vary the threshold, and measure with JMH or a proper benchmark. Require correct results as a prerequisite before recording latency/speedup. Test multiple input sizes and parallelism levels rather than concluding from a single run.

### Exercise 6: Skewed Tree

Create a tree with only right children. Observe why "forking two branches" helps little; consider converting to a list/node range or splitting a frontier if the problem allows.

### Exercise 7: Results with Errors

Have a leaf throw `IllegalArgumentException` when encountering invalid data; trace how the exception is reported at `join()` or `pool.invoke()`. Define a policy on whether other subtasks have side effects and can be safely retried.

## 24. Self-Check Questions

**1. Why is `RecursiveTask<Long>` suitable for summing an array?**

Because each subtask can return an independent `Long`; the parent combines them after `join()` without workers concurrently writing to a shared sum variable.

**2. What is the necessary condition for splitting an array into two tasks without missing or double-counting elements?**

Use two non-overlapping half-open intervals `[from,mid)` and `[mid,to)` that together cover `[from,to)`.

**3. What is the performance issue with `left.fork(); left.join(); right.compute();`?**

It can cause the worker to wait for `left` before processing `right`, reducing the opportunity to run both branches concurrently. Typically, fork one branch, compute the other, then join.

**4. Does work stealing guarantee that a subtask is executed by another worker?**

No. It allows idle workers to take work; the runtime decides the execution schedule. Correctness must not depend on which worker executes a task.

**5. Why is a threshold necessary?**

To avoid creating too many small tasks relative to leaf computation cost, which would make fork/join and allocation overhead outweigh parallelism benefits.

**6. Will a very deep tree with only one branch automatically run fast with Fork/Join?**

No. Without enough independent branches, there is very little work to distribute; recursion also risks stack overflow.

**7. Is it safe for two merge sort tasks to share the same arrays?**

Yes, provided they only write to **disjoint** segments, the parent waits for its children before merging, and no external writer violates ownership.

**8. Why not fork a separate task for every leaf node?**

Task creation and scheduling overhead can exceed leaf computation cost. Process small subtrees sequentially.

**9. Does forking naive Fibonacci automatically make it an optimal algorithm?**

No. Subproblems are recomputed due to the recursive structure; DP/memoization or fast doubling is usually much more efficient.

**10. Should `ForkJoinPool.commonPool()` be shut down at the end of every method?**

No. It is a shared pool, not a private resource of the method. Only pools created by the application require the owner to manage their lifecycle.

**11. If a `ForkJoinTask` has `cancel(true)` called on it, is the computing worker guaranteed to be interrupted and stop immediately?**

No. `ForkJoinTask`'s cancellation contract does not guarantee using interrupts to control execution; design cooperative cancellation when needed.

**12. Why can the parallel result of `double` addition differ from a sequential loop?**

Due to different addition groupings and rounding; floating-point addition is not strictly associative.

**13. Does `RecursiveAction` automatically prevent races when multiple tasks write to a shared `ArrayList`?**

No. Having no return value does not mean side effects are safe; writes must be partitioned or synchronized.

**14. Why can a graph with a node shared across two branches be computed incorrectly by a tree-sum algorithm?**

Because the same node can be counted multiple times; if there is a cycle, it can even recurse infinitely. Graph semantics and proper visited/dedup handling must be defined.

## 25. Summary

**Fork/Join** is a way to organize **divide-and-conquer** computations over independent data or branches. `RecursiveTask<V>` fits **returning results for reduction**, while `RecursiveAction` fits **operating on data regions with separate write ownership**. `ForkJoinPool` uses work stealing to distribute available tasks, but it cannot create parallelism on its own if the algorithm cannot split the work.

For **arrays**, split using half-open ranges and combine results after `join()`. For **trees**, split by subtree and watch out for skewed trees, recursion depth, graphs/cycles, and ownership. For **recursive computations**, check for overlapping subproblems before forking; naive Fibonacci is a lesson in limitations, not a good production algorithm. For **merge sort**, tasks modify independent segments and the parent only merges after waiting for its children.

To write correct and efficient code: **have a base case + threshold**, avoid shared mutable accumulators, bound depth/task count, manage pool ownership, handle errors and cancellation per contract, and **compare against a sequential oracle before benchmarking**. Fork/Join is most useful when per-branch cost is substantial, data can be safely partitioned, and parallel overhead is offset by real work.
