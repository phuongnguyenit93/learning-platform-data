# destination, subscription id, and message id in STOMP

## 1. Why distinguish the three concepts?

In STOMP, a message can pass through multiple destinations, be sent to multiple subscriptions, and carry its own identifier when the server delivers it to the client. The three concepts destination, subscription id, and message id are related to each other but solve three different problems:

- **destination** indicates where a message is sent or where the client wants to listen.
- **subscription id** identifies a specific subscription of a STOMP connection for receiving messages.
- **message-id** identifies a message that the server sends back to the client in a MESSAGE frame.

If you confuse them, an application can cancel the wrong subscription, fail to distinguish copies received for the same destination, ACK the wrong message, or use a temporary ID as a long-lived business key.

Besides the three values above, STOMP has other identifiers: id in SUBSCRIBE/UNSUBSCRIBE, the ack token, receipt/receipt-id, session id, transaction id, and business IDs defined by the application itself. Header names can be the same across commands, but their meaning depends on the command being sent.

This lesson uses STOMP 1.2 and Spring Framework 6.2 as its foundation. After the lesson, the reader can:

- Identify the destination in SEND, SUBSCRIBE, and MESSAGE.
- Explain the scope and uniqueness of the subscription id.
- Read message-id in a MESSAGE frame and understand who creates it.
- Distinguish message-id from the ack token, the receipt id, Spring MessageHeaders.ID, and the business event id.
- Understand how ACK/NACK link to a message in STOMP 1.2.
- Access headers through StompHeaderAccessor and a Spring Message.
- Configure the endpoint, broker, and @MessageMapping in Spring.
- Use a STOMP client to subscribe, publish, and read the returned IDs.
- Diagnose routing, subscription, and acknowledgement errors.

## 2. Destination: the routing address of a message

### 2.1. Where does a destination appear?

In STOMP, destination is a header that indicates where a message is sent or where the client wants to register to receive messages.

Destination is a required header in the frames:

- SEND: where the client sends the message.
- SUBSCRIBE: where the client registers to receive messages.
- MESSAGE: the destination the message is delivered from.

Example of a client sending a message:

~~~text
SEND
destination:/app/orders.publish
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001","status":"CREATED"}<NUL>
~~~

Example of a client registering to receive messages:

~~~text
SUBSCRIBE
id:orders-view-1
destination:/topic/orders
ack:auto

<NUL>
~~~

When the server delivers a message to a subscriber, the MESSAGE frame has a destination:

~~~text
MESSAGE
subscription:orders-view-1
message-id:server-msg-9001
destination:/topic/orders
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001","status":"CREATED"}<NUL>
~~~

The destination in MESSAGE indicates which destination the message was delivered from. According to STOMP 1.2, if the message was sent using STOMP SEND, the destination in MESSAGE should be the same as the destination of the corresponding SEND. Some application flows can re-route messages, so treat the destination the server sends back as the final source of information for that frame.

### 2.2. STOMP does not impose a meaning on destinations

STOMP treats a destination as an opaque string, meaning the protocol does not specify a particular syntax or delivery semantics. The server/broker decides which string is a queue, topic, exchange, routing key, user destination, or a custom kind of address.

Common conventions:

| Destination | Common convention | Note |
|---|---|---|
| /topic/orders | Publish/subscribe, one message to many subscribers | A common naming convention, not a mandatory STOMP keyword |
| /queue/orders | Point-to-point or competing consumers | The actual semantics depend on the broker |
| /app/orders.publish | A target for Spring to route to @MessageMapping | This is Spring's application prefix convention |
| /user/queue/notifications | A per-user target in Spring | Spring converts it into a concrete destination per user/session |

You should not infer that every STOMP server handles /queue the same way. Read the documentation of the broker you are using. Spring's simple broker is also not a full message broker: it keeps subscriptions in the application's memory and emits messages by the configured destinations.

### 2.3. Destinations in Spring

A common Spring STOMP configuration:

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
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Three groups of paths have different duties:

- /ws is the HTTP/WebSocket endpoint URL for the client to open a connection.
- /app is the prefix of STOMP destinations that are routed to controllers.
- /topic and /queue are prefixes handled by the simple broker.

For example, a client sends SEND to /app/orders.publish. Spring strips the /app prefix and finds the method @MessageMapping("/orders.publish"). The controller can return the result to /topic/orders using @SendTo.

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders.publish")
    @SendTo("/topic/orders")
    public OrderEvent publish(OrderEvent event) {
        return event;
    }
}
~~~

The path /app/orders.publish is a destination in the STOMP frame. It is not an HTTP POST URL and does not cause a new HTTP request.

### 2.4. A destination is routing data, not an access permission

A client can send a destination in SEND or SUBSCRIBE on its own. Therefore, the server must check whether the user has permission to send to or subscribe to that destination.

Do not trust a destination sent by the client just because it has a valid prefix. For example, /topic/admin-events may exist but not every user is allowed to subscribe. Authorization must be checked against the Principal, the tenant, and the business policy.

## 3. Subscription id: identifying a subscription for receiving messages

### 3.1. What is a subscription?

A client sends SUBSCRIBE to ask the server to register it to receive messages from a destination. The server creates a subscription tied to the STOMP connection and uses the subscription id to link the subsequent MESSAGE or UNSUBSCRIBE to that registration.

STOMP 1.2 requires SUBSCRIBE to have two headers:

- destination: where the client wants to listen.
- id: the subscription identifier.

Example:

~~~text
SUBSCRIBE
id:orders-view-1
destination:/topic/orders
ack:auto

<NUL>
~~~

The id value is set by the client. Within the same STOMP connection, different subscriptions must use different IDs. A connection can have multiple subscriptions to the same destination, as long as each subscription has its own ID.

Example:

~~~text
SUBSCRIBE
id:orders-main
destination:/topic/orders

<NUL>

SUBSCRIBE
id:orders-audit
destination:/topic/orders

<NUL>
~~~

The client has two separate registrations for the same destination. When a message is emitted to /topic/orders, both subscriptions can receive the message. Therefore, a client can receive two deliveries if it subscribes to the same destination multiple times.

### 3.2. A subscription id is scoped to a connection

A subscription id is not a system-wide ID. STOMP 1.2 only requires that different subscriptions on the same connection have different IDs.

For example, two browser tabs with two independent WebSocket connections can both use id:orders-view-1. That does not make them conflict because the subscriptions belong to two different connections.

When logging or storing subscription state, you should combine the subscription id with the session id or the user/session context. Do not store only the subscription id and then assume it is unique across the whole system.

### 3.3. MESSAGE returns the subscription id via the subscription header

When the server sends a MESSAGE to the client, the frame must have the subscription header. This value must match the id of the SUBSCRIBE that received the message.

Example:

~~~text
MESSAGE
subscription:orders-view-1
message-id:server-msg-9001
destination:/topic/orders
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001"}<NUL>
~~~

The subscription header indicates through which registration this MESSAGE was delivered. If the client has two subscriptions both listening to /topic/orders, subscription helps the client distinguish which subscription a delivery belongs to.

A subscription id does not identify the content of a message. A subscription can receive thousands of different messages; each MESSAGE still has its own message-id.

### 3.4. Canceling a subscription with UNSUBSCRIBE

To cancel a registration, the client sends UNSUBSCRIBE with the id that was used in SUBSCRIBE:

~~~text
UNSUBSCRIBE
id:orders-view-1

<NUL>
~~~

The server uses this ID to find the subscription to remove. The destination cannot replace the subscription id when canceling a registration.

If the client cancels the wrong ID, the server may report an error or be unable to find the corresponding subscription, depending on the implementation. When creating many dynamic subscriptions, you should keep the subscription object or the ID returned from the client library in order to cancel the right registration.

## 4. Message-id: identifying a message the server delivers to the client

### 4.1. Message-id appears in the MESSAGE frame

STOMP 1.2 requires every MESSAGE frame to have:

- destination: the destination of the message.
- message-id: a unique identifier for that message.
- subscription: the ID of the subscription that receives the message.

Example:

~~~text
MESSAGE
destination:/queue/orders
subscription:orders-worker-1
message-id:broker-message-73
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001"}<NUL>
~~~

message-id is an identifier at the protocol layer used by the server/broker when delivering a message. The client should treat it as an opaque value: store it if it needs to correlate frames, but do not parse its structure or create rules of its own based on its internal parts.

STOMP does not require the client to set a message-id in SEND. SEND has a destination and a body; the server/broker creates the MESSAGE frame when delivering the message to a subscription and supplies the message-id.

### 4.2. Message-id is not a business event id

A business event needs a stable ID to track it across multiple systems, retries, logs, and reprocessing. For example eventId = evt-1001 can be created by the application before publishing and stored with the outbox record.

STOMP's message-id serves to identify a message in the delivery protocol. Do not use it in place of eventId because:

- A business event can be published multiple times.
- The broker can create a new message-id when the message is emitted or redelivered.
- message-id has semantics and a scope that depend on the server/broker.
- A client reconnecting or re-subscribing can receive a new MESSAGE frame for the same business event.

If you need to deduplicate, use a stable business event id in the payload or in a custom header. For example, the consumer stores the processed eventId in an inbox table with a unique constraint.

### 4.3. Message-id differs from Spring MessageHeaders.ID

In Spring Messaging, a Message has a MessageHeaders.ID created by Spring to identify the Message object internally within the framework. This is the internal ID of the Spring Message.

The STOMP message-id is a native protocol header encoded into the MESSAGE frame. The two values can differ and have different lifecycles. When you need to read the STOMP header, use StompHeaderAccessor.getMessageId() or the client's frame.headers["message-id"]; do not use MessageHeaders.getId() and assume it is the STOMP message-id.

## 5. A table distinguishing the related IDs and headers

Some headers have similar names but their own meanings depending on the command.

| Header/value | Appears in frame | Who creates it | Meaning |
|---|---|---|---|
| destination | SEND, SUBSCRIBE, MESSAGE | The client in SEND/SUBSCRIBE; the server in MESSAGE | A routing address or receiving location |
| id | SUBSCRIBE | Client | Subscription id |
| id | UNSUBSCRIBE | Client | The subscription to cancel |
| subscription | MESSAGE | Server/broker | The subscription id that receives the message |
| message-id | MESSAGE | Server/broker | The identifier of the message delivered to the client |
| ack | MESSAGE when explicit ACK is needed | Server/broker | A token for ACK/NACK of the message |
| id | ACK/NACK in STOMP 1.2 | Client | The value must match the ack token of the MESSAGE |
| receipt | A client frame that requests a receipt | Client | A token the client asks the server to respond with |
| receipt-id | RECEIPT | Server | Echoes the corresponding receipt value |
| session | CONNECTED if the server provides it | Server | The STOMP session identifier |
| eventId | Payload or custom header | Application | A stable business ID |
| correlationId | Payload or custom header | Application | Links the messages in a business flow |
| MessageHeaders.ID | Internal Spring Message | Spring | The identifier of the Message object in Spring |

Note: the id header does not have a single meaning for all frames. With SUBSCRIBE, it is the subscription id. With UNSUBSCRIBE, it points to the subscription to cancel. With ACK/NACK in STOMP 1.2, it carries the ack token value of the MESSAGE.

## 6. The ACK token differs from message-id

This is one of the easiest points to confuse when working with STOMP 1.2.

### 6.1. Three acknowledgement modes

SUBSCRIBE can set the ack header:

- auto: the default if not declared. The client does not need to send ACK; the server considers the message received when it is sent to the client.
- client: the client must ACK. ACK has cumulative semantics and can acknowledge the specified message together with the earlier messages that have not been ACKed.
- client-individual: ACK/NACK applies independently to each message.

Example:

~~~text
SUBSCRIBE
id:orders-worker-1
destination:/queue/orders
ack:client-individual

<NUL>
~~~

With client or client-individual, the MESSAGE frame must additionally have an ack header:

~~~text
MESSAGE
subscription:orders-worker-1
message-id:broker-message-73
ack:ack-token-73
destination:/queue/orders
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001"}<NUL>
~~~

### 6.2. ACK in STOMP 1.2 uses the ack token

To acknowledge the message above, the client sends:

~~~text
ACK
id:ack-token-73

<NUL>
~~~

The id value of ACK must equal the ack value in MESSAGE. It is not the message-id.

This is an important difference between the two headers:

- message-id identifies the MESSAGE frame.
- ack is the token the server uses to link a MESSAGE with ACK/NACK.
- id in ACK/NACK carries the value of the ack token.

If the client sends ACK with the message-id instead of the ack token, the broker may be unable to determine which message to acknowledge.

### 6.3. NACK

If the client cannot process the message, it can send NACK, linking in the same way:

~~~text
NACK
id:ack-token-73

<NUL>
~~~

The broker can redeliver, discard, or move the message to a dead-letter destination. The specific behavior depends on the broker and the redelivery configuration.

ACK/NACK do not replace business idempotency. If the consumer has updated the database but loses the connection before the ACK reaches the broker, the message can be delivered again. The consumer needs to handle a repeated eventId safely.

## 7. receipt and receipt-id are not message-id

A client can ask the server to send a RECEIPT after processing a frame by adding the receipt header.

Example of a client requesting a receipt when subscribing:

~~~text
SUBSCRIBE
id:orders-view-1
destination:/topic/orders
receipt:orders-sub-ready

<NUL>
~~~

The server responds:

~~~text
RECEIPT
receipt-id:orders-sub-ready

<NUL>
~~~

receipt is a token created by the client. receipt-id is the value the server returns to indicate which frame has been processed.

A receipt confirms that the server has processed the corresponding frame according to STOMP semantics. It does not prove that the final consumer has finished processing a business message. For example, a RECEIPT for SEND is not evidence that all subscribers have received and successfully written the data.

Do not use receipt-id as a business event id or message-id. Each kind serves a different point in the protocol lifecycle.

## 8. The complete flow from SEND to MESSAGE

Suppose one client sends an event to Spring and another client has already subscribed to the destination /topic/orders.

~~~mermaid
sequenceDiagram
    participant P as Producer client
    participant S as Spring STOMP
    participant B as Simple broker
    participant C as Consumer client

    C->>S: SUBSCRIBE id=orders-view-1, destination=/topic/orders
    S->>B: Register subscription
    B-->>C: RECEIPT receipt-id=orders-sub-ready (if requested)
    P->>S: SEND destination=/app/orders.publish
    S->>S: @MessageMapping("/orders.publish")
    S->>B: Publish to /topic/orders
    B-->>S: MESSAGE for the matching subscription
    S-->>C: MESSAGE subscription=orders-view-1, message-id=server-msg-1
~~~

Detailed flow:

1. The consumer client sends SUBSCRIBE with a destination and a subscription id.
2. Spring decodes the STOMP frame and puts the message into the clientInboundChannel.
3. Spring routes the subscription to the broker.
4. The broker stores the registration tied to the session and the subscription id.
5. The producer sends SEND to /app/orders.publish.
6. Spring strips the application prefix /app and invokes @MessageMapping("/orders.publish").
7. The controller processes the event and sends the result to /topic/orders.
8. The broker finds the matching subscriptions.
9. Spring encodes a MESSAGE frame for each subscriber.
10. MESSAGE contains the destination, message-id, and subscription; if explicit ACK is needed, there is additionally an ack token.

An event can be emitted to multiple subscriptions. Each MESSAGE frame must carry the subscription id corresponding to the subscription that receives that frame. Therefore, the same business message can be seen by a client through multiple subscriptions with different subscription headers.

## 9. Reading headers in Spring with StompHeaderAccessor

The Spring Framework provides StompHeaderAccessor to access the decoded STOMP command and headers.

Commonly used methods:

| Method | Value |
|---|---|
| getCommand() | The STOMP command such as SEND, SUBSCRIBE, MESSAGE |
| getDestination() | The destination as mapped by Spring |
| getSubscriptionId() | The subscription id; mapped from the id of SUBSCRIBE/UNSUBSCRIBE or the subscription of MESSAGE |
| getMessageId() | The native STOMP message-id |
| getAck() | The native STOMP ack token |
| getFirstNativeHeader(name) | The first value of a native STOMP header |
| getSessionId() | The Spring WebSocket/STOMP session id |

A special point in Spring is that getSubscriptionId() normalizes the header by command:

- With SUBSCRIBE or UNSUBSCRIBE, Spring reads the native header id.
- With MESSAGE, Spring reads the native header subscription.

Therefore, server code does not have to check two different header names on its own to get the subscription id.

### 9.1. Access in @MessageMapping

Example of a controller that reads the destination and the custom header trace-id:

~~~java
package com.example.websocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class OrderController {

    @MessageMapping("/orders.publish")
    @SendTo("/topic/orders")
    public OrderEvent publish(
            @Payload OrderEvent event,
            StompHeaderAccessor accessor) {

        String destination = accessor.getDestination();
        String traceId = accessor.getFirstNativeHeader("trace-id");

        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }

        System.out.println(
            "destination=" + destination + ", traceId=" + traceId
        );

        return event;
    }
}
~~~

For a SEND frame sent to a controller, the destination is usually /app/orders.publish. The subscription id and message-id are usually absent on a SEND frame because it is not a MESSAGE frame delivered by the server to a subscriber.

Do not take a message-id from a SEND frame and assume the client created that ID according to standard STOMP. If you want to track an event sent by the client, use an eventId or correlationId defined by the application.

### 9.2. Monitoring SUBSCRIBE and UNSUBSCRIBE with a ChannelInterceptor

A ChannelInterceptor is suitable for auditing or applying policy to each STOMP frame after Spring has decoded it.

~~~java
package com.example.websocket;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

public class SubscriptionAuditInterceptor implements ChannelInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(SubscriptionAuditInterceptor.class);

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        StompHeaderAccessor accessor =
            StompHeaderAccessor.wrap(message);

        StompCommand command = accessor.getCommand();

        if (StompCommand.SUBSCRIBE.equals(command)) {
            log.info(
                "SUBSCRIBE session={} destination={} subscriptionId={}",
                accessor.getSessionId(),
                accessor.getDestination(),
                accessor.getSubscriptionId()
            );
        }
        else if (StompCommand.UNSUBSCRIBE.equals(command)) {
            log.info(
                "UNSUBSCRIBE session={} subscriptionId={}",
                accessor.getSessionId(),
                accessor.getSubscriptionId()
            );
        }

        return message;
    }
}
~~~

Register the interceptor on the inbound channel:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new SubscriptionAuditInterceptor());
}
~~~

This is an audit example. In a real application, you can extend the interceptor to check subscribe permission by destination, limit the number of subscriptions of a session, or record lifecycle events.

Do not use the subscription id as the basis for authenticating a user. It is sent by the client and only identifies a registration within the current connection. Identity needs to be taken from the Principal that Spring Security has authenticated.

## 10. A complete example with Spring Boot, Java 17, and STOMP.js

The example creates a STOMP endpoint to publish an order event. The client sends to /app/orders.publish; Spring handles it with @MessageMapping and emits the result to /topic/orders. A subscriber client reads the destination, subscription, and message-id from the MESSAGE frame.

The project uses Java 17, Spring Boot 3.5.x, and Spring Framework 6.2.x. Spring Boot manages the compatible Spring versions.

### 10.1. Project structure

~~~text
stomp-identifiers-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/websocket/
        │   ├── StompIdentifiersApplication.java
        │   ├── StompConfig.java
        │   ├── OrderController.java
        │   ├── OrderEvent.java
        │   └── SubscriptionAuditInterceptor.java
        └── resources/
            └── application.properties
~~~

### 10.2. Maven dependencies

Create pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>stomp-identifiers-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.3. Startup class

Create StompIdentifiersApplication.java:

~~~java
package com.example.websocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompIdentifiersApplication {

    public static void main(String[] args) {
        SpringApplication.run(StompIdentifiersApplication.class, args);
    }
}
~~~

### 10.4. Configuring the endpoint and broker

Create StompConfig.java:

~~~java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            .setAllowedOrigins("http://localhost:3000");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new SubscriptionAuditInterceptor());
    }
}
~~~

### 10.5. Business payload

Create OrderEvent.java:

~~~java
package com.example.websocket;

public record OrderEvent(
    String eventId,
    String orderId,
    String status
) {
}
~~~

eventId is a business ID managed by the application. It is kept in the payload so that the consumer can deduplicate or reconcile logs across multiple publishes. This is not a STOMP message-id.

### 10.6. Controller handling SEND

Create OrderController.java:

~~~java
package com.example.websocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class OrderController {

    @MessageMapping("/orders.publish")
    @SendTo("/topic/orders")
    public OrderEvent publish(
            @Payload OrderEvent event,
            StompHeaderAccessor accessor) {

        String traceId = accessor.getFirstNativeHeader("trace-id");

        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }

        System.out.println(
            "SEND destination=" + accessor.getDestination()
                + ", eventId=" + event.eventId()
                + ", traceId=" + traceId
        );

        return event;
    }
}
~~~

When a client sends to /app/orders.publish, Spring invokes the publish() method. The return value is sent to /topic/orders. The broker creates a MESSAGE frame for each matching subscription; the frame contains destination, subscription, and message-id.

### 10.7. Subscription audit interceptor

Create SubscriptionAuditInterceptor.java:

~~~java
package com.example.websocket;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

public class SubscriptionAuditInterceptor implements ChannelInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(SubscriptionAuditInterceptor.class);

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        StompHeaderAccessor accessor =
            StompHeaderAccessor.wrap(message);

        if (StompCommand.SUBSCRIBE.equals(accessor.getCommand())) {
            log.info(
                "SUBSCRIBE session={} destination={} subscriptionId={}",
                accessor.getSessionId(),
                accessor.getDestination(),
                accessor.getSubscriptionId()
            );
        }

        if (StompCommand.UNSUBSCRIBE.equals(accessor.getCommand())) {
            log.info(
                "UNSUBSCRIBE session={} subscriptionId={}",
                accessor.getSessionId(),
                accessor.getSubscriptionId()
            );
        }

        return message;
    }
}
~~~

### 10.8. Application configuration

Create application.properties:

~~~properties
spring.application.name=stomp-identifiers-demo
server.port=8080
~~~

### 10.9. Running the application

From the project directory:

~~~bash
mvn spring-boot:run
~~~

The application exposes the WebSocket/STOMP endpoint at ws://localhost:8080/ws.

### 10.10. STOMP.js client

Install the library:

~~~bash
npm install @stomp/stompjs
~~~

Client example:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,

    onConnect: () => {
        const subscription = client.subscribe(
            "/topic/orders",
            (frame) => {
                const destination = frame.headers.destination;
                const subscriptionId = frame.headers.subscription;
                const messageId = frame.headers["message-id"];
                const event = JSON.parse(frame.body);

                console.log({
                    destination,
                    subscriptionId,
                    messageId,
                    eventId: event.eventId
                });
            },
            {
                id: "orders-view-1",
                ack: "auto"
            }
        );

        console.log("active subscription:", subscription.id);

        client.publish({
            destination: "/app/orders.publish",
            headers: {
                "content-type": "application/json",
                "trace-id": "trace-1001"
            },
            body: JSON.stringify({
                eventId: "evt-1001",
                orderId: "ORD-1001",
                status: "CREATED"
            })
        });
    },

    onStompError: (frame) => {
        console.error("STOMP error:", frame.headers.message);
        console.error(frame.body);
    }
});

client.activate();
~~~

In the callback:

- destination is the destination from which the broker delivered the message.
- subscriptionId is the subscription that received the MESSAGE.
- messageId is the STOMP message-id issued by the server/broker.
- eventId is the business identifier in the JSON body.

These values are read from three different sources and should not be substituted for one another.

### 10.11. Corresponding frame flow

The client sends SUBSCRIBE:

~~~text
SUBSCRIBE
id:orders-view-1
destination:/topic/orders
ack:auto

<NUL>
~~~

The client sends SEND:

~~~text
SEND
destination:/app/orders.publish
content-type:application/json
trace-id:trace-1001

{"eventId":"evt-1001","orderId":"ORD-1001","status":"CREATED"}<NUL>
~~~

The server delivers MESSAGE:

~~~text
MESSAGE
subscription:orders-view-1
message-id:server-generated-id
destination:/topic/orders
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001","status":"CREATED"}<NUL>
~~~

server-generated-id is just an illustrative value. The actual ID is generated by the STOMP server/broker and may have a different format.

## 11. Destination, subscription, and message-id in real-world scenarios

### 11.1. One connection subscribing to multiple destinations

The client can register:

~~~text
SUBSCRIBE
id:orders-sub
destination:/topic/orders

<NUL>

SUBSCRIBE
id:payments-sub
destination:/topic/payments

<NUL>
~~~

The two subscriptions have different IDs. A MESSAGE from /topic/orders carries subscription:orders-sub; a MESSAGE from /topic/payments carries subscription:payments-sub.

### 11.2. One connection subscribing to the same destination multiple times

Example:

~~~text
SUBSCRIBE
id:orders-panel
destination:/topic/orders

<NUL>

SUBSCRIBE
id:orders-audit
destination:/topic/orders

<NUL>
~~~

Both subscriptions can receive messages from /topic/orders. If the client does not want to process duplicates, create only one subscription or control subscriptions according to the UI component lifecycle.

### 11.3. Client reconnect

When a WebSocket/STOMP connection is closed and reopened, the client must re-create the necessary subscriptions. The old subscription id can be reused on the new connection, but the previous subscription belonged to the old connection and is no longer an active registration.

Do not assume that message-id will be the same after a reconnect or redelivery. If you need to know whether a business event has already been processed, use a stable eventId and store the processing state on the server.

### 11.4. Broker relay

When Spring uses a broker relay, STOMP messages are forwarded to an external broker. Destination semantics, message-id format, redelivery, and acknowledgement behavior may depend on the broker. The client must still follow the STOMP frame structure, but should not depend on a specific broker's proprietary ID format if the application needs to switch brokers.

## 12. Ensuring correctness and idempotency

A message can be sent again due to a lost connection, broker redelivery, or a client retry. Therefore, the protocol's message-id is not a duplicate-prevention mechanism at the business layer.

A commonly used design:

1. The producer generates a stable eventId before the first publish.
2. The producer puts the eventId into the payload or a custom native header.
3. The consumer receives the message and checks whether the eventId has already been processed.
4. If not yet processed, the consumer performs the business logic and writes the eventId into an inbox table or dedup store within the same appropriate transaction.
5. If the eventId already exists, the consumer skips the side effects and acknowledges the message according to the acknowledgement mode.

Example payload:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "status": "CREATED"
}
~~~

eventId must be generated by the application and remain stable across retries. Do not generate a new eventId on each retry if you want to deduplicate the same event.

correlationId has a different purpose: linking a request, a response, or steps in a workflow. You can use eventId to deduplicate and correlationId to trace the processing flow; a system may need both.

## 13. Security of destinations and IDs

- Do not treat subscription id as the user's identity. The client can choose this value itself.
- Do not allow a client to subscribe to sensitive destinations without checking permissions first.
- Check SEND and SUBSCRIBE permissions separately; permission to send does not mean permission to read.
- Do not use message-id as an access token or secret.
- Do not use an eventId sent by the client as proof that the user has been authenticated.
- Do not allow the client to self-declare a userId and then use that value as the subscription owner.
- Limit the number of subscriptions per connection to avoid excessive resource consumption.
- Limit frame size, header count, and SEND rate according to application policy.
- Log the destination, session id, and subscription id when auditing is needed; avoid logging payloads or sensitive tokens.
- When using a broker relay, configure destination permissions and credentials separately for the client and system connections.

Destinations and IDs help with routing, correlation, and lifecycle management. They do not replace authentication or authorization.

## 14. Diagnosing common errors

| Symptom | Common cause | How to check |
|---|---|---|
| SUBSCRIBE gets ERROR | Missing destination or id, invalid destination | Check the SUBSCRIBE frame and the broker destination |
| Two subscriptions on the same connection conflict | Reusing the same id | Assign a different ID to each subscription |
| MESSAGE does not have the expected subscription | The client subscribed to the wrong destination or the registration was canceled | Check SUBSCRIBE, UNSUBSCRIBE, and MESSAGE.subscription |
| Client does not receive MESSAGE | Not subscribed, wrong destination, or broker did not route | Compare SEND.destination, SUBSCRIBE.destination, and MESSAGE.destination |
| Client cancels the wrong registration | Used destination instead of subscription id | UNSUBSCRIBE must carry the id of SUBSCRIBE |
| ACK is rejected or does not acknowledge | Used message-id instead of the ack token in STOMP 1.2 | Compare ACK.id with MESSAGE.ack |
| Message is processed repeatedly | Redelivery or retry; used message-id as dedup key | Use a stable business eventId |
| Cannot find message-id on SEND | Client is looking for a header only required in MESSAGE | Check the MESSAGE frame on the receiving side |
| Receipt does not prove business processing succeeded | Receipt only confirms the server processed the frame | Use a separate business acknowledgement if needed |
| Client receives the message twice | Two subscriptions to the same destination or multiple delivery paths | Check the subscription ids and routing |
| Logs do not match native header | Confused Spring internal header with STOMP native header | Use StompHeaderAccessor and getFirstNativeHeader |

## 15. Testing STOMP identifiers end-to-end

A test should verify the following steps:

1. Open a STOMP connection.
2. Subscribe twice to the same destination with two different IDs.
3. Confirm that MESSAGE from each subscription has the corresponding subscription header.
4. Check that MESSAGE has destination and message-id.
5. If using ack:client-individual, confirm that MESSAGE has an ack token.
6. Send ACK with id equal to the ack value, not message-id.
7. Send UNSUBSCRIBE with the exact id and confirm that subscription stops receiving messages.
8. Subscribe with a receipt and check that receipt-id matches the receipt sent.
9. Reconnect and then re-register the subscription.
10. Publish the same eventId again and verify that the consumer deduplicates properly according to business rules.

When using Spring, you can test the controller separately, but you still need an integration test with a STOMP client to verify destination mapping, subscription lifecycle, message-id, and ACK/receipt on the wire.

## 16. Common misconceptions

- **Assuming destination is the message ID**: destination is the routing address; one destination contains many messages.
- **Assuming subscription id is the destination**: destination indicates where to listen; subscription id distinguishes each registration.
- **Assuming subscription id must be system-wide unique**: STOMP 1.2 requires uniqueness within the same connection.
- **Assuming message-id is sent by the client in SEND**: only the MESSAGE frame delivered by the server is required to have message-id.
- **Using message-id as eventId**: the two IDs have different lifecycles and purposes.
- **Using the id of SUBSCRIBE to ACK**: ACK in STOMP 1.2 needs id equal to the ack value of MESSAGE.
- **Using message-id to ACK**: message-id and ack token are two separate headers.
- **Using receipt-id to deduplicate business events**: receipt only correlates a frame that requested a receipt.
- **Assuming /topic and /queue have the same semantics on every broker**: STOMP lets the server decide the semantics of destinations.
- **Using subscription id to authenticate the user**: this is a value set by the client, not a trusted identity.
- **Assuming a reconnect keeps old subscriptions**: a new connection needs to re-create the subscriptions.
- **Confusing MessageHeaders.ID with STOMP message-id**: Spring's internal ID is not a native protocol header.

## 17. Implementation checklist

- [ ] Choose a clear destination naming convention for the application and the broker.
- [ ] Determine which destinations are allowed for SEND and which destinations are allowed for SUBSCRIBE.
- [ ] Assign a distinct subscription id for each SUBSCRIBE within the same connection.
- [ ] Store the subscription id in order to UNSUBSCRIBE the right registration.
- [ ] Read the subscription from MESSAGE.subscription.
- [ ] Read message-id from MESSAGE and treat it as an opaque protocol ID.
- [ ] Choose an ack mode appropriate to the delivery requirements.
- [ ] With STOMP 1.2 explicit ACK, use MESSAGE.ack as ACK.id.
- [ ] Use receipt/receipt-id to confirm the server processed a frame when needed.
- [ ] Generate a stable eventId for business logic and deduplication.
- [ ] Use correlationId to trace a request/workflow if needed.
- [ ] Use StompHeaderAccessor to read destination, subscription id, and message-id.
- [ ] Do not use IDs sent by the client for authentication or authorization.
- [ ] Test multiple subscriptions on the same connection.
- [ ] Test reconnect, redelivery, ACK/NACK, and receipt.
- [ ] Verify destination semantics according to the actual broker.

## 18. Summary

Destination answers the question of where a message is sent or where the client wants to listen. Subscription id identifies a subscription for receiving messages within a STOMP connection. Message-id identifies the message that the server delivers to the client in a MESSAGE frame.

In STOMP 1.2, SUBSCRIBE uses id to identify the subscription; MESSAGE returns that ID in the subscription header while also having its own message-id. When explicit acknowledgement is enabled, MESSAGE also has an ack token; the client must use that token as the id header of ACK/NACK. receipt and receipt-id are a separate pair to confirm that the server has processed a frame that requested a receipt.

In Spring, StompHeaderAccessor provides getDestination(), getSubscriptionId(), getMessageId(), getAck(), and getFirstNativeHeader() to read these values. Keep the business event id and correlation id separate in the payload or custom headers to deduplicate and trace business operations across retries, reconnects, and different brokers.

## References

- STOMP Protocol Specification 1.2 — SEND, SUBSCRIBE, subscription id, ACK/NACK, MESSAGE and RECEIPT: https://stomp.github.io/stomp-specification-1.2.html
- Spring Framework 6.2 — Flow of Messages: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html
- Spring Framework 6.2 — Annotated Controllers: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-annotations.html
- Spring Framework 6.2.14 — StompHeaderAccessor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html
- Spring Framework 6.2.3 — SimpMessageHeaderAccessor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/messaging/simp/SimpMessageHeaderAccessor.html
- Spring Framework 6.2 — STOMP overview: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp.html