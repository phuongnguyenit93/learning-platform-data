# Distinguishing Controller Handling from Forwarding Directly to the Broker in STOMP

## Objectives

In Spring WebSocket + STOMP, a frame from a client can be routed either to an application controller or to the message broker. Both paths start from the WebSocket connection and pass through Spring's messaging infrastructure, but they differ in where the business logic is handled, how outgoing messages are produced, and what permissions the client needs.

"Forwarding directly to the broker" in this lesson means that Spring routes the frame to the broker handler without invoking a controller method. The client still connects to the WebSocket endpoint of the Spring application. If a broker relay is used, Spring continues to forward the frame over a STOMP connection to the external broker; the client does not automatically connect directly to the broker server.


**Scope of the Java examples:** The code blocks in this lesson are illustrative snippets for components of a Spring application that has already been configured for STOMP. They omit some imports, DTOs, services, and supporting configuration that are not directly related to the flow being explained. The examples that use `@Valid` and `@NotBlank` require the Jakarta Bean Validation API together with an implementation provider such as Hibernate Validator; with Spring Boot you can add `spring-boot-starter-validation`. Without a provider, the constraint annotations do not perform validation on their own.

## 1. Components and destination conventions

- **WebSocket** provides a long-lived two-way connection between client and server.
- **STOMP** defines frames such as CONNECT, SEND, SUBSCRIBE, MESSAGE, and DISCONNECT, along with the destination header.
- **Spring Messaging** represents frames as Message objects and puts messages onto internal channels, typically **clientInboundChannel**, **brokerChannel**, and **clientOutboundChannel**.
- **Controllers** handle messages routed to **@MessageMapping** methods or subscriptions routed to **@SubscribeMapping**.
- **The broker** manages subscriptions and delivers messages to subscribers with matching destinations.

A common configuration separates destinations meant for the application from destinations meant for the broker:

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

In the configuration above:

- **/ws** is the WebSocket endpoint where clients establish a connection.
- **/app** is the prefix for messages entering the application's handling layer.
- **/topic** and **/queue** are prefixes handled by the broker.
- When routing to a controller, Spring strips the **/app** prefix before matching the remainder against **@MessageMapping**.

The names **/app**, **/topic**, and **/queue** are common configuration conventions, not three mandatory keywords of the STOMP protocol. You can choose other prefixes, but keep them clear and make sure they do not overlap between the controller and the broker.

## 2. The flow where a client sends a message for a controller to handle

Suppose a client sends a message to **/app/chat.send**, while clients receive chat messages by subscribing to **/topic/chat**.

Processing flow:

1. The client sends a STOMP SEND frame to **/app/chat.send**.
2. Spring decodes the frame, creates a Message, and puts it into **clientInboundChannel**.
3. The **/app** prefix causes the message to be routed to the application's group of handlers. Spring strips this prefix, then looks for the method matching **@MessageMapping("/chat.send")**.
4. Spring converts the payload, headers, and user information into suitable method parameters. If configured, the payload can be validated with Jakarta Validation.
5. The controller performs the business logic: validating data, identifying the sender from the Principal, calling services, persisting data, or applying authorization rules.
6. The return value is sent through **brokerChannel** to the broker. **@SendTo** lets you specify the output destination.
7. The broker finds the subscriptions matching the destination and sends a MESSAGE frame to the corresponding clients through **clientOutboundChannel**.

Java 17+ example:

~~~java
public record ChatCommand(@NotBlank String text) {}

public record ChatEvent(String sender, String text) {}

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatEvent send(
            @Valid @Payload ChatCommand command,
            Principal principal) {

        return new ChatEvent(principal.getName(), command.text());
    }
}
~~~

The client sends to **/app/chat.send**. The controller receives the remaining destination part, **/chat.send**. After the method returns the **ChatEvent**, Spring converts the result into a message and sends it to **/topic/chat**; the broker delivers the message to the clients that have subscribed to that destination.

**@SendTo** explicitly states where the result goes. If no output destination is specified, Spring by default derives the destination by replacing the **/app** prefix of the input destination with **/topic**. For example, the result of **/app/greeting** is sent by default to **/topic/greeting**.

You can use **@SendToUser("/queue/updates")** to send the result to the user associated with the current message. A controller can also call **SimpMessagingTemplate** when it needs to send multiple messages, send conditionally, or send to a destination determined at runtime.

The key point: the message passes through the controller before the application emits it to the broker. This makes it the right choice when the application must decide whether the message is valid, who may send it, who it should be sent to, how the content needs to be transformed, or whether it needs to be persisted.

## 3. The flow where a client sends directly to the broker

With the same chat example, a client can send a SEND frame directly to a broker destination such as **/topic/chat**, if the configuration and security policy allow it.

~~~text
SUBSCRIBE
id:sub-1
destination:/topic/chat

[SUBSCRIBE frame terminated by a NUL character]

SEND
destination:/topic/chat
content-type:application/json

{"text":"Hello everyone"}
[SEND frame terminated by a NUL character]
~~~

When a client sends to **/topic/chat**:

1. The frame is still received by Spring over WebSocket and put into **clientInboundChannel**.
2. The destination matches the configured broker prefix.
3. The broker handler receives the message directly; the **@MessageMapping** method in the controller is not invoked.
4. The broker applies its routing rules and delivers the message to the matching subscriptions.

On this path, the controller does not automatically validate the content, write data, attach the sender's identity, or perform business logic. The broker is responsible for processing according to the destination, the subscriptions, and the broker's own policies. If a simple broker is used, delivery takes place inside the simple broker running in the Spring application. If a broker relay is used, Spring forwards the frame to the external STOMP broker.

It is necessary to distinguish "going directly to the broker" from "bypassing the Spring server": the client still sends the frame over the application's WebSocket connection. Spring still receives the frame and routes it to the broker handler. With a broker relay, Spring also acts as a forwarder between the WebSocket client and the external broker.

## 4. Three easily confused paths

There are three common ways for a message to reach the broker:

| Path | Message source | Does a controller handle it? | Entry point to the broker |
|---|---|---|---|
| Client → controller → broker | Client SEND to **/app/** | Yes, via **@MessageMapping** | Return value, **@SendTo**, or template |
| Client → broker | Client SEND to **/topic/** or **/queue/** | **@MessageMapping** is not invoked | Received directly by the broker handler |
| Application → broker | Server-side service, HTTP controller, job, or listener | **@MessageMapping** is not needed for outgoing messages | **SimpMessagingTemplate** sends via **brokerChannel** |

Example of the third path:

~~~java
@Service
public class NotificationPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(SystemEvent event) {
        messagingTemplate.convertAndSend("/topic/system-events", event);
    }
}
~~~

A service can publish a message after completing business logic, after receiving an event from another system, or within an HTTP request. **convertAndSend** sends the message to the broker channel for the broker to deliver; it does not call back into an **@MessageMapping** method.

Therefore, when saying "the controller handles it and then sends it to the broker", you need to determine whether the controller actually handles the incoming message or is merely a place that calls **SimpMessagingTemplate**. Both can produce messages on the server side, but only the first path begins with a STOMP message routed to **@MessageMapping**.

## 5. SUBSCRIBE and the special case of @SubscribeMapping

Not every frame is routed the same way as SEND:

- A client SUBSCRIBE to **/topic/chat** or **/queue/orders** is typically handled by the broker to register the subscription.
- A client SUBSCRIBE to a destination under the application prefix such as **/app/chat.initial** can be handled by a method annotated with **@SubscribeMapping("/chat.initial")**.

**@SubscribeMapping** suits the one-time request-reply style, for example fetching initial data when a screen has just opened:

~~~java
@Controller
public class ChatQueryController {

    @SubscribeMapping("/chat.initial")
    public List<ChatEvent> initialMessages() {
        return chatService.findRecentMessages();
    }
}
~~~

The client subscribes to **/app/chat.initial**. By default, the return value is sent directly back to the client that created the subscription through **clientOutboundChannel**, without passing through the broker channel and without being stored as a broker subscription. The client receives the initial snapshot but will not automatically receive subsequent updates from this destination.

If you add **@SendTo** or **@SendToUser**, the result of **@SubscribeMapping** is sent through the broker instead of being returned directly. You should not configure the controller and the broker to handle the same destination prefix without a clear intention: the handlers may process the message in parallel, and there is no guarantee about which handler runs first.

## 6. Comparison when choosing

| Criterion | Handling at the controller | Forwarding directly to the broker |
|---|---|---|
| Where business decisions are made | Application code | The broker and broker configuration |
| Payload validation | Can use validation and services | No business validation from a controller |
| Sender identity | Can be obtained from **Principal** and attached to the message | Must rely on authentication information, ACLs, and metadata trusted by the broker |
| Content transformation | Easy to do in the controller/service | Usually no application business transformation step |
| Persisting business data | Can coordinate with repositories/services | Not automatically saved to the application database |
| Pub-sub delivery | The controller publishes the message, the broker delivers | The broker receives and delivers directly |
| Application processing cost | Has an additional controller processing step | Less business processing in the application |
| Suitable when | Business rules, permission checks, data validation, or persistence are needed | Simple pub-sub flows where clients are allowed to publish and the broker can apply policies itself |

Do not choose the direct broker path just because it has fewer steps. If a client can send to **/topic/** by itself, the client can publish content that other subscribers will see. If the message represents a business action, such as placing an order, making a payment, changing a status, or sending a system notification, route it through a controller/service so that the server decides the content and the right to publish.

## 7. Security: separating SEND and SUBSCRIBE permissions

In STOMP, SEND and SUBSCRIBE are two different kinds of action. A client may be allowed to receive notifications but not be allowed to send notifications into that destination itself.

A commonly used policy with Spring Security:

- Allow only authenticated users to send messages to **/app/**, then check business permissions in the controller/service.
- Allow SUBSCRIBE to destinations that the user's role is permitted to read.
- Deny MESSAGE from clients to **/topic/** and **/queue/** if the application has no need for clients to publish directly. This prevents clients from forging system messages or sending arbitrary data to subscribers.
- If you allow clients to send directly to the broker, restrict destinations and publish permissions with the corresponding authorization configuration; with an external broker, the ACL configuration on the broker must also be appropriate.
- Do not trust the **sender**, **userId**, **role** fields or a username sent by the client in the payload. Take the identity from the authenticated **Principal** and attach it to the message yourself on the server.
- Protect SUBSCRIBE carefully because the subscribe permission determines which data a client can read. Spring Security protects incoming messages; you need to control subscriptions to avoid leaking data to people without permission.

For per-user private messages, use a user destination such as **/user/queue/updates**, combined with **@SendToUser** or **SimpMessagingTemplate.convertAndSendToUser(user, "/queue/updates", payload)**. The client subscribes to **/user/queue/updates**; Spring maps this logical destination to the actual destination tied to the user/session. Do not let clients freely subscribe to another user's internal queue.

## 8. Simple broker and broker relay

**enableSimpleBroker("/topic", "/queue")** enables the simple broker built into Spring. This broker stores subscriptions in memory and publishes messages to clients subscribed to matching destinations. It is useful for small applications, development environments, or basic pub-sub flows.

The simple broker supports only part of STOMP, does not provide the full set of features such as ACK and receipt, is not a distributed broker, and is not suitable for clustered deployments. Do not assume by default that a destination name like **/queue** creates a durable queue or guarantees that messages are stored when there are no subscribers.

When you need a full-featured broker, you can replace the simple broker with the STOMP broker relay:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("localhost")
            .setRelayPort(61613);
}
~~~

The external broker must be installed and have STOMP support enabled; login credentials and connection configuration must be set up appropriately for the environment. The relay lets Spring pass messages between WebSocket clients and the external broker. Durability, ACK, queue/topic delivery, clustering, and delivery guarantees depend on the type of broker and its specific configuration; do not infer these guarantees merely from the use of a broker relay.

## 9. Common errors and how to check

**The @MessageMapping method is not invoked**

- Check that the frame is SEND and that the destination starts with the configured application prefix.
- Check that the remaining destination part matches the **@MessageMapping** at the class and method level.
- Check whether the client is mistakenly sending to **/topic/** or **/queue/**. These destinations are usually routed to the broker.

**The controller runs but subscribers do not receive the result**

- Check that the destination in **@SendTo** matches the destination the client subscribes to.
- Check that the broker has enabled the corresponding prefix and that the subscription has been registered.
- Check whether the payload was successfully converted by the message converter; look at the logs of the inbound channel, the controller, and the broker when needed.

**Clients can forge notifications**

- Check whether the policy lets clients send MESSAGE to **/topic/** or **/queue/**.
- Separate the MESSAGE permission from SUBSCRIBE; allow direct publishing only when that is an intentional requirement.
- Take the identity from the Principal instead of trusting the sender field in the payload.

**A message is processed twice or the result is unstable**

- Check whether the application prefix and the broker prefix overlap.
- Avoid mapping the same destination to both a controller and the broker without a special reason. Spring may route the message to the corresponding handlers in parallel, so you cannot rely on processing order to determine the outcome.

**Using /queue but expecting messages to be stored while the client is offline**

- Check the actual broker type and queue configuration. The simple broker keeps subscriptions in memory and is not a durable queue.
- If you need durability, ACK, retry, or delivery across multiple instances, choose a broker that supports them and configure those mechanisms explicitly.

## 10. Quick recognition rules

| Frame or call | Typical path |
|---|---|
| Client SEND **/app/orders** | Controller via **@MessageMapping** |
| Client SEND **/topic/notifications** | Directly to the broker, if configured and allowed |
| Client SEND **/queue/tasks** | Directly to the broker, if configured and allowed |
| Client SUBSCRIBE **/topic/notifications** | The broker registers the subscription |
| Client SUBSCRIBE **/app/dashboard.initial** | **@SubscribeMapping** if a matching handler exists |
| Server calls **convertAndSend("/topic/notifications", event)** | The server sends to the broker channel |
| Controller returns a value with **@SendTo("/topic/notifications")** | The controller handles it first, then sends to the broker |

You can remember it by destination: **/app/** is usually for requests that need the application to handle them; **/topic/** and **/queue/** are usually for subscriptions and broker routing. The actual rules still depend on the configured prefixes and the application's security policy.

## References

- Spring Framework — Flow of Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework — Sending Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html
- Spring Framework — Simple Broker: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html
- Spring Framework — External Broker: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html
- Spring Framework — User Destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
