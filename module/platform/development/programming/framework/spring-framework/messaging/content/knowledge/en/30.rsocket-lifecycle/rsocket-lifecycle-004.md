# Per-Request Timeouts and Managing Unbounded Streams

> Scope: Spring Framework Messaging with RSocket, Project Reactor, and Java 17+. The focus is setting time limits for each call, ending streams on time, and releasing resources when subscribers stop receiving data.

## 1. Why Are Timeouts and Stream Lifecycle Management Needed?

RSocket supports bidirectional, asynchronous, multiplexed communication over a single connection. One connection can carry many independent requests. Each request creates a stream with its own lifecycle:

- **Request-Response** sends one payload and receives at most one response payload. In Spring/Reactor, the return type is usually `Mono<T>`.
- **Request-Stream** sends one payload and receives many payloads. The return type is usually `Flux<T>`.
- **Channel** exchanges multiple payloads in both directions. The sender can pass a `Publisher`, and the receiver returns a `Publisher`.
- **Fire-and-Forget** sends one payload without waiting for a response payload. `RSocketRequester.send()` returns `Mono<Void>`; the Mono completing only indicates that the message has been sent, not that the handler finished processing it successfully.

A request can be slow, never answer, or return a stream that runs forever. Without an explicit policy, the caller can wait indefinitely; an old stream can keep holding subscriptions, sockets, cursors, listeners, or external resources. Therefore, you should define at least three things: response wait time, maximum silence between two events, and maximum lifetime of the entire stream.

Timeouts should match the contract of each operation. A data read command usually has a short deadline; a telemetry stream may be allowed to run long-term, yet must terminate when the user leaves the screen or when the monitoring session expires.

## 2. RSocket in Spring and Where to Place Timeouts

Spring provides `RSocketRequester` in the `spring-messaging` module. This API packages payloads and metadata, then turns results into `Mono` or `Flux`. The interaction model is inferred from the input and output payload cardinality.

Example of a request-stream: sending one object and receiving multiple results:

```java
Flux<Reading> readings = requester.route("sensor.readings")
    .data(new SensorRequest("sensor-17"))
    .retrieveFlux(Reading.class);
```

Example of a request-response requiring no input payload:

```java
Mono<Reading> reading = requester.route("sensor.latest")
    .retrieveMono(Reading.class);
```

`retrieveMono` fits a single result; `retrieveFlux` fits multiple results. Do not convert a stream into a `Mono` just to dodge lifecycle management: preserve the protocol cardinality and actual data semantics.

Reactor publishers are usually lazy. Calling a method to create a `Mono` or `Flux` has not started the request yet. The request starts upon subscription; hence, timeouts placed on the reactive chain normally start counting when the subscriber subscribes.

Timeouts can be placed at multiple layers:

1. **Client timeout** limits how long the caller waits for a result. This is the direct safeguard for the caller's experience.
2. **Server timeout** limits how long an operation executes on the responder side. It prevents internal work from running forever when downstream dependencies hang.
3. **Stream timeout** detects a stream that stops emitting events within the allowed interval.
4. **Stream lifetime** limits the total time a subscription is allowed to exist.

These limits solve different problems. Avoid using a single timeout value for every operation.

## 3. Timeouts for Request-Response with Mono

For a single response, `Mono.timeout(Duration)` raises a `TimeoutException` if the Mono does not emit an element within the specified duration. Example:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

Mono<Reading> read(String sensorId) {
    return requester.route("sensor.read")
        .data(new SensorRequest(sensorId))
        .retrieveMono(Reading.class)
        .timeout(Duration.ofSeconds(3))
        .onErrorMap(
            TimeoutException.class,
            error -> new SensorRequestTimeoutException(sensorId, error)
        );
}
```

In this example, the caller allocates at most three seconds for the read operation. If no response arrives in time, the timeout error is mapped into a domain exception so upper layers can classify, log, or return an appropriate error code.

You can replace the error with a fallback publisher if the business logic allows it:

```java
Mono<Reading> readWithFallback(String sensorId) {
    return requester.route("sensor.read")
        .data(new SensorRequest(sensorId))
        .retrieveMono(Reading.class)
        .timeout(
            Duration.ofSeconds(3),
            Mono.just(Reading.unavailable(sensorId))
        );
}
```

A fallback is appropriate only when the substitute value has clear meaning. Do not turn a timeout into fake success data if the caller needs to know the system received no response.

Another case to distinguish: `Mono.empty()` completes without emitting an element. If it completes before the deadline, `timeout` does not trigger because the publisher already terminated. When business logic requires a result, check for emptiness explicitly:

```java
return requester.route("sensor.read")
    .data(new SensorRequest(sensorId))
    .retrieveMono(Reading.class)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("Sensor returned no data")
    ))
    .timeout(Duration.ofSeconds(3));
```

Place `timeout` after building the request so it covers the entire publisher the caller awaits. When a unified deadline is needed across multiple calls, pass the remaining time down to lower layers instead of letting each layer start a fresh long wait.

## 4. Timeouts for Request-Stream with Flux

For `Flux<T>`, `timeout(Duration)` means the **maximum duration with no new element**. The clock starts when the subscription begins waiting for the first element, then resets after every `onNext`.

```java
Flux<Reading> watch(String sensorId) {
    return requester.route("sensor.watch")
        .data(new SensorRequest(sensorId))
        .retrieveFlux(Reading.class)
        .timeout(Duration.ofSeconds(15));
}
```

The stream raises `TimeoutException` if:

- The first element is not received within 15 seconds; or
- After an element, the next element is not received within 15 seconds.

If the stream emits data steadily every 10 seconds, it can run for hours or forever without timing out. This is the intended behavior: `Flux`'s `timeout(Duration)` is an idle-gap timeout, not an overall deadline.

When each element has a different SLA, Reactor also supports `timeout(firstTimeout, nextTimeoutFactory)`. The first publisher sets the limit for the first element; the `nextTimeoutFactory` function builds the wait limit for the next element based on the element just received. This is useful when wait time is determined by event type or business state.

If a stream can legitimately be silent for a long time, choose a threshold matching the data frequency or design an application-layer heartbeat. RSocket KEEPALIVE only checks connection liveness; KEEPALIVE frames are not business payloads and do not substitute for the data events that `Flux.timeout` waits for.

## 5. Limiting Total Stream Lifetime

A stream can operate normally yet never complete. When business rules only allow observing for a bounded period, set a total limit with `take(Duration)`:

```java
Flux<Reading> watchForTenMinutes(String sensorId) {
    return requester.route("sensor.watch")
        .data(new SensorRequest(sensorId))
        .retrieveFlux(Reading.class)
        .timeout(Duration.ofSeconds(15))       // Max 15 seconds of silence
        .take(Duration.ofMinutes(10))          // Max 10 minutes for the entire stream
        .doFinally(signal ->
            log.info("sensor.watch ended: {}", signal)
        );
}
```

After 10 minutes, `take(Duration)` completes the downstream stream and cancels the upstream subscription. Thus the caller receives a normal completion signal and the open request is told to stop. If you want to limit the event count, use `take(n)`. If you want to stop upon hitting a business event, use `takeUntil(predicate)`; this operator still forwards the last matching element. `takeWhile(predicate)` stops before forwarding the first element that no longer satisfies the condition.

| Need | Operator | Result When Limit Is Reached |
|---|---|---|
| Single response does not arrive on time | `Mono.timeout(Duration)` | Emits timeout error |
| Stream emits no new elements | `Flux.timeout(Duration)` | Emits timeout error |
| Stream runs beyond allowed duration | `Flux.take(Duration)` | Completes normally and cancels upstream |
| Need at most N elements | `Flux.take(n)` | Completes after N elements |
| Stop when a business condition is met | `Flux.takeUntil(predicate)` | Includes matching element then completes |

If the API must report an error when the overall deadline is exceeded rather than completing normally, define the deadline explicitly and represent it as an error at the application layer. Do not interpret `take(Duration)` as a timeout exception: the two behaviors have different contracts.

## 6. Cancelling Requests and Releasing Resources

Reactive Streams includes a cancellation signal. When downstream cancels the subscription, operators such as `timeout` or `take` propagate the cancel request upstream. In RSocket, the requester can send a `CANCEL` frame for an active stream. The responder receives the cancellation and can stop generating data for that request.

This only releases resources properly if the server-side publisher and data source honor cancellation. For example, a handler returning a `Flux` should tie cleanup to the subscription lifecycle:

```java
@Controller
class SensorRSocketController {

    private final SensorService sensorService;

    SensorRSocketController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @MessageMapping("sensor.watch")
    Flux<Reading> watch(SensorRequest request) {
        return sensorService.watch(request.sensorId())
            .doFinally(signal ->
                log.info("watch {} ended with {}", request.sensorId(), signal)
            );
    }
}
```

`doFinally` is invoked when the sequence completes, errors, or is cancelled; `SignalType` distinguishes `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`. Use it to record lifecycle events, increment metrics, or perform short synchronous cleanup. Do not block threads or put long synchronous I/O inside this callback.

If each subscription owns an asynchronous resource, `usingWhen` is a better fit because it lets you declare separate cleanup for completion, error, and cancellation:

```java
Flux<Reading> watch(String sensorId) {
    return Flux.usingWhen(
        streamRegistry.open(sensorId),
        handle -> handle.events(),
        handle -> handle.close(),
        (handle, error) -> handle.close(),
        handle -> handle.close()
    );
}
```

In the example, `open` returns `Publisher<StreamHandle>`, `events()` returns the data stream, and `close()` returns a publisher that completes after releasing the resource. Ensure cleanup is safe to invoke and does not release resources shared by another subscriber.

Avoid calling `subscribe()` manually inside `@MessageMapping` and returning a different publisher. The handler should return `Mono` or `Flux` directly so Spring manages the subscription, errors, backpressure, and cancellation with the request lifecycle.

## 7. Backpressure and Memory in Long-Lived Streams

RSocket carries Reactive Streams semantics across network boundaries. For request-stream and channel, the requester sends initial demand and updates it via `REQUEST_N` frames. The responder should emit only the number of elements matching the granted demand. This is the flow-control mechanism between both ends.

Backpressure does not automatically protect the application from all local buffering. Some operators or data sources can accumulate data in memory. In particular:

- Do not use `collectList()` on a stream without a clear end; it must wait for completion and holds all received elements.
- Do not use default `cache()` on an unbounded stream; it can retain an unbounded element history.
- Avoid unbounded `onBackpressureBuffer()`. If buffering is truly needed, set a maximum capacity and define overflow behavior: error, drop oldest, or drop latest per business requirements.
- Use `limitRate(n)` when you need to pace upstream requests. This regulates demand, not total element count or stream lifetime.
- Prefer data sources that support demand/cancellation rather than emitting infinitely into a queue.

For telemetry, logs, or high-rate events, explicitly decide which data can be dropped, which must be retained, and whether a slow consumer causes the system to slow down, buffer boundedly, or disconnect the subscription.

## 8. Keepalive Is Not a Request Timeout

RSocket has connection-level `KEEPALIVE` frames. The client sends periodic heartbeats; both ends use responses to verify the peer is still alive. In RSocket Java, `RSocketConnector.keepAlive(interval, maxLifeTime)` configures the sending interval and the maximum wait for a heartbeat from the peer. Default values in RSocket Java are 20 seconds and 90 seconds.

Spring lets you customize the connector via `RSocketRequester.Builder.rsocketConnector`:

```java
@Bean
RSocketRequester sensorRequester(RSocketRequester.Builder builder) {
    return builder
        .rsocketConnector(connector ->
            connector.keepAlive(
                Duration.ofSeconds(20),
                Duration.ofSeconds(90)
            )
        )
        .tcp("localhost", 7000);
}
```

This is connection configuration; it does not limit how long `sensor.read` can process, nor how many minutes a stream may remain open. A connection can stay healthy while a specific request hangs. Therefore, publisher-level timeouts are still required.

Conversely, a request-stream can stay silent for a long time even while the connection is healthy. If the application requires detecting silence at the data level, use `Flux.timeout` with an appropriate threshold. Do not shrink the keepalive interval merely to substitute for a business timeout.

## 9. Error Handling and Safe Retries

A timeout is an error that can be handled with `onErrorResume`, `onErrorMap`, or `retryWhen`. Choose behavior based on the operation's contract:

- Use `onErrorMap` to translate `TimeoutException` into a business-domain error, preserving the cause for diagnostics.
- Use `onErrorResume` when there is a genuinely valid fallback, such as reading from a cache labeled as stale data.
- Retry only when the request can be safely repeated or has an idempotency key. When the client times out, the server may have already executed the operation while the response was delayed or lost; retrying a write command can cause duplicate side effects.
- Limit retry attempts, use backoff, and enforce an overall deadline. Unbounded retries can keep an expired request running longer than the caller's policy.
- Do not catch every exception and return empty data. Distinguish timeouts, business errors, connection errors, and decoding errors.

If both server and client set timeouts, choose a sensible ordering. For instance, the server may limit processing to two seconds while the client allocates three seconds for the whole request so there is time to transmit errors and handle them on the calling side. Actual values should be based on SLAs, network latency, and measured processing time.

## 10. Standalone Reactor Example

The following example uses Reactor Core to illustrate three cases: an unresponsive single request, an infinite stream limited by element count, and a stream cut off when no new data arrives. This program demonstrates Reactor operators; it does not open a real RSocket connection.

**pom.xml** (Java 17+, Maven):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>rsocket-timeout-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
</project>
```

**TimeoutDemo.java**:

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class TimeoutDemo {

    public static void main(String[] args) {
        String response = Mono.<String>never()
            .timeout(Duration.ofMillis(50))
            .onErrorResume(
                TimeoutException.class,
                error -> Mono.just("fallback")
            )
            .block();

        System.out.println("request = " + response);

        List<Long> stream = Flux.interval(Duration.ofMillis(10))
            .take(3)
            .collectList()
            .block();

        System.out.println("stream = " + stream);

        List<String> idle = Flux.concat(
                Flux.just("connected"),
                Mono.delay(Duration.ofMillis(200)).thenReturn("late")
            )
            .timeout(Duration.ofMillis(50))
            .onErrorResume(
                TimeoutException.class,
                error -> Flux.just("timed-out")
            )
            .collectList()
            .block();

        System.out.println("idle = " + idle);
    }
}
```

Run from the directory containing `pom.xml` and `TimeoutDemo.java`.

On Linux/macOS:

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=cp.txt
javac -cp "$(cat cp.txt)" TimeoutDemo.java
java -cp ".:$(cat cp.txt)" TimeoutDemo
```

On Windows PowerShell:

```powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=cp.txt"
$cp = (Get-Content .\cp.txt -Raw).Trim()
javac -cp $cp .\TimeoutDemo.java
java -cp ".;$cp" TimeoutDemo
```

Output:

```text
request = fallback
stream = [0, 1, 2]
idle = [connected, timed-out]
```

Explanation:

1. `Mono.never()` emits no data and never completes. After 50 ms, `timeout` emits an error; `onErrorResume` switches to the fallback value.
2. `Flux.interval` is a continuous emitter. `take(3)` forwards only three elements and then cancels the upstream subscription.
3. The third stream emits `connected` immediately, then waits 200 ms. Because the wait exceeds 50 ms, `timeout` cancels the source and switches to the `timed-out` fallback publisher.

The `block()` calls in this program are only for observing the demo's output. Do not use `block()` in reactive request handlers or application event loops.

## 11. Testing Timeouts Without Waiting in Real Time

You can use `StepVerifier` from the `reactor-test` dependency with virtual time to test timeouts quickly and reliably:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutPolicyTest {

    @Test
    void timesOutWhenNoResponseArrives() {
        StepVerifier.withVirtualTime(
                () -> Mono.<String>never().timeout(Duration.ofSeconds(3))
            )
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify();
    }
}
```

Add the test dependency:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <version>3.8.8</version>
    <scope>test</scope>
</dependency>
```

You should also test scenarios such as: response arrives before the deadline, Mono completes empty, stream emits steadily, stream stops emitting after a few elements, stream is cancelled by the client, and cleanup is invoked properly on cancellation. With RSocket integration tests, test both sides to verify the server stops the publisher and releases resources after the client times out.

## 12. Common Mistakes

1. **Using `Flux.timeout` as a total deadline.** A stream that emits data steadily can stay alive indefinitely. Combine idle-gap timeout with `take(Duration)` or a business termination condition.
2. **Using KEEPALIVE as a request timeout.** Heartbeats only reflect connection liveness; an individual request can still hang.
3. **Forgetting cancellation cleanup.** The client stops receiving while the server keeps the subscription or resources alive. Tie cleanup to cancellation and verify the source publisher honors cancellation.
4. **Collecting an unbounded stream into memory.** `collectList()`, unbounded `cache()`, or unbounded buffers can cause memory to grow continuously.
5. **Retrying every timeout.** The server may have executed the operation before the caller timed out. Retrying write commands requires idempotency.
6. **Swallowing timeout errors with an unclear fallback.** Callers will be unable to distinguish real data from fallback data.
7. **Creating manual subscriptions inside handlers.** Calling `subscribe()` yourself takes request lifecycle management away from Spring. Return the publisher from the handler.
8. **Setting timeouts too short.** Timeouts must account for network latency, system load, processing time, and jitter; monitor timeout rates to tune with metrics.

## 13. Policy Selection Procedure

When designing an RSocket endpoint, answer in order:

1. Does the endpoint return one result or many results? Choose `Mono` or `Flux` accordingly.
2. If no first response arrives, how long should the caller wait at most? Set `Mono.timeout` or the first timeout for the stream.
3. For a stream, how long of a silence gap is considered abnormal? Set `Flux.timeout`.
4. Is the stream allowed to run forever? If not, set a total bound with `take(Duration)`, an element limit, or a business condition.
5. When the caller leaves or times out, what resources must the server release? Use a cancellation-aware publisher, `doFinally`, or `usingWhen`.
6. When the consumer is slow, does the system slow down, buffer boundedly, or drop data? Define the backpressure and overflow policy.
7. Can timeouts be safely retried? Verify idempotency and overall deadline before enabling retries.

A sound policy clearly separates single-response timeout, stream silence timeout, and maximum subscription lifetime. When these three bounds are designed together with cancellation, cleanup, and backpressure, RSocket requests can terminate predictably without leaving unnecessary work or resources behind.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, request interaction models, `retrieveMono`, and `retrieveFlux`.
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `timeout`, `take`, `takeUntil`, `doFinally`, and stream control operators.
- [RSocket Protocol Specification](https://github.com/rsocket/rsocket/blob/master/Protocol.md): `REQUEST_N`, `CANCEL`, `KEEPALIVE`, and stream lifecycle.
- [RSocketConnector Javadoc](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/core/RSocketConnector.html): connection-level keepalive configuration.
