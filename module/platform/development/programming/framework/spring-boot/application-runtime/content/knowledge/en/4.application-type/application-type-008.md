# Boundary Between Application Lifecycle and Servlet or Reactive Request Handling

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Spring Boot application lifecycle** from **HTTP request lifecycle**.
2. Explain the roles of `SpringApplication`, `ApplicationContext`, embedded web server, controllers, and Servlet/Reactive pipelines.
3. Understand why `ApplicationRunner`, `ApplicationReadyEvent`, `@PostConstruct`, and `@PreDestroy` are not "per-request" callbacks.
4. Read and run Spring MVC (Servlet) and Spring WebFlux (Reactive) examples, comparing similarities and differences.
5. Properly handle failed requests, canceled requests, unready applications, or graceful shutdown.

**Context:** This lesson belongs to **Spring Boot Application Runtime → Application Types**. The focus is *lifecycle boundaries*, not learning the full Servlet API, Reactor, or REST API design.

## 1. There Are at Least Two Different Lifecycles

### Application Lifecycle

The application lifecycle begins when the process calls `main` and `SpringApplication.run(...)`, encompassing creating/loading `ApplicationContext`, preparing `Environment`, configuring beans, starting a web server when needed, invoking runners, and signaling application readiness. It continues until the context closes and resources are released.

Typically a Spring Boot application has **one main context** serving many requests. Certain specialized architectures may use multiple contexts, though that is not the default.

~~~text
main()
  └─ SpringApplication.run(args)
       ├─ Prepare Environment / configuration
       ├─ Create appropriate ApplicationContext
       ├─ Register configurations and bean definitions
       ├─ refresh(): instantiate beans, start infrastructure
       ├─ ApplicationStartedEvent
       ├─ ApplicationRunner / CommandLineRunner
       ├─ ApplicationReadyEvent
       └─ Return ConfigurableApplicationContext

Application continues running
  ├─ Request A arrives and completes
  ├─ Request B arrives and completes
  ├─ Request C is canceled or errors
  └─ ... many other requests ...

Close context / shut down application
  ├─ Stop accepting and/or drain in-flight requests per shutdown policy
  ├─ Stop managed components
  └─ Destroy beans, release resources
~~~

This is a **conceptual** diagram. The detailed sequence includes additional lifecycle events, post-processors, and callbacks. For example, `ApplicationStartedEvent` occurs **after the context has refreshed yet before runners**, while `ApplicationReadyEvent` fires after runners succeed.

### Request Lifecycle

Each HTTP request has its own journey: the connection/request reaches the server, the framework resolves the route, invokes the handler/controller, builds the response (or response stream), handles errors, and completes or is canceled. This journey occurs **within the period the application is running**, without repeating all of `SpringApplication.run`.

~~~text
                  Context and server running
                         │
Client ── HTTP request ──┤
                         ├─ Servlet: filter → DispatcherServlet → handler
                         │              → process → HTTP response
                         │
                         └─ Reactive: WebFilter → DispatcherHandler → handler
                                        → Publisher → HTTP response
                                                  or error/cancel
~~~

One request finishing does **not** mean the application shuts down. A handler throwing an exception does **not by default** cause the entire `ApplicationContext` to fail. Conversely, when the application begins shutting down, new or in-flight requests may be affected depending on the server and graceful shutdown policy.

## 2. Three Layers of Responsibility and Lifespan

| Component | Typical Lifespan | Responsibility | Should Not Be Confused With |
| --- | --- | --- | --- |
| JVM process | From launch until exit | Runs code, manages threads, heap, and process resources | A single HTTP request |
| `SpringApplication` | Bootstrap object, mainly used during `run` | Coordinates context startup per configuration | Request handler; holder of all business state |
| `ApplicationContext` | From creation until close | Manages beans, dependency injection, lifecycle, events | Recreated for each HTTP request |
| Embedded web server | Part of web runtime, lives alongside its context | Listens on port, accepts connections, passes requests to framework | Synonymous with controller |
| Controller/handler | Usually a singleton bean in context | Maps routes and handles requests | Created fresh on every route call |
| Request/response objects | Per exchange or related operation | Carry HTTP metadata, body, status, headers | Place for application-wide configuration |

**Important consequence:** a `@RestController` is typically a **singleton** bean, created at startup and able to handle many concurrent requests. Do not store request-specific state—such as `currentUser` or `lastRequestBody`—in a mutable field of a singleton controller without an appropriate isolation design.

`@PostConstruct` runs when the bean is initialized, and `@PreDestroy` runs when the bean is destroyed under container management. They do not run before/after every HTTP request.

## 3. Application Type Determines Request Infrastructure

Spring Boot typically infers `WebApplicationType` from libraries present on the classpath:

- **`SERVLET`:** Servlet stack web application, typically using `spring-boot-starter-web`, Spring MVC, `DispatcherServlet`, and embedded Tomcat by default.
- **`REACTIVE`:** Reactive web application, typically using `spring-boot-starter-webflux`, Spring WebFlux, `DispatcherHandler`, and Reactor Netty as the common default.
- **`NONE`:** Application that does not set up an embedded web server under Spring Boot's web auto-configuration; suited for CLIs, workers, or background tasks.

You can set the application type explicitly **before `run`**:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.setWebApplicationType(WebApplicationType.NONE);
application.run(args);
~~~

The code above only illustrates the configuration point, not a standalone program.

If `spring-boot-starter-web` and `spring-boot-starter-webflux` are both present, Spring Boot **typically selects `SERVLET`**; this suits using `WebClient` inside an MVC application, yet does not automatically turn controllers into the WebFlux model. To study the boundary clearly, experiment with two projects using only one of the two starters. Do not force `REACTIVE` merely to "run faster": framework, dependencies, I/O style, and operational design must match.

### Servlet and Reactive Boundaries

| Aspect | Spring MVC / Servlet | Spring WebFlux / Reactive |
| --- | --- | --- |
| Spring request dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Interception layer | Servlet `Filter`, MVC `HandlerInterceptor`... | `WebFilter` and reactive equivalents |
| Common handler return values | `String`, DTO, `ResponseEntity<T>`, async types when appropriate | `Mono<T>`, `Flux<T>`, or supported values |
| Typical I/O model | Servlet thread pool; requests usually handled on server threads | Non-blocking I/O, event loop, and Publisher chains |
| Requirements for blocking operations | Servlet supports blocking models; still bound threads and timeouts | Avoid blocking on the event loop; use a suitable scheduler if blocking libraries are unavoidable |
| When request completes | Framework writes response and finishes request processing | Reactive chain completes (`onComplete`), errors (`onError`), or cancels (`cancel`), tied to HTTP handling |
| Context and core beans | Reused across many requests | Reused across many requests |

These are **common models**, not claims that "Servlet cannot be asynchronous" or "Reactive runs only on a single thread". Servlet has async processing; WebFlux can switch schedulers and use multiple threads. The essential difference lies in **the request-handling and I/O contract**.

## 4. Runnable Example: Same Application Lifecycle, Two Request Models

Using **Java 17+**, **Gradle**, and **Spring Boot 3.3.13**. We build a small web application, then switch between Spring MVC and WebFlux to compare. Use only **one** web starter at a time.

### 4.1. File Structure

~~~text
runtime-boundary-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/runtime/
    ├── RuntimeBoundaryApplication.java
    └── GreetingController.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'runtime-boundary-demo'
~~~

`build.gradle` for the **Servlet/MVC version**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
}

springBoot {
    mainClass = 'com.example.runtime.RuntimeBoundaryApplication'
}
~~~

File `src/main/java/com/example/runtime/RuntimeBoundaryApplication.java`:

~~~java
package com.example.runtime;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class RuntimeBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeBoundaryApplication.class, args);
    }

    @Bean
    ApplicationRunner startupRunner() {
        return args ->
                System.out.println("LIFECYCLE: runner executed");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("LIFECYCLE: application ready");
    }

    @PreDestroy
    public void onDestroy() {
        System.out.println("LIFECYCLE: context closing");
    }
}
~~~

Here:

- `main` calls `SpringApplication.run` **once**.
- `ApplicationRunner` executes after the context refreshes and before the application is marked ready.
- The `ApplicationReadyEvent` listener runs when startup reaches the ready milestone; it does not run per HTTP request.
- `@PreDestroy` is tied to bean destruction when the context closes normally. It does not run after a controller returns a response.

File `src/main/java/com/example/runtime/GreetingController.java` for the **Servlet/MVC version**:

~~~java
package com.example.runtime;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping(
            value = "/api/greeting",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String greet(
            @RequestParam(name = "name", defaultValue = "friend") String name) {
        System.out.println("REQUEST: MVC handler invoked");
        return "Hello, " + name;
    }
}
~~~

With `@RestController`, the `String` return value is the **HTTP response body**, not a view name. `produces = MediaType.TEXT_PLAIN_VALUE` specifies the content type. No user data is stored in any controller field.

### 4.2. Running the Servlet/MVC Version

In the directory containing `build.gradle`, with a compatible Gradle installed:

~~~bash
gradle bootRun
~~~

If the project has a Gradle Wrapper, you can use `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows.

Once the application is running, in a second terminal:

~~~bash
curl -s "http://localhost:8080/api/greeting?name=Lan"
~~~

**HTTP response body** (excluding HTTP headers):

~~~text
Hello, Lan
~~~

The `System.out.println` lines written in our code appear in meaning as:

~~~text
LIFECYCLE: runner executed
LIFECYCLE: application ready
REQUEST: MVC handler invoked
~~~

Both `LIFECYCLE` lines appear during startup, while the `REQUEST` line appears when sending the request. Framework logs may interleave; do not rely on framework log ordering. When calling the URL twice, the `REQUEST` line appears again, whereas runner/ready **do not rerun**.

Under `spring-boot-starter-web`'s default configuration, Tomcat receives the HTTP request and Spring MVC dispatches it to `GreetingController.greet`. Each request may use a separate server thread, while the controller instance is typically shared across requests.

### 4.3. Switching to WebFlux/Reactive

**Keep** `settings.gradle` and `RuntimeBoundaryApplication.java` unchanged. In `build.gradle`, swap only the web dependency:

~~~groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

This **replaces the entire `dependencies` block** of the MVC version, rather than adding WebFlux alongside `spring-boot-starter-web`. Next, replace `GreetingController.java` with:

~~~java
package com.example.runtime;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    @GetMapping(
            value = "/api/greeting",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> greet(
            @RequestParam(name = "name", defaultValue = "friend") String name) {
        return Mono.fromSupplier(() -> {
            System.out.println("REQUEST: WebFlux publisher executed");
            return "Hello, " + name;
        });
    }
}
~~~

`Mono<String>` represents a publisher emitting at most one value. `Mono.fromSupplier(...)` defers invoking the supplier until the publisher is **subscribed** to. In normal WebFlux HTTP handling, the framework subscribes to the publisher and writes the emitted value to the response. The handler **does not need** to call `subscribe()` or `block()` itself.

Stop the MVC version, then run again with the WebFlux dependency:

~~~bash
gradle bootRun
~~~

Send the same request:

~~~bash
curl -s "http://localhost:8080/api/greeting?name=Lan"
~~~

The response body remains:

~~~text
Hello, Lan
~~~

Startup milestones `LIFECYCLE: runner executed` and `LIFECYCLE: application ready` still occur only once per startup. For the request just sent, the log prints:

~~~text
REQUEST: WebFlux publisher executed
~~~

The difference lies in the request-handling infrastructure and the `Mono` return contract, **not** that every publisher spawns a new `ApplicationContext`. One context and its singleton beans still serve very many requests.

**Note for running the example:** Always stop the previous application before launching the new version to avoid port 8080 collisions. If `server.port` is set via deployment config or environment variables, use the actual port rather than assuming 8080.

## 5. Comparing Per-Request Lifecycles

### Servlet/MVC: From Request to Response

Common model:

~~~text
Client
  → Embedded Tomcat
  → Servlet Filter chain
  → DispatcherServlet
  → HandlerMapping / HandlerAdapter
  → @RestController
  → Return value / HttpMessageConverter
  → HTTP response
~~~

Requests can be rejected, time out, fail validation, or hit server errors. The framework has dedicated error handling; in Spring MVC this commonly involves `HandlerExceptionResolver` and `@ExceptionHandler`/`@RestControllerAdvice`. A handler error normally affects only the relevant request; it does not mean the context closes.

The Servlet API has its own request/response model and allows using `HttpServletRequest` and `HttpServletResponse` when needed. However, do not store a request object in a singleton for later use; the request becomes invalid once its processing cycle ends.

### WebFlux/Reactive: Publisher and Termination Signals

Common model:

~~~text
Client
  → HTTP server (typically Reactor Netty)
  → WebFilter chain
  → DispatcherHandler
  → Reactive handler/controller
  → Mono / Flux publisher
  → ServerHttpResponse / encoded body
      ├─ onNext + onComplete (success)
      ├─ onError (error)
      └─ cancel (canceled or no subscriber left)
~~~

`Mono`/`Flux` are not a "new request" or "new bean". They are contracts describing work and data signals; code inside a lazy publisher typically runs upon subscription. A pipeline can be canceled when a client disconnects or due to logic like timeouts, though exact timing and observability depend on the server, operators, and response stage. Do not assume every TCP disconnect always delivers `cancel` at one fixed line of code.

Illustrative snippet inside a WebFlux handler:

~~~java
@GetMapping("/api/slow")
public Mono<String> slow() {
    return Mono.fromSupplier(() -> "done");
}
~~~

This is an **illustrative snippet**, not a standalone Java file; adding it to a controller requires importing `GetMapping` and `Mono` as in the earlier example. `fromSupplier` here does not create slow processing; it merely illustrates deferred value production. If actual blocking calls such as synchronous JDBC or `Thread.sleep` exist, do not run them directly on the event loop merely because the handler returns `Mono`.

### Common Ground

- The framework creates/holds controller beans in the context; HTTP requests typically just **invoke existing beans**.
- Singleton beans can be invoked concurrently. Keep per-request state in local variables, parameters, or an appropriate context.
- Never call `SpringApplication.run(...)` inside an HTTP handler to "open a session" for a user.
- Normal error responses or client-canceled requests do not trigger `ApplicationReadyEvent`, do not require rebuilding the context, and do not fire `@PreDestroy` for the whole application.
- Only when the application encounters severe failures outside request handling or undergoes an intentional shutdown can the context close; distinguish that from an isolated HTTP error.

## 6. Concurrency Boundaries, ThreadLocal, and Blocking I/O

### Servlet Does Not Mean "One Dedicated Thread Forever per Request"

In synchronous Spring MVC, the server usually assigns a request-handling thread for most of the handler's execution; many requests share a thread pool. Servlet 3+ also supports asynchronous requests, so a request is not bound to a single thread for its entire lifecycle.

Therefore:

- Do not spawn `new Thread(...)` per request when the framework/executor already provides suitable tools.
- Bound the duration of blocking operations; configure timeouts and resource limits.
- If using `ThreadLocal` or request-scoped data, understand how the framework sets and clears it, especially across async dispatches.

### Reactive Does Not Mean "Changing Return Type Makes It Non-Blocking"

Example **to avoid** in a WebFlux handler:

~~~java
@GetMapping("/api/bad")
public Mono<String> bad() {
    return Mono.fromSupplier(() -> {
        try {
            Thread.sleep(1000); // Blocking: risks occupying the event loop.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
        return "done";
    });
}
~~~

This is an illustrative snippet, not a standalone file. `Thread.sleep` remains blocking even when wrapped inside `Mono`. Avoid calling `block()` on non-blocking threads, especially the event loop, as it can throw runtime errors or render the system unresponsive.

If a legacy blocking library must be used, the common pattern is to **isolate the task** on an appropriate scheduler instead of running it on the event loop:

~~~java
@GetMapping("/api/legacy")
public Mono<String> legacy() {
    return Mono.fromCallable(() -> legacyBlockingCall())
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

This is also **illustrative code**, assuming `legacyBlockingCall()` is defined and `Mono`, `Schedulers` are imported. This does not turn a blocking library into a non-blocking one and still requires concurrency limits, timeouts, cancellation handling, and resource bounds. Using non-blocking clients/I/O is preferable when supported.

In a Reactive pipeline, do not assume `ThreadLocal` data automatically propagates across every thread hop. For data carried along the processing chain, use appropriate mechanisms such as **Reactor Context** or APIs provided by Spring WebFlux/Security/Observation.

## 7. Startup, Readiness, and Accepting Requests Are Three Distinct Signals

### Context Startup Completion Is Not Enough to Guarantee Successful Serving

In a web application, the embedded server is initialized during context refresh. The HTTP socket may already be listening **before** `ApplicationReadyEvent` is published and before the readiness state officially transitions to **ACCEPTING_TRAFFIC**.

That explains why:

- **The port being open** does not prove all runners, initial data, or business checks have completed.
- **Context refresh completing** does not mean every HTTP request will succeed.
- If the system uses a load balancer/Kubernetes, a proper **readiness probe** is needed to decide when to route traffic.

`ApplicationRunner` and `CommandLineRunner` run after refresh. If a runner performs long tasks or fails, reaching ready takes longer or startup fails. Do not put infinite work, endless consumers, or non-terminating loops directly inside a runner if you expect the application to reach ready.

### Tracking Readiness with Actuator (Optional)

You can add to the dependencies of **either** example version:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
~~~

Then create `src/main/resources/application.properties`:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

When Actuator, compatible probes, and enabled endpoints are present, common health URLs include:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

In Kubernetes environments, Spring Boot supports automatically enabling the corresponding health groups under documented conditions; the property above helps test them elsewhere. **Liveness** answers whether the process should be restarted; **readiness** answers whether new traffic should be sent to the instance. These probes do not automatically check all external dependencies; reflecting mandatory business conditions requires configuring appropriate health indicators.

**Do not query readiness on every request to decide whether beans exist.** Readiness is a process- and traffic-management signal; controllers still rely on per-request error handling, validation, and timeouts.

## 8. Shutdown: Impact on In-Flight Requests

When the JVM receives a supported termination signal or the context closes cleanly, Spring manages shutting down the server and beans. This is **application lifecycle**, yet in-flight requests may still be running, requiring a shutdown strategy.

Sample configuration in `application.properties`:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Meaning:

- `server.shutdown=graceful` asks supporting servers to shut down gracefully: stop accepting new traffic and give active requests a chance to complete, with exact behavior depending on the server.
- `spring.lifecycle.timeout-per-shutdown-phase=30s` sets **the maximum wait deadline per `SmartLifecycle` shutdown phase**; it is not a promise that every request finishes in exactly 30 seconds.
- When the timeout expires, an error occurs, or the process is **force-killed**, an in-flight request can be severed mid-way. Graceful shutdown does not replace client-side timeouts, idempotency, or retry logic.

Between Spring MVC/Servlet and Spring WebFlux/Reactive, servers may handle rejecting new requests/connections differently during shutdown. Do not assume one identical HTTP status code is returned in every case.

A managed bean's `@PreDestroy` callback runs when the bean is destroyed during a normal close sequence; this is far from "end of each request" and is also not guaranteed if the JVM is killed abruptly.

If the application runs long jobs, consumers, or background processing, design it to receive stop signals, stop picking up new work, await/hand off active work when possible, and close resources. That is a **whole-process lifecycle** concern, not a single Filter/WebFilter.

## 9. Exception Lifecycle and Error Scope

The same exception has different consequences depending on where it happens:

| Where Did the Error Occur? | Typical Consequence | Appropriate Handling |
| --- | --- | --- |
| Constructor or bean initialization during startup | Context refresh may fail, `run` throws an exception, app never becomes ready | Fix configuration, bean dependencies, startup conditions; inspect startup logs |
| `ApplicationRunner` during startup | Can fail startup before ready | Do not swallow critical errors; validate startup data/tasks |
| MVC controller handling a request | Request receives an error status; context normally keeps serving other requests | Exception handlers, validation, observability, timeouts |
| WebFlux publisher emitting `onError` | Request pipeline emits error; WebFlux handles it if response can still write an error | Reactive error handling; avoid manual `subscribe` calls |
| Client disconnects/cancels | That request pipeline may be canceled; does not shut down the app | Design proper task cancellation, cleanup, and retries |
| Severe resource failure, OOM, or process killed | Can impact the whole process including active requests | Monitoring, resource limits, restart/recovery, and durable state |

For instance, an endpoint returning an error does not necessarily emit `ContextClosedEvent`. Likewise, `@RestControllerAdvice`/`@ExceptionHandler` handle HTTP errors within MVC/WebFlux scope; they are not a substitute for handling failures at `SpringApplication.run`.

## 10. Common Confusions and How to Fix Them

**Confusion 1: "Every request goes through `SpringApplication.run`."**

False. `run` starts the context and server; afterward requests are routed by the server/framework to handlers on the existing context. Calling `run` inside a controller can create extra contexts, causing port collisions or resource leaks.

**Confusion 2: "Controllers are created fresh on every call."**

By default `@RestController` is a singleton. Shared mutable fields easily cause race conditions or data leaks across requests. Move per-request data into parameters/local variables and design lifecycle state properly.

**Confusion 3: "WebFlux is just Servlet with more parallel processing."**

Spring WebFlux has its own handler model and reactive pipeline. `WebFilter` is not Servlet `Filter`; `DispatcherHandler` differs from `DispatcherServlet`. Do not apply Servlet request-thread assumptions directly to all Reactive pipelines.

**Confusion 4: "Returning Mono makes blocking operations non-blocking."**

A `Mono` can still contain blocking code. Inspect which I/O actually blocks, which scheduler executes it, concurrency bounds, and timeouts.

**Confusion 5: "If a controller throws an error, Spring Boot automatically restarts."**

Normally request errors are translated into error responses or error signals for that request; the application context keeps running. Only startup/lifecycle failures or severe process faults threaten the entire process.

**Confusion 6: "`@PostConstruct` and `@PreDestroy` are per-request callbacks."**

They belong to the bean lifecycle. Servlet filters or WebFlux filters handle the request path; per-request cleanup code must attach to the appropriate request mechanism, not `@PreDestroy` on a singleton controller.

**Confusion 7: "Port 8080 open means already ready."**

Port listening can happen before runners finish. Use readiness probes and deployment mechanisms to avoid routing traffic too early.

**Confusion 8: "Graceful shutdown always finishes sending complete responses for all requests."**

Shutdown has deadlines and depends on server, client, load balancer, and task duration. Handle timeouts, controlled reconnect/retry, and idempotency for operations with side effects.

**Confusion 9: "Having both spring-webmvc and spring-webflux makes handlers automatically choose Reactive."**

Spring Boot typically infers Servlet when both stacks are present; application type must be verified from dependencies and configuration. `WebClient` can be used as an HTTP client in an MVC application without switching the request server to WebFlux.

**Confusion 10: "Request completion always closes transactions, subscriptions, and resources under the exact same rules in all cases."**

Transactions, subscriptions, and resources must be managed by the corresponding framework/I/O mechanisms. For instance, Servlet async, streaming publishers, and request cancellation produce different cleanup timings; understand the actual handler and server contracts.

## 11. Practice Exercises and Self-Check Questions

1. Run the Servlet/MVC version. Send three consecutive requests and count how many times the `LIFECYCLE`/`REQUEST` lines appear. Why do the counts differ?
2. Switch the dependency to WebFlux and update the controller to return `Mono<String>` as instructed. Call the same URL again. What changed in how the server/framework processes requests, and what did not change in the context lifecycle?
3. Add thread-name logging to both the startup runner and the controller. Send multiple concurrent requests. Should you write tests expecting the thread name to **always be fixed** across runs? Why or why not?
4. Predict what happens if you add `spring.main.web-application-type=none` to an app that has a controller: the bean may exist, yet why is the HTTP URL no longer available under standard web config?
5. Explain why a direct blocking I/O call on the WebFlux event loop is dangerous, even when the method returns `Mono`.
6. Install the Actuator readiness probe. Review the differences among `ApplicationStartedEvent`, runners, `ApplicationReadyEvent`, and readiness accepting traffic. Why should health be configured to fit the operational environment?
7. Enable graceful shutdown, trigger a long-running request, and send a normal stop signal. Observe the difference between tasks finishing before the deadline and tasks exceeding the deadline.
8. If a request throws an exception, identify the right handling scope: `@RestControllerAdvice` for the request or startup handling in `main`? Explain based on where the exception occurs.

## Knowledge Summary

- **Application lifecycle**: create context, start server/beans, runners, ready, operate, shut down.
- **Request lifecycle**: server receives, framework resolves route, handler produces result, writes response or handles error/cancel.
- **Servlet/MVC** and **Reactive/WebFlux** have distinct request pipelines while sharing the rule that one context can serve many requests.
- **ApplicationReadyEvent** is a startup milestone; **HTTP response**, **onComplete**, **onError**, or **cancel** belong to each individual request.
- **Graceful shutdown** bridges the two scopes: shutting down the application affects in-flight requests, without an absolute guarantee that every request completes.
- **Never build application lifecycle inside a handler** and never assume a request recreates all beans/context.

### References

- Spring Boot 3.3 — SpringApplication & Events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Framework — DispatcherServlet: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html
- Spring Framework — DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
