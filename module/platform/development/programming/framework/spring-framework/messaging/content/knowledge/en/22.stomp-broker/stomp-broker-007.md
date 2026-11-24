# BrokerAvailabilityEvent and Reacting When the STOMP Broker Is Unavailable

## Objectives

In a Spring WebSocket application using STOMP, the broker is the component that receives, routes, and distributes messages among clients. When the application uses an external broker via the STOMP broker relay, the connection to the broker may be lost due to broker restarts, network disruptions, timeouts, or operational errors. If server code keeps sending messages as if the broker were always ready, messages may fail to be delivered and business flows can break.

Spring provides **BrokerAvailabilityEvent** to notify when the broker's availability state changes. The application can listen for this event to:

- Stop or defer new message sends when the broker is unavailable.
- Display a degraded status for features that depend on STOMP.
- Persist messages to be sent into a durable mechanism for reprocessing once connectivity recovers.
- Track disconnection and recovery times using logs, metrics, or health indicators.

Combine the event with actual send-error handling. State can change between the check and the send, so seeing that the broker is available does not guarantee the next send will succeed.

## 1. What Is BrokerAvailabilityEvent?

BrokerAvailabilityEvent is a Spring ApplicationContext event in the package:

~~~java
org.springframework.messaging.simp.broker
~~~

The event is published when the availability state of the message broker changes. It has a constructor accepting a boolean state and the event source, and provides the **isBrokerAvailable()** method to read the state:

~~~java
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;

public void onBrokerAvailability(BrokerAvailabilityEvent event) {
    boolean available = event.isBrokerAvailable();
}
~~~

Meaning of the values:

| Value | Meaning | Typical Application Action |
|---|---|---|
| true | The broker is ready to accept and process messages per the state tracked by Spring | Allow send attempts; begin draining backlog if any |
| false | The broker is unavailable | Pause direct sends; persist or defer messages |

The event represents **a state transition**, not a continuous polling stream. The application should store the latest state so other services can read it quickly.

You can receive the event in either of two ways:

- Implement **ApplicationListener<BrokerAvailabilityEvent>**.
- Use the **@EventListener** annotation on a Spring bean.

You do not need to create the event manually to check the broker. In a standard STOMP configuration, Spring publishes the event from the message broker handler whenever the broker state changes.

## 2. How Does the Event Apply to Simple Broker and Broker Relay?

Spring supports two common broker types:

| Type | How It Works | Availability Characteristics |
|---|---|---|
| Simple Broker | Simple broker running inside the Spring application | Considered available right after startup and stays in that state while the application is running |
| STOMP Broker Relay | Spring forwards STOMP messages to a full-featured external broker such as RabbitMQ or ActiveMQ with STOMP support | The connection to the external broker can be lost and re-established |

With the Simple Broker, the event mainly reflects the internal broker lifecycle. The Simple Broker does not provide the full storage, distribution, and operational capabilities of a dedicated broker.

With the Broker Relay, Spring maintains a system TCP connection to the external broker. This connection is used for messages originating from the server application. In addition, the relay creates a separate TCP connection for each connected WebSocket client.

**Key distinction:** the relay's BrokerAvailabilityEvent tracks the state of the system connection to the broker. It is not an individual health report for each client connection, subscription, queue, or the entire broker cluster. If an individual client's connection has an issue, this event does not necessarily switch to false.

## 3. How Does the Broker Relay Reconnect Automatically?

When the connection to the external broker is lost, Spring's STOMP broker relay automatically attempts to re-establish the system connection. According to current Spring documentation, the relay retries periodically, defaulting to roughly 5 seconds between attempts. Heartbeats on the system connection help detect unresponsive connections; default send and receive heartbeat intervals are 10 seconds and are configurable.

When the system connection is lost, Spring publishes the event with state false. When the connection is re-established, Spring publishes the event with state true.

The relay recovering the system connection **does not mean individual client TCP connections are automatically restored**. Clients must implement their own reconnect logic. When heartbeats are enabled, clients can detect an unresponsive broker and reconnect according to the application's policy.

An example relay configuration:

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

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost("localhost")
                .setRelayPort(61613)
                .setSystemLogin(System.getenv("STOMP_RELAY_SYSTEM_LOGIN"))
                .setSystemPasscode(System.getenv("STOMP_RELAY_SYSTEM_PASSCODE"));
    }
}
~~~

This is an illustrative configuration inside a Spring application, not a standalone program. Replace the host, port, and environment variable names to match your real environment configuration. Do not store broker passwords directly in source code; retrieve them from environment variables or a secret manager. System login and system passcode are used for the system connection opened by the application. The relay also has separate credentials configured for client connections.

## 4. Listening for the Event and Storing Broker State

A straightforward approach is creating a Spring component that holds the current state in an AtomicBoolean. Use an initial value of false so the application only allows sending after receiving notification that the broker is ready:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
public class BrokerAvailabilityMonitor {

    private final AtomicBoolean brokerAvailable = new AtomicBoolean(false);

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        brokerAvailable.set(event.isBrokerAvailable());
    }

    public boolean isBrokerAvailable() {
        return brokerAvailable.get();
    }
}
~~~

Explanation:

1. @Component lets Spring manage the bean and discover the listener.
2. @EventListener registers the method to receive BrokerAvailabilityEvent.
3. event.isBrokerAvailable() reads the new state reported by Spring.
4. AtomicBoolean.set() updates the state safely when accessed concurrently by multiple threads.
5. Other services call isBrokerAvailable() to decide whether to attempt sending messages.

AtomicBoolean is appropriate because the event listener updates the state while multiple requests or workers may read it simultaneously. A plain boolean variable does not clearly express cross-thread synchronization intent.

If you prefer an interface over an annotation, you can implement ApplicationListener<BrokerAvailabilityEvent> and update the state in onApplicationEvent. Both are Spring event-listening mechanisms; do not register both for the same logic.

The listener should execute quickly: only update state, record metrics, or emit an internal signal. Do not perform long-running I/O, send thousands of messages, or wait on retries inside the listener, as that can slow down the event dispatch thread.

## 5. Checking Availability Before Sending and Still Catching MessageDeliveryException

Spring recommends that components using SimpMessagingTemplate monitor BrokerAvailabilityEvent to avoid sending when the broker is unavailable. However, the application must still handle MessageDeliveryException when sending messages.

The reason is the time window between two operations:

1. The service reads the state and sees the broker is available.
2. The broker connection drops immediately after the check.
3. The service calls convertAndSend() and the send operation fails.

This is a normal race condition in distributed systems. Checking state avoids sends that obviously should not be attempted, while catching the exception handles the case where state just changed.

Example notification-sending service:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(NotificationPublisher.class);

    private final SimpMessagingTemplate messagingTemplate;
    private final BrokerAvailabilityMonitor brokerMonitor;

    public NotificationPublisher(
            SimpMessagingTemplate messagingTemplate,
            BrokerAvailabilityMonitor brokerMonitor) {
        this.messagingTemplate = messagingTemplate;
        this.brokerMonitor = brokerMonitor;
    }

    public PublishResult publish(Notification notification) {
        if (!brokerMonitor.isBrokerAvailable()) {
            return PublishResult.BROKER_UNAVAILABLE;
        }

        try {
            messagingTemplate.convertAndSend(
                    "/topic/notifications",
                    notification
            );
            return PublishResult.ACCEPTED_BY_SPRING_CHANNEL;
        }
        catch (MessageDeliveryException ex) {
            log.warn("Failed to send notification via STOMP broker", ex);
            return PublishResult.DELIVERY_FAILED;
        }
    }
}

enum PublishResult {
    ACCEPTED_BY_SPRING_CHANNEL,
    BROKER_UNAVAILABLE,
    DELIVERY_FAILED
}

record Notification(String id, String message) {}
~~~

The example above illustrates distinguishing three outcomes:

- BROKER_UNAVAILABLE: the service did not attempt the send because the current state is unavailable.
- ACCEPTED_BY_SPRING_CHANNEL: the Spring message channel accepted the send operation.
- DELIVERY_FAILED: the send operation failed and threw MessageDeliveryException.

The outcome name ACCEPTED_BY_SPRING_CHANNEL is chosen deliberately. Returning normally from convertAndSend() does not by itself prove that the client received the message, the consumer processed it, or the broker persisted it durably. If business logic requires delivery confirmation, design acknowledgments, persistence, and retries suited to the broker and protocol in use.

Do not catch every Exception and return success. Only handle send errors the application can react to, log sufficient context, and propagate unexpected errors to the general error-handling mechanism.

## 6. What Should the Application Do When the Broker Is Unavailable?

The response depends on how critical the message is.

### 6.1. Temporarily Drop Ephemeral Messages

Some messages are purely point-in-time, such as:

- Live location updates.
- Typing-status indicators.
- Transient display data.
- Real-time metrics that will be re-sent on the next cycle.

For this group, the service can return BROKER_UNAVAILABLE, drop the current broadcast, and wait for fresh data. Clearly establish that dropping is an acceptable business policy.

### 6.2. Bounded Retries

If the message needs to be re-sent, use a retry mechanism with:

- A maximum number of attempts.
- Exponential backoff to progressively increase wait intervals.
- Jitter to avoid multiple workers retrying at the exact same moment.
- Timeouts and a retention limit for holding messages.
- An idempotency key to handle duplicate sends.
- A dead-letter state or final failed status for investigation.

Do not retry continuously in a tight loop without delay. Such a loop can saturate CPU, thread pools, and logs while the broker remains disconnected.

When the broker recovers, you can signal a worker to drain the backlog. The listener should only signal or wake the worker; the worker processes items in bounded batches.

### 6.3. Use a Transactional Outbox for Critical Messages

If a message represents a business change that must not be lost—such as a paid order or completed transaction—keeping the message only in RAM is insufficient. The application might stop before the broker recovers and lose the in-memory queue.

The Transactional Outbox is a suitable design pattern:

1. Within the same database transaction, save the business change and an outbox record.
2. A separate worker reads unsent outbox records.
3. The worker only attempts to send when the broker is available.
4. Once sent successfully according to the confirmation mechanism the system requires, mark the record as processed.
5. On error, keep the record for retry according to policy.
6. Use a message ID or idempotency key so consumers can deduplicate processing.

High-level flow:

~~~text
Business request
      |
      v
Database transaction
  +----------------------+
  | Update business data |
  | Insert outbox record |
  +----------------------+
      |
      v
Outbox publisher
      |
      +---- Broker unavailable ----> Keep pending
      |
      v
Check availability and publish
      |
      +---- Delivery failure ------> Retry with backoff
      |
      v
Broker / consumers
      |
      v
Mark outbox item processed
~~~

Note: succeeding through SimpMessagingTemplate does not always mean the broker confirmed durable storage. For strict delivery requirements, design acknowledgments or publisher confirmations according to the broker's capabilities and integration mechanism. The outbox should be marked complete based on the confirmation level required by the business.

### 6.4. Display Degraded Status to Users

When the broker stops working, real-time features may be temporarily unavailable even though HTTP processing and the database continue working.

The application can:

- Return a temporary status for APIs that need to emit messages.
- Show a banner indicating real-time connectivity is interrupted.
- Allow users to continue business actions that do not depend on the broker.
- Display the last updated timestamp if real-time data is stale.
- Provide a mechanism to reload state from an API when connectivity recovers.

Do not let the UI display that a message was delivered successfully if the server only received the request without the required delivery confirmation.
## 7. Distinguishing Broker State from Client Connection State

BrokerAvailabilityEvent is an event on the Spring application side. It does not automatically send notifications to browsers and does not replace STOMP session lifecycle events.

| Scenario | Mechanism to Monitor |
|---|---|
| System connection from Spring broker relay to external broker drops or recovers | BrokerAvailabilityEvent |
| A client starts sending STOMP CONNECT | SessionConnectEvent |
| Broker responds with STOMP CONNECTED to client | SessionConnectedEvent |
| Client subscribes to a destination | SessionSubscribeEvent |
| Client closes session | SessionDisconnectEvent |
| Client needs to reconnect after network or broker failure | STOMP client reconnect logic |

For the relay, the system connection and each client's individual connection have separate lifecycles. Therefore:

- BrokerAvailabilityEvent may report that the system connection recovered while clients still need to reconnect.
- A client may lose its individual connection even while the system connection remains active.
- Broker availability does not prove all subscriptions are active or all messages are being processed by consumers.
- If real-time status is needed in the UI, the server must expose a separate status endpoint or message; clients still need to detect close/error and reconnect.

When handling SessionDisconnectEvent, make cleanup operations idempotent. Spring notes that this event may be published more than once for the same session.

## 8. Monitoring State with Logs, Metrics, and Health Checks

A listener can record every state transition:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
public class BrokerAvailabilityLogger {

    private static final Logger log =
            LoggerFactory.getLogger(BrokerAvailabilityLogger.class);

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        if (event.isBrokerAvailable()) {
            log.info("STOMP broker is available");
        }
        else {
            log.warn("STOMP broker is currently unavailable");
        }
    }
}
~~~

In real systems, also track:

- Number of transitions from available to unavailable.
- Total duration the broker stays in the unavailable state.
- Number of messages waiting in the outbox or retry queue.
- Number of failed sends due to MessageDeliveryException.
- Latency from broker recovery until the backlog is cleared.
- Number of successful or failed client reconnects.

You can expose the status in a Spring Boot Actuator HealthIndicator or an internal endpoint. However, choose an appropriate readiness policy:

- If the application cannot serve most features when the broker is disconnected, you can mark readiness as failing.
- If only real-time features are degraded, the application can still accept HTTP requests and process database operations. In that case, represent the dependency status separately rather than necessarily marking the entire application unhealthy.
- Do not use broker availability to replace liveness. An external broker failure does not mean the Spring process is dead.

Health checks should reflect the service's operational policy. Avoid letting a temporarily unavailable dependency cause the orchestrator to continuously restart the entire application, making recovery harder.

## 9. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Service sends messages while broker is disconnected | Not listening to BrokerAvailabilityEvent | Store the latest state and check before sending |
| Broker disconnects right after availability check | Race condition between check and send | Catch MessageDeliveryException on the send call |
| Application thinks clients reconnected when event turns true | Confusing system connection with individual client connections | Clients reconnect themselves and wait for STOMP CONNECTED |
| Critical messages lost while broker is down | Keeping messages only in memory or ignoring errors | Use an outbox or durable queue |
| Retries produce duplicate messages | Re-sending after timeouts without idempotency | Attach a message ID and process idempotently on consumers |
| CPU spikes during broker outage | Continuous retries without backoff | Use exponential backoff, jitter, and retry limits |
| Listener slows down event processing | Performing batch sends or synchronous I/O inside listener | Only update state and wake up a worker |
| Health check reports entire app DOWN on broker error | Combining broker status into liveness | Separate liveness, readiness, and dependency status |

## 10. Testing Behavior When the Broker Is Unavailable

Test both the listener logic and the integration flow with a broker.

### Unit test for the listener

You can construct events to verify the monitor updates state:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;

class BrokerAvailabilityMonitorTest {

    @Test
    void updatesAvailabilityWhenEventArrives() {
        BrokerAvailabilityMonitor monitor = new BrokerAvailabilityMonitor();

        assertFalse(monitor.isBrokerAvailable());

        monitor.onBrokerAvailability(
                new BrokerAvailabilityEvent(true, this)
        );
        assertTrue(monitor.isBrokerAvailable());

        monitor.onBrokerAvailability(
                new BrokerAvailabilityEvent(false, this)
        );
        assertFalse(monitor.isBrokerAvailable());
    }
}
~~~

This is a JUnit test example for the monitor component; JUnit Jupiter and Spring Messaging dependencies are required in the project. The test verifies that the listener handles both state transitions properly.

### Integration test with an external broker

For the STOMP broker relay, you can use a real broker in the test environment or Testcontainers if an appropriate image is available:

1. Start the application and the broker.
2. Wait for the event reporting the broker is available.
3. Send a message and verify reception.
4. Stop the broker or block the TCP connection.
5. Verify the state switches to unavailable.
6. Call the sending service and verify the message is deferred or returns failure according to policy.
7. Restart the broker.
8. Verify the relay reconnects and the event switches to available.
9. Verify the outbox/retry worker processes pending messages.
10. Verify the STOMP client reconnects and re-registers subscriptions.

The built-in Simple Broker cannot fully simulate external broker disconnections. To test the Broker Relay path, use a STOMP-capable broker in integration tests.

## 11. Implementation Checklist

- [ ] Understand that the event belongs to package org.springframework.messaging.simp.broker.
- [ ] Listen for the event using @EventListener or ApplicationListener.
- [ ] Store current state with AtomicBoolean or an appropriate synchronization mechanism.
- [ ] Disallow sending by default until the available state is received.
- [ ] Check availability before calling SimpMessagingTemplate.
- [ ] Catch MessageDeliveryException because state can change between check and send.
- [ ] Do not treat sending through a Spring channel as confirmation of client receipt.
- [ ] Explicitly choose drop, retry, or outbox persistence policy based on message criticality.
- [ ] Use backoff, jitter, and idempotency when retrying.
- [ ] Let clients detect errors and reconnect their sessions themselves.
- [ ] Track outage duration, send failures, and backlogs.
- [ ] Separate liveness from readiness and dependency status.
- [ ] Test both disconnection and recovery states with a real broker.

## References

- [Spring Framework — ApplicationContext Events for STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Javadoc — BrokerAvailabilityEvent](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/BrokerAvailabilityEvent.html)
- [Javadoc — SimpMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/SimpMessagingTemplate.html)
- [Javadoc — MessageDeliveryException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageDeliveryException.html)
