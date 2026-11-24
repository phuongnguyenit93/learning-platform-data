# Fire-and-Forget and Processing Acknowledgment Limits in RSocket

## Objectives

RSocket supports multiple interaction styles between two endpoints of a connection. **Fire-and-forget** (FNF) is a one-way message send: the requester sends a payload to the responder and does not request a response payload. It is a lightweight option for events that can tolerate best-effort processing, such as telemetry, typing indicators, or transient status updates.

The most important point to understand clearly is: **sending successfully does not mean processing succeeded**. In Spring, the **RSocketRequester.send()** method returns a **Mono that emits no value**. According to Spring documentation, this Mono only indicates that the message was sent successfully; it does not confirm that the responder received, persisted, processed, or completed the business operation.

Therefore, choosing FNF must be based on the criticality of the message and the level of confirmation the business requires. If you need to know whether the server accepted a command or completed processing, use Request-Response or a dedicated acknowledgment protocol.

## 1. Fire-and-Forget Among the Four RSocket Interaction Models

RSocket is a bidirectional communication protocol multiplexed over a single connection and supports transports such as TCP or WebSocket. Both sides can initiate requests; hence the accurate terms are requester and responder rather than assuming client and server.

RSocket has four primary interaction models:

| Interaction model | Data sent | Data received | Use case |
|---|---|---|---|
| Request-Response | One message | One response | Sending a command and needing a result or confirmation |
| Request-Stream | One message | A stream of responses | Sending search criteria and receiving multiple results |
| Request-Channel | A stream of messages | A bidirectional stream of responses | Continuous bidirectional data exchange |
| Fire-and-Forget | One message | No response payload | Sending telemetry or transient events without processing confirmation |

In the protocol, Fire-and-Forget is represented by the REQUEST_FNF frame. The requester sends one payload to the responder. The responder does not send back a corresponding response payload as in Request-Response or Request-Stream.

An FNF request still has a route and payload. Metadata can carry the route or other details; data carries the business content. However, there is no response message for the requester to read the processing result.

## 2. Confirmation Limits: Send Completion Is Not Handler Completion

On the Spring side, the common way to invoke FNF is:

~~~java
Mono<Void> result = requester
        .route("telemetry.record")
        .data(event)
        .send();
~~~

The send() method returns a Mono that emits no value. When that Mono completes normally, it only confirms that the requester's send operation completed per the Spring API. It **does not prove** that any of the following occurred:

- The responder executed the handler method.
- The payload passed all business validations.
- The database successfully wrote the data.
- The message was durably persisted.
- Downstream consumers received or processed the event.
- A side effect such as sending an email, updating a balance, or creating an order completed.

Three milestones must be separated:

1. **Send completion**: the sender finishes the message send operation.
2. **Handler completion**: the responder finishes processing inside the application.
3. **Business completion**: the business outcome meets the system's committed conditions, such as data committed or side effects completed.

With FNF, the requester receives no application-level acknowledgement to know milestone 2 or milestone 3. Even if the responder-side handler returns a Mono that emits no value and that Mono completes after writing to the database, that completion is still not sent back as a response to the FNF request.

This is a core limitation of the interaction model, not a bug in Reactor or Spring.

## 3. Sending Fire-and-Forget with RSocketRequester

Example requester connecting to an RSocket server over TCP:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester =
        RSocketRequester.builder().tcp("localhost", 7000);
~~~

In Spring, the builder creates an RSocketRequester. The connection is established when the requester executes its first request; subsequent requests can share the connection.

Creating a publisher to send telemetry:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class TelemetryPublisher {

    private final RSocketRequester requester;

    public TelemetryPublisher(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<Void> publish(TelemetryEvent event) {
        return requester
                .route("telemetry.record")
                .data(event)
                .send();
    }
}

record TelemetryEvent(
        String eventId,
        String type,
        long occurredAt
) {}
~~~

Steps:

1. route("telemetry.record") selects the responder's route.
2. data(event) supplies the payload to send.
3. send() selects the Fire-and-Forget interaction and returns an empty-valued Mono.
4. The caller decides how to compose this Mono into its reactive processing flow.

If another service is running in Reactor, return this Mono to the caller or chain it into a pipeline:

~~~java
public Mono<Void> recordAndPublish(TelemetryEvent event) {
    return telemetryRepository.save(event)
            .then(telemetryPublisher.publish(event));
}
~~~

This snippet only illustrates reactive pipeline composition. If saving telemetry and sending via RSocket must be atomic or must not lose messages if the process stops, a durable design like Transactional Outbox is needed; a plain save followed by send does not form a distributed transaction.

### Subscribing Is Required for the Request to Actually Execute

Reactor Publishers are lazy. Creating a Mono does not immediately run the send operation. The Mono must be subscribed to, or subscribed to by the framework/caller when the pipeline executes.

In a reactive controller or service, normally return the Mono for the framework or caller to manage:

~~~java
public Mono<Void> handleTelemetry(TelemetryEvent event) {
    return telemetryPublisher.publish(event);
}
~~~

At an imperative boundary such as a scheduled job, you can actively subscribe and handle errors:

~~~java
telemetryPublisher.publish(event)
        .doOnError(error ->
                log.warn("Failed to send telemetry over RSocket", error))
        .subscribe();
~~~

Do not call block() on an event loop or reactive request path because it can stall processing threads. Also avoid calling subscribe() arbitrarily inside services: doing so detaches the send from the caller's lifecycle and error handling.

Log messages should accurately reflect what was confirmed. For example, “FNF send completed” is more accurate than “Telemetry processed successfully”.

## 4. Receiving Fire-and-Forget with @MessageMapping

On the responder side, Spring uses @MessageMapping to map routes to handler methods. Example server receiving telemetry at route telemetry.record:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class TelemetryController {

    private final TelemetryService telemetryService;

    public TelemetryController(TelemetryService telemetryService) {
        this.telemetryService = telemetryService;
    }

    @MessageMapping("telemetry.record")
    public Mono<Void> record(TelemetryEvent event) {
        return telemetryService.record(event);
    }
}

record TelemetryEvent(
        String eventId,
        String type,
        long occurredAt
) {}

interface TelemetryService {
    Mono<Void> record(TelemetryEvent event);
}
~~~

The application must configure an RSocket server and RSocketMessageHandler to detect annotated responders. The snippet above is an illustrative controller/service, not a standalone Java program.

With one input payload and a void-emitting result, Spring can map the responder method for an FNF interaction. Returning a Mono without a value allows asynchronous processing without producing a response payload.

Inside the responder:

- Validate the payload before executing side effects.
- Use an event ID to support deduplication if the producer may resend.
- Log with correlation ID and route.
- Handle errors within the pipeline or route them to the application's error handling mechanism.
- Do not assume the requester will receive exceptions or results from the handler as a business response.

If an accepted or rejected status must be returned to the requester, change the contract to Request-Response.

## 5. When Should Fire-and-Forget Be Used?

FNF is suitable when losing an individual message does not corrupt critical business state, or when newer data will soon supersede older data.

Typically suitable examples:

- Telemetry and metrics where losing some samples is acceptable.
- User typing indicators in a chat conversation.
- Cursor position updates or transient UI states.
- Observational events that do not determine business outcomes.
- Cache refresh signals that can be re-emitted from another source.

FNF is typically unsuitable when the requester needs to know whether a command was accepted:

- Order creation.
- Payments or refunds.
- Inventory deduction or balance changes.
- Access permission changes.
- Mandatory audit logging.
- Critical notifications requiring delivery tracking.
- Any operation where the user must clearly see success or failure status.

Do not choose FNF just because it is shorter or requires less code. Choose according to the communication contract the business can accept.

## 6. Feedback and Backpressure Limits

FNF provides neither a response payload nor per-request acknowledgements. Therefore, the requester has no business-level signal to know whether the responder is processing fast or slow, or whether a message has finished processing.

### No Acknowledgment to Pace Emission by Processing Results

With Request-Stream and Request-Channel, RSocket provides a demand mechanism so requester and responder regulate the number of messages in a stream. FNF has no corresponding response stream and provides no demand tied to the completion of each business task.

The transport still manages byte transmission, but that does not replace application-level processing rate limits. If the producer sends faster than the consumer can handle, the system still risks work buildup, increased latency, or resource exhaustion.

Consider applying:

- Message emission rate limiting.
- Bounded queues.
- Worker concurrency limits.
- Batching or coalescing mergeable updates.
- An explicit drop policy for droppable telemetry.
- Metrics for messages received, processed, failed, and dropped.

Do not create an unbounded in-memory queue expecting the responder to keep up with every message.

### No Response to Propagate Business Errors Back to Requester

If the responder rejects a payload, validation fails, or database processing raises an error, the requester receives no response payload detailing the outcome of that operation.

The responder application must observe errors itself using logs, metrics, tracing, or internal handling mechanisms. If the producer needs to know the rejection reason, use Request-Response with an explicit result type.

### No Exactly-Once Completion Guarantee

FNF does not create an exactly-once guarantee for business processing. If the producer is unsure whether a message reached the responder and resends it, the responder may process duplicates. If the producer does not resend, a connection failure can leave the message unprocessed.

When retrying, use an event ID or idempotency key and design consumers to handle repeats safely. Never treat the absence of a response as proof that the responder has not processed the message.

## 7. Choosing Request-Response When Confirmation Is Needed

If the caller needs to know the server accepted or finished processing a command, use Request-Response. The responder returns an object; the requester uses retrieveMono() to receive the response.

Example contract confirming the server recorded a command:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.submit")
    public Mono<SubmissionAck> submit(OrderCommand command) {
        return orderService.accept(command)
                .map(orderId -> new SubmissionAck(orderId, "ACCEPTED"));
    }
}

record OrderCommand(String idempotencyKey, String productId, int quantity) {}

record SubmissionAck(String orderId, String status) {}
~~~

Requester:

~~~java
Mono<SubmissionAck> acknowledgement = requester
        .route("orders.submit")
        .data(command)
        .retrieveMono(SubmissionAck.class);
~~~

Here, the requester receives a typed response. However, the meaning of the acknowledgment depends on when the responder produces it:

- ACCEPTED: the server validated, checked, and persisted the command durably for later processing.
- COMPLETED: the business operation finished according to contract-defined conditions.
- REJECTED: the server rejected the command and can return an appropriate code/reason.

Do not return COMPLETED right after merely enqueuing a command into an in-memory queue. Name the status after the actual milestone the server has reached.

If an operation takes a long time, a common pattern is to return ACCEPTED with an operation ID, then expose a status endpoint or stream so the caller can track it until completion.

## 8. Comparing Interaction Model Choices

| Need | Recommended interaction | Reason |
|---|---|---|
| Send a transient event with no result needed | Fire-and-Forget | One-way, no response payload |
| Send a command and need accepted/rejected | Request-Response | Provides a single confirmation response |
| Send criteria and receive many results | Request-Stream | One request, multiple responses |
| Both sides exchange many messages continuously | Request-Channel | Bidirectional stream with demand |
| Send critical command needing completion tracking | Request-Response plus operation status | Separates intake confirmation from final processing state |

An application can use multiple interaction models over the same RSocket connection. Choose per route and contract rather than forcing the entire API into one style.

## 9. Making FNF Safer When Loss or Duplicates Are Allowed

Even though FNF has no acknowledgements, observability can still be improved and the impact of lost or duplicate messages reduced.

### Attach an Event ID and Emission Timestamp

Each message should carry a unique ID or idempotency key, emission timestamp, and event type:

~~~java
record TelemetryEvent(
        String eventId,
        String source,
        String type,
        long occurredAt
) {}
~~~

The responder can use the event ID to deduplicate events if the business requires it. Timestamps help detect stale or out-of-order data. Do not use a timestamp alone as an idempotency key because multiple events can share the same timestamp.

### Queue Bounds and Drop Policies

If the producer generates events rapidly, choose an explicit policy:

- Drop newest: discard new messages when the queue is full.
- Drop oldest: discard old messages to keep newer state.
- Coalesce: merge multiple updates into one latest update.
- Reject upstream: signal the data generator to slow down.
- Persist: write data to durable storage if it cannot be lost.

Choose the policy by data type. For cursor positions, keeping the latest state may be reasonable. For audit events, dropping is inappropriate.

### Use Transactional Outbox When the Producer Must Not Lose Events

If a database change and a message must be emitted together, write the business change and an outbox record in the same transaction. A worker reads the outbox and emits messages afterward.

Outbox addresses the risk of the process stopping after committing data but before sending the message. However, if the worker only emits FNF, it still does not know whether the responder finished processing. Producer-side outbox helps manage re-emission; it does not turn FNF into a confirmed processing protocol.

If confirmation from the responder is needed, add Request-Response, a dedicated acknowledgment route, or a durable mechanism with well-defined delivery states.

## 10. Testing Fire-and-Forget Properly

Test both sides separately because completion on the requester does not confirm completion on the responder.

### Testing the Requester

Verify that the requester constructs and subscribes to the publisher properly, handles connection or serialization errors, and does not turn send failures into false successes.

With Reactor Test, StepVerifier can verify that the Mono completes or emits an error:

~~~java
StepVerifier.create(publisher.publish(event))
        .verifyComplete();
~~~

This test only verifies that the requester-side publisher completes normally in the test setup. It does not prove the responder persisted data or completed side effects.

### Testing the Responder and Integration Flows

In integration tests, observe the responder-side outcome directly:

1. Start the RSocket server and handler.
2. Connect the requester.
3. Send an FNF event with a known event ID.
4. Wait for a test signal or query responder-side storage.
5. Verify the handler processed the event according to the contract.
6. Resend the same event ID and verify deduplication if required.
7. Disconnect or stop the server during sending to test error paths.
8. Verify metrics/logs accurately reflect sent counts and processed counts.

Do not use a single requester-side verifyComplete() as sole proof that responder-side business logic finished.

## 11. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Assuming send() completion means server finished processing | Confusing send completion with handler/business completion | Use Request-Response if acknowledgment is needed |
| Mono created yet no message is sent | Not subscribed or publisher not returned to framework | Connect Mono to an executed pipeline |
| Service subscribes internally causing errors to be lost from caller | Detaching publisher from caller's lifecycle | Return Mono to caller; subscribe at imperative boundaries |
| Calling block inside reactive request path | Blocking event-loop or processing threads | Compose Mono instead of blocking |
| Producer overwhelms responder resources | No rate limit or queue bounds | Rate limits, bounded queues, concurrency limits |
| Retries cause duplicate processing | Missing event ID or idempotency | Deduplicate by idempotency key |
| Unknown why responder rejected an event | FNF returns no business response | Log/emit metrics on responder or switch to Request-Response |
| Outbox marked completed too early | Relying solely on local send completion | Define clear confirmation milestones; use acknowledgments if needed |

## 12. Checklist Before Choosing Fire-and-Forget

- [ ] The message genuinely needs no response payload.
- [ ] Business requirements accept that the requester does not know whether the responder processed it.
- [ ] Losing an individual message does not corrupt critical state.
- [ ] An event ID or idempotency key exists if duplicate sends can occur.
- [ ] The producer enforces rate limits and queue bounds.
- [ ] The responder has its own logging, metrics, and error handling.
- [ ] The Mono from send is subscribed or returned for the framework/caller to manage.
- [ ] Send completion is never interpreted as business completion.
- [ ] Retry/drop/persist policies match the data category.
- [ ] Request-Response is used if the caller needs accepted/rejected or completion results.
- [ ] Requester sending and responder processing are tested separately.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Spring Javadoc — RSocketRequester.RequestSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RequestSpec.html)
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [RSocket Protocol](https://rsocket.io/about/protocol/)
