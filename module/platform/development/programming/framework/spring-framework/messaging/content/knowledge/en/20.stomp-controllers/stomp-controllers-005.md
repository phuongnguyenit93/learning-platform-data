# @Header, @Headers, and Principal in STOMP Handler Methods

## Objectives

In a Spring WebSocket application using STOMP, a method annotated with @MessageMapping can receive the payload, message metadata, and sender identity at the same time. Three common ways to obtain this information are:

- **@Header**: extracts a specific header, such as a correlation ID, client version, or priority level.
- **@Headers**: extracts the entire message header map to inspect multiple metadata entries at once.
- **Principal**: retrieves the user identity associated with the current WebSocket session.

Choosing the right parameters keeps handler signatures clear, reduces manual header map lookups, and prevents confusing client-supplied data with server-authenticated identity.

## 1. The Role of These Parameters in the STOMP Flow

WebSocket provides a full-duplex transport channel. STOMP defines frame structure and commands such as CONNECT, SEND, SUBSCRIBE, and MESSAGE. Spring converts an incoming STOMP frame into a Message object containing a payload and MessageHeaders, then passes the message into internal channels for routing.

In a typical configuration:

- Client sends to /app/...: the message is routed to a controller with @MessageMapping.
- Client subscribes to /topic/... or /queue/...: the subscription message is handled by the broker.
- Controller returns a value: Spring converts the value into a payload and sends it through the broker. With the default configuration, the reply destination is typically the incoming destination prefixed with /topic.

For example, the client sends a SEND to /app/rooms/42/messages; the handler is mapped with @MessageMapping("/rooms/{roomId}/messages"). If the handler returns an object, the default destination is typically /topic/rooms/42/messages.

Handler parameters are resolved by Spring according to type and annotation. Payload is the business content; headers are the metadata accompanying the message; Principal is the user identity of the session. They are not three different ways to read the same data.

## 2. Minimal STOMP Configuration to Contextualize Examples

The following configuration snippet illustrates two important prefixes. /app is for messages entering controllers, while /topic and /queue are for the broker:

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
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

This is configuration code inside a Spring application, not a standalone Java program. The application requires Spring WebSocket and Spring Messaging dependencies matching the Spring version in use; place this public class in WebSocketConfig.java.

A STOMP client can send a payload along with custom headers as follows:

~~~javascript
stompClient.publish({
    destination: "/app/rooms/42/messages",
    headers: {
        "traceId": "req-7f31",
        "client-version": "1.4.0"
    },
    body: JSON.stringify({ text: "Hello everyone!" })
});
~~~

traceId and client-version are metadata sent by the client in the SEND frame. They do not automatically become an authenticated identity. The exact header names and sending mechanism depend on the STOMP client library, but on the server side they are handled as native STOMP headers.

## 3. @Header: Extracting a Specific Value

Use the annotation from the **org.springframework.messaging.handler.annotation** package:

~~~java
import org.springframework.messaging.handler.annotation.Header;

@MessageMapping("/orders")
public void receiveOrder(
        @Header("traceId") String traceId,
        @Header(name = "priority", required = false) Integer priority) {

    // Process the order with the accompanying metadata.
}
~~~

Spring looks up the header value by name and converts its type if needed using Spring's conversion mechanism. Thus, a string value can be converted into Integer, Long, or another type if a matching converter exists.

### Important Attributes

| Attribute | Meaning |
|---|---|
| value | Name of the header to extract; alias for name. |
| name | Name of the header to extract; can be used instead of value. |
| required | Defaults to true. If a required header is missing, invoking the handler fails with a missing-header error. |
| defaultValue | Fallback value when the header is absent. When this attribute is specified, required is implicitly set to false. |

Example:

~~~java
@MessageMapping("/orders")
public void receive(
        @Header("traceId") String traceId,
        @Header(name = "retry-count", required = false) Integer retryCount,
        @Header(name = "source", defaultValue = "web") String source) {
    // traceId is required.
    // retryCount may be null.
    // source receives "web" if the client does not send the header.
}
~~~

If using required = false, choose a reference type such as Integer rather than primitive int, because a missing value may be represented as null. If a required header does not exist, Spring does not fill in a dummy value; the error is routed to the application's message error-handling mechanism.

### Standard Headers vs. Native STOMP Headers

Spring Messaging has two layers of metadata to distinguish:

1. **Top-level Spring headers**: metadata used for routing and internal processing, such as simpDestination, simpSessionId, simpMessageType, and simpUser.
2. **Native headers**: original protocol headers or custom headers sent by the client. In a Spring message, they are stored in a nested map under the key nativeHeaders.

In a STOMP handler, @Header("traceId") can resolve a native header named traceId. If you need to explicitly require reading from the native map, use the `nativeHeaders.` + header name syntax:

~~~java
@MessageMapping("/events")
public void receive(
        @Header("traceId") String traceId,
        @Header(name = "nativeHeaders.client-version", required = false)
        String clientVersion) {
    // ...
}
~~~

If the same name exists in both the top-level header map and the native map, the top-level value takes precedence for normal lookup. Use `nativeHeaders.` + header name when you need to specify the native source explicitly.

A native STOMP header can have multiple values. When there is only one value, Spring resolves it to a single value; when there are multiple values, the data may be represented as a list. If the protocol or client allows repeated headers, check the actual type and consider receiving a List or using StompHeaderAccessor to read them cleanly.

### When Should You Use @Header?

Use @Header when the handler only needs one or a few specific values, for example:

- traceId to correlate logs across services.
- client-version to adapt behavior by client version.
- priority or retry-count to control processing.
- simpSessionId to diagnose the connection session.

Never use self-declared client headers as proof of authentication or authorization. Values such as userId, role, or isAdmin sent from a browser can all be tampered with.

## 4. @Headers: Extracting the Entire Header Map

@Headers is used when you need to inspect multiple metadata fields at once. The annotated parameter must accept a type compatible with a Map whose keys are String and values are Object.

~~~java
import java.util.Map;
import org.springframework.messaging.handler.annotation.Headers;

@MessageMapping("/inspect")
public void inspect(@Headers Map<String, Object> headers) {
    Object destination = headers.get("simpDestination");
    Object sessionId = headers.get("simpSessionId");
    Object nativeHeaders = headers.get("nativeHeaders");

    // Set a breakpoint or pass filtered metadata into structured logs.
}
~~~

This map contains the message's headers, including Spring's internal metadata and the nativeHeaders entry holding the map of native STOMP headers. For example, simpDestination indicates the destination normalized by Spring; simpSessionId identifies the WebSocket session; nativeHeaders holds protocol or custom headers.

Do not assume every key exists on every message type. CONNECT, SEND, SUBSCRIBE, and server-generated messages can carry different metadata. Check for null and verify types before casting or using values.

@Headers suits selective logging, tracing, business interceptors needing multiple metadata fields, or diagnostics. If you only need a single key, @Header is usually easier to read. Avoid logging the entire map because it may contain sensitive information such as tokens or credentials.

### Distinguishing @Headers from MessageHeaders

You can declare MessageHeaders directly to access the message's header map without using an annotation:

~~~java
import org.springframework.messaging.MessageHeaders;

@MessageMapping("/inspect")
public void inspect(MessageHeaders headers) {
    Object destination = headers.get("simpDestination");
}
~~~

@Headers explicitly expresses the intent to retrieve all headers via a Map parameter. MessageHeaders is Spring's specialized type for message metadata and also provides key-based lookup operations. In both cases, treat incoming metadata as read-only data; do not attempt to modify the header map of an already created message.

## 5. Principal: Sender Identity

java.security.Principal represents the user attached to the WebSocket session. In STOMP controllers, Spring supports passing Principal directly as a handler parameter:

~~~java
import java.security.Principal;

@MessageMapping("/private/ping")
public String ping(Principal principal) {
    if (principal == null) {
        throw new IllegalStateException("The current session is not authenticated");
    }

    return "Hello " + principal.getName();
}
~~~

principal.getName() returns the identifier name provided by the authentication mechanism. This is the proper source for knowing who is sending the message. Do not take the sender identity from @Header("userId") or from a userId field in the payload and trust it directly.

### Where Is Principal Created and Propagated?

In a standard HTTP authentication flow:

1. The user logs in through an HTTP security mechanism, such as Spring Security.
2. The WebSocket handshake executes within that user's context.
3. Spring automatically associates the HTTP request's Principal with the WebSocket session.
4. STOMP messages on that session carry the corresponding user information.
5. Handlers can accept Principal as a parameter.

Therefore, if the application has already authenticated the user over HTTP and preserves the session/cookie properly, you usually do not need to send the username manually in every SEND frame.

If the application uses tokens at the STOMP layer, you can authenticate the CONNECT frame with a ChannelInterceptor and attach the authenticated Principal to the message. The following example illustrates only the integration point; authenticationService is an authentication component provided by the application. Place this logic inside a class implementing ChannelInterceptor and register that class with the client inbound channel:

~~~java
import java.security.Principal;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(message, StompHeaderAccessor.class);

    if (accessor != null && StompCommand.CONNECT.equals(accessor.getCommand())) {
        String token = accessor.getFirstNativeHeader("Authorization");
        Principal authenticatedUser = authenticationService.authenticate(token);
        accessor.setUser(authenticatedUser);
    }

    return message;
}
~~~

Spring records the user attached on CONNECT and associates that user with subsequent messages in the same session. When using Spring Security for message authorization, configure the authentication interceptor to run before Spring Security's authorization interceptor.

### STOMP login and passcode Do Not Automatically Authenticate WebSocket

STOMP defines login and passcode headers on the CONNECT frame. In Spring STOMP over WebSocket, Spring ignores STOMP-level authentication headers by default and expects identity to be authenticated at the HTTP layer. If you want token authentication at the STOMP layer, you must explicitly process headers in a ChannelInterceptor and call setUser after authentication succeeds.

Never treat a client-sent header as a trustworthy Principal. Principal must come from an authenticated handshake or from server-side token verification.

### Principal Can Be null

If an endpoint allows anonymous connections or authentication is not configured, Principal may be null. Decide explicitly whether the endpoint permits anonymous access:

- Public endpoint: can handle a null Principal as an unauthenticated guest.
- Private endpoint: reject the message when Principal is null.
- Endpoint requiring authorization: check permissions on the server based on the authenticated identity, not based on client-declared headers.

Do not assign a default fallback username and use that name to grant permissions.

## 6. Combining @Header, @Headers, and Principal in One Handler

The following example illustrates a handler that receives a payload, a destination variable, custom headers, all metadata, and the sender. The DTO uses Java records, so Java 16 or later is required; Java 17 is a suitable choice.

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/rooms/{roomId}/messages")
    public ChatReply receive(
            @DestinationVariable("roomId") String roomId,
            @Payload ChatMessage request,
            @Header(name = "traceId", required = false) String traceId,
            @Header(name = "nativeHeaders.client-version", required = false)
            String clientVersion,
            @Headers Map<String, Object> allHeaders,
            Principal principal) {

        if (principal == null) {
            throw new IllegalStateException("Authentication is required to send messages");
        }

        String sender = principal.getName();
        String destination = (String) allHeaders.get("simpDestination");

        return new ChatReply(
                roomId,
                sender,
                request.text(),
                traceId,
                clientVersion,
                destination
        );
    }
}

record ChatMessage(String text) {}

record ChatReply(
        String roomId,
        String sender,
        String text,
        String traceId,
        String clientVersion,
        String inboundDestination
) {}
~~~

When a client sends to /app/rooms/42/messages, roomId receives 42; the JSON payload is converted to ChatMessage; traceId and client-version are extracted from native headers; allHeaders provides access to metadata such as simpDestination; Principal provides the session's user. The return value is converted into a message and sent according to the broker's default destination rules.

This is a controller example for a Spring application with STOMP enabled, a JSON message converter, and authentication configured. The records can be placed in separate files if the project requires each public type in its own file. If the endpoint intentionally allows anonymous access, replace the rejection condition with an explicit guest policy.

## 7. Using StompHeaderAccessor When Typed STOMP Metadata Is Needed

When you need multiple protocol fields or want to avoid string-based key lookups, accept StompHeaderAccessor directly:

~~~java
import java.security.Principal;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

@MessageMapping("/diagnostics")
public void diagnostics(StompHeaderAccessor accessor) {
    String sessionId = accessor.getSessionId();
    String destination = accessor.getDestination();
    String clientVersion = accessor.getFirstNativeHeader("client-version");
    Principal user = accessor.getUser();
    StompCommand command = accessor.getCommand();
}
~~~

The accessor provides typed methods for reading common metadata. Examples:

- getSessionId(): ID of the WebSocket session.
- getDestination(): destination processed by Spring.
- getUser(): Principal attached to the message.
- getCommand(): STOMP command such as SEND or SUBSCRIBE.
- getFirstNativeHeader(name): first value of the native header by name.

Use SimpMessageHeaderAccessor if you only need general Spring Messaging metadata. Use StompHeaderAccessor when you need STOMP-specific details. For a single simple value, @Header remains the most concise option.

## 8. Replying Privately to the Current User

When you want to reply privately to the user sending the message, combine Principal with @SendToUser:

~~~java
import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;

@MessageMapping("/private/ping")
@SendToUser("/queue/reply")
public Pong ping(Principal principal) {
    if (principal == null) {
        throw new IllegalStateException("Authentication required");
    }
    return new Pong("Pong from " + principal.getName());
}

record Pong(String message) {}
~~~

Spring routes the reply to the user destination corresponding to the incoming message's Principal. This is far better than constructing a destination from a userId sent up by the client. The broker configuration must support user destinations according to the application's STOMP setup.

## 9. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | How to Fix |
|---|---|---|
| Handler reports missing header | @Header is required by default, but the client did not send that key | Send the header or set required = false / defaultValue |
| Error assigning null to a numeric type | Using a primitive type with an optional header | Use Integer, Long, or a reference type |
| Header value fails to convert to target type | Invalid string or no matching converter | Check the value sent by the client and the parameter type |
| Custom STOMP header not found in top-level map | Native headers are stored under the nativeHeaders entry | Use @Header with the native name or StompHeaderAccessor |
| Wrong value retrieved when two maps share the same key | Top-level headers take precedence in normal lookups | Specify `nativeHeaders.` + header name explicitly |
| Principal is null | Anonymous connection or handshake had no authenticated user | Check authentication configuration and anonymous policy |
| Principal does not change even when client sends a different userId | Identity is not determined by arbitrary payload/headers | Authenticate during the HTTP handshake or in a ChannelInterceptor |
| Logs contain tokens or sensitive information | Logging the entire @Headers map | Log only necessary keys and mask sensitive values |

Another pitfall is importing the wrong annotation. @Header for Spring Messaging handlers lives in the org.springframework.messaging.handler.annotation package. @RequestHeader belongs to Spring MVC and applies to HTTP request parameters; it does not replace @Header in STOMP handlers.

## 10. Choosing How to Receive Parameters

| Need | Recommended Approach |
|---|---|
| Extract a custom header | @Header("traceId") |
| Header might be missing | @Header(required = false) or defaultValue |
| Inspect all metadata | @Headers Map<String, Object> |
| Read header map with Spring's specialized type | MessageHeaders |
| Get the authenticated sender identity | Principal |
| Read multiple STOMP fields via an accessor | StompHeaderAccessor |
| Send a private reply to the current user | @SendToUser with Principal |

## 11. Implementation Checklist

- [ ] Clearly distinguish payload, headers, and sender identity.
- [ ] Use the correct package org.springframework.messaging.handler.annotation.
- [ ] Mark required only for headers the client is strictly required to send.
- [ ] Use reference types for optional headers.
- [ ] Validate data before casting or converting.
- [ ] Use `nativeHeaders.` + header name or an accessor when reading native headers explicitly.
- [ ] Never use client-sent userId/role to make authorization decisions.
- [ ] Authenticate the HTTP handshake or authenticate CONNECT via a ChannelInterceptor.
- [ ] Handle a null Principal according to the endpoint's anonymous policy.
- [ ] Never log tokens, passcodes, or the entire header map.

## References

- [Spring Framework — Annotated Controllers for STOMP](https://docs.spring.io/spring/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework — Authentication for STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Javadoc — Header](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html)
- [Javadoc — Headers](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Headers.html)
