# Distinguishing Assembly-Time and Execution-Time Stack Traces in Spring WebFlux and Project Reactor

## 1. Lesson Objectives

An error in a Spring WebFlux application can appear on a different thread, at a different time, far away from the line of code that defined the processing chain. Therefore, when reading an error from a `Mono` or `Flux`, you need to distinguish two questions:

1. **Execution/subscription time:** Where was the exception thrown or the `onError` signal emitted, and in what processing context?
2. **Assembly time:** At which line of code was the operator or reactive pipeline leading to the error declared?

A regular Java stack trace mainly answers the first question. The **assembly traceback** supported by Reactor helps answer the second question. The two complement each other; never treat an assembly traceback as a separate business exception or as proof that the error occurred the moment the application created the Mono/Flux.

This lesson focuses on understanding assembly time versus subscription time, how to read errors and suppressed tracebacks, choosing among `checkpoint`, `Hooks.onOperatorDebug()`, and `ReactorDebugAgent`, and a methodology for diagnosing errors in WebFlux chains.

## 2. Two-Phase Diagram

~~~text
          ASSEMBLY TIME                             EXECUTION TIME
     (build pipeline spec)                     (subscribe, run signals)

   buildOrderPipeline()                              HTTP request
          |                                                |
          v                                                v
    repository.findById(id)                              subscribe
          |                                                |
          v                                                v
    .flatMap(this::enrich)                        subscribe upstream
          |                                                |
          v                                                v
    .map(this::toDto)  --------------------------> mapper receives item
          |                                                |
          v                                                v
    .checkpoint("order-read")                           mapper throws
          |                                                |
          v                                                v
    return Mono<OrderDto>                           onError(exception)
                                                           |
                                                           v
                                                  WebFlux error handler
~~~

A call to `map(fn)` usually **does not execute fn at assembly time**. It creates an operator that stores the function `fn` to call later when a signal arrives. If `fn` throws `IllegalStateException` when data arrives, the Java stack trace will reflect the function call in the executing pipeline. Meanwhile, the assembly traceback can point to the `.map(this::toDto)` line in the service where the Mono was created.

### 2.1. Understand "Usually" Rather Than as an Absolute

Not all code in a method that builds a Publisher is completely lazy:

- Java expressions are evaluated **before** being passed to `Mono.just(value)` or `Flux.just(values)`.
- Some operators validate arguments when called; for example, passing `null` as a mapper can be rejected immediately at assembly time.
- `Mono.fromCallable(supplier)` and `Mono.defer(supplier)` defer function execution until subscription time.
- A hot source, an already started Future, or an external task can begin before there is a Reactor subscriber.
- `Mono.defer` can assemble **a new inner chain inside the subscription**, so the inner chain's assembly happens later.

Therefore, the "assembly first, execution later" model describes most cold/declarative pipelines, but it is not a claim that everything in a program is lazy.

## 3. What Is Assembly Time?

Assembly occurs when code calls operators to build a chain:

~~~java
Flux<Integer> numbers = Flux.just("10", "20", "bad")
        .map(Integer::parseInt)
        .filter(number -> number > 10);
~~~

At this step:

- Java calls `Flux.just`, `map`, and `filter`.
- Reactor creates the corresponding publisher/operator objects.
- The `Integer::parseInt` lambda has not run on the data yet.
- The `number -> number > 10` lambda has not run on the data yet.
- No subscriber has requested elements yet.

If the lines above are inside a `createReportFlow` method, the assembly site can be those lines inside `createReportFlow`, even though the error occurs later when a controller request is processed on another thread.

### 3.1. An Assembly Site Is Not the "Place Where the Exception Was Created"

The assembly stack is **recorded ahead of time** (if appropriate tracing is enabled) so that when an error occurs later, Reactor can add:

- Which operator was instantiated.
- Which class/method and line of code built the operator.
- Which operators observed the error signal as it passed through.
- The path of the error signal through the chain.

An assembly traceback does not mean the map/filter functions ran at assembly time. It is a **snapshot of where the operators were defined**.

## 4. What Is Execution Time?

Execution begins when the Publisher is subscribed to. For a WebFlux request/response, the framework typically subscribes to the Publisher returned from the controller/handler. In standalone code, subscription may be triggered by `subscribe()`, `block()`, or `StepVerifier`.

~~~java
Flux<Integer> numbers = Flux.just("10", "bad")
        .map(Integer::parseInt);

// None of the strings above have been parsed yet.

numbers.subscribe(
        value -> System.out.println("value=" + value),
        error -> System.out.println(
                "error=" + error.getClass().getSimpleName()));
~~~

Upon subscribing, Reactor starts emitting data; the mapper is called for `10` and then `bad`, at which point `NumberFormatException` is turned into `onError`.

Key events to remember:

| Phase | What happens? |
| --- | --- |
| Assembly | `map` is added to the chain |
| Subscription | Subscribers and Subscriptions are established |
| Demand | Downstream requests elements via `request(n)` |
| onNext | Data arrives; mapper/filter/flatMap run |
| onError | An exception is converted into an error signal |
| onComplete | The source finishes emitting successfully |
| cancel | Downstream does not want to receive more data |

**A runtime error inside a mapper does not mean a Java exception was thrown from the `.map(...)` call at assembly time.**

## 5. What Does a Normal Java Stack Trace Show?

Example:

~~~java
Mono<OrderDto> flow = repository.findById(orderId)
        .map(this::convertToDto);

return flow;
~~~

If `convertToDto` throws an exception, the runtime stack trace may contain:

~~~text
java.lang.IllegalStateException: invalid order data
    at example.orders.OrderService.convertToDto(OrderService.java:87)
    at reactor.core.publisher.FluxMapFuseable$MapFuseableSubscriber.onNext(...)
    at reactor.core.publisher.MonoJust.subscribe(...)
    at ...
~~~

This is an **illustrative example**; Reactor class names, frame ordering, and line numbers will vary by version, fusion, scheduler, source type, and logging setup.

A runtime stack trace helps determine:

- The error type and original message.
- Which user-code function threw the error if the exception was created directly there.
- Which operator/subscriber was executing.
- Part of the Java call stack at the time of the error.

However, it may **not indicate** which service/controller line assembled the chain if the flow crosses asynchronous boundaries, schedulers, callbacks, subscriptions created elsewhere, or code using shared helper pipelines.

For example, `Flux.single()` can throw `IndexOutOfBoundsException` when the source emits more than one element. The stack trace may contain many `MonoSingle`, `FluxFlatMap`, and `FluxMap` frames without making it clear where in application code `.single()` was inappropriately added.

## 6. Assembly Traceback Fills In the Missing Information

Reactor supports **assembly tracing**: recording where operators were created to attach as context when upstream emits an error.

An enhanced error can have the following sections:

~~~text
java.lang.IndexOutOfBoundsException: Source emitted more than one item
  at reactor.core.publisher.MonoSingle$SingleSubscriber.onNext(...)
  Suppressed: reactor.core.publisher.FluxOnAssembly$OnAssemblyException:
Assembly trace from producer [reactor.core.publisher.MonoSingle]:
  reactor.core.publisher.Flux.single(...)
  example.orders.OrderService.buildPipeline(OrderService.java:42)
Error has been observed at the following site(s):
  *______Flux.single   at example.orders.OrderService.buildPipeline(...)
  |_     Mono.flatMap  at example.orders.OrderController.read(...)
Original Stack Trace:
  ...
~~~

This is an **illustrative format**, not a fixed output. Reactor may change the format, branch markers, and operator names across versions.

How to read it:

1. **Primary exception:** `IndexOutOfBoundsException` describes the real error type.
2. **Assembly trace from producer:** the line of code that created the relevant operator (for example `.single()`).
3. **Error has been observed...:** the operators along the path that saw the error signal.
4. **Original Stack Trace:** the actual calls and frames on the execution path.
5. **Suppressed traceback:** attached debugging data; usually not a second error.

### 6.1. "Producer" Is Where the Error Originates in the Pipeline

If the error comes from `Flux.single()` because there was more than one element, the assembly site worth inspecting is where `single()` was called. If a map lambda throws, the point worth inspecting is `map` along with the lambda/data source. The "observed at" section also helps trace the path through downstream operators.

### 6.2. Multiple Branches and Multiple Observations

In `Mono.when`, `Flux.merge`, `flatMap`, or flows reusing a shared Publisher, the same error can travel through multiple branches. Reactor may record multiple observation sites or an "observed N times" note.

Therefore, **read the observation section as a signal graph**; do not treat every line in the enhanced trace as an independent exception.

## 7. Hooks.onOperatorDebug(): Enabling Global Assembly Tracing

Usage:

~~~java
Hooks.onOperatorDebug();
~~~

It must be enabled **before the operators to be observed are created**. It is typically placed at application bootstrap:

~~~java
public static void main(String[] args) {
    Hooks.onOperatorDebug();
    SpringApplication.run(MyWebFluxApplication.class, args);
}
~~~

When the hook is enabled, Reactor intercepts operator assembly to capture stack traces. Later, if an error signal passes through an instrumented operator, the error gets the additional traceback.

### 7.1. Why Enable It Before Assembly?

The following sequence does not provide full traces for pipelines created before the hook:

~~~java
Flux<Integer> flow = Flux.just("10", "bad")
        .map(Integer::parseInt);

Hooks.onOperatorDebug(); // Too late for the map already created.

flow.subscribe();
~~~

The hook only affects operators **assembled after the hook takes effect**. It cannot go back in time to reconstruct stack traces for older operators.

### 7.2. Cost and Scope

Global debug:

- Captures stack traces for a great many newly assembled operators.
- Increases CPU and allocation overhead.
- Can alter latency and throughput.
- Affects the entire process and other reactive chains, not just one request.
- Is useful when isolating hard-to-reproduce bugs in a controlled environment.

**Do not enable Hooks.onOperatorDebug unconditionally on a production hot path**, especially in high-RPS systems, without measuring performance. For production, prefer targeted `checkpoint(String)` or `ReactorDebugAgent` under an appropriate deployment model.

### 7.3. Turning Off the Hook in Tests/Demos

~~~java
Hooks.onOperatorDebug();

try {
    runDiagnostic();
}
finally {
    Hooks.resetOnOperatorDebug();
}
~~~

The hook is global process state; you must clean it up after tests so it does not affect other test cases. Resetting the hook **does not strip snapshots from Publishers assembled earlier**. Only operators created afterward are no longer instrumented.

Do not toggle the global hook on and off per HTTP request: it can affect other requests assembling concurrently.

## 8. checkpoint(): Placing a Marker at a Chosen Location

`checkpoint` is an operator for adding assembly information when an error passes through it.

Three forms:

~~~java
Mono<Order> a = source.checkpoint();

Mono<Order> b = source.checkpoint(
        "orders:load-by-id");

Mono<Order> c = source.checkpoint(
        "orders:load-by-id", true);
~~~

| Form | Captured Content | Cost | When to Use |
| --- | --- | --- | --- |
| `checkpoint()` | Full assembly stack trace | Higher | Investigating a specific pipeline where the call site is needed |
| `checkpoint("description")` | Light marker carrying only a label | Lighter | Production or flows whose location is already known |
| `checkpoint("description", true)` | Description plus full assembly stack | Higher | Deep debugging when both a label and call site are needed |
| `checkpoint("description", false)` | Equivalent to light marker | Lighter | Stable, easy-to-trace labels |

### 8.1. checkpoint(String) Does Not Capture a Full Stack Trace

~~~java
Mono<Order> result = orderRepository.findById(id)
        .flatMap(this::enrich)
        .map(this::validate)
        .checkpoint("orders:load-v2");
~~~

If upstream emits an error, the enhanced traceback can include the light checkpoint label `orders:load-v2`. It **does not necessarily record the file and line number** when using only a light marker. Therefore, choose a label unique enough for operators to locate the method/flow.

Good labels:

- `orders:load-by-id`
- `inventory:reserve-stock`
- `billing:calculate-total`
- `notifications:send-email`

Poor labels:

- `checkpoint`
- `error`
- `service`

A label that is too generic does not identify the assembly site.

### 8.2. Checkpoint Position Determines Which Errors Are Marked

Place a checkpoint downstream of the operators you want to monitor:

~~~java
return repository.findById(id)
        .flatMap(this::enrich)
        .map(this::convert)
        .checkpoint("order-read");
~~~

If an error originates in `findById`, `enrich`, or `convert` and passes through the checkpoint, the marker is attached.

If the checkpoint sits **before** the throwing operator:

~~~java
return repository.findById(id)
        .checkpoint("repository-read")
        .map(this::convert);
~~~

An error emitted by `convert` **after the checkpoint** will not travel backward through this checkpoint. Thus, the marker may not appear on errors from the mapper.

Rule: **a checkpoint observes error signals flowing from upstream to downstream**. Place it near the end of the logic section you want to mark; you can place multiple checkpoints at meaningful boundaries.

### 8.3. Checkpoint Does Not Handle Errors for You

`checkpoint` does not retry, does not convert HTTP statuses, does not swallow exceptions, and does not replace `onErrorResume` or `onErrorMap`. It is an observation tool.

~~~java
return callPartnerApi()
        .checkpoint("partner:fetch-offers")
        .onErrorMap(
                WebClientResponseException.class,
                error -> new PartnerApiException(
                        "Partner failure", error));
~~~

This is an illustrative snippet requiring the application's `callPartnerApi` and `PartnerApiException` types. Creating a new exception with `onErrorMap` can change the primary stack trace; preserve the original cause so you can still trace where the real error occurred.

### 8.4. Use Stable Names and Avoid Sensitive Data

A checkpoint description is metadata that can end up in error logs. Do not put bearer tokens, passwords, card details, or raw request bodies into the label. You can use static route names or non-sensitive business error codes.

If a correlation ID is needed, keep it in the log/tracing context and only include it in a checkpoint after checking privacy and cardinality. Generating a long new label per request can increase allocations and make searching harder.

## 9. Suppressed Exceptions and Exceptions.isTraceback

Reactor typically adds the assembly traceback as a suppressed exception on the primary Throwable:

~~~java
Throwable[] suppressed = error.getSuppressed();

for (Throwable candidate : suppressed) {
    if (Exceptions.isTraceback(candidate)) {
        System.out.println("Reactor assembly traceback detected");
    }
}
~~~

Points to remember:

- The primary Throwable is still the error to investigate, for example NumberFormatException.
- The assembly traceback describes the operator construction/observation path.
- Suppressed does not necessarily mean "secondary failure".
- A Throwable may have other suppressed exceptions unrelated to Reactor tracing.
- Reactor can also add a suppressed marker for `block()`; do not count every suppressed Throwable as an assembly trace.

In a composite error, such as when multiple branches fail and an operator merges the errors, the unwrapped list can contain tracebacks. Reactor provides `Exceptions.unwrapMultipleExcludingTracebacks(error)` to filter out trace entries when processing composite errors.

### 9.1. Do Not Strip Suppressed Traces When Logging

If you only log `error.getMessage()`:

~~~java
.doOnError(error ->
        log.warn("Request failed: {}", error.getMessage()))
~~~

you can lose the cause chain, suppressed assembly trace, and useful stack frames.

In an appropriate logging setup:

~~~java
.doOnError(error ->
        log.error("Order pipeline failed", error))
~~~

SLF4J loggers usually print the full throwable when using the proper overload. However, redact sensitive data in messages, tags, headers, and bodies before logging.

## 10. ReactorDebugAgent: An Instrumentation Option for Production

Besides the global debug hook, Reactor provides `ReactorDebugAgent` from the `reactor-tools` artifact. This approach instruments code using Byte Buddy and provides assembly information with lower overhead than creating a Throwable stack trace for every operator at runtime.

Add the dependency (version managed by the Reactor BOM/Spring Boot):

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-tools</artifactId>
</dependency>
~~~

Initialize early:

~~~java
import reactor.tools.agent.ReactorDebugAgent;

public static void main(String[] args) {
    ReactorDebugAgent.init();
    SpringApplication.run(MyWebFluxApplication.class, args);
}
~~~

**Note on class-loading lifecycle:** the agent instruments classes loaded after it is initialized. If classes were already loaded beforehand, `ReactorDebugAgent.processExistingClasses()` exists, but retransformation can take time. Do not call it on every request.

### 10.1. Environmental Constraints

`ReactorDebugAgent` uses Byte Buddy agent attachment; some JVMs/containers restrict self-attach. Depending on the environment, you may need to run with `-javaagent`:

~~~bash
java -javaagent:reactor-tools.jar -jar app.jar
~~~

This is illustrative syntax. You must supply the exact path and JAR version, and test the agent mechanism in your build, container image, and runtime.

Build-time instrumentation via a Byte Buddy plugin is also an option. Do not add an agent on your own without reviewing your organization's observability, performance, JVM flags, and deployment policies.

### 10.2. Comparing the Approaches

| Tool | Scope | Cost | Best Fit |
| --- | --- | --- | --- |
| `checkpoint("label")` | Single location only | Typically low | Critical production flows |
| `checkpoint()` | Single location, full stack | Higher than light | Investigating an already-narrowed case |
| `Hooks.onOperatorDebug()` | All operators assembled after enabling | High | Local/dev diagnostics |
| `ReactorDebugAgent` | Code instrumented by the agent | Lower than global stack capture | Production observability when agent setup is appropriate |

None of these tools replace logging, tracing, metrics, error classification, or unit/integration tests.

## 11. Recognizing Real-World Errors in WebFlux

Suppose a service has:

~~~java
Mono<OrderDto> getOrder(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)))
            .flatMap(this::fetchDetails)
            .map(this::toDto)
            .checkpoint("orders:get-order");
}
~~~

There are at least three distinct error groups:

1. A repository error, or empty converted into `OrderNotFoundException`.
2. `fetchDetails` may call WebClient and emit `WebClientRequestException` (connection) or `WebClientResponseException` (status).
3. `toDto` may throw an exception due to invalid data.

Within an HTTP request, operator code may execute on the Netty event loop or another Scheduler. The runtime trace may contain many framework frames; the checkpoint helps identify which **application flow** assembled the operators the error passed through.

### 11.1. Runtime Errors Are Not Always Network Errors

An HTTP 200 with a malformed body can cause `DecodingException` when WebClient decodes JSON. Alongside that technical error, a Java error thrown by your mapper after decoding is still an application-layer error.

Diagnose in order:

- What are the Throwable type and message?
- Does the cause chain contain an HTTP/network/codec error?
- Which user method in the runtime stack threw the error?
- Which operator does the assembly trace point to?
- Through which stages was the error observed?
- What are the corresponding request trace ID, route, and service dependency?

Do not see `FluxMapFuseable` and conclude reactor-core has a bug; your application's mapper may be what threw the exception.

### 11.2. Integrating WebFlux Exception Handling

`@RestControllerAdvice` and `@ExceptionHandler` can convert exceptions into consistent HTTP responses. **Do not lose the original exception before logging**:

~~~java
@RestControllerAdvice
class ApiErrors {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> badRequest(
            IllegalArgumentException error) {

        return ResponseEntity.badRequest()
                .body(Map.of("code", "BAD_INPUT"));
    }
}
~~~

This is an illustrative snippet for HTTP mapping code, not a complete exception-handling system. In practice, you need logging with correlation IDs, separation between internal errors and input errors, and you must not return stack traces or internals to browsers/clients.

Assembly tracebacks belong in server-side logs/diagnostics, **not in production response bodies**.

## 12. Eager Evaluation: Errors That Truly Happen at Assembly

The following two snippets look similar but have different timing.

### 12.1. Eager Value

~~~java
Mono<Integer> value =
        Mono.just(Integer.parseInt("oops"));
~~~

Java must evaluate `Integer.parseInt("oops")` before calling `Mono.just`. Therefore `NumberFormatException` is thrown immediately when creating the publisher; **there is no valid Mono to subscribe to yet**.

### 12.2. Deferred Supplier

~~~java
Mono<Integer> value =
        Mono.fromCallable(() -> Integer.parseInt("oops"));
~~~

At assembly time, Reactor receives a Callable. `parseInt` is only invoked after subscription. The exception becomes an `onError` signal; therefore `checkpoint` and Reactor error operators can observe it.

### 12.3. Deferring the Entire Publisher Creation

~~~java
Mono<Integer> value = Mono.defer(() ->
        Mono.just(Integer.parseInt("oops")));
~~~

`Mono.defer` postpones even the creation of the inner Mono until subscription. At subscribe time, Java calls parseInt, and the error is emitted as onError from the deferred publisher.

The difference from `Mono.just` shows up right at the assembly boundary. When debugging, determine which expressions are actually evaluated when the method is called, rather than looking only at the return type.

### 12.4. fromFuture Can Be an Eager Source

~~~java
CompletableFuture<Integer> future =
        CompletableFuture.supplyAsync(this::loadValue);

Mono<Integer> mono = Mono.fromFuture(future);
~~~

The Future can run before subscription. Even though the Mono awaits/observes the future's result, the external work has already started. The Mono's assembly traceback does not automatically describe the full call stack inside the future's thread pool.

To defer creating the future:

~~~java
Mono<Integer> mono = Mono.defer(() ->
        Mono.fromFuture(
                CompletableFuture.supplyAsync(this::loadValue)));
~~~

This is an illustrative snippet. Use an appropriate Executor and cancellation policy in production, and do not use the Common Pool for uncontrolled blocking I/O.

## 13. A Publisher Can Be Subscribed To Multiple Times

Example:

~~~java
Mono<Integer> flow = Mono.fromCallable(
        () -> Integer.parseInt("5"))
        .map(i -> i * 2);

Integer first = flow.block();
Integer second = flow.block();
~~~

Two `block()` calls correspond to two subscriptions against a cold pipeline. Assembly of `flow` usually happens once, whereas the Callable can execute twice.

Consequences:

- **The same assembly site** can be associated with multiple distinct runs.
- Runtime stacks/trace IDs help distinguish specific requests/subscriptions.
- An assembly traceback alone is not enough to know which subscription caused the error.
- If `cache()`, `share()`, or a hot source is used, subscription and re-execution have different semantics.
- If code uses `Mono.defer`, inner operators can be re-assembled for each subscription.

Do not hardcode a raw request ID into a shared Publisher and assume it accurately represents every subscription. Use Reactor Context or tracing spans to carry per-subscription metadata.

## 14. Schedulers and Why the Runtime Stack Differs from Source Code

Example:

~~~java
Mono<String> flow = Mono.fromCallable(
                () -> blockingClient.fetch())
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::normalize)
        .checkpoint("partner:normalize");
~~~

This is an illustrative snippet requiring the application's `blockingClient` and `normalize`.

- `subscribeOn` determines the Scheduler for subscription/upstream source at a boundary.
- `publishOn` can switch downstream processing to another Scheduler.
- Lambdas can run on threads with names different from the request thread.
- The runtime call stack is captured at error time on the currently executing thread.
- The assembly trace still points to where the code created the operator (if instrumented).

For blocking APIs, you must offload to an appropriate scheduler rather than blocking the event loop. However, a scheduler **does not fix logic bugs on its own**; it only changes where the work runs.

### 14.1. Reactor Context Differs from the Call Stack

Reactor `Context` stores metadata per subscription, not as a plain Java ThreadLocal:

~~~java
Mono<String> identity = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "unknown")));
~~~

You can provide context:

~~~java
Mono<String> withTrace =
        identity.contextWrite(ctx ->
                ctx.put("traceId", "req-123"));
~~~

Context aids correlation in reactive chains; it does not make assembly stack traces automatically complete or replace distributed tracing. For production, use official tracing frameworks and context propagation.

## 15. log(), doOnError, and checkpoint Serve Different Goals

| API | What does it observe? | Effect |
| --- | --- | --- |
| `log("stage")` | subscribe/request/onNext/onError/onComplete/cancel signals | Has logging cost per signal |
| `doOnError(error -> ...)` | Side effect when an error passes through the stage | Does not alter the signal if the callback behaves normally |
| `checkpoint("stage")` | Label of the operator chain for enhanced tracebacks | Light assembly marker |
| `checkpoint()` | Full assembly site trace | Stack snapshot for the stage |
| `Hooks.onOperatorDebug()` | Global assembly of newly created operators | Higher overhead |
| Distributed tracing | Cross-service requests, latency/spans | Does not replace source call-site tracing |
| Metrics | Counts, latency, errors, pool saturation | Does not contain full stacks |

Example:

~~~java
return fetchOrders()
        .log("orders-source")
        .flatMap(this::enrichOrder)
        .checkpoint("orders:enrich")
        .doOnError(error ->
                log.error("Orders request failed", error));
~~~

The illustrative snippet assumes methods `fetchOrders` and `enrichOrder`. Disable/reduce `log()` on flows with PII or high message volume because it can generate massive log volume. Log metadata only; do not log full payloads that may contain secrets.

`doOnError` is an observation hook. Do not use it to `subscribe()` to another stream or alter the error contract; use `onErrorMap` or `onErrorResume` if you genuinely need to transform the signal.

## 16. Runnable Java 17+ Program: Verifying Both Types of Stack Traces Yourself

The program below compares:

1. A normal pipeline: the error occurs at execution time, with no Reactor assembly traceback.
2. A pipeline with `checkpoint("label", true)`: the same error, but with an assembly traceback.
3. A pipeline created **after** `Hooks.onOperatorDebug()`: the error has a global assembly traceback.
4. `Mono.just(Integer.parseInt("bad"))`: the error occurs immediately when creating the Publisher.
5. `Mono.fromCallable(...)`: the error occurs upon subscription.

The program prints only a **stable summary** rather than printing full stack traces that depend on the Reactor/JVM version.

### 16.1. Project Structure

~~~text
reactor-assembly-trace-demo/
  pom.xml
  src/main/java/example/debug/AssemblyTraceDemo.java
~~~

Requires JDK 17+, Maven 3.6.3+, and the Spring Boot 4.1.2 BOM to manage reactor-core.

### 16.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>reactor-assembly-trace-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 16.3. AssemblyTraceDemo.java

~~~java
package example.debug;

import java.time.Duration;
import java.util.Arrays;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Hooks;
import reactor.core.publisher.Mono;

public final class AssemblyTraceDemo {

    private static Flux<Integer> build(
            String label, boolean fullCheckpoint) {

        System.out.println("assembly:" + label);

        Flux<Integer> values = Flux.just("12", "bad")
                .map(text -> {
                    System.out.println(
                            "execute:" + label + ":" + text);
                    return Integer.parseInt(text);
                });

        if (fullCheckpoint) {
            return values.checkpoint(
                    "parse-stage-" + label, true);
        }

        return values;
    }

    private static boolean hasTraceback(Throwable error) {
        return Arrays.stream(error.getSuppressed())
                .anyMatch(Exceptions::isTraceback);
    }

    private static void expectParseFailure(
            String label,
            Flux<Integer> pipeline,
            boolean expectAssemblyTrace) {

        try {
            pipeline.collectList()
                    .block(Duration.ofSeconds(3));

            throw new AssertionError(
                    "Expected NumberFormatException");
        }
        catch (NumberFormatException error) {
            boolean traced = hasTraceback(error);

            if (traced != expectAssemblyTrace) {
                throw new AssertionError(
                        "Wrong traceback flag: " + traced, error);
            }

            System.out.println(
                    "error:" + label + ":"
                    + error.getClass().getSimpleName()
                    + ":traceback=" + traced);
        }
    }

    private static void eagerVersusLazy() {
        try {
            Mono<Integer> ignored =
                    Mono.just(Integer.parseInt("bad"));

            throw new AssertionError(
                    "Expected eager parse failure");
        }
        catch (NumberFormatException error) {
            System.out.println("eager:thrown-at-assembly");
        }

        Mono<Integer> lazy =
                Mono.fromCallable(() -> Integer.parseInt("bad"));

        System.out.println("lazy:assembled");

        try {
            lazy.block(Duration.ofSeconds(3));
            throw new AssertionError(
                    "Expected deferred parse failure");
        }
        catch (NumberFormatException error) {
            System.out.println("lazy:thrown-at-subscription");
        }
    }

    public static void main(String[] args) {
        Flux<Integer> baseline = build("base", false);

        System.out.println("before-subscription");
        expectParseFailure("base", baseline, false);

        Flux<Integer> marked = build("checkpoint", true);
        expectParseFailure("checkpoint", marked, true);

        Hooks.onOperatorDebug();

        try {
            Flux<Integer> global = build("global", false);
            expectParseFailure("global", global, true);
        }
        finally {
            Hooks.resetOnOperatorDebug();
        }

        eagerVersusLazy();
    }
}
~~~

### 16.4. Run

From the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.debug.AssemblyTraceDemo
~~~

**Expected stdout (only lines printed by the program, ignoring other Maven/runtime logs):**

~~~text
assembly:base
before-subscription
execute:base:12
execute:base:bad
error:base:NumberFormatException:traceback=false
assembly:checkpoint
execute:checkpoint:12
execute:checkpoint:bad
error:checkpoint:NumberFormatException:traceback=true
assembly:global
execute:global:12
execute:global:bad
error:global:NumberFormatException:traceback=true
eager:thrown-at-assembly
lazy:assembled
lazy:thrown-at-subscription
~~~

Explanation:

- `assembly:base` appears before subscribing; no parsing has happened yet.
- `execute:base:...` only appears when collectList/block subscribes.
- Baseline is not instrumented with checkpoint or debug hook, so there is no Reactor assembly traceback.
- The pipeline with full checkpoint attaches a suppressed traceback, detected via `Exceptions.isTraceback`.
- The global hook was enabled before creating the `global` pipeline, so the new pipeline has assembly tracing.
- `Mono.just(Integer.parseInt("bad"))` evaluates its argument immediately when creating the Publisher.
- `Mono.fromCallable(...)` only parses when subscribed to.

The example uses `block(Duration)` at the boundary of a command-line program for easy observation. In a controller or service running on the Netty event loop, do not use `block()`; return a Mono/Flux for WebFlux to subscribe to.

## 17. Testing with StepVerifier Instead of Blocking in Services

If you are writing a JUnit test, you can verify errors without blocking service methods:

~~~java
@Test
void capturesAssemblyCheckpoint() {
    Flux<Integer> source = Flux.just("1", "oops")
            .map(Integer::parseInt)
            .checkpoint("parse-in-test", true);

    StepVerifier.create(source)
            .expectNext(1)
            .expectErrorSatisfies(error -> {
                assertInstanceOf(
                        NumberFormatException.class, error);

                assertTrue(Arrays.stream(error.getSuppressed())
                        .anyMatch(Exceptions::isTraceback));
            })
            .verify();
}
~~~

This snippet assumes JUnit Jupiter, reactor-test, `assertInstanceOf`, `assertTrue`, and the corresponding imports. It demonstrates verifying both the primary exception and assembly metadata. Do not assert the entire stack trace string, because file/line/operator names can change on refactoring or version upgrades.

If you need to check that the cause belongs to a service code region, set a breakpoint or combine with an assertion on the checkpoint label. Do not use stack trace text as a business contract.

### 17.1. Testing Eager vs Deferred Semantics

~~~java
AtomicInteger counter = new AtomicInteger();

Mono<Integer> lazy = Mono.fromCallable(() ->
        counter.incrementAndGet());

assertEquals(0, counter.get());

StepVerifier.create(lazy)
        .expectNext(1)
        .verifyComplete();

assertEquals(1, counter.get());
~~~

This is an illustrative test snippet requiring `reactor-test` and JUnit imports. It helps prove that a Callable is only invoked after subscription, while assembly does not increment the counter.

## 18. How to Read Reactor Errors in Production Logs

A concise workflow when encountering a log:

1. **Find the request:** request/trace ID, route, service dependency, and timestamp.
2. **Find the root Throwable:** error type, message, cause chain.
3. **Inspect runtime frames:** which user mapper/service, I/O/codec/timeout, or Reactor internals were running?
4. **Look for Suppressed / Assembly trace:** is there an `OnAssemblyException` or a light checkpoint?
5. **Check the operator assembly site:** the user-code method/line that created the operator.
6. **Read the observed path:** which operators did the error pass through?
7. **Inspect the data source:** item, condition, and redacted request context.
8. **Cross-check the subscription:** specific request, retry count, Scheduler, and cancellation.
9. **Reproduce:** write a StepVerifier/integration test for the failure case.
10. **Fix the root cause:** change the operator, fix the mapper/contract or I/O policy; do not merely add a checkpoint to mask the error.

### 18.1. Distinguishing Error Types in WebFlux

| Symptom | Common Cause | Investigation Step |
| --- | --- | --- |
| `NumberFormatException` in map | Invalid input data to parse | Check mapper, validation |
| `NullPointerException` in operator | Null from mapper or user code | Check that Reactive Streams forbids onNext(null) |
| `IndexOutOfBoundsException` at single | Source emitted more than one item | Check whether `single()` was misused |
| `WebClientResponseException` | Server returned 4xx/5xx error status | Inspect status and redacted body |
| `WebClientRequestException` | Error executing request/transport | Inspect DNS/TCP/TLS/timeout cause |
| `DecodingException` | JSON/body could not be decoded | Check Content-Type and DTO |
| `TimeoutException` | Publisher emitted no signal within deadline | Identify timeout scope |
| `IllegalStateException: block() not supported` | Called block on non-blocking event loop | Compose reactively instead of blocking |
| `ErrorCallbackNotImplemented` | Subscribed without an error consumer | Provide an error handler or let the framework subscribe |
| Composite exception + traceback | Multiple failing branches and tracing metadata | Use appropriate unwrap, filter tracebacks |

Do not infer buggy user code from an internal operator name alone. The assembly site and runtime cause need to be read together.

## 19. Common Misconceptions

| Misconception | Why It Is Wrong | Fix |
| --- | --- | --- |
| "map executes right when map() is called" | Operators usually only store the lambda | Distinguish assembly and subscription |
| "Runtime stack trace always includes the controller method that built the flow" | Threads/callbacks/boundaries may differ | Use checkpoint/assembly trace |
| "Assembly traceback is a new error" | It is usually suppressed metadata | Read the root Throwable first |
| "Enabling debug after creating a Mono still traces old assembly" | Hooks do not backfill already-assembled pipelines | Enable before assembly |
| "Enabling the global hook is safe and free" | Stack trace capture costs CPU/memory | Use light checkpoints or the agent |
| "checkpoint() and checkpoint(String) are the same" | One captures full stack, the other a light label | Choose based on need |
| "A checkpoint anywhere catches all errors" | Downstream errors do not flow upstream | Place after the region to observe |
| "checkpoint can retry errors" | It only attaches trace info | Use onError... if handling must change |
| "Keeping a static Throwable to save allocations is always good" | Suppressed tracebacks can accumulate on the same instance | Create exceptions per event when appropriate |
| "Seeing suppressed means there are multiple business errors" | Tracebacks are suppressed metadata | Filter with Exceptions.isTraceback |
| "doOnError handles the exception" | It is only a side effect | Use onErrorResume/onErrorMap |
| "Logging getMessage() alone is enough" | Loses stack, cause, suppressed | Log full Throwable and redact |
| "Reactor Context is ThreadLocal" | Context is per-subscription | Use deferContextual/contextWrite |
| "Scheduler changes the error cause" | It changes timing/thread, not logic | Inspect user mapper and data contract |
| "Two block() calls on one Mono share the same execution" | Cold publishers usually re-run | Track each subscription |
| "Multiple assembly sites mean multiple failed requests" | One error can pass through multiple operators/branches | Correlate with request trace ID |
| "Using WebFlux eliminates the need for integration tests" | Network/codec errors differ from unit errors | Test decoders, timeouts, and HTTP statuses |

### 19.1. Avoid Reusing Mutable Exceptions with Assembly Traces

Reactor can add suppressed tracebacks to a Throwable. If a static exception object is re-emitted across many requests, suppressed entries can accumulate and cause memory growth.

Instead of:

~~~java
private static final RuntimeException SHARED =
        new RuntimeException("partner failed");

Mono<String> alwaysError() {
    return Mono.error(SHARED);
}
~~~

you can create a new exception per subscription:

~~~java
Mono<String> alwaysError() {
    return Mono.error(() ->
            new RuntimeException("partner failed"));
}
~~~

`Mono.error(Supplier)` defers exception creation until subscription. If messages incorporate user data, ensure redaction and avoid exposing secrets in error logs.

## 20. Observability and Security Principles

Assembly traces aid investigation, but can reveal class/method/source paths in server logs. Do not return those traces in production HTTP responses. Do not put request bodies, bearer tokens, cookies, or personal information into checkpoint labels.

For high-traffic systems:

- Place light checkpoints at critical boundaries.
- Enable full checkpoints intentionally during incidents.
- Use tracing spans for correlation across HTTP/WebClient/DB.
- Use latency/error-rate metrics to gauge impact.
- Log full Throwables on the server while limiting sampling, cardinality, and retention per policy.
- Do not enable global debug cluster-wide without benchmarking overhead.
- Evaluate ReactorDebugAgent against runtime constraints and performance benchmarks.
- Test in environments with Schedulers, fusion, retries, and cancellation close to production.

A Reactor `onError` event is just a terminal signal within a subscription; HTTP mapping and retry policies are still decided by the application. Assembly tracing does not grant permission to log sensitive data.

## 21. Checklist When Debugging a Mono/Flux

- [ ] Identified where the Publisher is assembled.
- [ ] Identified where the Publisher is subscribed to.
- [ ] Know whether mapper/flatMap runs lazily or has eager expressions.
- [ ] Checked the primary Throwable, message, and cause chain.
- [ ] Read the suppressed assembly traceback if present.
- [ ] Know whether the checkpoint is placed before or after the failing operator.
- [ ] Used clear, non-sensitive checkpoint labels.
- [ ] Did not mistake the error observation path for separate exceptions.
- [ ] Enabled Hooks.onOperatorDebug before assembly if global debugging is needed.
- [ ] Reset the global hook after tests and did not toggle it per request.
- [ ] Evaluated the cost of global stack capture.
- [ ] Have an agent strategy if broad production debugging is needed.
- [ ] Tracked request/trace ID and subscription timing.
- [ ] Did not block the event loop to debug.
- [ ] Have tests reproducing error, empty, and cancellation cases appropriately.
- [ ] Did not log tokens/PII or return stack traces to API clients.

## 22. Self-Check Questions

**Question 1.** When is assembly time?

It is when code creates and composes Publishers/operators such as `map`, `flatMap`, `filter`, and `checkpoint` into a pipeline.

**Question 2.** When does execution time start?

When the Publisher is subscribed to; afterward the source receives demand and emits signals reactively.

**Question 3.** Does a lambda passed to map run immediately at assembly time?

Normally no. It runs when elements pass through map after subscription.

**Question 4.** Which question does a runtime stack trace answer best?

How and where the error was actually created/thrown on the running call stack.

**Question 5.** Which question does an assembly traceback answer?

At which file/method/line of code the operator was assembled and which operators the error passed through.

**Question 6.** Why must Hooks.onOperatorDebug be enabled before creating pipelines?

Because the hook captures operator construction at assembly time and cannot retroactively build stacks for already existing operators.

**Question 7.** How does checkpoint(String) differ from checkpoint()?

checkpoint(String) is a light marker that does not capture a full stack; checkpoint() captures a full assembly stack trace.

**Question 8.** When should checkpoint("label", true) be used?

When both a description and the full assembly call site are needed for a chosen location.

**Question 9.** Why might a checkpoint placed before map not mark an error thrown by map?

Because the error originates downstream and does not propagate backward through that upstream checkpoint.

**Question 10.** Where is the assembly traceback located inside a Throwable?

Usually attached as a suppressed exception and identified via `Exceptions.isTraceback`.

**Question 11.** Does a suppressed exception mean there is an additional business error?

No. Reactor tracebacks are primarily diagnostic metadata.

**Question 12.** What is the advantage of ReactorDebugAgent?

It instruments assembly sites with lower overhead than capturing full stack traces on every operator at runtime; JVM/Byte Buddy support must be verified.

**Question 13.** Why does Mono.just(Integer.parseInt("bad")) fail early?

Java evaluates the `parseInt` argument before calling Mono.just.

**Question 14.** How does Mono.fromCallable differ?

The Callable is executed upon subscription, and exceptions become error signals.

**Question 15.** Do two subscriptions to the same cold Publisher share the same execution?

Not necessarily. A cold source may run again; the assembly site may stay the same, but the subscription differs.

**Question 16.** What should be used to correlate multiple services within one request?

Distributed tracing/correlation IDs together with structured logs; assembly tracebacks are only a supplementary tool to pinpoint operator call sites.

## 23. Official References

- [Project Reactor — Debugging Reactor](https://projectreactor.io/docs/core/release/reference/debugging.html): assembly vs execution, global hooks, tracebacks, checkpoint, debug agent, and log().
- [Project Reactor — Mono JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): checkpoint(), checkpoint(String), checkpoint(String, boolean), defer, fromCallable, error supplier.
- [Project Reactor — Flux JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): assembly markers, pipeline operators, and error propagation.
- [Project Reactor — Hooks JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Hooks.html): onOperatorDebug, resetOnOperatorDebug, and assembly hooks.
- [Project Reactor — Exceptions JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/Exceptions.html): isTraceback, unwrapMultipleExcludingTracebacks, and exception utilities.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier and error assertions.
- [Project Reactor — Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): Reactor Context and tracing.
- [Spring Framework — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html): controller errors and HTTP exception handling.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client and error propagation.
- [Spring Blog — Flight of the Flux: Assembly vs Subscription](https://spring.io/blog/2019/03/06/flight-of-the-flux-1-assembly-vs-subscription): how to understand both phases.
- [Spring Blog — Reactor Debugging Experience](https://spring.io/blog/2019/03/28/reactor-debugging-experience/): assembly backtracing experience.

**Key Takeaway:** In WebFlux, assembly is when code builds a `Mono`/`Flux` chain; execution is when it is subscribed to and processes signals. A runtime stack trace shows where the exception was thrown during execution; an assembly traceback helps trace back where the operator was declared. Use `checkpoint("label")` to mark boundaries with low overhead, `checkpoint()` or `checkpoint("label", true)` when a full stack is needed, `Hooks.onOperatorDebug()` for controlled global debugging, and `ReactorDebugAgent` when production-appropriate instrumentation is required. Always read the primary Throwable, cause, suppressed traceback, and request trace ID together; never mistake an assembly trace for a separate error.