# Backpressure via REQUEST_N and Data Demand

RSocket supports streaming data transfer with a flow-control mechanism driven by receiver demand. Rather than letting the producer emit indefinitely, the consumer grants receive credit using REQUEST_N frames. The producer may only send payloads within the remaining demand; when the consumer needs more data, it sends the next REQUEST_N.

In Spring, this mechanism is represented at the application layer via Reactive Streams: the subscriber calls request(n), Reactor propagates demand through the publisher chain, and RSocket translates that demand into flow control on the connection. Consequently, how a Flux is subscribed to and processed directly affects the allowed data transmission rate.

Distinguish backpressure from rate limiting. Backpressure regulates the number of elements permitted in flight based on receive capacity; rate limiting caps rates over time. A consumer can request 1,000 elements and receive them very quickly. If business rules allow at most 20 requests per second, a separate rate limiter is still needed.

## 1. What Is REQUEST_N?

In Reactive Streams, a subscriber signals how many elements it is ready to receive via Subscription.request(n). The publisher must not emit more elements than the total demand granted by the subscriber.

RSocket carries that rule across the network with flow-control frames:

- For request-stream, the REQUEST_STREAM frame opens the stream and carries an initial request N.
- When the consumer needs more data, it sends REQUEST_N to add credit to the stream.
- For request-channel, the two data directions have independent demand. Each side regulates how many payloads it is ready to receive from the other.
- The producer emits payloads only within available credit. When credit reaches zero, the producer must wait for subsequent demand.

REQUEST_N adds to the allowed payload count rather than resetting an absolute cap. If the consumer requests 10 more while 3 credits remain, remaining credit becomes 13.

Example where a consumer initially requests 2 elements, then requests 1 more after finishing each element:

~~~text
Consumer -> REQUEST_STREAM(initialRequestN = 2)
Producer -> NEXT(item-1)
Producer -> NEXT(item-2)
Consumer -> REQUEST_N(1)
Producer -> NEXT(item-3)
Consumer -> REQUEST_N(1)
Producer -> NEXT(item-4)
~~~

The producer cannot unilaterally send item-3 before new credit arrives. This mechanism caps in-flight data at the receiving end and paces the two endpoints of the connection.

## 2. Interaction Types With and Without REQUEST_N

Not every RSocket interaction creates a stream requiring repeated credit grants.

| Interaction model | Result | Meaning of REQUEST_N |
|---|---|---|
| Fire-and-forget | Client sends one payload, receives no response stream | No response stream on which to grant demand |
| Request-response | One request and at most one response | No REQUEST_N window needed for a response sequence |
| Request-stream | One request opens multiple responses | Consumer grants initial demand then sends additional REQUEST_N |
| Request-channel | Both sides exchange payload streams | Each direction has independent flow control |

If an API only returns one result, request-response is usually simpler. If the server needs to emit many events over time, request-stream fits better. If the client also sends data continuously while receiving response data, request-channel may fit.

Do not choose request-stream merely to send multiple times. Clarify who produces each direction, who controls receive pacing, and whether both sides need concurrent streaming.

## 3. Reactive Streams Demand in Spring

Spring RSocket integrates with Reactor and Reactive Streams. On the server side, a handler returning Flux represents a response stream. On the client side, retrieveFlux returns a Flux whose subscriber can control demand.

Minimal TCP server configuration in Spring Boot:

~~~properties
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
~~~

Add the Spring Boot RSocket starter dependency matching the Spring Boot version in use:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-rsocket")
}
~~~

A controller can return Flux:

~~~java
import reactor.core.publisher.Flux;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
public class QuoteController {

    private final QuoteService quoteService;

    public QuoteController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @MessageMapping("quotes.stream")
    public Flux<Quote> stream(QuoteRequest request) {
        return quoteService.streamQuotes(request.symbol())
            .doOnRequest(n ->
                System.out.println("Downstream requested: " + n)
            )
            .doOnCancel(() ->
                System.out.println("Quote stream cancelled")
            );
    }

    public record QuoteRequest(String symbol) {}

    public record Quote(String symbol, long sequence, double price) {}
}
~~~

The quotes.stream route is invoked by the client via RSocketRequester. When the server-side publisher complies with Reactive Streams, consumer demand propagates back across the response stream. When the consumer has not requested more data, the publisher must not emit beyond demand.

doOnRequest only observes the demand passing through that operator position. Values may reflect batching or prefetching by intermediate operators rather than a one-to-one mapping to each REQUEST_N frame per request(n) call.

## 4. RSocketRequester and retrieveFlux

Spring provides RSocketRequester to issue request-response, request-stream, fire-and-forget, and request-channel calls.

A requester bean connecting to a TCP server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
public class RSocketClientConfig {

    @Bean
    RSocketRequester quoteRequester(RSocketRequester.Builder builder) {
        return builder.tcp("localhost", 7000);
    }
}
~~~

Client requesting a quote stream:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Flux;

public class QuoteClient {

    private final RSocketRequester requester;

    public QuoteClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Flux<Quote> streamQuotes(String symbol) {
        return requester
            .route("quotes.stream")
            .data(new QuoteRequest(symbol))
            .retrieveFlux(Quote.class);
    }

    public record QuoteRequest(String symbol) {}

    public record Quote(String symbol, long sequence, double price) {}
}
~~~

retrieveFlux returns a publisher. At Flux creation time, the client has not necessarily consumed any data yet. Once subscribed and the subscriber signals demand, the RSocket client regulates payload reception via flow control.

Other result-returning APIs:

- retrieveMono(Type.class): request-response with one result.
- retrieveFlux(Type.class): interaction returning a stream.
- send(): fire-and-forget, with no response body.
- For request-channel, RequestSpec takes a Publisher as input data and retrieveFlux describes the response stream.

Request-channel example:

~~~java
Flux<ChatReply> replies = requester
    .route("chat.channel")
    .data(outgoingMessages)
    .retrieveFlux(ChatReply.class);
~~~

In request-channel, outgoingMessages is also a publisher. Demand for data flowing from client to server and demand for responses flowing from server to client are regulated independently. Do not assume that one side requesting more data automatically increases demand on the other side.

## 5. Consumer Controlling Demand with BaseSubscriber

Standard subscribe calls typically request unbounded data. For example, Reactor's subscribe() uses a default subscriber that requests unbounded demand. This is convenient for light streams, yet unsuitable when processing in batches or capping pending work.

BaseSubscriber lets you decide explicitly when to request additional data:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;

public final class QuoteSubscriber extends BaseSubscriber<Quote> {

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(2);
    }

    @Override
    protected void hookOnNext(Quote quote) {
        process(quote);

        // Request more only after synchronously processing the current element.
        request(1);
    }

    @Override
    protected void hookOnError(Throwable throwable) {
        System.err.println("Quote stream failed: " + throwable.getMessage());
    }

    @Override
    protected void hookOnComplete() {
        System.out.println("Quote stream completed");
    }

    private void process(Quote quote) {
        System.out.println("Processing " + quote);
    }
}
~~~

Registering the subscriber:

~~~java
Disposable subscription = quoteClient
    .streamQuotes("ACME")
    .subscribeWith(new QuoteSubscriber());
~~~

The consumer starts with demand 2. After processing one quote, it requests 1 more. If processing is slow, the producer waits for demand instead of pushing unbounded elements.

An important caveat: if process merely submits work to an executor and returns immediately, the subsequent request(1) no longer reflects actual task completion. When processing asynchronously, grant additional demand only when concurrency capacity opens up or the task completes. Otherwise, client-side work queues can still grow unbounded despite using BaseSubscriber.

## 6. limitRate and Batching Upstream Demand

When writing a custom BaseSubscriber is unnecessary, Reactor provides limitRate to split upstream demand into smaller batches.

~~~java
quoteClient.streamQuotes("ACME")
    .limitRate(32)
    .subscribe(quote -> process(quote));
~~~

limitRate regulates how much the operator requests upstream in batches. It is useful when the final subscriber requests unbounded data yet the application wants to limit prefetch and queued work in earlier stages.

limitRate is not a per-second rate limiter. It controls requests by element count; if the producer responds quickly, 32 elements can still arrive in a very short time. To limit rate over time, add a rate limiter.

Other operators can alter how demand propagates:

- **publishOn:** switches processing to another scheduler and prefetches, meaning some elements may sit queued waiting.
- **buffer:** groups multiple elements into batches; buffer sizes must be bounded.
- **flatMap:** can run multiple inner publishers concurrently; set concurrency and prefetch appropriately.
- **concatMap:** processes inner publishers sequentially, generally easier for controlling order and concurrency.
- **limitRate:** splits upstream requests, helping control prefetch.

When analyzing backpressure, inspect the entire operator chain from subscriber to source. A single operator may buffer elements or request more upstream than the immediate downstream code needs.

## 7. onBackpressureBuffer, Drop, Latest, and Error

A data source may emit independently of demand, such as callbacks from an external library or a push-style event source. In that case, the application must explicitly choose how to handle a producer that emits faster than the consumer.

~~~java
Flux<Event> buffered = source
    .onBackpressureBuffer(1_000);

Flux<Event> latest = source
    .onBackpressureLatest();

Flux<Event> dropped = source
    .onBackpressureDrop();

Flux<Event> failOnOverflow = source
    .onBackpressureError();
~~~

The options carry distinct semantics:

| Operator | Behavior | Suitable for |
|---|---|---|
| onBackpressureBuffer(1000) | Holds up to 1,000 pending elements; errors on overflow | Events needing brief, bounded buffering |
| onBackpressureDrop() | Drops arriving elements while downstream has no demand | Typing indicators, transient state |
| onBackpressureLatest() | Keeps only the newest value, discarding older pending ones | Measurements or snapshots where only the latest matters |
| onBackpressureError() | Emits an error when demand cannot be satisfied | Streams that must fail visibly instead of silently dropping data |

These operators define a policy for speed mismatches; they do not replace RSocket flow control. Several backpressure operators actively request unbounded demand from upstream and then buffer/drop locally in the application. Placing them on an RSocket stream can mask peer demand and accumulate data in local buffers.

If the goal is for REQUEST_N to genuinely reflect the client's receive capacity, keep the publisher chain demand-aware and avoid placing an operator in the middle that switches to unbounded requests unnecessarily. When buffering is needed, always set a finite capacity, choose overflow behavior, and monitor dropped or errored element counts.

Do not use onBackpressureDrop or onBackpressureLatest for payment commands, order status updates, or audit events where losing an element corrupts business state. Those data types require durable storage and proper retries/acknowledgements.

## 8. Distinguishing Backpressure from Buffering and Rate Limiting

These three concepts are often confused:

- **Backpressure:** consumer grants demand; producer may emit only within remaining demand.
- **Buffering:** temporarily storing elements when producer and consumer speeds mismatch; finite buffers need overflow policies.
- **Rate limiting:** capping the number of elements or requests per unit of time.

For instance, a consumer can request 100 elements at once. If the server emits rapidly, all 100 elements can arrive within a few milliseconds. Backpressure still worked properly because the producer did not exceed demand, yet the application may still need rate limiting to prevent excessive bursts.

Conversely, a rate limit of 10 messages/second does not automatically bound how many elements sit in a queue if the consumer processes slowly. Combine demand, finite buffers, concurrency limits, and rate limits according to your goals.

## 9. Does REQUEST_N Always Map 1-to-1 to request(n)?

Do not assume every request(n) call in code generates exactly one REQUEST_N frame on the network. Reactor and RSocket may coalesce demand, send initial request N when opening the stream, or batch demand. Operators like limitRate, publishOn, or flatMap can also introduce prefetching.

What matters at the protocol layer is total granted credit and ensuring emitted payloads never exceed remaining credit. REQUEST_N adds credit; it does not force the producer to immediately emit N elements if the source does not yet have data.

For example, if a subscriber calls request(1) repeatedly, the RSocket implementation may optimize demand propagation into batches. Therefore, when debugging, observe total demand, payload counts, and stream states rather than writing tests that depend on an exact count of REQUEST_N frames per API call.

## 10. Stream Cancellation and Resource Cleanup

When a consumer no longer needs data, it can cancel the subscription. For an RSocket stream, cancellation propagates to the peer via the protocol's cancel mechanism. The producer should stop generating data and release related resources.

~~~java
Disposable subscription = quoteClient
    .streamQuotes("ACME")
    .subscribe(this::processQuote);

// When the screen or task ends:
subscription.dispose();
~~~

On the server side, you can watch for cancel to close resources:

~~~java
@MessageMapping("quotes.stream")
public Flux<Quote> stream(QuoteRequest request) {
    return quoteService.streamQuotes(request.symbol())
        .doOnCancel(() -> quoteService.release(request.symbol()));
}
~~~

If the source uses listeners or subscriptions to external systems, attach cleanup to doFinally or an equivalent dispose mechanism so cancel, complete, and error all release resources. Do not leave an infinite publisher running per client after a session closes.

## 11. Testing Demand with StepVerifier

StepVerifier allows controlling subscriber demand in tests. You can start with initial request 0 and increase demand step by step:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BackpressureTest {

    @Test
    void emitsOnlyWhenDemandIsGranted() {
        Flux<Integer> source = Flux.range(1, 5);

        StepVerifier.create(source, 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(1)
            .expectNext(3)
            .thenRequest(2)
            .expectNext(4, 5)
            .verifyComplete();
    }
}
~~~

This test proves the publisher obeys demand in Reactive Streams. It does not prove RSocket sent a specific sequence of REQUEST_N frames over a socket.

For RSocket integration tests, connect a real RSocketRequester to the server, call a route returning Flux, and use StepVerifier with initial request 0:

~~~java
StepVerifier.create(
        requester.route("quotes.stream")
            .data(new QuoteRequest("ACME"))
            .retrieveFlux(Quote.class),
        0
    )
    .thenRequest(2)
    .expectNextCount(2)
    .thenRequest(3)
    .expectNextCount(3)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

This integration test verifies that the stream over RSocket only emits data when the consumer grants demand. To inspect REQUEST_N frames on the wire, enable RSocket frame logging/tracing or use protocol observation tools. Never infer frame counts solely from the number of request(n) calls.

## 12. Scenarios to Test in Production

- Slow subscriber while the server emits data continuously.
- Client pauses demand and then resumes requesting after some time.
- Client cancels the stream while the server is generating data.
- Cold publisher generating on demand vs. hot source emitting independently.
- An intermediate operator inadvertently creating unbounded demand or large prefetch.
- Buffers filling and overflowing according to the chosen policy.
- Request-channel having two data directions with independent demand.
- Client reconnecting must create a new stream and restore read position if business rules require it.
- A consumer requesting very large demand; the server still controls processing cost and fan-out.
- Infinite streams cleaning up on cancel, error, or session close.

For long-lived streams, carry a sequence number or cursor if the client needs to resume from the last received position after reconnecting. Backpressure only paces data within an active stream; it does not retain emitted elements across a lost connection.

## 13. Backpressure Diagnostic Checklist

- Is the API using request-stream or request-channel? Is it truly an interaction needing multiple responses?
- Is the client using default subscribe() or a subscriber that explicitly controls request(n)?
- How much initial demand is granted? When does the consumer request more?
- Does the server-side publisher genuinely honor Reactive Streams demand?
- Do any operators buffer, drop, or request unbounded upstream?
- Do limitRate, publishOn, or flatMap have prefetch/concurrency exceeding processing capacity?
- For request-channel, has demand in both directions been examined independently?
- Does cancel propagate to the source and release resources?
- Are tests verifying Reactive Streams demand or asserting a specific count of REQUEST_N frames?
- On reconnect, does the application have a mechanism to resynchronize missed data?

REQUEST_N is the flow-control mechanism at the RSocket protocol layer; request(n) is how consumers express demand in Reactive Streams. Spring and Reactor bridge these two layers so producers know when they may send additional data. When designing streams, control demand on the consumer, avoid unbounded buffers, select explicit policies for push sources, and test both Reactive Streams behavior and networked RSocket integration separately.