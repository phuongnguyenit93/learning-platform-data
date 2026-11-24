# What Is Reactive Programming and Why Does Spring Support It?

## 1. The Problem Reactive Programming Solves

In a web application, request processing time often includes **I/O wait time**: querying a database, calling another service, receiving data over the network, or sending events to a browser. With synchronous processing, code may pause at an I/O call until a result arrives; the executing thread cannot continue that work while waiting.

**Reactive programming** is a way of building programs around asynchronous streams of data and events. Instead of demanding a value immediately, you describe the **chain of processing that will happen when data arrives**, along with completion and error-handling rules. The system receives data signals, transforms them, combines sources, and forwards results to the consumer.

For example, instead of thinking “call service A, wait; then call service B, wait,” you can describe non-blocking I/O operations, combine results when ready, and return a response without holding a thread just to wait on the network. This benefit applies when **all the involved I/O segments genuinely support non-blocking execution**.

Three concepts to distinguish:

- **Asynchronous:** work can complete later, with the result delivered via a signal/callback/future; this does not mean it is always non-blocking at every layer.
- **Non-blocking:** the executing thread is not held solely to wait for an I/O operation to finish.
- **Reactive:** organizing data and events into a pipeline with rules for emission, consumption, completion, errors, and (in the Reactive Streams model) regulating the rate of consumption. Reactive does not automatically mean running in parallel or running faster.

“Reactive” in **Reactive Streams** is a specification for communication between a publisher and a subscriber; a “reactive system” in software architecture is a broader concept. The two terms should not be equated.

## 2. Core Mechanism: Data Streams, Signals, and Backpressure

In the Spring reactive ecosystem, the **Project Reactor** library implements the Reactive Streams model. The key components are:

| Component | Responsibility |
| --- | --- |
| Publisher | A source describing the ability to emit elements over time. |
| Subscriber | A party that subscribes to receive data, errors, or completion signals. |
| Subscription | A registration relationship that allows requesting more elements and cancelling the stream. |
| Operator | A pipeline transformation/combination operation, such as map, filter, flatMap, zip, timeout. |

The typical signal flow is: Subscriber subscribes to Publisher → receives Subscription → sends a request for the number of elements it can accept (request(n)) → receives onNext signals → terminates with **onComplete** or **onError**; Subscriber can **cancel**. A stream has at most one terminal signal. An error is a terminal signal, not an ordinary data element.

**Backpressure** solves the situation where a source emits faster than the consumer can process. Under the Reactive Streams contract, the Subscriber can request data in bounded amounts via request(n) instead of being forced to accept an unbounded amount. However, backpressure only works fully when the components along the path cooperate to support it; you should not assume that every driver, network protocol, or external data source has equivalent throttling capabilities.

Two Publisher types are used frequently in Reactor:

- **Mono<T>:** emits at most one element, or completes empty, or signals an error. Suitable for fetching a single record, an API call result, a write command, or an HTTP response.
- **Flux<T>:** emits 0 to many elements, then completes or errors. Suitable for lists, continuous events, data streams, and multi-item responses.

Most Reactor pipelines are **lazy**: declaring a Flux/Mono with operators does not start the work; it is triggered when there is a **subscription**. By default, many sources are *cold* (each subscription creates a new execution); some *hot* sources can emit signals independently of subscription timing. Choosing cold vs. hot affects data sharing, replay, and how many times I/O is executed.

## 3. Why Does Spring Support the Reactive Model?

Spring serves both traditional web applications and systems with high numbers of concurrent connections, many I/O calls, and continuously updating data. Reactive is **an additional option** to address these needs:

1. **Efficient thread usage when I/O takes a large share of time.** With a non-blocking stack, a smaller number of threads can coordinate many requests waiting on the network; the application does not have to dedicate a blocked thread to each I/O operation.
2. **Handling many concurrent connections and long-lived streams.** Server-Sent Events (SSE), WebSocket, and sequential data emitters are easy to express via Publisher.
3. **Composing asynchronous calls.** Operators make it possible to coordinate results from multiple services and handle timeouts, fallbacks, cancellation, and errors within a clear pipeline.
4. **Throttling data flow.** Reactive Streams provides a demand/backpressure mechanism at supported boundaries, helping design controllable consumption flows.
5. **Consistency across the programming ecosystem.** The same Mono/Flux model can flow through HTTP, WebClient, reactive data access, and business logic, reducing fragmented conversions between different callback styles.

The primary goal is **strong scalability for I/O-heavy concurrent workloads and expressive modeling of data streams**. Reactive **does not guarantee lower per-request latency**, does not make the CPU compute faster on its own, and does not replace the need for performance measurement.

### Building Blocks in Spring

| Technology | Role |
| --- | --- |
| **Project Reactor** | Foundational library providing Mono, Flux, and operators; implements Reactive Streams. |
| **Spring WebFlux** | Reactive web stack for handling HTTP, controller programming, or functional routing; supports streaming. |
| **WebClient** | HTTP client with a reactive API; suitable for non-blocking network calls. |
| **Spring Data R2DBC** | Relational database access using reactive APIs/drivers; unlike traditional JDBC, which is blocking. |
| **Spring Data reactive repositories** | Provides reactive repositories when the corresponding data store and driver genuinely support them. |
| **Spring Boot** | Auto-configures and runs a WebFlux application when the appropriate starter is selected. |

**Spring MVC and Spring WebFlux coexist.** MVC is a great choice for many conventional HTTP applications; WebFlux fits when a non-blocking pipeline or streaming is needed. WebFlux can run on an appropriate supported runtime, commonly using Reactor Netty with an event-loop model. Spring does not force every application to switch to reactive.

## 4. A Runnable Reactor Pipeline on Java 17+

The following example illustrates how to declare, transform, filter, and consume Mono/Flux. This is a **Reactor Core** example, not yet an HTTP application.

Create the directory structure:

~~~text
reactive-intro/
├── pom.xml
└── src/main/java/ReactiveIntro.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-intro</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>ReactiveIntro</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **src/main/java/ReactiveIntro.java**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveIntro {
    public static void main(String[] args) {
        Flux.just("spring", "reactor", "webflux")
                .map(String::toUpperCase)
                .filter(word -> word.length() >= 7)
                .doOnNext(word -> System.out.println("Flux: " + word))
                .blockLast();

        Mono.just("reactive")
                .map(String::toUpperCase)
                .doOnNext(word -> System.out.println("Mono: " + word))
                .block();
    }
}
~~~

With **JDK 17+** and Maven installed, run inside the project directory:

~~~bash
mvn -q compile exec:java
~~~

Program stdout:

~~~text
Flux: REACTOR
Flux: WEBFLUX
Mono: REACTIVE
~~~

Step-by-step explanation:

- Flux.just creates a Publisher from three strings; map converts them to uppercase; filter drops “SPRING” because it has 6 characters; doOnNext prints the remaining two elements.
- Mono.just creates a Publisher of at most one element; map converts it to “REACTIVE”.
- blockLast()/block() creates a subscription and **waits** for completion so the console program does not exit before the output can be observed. This waiting pattern is only used at **demo/synchronous program boundaries**; do not insert block() into WebFlux non-blocking request-handling flows.
- Because the source in this example is in-memory data, the example mainly illustrates **the pipeline and subscription model**; it does not demonstrate the non-blocking I/O advantage. That advantage appears when connecting the pipeline to genuinely non-blocking network/database APIs.

## 5. How Reactivity Appears in a Spring API

In a Spring Boot project configured with **spring-boot-starter-webflux**, the controller below emits three values as **Server-Sent Events**. This is a **controller snippet for an existing WebFlux project**; it is not a standalone program lacking bootstrap code.

~~~java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class TickController {
    @GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Long> ticks() {
        return Flux.interval(Duration.ofSeconds(1)).take(3);
    }
}
~~~

When the application is running, an HTTP request to **GET /ticks** receives values 0, 1, 2 over time and then completes. The framework subscribes to the Publisher and writes data to the HTTP response according to WebFlux's mechanism. The controller **returns the Publisher** so the framework manages the lifecycle, rather than calling subscribe() itself and returning before processing finishes.

**Mono/Flux does not mean non-blocking in every case.** For example, placing a blocking JDBC query or Thread.sleep() inside map() still holds the running thread while waiting. To take advantage of WebFlux, the I/O path needs to use compatible APIs such as WebClient and reactive database drivers when available.

## 6. Comparison with Traditional Processing

| Criterion | Common Model with Spring MVC and Blocking APIs | Spring WebFlux with Non-blocking I/O |
| --- | --- | --- |
| Processing mindset | Call a function, receive the result or wait for it before moving on. | Declare a Publisher and transformations to apply when signals arrive. |
| While waiting for I/O | The thread calling a blocking API is usually held waiting. | The thread can continue coordinating other work if I/O is genuinely non-blocking. |
| Interface | Values, collections, ResponseEntity, along with MVC's other async supports. | Mono/Flux or other types supported by WebFlux. |
| Streaming | Has MVC's own streaming/async mechanisms. | Streams are the central model, well suited to SSE and continuous flows. |
| Complexity | Easy to trace via a synchronous call stack. | Requires understanding subscriptions, operators, scheduling, context, and error signals. |

Two false conclusions to avoid:

- **Reactive does not mean every operation runs on its own thread.** A pipeline can run right on the calling thread when using a synchronous source; a scheduler decides when to switch threads, while an event loop supports non-blocking I/O.
- **Reactive does not mean parallel.** Running CPU tasks in parallel requires dedicated design and measurement; simply using Flux/Mono does not automatically distribute tasks across multiple cores.

## 7. When to Choose, When to Reconsider?

**WebFlux/reactive is often worth considering** when a service has a very high number of concurrent connections where most time is spent waiting on I/O; needs SSE/WebSocket/streams; calls multiple external services and wants to compose Publishers; or the system already uses non-blocking drivers and libraries end-to-end.

**Spring MVC is often simpler and more effective** for traditional CRUD, moderate traffic, systems relying on JDBC/blocking libraries, and teams familiar with sequential programming. With modern Java, **virtual threads** are also an option worth measuring for blocking I/O workloads, though they do not turn JDBC or blocking APIs into Reactive Streams.

The decision should be based on **workload type (I/O vs. CPU), number of concurrent requests/connections, libraries in use, operational readiness, and actual measurements**, rather than choosing reactive by default because of a modern label.

## 8. Common Beginner Mistakes

1. **Calling block(), blockFirst(), or blockLast() inside a WebFlux HTTP handling path.** This blocks the thread and can cause errors on event-loop threads. Return Mono/Flux for the framework to handle, and use operators to chain the pipeline.
2. **Wrapping a blocking operation in Mono.just() and assuming it is non-blocking.** The value passed to Mono.just() is evaluated eagerly beforehand; if the DB query/network call is blocking, blocking has already occurred. When forced to use a blocking API, isolate the boundary clearly and consider an appropriate scheduler, such as boundedElastic, as a bounded transitional solution.
3. **Calling subscribe() manually in a controller/service “to make sure it runs.”** This easily breaks error handling, request cancellation, and response timing. Compose Publishers and return them to the layer responsible for subscribing.
4. **Ignoring onError, timeout, and cancel.** An error in a pipeline is a terminal signal; handle it with appropriate operators, and set timeouts for external calls.
5. **Confusing map with flatMap.** map is used when the function returns a plain value; flatMap is appropriate when the function returns a Publisher to be merged into the asynchronous chain. flatMap can interleave results; if ordering is a business requirement, choose the right operator.
6. **Assuming ThreadLocal always follows the request.** A pipeline can switch threads; contextual data in a reactive application should flow through supported mechanisms such as Reactor Context / the corresponding Spring support.
7. **Assuming backpressure always prevents out-of-memory errors on its own.** You must understand data source limits, buffering, downstream processing speed, and the mechanics of each driver/protocol.
8. **Optimizing without measuring.** Reactive flows add complexity for debugging, tracing, and testing; compare throughput, latency, CPU, memory, and stability under realistic load before deciding.

## 9. Key Takeaways

Reactive programming describes **what happens when data/events arrive** through a Publisher → Subscriber pipeline, with data, completion, and error signals; Reactive Streams adds a demand/backpressure mechanism. In Spring, **Reactor** provides Mono/Flux, **WebFlux** serves reactive HTTP, **WebClient** supports asynchronous HTTP calls, and reactive data components enable non-blocking chaining when supported by the driver.

**Spring supports reactive to offer an additional model for concurrent I/O, streaming, and asynchronous composition**, alongside Spring MVC. Its value depends on whether the pipeline is genuinely non-blocking and whether the problem requires scaling in that direction.