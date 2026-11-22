# Choosing a Shared Lock When Coordinating Multiple Operations on StringBuffer

## Objective

StringBuffer is a mutable string buffer; many methods such as append(), insert(), and delete() are synchronized to protect individual calls on the same object. However, **thread-safety at the method level does not mean a sequence of methods is atomic**. When multiple threads check a condition before modifying content, or must append multiple text fragments as one contiguous record, we need a **shared lock** covering the entire logical operation.

After this lesson, learners should know when additional synchronization is needed, which monitor to choose, why all threads must use the exact same lock object, and how to verify invariants after concurrent execution.

## 1. Why Is Per-Method Synchronization Not Enough?

Consider a requirement: the log has only one HEADER line at the beginning, then each thread appends its name. The following snippet is **not safe for the compound operation**, even though StringBuffer has synchronized methods:

```java
// Illustrates a processing snippet, not a standalone runnable program.
if (log.length() == 0) {
    log.append("HEADER\n");
}
log.append(Thread.currentThread().getName()).append('\n');
```

A valid interleaving sequence:

1. T1 calls length() and sees 0; the call ends and the monitor is released.
2. T2 calls length() and also sees 0.
3. T1 executes append("HEADER\n").
4. T2 executes append("HEADER\n").
5. Both threads append their records: the log has two HEADERs, violating the requirement.

This is a **check-then-act** bug: the checked value is no longer reliable when the action runs in another call. Similarly, three calls append("["); append(data); append("]") can have another thread interleave in between; each append() still protects StringBuffer's internal state, yet does not guarantee the three fragments form an atomic record.

**Rule:** If a later step's decision depends on a previous step's result, or multiple steps must appear as a single unit, protect the entire sequence of steps with one critical section.

## 2. A Shared Lock Means the Same Object, Not Just the Same Name

In Java, synchronized(lock) acquires the monitor associated with lock's **object identity**. Two threads only block each other when acquiring the monitor of the exact same instance. For an already shared StringBuffer, choosing the buffer itself as the lock is often simplest:

```java
// Threads must share the exact same buffer reference.
synchronized (buffer) {
    if (buffer.length() == 0) {
        buffer.append("HEADER\n");
    }
    buffer.append("event: ").append("done").append('\n');
}
```

StringBuffer's synchronized methods also use the buffer's own monitor. Because Java locks are **reentrant**, a thread already inside synchronized(buffer) can call synchronized methods on that buffer. Another thread acquiring the same monitor must wait for the entire block to finish.

The atomic scope here covers checking emptiness, deciding to write the header, and writing the record. If you lock only length(), and release the lock before append(), the bug remains. One thread using synchronized(otherLock) while another uses synchronized(buffer) cannot coordinate either; two monitors are not automatically linked to each other.

You must agree upon and enforce **the same locking convention on every access path related to the invariant**. An append() outside the critical section is still safe at the call level, yet can interleave between steps of the compound operation and break the business rule.

## 3. Complete Program on Java 17+

The program below starts two threads close together, each wanting to ensure a HEADER exists and then record its own name. CountDownLatch only coordinates start timing; **synchronized(log) is what protects the condition and update**.

```java
import java.util.concurrent.CountDownLatch;

public class SharedLockDemo {
    public static void main(String[] args) throws InterruptedException {
        StringBuffer log = new StringBuffer();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Runnable task = () -> {
            ready.countDown();
            try {
                start.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            synchronized (log) {
                if (log.length() == 0) {
                    log.append("HEADER\n");
                }
                log.append(Thread.currentThread().getName()).append('\n');
            }
        };

        Thread first = new Thread(task, "T1");
        Thread second = new Thread(task, "T2");
        first.start();
        second.start();

        ready.await();
        start.countDown();
        first.join();
        second.join();

        String snapshot;
        synchronized (log) {
            snapshot = log.toString();
        }

        long headers = snapshot.lines()
                .filter("HEADER"::equals)
                .count();
        long records = snapshot.lines()
                .filter(s -> s.equals("T1") || s.equals("T2"))
                .count();

        System.out.println("headers=" + headers);
        System.out.println("records=" + records);
        System.out.println("headerFirst=" + snapshot.startsWith("HEADER\n"));
    }
}
```

Save as SharedLockDemo.java and run:

```bash
javac SharedLockDemo.java
java SharedLockDemo
```

Consistent output:

```text
headers=1
records=2
headerFirst=true
```

The order of T1/T2 in the string can vary by CPU scheduling, so the program does not print or assert that order. Only the first thread entering synchronized(log) sees an empty log; the later thread sees HEADER already present. join() makes main wait for both to finish. Capturing the snapshot under the same monitor is a consistent read pattern, especially useful if the application later still has active writer threads.

If you remove synchronized(log) wrapping the condition and appends, the program has the **potential** to write duplicate HEADERs, though not every run exposes the race. Correct results over a few runs do not prove code is free of concurrency bugs.

## 4. A Private Lock Object for a Data-Managing Class

When StringBuffer is managed inside a class, or an invariant spans both string content and other data, using a private lock field often makes ownership clearer:

```java
// Illustrative class used inside a Java project; no standalone main().
final class Transcript {
    private final Object lock = new Object();
    private final StringBuffer buffer = new StringBuffer();
    private int recordCount;

    public void record(String text) {
        synchronized (lock) {
            if (buffer.length() == 0) {
                buffer.append("HEADER\n");
            }
            buffer.append(text).append('\n');
            recordCount++;
        }
    }

    public String snapshotWithCount() {
        synchronized (lock) {
            return "count=" + recordCount + "\n" + buffer.toString();
        }
    }
}
```

Both buffer and recordCount fall under the same update rule. Choosing private final Object lock keeps the lock identity constant and prevents external code from arbitrarily holding this monitor. Do not return the buffer reference for callers to modify without acquiring lock.

Understand the difference: synchronized(lock) uses lock's monitor, whereas synchronized methods on StringBuffer use buffer's monitor. StringBuffer's methods **do not automatically synchronize on the private lock**. The design above protects compound operations because **every read/write path owned by the class** consistently acquires lock. If external code held a reference to buffer and called append() directly, it could interleave while a thread held lock; the class-level invariant would no longer be guaranteed.

When all data is accessed exclusively through a private lock, you can consider StringBuilder instead of StringBuffer to avoid redundant method-level synchronization. The mandatory condition is that zero StringBuilder accesses exist outside the lock convention, and choosing StringBuilder does not change the lesson's requirements regarding StringBuffer.

## 5. How to Identify the Right Critical Section

Before using synchronized, clearly identify:

1. **Invariant:** what must always hold true? For example, HEADER appears exactly once; each record's prefix, body, and suffix stay contiguous; recordCount equals the number of appended records.
2. **Steps forming one unit:** check state → decide → update one or more fields → complete the record.
3. **Threads and access paths:** which methods can observe or modify that state, and do they use the exact same lock?

Reads may also need the shared lock. A single buffer.toString() captures the string at one point in time, yet reading recordCount afterward at a different time does not guarantee the count matches the snapshot. When consistent aggregate state is required, read both content and counter under the same monitor used by writers.

One thread releasing a monitor and another thread later acquiring **the same monitor** establishes a happens-before relationship under the Java Memory Model: modifications prior to release are published for the lock-acquiring thread to see. Marking the buffer reference volatile only aids reference visibility; it **does not make length() followed by append() atomic**.

If an invariant spans **two StringBuffers**, a shared private lock can be used:

```java
// Assumes all accesses involving ready/processed acquire lock.
synchronized (lock) {
    processed.append(ready);
    ready.setLength(0);
}
```

One thread must not lock only ready and assume it has protected processed as well. If forced to acquire two nested monitors, every code path must acquire locks in a consistent order; T1 holding lock A and waiting for B while T2 holds B and waits for A can cause deadlock. One shared lock is usually easier to reason about for small multi-field invariants, though it can also create more contention.

## 6. Wrong Ways to Choose a Lock

**A new lock on every call:** synchronized(new Object()) uses different monitors across calls and threads, failing to coordinate.

```java
// Wrong for multiple threads concurrently modifying the buffer.
synchronized (new Object()) {
    if (buffer.length() == 0) {
        buffer.append("HEADER\n");
    }
}
```

**Locking on a string snapshot:** synchronized(buffer.toString()) locks a String object, not the buffer's monitor. Separate toString() calls can create different objects, so there is no shared locking convention.

**Locking `this` across different wrapper instances:** two wrapper instances have two different `this` monitors; if both modify a shared buffer, synchronized(this) on each wrapper provides no shared protection. It is only suitable when all threads actually use the exact same state-managing instance.

**Locking on string literals:** synchronized("LOG_LOCK") can accidentally share a monitor with unrelated code due to String interning, causing unwanted waiting or deadlock. A private final lock is much easier to control.

**Changing the lock object:** reassigning the buffer or lock variable mid-flight causes one thread to lock the old instance and another to lock the new instance. The identity of a coordinating lock must remain stable and consistent.

**Lock too narrow:** putting synchronized only around length(), or around each individual append(), leaves the gap between check and update unprotected. A call chain append("["); append(value); append("]") can still be interleaved.

**Lock too wide:** holding the monitor while waiting on network calls, performing slow I/O, sleeping, or running long computations that do not touch shared state increases waiting. Prepare independent data beforehand, then keep the critical section short enough while still covering all invariant-maintaining steps.

**Using two locking conventions simultaneously:** T1 using synchronized(buffer) and T2 using synchronized(lock) fails to coordinate compound operations even though individual StringBuffer methods remain safe. Every party able to affect the invariant must follow the same convention.

## 7. When Is an External Lock Truly Needed?

- **A single independent call** such as append(wholeRecord), with no invariant spanning multiple calls or other fields: StringBuffer's internal protection is usually sufficient for that call.
- **Multiple calls that must stay contiguous** such as check-then-append, assembling prefix/body/suffix across multiple append() calls, or read-modify-write based on current content: a shared lock wrapping the whole sequence is needed.
- **Multiple related fields** such as buffer with recordCount, or two buffers transferring data together: protect all related data as well as aggregate snapshot reads.
- **No sharing across threads:** no extra lock needs to be imposed to protect data owned by a single thread; StringBuilder may fit better in local scope.

Do not lock merely because you see the StringBuffer type, and do not omit locking merely because each method is already synchronized. Atomic boundaries must be decided by **the application's invariants**.

## 8. Testing and Review

In multi-threaded applications, verify stable properties: HEADER appears exactly once; record count matches request count; each record has intact opening/closing delimiters; counters match the data. Repeating tests and increasing contention help uncover bugs, yet do not replace reasoning about locks. A race might not manifest across thousands of runs.

During code review, mark all entry/exit paths of critical sections, verify all use **the exact same lock instance**, confirm the lock reference is never reassigned, and ensure no write path bypasses it. When multiple monitors are acquired nestedly, verify lock ordering to prevent deadlock. When seeing slow operations inside a locked block, check whether independent work can be moved outside while preserving the invariant.

## Key Takeaway

**StringBuffer synchronizes individual methods; a shared lock synchronizes an entire multi-method workflow.** Use synchronized(buffer) when multiple threads share a single StringBuffer and need to protect an entire compound operation. Use private final Object lock when a class manages multiple related pieces of state and controls every access path. The core condition is that threads must coordinate on **the exact same monitor**, and the lock block must encompass the check, decision, and update that must be observed as one unit.
