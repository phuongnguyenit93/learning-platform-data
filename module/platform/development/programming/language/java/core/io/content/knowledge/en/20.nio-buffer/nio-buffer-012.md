# Buffers Are Not Thread-Safe by Default in Java NIO

## 1. The Issue to Understand

`java.nio.Buffer` and its subclasses such as `ByteBuffer`, `CharBuffer`, and `IntBuffer` are designed for efficient data manipulation and tracking read/write state. They **are not thread-safe by default when multiple threads access the same buffer concurrently**. The Java API documentation explicitly states that buffers are not safe for use by multiple concurrent threads without proper synchronization.

This is an issue even when multiple threads **only read bytes**. With a relative read method such as `get()`, reading modifies `position`, so the threads are mutating **shared cursor state**. If another thread calls `flip()`, `clear()`, or `compact()` during reading, bounds errors and inconsistent data can also occur.

Two separate questions must be distinguished:

- **Is buffer state shared?** `position`, `limit`, `mark`, and operations mutating them determine which bytes are read/written.
- **Is the data memory region shared?** Two buffers can have separate cursors while still pointing to the same array or memory region; reading/writing the same region can cause data races.

Design conclusion: **A buffer is safe only when usage ownership, operations, and synchronization relationships among threads are clearly defined.** Never assume `ByteBuffer` provides built-in locking merely because it belongs to Java NIO.

## 2. Position, limit, capacity, mark Are Mutable State

A `Buffer` has four core concepts:

| Property | Meaning | Multi-Thread Consideration |
| --- | --- | --- |
| `capacity` | Size of the memory represented by the buffer, constant over the object's lifetime | Does not protect other state |
| `limit` | Exclusive end boundary of the currently permitted read/write region | One thread changing `limit` can cause other threads to read the wrong range |
| `position` | Index for the next relative read/write operation | `get()`/`put(...)` advance a shared `position` |
| `mark` | Saved position to return to with `reset()` | Changing `position`/`limit` can invalidate `mark` |

The invariants maintained by a buffer during a single operation take the form `0 ≤ position ≤ limit ≤ capacity`; if a mark is set, `mark ≤ position`. The fact that a single method maintains buffer invariants **does not mean a sequence of operations from multiple threads executes atomically like a transaction**.

Typical buffer lifecycle example:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(4);
buffer.put((byte) 10);
buffer.put((byte) 20);
buffer.flip();        // switch from write to read: limit=2, position=0
byte a = buffer.get(); // a=10; position=1
~~~

This is an **illustrative snippet** that can go inside a method. `put`, `flip`, and `get` all mutate state. `flip()` prepares to read the newly written data; `clear()` resets `position`/`limit` for a new write cycle without **erasing data**, while `compact()` can move unread bytes in memory.

If one thread reads while another thread calls `flip()`/`clear()`/`compact()` without synchronization, the reader can see its readable range altered, encounter stale bytes, or read data at unexpected offsets.

## 3. A Relative Read Is a State-Mutating Operation

Suppose a buffer holds four bytes:

~~~text
index:     0   1   2   3
data:     10  20  30  40
position:  0
limit:     4
~~~

Two threads A and B both call `get()` on **the exact same buffer object**. Each `get()` reads the byte at the current `position` and updates the next position. Even if nobody modifies the byte array contents, both threads are contending over **the exact same cursor**.

One valid interleaving under controlled ordering:

~~~text
A: get() -> 10, position=1
B: get() -> 20, position=2
B: get() -> 30, position=3
A: get() -> 40, position=4
~~~

If A wants the first two bytes and B wants the last two bytes, calling `get()` on a single shared buffer **cannot enforce work boundaries by itself**. Moreover, when two threads truly call concurrently without synchronization, the read and `position`-update steps have no atomic guarantee to hand out each byte exactly once: data can be duplicated, skipped, or throw `BufferUnderflowException`/`BufferOverflowException` depending on timing.

Distinguish **controlled operation interleaving** from a **data race**: the example in the next section uses latches for deterministic output in order to prove cursor sharing. It does not rely on triggering a random data race, so it is not a test designed to catch every race.

## 4. Runnable Java 17+ Example: Shared Cursor vs. Independent Views

Create **`BufferThreadsDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;

public class BufferThreadsDemo {
    public static void main(String[] args) throws InterruptedException {
        ByteBuffer shared = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
        CountDownLatch aReadFirst = new CountDownLatch(1);
        CountDownLatch bReadBoth = new CountDownLatch(1);
        int[] a = new int[2], b = new int[2];

        Thread threadA = new Thread(() -> {
            a[0] = Byte.toUnsignedInt(shared.get());
            aReadFirst.countDown();
            await(bReadBoth);
            a[1] = Byte.toUnsignedInt(shared.get());
        });
        Thread threadB = new Thread(() -> {
            await(aReadFirst);
            b[0] = Byte.toUnsignedInt(shared.get());
            b[1] = Byte.toUnsignedInt(shared.get());
            bReadBoth.countDown();
        });

        threadA.start();
        threadB.start();
        threadA.join();
        threadB.join();
        System.out.println("Shared A: " + Arrays.toString(a));
        System.out.println("Shared B: " + Arrays.toString(b));
        System.out.println("Shared position: " + shared.position());

        ByteBuffer source = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
        ByteBuffer left = source.slice(0, 2).asReadOnlyBuffer();
        ByteBuffer right = source.slice(2, 2).asReadOnlyBuffer();
        int[][] results = new int[2][2];

        Thread leftThread = new Thread(() -> {
            results[0][0] = Byte.toUnsignedInt(left.get());
            results[0][1] = Byte.toUnsignedInt(left.get());
        });
        Thread rightThread = new Thread(() -> {
            results[1][0] = Byte.toUnsignedInt(right.get());
            results[1][1] = Byte.toUnsignedInt(right.get());
        });
        leftThread.start();
        rightThread.start();
        leftThread.join();
        rightThread.join();
        System.out.println("View A: " + Arrays.toString(results[0]));
        System.out.println("View B: " + Arrays.toString(results[1]));
        System.out.println("Source position: " + source.position());
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
    }
}
~~~

Compile and run:

~~~bash
javac BufferThreadsDemo.java
java BufferThreadsDemo
~~~

**Exact** stdout of the program (compiled and run on the JDK):

~~~text
Shared A: [10, 40]
Shared B: [20, 30]
Shared position: 4
View A: [10, 20]
View B: [30, 40]
Source position: 0
~~~

Explanation:

1. The first two threads receive the same `ByteBuffer shared`. `CountDownLatch` enforces the order: A reads one byte, B reads two bytes, then A reads the last byte. As a result, A receives `[10, 40]` instead of an assumed contiguous pair `[10, 20]`. Every `get` in this part is ordered via latches, so **this demonstrates `position` sharing rather than simulating an unsynchronized race**.
2. In the second part, `slice(0, 2)` and `slice(2, 2)` create two views over distinct segments of the same data. Each view has its **own** `position`, `limit`, and `mark`. `asReadOnlyBuffer()` forbids writes **through that view**.
3. Each of the second pair of threads uses only its own view, and neither thread mutates the underlying bytes; A reads `[10, 20]` and B reads `[30, 40]`.
4. `source.position()` remains 0 because reading through views does not move `source`'s cursor. The threads are started after creating and configuring the views; `Thread.start()` and `Thread.join()` also establish the proper *happens-before* relationships for the example's inputs and outputs.

**Do not conclude that `slice` and `asReadOnlyBuffer` make every sharing scenario thread-safe.** Views still share the same byte memory; if another thread holds a reference to the original buffer or underlying array and writes to it, the data read by the views can change concurrently.

## 5. duplicate(), slice(), asReadOnlyBuffer(): Separating Cursors, Not Necessarily Data

Java NIO allows creating multiple views onto the same memory region:

| Creation | View's `position/limit/mark` State | Byte Contents | Caution |
| --- | --- | --- | --- |
| `original.duplicate()` | Initially copies state values; moves independently afterward | Shares backing storage | Two views writing to the same byte can still conflict |
| `original.slice()` | New view with position 0, limit/capacity equal to source's `remaining()` at creation | Shares region starting from source's current `position` | Unaffected by later source cursor changes, yet still shares data |
| `original.slice(index, length)` | New view with position 0, limit/capacity equal to `length` | Shares exact region from `index` to `index+length` of source | Only on Java versions supporting the overload; works well on Java 17+ |
| `original.asReadOnlyBuffer()` | Independent cursor state, initially matching source | Shares data, yet **forbids `put` through the view** | Owner or another alias can still mutate data |
| `ByteBuffer.allocate(n)` | Independent state | Allocates new byte region | Useful when each worker needs private writes, requiring a result-exchange mechanism |
| `ByteBuffer.wrap(array)` | Independent buffer state | **Shares the external `array`** | Anyone retaining the original array can still mutate contents |

Decisive points:

- Separating **cursors** with `duplicate`/`slice` keeps threads from stepping on each other's `position` when each thread owns its own view.
- Separating **data** requires separate memory, e.g., allocating a new buffer and copying bytes, or guaranteeing disjoint write regions along with rules forbidding overlapping writable aliases.
- Reading from views sharing a data region can be safe in practice when the data is finalized, safely published (*safe publication*), and no writer mutates that region anymore.
- A read-only view only protects the write interface of that view itself; it **does not make backing data immutable**.

Example of a read-only view whose observed data can still change:

~~~java
byte[] bytes = {1, 2, 3};
ByteBuffer readOnly = ByteBuffer.wrap(bytes).asReadOnlyBuffer();
bytes[0] = 9;
System.out.println(readOnly.get(0)); // 9
~~~

This is an illustrative snippet that can go inside a method. There is no concurrent access in this example; it demonstrates backing-storage sharing. If modifying `bytes[0]` happened concurrently with reading without synchronization, *visibility* issues and data races would also arise.

A buffer created via `allocateDirect` is not automatically thread-safe either. *Direct* only refers to allocation/accessibility of off-heap memory; it does not provide locking, write permissions, or memory ordering on the program's behalf.

## 6. Absolute get/put Avoids Mutating position but Does Not Solve Every Race

`ByteBuffer` offers **relative** and **absolute** operations:

~~~java
byte next = buffer.get();           // gets at position, increments position
byte atThree = buffer.get(3);       // gets at index 3, does not change position
buffer.put((byte) 7);               // puts at position, increments position
buffer.put(3, (byte) 7);            // puts at index 3, does not change position
~~~

This is an illustrative snippet assuming `buffer` exists and indices lie within a valid `limit`. An absolute-index operation does not change the cursor, avoiding **one source of contention**. However:

- If another thread concurrently changes `limit`, index-bounds validation and accessible ranges can become unstable.
- Two writers accessing the same index, or a reader reading while a writer writes the same byte, still suffer data races and uncoordinated results.
- Nothing guarantees that a sequence of absolute operations such as "read 4 bytes, check, then write 4 bytes" is atomic.
- `getInt(index)` or `putLong(index, value)` does not automatically make updating multiple fields of a record transactional. Atomicity and visibility must be designed using actual API/JVM guarantees.

Absolute access can be used in a **read-only schema with frozen data** across clear byte ranges, though the buffer must still be safely published to the threads.

## 7. Safe Strategies for Multi-Threaded Execution

### 7.1. Thread Confinement: Each Thread Owns Its Own Buffer

This is usually the clearest option: each worker calls `ByteBuffer.allocate(...)` or receives its own copy of the data, and only that worker calls `put/get/flip/clear`. Neither mutable cursors nor backing storage are shared with other writers.

Example of single-threaded task logic:

~~~java
static int parseTwoBytes(byte[] input) {
    ByteBuffer own = ByteBuffer.wrap(input.clone());
    int a = Byte.toUnsignedInt(own.get());
    int b = Byte.toUnsignedInt(own.get());
    return (a << 8) | b;
}
~~~

The snippet above is an **illustrative method**; the caller must ensure `input` has at least two bytes. `clone()` creates a copy separating contents from the array held by the caller. If only one thread ever owns `input` throughout the entire process, copying may be unnecessary.

### 7.2. Partitioning the Work Region, One View Per Thread

If data is large and copying is undesirable, you can create non-overlapping views after establishing boundaries:

~~~java
ByteBuffer left  = source.slice(0, half);
ByteBuffer right = source.slice(half, source.limit() - half);
~~~

This is an illustrative snippet assuming `source` has been stably constructed and `0 ≤ half ≤ source.limit()`. Hand only `left` to worker A and `right` to worker B. If writes occur, every alias (including `source` or the backing array) must obey **disjoint ownership regions**. If data is read-only, add `asReadOnlyBuffer()` to catch accidental writes through a view.

Understand that creating views does not automatically lock the data region. If another component still holds write access to the whole original array, partitioning between two workers is not enough.

### 7.3. Ownership Handoff Instead of Simultaneous Sharing

A producer/consumer pipeline typically operates as follows:

1. The producer holds exclusive permission to write into the buffer, finishes writing, and calls `flip()`.
2. The producer **hands off** the buffer through a synchronization mechanism such as `BlockingQueue.put(buffer)`.
3. The consumer calls `take()` and is the sole component reading/advancing `position` during that stage.
4. The consumer signals completion or returns the buffer to a pool under a clear protocol; **only then** may the producer/pool call `clear()` and reuse it.

`BlockingQueue` provides memory-consistency guarantees: actions before placing an object into the queue *happen-before* actions after another thread takes the object out. That provides **safe publication**, yet the queue **does not automatically revoke the producer's access**. If the producer keeps mutating the buffer after `put`, shared-access bugs still happen.

In async I/O systems, wait for the operation to complete before reusing a buffer. Never `clear()`/`compact()` a buffer while an asynchronous read/write operation is still using that region.

### 7.4. Synchronizing All Operations on a Shared Buffer

If you truly need to share **the same cursor**, use a lock covering a sufficiently large unit of work. For example, the method below retrieves the next byte safely **provided all code accessing/mutating the same buffer obeys this lock**:

~~~java
static byte takeNext(ByteBuffer shared) {
    synchronized (shared) {
        if (!shared.hasRemaining()) {
            throw new java.nio.BufferUnderflowException();
        }
        return shared.get();
    }
}
~~~

This is an **illustrative method**, not a standalone program. `hasRemaining()` and `get()` sit inside the same critical section, so no thread obeying that monitor can interleave and alter `position` between the check and the read.

However, this lock only helps when **every relevant access path** (`put`, `get`, `position`, `limit`, `flip`, `clear`, `compact`, and backing-array access if any) follows the same protocol. Locking only the read helper while letting a writer call `shared.put(...)` outside the lock breaks the guarantee. Furthermore, locking per byte may be insufficient for a domain operation spanning multiple bytes that must stay consistent as one record; in that case, lock the entire record/batch or use a different design.

`ReentrantLock` or another locking mechanism can fit when timeouts, fairness, or condition waits are needed. What matters is **lock scope**, not the primitive's name.

### 7.5. Immutable Data and Concurrent Reads

For data created once and never modified afterward, multiple workers can read concurrently **through independent views**, provided:

- All bytes are finalized before publishing to workers; no writer or writable alias can mutate the data during reads.
- Safe publication is guaranteed (e.g., `Thread.start()`, passing through `BlockingQueue`, or an appropriate synchronization construct).
- Each thread keeps its own cursor (`duplicate`, `slice`, or absolute indices with an immutable limit).

Never label `ByteBuffer.asReadOnlyBuffer()` as "immutable" while a writable alias to backing storage still exists. For strong immutability guarantees, copy data into a managed object and guard all aliases, or expose a read-only API whose actual contents cannot be modified.

## 8. Common Mistakes in NIO Applications

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Two threads both calling `get()` on the same object | Contention over `position`, lost read partitioning | Give separate views, transfer ownership, or synchronize |
| Two threads both calling `put()` on the same object | Contention over write position and data | Separate regions, locks, or producer/consumer architecture |
| One thread calling `flip()` while another still calls `put()` | Changes `limit`/`position` before data is complete | Finish writing, then hand off the buffer via synchronization |
| Using `duplicate()` assuming bytes were copied | Both views still share backing storage | Copy explicitly if independent memory is needed |
| Using `asReadOnlyBuffer()` assuming data cannot change | Another alias can still write | Control all aliases and write permissions |
| Using absolute `get(index)` and concluding all operations are thread-safe | Data/`limit` contention and lack of atomicity remain | Establish data immutability or use locking |
| Sharing `ByteBuffer.wrap(array)` across threads while mutating `array` externally | Readers see unsynchronized changes | Stop mutating the array or copy it |
| Using `volatile ByteBuffer buffer` thinking `position/get/put` are synchronized | A volatile reference does not synchronize internal mutable state | Use proper ownership/locking protocols |
| Taking a buffer from a pool and reusing it before consumer/async I/O finishes | Old bytes overwritten, cursor/limit corrupted mid-task | Return to pool only after completion confirmation |
| Calling `clear()` to "wipe all data" | Old data remains in backing storage | To erase sensitive data, overwrite the region per security requirements |

**Note on runtime errors:** a race can trigger `BufferUnderflowException`, `BufferOverflowException`, or `InvalidMarkException`, yet it can also produce **wrong results without throwing any exception**. Running 1,000 times without error does not prove a program is thread-safe; failures depend on execution timing and memory access ordering.

## 9. Consequences for SocketChannel, FileChannel, and Pipelines

An NIO application often passes `ByteBuffer` as input/output to channels. Keep the two objects and their contracts separate:

- A channel may have its own per-implementation/method concurrency guarantees, yet **those guarantees do not automatically cover the cursor of a buffer passed in concurrently by multiple threads**.
- When calling `channel.read(buffer)`, the channel **writes bytes into the buffer and updates `position`**; `channel.write(buffer)` **reads bytes from the buffer and updates `position`**. If another thread concurrently alters `position`/`limit` or contents, sent/received data can be corrupted.
- A non-blocking `SocketChannel` can read/write partially: the buffer must retain its exact `position` so the remaining portion can be processed next. Never let another worker `rewind()`/`clear()` between partial-write retries.
- In a packet-processing pipeline, each connection or task can own its own buffer; if passing a buffer between an event loop and a worker, establish an explicit ownership-handoff protocol.
- When using a buffer pool, return to the pool only after channel/consumer work completes; retaining a view elsewhere while returning backing storage too early remains dangerous.

Example of a common send cycle:

~~~java
buffer.flip();
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
buffer.clear();
~~~

This is **illustrative code for a channel in blocking mode**, assuming `buffer` already holds data and `channel` is ready, open, and writable. With a non-blocking channel, `write` can return 0; register write-readiness or use an appropriate retry mechanism instead of busy-spinning in the loop above. In either case, the current thread must retain exclusive control over the buffer throughout the cycle, or synchronize appropriately.

## 10. Visibility and Happens-Before

The Java Memory Model defines when writes in one thread become properly visible to another thread. If one thread writes bytes and another thread reads the same backing storage without a suitable *happens-before* relationship, the code has no guarantee of visibility or operation ordering.

Several mechanisms establish this relationship:

- `Thread.start()`: actions in the spawning thread before `start()` happen-before actions in the newly started thread.
- `Thread.join()`: when thread A terminates and thread B completes joining A, A's actions happen-before B's subsequent actions.
- Monitor release/acquire on the same monitor via `synchronized`.
- Properly paired element handoffs through `BlockingQueue`.
- Memory-consistency contracts of other synchronization utilities in `java.util.concurrent`.

**Happens-before does not mean permission to mutate concurrently.** Passing a buffer through a queue properly establishes visibility for data written before handoff, yet if producer and consumer both keep writing to the same bytes simultaneously, a design bug still exists. Combine memory visibility with ownership and concurrency coordination.

## 11. How to Make Design Decisions

| Need | Usually Reasonable Choice | Limitation to Remember |
| --- | --- | --- |
| Each thread processes its own data | Dedicated allocated buffer or copy | Copy/allocation overhead |
| Multiple threads read an immutable dataset | Independent views, no remaining writers, safe publication | A read-only view does not itself freeze backing data |
| Splitting large data across workers | `slice(index, length)` over non-overlapping regions | External aliases must respect region boundaries |
| Producer writes, consumer reads in turns | Blocking queue or exclusive handoff mechanism | Do not reuse buffer before acknowledgement |
| Multiple consumers fetch the next byte from one cursor | Synchronize around `hasRemaining/get` or design an explicit queue | Lock must cover all related reads/mutations |
| Multiple writers update the same byte region | Lock or partition memory ownership; consistent protocol | Positional access is not a transaction |
| Multiple threads pass buffers to I/O channels | Prefer one buffer per task or one owner at a time | Channel thread safety does not replace Buffer thread safety |

You do not need locks on every buffer in a program. When only one thread uses a buffer at a time, **simple ownership** is usually easier to reason about and verify. Only introduce locks or coordination when mutable state/data is genuinely shared.

## 12. Self-Check Questions

1. Two threads only call `ByteBuffer.get()` (never `put`)—is this considered contention-free read-only access? **No.** Relative `get()` mutates the shared `position`.
2. Two threads receive `duplicate()` of the same buffer—can they change `position` independently? **Yes.** Yet backing-storage bytes are still shared; do not let two writers overwrite without synchronization.
3. Can you use `asReadOnlyBuffer()` and let another thread write to the original buffer concurrently and assume automatic safety? **No.** Only writes via the view are blocked; contents can still be mutated by another alias.
4. Does `ByteBuffer.get(index)` change `position`? **No.** Yet this operation alone does not guarantee safety when a writer or `limit` changes concurrently.
5. Once a producer puts a buffer into a `BlockingQueue`, can the producer immediately call `clear()`? **No**, unless another protocol confirms the consumer is done and returns ownership.
6. Does using `allocateDirect()` automatically synchronize multi-threaded access? **No**; direct/heap is a storage property, not a thread-safety contract.
7. Why can multiple threads calling `channel.write(sharedBuffer)` fail even if the channel has internal synchronization? Because reading from the buffer mutates `position`, and threads can also modify the buffer outside the channel's synchronization scope.
8. Is writing `synchronized(shared) { shared.get(); }` in one place enough? **Not necessarily**; every related access path must follow the same protocol and the critical section must span all operations needed for consistency.

## References

- [Java SE 17 — Buffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): `position`, `limit`, `mark`, state operations, and thread safety.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): relative/absolute access, `slice`, `duplicate`, `asReadOnlyBuffer`.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): execution ordering and memory consistency.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): producer/consumer handoff and memory consistency.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): interaction between channels and buffers.
