# @DestinationVariable and Dot Conventions in Destinations

In Spring Messaging with STOMP, the destination in a STOMP frame is the address Spring uses to route a message to a handler. When a routing pattern contains a variable inside curly braces, such as `{roomId}`, a parameter annotated with `@DestinationVariable` receives the value extracted from that destination. By default, Spring uses the forward slash `/` as the separator. If an application wants to use a dot-separated hierarchical destination convention `.`, it can configure `AntPathMatcher` with a dot as the separator.

These two parts are directly related: `@DestinationVariable` extracts values from the `@MessageMapping` pattern, while `PathMatcher` determines how Spring splits and matches destination segments.

## 1. Destinations and @MessageMapping

WebSocket only provides a bidirectional data transmission channel. STOMP adds message structure and headers, where the `destination` header indicates where a message is being sent. In a typical configuration:

- The client sends a message to an application destination prefixed with `/app`.
- Spring strips the configured application prefix and then matches the remaining destination against `@MessageMapping` patterns.
- The message is handled by the matching controller.
- The return value from the handler can be converted into a message sent to the broker so subscribed clients receive it.

For example, when the application prefix is configured as `/app` and the client sends to:

```text
/app/chat/rooms/42/messages
```

the handler can declare the pattern:

```java
@MessageMapping("/chat/rooms/{roomId}/messages")
```

The `{roomId}` part is a template variable. For the destination above, Spring extracts the string value `42` for the `roomId` variable.

`@MessageMapping` can be placed at the class level and method level. The class-level value establishes a shared prefix; the method-level value specifies the concrete route. Both parts are combined according to the rules of the active path matcher.

The destination belongs to the STOMP message headers. It is independent of the payload. Therefore, `@DestinationVariable` reads routing data from the destination, whereas `@Payload` reads the message body after Spring converts it using a message converter.

## 2. Using @DestinationVariable with the Default / Separator

When no custom path matcher is configured, Spring uses `AntPathMatcher` with the default separator `/`. A controller can receive a room ID from the destination as follows:

```java
package com.example.messaging;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat/rooms/{roomId}/messages")
    public String handleMessage(
            @DestinationVariable("roomId") long roomId,
            @Payload String text) {

        return "room=" + roomId + "; text=" + text;
    }
}
```

With a broker configuration using application prefix `/app` and simple broker prefix `/topic`, a client can send and receive as follows:

```javascript
stompClient.subscribe(
  "/topic/chat/rooms/42/messages",
  frame => console.log(frame.body)
);

stompClient.publish({
  destination: "/app/chat/rooms/42/messages",
  headers: { "content-type": "text/plain" },
  body: "Hello"
});
```

When the message is routed successfully, Spring invokes `handleMessage` with `roomId = 42` and `text = "Hello"`. The return value is converted into a message sent to the default reply destination under the `/topic` broker prefix, which in this example is `/topic/chat/rooms/42/messages`. A client subscribed to that destination receives the body:

```text
room=42; text=Hello
```

The example uses a `String` payload to focus on the routing mechanism. For JSON payloads, the application needs a suitable JSON message converter, typically Jackson, and a corresponding DTO type.

## 3. How to Declare and Convert Destination Variables

### Variable Names Must Match the Pattern

The name in the annotation must match the template variable name in `@MessageMapping`:

```java
@MessageMapping("/orders/{orderId}/events")
public void handle(
        @DestinationVariable("orderId") long id) {
    // Handle the order with the corresponding id.
}
```

Here, the Java parameter name is `id`, while the name in the destination is `orderId`. This is valid because the annotation explicitly specifies the name to extract. You should specify the annotation value explicitly when a route has multiple variables or when the Java parameter name differs from the destination name; this makes the mapping intent clearer and reduces reliance on parameter-name metadata at compile time.

### Spring Converts Parameter Types

The value extracted from the destination is initially a string. Spring converts it to the declared parameter type if a matching converter is available. For example:

```java
@MessageMapping("/accounts/{accountId}/events")
public void handle(
        @DestinationVariable("accountId") Long accountId) {
    // accountId has been converted to Long.
}
```

Use `String` when an identifier can contain letters, hyphens, or other characters. Use a specific type such as `Long` when the identifier is genuinely numeric and the application wants Spring to perform the conversion. If the value cannot be converted to the required type, argument resolution fails and the message enters the application's error-handling flow. Do not assume every string is valid just because it matched the variable position in the destination.

### Multiple Variables in a Single Destination

Each template variable can be mapped to its own parameter:

```java
@MessageMapping("/rooms/{roomId}/users/{userId}/messages")
public void handle(
        @DestinationVariable("roomId") long roomId,
        @DestinationVariable("userId") long userId,
        @Payload String text) {
    // Handle a user's message in a room.
}
```

For the destination `/app/rooms/42/users/7/messages`, Spring extracts `42` for `roomId` and `7` for `userId`, then converts them to `long`.

A template variable is required. `@DestinationVariable` is not a mechanism for declaring optional parameters. If a route has an optional trailing segment, design separate mapping patterns or an explicitly matching pattern rather than expecting a missing variable to automatically become `null`.

### Distinguishing from @PathVariable, @Header, and @Payload

- `@DestinationVariable`: extracts a value from a template variable in the STOMP destination of a message.
- `@PathVariable`: extracts a variable from the path of an HTTP request in Spring MVC/WebFlux.
- `@Header`: extracts a value from a message header, such as a custom header or STOMP header.
- `@Payload`: extracts the message body after conversion by a message converter.

Do not use `@PathVariable` for variables in a `@MessageMapping` destination. The two annotations serve two different routing mechanisms.

## 4. Switching to Dot Conventions in Destinations

Some messaging systems represent hierarchy using dots, such as `chat.rooms.42.messages`, instead of slashes. Spring supports this convention by configuring an `AntPathMatcher` with a dot as the separator in `configureMessageBroker`:

```java
package com.example.messaging;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.util.AntPathMatcher;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setPathMatcher(new AntPathMatcher("."));
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

After enabling the dot separator, the controller can combine class-level and method-level mappings:

```java
package com.example.messaging;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
@MessageMapping("chat")
public class ChatController {

    @MessageMapping("rooms.{roomId}.messages")
    public String handleMessage(
            @DestinationVariable("roomId") long roomId,
            @Payload String text) {

        return "room=" + roomId + "; text=" + text;
    }
}
```

The class-level mapping is `chat`; the method-level mapping is `rooms.{roomId}.messages`. When combined, the route is `chat.rooms.{roomId}.messages`. The client sends a message to:

```text
/app/chat.rooms.42.messages
```

and subscribes to the reply destination:

```text
/topic/chat.rooms.42.messages
```

A STOMP.js client can perform both operations as follows:

```javascript
stompClient.subscribe(
  "/topic/chat.rooms.42.messages",
  frame => console.log(frame.body)
);

stompClient.publish({
  destination: "/app/chat.rooms.42.messages",
  headers: { "content-type": "text/plain" },
  body: "Hello"
});
```

The handler receives `roomId = 42`. With payload `Hello`, the return value is `room=42; text=Hello` and is sent to the default reply destination under the `/topic` prefix.

### Which Parts Still Use Slashes?

The application prefix `/app`, the WebSocket endpoint `/ws`, and broker prefixes such as `/topic` or `/queue` are still configured separately. For example, `/app` is the prefix Spring uses to classify messages entering application handlers; it is not part of the `@MessageMapping` pattern in the example above.

The `/ws` endpoint is also not a message destination. It is the URL clients use to establish the WebSocket/STOMP connection. After connecting, clients send STOMP frames to destinations such as `/app/chat.rooms.42.messages`.

## 5. Impact and Limitations of the Dot Separator

### The Configuration Applies to Matching Logic, Not Just One Annotation

`registry.setPathMatcher(new AntPathMatcher("."))` changes the splitting rules when Spring matches message mapping patterns. It does not automatically rewrite every destination string in the application, nor does it alter the destinations clients send. `@MessageMapping` patterns, destinations sent by clients, and destinations used when subscribing must all follow the same convention.

When using Spring's built-in simple broker, the broker also relies on the configured `PathMatcher` to match subscription destinations. Therefore, changing the separator can affect how the broker matches subscriptions as well. You should test subscribe and publish patterns after changing this configuration, especially when wildcards are in use.

If you use a STOMP broker relay to an external broker, the external broker's destination routing rules are determined by that broker itself. Spring's `PathMatcher` configuration does not change the internal rules of an external broker. Relay prefixes such as `/topic` and `/queue` still need to align with the broker's configuration; consult your broker's documentation before changing the destination convention.

### The Dot Becomes a Structural Separator

When `AntPathMatcher` is configured with separator `.`, the dot carries structural meaning. For example, `chat.rooms.{roomId}.messages` has segments `chat`, `rooms`, the `roomId` value, and `messages`.

This affects variable values. If `roomId` has the value `team.alpha`, the dot inside the value can be interpreted as a boundary between destination segments rather than a character belonging to the identifier. Choose identifiers that do not contain the separator, or design and test a consistent escaping/encoding rule on both client and server. Do not assume Spring automatically encodes or decodes dots inside variables.

### Do Not Mix Two Conventions Arbitrarily

With the default separator, slashes separate segments; dots are ordinary characters inside destination segments. When switching to the dot separator, wildcards and template variables are matched along dot boundaries. Consequently, a pattern written under the slash convention is not automatically equivalent to a dot-separated pattern.

If an application has multiple clients or multiple messaging modules, agree on the convention in the destination contract before changing the configuration. Changing the path matcher can break existing mappings and subscriptions that were previously working.

## 6. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | How to Check or Fix |
|---|---|---|
| Handler is not invoked | The destination sent by the client does not match the `@MessageMapping` pattern | Compare the exact destination header with the pattern after stripping the application prefix. |
| Variable is not extracted | The name in `@DestinationVariable` differs from the name in `{...}` | Use the exact same name, including case; specify `@DestinationVariable("roomId")` explicitly. |
| Client sends slashes while server declares dots | Client and server are using two different separator conventions | Align mapping patterns and destinations on both sides. |
| Variable cannot be converted to a number | Destination contains a non-numeric value while the parameter is `long` or `Long` | Check the sent data; use `String` or an appropriate type if the identifier is non-numeric. |
| Variable value containing a dot gets split | The dot is currently the path matcher's separator | Choose identifiers without dots or build a tested escaping/encoding convention. |
| Subscription does not receive replies with simple broker | Subscription destination does not match the matcher rules or broker prefix | Check the default reply destination, the `/topic` prefix, and the path matcher. |
| Old mappings break after changing separator | `setPathMatcher` affects matching globally | Review mappings and subscriptions using the simple broker; deploy changes in sync with clients. |
| Confused `/ws` with a destination | The WebSocket endpoint and STOMP destination are two different addresses | Use `/ws` to connect; use `/app/...` to send messages after connecting. |

A destination sent by a client can contain user-controlled data. Successfully extracting a value with `@DestinationVariable` does not mean that the data is valid or that the sender is authorized to access the corresponding resource. Validate value ranges in the application and enforce authorization based on the authenticated user, for example via `Principal` and the service layer. Never use `roomId` or `userId` in a destination by itself as proof of authorization.

## 7. Testing Checklist

When adding or modifying a mapping, test over an actual STOMP connection using the same configuration the application deploys:

1. Send a message to a valid destination and verify the right handler is invoked.
2. Verify each `@DestinationVariable` receives the expected value with the expected data type.
3. Send a value that cannot be converted to the parameter type to verify the error-handling flow.
4. Send a destination missing a segment or with segments out of order to verify the mapping does not match accidentally.
5. Check that clients use the right separator: slash when using the default, dot when `AntPathMatcher(".")` is configured.
6. With the simple broker, test both subscribe destinations and reply destinations.
7. With a broker relay, check destination rules according to the external broker and verify broker prefixes remain correct.
8. Test access control with different users; do not test only whether the route matches.

You can use `WebSocketStompClient` in an integration test or a STOMP client such as STOMP.js to send frames and subscribe. Testing a standalone controller in isolation cannot replace verifying that destinations, prefixes, the path matcher, and the broker work together in a real STOMP session.

## References

- [Spring Framework Reference — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): how to declare `@MessageMapping`, handler parameters, and `@DestinationVariable`.
- [Spring Framework Reference — Dots as Separators](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/destination-separator.html): configuring `AntPathMatcher(".")`, dot-separated mapping examples, and impact on the simple broker.
- [Spring Framework Javadoc — DestinationVariable](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/DestinationVariable.html): purpose of the annotation, the `value` attribute, and the requirement that the template variable exists.
