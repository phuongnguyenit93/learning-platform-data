# ConcurrentLinkedQueue and ConcurrentLinkedDeque

## 1. The problem: multiple threads adding and removing elements concurrently

One thread produces work, another thread consumes work; or multiple threads push and pop data at both ends simultaneously. The container structure must protect the linking, searching, and removal of elements when operations overlap.

`ConcurrentLinkedQueue<E>` and `ConcurrentLinkedDeque<E>` are two options in `java.util.concurrent`:

- **`ConcurrentLinkedQueue`** is a concurrent FIFO queue: elements are added at the tail and removed at the head.
- **`ConcurrentLinkedDeque`** is a concurrent double-ended queue: it allows adding, inspecting, and removing elements at both the head and the tail.

Both are based on linked nodes, have no intrinsic capacity bound, and do not permit null elements. Access and update operations are designed to be thread-safe across multiple threads. [ConcurrentLinkedQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html), [ConcurrentLinkedDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html)

What you need to learn is not just the class names. You need to know **where to add, where to remove, what to do when empty, and when you may conclude there is no more work**. The collection protects the store/retrieve operations; the work-processing protocol is still defined by the application.

The examples use Java 17 or later. Prerequisite knowledge includes `Queue`, `Deque`, generics, object references, and loops. The multithreading section explains the coordination and termination conditions directly in this lesson.

### 1.1. Terminology and relationships

| Term | Meaning |
| --- | --- |
| Head (`head`/`first`) | The removal end of a FIFO queue |
| Tail (`tail`/`last`) | The insertion end of a FIFO queue |
| FIFO | First-In, First-Out: elements inserted earlier are removed earlier in queue order |
| LIFO | Last-In, First-Out: elements inserted later are removed earlier, like a stack |
| Producer / consumer | The task that inserts elements and the task that removes elements |
| Unbounded (no intrinsic bound) | No fixed element limit imposed by the data structure itself |
| Non-blocking retrieval | A retrieval call returns immediately based on the observed state, without waiting for a future element to appear |

"Unbounded" does not mean infinite memory. "Thread-safe" does not mean multiple steps in a program automatically combine into a single transaction.

## 2. Choosing the right end and the right return behavior

### 2.1. ConcurrentLinkedQueue: a single FIFO path

Basic model:

```text
take at head                           add at tail
poll / peek  <- [old-task, next-task, new-task] <- offer
```

`offer(e)` inserts an element at the tail. `poll()` retrieves and removes the element at the head. `peek()` only inspects the head without removing it.

There are two groups of methods depending on how an empty queue is handled:

| Intent | Returns special value | Throws exception if empty |
| --- | --- | --- |
| Retrieve and remove head | `poll()` returns null | `remove()` throws `NoSuchElementException` |
| Inspect head without removing | `peek()` returns null | `element()` throws `NoSuchElementException` |

This is the contract of the `Queue` methods. The zero-argument `remove()` differs from `remove(object)`, which searches for and removes a single occurrence of the specified object. [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

For the unbounded `ConcurrentLinkedQueue`, `offer` returns true when the insertion succeeds; it does not return false because "the queue has reached N elements". There is no mechanism to wait for available space as in a capacity-managed queue.

### 2.2. ConcurrentLinkedDeque: two independent ends in the interface

`Deque` stands for "double-ended queue".

| Intent | Head (`First`) | Tail (`Last`) |
| --- | --- | --- |
| Insert | `offerFirst(e)` or `addFirst(e)` | `offerLast(e)` or `addLast(e)` |
| Retrieve, returns null if empty | `pollFirst()` | `pollLast()` |
| Retrieve, throws exception if empty | `removeFirst()` | `removeLast()` |
| Inspect, returns null if empty | `peekFirst()` | `peekLast()` |
| Inspect, throws exception if empty | `getFirst()` | `getLast()` |

`addFirst/addLast` return void; `offerFirst/offerLast` return boolean. With `ConcurrentLinkedDeque`, offer operations at both ends return true upon successful insertion and are not rejected due to an intrinsic capacity limit. Null elements are still invalid.

When using a deque as a queue, `offer/add` inserts at the tail, while `poll/remove` retrieves from the head. When using it as a stack, `push` corresponds to inserting at the head and `pop` corresponds to removing from the head. [Deque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

Therefore:

- `offerLast` followed by `pollFirst` produces FIFO usage.
- `push` followed by `pop`, both operating at the head, produces LIFO usage.
- If a program mixes insertions and removals at both ends, the processing order must be described according to that actual rule; do not mechanically call the entire usage FIFO.

### 2.3. Duplicate elements are allowed

Inserting the same value twice creates two occurrences. This is a queue/deque, not a set.

A successful retrieval removes one occurrence. If the same reference is inserted twice, two consumers can receive that same reference from two different positions. This does not prove that the queue delivered a single position twice.

If business logic requires unique job IDs, deduplication rules must be handled separately. Do not rely on the queue's thread safety as a uniqueness guarantee.

## 3. Sequential program to verify ordering and exceptions

Save as **`LinkedEndpointsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedDeque;
import java.util.concurrent.ConcurrentLinkedQueue;

public class LinkedEndpointsDemo {
    public static void main(String[] args) {
        ConcurrentLinkedQueue<String> queue = new ConcurrentLinkedQueue<>();
        queue.offer("one");
        queue.offer("two");
        queue.offer("three");
        System.out.println("queue peek = " + queue.peek());
        System.out.println("queue drain = " + drain(queue));
        System.out.println("empty queue poll = " + queue.poll());
        expectEmpty("empty queue remove", queue::remove);

        ConcurrentLinkedDeque<String> deque = new ConcurrentLinkedDeque<>();
        deque.offerLast("B");
        deque.offerFirst("A");
        deque.offerLast("C");
        System.out.println("deque forward = " + new ArrayList<>(deque));
        List<String> reverse = new ArrayList<>();
        Iterator<String> iterator = deque.descendingIterator();
        iterator.forEachRemaining(reverse::add);
        System.out.println("deque reverse = " + reverse);
        System.out.println("deque ends = " + deque.peekFirst()
                + ", " + deque.peekLast());
        System.out.println("poll first = " + deque.pollFirst());
        System.out.println("poll last = " + deque.pollLast());
        System.out.println("middle remains = " + new ArrayList<>(deque));

        deque.push("X");
        deque.push("Y");
        System.out.println("stack pop = " + deque.pop());
        System.out.println("remove last = " + deque.removeLast());
        System.out.println("remaining = " + new ArrayList<>(deque));
        deque.clear();
        System.out.println("empty deque pollLast = " + deque.pollLast());
        expectEmpty("empty deque pop", deque::pop);
    }

    private static <T> List<T> drain(Queue<T> queue) {
        List<T> values = new ArrayList<>();
        T value;
        while ((value = queue.poll()) != null) {
            values.add(value);
        }
        return values;
    }

    private static void expectEmpty(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("expected NoSuchElementException");
        } catch (NoSuchElementException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all LinkedEndpointsDemo.java
java LinkedEndpointsDemo
```

Stdout on a successful run:

```text
queue peek = one
queue drain = [one, two, three]
empty queue poll = null
empty queue remove -> NoSuchElementException
deque forward = [A, B, C]
deque reverse = [C, B, A]
deque ends = A, C
poll first = A
poll last = C
middle remains = [B]
stack pop = Y
remove last = B
remaining = [X]
empty deque pollLast = null
empty deque pop -> NoSuchElementException
```

The program intentionally uses only a single thread to separate understanding the API from analyzing execution schedules:

1. `peek` reads `one` while leaving it at the head, so the subsequent drain still retrieves all three elements in FIFO order.
2. `poll` on an emptied queue returns null, whereas `remove` throws an exception.
3. The deque is constructed as `A, B, C` using operations at both ends.
4. The regular iterator traverses from head to tail; `descendingIterator` traverses in the opposite direction.
5. Removing head A and tail C leaves B.
6. Pushing X then Y at the head makes Y the first element popped by `pop`.
7. The final empty state shows the difference between `pollLast` and `pop`.

The `ArrayList` copies in the example are only for printing the structure when no other party is modifying it. They are not a way to turn a concurrently updated source into a globally consistent snapshot.

The `drain` method stops when `poll` returns null. That is appropriate here because no producer is still active. Do not generalize this stopping condition to systems where elements may be added later.

## 4. Use the result of the retrieval, do not rely on a stale observation

### 4.1. `isEmpty` followed by `remove` has a race window

Illustrative snippet that is intentionally problematic when multiple consumers run concurrently:

```java
if (!queue.isEmpty()) {
    String value = queue.remove();
    System.out.println(value);
}
```

One thread observes that the queue still has an element. Before it calls `remove`, another thread takes the last element. The subsequent `remove` encounters an empty queue and can throw `NoSuchElementException`.

Each individual operation can be completely valid. The mistake is that the program treats the earlier check result as a reservation on an element.

### 4.2. A single `poll` both attempts retrieval and returns the result

Non-standalone illustrative snippet, where `queue` is a `ConcurrentLinkedQueue<String>`:

```java
String value = queue.poll();
if (value != null) {
    System.out.println("Da nhan: " + value);
} else {
    System.out.println("Lan nay chua co phan tu");
}
```

Because the class does not allow null elements, null can serve as the signal that the retrieval did not obtain an element. There is no need for a preceding `isEmpty` check.

Similarly, a non-null `peek` does not reserve the right to retrieve that element in the next `poll` call. When multiple consumers contend, an observation of the head can become stale immediately after the method returns.

Two threads simultaneously retrieving the last element with `pollFirst`/`pollLast` on a deque cannot both receive the same occurrence; one side can receive the element and the other receives null. You do not need external locking just to perform a single contract-compliant retrieval call.

### 4.3. Transient null and the termination condition are two separate issues

A consumer sees null when the queue is empty, but a producer may add elements afterward. Therefore, null by itself does not mean:

- All producers have finished.
- No new work will arrive.
- All retrieved work items have finished processing successfully.
- The system can immediately shut down the entire thread pool.

A termination protocol can use a known work count, a properly coordinated completion signal, or non-null sentinel control elements. You must define in advance the condition that the application needs to prove.

## 5. Two-producer, two-consumer program with ConcurrentLinkedQueue

### 5.1. The protocol chosen for the experiment

The following example creates exactly 2,000 work items with distinct IDs. Two tasks insert work at the tail; two tasks retrieve from the head.

So that the consumers know when to stop, the main thread waits for both producers to finish and then inserts **two non-null STOP control elements**; each consumer terminates upon retrieving one STOP.

The protocol is valid within the scope of this example because:

1. All work items are inserted before the main thread inserts STOP.
2. Both work items and STOP are inserted at the tail, while consumers only retrieve from the FIFO head.
3. There are exactly two consumer tasks and two STOP items; each task returns immediately after retrieving one STOP.
4. The main thread waits for both consumer tasks to finish before verifying the summary.

STOP is the same reference inserted twice. The queue allows these two occurrences; it does not use null to signal termination.

### 5.2. Complete program

Save as **`LinkedQueueTransferDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LinkedQueueTransferDemo {
    private static final int PER_PRODUCER = 1_000;
    private static final Work STOP = new Work(-1);

    public static void main(String[] args) throws Exception {
        ConcurrentLinkedQueue<Work> queue = new ConcurrentLinkedQueue<>();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            Future<List<Integer>> consumerA =
                    pool.submit(() -> consume(queue, start));
            Future<List<Integer>> consumerB =
                    pool.submit(() -> consume(queue, start));
            Future<?> producerA = pool.submit(() -> {
                produce(queue, start, 0);
                return null;
            });
            Future<?> producerB = pool.submit(() -> {
                produce(queue, start, PER_PRODUCER);
                return null;
            });
            start.countDown();

            producerA.get(20, TimeUnit.SECONDS);
            producerB.get(20, TimeUnit.SECONDS);
            queue.offer(STOP);
            queue.offer(STOP);

            List<Integer> a = consumerA.get(20, TimeUnit.SECONDS);
            List<Integer> b = consumerB.get(20, TimeUnit.SECONDS);
            Set<Integer> unique = new HashSet<>();
            long sum = 0;
            for (int id : a) {
                require(unique.add(id), "duplicate id");
                sum += id;
            }
            for (int id : b) {
                require(unique.add(id), "duplicate id");
                sum += id;
            }
            int total = 2 * PER_PRODUCER;
            require(a.size() + b.size() == total, "wrong processed count");
            require(unique.size() == total, "missing work");
            require(sum == (long) total * (total - 1) / 2, "wrong checksum");
            require(queue.isEmpty(), "queue must be drained");

            System.out.println("processed = " + (a.size() + b.size()));
            System.out.println("distinct ids = " + unique.size());
            System.out.println("id sum = " + sum);
            System.out.println("queue empty = " + queue.isEmpty());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void produce(ConcurrentLinkedQueue<Work> queue,
            CountDownLatch start, int firstId) throws InterruptedException {
        await(start);
        for (int i = 0; i < PER_PRODUCER; i++) {
            queue.offer(new Work(firstId + i));
        }
    }

    private static List<Integer> consume(ConcurrentLinkedQueue<Work> queue,
            CountDownLatch start) throws InterruptedException {
        await(start);
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
        List<Integer> result = new ArrayList<>();
        while (true) {
            if (Thread.currentThread().isInterrupted()) {
                throw new InterruptedException("consumer interrupted");
            }
            if (System.nanoTime() - deadline >= 0) {
                throw new IllegalStateException("consumer timed out");
            }
            Work work = queue.poll();
            if (work == STOP) {
                return result;
            }
            if (work != null) {
                result.add(work.id());
            } else {
                Thread.onSpinWait();
            }
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("start timed out");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private record Work(int id) {}
}
```

Command to run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all LinkedQueueTransferDemo.java
java LinkedQueueTransferDemo
```

Stdout on a successful run:

```text
processed = 2000
distinct ids = 2000
id sum = 1999000
queue empty = true
```

Each consumer task maintains its own `ArrayList`; no two threads write to the same result list. Only after `Future.get` returns does the main thread read the lists and merge them to check for duplicate IDs, total count, and ID sum.

The program does not print the per-consumer work count because even distribution is not guaranteed. One consumer may process more items than the other. What must be verified is that IDs 0 through 1,999 appear accurately in the combined result.

### 5.3. Important details in the code

**The thread pool has four threads.** If there were only two threads and the two consumer tasks occupied both of them spinning, the two producer tasks could sit in the executor's queue and never get a chance to run. That would be a task coordination bug, not a queue bug.

**`poll` is still non-blocking.** When it sees null, the code runs an active wait loop with interruption and deadline checks. `Thread.onSpinWait` does not turn it into `take`.

This spin loop is only for a small, bounded, deadline-limited experiment. For applications that need to sleep while waiting for work, a `BlockingQueue` with the appropriate blocking operation usually expresses the intent more clearly. Do not copy this spin loop into a long-running service loop without designing the waiting strategy and CPU usage.

**The code checks for interruption and propagates failures.** If a task makes no progress, the deadline fails the test instead of hanging indefinitely. The `finally` block shuts down the thread pool and awaits termination.

**"Processing" in the example is recording the ID in a local list.** Removing an item from the queue does not automatically provide durable acknowledgment, rollback, or retry for an external task. If real work fails after retrieval, the application must define how to handle it next.

### 5.4. Why FIFO does not guarantee completion order

The queue preserves the order of retrievals according to queue order. However, after A retrieves an earlier task, A may be paused; B retrieves a later task and finishes processing before A.

Similarly, when multiple threads call `offer` concurrently, do not use externally measured call timestamps to assume an absolute order different from the order the queue establishes for those operations. Sequential, non-overlapping calls have a clearer ordering relationship.

Do not print logs after processing and then treat the log order as proof that the queue violated FIFO. You must distinguish between insertion time, retrieval time, and work completion time.

One consumer encountering STOP also does not prove that the other consumer has finished processing every element it previously retrieved. That is why the main thread waits for both consumer results.

### 5.5. Do not carry the STOP protocol unchanged to a different two-ended usage

If you insert STOP at the tail of a deque and then retrieve using `pollLast`, a consumer can pick up STOP before older work items still sitting at the head. In that case, the program's FIFO reasoning no longer holds.

Whenever you change the insertion/retrieval ends or change the number of consumers, you must re-determine the number of termination signals and their placement relative to the work items. The collection does not know on its own whether an element is data or a stop signal.

## 6. ConcurrentLinkedDeque program: consuming from both ends simultaneously

### 6.1. Different termination condition from the previous example

In this example, the main thread pre-populates 1,000 numbers into the deque **before submitting the tasks**, and no other thread adds more items. One task retrieves from the head, and the other retrieves from the tail.

Because the source is already closed by the program's rules, when a task receives null, it can stop. There is no need for STOP or waiting on future producers.

Save as **`OppositeEndsDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ConcurrentLinkedDeque;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class OppositeEndsDemo {
    private static final int COUNT = 1_000;

    public static void main(String[] args) throws Exception {
        ConcurrentLinkedDeque<Integer> deque = new ConcurrentLinkedDeque<>();
        for (int i = 0; i < COUNT; i++) {
            deque.offerLast(i);
        }
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Set<Integer>> first =
                    pool.submit(() -> drain(deque, start, true));
            Future<Set<Integer>> last =
                    pool.submit(() -> drain(deque, start, false));
            start.countDown();

            Set<Integer> a = first.get(10, TimeUnit.SECONDS);
            Set<Integer> b = last.get(10, TimeUnit.SECONDS);
            Set<Integer> overlap = new HashSet<>(a);
            overlap.retainAll(b);
            Set<Integer> all = new HashSet<>(a);
            all.addAll(b);
            long sum = all.stream().mapToLong(Integer::longValue).sum();

            require(overlap.isEmpty(), "same occurrence claimed twice");
            require(all.size() == COUNT, "missing element");
            require(sum == (long) COUNT * (COUNT - 1) / 2, "wrong checksum");
            require(deque.isEmpty(), "deque not drained");

            System.out.println("opposite-end claimed = " + all.size());
            System.out.println("overlap = " + overlap.size());
            System.out.println("id sum = " + sum);
            System.out.println("deque empty = " + deque.isEmpty());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static Set<Integer> drain(ConcurrentLinkedDeque<Integer> deque,
            CountDownLatch start, boolean fromFirst) throws InterruptedException {
        if (!start.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("start timed out");
        }
        Set<Integer> result = new HashSet<>();
        Integer value;
        while ((value = fromFirst ? deque.pollFirst() : deque.pollLast()) != null) {
            require(result.add(value), "local duplicate");
        }
        return result;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Command to run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all OppositeEndsDemo.java
java OppositeEndsDemo
```

Stdout on a successful run:

```text
opposite-end claimed = 1000
overlap = 0
id sum = 499500
deque empty = true
```

The two local result sets are disjoint and their union contains all 1,000 elements. When only one element remains, contention between `pollFirst` and `pollLast` does not cause the same occurrence to be returned to both tasks.

One task may drain everything before the other performs many operations; the test does not require a 500/500 split between the two ends. These classes do not promise fair distribution across threads.

### 6.2. Do not call every deque usage FIFO

If you only insert at the tail and retrieve at the head, the deque is used as FIFO. In the opposite-ends example, one task takes elements from the tail while the other takes from the head; this is a different work-claiming rule.

The test only verifies the correctness of the set of retrieved elements; it does not enforce a global processing order in ascending numeric order. If an application needs strict completion ordering, it must have a corresponding work-coordination mechanism.

A deque provides double-ended access. It does not automatically become a complete scheduler, does not partition work ownership by itself, and does not provide priority or fairness policies.

## 7. Limits on memory, observation, and atomicity scope

### 7.1. Unbounded capacity does not mean no throttling is needed

Neither class has a fixed element limit where `offer` returns false because it is full. If producers consistently outpace consumers, the number of nodes and retained data can keep growing.

That is not an automatic backpressure mechanism. JVM memory is still finite; using an unbounded queue does not replace controlling intake rate, bounding in-flight work, or defining an overload policy.

`ConcurrentLinkedQueue` is documented as using a non-blocking algorithm. At the usage level covered here, neither class provides `take`, `put`, or `poll(timeout, unit)` to wait on data or space conditions. This does not promise fixed per-operation latency or fair scheduling across threads.

Do not infer "uses no CPU when there is no work" from the term "non-blocking". A `while (poll() == null)` loop is still driven by the program itself and can consume CPU continuously.

### 7.2. `size` is not a constant-time read

For both classes, `size()` must traverse the structure to count; the documentation explicitly states it is not a constant-time operation. When the structure changes during counting, the result may be inaccurate relative to the point-in-time state you intended to act on. [ConcurrentLinkedQueue — size](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html#size()), [ConcurrentLinkedDeque — size](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html#size())

Do not put `size()` in a hot loop just to check whether an element can be retrieved. Use the return value of `poll` for retrieval; if you only monitor status, keep in mind that the observed value can be transient.

The following patterns do not form atomic protocols:

- `size() > 0` followed by retrieval.
- `size() < limit` followed by insertion.
- `contains(x)` followed by removing or processing `x` as if it were still reserved.
- `peek()` followed by `poll()` assuming you will definitely get the exact same object.

If an invariant must hold across multiple steps or multiple collections, you need a coordination mechanism covering that entire invariant.

### 7.3. Weakly consistent iterators and bulk operations

The iterators and spliterators of both classes are weakly consistent. You can traverse while other threads update the collection, but they must not be treated as a fixed snapshot of the entire structure.

For a deque, the regular iterator goes from head to tail and `descendingIterator` goes from tail to head. Change-visibility policy and traversal order are two different properties: weak consistency does not mean losing all ordering rules.

Bulk operations such as `addAll`, `removeIf`, and `forEach` are not guaranteed to be atomic as a single block. Concurrent readers may observe partial effects of a batch insertion. [ConcurrentLinkedDeque — traversal policy and bulk operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html)

The absence of `ConcurrentModificationException` does not prove that a report reflects all numbers from the same version. Likewise, `toArray` or copying into a new collection does not elevate the consistency level of collecting from a mutating source.

If you need a consistent snapshot, define a shared protocol for all updaters and snapshotters, or design versioned state. External locking in one place does not force threads that only call the queue/deque API to acquire that lock.

### 7.4. Publishing an element does not keep its internal state synchronized forever

The memory consistency contract of concurrent collections specifies that actions prior to placing an object into the collection happen-before actions subsequent to another thread accessing or removing that object according to the contract. This supports constructing data and transferring it through the queue. [java.util.concurrent — Memory Consistency Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility)

However, the queue/deque stores and returns references; it does not deep-copy objects. If a producer continues mutating ordinary fields after insertion while a consumer is reading them, those subsequent mutations still need their own protection mechanism.

The two multithreaded programs use `Integer` IDs or a record containing only an `int`, avoiding element state that can be mutated after publication. For business objects with multiple related fields, define clear ownership or immutability/field-coordination rules.

### 7.5. Null is forbidden on input, but valid as a return signal

The following illustrative statements intentionally violate the contract:

```java
queue.offer(null);       // NullPointerException.
deque.offerFirst(null);  // NullPointerException.
deque.offerLast(null);   // NullPointerException.
```

The variables here are understood to be the two classes under study; this snippet is not a standalone program. Constructors accepting a collection also reject a null source or null elements.

Conversely, `poll/peek` and their double-ended variants return null when no suitable element is available on that call. A returned null is not a stored null element.

If business data genuinely has a "no value" state, use a non-null element object to represent that state by design. If you need a stop signal, use a sentinel control element that cannot be confused with normal data; do not insert null.

## 8. Removing by value and choosing a structure by need

### 8.1. Removing head/tail vs. removing a single occurrence

`pollFirst`/`pollLast` select by head or tail position. `removeFirstOccurrence(x)`/`removeLastOccurrence(x)` search for an element equal to `x` in the corresponding direction.

Sequential illustrative snippet, with `Deque`, `List`, and `ConcurrentLinkedDeque` imported:

```java
Deque<String> values = new ConcurrentLinkedDeque<>(
        List.of("A", "B", "A", "C", "A"));

values.removeFirstOccurrence("A"); // [B, A, C, A]
values.removeLastOccurrence("A");  // [B, A, C]
values.remove("A");                // [B, C]
```

A deque's `remove(Object)` is equivalent to removing the first occurrence. If the value is not found, value-based removal returns false. It does not have the same meaning as the zero-argument `remove()`, which retrieves the head and throws an exception when empty.

Value-based search/removal operations do not simply pick one end directly. If an application primarily looks up or removes by key, consider whether a key-based structure or another index is more appropriate, rather than treating a queue like a map.

### 8.2. Selection table by requirement

| Need | Approach to consider | What must be defined |
| --- | --- | --- |
| Multiple threads adding at tail / removing at head, non-blocking retrieval | `ConcurrentLinkedQueue` | Termination, overload, post-retrieval processing errors |
| Need concurrent selection at both head and tail | `ConcurrentLinkedDeque` | Specific insertion/retrieval ends and ordering semantics |
| Need to sleep waiting for work or wait with a timeout | Appropriate `BlockingQueue` | Interruption, timeout, termination, and whether capacity bounds are needed |
| Need blocking wait at both ends | Appropriate `BlockingDeque` | Head/tail rules and capacity |
| Data owned by only a single thread | Standard structure suited to the need | No sharing outside that ownership |
| Need deduplication by ID | Protocol with a set/map or suitable work-claiming mechanism | Deduplication scope and ID lifecycle |
| Need durable work storage / crash recovery | Appropriate storage and acknowledgment mechanism | In-memory queues do not provide this by themselves |

`BlockingQueue` adds operations such as `take`, `put`, and timed retrieval/insertion; implementations exist both with and without capacity bounds. `BlockingDeque` extends that model to both ends. [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html), [BlockingDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html)

Adding the word "concurrent" to a data structure's name does not mean the architecture is settled. Requirements for waiting, bounds, ordering, and task lifecycle must be specified upfront.

### 8.3. Test against contracts, not lucky scheduling

With multiple threads, verify the expected number of items received, the set of IDs, duplicates, termination conditions, and observed task failures.

Do not assert that two consumers must receive an even split, do not treat completion logs as queue retrieval order, and do not use `sleep` to prove that producers have definitely finished.

The three programs in this lesson are runnable demonstrations of their defined protocols. They are not performance benchmarks and do not prove that every protocol using these two classes is correct. Whenever you change how items are added/removed or how termination is signaled, you must re-analyze interleavings and invariants.

## 9. Practice

### Exercise 1 — Queue empty for a moment

A consumer calls `poll()`, sees null, and stops; producers are still active.

**Question:** Was the retrieval call wrong? Is the stopping protocol justified?

**Check:** The retrieval call can be completely valid because the queue was empty at that moment. Stopping permanently requires knowing there will be no future data or having another termination signal; a transient null does not provide that.

### Exercise 2 — FIFO and output print order

A retrieves task 1 and takes a long time; B retrieves task 2 and prints its result before A.

**Question:** Can you conclude that `ConcurrentLinkedQueue` violated FIFO?

**Check:** No. Retrieval order and completion order are two different events. Observe the exact boundary that the FIFO contract describes.

### Exercise 3 — STOP at the wrong end

A program inserts all work items using `offerLast`, then inserts STOP using `offerLast`, but the consumer uses `pollLast`.

**Question:** Why can it stop while work items still remain?

**Check:** STOP is at the tail, so it is retrieved before older work items at the head. A protocol that appends a trailing signal based on FIFO no longer fits that LIFO/tail-retrieval pattern.

### Exercise 4 — Inserting the same object twice

A work object is inserted twice. Two consumers both retrieve a reference to that object.

**Question:** Did the queue necessarily deliver a single occurrence twice? Do you need to consider the object's internal state?

**Check:** There are two valid occurrences because the queue allows duplicates. Two retrievals can receive the same reference from two different positions. If both consumers mutate the object, the object's state requires a separate protocol.

### Exercise 5 — Bounding with `size`

Two producers both check `queue.size() < 100` and then insert.

**Question:** Can the queue be considered bounded to a maximum capacity of 100?

**Check:** No. Counting can be expensive and stale under concurrent updates, and check-then-insert is a multi-step sequence. Neither class has that intrinsic bound either. Enforcing a bound requires a mechanism suited to the requirement.

### Exercise 6 — Both ends, but only one element

A deque has one element and no remaining producers. A calls `pollFirst`, B calls `pollLast`.

**Question:** Can both sides receive the same occurrence? Can the side that sees null stop under the stated condition?

**Check:** Only one retrieval receives the element; the other can receive null. Because it is known that no producers remain, that task may stop, while final aggregation must still wait for the other task to finish processing the element it retrieved.

## 10. Reference documentation

- [ConcurrentLinkedQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): FIFO, null prohibition, traversal, and bulk-operation limits.
- [ConcurrentLinkedDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html): double-ended access, bidirectional iterators, and occurrence-based removal.
- [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html), [Deque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html): semantics of each method group.
- [java.util.concurrent Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): data publication guarantees and concurrent collection families.
- [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html), [BlockingDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html): comparison for waiting and capacity-bound needs.
