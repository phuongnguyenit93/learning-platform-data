# @MessageExceptionHandler and @ControllerAdvice in Spring Framework Messaging (STOMP)

## Objectives and Scope

When a client sends a STOMP message to a **@MessageMapping** method, errors can arise from input validation, business rules, or service calls. Rather than letting errors disrupt the processing flow and return cryptic information to the client, Spring Messaging allows converting exceptions into structured payloads.

The two annotations play distinct roles:

- **@MessageExceptionHandler** marks a method that handles exceptions.
- **@ControllerAdvice** extends the scope of those handler methods across multiple controllers.

This guide focuses on Spring Messaging, specifically STOMP over WebSocket. **@MessageExceptionHandler** is not Spring MVC's **@ExceptionHandler**: one handles errors from message handlers, while the other handles errors from HTTP controllers.

This mechanism applies to exceptions thrown while Spring invokes **@MessageMapping** methods. Errors during the WebSocket handshake, STOMP frame decoding, network transport, or broker connectivity can occur outside the controller's scope and must be handled at the corresponding layer.

## 1. @MessageExceptionHandler

### 1.1. How It Works

Place **@MessageExceptionHandler** on a method inside a controller to handle exceptions thrown during message processing. You can declare the exception type directly in the annotation or let Spring infer it from the method parameter's exception type.

Example:

~~~java
@MessageExceptionHandler(InvalidChatMessageException.class)
public ErrorPayload handleInvalidMessage(InvalidChatMessageException ex) {
    return new ErrorPayload("INVALID_MESSAGE", ex.getMessage());
}
~~~

If no exception class is passed to the annotation, the exception type in the method parameter is used to determine which errors to handle:

~~~java
@MessageExceptionHandler
public ErrorPayload handleInvalidMessage(InvalidChatMessageException ex) {
    return new ErrorPayload("INVALID_MESSAGE", ex.getMessage());
}
~~~

A single method can handle multiple exception types by passing a list of classes to the annotation. Choose exception types specific enough so each error receives an appropriate response.

### 1.2. Scope of Handling

By default, a **@MessageExceptionHandler** method applies only within the controller that declares it and that controller's class hierarchy. This is a good fit when an error is specific to one feature group, such as message-sending errors in ChatController.

Exception handler methods support the same parameter and return types as **@MessageMapping** methods. In addition to the exception parameter, you can accept message context such as **Message**, **MessageHeaders**, **@Header**, **@Headers**, **@DestinationVariable**, and **Principal** when needed to construct the response.

The return value is handled like a message handler result: Spring uses an appropriate **MessageConverter** to convert the object into a payload. You can use **@SendTo** or **@SendToUser** to specify the recipient destination. For errors that should go privately to the user who triggered the request, **@SendToUser** is usually preferable.

## 2. @ControllerAdvice for Global Error Handling

When multiple STOMP controllers need to share the same way of turning exceptions into error payloads, you can move **@MessageExceptionHandler** methods into a class annotated with **@ControllerAdvice**.

**@ControllerAdvice** is a Spring component, so the class must fall under component scanning or be registered as a bean. Spring Messaging supports **@MessageExceptionHandler** methods inside this class to handle errors across multiple controllers.

Example:

~~~java
package com.example.chat;

import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GlobalMessagingExceptionAdvice {

    @MessageExceptionHandler(InvalidChatMessageException.class)
    @SendToUser(destinations = "/queue/errors", broadcast = false)
    public ErrorPayload handleInvalidChatMessage(InvalidChatMessageException ex) {
        return new ErrorPayload(
                "INVALID_MESSAGE",
                "Message text must not be blank"
        );
    }
}
~~~

Global advice can be used for shared errors such as invalid data, missing resources, or unauthorized operations. Errors requiring controller-specific responses can still be handled directly inside that controller.

Make ownership of each handling rule explicit. Avoid declaring the same exception mapping in both a controller and an advice without clear intent, as doing so makes it harder to trace which handler gets selected.

## 3. Sending Error Payloads to the Right Client

### 3.1. Distinguishing @SendTo and @SendToUser

- **@SendTo("/topic/...")** sends the result to the specified destination, typically used for data that should be broadcast to subscribers.
- **@SendToUser("/queue/...")** sends the result to the user destination of the user associated with the message being handled.
- With **@SendToUser**, setting **broadcast = false** restricts the reply to the exact WebSocket session that sent the message. Without setting false, other sessions of the same user subscribed to that destination can also receive the reply.

Suppose the user destination prefix is configured as **/user**. The error handler declares destination **/queue/errors**, while the client subscribes to **/user/queue/errors**. Do not include **/user** in the destination value inside **@SendToUser**, because Spring applies that prefix when resolving user destinations.

### 3.2. Minimal STOMP Configuration

The following snippet illustrates the destinations used in the examples. It is configuration for an existing Spring Boot application, not a standalone program.

~~~java
package com.example.chat;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }
}
~~~

With this configuration:

| Purpose | Destination |
|---|---|
| Client sends message for controller handling | /app/chat.send |
| Broadcast valid messages | /topic/chat |
| Client subscribes to receive private errors | /user/queue/errors |
| Destination in @SendToUser | /queue/errors |

## 4. Complete File-by-File Example

The files below use Java 17+ (records) and assume the application already has Spring WebSocket/STOMP and a JSON MessageConverter on the classpath. They illustrate the controller and exception handling parts; endpoint configuration is shown in the previous section.

### 4.1. DTOs and Exception

**ChatMessage.java**

~~~java
package com.example.chat;

public record ChatMessage(String text) {
}
~~~

**ErrorPayload.java**

~~~java
package com.example.chat;

public record ErrorPayload(String code, String message) {
}
~~~

**InvalidChatMessageException.java**

~~~java
package com.example.chat;

public class InvalidChatMessageException extends RuntimeException {

    public InvalidChatMessageException(String message) {
        super(message);
    }
}
~~~

### 4.2. Handling Errors Directly Inside the Controller

**ChatController.java**

~~~java
package com.example.chat;

import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(@Payload ChatMessage message) {
        if (message.text() == null || message.text().isBlank()) {
            throw new InvalidChatMessageException(
                    "Message text must not be blank"
            );
        }

        return message;
    }

    @MessageExceptionHandler(InvalidChatMessageException.class)
    @SendToUser(destinations = "/queue/errors", broadcast = false)
    public ErrorPayload handleInvalidMessage(InvalidChatMessageException ex) {
        return new ErrorPayload("INVALID_MESSAGE", ex.getMessage());
    }
}
~~~

Processing flow:

1. Client sends JSON to **/app/chat.send**.
2. Spring converts the payload into **ChatMessage** and calls **send()**.
3. If the text is blank, the controller throws **InvalidChatMessageException**.
4. Spring finds the matching **@MessageExceptionHandler** method in the controller.
5. The handler method returns **ErrorPayload**; **@SendToUser** routes the payload to the session that sent the message.
6. If the message is valid, **send()** returns **ChatMessage** and **@SendTo** sends the result to **/topic/chat**.

In this example, the exception's message is a message intentionally created by the application and safe to display to users. For technical exceptions or uncontrolled exceptions, never send the raw message, SQL, stack trace, or internal details to the client. Log the details on the server and return an error code along with a safe message.

### 4.3. Moving the Handler to @ControllerAdvice

If multiple controllers need the same handling for **InvalidChatMessageException**, remove the corresponding handler method from **ChatController** and place it in **GlobalMessagingExceptionAdvice** as shown in section 2.

Then, the controller focuses solely on business logic:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(@Payload ChatMessage message) {
        if (message.text() == null || message.text().isBlank()) {
            throw new InvalidChatMessageException(
                    "Message text must not be blank"
            );
        }

        return message;
    }
}
~~~

Global advice can handle exceptions from ChatController and other STOMP controllers within scope. Do not keep two identical handlers in both places unless you specifically need controller-level override behavior.

## 5. Verifying from a STOMP Client

The client must subscribe to the user destination beforehand to receive error payloads. Example with the **@stomp/stompjs** API:

~~~javascript
client.subscribe("/user/queue/errors", (frame) => {
    const error = JSON.parse(frame.body);
    console.log(error.code, error.message);
});

client.publish({
    destination: "/app/chat.send",
    body: JSON.stringify({ text: "" })
});
~~~

Expected result in the callback:

~~~json
{
  "code": "INVALID_MESSAGE",
  "message": "Message text must not be blank"
}
~~~

When sending a valid message, the client receives content on **/topic/chat**. With an error payload, the client receives a normal message on **/user/queue/errors**. Consequently, the client can keep the connection open and continue sending messages after handling the business error.

Points to verify:

- The WebSocket endpoint **/ws** connects successfully and the STOMP session is ready.
- Application prefix, broker prefix, and user destination prefix match the server configuration.
- The client subscribed to **/user/queue/errors** before sending a message that could trigger an error.
- The error payload matches the schema and error codes understood by the client.
- **broadcast = false** sends the error only to the originating session; test with two sessions of the same user if your application supports multiple sessions.
- When using **@ControllerAdvice**, test errors from at least two controllers to confirm global scope.

## 6. How Does @MessageExceptionHandler Differ from a STOMP ERROR Frame?

These are two mechanisms operating at two different layers:

| Mechanism | Purpose | Client-Side Behavior |
|---|---|---|
| @MessageExceptionHandler | Handles exceptions inside message handlers and builds an application error payload | Receives a message at a destination such as /user/queue/errors; the connection can remain open |
| StompSubProtocolErrorHandler | Customizes or suppresses STOMP ERROR frames when handling errors at the STOMP sub-protocol layer | If the server sends a STOMP ERROR frame, the protocol requires the server to close the connection |

Use **@MessageExceptionHandler** for business errors inside **@MessageMapping** methods, such as invalid input or missing entities. Use **StompSubProtocolErrorHandler** when you need to control STOMP ERROR frames, such as errors processing client messages at the sub-protocol layer. This API resides in the **org.springframework.web.socket.messaging** package and can be configured via the STOMP endpoint registry.

Do not use STOMP ERROR frames as the default way to report user input errors: sending that frame triggers closing the connection. For business errors, a structured error payload over a user destination is usually much easier to handle.

## 7. Common Pitfalls and How to Fix Them

| Issue | Common Cause | How to Fix |
|---|---|---|
| Handler is not invoked | Used @ExceptionHandler instead of @MessageExceptionHandler | Use the Spring Messaging annotation |
| Advice has no effect | Class is outside component scan or not registered as a bean | Place the advice in a scanned package or declare it as a bean |
| Client does not receive error payload | Client has not subscribed to the user destination or wrong prefix | Check /user/queue/errors and user prefix configuration |
| Multiple devices receive the same error | broadcast defaults to true across sessions of the same user | Set broadcast = false if replying only to the sending session |
| Client loses connection on error | Server sent a STOMP ERROR frame | Use message-level handlers for business errors; customize sub-protocol ERROR frames only when appropriate |
| Payload exposes internal details | Returned raw technical exception message | Use an error DTO with a code and public message; log details on the server |

## 8. Design Principles

1. **Catch exceptions purposefully.** Use specific exceptions for business errors so they map cleanly to error codes and messages.
2. **Keep payloads stable.** A DTO such as **ErrorPayload(code, message)** helps the frontend handle errors consistently without coupling to exception class names.
3. **Choose the right scope.** Handlers inside a controller are for controller-specific rules; **@ControllerAdvice** is for shared rules.
4. **Route clearly.** Use **@SendTo** for broadcast results and **@SendToUser** for sender-targeted errors.
5. **Never send sensitive information.** Do not return stack traces, queries, tokens, or infrastructure details in payloads.
6. **Separate application errors from protocol errors.** Business errors should be structured messages; STOMP protocol errors belong at the sub-protocol layer.

## 9. References

- [Annotated Controllers – Spring Framework](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [User Destinations – Spring Framework](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [MessageExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/MessageExceptionHandler.html)
- [StompSubProtocolErrorHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolErrorHandler.html)
- [Controller Advice – Spring Framework](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html)
