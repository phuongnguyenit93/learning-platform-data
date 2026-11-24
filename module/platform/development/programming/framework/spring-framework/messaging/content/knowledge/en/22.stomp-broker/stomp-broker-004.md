# STOMP Broker Relay and Connecting to an External Broker

This document explains how Spring Framework forwards STOMP messages to an independently running message broker such as RabbitMQ or ActiveMQ. This is the next step after configuring WebSocket endpoints and STOMP controllers: Spring still accepts WebSocket connections and routes messages to the application, while a dedicated broker handles managing subscriptions, queues, and delivering messages.

## 1. Why Use an External Broker?

Spring includes an in-memory simple broker. It is useful when learning STOMP or building small applications, but it only supports a subset of the protocol: it does not support ACK, RECEIPT, and certain other STOMP commands; subscription state lives inside the application process and the simple broker is not suitable for clustering.

When fuller messaging capabilities are needed, the application can connect to a separate broker. Popular choices include RabbitMQ with the STOMP plugin enabled and ActiveMQ with a STOMP connector. The broker must actually enable and open a port for the STOMP protocol; the AMQP or OpenWire port of the same product is not automatically a STOMP port.

Spring provides a **STOMP broker relay** to bridge WebSocket/STOMP clients and the broker. The relay receives messages from Spring, forwards them over TCP to the broker, receives messages from the broker, and delivers them back to subscribed WebSocket sessions. Spring's controllers, destination prefixes, and message-sending APIs continue to be used in the application.

## 2. Architecture and Message Path

In a typical configuration, destinations are divided into two groups:

- Destinations starting with **/app** are routed to **@MessageMapping** methods in Spring controllers.
- Destinations starting with **/topic** or **/queue** are forwarded to the external broker according to the registered prefixes.

High-level flow:

~~~mermaid
flowchart LR
    C[Browser / STOMP client] <-->|WebSocket + STOMP| WS[Spring WebSocket endpoint]
    WS --> IN[clientInboundChannel]
    IN --> APP[@MessageMapping controllers]
    IN --> RELAY[STOMP broker relay]
    APP --> BC[brokerChannel]
    BC --> RELAY
    RELAY <-->|TCP + STOMP| B[External broker]
    B --> RELAY
    RELAY --> OUT[clientOutboundChannel]
    OUT --> WS
    WS --> C
~~~

For example, a client sends a frame to **/app/orders.create**. Spring routes the message to the **@MessageMapping("/orders.create")** method. The controller processes business logic, and can then return a result or call **SimpMessagingTemplate** to send to **/topic/orders**. The message goes through **brokerChannel**, the relay forwards it to the broker, and the broker broadcasts the message to clients subscribed to the corresponding destination.

If a client subscribes to **/topic/orders**, the subscription is forwarded to the broker. When the broker broadcasts a message, the relay receives that message and Spring delivers it to matching WebSocket sessions. The broker is responsible for queue/topic semantics, routing, and the messaging features supported by the product.

## 3. Differences Between the Simple Broker and Broker Relay

| Criterion | Simple broker | STOMP broker relay |
| --- | --- | --- |
| Where subscriptions are held | In-memory inside the Spring application | External broker |
| Scope | Tied to a single application process | Multiple application instances can share one broker |
| STOMP ACK/RECEIPT | Not fully supported | Depends on the connected STOMP broker |
| Queues, persistence, policies | Limited | Provided and configured by the broker |
| Operations | Fewer components, easy to start | Requires operating the broker, network, credentials, and connection limits |

The broker relay does not make all brokers behave identically. STOMP specifies frames and commands, but the meaning of destinations, queues, persistence, ACK modes, access permissions, and policies can differ across RabbitMQ, ActiveMQ, and other products. Always check the documentation of the broker in use.

## 4. The Two Types of TCP Connections Managed by the Relay

An important point is that the relay does not use a single TCP connection for all activity.

**Client connections:** Spring opens a dedicated TCP connection to the broker for each connected WebSocket client. That connection carries the corresponding client's STOMP frames, including SUBSCRIBE, SEND, ACK, and DISCONNECT. With N active WebSocket sessions, there will generally be about N client TCP connections to the broker.

**System connection:** Spring maintains a shared TCP connection to send messages originating from the application side—that is, messages not tied to a specific client session. For example, a service calls **SimpMessagingTemplate.convertAndSend(...)** or an HTTP controller broadcasts a notification to a topic. By default, the system connection serves outbound application messages; it is not a connection that receives messages on behalf of client subscriptions.

Thus, if there are 500 WebSocket sessions on one Spring instance, the relay typically needs around 501 broker connections: 500 client connections and one system connection. When running multiple Spring instances, each instance maintains its own client connections for its sessions and its own system connection.

Spring configures two separate sets of credentials:

- **clientLogin / clientPasscode**: credentials the relay uses for every TCP connection opened on behalf of WebSocket clients.
- **systemLogin / systemPasscode**: credentials for the system connection used to send messages from the application.

The relay places the configured login and passcode into every CONNECT frame sent to the broker on behalf of clients. Any login/passcode headers sent by the browser are ignored. Therefore, all broker connections on behalf of clients typically share a single broker identity. Authenticate users during the HTTP/WebSocket handshake using Spring Security so Spring attaches a Principal to the session; then check destination access and action permissions at the Spring layer. Do not treat clientLogin as the individual identity of each end user.

## 5. Configuring Spring in Java

The example below uses Spring Framework 6.2 or 7.0 with Java configuration. Adjust host, port, virtual host, and credentials for your environment's broker.

~~~java
package com.example.messaging;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Value("${messaging.stomp.relay.host}")
    private String relayHost;

    @Value("${messaging.stomp.relay.port:61613}")
    private int relayPort;

    @Value("${messaging.stomp.relay.virtual-host:/}")
    private String virtualHost;

    @Value("${messaging.stomp.relay.client-login}")
    private String clientLogin;

    @Value("${messaging.stomp.relay.client-passcode}")
    private String clientPasscode;

    @Value("${messaging.stomp.relay.system-login}")
    private String systemLogin;

    @Value("${messaging.stomp.relay.system-passcode}")
    private String systemPasscode;

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost(relayHost)
                .setRelayPort(relayPort)
                .setVirtualHost(virtualHost)
                .setClientLogin(clientLogin)
                .setClientPasscode(clientPasscode)
                .setSystemLogin(systemLogin)
                .setSystemPasscode(systemPasscode)
                .setSystemHeartbeatSendInterval(10_000)
                .setSystemHeartbeatReceiveInterval(10_000);
    }
}
~~~

**registerStompEndpoints** registers the WebSocket endpoint clients connect to, such as **/ws**. **setApplicationDestinationPrefixes("/app")** reserves destinations for controllers. **enableStompBrokerRelay("/topic", "/queue")** forwards destinations with those two prefixes to the external broker. **setRelayHost** and **setRelayPort** are the TCP address of the STOMP listener on the broker.

**setVirtualHost** sets the **host** header in the STOMP CONNECT frame. With RabbitMQ, this header selects the broker's virtual host. It can differ from the hostname/IP used to open the TCP connection—for instance, when using a cloud broker service or proxy.

The two heartbeat intervals in the example apply to the system connection. Units are milliseconds. Spring defaults to 10-second intervals for sending and receiving heartbeats on the system connection; you can keep the defaults if customization is unnecessary.

### 5.1. Putting Configuration in application.yml

Do not hardcode real passwords in source code or commit configuration files containing secrets. Example using environment variables:

~~~yaml
messaging:
  stomp:
    relay:
      host: ${STOMP_RELAY_HOST:localhost}
      port: ${STOMP_RELAY_PORT:61613}
      virtual-host: ${STOMP_RELAY_VHOST:/}
      client-login: ${STOMP_RELAY_CLIENT_LOGIN}
      client-passcode: ${STOMP_RELAY_CLIENT_PASSCODE}
      system-login: ${STOMP_RELAY_SYSTEM_LOGIN}
      system-passcode: ${STOMP_RELAY_SYSTEM_PASSCODE}
~~~

Supply the environment variables from a secret manager or the deployment platform's runtime configuration. Use separate accounts for the client relay and system connection so broker permissions can be scoped by purpose. In production, grant only the necessary permissions on the virtual host and destinations the application uses.

### 5.2. Dependencies for the TCP Relay

Beyond Spring's WebSocket module, the Spring Framework documentation requires TCP connection management dependencies for the broker relay:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-websocket</artifactId>
</dependency>

<dependency>
    <groupId>io.projectreactor.netty</groupId>
    <artifactId>reactor-netty</artifactId>
</dependency>

<dependency>
    <groupId>io.netty</groupId>
    <artifactId>netty-all</artifactId>
</dependency>
~~~

Use dependency management/BOM compatible with the project's Spring Boot or Spring Framework version to select Reactor Netty and Netty versions. If the application uses Spring Framework directly, inspect the dependency tree to ensure the TCP libraries needed by the broker relay are present. Spring uses Reactor Netty's TCP client by default; you can supply a custom TCP client via **setTcpClient(...)** when advanced settings such as TLS or custom broker address selection are required.

## 6. RabbitMQ Connection Example

RabbitMQ supports STOMP via the **rabbitmq_stomp** plugin. Enable the plugin on the RabbitMQ node:

~~~bash
rabbitmq-plugins enable rabbitmq_stomp
~~~

If listener settings are unchanged, the STOMP adapter listens on TCP port **61613** by default. This port is the STOMP port; the default AMQP port 5672 cannot be used in its place.

RabbitMQ has a default virtual host **/**. For example, to create a dedicated virtual host named **/messaging** and two relay accounts:

~~~bash
rabbitmqctl add_vhost /messaging
rabbitmqctl add_user stomp-clients REPLACE_WITH_CLIENT_SECRET
rabbitmqctl add_user stomp-system REPLACE_WITH_SYSTEM_SECRET
rabbitmqctl set_permissions -p /messaging stomp-clients ".*" ".*" ".*"
rabbitmqctl set_permissions -p /messaging stomp-system ".*" ".*" ".*"
~~~

The permission commands above grant broad configure, write, and read permissions within the virtual host to illustrate connectivity. In real deployments, restrict permission expressions to the exchanges, queues, and routing patterns the application needs. Set **STOMP_RELAY_VHOST=/messaging** and the two corresponding credential sets in Spring's runtime environment.

Do not use the **guest/guest** account for remote connections in production. RabbitMQ by default only allows the guest user to connect from localhost; create dedicated users with randomly generated passwords and least-privilege permissions. Ensure firewalls only allow Spring application hosts to access the STOMP listener.

### 6.1. RabbitMQ Destination Semantics

The RabbitMQ STOMP adapter supports several destination forms:

- **/topic/name**: publish/subscribe. Messages sent to the topic are routed to matching subscribers. If there are no subscribers, messages are typically discarded unless the application configures durable subscriptions.
- **/queue/name**: shared queue. Each message is delivered to at most one subscriber consuming the queue; messages can be retained when no subscriber is present yet.
- **/amq/queue/name**: accesses a queue created outside the STOMP adapter. SUBSCRIBE fails if the queue does not exist.
- **/exchange/name/routing-key**: sends to an exchange and routing key or subscribes using a binding pattern.

RabbitMQ durable topic subscriptions require header configuration per broker documentation, such as SUBSCRIBE with id, durable:true, and auto-delete:false. Simply adding the **/topic** prefix does not automatically make messages durable. Design queues, exchanges, persistence, and acknowledgments according to actual delivery requirements.

## 7. Sending Messages from the Spring Application

Controllers continue to use **@MessageMapping** to receive client requests. Services or controllers can send messages to the broker via **SimpMessagingTemplate**:

~~~java
package com.example.messaging;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderNotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishOrderCreated(OrderCreatedEvent event) {
        messagingTemplate.convertAndSend("/topic/orders", event);
    }
}
~~~

Calling **convertAndSend** places the message onto Spring's broker channel. Because the message is not tied to a specific WebSocket session, the relay sends it over the shared system connection. The broker then broadcasts the message to subscriptions matching **/topic/orders**.

To send to a single user, you can use a user destination such as **/user/queue/notifications** along with **convertAndSendToUser(...)**. In a multi-instance Spring environment, configure an appropriate user registry/destination broadcast mechanism so one node can locate a user's session connected to another node.

## 8. Broker Availability and Connection Recovery

An external broker may restart, lose network connectivity, or reject connections. Spring's broker relay automatically attempts to reconnect the shared system connection when the broker is temporarily unavailable; by default, retry attempts occur every 5 seconds. When the system connection status changes, Spring publishes a **BrokerAvailabilityEvent**.

The application can listen for this event:

~~~java
package com.example.messaging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
public class BrokerAvailabilityListener {

    private static final Logger log =
            LoggerFactory.getLogger(BrokerAvailabilityListener.class);

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        if (event.isBrokerAvailable()) {
            log.info("STOMP broker system connection is available");
        } else {
            log.warn("STOMP broker system connection is unavailable");
        }
    }
}
~~~

This event reflects the status of the shared system connection. It is useful for services proactively sending messages via **SimpMessagingTemplate**, but it is not proof that all client TCP connections are active. When sending messages, the application must still handle **MessageDeliveryException** in case the broker just lost connectivity.

Client TCP connections are not automatically restored by Spring in the same way as the system connection. Clients need a reconnect strategy and must re-subscribe after connecting successfully. Example with the **@stomp/stompjs** library in the browser:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000,

    onConnect: () => {
        // Re-register subscriptions after every successful connection.
        client.subscribe("/topic/orders", (frame) => {
            console.log("Order event:", frame.body);
        });
    },

    onStompError: (frame) => {
        console.error("STOMP broker error:", frame.headers["message"]);
    }
});

client.activate();
~~~

The example above uses the raw WebSocket endpoint **/ws**. If the server registers a SockJS endpoint, configure the client with the corresponding SockJS transport. Do not send broker username/password from the browser: the relay replaces login/passcode with the server-configured credentials.

## 9. Heartbeats and Connection Health Checks

STOMP heartbeats help both sides detect silent connections or network drops. Heartbeats are negotiated via the STOMP CONNECT/CONNECTED headers. If both sides agree on send/receive intervals, they send heartbeats when no other data frames occur during that interval.

Spring's broker relay supports heartbeats on the system connection; by default, both send and receive intervals are 10 seconds. Clients should also configure heartbeats compatible with the broker and proxy/network timeouts. Do not set load balancer timeouts lower than the heartbeat/idle timeout expected by the application.

Heartbeats do not replace reconnect logic. When a connection closes, the browser needs to reconnect, wait for STOMP CONNECTED, and then recreate its subscriptions. For critical messages, the application must define policies for deduplication, retries, ACK, and durable storage on the broker; heartbeats only help identify connection issues.

## 10. Monitoring Connection Counts and Load

The broker relay maintains one TCP connection per WebSocket client plus one system connection per Spring application instance. When estimating capacity, account for concurrent sessions, instance counts, broker connection limits, file descriptors, memory, heartbeat traffic, and message rates.

Spring provides the **WebSocketMessageBrokerStats** bean to aggregate metrics. By default, this bean logs at INFO level every 30 minutes and can be exported via JMX. In the STOMP Broker Relay section, the TCP Connections metric is normally close to the current WebSocket session count plus one system connection. If metrics are unusually lower or higher, check session lifecycles, broker-initiated connection closures, heartbeats, and transport errors.

On the broker side, monitor connection counts, queue depth, consumers, message rates, disk/memory alarms, and authentication logs. Do not monitor only the Spring application status: the broker may still be running while rejecting connections due to exhausted limits, wrong credentials, or missing virtual host permissions.

## 11. Security When Connecting to a Remote Broker

- Place the broker in a private network and only allow required application hosts to access the STOMP listener.
- Use separate credentials for the client relay and system connection; do not use guest/guest or hardcoded secrets in the repository.
- Grant least-privilege permissions on virtual hosts and destinations. If the client relay has overly broad permissions, all WebSocket clients using that shared broker identity through the relay could have similar scope if Spring does not block them.
- Authenticate the WebSocket handshake using HTTP/Spring Security mechanisms and use the Principal attached to the session to check permissions at the application layer.
- Do not trust usernames, user-ids, or roles sent by the client in STOMP headers. If tokens are used, validate them during the handshake or in an interceptor and establish a trusted Principal on the server.
- Use TLS for Spring-to-broker connections over untrusted networks. The broker must enable a TLS listener; on the Spring side, a TCP client configured with TLS must be passed into **setTcpClient(...)**. Merely changing the port does not enable TLS.
- Do not log credentials or sensitive payloads. Limit frame sizes and control which destinations clients are allowed to SEND/SUBSCRIBE to.

## 12. Common Issues and Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Spring starts but cannot connect to broker | Wrong host/port, STOMP listener not enabled on broker, firewall blocking TCP | Check listener and test TCP connectivity from the exact host/container running Spring |
| Connection refused | Using AMQP port instead of STOMP or STOMP plugin not enabled | For RabbitMQ, enable rabbitmq_stomp and check listener 61613 |
| Authentication failed | Wrong client/system credentials, user missing, or locked | Check broker logs and each relay account |
| Access refused on CONNECT | Virtual host does not exist or user lacks access permission | Check **setVirtualHost**, virtual host, and permissions |
| Client CONNECTED but receives no messages | Subscribed to wrong prefix, incorrect broker destination, or topic has no subscribers | Inspect frame destinations and broker subscriptions/queues |
| Service fails to send messages after broker restart | System connection is currently unavailable | Listen for BrokerAvailabilityEvent and handle MessageDeliveryException |
| Client disconnects when broker restarts | Client-side TCP connection was lost | Configure reconnect delay and re-create subscriptions after onConnect |
| Broker has too many connections | Each WebSocket session opens one TCP connection; stale sessions may remain open | Compare WebSocketMessageBrokerStats with the broker's connection count |

A common pitfall with RabbitMQ: the **guest** user is only allowed to connect from localhost by default. Spring running in a container or another host may be rejected even with the correct guest password. Creating dedicated users for the relay is the proper fix.

## 13. Integration Testing

An integration test should run the Spring application alongside a real broker or a broker container with the STOMP plugin enabled. Scenarios to verify:

1. Client connects to the WebSocket endpoint and receives STOMP CONNECTED.
2. Client subscribes to **/topic/orders**, then a service calls **SimpMessagingTemplate.convertAndSend**; client receives the exact payload.
3. Client SENDs to **/app/orders.create**; controller processes and publishes an event to a broker destination.
4. Two clients subscribed to the same topic both receive copies of messages published to the topic.
5. Two clients subscribed to the same queue have messages distributed by the broker according to queue semantics—do not assume both receive the same message.
6. Incorrect credentials or virtual host cause connection failure; broker logs show the reason.
7. Restart the broker; Spring publishes BrokerAvailabilityEvent, the system connection automatically reconnects, and clients reconnect and re-subscribe.
8. Verify ACK/RECEIPT, durable subscriptions, or persistence according to the specific features of the chosen broker.

Using a real broker in integration tests helps uncover differences that mocks or the simple broker cannot simulate, especially authentication, virtual hosts, destination mapping, ACK modes, and reconnect behavior.

## 14. Deployment Checklist

- Broker is installed with the STOMP protocol listener enabled.
- Spring relay points to the correct hostname and STOMP port reachable from the runtime.
- Prefixes **/app**, **/topic**, and **/queue** are separated properly by purpose.
- Client credentials and system credentials exist with permissions on the right virtual host.
- Virtual host in STOMP CONNECT matches broker configuration.
- HTTP/WebSocket authentication and authorization are enabled; clients do not dictate broker credentials.
- Heartbeats, reconnect, and re-subscribe are configured on clients.
- Application handles BrokerAvailabilityEvent and MessageDeliveryException.
- Broker connection limits, queue policies, persistence, and TLS match load and reliability requirements.
- Spring metrics and broker metrics are monitored together.

## 15. References

- [Spring Framework — External Broker](https://docs.spring.io/spring/reference/6.2/web/websocket/stomp/handle-broker-relay.html): broker relay configuration and TCP dependencies.
- [Spring Framework — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html): system/client connections, credentials, heartbeats, reconnect, and virtual host.
- [Spring Framework — Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html): BrokerAvailabilityEvent and lifecycle events.
- [Spring Framework — Monitoring](https://docs.spring.io/spring/reference/6.2/web/websocket/stomp/stats.html): WebSocketMessageBrokerStats and relay TCP connection counts.
- [RabbitMQ — STOMP Plugin](https://www.rabbitmq.com/docs/stomp): enabling the plugin, listeners, ports, TLS, destinations, ACK, and durable subscriptions.
- [RabbitMQ — Access Control](https://www.rabbitmq.com/docs/access-control): users, virtual hosts, authentication, and permissions.
