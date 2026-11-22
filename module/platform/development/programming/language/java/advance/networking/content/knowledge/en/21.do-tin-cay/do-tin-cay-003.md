# Bounded Retries with Exponential Backoff and Jitter in Java Networking

When an HTTP request encounters `503 Service Unavailable`, `429 Too Many Requests`, or a temporary connection error, resending the request can help the system ride out a short-lived incident. However, "retry immediately on every error" is a dangerous strategy: many clients can simultaneously hammer an already overloaded server, increasing latency, tying up worker threads, and multiplying requests across the entire system. If a request has side effects, retrying can also **create duplicate orders, double-charge payments, or write duplicate data** when the server already processed the first request but the client never received the response.

This Knowledge article focuses on **bounded retries + capped exponential backoff + jitter**:

1. **Retry only transient errors and operations that are safe to replay**; distinguish between transient transport failures, HTTP statuses, and business failures.
2. **Bound the number of attempts** (`maxAttempts` including the initial attempt), per-attempt duration, **total deadline**, concurrent retries, and queue capacity.
3. **Increase wait time after failures** with capped exponential backoff (`maxBackoff`), then add **jitter** so clients do not wake up in lockstep.
4. **Respect the server's `Retry-After`** when appropriate; do not truncate a 1-hour wait request down to 2 seconds just because the local backoff cap is 2 seconds.
5. **Stop at the right time** on success, on non-retryable errors, when attempts are exhausted, when the time budget is exhausted, on cancellation/interruption, or when the request body cannot be replayed.
6. **Observe and test** using Java 17+, with a deterministic math example, a loopback HTTP server returning 503→503→200, and an async example using `ScheduledExecutorService` instead of blocking threads with `sleep`.

**Foundational principle:** retry is a **bounded recovery mechanism**, not a guarantee that a request will succeed, not "exactly-once" message delivery, and not a substitute for rate limiting, timeouts, circuit breakers, or backpressure.

## 1. When Does Retry Help and When Does It Harm?

### 1.1. What Is a Transient Failure?

A transient error has a chance of resolving itself after a short period: a temporarily overloaded server, flaky network, a proxy/gateway dropping a connection during rotation, temporary rate limiting, or a restarting service. If the client resends **in a controlled manner**, the probability of success can increase.

~~~text
Client                       API server
  │ GET /inventory               │
  ├──────────────────────────────>│
  │<──────── 503 + Retry-After ──┤   Server in brief maintenance
  │                              │
  │    capped backoff + jitter   │
  │    (no spin retry)           │
  │                              │
  ├──────────────────────────────>│
  │<──────── 200 OK ─────────────┤
~~~

Some errors will not resolve by repeating the exact same request: wrong endpoint (404), invalid token (401), missing permissions (403), malformed request body (400/422), failed business constraint, or untrusted certificate. Continuously retrying these errors wastes resources and can mask the root cause.

### 1.2. Baseline HTTP Retry Policy Table

| Scenario | Auto-retry? | Conditions |
| --- | --- | --- |
| `GET/HEAD` receives `429` | Usually **yes** | If permitted, respect rate-limit/`Retry-After` and total deadline |
| `GET/HEAD` receives `503` | Usually **yes** | Temporary service unavailable, budget remaining |
| `502/504` | Possible per policy | Temporary gateway/upstream error; only when request has retry-safe semantics |
| `500` | **Not by default** | Must know server error is likely transient; repeating a logic bug indefinitely does not help |
| `408` | Possible per semantics/contract | Request timeout at HTTP layer, verify request can be replayed |
| `400/401/403/404/422` | **No** with the same payload | Must fix request, credential, permission, or resource |
| `409/412` | Do not retry blindly | Conflict/Precondition Failed requires reading fresh state before deciding |
| `301/302/307/308` | Not a transient failure by default | Redirect is a separate mechanism; `Retry-After` may apply to redirects |
| TCP connection reset/temporary `IOException` | Possible | Classify error and idempotency safety; do not retry all `IOException`s |
| `UnknownHostException` due to wrong host | Usually no | Wrong DNS/config; retrying endlessly will not create a valid host |
| `SSLHandshakeException`/certificate mismatch | No | Fix TLS trust/hostname; do not disable verification |
| `InterruptedException`/caller cancel | No | Respect cancellation; restore interrupt when needed |

**This is a starting point, not a mandatory HTTP rule for every API.** A `429` error is a rate-limiting signal that may include `Retry-After`; a `503` error is temporary unavailability that may also include a hint. An API may define custom error codes, quota windows, and stricter retry rules. A transport error before the client receives a response **does not prove the server has not processed the request**.

### 1.3. Three Questions Before Retrying

Before letting any code perform another attempt, answer:

1. **Retryable?** Is this error likely transient according to the service contract?
2. **Safe to replay?** Does the request have idempotency semantics or a deduplication mechanism, can the body be resent, and are auth/context still valid?
3. **Budget available?** Do remaining attempt count, time, concurrency, resources, and `Retry-After` policy still allow it?

**Schedule the next attempt only when all three answers are "yes".** Jitter and backoff do not make a non-idempotent request safe.

## 2. Bounded Retry: Distinguishing Attempts, Retries, and Time Budget

Two easily confused parameters:

- `maxAttempts = 4`: **at most 4 total sends**; includes the initial attempt and at most **3 retries**.
- `maxRetries = 4`: if this naming is used, **at most 5 total sends**.

Throughout this article, examples always use **`maxAttempts`**, and `attempt` is 1-based.

~~~text
maxAttempts = 4

attempt #1  -- fail --> backoff #1
attempt #2  -- fail --> backoff #2
attempt #3  -- fail --> backoff #3
attempt #4  -- fail --> STOP (out of attempts, no extra sleep)

At most 4 network calls, 3 delays.
~~~

**Never sleep after the final attempt.** This is a common implementation bug that adds several wasted seconds to an already failed request.

### 2.1. Three Time Boundaries

A complete retry policy should include all three:

| Parameter | Meaning | Illustrative example |
| --- | --- | --- |
| `perAttemptTimeout` | How long each network call is allowed to run | 1.5 seconds |
| `totalDeadline` | Total time from request start until all retries stop | 5 seconds |
| `maxBackoff` | **Client-chosen** cap on exponential wait time | 1 second |

Suppose the overall deadline has 350ms left, while the chosen retry delay is 500ms. **Do not schedule another retry**, even if attempt slots remain: the delay would exhaust the budget before the new attempt even starts. You must also account for time for the network call to actually complete, not just enough time to sleep.

An implementation can enforce:

~~~text
time_remaining = total_deadline - elapsed
if time_remaining <= 0:
    STOP
if proposed_wait >= time_remaining:
    STOP
otherwise:
    schedule next attempt after proposed_wait
    next per-attempt timeout <= remaining time after wait
~~~

Use `System.nanoTime()` or a **monotonic** time source to measure elapsed time/deadlines; do not subtract `System.currentTimeMillis()` when the system clock can be adjusted by NTP. `Instant`/wall clock is still needed when handling **HTTP-date in `Retry-After`**; these are two different kinds of time.

**A retry budget can also be resource-based, not just time-based**: allow at most X retry tokens/second, Y concurrent requests, and Z pending tasks per service/tenant. A correct deadline that still creates thousands of unbounded scheduled futures can still cause overload.

## 3. Capped Exponential Backoff: Formula and Counting

After the **k-th failed attempt** (`k` starting at 1), if a retry is still allowed:

\[
\text{capDelay}(k)=\min(\text{maxBackoff},\ \text{baseDelay}\times 2^{k-1})
\]

Take `baseDelay = 100ms`, `maxBackoff = 500ms` as an example:

| Failed attempt | Exponential before cap | Capped delay |
| --- | ---: | ---: |
| 1 | 100ms | 100ms |
| 2 | 200ms | 200ms |
| 3 | 400ms | 400ms |
| 4 | 800ms | 500ms |
| 5 | 1,600ms | 500ms |

The wait time **does not grow forever**. The cap protects latency and prevents overflow when the attempt count is high. If `maxAttempts=5`, delays are used only after failures 1, 2, 3, and 4 — **never after failure 5**.

### 3.1. Why Not Use Arbitrary `baseDelay << (k-1)`?

In Java, a large shift can overflow or wrap via shift-masking unexpectedly; multiplying `base * (1L << n)` can also overflow. Use **saturating multiplication**:

~~~java
long cap = baseMillis;
for (int i = 1; i < failedAttempt; i++) {
    cap = cap > maxMillis / 2
            ? maxMillis
            : cap * 2;
}
~~~

This snippet is **illustrative** when `baseMillis > 0`, `maxMillis >= baseMillis`, and values fit within `long`. Once `cap` approaches the ceiling, multiplication is replaced by `maxMillis` without overflowing.

**Be careful when computing random bounds:** if using `random.nextLong(cap + 1)` to get an inclusive range up to `cap`, ensure `cap < Long.MAX_VALUE` because `cap+1` can overflow. In production, choose finite, reasonable configured durations (ms to seconds/minutes depending on workload), not `Long.MAX_VALUE` as a delay cap.

## 4. Jitter: Why Add Randomness to Wait Times?

Without jitter:

~~~text
1000 clients fail at the same time
             |
     1000 clients sleep for exactly 100ms
             |
     1000 clients wake up together ──> server overloaded again
             |
     1000 clients sleep for exactly 200ms
             |
     wake up together again ─────────> a new wave
~~~

This is a **thundering herd**: exponential backoff can still create **synchronized bursts of requests** even while reducing average frequency. Jitter gives clients different delays to spread traffic out over time.

Common variants (where `B_k` is the capped exponential delay):

| Strategy | Delay calculation | Characteristics |
| --- | --- | --- |
| **No jitter** | `B_k` | Prone to synchronization, retry bursts |
| **Full jitter** | Uniform random from `0` to `B_k` | Simple, reduces synchronization; delay can be very short or 0 |
| **Equal jitter** | `B_k / 2 + random(0..B_k/2)` | Never drops below half the cap, fewer zero-delays |
| **Decorrelated jitter** | Random in a range based on base and previous wait, then capped | Less dependent on attempt count, but stateful and harder to test |

According to AWS's analysis of exponential backoff and jitter, **full jitter** performs well in many contention scenarios. No algorithm guarantees every request succeeds; the choice also depends on quotas, latency SLAs, server hints, and workload. This article uses **full jitter as a simple default**.

### 4.1. How to Sample Full Jitter

~~~java
long delayMillis = ThreadLocalRandom.current()
        .nextLong(capMillis + 1);
~~~

This is an **illustrative Java snippet** with `capMillis` validated in `0` to `Long.MAX_VALUE-1`, requiring `import java.util.concurrent.ThreadLocalRandom`. `nextLong(bound)` returns **0 to bound-1**, so add 1 to include `capMillis`. The delay can be 0; in rate-limited systems, combine with **server minimum `Retry-After`** or a minimum delay if policy requires, rather than ignoring the server's message.

In unit tests, **do not depend on real randomness to assert stdout**. Inject a controlled strategy/random sampler—for example, always picking `cap/2`—and separately test that random delays always stay within bounds. Example 1 demonstrates this.

### 4.2. Full Jitter Is Not Adding Randomness on Top of Exponential

An anti-pattern:

~~~text
delay = cappedExponential + random(0..cappedExponential)
~~~

This pushes the delay from `B_k` up to `2B_k`, **exceeding the cap if not clamped again**, and tends to increase wait times. This **is not full jitter**. If you want randomness around `B_k`, clearly specify the range, cap, and algorithm; do not call every "+ random" full jitter.

### 4.3. Jitter Must Not Violate Server `Retry-After`

Suppose the server sends `Retry-After: 30`, meaning you should wait at least around 30 seconds before retrying. Local full jitter on a 1,000ms cap producing 125ms **must not be used to retry after 125ms**.

A common way to combine them:

~~~text
clientJitter = uniform(0, cappedExponential)
serverMinimum = parsed Retry-After (if valid/trusted)
proposedWait = max(clientJitter, serverMinimum)

if proposedWait exceeds remaining total budget:
    fail / defer request; do not silently shorten serverMinimum
else:
    schedule after proposedWait
~~~

`maxBackoff` only bounds the **local backoff** portion, not permission to bypass a rate-limit published by the peer. When the server asks to wait too long, it is usually better to **report retry-deferred/quota exceeded** for the caller to handle rather than holding thousands of scheduled tasks inside one service.

## 5. `Retry-After`: Properly Handling Both Seconds and HTTP-Date

[RFC 9110 `10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3) defines `Retry-After` as **an HTTP-date or a non-negative decimal integer indicating delay-seconds**:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 120
Content-Length: 0
~~~

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: Fri, 31 Dec 1999 23:59:59 GMT
Content-Length: 0
~~~

The header can appear on `503`, `429`, and also some `3xx` responses (with redirection semantics). Per RFC 6585, `429` **may** include the header, though it is not required. Do not try to read headers from a network-error HTTP response that has no headers.

**A production parser** must handle:
- `delay-seconds`: integer **seconds**, not milliseconds; `Retry-After: 5` means roughly **5 seconds**.
- HTTP-date: convert to UTC `Instant`; take `max(0, date - now)` to handle dates in the past.
- The RFC uses HTTP-date; `DateTimeFormatter.RFC_1123_DATE_TIME` handles the common IMF-fixdate format in Java 17; if you need to support obsolete HTTP-date formats still accepted by the HTTP spec, use a proven standard HTTP parser instead of slicing strings manually.
- `Long.parseLong`/`Duration.ofSeconds` and multiplying by 1,000 can overflow; do not let a malformed header crash the retry loop.
- Multiple header values/invalid syntax: define a clear policy (ignore, reject, or fail closed depending on trust), and never loop infinitely.
- The client clock may drift from the server clock; if accuracy matters, consider the `Date` response header, round-trip time, and clock skew instead of blindly trusting the local clock.
- Very large header values: if they exceed the deadline/quota, **stop retrying or report up for higher-level scheduling**, rather than spinning or clamping below the server minimum.

An **illustrative Java 17 utility** for common values (does not handle obsolete HTTP-date variants):

~~~java
static Optional<Duration> parseRetryAfter(
        String raw, Clock clock) {
    String value = raw.trim();
    try {
        if (value.matches("[0-9]+")) {
            return Optional.of(
                    Duration.ofSeconds(Long.parseLong(value)));
        }

        Instant target = ZonedDateTime.parse(
                value, DateTimeFormatter.RFC_1123_DATE_TIME)
                .toInstant();
        Duration until =
                Duration.between(clock.instant(), target);
        return Optional.of(
                until.isNegative() ? Duration.ZERO : until);
    } catch (DateTimeParseException
             | ArithmeticException invalid) {
        return Optional.empty();
    }
}
~~~

This is an **illustrative snippet inside a utility class/method**, requiring imports `java.time.*`, `java.time.format.DateTimeFormatter`, `java.time.format.DateTimeParseException`, `java.util.Optional`, and callers must pass a non-null `raw`. The `catch` block covers invalid numeric values; do not treat `Optional.empty()` as proof the server "allows immediate retry". If the header cannot be parsed and policy requires honoring it, you may **fail/defer** instead of falling back to an overly short delay.

With `HttpResponse<?>`, read the header using `response.headers().firstValue("Retry-After")` rather than relying on letter casing. Do not trust `Retry-After` from an endpoint outside your trust boundary to enqueue an unbounded scheduler.

## 6. Retry Safety: Idempotency Matters More Than Backoff Formulas

[RFC 9110 `9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2) describes idempotency as the **intended effect** of repeating a request multiple times being the same as executing it once. Safe HTTP methods like GET/HEAD are typically idempotent; PUT/DELETE also have idempotent semantics. `POST` is not idempotent by default.

| Method / operation | Retry when response does not arrive? | Things to watch |
| --- | --- | --- |
| `GET /products` | Usually yes | Data may change between attempts; deadline still needed |
| `HEAD /health` | Usually yes | Do not treat success as a transaction guarantee |
| `PUT /resource/42` setting same desired state | Possible per contract | ETag/version precondition may cause later attempts to get 412 |
| `DELETE /resource/42` | Usually idempotent in intended effect | Later response may be 404 even though effect was achieved |
| `POST /payments` | **Not by default** | Can charge twice |
| `POST /payments` with server-supported Idempotency-Key | Possible **if** API has dedupe contract | Key scope, TTL, payload consistency, replay, retry policy |
| Streaming upload from an already-read `InputStream` | No if body cannot be recreated | Needs a supplier that opens a new stream with identical bytes |

For example, a POST request might have already recorded an order before the TCP connection drops prior to the response; the client only sees an `IOException`. Retrying immediately will record a **second order** if the backend does not deduplicate. The solution is not in jitter:
1. The client generates a unique `operationId` or **Idempotency-Key** for one logical operation.
2. The backend persists the key along with the result/transaction state under a clear scope and TTL.
3. Retry with the same key and **same payload semantics**.
4. The server returns the same result or confirmed state per the API contract.
5. If unsure whether the backend supports it, **do not enable `POST` retries**.

**Idempotency on an HTTP method does not mean "every system implements it correctly."** A poorly designed API's GET can still cause side effects; the client must know the endpoint's contract. POST with an idempotency key is only safe within the key semantics guaranteed by the server. And retries do not provide "exactly-once" in a distributed system; they only help manage the probability of duplicates.

### 6.1. Replayable Request Bodies in Java 17

`HttpRequest.BodyPublishers.ofString(...)` or `ofByteArray(...)` are usually suitable when the payload can be reused. For streaming:

~~~java
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofInputStream(
                () -> Files.newInputStream(path));
~~~

This is an **illustration that may need `IOException` handling inside the lambda**: `Files.newInputStream(path)` throws a checked `IOException`, so the example **is not complete copy-pasteable code that compiles directly**; a version usable inside a Java method could be:

~~~java
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofInputStream(() -> {
            try {
                return Files.newInputStream(path);
            } catch (IOException failure) {
                throw new UncheckedIOException(failure);
            }
        });
~~~

The second snippet is **syntactically valid illustrative code** given `path` and imports `java.nio.file.Files`, `java.io.*`, `java.net.http.HttpRequest`. The Javadoc for `BodyPublishers.ofInputStream(Supplier<? extends InputStream>)` uses a supplier **because the request may need to be repeated**; each subscription can open a fresh `InputStream`. A supplier that always returns **the same already-consumed `InputStream`** is wrong.

To guarantee the same body across retries, the source file/stream must remain stable (snapshot/checksum/version) throughout the logical request. If the file changes between attempts, sending the same idempotency key with a different payload can cause the backend to reject it or corrupt state. **Do not retry a non-replayable stream just because code can call `sendAsync` again.**

## 7. Classifying Java Errors Instead of `catch(Exception) { retry(); }`

`java.net.http.HttpClient` has two failure paths:

1. **An HTTP response is received:** `client.send(req, handler)` returns an `HttpResponse<T>` with `statusCode()` (including 429/503). HTTP 503 itself **does not throw `IOException` just because the status is 503**.
2. **No complete response is received:** `send` can throw `IOException`, `InterruptedException`; `sendAsync` can complete exceptionally.

You should not retry every exception indiscriminately. Evaluate:

| Exception / status | Example cause | Guidance |
| --- | --- | --- |
| `java.net.http.HttpTimeoutException` | Attempt exceeded request timeout | May be transient; check idempotency and total budget |
| `ConnectException` | Service not listening, proxy refused | May be temporary or misconfigured; endpoint-specific policy |
| `SocketTimeoutException` | Read/connect timeout in older socket API | May be temporary; does not prove server did not process |
| `SocketException: Connection reset` | Network/peer reset | Safe operations may be retried |
| `UnknownHostException` | DNS resolution failed | Usually requires fixing DNS/hostname; avoid continuous retries |
| `SSLHandshakeException` | Certificate/TLS protocol/identity mismatch | Do not retry blindly, do not disable TLS validation |
| `InterruptedException` | Caller/thread requested stop | **Stop**, propagate or restore interrupt |
| `CancellationException` | Request cancelled | **Stop**, do not restart automatically |
| `CompletionException`/`ExecutionException` | Wrapper around async failure | Unwrap cause before classifying |
| `IllegalArgumentException` from building request | Invalid request config | Do not retry |
| `429/503` response | Server returned status | Use status policy and `Retry-After` |

An `IOException` can also come from a request-body file read error, a write-to-file error, or a full filesystem—not a transient network issue. If the transport does not clearly confirm the source, retrying all `IOException`s can be unsafe. The async demo in section 11 uses **simulated `IOException`s**, so its "retry on `IOException`" policy does not represent production classification.

## 8. Java 17+ Example 1: Testable Capped Exponential + Full Jitter Calculation

This example **uses no network**, separating retry math from HTTP. Policy:
- `maxAttempts = 5`: at most 5 attempts and 4 delays.
- `baseMillis = 100`, `maxMillis = 500`.
- `cappedExponentialMillis` performs saturating doubling without overflow.
- `chooseFullJitter` accepts a random sampler function and validates that the value lies in `[0, cap]`.
- In the unit-demo, the sampler **intentionally picks `cap/2`** so stdout is always deterministically repeatable. It **is not production randomness**.
- Afterward, the program tries `ThreadLocalRandom` once and only asserts the range, **without printing the random value**.

Create **`RetryBackoffMathDemo.java`**:

~~~java
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.LongUnaryOperator;

public final class RetryBackoffMathDemo {
    static long cappedExponentialMillis(
            int failedAttempt, long baseMillis, long maxMillis) {
        if (failedAttempt < 1 || baseMillis < 1
                || maxMillis < baseMillis
                || maxMillis == Long.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "Invalid retry policy");
        }

        long cap = baseMillis;
        for (int i = 1; i < failedAttempt; i++) {
            cap = (cap > maxMillis / 2)
                    ? maxMillis
                    : cap * 2;
        }
        return cap;
    }

    static long chooseFullJitter(
            long capMillis, LongUnaryOperator pickExclusive) {
        long candidate =
                pickExclusive.applyAsLong(capMillis + 1);
        if (candidate < 0 || candidate > capMillis) {
            throw new IllegalArgumentException(
                    "Jitter out of range");
        }
        return candidate;
    }

    public static void main(String[] args) {
        int maxAttempts = 5; // 1 initial + at most 4 retries
        long accumulated = 0;

        LongUnaryOperator deterministic =
                bound -> (bound - 1) / 2;

        for (int failed = 1;
                failed < maxAttempts;
                failed++) {
            long cap = cappedExponentialMillis(
                    failed, 100, 500);
            long delay = chooseFullJitter(
                    cap, deterministic);
            accumulated += delay;
            System.out.println(
                    "failure=" + failed
                    + " cap=" + cap
                    + " deterministicDelay=" + delay);
        }

        System.out.println(
                "total deterministic wait=" + accumulated);

        long actualRandom = chooseFullJitter(500,
                bound -> ThreadLocalRandom.current()
                        .nextLong(bound));
        System.out.println(
                "random within 0..500: " +
                (actualRandom >= 0 && actualRandom <= 500));
    }
}
~~~

~~~bash
javac --release 17 RetryBackoffMathDemo.java
java RetryBackoffMathDemo
~~~

Stdout **tested and independent of random seed**:

~~~text
failure=1 cap=100 deterministicDelay=50
failure=2 cap=200 deterministicDelay=100
failure=3 cap=400 deterministicDelay=200
failure=4 cap=500 deterministicDelay=250
total deterministic wait=600
random within 0..500: true
~~~

**Explanation:**
- Failure 1: cap=100, test sampler picks 50ms.
- Failure 2: cap=200, picks 100ms.
- Failure 3: cap=400, picks 200ms.
- Failure 4: exponential gives 800 but cap=500, picks 250ms.
- Total test delay 50+100+200+250=**600ms** if all four retries occur. This total **does not include the execution time of each request**.
- Real jitter sampling with `ThreadLocalRandom` returns a different value per run; only the boolean bounds check is printed to keep stdout stable.
- `chooseFullJitter` requires the sampler to return a number in range, but **does not itself guarantee uniform distribution**. Production uses `ThreadLocalRandom.current().nextLong(bound)` or an appropriate random generator; the deterministic sampler is for tests only.
- `cappedExponentialMillis` has O(failedAttempt) complexity and handles reasonable attempt counts; there is no need to compute `Math.pow(2,k)` via `double` and cast to `long` (which can lose precision or overflow).

In production, test overflow, invalid base/cap, `maxAttempts=1`, zero/negative durations, time budget sources, and ensuring no delays are generated after the final attempt.

## 9. Java 17+ Example 2: HTTP Loopback, Retrying 503 for Exactly Three Attempts

This example uses the JDK's `HttpServer` to create a **loopback-only** server without calling external APIs:
- Request 1 returns `503` and `Retry-After: 0`.
- Request 2 also returns `503` and `Retry-After: 0`.
- Request 3 returns `200` with body `ready`.
- The client uses an **idempotent GET**, `maxAttempts=3`, reads the full response body via `BodyHandlers.ofString()`, and then decides whether to retry.
- The delay uses **deterministic test jitter** `cap/2`: 5ms and 10ms. This sample uses `Thread.sleep` only to demonstrate synchronous retries in a console test; do not use this pattern on event loops or high-load request-serving threads.

Create **`HttpBoundedRetryDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

public final class HttpBoundedRetryDemo {
    private static boolean retryableStatus(int code) {
        return code == 429 || code == 503;
    }

    public static void main(String[] args)
            throws Exception {
        AtomicInteger calls = new AtomicInteger();
        InetAddress loopback =
                InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);

        server.createContext("/read", exchange -> {
            int number = calls.incrementAndGet();
            boolean temporary = number <= 2;
            String message =
                    temporary ? "busy" : "ready";
            byte[] body = message.getBytes(
                    StandardCharsets.UTF_8);
            if (temporary) {
                exchange.getResponseHeaders()
                        .set("Retry-After", "0");
            }

            exchange.sendResponseHeaders(
                    temporary ? 503 : 200,
                    body.length);
            try (OutputStream out =
                    exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();

        try {
            URI url = new URI(
                    "http", null, loopback.getHostAddress(),
                    server.getAddress().getPort(),
                    "/read", null, null);

            HttpClient client = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request =
                    HttpRequest.newBuilder(url)
                            .timeout(Duration.ofSeconds(3))
                            .GET().build();

            final int maxAttempts = 3;
            HttpResponse<String> result = null;

            for (int attempt = 1;
                    attempt <= maxAttempts;
                    attempt++) {
                result = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString());
                System.out.println(
                        "attempt=" + attempt
                        + " status=" + result.statusCode());

                if (!retryableStatus(result.statusCode())
                        || attempt == maxAttempts) {
                    break;
                }

                long capMillis =
                        Math.min(40L, 10L << (attempt - 1));
                long deterministicJitter =
                        capMillis / 2;

                long serverMinMillis = result.headers()
                        .firstValue("Retry-After")
                        .map(Long::parseLong)
                        .map(seconds -> seconds * 1000)
                        .orElse(0L); // test server only sends "0"

                long delayMillis = Math.max(
                        deterministicJitter,
                        serverMinMillis);
                System.out.println(
                        "backoff ms=" + delayMillis);
                Thread.sleep(delayMillis);
            }

            System.out.println(
                    "final body=" + result.body());
            System.out.println(
                    "origin calls=" + calls.get());
        } finally {
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac --release 17 HttpBoundedRetryDemo.java
java HttpBoundedRetryDemo
~~~

Stdout **verified on a local JDK**:

~~~text
attempt=1 status=503
backoff ms=5
attempt=2 status=503
backoff ms=10
attempt=3 status=200
final body=ready
origin calls=3
~~~

**Key takeaways:**

1. `HttpResponse<String>` with status 503 is returned as a normal HTTP response; you do not need `catch(IOException)` to detect the status.
2. `GET` fits the replay example because it is read-only/idempotent in intended effect per HTTP semantics. Do not swap `GET` for `POST /payments` while keeping the retry loop as-is.
3. `maxAttempts=3` means at most 3 HTTP calls, with no third backoff after receiving 200.
4. `BodyHandlers.ofString()` consumes the full body before returning the response, avoiding abandoned streaming bodies from failed attempts. For large error bodies, production should use bounded response handling instead of buffering indefinitely.
5. `Retry-After: 0` is **0 seconds**, so the delay is chosen from the local deterministic jitter. The demo code **only parses numeric headers with `Long.parseLong` and is not a production parser**; if the server sends an HTTP-date or a very large number, use the utility from section 5.
6. `Math.max(localJitter,serverMinMillis)` does not truncate the server wait; in production, also compare against the **remaining total deadline** before sleeping.
7. `Thread.sleep` here is for a few milliseconds in a one-off console test. Do not tie up one worker thread per queued retry when there are tens of thousands of clients; use a scheduler and backpressure.
8. The request sets `HttpRequest.Builder.timeout(Duration.ofSeconds(3))` per attempt, but **does not set a total deadline for the whole loop**. This demo illustrates count/status/backoff, not a complete retry utility. The async sample in section 11 shows **totalBudget + watchdog**.

If the runtime lacks the `jdk.httpserver` module, or the sandbox disallows binding loopback, the program may throw an environment error. No Internet, external DNS, or credentials are needed.

## 10. Asynchronous Backoff: Why Not Block a Thread Waiting to Retry?

An anti-pattern for high-load servers:

~~~java
// One request per worker thread:
while (shouldRetry) {
    Thread.sleep(delayMillis);
    callRemoteService();
}
~~~

This is **pseudocode** with undefined `shouldRetry`, `delayMillis`, and `callRemoteService`. If 5,000 requests fail temporarily at once and each thread sleeps for 10 seconds, the system can require a huge number of blocked threads and memory stacks. Instead:

~~~text
HTTP async attempt #1
    |
 CompletableFuture exceptionally: transient
    |
 compute jitter + check deadline/count
    |
 ScheduledExecutorService.schedule(nextAttempt, wait)
    |   (does not occupy a thread while waiting)
    v
HTTP async attempt #2
    |
 complete success/failure
~~~

`ScheduledExecutorService.schedule(Runnable,delay,unit)` schedules execution **after a relative delay** and returns a cancellable `ScheduledFuture`. One scheduler thread can manage many scheduled tasks, though **the scheduler queue still consumes memory**; bound the number of outstanding retries and do not enqueue without limit.

Each logical operation needs:
- A `CompletableFuture<Result>` returned to the caller.
- State holding `attemptNumber` and a monotonic deadline.
- A reference to the in-flight HTTP future so it can be cancelled if the caller abandons the request.
- A scheduled timer for the next attempt and a **total-budget watchdog**.
- An injectable source of randomness for testing (or a fixed test sampler).
- A policy classifying status/exception **before** scheduling a retry.
- Explicit shutdown so scheduler threads do not linger after application stop.

Do not use `scheduleAtFixedRate` or `scheduleWithFixedDelay` as a generic timer for each request attempt: those are **periodic** task APIs that easily spawn multiple attempts unrelated to the previous request's completion. For retries, use a **one-shot schedule** after the attempt result has been classified.

## 11. Java 17+ Example 3: Scheduler, Bounded Attempts, Watchdog, and Cancellation

This example tests the **async state machine** with a `Supplier<CompletableFuture<String>>`, without making real network calls. It tests four branches:

1. The first two attempts complete with `IOException("temporary")`; attempt 3 succeeds with `"ready"`.
2. An operation always fails; `maxAttempts=2` makes it stop after exactly 2 attempts and return the underlying error.
3. The caller cancels a pending operation; cancellation is propagated to the in-flight future.
4. The operation never completes; the **totalBudget watchdog** completes the result with `TimeoutException` and cancels the underlying future.

To keep stdout deterministic, the code uses `cap/2` delay instead of real randomness; a production version replaces the sampler with full jitter from section 8. The code limits `maxAttempts<=8` so the bit shift in the demo cannot overflow; real systems can use the saturating function from section 8 and a small attempt policy.

Create **`AsyncRetrySchedulerDemo.java`**:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.Supplier;

public final class AsyncRetrySchedulerDemo {
    static CompletableFuture<String> retryAsync(
            Supplier<CompletableFuture<String>> action,
            ScheduledExecutorService scheduler,
            int maxAttempts,
            Duration totalBudget) {

        if (maxAttempts < 1 || maxAttempts > 8
                || totalBudget.isNegative()
                || totalBudget.isZero()) {
            throw new IllegalArgumentException(
                    "Invalid retry budget");
        }

        Objects.requireNonNull(action);
        Objects.requireNonNull(scheduler);

        long started = System.nanoTime();
        long allowedNanos = totalBudget.toNanos();
        CompletableFuture<String> result =
                new CompletableFuture<>();

        AtomicReference<CompletableFuture<String>> active =
                new AtomicReference<>();
        AtomicReference<ScheduledFuture<?>> waiting =
                new AtomicReference<>();

        ScheduledFuture<?> watchdog = scheduler.schedule(
                () -> result.completeExceptionally(
                        new TimeoutException(
                                "Total budget exceeded")),
                allowedNanos, TimeUnit.NANOSECONDS);

        class Runner {
            void attempt(int number) {
                if (result.isDone()) return;

                if (System.nanoTime() - started >= allowedNanos) {
                    result.completeExceptionally(
                            new TimeoutException(
                                    "Total budget exceeded"));
                    return;
                }

                CompletableFuture<String> current;
                try {
                    current = Objects.requireNonNull(
                            action.get());
                } catch (RuntimeException failure) {
                    current = CompletableFuture.failedFuture(
                            failure);
                }
                active.set(current);

                current.whenComplete((value, failure) -> {
                    if (result.isDone()) return;

                    if (failure == null) {
                        result.complete(value);
                        return;
                    }

                    Throwable cause =
                            failure instanceof CompletionException
                            ? failure.getCause()
                            : failure;

                    if (!(cause instanceof IOException)
                            || number == maxAttempts) {
                        result.completeExceptionally(cause);
                        return;
                    }

                    long capMs =
                            Math.min(80L,
                                    10L << (number - 1));
                    long delayMs = capMs / 2;
                    // Demo: deterministic test sample.

                    long remaining = allowedNanos -
                            (System.nanoTime() - started);
                    if (remaining <= TimeUnit.MILLISECONDS
                            .toNanos(delayMs)) {
                        result.completeExceptionally(
                                new TimeoutException(
                                        "No retry time left"));
                        return;
                    }

                    try {
                        waiting.set(scheduler.schedule(
                                () -> attempt(number + 1),
                                delayMs,
                                TimeUnit.MILLISECONDS));
                    } catch (RejectedExecutionException rejected) {
                        result.completeExceptionally(rejected);
                    }
                });
            }
        }

        result.whenComplete((value, failure) -> {
            watchdog.cancel(false);

            ScheduledFuture<?> timer =
                    waiting.getAndSet(null);
            if (timer != null) timer.cancel(false);

            if (result.isCancelled()
                    || failure instanceof TimeoutException) {
                CompletableFuture<String> call =
                        active.get();
                if (call != null) call.cancel(true);
            }
        });

        new Runner().attempt(1);
        return result;
    }

    public static void main(String[] args)
            throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        try {
            AtomicInteger started = new AtomicInteger();
            CompletableFuture<String> recovered =
                    retryAsync(() -> {
                        int attempt =
                                started.incrementAndGet();
                        System.out.println(
                                "async start=" + attempt);
                        return attempt < 3
                                ? CompletableFuture.failedFuture(
                                        new IOException("temporary"))
                                : CompletableFuture.completedFuture(
                                        "ready");
                    }, scheduler, 4,
                    Duration.ofSeconds(2));

            System.out.println(
                    "async result=" +
                    recovered.get(
                            3, TimeUnit.SECONDS));

            AtomicInteger failed = new AtomicInteger();
            CompletableFuture<String> stopped =
                    retryAsync(() -> {
                        failed.incrementAndGet();
                        return CompletableFuture.failedFuture(
                                new IOException(
                                        "still unavailable"));
                    }, scheduler, 2,
                    Duration.ofSeconds(2));

            try {
                stopped.get(3, TimeUnit.SECONDS);
            } catch (ExecutionException expected) {
                System.out.println(
                        "exhausted attempts=" +
                        failed.get());
                System.out.println(
                        "last error=" +
                        expected.getCause()
                                .getClass().getSimpleName());
            }

            CompletableFuture<String> never =
                    new CompletableFuture<>();
            CompletableFuture<String> cancelled =
                    retryAsync(() -> never,
                            scheduler, 4,
                            Duration.ofSeconds(2));
            cancelled.cancel(true);
            System.out.println(
                    "cancel reached in-flight: " +
                    never.isCancelled());

            CompletableFuture<String> neverEnds =
                    new CompletableFuture<>();
            CompletableFuture<String> timedOut =
                    retryAsync(() -> neverEnds,
                            scheduler, 1,
                            Duration.ofMillis(30));
            try {
                timedOut.get(1, TimeUnit.SECONDS);
            } catch (ExecutionException expected) {
                System.out.println(
                        "budget timeout: " +
                        expected.getCause()
                                .getClass().getSimpleName());
            }

            System.out.println(
                    "timeout cancelled in-flight: " +
                    neverEnds.isCancelled());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac --release 17 AsyncRetrySchedulerDemo.java
java AsyncRetrySchedulerDemo
~~~

Stdout **verified on a local JDK**:

~~~text
async start=1
async start=2
async start=3
async result=ready
exhausted attempts=2
last error=IOException
cancel reached in-flight: true
budget timeout: TimeoutException
timeout cancelled in-flight: true
~~~

**How the code works:**

- `retryAsync` creates a **single shared future for the entire logical operation**, rather than returning a new future per attempt to the caller.
- `Runner.attempt(1)` invokes the supplier once. When the future fails with `IOException`, the callback checks attempts/budget and uses `scheduler.schedule(...)` to start the next attempt **after the delay**. During the wait, no thread is blocked by `sleep`.
- `watchdog` schedules once for `totalBudget`. If an in-flight future never completes, the watchdog **can still terminate the operation**; checking remaining budget before retrying is not enough to catch a permanently hung future.
- When `result` completes, the callback cancels the watchdog and timer. On caller cancellation or timeout, it attempts to cancel the in-flight future. With a real `HttpClient.sendAsync`, cancellation is **best-effort**, and the server may still have processed the request.
- In the test, `CompletableFuture.failedFuture(new IOException(...))` simulates transient errors; **do not make all `IOException`s retryable in production**. Apply the policy from section 7.
- `result.completeExceptionally(lastError)` preserves the last cause when attempts are exhausted. `get()` wraps the cause in `ExecutionException`; the caller must unwrap the cause.
- `retryAsync` bounds attempt count and deadline; it does **not** yet bound the number of concurrent *logical calls* or scheduler queue length. In production, add a semaphore/global retry budget and metrics.
- `then/whenComplete` callbacks can run on the thread completing the future or on the scheduler; do not run blocking work inside callbacks.
- `Duration.toNanos()` can overflow for huge durations; the example uses reasonable durations ≤ a few seconds. Production should validate upper bounds before conversion.
- `AtomicReference` shares handles across scheduler/callback/caller; cleanup logic must account for races when completion and cancellation happen nearly simultaneously. This is a state-machine learning example, **not a general-purpose retry framework proven linearizable under every race**.
- `scheduler.shutdownNow()` is only used because the console program owns the executor. In a server, pass a centrally managed scheduler; do not create and destroy a thread pool per retry.

### 11.1. Connecting the Async State Machine to HttpClient

A conceptual integration:

~~~java
// Illustrative snippet in a class with HttpClient client and HttpRequest req:
Supplier<CompletableFuture<HttpResponse<String>>> action =
        () -> client.sendAsync(
                req, HttpResponse.BodyHandlers.ofString());
~~~

To use a generic utility typed with `HttpResponse<String>`, adjust the type parameter and classify the response **status** in the callback rather than only failure exceptions. An `HttpResponse` with status `503` is still a **successful `CompletableFuture` completion**, so if you only retry when `failure != null` as in demo 3, it **will not retry 503**.

A production design should return an `AttemptOutcome<T>` type distinguishing:
- `Success(value)`.
- `RetryableStatus(status, headers, bodyAlreadyConsumed)`.
- `RetryableTransportFailure(cause)`.
- `PermanentFailure(status/cause)`.

A dispatcher decides in **a single place** before scheduling, avoiding different callers implementing their own retries and causing retry storms.

### 11.2. Cancelling Futures and Deadlines

The Java 17 Javadoc for `HttpClient.sendAsync` states that the default implementation returns cancellable futures. Calling `cancel(true)` on an incomplete future will **attempt** to cancel the HTTP exchange to free resources, with **no guarantee of exact timing**. For HTTP/1.1 it may close the connection; for HTTP/2 it may reset the stream. This does not guarantee the server has not processed the request. If the operation has an idempotency key, retry/reconciliation must still follow the business contract.

A coroutine or reactive implementation needs the same rules: when the downstream caller cancels, cancel the scheduled retry timer, the in-flight HTTP attempt, and any retained body buffers; do not resurrect cancelled work.

## 12. Backoff Does Not Solve Overload When Retrying Across Multiple Layers

Suppose a request travels through:

~~~text
Web UI -> API Gateway -> Service A -> Service B -> Database
                 │          │          │          │
              3 attempts  3 attempts  3 attempts  3 attempts
~~~

If all four layers independently retry each downstream call up to 3 times, the worst-case number of operations at the bottom **can multiply to 3×3×3×3 = 81** for one logical user request (ignoring other limits). Jitter at each layer alone does not solve retry amplification.

A better strategy:
1. Designate a **retry owner** at the most appropriate layer, or a very deliberate small set of layers.
2. Propagate **deadline context** to downstream calls; do not grant a fresh unbounded budget at every hop.
3. Use a **retry budget per service/tenant** (token bucket or ratio of retries to initial calls).
4. Respect `Retry-After`, server overload/quota hints, and circuit breakers.
5. Bound concurrency + queues + load shedding; do not let an overloaded service receive more retries than initial traffic.
6. Do not retry from the UI layer while the backend is still retrying unless there is an explicit contract.
7. Propagate a correlation ID to identify **attempt 2 of the same logical call**, rather than treating it as a brand-new independent transaction.

### 12.1. Retry Budget vs. `maxAttempts`

`maxAttempts=4` protects **one logical operation**. But if 100,000 concurrent logical operations all retry 3 times, the service still receives 300,000 extra requests. An **overall retry budget** protects at the system/tenant level—for example, allowing at most 20% of requests to be retries within a measurement window (illustrative value only).

Illustrative calculation:

~~~text
Within a quota window:
  initial attempts = 1000
  retry tokens max = 200
  retries used = 200

A logical request still has maxAttempts left but no retry token:
  -> fail/defer per policy, make no further network call.
~~~

You can use a token bucket with controlled refill, independent jitter and randomness, without automatically queueing every request indefinitely. Avoid minting retry tokens based on successes skewed by retries without thinking through feedback loops.

### 12.2. Circuit Breaker, Rate Limiter, and Retry Do Not Replace Each Other

| Mechanism | Role |
| --- | --- |
| Bounded retry | Increase chance of riding out short-lived errors at bounded cost |
| Exponential backoff | Space out attempts as failures accumulate |
| Jitter | Break synchronization across multiple retrying clients |
| Total deadline/timeout | Prevent holding a logical operation for too long |
| Rate limiting | Bound traffic per time window/tenant |
| Concurrency limiter/bulkhead | Prevent exceeding in-flight/thread/socket limits |
| Circuit breaker | Temporarily stop calling a dependency with a high failure rate |
| Idempotency/dedup | Reduce risk of repeating business side effects |
| Cache/fallback | Serve alternative data when a dependency fails (if business allows) |

**Retry is not "turn it on and it gets healthier"**: when downstream is overloaded, extra attempts can increase latency and failure rates. If the circuit is open, retry attempts should be blocked by the circuit policy.

## 13. Scenarios Requiring Careful Thought

### 13.1. `429 Too Many Requests` with a 60-Second Server Quota

If you receive:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
~~~

While the user deadline only has 3 seconds left, do **not** retry after 200ms just because local jitter is small. Stop and return an appropriate failure/quota response, or hand the work to a job queue with a controlled longer deadline. Do not hold a request thread or connection open indefinitely waiting 60s.

### 13.2. Connection Drops After a Money-Transfer POST

The client may have sent the payload, the server may have committed, and TCP resets while returning the response. The client sees an exception without knowing whether the transaction occurred. **Do not retry POST blindly**, even with a very long delay. You need an idempotency key, server lookup/reconciliation, or an event ID to verify state. Jitter only spreads load; it does not reduce duplicate side effects.

### 13.3. DNS `UnknownHostException`

If a domain is misspelled, retrying hundreds of times will not help. If service discovery has a temporary hiccup, a few policy-governed retries may be allowed, but there must be a DNS timeout and fallback checks; do not lump every `IOException` into the retry bucket while ignoring configuration errors.

### 13.4. Response Body Streamed Mid-Flight

If the body handler returns an `InputStream` from `HttpClient`, the response future can complete **when headers arrive** even before body EOF. If reading the body later throws `IOException`, retrying requires:
- Closing/cancelling the old body to avoid resource leaks.
- Determining whether the entire request can be replayed.
- Determining whether the downstream consumer already received partial data and caused side effects; if so, roll back, offset, or deduplicate.
- Deleting temporary/partial output bytes or resuming with HTTP Range/ETag if the protocol allows, instead of appending duplicate bytes.
- Total deadline and attempt budget still apply.

Using `BodyHandlers.ofString()` in the demo simplifies this because the body is tiny and consumed before returning.

### 13.5. Expired Authentication/Token

When receiving `401`, you usually need to **refresh credentials per the auth contract**, rather than retrying the exact same token 5 times. When refreshing, prevent multiple threads from refreshing simultaneously using bounded single-flight logic. Do not log tokens or bypass TLS verification to "fix" HTTP errors.

### 13.6. Timeout While Request Is Still Processing

The client times out after 2 seconds while the server needs 3 seconds. If it retries immediately, the server may process both tasks concurrently. For idempotent REST reads, extra load may be acceptable within a retry budget; for writes, an idempotency token is required. Do not treat a timeout as a signal that the server cancelled the work.

### 13.7. Application Shutdown or User Cancellation

When the application shuts down, scheduled retries must be cancelled; do not wait for `maxAttempts` to finish. For Java `InterruptedException`:

~~~java
try {
    Thread.sleep(delayMillis);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw interrupted;
}
~~~

This is an **illustrative snippet inside a method that `throws InterruptedException`** with a known `delayMillis`. Do not swallow the interrupt and keep retrying, because the user or shutdown has requested a stop.

## 14. Tuning Policy by SLA and Load—No Magic Numbers

The following parameters are **illustrative starting configurations for discussion**, not mandatory values for every service:

| Operation type | maxAttempts | baseDelay | maxBackoff | Total deadline | Guidance |
| --- | ---: | ---: | ---: | ---: | --- |
| Lightweight GET read from internal dependency | 3 | 50ms | 500ms | 2s | Full jitter, per-attempt timeout based on RTT |
| Quota-limited external API GET | 2–3 | 500ms | 5s | Per SLA/quota | Prioritize `Retry-After`; defer if quota window is too long |
| Idempotent background job | 4–6 | 1s | 30s | Per job deadline | Jitter and bounded persistent queue |
| POST financial command without dedup | 1 | — | — | Per business SLA | Do not auto-retry |
| POST with backend-supported idempotency key | Per contract | Per SLA | Capped | Per deadline | Same key/payload, reconcile ambiguous results |
| Health checks | 1–2 | Short | Short | Very short | Do not create a retry storm overloading the health service |

**Do not copy these numbers blindly** without measuring p50/p95/p99 latency, error durations, quota limits, server capacity, connection pooling, user-facing timeouts, and downstream retry ownership.

Backoff that is too short causes load spikes; too long inflates latency and misses recovery windows; `maxAttempts` that is too large causes request amplification. Appropriate jitter reduces synchronization but does not replace capacity planning.

### 14.1. Deriving Parameters from Telemetry

Observe:
- Rate of transient failures and server recovery time.
- Duration of successful vs. failed attempts; p95/p99.
- Distribution of `Retry-After` (low/high/absent).
- Retries per logical operation and fraction succeeding after retry.
- Total requests generated by retries.
- Queue age, concurrency, memory, and cancellation counts.
- Business duplicates and idempotency conflicts.
- Failures due to exhausted attempts vs. expired deadline vs. exhausted retry budget.

For a downstream that regularly has 20-minute 503s, retrying inside a 30-second synchronous HTTP request is the wrong architecture; use a job queue, circuit breaker, and business-level deferred processing.

## 15. Logging and Metrics That Preserve Attempt Meaning

A retry-friendly log should include:
- `logicalRequestId` / trace ID across **one logical operation**.
- `attemptNumber` and `maxAttempts`.
- `httpMethod`, sanitized target service/operation (never log access tokens).
- `retryDecision`: `success`, `retryable_status`, `transient_io`, `permanent`, `exhausted`, `deadline`, `cancelled`, `circuit_open`.
- `backoffCapMillis`, `selectedJitterMillis`, and `retryAfterMillis` (if present), `effectiveWaitMillis`.
- `elapsedMillis`, `remainingBudgetMillis`.
- `requestBodyReplayable` or idempotency policy (do not log full bodies).
- Correlation with server `429/503` and service-side rate limiter metrics.

Useful metrics:

| Metric | Purpose |
| --- | --- |
| `request_initial_total` | Volume of initial logical calls |
| `retry_attempt_total` | Extra attempts, labeled by reason |
| `retry_exhausted_total` | Exhausted attempt counts |
| `retry_deadline_total` | Expired total time budgets |
| `retry_budget_rejected_total` | Retries rejected by token/concurrency budget |
| `retry_cancelled_total` | Cancelled by caller or shutdown |
| `retry_delay_ms` histogram | Spread of wait durations |
| `retry_success_after_attempt` | Actual recovery value of retries |
| `inflight_dependency_requests` | Concurrency protection |
| `server_429_total` / `server_503_total` | Signals of quota/overload |
| `idempotency_dedup_total` | Detects retried writes deduplicated by backend |

Do not treat **retry success rate** as good performance if each success requires many extra requests and increases total latency. Track success rate **per logical operation** alongside total work/amplification and tail latency.

## 16. Bounded Retry Test Checklist

### 16.1. Deterministic Unit Tests

1. `maxAttempts=1`: exactly **one** call, no sleep.
2. `maxAttempts=3`: **at most 3 calls**, at most 2 delays.
3. Verify exponential sequence with cap: base=100ms, max=500ms → 100, 200, 400, 500, 500...
4. Full jitter always stays within `0..cap`; test injectable RNG with a fixed function/seed.
5. Saturating arithmetic does not overflow on large attempt numbers.
6. `Retry-After: 120` is parsed as 120 **seconds**, not 120ms.
7. Past `Retry-After` HTTP-date → wait 0; future → positive wait.
8. `Retry-After` larger than total budget → **do not retry early**.
9. Retryable statuses 503/429 are classified; non-retryable 400/401/403/404 are not repeated.
10. Ambiguous network failure on non-idempotent POST → do not retry.
11. Non-replayable `BodyPublisher` → fail/defer, do not resend an EOF stream.
12. Deadline expires before scheduled attempt → do not start a new network call.
13. Watchdog expires while in-flight hangs → result times out and cancels underlying call.
14. Caller cancels during sleep/scheduled timer → timer cancelled, no next attempt made.
15. Scheduler `RejectedExecutionException` → result fails cleanly, does not hang.
16. Multiple concurrent callers: total retries and throttled queue stay within budget.

### 16.2. Integration Tests

Set up a loopback/mock HTTP server and scenarios:
- 503→503→200 with `Retry-After: 0`: exactly 3 calls and succeeds.
- Continuous 503: stops at `maxAttempts`, no sleep after the last attempt.
- 429 with `Retry-After: 60` inside a 2s deadline: stops, does not resend.
- Persistent 404: 1 call.
- Oversized response body / cancellation during streaming: resources closed cleanly.
- Network reset after server receives POST: idempotency key prevents duplicates.
- Two hundred clients hit 503 simultaneously: jitter reduces clustering; observe request distribution.
- Downstream circuit open: no automatic multi-layer retries.
- Load test with retry budget: when server is overloaded, extra attempts are capped.
- After client closes, no scheduled retries or in-flight tasks remain outside policy.

In test environments, use injected clocks/RNG and virtual/mock schedulers when available so unit tests stay fast and non-flaky. For integration tests using real wall time, set timeouts wide enough for CI while still bounded; do not rely on millisecond-accurate OS sleeps.

## 17. Most Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `while(true)` infinite retry | Floods server, hangs user request | `maxAttempts` + `totalDeadline` |
| Counting `maxRetries` as `maxAttempts` | Sends one extra time | Define counter clearly |
| Sleeping after the final attempt | Wasted latency | Only sleep when `attempt < maxAttempts` |
| Uncapped exponential | Huge delays/overflow | Capped saturating arithmetic |
| No jitter | Clients wake up in lockstep | Full/equal/decorrelated jitter per policy |
| `random.nextLong(cap)` expecting `cap` to be possible | Exclusive bound | `nextLong(cap + 1)` with safe cap |
| Adding jitter to capped delay without re-capping | Exceeds local `maxBackoff` | Use full jitter in `0..cap` |
| Retrying below `Retry-After` minimum | Violates rate-limit hint | `max(clientDelay, serverMinimum)` |
| Parsing `Retry-After: 30` as 30ms | Retries 1000x too early | Parse seconds/HTTP-date properly |
| Truncating 60s server hint to 2s `maxBackoff` | Disrespects peer quota | Stop/defer if `> totalBudget` |
| Retrying all `IOException`s | Retries DNS/config/TLS/body file errors | Classify exception and context |
| Retrying all HTTP 5xx | Can repeat permanent server failures | Status allowlist per endpoint |
| Retrying POST without idempotency | Duplicate writes/payments | Idempotency/reconcile/do not retry |
| Reusing an already-read `InputStream` for upload | Sends empty/partial body | New stream per attempt, immutable payload |
| Assuming timeout = server did not process | Repeated side effects | Idempotency key, ambiguity handling |
| Only per-attempt timeout, no total deadline | Total time = many attempts × timeout + sleep | Monotonic total budget/watchdog |
| `Thread.sleep` on event loop | Starvation, low throughput | `ScheduledExecutorService`/async |
| Creating a scheduler per request | Thread/resource explosion | Shared bounded scheduler |
| Multiple layers retrying together | Exponential amplification | Choose retry owner, shared deadline |
| Unbounded retry queue | Memory grows when server is down | Token/concurrency budget, bulkhead |
| Forgetting to cancel in-flight when caller cancels | Unneeded network work continues | Propagate best-effort cancel |
| Suppressing `InterruptedException` | Shutdown fails to stop | Propagate/restore interrupt |
| Recording every attempt as a new logical transaction | Skewed metrics/tracing, duplicate risk | Correlation ID + attempt number |

## 18. Self-Check Questions

**Q1.** How many retries at most does `maxAttempts=4` allow?  
**Answer:** 3 retries after the initial attempt, for 4 total network calls.

**Q2.** Base 100ms, cap 500ms: what is the capped exponential after the 4th failure?  
**Answer:** `min(500, 100×2^3) = 500ms`.

**Q3.** Can full jitter with `cap=500ms` produce `0ms`?  
**Answer:** Yes. If a minimum delay is required, combine with policy or server hints.

**Q4.** Why does having 1,000 clients use a fixed 100ms backoff cause problems?  
**Answer:** They wake up simultaneously, creating request spikes; jitter spreads out the attempts.

**Q5.** If the server returns `Retry-After: 30`, what is the minimum time to wait?  
**Answer:** About 30 seconds, not 30 milliseconds.

**Q6.** The server asks to wait 60s, and the total deadline has 2s left. Should you clamp the wait to 2s and retry?  
**Answer:** No. Stop/defer rather than violating the server minimum.

**Q7.** Does `HttpClient.send` automatically throw `IOException` on a `503` response?  
**Answer:** Not just for status 503. Classify using `response.statusCode()`.

**Q8.** `POST /payment` times out—is it certain the server has not charged the payment?  
**Answer:** No; you need an idempotency key/reconciliation or must not auto-retry.

**Q9.** Can a GET be safely retried when upstream drops mid-stream while writing a response file?  
**Answer:** Possibly depending on API semantics, but you must clean/truncate partial output before restarting from the beginning or perform a controlled resume.

**Q10.** Should `Thread.sleep` be used inside an HTTP async callback on a high-concurrency server?  
**Answer:** No; use a scheduler, bounded concurrency, and cancellation.

**Q11.** Do jitter and backoff replace timeouts?  
**Answer:** No. Both each attempt and the overall logical operation need deadlines.

**Q12.** Should `HttpRequest.BodyPublishers.ofInputStream`'s supplier return an already-read `InputStream`?  
**Answer:** No. Each subscription/attempt needs a newly opened stream with the same payload.

**Q13.** If three layers each do 3 attempts, how many calls at the bottom can occur at most?  
**Answer:** 27 in a nested model with no other limits; avoid multi-layer amplification.

**Q14.** A retry delay is already scheduled when the user cancels the request—what should happen?  
**Answer:** Cancel the scheduled timer and the in-flight operation (best-effort); do not start a new attempt.

**Q15.** `maxAttempts` is exhausted and the server still returns 503—should you sleep one last time?  
**Answer:** No; stop and return the error/response per contract.

**Q16.** Why must metrics distinguish initial attempts from retry attempts?  
**Answer:** To measure amplification/overload, success per logical operation, and the true cost of recovery.

**Q17.** If retrying after a network error with no response, how do you know if a write was already processed?  
**Answer:** You cannot know from the client exception alone; you need an idempotency/reconciliation protocol.

**Q18.** Should a `CompletableFuture` ending with `CancellationException` be retried like a transient `IOException`?  
**Answer:** No. Cancellation is typically a stop request from the caller or system.

## 19. Pre-Production Retry Design Checklist

1. **Define the logical unit** of the operation: `requestId`, `attemptNo`, side effects, caller deadline.
2. **Verify idempotency/replayability** before any retry, especially for POST and streaming uploads.
3. **Classify transient statuses/exceptions explicitly** per endpoint; never `catch(Exception)` and retry blindly.
4. **Use an explicit `maxAttempts`**, always including the initial send, and never sleep after the final attempt.
5. **Compute exponential backoff by failure count**, with a cap and saturating arithmetic to avoid overflow.
6. **Add properly distributed jitter**, unit-test with an injected RNG; do not use fixed delays in production.
7. **Respect `Retry-After`** in seconds or HTTP-date; if it exceeds the total budget, stop/defer.
8. **Bound per-attempt timeout and total deadline** using monotonic elapsed time and a watchdog.
9. **Never block async event loops**; use one-shot `ScheduledExecutorService` tasks and a bounded queue.
10. **Cancel timers/in-flight requests on caller cancellation**, propagate interruption, and close response bodies.
11. **Avoid multi-layer retries**; designate a retry owner, use a token budget, and bound concurrency.
12. **Combine with rate limits, circuit breakers, and bulkheads/backpressure** when dependencies frequently overload.
13. **Log logical request ID and attempt number**, without leaking credentials or private payloads.
14. **Track recovery value vs. amplification cost**: retries, latency, quota/exhaustion, dedup.
15. **Test failures under controlled conditions**: 503→200, 429 `Retry-After`, permanent failures, deadlines, cancellation, body replay, and many concurrent clients.
16. **Never promise exactly-once** from TCP/HTTP retries; business writes must have idempotency semantics and reconciliation.

## Standard References

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): `9.2.2` idempotent methods, `10.2.3` `Retry-After` (HTTP-date or seconds), `15.6.4` 503 Service Unavailable.
- [RFC 6585 — HTTP 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4): rate limiting and optional `Retry-After`.
- [AWS Architecture Blog — Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/): full/equal/decorrelated jitter and thundering herd under client contention.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, cancellation semantics.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): `timeout(Duration)` and request construction.
- [Java SE 17 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): request body replayability and `ofInputStream(Supplier)`.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): `statusCode()` and response headers.
- [Java SE 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): one-shot delayed `schedule` tasks and `ScheduledFuture`.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion, `failedFuture`, `whenComplete`, and `cancel`.
- [Java SE 17 — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): `nextLong(bound)` for choosing full jitter in a bounded range.
- [Java SE 17 — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html) and [System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): managing elapsed time and budgets.

**Conclusion:** A resilient client does not simply "retry three times." It must ask **whether it should retry**, **whether it is safe to replay**, and **whether time/resource budget remains**. When retrying is warranted, use **capped exponential backoff + jitter**, respect the server's `Retry-After`, terminate cleanly, and never let a retry storm push an already failing system further into overload.
