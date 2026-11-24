# `checkpoint`, `Hooks.onOperatorDebug`, and `ReactorDebugAgent` in Project Reactor

## 1. Goal: Finding Where a Reactive Chain Was Created

When a synchronous Java program throws an exception, the stack trace usually shows the call chain leading to the failing line of code. With Reactor, the processing flow is declared as a `Mono` or `Flux`, and only runs when subscribed to. Operators may emit signals across multiple threads, via schedulers, callbacks, or other libraries. Therefore, the stack trace at failure time often describes the execution path inside Reactor rather than the code location that assembled the operator chain.

The three main tools in this lesson solve that problem:

- **`checkpoint(...)`**: marks a reactive chain or a critical point in a chain. It has a variant that records only a light marker and a variant that captures a full stack trace.
- **`Hooks.onOperatorDebug()`**: enables global assembly debugging, recording operator creation sites for chains assembled after the hook is enabled.
- **`ReactorDebugAgent`**: uses a Java Agent/ByteBuddy to instrument call sites in classes, providing broad assembly information without capturing a stack trace for every operator like the global hook.

After this lesson, you will be able to:

1. Distinguish assembly time, subscription time, and signal execution time.
2. Understand why a normal `Mono`/`Flux` stack trace makes it hard to trace back to the line declaring the chain.
3. Place `checkpoint()` in the right position and choose between a light marker and a full stack.
4. Read the Reactor traceback attached as a suppressed exception.
5. Enable and reset `Hooks.onOperatorDebug()` at the right time.
6. Initialize `ReactorDebugAgent` before Spring Boot creates reactive chains.
7. Choose tools for local, test, staging, and production environments.
8. Use `StepVerifier` and `WebTestClient` to verify tracebacks without using `block()` in services.
9. Avoid global debug overhead, leaked global hooks across tests, and logs exposing sensitive data.

The hands-on example uses Java 17+, Spring Boot 3.3.5, Spring WebFlux, and Reactor 3.6.x with dependency versions managed by Spring Boot.

## 2. Three Phases to Distinguish

A reactive pipeline has three conceptual phases:

```text
ASSEMBLY
  Declare Mono/Flux and attach operators
       |
       v
SUBSCRIPTION
  Subscriber registers and demand begins
       |
       v
SIGNAL EXECUTION
  onNext / onError / onComplete flow through the chain
```

Example:

```java
Mono<String> result = Mono.just("42")
        .map(this::parseId)
        .flatMap(repository::findName);

return result;
```

- **Assembly**: the `just`, `map`, `flatMap` calls build the Publisher structure.
- **Subscription**: the framework or caller subscribes to the Publisher.
- **Execution**: operators process data and emit signals.

With a WebFlux controller, the framework subscribes to the returned publisher. There is no need to call `subscribe()` inside the controller or service.

### 2.1. Why Are Normal Stack Traces Often Hard to Read?

An exception may be detected in `MonoSingle`, `FluxMap`, `FluxFlatMap`, or a callback after a scheduler has switched threads. A runtime stack trace usually shows:

- The internal operator that detected the contract violation.
- `reactor.core.publisher.*` classes.
- `subscribe`, `request`, `onNext` calls.
- The application's final subscription point.

However, the subscription point is not necessarily where the chain was created. A service may build a `Mono` earlier, store it in a variable, or return it through several methods before it is subscribed to in a WebFlux adapter.

Failing example:

```java
Mono<String> oneName = Flux.just("An", "Binh")
        .map(String::toUpperCase)
        .single();
```

`single()` requires the source to emit exactly one element. The source here emits two elements, so the pipeline errors. The stack trace may focus on `MonoSingle` and operator internals; the reader needs to locate the `.single()` line in application code.

Assembly tracebacks add information about **where the operator was declared**, helping connect runtime errors to the source code that created the chain.

### 2.2. Assembly Tracebacks Do Not Replace the Root Cause

Reactor's traceback helps answer:

- Which operator was assembled in which file/class/line?
- Through which chain segments was the error observed?
- Where was the chain constructed via a reusable `transform`?

It does not by itself explain why data was invalid, why a database rejected a query, why upstream timed out, or why a business rule failed. Always read the original exception and cause chain alongside the assembly traceback.

## 3. Reading a Reactor Traceback

When assembly debugging is active, Reactor can attach a suppressed exception to the original exception. The added section typically contains parts such as:

1. **Assembly trace from producer**: where the failing operator was assembled.
2. **Error has been observed at the following site(s)**: the operators/chains that received the error signal.
3. **Original Stack Trace**: the initial runtime stack trace.

Abbreviated structure illustration:

```text
java.lang.IllegalStateException: remote store unavailable
    at ...

Suppressed: The stacktrace has been enhanced by Reactor
Assembly trace from producer [reactor.core.publisher.MonoFlatMap]:
    at com.example.OrderService.findById(OrderService.java:42)

Error has been observed at the following site(s):
    |_ Mono.flatMap  at OrderService.findById(OrderService.java:42)
    |_ Mono.checkpoint at OrderService.findById(OrderService.java:43)

Original Stack Trace:
    at ...
```

This is an illustrative shape, not a fixed output across every Reactor version. Producer names, line numbers, and sections vary by operator, version, and chain structure.

### 3.1. Root Marker and Observed Sites

When an error traverses multiple operators or multiple branches sharing a single source, the traceback can mark where the error originated and list the points that observed it. This lets you distinguish:

- The operator that produced the error.
- Operators that forwarded the error.
- A chain composed from a reusable transformation.
- Multiple branches observing the same error.

Do not just look for the first line containing `reactor`. Look for the assembly trace section and match the class/method/line of application code.

### 3.2. Tracebacks Are Usually Suppressed Exceptions

You can iterate over suppressed exceptions:

```java
for (Throwable suppressed : error.getSuppressed()) {
    if (Exceptions.isTraceback(suppressed)) {
        log.debug("Reactor assembly traceback: {}", suppressed.getMessage());
    }
}
```

Import:

```java
import reactor.core.Exceptions;
```

Do not manually append tracebacks to exception messages or replace the original exception just to make logs easier to read.

If Reactor creates a composite exception, tracebacks can also appear in the component list when unwrapped. Useful APIs include:

```java
Exceptions.unwrapMultiple(error);
Exceptions.unwrapMultipleExcludingTracebacks(error);
Exceptions.isTraceback(error);
```

Use `unwrapMultipleExcludingTracebacks` when you need the component errors without treating an assembly traceback as a separate business error.

### 3.3. Be Careful with Reused Exceptions

Do not store an exception that carries suppressed tracebacks in a static field and throw it repeatedly. Tracebacks may keep getting appended to the suppressed list of the same object, accumulating data and causing memory growth.

Creating a new exception per failure is usually clearer and safer. Avoid optimizing with static exception instances when pipelines use assembly tracebacks.

## 4. `checkpoint()` Marks a Specific Chain

`checkpoint` is an operator that can be placed directly in a `Mono` or `Flux` chain. Unlike the global hook, it only adds information for the chain where the operator is used.

There are three main forms:

| API | Additional Information | Relative Cost |
|---|---|---|
| `checkpoint()` | Captures full assembly stack | Higher than light marker |
| `checkpoint("id")` | Adds description/marker only | Lower than full stack |
| `checkpoint("id", true)` | Description and full assembly stack | Higher than light marker |
| `checkpoint("id", false)` | Equivalent to light marker | Lower than full stack |

### 4.1. Full Stack with `checkpoint()`

```java
Mono<Order> result = repository.findById(id)
        .map(this::toOrder)
        .flatMap(this::enrich)
        .checkpoint();
```

When an error travels from upstream through the checkpoint, Reactor can attach a full assembly stack trace for the checkpoint site.

Use when:

- Investigating a hard-to-reproduce bug.
- Needing to know the exact place where the chain was created.
- The cost of stack capture on a few critical chains is acceptable.

### 4.2. Light Marker with `checkpoint(String)`

```java
Mono<Order> result = repository.findById(id)
        .map(this::toOrder)
        .flatMap(this::enrich)
        .checkpoint("orders.findById");
```

A light marker does not capture a full stack trace at the checkpoint site. It puts a description into the traceback so readers can find the related operation.

The description must be specific enough to distinguish chains. Use stable names like:

```text
orders.findById
billing.calculateInvoice
catalog.refreshCache
```

Avoid generic descriptions like `"checkpoint"` or `"error"`.

### 4.3. Choosing Full Stack with Description

```java
Mono<Order> result = repository.findById(id)
        .map(this::toOrder)
        .checkpoint("orders.repository.lookup", true);
```

The boolean argument `true` requests a full stack trace along with the description. `false` uses a light marker similar to `checkpoint(String)`.

Using static descriptions per operation is usually easy to operate. If you include a correlation ID in the description, ensure the value is sanitized and contains no tokens, emails, personal data, or secrets.

## 5. Where Should You Place `checkpoint`?

A checkpoint only observes errors propagating from upstream through it. Errors originating downstream after the checkpoint do not travel backward to be annotated by that checkpoint.

Example:

```java
Mono<String> result = repository.findById(id)
        .map(this::toDto)
        .flatMap(this::enrich)
        .checkpoint("orders.lookup")
        .map(this::render);
```

The checkpoint can attach a traceback for errors from `findById`, `toDto`, or `enrich`. If `render` downstream emits an error, the earlier checkpoint does not observe that error.

Therefore, place the checkpoint near the end of the chain segment you want to observe:

```java
Mono<String> result = repository.findById(id)
        .map(this::toDto)
        .flatMap(this::enrich)
        .map(this::render)
        .checkpoint("orders.lookup.response");
```

### 5.1. Checkpoints at Service Boundaries

A readable pattern:

```java
@Service
public class OrderService {

    public Mono<OrderView> find(String id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new OrderNotFoundException(id)))
                .map(this::toView)
                .flatMap(this::attachPricing)
                .checkpoint("orders.find");
    }
}
```

The checkpoint describes a use case rather than adding markers to every operator. If the error is still hard to pinpoint, add narrower checkpoints at specific adapters or upstream branches.

### 5.2. Multiple Checkpoints in One Pipeline

```java
Mono<OrderView> result = repository.findById(id)
        .checkpoint("orders.repository")
        .map(this::toView)
        .flatMap(pricingClient::enrich)
        .checkpoint("orders.pricing")
        .map(this::toResponse)
        .checkpoint("orders.response");
```

Markers help segment important boundaries. You do not need to add a checkpoint after every simple `map`; too many redundant markers lengthen tracebacks and reduce diagnostic value.

### 5.3. A Method Returns a Publisher and the Caller Chains More Operators

```java
Mono<Order> servicePublisher = service.find(id);

Mono<String> response = servicePublisher
        .map(this::render)
        .checkpoint("http.order.response");
```

A checkpoint inside `service.find` cannot observe an error created by `render` in the caller. If you want to inspect the entire HTTP response pipeline, place a checkpoint at the final boundary of that pipeline or add a checkpoint in the method containing the failing operator.

### 5.4. Checkpoints Do Not Fix Errors

Checkpoints do not:

- Retry requests.
- Recover connections.
- Change backpressure.
- Fix invalid data.
- Turn exceptions into success responses.
- Guarantee every downstream error is observed.

They attach the assembly location to errors for faster investigation.

## 6. `Hooks.onOperatorDebug()` Enables Global Assembly Debugging

If you do not yet know which chain might fail, Reactor provides a global debug mode:

```java
Hooks.onOperatorDebug();
```

The hook instruments operator creation calls and records stack traces at assembly time. When an error occurs later, Reactor can attach tracebacks for operators created while the hook was active.

### 6.1. Must Be Enabled Before Creating Publishers

Correct:

```java
public static void main(String[] args) {
    Hooks.onOperatorDebug();

    SpringApplication.run(Application.class, args);
}
```

Ineffective for chains already assembled before the hook was enabled:

```java
static final Mono<String> PREBUILT =
        Mono.just("value").map(String::toUpperCase);

public static void main(String[] args) {
    Hooks.onOperatorDebug();
    // PREBUILT was already assembled before the hook was enabled.
}
```

Placing the hook at the start of `main` before Spring creates beans and reactive pipelines avoids this issue.

### 6.2. Performance Impact

`Hooks.onOperatorDebug()` is global. It affects all `Mono`/`Flux` assembled after the hook is enabled in the process, not just one request or one service.

The notable cost is capturing stack traces at operator assembly. This can increase pipeline creation time and allocations, especially when the application builds many chains or operators on hot paths.

Use the global hook for:

- Local debugging.
- Controlled tests.
- One-off error reproduction on staging.
- Situations requiring broad assembly traces where the cost is acceptable.

Do not enable it by default in production just to make logs more informative. Consider `checkpoint(String)` or `ReactorDebugAgent` first.

### 6.3. Disabling the Hook with `resetOnOperatorDebug()`

```java
Hooks.onOperatorDebug();

try {
    // Assemble and run the pipeline under investigation.
}
finally {
    Hooks.resetOnOperatorDebug();
}
```

`Hooks.resetOnOperatorDebug()` removes the debug hook installed by `onOperatorDebug`.

This is global state, not a per-subscriber setting. Do not toggle the hook per HTTP request or inside a reactive callback. If multiple tests run in parallel, one test resetting the hook can affect another test. Keep tests that use global hooks isolated, run sequentially, or protected by appropriate synchronization.

## 7. `ReactorDebugAgent`: Instrumenting Call Sites with a Java Agent

`ReactorDebugAgent` belongs to the `io.projectreactor:reactor-tools` artifact. The agent uses ByteBuddy to instrument application classes as they are loaded, allowing Reactor to obtain assembly information without capturing a stack trace on every operator call like `Hooks.onOperatorDebug()`.

### 7.1. Adding the `reactor-tools` Dependency

With Maven and Spring Boot dependency management:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-tools</artifactId>
</dependency>
```

When using the Reactor BOM managed by Spring Boot, you do not need to specify a separate version. Keep `reactor-tools` compatible with the `reactor-core` selected by the BOM; do not mix Reactor versions from different release trains arbitrarily.

### 7.2. Early Initialization in `main`

```java
import reactor.tools.agent.ReactorDebugAgent;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        ReactorDebugAgent.init();
        SpringApplication.run(Application.class, args);
    }
}
```

Call `init()` before `SpringApplication.run(...)` so the agent is ready to instrument classes as they are loaded and reactive chains are created.

The agent fits when you want broad assembly debugging in an environment running longer than local debugging without enabling global stack capture on every operator.

### 7.3. When Classes Were Already Loaded Before `init()`

If some classes/call sites were already loaded before the agent initialized, you can ask the agent to reprocess existing classes:

```java
ReactorDebugAgent.init();
ReactorDebugAgent.processExistingClasses();
```

`processExistingClasses()` has to scan loaded classes and apply transformations; this operation can take several seconds. Only use it when you detect already-loaded call sites were not instrumented. The better approach in normal applications is calling `init()` very early.

### 7.4. Self-Attach Limitations and the `-javaagent` Option

`ReactorDebugAgent.init()` uses ByteBuddy self-attach. Some JVM/runtime policies disallow attaching to the current process itself. If self-attach does not work, you can run reactor-tools as a Java Agent at JVM startup:

```bash
java -javaagent:reactor-tools.jar -jar app.jar
```

The `reactor-tools.jar` path must point to the actual JAR file distributed with the application. When running in containers, place the agent JAR at a fixed location and configure the JVM startup command accordingly.

### 7.5. Build-Time Instrumentation

Reactor Tools also supports a ByteBuddy Maven/Gradle plugin to instrument classes during the build. This requires configuring the plugin and the `reactor-tools` dependency with the appropriate classifier according to Reactor's documentation.

Note: build-time transformation applies only to the instrumented project's classes; libraries on the dependency classpath are not automatically instrumented by that step. This is a separate build/deployment option and does not need to be added to a minimal learning project.

### 7.6. How Does the Agent Differ from the Global Hook?

- `Hooks.onOperatorDebug()` captures stack traces when operators are created after the hook is enabled; capture cost occurs during assembly.
- `ReactorDebugAgent` instruments bytecode to add assembly info to call sites in classes; it avoids capturing a stack trace on every operator call the way the global hook does.
- Neither replaces `checkpoint` when you want to clearly mark a specific use case.
- There is no need to enable both the Agent and the global hook at the same time without a specific diagnostic reason.

## 8. Comparing and Choosing Tools

| Tool | Scope | Full Stack at Assembly? | Cost/Conditions | Best Fit |
|---|---|---|---|---|
| No debug enabled | Default | No | Low | Normal production |
| `checkpoint("id")` | Single chain | No, light marker | Lower than full checkpoint | Marking critical boundaries |
| `checkpoint()` | Single chain | Yes | Captures stack at checkpoint | Investigating a specific error |
| `checkpoint("id", true)` | Single chain | Yes + description | Captures stack at checkpoint | Need both stack and clear label |
| `Hooks.onOperatorDebug()` | Global | Yes, on operators assembled after hook | Higher due to stack capture on operators | Controlled local/test/reproduction |
| `ReactorDebugAgent` | Instrumented call sites | Has assembly info | Agent attach/instrument at startup or class load | Staging/production diagnosis needing broad traces |

### Recommendations by Environment

**Local development**

- Start with `checkpoint("service.operation")`.
- When you do not know which chain is failing, enable `Hooks.onOperatorDebug()` at process startup.
- Use `log()` or `doOnError` to inspect signals and causes.

**Unit/integration tests**

- Place checkpoints at key service boundaries.
- You can use the global hook in an isolated test, but must reset it with `finally`.
- Assert that a traceback exists rather than comparing the entire stack trace, since line numbers change across builds.

**Staging**

- Can enable `ReactorDebugAgent` early to investigate bugs requiring broad assembly information.
- Measure startup, memory, and latency before/after the change.
- Turn off debug settings that are no longer needed after investigation.

**Production**

- Prefer light checkpoints at operationally valuable boundaries.
- Use the agent under evaluated operational procedures when broad assembly debugging is needed.
- Avoid enabling the global hook by default across all operators in high-load processes.

## 9. Checking Tracebacks with the Java API

Tracebacks are attached as suppressed exceptions. You can write a helper:

```java
static boolean hasReactorTraceback(Throwable error) {
    return Arrays.stream(error.getSuppressed())
            .anyMatch(Exceptions::isTraceback);
}
```

Imports:

```java
import java.util.Arrays;
import reactor.core.Exceptions;
```

Usage in tests:

```java
StepVerifier.create(service.find("fail"))
        .expectErrorSatisfies(error -> {
            assertTrue(error instanceof IllegalStateException);
            assertTrue(hasReactorTraceback(error));
        })
        .verify();
```

Do not assert the entire stack trace string. It contains files/lines, internal classes, and content dependent on the compiler, Reactor version, and code layout. Assert stable properties instead:

- The original exception has the expected type.
- A suppressed traceback is present.
- Key descriptions appear when the API provides descriptions.
- The Publisher terminates with the expected `onError` or response status per contract.

### 9.1. Cause Chain and Suppressed List Are Two Different Things

- `getCause()` follows wrapped causes.
- `getSuppressed()` lists exceptions attached alongside the original exception.
- Reactor assembly tracebacks typically reside in the suppressed list.

Do not inspect only `getCause()` and conclude there is no traceback. When handling composite errors, use the appropriate `Exceptions` helpers to distinguish tracebacks from business errors.

## 10. Observing Signals with `log()`, `doOnError`, and Metadata

Assembly tracebacks tell you where a chain was created. When you need to know **which signals actually occurred**, you can use other tools.

### 10.1. `log()`

```java
Flux<Integer> values = Flux.range(1, 5)
        .log("orders.stream")
        .take(2);
```

`log()` can record events such as:

- `onSubscribe`
- `request(n)`
- `onNext`
- `onError`
- `onComplete`
- `cancel`

Where `log()` is placed affects which operators are observed. For example, placing it before `take(2)` shows downstream requesting limited demand and cancelling upstream after two elements.

`log()` is very helpful in local debugging, but should not be enabled indiscriminately on streams with large or sensitive payloads. Check logger levels and appender configuration to avoid recording tokens, personal data, or request contents.

### 10.2. `doOnError`

```java
return repository.findById(id)
        .doOnError(error ->
                logger.warn(
                        "order lookup failed: type={}",
                        error.getClass().getSimpleName()))
        .checkpoint("orders.repository.lookup");
```

`doOnError` observes errors for logging/metrics; it does not turn an error into success on its own. Do not swallow errors by logging and dropping the publisher.

### 10.3. `name()` and `tag()`

```java
Mono<Order> result = repository.findById(id)
        .name("orders.findById")
        .tag("component", "order-service")
        .checkpoint("orders.findById");
```

`name`/`tag` provide metadata for introspection/observation when tooling supports it. They are not equivalent to assembly stack traces and do not replace checkpoints.

## 11. Integrating with Spring WebFlux

In WebFlux, controllers/services usually return a `Mono` or `Flux` to the framework. Therefore, the location where the chain was assembled can be far removed from when the Netty thread handles the error.

A useful way to organize it:

```text
HTTP request
    |
    v
Controller
    |
    v
Service reactive chain
    |---- checkpoint("orders.find")
    |
    v
Repository / WebClient
    |---- checkpoint("orders.remote")
    |
    v
onError
    |
    +---- original cause
    +---- Reactor assembly traceback
```

### 11.1. Do Not Use `block()` Just to Make Stack Traces Readable

Do not add `.block()` or `.subscribe()` just so exceptions appear on the current thread. Doing so changes the execution model, can block the event loop, or detaches errors/cancellation from the request lifecycle.

Keep reactive composition and add checkpoints where observation is needed.

### 11.2. Spring Boot Initializes the Agent Before Creating Beans

With ReactorDebugAgent, call `init()` at the start of `main` before `SpringApplication.run`. Beans and services created afterward will be loaded in the process with the agent already initialized.

If tests use `@SpringBootTest`, Spring Test may bootstrap the application context without calling the application's `main` method. Therefore, tests should not assume the agent was initialized just because the main class contains `ReactorDebugAgent.init()`. The unit tests below use checkpoints and isolated global hooks to verify behavior.

### 11.3. WebClient and Library Boundaries

When a chain calls WebClient, placing a checkpoint at the service boundary helps locate where the outbound publisher was assembled. Assembly traces can show which operator was created in application code; they do not automatically turn HTTP 500, DNS, or TLS failures into detailed root causes. Combine them with the cause chain, HTTP status, request ID, and WebClient observation/metrics.

## 12. Runnable Java 17+ Project: Spring Boot WebFlux and Reactor Tools

The sample project includes:

- Spring Boot 3.3.5 and Java 17.
- Spring WebFlux endpoint `/orders/{id}`.
- `OrderService` with a light checkpoint at the end of the pipeline.
- `ReactorDebugAgent.init()` before Spring Boot starts.
- Unit tests verifying that checkpoints attach tracebacks.
- A test enabling `Hooks.onOperatorDebug()` before assembling a chain and resetting it in `finally`.
- An integration test using `WebTestClient` verifying service errors produce HTTP 5xx.

Spring Boot's Maven dependency management selects compatible Reactor versions. Do not declare an arbitrary `reactor-tools` version that differs from Reactor Core.

### 12.1. Project Structure

```text
reactor-debugging-webflux/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/edu/demo/debug/
    │   │   ├── DebuggingApplication.java
    │   │   ├── OrderService.java
    │   │   └── OrderController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/edu/demo/debug/
            └── OrderDebuggingTests.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>reactor-debugging-webflux</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-tools</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

`reactor-tools` is added to provide `ReactorDebugAgent`. The project still uses `checkpoint` independently of the agent; if an agent is not needed in a module, that dependency can be removed while keeping Reactor Core APIs.

### 12.3. `DebuggingApplication.java`

```java
package edu.demo.debug;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

import reactor.tools.agent.ReactorDebugAgent;

@SpringBootApplication
public class DebuggingApplication {

    public static void main(String[] args) {
        ReactorDebugAgent.init();
        SpringApplication.run(DebuggingApplication.class, args);
    }
}
```

The agent is initialized before Spring creates the application context and application beans.

If the environment does not allow ByteBuddy self-attach, run the JVM with a Java Agent:

```bash
java -javaagent:reactor-tools.jar -jar target/reactor-debugging-webflux-1.0.0.jar
```

Replace `reactor-tools.jar` with the actual JAR path. You do not need to also call `Hooks.onOperatorDebug()` if you have already chosen the Agent for the same assembly debugging goal.

### 12.4. `OrderService.java`

```java
package edu.demo.debug;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class OrderService {

    public Mono<String> find(String id) {
        return Mono.just(id)
                .map(String::trim)
                .flatMap(this::load)
                .checkpoint("orders.find");
    }

    private Mono<String> load(String id) {
        if ("fail".equals(id)) {
            return Mono.error(
                    new IllegalStateException(
                            "simulated order store failure"));
        }

        return Mono.just("order:" + id);
    }
}
```

The checkpoint is placed after `flatMap`, so it can observe errors originating from `load` upstream. It uses a light marker and does not capture a full stack at the checkpoint site.

### 12.5. `OrderController.java`

```java
package edu.demo.debug;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders/{id}")
    public Mono<String> find(@PathVariable String id) {
        return orderService.find(id);
    }
}
```

The controller returns the publisher to WebFlux. Do not subscribe or block in the controller.

### 12.6. `application.properties`

```properties
spring.application.name=reactor-debugging-webflux
logging.level.edu.demo.debug=DEBUG
```

In production, choose appropriate log levels and appenders. Do not turn on logging of sensitive payloads or headers just to observe stack traces.

### 12.7. `OrderDebuggingTests.java`

```java
package edu.demo.debug;

import java.time.Duration;
import java.util.Arrays;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.Exceptions;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Hooks;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderDebuggingTests {

    @Autowired
    OrderService orderService;

    @Autowired
    WebTestClient webTestClient;

    @Test
    void checkpointAddsAssemblyTraceToUpstreamFailure() {
        StepVerifier.create(orderService.find("fail"))
                .expectErrorSatisfies(error -> {
                    assertTrue(error instanceof IllegalStateException);
                    assertTrue(hasTraceback(error));
                })
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void globalHookCapturesAssemblyWhenEnabledBeforeAssembly() {
        Hooks.onOperatorDebug();

        try {
            Mono<String> failing = Mono.just("value")
                    .map(value -> {
                        throw new IllegalArgumentException("bad value");
                    });

            StepVerifier.create(failing)
                    .expectErrorSatisfies(error ->
                            assertTrue(hasTraceback(error)))
                    .verify(Duration.ofSeconds(3));
        }
        finally {
            Hooks.resetOnOperatorDebug();
        }
    }

    @Test
    void webFluxEndpointPropagatesServiceFailureAsServerError() {
        webTestClient.get()
                .uri("/orders/fail")
                .exchange()
                .expectStatus().is5xxServerError();
    }

    private static boolean hasTraceback(Throwable error) {
        return Arrays.stream(error.getSuppressed())
                .anyMatch(Exceptions::isTraceback);
    }
}
```

The global hook test enables the hook **before** creating the failing `Mono` and resets it in `finally`. Global hooks are process-wide state; do not run this test in parallel with other tests that also modify Reactor hooks.

The `checkpoint` test verifies that a traceback is attached to the exception. The HTTP test confirms WebFlux returns a server error when the service emits an error. The exact response content can depend on Spring Boot's error handling and application configuration.

### 12.8. Running the Project

From the directory containing `pom.xml`:

```bash
mvn test
```

Run the server:

```bash
mvn spring-boot:run
```

Call the success path:

```bash
curl -i http://localhost:8080/orders/42
```

Expected body:

```text
order:42
```

Call the failure path:

```bash
curl -i http://localhost:8080/orders/fail
```

The expected HTTP response is a 5xx status; server-side logs contain the original exception and may include the Reactor traceback from the checkpoint/agent. The full stack trace depends on the logger, configuration, and Reactor version, so no fixed hypothetical output is given.

**The sample test suite has 3 test methods.** This is the expected result when running Maven, not a claim that Maven was executed in the authoring environment.

## 13. Step-by-Step Diagnosis

When a reactive error is hard to trace to its source, you can follow this workflow:

1. **Find the original exception**: read the class, message, and cause chain. Determine whether the error stems from validation, codec, database, timeout, or operator contract.
2. **Determine the timing**: did the error happen while assembling the chain, when subscribing, or during `onNext`/`onError` execution?
3. **Locate operators likely to violate a contract**: such as `single`, `next`, `flatMap`, `zip`, `switchIfEmpty`, `collectList`.
4. **Add light checkpoints** at relevant service/repository/client boundaries.
5. **Reproduce with a full-stack checkpoint** if a marker is not enough.
6. **Enable `Hooks.onOperatorDebug()`** in an isolated process/test if you do not yet know which chain caused the error.
7. **Use ReactorDebugAgent** when broad assembly information is needed without having the global hook capture stacks at every operator.
8. **Cross-reference the traceback with the source** and fix the actual root cause.
9. **Remove temporary debug settings** or keep operationally valuable light checkpoints.
10. **Add a regression test** reproducing the bug so it does not return.

### 13.1. Example: Cardinality Error

```java
Mono<String> result = Flux.just("one", "two")
        .single();
```

`single()` requires exactly one item, but the source has two. The fix depends on business logic:

```java
Mono<String> first = Flux.just("one", "two")
        .next();
```

`next()` takes the first element and does not require the source to emit only one element. If business logic requires exactly one item, keep `single()` and fix the source/contract. Debugging shows the line that created the operator; it does not decide the right semantics for the application.

### 13.2. Example: Error Inside a Lambda

```java
Mono<Integer> result = Mono.just(10)
        .map(value -> value / 0)
        .checkpoint("pricing.divide");
```

The root cause is division by zero inside the lambda. The checkpoint helps locate where the chain was created; the original exception is still `ArithmeticException`.

### 13.3. Example: Error from Upstream

```java
Mono<String> result = remoteClient.fetch()
        .checkpoint("catalog.remote.fetch")
        .onErrorMap(error ->
                new CatalogUnavailableException("catalog unavailable", error));
```

The checkpoint sits before `onErrorMap`, so it can attach a traceback to the upstream error before the error is wrapped. If you need a traceback at the boundary layer after mapping, place a checkpoint at the end of the chain according to your observation goal and test the actual cause/suppressed behavior.

## 14. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Reading only the runtime stack trace | Only see Reactor internals or subscription site | Read the assembly traceback or add a checkpoint |
| Enabling `Hooks.onOperatorDebug()` after chains were assembled | Old chains have no corresponding capture | Enable the hook very early before creating Publishers |
| Using the global hook for every request | Increases assembly cost across the whole process | Use light checkpoints or the Agent |
| Placing a checkpoint before the failing downstream operator | The checkpoint does not observe that error | Place the checkpoint after the chain segment to monitor |
| Using `"checkpoint"` as the description in many places | Cannot tell which specific chain failed | Use a sufficiently unique operation ID |
| Using `checkpoint()` on every operator | Long tracebacks and higher stack-capture cost | Place at meaningful service/adapter boundaries |
| Thinking a checkpoint fixes or retries errors | The original error still occurs | Fix the cause or design retry separately |
| Inspecting only `getCause()` | Misses suppressed tracebacks | Inspect `getSuppressed()` and `Exceptions.isTraceback` |
| Comparing the entire stack trace verbatim in tests | Tests are brittle across lines/versions | Assert exception type and presence of traceback |
| Not resetting the global hook in tests | Leaks global state to other tests | `try/finally` with `Hooks.resetOnOperatorDebug()` |
| Running hook-mutating tests in parallel | Results depend on execution order | Isolate tests/global resources or run sequentially |
| Calling `ReactorDebugAgent.init()` after Spring creates beans | Some already-loaded call sites are not instrumented | Init before `SpringApplication.run` |
| Always calling `processExistingClasses()` | Slows startup/tests by several seconds | Only use when classes are already loaded and call sites are uninstrumented |
| JVM disallows self-attach | Agent init fails | Use `-javaagent` at startup |
| Enabling both Agent and global hook unnecessarily | Increases complexity and debug cost | Pick one global mechanism matching your goal |
| Logging full payloads/headers when debugging | Exposes tokens or personal data | Log route, correlation ID, exception type, and masked metadata |
| Reusing an exception with a suppressed traceback | Suppressed list can accumulate | Create a new exception per failure |
| Using `block()` to keep stack traces synchronous | Can block the event loop and alter semantics | Keep the reactive pipeline and add checkpoints |
| Thinking the Agent instruments every third-party library | Wrong expectations about call-site scope | Identify which classes are instrumented and use checkpoints at boundaries |

## 15. Operational Checklist

### Assembly and checkpoint

- Have you identified which chain segment needs observation?
- Is the checkpoint placed after the upstream section whose errors must be caught?
- Is the description sufficiently unique while containing no secrets/PII?
- Did you choose a light marker or full stack based on need?
- Is there a regression test for the discovered bug?

### Global hook

- Is the hook enabled before assembling Publishers?
- Have you evaluated the process-wide cost?
- Is it enabled only in intentional environments?
- Is it reset in tests or diagnostic tools?
- Is the global hook never toggled per request?

### ReactorDebugAgent

- Is the `reactor-tools` version compatible with the Reactor BOM?
- Does `init()` run before the Spring Boot context?
- Does the JVM allow self-attach?
- Is there a `-javaagent` plan if self-attach is blocked?
- Is `processExistingClasses()` only called when truly needed?
- Have startup/latency and instrumented class call sites been measured/verified?

### Logging and security

- Do logs preserve the root cause?
- Are tracebacks recognized among suppressed exceptions?
- Are raw tokens, passwords, cookies, or sensitive payloads excluded from logs?
- Are static exceptions that could accumulate suppressed tracebacks avoided?
- Does the log appender avoid blocking the event loop?

### Testing

- Is there a test for the success path?
- Is there a test for the error path and exception type?
- Is there a test verifying the checkpoint produces a traceback?
- Is there a test verifying the global hook is enabled before assembly and reset afterward?
- Is there an integration test via WebTestClient if errors travel over HTTP?
- Do tests avoid depending on fixed stack trace line numbers?
- Do global hook tests avoid running in parallel with other hook-modifying tests?

## 16. Self-Check Exercises

**Exercise 1.** Why does a Reactor runtime stack trace often not point directly to the line declaring `map` or `flatMap`?

**Answer:** Because execution is asynchronous; the stack trace usually reflects where signals were processed/subscribed and operator internals, while the chain may have been assembled in a different method.

**Exercise 2.** How does `checkpoint()` differ from `checkpoint("orders.lookup")`?

**Answer:** `checkpoint()` captures a full assembly stack for the chain; `checkpoint(String)` adds a light description marker and relies on the description to locate the site, without capturing a full stack at the checkpoint.

**Exercise 3.** What does `checkpoint("id", true)` mean?

**Answer:** It adds a description and forces a full stack trace; `false` uses a light marker.

**Exercise 4.** Why is a checkpoint usually placed near the end of the chain segment to monitor?

**Answer:** It only observes errors traveling from upstream through the checkpoint; errors originating downstream after the checkpoint do not get a traceback added by that checkpoint.

**Exercise 5.** When must `Hooks.onOperatorDebug()` be enabled?

**Answer:** Before the `Mono`/`Flux` to be observed are assembled; typically enabled at the beginning of `main`.

**Exercise 6.** Why is the global hook expensive?

**Answer:** It captures stack traces at operator assembly for chains created after the hook is enabled, impacting the process broadly.

**Exercise 7.** Which API resets the operator debug hook?

**Answer:** `Hooks.resetOnOperatorDebug()`.

**Exercise 8.** Where should `ReactorDebugAgent.init()` run in Spring Boot?

**Answer:** Before `SpringApplication.run(...)`, so the agent instruments call sites as application classes are loaded.

**Exercise 9.** When should `processExistingClasses()` be called?

**Answer:** When the agent is initialized late and already-loaded classes need to be re-instrumented; the operation can take several seconds, so do not call it routinely if unnecessary.

**Exercise 10.** How do you determine whether a suppressed exception is a Reactor traceback?

**Answer:** Iterate over `Throwable.getSuppressed()` and use `Exceptions.isTraceback(Throwable)`.

**Exercise 11.** If self-attach does not work on the JVM, what approach should be used?

**Answer:** Start the JVM with `-javaagent:reactor-tools.jar`.

**Exercise 12.** Does `checkpoint` make a request automatically retry when a remote service fails?

**Answer:** No. It only attaches assembly info to the error; retry is a separate policy and must be designed according to business semantics.

## 17. Key Takeaways

- Reactor distinguishes assembly, subscription, and signal execution; runtime stack traces are often insufficient to find where a chain was declared.
- Assembly tracebacks add operator creation sites and the points along the chain that observed the error.
- `checkpoint()` captures a full stack for a single chain; `checkpoint(String)` uses a light marker; `checkpoint(String, true)` includes both a description and a full stack.
- A checkpoint only catches upstream errors passing through it; place it after the chain segment you want to observe.
- `Hooks.onOperatorDebug()` is a global hook that must be enabled before chain assembly and incurs stack-capture cost on operators created afterward.
- `Hooks.resetOnOperatorDebug()` removes the global debug hook.
- `ReactorDebugAgent` from `reactor-tools` instruments call sites via a Java Agent/ByteBuddy; call `init()` before Spring Boot startup.
- `processExistingClasses()` is for already-loaded classes and can take several seconds; do not use it routinely if early init is possible.
- If the JVM does not support self-attach, use `-javaagent` at startup.
- Tracebacks are typically suppressed exceptions; use `Exceptions.isTraceback` to detect them.
- `log()` observes signals/demand/cancellation; `checkpoint` helps find assembly sites. Both tools answer different questions.
- Never log sensitive payloads/credentials, never hold static exceptions with suppressed tracebacks, and never use `block()` just to make reactive code look synchronous.
- Choose `checkpoint` for a single chain, the global hook for controlled reproduction, and the Agent for broad assembly debugging with lower runtime overhead than global stack capture.

**Diagnostic rule:** find the original exception first, identify where the chain was assembled, place checkpoints at the right boundaries, and only enable the global hook or Agent when a broader observation scope is needed.

## 18. Official Documentation

- Project Reactor Reference — **Debugging Reactor**: https://projectreactor.io/docs/core/3.6.11/reference/debugging.html
- Project Reactor 3 Reference — **Activating Debug Mode, checkpoint and ReactorDebugAgent**: https://projectreactor.io/docs/core/release/reference/debugging.html
- Reactor Core 3.6.11 Javadoc — **`Flux.checkpoint()` / `checkpoint(String)` / `checkpoint(String, boolean)`**: https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html
- Reactor Core Javadoc — **`Hooks.onOperatorDebug()` and `resetOnOperatorDebug()`**: https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Hooks.html
- Reactor Core Javadoc — **`Exceptions.isTraceback` and composite exception utilities**: https://projectreactor.io/docs/core/3.6.11/api/reactor/core/Exceptions.html
- Reactor Tools — **ReactorDebugAgent and ByteBuddy instrumentation**: https://projectreactor.io/docs/core/release/reference/debugging.html#production-ready-global-debugging
- Spring Boot 3.3.5 — **Dependency versions and Reactor BOM**: https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-dependencies/3.3.5
- Spring Framework — **WebFlux reactive application infrastructure**: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/reactive-spring.html