# Distinguishing /topic and /queue naming conventions from actual broker semantics

In STOMP, the value of the destination header is a string that the client sends to the server. Names such as **/topic/prices** or **/queue/orders** are very common, but the STOMP protocol itself does not require every server to interpret these two prefixes in the same way. STOMP 1.2 treats a destination as an opaque string and leaves both the syntax and the delivery semantics for each server/broker to decide.

That means the same STOMP frame can lead to different behavior when running with the Spring simple broker, the RabbitMQ STOMP plugin, or ActiveMQ Classic. A destination name only has meaning when you know which adapter/broker is handling it, how the broker is configured, and whether the client uses SEND or SUBSCRIBE.

This lesson distinguishes three layers: naming conventions in the application, how Spring routes destinations, and the actual semantics provided by the broker. This is a key point to grasp before designing queues, topics, durable subscriptions, competing consumers, or systems that require message guarantees.

## 1. STOMP does not define a fixed meaning for /topic and /queue

STOMP is an application-layer messaging protocol. A SEND frame has a destination header to indicate where to send the message; a SUBSCRIBE frame uses destination to register to receive messages.

Example:

~~~text
SEND
destination:/queue/orders
content-type:application/json

{"orderId":"ORD-42","event":"created"}^@
~~~

Or:

~~~text
SUBSCRIBE
id:prices-sub
destination:/topic/prices
ack:auto

^@
~~~

In STOMP 1.2, destination is an opaque string. The protocol does not require the server to have queues or topics, nor does it mandate a delivery model for names with the /queue or /topic prefix. The destination syntax and message exchange semantics depend on the server.

STOMP standardizes commands and several headers, such as SEND, SUBSCRIBE, ACK, NACK, RECEIPT, content-type, and content-length. It does not standardize the operational properties of a specific destination such as:

- Whether the destination is a queue, topic, exchange, address, or a logical name.
- Whether a message is delivered to one consumer or copied to multiple subscribers.
- Whether a message is retained when there is no subscriber or discarded.
- Whether a subscription is durable or exists only while the client is connected.
- Whether a queue/topic is created automatically on SEND or SUBSCRIBE or must exist beforehand.
- Whether messages are persistent, or have TTL, priority, dead-letter, or replay.
- At what level ACK, redelivery, and transactions are implemented.

Therefore, do not infer semantics solely from the destination string. You need to read the documentation of the actual broker's STOMP adapter and check the deployment configuration.

## 2. /topic and /queue are common naming conventions

In many messaging systems:

- A **Topic** represents publish-subscribe: one publisher sends one message, and the broker can make copies for multiple subscriptions.
- A **Queue** represents point-to-point or competing consumers: multiple consumers read from the same queue, but each message is usually delivered to one consumer at a time.

Common conventions are:

- /topic/prices: price messages broadcast to multiple subscribers.
- /queue/orders: order messages distributed to one consumer in a worker group.

This is a naming style that is easy for developers to read. However, only a broker with the corresponding semantics turns that convention into real queue/topic behavior.

Three ideas must be distinguished:

1. **Destination name:** the string inside the STOMP header.
2. **Routing rules:** which handler, broker, or resource the server selects based on that string.
3. **Delivery semantics:** how the broker distributes, retains, acknowledges, and redelivers messages.

An application can use the /queue prefix in a destination name and still receive broadcasts if the broker simply broadcasts to every subscription with a matching destination. Conversely, a broker can use a different syntax to access a queue or exchange.

## 3. Spring simple broker: prefixes are only a routing convention

When enabling the built-in simple broker:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Spring uses prefixes to route messages:

- Destinations starting with /app are routed to @MessageMapping methods.
- Destinations starting with /topic or /queue are passed directly to the simple broker.

With the simple broker, /topic and /queue **have no special meaning regarding delivery**. They are only a convention for the development team to distinguish destinations normally used for pub-sub from destinations normally used for point-to-point.

The simple broker stores subscriptions in the application's memory. When a message is sent to a destination, the broker finds the subscriptions with a matching destination and broadcasts the message to those subscribers.

For example, two clients both SUBSCRIBE to /queue/orders on the simple broker. When the application sends a message to /queue/orders, both subscriptions match and both clients receive a copy. The simple broker does not turn /queue/orders into a queue with competing consumers just because of the prefix.

Similarly, /topic/prices is also broadcast to every matching subscription. With the simple broker, the difference between /topic and /queue lies mainly in the conventional meaning in code and prefix configuration.

### 3.1. When is the simple broker suitable?

The simple broker is suitable for small applications, demos, development environments, or real-time features with moderate requirements:

- Subscriptions are stored in the memory of a single Spring application instance.
- Messages are broadcast to connected clients that have a matching destination.
- There is no broker persistence to hold a backlog when the application stops.
- There is no competing-consumers queue mechanism like a dedicated message broker.
- It is not suitable for clustering subscriptions across multiple application instances.
- It supports only part of STOMP; for example, it does not support ACK and RECEIPT.

If you need a destination with real queue semantics, storing messages when consumers are offline, distributing across multiple workers, or redelivering after errors, use a dedicated broker through the broker relay.

### 3.2. Do not use misleading names

If using the simple broker, the destination /queue/orders can make readers think that messages are load-balanced among consumers. That does not happen just because the prefix is /queue.

You should agree on a convention within the team:

- Use /topic for destinations that are broadcast to subscribers.
- Use /queue for logical destinations that the application intends to process point-to-point.
- State clearly that with the simple broker, both still broadcast by subscription matching.
- If real queue semantics are needed, switch to a broker that supports queues and verify delivery behavior.

You can use names like /events/orders or /realtime/prices if you want to avoid implying queue/topic behavior that the broker does not provide.

## 4. Spring broker relay: destinations are forwarded to an external broker

When a dedicated broker is needed, Spring can relay STOMP frames to a STOMP-capable broker:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.example.com")
            .setRelayPort(61613)
            .setClientLogin("spring-client")
            .setClientPasscode("configured-secret");
}
~~~

In this configuration:

- /app is still the prefix for Spring to route messages to @MessageMapping.
- /topic and /queue are the prefixes Spring forwards to the broker relay.
- The external broker decides what resource the destination maps to and under what semantics messages are delivered.

Spring's broker relay does not automatically turn /queue into a queue in the same way across every broker. It forwards frames to the broker, and the broker handles the destination according to the specific adapter, configuration, and product.

For example, the RabbitMQ STOMP plugin and the ActiveMQ Classic STOMP connector both support /queue and /topic, but how destinations are mapped and several defaults differ.

## 5. RabbitMQ STOMP plugin: /queue and /topic have specific semantics

RabbitMQ provides a STOMP adapter through the rabbitmq_stomp plugin. The plugin defines several destination forms. Two common forms are /queue and /topic.

### 5.1. /queue/name in RabbitMQ

For a destination of the form /queue/orders:

- SUBSCRIBE creates or uses a shared queue named orders managed by the STOMP gateway.
- SEND sends messages into that queue.
- Multiple subscribers registering on the queue compete to receive messages.
- Each message is delivered to at most one subscriber at a time.
- When there is no subscriber, messages can be held in the queue waiting for a consumer to connect.
- If queue arguments are not specified, the default queue is described as durable, non-exclusive, and non-auto-delete.

This is the queue/competing-consumers semantics that many people expect when they see the /queue prefix. However, this is the behavior of the RabbitMQ STOMP plugin, not a general requirement of STOMP.

RabbitMQ also has /amq/queue/name to access a queue already created outside the STOMP gateway. For SUBSCRIBE, the queue must exist; the adapter does not create a new queue for this destination form.

### 5.2. /topic/name in RabbitMQ

For a destination of the form /topic/prices:

- SEND publishes the message to the default amq.topic exchange with the corresponding routing key.
- SUBSCRIBE creates a separate queue for the current subscription and binds that queue to the exchange.
- Each subscriber has its own queue, so every active subscriber can receive a copy.
- The subscription queue defaults to auto-delete and non-durable.
- If there is no active subscriber, messages sent to the topic may be discarded.

This differs from a queue: a topic usually fans out to subscribers, whereas a queue splits messages among competing consumers.

RabbitMQ also supports the /exchange/exchange-name/routing-key form to send directly to an exchange and register binding patterns. If you need to use an existing queue, distinguish /queue and /amq/queue according to the plugin documentation.

### 5.3. A durable queue and a persistent message are two different concepts

A queue declared durable does not automatically mean every message sent to it is persistent. Queue durability relates to whether the queue definition survives a broker restart; message persistence relates to whether the broker stores the message according to the delivery mode and configuration.

Both must be checked:

- Is the queue/exchange durable?
- Is the message persistent?
- Does the broker confirm that the publish was accepted?
- Which ack mode does the consumer use?
- Are unACKed messages redelivered when the consumer disconnects?
- Are there TTL, dead-letter exchanges, or queue limits?

Do not treat the name /queue as proof that messages are durably stored.

## 6. ActiveMQ Classic STOMP: prefixes are stripped before mapping to JMS destinations

ActiveMQ Classic has a STOMP connector and maps STOMP destinations to JMS destinations.

According to the default rules:

- /queue/FOO.BAR is mapped to a JMS Queue named FOO.BAR.
- /topic/FOO.BAR is mapped to a JMS Topic named FOO.BAR.
- The /queue/ or /topic/ prefix is stripped before passing the destination name to ActiveMQ.

For example, a client sends:

~~~text
SEND
destination:/queue/ORDERS.CREATED

OrderCreated^@
~~~

ActiveMQ Classic treats this as the JMS Queue ORDERS.CREATED. If sent to /topic/ORDERS.CREATED, it is mapped to the JMS Topic ORDERS.CREATED.

ActiveMQ Classic has an important difference regarding persistence: STOMP messages are non-persistent by default. To send a persistent message, the client needs to add a header:

~~~text
SEND
destination:/queue/ORDERS.CREATED
persistent:true

OrderCreated^@
~~~

Therefore, even when the destination is /queue, a message can still be non-persistent by the STOMP connector's default. This is a clear example showing that queue semantics and message persistence must be checked separately.

ActiveMQ Classic also supports several extension headers to map JMS properties, such as correlation-id, expires, priority, reply-to, JMSXGroupID, and selector. These extensions belong to ActiveMQ's implementation; not every STOMP broker supports them the same way.

## 7. Comparing the same destination across brokers

The table below shows that the same destination string can lead to different behavior:

| Destination | Spring simple broker | RabbitMQ STOMP plugin | ActiveMQ Classic STOMP |
|---|---|---|---|
| /queue/orders | Matching subscriptions receive broadcasts; no competing-consumer queue just from the prefix | Shared queue; a message is delivered to at most one subscriber | JMS Queue named orders |
| /topic/prices | Matching subscriptions receive broadcasts | Exchange amq.topic; each subscription has its own queue and receives a copy | JMS Topic named prices |
| Messages when there is no subscriber | Simple broker only holds subscriptions in memory; not a persistent queue | Queue holds messages per queue config; topic with no active subscriber may drop messages | Queue/topic and durable subscriptions follow JMS/ActiveMQ config |
| Message persistence | No built-in broker persistence | Depends on queue/message flags and broker config | STOMP is non-persistent by default; use persistent:true to request persistence |
| Clustering | Simple broker does not share subscriptions across instances | Depends on RabbitMQ cluster and configuration | Depends on ActiveMQ deployment/topology |

This table is a comparison guide for commonly seen default configurations. A broker can be customized through policies, queue arguments, plugin settings, or destination resolvers. Always confirm the actual version and configuration before relying on a specific semantics.

## 8. SEND and SUBSCRIBE can have different destination creation rules

A destination is not necessarily created in the same way when a client sends SEND and when a client registers SUBSCRIBE.

RabbitMQ example:

- SEND to /queue/orders can create the shared queue the first time in the session according to the STOMP gateway's rules.
- SUBSCRIBE to /queue/orders registers a consumer on that shared queue.
- SUBSCRIBE to /topic/prices creates a separate queue for the subscription and binds the queue to the exchange.
- SEND to /topic/prices publishes to the exchange; if there is no matching binding/subscriber, the message may not be retained.

With /exchange/orders/created, RabbitMQ can publish to the orders exchange with routing key created. When SUBSCRIBING to the same destination, the adapter can create a separate queue and bind by pattern. That is why you need to read both the SEND and SUBSCRIBE rules in the broker documentation.

With ActiveMQ Classic, the prefix is stripped to create a JMS Queue or Topic; destinations can be created according to broker policy and user permissions. Do not assume every adapter has the same auto-create behavior.

## 9. A durable subscription is not synonymous with an ordinary /topic

An ordinary topic subscription may exist only while the client is connected. If the client disconnects, messages published during that time may not be kept for the client.

A durable subscription provides a long-lived subscription identifier so that the broker retains messages for the subscriber even when the client is offline, depending on configuration and broker semantics. When the client reconnects and re-registers the exact durable subscription, it can receive the waiting messages.

You need to determine:

- By which header or configuration is a durable subscription named?
- Is the subscription tied to a client ID, user, or session?
- Can multiple consumers read from the same durable subscription?
- On unsubscribe, is the subscription detached or deleted completely?
- How long are messages retained and under what TTL/policy are they deleted?
- Are there backlog limits and dead-lettering?

There is no general rule that adding the /topic prefix creates a durable subscription. For example, RabbitMQ configures durable topics differently from ActiveMQ Classic and other STOMP brokers.

## 10. /user and Spring's logical destinations

Spring also has a user destination prefix, which defaults to /user. This is a logical routing layer for sending messages to an authenticated user or a specific session.

Example:

~~~java
messagingTemplate.convertAndSendToUser(
        username,
        "/queue/notifications",
        notification
);
~~~

Spring resolves a user destination into a separate destination for that user's session. The string /user/queue/notifications that the client subscribes to is not necessarily a physical queue named user/queue/notifications in the broker.

If using a broker relay, Spring can forward the resolved destination to the broker. In that case, the final semantics still depend on the broker. Distinguish:

- /user is Spring's logical prefix.
- /queue is a convention or a broker-specific destination prefix.
- The physical queue name is created or selected according to the broker's rules and Spring's user destination resolver.

Do not use /user as an authorization measure. The server must still authenticate the Principal and check whether the user has permission to send/receive the corresponding destination.

## 11. Designing destinations to reduce confusion

A good convention should express both the domain and the desired delivery type:

| Purpose | Example name | What to verify |
|---|---|---|
| Broadcast real-time prices | /topic/prices | Fan-out; do new subscribers receive old messages? |
| Distribute jobs to workers | /queue/orders | Competing consumers, persistence, ACK, and redelivery |
| Domain events | /topic/orders.created | Should one or many subscribers receive copies? |
| Request/reply | /temp-queue/replies | How are temporary destinations and reply-to supported by the broker? |
| User notifications | /user/queue/notifications | How does Spring resolve user/session and how does the broker handle the final destination? |
| Key-based routing | /exchange/events/order.created | Broker exchange, routing key, and binding pattern |

Document destination conventions clearly in the integration specification:

- Which prefix is a Spring application destination?
- Which prefix is forwarded directly to the broker?
- Are destination names auto-created?
- Do SEND and SUBSCRIBE use the same resource or different ones?
- Is the queue/topic durable?
- Are messages persistent?
- What are the ACK mode, redelivery, and dead-letter policies?
- Does the destination restrict publish/subscribe permissions per user?

When switching brokers, do not just swap the connection URL and keep the same delivery assumptions. Review destination mapping, queue declarations, subscriptions, persistence, ACK, and redelivery.

## 12. Security and destination access permissions

A destination is data sent by the client in a STOMP frame. You should not trust that a client is allowed to SEND or SUBSCRIBE just because it uses a valid prefix.

Authorize separately:

- **SEND:** which users are allowed to publish to /app or which broker destinations?
- **SUBSCRIBE:** which users are allowed to read which /topic, /queue, or user destinations?
- **Destination ownership:** can a user access resources belonging to another tenant?
- **Broker credentials:** the Spring relay uses its own credentials; clients should not receive broader broker permissions than needed.
- **Destination creation:** can a client create arbitrary queues/topics?
- **Resource limits:** limit the number of queues, subscriptions, consumers, and message sizes.

With Spring Security, you can check message types and destinations through message authorization rules. With an external broker, add ACLs at the broker to restrict SEND/SUBSCRIBE permissions and destination creation. Protecting at both Spring and the broker helps prevent another access path from bypassing the application's policy.

## 13. Java 17 example: same destination, three interpretations

The following example simulates how three implementations interpret the same destination. It uses plain JDK, does not connect to a broker, and does not create real queues/topics. The purpose is to show that prefixes do not automatically carry universal semantics across every server.

Create the file **StompDestinationSemanticsDemo.java**:

~~~java
public class StompDestinationSemanticsDemo {

    record Interpretation(
            String implementation,
            String destination,
            String resource,
            String delivery,
            String persistence) {}

    static Interpretation springSimpleBroker(
            String destination,
            int matchingSubscribers) {

        requireSupported(destination);

        return new Interpretation(
                "Spring simple broker",
                destination,
                "in-memory subscription destination",
                "broadcast to " + matchingSubscribers
                        + " matching subscriber(s)",
                "no broker persistence"
        );
    }

    static Interpretation rabbitMq(String destination) {
        if (destination.startsWith("/queue/")) {
            String name = destination.substring("/queue/".length());

            return new Interpretation(
                    "RabbitMQ STOMP",
                    destination,
                    "shared queue " + name,
                    "competing consumers; at most one subscriber per message",
                    "queue defaults durable; message persistence is separate"
            );
        }

        if (destination.startsWith("/topic/")) {
            String name = destination.substring("/topic/".length());

            return new Interpretation(
                    "RabbitMQ STOMP",
                    destination,
                    "amq.topic exchange with routing key " + name,
                    "one subscription queue per subscriber; fan-out copies",
                    "subscription queue defaults non-durable and auto-delete"
            );
        }

        throw new IllegalArgumentException(
                "Demo supports only /queue/ and /topic/: " + destination);
    }

    static Interpretation activeMqClassic(String destination) {
        if (destination.startsWith("/queue/")) {
            String jmsName = destination.substring("/queue/".length());

            return new Interpretation(
                    "ActiveMQ Classic STOMP",
                    destination,
                    "JMS Queue " + jmsName,
                    "queue delivery to competing consumers",
                    "STOMP message non-persistent by default"
            );
        }

        if (destination.startsWith("/topic/")) {
            String jmsName = destination.substring("/topic/".length());

            return new Interpretation(
                    "ActiveMQ Classic STOMP",
                    destination,
                    "JMS Topic " + jmsName,
                    "topic fan-out to subscriptions",
                    "STOMP message non-persistent by default"
            );
        }

        throw new IllegalArgumentException(
                "Demo supports only /queue/ and /topic/: " + destination);
    }

    private static void requireSupported(String destination) {
        if (!destination.startsWith("/queue/")
                && !destination.startsWith("/topic/")) {
            throw new IllegalArgumentException(
                    "Unsupported destination: " + destination);
        }
    }

    private static void print(Interpretation result) {
        System.out.println(result.implementation()
                + " | " + result.destination()
                + " | " + result.resource()
                + " | " + result.delivery()
                + " | " + result.persistence());
    }

    public static void main(String[] args) {
        String queueDestination = "/queue/orders";
        String topicDestination = "/topic/prices";

        print(springSimpleBroker(queueDestination, 2));
        print(springSimpleBroker(topicDestination, 2));

        print(rabbitMq(queueDestination));
        print(rabbitMq(topicDestination));

        print(activeMqClassic(queueDestination));
        print(activeMqClassic(topicDestination));
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac StompDestinationSemanticsDemo.java
java StompDestinationSemanticsDemo
~~~

Output:

~~~text
Spring simple broker | /queue/orders | in-memory subscription destination | broadcast to 2 matching subscriber(s) | no broker persistence
Spring simple broker | /topic/prices | in-memory subscription destination | broadcast to 2 matching subscriber(s) | no broker persistence
RabbitMQ STOMP | /queue/orders | shared queue orders | competing consumers; at most one subscriber per message | queue defaults durable; message persistence is separate
RabbitMQ STOMP | /topic/prices | amq.topic exchange with routing key prices | one subscription queue per subscriber; fan-out copies | subscription queue defaults non-durable and auto-delete
ActiveMQ Classic STOMP | /queue/orders | JMS Queue orders | queue delivery to competing consumers | STOMP message non-persistent by default
ActiveMQ Classic STOMP | /topic/prices | JMS Topic prices | topic fan-out to subscriptions | STOMP message non-persistent by default
~~~

The output illustrates the rules described in each implementation's documentation. It does not prove that a running broker has the same configuration; queue durability, message persistence, auto-delete, acknowledgement, and redelivery must be tested in the actual environment.

## 14. Procedure for verifying semantics before integrating

When integrating a STOMP broker or switching brokers, follow these steps:

1. Record the broker version, STOMP plugin/adapter, and Spring version.
2. Read the official destination syntax of the adapter.
3. Check SEND and SUBSCRIBE behavior separately.
4. Determine whether destinations are created automatically or must be declared beforehand.
5. Create two subscribers subscribing to the same /queue and send multiple messages; confirm whether messages are split among consumers or broadcast to both.
6. Create two subscribers subscribing to the same /topic; confirm whether each subscriber receives a copy.
7. Disconnect all subscribers and then send a message; check whether the message is retained, expires, or is discarded.
8. Restart the broker; check whether queues, subscriptions, and messages are recovered.
9. Disconnect a consumer before ACK; confirm redelivery and delivery count.
10. Check persistent messages, receipt/publisher confirms, TTL, and dead-letter.
11. Check ACLs for SEND, SUBSCRIBE, and destination creation.
12. Record the results as a contract so that clients and producers use the same semantics.

An integration test should run against a real broker or a matching broker container. A unit test that only checks the destination string cannot prove the broker's delivery semantics.

## 15. Key takeaways

STOMP only standardizes destination as a string and leaves it to the server to decide syntax and delivery semantics. /topic and /queue are common conventions, not mandatory STOMP rules.

Spring's simple broker uses prefixes to choose routing paths and broadcasts to matching subscriptions; /queue does not automatically become a competing-consumer queue. The RabbitMQ STOMP plugin maps /queue and /topic to queues/exchanges with RabbitMQ-specific semantics. ActiveMQ Classic strips the prefix and maps to a JMS Queue or Topic, while STOMP messages are non-persistent by default.

When designing a system, verify destination mapping, queue/topic behavior, persistence, ACK, redelivery, durable subscriptions, and ACLs on the actual broker. Destination names should express the application's intent, while real guarantees must come from the implementation's configuration and contract.

## References

- [STOMP 1.2 Specification – Protocol Overview and Destinations](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework – STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework – Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework – Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework – External Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [RabbitMQ – STOMP Plugin and Destinations](https://www.rabbitmq.com/docs/stomp)
- [ActiveMQ Classic – STOMP Destinations and Persistence](https://activemq.apache.org/components/classic/documentation/stomp)