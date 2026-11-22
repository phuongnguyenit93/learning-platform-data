# Time Budgets for Overall Requests, Individual Operations, and Idle Time in Java Networking

## 1. Why can a request still hang even when timeouts are configured?

A Java service calls an external API. The development team sets `connectTimeout(2 seconds)` and assumes every request will finish within 2 seconds. In reality, the TCP connection may be established in just 50 ms, but the server is slow to return headers, continues sending the response body byte by byte, or the application spends time parsing/reconciling and retrying. **Connect timeout is not the total duration of a request.**

The opposite mistake: setting `Socket.setSoTimeout(500)` and concluding that a file download will be canceled if it exceeds 500 ms. If the server continuously sends more bytes at intervals under 500 ms, each `read()` call can succeed, yet the entire file takes minutes. **Read timeout/idle timeout is not an overall deadline.**

Three concepts need to be clearly **defined and coordinated**:

1. **End-to-end deadline / overall request budget:** a time limit that **is not reset** across DNS, connect, TLS handshake, sending, receiving, parsing, cache lookup, retry, backoff, or calling downstream services. It protects the caller's experience/SLA.
2. **Per-operation timeout / operation budget:** a limit for **a specific activity**, such as establishing a new connection, sending an HTTP attempt, waiting for a socket read, or calling a dependency. It detects bottlenecks at a single stage.
3. **Idle timeout / idle budget:** a limit on the period **without defined activity or progress**. In Java 17's `Socket.setSoTimeout`, the specific case is limiting the time **waiting for data in each `InputStream.read()` call**. In streaming applications, you can set your own idle budget measured from the most recent **meaningful progress** received.

These three limits **cannot replace each other**. A reliable system needs to coordinate them, choose the shortest effective limit at each step, and still maintain an overall deadline across retries.

### After this lesson, what will you be able to do?

- Define and calculate the remaining time budget using `System.nanoTime()`/a monotonic clock instead of relying on `Instant.now()` for elapsed duration.
- Understand `Socket.connect(endpoint, timeout)`, `Socket.setSoTimeout`, `URLConnection.setReadTimeout`, `HttpClient.Builder.connectTimeout`, and `HttpRequest.Builder.timeout` in JDK 17.
- Cap timeouts for individual operations by the **remaining deadline**, avoiding setting a new timeout longer than the remaining budget.
- Distinguish between request timeout, HTTP response wait time, read idle, long-lived streams, connection pool idle, and application heartbeats.
- Design retries with backoff/jitter, cancellation, cleanup, and unknown outcome statuses when requests have side effects.
- Run **two tested Java 17 examples**: deterministic time simulation and TCP loopback proving `SO_TIMEOUT` only bounds a blocking read.

## 2. Comparison table of time limit types

| Limit type | Where does it start? | Termination / threshold condition | Does it reset on new data? |
|---|---|---|---|
| **Overall deadline** | Start of the **logical request** or caller-provided deadline | Total elapsed time exceeds the budget, including attempts/retries | **No** |
| **Connect timeout** | When performing establishment of a new connection | Connection is not established within the limit | No; each new connect is a separate operation |
| **Per-request/attempt timeout** | Start of **one HTTP attempt** per API | Response does not arrive within the configured interval per API contract | Not due to body chunks (do not assume it acts as idle) |
| **Read timeout (`SO_TIMEOUT`)** | Upon entering **one blocking `read()`** on a Socket | That read receives no data within the limit | A new `read()` gets its own window |
| **Application read-idle timeout** | From start of waiting or from the latest meaningful progress | No **defined** bytes/frames/records within an interval | **Yes**, when progress meets criteria |
| **Write/stall timeout** | When starting a send operation or when no write progress occurs | Sending is blocked/stalled for too long | Depends on the implemented I/O/streaming layer |
| **Connection-pool idle timeout** | Connection sits idle, not serving a request | Close/evict connection from pool per policy | This is **pool lifecycle**, not response idle |
| **Retry backoff budget** | After a failed attempt when deciding to retry | Wait time + next attempt must not exceed overall deadline | Does not reset the overall deadline |
| **Business processing deadline** | Start of business request or from upstream | End-to-end work is not completed on time | Does not reset just because the HTTP call succeeded |

It is necessary to distinguish **deadline (the ending timestamp)** from **timeout (the allowed duration for an action)**:

- A deadline can be expressed as `t_end` on a monotonic clock.
- A timeout is a `duration` interval passed into an API.
- At the start of an operation, compute `remaining = max(0, deadline - now)` and set `operationTimeout = min(perOperationLimit, remaining)`.
- After any stage, re-measure `remaining`; do not reuse the full timeout planned at the start of the workflow.

### Calculation error example

A request has a total budget of 2 seconds. You configure `connectTimeout(2s)`, `readTimeout(2s)`, three retries, each with a 1-second backoff. If each stage is granted a **fresh 2 seconds**, the entire chain can stretch far beyond 2 seconds. **Separate timeouts do not automatically add up to an overall deadline.**

## 3. End-to-end: a request has more stages than just connecting

In an HTTP/HTTPS call, the stages can include:

```text
T0: caller starts logical request / creates overall deadline
 |
 +-- Wait in queue, rate limiter, connection-pool slot
 +-- Prepare body / serializing
 +-- DNS / proxy selection
 +-- TCP connect (if not reusing a connection)
 +-- TLS handshake (if HTTPS)
 +-- Send request headers and body
 +-- Wait for server processing, receive response headers / time-to-first-byte
 +-- Read response body or stream
 +-- Parse, validate, record/cache, business processing
 +-- Possible retry after failure and backoff
 |
T_done or overall deadline expires
```

Which stages **are** covered by an API timeout is an API and implementation detail. For example, `HttpClient.Builder.connectTimeout` applies when **a new connection needs to be created**; if the client **reuses** an existing connection, this option **has no effect** on that request. `HttpRequest.Builder.timeout` controls the time to receive a response per the JDK 17 contract, not a standalone policy to manage an entire multi-attempt workflow or all streaming resources in the application.

Consequences:

- **Do not configure only connect timeout.** An already-open connection can still hang waiting for a response.
- **Do not configure only per-read timeout.** A server sending small amounts of data steadily can evade read timeouts while total time grows unbounded.
- **Do not configure an overall deadline only on paper.** If the code does not check remaining budget and has no way to cancel/close blocking I/O, the thread can still wait past the deadline.
- **Do not count only network time.** Serialization, queuing, backoff, parsing, retries, and writing data all consume the total budget.

A good overall deadline is a **contract between caller and callee** on completion time, not a standalone number of seconds for the TCP stack.

## 4. Measuring time correctly: monotonic clock instead of wall clock

A deadline is typically implemented via:

```java
// Illustrative snippet: moderate total budget, not too large to overflow toNanos().
long started = System.nanoTime();
long allowed = Duration.ofSeconds(3).toNanos();

long elapsed = System.nanoTime() - started;
long remaining = Math.max(0L, allowed - elapsed);

if (remaining <= 0) {
    // Reject starting a new stage, cancel/clean up ongoing work.
}
```

**Why use `System.nanoTime()`?**

- It is used to measure **elapsed time**; it does not represent calendar time visible to users.
- Wall clocks such as `Instant.now()`/`System.currentTimeMillis()` can be adjusted by time synchronization or administrative changes. If a wall clock is used to measure timeouts, clock jumps can cause deadlines to fire inaccurately.
- The difference `nanoTime() - started` is the appropriate basis for intervals; Java documentation notes that when directly adding to a deadline timestamp, you must be careful of **overflow**, especially when measuring very long intervals.

**Do not compare `System.nanoTime()` with a Unix timestamp or `Instant`.** The two kinds of time serve two purposes: `Instant` for recording audits/schedules in UTC, and `nanoTime` for measuring durations within a process.

### Beware of overflow and units

`Duration.toNanos()` can throw `ArithmeticException` if the duration is too large; Java `long` has limits. For practical timeout configurations in milliseconds/seconds, the risk is small, but production libraries should still validate inputs. Do not write:

```java
int millis = (int) remainingNanos / 1_000_000;
```

because casting to `int` **before division** can overflow; division must happen first, and then clamp to the API's capacity:

```java
long remainingMillis =
        TimeUnit.NANOSECONDS.toMillis(remainingNanos);
```

With `Socket.setSoTimeout(int)`, **0 milliseconds means infinite**. If less than 1 ms remains, integer division rounds down to 0; **do not accidentally pass 0**, as that can **disable the timeout**. You can fail fast when less than a full unit remains, or use a minimum positive value paired with an independent overall deadline mechanism, depending on precision requirements.

### Relative deadlines differ from absolute timestamps passed across services

Do not pass raw `System.nanoTime()` values from machine A to machine B: the nanosecond origin is not synchronized between two processes/machines. When propagating deadlines over RPC, applications typically pass a **remaining budget** decremented over time or an absolute wall-clock timestamp accounting for clock skew, latency, and synchronization policy; the receiver builds a **local monotonic deadline**. Do not add "re-initialization" time that gives downstream a larger budget than the caller actually has.

## 5. Allocating budgets per operation

A common model:

```text
Total remaining     = 950 ms
Per-connect limit   = 300 ms
Per-read-operation  = 400 ms
Read-idle remaining = 250 ms

New connect operation: timeout = min(950, 300) = 300 ms
Read operation:        timeout = min(950, 400, 250) = 250 ms
```

After connect actually takes 180 ms, **total remaining drops to 770 ms** (assuming no other overhead). When starting to read, you must recalculate. If an earlier stage has exhausted the budget, do not open a new request just to "try one more time."

### A budget is not a quota that must be spent

`connectTimeout(300ms)` is a **limit**, not a command to wait a full 300 ms. If the connection succeeds after 30 ms, the remaining time still belongs to the overall deadline. Conversely, the connection can fail immediately after 5 ms with `ConnectException`; a timeout does not guarantee that every failure waits until the threshold.

### Each stage has its own technical budget

| Stage | Example limit | Interpretation |
|---|---:|---|
| Waiting for pool slot | 100 ms | Limits queue / resource wait time |
| TCP connect | 300 ms | Limits establishing a new connection |
| Socket read | 250 ms | Limits **one** blocking read when no data arrives |
| One HTTP attempt | 700 ms | Limits the request per API/client |
| JSON parsing | 150 ms | Application CPU/worker limit, usually requires cooperative cancellation |
| Overall request | 1,200 ms | Must not exceed the sum of all stages and retries |

These values are **illustrative examples only**: actual numbers must be based on latency distribution, service-level objectives, expected payload size, network path, number of downstream calls, and fail/retry cost.

### Parallel budgets differ from sequential budgets

For two downstream calls running **in parallel**, the total time is usually close to the **max** of the two branches plus overhead, not their simple sum. However, both branches must share the same overall deadline and both must be canceled/cleaned up when the caller no longer needs the result. For a **sequential** chain, each stage consumes part of the budget before the next stage begins.

## 6. Idle timeout: defining "progress" is what matters

Idle timeout has at least **three different meanings** in networking:

1. **Socket read idle:** `Socket.setSoTimeout(ms)` limits how long **one `InputStream.read()` call waits for data**. If the read succeeds and the code calls `read()` again, the new call gets a fresh wait window. When expired, it throws `SocketTimeoutException`, but the socket **remains valid** per contract.
2. **Application stream idle:** the receiver tracks the latest timestamp of **meaningful progress** such as receiving bytes, frames, or a complete business record. When too much time passes without progress, the request/stream is canceled. What counts as "progress" is defined by the protocol and application.
3. **Keep-alive/pool idle:** a connection remains open but **is not serving a request** and is closed by the pool after an idle period. This is a connection reuse policy, **not** a response read timeout for an active request.

### A "slow drip" server fools idle timeouts

Suppose the idle limit is 250 ms; the server sends 1 byte every 180 ms:

```text
t=0 ms     start reading
t=180 ms   1 byte arrives -> reset idle
t=360 ms   1 byte arrives -> reset idle
t=540 ms   1 byte arrives -> reset idle
...
```

**No silent gap exceeds 250 ms**, yet a request with an **overall deadline of 500 ms** has already expired at t=540 ms. This is why **both an idle window and an overall deadline** are needed. When designing streams that may intentionally last for hours, clearly decide whether the **overall request deadline** applies to each logical operation, each session, or only invariant phases, rather than blindly applying 500 ms to every long-lived session.

### Byte-level progress is not necessarily business progress

If a server sends whitespace steadily without ever completing a JSON object, that may be **byte progress** but not **message progress**. For an event stream, valid heartbeats can keep a session alive without completing the job. Define:

- `lastByteAt`: the last time a valid byte was read.
- `lastFrameAt`: the last time a valid protocol frame was received.
- `lastBusinessProgressAt`: the last time a meaningful record/chunk was completed.
- The overall session/operation deadline still **does not reset** on those markers.

Do not rely solely on socket read timeouts to defend against slowloris/slow-drip; you need minimum throughput, max size, protocol deadlines, or an appropriate application progress policy.

## 7. Java 17: semantics of timeout APIs you commonly encounter

| Java API | Specific scope | When threshold is reached |
|---|---|---|
| `Socket.connect(SocketAddress, int timeout)` | One TCP connection open, positive ms | `SocketTimeoutException` on expiration; other errors may occur earlier |
| `Socket.setSoTimeout(int ms)` | One blocking `InputStream.read()` waiting for data | `SocketTimeoutException`; socket is not automatically closed by read timeout |
| `ServerSocket.setSoTimeout(int ms)` | One blocking `accept()` waiting for a client | `SocketTimeoutException`; listening socket remains valid |
| `URLConnection.setConnectTimeout(int ms)` | Connection establishment per protocol handler | May throw `SocketTimeoutException` |
| `URLConnection.setReadTimeout(int ms)` | One read from InputStream waiting for data | May throw `SocketTimeoutException` |
| `HttpClient.Builder.connectTimeout(Duration)` | Establishing a **new connection**; no effect if reusing a connection | `HttpConnectTimeoutException` when connect times out |
| `HttpRequest.Builder.timeout(Duration)` | **One request**: waiting for response per Java 17 API | `HttpTimeoutException` if response is not received on time |
| `CompletableFuture.orTimeout(long, TimeUnit)` | Future not completed after interval | Future completes exceptionally with `TimeoutException`; does not mean external task is stopped |
| `Future.get(long, TimeUnit)` | Time the caller **waits** for the future | `TimeoutException`; future/task may still be running |
| `Thread.sleep(...)` | A voluntary wait interval | Does **not** automatically bound total retry duration or cancel network I/O |

**Specifically:** on `Socket`/`URLConnection`, a timeout of **0** means **unlimited** (infinite). On the `HttpClient.connectTimeout(Duration)` and `HttpRequest.timeout(Duration)` builders, `Duration` must be **positive**; do not use `Duration.ZERO` to mean "do not wait" — it will throw `IllegalArgumentException`. If remaining is already 0, **fail fast**.

### About HTTP request timeout and body streams

Per Java 17 `HttpRequest.Builder.timeout`, when **the response is not received** within the timeout, `HttpClient.send` throws `HttpTimeoutException` or the `sendAsync` future completes exceptionally. **Do not infer** from this that all application operations on a streaming body such as `BodyHandlers.ofInputStream()`, parsing gigabytes of data, retries, and downstream work are all bounded until you finish the workflow. For a handed-off stream, the application needs its own read timeout and overall deadline, closing the stream when data is no longer needed.

### Does connect timeout apply to TLS handshake?

The exact scope of connect timeout for an HTTP client/provider/runtime requires reading JDK documentation and testing. Java 17 Javadoc emphasizes **when a new connection needs to be established** and does not apply on reuse; do not treat a single `connectTimeout` number as a hard guarantee across **all** stages of DNS, TLS handshake, body, and parsing. For strict deadline requirements, add a request budget and external cancellation.

## 8. Visualizing deadlines with a concrete timeline

Suppose the total budget is 1,200 ms:

```text
0             100             280             480             680      940   1200
|--- setup ---|--- connect ----|-- chunk #1 ---|-- chunk #2 ---|--silence--|-----|
                                                ^               ^
                                            progress        progress
                                                                |
  at 940 ms: 260 ms without new bytes -> idle limit 250 ms has expired
  at 940 ms: total used is only 940/1200 ms -> overall still has 260 ms left
  at 1200 ms: overall deadline has expired, not reset by retries
```

For example:

- After 100 ms setup: remaining 1,100 ms.
- Per-connect cap is 300 ms, not 1,100 ms.
- Connect actually takes 180 ms: remaining 920 ms.
- Per-read cap 350 ms and idle window 250 ms: first read is capped at 250 ms.
- Chunk #1 arrives after 200 ms: remaining 720 ms, idle resets.
- Chunk #2 arrives after 200 ms: remaining 520 ms, idle resets.
- Another 260 ms of silence: idle expired, **overall still has 260 ms**.

**These are two separate failure modes.** An operation can time out due to idle before the overall budget expires. Conversely, a stream can continuously make progress while the overall deadline expires first. These numbers are generated by the fake-clock demo below for deterministic testing without depending on scheduling.

## 9. Java 17 Example #1: simulating deadline and idle window with a controlled clock

To learn the calculations in a **deterministic way, independent of OS jitter**, `TimeBudgetSimulation.java` uses a fake clock `FakeTicker`. It simulates elapsed time intervals rather than **generating real traffic**. Therefore stdout is exact, verifying both "idle expires first" and "overall expires first."

`Deadline` keeps **start + total** fixed, and `capMillis` takes the minimum of the per-operation limit and remaining time. `IdleWindow` keeps the timestamp of the latest progress, and only `progress()` resets idle. Assertions fail if the state is incorrect.

**Complete program:**

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class TimeBudgetSimulation {
    static final class FakeTicker {
        private long nowNanos;

        long now() {
            return nowNanos;
        }

        void advanceMillis(long amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("negative advance");
            }
            nowNanos += TimeUnit.MILLISECONDS.toNanos(amount);
        }
    }

    static final class Deadline {
        private final FakeTicker ticker;
        private final long start;
        private final long totalNanos;

        Deadline(FakeTicker ticker, Duration total) {
            if (total.isZero() || total.isNegative()) {
                throw new IllegalArgumentException("total must be positive");
            }
            this.ticker = ticker;
            this.start = ticker.now();
            this.totalNanos = total.toNanos();
        }

        long remainingNanos() {
            long elapsed = ticker.now() - start;
            return Math.max(0L, totalNanos - elapsed);
        }

        boolean expired() {
            return remainingNanos() == 0;
        }

        long capMillis(Duration operation) {
            if (operation.isZero() || operation.isNegative()) {
                throw new IllegalArgumentException("operation must be positive");
            }
            long left = remainingNanos();
            if (left == 0) {
                throw new IllegalStateException("overall deadline expired");
            }
            return TimeUnit.NANOSECONDS.toMillis(
                    Math.min(left, operation.toNanos()));
        }
    }

    static final class IdleWindow {
        private final FakeTicker ticker;
        private final long limitNanos;
        private long lastProgress;

        IdleWindow(FakeTicker ticker, Duration idleLimit) {
            if (idleLimit.isNegative() || idleLimit.isZero()) {
                throw new IllegalArgumentException("idle limit must be positive");
            }
            this.ticker = ticker;
            this.limitNanos = idleLimit.toNanos();
            this.lastProgress = ticker.now();
        }

        void progress() {
            lastProgress = ticker.now();
        }

        boolean expired() {
            return ticker.now() - lastProgress >= limitNanos;
        }

        long remainingMillis() {
            return TimeUnit.NANOSECONDS.toMillis(
                    Math.max(0L, limitNanos - (ticker.now() - lastProgress)));
        }
    }

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected time budget state");
        }
    }

    public static void main(String[] args) {
        FakeTicker t = new FakeTicker();
        Deadline total = new Deadline(t, Duration.ofMillis(1200));

        System.out.println("Initial total: "
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos()) + " ms");

        t.advanceMillis(100); // setup / DNS model
        System.out.println("After setup: "
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos()) + " ms");
        System.out.println("Connect operation cap: "
                + total.capMillis(Duration.ofMillis(300)) + " ms");

        t.advanceMillis(180); // successful connect
        System.out.println("After connect: "
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos()) + " ms");

        IdleWindow idle = new IdleWindow(t, Duration.ofMillis(250));
        System.out.println("First read cap: "
                + Math.min(total.capMillis(Duration.ofMillis(350)),
                           idle.remainingMillis()) + " ms");

        t.advanceMillis(200);
        idle.progress(); // first chunk arrived
        check(!idle.expired());
        System.out.println("Chunk 1: totalLeft="
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos())
                + " ms, idleExpired=" + idle.expired());

        t.advanceMillis(200);
        idle.progress(); // second chunk arrived
        check(!idle.expired());
        System.out.println("Chunk 2: totalLeft="
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos())
                + " ms, idleExpired=" + idle.expired());

        t.advanceMillis(260); // no new data
        check(idle.expired() && !total.expired());
        System.out.println("Silence: idleExpired=" + idle.expired()
                + ", overallExpired=" + total.expired()
                + ", totalLeft="
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos()) + " ms");

        t.advanceMillis(260);
        check(total.expired());
        System.out.println("Deadline expired: " + total.expired());

        FakeTicker dripTicker = new FakeTicker();
        Deadline dripDeadline =
                new Deadline(dripTicker, Duration.ofMillis(500));
        IdleWindow dripIdle =
                new IdleWindow(dripTicker, Duration.ofMillis(250));
        for (int i = 0; i < 3; i++) {
            dripTicker.advanceMillis(180);
            dripIdle.progress(); // progress prevents idle timeout
        }
        check(!dripIdle.expired() && dripDeadline.expired());
        System.out.println("Slow drip: idleExpired=" + dripIdle.expired()
                + ", overallExpired=" + dripDeadline.expired());

        FakeTicker retryTicker = new FakeTicker();
        Deadline retryBudget =
                new Deadline(retryTicker, Duration.ofMillis(1000));
        System.out.println("Attempt 1 cap: "
                + retryBudget.capMillis(Duration.ofMillis(450)) + " ms");
        retryTicker.advanceMillis(400);
        System.out.println("Attempt 2 cap: "
                + retryBudget.capMillis(Duration.ofMillis(450)) + " ms");
        retryTicker.advanceMillis(400);
        System.out.println("Attempt 3 cap: "
                + retryBudget.capMillis(Duration.ofMillis(450)) + " ms");
    }
}
```

Compile/run (Java 17+):

```bash
javac --release 17 -encoding UTF-8 TimeBudgetSimulation.java
java TimeBudgetSimulation
```

**Exact stdout:**

```text
Initial total: 1200 ms
After setup: 1100 ms
Connect operation cap: 300 ms
After connect: 920 ms
First read cap: 250 ms
Chunk 1: totalLeft=720 ms, idleExpired=false
Chunk 2: totalLeft=520 ms, idleExpired=false
Silence: idleExpired=true, overallExpired=false, totalLeft=260 ms
Deadline expired: true
Slow drip: idleExpired=false, overallExpired=true
Attempt 1 cap: 450 ms
Attempt 2 cap: 450 ms
Attempt 3 cap: 200 ms
```

### Analysis of each result

- `1200 → 1100 → 920`: the total budget is not reset when setup or connect succeeds.
- `Connect operation cap: 300ms`: a single connect does not consume the entire remaining 1100ms if policy only allows 300ms.
- `First read cap: 250ms`: the minimum of overall remaining, the 350ms per-read limit, and the 250ms idle window.
- Two chunks 200ms apart reset idle but still consume **400ms** of the total budget.
- After 260ms without progress, idle expires while overall still has 260ms left: **idle timeout occurs before overall timeout**.
- Slow drip has progress every 180ms so idle never expires, while **the 500ms total is exceeded**.
- Retry attempts have caps of 450, 450, **200ms**: the final attempt is capped to the remaining budget rather than receiving a fresh 450ms.

**Limitation to state clearly:** `FakeTicker` is a simulation; it **does not automatically cancel a blocked socket**. `Deadline.capMillis` returns milliseconds solely to illustrate budgeting. In production, you must handle sub-1ms remaining/overflow, choose appropriate positive API timeouts, provide I/O cancel/close mechanisms, and test against a real clock. Do not treat test output as a measurement of OS timer precision.

## 10. Java 17 Example #2: `Socket.setSoTimeout` only limits a single blocking read

The second example uses **real TCP loopback**, requiring no Internet and no external libraries. The program starts a `ServerSocket`, has the server send the letter `A` once and then **deliberately stay silent**. The client:

1. Calls `Socket.connect(..., 2000)` with a **2000ms connect timeout**.
2. Calls `setSoTimeout(3000)` to wait for the first byte for up to 3000ms.
3. Receives `A` successfully.
4. Switches to `setSoTimeout(300)` and calls `read()` again.
5. The server sends no more bytes and does not close the connection until the client signals completion → `SocketTimeoutException` on the second read.
6. Catches the exception and proves that **read timeout does not automatically close the Socket object**.

`CountDownLatch` is used so the server only exits **after the client finishes testing**, without relying on `Thread.sleep` or scheduling jitter to produce the result. A 5-second guard prevents the test server from waiting forever if the client fails.

File **`SocketIdleReadDemo.java`**:

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class SocketIdleReadDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] { 127, 0, 0, 1 });
        CountDownLatch releaseServer = new CountDownLatch(1);
        AtomicReference<Throwable> serverFailure = new AtomicReference<>();

        try (ServerSocket listener = new ServerSocket(0, 1, loopback)) {
            Thread server = new Thread(() -> {
                try (Socket peer = listener.accept()) {
                    peer.getOutputStream().write('A');
                    peer.getOutputStream().flush();
                    if (!releaseServer.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("server release timeout");
                    }
                } catch (Throwable error) {
                    serverFailure.set(error);
                }
            }, "loopback-test-server");
            server.start();
            try {
                try (Socket client = new Socket()) {
                    client.connect(
                            new InetSocketAddress(
                                    loopback, listener.getLocalPort()),
                            2000);
                    client.setSoTimeout(3000); // initial read
                    InputStream in = client.getInputStream();
                    int firstByte = in.read();
                    if (firstByte != 'A') {
                        throw new AssertionError("Unexpected first byte");
                    }

                    client.setSoTimeout(300); // each blocking read
                    boolean timedOut = false;
                    try {
                        in.read(); // server deliberately waits, sends no bytes
                    } catch (SocketTimeoutException expected) {
                        timedOut = true;
                    }
                    if (!timedOut) {
                        throw new AssertionError("Missing read timeout");
                    }

                    System.out.println("First byte: " + (char) firstByte);
                    System.out.println("Read idle timed out: " + timedOut);
                    System.out.println(
                            "Socket closed by timeout: " + client.isClosed());
                }
            } finally {
                releaseServer.countDown();
                server.join(2000);
                if (server.isAlive()) {
                    throw new AssertionError("Server thread did not finish");
                }
            }
        }
        if (serverFailure.get() != null) {
            throw new AssertionError("Server failed", serverFailure.get());
        }
    }
}
```

Compile/run:

```bash
javac --release 17 -encoding UTF-8 SocketIdleReadDemo.java
java SocketIdleReadDemo
```

**Exact stdout when the environment permits TCP loopback:**

```text
First byte: A
Read idle timed out: true
Socket closed by timeout: false
```

### Accurate interpretation

- Connect succeeding **does not prove** the entire response will arrive on time.
- The client receives the first byte, so the first read succeeds.
- The second read waits for data; because the server keeps the TCP connection open but silent, a 300ms gap without data leads to `SocketTimeoutException`.
- `Socket closed by timeout: false` is printed **before try-with-resources closes the client**: a read timeout exception **does not automatically close the socket**. This **does not** prove the peer is still healthy or can accept data indefinitely.
- Upon exiting `try`, the client socket is **explicitly closed**; the latch releases the server and test resources are cleaned up.

**Do not infer this is a 300ms overall deadline.** If the server keeps sending data fast enough, each `read()` may never time out, yet a loop reading millions of times still exceeds the business deadline. To bound the total, you must also measure elapsed time, limit bytes/chunks, and have a way to cancel/close the socket when the budget expires.

## 11. From simulation to real code: capping timeouts for HttpClient

A Java 17 application using `java.net.http.HttpClient` can set **connect timeout on the client** and **request timeout on each HttpRequest**:

```java
// Illustrative code: placed inside a method with URI and deadline helper.
// deadline.remaining() returns a positive Duration or Duration.ZERO.
// Not a complete program, as the helper is application-defined.
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(300))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

Duration remaining = deadline.remaining();
if (remaining.isZero() || remaining.isNegative()) {
    throw new TimeoutException("overall deadline exhausted");
}

Duration perAttempt = Duration.ofMillis(700);
Duration allowedAttempt = remaining.compareTo(perAttempt) < 0
        ? remaining : perAttempt;

HttpRequest req = HttpRequest.newBuilder(uri)
        .timeout(allowedAttempt)
        .GET()
        .build();

HttpResponse<String> response = client.send(
        req,
        HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
```

**Key points:**

1. `connectTimeout(300ms)` applies to **new connections** of the client; it has no effect if a connection from the pool is reused.
2. `req.timeout(allowedAttempt)` is the **timeout of that specific attempt**. `allowedAttempt` is chosen to be **no greater than** the total remaining at the start.
3. After `send` returns, you still need to check **how much deadline remains** before parsing JSON, calling another dependency, or retrying; a request timeout does not manage the entire workflow for you.
4. If a retry is needed, recompute `deadline.remaining()` **again** for the new attempt. **Do not** start an attempt with `remaining == 0`.
5. If the application needs a "hard" deadline for post-response operations, it must use cancellation/cooperative checks and resource cleanup, rather than assuming `HttpResponse<String>` covers all business processing.

### HttpTimeoutException and HttpConnectTimeoutException

`HttpConnectTimeoutException` extends `HttpTimeoutException`. If you want to distinguish them when catching:

```java
// Illustrative snippet; client and request are configured as above.
try {
    HttpResponse<String> r = client.send(
            request, HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));
    // Evaluate status/header/body.
} catch (HttpConnectTimeoutException ex) {
    // New connection was not established within the limit.
} catch (HttpTimeoutException ex) {
    // Request did not receive a response within the API timeout.
} catch (IOException ex) {
    // Other transport/TLS/I/O errors.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Cancel workflow and release resources.
}
```

If you catch `HttpTimeoutException` before `HttpConnectTimeoutException`, the subsequent subclass branch becomes unreachable, and the Java compiler reports an unreachable catch error. **A timeout is an I/O error, not an HTTP status code.** A server returning `504 Gateway Timeout` is an **HTTP response from a gateway**, distinct from the client itself throwing `HttpTimeoutException` because it did not receive a response in time.

### With the classic URLConnection API

`HttpURLConnection`/`HttpsURLConnection` provides:

```java
// Illustrative code: URL and connection must be closed per lifecycle.
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();
conn.setConnectTimeout(300);
conn.setReadTimeout(250);
conn.setInstanceFollowRedirects(false);
```

`setConnectTimeout` limits the connection phase per handler; `setReadTimeout` limits waiting for data on a read. **There is no guarantee** that `connectTimeout + readTimeout` sums to an overall deadline. `0` means infinite; configure timeouts **before implicit connection** via `getResponseCode`/`getInputStream`.

## 12. How to apply an overall deadline to a streaming read loop

A very long stream needs at least three layers of protection:

- **Overall deadline** (if the business operation is required to finish): the monotonic deadline of the logical request.
- **Per-read/idle timeout**: if no data or valid progress occurs for an interval, stop.
- **Size / progress quota**: limit byte count, message count, excessively slow rates, and protocol-invalid content.

A socket processing loop can follow this **algorithm**:

```text
overallDeadline = monotonicStart + 1200ms
idleLimit = 250ms
perReadLimit = 350ms
lastProgress = monotonicStart

while response is not complete:
    remainingTotal = deadline - now
    remainingIdle  = idleLimit - (now - lastProgress)
    readWait = min(remainingTotal, remainingIdle, perReadLimit)

    if readWait <= 0: abort/close and report the appropriate timeout type
    setSoTimeout(appropriate_positive_millis(readWait))
    n = input.read(buffer)

    if n == -1: handle EOF per protocol
    if n > 0:
        lastProgress = monotonicNow
        bytes += n
        if quota exceeded: abort/close and report error
        parse bounded chunks / apply backpressure
```

**This is pseudocode**, not a runnable class. In real code, you must add protocol-specific termination conditions (Content-Length/chunked/framing), avoid overflow, avoid `0` when converting ns→ms, and have a watchdog/hard cancellation if a blocking operation does not respect the deadline.

### Why check again after the read?

Recompute `now` and the deadline **after the read finishes**. If the read completes right as the total budget expires, the application must not proceed to parse/commit a business operation with a strict deadline. When the requirement is simply "return before deadline," a timeout near the end is an intentional race: you must clearly define how an overdue response is discarded/recorded.

### Per-read timeout differs from whole-content timeout

For example, a file with 10,000 chunks, each delivering a byte after 100ms. A 250ms per-read timeout does **not** bound the whole file; it can take nearly 1,000 seconds without any single read expiring. An overall budget or minimum progress rate is a complementary mechanism.

## 13. Retries and backoff must share one deadline

### Anti-pattern: each attempt creates a new deadline

```text
Wrong:
attempt1: create 1s timeout
  fails after 900ms
backoff 500ms
attempt2: create new 1s timeout
  fails after 900ms
backoff 500ms
attempt3: create new 1s timeout

Total ~= 4.8s even though caller only gave 1s.
```

Correct design:

```text
t0: overall budget 1000ms
attempt1 cap 450ms, actually used 400ms
  remaining = 600ms
attempt2 cap 450ms, actually used 400ms
  remaining = 200ms
attempt3 cap min(450, 200) = 200ms
no attempt4 once remaining <= 0
```

If there is a 100ms backoff between attempts, it also **consumes the overall deadline**. Do not add an "exception" of 100ms per retry when the caller has set a strict deadline.

### Rules for retry decisions

1. **Only retry when enough remaining time exists** for a meaningful attempt; optionally reserve time for cleanup/response serialization.
2. **Do not retry indefinitely.** Have a retry budget, backoff with jitter, and respect `Retry-After`/rate limits when appropriate.
3. **Do not blindly retry POST side effects** after an I/O timeout: the server may have already processed the payment/order while the response was lost. You need a server-supported idempotency key or lookup/reconciliation.
4. **HTTP 429/503** may suggest retrying per contract; a `504` from a gateway does not by itself prove the origin did not commit.
5. For **non-replayable body publishers**, redirects/auth/retries need a dedicated policy; an already-consumed stream may not be resendable.
6. **Cancel the old attempt** and clean up before reusing resources, avoiding multiple attempts running concurrently unintentionally.

### Hedged requests also consume the budget

Hedging by sending a secondary request when the primary is slow can reduce tail latency for safe read operations, but increases load, cost, and races. Both branches must belong to the same deadline; once a result arrives, cancel/close the redundant branch, and do not create duplicate side effects when the operation is not idempotent.

## 14. Cancellation and deadlines: a logical limit does not automatically stop the system

A deadline stored only in a `long` variable **does not automatically cancel a blocked thread/socket**. To guarantee returning and reclaiming resources:

- Use the API's built-in timeout when available.
- With `Socket`, **close the socket** when you need to force a blocking read/write to end; calling `Thread.interrupt()` alone cannot be relied upon as a universal guarantee for all blocking I/O on Java 17.
- With `HttpClient.sendAsync`, you can manage `CompletableFuture` and cancellation, but understand that this is best-effort and the response/server-side side effect may have already occurred.
- With `Future.get(timeout)`, when the wait expires only the caller throws `TimeoutException`; the worker may keep running if you do not cancel the task/cooperatively terminate.
- With streaming `BodyHandlers.ofInputStream()`, close the InputStream on cancellation and do not hold the connection/body subscriber open indefinitely.
- With parsing/CPU-bound tasks, use cancellation flags/interruption/cooperative checks; an overall deadline does not automatically stop a long loop.
- Once a business callback/transaction has committed, canceling the network response does not automatically roll back state. You must use idempotency, saga/compensation, or separate reconciliation.

### Beware of `CompletableFuture.orTimeout`

`future.orTimeout(500, TimeUnit.MILLISECONDS)` completes the future exceptionally if it has not completed within the limit. It does **not** prove the worker thread/server has stopped; nor does it turn a logical deadline across three retries into an overall limit if you create a new future with a fresh timeout on each attempt.

### Distinguish timeout exceptions from cancellation

`CancellationException` indicates a future/task was canceled; `TimeoutException` is exceeding an API wait/completion deadline; `SocketTimeoutException` is a form of I/O timeout; `HttpTimeoutException` relates to HTTP client deadlines. Do not lump them into a single "network error" string and apply the same retry decision.

## 15. Observability, setting SLOs, and choosing practical timeouts

Improving reliability requires real data, not just setting every timeout to 30 seconds:

| Observation | Why it is needed |
|---|---|
| End-to-end latency (p50/p95/p99) | Know how long requests actually take and their tail latency |
| DNS + connect + TLS timing | Separate connection establishment cost from server processing |
| Time-to-first-byte / response headers | Distinguish slow server processing from slow body transfer |
| Response streaming throughput | Detect slow-drip and downstream congestion |
| Per-attempt timeout counts | See which operations frequently exhaust their budget |
| Overall deadline exhausted | Count requests violating the SLO contract |
| Read-idle timeout counts | Detect stalls or silent peers |
| Retries, backoff, remaining budget | Know whether retries actually help or just amplify load |
| Cancellation completion and leaks | Verify sockets/streams/tasks are released on time |
| Late-response discarded | See server-side requests completing after the caller's deadline |

**Do not treat "timeout" as a single root cause.** For example, `HTTP 504` may come from a gateway, `SocketTimeoutException` from a read missing bytes, `HttpConnectTimeoutException` from establishment; an endpoint that already received a request before the client timed out also creates an **unknown outcome**. Metrics should carry `phase`/`attempt`/`elapsed`/`remaining` tags, while avoiding unbounded cardinality (URLs with user IDs, random queries) and never logging secrets.

### How to choose a budget

- Start from the overall request **SLO/UX deadline**, not from connect timeout.
- Use each dependency's real latency to set per-operation caps.
- Set a sensible lower bound to avoid overly tight timeouts failing normal traffic; set an upper bound to avoid holding resources indefinitely.
- Set **separate budgets for long-lived streams** like WebSocket/SSE, since a session may be allowed to stay open for a long time; still enforce heartbeats/idle and internal operation deadlines.
- Account for bursts, cold starts, DNS, proxies, TLS, retry storms, scheduled maintenance, and backpressure.
- Reserve budget for **response serialization and cleanup** so upstream can still receive a result when you are close to expiring.

## 16. Common mistakes and how to fix them

| Mistake | Consequence | Correct approach |
|---|---|---|
| `connectTimeout=2s` means whole request ≤ 2s | Slow server read/send still hangs | Separate overall deadline |
| `setSoTimeout(500)` means file finishes in 500ms | Slow drip every 400ms evades read timeout | Overall deadline + size/throughput quota |
| `readTimeout=0` to "not wait" | 0 is **infinite** in Socket/URLConnection | Fail fast or positive timeout |
| `HttpRequest.timeout(Duration.ZERO)` | `IllegalArgumentException` | Check remaining, do not start attempt when 0 |
| Each retry creates a fresh total timeout | Exceeds caller's budget | Keep one immutable deadline from initial request |
| Not counting backoff against deadline | Retry sleep eats past the budget | Compute remaining before/after backoff |
| Using `Instant.now()` to measure elapsed | Clock can jump | `System.nanoTime()` / monotonic ticker |
| Sending `nanoTime()` from machine A to B | Different reference frames | Pass remaining budget/protocol deadline |
| Computing `(int) remainingNanos / 1_000_000` | Overflow from early cast | Divide as `long` then clamp |
| Converting nanoseconds to milliseconds <1ms becomes 0 | Accidentally disables socket timeout | Fail fast / minimum positive timeout |
| Setting same per-operation limit for all stages | Different stage costs/tails are ignored | Give connect/read/parse/upload separate caps |
| Ignoring queue and serialization | Pre-send delays go uncounted | Measure whole workflow from the start |
| Thinking `HttpClient.connectTimeout` applies to reused connections | No effect on reuse | Request/per-operation deadline |
| Thinking `get(timeout)` canceled the worker | Task keeps running and consuming resources | Cancel/cooperative stop + cleanup |
| Using `Thread.interrupt` as sole solution for Socket | Not guaranteed to unblock blocking I/O universally on Java 17 | Close socket and manage lifecycle |
| Thinking one byte is business progress | Stream can send whitespace/heartbeats forever | Protocol/business progress timeout |
| Resetting overall deadline on heartbeat | Request never expires | Reset idle if valid, never reset overall |
| Not limiting response size | Body can exceed heap despite timeout | Bounded stream/size quota |
| Not handling error stream/status | Confusing HTTP errors with I/O timeouts | Inspect HTTP responses separately |
| Retrying payment POST when response is lost | Can cause duplicate side effects | Idempotency key/reconciliation |
| Tracking only timeout counts | Cannot tell which stage is the bottleneck | Metrics by phase, elapsed, budget left |
| Not identifying long-lived nature of a stream | Picking 1s overall for a multi-hour WebSocket | Session idle, heartbeat, sub-operation deadline |
| Ignoring connection pool idle | Stale connections hold resources too long | Pool lifecycle separate from request budget |
| Catching `SocketTimeoutException` and dropping connection without cleanup | Socket/stream leaks | `try-with-resources` or proper close/cancel |

## 17. Exercises and self-check questions

**Question 1.** You have a 2s connect timeout, 2s read timeout, and 3 retries. Is the request guaranteed to finish within 2s?

**Answer:** No. Each limit applies to a different stage/operation; without an overall deadline, multiple stages and retries can far exceed 2s.

**Question 2.** `Socket.setSoTimeout(200)`, and the server sends one byte every 150ms. Can downloading 5 MiB take longer than 200ms?

**Answer:** Yes. Each blocking read can receive data before its own limit. You need an overall deadline and throughput/size quotas when needed.

**Question 3.** Total budget 1,000ms, attempt1 uses 400ms, attempt2 uses 400ms. Per-attempt limit is 450ms. What is the cap for attempt3?

**Answer:** `min(450, 200) = 200ms`, before subtracting any further overhead/backoff.

**Question 4.** An attempt times out because the server sends slowly; should the total budget be reset on the next attempt?

**Answer:** No. Retries are part of the **same logical request** and consume the remaining budget.

**Question 5.** Why use `System.nanoTime()` to measure elapsed time instead of `System.currentTimeMillis()`?

**Answer:** `nanoTime` is suited for intervals/monotonic elapsed time, not an adjustable wall clock. It is not used as a Unix timestamp.

**Question 6.** Why is `remainingMillis = (int)remainingNanos / 1_000_000` error-prone?

**Answer:** Casting before dividing can overflow `int`. Divide as `long` first, check API bounds, and avoid 0 causing an infinite timeout.

**Question 7.** Does `Socket.setSoTimeout(0)` mean reading finishes immediately?

**Answer:** No. 0 **disables** the read timeout, equivalent to waiting indefinitely, and can block if no data arrives.

**Question 8.** Does `HttpClient.Builder.connectTimeout` apply to a request that reuses an existing connection?

**Answer:** No. Java 17 specifies that connect timeout only applies when a **new connection** must be established.

**Question 9.** Does `HttpRequest.Builder.timeout` replace the overall deadline across retries + parsing?

**Answer:** No. It applies to a single HTTP request per contract; the application still needs to coordinate the end-to-end budget.

**Question 10.** If `Future.get(300, MILLISECONDS)` throws `TimeoutException`, has the task definitely stopped?

**Answer:** No. That is only the caller's wait timeout; cancellation/cleanup must be managed separately.

**Question 11.** If `Socket.getInputStream().read()` times out, is the socket automatically closed?

**Answer:** No per the `SO_TIMEOUT` API; `SocketTimeoutException` is thrown, but the socket remains valid. The loopback demo verifies the socket object is not closed.

**Question 12.** Are `HTTP 504` and `HttpTimeoutException` the same?

**Answer:** No. `504` is an HTTP response from a gateway; `HttpTimeoutException` is a Java HTTP client exception when no response is received in time.

**Question 13.** An SSE stream sends heartbeats regularly but produces no business records for 15 minutes. Is a timeout needed?

**Answer:** Depends on the contract: heartbeats can reset **transport idle**, but the application may need a separate **business progress deadline**. Do not reset the overall operation deadline if no required result has arrived.

**Question 14.** Should you cancel a payment POST right when the deadline expires and automatically send a new POST?

**Answer:** No. The server may have committed before the response was lost. You need an idempotency key/reconciliation; client cancellation does not roll back the server.

**Question 15.** Why does a long-lived WebSocket need multiple types of limits?

**Answer:** A session may intentionally live a long time, yet still needs idle/heartbeats, resource caps, per-command timeouts, business progress deadlines, and proper cancellation.

**Question 16.** Is `Socket.setSoTimeout` alone sufficient for idle timeout in every protocol?

**Answer:** No. `SO_TIMEOUT` only bounds each blocking read; applications may need frame/record progress timeouts, upload write stall timeouts, or separate connection pool idle policies.

**Question 17.** If 0.4ms remains on the deadline and converting to millis for `setSoTimeout(int)` yields 0, what should you do?

**Answer:** Do not pass 0 when you want a limit. Usually fail fast, or use a minimum positive timeout alongside an external monotonic deadline/cancellation, depending on contract precision.

**Question 18.** If two downstream calls run in parallel, must the deadline equal the sum of both timeouts?

**Answer:** Not necessarily. They can overlap in time, but they share the overall deadline and both require cancellation/resource cleanup.

**Question 19.** Is a 200ms backoff outside or inside the request budget?

**Answer:** Inside the **logical request** budget, unless the caller contract explicitly specifies otherwise. Do not grant extra time for each backoff.

**Question 20.** If the socket API already provides a read timeout, why still measure time after each chunk?

**Answer:** Read timeout only tracks the wait for data on each individual read. Total elapsed time still grows across all chunks and can hit the deadline, so you must measure/bound the entire sequence.

## 18. Timeout implementation checklist for Java networking

1. **Lock down the overall deadline from the SLO**, measured from the start of the logical request, never reset across retries/redirects/parsing.
2. **Use monotonic time** for elapsed duration; have a `Ticker/Clock` abstraction to unit test boundary conditions easily.
3. **Compute remaining before every step**; if exhausted, fail fast without making network calls.
4. **Cap operation timeout = min(perPhaseLimit, remaining)**; never grant a timeout longer than what remains.
5. **Separate connect/request/read idle/write stall**; do not refer to them generically as a "2s timeout" in docs.
6. **Remember 0 means infinite** in `Socket/URLConnection` and `Duration` must be positive in HttpClient builders.
7. **Bound streaming bytes and business progress**, defending against slow drip/slowloris; heartbeats do not equal a complete result.
8. **Wire up proper cancel/close** so the deadline does not just exist in a variable but actually frees threads/sockets/streams.
9. **Include retries/backoff/jitter in the same budget**, with idempotency/reconciliation and a maximum attempt count.
10. **Do not assume a timeout means the server did not process the request**, especially for POST/side effects.
11. **Test with both a fake clock and a loopback network**; test overall-first, idle-first, boundary races, no data, partial responses, slow streams, and cancellation.
12. **Observe by stage**, measuring p95/p99, timeout percentage, retry count, remaining budget, and task leaks.
13. **Handle HTTP statuses separately from I/O exceptions**: a 504 server/gateway response is not the same as a client-side timer throwing an exception.
14. **Clean up on cancellation**, ensuring streams/files/connections close per lifecycle without keeping late tasks alive indefinitely.
15. **Tune budgets by request type**: large uploads, long streams, small reads, and payments require different profiles.

**Final takeaway:** An **overall deadline** guarantees a bound for the **entire logical request**; a **per-operation timeout** bounds **one stage or attempt**; an **idle timeout** bounds the period **without progress by a defined criterion**. In Java 17, `connectTimeout` does not replace read timeout, `SO_TIMEOUT` does not replace overall deadline, and `HttpRequest.timeout` does not replace the entire retry/business workflow. Keep one monotonic deadline, grant each operation no more than remaining time, and combine stream controls with cancellation — that is the foundation of reliable networking design.

### Official references

- [Java SE 17 — System.nanoTime (elapsed time)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime())
- [Java SE 17 — Socket.connect and setSoTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Java SE 17 — ServerSocket.setSoTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html)
- [Java SE 17 — URLConnection.setConnectTimeout and setReadTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html)
- [Java SE 17 — HttpClient.Builder.connectTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 17 — HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 17 — HttpTimeoutException / HttpConnectTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html)
- [Java SE 17 — CompletableFuture.orTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [RFC 9110 — HTTP semantics, errors and retries](https://www.rfc-editor.org/rfc/rfc9110)
