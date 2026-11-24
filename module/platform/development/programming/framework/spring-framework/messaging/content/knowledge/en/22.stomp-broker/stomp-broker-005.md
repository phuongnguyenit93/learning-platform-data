# System Connection, Client Connections, and Relay Credentials

## 1. Role of the STOMP Broker Relay

Spring Messaging supports two common ways of handling a message broker in WebSocket/STOMP:

- **Simple broker** runs inside the Spring application process. It is suitable for basic needs, but does not provide the full capabilities of a dedicated message broker.
- **STOMP broker relay** forwards STOMP frames between the Spring application and an external STOMP broker such as RabbitMQ or ActiveMQ. The external broker handles subscription management and message delivery; Spring maintains WebSocket connections with clients and TCP connections to the broker.

When using the relay, browsers still connect over WebSocket to the Spring application's endpoint. Browsers do not need to connect directly to the broker's STOMP TCP port. Spring receives STOMP frames from clients, forwards frames over TCP to the broker, and returns frames from the broker back to the right WebSocket session.

The broker relay has two important types of TCP connections:

1. **System connection**: a shared connection from each relay instance to the broker, serving messages emitted by the server application itself—such as messages sent from a REST controller, service, or scheduled task.
2. **Client connection**: a separate TCP connection for each connected WebSocket client. The relay forwards the client's STOMP frames to the broker and delivers response frames from the broker back to the corresponding WebSocket session.

Distinguishing these two connections helps configure credentials, broker permissions, heartbeats, and status monitoring properly.

## 2. Overall Connection Flow

An application can configure the WebSocket endpoint /ws, application prefix /app, and broker prefixes /topic, /queue.

- The client performs an HTTP handshake to the Spring application and upgrades to WebSocket.
- The client sends STOMP CONNECT over WebSocket.
- Spring establishes the user identity from the HTTP/WebSocket authentication mechanism.
- The broker relay opens or uses the corresponding TCP connection to the broker.
- Frames to destinations /app/... are routed by Spring to controllers with @MessageMapping.
- Frames to broker destinations such as /topic/... or /queue/... are forwarded by the relay to the external broker.
- Frames delivered by the broker to subscriptions are forwarded over the client TCP connection and WebSocket session to the client.

Message flow diagram:

~~~mermaid
flowchart LR
    C["Browser / STOMP client"] <-->|"WebSocket + STOMP"| S["Spring WebSocket endpoint"]
    S <-->|"Dedicated client TCP connection"| R["STOMP broker relay"]
    R <-->|"STOMP TCP"| B["External STOMP broker"]
    A["REST / Service / Scheduler"] -->|"SimpMessagingTemplate"| S
    S <-->|"Shared system TCP connection"| B
    S -->|"/app/..."| H["@MessageMapping controller"]
~~~

The diagram illustrates the main paths. In the actual implementation, the broker relay is a message handler in Spring; Spring's internal channels route messages between controllers, the broker handler, and WebSocket sessions.

## 3. How Do the System Connection and Client Connections Differ?

| Property | System connection | Client connection |
|---|---|---|
| Count | One shared connection per relay instance. | One connection per WebSocket client connected to that instance. |
| Purpose | Sends messages from the server-side application to the broker, not tied to a specific client session. | Forwards one client's messages to the broker and returns frames from the broker back to that client. |
| Credentials | systemLogin, systemPasscode. | clientLogin, clientPasscode. |
| Lifecycle | Created by the relay on startup and automatically reconnects when disconnected. | Created when the client connects; closed when the client session ends or the connection fails. |
| Example | A REST request calling SimpMessagingTemplate.convertAndSend(...). | A client subscribing to /topic/prices or sending STOMP SEND. |

For example, if a relay instance serves 500 active WebSocket sessions, the broker typically sees around 500 client TCP connections plus that instance's system connection. When running multiple Spring instances, each instance has its own system connection and manages the client connections for sessions connected to that instance. Account for this connection count when setting broker connection limits, quotas, and resources.

The system connection is not a user's WebSocket connection. Nor does it replace client connections used to receive broker messages returned to individual clients.

## 4. Configuring the STOMP Broker Relay in Java

Use enableStompBrokerRelay to forward broker destinations to an external STOMP broker:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.messaging.simp.config.StompBrokerRelayRegistration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    private final String relayHost;
    private final int relayPort;
    private final String clientLogin;
    private final String clientPasscode;
    private final String systemLogin;
    private final String systemPasscode;
    private final String virtualHost;

    public WebSocketConfig(
            @Value("${app.stomp.relay.host${") String relayHost,
            @Value("${app.stomp.relay.port:61613${") int relayPort,
            @Value("${app.stomp.relay.client-login${") String clientLogin,
            @Value("${app.stomp.relay.client-passcode${") String clientPasscode,
            @Value("${app.stomp.relay.system-login${") String systemLogin,
            @Value("${app.stomp.relay.system-passcode${") String systemPasscode,
            @Value("${app.stomp.relay.virtual-host:${") String virtualHost) {
        this.relayHost = relayHost;
        this.relayPort = relayPort;
        this.clientLogin = clientLogin;
        this.clientPasscode = clientPasscode;
        this.systemLogin = systemLogin;
        this.systemPasscode = systemPasscode;
        this.virtualHost = virtualHost;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        StompBrokerRelayRegistration relay =
                registry.enableStompBrokerRelay("/topic", "/queue")
                        .setRelayHost(relayHost)
                        .setRelayPort(relayPort)
                        .setClientLogin(clientLogin)
                        .setClientPasscode(clientPasscode)
                        .setSystemLogin(systemLogin)
                        .setSystemPasscode(systemPasscode)
                        .setSystemHeartbeatSendInterval(10_000)
                        .setSystemHeartbeatReceiveInterval(10_000);

        if (!virtualHost.isBlank()) {
            relay.setVirtualHost(virtualHost);
        }
    }
}
~~~

Meaning of the settings:

- **setRelayHost** and **setRelayPort**: network address and STOMP TCP port of the external broker.
- **setClientLogin** and **setClientPasscode**: credentials the relay uses when opening broker connections on behalf of WebSocket clients.
- **setSystemLogin** and **setSystemPasscode**: credentials for the shared system connection.
- **setVirtualHost**: value of the STOMP host header sent in the CONNECT frame, if required by the broker.
- **setSystemHeartbeatSendInterval** and **setSystemHeartbeatReceiveInterval**: send interval and receive timeout for system connection heartbeats, in milliseconds.

The configuration snippet is an example for an application with Spring Messaging and Spring's configuration injection mechanism. Actual values must come from the deployment environment and the configuration of the broker in use.

## 5. Broker Address, TCP Port, and Virtual Host

There are three concepts that are easily confused:

| Setting | Meaning |
|---|---|
| WebSocket endpoint, e.g. /ws | Address clients use to connect to the Spring application. |
| Relay host/port | IP address or hostname and TCP port Spring uses to connect to the STOMP broker. |
| Virtual host | Value of the host header in STOMP CONNECT, which can select a virtual host or tenant on the broker. |

For example, a browser might connect to wss://app.example.com/ws, while the Spring relay connects to broker.internal:61613. These are two different connections to two different endpoints.

Port 61613 is commonly used as the STOMP TCP port in some broker configurations, such as RabbitMQ when the STOMP plugin is enabled. This is not a universal default port for every broker. Check the STOMP TCP listener, plugins, port mappings, firewalls, and documentation of the broker in use. Do not use the broker's AMQP port or WebSocket port in place of the STOMP TCP port.

setVirtualHost("example-vhost") does not change the TCP address the relay connects to. It sets the host header in the STOMP CONNECT frame. This property is useful when the logical STOMP service address differs from the physical hostname the TCP socket connects to, or when the broker requires a specific virtual host.

## 6. Distinguishing Client Credentials and System Credentials

Spring provides two independent credential pairs.

### Client credentials

- Configured via setClientLogin(...) and setClientPasscode(...).
- Used when the relay creates TCP connections to the broker on behalf of WebSocket clients.
- A single configured pair applies to client connections managed by the relay.
- By default, the two values are guest and guest.

### System credentials

- Configured via setSystemLogin(...) and setSystemPasscode(...).
- Used for the shared system TCP connection.
- Serves messages sent to the broker by the server-side application without being tied to a client session, such as from a REST controller, service, or scheduled task.
- By default, the two values are guest and guest.

The two credential pairs should not be confused. Client credentials serve connections representing WebSocket clients; system credentials serve messages emitted by the server application.

**Important point about client CONNECT:** the broker relay always sets the login and passcode headers on every STOMP CONNECT frame that the relay forwards to the broker on behalf of a client. Therefore, any login and passcode sent by the browser in STOMP CONNECT are ignored. WebSocket clients do not need to send broker credentials from JavaScript.

This also means clientLogin/clientPasscode are shared broker credentials for client connections created by the relay, not individual usernames/passwords for each application account. Spring identifies application users via HTTP/WebSocket identity and Principal; broker authentication and application authentication are two separate layers.

## 7. Authenticating Users Over HTTP/WebSocket

A STOMP-over-WebSocket session starts with an HTTP request: the WebSocket handshake or SockJS HTTP requests. In a typical web application, Spring Security authenticates the HTTP request and stores the identity in the HTTP session. Spring associates that principal with the WebSocket/SockJS session and subsequent STOMP messages.

Typical authentication flow:

1. The user logs in through the application's HTTP authentication mechanism.
2. The browser opens a WebSocket handshake to the Spring endpoint, sending the appropriate cookie/session.
3. Spring retrieves the principal from the authenticated HTTP request and attaches it to the WebSocket session.
4. STOMP messages on the session carry the user identity managed by Spring.
5. Spring Security can use the principal and destination to check SEND/SUBSCRIBE permissions.

With STOMP over WebSocket, the protocol's login and passcode headers are not Spring's default user authentication mechanism. Do not use broker credentials as application user account login credentials.

If the application uses tokens instead of cookie-based HTTP sessions, design a token authentication step and attach a Principal to the message/session, typically using an authentication mechanism on the inbound channel. Do not pass a user token as the relay's clientPasscode.

## 8. Clients Connecting to Spring with STOMP.js

In an example with STOMP.js, brokerURL is the WebSocket endpoint of the Spring application:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000,

    onConnect: () => {
        client.subscribe("/topic/updates", (frame) => {
            console.log("Update:", frame.body);
        });
    },

    onStompError: (frame) => {
        console.error("Broker error:", frame.headers["message"]);
    }
});

client.activate();
~~~

In an HTTPS environment, the WebSocket endpoint typically uses wss://. With SockJS, the client uses webSocketFactory to create a SockJS connection instead of brokerURL.

The client only knows the Spring endpoint, such as /ws. It does not need to know the broker's internal hostname, STOMP TCP port, username, or passcode. Do not put broker login/passcode in JavaScript configuration; the relay will use the clientLogin/clientPasscode configured on the server.

## 9. Server Sending Messages via the System Connection

Messages generated by the server application and sent through the broker relay without being tied to a specific WebSocket client use the system connection. One example is a REST request that updates an order status and then broadcasts a notification to a topic:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishOrderUpdate(String orderId, String status) {
        OrderUpdate event = new OrderUpdate(orderId, status);
        messagingTemplate.convertAndSend("/topic/order-updates", event);
    }
}
~~~

Example payload:

~~~java
public record OrderUpdate(String orderId, String status) {
}
~~~

Because the send originates from the server and is not bound to a specific session, the relay uses the system connection and systemLogin/systemPasscode. The system connection's broker user needs appropriate permissions for the destinations that the server application will publish to or subscribe to according to the system configuration.

Conversely, if a client sends STOMP SEND to a broker destination, the frame is forwarded over that session's client connection. Not every message passing through the relay uses the system connection.

## 10. Heartbeats, Reconnect, and Broker Status

The broker relay exchanges heartbeats with the broker over the system connection. In Spring Framework, the default send and receive heartbeat intervals for the system connection are 10 seconds. They can be adjusted with:

- **setSystemHeartbeatSendInterval(milliseconds)**: interval for sending heartbeats when there is no other data to send.
- **setSystemHeartbeatReceiveInterval(milliseconds)**: maximum time to wait for a heartbeat from the broker when there is no other data.
- A value of 0 can be used to disable outgoing heartbeats or not require incoming heartbeats in the corresponding direction.

If the connection to the broker is lost, the relay keeps trying to reconnect; by default, retries occur every 5 seconds until successful. Distinguish WebSocket client state from system connection state: clients may remain connected to the application while the relay is disconnected from the broker.

Spring publishes BrokerAvailabilityEvent when the system connection is lost or re-established. Services that need to know whether the broker is available can listen for the event:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
public class BrokerAvailabilityListener {

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        if (event.isBrokerAvailable()) {
            System.out.println("STOMP broker is available");
        } else {
            System.out.println("STOMP broker is unavailable");
        }
    }
}
~~~

The application can use this status to pause unnecessary publish tasks, surface operational status, or retry at the business layer according to its own policy. Do not assume a publish call will succeed simply because a client's WebSocket handshake succeeded.

## 11. Managing Credentials and Broker Permissions

In real environments, avoid putting usernames/passwords directly in source code, committed configuration files, or logs. Values can be supplied via environment variables, a secret manager, or a secure configuration management system.

Example application.properties:

~~~properties
app.stomp.relay.host=${STOMP_RELAY_HOST:localhost${
app.stomp.relay.port=${STOMP_RELAY_PORT:61613${

app.stomp.relay.client-login=${STOMP_RELAY_CLIENT_LOGIN${
app.stomp.relay.client-passcode=${STOMP_RELAY_CLIENT_PASSCODE${

app.stomp.relay.system-login=${STOMP_RELAY_SYSTEM_LOGIN${
app.stomp.relay.system-passcode=${STOMP_RELAY_SYSTEM_PASSCODE${

app.stomp.relay.virtual-host=${STOMP_RELAY_VIRTUAL_HOST:${
~~~

Environment variables containing passcodes must be provided in the application runtime environment. The example above intentionally omits default values for passcodes to avoid accidentally running production with sample accounts.

Some operational principles:

1. **Do not keep guest/guest in production.** These are Spring relay defaults, not secure credentials for real deployments.
2. **Use least privilege.** The broker account for client connections should only have necessary permissions on the exchanges, queues, or destinations clients need to access. The system account should only have necessary permissions for server-emitted message flows.
3. **Understand client account scope.** Because the relay uses the same clientLogin/clientPasscode for connections on behalf of clients, the broker may see client connections under the same broker identity. Per-user application authorization must be enforced in Spring Security and the business layer, or via custom broker authentication/authorization design if deeper separation is needed.
4. **Do not log passcodes.** Avoid logging full STOMP CONNECT frames, configurations, or exceptions containing credentials.
5. **Protect the transport.** Use a private network and appropriate TLS between Spring and the broker; protect WebSocket with HTTPS/WSS when deploying over untrusted networks.
6. **Rotate secrets.** When changing credentials, update secrets and plan a restart/reconnect so the relay establishes broker connections using the new credentials.
7. **Separate environments.** Use distinct broker accounts and secrets for local, staging, and production.

## 12. Authorization in Spring and on the Broker

There are two different layers of control:

- **Broker authorization** determines which broker accounts can CONNECT, SEND, or SUBSCRIBE to which destinations.
- **Spring Security authorization** determines which application principals can send or subscribe to which destinations inside the Spring application.

For example, all client TCP connections can use a broker account restricted to the destination group allowed by the application. Spring Security continues checking each Principal before allowing SUBSCRIBE to /user/** or SEND to /app/**. The fact that clients do not know the broker password does not mean the application is automatically secure; WebSocket endpoints, origins, authentication, and message authorization must still be configured.

Do not use destination prefixes as the sole security boundary. Permissions must be checked against the principal and business rules, especially for private messages, tenant data, and actions affecting other accounts.

## 13. Common Errors and Diagnostics

### Connection refused or timeout

Common causes:

- Wrong relayHost or relayPort.
- Broker has not enabled the STOMP TCP listener or corresponding plugin.
- Spring is running in a container and using localhost pointing to the Spring container itself rather than the broker.
- Firewall, network policy, DNS, or port mapping is blocking the connection.

How to check: verify the hostname from Spring's runtime environment, the broker's TCP listener, port mappings, and broker startup logs. Test connectivity from the application's own container/host, not just from a developer machine.

### Broker rejects CONNECT

Common causes:

- Invalid clientLogin/clientPasscode for client connections.
- Invalid systemLogin/systemPasscode for the system connection.
- Account is locked, password expired, or broker does not allow the account to use STOMP.
- Incorrect virtualHost or the account lacks permissions on that virtual host.

How to check: determine whether the error occurs when the system connection initializes or when a new client connection is created; check the corresponding credentials and broker logs. Do not try sending broker passwords from the browser to work around a relay error.

### WebSocket client connects but receives no messages

Check:

1. The client subscribed to the right broker destination, such as /topic/updates.
2. The destination prefix declared in enableStompBrokerRelay matches the destination to be relayed.
3. The client broker account has SUBSCRIBE permission.
4. Whether the broker is actually publishing messages to that destination.
5. Whether the relay is still maintaining the client TCP connection and WebSocket session.

### Server publish fails while clients remain connected

Check the system connection, systemLogin/systemPasscode, SEND permissions of the system account, and BrokerAvailabilityEvent status. Active client WebSocket sessions do not prove the system connection is working.

### /app/... is not forwarded to the broker by the relay

This is usually confusion between application destinations and broker destinations. Destinations starting with /app are routed to Spring @MessageMapping methods after stripping the application prefix. Only destinations matching broker prefixes such as /topic or /queue are relayed under the example configuration.

### Heartbeat errors or periodic connection closures

Check bidirectional heartbeats, load balancer/proxy idle timeouts, broker heartbeat handling, and TCP logs. If changing intervals, ensure compatible configuration across components; do not set proxy timeouts shorter than the expected heartbeat interval.

### Only some instances can send messages

In a clustered deployment, check the broker endpoint, credentials, virtual host, network policies, and system connection status of each Spring instance. Each relay instance has its own system connection; one healthy instance does not prove the others connected successfully.

## 14. Deployment Checklist

- [ ] External broker has STOMP TCP listener enabled and allows Spring to connect.
- [ ] relayHost/relayPort point to the right address from Spring's runtime environment.
- [ ] Broker account for client connections is configured with clientLogin/clientPasscode.
- [ ] Broker account for system connection is configured with systemLogin/systemPasscode.
- [ ] Accounts have SEND/SUBSCRIBE permissions scoped to the proper destinations.
- [ ] virtualHost is configured when the broker requires a STOMP host header.
- [ ] WebSocket endpoint and HTTP authentication operate independently of broker credentials.
- [ ] Clients do not send broker login/passcode in STOMP CONNECT.
- [ ] Heartbeats, reconnect, and BrokerAvailabilityEvent are verified.
- [ ] Secrets are not in source control or logs.
- [ ] Broker connection limits accommodate the total number of client sessions plus Spring instances.

## 15. Key Takeaways

The STOMP broker relay maintains one shared system TCP connection for server-emitted messages and one separate client TCP connection per WebSocket client. systemLogin/systemPasscode authenticates the system connection; clientLogin/clientPasscode authenticates connections on behalf of clients. The relay automatically writes login/passcode into STOMP CONNECT frames sent to the broker, so WebSocket clients do not need to know broker credentials. Application users are authenticated via HTTP/WebSocket and Principal; access control is checked in Spring Security alongside broker ACLs. Understanding these connection and authentication layers helps configure the relay properly, scope permissions appropriately, and diagnose failures by pinpointing the exact failing connection.

## References

- [Spring Framework Reference — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework Reference — Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [StompBrokerRelayRegistration API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)