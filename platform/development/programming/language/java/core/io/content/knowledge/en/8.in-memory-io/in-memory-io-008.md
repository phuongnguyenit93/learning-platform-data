# PipedReader, PipedWriter, and Deadlock Risks When Used Improperly

> **Context:** Core Java → In-Memory I/O. This lesson explains a pair of character streams connecting two tasks within the same JVM, why reads/writes can block, scenarios that create deadlocks when misused, and how to organize a producer–consumer setup with clear termination, resource cleanup, and error reporting. These classes have been in `java.io` since Java 1.1; the standalone example below targets Java 17.

## 1. Nature of a Character Pipe

`PipedWriter` is the character **write end**; `PipedReader` is the **read end**. Once both ends are connected into a pipe, `char`s written to the writer are pulled sequentially from the reader. The pipe contains a **bounded buffer** so both sides can run at different speeds within that buffer capacity. It is typically used for producer–consumer communication **between threads in the same JVM**. It is not a socket, not a file on disk, and not an inter-process communication mechanism.

~~~text
PRODUCER thread                       CONSUMER thread
       |                                     ^
       | PipedWriter.write(...)              | PipedReader.read(...)
       v                                     |
       +-------------------------------------+
       |       bounded char buffer           |
       +-------------------------------------+
          empty → read must wait for data
          full  → write must wait for space
          writer.close() → reader can reach EOF
~~~

The units transferred through the pipe are **UTF-16 code units** per `Reader`/`Writer`, not encoded bytes. For ordinary Vietnamese text whose characters sit in the BMP, one `char` usually represents one code point; for emojis outside the BMP, one code point takes **two `char`s** forming a surrogate pair. If you need to transfer **binary bytes**, use `PipedInputStream` and `PipedOutputStream` or another suitable mechanism.

### Comparison with StringReader/StringWriter and Queues

| Mechanism | Best Fit | Limitations |
| --- | --- | --- |
| `StringReader` / `CharArrayReader` | A string or array already in memory, read locally | Does not create a live streaming link to a producing writer thread. |
| `StringWriter` / `CharArrayWriter` | Accumulating character output in a growing buffer to read later | Can hold the entire content in RAM; provides no producer–consumer blocking. |
| `PipedReader` + `PipedWriter` | One producer emits characters incrementally and a consumer reads via `Reader` | Bounded pipe; can block and deadlock without a matching thread. |
| `BlockingQueue<String>` | Producer–consumer passing discrete **messages** with clear boundaries | Must choose capacity, termination protocol, and error handling manually; not a Reader/Writer. |
| `PipedInputStream` + `PipedOutputStream` | Connecting a sender and receiver of **bytes** | Does not decode charsets automatically; also typically requires two threads. |

**Pick the right abstraction:** If a parser only accepts a `Reader` and data is produced incrementally by another task, a character pipe can work. If communication is an event queue or discrete messages, a bounded queue with an explicit shutdown mechanism is usually simpler. If you only need to pass an already-built `String`, a pipe adds unnecessary complexity.

## 2. Creating a Pipe Pair and Connecting Exactly Once

There are two valid patterns.

**Connect immediately via constructor:**

~~~java
// Fragment placed inside a method that can throw IOException.
PipedReader reader = new PipedReader(1024);
PipedWriter writer = new PipedWriter(reader);
~~~

**Or instantiate separately and connect:**

~~~java
// Fragment placed inside a method that can throw IOException.
PipedReader reader = new PipedReader();
PipedWriter writer = new PipedWriter();
writer.connect(reader);       // Equivalent to reader.connect(writer).
~~~

These are **fragments**; compiling them requires importing `java.io.PipedReader` and `java.io.PipedWriter` and declaring/catching `IOException` where the connection occurs. Both patterns mean the same thing: writer and reader form a one-way communication pair.

- An **unconnected** reader/writer cannot perform normal read/write operations and can throw `IOException` when used.
- Calling `connect` a second time after the pair is already connected (or trying to connect one end to another object) throws `IOException`. Do **not** reconnect ends as a kind of "reset."
- `new PipedReader(int pipeSize)` specifies the buffer size in **number of `char`s**, requiring `pipeSize > 0`; zero or negative values throw `IllegalArgumentException`. The buffer-size overload has existed since Java 6.
- `new PipedReader(writer, pipeSize)` creates a reader with the chosen buffer size and connects it to an unconnected writer. `new PipedWriter(reader)` is the straightforward way to attach to an existing reader.
- The default buffer in OpenJDK is typically 1,024 `char`s, but **never rely on a default size to claim your program cannot deadlock**. Every buffer is finite, and a producer can always outpace a consumer.

### 2.1. Key States

~~~text
UNCONNECTED
   └── connect once ──> CONNECTED
                           |       |
                           |       └── reader.close() → read side can no longer be used
                           └── writer.close() → write side ends,
                                                reader drains buffer then hits EOF
~~~

This is a conceptual model, **not** an exhaustive formal state machine of the implementation. Closing the writer signals no more data; closing the reader stops consumption. Never treat a closed end as reconnectable or reusable for a new session.

## 3. Blocking and Backpressure: The Primary Cause of Stalls

A pipe has a finite buffer. Two fundamental rules apply:

1. `PipedReader.read()` can **block** until at least one character arrives, EOF is detected, or an error occurs. Once the writer closes normally and the buffer is drained, `read()` returns `-1`.
2. `PipedWriter.write(...)` can **block** if the buffer is full and must wait for the consumer to read some characters. With `write(char[], off, len)`, the call must write all requested characters or throw an error; a long write may wait through several cycles.

That is **backpressure**: a fast producer is throttled by the consumer's ability to drain data. It helps avoid buffering entire payloads in memory, yet it requires producer and consumer to make progress **independently**.

Suppose the buffer holds 4 `char`s:

~~~text
Producer writes 'A','B','C','D' → [ A B C D ] (full)
Producer tries to write 'E'     → WAITS until consumer reads some
Consumer reads 'A','B'          → [ C D _ _ ]
Producer now has space to write → makes progress
~~~

If the consumer **is not running yet** or is waiting on something only the producer can complete, waiting becomes infinite. If the producer **never writes and never closes** while the consumer keeps reading, the consumer waits forever. Adding `Thread.sleep(...)` does not fix this dependency cycle.

## 4. Three Common Deadlock / Stall Patterns

### 4.1. Same Thread Calls read Before write

~~~java
// ANTI-PATTERN: DO NOT RUN as a program.
PipedReader reader = new PipedReader(4);
PipedWriter writer = new PipedWriter(reader);
int first = reader.read();       // May BLOCK because the pipe is empty.
writer.write('A');               // Never reached.
~~~

The thread stalls inside `reader.read()` waiting for a character that **it itself** intends to write on the next line. The Javadoc recommends operating the two pipe ends on two different threads; using both ends on the same thread can deadlock.

### 4.2. Same Thread Writes Past Capacity Before Reading

~~~java
// ANTI-PATTERN: DO NOT RUN as a program.
PipedReader reader = new PipedReader(4);
PipedWriter writer = new PipedWriter(reader);
writer.write("ABCDEFGHIJ");     // Longer than the 4-char capacity; may block.
char[] block = new char[10];
int n = reader.read(block);      // Never reached to free the buffer.
~~~

A single `write(String)` call may need multiple chunks to pass through the pipe. Once full, the writer waits for the reader to drain some characters, yet the reader sits after the write on the **same thread**. Writing less than capacity before reading **might** happen to run under certain conditions; that does not make a single-thread design safe for arbitrary input sizes.

### 4.3. Main Thread Joins Producer Before Reading

~~~java
// ANTI-PATTERN: DO NOT RUN if producer writes more than the buffer.
producer.start();
producer.join();                 // Main waits for producer to finish.
while (reader.read() != -1) { }  // Yet consumer only starts after join.
~~~

The producer is waiting for space in the buffer while `main` waits for the producer to exit; `main` cannot read because it is blocked on `join()`. This is a **circular wait dependency**. To run properly, **start the producer, consume concurrently, and only then join** once EOF is reached or resource cleanup runs. Even with **two threads**, placing `join` in the wrong order still hangs the program.

### Deadlock vs. Normal Blocking

A `read` waiting a few milliseconds for a producer to generate data is **valid blocking**, not a deadlock. Deadlock happens when tasks form a circular dependency where none can proceed. With pipes, an **indefinite wait** can also happen when one side stays alive without sending or closing, or when a processing thread stops without notifying the other side. Do not lump every wait into "deadlock"; check **who is waiting for what condition and who can satisfy it**.

## 5. Correct Standalone Example: Concurrent Producer and Consumer

Create **`PipeCharsDemo.java`**:

~~~java
import java.io.IOException;
import java.io.PipedReader;
import java.io.PipedWriter;
import java.util.concurrent.atomic.AtomicReference;

public class PipeCharsDemo {
    public static void main(String[] args) throws Exception {
        // Buffer holds only 4 chars; producer will send more than 4 chars.
        PipedReader reader = new PipedReader(4);
        PipedWriter writer = new PipedWriter(reader);
        AtomicReference<IOException> producerError = new AtomicReference<>();

        Thread producer = new Thread(() -> {
            try (writer) {
                writer.write("HELLO\nJAVA");
                // No need to use sleep() for coordination.
            } catch (IOException error) {
                producerError.set(error);
            }
            // try-with-resources closes writer as soon as producer finishes.
        }, "pipe-producer");

        producer.start(); // Producer gets a chance to write/wait on its own thread.

        StringBuilder received = new StringBuilder();
        try (reader) {
            char[] buffer = new char[3];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                received.append(buffer, 0, count);
            }
        }

        producer.join(); // Wait only after consuming up to EOF.
        if (producerError.get() != null) {
            throw producerError.get(); // Do not swallow producer error.
        }

        System.out.println("received="
                + received.toString().replace('\n', '|'));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 PipeCharsDemo.java
java PipeCharsDemo
~~~

**Stdout from a successful run:**

~~~text
received=HELLO|JAVA
~~~

This example uses fixed input; the exact scheduling order of producer and consumer is **non-deterministic**, yet the output preserves exact character order. This example was verified on the JDK using an equivalent Java runner.

Each piece serves a specific purpose:

1. `PipedReader(4)` intentionally uses a small buffer so the 10-character string cannot fit in the buffer all at once.
2. `new PipedWriter(reader)` creates **a single connection**.
3. `producer.start()` lets the writer thread run concurrently with `main` reading. When the producer blocks on a full buffer, it **does not block `main`** from draining.
4. `read(buffer)` returns the actual number of `char`s read; you must append `count` characters rather than the whole array, because the final read can be partial.
5. Exiting `try (writer)` calls `close()` on the write side, letting the reader observe **EOF** after draining buffered data.
6. `producer.join()` runs **after the read loop**, so `main` never waits for the producer while the producer still needs `main` to consume. `AtomicReference` ensures any `IOException` from the producer reaches `main` instead of vanishing on another thread.

**Scope of this demo:** This shows the happy path illustrating the producer–consumer relationship. If the consumer throws an exception before reading everything or is cancelled, production code needs a strategy to **close the read end, signal cancellation, stop the producer, and join with a timeout** so the writer thread is never stranded waiting on the buffer. The sections below cover those principles. Never use `Thread.stop()` for cleanup.

## 6. Why Must You Close the Writer for the Reader to See EOF?

Distinguish three states:

- **Empty buffer, writer still open:** the reader blocks waiting because the producer may still send more characters.
- **Buffer still holds characters, writer closed cleanly:** the reader still drains those remaining characters; once the buffer is empty, `read()` returns `-1`.
- **Reader closed:** the receiving end no longer consumes; a writer currently writing or about to write can throw `IOException`. Closing the reader is **not** the normal completion ritual for a finished stream.

Common mistake:

~~~java
// Producer finished writing but did not call close().
writer.write("done");
// Another reader still looping while ((n = reader.read(...)) != -1)
// will not necessarily see EOF; it keeps waiting for "more data".
~~~

**Practical rule:** in a model where one producer owns the writer, close the writer using `try-with-resources` or `finally` once truly finished. Never just call `flush()` and expect the reader to guess the stream has ended.

`PipedWriter.flush()` notifies waiting readers that data is present in the pipe; when wrapped by an outer `BufferedWriter`, `bufferedWriter.flush()` also pushes data from the wrapper's buffer down into the underlying writer. However, **flush is not an EOF signal** and does not close the writer. For long-lived character streams, define an explicit completion protocol or end-of-message marker where needed rather than "no data arrived for a bit so exit."

## 7. Is `flush()` Actually Needed?

From the API perspective:

- `PipedWriter` provides `flush()`, and its specification notes it wakes up waiting readers when characters are waiting in the pipe.
- An outer `BufferedWriter` maintains its **own** buffer; a `write` may still sit inside that buffer. When the consumer must receive data immediately while the writer stays open, calling `flush()` on the **BufferedWriter** pushes characters into the pipe.
- Calling `close()` on the writer/wrapper also completes the write lifecycle, typically flushing wrapper-buffered data and closing the target per that class's contract.
- `flush()` does not ensure the producer has read its entire input, does not free pipe capacity if the consumer is not reading, and does not fix a single-thread full-buffer deadlock.

Fragment example with external buffering:

~~~java
// Fragment: pipe is an already-connected PipedWriter.
try (java.io.BufferedWriter out =
        new java.io.BufferedWriter(pipe)) {
    out.write("part-1");
    out.flush(); // Push data from BufferedWriter down into the pipe.
    out.write("part-2");
} // Closes the wrapper, and normally closes the inner writer.
~~~

This fragment still requires a concurrent consumer. If no consumer is running, `flush` or `close` can block when the buffer fills; adding `flush()` is not a workaround for deadlock.

## 8. Dead Threads and the "Broken Pipe" Concept

`PipedReader.read()` can throw `IOException` when the pipe is **broken**, unconnected, closed, or encounters an I/O error. `PipedWriter.write(...)` can likewise report broken, unconnected, or closed pipe errors. Certain implementations detect that **the thread that previously performed read/write is no longer alive** and throw errors such as `"Read end dead"` or `"Write end dead"`.

However, **do not use dead-thread detection as your program's termination protocol**:

- A producer can exit **without closing the writer**, causing the consumer to block or fail depending on state; that must not be treated as clean EOF.
- A consumer stopping reads while the producer keeps writing can cause the producer to block on the buffer or fail; the caller must coordinate cancellation and cleanup.
- Error types and detection timing depend on state, scheduling, and implementation details; never assert exact exception message strings in tests.
- A thread that remains alive with no intention of writing more can still keep the consumer waiting forever; checking `isAlive()` alone does not prove progress.

Therefore, **close the writer on the success path**, and on failure **report the exception separately**, close endpoints, and manage task lifecycles deliberately. The consumer seeing EOF does not automatically prove the producer succeeded—also check `Future.get()`, `join()` + error channel, or application coordination state.

## 9. Do Not Swallow Producer Errors

Code running on another thread does not automatically propagate exceptions back to the thread that called `start()`. If the producer throws an exception while the consumer keeps waiting for more input, the reader can hang or fail with a broken-pipe error, hiding the **root cause**. In `PipeCharsDemo`, `AtomicReference<IOException>` captures the producer's error and checks it after `join()`. Broader designs can use:

- `ExecutorService.submit(...)` returning a `Future<?>`. `future.get()` confirms task completion and throws `ExecutionException` wrapping the cause—just never call `get()` **before** the consumer drains enough data if the producer might block on a full pipe.
- An explicit result/error reporting structure in the pipeline; even after the reader hits EOF, the caller checks whether the producer succeeded.
- Coordinated cancellation of all tasks when either reader or writer fails, closing endpoints properly and awaiting task shutdown with a sensible timeout.
- Bidirectional error propagation, not producer-only: a consumer `IOException` may also require signaling the producer to stop.

**Do not** promise that `Thread.interrupt()` always unblocks every blocked I/O operation immediately on every JDK or provider. Whenever cancellation is required, verify the specific API's interrupt behavior, pair it with endpoint closing and cleanup, enforce timeouts at the **task level**, and never leave threads waiting unboundedly.

## 10. Can You Read and Write on a Single Thread?

For small, known inputs that never fill the buffer, you **might observe** a single-thread program run to completion. Yet the Java API documentation explicitly warns that using both reader and writer of a pipe pair on the same thread **is not recommended** due to deadlock risk; succeeding on a short string does not make it safe for longer payloads, fluctuating speeds, or newline handling.

When working on a single thread with data already available:

- Choose `StringReader` to hand a parser a `Reader` once the string is built.
- Choose `CharArrayReader`/`CharArrayWriter` when you want data in `char[]` form.
- Use `StringWriter` to accumulate text and then `new StringReader(writer.toString())` if a `Reader` interface is truly required.
- For files that can be re-read, use `Files.newBufferedReader` or an appropriate file source.

Using a pipe merely to "turn a String into a Reader" on the same thread only invites stalls when `new StringReader(text)` already solves the task directly.

## 11. Bounded Buffers and Choosing `pipeSize`

`pipeSize` is the number of **UTF-16 code units** in the reader's buffer. When the producer can emit strings of unbounded length, no fixed buffer size guarantees the writer **will never wait**. The whole point of a bounded buffer is regulating pace between both sides.

Selection guidelines:

1. Start with a size fitting a few character chunks appropriate for your workload. Never inflate it to millions of characters just to mask a deadlock caused by broken thread coordination.
2. Measure throughput, producer wait time, and memory pressure with realistic data. Larger buffers can reduce waits during bursty traffic at the cost of RAM and more in-flight data.
3. `read(char[], off, len)` may return fewer than `len` characters; process only the **actual count returned** each iteration. Never assume a single read returns one full "message" or one line.
4. When data has message boundaries, define explicit framing such as a length prefix, escaped newlines, or an object queue; a pipe is a sequential character stream and does not preserve individual `write` call boundaries.
5. When small buffer sizes expose ordering problems where operations demand reverse order from the peer, the root issue is a **dependency cycle**, not the capacity number.

**Regarding Unicode:** an emoji outside the BMP consists of two UTF-16 code units; the pipe can split those two halves across separate `read(buffer)` calls. When displaying, parsing, or encoding to UTF-8, preserve character state across buffer boundaries rather than treating each read chunk as an independent complete string.

## 12. Do Not Confuse `ready()`, `read()`, and EOF

`PipedReader.ready()` reports whether the reader **currently has characters in its circular buffer** so the next read call will not block waiting for input at that moment. If it returns `false`, it **does not promise** the next `read` will block: the producer might write a character in the meantime.

~~~java
// Fragment: reader is connected and still open.
if (reader.ready()) {
    int ch = reader.read(); // Can retrieve a ready character.
}
// If ready() is false, DO NOT conclude the reader hit EOF.
~~~

Do not do this:

~~~java
// LOGICAL ANTI-PATTERN:
while (reader.ready()) {
    System.out.print((char) reader.read());
}
// Exits early when buffer is temporarily empty even if producer is about to write more.
~~~

The proper way to read the entire stream is:

~~~java
// Fragment: inside a method that can throw IOException.
char[] block = new char[1024];
int n;
while ((n = reader.read(block)) != -1) {
    process(block, n); // process is an application-defined method.
}
~~~

This is a **fragment**, not a standalone program, because `reader` and `process` are supplied by the caller. Looping to `-1` requires the writer to close cleanly in order to stop. `read(char[], off, 0)` may return 0, whereas for a positive length request the method attempts to read at least one `char` or returns `-1` per the API contract.

## 13. Both Ends of the Pipe and try-with-resources: Who Owns the Resources?

A pipe pair has **two lifecycles**: the producer owns the write end, and the consumer owns the read end. Splitting ownership this way keeps responsibilities clear.

| Situation | Producer / Writer | Consumer / Reader |
| --- | --- | --- |
| Normal execution | Writes chunks, closes writer when finished | Reads until `-1`, closes reader |
| Producer fails | Captures/reports error, still closes writer in `finally` / `try-with-resources` | May hit EOF after already-written data; coordinator checks producer error state |
| Consumer exits early | Receives stop signal via controller or detects closed reader | Closes reader and signals cancellation per policy |
| Program cancelled | Stops producing, closes write end and resolves blocked operations | Closes read end, joins task with a timeout |
| Writer closes before writing anything | Closes writer normally | Reader reaches EOF immediately |
| Writer fails to close after finishing | No more data, yet keeps pipe open | Reader may wait indefinitely |

A Java `try-with-resources` note: if you create both endpoints inside **the same try block** while writer or reader runs on another thread, the resource lifetime must span the entire period both threads actually use them. Never close the read end in `main` while the producer is still sending; and never let the producer leave the writer open after stopping.

### 13.1. Coordination Pattern with Timeouts and Cancellation

Production applications should have a coordinator that knows:

1. When to start producer and consumer and how many pipes are connected.
2. Which tasks are running and how errors arrive via `Future` or a result channel.
3. When to close the writer to mark completion, and when to close the reader because it is no longer needed.
4. When to stop waiting (`Future.get(timeout, unit)` or an equivalent task timeout).
5. On timeout, how to cancel tasks, close affected ends, log errors, and await shutdown—without assuming interrupt alone solves everything.

**Ordering warning:** `future.get()`/`thread.join()` itself can form the deadlock link if the caller is also responsible for draining data yet waits on the producer first. Ensure the consumer runs concurrently; if both producer and consumer are separate tasks, the controller can monitor both without acting as the consumer itself.

## 14. Why Does a Pipe Sometimes Throw `IOException` Instead of Waiting Forever?

The Javadoc states `PipedReader.read()` can throw `IOException` if the pipe is broken, unconnected, closed, or encounters an I/O error. The writer can throw `IOException` in analogous cases. An implementation may detect that the peer thread has died while the buffer is empty or the reader is no longer receiving.

This is **not a guaranteed mechanism for catching every concurrency failure** and never replaces `join`/`Future`/closing. Any program that relies on exception message strings like `"Pipe broken"`, `"Write end dead"`, or `"Read end dead"` to convey application results will be brittle across JVM versions and environments.

Always record the **root exception from the failing task** rather than looking only at the secondary pipe error on the other end. When a consumer fails to parse, do not keep the writer pushing indefinitely and log only a secondary `IOException`. When a producer fails, close the writer in `finally` and report the cause to the coordinator so it can distinguish "all data sent cleanly" from "EOF caused by a crashed task."

## 15. Common Mistakes

1. **Calling `read()` before `write()` on the same thread**: the read blocks waiting for data this very thread has not written yet.
2. **Writing a payload longer than `pipeSize` before starting reads on the same thread**: the producer fills the buffer and cannot free space itself.
3. **Calling `join()` on the producer before draining the pipe**: two threads still create a circular wait dependency.
4. **Forgetting `writer.close()`**: a consumer reading until EOF can block forever.
5. **Calling `flush()` thinking it sends EOF**: flush wakes/pushes data, yet the writer remains open.
6. **Using `ready() == false` to assume end of data**: it is only an instantaneous readiness snapshot.
7. **Writing without connecting or connecting twice**: violates the pipe contract and throws `IOException`.
8. **Setting a huge buffer to "fix deadlock"**: only hides the bug for the current payload size; real concurrency coordination is required.
9. **Doing one array read and assuming all n characters arrived**: always check the actual `char` count returned and EOF.
10. **Using character pipes to copy images or ZIPs**: binary data must flow through byte streams, not `Reader`/`Writer`.
11. **Letting producer exceptions vanish in a background thread**: the consumer only sees EOF/broken pipe/hang with no root cause.
12. **Assuming an interrupted thread immediately exits all I/O**: always combine cancellation with explicit resource closing.
13. **Arbitrarily sharing one pipe among multiple producers/consumers**: pipes are designed for one writer end and one reader end; multiple publishers require higher-level coordination or message passing.
14. **Closing the reader before the producer finishes without signaling cancellation**: the producer can throw an error or remain stuck mid-operation.
15. **Treating each `write` as an indivisible message**: `Reader` yields a flat character stream; `read` calls may split or coalesce writes depending on buffer state.

## 16. Self-Check Exercises

1. Why must `PipedReader` and `PipedWriter` normally run on two separate threads?
2. Can `new PipedReader(4)` process a total of 10,000 characters? What condition is required for it to succeed?
3. Describe the dependency cycle when `main` calls `producer.join()` before the `reader.read()` loop.
4. How do `writer.flush()` and `writer.close()` differ with respect to the consumer reaching EOF?
5. Is `reader.ready() == false` an indicator that the producer has finished?
6. If the producer writes a UTF-16 string containing an emoji outside the BMP, how many `char` units travel through the pipe for that emoji, and what assumption must the consumer avoid?
7. Why does an application still need a separate producer error-reporting channel even when the consumer reads `-1`?
8. If you just want to turn an existing `String` into a `Reader` for a parser on the same thread, should you pick `PipedReader` or `StringReader`?
9. A producer thread stays alive doing nothing and never closes the writer; can the reader block forever? Is every such indefinite wait a deadlock?
10. When you need to pass delimited messages from multiple producers, what other abstraction should you consider?

**Guided answers:**

1. Because blocking when the pipe is empty or full requires the opposite side to be running in order to produce data or free buffer capacity.
2. **Yes**; the buffer holds only a slice at any moment; the consumer must read concurrently and the writer must close when done.
3. The producer waits for the consumer to read and free space, while `main` waits for the producer to exit, so the consumer never runs.
4. `flush` helps push/notify pending data; **`close`** finishes the write side and lets the reader receive EOF after draining the buffer.
5. **No**; it is merely a snapshot of buffer state at the instant checked.
6. Usually **two `char`s** for a supplementary code point; never assume a single `read` or single `char` equals a complete Unicode character.
7. EOF signals the end of the byte/char stream; it does not confirm the producer generated complete data or exited without errors.
8. `StringReader`, which is direct and simple.
9. **Yes**, it can wait indefinitely; not every long wait forms a circular deadlock dependency.
10. A `BlockingQueue` with capacity and a shutdown protocol, or an appropriate messaging/concurrency API.

## 17. Authoritative References

- [Oracle Java SE 21 – PipedReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PipedReader.html): connecting, `pipeSize`, blocking reads, `ready()`, EOF, and errors.
- [Oracle Java SE 21 – PipedWriter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PipedWriter.html): connecting, blocking writes, `flush()`, and `close()`.
- [Oracle Java SE 21 – Reader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Reader.html): character-stream I/O contract and `read(char[],off,len)`.
- [Oracle Java SE 21 – PipedInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PipedInputStream.html) and [PipedOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PipedOutputStream.html): byte-level counterparts.
- [Oracle Java SE 21 – BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html): alternative for message-based producer–consumer pipelines with capacity policies.

**Key takeaway:** A character pipe is a bounded buffer linking a writer and a reader. Reading when empty and writing when full both block; therefore producer and consumer must run concurrently, **close the writer to emit EOF**, propagate thread errors explicitly, and place `join()/get()` only after letting the consumer make progress.
