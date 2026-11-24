# Message Size Limits, Send Queues, and Slow Consumers

> **Module:** Spring Boot - web-runtime · **Group:** Long-lived connections. This lesson focuses on **WebSocket, STOMP over WebSocket, and SSE** in Spring Boot: protecting the system from oversized payloads, unbounded outbound queues, and slow consumers. For Spring MVC/STOMP, the three key APIs to master are `setMessageSizeLimit`, `setSendBufferSizeLimit`, and `setSendTimeLimit`. It also distinguishes raw WebSocket, WebFlux/Reactor backpressure, executor queues, and network buffers. Examples use **Java 17+**, **Spring Boot 4.1.2**, and Maven.

## Objectives

After this lesson, you will be able to:

1. Distinguish a WebSocket **frame**, a WebSocket **message**, a STOMP **message**, and a business payload, and understand that byte size is not identical to Java string length.
2. Explain **slow consumers** and why producing faster than a client reads drives up queues, latency, RAM, GC, and denial-of-service risk.
3. Configure inbound STOMP message limits, outbound per-session send buffers, and send time limits; understand these limits **are not** frame limits, task queues, or hard timers.
4. Use `configureClientOutboundChannel` to manage executor tasks and understand the trade-offs between core/max threads and queue capacity.
5. Choose among backpressure, coalescing, bounded buffers, controlled drops, disconnects, and durable replay based on data semantics.
6. Run a small Spring MVC STOMP/WebSocket app to observe limits and test bursts; test slow clients using network shaping rather than guesswork.
7. Recognize differences among raw WebSocket `ConcurrentWebSocketSessionDecorator`, WebFlux `session.receive()/send()`, and SSE `SseEmitter` / `Flux<ServerSentEvent>`.
8. Plan metrics, load testing, security, quotas, and post-reconnect recovery for production systems.

## 1. Why Do Long-Lived Connections Need Buffer Controls?

WebSocket keeps a bidirectional connection open for a long duration. SSE keeps an HTTP response stream open so the server can emit events. A system may push hundreds of thousands of events to many sessions, unlike a REST endpoint that returns a single response and exits.

~~~text
Business events / upstream hot feed
          |
          v
       Publisher
          |
          v
     Broker / fanout
        /   |   \
       /    |    \
 client A  B     C
  fast   slow   offline
          |
       pending bytes
          |
       growing queue -> memory pressure -> GC / dropped connections
~~~

A client can be slow because of weak mobile networks, a small TCP receive window, a frozen browser, a sleeping device, a slow proxy, client CPU busy parsing JSON, or the browser not reading steadily. Regardless of the cause, the server must enforce **per-client and global resource limits**.

Suppose a session needs to receive 800 KiB/s of fresh data, while the connection can actually transmit only 100 KiB/s—creating ~700 KiB/s of backlog. If that excess really enters a 512 KiB buffer, an idealized calculation puts time-to-full at roughly 512/700 = **0.73 seconds**. That is only **a model**: thread scheduling, frame overhead, OS/TCP buffers, compression, other queues, and timeouts all play a part.

If 10,000 sessions are each permitted a 512 KiB buffer, the logical ceiling at that single layer approaches **4.9 GiB**, before counting heap overhead and broker/executor data. Raising every limit to prevent disconnects typically worsens OOM risk.

### 1.1. Four Possible Outcomes When Producers Outpace Consumers

- **Throttle/slow upstream:** if the source honors demand/backpressure, slow down emission when downstream lags.
- **Buffer:** hold data temporarily—acceptable only when **bounded** with an explicit overflow policy.
- **Drop/coalesce:** keep the latest snapshot, drop oldest/latest, or sample; valid only for data types that tolerate losing intermediate events.
- **Disconnect:** close the slow client and let it reconnect and recover via snapshot or replay from a durable store.

Plain WebSocket does not guarantee exactly-once delivery or ACKs. A successful `send` call does not prove the user viewed or processed the event.

## 2. Distinguish Frames, STOMP Messages, and Queues

~~~text
App object (e.g., JSON)
   |
   +-- serialize UTF-8 bytes
   |
   +-- STOMP frame: command + headers + body + NUL
   |
   +-- WebSocket message / multiple fragments
   |
   +-- WebSocket frames
   |
   +-- TLS/TCP -> network -> browser
~~~

| Layer | Example Limit | Unit | What Must Not Be Inferred |
| --- | --- | --- | --- |
| Business payload | DTO/schema, JSON size, depth | bytes/objects | Does not automatically bound WebSocket frames |
| STOMP inbound message | `setMessageSizeLimit` | assembled bytes | Does not automatically bound all HTTP requests |
| WebSocket frame/message | Tomcat/Jetty/Netty settings | bytes | Not identical to assembled STOMP aggregate |
| Spring per-session outbound | `setSendBufferSizeLimit` | pending bytes | Not a global JVM heap cap |
| Outbound thread pool | `clientOutboundChannel` executor queue | **tasks** | Not bytes per session |
| Socket/kernel | TCP send buffer/window | bytes | Not replaced by a STOMP property |
| SSE stream | app events, HTTP response writes | bytes/event | Does not use STOMP settings |

One Unicode character does not always take one byte. For example, `"á"` typically takes 2 UTF-8 bytes even though Java `String.length()` is 1; emojis can take 4 UTF-8 bytes. Add STOMP headers, JSON escaping, and encoding overhead, so message-parser quotas should measure **actual serialized bytes**.

### 2.1. STOMP over WebSocket Can Reassemble Fragments

STOMP SEND/MESSAGE is not the same concept as a WebSocket frame. Spring STOMP support can receive a STOMP message split across multiple smaller WebSocket messages and reassemble it for parsing. Thus **the post-assembly limit** matters critically. An attacker sending many small fragments must not be allowed to bypass the total message quota.

Container limits should also be enabled: an enormous frame payload can be stopped at the container before reaching the STOMP decoder. Never infer that `setMessageSizeLimit` constrains raw binary WebSockets, HTTP uploads, or post-decompression sizes.

## 3. STOMP Flow in Spring MVC

~~~text
WebSocket handshake /ws -> HTTP 101 Switching Protocols
          |
          v
       STOMP CONNECT / SEND / SUBSCRIBE
          |
          v
  StompSubProtocolHandler
          |
          v
    clientInboundChannel ---------> @MessageMapping
          |                            |
          |                            v
          +----------------------> brokerChannel
                                       |
                                       v
                                  simple broker
                                       |
                                       v
                              clientOutboundChannel
                                       |
                                       v
                            WebSocketSession send
                                       |
                                    browser
~~~

- `clientInboundChannel` processes messages from clients via an executor.
- `brokerChannel` passes messages from application handlers to the broker.
- `clientOutboundChannel` delivers messages to sessions with an independent executor and queue.
- The simple broker keeps subscriptions in memory and broadcasts to destinations; it **is not a persistent log** for automatic replay.
- With a broker relay to RabbitMQ/ActiveMQ, the external broker adds flow control and durability per configuration, yet the final hop from broker to WebSocket client still faces the slow-consumer problem.

## 4. Three Crucial Settings in WebSocketTransportRegistration

Inside `WebSocketMessageBrokerConfigurer`:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration r) {
    r.setMessageSizeLimit(32 * 1024);
    r.setSendBufferSizeLimit(256 * 1024);
    r.setSendTimeLimit(10_000);
    r.setTimeToFirstMessage(30_000);
}
~~~

These values are **test lab examples**, not universal presets for every environment.

### 4.1. setMessageSizeLimit: Inbound STOMP Quota

`setMessageSizeLimit(32 * 1024)` sets the byte limit for **an assembled incoming STOMP message** before passing it to the application. Spring Framework STOMP defaults typically to **64 KiB**; verify for your exact version.

- A STOMP message includes headers and body and may be fragmented across multiple WebSocket messages.
- Messages exceeding the limit can trigger decoder errors, session closure, or a STOMP ERROR depending on implementation.
- After WebSocket upgrade, errors do not surface as HTTP 413.
- Spring may adjust minimum WebSocket container message sizes to accept STOMP chunks, yet container and framework limits remain independent.

Do not design a 32,768-byte payload expecting it to pass: STOMP headers and framing add overhead. Always boundary-test with real encoding.

### 4.2. setSendBufferSizeLimit: Per-Session Pending Bytes

`setSendBufferSizeLimit(256 * 1024)` limits the bytes of messages **waiting to be sent** on a slow session. While one thread is sending, other threads cannot concurrently write straight onto that session; Spring buffers pending messages and checks for overflow.

When exceeded, Spring can clear state and attempt to close the session. Closure depends on transport/network state and **is not guaranteed to fire the instant byte 262,145 is produced**.

This **per-session** limit does not include:

- Tasks queued in the `clientOutboundChannel` executor.
- Messages waiting in custom publisher queues or sinks.
- Data queued inside an external broker relay.
- OS kernel send buffers, TLS buffers, or proxy buffers.

If a client can open many sessions, total memory risk still multiplies even when each session is bounded.

### 4.3. setSendTimeLimit: Not a Hard Timer on Every Send

`setSendTimeLimit(10_000)` configures the millisecond threshold for slow sending. Per Spring Javadoc, the time limit is checked **when subsequent send attempts occur**; if only one message is sent and the writer hangs with no follow-up message, the session is not guaranteed to close right at 10 seconds.

Therefore, combine it with:

- Server socket/connector I/O timeouts and idle timeouts.
- WebSocket ping/pong or STOMP heartbeats.
- Monitoring time since last successful send.
- Explicit session close policies and resource cleanup.

**Heartbeats are not backpressure:** a client still replying to heartbeats does not prove it is keeping up with all business events.

### 4.4. setTimeToFirstMessage

`setTimeToFirstMessage(30_000)` caps the time allowed after WebSocket upgrade before the client sends its first STOMP frame. This prevents holding idle empty connections open, rather than limiting bandwidth or message rates.

## 5. Executor Queues Are a Separate Layer from Send Buffers

Spring STOMP uses executors for inbound and outbound channels. Specifically, the `clientOutboundChannel` queue holds **tasks waiting for worker threads**, whereas `sendBufferSizeLimit` tracks **pending bytes on each WebSocket session**.

~~~text
Simple broker
   |
   v
clientOutboundChannel executor
   +-- queue: task 1, task 2, task 3, ...
   |
   +-- worker threads
          |
          v
    one session send lock
          |
          +-- per-session pending message bytes
          |
          v
     connector/socket buffers
~~~

A common misconfiguration sets `corePoolSize=4` and `maxPoolSize=64` while leaving a nearly unbounded executor queue. Java's `ThreadPoolExecutor` **enqueues tasks** before spawning threads above core size, preventing `maxPoolSize` from taking effect as expected. Always measure queue capacity, rejected tasks, active threads, and latency.

### 5.1. configureClientOutboundChannel Example

~~~java
@Override
public void configureClientOutboundChannel(ChannelRegistration registration) {
    registration.taskExecutor()
            .corePoolSize(4)
            .maxPoolSize(8)
            .queueCapacity(200);
}
~~~

This is a **Java fragment** inside `WebSocketMessageBrokerConfigurer`. `queueCapacity(200)` counts **tasks**, not 200 bytes and not a guarantee that 200 messages reached the client. With a bounded queue, the executor rejects tasks under overload; never swallow those rejections and keep reporting `delivered=true`.

### 5.2. Why Adding Threads Does Not Fix Every Slow Client

If a client's link carries only 50 KiB/s while you push 500 KiB/s, adding 100 outbound threads creates zero extra client bandwidth. Pushing messages into send buffers faster can even worsen memory/GC pressure and shift the bottleneck into TCP or proxies.

Consider **throttling producers, coalescing snapshots, bounding per-session buffers, and disconnect/replay** before simply growing thread pools. That said, if workloads mainly wait on short I/O stalls and threads are genuinely starved, tuning the pool helps. Tune via latency and queue metrics—there is no universal number for all deployments.

## 6. Policies for Slow Consumers

| Policy | Meaning | Good Fit | Poor Fit |
| --- | --- | --- | --- |
| Upstream backpressure | Slow production per downstream demand | Cold publishers, demand-aware pipelines | Hot brokers that ignore downstream demand |
| Bounded buffer | Hold a finite number of events/bytes | Short bursts | Producers permanently faster than consumers |
| Drop oldest | Discard older events to make room for new ones | Telemetry tolerating snapshot views | Audit / payment events |
| Drop latest | Discard incoming events while queue is full | Certain sampling/batching cases | Streams needing the newest state immediately |
| Keep latest / coalescing | Retain only the latest state per key | Price boards, dashboards | Workflows needing every state transition |
| Disconnect | Close slow clients to protect the server | Real-time fan-out with reconnect | Workflows lacking replay |
| Durable queue/replay | Persist durably; client resumes via cursor/ACK | Orders, payments, audits | Small ephemeral apps needing no persistence |
| Admission control | Reject publishes/connections over quota | Protecting overall server health | Systems unable to surface backpressure errors |

### 6.1. Conditional Coalescing

Suppose a dashboard receives 1,000 updates/s for a single sensor. If the browser only repaints 10 times/s, you can retain **the last update in each 100 ms window** or only the newest value per sensor. The UI stays fresh without thousands of queued DOM updates.

Conversely, a business sequence `order-created → paid → shipped` must never silently drop `paid` without state reconciliation and durable events. Distinguish **state snapshots** from **event logs**.

### 6.2. Sequences, Gaps, and Replay

~~~json
{"seq":101,"asset":"A","value":12}
{"seq":104,"asset":"A","value":14}
~~~

The client detects missing 102/103 when sequences must be contiguous. After reconnecting, it can call a REST API for a fresh snapshot or request replay from `lastSeenSeq` if the backend keeps a durable log. WebSocket/STOMP `SUBSCRIBE` **does not automatically replay** lost events.

**Application ACK** differs from calling socket `send`. When business correctness matters, apply appropriate transactions, outbox tables, offsets, and idempotency.

### 6.3. Fairness and Quotas

Bound resources across multiple dimensions:

- Max active connections per IP, user, and tenant.
- Number of destinations/subscriptions per session.
- Inbound message bytes, messages/s, and burst allowance.
- Outbound bytes/s, fan-out factor, pending bytes/session, and global memory.
- Maximum connection lifetime, idle timeouts, and reconnect rates.
- Decode/serialization/compression cost and max JSON nesting/array lengths.

An attacker can send 100,000 10-byte messages: `setMessageSizeLimit` does not replace a message rate limit. If an attacker opens thousands of sessions, per-session quotas alone fail; global and per-user quotas are required too.

## 7. Complete Project: Spring Boot 4.1.2 STOMP/WebSocket

The lab features:

- WebSocket HTTP upgrade at `/ws`.
- STOMP SEND to `/app/echo`, with Spring broadcasting replies to `/topic/echo`.
- Max inbound STOMP message **32 KiB**.
- Max per-session send buffer **256 KiB**.
- Send time limit **10 seconds**, time to first message **30 seconds**.
- Outbound executor queue **200 tasks**.
- Endpoint `POST /lab/burst` publishing up to 200 events × 8 KiB ASCII.
- Minimal HTML browser WebSocket/STOMP client.

This is a **localhost lab** with no authentication or authorization; never expose it to the public internet or send sensitive data.

### 7.1. File Tree

~~~text
slow-client-lab/
  pom.xml
  src/main/java/com/example/slowclient/
    SlowClientApplication.java
    WebSocketConfig.java
    EchoStompController.java
    BurstController.java
  src/main/resources/
    application.properties
    static/demo.html
~~~

### 7.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>slow-client-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
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

`spring-boot-starter-websocket` in Boot 4.1.2 includes Spring MVC WebSocket support. Do not combine this configuration with a WebFlux server expecting Servlet STOMP transport settings to apply automatically.

### 7.3. SlowClientApplication.java

~~~java
package com.example.slowclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SlowClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(SlowClientApplication.class, args);
    }
}
~~~

### 7.4. WebSocketConfig.java

~~~java
package com.example.slowclient;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration(proxyBeanMethods = false)
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("http://localhost:8080");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {
        registration.setMessageSizeLimit(32 * 1024);
        registration.setSendBufferSizeLimit(256 * 1024);
        registration.setSendTimeLimit(10_000);
        registration.setTimeToFirstMessage(30_000);
    }

    @Override
    public void configureClientOutboundChannel(
            ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(4)
                .maxPoolSize(8)
                .queueCapacity(200);
    }
}
~~~

**Configuration scope:**

- `/ws` is the upgrade endpoint, not a STOMP destination.
- STOMP SEND `/app/echo` is handled by Spring's controller method; `/topic/echo` is delivered by the simple broker to subscribers.
- `setMessageSizeLimit` bounds assembled STOMP messages; it does not govern the HTTP body size of `/lab/burst`.
- `setSendBufferSizeLimit` bounds per-session pending bytes; `queueCapacity(200)` bounds executor tasks.
- `setSendTimeLimit` is not a hard timeout for every individual send.
- `setAllowedOrigins("http://localhost:8080")` is a **fixed same-origin lab policy**. Origin never replaces authentication; non-browser clients can spoof it.

### 7.5. EchoStompController.java

~~~java
package com.example.slowclient;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class EchoStompController {
    @MessageMapping("/echo")
    @SendTo("/topic/echo")
    public String echo(String message) {
        return "echo: " + message;
    }
}
~~~

A client sending a STOMP message to destination `/app/echo` with `content-type:text/plain` maps to `echo`, and the return value goes to `/topic/echo`. In a real app, never echo tokens, PII, or unvalidated schemas; subscriptions must enforce user/tenant authorization.

### 7.6. BurstController.java

~~~java
package com.example.slowclient;

import org.springframework.http.ResponseEntity;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BurstController {

    private final SimpMessagingTemplate template;

    public BurstController(SimpMessagingTemplate template) {
        this.template = template;
    }

    @PostMapping("/lab/burst")
    public ResponseEntity<String> burst(
            @RequestParam(defaultValue = "10") int count,
            @RequestParam(defaultValue = "128") int bytes) {
        if (count < 1 || count > 200 || bytes < 1 || bytes > 8192) {
            return ResponseEntity.badRequest().body(
                    "count must be 1..200 and bytes must be 1..8192");
        }

        String body = "x".repeat(bytes);
        for (int i = 1; i <= count; i++) {
            template.convertAndSend("/topic/echo", i + ":" + body);
        }

        return ResponseEntity.accepted().body(
                "submitted " + count + " messages");
    }
}
~~~

The code validates inputs so a single lab HTTP request cannot trigger an infinite loop. `bytes` is the count of ASCII `x` characters, plus the `i:` prefix and STOMP framing overhead. HTTP **202 Accepted** in the demo **does not mean** all subscribers received bytes or ACKed events: it means only that the loop submitted messages to the broker without synchronous errors.

If exposed publicly, this endpoint acts as a fan-out amplification vector enabling DoS; production requires auth, quotas, rate limits, and never allowing users to pick arbitrary counts/payloads.

### 7.7. application.properties

~~~properties
server.port=8080

# Lab lacks authentication; never expose to the internet.
logging.level.org.springframework.web.socket=INFO
logging.level.org.springframework.messaging=INFO
~~~

### 7.8. static/demo.html

This file uses the browser WebSocket API to send basic STOMP frames and **is not a full STOMP client**. It assumes the CONNECTED frame arrives separately and omits robust frame parsing, heartbeats, escaping, content-length, receipts, and reconnection. Production should use a battle-tested STOMP client library.

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>WebSocket slow client lab</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; }
    button, input { padding: 0.5rem; }
    pre { border: 1px solid #aaa; height: 280px; overflow: auto; }
  </style>
</head>
<body>
  <h1>STOMP/WebSocket lab</h1>
  <button id="connect">Connect</button>
  <input id="message" maxlength="100" value="hello">
  <button id="send">SEND</button>
  <button id="close">Close</button>
  <pre id="log"></pre>
  <script>
    let socket = null;
    let subscribed = false;
    const log = (line) => {
      const panel = document.getElementById("log");
      panel.textContent += line + "\n";
      panel.scrollTop = panel.scrollHeight;
    };
    function frame(command, headers, body = "") {
      return command + "\n" + headers.join("\n")
          + "\n\n" + body + "\0";
    }
    document.getElementById("connect").onclick = () => {
      if (socket && socket.readyState === WebSocket.OPEN) return;
      subscribed = false;
      socket = new WebSocket("ws://" + location.host + "/ws");
      socket.onopen = () => {
        log("WebSocket OPEN");
        socket.send(frame("CONNECT",
          ["accept-version:1.2", "host:localhost"]));
      };
      socket.onmessage = event => {
        const raw = String(event.data);
        if (!subscribed && raw.startsWith("CONNECTED")) {
          subscribed = true;
          socket.send(frame("SUBSCRIBE",
            ["id:s-1", "destination:/topic/echo", "ack:auto"]));
          log("STOMP CONNECTED, subscribed");
        } else {
          log("RECEIVED: " + raw.slice(0, 200));
        }
      };
      socket.onerror = () => log("WebSocket ERROR");
      socket.onclose = event => {
        subscribed = false;
        log("CLOSE code=" + event.code);
      };
    };
    document.getElementById("send").onclick = () => {
      if (!socket || socket.readyState !== WebSocket.OPEN || !subscribed) {
        log("Not subscribed yet");
        return;
      }
      const body = document.getElementById("message").value;
      socket.send(frame("SEND",
        ["destination:/app/echo", "content-type:text/plain"], body));
    };
    document.getElementById("close").onclick = () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close(1000, "demo finished");
      }
    };
  </script>
</body>
</html>
~~~

`WebSocket.bufferedAmount` in the browser measures bytes **queued by the browser itself for sending**, not the server→browser send buffer. Use server metrics to detect slow-reading clients. A browser tab with paused JS can still have an OS receive buffer accepting incoming data; never treat a frozen UI as proof TCP is backpressured.

### 7.9. Running and Verifying

At project root:

~~~bash
mvn spring-boot:run
~~~

Open:

~~~text
http://localhost:8080/demo.html
~~~

Click **Connect**, then **SEND**. Expected application-level log output:

~~~text
WebSocket OPEN
STOMP CONNECTED, subscribed
RECEIVED: MESSAGE
destination:/topic/echo
...
echo: hello
~~~

`...` represents actual STOMP headers that can vary, **not fixed output**. Inspect DevTools Network → WS to view raw frames.

Trigger a small burst from another terminal:

~~~bash
curl -i -X POST \
  "http://localhost:8080/lab/burst?count=10&bytes=128"
~~~

When the controller submits messages to the broker with no synchronous error, response:

~~~text
HTTP/1.1 202
...
submitted 10 messages
~~~

Status line/headers can vary by container, while the demo body is exact. Also try:

~~~bash
curl -i -X POST \
  "http://localhost:8080/lab/burst?count=500&bytes=128"
~~~

Expect HTTP **400** and body:

~~~text
count must be 1..200 and bytes must be 1..8192
~~~

This HTTP 400 comes from **`BurstController` input validation**, not from the STOMP message size limit.

### 7.10. Testing STOMP Inbound Over 32 KiB

In the DevTools Console of the open page, create a separate socket:

~~~javascript
const ws = new WebSocket("ws://localhost:8080/ws");
ws.onopen = () => {
  ws.send("CONNECT\naccept-version:1.2\nhost:localhost\n\n\0");
};
ws.onmessage = event => {
  const data = String(event.data);
  if (data.startsWith("CONNECTED")) {
    const body = "x".repeat(40 * 1024);
    ws.send("SEND\ndestination:/app/echo\n"
      + "content-type:text/plain\n\n" + body + "\0");
  }
  console.log(data.slice(0, 150));
};
ws.onclose = event => console.log("CLOSED", event.code);
ws.onerror = () => console.log("ERROR");
~~~

The 40 KiB payload exceeds the configured 32 KiB STOMP limit. You may observe a STOMP ERROR, decoder exception, or WebSocket closure depending on container and version. There is no HTTP 413 after upgrade; an oversized frame may also be blocked by the container **before** reaching the STOMP parser. Tests should verify the payload is not processed by the controller as a valid message and does not exhaust server RAM.

### 7.11. Testing Slow Consumers Properly

You cannot reliably simulate a slow TCP reader using `Thread.sleep()` inside browser JS: the browser/kernel keeps draining bytes into buffers even while handlers pause. Use a network emulator, traffic shaping, or a test environment with real bandwidth/latency throttling, then measure bytes and queues.

1. Connect 1 fast client and 1 client with throttled download bandwidth.
2. Subscribe both to the same topic; observe actual send and receive rates.
3. Emit small bursts, then increase gradually in **an isolated lab**, e.g.:
   
~~~bash
curl -i -X POST \
  "http://localhost:8080/lab/burst?count=200&bytes=8192"
~~~

4. Monitor latency, active outbound threads, executor queue depth, pending bytes per session (if instrumented), close reasons, heap, and GC.
5. Check whether the fast client is slowed down too; test disconnect/reconnect.
6. Repeat tests under higher/lower limits **recorded in test configs** without altering production.

**Do not promise the burst command will always close the client right at 10 seconds**: if the network is fast enough and buffers do not fill, the connection stays healthy. Conversely, extreme throttling can cause the kernel or proxy to drop the connection before Spring's limits kick in.

### 7.12. Maven Packaging

~~~bash
mvn package
java -jar target/slow-client-lab-0.0.1-SNAPSHOT.jar
~~~

This is a Spring Boot project; never invoke bare `javac` on Spring classes without the Maven dependency classpath.

## 8. Raw WebSocket on Servlet: ConcurrentWebSocketSessionDecorator

When using `TextWebSocketHandler` or `BinaryWebSocketHandler` directly via `WebSocketConfigurer`, STOMP's `configureWebSocketTransport` settings do not apply automatically.

Spring Servlet provides `ConcurrentWebSocketSessionDecorator` so only one thread writes to a given session at a time; concurrent sends are queued/buffered and checked against time and size limits:

~~~java
// Fragment inside a raw WebSocket session manager.
WebSocketSession safeSession =
        new ConcurrentWebSocketSessionDecorator(
                originalSession, 10_000, 256 * 1024);
~~~

**Important:** create **one decorator per session** and share that exact wrapper across every send path. Wrapping a fresh decorator on every send loses synchronization and breaks shared per-session limits.

This decorator **does not** replace:

- WebSocket container frame/message maximums.
- App-level inbound payload size/schema checks.
- Global heap/connection quotas.
- Broker persistence.
- Socket/network timeouts.

Some versions also provide `ConcurrentWebSocketSessionDecorator.OverflowStrategy` (drop/terminate) to choose behavior when the buffer overflows. Pick a strategy matching business data semantics and always count dropped messages.

### 8.1. Servlet Container Buffers

With Jakarta WebSocket on a servlet container, use `ServletServerContainerFactoryBean`:

~~~java
// @Bean fragment inside a Spring MVC @Configuration.
@Bean
ServletServerContainerFactoryBean createWebSocketContainer() {
    ServletServerContainerFactoryBean bean =
            new ServletServerContainerFactoryBean();
    bean.setMaxTextMessageBufferSize(64 * 1024);
    bean.setMaxBinaryMessageBufferSize(64 * 1024);
    bean.setMaxSessionIdleTimeout(60_000L);
    return bean;
}
~~~

This fragment requires imports and a configuration class to run; **container message buffer** sizes are distinct from STOMP's `setMessageSizeLimit`. Tomcat/Jetty defaults differ; Spring may raise minimum transport buffer sizes for STOMP chunks, so always test the real receive path.

## 9. WebFlux/WebSocket: Backpressure, Yet Not Magic

WebFlux uses:

- `WebSocketSession.receive()` → `Flux<WebSocketMessage>`.
- `WebSocketSession.send(Publisher<WebSocketMessage>)` → `Mono<Void>`.
- `WebSocketHandler.handle(...)` must return a `Mono<Void>` representing the send/receive lifecycle.
- Reactor supports demand signals and backpressure operators, yet **hot sources, broker callbacks, sockets, and other buffers** still require explicit policies.

Illustrative echo handler:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

public final class EchoWebSocketHandler implements WebSocketHandler {
    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> outbound = session.receive()
                .map(WebSocketMessage::getPayloadAsText)
                .map(text -> "echo:" + text)
                .map(session::textMessage);

        return session.send(outbound);
    }
}
~~~

This handler class **lacks route registration and inbound size guards**, so do not deploy it publicly as-is. In WebFlux, cap frame/message sizes at Reactor Netty/transport **for your exact version** alongside parser/application limits; do not assume `spring.codec.max-in-memory-size` acts as a universal hard cap on all WebSocket messages.

### 9.1. Cold vs. Hot Publishers

- Cold publishers can respond to demand and slow down production.
- Hot sources can keep emitting regardless of a slow subscriber.
- A misused `Sinks.Many` or `Flux.create` can accumulate backlog in internal queues, causing OOM even though WebSocket's send API accepts a Publisher.

Reactor operators:

| Operator | Effect | Limitation |
| --- | --- | --- |
| `onBackpressureLatest()` | Retains only the newest item | Drops intermediate events |
| `onBackpressureDrop()` | Drops when downstream lacks demand | Must meter drops if visibility is needed |
| `onBackpressureBuffer(maxSize, ...)` | Bounded buffer with overflow handling | Never use unbounded variant on hot streams |
| `limitRate(...)` | Tunes upstream demand batching | Not a network bandwidth cap |
| `timeout(...)` | Reactive signal timeout per operator semantics | Not a hard socket send timeout |
| `doFinally(...)` | Cleanup on complete/error/cancel | Does not itself prevent overload |

Fragment strictly for state where losing intermediate updates is acceptable:

~~~java
// Snapshot and metrics are app-defined types/beans, not standalone code.
Flux<Snapshot> latest = snapshots
        .onBackpressureLatest()
        .doOnDiscard(Snapshot.class, s -> metrics.incrementDropped());
~~~

For orders, payments, or audits, never use drops to solve backpressure; use durable logs, cursors/replay, and retries/idempotency.

### 9.2. Sinks and EmitResult

When using Reactor Sinks for broadcasting, handle `tryEmitNext` failures on missing demand, overflow, or terminal state, and define policies **per subscriber**. Never spin-retry endlessly on a Netty event-loop thread when emission is rejected.

Enforce frame size limits at server transport, publish rates, subscription counts, and connection pool quotas. Calling a publisher "reactive" does not mean application memory is automatically bounded.

## 10. SSE Also Suffers from Slow-Reading Clients

Server-Sent Events hold an HTTP `text/event-stream` response open while the server pushes line-delimited events. Browser `EventSource` can auto-reconnect; `Last-Event-ID`/event IDs enable resumability when the application implements actual replay.

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

id: 101
event: update
data: {"state":"working"}

id: 102
event: update
data: {"state":"done"}

~~~

When a client reads slowly:

- Servlet MVC `SseEmitter` can block, error, or time out while writing; **never** let an upstream producer queue grow unbounded.
- WebFlux `Flux<ServerSentEvent<?>>` honors reactive demand; if a hot source or proxy buffer ignores demand, enforce bounded policies.
- Reverse proxies/Nginx/Envoy can buffer data or enforce idle timeouts, causing events to arrive in bursts. Configure streaming routes, heartbeats, connection caps, and load-test behind real proxies.
- `Last-Event-ID` only lets the client report its last seen ID. The server needs a log/snapshot and retention policy to replay.

Servlet MVC fragment:

~~~java
// Fragment, not a standalone program.
SseEmitter emitter = new SseEmitter(60_000L);
// When a valid event arrives from the source:
// emitter.send(SseEmitter.event().id("101").name("tick").data("hello"));
~~~

WebFlux fragment:

~~~java
// Fragment in a WebFlux controller; needs imports for Flux/ServerSentEvent/Duration.
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(i -> ServerSentEvent.<String>builder()
                    .id(Long.toString(i))
                    .event("tick")
                    .data("tick-" + i)
                    .build());
}
~~~

Never treat SSE heartbeats or TCP keep-alive as proof the browser processed messages. Track event-age metrics and clean up subscribers on disconnect.

## 11. Ordering, ACKs, Reconnect, and Replay

### 11.1. Accepted by Broker Differs from Delivered by Client

~~~text
Produced
   -> accepted by messaging channel
   -> queued for broker
   -> queued for clientOutboundChannel
   -> write attempted
   -> bytes reached client TCP
   -> browser parsed event
   -> application processed and ACKed
~~~

Each stage represents a different level of completion. `SimpMessagingTemplate.convertAndSend` returning does not prove the client ACKed, because most of the pipeline is asynchronous. When business logic requires exactly-once effects, use transactions/outbox, a durable message log, and business-layer idempotency; WebSocket does not supply automatic exactly-once.

### 11.2. Publish Order

Spring STOMP allows:

~~~java
// Fragment inside configureMessageBroker(...):
registry.setPreservePublishOrder(true);
~~~

This preserves publication order **within a single client session** when the outbound executor runs in parallel, at the cost of extra overhead. It neither enforces global ordering across nodes nor guarantees replay across reconnects. With fan-out, attach `seq`/version fields so clients detect gaps or out-of-order messages.

### 11.3. Reconnect Storms

Disconnecting slow clients can save server memory, yet if 10,000 clients all reconnect instantly, handshakes, auth, and snapshot APIs get hammered. Implement exponential backoff + jitter, retry/rate limits, and cursor-based snapshots/replay. Never stuff an entire history dump into one huge WebSocket frame to "catch up".

## 12. Observability and Alerting

Spring Framework exposes `WebSocketMessageBrokerStats` when using `@EnableWebSocketMessageBroker`, reporting session counts, abnormal closes, inbound/outbound channel executors, and broker/SockJS stats. It can log periodically at INFO or export stats via JMX/integrations. Several metrics below require custom instrumentation rather than appearing automatically.

| Metric Group | What to Measure | Purpose |
| --- | --- | --- |
| Sessions | active, created, closed, abnormal closes | Connection leaks, reconnect storms |
| Inbound | messages/s, bytes/s, rejected oversized | Floods / parse limits |
| Outbound | executor active threads, queued tasks, rejections | Send saturation |
| Per-session | pending bytes, send duration, last successful send | Spot slow consumers |
| Broker | subscription count, fan-out, destination hot spots | Resource pressure |
| Reliability | dropped events, sequence gaps, replay lag | Data quality |
| Runtime | heap, GC pauses, CPU, network egress | OOM/latency risks |
| Edge | proxy resets, idle timeouts, TLS/WebSocket failures | Network issues |

**Measure tail latency:** a 5 ms average send can hide a cohort of clients lagging 30 seconds behind. Track p95/p99 event delivery lag, queue wait time, and per-client backlog, distinguishing 1% ultra-slow clients from global overload.

Suggested alerts:

- Outbound executor queue climbs steadily while active threads stay pinned at max.
- Spike in abnormal closes or slow-client disconnects after a deploy.
- Heap grows proportionally with sessions and fails to recover after disconnects.
- P99 delivery lag breaches SLO; dropped event count climbs.
- Broker fan-out/egress approaches capacity limits.
- Reconnect rate spikes, driving extra auth/database load.

Never attach raw session IDs, user IDs, or dynamic destinations to millions of high-cardinality metric labels; design sampling, aggregation, and privacy carefully.

## 13. Load Testing: Never Guess Whether the Server Closes Slow Clients

Key scenarios to include:

1. Healthy client with 100–500 byte payloads to establish baseline latency/CPU/memory.
2. Inbound messages near and above 32 KiB; test STOMP fragmentation.
3. One slow client throttled via network emulator alongside one fast client simultaneously.
4. High fan-out to thousands of clients within lab limits.
5. Bursts exceeding network throughput for several seconds (never aimed at production).
6. Sleeping tabs, network drops, reconnects, and state replay.
7. Real reverse proxy/CDN/ingress for WebSocket upgrades and SSE buffering.
8. Compressed payloads expanding heavily, serialization allocations, and JSON parser limits.
9. Fairness across tenants/users, inbound floods, and quotas.
10. Disconnecting all clients and confirming memory/subscription counts return to baseline.

Acceptance criteria should quantify SLOs: p99 event lag, max buffered bytes, max queue depth, max sessions, intentional disconnect rate, zero loss for critical data, and zero impact on fast clients.

### Egress Estimation

With `N` clients, `R` events/s/client, and `S` serialized bytes/event:

~~~text
approx_outbound_payload_bytes_per_second = N * R * S
~~~

For example, 1,000 clients × 10 events/s × 1 KiB ≈ **9.77 MiB/s** of raw payload, before WebSocket/STOMP/TLS/TCP overhead. If every event is serialized separately per client, CPU and GC pressure also scale with fan-out. Size capacity across socket buffers, executor queues, and per-session buffers—not network throughput alone.

## 14. Common Mistakes

| Mistake | Problem | Fix |
| --- | --- | --- |
| Limiting only WebSocket frames | A STOMP message can reassemble many fragments | Add inbound STOMP aggregate limit |
| Setting only `setMessageSizeLimit` | Leaves outbound pending bytes unbounded | Add per-session send buffer/time limits |
| Treating send time limit as a hard timer | A lone hung send isn't checked until the next send attempt | Add transport idle/socket timeouts and observability |
| Confusing executor queue with send buffer | One counts tasks, the other counts pending bytes | Monitor both |
| Large maxPoolSize with unbounded queue | Threads never scale up as expected while heap grows | Bound queue and size pools via testing |
| Keep adding threads | Does not increase client network bandwidth | Use coalescing, rate control, drop/disconnect |
| No per-user connection caps | Users open many sessions to bypass quotas | Enforce global + per-user quotas |
| Dropping audit/payment events | Critical business data lost | Use durable logs, replay, and idempotency |
| Using `String.length()` as byte size | UTF-8 has multibyte characters | Enforce limits on serialized bytes |
| Applying STOMP settings to WebFlux or raw WebSocket | Wrong framework/transport | Pick APIs and server limits matching your stack |
| Creating a new decorator per raw send | Fails to share per-session state | Wrap once per session |
| Hot Flux + unbounded buffer | OOM despite using Reactor | Use bounded buffers and overflow strategies |
| Treating lab HTTP 202 as client-delivered | No browser ACK | Track sequences and actual delivery |
| Using JS sleep as proof of slow TCP | Kernel/browser keep buffering bytes | Use traffic shaping and server metrics |
| Exposing burst endpoint publicly without auth | Fan-out/DoS amplifier | Enforce auth, rate limits, and quotas |
| Treating heartbeats as backpressure | Client can still answer pings while lagging behind on data | Track pending bytes and event lag |
| Missing reconnect backoff | Triggers reconnect storms | Add exponential backoff + jitter |
| Forgetting proxy SSE buffering | Events arrive in bursts | Configure streaming path properly |
| Measuring CPU only | Misses network/queue/GC/tail latency bottlenecks | Use multi-layer observability |

## 15. Production Deployment Checklist

- [ ] Identify exact protocol: STOMP/WebSocket, raw WebSocket, WebFlux, or SSE.
- [ ] Cap inbound bytes post-assembly/parse; test encoding, compression, JSON depth, and container frame limits.
- [ ] Cap message rates/s, connections, and subscriptions per user/tenant.
- [ ] Size outbound per-session buffers/time limits to balance valid bursts against total RAM capacity.
- [ ] Bound `clientOutboundChannel` executor queues with metrics and a rejection policy.
- [ ] Enforce global memory/network/CPU caps so one slow client never starves others.
- [ ] Define clear slow-consumer overflow actions: drop/coalesce/disconnect/replay per data semantics.
- [ ] Back critical events with durable logs, sequence numbers, and ACK/replay/idempotency.
- [ ] Set matching heartbeats and idle timeouts without confusing them with backpressure.
- [ ] Secure WebSocket/SSE endpoints with auth, authorization, allowed origins, rate limits, and no public stress endpoints.
- [ ] Test with network shaping, high fan-out, proxy buffering, disconnects, and reconnect storms.
- [ ] Build dashboards for active sessions, pending bytes, executor tasks, drops, p99 event age, and heap/GC.
- [ ] Maintain a runbook for tuning thresholds from real workloads rather than setting limits to infinity.

## 16. Self-Check Questions and Answers

**1.** Does `setMessageSizeLimit(32 * 1024)` restrict each WebSocket frame to 32 KiB?

**Answer:** No. It bounds assembled inbound STOMP messages, not the container's frame limit.

**2.** Does `setSendBufferSizeLimit(256 * 1024)` guarantee the app holds at most 256 KiB outbound in total?

**Answer:** No. It applies to per-session pending bytes at the Spring STOMP layer, excluding task queues, sockets, and other sessions.

**3.** Does `setSendTimeLimit(10_000)` guarantee closing a hung send right at 10 seconds?

**Answer:** No. Spring checks this limit on subsequent send attempts; you also need socket/idle timeouts.

**4.** Why is outbound `queueCapacity=200` different from a 256 KiB send buffer?

**Answer:** The executor queue counts tasks; the send buffer counts per-session pending bytes. Either can saturate independently.

**5.** Can `Thread.sleep()` in browser `onmessage` reliably simulate slow TCP reads?

**Answer:** No. Network and browser buffers still accept incoming data; use traffic shaping and server metrics instead.

**6.** Does raw `TextWebSocketHandler` automatically inherit STOMP `configureWebSocketTransport` settings?

**Answer:** No. Use raw session decorators and container limits as appropriate.

**7.** Is WebFlux with unbounded `onBackpressureBuffer()` safe from OOM?

**Answer:** No. Hot producers can overflow the queue; use bounded capacity with an overflow strategy.

**8.** Does `SimpMessagingTemplate.convertAndSend` succeeding mean every subscriber processed the event?

**Answer:** No. When guarantees are needed, implement business ACKs, durable logs, and replay.

**9.** Can payment events be dropped like chart snapshots?

**Answer:** No. Charts can keep latest state, whereas payments and audits require durability and correctness.

**10.** Can one slow client affect other clients?

**Answer:** Yes, through shared executor threads, queues, brokers, heap, or network egress. Enforce isolation, bounded resources, and load testing.

## 17. Official References

- [Spring Framework — STOMP Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html) — outbound executor, `sendTimeLimit`, `sendBufferSizeLimit`, inbound message size.
- [Spring Framework — WebSocket Transport](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/server-config.html) — frame/container settings and STOMP limits.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html) — inbound/outbound/broker channels.
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html).
- [Spring Framework — Monitoring WebSocket/STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html).
- [Spring Framework — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html).
- [Spring Framework Javadoc — WebSocketTransportRegistration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketTransportRegistration.html).
- [Spring Framework Javadoc — ConcurrentWebSocketSessionDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.html).
- [Spring Framework Javadoc — SseEmitter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html).
- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/backpressure.html).
- [Spring Boot 4.1.2 managed dependencies](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html).
- [Spring Boot 4.1.2 release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455).
- [WHATWG — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html).
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html).

**Takeaway:** Inbound message size limits, pending outbound send bytes, send time limits, and task queues are **distinct barriers**. On Spring MVC STOMP, configure `setMessageSizeLimit`, `setSendBufferSizeLimit`, `setSendTimeLimit`, and tune `clientOutboundChannel` based on measurements. On raw WebSocket, WebFlux, and SSE, pick the runtime-appropriate APIs. For slow clients, rely on bounded resources, transparent overflow policies, quotas, sequences/replay, and monitoring—**never** try to fix them with infinite buffers or unbounded threads.
