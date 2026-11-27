# Sending Real-Time Notifications with Pub/Sub

**Redis Pub/Sub** is a message distribution mechanism following the *publish–subscribe* model: a publisher sends a message to a **channel**, and Redis delivers that message to subscribers currently subscribed to the channel at publish time. In **Spring Data Redis**, we can use `StringRedisTemplate.convertAndSend(...)` to publish and `RedisMessageListenerContainer` paired with `MessageListener` to subscribe.

This exercise builds the flow **Spring Boot → Redis Pub/Sub → Spring listener → Server-Sent Events (SSE) → browser**. A notification published on application instance A can appear almost instantaneously in browsers connected to both A and B, with Redis acting as an event-distribution *backplane* across application instances.

**Core limitation:** Redis Pub/Sub is **best-effort/at-most-once**; messages are **not persisted for replay** to offline subscribers. A successful response from `PUBLISH` does not mean users saw the notification on screen. If notifications require history, ACKs, retries, and recovery, pair it with a durable data store or use Redis Streams / an appropriate message broker.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain channels, publishers, subscribers, and delivery semantics of Redis Pub/Sub.
2. Test `SUBSCRIBE`/`PUBLISH` manually via Redis CLI.
3. Build a Spring Boot 3.x/Java 17 application using Redis auto-configuration.
4. Define a JSON notification payload containing `id`, `type`, `text`, and `createdAt`.
5. Create an HTTP endpoint `POST /api/notifications` that publishes messages to Redis.
6. Register a listener with `RedisMessageListenerContainer` and `ChannelTopic`.
7. Push messages to browsers via `SseEmitter` and `EventSource`.
8. Verify multi-instance broadcasting, disconnections, offline subscribers, and reconnects.
9. Understand ACL channel permissions, security, serialization, executor limits, and performance measurement.
10. Decide when Pub/Sub is sufficient versus when history/outbox/Redis Streams are needed.

Within the scope of this exercise, notifications are **public announcements** containing no private information. Do not use this prototype as-is for payment, authentication, or personal-data notifications without adding authorization and persistence.

## 2. End-to-End Architecture

```text
Browser 1             Browser 2           Browser 3
   ^                      ^                   ^
   | SSE                  | SSE               | SSE
   |                      |                   |
   +---------- App A -----+                   App B
                   ^                         ^
                   |                         |
          RedisMessageListenerContainer (per instance)
                   ^                         ^
                    \                       /
                     \                     /
                      Redis Pub/Sub Channel
                          demo:notifications
                                ^
                                |
                        PUBLISH JSON event
                                ^
                                |
                     POST /api/notifications
```

Each Spring Boot instance opens its own Redis subscription and holds a set of **local** SSE connections. Redis sends a message to all subscribed connections; each instance fans it out to the browsers it serves.

Four conclusions follow from this architecture:

- **A Redis subscriber connection is not a browser connection.** One Redis listener on instance A can serve hundreds of SSE clients.
- **A Pub/Sub channel is not a Redis key storing messages.** You cannot `GET` past messages.
- **There is no replay/ACK.** Instance B being offline during a publish loses that notification.
- **SSE reconnect does not automatically recover missed Pub/Sub events.** Catch-up requires a separate history store.

## 3. Pub/Sub at the Redis Protocol Level

Basic commands:

```text
SUBSCRIBE demo:notifications
PUBLISH demo:notifications "Hello"
UNSUBSCRIBE demo:notifications
```

When a publisher invokes `PUBLISH`, Redis delivers the message to connected subscribers matching the channel.

| Component | Role |
|---|---|
| Channel | Logical channel name, e.g., `demo:notifications` |
| Publisher | Client calling `PUBLISH` |
| Subscriber | Client that executed `SUBSCRIBE` or `PSUBSCRIBE` |
| Message | Delivered payload bytes, not a durable key-value entry |
| Connection | Redis subscription tied to a connection's lifetime |
| Listener | Spring code handling messages pushed by Redis |

Do not confuse Pub/Sub with Redis Streams. Pub/Sub has no stream IDs, consumer groups, Pending Entries List, `XACK`, or retention. Redis has no way to "re-read the last 10 messages" from a Pub/Sub channel alone.

### Ordering Guarantees

Redis delivers messages in order over a given subscription stream, yet processing order **after Redis** can vary when applications use multiple threads, fan-out queues, or reconnects. Do not treat a Redis channel as a global ordering guarantee across all browsers and nodes unless serialization is explicitly designed.

## 4. Which Types of Notifications Should Use Pub/Sub?

| Need | Suitable? | Explanation |
|---|---|---|
| Live dashboard metric updates | Yes | If a message is missed, the client can reload state |
| Non-critical general announcement banners | Yes | Missing an occasional message is acceptable |
| "Cache changed" invalidation signals | Conditionally | Requires TTL/versioning/reconciliation to avoid permanent staleness |
| "New message available" hint backed by DB | Yes | Actual content remains safely stored in the database |
| Emails that must send even if workers are offline | Do not use standalone Pub/Sub | Needs a durable queue, ACK/retry |
| Payment transactions/balance updates | Do not use Pub/Sub as source of truth | Needs transactions, idempotency, audit |
| Notification center with history | Must add a persistent store | Pub/Sub acts only as the realtime signal |
| Realtime distribution across app instances | Yes | Redis acts as the fan-out backplane |

A helpful decision question: **"If a subscriber goes offline for 30 seconds, is it acceptable to miss those 30 seconds of notifications?"** If the answer is no, plain Pub/Sub is not enough.

## 5. How Do Pub/Sub, Streams, SSE, and WebSocket Differ?

| Technology | Function | Key Limitation |
|---|---|---|
| Redis Pub/Sub | Immediate message distribution among server clients | No persistence/ACK/replay |
| Redis Streams | Persists events by ID, supports consumer groups | Must manage retention, ACK, recovery |
| SSE | Unidirectional HTTP push app → browser | Does not persist history itself |
| WebSocket | Bidirectional connection app ↔ browser | Must manage connections, auth, state |
| Polling | Browser repeats HTTP GET | Increases request overhead; updates lag by interval |

This lesson picks **SSE** because notifications only flow from server to browser. Browsers send notification creation requests via a separate **HTTP POST**. Redis Pub/Sub sits **between Spring instances**, not as a protocol the browser speaks directly.

## 6. Preparing the Redis Lab

You can run an isolated Redis using Docker:

```bash
docker run --rm --name redis-pubsub-lab -p 127.0.0.1:6379:6379 redis:7.4-alpine
```

Depending on OS and Docker networking, port binding syntax may need adjustment. This is a **local test** Redis without authentication or TLS; **do not expose the lab Redis to the Internet** or store real data in it.

Verify:

```bash
redis-cli -h 127.0.0.1 -p 6379 PING
```

Expected: `PONG`. If `redis-cli` is not installed on the host:

```bash
docker exec -it redis-pubsub-lab redis-cli
```

Only use `redis-cli` against lab Redis servers you manage.

## 7. Trying Pub/Sub Manually Before Writing Java

In terminal A:

```bash
redis-cli -h 127.0.0.1 -p 6379 SUBSCRIBE demo:notifications
```

Keep A open. In terminal B:

```bash
redis-cli -h 127.0.0.1 -p 6379 PUBLISH demo:notifications "Hello Redis"
```

Terminal A displays a message containing `Hello Redis`.

To test the **no-replay** property:

1. Stop the subscriber in A.
2. Publish two more messages in B.
3. Restart subscriber A.
4. Observe that the two messages published while A was offline **do not appear automatically**.
5. Publish a new message once A is subscribed; A receives it again.

This is by design in Redis Pub/Sub, not a client bug.

## 8. Spring Boot Dependencies

For a Spring Boot project with managed plugins/BOM, Gradle declaration:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-validation")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers")
}
```

- Spring Web MVC provides REST Controllers and `SseEmitter`.
- Spring Data Redis integrates `RedisTemplate`, Lettuce, and the Redis listener container.
- Validation handles `@NotBlank` and `@Size`.
- Testcontainers runs real Redis in integration tests.

The example uses Java 17 and Spring Boot 3.x. Projects using Maven, WebFlux, or other Spring Boot versions should adjust APIs and dependency metadata accordingly.

## 9. Source File Layout

```text
src/main/java/com/example/notifications/
  NotificationsApplication.java
  NotificationEvent.java
  NotificationRequest.java
  PublishReceipt.java
  NotificationPublisher.java
  RedisPubSubConfiguration.java
  RedisNotificationSubscriber.java
  SseNotificationHub.java
  NotificationController.java

src/main/resources/
  application.yml
  static/index.html
```

Components are separated so the **Redis subscriber does not depend directly on the HTTP Controller**, and the publisher does not need to know which instance holds which browser.

## 10. Configuring Spring Redis and the Channel

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s

app:
  notifications:
    channel: demo:notifications
```

`app.notifications.channel` is an application-specific configuration property, not a built-in Redis property.

In real environments:

- The Redis endpoint must sit on a private network.
- Username/password must live in a secret manager or protected config.
- Enable TLS and verify certificates if the Redis endpoint requires it.
- With Sentinel/Cluster, use appropriate configuration rather than hardcoding an old primary endpoint.
- Publisher and subscriber **must use the exact same channel**.

A common mistake is the publisher using `demo:notifications` while the subscriber uses `demo:notification`. Redis does not warn about channel typos: it simply has no matching recipients.

## 11. Entry Point and Heartbeat Scheduling

`NotificationsApplication.java`:

```java
package com.example.notifications;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class NotificationsApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotificationsApplication.class, args);
    }
}
```

`@EnableScheduling` supports the SSE heartbeat in a later section. It is not required by Redis Pub/Sub itself.

With the Spring Data Redis starter, Spring Boot auto-configures `StringRedisTemplate`/`RedisConnectionFactory`. There is no need to write a manual Lettuce factory for a simple standalone example.

## 12. Notification JSON Contract

Each message follows a clear schema:

```json
{
  "id": "b16e7484-142b-4e41-a219-fb6170d6d74a",
  "type": "ANNOUNCEMENT",
  "text": "Maintenance schedule has just been updated",
  "createdAt": "2026-11-13T03:00:00Z"
}
```

`NotificationEvent.java`:

```java
package com.example.notifications;

import java.time.Instant;

public record NotificationEvent(
        String id,
        String type,
        String text,
        Instant createdAt) {
}
```

- `id` enables application-level correlation/dedup.
- `type` lets the frontend categorize notifications.
- `text` is user-provided data and must be validated and rendered safely.
- `createdAt` is when the publisher created the event, **not** when the browser received it.

Java 17 records serialize/deserialize cleanly with Spring Boot's `ObjectMapper`. If the application uses a custom Jackson configuration, ensure `Instant` support is registered and formats agree across instances.

## 13. Validating HTTP Requests

`NotificationRequest.java`:

```java
package com.example.notifications;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NotificationRequest(
        @NotBlank
        @Size(max = 500)
        String text) {
}
```

In this lab, clients only submit the message text. **Clients must not choose the Redis channel or sensitive notification types.**

`@NotBlank` and `@Size` are minimal validation; production also needs authentication, authorization, rate limiting, payload byte caps, anti-spam controls, and rules governing what content may be broadcast.

## 14. PublishReceipt Is Not Confirmation of User Delivery

`PublishReceipt.java`:

```java
package com.example.notifications;

import java.time.Instant;

public record PublishReceipt(
        String eventId,
        Instant createdAt,
        long redisSubscriberConnections) {
}
```

Redis `PUBLISH` returns the count of subscribed clients at the Redis layer. `redisSubscriberConnections` illustrates that count, but it is **neither the number of open SSE browsers, nor the number of users who read it**, nor a delivery guarantee.

In a real API you may omit this field from external responses and record it only as an internal metric.

## 15. Writing the Publisher with StringRedisTemplate

`NotificationPublisher.java`:

```java
package com.example.notifications;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;
    private final String channel;

    public NotificationPublisher(
            StringRedisTemplate redis,
            ObjectMapper mapper,
            @Value("${app.notifications.channel}") String channel) {

        this.redis = redis;
        this.mapper = mapper;
        this.channel = channel;
    }

    public PublishReceipt publish(NotificationRequest request)
            throws JsonProcessingException {

        NotificationEvent event = new NotificationEvent(
                UUID.randomUUID().toString(),
                "ANNOUNCEMENT",
                request.text().trim(),
                Instant.now());

        String payload = mapper.writeValueAsString(event);
        Long subscribers = redis.convertAndSend(channel, payload);

        return new PublishReceipt(
                event.id(),
                event.createdAt(),
                subscribers == null ? 0L : subscribers);
    }
}
```

`StringRedisTemplate` publishes JSON strings using String serializers. Subscribers must share the exact same encoding contract.

### When Subscriber Count Is 0

If no Redis subscriber is currently subscribed, `PUBLISH` can still succeed and return `0`. Redis does not buffer messages waiting for a future subscriber.

### On Redis Timeout

If the caller loses the response after sending the command, it cannot be sure Redis did not execute `PUBLISH`. Retrying unconditionally can cause duplicate notifications. `event.id` helps deduplicate in downstream systems, though generating a fresh UUID on every retry defeats idempotency. For critical notifications, use a stable operation ID and a durable store.

## 16. Creating RedisMessageListenerContainer

`RedisPubSubConfiguration.java`:

```java
package com.example.notifications;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class RedisPubSubConfiguration {

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory factory,
            RedisNotificationSubscriber listener,
            @Value("${app.notifications.channel}") String channel) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);
        container.addMessageListener(
                listener,
                new ChannelTopic(channel));
        return container;
    }

    @Bean("notificationFanoutExecutor")
    ThreadPoolTaskExecutor notificationFanoutExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(256);
        executor.setThreadNamePrefix("notification-fanout-");
        executor.initialize();
        return executor;
    }
}
```

`RedisMessageListenerContainer` manages subscription lifecycle and dispatches messages to `MessageListener`. `ChannelTopic` subscribes to an exact channel name; `PatternTopic` is used for pattern subscriptions.

The executor here handles application-side fan-out; it does not turn Pub/Sub into a durable queue. Queue capacity 256 and a pool of 2–4 threads are lab values that must be tuned under real load.

### Subscription Startup Is Not Strictly Synchronous

Creating the container bean **does not prove** the Redis subscription is active immediately. Publishing too early can drop messages. Integration tests should wait until the subscription is ready rather than using arbitrary `Thread.sleep` calls.

## 17. Defining the Redis Subscriber

`RedisNotificationSubscriber.java`:

```java
package com.example.notifications;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class RedisNotificationSubscriber implements MessageListener {

    private final ObjectMapper mapper;
    private final SseNotificationHub hub;
    private final Executor fanoutExecutor;

    public RedisNotificationSubscriber(
            ObjectMapper mapper,
            SseNotificationHub hub,
            @Qualifier("notificationFanoutExecutor")
            Executor fanoutExecutor) {
        this.mapper = mapper;
        this.hub = hub;
        this.fanoutExecutor = fanoutExecutor;
    }

    @Override
    public void onMessage(Message message, byte[] pattern) {
        try {
            NotificationEvent event = mapper.readValue(
                    message.getBody(),
                    NotificationEvent.class);

            fanoutExecutor.execute(() -> hub.broadcast(event));
        } catch (IOException invalidJson) {
            recordMalformedMessage(invalidJson);
        } catch (RejectedExecutionException overloaded) {
            recordDroppedMessage(overloaded);
        }
    }

    private void recordMalformedMessage(Exception cause) {
        // Replace with structured logging/metrics as appropriate.
    }

    private void recordDroppedMessage(Exception cause) {
        // Replace with metrics + alerts; do not retry infinitely.
    }
}
```

The callback parses the payload and hands fan-out off to the executor. If SSE delivery is slow, do not block the Redis message-receiving thread with network blocking calls.

**Limitation to recognize:** when the queue is full, the sample code drops the fan-out task and records a drop. This is only acceptable for best-effort notifications. `recordMalformedMessage` and `recordDroppedMessage` are unimplemented instrumentation hooks that must be completed before production.

## 18. SSE Hub Managing Browser Connections

`SseNotificationHub.java`:

```java
package com.example.notifications;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Component
public class SseNotificationHub {

    private final Map<String, SseEmitter> clients =
            new ConcurrentHashMap<>();

    public SseEmitter connect() {
        String id = UUID.randomUUID().toString();
        SseEmitter emitter = new SseEmitter(30L * 60_000L);

        clients.put(id, emitter);

        emitter.onCompletion(
                () -> clients.remove(id, emitter));

        emitter.onTimeout(() -> {
            clients.remove(id, emitter);
            emitter.complete();
        });

        emitter.onError(error -> clients.remove(id, emitter));

        try {
            emitter.send(SseEmitter.event()
                    .name("connected")
                    .data("ready"));
        } catch (IOException | IllegalStateException error) {
            clients.remove(id, emitter);
            emitter.completeWithError(error);
        }

        return emitter;
    }

    public void broadcast(NotificationEvent notification) {
        for (Map.Entry<String, SseEmitter> entry : clients.entrySet()) {
            SseEmitter emitter = entry.getValue();

            try {
                synchronized (emitter) {
                    emitter.send(SseEmitter.event()
                            .name("notification")
                            .id(notification.id())
                            .data(notification, MediaType.APPLICATION_JSON));
                }
            } catch (IOException | IllegalStateException error) {
                disconnect(entry.getKey(), emitter);
            }
        }
    }

    @Scheduled(fixedDelay = 25_000L)
    public void heartbeat() {
        for (Map.Entry<String, SseEmitter> entry : clients.entrySet()) {
            SseEmitter emitter = entry.getValue();

            try {
                synchronized (emitter) {
                    emitter.send(SseEmitter.event()
                            .comment("heartbeat"));
                }
            } catch (IOException | IllegalStateException error) {
                disconnect(entry.getKey(), emitter);
            }
        }
    }

    private void disconnect(String id, SseEmitter emitter) {
        clients.remove(id, emitter);
        emitter.complete();
    }

    public int localConnections() {
        return clients.size();
    }
}
```

**Why ConcurrentHashMap?** Browser clients can connect and disconnect concurrently while the listener fans out messages. The registry must support concurrent modification.

**Why synchronized(emitter)?** Heartbeats and fan-outs run on different threads. Locking reduces the risk of two `send` calls writing to the same emitter simultaneously. It does not guarantee global ordering and does not replace backpressure.

**Why cleanup callbacks?** If a browser closes its tab and the emitter is never removed, the registry grows indefinitely and leaks memory. `onCompletion`, `onTimeout`, `onError`, and `send` error handling keep cleanup intact.

**Why a heartbeat?** Periodic SSE comment lines help keep reverse proxies from closing idle connections prematurely. A heartbeat does **not** prove the Redis subscription is healthy and is **not** a notification ACK.

### Lab Version Limitation

A very slow browser can stall `emitter.send(...)`, blocking the fan-out task. Production should consider **per-client bounded queues**, timeout/drop policies, SSE connection limits, WebFlux SSE, or a dedicated realtime gateway at large client scale.

## 19. REST Controller for Publishing and Subscribing

`NotificationController.java`:

```java
package com.example.notifications;

import com.fasterxml.jackson.core.JsonProcessingException;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/notifications")
public class NotificationController {

    private final NotificationPublisher publisher;
    private final SseNotificationHub hub;

    public NotificationController(
            NotificationPublisher publisher,
            SseNotificationHub hub) {
        this.publisher = publisher;
        this.hub = hub;
    }

    @PostMapping
    public ResponseEntity<PublishReceipt> publish(
            @Valid @RequestBody NotificationRequest request)
            throws JsonProcessingException {

        PublishReceipt receipt = publisher.publish(request);
        return ResponseEntity.accepted().body(receipt);
    }

    @GetMapping(
            path = "/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream() {
        return hub.connect();
    }
}
```

`POST` returns HTTP 202 once Redis `PUBLISH` responds; this means the API **published to Redis**, not that browsers displayed it.

In real products, add `@RestControllerAdvice` or error handling so Redis exceptions do not leak internal details, and HTTP responses properly reflect connection/ACL/timeout errors. Also add authentication/authorization if POST should not be public.

## 20. Frontend Receiving SSE with EventSource

Create `src/main/resources/static/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spring Data Redis Pub/Sub</title>
</head>
<body>
  <h1>Real-time Notifications</h1>
  <input id="text" maxlength="500" value="Hello Pub/Sub">
  <button id="send">Send</button>
  <p id="status">Connecting...</p>
  <ul id="messages"></ul>

  <script>
    const status = document.getElementById("status");
    const messages = document.getElementById("messages");
    const input = document.getElementById("text");

    const stream = new EventSource("/api/notifications/stream");

    stream.addEventListener("open", () => {
      status.textContent = "SSE connected";
    });

    stream.addEventListener("connected", () => {
      status.textContent = "SSE ready";
    });

    stream.addEventListener("notification", (message) => {
      const event = JSON.parse(message.data);
      const item = document.createElement("li");

      // Do not use innerHTML with data from Redis.
      item.textContent = event.createdAt + " — " + event.text;
      messages.prepend(item);
    });

    stream.addEventListener("error", () => {
      status.textContent = "Disconnected, EventSource is retrying";
    });

    document.getElementById("send").addEventListener(
      "click", async () => {
        const response = await fetch("/api/notifications", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({text: input.value})
        });

        if (!response.ok) {
          status.textContent = "Publish failed: " + response.status;
        }
      });

    window.addEventListener("beforeunload", () => stream.close());
  </script>
</body>
</html>
```

`EventSource` maintains a streaming HTTP connection. When the server sends a `notification` event, the browser parses JSON and inserts the text into the list.

**XSS protection:** `textContent` renders literal text without executing HTML from the payload. Never write `item.innerHTML = event.text` for untrusted content.

### Same Origin for Frontend and Server

The HTML above is served by Spring Boot's static resource handler on the same origin as the API. If the frontend runs on a different origin, configure CORS, cookie/session/credentials, and CSRF appropriately. Browser `EventSource` does not natively allow setting arbitrary custom HTTP headers like `fetch`; avoid passing secret access tokens in query strings.

## 21. Running the Demo

Steps:

1. Start the lab Redis.
2. Run the Spring Boot app on port 8080.
3. Open `http://localhost:8080/` in two tabs.
4. Wait for status `SSE ready`.
5. Type a message and click **Send**.
6. Observe both tabs receiving the `notification` event.

Actual flow:

```text
Browser POST
    |
    v
NotificationController
    |
    v
NotificationPublisher
    |
    v
StringRedisTemplate.convertAndSend
    |
    v
Redis PUBLISH demo:notifications JSON
    |
    v
RedisMessageListenerContainer
    |
    v
RedisNotificationSubscriber
    |
    v
NotificationFanoutExecutor
    |
    v
SseNotificationHub.broadcast
    |
    +--> Browser tab 1
    +--> Browser tab 2
```

Do not publish immediately upon Spring process startup assuming the subscriber is already listening; Redis subscriptions may be established asynchronously.

## 22. Publishing with curl and PowerShell

On a Unix shell:

```bash
curl -i -X POST http://localhost:8080/api/notifications \
  -H "Content-Type: application/json" \
  -d '{"text":"Notification from HTTP API"}'
```

On Windows PowerShell:

```powershell
$body = @{ text = "Notification from PowerShell" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8080/api/notifications" -Method Post -ContentType "application/json" -Body $body
```

Sample response:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "eventId": "9e949e39-3033-48ab-91a4-7d5cfcd091cb",
  "createdAt": "2026-11-13T03:00:00Z",
  "redisSubscriberConnections": 1
}
```

Actual UUIDs and timestamps will differ. If no subscribers are connected, the count may be 0 and Redis does not persist the message.

## 23. Viewing the SSE Stream from a Terminal

On a shell with curl:

```bash
curl -N http://localhost:8080/api/notifications/stream
```

On Windows PowerShell:

```powershell
curl.exe -N http://localhost:8080/api/notifications/stream
```

An SSE stream looks like:

```text
event: connected
data: ready

id: 9e949e39-3033-48ab-91a4-7d5cfcd091cb
event: notification
data: {"id":"9e949e39-3033-48ab-91a4-7d5cfcd091cb","type":"ANNOUNCEMENT","text":"Hello","createdAt":"2026-11-13T03:00:00Z"}

:heartbeat
```

`id:` in SSE allows the browser to store `Last-Event-ID` on reconnect per the SSE protocol, **but it does not create Redis Pub/Sub replay**.

Proxies may buffer SSE responses, delaying notifications, or close idle connections. Production deployments must verify reverse-proxy buffering, timeouts, and keep-alive settings.

## 24. Inspecting What Java Published with Redis CLI

Terminal A:

```bash
redis-cli SUBSCRIBE demo:notifications
```

Terminal B publishes via the HTTP API. Terminal A should display JSON matching `NotificationEvent`.

If you run:

```bash
redis-cli PUBLISH demo:notifications "hello"
```

The Redis subscriber receives `hello`, but **the example Spring listener will not broadcast SSE** because `hello` is not valid JSON matching the `NotificationEvent` schema. That is a payload contract error, not Redis dropping the message.

To test the Spring listener via CLI, send valid JSON:

```bash
redis-cli PUBLISH demo:notifications '{"id":"manual-1","type":"ANNOUNCEMENT","text":"Hello CLI","createdAt":"2026-11-13T03:00:00Z"}'
```

Windows shell quoting differs from Unix; you can use `redis-cli` interactive mode to enter the message.

## 25. Why Does the PUBLISH Count Differ from the Browser Count?

Suppose:

```text
Spring instance A:
  1 Redis subscriber
  100 SSE browsers

Spring instance B:
  1 Redis subscriber
  50 SSE browsers

Redis PUBLISH:
  sees the matching Redis subscriber connections,
  cannot directly count the 150 SSE browser clients.
```

`convertAndSend` returns information at the Redis layer; it does not prove:

- JSON was parsed successfully.
- The executor had capacity to process it.
- The SSE connection is still alive.
- Browsers received the event.
- Users read the notification.
- The event was persisted.

Measuring *browser delivery* requires frontend callbacks/ACKs and persisting state in an appropriate data store; Redis Pub/Sub itself has no ACKs.

## 26. Running Two Spring Boot Instances

Run two JVM processes with the same Redis/channel configuration and different HTTP ports:

```text
Instance A:
  server.port = 8080

Instance B:
  server.port = 8081

Both:
  Redis = localhost:6379
  app.notifications.channel = demo:notifications
```

Open `http://localhost:8080/` and `http://localhost:8081/` in two browser tabs.

Publish through A:

```bash
curl -X POST http://localhost:8080/api/notifications \
  -H "Content-Type: application/json" \
  -d '{"text":"Published from instance A"}'
```

When both Redis subscriptions and SSE connections are active, browsers on **both A and B** receive the notification. This is the strength of Redis Pub/Sub in multi-node architectures: the publisher does not need to know which node holds which browser.

**Note:** simply pointing two instances at the same Redis server does not make an instance without a registered Redis listener receive messages. Every instance needs a subscription or an equivalent fan-out mechanism.

## 27. Testing an Offline Subscriber to Observe At-Most-Once

Procedure:

1. With A and B running, publish a message and confirm both receive it.
2. Stop B.
3. Publish three messages into Redis through A.
4. Restart B and reconnect its browser.
5. B **does not** receive the three messages published while offline.
6. Publish a fourth message once B is subscribed; B receives the new message.

Redis does not maintain per-subscriber queues. Messages published while B is offline cannot be recovered from the channel alone.

If the product requires "users logging back in still see unread notifications", **persist notifications in a database/Streams** and provide a history API.

## 28. Browser Reconnect Does Not Mean Replay

SSE `EventSource` can reconnect automatically:

```text
T1 Browser receives event id=10
T2 Network drops
T3 Redis Pub/Sub publishes events 11, 12, 13
T4 Browser reconnects sending Last-Event-ID=10
```

The current application **has no store** holding 11–13. It only receives new events from Redis once the subscription/connection is active again. Thus it cannot replay missed events using `Last-Event-ID`.

A replay mechanism requires:

- A persistent store (SQL or Redis Streams with retention).
- A cursor/event ID to query unseen entries.
- An API to fetch events after the cursor.
- Per-user authentication and authorization.
- Deduplication between live events and history.
- Retention limits and cleanup rules.

Never promise "no missed notifications" simply because SSE reconnects automatically.

## 29. When History Must Be Saved: Persist First, Then Signal

A suitable architecture for a notification center:

```text
User action
   |
   v
SQL transaction
   |
   +--> INSERT notification
   +--> INSERT outbox_event
   |
   v
COMMIT
   |
   v
Outbox dispatcher
   |
   v
Redis PUBLISH "notification-created"
   |
   v
Browser receives signal
   |
   v
GET /api/notifications?after=<cursor>
   |
   v
SQL: notifications with authorization
```

Here the **database** holds the source of truth. Pub/Sub merely notifies the browser that fresh data should be fetched.

Why use an outbox? If the SQL transaction commits and the process dies before `PUBLISH`, the signal event is lost. An outbox lets the dispatcher retry after a crash. It does not magically make an offline Pub/Sub listener receive missed messages, yet the UI can still load accurate data from the database upon reconnecting.

## 30. Securing Redis Pub/Sub with ACLs

Redis ACLs distinguish **key patterns** from **Pub/Sub channel patterns**.

For example, a publisher principal only needs:

```text
+publish
&demo:notifications
```

A subscriber principal only needs:

```text
+subscribe
&demo:notifications
```

On a lab Redis with ACLs (Redis 6+), you can use `redis-cli` interactively as an admin user:

```text
ACL SETUSER lab_publisher reset on >CHANGE_ME_PUB +ping +publish &demo:notifications
ACL SETUSER lab_subscriber reset on >CHANGE_ME_SUB +ping +subscribe &demo:notifications
```

These passwords are placeholders; never use them in production. Enter them directly in `redis-cli` interactive mode rather than pasting into a shell where `>` and `&` can be interpreted as shell operators.

### Negative Permission Tests

- Publisher tries `SUBSCRIBE` → denied if lacking permission.
- Subscriber tries `PUBLISH` → denied if lacking permission.
- Either tries channel `private:secret` → `NOPERM`.
- App uses wrong user/password → `NOAUTH`/`WRONGPASS`, not "message hasn't arrived yet".
- The Redis client needs permissions to open connections and run Spring health check commands if enabled; test with the real application path.

In a simple lab where one Spring app both publishes and subscribes, one user can have both `+publish +subscribe`. If your threat model requires separation, configure separate connection factories/templates and listener containers with distinct credentials and verify bean wiring carefully.

**Do not grant `+@all ~* &*` just to silence NOPERM.**

## 31. PatternTopic When Multiple Channels Are Needed

Example channels:

```text
demo:notifications:orders
demo:notifications:inventory
demo:notifications:system
```

When pattern subscription is needed, Spring Data Redis supports:

```java
import org.springframework.data.redis.listener.PatternTopic;

container.addMessageListener(
        listener,
        new PatternTopic("demo:notifications:*"));
```

This issues `PSUBSCRIBE`, distinct from exact-channel `SUBSCRIBE`. When using patterns:

- ACLs require `+psubscribe` and matching channel patterns.
- Do not use overly broad wildcards that receive data outside your scope.
- Identify the actual channel from `Message.getChannel()`.
- Subscription/matching overhead can grow with channel count and subscriber count.
- Pattern subscriptions do not add replay.

For per-user or per-tenant notifications, never subscribe with a wildcard and broadcast every payload to every browser.

## 32. Private Notifications Require Application-Layer Authorization

**The demo broadcasts public announcements only.** If a notification carries information for user-42, browsers belonging to user-43 must never see it.

Design approaches:

1. The SSE endpoint authenticates users and binds each connection to a verified principal.
2. Notification data is stored in a database with per-user/tenant authorization.
3. Redis Pub/Sub broadcasts only an event ID or "new data available" hint, never sensitive payloads over a global channel.
4. The app routes to the specific target client sessions rather than broadcasting globally.
5. For per-tenant/room channels, the server derives the channel from authenticated identity, never trusting client-supplied channels.
6. Never put tokens or session secrets into Redis channel names.
7. When using dynamic subscriptions, cap channel counts and manage cleanup lifecycles.

Redis ACLs restrict Redis principals, **not browser users**. Even when a Redis subscriber is authorized on a channel, Spring application code must still enforce authorization properly.

## 33. Preventing XSS and Malformed Data

Pub/Sub messages can originate from multiple services or producers. Subscribers must treat payloads as untrusted external data:

- Enforce JSON schema and type validation.
- Cap text/payload sizes.
- Never execute arbitrary code from payloads.
- Never log raw PII or secrets.
- Render in the frontend using `textContent`.
- Never use `innerHTML` with unsanitized text.
- Require authentication, authorization, and rate limiting on HTTP POST if it affects users.
- With cookie-based sessions, apply CSRF protection to POST per security policy.

A payload delivered by Redis **does not automatically become trustworthy** just because the server resides on a private network.

## 34. Reconnect Failures and Listener Lifecycle

A Redis subscription is state tied to a connection:

```text
Spring process starts
      |
      v
Connect Redis
      |
      v
SUBSCRIBE
      |
      v
ACTIVE
      |
      +--> messages
      |
      +--> network failure
                  |
                  v
               reconnect
                  |
                  v
               resubscribe
```

During the disconnected window, Redis Pub/Sub does not buffer messages for catch-up. `RedisMessageListenerContainer` manages lifecycle, yet the application must monitor subscription errors/reconnects and test them in practice.

**A `PING` over a separate Redis connection does not prove the subscription connection is actively receiving messages.**

Do not configure Kubernetes liveness probes tied to a remote Redis subscriber so that every pod restarts whenever Redis blips; restarting pods will not fix a Redis outage and can trigger a reconnect storm.

## 35. Slow SSE Clients and Backpressure

The demo maintains a list of emitters per instance. One slow browser can stall `send`, building up a backlog in `notificationFanoutExecutor`.

Warning signs:

- Increasing executor queue depth.
- Increasing fan-out p95/p99 latency.
- Increasing rejected tasks/dropped notifications.
- Servlet async contexts holding memory longer.
- Frequent SSE connection timeouts and reconnects.

A production-oriented approach:

```text
Redis message
      |
      v
Validate JSON
      |
      v
Bounded dispatcher
      |
      +--> Client A queue (bounded)
      +--> Client B queue (bounded)
      +--> Client C queue (bounded)
                       |
                       +--> Slow client: drop/close per policy
```

At large browser scale, consider WebFlux, a realtime gateway, or a platform built for high-scale broadcasting. Never make queues unbounded: at high Redis/message rates, the JVM can run out of memory before the bottleneck is noticed.

**Limitation of the lab's guarantees:** a dropped fan-out task means browsers can miss a notification. That is why mandatory delivery requires persistent storage and replay.

## 36. Redis Cluster and Sharded Pub/Sub

In Redis Cluster, traditional Pub/Sub and **sharded Pub/Sub** are distinct models. Redis 7 introduced commands like `SPUBLISH`, `SSUBSCRIBE`, and `SUNSUBSCRIBE` for shard-scoped distribution.

| Model | Commands | What to Verify |
|---|---|---|
| Traditional Pub/Sub | `PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE` | Distribution and fan-out cost across cluster |
| Sharded Pub/Sub | `SPUBLISH`, `SSUBSCRIBE` | Channel hash slot, routing, server/client versions |
| Redis Streams | `XADD`, `XREADGROUP` | Retention, ACK, PEL, and recovery |

Do not assume `RedisMessageListenerContainer` automatically switches to sharded Pub/Sub across every Spring Data Redis version. If sharded mode is required, verify API/Lettuce/Redis version support and test on a real Cluster.

Operational considerations:

- Redis Cluster topology changes/failovers can trigger subscription reconnects.
- Endpoints advertised by Redis nodes must be reachable by application instances.
- ACL channel rules must be consistent across the infrastructure.
- Subscriber counts from one node are not browser delivery metrics.
- Failovers can introduce a window of lost messages.
- Measure network and CPU under multi-channel/multi-subscriber fan-out, not just `PUBLISH` latency.

## 37. Using Testcontainers to Test Real Redis Pub/Sub

Mocking `StringRedisTemplate` only proves Java called `convertAndSend`; it does not prove Redis delivered anything to a real subscriber.

Test skeleton:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisPubSubIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
                () -> REDIS.getMappedPort(6379));
    }

    // @Autowired NotificationPublisher publisher;
    // @Autowired ObjectMapper mapper;
    // Publish/subscribe tests in the next section.
}
```

Test Redis instances must be isolated. When running fault injection, ACL denials, or killing containers, never target production Redis or another team's shared Redis.

## 38. Integration Test: Waiting for a Real Subscription with Lettuce

An independent message-receiving test using Lettuce can use `RedisPubSubAdapter`. Unlike flaky sleeps, the test waits for Redis to confirm the subscription:

```java
import io.lettuce.core.RedisClient;
import io.lettuce.core.pubsub.RedisPubSubAdapter;
import io.lettuce.core.pubsub.StatefulRedisPubSubConnection;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

String channel = "demo:notifications";
String uri = "redis://" + REDIS.getHost() + ":"
        + REDIS.getMappedPort(6379);

RedisClient client = RedisClient.create(uri);
BlockingQueue<String> received = new LinkedBlockingQueue<>();
CountDownLatch subscribed = new CountDownLatch(1);

try (StatefulRedisPubSubConnection<String, String> connection =
        client.connectPubSub()) {

    connection.addListener(new RedisPubSubAdapter<String, String>() {

        @Override
        public void subscribed(String name, long count) {
            if (channel.equals(name)) {
                subscribed.countDown();
            }
        }

        @Override
        public void message(String name, String payload) {
            if (channel.equals(name)) {
                received.add(payload);
            }
        }
    });

    connection.async().subscribe(channel);

    if (!subscribed.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("SUBSCRIBE not ready");
    }

    publisher.publish(new NotificationRequest("Lab event"));

    String payload = received.poll(5, TimeUnit.SECONDS);
    assertThat(payload).isNotNull();

    NotificationEvent event =
            mapper.readValue(payload, NotificationEvent.class);
    assertThat(event.text()).isEqualTo("Lab event");
} finally {
    client.shutdown();
}
```

This snippet is the **body of an integration test**, assuming `REDIS`, `publisher`, and `mapper` are wired/injected and AssertJ `assertThat` is imported. The test proves **Redis publish → a real subscriber**; it does not yet test Spring listener → browser SSE.

An end-to-end HTTP test suite should:

1. Connect to SSE and wait for `connected`.
2. Ensure the Redis listener has subscribed.
3. Publish via the HTTP API.
4. Read the `notification` SSE event and assert JSON event ID/text.
5. Close the browser connection and verify cleanup.
6. Repeat with two instances to verify fan-out.

Never use `Thread.sleep(100)` as proof that a subscription is ready.

## 39. Recommended Test Matrix

| ID | Scenario | Expected Behavior |
|---|---|---|
| PUB-01 | Subscriber online and valid message | Receives exact JSON |
| PUB-02 | No subscribers | No replay/history; publish may return 0 |
| PUB-03 | Wrong channel | Not received |
| PUB-04 | Invalid JSON | Parse error recorded, not broadcast |
| PUB-05 | Redis unavailable | API does not report successful delivery |
| PUB-06 | Timeout after PUBLISH | Distinguish uncertain outcome; dedup policy if needed |
| SUB-01 | Spring listener startup | Subscription confirmed before publishing |
| SUB-02 | Redis restart | Reconnects; messages during outage may be lost |
| SUB-03 | ACL missing SUBSCRIBE/channel | `NOPERM` detected |
| SSE-01 | Single browser | Receives event |
| SSE-02 | Multiple browsers on one instance | All connected browsers receive event |
| SSE-03 | Disconnect/timeout | `SseEmitter` cleaned up |
| SSE-04 | Browser reconnect | Receives new events, does not replay old ones |
| SSE-05 | Slow client | Overload/queue/drop policy emits metrics |
| MULTI-01 | Two Spring instances | Publish via A, browsers on A and B receive |
| MULTI-02 | B offline | Does not catch up upon restart |
| ACL-01 | Publisher only allowed to publish | Cannot subscribe or use other channels |
| ACL-02 | Subscriber only allowed to subscribe | Cannot publish or use other channels |
| SEC-01 | Blank/oversized text | Rejected by validation |
| SEC-02 | Text containing HTML/script | Does not execute thanks to `textContent` |
| LOAD-01 | N browsers, M msgs/s | Measure fan-out p99, queue, heap, drops |
| STORE-01 | With DB notification store | Reconnect loads missed history |

Suites should be separated into Redis protocol, Spring integration, browser SSE, multi-instance, ACL/security, and load/fault tests. Never claim reliability based solely on a single happy-path test.

## 40. Production Observability and Incident Handling

Metrics worth tracking:

| Signal | Meaning |
|---|---|
| HTTP publish success/error rate | Whether publishers can reach Redis |
| Redis PUBLISH latency | Command/connection overhead |
| Redis subscriber count | Whether listeners are subscribed; not browser count |
| Listener reconnect/subscription errors | Whether the app experienced missed message windows |
| Invalid JSON count | Incompatible publisher/schema |
| Executor queue depth/rejections | Whether fan-out is overloaded |
| Local SSE connection count | Browser connections per instance |
| SSE send latency p95/p99 | Slow clients/proxy/servlet pressure |
| SSE disconnect/reconnect rate | Connection stability |
| Publish-to-browser latency | True end-to-end realtime experience |
| Memory/CPU | Headroom as fan-out scales |
| Historical sync errors | If store/replay exists, whether clients can catch up |

**Never attach user IDs, tokens, or raw notification text to metric labels**, to avoid data leaks and high cardinality.

### Quick Troubleshooting

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Redis PUBLISH returns 0 | No matching subscription | Channel name, listener startup, `PUBSUB NUMSUB` |
| CLI sees JSON, browser does not | SSE/JSON parser/executor error | Logs, invalid count, queue, and SSE connection |
| Browser "connected" but no messages | Redis subscription not active | Subscription status, Redis config |
| Only one Spring instance receives | Other instance misconfigured Redis/channel/ACL | Endpoints, channel config, reconnect |
| Duplicate messages | HTTP publisher retries or app fan-out logic | Event IDs and dedup |
| Messages lost on restart | Redis Pub/Sub has no replay | Persistent store/Streams |
| `NOPERM` | Missing Redis channel rule/command | ACL user, `ACL LOG` |
| `NOAUTH`/`WRONGPASS` | Incorrect secret/user | Spring connection factory |
| Browser receives slowly | Reverse proxy buffering, slow client, executor | SSE p99, queue, proxy settings |
| Browser disconnects after idle | SSE timeout/proxy | Heartbeat, keep-alive, reconnect |

## 41. Runbook When Redis or Subscribers Disconnect

1. Identify the failing segment: publisher, Redis, subscriber, or SSE.
2. Check the Redis connection and exact channel name.
3. Check Redis ACL/authentication without printing credentials.
4. Confirm listeners have reconnected and resubscribed.
5. Check executor queue depth, rejected tasks, and SSE connection counts.
6. Do not assume notifications published during downtime were saved.
7. If a persistent store exists, instruct browsers to fetch history after reconnecting.
8. Bound `PUBLISH` retries on uncertain outcomes; do not spam every event again.
9. After recovery, send a synthetic event in an authorized environment and verify end-to-end delivery to an SSE browser.
10. Monitor error rates, drop counts, fan-out p99, and memory post-incident.

Never attempt to fix Pub/Sub issues with `FLUSHDB`, `FLUSHALL`, or restarting all pods. Those will not recover lost messages and can worsen the incident.

## 42. Self-Assessment Questions

**1. Is Redis Pub/Sub a durable queue?**  
No. Messages are delivered only to currently subscribed clients, with no ACKs or replay.

**2. Which Spring Data Redis API does PUBLISH use?**  
`StringRedisTemplate.convertAndSend(channel, payload)`.

**3. Which Spring component manages subscriptions?**  
`RedisMessageListenerContainer` paired with `MessageListener` and `ChannelTopic`/`PatternTopic`.

**4. If PUBLISH returns 2, does that mean two browsers read the message?**  
No. It reflects subscribed connections at the Redis layer, not user acknowledgements.

**5. Why can a single Redis listener serve 100 browser clients?**  
Because the Spring instance receives one Redis message and fans it out across its local SSE connections.

**6. Can SSE EventSource reconnect automatically?**  
Yes, though it does not automatically replay missed Redis Pub/Sub events.

**7. Why is an event ID needed?**  
For correlation/dedup and history queries when a persistent store exists; it does not provide reliability by itself.

**8. Why avoid broadcasting directly on the Redis callback thread?**  
A slow browser can block the subscription callback and cause a backlog.

**9. Does Pub/Sub use Redis ACL key patterns or channel patterns?**  
Channel patterns `&...` and corresponding command permissions.

**10. For private per-user notifications, can you broadcast the full payload to all browsers?**  
No. You need authentication/authorization, scoping, and usually an access-controlled store.

**11. What happens if a producer publishes while a subscriber is offline?**  
The notification is lost for that subscriber; Redis does not retain it for later delivery.

**12. Why did Redis CLI PUBLISH `"hello"` not show up in the demo browser?**  
Because the subscriber expects JSON matching `NotificationEvent`; `"hello"` violates the schema.

**13. When Redis is healthy but SSE is slow, what should you inspect?**  
Executor queue depth, servlet/proxy buffering, SSE client send latency, memory, and reconnects.

**14. If notifications require history and zero loss, what is needed?**  
A persistent store, a cursor/replay API, and where appropriate, an outbox/Streams/queue with ACK and recovery.

**15. At which layer does Redis Pub/Sub differ from WebSocket/SSE?**  
Pub/Sub connects backend servers via Redis; WebSocket/SSE connects the application to browsers.

## 43. Pre-Production Readiness Checklist

- [ ] Decide whether notifications are best-effort or require history/replay.
- [ ] Publisher and subscriber agree on exact channel and JSON schema.
- [ ] Redis connection uses TLS/ACL and proper secret management.
- [ ] Unauthenticated lab Redis is never exposed to public networks.
- [ ] HTTP publish API has validation, authentication, authorization, and rate limiting.
- [ ] Arbitrary channel names from browsers are never accepted.
- [ ] `RedisMessageListenerContainer` is monitored for reconnects/subscription errors.
- [ ] Heavy blocking fan-out does not run on the Redis listener thread.
- [ ] Executors/queues are bounded, and drops emit metrics/alerts.
- [ ] SSE clients have appropriate timeouts, cleanup, and heartbeats.
- [ ] Frontend uses safe rendering (`textContent`).
- [ ] Notifications containing PII never travel over global channels.
- [ ] Redis ACLs separate command and channel permissions.
- [ ] Tested pre-subscription timing and Redis outages.
- [ ] Tested two app instances, multiple SSE browsers, and slow clients.
- [ ] `PUBLISH` counts are never treated as browser delivery acknowledgements.
- [ ] Errors are classified across timeout/NOPERM/NOAUTH/WRONGPASS.
- [ ] Metrics cover p95/p99 publish-to-browser latency, queue depth, and drop counts.
- [ ] For critical data, a persistent store/outbox/Streams and replay API exist.
- [ ] Fault/ACL tests run solely against isolated Redis instances.

## 44. Summary

Using a few Spring Data Redis components, we built a real-time signaling system:

- `StringRedisTemplate.convertAndSend` **publishes JSON** to a Redis channel.
- `RedisMessageListenerContainer` and `MessageListener` **subscribe and receive** messages.
- `SseNotificationHub` uses `SseEmitter` to **fan out** to browsers connected to each instance.
- `EventSource` displays notifications and handles SSE reconnects.
- Redis acts as a **backplane across Spring instances**, eliminating direct instance-to-instance HTTP calls from A to B.

However, **Pub/Sub provides immediate distribution only**. When subscribers drop, apps restart, executors fill up, or browsers are disconnected, notifications can be lost. To build a notification center with history, **persist data first, publish Pub/Sub as an update signal**, and let clients fetch missed entries via cursor; if consumer ACKs and recovery are needed, evaluate Redis Streams or a dedicated message broker.

A sound realtime system does not just deliver messages quickly under ideal conditions—it **explicitly defines what may be lost, what must be stored, how users recover missed items, and how failed deliveries are observed**.

## References

- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html): RedisMessageListenerContainer, MessageListener, and topics.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): Redis operations and `convertAndSend`.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): consumer groups/ACK/replay.
- [Spring Framework — SSE with SseEmitter](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html#mvc-ann-async-sse): using SSE in Spring MVC.
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): delivery semantics and channels.
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/): publishing and reply values.
- [Redis — SUBSCRIBE](https://redis.io/docs/latest/commands/subscribe/): subscribing to channels.
- [Redis — PSUBSCRIBE](https://redis.io/docs/latest/commands/psubscribe/): subscribing by pattern.
- [Redis — ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): command and channel pattern permissions.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): cluster and sharded Pub/Sub.
- [MDN — EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource): SSE browser interface.
- [MDN — Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): SSE format and reconnects.
- [Testcontainers for Java](https://java.testcontainers.org/): isolated Redis server for integration tests.
