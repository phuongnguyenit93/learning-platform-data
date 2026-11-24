# subscribe, Disposable, and Subscription Control in Reactor

## 1. The Problem: Who Starts and Who Stops a Mono/Flux Stream?

In Project Reactor, **Mono<T>** represents a stream of at most one element, while **Flux<T>** represents a stream of 0 to many elements. Creating a Mono/Flux object or chaining operators such as **map**, **filter**, and **flatMap** is usually only the step of **describing the pipeline**. With cold sources, the work inside the pipeline does not execute until a **Subscriber** subscribes. The **subscribe(...)** method triggers the subscription process and signal handling.

The issue is not just "how to run a Flux": an application must also know **who is responsible for subscribing**, **who receives errors**, **who has the authority to cancel**, and **how data demand (demand/backpressure) should be managed**. That is the focus of this lesson.

After this lesson, you will be able to:

- Explain the relationship among **Publisher**, **Subscriber**, **Subscription**, and **Disposable**.
- Distinguish **subscribe() returning a Disposable** from the **onSubscribe(Subscription)** signal.
- Use the overloads of **subscribe(...)** to handle data, errors, and completion.
- Use **dispose()** to request cancellation of an active subscription.
- Use **BaseSubscriber** to control **request(n)**, **cancel()**, and lifecycle callbacks.
- Identify when to let **Spring WebFlux** subscribe automatically instead of calling subscribe manually in application code.

## 2. Three Frequently Confused Objects

| Component | Role | Who Creates or Uses It? | Primary Operations |
| --- | --- | --- | --- |
| **Publisher** (Mono/Flux) | Provides a sequence of signals under the Reactive Streams contract | Code building the pipeline; operators composing sources | Subscribed to via **subscribe(...)** |
| **Subscription** (**org.reactivestreams.Subscription**) | The subscription link between Publisher and Subscriber, which also controls **demand** | Passed by the Publisher to **Subscriber.onSubscribe(subscription)** | **request(n)**, **cancel()** |
| **Disposable** (**reactor.core.Disposable**) | Lifecycle handle, typically used to request cancellation of a subscription from the outside | Returned by lambda-based **subscribe(...)** overloads | **dispose()**, **isDisposed()** |

**Subscription** is a Reactive Streams interface and holds the authority to **request a number of elements**. **Disposable** is a Reactor interface meaning cancel/cleanup; Disposable itself does not have **request(n)**. A subscription can be wrapped in a Disposable so external code can stop receiving data. When using **BaseSubscriber**, that Subscriber object also supports calling **request**, **cancel**, and **dispose**.

One view of the control flow:

~~~text
Application:
Flux/Mono ── subscribe(subscriber) ──> subscribe

Publisher ── onSubscribe(Subscription) ──> Subscriber
Publisher ── onNext(item) ───────────> Subscriber
Publisher ── onError(err) / onComplete() ──> Subscriber

Subscriber ── Subscription.request(n) ──> Publisher
Subscriber ── Subscription.cancel() ─────> Publisher

Application holds Disposable from subscribe(lambda)
    └── dispose() ──> requests subscription cancellation
~~~

**onSubscribe** must arrive before **onNext**, **onError**, and **onComplete**. Within a single subscription, **onError** and **onComplete** are mutually exclusive endings. **cancel/dispose** is a control operation, not an **onComplete** sent to the Subscriber. Once a subscription has already terminated normally or with an error, calling cancel afterward usually has no meaningful effect.

## 3. What Does subscribe(...) Do and When Does It Take Effect?

Example:

~~~java
Flux<Integer> numbers = Flux.range(1, 3)
    .map(number -> {
        System.out.println("map " + number);
        return number * 10;
    });

// Only builds the pipeline; no "map 1", "map 2", "map 3" yet.
numbers.subscribe(value -> System.out.println("receive " + value));
~~~

With synchronous **Flux.range** and **map**, processing runs when **subscribe** is called. Output:

~~~text
map 1
receive 10
map 2
receive 20
map 3
receive 30
~~~

Three key points:

1. **subscribe** begins a **subscription**. For a cold source, calling **subscribe** a second time typically triggers generating/emitting data again, independent of the first run. This can repeat I/O, queries, or side effects if uncontrolled.
2. **subscribe** does not necessarily block until completion. A synchronous source like **Flux.range** may finish inside the call; an asynchronous source like **Flux.interval** or I/O may return control before the first element arrives.
3. A **Mono/Flux** may be subscribed to by a **framework**, **StepVerifier**, or another operator. Application code does not always call **subscribe()** directly.

**Cold vs. hot:** for example, **Flux.range** is cold, so each subscription gets its own sequence of elements. With a hot source (such as an active event stream), a Subscriber may only receive data emitted after subscribing; subscribing does not necessarily replay the entire history.

## 4. Common subscribe Overloads

Common lambda overloads on **Flux** and **Mono** include:

~~~java
publisher.subscribe();

publisher.subscribe(value -> handleValue(value));

publisher.subscribe(
    value -> handleValue(value),
    error -> handleError(error)
);

publisher.subscribe(
    value -> handleValue(value),
    error -> handleError(error),
    () -> onCompleted()
);

publisher.subscribe(
    value -> handleValue(value),
    error -> handleError(error),
    () -> onCompleted(),
    subscription -> subscription.request(1)
);
~~~

The names **handleValue**, **handleError**, and **onCompleted** above are hypothetical method names used to explain signatures, **not a standalone Java program**. The **subscribe(value, error, complete)** form provides callbacks for elements, errors, and completion. The fourth overload adds a callback receiving **Subscription** to send requests manually.

| Form | Signals the Application Can Handle Directly | Initial Demand |
| --- | --- | --- |
| **subscribe()** | No callbacks passed | Normally requests unbounded |
| **subscribe(onNext)** | Each element | Normally unbounded |
| **subscribe(onNext, onError)** | Elements and errors | Normally unbounded |
| **subscribe(onNext, onError, onComplete)** | Elements, errors, and completion | Normally unbounded |
| **subscribe(onNext, onError, onComplete, onSubscribe)** | Adds control over Subscription from the start | **Decided by the onSubscribe callback** |

Most lambda overloads send **request(Long.MAX_VALUE)** upfront, meaning the Subscriber imposes no finite demand limit. **This is not a guarantee of efficient processing or infinite memory**: individual operators and sources may limit, adjust, or buffer data, while processing speed and system resources remain real constraints.

If you use the four-callback overload and only store the Subscription **without calling request(n)**, the Publisher may wait for demand forever and send no **onNext**. For per-element request control, **BaseSubscriber** is usually clearer and easier to maintain.

**Always handle errors at a manual subscribe boundary.** Without an **onError** callback, an asynchronous error may be routed to Reactor's default error handler/hook, making errors hard to manage or losing business context. The terminal **onError** callback only *consumes the error*; it does not turn the error into a recovery element. To recover inside the pipeline, use operators like **onErrorResume** or **onErrorReturn**.

## 5. Disposable: Obtaining a Handle to Cancel

When using lambda overloads, **subscribe(...)** returns a **Disposable**:

~~~java
Disposable disposable = Flux.interval(Duration.ofSeconds(1))
    .subscribe(
        value -> System.out.println("tick " + value),
        error -> System.err.println("interval failed: " + error)
    );

// Example: when the screen closes, the session ends,
// or the task is no longer needed:
disposable.dispose();
~~~

The above is a snippet requiring imports for **reactor.core.Disposable**, **reactor.core.publisher.Flux**, and **java.time.Duration**. **Flux.interval** emits asynchronously; in a real application, store the Disposable in the component owning the task and call dispose when its lifecycle ends. Calling dispose immediately after subscribe may prevent any ticks from arriving.

Understand **dispose()** accurately:

- It is a **cancellation request** for an active subscription, usually translated into **Subscription.cancel()** upstream.
- **dispose() does not emit onComplete** and does not turn cancellation into business success.
- Cancellation **is not guaranteed to be instantaneous**: already-emitted data, running callbacks, or sources that do not support immediate stopping may continue briefly.
- Calling dispose multiple times should be treated as a safe idempotent cleanup operation; it does not restart a subscription.
- If the source has already terminated, calling dispose does not "re-run" it and does not alter the **onComplete/onError** outcome that already occurred.
- Dropping the Disposable reference is not controlled cancellation; for long-lived or infinite sources, failing to retain the handle can allow the task to outlive its intended lifecycle.

**isDisposed()** reports the disposed state according to the Disposable object/implementation; do not treat it as the source of truth for business states like "succeeded", "failed", or "data saved". To observe termination, use Reactor signals or an appropriate business result model.

### 5.1. Choosing the Right Owner

For tasks spanning multiple callbacks in a desktop app, event listener, or background service, the component **starting the subscription** must have a place to **hold the Disposable and clean it up when no longer needed**. Example managing one active subscription:

~~~java
private Disposable active;

void start() {
    stop();
    active = Flux.interval(Duration.ofSeconds(1))
        .subscribe(
            tick -> onTick(tick),
            error -> reportError(error)
        );
}

void stop() {
    if (active != null) {
        active.dispose();
        active = null;
    }
}
~~~

This is an illustrative snippet inside a class that already defines **onTick** and **reportError**. Do not use the sketch above as a thread-safe solution: if **start/stop** can run concurrently, use synchronization or **Disposables.swap()** to replace subscriptions atomically.

Reactor provides **Disposables.composite(...)** to group multiple handles and cancel them together; **Disposables.swap()** is useful when replacing an old task with a new one (for example, a new search replacing an ongoing search). Remember: these helpers manage cancellation, not business error-handling logic or business results.

## 6. BaseSubscriber: Controlling request(n) and cancel()

Reactor's **BaseSubscriber<T>** is suited when you need to regulate the rate of incoming data yourself. Unlike lambda subscribe overloads that normally request unbounded demand, BaseSubscriber lets you declare a demand strategy via hooks:

- **hookOnSubscribe(Subscription)**: receives the subscription and sends the initial request.
- **hookOnNext(T)**: processes an element and decides whether to request more or cancel.
- **hookOnError(Throwable)**: handles terminal errors.
- **hookOnComplete()**: handles terminal completion.
- **hookOnCancel()**: reacts when the Subscriber actively cancels.
- **hookFinally(SignalType)**: performs cleanup or observes the termination reason, including completion, error, or cancellation.

Conceptual example requesting one element at a time:

~~~java
Flux.range(1, 5).subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        process(value);     // Hypothetical business method
        request(1);         // Request next element only after processing
    }

    @Override
    protected void hookOnError(Throwable error) {
        reportError(error); // Hypothetical business method
    }
});
~~~

This is a snippet; **process** and **reportError** must be defined by you. Inside the hook, **request(1)** increments demand by one element; after processing one element, calling request(1) again allows another emission. Omitting the initial request means a backpressure-compliant Publisher may send no data at all.

**request(n)** with **n > 0** requests up to n additional elements, not a guarantee that the Publisher will definitely emit n items. **request(0)** or negative numbers violate the Reactive Streams contract. Some operators such as **buffer**, **flatMap**, and **publishOn** adjust upstream request amounts; the request count observed at one point is not necessarily the same as at another.

**One BaseSubscriber should only be used for one subscription.** Do not reuse the same instance to subscribe to multiple independent sources; Reactor cancels the previous subscription if reused, to protect the sequential signal contract. Create a new Subscriber for each new subscription.

## 7. Runnable Java 17+ Example: Complete, Error, Dispose, and Bounded Request

The example below works with **reactor-core 3.8.8**, using four synchronous sources and one non-emitting source to keep output predictable. It demonstrates separating **subscribe**, **terminal** signals, **dispose**, and demand control.

Create the file structure:

~~~text
reactor-subscribe-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── SubscriptionControlDemo.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-subscribe-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.8.8</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

File **src/main/java/SubscriptionControlDemo.java**:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.Disposable;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class SubscriptionControlDemo {

    public static void main(String[] args) {
        System.out.println("=== 1. Complete ===");
        Flux.just(10, 20)
            .doOnSubscribe(s -> System.out.println("onSubscribe"))
            .subscribe(
                value -> System.out.println("onNext(" + value + ")"),
                error -> System.out.println("onError(" + error + ")"),
                () -> System.out.println("onComplete")
            );

        System.out.println("=== 2. Error ===");
        Flux.<Integer>error(new IllegalStateException("boom"))
            .doOnSubscribe(s -> System.out.println("onSubscribe"))
            .subscribe(
                value -> System.out.println("onNext(" + value + ")"),
                error -> System.out.println(
                    "onError(" + error.getMessage() + ")"
                ),
                () -> System.out.println("onComplete")
            );

        System.out.println("=== 3. Dispose ===");
        Disposable handle = Flux.<Integer>never()
            .doOnSubscribe(s -> System.out.println("onSubscribe"))
            .doOnCancel(() -> System.out.println("doOnCancel"))
            .subscribe(
                value -> System.out.println("onNext(" + value + ")"),
                error -> System.out.println("onError(" + error + ")"),
                () -> System.out.println("onComplete")
            );

        handle.dispose();

        System.out.println("=== 4. Manual demand ===");
        Flux.range(1, 5)
            .subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    System.out.println("onSubscribe");
                    request(1);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("onNext(" + value + ")");
                    if (value == 2) {
                        cancel();
                    } else {
                        request(1);
                    }
                }

                @Override
                protected void hookOnCancel() {
                    System.out.println("hookOnCancel");
                }
            });
    }
}
~~~

Run in the directory containing **pom.xml** (on a machine with JDK 17+ and Maven):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=SubscriptionControlDemo
~~~

Program stdout:

~~~text
=== 1. Complete ===
onSubscribe
onNext(10)
onNext(20)
onComplete
=== 2. Error ===
onSubscribe
onError(boom)
=== 3. Dispose ===
onSubscribe
doOnCancel
=== 4. Manual demand ===
onSubscribe
onNext(1)
onNext(2)
hookOnCancel
~~~

Breakdown of each section:

1. **Complete**: **Flux.just** emits two elements, then **onComplete**. The default lambda subscriber requests enough demand to receive them.
2. **Error**: **Flux.error** sends **onError**, without calling **onComplete**; the error callback receives **IllegalStateException("boom")**.
3. **Dispose**: **Flux.never** does not emit elements or terminal signals by itself. After subscribe returns a Disposable, **dispose()** causes cancellation and triggers **doOnCancel**; no **onComplete** appears.
4. **Manual demand**: **BaseSubscriber** requests one element at a time; upon receiving 2, it calls **cancel()**. Because **Flux.range** is synchronous and honors demand, values 3–5 are not sent to the Subscriber.

Each section uses **a separate subscription**. The program does not use sleep or time synchronization because the chosen sources are either synchronous or non-emitting, so the output above does not depend on whether a scheduler emits ticks in time.

## 8. Observing Subscriptions with Lifecycle Operators

The **doOn...** operators help log and monitor a pipeline, though they do not replace owning a Disposable:

| Operator | When Is It Invoked? | Does It See Cancel? |
| --- | --- | --- |
| **doOnSubscribe(s)** | When upstream receives a subscription | Not a callback for cancel |
| **doOnRequest(n)** | When a demand signal is requested at the observed point | No |
| **doOnNext(value)** | When an element passes through | No |
| **doOnError(error)** | When an error signal occurs | No |
| **doOnComplete()** | When a Flux completes normally | No |
| **doOnCancel(action)** | When a cancel signal passes through | **Yes** |
| **doFinally(signalType)** | When ending by complete, error, or cancel | **Yes**, with **SignalType.CANCEL** |

Example:

~~~java
Flux<Integer> source = Flux.range(1, 10)
    .doOnSubscribe(s -> log("subscribed"))
    .doOnRequest(n -> log("requested: " + n))
    .doOnCancel(() -> log("cancelled"))
    .doFinally(signal -> log("finally: " + signal));
~~~

This is a snippet (with a hypothetical **log** method). Operators at different positions may see different **request(n)** values because intermediate operators adjust demand. **doOnComplete** and **doOnError** do not replace **doOnCancel**. If you need a single cleanup point for all three termination paths, **doFinally** is usually the right choice; for resources whose lifecycle is tied to a publisher, you can also use **using/usingWhen**.

**Ordering and threading note:** many sources complete synchronously, but pipelines using I/O, schedulers, or asynchronous operators do not guarantee callbacks run on the thread that called subscribe. Do not treat **doFinally** as a synchronous waiting mechanism; any cleanup action should be safe to run in the source's actual execution context.

## 9. With Mono: Empty Completion and Cancellation Also Matter

A **Mono** can:

- **Mono.just(value)**: send one **onNext(value)** then **onComplete**.
- **Mono.empty()**: send no **onNext**, only **onComplete**.
- **Mono.error(error)**: send **onError** and no **onComplete**.
- **Mono.never()**: send neither elements nor terminal signals on its own; the owner can call **dispose()** to cancel.

For example, **Mono.fromCallable** or **Mono.defer** can defer computation until subscription time; calling subscribe twice on a cold Mono can trigger the computation twice. **Mono** does not mean "the function will always finish immediately" or "no Disposable is needed"; a Mono representing a network request can still be pending and need cancellation if its result is no longer wanted.

In Mono, **doOnSuccess(value)** receives **null** when the Mono completes empty (this is an argument to the success-observation callback, **not onNext(null)**). If you want to observe complete/error/cancel uniformly, use **doFinally**.

## 10. Spring WebFlux: Let the Framework Own Subscription at the HTTP Boundary

In a WebFlux controller, the standard approach is to **return Mono/Flux**, letting Spring WebFlux/Reactor Netty subscribe at the right time, connect results to the HTTP response, propagate cancellation when the client disconnects, and route errors through the pipeline/framework.

Example controller returning data:

~~~java
@GetMapping("/orders/{id}")
public Mono<Order> getOrder(@PathVariable String id) {
    return orderRepository.findById(id);
}
~~~

This snippet assumes **Order**, **orderRepository**, and the corresponding Spring imports exist. The framework subscribes when servicing the HTTP request. If you manually call **subscribe()** inside and return **Mono.empty()**, you risk finishing the HTTP response before the background task completes; request errors, context, and cancellation will also no longer be wired properly to that task.

Comparison:

~~~java
// Easily detaches work from the request: avoid in normal HTTP flows.
public Mono<Void> saveWrong(Order order) {
    repository.save(order).subscribe(); // Does not propagate errors, does not manage cancellation
    return Mono.empty();
}

// Caller decides when to subscribe, cancel, and handle errors.
public Mono<Void> saveCorrect(Order order) {
    return repository.save(order).then();
}
~~~

Both snippets above are illustrations inside a service with **repository**; type names must come from the real application. With **saveCorrect**, errors and cancellation remain part of the chain. If you need two sequential operations, compose them with **flatMap**, **then**, **zipWhen**, etc., rather than nesting **subscribe** inside **subscribe**.

However, **manual subscribe still has legitimate uses**: an event listener, CLI tool, UI application, component-managed background job, or an imperative boundary that must initiate the stream itself. In those cases, identify the owner, supply an error callback, retain the **Disposable** if the task can be long-lived, and clean up at lifecycle end.

**Do not use block() on the WebFlux event loop** to "wait for subscribe to finish". **block()** turns execution into a synchronous wait for the result and can stall threads handling I/O; reactive workflows should be composed with operators.

## 11. Common Mistakes and How to Investigate

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Built a Mono/Flux and nothing runs | No Subscriber; cold source has not been subscribed to | Return the pipeline to the framework or subscribe at the proper boundary |
| An I/O operation runs twice | Subscribed twice to a cold source with side effects | Subscribe only in the right place; when results must be shared, consider sharing/caching operators and their lifecycles |
| First element arrives and then the stream "stalls" | Subscriber only called request(1) and never requested more | Check demand, **hookOnNext**, and any operators altering demand |
| Screen closed yet background ticks continue | Lost the Disposable, no cleanup | Retain the handle and call **dispose()** on close/stop |
| Called dispose yet still saw one final callback | Cancel is asynchronous or an element was already in flight | Design idempotent logic; do not assume instantaneous hard stop |
| Called dispose and waited forever for onComplete | Cancel does not mean complete | Observe **doFinally(CANCEL)** or the cancel hook, not a successful terminal signal |
| Errors not handled in the right place | **subscribe()** missing an error consumer or nested subscribe | Keep errors in the pipeline with **onErrorResume**, and add an error consumer at imperative boundaries |
| Hard to distinguish "cancelled" from "completed" | Only logging doOnComplete/doOnError | Add **doOnCancel**, **doFinally**, and a correlation ID if needed |
| Reused a single BaseSubscriber | Subscriber has a single-subscription lifecycle | Create a new BaseSubscriber instance per subscription |
| Processing loses rate control | Default lambda subscribe requests unbounded demand | Use **BaseSubscriber**, backpressure operators, and appropriate concurrency limits |

To investigate a stream, answer in order: **(1) who subscribes, (2) does onSubscribe happen, (3) how much demand is requested, (4) who holds the Disposable, (5) did termination happen via onComplete, onError, or cancel, (6) is a cold source being subscribed to repeatedly?** For multi-branch pipelines, log per subscription or request ID to avoid mixing unrelated events.

## 12. Self-Check and Exercises

**Question 1.** Create **Flux.interval(Duration.ofSeconds(1))**, call subscribe, and discard the Disposable. What is the risk?  
**Hint:** a long-lived source can keep emitting even when the consumer no longer needs data; lifecycle management and cancellation are required.

**Question 2.** A **BaseSubscriber** sends **request(2)** and receives two elements. Will it definitely receive a third element?  
**Answer:** no. Without sending a new request, a backpressure-compliant source must not emit a third onNext; additionally, the source may complete early or fail.

**Question 3.** Distinguish **onComplete**, **onError**, and **dispose()**.  
**Answer:** the first two are terminal signals from upstream to the Subscriber (success/failure); the last is a cancellation request from the owner and does not generate onComplete by itself.

**Question 4.** When should you call **subscribe()** in a WebFlux controller?  
**Answer:** for response-producing pipelines, normally do not call it manually; return **Mono/Flux** so the framework owns the subscription. Subscribe manually only at a clearly designed imperative boundary with a plan for errors and cancellation.

**Extended exercise:** modify the **Manual demand** section of the example to request one element at a time up to value 5, then complete. Add **hookOnComplete()** and compare the output with cancelling at value 2. Try adding **doFinally** to observe **ON_COMPLETE** and **CANCEL**.

## 13. References

- Project Reactor — Simple Ways to Create a Flux or Mono and Subscribe to It: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Project Reactor — BaseSubscriber API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BaseSubscriber.html
- Project Reactor — Disposable API: https://projectreactor.io/docs/core/release/api/reactor/core/Disposable.html
- Reactive Streams Specification for the JVM: https://github.com/reactive-streams/reactive-streams-jvm
- Spring Framework — Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
