# `PipedInputStream`, `PipedOutputStream`, and Inter-Thread Communication in Java

`PipedInputStream` and `PipedOutputStream` in `java.io` form a **one-way byte pipe** between two units of work within the **same JVM**. One thread can write bytes to the output end while another thread reads those bytes from the input end. Unlike `ByteArrayInputStream`/`ByteArrayOutputStream`, which store already-available data in memory, a pipe has a **bounded buffer and blocking behavior**: if no data is available yet, the reader can block waiting; if the buffer is full, the writer can block waiting for the reader to consume bytes.

The most important rules are to **connect both ends properly, run writer and reader concurrently, close the write end when finished, and handle errors on both sides**. A pipe transfers an ordered **byte stream**; it creates no "message" boundaries on its own and does not make `read()` asynchronous.

## 1. What Role Does Each Class Play?

- `PipedOutputStream`: the **write** end. The producer calls `write(int)` or `write(byte[], off, len)` to push bytes into the pipe.
- `PipedInputStream`: the **read** end. The consumer calls `read()` or `read(byte[])` to retrieve bytes in the exact order written.
- **Connection**: an input end and an output end are linked via a constructor or `connect(...)`. An already-connected end must not be connected again.
- **Lifecycle**: once the producer closes the output end after finishing writes, the consumer can drain any bytes left in the buffer and then receive `-1` (EOF). Conversely, closing the input end prematurely can cause the producer's write calls to fail.
- **Buffer**: the buffer lives inside the in-memory pipe mechanism, not in a file or network socket. `PipedInputStream(int pipeSize)` lets you specify the buffer size with a positive byte count.

Diagram:

```text
Producer thread                         Consumer thread
      |                                       ^
      | write(bytes)                          | read(bytes)
      v                                       |
PipedOutputStream ---- connected ----> PipedInputStream
                                    [bounded byte buffer]
```

This is a **unidirectional** mechanism: data flows from output to input. If an application needs bidirectional communication, it needs two opposite-direction pipes or a more suitable communication mechanism.

### Valid Construction / Connection Patterns

```java
// Option 1: Create input first, pass it to output's constructor.
PipedInputStream input = new PipedInputStream();
PipedOutputStream output = new PipedOutputStream(input);

// Option 2: Create output first, pass it to input's constructor.
PipedOutputStream output2 = new PipedOutputStream();
PipedInputStream input2 = new PipedInputStream(output2);

// Option 3: Create both ends separately, then connect once.
PipedInputStream input3 = new PipedInputStream(4096);
PipedOutputStream output3 = new PipedOutputStream();
output3.connect(input3);
```

These snippets are **illustrative**, requiring `import java.io.PipedInputStream; import java.io.PipedOutputStream;` inside a method handling `IOException`. Pick **one** approach per input/output pair, not all three for the same pipe. `connect()` can throw `IOException` if either end is already connected, closed, or invalid; reading or writing before connecting can also fail.

`PipedInputStream` defaults to a bounded buffer; do not rely on a specific default capacity when designing logic. Whenever buffer capacity matters, explicitly pass a positive `pipeSize` and treat it as the limit of the **byte buffer**, not the maximum length of the entire data stream.

## 2. Complete Example: One Thread Writes, Another Thread Reads

The example below uses a thread from an `ExecutorService` as the producer and the `main` thread as the consumer. The pipe buffer is only **4 bytes** to demonstrate that both sides must make progress concurrently. The producer writes the entire UTF-8 payload and closes the output; the consumer reads until EOF and decodes the bytes at the end.

```java
// PipeHelloDemo.java
import java.io.ByteArrayOutputStream;
import java.io.PipedInputStream;
import java.io.PipedOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class PipeHelloDemo {
    public static void main(String[] args) throws Exception {
        PipedInputStream input = new PipedInputStream(4);
        PipedOutputStream output = new PipedOutputStream(input);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> producer = executor.submit(() -> {
                try (PipedOutputStream writer = output) {
                    writer.write("Xin chào, pipe!"
                            .getBytes(StandardCharsets.UTF_8));
                }
                return null;
            });

            try (PipedInputStream reader = input) {
                ByteArrayOutputStream received = new ByteArrayOutputStream();
                byte[] buffer = new byte[3];
                int count;

                while ((count = reader.read(buffer)) != -1) {
                    received.write(buffer, 0, count);
                }

                producer.get(); // Propagate any producer exception to main.
                System.out.println("text="
                        + received.toString(StandardCharsets.UTF_8));
                System.out.println("bytes=" + received.size());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Compile and run with **Java 17+**:

```bash
javac -encoding UTF-8 PipeHelloDemo.java
java PipeHelloDemo
```

Output:

```text
text=Xin chào, pipe!
bytes=16
```

Explanation:

1. `PipedOutputStream(input)` connects the output end to the input end.
2. `executor.submit(...)` runs the write task on a separate thread. `main` does not wait for the producer to finish before starting to read.
3. Because the buffer is only 4 bytes while the UTF-8 payload is 16 bytes, the producer must wait for the consumer to free space as needed.
4. `reader.read(buffer)` returns the **actual number of bytes received**; the loop writes only `count` valid bytes into `ByteArrayOutputStream`.
5. The producer closes `writer`, signaling end of data. The consumer receives `-1` after reading all remaining bytes in the pipe.
6. `producer.get()` waits for task completion and surfaces any exception from the producer (wrapped by `Future`), instead of silently ignoring worker failures.
7. UTF-8 includes the multi-byte character `à`; collecting all bytes before decoding avoids accidentally splitting a multi-byte character across `read()` boundaries.

**Do not call `producer.get()` before the read loop** in this example: if the producer writes more than the pipe's capacity, it blocks waiting for the consumer to read; if `main` simultaneously waits for the producer to finish before reading, the program can **deadlock**.

Note that in production code, if the consumer fails early, close the input to release resources and cancel/handle the producer, and enforce timeouts where appropriate. This example focuses on the happy path and producer error propagation.

## 3. Blocking, Backpressure, and Byte Ordering

Both ends of the pipe communicate through a fixed-capacity buffer:

| Situation | Reader Side | Writer Side |
| --- | --- | --- |
| No bytes yet and write end still open | `read()` may **block** waiting for data | Can write bytes into the buffer while space remains |
| Buffer currently contains bytes | `read()` returns one or more bytes | Continues writing while space remains |
| Buffer is full | Consumer reads free up buffer space | `write()` may **block** until space becomes available |
| Write end closed after finishing writes | Reads remaining buffered bytes, then `read()` returns `-1` | Cannot write further to a closed output |
| Read end closed while producer still writes | Cannot continue reading | Write calls may throw `IOException` |

Having the writer naturally wait when the buffer fills up is called **backpressure**: the producer's pace is throttled by the consumer's ability to drain data. That is a useful property for a byte stream, yet also the reason you must never misuse a pipe inside sequential tasks running on the same thread.

### Complete Example: Observing Blocked Writes When the Buffer Fills

To avoid relying on `sleep()` or timing luck, this program creates a **2-byte** pipe and has the producer write **3 bytes**. Before `main` reads a single byte, writing all three bytes cannot complete. Once `main` reads one byte, the producer gets room to write the third byte and finishes.

```java
// PipeBackpressureDemo.java
import java.io.PipedInputStream;
import java.io.PipedOutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class PipeBackpressureDemo {
    public static void main(String[] args) throws Exception {
        PipedInputStream input = new PipedInputStream(2);
        PipedOutputStream output = new PipedOutputStream(input);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> writeTask = executor.submit(() -> {
                try (PipedOutputStream writer = output) {
                    writer.write(new byte[] {10, 20, 30});
                }
                return null;
            });

            try (PipedInputStream reader = input) {
                System.out.println("doneBeforeRead=" + writeTask.isDone());
                System.out.println("first=" + reader.read());

                writeTask.get();
                System.out.println("doneAfterRead=" + writeTask.isDone());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac PipeBackpressureDemo.java
java PipeBackpressureDemo
```

Expected output when producer and consumer work properly:

```text
doneBeforeRead=false
first=10
doneAfterRead=true
```

With capacity 2, the producer cannot finish writing all three bytes **before a read frees at least one slot**, so `writeTask.isDone()` starts out `false` (either blocked or not yet scheduled). After `reader.read()` retrieves the first byte `10`, the write can complete; `writeTask.get()` waits precisely until the producer finishes. This illustrates a **buffer condition**, not a timing benchmark.

If written like this on a single thread:

```java
// DESIGN BUG: illustrative only, do not run as written.
PipedInputStream input = new PipedInputStream(2);
PipedOutputStream output = new PipedOutputStream(input);
output.write(new byte[] {10, 20, 30}); // May block indefinitely.
int first = input.read();               // May never be reached.
```

The thread trying to write more than the buffer capacity blocks waiting for a consumer, yet the consumer sits on the **next** line in that very same thread. That is a classic deadlock trap.

### `read()` Does Not Guarantee Returning a Full "Message"

A pipe is a **byte stream**, so a single `read(byte[])` call can return fewer bytes than requested. The consumer's buffer size, how the producer splits `write` calls, and thread scheduling **do not act as record boundaries**. Even if the producer calls `write(message)` once, the consumer may still receive the message across multiple `read` calls.

Therefore, never equate "one `read` = one message." To exchange messages, the application must define a framing protocol—such as a length prefix, escaped delimiters, or a higher-level codec.

## 4. Closing the Write End, EOF, and Both Sides' Lifecycles

An essential relationship:

```text
Producer writes data ---> Producer closes output
       |                        |
       v                        v
Consumer drains buffer ---> read() == -1 (EOF)
```

When the writer **closes cleanly**, any bytes already written are still drained by the consumer before hitting EOF. Calling `read()` on the input end does not automatically return `-1` merely because data is temporarily absent; while the write end remains open and no bytes are buffered, `read()` blocks waiting.

Closing the **read end** is not the same as closing the **write end**:

- Closing `PipedOutputStream` is how the producer announces "no more bytes are coming" along the stream and lets the consumer terminate with EOF after draining buffered bytes.
- Closing `PipedInputStream` while the producer is still writing can cause the producer to receive an `IOException` on write. Never use it as a "normal signal" that the producer is finished.
- If a worker crashes or exits **without properly closing its pipe end**, errors like "broken pipe" / "write end dead" / "read end dead" can occur depending on state and implementation. Do not rely on specific exception message text in place of a completion protocol.
- `flush()` does not replace `close()` as an end-of-stream signal. In particular, `flush()` emits no EOF marker.

### Resource Ownership When Using Wrappers

You can wrap the pipe with other stream classes:

```java
// Illustrative wrapper pair for reading/writing binary data.
DataInputStream reader = new DataInputStream(pipedInput);
DataOutputStream writer = new DataOutputStream(pipedOutput);
```

This snippet assumes `pipedInput` and `pipedOutput` are already connected and imports are present. When each thread **owns** one end of the pipe, use `try-with-resources` on the **outermost wrapper** of that end. `DataOutputStream.close()` closes the underlying output end; `DataInputStream.close()` closes the underlying input end. Never close the raw pipe end currently used by the other thread before it is finished.

If you wrap the output with `BufferedOutputStream`/`BufferedWriter`, data may remain in the buffer **outside** the pipe; call `flush()` whenever messages must become visible to the consumer right away, or `close()` when finished. Avoid deadlocking where the reader waits for data in the pipe while the writer waits for the reader while the bytes are still sitting in the writer's buffer.

## 5. Pipes Transfer Bytes Only: Framing Is Needed for Message Passing

Suppose the producer wants to send two strings `"A"` and `"Xin chào"`. If you simply write UTF-8 bytes back-to-back, the consumer cannot tell where the first string ends. A clean protocol sends:

1. A 4-byte `int` (`writeInt`) representing the **byte** length of the payload.
2. Exactly that many payload bytes.
3. Repeat for the next message.
4. Send a `-1` length sentinel to end this example protocol, then close the output.

The consumer uses `readInt()` to read the size, validates its bounds, and calls `readFully()` to receive the **exact** number of bytes. `readFully()` loops across multiple reads if needed and throws `EOFException` if the stream closes prematurely; never mistake a short read for a complete message.

```java
// PipeMessagesDemo.java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.PipedInputStream;
import java.io.PipedOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class PipeMessagesDemo {
    private static void send(DataOutputStream writer, String text)
            throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        writer.writeInt(payload.length);
        writer.write(payload);
    }

    public static void main(String[] args) throws Exception {
        PipedInputStream input = new PipedInputStream(8);
        PipedOutputStream output = new PipedOutputStream(input);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> producer = executor.submit(() -> {
                try (DataOutputStream writer = new DataOutputStream(output)) {
                    send(writer, "A");
                    send(writer, "Xin chào");
                    writer.writeInt(-1);
                }
                return null;
            });

            try (DataInputStream reader = new DataInputStream(input)) {
                int messages = 0;

                while (true) {
                    int length = reader.readInt();

                    if (length == -1) {
                        break;
                    }
                    if (length < 0 || length > 1024) {
                        throw new IOException("Invalid message length");
                    }

                    byte[] payload = new byte[length];
                    reader.readFully(payload);
                    System.out.println("message="
                            + new String(payload, StandardCharsets.UTF_8));
                    messages++;
                }

                producer.get();
                System.out.println("count=" + messages);
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 PipeMessagesDemo.java
java PipeMessagesDemo
```

Output:

```text
message=A
message=Xin chào
count=2
```

This is an **application-defined example protocol**, not a built-in format of `PipedInputStream`/`PipedOutputStream`. The `-1` sentinel works solely because both ends agreed on it beforehand; `readInt()` does **not** treat `-1` as pipe EOF. If the producer closes before sending a full header or payload, the consumer receives `EOFException`; that is an incomplete-message error, distinct from a normal sentinel.

Validate `length` before allocating the array to prevent a buggy or malicious sender from specifying a huge size and exhausting memory. In real systems, also add rules for versioning, checksums, timeouts, malformed payloads, and application limits.

Newline-delimited framing can substitute when **content is guaranteed not to contain unescaped newlines**, or you can use `InputStreamReader`/`BufferedReader` for text protocols. When content involves complex delimiters or escaping, a proper grammar parser is needed; the pipe itself remains purely a byte transport.

## 6. Bytes, Characters, and UTF-8: Avoid Decoding Arbitrary Chunks

`PipedInputStream`/`PipedOutputStream` **have no knowledge of Unicode**. UTF-8 encodes characters into 1–4 bytes, so a single `read(buffer)` can stop **in the middle** of a character's bytes.

Do not do this:

```java
// WRONG EXAMPLE CODE: may decode a UTF-8 chunk cut mid-character.
byte[] buffer = new byte[2];
int n;
while ((n = input.read(buffer)) != -1) {
    System.out.print(new String(buffer, 0, n, StandardCharsets.UTF_8));
}
```

This snippet assumes `input` is an open stream. `new String(...)` on each chunk creates a **fresh decoder**; if a multi-byte character gets split, the output can turn into replacement characters `` instead of the original text.

Choose one of two correct approaches depending on your needs:

- **Byte layer:** retain raw payload bytes until the full message arrives (as `readFully` does above), then decode *the entire payload* as UTF-8.
- **Character layer:** wrap `PipedInputStream` once in `InputStreamReader(input, StandardCharsets.UTF_8)`, optionally wrapped in `BufferedReader`. The decoder then preserves state across multiple reads. To write characters on the producer side, wrap `PipedOutputStream` in `OutputStreamWriter(output, StandardCharsets.UTF_8)`.

Using `Reader`/`Writer` still creates no message boundaries. You still need application-level delimiters or framing, plus `flush()` where buffered writers are used.

## 7. Common Errors, Thread Interrupts, and Deadlock Diagnosis

### 7.1. Writing Before Reading on the Same Thread

If the producer writes beyond buffer capacity with no consumer running, `write()` can block forever. **Fix:** run producer and consumer concurrently; never call `join()` or `Future.get()` on the producer **before** the consumer begins reading whenever the producer might block on a full buffer.

### 7.2. Forgetting to Close the Output End

If the producer sends the last byte yet leaves the output end open, the consumer keeps blocking on the next `read()`. Never use `available() == 0` to conclude input is finished: `available()` only reports bytes readable without blocking right now and **does not prove EOF**. **Fix:** design a clean shutdown path, close the writer in `finally`/`try-with-resources`, or define an explicit end-of-message protocol.

### 7.3. Closing the Input End Prematurely

If the consumer hits an error or exits early while the writer is sending, the writer can fail with `IOException`. **Fix:** define a clear cancellation policy, close the appropriate ends to wake up blocked tasks on error, and propagate errors from both sides back to the coordinator. Never ignore `Future.get()` in production code when producer errors matter.

### 7.4. Unconnected or Double-Connected Pipe Ends

Reading or writing on an unconnected end throws `IOException` (exact message varies by environment). Connecting already-connected ends is also invalid. **Fix:** wire the input/output pair **once** before starting threads and hand each end to its worker.

### 7.5. Abnormal Thread Termination

Java pipes check reader/writer thread liveness in certain situations; when the remote thread terminates improperly, a broken/dead pipe `IOException` may be thrown. **Do not** treat dead-thread detection as a reliable business-level end-of-stream signal. Close cleanly, propagate exceptions via `Future`/coordination logic, and define a clear protocol.

### 7.6. Interrupts and Task Cancellation

Blocking pipe operations can react to thread interrupts with `InterruptedIOException` or related API/implementation errors. In cancellable programs, explicitly design task interruption, close the pipe to unblock waiting threads, and never swallow interrupt flags/exceptions. `Future.cancel(true)` only sends an interrupt request if the worker is running; do not assume it frees all resources or guarantees instant exit.

### 7.7. Multiple Producers or Consumers Sharing One Pipe

Pipes target thread-to-thread communication, typically **one writer and one reader** per pair. Using multiple writers does not make `write()` calls atomic messages; writes can interleave at the application level. Using multiple consumers splits bytes among them rather than broadcasting copies to each consumer. When multiple producers/consumers need clear element boundaries and coordination, consider `BlockingQueue<T>` or an appropriate concurrent primitive.

### 7.8. Using a Pipe as a Message Queue Replacement

`PipedInputStream` handles **bytes**. It has no `put(Message)`, broadcasting, retries, acknowledgments, persistence, or schema. If your goal is passing objects or tasks between workers, `BlockingQueue<T>` is usually more direct and controllable. If your goal is connecting an `OutputStream`-producing API to an `InputStream`-consuming API without creating temporary files, a pipe is genuinely useful.

## 8. Comparison with Other In-Memory I/O Solutions

| Solution | Data Form | Blocks Waiting for Other End? | Typical Use Case |
| --- | --- | --- | --- |
| `ByteArrayOutputStream` / `ByteArrayInputStream` | Byte array | Not via pipe semantics | Building data and reading it back in RAM without concurrent producer/consumer |
| `PipedOutputStream` / `PipedInputStream` | Connected two-end byte stream | **Yes**: reads wait for data, writes wait for space | Streaming bytes concurrently between a producer and consumer in the same JVM |
| `StringWriter` / `StringReader` | In-memory characters | Not via pipe semantics | Constructing and reading character strings |
| `BlockingQueue<T>` | Elements of type `T` | **Yes**, depending on operation and queue capacity | Passing discrete messages/tasks between threads while preserving item boundaries |
| `java.nio.channels.Pipe` | Bytes via `SourceChannel`/`SinkChannel` | Blocking mode configurable per channel API | Integrating with NIO and channels |

`java.nio.channels.Pipe` is also a one-way byte mechanism, yet it is a channel API with different characteristics and methods. Do not equate it with `java.io.PipedInputStream`/`PipedOutputStream`; blocking behavior, selector integration, and design options must be checked per channel/provider.

### When Should You Choose `PipedInputStream`/`PipedOutputStream`?

Appropriate when:

- You need to connect an **OutputStream-writing** API directly to an **InputStream-reading** API within the same application.
- You want the producer to emit data incrementally and the consumer to process it concurrently without creating temp files or holding the entire payload in RAM.
- You accept byte-stream semantics, backpressure, and thread lifecycle management.

Inappropriate when:

- You only need to read back already-generated bytes: `ByteArrayOutputStream` and `ByteArrayInputStream` are simpler.
- You need a queue of discrete message objects or multiple producers/consumers: use a queue.
- You need communication between **two separate processes** or different machines: use appropriate IPC or networking; `Piped*Stream` classes are not OS named pipes.
- You need high concurrency throughput, timeouts, cancellation, and specialized error handling: channels, queues, or a well-structured concurrent pipeline may be needed.

## 9. Pipe Communication Design Checklist

Before implementing, determine:

1. **Who creates and connects the pipe?** Connect both ends once before workers start using them.
2. **Who is the producer and who is the consumer?** Run both concurrently on appropriate threads; never create a situation where the writer waits for the reader on the same thread.
3. **What is the buffer size?** Balance RAM, throughput, and blocking frequency. Never treat buffer capacity as a message boundary.
4. **What is the data format?** Raw bytes, a defined charset, or a length-prefixed/delimited protocol? If messages exist, specify framing explicitly.
5. **What is the termination condition?** Producer closes output; consumer reads to EOF or parses an agreed protocol sentinel.
6. **Who closes resources?** Each side owns its own end and outermost wrapper; close in proper order.
7. **How are errors propagated from either side?** Use `Future.get()`, shared error state, or a coordinator; handle cancellation so blocked threads are not stranded.
8. **Are inputs bounded?** When reading length prefixes, validate lengths before allocating; when streaming external data, enforce total byte limits where needed.
9. **Are buffered or character wrappers used?** Understand `flush()` and charsets; avoid deadlocks caused by data sitting inside a writer's buffer.
10. **Do you truly need a byte stream?** If communicating at the object/task level, consider `BlockingQueue`.

## 10. Self-Check Questions

**1.** Can a pipe let thread A write bytes while thread B reads them as soon as they are produced?

**Answer:** Yes. Connect a `PipedOutputStream` to a `PipedInputStream` and run the producer and consumer concurrently. It acts as a one-way byte stream.

**2.** A pipe has a 4-byte buffer; a single thread calls `write` with 100 bytes before calling `read`. Is this safe?

**Answer:** No. `write` will block once the buffer fills up, with no running consumer to free space.

**3.** The reader finds no bytes currently in the buffer, yet the writer is still open. Must `read()` return `-1`?

**Answer:** No. It blocks waiting for data. EOF `-1` normally appears only after the write end closes and all buffered bytes are consumed.

**4.** The producer calls `write(byte[])` once. Is the consumer guaranteed to receive the entire array in a single `read(byte[])` call?

**Answer:** No. A pipe does not preserve `write` call boundaries as messages. The consumer must use framing and loop reads until all expected bytes arrive.

**5.** When sending UTF-8 text, should you convert arbitrary chunks into separate `String`s?

**Answer:** No. Multi-byte characters can be split across chunk boundaries. Use a stateful decoder (`InputStreamReader`) or assemble the full byte payload before decoding.

**6.** Does calling `flush()` on the writer signal "end of stream" to the consumer?

**Answer:** No. `flush()` pushes buffered data onward; the producer must close the write end or send an application-level termination signal.

**7.** When passing objects/tasks from multiple producers to multiple consumers, is a pipe the first choice?

**Answer:** Usually not. `BlockingQueue<T>` preserves discrete items and coordinates multiple producers/consumers much more cleanly. Pipes fit byte streams.

**8.** Why did `PipeHelloDemo` call `producer.get()` **after** the read loop?

**Answer:** Calling it beforehand would make the `main` thread wait for the writer to finish while the writer waits for `main` to read and free buffer space, causing a deadlock. Reading concurrently and awaiting the `Future` afterward lets both sides make progress.

**Key takeaway:** `PipedOutputStream` + `PipedInputStream` form a **one-way, blocking, bounded-buffer byte pipe between threads in the same JVM**. Connect before starting, read and write concurrently, close the write end so the consumer observes EOF, and define explicit framing if you need discrete messages. When your problem operates on objects or tasks rather than byte streams, reach for a concurrent queue instead.
