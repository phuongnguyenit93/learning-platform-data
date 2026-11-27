# How Reactor Context Differs from ThreadLocal Across Thread Switches

In a Spring WebFlux application, a request can pass through many Reactor operators and be processed across multiple different threads. When you need to preserve information such as a correlation ID, tenant identifier, or tracing data, storing it in ThreadLocal can break because ThreadLocal binds data to a specific thread. Reactor Context is designed for the reactive model: data is bound to the subscription and can be read along the processing chain even when operators switch to another scheduler.

This difference is especially important when integrating Spring Cloud CircuitBreaker with Reactor. A WebClient call, execution through ReactiveCircuitBreaker, and a fallback may run at different times or on different threads. If code relies on ThreadLocal to read request metadata, the information may no longer be present where it is needed. Reactor Context provides a way to pass metadata along the reactive stream without depending on the executing thread.

## 1. ThreadLocal stores data per thread

ThreadLocal is a Java mechanism that gives each thread its own separate value associated with the same ThreadLocal variable. Two threads accessing the same variable see two independent values. This mechanism is commonly used in synchronous applications to hold information tied to processing on a single thread, such as the current user or logging data.

Example:

~~~java
public final class RequestContextHolder {

    private static final ThreadLocal<String> CORRELATION_ID =
            new ThreadLocal<>();

    private RequestContextHolder() {
    }

    public static void setCorrelationId(String id) {
        CORRELATION_ID.set(id);
    }

    public static String getCorrelationId() {
        return CORRELATION_ID.get();
    }

    public static void clear() {
        CORRELATION_ID.remove();
    }
}
~~~

In a synchronous processing model, a request is usually handled from start to finish on the same thread. Code can set the correlation ID at the start of the request, read it in deeper layers, and clear it when the request finishes.

However, ThreadLocal does not automatically propagate values from one thread to another. In systems using thread pools, threads are reused across many different tasks. If code fails to clear the value at the right time, stale leftover data can be mistakenly read by a later task.

## 2. Why is ThreadLocal unsuitable as the primary context source in Reactor?

Reactor does not guarantee that a processing chain always runs on one thread. Operators such as publishOn and subscribeOn can change the executing scheduler. A request may start on a WebFlux worker thread, switch to another scheduler to do work, and then continue on yet another thread when signals arrive.

Example:

~~~java
Mono<String> pipeline = Mono.just("work")
    .publishOn(Schedulers.boundedElastic())
    .map(ignored -> "correlationId="
            + RequestContextHolder.getCorrelationId());
~~~

If ThreadLocal was set on the initial thread before subscription, the map operator after publishOn may run on a thread from boundedElastic. That thread does not necessarily hold the initial thread's ThreadLocal value. The result can be null or a different leftover value on a reused thread.

Two common operators play different roles:

- **publishOn** switches downstream signal processing after the operator's position to the specified scheduler.
- **subscribeOn** affects the scheduler used to perform the upstream subscription process.

Both can change the executing thread. Therefore, never assume a reactive request stays on its initial thread or that ThreadLocal automatically follows the request.

## 3. Reactor Context is bound to the subscription

Reactor Context is an immutable key-value structure bound to the subscriber and propagated through the reactive chain. It is designed to hold metadata needed during publisher execution, such as:

- Correlation ID or trace ID.
- Tenant identifier used to select data scope.
- Normalized authorization metadata, if the pipeline needs it.
- Metadata for logging, tracing, or business policies.

Context is not bound to a thread. When Reactor switches execution to another scheduler, Context travels with the subscription so operators can still access it.

You can visualize it as:

~~~mermaid
flowchart TD
    A[Subscriber creates subscription] --> B[Reactor Context travels with subscription]
    B --> C[Publisher and upstream operators]
    C --> D[publishOn switches scheduler]
    D --> E[Operator runs on another thread]
    E --> F[Reads the same metadata from Reactor Context]
~~~

This differs from ThreadLocal: ThreadLocal is looked up from the current thread, whereas Reactor Context is accessed from the reactive chain's subscriber context.

Context is immutable. When adding or modifying a value, Reactor creates a new Context for the corresponding upstream segment. As a result, many concurrent requests can carry their own Context without overwriting each other's data.

## 4. Putting data into Context with contextWrite

You can add a value to Context using contextWrite:

~~~java
Mono<String> pipeline = Mono.deferContextual(context ->
        Mono.just(context.get("correlationId")))
    .contextWrite(context ->
        context.put("correlationId", "req-2026-001"));
~~~

In this example:

1. contextWrite adds correlationId to the subscription's Context.
2. deferContextual reads the value from Context when the publisher is subscribed to.
3. The Mono emits the string req-2026-001.

You can use Context.of when you want to construct a Context from scratch:

~~~java
Mono<String> pipeline = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("correlationId", "unknown")))
    .contextWrite(Context.of("correlationId", "req-2026-001"));
~~~

Commonly used APIs:

| API | Purpose |
|---|---|
| contextWrite(context -> context.put(key, value)) | Adds or replaces a value in Context for upstream |
| Context.of(key, value) | Creates a Context with one or more key-value pairs |
| deferContextual(contextView -> ...) | Reads Context at subscription time |
| contextView.get(key) | Reads value by key; throws an error if the key does not exist |
| contextView.getOrDefault(key, defaultValue) | Reads value or returns default |
| contextView.hasKey(key) | Checks whether a key exists |

Use clear key names and avoid collisions across components. In large applications, define constants or namespaced keys so one library does not overwrite another component's metadata.

## 5. Context propagation direction and contextWrite placement

A frequent point of confusion is that Context propagates from the subscriber upstream, in the opposite direction of data emission. The contextWrite operator modifies the Context seen by operators located upstream of it.

Example:

~~~java
Mono<String> pipeline =
        Mono.deferContextual(context ->
                Mono.just("trace=" + context.get("traceId")))
            .map(value -> value + ", processed")
            .contextWrite(context -> context.put("traceId", "trace-001"));
~~~

contextWrite appears lower in the declaration chain, yet the Context is provided to operators above it when subscription occurs. Therefore, deferContextual can read traceId.

If contextWrite is placed on a branch outside the same subscription, other branches will not automatically receive that value. When composing multiple publishers, understand subscription boundaries and contextWrite placement.

Example with two branches:

~~~java
Mono<String> source = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("tenantId", "public")));

Mono<String> result = source
        .flatMap(value -> source.map(other -> value + ":" + other))
        .contextWrite(context -> context.put("tenantId", "tenant-a"));
~~~

Publishers composed within the same subscription chain can see the corresponding Context. However, if you create an independent subscription with subscribe() or launch a task outside the chain, Context is not automatically shared with that task. Prefer composing publishers rather than creating new manual subscriptions.

## 6. Context persists across scheduler switches

The following example demonstrates reading the same correlation ID before and after publishOn:

~~~java
Mono<String> pipeline = Mono.deferContextual(context -> {
        String beforeSwitch = context.get("correlationId");

        return Mono.just(beforeSwitch)
                .publishOn(Schedulers.boundedElastic())
                .map(value -> {
                    String afterSwitch = context.get("correlationId");
                    return value + " -> " + afterSwitch;
                });
    })
    .contextWrite(context ->
            context.put("correlationId", "req-42"));
~~~

The purpose of this example is to show that Context is bound to the subscription, independent of threads. Even though map executes on a different scheduler, it can still read metadata from the subscriber's Context.

In production code, if you need to read Context at multiple points, use deferContextual wherever access is needed. Do not read Context while assembling a publisher and store the value in a global or shared variable across requests.

## 7. Applying Reactor Context to reactive Circuit Breaker calls

In Spring Cloud CircuitBreaker, ReactiveCircuitBreaker protects Mono or Flux publishers. Metadata such as a correlation ID can be written into Context before the publisher is subscribed to. As the call flows through WebClient, Circuit Breaker, and fallback, reactive operators in the same chain can read that metadata.

Example:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

public class PartnerClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker circuitBreaker;

    public PartnerClient(
            WebClient webClient,
            ReactiveCircuitBreaker circuitBreaker) {
        this.webClient = webClient;
        this.circuitBreaker = circuitBreaker;
    }

    public Mono<PartnerResponse> findPartner(String partnerId) {
        Mono<PartnerResponse> remoteCall = webClient.get()
                .uri("/partners/{id}", partnerId)
                .retrieve()
                .bodyToMono(PartnerResponse.class);

        return circuitBreaker.run(
                remoteCall,
                error -> Mono.deferContextual(context -> {
                    String correlationId =
                            context.getOrDefault("correlationId", "unknown");

                    logFallback(correlationId, error);
                    return Mono.just(PartnerResponse.unavailable(partnerId));
                })
        );
    }

    private void logFallback(String correlationId, Throwable error) {
        // Log with correlation ID and fallback cause.
    }
}
~~~

The calling layer can attach Context:

~~~java
return partnerClient.findPartner(partnerId)
        .contextWrite(context ->
                context.put("correlationId", correlationId));
~~~

In this design, the fallback uses deferContextual to read the correlation ID at subscription time. Do not call context.get while constructing the publisher because no subscriber context exists to read at that moment.

Whether Context is preserved across fallbacks should be verified via integration tests with your application's versions of Spring Cloud CircuitBreaker, Resilience4j, and Reactor. When the fallback is composed within the same reactive chain, Reactor Context is the right mechanism for passing metadata. If an adapter or custom code creates an independent subscription, Context may no longer be in the same scope.

## 8. ThreadLocal, MDC, and logging

Many logging libraries use MDC (Mapped Diagnostic Context) to attach correlation IDs to logs. Traditional MDC relies on ThreadLocal. Therefore, if a reactive application switches schedulers, MDC may not hold the expected value on the current thread.

This can be addressed in several ways:

- Use Micrometer Context Propagation to register how ThreadLocal values are read, written, and cleared, then connect them to Reactor Context as supported by your library version.
- Use Micrometer Tracing or Spring Boot's tracing integration to manage trace context across supported components.
- Log from reactive operators using metadata read directly from Reactor Context, if MDC is not required.
- If bridging to MDC is needed, ensure values are restored and cleared promptly so thread pools do not retain data from previous requests.

Reactor and the Micrometer ecosystem provide context propagation mechanisms to connect Context with ThreadLocal-based imperative libraries. However, automatic propagation capabilities depend on the Reactor version, Micrometer Context Propagation, and how the application enables the corresponding mode. Do not assume ThreadLocal is synchronized automatically simply because the application uses Reactor.

One approach is registering a ThreadLocalAccessor for MDC or a specific ThreadLocal in ContextRegistry, then using the capture/restore mechanism appropriate for the version. With certain Reactor configurations, automatic context propagation can be enabled via the corresponding hook. Check the documentation for your actual dependencies and avoid enabling multiple overlapping bridge mechanisms.

## 9. contextCapture and automatic context propagation

Micrometer Context Propagation provides tools to capture values from registered ThreadLocal-style contexts and transfer them into the appropriate context mechanism. In a Reactor environment, integration APIs can support capturing at subscription time and restoring ThreadLocals when callbacks execute.

Distinguish two concepts:

- **Context capture** reads values from registered ThreadLocals at a point in time and writes them into Reactor Context. This is useful when starting a reactive chain from imperative code that already holds ThreadLocals.
- **Automatic context propagation** lets Reactor automatically restore registered ThreadLocals within the execution scope of supported callbacks. This mechanism requires compatible versions and explicit configuration.

Not every ThreadLocal is captured automatically. Only registered accessors supported by the propagation mechanism can be read/written according to the corresponding rules. Capturing also does not mean the entire thread state is copied.

In a Spring Boot application, check the Reactor and Micrometer Context Propagation versions provided by your project's dependency management. Review the configuration guide for that exact version before enabling hooks or using contextCapture. If compatibility with imperative libraries is unnecessary, prefer using Reactor Context directly to minimize reliance on thread state.

## 10. What not to store in Reactor Context

Reactor Context is suited for metadata accessed along a processing chain, not for storing all application data.

Store small, immutable values such as correlation IDs, trace metadata, or tenant identifiers. Avoid storing:

- Large request bodies or long-lived data objects.
- Buffers, streams, or resources that require closing.
- Mutable objects modified concurrently by multiple publisher branches.
- Secrets, access tokens, or credentials unless strictly necessary.
- Data intended to be sent over the network without dedicated encryption and access control.

Context is an immutable structure, but objects stored inside it are not automatically immutable. If you put a mutable object into Context and multiple branches mutate it, race conditions can still occur. Store immutable values or small metadata items.

Context also does not automatically travel to another service over HTTP. If you need to send a correlation ID to a dependency, attach it to a header using a WebClient filter or use appropriate tracing instrumentation. Reactor Context only manages data within the current reactive pipeline.

## 11. Common mistakes during thread switches

- **Reading ThreadLocal after publishOn and expecting the old value**: the callback may run on a different thread; use Reactor Context or a configured bridge.
- **Reading Context at assembly time instead of subscription time**: use deferContextual to access Context at execution time.
- **Placing contextWrite in the wrong spot**: Context flows upstream; verify which operators lie within that scope.
- **Calling subscribe() inside a service**: an independent subscription can detach from the original request's Context.
- **Sharing mutable objects in Context**: an immutable Context does not make objects inside it immutable.
- **Using MDC without propagation**: logs on other threads may miss the correlation ID or read a stale value.
- **Forgetting to clear ThreadLocal when bridging manually**: reused pool threads can leak data across requests.
- **Assuming Context crosses HTTP automatically**: use a WebClient filter or tracing to propagate metadata across service boundaries.
- **Failing to test the fallback**: the fallback is another branch of the pipeline; verify it reads the expected metadata in the version you run.

## 12. Adoption workflow in a Spring Cloud CircuitBreaker service

When a reactive service needs to preserve request metadata across a dependency call and fallback, follow this sequence:

1. Identify the metadata to propagate, such as correlation ID or tenant ID.
2. Define consistent keys and store only small, immutable values in Reactor Context.
3. Inject metadata into the pipeline with contextWrite at the entry layer of processing.
4. Use deferContextual in operators that need to read metadata, including inside fallbacks.
5. Compose WebClient and ReactiveCircuitBreaker in the same reactive chain; avoid manual subscribe or detached tasks.
6. If MDC or imperative libraries are required, configure Micrometer Context Propagation with proper accessors and verify version compatibility.
7. If metadata must cross HTTP, configure a WebClient filter or tracing instrumentation to place metadata into headers.
8. Test across publishOn, subscribeOn, fallback branches, and concurrent requests to confirm Context is neither lost nor mixed up.

Reactor Context binds metadata to the subscription, making it fit the reactive model and remain accessible when execution switches schedulers. ThreadLocal binds data to a thread, so it is only safe when processing stays on that thread or uses an explicit propagation mechanism. When combining Spring Cloud CircuitBreaker with WebFlux, use Reactor Context for pipeline metadata, design fallbacks to read Context at the right time, and bridge to ThreadLocal only when integrating imperative libraries.
