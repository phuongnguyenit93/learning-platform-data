# Content-Type, Heartbeat Cadence, and Proxy Buffering in Spring Boot Long-Lived Connections

**Context:** Spring Boot → web-runtime → Long-lived connections. This lesson focuses on the three variables that determine whether an HTTP stream truly reaches users in real time: **Content-Type/data format**, **heartbeats (periodic data sent to keep connections alive / detect dropped clients)**, and **buffering in the application, servlet container, proxy, CDN, and client**. The focus is **Server-Sent Events (SSE)**, alongside comparisons with NDJSON streaming, HTTP long polling, and WebSocket. Includes a runnable **Java 17 + Spring Boot 3.5.16 + Spring MVC + Maven** example, Nginx configuration, `curl -N` verification, timeout calculation, production debugging, and WebFlux notes.

> A TCP connection staying open for minutes **does not guarantee** the client receives each event as soon as the server emits it. A `write` call in Java, a `200` response status, and a `Transfer-Encoding: chunked` header likewise **do not prove** the path is free of proxy/client buffering. You must measure the timestamps **event generated → server flush → proxy read → client receive** on the real path.

## 1. What Are Long-Lived Connections and Which Layers Are Involved?

A typical HTTP request has a short lifecycle: the client sends a request, the server computes the result, returns the response, and finishes. With a long-lived connection, the response **stays open** while the server emits pieces of data at different times. Examples: report progress, notifications, dashboard events, log tailing, streamed AI output, monitoring UIs, and data feeds.

~~~text
Client (browser/curl)
    │ GET /events, Accept: text/event-stream
    │
    ▼
CDN / Load Balancer / Ingress
    │  Has idle timeout, HTTP version, buffering policy
    ▼
Reverse Proxy (Nginx)
    │  Has proxy_buffering, proxy_read_timeout, gzip/proxy_cache
    ▼
Spring Boot (Servlet MVC or WebFlux)
    │  Response Content-Type + individual events/frames + flush
    │
    ├─ T+0s   event: ready  ─────► proxy ─────► client
    ├─ T+10s  : heartbeat   ─────► proxy ─────► client
    ├─ T+20s  : heartbeat   ─────► proxy ─────► client
    └─ T+30s  data: update  ─────► proxy ─────► client

If the proxy accumulates/waits for a large buffer:
    At T+0s, 10s, 20s, 30s bytes arrive at the proxy, yet the client sees nothing.
    The client only sees a batch after the buffer fills or the response ends.
~~~

You must distinguish **a long-lived connection**, **a long-lived HTTP response**, **changing connections on reconnect**, and **reusing a TCP socket across subsequent HTTP requests**. HTTP/1.1 keep-alive is not an SSE body heartbeat.

### 1.1. Techniques Used

| Technique | Common Protocol/Media Type | Characteristics | Heartbeat Mechanism |
| --- | --- | --- | --- |
| **SSE (EventSource)** | HTTP GET + `text/event-stream` | One-way server → browser, EventSource auto-reconnect | **Comment-only SSE frame** or application event |
| **NDJSON / JSON Lines stream** | `application/x-ndjson` | Each line is complete JSON; client parses lines itself | A no-op/heartbeat record per app contract |
| **Arbitrary HTTP response streaming** | `text/plain`, `application/octet-stream`... | Byte stream, no universal event frame standard | Protocol-specific no-op bytes |
| **Long polling** | Usually `application/json` | A request waits for data then returns **one complete response**; client issues another request | Timeouts and reissued requests; frames aren't necessarily sent mid-response |
| **WebSocket** | HTTP Upgrade or HTTP/2 CONNECT and WebSocket frames | Bidirectional, not an SSE Content-Type | WebSocket **Ping/Pong control frames** |
| **gRPC streaming** | HTTP/2, `application/grpc` | Dedicated message framing/flow control, not EventSource | HTTP/2/gRPC keepalive per client/server policy |

These media types **do not substitute for one another**. Browser `EventSource` understands `text/event-stream` and the fields `data`, `event`, `id`, `retry`. It does not automatically parse an `application/json` or `application/x-ndjson` stream into SSE events. Use `fetch` + a streaming reader when you want to parse NDJSON yourself.

## 2. The Right Content-Type Is Not Just a Decorative Header

### 2.1. SSE Must Have `text/event-stream`

For SSE, the server typically returns:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream;charset=UTF-8
Cache-Control: no-cache, no-transform
X-Accel-Buffering: no

event: ready
id: 1
retry: 3000
data: connected

: heartbeat

event: progress
id: 2
data: {"percent":42}

~~~

The example headers are illustrative: `Transfer-Encoding`, `Connection`, `Date`, and header ordering can vary by HTTP version, web server, and proxy. **The SSE body format** carries the core semantics:
- each `data: ...` line appends event data;
- `event: progress` sets the event name so the browser can register `addEventListener("progress", ...)`;
- `id: 2` provides the event ID; upon auto-reconnect, EventSource may send `Last-Event-ID`;
- `retry: 3000` instructs the browser to use a 3,000 ms reconnect interval (some browsers apply their own policies);
- **a blank line** terminates the event frame and causes the parser to dispatch the data;
- a line starting with **`:`** is an **SSE comment**; the EventSource client **ignores it** in JavaScript callbacks, yet bytes still travel over the wire.

An SSE stream sends sequential events over time—it **does not** wrap all events into a single JSON array and wait for a closing `]` before sending.

### 2.2. Valid SSE Heartbeat Frame Syntax

A simple comment heartbeat:

~~~text
: heartbeat

~~~

That is, the UTF-8 byte sequence `": heartbeat\n\n"`. The double newline separates the comment into its own block; comments do not trigger a `message` event in JavaScript. You can send `":\n\n"` if no label is needed. Using Windows CRLF is also valid under the SSE specification.

**Do not send a lone space character**, a `{}` JSON object, or a `"ping"` string expecting EventSource to ignore it. Sending `data: ping\n\n` delivers **a real data event** to the browser, potentially triggering handlers. With a **comment-only** heartbeat, EventSource invokes neither `onmessage` nor `addEventListener`; if the application wants JavaScript to monitor liveness, use an event named `heartbeat` and treat it as a real event.

### 2.3. Content Negotiation and Charset

A typical Spring MVC endpoint:

~~~java
@GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    return new SseEmitter();
}
~~~

This is an **illustrative snippet without sending/cleanup logic**, not a complete endpoint. `produces` declares the media type Spring uses for handler matching and response serialization; returning `SseEmitter` activates the SSE writer. Browser EventSource normally sends `Accept: text/event-stream`, yet **the client sending Accept is not enough**: the server must also return the matching Content-Type and framing.

Standard SSE is **UTF-8**. Do not send UTF-16 or invalid byte streams and call them `text/event-stream`. When embedding JSON inside `data: ...`, serialize JSON properly before placing it in the event (Spring `SseEmitter.event().data(object)` uses a converter if configured); if using raw strings, avoid concatenating JSON from unescaped input.

**Avoid relying on MIME sniffing.** Browsers enforce different policies for `text/plain`, `application/json`, and `text/event-stream`; MIME guessing does not make streaming work properly. With `X-Content-Type-Options: nosniff`, the response must carry the exact accurate Content-Type.

### 2.4. NDJSON Differs from SSE

NDJSON usually uses `Content-Type: application/x-ndjson`, with each line being **one complete JSON object/value**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"seq":1,"type":"tick"}
{"seq":2,"type":"tick"}
{"seq":3,"type":"tick"}
~~~

Each line ends with `\n`. The client reads bytes until encountering a newline before parsing one JSON record. It **lacks** SSE's `event:`/`id:`/`retry:` fields and has no built-in browser EventSource auto-reconnect. To send an NDJSON heartbeat, define an ignorable record such as `{"type":"heartbeat"}\n` and have the client/parser skip passing it to business logic. Do not inject SSE-style `": ping\n\n"` into NDJSON because that is **not valid JSON**.

### 2.5. Why `application/json` Easily Creates the Illusion of "Not Streaming"

When a server intends to send a single JSON object or overall array, serializers, output wrappers, and clients often buffer content until a valid complete structure is formed or the response ends. An `application/json` response **can** be streamed by certain APIs/frameworks, yet **the JSON Content-Type alone provides no message-by-message contract**. When the client needs to parse individual records over time, use NDJSON; when the browser needs to subscribe to server events with auto-reconnect, use SSE; when bidirectional traffic is required, consider WebSocket.

## 3. What Is a Heartbeat For?

A heartbeat is **a tiny piece of data** sent periodically even when no business events occur. It serves two related but distinct purposes:

1. Shows network components with idle timeouts that traffic is still flowing so they do not close the connection solely for prolonged silence.
2. Helps the application **detect client loss sooner**: in Servlet apps, there is usually no callback for remote disconnect the moment a client loses connectivity; the next write attempt raises an `IOException`.

**Heartbeats do not guarantee** a connection will never drop. A proxy might buffer all heartbeats, an LB might enforce an absolute duration cap, browser tabs can undergo background throttling, clients lose connectivity, schedulers stall, or servers restart. SSE clients must still have a **reconnect/resume strategy**.

### 3.1. Calculating the Cadence from Actual Timeouts

Suppose a path has:

| Component | Illustrative Timeout | Meaning |
| --- | --- | --- |
| Spring MVC `SseEmitter` | 300 seconds | **Total** async request lifetime of the emitter if declared as 300,000 ms |
| Nginx `proxy_read_timeout` | 75 seconds | Silence **between two reads from upstream**, not 75 seconds total response |
| A load balancer | 45 seconds | **Assumed configuration** idle timeout on that hop, not a universal default |
| Application heartbeat | 10 seconds | A tiny comment frame on each scheduler tick |

10 seconds is smaller than 45 and 75, leaving margin for jitter, GC pauses, and network delay. Yet after **300 seconds**, `SseEmitter(300_000L)` can still time out per its async lifetime despite heartbeats every 10 seconds, requiring EventSource to reconnect. **Heartbeats do not reset an "absolute request lifetime".** For multi-hour streams, design timeouts by contract, periodic reconnects, and retries instead of arbitrarily setting everything to infinity.

Practical rules:
- set `heartbeat_interval` **below the smallest idle timeout** across hops, with headroom for pauses/jitter;
- do not send heartbeats every few milliseconds because large client counts amplify CPU/network/syscall overhead;
- verify **bytes actually reach the hops**: sending at the server while a proxy buffers means a client-side LB can still time out;
- distinguish upstream read timeout, downstream write timeout, and total request deadline;
- test heartbeats during business inactivity, under high server load, and on abrupt client disconnects.

### 3.2. Do Not Confuse Three Kinds of "Keep-Alive"

| Mechanism | Layer | Emits SSE Bytes in the Response? |
| --- | --- | --- |
| HTTP/1.1 persistent connection / `Connection: keep-alive` | Reuses TCP connections across multiple HTTP requests | **No** |
| TCP keepalive probes | Kernel TCP sends socket probes under specific conditions | **No**; proxy/LB application idle timers may ignore them |
| SSE `: heartbeat\n\n` | HTTP **response body** | **Yes**, provided every hop flushes/forwards properly |
| WebSocket Ping/Pong | WebSocket protocol frames | **Not** SSE bytes; only applies after upgrade |
| HTTP/2 PING frame | Connection-level HTTP/2 control frame | Does not substitute for SSE/application messages under all LB policies |

Do not try to fix silent SSE drops merely with `Connection: keep-alive`. Moreover, it is a **hop-by-hop** header and is not sent over HTTP/2 the way HTTP/1.1 uses it. HTTP/2 multiplexes multiple streams over one connection and remains subject to separate timeouts and policies.

### 3.3. Heartbeats and Disconnect Detection

A Servlet stream broken by a client disconnect is not necessarily detected immediately in the controller. Spring Framework recommends **periodically sending** data (a comment-only SSE or no-op stream item) so the next write surfaces an I/O failure. When `SseEmitter.send(...)` throws `IOException`, in Spring MVC the container normally notifies Spring of the async error; per documentation, **do not manually call `completeWithError` for that `IOException`** as mandatory handling, because the container already does so. Clean up the subscriber and let the container/Spring complete the error lifecycle.

`onCompletion`, `onTimeout`, and `onError` on the emitter are useful for releasing connections/subscribers, tasks, database listeners, and queues. Across multiple nodes, termination and deployment restarts are normal; use client-side auto-reconnect.

## 4. Where Does Buffering Happen and Why Can It Block Every Beat?

### 4.1. Independent Buffers

~~~text
Spring code (send/flush)
  │
  ▼
Spring HTTP message converter / SseEmitter writer
  │
  ▼
Servlet response / container output buffer
  │
  ▼
OS TCP buffers
  │
  ▼
Nginx proxy_buffering / gzip / proxy_cache
  │
  ▼
Ingress, LB, CDN, WAF, CDN transforms
  │
  ▼
Browser network buffering / EventSource parser
  │
  ▼
JavaScript event listener
~~~

The server might call `send` right on schedule every 10 seconds, while the browser only sees events when Nginx fills a buffer or the server closes the response. Or the client might receive bytes on the network on time, yet `EventSource` does not fire the callback because **there is no blank line ending the event**. Or the browser receives a comment heartbeat, yet JavaScript **sees no callback because comments are ignored by design**.

Therefore, verify **HTTP headers, byte arrival timing, framing content, and the client parser**—not just a server log saying `send() completed`.

### 4.2. Nginx `proxy_buffering`

A standard Nginx reverse proxy can buffer upstream responses. The directive:

~~~nginx
proxy_buffering off;
~~~

tells the proxy to pass bytes to the client synchronously as they arrive, instead of reading ahead and accumulating them into internal buffers/temp files. Per Nginx docs, `proxy_buffering` is **on by default** in typical setups; the effective setting can be overridden in `http`/`server`/`location`, or via `X-Accel-Buffering` unless ignored.

**Disable buffering only on routes requiring streaming**, such as `/events` or `/ndjson`, rather than globally across all pages and cacheable assets to preserve proxy efficiency.

### 4.3. `X-Accel-Buffering: no` Is a Response Header, Not a Request Header

Spring Boot can return:

~~~http
X-Accel-Buffering: no
~~~

on streaming endpoints. Nginx can **honor** this header and disable buffering for that specific response, provided configuration does not set `proxy_ignore_headers X-Accel-Buffering`. This is an **Nginx-specific mechanism**, not an HTTP standard that every CDN/LB must obey.

By default, Nginx **does not necessarily forward `X-Accel-*` headers to the browser**, even after applying the behavior itself. Therefore, not seeing `X-Accel-Buffering` in browser DevTools **does not prove** Nginx ignored it. To be certain, configure `proxy_buffering off` explicitly on the route and measure data flow through the public endpoint.

**Do not** confuse `X-Accel-Buffering: no` with `proxy_request_buffering off`: the latter controls **the request body from client to upstream**, not buffered SSE responses.

### 4.4. Gzip/Compression and Caching

Compression can introduce buffering before flushing tiny payloads; proxies/CDNs can transform responses or terminate streams. For SSE:
- Prioritize keeping streaming responses free from proxy buffering/transformation.
- `Cache-Control: no-cache, no-transform` signals not to transform content and to revalidate caches, yet **does not force every proxy to skip buffering**.
- `no-cache` **does not mean** `no-store`. For private data, consider `Cache-Control: private, no-store, no-transform` and disable `proxy_cache` on the route.
- Audit middleware performing compression, content transformation, or output wrapping in the JVM and reverse proxy. When needed, **disable gzip specifically on streaming routes**.
- Do not set an estimated `Content-Length` if the total stream length is unknown; HTTP/1.1 responses typically use chunked transfer encoding automatically. HTTP/2 **does not use** `Transfer-Encoding: chunked`, while SSE/heartbeat semantics remain unchanged.

`Transfer-Encoding: chunked` is **HTTP/1.1 framing**, not what makes clients parse SSE events; and gzip content encoding does not automatically guarantee buffering, though it can affect flushing and timing. Always observe actual wire bytes.

## 5. Proxy Timeouts: Reading the Direction and Meaning Correctly

| Parameter/Mechanism | Affected Path | Typical Meaning | Is It Total SSE Lifetime? |
| --- | --- | --- | --- |
| **Nginx `proxy_read_timeout`** | Nginx reading from Spring upstream | Maximum gap **between two read operations**; closed if upstream sends nothing | **No** |
| Nginx `proxy_connect_timeout` | Nginx connecting to upstream | Time allowed to establish connection to backend | No |
| Nginx `proxy_send_timeout` | Nginx sending request to upstream | Time between successive **request-write** operations | No |
| Nginx `send_timeout` | Nginx sending response to downstream client | Timeout between writes/progress sent to the client | Not total |
| Spring MVC `SseEmitter(timeoutMillis)` | Servlet async request | Emitter's own async lifecycle timeout | **Can bound total lifetime** |
| Spring Boot `spring.mvc.async.request-timeout` | MVC async | Default async request timeout if not overridden per emitter | Can bound lifetime |
| Tomcat HTTP keep-alive timeout | Socket idle between separate requests | Distinct from the lifetime of an **actively streaming response** | Not equivalent |
| Load balancer/CDN idle timeout | Specific network hop | May measure data/idle per direction and layer differently | Provider-dependent |
| Client `curl --max-time` | Entire curl invocation | Hard deadline set by client even while heartbeats flow | **Yes** |

For example, Nginx `proxy_read_timeout 75s` does not mean every stream dies at 75 seconds: if upstream sends bytes every 10 seconds, the inter-read timer keeps resetting. However, if the Spring side stalls for 80 seconds (blocked scheduler, stop-the-world pause, downstream backpressure...), the proxy can close it. **Increasing `proxy_read_timeout`** helps, but does not replace reliable heartbeats.

If streams still cut off sharply at 60/120/300 seconds, look for an **absolute timeout in the app/proxy/LB**, rather than just tweaking the heartbeat interval. With `new SseEmitter(300_000L)`, the emitter itself has a 5-minute lifetime; heartbeats do not make it infinite.

## 6. Runnable Spring Boot Project: SSE Heartbeat and Line-by-Line NDJSON

The example uses Java 17+, Maven, Spring MVC, and Spring Boot **3.5.16**. Goals:
- `GET /events` returns `text/event-stream`, emits an initial event and a comment heartbeat every 10 seconds, with cleanup callbacks;
- `GET /ndjson` returns `application/x-ndjson`, writes 3 JSON records spaced ~1 second apart, flushing each line;
- configures an MVC async executor to avoid relying on a development default unsuitable for blocking writes under load;
- verifies the difference with `curl -N` and through Nginx.

**This is a controlled lab, not a production fan-out implementation for tens of thousands of clients.** Sequential `@Scheduled` loops and blocking `SseEmitter.send` calls can be stalled by slow clients; scaling requires bounded queues, backpressure, authorization, and resource management.

### 6.1. Directory Structure

~~~text
stream-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/streamdemo/
    │   ├── StreamDemoApplication.java
    │   ├── StreamController.java
    │   └── MvcAsyncConfig.java
    └── resources/application.properties
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>stream-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
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

### 6.3. `src/main/java/com/example/streamdemo/StreamDemoApplication.java`

~~~java
package com.example.streamdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication
public class StreamDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamDemoApplication.class, args);
    }
}
~~~

`@EnableScheduling` enables the `@Scheduled` method in the controller. This project omits a database, Redis, WebSocket, and Spring Security to focus on HTTP streams, heartbeats, and buffering.

### 6.4. `src/main/java/com/example/streamdemo/StreamController.java`

~~~java
package com.example.streamdemo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class StreamController {
    private final Set<SseEmitter> clients = ConcurrentHashMap.newKeySet();
    private final AtomicLong nextId = new AtomicLong();

    @GetMapping(path = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<SseEmitter> events() throws IOException {
        // 5 minutes: maximum emitter lifetime in the lab.
        SseEmitter emitter = new SseEmitter(300_000L);

        clients.add(emitter);
        emitter.onCompletion(() -> clients.remove(emitter));
        emitter.onTimeout(() -> clients.remove(emitter));
        emitter.onError(error -> clients.remove(emitter));

        // SseEmitter supports sending before MVC finishes returning from the handler.
        emitter.send(SseEmitter.event()
                .name("ready")
                .id(Long.toString(nextId.incrementAndGet()))
                .reconnectTime(3000L)
                .data("connected"));

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .header(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .body(emitter);
    }

    @Scheduled(fixedDelay = 10_000L)
    public void heartbeat() {
        for (SseEmitter emitter : clients) {
            try {
                // SSE comment: browser EventSource skips data callbacks.
                emitter.send(SseEmitter.event().comment("heartbeat"));
            } catch (IOException | IllegalStateException ex) {
                // Cleanup; on IOException, container/Spring handles the async error.
                clients.remove(emitter);
            }
        }
    }

    @GetMapping(path = "/ndjson", produces = "application/x-ndjson")
    public ResponseEntity<StreamingResponseBody> ndjson() {
        StreamingResponseBody body = out -> {
            for (int i = 1; i <= 3; i++) {
                String line = "{\"seq\":" + i + ",\"type\":\"tick\"}\n";
                out.write(line.getBytes(StandardCharsets.UTF_8));
                out.flush();

                if (i < 3) {
                    try {
                        Thread.sleep(1000L);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        throw new IOException("Interrupted while streaming",
                                interrupted);
                    }
                }
            }
        };

        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("application/x-ndjson"))
                .header(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .body(body);
    }
}
~~~

**How the code works:**
- `Set<SseEmitter>` tracks currently connected subscribers within **a single JVM process**. A concurrent set is appropriate because the controller, scheduler, and callbacks run on different threads.
- `AtomicLong` issues event IDs in-process only. After a restart or across multiple replicas, IDs can repeat; these are **not durable resume IDs**.
- `onCompletion`, `onTimeout`, and `onError` remove the subscriber so objects are not leaked.
- `SseEmitter(300_000L)` sets the async response timeout; after 5 minutes the stream may close. EventSource will reconnect if the client is still active and server policy allows.
- `@Scheduled(fixedDelay=10_000L)` sends comments to clients on a scheduler; with many clients or a slow scheduler, actual heartbeats are **not an exact 10,000 ms clock**.
- On `IOException` when writing to a disconnected client, Spring MVC docs recommend letting the Servlet container/Spring dispatch the async error. The code removes the subscriber and **does not** call `emitter.completeWithError(ex)` for that IOException.
- NDJSON emits 3 records, each a complete JSON object plus `\n`. `out.flush()` pushes buffered content from Java's output stream; it **does not guarantee** every proxy along the path forwards bytes immediately.
- `Thread.sleep(1000L)` is purely for observing lines in the demo, **not a production pattern**. With thousands of streams, avoid holding blocking threads indefinitely.

### 6.5. `src/main/java/com/example/streamdemo/MvcAsyncConfig.java`

~~~java
package com.example.streamdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcAsyncConfig {

    @Bean
    ThreadPoolTaskExecutor mvcStreamExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mvc-stream-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(64);
        executor.initialize();
        return executor;
    }

    @Bean
    WebMvcConfigurer mvcAsyncConfigurer(
            ThreadPoolTaskExecutor mvcStreamExecutor) {
        return new WebMvcConfigurer() {
            @Override
            public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
                configurer.setTaskExecutor(mvcStreamExecutor);
            }
        };
    }
}
~~~

Spring Framework notes that the default executor for MVC asynchronous blocking writes is **not suitable for production under load**. The example above configures a bounded thread pool, though 4/16/64 are **illustrative values**; production requires load testing to size pools/queues and handle rejections. `SseEmitter` broadcasts inside `@Scheduled` can still block the scheduler when a client reads slowly; configuring the MVC async executor **does not automatically fix that drawback**.

### 6.6. `src/main/resources/application.properties`

~~~properties
server.port=8080
spring.application.name=stream-demo

# Default timeout for MVC async without an explicit emitter override.
# SseEmitter(300_000L) still has its own 5-minute timeout.
spring.mvc.async.request-timeout=6m
~~~

`spring.mvc.async.request-timeout` is an **MVC asynchronous request lifetime** property, not an Nginx idle timeout or TCP keepalive. In the example, `SseEmitter` sets its own constructor timeout. Do not tweak unrelated HTTP thread/connection timeouts expecting heartbeats to start working.

### 6.7. Running from Project Root

Requires Java 17+ and Maven:

~~~bash
java -version
mvn spring-boot:run
~~~

Once Spring Boot opens port 8080, use another terminal.

#### Testing SSE with `curl -N`

~~~bash
curl -i -N http://localhost:8080/events
~~~

`-N`/`--no-buffer` disables **curl's** output buffering. Output includes headers (due to `-i`) and the SSE body. At the start of the stream you should see fields like:

~~~text
id:1
event:ready
retry:3000
data:connected

:heartbeat

:heartbeat

~~~

**Do not hardcode expectations about the exact order of `id`/`event`/`retry`/`data` lines when using the builder; order/spacing may be formatted by Spring depending on call order.** The output shown is the **SSE frame shape**, not exact byte-for-byte stdout. After the initial event, comments appear roughly every 10 seconds (subject to scheduler jitter). `curl -N` **prints comments** because it outputs raw bytes; JavaScript `EventSource` **has no** message callback for comments.

Limit client session duration for testing:

~~~bash
curl -i -N --max-time 27 http://localhost:8080/events
~~~

The command can exit with curl code **28** caused by `--max-time` after ~27 seconds: **this is not a server 5xx error**. If no heartbeat arrives during those 27 seconds, inspect scheduling, proxies, and output flushing.

#### Testing NDJSON

~~~bash
curl -i -N http://localhost:8080/ndjson
~~~

After headers, the body arrives line by line:

~~~text
{"seq":1,"type":"tick"}
{"seq":2,"type":"tick"}
{"seq":3,"type":"tick"}
~~~

Lines are spaced ~1 second apart in the lab project. `Content-Type` is `application/x-ndjson`; a browser `EventSource` will not interpret this as SSE. The endpoint completes after ~2 seconds, whereas SSE remains open until timeout or disconnect.

#### Comparing Buffered vs. Unbuffered Client Output

~~~bash
# Print response body with curl no-buffer to see each frame as received.
curl -N -sS http://localhost:8080/events

# Inspect headers and connection details (never pass -k to skip TLS outside a lab).
curl -v -N http://localhost:8080/events
~~~

If using PowerShell where `curl` is an alias for `Invoke-WebRequest`, invoke `curl.exe`. On Windows, stdout/console rendering and line endings may look different, while the underlying SSE framing protocol stays the same.

### 6.8. Testing EventSource in the Browser

An illustrative same-origin HTML/JavaScript snippet:

~~~html
<script>
  const stream = new EventSource("/events");

  stream.addEventListener("ready", event => {
    console.log("SSE ready:", event.data, event.lastEventId);
  });

  stream.onerror = () => {
    console.warn("SSE may reconnect automatically");
  };

  // Release the connection when the stream is no longer needed:
  window.addEventListener("beforeunload", () => stream.close());
</script>
~~~

In the browser, an event with `event: ready` **does not** enter default `onmessage`; register `addEventListener("ready", ...)` as above. `: heartbeat` lines **do not invoke callbacks**, so you only see one log entry on connect and possibly reconnects after timeout—that **does not mean the server stopped sending heartbeats**. Inspect the Network tab or use `curl` to verify.

Because the project has no static HTML file yet, this snippet is **illustrative** for embedding in a same-origin page or running in the browser DevTools console on `http://localhost:8080`. If opened from a different origin, handle CORS/SameSite/cookies and authentication; do not treat this snippet as guaranteed to work cross-origin without configuration.

## 7. Nginx for SSE/NDJSON: Verifiable Configuration

Assume Nginx sits in front of Spring Boot at `127.0.0.1:8080`, and the real public website uses `https://app.example.test` with TLS terminated at the proxy. This is an **illustrative server block snippet**, not a complete configuration for certificates, DNS, HSTS, or security.

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location = /events {
        proxy_pass http://127.0.0.1:8080;

        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Crucial: stream incrementally instead of buffering the response.
        proxy_buffering off;
        proxy_cache off;
        gzip off;

        # Must exceed heartbeat interval + jitter.
        proxy_read_timeout 75s;

        # Guard against slow clients while sending the response.
        send_timeout 75s;
    }

    location = /ndjson {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;
        proxy_cache off;
        gzip off;
        proxy_read_timeout 75s;
        send_timeout 75s;
    }
}
~~~

**How to read this configuration:**
- `proxy_buffering off` stops Nginx from buffering responses before forwarding, letting chunks pass through promptly.
- `proxy_read_timeout 75s` is the timeout while Nginx waits for **the next bytes from Spring**; the example's 10-second heartbeat is well below 75 seconds.
- `proxy_cache off` prevents caching a real-time endpoint as a static response.
- `gzip off` inside the route removes one layer that can buffer/transform data; you do not have to disable gzip site-wide.
- `proxy_http_version 1.1` is set **explicitly** to avoid depending on Nginx version defaults (default upstream HTTP version has varied across releases). `Connection ""` strips unwanted hop-by-hop headers when proxying to upstream.
- `send_timeout` governs **Nginx writing the response to the downstream client** and does not replace `proxy_read_timeout`.
- Even if public clients talk HTTP/2 to Nginx, Nginx can talk HTTP/1.1 to Spring Boot; the two hops are independent. HTTP/2 **does not** use HTTP/1.1 chunked transfer coding.
- `proxy_pass` has no path suffix in the example, so it forwards `/events` and `/ndjson` verbatim. With context-path rewrites, verify the effective upstream URL.

If the backend already emits `X-Accel-Buffering: no` like the lab code, Nginx can use that header to turn off buffering for that response, yet specifying `proxy_buffering off` on the route makes the policy explicit. **Not all CDNs, API gateways, or service meshes honor `X-Accel-Buffering`**; apply equivalent policies at those hops too.

### 7.1. Checking Nginx Syntax and Reloading

In an environment where you manage Nginx:

~~~bash
nginx -t
# After syntax is OK, reload via the appropriate service manager.
sudo nginx -s reload
~~~

Only reload once sure you are targeting the right server block/certificates without disrupting other infrastructure. In Docker/Kubernetes, follow your formal rollout process. Crucially: test the endpoint **through the proxy's public URL** after reloading; testing `localhost:8080` directly does not prove Nginx/CDN stopped buffering.

### 7.2. Observing the Stream Through the Proxy

~~~bash
curl -i -N https://app.example.test/events
curl -i -N https://app.example.test/ndjson
~~~

The domain is an example with no real DNS/certificate. On your system, substitute your real public/ingress domain. Compare direct backend results against results through the proxy:
- Are status 200 and `Content-Type` right?
- Does the initial event reach the client immediately?
- Do heartbeat comments appear on the 10-second cadence?
- Do bursts of multiple events pile up after 30–60 seconds?
- When silent past the limit, does Nginx/LB return 504/502 or close the connection?
- When the client closes, does the server clean up the subscriber?

**Absence of `X-Accel-Buffering` in the final response headers does not prove the proxy buffered**: Nginx may consume/hide that header. Rely on client byte timing and proxy logs.

## 8. Anti-Pattern Configurations and Why They Break

### 8.1. Leaving Buffering Enabled in Nginx

~~~nginx
location /events {
    proxy_pass http://127.0.0.1:8080;
    proxy_buffering on;
}
~~~

For an SSE response made of many small frames, Nginx can accumulate them before sending downstream. The browser sees neither `ready` nor progress until the buffer fills or the stream finishes; meanwhile the proxy keeps reading from upstream smoothly, so `proxy_read_timeout` never triggers yet **the client sees no data**.

Not every `proxy_buffering on` setup delays identically (buffer sizes, flushes, `X-Accel-Buffering`, and transports vary). Base conclusions on actual tests.

### 8.2. Mistaking `Connection: keep-alive` for a Heartbeat

~~~http
Connection: keep-alive
~~~

This header **is not an event body** and does not reset all idle timers. Moreover, HTTP/2 does not use the `Connection` header. For SSE, send actual periodic SSE comment/data frames and verify all hops forward them. Do not manually set hop-by-hop headers in Spring responses when the container/proxy manages connections.

### 8.3. Calling Java `send` Without an Event Separator

Wrong:

~~~text
data: step 1
data: step 2
~~~

Without a **blank line**, the browser may not dispatch the event yet. Right:

~~~text
data: step 1

data: step 2

~~~

Two events are separated by a blank line, not just a single newline. Using Spring `SseEmitter.event()` / WebFlux `ServerSentEvent` lets the formatter handle framing accurately compared to manual String concatenation.

### 8.4. Using `application/json` for a Live EventSource

If the server returns `Content-Type: application/json` with a JSON object/array body, browser EventSource rejects it as not being an event stream. For SSE, set `text/event-stream` with proper framing. For JSON Lines, use a `fetch` + Stream reader client and an NDJSON parser.

### 8.5. Disabling Response Caching While Forgetting Proxy Buffering

~~~http
Cache-Control: no-cache
~~~

This header does not instruct Nginx to turn off `proxy_buffering`. Caching and buffering are **two different concepts**:
- **Caching** retains a response to serve future requests.
- **Buffering** accumulates data from **the in-progress request** before forwarding it.

`proxy_cache off` and `proxy_buffering off` serve different purposes. Also account for compression and downstream layers.

### 8.6. Setting Every Timeout to Infinity

This hides failures, leaves orphaned connections, holds file descriptors/heap, and hampers cleanup. Better:
- identify timeout points/thresholds per hop;
- set heartbeats with safety margin;
- declare finite timeouts/clear renewal semantics;
- implement reconnect/backoff, client caps, and resource cleanup;
- track metrics distinguishing clean disconnects from infrastructure errors.

## 9. Reconnect and Last-Event-ID: Heartbeats Do Not Replace Message Durability

Browser EventSource automatically reconnects when an SSE connection closes under suitable conditions. The server can send `id: 123` and `retry: 3000`; on reconnect, the browser can send:

~~~http
GET /events HTTP/1.1
Accept: text/event-stream
Last-Event-ID: 123
~~~

**Yet EventSource sending `Last-Event-ID` does not mean Spring Boot automatically replays lost events.** The application must maintain a log/queue with stable IDs, verify stream access permissions, and replay events after the client-supplied ID if no data may be lost.

In the lab project, IDs come from an in-JVM `AtomicLong`, reset on restart, and are unsynchronized across replicas. Therefore, the endpoint **only demonstrates event streaming + heartbeats** and **does not** promise exactly-once delivery, durable resume, replay, or multi-instance consistency.

A production design can:
1. Assign sequentially ordered IDs per stream/topic and persist events into Kafka, Redis Streams, or a database with defined retention.
2. Authenticate the client and verify it is authorized to subscribe to the requested topic/event IDs.
3. When a request includes `Last-Event-ID`, read events after that ID if still within retention.
4. If the ID is too old or unknown, return a fresh snapshot/starting point per app contract rather than silently pretending replay occurred.
5. For event processing with side effects, clients must handle duplicates/idempotency; SSE + reconnect does not guarantee exactly-once.

A `: heartbeat` needs no event ID since it carries no business data. If the server sends heartbeats as **named events**, decide whether to attach IDs according to the replay policy (avoid letting heartbeats jump past unreceived business IDs).

## 10. WebFlux: ServerSentEvent and Reactive Backpressure

Spring WebFlux supports SSE via `Flux<ServerSentEvent<T>>` or `Flux<T>` with `produces = MediaType.TEXT_EVENT_STREAM_VALUE`. Do not use Servlet `SseEmitter` directly inside a Reactor Netty application. An **illustrative standalone endpoint snippet** (not part of section 6's MVC project; requires `spring-boot-starter-webflux`, Reactor imports, and `@RestController`):

~~~java
@GetMapping(path = "/reactive/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    Flux<ServerSentEvent<String>> data =
        Flux.interval(Duration.ofSeconds(5))
            .map(n -> ServerSentEvent.<String>builder()
                .id(Long.toString(n))
                .event("tick")
                .data("tick-" + n)
                .build());

    Flux<ServerSentEvent<String>> heartbeat =
        Flux.interval(Duration.ofSeconds(10))
            .map(n -> ServerSentEvent.<String>builder()
                .comment("heartbeat")
                .build());

    return Flux.merge(data, heartbeat);
}
~~~

- `ServerSentEvent.builder().comment(...)` produces an SSE comment-only frame.
- `Flux.interval` generates timer events and `Flux.merge` combines the data and heartbeat streams; **it is not an event storage/replay system**.
- Spring WebFlux uses non-blocking HTTP I/O, yet **that does not eliminate buffering in Nginx/CDNs**. Proper `text/event-stream` and proxy configurations are still required.
- Reactive `Flux` must still handle slow clients, subscriber counts, backpressure, cancellation, and memory bounds. `Flux.interval` does not automatically ensure emission only when the client can consume.
- Reactor Netty has its own timeout/keepalive settings; do not use `spring.mvc.async.request-timeout` to configure WebFlux as if it were Servlet MVC.

**When both starters are present:** If a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot normally prefers the MVC/Servlet application type. Having `WebClient` or `Flux` in a project does not prove the HTTP server runs WebFlux; check the actual application type and embedded runtime.

### 10.1. NDJSON in WebFlux

With an endpoint returning `Flux<MyRecord>` and `produces = "application/x-ndjson"`, the framework can serialize each object as JSON lines via supported codecs. This behaves differently from returning `Mono<List<MyRecord>>` as standard `application/json`. When using `Flux<DataBuffer>` manually, remember to release pooled buffers per API contracts to avoid memory leaks; if you only need JSON records, prefer codecs over manual buffer handling.

## 11. WebSocket and Long Polling: Do Not Copy SSE Heartbeats

### 11.1. WebSocket

Once HTTP upgrades to WebSocket (or negotiates via supported HTTP/2 mechanisms), traffic is no longer `text/event-stream`; it travels as **WebSocket frames**. Maintain connections with Ping/Pong control frames or application-protocol heartbeats per your implementation; **never** send `": heartbeat\n\n"` expecting the client to treat it as a WebSocket Ping.

WebSocket fits bidirectional chat or low-latency interaction. SSE fits server → browser push using HTTP GET, easy curl debugging, and EventSource auto-reconnect. Both require separate resource controls, security, idle timeouts, and proxy/ingress configuration.

Nginx proxying WebSocket must handle Upgrade/Connection headers per Nginx documentation—**do not copy** SSE's `proxy_set_header Connection ""` config into a WebSocket block and break the handshake. Conversely, SSE **needs no Upgrade** and does not return 101 Switching Protocols.

### 11.2. Long Polling

Long polling holds a request until an event arrives or a timeout expires, then returns **one complete response** (usually JSON) and the client opens a new request. It does not require sending in-body comments/heartbeats. If a load balancer enforces an absolute idle cutoff, choose a poll timeout **shorter than** the cutoff and reissue the request rather than keeping an SSE stream open forever.

With long polling, never inject SSE heartbeat comments into a pending `application/json` response; that corrupts JSON. Return `204 No Content` or an empty success payload per contract on poll timeout so the client polls again.

## 12. Impact of HTTP/1.1 and HTTP/2

An HTTP/1.1 streaming response may use **chunked transfer encoding** when length is unknown, yet `Transfer-Encoding: chunked` is **not** part of the SSE protocol and does not ensure each chunk aligns with an SSE event. HTTP/2 splits payloads into **DATA frames** on a stream and multiplexes multiple streams over one TCP connection; it **does not** use HTTP/1.1 chunked encoding.

Browser SSE over HTTP/1.1 can hit browser per-origin concurrent connection limits; over HTTP/2, concurrent streams depend on SETTINGS negotiated by client/server/proxy. Do not rely on a hardcoded default in your design: measure with real browsers and configurations, especially with multiple tabs and dashboards.

A reverse proxy can speak **HTTP/2 to the browser** while speaking **HTTP/1.1 to Spring Boot**; those are two independent hops. Proper proxy-to-upstream configuration does not force the client hop to use the same protocol. The core issue remains stream framing and unbuffered forwarding, not merely enabling HTTP/2.

## 13. Security and Resource Limits for Long-Lived Connections

### 13.1. Authentication and Authorization for Streams

An SSE connection is a long-lived **HTTP GET**. It still needs authentication, authorization, tenant/topic isolation, and rate limiting:
- Never allow anonymous subscriptions to private events just because the endpoint uses GET.
- Browser native `EventSource` lacks a standard API for arbitrary custom `Authorization` request headers; same-origin apps commonly use cookies/sessions, or a carefully designed short-lived single-use ticket policy. **Never put long-lived JWTs/secrets in query strings** because they leak via URL logs, referrers, and history.
- If cross-origin with cookies, configure CORS with specific allowed origins, credentials, and proper `SameSite`/`Secure`; evaluate the Origin/CSRF threat model. CORS **does not replace authorization**.
- Never route user A's data into user B's stream; bind the subscriber registry to user/tenant/topic after authorization.
- Never log raw event bodies containing PII/secrets; restrict log retention and access.
- Ensure the GET stream performs no unsafe state-changing actions just to open the connection.

### 13.2. Client Limits and Backpressure

Every long-lived connection consumes resources: a socket/file descriptor, buffers, subscriber state memory, request context, async executor capacity, proxy connection slots, send/flush CPU, and downstream bandwidth. If fan-out loops sequentially across 10,000 subscribers, a single slow client can block the scheduler long enough to delay heartbeats for everyone else.

Production requires:
- capping concurrent subscribers **per user/IP/tenant/node**;
- bounded queues and a backpressure/drop policy for slow consumers;
- grouping/snapshots, asynchronous broadcast, or an appropriate reactive design;
- sending heartbeats independently or with strict deadlines so a global sender isn't held hostage by one client;
- reliable cleanup on completion/timeout/error/cancellation and app shutdown;
- monitoring active connections, messages, bytes, send latency, queue depth, dropped events, client disconnects, and proxy 499/502/504s;
- scaling across load balancers and external event brokers rather than holding clients solely in one JVM when cross-node fan-out is needed;
- preventing memory leaks from stale emitters after client disconnects.

Using `ConcurrentHashMap.newKeySet` only keeps **references** to active emitters inside one JVM. It is not a durable subscription store. Do not rely on it to pin reconnects to the same replica; if replay is required, persist state/offsets outside the app.

### 13.3. Caching Headers for Private Data

For sensitive events, consider:

~~~http
Cache-Control: private, no-store, no-transform
Content-Type: text/event-stream
~~~

This is policy-illustrative only; `private`/`no-store` governs HTTP caching semantics and does not replace access control, TLS, or response buffering control. Proxy `proxy_cache off` on the route must also be set properly. Manage `Vary: Origin` if the API varies CORS responses by Origin so shared caches do not mis-serve responses.

### 13.4. TLS, HSTS, and Internal Networks

SSE over HTTPS uses the same TLS transport as any other HTTP request. If a proxy terminates HTTPS, the backend may use internal HTTP per policy, but that hop must be secured inside the infrastructure. Never mistake `X-Forwarded-Proto: https` as proof the backend hop itself is encrypted. With a CDN/ingress, check TLS, proxy idle timeouts, header forwarding, caching, and authentication at every hop.

## 14. Diagnosing by Symptom

| Symptom | Likely Cause | How to Check and Fix |
| --- | --- | --- |
| `EventSource` reports invalid MIME type | Actual response is `application/json`, an HTML login page, or a proxy error page | Run `curl -i -N` to inspect actual status, `Content-Type`, and body |
| Curl sees an event, browser does not invoke `onmessage` | Event has `event: ready` instead of default `message`; or it is comment-only | Register `addEventListener("ready")`; comments do not dispatch |
| Browser receives nothing until server closes response | Proxy/compression/client buffer | Compare direct vs. public URL; `proxy_buffering off`, `curl -N` |
| Server logs send every 10s, client gets batches every 60s | Proxy coalescing bytes, gzip, or client buffering | Test per hop, turn off route buffering, check `X-Accel-Buffering` |
| Stream closes right after 5 minutes despite steady heartbeats | `SseEmitter(300_000L)` async total timeout | Tune lifecycle and reconnects, not just `proxy_read_timeout` |
| Nginx closes after ~60s of silence | `proxy_read_timeout` between upstream reads | Send heartbeats shorter than threshold, adjust timeout |
| Client closes stream yet server keeps subscriber forever | Missing cleanup callbacks or undetected disconnect | Wire `onCompletion`/`onTimeout`/`onError`; periodic writes; resource bounds |
| `curl` does not display data promptly | Curl stdout buffering | Use `curl -N` or `--no-buffer` |
| `curl --max-time` exits with code 28 | Client-imposed total deadline | Check exit code and pick a suitable test timeout |
| `X-Accel-Buffering` missing in browser headers | Nginx may consume/strip `X-Accel-*` | Measure real byte timing and configure `proxy_buffering` |
| 504 at proxy | Silent upstream, timeout, slow/stuck app | Check `proxy_read_timeout`, app logs, thread dumps, and scheduler |
| 502 while proxying | Backend dropped, errored, restarted on deploy, bad upstream | Check upstream logs, TLS/hop health, and status |
| CORS error though direct curl succeeds | Browser Origin/preflight/cookie policy mismatch | Inspect Network tab, `allowedOrigins`/credentials, `SecurityFilterChain` |
| NDJSON client parse error | Missing newline, injected SSE comment, or partial JSON | Each line must be complete JSON, framed as NDJSON |
| Heartbeat treated as business message | Server sent `data: ping` instead of `: ping` | Use comment-only SSE or filter heartbeat event explicitly |
| Reconnect loses several events | No replay store or `Last-Event-ID` ignored | Durable IDs, replay semantics, idempotent clients |
| Multiple SSE tabs stall over HTTP/1.1 | Per-origin browser connection limit/scheduling | Measure per-origin connections; consider HTTP/2 or multiplexing app topics |
| One slow client starves heartbeats for all clients | Blocking scheduler/send fan-out | Bounded queues, isolate slow clients, backpressure |
| HTTP/2 enabled yet still buffering | Proxy buffering is independent of HTTP version | Disable buffering on the right route/hop and verify |
| Response has `Transfer-Encoding: chunked` yet arrives late | Chunked is framing, not a flush guarantee | Measure per hop, Spring flush, proxy buffering |
| SSE suddenly returns 401/403 after redirect/login | Expired auth cookie/session or chain policy | Inspect status/response Content-Type, session auth, and EventSource `onerror` |

### 14.1. Quick Debug Runbook

1. Record the **public URL**, DNS/proxy hops, HTTP versions, status, Content-Type, Cache-Control, and disconnect timestamp.
2. Test **the backend directly** with `curl -N -i http://.../events` and time intervals between comments.
3. Test **through the proxy/CDN** with `curl -N -i https://.../events` at the same time; if direct is fast and public is batched, inspect intermediary buffering/transforms.
4. Check `proxy_buffering`, `X-Accel-Buffering`, `proxy_cache`, gzip, and read/send timeouts. Watch for `proxy_ignore_headers` disabling `X-Accel` headers.
5. Verify exact SSE blank lines, `data/event/id/retry`, UTF-8 encoding, and whether the client uses EventSource or an NDJSON parser.
6. Distinguish the emitter's **absolute async timeout** from Nginx/LB **idle timeouts**. Heartbeats must reach the hop **before** the idle cutoff.
7. Inspect the scheduler/executor: is it blocked or slow? Record last-send/last-receive timestamps, queue depth, and downstream send latency.
8. Verify cleanup callbacks on client disconnect: are any emitters or sockets leaking?
9. Test under production-like load, multiple tabs, network interruptions, backgrounded browsers, proxy restarts, rolling deployments, and client reconnects.
10. When zero event loss is required, test `Last-Event-ID` and durable log replay—never mistake heartbeats for message delivery guarantees.

## 15. Solution Decision Table

| Need | Preferred Choice | Why |
| --- | --- | --- |
| Browser only needs server-pushed notifications/progress | **SSE** `text/event-stream` | EventSource + comment heartbeats + auto-reconnect |
| Browser must send and receive continuously over one connection | **WebSocket** | Full duplex; Ping/Pong, no SSE framing |
| CLI/service needs to read JSON records line by line | **NDJSON** `application/x-ndjson` | Easy to stream and parse incrementally, custom reconnect |
| Returning a precomputed JSON array | `application/json` | No reason to hold a long-lived connection |
| Backend emits rare events and LB dislikes long streams | Long polling | Finite responses followed by client re-polling |
| Large file downloads or seekable video | File streaming/HTTP Range, not SSE | Byte-range media framing differs from SSE |
| Token-by-token text output (AI streaming) | SSE or HTTP streaming/NDJSON with clear contract | Requires flushing, framing, unbuffered proxy, and cancellation |
| Huge client counts needing non-blocking I/O | Evaluate WebFlux/event brokers and supporting gateways | Backpressure/concurrency, not just swapping Content-Type |

No single technique prevents every failure. Choose based on data direction, reconnect/replay semantics, client capabilities, proxy behavior, load, authentication, and cost. Choosing SSE is a **protocol choice**, while heartbeats and proxy buffering are **end-to-end operational concerns**.

## 16. Exercises and Answers

1. Which MIME type does browser EventSource require? Can you serve `application/json` and expect `message` events?
2. What does a valid SSE heartbeat comment look like? Why doesn't the browser call `onmessage` for it?
3. How does `data: ping` differ from `: ping`?
4. Why is a **blank line** required between SSE events?
5. If Spring sends a heartbeat every 10 seconds while Nginx buffers the response, will a downstream load balancer necessarily see that cadence?
6. How does `proxy_buffering off` differ from `proxy_cache off`?
7. Who sends `X-Accel-Buffering: no` and who understands it? Is it an HTTP standard honored by every CDN?
8. What does `proxy_request_buffering off` do, and does it fix delayed SSE responses?
9. Is `proxy_read_timeout 75s` 75 seconds for the entire response or between two upstream reads?
10. Does `SseEmitter(300_000L)` extend itself indefinitely if heartbeats run every 10 seconds?
11. Is `spring.mvc.async.request-timeout` the Nginx idle timeout?
12. Does `curl -N` fix buffering on the server/proxy or only in curl's stdout?
13. Is `Transfer-Encoding: chunked` used in HTTP/2, and does it guarantee timely event delivery?
14. How must records be delimited for `Content-Type: application/x-ndjson`?
15. When EventSource reconnects with `Last-Event-ID`, does Spring Boot automatically replay data from the database?
16. Why shouldn't you put a long-lived JWT in URL query parameters to authenticate SSE?
17. What do `SseEmitter`'s `onCompletion`/`onTimeout`/`onError` help accomplish?
18. Why might heartbeat fan-out for many clients on a blocking scheduler drift off cadence?
19. How does WebFlux `Flux<ServerSentEvent<String>>` differ from Servlet `SseEmitter`?
20. When the browser receives `event: ready` yet the `onmessage` handler stays silent, how do you fix the client?
21. Is it valid for an HTTPS proxy to speak HTTP/2 to the browser and HTTP/1.1 to the backend?
22. Why is setting every timeout to infinity usually an unsustainable fix?

**Suggested answers:** (1) `text/event-stream`, no. (2) `: heartbeat\n\n`; comments are ignored per protocol. (3) Real data event vs. no-op comment. (4) A blank line terminates an event frame. (5) No, bytes may be held in the proxy. (6) Buffering an in-flight response vs. caching for later requests. (7) Backend response header typically for Nginx, not a universal CDN standard. (8) Buffers request bodies, does not fix responses. (9) Between two reads from upstream. (10) No, it still has an async lifetime. (11) No. (12) Only curl's stdout. (13) No; does not guarantee timing. (14) Each valid JSON line terminated with LF. (15) No, requires a replay store/logic. (16) Query strings easily leak into logs/exposure. (17) Cleanup subscribers/resources. (18) Slow clients block the sender, causing scheduling jitter. (19) Reactive non-blocking pipeline vs. Servlet async API; both still depend on proxies. (20) Use `addEventListener("ready", ...)`. (21) Yes, hops are independent. (22) Leaks, resource cost, masked failures, and no substitute for a reconnect policy.

## 17. Standards and Official References

- WHATWG HTML Living Standard, **Server-Sent Events / Event Stream Format**: https://html.spec.whatwg.org/multipage/server-sent-events.html — `text/event-stream`, `event/data/id/retry`, comments, reconnect, and `Last-Event-ID`.
- Spring Framework 6.2, **Spring MVC Asynchronous Requests**, SSE/HTTP streaming/Disconnects sections: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html — `SseEmitter`, `ResponseBodyEmitter`, `StreamingResponseBody`, heartbeats, and async executor.
- Spring Framework 6.2, **SseEmitter javadoc**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html — `SseEventBuilder`, `comment`, `id`, `retry`.
- Spring Framework, **WebFlux annotated controller return types**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html — `Flux<ServerSentEvent>` and streaming media types.
- Spring Framework, **WebFlux Streaming**: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html — heartbeats, disconnect detection, DataBuffer.
- Spring Boot 3.5, **Common application properties**: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html — `spring.mvc.async.request-timeout`.
- Nginx official documentation, **ngx_http_proxy_module**: https://nginx.org/en/docs/http/ngx_http_proxy_module.html — `proxy_buffering`, `X-Accel-Buffering`, `proxy_read_timeout`, `proxy_cache`, `proxy_http_version`, `proxy_request_buffering`.
- Nginx official documentation, **ngx_http_core_module**: https://nginx.org/en/docs/http/ngx_http_core_module.html — `send_timeout`.
- MDN, **Using Server-Sent Events**: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events — EventSource browser API, SSE parsing, and server side.
- RFC 9110, **HTTP Semantics**: https://www.rfc-editor.org/rfc/rfc9110.html — caching/semantics/content representation; alongside HTTP caching standards for `Cache-Control`.
