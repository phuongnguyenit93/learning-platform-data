# The Role of `StringBuffer` in Code Requiring Synchronization

`StringBuffer` is a class representing a **mutable** sequence of characters in Java. It provides familiar operations such as `append`, `insert`, `delete`, `replace`, `reverse`, and `toString`. The core distinction from `StringBuilder` is that **many manipulation methods of `StringBuffer` are synchronized (`synchronized`)**, helping protect the state of **the same buffer** when multiple threads invoke those operations.

However, the statement "`StringBuffer` is thread-safe" must be understood **within its proper scope**:

- Each synchronized operation on the **same `StringBuffer` object** is serialized through that object's lock (monitor).
- A sequence of multiple separate calls, such as **checking the length before appending**, is **not automatically atomic**; another thread can interleave between the two calls.
- An input that is a shared mutable `CharSequence` or array may need its **own** protection mechanism; synchronizing on the destination buffer does not lock every source object.
- If there is no need to share a mutable text area across multiple threads, `StringBuilder` is usually simpler and more appropriate. `StringBuffer` is not the default choice for every string concatenation operation.

This lesson focuses on the **synchronization role** of `StringBuffer`, the guarantees it provides, the limits of those guarantees, and how to choose the right design.

## 1. Quick Comparison of `String`, `StringBuilder`, and `StringBuffer`

| Characteristic | `String` | `StringBuilder` | `StringBuffer` |
| --- | --- | --- | --- |
| Can content be modified in place? | No; immutable | Yes | Yes |
| Does `append(...)` modify the object itself? | No mutable `append` API like a builder | Yes | Yes |
| Synchronize multiple operations on the same object? | No lock needed to protect immutable content | Not self-synchronized | Many methods are `synchronized` |
| Typical fit | Finished text values, passing shared content | Building text locally within a single thread | Shared mutable character buffer when per-operation synchronization is needed |
| Effect of multiple threads writing concurrently | Cannot modify `String` content | Risk of data race and corrupted state | Synchronized operations on the same buffer are serialized, but multi-step business logic still needs coordination |

Both `StringBuilder` and `StringBuffer` inherit from `AbstractStringBuilder` by JDK design, and both implement interfaces related to character sequences and appending data. **You should not write code that depends on internal/implementation classes**; rely on the public API and synchronization contract of the class being used.

Choosing `StringBuffer` does not mean every variable, thread, source array, or related object automatically becomes safe for concurrent execution.

## 2. What Does `synchronized` on the Buffer Protect?

Several methods of `StringBuffer` are declared `synchronized`, such as specific add, modify, read, and state-access operations. When one thread is executing a synchronized method of a `StringBuffer`, another thread wanting to enter a synchronized method that uses **the same lock of that very buffer** must wait.

Imagine two threads pointing to the same buffer:

```text
Thread A ─┐
          ├──> StringBuffer shared
Thread B ─┘          │
                     └─ monitor of shared
                        (only one thread holds this lock at a time)
```

Example:

```java
StringBuffer shared = new StringBuffer();
shared.append("A");
shared.append("B");
```

Each `append` above writes to the `shared` object. If other threads concurrently use `shared.append(...)`, the append calls are synchronized with one another on this buffer. It does not mean only one thread runs in the entire program, or that two consecutive `append` calls from the same thread are combined into a single transaction.

**Each object's monitor is separate:** two different `StringBuffer` instances have two separate locks. Synchronizing a method of buffer X does not lock buffer Y, nor does it lock another `StringBuilder` variable.

### Synchronization Also Relates to Data Visibility

In addition to *mutual exclusion*, a `synchronized` monitor participates in the Java Memory Model's **happens-before** rule. One thread releasing an object's monitor happens-before another thread subsequently acquiring **that same monitor**, ensuring consistent data visibility.

In practice, synchronized operations on the same `StringBuffer` not only prevent two concurrent writes from corrupting internal state, but also help ensure subsequent operations see updates protected by the same locking mechanism.

However, if you read/write other variables outside this lock, or coordinate multiple resources, there is **no automatic rule** that all business state remains consistent merely through a `buffer.append(...)` call.

## 3. Multi-Threaded Example: Each `append` Call Is Protected

When multiple threads append a fixed character to the **same `StringBuffer` object**, the final character count can be verified after all threads have finished.

Create the file `ConcurrentBufferAppendDemo.java`:

```java
public class ConcurrentBufferAppendDemo {
    public static void main(String[] args) throws InterruptedException {
        final int threadCount = 4;
        final int repeats = 1000;
        StringBuffer shared = new StringBuffer();
        Thread[] threads = new Thread[threadCount];

        for (int i = 0; i < threadCount; i++) {
            threads[i] = new Thread(() -> {
                for (int j = 0; j < repeats; j++) {
                    shared.append('x');
                }
            });
        }

        for (Thread thread : threads) {
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        String result = shared.toString();
        System.out.println(result.length());
        System.out.println(result.chars().allMatch(ch -> ch == 'x'));
    }
}
```

Compile/run on JDK 17 or later:

```bash
javac ConcurrentBufferAppendDemo.java
java ConcurrentBufferAppendDemo
```

Output:

```text
4000
true
```

Why is the result deterministic?

1. There are four threads, each calling `append('x')` exactly 1,000 times.
2. Calls to `append` on a `StringBuffer` are synchronized so internal state updates of the buffer do not overlap.
3. `join()` ensures the `main` thread reads the result only **after** each thread finishes; actions of a finished thread have a happens-before relationship with the successful return of `join()`.
4. All appended characters are `'x'`, so interleaving order does not affect the content; the result has length 4,000 and every code unit is `x`.

If the four threads append **different strings**, the order of appearance among calls depends on scheduling. `StringBuffer` guarantees the safety of each individual operation, **not** which thread appends first based on request time or thread ID.

Do not use the exact interleaving order of threads as a test assertion unless the application has its own ordering mechanism.

## 4. How Is `StringBuilder` Different When Shared Across Threads?

`StringBuilder` has a nearly identical string-building API but **does not automatically synchronize** mutable operations. If multiple threads call `append` on the same `StringBuilder` without proper synchronization relationships, the program has a **data race** and there is no guarantee that the resulting count or content will be correct.

You should not write a test assuming `StringBuilder` "will definitely lose characters" on every run. A race may manifest sometimes and not other times; the outcome depends on thread scheduling, JIT optimizations, and the environment. What matters is that **the shared design lacks thread-safety guarantees**, not proving a bug with a lucky run.

A contrasting example about **ownership**, without needing to share a mutable builder:

```java
// Each thread owns its own builder inside the method.
static String buildLine(int id) {
    StringBuilder local = new StringBuilder();
    local.append("thread=").append(id);
    return local.toString();
}
```

This is an illustrative method snippet, not a standalone program. Each call creates a new builder manipulated only within that call; the returned result is an immutable `String`. Sharing the **resulting string** instead of sharing a mutable builder often reduces the need for synchronization.

Not every multi-threaded task needs `StringBuffer`. The first question is: **do multiple threads actually need to modify the same character sequence object?**

## 5. Four Design Boundaries to Recognize

A `StringBuffer` object helps coordinate **each individual content modification**. When placing it into a real program, distinguish the boundaries of the operation, source data, ownership, and result snapshot.

| Need | Is each `StringBuffer` method alone enough? | Additional design |
| --- | --- | --- |
| Multiple threads only append an independent segment via `append(String)` | Yes, for each individual append to the same buffer | Do not assume ordering between threads |
| Check a condition before modifying, such as a length limit | Not enough | Lock across both the check and the update |
| Build a single record from multiple `append` calls | Not enough | Construct a complete `String` then append once, or lock the whole group |
| Copy from a mutable source `CharSequence` | Not enough | Synchronize convention on the source or capture a stable `String` first |
| Hand text values to readers for later use | Should not hand out the mutable buffer itself | Return `buffer.toString()` at the desired point |

### An Independent Operation Differs from a Business Rule

For example, checking length before appending a character consists of two separate calls:

```java
// May exceed the limit when multiple threads check before writing.
if (shared.length() < 3) {
    shared.append('x');
}
```

If the limit is a mandatory invariant, the same monitor must be used for both steps:

```java
synchronized (shared) {
    if (shared.length() < 3) {
        shared.append('x');
    }
}
```

This bug and how to reproduce it using `CountDownLatch` are covered in full in the lesson **"Per-Method Synchronization Does Not Guarantee Atomicity for a Sequence of Operations"**; the lesson **"Choosing a Shared Lock"** analyzes the difference between the buffer's monitor and a private lock of a data-managing class.

### A Record Can Be Complete from the Start

```java
String record = "[" + userId + "] done\n"; // Local, already complete data.
shared.append(record);                    // Single modification to the shared buffer.
```

Doing this keeps each record contiguous when threads all append via a single call on the same buffer. **The order of records is still not guaranteed**. If multiple fields or conditions must also be updated together with the record, the entire invariant must be protected.

### A Synchronized Destination Does Not Make the Source Stable

When reading a `StringBuilder` or another mutable `CharSequence`, you must ensure writers do not modify it during the copy. You can capture an immutable `String` under a locking convention followed by all parties, and then use the snapshot multiple times. The lesson **"Mutable Source Objects During append or insert"** dives deeper into overloads, `start/end` ranges, `CharBuffer`, and self-references.

### Preserving Ownership of the Buffer

`final StringBuffer` only fixes the reference; the content can still be modified. When the object is internal state of a class, consider keeping the field `private`, exposing APIs that operate according to invariants, and returning `String` to callers that only need to read. The lesson **"Converting from StringBuffer to String"** explains snapshots, `null` handling, and Unicode.


## 6. When Should You Choose `StringBuffer`?

### When to Consider `StringBuffer`

- **There is a genuinely shared mutable buffer**, and multiple threads need to invoke operations on that same buffer.
- You want to leverage the built-in synchronized methods and clearly understand the boundary of each operation.
- You are maintaining a legacy API or library that already uses `StringBuffer` as part of its contract, and changing the type could affect compatibility.
- Data is constructed sequentially across calls that need to interact with APIs that inherently accept `StringBuffer`.

### When to Usually Choose Another Solution

- **Each task only concatenates strings within one thread:** choose a local `StringBuilder`.
- **Only need to share an unchanging text value:** use an immutable `String`.
- **Need an entire multi-operation transaction on a builder:** even if choosing `StringBuffer`, a lock wrapping the transaction is still needed; or use `StringBuilder` with an external lock applied consistently.
- **Need to store many events in strict order, pass messages, or batch:** consider a queue, immutable records, a single aggregator thread, or an appropriate concurrent structure, instead of turning `StringBuffer` into a queueing system.
- **Threads frequently contend on the same buffer:** a single lock can cause contention. Consider building strings locally and synchronizing only at the merge point.

Do not claim that `StringBuffer` is always "slow" or `StringBuilder` is always "fast" on every JVM and in every scenario. `StringBuffer` has synchronization-related overhead, but performance also depends on JVM optimizations, contention, data size, and design. Choose based on correctness requirements first, and benchmark in practice if performance matters.

## 7. Common Misconceptions

**Misconception 1 — "Using `StringBuffer` makes the whole program thread-safe."** This class only provides synchronization for operations on the buffer; other variables and resources must be protected separately.

**Misconception 2 — "`length()` is thread-safe and `append()` is thread-safe, so `if (...) append(...)` is also thread-safe."** This is a compound operation. A critical section covering both the check and the update is required.

**Misconception 3 — "`append(...).append(...)` automatically locks across the entire chain."** Each call has its own synchronization scope. Operations from another thread can interleave in between.

**Misconception 4 — "`StringBuffer` determines the order of threads."** It synchronizes individual operations; the order in which threads acquire the lock depends on scheduling, not predetermined by thread ID or `start()` call order.

**Misconception 5 — "Taking a `StringBuffer` as a parameter is automatically safe with a mutable source."** The destination and source are different objects. Stable observation of the source must be ensured if the source is shared and modified concurrently.

**Misconception 6 — "`final StringBuffer` is immutable."** `final` fixes the reference; it does not prevent modifying the buffer's content.

**Misconception 7 — "You can test for a race with a single trial run, and if it passes, it is safe."** Concurrency bugs may not appear in a single execution; rely on API contracts and happens-before relationships instead of hoping for random testing luck.

**Misconception 8 — "Any API using `StringBuilder` is wrong in a multi-threaded application."** A builder owned and used locally by a single thread is completely normal, even in a multi-threaded server.

**Misconception 9 — "`StringBuffer` can replace any `Lock` or concurrent structure."** It does not provide multi-object transactions, message queues, or event-ordering protocols.

**Misconception 10 — "`StringBuffer` is immutable like `String`."** `StringBuffer` can be modified in place, so you must consider ownership, synchronization, and exposing references externally.

## 8. Self-Check Questions

### Question 1: Final Character Count

Four threads each append `"x"` one thousand times to the same `StringBuffer`; the main thread reads only after `join`. Assuming no delete operations, what is the expected length?

**Answer:** 4,000. Each `append` is synchronized on the buffer; `join` ensures the main thread reads after all have finished.

### Question 2: Why Is `synchronized(shared)` Still Needed?

```java
if (shared.length() < 10) {
    shared.append("x");
}
```

**Answer:** Between `length()` and `append()`, another thread can append. To maintain the limit of 10, the read–check–write region must be locked as a single business operation.

### Question 3: Sharing the Source or Sharing the Destination?

Thread A calls `target.append((CharSequence) source)` while Thread B modifies `source`, which is a `StringBuilder`. Does having `target` be a `StringBuffer` solve the entire problem by itself?

**Answer:** No. The destination buffer's lock does not automatically synchronize source reads with source writes. Clear ownership, a snapshot, or lock coordination among threads using the source is required.

### Question 4: Designing a Multi-Part Record

Multiple threads need to add lines `id=..., status=...` to a shared buffer where each line must remain contiguous. What solutions can be chosen?

**Answer:** Build the entire line into a `String` in a local `StringBuilder` and make a single `shared.append(record)` call, or lock the same buffer around all append calls for one line. If ordering between records must be preserved, a separate ordering protocol is required.

### Question 5: Which Builder Should Be Chosen?

A function simply builds simple JSON to return a `String`, creating a new builder on each call and never letting other threads touch the builder. Is `StringBuffer` needed?

**Answer:** Not necessarily. A local `StringBuilder` is the natural choice if synchronized operations on the same object are not required. Regardless of which class is used, real-world JSON needs proper escaping and valid formatting; manual string concatenation does not automatically handle JSON rules.

## Conclusion

**The role of `StringBuffer` is to support modifying a shared character sequence with operations synchronized at the object level.** It is suitable when multiple threads genuinely need to interact with **the same mutable buffer**, but it does not mean a whole read–check–write sequence is atomic, does not automatically protect other mutable sources, and does not establish arbitrary event ordering. Identify **which data is shared**, **which lock protects that data**, and **which business boundaries need to be atomic**. If text is only built locally and then passed along as a `String`, a local `StringBuilder` together with immutable data usually yields a cleaner design.