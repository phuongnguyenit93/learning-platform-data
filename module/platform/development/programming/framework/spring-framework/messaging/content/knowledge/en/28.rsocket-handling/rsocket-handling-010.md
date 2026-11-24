# Separating Business Processing from Transport Operations and Connection Sessions

## Objectives

After this lesson, you will be able to design a Spring RSocket application so that use cases and business rules do not depend on `RSocketRequester`, routes, payloads, TCP/WebSocket, or the lifecycle of a connection. You will also know how to place connection handling in the right adapter, manage connected clients safely, and test business logic without opening a socket.

## 1. Why Separate Them?

RSocket is a bidirectional communication protocol supporting Request-Response, Request-Stream, Request-Channel, and Fire-and-Forget. Spring provides `@MessageMapping`, `@ConnectMapping`, and `RSocketRequester` to receive and send messages. These APIs handle how messages travel over the network; they should not decide business operations such as placing an order, recording a measurement, calculating limits, or granting permissions.

If all processing is placed inside an RSocket controller, a single method might read the payload, check the route, retrieve connection info, validate business rules, write to the database, send messages back to the client, and handle transport errors. In that state, switching TCP to WebSocket, adding an HTTP API, running a background job, or writing unit tests all become difficult because business logic is coupled to communication details.

The goal of layering is so the same use case can be invoked from multiple adapters. For example, `RecordMeasurementUseCase` can be called by RSocket, REST, a message broker, or a scheduled task. Each adapter merely converts input data into a command, invokes the use case, and translates the result into the corresponding response format.

## 2. Distinguishing Business Data, Request Data, and Connection Data

The following three categories of data have different lifecycles and must be managed in the appropriate place:

| Category | Examples | Lifecycle and where to manage |
| --- | --- | --- |
| Business state | Orders, balances, device status, ownership permissions | Belongs to domain/application; persisted via repositories or appropriate storage systems |
| Request state | Payload, route, correlation ID, metadata of a command | Serves only a single request; extracted by the adapter and converted into a command |
| Connection state | `RSocketRequester`, TCP/WebSocket connection, keepalive, open/closed state | Belongs to infrastructure/transport; exists for the duration of the connection |

**An RSocket connection is not synonymous with an account, a user, or an application login session.** A single user may open multiple connections; a single connection may also be shared by a gateway representing many users. A connection can drop and be re-established while business data must remain intact.

Do not store critical unique data in a map tied to a connection. If the server restarts or the client reconnects, that data can be lost. A connection registry should only hold temporary references to active peers and the information needed to send messages.

## 3. Dividing Responsibilities

| Component | Responsibility | Should not do |
| --- | --- | --- |
| Domain and application services | Enforce rules, coordinate repositories and business ports | Read `RSocketRequester`, routes, or payloads |
| Inbound RSocket adapter (`@MessageMapping`) | Receive messages, validate/map DTOs, invoke use cases, return results | Contain all business rules |
| Connection adapter (`@ConnectMapping`) | Handle `SETUP`, connection authentication/context, register and track connections | Execute long-running business logic just because a client connected |
| Outbound RSocket adapter | Send messages via requester, translate communication errors appropriately | Let application services construct routes or manage sockets directly |
| Connection registry | Look up connected peers and remove entries when connections close | Serve as storage for long-lived domain state |

Inbound request flow:

```text
RSocket frame
    -> @MessageMapping (inbound adapter)
    -> Command / application use case
    -> Domain + repository / outbound ports
    -> Use case result
    -> RSocket response
```

Flow for proactively sending notifications to clients:

```text
Application use case
    -> ClientNotificationPort
    -> RSocket outbound adapter
    -> Connection registry
    -> Connected peer's RSocketRequester
    -> RSocket frame
```

Both flows can share domain/application services, while only the adapters know about routes, payloads, metadata, and RSocket APIs.

## 4. Placing Business Logic in Application Services

Example: a client sends a measurement and the system needs to save it. The command and use case describe business intent, not the protocol used to deliver the command.

```java
// RecordMeasurementCommand.java
public record RecordMeasurementCommand(String sensorId, double value) {}

// MeasurementReceipt.java
public record MeasurementReceipt(String measurementId, String sensorId) {}

// RecordMeasurementUseCase.java
public interface RecordMeasurementUseCase {
    Mono<MeasurementReceipt> execute(RecordMeasurementCommand command);
}

// RecordMeasurementService.java
@Service
public class RecordMeasurementService implements RecordMeasurementUseCase {

    private final MeasurementRepository repository;

    public RecordMeasurementService(MeasurementRepository repository) {
        this.repository = repository;
    }

    @Override
    public Mono<MeasurementReceipt> execute(RecordMeasurementCommand command) {
        Measurement measurement = new Measurement(command.sensorId(), command.value());
        return repository.save(measurement)
            .map(saved -> new MeasurementReceipt(saved.id(), saved.sensorId()));
    }
}
```

`MeasurementRepository`, `Measurement`, and return types are defined in application/domain according to project conventions. The key point is that the use case does not import `org.springframework.messaging.rsocket.*`, does not accept `RSocketRequester`, does not know whether the client uses TCP or WebSocket, and does not need to know the route is `measurements.record`.

The example still uses Project Reactor's `Mono` to express asynchronous processing. `Mono` is not an RSocket-specific API, though it introduces a dependency on Reactor. If the architecture requires the application layer to be independent of Reactor as well, ports can be designed with synchronous types or another asynchronous abstraction. Weigh conversion overhead and backpressure handling; do not remove `Mono` solely to achieve formalistic layering.

## 5. Using `@MessageMapping` as an Inbound Adapter

The RSocket controller receives wire-protocol DTOs, maps them to commands, and forwards them to the use case:

```java
public record MeasurementRequest(String sensorId, double value) {}

@Controller
public class MeasurementRSocketController {

    private final RecordMeasurementUseCase recordMeasurement;

    public MeasurementRSocketController(RecordMeasurementUseCase recordMeasurement) {
        this.recordMeasurement = recordMeasurement;
    }

    @MessageMapping("measurements.record")
    public Mono<MeasurementReceipt> record(@Payload MeasurementRequest request) {
        RecordMeasurementCommand command =
            new RecordMeasurementCommand(request.sensorId(), request.value());
        return recordMeasurement.execute(command);
    }
}
```

Spring maps the route `measurements.record` to the handler. A single payload and a single result as above correspond to Request-Response. If the use case returns `Flux<T>`, Spring can map it to Request-Stream; the interaction type is inferred from input and output cardinality.

The adapter is the right place to validate DTO structure, convert data types, read necessary metadata, and translate technical errors into appropriate protocol errors. Business checks such as whether the sensor belongs to the customer or whether values fall within valid bounds must be performed in the use case/domain so every adapter applies the same rules.

## 6. Placing Connection Management in a Connection Adapter

`@ConnectMapping` handles the `SETUP` frame when a connection starts and connection-level `METADATA_PUSH` notifications. It is suitable for validating setup info, identifying the peer, registering the connection, or initializing connection-scoped resources. It does not replace `@MessageMapping` for business commands.

Example of a client sending a route and setup data in `SETUP`:

```java
RSocketRequester requester = RSocketRequester.builder()
    .setupRoute("clients.connect")
    .setupData(new ClientHello(clientId))
    .tcp(host, port);
```

This snippet belongs to the client-side connection management component. `tcp()` prepares the requester; per the Spring reference, the shared connection is established when a request is executed. WebSocket can be used if the chosen transport is WebSocket. Application services should not create requesters per business command.

On the responder side, the connection controller can register the requester representing the peer:

```java
@Controller
public class ClientConnectionController {

    private final RSocketConnectionRegistry registry;

    public ClientConnectionController(RSocketConnectionRegistry registry) {
        this.registry = registry;
    }

    @ConnectMapping("clients.connect")
    public Mono<Void> connected(
            RSocketRequester requester, @Payload ClientHello hello) {

        registry.register(hello.clientId(), requester);

        requester.rsocketClient().onClose()
            .doFinally(signal -> registry.remove(hello.clientId(), requester))
            .subscribe();

        return Mono.empty();
    }
}
```

This example targets Spring Framework versions providing `RSocketRequester.rsocketClient()` and RSocket Java providing `onClose()`. Verify APIs against the Spring Framework/RSocket Java versions in use. `onClose()` is the connection's lifecycle signal; `doFinally` runs when the signal completes, errors, or is cancelled. The subscription here exists solely so the adapter observes the connection-close event. Do not use internal `subscribe()` like this to silently run business logic; business flows should be returned for the caller to manage.

`RSocketConnectionRegistry` is an infrastructure component; for example, it can use `ConcurrentHashMap<String, RSocketRequester>` if the convention is one active connection per client. The `remove(clientId, requester)` method should remove conditionally by both key and exact instance. If an old connection closes after a new connection has replaced it, conditional removal will not accidentally remove the new connection.

When a client can open multiple concurrent connections, do not store a single requester per `clientId`. Store by connection ID or a set of connections per client, then define a policy for sending to one peer, all peers, or the most recent peer. When a connection closes, remove only that specific entry.

`@ConnectMapping` is not a general-purpose handler for all business events and not a place to store long-lived state. To track connection closure, use the RSocket/transport-level close signal as shown, or the connector's corresponding lifecycle mechanism. When `@ConnectMapping` needs to initiate a request to the peer right at setup, Spring requires decoupling that work from setup processing; do not hold setup waiting for that request over the requester to complete.

## 7. Hiding `RSocketRequester` Behind an Outbound Port

When business logic needs to send notifications, the application layer defines the intent to notify. Only the adapter knows how to look up the requester and select the route:

```java
public interface ClientNotificationPort {
    Mono<Void> notify(String clientId, ClientNotification notification);
}

@Component
public class RSocketClientNotificationAdapter implements ClientNotificationPort {

    private final RSocketConnectionRegistry registry;

    public RSocketClientNotificationAdapter(RSocketConnectionRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Mono<Void> notify(String clientId, ClientNotification notification) {
        return Mono.defer(() -> registry.find(clientId)
            .map(requester -> requester.route("clients.notification")
                .data(notification)
                .send())
            .orElseGet(() -> Mono.error(new ClientOfflineException(clientId))));
    }
}
```

The use case depends only on `ClientNotificationPort`; it does not know that `clients.notification` is an RSocket route. The adapter can also be swapped with an implementation that enqueues notifications, sends over WebSocket, or stores notifications for later client retrieval.

Note: `send()` returns `Mono<Void>` indicating the send operation has completed on the requester side; it does not by itself prove the receiving handler succeeded in business processing. If the business logic needs confirmation, design an interaction with a response/acknowledgement, such as Request-Response, and model the confirmation result explicitly.

## 8. Security: Identity Is Not Synonymous with Connection ID

Do not trust a `clientId`, `userId`, or `role` merely because that value appears in a `SETUP` payload or metadata. These fields are sender-supplied data and must be authenticated/authorized before being used to register a connection or invoke business logic.

Spring Security supports RSocket authentication at `SETUP` time or per request. Authenticating at `SETUP` fits when a connection is bound to a single user. If a gateway shares a connection across multiple users, per-request authentication is usually more appropriate because each request may represent a different principal. Some scenarios require both layers of authentication.

The connection registry should associate the requester with an authenticated identity and system policies. Use cases must still verify authorization to perform actions on specific resources; an authenticated connection does not imply every request is permitted.

## 9. Testing by Boundary

Layering allows testing each responsibility without spinning up the full RSocket stack for every case:

1. **Unit test use cases:** pass commands directly using fake/mock repositories and outbound ports; verify business rules, results, errors, and side effects. These tests do not need `RSocketRequester`, routes, or server sockets.
2. **Test inbound adapters:** invoke the handler with sample DTOs and a stubbed use case; verify DTO-to-command mapping, input validation, and result/error translation.
3. **Test connection adapters:** verify `SETUP`/`@ConnectMapping`, requester registration, duplicate client ID handling, cleanup when `onClose` terminates, and cases where an old connection closes after a new connection is registered.
4. **RSocket integration tests:** start server/client using local or TCP test transport; verify routes, codecs, metadata, interaction models, security, and real request flows.

Do not use integration tests to re-verify every business calculation branch if unit tests on the use case already cover them. Integration tests focus on risks at transport and configuration boundaries.

## 10. Common Design Mistakes

- **Putting business logic in `@ConnectMapping`:** a client connecting does not necessarily mean a business operation should execute. Let the connection handler manage lifecycle; business commands go through request handlers.
- **Passing `RSocketRequester` into domain services:** couples the domain to Spring Messaging and forces tests to mock transport. Define outbound ports based on business needs.
- **Using connection ID as user ID:** a user can have multiple connections, and connections can change across reconnects. Separate authenticated user identity from connection identity.
- **Storing business state in the connection registry:** the registry can be lost on server restart or connection close. Persist durable state via repositories.
- **Removing from the registry by client ID alone:** an old connection can close after a new connection has already registered. Remove conditionally by exact instance or connection ID.
- **Blocking threads with `block()`:** keep reactive flows and return `Mono`/`Flux` so Spring manages subscriptions. Avoid blocking event-loop threads.
- **Calling `subscribe()` inside use cases:** the caller loses control over lifecycle, errors, and cancellation. Only adapters owning lifecycle should subscribe themselves to an infrastructure signal such as connection close.
- **Treating `send()` as business confirmation:** if you need to know the receiver processed it, use a protocol-level response/acknowledgement and model that result.
- **Trusting `SETUP` metadata as authenticated identity:** verify authentication and authorization before associating a requester with a user or permitting actions.

## 11. Quick Application Rules

- If the question is “is this business operation valid?”, place the rule in domain/application.
- If the question is “which route receives the message and how is the payload decoded?”, place it in the RSocket inbound adapter.
- If the question is “which client just connected and which connection closed?”, place it in the connection adapter/registry.
- If the question is “how do we send notifications to an online client?”, define an outbound port and implement it with an RSocket adapter.
- If data must survive client disconnect or server restart, store it outside the connection registry.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): requester, annotated responders, `@MessageMapping`, `@ConnectMapping`, interaction models, and metadata.
- [Spring Framework Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): requester API, `rsocketClient()`, and `dispose()`.
- [RSocket Java Javadoc — Closeable](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/Closeable.html): the `onClose()` signal of RSocket resources.
- [Spring Security Reference — RSocket](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html): authentication at `SETUP` vs per request.
- [Spring Blog — Getting Started With RSocket: Servers Calling Clients](https://spring.io/blog/2020/05/12/getting-started-with-rsocket-servers-calling-clients/): example managing connected clients and cleaning up the registry on connection close.
