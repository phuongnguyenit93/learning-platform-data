# Restoring Trace Links When Missing a Builder, Propagation, or Async Context

A request flowing from an orders service to an inventory service can still return HTTP 200 while the two services appear in two separate traces. The business flow ran properly, yet the metadata describing the relationship between operations was lost at a boundary.

This lesson shows how to find that exact boundary and fix three classes of causes: an HTTP client not receiving Spring Boot's observation config; the two HTTP ends not writing/reading the same context format; and an async task not receiving the submitting thread's context. Examples use Spring Boot 3.3.x, Spring Framework 6.1, and Micrometer Tracing with Java 17+ source code. Do not use Boot 2-era Spring Cloud Sleuth configuration.

## 1. What Needs to Be Reconnected?

A **trace** is the journey of a request or job across multiple operations. A **span** is a single recorded operation along that journey. **Trace context** holds the data needed to identify the journey and parent–child relationships, such as trace ID, span ID, and sampling flag.

| Component | Role | Common misconception |
| --- | --- | --- |
| Trace ID | Identifies the same journey | Two services logging does not mean they share a trace |
| Span ID | Identifies a single operation | Not every span in a trace has the same span ID |
| Instrumentation (attaching observation to operations) | Creates and finishes an observation/span for HTTP, tasks, or other operations | Having Actuator does not instrument objects created directly with `new` |
| Propagation (transmitting context) | Writes context onto the transport and reads it back on the receiver | Putting trace ID into logs does not propagate context over HTTP |
| Scope (current active context scope) | Lets running code access the current observation/span | A span existing does not mean it is currently active on this thread |
| Exporter and trace storage backend | Sends and stores spans for search and display | Valid linking does not guarantee data was sent/stored successfully |

For a synchronous HTTP call, the model to observe is:

```text
orders: server span
    -> orders: HTTP client span
        -> context in HTTP request
            -> inventory: server span
```

The trace ID must stay connected end-to-end if both services accept that context. In the example's W3C config without Brave span joining, operations have distinct span IDs. The `parent-id` field in `traceparent` on the request from orders to inventory is the ID of the HTTP client span in orders, not necessarily equal to the span ID in the orders controller.

If work switches to an executor before making the HTTP call, there is an additional boundary:

```text
HTTP-receiving thread in orders
    -> submit task to executor
        -> restore context on worker thread
            -> instrumented HTTP client
                -> HTTP request carries context
```

The right builder solves how the HTTP client is created. Propagating context across the executor determines which parent trace the HTTP client runs under. These two conditions complement each other.

## 2. Diagnose by Boundary, Do Not Guess by Feel

Pick a reproducible request and record: the trace ID at the call site, the context actually leaving the HTTP client, the headers actually arriving at the receiving service, and the trace ID on the receiver. In a local test environment, you can set sampling probability to 1 to reduce noise. Do not infer the cause solely from a trace UI screenshot.

| Symptom | Hypothesis to verify first |
| --- | --- |
| Current span exists in orders, yet outbound request lacks trace header | HTTP client is uninstrumented or uses a different propagation format |
| Client emits header yet inventory never receives it | Proxy, gateway, or intermediate layer stripped/overwrote the header |
| Inventory receives header yet creates a different trace ID | Incompatible format, invalid header, or receiver intentionally rejects external context |
| Sync call links fine, call via executor splits | Context lost across thread handoff or task runs on an unexpected executor |
| Worker has no parent span yet outbound request carries a new trace header | Instrumented HTTP client started a new trace; this did not reconnect the original trace |
| Both ends have the right trace ID yet trace backend lacks data | Check sampling, export delivery, collector errors, and search range |
| Logs lack trace ID yet code reads a current span | Check logging pattern and MDC integration before concluding tracing is lost |

Do not use both apps returning `/actuator/health` as proof that tracing works. Health, metrics, and tracing are separate capabilities.

## 3. First Case: HTTP Client Bypasses Boot's Builder

### 3.1. Why Adding the Dependency Alone Is Not Enough

When auto-configuration conditions are met, Boot supplies builders and applies customizers so HTTP clients use the application's observation mechanism. The HTTP client's observation together with the tracing handler creates spans and propagates context accordingly.

A manually instantiated client can send HTTP requests normally yet skip all those configurations. Even a Spring-managed bean is not automatically rewritten inside just because it is a bean: how the object is constructed still matters.

| Client | Way auto-configuration is easily bypassed | Preferred approach |
| --- | --- | --- |
| `RestTemplate` | `new RestTemplate()` or creating `new RestTemplateBuilder()` manually | Inject Boot-provided `RestTemplateBuilder` and call `build()` |
| `RestClient` | `RestClient.create()` or creating `RestClient.builder()` manually | Inject Boot-provided `RestClient.Builder` |
| `WebClient` | `WebClient.create()` or creating `WebClient.builder()` manually | Inject Boot-provided `WebClient.Builder` when the app has matching dependencies |

The deciding factor is not merely having the word `Builder` in code. A Boot-injected builder and a builder created via static factory methods do not share the application's default customizations.

In the complete example below, `inventoryClient` uses the injected builder; `rawInventoryClient` intentionally uses `RestClient.create(baseUrl)` to reproduce the bug. Both are beans and both call the exact same URL.

### 3.2. If Linking Still Breaks After Switching Builders

Inspect the exact object used at the call site:

1. Are you injecting the right bean, especially when multiple HTTP clients and `@Qualifier` exist?
2. Did code declare a custom builder bean causing Boot's auto-configuration to back off?
3. Is anything replacing the observation registry with an empty or no-op registry?
4. Does a customizer disable or overwrite observation config after the builder was customized?
5. Is an active tracing bridge and corresponding tracing handler present, or only metrics instrumentation?

Within a single application, use Boot-managed versions and pick one tracing bridge deliberately. Do not add both Brave and OpenTelemetry arbitrarily to try fixing missing traces. A system may use different implementations across services as long as they agree on context propagation.

If a library forces manual client creation, integrate observation/tracing using that library's proper API. Do not treat manually adding a header containing a trace ID as a full substitute for instrumentation.

## 4. Second Case: Both HTTP Ends Do Not Understand the Same Context

### 4.1. Agree on Format Before Investigating Deeper

Two common formats are W3C Trace Context and B3. With W3C, the primary header is `traceparent`; `tracestate` may accompany it for tracer-specific state. B3 uses either a single `b3` header or multi-header form such as `X-B3-TraceId`, depending on configuration.

Across the two Boot 3.3.x services in the lab, explicitly choose:

```yaml
management:
  tracing:
    propagation:
      type: w3c
```

Do not assume header names from the trace storage vendor. Brave can propagate W3C; using a specific trace storage system does not dictate the propagation protocol between two services.

For systems migrating protocols in phases, verify the format each service version actually accepts and emits. Do not flip production settings wholesale just to make one test pass.

### 4.2. Understanding `traceparent` Properly

A value used in testing:

```text
00-11111111111111111111111111111111-2222222222222222-01
```

For version `00`:

- `11111111111111111111111111111111` is a 32-hex-character trace ID.
- `2222222222222222` is the sender's 16-hex-character span ID.
- `01` has the sampled bit enabled.
- All-zero trace IDs or parent IDs are invalid.

The receiving service creates a server span from the extracted context. When that service calls downstream, its HTTP client creates context for the outbound operation and injects the corresponding header. Do not write a custom interceptor copying the incoming `traceparent` verbatim onto every outbound request: doing so can drop the link to the newly created client span.

HTTP header names are case-insensitive. Simply changing `Traceparent` to `traceparent` does not fix format mismatches or missing instrumentation.

### 4.3. Pinpointing Where the Header Vanishes

Observe in order:

```text
current context in orders
    -> header after client instrumentation
        -> header after proxy/gateway
            -> header inventory actually receives
                -> current context in inventory
```

A custom interceptor running before instrumentation injects headers may see the header still empty. Know where in the chain you are observing; the headers actually received by the downstream server are clearer evidence than logging too early on the client.

If the header arrives intact at inventory yet a new trace ID is created, check receiver configuration, header validity, and external context acceptance policy. A trust boundary may intentionally start a new trace; distinguish that design choice from a configuration bug.

Trace headers normally travel on requests. A response lacking `traceparent` does not prove propagation failed: frameworks are not required to echo that header back to the caller.

## 5. Third Case: Context Lost When Switching to Async

### 5.1. Why Changing Threads Can Split a Trace

In normal synchronous execution, the active context is bound to the thread via mechanisms like `ThreadLocal`. Executors reuse pooled threads; the worker thread running a task does not automatically inherit the submitting thread's context.

Places to inspect include:

- `@Async`.
- `ExecutorService.submit(...)` or `execute(...)`.
- `CompletableFuture.supplyAsync(...)` without passing an appropriate executor.
- Continuation stages such as `thenApplyAsync(...)` hopping onto another executor.
- Reactive chains crossing boundaries lacking context propagation integration.

`CompletableFuture` represents an asynchronous result, not a trace context propagation tool. `InheritableThreadLocal` is not a general fix for thread pools either, because thread creation differs from per-task submission.

### 5.2. Use a Decorator on the Right Executor

Spring Framework 6.1 provides `ContextPropagatingTaskDecorator`. In a Boot app with matching Micrometer integration, the decorator captures registered context at task submission, restores it while running, and restores the prior context on completion.

In the example, `traceExecutor` has the decorator; `plainExecutor` intentionally omits it. `@Async("traceExecutor")` must actually point to the configured executor.

The decorator does not create a new business span for every task. First and foremost, it restores the current context. An HTTP client inside the task still creates its own client span. If you need a dedicated span for a business operation, create a child observation/span with explicit lifecycle management after fixing context propagation.

Conditions easily overlooked:

1. `@Async` calls must pass through the Spring proxy. Calling `this.linked()` on the same object does not trigger normal `@Async` interception.
2. Both the bean containing the method and the executor bean must be Spring-managed.
3. Configuring the decorator on one executor while tasks actually submit to the common pool or another executor.
4. Capturing context while the parent context is still active. Capturing after already hopping to a context-less thread cannot recover lost info.
5. Propagating tracing context does not automatically propagate every other state such as transactions or `SecurityContext`.

### 5.3. When Using a Plain Executor

The snippet below is integration code placed inside a method that has a parent context, not a standalone program:

```java
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;
import java.util.concurrent.Executor;

// executor is already initialized and lifecycle-managed elsewhere.
void submitWork(Executor executor, Runnable work) {
    ContextSnapshot snapshot = ContextSnapshotFactory.builder()
            .build()
            .captureAll();
    executor.execute(snapshot.wrap(work));
}
```

Snapshot captures only context types with registered accessors. In custom integrations outside Boot, configure registries/accessors properly; adding the `context-propagation` dependency alone does not create a tracing system.

Do not hack around this with `MDC.put("traceId", ...)`. MDC is for logging; HTTP clients read context from observation/tracing, not from an arbitrary string placed in MDC. Always close manually opened scopes with `try-with-resources`; finish manually created spans in `finally` where appropriate to avoid context leaks across tasks sharing threads.

## 6. Hands-On Lab: Comparing Four Call Paths

### 6.1. Preparing a Standalone Project

Create the following test project. This is a standalone demo application requiring no edits to any existing repository's build config.

```text
trace-link-lab/
├── pom.xml
└── src/main/
    ├── java/demo/trace/
    │   ├── TraceLabApplication.java
    │   ├── ClientConfiguration.java
    │   ├── AsyncConfiguration.java
    │   ├── TraceCalls.java
    │   ├── AsyncCalls.java
    │   └── TraceController.java
    └── resources/application.yml
```

Use JDK 17+ and Maven. Version 3.3.5 below is pinned so the example has a concrete environment; this is not a recommendation for choosing a production deployment version.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>trace-link-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-brave</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>context-propagation</artifactId>
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
```

Actuator provides observation integrations; the Brave bridge connects Micrometer Tracing to the tracer implementation. No external trace storage system is needed to compare IDs/headers in the lab. Exporter dependencies and shipping config are separate if you also want to view a trace UI.

`src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: orders
management:
  tracing:
    sampling:
      probability: 1.0
    propagation:
      type: w3c
    brave:
      span-joining-supported: false
logging:
  pattern:
    level: "%5p [${spring.application.name:},%X{traceId:-},%X{spanId:-}]"
```

Probability 1.0 makes observation easier in the lab, not a propagation fix. W3C format is chosen on both processes. Disabling Brave span joining keeps the relationship between client spans and server spans clear.

### 6.2. Complete Source Code

`TraceLabApplication.java`:

```java
package demo.trace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TraceLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TraceLabApplication.class, args);
    }
}
```

`ClientConfiguration.java`:

```java
package demo.trace;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {
    @Bean
    RestClient inventoryClient(RestClient.Builder builder,
            @Value("${inventory.base-url:http://localhost:8081}") String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }

    @Bean
    RestClient rawInventoryClient(
            @Value("${inventory.base-url:http://localhost:8081}") String baseUrl) {
        return RestClient.create(baseUrl);
    }

    @Bean
    RestTemplate inventoryTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
```

`inventoryTemplate` illustrates creating `RestTemplate` via an injected builder. This lesson's endpoints use `RestClient`. No WebFlux dependency is needed just to run the lab.

`AsyncConfiguration.java`:

```java
package demo.trace;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {
    @Bean("traceExecutor")
    ThreadPoolTaskExecutor traceExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("trace-worker-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }

    @Bean("plainExecutor")
    ThreadPoolTaskExecutor plainExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("plain-worker-");
        return executor;
    }
}
```

Spring initializes and manages both executors because they are beans. Both executors have the same size so the observed difference is the decorator, not thread count.

`TraceCalls.java`:

```java
package demo.trace;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class TraceCalls {
    public record Snapshot(String traceId, String spanId) {}
    public record Seen(String traceId, String spanId, String incomingTraceparent) {}
    public record Result(String mode, Snapshot atCallSite, Seen downstream) {}

    private final Tracer tracer;
    private final RestClient client;
    private final RestClient rawClient;

    public TraceCalls(Tracer tracer,
            @Qualifier("inventoryClient") RestClient client,
            @Qualifier("rawInventoryClient") RestClient rawClient) {
        this.tracer = tracer;
        this.client = client;
        this.rawClient = rawClient;
    }

    public Snapshot snapshot() {
        Span span = tracer.currentSpan();
        if (span == null) {
            return new Snapshot("(none)", "(none)");
        }
        return new Snapshot(span.context().traceId(), span.context().spanId());
    }

    public Result call(String mode, boolean raw) {
        Snapshot before = snapshot();
        RestClient selected = raw ? rawClient : client;
        Seen seen = selected.get()
                .uri("/inventory")
                .retrieve()
                .body(Seen.class);
        return new Result(mode, before, seen);
    }
}
```

`atCallSite` is the context right before sending HTTP. If no current span exists, the code returns the exact string `"(none)"`. `downstream` contains the data returned by inventory. Recording at these two points distinguishes losing the parent on the worker from losing the HTTP header.

`AsyncCalls.java`:

```java
package demo.trace;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncCalls {
    private final TraceCalls calls;

    public AsyncCalls(TraceCalls calls) {
        this.calls = calls;
    }

    @Async("traceExecutor")
    public CompletableFuture<TraceCalls.Result> linked() {
        return CompletableFuture.completedFuture(calls.call("async-linked", false));
    }

    @Async("plainExecutor")
    public CompletableFuture<TraceCalls.Result> detached() {
        return CompletableFuture.completedFuture(calls.call("async-detached", false));
    }
}
```

Despite using `CompletableFuture.completedFuture(...)`, the method body runs on the executor when invoked via the `@Async` proxy. The work executes on that thread before creating the completed future. Separating `AsyncCalls` and the controller into two beans avoids same-object self-invocation bugs.

`TraceController.java`:

```java
package demo.trace;

import java.util.concurrent.CompletableFuture;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TraceController {
    private final TraceCalls calls;
    private final AsyncCalls asyncCalls;

    public TraceController(TraceCalls calls, AsyncCalls asyncCalls) {
        this.calls = calls;
        this.asyncCalls = asyncCalls;
    }

    @GetMapping("/inventory")
    public TraceCalls.Seen inventory(
            @RequestHeader(value = "traceparent", required = false) String header) {
        TraceCalls.Snapshot current = calls.snapshot();
        return new TraceCalls.Seen(current.traceId(), current.spanId(), header);
    }

    @GetMapping("/orders/sync")
    public TraceCalls.Result sync() {
        return calls.call("sync-linked", false);
    }

    @GetMapping("/orders/raw")
    public TraceCalls.Result raw() {
        return calls.call("sync-raw", true);
    }

    @GetMapping("/orders/async")
    public CompletableFuture<TraceCalls.Result> linked() {
        return asyncCalls.linked();
    }

    @GetMapping("/orders/async-detached")
    public CompletableFuture<TraceCalls.Result> detached() {
        return asyncCalls.detached();
    }
}
```

The inventory endpoint echoes the received header for local testing. This is data intentionally added to JSON by the app, not Spring's default trace-header response behavior.

### 6.3. Compiling and Running Two Processes

From the directory containing `pom.xml`, package:

```bash
mvn clean package
```

First terminal runs inventory:

```bash
java -jar target/trace-link-lab-1.0.0.jar --server.port=8081 --spring.application.name=inventory
```

Second terminal runs orders:

```bash
java -jar target/trace-link-lab-1.0.0.jar --server.port=8080 --spring.application.name=orders --inventory.base-url=http://localhost:8081
```

Both processes share the same codebase to keep the example compact, yet run in independent JVM contexts and communicate over HTTP. Wait for both to start successfully. If ports are already occupied by another app, change ports and `inventory.base-url` accordingly.

Third terminal:

```bash
curl --fail --silent http://localhost:8080/orders/sync
curl --fail --silent http://localhost:8080/orders/raw
curl --fail --silent http://localhost:8080/orders/async
curl --fail --silent http://localhost:8080/orders/async-detached
```

In Windows PowerShell where `curl` is an alias, use `curl.exe` to call the real cURL binary. Output is JSON; trace/span IDs change per request. Do not compare IDs from the four independent requests against one another.

### 6.4. How to Read the Results Accurately

Let `T` denote the trace ID of the current request in orders, and `U` denote a new trace ID distinct from `T`. These are notation for explaining relationships, not literal strings printed by the program.

| Endpoint | `atCallSite.traceId` | `downstream.traceId` | `downstream.incomingTraceparent` | Conclusion |
| --- | --- | --- | --- | --- |
| `/orders/sync` | `T` | `T` | Present, contains trace ID `T` | Builder and propagation link properly |
| `/orders/raw` | `T` | `U` | `null` | Raw client bypassed observation config |
| `/orders/async` | `T` | `T` | Present, contains trace ID `T` | Decorator preserved context across thread switch |
| `/orders/async-detached` | `"(none)"` | `U` | Present, contains trace ID `U` | Worker lost parent; client started a new trace for the HTTP call |

The last row is an important diagnostic point: **having a trace header does not mean it is still linked to the original request's trace**. The builder works, yet cannot recover a parent trace that was already lost before calling the client.

In the linked synchronous call path, `atCallSite.spanId` is the server span in orders. The parent ID in the header at inventory belongs to orders's client span. Do not require all three span IDs to be equal as proof of success.

### 6.5. Testing with a Known Incoming Trace ID

Send a valid W3C header into orders:

```bash
curl --fail --silent -H "traceparent: 00-11111111111111111111111111111111-2222222222222222-01" http://localhost:8080/orders/sync
```

In the lab configuration, these two fields must both be `11111111111111111111111111111111`:

- `atCallSite.traceId`.
- `downstream.traceId`.

The header in `downstream.incomingTraceparent` must retain that trace ID, while its parent ID belongs to the new client span in orders rather than copying `2222222222222222` verbatim. Re-running the command will generate different span IDs. Reuse fixed IDs only in controlled tests; independent business requests need proper trace identities.

### 6.6. Injecting Faults to Verify Hypotheses

Make one change at a time, restart the modified process, and compare within the same request:

1. Switch the active client to the raw client: trace ID still exists in orders, yet the header arriving at inventory disappears.
2. Switch `@Async("traceExecutor")` to `@Async("plainExecutor")`: no parent span exists on the worker; the HTTP client still emits a new context.
3. On inventory alone, switch propagation format to `b3` while orders still emits W3C: in this simple example carrying only the W3C header, inventory cannot use that context to link the trace. Seeing the header string in JSON does not prove the tracer accepted it.
4. Restore W3C on both sides and the decorated executor; verify the trace ID relationship again.

After each test, revert config to the baseline before testing the next cause. Do not enable multiple instrumentation mechanisms simultaneously, as that can create duplicate spans and obscure the root cause.

## 7. If the Call Path Uses WebClient or Reactor

The builder still matters for `WebClient`, yet a thread-pool `TaskDecorator` does not replace Reactor's context mechanism.

In a Boot 3.3.x app with Reactor and matching Micrometer integrations, you can use:

```yaml
spring:
  reactor:
    context-propagation: auto
```

Check both the injected builder and the context at subscription time of the reactive chain. Reactor context follows subscription/execution chains, not simply the thread assembling the chain.

Common mistakes include manually calling `subscribe()` detached from the current execution flow, spawning work outside the context-bearing chain, or reading `ThreadLocal` too early and assuming it holds for every execution. Do not call `block()` inside WebFlux handlers to force synchronous execution and mask context-loss bugs.

If a step delegates work onto a custom executor, inspect that exact boundary too. Reactor configuration does not automatically attach decorators to every executor the application creates.

## 8. Distinguishing Broken Linking from Missing Display Data

### Trace ID Exists, Yet the Trace Does Not Appear in Storage

Check in order:

- Was the span sampled and recorded?
- Has the span finished, or is it waiting on an incomplete task?
- Is the exporter configured and sending successfully?
- Are collector address, protocol, authentication, and connectivity right?
- Do service filters, search time range, and ingestion delay match?

The sample app configures no exporter, so it makes no promise of data appearing in Zipkin or another UI. It verifies linking via current context and headers.

### Sampling Is Not a Builder or Executor Fix

Sampling decisions affect span recording/export. Context can still propagate even when a trace is not sampled. Setting `probability: 1.0` does not instrument a raw client or propagate context into a plain executor.

Conversely, when upstream sampling context already exists, check how the tracer honors that decision. Do not treat local sampling probability as a guarantee every request across a distributed system will be stored.

### Matching Logs Are Not Enough Proof of Correctness

An application-propagated correlation ID can help search logs yet does not create parent–child span relationships. Do not put trace IDs into metric labels with unbounded cardinality just to aid troubleshooting. Use IDs in logs/traces for their proper roles and inspect relationships on a concrete request.

## 9. Criteria to Confirm Restoration

A fix can be considered complete when all of the following evidence is consistent:

1. The actual HTTP client called receives the intended observation/tracing configuration.
2. Both before task submission and inside task execution, context still belongs to the original trace when required by design.
3. Outbound requests carry the right context format, and the receiving service actually receives it.
4. The receiver creates a span belonging to the same trace with proper parent–child linkage; do not force all span IDs to match.
5. Repeating with multiple independent requests does not leak a prior task's trace onto later tasks.
6. Error or exception paths still properly close manually opened scopes and finish manually managed spans.
7. If a trace UI is required, also verify sampling and export delivery; do not use HTTP 200 as a substitute for that check.

When investigating, always ask at which boundary context was lost: client creation, HTTP propagation, or offloading work to another execution context. Restoring the exact boundary reconnects the journey without manually stitching trace IDs through logs or hand-crafted headers.
