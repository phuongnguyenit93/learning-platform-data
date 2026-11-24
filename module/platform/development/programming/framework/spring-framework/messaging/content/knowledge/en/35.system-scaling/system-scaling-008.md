# Graceful Shutdown and Handling In-Flight Messages

## Objectives

A messaging application must not only handle requests properly while running. It must also stop safely upon receiving `SIGTERM`, deploying a new version, scaling down, or encountering an incident. If the process stops immediately while a request or stream is executing, consumers may see timeouts even though the server already committed part of the business work. Messages held only in memory can also be lost.

This lesson shows how to design graceful shutdown for Spring applications using RSocket and Reactor. After this lesson, you will be able to:

- Distinguish immediate shutdown from drained shutdown.
- Reject new requests while allowing in-flight requests to finish.
- Track in-flight Request-Response, Request-Stream, and Channel interactions.
- Handle completion, error, and cancellation so counters are released accurately.
- Set a drain deadline and decide what to do when time expires.
- Coordinate readiness, Spring lifecycle, transport, and Kubernetes.
- Close `RSocketRequester` or servers after necessary work has finished.
- Ensure retries, idempotency, and durable state when connections are severed.

## 1. Why Is Graceful Shutdown Needed?

Suppose a client sends an order-creation command. The server has already written the order to the database, but before sending the response, the process receives `SIGTERM`. If the server closes the connection immediately, the client may only see a transport error or timeout. The client has no way to know whether the order was created.

A stream can face a similar situation: the server has emitted several items, then the process stops before emitting the rest. With a Channel, client and server may be exchanging messages in both directions. A fire-and-forget task may also still be processing after the client sent the message.

Immediate shutdown can cause:

- In-flight requests to fail or be cancelled.
- Lost responses even though side effects already committed.
- Consumers retrying and creating duplicate side effects.
- Streams cut mid-flight, leaving clients unsure which portion was processed.
- In-memory messages lost when the process exits.
- Transactions, files, connection pools, or downstream resources left unreleased properly.
- New deployments starting while old instances have not finished leaving the system.

Graceful shutdown creates a window for the application to stop accepting new work, finish accepted work, persist necessary state, and close resources in order.

### 1.1. Distinguishing Termination Signals

In Reactor and RSocket, distinguish:

| Signal | Meaning | What to Do |
|---|---|---|
| `onComplete` | Publisher completed normally. | Decrement in-flight count and release resources. |
| `onError` | Publisher terminated with an error. | Record the error, persist state, and decrement in-flight count. |
| `cancel` | Subscriber requested stopping the stream. | Cancel upstream properly, run cleanup, and preserve committed side effects. |
| Process shutdown | Application begins stopping. | Reject new work, drain running work, then close transport. |

Cancellation is not a rollback. If the server committed a change before receiving `CANCEL`, that change remains. Similarly, a request ending in an error does not prove none of the business logic ran.

### 1.2. What Is In-Flight?

A request is considered in-flight from the moment the application accepts it for processing until its corresponding publisher terminates with complete, error, or cancel.

For Request-Response, this duration typically spans validation, service calls, data writes, and response creation. For Request-Stream or Channel, it can last until the stream finishes or is cancelled.

Do not count only the time before emitting the first payload. A stream that has emitted several items is still in-flight until a terminal signal occurs.

Also distinguish an accepted request from a durably stored message. If work is handed off to a durable queue or background worker, the handler's publisher may finish right after writing the message to an outbox/queue. In that case, the worker must have its own draining and checkpointing mechanism.

## 2. Safe Shutdown Sequence

A general sequence:

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as Spring Application
    participant C as RSocket Clients
    participant S as RSocket Server
    participant D as Database / Queue

    O->>A: SIGTERM / shutdown signal
    A->>A: Mark instance NOT_READY
    A->>A: Stop admission of new work
    C->>S: Existing requests and streams continue
    S->>D: Complete and persist in-flight work
    D-->>S: Commit / durable checkpoint
    S-->>C: Final response or stream completion
    A->>A: Wait for in-flight count = 0
    A->>S: Close listener and connections
    A->>C: Dispose outbound requester
    A->>D: Close remaining resources
    A-->>O: Process exits
~~~

Steps to execute:

1. **Leave new traffic:** mark the instance unready for traffic and wait for service discovery/load balancers to update.
2. **Close admission:** reject new requests, including requests arriving over already-open RSocket connections.
3. **Drain:** wait for running publishers to complete or error; handle cancellations and save recovery state.
4. **Enforce a deadline:** if draining exceeds the time limit, shut down cleanly per policy and ensure unfinished work can be reconciled.
5. **Close transport:** stop listeners, close connections, and dispose requesters.
6. **Close dependencies:** flush outboxes/checkpoints, close connection pools, and release remaining resources.
7. **Exit process:** finish before the orchestrator forcefully kills the process.

The exact ordering among components depends on how the application owns servers, queues, and workers. What matters is never closing a dependency that running requests still need.

## 3. Readiness Does Not Replace Admission Control

Readiness indicates whether an instance should receive new traffic through service discovery or a load balancer. It does not automatically block requests arriving on existing connections.

RSocket multiplexes many streams over a single connection. A client may open a connection prior to shutdown and keep sending new requests over that connection. Even after the endpoint is removed from the load balancer, already-open connections can persist.

Therefore, the application needs two layers:

- **Readiness:** stop routing new connections to the instance.
- **Admission control:** check shutdown state at the handler boundary and reject new work even on existing connections.

When using Spring Boot Actuator Availability, the application can switch readiness to `REFUSING_TRAFFIC` when shutdown starts. Example:

~~~java
AvailabilityChangeEvent.publish(
    applicationContext,
    this,
    ReadinessState.REFUSING_TRAFFIC
);
~~~

This snippet assumes an `ApplicationContext` and imported availability classes from Spring Boot. Publish the event at the start of the shutdown process, early enough for endpoint routing to propagate.

Do not rely on readiness alone to conclude no new requests can arrive. An in-application admission gate must still protect routes.

## 4. Tracking In-Flight Requests with Reactor

A straightforward approach is maintaining an in-flight counter. Each accepted request increments the counter once; when the publisher completes, errors, or cancels, the counter decrements once.

Lazy registration is crucial. The counter increments only when the publisher is subscribed to and work actually begins. Creating a `Mono` or `Flux` without subscribing means no request has started executing yet.

### 4.1. `InFlightRequests`

The following example provides two wrappers for Request-Response and streams:

~~~java
package com.example.messaging;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

@Component
public class InFlightRequests {

    private final AtomicBoolean accepting = new AtomicBoolean(true);
    private final AtomicInteger active = new AtomicInteger();
    private final Sinks.One<Void> drained = Sinks.one();

    public <T> Mono<T> trackMono(Supplier<Mono<T>> work) {
        return Mono.defer(() -> {
            if (!enter()) {
                return Mono.error(new ServiceStoppingException());
            }

            return Mono.defer(work)
                .doFinally(signal -> leave());
        });
    }

    public <T> Flux<T> trackFlux(Supplier<Flux<T>> work) {
        return Flux.defer(() -> {
            if (!enter()) {
                return Flux.error(new ServiceStoppingException());
            }

            return Flux.defer(work)
                .doFinally(signal -> leave());
        });
    }

    private boolean enter() {
        if (!accepting.get()) {
            return false;
        }

        active.incrementAndGet();

        // Re-check to avoid a race with beginDrain().
        if (accepting.get()) {
            return true;
        }

        leave();
        return false;
    }

    private void leave() {
        if (active.decrementAndGet() == 0 && !accepting.get()) {
            drained.tryEmitEmpty();
        }
    }

    public Mono<Void> beginDrain() {
        accepting.set(false);

        if (active.get() == 0) {
            drained.tryEmitEmpty();
        }

        return drained.asMono();
    }

    public int activeCount() {
        return active.get();
    }

    public static final class ServiceStoppingException
            extends RuntimeException {

        public ServiceStoppingException() {
            super("Service is shutting down");
        }
    }
}
~~~

The counter is updated according to these rules:

- `enter()` admits requests only while `accepting` is true.
- After incrementing the counter, `enter()` re-checks state to handle races with `beginDrain()`.
- `doFinally` runs on publisher complete, error, or cancel, so `leave()` is called on all three termination paths.
- `beginDrain()` flips admission to false and completes the `drained` signal once `active` reaches 0.
- Requests arriving after draining starts receive `ServiceStoppingException`.

Checking `accepting` twice is essential. Checking only once before incrementing could allow shutdown to observe `active == 0` and finish draining right before the new request registers.

`Sinks.One` emits a single completion signal once no work remains. This example assumes an `ApplicationContext` undergoes one shutdown cycle; if the application stops and restarts the same bean, redesign drain signal initialization per cycle.

### 4.2. Wrapping Spring RSocket Handlers

Request-Response:

~~~java
@Controller
public class OrderController {

    private final InFlightRequests inFlight;
    private final OrderService service;

    public OrderController(
        InFlightRequests inFlight,
        OrderService service
    ) {
        this.inFlight = inFlight;
        this.service = service;
    }

    @MessageMapping("orders.submit")
    public Mono<OrderAccepted> submit(
        @Payload SubmitOrder command
    ) {
        return inFlight.trackMono(
            () -> service.submit(command)
        );
    }
}
~~~

Request-Stream:

~~~java
@MessageMapping("orders.events")
public Flux<OrderEvent> events(
    @Payload OrderQuery query
) {
    return inFlight.trackFlux(
        () -> service.events(query)
    );
}
~~~

The examples assume `OrderService` returns `Mono<OrderAccepted>` and `Flux<OrderEvent>`. DTO, service, and annotation imports are omitted from the second snippet to focus on wrapping the publisher.

For Channel, the handler receives an input `Flux` and returns an output `Flux`. Wrap the handler's entire output publisher so the counter stays active while the exchange remains live. Verify cancellation and completion of both data directions according to the handler's contract.

Do not increment/decrement the counter at multiple nested layers for the same logical request. Pick one clear boundary—typically the handler or application service entry point—to avoid double counting.

### 4.3. Do Not Overlook Synchronous Errors and Empty Publishers

A `Supplier` may throw an exception before returning a publisher. `Mono.defer` and `Flux.defer` convert that synchronous exception into `onError`, so `doFinally` still releases the counter.

`Mono.empty()` completes normally and decrements the counter. A cancelled publisher also decrements the counter. You do not need three separate cleanup branches when `doFinally` wraps the whole publisher.

Do not manually subscribe inside a handler to launch background work and return `Mono.empty()`. If the application genuinely needs background processing, write the work to a durable queue/outbox before finishing the handler and manage the worker with its own lifecycle.

## 5. Draining When the Spring `ApplicationContext` Closes

For servers whose lifecycle is managed by Spring Boot's `ApplicationContext`, you can use `ContextClosedEvent` to close admission and wait for running requests before lifecycle beans and transports are stopped.

Example:

~~~java
package com.example.messaging;

import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class DrainOnContextClose {

    private static final Logger log =
        LoggerFactory.getLogger(DrainOnContextClose.class);

    private final InFlightRequests inFlight;

    public DrainOnContextClose(InFlightRequests inFlight) {
        this.inFlight = inFlight;
    }

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        inFlight.beginDrain()
            .timeout(Duration.ofSeconds(25))
            .doOnError(error -> log.warn(
                "Drain deadline reached; active requests: {}",
                inFlight.activeCount(),
                error
            ))
            .onErrorResume(error -> Mono.empty())
            .block();
    }
}
~~~

In Spring's default configuration, event listeners are invoked synchronously during context closure. The handler switches admission to false, waits up to 25 seconds for the `drained` signal, and then allows context closing to proceed.

If the application changes `ApplicationEventMulticaster` to async, do not assume this listener still blocks shutdown. In that case, use a lifecycle coordinator with explicitly verified callbacks and phase ordering.

The timeout here bounds only how long draining waits. It does not automatically cancel running requests or roll back the database. Once 25 seconds elapse, the application continues closing the context; the transport may sever remaining streams. Unfinished operations must rely on durable state, checkpoints, or reconciliation workflows to recover.

Do not use `ContextClosedEvent` to start new background tasks. It is the time to stop accepting work and finish what was already admitted.

## 6. Spring Boot Graceful Shutdown Configuration

For applications with an embedded web server such as Tomcat, Jetty, Reactor Netty, or Undertow, Spring Boot supports graceful shutdown:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

`server.shutdown=graceful` instructs the embedded web server to stop accepting new requests at the network layer and give in-flight requests a chance to finish. `spring.lifecycle.timeout-per-shutdown-phase` sets the wait timeout for each Spring lifecycle phase.

Distinguish the scope:

- For standard HTTP endpoints, embedded web server graceful shutdown helps drain active requests.
- For RSocket over WebSocket, the HTTP server manages transport and handshake; post-handshake RSocket sessions are long-lived connections carrying many streams. Do not assume the HTTP timeout automatically drains all running RSocket streams.
- For standalone RSocket TCP listeners, `server.shutdown` is not a general setting for draining RSocket TCP. An admission gate and server-management lifecycle are needed.

Even when Spring Boot manages the server automatically, the application should still track in-flight work at the handler level if business guarantees require it. Check the specific transport and test shutdown in integration tests.

## 7. Handling Drain Deadline Expiration

Not every request finishes within the shutdown window. A stream may run for hours, downstream may hang, or a task may be waiting on a user.

Define clear bounds:

- **Request deadline:** maximum time for a single business operation.
- **Stream lifetime:** maximum lifetime for long-lived streams if the contract permits.
- **Drain deadline:** how long the instance waits for current work to finish during shutdown.
- **Process termination deadline:** time allowed by the orchestrator before forcefully killing the process.

The drain deadline must be smaller than the remaining termination time after subtracting `preStop`, propagation, and cleanup. Never set the drain deadline longer than the process is allowed to live.

When the deadline expires:

1. Record metrics and log the count of still-active requests.
2. Persist checkpoints or operation state if not already saved.
3. Ensure clients can query outcomes by operation ID.
4. Never emit a success confirmation if nothing committed.
5. Allow the orchestrator to terminate the process at the final deadline.

Do not try to hold the process open forever waiting for a publisher that never terminates. Nor should you automatically mark every remaining request as failed without checking side effects.

### 7.1. Handling by Message Type

| Message Type | Drain Policy |
|---|---|
| Request-Response | Allow the handler to finish and commit before sending the response. |
| Request-Stream | Wait for stream complete/error or client cancel; cap stream lifetime if needed. |
| Channel | Stop accepting new work per policy, finish already-received items, and emit final results if possible. |
| Fire-and-Forget | Do not treat sending the frame as business confirmation; persist work durably and provide status queries if callers need guarantees. |
| Background worker | Stop pulling new messages, complete or checkpoint the current message, then close the consumer. |

### 7.2. Poison Messages and Unrecoverable Tasks

A message may fail repeatedly due to invalid data or incompatible dependencies. Do not let one such message block the entire drain.

Worker design should:

- Cap retry attempts.
- Distinguish transient errors from permanent errors.
- Route unprocessable messages to a dead-letter queue or quarantine area if the architecture supports it.
- Record failure reason, attempt count, and correlation ID.
- Never acknowledge a message before durable state is recorded.

On shutdown, workers should stop fetching new messages and finish or return the in-flight message according to broker semantics. Ack/nack details depend on the message broker; RSocket itself does not provide a durable queue or business delivery guarantee.

## 8. Closing Client `RSocketRequester` in the Right Order

`RSocketRequester` is the client API and implements `Disposable`. Calling `dispose()` tears down the requester and its underlying connection.

If disposed too early, running requests may fail or streams may be cancelled. Therefore, the client side also needs draining:

1. Stop issuing new requests.
2. Wait for active outbound publishers to complete/error/cancel.
3. Record requests with unknown outcomes for later status queries.
4. Call `requester.dispose()`.
5. Close other dependencies.

Example closing a requester in bean lifecycle:

~~~java
@Component
public class OrderRSocketClient {

    private final RSocketRequester requester;

    public OrderRSocketClient(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("order-service", 7000);
    }

    public Mono<OrderAccepted> submit(SubmitOrder command) {
        return requester
            .route("orders.submit")
            .data(command)
            .retrieveMono(OrderAccepted.class);
    }

    @PreDestroy
    public void close() {
        requester.dispose();
    }
}
~~~

This is a minimal example. In production, wait for outbound in-flight work inside a shutdown coordinator before beans are destroyed. `@PreDestroy` should perform only the final `dispose` step after the coordinator has drained; it does not automatically know about other running publishers.

Never dispose a shared requester after every request. A single requester can serve many concurrent streams.

## 9. Closing RSocket Servers and Listeners

With Spring Boot auto-configuration, the RSocket server is managed by the `ApplicationContext` lifecycle. Ensure the admission gate has drained before the context stops the server and the beans needed by handlers.

If the application manually builds an RSocket server using RSocket Java, keep the server handle returned at bind time. Once admission is closed and in-flight reaches 0 or the deadline is handled, dispose the handle to stop the listener and release transport resources.

Do not assume closing the listener automatically lets running requests finish. Test how your transport and server implementation treat open connections and streams. With custom lifecycles, order phases so the admission/drain coordinator runs before closing the listener; if two beans share the same phase, they may be stopped in the same group and draining may not happen before the listener closes.

With RSocket over WebSocket, web server shutdown also affects connections. Define how long-lived sessions are closed and how clients are notified to reconnect or resume operations.

## 10. Coordinating with Kubernetes and Deployments

Kubernetes sends a termination signal when a Pod is terminated. The application has a bounded grace period before the process is forcefully killed.

A deployment setup should include:

- Readiness probes to remove the instance from endpoint routing.
- A `preStop` hook or equivalent mechanism to let routing update before the process stops if infrastructure needs propagation time.
- A `SIGTERM` handler and Spring lifecycle to close admission.
- A drain deadline smaller than `terminationGracePeriodSeconds`.
- Checkpoints, idempotency, and reconciliation for work that could exceed the deadline.
- Shutdown metrics to verify instances actually drain.

Example timing configuration:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
~~~

This is only an illustrative duration. Sum up the time for `preStop`, propagation, draining, Spring lifecycle shutdown, and cleanup. If the total could exceed 60 seconds, adjust deadlines or orchestrator settings to match real requirements.

Do not use a fixed sleep as the sole solution. A delay only gives endpoint routing time to update; it does not prove zero requests remain running. Admission gates and in-flight trackers control the work inside the process.

## 11. Observing the Shutdown Process

Record the following metrics:

- Current in-flight request count.
- New requests rejected due to shutdown.
- Duration from drain start until active count reaches 0.
- Remaining request count when drain deadline expires.
- Streams cancelled during shutdown.
- Operations checkpointed or queued for retry.
- Requesters/server connections disposed.
- Errors occurring during shutdown.

Logs should include correlation ID, operation ID, and route for tracing. Never log sensitive payloads or credentials.

Useful log lines to emit:

~~~text
shutdown_started accepting=false active=12
shutdown_draining active=4 elapsed_ms=8200
shutdown_completed active=0 elapsed_ms=10450
~~~

This is illustrative output, not logs automatically emitted by Spring. The application must instrument its own lifecycle milestones and tracker.

If draining frequently hits the deadline, investigate the root cause: unbounded streams, slow downstream, consumers failing to cancel, hung workers, or overly long business timeouts. Merely raising the termination grace period without finding the cause can mask deeper issues.

## 12. Testing Graceful Shutdown

Test both publisher behavior and transport lifecycle.

### 12.1. Unit Tests for the Tracker

Key scenarios:

1. Requests are admitted while `accepting=true`.
2. New requests are rejected after `beginDrain()`.
3. Drain does not complete while a request remains active.
4. Drain completes after the request completes.
5. Drain completes after the request errors.
6. Drain completes after the subscriber cancels.
7. Races between `enter()` and `beginDrain()` never make the counter negative or drop a request.

You can use `TestPublisher` to keep a publisher open and explicitly complete or cancel it in tests. `StepVerifier` helps verify the exact moment draining completes.

### 12.2. Testing Cancellation

Example verifying the tracker releases the counter when the subscriber cancels:

~~~java
TestPublisher<String> work = TestPublisher.create();
InFlightRequests tracker = new InFlightRequests();

StepVerifier.create(
        tracker.trackMono(work::mono)
    )
    .then(() -> {
        assertEquals(1, tracker.activeCount());
    })
    .thenCancel()
    .verify();

assertEquals(0, tracker.activeCount());
~~~

The example assumes JUnit `assertEquals` and `reactor-test` in test scope. `TestPublisher` keeps the publisher open until the subscriber cancels; `doFinally` in the tracker must run and bring `active` back to 0.

### 12.3. Integration Tests with RSocket

Unit tests do not verify that a real transport drains properly. Integration tests should:

- Open an RSocket connection and send a request whose completion time can be controlled.
- Initiate shutdown while that request is running.
- Send another request over the existing connection and assert it is rejected.
- Complete the first request and assert the response is received.
- Verify the server closes the listener after draining.
- Verify the client receives an appropriate error when new requests are rejected.
- Test Request-Stream/Channel behavior on cancel or when the drain deadline expires.

For Kubernetes, run real deployment tests or staging tests to verify readiness propagation, `SIGTERM`, and termination deadlines.

### 12.4. What to Assert in Tests

- Counter increments exactly once per logical request.
- Counter decrements on complete, error, and cancel.
- No new requests are accepted after admission closes.
- Databases/queues are not closed before handlers finish.
- Requests with side effects are not retried as duplicates after responses are lost.
- Long-lived streams enforce timeout or checkpoint policies.
- Shutdown does not exceed the termination grace period in normal scenarios.
- When the deadline expires, remaining operations can be queried and recovered.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Only marking readiness false | New requests can still arrive over existing RSocket connections. | Use an admission gate at handlers. |
| Closing the requester before draining | Running outbound requests fail or cancel. | Wait for outbound in-flight work before disposing. |
| Decrementing counter only on complete | Counter gets stuck when publishers error or cancel. | Use `doFinally`. |
| Incrementing counter when constructing `Mono` | Unsubscribed publishers are counted as active. | Use `Mono.defer` and increment on subscribe. |
| Tracking only until the first payload | Stream keeps running while drain thinks it finished. | Track until terminal signals. |
| Treating cancel as rollback | Committed side effects are ignored in state. | Persist outcomes durably and support reconciliation. |
| Waiting indefinitely to drain | Pod fails to exit before the termination deadline. | Set a drain deadline and checkpoint remaining work. |
| Relying on `server.shutdown` for every RSocket TCP server | Standalone TCP listeners are not managed like embedded web servers. | Use lifecycle hooks and transport-specific shutdown. |
| Relying on `@PreDestroy` to start draining | Dependencies may already be shutting down. | Start draining before bean destruction phases. |
| Not tracking background workers | Handlers finish while workers keep running as process stops. | Drain workers and queue consumers separately. |
| Acking messages before committing | Messages can be lost before business work is durable. | Commit/checkpoint before acknowledgement. |
| Retrying timed-out requests with a new key | Side effects can execute twice. | Keep the idempotency key and query status. |

## 14. Deployment Checklist

- [ ] Readiness switches to `REFUSING_TRAFFIC` when shutdown starts.
- [ ] Admission gate rejects new requests even on open connections.
- [ ] Every handler is tracked from subscribe to complete/error/cancel.
- [ ] Counter does not increment before a publisher is subscribed to.
- [ ] Request-Stream and Channel drain until terminal signal or deadline.
- [ ] Background workers and queue consumers have separate draining procedures.
- [ ] Side effects are committed or checkpointed before confirming.
- [ ] Operation IDs/idempotency exist to handle unknown outcomes.
- [ ] Drain deadline is smaller than the process termination deadline.
- [ ] Drain timeouts are not misinterpreted as rollbacks or guaranteed failures.
- [ ] `RSocketRequester` disposes only after outbound requests have drained.
- [ ] RSocket servers/listeners close only after admission and draining complete per policy.
- [ ] Differences between TCP, WebSocket, and embedded web servers have been verified.
- [ ] Metrics, logs, and runbooks exist for shutdown timeouts.
- [ ] Unit and integration tests cover complete, error, cancel, and requests arriving during drain.

## References

- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): graceful shutdown configuration for embedded web servers and lifecycle timeouts.
- [Spring Framework Reference — Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): lifecycle callbacks and bean lifecycle management.
- [Spring Framework Javadoc — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html): `start`, `stop`, callbacks, and phase ordering.
- [Spring Boot Reference — Availability](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): application availability and readiness state.
- [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, `TestPublisher`, and virtual time.
- [RSocket Protocol](https://rsocket.io/about/protocol/): stream lifecycle, `CANCEL`, `ERROR`, and connection semantics.
