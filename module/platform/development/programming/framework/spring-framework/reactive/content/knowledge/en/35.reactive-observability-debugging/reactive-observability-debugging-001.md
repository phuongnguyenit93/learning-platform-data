# Tracking Signal Chains with log and doOn Operators in Reactor

## 1. Why Track Reactive Signals?

A Reactor chain does not run like sequential code at the moment its methods are called. When writing:

~~~java
Mono<Product> product = repository.findById(id)
        .map(this::toResponse)
        .doOnNext(response -> log.info("mapped {}", response));
~~~

we are **assembling a pipeline**. The data source usually starts executing only when there is a subscription and appropriate demand. In a WebFlux request, the framework is what subscribes to the Publisher returned by the controller.

When debugging, you need to be able to answer:

- Has the pipeline been subscribed to yet?
- How many elements has the Subscriber requested?
- Did the source emit onNext?
- Where were elements filtered or discarded?
- Did the pipeline complete normally or emit an error?
- Did the consumer cancel the subscription before the source completed?
- Where in the chain is the doOn callback located, and is it observing the value before or after transformation?

Reactor provides two main groups of tools:

1. **log():** records the Reactive Streams signals passing through the operator's position.
2. **doOn... operators:** invoke a callback when a specific signal or event occurs, without intentionally transforming the element.

These tools help observe the pipeline. They do not replace map, flatMap, onErrorResume, retry, or business logic.

## 2. Understanding Subscription Lifecycle and Signals

Reactive Streams has four main signals from Publisher to Subscriber:

- **onSubscribe(Subscription):** the Publisher provides a Subscription so the Subscriber can control demand and cancellation.
- **onNext(value):** the Publisher emits an element.
- **onError(error):** the Publisher terminates with an error.
- **onComplete():** the Publisher terminates successfully.

The Subscriber also calls two control methods back to the Publisher:

- **request(n):** requests at most the next n elements.
- **cancel():** cancels the subscription, asking the Publisher to stop emitting data.

Simple model:

~~~text
Subscriber                         Publisher
    |                                  |
    |<------ onSubscribe(subscription)-|
    |                                  |
    |---------- request(2) ------------>|
    |                                  |
    |<------------- onNext(A) ----------|
    |<------------- onNext(B) ----------|
    |                                  |
    |---------- request(1) ------------>|
    |<------------- onNext(C) ----------|
    |<------------- onComplete() -------|
~~~

If the subscriber cancels before the source finishes:

~~~text
Subscriber                         Publisher
    |                                  |
    |<------ onSubscribe(subscription)-|
    |---------- request(1) ------------>|
    |<------------- onNext(A) ----------|
    |---------- cancel() -------------->|
    |                                  |
    |         No more new onNext       |
~~~

request(n) is the backpressure mechanism. It describes demand, not the number of elements guaranteed to have been processed. The source may emit fewer than the demand, terminate early, or error. Some operators also adjust/prefetch upstream demand, so the value observed by doOnRequest depends on where the operator is placed.

cancel() is neither onComplete() nor onError(). Therefore, logging only doOnComplete or doOnError will miss cases where the client closes the connection or downstream proactively stops the stream.

### 2.1. Mono and Flux Have Different Terminal Signals

- **Mono<T>** emits at most one onNext(T), then onComplete(), or emits an empty onComplete(), or onError().
- **Flux<T>** emits 0 to many onNext signals, then onComplete() or onError().
- **Mono.empty()** completes successfully without emitting a value.
- **Mono.error(error)** terminates with an error without emitting a value.

This point is especially important with Mono.doOnSuccess: the callback is invoked both when the Mono has a value and when the Mono completes empty. In the empty case, the value passed to the callback is null. doOnNext only runs when there is an element.

## 3. Pipeline Assembly Differs from Pipeline Execution

~~~java
Flux<Integer> numbers = Flux.defer(() -> {
    log.info("source factory invoked");
    return Flux.range(1, 3);
}).doOnSubscribe(subscription ->
        log.info("subscribed"));
~~~

When the line declaring numbers runs, the pipeline is created, but Flux.defer has not called the supplier yet. When there is a subscriber:

1. defer creates the source for that subscription.
2. doOnSubscribe observes the subscription.
3. The Subscriber requests demand.
4. The source emits elements and the terminal signal.

If a cold publisher is subscribed to twice, the source may run twice and the callbacks also run twice. Therefore, duplicate logs do not necessarily mean a single request was processed twice; the application may have created two subscriptions.

In WebFlux, a controller should return a Mono/Flux so the framework manages the subscription:

~~~java
@GetMapping("/products")
Flux<Product> products() {
    return service.findAll();
}
~~~

Do not manually call subscribe() in a controller just to "make it run". A detached subscription prevents the framework from owning the full lifecycle, cancellation, and errors of that work.

## 4. Lookup Table of doOn Operators

| Operator | When does the callback run? | Used to observe |
| --- | --- | --- |
| doFirst | Before upstream is subscribed to | Subscription starting point |
| doOnSubscribe | When receiving Subscription | A new subscription |
| doOnRequest | When receiving request(n) | Demand/backpressure |
| doOnNext | When there is an onNext element | Value at the operator's position |
| doOnEach | When there is onNext, onError, or onComplete | Subscriber signal in Signal form |
| doOnError | When the source terminates with an error | Exception and error cause |
| Flux.doOnComplete | When Flux completes successfully | Flux completion |
| Mono.doOnSuccess | When Mono completes successfully, with or without a value | Value or null if empty |
| doOnCancel | When downstream calls cancel | Subscription cancellation |
| doOnTerminate | On completion or error, before the terminal signal is forwarded | Success/error termination |
| doAfterTerminate | After onComplete/onError has been forwarded | Work after the terminal signal |
| doFinally | After complete, error, or cancel | Any kind of termination |
| doOnDiscard | When a discard-supporting operator drops upstream elements | Cleanup of discarded resources |

The doOn... callbacks are designed for side effects. They do not transform elements passing through the pipeline. If you need to modify data, use map, flatMap, filter, or the corresponding operator.

### 4.1. doOnSubscribe and doFirst

~~~java
Flux<Integer> pipeline = Flux.range(1, 2)
        .doFirst(() -> log.info("doFirst"))
        .doOnSubscribe(subscription ->
                log.info("doOnSubscribe"));
~~~

doFirst runs before upstream is subscribed to. doOnSubscribe runs when the Subscription is passed to the subscriber at the operator's position.

If multiple doFirst calls are chained consecutively, the callback order can be the reverse of the declaration order because subscription propagates backward from downstream to upstream. Do not rely on the log order of consecutive doFirst calls as a business mechanism.

### 4.2. doOnRequest

~~~java
Flux<Integer> pipeline = Flux.range(1, 10)
        .doOnRequest(n ->
                log.info("upstream demand={}", n));
~~~

doOnRequest is useful for checking whether a consumer requests unbounded demand, or how many elements an operator is prefetching.

For example, a test that proactively requests elements step by step:

~~~java
StepVerifier.create(pipeline, 0)
        .thenRequest(2)
        .expectNext(1, 2)
        .thenCancel()
        .verify();
~~~

With a simple pipeline without demand-adjusting operators, the callback can observe request(2). When adding publishOn, flatMap, buffer, or prefetching operators, upstream demand may be larger than the direct request from the subscriber.

Do not sum request values to infer the number of processed business records. Use doOnNext or a metric at an appropriate position to measure actual elements.

### 4.3. doOnNext

~~~java
Flux<Integer> pipeline = Flux.range(1, 3)
        .doOnNext(value ->
                log.info("received value={}", value));
~~~

The callback runs when an element is emitted past the doOnNext position. It does not run for Mono.empty() or Flux.empty().

Placing the callback before or after filter will observe a different set of elements:

~~~java
Flux.range(1, 5)
        .doOnNext(value -> log.info("source={}", value))
        .filter(value -> value % 2 == 0)
        .doOnNext(value -> log.info("accepted={}", value))
        .map(value -> value * 10)
        .doOnNext(value -> log.info("mapped={}", value));
~~~

Observed values:

- source: 1, 2, 3, 4, 5.
- accepted: 2, 4.
- mapped: 20, 40.

This is a very effective technique to locate which operator dropped or altered data in which stage.

### 4.4. doOnEach

doOnEach receives Signal<T>. You can distinguish:

- signal.isOnNext() and get signal.get().
- signal.isOnError() and get signal.getThrowable().
- signal.isOnComplete() to recognize completion.

Example:

~~~java
Flux.range(1, 2)
        .doOnEach(signal -> {
            if (signal.isOnNext()) {
                log.info("next={}", signal.get());
            } else if (signal.isOnError()) {
                log.warn("error", signal.getThrowable());
            } else if (signal.isOnComplete()) {
                log.info("complete");
            }
        });
~~~

doOnEach is useful when you need a centralized callback for the three Subscriber signal types. It does not replace doOnRequest or doOnCancel, because request and cancel are Subscription control operations, not onNext/onError/onComplete.

If you only need to log a value, doOnNext is more concise. If you need context or need to distinguish complete/error within a single callback, doOnEach is more suitable.

### 4.5. doOnError Does Not Recover from Errors

~~~java
Mono<Product> product = repository.findById(id)
        .doOnError(error ->
                log.warn("find product failed", error));
~~~

doOnError observes the error, but the error still continues propagating downstream. If you want to replace the error with a fallback, use a recovery operator:

~~~java
Mono<Product> product = repository.findById(id)
        .doOnError(error ->
                log.warn("find product failed", error))
        .onErrorResume(error ->
                cache.findById(id));
~~~

Do not place recovery logic inside a logger. Keep observation and control-flow modification separate so they are easy to test.

### 4.6. Mono.doOnSuccess and Null Values

~~~java
Mono.<String>empty()
        .doOnSuccess(value ->
                log.info("success value={}", value));
~~~

The callback still runs even though there is no onNext; value is null. That differs from doOnNext, which is not called in this case.

If you need to distinguish empty from a value, you can check for null inside doOnSuccess, or use switchIfEmpty to handle empty as a separate branch.

### 4.7. doOnComplete, doOnTerminate, and doAfterTerminate

- Flux.doOnComplete only observes successful completion of a Flux.
- doOnTerminate observes complete or error, not cancel.
- doAfterTerminate runs after complete/error has been forwarded downstream; it also does not run on cancel.
- With Mono, onNext is the final element before complete; doOnSuccess is usually more expressive if you need the success value.

Do not use these operators to guarantee cleanup when the consumer cancels the stream. Use doFinally or doOnCancel depending on the purpose.

### 4.8. doOnCancel and doFinally

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(200))
        .doOnCancel(() ->
                log.info("downstream cancelled"))
        .doFinally(signalType ->
                log.info("terminated by {}", signalType));
~~~

doOnCancel runs when the subscription is cancelled. doFinally receives a SignalType and runs after the pipeline terminates due to:

- ON_COMPLETE
- ON_ERROR
- CANCEL

Because doFinally runs after the terminal signal has been forwarded downstream, the callback may execute after assertions or the subscriber's completion-handling code. It is suitable for stopping timers, recording metrics, or lightweight cleanup.

If multiple doFinally calls are chained consecutively, the callbacks may run in the reverse order of declaration. Do not rely on that order to coordinate critical resources; use usingWhen, doFinally at a clear lifecycle boundary, or an appropriate resource management abstraction.

### 4.9. doOnDiscard

Some operators may drop elements that were already prefetched or buffered when downstream filters/cancels/errors. doOnDiscard lets you register cleanup for element types whose upstream operators support discard:

~~~java
Flux<DataBuffer> buffers = source
        .filter(this::isUseful)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

This is an illustrative example for DataBuffer, which has contract-based ownership. doOnDiscard only takes effect with operators that support discard and must be placed at the right position in the chain. The cleanup callback must be idempotent and safe for any instance of that type.

Do not add doOnDiscard arbitrarily for every object. For DataBuffer/pooled resources, follow the ownership and retain/release guidelines of the API in use.

## 5. log(): Viewing Signals at a Position in the Pipeline

### 5.1. Basic Usage

~~~java
Flux<Integer> result = Flux.range(1, 3)
        .log("example.reactor.source")
        .map(value -> value * 10);
~~~

log() records the Reactive Streams signals passing through that operator, typically including subscription, request, onNext, onComplete, onError, and cancel. It is useful when you need an overall view instead of writing multiple callbacks yourself.

Reactor uses Loggers to integrate with popular logging frameworks via SLF4J, such as Logback or Log4j. If no compatible logging backend is present, the fallback mechanism may write to the console. Production applications should configure a logging backend that does not block the event loop.

### 5.2. Log Position Determines Which Values Are Observed

~~~java
Flux.range(1, 3)
        .log("before-map")
        .map(value -> value * 10)
        .log("after-map");
~~~

The log before map sees 1, 2, 3; the log after map sees 10, 20, 30. The log operator observes signals at its position in the chain, so you can place multiple short log categories at key boundaries.

Similarly with filter:

~~~java
Flux.range(1, 5)
        .log("before-filter")
        .filter(value -> value % 2 == 0)
        .log("after-filter");
~~~

before-filter sees all five values. after-filter only sees 2 and 4.

### 5.3. Choosing Category and Log Level

You can use a dedicated category to enable/disable it in application.yml or Logback configuration:

~~~java
Flux.range(1, 3)
        .log("app.reactor.catalog", Level.DEBUG);
~~~

Configuration example:

~~~yaml
logging:
  level:
    root: INFO
    app.reactor.catalog: DEBUG
~~~

If detailed logging is enabled on every production pipeline, log volume can grow sharply. Only enable it on the component or request under investigation, then turn it off when finished.

### 5.4. How Do log() and doOn... Differ?

| Tool | Strengths | Limitations |
| --- | --- | --- |
| log() | Observes multiple signals and request/cancel at one position | Logs can be verbose, hard to customize business fields |
| doOnNext | Logs a specific value | Does not see error/cancel without adding other operators |
| doOnEach | Receives Signal and can read Reactor Context | Requires branching on signal type |
| doOnError | Logs exceptions intentionally | Does not recover from errors |
| doFinally | Observes complete/error/cancel | Does not directly provide the last element or exception |
| doOnRequest | Observes demand | Demand is not synonymous with the number of processed records |

In practice, they are often combined: temporary log() to see all signals, then keeping a few operationally meaningful doOn... hooks such as error, duration, cancellation, and trace ID.

## 6. Example Illustrating Operator Placement

Consider the pipeline:

~~~java
Flux<Integer> result = Flux.range(1, 5)
        .doOnSubscribe(s -> log.info("subscribed"))
        .doOnRequest(n -> log.info("requested={}", n))
        .doOnNext(v -> log.info("raw={}", v))
        .filter(v -> v % 2 == 0)
        .doOnNext(v -> log.info("filtered={}", v))
        .map(v -> v * 10)
        .doOnNext(v -> log.info("mapped={}", v))
        .doOnComplete(() -> log.info("completed"))
        .doFinally(type -> log.info("finally={}", type));
~~~

When the subscriber requests enough data, the values pass through the observation points as follows:

| Observation Point | Value |
| --- | --- |
| raw | 1, 2, 3, 4, 5 |
| filtered | 2, 4 |
| mapped | 20, 40 |
| doOnComplete | Once when the Flux completes |
| doFinally | Once with ON_COMPLETE |

If downstream cancels after receiving 20, doOnComplete does not run; doFinally receives CANCEL. This is a classic example of why terminal signal logging must distinguish complete from cancel.

## 7. Reactor Context, Trace ID, and MDC

### 7.1. Why Is ThreadLocal Error-Prone?

A reactive pipeline can switch across multiple threads when using publishOn, subscribeOn, schedulers, or connectors. Traditional ThreadLocal/MDC attaches data to the current thread, not automatically to the subscriber.

You should not assume:

~~~java
MDC.put("traceId", traceId);
return service.call();
~~~

that all subsequent callbacks will see that MDC. When the pipeline switches threads, MDC can be lost or carry another request's value if not managed properly.

### 7.2. Using Reactor Context

Reactor Context is data attached to the subscriber, suitable for carrying a correlation ID through the pipeline:

~~~java
Flux<String> pipeline = Flux.just("A", "B")
        .doOnEach(signal -> {
            if (signal.isOnNext()) {
                String traceId = signal.getContextView()
                        .getOrDefault("traceId", "unknown");

                log.info("trace={} value={}",
                        traceId, signal.get());
            }
        })
        .contextWrite(context ->
                context.put("traceId", "req-42"));
~~~

contextWrite provides context along the subscription direction from downstream to upstream. Therefore its position matters; placing context on an unrelated branch can prevent the operator from reading the desired key.

Context is immutable in its API usage; contextWrite creates a new context for the subscription rather than mutating a shared global map.

### 7.3. Integrating MDC

If the log format requires MDC, use a context propagation mechanism compatible with your Reactor/Spring version and logging backend, such as Micrometer Context Propagation when the application has integrated it. Automatic context propagation configuration or global hooks must be well understood and tested; do not add a global hook arbitrarily just so one log line has a trace ID.

A simple and safe approach is to read the trace ID from Signal.getContextView() in the callback that needs to log, then pass it as a structured logging field. If using MDC manually, you must restore/clear the value in every branch to avoid context leakage between requests.

## 8. Debugging Assembly Errors and Operator Chains

### 8.1. checkpoint()

When an error occurs deep inside a pipeline, the stack trace may show where the error was emitted, but not fully show where the chain was assembled.

Add a named checkpoint:

~~~java
Mono<Product> product = repository.findById(id)
        .map(this::toResponse)
        .checkpoint("CatalogService.findProduct");
~~~

A checkpoint adds a marker to the assembly traceback. You can use a full stack trace:

~~~java
.checkpoint("CatalogService.findProduct", true)
~~~

Full stack capture has higher cost. Only enable it when needed for diagnosis.

### 8.2. Hooks.onOperatorDebug()

~~~java
Hooks.onOperatorDebug();
~~~

This hook enables broader assembly tracing for operators created after the hook is activated. It is useful in development environments, but has overhead; do not enable it unconditionally on high-traffic production systems.

If you need a more efficient debugging agent, Reactor provides ReactorDebugAgent via the reactor-tools dependency in compatible versions. Read the guide for the exact version and initialize the agent before pipelines are created.

### 8.3. Distinguishing Original Errors from Callback Errors

doOnError should only log. If a doOn callback throws an exception itself, the callback can alter the pipeline result or cause an operator error. Therefore:

- Loggers must be safe and fast.
- Do not parse/serialize large payloads inside log callbacks.
- Do not call blocking APIs or databases from callbacks.
- Do not let formatters or redaction code throw exceptions themselves.
- If you need to transform an error, use onErrorMap; if you need a fallback, use onErrorResume.

## 9. Logging in WebFlux: Operational Rules

### 9.1. Do Not Block the Event Loop

Heavy synchronous logging, slow file/network writes, or formatting large objects can slow down the event loop. Use an appropriate backend and appender; avoid logging entire large bodies in callbacks.

### 9.2. Do Not Log Sensitive Data

Do not log:

- Authorization headers, access tokens, refresh tokens.
- Session IDs, cookies, CSRF tokens.
- Passwords, API keys, private keys.
- Personal data or payloads containing payment information.
- Full request/response bodies without redaction.

Log useful metadata instead: trace ID, route, method, status, duration, upstream name, item count, and normalized error codes.

### 9.3. Do Not Turn Logs into Metrics

Logging every element of a very large Flux can produce millions of lines. To measure throughput, error rate, or latency, use Micrometer metrics/observation or appropriate tracing. Detailed logs help investigate a single request; metrics help observe system-wide trends.

### 9.4. Do Not Trigger Business Side Effects in doOn

Example to avoid:

~~~java
orders.doOnNext(order -> paymentService.charge(order));
~~~

doOnNext is not the right place to perform an asynchronous reactive task without composing its result. If charge returns a Mono, use flatMap:

~~~java
orders.flatMap(paymentService::charge);
~~~

Use doOn to observe; use transformation/composition operators to drive business logic.

## 10. Runnable Project: Java 17+, Spring Boot 3.5, and Reactor

This example creates a WebFlux application with the following endpoints:

- GET /debug/numbers: emits four transformed numbers, logging subscription/request/value/complete.
- GET /debug/failure: emits two values then terminates with an error to observe doOnError.
- GET /debug/events: streams events over time; when the client disconnects, doOnCancel and doFinally record the cancellation.
- GET /debug/context: demonstrates a trace ID flowing through Reactor Context.

Tests use StepVerifier to verify values, errors, signal order, context, and cancellation without depending on network timing.

### 10.1. Project Structure

~~~text
reactor-signal-tracing/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/tracing/
    │   │   ├── SignalTraceApplication.java
    │   │   ├── SignalTraceService.java
    │   │   └── SignalTraceController.java
    │   └── resources/application.yml
    └── test/java/example/tracing/
        └── SignalTraceServiceTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>reactor-signal-tracing</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
~~~

Spring Boot manages compatible Reactor versions through dependency management; there is no need to manually override reactor-core without a clear reason.

### 10.3. SignalTraceApplication.java

~~~java
package example.tracing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SignalTraceApplication {

    public static void main(String[] args) {
        SpringApplication.run(SignalTraceApplication.class, args);
    }
}
~~~

### 10.4. SignalTraceService.java

~~~java
package example.tracing;

import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Signal;

@Service
public class SignalTraceService {

    private static final Logger log =
            LoggerFactory.getLogger(SignalTraceService.class);

    public Flux<Integer> numbers() {
        return Flux.range(1, 4)
                .name("debug-numbers")
                .doOnSubscribe(subscription ->
                        log.info("numbers subscribed"))
                .doOnRequest(n ->
                        log.info("numbers requested={}", n))
                .log("example.tracing.source")
                .map(value -> value * 10)
                .doOnNext(value ->
                        log.info("mapped value={}", value))
                .doOnEach(signal -> logSignal("numbers", signal))
                .doOnComplete(() ->
                        log.info("numbers completed"))
                .doFinally(type ->
                        log.info("numbers finally={}", type))
                .checkpoint("SignalTraceService.numbers");
    }

    public Flux<Integer> failure() {
        return Flux.just(1, 2)
                .concatWith(Flux.error(
                        new IllegalStateException("demo failure")))
                .doOnNext(value ->
                        log.info("before error value={}", value))
                .doOnError(error ->
                        log.warn("failure pipeline error", error))
                .doFinally(type ->
                        log.info("failure finally={}", type))
                .checkpoint("SignalTraceService.failure");
    }

    public Flux<Long> events() {
        return Flux.interval(Duration.ofMillis(250))
                .doOnRequest(n ->
                        log.info("events requested={}", n))
                .doOnNext(value ->
                        log.debug("event sequence={}", value))
                .doOnCancel(() ->
                        log.info("events cancelled"))
                .doFinally(type ->
                        log.info("events finally={}", type));
    }

    public Flux<Integer> withTraceId(String traceId) {
        return Flux.range(1, 2)
                .doOnEach(signal -> {
                    if (signal.isOnNext()) {
                        String id = signal.getContextView()
                                .getOrDefault("traceId", "unknown");
                        log.info("trace={} value={}", id, signal.get());
                    }
                })
                .contextWrite(context ->
                        context.put("traceId", traceId));
    }

    private void logSignal(String pipeline, Signal<Integer> signal) {
        if (signal.isOnNext()) {
            log.info("{} onNext={}", pipeline, signal.get());
        } else if (signal.isOnError()) {
            log.warn("{} onError", pipeline, signal.getThrowable());
        } else if (signal.isOnComplete()) {
            log.info("{} onComplete", pipeline);
        }
    }
}
~~~

log() is before map, so it observes source values 1, 2, 3, 4. doOnNext is after map, so it logs 10, 20, 30, 40. This placement intentionally shows how operator positioning changes the observation perspective.

doOnEach is after map, so it sees the transformed values. doFinally records complete/error/cancel. The events() method is an infinite stream; when the browser disconnects, cancellation propagates upstream through the pipeline.

### 10.5. SignalTraceController.java

~~~java
package example.tracing;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/debug")
public class SignalTraceController {

    private final SignalTraceService service;

    public SignalTraceController(SignalTraceService service) {
        this.service = service;
    }

    @GetMapping("/numbers")
    public Flux<Integer> numbers() {
        return service.numbers();
    }

    @GetMapping("/failure")
    public Flux<Integer> failure() {
        return service.failure();
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<Long>> events() {
        return service.events()
                .map(value -> ServerSentEvent.<Long>builder(value)
                        .id(Long.toString(value))
                        .event("tick")
                        .build());
    }

    @GetMapping("/context")
    public Flux<Integer> context(
            @RequestHeader(
                    name = "X-Trace-Id",
                    defaultValue = "local"
            ) String traceId) {
        return service.withTraceId(traceId);
    }
}
~~~

The controller returns the Publisher directly; it does not subscribe or block. Spring WebFlux manages the subscription according to the HTTP request lifecycle. With /debug/events, when the browser/curl closes the stream, cancellation can reach doOnCancel and doFinally.

### 10.6. SignalTraceServiceTest.java

~~~java
package example.tracing;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

import static org.assertj.core.api.Assertions.assertThat;

class SignalTraceServiceTest {

    private SignalTraceService service;

    @BeforeEach
    void setUp() {
        service = new SignalTraceService();
    }

    @Test
    void emitsMappedNumbersAndCompletes() {
        StepVerifier.create(service.numbers())
                .expectNext(10, 20, 30, 40)
                .verifyComplete();
    }

    @Test
    void logsErrorWithoutConsumingIt() {
        StepVerifier.create(service.failure())
                .expectNext(1, 2)
                .expectErrorMessage("demo failure")
                .verify();
    }

    @Test
    void doOnEachObservesNextAndComplete() {
        List<String> observed = new ArrayList<>();

        Flux<Integer> source = Flux.just(7, 8)
                .doOnEach(signal -> {
                    if (signal.isOnNext()) {
                        observed.add("next:" + signal.get());
                    } else if (signal.isOnComplete()) {
                        observed.add("complete");
                    }
                });

        StepVerifier.create(source)
                .expectNext(7, 8)
                .verifyComplete();

        assertThat(observed)
                .containsExactly("next:7", "next:8", "complete");
    }

    @Test
    void doOnSuccessReceivesNullForEmptyMono() {
        AtomicReference<String> observed = new AtomicReference<>("unset");

        Mono<String> empty = Mono.<String>empty()
                .doOnSuccess(observed::set);

        StepVerifier.create(empty)
                .verifyComplete();

        assertThat(observed.get()).isNull();
    }

    @Test
    void doOnRequestObservesDemand() {
        AtomicLong requested = new AtomicLong();

        Flux<Integer> source = Flux.range(1, 5)
                .doOnRequest(requested::set);

        StepVerifier.create(source, 0)
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();

        assertThat(requested.get()).isEqualTo(2);
    }

    @Test
    void doFinallyObservesCancellation() {
        AtomicReference<SignalType> finalSignal =
                new AtomicReference<>();

        Flux<Long> source = Flux.interval(Duration.ofMillis(10))
                .doFinally(finalSignal::set);

        StepVerifier.create(source)
                .expectNext(0L)
                .thenCancel()
                .verify();

        assertThat(finalSignal.get()).isEqualTo(SignalType.CANCEL);
    }

    @Test
    void doOnEachCanReadReactorContext() {
        AtomicReference<String> observedTraceId =
                new AtomicReference<>();

        Flux<Integer> source = Flux.just(1)
                .doOnEach(signal -> {
                    if (signal.isOnNext()) {
                        observedTraceId.set(
                                signal.getContextView()
                                        .get("traceId"));
                    }
                })
                .contextWrite(Context.of("traceId", "req-42"));

        StepVerifier.create(source)
                .expectNext(1)
                .verifyComplete();

        assertThat(observedTraceId.get()).isEqualTo("req-42");
    }
}
~~~

The doOnSuccessReceivesNullForEmptyMono test simply subscribes to a publisher with the callback; therefore the callback is invoked and the observed value is null.

### 10.7. application.yml

~~~yaml
spring:
  application:
    name: reactor-signal-tracing

logging:
  level:
    root: INFO
    example.tracing: DEBUG
    example.tracing.source: INFO
~~~

The DEBUG log level for the service package helps inspect event values. In production, set levels according to need and do not enable tracing for all requests under high traffic.

### 10.8. Running the Application and Verifying

In the directory containing pom.xml:

~~~bash
mvn test
~~~

Start the application:

~~~bash
mvn spring-boot:run
~~~

Call the normal pipeline:

~~~bash
curl -i http://localhost:8080/debug/numbers
~~~

Expected response body:

~~~json
[10,20,30,40]
~~~

Logs will show subscription, demand, signals from log() before map, values after map, and the terminal signal. Actual log lines include timestamps, threads, logger names, and formatting depending on backend configuration.

Check error handling:

~~~bash
curl -i http://localhost:8080/debug/failure
~~~

The response will terminate with an HTTP server error; the doOnError log records the demo failure exception. Logging does not make the error disappear.

Check Reactor Context:

~~~bash
curl -i -H "X-Trace-Id: req-42" \
  http://localhost:8080/debug/context
~~~

Body:

~~~json
[1,2]
~~~

The service log contains trace ID req-42 when doOnEach reads ContextView.

Check stream cancellation:

~~~bash
curl -N http://localhost:8080/debug/events
~~~

After receiving a few events, press Ctrl+C. The subscription is cancelled; logs may record events cancelled and events finally=CANCEL.

Do not treat timestamps or thread names in logs as fixed output. They depend on runtime, scheduler, connector, and logging pattern. The HTTP bodies in the examples above are the outputs based on the demo code.

## 11. Reading Logs in Real-World Scenarios

### 11.1. No doOn Logs Seen at All

Check:

- Did a subscriber actually subscribe?
- Did the controller return the Publisher to WebFlux, or was the result discarded?
- Is there a Mono.never() or a publisher emitting no signals?
- Is there a filter/empty branch causing doOnNext not to run?
- Are you waiting on a hot source that already finished emitting before subscription?

Do not add subscribe() immediately. First identify who owns the Publisher's lifecycle.

### 11.2. Subscribed, but No onNext

Check:

- Does the source emit values?
- Has the Subscriber requested elements yet?
- Is an operator buffering/prefetching and waiting for demand?
- Did filter, filterWhen, or switchIfEmpty drop or replace elements?
- Is the Publisher Mono.empty() or Flux.empty()?

Place doOnRequest and doOnNext on both sides of the suspected operator to narrow it down.

### 11.3. onNext Seen, but No Complete

Possible causes:

- The source is an infinite stream such as Flux.interval.
- The connection is still open and waiting for data.
- Downstream has not cancelled.
- The source is hanging because a dependency never emits a terminal signal.
- The pipeline is waiting on an inner publisher that has not completed.

For long-lived streams, having no onComplete can be normal behavior. Monitor idle timeouts, heartbeats, cancellation, and session duration.

### 11.4. Only doFinally=CANCEL Seen

This can be normal when:

- The browser tab is closed.
- The client cancels the HTTP request.
- take(n) receives enough elements and then cancels upstream.
- StepVerifier calls thenCancel().
- A timeout or switch-to-fallback cancels the old source.

Do not assume cancel is an error by default. Cross-check with the request lifecycle and disconnect metrics.

### 11.5. Error Logged, but HTTP Response Differs from Expected

onErrorResume, retry, or an exception handler can alter the outcome after the log position. Place logs before and after recovery operators to see:

- The original error.
- The number of retries.
- The fallback invoked.
- The final outcome.

If a log is placed before onErrorResume, it can record an error even though the client ultimately receives HTTP 200 from the fallback. This is valid behavior.

## 12. Common Mistakes When Using doOn and log

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking the pipeline runs at declaration time | No logs appear when there is no subscriber | Identify the subscription boundary |
| Calling subscribe() in a controller | Framework cannot manage the full lifecycle of secondary work | Return Mono/Flux to WebFlux |
| Using doOnNext to transform data | Side effects do not express transformation | Use map/flatMap |
| Thinking doOnError handles the error | The error still propagates downstream | Use onErrorResume/onErrorMap if needed |
| Logging only doOnComplete | Misses errors and cancellations | Use doOnError and doFinally |
| Thinking cancel means complete | Incorrect lifecycle counting | Distinguish ON_COMPLETE, ON_ERROR, and CANCEL |
| Using Mono.doOnSuccess for empty without null check | Log shows null value, causing confusion | Use doOnNext or check for empty |
| Placing log at the wrong position | Unexpected values before/after map | Place log at the operator boundary to observe |
| Thinking request(10) means 10 records were processed | Confuses demand with emission | Measure onNext or processing metrics |
| Logging every production payload | Huge log volume and potential data exposure | Log metadata, use redaction, sampling |
| Calling blocking logger/appender on the event loop | Increases latency across the pipeline | Use an appropriate logging backend/appender |
| Using MDC ThreadLocal without propagation | Trace ID lost or mixed between requests | Use Reactor Context and context propagation |
| Calling blocking APIs inside doOn | Blocks the reactive processing thread | Compose Publishers or offload blocking work to an appropriate scheduler |
| Relying on the order of multiple chained doFinally calls | Callbacks may run in reverse order | Consolidate cleanup into one callback or a resource abstraction |
| Using doOnDiscard as general-purpose cleanup | Hook does not run if the operator does not support discard | Check discard support and place at the right position |
| Enabling Hooks.onOperatorDebug across all of production | Assembly tracing overhead | Enable only intentionally in debug/test |
| Assuming log() only logs onNext | Ignores request, subscribe, error, complete, cancel | Read signal logs according to operator position |

## 13. Checklist for Observing a Pipeline

When a reactive chain has an issue, follow this order:

1. Identify who subscribes to the Publisher.
2. Add doOnSubscribe to confirm subscription.
3. Add doOnRequest to check demand.
4. Add log() at the source boundary or suspected operator.
5. Add doOnNext before/after filter/map to compare values.
6. Use doOnEach if you need to observe onNext/onError/onComplete or Reactor Context.
7. Use doOnError to log the original error before fallback.
8. Use doFinally to distinguish complete/error/cancel.
9. Use checkpoint("meaningful-name") to add an assembly marker.
10. Check whether logs contain tokens, cookies, PII, or sensitive payloads.
11. Use StepVerifier to reproduce signals in tests.
12. Disable temporary logs/debug hooks after investigation and re-check latency.

## 14. Key Takeaways

- A reactive pipeline is assembled first; a cold source usually runs only when subscribed to.
- Reactive Streams has onSubscribe, onNext, onError, onComplete; request and cancel are Subscription control operations.
- doOnSubscribe observes Subscription; doOnRequest observes demand; doOnNext observes elements at the operator's position.
- doOnEach observes onNext/onError/onComplete as a Signal; use doOnRequest and doOnCancel for demand/cancel.
- Mono.doOnSuccess runs even when empty and receives null; doOnNext only runs when there is a value.
- doOnError only observes errors; onErrorResume or onErrorMap is what changes the error flow.
- doOnTerminate and doAfterTerminate do not cover cancellation; doFinally covers complete/error/cancel.
- log() records multiple Reactive Streams signals at the operator's position; log placement determines the observed data.
- doOn... is for fast, safe side effects; use map/flatMap for transformations and async business work.
- Use Reactor Context for trace metadata; do not assume ThreadLocal/MDC propagates automatically across all schedulers.
- checkpoint() and Hooks.onOperatorDebug() aid assembly debugging but have different overhead.
- Never log credentials, tokens, cookies, CSRF tokens, or sensitive payloads; use metrics/tracing for long-term observability.

**Official Documentation:**
- [Project Reactor 3.7.17 — Reference Guide, Peeking into a Sequence](https://projectreactor.io/docs/core/3.7.17/reference/index.html)
- [Project Reactor 3.7.17 — Flux Javadoc](https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Flux.html)
- [Project Reactor 3.7.17 — Mono Javadoc](https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Debugging Reactor](https://projectreactor.io/docs/core/release/reference/debugging.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Spring Framework 6.2 — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
