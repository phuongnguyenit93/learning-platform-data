# clientInboundChannel, brokerChannel, and clientOutboundChannel

In the Spring Framework, when enabling STOMP over WebSocket with **@EnableWebSocketMessageBroker**, Spring creates an internal message flow consisting of three main channels: **clientInboundChannel**, **brokerChannel**, and **clientOutboundChannel**. Each channel connects a group of components in the application, helping separate receiving messages from clients, processing on the server side, and publishing messages back to clients.

These three channels are **Spring MessageChannel** instances inside the server-side processor. They are not three STOMP destinations such as /app, /topic, or /queue. The destination determines which handler a message is routed to; a channel is the path that passes messages between Spring components.

## 1. Roles of the three channels

| Channel | Flow direction | Main role |
|---|---|---|
| **clientInboundChannel** | WebSocket client → Spring | Receives STOMP frames decoded into Spring Messages for routing to controllers or the broker. |
| **brokerChannel** | Spring application → message broker | Passes messages produced by server-side code to the broker to find matching subscribers. |
| **clientOutboundChannel** | Broker/application → WebSocket client | Passes messages sent to clients for Spring to encode into STOMP frames and write to WebSocket sessions. |

You can picture it as:

~~~text
                 CLIENT
                   |
             STOMP over WS
                   |
                   v
        +-----------------------+
        |  clientInboundChannel |
        +-----------------------+
                   |
          +--------+---------+
          |                  |
       /app/...          /topic/...,
          |               /queue/...
          v                  |
  @MessageMapping            |
          |                  |
   handler return            |
          |                  |
          v                  |
    +---------------+        |
    | brokerChannel |<-------+
    +---------------+
          |
          v
    Message Broker
          |
          v
  +------------------------+
  | clientOutboundChannel  |
  +------------------------+
          |
          v
     STOMP over WS
          |
          v
        CLIENT
~~~

In the diagram, the /topic or /queue path from inbound is handled directly by the broker handler to register subscriptions or receive SENDs. Messages published by server-side controllers or services pass through brokerChannel.

## 2. clientInboundChannel: the entry path from clients

When a client sends a STOMP frame over WebSocket, Spring decodes the frame and creates an **org.springframework.messaging.Message<?>** containing the payload along with headers. That message is sent into clientInboundChannel.

Frames that commonly pass through this channel include:

- **CONNECT / STOMP:** starts a STOMP session.
- **SUBSCRIBE:** registers to receive messages at a destination.
- **UNSUBSCRIBE:** cancels a subscription.
- **SEND:** sends a payload to the server or broker.
- **ACK / NACK:** acknowledges or rejects a message in a subscription using explicit acknowledgment.
- **DISCONNECT:** ends a STOMP session.

After entering the channel, the message is handled by the handlers subscribed to it. Spring relies on the destination prefix and STOMP command to choose the branch:

- Destinations starting with **/app** are usually routed to **@MessageMapping** methods.
- Destinations starting with **/topic** or **/queue** can be routed directly to the message broker.
- Connection/subscription management commands are handled by the broker handler and the corresponding STOMP components.

### SEND flow to a controller

Suppose the server configures the application prefix as /app:

~~~text
Client SEND
destination:/app/chat

{"text":"Hello"}
       |
       v
clientInboundChannel
       |
       | remove /app prefix to look up mapping
       v
@MessageMapping("/chat")
       |
       v
ChatController.handle(...)
~~~

The /app prefix helps distinguish messages sent into application logic from messages sent directly to the broker. This prefix is not a separate channel.

### SUBSCRIBE flow to the broker

When a client sends:

~~~text
SUBSCRIBE
id:chat-sub
destination:/topic/chat

^@
~~~

Spring passes the frame into clientInboundChannel. The broker handler recognizes the /topic/chat destination and registers the subscription for the corresponding session. When a message is published to the destination, the broker finds matching subscribers and sends the message out to clientOutboundChannel.

### Tasks suited for the inbound channel

- Authenticating STOMP CONNECT if the application uses tokens at the STOMP layer.
- Checking SEND or SUBSCRIBE permissions by user and destination.
- Validating commands, headers, and payload limits.
- Attaching a correlation ID or metadata for tracing.
- Collecting metrics on the number of messages sent by clients.
- Blocking invalid messages before they reach a controller or the broker.

Do not place long database queries or slow HTTP calls inside a synchronous inbound channel interceptor. Doing so holds worker threads and can cause the inbound queue to grow quickly.

## 3. brokerChannel: the path from server code to the broker

**brokerChannel** carries messages created inside the Spring application to the message broker. This is the path that controllers, services, or other components use when they want to publish messages to subscribers.

Two common sources:

1. The return value from a **@MessageMapping** method is converted by Spring into a message and sent to brokerChannel.
2. The application calls **SimpMessagingTemplate.convertAndSend(...)** or **send(...)** to publish from any bean.

### Controller returning a message

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat")
    @SendTo("/topic/chat")
    public ChatMessage handle(ChatMessage message) {
        return message;
    }
}
~~~

The client sends to /app/chat. Spring invokes the handle method, takes the return value, and sends the message to /topic/chat through brokerChannel. The broker finds subscribers listening on /topic/chat and delivers it to each client through clientOutboundChannel.

### Publishing from a service with SimpMessagingTemplate

~~~java
@Component
public class NotificationPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishSystemNotice(String text) {
        messagingTemplate.convertAndSend(
                "/topic/notifications",
                new Notice(text)
        );
    }

    public record Notice(String text) {
    }
}
~~~

SimpMessagingTemplate sends the message to brokerChannel. Therefore, a service can publish notifications after an HTTP operation, a scheduled task, or a business event without needing to call each client's WebSocketSession directly.

### Configuring brokerChannel

In Java configuration, **MessageBrokerRegistry.configureBrokerChannel()** returns a ChannelRegistration to customize this channel:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");

    registry.configureBrokerChannel()
            .taskExecutor()
            .corePoolSize(2)
            .maxPoolSize(4)
            .queueCapacity(500);
}
~~~

You can register a ChannelInterceptor on brokerChannel to observe or enforce policies on messages published by the application. When configuring the executor, choose the queue capacity and pool size based on real load; do not set arbitrary limits without measuring throughput and latency.

brokerChannel is not where clients directly send STOMP frames. Messages sent in by clients are processed starting from clientInboundChannel; brokerChannel mainly serves the message-publishing flow originating on the server side.

## 4. clientOutboundChannel: the outbound path to WebSocket clients

When the broker finds matching subscriptions, it sends Spring Messages to clientOutboundChannel. Spring converts the messages into STOMP frames and writes them to the corresponding WebSocket sessions.

Server publish example:

~~~java
messagingTemplate.convertAndSend(
        "/topic/chat",
        new ChatMessage("server", "Someone has just joined the chat room")
);
~~~

Flow:

~~~text
SimpMessagingTemplate
       |
       v
brokerChannel
       |
       v
Message Broker
       |
       | find subscribers of /topic/chat
       v
clientOutboundChannel
       |
       | encode into STOMP MESSAGE
       v
Each client's WebSocket session
~~~

clientOutboundChannel typically carries messages sent by the broker to clients, including application data and responses related to STOMP processing. This is also a useful place to measure outbound traffic, observe errors, and detect slow-consuming clients.

### Tasks suited for the outbound channel

- Collecting metrics on the number of messages and bytes sent to clients.
- Recording send durations and transport errors.
- Applying header checks or transformations when truly needed.
- Observing pressure caused by slow clients or low-bandwidth networks.

Do not arbitrarily modify destinations, subscription IDs, or STOMP headers managed by the framework. Changing routing metadata can cause messages to reach the wrong session or no longer match the subscription.

## 5. Distinguishing destination prefixes from channels

This is an easy point of confusion when first learning Spring STOMP.

| Component | Example | Meaning |
|---|---|---|
| WebSocket endpoint | /ws | URL clients use for the WebSocket handshake. |
| Application destination prefix | /app | Prefix routing SENDs to @MessageMapping. |
| Broker destination prefix | /topic, /queue | Destination prefixes handled by the broker per configuration. |
| clientInboundChannel | Spring internal channel | Receives messages from clients. |
| brokerChannel | Spring internal channel | Passes messages from the application to the broker. |
| clientOutboundChannel | Spring internal channel | Passes messages sent out to clients. |

Example endpoint and broker configuration:

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

With this configuration:

- Clients connect over WebSocket to /ws.
- SEND to /app/chat is routed to @MessageMapping("/chat").
- SUBSCRIBE /topic/chat registers with the broker.
- Controllers or services publish to /topic/chat via brokerChannel.
- The broker sends messages to subscribers via clientOutboundChannel.

With the built-in simple broker, /topic and /queue are naming conventions to distinguish usage styles; they have no mandatory special meaning in the STOMP protocol. With an external broker relay, use destination prefixes supported by the actual broker.

## 6. Interceptors on each channel

Spring lets you register a **ChannelInterceptor** to observe or intercept messages in the processing flow. In STOMP over WebSocket, interceptors are usually registered through WebSocketMessageBrokerConfigurer.

| Location | Registration point | Common uses |
|---|---|---|
| Inbound | configureClientInboundChannel | Authentication, authorization, checking commands/destinations, tracing. |
| Broker | MessageBrokerRegistry.configureBrokerChannel() | Inspecting or measuring messages published by the server. |
| Outbound | configureClientOutboundChannel | Measuring outbound traffic, observing metadata and errors. |

### How does ChannelInterceptor work?

An interceptor can implement callbacks:

- **preSend:** runs before a message is sent into the channel. Return the message to continue; return null to block the message.
- **postSend:** runs after the send operation and receives whether the send succeeded.
- **afterSendCompletion:** runs after sending completes, even if an exception occurred.
- **preReceive / postReceive:** applies to channels with corresponding receive operations.

With STOMP, use **StompHeaderAccessor** to read the command, destination, session ID, user, and native headers.

### Example interceptor for inbound

~~~java
public class InboundTraceInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        StompHeaderAccessor accessor =
                StompHeaderAccessor.wrap(message);

        StompCommand command = accessor.getCommand();
        String destination = accessor.getDestination();
        String sessionId = accessor.getSessionId();

        // Can record metrics/tracing from command, destination, and sessionId.
        // Do not log full payloads or sensitive tokens.

        return message;
    }
}
~~~

Registration:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new InboundTraceInterceptor());
}
~~~

If an interceptor returns null from preSend, the message is dropped from the flow and downstream handlers do not receive it. Only do this when policy truly requires blocking; at the same time, design an appropriate error response so the client understands why.

### ExecutorChannelInterceptor

**ExecutorChannelInterceptor** extends ChannelInterceptor and provides callbacks that run on the processing thread of each MessageHandler subscribed to the channel. It is useful when you need to attach context or measure timing around each handler invocation.

ChannelInterceptor is called once for the operation of sending a message into the channel; ExecutorChannelInterceptor can be called per handler subscriber. Do not confuse these two callback scopes when counting messages or measuring latency.

### Authentication and Spring Security

A common pattern is handling STOMP CONNECT with an interceptor on clientInboundChannel, validating a token, and setting the Principal on the message through StompHeaderAccessor. Spring records the user for the session and attaches that user to subsequent messages.

If the application uses Spring Security message authorization, the authentication interceptor must execute before the authorization interceptor so that the user is already set when permissions are checked. Refer to the interceptor ordering configuration in the Spring Security documentation instead of assuming bean ordering.

## 7. Executor configuration and handling load

clientInboundChannel and clientOutboundChannel are backed by executors to run message handlers asynchronously. brokerChannel can also have an executor configured through MessageBrokerRegistry.

Example:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration
            .taskExecutor()
            .corePoolSize(4)
            .maxPoolSize(8)
            .queueCapacity(1000);
}

@Override
public void configureClientOutboundChannel(ChannelRegistration registration) {
    registration
            .taskExecutor()
            .corePoolSize(4)
            .maxPoolSize(8)
            .queueCapacity(1000);
}
~~~

The numbers above are only illustrative values. Choose them according to CPU, processing time, number of sessions, client speed, and the broker's load capacity.

### Core pool, max pool, and queue capacity

- **corePoolSize:** the number of core workers maintained.
- **maxPoolSize:** the maximum number of workers when the executor needs to scale up.
- **queueCapacity:** the number of tasks that can wait when no worker is free.

An important point about ThreadPoolExecutor: if the queue is unbounded, tasks are normally placed into the queue after core threads are busy, so maxPoolSize may not be used as expected. If you want the executor to scale up to maxPoolSize, choose a bounded queue capacity and understand the rejection policy when the queue is full.

### Inbound and outbound have different load characteristics

- **Inbound:** load mainly comes from the number of frames clients send and the processing time inside controllers/interceptors. If a handler makes synchronous database or HTTP calls, workers can be held for a long time.
- **Outbound:** load depends on the number of published messages and the write speed to each client. Slow clients or weak networks can cause buffers to grow.
- **Broker channel:** load comes from server-side controllers and services publishing. If the broker is slow or many messages are published concurrently, the channel's queue can grow.

Do not increase thread pools mechanically. Too many threads increase context switching and resource contention; too large a queue can hide overload conditions and cause latency to rise.

## 8. Message ordering and preserve order

Because inbound and outbound channels can use ThreadPoolExecutor, messages received in one order may be processed or sent out on different threads. The order observed at the client can differ from the original order.

Spring provides two separate settings:

### Preserving receive order from clients

In **registerStompEndpoints**, enable preserve receive order:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
    registry.setPreserveReceiveOrder(true);
}
~~~

This setting ensures that messages within the same WebSocket session are passed into clientInboundChannel one by one in the order received. It does not create global ordering across different client sessions.

### Preserving publish order to clients

In **configureMessageBroker**, enable preserve publish order:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

This setting causes messages within the same client session to be sent to clientOutboundChannel one message at a time in publish order. It has a performance cost, so enable it only when business logic requires it.

The two flags have different purposes:

| Setting | Where does it protect order? |
|---|---|
| setPreserveReceiveOrder(true) | Client → clientInboundChannel. |
| setPreservePublishOrder(true) | Broker → clientOutboundChannel → client. |

They do not guarantee global ordering across multiple clients, multiple server instances, or multiple independent publishers. If business logic requires ordering per aggregate, still use sequence numbers and idempotent handling.

## 9. Simple broker and external broker relay

The three channels still have similar roles whether using the built-in simple broker or an external STOMP broker. The difference is the component receiving messages on the broker side.

### Built-in simple broker

- The broker handler runs inside the Spring application.
- Subscriptions are managed in the application's memory.
- Suitable for development, testing, or small applications.
- Does not provide the full feature set of a dedicated broker.
- Not suitable for sharing subscription/message state across multiple application instances.

### External broker relay

- Spring forwards messages from brokerChannel to an external STOMP broker over TCP.
- The external broker manages subscriptions and broadcasting.
- Messages from the broker are brought back to Spring and then pass through clientOutboundChannel.
- Can scale out multiple application instances connecting to a shared broker.
- Destination capabilities, persistence, acknowledgment, and advanced features depend on the broker.

Flow with relay:

~~~text
WebSocket Client
      |
      v
clientInboundChannel
      |
      +---- /app ---> @MessageMapping
      |                    |
      |                    v
      |               brokerChannel
      |                    |
      |                    v
      |             STOMP Broker Relay
      |                    |
      |                    v
      |              External Broker
      |                    |
      |                    v
      +---------------- clientOutboundChannel
                           |
                           v
                       WebSocket
~~~

The broker relay maintains a dedicated system TCP connection for messages published by the server and separate TCP connections representing each WebSocket client. Configure credentials, virtual host, host/port, and heartbeat according to the actual broker. Using a relay does not eliminate Spring's three internal channels.

## 10. Combined example: receiving chat and publishing notifications

The example below combines the three channels with a controller, a service publisher, and an interceptor. These are Spring Framework integration components; the application needs a WebSocket endpoint, a message broker, and a running STOMP client.

### WebSocketConfig.java configuration

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.ChannelRegistration;
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
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setPreservePublishOrder(true);

        registry.configureBrokerChannel()
                .taskExecutor()
                .corePoolSize(2)
                .maxPoolSize(4)
                .queueCapacity(500);
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new InboundTraceInterceptor());
        registration.taskExecutor()
                .corePoolSize(4)
                .maxPoolSize(8)
                .queueCapacity(1000);
    }

    @Override
    public void configureClientOutboundChannel(ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(4)
                .maxPoolSize(8)
                .queueCapacity(1000);
    }
}
~~~

### ChatMessage.java

~~~java
package com.example.messaging;

public record ChatMessage(String sender, String text) {
}
~~~

### ChatController.java

~~~java
package com.example.messaging;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat")
    @SendTo("/topic/chat")
    public ChatMessage handle(ChatMessage message) {
        return message;
    }
}
~~~

### NotificationPublisher.java

~~~java
package com.example.messaging;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;

@Component
public class NotificationPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(String text) {
        messagingTemplate.convertAndSend(
                "/topic/notifications",
                new ChatMessage("system", text)
        );
    }
}
~~~

### InboundTraceInterceptor.java

~~~java
package com.example.messaging;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

public class InboundTraceInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);

        StompCommand command = accessor.getCommand();
        String destination = accessor.getDestination();
        String sessionId = accessor.getSessionId();

        // Feed command, destination, and sessionId into appropriate metrics/tracing.
        // Avoid logging tokens or full payloads.

        return message;
    }
}
~~~

### How clients use it

The client connects to the /ws endpoint, then subscribes and sends:

~~~text
SUBSCRIBE
id:chat-sub
destination:/topic/chat

^@

SEND
destination:/app/chat
content-type:application/json

{"sender":"Lan","text":"Hello"}^@
~~~

Flow result:

1. STOMP SEND is decoded and enters clientInboundChannel.
2. InboundTraceInterceptor observes the command and destination.
3. The /app prefix routes to ChatController.handle.
4. The return value is sent through brokerChannel to the broker.
5. The broker finds subscribers of /topic/chat.
6. The message is sent through clientOutboundChannel and encoded into a STOMP MESSAGE.
7. Subscribed clients receive the chat content.

If a service calls NotificationPublisher.publish, the message goes straight from the application through brokerChannel, and then the broker distributes it out to clientOutboundChannel. This flow does not require a client to send a SEND first.

This is an integration example with no fixed stdout. Results are observed via connected and subscribed STOMP clients; the application needs the Spring WebSocket/Messaging dependencies configured and an appropriate WebSocket runtime environment.

## 11. Monitoring and diagnosing channels

Spring provides statistics for the message broker and related executors. You can use **WebSocketMessageBrokerStats** to monitor session counts, frames, transport errors, and thread pool statistics.

Some indicators:

| Indicator | Where to check | Possibilities to investigate |
|---|---|---|
| Inbound task queue growing | clientInboundChannel | Slow controller/interceptor processing, blocking database/HTTP calls, or pool too small. |
| Outbound task queue growing | clientOutboundChannel | Slow client, weak network, overly large messages, or high publish rate. |
| Send timeout or growing buffer | WebSocket transport | Client not consuming fast enough; check sendTimeLimit and sendBufferSizeLimit. |
| Slow broker publishing | brokerChannel and broker relay | Broker overloaded, slow TCP, or brokerChannel queue backed up. |
| Client not receiving messages | Inbound → broker → outbound | Check destination prefixes, subscriptions, authorization, and broker status. |
| Message reaching wrong handler | clientInboundChannel | Check applicationDestinationPrefixes and broker destination prefixes. |

When outbound is slow, increasing the thread pool does not always solve the problem. Spring WebSocket transport has sendTimeLimit and sendBufferSizeLimit to cap send time and buffered data for a client.

With multiple application instances, the simple broker does not share state across instances. If a client connects to instance A while a publisher runs on instance B, you need an external broker relay or a suitable message-sharing mechanism.

## 12. Common mistakes

1. **Confusing channels with destinations.** clientInboundChannel is a Spring internal path; /app/chat and /topic/chat are routed destinations.
2. **Assuming every message sent by a client goes through brokerChannel.** Client frames enter clientInboundChannel; frames are routed directly to the broker or controller depending on destination/command.
3. **Assuming controller return values are sent directly to WebSocket.** Return values are normally converted into Spring Messages and sent via brokerChannel for the broker to distribute.
4. **Using clientOutboundChannel to publish from a service.** Services should use SimpMessagingTemplate; the template sends through brokerChannel.
5. **Not distinguishing /app from /topic.** /app typically routes to @MessageMapping; /topic and /queue typically route to the broker per configuration.
6. **Registering an interceptor on the wrong channel.** Authentication/authorization for client frames usually belongs on inbound; inspecting server-published messages belongs on brokerChannel; measuring outbound sends belongs on outbound.
7. **Blocking a message but forgetting to return an error.** Returning null from preSend stops the message at the channel; the client may not know why the action was not processed.
8. **Putting long blocking work in an inbound interceptor.** Workers are held, increasing queues and latency across the whole endpoint.
9. **Increasing maxPoolSize while keeping an unbounded queue.** The executor may keep queuing tasks and not scale up to maxPoolSize as expected.
10. **Enabling preserve order and thinking the whole system has FIFO.** The two flags only protect ordering within the same session at their respective stages; they do not create global ordering across clients or instances.
11. **Using the simple broker for multiple instances.** The simple broker stores subscriptions in memory on a single instance; use a broker relay when sharing across multiple nodes is needed.
12. **Ignoring outbound backpressure.** Slow clients can cause send buffers and executor queues to grow; monitor timeouts, buffers, and publish rates.
13. **Arbitrarily modifying STOMP headers on outbound.** Changing destination or subscription metadata can prevent messages from reaching the right client.
14. **Using ChannelInterceptor as a business handler.** Interceptors suit cross-cutting concerns; business logic should reside in controllers/services for easier testing and transaction management.

## 13. Key takeaways

- **clientInboundChannel** receives STOMP messages from WebSocket clients after Spring decodes frames.
- **brokerChannel** carries messages created by server-side code to the message broker.
- **clientOutboundChannel** carries messages from the broker/server to WebSocket clients.
- Destination prefixes such as /app, /topic, and /queue determine routing; channel names are Spring internal infrastructure.
- Client SENDs to /app are usually handled by @MessageMapping; SUBSCRIBEs to /topic or /queue are managed by the broker.
- Controller return values and SimpMessagingTemplate publish via brokerChannel.
- ChannelInterceptor is used for tracing, authentication, authorization, and message inspection; ExecutorChannelInterceptor has callbacks per MessageHandler.
- WebSocketMessageBrokerConfigurer configures inbound/outbound channels; MessageBrokerRegistry.configureBrokerChannel() configures brokerChannel.
- Executors, queue capacities, and send buffers must be chosen according to workload and measured in practice.
- setPreserveReceiveOrder and setPreservePublishOrder protect ordering within the same session at two different stages, at a performance cost.
- The simple broker fits simple applications; the broker relay connects to an external broker and supports sharing messages across multiple application instances.

When debugging a STOMP message, trace through the exact three stages: clientInboundChannel to see where the message enters, brokerChannel to see how the application publishes, and clientOutboundChannel to see which client the broker delivers the message to. This trace approach helps isolate routing, processing, and delivery issues faster.

## References

- [Spring Framework 6.2.19 — Flow of Messages](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html)
- [Spring Framework 6.2 — Enable STOMP](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/enable.html)
- [Spring Framework 6.2 — Interception](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/interceptors.html)
- [Spring Framework 6.2 — Order of Messages](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/ordered-messages.html)
- [Spring Framework 6.2 — Performance](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/configuration-performance.html)
- [Spring Framework 6.2 — WebSocketMessageBrokerConfigurer API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketMessageBrokerConfigurer.html)
- [Spring Framework 6.2 — MessageBrokerRegistry API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [Spring Framework 6.2 — ChannelRegistration API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/config/ChannelRegistration.html)
