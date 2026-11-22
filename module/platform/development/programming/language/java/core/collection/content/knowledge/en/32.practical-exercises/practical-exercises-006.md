# Comprehensive Practice: Solving the Top-K Problem and Priority Task Queue

When a system receives a large volume of data, we sometimes only need the **best K elements**, or we must choose **which task to execute next** based on urgency. Both problems can be solved using Java's `PriorityQueue`, though with **different goals and comparison directions**.

This practical exercise applies the Java Collections Framework to two concrete scenarios. After completing this lesson, you will be able to:

- Clearly define the top-K selection criteria, including duplicate values, empty inputs, and cases where K exceeds the number of elements.
- Use a min-heap of size at most K to find the K largest values.
- Analyze the invariant, prove correctness, and calculate time and space complexity in terms of N and K.
- Build a task queue that processes higher-priority items first while preserving arrival order when priorities are equal.
- Explain `offer()`, `peek()`, and `poll()`, and why iterating over a `PriorityQueue` does not yield sorted results.
- Verify the implementation with compilable and runnable Java 17 code, then extend it to other business scenarios.

The examples are designed for single-threaded programs; concurrency concerns are distinguished in the notes section.

## 1. The Two Problems and Output Rules

### Problem A: Selecting the Top-K Highest Scores

A system stores test attempt scores in an array:

~~~text
[12, 7, 25, 10, 25, 3, 19, 18]
~~~

Return the **three highest scores**, sorted in descending order. The two occurrences of `25` are two separate elements of the input, so the problem **allows duplicates** and the expected result is:

~~~text
[25, 25, 19]
~~~

Conventions to agree upon before coding:

| Case | Expected Behavior |
| --- | --- |
| `k = 3` with the array above | `[25, 25, 19]` |
| `k = 0` | Empty list |
| `k > n` (where n is the number of elements) | Return all n elements in descending order |
| Empty array and `k ≥ 0` | Empty list |
| `k < 0` | Throw `IllegalArgumentException` |
| Input array is `null` | Throw `IllegalArgumentException` |

The function must not sort in place or modify the original array. The problem selects the **K highest-valued occurrences**, which differs from selecting K *distinct* values.

### Problem B: Processing Tasks by Priority

The queue receives the following tasks in order:

| Arrival Order | Task | Priority Level |
| --- | --- | --- |
| 0 | Sao lưu dữ liệu (Data backup) | 2 |
| 1 | Xử lý sự cố (Incident handling) | 5 |
| 2 | Gửi email (Send email) | 2 |
| 3 | Khôi phục dịch vụ (Service recovery) | 5 |
| 4 | Dọn tệp tạm (Clean temporary files) | 1 |

The rule is that a **larger priority number is processed first**. If priority levels are equal, the task received earlier is processed first. The results dequeued one by one must be:

1. Xử lý sự cố (Incident handling — priority 5, arrival 1).
2. Khôi phục dịch vụ (Service recovery — priority 5, arrival 3).
3. Sao lưu dữ liệu (Data backup — priority 2, arrival 0).
4. Gửi email (Send email — priority 2, arrival 2).
5. Dọn tệp tạm (Clean temporary files — priority 1, arrival 4).

A priority queue differs from a standard First-In-First-Out (FIFO) queue: a high-priority task arriving later can still overtake waiting low-priority tasks. FIFO serves only as a **secondary tie-breaking criterion** within a group sharing the same priority.

## 2. Why Is `PriorityQueue` Suitable?

`PriorityQueue<E>` belongs to `java.util`. It orders elements according to their natural ordering or a `Comparator` provided at construction time. The standard implementation uses a binary heap to maintain the **head element according to the comparator** without sorting the entire collection after every insertion.

| API | Meaning | Typical Complexity |
| --- | --- | --- |
| `offer(e)` | Insert an element | O(log m) |
| `peek()` | View the head of the queue without removing it; returns `null` if empty | O(1) |
| `poll()` | View and remove the head of the queue; returns `null` if empty | O(log m) |
| `size()` / `isEmpty()` | Count elements / check if empty | O(1) |
| `contains(e)` | Find an element by equality rule | O(m) |
| `remove(e)` | Remove a specific element | O(m) |

In the table, m is the number of elements currently stored; the complexities describe the standard `PriorityQueue` implementation.

By default, `new PriorityQueue<Integer>()` is a **min-heap**: `peek()` returns the **smallest number**. With `Comparator.reverseOrder()`, it acts as a **max-heap** for integer ordering: `peek()` returns the **largest number**.

Three orderings must be distinguished:

- **Arrival order:** when elements are inserted via `offer()`.
- **Priority order:** determined by `Comparable` or `Comparator`.
- **Internal iteration order:** the order seen by `iterator`, `for-each`, or `toString()`; **it is not guaranteed to be sorted by priority**.

Only by calling `poll()` repeatedly do you retrieve elements in priority order according to the comparator. If you must preserve the queue for later use, create a copy and call `poll()` on the copy, or use a different sorting approach.

By default, `PriorityQueue` also **does not preserve FIFO order for elements with equal priority**. To stabilize arrival order within the same priority level, we must include the arrival sequence in the comparator.

## 3. Top-K Largest: Using a Min-Heap of Size K

### 3.1. Intuition Behind Choosing the Structure

A straightforward approach is to copy and sort all n elements in descending order, then take the first K elements. This typically requires O(n log n) time and must hold or operate on all n elements.

When K is small compared to n, we do not need to remember everything. We only need to maintain the **K largest candidates among the elements read so far**. To quickly replace the weakest element in the candidate group, we place the **smallest element of that group at the head of the heap**.

Therefore, finding the **K largest numbers** uses a **min-heap**, not a max-heap, during the candidate selection stage. A max-heap of all n elements can retrieve the K largest numbers, but it must hold O(n) elements if all data is loaded upfront.

### 3.2. Step-by-Step Algorithm

Given a positive K and an input array:

1. Create `PriorityQueue<Integer> minHeap = new PriorityQueue<>()`.
2. Iterate through each number `x`. If the heap has fewer than K numbers, add `x` using `offer(x)`.
3. If the heap already has K numbers, inspect `minHeap.peek()`, which is the **smallest candidate**.
4. If `x > minHeap.peek()`, it deserves to replace the weakest candidate: call `poll()` and then `offer(x)`.
5. If `x ≤ minHeap.peek()`, keep the existing K candidates unchanged. For a problem that only considers **numeric values**, a new element equal to the threshold does not change the result set.
6. After iteration completes, copy the candidates into a `List<Integer>` and sort it in **descending order** to produce output matching the contract.

### 3.3. Data Trace

With K = 3, we have the following step-by-step trace. The last column is **shown in ascending order for readability** and does not represent the internal array order of the heap:

| Number Read | Decision | Retained Candidates |
| --- | --- | --- |
| 12 | Fewer than 3, add | [12] |
| 7 | Fewer than 3, add | [7, 12] |
| 25 | Fewer than 3, add | [7, 12, 25] |
| 10 | Greater than 7, replace 7 | [10, 12, 25] |
| 25 | Greater than 10, replace 10 | [12, 25, 25] |
| 3 | Not greater than 12, skip | [12, 25, 25] |
| 19 | Greater than 12, replace 12 | [19, 25, 25] |
| 18 | Not greater than 19, skip | [19, 25, 25] |

Sorting the three candidates in descending order gives `[25, 25, 19]`.

### 3.4. Invariant and Why the Algorithm Is Correct

**Invariant:** after processing any prefix of the input, the heap contains the exact `min(K, number of elements read)` largest values of that prefix, **including duplicate values**.

- When the heap has fewer than K elements, all numbers encountered so far are valid candidates and are added.
- When the heap has K elements, if the new number `x` is not greater than the smallest retained value, there are already K candidates with values no smaller than `x`; adding `x` would not improve the result.
- When `x` is greater than the smallest retained value, replacing the smallest value with `x` preserves the exact K best values of the new prefix.

This property holds after every iteration; therefore, once the entire array has been traversed, the heap holds the exact target values. The final sort only changes the presentation order, not the result set.

### 3.5. Cost Analysis

Let n be the number of elements, and `h = min(K, n)` when K ≥ 0. The heap contains at most h elements. Each number may trigger an insert, remove, or replace operation costing O(log h) when h ≥ 2. Sorting the h results takes O(h log h).

**Time:** O(n log h + h log h) when h ≥ 2; the cases h = 0 or h = 1 are handled more simply.

**Auxiliary Space:** O(h) to hold the heap and the result list. If K = 10 and n is very large, the memory required to store candidates stays proportional to 10, whereas sorting the entire dataset typically requires processing a much larger structure.

Never call `peek()` on an empty heap: the sample code checks for K = 0 and an empty array first, and only compares against `peek()` after the heap has reached K elements.

## 4. Task Queue: Primary Priority and Secondary Tie-Breaker

### 4.1. Representing a Task

Each task needs:

- `name`: descriptive name.
- `priority`: integer priority level, where a larger number indicates higher urgency.
- `sequence`: arrival sequence number, strictly increasing and **unique within a single queue**.

Java 17 supports `record` to define immutable data carrier objects. Using a record prevents mutating a task's priority while the object resides inside the heap.

### 4.2. The Required Comparator

The comparator must evaluate **priority in descending order**, followed by **arrival sequence in ascending order**:

~~~java
Comparator<Task> taskOrder =
        Comparator.comparingInt((Task task) -> task.priority())
                .reversed()
                .thenComparingLong(Task::sequence);
~~~

This snippet illustrates the comparator within a scope where `Task` is defined; the complete standalone runnable program is provided in Section 5.

Tasks sharing priority level 5 will be dequeued in ascending order of `sequence`: 1 before 3. Next come priority level 2 tasks, and finally level 1. Inserting a new task into the queue **does not start executing** that task; `poll()` merely selects and removes the next element.

If a task has already started running, a newly arrived higher-priority task does not automatically interrupt it. The queue manages **selecting the next task**, not preempting a currently executing task.

## 5. Complete Java 17 Program

Create a file named **`TopKAndPriorityDemo.java`** in your practice directory.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class TopKAndPriorityDemo {

    private record Task(long sequence, String name, int priority) {
    }

    public static List<Integer> topKLargest(int[] numbers, int k) {
        if (numbers == null) {
            throw new IllegalArgumentException("numbers không được null");
        }
        if (k < 0) {
            throw new IllegalArgumentException("k phải không âm");
        }
        if (k == 0 || numbers.length == 0) {
            return List.of();
        }

        PriorityQueue<Integer> minHeap = new PriorityQueue<>();

        for (int number : numbers) {
            if (minHeap.size() < k) {
                minHeap.offer(number);
            } else if (number > minHeap.peek()) {
                minHeap.poll();
                minHeap.offer(number);
            }
        }

        List<Integer> result = new ArrayList<>(minHeap);
        result.sort(Comparator.reverseOrder());
        return result;
    }

    public static void main(String[] args) {
        int[] scores = {12, 7, 25, 10, 25, 3, 19, 18};

        System.out.println("Top 3 điểm: " + topKLargest(scores, 3));
        System.out.println("Top 0 điểm: " + topKLargest(scores, 0));

        Comparator<Task> taskOrder =
                Comparator.comparingInt((Task task) -> task.priority())
                        .reversed()
                        .thenComparingLong(Task::sequence);

        PriorityQueue<Task> pending = new PriorityQueue<>(taskOrder);

        pending.offer(new Task(0, "Sao lưu dữ liệu", 2));
        pending.offer(new Task(1, "Xử lý sự cố", 5));
        pending.offer(new Task(2, "Gửi email", 2));
        pending.offer(new Task(3, "Khôi phục dịch vụ", 5));
        pending.offer(new Task(4, "Dọn tệp tạm", 1));

        System.out.println("Thứ tự xử lý tác vụ:");
        while (!pending.isEmpty()) {
            Task task = pending.poll();
            System.out.println("- " + task.name()
                    + " | ưu tiên=" + task.priority()
                    + " | đến=" + task.sequence());
        }
    }
}
~~~

In the directory containing the file above, compile and run:

~~~text
javac -encoding UTF-8 --release 17 TopKAndPriorityDemo.java
java -Dfile.encoding=UTF-8 TopKAndPriorityDemo
~~~

**Stdout output:**

~~~text
Top 3 điểm: [25, 25, 19]
Top 0 điểm: []
Thứ tự xử lý tác vụ:
- Xử lý sự cố | ưu tiên=5 | đến=1
- Khôi phục dịch vụ | ưu tiên=5 | đến=3
- Sao lưu dữ liệu | ưu tiên=2 | đến=0
- Gửi email | ưu tiên=2 | đến=2
- Dọn tệp tạm | ưu tiên=1 | đến=4
~~~

### Reading the Top-K Code

- `topKLargest(int[] numbers, int k)` rejects a `null` array and negative K.
- When K is 0 or the array is empty, the method returns `List.of()`. This empty list requires no element additions or removals.
- `minHeap.size() < k` allows inserting elements until K candidates are accumulated.
- Once K elements are present, `number > minHeap.peek()` determines whether to replace the smallest element.
- `new ArrayList<>(minHeap)` copies the data out of the heap; `sort(Comparator.reverseOrder())` is a separate step to satisfy the descending output contract.
- `scores` is the input array; the algorithm does not modify any element positions in this array.

### Reading the Task Queue Code

- `Task` has three immutable components: `sequence`, `name`, and `priority`.
- `Comparator.comparingInt(...).reversed()` places higher priority levels first.
- `thenComparingLong(Task::sequence)` ensures ascending arrival order when priority levels are equal.
- `pending.offer(...)` simply inserts the task into the queue.
- Each iteration of `while (!pending.isEmpty())` calls `poll()`, removing the highest-priority task according to the comparator and printing its details.
- After five `poll()` calls, the queue is empty. The program output is deterministic because the comparator defines both priority and arrival order.

Do not replace the `poll()` loop with direct iteration over `pending` if you need to print tasks in their actual processing order.

## 6. Comparing Two Ways of Using the Same Structure

| Aspect | Top-K Largest | Task Queue |
| --- | --- | --- |
| Goal | Retain the K best candidates | Select the next task |
| Element at head of heap | Smallest number among the K best | Highest-priority task |
| Comparator | Ascending natural order of `Integer` | Descending priority, then ascending arrival order |
| Size | Bounded to at most K | Grows/shrinks with waiting tasks |
| When a new element arrives | May evict the weakest candidate | Added to compete for processing order |
| When removing an element | Evicts the lowest candidate during updates | Retrieves the next task to process |
| Output | Converted to a `List` and sorted descending | `poll()` called for each task |

The decisive factor is placing the **element that needs to be inspected frequently** at `peek()`. For top-K, that is the lowest value among the K candidates. For task processing, that is the most urgent task.

## 7. Problem Variants and Design Implications

### 7.1. Top-K **Without Duplicate Values**

If the problem changes to "the K highest **distinct** scores", the example result must be `[25, 19, 18]`. We need a deduplication step, such as recording seen values in a `HashSet<Integer>` before considering them for the heap. A `HashSet` that remembers **all** read values can consume O(s) memory where s is the number of distinct values, so it no longer uses only O(K) total auxiliary memory. Always state the exact cost of this variant.

### 7.2. Top-K **Records** Instead of Numbers

If we need the K students with the highest scores, each element might be `Student(id, score, sequence)`. When multiple students share the same score and K cuts right across a tie boundary, we must define a tie-breaking criterion: smaller student ID, earlier arrival, or arbitrary selection? Comparing `number > peek()` only resolves **numeric values**, not selection rules among tied records. Both the comparator and the replacement condition must enforce a consistent tie-breaking policy.

### 7.3. Top-K **Frequencies**

If the problem asks for the K most frequent words, we must first count occurrences using a `Map<String, Integer>`, and then select the top K (word, frequency) pairs by occurrence count. We must also specify how to break ties when two words have the same frequency; using the word itself as the primary criterion violates the problem statement.

### 7.4. Priority Changing While a Task Is Waiting

`PriorityQueue` does not automatically re-heapify when fields affecting the comparator are mutated on an object already inside the queue. For tasks whose priority can change, you must design a cancel-and-reinsert operation or a mechanism that marks old entries as stale and inserts an updated entry. The immutable record in our example prevents hidden mutations from corrupting heap order.

### 7.5. Multithreading and Continuous Task Sources

`PriorityQueue` is not thread-safe when multiple threads concurrently insert and remove elements. With multiple producers and consumers, consider `PriorityBlockingQueue` along with an appropriate worker model. However, prioritizing tasks **does not automatically guarantee bounded queue capacity, strict fairness, or eventual execution for low-priority tasks**. If urgent tasks arrive continuously, low-priority tasks may wait indefinitely (starvation); that is a scheduling policy issue that cannot be solved by a comparator alone.

## 8. Common Mistakes

**Mistake 1 — Using a max-heap holding all N elements and calling it memory-optimal for top-K.** That approach produces the right result but holds O(N) elements if the entire array is loaded. When K is small, a K-bounded min-heap is much more memory-efficient.

**Mistake 2 — Printing the heap directly and assuming it is sorted.** `PriorityQueue` only guarantees the head element; iterator order is not `poll()` order. To obtain ordered results, sort a copied list or dequeue elements properly with `poll()`.

**Mistake 3 — Writing a comparator using subtraction `b - a`.** Integer subtraction can overflow and produce incorrect ordering. Use `Integer.compare(b, a)` or `Comparator.comparingInt(...).reversed()`. For `long` sequence numbers, use `Long.compare` or `thenComparingLong`.

**Mistake 4 — Comparing only the priority level while forgetting the tie-breaking rule.** Java does not guarantee FIFO order for tasks that the comparator considers equal. If "first come, first served" is required within the same priority level, include `sequence` in the comparator.

**Mistake 5 — Calling `peek()` on an empty queue or ignoring K = 0.** When empty, `peek()` returns `null`; auto-unboxing to a primitive integer throws a `NullPointerException`. Handle boundary conditions before entering the comparison branch.

**Mistake 6 — Mutating the priority value of an element already inside the heap.** The data structure will not automatically restore the heap invariant as expected. Keep priority keys immutable or update the queue through an explicit removal/re-insertion workflow.

**Mistake 7 — Treating a priority queue as an active execution scheduler.** Inserting into a queue or retrieving via `poll()` does not spawn threads, manage retries or timeouts, or preempt a currently running task.

## 9. Reinforcement Exercises and Self-Check Results

### Exercise 1. Top-2 with Duplicate Elements

Given `[4, 15, 2, 15, 9, 20]` and K = 2. Trace the retained candidates after each number and then run the method. Expected output: `[20, 15]`. Explain why one of the two occurrences of `15` is replaced by `20`.

### Exercise 2. Top-K Boundary Cases

Given the input `[8, 1, 8]`, run the method with K = 0, 1, 3, 5. The results must be `[]`, `[8]`, `[8, 8, 1]`, and `[8, 8, 1]` respectively. With K = -1, verify that the method throws `IllegalArgumentException` and that the input array remains unchanged.

### Exercise 3. Mixing Priorities and Arrival Order

Insert A (arrival 0, priority 2), B (arrival 1, priority 4), C (arrival 2, priority 4), D (arrival 3, priority 1), and E (arrival 4, priority 2). Before running, predict the `poll()` sequence to be **B, C, A, E, D**. After running, explain the ordering of the two equal-priority pairs B/C and A/E.

### Exercise 4. Adding a Processing Deadline

Add a `deadline` field to the task. New requirement: **descending priority → earlier deadline → ascending arrival order**. Modify the comparator and create a test case with three tasks of equal priority, two of which share the same deadline, to verify both secondary criteria. Do not use a mutable deadline object inside the heap.

### Exercise 5. Choosing a Structure for Very Large Datasets

With n = 1,000,000 scores and K = 10, compare the memory required between sorting a full copy of the array versus using a K-bounded min-heap. Explain why the final sorting step of just 10 results is still necessary if the contract requires descending order.

## 10. Solution Evaluation Checklist

- The problem statement clearly specifies whether to find the K largest or smallest, whether duplicates are allowed or distinct values are required, and the expected output ordering.
- The top-K algorithm maintains the invariant of retaining the K best candidates after each element.
- The heap never exceeds K elements; K = 0 and empty array cases are handled safely.
- The top-K result list is explicitly sorted in descending order rather than relying on the heap's iterator order.
- The task comparator includes both primary priority and a tie-breaker reflecting the requirements.
- Every task has a deterministic arrival sequence number; sort keys are never mutated while a task resides in the heap.
- Tested with duplicate inputs, K exceeding N, multiple tasks sharing the same priority, and an empty queue.
- Time and space complexity analyses accurately reflect n, K, and the auxiliary structures actually used.

Once you understand the condition for "which element must sit at the head" and the heap invariant, you can use the same `PriorityQueue` either to maintain the K best candidates or to select the next task to process, while rigorously verifying the correctness of both solutions.
