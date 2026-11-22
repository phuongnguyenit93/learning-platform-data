# Per-Method Synchronization Does Not Guarantee Atomicity for a Sequence of Operations with `StringBuffer`

`StringBuffer` is Java's **mutable** string-building class, whose primary methods such as `append()`, `insert()`, `delete()`, `length()`, and `toString()` are synchronized to support multi-threaded access. However, a very common design mistake is assuming: **"Because `StringBuffer` calls are synchronized, all of my consecutive statements are automatically an atomic operation as well."**

That is **not true**.

An `append("A")` call may be protected by the `StringBuffer`'s lock while the method executes; however, after that call completes, another thread can enter and modify the buffer **before your next call begins**. Therefore, operations such as **check-then-act**, **read-then-delete**, **appending multiple segments that must stay contiguous**, or **checking multiple conditions on the same state** must be synchronized as a single **logical unit**.

**Core takeaway:** *thread-safety at the method level does not automatically guarantee atomicity at the multi-method workflow level.*

## 1. Three Concepts to Distinguish

### Thread-Safety at the Call Level

A single method call is designed so that multiple threads can use it without corrupting the object's internal state. For example, two threads concurrently calling `append()` on a `StringBuffer` will not suffer the unsynchronized buffer access that occurs when concurrently modifying a `StringBuilder`.

This **does not guarantee** a global order desired by the programmer. If two threads concurrently add `"A"` and `"B"`, the order depends on scheduling; the result can be `"AB"` or `"BA"` if both additions succeed.

### Atomicity at the Logical Operation Level

An *atomic* operation is an operation observed as a single unit without interference from competing operations on the same state. If the business rule is "**only add X if the buffer is currently empty**", the two steps:

1. Read `buffer.length() == 0`.
2. Call `buffer.append("X")`.

must be executed inside **the same critical section**. Two separate steps, even if each is individually synchronized, do **not** form an atomic operation.

### Invariant — A Condition That Must Always Hold True

An *invariant* is a condition on state that the program must maintain, such as "only one header exists", "each record consists of a prefix and suffix without interleaving", or "delete the last character only if the buffer still has data".

A lock is meaningful only when it protects **enough of the operation for the invariant to remain true**. If you only lock each small call and allow another thread to modify state between steps, the invariant can be broken.

## 2. Why Is `StringBuffer` Considered Thread-Safe?

`StringBuffer` is designed with synchronization on its key methods so that operations on an instance do not conflict when accessing the internal buffer across multiple threads. Many operations use the *intrinsic monitor* lock of the `StringBuffer` object itself, equivalent in lock usage to `synchronized (buffer)` on the caller side.

Example:

```java
StringBuffer buffer = new StringBuffer();

buffer.append("A");
buffer.append("B");
```

Each `append()` call can execute safely on its own. Yet between the moment the first call ends and the second call begins, another thread can still call `append()` or modify the buffer.

There is no contract saying that two consecutive Java statements in the same thread retain the lock across both calls.

One valid interleaving schedule:

```text
Thread 1                   Thread 2
--------                   --------
append("A")  [done]
                           append("X")  [done]
append("B")  [done]

Final content: "AXB"
```

No individual `append()` call was executed "halfway"; however, **the overall result is not `"ABX"`** as the author of Thread 1 might expect.

Synchronized operations protect method entry/exit; they **do not automatically turn an entire external block of statements into a transaction**.

## 3. First Bug: *check-then-act*

Consider a seemingly simple rule: **only add the symbol `"X"` if the buffer is currently empty**.

```java
// Fragment illustrating an INCORRECT approach when multiple threads compete:
if (buffer.length() == 0) {
    buffer.append("X");
}
```

`length()` and `append()` are individually protected, but the following schedule can occur:

```text
Initially: buffer = ""

Thread A: length() == 0   → true
Thread B: length() == 0   → true
Thread A: append("X")     → buffer = "X"
Thread B: append("X")     → buffer = "XX"

Result: "XX", violating the "add only once" requirement.
```

Each thread makes its decision from a **snapshot of state that may already be stale** by the time the action runs. This is a *time-of-check to time-of-use* (TOCTOU) bug at the shared-state level.

### Fix Using a `synchronized` Block Wrapping Both Check and Modification

```java
synchronized (buffer) {
    if (buffer.length() == 0) {
        buffer.append("X");
    }
}
```

Here, the thread holds the monitor of `buffer` **throughout** the check and `append`. Another thread wanting to run `StringBuffer` methods using the same monitor must wait for the critical section to finish.

Synchronization is **reentrant**: while already holding `buffer`'s lock in `synchronized(buffer)`, the current thread can still invoke `synchronized` methods on `buffer` itself. The lock does not self-deadlock simply because the thread holds it and then calls a synchronized method on the same object.

**Guarantee condition:** every path modifying the related state must obey the same synchronization rule; if related data resides in another object or a library modifies it without participating in the lock, the protection design must be extended accordingly.

## 4. Standalone Java 17+ Example with Clearly Coordinated Multi-Threaded Output

To avoid a race-condition example that "sometimes shows up, sometimes doesn't," the program below uses `CountDownLatch` to **force both threads to check the empty state before either thread is allowed to append**. Therefore, the output of the buggy case is predictable.

Create the file `StringBufferAtomicityDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class StringBufferAtomicityDemo {
    private static String unsafeCheckThenAppend()
            throws InterruptedException {
        StringBuffer buffer = new StringBuffer();
        CountDownLatch bothChecked = new CountDownLatch(2);
        CountDownLatch proceed = new CountDownLatch(1);

        Runnable task = () -> {
            boolean wasEmpty = buffer.length() == 0;
            bothChecked.countDown();

            try {
                proceed.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            if (wasEmpty) {
                buffer.append("X");
            }
        };

        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.start();
        second.start();

        bothChecked.await(); // Both threads have seen the buffer empty.
        proceed.countDown(); // Allow both to append.
        first.join();
        second.join();

        return buffer.toString();
    }

    private static String atomicCheckThenAppend()
            throws InterruptedException {
        StringBuffer buffer = new StringBuffer();

        Runnable task = () -> {
            synchronized (buffer) {
                if (buffer.length() == 0) {
                    buffer.append("X");
                }
            }
        };

        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        return buffer.toString();
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println(
                "nonAtomic = " + unsafeCheckThenAppend());
        System.out.println(
                "atomic = " + atomicCheckThenAppend());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac StringBufferAtomicityDemo.java
java StringBufferAtomicityDemo
```

Output when there are no unintended thread interrupts:

```text
nonAtomic = XX
atomic = X
```

**Why is the result deterministic?**

- In `unsafeCheckThenAppend()`, each thread stores `wasEmpty = true` from the initial state. `bothChecked` only unblocks the main thread when **both** have finished checking; `proceed` blocks appending until that point. Hence both call `append("X")` and the result is guaranteed to be `"XX"`, regardless of which thread appends first.
- In `atomicCheckThenAppend()`, the first thread to enter `synchronized(buffer)` checks for empty and appends. The other thread can only enter after the first releases the monitor; at that point `length() != 0`, so it does not append again. The result is `"X"`.
- `Thread.join()` makes the main thread wait for both threads to finish before printing the buffer content. Calling `toString()` without waiting for the threads to finish does not guarantee it reflects the final state.

**Note:** the program uses `CountDownLatch` to demonstrate the bug in a controlled way. In real applications, the same race can happen randomly whenever scheduling happens to place two checks before both writes.

## 5. Second Bug: Multiple `append()` Calls Forming One Record Get Interleaved

Suppose we want to produce two independent records `"[A]"` and `"[B]"` in a shared buffer.

```java
// Illustrative fragment: each thread may run this snippet with a different id.
buffer.append("[");
buffer.append(id);
buffer.append("]");
```

Each individual `append()` is safe, yet the three calls are **not guaranteed to stay adjacent**. A schedule can produce:

```text
Thread A: append("[")   → "["
Thread B: append("[")   → "[["
Thread B: append("B")   → "[[B"
Thread A: append("A")   → "[[BA"
Thread A: append("]")   → "[[BA]"
Thread B: append("]")   → "[[BA]]"
```

The result `"[[BA]]"` does not contain two intact records in the intended format, even though no `append()` method executed incorrectly.

### Solution 1: Use One `append()` Call for a Completed Record

If a short record is easy to construct independently, build it separately first:

```java
String record = "[" + id + "]";
buffer.append(record);
```

Now adding *a completed result string* to the buffer happens via one `append(String)` call. Other records may appear before or after this record, but cannot interleave between parts of **a single append call** on the same `StringBuffer`.

This approach is usually clear when each record is small; it has the cost of creating a separate record `String`.

### Solution 2: Lock the Entire Multi-Part Addition Workflow

```java
synchronized (buffer) {
    buffer.append("[");
    buffer.append(id);
    buffer.append("]");
}
```

The outer block holds `buffer`'s monitor across all three calls. If threads share the buffer and all obey that monitor, record contents will not be interleaved by competing calls on the same buffer.

**Attention:** a method-call chain like `buffer.append("[").append(id).append("]")` looks like one Java statement, yet it still consists of **multiple separate `append()` calls**. One Java statement or a fluent chain does not equal one atomic operation.

## 6. Multiple Reads Can Also Fail: *read-modify-write* and Changing Indices

When a thread reads state and then decides how to modify based on the result, any value already read can become stale if the buffer changes between calls.

Example: "delete the last character if the string is not empty."

```java
// INCORRECT fragment when another thread modifies the same buffer:
if (buffer.length() > 0) {
    buffer.deleteCharAt(buffer.length() - 1);
}
```

Thread A sees a positive length. Before it computes the index or deletes, Thread B may clear the entire content. When A calls `deleteCharAt()`, the index may no longer be valid and Java can throw `StringIndexOutOfBoundsException`.

Even if no exception is thrown, A may delete **a different character** than intended because the content has changed. Having each call locked does not automatically refresh a previously read value.

Fix with a critical section:

```java
synchronized (buffer) {
    int length = buffer.length();
    if (length > 0) {
        buffer.deleteCharAt(length - 1);
    }
}
```

Now reading the length, calculating the index, and deleting all lie inside **one locked logical transaction**. The condition `length > 0` remains true throughout the protected region for all actors obeying the buffer lock.

### Reading a Consistent Snapshot

When you need **a text snapshot** at a specific moment, `buffer.toString()` returns an independent, immutable `String`. However, separate calls can still observe different points in time:

```java
int before = buffer.length();
// Another thread can append/delete here.
String snapshot = buffer.toString();
```

`before` does not necessarily equal `snapshot.length()`. If two values must reflect **the same state**, retrieve them inside the same `synchronized(buffer)` block or derive everything from the snapshot alone:

```java
String snapshot = buffer.toString();
int snapshotLength = snapshot.length();
```

In the latter example, `snapshotLength` is guaranteed to be the length of the snapshot string itself because `String` is immutable. They do not necessarily represent the buffer's state at **a later point in time**.

## 7. Using the Right Monitor: All Components Must Share the Same Locking Rule

A simple approach when exclusively managing a shared buffer:

```java
private final StringBuffer shared = new StringBuffer();

public void appendEntry(String entry) {
    synchronized (shared) {
        shared.append("<").append(entry).append(">");
    }
}
```

This is a **fragment placed inside a class**, not a standalone runnable program. `shared` is initialized once and then used as a unified monitor. Other methods performing state-dependent workflows on the same buffer must also adopt a compatible synchronization convention.

Another design option is using a **private lock**, especially when protecting additional state alongside the buffer:

```java
private final Object lock = new Object();
private final StringBuffer buffer = new StringBuffer();
private int entryCount;

public void appendEntry(String entry) {
    synchronized (lock) {
        buffer.append("<").append(entry).append(">");
        entryCount++;
    }
}
```

In this design, **every read/write path for the pair `buffer` and `entryCount` must go through `lock`** if their invariant requires atomicity. The `lock` object is a **different** lock from `buffer`'s intrinsic monitor, so do not assume direct `buffer.append()` calls elsewhere will automatically respect that private lock. Keeping both fields `private` and accessing them only through the class's methods helps enforce the locking rule.

Avoid confusion:

- `synchronized(buffer)` and `synchronized(lock)` do not protect the same critical section if `lock != buffer`.
- `synchronized(this)` may fit when a wrapper object uses `this` consistently as its lock, but it does not automatically lock another buffer's monitor.
- Declaring a reference variable `final StringBuffer buffer` only forbids reassigning the variable; it does **not** make multi-step operation sequences atomic.
- Declaring a reference field `volatile StringBuffer buffer` mainly concerns visibility of changes to the **reference**; it does not replace locking to protect a read-then-modify workflow on buffer content.

## 8. What Does "Protecting Enough Scope" Mean?

Identify the logical operation at the business level, then protect the entire portion that depends on shared state.

| Logical requirement | Calls that may need grouping under the same lock | Risk if locks are split |
| --- | --- | --- |
| Add header only once | Check `length() == 0` then `append(header)` | Two threads both see empty and add duplicates. |
| Keep a record contiguous | `append(prefix)`, `append(body)`, `append(suffix)` | Contents of two records interleave. |
| Delete last character if present | `length()`, condition check, `deleteCharAt()` | Stale index, wrong deletion, or exception. |
| Read multiple properties of the same snapshot | `length()`, `charAt()`, or take one `toString()` and inspect the snapshot | Reads may come from different moments in time. |
| Update buffer alongside a counter | `append()` and `entryCount++` | Buffer and counter become inconsistent. |
| Check absence of data then write a marker | `indexOf()` or `toString()` to check, then `append()` | Two threads decide based on the same stale state. |

**Do not hold a lock wider than necessary.** For example, network calls, slow file reads, waiting on user input, or heavy processing inside `synchronized(buffer)` can force other threads to wait needlessly long.

A good pattern is to **prepare immutable data outside the lock**, then hold the lock only long enough to check shared conditions and apply the update:

```java
String record = "[" + value + "]"; // Prepare beforehand.
synchronized (buffer) {
    // Check any additional invariants, if applicable.
    buffer.append(record);
}
```

When you only need to add a single completed record with no other conditions, a single `buffer.append(record)` already has method-level locking; an outer `synchronized` block is not necessarily required. An external lock is needed when **a workflow has multiple related steps that must execute together**.

## 9. Second Java 17+ Example: Controlled Interleaving of Multiple `append()` Calls

The following program forces Thread B to insert a complete record between Thread A's two appends. No data is corrupted at the internal buffer level, yet the overall formatting is no longer as intended.

Create the file `StringBufferInterleavingDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class StringBufferInterleavingDemo {
    public static void main(String[] args) throws InterruptedException {
        StringBuffer buffer = new StringBuffer();
        CountDownLatch firstPartDone = new CountDownLatch(1);
        CountDownLatch otherPartDone = new CountDownLatch(1);

        Thread first = new Thread(() -> {
            buffer.append("[A");
            firstPartDone.countDown();

            try {
                otherPartDone.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            buffer.append("]");
        });

        Thread second = new Thread(() -> {
            try {
                firstPartDone.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            buffer.append("[B]");
            otherPartDone.countDown();
        });

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("interleaved = " + buffer);
    }
}
```

Run:

```bash
javac StringBufferInterleavingDemo.java
java StringBufferInterleavingDemo
```

Output when uninterrupted:

```text
interleaved = [A[B]]
```

Coordinated execution schedule: Thread A adds `"[A"` first, then waits; Thread B inserts `"[B]"` in between; only then does A add `"]"`. All three `append()` calls are valid, yet the final string does not contain two intact records `"[A]"` and `"[B]"`.

To fix this in a real application, change the **workflow design**: either build the record `"[A]"` and call `append(record)` once, or use a critical section holding the lock across all parts creating one record. Example intentionally using a shared lock:

```java
private static void appendRecord(StringBuffer buffer, String label) {
    synchronized (buffer) {
        buffer.append("[");
        buffer.append(label);
        buffer.append("]");
    }
}
```

This is a **fragment** of a static method placed inside a Java class. If both threads call this method on the same buffer, whether the order is `"[A][B]"` or `"[B][A]"` still depends on scheduling, but each individual record stays contiguous. **Atomicity protects contiguity; it does not by itself dictate which thread goes first.**

## 10. Broader View: Atomicity, Visibility, Ordering

Multi-threaded programs generally need to consider at least three aspects:

1. **Atomicity**: steps must appear as one logical unit, without competing steps interleaving in between.
2. **Visibility**: when one thread writes, whether another thread can observe that value under the Java Memory Model rules.
3. **Ordering**: which steps must be observed in a particular order; for instance, `CountDownLatch`, `join()`, and monitors establish appropriate coordination relationships.

`StringBuffer`'s synchronized methods provide important guarantees at the individual operation level. However, they **do not replace** defining a logical sequence across multiple calls.

For example, if a program relies on one thread finishing a record before another thread reads the whole record, a **coordination mechanism** beyond a single `toString()` call may be needed: a monitor covering the entire record creation, a message queue, a latch, or an appropriate data-exchange design.

`toString()` captures an immutable `String` value of the content at the time of the call; it does not "wait" for the application to finish a transaction that has not been expressed with proper synchronization.

## 11. Comparing `StringBuffer`, `StringBuilder`, and `String`

| Type | Mutable? | Built-in synchronization | Best fit |
| --- | --- | --- | --- |
| `String` | No | No lock needed just to preserve content | Finished text values, sharing read-only strings. |
| `StringBuilder` | Yes | Not thread-safe when multiple threads modify concurrently | Building strings in a single thread or unshared local builders. |
| `StringBuffer` | Yes | Primary operations synchronized per object | When a mutable buffer truly needs to be shared by threads and per-method synchronization is desired. |

**Do not conclude "choosing `StringBuffer` makes everything safe."** It does not solve multi-step conditions, invariants spanning multiple objects, or business ordering between threads.

If a builder/buffer is **not shared** across threads, `StringBuilder` is usually simpler and avoids `StringBuffer`'s synchronization overhead. When multiple threads must produce records concurrently, it is sometimes better to let each thread build its own string and place it into a thread-safe queue, then have **one dedicated thread** assemble the result. That approach can make ordering and formatting easier to control than locking a global buffer.

Do not claim exact performance differences without measuring on the target JVM version and real workload.

## 12. What Problems Can Synchronizing on the Buffer Cause?

### Holding the Lock Too Long

```java
synchronized (buffer) {
    buffer.append("begin");
    // Should not wait for very slow I/O tasks here unnecessarily.
    buffer.append("end");
}
```

While the lock is held, threads wanting to enter synchronized methods of the same buffer may have to wait. Shorten the critical section, prepare data before locking, and hold the lock only for the portion protecting the invariant.

### Lock Acquisition Ordering

If a workflow holds `bufferA`'s lock and then acquires `bufferB`, while another thread does the reverse, **deadlock** can occur. When multiple locks must be held, define a consistent lock ordering across threads or change the design to reduce holding multiple monitors.

### Using a Public Buffer as a Monitor

If you expose a `StringBuffer` to uncontrolled code, external components can use `synchronized(buffer)` and hold the lock for a long time, blocking other components. In larger systems, it is usually better to **encapsulate shared state**, avoid exposing mutable buffers, and use an internal lock with atomic business APIs.

If the internal lock is a different object from the buffer, **do not forget** that every access path for the same invariant must go through that lock. A private lock does not automatically synchronize with `StringBuffer`'s monitor if someone accesses the buffer directly.

## 13. Common Mistakes

| Misconception | Reality | Fix |
| --- | --- | --- |
| "`StringBuffer` is thread-safe so two consecutive calls are atomic." | Each call can release the lock before the next call. | Lock the whole critical section or combine the work into one appropriate call. |
| "`if (length()==0) append()` will always add only once." | Two threads can both observe empty before either appends. | Wrap the entire check-then-act in the same monitor. |
| "Writing `append(a).append(b)` is one operation." | These are still two separate method calls. | Wrap the call chain in `synchronized(buffer)` if atomicity is needed. |
| "Each individual `append()` being safe means a multi-part record won't interleave." | Another thread can append between parts. | Build the complete record first or lock the entire record. |
| "`length()` just returned a value so it's definitely still valid at `deleteCharAt()`." | State can change after `length()` returns. | Read, check, and delete inside one critical section. |
| "`volatile StringBuffer` makes compound operations safe." | `volatile` does not merge multiple calls into one atomic action. | Use a monitor/lock or transaction-level synchronization design. |
| "Locking another object automatically locks the buffer too." | Two different monitors are two independent locking mechanisms. | Unify the lock and encapsulate all access paths. |
| "Using synchronized makes thread order match what we want." | Excluding interleaving does not determine which thread enters first. | Use an appropriate coordination mechanism if ordering matters. |
| "`toString()` creates a live view so you might read a half-written record." | The resulting `String` is an immutable value; however, a record may be in a **logically incomplete** state due to a non-atomic workflow. | Synchronize the entire record creation or publish a snapshot when complete. |

## 14. Self-Check Questions

**Question 1.** Two threads concurrently run the following snippet on the same `StringBuffer`. What can happen?

```java
if (buffer.length() == 0) {
    buffer.append("A");
}
```

**Answer:** both may see `length() == 0` and both append `"A"`, giving `"AA"`. There is no violation of the individual safety of `length()` or `append()`; the bug lies in **the two steps not being atomic**.

**Question 2.** Is changing to `buffer.append("[A").append("]")` enough to guarantee `"[A]"` won't have characters interleaved from another thread?

**Not yet.** Chained calls are still two calls. To protect an intact record, use `synchronized(buffer)` around both or build `"[A]"` independently and append **once**.

**Question 3.** If both threads write complete records inside a `synchronized(buffer)` block, are we guaranteed the order `"[A][B]"`?

**No.** It may be `"[A][B]"` or `"[B][A]"` depending on scheduling. What is guaranteed is that the parts of each record are not interleaved by competing calls using the same monitor.

**Question 4.** Why doesn't `synchronized(lock)` guarantee atomicity against other code directly calling `buffer.append()` if `lock` differs from `buffer`?

Because `buffer.append()` uses the buffer's lock mechanism, while `synchronized(lock)` uses a **different** monitor. The two sides do not wait on each other using the same lock. You must encapsulate the buffer and follow **one consistent locking convention**.

**Question 5.** If only a single thread builds text, is `StringBuffer` mandatory?

**No.** A local `StringBuilder` is usually appropriate. Synchronization in `StringBuffer` is only useful when addressing matching multi-threaded sharing needs, and it does not absolve you from designing atomicity for multi-step operations.

## Conclusion

- `StringBuffer`'s key calls are synchronized to support multiple threads accessing a mutable object.
- **Each method being safe individually does not mean an entire call sequence is atomic.** Another thread can still interleave between calls.
- Pay special attention to **check-then-act**, **read-modify-write**, **multiple `append()` calls for one record**, and **multiple reads that must be consistent**.
- When a logical transaction is needed, group the steps under **the same monitor/lock** and ensure all involved parties obey that rule.
- Choose the API based on real requirements: `StringBuilder` for local string building, `StringBuffer` for synchronized operations on a shared buffer, or queues/encapsulation when multi-threaded invariants are complex.
- **Atomicity, visibility, and ordering are distinct properties**. A thread-safe API does not automatically solve every coordination rule of a program.

## References

- [Java SE 21 API — `java.lang.StringBuffer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuffer.html): synchronization contract for operations, `append()`, `length()`, `toString()`.
- [Java SE 21 API — `java.lang.StringBuilder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html): comparison with an unsynchronized mutable builder.
- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html): monitors, happens-before, and the memory model.
- [Java SE 21 API — `java.util.concurrent.CountDownLatch`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordinating thread progress in race-reproduction examples.
