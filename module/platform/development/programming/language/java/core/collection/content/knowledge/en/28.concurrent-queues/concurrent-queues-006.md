# DelayQueue and the Delayed Contract

## 1. Getting It Right: Being in the Queue Does Not Mean Ready to Be Taken

Suppose a retry request should only be attempted after a backoff interval. We want to place the request into storage immediately, but hand it off to the processor only once it becomes due. If we use a regular queue, the head element is retrieved according to the queue's ordering rules without this time condition. If we inspect elements ourselves and put non-expired ones back, we have to handle waiting, waking up, and reordering whenever a request with an earlier deadline arrives.

`DelayQueue<E extends Delayed>` represents a queue with a time condition. Each element describes when it is due via `Delayed`. The queue locates the candidate with the earliest deadline, but deadline-based retrieval operations only hand over that candidate once its remaining delay has elapsed.

Let us separate three concerns:

1. **Storage:** the element has been inserted into the queue.
2. **Eligibility for retrieval:** the element has reached its deadline.
3. **Executing the work:** application code receives the element and decides what to do.

`DelayQueue` handles the first two. It does not invoke a work-handling method on behalf of the application. Putting an object that has a `run()` method into the queue does not automatically cause that method to run.

For example, suppose we insert three elements with deadlines 30, 10, and 20 into the same queue in that order. At time 0, the queue holds three elements, the head candidate is the element with deadline 10, yet no element can be retrieved by `poll()`. At time 20, the elements with deadlines 10 and 20 are both eligible; the element with deadline 30 remains stored. Insertion order does not determine retrieval order.

In this article, **expired** (or **due**) means the remaining delay is 0 or negative. "Delay expired" does not mean "invalid data to be discarded." An application may retrieve an expired element to perform a completely valid task, such as retrying an operation.

The most common point of confusion is that both of the following can be true at the same time:

- `queue.isEmpty()` returns `false`.
- `queue.poll()` returns `null`.

There is no contradiction: the queue contains data, but no data is currently eligible for delivery through this operation. Therefore, do not use `size() > 0` as proof that a subsequent `take()` call will return immediately.

**Learning objectives:** after this article, you should be able to explain the two methods of `Delayed`, write a stable element with a deadline, distinguish inspection from deadline-based retrieval, and properly handle waiting, interruption, and retries. The first part explains the contract; the three programs that follow verify semantics, waiting mechanics, and a bounded retry flow, respectively.

## 2. Delayed Connects Application Data to Time Rules

### 2.1. Two Methods Describing the Same Deadline

`Delayed` extends `Comparable<Delayed>`. When creating an element type for `DelayQueue`, you must provide both parts:

| Method | Question it answers | Consistency requirement |
| --- | --- | --- |
| `getDelay(TimeUnit unit)` | How much time remains from now until the deadline, in the requested unit? | The value decreases over time and is 0 or negative when due. |
| `compareTo(Delayed other)` | Which element has an earlier deadline? | The ordering must be consistent with the remaining-time ordering. |

This is the contract stated in the [Java 17 Delayed API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Delayed.html). Writing a plausible `getDelay()` alone is not enough: if `compareTo()` places the wrong candidate at the head, the queue's behavior is also wrong.

Let us distinguish:

- **Initial delay:** for example, 5 seconds from creation time.
- **Deadline:** a fixed point obtained by adding the delay to the creation timestamp.
- **Remaining time:** the deadline minus the current time.

For a typical element in this article, the deadline is immutable data; remaining time is recomputed on every call. The passage of the clock causes remaining time to decrease without needing to mutate the element's deadline field.

One incorrect implementation is storing `delay = 5` and always returning 5 seconds. The next time the queue checks, the element still claims "5 seconds remaining"; elapsed time is never reflected. Another incorrect implementation is subtracting the current time once during construction, storing that frozen remainder, and returning that same number forever.

The rule to follow is: **record the deadline; recompute the remainder**.

### 2.2. Do Not Let Priority Order Diverge from Expiration Order

Suppose A is due in one hour while B is already due. If `compareTo()` sorts by name and places A before B, a ready element can be hidden behind a non-ready candidate. You cannot fix this bug merely by making `getDelay()` accurate.

In the programs below, all elements in a queue share the same time domain and compare their immutable deadlines directly:

```java
// Conceptual snippet; not a standalone runnable program.
return Long.compare(deadline, item.deadline);
```

Do not replace this with `(int) (deadline - item.deadline)`. The difference of two `long` values can overflow the `int` range; casting loses information and can even flip the sign. For example, a difference of just a few seconds expressed in nanoseconds already exceeds `Integer.MAX_VALUE`. Using `Long.compare` avoids subtraction in the comparison itself, though you still need to design the deadline domain so that stored values are meaningful: it does not automatically fix a deadline calculation that already overflowed earlier.

You also should not call `this.getDelay(...)` and `other.getDelay(...)` at two different instants and subtract them to compare. You would be injecting clock drift into the comparison. Once elements share a reference frame, comparing fixed deadlines is simpler and more stable.

The example classes only accept their own element type. The class using a controlled clock also requires the exact same clock object. This is a constraint in the examples to avoid mixing reference frames. An arbitrary `Delayed` class is not inherently meaningfully comparable to every other `Delayed` class.

Two elements with the same deadline may compare as 0 even though they are different tasks. Do not infer that the queue will deduplicate them or preserve insertion order between them. If your problem requires a stable tie-breaker for equal deadlines, add a stable secondary criterion, such as an incrementing sequence number, and manage that number's lifecycle. The current article does not impose that requirement, so no extra mechanism is added to the code.

### 2.3. The Measurement Unit Is Part of the Contract

The `unit` parameter is not a hint. If the caller asks for nanoseconds and the element returns unconverted seconds, expiration checks will be wildly wrong. A common pattern is to store the deadline in a common unit and convert the remaining time:

```java
// Snippet: remaining is expressed in nanoseconds.
return unit.convert(remaining, TimeUnit.NANOSECONDS);
```

The [TimeUnit API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html) distinguishes unit conversion from timing precision. When converting from a finer unit to a coarser unit, fractional parts are truncated: 1 nanosecond becomes 0 milliseconds. Therefore, `getDelay(MILLISECONDS) == 0` does not prove an element is due if 1 nanosecond still remains.

`DelayQueue` uses the sign of the remaining time in nanoseconds to determine eligibility. The first program intentionally retains exactly 1 nanosecond so you can observe this difference regardless of machine speed.

In the direction of converting to a finer unit, `TimeUnit` saturates results that are too large at the bounds of `long`. This is not input validation on behalf of the application. If a program only supports short intervals, check the range after conversion and reject intervals outside the design. The real-clock examples below bound delays within plus or minus one day.

## 3. Choosing a Clock and Keeping Deadlines Immutable

### 3.1. An In-Process Wait Interval Differs from a Calendar Date-Time

A requirement like "wait another 100 milliseconds" is a problem of measuring elapsed time. `System.nanoTime()` is suited for that purpose. Its value is not a timestamp relative to a calendar epoch, may be negative, and is meaningful only when compared within the same JVM measurement domain.

By contrast, "run at 09:00 tomorrow in the user's time zone" is a calendar requirement. To translate that into a relative wait mechanism, you must decide how to convert it and how to react to clock adjustments or restarts. This article does not turn `nanoTime()` into a persistent schedule.

Do not save a `nanoTime()` deadline into a database and treat it as a timestamp that can be reused after a JVM restart. If you need persistent scheduling, store the appropriate domain time representation, then re-establish the wait interval in the new process.

The [System.nanoTime() API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()) also notes the finite `long` range for elapsed-time differences. Nanosecond measurement does not give us an infinite number line; intervals of roughly 292 years already hit the limit of signed difference representation. When checking whether an interval has elapsed, writing in terms of elapsed differences is often better than assuming deadline addition can never overflow.

### 3.2. Short-Lived Design Used in the Programs

The two real-clock programs below follow an intentional design:

1. A shared `ORIGIN` is captured from `System.nanoTime()`.
2. `elapsed()` computes the time elapsed since that origin.
3. Each element has `deadline = elapsed() + delayNanos`.
4. `getDelay()` computes `deadline - elapsed()`.
5. `compareTo()` compares two `deadline` values in the same reference frame.

`Math.addExact` causes addition to fail loudly when unrepresentable instead of silently wrapping around. The deadline is held in a `final` field. Delays are bounded within plus or minus one day; the programs run briefly and do not retain elements across extreme intervals. Under these assumptions, directly comparing deadline offsets is straightforward.

This is a design for short-lived examples, not a proof that `long` deadline addition/subtraction is safe for every system lifetime. `Math.addExact` on addition does not automatically protect every subtraction in a process running for hundreds of years. When changing the usage domain, you must revisit unit conversion, addition, subtraction, and comparison rules together.

Allowing negative intervals in the examples is intentional: an element created with a deadline in the past is immediately eligible for retrieval. "Deadline already passed" is not a data-type error. An application may choose to reject it under its own business rules, but should not confuse those rules with the `Delayed` contract.

### 3.3. Do Not Mutate the Deadline While the Element Is in the Queue

You could declare `deadline` as `volatile` and mutate it from another thread. That only addresses visibility of the value; it does not tell the queue to rebuild its ordering or update its wait schedule.

An implementation observation on [OpenJDK 17u source](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/concurrent/DelayQueue.java): `DelayQueue` uses an internal `PriorityQueue` along with a lock and a wait condition. Identifying the head candidate relies on that priority structure. Directly mutating a sort key of an object already inside the structure is not a queue update operation.

Therefore, the safe and easy-to-explain design in this article is: **one insertion corresponds to one element with an immutable deadline**. If you need to reschedule, create a new element with a new deadline, paired with cancellation or versioning rules suited to your problem. The case where the old element has already been taken by a consumer is a separate race condition that mutating a field cannot solve.

## 4. Reading the API Through Two Questions: What Is Stored, and What Can Be Taken Now?

The table below uses "expired" (due) according to the nanosecond condition explained earlier. It is a map for reading the experiments, not a promise that multiple consecutive operations form a single transaction.

| Group | Operations | Key takeaway |
| --- | --- | --- |
| Insertion | `offer(e)`, `put(e)`, `offer(e, timeout, unit)` | Unbounded capacity; does not wait for space. The timeout parameter on `offer` does not create a delay for the element. |
| Inspection | `peek()`, `element()` | Views the head candidate, even if not yet expired. `peek()` returns `null` when empty; `element()` throws when empty. |
| Immediate retrieval | `poll()`, no-arg `remove()` | Retrieves only an expired element. When none is expired, `poll()` returns `null`; `remove()` throws `NoSuchElementException`. |
| Waiting retrieval | `take()`, `poll(timeout, unit)` | Waits for an expired element; the timed variant can return `null`. Interruptible via `InterruptedException`. |
| Storage checks | `size()`, `isEmpty()` | Includes non-expired elements. |
| Targeted removal | `remove(Object)`, `clear()` | Can remove non-expired elements; `clear()` removes all stored elements. |
| Transferring ready items | `drainTo(...)` | Transfers expired elements, optionally capped by the `maxElements` overload. |

The authoritative reference for each method is the [DelayQueue API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/DelayQueue.html). For `element()` and no-arg `remove()`, also see the methods inherited from [AbstractQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractQueue.html): they delegate to `peek()` and `poll()`, respectively. That difference in their underlying operations explains why `element()` sees a future element while `remove()` still reports no element available to take.

Three notes before running:

- `offer(e, 10, SECONDS)` does not mean "make `e` wait 10 seconds." The deadline still comes from `e` itself. That parameter is the insertion wait timeout in the `BlockingQueue` interface, and `DelayQueue` does not need it for capacity.
- Not waiting for capacity does not mean the structure is lock-free or that every call completes instantaneously regardless of thread contention.
- `null` is not permitted. A `null` return from `poll()` means no eligible element is available, not a data item you inserted.


## 5. First Experiment: Decoupling the Clock from Machine Speed

This program uses a numeric clock we control to observe **non-waiting** operations. The numbers 10, 20, and 30 are deadlines in nanoseconds on the test timeline. When changing the clock from 0 to 20, we do not sleep for 20 nanoseconds; we explicitly set "now" for the elements to 20.

As a result, the output does not depend on how long the machine takes to print a line or execute a statement. We verify the relationship between deadlines and operations instead of trying to measure tiny intervals with `Thread.sleep()`.

Save all of the following code to `DelayQueueSemanticsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.concurrent.DelayQueue;
import java.util.concurrent.Delayed;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public class DelayQueueSemanticsDemo {
    public static void main(String[] args) {
        AtomicLong clock = new AtomicLong(0);
        ManualItem early = new ManualItem("early", 10, clock);
        ManualItem middle = new ManualItem("middle", 20, clock);
        ManualItem late = new ManualItem("late", 30, clock);
        DelayQueue<ManualItem> queue = new DelayQueue<>();
        queue.offer(late);
        queue.offer(early);
        queue.offer(middle);

        require(queue.size() == 3 && queue.peek() == early, "initial ordering");
        System.out.println("stored = " + queue.size());
        System.out.println("peek before expiry = " + queue.peek());
        System.out.println("poll before expiry = " + queue.poll());

        clock.set(20);
        System.out.println("poll at time 20 = " + queue.poll());
        List<ManualItem> drained = new ArrayList<>();
        int transferred = queue.drainTo(drained);
        require(transferred == 1 && drained.get(0) == middle, "expired drain");
        System.out.println("drained = " + drained);
        System.out.println("future-only empty = " + queue.isEmpty());
        System.out.println("element with future only = " + queue.element());
        try {
            queue.remove();
            throw new AssertionError("no expired head should be removable");
        } catch (NoSuchElementException ex) {
            System.out.println("remove without argument -> "
                    + ex.getClass().getSimpleName());
        }
        System.out.println("remove future by object = " + queue.remove(late));
        System.out.println("stored after removal = " + queue.size());

        AtomicLong tinyClock = new AtomicLong(0);
        ManualItem tiny = new ManualItem("tiny", 1, tinyClock);
        DelayQueue<ManualItem> tinyQueue = new DelayQueue<>();
        tinyQueue.offer(tiny);
        System.out.println("tiny delay in milliseconds = "
                + tiny.getDelay(TimeUnit.MILLISECONDS));
        System.out.println("tiny delay in nanoseconds = "
                + tiny.getDelay(TimeUnit.NANOSECONDS));
        System.out.println("tiny poll = " + tinyQueue.poll());
    }

    private static final class ManualItem implements Delayed {
        private final String name;
        private final long deadline;
        private final AtomicLong clock;

        private ManualItem(String name, long deadline, AtomicLong clock) {
            this.name = Objects.requireNonNull(name);
            this.deadline = deadline;
            this.clock = Objects.requireNonNull(clock);
        }

        @Override
        public long getDelay(TimeUnit unit) {
            long remaining = Math.subtractExact(deadline, clock.get());
            return unit.convert(remaining, TimeUnit.NANOSECONDS);
        }

        @Override
        public int compareTo(Delayed other) {
            if (!(other instanceof ManualItem item) || item.clock != clock) {
                throw new ClassCastException("same item type and clock required");
            }
            return Long.compare(deadline, item.deadline);
        }

        @Override
        public String toString() {
            return name;
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all DelayQueueSemanticsDemo.java
java DelayQueueSemanticsDemo
```

Output:

```text
stored = 3
peek before expiry = early
poll before expiry = null
poll at time 20 = early
drained = [middle]
future-only empty = false
element with future only = late
remove without argument -> NoSuchElementException
remove future by object = true
stored after removal = 0
tiny delay in milliseconds = 0
tiny delay in nanoseconds = 1
tiny poll = null
```

### Explaining Each State Transition

At the beginning of the program, the insertion order is `late`, `early`, `middle`, yet `peek()` sees `early`. This verifies deadline ordering. `stored = 3` and `poll before expiry = null` appear together because the number of stored items is not the number of expired items.

When `clock.set(20)` runs, `early` has a remaining time of -10. `poll()` retrieves it first. `middle` has a remaining time of 0, so it is eligible for the subsequent `drainTo()`. `late` still has 10 remaining, so it is not transferred into `drained`.

In the state where only `late` remains, we observe three aspects of the same element:

- It is still stored data, so `isEmpty()` is `false`.
- It is the head candidate, so `element()` returns it.
- It has not expired yet, so no-arg `remove()` throws `NoSuchElementException`.

Then `remove(late)` deletes it. This is an object-matching removal operation, not an operation to retrieve the next expired task. Because the example class does not override `equals()`, passing back the exact `late` reference makes the removal semantics unambiguous.

The `tiny` experiment verifies measurement units. The same remaining interval of 1 nanosecond converts to 0 when expressed in milliseconds. The queue still does not hand it out via `poll()`. If you only check milliseconds and conclude the element is ready, you will conclude too early compared to the queue's condition.

### Limits of a Controlled Clock

Do not extend this experiment by calling `take()` and then only calling `clock.set(...)` on another thread while expecting the queue to wake up immediately. The controlled clock lives inside the elements; it does not drive `DelayQueue`'s internal wait timer. Changing an `AtomicLong` does not send a signal to the queue's internal wait condition.

Therefore, this program only uses `peek()`, `poll()`, `drainTo()`, inspection, and removal operations. It verifies expiration semantics without pretending to be a virtual-time scheduler. To test the waiting methods, we switch to a real clock in the next program.

`Math.subtractExact` in `ManualItem` is also a verification choice: the test values are small, so they do not overflow. If you replace them with extremes of `long`, an exception indicates the test data exceeded the design; it does not prove the queue supports every arbitrary pair of deadlines.

## 6. Second Experiment: Waiting, an Earlier Candidate Arriving, and Thread Interruption

The next problem is a consumer that must wait when no item is due yet. We place an element due in 12 hours into the queue, prepare a `take()`, and then insert an already-expired element. The consumer must receive the new element rather than waiting 12 hours just because the other element was added first.

This is also where we need to distinguish:

- **Wait time derived from the deadline:** which element gets delivered.
- **Call wait timeout:** how long the caller is willing to wait in `poll(timeout, unit)`.
- **Interrupt signal:** a request to stop a thread performing a potentially blocking operation.

Save as `DelayQueueWaitingDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.DelayQueue;
import java.util.concurrent.Delayed;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class DelayQueueWaitingDemo {
    public static void main(String[] args) throws Exception {
        DelayQueue<TimedItem> queue = new DelayQueue<>();
        queue.put(new TimedItem("later", 12, TimeUnit.HOURS));
        CountDownLatch enteringTake = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<TimedItem> consumer = pool.submit(() -> {
                enteringTake.countDown();
                return queue.take();
            });
            await(enteringTake);
            queue.offer(new TimedItem("ready", -1, TimeUnit.SECONDS));
            TimedItem received = consumer.get(5, TimeUnit.SECONDS);
            require("ready".equals(received.name), "wrong head");
            require(received.getDelay(TimeUnit.NANOSECONDS) <= 0, "not expired");
            System.out.println("taken = " + received.name);
            System.out.println("next candidate = " + queue.peek().name);

            TimedItem timed = queue.poll(1, TimeUnit.MILLISECONDS);
            require(timed == null && queue.size() == 1, "timed poll");
            System.out.println("timed poll without expired item = " + timed);
            showInterruption(queue);
            queue.clear();
            System.out.println("empty after clear = " + queue.isEmpty());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void showInterruption(DelayQueue<TimedItem> queue)
            throws Exception {
        CountDownLatch entering = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        Thread receiver = new Thread(() -> {
            entering.countDown();
            try {
                queue.take();
            } catch (InterruptedException ex) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
            } finally {
                finished.countDown();
            }
        });
        try {
            receiver.start();
            await(entering);
            receiver.interrupt();
            await(finished);
            require(interrupted.get(), "take must observe interruption");
            System.out.println("interrupted take observed = " + interrupted.get());
        } finally {
            receiver.interrupt();
            receiver.join(5_000);
            if (receiver.isAlive()) {
                throw new IllegalStateException("receiver did not terminate");
            }
        }
    }

    private static final class TimedItem implements Delayed {
        private static final long ORIGIN = System.nanoTime();
        private static final long MAX_DELAY = TimeUnit.DAYS.toNanos(1);
        private final String name;
        private final long deadline;

        private TimedItem(String name, long delay, TimeUnit unit) {
            this.name = Objects.requireNonNull(name);
            long nanos = Objects.requireNonNull(unit).toNanos(delay);
            if (nanos < -MAX_DELAY || nanos > MAX_DELAY) {
                throw new IllegalArgumentException("delay outside demo range");
            }
            deadline = Math.addExact(elapsed(), nanos);
        }

        private static long elapsed() {
            return System.nanoTime() - ORIGIN;
        }

        @Override
        public long getDelay(TimeUnit unit) {
            return unit.convert(deadline - elapsed(), TimeUnit.NANOSECONDS);
        }

        @Override
        public int compareTo(Delayed other) {
            if (!(other instanceof TimedItem item)) {
                throw new ClassCastException("TimedItem required");
            }
            return Long.compare(deadline, item.deadline);
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("latch timed out");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all DelayQueueWaitingDemo.java
java DelayQueueWaitingDemo
```

Output:

```text
taken = ready
next candidate = later
timed poll without expired item = null
interrupted take observed = true
empty after clear = true
```

### Why Does the Result Not Wait 12 Hours?

`later` has a deadline in the future. `ready` is created with a -1 second delay, so it is already due when inserted. The comparison places `ready` before `later`; `take()` returns `ready`. Afterward, `peek()` still sees `later`, confirming the future element was not lost.

From the OpenJDK 17u implementation noted earlier: when `offer()` places a new candidate at the head, the wait condition is signaled so the consumer re-evaluates the head candidate. This is an implementation-level explanation for the observed behavior; the application-level contract remains deadline ordering and expiration eligibility.

`enteringTake` is counted down right before `take()`. This latch coordinates startup, and **does not prove** the consumer thread was already asleep inside `take()` before `ready` was added. The element may have been added just before the consumer entered the call. Both interleavings must produce the same valid result shown above.

That is why the program does not claim to measure wakeup latency or force a single interleaving. A sound test does not turn an "about to call" signal into proof of "currently blocked."

### A Timeout Does Not Change an Element's Deadline

After the first retrieval, only `later` remains in the queue. `poll(1, MILLISECONDS)` does not make it expire sooner. When no item becomes due within that wait interval, the result is `null` even though the queue still stores one element.

The program does not verify an exact 1-millisecond duration against an external clock. Timer resolution, CPU scheduling, and JVM pauses can cause the call to resume later. What needs verification is that the future item is not mistakenly returned and the call does not wait indefinitely.

The 5-second bounds used for `Future.get()`, latches, and thread termination are thresholds to detect lack of progress in a normal environment. They are not real-time guarantees from Java. If the machine is paused long enough by a debugger or the OS, the check can fail due to those bounds.

### Interruption Is Part of the Shutdown Protocol

`showInterruption()` spawns a dedicated consumer thread, interrupts it, and verifies that `InterruptedException` is observed. The interrupt may arrive before `take()` actually blocks or while it is waiting; the program does not rely on distinguishing those two cases.

In the catch block, the thread restores the interrupt flag via `Thread.currentThread().interrupt()` and then exits. Restoring the flag preserves the signal for enclosing callers in designs with outer call layers. In this example the thread exits immediately, so the main purpose is to demonstrate not swallowing the interrupt request.

The `finally` block interrupts again and performs a bounded `join` to avoid leaving a stray thread running if an earlier check fails. The executor pool is also shut down and awaited. Calling `clear()` at the end only cleans up the `later` element; it does not replace thread-management steps.

If you write a real consumer loop, you must choose one policy when interrupted: propagate the exception, exit the loop, or handle it according to a defined shutdown protocol. Catching the exception and unconditionally looping back to `take()` can prevent the system from stopping when management requests shutdown.

### Why Are All Deadline Fields Final?

Even when `ready` and `later` are observed from different threads, the code has no branch that mutates their deadlines. After construction, each object retains its identity and deadline; remaining time changes because the clock keeps advancing.

The queue handles producer/consumer coordination; it does not make arbitrary mutable data inside elements safe for concurrent modification. If you need mutable state, you must separately design synchronization and lifecycle rules for that state. For these examples, keeping essential data immutable is clean and easy to verify.


## 7. Putting Together a Bounded Retry Flow

A failed attempt should usually not be retried immediately in a tight hot loop. We want to wait briefly while keeping the attempt count and termination condition explicit.

The example below simulates a job: attempts 1 and 2 require a retry, and attempt 3 succeeds. It makes no network calls and uses no random failures, so the outcome is deterministic. Each reschedule creates a new `RetryItem` with a new deadline; it never mutates an element already inside the queue.

Save as `DelayQueueRetryDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.DelayQueue;
import java.util.concurrent.Delayed;
import java.util.concurrent.TimeUnit;

public class DelayQueueRetryDemo {
    public static void main(String[] args) throws Exception {
        DelayQueue<RetryItem> queue = new DelayQueue<>();
        queue.offer(new RetryItem("job-7", 1, 0, TimeUnit.NANOSECONDS));

        boolean completed = false;
        while (!completed) {
            RetryItem item = queue.poll(5, TimeUnit.SECONDS);
            require(item != null, "retry did not become available");
            require(item.getDelay(TimeUnit.NANOSECONDS) <= 0, "not expired");
            if (item.attempt < 3) {
                System.out.println("attempt " + item.attempt + " -> retry");
                queue.offer(new RetryItem(item.id, item.attempt + 1,
                        5, TimeUnit.MILLISECONDS));
            } else {
                System.out.println("attempt " + item.attempt + " -> success");
                completed = true;
            }
        }
        System.out.println("queue empty = " + queue.isEmpty());
    }

    private static final class RetryItem implements Delayed {
        private static final long ORIGIN = System.nanoTime();
        private static final long MAX_DELAY = TimeUnit.DAYS.toNanos(1);
        private final String id;
        private final int attempt;
        private final long deadline;

        private RetryItem(String id, int attempt, long delay, TimeUnit unit) {
            this.id = Objects.requireNonNull(id);
            if (attempt < 1) {
                throw new IllegalArgumentException("positive attempt required");
            }
            this.attempt = attempt;
            long nanos = Objects.requireNonNull(unit).toNanos(delay);
            if (nanos < -MAX_DELAY || nanos > MAX_DELAY) {
                throw new IllegalArgumentException("delay outside demo range");
            }
            deadline = Math.addExact(elapsed(), nanos);
        }

        private static long elapsed() {
            return System.nanoTime() - ORIGIN;
        }

        @Override
        public long getDelay(TimeUnit unit) {
            return unit.convert(deadline - elapsed(), TimeUnit.NANOSECONDS);
        }

        @Override
        public int compareTo(Delayed other) {
            if (!(other instanceof RetryItem item)) {
                throw new ClassCastException("RetryItem required");
            }
            return Long.compare(deadline, item.deadline);
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all DelayQueueRetryDemo.java
java DelayQueueRetryDemo
```

Output:

```text
attempt 1 -> retry
attempt 2 -> retry
attempt 3 -> success
queue empty = true
```

### Tracing the Path of a Request

The first insertion has a delay of 0. It is already due when the consumer checks, so the first retrieval does not need to wait for a future deadline.

After receiving attempt 1, the loop in `main` itself decides that a retry is needed. It creates attempt 2 with a 5-millisecond delay and calls `offer()`. When the loop polls next, the element is delivered only once it is due. If the machine already spent more than 5 milliseconds between insertion and the retrieval call, returning immediately is also correct: the delay has elapsed.

After attempt 2, the same flow creates attempt 3. Attempt 3 succeeds, `completed` becomes `true`, and the loop ends. No element remains to be scheduled, so `queue empty = true`.

The decision point does not reside in any hidden mechanism of `DelayQueue`. Application code explicitly:

1. Retrieves an expired element.
2. Performs or simulates an attempt.
3. Decides whether to finish or reschedule.
4. If rescheduling, creates a new immutable element.

The 5-millisecond interval is the delay until **eligibility for retrieval**, not a guarantee that the processing statement will begin at exactly 5 milliseconds. When there are many requests or the consumer is busy, an already-due item can still sit in the queue.

The example caps at three attempts to show a complete lifecycle. When applying this to real work, you must clearly define the maximum attempt count, which errors are retryable, shutdown handling, and how to avoid duplicate execution. A delay queue does not automatically turn an external operation into "exactly-once execution."

In the program, `poll(5, SECONDS)` is merely a wait bound to detect anomalies in the demo. It is not a 5-second retry policy; the interval passed to `RetryItem` is what sets the deadline. Distinguishing these two parameters avoids a very common design bug: confusing how long the consumer is willing to wait with how long the job should be delayed.

## 8. Bugs to Recognize from Symptoms

### 8.1. The Queue Has Many Elements, Yet the Consumer Still Waits

First ask: are those elements due yet? Inspect with `peek()` and read `getDelay(NANOSECONDS)` to understand the head candidate at the time of observation. This is diagnostic information, not a reservation: another thread can retrieve or insert elements immediately afterward.

If the head candidate still has positive remaining time, `take()` waiting is normal. If an element you believe is due is stuck behind a future candidate, check `compareTo()` and whether any sort key was mutated after insertion.

Do not "fix" this with a loop:

```java
// Anti-pattern: snippet only, not standalone.
while (!queue.isEmpty()) {
    Object item = queue.poll();
    // item can still be null; the loop can spin continuously.
}
```

Such a non-waiting loop can burn CPU while all items are still in the future. If your model requires waiting for the next item, use a blocking operation with a shutdown policy; if you only need an immediate check, handle `null` and return control to the caller.

### 8.2. Elements Are Never Retrieved

Check whether `getDelay()` is always returning the initial delay. Also check the returned unit, the subtraction order, and whether two element types share the same time origin.

If you write `now - deadline` instead of `deadline - now`, a future item can have a negative value and be retrieved early. If it always returns a positive number, the item never becomes due according to its own report. If you sort by name while timing by deadline, the head candidate no longer represents the earliest item.

These bugs belong to the element's contract. Adding `synchronized` around `poll()` cannot fix a broken time representation.

### 8.3. Attempting to Reschedule by Mutating a Single Field

Mutating a deadline directly can leave the internal ordering and wait time out of sync with the new value. Making the field `volatile` does not turn that mutation into "remove and re-insert" either.

For a task that can be rescheduled from multiple threads, merely calling `remove(oldItem)` and inserting a new version is not enough to guarantee no old run happens: a consumer may have already taken `oldItem`. You must resolve that race at the application level, such as checking a job version before execution or maintaining properly synchronized cancellation state. This article only asks you to recognize the boundary; it does not assume a single cancellation protocol fits every application.

`remove(Object)` uses object equality rules. In the three example classes, two objects with the same name or job ID are still distinct objects because `equals()` is not overridden. When designing `equals()` yourself, consider whether multiple attempts of the same job must be distinguished. Do not assume that sharing a job ID identifies the exact scheduled item to remove.

### 8.4. Inserting Heavy Load and Expecting the Queue to Backpressure

`DelayQueue` has no configurable capacity to apply backpressure to producers. `remainingCapacity()` returning `Integer.MAX_VALUE` does not mean the JVM has infinite memory or can actually hold that many objects.

An expired item does not vanish merely because time passes. An operation must retrieve or remove it. If producers keep inserting while consumers are stopped or slow, data can accumulate in memory.

Therefore, separate two problems:

- Expiration rules answer **when an item may be taken**.
- Concurrency/admission control answers **whether more work may be accepted**.

If the system needs to bound pending items, add an appropriate admission policy and release permits at the right point in the lifecycle. You cannot achieve that simply by choosing the timed `offer` overload.

### 8.5. Calling clear and Expecting All Threads to Exit

`clear()` removes stored data. It does not close the queue or stipulate that waiting `take()` calls must terminate with a "closed" signal. A consumer can still keep waiting for a new due item.

Shutdown management is a separate protocol: the application can retain thread references to interrupt them, use an executor and cancel pending tasks, or design an appropriate termination signal. You must wait for termination if resource lifecycles require it.

Do not mechanically copy a poison-pill element from a FIFO queue:

- If the poison pill has a distant deadline, the consumer may still have to wait.
- If it is due immediately, the consumer may stop before future tasks you still wanted to process.
- If there are multiple consumers, you must decide how many consumers the termination signal is meant for.

The right question is "on shutdown, should pending items be completed, canceled, or persisted?" and only then choose how to signal shutdown.

### 8.6. Iterating to Infer Upcoming Retrieval Order

`DelayQueue`'s iterator is weakly consistent and does not guarantee deadline order. It can also observe future elements. The array returned by `toArray()` is likewise not sorted by retrieval time.

If you only need diagnostic display, you can copy and sort the snapshot by known deadline data, while understanding that other threads continue mutating the queue. That copy is not an atomic snapshot of all system state and does not reserve the next retrieval.

If you need to process elements according to the queue's rules, use the queue's own retrieval operations. Do not use a `for-each` loop as a scheduler.

### 8.7. Treating drainTo as "Delete All" or an Infallible Transfer

The first program already showed `late` remaining after `drainTo()`. This is an operation to transfer eligible items, not a way to copy or remove every stored element. Clearing all data is a different requirement.

Choose a destination collection that can accept elements normally. Per the `drainTo` contract, if adding to the destination throws an exception, do not assume a transaction rolled back completely. Avoid draining into the source queue itself. When you need atomicity across two structures or external non-memory side effects, design a dedicated protocol; a bulk transfer call does not provide all those guarantees.

## 9. Choosing the Right Tool for the Question at Hand

`DelayQueue` fits when the application wants to own the element type, deadline condition, and receive/process loop. For example, the retry program above wanted explicit control over each retrieval and element recreation.

If the primary requirement is "run a piece of code after a delay" or "run periodically," look at [ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html). That interface provides execution scheduling operations and returns an object to track or cancel the task. `DelayQueue` only provides storage and deadline-based retrieval; if you use it, you own the execution part yourself.

If you only need to pass data between threads without per-item time conditions, start from the ordering and capacity requirements of an appropriate `BlockingQueue`. Do not add `Delayed` when deadlines have no domain meaning.

If the goal is expiring data that needs cleanup, choosing `DelayQueue` does not by itself create an automatic cleanup system: you still need a consumer and resource-deletion logic. If recovery after process restart is required, you also need persistent storage and a schedule-reconstruction rule. An in-memory queue does not replace those requirements.

None of these options automatically guarantee execution starts at an exact wall-clock instant. Reaching the deadline makes the item eligible; CPU availability, worker threads, system latency, and prior work still affect when execution actually happens.

## 10. Self-Check and Practice with Solutions

### Question 1. The Queue Has Only One Item with 30 Seconds Left. Predict the Results

Assume no other thread adds or removes items and the deadline does not arrive during inspection. What do `size()`, `peek()`, `poll()`, and no-arg `remove()` return?

**Solution:** `size()` is 1; `peek()` returns that item; `poll()` returns `null`; `remove()` throws `NoSuchElementException`. Distinguish existence from eligibility for retrieval. By contrast, `remove(thatItem)` can delete the item when the object matches.

**Practice:** using the first program's controlled clock, create an item with deadline 30 instead of sleeping 30 seconds. Verify the state before, at, and after the deadline. Use only non-waiting operations in this experiment.

### Question 2. Does Modifying compareTo to Prioritize Smaller Job IDs Make Sense?

Suppose item ID 1 has one hour left, and item ID 2 is already due. You want ID 1 to have "higher business priority."

**Solution:** you cannot replace expiration order with ID order while keeping the required contract. When a non-expired item stands in front, an expired item can be shadowed. If business priority exists, you must first define how it interacts with the time condition. A secondary tie-breaker for equal deadlines is different from ignoring deadlines altogether.

**Practice:** on a separate copy using the controlled clock, intentionally invert the deadline comparison and observe `peek()`/`poll()`. Explain the behavior using the head candidate, then restore the correct comparison. Do not use the intentionally broken version for real work.

### Question 3. Why Does Milliseconds Show 0 While poll Still Returns null?

**Solution:** unit conversion can truncate fractional parts. A 1-nanosecond interval is still positive in nanoseconds but 0 in milliseconds. The queue's eligibility check relies on nanoseconds.

**Practice:** in the first program, advance `tinyClock` from 0 to 1, then call `poll()` again. Now the `tiny` element must be returned. Do not add a real sleep to the unit verification.

### Question 4. You Just Called remove(oldItem), Yet an Old Execution Still Happens. Is That Possible?

**Solution:** yes. A consumer may have already retrieved the element before the removal; or the object you passed did not match the target item under equality rules. The queue cannot rewind an already-delivered element. If cancellation must affect an already-taken task, you need a job-level cancellation state/protocol and a clear check point.

**Practice:** describe two interleavings: removal before retrieval, and retrieval before removal. Write down the expected result of `remove` in each interleaving, then state what you still do not know about whether the external work has already executed.

### Question 5. Is Changing a 5-Millisecond Retry to 5 Seconds Just a Matter of Changing poll?

**Solution:** no. To schedule the next attempt 5 seconds later, you must change the delay passed to the new `RetryItem`. `poll(timeout, unit)` only bounds how long the consumer waits. If the wait timeout is shorter than the item's deadline, a `null` result is a valid possibility to handle, not proof that the item was lost.

**Practice:** pick a delay longer than the wait timeout, then design an explicit `null`-handling branch. Define when to keep waiting and when the overall job is canceled. Do not simply delete the `require` check and let the loop spin forever.

### Question 6. To Stop a Consumer Thread When No Item Is Due, Is clear Enough?

**Solution:** no. `clear()` empties data but does not close the queue. The consumer thread needs a shutdown protocol, such as being interrupted and exiting upon `InterruptedException`, after which the manager waits for it to terminate.

**Practice:** re-read `showInterruption()` and point out three distinct actions: sending the interrupt request, the consumer observing the request, and the manager waiting for the thread to exit. Explain why the latch placed before `take()` does not confirm a blocked waiting state.

## 11. Verification and Reference Documentation

The three programs in this article were compiled with `javac --release 17 -encoding UTF-8 -Xlint:all` and run on OpenJDK 24.0.2; their outputs match the `text` blocks shown. `--release 17` checks Java 17 syntax and API compatibility at compile time; it does not mean the runs themselves occurred on a Java 17 JVM.

When running them yourself, keep the exact filenames, use JDK 17 or later, and run each program standalone. The first program does not measure real time; the latter two use relative delays and wait bounds to avoid leaving infinite consumer loops in the demos. None of the results require nanosecond-exact execution timing.

Primary sources for verifying the contract:

- [Delayed — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Delayed.html): remaining time and consistent comparison ordering.
- [DelayQueue — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/DelayQueue.html): retrieval, inspection, removal, transfer, and iteration rules.
- [AbstractQueue — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractQueue.html): inherited behavior of `remove()` and `element()`.
- [TimeUnit — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): unit conversion, truncation, and representation bounds.
- [System.nanoTime() — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed-time measurement and bounds of time differences.
- [ScheduledExecutorService — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): execution scheduling when task lifecycle management is needed.
- [DelayQueue source in OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/concurrent/DelayQueue.java): implementation observations on the priority structure and signaling when the head candidate changes; does not replace the API contract.
