# ReactiveRedisTemplate and ReactiveRedisConnectionFactory

## 1. Where the two components sit in the Spring Data Redis architecture

When a Spring WebFlux application needs to read or write Redis **without blocking execution threads while waiting for I/O** (non-blocking I/O), Spring Data Redis provides two central components:

- **ReactiveRedisTemplate<K, V>**: a high-level API for applications to operate on keys/values, hashes, sets, sorted sets, lists, streams, and other Redis data structures under the Reactor model.
- **ReactiveRedisConnectionFactory**: an infrastructure contract that creates/provides **reactive Redis connections** for the data-access layer. It decouples Redis-consuming code from driver details and connection setup.

The architectural relationship can be visualized as follows:

~~~text
HTTP request / event / reactive pipeline
               |
               v
      Controller / Service
          Mono / Flux
               |
               v
 ReactiveRedisTemplate<K, V>
   - Redis operations
   - key/value serialization
   - error & result mapping
               |
               v
 ReactiveRedisConnectionFactory
   - provides reactive connections
               |
               v
        Lettuce Redis driver
               |
          Redis server
~~~

Normally **services should depend on the template** rather than managing connections, data buffers, and serializers manually. The **connection factory** is usually configured once at the application layer and injected by Spring into the template.

The names look similar, yet their roles differ: the factory answers *“where do we obtain a reactive connection to Redis?”*, while the template answers *“which API do we use to operate on Redis data, which serializer applies, and how are Reactor results returned?”*.

## 2. What does reactive mean here?

In Spring Data Redis, reactive APIs return **Project Reactor** types:

| Type | Meaning | Example Redis operation |
|---|---|---|
| **Mono<T>** | Stream emitting at most one result then completing, completing empty, or failing | Reading a key: **Mono<String>** |
| **Mono<Boolean>** | Single result indicating operation success per API semantics | **SET** a value |
| **Mono<Long>** | Single numeric value, such as a count or counter | **INCR**, **DEL** |
| **Flux<T>** | Stream capable of emitting multiple items | **SCAN** multiple keys, reading item streams |

Example:

~~~java
Mono<String> value = reactiveStringRedisTemplate
    .opsForValue()
    .get("profile:42:name");
~~~

Here **value** is a description of a read operation as a **Mono**. Creating this variable does not mean the application has synchronously waited and fetched the data. With typical cold publishers for Redis operations, the command is triggered only when the pipeline has a subscriber.

~~~java
Mono<String> result = reactiveStringRedisTemplate
    .opsForValue()
    .get("profile:42:name")
    .map(String::toUpperCase)
    .defaultIfEmpty("NO NAME YET");

// Do not call block() in the WebFlux request-processing path.
// Return the Mono to WebFlux so the framework subscribes and sends the HTTP response.
return result;
~~~

As the request runs, Reactor passes results onward through operators like **map**, **flatMap**, **switchIfEmpty**, and **onErrorResume** without forcing the request-handling thread to sit idle waiting synchronously on a Redis response.

**Non-blocking** does not mean Redis executes every command in parallel, nor does it mean individual operations are always faster. The primary benefit is more efficient thread utilization while waiting on I/O when many requests are in flight.

### Difference between imperative and reactive

~~~java
// Imperative: reading returns the value directly; the call waits for I/O to finish.
String name = stringRedisTemplate.opsForValue().get("profile:42:name");

// Reactive: reading returns a publisher describing a future result.
Mono<String> namePublisher = reactiveStringRedisTemplate
    .opsForValue()
    .get("profile:42:name");
~~~

**StringRedisTemplate** and **ReactiveStringRedisTemplate** are not just two names for identical behavior. One exposes a synchronous API, while the other provides a Reactor API backed by reactive infrastructure.

## 3. ReactiveRedisConnectionFactory: the connection boundary

**ReactiveRedisConnectionFactory** is a Spring Data Redis interface. It provides connections below the template layer so Redis commands can execute under the reactive model.

A familiar implementation is **LettuceConnectionFactory**. When using Lettuce, the same factory type can serve both imperative and reactive Redis APIs because Lettuce supports asynchronous/non-blocking connections.

At the design layer:

1. **Spring Boot** reads Redis configuration and manages connection beans when auto-configuration applies.
2. **LettuceConnectionFactory** holds server configuration, authentication, topology, and client resources.
3. **ReactiveRedisTemplate** receives the factory and serialization context via its constructor.
4. **Services** inject the template and compose operations into **Mono/Flux** pipelines.

Never create a new **LettuceConnectionFactory** inside every service method or per request. The factory and its associated connection resources should be managed by Spring for the application lifecycle.

### Why not inject connections directly into every service?

Connection-level APIs are useful when you need low-level operations not wrapped by the template or when building a specialized infrastructure adapter. When working directly at that level, however, application code must handle codecs, command results, session/resource management, and low-level error rules itself.

The template already provides a consistent abstraction for most everyday data operations. Therefore, business services typically only need to depend on **ReactiveRedisTemplate<K, V>** or **ReactiveStringRedisTemplate**.

### Choosing Lettuce for Reactive Redis

With Spring Data Redis, **Lettuce** is the standard driver choice supporting reactive execution. Do not assume just any **RedisConnectionFactory** automatically works as a **ReactiveRedisConnectionFactory**: both driver and implementation must genuinely support the reactive contract.

When an application uses Redis Cluster or Sentinel, the factory also coordinates topology and driver settings, though that does not turn multiple Redis nodes into a single distributed transaction.

## 4. Configuring a Spring Boot application

In a Spring Boot project using Gradle, you can declare the starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
}
~~~

This starter brings Spring Data Redis and the compatible driver into the dependency graph. Reactor must also be present, typically pulled in already by WebFlux or the reactive starter.

Example connection configuration for a local development Redis instance:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

In production environments, also configure passwords/TLS, Cluster or Sentinel topology, timeouts, monitoring, and network access controls according to operational architecture. Never embed credentials in source code.

When auto-configuration applies and bean/dependency conditions are met, Spring Boot provides the Lettuce factory and standard Redis templates automatically. Many applications therefore do not need to declare a connection factory manually.

A service working with strings can inject **ReactiveStringRedisTemplate** directly:

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class VisitCounterService {
    private final ReactiveStringRedisTemplate redis;

    public VisitCounterService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> increment(String pageId) {
        return redis.opsForValue().increment("page:views:" + pageId);
    }

    public Mono<String> readRaw(String pageId) {
        return redis.opsForValue().get("page:views:" + pageId);
    }
}
~~~

**increment** is a single increment command on Redis, so it avoids lost updates caused by executing **GET → compute → SET** in Java. However, the API can still emit an error if Redis is unavailable or the stored value is a non-integer string.

## 5. ReactiveRedisTemplate: typed data-access abstraction

**ReactiveRedisTemplate<K, V>** separates two layers of responsibility:

**Data-operations layer**

~~~java
redis.opsForValue();
redis.opsForHash();
redis.opsForList();
redis.opsForSet();
redis.opsForZSet();
redis.opsForStream();
~~~

**Serialization layer**

- Java keys are converted to bytes sent to Redis.
- Java values are converted to bytes according to configured serializers.
- Data returned from Redis is decoded into the expected Java type.

Redis does not store native Java objects. **Strings**, JSON, and binary formats are all represented as bytes. The generic parameters **<K, V>** do not automatically guarantee that stored Redis data matches the serializer; schemas and formats must still be aligned across clients.

### How do ReactiveStringRedisTemplate and ReactiveRedisTemplate differ?

**ReactiveStringRedisTemplate** is a convenient variant for string keys and values, using string serializers accordingly. It fits counters, markers, tokens, or small values that the service handles directly as Strings.

**ReactiveRedisTemplate<K, V>** fits when the application maps values to a DTO or other custom type via **RedisSerializationContext**.

| Criterion | ReactiveStringRedisTemplate | ReactiveRedisTemplate<K, V> |
|---|---|---|
| Typical key/value | String/String | Depends on serializers and generics |
| Configuration | Usually uses standard auto-configured bean | Often requires configuring a custom context |
| Common use cases | Counters, text keys, flags | JSON objects, domain data |
| Return types | Mono/Flux | Mono/Flux |
| Connection source | ReactiveRedisConnectionFactory | ReactiveRedisConnectionFactory |

Both templates are application-layer abstractions; neither replaces the connection factory.

## 6. Creating a ReactiveRedisTemplate with a custom serializer

Suppose session data is stored in Redis as JSON with string keys. You can define a DTO:

~~~java
public record SessionPayload(
    String userId,
    String displayName
) {}
~~~

Then create the template:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ReactiveSessionRedisConfig {

    @Bean
    public ReactiveRedisTemplate<String, SessionPayload> sessionRedisTemplate(
            ReactiveRedisConnectionFactory connectionFactory) {

        var keySerializer = new StringRedisSerializer();
        var valueSerializer =
            new Jackson2JsonRedisSerializer<>(SessionPayload.class);

        RedisSerializationContext<String, SessionPayload> context =
            RedisSerializationContext
                .<String, SessionPayload>newSerializationContext(keySerializer)
                .value(valueSerializer)
                .build();

        return new ReactiveRedisTemplate<>(connectionFactory, context);
    }
}
~~~

In this configuration:

1. **ReactiveRedisConnectionFactory** defines how the template obtains reactive connections.
2. **StringRedisSerializer** turns String keys into bytes that can be inspected and queried in Redis.
3. **Jackson2JsonRedisSerializer** converts **SessionPayload** to JSON and reads it back into that target type.
4. **RedisSerializationContext** supplies the serializers used by the template.
5. **ReactiveRedisTemplate** pairs the connection factory with the serialization context to execute Redis operations.

This example sets only the value serializer because the service below uses **opsForValue()**. If you operate on hashes, explicitly configure **hash key** and **hash value** serializers as well; if the application stores multiple DTOs or data formats, design key/serializer separation accordingly.

JSON improves readability and cross-language interoperability, yet you still must manage schema changes, data types, cross-version compatibility, and sensitive fields. Never assume the default Java serializer on every template is JSON.

### Using the template in a service

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SessionStore {
    private final ReactiveRedisTemplate<String, SessionPayload> redis;

    public SessionStore(
            ReactiveRedisTemplate<String, SessionPayload> redis) {
        this.redis = redis;
    }

    public Mono<Boolean> save(
            String sessionId,
            SessionPayload payload,
            Duration ttl) {
        return redis.opsForValue()
            .set("session:" + sessionId, payload, ttl);
    }

    public Mono<SessionPayload> find(String sessionId) {
        return redis.opsForValue().get("session:" + sessionId);
    }

    public Mono<Long> delete(String sessionId) {
        return redis.delete("session:" + sessionId);
    }
}
~~~

In **save**, TTL is passed into the same **SET** operation rather than creating the value first and calling **EXPIRE** in a separate step. **find** emits **Mono.empty()** when the key does not exist; that is a normal empty signal, distinct from a Redis connection error.

## 7. Composing Redis operations into a reactive pipeline

Reactor operators express control flow clearly without calling **block()**:

~~~java
public Mono<SessionPayload> updateDisplayName(
        String sessionId,
        String newName) {

    return redis.opsForValue()
        .get("session:" + sessionId)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Session not found")))
        .flatMap(oldValue -> {
            SessionPayload updated =
                new SessionPayload(oldValue.userId(), newName);

            return redis.opsForValue()
                .set("session:" + sessionId, updated, Duration.ofMinutes(30))
                .thenReturn(updated);
        });
}
~~~

Each request follows this flow:

~~~text
get(key) ──► Mono<SessionPayload>
                │
                ├─ empty ─► not-found error
                │
                └─ value ─► create new SessionPayload
                               │
                               ▼
                       set(key, updated, ttl)
                               │
                               ▼
                       Mono<SessionPayload>
~~~

**Race-condition warning:** this example demonstrates composing publishers, **not an atomic update** between GET and SET. If two requests read and update the same session concurrently, the later write can overwrite the earlier update. When business logic requires checking and writing as an indivisible unit, design a **Lua script / Redis Function** or an appropriate conditional mechanism such as **WATCH + MULTI/EXEC**, respecting reactive API support and your Redis deployment scope.

Using **flatMap** only orders data dependencies within a single subscription; it does not create distributed locks, transactions, or serialization across separate subscribers.

### Example exposing a Mono via WebFlux

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/sessions")
public class SessionController {
    private final SessionStore store;

    public SessionController(SessionStore store) {
        this.store = store;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<SessionPayload>> find(
            @PathVariable String id) {

        return store.find(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
~~~

The controller returns the publisher and lets WebFlux subscribe according to the HTTP request lifecycle. Never call **subscribe()** manually inside a controller or service just to “make Redis run.”

## 8. Publisher lifecycle, subscription, and backpressure

A common mistake is:

~~~java
Mono<Boolean> action =
    reactiveStringRedisTemplate.opsForValue().set("flag:ready", "yes");
~~~

If **action** is merely created and discarded without any subscriber consuming the publisher, the operation generally will not execute. You must **return action** to the framework, compose it into another pipeline via **then/flatMap**, or ensure a managed subscriber exists when subscribing explicitly.

~~~java
public Mono<String> writeThenRead() {
    return reactiveStringRedisTemplate.opsForValue()
        .set("flag:ready", "yes")
        .then(reactiveStringRedisTemplate.opsForValue().get("flag:ready"));
}
~~~

**then** waits for the write publisher to complete successfully before subscribing to the read publisher. By contrast, creating two independent Monos and returning only one of them does not cause the other publisher to run.

In the Reactor model:

- **Subscription** triggers the pipeline.
- **Cancellation** signals that results are no longer wanted; cancellation must not be treated as rolling back a mutation already executed by Redis.
- **Backpressure** lets subscribers request appropriate demand when consuming a **Flux**, though it does not turn every Redis command into an instantly pausable or reversible source once sent. Consider memory, in-flight commands, and how the driver reads/emits responses.
- **Concurrency** introduced by operators such as **flatMap** can dispatch many Redis operations at once; request volume and key hot-spotting still require sensible bounds.

Example scanning keys as a stream:

~~~java
import org.springframework.data.redis.core.ScanOptions;
import reactor.core.publisher.Flux;

public Flux<String> scanProfileKeys() {
    return reactiveStringRedisTemplate.scan(
        ScanOptions.scanOptions()
            .match("profile:*")
            .count(100)
            .build()
    );
}
~~~

**SCAN** iterates with a cursor, making it preferable to **KEYS** for retrieving keys on a large Redis instance. **COUNT** is only a hint for scan work per step, not a guaranteed batch size; scans can also surface duplicates or miss/reflect keys modified concurrently. For Cluster deployments, understand node scope and client scan support.

## 9. Errors, timeouts, and empty results

Distinguish at least three execution paths:

| State | Example | Approach |
|---|---|---|
| **Value present** | Successful GET | Map to DTO or HTTP 200 |
| **Empty** | Key absent, **Mono.empty()** | **switchIfEmpty** or **defaultIfEmpty** |
| **Error** | Redis disconnected, timeout, wrong data type | Handle via **onErrorMap/onErrorResume**, proper logs/metrics |

Example mapping missing data to a fallback:

~~~java
public Mono<String> nickname(String userId) {
    return reactiveStringRedisTemplate.opsForValue()
        .get("nickname:" + userId)
        .defaultIfEmpty("anonymous");
}
~~~

If Redis fails with a connection error, **defaultIfEmpty** does not swallow the error; it only handles publishers that complete without emitting a value.

Example bounding wait time at the reactive layer:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

public Mono<String> readWithTimeout(String key) {
    return reactiveStringRedisTemplate.opsForValue()
        .get(key)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
            error -> Mono.error(
                new IllegalStateException("Redis read timed out", error)));
}
~~~

A pipeline timeout bounds how long **the subscriber waits for a result**; if a write command already reached Redis, a client-side timeout or cancellation does not prove the command never executed. When automatically retrying commands with side effects, analyze idempotency, business rules, and duplicate handling.

In practice, configure timeouts deliberately on both the driver/connection and request pipeline; avoid using **onErrorResume** to replace every error with dummy data when doing so could mislead the application about storage state.

## 10. Transactions and atomicity in reactive Redis

Reactive execution does not change the fundamental atomicity properties of Redis commands. An **INCR** command remains an atomic server-side increment, while a reactive **get().flatMap(...set(...))** chain remains two independent commands.

Three categories of behavior are easily confused:

| Mechanism | Primary guarantee | What it does not guarantee |
|---|---|---|
| **Mono/Flux + flatMap/then** | Dependency ordering within a pipeline | Atomicity across multiple commands |
| **Single Redis command** | One command finishes without interleaving on the handling instance | Multi-step Java workflows |
| **MULTI/EXEC** | Redis executes queued commands contiguously without other clients interleaving | Rollback if one queued command errors at runtime |
| **WATCH + MULTI/EXEC** | Detects modified keys and aborts the transaction before EXEC | Success across retries; rollback on runtime errors |
| **Lua script / Redis Function** | Condition check and update in one server execution | Rollback after writes already executed before an error |

Reactive APIs do not make a method annotated with **@Transactional** automatically participate in a distributed transaction across Redis, a database, and a message broker. Transaction mechanisms, support at each Redis API layer, and connection lifecycles must be chosen and configured explicitly.

If a service needs “decrement stock only if sufficient inventory exists,” evaluate an atomic server-side operation; if a service only needs a counter, use **increment** instead of building complex transactions.

## 11. Common architectural pitfalls

### 11.1. Calling block() in a WebFlux processing chain

~~~java
// Avoid inside a controller or service running on an event loop:
String value = reactiveStringRedisTemplate
    .opsForValue()
    .get("key")
    .block();
~~~

**block()** turns waiting for the result into synchronous blocking, stalling threads and triggering Reactor rejections on non-blocking threads. Returning **Mono** or composing with reactive operators is usually the right choice.

### 11.2. Calling subscribe() and discarding the handle

~~~java
// Risks losing error handling and lifecycle tracking:
reactiveStringRedisTemplate.opsForValue()
    .set("flag", "ready")
    .subscribe();
~~~

The command runs detached from the result the caller awaits; errors may never reach the HTTP flow, and cancellation and tracing become harder to manage. For request-response flows, **return the Mono** so the caller/framework manages subscription.

### 11.3. Using inconsistent serializers

One template writes objects as JSON while another uses Java native serialization or a string serializer on the same key. The key may exist in Redis while deserialization fails or yields corrupted meaning. Align **key prefixes, serializers, value types, TTLs, and schema formats** across all consumers.

### 11.4. Treating reactive as guaranteeing atomicity

~~~java
return reactiveStringRedisTemplate.opsForValue()
    .get("stock")
    .flatMap(current -> {
        long remaining = Long.parseLong(current) - 1;
        return reactiveStringRedisTemplate.opsForValue()
            .set("stock", Long.toString(remaining));
    });
~~~

This snippet is non-blocking, yet still suffers from race conditions. Non-blocking I/O, template thread safety, and business atomicity are **three distinct properties**.

### 11.5. Using Redis Cluster without considering hash slots

When multi-key Redis commands or scripts are required, Cluster enforces hash-slot constraints. Keys like **cart:{user42}:items** and **cart:{user42}:total** can share a hash tag to co-locate in the same slot; intentional key design is a data-modeling responsibility, not something the template resolves automatically.

### 11.6. Using reactive Redis when the rest of the path is blocking

If a controller calls reactive Redis, immediately calls **block()**, and then runs JDBC or synchronous file I/O on the event loop, the application gains none of the intended architectural benefits. An effective reactive pipeline considers the controller, services, clients, and data stores end to end.

Not every system needs to become reactive. Choosing imperative vs. reactive should depend on overall application architecture and load characteristics; **ReactiveRedisTemplate** shines when the request path already uses Reactor/WebFlux or naturally integrates with reactive pipelines.

## 12. Service design and production operations

A maintainable structure:

~~~text
Spring Boot configuration
  ├─ Redis connection properties
  ├─ LettuceConnectionFactory
  │    └─ ReactiveRedisConnectionFactory
  └─ ReactiveRedisTemplate<String, DTO>
       └─ RedisSerializationContext

Application service
  ├─ validate input
  ├─ call template operations
  ├─ compose Mono/Flux
  └─ map errors / empty data

WebFlux controller / message handler
  └─ return publisher to framework
~~~

Design decisions to settle upfront:

1. **Key naming and TTL:** establish namespaces, separate environments/tenants as needed, and define retention lifetimes from business requirements.
2. **Serializers:** choose string/JSON/binary, schema versioning, and cross-service compatibility.
3. **Connections and driver:** let Spring manage them; configure timeouts, credentials, SSL/TLS, topology, and connection-error observability.
4. **Atomicity:** identify which operations require a single atomic command or server-side logic.
5. **Reactive composition:** return publishers, avoid blocking, avoid detached subscriptions, and bound concurrency.
6. **Failure behavior:** handle missing keys, Redis unavailability, timeouts, failovers, retries, and side-effecting commands.
7. **Monitoring:** track latency, error rates, request counts, hot keys, queues, throughput, and connection usage.

### Illustrating concurrency bounds in a batch

Suppose you need to fetch multiple nicknames from Redis:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;

public Flux<String> findNicknames(List<String> userIds) {
    return Flux.fromIterable(userIds)
        .flatMap(
            id -> reactiveStringRedisTemplate.opsForValue()
                .get("nickname:" + id)
                .defaultIfEmpty("anonymous"),
            16
        );
}
~~~

The parameter **16** caps how many inner publishers **flatMap** runs concurrently, bounding in-flight commands for the batch. This is an illustrative value to tune for real traffic. **flatMap** may emit results out of input order; if ordering must be preserved, consider **flatMapSequential** or **concatMap**, weighing buffering and concurrency trade-offs.

## 13. Reasoning scenarios

**Scenario 1 — Factory vs. template:** A service needs to store a DTO in Redis as JSON. Should **ReactiveRedisConnectionFactory** or **ReactiveRedisTemplate<String, DTO>** be injected into its constructor?

**Explanation:** Inject the template configured with the DTO serializer. The factory belongs in the configuration layer to construct templates or when low-level commands are deliberately required.

**Scenario 2 — Data never appears in Redis:** Code creates **Mono<Boolean> save = template.opsForValue().set(...)** without returning, composing, or subscribing to it. Why isn't the key in Redis?

**Explanation:** Constructing a cold publisher does not execute the command. Include the publisher in a chain subscribed to by the framework or caller.

**Scenario 3 — Lost updates:** Two HTTP requests concurrently run **get().flatMap(value -> set(value + 1))**. Why does the counter sometimes increase by only one?

**Explanation:** Reactive changes asynchronous representation and execution, not command boundaries; **GET** and **SET** remain separate Redis commands. Use **increment()** to express the increment as one atomic command.

**Scenario 4 — HTTP response times out after a write:** A request calls **set()** and times out on the client side. Is it certain Redis did not write the data?

**Explanation:** No. A timeout can occur after the command reached Redis while the response was lost or delayed. If the client retries, account for idempotency and possible prior state changes.

**Scenario 5 — Garbled data on read:** One service writes sessions using a JSON serializer, while another reads the same key with a string serializer. Is the connection factory broken?

**Explanation:** There is no basis to blame the connection. Both services may be using **valid connections** while disagreeing on byte encoding. Check the serialization context, key prefix, and data schema.

## Conclusion

In the Spring Data Redis architecture, **ReactiveRedisConnectionFactory** is the layer supplying reactive Redis connections, while **ReactiveRedisTemplate** is the service-facing data API providing serializers and Redis operations expressed as **Mono/Flux**. **ReactiveStringRedisTemplate** is a convenient choice when keys and values are strings.

Keeping the three boundaries clear—**connectivity**, **serialization**, and **subscription/reactive execution**—makes Redis usage in WebFlux applications clean and maintainable. At the same time, always distinguish **non-blocking I/O** from **business atomicity**: a reactive pipeline of multiple Redis commands can still suffer race conditions and requires appropriate synchronization.
