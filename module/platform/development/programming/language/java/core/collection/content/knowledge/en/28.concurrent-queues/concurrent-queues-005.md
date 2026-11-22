# PriorityBlockingQueue and Practical Capacity Limits

`PriorityBlockingQueue` solves **priority-based element selection in a multithreaded environment**. It does not by itself solve **bounding the amount of admitted work**.

Those two requirements often go together in a scheduler, yet they are two independent decisions:

- Among the tasks already admitted and waiting, which one should be taken first?
- When there is already too much unprocessed work, should more be admitted?

A common mistake is assuming `new PriorityBlockingQueue<>(100)` can only hold `100` tasks, or thinking `put` will block producers once that level is reached. The constructor argument is the **initial capacity**, not the maximum capacity.

This lesson uses the Java 17 API to explain priority ordering, practical memory limits, and an admission-bounding example with an explicit permit protocol.

Key terms to distinguish:

- **Initial capacity:** the starting storage size from which the structure can grow as elements are added.
- **Admission limit:** the quantity an application allows to be held within a defined scope.
- **Dequeue priority:** the selection order among elements currently eligible to be taken.
- **In-flight work:** elements that have already left the queue and no longer participate in queue selection.
- **Backpressure:** signaling overload back to the sender via waiting, rejection, or an explicit policy.
- **Permit:** a unit of budget acquired before admission and returned at the exact resource-release point.

## 1. What Does PriorityBlockingQueue Actually Guarantee?

`PriorityBlockingQueue` is a concurrent queue **unbounded in capacity by class policy**, using natural ordering or a `Comparator` to select elements. Insertion can still fail due to resource exhaustion, such as `OutOfMemoryError`; “unbounded” does not mean the machine has infinite memory. [Java 17: PriorityBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html)

The word `Blocking` should be read according to its specific contract:

- `take` can wait when no element is available.
- `poll(timeout, unit)` can wait for an element up to a specified duration.
- `put` does not wait for free space due to a full queue, because the class has no such capacity limit.
- Timed `offer` does not create an admission limit.

You can picture it as:

~~~text
Producer side:
    valid insertion -> the queue can grow its storage

Consumer side:
    empty queue -> take waits
    non-empty queue -> takes the head element according to priority order
~~~

This is a queue that blocks on the consumer side when empty, not a fixed-capacity priority buffer.

## 2. initialCapacity Is Not maximumCapacity

An illustration inside a method:

~~~java
java.util.concurrent.PriorityBlockingQueue<Integer> queue =
        new java.util.concurrent.PriorityBlockingQueue<>(1);

queue.offer(30);
queue.offer(10);
queue.offer(20);
~~~

Three elements can be admitted even though the constructor received `1`. The class is permitted to expand its storage.

The same is not true for `ArrayBlockingQueue<>(1)`, where the argument is the fixed capacity of the buffer. Reading the same number across two different constructors while ignoring the parameter name can lead to a completely wrong overload design.

### 2.1. remainingCapacity Is a Contract Signal

`PriorityBlockingQueue.remainingCapacity()` always returns `Integer.MAX_VALUE` because the class is not capacity-bounded by contract. [Java 17: PriorityBlockingQueue.remainingCapacity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html#remainingCapacity())

Do not interpret that result as:

- The machine still has enough memory for that exact number of elements.
- This is an actual count of pre-reserved free slots.
- `size + remainingCapacity` is the application's business limit.
- The next insertion is guaranteed not to fail from resource exhaustion.

It is a signal indicating that the queue has no intrinsic bounded-buffer policy.

### 2.2. Setting a Very Large initialCapacity Does Not Create a Limit Either

Pre-sizing a large capacity can affect initial allocation and the number of later resizes. It does not prevent the queue from growing beyond that level.

If you need a work budget, you must implement a separate admission mechanism. Do not use initial storage configuration as a substitute for a business rule.

## 3. put and Timed offer Do Not Make Producers Wait When Full

| Method on PriorityBlockingQueue | Capacity-Related Meaning |
|---|---|
| `offer(item)` | Does not return `false` due to running out of space under an intrinsic capacity limit. |
| `add(item)` | Inserts according to the class contract; do not use it as a check against a constructor-supplied maximum. |
| `put(item)` | Does not wait for space due to a full queue. |
| `offer(item, timeout, unit)` | Does not wait for capacity; the timeout parameter does not create a bounded admission mechanism. |
| `take()` | Can wait because the queue is empty. |
| `poll(timeout, unit)` | Can wait for an element when empty, then return `null` if the timeout expires without one. |

The Javadoc states clearly that `put` does not block due to capacity and timed `offer` does not block or return `false` on a full condition; the timeout parameter of timed `offer` is ignored in this class. [Java 17: put and timed offer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html#offer(E,long,java.util.concurrent.TimeUnit))

Understand “does not wait for full” within its proper scope. The class still has to coordinate internal access, perform comparisons, and potentially allocate/grow the backing array. Do not assume an insertion always completes in constant time, with zero contention, or with zero allocation cost.

The OpenJDK 17 source code shows `put` and timed `offer` delegating to the `offer` insertion path, which still uses an internal lock and handles storage growth. [OpenJDK 17: PriorityBlockingQueue](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/concurrent/PriorityBlockingQueue.java)

### 3.1. Swapping ArrayBlockingQueue for PriorityBlockingQueue Changes Load Throttling

A system relying on `ArrayBlockingQueue.put` to slow down producers will lose that capacity-waiting mechanism if it merely switches to `PriorityBlockingQueue`.

The change may still compile because both classes implement `BlockingQueue`. However, their capacity contracts differ. Type compatibility alone is not enough to prove behavioral compatibility.

### 3.2. Not Waiting for Full Does Not Mean Accepting Any Input

`PriorityBlockingQueue` does not accept `null`. If natural ordering is used, elements must be mutually comparable; incomparable data can cause `ClassCastException`.

A broken comparator, invalid data, or resource exhaustion remain separate issues. Do not lump every failure together as a capacity-overload outcome.

## 4. Priority Is the Selection Order Among Waiting Elements

A priority queue selects the smallest element according to the specified order. If you want `1` to represent higher urgency than `5`, an ascending comparator on the priority field is appropriate.

Example immutable data type and comparator:

~~~java
record Work(String name, int priority, long sequence) {}

java.util.Comparator<Work> order =
        java.util.Comparator.comparingInt(Work::priority)
                            .thenComparingLong(Work::sequence);
~~~

This snippet uses Java 17 syntax in an appropriate declaration scope. The comparator evaluates `priority` first, then `sequence`. Comparator factory methods help avoid subtraction tricks that can overflow during comparison. [Java 17: Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

### 4.1. Equal Priority Does Not Automatically Give FIFO

`PriorityBlockingQueue` does not guarantee ordering among elements with equal priority. If you need a tie-breaker order, include it in the comparator.

A sequence number assigned at request creation can serve as a secondary criterion. However, in a multithreaded environment, the sequence-assignment order and the actual queue-admission order can differ. You must define whether “arrived first” means created first, started calling first, or admitted first.

The program example uses an explicitly assigned sequence, so ordering is verified against that metadata; it does not claim to recover every external notion of FIFO.

### 4.2. In-Flight Elements Are No Longer Reordered by the Queue

A less urgent task already taken by a consumer may be running when a more urgent task is inserted. A priority queue does not automatically pause or preempt an in-flight task.

With multiple consumers, dequeue order also does not guarantee completion order. Tasks can take different amounts of time or be affected by other resources.

### 4.3. Priority Does Not Create Long-Term Fairness

If urgent tasks arrive continuously, less urgent tasks can wait for a very long time. That is a scheduling-policy starvation issue, distinct from queue thread-safety.

If you need bounded wait times per group, you may need per-group budgets, weighted rotation, or a dedicated priority-aging mechanism. Simply adding a priority field does not automatically provide fairness guarantees.

### 4.4. Do Not Mutate Ordering Fields While an Element Is in the Heap

The queue does not track arbitrary mutations inside objects that have already been inserted. If you mutate priority in place, the heap is not automatically re-sorted for the new value.

Prefer immutable values. When priority must change, use an explicit update protocol such as removing and re-inserting; note that those two calls do not automatically form a single transaction with other parties.

Similarly, a comparator that depends on changing external state, such as the current time, does not cause the heap to continuously rebalance itself. Design the scheduling algorithm accordingly.

## 5. Iteration Differs from Priority Dequeue

A heap only guarantees how the head element is selected; the backing array does not need to be fully sorted in ascending order.

Therefore, do not use `iterator`, `for-each`, `toString`, or `toArray` to infer that all elements appear in priority order. `PriorityBlockingQueue` does not promise that iteration order.

If you only want to inspect or export ordered data:

1. Take a separate snapshot using an appropriate API.
2. Sort that snapshot with the same comparator.
3. Understand that subsequent updates may cause the snapshot to differ from the live source.

If you want to **remove elements for processing**, use `take`/`poll` per the contract or `drainTo` to extract a batch in priority order. `drainTo` mutates the queue; it is not a non-destructive view.

Plain `PriorityQueue` also separates heap-head order from iterator order, but it does not provide synchronization for concurrent updates like `PriorityBlockingQueue` does. [Java 17: PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

Do not replace `PriorityBlockingQueue` with `PriorityQueue` simply because a program still “picks the smallest number” in a single-threaded test.

## 6. Practical Limits Come from Memory and Unfinished Work

The queue can grow, yet each element still retains data:

- References in the storage structure.
- Payloads reachable from the element.
- Indirect data such as arrays, strings, request contexts, or task objects.
- Work being constructed on producers prior to admission.
- Work already dequeued and currently executing.

If the arrival rate exceeds the processing rate for long enough, the number of waiting tasks can grow until latency or memory becomes unacceptable.

Priority only chooses the service order among admitted work. It does not reduce total processing volume and does not prevent low-urgency work from accumulating.

### 6.1. Element Count Does Not Equal Byte Count

A limit of `N` elements does not directly bound bytes if payload sizes vary widely. You must define a budget appropriate to your data.

You can bound task count, estimated total data weight, active sessions, or a combination of conditions. The accounting must match the resource you are protecting.

### 6.2. OutOfMemoryError Is Not an Admission Policy

Do not wait until allocation fails and treat that as a normal “queue full” signal. By that point, many other parts of the process may also lack the resources to operate or respond.

Set proactive limits based on memory budget, latency, and processing capacity. The example in this lesson inserts only a small number of items to demonstrate that `initialCapacity` is not a bound; it does not attempt to exhaust memory.

### 6.3. Choosing When to Release the Budget

There are at least two distinct scopes:

- **Bounding waiting work:** return the budget when the element is taken from the queue.
- **Bounding admitted-but-unfinished work:** hold the budget throughout processing, returning it only on completion or cancellation under the protocol.

A semaphore can participate in either model, but the `release` site differs. Releasing on `take` and claiming you have bounded all unfinished work is a scope error.

## 7. An Admission-Bounding Example Using Semaphore

The idea is to acquire a permit before inserting into `PriorityBlockingQueue` and release it once an element has been removed.

`Semaphore` manages the permit count via acquire/release operations; it separates budget management from how the queue orders elements. [Java 17: Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)

Rules of the example:

~~~text
Before admission:
    must acquire a permit

If insertion fails:
    release the permit just acquired

When poll/take actually removes an element:
    release exactly one permit

When poll finds the queue empty:
    do not release a permit
~~~

An element for which a producer holds a permit but has not yet published into the queue also consumes budget. That prevents two producers from consuming the same slot just because both observed a small `size`.

### 7.1. Keep the Internal Queue Encapsulated

Do not expose the backing queue directly so callers can invoke `offer` while bypassing permit acquisition. Do not allow an unguarded `clear`/`remove`/`drainTo` path to remove elements without returning budget.

The example provides only a small set of methods wired to permits. It **does not implement the full BlockingQueue interface**, so it is not a drop-in replacement wherever a `BlockingQueue` is required.

If you expand the API, every insertion, removal, cancellation, and error path must preserve the same invariant.

### 7.2. Do Not Wait While Holding a Lock Needed by Consumers

`Semaphore` can wait for a permit. That wait must not hold an external lock that prevents consumers from taking elements or releasing permits.

Permits are a budget, not a shortcut replacing all data-structure synchronization. The queue still uses its own concurrency contract.

## 8. Standalone Runnable Program

Save the file as `PriorityCapacityDemo.java`. The program uses the Java 17 API, was compiled with `javac --release 17`, and was run on OpenJDK Zulu 24.0.2. Do not treat this as proof of execution on a Java 17 JVM.

The `PriorityBuffer` class is an example that bounds **waiting items plus reserved-but-unpublished slots**, not all executing work. It uses an explicit comparator and does not expose the backing queue.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.PriorityBlockingQueue;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class PriorityCapacityDemo {
    record Work(String name, int priority, long sequence) {}

    static final Comparator<Work> ORDER =
            Comparator.comparingInt(Work::priority)
                      .thenComparingLong(Work::sequence);

    static final class PriorityBuffer<E> {
        private final PriorityBlockingQueue<E> queue;
        private final Semaphore free;

        PriorityBuffer(int capacity, Comparator<? super E> comparator) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            queue = new PriorityBlockingQueue<>(Math.min(capacity, 11),
                                                Objects.requireNonNull(comparator));
            free = new Semaphore(capacity);
        }

        private void publishReserved(E item) {
            boolean inserted = false;
            try {
                inserted = queue.offer(item);
                if (!inserted) {
                    throw new AssertionError("Unexpected priority queue rejection");
                }
            } finally {
                if (!inserted) {
                    free.release();
                }
            }
        }

        boolean offer(E item) {
            Objects.requireNonNull(item);
            if (!free.tryAcquire()) {
                return false;
            }
            publishReserved(item);
            return true;
        }

        boolean offer(E item, long timeout, TimeUnit unit)
                throws InterruptedException {
            Objects.requireNonNull(item);
            if (!free.tryAcquire(timeout, unit)) {
                return false;
            }
            publishReserved(item);
            return true;
        }

        void put(E item) throws InterruptedException {
            Objects.requireNonNull(item);
            free.acquire();
            publishReserved(item);
        }

        E poll() {
            E item = queue.poll();
            if (item != null) {
                free.release();
            }
            return item;
        }

        E take() throws InterruptedException {
            E item = queue.take();
            free.release();
            return item;
        }
    }

    static List<String> names(List<Work> work) {
        return work.stream().map(Work::name).toList();
    }

    static void await(CountDownLatch event) throws InterruptedException {
        if (!event.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Event timed out");
        }
    }

    static void finish(Thread thread, AtomicReference<Throwable> problem)
            throws InterruptedException {
        thread.join(5000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Thread timed out");
        }
        if (problem.get() != null) {
            throw new AssertionError("Thread failed", problem.get());
        }
    }

    public static void main(String[] args) throws Exception {
        PriorityBlockingQueue<Integer> raw = new PriorityBlockingQueue<>(1);
        raw.offer(5);
        raw.offer(2);
        raw.offer(8);
        raw.offer(1);
        raw.put(3);
        System.out.println("timed-offer-zero = "
                + raw.offer(4, 0, TimeUnit.NANOSECONDS));
        System.out.println("initial-one-current-size = " + raw.size());
        System.out.println("raw-remainingCapacity = " + raw.remainingCapacity());
        List<Integer> rawOrder = new ArrayList<>();
        raw.drainTo(rawOrder);
        System.out.println("raw-priority-order = " + rawOrder);

        PriorityBlockingQueue<Work> scheduled = new PriorityBlockingQueue<>(1, ORDER);
        scheduled.add(new Work("low", 5, 3));
        scheduled.add(new Work("same-later", 1, 2));
        scheduled.add(new Work("same-earlier", 1, 1));
        List<Work> display = new ArrayList<>(scheduled);
        display.sort(ORDER);
        System.out.println("sorted-display = " + names(display));
        List<Work> drained = new ArrayList<>();
        scheduled.drainTo(drained);
        System.out.println("drained-order = " + names(drained));
        System.out.println("scheduled-size-after-drain = " + scheduled.size());

        PriorityBlockingQueue<String> empty = new PriorityBlockingQueue<>();
        CountDownLatch beforeTake = new CountDownLatch(1);
        AtomicReference<String> received = new AtomicReference<>();
        AtomicReference<Throwable> takeProblem = new AtomicReference<>();
        Thread taker = new Thread(() -> {
            try {
                beforeTake.countDown();
                received.set(empty.take());
            } catch (Throwable ex) {
                takeProblem.set(ex);
            }
        }, "empty-taker");
        taker.setDaemon(true);
        taker.start();
        await(beforeTake);
        System.out.println("take-received-before-offer = " + (received.get() != null));
        empty.offer("ready");
        finish(taker, takeProblem);
        System.out.println("take-received-after-offer = " + received.get());

        PriorityBuffer<Work> bounded = new PriorityBuffer<>(2, ORDER);
        System.out.println("bounded-offer-low = "
                + bounded.offer(new Work("low", 5, 1)));
        System.out.println("bounded-offer-high = "
                + bounded.offer(new Work("high", 1, 2)));
        System.out.println("bounded-offer-urgent-full = "
                + bounded.offer(new Work("urgent", 0, 3)));
        System.out.println("bounded-timed-offer-full = "
                + bounded.offer(new Work("later", 2, 4), 0, TimeUnit.NANOSECONDS));
        System.out.println("bounded-first = " + bounded.take().name());
        System.out.println("bounded-offer-urgent-after-space = "
                + bounded.offer(new Work("urgent", 0, 3)));
        System.out.println("bounded-next = " + bounded.take().name());
        System.out.println("bounded-last = " + bounded.take().name());
        System.out.println("bounded-poll-empty = " + bounded.poll());

        PriorityBuffer<Integer> waiting = new PriorityBuffer<>(1, Integer::compare);
        waiting.put(9);
        CountDownLatch beforePut = new CountDownLatch(1);
        CountDownLatch afterPut = new CountDownLatch(1);
        AtomicReference<Throwable> putProblem = new AtomicReference<>();
        Thread putter = new Thread(() -> {
            try {
                beforePut.countDown();
                waiting.put(1);
                afterPut.countDown();
            } catch (Throwable ex) {
                putProblem.set(ex);
            }
        }, "bounded-putter");
        putter.setDaemon(true);
        putter.start();
        await(beforePut);
        System.out.println("bounded-put-returned-before-space = "
                + (afterPut.getCount() == 0));
        System.out.println("bounded-existing-item = " + waiting.take());
        await(afterPut);
        finish(putter, putProblem);
        System.out.println("bounded-new-item = " + waiting.take());

        PriorityBuffer<Integer> cancelled = new PriorityBuffer<>(1, Integer::compare);
        cancelled.put(7);
        CountDownLatch attempting = new CountDownLatch(1);
        AtomicBoolean wasInterrupted = new AtomicBoolean();
        AtomicReference<Throwable> cancelProblem = new AtomicReference<>();
        Thread cancelledPutter = new Thread(() -> {
            try {
                attempting.countDown();
                cancelled.put(1);
            } catch (InterruptedException ex) {
                wasInterrupted.set(true);
                Thread.currentThread().interrupt();
            } catch (Throwable ex) {
                cancelProblem.set(ex);
            }
        }, "cancelled-putter");
        cancelledPutter.setDaemon(true);
        cancelledPutter.start();
        await(attempting);
        cancelledPutter.interrupt();
        finish(cancelledPutter, cancelProblem);
        System.out.println("bounded-cancelled = " + wasInterrupted.get());
        System.out.println("bounded-offer-while-held = " + cancelled.offer(2));
        System.out.println("bounded-held-item = " + cancelled.poll());
        System.out.println("bounded-offer-after-take = " + cancelled.offer(2));
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 PriorityCapacityDemo.java
java PriorityCapacityDemo
~~~

Verified stdout:

~~~text
timed-offer-zero = true
initial-one-current-size = 6
raw-remainingCapacity = 2147483647
raw-priority-order = [1, 2, 3, 4, 5, 8]
sorted-display = [same-earlier, same-later, low]
drained-order = [same-earlier, same-later, low]
scheduled-size-after-drain = 0
take-received-before-offer = false
take-received-after-offer = ready
bounded-offer-low = true
bounded-offer-high = true
bounded-offer-urgent-full = false
bounded-timed-offer-full = false
bounded-first = high
bounded-offer-urgent-after-space = true
bounded-next = urgent
bounded-last = low
bounded-poll-empty = null
bounded-put-returned-before-space = false
bounded-existing-item = 9
bounded-new-item = 1
bounded-cancelled = true
bounded-offer-while-held = false
bounded-held-item = 7
bounded-offer-after-take = true
~~~

The latches establish test ordering without using `Thread.sleep` to guess waiting states. The five-second timeouts only ensure verification fails with an error instead of hanging indefinitely.

## 9. Reading the Output

### 9.1. Initial Capacity of 1 Still Holds 6 Elements

~~~text
timed-offer-zero = true
initial-one-current-size = 6
raw-remainingCapacity = 2147483647
~~~

The queue accepted four `offer` calls, one `put`, and one timed `offer` with a `0` timeout. There is no constructor-enforced maximum of `1`. The zero-timeout `offer` does not reject due to an imaginary “capacity of 1”.

The `remainingCapacity` line prints `Integer.MAX_VALUE` per the contract, not a measurement of the machine's free memory.

### 9.2. Output Order Comes from Dequeue Operations

~~~text
raw-priority-order = [1, 2, 3, 4, 5, 8]
~~~

`drainTo` extracts elements in priority order when no other party is updating the queue during the check.

For `Work` items, the comparator uses `priority` first, then `sequence`:

~~~text
sorted-display = [same-earlier, same-later, low]
drained-order = [same-earlier, same-later, low]
~~~

The display copy is sorted separately; the drained list is removed from the queue. Matching data in a quiescent test does not mean the two operations have the same effect. After draining, the queue is empty.

### 9.3. Blocking Behavior Appears on take When Empty

~~~text
take-received-before-offer = false
take-received-after-offer = ready
~~~

The latch signals that the consumer thread has reached the `take` call. With no element and no `offer` yet, it cannot have received anything. Once `ready` is inserted, `take` completes.

There is no need to inspect `Thread.State` to prove a specific internal wait; what needs verification is that the element is returned only after data becomes available.

### 9.4. Wrapper Bounds Differ from Backing-Queue Limits

~~~text
bounded-offer-low = true
bounded-offer-high = true
bounded-offer-urgent-full = false
bounded-timed-offer-full = false
~~~

The wrapper has two permits. Two elements have consumed the budget, so new requests are rejected or fail to acquire a permit within the `0` timeout.

This `false` comes from the wrapper's admission rule, not from the backing `PriorityBlockingQueue` hitting its `initialCapacity`.

### 9.5. Even an Urgent Task Can Be Rejected Before Admission

`urgent` has priority `0`, which is higher under the example's convention, yet it is still rejected when both slots are occupied.

After `high` is taken, a permit is released; `urgent` is admitted and becomes the next element taken:

~~~text
bounded-first = high
bounded-offer-urgent-after-space = true
bounded-next = urgent
bounded-last = low
~~~

This separates **admission policy** from **dequeue policy**. Priority does not automatically allow a request to exceed the budget or evict an existing element.

### 9.6. Wrapper put Can Wait; Backing PBQ put Does Not Wait for Capacity

The capacity-one wrapper already holds `9`. The `put` of `1` has not completed before space opens up. The consumer still takes `9` because `1` has not been admitted to the queue yet:

~~~text
bounded-put-returned-before-space = false
bounded-existing-item = 9
bounded-new-item = 1
~~~

Do not assume that because a producer has an urgent task waiting for a permit, that task already participates in the heap ordering. Only admitted elements are eligible for queue selection.

### 9.7. Cancelling Before Acquiring a Permit Does Not Over-Release Budget

In the cancellation section, one slot is occupied by `7`. A producer waiting for a permit for `1` is interrupted.

~~~text
bounded-cancelled = true
bounded-offer-while-held = false
bounded-held-item = 7
bounded-offer-after-take = true
~~~

The cancelled wait never held a permit, so it must not call `release` as if it had acquired one. When `7` is actually taken, exactly one permit is released and the next `offer` succeeds.

## 10. Reasoning About the Example's Invariant

For capacity `C`, every element in the queue must be backed by an acquired and unreturned permit. A producer that has not acquired a permit cannot reach the publication path.

In-use permits can correspond to:

- Elements already published and still in the queue.
- Slots reserved by a producer that has not finished inserting yet.
- Elements just removed from the queue whose permit release has not finished executing yet.

Therefore, the actual number of elements in the queue never exceeds `C` as long as all access goes through the wrapper and the comparator/elements obey their contracts.

### 10.1. Failed Insertion Branch

After acquiring a permit, if the insertion path does not complete successfully, `finally` returns the permit. This avoids permanently leaking a unit of budget for an item that was never admitted.

The comparator in the example is a short, stable comparison over immutable components. Do not build a protocol around a comparator that has side effects, varies randomly, or throws exceptions to control admission.

### 10.2. Empty Poll Branch

`poll` only releases a permit when it actually returns a non-`null` element. If every empty `poll` also released a permit, permits could grow past `capacity` and the wrapper would lose its bound.

This is a common bug when putting `finally` at the wrong scope: “a removal method was called” is different from “an element was actually removed.”

### 10.3. Interrupted Wait Branch

If `free.acquire` throws `InterruptedException` before acquiring a permit, no permit needs to be released. If the permit was already acquired and insertion succeeded, the element follows the normal admission lifecycle.

The cancellation example is placed in the phase before a permit is held, so its outcome is deterministic. It does not claim that an interrupt at an arbitrary instant can always retract an already-admitted element. Task cancellation and admission rollback require a separate protocol.

### 10.4. Timed offer Only Budgets the Permit Wait

In the wrapper, the timeout parameter applies to `Semaphore.tryAcquire`. Once a permit is acquired, the insertion path still needs to perform the queue operation and comparisons.

Do not treat this as a real-time guarantee for the entire method. If a production API needs a strict end-to-end deadline, you must define the scope and handle the remaining steps accordingly.

### 10.5. Expanding the API Requires Expanding the Proof

If you add `remove`, `clear`, `drainTo`, or a removable iterator, you must release budget for the exact number of elements actually removed and handle errors consistently.

Do not pass the backing queue directly to an executor or another utility and expect it to know about returning permits. The demonstration class intentionally includes only the methods that uphold the full protocol; any broader integration requires a complete design for that interface.

## 11. Admission Limits Do Not Solve Every Scheduling Problem

### 11.1. When Full of Low-Urgency Work

A late-arriving urgent task can be rejected, as shown in the example. If the requirement is to always have room for urgent tasks, a different policy is needed: per-class budgets, multiple queues, or explicit eviction/replacement rules.

Do not simply call an arbitrary `remove` before `offer` and treat that as a proper bounded priority buffer. Deciding who to evict, who to admit, how to return budget, and how to report dropped work must all be coordinated.

### 11.2. Bounding Waiting Work Differs from Bounding Unfinished Work

The wrapper releases a permit when `take`/`poll` removes an element. With multiple consumers, work executing outside the queue still consumes resources.

To bound total admitted-but-unfinished work, you must hold the budget across processing and confirm completion or cancellation exactly once. That also requires handling consumer failures, retries, and recovery. That is a different protocol from the class demonstrated here.

### 11.3. Waiting for a Permit Does Not Stop Producers from Building Payloads

A producer might build a very large object before blocking on `put`. If many producers do this, the amount of data sitting outside the queue can still be large.

Place budget boundaries where resources are allocated and propagate overload signals back to the true source. Do not count only the queue's heap contents while ignoring objects waiting outside.

### 11.4. Poison Objects in a Priority Queue Require Extra Care

A sentinel/poison object is also subject to the comparator. If it is treated as highest priority, consumers may pick up the poison object ahead of remaining normal tasks. If it is lowest priority, new arrivals can delay it indefinitely.

`PriorityBlockingQueue` has no built-in `close`. A protocol for stopping admission, draining remaining work, and shutting down consumers must be designed alongside priority ordering—do not blindly copy a FIFO queue's poison-pill pattern while ignoring the comparator. [Java 17: BlockingQueue and shutdown](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

## 12. Using with ThreadPoolExecutor

`ThreadPoolExecutor` typically attempts to place tasks into its work queue once core thread count is reached. If the queue accepts the task, it stays queued; scaling up to maximum pool size is tied to the queue rejecting the insertion under its admission algorithm. [Java 17: ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

Because a plain `PriorityBlockingQueue` does not return `false` due to being full, choosing it will not by itself cause the pool to expand under backlog up to max threads or trigger rejection at a small constructor-supplied capacity.

In addition, every task actually placed into the priority queue must be comparable under the queue's rules. Task-wrapping layers can change the runtime type of submitted objects, so executor priority designs must inspect the actual submission path.

The `PriorityBuffer` example above does not implement `BlockingQueue` and is not presented as a work queue you can pass directly to an executor constructor. If integration is needed, you must provide a complete interface implementation that preserves the bound across every path the executor uses.

The purpose of the example is to demonstrate separating the **admission budget** from **heap ordering**, without assuming external components already know the permit protocol.

## 13. Observing and Testing Practical Limits

Track metrics that answer the right questions:

- Waiting element count and wait time by priority group.
- Admission, rejection, cancellation, and completion rates.
- Number of producers waiting for budget.
- Number of in-flight tasks executing outside the queue.
- Retained payload size and processing latency.
- Potential starvation or prolonged delays for low-urgency work.

Tests should verify invariants directly:

1. Constructor initial capacity is not mistaken for a maximum limit.
2. The wrapper rejects or blocks properly when permits are exhausted.
3. Empty polls and cancellations before permit acquisition do not inflate the budget.
4. Successful element removal releases exactly one permit.
5. Dequeue order is verified only over elements actually admitted.
6. When a secondary order is needed, it is included in the comparator and explicitly documented.
7. Consumers can continue making progress while producers are waiting.

Do not verify by trying to exhaust the heap or assuming a sleep duration will force threads to interleave as desired. The latches in the program establish clear test states, and growing from an initial capacity of `1` to `6` is enough to prove the contract point being taught.

## 14. Self-Check Exercises

### Exercise 1 — The 100 in the Constructor

`new PriorityBlockingQueue<>(100)` already holds `100` elements. Must the next `offer` return `false`?

**Answer:** No. `100` is the initial capacity, not an admission limit. The class can grow its storage and will not return `false` for such an intrinsic capacity limit.

### Exercise 2 — Timed offer

Why does `offer(item, 1, SECONDS)` on `PriorityBlockingQueue` not create backpressure when the backlog grows?

**Answer:** The class does not wait for space because it has no capacity limit by policy; the timeout parameter on that `offer` overload does not create an admission threshold.

### Exercise 3 — Integer.MAX_VALUE

`remainingCapacity` returns `Integer.MAX_VALUE`. Can that be treated as the number of large payloads guaranteed to fit on the heap?

**Answer:** No. It is a contract value for a capacity-unbounded queue, not a memory measurement and not an allocation guarantee.

### Exercise 4 — Ordered Iteration?

A `for-each` loop prints elements out of ascending order, yet `poll` calls return elements in proper priority order. Is the queue violating its contract?

**Answer:** No. The iterator is not promised to traverse in priority order. Sort a separate snapshot or dequeue using the queue API depending on your goal.

### Exercise 5 — Urgent Task Arriving When Full

The wrapper is full of low-urgency tasks, and a more urgent task is offered and rejected. Does this contradict priority?

**Answer:** No. Admission rules and dequeue rules are two different layers. Reserving room for urgent work requires an additional budget or scheduling policy.

### Exercise 6 — Empty Poll

A wrapper calls `semaphore.release()` on every `poll`, even when it returns `null`. What is wrong?

**Answer:** It releases a permit without freeing any element, inflating the budget and allowing the bound to be exceeded. Only release when an element is actually taken.

### Exercise 7 — Taken but Still Running

The wrapper releases the permit immediately after `take`. Does it bound the total number of unfinished tasks?

**Answer:** No. It bounds waiting items plus reserved slots. Already-taken tasks still consume resources outside the queue. Bounding all unfinished work requires a different release point and a completion protocol.

### Exercise 8 — Highest-Priority Poison Object

A priority queue holds many normal tasks. Does inserting a poison object with highest priority and having consumers exit upon taking it guarantee the backlog is drained?

**Answer:** No. The poison object may be taken ahead of waiting tasks. You must stop admission and define an explicit drain/cancellation policy before shutting down consumers.

`PriorityBlockingQueue` provides priority selection and blocking when empty. Practical resource limits must be designed at the admission boundary, with an explicit budget and release point; only when both layers align does a scheduler have verifiable overload behavior.
