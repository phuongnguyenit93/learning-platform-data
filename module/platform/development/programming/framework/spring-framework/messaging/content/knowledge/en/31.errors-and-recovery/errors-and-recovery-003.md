# Timeout Does Not Mean the Receiver-Side Task Has Stopped

## 1. Scenario and Objectives

An application sends a report generation request to another service. The client waits at most three seconds. After three seconds, Reactor emits a TimeoutException and the application returns a timeout error to the user. However, the receiving service may already have started querying data, writing results to the database, or dispatching work to an executor. The fact that the client stopped waiting does not prove those activities stopped.

Four events must be separated:

1. **Caller timeout:** the calling side runs out of wait time and no longer wants to keep waiting for the result.
2. **Subscription cancellation:** the subscriber cancels the subscription observing the publisher.
3. **Remote stream cancellation:** cancellation is propagated over the transport/protocol to the active stream on the receiving side.
4. **Task termination:** the business code, worker, or external system actually stops the work.

These four events can follow one another, but they are not synonymous and do not always all happen. A timeout on the client can cancel the upstream subscription; RSocket can propagate that cancellation using a CANCEL frame. Even so, the receiver-side task only stops if it is still tied to the stream lifecycle and is capable of reacting to cancellation. Committed side effects are also not automatically undone.

The goal of this lesson is to understand what a timeout bounds, identify at which layer cancellation stops, design cancellable work, and handle uncertain outcomes after a timeout.

## 2. Distinguishing Timeout, Cancellation, and Task Termination

| Concept | Meaning | Does it guarantee the business task has stopped? |
| --- | --- | --- |
| Caller timeout | The caller ran out of time waiting for a result. | No. |
| Subscription cancellation | The subscriber calls cancel or an operator cancels upstream. | Only asks the publisher to stop; the publisher must cooperate with that request. |
| RSocket CANCEL | A frame canceling an active stream by stream ID. | Terminates the stream on the responder; does not automatically define how to stop a worker or roll back business state. |
| Task termination | The executing code has exited, the worker stopped, or the target system confirmed cancellation. | Yes, within the scope of the task confirmed stopped. |
| Side-effect rollback | Written data is undone via a transaction or compensating business action. | Cannot be inferred from a timeout or cancellation. |

Ask specific questions when investigating: "Did the caller expire its wait?", "Did the subscription receive cancel?", "Did the RSocket stream receive CANCEL?", "Did the worker stop?", "Did side effects commit?". A single log line saying "timeout" does not answer all of these questions.

### 2.1. Timeout Is an Observation Time Limit

A timeout usually answers the question: "How much longer will I wait for this result?". It does not necessarily answer the question: "How long is the work on the receiving service allowed to run?".

For example, a three-second timeout on the client can occur when:

- The request has not reached the receiving service due to network or queue delays.
- The service received the request but has not started processing yet.
- The service is currently processing and has no result yet.
- The service already wrote the result successfully, but the response has not reached the client.
- The response arrived, but the client or gateway could not process it in time.

On the client side, all of these situations can manifest as a timeout. Yet the actual business state differs.

### 2.2. Cancellation Is a Stop Request, Not Proof of Stopping

Reactive Streams defines Subscription.cancel() for a subscriber to ask a publisher to stop emitting data. Cancellation is a control signal flowing subscriber → publisher. It is not onComplete, not onError, and does not mean prior side effects have been erased.

A publisher must cooperate with cancellation. A timer-based publisher or reactive source can cancel upstream work. A blocking method, a CPU loop that does not check interruption, a database query without cancel support, or a task already pushed onto a queue may continue running.

Cancellation can also race with completion: a worker may finish or commit data right before receiving the cancel request. The application must determine business state using authoritative data rather than guessing from the moment the client timed out.

## 3. Types of Timeouts to Distinguish

| Timeout type | Scope | Key point |
| --- | --- | --- |
| Caller timeout | Time the calling application waits for a response. | The caller may stop waiting while the receiver continues working. |
| Reactor Mono.timeout | Wait time for the first data signal from a Mono. | Upon expiration, Mono emits TimeoutException or switches to a fallback and cancels the source subscription. |
| Reactor Flux.timeout(Duration) | Interval with no new element. | The timer applies from subscribe to the first element and resets from each previous element; this is a per-item idle timeout, not a total stream duration. |
| Transport/connection timeout | Communication, keepalive, or connection state. | An unresponsive connection does not tell for sure whether the receiver-side worker has stopped. |
| Server-side deadline | Time budget the receiving service enforces on business work itself. | Must be enforced on the receiving side and propagated to child tasks if bounding the entire processing chain. |

### 3.1. Reactor Mono.timeout

With Mono, timeout(Duration) emits TimeoutException if no data element arrives within the specified duration. The overload with a fallback switches to the fallback publisher on timeout. When timeout occurs, the operator cancels the subscription to the original source.

An important detail is where observation hooks are placed:

~~~java
Mono<Report> result = reportService.generate()
    .doFinally(signal ->
        log.info("source lifecycle: {}", signal))
    .timeout(Duration.ofSeconds(3))
    .doOnError(TimeoutException.class, error ->
        log.warn("caller timed out"))
    .doFinally(signal ->
        log.info("caller pipeline lifecycle: {}", signal));
~~~

If the source has not emitted data after three seconds:

- doFinally placed before timeout is on the source side, so it receives SignalType.CANCEL when timeout cancels the source subscription.
- doOnError placed after timeout observes TimeoutException on the caller side.
- The final doFinally at the end of the pipeline receives SignalType.ON_ERROR if the error propagates downstream.

One timeout can therefore produce **CANCEL on the source and ON_ERROR on the caller** within the same pipeline. The two hooks observe two different points.

If you add onErrorResume to return a fallback, the caller may receive the fallback result and the final pipeline completes with ON_COMPLETE. A successful fallback does not prove the original work stopped.

### 3.2. Reactor Flux.timeout Is an Idle Timeout

With Flux, timeout(Duration) measures the gap between consecutive elements: from subscribe to the first element, and then from each element to the next. If a wait interval exceeds the limit, the operator emits TimeoutException or switches to a fallback.

If the business requirement is "the entire stream must finish within 30 seconds", an idle timeout does not express that requirement accurately. Apply a separate total deadline to the stream, for example using an appropriate overall duration bound or an independent timer/deadline publisher. Name metrics and configurations clearly to distinguish idle timeout from total deadline.

### 3.3. Transport Timeouts vs. Server Deadlines

Connection keepalive/timeouts detect issues at the transport layer. They do not automatically place a deadline on queries, background tasks, or transactions inside the application.

If the server must stop work after a certain budget, the server must enforce the deadline itself. When a request traverses multiple services, each service needs to receive the remaining budget or shared deadline and apply that bound to its own work. Do not let each hop grant itself the full original timeout again, as total elapsed time can far exceed the caller's budget.

## 4. Cancellation over RSocket

RSocket carries interactions using streams with distinct IDs. The side opening a request is the **requester**, and the side receiving the request is the **responder**. One connection can carry requests in both directions.

### 4.1. The CANCEL Frame

RSocket defines the **CANCEL** frame with frame type **0x09**. The frame contains the stream ID of the request to cancel.

When the requester sends CANCEL for an active stream:

1. The stream ends on the requester.
2. The responder receives CANCEL and terminates the corresponding stream.
3. The responder should not send a response for Request-Response after receiving CANCEL.

This is protocol stream lifecycle semantics. It does not dictate that an executor, thread, database query, message queue, or external service must automatically cancel its work. The framework can propagate cancellation to the publisher returned by the handler; business code must continue wiring cancellation to the actual resources.

If the response was already sent and the stream terminated before CANCEL arrived, cancellation arrived too late to retract the response or side effects.

### 4.2. CANCEL Is Not the Same as ERROR[CANCELED]

Two messages must be distinguished:

- **CANCEL frame (0x09):** the requester asks to terminate an active stream.
- **ERROR[CANCELED] (error code 0x00000203):** the responder reports that it canceled the request. Per the protocol, the responder may already have begun processing; this notice does not guarantee there are no side effects.

The RSocket specification distinguishes ERROR[REJECTED] from ERROR[CANCELED]: REJECTED guarantees the request was not processed, whereas CANCELED does not guarantee that. Therefore, never treat every "canceled" status as safe proof to resend a write command.

### 4.3. Interaction Models and Cancellability

| Interaction | Behavior | Meaning on timeout |
| --- | --- | --- |
| Request-Response | One request, at most one response. | If the request is still active, the requester can cancel the stream with CANCEL. If the service committed before the response was delayed, the side effect remains. |
| Request-Stream | One request, a sequence of responses. | The requester can send CANCEL when it no longer needs the stream. The source publisher must cooperate to stop work. |
| Request-Channel | Both sides exchange sequences of data; each side can send COMPLETE. | COMPLETE from one side only closes that side's sending direction. CANCEL terminates the active stream. |
| Request-Fire-and-Forget | One-way message send, no response. | The stream ends per protocol once the request is sent/received; there is no active request to send CANCEL to later. Canceling an accepted job requires a separate business mechanism. |

In particular, Fire-and-Forget is often used to trigger background work. If the receiving service enqueues the job and finishes the stream, the caller cannot rely on canceling an already-finished stream to retract the job. Return a job ID via Request-Response if status tracking is needed, and design a separate route/command for cancellation requests.

### 4.4. Event Flow When the Requester Times Out

~~~text
Requester / calling application
    |
    | Mono.timeout(3 seconds) expires
    v
TimeoutException at caller
    |
    +--> timeout operator cancels source subscription
             |
             v
       RSocket requester
             |
             | If stream is still active and transport is still usable
             v
       Frame CANCEL(streamId)
             |
             v
       RSocket responder
             |
             v
       Publisher of @MessageMapping receives cancel
             |
             v
       Service / worker may receive stop request
             |
             v
       Task actually stops if implemented cancellation-aware
~~~

The path can be broken by races, connection failures, or detached subscriptions. Even if the responder receives CANCEL, the task can still keep running if the code detached it from the publisher or the underlying library does not support cancellation.

## 5. Applying This in Spring Framework and Reactor

### 5.1. Setting Timeout on the Requester

Example with RSocketRequester:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import reactor.core.publisher.Mono;

Mono<Report> report = requester.route("reports.generate")
    .data(command)
    .retrieveMono(Report.class)
    .doFinally(signal ->
        log.info("RSocket source ended: {}", signal))
    .timeout(Duration.ofSeconds(3))
    .doOnError(TimeoutException.class, error ->
        log.warn("Report request exceeded caller deadline"))
    .doFinally(signal ->
        log.info("Caller pipeline ended: {}", signal));
~~~

This is the requester's wait time limit. On timeout, the source subscription is canceled. For an active RSocket request, the client implementation may propagate cancellation using CANCEL. The application must still check job status if the result may already have been created or committed.

If using a fallback:

~~~java
Mono<ReportResult> result = requester.route("reports.generate")
    .data(command)
    .retrieveMono(ReportResult.class)
    .timeout(
        Duration.ofSeconds(3),
        Mono.just(ReportResult.pending(command.requestId()))
    );
~~~

The fallback here is only a substitute response for the caller. The pending value does not automatically create job state on the server; the server must have a mechanism to persist and look up the real state.

### 5.2. Responder Handler Keeps the Publisher Within the Request Lifecycle

A reactive handler can observe cancellation:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class ReportController {

    private final ReportService reportService;

    ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @MessageMapping("reports.generate")
    public Mono<Report> generate(@Payload GenerateReport command) {
        return reportService.generateReactive(command)
            .doOnCancel(() ->
                log.info("Requester cancelled report {}", command.requestId()))
            .doFinally(signal ->
                log.info("Report publisher ended: {}", signal));
    }
}
~~~

The handler returns the publisher for Spring to manage. When the requester cancels the stream, cancellation can propagate to the publisher and upstream operators. However, reportService.generateReactive must actually wire the publisher to cancellable work.

Avoid creating self-managed subscriptions inside the handler:

~~~java
@MessageMapping("reports.generate")
public Mono<Void> generate(@Payload GenerateReport command) {
    reportService.generateReactive(command).subscribe();
    return Mono.empty();
}
~~~

In this flawed example, the handler returns Mono.empty and the subscription created by subscribe() runs independently. The RSocket request can finish immediately while the self-subscribed work continues. Request cancellation does not automatically own that independent subscription.

### 5.3. Wiring Cancellation to a Blocking Task

If you must run a blocking API, you need a handle to request stopping and the blocking code must cooperate. Illustrative example with Future:

~~~java
Mono<Report> generateWithCancellableWorker(GenerateReport command) {
    return Mono.create(sink -> {
        Future<?> task = executor.submit(() -> {
            try {
                Report report = reportService.generateBlocking(command);
                sink.success(report);
            }
            catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                sink.error(error);
            }
            catch (Exception error) {
                sink.error(error);
            }
        });

        sink.onCancel(() -> task.cancel(true));
    });
}
~~~

When the subscription is canceled, onCancel calls Future.cancel(true), asking that the running thread receive an interrupt. This is an interruption request, not a command that forcibly kills the thread. generateBlocking must check for interruption or invoke an underlying API that supports cancellation. Do not swallow InterruptedException and keep looping as if nothing happened.

If the database library, HTTP client, or SDK provides a dedicated cancel API, wire the cancellation handle to that exact API. Close resources in finally or use appropriate resource management so cleanup runs on complete, error, and cancel alike. Do not assume an interrupt rolls back a transaction or undoes committed side effects.

## 6. When Should You Use a Job ID and a Separate Cancel Command?

If work can outlast the caller's wait time, or must exist independently of the RSocket connection, model it as a **background job**.

A common flow:

1. Client sends a create-job command using Request-Response, along with an idempotency key.
2. Server validates the request, persists the job in a durable state store, and returns a job ID.
3. Worker picks up the job and updates state QUEUED → RUNNING → SUCCEEDED or FAILED.
4. Client uses the job ID to query status and fetch results later.
5. To stop it, client sends a separate cancel-job command with the job ID.
6. Server verifies permissions, saves CANCEL_REQUESTED, and forwards the signal to the worker.
7. Worker checks for the cancellation request at safe checkpoints, stops cancellable resources, and updates to CANCELLED if stopped successfully.

Statuses you can use:

| Status | Meaning |
| --- | --- |
| QUEUED | Job received and stored, waiting for a worker. |
| RUNNING | Worker is processing. |
| CANCEL_REQUESTED | Cancellation request received; worker has not confirmed stopping yet. |
| CANCELLED | Worker stopped according to business rules. |
| SUCCEEDED | Work completed successfully. |
| FAILED | Work ended with an error. |

Do not transition straight from CANCEL_REQUESTED to CANCELLED just because the cancel endpoint returned a successful HTTP/RSocket response. That response may only confirm the server received the request. Record CANCELLED only when the worker or execution system confirms the task stopped per the business definition. If the task already committed and cannot be undone, you may need COMPLETED or COMPENSATION_REQUIRED instead of pretending the task never ran.

A Job ID is useful when:

- Work takes seconds or minutes.
- Client connections may drop mid-operation.
- Users need to view progress or download results later.
- There are multiple workers or queues.
- Auditing cancellation requests and worker stop times is required.
- Retries need to be handled after an unknown-outcome timeout.

## 7. Deadlines Must Be Enforced on the Receiving Side

If the business operation has a total time limit, pass the deadline or remaining budget to the receiving service and downstream services.

For example, the payload can include:

~~~json
{
  "requestId": "report-2026-00421",
  "deadlineEpochMillis": 1794067200000,
  "idempotencyKey": "report-2026-00421"
}
~~~

This is an illustrative structure; applications can place fields in payload or metadata depending on schema and codecs.

On the receiving side:

1. Validate the deadline and maximum allowed bound.
2. Compute remaining budget when processing begins.
3. Do not start work if the deadline has already expired.
4. Apply timeouts/deadlines to publishers, queries, HTTP calls, and sub-steps.
5. Propagate the remaining budget or shared deadline to the next service.
6. Record the exact outcome when the deadline expires: stopped, stop requested, or side effects already completed.

If using absolute timestamps across multiple machines, account for clock skew and time synchronization. Another option is passing remaining budget and subtracting elapsed time at each hop. Never grant each service the full original budget again.

A deadline is also not an automatic cancellation mechanism. The server must attach a timer to the task, request cancellation of underlying resources, and persist the actual outcome of the stop process.

## 8. Timeout Makes the Business Outcome Uncertain

Suppose a client sends a money transfer command, the service writes the transaction successfully, yet the response is delayed. The client hits its timeout and does not know whether the transaction committed.

If the client resends the command immediately, the transaction could be executed twice. Timeout only tells you the client did not receive a response within the desired time; it does not prove the request was not processed.

### 8.1. Idempotency Keys and Deduplication

For operations with side effects, generate a stable idempotency key for the same business intent. The server stores the key along with status/result consistently with the write operation:

- If the key does not exist yet, create the record and execute the business logic.
- If the key already exists and is completed, return the stored result.
- If the key is currently processing, return the in-progress status or have the caller wait per policy.
- If the key was canceled or failed, apply predefined continuation/retry rules.

The key must remain unchanged across retries of the same operation. If every retry generates a new key, deduplication loses its effect.

### 8.2. Check Status Before Retrying

After a timeout, prefer querying by request ID or job ID if the business API supports it:

- SUCCEEDED: retrieve the stored result; do not re-execute.
- RUNNING or CANCEL_REQUESTED: continue monitoring or send an intentional cancel request.
- QUEUED: wait for a worker or cancel the job per policy.
- FAILED: decide whether to retry based on error type and idempotency.
- Not found: conclude the request was never received only if the state system guarantees that; otherwise, state may simply not be synchronized yet.

Retry is only safe when the operation is idempotent or the server has durable deduplication. Use backoff and bound retry attempts to avoid overloading a slow service.

### 8.3. Do Not Confuse "Canceled" with "No Side Effects"

In RSocket, ERROR[REJECTED] guarantees the responder did not process the request. ERROR[CANCELED] indicates the responder canceled, yet may already have begun processing. A caller-side timeout does not independently establish either conclusion.

Without evidence of processing state, treat the outcome as an **unknown outcome** and query status by request ID before resending a command with side effects.

## 9. Standalone Java 17+ Example

This example uses Reactor Core to simulate two lifecycles: the response publisher timing out while a detached job on the receiver still completes. The program runs in a single JVM to illustrate the principle; it does not open a real RSocket connection.

### 9.1. Maven Configuration

Create pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>timeout-cancellation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
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

### 9.2. Program

Create src/main/java/TimeoutDoesNotStopRemoteWorkDemo.java:

~~~java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import reactor.core.publisher.Mono;

public class TimeoutDoesNotStopRemoteWorkDemo {

    public static void main(String[] args) throws InterruptedException {
        ExecutorService receiverExecutor =
            Executors.newSingleThreadExecutor();
        CountDownLatch receiverFinished = new CountDownLatch(1);

        try {
            Mono<String> request = Mono.defer(() -> {
                // Simulate receiver work detached from the request publisher.
                receiverExecutor.submit(() -> {
                    try {
                        Thread.sleep(300);
                        System.out.println(
                            "receiver: detached work completed");
                    }
                    catch (InterruptedException error) {
                        Thread.currentThread().interrupt();
                    }
                    finally {
                        receiverFinished.countDown();
                    }
                });

                // Simulate response not arriving before deadline.
                return Mono.<String>never()
                    .doFinally(signal ->
                        System.out.println(
                            "request publisher: " + signal));
            });

            String result = request
                .timeout(Duration.ofMillis(50))
                .doOnError(TimeoutException.class, error ->
                    System.out.println(
                        "caller observed: TimeoutException"))
                .onErrorResume(TimeoutException.class, error ->
                    Mono.just("timed out"))
                .block();

            System.out.println("caller result: " + result);

            if (!receiverFinished.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Receiver task did not finish in time");
            }
        }
        finally {
            receiverExecutor.shutdownNow();
        }
    }
}
~~~

Run with Java 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=TimeoutDoesNotStopRemoteWorkDemo
~~~

Stdout:

~~~text
request publisher: CANCEL
caller observed: TimeoutException
caller result: timed out
receiver: detached work completed
~~~

Explanation:

1. Mono.defer starts work in the executor and returns Mono.never to simulate a response that never arrives.
2. The 50 ms timeout expires, canceling the subscription to Mono.never. doFinally on the source receives CANCEL.
3. The caller receives TimeoutException and onErrorResume replaces the error with the result "timed out".
4. The work in the executor was submitted independently without wiring cancellation to the request publisher. It continues running and prints "receiver: detached work completed".
5. CountDownLatch only lets the program wait to observe the result; it is not a job cancellation mechanism.

This example simulates a common situation: the caller times out and the source publisher is canceled, yet the detached task keeps running. In distributed systems, the executor/queue on the receiving service may reside in another process; the caller is even less able to use a local timeout to forcibly stop that process.

## 10. Testing and Observing in Production Environments

When a request times out while CPU, queries, or jobs keep running, collect data across each layer:

1. **Correlation ID / request ID:** use one ID across caller, RSocket stream, handler, and worker.
2. **Deadline:** log initial deadline, remaining budget at each hop, and timeout timestamp.
3. **Caller:** log which layer raised the timeout, whether it was TimeoutException or a transport error, and whether the caller retried.
4. **Publisher:** place doFinally both before and after timeout to distinguish upstream CANCEL from downstream ON_ERROR.
5. **RSocket:** where possible, observe stream ID, request type, CANCEL send/receive times, and connection state.
6. **Handler:** record doOnCancel on the publisher returned by @MessageMapping.
7. **Worker:** log start time, stop-request receipt time, actual exit time, and exit reason.
8. **Side effect:** log when the transaction committed or the external request was accepted; never treat a timeout log as a rollback.
9. **Retry:** log idempotency key, attempt number, and deduplication status.

A useful test suite should cover:

- Timeout before the request reaches the responder.
- Timeout after the handler starts but before side effects.
- Timeout while a cancellation-aware worker is running.
- Timeout when a worker is detached from the publisher.
- Timeout after side effects commit but before the response returns.
- Request-Fire-and-Forget already accepted when the caller wants to cancel the job.
- Retrying with the same idempotency key after the caller lost track of the first outcome.

Use latches, barriers, or fake services to create deterministic timing points. Verify actual worker state and business data, not merely that the doOnCancel hook executed.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating TimeoutException as proof the request failed | May resend a command that already succeeded. | Query status by request ID and use an idempotency key. |
| Setting timeouts only on the client | Receiver may keep working indefinitely. | Enforce deadlines on the server and downstream services. |
| Thinking CANCEL automatically stops every thread | Blocking or detached tasks keep running. | Wire cancellation to Future, token, cancel API, or worker checkpoints. |
| Calling subscribe() inside @MessageMapping | Creates a subscription outside the request lifecycle. | Return the composed publisher so Spring manages the subscription. |
| Using Fire-and-Forget for jobs needing tracking | No response/job ID to check the outcome. | Use Request-Response to receive a job ID and dedicated routes to query/cancel. |
| Using Flux.timeout as a total deadline | Stream can still run forever if elements keep arriving on time. | Use a separate total deadline in addition to idle timeout. |
| Treating Future.cancel(true) as a forced kill | Code may ignore interruption or be inside a non-cancellable API. | Design cooperative cancellation and verify the worker actually exited. |
| Retrying immediately after a timeout | Side effects may be duplicated. | Deduplicate, query status, and retry only when safe. |
| Recording CANCELLED immediately upon receiving a cancel request | Job may still be running. | Use CANCEL_REQUESTED and record CANCELLED only after the worker confirms stopping. |
| Assuming timeout rolls back transactions | Committed data remains intact. | Use transactions/compensation per business rules. |

## 12. Key Takeaways

- Timeout limits how long the caller waits; it is not the final state of the receiver-side task.
- Reactor timeout cancels the source subscription and emits TimeoutException or switches to a fallback for the caller.
- doFinally on the source may receive CANCEL while downstream receives ON_ERROR due to TimeoutException.
- RSocket CANCEL (0x09) terminates a stream by stream ID; it does not automatically stop a detached worker or undo side effects.
- Request-Fire-and-Forget has no active response stream to cancel later; a dedicated job-cancellation mechanism is needed.
- The server must enforce deadlines, cooperate with cancellation, and report actual task status.
- For operations with side effects, timeout creates an unknown outcome; use request IDs, idempotency keys, and durable state before retrying.
- Report CANCELLED only when the worker has confirmed stopping according to the business definition.

## 13. References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): RSocketRequester, @MessageMapping, and interaction models.
- [RSocket Protocol](https://rsocket.io/about/protocol/): CANCEL frame, stream ID, REQUEST_FNF, Request-Response, Request-Stream, Request-Channel, and ERROR codes.
- [Reactor Core — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): timeout, doOnCancel, and doFinally.
- [Reactor Core — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): timeout by gap between elements.
- [Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): composing publishers, error handling, and managing cancellation.
- [Reactive Streams for the JVM](https://github.com/reactive-streams/reactive-streams-jvm): Publisher, Subscriber, Subscription, request, and cancel contracts.
