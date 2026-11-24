# TemporaryQueue and TemporaryTopic in JMS / Spring JMS

## 1. Purpose: What Problem Do Temporary Destinations Solve?

In JMS (Java Message Service, now standardized as **Jakarta Messaging**), applications typically send or receive messages via two types of `Destination`:

- **`Queue`**: a point-to-point channel where a message is normally handed to one eligible consumer.
- **`Topic`**: a publish/subscribe channel where valid subscriptions can receive copies of published messages.

Normally queues/topics are long-lived destinations provisioned by broker administrators or infrastructure configuration. However, there are cases where an application needs an **isolated, short-lived** reply endpoint serving only one client or one exchange session. JMS provides two specialized interfaces:

- **`TemporaryQueue extends Queue`**: a temporary queue.
- **`TemporaryTopic extends Topic`**: a temporary topic.

These two destinations are created by the provider with a unique identity scoped to a connection, live for **the lifetime of the connection that created them**, and have a special ownership rule: **only the connection that created the destination may create consumers on it; producers on other connections can still send to the destination.** Therefore, they are very useful for the **request–reply** pattern: the requester creates a temporary reply mailbox, sends that mailbox address via the `JMSReplyTo` header, and the processor sends the result back there.

These are **real destinations managed by the JMS provider/broker**, not merely Java objects in memory. Creating many temporary destinations can consume broker resources; consumers must be closed and destinations deleted promptly when no longer needed.

### Quick Visualization

~~~text
Request client (connection A)                     Reply service (connection B)
┌─────────────────────────────────┐                ┌─────────────────────────────┐
│ Create TemporaryQueue reply-A   │                │ Consume from requests.queue │
│ Consumer only created by A      │                │                             │
│ Send request to requests.queue ─┼───────────────>│ Read payload + JMSReplyTo   │
│   JMSReplyTo = reply-A          │                │ Create response             │
│                                 │<───────────────┼─ Send response to reply-A   │
│ Receive response from reply-A   │                │ (B is allowed to PRODUCE)   │
│ Close consumer, delete reply-A  │                └─────────────────────────────┘
└─────────────────────────────────┘
~~~

**Distinction**: connection B **may send** to `reply-A`, but **may not create its own consumer** to read from it. This protects the owner's receiving model, though it does not replace broker security authorization.

## 2. Detailed Comparison of TemporaryQueue and TemporaryTopic

| Criterion | `TemporaryQueue` | `TemporaryTopic` |
| --- | --- | --- |
| Parent type | `Queue` | `Topic` |
| Distribution semantics | Point-to-point: a message is delivered to one consumer among competing consumers on the queue | Publish/subscribe: matching subscriptions can receive messages |
| Created via classic API | `Session.createTemporaryQueue()` | `Session.createTemporaryTopic()` |
| Created via simplified API | `JMSContext.createTemporaryQueue()` | `JMSContext.createTemporaryTopic()` |
| Who may create consumers? | Owning connection only | Owning connection only |
| Who may send messages? | Producers on the owning connection or another connection, if permitted by the broker | Producers on the owning connection or another connection, if permitted by the broker |
| Lifetime | Tied to the creating connection, or deleted early via `delete()` | Same |
| Typical use case | A temporary reply address for single-result request–reply | Broadcasting temporary events to subscriptions scoped to the owning connection |
| Durable subscription? | Not applicable in the Topic sense | **Do not create durable subscriptions** on temporary topics; durable semantics contradict temporary nature |
| Deletion API | `TemporaryQueue.delete()` | `TemporaryTopic.delete()` |

Do not infer from the word "temporary" that it means "no persistence at any layer" or "messages are guaranteed to be received before ending". The specification speaks to **the existence scope of the destination**; broker policies, delivery mode, message expiration, connections, network failures, and transactions still affect delivery. If the owning connection closes before the reply arrives, the destination disappears and the reply message may fail or fail to reach the client depending on the provider.

### 2.1. A TemporaryQueue Is Not a Randomly Named Queue

Compare two different operations:

~~~java
Queue namedQueue = context.createQueue("reply.order.123");
TemporaryQueue realTemporaryQueue = context.createTemporaryQueue();
~~~

`createQueue("reply.order.123")` creates a **Queue object representing the destination name**, which does not mean JMS just created a temporary queue on the broker. Whether the broker auto-creates queues by name or requires admin provisioning depends on the provider/configuration. Meanwhile, `createTemporaryQueue()` instructs the provider to create a temporary destination with specification-defined lifetime/ownership rules.

Similarly: `createTopic("news")` differs from `createTemporaryTopic()`. Simply adding a prefix like `temp.` to a queue/topic name usually **does not grant** the special consumer/lifecycle rules of `TemporaryQueue` or `TemporaryTopic`.

### 2.2. Lifetime Is Based on Connection, Not Session

Classic JMS uses a `Connection` containing one or more `Session`s. The call to create a temporary destination is typically invoked on a `Session`, yet its existence scope is **the entire connection**.

- Session S1 on connection A creates temporary queue T.
- Session S2 **also on connection A** can create a consumer to read T (subject to JMS session usage rules).
- A Session on connection B is not permitted to create a consumer on T.
- Connection B can still create a producer to send messages to T, given permissions and while the destination still exists.
- Closing S1 **does not automatically delete** T because connection A may still be open; delete T via `delete()` or by closing **connection A**.
- `JMSContext` in the simplified API manages the underlying connection/session; closing the context that created the destination may close the associated connection depending on context/provider relationships. Do not carry a temporary destination reference over to a new connection after reconnect and expect it to remain valid.

JMS standardizes consumer creation permissions by connection. With connection pooling, caching, and failover, **do not infer from Java beans or wrapper objects that two operations share the same physical connection**: inspect `ConnectionFactory` configuration and actual resource lifecycles.

## 3. Creating, Using, and Deleting with the Jakarta Messaging API

The examples use `jakarta.jms.*`, matching the **Jakarta Messaging 3.x / Spring Framework 6+ / Spring Boot 3+** generation. Legacy Spring/JMS projects may use `javax.jms.*`; do not mix the two interface sets in the same provider without a supported conversion mechanism.

### 3.1. Classic API: Understanding Connection and Session

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TemporaryTopic;

// An illustrative method, taking an already configured ConnectionFactory.
// This is not a standalone runnable Java file.
static void showCreation(ConnectionFactory factory) throws JMSException {
    try (Connection connection = factory.createConnection()) {
        try (Session session =
                 connection.createSession(false, Session.AUTO_ACKNOWLEDGE)) {
            TemporaryQueue replyQueue = session.createTemporaryQueue();
            TemporaryTopic eventTopic = session.createTemporaryTopic();
            try {
                // Before reading, a consumer and connection.start() are needed.
                // replyQueue/eventTopic can be passed via JMSReplyTo.
            } finally {
                // All consumers using the destination must be closed before deleting.
                replyQueue.delete();
                eventTopic.delete();
            }
        }
    }  // Closing the connection also terminates any remaining temporary destinations.
}
~~~

Explanation:

1. `factory` must have a **JMS provider implementation** and broker connection configuration; adding the API jar alone is not enough to run.
2. `Connection` represents the owning context. Session is a convenient place to create temporary queues/topics, but does not independently "own" the destination's lifetime.
3. If there is an active `MessageConsumer` or `JMSConsumer` using the destination, **close the consumer before calling `delete()`**; per the API, deleting while a receiver/subscriber is still using it can raise `JMSException`.
4. Only call `connection.start()` when actually starting to receive messages with the classic API; if forgotten, receive calls may block even when the broker already holds messages.
5. `try-with-resources` guarantees closing the session and connection even upon exceptions, though for long-lived connections using temporary destinations, delete intentionally and early when finished.

The snippet above does not send/receive so `connection.start()` is not needed; the condition in step 4 applies to programs with consumers.

### 3.2. Simplified API: Small Hands-On with TemporaryQueue

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.TemporaryQueue;

// Method snippet that can be placed in a class, with factory from provider.
// Requires a running broker and appropriate send/receive permissions.
static String temporaryQueueRoundTrip(ConnectionFactory factory)
        throws JMSException {
    try (JMSContext owner = factory.createContext();
         JMSContext other = factory.createContext()) {

        TemporaryQueue replyQueue = owner.createTemporaryQueue();
        try (JMSConsumer replyConsumer = owner.createConsumer(replyQueue)) {
            // Simplified: other simulates a service sending a reply.
            other.createProducer().send(replyQueue, "response-42");

            // Owner can receive; wait at most 3 seconds.
            return replyConsumer.receiveBody(String.class, 3_000);
        } finally {
            // Consumer is already closed upon leaving try-with-resources.
            replyQueue.delete();
        }
    }
}
~~~

If the broker is available and the message is delivered within the limit, the method returns `"response-42"`; if 3 seconds elapse, it returns `null`. This example verifies that **a producer from another context can send to a temporary queue**, while the consumer belongs to the owning context. `JMSContext` starts the connection automatically by default when receiving messages; calling `start()` is not required in this default situation.

Note on pooling: two `JMSContext`s do not necessarily correspond to two independent physical connections in every wrapper implementation. Regardless of how pooling is optimized, the "only the owning connection may consume" rule remains a constraint at the JMS layer.

### 3.3. Simplified API: Using TemporaryTopic

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.TemporaryTopic;

// Illustrative method snippet; requires a valid provider ConnectionFactory.
static String temporaryTopicExample(ConnectionFactory factory)
        throws JMSException {
    try (JMSContext subscriberContext = factory.createContext();
         JMSContext publisherContext = factory.createContext()) {

        TemporaryTopic topic = subscriberContext.createTemporaryTopic();
        try (JMSConsumer subscriber = subscriberContext.createConsumer(topic)) {
            // Another producer sends to the shared topic address.
            publisherContext.createProducer().send(topic, "notice-42");

            // With a message being published and the subscriber already existing,
            // the owner-side subscriber can receive the notice.
            return subscriber.receiveBody(String.class, 3_000);
        } finally {
            topic.delete();
        }
    }
}
~~~

If the message arrives before timeout, the result is `"notice-42"`; otherwise, `null`. Unlike a queue, a temporary topic can have **multiple valid consumers/subscriptions within the owning connection's scope**, and each subscription can receive a copy of the message under pub/sub rules. Do not create durable subscriptions on this destination: it is designed to vanish when the connection ends its lifecycle.

**Snippets 3.2 and 3.3 are methods, not standalone `main` programs.** To run, the application must have a real `ConnectionFactory`, provider dependencies, a broker, and access permissions. Section 5 has a complete Spring Boot project to run the common request–reply pattern.

## 4. Request–Reply with TemporaryQueue

### 4.1. Step-by-Step Flow

Suppose an `OrderClient` service wants to ask `OrderWorker` for an order's status:

1. The requester keeps connection A open, creates `TemporaryQueue` `replyDestination`, and creates a consumer waiting for the reply.
2. The requester creates a `TextMessage` request, sets `request.setJMSReplyTo(replyDestination)`, and sends it to the fixed queue `orders.requests`.
3. The service on connection B receives the request and reads `request.getJMSReplyTo()`.
4. The service creates a response and sends it to the `Destination` obtained from `JMSReplyTo`. Connection B is a **producer** and does not need a consumer on the temporary queue.
5. The requester receives the message from the temporary queue, checks the body type/correlation ID, then closes the consumer and calls `delete()`.
6. If the request times out, the requester does not wait forever; a response arriving after the queue has been deleted may no longer have a destination to be received on.

~~~text
A                                Broker                                B
│ createTemporaryQueue()          │                                    │
│ createConsumer(reply)           │                                    │
│ -- request: JMSReplyTo=reply -->│ -- deliver orders.requests ------->│
│                                 │                                    │ process
│                                 │<----------- send(reply, result) ----│
│<-------------- deliver result --│                                    │
│ close consumer; reply.delete()  │                                    │
~~~

The `JMSReplyTo` header only **indicates the destination to send the reply to**; JMS does not automatically handle the entire request–reply interaction. The application or framework must still handle timeouts, errors, correlation, and lifecycle.

### 4.2. `JMSCorrelationID`, `JMSMessageID`, and Matching Replies

There are two common strategies:

- **Echo an application-generated request ID:** generate a unique correlation ID and put it on the request; the responder copies that ID into the reply, and the requester checks for a match.
- **Use the request's `JMSMessageID`:** after the request is sent, the provider assigns `JMSMessageID`; the responder sets the reply's `JMSCorrelationID = request.getJMSMessageID()`, and the requester compares. Both sides must agree on the convention because the two strategies are **not equivalent**.

Both fields are JMS headers, yet JMS does not force every service to correlate request/reply using one specific convention. If using **a dedicated temporary queue per request**, the reply address itself isolates the result. When using **one shared reply destination** for multiple concurrent requests, correlation, a selector/dispatcher, and expired-message handling are required to prevent callers from receiving the wrong reply.

Manual responder example, a **code fragment inside a method** that already has `JMSContext responderContext` and `Message incoming`:

~~~java
Destination replyTo = incoming.getJMSReplyTo();
if (replyTo == null) {
    throw new IllegalArgumentException("Missing JMSReplyTo");
}

TextMessage response = responderContext.createTextMessage("DONE");
response.setJMSCorrelationID(incoming.getJMSMessageID());
responderContext.createProducer().send(replyTo, response);
~~~

Here `Destination` can be a `TemporaryQueue`, `TemporaryTopic`, or a regular destination. The responder sends based on the actual destination present in the header; never infer from a String name and create another queue. This code fragment requires importing `jakarta.jms.Destination`/`TextMessage`/`Message` and a method context that can throw `JMSException`.

### 4.3. Why Is TemporaryQueue Usually Better Suited to Request–Reply Than TemporaryTopic?

A request normally expects **one result** received by **one requester**. TemporaryQueue has point-to-point semantics, so it fits that case naturally. TemporaryTopic is useful when a temporary result/notice needs to be broadcast to **multiple subscriptions belonging to the connection that created the topic**. A Topic does not inherently create a one-to-one reply; with multiple subscribers, one reply can reach multiple consumers. Neither is intended for events that must be retained long-term after the client disconnects.

## 5. Runnable Spring Boot Example: `JmsTemplate.sendAndReceive()`

Spring Framework provides `JmsTemplate.sendAndReceive(...)`. With the standard request-sending overloads, Spring **automatically creates a `TemporaryQueue`**, sets it in the `JMSReplyTo` header, creates a consumer to receive the reply, and deletes the temporary queue upon completion. This is a way to observe TemporaryQueue without business code manually managing every `Connection`/`Session`.

This sample uses **Java 17+**, **Maven**, **Spring Boot 3.5.7** (`jakarta.jms` API), and **Apache ActiveMQ Artemis** running on Docker. Practice locally to observe the request–reply flow; real project library versions should align with your project's BOM.

### 5.1. Starting Local Artemis

~~~bash
docker run --rm -d --name artemis-temp-demo \
  -p 127.0.0.1:61616:61616 \
  apache/artemis:latest-alpine
~~~

The official image uses the default account `artemis/artemis`. The command binds the port on loopback for local practice; real deployments require dedicated users, TLS, access control, and broker configuration.

If the broker is not ready yet, inspect logs with `docker logs artemis-temp-demo` and run the application after the broker starts. The demo broker is normally configured to auto-create appropriate queues; for production systems, proactively manage the `demo.requests` queue and routing policies.

### 5.2. Creating the Maven Project

In a new directory, create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>temporary-jms-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
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

`spring-boot-starter-artemis` brings in Spring JMS and the required provider/client. The `jakarta.jms` API defines the Java types, while the Artemis provider is the component connecting to the broker.

### 5.3. Declaring `src/main/resources/application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

spring.jms.template.receive-timeout=5s
~~~

- `native`: connects to an already running broker without starting an embedded broker.
- `receive-timeout=5s`: avoids blocking indefinitely if the service does not respond.
- For the queue demo, there is no need to change the default `spring.jms.pub-sub-domain` (false). The TemporaryQueue created by `sendAndReceive` belongs to the Queue model regardless of the fixed destination's name.
- Connection parameters are **provider/broker** configuration, not fixed rules of the JMS API.

### 5.4. Complete Java Source

Create `src/main/java/com/example/jms/TemporaryDestinationApplication.java`:

~~~java
package com.example.jms;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class TemporaryDestinationApplication {
    public static void main(String[] args) {
        SpringApplication.run(TemporaryDestinationApplication.class, args);
    }

    @Bean
    CommandLineRunner requestOnce(JmsTemplate jmsTemplate) {
        return args -> {
            Message reply = jmsTemplate.sendAndReceive(
                    "demo.requests",
                    session -> session.createTextMessage("order-42")
            );

            if (reply == null) {
                System.out.println("Reply timeout");
                return;
            }
            if (!(reply instanceof TextMessage textReply)) {
                throw new IllegalStateException(
                        "Expected TextMessage, got " + reply.getClass().getName()
                );
            }
            System.out.println("Reply: " + textReply.getText());
        };
    }
}

@Component
class RequestResponder {
    @JmsListener(destination = "demo.requests")
    public String handle(String requestPayload) {
        return "ACK:" + requestPayload;
    }
}
~~~

### 5.5. Running and Explaining

In the directory containing `pom.xml`, run:

~~~bash
mvn spring-boot:run
~~~

Once the broker is running and the listener processes successfully, the application console will contain the line:

~~~text
Reply: ACK:order-42
~~~

Spring/Artemis log lines and log ordering are not fixed. If the broker or listener does not respond before timeout, the line printed by the code is:

~~~text
Reply timeout
~~~

**Path breakdown:**

1. `JmsTemplate.sendAndReceive` creates a `TextMessage`, uses an internal temporary queue, and puts it into `JMSReplyTo`.
2. Spring sends the request to the fixed queue `demo.requests`, then waits for the reply on the temporary queue.
3. The `@JmsListener` receives payload `order-42` and returns String `ACK:order-42`. For requests with `JMSReplyTo`, Spring's listener adapter converts the return value into a reply message and sends it back to the destination in the header.
4. The requester receives the `TextMessage` and prints the result.
5. When `sendAndReceive` finishes, `JmsTemplate` closes the required JMS resources and deletes the temporary queue it created.

In this case, the developer **does not need to call `createTemporaryQueue()` or `delete()` manually**; Spring manages it within the scope of the call. This feature **does not automatically provide** infinite retries, end-to-end exactly-once guarantees, or response recovery if the requester's connection drops.

Stop the app with Ctrl+C; stop the demo broker:

~~~bash
docker stop artemis-temp-demo
~~~

> In server applications, avoid calling synchronous `sendAndReceive()` on threads with very low latency requirements without considering wait times, backpressure, connection counts, and open temporary destination counts. Set explicit timeouts, metrics, and retry policies.

## 6. Differences Between Spring JMS and Manual TemporaryTopic

With Spring JMS, `JmsTemplate` and `@JmsListener` are abstractions over JMS operations. However, **`sendAndReceive` defaults to TemporaryQueue**, because a single request–reply usually expects one recipient. If business needs demand TemporaryTopic, it can be created via `Session.createTemporaryTopic()` or `JMSContext.createTemporaryTopic()`, managing consumers, connections, and destination deletion according to the application's own lifecycle.

Do not set `spring.jms.pub-sub-domain=true` and assume `JmsTemplate.sendAndReceive` will automatically use `TemporaryTopic`. That setting affects how Spring resolves named destinations and configured listeners, and **does not alter the TemporaryQueue creation logic of the default request–reply overloads**.

In a multithreaded service using **`CachingConnectionFactory`** or pooling, temporary destinations are tied to the underlying connection. Closing a wrapper or session must not be treated as certain proof that the physical connection has ended. If creating temporary queues/topics manually, check the caching strategy and **delete proactively** once consumers have closed. Do not cache `TemporaryQueue`/`TemporaryTopic` long-term in a singleton Spring bean to reuse across reconnects.

## 7. When Should You Not Use Temporary Destinations?

Use temporary destinations for short-lived request–reply, still-connected interactive sessions, or short-lifetime subscriptions. Do not use them if you need:

- **Replies that survive client offline/restart:** use a long-lived queue or persistence/state store with correlation IDs and TTL.
- **Long-lived subscriptions that survive reconnects:** use a regular topic with an appropriate durable subscription; temporary topics are not meant for durability.
- **Broadcasting information for multiple independent microservices to consume:** use administered topics/queues, because only the owning connection can create consumers on a temporary destination.
- **Very high concurrent requests with low broker resource limits:** consider a shared reply queue, correlation IDs, and a listener dispatcher; competing consumers, failover, load balancing, and stale messages must be handled properly.
- **Responses that must traverse other brokers/clusters/bridges:** verify temporary destination routability across the topology. Do not assume an internal destination name has meaning on another broker.

### 7.1. Comparing Reply Strategies

| Design | Strengths | Trade-offs |
| --- | --- | --- |
| One `TemporaryQueue` per request | Clear isolation, cleaned up by connection/delete call; very intuitive | Round-trip cost to create/delete destination; many concurrent requests can use many resources |
| One temporary queue per connection, shared across requests | Fewer destinations; owning connection still holds consume rights | Needs correlation, multi-call dispatching, concurrency/reconnect handling |
| Fixed reply queue | Can survive restarts, easy centralized management | Needs routing IDs, selector/consumer strategy, TTL, stale message cleanup, security |
| Asynchronous callback/event | Does not block threads waiting for reply | Needs state storage, completion/correlation definition, and different timeout mechanism |

The choice depends on SLA, requests/second, connection count, broker cost, and recovery requirements. There is no single optimal strategy for every system.

## 8. Common Errors and How to Fix Them

### Error 1: Consumer Created on a Different Connection

**Scenario:** connection A creates a `TemporaryQueue`, connection B obtains the destination reference and calls `createConsumer(tempQueue)`.

**Why it fails:** JMS allows only connection A itself to create consumers on the temporary destination. Connection B **may send** to tempQueue, but **may not consume**.

**Fix:** the reply consumer must live on the connection that created the destination; if multiple services need to read, redesign using regular queues/topics.

### Error 2: Closing the Connection Before the Service Replies

**Scenario:** the requester creates a temp queue, sends a request, exits try-with-resources/closes the connection, and only then does the service send the reply.

**Consequence:** the temp queue's lifetime has ended; the response may fail to send or have no consumer left to receive it.

**Fix:** keep the owning connection and consumer alive until the reply, timeout, or cancellation; delete after completion.

### Error 3: Not Closing Consumers Before `delete()`

`TemporaryQueue.delete()`/`TemporaryTopic.delete()` can throw `JMSException` if the destination still has active consumers/subscribers.

**Fix:** close consumers first, then delete in `finally`; use try-with-resources to guarantee cleanup even if receive fails.

### Error 4: Mistaking Session Close for Temporary Destination Close

A `Session` creates the temp destination, but does not define its own lifetime. An active connection may have another session consuming the created destination.

**Fix:** identify the owning connection properly, delete the destination when finished using it, and manage connection lifecycles in pools/caches.

### Error 5: Calling Receive Indefinitely

A failing service or congested broker causes the requester to wait forever if no timeout is set.

**Fix:** `receive(timeout)`, `receiveBody(..., timeout)`, or `spring.jms.template.receive-timeout=5s`; define behavior for receiving `null`, timeouts, request cancellation, and retries. Retries can create duplicate requests, so business logic should support idempotency.

### Error 6: Receiving the Wrong Response on a Shared Reply Queue

There are multiple concurrent requests without correlation, and competing consumers grab messages.

**Fix:** generate unique correlation IDs, define how responders echo them, and use an appropriate message selector/dispatcher; handle late replies, duplicate replies, timeouts, and TTL.

### Error 7: Waiting for a Response in the Same Uncommitted Request Transaction

If a request is sent inside an uncommitted JMS transaction and the caller blocks waiting for the response, the responder may **not see the request yet**. The transaction holds back the uncommitted send.

**Fix:** send the request and commit before waiting for the response, or design asynchronous request–reply; avoid holding DB transactions open while waiting on the network. Simple `sendAndReceive` uses normal send/receive flow, but callers must still understand actual transaction configuration.

### Error 8: Assuming Temporary Destinations Survive Failover

Reconnecting often creates a new connection; the old temporary queue/topic was bound to the previous connection. Providers may offer proprietary recovery features, yet **do not assume** the old destination is restored with valid consumers.

**Fix:** recreate the temporary destination on the new connection, resend the request per idempotency policy, and record timeouts/recoveries with metrics.

### Error 9: Using TemporaryTopic as a Durable Topic

Durable subscriptions need to live independently longer than a single connection, which contradicts the nature of a temporary topic.

**Fix:** use a regular topic with a durable subscription managed with the proper client ID/subscription name per JMS version, or use a long-lived queue if point-to-point is required.

### Error 10: Misunderstanding Security and Communication Scope

"Only the owner consumes" is an **API rule**. It does not prove any producer is allowed to send: send permissions, auth/TLS, user/role, and routing are still governed by the broker.

**Fix:** keep `JMSReplyTo` as a destination object; verify send permissions, topology, and security policies. Do not mistake temporary destinations for comprehensive authorization.

## 9. Practical Implementation Checklist

1. **Purpose:** need a short-lived one-to-one reply (TemporaryQueue) or temporary broadcast to multiple subscriptions on the same connection (TemporaryTopic)?
2. **Ownership:** which connection creates, which consumes, which sends? Are any framework caches/transaction proxies involved?
3. **Lifecycle:** are creation timing, timeout, consumer closing, `delete()`, connection close, and failover clearly designed?
4. **Correlation:** a separate destination per request or a shared destination; using `JMSCorrelationID` or request `JMSMessageID` and agreed upon by both sides?
5. **Semantics:** queue vs topic, acknowledgment, transactions, redelivery, duplicate/late responses, message TTL?
6. **Resources:** temporary destination limits, connection counts, create/delete rates, leak metrics, timeout rates?
7. **Integration:** can producers route to temporary destinations across clusters/broker bridging, and do they have send permissions?
8. **Testing:** request success, timeout, connection loss, retries, concurrent requests, consumer close, delete under load.

## 10. Self-Check

**Question 1.** Session S1 on connection A creates a TemporaryQueue. S1 closes; session S2 belonging to A is still active. Can S2 create a consumer?  
**Answer:** Yes, as long as the temporary queue has not been deleted and connection A still exists. A temporary destination's scope is the **connection**, not S1.

**Question 2.** Can connection B send to a TemporaryTopic created by A?  
**Answer:** Yes, if the destination is still valid and the broker allows sending. B is not permitted to create consumers on that temporary topic.

**Question 3.** Is `createQueue("tmp.reply")` equivalent to `createTemporaryQueue()`?  
**Answer:** No. The first creates an object identifying a queue by name; the second asks the provider to allocate a temporary queue with its own lifetime and consumer rules.

**Question 4.** Does closing the consumer automatically delete the temporary destination?  
**Answer:** Do not assume so. Closing the consumer stops consumption; `delete()` or closing the owning connection is needed to end its lifetime.

**Question 5.** What happens when a reply arrives after timeout and the temporary queue has already been deleted?  
**Answer:** You cannot assume the reply still reaches the requester; sending a late reply will encounter an invalid destination or be handled according to broker-specific policies.

**Question 6.** Should durable subscriptions be used on a TemporaryTopic?  
**Answer:** No. Durable subscriptions and temporary topics have conflicting lifecycles.

**Question 7.** When calling `JmsTemplate.sendAndReceive`, who creates and cleans up the TemporaryQueue?  
**Answer:** Spring `JmsTemplate` manages the temporary queue for that request–reply round-trip, sets it in `JMSReplyTo`, and cleans it up when the method finishes.

**Question 8.** Why does sharing one reply queue for 100 requests require additional design?  
**Answer:** You must match each response back to the corresponding requester via correlation/dispatcher, handle concurrency, and handle timeouts; merely having one destination does not solve this.

## 11. Official Documentation for Deeper Reading

- [Jakarta Messaging 3.1 Specification — Creating temporary destinations, TemporaryQueue/TemporaryTopic and Request/reply](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta EE Tutorial — Creating Temporary Destinations](https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html)
- [Jakarta Messaging API — TemporaryQueue](https://javadoc.io/static/jakarta.jms/jakarta.jms-api/3.1.0/jakarta.messaging/jakarta/jms/TemporaryQueue.html)
- [Jakarta Messaging API — TemporaryTopic](https://javadoc.io/static/jakarta.jms/jakarta.jms-api/3.1.0/jakarta.messaging/jakarta/jms/TemporaryTopic.html)
- [Spring Framework — Using Spring JMS, JmsTemplate and Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Annotation-driven Listener Endpoints and replying via JMSReplyTo](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework 6.2 — JmsTemplate.sendAndReceive API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Boot — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
- [Apache ActiveMQ Artemis — Official Docker Image](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)
