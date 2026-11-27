# Integrating Reactive Redis with a WebFlux API

**Spring WebFlux** provides a model for building HTTP APIs based on Reactive Streams, where asynchronous operations are represented by `Mono<T>` and `Flux<T>`. **Spring Data Redis Reactive** lets applications execute Redis commands under the same model via `ReactiveRedisTemplate`, `ReactiveStringRedisTemplate`, and reactive Lettuce connections.

This exercise builds a Spring Boot application exposing an API for managing **temporary notes**. Each note is stored in Redis with a **30-minute TTL**. The application supports:

- `POST /api/notes`: creates a note, returning HTTP `201 Created`.
- `GET /api/notes/{id}`: reads a note; returns `404` when the key genuinely does not exist.
- `DELETE /api/notes/{id}`: deletes a note; returns `204` when deleted, `404` when absent.
- Testing with `curl` and `WebTestClient` connected to real Redis in Testcontainers.

Beyond the sample application, the article analyzes `Mono`/`Flux` usage, serialization, Redis access errors, cache-aside, concurrency, Redis Cluster, Pub/Sub, Streams, testing, and operations. The goal is not merely to write an endpoint, but to understand **the boundaries of reactivity**: never blocking the event loop, never manually subscribing inside a controller, never confusing cache misses with errors, and never treating a reactive chain as a global transaction.

## 1. Architecture: WebFlux Calling Redis in a Reactive Chain

A request flows through the layers:

```text
                    HTTP client
                        |
                 Reactor Netty
                        |
                        v
                 WebFlux Router
                        |
                        v
               NoteController
                 Mono<...>
                        |
                        v
                  NoteService
                        |
                        v
          ReactiveStringRedisTemplate
                        |
                        v
           Lettuce reactive connection
                        |
                  TCP / TLS
                        |
                        v
                    Redis server
                        |
                        v
            Mono success / empty / error
                        |
                        v
              WebFlux HTTP response
```

Key characteristics:

1. The controller **returns a publisher** to WebFlux instead of calling `subscribe()` or `block()` itself.
2. The Redis client performs asynchronous I/O; the request-handling thread does not block synchronously waiting for Redis to reply.
3. `Mono` represents at most one result; `Flux` represents multiple results.
4. An empty publisher and an errored publisher are two distinct signals.
5. There is no guarantee that all code inside a reactive chain is non-blocking: synchronous JDBC, `Thread.sleep`, or blocking file I/O can still stall threads if called directly.
6. Canceling a request does not necessarily cancel a Redis command already dispatched to the server.

This is an I/O model, **not a guarantee that Redis itself executes individual commands faster**. Under small loads, reactive chain overhead may yield no visible gain; benefits typically appear under high concurrency waiting on I/O.

## 2. ReactiveRedisTemplate and ReactiveStringRedisTemplate

Two common APIs:

| API | When to Use | Characteristics |
|---|---|---|
| `ReactiveRedisTemplate<K,V>` | Need object keys/values using configured serializers | Generic, flexible across Redis structures |
| `ReactiveStringRedisTemplate` | UTF-8 String keys and values | Fits Strings, JSON strings, counters, and small examples |
| `ReactiveValueOperations<K,V>` | SET, GET, INCR on Redis Strings | Accessed via `opsForValue()` |
| `ReactiveHashOperations` | Hash fields | Accessed via `opsForHash()` |
| `ReactiveSetOperations` | Redis Sets | Accessed via `opsForSet()` |
| `ReactiveZSetOperations` | Sorted Sets | Accessed via `opsForZSet()` |
| `ReactiveStreamOperations` | Redis Streams | Stream operations with reactive APIs |
| `ReactiveRedisConnectionFactory` | Creates reactive Redis connections | Spring Data Redis infrastructure |

In this exercise, we use `ReactiveStringRedisTemplate` so both keys and values are Strings. `Note` objects are converted to JSON with Jackson at the service layer.

Reasons for this choice:

- Easy to inspect data directly via `redis-cli GET`.
- Avoids confusion between key and value serializers.
- Clearly illustrates the Redis bytes ↔ JSON ↔ Java object boundary.
- Enables basic commands without configuring generic serializers upfront.

In larger applications, a `ReactiveRedisTemplate<String, Note>` with an explicitly configured JSON serializer is also reasonable. Either way, **every application reading the same key must agree on serializer, namespace, and schema**.

## 3. Environment Setup

Practice components:

- A JDK compatible with the Spring Boot version in use.
- Spring Boot with WebFlux and Spring Data Redis Reactive.
- Redis supporting standard String and TTL commands.
- Docker to run local Redis or Testcontainers when testing.
- An HTTP tool such as `curl`.

Sample project layout:

```text
redis-webflux-demo/
├── build.gradle
├── src/main/java/com/example/rediswebflux/
│   ├── RedisWebfluxDemoApplication.java
│   ├── note/
│   │   ├── Note.java
│   │   ├── CreateNoteRequest.java
│   │   ├── NoteService.java
│   │   └── NoteController.java
│   └── web/
│       └── RedisErrorAdvice.java
├── src/main/resources/
│   └── application.yml
└── src/test/java/com/example/rediswebflux/
    └── NoteApiIntegrationTest.java
```

Java classes must reside in packages covered by Spring component scanning. The main example uses root package `com.example.rediswebflux` and its subpackages.

### 3.1. Dependencies

With Gradle and appropriate Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers'
}
```

The project relies on the Spring Boot plugin/BOM to manage compatible versions of Reactor, Spring Data Redis, Lettuce, and Testcontainers. Across Spring Boot releases, dependency names and auto-configuration details may vary; use the reactive starters provided for the **exact version** you deploy.

**Do not add `spring-boot-starter-web` (Spring MVC) for the APIs in this example.** Having both MVC and WebFlux on the classpath may cause Spring Boot to pick an unintended web application type depending on configuration. Explicitly verify which stack is active.

### 3.2. Local Redis

With Docker, start a test Redis bound solely to the development machine's loopback interface:

```bash
docker run --rm -d \
  --name redis-webflux-demo \
  -p 127.0.0.1:6379:6379 \
  redis:7.4-alpine
```

Verify:

```bash
docker exec redis-webflux-demo redis-cli PING
```

Expected: `PONG`.

This configuration is strictly for a **controlled development machine**; production Redis needs private endpoints, firewalls, TLS, ACLs, secret management, and HA as required. Never publish Redis `6379` to the Internet.

When done practicing:

```bash
docker stop redis-webflux-demo
```

Never run `FLUSHALL` on a shared Redis instance just to clean up lesson data.

## 4. Configuring Spring Boot to Connect to Redis

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      connect-timeout: 2s
      timeout: 2s

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Locally, Redis runs on `localhost:6379`. In containers or cloud environments, point `REDIS_HOST` and `REDIS_PORT` to a **private Redis endpoint**.

For Redis with authentication and TLS, an appropriate Spring Boot configuration may add:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
```

This configuration is for a **TLS-enabled environment**; do not apply it verbatim to the plain-TCP local Redis above if TLS is disabled there. Passwords must come from a secret manager or secret injection mechanism; never hardcode production credentials.

### 4.1. Why Not Create a Connection per Request?

Spring Boot creates a `ReactiveStringRedisTemplate` bean from the connection factory when reactive Redis auto-configuration conditions match. Controllers/services simply inject the bean:

```java
@Service
public class ExampleService {

    private final ReactiveStringRedisTemplate redis;

    public ExampleService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }
}
```

Never instantiate a fresh native Lettuce client per HTTP request. The connection factory is a shared Spring-managed resource handling reconnects, topology, and connection cleanup.

However, **successful bean creation does not prove Redis is reachable**. Network, ACL, TLS, or timeout failures may surface only when subscribing to a publisher executing a command.

## 5. Bootstrapping the Spring Boot Application

Entry point:

```java
package com.example.rediswebflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedisWebfluxDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RedisWebfluxDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` component-scans classes in the root package and its subpackages.

The sample app does not use R2DBC/JPA. Redis stores **temporary** notes. In production, if data must be durable, Redis with a TTL must not be treated as equivalent in durability to a transactional database.

## 6. Resource Design: Note and CreateNoteRequest

Immutable model using a Java record:

```java
package com.example.rediswebflux.note;

import java.time.Instant;

public record Note(
        String id,
        String text,
        Instant createdAt) {
}
```

API input:

```java
package com.example.rediswebflux.note;

public record CreateNoteRequest(String text) {
}
```

Sample request:

```json
{
  "text": "WebFlux and Redis test note"
}
```

Sample response:

```json
{
  "id": "e27a9f8a-d755-42ac-b11d-9e7c87501866",
  "text": "WebFlux and Redis test note",
  "createdAt": "2026-11-13T08:10:00Z"
}
```

Values are illustrative. Each note's ID is generated with a UUID so users cannot supply arbitrary Redis keys.

Business contract for the exercise:

- Notes are temporary data, **not required to survive every Redis failure**.
- Each note has a 30-minute TTL from creation.
- `GET` **does not extend TTL**.
- Expired notes behave identically to non-existent IDs.
- On Redis connection failures, the API **must not** return `404` as though the key were confirmed absent.

## 7. NoteService: Redis GET, SET with TTL, and DEL

This is the core integration piece of the exercise.

```java
package com.example.rediswebflux.note;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
public class NoteService {

    private static final String PREFIX = "demo:webflux:notes:v1:";
    private static final Duration TTL = Duration.ofMinutes(30);

    private final ReactiveStringRedisTemplate redis;
    private final ObjectMapper mapper;

    public NoteService(
            ReactiveStringRedisTemplate redis,
            ObjectMapper mapper) {
        this.redis = redis;
        this.mapper = mapper;
    }

    public Mono<Note> create(String text) {
        return Mono.defer(() -> {
            if (text == null
                    || text.isBlank()
                    || text.length() > 1000) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "text must contain 1..1000 characters"));
            }

            Note note = new Note(
                    UUID.randomUUID().toString(),
                    text.trim(),
                    Instant.now());

            return Mono.fromCallable(
                            () -> mapper.writeValueAsString(note))
                    .flatMap(json ->
                            redis.opsForValue()
                                    .set(key(note.id()), json, TTL)
                                    .flatMap(saved -> Boolean.TRUE.equals(saved)
                                            ? Mono.just(note)
                                            : Mono.error(
                                                    new IllegalStateException(
                                                            "Redis SET not confirmed"))));
        });
    }

    public Mono<Note> findById(String id) {
        String redisKey = key(id);

        return redis.opsForValue()
                .get(redisKey)
                .flatMap(json -> Mono.fromCallable(
                        () -> deserializeNote(json)));
    }

    public Mono<Boolean> deleteById(String id) {
        return redis.delete(key(id))
                .map(count -> count > 0);
    }

    private Note deserializeNote(String json)
            throws JsonProcessingException {

        Note note = mapper.readValue(json, Note.class);

        if (note == null) {
            throw new IllegalStateException(
                    "Redis returned invalid note payload");
        }

        return note;
    }

    private String key(String id) {
        try {
            return PREFIX + UUID.fromString(id);
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid note id", error);
        }
    }
}
```

### 7.1. Why Use Mono.defer When Creating Notes?

`Mono.defer(...)` defers generating `UUID` and `Instant.now()` until subscription time.

In WebFlux, the framework subscribes to the publisher to execute the request. Writing it this way gives each subscription a clean execution rather than eagerly generating an ID when the Java method is called before subscription occurs.

**This does not mean HTTP retries preserve the same ID.** Resending `POST` starts a new request and creates a new note. If business rules require duplicate prevention on retries, add a dedicated idempotency mechanism.

### 7.2. SET with TTL Is the Right Operation

The line:

```java
redis.opsForValue().set(redisKey, json, Duration.ofMinutes(30))
```

corresponds to sending a `SET` with expiration in the same Redis operation.

Prefer **SET with TTL** over:

```text
SET key value
EXPIRE key 1800
```

in two separate commands whenever the requirement is "values always have a TTL". If the connection drops between the two commands, the key is created without an expiry.

Redis enforces TTL per server policy. Once TTL expires or a key is evicted/deleted, `GET` no longer sees the value. TTL **does not guarantee a resource survives a full 30 minutes** if Redis loses data or eviction is permitted to drop it early.

### 7.3. GET Returns Mono.empty() for Missing Keys

`redis.opsForValue().get(redisKey)` returns a `Mono<String>`:

- Redis holds a value: emits the JSON String.
- Redis returns nil because the key is absent: completes empty, i.e., `Mono.empty()`.
- Redis fails: emits `Mono.error(error)`.

`flatMap(json -> Mono.fromCallable(...))` decodes only when JSON is present. On a Redis miss, the decode branch does not execute.

`deserializeNote` explicitly rejects the JSON literal `null` so an invalid payload does not turn into a false `Mono.empty()`. If JSON fails schema decoding, the exception propagates down the reactive chain; that is an **invalid payload**, not a missing key.

### 7.4. DELETE Returns the Count of Deleted Keys

`redis.delete(redisKey)` returns `Mono<Long>` in the reactive API:

- `1`: one key was deleted.
- `0`: no key existed to delete at command execution time.
- `onError`: the command did not complete normally.

`DELETE` can be called repeatedly on client retries, though the second result differs: once gone, count is 0. On a timeout after delete, you may not know whether the command ran; however, key deletion is effectively idempotent, unlike `INCR`.

## 8. NoteController: Mapping Mono to HTTP Responses

The controller returns publishers without executing them manually:

```java
package com.example.rediswebflux.note;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/notes")
public class NoteController {

    private final NoteService service;

    public NoteController(NoteService service) {
        this.service = service;
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Note>> create(
            @RequestBody Mono<CreateNoteRequest> request) {

        return request
                .flatMap(body -> service.create(body.text()))
                .map(note -> ResponseEntity
                        .created(URI.create("/api/notes/" + note.id()))
                        .body(note));
    }

    @GetMapping("/{id}")
    public Mono<Note> get(@PathVariable String id) {
        return service.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Note not found")));
    }

    @DeleteMapping("/{id}")
    public Mono<ResponseEntity<Void>> delete(
            @PathVariable String id) {

        return service.deleteById(id)
                .map(deleted -> {
                    if (deleted) {
                        return ResponseEntity.noContent()
                                .<Void>build();
                    }

                    return ResponseEntity.status(
                                    HttpStatus.NOT_FOUND)
                            .<Void>build();
                });
    }
}
```

This application is reactive across both HTTP and Redis I/O. There is no:

```java
redis.opsForValue().get(key).block();
```

in the controller, nor:

```java
redis.opsForValue().set(key, value).subscribe();
return Mono.just(ResponseEntity.ok().build());
```

That second pattern is **fire-and-forget**: the HTTP response can go out before Redis finishes writing, write errors never reach the response, and manual subscriptions are poorly tied to request cancellation or shutdown lifecycles.

### 8.1. switchIfEmpty Applies Only to Misses

In the `GET` endpoint:

```java
return service.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Note not found")));
```

`switchIfEmpty` triggers only when upstream **completes without emitting a Note**. If Redis times out and upstream emits `onError`, `switchIfEmpty` **does not** turn that error into `404`.

This is the desired behavior:

```text
GET /api/notes/{id}
        |
        +-- Redis returns valid JSON -> 200
        |
        +-- Redis returns nil        -> 404
        |
        +-- Redis connection fails   -> access error, not 404
        |
        +-- JSON decode fails        -> data error, not 404
```

### 8.2. Mono<ResponseEntity<T>> vs Mono<T>

Both are valid in WebFlux:

- `Mono<Note>` lets the framework serialize the body with the default success status.
- `Mono<ResponseEntity<Note>>` lets you customize status/headers, e.g., `201 Created`.
- `Mono<ResponseEntity<Void>>` lets you select `204 No Content` or `404 Not Found`.

Using `ResponseEntity` does not make code blocking. What matters is building the HTTP response **inside the reactive chain** without calling blocking APIs on the event loop.

## 9. Classifying Redis Errors and API Responses

In an API application, Redis errors can include:

- Unreachable host or connect timeout.
- Command timeout.
- Wrong credentials/ACL `NOAUTH` or `NOPERM`.
- Redis returning `WRONGTYPE` because a key holds the wrong structure.
- TLS handshake or certificate validation failures.
- Redis Cluster redirects/unavailable slots.
- JSON data failing deserialization.
- Client shutdown while commands are in flight.

Do not catch everything with:

```java
.onErrorResume(error -> Mono.empty())
```

if the controller subsequently uses `switchIfEmpty` to return `404`. Doing so disguises infrastructure outages or corrupt data as "note not found".

### 9.1. Advice for Redis Connection Errors

Example mapping a common connection failure to HTTP `503 Service Unavailable`:

```java
package com.example.rediswebflux.web;

import java.util.Map;

import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class RedisErrorAdvice {

    @ExceptionHandler(RedisConnectionFailureException.class)
    public ResponseEntity<Map<String, String>> unavailable(
            RedisConnectionFailureException error) {

        // Emit internal logs/metrics with secrets scrubbed.
        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of(
                        "error", "redis_unavailable",
                        "message", "Temporary storage is unavailable"));
    }
}
```

The example catches only **one specific exception type**. In production, classify timeouts, driver connection errors, serialization errors, misconfigurations, `WRONGTYPE`, and business errors. Never assume every `DataAccessException` subtype is a transient error safe to retry.

Never return raw exception messages containing hostnames, keys, or configuration details in public API responses.

### 9.2. Expected HTTP Outcomes Table

| Scenario | Reactive Signal | HTTP in Lesson |
|---|---|---|
| Note created successfully | `Mono.just(note)` | `201 Created` |
| Valid ID read and key exists | `Mono.just(note)` | `200 OK` |
| Valid ID read and Redis nil | `Mono.empty()` | `404 Not Found` |
| Existing key deleted | `Mono.just(true)` | `204 No Content` |
| Missing key deleted | `Mono.just(false)` | `404 Not Found` |
| Blank or oversized body text | `Mono.error(ResponseStatusException)` | `400 Bad Request` |
| Invalid UUID | `Mono.error(ResponseStatusException)` | `400 Bad Request` |
| Redis connection failure | `Mono.error(RedisConnectionFailureException)` | `503` via advice |
| Undecodable payload | `Mono.error(...)` | `5xx` and alert; never `404` |
| Wrong Redis ACL | Access/command error | `5xx` with config alert; never treat as miss |

When Redis is only a cache and a database is the source of truth, the policy on Redis failure differs: the app can **fail open within limits** to the database. Here, however, the notes API stores resources directly in Redis with no database to fall back to. Avoid "returning a default note" as if real data were found.

## 10. Practicing API Calls with curl

Once local Redis and the Spring Boot application are running, create a note:

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello WebFlux Redis"}'
```

Expected output:

```http
HTTP/1.1 201 Created
Location: /api/notes/e27a9f8a-d755-42ac-b11d-9e7c87501866
Content-Type: application/json

{"id":"e27a9f8a-d755-42ac-b11d-9e7c87501866","text":"Hello WebFlux Redis","createdAt":"2026-11-13T08:10:00Z"}
```

Actual IDs and timestamps will differ from the sample. Copy the returned ID into the next command:

```bash
curl -i \
  http://localhost:8080/api/notes/e27a9f8a-d755-42ac-b11d-9e7c87501866
```

Expected: `200 OK` with the Note JSON.

Inspect the physical key in local Redis:

```bash
docker exec redis-webflux-demo redis-cli \
  GET 'demo:webflux:notes:v1:e27a9f8a-d755-42ac-b11d-9e7c87501866'
```

Inspect expiration time:

```bash
docker exec redis-webflux-demo redis-cli \
  TTL 'demo:webflux:notes:v1:e27a9f8a-d755-42ac-b11d-9e7c87501866'
```

TTL will be just under 1800 seconds if freshly created. Redis `TTL` returns `-2` when the key is gone and `-1` when the key exists without an expiry; negative numbers do not automatically mean network errors.

Delete:

```bash
curl -i -X DELETE \
  http://localhost:8080/api/notes/e27a9f8a-d755-42ac-b11d-9e7c87501866
```

Expected: `204 No Content`. Calling GET again on the deleted ID returns `404 Not Found`.

### 10.1. Testing a Non-Existent Key

Use a valid UUID that has never been created:

```bash
curl -i \
  http://localhost:8080/api/notes/00000000-0000-0000-0000-000000000001
```

Expected `404` when Redis is reachable. This highlights the **fundamental difference** from stopping the test Redis and calling the same endpoint: when Redis is unavailable, the application has no proof the key does not exist.

### 10.2. Testing Invalid Input

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"text":"   "}'
```

Expected `400` from service validation. Non-UUID IDs also return `400`. In production, add Bean Validation and request body size/JSON schema limits at the HTTP boundary rather than checking only a single field.

## 11. Mono and Flux: Understanding Signals Before Composing Operators

Reactor distinguishes:

```text
Mono with value:
    onNext(value) -> onComplete

Empty Mono:
    onComplete

Errored Mono:
    onError(error)
```

There is no `onNext(null)` in Reactive Streams. When Redis returns nil, reactive `GET` methods express it as empty completion rather than emitting Java `null`.

### 11.1. Common Operators

| Operator | Purpose | What to Remember |
|---|---|---|
| `map` | Synchronous value transform | Mapping function must not return null arbitrarily |
| `flatMap` | Compose async publisher-returning step | Use when chaining reactive Redis/API/DB calls |
| `switchIfEmpty` | Switch to another publisher if empty | Does not catch `onError` |
| `defaultIfEmpty` | Supply default value if empty | Does not handle exceptions |
| `onErrorResume` | Recover based on error type | Place close to the intended source so unrelated errors aren't swallowed |
| `onErrorMap` | Translate exception type | Preserve useful cause |
| `timeout` | Cap wait time in chain | Timeout does not guarantee the Redis command didn't run |
| `retryWhen` | Conditional, bounded retries | Never blindly retry side effects |
| `doOnNext` | Observation/logging/metrics | Avoid unmanaged business side effects |
| `doFinally` | Cleanup/metrics on complete/error/cancel | Do not treat cancel as rollback |
| `concatMap` | Process values sequentially | Useful when ordering must be preserved |
| `flatMap` with concurrency | Bounded parallel processing | Does not guarantee side-effect ordering |

### 11.2. Why Not Call subscribe() Inside a Controller?

Wrong:

```java
@PostMapping("/bad")
public Mono<String> wrong() {
    redis.opsForValue()
            .set("demo:key", "value")
            .subscribe();

    return Mono.just("ok");
}
```

The response can leave before `SET` completes; if `SET` fails, the response can still be `200`. Detached subscriptions also fail to bind to HTTP request cancellation or shutdown lifecycles.

Better:

```java
@PostMapping("/good")
public Mono<String> correct() {
    return redis.opsForValue()
            .set("demo:key", "value")
            .flatMap(ok -> Boolean.TRUE.equals(ok)
                    ? Mono.just("ok")
                    : Mono.error(new IllegalStateException(
                            "SET was not confirmed")));
}
```

WebFlux subscribes and manages the publisher; errors flow into HTTP error handling.

### 11.3. Why Not Call block() Inside a Request Handler?

Wrong:

```java
@GetMapping("/bad/{key}")
public String wrong(@PathVariable String key) {
    return redis.opsForValue().get(key).block();
}
```

`block()` waits synchronously, losing non-blocking benefits and risking Reactor rejections on non-blocking threads. Under high request loads, blocking I/O like this degrades throughput.

If you must invoke a blocking library such as JDBC/JPA, choose a suitable stack or offload the call onto a blocking-I/O scheduler such as `Schedulers.boundedElastic()`:

```java
Mono<Product> result =
        Mono.fromCallable(() -> blockingRepository.find(id))
                .subscribeOn(Schedulers.boundedElastic());
```

This **isolates blocking**, rather than turning JDBC into true non-blocking I/O; you must still bound connection pools, concurrency, and latency. In end-to-end reactive WebFlux apps, R2DBC or a native reactive API is usually easier to govern.

## 12. Serializer Configuration: Why String + JSON?

In the example:

```text
Note object
    |
    v
ObjectMapper.writeValueAsString
    |
    v
JSON String
    |
    v
ReactiveStringRedisTemplate
    |
    v
UTF-8 bytes in Redis
```

On read, the flow reverses:

```text
Redis UTF-8 String
    |
    v
ReactiveStringRedisTemplate GET
    |
    v
ObjectMapper.readValue(..., Note.class)
    |
    v
Note object
```

Boundaries to preserve:

1. **Redis nil:** key missing on `GET` → `Mono.empty()`.
2. **JSON literal null:** key holds `"null"`, decoder returns Java null → invalid data per Note contract.
3. **Invalid JSON schema:** Redis holds bytes, deserialization fails → `Mono.error()`.
4. **Wrong key serializer/prefix:** app queries a different physical key → valid miss in Redis, architectural misconfiguration in code.
5. **Data versioning:** when Java record/schema changes, plan compatibility with entries still living inside TTL.

### 12.1. ReactiveRedisTemplate with Object Serializers

In larger projects, you can configure `ReactiveRedisTemplate<String, Note>` with `RedisSerializationContext` to handle value serialization automatically. Explicitly configure:

- Key serializer.
- Value serializer.
- Hash key/value serializers if using Hashes.
- JSON type mapping or schema version.
- Handling rules for unreadable values.
- Compatibility across app versions during rolling deploys.

Never have two services share a namespace where one uses JSON Strings and the other uses Java native serialization, then conclude "Redis lost the key".

### 12.2. JSON Mapping Does Not Always Need a Thread Hop

`ObjectMapper` performs synchronous CPU work on in-memory data. For small payloads like `Note`, running inside `Mono.fromCallable` on the reactive chain is fine. For massive payloads, CPU-heavy encoding/decoding can stall the event loop—measure and consider changing formats, shrinking payloads, or offloading heavy computation onto an appropriate scheduler.

**Do not wrap every trivial synchronous Java call in `boundedElastic()`.** Scheduler hops carry overhead; optimize based on profiling and workload traits.

## 13. TTL, Sliding Expiration, and Limits of Temporary Storage

In this exercise, each Note gets `TTL = 30 minutes` on `SET`:

```text
T0: POST creates note, TTL 30 minutes
T1: GET note, remaining TTL 20 minutes
T2: GET note, remaining TTL 5 minutes
T3: Redis expires key
T4: GET note -> Mono.empty -> HTTP 404
```

`GET` does not automatically renew TTL. This is **fixed expiration** from write time.

If **sliding expiration** is desired for suitable data, refresh TTL on access. However, issuing `GET` and `EXPIRE` as two separate commands is not atomic; in some cases it races with deletes or rewrites. For strict requirements, use a supporting command or Lua script to read and extend on the same server/slot.

Do not apply sliding TTLs blindly without considering:

- Keys surviving forever due to continuous reads.
- Absolute lifetime requirements.
- Risk of `GET` improperly extending session/lock lifetimes against policy.
- Cost of an extra write command on every read.
- Redis Cluster slot and script semantics.

In production, storing critical resources solely in Redis with eviction/TTL requires careful durability evaluation. `201 Created` in the example confirms `SET` succeeded, **not that data is guaranteed to survive every failover or host loss**.

## 14. Difference Between Redis Miss and Redis Error in Reactive APIs

Suppose you write:

```java
Mono<Note> noteMono = redis.opsForValue()
        .get(key)
        .flatMap(this::decode);
```

Three paths:

```text
Redis GET succeeds, JSON present:
    onNext(json) -> decode -> onNext(Note)

Redis GET succeeds, key absent:
    onComplete -> Mono.empty

Redis timeout / connection failure:
    onError(error) -> Mono.error(error)
```

Mistake:

```java
return redis.opsForValue()
        .get(key)
        .onErrorResume(error -> Mono.empty())
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)));
```

This returns `404` even when Redis times out, breaking HTTP response semantics and hiding outages.

### 14.1. Cache-Aside with a Source Database Differs

Suppose Redis is only a cache while products live in a database. A flow might be:

```text
GET cache
    |
    +--> HIT -> return immediately
    |
    +--> MISS -> call Reactive ProductSource
    |              |
    |              +--> Found     -> write cache TTL, return product
    |              +--> Not found -> business not found
    |
    +--> Redis ERROR -> dedicated policy:
                        bounded fallback or return 503
```

In this case, Redis errors may fall back to the database, **yet must be measured as ERROR**, not counted as MISS. If the source database also fails, never convert the source error into not-found.

Conceptual example (application-provided methods):

```java
Mono<ProductView> cacheRead =
        productCache.read(productId)
                .onErrorResume(
                        RedisConnectionFailureException.class,
                        error -> {
                            metrics.redisError();
                            return Mono.empty();
                        });

Mono<ProductView> response =
        cacheRead.switchIfEmpty(
                Mono.defer(() -> productSource.findById(productId)));
```

This is a **deliberately fail-open** cache-only policy. Scope `onErrorResume` strictly to `productCache.read` so it never swallows `productSource` errors. In production code, separate metrics for "source load from miss" vs "source load from Redis outage", or return an explicit stateful result type.

Never use this pattern for sessions, distributed locks, nonces, or access-control decisions without dedicated security design.

## 15. Complete Reactive Cache-Aside Must Handle Cache Writes Too

Another cache-aside pattern:

```java
public Mono<ProductView> loadAndCache(String id) {
    return productSource.findById(id)
            .flatMap(product ->
                    productCache.put(product)
                            .onErrorResume(
                                    RedisConnectionFailureException.class,
                                    error -> {
                                        metrics.redisWriteError();
                                        return Mono.empty();
                                    })
                            .thenReturn(product));
}
```

Here `productSource.findById` is the reactive database/source API, and `productCache.put` returns `Mono<?>` indicating write completion.

Meaning:

- The database/source is the source of truth.
- When caching is purely an optimization, a cache write failure need not fail a response already retrieved from the source.
- Never swallow database errors inside Redis's catch branch.
- If `put` times out, you may not know whether the cache wrote, yet the caller still gets the authoritative value from the source.
- When a product updates, design invalidation/TTL/versioning rather than relying solely on cache fills.

If data must never be stale, simple cache-aside is usually insufficient; read the authoritative source or design versioned/invalidated consistency.

## 16. Atomic Operations: Counters and Race Conditions

Redis offers atomic **single-key** commands like `INCR`. In reactive Spring Data Redis:

```java
public Mono<Long> incrementViews(
        ReactiveStringRedisTemplate redis,
        String productId) {

    String key = "demo:webflux:views:v1:" + productId;
    return redis.opsForValue().increment(key);
}
```

`increment` returns `Mono<Long>` emitting the new value once complete.

Do not replace with read-modify-write:

```java
// Unsafe under concurrent requests:
return redis.opsForValue().get(key)
        .map(Long::parseLong)
        .flatMap(old -> redis.opsForValue()
                .set(key, Long.toString(old + 1)));
```

Two requests can read the same old value and overwrite each other.

### 16.1. INCR Timeouts Require Attention

```text
Client sends INCR
        |
        v
Redis increments counter successfully
        |
        v
Connection drops before client receives reply
        |
        v
Mono.error(timeout)
```

Blindly retrying `INCR` can increment twice. A reactive chain does not grant exactly-once semantics. For sensitive business counters, use operation IDs, idempotency, or an appropriate transactional store.

### 16.2. Reactive @Transactional Does Not Span Redis + DB

`@Transactional` in an R2DBC application governs the reactive database transaction, **not an automatic distributed transaction across database and Redis**.

Updating DB and `SET`ting Redis can succeed on one side and fail on the other. For critical workflows, keep the database transaction as the source of truth and sync caches via an outbox or reconciliation mechanism.

Redis Lua scripts provide atomic check-and-write **within a single compatible node/slot**, yet do not roll back prior writes on runtime errors and do not provide transactions spanning multiple Redis Cluster primaries.

## 17. Bringing Flux into WebFlux: When Does It Fit?

`Mono` fits single GET/SET calls. `Flux` fits **multi-element streams**: key scans, event streaming, reading records, or aggregating multiple Redis operations.

Example fetching multiple IDs from a client in a reactive chain:

```java
public Flux<Note> findMany(
        NoteService service,
        Flux<String> ids) {

    return ids.flatMap(
            service::findById,
            8); // At most 8 concurrent inner subscriptions.
}
```

This is a service helper example, not a complete endpoint. Cap incoming ID counts, validate input, and never let clients trigger scans of millions of keys.

To preserve input ordering, use `concatMap`:

```java
return ids.concatMap(service::findById);
```

Trade-offs:

| Operator | Characteristics | Notes |
|---|---|---|
| `concatMap` | Sequential processing | Preserves order easily; potentially lower throughput |
| `flatMap(fn, n)` | Up to `n` concurrent inner subscriptions | May complete out of order |
| `flatMapSequential(fn, n)` | Concurrent execution, emits in source order | Buffers when early items are slow |

If a `findById` returns `Mono.empty()` for a missing key, `flatMap` emits nothing for that ID. Batch APIs may need per-ID wrapper objects with explicit HIT/MISS/ERROR statuses so callers do not mismatch returned counts against input IDs.

### 17.1. Backpressure Is Not Magic

Reactive Streams let downstreams signal demand. However, a Redis server does not automatically pause producing events just because a browser reads slowly, especially with Pub/Sub.

Enforce bounds on:

- Concurrent requests to Redis.
- Batch sizes.
- Returned payload sizes.
- Buffer memory.
- Timeouts and cancellation policies.
- Unbounded/infinite publishers.

Never call `collectList()` on an infinite `Flux` or huge key list expecting WebFlux to protect memory automatically.

## 18. SSE and Redis Pub/Sub: An Extension Path

A WebFlux API can stream Server-Sent Events (SSE) backed by Redis Pub/Sub:

```text
Publisher
   |
   v
Redis PUBLISH updates
   |
   v
Reactive Pub/Sub subscription
   |
   v
Flux<event>
   |
   v
GET /api/events (text/event-stream)
   |
   v
Browser EventSource
```

Spring Data Redis provides a reactive Pub/Sub listener container capable of receiving messages as a `Flux` per version/API support.

An SSE handler can return:

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return eventSource.receiveUpdates()
            .map(text -> ServerSentEvent.<String>builder()
                    .data(text)
                    .build());
}
```

`eventSource.receiveUpdates()` represents an application bean backed by a reactive Redis Pub/Sub subscription, not a built-in Spring Data Redis API of that name.

### 18.1. Limits of Redis Pub/Sub

- Messages published while a subscriber is disconnected can be lost.
- Standard Pub/Sub lacks consumer groups, PELs, ACKs, and replay.
- Slow HTTP clients do not turn Redis Pub/Sub into a durable backpressured queue.
- HTTP subscription cancellations must be handled to avoid leaking subscriptions/resources.
- Many simultaneous HTTP listeners increase load; use a shared subscription fan-out strategy.
- Never use Pub/Sub as the sole source for audits, transactions, or mandatory events.

If the API needs replay on reconnect, consider Redis Streams or a durable event store/broker, mapping into a controlled `Flux`.

## 19. Reactive Redis Streams with WebFlux

Redis Streams suit use cases requiring persisted events, consumer group work distribution, and ACKs better than Pub/Sub.

Spring Data Redis offers reactive stream APIs, including `ReactiveStreamOperations` and receiver components per your version.

Application flow:

```text
Producer
    |
    v
XADD stream:orders:v1
    |
    v
Redis Stream
    |
    v
Consumer group read
    |
    v
Flux<Record>
    |
    v
Business handler (reactive)
    |
    v
Commit completion
    |
    v
XACK
```

Conceptual composition pattern:

```java
receiver.receive(
        Consumer.from(group, consumerName),
        StreamOffset.create(
                stream, ReadOffset.lastConsumed()))
    .concatMap(record ->
        processBusiness(record)
                .then(acknowledge(record)));
```

Here `receiver`, `processBusiness`, and `acknowledge` are components implemented against real APIs, not a complete program. Use `concatMap` to serialize processing and ACK order when required.

Key properties to uphold:

- **Reading does not equal ACKing.**
- Delivered unacknowledged messages remain in the PEL.
- Worker crashes before ACK require pending recovery.
- Crashes after database commit and before ACK cause redelivery, requiring idempotent handlers.
- `ReadOffset.lastConsumed()` reads new messages without claiming pending items from dead consumers.
- Reactive cancellation does not clear the PEL or roll back business side effects.
- Stream TTL/retention/trimming must not delete payloads before recovery windows if durability is required.

For this lesson's simple notes API, Streams are unnecessary. Choose Streams only when asynchronous work and replay are genuine business needs.

## 20. Redis Cluster and Reactive Connections

When scaling Redis to a Cluster, each key belongs to one of 16,384 hash slots. Cluster-aware reactive Lettuce routes normal single-key commands automatically:

```text
ReactiveStringRedisTemplate
           |
           v
Lettuce Cluster client
           |
    Compute slot from key
           |
    +------+------+------+
    |             |      |
    v             v      v
Primary A    Primary B  Primary C
```

Using `Mono`/`Flux` does not remove Redis Cluster constraints:

- Multi-key commands may require same hash slots or driver-specific splitting.
- Multi-key Lua scripts must respect slot boundaries; there are no atomic transactions across primaries.
- `MOVED`/`ASK` redirects occur during resharding.
- An unavailable node impacts keys in slots it owns.
- Replica reads may return stale data due to asynchronous replication.
- Driver topology refresh and retries must be configured and tested.
- Pinging one seed node does not guarantee all slots are healthy.

Example seed-node configuration with supporting Spring Boot properties:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a.internal:6379
          - redis-b.internal:6379
          - redis-c.internal:6379
        max-redirects: 5
      timeout: 2s
```

Addresses are illustrative. In Cluster mode, ensure all advertised Redis node endpoints have reachable private addresses and matching TLS/ACL setup.

This lesson's notes store each object in **one key**, avoiding multi-key transactions. If expanding to multiple keys per aggregate, hash tags can co-locate keys on one slot while watching for load skew.

## 21. Timeouts, Retries, and Cancellation in Reactive I/O

An endpoint waiting on Redis cannot wait forever. Set deadlines aligned with HTTP budgets and command timeouts.

Example timeout inside a reactive chain:

```java
return service.findById(id)
        .timeout(Duration.ofSeconds(2))
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND)));
```

Distinguish:

- `Mono.empty()` when Redis confirms the key is absent → can return `404`.
- `TimeoutException` from Reactor `timeout` → error, not a miss.
- Lettuce/connection timeout → also an error, with a different exception class.
- Timeouts do not prove a write command did not apply.

### 21.1. Retry Only Appropriate Errors

For idempotent `GET`s, brief retries on transient errors can help. Never put an unbounded:

```java
.retry()
```

on a high-traffic API. It can create infinite retry storms that crush Redis during incidents.

A bounded pattern filters exceptions and uses backoff, e.g.:

```java
return redis.opsForValue()
        .get(key)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                        .filter(this::isTransientRedisFailure));
```

`isTransientRedisFailure` is an application-defined error classifier; never treat JSON schema errors, ACL `NOPERM`, or `WRONGTYPE` as transient.

For `SET` in this exercise, resending the same key and value may be relatively safe in certain scenarios, yet still alters TTL and could overwrite concurrent updates. For `INCR`, side-effecting Lua, or `XADD`, retrying after timeout risks duplicate side effects. **Do not apply the same retry policy to every command.**

### 21.2. Cancellation When Clients Disconnect

HTTP clients can abort requests mid-command. Reactor cancels the application-side subscription, yet if the command already reached Redis, the server can still complete it.

```text
POST /api/notes
    |
    v
Client sends SET to Redis
    |
    v
Browser disconnects
    |
    v
Publisher is canceled
    |
    v
Redis may still have saved the Note
```

Do not infer that because the client never received `201`, Redis did not create the note. When preventing duplicates across retries is required, use a stable client idempotency key with an atomic Redis or database mechanism.

## 22. WebFlux Does Not Replace Authentication and Security

A reactive API still needs the same core protections:

- Spring Security WebFlux filter chain when endpoints require user authentication.
- Per-resource and per-tenant authorization.
- Request/payload size validation.
- Appropriate rate limiting.
- Private networking, TLS, and Redis ACLs.
- Never logging session IDs, JWTs, passwords, or sensitive data.
- Never exposing a generic Redis command-execution endpoint to the Internet.

The notes API in this lesson omits authentication to focus on Reactive Redis. In production, never deploy this prototype unmodified as a private multi-user notes store.

If data is scoped by tenant/user, keys should embed an authenticated scope per policy, e.g.:

```text
tenant:team-7:notes:v1:<note-uuid>
```

Never **trust a client-supplied tenant ID** without authorization. Extract tenant/principal from the verified security context to prevent cross-tenant access on GET/DELETE by ID.

### 22.1. Reactive SecurityContext Differs from Standard ThreadLocal

In WebFlux, the Reactor Context propagates security state along the reactive chain. Never assume `ThreadLocal`-backed `SecurityContextHolder` inside reactive handlers behaves like a Servlet request thread.

When principal data is needed, use reactive WebFlux/Spring Security APIs such as injecting `Principal`/`Mono<Principal>` into controller methods or reading `ReactiveSecurityContextHolder` inside the chain.

Never treat a user ID passed as a query parameter as authorization proof merely because it flows through a `Mono`.

## 23. Layered Observability for API and Redis

A reactive system needs dedicated metrics for HTTP, Redis, and business layers.

| Metric | Meaning |
|---|---|
| HTTP requests/s and error rate | Overall serving health |
| HTTP p50/p95/p99 | User-perceived latency |
| Redis GET/SET/DEL latency | Redis command latency |
| Redis connection failures | Network, TLS, auth, and reconnect errors |
| Redis timeout count | Commands exceeding deadlines |
| Redis cache hit/miss | Cache effectiveness when Redis is a cache |
| Redis invalid payload count | Corrupt JSON/schema mismatches |
| Redis command failures by type | Distinguish network issues vs wrong types |
| Event-loop delay | Indicator of accidental blocking or heavy CPU work |
| Active requests/subscriptions | Concurrency pressure |
| Reactor operator errors/cancellations | Failed or canceled reactive chains |
| Redis Cluster redirects/slot errors | Topology churn |
| Redis memory/evictions | Risk of data loss before TTL |
| Separate HTTP 404 and 503 counts | Never conflate missing resources with infra failures |

With Spring Boot Actuator, enable the Redis health indicator if supported by auto-configuration, while separating readiness and liveness:

- Liveness: whether the process is alive or wedged.
- Readiness: whether the instance can accept new traffic.
- Redis health: whether one dependency is reachable; it does not prove every business flow works.

If Redis is mandatory storage for the notes API, readiness can depend on Redis. If Redis is an optional cache with safe fallback, avoid marking every pod unready during a Redis outage.

### 23.1. Do Not Let Health Checks Generate Heavy Load

`GET /actuator/health/readiness` should never:

- `SCAN` the entire Redis keyspace.
- Create/delete many keys.
- Publish a Pub/Sub event and wait for a subscriber.
- Probe all Redis Cluster nodes with hundreds of commands.
- Open a new connection factory.
- Run heavy database queries to verify cache consistency.

Health checks run frequently; keep them lightweight and strictly bounded by timeouts.

## 24. Testing the API with WebTestClient and Real Redis

Mocking the service tests the controller, yet does not prove `SET` with TTL, Redis nil, `DEL`, and serialization work. For integration tests, use **Testcontainers** with real Redis.

Example:

```java
package com.example.rediswebflux;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import com.example.rediswebflux.note.Note;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NoteApiIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.data.redis.host",
                REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    WebTestClient client;

    @Test
    void canCreateReadAndDeleteNote() {
        EntityExchangeResult<Note> created =
                client.post()
                        .uri("/api/notes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of("text", "Hello Redis"))
                        .exchange()
                        .expectStatus().isCreated()
                        .expectBody(Note.class)
                        .returnResult();

        Note note = created.getResponseBody();
        assertNotNull(note);

        client.get()
                .uri("/api/notes/{id}", note.id())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.text")
                .isEqualTo("Hello Redis");

        client.delete()
                .uri("/api/notes/{id}", note.id())
                .exchange()
                .expectStatus().isNoContent();

        client.get()
                .uri("/api/notes/{id}", note.id())
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void missingValidUuidReturnsNotFound() {
        client.get()
                .uri("/api/notes/{id}",
                        "00000000-0000-0000-0000-000000000001")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void invalidBodyReturnsBadRequest() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("text", " "))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

Adjust imports and auto-configuration annotations per Spring Boot version and test package layout. The test must run inside a Spring Boot context containing `NoteService` and `NoteController`, with Docker/Testcontainers permitted to launch containers.

### 24.1. Why Use Real Redis?

A mocked `ReactiveStringRedisTemplate` can stub:

```java
Mono.just("json")
Mono.empty()
Mono.error(new RuntimeException("Redis failed"))
```

yet **does not verify**:

- Actual key serialization.
- Redis applying TTL.
- Accurate Redis String round-trips.
- Deleting and re-reading keys.
- ACLs/connections/TLS.
- Expected command execution.
- Data isolation between tests.

Testcontainers closes that gap in integration tests. You do not need real Redis for every trivial unit test; combine both levels.

## 25. Testing Reactor with StepVerifier

For services returning `Mono`/`Flux`, `StepVerifier` directly asserts signal sequences:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.create(Mono.just("READY"))
        .expectNext("READY")
        .verifyComplete();

StepVerifier.create(Mono.<String>empty())
        .verifyComplete();

StepVerifier.create(
                Mono.<String>error(
                        new IllegalStateException("Redis unavailable")))
        .expectError(IllegalStateException.class)
        .verify();
```

This illustrates **testing Reactor signal semantics**. To test real services, mock Redis operations or use Redis Testcontainers.

### 25.1. Scenarios Worth Testing

| Scenario | Expected Behavior |
|---|---|
| GET existing key | `Mono<Note>` emits Note and HTTP 200 |
| GET missing key | `Mono.empty()` in service, HTTP 404 |
| Redis connection refused | `onError`, HTTP 503/5xx per policy |
| Redis key holds invalid JSON | Decode error, never returns 404 |
| SET with TTL | Redis holds key with positive TTL |
| Wait for TTL expiration | GET becomes empty/404 |
| DELETE same ID twice | First true/204, second false/404 |
| Blank input text | HTTP 400, no Redis write |
| Malformed UUID path | HTTP 400 |
| Many concurrent POSTs | Distinct IDs generated without blocking event loop |
| Cancel mid-SET | Do not assume command never applied |
| Retry INCR after timeout | Idempotency policy tested |
| Redis Cluster failover | Errors/reconnects never masquerade as misses |
| Server shutdown | No leaked subscriptions or connections |

For TTL tests, avoid `Thread.sleep(100)` with overly tight durations that cause flaky tests. Pick an appropriate test TTL and use bounded polling/deadlines to confirm expiration.

### 25.2. Inspecting TTL Directly in Integration Tests

As an extra check, inject `ReactiveStringRedisTemplate` into the test, create a note, and verify:

```java
StepVerifier.create(
        redis.getExpire(
                "demo:webflux:notes:v1:" + createdNote.id()))
        .assertNext(ttl -> {
            // Freshly created TTL should be > 0 and <= 30 minutes.
            org.junit.jupiter.api.Assertions.assertTrue(
                    ttl.compareTo(Duration.ZERO) > 0);
            org.junit.jupiter.api.Assertions.assertTrue(
                    ttl.compareTo(Duration.ofMinutes(30)) <= 0);
        })
        .verifyComplete();
```

This is an auxiliary assertion assuming `redis` and `createdNote` are already set up in the test. It does not replace HTTP tests and does not guarantee keys survive all 30 minutes if Redis evicts or loses data.

## 26. Testing Network Failures, Deserialization, and Backpressure

An API may work when Redis is healthy and behave incorrectly when Redis disconnects.

Test scenario:

1. Create a note while Redis is healthy.
2. Stop test Redis or block container traffic via a test harness.
3. Send GET for that ID again.
4. Confirm the response is not turned into `404` simply because Redis is unavailable.
5. Verify timeouts are bounded so requests do not hang indefinitely.
6. Restore Redis and observe reconnection.
7. If the container was recreated, recognize Redis data was wiped: GET now returns `404` because the key is genuinely missing in the fresh store, unlike a connection failure.

To test malformed JSON, write an invalid value to a test key, then call GET and verify the handler does not return 404:

```bash
redis-cli SET \
  demo:webflux:notes:v1:00000000-0000-0000-0000-000000000001 \
  'not-valid-json' EX 120
```

Use an isolated test Redis. Never tamper with production keys to simulate deserialization errors.

### Concurrency Testing

Send many concurrent `POST` requests with `WebTestClient` or a load-testing tool and measure:

- HTTP throughput and p95/p99 latency.
- Redis connection and command latency.
- Success rate and created key count.
- JVM heap and event-loop delay.
- Error rate when Redis hits limits.
- Impact of accidentally introducing a blocking call.

Never assume "reactive is faster" merely because `block()` is absent. Compare under identical workloads, payloads, network topologies, and memory budgets.

## 27. Operating in Kubernetes and Graceful Shutdown

When deploying WebFlux + Redis, applications must shut down cleanly:

```text
Pod startup
    |
    v
Spring context creates ReactiveRedisTemplate/Lettuce
    |
    v
Readiness reported per dependency policy
    |
    v
Accepts HTTP requests
    |
    v
Pod receives SIGTERM
    |
    v
Stops accepting new requests
    |
    v
Lets in-flight requests finish within deadline
    |
    v
Cancels/closes background subscriptions if any
    |
    v
Spring closes connection factory
    |
    v
Process exits
```

Sample configuration:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s

management:
  endpoint:
    health:
      probes:
        enabled: true
```

If Redis is mandatory for every endpoint, include the Redis health contributor in the readiness group per your Boot version. If it is only a cache with fallback, configure probes so a Redis outage does not mark every pod unready at once.

**Spring Boot graceful shutdown is only part of the picture.** Background subscriptions like Pub/Sub/SSE or Redis Stream consumers opened by the application must be tracked and closed cleanly by lifecycle hooks; never spawn detached `subscribe()` calls hoping JVM exit cleans up immediately.

### 27.1. Avoid Closing LettuceConnectionFactory in Handlers

Never call `destroy()` or `close()` on the shared connection factory after each HTTP request. It is an infrastructure bean managed by the Spring context; closing it early breaks concurrent requests.

For manually constructed native clients or low-level connections, the creator must release them under clear ownership and proper ordering.

## 28. Common Pitfalls When Integrating WebFlux with Reactive Redis

| Mistake | Consequence | Fix |
|---|---|---|
| Calling `.block()` in a WebFlux controller | Ties up thread waiting on Redis; can stall event loop | Return `Mono`/`Flux` to WebFlux |
| Calling `.subscribe()` and returning success | HTTP responds before Redis finishes; errors detached | Compose publishers and return the chain |
| Using blocking `StringRedisTemplate` in reactive flows | Loses non-blocking I/O | Use `ReactiveStringRedisTemplate` |
| Treating `Mono.empty()` as a Redis outage | Returns error on normal missing keys | Distinguish misses from errors |
| `.onErrorResume(e -> Mono.empty())` for all errors | Redis timeouts turn into 404 | Fall back only on targeted errors per policy |
| Turning JSON `null` into a key miss | Violates data contract | Reject null/invalid payloads |
| Omitting TTL on temporary data | Keys accumulate, growing memory | Use `SET` with `Duration` |
| Uncoordinated separate `SET` and `EXPIRE` | Keys can persist without TTL | Use `SET` with expiration in one command |
| Blindly retrying `INCR`/`XADD` | Increments counters or creates events twice | Apply idempotency and targeted retry policies |
| Assuming `@Transactional` makes Redis + R2DBC atomic | Two stores can diverge on commit/error | Use authoritative DB + outbox |
| Unbounded `flatMap` concurrency | Spikes commands, connections, and buffers | Bound concurrency and backpressure |
| Calling `collectList()` on an unbounded `Flux` | Unbounded memory growth | Stream or process in bounded batches |
| Letting clients choose arbitrary Redis keys | Accesses wrong namespaces or sensitive data | Derive keys from validated IDs and scopes |
| Exposing public Redis ports | Data leaks and attack surface | Private network/TLS/ACLs |
| Mismatched serializers across apps | False misses or decode failures | Versioned serializers and schemas |
| Using Pub/Sub as a durable event log | Messages lost when subscribers are offline | Use Streams or a durable broker |
| Reading Redis replicas for critical sessions/locks | Stale reads | Choose matching consistency policies |
| Testing controllers only with mocks | Misses real Redis TTL/serialization bugs | Use `WebTestClient` + Testcontainers |
| Pinging only one Redis Cluster node | Misses failures in other slots | Monitor cluster metrics and test topology |
| Not measuring event-loop blocking | Unexplained p99 latency spikes | Add observability and profiling |

## 29. Exercise Completion Checklist

**Application and API**

- Spring Boot runs WebFlux with the reactive Redis dependency.
- `ReactiveStringRedisTemplate` is injected cleanly.
- `POST` writes JSON with a TTL and returns `201` only when `SET` is confirmed.
- `GET` returns the Note or HTTP `404` accurately on Redis nil.
- `DELETE` confirms the deleted key count.
- Inputs and IDs are validated.
- No manual `block()` or `subscribe()` calls exist in controllers.

**Reactive Semantics**

- `Mono.just`, `Mono.empty`, and `Mono.error` are clearly distinguished.
- `flatMap` composes asynchronous Redis operations.
- `switchIfEmpty` handles only genuinely empty signals.
- Error handlers do not blindly swallow Redis failures.
- Timeouts and retries follow policy without duplicating side effects.
- Concurrency limits guard batch/`Flux` paths.

**Redis Data**

- Key namespaces carry appropriate versions and scopes.
- Serializers and lifetimes are explicitly defined.
- TTLs are not extended unintentionally.
- Invalid JSON is treated as a data error, not a miss.
- Redis Cluster/Sentinel/TLS/ACLs are prepared for production transitions.
- TTL-bound Redis data is not treated as durable transactional storage when strong durability is required.

**Testing and Operations**

- `curl` create/read/delete flows succeed.
- `WebTestClient` + Testcontainers test real Redis.
- Missing keys, invalid input, Redis failures, malformed JSON, and TTLs are tested.
- Readiness/liveness probes reflect Redis's role.
- HTTP/Redis latency and error metrics are instrumented.
- WebFlux event loops are free of prolonged blocking calls.
- Connection factories and subscriptions clean up properly on shutdown.

## 30. Summary

Integrating reactive Redis into a WebFlux API is more than swapping `RedisTemplate` for `ReactiveRedisTemplate`. The essential part is **building an observable asynchronous pipeline with sound error management**:

1. **Controllers return `Mono`/`Flux`**, letting WebFlux subscribe and manage lifecycles.
2. **Reactive Lettuce performs Redis I/O** without blocking threads waiting for replies.
3. **Redis nil differs from Redis failure.** `Mono.empty()` expresses absent keys, whereas `onError` must be handled as an error.
4. **Serialization and TTL belong to the data contract.** An existing key with corrupt payload is not a miss; temporary notes need `SET` with expiry.
5. **Redis commands are not system-wide transactions.** Retries, cancellations, and DB/Redis dual writes need explicit idempotency/consistency policies.
6. **`Flux` does not erase resource limits.** Enforce concurrency caps, backpressure, and payload limits.
7. **Test against real Redis.** `WebTestClient` + Testcontainers verify `GET`/`SET`/`DELETE`/TTL behavior and error paths.
8. **Deployments must still be secure.** Private Redis, TLS/ACLs, readiness probes, graceful shutdown, and observability matter just as much as reactive code.

For this practice app, `ReactiveStringRedisTemplate`, JSON Strings, and `Mono<Note>` make the flow from HTTP to Redis easy to inspect. As you evolve it into a production system, continue separating **cache vs primary datastore**, choosing fitting serialization and durability, and treating reactive composition as a tool to govern asynchronous work—not a substitute for sound business architecture.
