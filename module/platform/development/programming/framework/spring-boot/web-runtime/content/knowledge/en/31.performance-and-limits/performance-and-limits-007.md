# Impact of JSON Serialization, Compression, and Logging on Per-Request Cost

> **Module:** Spring Boot - web-runtime · **Topic:** Performance and Limits. An HTTP request costs more than controller or database time. When returning JSON, the server must also build an object graph, convert objects into bytes, optionally compress the response, write logs/metrics/traces, and push bytes over the network. This lesson analyzes **CPU, allocation/GC, latency, throughput, bandwidth, and memory costs** across three stages—**JSON serialization, HTTP compression, and logging**—with empirical measurements, optimization criteria, and **Spring Boot 4.1.2 / Java 17+** code. Examples use **Spring MVC/Tomcat, Jackson 3, SLF4J/Logback, Actuator/Micrometer**, and explain corresponding points for WebFlux.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Trace the response path from controller through **`HttpMessageConverter`/Jackson**, HTTP server compression, sockets, and proxies to the client, identifying which stages fall inside request latency.
2. Explain why an endpoint returning 200 with a fast database query can still be slow or overloaded due to **JSON serialization**, byte arrays/buffers, GZIP compression, or logging.
3. Distinguish heap object-graph size, uncompressed UTF-8 JSON bytes, compressed wire bytes, and log record bytes.
4. Understand the **Spring Boot 4.x** change: **Jackson 3** is the default mapper, auto-configuring **`tools.jackson.databind.json.JsonMapper`**; do not copy Boot 3.x's `com.fasterxml.jackson.databind.ObjectMapper` defaults blindly into Boot 4 code.
5. Use `server.compression.enabled`, `server.compression.min-response-size`, and `server.compression.mime-types` to test compression impact, understanding `Accept-Encoding`/`Content-Encoding`, CPU cost, and small/large payload trade-offs.
6. Use logging levels, **SLF4J parameterized logging**, log content caps, structured logging, and async appenders properly without logging raw bodies or tokens.
7. Build a runnable Spring Boot 4.1.2 project with controlled JSON response sizes and measure four compression/logging variants via cURL, Actuator, and profilers.
8. Avoid misleading measurements: `System.nanoTime()` inside a controller **does not measure serialization after the method returns**, a single `curl` is not a benchmark, and compression may be skipped if the client does not request it or MIME/size conditions fail.
9. Establish per-request cost budgets, p95/p99 SLOs, bytes/response, request rate, CPU/request, and log volume—optimizing from evidence rather than disabling all logs or enabling compression unconditionally.

## 2. What Resources Does a Spring Boot Request Consume?

Typical Spring MVC REST API path:

~~~text
HTTP request arrives
   |
   v
Tomcat connector / request threads
   |
   +-- Servlet filters, Spring Security, observation
   |
   v
DispatcherServlet -> @RestController
   |
   +-- calls service/database/cache
   +-- builds object graph/DTO
   +-- writes application logs (if any)
   |
   v
HttpMessageConverter
   |
   +-- Jackson 3: Java objects -> JSON UTF-8 bytes
   +-- may allocate buffers/objects
   |
   v
Servlet response / HTTP compression (when eligible)
   |
   +-- GZIP/deflate uses CPU and buffers
   |
   v
socket/TLS/TCP -> proxy -> client
   |
   +-- client decompresses and parses JSON
   |
   v
HTTP response completes / observation metrics
~~~

Conceptual model for analyzing **a single request**:

~~~text
T_total ≈ T_queue + T_request_read + T_decode + T_business
        + T_json_encode + T_compress + T_output_wait
        + T_other_filters + T_logging_critical_path

CPU_per_request ≈ CPU_parse + CPU_business + CPU_json
                + CPU_compression + CPU_log_formatting
                + CPU_TLS + CPU_framework

Memory_pressure ≈ object_graph + JSON_buffers + gzip_buffers
                + log_queue + framework_buffers + in_flight_requests
~~~

Stages **can overlap** during streaming, async I/O, or HTTP/2; this is a budgeting diagram, **not an exact measurement formula** for summing independent counters. `T_output_wait` can include backpressure/socket writes or blocked threads; low CPU does not prove a response is cheap if the network or receiver is slow.

### 2.1. One Request Has Multiple Sizes

Suppose a service returns 5,000 records:

| Concept | Example | What Pays the Cost? |
| --- | --- | --- |
| Java object graph | 5,000 records, `String`s, `List`s | Heap, allocations, GC |
| UTF-8 JSON | 1.2 MiB uncompressed (illustrative) | Encoder, buffers, HTTP write |
| GZIP response | 140 KiB if highly repetitive (illustrative) | Compression CPU; lower network egress |
| Log event | 1 summary line or 5,000 per-item lines | Formatting CPU, queues, stdout/file, log backend |
| Client decode | GZIP decompression, JSON parsing | Client-side CPU/heap |

Sizes in this table are **illustrative scenarios only**, not outputs from running the lesson's code. Compression ratio depends on character distribution, repetition, size, headers, algorithm, compression level, and library. Random/Base64 binary data compresses poorly, whereas schema-heavy repetitive JSON compresses heavily.

### 2.2. Amdahl's Law: Optimizing the Wrong Stage Yields Little Gain

If the database accounts for 95% of request time and JSON accounts for 2%, doubling serialization speed cuts overall request time by only about **1%** ideally if nothing else changes. Conversely, with multi-MiB responses and DB cache hits, JSON/gzip can dominate CPU. Always **profile and A/B test** first.

Nor is the question simply "is compression better?": GZIP cuts transfer time on constrained bandwidth while increasing server CPU, which can lower requests/second when CPU saturates. **Single-client latency** and **cluster throughput** can move in opposite directions.

## 3. JSON Serialization: What Happens After the Controller Returns an Object

A Spring REST controller:

~~~java
@GetMapping("/api/orders")
public List<OrderDto> orders() {
    return orderService.listOrders();
}
~~~

This is a **fragment**: `OrderDto` and `orderService` are supplied by the application. The controller returns **Java objects**; the response is not JSON yet at the `return` statement. Spring MVC picks a matching `HttpMessageConverter` (typically the Jackson JSON converter) to serialize the object graph into JSON.

### 3.1. Jackson 3 Is the Default in Spring Boot 4.1

Spring Boot 4.x integrates **Jackson 3** by default via its JSON starter; when compatible Jackson libraries are on the classpath, Boot auto-configures a `JsonMapper` bean. Primary package used in Jackson 3 examples:

~~~java
// Fragment used when direct access to the mapper is genuinely needed.
import tools.jackson.databind.json.JsonMapper;
~~~

In Spring Boot 3.x, many guides referenced `com.fasterxml.jackson.databind.ObjectMapper` (Jackson 2). Spring Boot 4.x retains transitional Jackson 2 support, **marked deprecated**, and you should not mix APIs/versions by default. To return JSON from a controller, you normally **do not instantiate `new JsonMapper`**: rely on the auto-configured converter so Boot manages modules and defaults.

### 3.2. Sources of Serialization CPU Cost

Jackson turns an object graph into a byte stream through serializers, incurring costs from:

1. Reading fields/getters/records via prepared metadata/serializers.
2. Traversing collections/maps, null values, nested objects, and generic types.
3. Formatting numbers, timestamps, enums, and specialized types.
4. Escaping special characters, quoting JSON, and encoding Unicode to UTF-8.
5. Executing custom serializers, filters, mixins, polymorphism, or reflection.
6. Writing bytes to buffers/response output; allocating buffers depending on mapper/converter and output path.
7. If code manually calls `writeValueAsString` before returning, creating an extra intermediate `String` before HTTP conversion writes it again.

Returning 100 records behaves very differently from returning 100,000 records, even with identical business/DB logic. Do not measure this solely inside the controller method, because JSON encoding often runs **after the method returns**.

### 3.3. Object Graphs Impact Performance Before Serialization Even Starts

A JPA entity with 10 lazy relationships can trigger N+1 queries as the serializer invokes getters (depending on session/lazy-loading config) or fail on closed sessions/cycles. Returning entities directly creates risks:

- Accidentally exposing fields never meant for the API.
- Lazy associations firing extra DB queries and allocations.
- Cyclic references causing infinite recursion or complex annotations.
- Unpredictable serialization time scaling with graph depth.
- Coupling API response stability to database entity mappings.

Prefer response-shaped DTOs/records with **bounded size, depth, and element counts**. Use cursor/offset pagination for large lists, project only needed columns/fields, batch queries, and avoid deep object graphs.

### 3.4. Before / After: Oversized Payloads

Avoid:

~~~java
// Fragment illustrating an anti-pattern.
@GetMapping("/api/all-orders")
public List<OrderEntity> allOrders() {
    return repository.findAll(); // may return unbounded rows/entity graphs
}
~~~

Prefer:

~~~java
// Fragment illustration; requires real service/cursor DTOs in app code.
@GetMapping("/api/orders")
public OrderPage page(@RequestParam(defaultValue = "100") int limit) {
    int safeLimit = Math.max(1, Math.min(limit, 500));
    return orderService.fetchPage(safeLimit);
}
~~~

The goal is to **bound response data before Jackson sees it**. Smaller JSON simultaneously lowers **DB reads, allocations, compressed bytes, network writes, client parsing, and log volume if payloads are logged**.

### 3.5. JSON Optimizations to Evaluate by Measurement

| Option | Potential Benefit | Risk / Trade-Off |
| --- | --- | --- |
| Small DTOs, pagination | Cuts object count, JSON bytes, query load | Changes API contract; requires cursors/links |
| Drop unused fields | Cuts encoding CPU and egress | Can break client compatibility |
| Reuse mapper/serializers | Avoids repeated setup/metadata cost | Thread-safety; never mutate mapper at runtime |
| Project only requested fields | Cuts allocations and nesting depth | Check field-level authorization |
| Stream serialization when appropriate | Lowers peak memory and time-to-first-byte | Error handling post-commit, backpressure, client semantics |
| Binary protocol for bulk transfer | Can reduce CPU/bytes | Added complexity, browser/tooling/contract impact |
| Cache JSON bytes at an appropriate layer | Avoids re-serializing identical representations | TTL/invalidation, auth, `Content-Encoding`/`Vary` |
| Custom serializers | Faster domain/format handling | Bug risk; verify with JMH/profiling |
| Disable pretty-printing on large APIs | Saves whitespace bytes | Compact JSON does not guarantee huge CPU savings |
| Reduce numeric precision per schema | Saves bytes and compute | Never silently truncate financial precision |

Never copy a "fast serialization trick" without profiling against your **real JDK, version, DTOs, and schemas**. Swapping mappers, enabling Afterburner, switching Jackson 2/3, or writing custom deserializers affects compatibility; verify JSON contracts with tests.

## 4. HTTP Compression: Fewer Bytes, Usually Higher CPU

Response compression runs **after producing the JSON/text representation**. It shrinks wire bytes and can lower end-to-end latency over constrained bandwidth or high RTT, at the cost of extra CPU and buffer memory.

### 4.1. Compression Conditions

Relevant exchange:

~~~http
GET /api/report?count=1000 HTTP/1.1
Host: localhost:8080
Accept-Encoding: gzip
~~~

The server only returns GZIP if content negotiation, MIME type, size, status, connector, and configuration all permit it. When compressed:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

Illustrative headers are **not guaranteed identical** across every container and proxy. `Content-Encoding: gzip` marks the body payload as gzip-encoded. `Content-Length`, if present, reflects compressed size, though responses may stream via chunked encoding or HTTP/2 without a known `Content-Length`.

If the client omits `Accept-Encoding: gzip`, the response normally arrives **uncompressed** even when `server.compression.enabled=true`. Small bodies, unlisted MIME types, pre-encoded responses, or proxy behavior can also bypass compression.

### 4.2. Spring Boot 4.1.2: Server Compression Configuration

~~~properties
server.compression.enabled=true
server.compression.min-response-size=2KB
server.compression.mime-types=application/json,text/plain,text/html,text/css,application/javascript
~~~

In Spring Boot 4.1, `server.compression.enabled` defaults to **false**; minimum response size defaults to around **2 KB**; and `application/json` is already in the default compressible MIME list. Setting `server.compression.mime-types` **replaces the whole default list**; to add MIME types while keeping defaults, check `server.compression.additional-mime-types`.

Response compression is performed by supporting embedded servers such as Tomcat, Jetty, or Reactor Netty. Do not mistake this property for automatic decompression of **incoming request bodies**; request decompression, proxies, and client request compression work separately.

**Threshold nuance:** Docs specify response/Content-Length thresholds; for streaming or unknown-length responses, connector behavior can vary. Always inspect actual `Content-Encoding` response headers rather than assuming from `server.compression.min-response-size`.

### 4.3. Why Should Small Responses Not Be Compressed?

Consider small JSON:

~~~json
{"ok":true}
~~~

GZIP adds headers, trailers, CRC, and deflate initialization overhead. On tiny responses, compressed output can be **larger or negligibly smaller**. Compressing everything wastes CPU, adds latency, and can inflate small responses.

On 500 KiB of repetitive-key JSON, GZIP shrinks wire size dramatically. On Base64-encoded pre-compressed blobs, ciphertext, or high-entropy strings, compression savings may be minimal.

### 4.4. Compression Levels and CPU

| Option | Typically Helpful When | Cost to Measure |
| --- | --- | --- |
| Uncompressed | Tight CPU limits, fast LAN, small bodies | Higher network bytes |
| Standard-level GZIP | Moderately large JSON/text over slower networks | Encode CPU, memory buffers, client decode |
| High compression level | Expensive egress, highly compressible payloads, low concurrency | Higher CPU, higher latency |
| Brotli/Zstd where stack/CDN supports | Better ratios on certain text/static assets | Negotiation, compatibility, CPU; Boot does not support every codec by default |
| Compress at CDN/proxy | Offloads app CPU, cacheable responses | TLS hops, caching, double compression, proxy config |
| Cache compressed representation | Eliminates repeated CPU work | Correct `Vary`/`ETag`/authorization/invalidation |

Never claim "Brotli is faster than gzip" or "gzip always saves CPU" universally. Compare codecs and levels on **real payloads** (text, JSON, random/binary) on target hardware and versions.

### 4.5. Impact on Caching, ETags, and Response Length

Compression produces distinct representations per `Accept-Encoding`. Caches and CDNs must honor `Vary: Accept-Encoding`, weak/strong ETag semantics, and never serve gzipped bytes to clients that did not accept them. For signed payloads or digests, verify whether signatures apply to compressed or uncompressed bytes.

**Avoid double compression:** if ingress/CDN already compresses, compressing again in the app rarely helps and can corrupt representations. Inspect headers at app, proxy, and client edge. Never compare a chunked response's wire size against raw JSON size and blame the compressor.

### 4.6. Compression Side Channels and Sensitive Data

Attacks like **BREACH** exploit compressed response lengths when responses mix secrets with attacker-controlled reflected input. For sensitive HTML/JSON combining secrets and reflected input, evaluate your threat model rather than enabling compression indiscriminately. Context-appropriate mitigations include separating secrets from reflected responses, CSRF/XSS defenses, padding, or disabling compression on sensitive routes; HTTPS alone does not eliminate compression-length side channels.

## 5. Logging: Every Request Can Generate More I/O Than Its Payload

Logging is often ignored when budgeting request cost. One call:

~~~java
log.info("Processed orderId={} in {} ms", orderId, durationMs);
~~~

triggers string formatting, encoder/JSON formatting, lock/queue contention, stdout or file I/O, log shipper/agent processing, network shipping to the log backend, and storage indexing. Logging **one line per item** on a 10,000-item response emits 10,000 log lines for **a single HTTP request**.

### 5.1. What Makes Logging Expensive?

| Step | Example | Cost / Risk |
| --- | --- | --- |
| Level check | Is DEBUG enabled? | Tiny per call, adds up in tight loops |
| Argument evaluation | Building Strings, reading object state | Allocations, or extra queries if calling expensive methods |
| Formatting/encoding | Pattern layout, structured JSON, exception stack traces | CPU, allocations |
| Appending | Console/file/socket | Locks, I/O, flushes, backpressure |
| Async queue | Log events waiting on writer thread | RAM, message drops, or blocking when full |
| Shipper/aggregator | Tailing stdout, parsing JSON, forwarding to backend | External CPU/egress/storage costs |
| Retention/indexing | Indexing structured fields | Backend cost and privacy exposure |
| MDC/tracing | Correlation IDs | Context propagation, scoping/cleanup |

Spring Boot starters default to **Logback**, writing to console without creating log files unless `logging.file.name/path` is set. Spring Boot also supports structured logging formats such as ECS, GELF, and Logstash.

### 5.2. Proper Logging: SLF4J Placeholders

~~~java
// RECOMMENDED: logger formats arguments only if the level is enabled.
log.debug("Request count={} kind={}", count, kind);
~~~

Avoid eager string concatenation when debug is off:

~~~java
// AVOID: allocates a new String even when DEBUG is disabled.
log.debug("Request count=" + count + " kind=" + kind);
~~~

Especially avoid:

~~~java
// DANGEROUS FOR PERFORMANCE AND PRIVACY:
// jsonMapper.writeValueAsString() runs BEFORE log.debug(),
// even when DEBUG is disabled.
log.debug("responseBody={}", jsonMapper.writeValueAsString(response));
~~~

If you genuinely need an expensive debug summary in development:

~~~java
if (log.isDebugEnabled()) {
    // Compute a safe summary only; never serialize raw PII or tokens.
    log.debug("response count={} status={}", responseCount, status);
}
~~~

These are **fragments** inside a class with an existing logger, variables, and mapper—not standalone Java sources. Remember SLF4J placeholders **do not defer evaluation of Java expressions passed as arguments**; guard expensive argument calls explicitly.

### 5.3. Never Log Full Request/Response Bodies

Dangerous data includes:

- `Authorization: Bearer ...`, cookies, session IDs, API keys.
- Passwords, refresh tokens, OTPs, payment details, emails/phone numbers.
- Query strings with PII, or full URLs containing secrets.
- Multipart/file contents, binary/Base64 blobs.
- Multi-MiB raw JSON or tens of thousands of records.
- Exception messages containing SQL, connection strings, or credentials.

Body logging both multiplies serialization/encoding cost and copies PII across stdout, log agents, ELK/log stores, and backups. Log **request/trace ID, URI template, status, outcome, item count, elapsed time**, and explicitly whitelisted safe fields. When emergency debugging demands more detail, use time-boxed enablement, sampling, redaction, size caps, and access approval.

### 5.4. Structured Logging Is Useful, Not Free

Boot 4 configuration:

~~~properties
logging.structured.format.console=logstash
~~~

Or:

~~~properties
logging.structured.format.console=ecs
~~~

Structured JSON logs are easy to parse and query by key, yet require formatting a separate JSON **log event** independent of the HTTP JSON response. Logging an entire 1 MiB response payload essentially serializes/escapes nearly the same data **twice** and pushes it down a second I/O pipeline.

Keep a compact, consistent log schema: `timestamp`, `level`, `logger`, `trace_id`, `route`, `status`, `elapsed_ms`, `result_count`. Do not dump entire payloads just because the log collector accepts JSON.

### 5.5. Synchronous vs Asynchronous Appenders

A synchronous console or file appender sits directly on the request critical path. If a stdout pipe, terminal, filesystem, or log agent stalls, request threads block or queues build up downstream.

An async appender moves I/O off the request thread, yet still must:

- Enqueue log events into a **bounded-capacity** queue.
- Format or snapshot context as required.
- Handle overload: **block**, **drop**, or fail per policy.
- Flush cleanly on shutdown for critical events.
- Never silently drop **audit, security, or financial logs** requiring durability.
- Monitor queue depth, dropped counts, and write errors.

**Illustrative** Logback `AsyncAppender` example; use in `logback-spring.xml` only if deliberately replacing Boot's default logging setup:

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <appender-ref ref="CONSOLE"/>
  </appender>

  <root level="INFO">
    <appender-ref ref="ASYNC"/>
  </root>
</configuration>
~~~

**Trade-off:** `neverBlock=false` can **block the producer** when the queue fills to avoid dropping logs; `neverBlock=true` drops logs when the buffer fills. `discardingThreshold=0` disables Logback's default threshold-based discarding, yet does not make the queue infinite or fix a slow underlying appender. Measure p99 latency, queue depth, and log loss before choosing. Replacing `logback-spring.xml` can drop Boot's built-in defaults unless re-included; this snippet is illustrative, not blanket advice to enable everywhere.

### 5.6. Access Logs and Application Logs Are Two Separate Paths

Tomcat access logging is controlled by `server.tomcat.accesslog.enabled`, defaulting to **false** in Boot 4. Per-request access logs help inspect statuses, bytes, and timings, while adding I/O and retention cost.

~~~properties
# Optional for lab/production once log security policies are in place.
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%a %s %D
~~~

This pattern omits raw URLs yet still records client IP (`%a`) and elapsed time (`%D`), so protect it under privacy policies. Default common patterns may include paths/queries depending on config. Access logs are distinct from Spring INFO/DEBUG application logs in format and retention. Avoid enabling verbose logs across gateway, app, and sidecar simultaneously while ignoring total log volume.

### 5.7. WebFlux / MDC

In WebFlux, Reactor continuations can hop across threads. Traditional `ThreadLocal` MDC does not automatically propagate across every reactive chain. Use Reactor `Context`, framework/version-appropriate context propagation, and official tracing hooks. Never copy request A's MDC into a mutable singleton for request B; that leaks user data across requests and adds overhead.

## 6. Interaction Among JSON, Compression, and Logging

Do not measure the three stages in isolation and assume gains add linearly.

| Scenario | JSON Encode | Compression | Logging | Likely Consequence |
| --- | --- | --- | --- | --- |
| Small JSON, no logs | Low | Off | Low | Network is rarely the bottleneck |
| Large, repetitive JSON | Higher | Big wire-byte savings | Low | Saves bandwidth at higher CPU cost |
| Large, high-entropy JSON | Higher | Minimal byte savings | Low | Pays CPU cost with little benefit |
| Large JSON + full body logging | JSON response + JSON log | Either | Very high | CPU, allocations, I/O, and log storage explode |
| 1 summary metadata log line | Unchanged | Optional | Controlled | Usually high operational value |
| Structured log per item | Response unchanged | Optional | Repeated JSON logs/events | Easily saturates stdout/log agent |
| WebFlux streaming | Chunk-by-chunk encoding | Transport-dependent | Context must stay accurate | Backpressure and flush behavior dominate |

### 6.1. Hardware Trade-Off Example

Suppose a server has a **4 CPU core-seconds/s** request budget (idealized) and each uncompressed request uses 8 ms of CPU. The CPU-only theoretical ceiling is:

~~~text
4 CPU-seconds/s / 0.008 CPU-seconds/request = 500 requests/s
~~~

If GZIP raises CPU cost to 12 ms/request, the theoretical CPU ceiling drops to:

~~~text
4 / 0.012 ≈ 333 requests/s
~~~

Conversely, if GZIP shrinks network egress enough to eliminate socket write waits or network saturation, **actual throughput** can improve despite higher CPU per request. These 8 ms and 12 ms numbers are **purely hypothetical budgeting examples**, not Spring Boot/Tomcat benchmarks.

### 6.2. In-Flight Requests Multiply Memory Footprint

Suppose one response holds a 1 MiB object graph, 0.5 MiB encoder buffers, and 0.5 MiB staging/proxy buffers (illustrative only). At 1,000 concurrent requests, potential memory hits several GiB **before heap fragmentation, connection pools, and framework overhead**. Reducing response sizes, streaming, bounding concurrency, and capping queues often matters far more than shaving a few microseconds off a serializer.

### 6.3. Caching Changes All Three Costs

Caching serialized JSON bytes for identical responses avoids rebuilding object graphs and re-serializing; CDNs/proxies can cut backend hits entirely. For authenticated/authorized data, partition cache keys strictly so user A's response is never served to user B. When compressing, caches must respect `Content-Encoding`/`Vary`, ETags, and invalidation. Caching does not remove logging cost if you still emit heavy logs on every cache hit.

## 7. Hands-On Project: Measuring JSON, Compression, and Logging in Spring Boot 4.1.2

The lab below isolates **response size** and **log line count** via bounded request parameters. It uses Java record DTOs, Spring Boot's default Jackson 3 converter, HTTP compression, and Micrometer metrics without embedding fake benchmarks inside the controller.

### 7.1. Directory Structure

~~~text
cost-per-request-lab/
  pom.xml
  src/main/java/com/example/costlab/
    CostPerRequestApplication.java
    CostController.java
  src/main/resources/
    application.properties
~~~

Requirements: **JDK 17+**, Maven, cURL. Run locally only—never expose load-test endpoints publicly. Measure actual figures on your own machine.

### 7.2. `pom.xml`

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
    <artifactId>cost-per-request-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
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

`spring-boot-starter-webmvc` is the Spring MVC/Tomcat starter in Boot 4.1.2. The Jackson 3 JSON converter comes from the Spring web starter's JSON dependencies and Boot auto-configuration. `spring-boot-starter-actuator` and the Micrometer Prometheus registry support measurement and are not required for JSON serialization or compression itself.

### 7.3. `CostPerRequestApplication.java`

~~~java
package com.example.costlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CostPerRequestApplication {
    public static void main(String[] args) {
        SpringApplication.run(CostPerRequestApplication.class, args);
    }
}
~~~

### 7.4. `CostController.java`

~~~java
package com.example.costlab;

import java.util.ArrayList;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class CostController {

    private static final Logger log =
            LoggerFactory.getLogger(CostController.class);

    private static final String REPETITIVE_DESCRIPTION =
            "Java Spring Boot JSON encoding and HTTP compression. ".repeat(8);

    public record Item(int id, String sku, String description, int quantity) {}

    public record Report(int count, String mode, List<Item> items) {}

    @GetMapping(value = "/report", produces = MediaType.APPLICATION_JSON_VALUE)
    public Report report(
            @RequestParam(defaultValue = "100") int count,
            @RequestParam(defaultValue = "repeated") String mode,
            @RequestParam(defaultValue = "false") boolean logEach) {

        if (count < 1 || count > 3000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "count must be 1..3000");
        }
        if (!mode.equals("repeated") && !mode.equals("varied")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "mode must be repeated or varied");
        }
        if (logEach && count > 50) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "logEach requires count <= 50");
        }

        List<Item> items = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            String description;
            if (mode.equals("repeated")) {
                description = REPETITIVE_DESCRIPTION;
            } else {
                // Deterministic per-index variation, NOT high-entropy random data;
                // avoid equating this with true "random".
                long code = 0x9E3779B97F4A7C15L * (i + 1L);
                description = "unique-" + i + "-"
                        + Long.toUnsignedString(code, 36);
            }

            items.add(new Item(i, "sku-" + i, description, (i % 7) + 1));

            // Used solely to observe per-item log cost at small counts.
            if (logEach) {
                log.info("lab item generated id={} mode={}", i, mode);
            }
        }

        log.info("report generated count={} mode={} logEach={}",
                count, mode, logEach);

        // Spring MVC/Jackson serializes AFTER this method returns.
        return new Report(count, mode, List.copyOf(items));
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Demo properties:

- With `mode=repeated`, long repeated descriptions yield a highly compressible body.
- With `mode=varied`, descriptions vary per index, creating a different pattern—**not true high-entropy random data**, so measure the exact ratio rather than guessing.
- `count=1..3000` caps object count so one request cannot allocate millions of records.
- `logEach=true` is restricted to `count<=50` to demonstrate per-record logging without flooding thousands of lines per request.
- INFO logs one summary line per request; when comparing INFO vs WARN, keep request parameters identical to isolate logging level impact.
- The controller returns a `Report` record rather than **hand-building JSON strings**. Spring MVC/Jackson performs JSON encoding after the controller returns.
- Never expose endpoints with user-selectable `mode`/`logEach` parameters on the public Internet; this is strictly for lab exploration.

### 7.5. `application.properties`

~~~properties
# Bind to loopback only in the lab.
server.address=127.0.0.1
server.port=8080

# Enable response compression; still subject to negotiation/MIME/size.
server.compression.enabled=true
server.compression.min-response-size=2KB

# Log app events at INFO to demonstrate volume.
logging.level.com.example.costlab=INFO

# Expose only required diagnostic endpoints on localhost.
management.endpoints.web.exposure.include=health,metrics,prometheus

# Disable Tomcat access logs by default in the lab to reduce noise.
server.tomcat.accesslog.enabled=false
~~~

Even with `server.compression.enabled=true`, compression only occurs when the client requests it and the response qualifies. Never assume from that property that **every response** is GZIP-compressed. Binding `server.address=127.0.0.1` and restricting Actuator exposure prevents leaking runtime telemetry from `/metrics`/`/prometheus`.

### 7.6. Running

~~~bash
mvn spring-boot:run
~~~

Call:

~~~bash
curl -i http://127.0.0.1:8080/api/ping

curl -i \
  "http://127.0.0.1:8080/api/report?count=2&mode=repeated"
~~~

`/api/ping` body:

~~~text
pong
~~~

`/api/report` body is JSON containing `count=2`, `mode="repeated"`, and `items` with two records holding `id`, `sku`, `description`, and `quantity`. Full JSON output is lengthy due to the repeated description; property order/formatting and headers depend on Jackson and the runtime. Do not hardcode literal expected JSON stdout without actually running Maven.

Test invalid inputs:

~~~bash
curl -i "http://127.0.0.1:8080/api/report?count=50000"
curl -i "http://127.0.0.1:8080/api/report?mode=unknown"
curl -i "http://127.0.0.1:8080/api/report?count=100&logEach=true"
~~~

Each returns HTTP **400** via handler validation instead of generating unbounded payloads or logs. Exact error JSON depends on Spring Boot's error handling—do not assume a fixed literal error body.

### 7.7. Measuring Uncompressed vs Compressed Wire Bytes

In a second terminal (Linux/macOS/WSL):

~~~bash
# Start the server from the project root first.

# DO NOT request gzip: save raw uncompressed body.
curl -sS \
  -D /tmp/raw.headers \
  -o /tmp/raw.body \
  -w "raw status=%{http_code} bytes=%{size_download} total=%{time_total}\n" \
  "http://127.0.0.1:8080/api/report?count=1000&mode=repeated"

# Request gzip and save raw wire bytes without auto-decompressing.
curl -sS \
  -H "Accept-Encoding: gzip" \
  -D /tmp/gzip.headers \
  -o /tmp/gzip.body \
  -w "gzip status=%{http_code} bytes=%{size_download} total=%{time_total}\n" \
  "http://127.0.0.1:8080/api/report?count=1000&mode=repeated"

# Verify whether the server ACTUALLY compressed the response.
grep -i "content-encoding" /tmp/gzip.headers
wc -c /tmp/raw.body /tmp/gzip.body
~~~

Only compare raw vs gzip byte counts once `/tmp/gzip.headers` shows `Content-Encoding: gzip`. If missing, check MIME types, `min-response-size`, negotiation, server connector, gateway, and response headers. cURL's `size_download` counts downloaded body bytes for that response; it does not equate to CPU, heap, or business latency.

If you pass `curl --compressed`, cURL automatically sends `Accept-Encoding` and **decompresses the body before writing output**; never treat `--compressed` body sizes as compressed wire sizes. To inspect decompressed JSON nicely:

~~~bash
curl --compressed -sS \
  "http://127.0.0.1:8080/api/report?count=10&mode=repeated"
~~~

On Windows PowerShell, use `curl.exe`; `/tmp` paths and `wc`/`grep` above target POSIX/WSL shells.

### 7.8. Comparing with a Small Body

~~~bash
curl -sS \
  -H "Accept-Encoding: gzip" \
  -D /tmp/small.headers \
  -o /tmp/small.body \
  "http://127.0.0.1:8080/api/report?count=1&mode=varied"

grep -i "content-encoding" /tmp/small.headers
~~~

With a 2 KB threshold, small responses are normally left uncompressed. Connectors can still have specific rules, so inspect actual response headers rather than promising identical outcomes across every machine.

### 7.9. Comparing Repetitive vs Varied JSON

~~~bash
curl -sS -H "Accept-Encoding: gzip" \
  -o /dev/null \
  -w "repeated=%{size_download}\n" \
  "http://127.0.0.1:8080/api/report?count=1000&mode=repeated"

curl -sS -H "Accept-Encoding: gzip" \
  -o /dev/null \
  -w "varied=%{size_download}\n" \
  "http://127.0.0.1:8080/api/report?count=1000&mode=varied"
~~~

Because the two payloads **have different uncompressed sizes**, never look solely at compressed download bytes and declare "entropy caused better/worse compression". To compute compression ratio, measure **both raw bytes and gzip bytes** for each payload shape, compute `compressed/raw`, and inspect CPU separately.

### 7.10. Testing Logging Levels Fairly

Run 1:

~~~bash
java -jar target/cost-per-request-lab-0.0.1-SNAPSHOT.jar \
  --logging.level.com.example.costlab=WARN \
  --server.compression.enabled=false
~~~

Run 2 (after stopping the first process):

~~~bash
java -jar target/cost-per-request-lab-0.0.1-SNAPSHOT.jar \
  --logging.level.com.example.costlab=INFO \
  --server.compression.enabled=false
~~~

Build the JAR first:

~~~bash
mvn package
~~~

Then send the exact same workload `count=20&logEach=true` to both runs:

~~~bash
curl -sS -o /dev/null \
  "http://127.0.0.1:8080/api/report?count=20&logEach=true"
~~~

Under `WARN`, the `log.info` calls are skipped; under `INFO`, the controller emits 21 log events for that request (20 per-item + 1 summary) upon completion. **That is the number of log calls executed by code**, not a guarantee that every record survives a lossy/sampled/retrying log collector. Measure elapsed time, CPU, and queue depth across many requests after warm-up at the same rate; one `curl` never tells overhead percentages.

### 7.11. Controlled A/B Matrix

| Trial | Compression | Log Level | Payload | Purpose |
| --- | --- | --- | --- | --- |
| A | Off | WARN | `repeated`, `count=1000` | Encode + network baseline with minimal app logs |
| B | On | WARN | `repeated`, `count=1000` | Isolate compression/network delta |
| C | Off | INFO | `repeated`, `count=1000` | Isolate one summary log/request |
| D | On | INFO | `repeated`, `count=1000` | Combined GZIP + logging impact |
| E | Off | WARN | `varied`, `count=1000` | Payload shape impact |
| F | On | WARN | `varied`, `count=1000` | Compression ratio/CPU on another shape |
| G | Off | INFO | `repeated`, `count=20`, `logEach=true` | Low-scale stress for per-item logging |
| H | Off | WARN | `repeated`, `count=20`, `logEach=true` | Control group with identical response, logging off |

Configure each variant via CLI properties and **restart the application** to change only one variable per run, unless you have controlled dynamic config. Keep JDK, heap, CPU quota, profile, GC, client/concurrency, proxy, response data, metrics settings, and warm-up request count identical.

In production-like benchmarks, run **multiple trials** and report median/p95/p99 and confidence intervals—never write unmeasured "x ms reduced by y%" claims as fact.

## 8. Java 17: Standalone Example Checking GZIP Bytes (Without Jackson)

To observe **raw bytes → GZIP bytes** without Spring or Maven, create `GzipSizeDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPOutputStream;

public class GzipSizeDemo {

    public static void main(String[] args) throws Exception {
        // Controlled ASCII JSON solely for this byte-size demo.
        // NEVER concatenate strings to build JSON from user data.
        String json = "{\"message\":\"" + "A".repeat(4096) + "\"}";
        byte[] raw = json.getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (GZIPOutputStream gzip = new GZIPOutputStream(out)) {
            gzip.write(raw);
        }
        byte[] compressed = out.toByteArray();

        System.out.println("raw bytes: " + raw.length);
        System.out.println("gzip smaller: " + (compressed.length < raw.length));
    }
}
~~~

Run:

~~~bash
javac --release 17 GzipSizeDemo.java
java GzipSizeDemo
~~~

Program stdout:

~~~text
raw bytes: 4110
gzip smaller: true
~~~

Byte math: this JSON contains 4,096 `A` characters (ASCII) plus 14 bytes for `{"message":"..."}`, totaling 4,110 UTF-8 bytes. Because the pattern repeats heavily, GZIP shrinks it below raw length. Exact **compressed byte counts** are not hardcoded because compression levels/JDK implementations can vary. This snippet also **does not** measure CPU, HTTP latency, or Jackson cost—it only verifies raw vs gzip size on a fixed payload.

With non-ASCII characters, `String.length()` no longer equals UTF-8 byte length. To compare real JSON API sizes, measure bytes after the serializer and/or on the real HTTP response.

## 9. Measuring Performance Properly: From Endpoints to Profilers

### 9.1. `http.server.requests` and Actuator

Spring Boot Actuator instruments Spring MVC/HTTP handlers with the logical meter `http.server.requests`. Enable:

~~~properties
management.endpoints.web.exposure.include=health,metrics,prometheus
~~~

After generating traffic:

~~~bash
curl -sS http://127.0.0.1:8080/actuator/metrics
curl -sS http://127.0.0.1:8080/actuator/metrics/http.server.requests
curl -sS http://127.0.0.1:8080/actuator/prometheus
~~~

`/actuator/metrics/http.server.requests` is for ad-hoc diagnostics, not production scraping. `/actuator/prometheus` serves Prometheus scrapes when the registry and endpoint are enabled. The HTTP timer tracks framework request elapsed time including most response processing, yet **does not split JSON vs GZIP vs logging**, and diverges under async I/O, proxy buffering, or slow clients. Breaking down stages requires targeted profiling or controlled benchmark instrumentation.

### 9.2. Suggested PromQL Queries

Per-route request rate:

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Mean duration (seconds):

~~~promql
sum by (uri) (rate(http_server_requests_seconds_sum[5m]))
/
clamp_min(sum by (uri) (rate(http_server_requests_seconds_count[5m])), 1e-9)
~~~

When histograms are configured and `_bucket` is exported:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Do not assume `_bucket` exists unless histograms are enabled. Likewise, never attach request IDs, user IDs, full URI queries, exact byte sizes, or arbitrary log text as metric labels: **cardinality explosion** will overload observability infrastructure itself.

### 9.3. CPU, GC, and Memory

Observe:

- Process CPU utilization/load and container CPU throttling.
- JVM heap used, allocation rate, GC pauses/time, humongous allocations.
- Thread pool active/queued requests, Tomcat busy threads.
- Response bytes (uncompressed/compressed), network egress Mbps.
- Log events/sec, bytes/sec, async log queue backlog, dropped logs.
- HTTP request rate, errors, p50/p95/p99 durations.
- Compression ratio by MIME type and body shape.
- Heap retained by object graphs, JSON buffers, and logging queues.

Spring Boot Actuator/metrics auto-configuration provides baseline JVM/process/log-event metrics, **not** every granular metric like "JSON encoder CPU per request" or "bytes sitting in async log queue". For per-stage breakdowns, use JFR/profilers or carefully bounded instrumentation.

### 9.4. JDK Flight Recorder

With Java 17 and a packaged JAR:

~~~bash
java -XX:StartFlightRecording=filename=cost.jfr,dumponexit=true \
  -jar target/cost-per-request-lab-0.0.1-SNAPSHOT.jar
~~~

This is an **example Java 17 command**; profiler/JFR settings, file write permissions, and environments vary. Open the recording in JDK Mission Control or a JFR viewer to inspect CPU samples, allocation hotspots, GC pauses, and blocked threads. Hotspots frequently appear in Jackson serializers, `Deflater`/GZIP, Logback encoders/appenders, or business logic.

For granular CPU flamegraphs and allocation profiles under load, use `async-profiler`, JFR, or JMH with compatible versions—never leave heavy production profiling running unmonitored for overhead or PII exposure. Remember a timer inside a controller method measures only **before `return`**, missing the HTTP converter afterward; never call it "JSON serialization time".

### 9.5. Microbenchmarking with JMH

When comparing serializers, DTOs, or schemas directly:

- Use **JMH** to benchmark Jackson serialization in isolation with proper warm-up, forks, and `Blackhole` consumption.
- Prepare input data outside the measured method, fixing size and shape.
- Keep JDK/JVM flags, CPU pinning if used, heap, and mapper configs identical.
- Measure both throughput and allocations (`-prof gc`) across diverse payload shapes.
- Contrast JVM serialization microbenchmarks against end-to-end HTTP load tests; one isolates a code path while the other covers network and framework behavior.
- Never write a raw `System.nanoTime()` loop and declare one framework 100× faster: JIT optimizations, dead-code elimination, caches, GC, and OS scheduling invalidate naive loops.

### 9.6. Load Generators and Test Environments

Tools like wrk, k6, Gatling, or hey measure RPS and latency percentiles. Ensure:

1. **The load generator does not saturate before the server.**
2. Concurrent users, connection reuse, and keep-alive match your scenario.
3. Server warm-up and cache pre-population match the target workload.
4. You test **multiple response sizes**, not just 1 KiB payloads.
5. You never use an interactive terminal stdout as a production log sink benchmark: terminal rendering speed can become the bottleneck.
6. Network profiles approximate production (RTT, bandwidth, proxies, TLS).
7. You test tail latency during bursts, GC, and stalled log agents.
8. You compare against baseline while changing **one variable** per round.
9. Results reflect steady-state intervals rather than the first cold request.
10. Error thresholds apply: HTTP 500s or timeouts invalidate a test even if raw RPS looks high.

## 10. Spring MVC vs WebFlux: Same Cost Categories, Different Execution

### 10.1. MVC / Servlet

- Controllers normally run on Servlet request threads; synchronous/blocking JSON conversion, logging, and I/O hold those threads.
- Jackson serializes the object graph into the response, allocating buffers; the embedded container compresses when eligible.
- If a log sink blocks on the request path, the request thread stalls; enough concurrent slow writes can saturate Tomcat threads.
- `server.compression.enabled` applies to embedded Tomcat/Jetty when supported; verify actual response headers.

### 10.2. WebFlux / Reactor Netty

- Reactive response writing runs in the Publisher pipeline; JSON encoding and compression still consume CPU and heap.
- **Reactive does not make JSON serialization free.** Encoding or logging huge payloads on the event loop still steals CPU and delays unrelated connections.
- Avoid `block()`, blocking file appenders, custom blocking logging I/O, or JDBC on Netty event loops; offload blocking work safely with bounded concurrency and queues.
- Reactor backpressure can throttle upstream demand in supporting pipelines, yet **does not automatically bound every hot producer or socket/proxy buffer**.
- When streaming `Flux<T>` JSON or SSE, account for element-by-element serialization, codec buffers, flushing, and slow clients. Stream compression can degrade time-to-first-byte and flushing behavior.
- Never treat `spring.codec.max-in-memory-size` as a general "total CPU/response byte ceiling"; it limits specific codec aggregation buffers rather than payload policies, client counts, or logging.

### 10.3. Never Mix User A's Logging Context Into User B

In Reactor, execution jumps across schedulers. Traditional MDC relies on `ThreadLocal`; maintain correlation via official Spring/Observation/tracing context propagation rather than storing mutable request metadata in shared singletons. Heavy logging on WebFlux event loops creates a shared bottleneck across many sessions.

## 11. Streaming, Pagination, and Response Buffering

For huge JSON payloads, reducing record counts is usually step one. Options include:

| Delivery Style | Benefits | Limitations |
| --- | --- | --- |
| Large `List<DTO>` | Simple code | High heap objects, JSON encode cost, latency, GC |
| Cursor / pagination | Bounds response size and DB rows | Client must coordinate multiple requests; consistency |
| NDJSON streaming | Record-by-record processing, continuous stream | Client must handle newline framing; proxy/compression flush |
| SSE streaming | Server push updates | Slow consumers, proxy buffering, event IDs/replay |
| Response body streaming | Lowers peak buffering when done right | Post-commit exceptions, backpressure/thread semantics |
| Binary download | Suited to large files | Different API semantics from JSON |
| Cached/precomputed JSON | Cuts repeated CPU work | Invalidation, auth, `Content-Encoding`/caching rules |

Spring MVC provides `StreamingResponseBody` for byte streaming, and WebFlux provides `Flux<DTO>` codecs. Never hand-assemble JSON arrays with an unbounded `StringBuilder` just to "skip Jackson"; escaping and encoding bugs are easy to introduce. When streaming, design for client cancellation, backpressure, unknown `Content-Length`, chunk boundaries, and post-commit errors.

### 11.1. Streaming Compression

With streamed responses, gzip/HTTP encoders may hold bytes to build compression blocks before flushing. Compression can worsen **time-to-first-byte or per-event latency** even while shrinking total wire bytes. Always test real-time SSE through your actual proxy with compression and buffering configured; never assume compressing `text/event-stream` is always beneficial.

### 11.2. Cache Keys and Security

When caching serialized responses, partition keys by auth/tenant, locale, field projections, API version, and `Content-Encoding`. Never serve User A's cached JSON to User B. With signed payloads or digests, compression alters raw bytes, so validate the right representation and ETag semantics. Never allow public CDNs to cache sensitive data unless explicitly permitted.

## 12. Optimizing Logging While Preserving Incident Investigation

### 12.1. Choosing the Right Log Level

- **ERROR:** actionable failures; do not log the exact same stack trace 100 times across every layer.
- **WARN:** abnormal but recoverable states, with rate limiting or sampling during floods.
- **INFO:** meaningful business state transitions or request summaries; never log every element of a large list.
- **DEBUG/TRACE:** enable temporarily, under strict scope and traffic bounds, without secrets.

A solid request summary:

~~~text
route=/api/report status=200 count=1000 duration_ms=34 trace_id=... 
~~~

This is an **illustrative format**, not literal demo stdout. Never put raw URLs with PII queries into metric labels or unbounded logs; use URI templates and redaction.

### 12.2. Logging Errors at the Right Layer

A DB timeout might pass through repository, service, controller, exception handler, gateway, and collector. If every layer prints a stack trace, one failure generates megabytes of logs. Designate one owning layer to log the full stack trace while other layers propagate context via exception causes and trace IDs, while ensuring critical audit and security events remain reliably recorded.

### 12.3. Rate-Limiting and Sampling Logs

When an error repeats thousands of times per second:

- Sample (e.g., 1 in 100) for non-critical diagnostics.
- Count aggregates via metrics by route/status while emitting detailed logs only for sampled occurrences.
- Rate-limit / token-bucket by finite keys, never unbounded IDs.
- Keep mandatory audit events **unsampled and undropped**; if the main log pipeline is lossy, route audits through a durable channel.
- Alert on dropped diagnostic logs and full async queues.

**Log sampling differs from trace/metric sampling.** Typically keep aggregate metrics 100% accurate and sample expensive diagnostic details; never drop business errors just to boost benchmark scores.

### 12.4. File vs Stdout

In containers/Kubernetes, apps usually write structured JSON logs to stdout for a collector, yet stdout still has pipes, buffers, and backpressure. If the log agent falls behind, appenders can block or queue. File appenders add filesystem writes, rotation, disk quotas, and cleanup. Pick log paths based on platform SLOs and retention—never treat a logger call as "zero I/O".

## 13. Security and Privacy in Measurements

Never log raw request/response bodies during production benchmarks without stripping PII. Responses mixing secrets and reflected user input under GZIP require side-channel evaluation; TLS alone does not prevent compression-ratio leakage.

In test labs:

- Use synthetic data—never real users, orders, or tokens.
- Bind ports to loopback and restrict Actuator endpoints.
- Never publish endpoints letting arbitrary callers specify item counts or `logEach`.
- Enforce limits on total request size, max count, concurrency, and timeouts.
- Never enable tracing/debug/access logs capturing `Authorization` headers or cookies.
- Never put secrets in URLs/query strings where proxies and access logs record them.
- On inbound JSON deserialization, bound nesting depth, document length, and schema; CPU/memory costs exist on input too.
- Restrict access and retention on JFR/profiler artifacts, since allocations and stack traces can expose sensitive state.

## 14. Per-Request Budget Formulas and Trade-Off Decisions

### 14.1. Request CPU Budget

Suppose a service has 8 vCPUs and targets 70% sustained CPU, giving ~5.6 CPU-seconds per second (simplified model). At 1,000 RPS, the average CPU budget per request is roughly:

~~~text
CPU_budget_per_request ≈ 5.6 / 1000 = 0.0056 CPU-second
                       = 5.6 ms CPU/request
~~~

If JSON encoding + GZIP + logging already burn 4 ms CPU/request, very little headroom remains for business logic, DB work, TLS, and framework overhead. Container CPU shares/throttling and multithreading can shift real behavior from this model; never treat 8 vCPUs as a guarantee of 8 full CPU-seconds/s.

### 14.2. Network Budget

Suppose each uncompressed response is 1 MiB: 1,000 RPS demands roughly 1,000 MiB/s of payload before TLS/TCP overhead. Compressing to 100 KiB slashes egress, while forcing the compressor to keep up at that rate. The right trade-off depends on NIC bandwidth, egress billing, CPU, RAM, payload shape, RTT, and client decoding. Never extrapolate compression ratios for real traffic from a hyper-repetitive synthetic JSON sample.

### 14.3. Log Budget

If each request emits 10 log events averaging 1 KiB at 1,000 RPS:

~~~text
10 events/request × 1 KiB/event × 1,000 requests/s
= 10,000 KiB/s ≈ 9.77 MiB/s logs
~~~

That log stream alone is ~9.77 MiB/s before indexing or replication, or **864,000 MiB/day** (~844 GiB/day) sustained prior to compression/retention. Use sampling, concise metadata summaries, or fewer log points to control cost without losing observability.

### 14.4. Viewing Request Cost Along Four Axes

| Axis | Question | Measurement Tool |
| --- | --- | --- |
| Latency | What are end-to-end p95/p99 and TTFB? | HTTP load tests, Micrometer timers |
| CPU | What is CPU/request and where are hotspots? | JFR, async-profiler, container CPU |
| Memory | Allocations/request, retained heap, GC pauses? | JFR allocations, JVM metrics |
| I/O | Raw/compressed response bytes, log bytes, egress cost? | cURL, network metrics, log collector |

Whenever optimizing one axis, re-check the other three. Enabling gzip cuts egress, yet pushing CPU from 50% to 95% can wreck p99 and trigger autoscaling; async logging lowers request latency, yet a full queue can drop logs or drive up memory pressure.

## 15. Common Problems and Remediation

| Symptom | Likely Cause | How to Check / Fix |
| --- | --- | --- |
| Controller finishes in ms, client waits seconds | JSON encoding, compression, or network after `return` | HTTP-level profiling, response size, JFR |
| Huge response despite fast DB query | Returning entity graphs or too many records | DTOs, pagination, projections |
| Enabled gzip yet no `Content-Encoding` header | Client omitted `Accept-Encoding`, MIME/size missed, proxy | Inspect headers via cURL, check compression config |
| Gzip barely shrinks bytes | Random/pre-compressed payload or tiny body | Measure compression ratio per payload shape |
| Gzip lowers egress yet RPS drops | Deflate CPU overhead saturating CPU | Profile CPU, adjust threshold/codec/level |
| Gzip hurts SSE latency | Server/proxy buffering before flushing | Test event delivery and streaming config |
| JSON logger is very expensive | Double serialization / logging full bodies / heavy structured logs | Log concise metadata, bound sampling |
| CPU high even with DEBUG disabled | Eager string concatenation or mapper calls inside arguments | Use placeholders and `isDebugEnabled` guards |
| Synchronous console logging stalls requests | Slow stdout pipe, log agent, or disk | Tune/sample or use async with explicit queue policy |
| Async log queue causes OOM or log loss | Oversized queue or full queue with `neverBlock=true` | Bound queue, add alerts, separate audit channel |
| 100,000 meter series created | Raw URIs or user IDs used as metric tags | Use route templates and bounded labels |
| GC pauses grow on large list responses | Large object graphs + byte arrays + log queues | Cap item counts, stream/paginate, profile allocations |
| Jackson 2 imports fail to compile in Boot 4 | Legacy package/mapper used | Switch to Jackson 3 `JsonMapper` and Boot 4 starters |
| Hand-built JSON response breaks escaping | Manual string concatenation | Return DTO/record for Jackson to serialize |
| `curl --compressed` file size misleads analysis | cURL auto-decompresses output | Save raw wire bytes and inspect headers |
| Every request logged by access, app, and proxy | Redundant multi-layer logging | Assign owners, retention, and sampling |
| Same exception logged multiple times | Every layer logs stack traces | Log once with trace correlation |
| Great microbenchmark, zero production gain | Different workload, JIT, network, concurrency | Pair JMH with end-to-end A/B tests |
| Compression breaks behind a proxy | Double compression or missing `Vary` | Inspect edge and backend headers |
| JFR doesn't highlight Jackson | Actual bottleneck is DB, network, or logs | Profile realistic load; compare CPU vs wall clock |
| Compressing responses containing secrets + reflected input | Side-channel risk | Threat model, route-specific compression policy |

## 16. Production Rollout Checklist

### JSON and Data

- [ ] DTOs/records shape responses, bounding item counts and object graph depth.
- [ ] Never expose JPA entities or lazy relationships directly without auditing.
- [ ] Avoid double JSON encoding (manual stringify followed by HTTP converter stringify).
- [ ] Serialization uses Jackson 3 and Boot's configured mapper for the target version.
- [ ] Verified JSON schema/ordering/precision tests across mapper/module changes.
- [ ] Bounded inbound JSON sizes, array lengths, nesting depth, and parser allocations.

### Compression and HTTP Responses

- [ ] Measured raw vs gzip bytes across real MIME types, body sizes, and shapes.
- [ ] Confirmed client sends `Accept-Encoding` and server actually emits `Content-Encoding`.
- [ ] Tuned `min-response-size` so CPU is not wasted compressing tiny JSON.
- [ ] Prevented double compression across app/proxy/CDN; verified cache `Vary`/`ETag`.
- [ ] Evaluated compression ratio against CPU/request, RPS, and p95/p99.
- [ ] Assessed streaming/SSE flush behavior and secret+reflected-input side channels.

### Logging

- [ ] Never log raw payloads, `Authorization`, cookies, PII, or tokens.
- [ ] Used parameterized logging and guarded expensive debug arguments.
- [ ] Configured appropriate log levels/sampling; never left TRACE enabled everywhere.
- [ ] Structured logs include only useful fields without re-serializing response bodies.
- [ ] Async logging uses bounded queues with explicit blocking/drop policies.
- [ ] Provisioned retention, rotation, collector capacity, and log backpressure handling.
- [ ] Verified MDC/Reactor Context propagation so user/trace IDs never bleed across requests.

### Performance and Observability

- [ ] Measured CPU, allocations/GC, network bytes, log volume, and p99 under identical workloads.
- [ ] Ran baseline + single-variable A/B matrices with warm-up and repeated trials.
- [ ] Tested high load, HTTP error paths, slow clients, proxies, and container CPU limits.
- [ ] Never mistook controller method timers for full serialization/compression time.
- [ ] Protected Actuator endpoints and kept metric labels low-cardinality.
- [ ] Established capacity budgets and SLOs: bytes/response, CPU/request, p99, egress, log bytes/s.
- [ ] Prepared a rollback plan in case enabling compression or structured logs degrades CPU or latency.

## 17. Self-Check Questions with Answers

**Question 1.** Why can a controller method return `List<DTO>` in 2 ms while request p99 takes 120 ms?

**Answer:** Post-return serialization, compression, socket/network waits, filters/logging, and queueing all consume time. A timer inside the controller does not span the full request lifecycle.

**Question 2.** Does Spring Boot 4.1 default to Jackson 2 `com.fasterxml.jackson.databind.ObjectMapper` or Jackson 3?

**Answer:** Jackson 3 is the default; Boot auto-configures Jackson 3's `JsonMapper` when compatible dependencies are present. Transitional Jackson 2 support is deprecated.

**Question 3.** Does `server.compression.enabled=true` guarantee every JSON response is compressed?

**Answer:** No. The client must send `Accept-Encoding` and the server checks MIME type, size threshold, connector rules, and headers. Verify actual `Content-Encoding`.

**Question 4.** When can gzip hurt throughput even while reducing wire bytes?

**Answer:** When compression CPU becomes the bottleneck—especially on poorly compressible payloads, small bodies, or high RPS. Compare CPU, RPS, p99, and egress together.

**Question 5.** Does `log.debug("payload={}", mapper.writeValueAsString(dto))` skip serialization when DEBUG is disabled?

**Answer:** No. Java evaluates method arguments before calling `log.debug()`, even when nothing gets written. Use an `isDebugEnabled()` guard—and generally avoid logging full bodies.

**Question 6.** Does an async log appender completely eliminate logging cost?

**Answer:** No. Formatting, queueing, memory, and I/O still exist; when the queue fills, it must block or drop events. Never use lossy async logging for mandatory audit records.

**Question 7.** Is swapping Jackson for another serializer always the best way to reduce JSON CPU?

**Answer:** No. Trimming fields/rows, using lean DTOs, fixing N+1 queries, and safe caching often eliminate far more CPU/bytes across multiple layers; swapping serializers carries compatibility risks and must be justified by profiling.

**Question 8.** Why can two JSON responses of equal raw size yield very different gzip ratios?

**Answer:** GZIP efficiency depends on repetition and entropy. Repetitive values compress tightly; random, binary, or pre-compressed data does not.

**Question 9.** Why must you never attach `userId` or full URLs to Micrometer `http.server.requests` tags during performance measurements?

**Answer:** Unbounded label values explode time-series cardinality and can leak sensitive data. Use URI templates, method/status, and bounded tags.

**Question 10.** If GZIP responses use fewer bytes yet p99 latency worsens, what should you do?

**Answer:** Measure compression CPU, network, queues, proxies, and response sizes; tune size thresholds/MIME lists/offloading or disable compression on endpoints where it hurts. Never conclude from a single request.

**Question 11.** Should you set `logging.level.root=ERROR` in production just to make benchmarks look faster?

**Answer:** Silencing most logs cripples incident diagnostics and can violate audit/security compliance. Choose policy-aligned log levels and sampling while preserving critical events.

**Question 12.** Does seeing `gzipSmaller=true` from the standalone JDK program prove Spring Boot responses will always be compressed?

**Answer:** No. It only tests GZIP on one highly compressible in-memory payload. HTTP negotiation, size thresholds, connectors, and streaming semantics decide whether an HTTP response gets `Content-Encoding`.

## 18. Official Documentation

- [Spring Boot — JSON Support (Jackson 3 default)](https://docs.spring.io/spring-boot/reference/features/json.html).
- [Spring Boot — Embedded Web Servers, Enable Response Compression](https://docs.spring.io/spring-boot/how-to/webserver.html).
- [Spring Boot — Common Application Properties, `server.compression.*`](https://docs.spring.io/spring-boot/appendix/application-properties/).
- [Spring Boot — Logging, Logback and Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html).
- [Spring Boot — Metrics and HTTP request observations](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot — Enabling Production-ready Features](https://docs.spring.io/spring-boot/reference/actuator/enabling.html).
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html).
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html).
- [Spring Framework — WebFlux Reactive Web](https://docs.spring.io/spring-framework/reference/web/webflux.html).
- [Micrometer — Concepts: Timers and Metrics](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).
- [Oracle — Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/).
- [OpenJDK — JMH](https://github.com/openjdk/jmh).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).

**Conclusion:** The cost of an HTTP request in Spring Boot extends well beyond the controller: **Jackson building JSON**, **compressors transforming bytes**, and **loggers emitting events** all consume CPU, allocations, latency, I/O, and infrastructure budget. Lean payloads, bounded DTOs/pagination, well-chosen compression thresholds, controlled summary logs, and representative benchmarks almost always beat compressing everything or logging full payloads. Measure **p95/p99, CPU/request, raw/compressed bytes, GC, and log bytes/s** together; an optimization only succeeds when it improves operational goals without sacrificing correctness, security, or diagnosability.