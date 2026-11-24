# Choosing Servlet/MVC or WebFlux by I/O Chain and Application Needs

## 1. Goal and selection principles

When building a web application with Spring Framework, the main choice is typically **Spring Web MVC (Servlet stack)** or **Spring WebFlux (reactive stack)**. Both build REST APIs, perform authentication, handle errors, return JSON, and serve many kinds of applications. The key question is not "which framework is more modern?", but rather:

1. **What I/O does the entire path of a request perform?** For example, database reads, HTTP calls, Redis calls, sending messages, or reading files.
2. **Do the libraries at each stage actually support non-blocking I/O?**
3. **What does the application need to optimize for?** Maintainability, concurrent requests, thread/memory consumption, streaming, tail latency (p95/p99), or reusing existing code.
4. **How well can the team operate and debug the reactive model?**

**Starting rule:** if most business logic uses synchronous libraries such as JDBC/JPA and Spring MVC already meets requirements, prefer MVC. If the application handles many long-waiting I/O operations, can preserve a non-blocking chain from HTTP down to downstream dependencies, and needs high concurrency, WebFlux is a strong candidate to evaluate. The final decision should be validated under realistic load.

## 2. Understanding blocking, asynchronous, non-blocking, and reactive

- **Blocking I/O:** the calling thread initiates an operation and must wait for the result before continuing. Examples: JDBC `repository.findById(id)`, synchronous HTTP call `RestClient.retrieve().body(...)`.
- **Asynchronous:** an operation completes at a later time; the caller may receive a `Future`, callback, or handle representing the result. "Async" does not guarantee that no underlying thread is waiting in a blocking call.
- **Non-blocking I/O:** when data is not ready yet, the thread does not sit waiting on that I/O operation; the runtime receives a notification or signal when processing can resume.
- **Reactive programming:** describes a data/event pipeline along with completion and error signals, commonly represented by `Mono<T>` (0 or 1 result) and `Flux<T>` (0 to many results) in Project Reactor.
- **Backpressure:** the consumer can signal how much data it can receive to the publisher in a pipeline that supports Reactive Streams. Backpressure does not mean automatically throttling all incoming HTTP requests or controlling every external system.

Keep two common misconceptions in mind:

- Returning `Mono`/`Flux` **does not mean** every stage is non-blocking. `Mono.just(jdbcRepository.findById(id))` still calls JDBC **immediately when creating the Mono**, on the current thread.
- WebFlux **does not inherently process a single request faster** than MVC. The main advantage of non-blocking I/O is serving many I/O-waiting connections with fewer threads under the right conditions. CPU, databases, connection pools, and downstreams still impose limits.

## 3. Two execution models seen from a single request

### Spring MVC / Servlet

Typical flow when a controller calls synchronous libraries:

~~~text
HTTP request
  → Servlet container (e.g., Tomcat)
  → Filter → DispatcherServlet → @Controller
  → Service → JDBC/JPA or synchronous HTTP client
                         [thread waits on I/O]
  ← Service ← result
  → Serialize JSON → HTTP response
~~~

In a normal synchronous path, one request-processing thread stays busy waiting on the blocking call. The Servlet container uses a thread pool to accept many concurrent requests. If I/O is slow and traffic is high, requests may queue waiting for threads.

**MVC also supports asynchronous processing:** `Callable`, `DeferredResult`, `WebAsyncTask`, returning reactive types, streaming, and SSE. Servlet async can release the request-accepting thread before the result is ready. Thus you should not equate "MVC" with "every request always holds a platform thread until the end"; inspect the actual code and executor.

### Spring WebFlux

Typical flow when **stages are genuinely non-blocking**:

~~~text
HTTP request
  → WebFlux runtime / event loop
  → WebFilter → DispatcherHandler → Controller returns Mono/Flux
  → WebClient / reactive repository: registers I/O, releases thread if data not ready
  → I/O ready: continues pipeline via signals
  → Encode data → non-blocking HTTP response
~~~

The event loop can multiplex many connections; it **must avoid being blocked** by `Thread.sleep`, `Future.get`, `block()`, synchronous JDBC/JPA, or long CPU-bound work. When an event-loop thread is blocked, many requests sharing that thread can slow down.

**The web server name does not dictate the model:** MVC is built on the Servlet API and commonly runs on Tomcat/Jetty; WebFlux typically defaults to Reactor Netty when initialized via Spring Boot, but can also run on other supported servers. "Running on Tomcat" does not automatically imply MVC; check the web stack and runtime configuration.

## 4. Analyze the **entire I/O chain** before choosing

Sketch a representative request, including the external systems your application calls:

~~~text
Client
  → HTTP server
  → Authentication/filters
  → Controller
  → Service
      ├─ SQL database / transaction
      ├─ External HTTP services
      ├─ Cache
      └─ Messaging / file storage
  → Serialize / stream response
  → Client
~~~

Classify each stage with the following questions:

| Stage | Common ways it can block | Non-blocking option when appropriate |
| --- | --- | --- |
| HTTP server | Synchronous Servlet handler processing | WebFlux event-loop/non-blocking transport |
| External REST/HTTP calls | Synchronous use of `RestClient`, `RestTemplate` | `WebClient` with a connector supporting non-blocking I/O |
| SQL | Traditional JDBC, JPA/Hibernate ORM | R2DBC with a supported driver and reactive repository |
| NoSQL/cache | Synchronous drivers/templates | Corresponding reactive drivers/templates, if available |
| Files/third-party SDKs | Sync SDKs, `InputStream.read` | Truly async/non-blocking APIs; must verify the specific SDK |
| CPU JSON processing, crypto, compression | Not I/O; still consumes CPU | Optimize algorithms, bound CPU scheduling; reactive does not make CPU faster |
| Writing response | MVC supports async, though some write paths remain blocking | WebFlux uses non-blocking I/O |

**Decisive bottleneck:** if a controller returns `Mono` while the service still calls synchronous JDBC, the waiting has not disappeared. WebFlux then pays both the reactive model overhead and the resources needed for blocking calls. Conversely, an MVC app can still use `WebClient` to coordinate async HTTP calls without migrating the entire server to WebFlux.

When auditing the I/O chain, record for each dependency: which API is used; which thread executes it; wait time; timeouts; connection pool limits; retry strategy; request cancellation capability; and transaction state. If information about an SDK is missing, measure or check its documentation rather than guessing from a method name containing "async".

## 5. When to choose Spring MVC?

MVC usually fits well when:

1. **CRUD, business applications, internal admin systems** where Spring Data JPA/Hibernate, JDBC, or synchronous SDKs make up most of the logic.
2. Business flows involve relational transactions and sequential code that is easy to read and debug; the team is already comfortable with `@Transactional` in the imperative model.
3. Current latency/throughput SLAs are met with acceptable thread counts, connection pools, and infrastructure cost.
4. Existing libraries, Servlet filters, interceptors, security, or integrations align naturally with MVC.
5. Only a few outbound HTTP calls exist: they can be optimized or called concurrently step-by-step as needed without changing the web stack.

**Example scenario:** creating an order requires reading and updating tables via JPA within one transaction. JDBC/JPA remains blocking; MVC is a clear foundation for implementing business logic, transaction management, validation, and error handling. Do not switch to WebFlux merely to make methods return `Mono<Order>`.

Optimizations to examine before changing frameworks: database indexes/queries, batch queries, timeouts, JDBC pool sizing, downstream connection limits, avoiding N+1 queries, sensible caching, and measuring p95/p99.

## 6. When is WebFlux worth considering?

WebFlux has potential advantages when several of these traits hold together:

1. **Many concurrent requests waiting on network I/O**: API gateways/BFFs aggregating multiple upstreams, chat/notification services, or endpoints holding long-lived connections.
2. Required HTTP clients, persistence, caches, and adapters have **truly reactive/non-blocking APIs**, or any blocking parts are minimal, isolated, and bounded.
3. There is a need to stream `Flux`/SSE or handle large data streams reactively; accounting for flow control and slow-reading clients.
4. Thread/memory resources or stability under I/O-waiting load is a measured problem.
5. The team has Reactor experience: understanding cold publishers, subscription, schedulers, error propagation, context, and async testing.

**Example scenario:** a BFF service concurrently calls three independent APIs with variable network latency, then merges results. `WebClient` + `Mono.zip` composes the results without holding a thread waiting on each socket. With many in-flight connections, this model can save thread resources; actual gains depend on upstream limits and benchmark results.

Do not pick WebFlux solely because there is a WebSocket/SSE endpoint: MVC also supports several async and streaming styles. Evaluate scale, flow control, infrastructure, and suitable libraries.

## 7. Side-by-side example: the same problem calling two upstreams

Suppose endpoint `GET /profiles/{id}` needs to fetch `GET /users/{id}` and `GET /scores/{id}` from another service at `http://localhost:8081`. Both upstream services are independent and return JSON:

~~~json
{"name":"Lan"}
~~~

~~~json
{"value":87}
~~~

The examples below target **two standalone Spring Boot 3.x applications**, using Spring Framework 6.1+ and Java 17+. Running end-to-end requires a mock upstream on port 8081 serving these exact two APIs. If the upstream is not running, requests will fail due to connection errors; **no fixed stdout or timing results** are assumed. Each project needs the standard Spring Boot Gradle plugin and dependency management.

### Option A — Spring MVC + synchronous HTTP client

In the MVC project, declare the dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Create `src/main/java/example/mvc/MvcApp.java`:

~~~java
package example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class MvcApp {
    public static void main(String[] args) {
        SpringApplication.run(MvcApp.class, args);
    }

    @RestController
    static class ProfileController {
        private final RestClient client = RestClient.builder()
                .baseUrl("http://localhost:8081")
                .build();

        @GetMapping("/profiles/{id}")
        Profile find(@PathVariable long id) {
            User user = client.get().uri("/users/{id}", id)
                    .retrieve().body(User.class);
            Score score = client.get().uri("/scores/{id}", id)
                    .retrieve().body(Score.class);

            if (user == null || score == null) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY);
            }
            return new Profile(user.name(), score.value());
        }
    }

    record User(String name) {}
    record Score(int value) {}
    record Profile(String name, int score) {}
}
~~~

In this example, the two `RestClient` calls sequentially wait for results on the processing thread; the HTTP path duration is roughly the sum of both upstream wait times (plus other processing overhead). This is a readable implementation suited to apps with synchronous dependencies. Do not conclude that **all** MVC apps must call upstreams sequentially like this snippet.

### Option B — WebFlux + non-blocking WebClient

In a **separate project** for WebFlux, use the dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Create `src/main/java/example/webflux/WebFluxApp.java`:

~~~java
package example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxApp {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxApp.class, args);
    }

    @RestController
    static class ProfileController {
        private final WebClient client = WebClient.builder()
                .baseUrl("http://localhost:8081")
                .build();

        @GetMapping("/profiles/{id}")
        Mono<Profile> find(@PathVariable long id) {
            Mono<User> user = client.get().uri("/users/{id}", id)
                    .retrieve().bodyToMono(User.class)
                    .switchIfEmpty(Mono.error(
                            new ResponseStatusException(HttpStatus.BAD_GATEWAY)));
            Mono<Score> score = client.get().uri("/scores/{id}", id)
                    .retrieve().bodyToMono(Score.class)
                    .switchIfEmpty(Mono.error(
                            new ResponseStatusException(HttpStatus.BAD_GATEWAY)));

            return Mono.zip(user, score)
                    .map(pair -> new Profile(
                            pair.getT1().name(), pair.getT2().value()));
        }
    }

    record User(String name) {}
    record Score(int value) {}
    record Profile(String name, int score) {}
}
~~~

`Mono.zip(user, score)` subscribes to both publishers and waits for **both** to complete; the HTTP requests can be processed concurrently by the non-blocking connector. Thus network wait time is typically close to the slower branch (plus overhead), provided the two upstreams are genuinely independent. `retrieve()` converts HTTP 4xx/5xx responses into error signals by default; production apps need clear error mapping, timeouts, cancellation, and downstream limits.

With either project above, run the app using `./gradlew bootRun` (Windows: `gradlew.bat bootRun`), after configuring the Boot project and upstream service. Test with:

~~~bash
curl http://localhost:8080/profiles/42
~~~

If the upstream returns the assumed JSON, the expected response body from **both** apps is:

~~~json
{"name":"Lan","score":87}
~~~

Note: the example illustrates **sequential calls versus async composition**, not a fair benchmark. MVC can also use `WebClient` or an executor to make concurrent calls; WebFlux can slow down if one step still blocks. Never compare performance by running these two snippets once and drawing broad conclusions.

## 8. Common architectures and how to decide

| Situation | Reasonable starting choice | Why |
| --- | --- | --- |
| CRUD REST + JPA/JDBC + business transactions | MVC | Persistence is still blocking; imperative code is easier to integrate and maintain |
| Existing MVC app needing multiple upstream HTTP calls | Keep MVC, consider `WebClient`/async for the HTTP stage | Optimize the network wait stage before considering a full-stack migration |
| I/O-heavy Gateway/BFF, non-blocking downstreams, many waiting connections | Trial WebFlux and benchmark | Optimize thread usage when most time is spent waiting on I/O |
| Reactive DB driver, but core SDKs remain sync | Evaluate stage-by-stage; insufficient reason to rewrite the whole app | Blocking still needs threads; isolating blocking work can incur noticeable cost |
| Heavy CPU processing, large encryption, image/video processing | Focus on worker architecture, CPU pools, and queues | Reactive does not add CPU; must avoid occupying the event loop |
| SSE/streaming with a moderate number of clients | Both MVC and WebFlux have options | Scale, backpressure, and operations decide |
| Project running stably on MVC with no measured problems | Stay on MVC | Migration carries cost and risk without assured benefit |

### Practical decision workflow

1. **Pick a real business flow** (e.g., placing an order, loading a dashboard, aggregating data for a screen).
2. **Draw the I/O chain and mark each call blocking or non-blocking**; verify down to the actual drivers and connectors, not just controller signatures.
3. **Set concrete load targets**: requests/second, concurrent connections, average and p95/p99 latency, downstream response speed, memory budget, CPU budget.
4. **Identify the bottleneck first**: thread pool, database connection pool, HTTP connection pool, slow queries, rate limits, or CPU.
5. **Choose the smallest solution that resolves the bottleneck**: DB tuning, timeouts, bulkheads, caching, async HTTP client, pool tuning, virtual threads, or WebFlux.
6. **Benchmark with the same business logic, data, infrastructure, and load profile**. Only commit to migration after obtaining evidence.

## 9. What if WebFlux needs to call a blocking library?

Do not call synchronous JDBC/SDK functions directly on the event loop, and do not call `block()` in the middle of a reactive request pipeline. A temporary escape hatch is running the blocking call on a scheduler meant for blocking tasks:

~~~java
Mono<Customer> customerMono = Mono.fromCallable(
        () -> blockingCustomerClient.findById(customerId))
    .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

This is an **illustrative snippet placed inside an existing service** that has `blockingCustomerClient` and `customerId` variables; it is not a standalone Java program. `fromCallable` defers invocation until subscription; `subscribeOn(boundedElastic())` moves the blocking work off the event loop.

**Limitations:** blocking still occurs on another thread; boundedElastic has finite resources and queues, and does not turn an SDK into non-blocking I/O. You must configure timeouts, concurrency, connection pools, and monitor saturation. If most of the pipeline is blocking JPA/JDBC, MVC is usually the simpler choice.

Conversely, never rewrite this as `Mono.just(blockingCustomerClient.findById(customerId))`, because the blocking call will execute immediately on the thread creating the publisher.

## 10. Transactions, context, error handling, and testing

- **Transactions:** the common imperative JDBC/JPA model ties transactions to a thread; reactive persistence requires a reactive transaction manager and Reactor context. `@Transactional` does not automatically make JDBC reactive; you cannot assume a thread-local transaction spans reactive callbacks. When switching models, redesign transaction boundaries and how DB calls are composed.
- **Context:** MVC code often relies easily on request-scoped `ThreadLocal`; reactive chains can switch threads, so tracing/security/request context must be propagated via a compatible context mechanism (such as Reactor Context and framework integrations). Avoid assuming every `ThreadLocal` always remains populated.
- **Errors:** MVC typically handles exceptions with `@ExceptionHandler`/`@ControllerAdvice`; WebFlux requires understanding both exceptions thrown before publisher creation and error signals emitted after subscription (`onErrorResume`, error handlers). Define HTTP statuses, timeouts, retries, and policies for partial upstream failures clearly.
- **Retries:** unconditional retries easily amplify load or repeat non-idempotent operations; only retry appropriate errors, with backoff and an overall time limit.
- **Testing:** MVC commonly uses `MockMvc`; WebFlux commonly uses `WebTestClient`, `StepVerifier` for publishers, and virtual time when needed. Both need integration tests for timeouts/streaming/slow clients and external adapters.
- **Observability:** measure per-endpoint latency, active threads/event-loop blocking, connection-pool utilization, request queues, GC, CPU, memory, in-flight requests, error rates, and dependency latency. Measurements matter more than how many reactive annotations you have.

## 11. Do virtual threads make WebFlux obsolete?

With **Java 21+**, virtual threads can help imperative code handle many I/O-waiting tasks at lower thread overhead than platform threads under suitable conditions. On supporting Spring Boot versions, you can configure:

~~~properties
spring.threads.virtual.enabled=true
~~~

This makes MVC with synchronous code worth benchmarking further, especially when using JDBC/JPA. However:

- I/O remains **blocking at the API level**; drivers and connection pools do not gain infinite throughput.
- Virtual threads do not make CPU-heavy tasks faster; you still must bound concurrent operations.
- Certain code patterns, locks, or native interactions can limit effectiveness; monitor for pinning symptoms according to your JDK and version.
- WebFlux still provides a reactive model with backpressure, non-blocking pipeline composition, and streaming; the two approaches carry different trade-offs.

Therefore, never conclude "with virtual threads, always choose MVC" or "with WebFlux, virtual threads are never needed." Measure your own system, including both throughput and p95/p99.

## 12. Common architecture and implementation mistakes

| Mistake | Harm | Fix |
| --- | --- | --- |
| Choosing WebFlux because it sounds "faster" | Increases complexity when the bottleneck is DB/CPU | Map the I/O chain and benchmark |
| Controller returns `Mono` but calls JPA directly | Blocks the event loop or shifts blocking elsewhere | Choose MVC, or temporarily isolate blocking with a bounded pool |
| Calling `block()` in a WebFlux controller | Blocks or throws errors on non-blocking threads | Return publishers and compose with operators |
| Mixing both starters and assuming WebFlux is running | Server stack configuration differs from expectations | Check Boot auto-configuration, startup logs, and application type |
| Setting `flatMap` concurrency too high | Overwhelms downstreams/connection pools | Set reasonable concurrency limits and timeouts |
| Using `WebClient` then calling `.block()` everywhere | Fails to leverage async at the call stage | Use async pipelines when suitable; if imperative, know the blocking points |
| Omitting timeout/cancel/retry policies | Requests hang indefinitely, queues grow, cascading failures | Set deadlines, conditional retries, backoff, and monitor saturation |
| Benchmarking a single request | Misses throughput, queuing, and tail latency | Test under realistic load and concurrent connections |
| Rewriting all of MVC to WebFlux despite many sync SDKs | High migration cost, little gain | Optimize the bottleneck stage first |

**Spring Boot note:** when adding both `spring-boot-starter-web` and `spring-boot-starter-webflux` in the same Boot 3.x app, web server auto-configuration normally favors **MVC** (many MVC projects add the WebFlux starter just to use `WebClient`). If you want a true WebFlux server, configure the application type and dependencies explicitly; do not identify the runtime by seeing `Mono` in a method signature.

## 13. Self-assessment exercises

Choose a starting approach and explain based on the I/O chain:

1. **Sales system:** `Controller → Service → JPA transaction → return JSON`. Moderate load and p95 meets target.
2. **BFF dashboard:** `Controller → 4 independent HTTP APIs → merge response`, each API with noticeable network latency, high concurrent connections.
3. **Existing MVC app:** one endpoint calls two slow HTTP services, while most business logic uses JPA.
4. **WebFlux endpoint:** controller calls a blocking file-reading SDK inside `map(...)` on the event loop.

**Suggested answers:** (1) MVC; measure SQL and transactions first. (2) Try WebFlux + WebClient when stages are non-blocking and benchmarks prove the benefit; or try an async client in MVC if that is the existing architecture. (3) Keep MVC and improve the HTTP step specifically (consider WebClient/async) before migrating. (4) Do not keep blocking work on the event loop: replace the SDK with an appropriate API or offload carefully with `boundedElastic`; if the architecture is mostly blocking, re-evaluate MVC.

## 14. Checklist before finalizing your choice

- [ ] Mapped the request path from HTTP through database, HTTP clients, caches, messaging, files, and response.
- [ ] Verified which dependencies/drivers are blocking and which are non-blocking.
- [ ] Defined concurrency, throughput, p95/p99, memory, and budget requirements.
- [ ] Checked database/HTTP connection pool, thread pool, and downstream limits.
- [ ] Considered MVC async/WebClient or virtual threads before a major migration.
- [ ] For WebFlux, ensured no unexpected blocking on the event loop; configured concurrency limits, timeouts, and error handling.
- [ ] Added appropriate tests for streaming, slow consumers, timeouts, cancellation, and retries.
- [ ] Ran benchmarks on a representative workload and gathered observability metrics to justify the decision.

**Practical conclusion:** choose a web stack from the **actual I/O chain and operational goals**. MVC is a sensible default for many imperative/JPA systems; WebFlux pays off when an application is designed end-to-end for non-blocking I/O, needs high I/O concurrency, and the team can operate reactive code. Both are valid tools; the conclusion should be backed by measurement.

### Official references

- [Spring Framework — Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html)
- [Spring Framework — WebFlux and selection criteria](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Framework — MVC asynchronous requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Boot — Virtual threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
