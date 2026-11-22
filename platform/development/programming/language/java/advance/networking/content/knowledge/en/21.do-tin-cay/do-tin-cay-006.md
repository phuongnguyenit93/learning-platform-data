# Slow Receivers, Write Queues, and Application-Level Rate Limiting — Java Networking (Java 17+)

## 1. The Problem: Why Can a Slow Receiver Overload the Sender?

A real-time server can generate 200 events per second, while a mobile device can only read or process 50 events per second. If the server keeps pushing data into an **unbounded write queue**, wait times grow, the heap can fill up, GC becomes heavy, and eventually the application can run out of memory. This situation occurs even before the TCP connection reports any error.

A slow receiver can be caused by network congestion, a weak device, an application not reading from the socket, a backgrounded browser, a throttling proxy, or a consumer waiting on a database. The consequences differ by layer, but the reliability question is the same: **what must the sender do when it produces data faster than the receiver can sustainably absorb?**

~~~text
Producer (very fast)                           Slow receiver
         |                                         |
         v                                         |
  app outbound queue                               |
      [m1,m2,m3,m4,...]                              |
         |                                         |
         v                                         |
    writer thread / NIO                             |
         |                                         |
         v                                         |
     kernel TCP send buffer -----------> network --+--> kernel receive buffer
         ^                                                 |
         |                                                 v
         +-- window/backpressure ----------- app read()/process()
~~~

TCP has **flow control**: the receiver advertises a receive window, so the sender's kernel cannot keep pushing bytes beyond the peer's capacity to receive. However, TCP **does not automatically bound the application's queue**, does not know how producers allocate new objects, and does not control pending `Future`s, HTTP/WebSocket outbound buffers, or retry tasks.

**Principle:** you need to combine a **bounded queue**, an **overload policy**, **rate limiting**, **time limits**, and, when business logic requires it, **application acknowledgment (ACK)**. No single TCP configuration replaces all of these components.

This lesson belongs to the **Java Advance - networking** module, parent section **Reliability**, topic **“Slow Receivers, Write Queues, and Application-Level Rate Limiting”**. Two complete examples are verified with `javac --release 17`: one real TCP queue over loopback, and one token bucket with a simulated clock.

## 2. After This Lesson, You Will Understand

- How to distinguish **slow consumer**, **backpressure**, **bounded queue**, **load shedding**, **flow control**, **token bucket**, **pacing**, and **fairness**.
- That the states **successfully enqueued**, **socket write completed**, **TCP ACK**, **receiver parsed message**, and **business committed** are not equivalent.
- Why `Socket.setSoTimeout(...)` bounds a blocking **read**, and does not automatically set a write deadline.
- How to choose a policy when the queue is full: reject, timed wait, drop, coalesce, disconnect, pause producer, or durable spill.
- Why capping the **number of messages** alone is not enough, and you must cap **bytes in queue + in-flight**.
- How to maintain **a single writer owner per connection** to preserve framing and prevent bytes from different producers from interleaving.
- That TCP is a byte stream, requiring **message framing and length validation**.
- How to throttle rate using a **token bucket** based on encoded bytes; distinguishing burst capacity and refill rate.
- How to handle `SocketChannel.write(ByteBuffer)` returning **0** or writing partially; using `SelectionKey.OP_WRITE` conditionally.
- How to recognize when `Flow.Subscription.request(n)` or `WebSocket.request(n)` is meaningful and when it cannot replace socket-write backpressure.
- How to design deadlines, idempotency, retries, queue TTL, fair scheduling, observability, and reconnects.

## 3. Four Key Milestones: Queued ≠ Sent ≠ Received ≠ Processed

~~~text
1. Producer queue.offer(message) -> true
       |
       v
2. Writer takes message, encodes, writes to socket
       |
       v
3. Kernel/transport/receiver reads bytes and parses frame
       |
       v
4. Receiver processes business logic, persists state, returns app ACK (if any)
~~~

| Signal | What It Actually Confirms | What Cannot Be Concluded |
| --- | --- | --- |
| `queue.offer(msg) == true` | Message has entered the **sender's queue** | Does not prove it was sent |
| Writer dequeues item | Item was picked up by a worker for processing | Does not prove it was written to the socket |
| `OutputStream.write(bytes)` returns | Local write operation completed per the API contract | Does not prove the receiver application has read it |
| `SocketChannel.write(buf)` returns `n > 0` | `n` bytes were accepted by the channel for writing | Does not mean the entire buffer was written |
| TCP ACK from peer stack | Peer transport acknowledged bytes per TCP semantics | Not a business ACK |
| `WebSocket.sendText(...)` future succeeds | WebSocket send operation completed | Receiver business worker may not have run yet |
| App replies `ACK(messageId)` | The action defined by the protocol as ACK has occurred | Does not guarantee database commit if ACK only means “received” |
| Committed ACK from transaction service | Committed per the receiving system's contract | Does not automatically guarantee exactly-once under retry/reconnect |

An app may need different milestones: lossy notifications only need best-effort delivery; chat needs message replay after reconnect; payments need an idempotency key and transaction commit confirmation. **TCP protects byte ordering within a connection; it does not provide durable exactly-once business delivery.**

### 3.1. How Does a Slow Receiver Affect TCP?

The receiver does not call `read()` fast enough → the receiver's kernel receive buffer fills up → the receiver advertises a small/zero TCP window → the sender kernel slows down byte transmission → the sender kernel buffer begins to fill → **blocking `OutputStream.write()` can block for a long time**, or **nonblocking `SocketChannel.write()` can return 0**.

However, for small payloads, kernel buffers still have room, so writes can return immediately even though the receiver is slow. Do not use a single successful write call as proof that the receiver is fast enough. **Latency will surface once the buffering layers run out of space**.

### 3.2. Application Queues Are Outside Kernel Control

~~~text
Fast producer
    |
    +--> Unbounded LinkedBlockingQueue
    |        |
    |        +--> Writer blocks when TCP stops accepting bytes
    |        |
    |        +--> Heap retains millions of Message objects
    |
    +--> ExecutorService with an unbounded task queue
    |
    +--> CompletableFuture callbacks retaining payloads until send finishes
~~~

An application can OOM because producers run too fast **before TCP reports any error**. If many clients are slow at the same time, total resource usage can scale by number of clients × queue cap.

## 4. Simple Arithmetic: How Fast Does a Queue Fill Up?

Suppose:

~~~text
Production rate: 200 messages/s
Encoded size per message: 2 KiB
Receiver processing rate: 50 messages/s

Produced = 200 × 2 KiB = 400 KiB/s
Consumed =  50 × 2 KiB = 100 KiB/s
Net delta = 300 KiB/s

Queue limit = 3,000 KiB
Time from empty to full ≈ 3,000 / 300 = 10 seconds
~~~

This is an **approximation** assuming steady arrival/drain rates, excluding kernel buffers and object overhead. It proves that simply increasing the queue cap does not solve the root cause: if the sustained arrival rate is **greater than** the drain rate, the backlog still grows.

Let `λ` denote the arrival rate and `μ` the sustainable send/consumption rate. When `λ > μ` for long enough, the backlog grows. A finite queue cap turns overload **into an explicit decision** instead of unbounded heap growth.

**Oldest message age** also matters: a queue may still have room, but if a location update takes 30 seconds to be sent, that message may already be meaningless. Combine a **queue byte cap** with a **deadline/TTL**.

## 5. Safe Architecture: Producer → Bounded Queue → Single Writer

~~~text
Producer #1 -----+
Producer #2 -----+----> admission gate ----> bounded FIFO ----> one writer
Producer #3 -----+       | rate / byte cap                       |
                         |                                   encode frame
                         +-- rejected/throttled                 |
                                                              TCP/NIO
                                                                |
                                                        peer read/parse
~~~

**One writer owner per byte stream** helps:

1. Preserve the FIFO order of enqueued frames.
2. Prevent two threads from interleaving partial heads/tails of messages into the same stream.
3. Have a single place managing the current frame/`ByteBuffer.position`, write errors, and timeouts.
4. Reduce the risk of races between close, retry, cancellation, and byte-budget release.
5. Make it easy to measure queue drain rate, blocked write time, and in-flight bytes.

**This does not mean you need one OS thread per connection** when you have thousands of clients: you can use an NIO `Selector`/event loop, or an async networking framework, as long as ownership/ordering is clear.

### 5.1. Options When the Queue Is Full

| Policy | Purpose | Pitfalls |
| --- | --- | --- |
| Reject new immediately | Fail fast, caller knows it was not accepted | Caller needs a backoff/retry contract |
| `offer(msg, timeout, unit)` | Bounded wait for space | Do not block an event loop |
| `put(msg)` | Unbounded wait for internal backpressure pipelines | Easy to cause deadlocks/thread starvation |
| Drop newest | Shed load for lossy telemetry | Unsuitable for payments/audit |
| Drop oldest | Prioritize latest state | Loses history; do not use for logs requiring completeness |
| Coalesce by key | Merge updates, keep only latest state | Unsuitable for increment/transaction events |
| Disconnect slow peer | Isolate the backlog-causing client | Reconnect needs backoff and resync |
| Pause producer | Propagate backpressure upstream | Source must support demand control |
| Durable broker/disk queue | Persist data for replay | Quota, retention, latency, and operations |

A mouse cursor position message can be dropped/coalesced; a `createOrder` event must not be silently dropped. **Policy is part of the business contract, not just throughput tuning**.

### 5.2. `ArrayBlockingQueue` in Java

~~~java
ArrayBlockingQueue<byte[]> queue = new ArrayBlockingQueue<>(100);

boolean accepted = queue.offer(encodedMessage);
if (!accepted) {
    // Respond with overload/throttle/drop per the published contract.
}
~~~

This is a **code snippet** requiring the `encodedMessage` variable and `import java.util.concurrent.ArrayBlockingQueue`.

- `offer(e)` **does not wait**; it returns `false` when the queue is full.
- `put(e)` **waits** until space is available or the thread is interrupted.
- `offer(e, timeout, unit)` waits up to a limit; returns `false` on timeout.
- `take()` waits until the queue has an item; a worker thread can block, an event loop should not.
- `remainingCapacity()` and `size()` are only **snapshots**, racy if used as `if size<cap then offer`; always rely on the result of `offer`.
- FIFO applies to **enqueued** items; it does not automatically guarantee ordering by business timestamps across concurrent producers.
- Byte arrays or `ByteBuffer`s placed into the queue need clear ownership: producers **must not mutate the payload** before the writer finishes.

## 6. Java Demo #1: Bounded TCP Queue, Rejecting When Full

### 6.1. Verifiable Scenario

Set up a TCP server on `127.0.0.1` only, a sender using `ArrayBlockingQueue<Message>(2)`, and **a single writer thread**. The writer takes the first message and **waits on a `CountDownLatch`**. Meanwhile, the producer offers messages #2, #3, and #4.

- #1 enters the queue and is already taken by the writer: accepted.
- #2 and #3 fill the two slots: accepted.
- #4 is rejected: `queue.offer(...) == false`.
- When the latch is released, the writer sends all three frames in order.
- The receiver reads a **4-byte length prefix**, validates the max length, reads the exact payload, and prints IDs `[1, 2, 3]`.

**Scientific note:** the latch simulates a controlled slow writer path, making the test deterministic. It **does not prove the TCP receive window closed**. In practice, when a receiver reads slowly for a long time, TCP send buffers slow the writer via a similar mechanism, but a loopback test sending a few bytes will not easily observe that phenomenon.

### 6.2. File `BoundedOutboundQueueDemo.java`

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BoundedOutboundQueueDemo {
    record Message(int id, String content) {}

    public static void main(String[] args) throws Exception {
        ExecutorService readerWorker = Executors.newSingleThreadExecutor();
        ExecutorService writerWorker = Executors.newSingleThreadExecutor();

        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(5000);

            Future<List<Integer>> received = readerWorker.submit(() -> {
                try (Socket peer = server.accept()) {
                    peer.setSoTimeout(5000);
                    DataInputStream input =
                            new DataInputStream(peer.getInputStream());
                    List<Integer> ids = new ArrayList<>();
                    for (int i = 0; i < 3; i++) {
                        int length = input.readInt();
                        if (length < 1 || length > 128) {
                            throw new IOException("Invalid frame length");
                        }
                        byte[] data = input.readNBytes(length);
                        if (data.length != length) throw new EOFException();
                        String frame = new String(data, StandardCharsets.UTF_8);
                        ids.add(Integer.parseInt(
                                frame.substring(0, frame.indexOf('|'))));
                    }
                    return ids;
                }
            });

            try (Socket sender = new Socket(
                    InetAddress.getByName("127.0.0.1"),
                    server.getLocalPort())) {
                sender.setTcpNoDelay(true);
                ArrayBlockingQueue<Message> queue = new ArrayBlockingQueue<>(2);
                CountDownLatch firstSelected = new CountDownLatch(1);
                CountDownLatch releaseWriter = new CountDownLatch(1);

                Future<Integer> writing = writerWorker.submit(() -> {
                    DataOutputStream output =
                            new DataOutputStream(sender.getOutputStream());
                    int sent = 0;
                    for (int i = 0; i < 3; i++) {
                        Message message = queue.take();
                        if (i == 0) {
                            firstSelected.countDown();
                            if (!releaseWriter.await(5, TimeUnit.SECONDS)) {
                                throw new IOException("Writer gate expired");
                            }
                        }
                        byte[] payload = (message.id() + "|" + message.content())
                                .getBytes(StandardCharsets.UTF_8);
                        output.writeInt(payload.length);
                        output.write(payload);
                        output.flush();
                        sent++;
                    }
                    return sent;
                });

                System.out.println("Offer #1: " +
                        queue.offer(new Message(1, "alpha")));
                if (!firstSelected.await(5, TimeUnit.SECONDS)) {
                    throw new IOException("Writer did not start");
                }
                System.out.println("Offer #2: " +
                        queue.offer(new Message(2, "beta")));
                System.out.println("Offer #3: " +
                        queue.offer(new Message(3, "gamma")));
                System.out.println("Offer #4 with full queue: " +
                        queue.offer(new Message(4, "delta")));

                releaseWriter.countDown();
                System.out.println("Writer completed: " +
                        writing.get(5, TimeUnit.SECONDS));
                System.out.println("Receiver ids: " +
                        received.get(5, TimeUnit.SECONDS));
            }
        } finally {
            readerWorker.shutdownNow();
            writerWorker.shutdownNow();
        }
    }
}
~~~

Compile/run commands targeting Java 17 API:

~~~bash
javac --release 17 -encoding UTF-8 BoundedOutboundQueueDemo.java
java BoundedOutboundQueueDemo
~~~

**Verified stdout on JDK 24 with `javac --release 17`:**

~~~text
Offer #1: true
Offer #2: true
Offer #3: true
Offer #4 with full queue: false
Writer completed: 3
Receiver ids: [1, 2, 3]
~~~

### 6.3. In-Depth Program Explanation

- `ServerSocket(0, 1, loopback)` picks a free port and does not open an Internet listener; the test needs no external server.
- `firstSelected.await` ensures the writer has taken #1 from the queue before the producer offers #2/#3.
- `releaseWriter` holds the writer back, so the capacity-2 queue is guaranteed to fill up; #4 is rejected.
- Each frame consists of `DataOutputStream.writeInt(payload.length)` followed by the exact bytes. The receiver uses `readInt` + `readNBytes(length)`, never assuming each TCP read contains exactly one message.
- `Writer completed: 3` confirms the writer task performed three sends per the API; it does not conclude they were committed by the receiver's database.
- `Receiver ids` proves the **local receiver actually parsed** three frames, though there is no application ACK/transaction yet.
- `Future.get(5, TimeUnit.SECONDS)` is the test deadline; it does not block indefinitely.
- `try-with-resources` cleans up Socket/ServerSocket; `shutdownNow()` terminates the demo executors.

**This is a test fixture, not a production socket server:** it only receives three known short frames, parses based on `'|'`, and has no TLS, auth, global quota, message TTL, durable queue, retry, or full shutdown protocol. Do not replace the message content with untrusted network data and assume this parser is safe.

## 7. An Item Cap Alone Is Not Enough: You Need a Byte Budget

`ArrayBlockingQueue<>(100)` only caps **100 items**. If each item can hold 10 MiB, the payloads alone can reach roughly 1 GiB. You must account for at least:

~~~text
queued payload bytes        : frames still in the app queue
in-flight payload bytes     : current frame dequeued but write not yet finished
other user-space buffers    : HTTP/WebSocket library, serialization, retry...
TOTAL app outstanding       = sum of the above layers per policy
~~~

**Do not release the byte reservation immediately upon dequeue** if the writer still holds the payload and is blocked. If you have 10,000 clients and each client is allowed a 1 MiB backlog, theoretical max queued payload alone is about **10 GiB**, excluding overhead. You need **per-client budget + per-tenant budget + global cap**.

### 7.1. Byte-Budget Management Pattern

This is a **standalone conceptual snippet**, not yet integrated into a socket server; it protects reservations with `synchronized` and avoids addition overflow via subtraction comparison:

~~~java
final class ByteBudget {
    private final long maxBytes;
    private long reservedBytes;

    ByteBudget(long maxBytes) {
        if (maxBytes <= 0) throw new IllegalArgumentException();
        this.maxBytes = maxBytes;
    }

    synchronized boolean reserve(long bytes) {
        if (bytes < 0 || bytes > maxBytes) return false;
        if (reservedBytes > maxBytes - bytes) return false;
        reservedBytes += bytes;
        return true;
    }

    synchronized void release(long bytes) {
        if (bytes < 0 || bytes > reservedBytes) {
            throw new IllegalStateException("Invalid release");
        }
        reservedBytes -= bytes;
    }

    synchronized long outstandingBytes() {
        return reservedBytes;
    }
}
~~~

Integrating admission with both item and byte limits:

~~~java
int cost = encoded.length + Integer.BYTES; // payload + length prefix
if (!budget.reserve(cost)) {
    // Reject: byte budget is full.
} else if (!queue.offer(encoded)) {
    budget.release(cost); // Rollback if item queue is full.
} else {
    // Writer owns reservation until no longer retaining payload.
}
~~~

This snippet assumes `encoded`, `budget`, and `queue` are appropriately declared. Production code needs to guard **queue close, admission, and rollback** with a lifecycle owner/atomic state to avoid races with cancel/close. You must release exactly once across success, failure, and cancellation. If a single message exceeds the byte cap, **reject immediately**—do not enqueue a task that can never fit.

### 7.2. High/Low Watermarks and TTL

Use two thresholds to create **hysteresis**:

~~~text
0% ---------- 20% ---------------- 80% ------------ 100%
              ^                     ^
           RESUME upstream       PAUSE upstream
                                                    HARD CAP
~~~

If you only toggle on/off around 80%, the producer can oscillate continuously between pause and resume. In addition to a byte cap, you should have an **oldest message age limit**. For a dashboard that only needs the latest state, an item sitting for 10 seconds may already be worthless even if the queue is not full; coalesce/drop stale items under an explicit contract.

## 8. Rate Limiting: Token Bucket and Burst Limits

**Queue limit** answers “how much backlog can exist simultaneously?”. **Rate limit** answers “how many bytes/cost units are allowed per time interval?”. They solve two different problems.

A token bucket has:

- **Capacity B**: maximum tokens held; determines maximum burst.
- **Refill rate R**: tokens added per second; determines long-term rate.
- **Cost c**: tokens each message consumes, e.g., encoded bytes.
- **Monotonic time**: in production use `System.nanoTime()` to measure elapsed time; do not use wall clock for deadlines.

~~~text
capacity = 9 tokens; refill = 6 tokens/second

t=0:
  A cost4 -> true; 5 left
  B cost4 -> true; 1 left
  C cost2 -> false; still 1 left

t=0.5s: +3 tokens -> 4
  D cost3 -> true; 1 left

t=0.75s: +1.5 tokens -> 2.5
  E cost3 -> false

t=1.0s: +1.5 tokens -> 4
  F cost4 -> true; 0 left
  G cost1 -> false
~~~

If the rate unit is bytes, compute **`payload.getBytes(UTF_8).length` + framing** when needed. `String.length()` counts UTF-16 code units, not transmitted bytes. Even with accurate token accounting, an app-level limiter cannot promise exact physical TCP rates at every millisecond due to kernel buffering, TLS/HTTP framing, and OS scheduling.

### 8.1. Where to Place the Limiter?

| Placement | Benefit | Risk If Used Alone |
| --- | --- | --- |
| Before enqueue | Producer gets early signal, less backlog | Does not prevent unbounded slow writes if tokens keep refilling |
| Before socket write | Paces output rate | Queue can still fill up if producer is too fast |
| At consumer/app subscription | Reduces demand when processing is slow | Must ensure publisher actually respects demand |
| Per-user/per-tenant | Prevents one actor from monopolizing throughput | Still needs a global budget |
| Global output limiter | Protects service bandwidth | Must share fairly so one client cannot starve the whole system |

A real-world pipeline should have **admission gate + bounded queue + rate/pacing + expiry + failure policy**. Running out of tokens does not mean waiting forever; if a message's TTL expires while waiting, reject/drop per contract.

## 9. Java Demo #2: Deterministic Byte-Based Token Bucket

The following program **does not access the network** because its job is to verify the decision algorithm. It uses a simulated `nowNanos` clock and `synchronized allow` so that sharing a bucket has no race between refill and consume.

### 9.1. File `TokenBucketRateLimitDemo.java`

~~~java
public class TokenBucketRateLimitDemo {
    static final class TokenBucket {
        private final double capacityBytes;
        private final double rateBytesPerSecond;
        private double availableBytes;
        private long lastRefillNanos;

        TokenBucket(double capacityBytes, double rateBytesPerSecond,
                    long startingNanos) {
            if (capacityBytes <= 0 || rateBytesPerSecond <= 0) {
                throw new IllegalArgumentException("Positive limits required");
            }
            this.capacityBytes = capacityBytes;
            this.rateBytesPerSecond = rateBytesPerSecond;
            this.availableBytes = capacityBytes;
            this.lastRefillNanos = startingNanos;
        }

        synchronized boolean allow(int costBytes, long nowNanos) {
            if (costBytes < 0 || nowNanos < lastRefillNanos) {
                throw new IllegalArgumentException("Invalid cost or clock");
            }
            long elapsed = nowNanos - lastRefillNanos;
            availableBytes = Math.min(capacityBytes,
                    availableBytes + elapsed / 1_000_000_000.0
                            * rateBytesPerSecond);
            lastRefillNanos = nowNanos;
            if (costBytes > capacityBytes ||
                    availableBytes + 1e-12 < costBytes) {
                return false;
            }
            availableBytes -= costBytes;
            return true;
        }
    }

    public static void main(String[] args) {
        TokenBucket bucket = new TokenBucket(9.0, 6.0, 0);
        System.out.println("t=0 A(4): " + bucket.allow(4, 0));
        System.out.println("t=0 B(4): " + bucket.allow(4, 0));
        System.out.println("t=0 C(2): " + bucket.allow(2, 0));
        System.out.println("t=500ms D(3): " +
                bucket.allow(3, 500_000_000L));
        System.out.println("t=750ms E(3): " +
                bucket.allow(3, 750_000_000L));
        System.out.println("t=1000ms F(4): " +
                bucket.allow(4, 1_000_000_000L));
        System.out.println("t=1000ms G(1): " +
                bucket.allow(1, 1_000_000_000L));
    }
}
~~~

Commands:

~~~bash
javac --release 17 -encoding UTF-8 TokenBucketRateLimitDemo.java
java TokenBucketRateLimitDemo
~~~

**Verified stdout with OpenJDK 24 after compiling with `--release 17`:**

~~~text
t=0 A(4): true
t=0 B(4): true
t=0 C(2): false
t=500ms D(3): true
t=750ms E(3): false
t=1000ms F(4): true
t=1000ms G(1): false
~~~

### 9.2. Interpreting Results and Limitations

- After A/B, the bucket has only 1 token left; C (cost 2) is rejected.
- After 500 ms, 3 tokens are added; D (cost 3) is accepted.
- After the next 250 ms, only 1.5 tokens are added, so E (cost 3) is still rejected.
- After another 250 ms, the bucket has 4 tokens; F is accepted and G is rejected.
- `allow(...) == true` only **permits** work to proceed; it does not mean the socket sent it or the receiver ACKed it.
- If `costBytes > capacityBytes`, the message will never fit in the bucket; reject it or use a separate streaming path with a quota.

In production, use `System.nanoTime()` as the elapsed-time source, consider fixed-point math to avoid double precision drift at high throughput, and limit concurrency/token contention. This is a deterministic algorithm demo, not a bandwidth benchmark. **A rate limiter does not replace a byte cap**, because a receiver can stop reading completely while tokens continue to refill.

## 10. Coordinating Limiter, Byte Budget, Queue, Writer, and ACK

~~~text
Business producer
   |
   v
Serialize + validate max frame size + deadline
   |
   v
Token bucket / demand controller
   |
   v
Reserve byte budget (queued + in-flight)
   |
   v
Bounded queue.offer(frame)
   +------ fail ------> rollback budget, reject/throttle
   |
   v
Single writer → TCP/NIO → receiver parser
   |
   v
Local send completed → release user buffer reservation
   |
   v
Optional application ACK with messageId
   |
   v
Mark received/accepted/committed per explicit protocol
~~~

A sensible order:

1. **Encode an immutable payload** to know its size and prevent payload mutation after admission.
2. **Validate max frame size** and TTL before holding resources.
3. Check rate limit/demand per contract.
4. Reserve queue+in-flight byte budget and verify the connection is still active.
5. Attempt `queue.offer`. If it fails, roll back the reservation; do not mark the message “sent”.
6. Writer takes the frame, writes **until all bytes are sent**, preserving buffer position and accounting for errors.
7. Release the user-space byte reservation exactly once when no longer retaining the payload; **do not** treat this as a business ACK.
8. If business confirmation is needed, use a message ID and a separate ACK, with a cap on **unacked outstanding** messages.
9. If the connection drops, classify queued/in-flight/unknown outcomes per contract; do not blindly retry side effects.

**Note on token refunds:** if tokens rate-limit **attempts**, a full queue does not necessarily refund tokens; if tokens only count **accepted messages**, you can design atomic reserve/rollback. This is a semantics decision that must be documented to avoid “losing tokens” or miscounting.

### 10.1. Hidden Queues to Control

Beyond the `ArrayBlockingQueue` you create, there may also be:

- The executor task queue of an `ExecutorService`.
- Callbacks and `CompletableFuture` chains retaining payloads.
- Outbound buffers of HTTP/WebSocket libraries.
- Retry queues, dead-letter queues, disk staging.
- Per-tenant fanout buffers or actor mailboxes.
- Async logging/metrics pipelines.

**Capping only the main queue is not enough** if other queues have no cap or timeout. Sum outstanding bytes across all places the application controls.

## 11. Blocking TCP: Commonly Confused Timeouts

### 11.1. `SO_TIMEOUT` Applies to Reads, Not Writes

With classic `Socket`:

~~~java
socket.setSoTimeout(5000); // timeout for blocking input read
socket.getOutputStream().write(payload); // NOT guaranteed to have a 5s write timeout
~~~

This snippet assumes `socket` and `payload` are initialized. Java's `Socket.setSoTimeout` sets the timeout for `read()` on the socket's `InputStream`. It **does not automatically set a deadline** for `OutputStream.write()`. If the receiver stops reading, a blocking write can hang indefinitely.

To handle write deadlines, consider **nonblocking `SocketChannel` + `Selector`** or a networking framework with corresponding send/cancel/timeout support; you can close the connection when there is no progress. Do not treat calling `Thread.interrupt()` as a safe guarantee that a classic `Socket` `OutputStream` write will always be interrupted immediately on every JDK/OS.

### 11.2. `SO_SNDBUF` and `TCP_NODELAY` Do Not Cure Backlog

- `Socket.setSendBufferSize`/`SO_SNDBUF` is a hint for the kernel send buffer size, subject to OS policy; it is not an app byte budget.
- Increasing the send buffer can **delay** when a write blocks, but it also hides a slow consumer for longer.
- `setTcpNoDelay(true)` can reduce Nagle's algorithm impact for some small messages; it **does not make the receiver process faster**.
- `Socket.isConnected()` is not a current liveness/throughput check for the receiver.
- A TCP ACK is not an app-level ACK; do not replace protocol idempotency with socket options.

### 11.3. Framing Is Mandatory Because TCP Is a Byte Stream

Two `OutputStream.write` calls do not guarantee the receiver gets two `InputStream.read` calls of the same sizes. One frame may be split across multiple reads, or multiple frames may be coalesced into one read.

Length-prefix example:

~~~text
4-byte big-endian length | N bytes payload
+-----------------------+--------------------------+
| uint32 payload length | payload N bytes          |
+-----------------------+--------------------------+
~~~

The receiver must read the full prefix, **validate 0 ≤ length ≤ MAX_FRAME_BYTES before allocating**, then read **exactly N bytes** and check for EOF. Demo #1 uses `DataOutputStream.writeInt`, `DataInputStream.readInt`, `readNBytes`, and a max frame of 128 bytes.

Do not use `InputStream.available()` to determine message completeness; it only indicates bytes that can be read immediately without blocking per the stream contract.

## 12. NIO SocketChannel: Partial Writes, `write(0)`, and `OP_WRITE`

Nonblocking `SocketChannel.write(ByteBuffer)` can return a positive number **smaller than** the remaining bytes, or **0** when the kernel socket buffer has no space left. When writing, `ByteBuffer.position` advances by the exact number of bytes written.

~~~java
SocketChannel channel = SocketChannel.open();
channel.configureBlocking(false);
// ... connect/finishConnect and register with Selector before writing ...

ByteBuffer frame = ...; // immutable/owned by single writer.
int n = channel.write(frame);
if (n == 0 && frame.hasRemaining()) {
    // Cannot write more yet: wait for OP_WRITE instead of spinning CPU.
}
~~~

This is an **incomplete code snippet** lacking the connection/selector lifecycle, not a standalone program; it requires importing `java.nio.ByteBuffer` and `java.nio.channels.SocketChannel`. Do not call `frame.clear()` or discard the frame after a write while `hasRemaining()` is still true.

### 12.1. Enable `OP_WRITE` Only When Bytes Are Pending

~~~text
Outbound queue empty and current frame finished:
    disable OP_WRITE (avoid continuous selector wakeups).

Producer enqueues frame:
    notify owner selector, wakeup if needed;
    enable OP_WRITE or attempt write on owner thread.

Selector key.isWritable():
    write current ByteBuffer as many bytes as possible;
    if frame still has remaining, keep position and wait again;
    if frame is finished, take next frame;
    if no frames remain, DISABLE OP_WRITE.

write() returns 0:
    do not spin while(true), return to Selector.select().
~~~

Many sockets are always **writable** whenever the OS send buffer has space. If you leave `OP_WRITE` enabled with no pending data, the selector can wake up continuously, burning CPU (**busy-spin**).

Interest-bits snippet:

~~~java
int flags = key.interestOps();
key.interestOps(flags | SelectionKey.OP_WRITE); // When there are pending bytes.

// ... after draining completely ...
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
~~~

This **snippet** runs on the selector owner thread with a valid `SelectionKey key`. If producers are on other threads, use a thread-safe queue, `selector.wakeup()`, and coordinate interestOps/state safely. A complete server must handle `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, cancellation, EOF, and errors. Do not treat `write==0` as a sign that the receiver is dead; it is transient backpressure.

## 13. Reactive Flow, WebSocket, and HTTP Do Not Share the Same Backpressure Layer

`Flow.Subscription.request(n)` in Java Reactive Streams is **demand in number of items** from subscriber to publisher. It does not directly set the TCP receive window; a single item can carry a large payload, so a byte budget is still needed.

With `java.net.http.WebSocket.Listener`, `WebSocket.request(n)` grants demand for **receive callbacks**. It does not directly bound the **outbound** app queue when calling `sendText`. A completed `sendText(...)` future does not prove the remote business consumer committed the event.

~~~java
@Override
public CompletionStage<?> onText(
        WebSocket webSocket, CharSequence data, boolean last) {
    // Process/grant more demand matching consumer capacity.
    webSocket.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

This is a **method snippet in `WebSocket.Listener`**, importing `CompletionStage` and `CompletableFuture`; WebSocket text messages can be fragmented, so `last` indicates the message boundary. Do not request unbounded demand when downstream lacks capacity.

HTTP/2 has **stream-level flow control** alongside TCP flow control, yet an app layer still needs admission/queue limits. Even with reactive demand, if the source runs on another thread and keeps producing data regardless of demand, you can still build an unbounded queue.

## 14. ACK, Retry, and Idempotency When a Connection Drops

~~~text
Sender                         Receiver
  |-- event ID=44 ------------->|
  |                              | committed business operation
  |<--- ACK ID=44 --------------X| ACK lost when network drops
  |
  | timeout; outcome at sender is UNKNOWN
  | retrying ID=44 if receiver does not dedupe → may create duplicate data.
~~~

Distinguish confirmation levels:

- **QUEUED**: message is waiting at the sender.
- **WRITTEN**: send operation completed per the API.
- **RECEIVED**: peer parser received the full message (if a protocol ACK exists).
- **ACCEPTED**: server accepted responsibility for processing.
- **COMMITTED**: transaction/durable log persisted successfully per contract.

If processing payments/orders, **do not retry blindly** after a write timeout or connection close; the request may have been processed and only the response was lost. Use message IDs, idempotency keys, deduplication, bounded retries, and status-check mechanisms. For lossy telemetry, you can use a latest-state snapshot instead of replaying every old message.

### 14.1. Phase-by-Phase Deadlines

| Deadline | What Slowness It Measures |
| --- | --- |
| Enqueue deadline | Whether the producer is admitted to the queue in time |
| Queue TTL | Whether the message expires before being sent |
| Write deadline | Whether the user-space sender makes progress or is blocked |
| Heartbeat timeout | Whether the peer/network shows signs of unresponsiveness |
| App ACK deadline | Whether the business protocol confirms the message in time |
| End-to-end deadline | Whether the caller received the business result within SLO |

Use `System.nanoTime()`/elapsed time for deadlines, not `currentTimeMillis()` as a monotonic clock. Slowness in one phase does not automatically prove slowness in other phases.

## 15. Choosing a Policy by Data Type

| Data Type | When Receiver Is Slow |
| --- | --- |
| Sensor position / UI presence | Coalesce latest-value by key; drop stale data per contract |
| Chat with history | Durable store/replay, bounded live queue, resync after reconnect |
| Payment / order | Do not silently drop; idempotency + committed ACK |
| Lossy telemetry | Bounded queue, sampling/drop counters, prioritize keeping service alive |
| Video/live frames | Prioritize new frames, drop expired frames |
| File transfer | Streaming/credit window/checksum, limit concurrent sessions |
| API gateway | Admission control, short queue with deadline, HTTP 429/503 per policy |
| WebSocket broadcaster | **Per-client** byte budget; slow-client disconnect/resync |
| Audit/event sourcing | Durable broker/retention quota, monitor consumer lag |

Do not let **one slow client** block a global broadcaster. Conversely, do not drop audit/payment events as if they were just UI state updates.

### 15.1. Fairness and System-Wide Limits

Beyond a per-client queue cap, you should have:

- Per-user/tenant quota, because one user can open multiple connections.
- Global bytes cap, counting queued/in-flight/app futures.
- Max single message/frame size.
- Max oldest age or deadline per event type.
- Per-client rate, global rate, and burst limits.
- Fair scheduling, such as round-robin by byte budget per connection.
- Bounded retry queue/backoff+jitter on reconnect.
- Metrics and alerts to know how much was rejected/dropped.

## 16. Observability and Diagnostics

| Metric | Meaning | Purpose |
| --- | --- | --- |
| `outbound_queue_items` | Number of waiting items | Fullness alert |
| `outbound_queue_bytes` | Queued bytes | Memory alert |
| `outbound_inflight_bytes` | Bytes held by writer | Avoid illusory caps |
| `outbound_oldest_age_ms` | Age of oldest item | Detect stale data |
| `outbound_offer_rejected_total` | Total admission failures | Observe load shedding |
| `outbound_drop_total` | Total intentional drops | Track data loss |
| `writer_blocked_ms` | Time spent waiting to write | Transport/receiver congestion |
| `writer_bytes_per_sec` | Actual write throughput | Compare against producer arrival rate |
| `write_zero_returns_total` | Nonblocking writes returning 0 | Send buffer unavailable |
| `selector_op_write_wakeups` | `OP_WRITE` wakeups | Detect busy-spin |
| `unacked_messages` | Missing app ACK | Unknown outcome risk |
| `application_ack_latency_ms` | Business ACK latency | Slow receiver consumer/DB |
| `slow_consumer_disconnect_total` | Connections closed due to backlog | Policy sensitivity |

**Do not log raw payloads, tokens, passwords, or message IDs into high-cardinality metric labels**. Aggregate by tenant/region/connection class and collect p95/p99 histograms.

### 16.1. Distinguishing Bottlenecks

| Observation | Likely Cause | What to Check |
| --- | --- | --- |
| Queue grows, write time rises, TCP send queue high | Receiver not reading or network congested | Receiver read rate, advertised window, retransmissions |
| Queue grows, write time low | Producer/encoding/scheduling imbalance | Writer capacity, hidden task queues |
| Queue empty but app ACK slow | Business worker/DB slow | Consumer queue/transaction latency |
| `write() == 0` continuously and high CPU | NIO busy-spin | `OP_WRITE` toggle, Selector readiness |
| Heap grows while queue size is small | Large payloads/in-flight/Futures | Byte budgeting, buffer copies |
| Only one client has high backlog | Per-client slow receiver | Isolate/disconnect/resync |
| All clients have high backlog | Systemic overload | Global cap, upstream rate, server health |
| Simultaneous reconnects after timeout | Thundering herd | Exponential backoff+jitter |

## 17. Common Programming Mistakes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Unbounded queue because TCP is reliable | TCP does not bound app heap | Bounded queue, byte cap |
| Capping only item count | A large item can hold MiBs | Byte budget and max frame |
| Releasing budget immediately on dequeue | In-flight payload is still retained | Count queued + in-flight |
| Calling `put()` on an event loop | Can block all clients | `offer()` / nonblocking admission |
| Spawning a new thread per message | Too many threads | One writer / bounded executor |
| Two threads writing to the same TCP stream | Frame bytes interleave | Serialize writes |
| Assuming one write = one read | TCP has no message boundaries | Length-prefixed framing |
| Sending unvalidated length | Peer can trigger huge allocations | Max frame cap before allocate |
| Thinking `setSoTimeout` is a write timeout | Bounds reads, not writes | Write deadline/cancel |
| Using large `SO_SNDBUF` to “fix” it | Only delays pressure | Throttle upstream/app |
| Calling `SocketChannel.write` once | Partial/0 writes occur | Preserve buffer position |
| Leaving `OP_WRITE` enabled continuously | Selector busy-spin | Enable only when pending |
| `while(write()==0){}` loop | Wastes CPU | Wait for writable readiness |
| Mutating `ByteBuffer` after enqueue | Data race/corruption | Immutable/ownership |
| Rate-limiting only, unbounded queue | Receiver can stop completely | Combine token bucket + cap |
| Releasing byte budget twice | Underflow/overadmission | Once-only lifecycle |
| Not releasing on cancel/reject | Memory quota leak | `finally`/rollback |
| Silently dropping orders/audits | Business data loss | Durable queue/ACK |
| Treating socket write as an ACK | Does not prove receiver parsed it | App protocol ACK |
| Unconditional POST retry | Duplicate side effects | Idempotency |
| One slow client blocks all fanout | No isolation | Per-client cap/fairness |
| Simultaneous reconnects | New overload spike | Backoff + jitter |
| Not measuring oldest age | Queue has space but data is stale | TTL/SLO |

## 18. Recommended Test Matrix

| Test | Setup | Expectation |
| --- | --- | --- |
| Queue capacity 2 | Writer pauses after dequeue #1 | #2/#3 accepted, #4 rejected |
| Unblock writer | Release latch | Receiver gets IDs [1,2,3] |
| Slow receiver | Staging test stops reading socket | Writer slows, queue stays bounded |
| Large frames | Item larger than byte cap | Rejected early |
| Variable-size items | One small item, one large item | Byte budget differs from item budget |
| In-flight accounting | Writer dequeues but has not written | Reservation not released yet |
| Producer concurrency | N producers offering concurrently | No double-release/overwrite |
| TCP frame fragmentation | Split frame across multiple reads | Decoder still works |
| Invalid length prefix | Negative or oversized length | No unbounded allocation |
| Token bucket burst | Capacity 9, rate 6/s | A/B true, C false |
| Token refill | Simulated clock | Matches demo #2 stdout |
| Clock goes backwards | `nowNanos` smaller than previous | Reject/validate |
| NIO write 0 | Socket buffer unavailable | No busy-spin |
| Partial write | One frame needs multiple writes | Preserves `ByteBuffer` position |
| No pending bytes | Selector idle | `OP_WRITE` disabled |
| Cancel in-flight | Close connection while write pending | Marked failed, released once |
| Stale message | TTL expired | Dropped/rejected per contract |
| ACK loss | Receiver commits but ACK is lost | Idempotency, no blind retry |
| One slow among many | Broadcaster with many subscribers | Other clients still served |
| Global overload | All clients slow | Global cap and fair shedding |
| Reconnect storm | N clients timeout together | Backoff+jitter reduces spike |

Do not use public networks or unauthorized servers to intentionally flood/blackhole data. Use localhost or bounded staging environments.

## 19. Review Questions and Answers

### 19.1. Why Doesn't TCP Flow Control Save the App Queue?

Because TCP only controls bytes in the transport layer; it does not manage the number of tasks, messages, retry jobs, and user-space buffers the application creates. Bounded admission/backpressure is required.

### 19.2. What Does `ArrayBlockingQueue.offer()` Returning `false` Mean?

The message **was not enqueued**. The caller must handle reject/drop/pause per contract and must not mark the message as sent.

### 19.3. Why Is `put()` on a Full Queue Dangerous Inside an Event Loop?

It can block indefinitely and let one slow client stall all event-loop connections. Use nonblocking `offer`/demand control.

### 19.4. Queue of 100 Items, Each Up to 5 MiB; Maximum Payload?

About 500 MiB **before object overhead**, so an item cap alone is not enough.

### 19.5. Writer Took a 20 MiB Payload but Hasn't Finished Writing; Release Byte Budget Immediately?

No, if the writer still holds the payload. The reservation must cover in-flight memory and be released exactly once after ownership actually ends.

### 19.6. Token Bucket 9 Tokens, Refill 6/s, A and B Each Cost 4 at t=0; Does C (Cost 2) Pass?

No: after A/B, 1 token remains; C is rejected. At t=0.5s the bucket refills 3 tokens so a request of cost 3 can be accepted.

### 19.7. Does a Rate Limit Replace a Queue Cap?

No. A rate limiter caps the average admission/send rate, whereas a receiver can stop reading completely; a queue/backlog bound is still required.

### 19.8. Why Doesn't `setSoTimeout(2000)` Guarantee a Write Fails After 2s?

Because `SO_TIMEOUT` is for **blocking `InputStream` reads**, not an `OutputStream` write deadline.

### 19.9. `SocketChannel.write(buffer)` Returns 0; What Should You Do?

Keep the buffer, wait for `OP_WRITE`, and do not spin in a loop. When there are no pending frames, disable `OP_WRITE` to avoid CPU spikes.

### 19.10. Does a Successful `OutputStream.write` Prove an Order Committed on the Server?

No. Knowing a commit occurred requires a business ACK/transaction result; retries also require idempotency to avoid duplicates.

### 19.11. A Broadcaster Has 10,000 Clients, Each with a 1 MiB Queue Cap; Does It Only Need 1 GiB RAM?

No. Theoretical queued payload alone reaches about **10 GiB**, excluding in-flight data, kernel buffers, TLS, futures, and threads. A global cap is needed.

### 19.12. Should Latest-State Telemetry Replay All Stale Messages After Reconnect?

Not necessarily; if the contract only needs the latest state, coalesce and send the latest snapshot instead of thousands of outdated updates.

## 20. Code Review Checklist

- [ ] Outbound has **item cap, byte cap, max frame size, oldest-age/TTL**.
- [ ] Both queued and in-flight payloads count toward the memory budget.
- [ ] There is **one writer owner** or single event-loop owner per connection.
- [ ] Event loop is never blocked by `put()` or unbounded `Future.get()`.
- [ ] When the queue is full, there is an explicit reject/drop/coalesce/pause/disconnect policy.
- [ ] Data requiring durable delivery is never silently dropped.
- [ ] Producers do not mutate payloads/`ByteBuffer`s after enqueue.
- [ ] TCP message framing has a bounded decoder.
- [ ] Enqueue, local write, peer read, app ACK, and committed ACK are distinguished.
- [ ] `Socket.setSoTimeout` is not treated as a write timeout.
- [ ] With NIO, `ByteBuffer` position is preserved across partial writes and `write=0` is handled.
- [ ] `OP_WRITE` is enabled only when bytes are pending and disabled once the queue drains.
- [ ] There is a rate limiter based on encoded bytes or business cost, with a burst cap.
- [ ] Rate limiter **does not** replace a bounded queue.
- [ ] Per-client, per-tenant, and global memory/rate budgets exist.
- [ ] Fair scheduling is used so one slow client cannot block the broadcaster.
- [ ] Monotonic elapsed time is used for deadlines/refill.
- [ ] Bounded retries, backoff+jitter, and idempotency are used where needed.
- [ ] Metrics exist for queue bytes/age, write duration, reject/drop, and ACK RTT.
- [ ] Tests cover slow writer/slow receiver, partial writes, cancellation, and queue overflow.
- [ ] Demo snippets are not used as a production TCP protocol/server without adding TLS/auth/security.

## 21. Official Documentation

- [Java SE 17 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO, `offer/put/take`.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): blocking and nonblocking insertion strategies.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `SO_TIMEOUT`, `SO_SNDBUF`, `TCP_NODELAY`.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): partial writes, nonblocking write can return 0.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `OP_WRITE`, `interestOps`.
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): nonblocking multiplexing and `wakeup`.
- [Java SE 17 — DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html): `writeInt` for frame length prefix.
- [Java SE 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt` and byte parsing.
- [Java SE 17 — Flow](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html): reactive backpressure, `request(n)`.
- [Java SE 17 — WebSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html): send futures, receive demand, close semantics.
- [Java SE 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed-time clock.
- [RFC 9293 — TCP](https://www.rfc-editor.org/rfc/rfc9293): reliable byte stream, receiver window, and flow control.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): stream-level flow control.

**Summary:** a slow receiver pushes backpressure up to TCP, but **does not automatically prevent an app from building an unbounded backlog**. Practical reliability requires a **bounded outbound queue by items and bytes**, owned writer/framing, a rate limiter, an explicit overload policy, deadlines, observability, and application ACK/idempotency when business logic demands it. Do not confuse **queued**, **written to socket**, with **processed and committed by the receiver**.
