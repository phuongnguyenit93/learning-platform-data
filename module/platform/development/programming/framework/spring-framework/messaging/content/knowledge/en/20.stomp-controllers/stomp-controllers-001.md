# @Controller and Message Mapping with @MessageMapping

## Objectives

In Spring Framework, an application using WebSocket with STOMP can receive messages from a browser and route them to Java methods. **@Controller** marks the handler bean; **@MessageMapping** maps a STOMP destination to the corresponding method.

After this lesson, you will be able to distinguish STOMP handling from HTTP, configure endpoints and a broker, receive payloads/headers/destination variables, broadcast results to a shared topic or specific user, and diagnose routing errors.

## 1. The Role of a Controller in the STOMP Flow

WebSocket provides a long-lived, full-duplex connection. STOMP is a messaging protocol running on top of that connection, with frames such as CONNECT, SEND, SUBSCRIBE, and MESSAGE. Spring converts STOMP frames into Message objects and passes them into the Spring Messaging system.

In a typical configuration, destinations are divided into two groups:

| Destination Group | Example | Handling Component |
| --- | --- | --- |
| Application | /app/chat.send | Controller with @MessageMapping |
| Broker | /topic/chat, /queue/alerts | Message broker and subscriptions |

The application prefix helps Spring distinguish messages that should invoke application logic from messages that the broker can distribute directly. This prefix is configured with setApplicationDestinationPrefixes("/app"). Broker prefixes are configured with enableSimpleBroker("/topic", "/queue") or via a broker relay.

Typical processing flow:

1. The browser opens a WebSocket connection to the /ws endpoint and negotiates STOMP.
2. The client sends SUBSCRIBE to /topic/chat; the broker records the subscription.
3. The client sends SEND to /app/chat.send.
4. Spring recognizes the /app prefix, strips it when looking up the mapping, and invokes the method annotated with @MessageMapping("/chat.send").
5. Spring converts the payload, such as JSON, into a Java object and passes it to the method.
6. The return value is converted into a message sent to the broker channel. The broker distributes the message to clients subscribed to the matching destination.
7. The client receives the MESSAGE frame and reads the payload.

Clients typically send to /app/... to request application processing, and subscribe to /topic/... or /queue/... to receive messages from the broker.

## 2. @Controller and @MessageMapping

**@Controller** is a Spring stereotype that allows component scanning to detect the controller as a bean. In a STOMP context, methods annotated with **@MessageMapping**, **@SubscribeMapping**, or **@MessageExceptionHandler** can handle the corresponding message types.

**@MessageMapping** routes based on the frame destination. The annotation can be placed at the class level or method level:

~~~java
@Controller
@MessageMapping("/orders")
public class OrderController {

    @MessageMapping("/created")
    public void handleCreated(OrderCreated event) {
        // Handle messages sent to /app/orders/created
    }
}
~~~

With the application prefix /app, the destination /app/orders/created matches the class-level mapping /orders combined with the method-level mapping /created. By default, mappings use Ant-style path patterns and support variables such as /rooms/{roomId}/send. Variables can be extracted with **@DestinationVariable**.

**@MessageMapping** is not an HTTP mapping annotation. **@RequestMapping**, **@PostMapping**, and their variants handle HTTP requests; **@MessageMapping** handles message destinations in the Spring Messaging layer. A single @Controller class can contain both HTTP handlers and STOMP handlers if the application is configured accordingly.

## 3. Parameters a Method Can Receive

Spring supports multiple signature styles. Choosing the right parameters ensures the method receives only the data it needs.

| Parameter | Purpose |
| --- | --- |
| @Payload | Extracts the payload; Spring converts from the message format, such as JSON, to a Java type. If no annotation is specified, a parameter not matched to another type is usually treated as the payload. |
| @Header("name") | Extracts a specific header and converts its type if needed. |
| @Headers Map<String, Object> | Extracts all headers as a Map. |
| Message<?> | Accesses both the payload and headers of the message. |
| MessageHeaders, SimpMessageHeaderAccessor, StompHeaderAccessor | Reads headers through a typed API; accessors are suitable when you need the session id, destination, or STOMP information. |
| @DestinationVariable | Extracts a variable parsed from the destination, such as roomId in /rooms/{roomId}/send. |
| Principal | Retrieves the user authenticated during the WebSocket handshake, if authentication is enabled in the application. |

Example of receiving a payload and a header:

~~~java
@MessageMapping("/chat.send")
public void send(
        @Payload ChatMessage message,
        @Header("simpSessionId") String sessionId) {
    // Process the message; sessionId identifies the current WebSocket session
}
~~~

Do not use **@RequestBody**, **@PathVariable**, or **@RequestParam** as substitutes for message handler parameters. Those are mechanisms tied to HTTP requests.

The payload can be validated automatically with Jakarta Validation when the parameter is annotated with **@Valid** or **@Validated**. The application needs a validation provider, such as the spring-boot-starter-validation dependency when using Spring Boot.

## 4. Return Values and Output Destinations

When a @MessageMapping method returns a value, Spring uses a suitable MessageConverter to convert that value into the payload of a message sent to the broker channel. With the /app application prefix configured, an incoming destination /app/greeting is mapped by default on output to /topic/greeting.

You can explicitly specify the destination with **@SendTo**:

~~~java
@MessageMapping("/chat.send")
@SendTo("/topic/chat")
public ChatMessage send(@Payload ChatMessage message) {
    return message;
}
~~~

Subscribers to /topic/chat receive the same message. **@SendTo** can also specify multiple destinations when the same result needs to be broadcast to multiple subscriber groups.

To send a private reply to the user who sent the message, use **@SendToUser**:

~~~java
@MessageMapping("/profile.refresh")
@SendToUser("/queue/profile")
public ProfileView refresh(Principal principal) {
    return profileService.load(principal.getName());
}
~~~

The corresponding client subscribes to /user/queue/profile. The /user prefix is used by Spring to resolve user-specific destinations. By default, if a user has multiple sessions, all matching sessions can receive the message. Set broadcast = false on @SendToUser when you want to send only to the session that originated the message.

When you need to choose a destination dynamically, send messages from a service, or proactively send multiple messages, inject **SimpMessagingTemplate** and call convertAndSend(destination, payload). This is useful when the destination depends on a room id or when a business event originates outside a controller method.

If a method does not need to emit a response, it can return void and send via SimpMessagingTemplate when needed. Methods can also return asynchronous types such as CompletableFuture or CompletionStage.

## 5. Minimal STOMP Configuration

The example below uses Spring Boot to bootstrap the application; the message-handling annotations and APIs belong to Spring Framework. In a Spring Boot project, add the WebSocket dependency and the validation dependency if using @Valid. Let the Spring Boot BOM manage dependency versions.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-websocket</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
~~~

Bootstrap class:

~~~java
package com.example.messaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
~~~

Configuring the endpoint, application prefix, and broker:

~~~java
package com.example.messaging;

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

Meaning:

- **@EnableWebSocketMessageBroker** enables the WebSocket/STOMP infrastructure backed by a message broker.
- **addEndpoint("/ws")** registers the HTTP handshake endpoint where clients open WebSocket connections.
- **setApplicationDestinationPrefixes("/app")** reserves destinations starting with /app for controllers.
- **enableSimpleBroker("/topic", "/queue")** enables the in-memory simple broker to distribute messages to subscribers.

The simple broker is suitable for examples and small systems. It is neither a durable storage broker nor a distributed broker across multiple nodes. When a dedicated broker is needed, you can configure a STOMP broker relay to a system such as RabbitMQ or ActiveMQ.

## 6. Complete Controller Example

DTO using a Java record, suitable for Java 17 and later:

~~~java
package com.example.messaging;

import jakarta.validation.constraints.NotBlank;

public record ChatMessage(
        @NotBlank String sender,
        @NotBlank String text
) {
}
~~~

Controller receiving JSON, validating the payload, and broadcasting the result to a topic:

~~~java
package com.example.messaging;

import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(@Valid @Payload ChatMessage message) {
        return message;
    }
}
~~~

When a client sends JSON to /app/chat.send, Spring converts the payload into a ChatMessage, runs validation, and invokes send. The return value is sent to /topic/chat. Clients subscribed to this topic receive the corresponding JSON payload if a JSON message converter is configured and present on the classpath. Spring Boot typically configures a JSON converter when Jackson is present in the application.

In this learning example, sender is included in the payload for easy observation. In a real application, never trust an identity self-declared by the client. Obtain the username from the authenticated Principal and check room access permissions before broadcasting the message.

## 7. STOMP Client for Sending and Receiving

Install the STOMP client for JavaScript:

~~~bash
npm install @stomp/stompjs
~~~

Example client using WebSocket directly:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  reconnectDelay: 5000
});

client.onConnect = () => {
  client.subscribe("/topic/chat", (frame) => {
    const message = JSON.parse(frame.body);
    console.log(message.sender, message.text);
  });

  client.publish({
    destination: "/app/chat.send",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      sender: "An",
      text: "Hello everyone"
    })
  });
};

client.activate();
~~~

Run the application with **mvn spring-boot:run**, then open the client. Once connected, the client subscribes to /topic/chat and then publishes to /app/chat.send. Every client subscribed to the topic receives a message with the corresponding sender and text.

The two destinations serve different roles: /app/chat.send invokes the Java method; /topic/chat receives data broadcast by the broker. If a client only publishes without subscribing, the server can still process the message, but that client will not receive the broadcast over the topic.

## 8. Destination Variables and Sending to a Specific Room

When a destination contains variables, use **@DestinationVariable** to extract their values. The following example combines a class-level controller mapping with a dynamic destination:

~~~java
package com.example.messaging;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
@MessageMapping("/rooms")
public class RoomController {

    private final SimpMessagingTemplate messagingTemplate;

    public RoomController(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/{roomId}/send")
    public void send(
            @DestinationVariable String roomId,
            @Payload ChatMessage message) {

        messagingTemplate.convertAndSend(
                "/topic/rooms/" + roomId,
                message
        );
    }
}
~~~

A client sending to /app/rooms/engineering/send causes roomId to receive the value engineering. The controller broadcasts the message to /topic/rooms/engineering; clients wanting to receive content for this room must subscribe to that exact destination. Before sending, the application should verify that the sender has permission to participate in the corresponding room.

## 9. Related Annotations

### @SubscribeMapping

**@SubscribeMapping** handles SUBSCRIBE frames instead of SEND frames. Without @SendTo or @SendToUser, the return value is sent directly to the subscribing client by default, without passing through the broker for broadcasting. This is useful for one-time initial data requests, such as recent history when a screen opens.

~~~java
@Controller
public class ChatHistoryController {

    @SubscribeMapping("/chat.history")
    public List<ChatMessage> history() {
        return chatService.latestMessages();
    }
}
~~~

The client subscribes to /app/chat.history to receive the initial response. For recurring updates, subscribe to a broker destination such as /topic/chat.

### @MessageExceptionHandler

**@MessageExceptionHandler** handles exceptions thrown inside message handler methods. It can be placed inside a controller to handle exceptions for that controller, or used with **@ControllerAdvice** for shared handling. The handler can return a payload and use **@SendToUser("/queue/errors")** to send the error to the relevant user. Return a message safe for display to the user; do not expose stack traces or internal details to the client.

## 10. Security and Operations

- **Authentication:** authenticate users during the handshake or integrate the application's authentication mechanism. Use Principal in the controller to obtain the authenticated identity.
- **Message authorization:** restrict who can SEND to each application destination and who can SUBSCRIBE to each topic/queue. @MessageMapping only performs routing; it does not create authorization rules automatically.
- **Never trust the payload:** do not use sender, role, or userId fields sent by the client as proof of identity. Obtain the identity from the security context and verify permissions for the room or resource.
- **Data validation:** use validation on payloads, enforce message size limits, validate input data, and handle errors in a controlled manner.
- **Origin:** allow only trusted frontend origins in the WebSocket configuration. Do not open wildcards arbitrarily when the application uses cookies or credentials.
- **Broker:** the simple broker holds subscriptions in the memory of a single process. When scaling to multiple nodes is required, route through a broker relay and redesign delivery, reconnect, and retry behavior accordingly.
- **Observability:** log the destination, event type, correlation id, and handling outcome; avoid logging tokens, cookies, or sensitive payloads.

## 11. Common Pitfalls

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Controller method is not invoked | Client sent the wrong application prefix or wrong mapping | Compare the sent destination against the /app prefix, class-level mapping, and method-level mapping. |
| Broadcast is not received | Client has not subscribed or subscribed to the wrong destination | Check /topic/... or /queue/... and the destination in @SendTo. |
| WebSocket connection fails | Wrong endpoint, disallowed origin, or handshake rejected | Check the /ws URL, HTTP handshake, and origin/security configuration. |
| Payload is not converted to DTO | Malformed JSON, missing content type, or missing JSON converter | Check the body, the content-type: application/json header, and Jackson on the classpath. |
| Validation rejects the message | Payload is missing a required field or has an invalid format | Check constraints on the DTO and how errors are returned to the client. |
| Client receives data from another room | Topic/room access permissions are not checked | Authenticate the user and check permissions on both SEND and SUBSCRIBE. |
| Controller is not detected | Controller package is outside the component scan area | Place the controller under the @SpringBootApplication class package or configure component scan explicitly. |

## 12. How to Test

Two layers of behavior should be tested:

1. **Unit test:** invoke the controller method directly with valid/invalid payloads to verify business logic and results.
2. **STOMP integration test:** start the application, connect to the WebSocket endpoint, subscribe to a topic, send a SEND frame to the application destination, and verify that a MESSAGE frame with the expected payload is received.

Controller unit tests do not prove that prefixes, handshakes, the broker, or subscriptions are configured properly. Routing issues often appear only in integration tests. When debugging, inspect in order: the connection, the CONNECT, SUBSCRIBE, and SEND frames, the destination after stripping the application prefix, and the returned MESSAGE frame.

## 13. Key Takeaways

- **@Controller** marks the handler bean; **@MessageMapping** connects a STOMP destination to a Java method.
- **/app** is typically used for messages entering the application; **/topic** and **/queue** are typically used for broker subscriptions.
- **@Payload** receives converted data; **@Header** and **@DestinationVariable** extract metadata and destination variables.
- **@SendTo** broadcasts results to a broker destination; **@SendToUser** sends to a specific user.
- **SimpMessagingTemplate** fits dynamic destinations or sending messages from other components.
- Authentication, authorization, validation, and origin control must be designed alongside the message flow.

## References

- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
