# Request Body Replayability, Uploads, and Streaming

When **Spring Cloud LoadBalancer** or an HTTP client tries to resend a failed request, the question is not just whether to pick the old `ServiceInstance` or another replica. For requests with a body—especially **file uploads, multipart requests, or streaming**—the client must also answer: **can the exact payload be reproduced for the next attempt?**

A request may be network-retryable yet **unable to replay its body** because the data source was already consumed. Conversely, a client may replay the body completely and still cause **duplicate business writes**, because the server already processed the first send before the client timed out.

This lesson in the **Retries** chapter clarifies two independent properties:

- **Replayability:** can the body source be re-read or regenerated on every attempt?
- **Business-level idempotency:** does repeating the same operation trigger unintended side effects?

The goal is to know when you can safely retry with `RestClient`, `WebClient`, and OpenFeign; when you must refuse to retry; and when you should design **checkpoint-resumable uploads** instead of resending a huge stream from scratch.

## 1. Retrying a request is more than resending a URL

Suppose `order-service` sends a record to `media-service`:

~~~http
POST http://media-service/uploads
Content-Type: application/octet-stream
Idempotency-Key: operation-123

<binary body>
~~~

On the first attempt, LoadBalancer may pick `media-1`. After the server receives the entire body yet before the client receives a response, the connection drops. The client cannot know for sure whether the server persisted the data.

If a retry triggers:

1. Policy evaluates whether the error qualifies for retry.
2. Client/supplier decides whether to re-select the same `ServiceInstance` or pick another instance.
3. HTTP client constructs a new request.
4. **The request body source must supply the payload once more.**
5. The server must recognize the repeated operation if it wants to prevent duplicate writes.

~~~mermaid
sequenceDiagram
    participant App as Order Service
    participant LB as LoadBalancer
    participant Stream as Body source
    participant S1 as media-1
    participant S2 as media-2
    App->>LB: POST /uploads, operation-123
    LB-->>App: Select media-1
    App->>Stream: Read body attempt 1
    Stream-->>App: File bytes
    App->>S1: Send body attempt 1
    S1->>S1: May have saved file
    S1--xApp: Lost response / connection error
    Note over App: Retry? Can body be recreated?
    App->>LB: Select instance for attempt 2
    LB-->>App: May select media-2
    App->>Stream: Read body attempt 2
    Stream-->>App: Must re-supply bytes
    App->>S2: POST same operation-123
    Note over S1,S2: Backend needs shared idempotency state
~~~

Picking `media-2` does not magically undo what `media-1` processed. If both instances write to independent stores without coordination or shared idempotency, retrying onto another instance can duplicate or diverge data.

## 2. Distinguishing three conditions: retryable error, replayable body, and safe business semantics

| Question | Example answer | If unmet |
|---|---|---|
| **Is the error suitable for retry?** | Transient connection failure, select 502/503/504 per policy | Do not retry; return error or fallback |
| **Can the body be regenerated?** | Intact `byte[]`, re-openable file | Never replay an already-consumed stream |
| **Can business logic tolerate repetition?** | Version-checked PUT, server-enforced idempotency-key POST | Risk of duplicate orders/uploads/billing |

These three questions must be answered **independently**. For example, HTTP 503 may allow policy to *consider* a retry, yet does not prove the server left business logic untouched. A single-use `InputStream` can cause a retry to fail before the second request sends a full body, even when business semantics are relatively safe.

### HTTP method cannot replace business analysis

- `GET` typically carries no body and can be retried per policy, provided the actual endpoint produces no side effects.
- `PUT` is semantically idempotent per HTTP if implemented properly; conditional headers like ETag/version help prevent unintended overwrites.
- `DELETE` is semantically idempotent per HTTP, though the second response may differ (e.g., 404), and side effects like event emission may need deduplication.
- `POST` uploads or order creations are usually **unsafe to retry blindly** without idempotency keys, transactions, or duplicate-operation detection.
- `PATCH` may be non-idempotent depending on patch format; never assume safety automatically.

Depending on version and adapter, Spring Cloud LoadBalancer retries may restrict which operations are retried by default. **Do not enable retries for all methods merely because the body "can be re-read."**

## 3. Which body types are replayable?

Replayability depends on the **data source**, not merely whether the HTTP client supports retries.

| Body source | Typical replayability | Conditions and caveats |
|---|---|---|
| Immutable `String` / `byte[]` per operation | Usually easy to replay | Keep snapshot intact; never mutate array between attempts |
| JSON DTO | Can be re-serialized | Identical data/version/headers; avoid DTOs with per-call time/random fields |
| `FileSystemResource` | Can re-open file stream | File exists, contents unchanged, each attempt opens its own stream |
| `ByteArrayResource` | Can re-read bytes | Holds bytes in RAM; unsuitable for very large files |
| Already-opened `InputStream` | Usually **single-use** | Never assume `reset()` works; use a fresh-stream supplier |
| `InputStreamResource` wrapping a single-use stream | Should not be treated as replayable | Retry attempt may read an exhausted or closed stream |
| Multipart form with strings + stable files | Can be regenerated | **Every part** must be repeatable; check encoder and boundaries/headers |
| Cold `Flux` regenerating data per subscription | Possible if designed properly | Source must regenerate data; never reuse released `DataBuffer`s |
| Hot `Flux` / live queue / socket / stdin | Not replayable by default | Emitted items may no longer exist for a new subscriber |
| SSE or infinite event streams | Cannot simply "resend whole stream" | Requires offsets, event IDs, cursors, or resume protocols |

"Possible" in the table is not a universal guarantee across all HTTP transports. One client may pre-serialize and buffer the body; another may stream straight over sockets. Inspect your actual **request factory, encoder, subscription lifecycle, and retry implementation**.

### Replayability does not guarantee identical regenerated data

A file might re-open on attempt 2 after another job overwrote it, yielding different bytes from attempt 1. A DTO might also include fields auto-generated at serialization time. Therefore, **freeze an operation's payload** via snapshots, checksums, or immutable files.

## 4. Failure timing determines uncertainty

| Where did the failure occur? | Might the server have received the body? | Key retry considerations |
|---|---|---|
| No `ServiceInstance` selected | No HTTP sent to backend | Check discovery/policy; body likely untouched |
| Failed to borrow connection from pool | Usually not sent | Can retry after reducing contention if policy allows |
| TCP connect failed before sending | Usually no body sent | Can retry if another endpoint or network path works |
| Connection dropped mid-upload | **May have received partial body** | Source must replay; server must clean up partial uploads |
| HTTP 503 after server read full body | **Body received**, side effect uncertain | Idempotency and status verification are vital |
| Timeout while reading response | Processing may have completed | Never assume failure; consider querying status by operation ID |
| Client canceled mid-stream | May have received some chunks | Requires offsets/checkpoints or cancel/resume handling |

**A timeout is a client-side observation, not proof of server rollback.** A timed-out request may have already written to a database, saved a file, or emitted an event.

## 5. Lab: building a backend proving the body is re-sent

To observe clearly, build a lab endpoint that reads the **entire body** and deliberately returns 503 on the first attempt for a given `X-Lab-Request-Id`. The server records the SHA-256 hash and hit count.

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
class UploadReplayLabController {

    private final ConcurrentMap<String, AtomicInteger> received =
            new ConcurrentHashMap<>();

    @PostMapping(
            path = "/lab/uploads",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    ResponseEntity<String> upload(
            @RequestHeader("X-Lab-Request-Id") String requestId,
            @RequestBody byte[] body
    ) throws NoSuchAlgorithmException {

        int number = received
                .computeIfAbsent(requestId, id -> new AtomicInteger())
                .incrementAndGet();

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(body);
        String hash = HexFormat.of().formatHex(digest);
        String observation =
                "requestId=" + requestId
                + " attempt=" + number
                + " bytes=" + body.length
                + " sha256=" + hash;

        System.out.println(observation);

        if (number == 1) {
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(observation);
        }

        return ResponseEntity.ok(observation);
    }
}
~~~

**This is a simulator, not a production upload design.** The endpoint reads the whole body into RAM so use small files only; the counter map is **single-process** in-memory state. Across multiple instances, each instance has its own map, so this code cannot demonstrate cross-instance idempotency.

The 503 here triggers **after the server has received and hashed the entire body**. It does not simulate mid-upload connection drops. To test mid-stream breaks, use a controlled proxy/fault injector and inspect received bytes/chunks.

### Expected observations

~~~text
requestId=lab-001 attempt=1 bytes=4096 sha256=<digest>
HTTP 503 (after server received body)
requestId=lab-001 attempt=2 bytes=4096 sha256=<digest>
HTTP 200
~~~

Matching SHA-256 digests across both attempts prove **identical content was re-sent** to the lab server. It still **does not prove real-world uploads are safe to repeat**, because the lab endpoint only counts and hashes bytes.

## 6. RestClient: use a re-openable source for every attempt

### 6.1. Configuring a service-ID client

For Spring Framework with `RestClient` (6.1+) and a compatible Spring Cloud LoadBalancer:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class UploadClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder uploadRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient mediaRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder.baseUrl("http://media-service").build();
    }
}
~~~

Provide a `ServiceInstance` source for `media-service`. With a simple single-instance config:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            media-service:
              - uri: http://127.0.0.1:8081
    loadbalancer:
      retry:
        enabled: false
~~~

In the lab, set `spring.cloud.loadbalancer.retry.enabled=false` to avoid **hidden LoadBalancer retries** interfering with the attempt count driven by your lab code. Default behavior and supported retry mechanisms vary by version/integration. When using another HTTP client or resilience middleware, audit retries in those layers too.

### 6.2. Build a new request per attempt and re-read the file

Suppose the app holds a stable file at `Path`. `FileSystemResource` is a re-openable file source; the code creates a new resource per attempt to make lifecycle boundaries clear:

~~~java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;

class ReplayableFileUploader {

    private final RestClient client;

    ReplayableFileUploader(RestClient client) {
        this.client = client;
    }

    ResponseEntity<String> upload(
            Path file, String operationId) {

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                return client.post()
                        .uri("/lab/uploads")
                        .header("X-Lab-Request-Id", operationId)
                        .contentType(MediaType.APPLICATION_OCTET_STREAM)
                        .body(new FileSystemResource(file.toFile()))
                        .retrieve()
                        .toEntity(String.class);
            } catch (HttpServerErrorException ex) {
                boolean expected503 =
                        ex.getStatusCode().value() == 503;

                if (attempt == 2 || !expected503) {
                    throw ex;
                }
                // Lab only: resend same operationId from the file source.
            }
        }

        throw new IllegalStateException("Upload attempts exhausted");
    }
}
~~~

This snippet retries **at most once** specifically for HTTP 503 to verify file replayability; it is **not a production retry policy**. Production deployments need size limits, overall deadlines, backoff/jitter, error classification, idempotency, and proper stop conditions.

For both sends to carry identical bytes, the file must remain unmodified during the test. If a file can mutate, copy it to an immutable snapshot or persist a checksum/metadata verified by the server.

### 6.3. Why is InputStreamResource a dangerous source?

Example to avoid as a shared source for retries:

~~~java
InputStream input = Files.newInputStream(file);
InputStreamResource body = new InputStreamResource(input);

// Never assume "body" can be re-read
// when a retry interceptor runs after the first send.
~~~

`InputStreamResource` wraps an already-opened stream and usually carries single-read semantics. A request factory might buffer bytes or behave differently, yet whether retries replay completely **depends on transport and lifecycle**, never a universal guarantee.

If you need streaming to save RAM, supply a **fresh-source factory** per attempt or use a re-openable `Resource` (such as a stable file) instead of sharing an already-consumed `InputStream`.

## 7. Multipart uploads: every part must replay

Spring `RestClient` supports multipart via `MultiValueMap<String, Object>`, where each part can be text, an object, a `Resource`, or an `HttpEntity` with its own headers.

Example with a small/stable file:

~~~java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;

static String sendMultipart(
        RestClient client, Path file, String operationId) {

    MultiValueMap<String, Object> parts =
            new LinkedMultiValueMap<>();

    parts.add("description", "profile-photo");
    parts.add("file", new FileSystemResource(file.toFile()));

    return client.post()
            .uri("/multipart-uploads")
            .header("Idempotency-Key", operationId)
            .contentType(MediaType.MULTIPART_FORM_DATA)
            .body(parts)
            .retrieve()
            .body(String.class);
}
~~~

When retrying, **rebuild the multipart request and verify every part can be re-read**. Multipart boundaries, headers, or encoding order may differ across attempts even when **logical content** is identical; never assume raw multipart request bytes are bit-for-bit identical. This matters especially if bodies are HMAC-signed or the server hashes raw payloads for deduplication.

| Multipart part | What to check before retrying |
|---|---|
| Immutable string or field | Can its value change between attempts? |
| File via `FileSystemResource` | Does the file still exist unchanged, and can the stream re-open? |
| `ByteArrayResource` | Is the byte snapshot intact and within RAM limits? |
| `InputStreamResource` | Is it a single-use stream already consumed? |
| JSON part from DTO | Is the serializer deterministic with stable fields? |
| Part from inbound HTTP stream | Was it buffered/persisted or only forwarded once? |

When proxying an incoming multipart request downstream, the **caller's inbound stream** may also be single-read. Never treat `MultipartFile` or `Part` as automatically supporting unlimited replays; verify storage lifecycles or buffer safely.

## 8. WebClient: retries usually mean re-subscribing

In the reactive model, `retryWhen` causes the source publisher to **be re-subscribed** when an eligible error occurs. That replays the body only if **the body-producing publisher regenerates data on each new subscription**.

- `Flux.defer(...)` creates a fresh publisher per subscription.
- `Mono.fromSupplier(...)` can recompute data on subscription, provided the supplier still produces the **same logical content**.
- A `Flux` reading a stable file can replay if it re-opens the file per subscription.
- `Sinks.Many`/hot publishers streaming from live queues or sensors do not replay previously emitted items.
- Reference-counted `DataBuffer`s must never be cached and blindly replayed once released.

### Example body regenerated from a file on each subscription

~~~java
import java.nio.file.Path;
import java.time.Duration;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

static Mono<String> uploadReactive(
        WebClient client, Path path, String operationId) {

    Flux<DataBuffer> body = Flux.defer(() ->
            DataBufferUtils.read(
                    path,
                    new DefaultDataBufferFactory(),
                    64 * 1024));

    return client.post()
            .uri("http://media-service/lab/uploads")
            .header("X-Lab-Request-Id", operationId)
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .body(BodyInserters.fromDataBuffers(body))
            .retrieve()
            .bodyToMono(String.class)
            .retryWhen(
                    Retry.backoff(1, Duration.ofMillis(200))
                            .filter(error ->
                                    error instanceof WebClientResponseException ex
                                    && ex.getStatusCode().value() == 503));
}
~~~

This pattern assumes `WebClient` was built from `@LoadBalanced WebClient.Builder` with `media-service` in discovery. `Retry.backoff(1, ...)` permits **one retry after the initial send**; the filter retries only HTTP 503 converted by `retrieve()` into `WebClientResponseException`.

Creating the `Flux` via `defer` lets it re-open the file on re-subscription instead of reusing sent `DataBuffer`s. Spring's `DataBufferUtils.read(...)` reads files in chunks, though you must inspect memory management, cancellation, and backpressure behavior for your exact version and connector. Never modify the file while two attempts could run.

### Not every retryWhen is safe

Semantically dangerous example:

~~~java
Flux<byte[]> hotEvents = eventSource.asFlux();

return webClient.post()
        .uri("/stream")
        .body(hotEvents, byte[].class)
        .retrieve()
        .bodyToMono(Void.class)
        .retryWhen(Retry.max(1));
~~~

If `eventSource` is a hot stream/`Sinks.Many`, elements emitted during the first try **will not replay automatically** when retry re-subscribes. Attempt 2 can start from newer items or send an incomplete stream. Design snapshot/log/offset mechanisms—or **do not retry at the HTTP layer**.

### Where do timeout and retry belong?

~~~java
Mono<String> oneOperationBudget =
        uploadReactive(webClient, file, operationId)
                .timeout(Duration.ofSeconds(5));
~~~

An outer `timeout` bounds total operation duration, including retries/backoff. Placing `timeout` **inside** the retried publisher grants each attempt a fresh wait window. Client-side cancellation time never proves the server aborted its work.

## 9. OpenFeign: do not confuse Feign Retryer with replayability

Spring Cloud OpenFeign registers `Retryer.NEVER_RETRY` by default to **disable Feign retries**, unlike plain Feign which can retry certain I/O errors. Retries in Spring Cloud LoadBalancer, transport, or application layers follow their own rules if enabled.

An interface uploading a small body can be declared as:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "media-service")
interface MediaFeignClient {

    @PostMapping(
            path = "/lab/uploads",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    String upload(
            @RequestHeader("X-Lab-Request-Id") String operationId,
            @RequestBody byte[] payload);
}
~~~

With a small immutable `byte[]`, the app has a byte source far easier to reuse than a single-read stream. Yet retrying HTTP 503 requires an **explicit policy** compatible with Spring Cloud OpenFeign, or a bounded outer wrapper. Never assume Feign automatically retries just because the interface uses `@FeignClient`.

For large files, `byte[]` forces the whole file into RAM. Some Feign encoders/transports buffer request bodies during encoding, while some streaming approaches are not replayable. Thus **OpenFeign multipart/streaming uploads must be tested against your actual encoder, Feign Client, and retry policy**; never claim every `MultipartFile`, `Resource`, or `InputStream` is replayable.

When Feign uses LoadBalancer, re-selecting a service instance on retry **does not guarantee the body is re-encoded or re-read properly**. Those are two separate layers.

## 10. Streaming and large uploads: why full-request retry is usually wrong

For a 20 KB file, retrying from the beginning may be fine in a lab. For a 4 GB video that dropped after sending 3.8 GB, retrying the entire POST can:

- Re-transmit huge volumes of data, inflating bandwidth and cost.
- Hold client and backend sockets/threads/buffers much longer.
- Leave behind orphaned temp files or dangling upload sessions.
- Duplicate data if the server already committed an earlier chunk or the entire file.
- Breach business timeouts and trigger cascading retries.

For **unbounded streams** (sensor events, live audio/video, SSE, or log streams), "replaying the whole body" rarely makes sense. Track **which events were acknowledged and which were not**, then resume from a cursor or sequence number.

### Designing checkpoint-resumable uploads

An upload protocol can be structured as:

~~~mermaid
flowchart TD
    A["Create upload session and uploadId"]
    B["Split file into parts: part 1, 2, 3..."]
    C["Send part k with checksum and offset"]
    D{"Server confirmed part k saved?"}
    E["Mark part k complete"]
    F["Query upload status / verify checksum"]
    G["Resend only unconfirmed parts"]
    H["Complete upload with fixed operationId"]
    I["Server commits once"]
    A --> B --> C --> D
    D -->|"Yes"| E --> H
    D -->|"No / timeout"| F --> G --> C
    H --> I
~~~

Illustrative HTTP contract (not built-in endpoints in Spring Cloud):

~~~http
POST /uploads
Idempotency-Key: operation-123

HTTP/1.1 201 Created
Location: /uploads/upload-789

PUT /uploads/upload-789/parts/4
Content-Range: bytes 3145728-4194303/8388608
X-Content-SHA256: <sha256-of-part>

GET /uploads/upload-789/status

POST /uploads/upload-789/complete
Idempotency-Key: operation-123
~~~

`uploadId`, part number, offset, checksum, and operation ID allow the server to identify already-stored chunks. The server must enforce consistent part writes, reject bad checksums, prevent invalid overwrites, and commit the final asset once.

Practical solutions can leverage object-storage multipart uploads, resumable upload protocols, or custom APIs with upload sessions. Do not reinvent complex resume protocols if your storage infrastructure already provides standard protocols and SDKs.

## 11. Idempotency-Key: resending the same body is still not enough

An idempotency key **does not create idempotency** merely because the client sends a header. The backend must enforce:

1. Persist the key under an appropriate scope (client/tenant/operation), tied to a checksum or payload identifier.
2. Use transactions, unique constraints, or atomic primitives so concurrent requests with one key never cause two side effects.
3. Persist outcomes or processing state durably enough for retries landing on another instance to query or replay them.
4. Reject mismatched payloads reusing the same key cleanly rather than silently returning old results.
5. Define TTL/retention, in-flight request handling, rollbacks, and post-timeout client recovery.

**Example:** attempt 1 hit `media-1`, committed the file, and lost the response; attempt 2 hits `media-2`. Only when both instances share idempotency state and storage can attempt 2 return attempt 1's result without creating a second file.

In section 5's lab, `X-Lab-Request-Id` is merely a counter key for observation—it is **not** a real idempotency implementation.

## 12. Memory costs and trade-offs for replayability

| Strategy | Memory | Retryability | Trade-offs |
|---|---|---|---|
| Buffer `byte[]` in RAM | Proportional to body size | Easy to replay from intact snapshot | OOM/GC risk under many large uploads |
| Spool to temp file then send | Lower RAM, consumes disk | Can re-open file | Disk I/O, cleanup, encryption, and quotas |
| Read stable file directly per attempt | Low RAM, repeated disk/network | Yes if file stays unchanged | Slow to re-send entire large files |
| Cold publisher regenerating data | Source-dependent | Yes if source can regenerate | Harder cancellation/backpressure control |
| Hot publisher/socket stream | Usually keeps no history | Not naturally replayable | Needs offsets/logs/resume protocol |
| Chunked/resumable upload | Buffers per part | Retries only confirmed-missing parts | More complex server and protocol |

Never crank up WebClient's `maxInMemorySize` just to "fix upload retries." That setting governs codec/aggregation buffering; it never turns a hot stream into a replayable body. If buffering in RAM, multiply by concurrency: 100 concurrent 50 MB uploads demand multiple gigabytes before overhead.

Temp files may hold sensitive data; enforce permissions, encryption where required, disk quotas, and cleanup on completion or expiration.

## 13. Retry checklist with Spring Cloud LoadBalancer

Spring Cloud LoadBalancer supports retries on compatible integrations when enabled with required dependencies, yet **instance selection** is separate from **request body replayability**.

Before enabling upload retries:

- **Body source:** can every attempt regenerate the payload from scratch, or is it a single-use stream?
- **Retry conditions:** are only classified transient errors retried, not arbitrary 4xx/5xx?
- **Method:** are `POST`/`PATCH` retries permitted, and does the server enforce real idempotency?
- **Instance selection:** do retries keep the old instance or pick another replica, and do replicas share state/storage?
- **Timeout/deadline:** do total attempts, backoff, and repeated bytes fit inside the budget?
- **Body size:** should it buffer to RAM/disk, or use chunked/resumable uploads?
- **Retry layers:** are Feign, HTTP transport, LoadBalancer, and resilience layers active simultaneously?
- **Resource lifecycle:** are streams/files/`DataBuffer`s opened and closed cleanly per attempt?
- **Observability:** can you log attempt number, operation ID, body size/hash, and commit state without exposing sensitive payloads?
- **Cancellation:** when a client cancels or times out, does the backend keep writing data?

Never set `spring.cloud.loadbalancer.retry.retryOnAllOperations=true` as a shortcut to enable upload retries without verifying idempotency, body sources, and your exact integration.

### Distinguishing "no server instance" from "unreplayable body"

If LoadBalancer finds no server for `media-service`, failure occurs before any HTTP send. If an instance is selected yet attempt 2 lacks data or throws `stream closed`, the fault lies in the body source, encoder, or lifecycle. If the full body replays cleanly yet the server creates two records, the bug is **business idempotency**, not instance selection.

## 14. Lab exercise verifying two independent factors

Run the backend on port `8081` using a single-instance `SimpleDiscoveryClient` as in section 6, and create an immutable 4 KB test file.

| Experiment | Body | Fault mechanism | What to verify |
|---|---|---|---|
| A | `byte[]` or `FileSystemResource` | Server returns 503 on attempt 1 after reading body | Attempt 2 re-sends full bytes with matching SHA-256 |
| B | `InputStreamResource` from opened stream | Enable retry and force re-read | Do not assume attempt 2 has a body; observe error or missing bytes |
| C | Multipart text + file | Return 503 after reading request | Every part regenerates with identical logical content |
| D | `Flux.defer` reading file | Server returns 503 | Fresh subscription; file re-reads cleanly |
| E | Hot Flux | Server returns 503/cancel | Previously emitted events do not reappear |
| F | Large chunked file | Drop connection after confirming several parts | Retry only unconfirmed parts without resending the whole file |
| G | Repeatable body, no server dedup | Return 503 after side effect | Can create duplicate business writes despite identical SHA-256 |

For each run, record:

~~~text
operationId=operation-123
attempt=1
serviceId=media-service
instanceId=media-1
bodyBytes=4096
bodySha256=<digest>
result=HTTP_503
serverReceived=true
serverCommitted=<unknown|true|false>

operationId=operation-123
attempt=2
instanceId=media-1
bodyBytes=4096
bodySha256=<same digest>
result=HTTP_200
~~~

This is a **suggested log format**, not default fields from Spring Cloud LoadBalancer. `serverCommitted` must come from actual backend state records rather than guessing from HTTP status.

### Lab completion criteria

1. Distinguish a **recreatable** body from a **single-read** stream source.
2. Prove two attempts sent identical content using byte counts/hashes and server logs, not merely "retry ran."
3. Explain why 503 or read timeouts do not prove the server left the request unprocessed.
4. Demonstrate the effect of same-instance vs. next-instance retries in Spring Cloud LoadBalancer.
5. Propose duplicate prevention for POST uploads using server-enforced idempotency keys.
6. For large uploads/streaming, propose chunks/offsets/checkpoints instead of endlessly retrying the full request.

## 15. Design principles to remember

- **Replayable ≠ idempotent.** Being able to resend the same bytes does not mean the business operation is safe to receive them twice.
- **Retries must be conditional.** Retry only eligible errors, capping attempts, backoff, and overall deadlines.
- **Never reuse an exhausted body stream.** Re-open files per attempt; regenerate data per subscription in reactive publishers.
- **Never infer rollback from HTTP status.** The server may have committed before the response was lost.
- **Never assume multipart/Feign streaming is replayable.** Test against your exact encoder, request factory, and transport.
- **Do not confuse LB retry with body replay.** LoadBalancer selects instances; the HTTP client/encoder and body source decide whether the payload replays.
- **Large uploads should support resume.** Chunk IDs, offsets, checksums, and upload state minimize re-transmitted bytes.
- **Idempotency requires backend enforcement.** Keys must stay stable across attempts with concurrency, data, and outcome control.
- **Observe every attempt.** Track attempt, instance, bytes/hash, failure reason, and commit status without logging sensitive data.

**Conclusion:** In Spring Cloud LoadBalancer, retries can select another `ServiceInstance`, yet they **cannot resurrect an exhausted `InputStream`, a hot `Flux` whose events already passed, or a transient body living only in a closed socket**. With `RestClient`, `WebClient`, and OpenFeign, combine replayable body sources, bounded retry policies, and server-side idempotency. For large uploads or streams, the reliable solution is usually a **resumable protocol** rather than blindly retrying the entire request.

**Official references:**

- [Spring Cloud Commons – Retrying Failed Requests](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Framework – REST Clients, Request Body, and Multipart](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework – WebClient Request Body](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html)
- [Spring Cloud OpenFeign – Retryer and Feign Client Configuration](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Project Reactor – Retry and Resubscription](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
