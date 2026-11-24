# Publishing Messages from a Service with `convertAndSend`

## Objectives

In a Spring application using STOMP over WebSocket, a service can proactively push data to connected clients without requiring clients to send a request first. The common approach is to inject `SimpMessagingTemplate` and call `convertAndSend(destination, payload)`.

For example: after an order is paid, the service publishes a notification to `/topic/notifications`. Browsers subscribed to this destination will receive the message almost immediately over the WebSocket connection.

This lesson focuses on sending messages from server to client using Spring Messaging/STOMP. This is a realtime push flow; it does not automatically create notification history or guarantee that the client has read the message.

## 1. Components in the sending flow

- **Business service** decides when to publish a message, for example when an order changes status.
- **`SimpMessagingTemplate`** receives the destination and payload object. The `convertAndSend` method uses the configured `MessageConverter` to convert the object into a Spring `Message`.
- **`brokerChannel` and the message broker** receive the outgoing message and find subscriptions matching the destination.
- **`clientOutboundChannel`** delivers the message to the corresponding WebSocket sessions.
- **STOMP client** receives the `MESSAGE` frame and processes the payload.

Key point: the service sends to a destination managed by the broker. Under common configurations, `/topic` is used for broadcast streams and `/queue` is used by convention for one-to-many or point-to-point streams. With the built-in simple broker, these two prefixes are merely naming conventions; the broker does not automatically enforce the queue semantics of a full-featured message broker.

## 2. Minimal STOMP/WebSocket configuration

The `spring-messaging` and `spring-websocket` modules are required. With Spring Boot, you can use the following starters; versions should be managed by the project's Spring Boot dependency management/BOM.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-websocket</artifactId>
    </dependency>
</dependencies>
~~~

Declare a STOMP endpoint for clients to perform the WebSocket handshake and configure the destination prefixes:

~~~java
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
        // Clients sending MESSAGE to /app/... will be routed to @MessageMapping.
        registry.setApplicationDestinationPrefixes("/app");

        // Clients SUBSCRIBE to these destinations; the server can also send here.
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Meaning of the paths:

| Component | Example | Role |
|---|---|---|
| WebSocket handshake endpoint | `/ws` | URL clients use to open the WebSocket connection |
| Application prefix | `/app` | Prefix for messages sent by clients to controllers with `@MessageMapping` |
| Broker prefix | `/topic`, `/queue` | Destinations handled by the broker and distributed to subscribers |

Do not prepend `/app` to the destination of a broadcast call using `convertAndSend`. `/app` is for the client → application direction; for example, the server sends to `/topic/notifications`.

If clients require SockJS fallback, register the endpoint with `registry.addEndpoint("/ws").withSockJS()` and use the corresponding SockJS client. Do not enable SockJS on the server if clients only connect over raw WebSocket under the current configuration.

## 3. Creating a structured payload

Send a structured DTO rather than concatenating a hard-to-extend string. For example, using a Java 17 record:

~~~java
import java.time.Instant;

public record NotificationMessage(
        String type,
        String title,
        String body,
        Instant createdAt
) {
}
~~~

When Jackson is on the classpath and a suitable JSON message converter is configured, the DTO can be serialized into JSON. The client receives the JSON payload and can read the `type`, `title`, `body`, and `createdAt` fields.

Do not send JPA entities directly if the entity has lazy relationships, sensitive data, or internal structures not meant for the client. Create a DTO containing only the fields allowed to be exposed.

## 4. Injecting the template into a service and calling convertAndSend

Spring creates `SimpMessagingTemplate` when the STOMP message broker is enabled. It can be constructor-injected into any Spring bean, such as a `@Service`.

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private static final String DESTINATION = "/topic/notifications";

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(NotificationMessage notification) {
        messagingTemplate.convertAndSend(DESTINATION, notification);
    }
}
~~~

Calling it from a business service:

~~~java
import java.time.Instant;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final NotificationService notificationService;

    public OrderApplicationService(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    public void markOrderPaid(long orderId) {
        // Perform business steps and update order status here.

        NotificationMessage message = new NotificationMessage(
                "ORDER_PAID",
                "Payment successful",
                "Order #" + orderId + " has been paid.",
                Instant.now()
        );

        notificationService.publish(message);
    }
}
~~~

When `markOrderPaid` calls `publish`, Spring converts the DTO into a message and sends it to the broker at destination `/topic/notifications`. Every client subscribed to that exact destination and authorized to receive it will receive the message. Clients connecting after the broadcast do not automatically receive past messages from the simple broker.

You can inject the `SimpMessageSendingOperations` interface instead of the concrete class if you prefer depending on the abstraction. `SimpMessagingTemplate` is the standard implementation in a STOMP configuration.

## 5. Clients must subscribe to the exact destination

JavaScript client example using the `@stomp/stompjs` package and connecting directly to the `/ws` endpoint:

~~~javascript
import { Client } from '@stomp/stompjs';

const client = new Client({
  brokerURL: 'ws://localhost:8080/ws',
  reconnectDelay: 5000,

  onConnect: () => {
    client.subscribe('/topic/notifications', (frame) => {
      const notification = JSON.parse(frame.body);

      console.log(notification.title);
      console.log(notification.body);
    });
  },
});

client.activate();
~~~

Required sequence:

1. The client opens a connection to `/ws`.
2. After STOMP CONNECT succeeds, the client sends SUBSCRIBE to `/topic/notifications`.
3. The service calls `convertAndSend("/topic/notifications", payload)`.
4. The broker finds matching subscriptions for the destination and sends the frame to the client.

In production, use `wss://` when the page is served over HTTPS and configure appropriate origins. The WebSocket endpoint path and subscription destination are two distinct values: `/ws` is the connection endpoint, whereas `/topic/notifications` is the destination for receiving messages.

## 6. Broadcasting vs. sending privately to one user

`convertAndSend(destination, payload)` sends to a shared destination. All sessions subscribed to that destination and authorized to receive it can receive the same payload.

If you need to send privately to a single user, use `convertAndSendToUser`:

~~~java
public void publishToUser(String username, NotificationMessage notification) {
    messagingTemplate.convertAndSendToUser(
            username,
            "/queue/notifications",
            notification
    );
}
~~~

That user's client subscribes to the logical destination:

~~~javascript
client.subscribe('/user/queue/notifications', (frame) => {
  const notification = JSON.parse(frame.body);
  console.log(notification.title);
});
~~~

Spring handles the `/user` prefix and translates the logical destination into a private destination for the user's session. The name passed to `convertAndSendToUser` must match the user name in the WebSocket session's `Principal`. When a user has multiple sessions, by default all matching sessions can be targeted.

Do not take an arbitrary `username` from a client request to determine the recipient. Obtain the identity from the server-authenticated context and check permissions before publishing the notification.

## 7. Commonly used overloads

Common call forms include:

~~~java
// Payload is converted using MessageConverter.
messagingTemplate.convertAndSend("/topic/events", event);

// Send with headers.
messagingTemplate.convertAndSend("/topic/events", event, headers);

// Send with a MessagePostProcessor to adjust the message after conversion.
messagingTemplate.convertAndSend("/topic/events", event, postProcessor);
~~~

- `destination`: a destination that the broker can handle, such as `/topic/events`.
- `payload`: the object to send; can be a String, DTO, or any type supported by the converter.
- `headers`: message metadata. With `SimpMessagingTemplate`, a header map is interpreted by default as native headers when sent over STOMP, unless already prepared via `SimpMessageHeaderAccessor` or containing the corresponding native headers structure.
- `MessagePostProcessor`: callback allowing modification of the message after the conversion step and before sending.

`convertAndSend` takes an object and performs conversion. If you already have a complete Spring `Message<?>`, use `send(destination, message)` to send that message.

## 8. Sending after transaction commit

If a notification depends on data just written inside a transaction, avoid publishing before the transaction commits. If the transaction rolls back, clients might already have received a notification for a change that does not exist.

A common approach is to publish a domain event in the business logic and listen after commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {

    private final NotificationService notificationService;

    public OrderNotificationListener(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPaid(OrderPaidEvent event) {
        NotificationMessage message = new NotificationMessage(
                "ORDER_PAID",
                "Payment successful",
                "Order #" + event.orderId() + " has been paid.",
                event.paidAt()
        );

        notificationService.publish(message);
    }
}
~~~

The example assumes the application has a record `OrderPaidEvent(long orderId, Instant paidAt)` and publishes that event inside a transaction. `AFTER_COMMIT` ensures it only publishes after the transaction commits successfully. This is still realtime sending; if guaranteed redelivery when the broker is temporarily down is required, a separate persistence/outbox and retry mechanism must be designed.

## 9. Securing destinations

WebSocket maintains long-lived connections, so the handshake, STOMP CONNECT, MESSAGE, and SUBSCRIBE all need protection:

- Allow only trusted frontend origins; avoid overly permissive origin configurations in production.
- Enforce SUBSCRIBE permissions per destination. A user should not automatically be allowed to read every topic just because they are logged in.
- Typically, clients may be permitted to SUBSCRIBE to a certain broker destination but should not be permitted to send MESSAGE directly to broker prefixes like `/topic/**` or `/queue/**`. If allowed, clients could spoof system notifications.
- Use `/app/**` for messages entering application handlers, and let the server validate the sender, data, and permissions before publishing to the broker.
- For private notifications, use user destinations and the authenticated `Principal` identity. Do not treat a client-supplied recipient ID as proof of access rights.

Configuring `SimpMessagingTemplate` does not replace Spring Security authorization configuration.

## 10. Delivery limitations and broker choices

`enableSimpleBroker` is suitable for development or small systems. The simple broker keeps subscriptions in the memory of each application instance; it is not a durable storage queue and is not suitable for clustering. When a client is offline, published messages are not automatically stored for later redelivery.

Consider a STOMP broker relay to a full-featured broker when scalability, clustering, or advanced protocol features are needed. A broker relay requires configuring connections and credentials to the external broker.

If business requirements demand that users can always view notifications even after being offline:

1. Persist the notification to a database with the recipient user and creation timestamp.
2. Use `convertAndSend` or `convertAndSendToUser` to notify currently online clients that new data is available.
3. When a client reconnects or opens the notifications page, load the unread list from the API/database.
4. Mark as read through a separate business request.

Completion of `convertAndSend` does not prove that the browser received, displayed, or the user read the message. If processing confirmation is needed, design an application-level acknowledgement.

## 11. Testing the service

You can unit test that the service sends to the right destination and payload using Mockito. This test verifies the call to the template; it does not replace integration tests for the WebSocket handshake, broker, or client subscription.

~~~java
import static org.mockito.Mockito.verify;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.messaging.simp.SimpMessagingTemplate;

@ExtendWith(MockitoExtension.class)
class NotificationServiceTest {

    @Mock
    private SimpMessagingTemplate messagingTemplate;

    @InjectMocks
    private NotificationService notificationService;

    @Test
    void publishesNotificationToTopic() {
        NotificationMessage payload = new NotificationMessage(
                "INFO",
                "Notification",
                "Test content",
                Instant.parse("2026-01-01T00:00:00Z")
        );

        notificationService.publish(payload);

        verify(messagingTemplate).convertAndSend(
                "/topic/notifications",
                payload
        );
    }
}
~~~

To test end-to-end, run the application, open at least one STOMP client, wait for SUBSCRIBE to succeed, and then call the endpoint or business action that triggers the service. Verify that the client receives the expected JSON and destination. You can open two clients to confirm broadcasting to all subscribers.

## 12. Common errors

| Symptom | Possible cause | How to check |
|---|---|---|
| Client does not receive messages | Client has not SUBSCRIBED or subscribed to the wrong destination | Compare exact destination on client and in `convertAndSend` |
| Sent to `/app/...` but no broadcast seen | `/app` is routed to application handlers | Send to a broker prefix like `/topic/...` when broadcasting |
| Client sends to `/topic` and gets rejected | Security rules block MESSAGE to broker prefixes | Check authorization; clients usually only need SUBSCRIBE |
| DTO does not convert to JSON | No suitable converter or unsupported payload type | Check Jackson and message converters configuration |
| Private send does not reach the right user | User value does not match `Principal.getName()` or client subscribed wrongly | Check authenticated identity and `/user/queue/...` subscription |
| Only one instance receives messages | Simple broker keeps subscriptions in each instance's memory | Use broker relay and appropriate shared configuration |
| Notification appears even though transaction rolled back | Message published before transaction commit | Publish via `@TransactionalEventListener(AFTER_COMMIT)` or outbox |

## Key takeaways

- Constructor-inject `SimpMessagingTemplate` into services.
- Use `convertAndSend("/topic/...", payload)` to publish to all matching subscribers.
- Clients must subscribe to the exact destination after STOMP CONNECT succeeds.
- Use `convertAndSendToUser(username, "/queue/...", payload)` for per-user notifications.
- `/ws` is the connection endpoint; `/app` is the inbound prefix; `/topic` and `/queue` are broker destinations in the example.
- The simple broker does not store messages for offline clients and does not guarantee that the user read them.

## References

- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Security — WebSocket Authorization](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
