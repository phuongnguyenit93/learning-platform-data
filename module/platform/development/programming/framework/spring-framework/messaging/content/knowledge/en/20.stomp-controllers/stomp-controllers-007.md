# Return Values, Default Destinations, and Customizing with @SendTo

> Scope: Spring Framework STOMP over WebSocket, Java 17+. Examples assume the application has enabled a WebSocket message broker and configured prefixes as shown below. Code snippets belong to a Spring application, not standalone Java programs that can run via javac/java without Spring dependencies and configuration.

## 1. What Does a @MessageMapping Method Return?

In STOMP, a client sends a SEND frame to an application destination. Spring routes that frame to a method annotated with @MessageMapping. If the method returns a value, Spring treats that value as the payload of a new message, converts the payload with a suitable MessageConverter, and sends the message via brokerChannel. The message broker distributes the message to clients with a matching SUBSCRIBE destination.

Therefore, the return value is neither an HTTP response nor a direct return call sent exclusively to the client that sent SEND. It is the payload of an outbound message. The requesting client also receives the message if it is subscribed to the output destination; other clients subscribed to the same destination can receive it as well.

Typical flow:

1. The client opens a WebSocket connection to the STOMP endpoint, such as /ws.
2. The client sends a STOMP SEND to /app/rooms/42/messages.
3. The /app prefix directs the message to controllers; Spring strips this prefix when matching mappings.
4. @MessageMapping("/rooms/{roomId}/messages") processes the payload.
5. The return value is converted into the payload of a new message and sent to brokerChannel.
6. The broker distributes the message to subscriptions matching the output destination, such as /topic/rooms/42/messages.

## 2. Prefix Configuration Determines Routing

A common configuration separates destinations meant for controllers from destinations meant for the broker:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        // Client SEND to /app/... will be routed to @MessageMapping.
        registry.setApplicationDestinationPrefixes("/app");

        // The broker handles these outbound destinations and subscriptions.
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

The three prefix groups play distinct roles:

| Prefix | Role |
|---|---|
| /app | Inbound prefix for application messages; Spring routes these to @MessageMapping. |
| /topic | Destination typically used for messages broadcast to multiple subscribers. |
| /queue | Destination typically used for queued or private message streams, depending on the broker and application design. |

The /app prefix is not a destination clients typically subscribe to for results. /topic and /queue must match the prefixes the broker is configured to handle. If using a STOMP broker relay instead of the simple broker, the external broker must also be configured to accept the required destinations.

## 3. Default Reply Destination

When a @MessageMapping method returns a value and does not declare @SendTo, Spring builds the default reply destination by taking the application destination after stripping the application prefix, and prepending the default reply prefix /topic.

Example with the configuration above:

| Action | Destination |
|---|---|
| Client SEND | /app/rooms/42/messages |
| Mapping in controller | /rooms/{roomId}/messages |
| Default reply destination | /topic/rooms/42/messages |
| Client SUBSCRIBE to receive result | /topic/rooms/42/messages |

This gives client and server a clear convention: clients send commands under /app, while messages are broadcast on /topic. The reply destination is derived from the actual inbound destination, so path variable values such as 42 are preserved.

Controller example:

~~~java
import java.time.Instant;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    public record ChatRequest(String text) {}

    public record ChatMessage(String roomId, String text, Instant sentAt) {}

    @MessageMapping("/rooms/{roomId}/messages")
    public ChatMessage publish(
            @DestinationVariable String roomId,
            @Payload ChatRequest request) {

        return new ChatMessage(roomId, request.text(), Instant.now());
    }
}
~~~

When a client sends to /app/rooms/42/messages, Spring extracts roomId as "42", converts the payload to ChatRequest, invokes publish, and sends ChatMessage to /topic/rooms/42/messages according to the default rule.

A client can subscribe and publish with STOMP.js as follows:

~~~javascript
client.subscribe("/topic/rooms/42/messages", frame => {
    const message = JSON.parse(frame.body);
    console.log(message);
});

client.publish({
    destination: "/app/rooms/42/messages",
    body: JSON.stringify({ text: "Hello" })
});
~~~

In a real application, establish subscriptions before publishing if the client needs to receive the reply message immediately. The simple broker does not store messages to replay for clients that subscribe later.

## 4. Spring Converts Return Values to Payloads

Spring does not send Java objects directly over WebSocket. A suitable MessageConverter converts the return value into the payload of a Spring Message:

- String is typically converted into a text payload.
- DTOs or records can be converted to JSON when the application includes and configures an appropriate Jackson-based message converter.
- Other data types require a corresponding converter; without a supporting converter, return value handling can fail.

For example, the method returning ChatMessage above: clients receive a STOMP MESSAGE frame with a JSON body matching the record's fields, provided a Jackson converter is configured. There is no need to invoke ObjectMapper manually to serialize the DTO into a JSON string in the controller.

A method can return CompletableFuture or CompletionStage for asynchronous processing. Spring waits for the result to complete and then processes that value like a normal return value. For long-running or I/O-bound tasks, use an appropriately managed executor instead of arbitrarily pushing work onto the common pool by default.

If a method returns void, there is no automatic return payload for Spring to send. When you need to send messages during processing or from a service, use SimpMessagingTemplate.

## 5. Using @SendTo to Choose a Different Destination

@SendTo belongs to the org.springframework.messaging.handler.annotation package. This annotation specifies the outbound destination for a method's return value. The declared destination must be one that the broker can handle.

Example sending the result to a fixed topic:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class AnnouncementController {

    public record AnnouncementRequest(String text) {}
    public record Announcement(String text) {}

    @MessageMapping("/announcements")
    @SendTo("/topic/announcements")
    public Announcement announce(@Payload AnnouncementRequest request) {
        return new Announcement(request.text());
    }
}
~~~

Clients send to /app/announcements and subscribe to /topic/announcements. Even though the inbound destination is /app/announcements, the result goes to /topic/announcements because @SendTo specifies an explicit destination.

### Sending the Same Payload to Multiple Destinations

The value attribute of @SendTo accepts a String array. Spring sends a copy of the message to each destination:

~~~java
@MessageMapping("/announcements")
@SendTo({"/topic/announcements", "/topic/audit"})
public Announcement announce(AnnouncementRequest request) {
    return new Announcement(request.text());
}
~~~

Subscribers to /topic/announcements and subscribers to /topic/audit both receive the payload. This is useful when the same event must be distributed to multiple consumer groups. Consider access permissions and payload contents carefully because all subscribers to each destination can receive the message.

### Declaring a Default Destination at the Class Level

@SendTo can be placed on a class to share a destination across message-handling methods in the class:

~~~java
@Controller
@SendTo("/topic/events")
public class EventController {

    @MessageMapping("/events/created")
    public Event created(EventRequest request) {
        return buildCreatedEvent(request);
    }

    @MessageMapping("/events/important")
    @SendTo("/topic/important-events")
    public Event important(EventRequest request) {
        return buildImportantEvent(request);
    }
}
~~~

This is an abbreviated illustration; Event, EventRequest, and the build... helper methods represent application DTOs and business logic. The created method uses the class-level destination /topic/events. The important method has @SendTo at the method level, so /topic/important-events overrides the class-level value. The same rule applies to @SendToUser when used at the class level.

## 6. Distinguishing Broadcast, User-Targeted Sending, and Proactive Sending

### @SendTo and @SendToUser

@SendTo is typically used to broadcast a message to a shared broker destination. Any client subscribed to that destination and authorized to receive the message can receive the payload.

@SendToUser is used to send to the user associated with the inbound message. Example:

~~~java
@MessageMapping("/orders/{orderId}/confirm")
@SendToUser("/queue/order-confirmations")
public OrderConfirmation confirm(
        @DestinationVariable String orderId,
        OrderRequest request,
        Principal principal) {

    return orderService.confirm(orderId, principal.getName());
}
~~~

The client receives the result by subscribing to the logical destination /user/queue/order-confirmations. Spring resolves the /user destination into a per-user/session destination, preventing users subscribed to the same queue name from mistakenly receiving each other's messages.

If the same user has multiple WebSocket sessions, all of that user's sessions subscribed to the destination can receive the message by default. Set broadcast = false on @SendToUser when you want to send only to the session that sent the message being handled. User destinations usually go hand-in-hand with authentication, though Spring also supports sessions without a Principal; in that case the message is scoped to the current session.

### Using SimpMessagingTemplate When Dynamic Control Is Needed

@SendTo fits when the destination is fixed and the payload is simply the handler's return value. If the destination depends on runtime data, needs to be sent from a service, requires emitting multiple messages at different times, or the handler returns void, inject SimpMessagingTemplate:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class ChatNotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public ChatNotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishToRoom(String roomId, ChatMessage message) {
        String destination = "/topic/rooms/" + roomId + "/messages";
        messagingTemplate.convertAndSend(destination, message);
    }
}
~~~

convertAndSend accepts a destination and an object payload; the template uses message conversion to build a message sent through the broker. To send to a specific user, you can use convertAndSendToUser(username, "/queue/notifications", payload).

@SendTo and @SendToUser are convenient declarative ways to send return values. SimpMessagingTemplate offers more direct control. If you both send with the template and return a value with @SendTo, check that you are not accidentally emitting two messages for the same event.

## 7. Notes on @SubscribeMapping

@SubscribeMapping handles STOMP SUBSCRIBE frames instead of SEND frames. The return value of a @SubscribeMapping method is sent directly back to the subscribing client via clientOutboundChannel by default, without passing through brokerChannel to broadcast to all subscribers.

This is useful when a client has just opened a screen and needs initial one-time data. If @SendTo or @SendToUser is added, Spring switches to sending the result through the broker to the declared destination. Do not confuse the default behavior of @SubscribeMapping with @MessageMapping.

## 8. Common Pitfalls and How to Check

| Symptom | Common Cause | How to Check |
|---|---|---|
| Handler runs but client does not see the message | Client subscribed to the wrong destination | Compare the SEND destination, mapping, and reply destination. |
| Client subscribes to /app/... and receives nothing | /app is typically the inbound prefix for controllers | Subscribe to a broker destination, such as /topic/... or /queue/.... |
| @SendTo fails to publish the message | Destination does not match a broker-handled prefix | Check enableSimpleBroker or broker relay configuration. |
| Client receives a string instead of JSON or payload conversion fails | Incompatible MessageConverter or Jackson not configured | Check configured converters and the message's content type. |
| Only the sending client receives it or no one receives it | Confusion between broadcast and user destinations | Use /topic for shared subscribers; use @SendToUser for a specific user/session. |
| Reply destination remains the default | @SendTo placed on the wrong class or method | Check annotation imports, class/method scope, and which method is actually invoked. |
| Message appears twice | Handler both called SimpMessagingTemplate and returned a payload with @SendTo | Keep only one sending path if only one message is wanted. |
| No message emitted when handler finishes | Handler returns void or produces no return payload | Return a DTO or send proactively with SimpMessagingTemplate. |

When debugging, inspect in order: the client's SEND frame, application prefix, selected mapping, return value, outbound destination, broker prefix, and client subscription. Distinguish routing errors from payload conversion errors: a handler may execute properly yet the client still receives nothing because of the destination or converter.

## 9. Choosing the Right Sending Approach

| Need | Approach |
|---|---|
| Reply with payload to the mapped inbound destination | Return a value from @MessageMapping and use the default destination. |
| Send return value to a fixed topic/queue | Add @SendTo on the method. |
| Send the same payload to multiple destinations | Use @SendTo with an array of destinations. |
| Share a default destination across multiple handlers | Place @SendTo at the class level; method-level can override it. |
| Send a private reply to a user/session | Use @SendToUser and have the client subscribe to /user/.... |
| Choose destination from roomId or runtime data | Use SimpMessagingTemplate.convertAndSend. |
| Send from a service or when the handler returns no payload | Use SimpMessagingTemplate. |
| Return initial data immediately upon client subscription | Consider @SubscribeMapping. |

## 10. Self-Check

1. With application prefix /app and broker prefix /topic, a client SENDs to /app/orders/23/changed. If the handler returns an object and has no @SendTo, which destination must the client subscribe to?
2. If a method has @SendTo({"/topic/a", "/topic/b"}), what payload does each destination receive?
3. When class-level @SendTo is /topic/events but a method has @SendTo("/topic/alerts"), where does the method's result go?
4. When you need to send a result privately to the user who sent the message, should you consider @SendTo or @SendToUser?
5. If the destination must be built from a roomId inside the payload, why is SimpMessagingTemplate usually a better fit than @SendTo?

Answers: (1) /topic/orders/23/changed. (2) The same payload is sent to both destinations. (3) /topic/alerts. (4) @SendToUser. (5) Annotation values are statically declared destinations; the template allows constructing destinations at runtime.

## References

- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): return values, default destinations, @SendTo, @SendToUser, and @SubscribeMapping.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): clientInboundChannel, brokerChannel, and clientOutboundChannel flow; example replacing /app with /topic.
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): /user destinations, @SendToUser, and multi-session behavior.
- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html): sending messages proactively with SimpMessagingTemplate.
