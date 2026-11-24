# @SendToUser and Replying to the Requesting User in Spring STOMP

## Objectives

In a Spring WebSocket application using STOMP, many messages are sent to a group of subscribers via a destination such as **/topic/announcements**. However, some operations only need to return results to the person who sent the request: checking order status, viewing balances, executing transactions, loading private data, or receiving validation errors.

Spring supports this model with **user destinations** and two common sending approaches:

- **@SendToUser**: binds the reply of a STOMP handler method to the user of the current message.
- **SimpMessagingTemplate.convertAndSendToUser(...)**: allows a service or any component to send a message to a user identified on the server side.

The key point is that the client sends requests to an application destination, while Spring resolves the reply destination according to the recipient's identity or session. The client does not need to construct each user's internal queue name manually.

## 1. What is a user destination?

Spring STOMP recognizes the user destination prefix, which defaults to **/user/**. A client can subscribe to a shared logical destination such as:

~~~text
SUBSCRIBE
id:private-replies
destination:/user/queue/replies

^@
~~~

Multiple users can subscribe to the same logical path **/user/queue/replies**. Spring uses **UserDestinationMessageHandler** to translate that path into an actual destination private to the session or user. For example, the internal destination may be transformed into a queue path containing a session identifier segment, preventing users from receiving each other's messages.

On the sending side, the application can target a specific user by sending to a logical destination bound to the user name, or use **@SendToUser** to target the user of the current message. Spring maps this logical destination to one or more actual destinations corresponding to active sessions.

Distinguish the following:

- **Destination the client subscribes to**: usually **/user/queue/replies**.
- **Destination sent via @SendToUser**: usually **/queue/replies**; the annotation applies the user destination prefix automatically.
- **Destination sent via convertAndSendToUser**: pass the username separately and the trailing destination such as **/queue/replies**; the template handles the user prefix.

Do not add the username to the client-side subscribe path. Do not manually construct internal destinations by session ID. Resolution is Spring's responsibility.

## 2. Request-response flow for the sender

Suppose the client has connected to STOMP with an authenticated identity, subscribed to **/user/queue/order-replies**, and then sent an order check request to **/app/orders.check**.

~~~text
Client
  | SUBSCRIBE /user/queue/order-replies
  | SEND      /app/orders.check
  v
Spring clientInboundChannel
  |
  v
@MessageMapping("/orders.check")
  |
  v
Process business logic and create OrderReply
  |
  v
@SendToUser("/queue/order-replies")
  |
  v
UserDestinationMessageHandler
  |
  v
Broker -> actual user/session destination
  |
  v
clientOutboundChannel -> WebSocket -> Client receives reply
~~~

Detailed steps:

1. The client opens a STOMP connection. Upon successful authentication, Spring attaches the corresponding **Principal** to the connection.
2. The client subscribes to receive replies at **/user/queue/order-replies**.
3. The client sends a SEND frame to **/app/orders.check**.
4. Spring places the message onto **clientInboundChannel**. The application destination prefix **/app** routes the message to the controller; the remainder **/orders.check** is matched against **@MessageMapping**.
5. The controller executes business logic and returns a reply object.
6. **@SendToUser("/queue/order-replies")** tells Spring to send the return value to the user associated with the current message.
7. Spring resolves the user destination into actual destinations for matching sessions. The broker forwards the message to subscribers and Spring sends a MESSAGE frame back to the WebSocket client.

Thus, the controller does not have to find the client's physical queue itself. It simply returns data and specifies the logical destination for the user.

## 3. Example using @SendToUser

The following example illustrates an order check request. The client sends an order ID; the server determines identity from **Principal**, calls the service, and returns the result privately to the requesting user.

~~~java
public record OrderCheckRequest(String orderId) {}

public record OrderCheckReply(
        String orderId,
        String status,
        String checkedBy) {}

@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders.check")
    @SendToUser("/queue/order-replies")
    public OrderCheckReply check(
            @Payload OrderCheckRequest request,
            Principal principal) {

        String username = principal.getName();
        return orderService.check(request.orderId(), username);
    }
}
~~~

This is an illustrative snippet of a controller and DTOs; it assumes the application has already declared an **OrderService** bean, configured STOMP endpoints, message converters, and authentication. Imports and the service's business implementation are omitted.

With the application prefix **/app**, a client sending to **/app/orders.check** invokes the **check** method. The return value is sent to the user destination based on the message's Principal. If the client subscribes to **/user/queue/order-replies**, that client receives the reply.

A client must not be allowed to choose the username by sending a **checkedBy** field in the payload itself. The server obtains the username from the authenticated **Principal** and attaches it to the result itself. If a connection has no Principal, do not call **principal.getName()** directly; choose an appropriate authentication policy or anonymous session handling.

## 4. broadcast: send to all sessions or only the requesting session?

A user may open multiple connections, such as logging into the same account in two browser tabs or on both a computer and a phone.

By default, **@SendToUser** has **broadcast=true**. If the user has multiple sessions subscribed to the same destination, Spring sends the reply to all of those sessions. This is usually sensible when all devices of the same user need synchronized state.

If the reply is intended only for the connection that sent the request, set **broadcast=false**:

~~~java
@MessageMapping("/orders.check")
@SendToUser(value = "/queue/order-replies", broadcast = false)
public OrderCheckReply check(
        @Payload OrderCheckRequest request,
        Principal principal) {

    return orderService.check(request.orderId(), principal.getName());
}
~~~

Comparison:

| Configuration | Recipient scope |
|---|---|
| **@SendToUser("/queue/replies")** | By default sends to all sessions of the user subscribed to that destination |
| **@SendToUser(value="/queue/replies", broadcast=false)** | Only the session that sent the processed message receives the reply |
| User destination from an unauthenticated session | Spring handles it as scoped to the sending session, similar to broadcast=false |

For a request-response action tied to a specific tab or connection, **broadcast=false** is usually the clearest choice. For personal notifications that should sync across all devices of the same account, keep the default broadcast=true.

Note: broadcast=false only restricts receiving sessions. It does not replace data access authorization checks, user authentication, or subscription control.

## 5. Proactive sending with SimpMessagingTemplate

Replies are not always produced directly from the return value of **@MessageMapping**. A service might send a notification after processing finishes, after receiving an event from another system, or when a background job completes.

Use **SimpMessagingTemplate.convertAndSendToUser(username, destination, payload)**:

~~~java
@Service
public class OrderNotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderNotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void sendStatus(String username, OrderStatus status) {
        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/order-status",
                status);
    }
}
~~~

Here:

- The first parameter is the user name that Spring uses to find active sessions. For authenticated users, this value usually matches **Principal.getName()**.
- The second parameter is the destination portion after the user prefix, e.g., **/queue/order-status**. Do not pass **/user/{username}** into this parameter.
- The third parameter is the payload converted into a message by a message converter.

Clients receive the notification by subscribing to **/user/queue/order-status**. Spring maps the message to the sessions of the user with the corresponding name.

A controller can obtain the username from Principal and pass it to the service:

~~~java
@MessageMapping("/orders.refresh")
public void refresh(
        @Payload OrderRefreshRequest request,
        Principal principal) {

    OrderStatus status = orderService.refresh(request.orderId(), principal.getName());
    notificationService.sendStatus(principal.getName(), status);
}
~~~

This example uses **void** because the service sends the message via the template. If a method both returns a value and calls the template, make sure whether two replies are intended so as to avoid duplicate sending.

Differences between the two sending approaches:

| Criterion | @SendToUser | convertAndSendToUser |
|---|---|---|
| Recipient | User attached to the current message | Username passed in |
| Common usage site | STOMP handler method or exception handler | Service, listener, job, or any component |
| Sent content | Method return value | Payload passed to template |
| Selecting a single session of the current request | Has the broadcast=false attribute | Requires session-based design or custom sending context; username-based template calls normally target the user's sessions |
| Best suited when | Replying immediately to the request being processed | Sending proactive notifications or sending from background workflows |

## 6. Replying with errors to the exact requesting user

A business error arising during STOMP processing can also be sent privately to the user who sent the request. Use **@MessageExceptionHandler** combined with **@SendToUser**:

~~~java
public record OrderError(String code, String message) {}

@Controller
public class OrderController {

    @MessageMapping("/orders.cancel")
    public void cancel(@Payload CancelOrderRequest request, Principal principal) {
        orderService.cancel(request.orderId(), principal.getName());
    }

    @MessageExceptionHandler(OrderNotCancellableException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public OrderError handleOrderError(OrderNotCancellableException exception) {
        return new OrderError("ORDER_NOT_CANCELLABLE", exception.getMessage());
    }
}
~~~

This is an illustrative snippet; the DTOs, service, and exception must be declared in the application. The client subscribes to **/user/queue/errors** to receive errors for the session that sent the request. **broadcast=false** avoids sending an error from an action on one tab to all other tabs logged in as the same user.

You can declare multiple **@MessageExceptionHandler** methods by exception type or create a general handler. Return only error details that the client needs to know; do not send stack traces, SQL statements, tokens, credentials, or internal system details.

If an error handler needs to send to all sessions of the user, **broadcast=false** can be omitted. Choose the scope based on the error's meaning: an error from a specific action should usually return only to the requesting session.

## 7. STOMP configuration and client-side subscription

A basic configuration:

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

Spring uses **/user/** as the default user destination prefix. If the application changes the prefix via **setUserDestinationPrefix(...)**, client subscriptions and destination resolution must use the configured prefix. The broker must be able to handle the actual destinations generated by Spring; both the simple broker and a broker relay can be configured for these flows.

Example STOMP frames for the client:

~~~text
SUBSCRIBE
id:order-replies
destination:/user/queue/order-replies

^@

SEND
destination:/app/orders.check
content-type:application/json

{"orderId":"ORD-42"}

^@
~~~

In a real application, the client should register the subscription before sending the request so it does not miss a fast reply. When using a library such as **@stomp/stompjs**, the subscription callback receives MESSAGE frames; the client decodes the body according to the format sent by the server.

Do not subscribe to **/queue/order-replies** directly if it is a user destination. Also do not manually subscribe to **/user/alice/queue/order-replies**. The client uses the logical path **/user/queue/order-replies**; Spring handles the resolution.

## 8. Authentication and authorization

User destinations rely on the identity that Spring attaches to the message or session. Therefore, the authentication flow must be properly established before using **@SendToUser** or **convertAndSendToUser**.

Important principles:

1. Use the Principal from the authenticated connection to identify the requesting user.
2. Do not trust username, userId, role, or sender fields placed in the payload by the client.
3. When using tokens in STOMP CONNECT, validate the token on the server with an appropriate mechanism and attach Authentication/Principal to the message before controller processing.
4. Separately enforce SEND and SUBSCRIBE permissions. A user permitted to send requests to **/app/** should not automatically be allowed to subscribe to every user destination.
5. Only allow clients to subscribe to their own personal destinations via **/user/**. Do not open subscribe permissions on internal resolved queues or shared destinations containing data for multiple users.
6. Check business permissions before reading or sending private data, even when messages are sent using **convertAndSendToUser**.

For example, Spring Security can allow authenticated users to SUBSCRIBE to **/user/queue/**, allow MESSAGE to designated application destinations, and deny direct MESSAGE to broker destinations if clients have no need to publish. Specific rules depend on the application's permission matrix.

**@SendToUser** only chooses where to send. The annotation does not verify that the sender is authorized to view the order, account, or resource in the payload. The controller/service must still check permissions on each resource.

## 9. Multiple sessions and multi-instance deployments

When a user logs in from multiple locations, Spring maintains session information to map user destinations. By default, sending to an authenticated user can distribute to all sessions of the user subscribed to the destination. The **broadcast=false** attribute of **@SendToUser** restricts the reply to the session that sent the request.

In a multi-instance deployment, each node may only know about WebSocket sessions connected to that node. If user destinations must be resolved across nodes, configure user registry sharing and unresolved user destination broadcasting according to Spring's guidelines. A broker relay helps route messages through an external broker, but using a broker relay alone does not automatically ensure every node shares complete session information.

When designing a distributed system, check these scenarios:
- The user sends a request to node A, but the receiving session is managed by node B.
- The user is logged in simultaneously on multiple nodes.
- A node disconnects while sending a reply.
- The client reconnects and creates a new session.
- Whether the reply is ephemeral data or must be durably stored for the client to retrieve after reconnecting.

STOMP WebSocket does not automatically guarantee that a reply will be stored and replayed to offline clients. If reliability after disconnection is required, store the state/result in the business system and provide an API or sync mechanism when the client reconnects.

## 10. Common errors and diagnosis

**Client does not receive a reply**

- Check whether the client SUBSCRIBED to **/user/queue/...** before sending the request.
- Check whether the destination in **@SendToUser** matches the queue portion the client subscribed to. The annotation usually takes **/queue/replies**, while the client subscribes to **/user/queue/replies**.
- Check whether the message's Principal exists and the username matches the connected user session.
- Check whether the broker prefixes include the queue portion needed, such as **/queue**.
- Check the message converter, controller logs, broker channel, and outbound channel.

**One reply appears in multiple tabs**

- Check **broadcast** on **@SendToUser**. The default is true and targets all sessions of the same user.
- If the reply belongs strictly to the action in the current tab, set **broadcast=false**.
- If it is a personal notification that should sync across devices, keep the default broadcast.

**Reply sent to the wrong user**

- Do not take the recipient from an arbitrary field in the payload without permission checks.
- With **@SendToUser**, check the identity attached to the STOMP session and Principal.
- With **convertAndSendToUser**, check the username passed in and how the system normalizes login names.

**Using convertAndSendToUser but no subscriber receives it**

- The username parameter must match the user name managed by Spring, usually **Principal.getName()**.
- The destination passed in must be the trailing portion such as **/queue/updates**, without manually adding **/user/{username}**.
- The client must subscribe to **/user/queue/updates**.
- Check that the user session is still active and subscribed to the expected destination.

**Anonymous user does not receive a reply**

- A WebSocket session without an authenticated user can still use user destinations. With **@SendToUser**, Spring handles it scoped to the sending session, similar to **broadcast=false**.
- Do not call **principal.getName()** when Principal can be null.
- If a service needs to proactively send to an anonymous user after asynchronous processing, design a clear session identification and lifecycle mechanism.

**Private notifications leaked**

- Check SUBSCRIBE permissions on **/user/** and deny access to internal queues.
- Do not send sensitive data over broadcast destinations.
- Check business permissions before publishing messages and do not rely on a client-declared username.

## 11. Choosing the right sending approach

| Need | Implementation approach |
|---|---|
| Return the result of a STOMP request to the requesting user | **@MessageMapping** + **@SendToUser** |
| Return only to the tab/session that sent the request | **@SendToUser(..., broadcast=false)** |
| Sync notifications to all sessions of the same user | Default **@SendToUser** or **convertAndSendToUser** |
| Send notifications from a service or background task to a specific username | **SimpMessagingTemplate.convertAndSendToUser** |
| Return an error of a STOMP action to the session that caused the error | **@MessageExceptionHandler** + **@SendToUser(broadcast=false)** |
| Send a public notification to all subscribers | **@SendTo** or **convertAndSend** to **/topic/** |

You can remember the following rule: **@SendTo** is typically used to broadcast results to a shared destination; **@SendToUser** is used to send results to the user of the message currently being processed; **convertAndSendToUser** is used when a server-side component needs to proactively send to a specific username. All three must be placed within a clear routing and authorization configuration.

## References

- Spring Framework — User Destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Framework — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework — Sending Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html
- Spring Framework — Authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
