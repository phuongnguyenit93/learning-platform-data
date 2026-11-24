# Testing Disconnects, Resource Exhaustion, and Invalid Messages

## Objectives

After this lesson, you will be able to:

- Distinguish transport errors, single-stream errors, business errors, and system overload errors.
- Design tests reproducing controlled disconnects, including graceful close and abrupt drops.
- Test concurrency limits, buffers, payload sizes, and work rejection when resources are exhausted.
- Test malformed messages, missing data, and validation rule violations.
- Verify that publishers terminate with the right signals, resources are released, and recovery policies do not create duplicate requests.

## 1. Identify the Right Error Category Before Writing Tests

In Spring Messaging, a message passes through multiple layers: transport, protocol, payload conversion, handler routing, and business processing. An error at each layer has a different blast radius. Tests must specify clearly which layer is being tested to avoid concluding that every failure is a disconnect.

| Error type | Examples | Typical scope | What to verify |
| --- | --- | --- | --- |
| Transport | TCP reset, WebSocket close, unresponsive peer | Connection or session | Publisher terminates, connection state changes, and resources are released |
| Protocol | Invalid frame, malformed frame, or wrong state | Can affect the entire connection | Peer rejects per protocol rules and stops processing corrupted data |
| Message/payload | Malformed JSON, missing field, wrong data type | Usually a single message or stream | Clear decoding error occurs, business handler is not invoked |
| Validation/business | Blank ID, negative quantity, disallowed state | Single message/request | Understandable error returned and no data written |
| Resource exhaustion | Full buffer, too many concurrent requests, oversized payload | Single stream, connection, or whole service | Bounded rejection, no unbounded memory growth, and system stays responsive |

With RSocket, distinguish stream errors from connection errors. An ERROR frame with a non-zero Stream ID represents an error for that stream; connection errors use Stream ID 0. A single malformed request should not accidentally bring down every stream. Conversely, losing the transport can terminate multiple streams sharing the same connection.

With STOMP over WebSocket, distinguish WebSocket closure, STOMP frame errors, message conversion errors, and handler errors. Each layer has its own error-reporting and recovery mechanisms.

## 2. Layered Testing Strategy

A solid test suite typically has three levels:

1. **Unit tests:** verify validators, handlers, retry policies, concurrency limits, and resource cleanup rules. Tests run fast without real sockets.
2. **Integration tests:** boot the Spring context and a real transport on a random port. Send messages over RSocket or STOMP, then deliberately close or corrupt the connection to observe end-to-end flow behavior.
3. **Resilience/load tests:** generate multiple clients, concurrent requests, large payloads, and controlled latency to verify load thresholds. Run separately from unit tests due to higher runtime and resource needs.

Use finite timeouts in tests so a non-terminating publisher cannot hang the whole build. With Reactor, **StepVerifier** helps verify message order, complete/error/cancel signals, and wait durations. Never use **Thread.sleep** to guess whether a network event occurred; await explicit signals or latches with timeouts.

Every test should state a specific hypothesis. For example: "When the server closes the connection, the pending request receives an error within the bounded timeout and cleanup runs exactly once." Then assert both observable signals and resource state.

## 3. Testing Disconnects

### Scenarios to Cover

- **Graceful close:** peer sends a valid close signal. Client detects the connection ended and stops sending requests on that connection.
- **Abrupt disconnect:** socket is reset or peer process dies. Client receives a transport error instead of hanging indefinitely.
- **Silent network drop:** no FIN/RST and no response. Keepalive or timeouts detect the peer is unresponsive.
- **Close mid-processing:** one or more requests are in flight when the connection closes. Publishers terminate cleanly and downstream tasks are canceled if no longer needed.
- **Close while idle:** no business requests are active, yet the connection still must be monitored and released when the peer disappears.
- **Reconnect:** a new connection is created after a transient failure; stale state is not mistakenly reused for new requests.

### Unit Test for Error Signals and Cleanup

The test below simulates a publisher receiving one message followed by an error equivalent to a transport reset. This is a unit test for the error-handling and cleanup contract; it does not replace integration tests using real sockets.

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ConnectionFailureTest {

    @Test
    void propagatesDisconnectAndRunsCleanup() {
        AtomicBoolean cleanedUp = new AtomicBoolean();

        Flux<String> inbound = Flux.concat(
                Flux.just("accepted"),
                Flux.error(new IOException("connection reset")))
            .doFinally(signal -> cleanedUp.set(true));

        StepVerifier.create(inbound)
                .expectNext("accepted")
                .expectError(IOException.class)
                .verify(Duration.ofSeconds(2));

        assertTrue(cleanedUp.get());
    }
}
~~~

The test verifies three things: the message received before the failure is still emitted in order; the error is not swallowed or turned into a fake completion; and cleanup runs when the publisher terminates. In a real system, cleanup might close subscriptions, release permits, remove the connection from a registry, or cancel dependent tasks.

### Integration Tests with Real Transports

With RSocket, create a server and client on TCP loopback using a random port to avoid conflicts. Keep a handle to the server-side connection in the test fixture so you can close it while the client is awaiting a response. After closing, verify:

1. The in-flight request publisher terminates with an appropriate error.
2. The client's connection close signal completes within the configured timeout.
3. New requests are no longer sent over the closed connection.
4. Server-side resources are released and a new connection can be established if policy permits.

With a Spring-created requester, you can observe client lifecycle via **requester.rsocketClient().onClose()**. Subscribe to monitor it once per connection/client rather than registering a new listener per request. When testing graceful close, expect the publisher to complete; when deliberately resetting the transport, expect an error. Do not force both cases into the same assertion.

With STOMP/WebSocket, start a real WebSocket server and test client, then close the session or transport mid-subscription. Verify session close callbacks, stopped subscriptions, that the broker no longer holds stale sessions, and that the client can reconnect. If the test uses an out-of-process broker, prepare dedicated fixtures and timeouts to avoid flaky startup ordering dependencies.

**Note:** closing a listener/server socket is not always equivalent to closing an already-accepted connection. Tests must close the exact observed connection or actively sever the client's transport.

## 4. Testing Resource Exhaustion and Backpressure

Resource exhaustion is not just running out of RAM. In messaging applications, key limits include:

- Concurrent connections/sessions.
- In-flight streams or requests.
- Queued tasks in executors.
- Queue/buffer capacities.
- Decoded payload sizes.
- Elements buffered in memory when downstream processes slowly.
- Connections to databases or dependent services.

A stable system must enforce clear limits. When thresholds are exceeded, it should reject or slow down producers according to an intentional policy. Unbounded queues merely defer failures and commonly drive memory growth until the process OOMs.

### Testing Bounded Buffers

The following example creates a fast producer while downstream has not requested any elements. The buffer holds only one slot, so exceeding the limit terminates the publisher with an overflow error.

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;
import reactor.core.publisher.BufferOverflowStrategy;
import reactor.test.StepVerifier;

class BackpressureTest {

    @Test
    void failsWhenBoundedBufferOverflows() {
        Flux<Integer> fastProducer = Flux.create(sink -> {
            sink.next(1);
            sink.next(2);
            sink.next(3);
            sink.complete();
        }, FluxSink.OverflowStrategy.IGNORE);

        Flux<Integer> guarded = fastProducer.onBackpressureBuffer(
                1, BufferOverflowStrategy.ERROR);

        StepVerifier.create(guarded, 0)
                .expectErrorMatches(Exceptions::isOverflow)
                .verify(Duration.ofSeconds(2));
    }
}
~~~

The producer in this test deliberately ignores demand to simulate overload. In production, prefer end-to-end backpressure across the pipeline; add buffers only with justification and bounded capacity. If choosing a drop strategy, specify which messages may be dropped and record metrics accordingly. If messages must not be lost, fail fast or reject early rather than silently dropping.

### Testing Concurrency and Executors

With Reactor, the concurrency parameter of **flatMap** limits how many inner publishers are subscribed concurrently within a single pipeline. That is a local bound on that pipeline, not an automatic system-wide quota. If many connections run the pipeline concurrently, total concurrency can be many times higher.

Tests should launch many concurrent requests and measure peak active tasks with an **AtomicInteger**, verifying it stays within configuration. If using **ThreadPoolTaskExecutor**, configure core pool, max pool, and queue capacity explicitly, then verify tasks exceeding capacity are rejected per the chosen rejection policy. Never allow tasks to accumulate indefinitely in a queue.

Key checks:

- Permits or semaphores are released on success, error, and cancel.
- Rejected requests do not increase active task counts.
- Once the queue hits its cap, the system emits a clear overload error/response.
- Once load subsides, the system accepts new requests normally.
- One overloaded client does not starve resources of other clients if per-client quotas exist.

### Testing Large Payloads

Send payloads across sizes: below the limit, at the exact limit, and above the limit. Confirm oversized payloads are rejected before consuming uncontrolled memory. Check both wire byte size and decoded size; JSON strings or decoded objects can occupy far more memory than transmitted bytes.

With Spring codecs, configure memory limits for decoding and test that exceeding the limit errors out. Do not check limits only inside the controller after the payload has already been decoded completely, as memory allocation has already occurred by then.

## 5. Testing Invalid Messages

Separate invalid messages into distinct categories:

1. **Undecodable:** malformed JSON/XML, unsupported content type, or bytes incompatible with the decoder.
2. **Invalid structure:** missing required fields, wrong types, incompatible schema version, or out-of-range fields.
3. **Validation failure:** blank strings, negative numbers, values outside allowed domains.
4. **Invalid routing:** nonexistent or unauthorized route/destination.
5. **Invalid business logic:** structurally valid data that violates state or execution permissions.

Do not check only that "an exception occurred." Good tests verify that the business handler is never called when a message is invalid, no data is written, the error is properly classified, and the connection stays alive when the error belongs only to the message/stream.

### Unit Test with Jakarta Bean Validation

This is a standalone test for data rules. It requires the Jakarta Validation API together with a provider such as Hibernate Validator.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

import org.junit.jupiter.api.Test;

class MessageValidationTest {

    record CreateOrder(
            @NotBlank String customerId,
            @Positive long quantity) {
    }

    @Test
    void rejectsBlankCustomerAndNonPositiveQuantity() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Set<String> invalidFields = validator
                    .validate(new CreateOrder("", 0))
                    .stream()
                    .map(error -> error.getPropertyPath().toString())
                    .collect(Collectors.toSet());

            assertEquals(Set.of("customerId", "quantity"), invalidFields);
        }
    }
}
~~~

The expected result is two violating fields: **customerId** and **quantity**. In message handlers, enforce validation before calling side-effecting services. If using **@Valid** on message-receiving methods, verify that a validation provider and message-handler validation are configured in the Spring context; do not assume every messaging adapter automatically applies the exact same rules as Spring MVC.

### Integration Tests for Invalid Payloads

In an RSocket test, send a request over a real route with a missing field or invalid value. Use **StepVerifier** to confirm the request terminates with an error within a bounded timeout. Also use a spy/mock on the service to verify the service was not called.

For malformed syntax or protocol-violating frames, create separate tests at the codec/transport layer. Do not conflate invalid JSON payloads with corrupted RSocket frames: the former is typically a message/stream decoding error, whereas frame structure violations can cause the connection to close per protocol.

With STOMP, send frames missing required headers, targeting nonexistent destinations, or containing undecodable payloads. Verify ERROR frame / close behavior per broker and application configuration. If a message is valid yet lacks permission for a destination, test authorization errors separately from syntax errors.

## 6. Testing Recovery After Failure

Recovery should be tested as a stateful workflow:

1. Detect the error and classify it as transient or permanent.
2. Stop work dependent on the lost connection.
3. Release stale resources.
4. Reconnect with bounded backoff if the error is recoverable.
5. Restore subscriptions/sessions if supported by protocol and application.
6. Ensure side-effecting requests are not inadvertently duplicated.

Do not retry every error. Transient network errors can retry; validation failures, nonexistent routes, or authorization errors normally require fixing input/permissions first. Overload errors require shedding load or rejecting; immediate retries from all clients can trigger a retry storm.

Example retry policy for transient errors in Reactor:

~~~java
import java.time.Duration;

import reactor.util.retry.Retry;

return sendRequest()
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                .filter(this::isTransientFailure));
~~~

**isTransientFailure** is an application-defined classifier. Cap retry attempts, use backoff, and consider jitter when multiple clients exist. Do not retry validation errors or business errors that cannot resolve on their own.

If the server may have processed a request while the response was lost, retries can create duplicate transactions or messages. Use idempotency keys, unique message IDs, deduplication, or transactional outbox/inbox depending on architecture. For continuous streams, clarify which offsets/acknowledgements were confirmed before resuming.

## 7. Suggested Test Matrix

| Scenario | Fault injection | Expected verification |
| --- | --- | --- |
| Peer graceful close | Close session/socket per protocol | Close signal completes, cleanup runs once |
| Transport reset | Abruptly close connection | Pending requests receive error, no hang |
| Silent network loss | Block traffic or drop responses in test env | Keepalive/timeout detects within configured threshold |
| Slow downstream | Slow or non-requesting consumer | Backpressure holds, buffers stay within bounds |
| Full buffer | Producer exceeds capacity | Overflow/error/drop matches policy |
| Concurrency exceeded | Send many concurrent requests | Active tasks stay within quota |
| Oversized payload | Send payload exceeding limit | Rejected without unbounded memory growth |
| Malformed JSON | Send undecodable bytes | Decoder fails, handler does not run |
| Missing fields | Send object missing required data | Validation fails, no data written |
| Nonexistent route | Send unknown destination/route | Clear routing error returned |
| Retry after disconnect | Drop connection after server processes | No duplicate side effects created |
| Load subsides | Stop producer and drain requests | System accepts new requests normally again |

## 8. Common Pitfalls

- **Testing only the happy path:** network faults and overload typically strike in transitional states while requests are in flight or buffers are full.
- **Using mocks to conclude transport behavior works:** mock publishers are great for unit tests, yet do not prove TCP/WebSocket close and error detection work accurately.
- **Using Thread.sleep:** tests become dependent on machine timing and flaky. Synchronize with signals, latches, or StepVerifier with timeouts.
- **Using unbounded queues:** hides producer-outpacing-consumer imbalances and can cause OOM.
- **Retrying immediately on failure:** increases load right when the service is overloaded and can create duplicate side effects.
- **Asserting only exceptions:** overlooks whether the handler ran, data was written, or resources were released.
- **Conflating stream errors with connection errors:** a single bad message should not by default break all streams; transport errors can impact the whole connection.
- **Testing only one type of close:** test graceful close, abrupt reset, silent network loss, and closing while requests are active.

## 9. Completion Checklist

- [ ] Unit tests exist for validation, error classification, and cleanup.
- [ ] Integration tests using real transports cover graceful close and abrupt drops.
- [ ] Timeout/keepalive tests cover silent network loss scenarios.
- [ ] Tests cover configured limits for buffers, concurrency, executors, and payload sizes.
- [ ] Separate tests cover malformed syntax, structural errors, and business errors.
- [ ] Verified handler does not run and no data is written for invalid payloads.
- [ ] Verified single-stream errors do not close connections when protocol permits continuing.
- [ ] Verified connection failures stop publishers and release resources.
- [ ] Retries are bounded, use backoff, and apply only to transient errors.
- [ ] Idempotency or deduplication is tested for side-effecting requests.
- [ ] Tests use finite timeouts and do not rely on Thread.sleep.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework Reference — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [RSocket Protocol — Error frame](https://github.com/rsocket/rsocket/blob/master/Protocol.md#error-frame-0x0b)
