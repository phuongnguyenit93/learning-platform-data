# Subscription Cancellation, Completion Signals, and Cancellation Propagation

## 1. Context and Objectives

RSocket uses the Reactive Streams model to transfer data asynchronously over the network. In Spring Framework, RSocket APIs typically work with Reactor: **Mono** represents at most one result, while **Flux** represents a sequence of 0 to many results. When an application no longer needs a running stream, it can cancel the subscription. Cancellation needs to travel from the subscriber through the operators, to the source publisher, and, for an active RSocket request, to the other side of the connection.

This lesson focuses on three concepts that must be distinguished:

- **Completion:** the publisher finishes successfully and emits the **onComplete** signal.
- **Error:** the publisher terminates due to an error and emits **onError**.
- **Cancellation:** the subscriber asks the publisher to stop emitting data via **Subscription.cancel()**.

Cancellation is not a form of completion. Both states can appear at different points in the same pipeline: an operator can cancel its upstream source and then emit onComplete to downstream.

After this lesson, you will be able to read a subscription's lifecycle, distinguish signals, observe cancellation in Reactor, explain RSocket's CANCEL frame, and implement cleanup in Spring handlers.

## 2. Subscription Lifecycle in Reactive Streams

A **Publisher** emits data; a **Subscriber** receives data. When a subscriber subscribes, the publisher invokes **onSubscribe(Subscription)** and passes a Subscription object to the subscriber. The subscriber uses that object to request data or cancel the subscription relationship.

Basic flow:

~~~text
Publisher -- onSubscribe(subscription) --> Subscriber
Subscriber -- request(n) ----------------> Subscription / Publisher
Publisher -- onNext(value) ---------------> Subscriber   (0 or more times)
Publisher -- onComplete() ----------------> Subscriber   (successful completion)
Publisher -- onError(error) --------------> Subscriber   (error termination)

Subscriber -- cancel() -------------------> Subscription / Publisher
~~~

Components and signals:

| Component / Signal | Meaning |
| --- | --- |
| **Publisher** | Data source, such as Flux or Mono. |
| **Subscriber** | Data consumer. |
| **Subscription** | Relationship between a Publisher and a Subscriber; provides request and cancel. |
| **onSubscribe** | Notifies that the subscription has been established and hands the Subscription to the subscriber. |
| **request(n)** | Requests the publisher to emit up to n more elements. n must be greater than 0. |
| **onNext(value)** | Emits a single data element. |
| **onComplete()** | Successful termination; no further elements or error signals will follow for that subscription. |
| **onError(error)** | Termination due to an error; this is also a terminal signal. |
| **cancel()** | Requests the publisher to stop emitting data and reclaim subscription resources. |

### 2.1. request(n) Is Demand Control, Not Cancellation

Reactive Streams uses backpressure so the subscriber controls how much data the publisher is allowed to send. A subscriber can call request(5), then request(3); the publisher may emit up to a total of eight elements according to the granted demand, as long as the subscription has not ended.

Having no new demand does not mean cancellation. If the subscriber has not called request for more, the publisher must wait for demand; the subscription may still be active. Conversely, cancel requests ending the data-transfer relationship, not merely pausing emission.

### 2.2. onComplete and onError Are Terminal Signals

A publisher may emit 0 or more onNext signals, then terminate with exactly one of two signals:

- **onComplete:** the sequence finishes successfully. The sequence may be empty, meaning no onNext preceded it.
- **onError:** the sequence terminates due to an error. After this signal, the publisher does not continue that sequence.

In Reactor, Mono emits at most one onNext followed by onComplete, or just onComplete if empty; if an error occurs, it emits onError. Mono<Void> typically represents an operation that only needs to signal completion without returning data.

Once the subscriber receives onComplete or onError, the subscription is considered terminated. The subscriber does not need to call cancel to reconfirm an already terminal sequence.

### 2.3. cancel Is a Request from the Subscriber

**Subscription.cancel()** is a request asking the publisher to stop emitting data and release associated resources. It is a control operation flowing subscriber → publisher, not an onComplete or onError signal pushed down to the subscriber.

Cancellation is asynchronous. The publisher may take time to notice the request and stop work. Therefore, the subscriber must accept the possibility that some previously requested onNext items still arrive while cancellation is propagating. You should not assume all work at the source stops immediately at the moment cancel is called.

Cancellation also does not undo side effects that have already been performed. If the source already wrote data to a database or called an external service, cancel does not automatically roll back those actions.

## 3. Cancellation and Completion in Reactor

Reactor implements Reactive Streams via **Flux** and **Mono**. Cancellation can originate directly from application code or from an operator deciding that upstream data is no longer needed.

Common scenarios:

- The user leaves a screen and the application calls **Disposable.dispose()** on the subscription.
- **take(n)** has received n elements and cancels the upstream source.
- **next()** takes only the first element from a Flux and cancels the remainder.
- **timeout** switches to a fallback branch after the wait expires and cancels the pending source.
- **switchMap** switches to a new inner publisher and cancels the previous inner publisher.

### 3.1. Lifecycle Observation Hooks

| Operator | When Invoked | Used For |
| --- | --- | --- |
| **doOnNext** | Whenever data arrives | Logging or inspecting elements. |
| **doOnComplete** | When the sequence completes successfully | Handling the completion case specifically. |
| **doOnError** | When the sequence terminates with an error | Logging or counting errors. |
| **doOnCancel** | When the subscription is cancelled | Reacting specifically to cancellation. |
| **doFinally** | When terminated by complete, error, or cancel | General cleanup or recording termination type. |

**doOnCancel** runs only when cancellation occurs. Its handler executes before the cancel signal continues propagating upstream.

**doFinally** receives a **SignalType** indicating the termination reason: **ON_COMPLETE**, **ON_ERROR**, or **CANCEL**. The callback is invoked after the corresponding terminal signal has been propagated downstream. Therefore, the doFinally callback is suitable for recording any termination type and performing general cleanup.

Do not rely solely on doOnComplete to release resources of a stream that can be cancelled. If the subscriber cancels the stream, doOnComplete does not run. Use doFinally or an appropriate resource-management mechanism to handle all three cases.

Example observing a cancelled source:

~~~java
Flux.range(1, 5)
    .doOnCancel(() -> log.info("Source received cancellation"))
    .doFinally(signal -> log.info("Source terminated: {}", signal))
    .take(2)
    .doOnComplete(() -> log.info("Downstream sequence completed"));
~~~

After receiving two elements, take(2) cancels the upstream subscription. The source observes cancellation, while take(2) emits onComplete to downstream because it has finished its task of taking two elements. This example demonstrates that upstream cancellation and downstream completion do not contradict each other.

### 3.2. Resource Cleanup

Place cleanup at the right spot in the pipeline:

- Use **doOnCancel** when you need an action specific to cancellation, such as recording a metric or reporting that the client left the stream.
- Use **doFinally** when cleanup must run regardless of whether the sequence completes, errors, or cancels.
- For resources created per subscription, prefer resource-lifecycle operators such as **using** or **usingWhen** instead of opening resources while assembling the pipeline and hoping a callback will always close them properly.

Cleanup callbacks should be short and must not block the signal-processing thread. If asynchronous cleanup is required, use an asynchronous resource-management mechanism instead of running a long blocking task inside doOnCancel or doFinally.

## 4. How Does RSocket Represent Cancellation on the Wire?

RSocket carries Reactive Streams interactions over a network connection. The roles in a request are **requester** (the party initiating the request) and **responder** (the party receiving the request). A single connection can carry requests in both directions; therefore, the requester is not necessarily always the client application.

### 4.1. CANCEL Frame

When the requester cancels an active RSocket request, the protocol uses the **CANCEL** frame, with frame type code **0x09** and containing the **stream ID** of the request to cancel.

- When the requester sends CANCEL, the stream is terminated on the requester.
- When the responder receives CANCEL, the corresponding stream is terminated on the responder.
- CANCEL acts on the stream with that stream ID; it does not mean closing the entire RSocket connection.

For Request-Response, the requester can cancel before receiving the response; per the specification, the responder terminates the stream and should not send a response after receiving CANCEL. For Request-Stream, the requester can cancel while receiving PAYLOADs. For Request-Channel, the requester can also cancel an active channel.

### 4.2. Distinguishing CANCEL, REQUEST_N, and COMPLETE

These three concepts serve different purposes:

| Frame / Flag | Meaning |
| --- | --- |
| **REQUEST_N (0x08)** | Grants additional credit for the responder to send the corresponding number of PAYLOADs. This is backpressure. |
| **CANCEL (0x09)** | Cancels an active request by stream ID. |
| **COMPLETE** | Signals that one direction of the stream has completed successfully. |

In the **PAYLOAD** frame, RSocket has two important flags:

- **N (Next):** the frame contains a data element, corresponding to onNext.
- **C (Complete):** signals completion, corresponding to onComplete.

Common valid combinations:

| N Flag | C Flag | Meaning |
| --- | --- | --- |
| Yes | No | Data present, stream continues. |
| No | Yes | Completion signal only, no data element attached. |
| Yes | Yes | Final PAYLOAD carrying both a data element and a completion signal. |

Thus, COMPLETE is not a separate frame in all cases: it can be represented by the C flag in a PAYLOAD. CANCEL is a dedicated frame meaning request cancellation.

### 4.3. Request-Stream and Request-Channel

**Request-Stream** sends an initial request and receives a stream of responses. The requester grants initial demand in REQUEST_STREAM, and can then send REQUEST_N to request additional elements. If the stream is no longer needed, the requester sends CANCEL.

**Request-Channel** allows both sides to send streams of data. Each direction can complete independently:

- COMPLETE from the requester means the requester will send no more input data. The responder can still continue sending responses.
- COMPLETE from the responder means the responder has finished the response direction. The requester may have already completed its sending direction or may still be sending.
- If there is no ERROR or CANCEL, the channel ends when both sides have completed.
- CANCEL from the requester terminates the stream at the responder.

Do not confuse the requester sending COMPLETE with the requester cancelling the entire channel. COMPLETE closes the requester's sending direction; CANCEL terminates the active request.

### 4.4. Cancellation Propagation Chain

For a Request-Stream in Spring, the processing flow typically proceeds as follows:

~~~text
Requester application
    |
    | Disposable.dispose() or operator cancels subscription
    v
Subscription.cancel()
    |
    v
RSocket requester sends CANCEL(streamId)
    |
    v
RSocket responder receives CANCEL
    |
    v
Subscription of the publisher inside the handler is cancelled
    |
    +--> doOnCancel(...)
    |
    +--> doFinally(SignalType.CANCEL)
    |
    v
Upstream source stops work and releases resources
~~~

This is the logical path. The actual stopping time depends on whether cancellation has reached the responder and whether the source publisher cooperates with cancellation. Data already sent or in flight may have been processed before the responder receives CANCEL.

## 5. Applying This in Spring Framework

Spring supports requesters via **RSocketRequester** and responders via **@MessageMapping** methods. The interaction model is determined from the input and output cardinality:

- Single input, multiple outputs (e.g., Flux) corresponds to Request-Stream.
- Multiple inputs (a multi-element publisher) corresponds to Request-Channel; the output can be empty, single-element, or multi-element.
- Single input, single output (e.g., Mono) corresponds to Request-Response.

### 5.1. Cancelling a Stream from the Requester Side

The example below assumes **requester** is already configured and connected:

~~~java
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

Flux<String> updates = requester.route("updates.live")
    .data("orders")
    .retrieveFlux(String.class);

Disposable subscription = updates
    .doFinally(signal ->
        System.out.println("Client stream ended: " + signal))
    .subscribe(
        value -> System.out.println("Update: " + value),
        error -> System.err.println("Stream error: " + error),
        () -> System.out.println("Stream completed")
    );

// Call when the user leaves the screen or no longer needs data:
subscription.dispose();
~~~

**retrieveFlux** returns a Flux for the stream response. **subscribe** starts consuming data and returns a Disposable. When the application calls dispose before the stream terminates on its own, Reactor cancels the subscription; for an active RSocket request, cancellation is propagated over the protocol to terminate the corresponding stream.

If the stream already completed or errored before dispose is called, the subscription is already terminal; dispose does not turn completion into cancellation.

### 5.2. Observing Cancellation in the Responder

A handler can place hooks directly on the returned publisher:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
class LiveUpdatesController {

    private final UpdateService updateService;

    LiveUpdatesController(UpdateService updateService) {
        this.updateService = updateService;
    }

    @MessageMapping("updates.live")
    public Flux<String> liveUpdates(@Payload String topic) {
        return updateService.streamFor(topic)
            .doOnCancel(() ->
                System.out.println("Requester cancelled topic: " + topic))
            .doFinally(signal ->
                System.out.println("Responder stream ended: " + signal));
    }
}
~~~

This is the handler portion in a Spring application that already has an UpdateService bean. **streamFor(topic)** must return a publisher that cooperates with cancellation. When the requester cancels the request, cancellation is propagated to the publisher returned by the handler; doOnCancel and doFinally can observe it.

Return the publisher from the handler and compose operations using operators. Avoid calling subscribe() inside the handler and returning a different publisher. A subscription manually created with subscribe() lives outside the RSocket request lifecycle; the requester cancelling the request will not automatically cancel that detached subscription. This can leave background tasks running and holding resources after the client has left the stream.

## 6. Standalone Reactor Example: take Cancels the Upstream Source

This example uses Reactor Core to demonstrate the difference between upstream cancellation and downstream completion. It does not open an RSocket connection; the mapping to the CANCEL frame is explained above.

### 6.1. Maven Configuration

Create a Maven project with **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-cancel-demo</artifactId>
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
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Java Program

Create **src/main/java/CancellationDemo.java**:

~~~java
import reactor.core.publisher.Flux;

public class CancellationDemo {

    public static void main(String[] args) {
        Flux.range(1, 5)
            .doOnCancel(() ->
                System.out.println("source: doOnCancel"))
            .doFinally(signal ->
                System.out.println("source: doFinally=" + signal))
            .take(2)
            .doOnComplete(() ->
                System.out.println("downstream: doOnComplete"))
            .subscribe(value ->
                System.out.println("onNext=" + value));
    }
}
~~~

Run with Java 17+ and Maven:

~~~bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=CancellationDemo
~~~

Stdout:

~~~text
onNext=1
onNext=2
source: doOnCancel
source: doFinally=CANCEL
downstream: doOnComplete
~~~

Order explanation:

1. **Flux.range(1, 5)** creates a source of five numbers.
2. **take(2)** only needs two elements. After the second onNext, the operator cancels the upstream source subscription.
3. **doOnCancel** on the source side observes cancellation.
4. **doFinally** on the source side receives SignalType.CANCEL.
5. **take(2)** has obtained all the data it needed so it emits onComplete to downstream; the downstream doOnComplete runs.

This output proves a pipeline can record CANCEL on the upstream source while still emitting onComplete downstream. The take operator successfully completed its own job after cancelling the source.

## 7. Common Errors and How to Handle Them

| Error | Why It Is Wrong | Correct Practice |
| --- | --- | --- |
| Using only doOnComplete for cleanup | This hook does not run when the subscription is cancelled. | Use doFinally for general cleanup or doOnCancel for cancellation-specific handling. |
| Treating cancel as onError | Cancellation is not an application error and does not emit onError merely because it was cancelled. | Record SignalType.CANCEL separately. |
| Treating cancel as onComplete | cancel is a request from the subscriber; onComplete is a successful completion result from the publisher. | Distinguish control signals from terminal signals. |
| Treating request(0) or no more requests as cancel | Lack of new demand only means the publisher has not been asked to emit more; the stream may still be open. | Call cancel when the stream is no longer needed. |
| Calling subscribe() inside a handler and dropping the subscription | Work is detached from the subscription managed by RSocket. | Return the composed publisher from the handler so cancellation propagates back to the source. |
| Assuming cancel stops everything immediately | The signal takes time to propagate; data being processed or in transit may still exist. | Write sources that cooperate with cancellation and clean up safely under races. |
| Assuming CANCEL closes the whole connection | CANCEL carries a stream ID and terminates the corresponding request. | Handle only the cancelled stream; manage the connection separately. |
| Using COMPLETE to close an entire Request-Channel | COMPLETE from one side only finishes that side's sending direction. | Wait for COMPLETE on both sides or handle ERROR/CANCEL per protocol. |
| Assuming cancel undoes side effects | Cancellation does not roll back already-executed operations. | Design idempotent operations, compensation, or transactions if business logic requires it. |

## 8. Procedure for Checking Cancellation in an Application

When investigating a stream that does not stop after the client leaves, check in order:

1. **Requester:** verify the code actually calls dispose or an operator actually cancels the subscription.
2. **Requester-side Reactor:** place doFinally to distinguish ON_COMPLETE, ON_ERROR, and CANCEL.
3. **RSocket:** identify the exact request/stream ID and verify whether the requester sent CANCEL for the active stream.
4. **Responder:** place doOnCancel and doFinally directly on the publisher returned by the handler.
5. **Upstream source:** verify whether the source responds to Subscription.cancel and releases timers, listeners, cursors, sockets, or similar resources.
6. **Detached subscriptions:** look for self-initiated subscribe() calls, Futures, or background tasks not tied to the request's publisher.
7. **Races and side effects:** identify data or work already started before cancellation arrived, and ensure cleanup does not run repeatedly and cause errors.

A useful test should cover at least three separate cases: stream completes on its own, stream emits an error, and requester actively cancels. Verify the appropriate hook is invoked for each case, and verify resources are released. Do not use a completion counter to represent cancellation.

## 9. Key Takeaways

- **request(n)** controls demand; **cancel()** asks to stop the subscription.
- **onComplete** signals successful termination; **onError** signals error termination; **cancel** is a control operation from the subscriber.
- In Reactor, **doOnCancel** is for cancellation; **doFinally** recognizes complete, error, and cancel.
- In RSocket, the requester cancels an active request with a **CANCEL (0x09)** frame bound to the stream ID.
- **REQUEST_N** is backpressure; **COMPLETE** is one-way successful completion; **CANCEL** terminates the request.
- For Request-Channel, COMPLETE from one side does not automatically close the other direction.
- For cancellation to propagate in Spring, return the publisher from the handler and avoid creating detached subscriptions.

## 10. References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, RSocketRequester, and @MessageMapping.
- [RSocket Protocol](https://rsocket.io/about/protocol/): CANCEL frame, PAYLOAD with COMPLETE/NEXT flags, Request-Stream and Request-Channel lifecycles.
- [Reactive Streams for the JVM](https://github.com/reactive-streams/reactive-streams-jvm): Publisher, Subscriber, Subscription, request, and cancel contracts.
- [Reactor Core — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): doOnCancel, doFinally, and terminal signals.
- [Reactor Core — Reference Guide](https://projectreactor.io/docs/core/release/reference/): operator usage and publisher lifecycle management.
