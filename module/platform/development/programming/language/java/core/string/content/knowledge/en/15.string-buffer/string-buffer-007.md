# Synchronization Cost and When StringBuffer Is Truly Needed

## 1. Objective and Practical Conclusion

`StringBuffer` is a **mutable** character sequence with synchronization for necessary operations on **the same object**. `StringBuilder` has a nearly identical API but **is not self-synchronized**. Therefore, when building strings inside a method, inside a request, or in a task where the buffer is owned by only one thread, the usual choice is `StringBuilder`. Consider `StringBuffer` only when multiple threads genuinely access and mutate **the same buffer**, protection is needed at the level of **individual method calls**, or compatibility with legacy APIs using `StringBuffer` is required.

Key takeaway: `StringBuffer`'s "thread-safe" behavior does **not** mean every multi-call operation sequence is atomic, does not enforce ordering between threads, and does not automatically protect a source `CharSequence` being modified by another thread.

## 2. How Does StringBuffer Synchronization Work?

- State-protecting methods such as `append(...)`, `insert(...)`, `delete(...)`, `setLength(...)`, and many read operations synchronize on the corresponding `StringBuffer` object. Calls on **the same object** are coordinated via its monitor, preventing overwrites or corruption of internal state when threads operate concurrently according to the API contract.
- When one thread exits a `synchronized` block/method and another thread later acquires **the same monitor**, the Java Memory Model establishes a *happens-before* relationship between the unlock and subsequent lock, ensuring updates are properly published.
- The monitor is **per-object**, not a global lock for all `StringBuffer` instances. Two independent buffers do not contend on the same intrinsic lock.
- With `append("A")`, adding that string to the buffer is protected as a single call. However, `append("[")` then `append("A")` then `append("]")` are **three** calls; another thread can interleave its own operations between those calls.
- Synchronization protects the **destination** buffer; it does not implicitly lock source data. For example, when `append(CharSequence source)` reads a shared mutable source object, the caller must ensure the source data stays stable during the read (such as using an immutable `String` or appropriate synchronization).

### Guarantees to Distinguish

| Scenario | Automatically guaranteed by `StringBuffer`? | Explanation |
| --- | --- | --- |
| Multiple threads call `append('x')` on the same buffer | Yes, at the single-call level | Internal state is not concurrently updated without synchronization; character order depends on scheduling |
| Two consecutive `append` calls must stay adjacent | No | Another thread can interleave in between |
| `if (buffer.length() == 0) buffer.append("init")` runs only once | No | Reading and writing are two separate operations |
| Threads must follow order A before B | No | External coordination/ordering mechanism is required |
| Another source buffer is modified during `append(source)` | No | Locking the destination does not automatically create a stable snapshot of the source |
| Each thread works on its own separate buffer | No cross-buffer synchronization needed | `StringBuilder` is usually more suitable |

## 3. Where Does Synchronization Cost Come From?

A synchronized method call incurs additional lock-coordination work and memory-ordering constraints compared to its unsynchronized counterpart. Two cases should be separated:

1. **Uncontended locks:** there is still synchronization expression and handling overhead, though HotSpot/JIT can optimize eligible locks (for instance when proving an object does not escape scope). You cannot conclude every `append` is slower by a fixed amount; actual efficiency depends on the JDK, code, and runtime behavior.
2. **Multiple threads contending on the same buffer:** only one thread can hold the monitor for the locked work at a time. Other threads must wait; lock ownership handoffs, memory synchronization, and thread scheduling increase latency and limit throughput and scalability. For sequences of many very short `append` calls, contention cost can be significant relative to the work of appending characters.

Beyond locking, both `StringBuilder` and `StringBuffer` may need to expand storage when exceeding `capacity()`. Allocation/copying during capacity growth is a **separate cost** from synchronization; setting a sensible initial capacity can help both. Do not attribute every timing or memory difference to `synchronized`.

There is no universal ratio like "`StringBuffer` is N times slower" valid for every application. JVMs vary in warm-up, JIT, garbage collection, data sizes, contention levels, and usage patterns. Even a single-threaded test does not reflect the cost when multiple threads share one object.

## 4. When Should StringBuffer Actually Be Chosen?

**Reasonable cases:**

- **A mutable object must be shared:** multiple threads concurrently `append`/edit a single `StringBuffer`, and the business contract only requires safety for **each individual call**, without requiring consecutive calls to form a transaction.
- **Existing APIs/libraries require `StringBuffer`:** parameter types or compatibility contracts in legacy systems must be preserved. When refactoring the design, re-evaluate sharing needs and whether `StringBuilder` can replace it.
- **Sharing a buffer with externally locked compound operations:** `StringBuffer` can still be used, provided the entire check/write sequence is wrapped in the same `synchronized (buffer)` when business-level atomicity is desired. In a new design, also consider encapsulated state with an explicit lock and an internal `StringBuilder`.

**Usually `StringBuffer` is unnecessary:**

- Concatenating strings in a loop/method running on one thread; each request/task has its own buffer.
- Multiple threads work in parallel, yet **each thread owns its own buffer**, then passes immutable `String` results to an aggregator.
- Short strings with clear `+` expressions, or conventional joining via `String.join`/`StringJoiner`/`Collectors.joining`. Choose APIs for readability and data characteristics; do not assume every `+` creates excessive objects.
- Multiple threads generate independent text segments: use local results and an appropriate collection/coordination mechanism, rather than forcing all threads to contend on one shared buffer just to be "thread-safe."

### Quick Selection Rules

| Workload characteristics | Usually sensible choice | Why |
| --- | --- | --- |
| Mutable string building in one thread | `StringBuilder` | No locking needed for a local buffer |
| Only finished immutable strings needed | `String` | Easy to share, no mutation synchronization needed |
| Multiple threads appending to the **same** mutable buffer, independent ops | `StringBuffer` | Synchronizes each operation |
| Multiple threads writing a record that must stay contiguous across calls | One lock block covering the whole record, or append a pre-built record in **one** call | `StringBuffer` alone does not make multiple calls atomic |
| Legacy system using `StringBuffer` signatures | `StringBuffer` at that boundary | Complies with existing contract |
| Multiple threads building separate string segments | Local `StringBuilder` + coordinated result aggregation | Reduces shared-lock contention |

## 5. Java 17 Example: Reducing Monitor Entries by Batching

If each thread appends hundreds of independent characters to a shared buffer, calling `append(char)` character by character enters `StringBuffer`'s monitor many times. An alternative is for each thread to build **a local chunk** in a `StringBuilder` and append the whole chunk in one call. Both are equivalent in content, yet **the number of calls on the shared buffer differs**.

Create the file `StringBufferBatchAppendDemo.java`:

```java
public class StringBufferBatchAppendDemo {
    private static void fill(StringBuffer shared, boolean batch)
            throws InterruptedException {
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            final char symbol = (char) ('A' + i);
            workers[i] = new Thread(() -> {
                for (int group = 0; group < 10; group++) {
                    if (batch) {
                        StringBuilder local = new StringBuilder(25);
                        for (int j = 0; j < 25; j++) {
                            local.append(symbol);
                        }
                        shared.append(local.toString());
                    } else {
                        for (int j = 0; j < 25; j++) {
                            shared.append(symbol);
                        }
                    }
                }
            });
        }

        for (Thread worker : workers) worker.start();
        for (Thread worker : workers) worker.join();
    }

    private static boolean expectedCounts(StringBuffer buffer) {
        String text = buffer.toString();
        if (text.length() != 1_000) return false;
        for (char letter = 'A'; letter <= 'D'; letter++) {
            final char expected = letter;
            if (text.chars().filter(ch -> ch == expected).count() != 250) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) throws InterruptedException {
        StringBuffer single = new StringBuffer();
        StringBuffer batched = new StringBuffer();
        fill(single, false);
        fill(batched, true);

        System.out.println("single correct=" + expectedCounts(single));
        System.out.println("batched correct=" + expectedCounts(batched));
        System.out.println("single append calls=" + (4 * 10 * 25));
        System.out.println("batched append calls=" + (4 * 10));
    }
}
```

```bash
javac StringBufferBatchAppendDemo.java
java StringBufferBatchAppendDemo
```

Output:

```text
single correct=true
batched correct=true
single append calls=1000
batched append calls=40
```

Each thread adds 250 characters of its own, so both results are 1,000 code units long and contain 250 of each letter `A`, `B`, `C`, `D`. The character-by-character version makes 1,000 `append` calls on the shared buffer; the batched version makes only 40. Group contents may be interleaved according to thread scheduling, yet each `append(String)` still adds an entire group as one operation on the destination.

**This is an API call count, not a speed benchmark.** The batched version requires an extra `StringBuilder` and creates local `String` objects, which can increase allocation cost. Actual benefit also depends on batch size, thread count, contention level, and GC. If performance matters, measure with JMH under realistic load before choosing.


## 6. Measure Performance Properly Before Optimizing

If performance is genuinely an issue, write a benchmark reproducing how the application uses the buffer:

1. Separate the **per-thread private buffer** scenario from **multiple threads sharing one buffer**. These are two different problems.
2. Across compared alternatives, keep data-generation logic, string sizes, loop counts, input sizes, and results equivalent. Avoid semantically broken optimizations just for flattering numbers.
3. Use **JMH** with warm-up, multiple measurement iterations/forks, and explicit thread counts; ensure results are consumed so the JIT does not eliminate the work. Measure both throughput and latency under contention.
4. Observe profiler/metrics for monitor wait time, CPU, allocation, and GC where relevant; compare on a JDK/hardware setup close to production.
5. If a shared buffer becomes a bottleneck, reconsider the **sharing design** before swapping one class for another. Replacing a shared `StringBuffer` with a shared `StringBuilder` without adding synchronization is **incorrect for thread safety**.

Do not use `System.nanoTime()` to measure a single loop and conclude the result represents the system: warm-up, inlining, dead-code elimination, and the scheduler can all skew measurements.

## 7. Common Misunderstandings

- **"It's a multi-threaded application, so every string concatenation must use StringBuffer."** False: what decides this is **whether the same instance is accessed concurrently**, not how many threads exist in the application.
- **"StringBuffer makes the whole block of code thread-safe."** False: it only protects individual operation behavior per the class contract. Check-then-write rules, multi-step updates, or relationships with other data must still be synchronized separately.
- **"Synchronized always makes a program drastically slower."** False: there is no fixed multiplier; the JIT applies optimizations and cost depends on contention. However, locking on a shared resource can still become a bottleneck.
- **"You can replace a shared StringBuffer with StringBuilder to speed it up."** False without redesigning ownership/locking; `StringBuilder` provides no safety for concurrent writes.
- **"StringBuffer automatically locks the source CharSequence too."** False: it only synchronizes on the destination buffer; a shared mutable source needs independent protection or a snapshot.
- **"If two threads append, characters definitely appear in thread-creation order."** False: execution order depends on the scheduler and synchronization coordination.

## 8. Pre-Selection Checklist

Before keeping or creating a `StringBuffer`, ask yourself: **(1)** Do multiple threads actually share *the exact same instance*? **(2)** Are there concurrent writes? **(3)** Does each individual call already satisfy business atomicity? **(4)** Can content be built locally and shared as an immutable `String`? **(5)** Are there API compatibility constraints? **(6)** Have you measured significant contention or performance impact?

If you only need to assemble data locally, choose `StringBuilder`. If you genuinely need to share a mutable buffer with per-method mutations, `StringBuffer` is a ready option. If multi-operation invariants or business ordering are needed, additional synchronization/coordination mechanisms must be designed regardless of class name.

### References

- [Oracle Java SE 17 — StringBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuffer.html)
- [Oracle Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
