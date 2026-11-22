# Limiting Concurrent Operations and Resource Pressure in Asynchronous Java NIO

## 1. Why Does Async I/O Still Need Limits?

Asynchronous I/O in `java.nio.channels` lets you initiate read/write operations and receive results later via `Future` or `CompletionHandler`. The requesting thread does not necessarily wait for the I/O operation to finish.

However, **not blocking the calling thread does not mean operations cost zero resources**. If an application continuously fires new requests without controlling the rate, the system may have to hold huge numbers of buffers, callbacks, sockets, file descriptors, data waiting to be processed, and queued work. Under overload, latency spikes, memory runs out, timeouts occur, and even healthy requests suffer.

For example: 10,000 read operations, each owning a 1 MiB `ByteBuffer`, create **roughly 10,000 MiB (nearly 9.8 GiB)** of byte-region memory in theory—excluding objects, queues, native memory, caches, and other resources. Using `AsynchronousFileChannel` does not solve this problem by itself.

This lesson belongs to **Java Core I/O → Asynchronous I/O**. The focus is identifying accurately what "concurrency" is measuring, limiting in-flight operations, choosing executors/channel groups, backpressure, `ByteBuffer` ownership, handling completion/failure, closing resources, and safe operation.

## 2. Three Numbers That Must Not Be Equated

Async systems usually have several distinct limit levels:

| Metric | Definition | Consequence If Too Large |
| --- | --- | --- |
| **In-flight operations** | Number of I/O operations initiated but not yet completed | Retains buffers, kernel resources, callbacks; may exhaust resources |
| **Worker/completion threads** | Number of threads used to execute or dispatch callbacks | Context switching/CPU and risk of callbacks monopolizing threads |
| **Queued work / pending bytes** | Number of requests or bytes queued, not yet dispatched to I/O or not yet fully sent | Memory buildup, rising latency, loss of pressure control |

For example, an `ExecutorService` with 4 threads **does not by itself prove** there are only 4 pending I/O operations. One thread can initiate many async operations and return immediately; the number of pending operations can then far exceed the worker count. Conversely, an `in-flight=4` limit does not mean the program always has exactly 4 physical threads or runs 4x faster.

Measure `activeIo`, `pendingRequests`, `pendingBytes`, `callbackDuration`, `requestLatency`, open channel counts, errors/timeouts, and rejection rates separately.

## 3. Relevant Java NIO APIs

### `AsynchronousFileChannel`

`AsynchronousFileChannel.open(path, options, executor, attrs...)` opens a file channel capable of reading/writing at absolute `long` positions. `read(dst, position, attachment, handler)` initiates an operation and the callback is invoked with bytes read or an exception. One channel can have **multiple concurrent read/write operations**, yet completion order **is not guaranteed to match initiation order**.

Depending on the provider, async file I/O may be implemented using threads in the executor rather than a purely asynchronous kernel interface. The executor thread count and the number of submitted operations remain two distinct limits.

### `AsynchronousSocketChannel`

`AsynchronousSocketChannel` allows **at most one pending read operation and one pending write operation on the same channel at a time**. One read and one write can coexist concurrently, yet calling a second read before the first finishes throws `ReadPendingException`; likewise a second write causes `WritePendingException`.

This is only a **per-socket** limit, not a service-wide limit: 20,000 sockets can simultaneously have up to 20,000 pending reads, plus writes alongside them. Both per-connection and application-wide quota policies are needed.

### `AsynchronousChannelGroup`

Asynchronous socket/server channels can attach to an `AsynchronousChannelGroup`, associated with a thread pool used to dispatch completions. Managing the group lets the application control the lifecycle and resources serving many channels.

Do not equate `AsynchronousChannelGroup` with `AsynchronousFileChannel.open(..., ExecutorService)`: file channels can accept an executor directly; socket channels use a channel group. Nor should you assume configuring `fixedThreadPool(8)` automatically creates a **bounded application request queue**.

### `Future` and `CompletionHandler`

With `Future<Integer>`, calling `future.get()` on the initiating thread **blocks that thread** until completion. With `CompletionHandler`, the initiating thread normally does not wait on `get`, yet callbacks still run on a thread and consume CPU. If callbacks contain long blocking logic, synchronous database reads, or heavy CPU processing, throughput can drop sharply.

## 4. Lifecycle of an Async Operation and When Resources Are Held

```text
Incoming request
     |
     v
Check quota + acquire permit + allocate buffer
     |
     v
Initiate async I/O (IN-FLIGHT)
     |
     +---- completed successfully --> process result / move to next phase
     |
     +---- failed / timeout --> handle error / close or retry per policy
     |
     v
Release permit and buffer when the operation truly ends
     |
     v
Take next request from bounded queue
```

A **permit** is the "right" to hold one running I/O slot. If limited to 32, operations tracked by the limiter do not exceed 32. Hold the permit **for the entire lifecycle** of a request if that request triggers multiple continuation reads to complete a payload; release the permit only when the logical activity is deemed finished or cancellation has been handled per the provider's contract.

Calling `release()` too early right after `channel.read(...)` is wrong: that call only **initiates** the async read, while the buffer and channel may still be in use. Re-issuing the permit then lets new requests flood in even though the prior request has not finished.

## 5. Calculate the Memory Budget Before Picking Limits

If one request holds a buffer of at most `B` bytes and at most `N` in-flight operations, buffer memory is roughly:

```text
memoryForBuffers ≈ N × B

Total budget ≈ memoryForBuffers
               + pending application payloads
               + outbound queues
               + connection state
               + executor queue / task objects
               + runtime, TLS, native, file-system resources
```

Examples:

| Max in-flight | Buffer/request | Total byte region size, excluding overhead |
| ---: | ---: | ---: |
| 16 | 64 KiB | 1 MiB |
| 128 | 64 KiB | 8 MiB |
| 512 | 256 KiB | 128 MiB |
| 10,000 | 1 MiB | ≈ 9.77 GiB |

Standard `ByteBuffer.allocate()` uses the heap; `ByteBuffer.allocateDirect()` uses direct/native memory with different limits and GC characteristics. **Direct buffers do not mean zero RAM usage.** Large numbers of direct buffers can cause `OutOfMemoryError: Direct buffer memory` or native memory pressure even while heap space remains.

If the application keeps buffers in an object pool, memory may remain retained after I/O finishes. Pools reduce repeated allocation overhead, yet an **unbounded** pool or oversized buffers can make things worse.

The budget also depends on buffer type, message length, connection count, unsent outbound bytes, and how fast consumers process results. Quotas by **task count** usually need to be paired with quotas by **byte count**.

## 6. Using `Semaphore` to Limit In-Flight I/O

`java.util.concurrent.Semaphore` is a direct way to represent remaining slots:

```java
Semaphore permits = new Semaphore(32);

// At a request-intake point permitted to wait:
permits.acquire();
try {
    // Allocate resources and start the async operation.
    // After initiating, DO NOT release immediately here.
} catch (RuntimeException e) {
    // If no completion callback will take cleanup responsibility,
    // release the acquired permit.
    permits.release();
    throw e;
}

// CompletionHandler in the terminal branch:
try {
    // handle success or failure
} finally {
    permits.release();
}
```

These are **illustrative snippets placed in separate locations**, not a standalone runnable Java method. In production, structure state so **every permit is released exactly once**, including failed callbacks, failed initiation, cancellation, and shutdown. If an operation can invoke its success/failure callback synchronously on the initiating thread, prevent races between the submit branch and callback.

Use `tryAcquire()` to avoid blocking a coordinating thread when slots are exhausted:

```java
if (!permits.tryAcquire()) {
    // Reject, return a "busy" signal, or place into a bounded queue.
    // Do not silently accumulate millions of requests.
    return;
}
```

Inside an event loop, avoid `Semaphore.acquire()` because it **blocks the event-processing thread**; use `tryAcquire()`, bounded queues, or asynchronous quota allocation. In a batch job with a dedicated producer thread, `acquire()` can be simple and valid backpressure.

### 6.1. Choosing a Policy When Permits Run Out

- **Wait**: producer waits, fitting batch jobs or threads outside an event loop.
- **Bounded queue**: wait in order up to a clear limit; when the queue is full, reject or wait at an outer layer.
- **Fail fast**: return a busy error, such as HTTP 429/503 (if the application is an appropriate server).
- **Load shedding**: drop low-priority requests or overly slow connections per an explicit policy.
- **Adaptive limit**: adjust slot count based on latency, CPU, memory, and error measurements; benchmark carefully to avoid oscillation.

Do not use `Executors.newFixedThreadPool(k)` as a "general quota solution" while forgetting that `newFixedThreadPool` comes by default with an **unbounded queue** for submitted tasks.

## 7. Runnable Java 17+ Example: Async File Reading with At Most Two Concurrent Jobs

This program uses `AsynchronousFileChannel`, `CompletionHandler`, `Semaphore(2)`, `CountDownLatch`, and a two-thread executor. A temporary file containing `ABCDEFGHIJKL` is split into three 4-byte regions; all regions are read asynchronously, yet **at most two logical jobs are in flight**.

The program **does not assume callback order**: each job stores its result in its own slot and prints results only after all finish. If one read returns fewer than 4 bytes, the same job continues reading the missing portion at the next offset while holding its permit.

Create the file `AsyncIoLimitDemo.java`:

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public class AsyncIoLimitDemo {
    private static final int BLOCK_SIZE = 4;
    private static final int MAX_IN_FLIGHT = 2;

    private static class ReadJob implements CompletionHandler<Integer, Void> {
        private final AsynchronousFileChannel channel;
        private final ByteBuffer buffer = ByteBuffer.allocate(BLOCK_SIZE);
        private final long fileOffset;
        private final int index;
        private final String[] results;
        private final Throwable[] errors;
        private final Semaphore permits;
        private final CountDownLatch done;
        private final AtomicBoolean settled = new AtomicBoolean();

        ReadJob(AsynchronousFileChannel channel, long fileOffset, int index,
                String[] results, Throwable[] errors,
                Semaphore permits, CountDownLatch done) {
            this.channel = channel;
            this.fileOffset = fileOffset;
            this.index = index;
            this.results = results;
            this.errors = errors;
            this.permits = permits;
            this.done = done;
        }

        void submit() {
            try {
                long nextPosition = fileOffset + buffer.position();
                channel.read(buffer, nextPosition, null, this);
            } catch (RuntimeException ex) {
                finish(null, ex);
            }
        }

        @Override
        public void completed(Integer n, Void ignored) {
            if (n == null || n < 0) {
                finish(null, new EOFException("Unexpected EOF"));
                return;
            }
            if (n == 0) {
                // Demo chooses to report an error to avoid a continuous retry loop.
                finish(null, new IOException("Read made no progress"));
                return;
            }
            if (buffer.hasRemaining()) {
                submit(); // Keep holding the same permit until BLOCK_SIZE is reached.
                return;
            }

            buffer.flip();
            byte[] bytes = new byte[buffer.remaining()];
            buffer.get(bytes);
            finish(new String(bytes, StandardCharsets.US_ASCII), null);
        }

        @Override
        public void failed(Throwable error, Void ignored) {
            finish(null, error);
        }

        private void finish(String value, Throwable error) {
            if (!settled.compareAndSet(false, true)) {
                return; // guard cleanup if finish is invoked repeatedly
            }
            results[index] = value;
            errors[index] = error;
            permits.release(); // One permit per logical job.
            done.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("async-io-limits-", ".dat");
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Files.writeString(
                    file, "ABCDEFGHIJKL", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(
                            file, Set.of(StandardOpenOption.READ), pool)) {

                Semaphore permits = new Semaphore(MAX_IN_FLIGHT);
                CountDownLatch done = new CountDownLatch(3);
                String[] results = new String[3];
                Throwable[] errors = new Throwable[3];

                for (int i = 0; i < 3; i++) {
                    // This is a batch producer on main, not an event loop.
                    permits.acquire();
                    new ReadJob(channel, i * (long) BLOCK_SIZE, i,
                            results, errors, permits, done).submit();
                }

                done.await();
                for (int i = 0; i < results.length; i++) {
                    if (errors[i] != null) {
                        throw new IOException("Job " + i + " failed", errors[i]);
                    }
                    System.out.println("chunk " + i + ": " + results[i]);
                }
                System.out.println("in-flight limit: " + MAX_IN_FLIGHT);
            }
        } finally {
            pool.shutdown();
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AsyncIoLimitDemo.java
java AsyncIoLimitDemo
```

Stdout when the temporary file is created successfully and the filesystem operates normally:

```text
chunk 0: ABCD
chunk 1: EFGH
chunk 2: IJKL
in-flight limit: 2
```

**Why is stdout stable?** Completion callbacks may arrive in any order, yet they write into `results[index]`; the main thread awaits `done.await()` before printing by index. `CountDownLatch` also establishes a happens-before relationship for updates prior to `countDown()`. The program does not print callback order or a "peak concurrent operations" metric that can vary by schedule.

**Limiting explanation:**

1. `MAX_IN_FLIGHT=2` creates two permits. Jobs 0 and 1 can start; the producer launches job 2 only after one completion returns its permit.
2. Each job has its own `ByteBuffer`, retained until the job finishes. If `read` transfers only a portion, `submit()` is called again with the offset advanced by `buffer.position()` without **acquiring a new permit**.
3. `completed`, `failed`, and synchronous initiation errors all route through `finish`; `AtomicBoolean` prevents releasing the permit multiple times.
4. `done.await()` ensures jobs have reported completion before the program reads results and closes the channel.
5. `pool.shutdown()` stops the executor, and `try-with-resources` closes the channel; the temporary file is cleaned up in `finally`.

With a normal file and three existing 4-byte regions, the output above is expected. If the provider hits an I/O error or returns `0` while the buffer still has space, the demo deliberately treats it as a "no progress" error instead of retrying infinitely; the result is an exception rather than complete stdout.

**Demo limitations:** `Semaphore.acquire()` blocks **the main batch producer**, intentionally illustrating backpressure; do not copy that pattern onto an event-processing thread. If the producer is interrupted or a global error occurs while I/O remains in progress, a real application must coordinate stopping intake, completing/canceling remaining jobs, and only then closing resources. The demo uses a fixed file and excludes waiting queues, retry policies, deadlines, and metrics.

## 8. A Socket Cannot Have Multiple Pending Reads

With `AsynchronousSocketChannel`, the following code is wrong if the first read has not finished:

```java
ByteBuffer first = ByteBuffer.allocate(1024);
ByteBuffer second = ByteBuffer.allocate(1024);

socket.read(first);  // Returns Future<Integer>
socket.read(second); // May throw ReadPendingException
```

This is a snippet with a `socket` variable inside a method, not a standalone program. Similarly, initiating a second write while a write is pending may throw `WritePendingException`.

The right pattern is **sequentially chaining reads for a socket**:

```text
start read #1
     |
     +-- completed(n > 0): parse data, check quota/buffer
     |                        |
     |                        +-- need more data: start read #2
     |
     +-- completed(-1): EOF, end of input
     +-- failed(error): log/close/cleanup
```

A socket can simultaneously have **one read and one write**. Reading and writing are independent yet share connection state, so closing, timeouts, and state synchronization must be controlled.

Do not spawn a new thread per socket just to call `future.get()`. With thousands of sockets, that forfeits much of the benefit of async I/O. Fast callbacks and sensible scheduling serve many connections using a bounded thread pool.

## 9. ByteBuffer Has Ownership Throughout the Operation

While `channel.read(buffer, ...)` or `channel.write(buffer, ...)` is in progress, **do not arbitrarily read/write or alter `position`/`limit` of that buffer from another thread**. The API documentation emphasizes `ByteBuffer` is not thread-safe and access must be avoided while async operations are pending.

Wrong:

```java
Future<Integer> pending = channel.read(buffer);
buffer.clear(); // Wrong: I/O may still be writing into the buffer
```

This snippet illustrates `AsynchronousByteChannel`, not `AsynchronousFileChannel` because file channel read signatures require a file position. Before completion, `clear()` can alter state that I/O depends on.

Design guidelines:

- Each pending operation has a buffer it owns, or a buffer pool grants **exclusive** ownership until completion.
- Reuse a buffer only after I/O has genuinely ended and the consumer no longer uses the data.
- With `slice()`/`duplicate()`, views can share storage despite separate `position`s: never assign them concurrently to two operations modifying the same memory region.
- On partial writes, the buffer must continue from its current `position`; calling `clear()` early loses the unsent data state.
- On partial reads of a frame, retain state across completions; `read()==0` is not EOF, only `read()==-1` signals end of input.
- If a timeout leaves a buffer in an undefined state under `AsynchronousSocketChannel`'s contract, do not reuse the buffer on the assumption "zero bytes were transferred."

Use `ByteBuffer.allocateDirect` only when real profiling shows benefit; direct buffers also need their own quota and a cleanup policy not relying on `clear()` (since `clear()` neither erases data nor frees memory).

## 10. CompletionHandlers Must Be Brief and Always Finalize Resources

Callbacks may be invoked by threads from the async processing pool. If a callback performs very heavy parsing, blocking database calls, or waits for another permit, it can stall completion of other I/O operations.

Recommended pattern:

```text
I/O completion callback
  1) Verify result and state
  2) Hand off data/work to a bounded processing queue if needed
  3) End I/O ownership and release permit at the right time
  4) Schedule next I/O when quota allows; avoid long blocking
```

However, if the downstream queue has no space, **do not release the permit and keep receiving endlessly** while application data goes unconsumed. Backpressure must span the entire pipeline: when the consumer slows down, cap queued bytes or pause issuing new reads on the socket.

### 10.1. Avoiding "Callback Starvation"

Suppose a group has 4 threads and all 4 callbacks call `semaphore.acquire()` waiting for a slot that another callback would `release()`. If the callback needed to release is waiting for a free thread in the same pool, the application can hit starvation/deadlock by design.

Solution: **do not block inside completion callbacks**. If no permit is available, record a paused state and let a scheduler or bounded queue resume once a slot returns; if the queue is full, apply a rejection/backpressure policy rather than waiting indefinitely inside the pool.

### 10.2. Ensuring Permits Are Released on Failure

Every logical termination branch must be handled:

- `completed(n)` fully succeeded.
- `completed(n)` partial, potentially needing continuation for the same job.
- `completed(-1)` EOF.
- `failed(exc)` I/O error, timeout, or close.
- Synchronous error when starting I/O before a callback is successfully registered.
- Shutdown/cancellation per the provider's rules.

Designing a job management object with an `AtomicBoolean settled` state reduces double-release bugs. For multi-step jobs, release when the **logical job** finishes; if tracking each physical operation instead, define the quota unit clearly to avoid counting mismatches.

## 11. Backpressure on Both Inbound and Outbound Paths

### Inbound: Slow Consumer

Clients send messages faster than the parser/database layer processes them. If every completion immediately reads again and buffers messages in an unbounded queue, heap grows even though pending reads per socket never exceed one.

Measures:

1. Limit in-flight requests.
2. Limit **total bytes** in the inbound queue, not just frame count.
3. Under overload, pause issuing further reads on connections with large backlogs, or reject per protocol.
4. Resume reading once the queue drops below a low watermark.
5. Enforce deadlines/timeouts so stalled connections do not hold slots forever.

### Outbound: Slow Receiver Peer

An `AsynchronousSocketChannel.write` may complete with fewer bytes than the initial `src.remaining()`. Multiple responses can accumulate in an outbound queue; ordering must be preserved and there can be **only one pending write per socket**.

```text
outbound queue: [remaining Frame A, Frame B, Frame C]
      |
      v
write(Frame A) -> completion
    if bytes remain: write remainder of Frame A
    if Frame A finished: dequeue Frame B
      |
      v
queue empty -> wait for new message
```

If the application enqueues responses faster than the socket sends them, an **`outboundBytes`** quota matters more than a frame-count quota. Stop processing new requests, apply flow control, or close excessively slow connections per policy.

For async sockets, never attempt a second `write` while the prior write is pending: besides `WritePendingException`, buffers can be managed out of order.

## 12. Thread Pools, Channel Groups, and Queues

Do not choose worker counts by the rule "more is faster." CPU-bound and I/O-bound tasks have different profiles; one provider may use threads to perform file I/O, while another has its own mechanism.

- Use a thread pool suited to the workload and profile.
- If callbacks are lightweight, a relatively small number of threads can serve many completions.
- If callbacks perform long CPU computations, move them to a separate **bounded worker queue** to avoid occupying completion threads.
- Do not create a new channel group or executor per request.
- Manage group/pool lifecycles service-wide; shut down cleanly, ensuring no new jobs are submitted after stopping intake.
- `AsynchronousChannelGroup.shutdown()` and `shutdownNow()` have distinct semantics; close channels and await termination per API when needed. Avoid relying on daemon threads exiting on their own.
- The JDK's default group/thread pool behaves according to system configuration; applications with strict resource needs should configure and measure an appropriate setup.

**Common confusion:** an executor using 8 threads does not mean there are at most 8 outstanding socket reads; completion thread count is also not the cap on total connections.

## 13. Cancellation, Timeouts, and Closing Channels

With `Future.cancel(true)`, do not infer that I/O stopped completely and the buffer is immediately safe to modify from another thread. Cancellation behavior depends on channel/provider, and canceling may close the channel or complete with an exception.

Some `AsynchronousSocketChannel.read/write` overloads accept a timeout; when a timeout occurs, the buffer or channel may enter a provider-dependent state. API documentation warns that a timeout can put the channel into an error state because the system cannot reliably determine whether data was transferred.

The cleanup sequence must distinguish:

1. **Stop accepting new requests** and stop initiating new I/O.
2. **Allow active operations to finish** within a reasonable deadline, or apply a cancellation policy.
3. **Terminate/close channels** once shutdown is decided.
4. **Ensure completion/failure paths update state and release permits**; avoid double-release.
5. **Free buffers and request state** once certain no operation accesses that memory.
6. Close channel groups/executors owned by the component; never arbitrarily shut down a pool shared by other components.

For "missing byte" or partial-write failures, retrying an entire request can cause application-level duplicates. If data was partially sent and timed out, use idempotency keys, sequence numbers, or proper confirmation protocols; retry only when business rules permit.

## 14. Observing and Tuning Limits with Metrics

An async system should expose at least these metrics:

| Metric | Purpose |
| --- | --- |
| `io.inflight` | Operations genuinely unfinished |
| `io.maxInFlight` | Current configured limit |
| `io.pending.requests` | Bounded queue size |
| `io.pending.bytes` | Actual memory/backpressure pressure |
| `io.complete.latency` | Latency from initiation → completion |
| `io.callback.duration` | Whether callbacks occupy workers too long |
| `io.errors`, `io.timeouts` | Diagnosing failures and overload |
| `io.rejected` | Requests rejected due to quota exhaustion |
| `process.openFiles` / sockets | File descriptor pressure |
| Heap/direct memory/GC | Visibility into allocation and native memory pressure |

Monitor `p95`/`p99` latency alongside throughput. If raising `MAX_IN_FLIGHT` from 32 to 1,024 barely increases throughput while queues, memory, and timeouts surge, the application has passed its point of diminishing returns.

### 14.1. Little's Law and Limits

For a system near steady state, the number of requests in the system is approximately:

```text
L = λ × W
```

Where `L` is average in-system requests, `λ` is average arrival/completion rate, and `W` is average time a request spends in the system (including wait time per measurement definition). For example, 500 requests/sec at 0.2s average latency corresponds to roughly 100 concurrent requests in the system.

The formula **does not tell you the optimal permit count by itself**. It helps estimate demand at real load and notice when rising latency inflates in-flight request counts. Choosing quotas also requires considering spikes, file descriptors, memory, fairness, SLAs, and failure modes.

## 15. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Launching async reads without quotas | Exhausted buffers, overloaded kernel/workers | Cap in-flight count and byte budget |
| Thinking 8 workers = max 8 I/O ops | Thousands of I/O ops can still be pending | Measure/limit operations independently |
| Calling `release()` right after `channel.read()` | Slot reused while I/O is still unfinished | Release on completion/failure |
| Forgetting release in `failed` | Permit leaks, system stalls accepting work | Single unified cleanup path |
| Callback calling `Semaphore.acquire()` | Blocks pool, starvation risk | `tryAcquire()` or scheduler with bounded queue |
| Allocating huge `ByteBuffer` per request | Heap/direct memory pressure | Memory quota and appropriately sized buffers |
| Modifying/clearing buffer before Future finishes | Data race/corrupted bytes | Buffer ownership until completion |
| Two simultaneous reads on an async socket | `ReadPendingException` | Chain reads after completion |
| Two simultaneous writes on an async socket | `WritePendingException` | Queue and serialize writes |
| Limiting queue only by item count | A few huge frames still exhaust RAM | Quota by total bytes |
| Treating `newFixedThreadPool` as a bounded queue | Task queue can grow unboundedly | Create bounded work queue or backpressure |
| Calling `future.get()` on an event-loop thread | Blocks event loop | CompletionHandler/callbacks or another wait model |
| Treating `cancel(true)` as making buffer safe | Provider-dependent I/O/state may persist | Coordinate cancel/close per contract |
| Retrying write after timeout without duplicate checks | Sends duplicate data/messages | Idempotency/sequence/acknowledgment |
| Opening an executor/group per request | Thread/resource explosion | Use centrally managed groups |

## 16. Self-Check Questions

**1.** You have a 4-thread executor. Does that guarantee at most 4 pending I/O operations?  
**Answer:** No. Thread count and pending I/O count are separate; separate limits are needed.

**2.** Is it right to initiate async `read` successfully and immediately call `permits.release()`?  
**Answer:** Wrong if the permit represents an in-flight operation; hold it until completion/failure or logical job completion.

**3.** Can an `AsynchronousSocketChannel` have two outstanding reads?  
**Answer:** No; the second throws `ReadPendingException`. It can have one read and one write concurrently.

**4.** Can an `AsynchronousFileChannel` have multiple outstanding reads?  
**Answer:** Yes; the API allows it, though results may complete out of initiation order.

**5.** With 1,000 requests each holding a 1 MiB buffer, roughly how much buffer memory is used?  
**Answer:** 1,000 MiB (nearly 0.98 GiB), excluding overhead and other queues.

**6.** Why must `ByteBuffer.clear()` not be called while an async read is still pending?  
**Answer:** It changes `position/limit`; ongoing I/O using the buffer can be affected. Buffers are unsafe for concurrent access before completion.

**7.** Callbacks run slowly while the in-flight limiter stays low. Can the system still overload?  
**Answer:** Yes. The completion pool and downstream queues/CPU are also bottlenecks; the limiter is only one part of backpressure strategy.

**8.** Is capping a queue at 100 messages enough to prevent running out of memory?  
**Answer:** Not necessarily. One message could be tens of MiB; a total-byte limit is needed.

**9.** An async `write` completes with part of the buffer remaining; how should you proceed?  
**Answer:** Continue with the same buffer from its remaining `position` once the previous write finishes, without issuing overlapping writes.

**10.** Is `Semaphore.acquire()` inside an event loop good practice?  
**Answer:** No. It can block the thread; use `tryAcquire()` and non-blocking queue/backpressure coordination.

## 17. Operational Checklist

1. Choose quota units: **physical I/O**, **logical requests**, **connections**, or all three.
2. Compute buffer budget from bytes/operation and slot counts; leave headroom for heap, direct memory, TLS, and outbound queues.
3. Combine concurrency limits with bounded queues, timeouts, and overload policies.
4. Hold permits until completion or logical job termination; clean up exactly once.
5. For asynchronous sockets, keep at most one pending read and one pending write per connection.
6. Manage `ByteBuffer` ownership across the entire task lifecycle.
7. Never block completion handlers; offload heavy processing to a bounded worker pool.
8. Control backpressure on both inbound and outbound paths, especially with slow senders or receivers.
9. Define shutdown/cancellation, avoiding double-release and premature buffer reuse.
10. Observe p95/p99 latency, in-flight count, backlog bytes, timeout errors, rejections, and open handles; tune limits via load testing.

## Official Documentation

- Java SE 17 — `AsynchronousFileChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html
- Java SE 17 — `AsynchronousSocketChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html
- Java SE 17 — `AsynchronousChannelGroup`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html
- Java SE 17 — `CompletionHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html
- Java SE 17 — `AsynchronousByteChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html
- Java SE 17 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 — `Semaphore`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html
