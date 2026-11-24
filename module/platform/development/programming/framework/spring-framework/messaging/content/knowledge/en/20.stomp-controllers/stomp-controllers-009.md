# @SubscribeMapping and Direct Replies on STOMP Subscription

## 1. The Problem This Annotation Solves

In Spring Framework, WebSocket provides a bidirectional connection, while STOMP defines the frames exchanged over that connection. When a client sends a `SUBSCRIBE` frame, the application may need to immediately return an initial data snapshot to render the UI. Afterwards, the client continues receiving new events via a destination managed by the message broker.

`@SubscribeMapping` targets the first case: mapping a STOMP `SUBSCRIBE` frame to a method inside a `@Controller`. If the method returns a value and does not declare `@SendTo` or `@SendToUser`, Spring sends the result directly back to the subscribing client via `clientOutboundChannel`, without passing the result through `brokerChannel`. Thus, it is a one-time request–reply exchange tied to the subscription operation, well suited for fetching initialization data.

Key point to remember: `@SubscribeMapping` does not create a continuous event stream. The broker does not retain a subscription at this application destination for future broadcasts. If the client needs continuous updates, it must also subscribe to a broker destination such as `/topic/jobs`.

## 2. Distinguishing SUBSCRIBE, SEND, and Annotations

| Actor / Situation | STOMP Frame | Typical Spring Handling | Default Result |
| --- | --- | --- | --- |
| Client wants an initial snapshot | `SUBSCRIBE` | `@SubscribeMapping` | Returned directly to the client that sent the frame |
| Client sends a command or data | `SEND` | `@MessageMapping` | Return value is sent through the broker for distribution to subscribers |
| Client wants continuous events | `SUBSCRIBE` | Message broker, e.g., destination `/topic/**` | Broker stores the subscription and distributes matching MESSAGEs |
| Controller needs to choose output destination | Return value from handler | `@SendTo` | Sent through the broker to the specified destination |
| Controller needs to send to a user-specific destination | Return value from handler | `@SendToUser` | Sent through the broker via user destination |

`@SubscribeMapping` is a method-level annotation and is specific to STOMP over WebSocket. It can be combined with a class-level `@MessageMapping` to share a common path prefix. For example:

- Application prefix is configured as `/app`.
- Controller class has `@MessageMapping("/jobs")`.
- Method has `@SubscribeMapping("/initial-state")`.
- Client sends `SUBSCRIBE` to `/app/jobs/initial-state`.

Spring strips the `/app` application prefix before matching the mapping. The remaining `/jobs/initial-state` is formed by combining the class-level and method-level mappings.

## 3. Minimal STOMP Configuration

The example below uses the WebSocket endpoint `/ws`, the controller prefix `/app`, and a simple broker accepting destinations starting with `/topic` or `/queue`.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

The two destination types serve different roles:

- `/app/**`: application-targeted frames. `SEND` frames can be handled by `@MessageMapping`; `SUBSCRIBE` frames can be handled by `@SubscribeMapping`.
- `/topic/**` and `/queue/**`: broker destinations in this example. The broker manages subscriptions to deliver subsequent messages.

The `/ws` endpoint is the WebSocket handshake address; it is not a STOMP destination. The client opens a WebSocket connection to this endpoint first, and only then sends STOMP frames with their own destinations.

## 4. Example: Returning a Snapshot When a Client Subscribes

Suppose the UI needs to load a job list right when a screen opens. We create a `@SubscribeMapping` method returning the current user's snapshot.

The DTOs use Java 17 records. Place each `public record` in its own file, or declare them as nested types inside the controller.

```java
import java.util.List;

public record JobView(
        String id,
        String name,
        String status
) {}

public record JobSnapshot(
        long version,
        List<JobView> jobs
) {}
```

Controller:

```java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SubscribeMapping;
import org.springframework.stereotype.Controller;

@Controller
@MessageMapping("/jobs")
public class JobController {

    private final JobService jobService;

    public JobController(JobService jobService) {
        this.jobService = jobService;
    }

    @SubscribeMapping("/initial-state")
    public JobSnapshot initialState(Principal principal) {
        return jobService.snapshotFor(principal.getName());
    }
}
```

`JobService` is an application-provided service injected by Spring. The `snapshotFor` method should return a clean DTO containing only the data the client is permitted to view. This is a Spring component example, not a standalone program runnable via `javac` alone: it requires Spring Messaging/WebSocket, STOMP configuration, a `JobService` bean, and the application's message converter configuration.

When a client subscribes to `/app/jobs/initial-state`:

1. The client has connected via STOMP over WebSocket `/ws`.
2. The client sends a `SUBSCRIBE` frame with destination `/app/jobs/initial-state`.
3. Spring receives the frame on `clientInboundChannel`, recognizes the `/app` application prefix, and looks up the handler for `/jobs/initial-state`.
4. Spring invokes `initialState`. The `Principal` argument represents the authenticated user associated with the WebSocket session.
5. The `JobSnapshot` value is converted into a payload via a suitable `MessageConverter`, such as a JSON converter if configured.
6. Spring sends the reply message over `clientOutboundChannel` back to the subscribing client's connection. The result does not pass through the broker to broadcast to other clients.

If the method returns `void` or produces no reply value, the client receives no snapshot payload from that method.

## 5. STOMP Client Receiving the Reply

Example using the `@stomp/stompjs` JavaScript library. The snippet assumes the server exposes the `/ws` endpoint and returns JSON payloads.

```javascript
import { Client } from '@stomp/stompjs';

const client = new Client({
  brokerURL: 'ws://localhost:8080/ws'
});

client.onConnect = () => {
  client.subscribe('/app/jobs/initial-state', frame => {
    const snapshot = JSON.parse(frame.body);
    renderSnapshot(snapshot);
  });
};

client.activate();
```

The subscription callback receives a `MESSAGE` frame; `frame.body` contains the payload sent back by the server. If the application uses SockJS instead of raw WebSocket, configure the client with `webSocketFactory` pointing to the registered SockJS endpoint.

The client-side destination name must match the server's prefix and mapping configuration exactly. In the example above, subscribing to `/jobs/initial-state` without `/app`, or subscribing to `/app/initial-state` without `/jobs`, will not match the declared handler.

## 6. Combining an Initial Snapshot with Continuous Updates

A screen often needs both kinds of data:

- Current snapshot when opening the screen: `@SubscribeMapping` on an application destination.
- Subsequent changes that occur afterwards: a subscription to a broker destination such as `/topic/jobs`.

Declare DTOs for commands and events:

```java
public record JobCommand(String name) {}

public record JobEvent(
        long version,
        String type,
        String jobId
) {}
```

Add the following method to the same `JobController` class above:

```java
@MessageMapping("/publish")
@SendTo("/topic/jobs")
public JobEvent publish(JobCommand command, Principal principal) {
    return jobService.publish(principal.getName(), command);
}
```

The client sends commands using a `SEND` frame to `/app/jobs/publish`; the broker distributes the result to clients subscribed to `/topic/jobs`:

```javascript
client.subscribe('/topic/jobs', frame => {
  const event = JSON.parse(frame.body);
  renderEvent(event);
});

client.publish({
  destination: '/app/jobs/publish',
  body: JSON.stringify({ name: 'Backup' })
});
```

The `publish` method is an addition to the `JobController` class; when combining the code, keep a single class-level `@MessageMapping("/jobs")` declaration and place both methods inside that class. `@SendTo("/topic/jobs")` asks the broker to handle the outbound message. Without `@SendTo` on the `@SubscribeMapping` method, its default behavior remains replying directly to the client.

When clients must avoid gaps between the snapshot and the event stream, synchronization order must be designed deliberately. With a broker that supports STOMP receipts, the client can wait for the receipt confirming that the subscription to `/topic/jobs` has been stored by the broker before requesting the snapshot. Spring's built-in simple broker does not support receipts. In that case, include a version/sequence number in snapshots and events, or use an application-level replay/catch-up mechanism, to detect and fill in missed events. Simply calling `subscribe()` before the snapshot `SUBSCRIBE` does not by itself guarantee synchronization.

## 7. Method Parameters and Return Data

`@SubscribeMapping` supports the same set of arguments as `@MessageMapping`. Commonly useful arguments:

| Argument | Purpose |
| --- | --- |
| `Principal` | Retrieves the authenticated identity of the WebSocket session |
| `@DestinationVariable` | Extracts a variable parsed from the destination |
| `@Header("...")` | Reads a specific header |
| `@Headers` | Receives all headers in a `Map` parameter |
| `Message` or `MessageHeaders` | Accesses the full message and headers |
| `SimpMessageHeaderAccessor` or `StompHeaderAccessor` | Reads headers through a typed accessor API |
| `@Payload` | Reads the payload converted by a MessageConverter |

Example fetching a snapshot for a specific room:

```java
@SubscribeMapping("/rooms/{roomId}/snapshot")
public RoomSnapshot roomSnapshot(
        @DestinationVariable UUID roomId,
        Principal principal) {
    return roomService.snapshotFor(roomId, principal.getName());
}
```

The client subscribes to `/app/rooms/42/snapshot`; Spring converts the `42` segment into the `roomId` value matching the parameter type. Mappings support path patterns and destination variables. If the class has `@MessageMapping("/jobs")`, the class prefix is also prepended to the method path.

A `SUBSCRIBE` frame normally has no body. Therefore, do not design a snapshot endpoint around a JSON payload sent with SUBSCRIBE. Obtain needed inputs from the destination, controlled headers, or `Principal`; if you need to send a command with a body, use a `SEND` frame and `@MessageMapping`.

The return value must be converted by an appropriate `MessageConverter`. A DTO is a good choice because it creates a stable data contract, is easy to test, and avoids accidentally exposing internal entities. If routing through the broker instead of replying directly is needed, you can add `@SendTo` or `@SendToUser`; these two annotations change the default delivery path of the result.

## 8. Distinguishing Application Replies from STOMP Receipts

These are two different kinds of messages:

- The reply from `@SubscribeMapping` is a business payload, typically sent as a `MESSAGE` frame, such as a JSON snapshot.
- A STOMP receipt is a protocol-level acknowledgement that the broker has processed a frame that requested a receipt. It does not contain a business snapshot and does not replace a controller's return result.

If the requirement is “initial data is available”, inspect the `MESSAGE` payload. If the requirement is “the broker has stored the subscription and is ready to deliver broadcasts”, use receipts when supported by the broker or an equivalent acknowledgement mechanism. Do not use receiving a snapshot to infer that a broker subscription on a different destination is ready.

Do not map both controllers and the broker to the same destination prefix unless you intentionally want both to process it. If both process a subscription, each receives the message independently and concurrently; there is no guarantee which runs first. This can create unpredictable behavior when expecting both the controller to return a snapshot and the broker to store the same subscription for broadcasts.

## 9. Security and Reliability

- Authenticate WebSocket connections and use the server-provided `Principal` to identify the user. Never trust a `userId` self-reported by the client in headers or destinations without authorization checks.
- Configure authorization for inbound frames, especially `SUBSCRIBE` permissions on `/app/**` destinations and broker destinations such as `/topic/**`. `@SubscribeMapping`'s direct reply is no reason to skip access control checks.
- Enforce per-resource read permissions. For example, a user may request a room snapshot only if they are a member of that room.
- Return DTOs containing only necessary fields; never return entities or internal data that could leak sensitive information.
- Handle business errors explicitly. You can use `@MessageExceptionHandler` in the controller or `@ControllerAdvice` for broader scope to standardize message errors.
- Every new SUBSCRIBE frame can invoke the handler again, including when a client reconnects or creates a new subscription. Avoid assuming the method runs only once in a user's lifecycle; consider caching, rate limiting, and query cost.
- If snapshots and events can change concurrently, include a version/sequence in payloads so clients can detect stale, duplicate, or missing data.

## 10. Testing the Right Behavior

A unit test calling the Java method directly only tests internal logic; it does not prove that Spring mapped the STOMP frame properly or routed the reply along the right path. Include tests at the messaging or end-to-end layer:

1. Connect a client to the WebSocket endpoint and complete STOMP CONNECT.
2. Send `SUBSCRIBE` to `/app/jobs/initial-state`; verify the handler is invoked and the client receives the expected snapshot.
3. Open a second client session; verify the first session's direct snapshot is not broadcast to the second session.
4. Subscribe to `/topic/jobs`, send `SEND` to `/app/jobs/publish`, and verify the broker delivers the event to matching subscribers.
5. Test unauthenticated access or lacking permission to read the resource.
6. Disconnect and reconnect; verify the client can request a fresh snapshot and handles version/sequence properly.
7. If using receipts, test against the actual broker type running in production; do not assume the simple broker supports receipts.

Spring supports testing handlers by sending messages to `clientInboundChannel` with a real Spring configuration or setting up a minimal `SimpAnnotationMethodMessageHandler`. End-to-end tests can start an embedded WebSocket server and connect a STOMP client. Both approaches complement each other: server-side tests are fast and focused; end-to-end tests verify the protocol, endpoint configuration, mappings, and message delivery paths together.

## 11. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Handler is not invoked | Client used the wrong destination or missed the `/app` prefix / class-level mapping | Check `setApplicationDestinationPrefixes`, class-level `@MessageMapping`, and method-level `@SubscribeMapping` |
| Handler does not run when client sends SEND | `@SubscribeMapping` only accepts SUBSCRIBE | Use `@MessageMapping` for SEND frames |
| Client does not receive snapshot | Handler returns `void`, query threw an error, or MessageConverter failed to convert the DTO | Check handler logs, exception handlers, and converters |
| Other clients also receive initialization data | Result was routed through the broker via `@SendTo`/`@SendToUser`, or destination prefixes overlap | Check output annotations and broker/controller prefixes |
| No events received after snapshot | Client only subscribed to `/app/**`, which does not store broadcast subscriptions | Also subscribe to a broker destination such as `/topic/jobs` |
| Events occasionally lost between snapshot and live updates | Timing mismatch between broker storing the subscription and snapshot retrieval | Use receipts if the broker supports them; otherwise use version/sequence and catch-up |
| Snapshot returns another user's data | Trusted identity from client-sent data or missing resource access check | Use the authenticated Principal and check permissions in the service |

## 12. Process for Choosing the Right Mechanism

- Only need to return a snapshot immediately when a client subscribes: use `@SubscribeMapping`.
- Client sends a command or data for the server to process: use `@MessageMapping`.
- Server needs to broadcast events to multiple clients or subscribers of a destination: use a broker destination and `@SendTo` or `SimpMessagingTemplate`.
- Server needs to send to a specific user: use a user destination, typically combined with `@SendToUser` or `SimpMessagingTemplate.convertAndSendToUser`.
- Need confirmation that the broker has stored a subscription: use STOMP receipts if the broker supports them; this is not `@SubscribeMapping`'s job.

## Official References

- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): mappings, arguments, return values, special `@SubscribeMapping` behavior, receipts, and exception handling.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): roles of `clientInboundChannel`, `clientOutboundChannel`, `brokerChannel`, application prefixes, and broker flow.
- [Spring Framework — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html): access control for STOMP messages.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/testing.html): server-side handler testing and end-to-end testing.
- [SubscribeMapping Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/annotation/SubscribeMapping.html): annotation scope and API contract.

**Key takeaway:** `@SubscribeMapping` handles a SUBSCRIBE frame and by default returns a snapshot directly to the client that sent that frame. The broker only gets involved when you explicitly route the result via `@SendTo`/`@SendToUser`, or when the client subscribes to a separate broker destination to receive subsequent updates.
