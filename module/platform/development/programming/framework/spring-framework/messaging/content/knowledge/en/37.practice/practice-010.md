# Experimenting with Request-Channel, Backpressure, and Cancellation

In RSocket, **Request-Channel** is an interaction model that allows a requester to send a stream of messages to a responder while the responder simultaneously sends a stream of messages back. Both directions operate over the same request stream and can emit data independently. This is a suitable choice for continuous bidirectional exchanges such as state synchronization, real-time collaboration, device control, or processing a sequence of commands with corresponding replies.

When experimenting with Request-Channel, three behaviors need to be observed:

- **Request-Channel:** both sides can send multiple payloads on the same request.
- **Backpressure:** each side controls its incoming data rate via demand; the sending side must honor that demand.
- **Cancellation:** when a subscriber cancels the channel, related data transmission and processing must terminate according to the request's lifecycle.

A good test must prove that data flows in both directions, demand genuinely throttles emission, and cancellation propagates to the source publisher. Merely checking that a Flux emits a few elements is not enough to prove RSocket channel behavior over the network.

## 1. What Is Request-Channel?

RSocket has four core interaction models:

| Interaction model | Requester sends | Responder returns | Suitable scenario |
|---|---|---|---|
| Request-Response | One message | One message | Lookup or update yielding a single result |
| Request-Stream | One message | One stream | Send parameters and receive multiple results |
| Fire-and-Forget | One message | No response payload | Send a notification needing no result |
| Request-Channel | One stream | One stream | Continuous data exchange in both directions |

Request-Channel is not simply two independent requests running in parallel. Both payload streams belong to the same interaction, share a lifecycle, and can be regulated by RSocket flow control.

For example, a client sends device monitoring commands and the server sends processing statuses:

- Client -> Server: SubscribeDevice, ChangeSamplingRate, StopDevice.
- Server -> Client: DeviceReady, SampleReceived, DeviceWarning.

The client can continue sending commands while the server is still emitting earlier statuses or results. The two directions do not need to emit the same number of elements, nor do they need to complete at the same time.

### Distinguishing from Spring's MessageChannel

The naming can be confusing:

- **RSocket Request-Channel** is a bidirectional protocol interaction model.
- **Spring MessageChannel** is an abstraction for sending a Spring Message to a channel.
- **Spring Integration request channel** is typically a channel used to pass requests to a handler inside an integration flow.

These concepts can be used together in a system, yet they are not synonymous. An RSocket Request-Channel is not automatically a Spring Integration channel, and a MessageChannel does not create a bidirectional protocol on its own.

## 2. How Is Request-Channel Represented with Flux?

In Spring Framework, an annotated responder can accept an input Flux and return an output Flux:

~~~java
@Controller
class DeviceChannelController {

    private final DeviceService deviceService;

    DeviceChannelController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @MessageMapping("devices.control")
    Flux<DeviceReply> control(Flux<DeviceCommand> commands) {
        return commands.concatMap(
            command -> deviceService.handle(command)
                .map(result -> new DeviceReply(
                    command.commandId(),
                    result.status()
                )),
            1
        );
    }
}
~~~

In this example:

- The `Flux<DeviceCommand>` parameter is the command stream from requester to responder.
- The `Flux<DeviceReply>` return value is the response stream from responder back to requester.
- Route `devices.control` identifies the handler.
- `concatMap` processes each command sequentially and caps prefetch at one element in this pipeline.

This is the natural form for implementing Request-Channel with a Spring annotated responder. The requester sends a multi-item Publisher and requests a Flux response.

The requester can invoke it like this:

~~~java
Flux<DeviceCommand> outbound = Flux.just(
    new DeviceCommand("cmd-1", "START"),
    new DeviceCommand("cmd-2", "SET_RATE"),
    new DeviceCommand("cmd-3", "STOP")
);

Flux<DeviceReply> inbound = requester
    .route("devices.control")
    .data(outbound, DeviceCommand.class)
    .retrieveFlux(DeviceReply.class);
~~~

Passing a multi-item Publisher to `data` and receiving a Flux with `retrieveFlux` creates the bidirectional interaction. Using the overload with the element class helps Spring know the type of each item in the stream so it can select the right encoder.

### DTO Examples

~~~java
record DeviceCommand(
    String commandId,
    String action
) {}

record DeviceReply(
    String commandId,
    String status
) {}

record DeviceResult(String status) {}
~~~

These DTOs only illustrate the payloads for this lab. In a real application, define schemas, validation, correlation IDs, duplicate command handling, and dedicated error rules.

## 3. Both Directions Have Independent Lifecycles

Request-Channel has two stream directions:

1. Requester -> Responder: the requester emits commands or input data.
2. Responder -> Requester: the responder emits responses, acknowledgements, or events.

Each direction can complete independently. For instance, the client may finish sending all commands while the server still needs to emit in-flight results. When the client's input Publisher completes, that only signals the client will send no more payloads; it does not mean the response stream must complete immediately.

Similarly, the responder can complete its response stream while the requester is still sending data, depending on the contract and processing logic. The channel completes normally only when both sides finish sending their respective streams.

Distinguish three signals:

- **Complete:** one side has finished sending data in its direction.
- **Error:** an error terminates the interaction according to protocol semantics.
- **Cancel:** the requester or responder cancels the active request; the channel is terminated.

Do not use completion of the outbound Flux to infer that the entire channel has ended. If you need to know when the whole exchange is finished, observe completion of the response Flux.

## 4. Testing a Complete Bidirectional Channel

A basic lab should have a server handler and a real requester. The server receives commands and returns corresponding acknowledgements.

Handler:

~~~java
@Controller
class EchoChannelController {

    @MessageMapping("lab.echo")
    Flux<EchoReply> echo(Flux<EchoCommand> commands) {
        return commands
            .map(command -> new EchoReply(
                command.sequence(),
                "ACK-" + command.value()
            ));
    }
}

record EchoCommand(long sequence, String value) {}

record EchoReply(long sequence, String result) {}
~~~

Requester:

~~~java
Flux<EchoCommand> commands = Flux.just(
    new EchoCommand(1, "alpha"),
    new EchoCommand(2, "beta"),
    new EchoCommand(3, "gamma")
);

Flux<EchoReply> replies = requester
    .route("lab.echo")
    .data(commands, EchoCommand.class)
    .retrieveFlux(EchoReply.class);
~~~

You can verify the result with StepVerifier:

~~~java
StepVerifier.create(replies)
    .assertNext(reply -> {
        assertEquals(1, reply.sequence());
        assertEquals("ACK-alpha", reply.result());
    })
    .assertNext(reply -> {
        assertEquals(2, reply.sequence());
        assertEquals("ACK-beta", reply.result());
    })
    .assertNext(reply -> {
        assertEquals(3, reply.sequence());
        assertEquals("ACK-gamma", reply.result());
    })
    .verifyComplete();
~~~

This test needs to run inside an integration test where a real RSocket server is started and a requester connects to it. Calling the `echo` method directly with a local Flux only verifies data transformation logic—not routing, encoding, channel interaction, or protocol flow control.

In integration tests, use a dynamic port or a separately configured test transport, start the server before creating the requester, and dispose of both the server and connections after the test. Do not hard-code a fixed port that another test could occupy.

## 5. Backpressure Works in Both Directions

Reactive Streams uses demand to regulate how many items a subscriber wants to receive. In RSocket, flow control is transmitted across the protocol via REQUEST_N frames.

For Request-Channel, each side can send REQUEST_N to grant credits to the other side. Therefore:

- The requester's demand regulates how many responses the responder is allowed to emit.
- The responder's demand regulates how many additional request payloads the requester is allowed to send.
- Both directions can have different demand levels.
- Granted credits accumulate; the sending side must not send beyond its available credits.

For example, the requester grants demand for only one response at a time. The responder must honor that limit before sending the next response. Conversely, if the responder requests only one command at a time, the requester cannot push an arbitrary burst of commands into the stream.

Backpressure is per-stream flow control. It does not replace limits on total channels or total requests accepted by the server. A single client can still open many channels, so the server needs additional admission control and application-level concurrency limits.

### Testing Demand with StepVerifier

You can start with small demand and increase it step by step:

~~~java
StepVerifier.create(replies, 1)
    .expectNextMatches(reply -> reply.sequence() == 1)
    .thenRequest(1)
    .expectNextMatches(reply -> reply.sequence() == 2)
    .thenRequest(1)
    .expectNextMatches(reply -> reply.sequence() == 3)
    .verifyComplete();
~~~

This test gives the subscriber one initial response credit, then requests one more element at a time. It tests how the consumer regulates the response stream.

Note: initial request N in the RSocket protocol must be positive. Use a valid initial demand such as one element when testing a channel over a real transport; do not assume zero demand in StepVerifier always maps directly to a valid REQUEST_CHANNEL frame.

## 6. Throttling the Command Stream on the Requester Side

If the command source is a Flux capable of honoring demand, RSocket can regulate how items are requested from that source. Operators can be added to limit request batch sizes or the number of items buffered at each step.

Example:

~~~java
Flux<DeviceCommand> outbound = commandSource
    .limitRate(4)
    .doOnRequest(n -> metrics.recordCommandDemand(n))
    .doOnCancel(() -> metrics.recordCommandStreamCancelled());
~~~

`limitRate` splits large demand requests into smaller batches as configured. It does not set a global limit on channel count, nor is it a per-second rate limiter.

If commands are produced from a hot source that cannot pause, a bounded policy is required to handle speed mismatches:

~~~java
Flux<DeviceCommand> outbound = hotCommandSource
    .onBackpressureBuffer(
        128,
        dropped -> metrics.incrementCommandOverflow(),
        BufferOverflowStrategy.ERROR
    );
~~~

A 128-element buffer here is an example of a local bound. When full, the publisher emits an error instead of buffering unbounded data. Use a buffer only if business rules allow queuing; for critical commands, define durable storage or return an error so the producer can retry safely.

Do not add large buffers out of habit. If the source already honors backpressure, letting demand propagate upstream is usually simpler and uses less memory.

## 7. Throttling Processing on the Responder Side

The responder also needs to decide how fast to consume commands. Example using `concatMap` with a small prefetch for sequential processing:

~~~java
@MessageMapping("devices.commands")
Flux<CommandAck> commands(Flux<DeviceCommand> inbound) {
    return inbound
        .concatMap(
            command -> deviceService.process(command)
                .map(result -> new CommandAck(
                    command.commandId(),
                    result.status()
                )),
            1
        );
}
~~~

`concatMap` guarantees processing in input order and runs only one inner publisher at a time in this pipeline. This fits when commands have ordering dependencies, such as START needing to occur before STOP.

If commands are independent and downstream can sustain multiple concurrent operations, you can use bounded `flatMap`:

~~~java
return inbound.flatMap(
    command -> deviceService.process(command)
        .map(result -> new CommandAck(
            command.commandId(),
            result.status()
        )),
    8,
    1
);
~~~

The limit of 8 applies to this subscription. With many simultaneous channels, total load can be much higher. If you need to protect a database or external service application-wide, use a shared bulkhead or admission control.

If response order must match command order while still processing concurrently, consider `flatMapSequential`. This operator preserves emission order, though it may buffer results from operations that finish earlier.

## 8. What Is Cancellation?

Cancellation happens when a subscriber no longer wants to receive or continue an interaction. With RSocket, the requester can send a CANCEL frame for an active request stream. A responder receiving cancellation must terminate the corresponding stream.

In Spring/Reactor, cancellation is represented by a Subscription's `cancel` signal. When the pipeline is wired properly, this signal propagates upstream through operators to the source publisher.

Example recording cancellation on the responder side:

~~~java
@MessageMapping("lab.cancel")
Flux<Progress> progress(Flux<WorkCommand> commands) {
    return commands
        .concatMap(workService::run)
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                metrics.incrementChannelCancellation();
            }
        });
}
~~~

`doFinally` runs when the pipeline terminates via complete, error, or cancel. Increment the cancellation metric only when the signal is `CANCEL`; do not treat every termination as a cancellation.

Cancellation is especially important when the handler is:

- Reading data from a database or an external stream.
- Monitoring device state.
- Running a long-lived task.
- Holding a subscription to a hot publisher.
- Waiting on a downstream service.
- Consuming resources that can be released when no subscribers remain.

Do not merely stop emitting responses while letting the source continue useless work. Verify that the source publisher supports cancellation and release resources in `finally` or `doFinally` as appropriate.

## 9. Canceling a Channel from the Requester

You can use the `take` operator to stop after a fixed number of responses:

~~~java
Flux<Progress> firstTwo = requester
    .route("lab.cancel")
    .data(workCommands, WorkCommand.class)
    .retrieveFlux(Progress.class)
    .take(2);
~~~

`take(2)` completes downstream after two elements and cancels the upstream subscription. With an RSocket channel, cancellation ends the active interaction. It does not merely mean "pausing response receipt"; the request channel has been canceled.

Test:

~~~java
StepVerifier.create(firstTwo)
    .expectNextCount(2)
    .verifyComplete();
~~~

To confirm cancellation actually reaches the server, do not check only that downstream completed. Place a probe on the responder side, such as a `CountDownLatch` or `Sinks.One`, triggered when the publisher receives `SignalType.CANCEL`; then have the test await the probe with a deadline.

~~~java
assertTrue(
    serverCancellation.await(5, TimeUnit.SECONDS),
    "Responder did not observe channel cancellation"
);
~~~

Event-driven waiting with a deadline lets the test prove cancellation propagated to the responder. Do not use `Thread.sleep` to guess when the server receives CANCEL.

## 10. Completing One Direction Differs from Canceling the Entire Channel

This is a critical point when designing application protocols:

- When the requester's outbound Publisher completes, the requester has finished sending commands. The server can still continue emitting remaining responses.
- When the requester's response Flux completes, the responder has finished sending responses. That does not automatically mean every requester command has been sent.
- When the requester cancels the response subscription, the channel is canceled; this terminates the interaction rather than closing only half the stream.
- When either side emits an error, the interaction ends according to RSocket error semantics.

For example, a client may finish sending a batch of commands yet still wait for the server to aggregate the final result. In that case, complete the outbound source normally and keep subscribing to the response Flux until it completes.

Do not use `take(0)`, `cancel`, or `dispose` to signal "I have no more commands" if you still need to receive results. Complete the outbound Publisher; cancel only when you want to stop the entire interaction.

## 11. Testing Cancellation with an Observable Source

A test publisher can record cancellation using an `AtomicBoolean`:

~~~java
AtomicBoolean sourceCancelled = new AtomicBoolean();

Flux<WorkCommand> commands = Flux
    .<WorkCommand>never()
    .doOnCancel(() -> sourceCancelled.set(true));

Flux<Progress> progress = requester
    .route("work.long-running")
    .data(commands, WorkCommand.class)
    .retrieveFlux(Progress.class)
    .take(1);
~~~

When the first response arrives and `take(1)` cancels upstream, you can inspect `sourceCancelled`. However, with a real Request-Channel, identify which publisher is being canceled and probe on the right side. Cancellation of a response subscription should not be inferred from a local test Flux that never crosses the transport.

An integration test can:

1. Open a channel to the server.
2. Send a command starting a long-running task.
3. Receive one progress response.
4. Cancel the subscription from the requester.
5. Wait for the responder-side probe to report cancellation.
6. Verify the service stops the task or releases subscriptions/resources.
7. Verify no further responses are emitted for the canceled channel.

If the underlying task does not support cancellation, Reactor cancellation cannot automatically stop a running thread or blocking call. In that case, you need client timeouts, interrupt/cancel APIs if supported by the library, and task-level resource management.

## 12. Testing Errors and Races Between Both Directions

Both directions of a channel can emit data concurrently, so tests need to consider race scenarios:

- The client emits the final command while the server is sending a response.
- The client completes the outbound stream while the server still has pending responses.
- The server emits an error while the client still has unsent commands.
- The client cancels while the server is processing a command.
- The network connection closes while both sides have active demand.
- A response arrives late after the client side has already canceled the interaction.

Do not assume a global ordering between both directions. RSocket guarantees per-stream semantics and flow control, yet applications need correlation IDs or sequence numbers to match responses with corresponding commands.

Example response carrying `commandId`:

~~~java
record WorkCommand(String commandId, String operation) {}

record WorkReply(
    String commandId,
    String status,
    long sequence
) {}
~~~

When responses can arrive out of order due to parallel server processing, the client should correlate by `commandId` rather than relying on element position in the Flux.

When strict ordering is required, use sequential processing on the responder or add sequence numbers with explicit reordering rules.

## 13. Distinguishing Unit Tests from Transport Tests

Some behaviors can be tested with local publishers; others require real RSocket.

| Goal | Suitable test type | What the test proves |
|---|---|---|
| Mapping command to reply | Unit test | Application logic is correct |
| `concatMap` sequential processing | Unit test with StepVerifier | Ordering and single concurrency |
| `flatMap` concurrency | Unit test with active counter | Bound within one subscription |
| Local Flux backpressure | StepVerifier/TestPublisher | Publisher honors demand |
| Route is mapped correctly | RSocket integration test | Spring responder receives the route |
| Bidirectional Request-Channel | RSocket integration test | Requester and responder exchange two streams over transport |
| `REQUEST_N` sent over network | Integration test with probe | Flow control between both sides |
| `CANCEL` propagated to responder | Integration test with cancellation probe | Request lifecycle terminates on server side |
| Mid-channel connection drop | Transport integration test | Error/reconnect/resume per real config |

Virtual time is useful for Reactor operators that use a replaceable scheduler. It does not control timers in TCP, Reactor Netty, or a real broker. For transport integration tests, use real time while awaiting signals with a deadline.

## 14. A Complete Experimental Scenario

You can build a lab with route `devices.session`:

**Responder:**

~~~java
@Controller
class DeviceSessionController {

    @MessageMapping("devices.session")
    Flux<SessionReply> session(Flux<SessionCommand> commands) {
        return commands
            .limitRate(2)
            .concatMap(command ->
                deviceService.execute(command)
                    .map(result -> new SessionReply(
                        command.id(),
                        result.message()
                    )),
                1
            )
            .doFinally(signal -> {
                if (signal == SignalType.CANCEL) {
                    deviceMetrics.channelCancelled();
                }
            });
    }
}
~~~

**Requester:**

~~~java
Flux<SessionCommand> commands = Flux.just(
    new SessionCommand("1", "OPEN"),
    new SessionCommand("2", "SET_MODE"),
    new SessionCommand("3", "READ"),
    new SessionCommand("4", "CLOSE")
);

Flux<SessionReply> replies = requester
    .route("devices.session")
    .data(commands, SessionCommand.class)
    .retrieveFlux(SessionReply.class);
~~~

**Test:**

~~~java
StepVerifier.create(replies, 1)
    .assertNext(reply -> assertEquals("1", reply.commandId()))
    .thenRequest(1)
    .assertNext(reply -> assertEquals("2", reply.commandId()))
    .thenRequest(2)
    .assertNext(reply -> assertEquals("3", reply.commandId()))
    .assertNext(reply -> assertEquals("4", reply.commandId()))
    .verifyComplete();
~~~

This scenario verifies the bidirectional stream at the application contract level: the client sends multiple commands, the server processes and returns multiple replies, and the requester controls response demand. When run through a real RSocket server, it also tests routing, serialization, and channel transport.

To extend the lab:

1. Replace `concatMap` with `flatMap` at concurrency two; measure response ordering and active operations.
2. Add an asynchronous delay in the service and control response demand with StepVerifier.
3. Use a long or non-terminating command source to test cancellation.
4. Cancel the requester after one progress response and await the server-side probe.
5. Try completing the outbound source first and verify the response stream is still consumed to completion.
6. Have the service emit an error on the second command and verify the channel terminates per error policy.
7. Use multiple concurrent requesters to test channel limits and server-wide resources.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Passing a single object instead of a Publisher for input | Creates Request-Stream or Request-Response instead of Channel | Pass a Flux input and receive a Flux output |
| Confusing Request-Channel with two independent requests | Loses shared lifecycle and flow control | Use a single channel interaction |
| Thinking outbound complete means channel complete | May miss remaining responses | Continue consuming the response Flux |
| Using cancel to signal end of commands | Cancels the entire interaction | Complete the outbound Publisher normally |
| Ignoring demand | Causes uncontrolled buffering or load | Use backpressure-compliant operators and sources |
| Assuming REQUEST_N limits the entire server | Only regulates stream demand | Add admission control and concurrency limits |
| Using unbounded `flatMap` | Downstream can be overloaded | Set explicit concurrency and prefetch |
| Using `take(1)` and expecting the channel to continue | `take` cancels the upstream subscription | Use completion or an explicit stop protocol |
| Missing `commandId`/sequence | Hard to correlate replies under parallel processing | Add correlation IDs or sequences |
| Unit testing only a local Flux | Misses protocol, routing, or network cancellation | Add RSocket integration tests |
| Using `Thread.sleep` to wait for CANCEL | Flaky tests and hard to diagnose | Use a latch/probe with a deadline |
| Assuming cancellation stops blocking calls | Blocking tasks may keep running | Use cancelable APIs and internal timeouts |

## 16. Pre-Production Checklist for Channels

- [ ] Clearly defined the data flowing in both directions.
- [ ] Requester sends a multi-item Publisher and receives a Flux response.
- [ ] Responder accepts a Flux input and returns a Flux output.
- [ ] Routes and element types are declared consistently.
- [ ] `commandId`/correlation ID exists to match requests with responses.
- [ ] Decided whether response ordering must be preserved or parallel processing is allowed.
- [ ] Concurrency and prefetch are appropriately bounded.
- [ ] Backpressure has been tested in both directions.
- [ ] Hot sources have bounded buffers and an overflow policy.
- [ ] One-direction completion is distinguished from full-channel cancellation.
- [ ] Cancellation has been tested on both requester and responder.
- [ ] Downstream tasks release resources upon cancellation.
- [ ] Error handling does not leave the channel in an undefined state.
- [ ] Integration tests exist against a real RSocket transport.
- [ ] Metrics cover active channels, demand, cancellation, errors, and processing latency.
- [ ] Application-level limit exists for concurrent channel count.

## 17. References

- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — interaction models, RSocketRequester, annotated responders, and passing Publishers.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — REQUEST_CHANNEL, REQUEST_N, CANCEL, COMPLETE, and bidirectional flow control.
- [Project Reactor Reference: Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — StepVerifier, demand, cancellation, and testing Publishers.
- [Project Reactor API: Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) — `concatMap`, `flatMap`, `limitRate`, and stream processing operators.
