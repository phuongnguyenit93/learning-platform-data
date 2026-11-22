# Queue, FIFO, and Non-FIFO Queues

## 1. Queue Is an Operation Interface; FIFO Is an Ordering Policy

In Java, `Queue<E>` represents a collection that holds elements prior to processing. It provides operations such as adding an element, inspecting the element at the head of the queue, and removing the element at the head of the queue.

One point must be distinguished immediately:

- **Queue** is the interface and operational model.
- **FIFO** is the "first in, first out" policy.
- Not every object of type `Queue` selects elements according to FIFO.

The `Queue` documentation explicitly states that queues typically order elements in FIFO order, but exceptions exist, including priority queues and LIFO queues. Each implementation must specify its ordering properties. [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

The common concept across all policies is the **head**: the element that removal operations such as `poll()` or `remove()` will select according to the implementation's contract.

Therefore, the method name `poll` does not inherently mean "retrieve the earliest added element." It means retrieving the element at the head according to the active policy.

For example, when adding elements sequentially:

```text
30, 10, 20
```

there can be three valid outcomes:

| Policy | Removal Order |
| --- | --- |
| FIFO | `30, 10, 20` |
| Smaller number prioritized first | `10, 20, 30` |
| LIFO, last in, first out | `20, 10, 30` |

To predict program behavior, you must know both the interface being called and the policy of the actual implementation object.

## 2. FIFO: Add at the Tail, Remove from the Head

### 2.1. The Head and Tail Model

A FIFO queue has two distinct roles:

```text
remove ← head [A] [B] [C] tail ← add
```

If `A`, `B`, `C` are added sequentially in that order and no other operation modifies the queue, subsequent removals will return `A`, then `B`, then `C`.

| Operation | FIFO State After Operation | Removed Result |
| --- | --- | --- |
| Add A | `[A]` | Not yet removed |
| Add B | `[A, B]` | Not yet removed |
| Add C | `[A, B, C]` | Not yet removed |
| Remove head | `[B, C]` | `A` |
| Remove head | `[C]` | `B` |
| Remove head | `[]` | `C` |

A new element added at the tail does not bypass elements already waiting ahead of it. That is the meaning of first in, first out.

### 2.2. Using FIFO in a Single Thread

```java
// Illustrative snippet; a complete program is provided later.
Queue<String> pending = new ArrayDeque<>();
pending.offer("A");
pending.offer("B");
pending.offer("C");

String next = pending.poll(); // A
```

When using `ArrayDeque` through queue operations as shown above, additions occur at the tail and removals occur at the head.

FIFO describes the order of removal from the queue, not necessarily the order in which external processing completes. If multiple consumers process items concurrently and one task takes longer than another, completion results may differ from the removal order. A queue does not automatically make the processing time of every element equal.

### 2.3. FIFO Does Not Imply Deduplication

A queue is not a `Set`. The implementations in this lesson can hold two equal elements:

```text
add A, add A
removed: A, A
```

If the requirement is to process each identifier only once, you need to design separate tracking for seen items rather than assuming that being in a `Queue` provides deduplication.

## 3. The Six Core Methods and Reading the Head Correctly

`Queue` divides its basic operations into two ways of reporting certain situations where an operation cannot be performed:

| Purpose | Throws Exception | Returns Special Value |
| --- | --- | --- |
| Insert element | `add(e)` | `offer(e)` |
| Retrieve and remove head | `remove()` | `poll()` |
| Inspect head, keep queue unchanged | `element()` | `peek()` |

The ordering policy determines **which element is the head**. The method pairs primarily differ in how they report their respective failure states; they do not turn FIFO into priority ordering or vice versa.

### 3.1. offer and add

`offer(e)` attempts to insert the element immediately. For a capacity-bounded queue, it returns `false` when it cannot insert because no space is currently available.

`add(e)` returns `true` upon success; if no space is available due to capacity limits, it signals this with an `IllegalStateException`.

Do not misunderstand "returns a special value" as meaning every error is converted into `false`. An invalid element, such as `null` in a queue that does not permit `null`, can still throw an exception.

Also, do not assume `offer` blocks and waits until space becomes available. Waiting operations belong to specialized interfaces such as `BlockingQueue`, which have their own methods. [Queue: add and offer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

### 3.2. poll and No-Argument remove

For standard queues in introductory programs:

- `poll()`: retrieves and removes the head of the queue; returns `null` if the queue is empty.
- `remove()`: retrieves and removes the head of the queue; throws `NoSuchElementException` if the queue is empty.

This is `remove()` **with no arguments**. It differs from `remove(Object value)` inherited from `Collection`, which searches for and removes a matching element by value and returns a `boolean`.

Do not read these two signatures as the same operation.

### 3.3. peek and element

Both methods inspect the head of the queue without removing it:

- `peek()`: returns `null` when empty.
- `element()`: throws `NoSuchElementException` when empty.

For a FIFO queue containing `[A, B, C]`, calling `peek()` multiple times with no other changes will still see `A`, rather than stepping through `A`, `B`, `C`.

### 3.4. Avoid Using null as a Valid Task Element

`ArrayDeque` and `PriorityQueue` do not allow adding `null`. The `Queue` interface has other implementations with different rules, but even when an implementation permits it, using `null` as an element creates ambiguity with the special return values of `poll` and `peek`.

You should keep the task domain free of `null` whenever possible. When removing an element, check the result before using it as an object or unboxing it to a primitive type.

Specialized queues may also have conditions on when an element is eligible to be retrieved; for example, `DelayQueue` is distinguished later. Do not generalize a simple processing loop to all implementations without reading their contracts. [Queue: null rules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

## 4. Complete Program: Same Interface, Three Removal Orders

Save the code to **QueuePoliciesDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.PriorityQueue;
import java.util.Queue;

public class QueuePoliciesDemo {
    private static <E> List<E> drain(Queue<E> queue) {
        List<E> result = new ArrayList<>();
        E value;
        while ((value = queue.poll()) != null) {
            result.add(value);
        }
        return result;
    }

    public static void main(String[] args) {
        Queue<Integer> fifo = new ArrayDeque<>();
        Queue<Integer> priority = new PriorityQueue<>();
        Queue<Integer> lifo =
                Collections.asLifoQueue(new ArrayDeque<>());

        List<Integer> input = List.of(30, 10, 20);
        for (Integer value : input) {
            fifo.offer(value);
            priority.offer(value);
            lifo.offer(value);
        }

        System.out.println("input: " + input);
        System.out.println("FIFO head: " + fifo.peek());
        System.out.println("priority head: " + priority.peek());
        System.out.println("LIFO head: " + lifo.peek());
        System.out.println("FIFO size after peek: " + fifo.size());
        System.out.println("FIFO removal order: " + drain(fifo));
        System.out.println("priority removal order: " + drain(priority));
        System.out.println("LIFO removal order: " + drain(lifo));
        System.out.println("FIFO empty: " + fifo.isEmpty());
        System.out.println("empty peek: " + fifo.peek());
        System.out.println("empty poll: " + fifo.poll());

        try {
            fifo.remove();
        } catch (NoSuchElementException ex) {
            System.out.println("empty remove: NoSuchElementException");
        }
        try {
            fifo.element();
        } catch (NoSuchElementException ex) {
            System.out.println("empty element: NoSuchElementException");
        }

        Queue<String> repeated = new ArrayDeque<>();
        repeated.offer("A");
        repeated.offer("A");
        System.out.println("duplicates: " + drain(repeated));
    }
}
```

Compile targeting Java 17 and run:

```shell
javac --release 17 -encoding UTF-8 QueuePoliciesDemo.java
java QueuePoliciesDemo
```

Stdout:

```text
input: [30, 10, 20]
FIFO head: 30
priority head: 10
LIFO head: 20
FIFO size after peek: 3
FIFO removal order: [30, 10, 20]
priority removal order: [10, 20, 30]
LIFO removal order: [20, 10, 30]
FIFO empty: true
empty peek: null
empty poll: null
empty remove: NoSuchElementException
empty element: NoSuchElementException
duplicates: [A, A]
```

How to interpret the output:

1. All three variables have type `Queue<Integer>`, but the underlying objects follow three different policies.
2. FIFO returns `30` as the head because it was added first.
3. The natural-order priority queue returns `10` as the head, not the element added first.
4. The LIFO view returns `20` as the head, the element added last.
5. `peek` does not reduce the size.
6. The `drain` method repeatedly calls `poll` and thus empties the queues in the example.
7. The empty-queue results clearly distinguish the `poll`/`remove` and `peek`/`element` pairs.
8. Both `A` values are retained and both are retrieved.

The `drain` method is used here for three non-delaying, `null`-free queues. For these, `poll()` returns `null` when no elements remain. It is not presented as an algorithm guaranteed to drain every element from all specialized queues.

The program obtains the order through `poll` calls. It does not use `for-each` iteration on a priority queue to infer processing order.

## 5. PriorityQueue: Priority Determines the Head

### 5.1. An Element Removed First May Arrive Later

`PriorityQueue` selects the head based on the elements' natural ordering or a provided `Comparator`.

Under the natural ordering of integers, the smallest available element is the head. If you add `30`, then `10`, then `20`, the first removal is `10`.

This conforms to the priority policy and is not a broken FIFO queue. Its element selection rule is different by design. [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

If no `Comparator` is passed, the elements must have a compatible natural ordering, typically via `Comparable`. A job class is not automatically compared by a field named `priority` just because that field exists; an appropriate comparison rule must be provided.

For job objects, whether "smaller number has higher priority" or "larger number has higher priority" is a convention that must be designed. The field name `priority` does not dictate the comparison direction on its own.

For example:

```java
Queue<Integer> greatestFirst =
        new PriorityQueue<>(Comparator.reverseOrder());
```

causes the largest number under standard numeric ordering to be selected first, because it is the smallest under the provided reversed ordering.

### 5.2. Equal Priority Does Not Mean FIFO Within the Group

If only `priority` is compared, two jobs with the same level yield a comparison result of `0`. `PriorityQueue` does not guarantee that the job arriving first in that group will be retrieved first; ties are broken arbitrarily per the contract.

Do not observe "A before B" in a single run and assume stability across all inputs or all JDK versions.

If FIFO ordering is required within the same priority level, you must include arrival order as a secondary criterion, such as a `sequence` field assigned according to a defined rule:

```java
Comparator<Job> order = Comparator.comparingInt(Job::priority)
        .thenComparingLong(Job::sequence);
```

The overall rule remains priority first, then sequence. It **does not become globally FIFO**: a higher-priority job arriving later can still overtake a lower-priority job that arrived earlier.

In the single-threaded example below, the sequences `0, 1, 2, 3` represent the order in which jobs are enqueued. In a multi-threaded design, how this sequence is assigned and what it means must be defined separately; the queue does not generate a sequence field for the user.

### 5.3. PriorityQueue Retains Elements with Equal Priority

`PriorityQueue` is not a `TreeSet`. A comparison result of `0` does not cause two jobs to be merged into a single element.

Two distinct jobs with the same priority can coexist in the queue. The lack of a secondary tie-breaker makes their retrieval order unspecified, not that one job is deduplicated.

If the application requires no two jobs with the same ID, a separate ID-management rule is needed. A priority comparator is not a deduplication mechanism.

### 5.4. Do Not Use an Iterator to Prove Priority Order

The `PriorityQueue` contract does not guarantee that `iterator`, `for-each`, or an array obtained from the queue is ordered according to `poll` order.

A heap-based priority queue does not need to maintain the entire structure as a fully sorted sequence. It only needs to provide the correct head for the corresponding retrieval operations.

If you want to inspect the removal order while preserving the original queue, you can create a priority copy with the same comparator and `poll` the copy. If you want a sorted list for display, create a list and sort it with the appropriate comparator.

Do not print a `PriorityQueue` directly and treat that output as the guaranteed processing order. [PriorityQueue: head, ties, and iteration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

### 5.5. Priority Keys Must Remain Stable While Jobs Are Waiting

If you mutate the field used for comparison on an object already in the queue, the structure does not automatically know to re-order itself just because the caller changed a field.

Prefer job objects with immutable comparison keys, or design an explicit update procedure. In the example, the record has stable `String`, `int`, and `long` components.

## 6. LIFO and Deque: Choosing the Insertion/Removal End Changes the Policy

LIFO stands for **last in, first out**, commonly known as a stack.

If you add `A`, `B`, `C` and then remove according to LIFO, the result is:

```text
C, B, A
```

`Deque` is a double-ended queue that supports operations at both the front and the back. The same implementation, such as `ArrayDeque`, can serve two usage patterns:

| Usage | Add | Remove | Order for A, B, C Added Sequentially |
| --- | --- | --- | --- |
| FIFO | `offerLast` | `pollFirst` | A, B, C |
| LIFO at the front | `push` or corresponding front-add operation | `pop` or corresponding front-remove operation | C, B, A |

`push` inserts at the front; `pop` retrieves and removes from the front. Adding and removing at the same end causes the most recent element to be retrieved first. [Deque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

When using the standard `Queue` methods of `ArrayDeque`, adding and removing follow FIFO semantics. When using `push/pop`, you are using it as a stack.

Do not arbitrarily mix double-ended operations and still claim that all data follows a FIFO history. The usage policy must be consistent across all parts of the program that modify the same structure.

### A Variable of Type Queue Can Behave as LIFO

Java provides a view:

```java
Queue<String> lifo =
        Collections.asLifoQueue(new ArrayDeque<>());
```

This view forwards queue operations to the corresponding stack operations on the backing deque. It is a direct example that the `Queue` type does not guarantee FIFO.

It is a view backed by the underlying deque, not an independent copy of the data. If you retain a reference to the deque as well, operations through either reference affect the same data. [Collections.asLifoQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#asLifoQueue(java.util.Deque))

## 7. Complete Program: Priority with a Secondary Criterion and Deque Usage

Save the code to **PriorityAndStackDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Queue;

public class PriorityAndStackDemo {
    private record Job(String name, int priority, long sequence) {
    }

    private static List<String> jobOrder(Queue<Job> jobs) {
        List<String> result = new ArrayList<>();
        Job job;
        while ((job = jobs.poll()) != null) {
            result.add(job.name());
        }
        return result;
    }

    public static void main(String[] args) {
        Comparator<Job> order = Comparator.comparingInt(Job::priority)
                .thenComparingLong(Job::sequence);
        Queue<Job> jobs = new PriorityQueue<>(order);
        jobs.offer(new Job("report", 2, 0));
        jobs.offer(new Job("parse", 1, 1));
        jobs.offer(new Job("index", 1, 2));
        jobs.offer(new Job("notify", 2, 3));
        System.out.println("priority then sequence: " + jobOrder(jobs));

        Queue<Job> tied = new PriorityQueue<>(
                Comparator.comparingInt(Job::priority));
        tied.offer(new Job("A", 1, 0));
        tied.offer(new Job("B", 1, 1));
        System.out.println("equal-priority count: " + tied.size());
        List<String> tiedNames = jobOrder(tied);
        tiedNames.sort(Comparator.naturalOrder());
        System.out.println("all tied names, sorted afterward: " + tiedNames);

        Queue<Integer> greatestFirst =
                new PriorityQueue<>(Comparator.reverseOrder());
        greatestFirst.addAll(List.of(30, 10, 20));
        List<Integer> descending = new ArrayList<>();
        Integer number;
        while ((number = greatestFirst.poll()) != null) {
            descending.add(number);
        }
        System.out.println("reverse-comparator order: " + descending);

        Deque<String> fifo = new ArrayDeque<>();
        fifo.offerLast("A");
        fifo.offerLast("B");
        fifo.offerLast("C");
        System.out.println("deque FIFO first: " + fifo.pollFirst());

        Deque<String> stack = new ArrayDeque<>();
        stack.push("A");
        stack.push("B");
        stack.push("C");
        System.out.println("deque stack first: " + stack.pop());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 PriorityAndStackDemo.java
java PriorityAndStackDemo
```

Stdout:

```text
priority then sequence: [parse, index, report, notify]
equal-priority count: 2
all tied names, sorted afterward: [A, B]
reverse-comparator order: [30, 20, 10]
deque FIFO first: A
deque stack first: C
```

How to interpret the output:

1. `report` was added earliest but has priority `2`; the two priority `1` jobs are retrieved first under the example's smaller-number-first convention.
2. Within the priority `1` group, `parse` with sequence `1` comes before `index` with sequence `2`.
3. Two jobs compared solely by the same priority still coexist: the size is `2`.
4. The list of tied names is **sorted after removal** before printing. That `[A, B]` line does not assert that the priority queue retrieved A before B.
5. The reverse comparator for the number sequence retrieves `30` before `20`, then `10`.
6. The deque used as FIFO returns `A`; the deque used as a stack returns `C`.

The two standalone programs in this lesson were compiled with `--release 17` and run to verify matching stdout. This option checks language/API levels and generates Java 17-compatible bytecode; it does not assert that the executing JVM itself is JDK 17.

## 8. Other Policies and Properties Not to Conflate with FIFO

### 8.1. Delay Queues Also Consider When Elements Become Eligible

`DelayQueue` is a specialized example: elements carry delay information and can only be retrieved according to the class's expiration rules.

An element inserted later whose eligible time arrives earlier does not have to wait simply because it was added later. Processing order cannot be inferred solely from insertion order.

An important detail: `poll()` can return `null` when no element has expired yet, even if the structure still holds unexpired elements. Therefore, a loop stopping when `poll` returns `null` does not mean all elements have been drained from this type of queue. [DelayQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/DelayQueue.html)

This lesson does not use a stdout example relying on time waits, because the focus is on distinguishing retrieval policies from insertion order.

### 8.2. Ordering Policy, Capacity Bounds, and Blocking Are Separate Axes

| Property | Question |
| --- | --- |
| Ordering | FIFO, LIFO, priority, or time-based condition? |
| Capacity | Bounded element count or dynamically growing? |
| Failure/waiting behavior | Return immediately, throw an exception, or provide blocking operations? |
| Concurrent access | Does the implementation support multiple threads under a defined contract? |

A FIFO queue can be bounded. A priority queue can have no fixed API-level bound. Having blocking capabilities does not mean it must automatically be FIFO.

`Queue` does not declare blocking methods such as `put` and `take`; those belong to `BlockingQueue`. That extended interface adds blocking capabilities, while the specific ordering still needs to be read from the implementation. [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

For example, `ArrayBlockingQueue` has a fixed capacity and a FIFO element policy. `PriorityQueue` is an automatically growing priority queue without that kind of fixed bound in its class contract. Do not infer blocking mechanisms or thread-safety from a variable typed as `Queue`. [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html), [PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

Standard `ArrayDeque` and `PriorityQueue` are not synchronized for concurrent modification by multiple threads. The examples in this lesson are examined in a single thread, not as multi-threaded coordination patterns.

## 9. Choosing a Structure Based on Processing Requirements

| Requirement | Suitable Approach |
| --- | --- |
| Process in insertion order within a single thread | `Queue` backed by `ArrayDeque` with FIFO discipline |
| Retrieve jobs by a priority level | `PriorityQueue` with a clear comparison rule |
| Same priority must follow a deterministic order | Add an appropriate secondary criterion, such as `sequence` |
| Need to return to the most recent step first | `Deque` used as a stack |
| Retrieve only after expiration | Consider a time-based structure such as `DelayQueue` |
| Bounded capacity and blocking between threads | Check the `BlockingQueue` contract and specific implementations |

Some design questions to answer upfront:

1. What determines the next job?
2. Can equal elements appear multiple times?
3. If priorities are equal, is a guaranteed secondary order needed?
4. When full or when no element is available, should it return immediately or block?
5. Who owns and is allowed to modify the queue?

With a priority queue, if high-priority jobs arrive continuously, a low-priority job may wait for a long time. This is a policy consequence that must be accounted for in the problem design, not a bug because "a queue should be FIFO." Adjusting priority over time or guaranteeing fairness requires additional design and is not built into `PriorityQueue` alone.

## 10. Understand Cost by Implementation Rather Than Assigning One Number to Queue

The `Queue` interface name does not promise that every operation on every implementation is O(1).

A few characteristics relevant to the examples:

- `ArrayDeque` has an amortized constant-time model for most standard double-ended operations.
- `PriorityQueue` must maintain the priority structure; the documentation describes insertion and head removal as O(log n), while inspecting the head is O(1).
- Finding or removing an element by value using `Collection` operations can have a different cost than removing from the head.

These differences match the structure's responsibility: maintaining true priority ordering differs from merely managing two ends by operation history. Do not pick a priority queue for a FIFO requirement simply because both provide `offer` and `poll`. [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), [PriorityQueue: operation complexity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

Do not use `toString` order or a small run to benchmark speed or prove ordering guarantees. Policy correctness is determined from the contract and verified with the corresponding operations.

## 11. Common Mistakes

| Misconception or Code Pattern | Problem | Fix |
| --- | --- | --- |
| Every Queue is FIFO | Confuses the interface with the implementation policy | Identify the rule used to select the head element |
| PriorityQueue must retrieve the earliest-arrived element | Priority is the primary criterion | Check the `Comparator` or natural ordering |
| A larger priority number is always processed first | Priority direction is a comparator convention | Write and verify the comparison direction |
| Equal priority guarantees FIFO | Ties are not guaranteed to be stable in `PriorityQueue` | Design a secondary tie-breaker when needed |
| Comparing equal to 0 causes PriorityQueue to deduplicate | Applies sorted-set rules to a queue | Separate ordering from element retention |
| For-each on PriorityQueue matches poll order | The iterator does not promise priority order | Poll or sort a copy to observe the actual order |
| Peek advances to the next element | `peek` does not remove the head | Use `poll` when you need to retrieve and remove |
| Offer never throws an exception | Invalid elements can still fail | Distinguish capacity limits from domain violations |
| Offer blocks when full | `Queue` does not provide blocking operations in that sense | Use the appropriate blocking interface/methods if needed |
| Calling push/pop and still assuming FIFO | Using the same end as a stack | Stay consistent in double-ended usage |
| Poll returning null always means the queue holds no elements | Specialized queues have eligibility conditions like `DelayQueue` | Read the specific contract |
| FIFO guarantees jobs finish in the same order | Removal order and external processing duration are independent | Keep the two concepts separate |

When predicting output, note the implementation type, the operations used to insert/remove, and the head-selection rule. Looking only at a variable named `queue` is not enough.

## 12. Self-Practice and Verification

### Exercise 1: Same Data, Three Policies

Insert `8, 3, 5` sequentially into three empty queues: FIFO, smaller-number-first priority, and LIFO. Drain all retrievable elements from these three standard queues.

Verification:

```text
FIFO:     8, 3, 5
Priority: 3, 5, 8
LIFO:     5, 3, 8
```

Be able to explain which rule selects each first element.

### Exercise 2: Inspect or Remove?

A FIFO queue contains `[A, B]`:

```text
peek() → A; queue is still [A, B]
poll() → A; queue has [B] left
peek() → B; queue is still [B]
poll() → B; queue is empty
poll() → null
```

If you replace the final call with `remove()`, on an empty queue it will throw `NoSuchElementException`.

### Exercise 3: Priority First, Sequence Second

Three jobs are inserted:

```text
A: priority=2, sequence=0
B: priority=1, sequence=1
C: priority=1, sequence=2
```

With an ascending priority then ascending sequence comparator, the order is `B, C, A`.

If you remove the sequence criterion and compare only by priority, all three elements are still present and A still comes after the priority 1 group, but you cannot assert whether B or C is retrieved first based solely on arrival order.

### Exercise 4: Is Deque Acting as FIFO or LIFO?

- Adding A, B, C with `offerLast` and removing with `pollFirst`: FIFO.
- Adding A, B, C with `push` and removing with `pop`: LIFO.
- Mixing insertions at both ends without a single rule: you cannot conclude the history is FIFO just by naming the structure.

### Exercise 5: Reading a Failed offer Correctly

An `ArrayBlockingQueue` with capacity 2 currently holds `A, B`. `offer("C")` returns `false` because there is no space to insert immediately. The two existing elements remain in FIFO order.

If `add("C")` is used in that full state, the lack of space is reported via `IllegalStateException`. That is a difference in failure reporting, not a new ordering policy.

## 13. Reference Documentation

- [Queue Java 17 — interface, head, and ordering policies](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)
- [ArrayDeque — deque implementation for FIFO/LIFO usage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)
- [Deque — double-ended and stack operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)
- [PriorityQueue — priority, ties, and iteration order limitations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)
- [Collections.asLifoQueue — LIFO Queue view](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#asLifoQueue(java.util.Deque))
- [BlockingQueue — dedicated blocking capabilities](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [ArrayBlockingQueue — bounded FIFO queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [DelayQueue — expiration condition before retrieval](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/DelayQueue.html)
