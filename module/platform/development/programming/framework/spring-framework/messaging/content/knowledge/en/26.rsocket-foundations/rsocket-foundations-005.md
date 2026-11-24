# Request-Stream and Multiple Response Elements

RSocket supports multiple interaction styles. With **Request-Stream**, the requester sends a single request payload and the responder returns a stream consisting of zero, one, or many response payloads. In Spring, the responder typically declares a **@MessageMapping** method returning **Flux<T>**, while the requester uses **RSocketRequester.retrieveFlux(...)** to receive the elements.

A crucial aspect of Request-Stream is that the stream has backpressure: the requester signals how many elements it is ready to receive, and the responder must honor that demand. This enables applications to transfer large or continuous datasets without collecting all results into a List in memory.

## 1. What Is Request-Stream?

RSocket defines four primary interaction models:

| Interaction | Request from requester | Response from responder | Use when |
| --- | --- | --- | --- |
| Request-Response | One payload | One payload | Querying a single result |
| Request-Stream | One payload | One stream of payloads | One request returns multiple results |
| Request-Channel | One stream of payloads | One stream of payloads | Both sides send and receive multiple elements |
| Fire-and-Forget | One payload | No response payload | Sending a one-way notification |

Request-Stream is not multiple independent requests. The requester sends one initial request, such as “get measurements for device A”, and the responder emits result elements as a stream. If the requester wants to send additional request elements while receiving the response stream, the appropriate interaction is Request-Channel.

In Spring, data types reflect cardinality:

- **Mono<T>** represents at most one asynchronous value.
- **Flux<T>** represents a sequence that may have many asynchronous values.
- **Mono<Void>** represents completion without a response payload.
- A regular value represents a single synchronous payload.

A method taking one request object and returning Flux is typically mapped as Request-Stream.

## 2. How Spring Maps @MessageMapping to Request-Stream

Example responder receiving a device watch request and returning multiple measurements:

~~~java
package com.example.rsocket;

import java.time.Instant;

public record WatchRequest(String deviceId) {
}

public record SensorReading(
        String deviceId,
        long sequence,
        Instant measuredAt,
        double value) {
}
~~~

Service providing a Flux:

~~~java
package com.example.rsocket;

import reactor.core.publisher.Flux;

public interface SensorService {
    Flux<SensorReading> streamReadings(String deviceId);
}
~~~

Responder using **@MessageMapping**:

~~~java
package com.example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class SensorRSocketController {

    private final SensorService sensorService;

    public SensorRSocketController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @MessageMapping("sensor.watch")
    public Flux<SensorReading> watch(
            @Payload WatchRequest request) {

        return sensorService.streamReadings(request.deviceId());
    }
}
~~~

The method takes one **WatchRequest** and returns **Flux<SensorReading>**. Spring infers Request-Stream from the input and output element counts. Each element emitted by Flux is serialized into a response payload on the same logical RSocket stream.

The route in the example is **sensor.watch**. RSocket routes are metadata, not HTTP URLs; Spring uses a dot as the default route separator. The client must call this exact route.

## 3. Configuring Codecs for DTOs

The examples above exchange Java objects such as WatchRequest and SensorReading. To send and receive DTOs, requester and responder need corresponding Encoders/Decoders. This is an important point when using Spring Framework directly.

Spring Framework's default RSocketStrategies only registers basic codecs for String, byte[], and ByteBuffer. When using DTOs, add appropriate JSON or CBOR codecs. With Jackson JSON, configuration can look like this:

~~~java
package com.example.rsocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketMessageHandler;
import org.springframework.messaging.rsocket.RSocketStrategies;

@Configuration
public class RSocketCodecConfiguration {

    @Bean
    public RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
                .build();
    }

    @Bean
    public RSocketMessageHandler rsocketMessageHandler(
            RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
~~~

The Jackson codec classes belong to the spring-web module. Plain Spring Framework applications need the spring-web dependency along with compatible Jackson libraries. When using Spring Boot, the **spring-boot-starter-rsocket** starter supplies the required dependencies and auto-configures RSocketStrategies; Boot attempts to register Jackson CBOR codecs and then Jackson JSON codecs in order. When customizing strategies, ensure both requester and responder use compatible codecs and matching MIME types.

The requester uses the same strategies when connecting:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(strategies)
        .tcp("localhost", 7000);
~~~

If only passing String, byte[], or ByteBuffer, the basic codecs may suffice. With records/DTOs, do not overlook serialization configuration because codec issues can prevent requests from encoding or responses from decoding.

## 4. Requester Receiving Multiple Responses with retrieveFlux

The requester can connect over TCP or WebSocket. TCP connection example:

~~~java
RSocketRequester requester =
        RSocketRequester.builder()
                .tcp("localhost", 7000);
~~~

This call prepares the requester; the connection is established upon the first request. Send one request and receive multiple responses:

~~~java
WatchRequest request = new WatchRequest("sensor-17");

Flux<SensorReading> readings = requester
        .route("sensor.watch")
        .data(request)
        .retrieveFlux(SensorReading.class);
~~~

**retrieveFlux(SensorReading.class)** declares the type of each response element. It does not return a List containing all elements. Instead, the requester receives a Flux and can process each element as it arrives.

You can subscribe to process data continuously:

~~~java
Disposable subscription = readings.subscribe(
        reading -> System.out.println(
                reading.sequence() + ": " + reading.value()),
        error -> System.err.println(
                "Stream failed: " + error.getMessage()),
        () -> System.out.println("Stream completed"));
~~~

If the stream is infinite or long-running, keep the handle so it can be cancelled:

~~~java
subscription.dispose();
~~~

When the requester cancels the subscription, cancellation propagates over RSocket so the responder can stop upstream work. Applications should release resources upon cancellation, such as closing cursors, stopping polling, or cancelling subscriptions to data sources.

## 5. Each Element Is a Separate Response Payload

A Request-Stream can return:

- **0 elements:** the stream completes without any response payloads.
- **1 element:** only one response payload arrives, though the interaction is still Request-Stream if the responder declares Flux.
- **N elements:** each element is sent as a payload on the same stream.
- **Error:** the stream terminates with an error; the requester receives onError.
- **Completion:** the responder ends the stream normally; the requester receives onComplete.

Finite stream example:

~~~java
@MessageMapping("numbers.range")
public Flux<Integer> range(@Payload NumberRange request) {
    return Flux.range(request.start(), request.count());
}

public record NumberRange(int start, int count) {
}
~~~

If the request has start=10 and count=3, the responses are 10, 11, and 12 in order, followed by stream completion. These are three separate response payloads, not a single JSON payload containing an array of all three numbers.

To return an array/list as a single result, use **Mono<List<T>>** or a DTO containing a list. To transmit multiple elements that can be processed incrementally, use **Flux<T>**.

## 6. Backpressure: Requester Controls Response Pace

RSocket integrates Reactive Streams semantics across the network. The requester does not merely subscribe to a stream; it also tells the responder how many elements it is ready to receive.

At the protocol level:

1. The requester sends a **REQUEST_STREAM** frame carrying an initial demand count, called initial Request N.
2. The responder may send at most the number of PAYLOAD frames matching the current demand.
3. When the requester needs more elements, it sends **REQUEST_N** with an additional count.
4. The responder must honor demand and never emit more elements than requested.
5. The requester can send **CANCEL** to end an active stream.

Initial Request N must be greater than 0. Additional demand grants accumulate; granted credit cannot be revoked. This lets the responder know precisely how many subsequent elements it is allowed to emit.

Example where the requester initially asks for 3 elements:

~~~text
Requester -> Responder: REQUEST_STREAM (initial Request N = 3)
Responder -> Requester: PAYLOAD #1
Responder -> Requester: PAYLOAD #2
Responder -> Requester: PAYLOAD #3
Requester -> Responder: REQUEST_N (N = 2)
Responder -> Requester: PAYLOAD #4
Responder -> Requester: PAYLOAD #5
Responder -> Requester: COMPLETE
~~~

The responder must wait for fresh demand after sending all 3 initial elements. If the stream completes after 5 elements, the responder sends COMPLETE without needing further demand.

## 7. Backpressure Propagates Through Flux

Spring uses Reactor to map Reactive Streams demand over RSocket. When the requester-side subscriber requests only one element, demand can propagate back across RSocket to pace emissions from the responder.

Example with Reactor:

~~~java
Flux<SensorReading> readings = requester
        .route("sensor.watch")
        .data(new WatchRequest("sensor-17"))
        .retrieveFlux(SensorReading.class);

readings
        .limitRate(32)
        .subscribe(this::processReading);
~~~

**limitRate(32)** paces upstream requests in batches, limiting the demand forwarded by the subscriber. Actual values and request cadence also depend on the operator chain and implementation; 32 should not be interpreted as a guarantee that each network frame always contains exactly 32 elements.

Backpressure is especially useful when the data source can slow down emission, such as reactive database drivers, demand-based publishers, or Reactor pipelines. When the consumer processes slowly, demand drops and the responder can pause further emission.

If the data source is push-only, such as device callbacks or listeners that cannot pause, an adapter must decide how to handle a slow consumer: bounded buffering, dropping old/new data, keeping the latest value, persisting durably, or throttling at the source if possible. Avoid unbounded buffers because they can cause memory to grow continuously.

## 8. Do Not Collect the Entire Stream Unnecessarily

A common mistake is converting a Flux to a List too early:

~~~java
List<SensorReading> allReadings = readings.collectList().block();
~~~

This approach only fits finite streams with small element counts. It waits for the whole stream to complete, retains every element in memory, and forfeits incremental processing benefits. If the stream is infinite, **collectList()** never completes until the stream ends, so the application may wait forever.

Prefer element-by-element processing:

~~~java
readings
        .filter(reading -> reading.value() > 0)
        .map(this::toMetric)
        .subscribe(this::storeMetric);
~~~

If only a bounded count is needed:

~~~java
Flux<SensorReading> firstHundred = readings.take(100);
~~~

**take(100)** emits at most 100 elements and then cancels upstream. With RSocket, cancellation propagates to the responder to stop the stream if possible.

If only the first element is needed, use **next()** or **take(1)** to turn it into a Mono fitting the processing intent.

## 9. Stream Termination, Errors, and Cancellation

Request-Stream has its own lifecycle:

- The responder emits PAYLOADs.
- The responder can complete normally.
- The responder can terminate with ERROR.
- The requester can cancel with CANCEL.
- When the requester cancels, the responder must stop emitting further data and release upstream resources.

Example adding cleanup for a stream:

~~~java
@MessageMapping("sensor.watch")
public Flux<SensorReading> watch(@Payload WatchRequest request) {
    return sensorService.streamReadings(request.deviceId())
            .doFinally(signal -> {
                // Release resources or record completion state.
                // signal can be ON_COMPLETE, ON_ERROR, or CANCEL.
            });
}
~~~

Do not assume CANCEL instantly stops an uninterruptible blocking operation. If a service uses blocking APIs, design appropriate adapters, executors, and cancellation mechanisms. Reactive cancellation only takes full effect when upstream components honor cancellation.

If an error occurs mid-stream, the requester receives **onError** and the stream ends; subsequent elements are not sent on an errored stream. Errors can be recovered before returning from the responder if the domain allows it:

~~~java
return sensorService.streamReadings(request.deviceId())
        .onErrorResume(
                SensorUnavailableException.class,
                error -> Flux.empty());
~~~

The snippet above converts a data-source error into an empty stream. Only do this if an empty stream is an acceptable business outcome; otherwise, let the error propagate to the requester so the client can display or retry appropriately.

## 10. Distinguishing Request-Stream from Request-Channel

Both interactions can exchange multiple payloads, yet they differ in direction:

| Characteristic | Request-Stream | Request-Channel |
| --- | --- | --- |
| Requester sends | One initial request payload | A stream of request payloads |
| Responder returns | A stream of response payloads | A stream of response payloads |
| Use when | One request, multiple results | Both sides need concurrent streaming |
| Typical Spring responder | Single payload input, returns Flux | Flux input, returns Flux/Mono/void |

Request-Stream example: the client sends one request containing a deviceId and receives continuous readings.

Request-Channel example: the client continuously sends sensor data while the server simultaneously returns analytical alerts. This is a bidirectional interaction with backpressure in both directions.

Do not use Request-Channel merely because the response has multiple elements; if the requester also needs to send a data stream, consider Request-Channel.

## 11. Preserving Response Element Order

A Flux emits elements in the order of signals produced by its publisher. However, operators using concurrency can alter completion order.

Example:

~~~java
Flux<EnrichedReading> unordered = readings.flatMap(
        reading -> enrichmentService.enrich(reading),
        8);
~~~

**flatMap** allows multiple inner tasks to run concurrently. If the second element finishes before the first, it may be emitted first. This is helpful when prioritizing throughput and elements are independent.

If input order must be preserved, use **concatMap**:

~~~java
Flux<EnrichedReading> ordered = readings.concatMap(
        reading -> enrichmentService.enrich(reading));
~~~

**concatMap** only subscribes to the next inner publisher after the current inner publisher completes, preserving order while reducing concurrency.

Another option is **flatMapSequential**:

~~~java
Flux<EnrichedReading> orderedConcurrent = readings.flatMapSequential(
        reading -> enrichmentService.enrich(reading),
        8);
~~~

This operator allows inner tasks to run concurrently while emitting results in source order. In exchange, early-completing results may have to be buffered while waiting for earlier elements. Choose the operator based on ordering requirements and memory limits.

Even when a Flux preserves order, different RSocket streams have no automatic global ordering across streams. If events belong to the same aggregate, carry a sequence/version and check it on the consumer.

## 12. Example Client Handling a Bounded Stream

Example requester taking the first 100 readings, processing each element, and cancelling once the count is reached:

~~~java
Flux<SensorReading> readings = requester
        .route("sensor.watch")
        .data(new WatchRequest("sensor-17"))
        .retrieveFlux(SensorReading.class);

Disposable subscription = readings
        .take(100)
        .doOnNext(reading -> System.out.println(
                reading.sequence() + " = " + reading.value()))
        .doOnError(error -> System.err.println(
                "RSocket stream failed: " + error.getMessage()))
        .doOnComplete(() -> System.out.println("Received 100 or fewer readings"))
        .subscribe();
~~~

If the responder completes early, the client receives fewer than 100 elements and onComplete. If 100 arrive, take cancels upstream and completes on the client side. In both cases, the client does not wait for an entire infinite data source to finish.

If the application needs stricter lifecycle management, retain the **Disposable** and call **dispose()** when the user leaves the screen or no longer needs the stream. Avoid nested subscribe calls inside services without keeping the handle, as that can leave uncancelled streams after components close.

## 13. Testing Backpressure and Cancellation

Use **StepVerifier** to test demand at the Reactor level. Example testing a subscriber that initially requests zero elements and then requests sequentially:

~~~java
StepVerifier.create(Flux.range(1, 5), 0)
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .thenRequest(2)
        .expectNext(4, 5)
        .verifyComplete();
~~~

This test verifies that the publisher honors subscriber demand. To test RSocket over the network, integration tests with a real RSocket server/client are needed to verify that streams cancel when the requester cancels.

Cases to cover:

- Responder emits multiple responses and requester receives the expected types and element counts.
- Requester asks for few initial elements then adds demand; responder never emits beyond demand.
- Requester cancels; upstream publisher receives cancellation and releases resources.
- Stream completes normally; requester receives onComplete.
- Stream errors; requester receives onError and receives no elements after the terminal error.
- Parallel/flatMap operators alter order; concatMap or flatMapSequential preserve desired order.
- Large or long streams; memory does not grow unbounded when consumers are slow.

StepVerifier tests Reactive Streams behavior of publishers. It does not replace testing protocol flow-control over RSocket; to verify REQUEST_N/CANCEL on the wire or broker/transport integration, use appropriate integration tests and observe RSocket metrics/logs.

## 14. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Stream returns one large list after a wait | Called collectList or block | Process Flux element-by-element |
| Slow consumer causes memory growth | Unbounded buffer or push-only source | Use bounded buffers, drop/latest, or throttle the producer |
| Requester stops receiving elements | Demand not replenished, stream completed/errored, or cancelled | Check subscriber demand, onComplete/onError, and cancellation |
| Response elements arrive out of order | flatMap or parallel processing | Use concatMap/flatMapSequential or sequence numbers |
| Client cancels yet server keeps running tasks | Upstream is blocking or ignores cancellation | Design cancellable APIs, use reactive I/O and cleanup |
| Two clients observe different ordering | Two independent RSocket streams lack global ordering | Define sequences per aggregate/business key |
| One request receives too much data | Unbounded stream or missing domain limits | Use take, filter, paging, or time windows |
| Error appears after several elements | Responder emitted an error mid-stream | Check onError, retry policy, and partial-result state |

## 15. References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, Request-Stream, RSocketRequester, and annotated responders.
- [RSocket Protocol — Request-Stream](https://rsocket.io/about/protocol/): REQUEST_STREAM, REQUEST_N, PAYLOAD, CANCEL, and flow-control.
- [Reactive Streams Specification](https://www.reactive-streams.org/): demand, Subscription, request(n), cancel, and backpressure principles.
- [Project Reactor — Flux](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html): processing multi-element sequences.
- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/): demand, operators, and flow control techniques.
