# Relationship Between Reactive Streams, Reactor, Reactor Netty, and Spring WebFlux

## 1. The Big Picture

These four names sit at **different layers of responsibility** in reactive programming on the JVM:

| Component | Nature | Primary Responsibility | Example |
| --- | --- | --- | --- |
| **Reactive Streams** | Specification for asynchronous stream processing with demand regulation | Defines the contract between publisher and receiver: Publisher, Subscriber, Subscription, Processor; signal and backpressure rules | Subscriber calls Subscription.request(n) to request up to n elements |
| **Project Reactor** | Reactive programming library on the JVM, implementing the Reactive Streams contract | Provides Mono, Flux types, stream transformation/coordination operators, and schedulers | Flux.range(1, 3).map(n -> n * 2) |
| **Reactor Netty** | Asynchronous networking library built on Netty and integrated with Reactor | Provides HTTP/TCP client, HTTP server, connections, socket read/write, I/O event loop, and reactive APIs | HttpServer, HttpClient; embedded HTTP server commonly used with WebFlux in Spring Boot |
| **Spring WebFlux** | Reactive web framework of Spring Framework | URL mapping, request/response handling, routing, controllers, codecs, validation, error handling, and reactive data source integration | @RestController returning Mono or Flux; RouterFunction |

Common relationship diagram in a Spring Boot WebFlux application running on Reactor Netty:

~~~text
HTTP client
    |
    v
[Reactor Netty: HTTP server, TCP/socket, event loop]
    |
    v
[Spring WebFlux: routing, handler, codec, HTTP response]
    |
    v
[Application: controller/service/repository]
    |
    v
[Project Reactor: Mono / Flux and operators]
    |
    v
[Reactive Streams: Publisher - Subscriber - Subscription contract]
~~~

**Read the diagram by responsibility, not as a chain of libraries that must be called in a strict order.** WebFlux uses Reactor as its reactive API foundation and can run on multiple compatible web runtimes; Reactor Netty is a common server choice, not the definition of WebFlux. Reactive Streams is the foundational contract that Reactor implements, not an HTTP server.

## 2. Reactive Streams: The Foundational Contract

Reactive Streams solves this problem: an asynchronous source can emit data faster than the receiver can process it. Instead of letting the source emit unboundedly and fill up memory, the receiver can **signal demand**.

Four main interfaces in the org.reactivestreams package:

- **Publisher<T>**: source supplying a sequence of elements; subscribe(Subscriber) method.
- **Subscriber<T>**: consumer receiving onSubscribe, onNext, onError, and onComplete signals.
- **Subscription**: link between a Publisher and a Subscriber; request(n) requests up to n more elements; cancel() cancels the subscription.
- **Processor<T,R>**: both a Subscriber and a Publisher, able to receive and emit data (not mandatory when building pipelines).

Basic signal sequence:

~~~text
Publisher.subscribe(subscriber)
         |
         v
Subscriber.onSubscribe(subscription)
         |
         +-- subscription.request(n), n > 0
         |
         +-- onNext(item) up to granted demand
         |
         +-- onComplete() OR onError(error)
         |
         +-- no further onNext after terminal signal
~~~

Points to remember:

1. **request(n) is the number of requested elements**, not bytes and not a command to send a new HTTP request. Demand can be replenished over time.
2. **Backpressure** is the mechanism for controlling production/consumption rates via demand signals. In a multi-operator pipeline, the actual request count may be adjusted by operators (e.g., prefetch), so do not assume every layer forwards the exact value n unchanged.
3. A Subscription can be cancelled via cancel(), such as when a client disconnects; cancellation must be supported by the layers to propagate fully.
4. onError and onComplete are **mutually exclusive terminal signals** for a subscription; after termination, no new data arrives for that subscription.
5. The specification addresses communication between stream components. It **does not itself provide** web APIs, sockets, databases, schedulers, or business policies.

Reactive Streams establishes rules so compatible libraries work together. Sharing the specification does not mean all libraries share the same APIs, operators, or execution strategies.

## 3. Project Reactor: Programming API Built on That Contract

Reactor implements Reactive Streams and provides two characteristic types:

| Type | Max Successful Elements | Common Use Cases |
| --- | --- | --- |
| **Mono<T>** | 0 or 1 | Fetching one record, calling a service returning one result, representing completion with Mono<Void> |
| **Flux<T>** | 0 to many | Lists of results, continuous events, server-sent events streams |

Example of a transformation stream:

~~~java
Flux<Integer> doubled = Flux.range(1, 3)
        .map(n -> n * 2)
        .filter(n -> n >= 4);
// When subscribed: emits 4, 6, then completes.
~~~

This is an **illustrative snippet**, not a standalone Java program. Declaring a pipeline usually only describes what will happen: many Publishers in Reactor are **cold** and do not process anything until subscribed. There are exceptions such as hot publishers and independently running sources, so do not equate all of Reactor with laziness.

A Reactor pipeline is commonly visualized as:

~~~text
Flux/Mono (Publisher) --subscribe--> Subscriber
       |                                |
       +<------- request(n) ------------+
       +--------- onNext -------------->+
       +--------- onComplete/onError --->+
~~~

Different operators serve different roles:

- **map**: synchronously transforms one element.
- **flatMap**: maps an element to another Publisher and merges the results; can change ordering under concurrent processing.
- **concatMap**: processes inner Publishers in order.
- **filter**, **take**, **collectList**, **zip**, **onErrorResume**: filter, limit, collect, combine, recover from errors.
- **subscribeOn**, **publishOn**: adjust the execution context at specific points; do not turn a blocking call into non-blocking on their own.

Example of controlling demand with Reactor, with the reactor-core dependency available via spring-boot-starter-webflux:

~~~java
package com.example.reactiverelationship;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandDemo {
    public static void main(String[] args) {
        Flux.range(1, 4).subscribe(new BaseSubscriber<Integer>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("received=" + value);
                request(1);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("completed");
            }
        });
    }
}
~~~

Expected output:

~~~text
received=1
received=2
received=3
received=4
completed
~~~

In this finite Flux.range example, the subscriber grants demand one element at a time. This demonstrates the **subscription/request/onNext** contract; with other sources, upstream throttling depends on how well that source supports backpressure.

## 4. Reactor Netty: Network Layer and I/O Loop

Netty is an asynchronous networking framework built on the event-loop model. Reactor Netty builds reactive HTTP/TCP APIs on Netty and connects I/O lifecycles with Mono/Flux. In a WebFlux application using Reactor Netty:

1. Reactor Netty accepts connections and HTTP requests, reading bytes from sockets via the event loop.
2. Request data is converted into a form HTTP handlers can consume.
3. WebFlux routes, decodes the body, invokes the application handler, and builds the response.
4. The response stream is encoded; Reactor Netty writes data to the network via asynchronous I/O.

Reactor Netty manages connections, the event loop, and network I/O; it **does not decide URL routing, business logic, or controller validation**. Those web responsibilities belong to WebFlux or application code.

Reactor demand regulation can help control data flow within the pipeline, but **there is no rule that one request(n) corresponds to one TCP read or one HTTP packet**. Buffers, codecs, protocols, client speed, and remote systems affect actual behavior.

In a Spring Boot setup with spring-boot-starter-webflux and no other server configured, Reactor Netty is the embedded server typically auto-configured. Other compatible servers can be used, because **WebFlux does not mean Reactor Netty**.

## 5. Spring WebFlux: Web Layer Using Reactor

Spring WebFlux provides two main programming styles:

- **Annotated controllers**: use @RestController, @GetMapping, @RequestBody; return Mono<T>, Flux<T>, or types supported by the framework.
- **Functional endpoints**: use RouterFunction and HandlerFunction to route and handle requests functionally.

In both styles, Spring handles HTTP concerns such as routing, status codes, headers, codecs, reading bodies, and writing responses. Reactor helps describe asynchronous processing chains, while the HTTP server runtime performs the networking.

### Flow of an HTTP Request

~~~text
GET /numbers
  -> Reactor Netty receives HTTP request
  -> WebFlux maps @GetMapping("/numbers")
  -> Controller returns Flux<Integer>
  -> WebFlux subscribes/orchestrates publisher to write response
  -> Codec serializes data into appropriate HTTP body
  -> Reactor Netty sends bytes to client
~~~

Important note: the controller **returns a Publisher**, and the framework orchestrates the subscription to handle the response. If a controller calls subscribe() itself and discards that subscription, errors, cancellation, and the HTTP lifecycle easily become detached from the framework.

### Runnable Application Example (Java 17+, Maven, Spring Boot 3.3.5)

Create the following three files:

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactive-relationship</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

**src/main/java/com/example/reactiverelationship/ReactiveRelationshipApplication.java**

~~~java
package com.example.reactiverelationship;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveRelationshipApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveRelationshipApplication.class, args);
    }
}
~~~

**src/main/java/com/example/reactiverelationship/RelationController.java**

~~~java
package com.example.reactiverelationship;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class RelationController {

    @GetMapping("/relation")
    public Mono<String> relation() {
        return Mono.just("WebFlux -> Reactor -> Reactor Netty");
    }

    @GetMapping("/numbers")
    public Flux<Integer> numbers() {
        return Flux.range(1, 3).map(n -> n * 2);
    }
}
~~~

In the directory containing pom.xml, run:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -s http://localhost:8080/relation
curl -s http://localhost:8080/numbers
~~~

Response bodies (respectively):

~~~text
WebFlux -> Reactor -> Reactor Netty
[2,4,6]
~~~

Spring Boot places the appropriate dependencies on the classpath: Spring WebFlux supports routing/controllers and HTTP encoding, reactor-core provides Mono/Flux, and Reactor Netty provides the default network server. In this example, the string at the endpoint is a simple mnemonic for the layers; **it does not mean WebFlux cannot run on another server**.

If you want to run DemandDemo separately within the same project, create another Java file matching the class name in the same package and execute it from your IDE or compile/run with the Maven dependency classpath. The DemandDemo example does not require an HTTP server.

### Where WebClient Fits

WebFlux also provides **WebClient** for a reactive HTTP client. When used with defaults in an appropriate setup, WebClient can use Reactor Netty HttpClient to perform I/O. WebClient is the **Spring-layer client API**; Reactor Netty HttpClient is the underlying **network connector**. Do not mistake WebClient for the WebFlux HTTP server.

## 6. Common Misconceptions and Technical Consequences

| Misconception | Accurate Understanding | Design Consequence |
| --- | --- | --- |
| “Reactive Streams is an HTTP library” | It is a protocol-independent specification for Publisher/Subscriber/backpressure | Choose WebFlux/Reactor Netty or another component for HTTP |
| “Reactor and Reactor Netty are the same thing” | Reactor handles pipelines; Reactor Netty integrates network I/O | Flux/Mono can be used in applications without a web server |
| “WebFlux must run on Reactor Netty” | WebFlux can run on other compatible web runtimes | Choose runtime based on environment and deployment requirements |
| “All publishers automatically prevent out-of-memory errors” | Backpressure only takes effect according to each source's and operator's semantics; some sources use buffer/drop/error strategies | Inspect sources, operators, buffering, and actual load |
| “Mono/Flux always run on another thread” | A Publisher does not automatically imply multithreading or async I/O | Understand schedulers and where code executes |
| “WebFlux is always faster than Spring MVC” | Benefits typically appear with many non-blocking I/O operations and high concurrency; better latency/throughput is not guaranteed for all workloads | Measure load, measure latency, and account for operational cost |
| “Just returning Mono makes a blocking call non-blocking” | JDBC, Thread.sleep(), and blocking HTTP calls still block threads if invoked directly | Prefer non-blocking drivers/APIs, or isolate blocking properly |
| “Controllers should call subscribe() themselves” | WebFlux owns the subscription to coordinate response, errors, and cancellation | Return the Publisher to the framework instead of calling subscribe() |

### Blocking on the Event Loop

Conceptually wrong example:

~~~java
@GetMapping("/bad")
public Mono<String> bad() {
    String value = legacyBlockingClient.call(); // Blocks the request-processing thread.
    return Mono.just(value);
}
~~~

Wrapping a synchronous result in Mono.just **does not make the original call non-blocking**. If a legacy API cannot be replaced yet, you can isolate the blocking work onto a dedicated scheduler:

~~~java
@GetMapping("/legacy")
public Mono<String> legacy() {
    return Mono.fromCallable(() -> legacyBlockingClient.call())
            .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
}
~~~

These two snippets only **illustrate structure**, assuming a variable legacyBlockingClient and method call() already exist; they are not standalone Java classes. boundedElastic helps avoid blocking the event loop for bounded blocking work, but it still consumes threads and can bottleneck under high load. The preferred long-term solution is using a genuinely non-blocking client/driver where appropriate.

### Backpressure Is Not Magic for HTTP

With a bounded finite source like Flux.range, it is easy to regulate how many elements are pushed to the subscriber. With external event sources, WebSockets, message brokers, or network peers, propagating demand back to the source may require adapters, buffers, and explicit policies. Distinguish between:

- **Reactive Streams demand**: the number of elements requested by the subscriber in the pipeline.
- **Protocol flow control**: mechanisms such as TCP receive windows, HTTP/2 flow control, and queues.
- **Resource limits**: threads, connection pools, memory, buffers, timeouts, queues.

They can interact, yet they are not a single mechanism. Relying solely on Mono/Flux does not replace load limits, timeouts, and load-resilience testing.

## 7. When to Use Each and Self-Check Questions

- Use **Reactor** when you need to compose asynchronous or reactive operations in a Java application, even without HTTP.
- Use **Reactor Netty** when you need a reactive HTTP/TCP client/server or when a WebFlux application selects it as the network runtime.
- Use **Spring WebFlux** when building Spring reactive endpoints, WebClient calls, or reactive web integrations. Consider it when the entire I/O path can execute non-blockingly.
- Use **Reactive Streams** as the mental contract for signals, cancellation, and demand when evaluating behavior across every layer.

Three self-check questions:

1. If you remove Reactor Netty and run WebFlux on another compatible server, do Mono/Flux and the Reactive Streams contract disappear? **No**. They are different layers.
2. If you use Flux.range in a CLI application without Spring, do you need WebFlux? **No**. Reactor runs independently of the web framework.
3. If a controller returns Mono but invokes blocking JDBC right before creating the Mono, is the request non-blocking? **No**. The JDBC call is still blocking and requires an appropriate handling architecture.

**Core relationship:** Reactive Streams defines the demand-driven data-passing contract; Reactor implements the contract and provides the Mono/Flux API; Reactor Netty bridges the reactive API to asynchronous networking; Spring WebFlux uses Reactor for HTTP programming and can use Reactor Netty as its network runtime. Recognizing the four layers clearly helps with technology selection, investigating blocked threads, and designing realistic backpressure.