# The Path of SEND to @MessageMapping

In Spring STOMP over WebSocket, a SEND frame from a client can be turned into a call to a Java method annotated with @MessageMapping. Spring does this through several components: decoding the STOMP frame, creating a Spring Message, putting the message into clientInboundChannel, choosing a handler by destination, converting the payload, resolving the arguments, and invoking the method.

After the method finishes, the return value can be converted into a new message and sent through brokerChannel for the broker to distribute to subscribers. Understanding this flow helps identify whether a fault lies in the protocol, the routing, the payload conversion, the business method, or the response-sending path.

## 1. Overview of the SEND flow

Suppose the server is configured with the application prefix /app and the simple broker handles /topic. The client sends a SEND frame to /app/orders.create.

~~~text
STOMP client
    |
    | SEND destination:/app/orders.create
    v
WebSocket connection
    |
    v
Sub-protocol handler
    | decode the STOMP frame
    | create a Spring Message and add session/header metadata
    v
clientInboundChannel
    |
    | channel interceptors / security checks
    v
SimpAnnotationMethodMessageHandler
    |
    | check the application destination prefix
    | remove /app from the part used for lookup
    | find @MessageMapping("/orders.create")
    v
Method argument resolvers
    | read the payload and headers
    | MessageConverter converts JSON to a DTO
    | validate and bind the arguments
    v
Controller method
    |
    | call a service / handle business logic
    | return a DTO or proactively send a message
    v
Return-value handler
    | MessageConverter converts the result to a payload
    | determine the response destination
    v
brokerChannel
    |
    v
Simple broker or STOMP broker relay
    | find subscribers matching the destination
    v
clientOutboundChannel
    |
    | encode as a STOMP MESSAGE frame
    v
Subscriber's WebSocket connection
~~~

Three channels commonly appear in the diagram:

| Channel | Role |
|---|---|
| clientInboundChannel | Receives the Spring Message created from the client's frame |
| brokerChannel | Passes messages from the application to the broker |
| clientOutboundChannel | Passes messages from the broker or the application to the client |

The simple broker handles subscriptions in Spring's memory. With a broker relay, messages are forwarded to an external broker over a STOMP/TCP connection; the subscription routing and broadcast are handled by the external broker.

## 2. Conditions for SEND to be handled by @MessageMapping

A method is detected to handle messages when the controller and the mapping are declared correctly.

Configuration example:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

Controller:

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders.create")
    @SendTo("/topic/orders")
    public OrderCreated create(CreateOrderCommand command) {
        return new OrderCreated("ORD-42", "CREATED");
    }
}
~~~

The client must connect over WebSocket to /ws, complete the STOMP CONNECT, and only then send SEND:

~~~text
SEND
destination:/app/orders.create
content-type:application/json

{"customerId":"CUS-9","items":[{"sku":"BOOK-1","quantity":2}]}
^@
~~~

Basic conditions:

- The WebSocket/STOMP endpoint is registered and the client connects successfully.
- The STOMP frame has the command SEND and an appropriate destination.
- The application prefix /app is configured.
- The class is annotated with @Controller and the method has @MessageMapping.
- The destination, after removing the application prefix, matches the mapping.
- The payload can be converted to the method's parameter type.
- The client has permission to send messages to that destination if the application has authorization enabled.

@MessageMapping handles STOMP SEND. SUBSCRIBE is routed through the broker's subscription mechanism or @SubscribeMapping; CONNECT, DISCONNECT, and other session management frames also have their own processing flows.

## 3. Step 1: WebSocket and the STOMP frame are decoded

After the HTTP Upgrade handshake, the WebSocket connection carries STOMP frames. Spring's sub-protocol handling component receives the WebSocket message and decodes the STOMP command, headers, and body.

Example SEND frame:

~~~text
SEND
destination:/app/orders.create
content-type:application/json
content-length:68

{"customerId":"CUS-9","items":[{"sku":"BOOK-1","quantity":2}]}
^@
~~~

The STOMP decoder creates a Spring Message representing the frame. The initial payload may still be byte[]; the headers contain information such as:

- The STOMP command.
- The destination.
- The content type.
- The native STOMP headers.
- The session ID and the Principal tied to the connection.
- The message type at the Spring Messaging layer.

Internal headers are usually accessed through SimpMessageHeaderAccessor or StompHeaderAccessor. Applications should use Spring's accessors/constants instead of guessing the names of internal headers.

A SEND frame is not an HTTP POST. It goes through the WebSocket/STOMP message pipeline, not through the Spring MVC DispatcherServlet like an ordinary HTTP request.

## 4. Step 2: The message enters clientInboundChannel

After decoding, Spring sends the message into clientInboundChannel so that the inbound processing components all receive it.

This channel is usually implemented with ExecutorSubscribableChannel. Therefore, processing can be carried out through an executor/thread pool according to the application's configuration.

Components that can take part in the inbound flow include:

- ChannelInterceptor to observe, add metadata to, or reject messages.
- Spring Security messaging to check SEND/SUBSCRIBE permissions.
- SimpAnnotationMethodMessageHandler to find @MessageMapping or @SubscribeMapping methods.
- The message broker handler to process destinations under the broker prefix.

A simple interceptor example:

~~~java
@Component
public class InboundAuditInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        StompHeaderAccessor accessor =
                StompHeaderAccessor.wrap(message);

        if (StompCommand.SEND.equals(accessor.getCommand())) {
            String destination = accessor.getDestination();
            logSend(destination, accessor.getSessionId());
        }

        return message;
    }
}
~~~

The illustrative code must be registered on clientInboundChannel via configureClientInboundChannel. If preSend returns null, the message is blocked and does not continue through the channel.

An interceptor is suitable for general checks such as correlation metadata, auditing, or technical policies. Business processing such as creating an order should live in a controller/service to make it easier to test and manage transactions.

## 5. Step 3: Classify the destination and remove the application prefix

SimpAnnotationMethodMessageHandler handles messages whose destination matches the application destination prefixes.

Example:

~~~java
registry.setApplicationDestinationPrefixes("/app");
~~~

With the input destination:

~~~text
/app/orders.create
~~~

The handler checks the /app prefix. When it matches, the prefix is removed from the destination used to find the method mapping:

~~~text
Destination from the client:  /app/orders.create
Application prefix:           /app
Destination used for lookup:  /orders.create
~~~

Therefore, the method should declare:

~~~java
@MessageMapping("/orders.create")
public OrderCreated create(CreateOrderCommand command) {
    return orderService.create(command);
}
~~~

Do not add /app to the annotation. If you declare @MessageMapping("/app/orders.create"), the mapping usually will not match because the handler has already removed the application prefix before the lookup.

If no application prefix is configured, by default the destinations may be eligible to be considered by the annotated handler. In an application with a broker, you should clearly separate the application prefix from the broker prefix so that routing is easy to predict.

## 6. Step 4: Find the method mapping

@MessageMapping methods are detected when Spring initializes the message-handling infrastructure. SimpAnnotationMethodMessageHandler registers the mappings from @Controller classes and annotated methods.

You can put a common mapping at the class level:

~~~java
@Controller
@MessageMapping("/orders")
public class OrderController {

    @MessageMapping("/create")
    public OrderCreated create(CreateOrderCommand command) {
        return orderService.create(command);
    }

    @MessageMapping("/{orderId}/cancel")
    public OrderCancelled cancel(
            @DestinationVariable String orderId) {

        return orderService.cancel(orderId);
    }
}
~~~

Combined mapping:

| Destination the client sends | Destination after removing /app | Method selected |
|---|---|---|
| /app/orders/create | /orders/create | create |
| /app/orders/ORD-42/cancel | /orders/ORD-42/cancel | cancel |

By default, Spring uses Ant-style path matching. A mapping can use wildcards and template variables. The template value is bound to a parameter annotated with @DestinationVariable.

For example, /orders/{orderId}/cancel takes ORD-42 as orderId. Spring converts the string value to the parameter type if the ConversionService has a suitable converter.

### 6.1. Mapping does not match

If there is no suitable method, the controller method is not called. Common causes:

- The client sends the wrong destination.
- The configured application prefix does not match.
- The annotation already contains the application prefix again.
- The class is missing @Controller.
- The method is missing @MessageMapping.
- The class-level mapping and method-level mapping combine into a different path than expected.
- A customized PathMatcher or separator is inconsistent.

If the destination falls under a broker prefix, the message may be handled directly by the broker. For example, a SEND to /topic/orders usually goes to the broker handler if /topic is a broker prefix; it does not automatically call @MessageMapping("/orders").

Do not configure the same prefix for both the broker and the annotated controller unless you really want both handlers to process the message. When there are multiple handlers on the same channel, the processing order is not a safe routing contract.

## 7. Step 5: Resolve the method arguments

After the mapping is chosen, Spring uses HandlerMethodArgumentResolvers to create the method's arguments.

Commonly used parameter types:

| Parameter | Data received |
|---|---|
| DTO or @Payload DTO | The payload after conversion |
| @Header("key") | A specific header |
| @Headers Map | The mapped headers |
| Message<?> | The Spring Message including payload and headers |
| MessageHeaders | The message's headers |
| SimpMessageHeaderAccessor | Headers through a typed accessor |
| @DestinationVariable | A variable taken from the destination pattern |
| Principal | The authenticated user of the WebSocket session |

A parameter without an annotation is usually treated as the payload if no other special resolver handles it. Use @Payload when you want to state its role explicitly or apply validation.

Example:

~~~java
@MessageMapping("/orders/{orderId}/items")
public void addItem(
        @DestinationVariable String orderId,
        @Payload AddItemCommand command,
        @Header("requestId") String requestId,
        Principal principal) {

    orderService.addItem(
            principal.getName(),
            orderId,
            command,
            requestId
    );
}
~~~

Principal carries the identity that Spring attached from the WebSocket handshake. Do not take a user ID from the payload and treat it as an authenticated identity.

## 8. Step 6: MessageConverter converts the payload

The body of a STOMP SEND is usually received as byte[]. Spring needs to convert the payload to the type the method requires.

Example where the client sends JSON and the method receives CreateOrderCommand:

~~~java
public record CreateOrderCommand(
        String customerId,
        List<OrderItem> items) {
}

public record OrderItem(String sku, int quantity) {
}
~~~

~~~java
@MessageMapping("/orders.create")
public OrderCreated create(@Payload CreateOrderCommand command) {
    return orderService.create(command);
}
~~~

The MessageConverter is chosen based on the payload type, the content-type, and the configured converters. With JSON, applications usually use a Jackson-based converter. If the client omits the content-type or sends a format that differs from the contract, Spring may not be able to choose the desired converter or may produce a different payload type.

Common cases:

- application/json: a JSON body is converted into a DTO if a suitable JSON converter exists.
- text/plain: the body is usually handled as a String.
- application/octet-stream: a binary body can be kept as byte[].
- an unsupported content-type: can raise a MessageConversionException.

Do not assume @Payload parses JSON automatically if the converter has not been configured. Check the message converters configuration in WebSocketMessageBrokerConfigurer and the actual parameter type.

### 8.1. Payload validation

You can combine @Valid with @Payload:

~~~java
@MessageMapping("/orders.create")
public OrderCreated create(
        @Valid @Payload CreateOrderCommand command) {

    return orderService.create(command);
}
~~~

When a Validator is configured, an invalid payload can make argument resolution fail before the business method is called.

Validation should check input data such as the number of items, the SKU, string length, and required fields. Order ownership, operation permissions, and database-dependent rules still need to be checked in the service.

## 9. Step 7: Invoke the controller method

When the mapping and the arguments are ready, Spring calls the method through the InvocableHandlerMethod infrastructure.

Example of a controller calling a service:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders.create")
    @SendTo("/topic/orders")
    public OrderCreated create(
            @Valid @Payload CreateOrderCommand command,
            Principal principal) {

        return orderService.create(principal.getName(), command);
    }
}
~~~

The controller should coordinate the request and call the service. Business rules, repository access, and transactions should live in the service so they can be reused from an HTTP API, a scheduled job, or other messaging flows.

If the method needs a database transaction, you can put @Transactional on the service. A client sending a STOMP SEND does not automatically create a distributed transaction across WebSocket, the broker, and the database.

## 10. Step 8: Handle the return value

When the method returns an object, Spring uses a return-value handler to turn the result into a Spring Message and send it to the appropriate destination.

There are three common ways:

1. Use @SendTo to specify the broadcast destination.
2. Use @SendToUser to send the result to the user who sent the message.
3. Use SimpMessagingTemplate to proactively send to a destination chosen by the application.

### 10.1. @SendTo specifies the destination

~~~java
@MessageMapping("/orders.create")
@SendTo("/topic/orders")
public OrderCreated create(CreateOrderCommand command) {
    return orderService.create(command);
}
~~~

The return value is converted into an outbound payload. The message is sent to brokerChannel and the broker publishes it to the subscribers of /topic/orders.

You can specify multiple destinations in @SendTo if the same result needs to be published to multiple groups of recipients.

### 10.2. The default destination when there is no @SendTo

If a @MessageMapping method returns a value but does not declare @SendTo or @SendToUser, Spring applies a default destination based on the input destination.

For example:

~~~text
Input SEND destination:       /app/greeting
Default response destination: /topic/greeting
~~~

Spring replaces the application prefix with the default broker prefix /topic according to the message flow rules. If the application has a specific response contract, declaring @SendTo explicitly helps avoid depending on the default rule.

### 10.3. @SendToUser sends to the user who sent the request

~~~java
@MessageMapping("/profile.refresh")
@SendToUser("/queue/profile")
public ProfileView refresh(Principal principal) {
    return profileService.load(principal.getName());
}
~~~

@SendToUser routes the result to the user associated with the input message. The destination is the part after the user prefix, for example /queue/profile.

If a user has multiple sessions, the broadcast attribute controls sending to the corresponding sessions. When you need to return only to the session that sent the request, you can configure broadcast=false according to the annotation's semantics.

### 10.4. A void method and SimpMessagingTemplate

If the method returns void, Spring does not create an automatic response from a return value. The application can send messages directly:

~~~java
@Controller
public class OrderController {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderController(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/orders.create")
    public void create(CreateOrderCommand command, Principal principal) {
        OrderCreated result =
                orderService.create(principal.getName(), command);

        messagingTemplate.convertAndSend("/topic/orders", result);
    }
}
~~~

Sending directly is useful when a method needs to publish multiple events, choose the destination based on the business result, or send to a specific group of users. Do not both return a value that @SendTo handles and send the same result through the template if you do not want subscribers to receive duplicates.

### 10.5. Asynchronous return types

Spring supports asynchronous return types such as CompletableFuture, CompletionStage, and ListenableFuture in the annotated messaging flow.

Example:

~~~java
@MessageMapping("/reports.generate")
@SendToUser("/queue/reports")
public CompletableFuture<ReportResult> generate(ReportCommand command) {
    return reportService.generateAsync(command);
}
~~~

The result is sent when the future completes. You need to handle the case where the future completes with an error as well, and make sure background tasks do not hold on to session or request-scoped objects after the method ends.

## 11. Step 9: The message goes through brokerChannel

The return-value handler or SimpMessagingTemplate sends the outbound Spring Message to brokerChannel.

The broker handler receives the message and processes it according to the configuration:

- With the simple broker, the broker finds active subscriptions whose destination matches.
- With a broker relay, Spring forwards the message to the external broker over STOMP/TCP.
- With a user destination, UserDestinationMessageHandler resolves the logical destination by user/session before the message reaches the appropriate broker destination.

If the response destination is not under a broker prefix that the broker manages, the message may not be passed to subscribers as expected.

Simple broker example:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

The client subscribes to /topic/orders before the server publishes the message so that the simple broker has a subscriber waiting to receive. With the simple broker, subscriptions are stored in memory and it is not a message store for offline clients.

## 12. Step 10: The broker publishes MESSAGE to the client

When the broker finds a subscription matching the destination, the message is passed to clientOutboundChannel.

Spring encodes the Spring Message into a STOMP MESSAGE frame, and then sends it over the corresponding WebSocket connection.

Response flow:

~~~text
Controller return value
    |
    v
MessageConverter
    |
    v
Spring outbound Message
    |
    v
brokerChannel
    |
    v
Broker matches subscriptions
    |
    v
clientOutboundChannel
    |
    v
STOMP MESSAGE frame
    |
    v
Subscriber WebSocket
~~~

The client receives a MESSAGE frame with the destination and the payload that the broker forwarded. With JSON, the client parses the body according to the content-type or the contract the application has agreed on.

A controller method completing once does not mean every client has received and processed the response. To confirm business processing on the client side, you need a separate application acknowledgement.

## 13. Channel interceptors and Spring Security in the SEND flow

clientInboundChannel is a suitable place to apply general checks to messages from clients.

A ChannelInterceptor can:

- Check the destination or the type of STOMP command.
- Add a correlation ID or internal metadata.
- Reject invalid messages before they reach the controller.
- Record audit events.
- Attach technical information for tracing.

Spring Security messaging can also control permission to send to /app/** and permission to subscribe to /topic/**. A client knowing a destination does not mean the client is allowed to use that destination.

Example security rules at a conceptual level:

| Operation | Rule to apply |
|---|---|
| SEND /app/orders.create | Only users with permission to create orders |
| SEND /app/orders/{id}/cancel | Must check ownership and order state |
| SUBSCRIBE /topic/orders | Only roles allowed to view the order stream |
| SUBSCRIBE /user/queue/notifications | Only receives the authenticated user's destination |

Do not use a ChannelInterceptor to replace business permission checks in the service. Rules such as whether the user owns the orderId must be checked at the business layer based on trusted data.

## 14. Handling exceptions from @MessageMapping

Errors can occur at many stages:

| Stage | Example error |
|---|---|
| STOMP decoding | A malformed frame or an invalid header |
| Inbound channel/security | The user is not allowed to SEND |
| Mapping | The destination does not match a method |
| Payload conversion | JSON with invalid syntax or a missing converter |
| Argument resolution | A required header is missing, validation fails |
| Controller/service | The order does not exist or the state is invalid |
| Return/send | The broker is unavailable or the destination is invalid |

You can use @MessageExceptionHandler to handle exceptions arising from messaging methods in a controller:

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders.create")
    @SendTo("/topic/orders")
    public OrderCreated create(CreateOrderCommand command) {
        return orderService.create(command);
    }

    @MessageExceptionHandler(OrderRejectedException.class)
    @SendToUser("/queue/errors")
    public ApplicationError handleOrderRejected(
            OrderRejectedException exception) {

        return new ApplicationError(
                "ORDER_REJECTED",
                exception.getMessage()
        );
    }
}
~~~

You can put a shared handler in a @ControllerAdvice if you want it to apply to multiple controllers. The error payload must avoid exposing stack traces, SQL, tokens, or internal information.

Errors that occur before the method is called, such as a malformed STOMP frame or a rejected authorization, may follow the protocol/channel error handling. @MessageExceptionHandler mainly handles exceptions from message-handling methods; it is not a handler for every transport error.

## 15. Processing order and performance

clientInboundChannel usually uses an executor to dispatch messages to handlers. Therefore, multiple messages can be processed concurrently.

If two consecutive SENDs from a client both modify the same entity, you should not assume by default that business processing always completes in exactly the order sent in every executor configuration.

When you need to preserve receive order from the same session, Spring provides the preserveReceiveOrder option on the STOMP endpoint registry in versions that support it. When you need to preserve publish order to clients, you can configure preservePublishOrder on MessageBrokerRegistry.

These options have overhead. Enable them according to business requirements and test under realistic load.

Some operating principles:

- Keep @MessageMapping methods short and call dedicated services.
- Avoid synchronously calling slow external APIs on the inbound executor if the work can be done asynchronously.
- Set limits on payloads and send buffers.
- Monitor inbound latency, method processing time, and outbound latency.
- Check the thread pool sizes of clientInboundChannel/clientOutboundChannel.
- Use a correlation ID to link logs from the input frame to the response event.

## 16. Testing the path from SEND to @MessageMapping

A controller unit test only checks the method logic. To check the whole path, you need an integration test through the WebSocket/STOMP endpoint.

Testing steps:

1. Start the Spring context and the STOMP endpoint.
2. Create a WebSocketStompClient that connects to the endpoint.
3. Establish the STOMP session successfully.
4. SUBSCRIBE to the response destination such as /topic/orders.
5. Send SEND to /app/orders.create with content-type application/json.
6. Wait for the MESSAGE frame at the subscriber using a latch or a future with a timeout.
7. Check the response payload and destination.
8. Send invalid JSON and confirm the error per the configured error handling.
9. Send to a destination with the wrong prefix and confirm the controller is not called.
10. Send a message without sufficient permission and confirm that authorization rejects it.
11. Check that @DestinationVariable and headers are bound correctly.
12. Check that @MessageExceptionHandler returns the correct error payload.
13. Check that a void method sending via SimpMessagingTemplate works if the application uses this approach.
14. Check the broker relay when using an external broker in place of the simple broker.

Conceptual test client example:

~~~java
WebSocketStompClient client =
        new WebSocketStompClient(new StandardWebSocketClient());

StompSession session = client.connectAsync(
        "ws://localhost:8080/ws",
        new StompSessionHandlerAdapter() {}
).get(5, TimeUnit.SECONDS);

BlockingQueue<OrderCreated> replies = new LinkedBlockingQueue<>();

session.subscribe(
        "/topic/orders",
        new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return OrderCreated.class;
            }

            @Override
            public void handleFrame(
                    StompHeaders headers,
                    Object payload) {

                replies.offer((OrderCreated) payload);
            }
        }
);

session.send(
        "/app/orders.create",
        new CreateOrderCommand("CUS-9", List.of(
                new OrderItem("BOOK-1", 2)
        ))
);

OrderCreated result = replies.poll(5, TimeUnit.SECONDS);
assertNotNull(result);
~~~

This is an illustrative example of how to test end to end; a real test needs a suitable message converter, client lifecycle, broker, and teardown configuration. If you use Jackson, the client and server must agree on the converter and the content-type.

Do not use Thread.sleep to guess when the broker has stored the subscription or the response has arrived. Use a receipt if the broker supports it, or a latch, queue, or polling with a timeout, for more stable tests.

## 17. Common errors and how to diagnose them

### 17.1. The controller is not called

Check that the class has @Controller, the method has @MessageMapping, the client sends the SEND command, the destination is correct, and the application prefix is configured as expected.

### 17.2. The destination has an extra /app in the annotation

The handler removes the application prefix before the lookup. The mapping needs the remaining destination part, for example /orders.create.

### 17.3. The client sends to /topic instead of /app

A destination under the broker prefix is passed to the broker handler. If you need to call the controller, the client must SEND to the application prefix.

### 17.4. JSON is not converted into a DTO

Check the content-type, the message converter, the target Java type, and the Jackson configuration. Changing the method's parameter type does not by itself create a JSON converter.

### 17.5. @DestinationVariable receives null or does not match

Check the template variable in @MessageMapping and the actual segment of the destination. The variable name in the annotation and the parameter must correspond.

### 17.6. The response does not reach the subscriber

Check that the client SUBSCRIBEd to the right destination, that the broker prefix is enabled, that @SendTo has the right destination, and that the broker is running.

### 17.7. The default response goes to the wrong destination

If @SendTo is not used, Spring applies the default destination rule based on the input destination. Declare @SendTo explicitly when the contract needs a fixed route.

### 17.8. The subscriber receives duplicates

Check whether the controller both returns an object and calls SimpMessagingTemplate to send the same result. Also check retries at the application layer and the broker.

### 17.9. The message-handling method is slow

Measure the time at the inbound channel and the service. Move long tasks to a worker/asynchronous processing if appropriate; limit the executor and backlog to protect the system.

### 17.10. Errors do not reach the client

Check @MessageExceptionHandler, @ControllerAdvice, broker availability, and STOMP error handling. Do not assume every exception automatically becomes a structured business response.

## 18. Stage-by-stage tracking checklist

When a SEND does not work, trace through the following questions:

1. Has the WebSocket handshake succeeded?
2. Has the STOMP CONNECT received CONNECTED?
3. Has the client sent the correct STOMP command SEND?
4. Does the frame have the correct destination and content-type?
5. Has the message entered clientInboundChannel?
6. Does security/an interceptor block the message?
7. Does the destination match the application prefix?
8. Has the prefix been removed correctly before the mapping?
9. Does SimpAnnotationMethodMessageHandler find the method?
10. Does the payload converter create the right parameter type?
11. Are the headers, Principal, and DestinationVariable bound correctly?
12. Does validation succeed?
13. Does the controller/service complete?
14. Does the return-value handler create an outbound message?
15. Is the response destination under a broker prefix?
16. Does brokerChannel pass the message to the broker?
17. Does the broker have a subscriber matching the destination?
18. Does clientOutboundChannel pass the message to the session?
19. Is the STOMP MESSAGE frame written to the WebSocket?
20. Does the client parse the body and process the response successfully?

Placing logs or metrics keyed by correlation ID at the important points helps find exactly which stage fails. Do not log whole sensitive payloads; record only the necessary metadata such as the destination, command, session ID, authenticated user, and processing time.

## 19. References

- [Spring Framework Reference — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework Reference — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [SimpAnnotationMethodMessageHandler — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/annotation/support/SimpAnnotationMethodMessageHandler.html)
- [MessageMapping — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html)
- [SendToMethodReturnValueHandler — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/annotation/support/SendToMethodReturnValueHandler.html)
- [ChannelInterceptor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [SimpMessagingTemplate — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/SimpMessagingTemplate.html)
- [Spring Framework Reference — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html)
- [Spring Framework Reference — STOMP Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html)

The path of SEND to @MessageMapping consists of STOMP decoding, the inbound channel, destination prefix matching, method mapping, argument resolution, invocation, and return-value handling. When you need to diagnose, check each stage in the right order; this helps distinguish routing errors from payload conversion errors, business errors, and errors in publishing the response to the broker.