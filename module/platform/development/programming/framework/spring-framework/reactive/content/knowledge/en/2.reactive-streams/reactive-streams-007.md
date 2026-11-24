# Relationship with java.util.concurrent.Flow and Adapters

## 1. The Problem: Why Are There Two Nearly Identical Interface Sets?

Reactive Streams is a specification for exchanging asynchronous data streams with **backpressure**: the receiver announces how many items it is ready to accept, and the producer sends only within the granted demand. On the JVM, the specification originally used interfaces in the **org.reactivestreams** package. Starting in **Java 9**, the JDK introduced corresponding interfaces into **java.util.concurrent.Flow**.

The crucial point is that they share **the same model and core rules, but are not the same Java types**. An object declared as Flow.Publisher<T> is not automatically an org.reactivestreams.Publisher<T>, even though the method names and meanings match. When API A returns a Flow.Publisher while library B expects an org.reactivestreams.Publisher, you need an **adapter** to bridge the two worlds.

Diagram:

~~~text
Java/JDK APIs                              Reactive Streams Ecosystem
java.util.concurrent.Flow                  org.reactivestreams
  Flow.Publisher<T>     <-- adapter -->       Publisher<T>
  Flow.Subscriber<T>    <-- adapter -->       Subscriber<T>
  Flow.Subscription     <-- adapter -->       Subscription
  Flow.Processor<T,R>   <-- adapter -->       Processor<T,R>
                                                       |
                                                       v
                                                Project Reactor
                                                 Flux<T>/Mono<T>
                                                       |
                                                       v
                                                Spring WebFlux
                                           handler / controller / WebClient
~~~

An **adapter** converts how the two sides view the same signal protocol. It does not by itself make a stream faster, create new backpressure, or turn blocking operations into non-blocking ones.

## 2. One-to-One Mapping Between the Interfaces

| Reactive Streams (org.reactivestreams) | JDK Flow (java.util.concurrent) | Role |
| --- | --- | --- |
| Publisher<T> | Flow.Publisher<T> | Allows a Subscriber to register via subscribe |
| Subscriber<T> | Flow.Subscriber<T> | Receives onSubscribe, onNext, onError, onComplete |
| Subscription | Flow.Subscription | Coordinates request(n) and cancel() |
| Processor<T,R> | Flow.Processor<T,R> | Both consumes T and emits R |

Example of core signatures with identical semantics:

~~~java
// In org.reactivestreams.Publisher<T>:
void subscribe(org.reactivestreams.Subscriber<? super T> subscriber);

// In java.util.concurrent.Flow.Publisher<T>:
void subscribe(java.util.concurrent.Flow.Subscriber<? super T> subscriber);
~~~

The two Subscriber parameters here are **two distinct types**, so a Publisher cannot be cast safely merely because the names and shapes match. Casting or treating the two interface sets as identical will either fail to compile or throw a ClassCastException; use an explicit adapter.

Important signals and rules for **each subscription**:

1. The Publisher calls onSubscribe, passing the Subscription to the Subscriber.
2. The Subscriber calls request(n) with n > 0 to grant demand; total demand is cumulative, subject to the protocol's rules.
3. The Publisher emits onNext(item) without exceeding remaining demand.
4. The Publisher terminates with **either** onComplete() or onError(error), after which it emits no new data signals for that subscription.
5. The Subscriber can cancel with cancel(); stopping emission and releasing resources depend on the source implementation.
6. Signals must be serialized per the protocol's rules, even when components process data across multiple threads.

**request(5)** means requesting at most five **items**, not five bytes, five connections, or five HTTP requests. Calling request(0) or a negative request violates the protocol, and a spec-compliant source must signal an error per Subscription rules.

## 3. What java.util.concurrent.Flow Is and Is Not

Flow belongs to the **java.base** module, so Java 17 includes these interfaces out of the box without installing Project Reactor, Spring, or external Reactive Streams dependencies. Flow is a **contract** for data-producing/receiving components; the Flow class itself does not provide operators like map, flatMap, or zip as Flux does.

The JDK provides **SubmissionPublisher<T>**, a Flow.Publisher implementation for publishing items to currently subscribed subscribers:

- Dispatches signals asynchronously via an Executor.
- Maintains per-subscriber buffers and handling for slow receivers.
- **submit(item)** may block when a subscriber's buffer is full; **offer(...)** provides options when an item cannot be accepted.
- Items sent before a subscriber registers are not replayed to that subscriber by default.
- You must manage closing the publisher and the executor lifecycle when creating dedicated resources.

This point is easy to misunderstand: **having a backpressure protocol in Flow does not mean every call on SubmissionPublisher is non-blocking**. You need to check each API's behavior and run load tests.

### Pure-JDK Java 17 Example: Receiving Item by Item Based on Demand

Save as **FlowBasicsDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowBasicsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch subscribed = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> source =
                new SubmissionPublisher<>(executor, 16)) {

            source.subscribe(new Flow.Subscriber<Integer>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription value) {
                    subscription = value;
                    subscription.request(1);
                    subscribed.countDown();
                }

                @Override
                public void onNext(Integer value) {
                    System.out.println("item=" + value);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    error.printStackTrace();
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("complete");
                    completed.countDown();
                }
            });

            if (!subscribed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("No subscription");
            }

            source.submit(10);
            source.submit(20);
            source.submit(30);
            source.close();

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Stream did not complete");
            }
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Run on JDK 17+:

~~~bash
javac FlowBasicsDemo.java
java FlowBasicsDemo
~~~

Output under normal execution conditions:

~~~text
item=10
item=20
item=30
complete
~~~

Here **onSubscribe** requests one item; **onNext** requests one more item. CountDownLatch ensures the example waits for the subscription and completion signals rather than relying on thread timing. Callbacks execute via the executor, so processing remains asynchronous. The example includes timeouts to detect missed signals; if an error occurs, stderr may contain a stack trace rather than those four lines.

## 4. What Does an Adapter Convert?

An adapter bridges the **interface types** on both sides. For a Publisher:

~~~text
Flow.Publisher<T>
      |
      | subscribe(Flow.Subscriber)
      |          adapted into
      v
org.reactivestreams.Publisher<T>
      |
      | subscribe(org.reactivestreams.Subscriber)
      v
Pipeline using Reactor / Reactive Streams library
~~~

At the conversion boundary, the adapter provides corresponding wrappers for Subscriber and Subscription. When downstream grants request(n), the adapter forwards the request call toward the source; when the source sends onNext, onError, or onComplete, the adapter forwards the signal to the receiver per the contract.

Four distinctions to keep clear:

- **Interface conversion ≠ transforming individual values**: an adapter normally keeps the same item type T. Use map if you want to change data contents.
- **Adapter ≠ scheduler**: an adapter does not automatically create a separate executor/thread for business processing.
- **Adapter ≠ unbounded buffer**: memory bounds are still determined by the source, operators, runtime, and backpressure strategy.
- **Adapter ≠ fixing a protocol-violating source**: if a Publisher violates demand or emits signals out of order, wrapping it in an adapter does not guarantee automatically fixing that behavior.

Adapters are especially useful **at integration boundaries**: when a JDK API returns a Flow.Publisher while the service layer uses Flux; or when a Reactor service needs to expose standard Flow APIs to a Java component that does not depend on Reactor.

## 5. Option 1: Built-in JdkFlowAdapter in Project Reactor

Reactor provides **reactor.adapter.JdkFlowAdapter**, included in the reactor-core library, with two main methods:

| Conversion | Method | Result |
| --- | --- | --- |
| Flow.Publisher<T> → Flux<T> | JdkFlowAdapter.flowPublisherToFlux(source) | A Flux<T> able to use Reactor operators |
| org.reactivestreams.Publisher<T> → Flow.Publisher<T> | JdkFlowAdapter.publisherToFlowPublisher(source) | Publisher in the JDK Flow type |

Both Mono<T> and Flux<T> belong to the Reactive Streams family, so either can be passed to the second method. If you want to preserve Mono's 0-or-1 item semantics when adapting back from a Flow.Publisher, ensure the source contract and choose an appropriate conversion; **flowPublisherToFlux** returns a Flux and does not inherently promise a Mono output.

### Runnable Example: Converting Back and Forth Between Reactor ↔ JDK Flow

Uses **Java 17+, Maven 3.9+**. Structure:

~~~text
flow-reactor-bridge/
  pom.xml
  src/main/java/example/FlowReactorBridgeDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>flow-reactor-bridge</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.11.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/FlowReactorBridgeDemo.java**:

~~~java
package example;

import java.util.concurrent.Flow;
import reactor.adapter.JdkFlowAdapter;
import reactor.core.publisher.Flux;

public class FlowReactorBridgeDemo {
    public static void main(String[] args) {
        // Reactive Streams ecosystem -> standard JDK Publisher type.
        Flux<Integer> reactorSource = Flux.range(1, 3);
        Flow.Publisher<Integer> flowSource =
                JdkFlowAdapter.publisherToFlowPublisher(reactorSource);

        // Standard JDK Publisher type -> Flux to use Reactor operators.
        Flux<Integer> reactorAgain =
                JdkFlowAdapter.flowPublisherToFlux(flowSource);

        reactorAgain
                .map(number -> number * 10)
                .doOnNext(number -> System.out.println("value=" + number))
                .blockLast(); // Only use at the boundary of a demo app.
    }
}
~~~

From the directory containing pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.FlowReactorBridgeDemo
~~~

Lines printed by the program:

~~~text
value=10
value=20
value=30
~~~

This is a pipeline with a finite **Flux.range** source; blockLast() is used in **main** to wait for completion in the CLI example. In a WebFlux controller, do not call blockLast()/block() to wait on a Publisher: the framework subscribes and manages the response.

The example above demonstrates both adapter directions using a Reactor source, so it **does not benchmark or prove the behavior of an external Flow.Publisher outside Reactor**. In practice, a Flow.Publisher may come from a JDK component, another library, or a custom Publisher complying with the Flow contract.

## 6. Option 2: org.reactivestreams.FlowAdapters

Reactive Streams provides **org.reactivestreams.FlowAdapters** to convert interfaces between the two sets. Do not confuse this class with **reactor.adapter.JdkFlowAdapter**.

| FlowAdapters Method | Effect |
| --- | --- |
| toPublisher(Flow.Publisher) | Flow Publisher → Reactive Streams Publisher |
| toFlowPublisher(Publisher) | Reactive Streams Publisher → Flow Publisher |
| toSubscriber(Flow.Subscriber) | Flow Subscriber → Reactive Streams Subscriber |
| toFlowSubscriber(Subscriber) | Reactive Streams Subscriber → Flow Subscriber |
| toProcessor(Flow.Processor) | Flow Processor → Reactive Streams Processor |
| toFlowProcessor(Processor) | Reactive Streams Processor → Flow Processor |

Depending on the dependencies and version in use, check which artifact actually provides FlowAdapters on your classpath. For example, with **org.reactivestreams:reactive-streams:1.0.4**, the FlowAdapters API is published in that artifact's Javadoc; older projects had a separate **reactive-streams-flow-adapters** artifact in earlier versions. Avoid putting multiple different versions of the same class on the classpath simultaneously.

Short example (assuming reactor-core and Reactive Streams 1.0.4 are on the classpath):

~~~java
import java.util.concurrent.Flow;
import org.reactivestreams.FlowAdapters;
import org.reactivestreams.Publisher;
import reactor.core.publisher.Flux;

// Reactor Flux is a Reactive Streams Publisher.
Publisher<Integer> rsPublisher = Flux.range(1, 3);

// Reactive Streams -> JDK Flow.
Flow.Publisher<Integer> flowPublisher =
        FlowAdapters.toFlowPublisher(rsPublisher);

// JDK Flow -> Reactive Streams.
Publisher<Integer> rsAgain =
        FlowAdapters.toPublisher(flowPublisher);

// Combine with Reactor.
Flux.from(rsAgain)
    .map(n -> n + 100)
    .doOnNext(System.out::println)
    .blockLast();
~~~

The snippet above **is an example placed inside a method, not a standalone Java class**. With Flux.range as the source and normal execution, it prints 101, 102, 103 on three lines. The toSubscriber/toFlowSubscriber and toProcessor/toFlowProcessor methods are useful when **the integrated contract is a subscriber or processor**, not only a publisher.

Practical selection:

- Already using Reactor and need to convert between **Flux** and **Flow.Publisher**: choose JdkFlowAdapter, concise and direct.
- Writing a library that wants to bridge the two **standard interface** sets without relying on Reactor operators: choose FlowAdapters, using the proper managed dependency.
- Building a WebFlux endpoint: convert Flow.Publisher to Flux at the service/controller boundary and return the Publisher to the framework.

There is no need for multiple round-trip conversions if both sides already use the same Publisher type.

## 7. Using This in Spring WebFlux

**Spring WebFlux** uses Reactor as its reactive programming foundation. Controllers can return Mono/Flux; Reactor expresses the Reactive Streams contract; the web runtime handles HTTP. When a JDK API or external library supplies a Flow.Publisher, adapt it at that boundary:

~~~text
External source providing Flow.Publisher<T>
                   |
      JdkFlowAdapter.flowPublisherToFlux(...)
                   |
                Flux<T>
                   |
          map / filter / timeout
                   |
           Spring WebFlux controller
                   |
             HTTP response
~~~

Example controller structure (illustrative snippet; requires an ExternalFlowService bean and a stream() method provided by the application):

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.adapter.JdkFlowAdapter;
import reactor.core.publisher.Flux;

@RestController
class FeedController {
    private final ExternalFlowService external;

    FeedController(ExternalFlowService external) {
        this.external = external;
    }

    @GetMapping("/feed")
    Flux<String> feed() {
        return JdkFlowAdapter
                .flowPublisherToFlux(external.stream())
                .map(String::trim);
    }
}
~~~

Assumes **external.stream()** returns **java.util.concurrent.Flow.Publisher<String>**. There is no need to call subscribe() manually in the controller; WebFlux coordinates subscription with the HTTP lifecycle. Cancellation caused by client disconnect can propagate through the adapter, yet will only stop actual work if **the source and intermediate layers honor cancel()**.

**Spring WebFlux is not synonymous with java.util.concurrent.Flow**: although the two interface sets are compatible in model, developers should still check the exact public API of the library they integrate with rather than assuming every Flow.Publisher can be passed directly to a method expecting org.reactivestreams.Publisher.

## 8. How Does Backpressure Flow Through an Adapter?

Suppose a Subscriber receives data through a Flux adapted from a Flow.Publisher:

~~~text
Flow source                         Adapter                   Reactor subscriber
     |                                  |                              |
     | <------------ request(2) --------|<------ request(2) ---------|
     | --------- onNext(A) ------------>|------ onNext(A) ---------->|
     | --------- onNext(B) ------------>|------ onNext(B) ---------->|
     | <------------ request(1) --------|<------ request(1) ---------|
     | --------- onNext(C) ------------>|------ onNext(C) ---------->|
     | -------- onComplete() ---------->|----- onComplete() -------->|
~~~

This is a **simplified logical diagram**. Real operators may prefetch, batch, split, or amplify demand, so you cannot assume requests from the final consumer always pass through every operator untouched. What matters is that the producer preserves the protocol and never sends past the demand for each subscription.

Clearly distinguish mechanisms that are often lumped together:

- **Reactive Streams / Flow request(n)**: regulates **item counts** between Publisher and Subscriber.
- **SubmissionPublisher buffer**: holds pending items according to the implementation's policy.
- **Network flow control**: TCP, HTTP/2, connection pools, or queues at the network layer.
- **Reactor operators**: may prefetch, buffer, drop, limitRate, or switch schedulers depending on operator semantics.

An adapter does not replace the other layers. If upstream generates data uncontrollably, you must configure bounds, timeouts, buffer monitoring, and error handling at the source or appropriate layer.

## 9. Common Integration Mistakes

### Mistake 1: Assuming Two Publishers with the Same Name Can Be Assigned Directly

~~~java
// Does not compile if the method returns Flow.Publisher<String>:
org.reactivestreams.Publisher<String> value = externalFlowMethod();
~~~

Fix with an adapter:

~~~java
org.reactivestreams.Publisher<String> value =
        org.reactivestreams.FlowAdapters.toPublisher(
                externalFlowMethod());
~~~

### Mistake 2: Calling subscribe() Manually in a Controller

If a controller calls subscribe() itself to process data and returns something else, the pipeline risks losing linkage with response writing, request cancellation, and error propagation. Normally, **return Flux/Mono** to WebFlux.

### Mistake 3: Converting Types and Assuming Blocking Disappeared

~~~java
Flow.Publisher<String> source = obtainFlowPublisher();
Flux<String> result = JdkFlowAdapter.flowPublisherToFlux(source);
~~~

An adapter does not guarantee that work inside the source is non-blocking; that depends on the implementation. If a Flow.Publisher is built on blocking threads or SubmissionPublisher.submit() occasionally blocks because the buffer is full, wrapping it into a Flux does not eliminate blocking.

### Mistake 4: Confusing Completion, Error, and Cancellation

- **onComplete**: source finished normally.
- **onError**: source terminated with an error; must not emit onComplete afterward.
- **cancel**: Subscriber proactively stops the subscription; receiving onComplete after cancel is not required.

When handling errors via onErrorResume or retry in Reactor, re-subscriptions and execution counts can change; the adapter is not responsible for retry policies.

### Mistake 5: Ignoring the Lifecycle of Hot Sources

SubmissionPublisher generally emits to **currently present subscribers**. If you subscribe after items were submitted, do not assume replay. If a source needs closing, manage close(), executors, and completion signals in the right place. Do not retain SubmissionPublishers or subscriptions that are no longer consumed.

### Mistake 6: Thinking FlowAdapters Converts Synchronous Data to Asynchronous

They only **wrap and translate protocol signals**. Use schedulers, executors, asynchronous I/O, or proper source design when you actually need to change execution behavior.

## 10. Guide to Choosing an Integration Approach

| Input / Requirement | Preferred Solution | Reason |
| --- | --- | --- |
| JDK Flow.Publisher → Flux in a Reactor app | JdkFlowAdapter.flowPublisherToFlux | Directly returns Flux to use operators |
| Flux or Mono → API expecting Flow.Publisher | JdkFlowAdapter.publisherToFlowPublisher | Keeps the reactive source, exposes JDK interface |
| Flow.Publisher → library accepting Reactive Streams Publisher, no Reactor needed | FlowAdapters.toPublisher | Keeps the API boundary pure Reactive Streams |
| Reactive Streams Publisher → JDK Flow.Publisher | FlowAdapters.toFlowPublisher | Avoids casting |
| Integrating Flow.Subscriber or Flow.Processor | FlowAdapters.toSubscriber/toFlowSubscriber or toProcessor/toFlowProcessor | Adapter supports both directions for Subscriber/Processor |
| Flow source entering Spring WebFlux | Convert to Flux in service or controller | Returns a Publisher suited to WebFlux's HTTP lifecycle |

Inspect the dependency tree to avoid multiple incompatible versions of Reactive Streams or adapters in the same application. In Spring Boot, prefer the Reactor and related library versions managed by dependency management unless there is a specific compatibility requirement.

## 11. Self-Check

**Question 1.** Why can't you assign Flow.Publisher<Integer> to org.reactivestreams.Publisher<Integer>?

Because they are two distinct interfaces in different packages; their subscribe APIs take different Subscriber types. They share the same model but have no inheritance relationship. Use an adapter.

**Question 2.** Do you need Reactor to use Flow.Publisher in Java 17?

No. Flow is in the JDK; you can use Flow.Subscriber and SubmissionPublisher without adding external dependencies.

**Question 3.** Does an adapter keep a WebFlux client from blocking if the underlying source performs blocking operations?

No. The adapter translates the Publisher contract; blocking operations still block on the running thread. You must choose an appropriate source or execution mechanism.

**Question 4.** If you want to return Flow.Publisher data from a service up to WebFlux, what should you do?

Convert Flow.Publisher to Flux using JdkFlowAdapter.flowPublisherToFlux and return the Flux from the handler/controller, letting WebFlux manage subscription, errors, and cancellation.

**Question 5.** Does request(3) guarantee the buffer or TCP socket reads exactly three times?

No. Demand is a protocol item count, whereas buffering, I/O, and prefetch have their own mechanisms.

## 12. Reference Materials

- Java 17 API: [java.util.concurrent.Flow](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html) and [Flow.Publisher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Publisher.html).
- Java 17 API: [SubmissionPublisher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html).
- Reactor API: [reactor.adapter.JdkFlowAdapter (Reactor 3.6)](https://docs.spring.io/projectreactor/reactor-core/docs/3.6.0/api/reactor/adapter/JdkFlowAdapter.html).
- Reactive Streams API: [org.reactivestreams.FlowAdapters (1.0.4)](https://javadoc.io/static/org.reactivestreams/reactive-streams/1.0.4/org/reactivestreams/FlowAdapters.html).
- Reactive Streams Specification for the JVM: [reactive-streams-jvm](https://github.com/reactive-streams/reactive-streams-jvm).

**Key takeaway:** **java.util.concurrent.Flow** is the JDK's representation of the protocol corresponding to Reactive Streams; **org.reactivestreams** is the independent interface set widely used across the reactive ecosystem; **FlowAdapters** and **JdkFlowAdapter** bridge the two sides; **Reactor** adds Mono/Flux and operators; **Spring WebFlux** uses those Publishers in its web processing pipeline. Converting properly at API boundaries keeps code readable and responsibilities clear for backpressure, threading, and data lifecycle.