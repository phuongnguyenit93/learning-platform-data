# One-Way Sending with `RSocketRequester.send()`

## Objectives

After this lesson, you can create an RSocket request that only sends data to the receiver, select the Fire-and-Forget interaction model with `send()`, integrate `Mono<Void>` into a reactive flow, and understand accurately what is confirmed when the Mono completes.

## 1. What Is One-Way Sending in RSocket?

RSocket defines four main interaction models:

| Interaction | Data sent | Data received | Suitable use case |
|---|---|---|---|
| Request-Response | One message | One response | Need a result or business confirmation immediately in the same request |
| Request-Stream | One message | A stream of responses | Send query criteria and receive multiple results |
| Channel | One stream | One stream | Both sides exchange multiple messages over time |
| Fire-and-Forget | One message | No response | Send an event or notification where the sender does not need a return result |

Fire-and-Forget is a one-way sending model. The sender creates a request, the receiver can process the payload, but the protocol does not generate a response payload for that request. In the RSocket protocol, this request type is represented by the `REQUEST_FNF` frame.

In Spring, `RSocketRequester` belongs to the `spring-messaging` module and provides a fluent API to declare route, payload, metadata, and the interaction to perform. The `send()` method selects Fire-and-Forget.

The most important point to remember: `send()` returns `Mono<Void>`. This Mono indicates whether sending the payload succeeded or encountered an error during sending. It **does not confirm** that the handler on the receiving machine ran, finished processing, or persisted data successfully.

## 2. Call Structure

~~~java
Mono<Void> completion = requester
        .route("audit.record")
        .data(event)
        .send();
~~~

Meaning of each step:

1. `route("audit.record")`: declares the route sent in the request metadata. The receiver uses this route to find the corresponding handler.
2. `data(event)`: sets the object as the payload. Spring uses the encoder registered in `RSocketStrategies` to serialize the object.
3. `send()`: performs Fire-and-Forget and returns `Mono<Void>`.

`send()` is the terminal operation that completes declaring the request. Do not call `retrieveMono()` or `retrieveFlux()` after it to obtain a response; Fire-and-Forget has no response payload.

The payload can be a single object, string, byte array, or another data type supported by both the sender's encoder and the receiver's decoder. If additional metadata needs to be sent, you can add `metadata(value, mimeType)` before `data(...)`. With default composite metadata, each metadata value must have a matching encoder and the receiver must register how to decode it.

## 3. Lifecycle of `Mono<Void>`

`Mono<Void>` is a Reactive Streams Publisher that emits no data values. It can only complete or emit an error signal.

- **Complete:** sending the payload completed successfully from the requester's perspective.
- **Error:** the requester encountered an error while connecting, encoding, or sending the payload.
- **No business response:** the requester does not receive processing results from the handler.

A Mono is part of a reactive pipeline. If you create the Mono and discard it, the request will not be triggered. Return the Mono to the outer reactive component or combine it into the running pipeline.

~~~java
public Mono<Void> publish(AuditEvent event) {
    return requester.route("audit.record")
            .data(event)
            .send()
            .doOnSuccess(ignored ->
                    log.debug("RSocket payload sent"))
            .doOnError(error ->
                    log.warn("Failed to send RSocket payload", error));
}
~~~

This usage leaves subscription control to the caller. For example, a WebFlux controller can directly return the `Mono<Void>` from the service. In an imperative program or a command-line demo snippet, you can call `block(Duration)` at the imperative boundary to wait for the send operation; do not block on the WebFlux/Reactor Netty event loop.

Avoid calling `subscribe()` inside a service just to "make the request run." Subscribing manually detaches the send operation from the current request lifecycle, making it hard for the caller to control errors, completion timing, and task cancellation. If an independent background task is genuinely needed, there must be a place managing the subscription and handling errors explicitly.

## 4. Spring Boot Example: Sending an Audit Event

The example below uses Java 17+ and Spring Boot. Place the receiving part in the server application and the sending part in the client application. Both require the `spring-boot-starter-rsocket` dependency; both sides must use compatible DTOs and compatible codecs.

### 4.1. Dependency

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
~~~

Spring Boot automatically configures `RSocketStrategies` and common JSON/CBOR codecs. If using custom data types or MIME types, register the corresponding encoders/decoders on both sides.

### 4.2. Shared DTO

~~~java
package com.example.rsocket;

public record AuditEvent(
        String eventId,
        String action,
        long occurredAtEpochMillis
) {
}
~~~

`eventId` is the event identifier. In systems with retries or potential duplicate sends, the receiving side can use this ID to implement idempotent processing.

### 4.3. Receiving Side: Declaring the Route

Configure the server in `application.properties`:

~~~properties
spring.rsocket.server.port=7000
~~~

Create the handler:

~~~java
package com.example.rsocket.server;

import com.example.rsocket.AuditEvent;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class AuditReceiver {

    private final AuditService auditService;

    public AuditReceiver(AuditService auditService) {
        this.auditService = auditService;
    }

    @MessageMapping("audit.record")
    public Mono<Void> receive(AuditEvent event) {
        return auditService.store(event);
    }
}
~~~

Example service to observe the handler being invoked:

~~~java
package com.example.rsocket.server;

import com.example.rsocket.AuditEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class AuditService {

    private static final Logger log =
            LoggerFactory.getLogger(AuditService.class);

    public Mono<Void> store(AuditEvent event) {
        return Mono.fromRunnable(() ->
                log.info("Received eventId={}, action={}",
                        event.eventId(), event.action()));
    }
}
~~~

`@MessageMapping("audit.record")` maps the route sent by the client. The handler receives the payload decoded as `AuditEvent`. Returning `Mono<Void>` indicates the handler produces no response payload; the service's pipeline still needs to be returned so Spring manages the execution.

In a real application, replace the logging with appropriate persistence logic. If using R2DBC or a reactive repository, return the Mono from the save operation directly. If calling a blocking API or library, do not perform blocking I/O directly on the event loop; choose an appropriate integration approach and scheduler.

### 4.4. Sending Side: Calling `send()`

Spring Boot provides the `RSocketRequester.Builder` bean. Create a requester connecting to the server and reuse that requester:

~~~java
package com.example.rsocket.client;

import com.example.rsocket.AuditEvent;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class AuditPublisher {

    private final RSocketRequester requester;

    public AuditPublisher(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("localhost", 7000);
    }

    public Mono<Void> publish(AuditEvent event) {
        return requester.route("audit.record")
                .data(event)
                .send();
    }
}
~~~

When the caller subscribes to the returned Mono, the requester executes the request. The connection is established when needed; creating the requester with the builder does not mean the payload has already been sent.

Example integration in a WebFlux handler:

~~~java
@PostMapping("/audit")
public Mono<Void> publish(@RequestBody AuditEvent event) {
    return auditPublisher.publish(event);
}
~~~

When the Mono completes, the sending application knows the send operation completed. That **does not mean** the record was committed in the server-side database. If the HTTP API needs to return `202 Accepted`, understand this as a sending-layer confirmation per the application contract; do not interpret it as confirmation of successful processing in the receiving system.

## 5. Choosing `send()` or Another Method?

| API | Interaction | Return value | When to choose |
|---|---|---|---|
| `send()` | Fire-and-Forget | `Mono<Void>` | Only need to send a payload, no response needed |
| `retrieveMono(Type.class)` | Request-Response | `Mono<Type>` | Need a response or business ACK |
| `retrieveFlux(Type.class)` | Request-Stream or Request-Channel, depending on input cardinality | `Flux<Type>` | Need to receive multiple responses |
| `sendMetadata()` | Metadata-Push | `Mono<Void>` | Send connection-level metadata, not a routed business payload |

If business logic needs to know "has the server received and saved it successfully?", design an explicit confirmation. The simplest approach is Request-Response: the handler returns an ACK DTO and the client calls `retrieveMono(Ack.class)`. If you need one-way sending while still receiving feedback later, you can design a separate ACK route or a bidirectional event stream; in that case you must manage correlation IDs and timeouts.

## 6. Common Errors and How to Handle Them

### Creating a Mono Without Subscribing

~~~java
public void publish(AuditEvent event) {
    requester.route("audit.record")
            .data(event)
            .send(); // Mono is discarded, request is not triggered
}
~~~

**Fix:** change the method return type to `Mono<Void>` and return the publisher to the caller. Only subscribe at an imperative boundary or in the component that genuinely owns the background task's lifecycle.

### Assuming Mono Completion Means the Server Finished Processing

This is the most critical misconception. `send()` returns no response and provides no confirmation of remote processing state. A `"payload sent"` log on the client does not replace logs, metrics, or business state on the server.

**Fix:** if an ACK is needed, use Request-Response or design a separate confirmation channel. If data must not be lost, consider a durable message broker, transactional outbox, and controlled retry mechanisms rather than relying on Fire-and-Forget.

### Route Mismatch Between Both Sides

If the client sends `audit.record` while the handler declares a different route, the intended handler will not be invoked.

**Fix:** agree on routes as part of the contract between both applications; check dots, names, and route patterns.

### Codec Mismatch Between Both Sides

If the client sends an object without a matching decoder on the server, or with incompatible MIME types, encoding/decoding errors can occur.

**Fix:** use codecs supported on both sides; for JSON/CBOR DTOs, check `RSocketStrategies` and dependencies. For custom metadata, register encoders and decoders with the same MIME type.

### Swallowing Send Errors

If you use `onErrorResume(error -> Mono.empty())` without logging or propagating the error, the caller may think the request succeeded.

**Fix:** log and propagate errors according to application policy. Note that transport/serialization errors can surface on the Mono; remote business processing errors are not returned as a response to Fire-and-Forget.

### Retries Causing Duplicate Processing

When send status is uncertain, retries can cause the receiving side to see the same event multiple times.

**Fix:** attach a stable `eventId`, record processed markers on the receiving side, and design idempotent operations. Do not assume Fire-and-Forget provides exactly-once delivery on its own.

### Confusing `send()` with `sendMetadata()`

`send()` sends a Fire-and-Forget request with route/payload. `sendMetadata()` emits a connection-level metadata notification. Choose the right API based on the kind of data and scope of information to transmit.

## 7. Flow Diagram

~~~mermaid
sequenceDiagram
    participant App as Sender application
    participant Req as RSocketRequester
    participant Server as RSocket server
    participant Handler as @MessageMapping handler

    App->>Req: route + data + send()
    Req->>Server: REQUEST_FNF (payload + metadata)
    Server->>Handler: dispatch by route
    Req-->>App: Mono<Void> complete or error
    Note over App,Handler: No response payload confirming remote processing
~~~

The diagram illustrates two distinct flows to separate: sending on the requester side and processing on the responder side. Fire-and-Forget does not connect the handler's processing outcome back to the sender-side Mono.

## 8. Adoption Checklist

- [ ] Chose Fire-and-Forget because the sender does not need a business response.
- [ ] Route in `route(...)` matches `@MessageMapping(...)`.
- [ ] Payload has compatible encoders/decoders on both sides.
- [ ] Mono from `send()` is returned or subscribed at the place managing lifecycle.
- [ ] Send errors are logged and handled.
- [ ] Mono completion is not interpreted as confirmation that remote persisted the data.
- [ ] If retries exist, receiver handles idempotently using an event identifier.
- [ ] If delivery guarantees or ACKs are required, a more suitable mechanism than Fire-and-Forget was chosen.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, `RSocketRequester`, `send()`, routes, payloads, and annotated responders.
- [Spring Framework Javadoc — RSocketRequester.RetrieveSpec](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html): return contract of `send()` and differences from `retrieveMono()`.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): server configuration, `RSocketStrategies`, and `RSocketRequester.Builder`.
