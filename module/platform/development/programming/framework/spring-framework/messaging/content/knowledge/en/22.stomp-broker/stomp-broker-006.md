# Virtual Hosts, TLS, and TCP Connection Configuration to a STOMP Broker in Spring Framework

## Objectives and Scope

When a Spring application uses a STOMP broker relay, Spring acts as a bridge between WebSocket/STOMP clients and an external message broker such as RabbitMQ or ActiveMQ. The relay forwards STOMP frames over TCP connections to the broker, then relays messages sent back by the broker to subscribed clients.

There are three settings that are easily confused yet solve three different concerns:

- **TCP host and port** identify the network address that the Spring process connects to.
- **Virtual host** is the value of the **host** header in the STOMP **CONNECT** frame, used to select a resource namespace or virtual host on the broker.
- **TLS** encrypts and authenticates peers on the TCP connection between the Spring application and the broker.

For example, the application can open TCP/TLS to **rabbitmq.internal:61614**, while sending the STOMP CONNECT header **host: /orders** to select a RabbitMQ virtual host named **/orders**. The DNS name, port, and virtual host do not have to match.

This section focuses on the connection from the **Spring broker relay to the broker over TCP**. The connection from the browser to the Spring application over WebSocket or **wss://** is a separate leg with its own TLS configuration.

## 1. STOMP Broker Relay and Connection Flow

### 1.1. Simple Broker and Broker Relay

Spring can enable the built-in simple broker via **enableSimpleBroker(...)**. This is a lightweight broker running inside the application, suitable for basic needs but lacking the full features of a standalone broker.

When a dedicated broker is needed, you can use **enableStompBrokerRelay(...)**. The relay forwards frames to an external broker over TCP. The external broker manages subscriptions, queues/topics, and message distribution according to its own capabilities.

### 1.2. Connection Model

A broker relay maintains:

1. One **system** TCP connection used for messages originating from server-side code, such as services or REST controllers sending via **SimpMessagingTemplate**. This connection is not a connection that receives messages for WebSocket client subscriptions.
2. One separate TCP connection per connected WebSocket client. The client's STOMP frames are relayed over the corresponding connection.

Therefore, for an application instance with N connected WebSocket clients, the broker normally sees N client connections plus one shared system connection. Each additional deployed application instance also maintains its own system connection.

~~~mermaid
flowchart LR
    C1[WebSocket client 1] -->|STOMP frames| S[Spring application]
    C2[WebSocket client 2] -->|STOMP frames| S
    S -->|TCP connection per client| B[External STOMP broker]
    S -->|Shared system TCP connection| B
    B -->|Messages for subscriptions| S
    S -->|WebSocket frames| C1
    S -->|WebSocket frames| C2
~~~

The relay both receives frames from clients to send to the broker and receives messages from the broker to forward back to the right WebSocket session. The TCP host/port is the broker's network address; destinations such as **/topic/orders** or **/queue/orders** are message addresses inside STOMP.

## 2. Distinguishing TCP Endpoint and Virtual Host

### 2.1. TCP Host and Port

**TCP host** is the DNS name or IP that the Spring application can resolve and reach. **TCP port** is the port the broker opens for STOMP over TCP. The port must be the STOMP listener, not the HTTP management port, AMQP port, or the Spring application's WebSocket port.

Example with a common RabbitMQ setup:

| STOMP Listener Type | Example Port | Meaning |
|---|---:|---|
| Unencrypted TCP | 61613 | Plain STOMP over TCP |
| TLS | 61614 | TLS-encrypted STOMP over TCP |

The actual port depends on the broker and deployment configuration. Do not assume every broker uses these ports.

### 2.2. Virtual Host in STOMP

In STOMP 1.1, the **CONNECT** frame includes a **host** header to specify the virtual host the client wishes to use. Spring provides **setVirtualHost(String)** on **StompBrokerRelayRegistration** to set that header value.

Example:

~~~java
relay.setVirtualHost("/orders");
~~~

This value is sent in the STOMP CONNECT header:

~~~text
CONNECT
accept-version:1.2
host:/orders
login:service-user
passcode:...
heart-beat:10000,10000

^@
~~~

The example frame above illustrates only the headers; passcode values should never be written to logs or real documentation.

With RabbitMQ, the **host** header selects the RabbitMQ virtual host. The virtual host must exist on the broker and the account used to connect must have appropriate permissions on that virtual host. RabbitMQ typically uses **/** as the default virtual host if STOMP CONNECT does not specify host and the broker is configured with that default.

### 2.3. Three Values to Configure Independently

| Property | Example | Where It Is Used |
|---|---|---|
| TCP host | rabbitmq.internal | DNS/IP for the TCP socket |
| TCP port | 61614 | STOMP TLS listener port |
| STOMP virtual host | /orders | host header of STOMP CONNECT |
| TLS server name/SNI | rabbitmq.internal | Server name used when verifying the TLS certificate |

Do not put the virtual host into **setRelayHost**. Do not put the port into **setVirtualHost**. When the broker uses virtual host **/orders** while the TCP endpoint is **rabbitmq.internal:61614**, the two values must be configured in their proper roles as shown in the example.

## 3. Configuring Broker Relay Over Plain TCP

If the broker only exposes an unencrypted STOMP TCP listener within a controlled internal network, you can configure the relay host and port directly. This is a connectivity configuration example, not an appropriate choice for every deployment environment.

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        StompBrokerRelayRegistration relay =
                registry.enableStompBrokerRelay("/topic", "/queue");

        relay.setRelayHost("rabbitmq.internal");
        relay.setRelayPort(61613);
        relay.setVirtualHost("/orders");

        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

In the example:

- Clients send messages to destinations prefixed with **/app** for Spring controllers to handle.
- **/topic** and **/queue** are forwarded to the external broker.
- The application opens TCP to **rabbitmq.internal:61613**.
- STOMP CONNECT sends the header **host: /orders**.

With this configuration, Spring uses the broker relay's default TCP client. To enable TLS or customize the TCP client more deeply, configure **setTcpClient(...)**.

## 4. Configuring STOMP Broker Relay with TLS

### 4.1. TLS on the Spring-to-Broker Leg

TLS on the relay connection protects STOMP frames as they travel between the Spring application and the broker. Configuring TLS here does not automatically enable TLS on the application's WebSocket endpoint.

Spring allows supplying a custom **TcpOperations<byte[]>** via **setTcpClient(...)**. One implementation approach is using **ReactorNettyTcpClient** with **StompReactorNettyCodec**. Reactor Netty's **TcpClient.secure()** enables TLS on the TCP client.

When using a custom TCP client, host and port must be set inside the **TcpClient** configuration itself. The **setRelayHost** and **setRelayPort** values on the relay registration are ignored once **setTcpClient** is called.

### 4.2. TLS Configuration with the Default Trust Store

The following example uses the default trust configuration of the JVM/Reactor Netty. The broker server certificate must be trusted by the active trust store and the hostname must match the certificate.

~~~java
package com.example.messaging;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.messaging.simp.config.StompBrokerRelayRegistration;
import org.springframework.messaging.simp.stomp.StompReactorNettyCodec;
import org.springframework.messaging.tcp.reactor.ReactorNettyTcpClient;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Value("${messaging.broker.tcp-host}")
    private String brokerHost;

    @Value("${messaging.broker.tcp-port}")
    private int brokerPort;

    @Value("${messaging.broker.virtual-host}")
    private String virtualHost;

    @Value("${messaging.broker.client-login}")
    private String clientLogin;

    @Value("${messaging.broker.client-passcode}")
    private String clientPasscode;

    @Value("${messaging.broker.system-login}")
    private String systemLogin;

    @Value("${messaging.broker.system-passcode}")
    private String systemPasscode;

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        StompBrokerRelayRegistration relay =
                registry.enableStompBrokerRelay("/topic", "/queue");

        relay.setVirtualHost(virtualHost);
        relay.setClientLogin(clientLogin);
        relay.setClientPasscode(clientPasscode);
        relay.setSystemLogin(systemLogin);
        relay.setSystemPasscode(systemPasscode);

        relay.setSystemHeartbeatSendInterval(10_000);
        relay.setSystemHeartbeatReceiveInterval(10_000);

        relay.setTcpClient(new ReactorNettyTcpClient<>(
                tcpClient -> tcpClient
                        .host(brokerHost)
                        .port(brokerPort)
                        .secure(),
                new StompReactorNettyCodec()
        ));

        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Configuration values can be placed in **application.yml**:

~~~yaml
messaging:
  broker:
    tcp-host: ${STOMP_BROKER_HOST:rabbitmq.internal}
    tcp-port: ${STOMP_BROKER_PORT:61614}
    virtual-host: ${STOMP_VIRTUAL_HOST:/}
    client-login: ${STOMP_CLIENT_LOGIN}
    client-passcode: ${STOMP_CLIENT_PASSCODE}
    system-login: ${STOMP_SYSTEM_LOGIN}
    system-passcode: ${STOMP_SYSTEM_PASSCODE}
~~~

Environment variables containing credentials should be supplied by a secret manager or the deployment platform's secret management mechanism. Do not commit real passcodes to source control.

### 4.3. Using a Private CA for an Internal Broker

If the broker uses a certificate signed by an internal CA not yet in the default trust store, add that CA to the trust store or configure a custom trust manager. The example below uses a CA PEM file:

~~~java
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import java.io.File;
import javax.net.ssl.SSLException;

private ReactorNettyTcpClient<byte[]> createTcpClientWithPrivateCa() {
    try {
        SslContext sslContext = SslContextBuilder.forClient()
                .trustManager(new File("/run/secrets/broker-ca.pem"))
                .build();

        return new ReactorNettyTcpClient<>(
                tcpClient -> tcpClient
                        .host(brokerHost)
                        .port(brokerPort)
                        .secure(ssl -> ssl.sslContext(sslContext)),
                new StompReactorNettyCodec()
        );
    }
    catch (SSLException ex) {
        throw new IllegalStateException(
                "Cannot initialize TLS trust for the STOMP broker", ex
        );
    }
}
~~~

In **configureMessageBroker**, use:

~~~java
relay.setTcpClient(createTcpClientWithPrivateCa());
~~~

Do not simultaneously call **setRelayHost** or **setRelayPort** expecting them to change the address of the custom TCP client; host and port are already set inside the lambda.

### 4.4. Mutual TLS (mTLS)

Standard TLS verifies the server certificate so the application knows it is connecting to the right broker. With mutual TLS, the broker also requires the application to present a client certificate to authenticate the reverse direction.

When the broker requires a client certificate, you can add **keyManager** to **SslContextBuilder**:

~~~java
SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(new File("/run/secrets/broker-ca.pem"))
        .keyManager(
                new File("/run/secrets/client-chain.pem"),
                new File("/run/secrets/client-private-key.pem")
        )
        .build();
~~~

This snippet replaces the **SslContext** creation in the private CA example. The private key must be protected like a secret. The broker must also be configured to require and verify client certificates; merely adding a certificate on the Spring side does not enable mTLS on the broker.

Do not disable certificate verification to bypass handshake errors. Inspect the CA chain, certificate expiration, SAN/hostname, SNI, and client certificate configuration if required by the broker.

## 5. Configuring the TLS Listener on the Broker

TLS must be enabled on both ends: the Spring TCP client and the broker's STOMP listener. Simply calling **secure()** in Spring will not turn a plain TCP listener into a TLS listener.

### 5.1. RabbitMQ STOMP Plugin Example

RabbitMQ needs the STOMP plugin enabled and a TLS listener configured. Abbreviated configuration example:

~~~ini
ssl_options.cacertfile = /etc/rabbitmq/tls/ca.pem
ssl_options.certfile = /etc/rabbitmq/tls/server.pem
ssl_options.keyfile = /etc/rabbitmq/tls/server-key.pem

stomp.listeners.tcp = none
stomp.listeners.ssl.1 = 61614
~~~

This example disables the plain TCP STOMP listener and opens a STOMP TLS listener on port **61614**. Filenames, paths, and ports should match the actual environment.

If deploying mTLS, the broker needs to require a client certificate and verify the CA, for example with the corresponding RabbitMQ options:

~~~ini
ssl_options.verify = verify_peer
ssl_options.fail_if_no_peer_cert = true
~~~

When these options are enabled, the client must send a certificate trusted by the broker. The broker's TLS configuration and Spring's trust/key manager configuration must align.

### 5.2. RabbitMQ Virtual Host

With RabbitMQ, the STOMP CONNECT **host** header selects the virtual host. Example:

~~~java
relay.setVirtualHost("/orders");
~~~

The **/orders** virtual host must be created beforehand on RabbitMQ, and the STOMP account configured in the relay must have appropriate permissions for that virtual host. If using the default virtual host **/**, you can explicitly configure **setVirtualHost("/")** to avoid relying on broker defaults.

## 6. Distinguishing Client and System Credentials

The broker relay uses two sets of STOMP credentials:

| Setting | Which Connection Uses It | Purpose |
|---|---|---|
| **clientLogin / clientPasscode** | Each TCP connection opened on behalf of a WebSocket client | Authenticates client connections through the relay |
| **systemLogin / systemPasscode** | One shared system TCP connection | Authenticates messages sent to the broker by server-side code |

Spring's relay always overwrites **login** and **passcode** on CONNECT frames forwarded on behalf of clients. Therefore, credentials sent directly by the browser in STOMP CONNECT are not used as broker authentication credentials. Clients should authenticate with the application via the HTTP/WebSocket handshake and let Spring Security determine the session's **Principal**.

An important architectural point: client connections via the relay generally share the same **clientLogin/clientPasscode** pair. The broker may therefore see the same broker account for many WebSocket users. If per-user authorization is needed, design an appropriate authentication/authorization layer and identity mapping; do not assume the relay forwards arbitrary credentials from the browser to the broker.

Use broker accounts with least privilege. You can separate system and client accounts to restrict permissions for server-emitted messages versus client-originated messages.

## 7. Heartbeats, Reconnect, and Broker Status

### 7.1. System Connection Heartbeats

The relay sends and receives STOMP heartbeats over the system TCP connection. By default, Spring uses 10-second intervals for sending and receiving. They can be tuned via:

~~~java
relay.setSystemHeartbeatSendInterval(10_000);
relay.setSystemHeartbeatReceiveInterval(10_000);
~~~

Values are in milliseconds. Setting 0 disables the corresponding heartbeat. Coordinate values with the broker's heartbeat capabilities and network infrastructure timeouts; do not arbitrarily reduce intervals because doing so increases traffic and checking overhead.

### 7.2. Broker Disconnection

If the system connection is lost, the relay automatically attempts to reconnect on a default 5-second interval until the connection succeeds. Spring publishes **BrokerAvailabilityEvent** whenever the system connection status changes. Services can listen for this event to know whether the broker is ready and avoid sending messages when the relay is unavailable.

When sending via **SimpMessagingTemplate**, the application must still handle send failures such as **MessageDeliveryException**. BrokerAvailabilityEvent reflects the state of the system connection; it does not replace tracking individual WebSocket client sessions.

TCP connections on behalf of WebSocket clients are not automatically restored merely because the system connection reconnected. Clients need to detect disconnection and perform STOMP/WebSocket reconnection according to an appropriate retry policy.

## 8. Connection Testing and Troubleshooting

### 8.1. Layer-by-Layer Verification

1. **DNS and routing:** can the container/VM running Spring resolve the broker host?
2. **TCP port:** do firewalls, security groups, Kubernetes NetworkPolicy, or routing allow outbound traffic from the application to the STOMP listener?
3. **TLS handshake:** does the broker expose a TLS listener on the right port? Is the certificate chain trusted? Does SAN match the hostname?
4. **STOMP CONNECT:** are credentials correct? Does the **host** header select the right virtual host?
5. **Broker authorization:** does the user have permissions to connect, send, subscribe, and access the required destinations?
6. **Message flow:** can clients connect over STOMP to Spring, subscribe to the right destination, and receive messages through the broker relay?

### 8.2. Network Diagnostic Commands

Test the TCP port from a machine/container with the corresponding tools:

~~~bash
nc -vz rabbitmq.internal 61614
~~~

This command only verifies that the TCP port accepts connections; it does not verify TLS or STOMP authentication.

Verify the TLS certificate and hostname:

~~~bash
openssl s_client -connect rabbitmq.internal:61614 -servername rabbitmq.internal -CAfile /run/secrets/broker-ca.pem -verify_return_error
~~~

If the TLS handshake fails, inspect the certificate chain, CA, validity period, hostname/SNI, port, and mTLS requirements. If TLS succeeds yet Spring still fails to connect, next inspect STOMP CONNECT headers, credentials, and virtual host in the broker logs.

### 8.3. Common Errors Table

| Symptom | Possible Cause | Diagnostic Direction |
|---|---|---|
| Connection refused | Wrong host/port or broker has not opened the listener | Check TCP host, port, and STOMP listener status |
| Connection timeout | Firewall, routing, or DNS | Check DNS, network policy, security groups, and outbound rules |
| SSL handshake failure | TLS connection to plain TCP port, untrusted CA, or certificate hostname mismatch | Check TLS listener, trust store, SAN, and SNI |
| Broker reports invalid virtual host | host header does not match virtual host | Check setVirtualHost and verify the virtual host exists on the broker |
| ACCESS_REFUSED / authentication failure | Wrong credentials or user not permitted | Check client/system credentials and broker permissions |
| Client connections drop when broker restarts | Client-side TCP/STOMP connections need to reconnect | Perform reconnect on client and monitor broker availability events |
| Server fails to send messages when broker is down | System connection is not ready | Listen for BrokerAvailabilityEvent and handle MessageDeliveryException |

## 9. Monitoring Connection Counts and Operations

With N WebSocket clients connected to a Spring instance, the number of relay TCP connections is typically roughly **N + 1**: one connection per client and one shared system connection. When deploying multiple Spring instances, each instance has its own system connection and client connection counts depend on how clients are distributed across instances.

Spring provides **WebSocketMessageBrokerStats** to monitor session counts, STOMP frames, and broker relay details. The broker relay's TCP Connections metric helps cross-check TCP connection counts against the model above. When connection counts are higher than expected, check session disconnects, reconnect loops, multiple instances, or clients failing to close sessions cleanly.

Before deploying to production, confirm:

- The broker has enabled the STOMP listener on the right protocol and port.
- The Spring application can reach the TCP endpoint from the actual runtime network.
- The virtual host exists and the broker user has appropriate permissions.
- TLS trust chain, hostname/SNI, and mTLS (if applicable) work.
- Client and system credentials are provided from a secret manager.
- Heartbeats and reconnects align with broker, load balancer, and network timeouts.
- Broker connection limits accommodate total WebSocket clients across all instances plus system connections.

## 10. Design Principles

1. **Separate the three configuration layers properly.** TCP host/port is the socket address; virtual host is a STOMP header; TLS is the transport security layer.
2. **Use a STOMP TLS listener when enabling a secure TCP client.** Do not send a TLS handshake to a plain-TCP-only port.
3. **Verify certificates.** Trust valid CAs and check hostname/SNI; do not disable verification to bypass errors.
4. **Restrict broker permissions.** Use separate credentials for system/client when appropriate and grant only required permissions.
5. **Manage secrets safely.** Never put passcodes, private keys, or tokens in source control or logs.
6. **Design reconnect on both sides.** The relay automatically reconnects the system connection; WebSocket clients still need their own reconnect policy.
7. **Plan connection counts ahead.** Each WebSocket client opens one TCP connection to the broker, in addition to the shared system connection per Spring instance.

## 11. References

- [Spring Framework – External STOMP Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework – Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [StompBrokerRelayRegistration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)
- [Reactor Netty – TCP Client, SSL and TLS](https://projectreactor.io/docs/netty/release/reference/tcp-client.html)
- [ReactorNettyTcpClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/tcp/reactor/ReactorNettyTcpClient.html)
- [Spring Framework – Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [RabbitMQ – STOMP Plugin, TLS and Virtual Hosts](https://www.rabbitmq.com/docs/stomp)
