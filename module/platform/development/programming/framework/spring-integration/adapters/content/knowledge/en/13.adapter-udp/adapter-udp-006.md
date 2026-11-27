# Socket timeout and lifecycle of UDP adapters in Spring Integration

## Learning objectives

After completing this lesson, you will be able to:

- Explain how **socket timeout** (`SO_TIMEOUT`) affects UDP datagram reception, and why timing out **does not mean the connection was dropped**.
- Distinguish between `so-timeout`, `ack-timeout`, `MessageChannel` `send-timeout`, business timeouts, and shutdown deadlines.
- Configure a UDP inbound adapter using Java/Java DSL, check `isRunning()`, `isListening()`, and the `UdpServerListeningEvent`.
- Accurately describe the **create → start → bind socket → receive datagrams → stop → close socket** lifecycle and where errors can occur.
- Build intentional tests: leave the socket idle past a timeout, send packets again, stop the adapter, try sending while stopped, then restart.
- Choose how to orchestrate startup, shutdown, retries, and observability for a Spring Integration flow connecting to external systems.

This lesson belongs to the **Adapter UDP** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems to Spring Integration using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, then handles message contracts, errors, and lifecycles when integrating files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. For UDP, two points require attention: **I/O wait timeouts** and the **actual listener state**, because UDP does not maintain a long-lived TCP connection.

## 1. Scenario: collector receives no datagrams for 30 seconds

A Spring Boot collector listens on UDP `12016`. A device sends telemetry every 5 seconds:

~~~text
v=1;sensor=node-7;seq=105;tempC=26.5
~~~

Initially the system works. Then the device stops sending for 30 seconds due to a power outage. Operators notice messages stop entering the `MessageChannel`.

There are three separate questions:

1. **Is the socket still open and the adapter still listening?** If yes, the receiver can still accept the next packet.
2. **Did a single `receive()` wait expire?** If `SO_TIMEOUT=1000 ms` is configured, each `receive()` call expires after roughly 1 second.
3. **Is the device still alive?** The absence of new packets is only a *missing data* signal; it does not by itself prove the device died, the network failed, or the adapter stopped.

~~~mermaid
flowchart LR
    S["Device / UDP sender"] -->|"Datagram when data is sent"| U["UnicastReceivingChannelAdapter"]
    U -->|"Message<byte[]>"| C["MessageChannel"]
    C --> H["Business handler"]
    T["SO_TIMEOUT: wait time for<br/>one DatagramSocket.receive()"] -.-> U
    L["SmartLifecycle: start / stop"] -.-> U
~~~

**Key takeaway:** a `SocketTimeoutException` caused by no packet arriving during the wait window is different from a UDP connection being closed. UDP has no connection handshake or "peer closed connection" notification like TCP.

## 2. How does DatagramSocket SO_TIMEOUT work?

In Java, a UDP socket receives datagrams via `DatagramSocket.receive(DatagramPacket)`. By default, if the timeout is **0**, the receive call can **block indefinitely** until a datagram arrives or another event/error occurs, such as closing the socket.

When setting `setSoTimeout(1000)`:

- Each `receive()` call waits for a datagram up to roughly **1000 ms**.
- If no datagram arrives, the call throws **`SocketTimeoutException`**.
- The socket **remains valid** after the timeout; the program can call `receive()` again.
- A timeout **does not automatically create an empty `Message`** to send into Spring Integration.
- A timeout **does not trigger client retransmission** and does not make UDP more reliable.

Positive values are in **milliseconds**; 0 means wait indefinitely. Actual timeout timing may drift from the configured number due to scheduling and system load. This is an I/O wait timeout, **not a heartbeat timer for the sending device**.

### 2.1. Plain Java example to understand the semantics

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.SocketTimeoutException;
import java.net.SocketException;
import java.io.IOException;

public class UdpReceiveTimeoutDemo {

    public static void main(String[] args) throws IOException {
        try (DatagramSocket socket = new DatagramSocket(12016)) {
            socket.setSoTimeout(1000); // 1 second per receive()

            byte[] buffer = new byte[1024];
            for (int attempt = 1; attempt <= 5; attempt++) {
                DatagramPacket packet =
                        new DatagramPacket(buffer, buffer.length);
                try {
                    socket.receive(packet);
                    System.out.println("Received bytes: " +
                            packet.getLength());
                } catch (SocketTimeoutException timeout) {
                    System.out.println("Idle receive timeout #" + attempt);
                    // Socket remains open; the loop continues.
                }
            }
        } // try-with-resources closes DatagramSocket
    }
}
~~~

This program is independent of Spring Integration to illustrate `SO_TIMEOUT` semantics precisely. **Do not run it simultaneously** with a UDP inbound adapter bound to the same port `12016`; two processes will conflict on the port. In a Spring application, the adapter manages the receive loop and socket lifecycle itself, so you do not write a `for`/`while` loop like this snippet.

### 2.2. SO_TIMEOUT is not a device health signal

Suppose `SO_TIMEOUT=1000 ms` while a sensor only sends **every 10 seconds**: between sends there will be many expired waits. That is normal behavior. Treating every timeout as an error would flood dashboards with false alarms.

To detect a silent sensor, store **`lastSeenAt`** per verified sensor ID, compare against the expected send interval, and add margin for jitter and network loss rules. That is a **business timeout** in the telemetry processing layer, not socket `SO_TIMEOUT`.

## 3. Types of timeouts commonly confused

| Timeout type | Configuration / mechanism | What is it waiting for? | When it expires |
|---|---|---|---|
| **UDP receive socket timeout** | `so-timeout`, `setSoTimeout(ms)` | A single `DatagramSocket.receive()` to receive a packet | `SocketTimeoutException`; socket can keep receiving |
| **UDP ACK timeout** | `ack-timeout` when `acknowledge=true` | ACK per Spring Integration UDP's protocol | Outbound may throw an exception because sufficient ACKs did not arrive in time |
| **MessageChannel send timeout** | e.g., `send(message, timeout)` | Channel accepting a message when it might block | May return `false` or error depending on implementation; unrelated to UDP ACK |
| **Gateway reply timeout** | e.g., `reply-timeout` on a suitable gateway | Reply message at the integration layer | Gateway times out waiting for a reply per contract |
| **Device inactivity timeout** | Application's `lastSeenAt` policy | Fresh telemetry/heartbeat from each device | Emits alert or updates sensor status |
| **Shutdown/drain timeout** | Orchestration, executor, broker procedures | In-flight work finishing before process exits | May force-stop after deadline; needs policy for unfinished messages |

### 3.1. Receive timeout and ACK timeout do not replace each other

A UDP sender normally only hands datagrams off to the network layer. If **application-level ACK** supported by Spring Integration is enabled, the sender needs parameters like `ack-host`, `ack-port`, `ack-timeout`, and the receiver must understand the ACK framing. If ACKs do not arrive in time, the outbound adapter can raise an error.

XML example *illustrating a sender with ACK specifically*:

~~~xml
<int-ip:udp-outbound-channel-adapter
    id="telemetryUdpSender"
    channel="toUdp"
    host="collector.example.test"
    port="12016"
    acknowledge="true"
    ack-host="sender.example.test"
    ack-port="12017"
    ack-timeout="3000"/>
~~~

For real use, replace both hosts with valid network addresses and configure the `int-ip` namespace matching your version; the receiver must support Spring Integration ACKs. **Do not enable ACK on one side only** when the collector reads raw UDP bytes.

Three things must be distinguished:

- **`so-timeout`** expiring on the **receiver**: one `receive()` wait finished because no packet arrived.
- **`ack-timeout`** expiring on the **sender**: no matching ACK arrived within the wait window.
- Missing `ACK` **does not prove the datagram was lost**; the receiver may have received it while the reply was lost or ACK processing was slow.

With multicast, `min-acks-for-success` specifies the minimum expected ACKs; it does not guarantee every multicast member received and processed the business payload.

### 3.2. Why is `so-timeout` on outbound different from inbound?

A UDP outbound handler primarily performs **sending**; with plain UDP, it does not await a response message like TCP request/reply. Socket timeout options on an outbound endpoint are defined by the socket API, but **should not be interpreted as a deadline for successful datagram delivery at the receiver**. If a response deadline is required, design an explicit ACK or business protocol, or choose another transport.

## 4. Lifecycle of a UDP inbound adapter

**`UnicastReceivingChannelAdapter`** is a Spring-managed endpoint. It implements Spring Integration lifecycle capabilities, including **`start()`**, **`stop()`**, **`isRunning()`**, and the **`autoStartup`** property. Additionally, UDP inbound adapters expose **`isListening()`** to reflect whether actual listening has begun.

~~~mermaid
stateDiagram-v2
    [*] --> Created: Bean instantiated
    Created --> Starting: Spring lifecycle / start()
    Starting --> Listening: Socket bound successfully
    Listening --> Listening: Datagram arrives / receive timeout
    Listening --> Stopping: stop() / context shutdown
    Stopping --> Stopped: Stop receive loop, release socket
    Stopped --> Starting: start() again
~~~

The diagram illustrates the expected flow, not every state transition on exceptions. If **port binding fails** or a socket error occurs, the adapter may never reach the listening state and the system must monitor startup failures.

| Stage | What typically happens | What to verify |
|---|---|---|
| **Bean created** | Spring instantiates adapter and sets output channel, port, socket options | Configuration is valid; channel has subscribers |
| **Start** | Lifecycle calls start according to phase/autoStartup | Do not assume socket bind succeeded solely because ApplicationContext started |
| **Listening** | UDP socket is bound and receive loop is active | `isListening()` or `UdpServerListeningEvent` |
| **Receiving packets** | Adapter reads datagrams and emits `Message<byte[]>` | Byte payload, source headers, receive rate, processing errors |
| **Stop** | Receive loop stops; socket stops accepting for endpoint | Datagrams sent while stopped may be lost |
| **Restart** | Adapter restarts/rebinds per config | Port/interface remains available; readiness re-established |

**Do not equate `isRunning()` with `isListening()`.** `isRunning()` reflects lifecycle state, whereas `isListening()` is a dedicated signal useful for knowing the UDP listener is actively listening. During transitions or bind failures, the two states can differ. For readiness or launching UDP-dependent test clients, prefer the **listening event** or an equivalent observed signal.

## 5. Java configuration: SO_TIMEOUT and endpoint management

### 5.1. Dependencies

In Spring Boot with dependency management:

~~~xml
<!-- Inside <dependencies> of pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

### 5.2. Creating an inbound adapter as a bean

The following example illustrates **Spring Integration 7.x**; inbound class packages moved to `org.springframework.integration.ip.udp.inbound`. For **Spring Integration 6.x**, import `org.springframework.integration.ip.udp.UnicastReceivingChannelAdapter` accordingly.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.ip.udp.inbound.UnicastReceivingChannelAdapter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class UdpTimeoutConfiguration {

    public static final int PORT = 12016;

    @Bean("udpInput")
    public MessageChannel udpInput() {
        return new DirectChannel();
    }

    @Bean("udpReceiver")
    public UnicastReceivingChannelAdapter udpReceiver(
            @Qualifier("udpInput") MessageChannel input) {

        UnicastReceivingChannelAdapter adapter =
                new UnicastReceivingChannelAdapter(PORT);

        adapter.setOutputChannel(input);
        adapter.setSoTimeout(1000);         // Receive timeout: 1 second
        adapter.setReceiveBufferSize(2048); // Buffer for 1 datagram
        adapter.setAutoStartup(true);       // Let Spring start it automatically
        return adapter;
    }
}
~~~

`setSoTimeout(1000)` configures the socket receive wait time. When the wait expires with no packet, **the adapter continues its receive loop** under normal operation. The application **does not need to catch `SocketTimeoutException` in the service activator**, as that exception occurs inside the socket-reading layer when there is no message to dispatch.

`setReceiveBufferSize(2048)` is the buffer used for a single datagram; it differs from `setSoReceiveBufferSize(...)`, which requests the **kernel socket** receive buffer size. Size it according to max payload and framing between both systems.

### 5.3. Message handler

~~~java
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class UdpTelemetryReceiver {

    private static final Logger log =
            LoggerFactory.getLogger(UdpTelemetryReceiver.class);

    @ServiceActivator(inputChannel = "udpInput")
    public void receive(Message<byte[]> message) {
        byte[] payload = message.getPayload();
        if (payload.length == 0 || payload.length > 512) {
            log.warn("UDP payload size rejected: {}", payload.length);
            return;
        }

        // Size-check example; production must validate UTF-8/schema.
        String text = new String(payload, StandardCharsets.UTF_8);
        log.info("UDP telemetry received: {}", text);
    }
}
~~~

**If no datagram arrives**, `receive(...)` on the service activator **is not called**. Even when `setSoTimeout(1000)` causes repeated socket receive timeouts, the system does not generate synthetic messages. Only actually received messages pass through the channel.

### 5.4. Equivalent Java DSL configuration

If using Java DSL, replace the *entire `udpReceiver` bean* in section 5.2 with an `IntegrationFlow` (keeping the channel/handler). **Do not register both listeners on the same port**, to avoid socket conflicts.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;

@Configuration
public class UdpTimeoutFlowConfig {

    @Bean
    public IntegrationFlow udpTimeoutFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(12016)
                        .soTimeout(1000)
                        .receiveBufferSize(2048))
                .channel("udpInput")
                .get();
    }
}
~~~

Java DSL sets `soTimeout` on the inbound adapter; it does not mean messages are automatically emitted every 1000 ms. If you want scheduled heartbeats, use a separate flow with an appropriate trigger. A **poller** is not the mechanism adapters use to read UDP packets.

## 6. Observing when the listener is ready

### 6.1. `UdpServerListeningEvent`

Spring Integration publishes **`UdpServerListeningEvent`** once the inbound UDP adapter has started and begun listening. This event is far more reliable than sleeping blindly or inferring readiness from Spring Boot's "Started Application" log line.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.integration.ip.udp.UdpServerListeningEvent;
import org.springframework.stereotype.Component;

@Component
public class UdpListeningObserver {

    private static final Logger log =
            LoggerFactory.getLogger(UdpListeningObserver.class);

    @EventListener
    public void onUdpListening(UdpServerListeningEvent event) {
        log.info("UDP inbound listener ready on port={}", event.getPort());
    }
}
~~~

The event exposes `getPort()`. When deploying **multiple** UDP listeners, also inspect the event's source or adapter identifier to avoid confusing events across listeners. **Do not treat the listening event as proof the receiver received datagrams from an external network**: firewalls, DNS, NAT, and network paths can still block packets.

### 6.2. `isRunning()` vs. `isListening()`

When interacting with the adapter bean directly:

~~~java
// Example inside a component injected with the udpReceiver bean:
boolean lifecycleActive = udpReceiver.isRunning();
boolean socketListening = udpReceiver.isListening();
~~~

Each value serves a distinct purpose:

- `isRunning()`: Spring lifecycle flag indicating the endpoint is active.
- `isListening()`: receiver has entered the UDP listening state, typically the better readiness signal.
- **Count of recently received messages**: a *separate* metric reflecting traffic and business heartbeats, not captured by either boolean.

Read these signals at appropriate moments; while stop/start transitions are underway, values may change between checks.

### 6.3. Port 0 in test environments

For a unicast UDP listener, you can configure **port `0`** so the OS assigns an ephemeral free port. Once the adapter is actually listening, retrieve the assigned port from `UdpServerListeningEvent.getPort()` or `adapter.getPort()` per your version's API.

This is useful for parallel integration tests because it avoids hardcoding shared port numbers. **Only send test datagrams after receiving the listening event or confirming state**; if sent too early, UDP has no network backlog waiting for an application to open its socket.

## 7. Controlled start, stop, and restart

By default, Spring manages the adapter lifecycle alongside `ApplicationContext`. Calling `start()`/`stop()` manually is useful in tests or **controlled** maintenance operations, but should not be overused inside ordinary request handlers.

Example component injecting the adapter bean created in section 5.2:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.ip.udp.inbound.UnicastReceivingChannelAdapter;
import org.springframework.stereotype.Component;

@Component
public class UdpListenerControl {

    private final UnicastReceivingChannelAdapter receiver;

    public UdpListenerControl(
            @Qualifier("udpReceiver")
            UnicastReceivingChannelAdapter receiver) {
        this.receiver = receiver;
    }

    public boolean isReady() {
        return receiver.isRunning() && receiver.isListening();
    }

    public void pause() {
        receiver.stop();
    }

    public void resume() {
        receiver.start();
        // Wait for UdpServerListeningEvent before reporting actually ready.
    }
}
~~~

**Be careful naming it "pause":** `stop()` halts the endpoint and releases receiving resources; it **does not create a temporary buffer** for datagrams arriving while stopped. Depending on timing and OS, datagrams sent while no socket is listening can be dropped. After calling `start()`, lost packets **are not replayed automatically**.

When an application needs no manual control, use `autoStartup` as configured and let Spring close endpoints on context shutdown. With interdependent endpoints, use lifecycle phases or application orchestration to start consumers/services in order; a listening event is the exact signal for a test sender to begin transmitting.

### 7.1. Restart failure modes

- **Port already taken:** another process bound the UDP port while the listener was stopped; rebinding fails.
- **Network interface disappeared/changed:** binding to an old `local-address` or multicast group may no longer be valid.
- **Wrong shutdown/startup order:** upstream services send before the receiver is ready, dropping datagrams.
- **External socket ownership:** if the application supplies a custom `DatagramSocket` or deeply customizes it, clarify who owns closing and reopening resources.
- **In-flight messages:** stopping the listener does not mean all downstream async handlers have finished processing and durably persisted data.

Do not use `Thread.sleep(...)` in tests as proof the listener started; waiting on events or bounded readiness predicates is far more reliable.

## 8. Graceful shutdown: what are UDP's limits?

When Spring Boot stops during a deployment, scale-down, or SIGTERM, you may need to:

1. **Stop generating new work** upstream if orchestration supports it.
2. **Stop accepting new UDP packets** at the appropriate stage of shutdown.
3. **Allow already-received work** in internal queues or brokers to finish within a deadline.
4. **Close sockets, executors, and resources** via Spring's managed lifecycle.
5. **Check for lost/duplicate packets** and recover per business contract once the new instance is active.

~~~mermaid
sequenceDiagram
    participant P as Sender
    participant L as Old UDP listener
    participant Q as Message pipeline
    participant N as New UDP listener

    P->>L: Datagram 101
    L->>Q: Message 101
    Note over L: Shutdown begins
    L--xP: Stop listening
    P-->>L: Datagram 102 during stop window
    Note over P,L: Datagram 102 may be lost
    Note over N: Start / bind / listening
    P->>N: Datagram 103
    N->>Q: Message 103
~~~

This is a **UDP limitation**: there is no session enabling the receiver to signal backpressure and seamlessly hand over queued packets to another instance. A UDP-capable load balancer can route packets to healthy instances, yet you must verify session affinity rules, timeouts, routing, and forwarding behavior in your environment.

If the business cannot lose events during a rolling deployment, tweaking `so-timeout` or `terminationGracePeriodSeconds` alone **is not enough**. You need durable storage/ACKs/retries/outbox or an appropriate transport change.

### 8.1. Coordinating lifecycles across endpoints

Suppose a flow receives UDP and writes to a database:

~~~mermaid
flowchart LR
    S["UDP sender"] --> U["UDP inbound adapter"]
    U --> C["MessageChannel"]
    C --> V["Validate / Transform"]
    V --> DB["Database"]
~~~

With `DirectChannel`, a synchronous handler can hold the reader thread long if the database slows down. On stop, a message may be mid-flight. With `ExecutorChannel` or queues, there is also pending queued work. Clearly define:

- Which component stops accepting new messages first.
- How long to wait for in-flight handlers and the policy when that deadline expires.
- Whether business-layer retries can produce duplicate records.
- Which metric proves data was committed, separate from received-datagram counts.

Configuring `SO_TIMEOUT` does not control `ServiceActivator` execution time or database commit duration.

## 9. Testing lifecycle and socket timeout

### 9.1. Sending a test packet from PowerShell

Use Spring Boot with `UdpTimeoutConfiguration` and `UdpTelemetryReceiver`. Open PowerShell on the same machine:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(
        "v=1;sensor=node-7;seq=105;tempC=26.5"
    )
    [void]$client.Send($bytes, $bytes.Length, "127.0.0.1", 12016)
}
finally {
    $client.Dispose()
}
~~~

If the listener is ready, handler logs should show telemetry received. The sender receives no ACK by default and must not conclude the packet was processed from `Send` alone.

### 9.2. Testing "no packets" across multiple SO_TIMEOUT intervals

- Set `soTimeout=1000` ms and **send nothing** for around 5 seconds.
- Check `receiver.isRunning()` and `receiver.isListening()`; the receiver should remain active normally.
- Confirm 5 synthetic messages do not appear on `udpInput`. Timeout is an internal I/O operation.
- Afterward, send a valid datagram; the handler must keep receiving packets **without restarting the adapter**.

Expected results under stable conditions:

| Observation | Expectation | Why |
|---|---|---|
| No datagram for 5 seconds | No new messages | Adapter emits only when a datagram actually arrives |
| SO_TIMEOUT = 1000 ms | No restart required | Timeout does not close the socket |
| Send after 5 seconds idle | Received normally | Receive loop continues |
| Sensor stops sending on schedule | Requires a separate `lastSeenAt` metric | SO_TIMEOUT does not measure business freshness |

### 9.3. Testing stop/start

In a test environment or via a protected internal maintenance mechanism:

1. Wait for `UdpServerListeningEvent` or `isListening()` before sending packet #1.
2. Call `receiver.stop()`; observe the listener stops accepting packets.
3. Send datagram #2 while the listener is stopped. Do not assume the datagram will be retained.
4. Call `receiver.start()`; **wait for actual listening** rather than just method return.
5. Send datagram #3; verify the handler receives the new packet again.
6. Check sequences: if packet #2 is missing, that is expected possible behavior while the receiver was paused.

Because UDP does not guarantee delivery, the test verifies **receiving capability after restart**, not overall delivery reliability from a single send.

### 9.4. Testing a port-bind failure

Open another process bound to UDP `12016`, then try starting the adapter on that port. Depending on OS and socket options, binding may fail with an error like "Address already in use".

How to diagnose:

- Check ports and local addresses of processes using UDP.
- Verify you did not accidentally register **two inbound adapters** on one port inside the same Spring context.
- Do not randomly change `SO_TIMEOUT`; it does not fix port conflicts.
- Check startup error logs and listening events. Without a ready signal, do not send test data and conclude the handler is broken.

When running parallel tests, use dynamic port `0` with unicast listeners and obtain the actual port from the listening event.

## 10. Errors, exceptions, and error channels

| Scenario | Where error occurs | How to observe/handle |
|---|---|---|
| No packet before SO_TIMEOUT | Socket receive | Normal timeout; do not mark message processing as failed |
| Port cannot be bound | Startup/listener | Socket/bind error logs, process checks, and readiness |
| Socket closed while receiving | Listener lifecycle | Distinguish intentional stop from abnormal socket failure |
| Datagram truncated | Receive buffer/transport | `check-length` when both sides match; properly sized buffers |
| Handler decode/validate fails | Message processing | Validation, error channel/exception policy, invalid metrics |
| Handler DB/broker fails | Downstream | Controlled retries, idempotency, durable storage as required |
| Outbound ACK wait expires | UDP outbound ACK handling | ACK timeout error; distinguish received vs. unknown processing |
| Missing messages during shutdown | Listener stopped | Track deploy windows and packet-loss behavior, design additional guarantees |

Spring Integration UDP inbound endpoints support **`error-channel`** to handle downstream errors per the `ErrorMessage`/`MessagingException` contract. This **does not mean** every normal socket `SO_TIMEOUT` sends an `ErrorMessage` to that channel.

Example error-handling path in Spring Integration:

~~~text
UDP adapter -> udpInput -> parse -> validate -> service
                                      |
                               processing error
                                      v
                                 errorChannel
                                      |
                             classify / metric / log
~~~

Clearly separate which errors enter the error channel from errors occurring **before a message is created**. Packets blocked by a firewall or lost in transit cannot enter Spring's error channel because the application never received them.

## 11. Purpose-built observability and health checks

A useful dashboard relies on multiple independent signals:

| Metric/Signal | What it reflects |
|---|---|
| `udp_listener_running` | Adapter lifecycle state |
| `udp_listener_listening` | UDP socket listening readiness |
| `udp_receive_total` | Datagrams reaching the app and accepted by mapper/channel |
| `udp_invalid_total` | Payloads rejected due to format, size, version |
| `udp_handler_error_total` | Downstream processing errors |
| `sensor_last_seen_seconds` or `lastSeenAt` | Data freshness per sensor |
| `udp_ack_timeout_total` | Sender ACK timeouts when ACK is enabled |
| `udp_sequence_gap_total` | Missing sequence gaps per business source |

**Distinguish three operational states:**

- **Liveness**: the process is alive and main loops are not deadlocked.
- **Readiness**: the listener is bound, listening, and essential channels/handlers are ready.
- **Freshness**: devices are sending sufficiently recent data per business rules.

An endpoint can be *live + ready* while sensor data is stale; conversely, a process can be *live* while the UDP port failed to bind. Therefore, health checks relying solely on "Spring Boot started" or solely on the most recent datagram will produce misleading conclusions.

## 12. Operational configuration in Docker/Kubernetes

UDP sockets inside containers normally belong to an isolated network namespace. When deploying the adapter in containers:

- **Expose the right UDP port**—do not map TCP instead of UDP. Verify Services/ingress/network policies support UDP.
- **Bind the right interface address**, especially when configuring `local-address`. Do not assume `127.0.0.1` inside a container is the host IP.
- **Ensure readiness** reflects that the listener is actively listening before the environment routes traffic to the instance.
- **Allow drain time** for already-received messages in executors/queues/brokers; do not expect `SO_TIMEOUT` to drain work.
- **Plan for packet loss** during rolling deployments. Datagrams sent while no receiver is available can vanish without notifying the sender.
- **Separate network timeouts from business timeouts**. Device heartbeats, UDP ACKs, and DB commits need distinct policies and metrics.

To monitor listener state changes, use lifecycle events and instance-tagged metrics. Avoid collecting unbounded dynamic `IP:port` labels that inflate cardinality and overload observability backends.

## 13. Security when starting/stopping listeners

An API letting clients arbitrarily call `stop()`/`start()` on a UDP listener can become a denial-of-service vector. In production, allow lifecycle control only through authenticated/authorized and audited operational procedures.

When building custom UDP replies or ACKs, remember UDP source addresses can be spoofed in some environments. Restrict allowed sender networks, reply rates, and datagram sizes to reduce UDP reflection/amplification risk. `SO_TIMEOUT` is neither DDoS protection nor rate limiting.

Socket lifecycle also involves not leaving listeners bound to old ports after config changes. If the app provides its own `DatagramSocket`, align ownership and cleanup; with Spring-managed adapters, let the container/lifecycle handle resources per contract.

## 14. Comprehensive practice exercise

You have a collector receiving datagrams on `12016`, with sensors sending every **5 seconds** and alerting when no telemetry arrives for **over 20 seconds**.

### Part A — Distinguishing timeouts

1. Configure `soTimeout(1000)` and leave the socket idle for 10 seconds. Observe the lifecycle and confirm no synthetic messages are created.
2. Send a datagram from PowerShell after waiting; explain why the adapter still receives it without needing a restart.
3. Add `lastSeenAt` to the processing service and a scheduled check: alert when `now - lastSeenAt > 20 seconds`. Explain why this value differs from `SO_TIMEOUT`.
4. Stop the sender for 25 seconds while keeping the receiver active. Verify the freshness alert triggers while `isListening()` may still be `true`.
5. Restart the sender and measure the recovery time back to active status.

### Part B — Lifecycle and shutdown

1. Run the receiver with `autoStartup=true`, observing `UdpServerListeningEvent` before sending the first packet.
2. Invoke stop/start in a test environment; send sequences before, during, and after the stop window. Record missing packets.
3. Configure an inbound UDP listener on port 0, retrieve the OS-assigned port from the event, and send a test datagram.
4. Intentionally trigger a port-bind conflict; note the error message and readiness state.
5. Simulate a slow database handler and discuss how to drain in-flight messages on shutdown.
6. Write a rolling-deploy policy: should the sender use retries/ACK or move to a broker if event loss is unacceptable?

### Part C — ACK timeout

Suppose UDP outbound has `ack-timeout=3000` ms. The receiver is designed to send a technical ACK right after receiving the packet, while business logic takes 5 seconds to write to the DB.

- Does an ACK arriving after 1 second prove the data was persisted successfully?
- If the ACK is lost while the record was saved, will a retry create a duplicate?
- If you want an ACK meaning "committed", how must the contract change?

**Self-assessment questions:**

1. What does `SO_TIMEOUT=0` mean for `DatagramSocket.receive()`?
2. Why does 5 seconds without datagrams not prove the UDP adapter is dead?
3. Why do `ack-timeout` and `so-timeout` need two separate metrics?
4. When is `isListening()` more useful than `isRunning()`?
5. What timing problem does `UdpServerListeningEvent` solve in integration tests?
6. During the window between `stop()` and `start()`, who bears responsibility for dropped packets?
7. Why do `MessageChannel` and pollers not automatically retry datagrams lost at the network layer?
8. If data is pulled from SFTP using a poller and then sent via UDP outbound, how does the poller's lifecycle relate to the UDP sender's lifecycle?

## 15. References

- [Spring Integration Reference — IP Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): describes `so-timeout` on UDP inbound/outbound, `ack-timeout`, receive buffers, and `error-channel`.
- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): Java config/Java DSL, `UdpServerListeningEvent`, `isListening()`, `getPort()`, ACK, and listener lifecycle.
- [Spring Integration Javadoc — UnicastReceivingChannelAdapter](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/ip/udp/UnicastReceivingChannelAdapter.html): adapter lifecycle methods and socket options.
- [Spring Integration Javadoc — UdpInboundChannelAdapterSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/ip/dsl/UdpInboundChannelAdapterSpec.html): DSL methods such as `soTimeout(int)`.
- [Oracle Java DatagramSocket API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/DatagramSocket.html): `setSoTimeout`, `receive`, and `close` semantics.

## Conclusion

The **socket timeout** on a UDP inbound adapter is the wait limit for a single datagram read, while the **lifecycle** governs when the endpoint starts, binds, listens, stops, and closes its socket. An expired `receive()` wait **does not mean the socket or sending device disconnected**, and Spring Integration does not emit empty messages merely because `SO_TIMEOUT` elapsed.

With **SPRING_INTEGRATION_ADAPTERS**, manage UDP adapters via Spring's lifecycle, use `UdpServerListeningEvent`/`isListening()` to observe readiness, use message contracts and metrics to track freshness, and separate receive timeouts, ACK timeouts, and business timeouts. When integration flows require delivery guarantees across files, SFTP, HTTP, JMS, AMQP, Kafka, or databases, design appropriate ACK, retry, durable storage, and shutdown policies; `SO_TIMEOUT` alone neither prevents datagram loss nor recovers data across restarts.
