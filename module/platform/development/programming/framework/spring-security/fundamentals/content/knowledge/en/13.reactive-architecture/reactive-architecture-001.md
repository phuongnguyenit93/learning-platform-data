# WebFlux, Mono, Flux, and the Non-Blocking Execution Model

> **Context:** Spring Security – fundamentals → Reactive architecture. This lesson explains the Reactor/Spring WebFlux foundation and connects it directly to how Spring Security handles authentication and authorization on the reactive stack. Examples use Java 17+ and Spring Boot with Spring WebFlux and Spring Security.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish Spring MVC (Servlet) from Spring WebFlux in terms of I/O and threading models.
2. Explain `Publisher`, `Subscriber`, `Subscription`, completion/error signals, and backpressure.
3. Choose appropriately between `Mono<T>` (0 or 1 value) and `Flux<T>` (0 to many values), and compose processing steps with Reactor operators.
4. Identify blocking operations on the event loop, integrate asynchronous APIs, and isolate unavoidable blocking APIs.
5. Understand `WebFilter`, `SecurityWebFilterChain`, `ServerHttpSecurity`, and `ReactiveSecurityContextHolder` in Spring Security.
6. Create and run a small WebFlux application, and verify public endpoints, authenticated endpoints, and data streams.

## 2. What Is WebFlux? Why the Reactive Model?

**Spring WebFlux** is the web framework in Spring Framework's reactive stack. It receives and returns data under the Reactive Streams contract and is designed for asynchronous, non-blocking I/O. WebFlux supports both annotation-based controllers and functional endpoints; Spring Boot typically runs WebFlux on Reactor Netty, though WebFlux can also run on other supported servers.

Conceptual comparison:

| Perspective | Typical Spring MVC / Servlet | Spring WebFlux / reactive |
| --- | --- | --- |
| Request handling | Typically uses a worker thread serving each executing request | Event-loop workers handle I/O events across many connections |
| Waiting for I/O results | May hold a thread waiting on synchronous calls | Registers the next step and frees the thread to handle other work |
| Common return types | Objects, `ResponseEntity<T>` (also supports async) | `Mono<T>`, `Flux<T>`, `Mono<Void>`, `ResponseEntity<Mono<T>>`, etc. |
| Data source pacing | Typically relies on synchronous call flow / buffers | Reactive Streams provides the `request(n)` mechanism to express demand |
| Suitable integration APIs | JDBC, synchronous clients under moderate load | WebClient, R2DBC, reactive drivers, and APIs returning `Publisher` |
| Spring Security | Servlet `Filter`, `SecurityFilterChain`, `HttpSecurity` | `WebFilter`, `SecurityWebFilterChain`, `ServerHttpSecurity` |

Do not equate **reactive** with "faster in every case." The benefits are usually clear when an application waits on many I/O connections, needs to handle high concurrency with a limited number of threads, or streams data. For CPU-heavy work, databases that only have JDBC, or simple CRUD applications, WebFlux does not automatically improve latency. An architecture truly avoids blocking threads only when the key I/O operations in the pipeline are also non-blocking.

**Remember:** `Mono`/`Flux` is a model for representing data and signals; merely returning a `Mono` does not turn a JDBC call or `Thread.sleep` into non-blocking execution.

## 3. Reactive Streams Mechanics: Data and Signals

Reactive Streams describes how a data producer and a data consumer communicate with each other:

- `Publisher<T>`: a source that can emit data of type `T`. `Mono` and `Flux` are Reactor's key implementations.
- `Subscriber<T>`: the party that subscribes to receive data and signals.
- `Subscription`: the relationship between subscriber and publisher; the subscriber can call `request(n)` to demand up to `n` more elements and `cancel()` to cancel.
- `onSubscribe`: signal delivering the `Subscription`; `onNext`: emits one element; `onComplete`: normal termination; `onError`: termination due to error.

Conceptual sequence:

~~~text
Subscriber                 Publisher
    | ------ subscribe() ----> |
    | <---- onSubscribe(s) --- |
    | ------ request(2) -----> |
    | <------ onNext(A) ------ |
    | <------ onNext(B) ------ |
    | ------ request(1) -----> |
    | <------ onNext(C) ------ |
    | <----- onComplete() ---- |
~~~

Within a valid subscription, `onComplete` and `onError` are mutually exclusive terminal states; no new `onNext` occurs after a terminal signal. A subscriber may cancel before completion. A backpressure-compliant publisher will not emit more `onNext` signals than the demand that has been requested.

**Backpressure** is how the consumer signals its intake rate to the producer to avoid being overwhelmed by data. If an external source cannot slow down (for example, an uncontrolled hot source), the system still needs an appropriate buffer/drop/error policy; Reactive Streams does not magically create infinite memory and does not guarantee that every network protocol propagates `request(n)` one-to-one all the way to the origin.

In WebFlux, Spring is typically the party that subscribes to the pipeline returned by a controller; it uses the signals to write the HTTP response. Therefore, **do not manually call `subscribe()` inside a controller** just to trigger a pipeline: doing so creates a separate subscription, detaches the data/error flow from the HTTP lifecycle, and can lose the security context.

## 4. Mono and Flux: Which Type to Choose?

| Type | Elements per subscription | Examples |
| --- | --- | --- |
| `Mono<T>` | 0 or 1 | Fetching a user, calling an API returning a single JSON payload, validating a token |
| `Mono<Void>` | No `T` value; signals completion/error only | Deleting a resource, asynchronous logging, completing a response |
| `Flux<T>` | 0 to many | Product list, event notifications, SSE, record streams |

Examples of Reactor sources:

~~~java
Mono<String> one = Mono.just("Java");
Mono<String> absent = Mono.empty();
Mono<String> maybe = Mono.justOrEmpty((String) null);
Mono<String> failed = Mono.error(new IllegalStateException("unavailable"));

Flux<Integer> many = Flux.just(1, 2, 3);
Flux<Integer> sequence = Flux.range(1, 5); // 1,2,3,4,5
Flux<Integer> none = Flux.empty();
~~~

The lines above are **illustrative snippets** using `reactor.core.publisher.Mono` and `Flux`, not a standalone Java program. They show that `Mono.empty()` is a stream that completes with no elements, unlike `Mono.just(null)`: Reactor does not allow `null` elements, so `Mono.just(null)` throws an error.

`Mono<List<T>>` and `Flux<T>` are also not the same: the former emits **one** list as a single element, while the latter emits elements **one by one**. `collectList()` can convert a finite `Flux<T>` into a `Mono<List<T>>`, but it must gather all the data in memory. For very large or unbounded streams, do not collect into a list.

### Lazy, Cold, Hot, and Execution Timing

Most `Mono`/`Flux` instances from standard factories are **cold**: each subscription initiates its own emission process. For example, `Mono.fromSupplier(...)` or `Mono.defer(...)` executes the source logic only when subscribed. `Mono.just(value)` already holds `value` at publisher construction time, even though emission signals to the subscriber still arrive after subscribing. A **hot** publisher (such as a source shared via `Sinks.Many`) can emit data independently of any specific subscriber; late subscribers may miss events if there is no replay mechanism.

~~~java
AtomicInteger counter = new AtomicInteger();
Mono<Integer> cold = Mono.fromSupplier(counter::incrementAndGet);

cold.subscribe(System.out::println); // 1
cold.subscribe(System.out::println); // 2
~~~

This is an illustrative snippet (requiring imports for `java.util.concurrent.atomic.AtomicInteger` and `reactor.core.publisher.Mono`). The two subscriptions run sequentially, so stdout order matches the comments; `subscribe()` on this synchronous source executes immediately. Do not assume every subscription runs asynchronously.

## 5. Operators: Building Pipelines Without Manual Thread Management

Reactor operators create **new** publishers; they do not mutate the original publisher object. Common operators:

- `map(f)`: synchronous transformation `T → R`. Use when `f` returns a regular value and executes quickly.
- `flatMap(f)`: transformation `T → Publisher<R>`, composing asynchronous tasks. With `Flux`, elements may interleave and completion order is not guaranteed.
- `concatMap(f)`: composes inner publishers sequentially, preserving source order; suitable when ordering is mandatory and reduced concurrency is acceptable.
- `filter(predicate)`: keeps only elements matching the condition.
- `switchIfEmpty(other)`: switches to an alternative publisher when the source emits no elements.
- `zip(a,b)`: combines results from sources when all required sources emit data; note that an empty source can cause the zipped result to also be empty.
- `onErrorResume(f)`: switches to a recovery branch on error; `onErrorMap(f)`: transforms the error type; `timeout(duration)`: sets a deadline on the pipeline.
- `doOnNext`, `doOnError`, `doFinally`: observe signals (logging, metrics, cleanup); they do not transform values like `map`.

~~~java
Flux<String> names = Flux.just(" an ", " binh ", " chi ");

Flux<String> normalized = names
    .map(String::trim)
    .filter(name -> name.length() >= 3)
    .map(String::toUpperCase);

normalized.subscribe(System.out::println);
~~~

When run in an application with Reactor on the classpath, this synchronous illustrative snippet prints exactly:

~~~text
BINH
CHI
~~~

`flatMap` is especially important for I/O. Example **illustrative code depending on a real reactive repository**:

~~~java
Mono<User> user = repository.findById(id)
    .switchIfEmpty(Mono.error(new UserNotFoundException(id)));

Flux<Order> orders = Flux.fromIterable(userIds)
    .flatMap(userId -> reactiveOrderRepository.findByUserId(userId));
~~~

Names like `User`, `Order`, the repositories, and the exception must be defined in a real application; this is not a self-contained runnable file. Do not replace `flatMap` with `map` when the callback returns a `Mono`: using `map` in that case produces `Mono<Mono<User>>` instead of `Mono<User>`.

Avoid `onErrorResume(error -> Mono.empty())` for all errors: it silently turns failures into empty data. For authentication, authorization, or critical system errors, preserve the proper semantics and return an appropriate HTTP response.

## 6. The Non-Blocking Execution Model: Understanding the Event Loop Properly

When a client sends an HTTP request to WebFlux running on Reactor Netty, the high-level model is:

~~~text
HTTP client
    |
    v
Reactor Netty event loop (socket read/write, I/O readiness)
    |
    v
WebFlux WebFilter chain (Spring Security participates here)
    |
    v
DispatcherHandler -> Controller/Handler
    |
    v
Mono/Flux pipeline -> data or completion/error signals
    |
    v
HTTP codec -> writes response based on I/O readiness
~~~

Callbacks may run on different threads due to I/O sources or a `Scheduler`; the diagram does not mean every step runs on the same thread. With non-blocking I/O, while waiting for a network/database response, the event loop can serve other connections instead of waiting idle for the result. That is why a relatively small number of event-loop threads can manage many connections.

Distinguish four concepts:

1. **Blocking:** a thread must wait before proceeding, such as `Thread.sleep`, synchronous JDBC, `Future.get()`, or `Mono.block()`.
2. **Non-blocking:** a call does not hold a thread waiting on I/O; work continues when an event/result arrives.
3. **Asynchronous:** the result arrives at a later time; this does not automatically mean the code is non-blocking.
4. **Parallelism:** multiple tasks actually execute simultaneously across multiple cores/threads; not synonymous with non-blocking.

For example, `Mono.delay(Duration.ofMillis(200))` produces a signal after roughly 200 ms using a scheduler/timer mechanism, without calling `Thread.sleep(200)` on the event-loop thread handling the request. By contrast, `Mono.just(slowJdbcCall())` invokes `slowJdbcCall()` **immediately when the expression is evaluated**, before the pipeline is subscribed, so it can still block the thread.

### `subscribeOn` and `publishOn`

Reactor does not open a new thread per `map` by default. Every callback generally runs on the thread emitting the signal, unless the source or a scheduler changes the context.

- `subscribeOn(scheduler)` affects the subscription context and upstream/source; placing it near the source helps readers see the intent.
- `publishOn(scheduler)` switches downstream signal processing after it to a worker of the chosen scheduler, until the next switch.
- `Schedulers.parallel()` is suitable for bounded CPU work; `Schedulers.boundedElastic()` is used to isolate unavoidable blocking calls, with bounded threads/queues.
- Do not overuse scheduler switches on every operator; thread switching has overhead and does not fix a data-source bottleneck.

**Important:** "offloading blocking to boundedElastic" avoids locking up the event loop, but the call itself is still blocking and still consumes a thread; the better choice for high-load I/O is a genuine reactive driver/API.

## 7. Complete WebFlux + Spring Security Application (Java 17+)

Create a project from Spring Initializr, choose **Java 17 or newer**, Maven, and exactly two dependencies: **Spring Reactive Web** (`spring-boot-starter-webflux`) and **Spring Security** (`spring-boot-starter-security`). Use a stable Spring Boot version compatible with the JDK at project creation time. Do not add the Spring Web MVC starter in the demo: when both Web MVC and WebFlux starters are present, Spring Boot defaults to the MVC model unless the application type is explicitly configured.

Place the files in `src/main/java/com/example/reactive/`. No database or external service is required.

**File `ReactiveDemoApplication.java`**

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveDemoApplication.class, args);
    }
}
~~~

**File `ApiController.java`**

~~~java
package com.example.reactive;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
class ApiController {

    record Message(String message) {}

    @GetMapping("/public")
    Mono<Message> publicEndpoint() {
        return Mono.just(new Message("public"));
    }

    @GetMapping("/squares")
    Flux<Integer> squares() {
        return Flux.range(1, 3).map(n -> n * n);
    }

    @GetMapping(value = "/ticks",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<Long> ticks() {
        return Flux.interval(Duration.ofMillis(200)).take(3);
    }

    @GetMapping("/me")
    Mono<Message> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> new Message("hello " + name));
    }
}
~~~

**File `SecurityConfig.java`**

~~~java
package com.example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public", "/api/ticks").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("learner")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }
}
~~~

Configuration explanation: `SecurityWebFilterChain` checks routes before the controller handles them; `/api/public` and `/api/ticks` are public, while the remaining endpoints require an `Authentication`. `httpBasic` allows sending Basic Authorization for testing. `MapReactiveUserDetailsService` is an in-memory user store suitable for demos; the password is hashed with BCrypt. Sample accounts and passwords are for learning environments only and must not be hardcoded into production. For production applications, choose authentication mechanisms, HTTPS, secret storage, and CSRF policies appropriate for the client type.

Run from the project directory:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell you can use `.\mvnw.cmd spring-boot:run`. Once the server has started on default port 8080, open another terminal:

~~~bash
curl -s http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -s -u learner:demo123 http://localhost:8080/api/me
curl -s -u learner:demo123 http://localhost:8080/api/squares
curl -N http://localhost:8080/api/ticks
~~~

Expected response contents:

- `GET /api/public` → HTTP 200, JSON `{"message":"public"}`.
- `GET /api/me` without credentials → HTTP 401 Unauthorized (headers may vary by version).
- `GET /api/me` with valid HTTP Basic → HTTP 200, JSON `{"message":"hello learner"}`.
- `GET /api/squares` with credentials → HTTP 200, JSON `[1,4,9]`.
- `GET /api/ticks` → HTTP 200, SSE stream emitting values `0`, `1`, `2` sequentially, spaced approximately 200 ms apart. `curl -N` disables buffering in curl; actual timing depends on scheduling.

Note: the results above are **expected outcomes based on the sample code**, not actual execution logs from a running environment. The example code aligns class names, packages, imports, and endpoints; external project environment settings may change the port or security behavior.

### Why Is This Example Reactive?

- `/api/public` uses `Mono<Message>` for a single value.
- `/api/squares` uses `Flux<Integer>` for three values; `map` is a fast synchronous transformation.
- `/api/ticks` uses a timer-driven publisher and SSE; it does not keep a request thread sleeping for 200 ms between values.
- `/api/me` retrieves the username via `ReactiveSecurityContextHolder` inside the pipeline.
- The controller only **returns publishers**. Spring WebFlux/Spring Security is responsible for subscribing, sending the response, and handling errors/cancellation.

Do not conclude that every `Mono` always runs on its own thread: `Mono.just` can emit synchronously; `Flux.interval` uses a scheduler. "Reactive" lies in the contract and how sources are composed, not a promise that every operator spawns a thread.

## 8. Spring Security on the Reactive Stack

Spring Security for WebFlux is integrated via **`WebFilter`** and configured with **`SecurityWebFilterChain`**/`ServerHttpSecurity`. It differs from the Servlet stack's `SecurityFilterChain`/`HttpSecurity`. Authentication and authorization concepts remain familiar, but the processing API is reactive:

| Task | Reactive type/concept |
| --- | --- |
| Inspecting requests and applying policy | `SecurityWebFilterChain` and `authorizeExchange` |
| Asynchronous authentication | `ReactiveAuthenticationManager` returning a publisher containing the authentication result |
| Looking up account details | `ReactiveUserDetailsService`, typically returning `Mono<UserDetails>` |
| Reading the request's security context | `ReactiveSecurityContextHolder.getContext()` |
| Saving/loading the security context at the web layer | Spring Security's reactive mechanisms, such as `ServerSecurityContextRepository` as configured |
| Service-method authorization (when used) | `@EnableReactiveMethodSecurity` and corresponding method security annotations |

### Why Not Read Servlet-Style SecurityContextHolder?

In the Servlet stack, `SecurityContextHolder` typically attaches data to the `ThreadLocal` of the thread serving the request. In a reactive pipeline, execution can hop across multiple threads due to I/O and schedulers, and a single thread can serve different subscriptions. Therefore, you should not rely on a plain `ThreadLocal` to carry identity across a reactive chain.

Spring Security propagates the appropriate security context through **Reactor Context**, bound to the subscription, and supports accessing it via `ReactiveSecurityContextHolder`. For example, `/api/me` reads the context inside the pipeline rather than grabbing a global value when constructing the controller. Context is not data that gets sent automatically to every other HTTP service: when making downstream calls, you must explicitly design how tokens/credentials are forwarded.

Also because context depends on the subscription, calling `subscribe()` in a detached way inside a service/controller can break the request lifecycle, error handling, or authentication context. Return `Mono`/`Flux` to the framework or compose it into the caller's pipeline.

### The Security Pipeline Must Stay Non-Blocking

An easy-to-follow pipeline is:

~~~text
request
  -> WebFilter/Authentication
  -> Authorization
  -> Controller
  -> Reactive service
  -> Reactive repository or WebClient
  -> HTTP response
~~~

If at any step you call a blocking API on the event loop (for example, looking up a user with synchronous JDBC during authentication), you can stall other requests as well. Changing the signature to `Mono<Authentication>` while performing synchronous I/O directly inside `map` does not solve the problem.

In method security, returning publishers and controlling context must be designed together. Do not accidentally "authorize after sensitive data has already been emitted"; apply rules early, with explicit check conditions, and avoid fallbacks that grant access when an authentication step errors.

## 9. Writing Non-Blocking End to End

An application typically needs to call other services or query a database. Preferred choices:

- Outbound HTTP: `WebClient` with a non-blocking connector instead of synchronous clients when using WebFlux.
- Relational queries: R2DBC/reactive repositories when supported by the database and driver; standard JDBC remains blocking.
- Event streams: compatible reactive adapters, managing backpressure and subscription lifecycle.
- Heavy CPU tasks: consider schedulers, concurrency limits, and background processing architectures rather than forcing heavy computation onto the event loop.

Example **illustrative snippet in a service with a configured `WebClient` and a declared `UserDto`**:

~~~java
Mono<UserDto> result = webClient.get()
    .uri("/users/{id}", id)
    .retrieve()
    .bodyToMono(UserDto.class)
    .timeout(Duration.ofSeconds(2));
~~~

Here `bodyToMono` represents a future result. `timeout` bounds the wait time; timeout errors should be classified and mapped to an appropriate response or retry strategy. Do not call `result.block()` inside a request handler just to "extract the value," as that defeats the non-blocking goal.

### When You Must Use a Legacy Blocking API

Use `Mono.fromCallable` to **defer** the call until subscription time, then move it onto `boundedElastic`. The following example is only an illustrative pattern because `legacyClient` must be provided in a real application:

~~~java
Mono<String> adapted = Mono
    .fromCallable(() -> legacyClient.lookup("customer-42"))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Why two steps: `fromCallable` avoids invoking `lookup` immediately when building the pipeline; `subscribeOn` runs the blocking source on a suitable scheduler, avoiding blocking the event-loop thread. This does not make the client non-blocking, and you must still bound concurrency/queues, connection pools, and timeouts. Do not use `Schedulers.parallel()` to wait on long-running blocking I/O.

**Common mistakes:**

~~~java
Mono<String> wrong = Mono.just(legacyClient.lookup("customer-42"));
// lookup() runs immediately and may block the event loop.

Mono<String> stillWrong = Mono.fromSupplier(
    () -> legacyClient.lookup("customer-42"));
// Lazy, but if subscribed on the event loop, it still blocks on the event loop.
~~~

Both snippets are non-runnable illustrative code. `fromSupplier` solves laziness, not selecting a scheduler capable of tolerating blocking.

## 10. Backpressure, Latency, and Memory Consumption

With `Flux`, downstream can demand an appropriate number of elements via `request(n)`. However, many operators have their own prefetch/buffering policies, and boundaries such as HTTP, database drivers, and hot sources behave differently. You need to control **in-flight requests**, **concurrently processed elements**, and **buffers** together.

Illustrative example of bounding concurrency:

~~~java
Flux<Result> results = Flux.fromIterable(ids)
    .flatMap(id -> reactiveService.fetch(id), 8);
~~~

This snippet requires `ids`, `Result`, and `reactiveService` from a real application. The `8` parameter limits how many inner publishers `flatMap` subscribes to concurrently, which is useful when you do not want to open too many upstream calls at once. It is not a system-wide connection limit: connection pools, rate limits, and server configuration still need to be set.

Some related operators:

- `limitRate(n)` shapes how demand is requested upstream; it does not mean the entire pipeline always holds at most `n` elements in memory.
- `onBackpressureBuffer(...)` stores elements when downstream is slow; it requires explicit bounds and an overflow strategy.
- `onBackpressureDrop()`/`onBackpressureLatest()` fit certain telemetry streams where samples may be dropped, not financial data or events where every item must be processed.
- `take(n)` completes after `n` elements and normally cancels upstream. Cancelling a subscription helps free resources, but cannot guarantee that an already-started external operation will always be rolled back.

For SSE/long-lived streams, handling disconnects, timeouts, cleanup, and client speed is critical. For regular JSON arrays, response encoding/writing may depend on how the codec buffers/flushes, so do not assume every `Flux` element will immediately appear on the client screen.

## 11. Handling Errors, Empty Signals, and Cancellation

A reactive error is a **terminal signal** for a subscription. Some patterns:

~~~java
Mono<String> fallback = remoteCall()
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(TimeoutException.class, error -> Mono.just("cached"));
~~~

This is an illustrative snippet: it requires `remoteCall()`, plus the corresponding `Duration` and `TimeoutException` imports. A cache fallback only makes sense if the business logic accepts stale data; never default to returning a `"cached"`-style fallback in place of an access-control decision.

- `onErrorResume` selects a recovery branch, unlike `doOnError` which only logs/observes.
- `switchIfEmpty` handles **no elements emitted**, which is completely different from **an error occurred**.
- `retry` can re-invoke upstream, so you must consider idempotency (especially for POST, payments, sending notifications), retry counts, and backoff.
- `timeout` sets a deadline; distinguish timeouts you enforce yourself from client/driver timeouts.
- `doFinally`/`usingWhen` are useful for releasing resources on complete/error/cancel.
- Once an HTTP response has started streaming, a late error may no longer be convertible into an error JSON body or a new status code; choose an error reporting mechanism suitable for streams.

Never swallow authentication/authorization errors with `onErrorResume(e -> Mono.just(true))` or return success-like default data. From a security standpoint, authentication/authorization failures must lead to denial or controlled error handling.

## 12. Common Mistakes and How to Fix Them

| Issue | Why it is wrong | How to fix it |
| --- | --- | --- |
| `Mono.just(blockingCall())` | The call runs before subscription | Use a reactive driver; or `fromCallable(...).subscribeOn(boundedElastic())` when unavoidable |
| `Thread.sleep`, `block()`, `Future.get()` in a controller | Blocks the request-handling thread | Compose the pipeline with `flatMap`/`zip`; use timers/async APIs |
| Calling `subscribe()` in a controller/service and returning `Mono.empty()` | Creates work detached from the response, losing error semantics/context | Return the publisher or chain it into the framework-managed pipeline |
| Using `map` for a function returning `Mono` | Produces nested publishers | Use `flatMap` |
| Assuming `Flux` always preserves order after `flatMap` | Inner publishers can complete out of order | Use `concatMap` when order matters |
| Calling `collectList()` on large/unbounded streams | Buffers data in RAM and waits for completion | Stream elements incrementally, paginate, or bound size |
| Using `ThreadLocal` for user/security context | Reactive chains can switch threads | Use `ReactiveSecurityContextHolder`/Reactor Context |
| Configuring `HttpSecurity` instead of `ServerHttpSecurity` in WebFlux | Mixes Servlet and reactive security stacks | Use `SecurityWebFilterChain` + `ServerHttpSecurity` |
| Retrying every error or swallowing every `onError` | Masks failures and may duplicate side effects | Classify errors, bound retries, preserve security semantics |
| Assuming every `Mono` runs asynchronously on its own | A publisher can be synchronous/lazy | Check the actual signal source, scheduler, and I/O |

Another mistake is adding both `spring-boot-starter-web` and `spring-boot-starter-webflux` and assuming the application runs on WebFlux. Spring Boot typically prefers MVC when both are present; verify your dependencies and application type. An MVC application can still use `WebClient` without turning the entire server into WebFlux.

## 13. Verification and Diagnostics

1. **HTTP behavior:** test anonymous and authenticated endpoints; verify 200/401/403 against your rules; inspect JSON and SSE responses.
2. **Threads and blocking:** check thread names in test-environment logs to understand scheduler hops; do not use logged thread names as an identity mechanism. BlockHound in test environments can help detect blocking calls on threads marked non-blocking.
3. **Performance:** monitor CPU, event-loop latency, connection pools, timeouts, active subscriptions, buffers/queues, and p95/p99 latency under realistic load.
4. **Backpressure:** test slow consumers, cancellation/disconnects, fast upstreams, and timeouts. Verify that chosen buffer/drop policies match the data requirements.
5. **Security:** verify context propagation across async steps; ensure no identity leakage between requests; avoid accidentally exposing endpoints via overly broad `permitAll` rules.
6. **Testing Reactor:** `StepVerifier` from `reactor-test` helps assert `onNext`, `onComplete`, and `onError` sequences; use `WebTestClient` to test WebFlux endpoints, with Spring Security test support when mocking an authenticated principal.

Do not judge an architecture solely by thread count: non-blocking can improve I/O scalability, but you still need to verify latency, throughput, GC, DB bottlenecks, and client-disconnect errors.

## 14. Practice Exercises

**Exercise 1 – Publisher classification.** Choose `Mono` or `Flux` for: fetching a profile by id, counting records, streaming notifications, and a delete command returning 204. Explain why `Mono<Void>` fits cases where you only need to know success/failure.

**Exercise 2 – Reading code and fixing bugs.** In a WebFlux controller, what are the two problems with `Mono.just(jdbcRepository.findById(id))`? State the best approach and the interim approach when JDBC cannot yet be replaced.

**Exercise 3 – Reactive security.** In the demo application, why can `/api/me` read `learner` even though the controller does not store a global `currentUser` variable? Explain the roles of `SecurityWebFilterChain`, authentication, and Reactor Context.

**Exercise 4 – Streaming.** Change `take(3)` in `/api/ticks` to `take(5)`, try disconnecting the client early, and describe cancellation. Identify why SSE data arrives incrementally while regular JSON arrays may be handled differently.

**Brief answer hints:** Profile and count are typically `Mono<T>`; notifications are `Flux<T>`; delete with no body is `Mono<Void>`. JDBC is still blocking; prefer a reactive driver, or temporarily use `fromCallable` and `boundedElastic` with resource limits. Authentication in the demo flows through WebFlux security filters, and the subscription's context is accessed via `ReactiveSecurityContextHolder`, not Servlet `ThreadLocal`.

## 15. Summary and Official References

Get the three layers straight: **WebFlux** provides the reactive HTTP stack; **Reactor** provides `Mono`/`Flux` and operators to describe signals, backpressure, and execution; **Spring Security reactive** enforces security policies via `WebFilter` and context bound to the reactive subscription. Non-blocking does not come automatically from return types: you must build an end-to-end non-blocking I/O pipeline, manage concurrency, and handle errors/cancellation explicitly.

Reference documentation:

- [Spring Framework – Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Spring Framework – WebFlux Overview and Concurrency Model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Project Reactor – Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor – Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
