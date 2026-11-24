# Class-Level, Method-Level, and Path Pattern Mappings in STOMP Controllers

## Learning Objectives

After this lesson, you will be able to:

- Distinguish a WebSocket endpoint, a STOMP destination, an application destination prefix, and a broker destination prefix.
- Explain how Spring combines a class-level pattern with a method-level pattern to locate a handler.
- Read and write Ant-style path patterns: wildcards, path variables, and regular expressions.
- Extract variables from a destination using `@DestinationVariable` and receive a converted payload.
- Choose the right destination when a client sends commands and when a client subscribes for results.

This lesson focuses on STOMP over WebSocket with controllers annotated with `@Controller` in Spring Framework. By default, Spring uses `AntPathMatcher` with the forward slash `/` as the destination separator.

## 1. Distinguishing Endpoints and Destinations

A STOMP application typically has at least three distinct kinds of paths:

| Component | Example | Role |
|---|---|---|
| WebSocket endpoint | `/ws` | HTTP address used for the handshake and opening the WebSocket connection |
| Application destination prefix | `/app` | Prefix for routing messages sent by clients to application controllers |
| Broker destination prefix | `/topic`, `/queue` | Prefix for routing subscriptions and messages through the message broker |

Illustrative configuration:

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
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Key imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
~~~

With the configuration above:

- Clients open a WebSocket connection to the `/ws` endpoint.
- Clients send STOMP `SEND` frames to a destination starting with `/app` to request application processing.
- Spring strips the `/app` application prefix before matching the remaining destination against controller mappings.
- Clients typically send `SUBSCRIBE` to a destination starting with `/topic` or `/queue`; the broker manages that subscription.

**An endpoint is not a destination.** `/ws` is used to open the connection. `/app/chat/send` and `/topic/chat/events` are destinations inside STOMP frames. Do not put `/ws` into `@MessageMapping`.

## 2. Combining Class-Level and Method-Level Mappings

`@MessageMapping` can be placed at either the class level or the method level:

- A class-level mapping describes the shared path segment for handlers in the controller.
- A method-level mapping describes the path segment specific to a single handler.
- Spring combines both parts to form the complete mapping for the method.

Example:

~~~java
@Controller
@MessageMapping("/chat")
public class ChatController {

    @MessageMapping("/send")
    public void send() {
        // Handle messages sent to /chat/send
    }

    @MessageMapping("/rooms/{roomId}/messages")
    public void sendToRoom() {
        // Handle messages sent to /chat/rooms/{roomId}/messages
    }
}
~~~

The resulting full mappings:

| Class-Level Mapping | Method-Level Mapping | Combined Mapping |
|---|---|---|
| `/chat` | `/send` | `/chat/send` |
| `/chat` | `/rooms/{roomId}/messages` | `/chat/rooms/{roomId}/messages` |

With the `/app` application prefix, clients send to `/app/chat/send` or `/app/chat/rooms/42/messages`. After Spring strips `/app`, the remainder is matched against the combined mapping.

Notes:

1. A class-level mapping is a shared segment and does not automatically turn every method in the class into a handler. A message-handling method still needs an appropriate mapping annotation such as `@MessageMapping` or `@SubscribeMapping`.
2. A class-level mapping can contain variables, such as `/tenants/{tenantId}/chat`. Handlers can receive that variable using `@DestinationVariable`.
3. A class-level `@MessageMapping` can also be combined with a method-level `@SubscribeMapping`.
4. Do not add `/app` to controller mappings when `/app` is already configured via `setApplicationDestinationPrefixes`.

## 3. Complete Example: Tenant and Room Controller

Suppose an application has a destination of the form:

`/app/tenants/{tenantId}/chat/rooms/{roomId}/messages`

We want the tenant segment to be shared across the controller, while each handler declares its own path segment.

~~~java
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
@MessageMapping("/tenants/{tenantId}/chat")
public class ChatController {

    @MessageMapping("/rooms/{roomId}/messages")
    public ChatMessageEvent send(
            @DestinationVariable("tenantId") String tenantId,
            @DestinationVariable("roomId") Long roomId,
            @Payload ChatMessageRequest request) {

        return new ChatMessageEvent(tenantId, roomId, request.text());
    }

    public record ChatMessageRequest(String text) {}

    public record ChatMessageEvent(
            String tenantId,
            Long roomId,
            String text) {}
}
~~~

These are component classes for a Spring application with a STOMP message broker enabled; they are not standalone Java programs to run solely with `javac`. In a Spring Boot application, the commonly used dependency is `spring-boot-starter-websocket`. A JSON payload requires a compatible JSON message converter, such as the Jackson converter.

### Analyzing a Specific Message

The client sends a STOMP frame to:

~~~text
SEND
destination:/app/tenants/acme/chat/rooms/42/messages
content-type:application/json

{"text":"Hello"}
^@
~~~

Spring processes it in order:

1. Receives the frame over the WebSocket connection.
2. Recognizes that the destination begins with the `/app` application prefix.
3. Strips `/app`, leaving `/tenants/acme/chat/rooms/42/messages`.
4. Combines the class-level mapping `/tenants/{tenantId}/chat` with the method-level mapping `/rooms/{roomId}/messages`.
5. Matches the destination and extracts `tenantId = "acme"`, `roomId = "42"`.
6. Converts `roomId` to the parameter type `Long`.
7. Converts the JSON payload into `ChatMessageRequest`, then invokes the handler.

With the broker configuration from section 1, clients can subscribe to receive results at:

~~~text
SUBSCRIBE
destination:/topic/tenants/acme/chat/rooms/42/messages
id:room-42
^@
~~~

If the handler returns an object, Spring converts the object into a payload and sends it through the broker. By the default rule with the `/app` application prefix and `/topic` broker prefix, the corresponding reply destination is `/topic/tenants/acme/chat/rooms/42/messages`. `@SendTo` or `@SendToUser` can be used to specify a different reply destination.

## 4. Ant-Style Path Pattern Syntax

By default, Spring's STOMP mappings use `AntPathMatcher`. Key symbols:

| Syntax | Meaning | Example |
|---|---|---|
| `?` | Matches exactly one character within a path segment | `/files/report?.csv` matches `/files/report1.csv` |
| `*` | Matches zero or more characters within a path segment; does not cross the `/` separator | `/rooms/*/messages` matches `/rooms/42/messages` |
| `**` | Matches zero or more path segments | `/files/**` matches `/files/a/b.txt` |
| `{name}` | Matches one path segment and captures its value into a variable named `name` | `/rooms/{roomId}` matches `/rooms/42` |
| `{name:regex}` | Matches one path segment against a regular expression and captures it into a variable | `/rooms/{roomId:[0-9]+}` matches `/rooms/42` |

Several detailed examples:

~~~java
@MessageMapping("/rooms/*/messages")
public void anyRoomMessage() {
    // Example match: /rooms/42/messages
    // Does not match: /rooms/42/archive/messages
}

@MessageMapping("/files/**")
public void anyFilePath() {
    // Can match: /files/a.txt
    // Can match: /files/images/2026/a.png
}

@MessageMapping("/rooms/{roomId}/messages/{messageId}")
public void oneMessage(
        @DestinationVariable("roomId") Long roomId,
        @DestinationVariable("messageId") Long messageId) {
    // Handle based on the two variables extracted from the destination
}

@MessageMapping("/rooms/{roomId:[0-9]+}")
public void numericRoom(
        @DestinationVariable("roomId") Long roomId) {
    // Only accepts roomId consisting of digits
}
~~~

Distinguishing `*` and `**`:

- `/rooms/*/messages` has only a single segment between `/rooms` and `/messages`.
- `/rooms/**` can also match deeper destinations such as `/rooms/42/messages/100/attachments`.

A `{roomId}` variable captures exactly one segment. For the destination `/rooms/42/messages`, the variable has the string value `42`; Spring converts the value to the parameter type if a matching converter exists. When a regex is used, the regex constrains accepted values right at the matching step.

The default separator is `/`. Do not mechanically apply `PathPatternParser` rules from Spring MVC to STOMP controllers; the STOMP mapping described here uses `AntPathMatcher`.

## 5. Multiple Patterns for a Single Handler

An annotation can declare multiple destination patterns:

~~~java
@Controller
@MessageMapping("/chat")
public class ChatController {

    @MessageMapping({
        "/rooms/{roomId}/messages",
        "/channels/{roomId}/messages"
    })
    public void publish(
            @DestinationVariable("roomId") Long roomId,
            @Payload ChatMessageRequest request) {
        // Both destinations route into this handler
    }

    public record ChatMessageRequest(String text) {}
}
~~~

With the example above, the handler receives both:

- `/app/chat/rooms/42/messages`
- `/app/chat/channels/42/messages`

Declaring multiple patterns is useful when one action has multiple compatible destination names. Keep routes clear and avoid creating multiple handlers with duplicate or ambiguous overlapping mappings. When adding a new route, check the mapping after combining class-level and method-level parts, not just the annotation on the method alone.

## 6. Extracting Variables and Payloads in Handlers

### `@DestinationVariable`

Use this annotation to extract a variable declared in the destination pattern:

~~~java
@MessageMapping("/orders/{orderId}/items/{itemId}")
public void updateItem(
        @DestinationVariable("orderId") Long orderId,
        @DestinationVariable("itemId") Long itemId) {
    // orderId and itemId are converted to Long
}
~~~

You should explicitly specify the variable name in the annotation, especially because Java parameter names can change during compilation or refactoring. The name in the annotation must match the name defined in the pattern. Spring can convert the value to the parameter type; if the value cannot be converted, the message will not be handled successfully.

Use `@DestinationVariable` for variables in STOMP destinations. `@PathVariable` belongs to Spring MVC's HTTP request-handling flow and is not the right annotation for destination variables in this example.

### `@Payload`

The payload is converted by a matching `MessageConverter`. For example, with a JSON payload and the Jackson converter:

~~~java
public record ChatMessageRequest(String text) {}

@MessageMapping("/send")
public void send(@Payload ChatMessageRequest request) {
    // request.text() contains the converted content
}
~~~

In many cases, `@Payload` can be omitted because Spring treats a parameter not mapped to another argument type as the payload by default. Keeping the annotation makes the handler signature easier to read. It can be combined with `@Valid` or `@Validated` to require payload validation when the application has configured validation support.

### Other Arguments

Depending on your needs, a handler can also accept:

- `Message` or `MessageHeaders` to access the message and headers.
- `@Header("simpSessionId")` or the appropriate header name to retrieve a specific header.
- `Principal` to retrieve the authenticated user associated with the WebSocket session.

There is no need to manually parse destination strings inside the method body when variables can be declared with `@DestinationVariable`.

## 7. Using Dots as Separators

An application can adopt a dot-separated destination convention instead of forward slashes. In that case, configure the `PathMatcher` before using this convention:

~~~java
import org.springframework.util.AntPathMatcher;

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPathMatcher(new AntPathMatcher("."));
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

The controller can declare:

~~~java
@Controller
@MessageMapping("red")
public class RedController {

    @MessageMapping("blue.{green}")
    public void handleGreen(
            @DestinationVariable("green") String green) {
        // ...
    }
}
~~~

The client sends to `/app/red.blue.green123`. In this example, `green` receives the value `green123`.

This is a global configuration choice for how destinations are matched. The simple broker also uses the configured `PathMatcher`, so the simple broker's subscription matching rules change as well. If you use an external STOMP broker relay, how the external broker handles destinations depends on that broker; Spring's `PathMatcher` configuration does not automatically change the external broker's internal rules.

Unless you need compatibility with a dot-separated messaging convention, keep the default `/` separator so destinations remain easy to read and close to URL structure.

## 8. Distinguishing Related Annotations

| Annotation | Where Used | Purpose |
|---|---|---|
| `@MessageMapping` | Class or method level | Maps messages by destination |
| `@SubscribeMapping` | Method level | Maps STOMP `SUBSCRIBE` requests; commonly used for an initial response directly to the client |
| `@DestinationVariable` | Method parameter | Extracts a variable from a destination pattern |
| `@Payload` | Method parameter | Receives the payload converted by a message converter |
| `@SendTo` | Class or method level | Specifies the destination to send the result through the broker |
| `@SendToUser` | Class or method level | Sends the result to the corresponding user |

`@MessageMapping` handles messages by destination, typically STOMP `SEND`. `@SubscribeMapping` is for subscription messages. With `@SubscribeMapping`, the return value is sent directly to the requesting client by default instead of being broadcast through the broker; adding `@SendTo` or `@SendToUser` changes how the result is sent.

`@SendTo` and `@SendToUser` can also be placed at the class level as defaults for handlers. An annotation of the same type at the method level overrides the class-level value.

## 9. Common Pitfalls and How to Check

| Symptom | Common Cause | How to Check |
|---|---|---|
| Handler is not invoked | Client sent the wrong application prefix or the mapping does not match | Check the destination of STOMP `SEND`, strip the configured prefix, and compare against the combined mapping |
| Mapping fails to match even though the ending is right | Forgot the class-level mapping or mistakenly included `/app` in the annotation | Combine the class-level and method-level paths, then compare against the destination after stripping `/app` |
| Confused `/ws` with `@MessageMapping` | Used the handshake endpoint as a destination | Inspect the WebSocket connection URL and the destination in the STOMP frame separately |
| `@DestinationVariable` does not receive a value | Variable name mismatch or pattern does not match the segment | Compare the name in `{roomId}` with `@DestinationVariable("roomId")` |
| Converting variable to number fails | Destination contains a value that cannot be converted to the parameter type | Check the sent data and regex constraints on the pattern |
| `*` does not match multi-level destinations | `*` does not cross the `/` separator | Use `**` if the route needs multiple segments |
| Client does not receive the result | Subscribed to the wrong broker destination or handler did not send to the broker | Check the `SUBSCRIBE` destination, broker prefix, return value, and `@SendTo` |
| JSON payload fails to convert | Missing or misconfigured message converter, or inappropriate content type | Check the `content-type` header and JSON converter configuration |
| Two handlers compete for the same destination | Duplicate or overlapping mappings | Review mappings after combining class-level and method-level parts; design unambiguous routes |

## 10. Process for Designing and Verifying Mappings

When adding a new STOMP handler, proceed in order:

1. Choose an application prefix, such as `/app`, and identify the broker prefix clients use to subscribe for results, such as `/topic`.
2. Choose the shared path segment of the controller and place it on the class-level `@MessageMapping` if multiple handlers belong to the same group.
3. Declare the handler-specific path segment on the method-level annotation.
4. Combine both parts to write out the full mapping; verify every segment, wildcard, and variable.
5. Compare the destination sent by the client against the mapping after the application prefix is stripped.
6. Declare `@DestinationVariable` for each variable to be used and pick an appropriate Java type.
7. Confirm that the payload is supported by a converter; add validation when needed.
8. Check the default reply destination or specify one with `@SendTo` / `@SendToUser`.
9. Test representative destinations: valid routes, invalid routes, boundary variables, and multi-segment routes.

## 11. Self-Check Exercises

### Exercise 1

A controller has class-level mapping `/orders` and a method has mapping `/customers/{customerId}/items/{itemId}`. The client sends to `/app/orders/customers/88/items/501`, with application prefix `/app`.

- What is the full mapping of the handler?
- What values do the two variables receive?

**Answer:** The full mapping is `/orders/customers/{customerId}/items/{itemId}`. After stripping `/app`, Spring extracts `customerId = "88"` and `itemId = "501"`; if the parameters are `Long`, Spring converts the values to numbers accordingly.

### Exercise 2

The pattern is `/rooms/*/messages`. Do the destinations `/rooms/42/messages` and `/rooms/42/archive/messages` both match?

**Answer:** No. The first destination matches because there is exactly one segment at the `*` position. The second destination has an extra segment `archive`, so it needs an appropriate pattern such as `/rooms/**` or a more specific pattern.

### Exercise 3

With `@MessageMapping("/rooms/{roomId:[0-9]+}")`, is the destination `/rooms/abc` mapped?

**Answer:** No. The regex `[0-9]+` accepts only one or more digits.

### Exercise 4

When `setApplicationDestinationPrefixes("/app")` is already configured, should you write `@MessageMapping("/app/chat/send")` or `@MessageMapping("/chat/send")`?

**Answer:** Use `@MessageMapping("/chat/send")`. Spring strips `/app` before matching against controller mappings.

## References

- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — Dots as Separators](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/destination-separator.html)
- [Spring Framework API — AntPathMatcher](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/AntPathMatcher.html)
