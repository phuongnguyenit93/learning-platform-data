# Testing DEADLINE_EXCEEDED

In gRPC, a deadline specifies the latest point in time an RPC is allowed to continue. When the time budget runs out, the client receives the **DEADLINE_EXCEEDED** status; the server is notified that the call was cancelled and should stop any work that can still be stopped. With Spring gRPC, testing needs to verify the client-side status, server-side cancellation behavior, and resource cleanup.

A deadline covers queuing and transport exchange time, not only the execution time inside the service statements. Consequently, a method can expire before the handler even starts if the request waits in a queue or on a connection. Nor does a deadline prove no side effects occurred: the server may have already committed data right before the response reached the client.

## 1. Distinguish Deadline, Timeout, and Cancellation

- **Deadline** is an absolute point in time by which a call must finish.
- **Timeout** is usually a relative duration used to construct a deadline, such as 300 ms from the moment the RPC is prepared.
- **Cancellation** is the signal to stop a call, triggered by the caller cancelling explicitly, a deadline expiring, or a parent call being cancelled.

Common states:

| Situation | Client-Side Status | Meaning |
| --- | --- | --- |
| RPC deadline expires | DEADLINE_EXCEEDED | The call's time budget is exhausted |
| Caller explicitly cancels before deadline | CANCELLED | Caller no longer needs the result |
| Server proactively returns an overtime error via custom logic | May be DEADLINE_EXCEEDED | Must be distinguished from runtime-enforced deadlines |
| Dependency temporarily unavailable | UNAVAILABLE | Availability error, not automatically a deadline expiration |

Do not infer the cause solely from a single status if the service might return the same code itself. In a true deadline test, set a short deadline on the client and keep the server processing longer to prove the runtime cancels the call.

## 2. Configure Deadlines on Generated Stubs

Generated stubs are immutable. The withDeadlineAfter method returns a new stub with a deadline computed from the moment the method is called:

~~~java
ReportServiceGrpc.ReportServiceBlockingStub callStub =
    reportStub.withDeadlineAfter(250, TimeUnit.MILLISECONDS);

ReportResponse response = callStub.generateReport(request);
~~~

Do not discard the derived stub:

~~~java
// Wrong: the new stub is discarded, the RPC below still uses reportStub.
reportStub.withDeadlineAfter(250, TimeUnit.MILLISECONDS);
ReportResponse response = reportStub.generateReport(request);
~~~

Create the stub with a relative deadline close to when each logical RPC starts. Do not store a stub configured with withDeadlineAfter inside a Spring singleton for subsequent requests, because the deadline keeps ticking while the stub is held.

## 3. RPC Contract Used in the Example

Suppose a service generates reports and may take considerable time:

~~~proto
syntax = "proto3";

package acme.reports.v1;

option java_multiple_files = true;
option java_package = "com.acme.reports.v1";

service ReportService {
  rpc GenerateReport(GenerateReportRequest)
      returns (GenerateReportResponse);
}

message GenerateReportRequest {
  string report_id = 1;
}

message GenerateReportResponse {
  string report_id = 1;
  bytes content = 2;
}
~~~

The client waits at most 100 ms in the test, while the server intentionally delays the response by 500 ms. The test verifies the client receives DEADLINE_EXCEEDED before the server sends a result.

## 4. Build a Test Server with Observable Cancellation

For unary RPCs, gRPC Java provides ServerCallStreamObserver so the service knows when a call has been cancelled. Example test service using a scheduler to simulate slow processing:

~~~java
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

final class SlowReportService
        extends ReportServiceGrpc.ReportServiceImplBase {

    private final ScheduledExecutorService scheduler;
    private final long responseDelayMillis;
    final CountDownLatch handlerStarted = new CountDownLatch(1);
    final CountDownLatch cancellationObserved = new CountDownLatch(1);
    final AtomicInteger responseExecutions = new AtomicInteger();

    SlowReportService(
            ScheduledExecutorService scheduler,
            long responseDelayMillis) {
        this.scheduler = scheduler;
        this.responseDelayMillis = responseDelayMillis;
    }

    @Override
    public void generateReport(
            GenerateReportRequest request,
            StreamObserver<GenerateReportResponse> responseObserver) {

        ServerCallStreamObserver<GenerateReportResponse> serverObserver =
            (ServerCallStreamObserver<GenerateReportResponse>)
                responseObserver;

        handlerStarted.countDown();

        ScheduledFuture<?> task = scheduler.schedule(() -> {
            if (serverObserver.isCancelled()) {
                return;
            }

            responseExecutions.incrementAndGet();
            responseObserver.onNext(
                GenerateReportResponse.newBuilder()
                    .setReportId(request.getReportId())
                    .build());
            responseObserver.onCompleted();
        }, responseDelayMillis, TimeUnit.MILLISECONDS);

        serverObserver.setOnCancelHandler(() -> {
            task.cancel(false);
            cancellationObserved.countDown();
        });
    }
}
~~~

This service is for testing only. Production applications must wire cancellation to actual work: cancelling futures, closing streams or statements where APIs support it, and checking call state before emitting a response. Do not continue writing a response after the client has cancelled the call.

Cancelling a task does not guarantee every blocking library stops immediately. Drivers or downstream calls must support interrupt/cancel; otherwise, work may continue running even after the client receives DEADLINE_EXCEEDED.

## 5. Test Deadlines Using an In-Process gRPC Server

In-process transport runs both server and client in the same JVM, making it suitable for testing deadlines, statuses, and cancellation at the gRPC layer without opening a TCP port. JUnit 5 test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ReportDeadlineTest {

    private Server server;
    private ManagedChannel channel;
    private ScheduledExecutorService scheduler;
    private SlowReportService service;
    private ReportServiceGrpc.ReportServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        scheduler = Executors.newSingleThreadScheduledExecutor();
        service = new SlowReportService(scheduler, 500);

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(service)
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = ReportServiceGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (scheduler != null) {
            scheduler.shutdownNow();
            assertTrue(scheduler.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void expiredDeadlineReturnsDeadlineExceededAndCancelsServerWork()
            throws InterruptedException {
        GenerateReportRequest request =
            GenerateReportRequest.newBuilder()
                .setReportId("report-42")
                .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.withDeadlineAfter(100, TimeUnit.MILLISECONDS)
                .generateReport(request));

        assertEquals(
            Status.Code.DEADLINE_EXCEEDED,
            error.getStatus().getCode());
        assertTrue(service.handlerStarted.await(1, TimeUnit.SECONDS));
        assertTrue(service.cancellationObserved.await(2, TimeUnit.SECONDS));
        assertEquals(0, service.responseExecutions.get());
    }

    @Test
    void sufficientDeadlineAllowsResponse() {
        GenerateReportResponse response = stub
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .generateReport(
                GenerateReportRequest.newBuilder()
                    .setReportId("report-42")
                    .build());

        assertEquals("report-42", response.getReportId());
        assertEquals(1, service.responseExecutions.get());
    }
}
~~~

The short-deadline test verifies three things: the handler started, the client received the expected status, and the server received cancellation before the task produced a response. The sufficient-deadline test proves the service is not flagged as failing merely because it runs slowly.

directExecutor() works here because the handler only schedules a task and returns; the wait happens on the separate scheduler. Do not use a direct executor for long-blocking handlers or tasks waiting on a latch on the same dispatch thread.

## 6. Parent Request Deadlines and Downstream Calls

A service may call another service while handling an RPC. The child call's budget must not exceed the remaining time of the parent request. Pick the earlier deadline between the parent deadline and the child's own budget:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

private ReportServiceGrpc.ReportServiceBlockingStub
        downstreamStub(Duration childBudget) {

    if (childBudget.isNegative() || childBudget.isZero()) {
        throw new IllegalArgumentException("childBudget must be positive");
    }

    Deadline child = Deadline.after(
        childBudget.toNanos(), TimeUnit.NANOSECONDS);
    Deadline parent = Context.current().getDeadline();

    if (parent != null && parent.isBefore(child)) {
        child = parent;
    }

    return reportStub.withDeadline(child);
}
~~~

If the parent deadline has already expired, the child call expires immediately as well; do not create a fresh budget to extend the parent request. If the parent service needs time to serialize the response or commit final work, subtract a buffer from the child budget.

When offloading work to another executor, propagate the gRPC Context using Context.wrap(...) or a context-propagating executor. If the context is lost, the task may fail to observe cancellation of the parent RPC.

## 7. Verify the Server Stops Work After Cancellation

The client receiving DEADLINE_EXCEEDED does not automatically mean the server stopped completely. A handler can keep querying the database or calling downstream services if cancellation is not wired to the work.

Tests should verify:

- The cancellation handler is invoked.
- The future or scheduled task is cancelled.
- No response is emitted after cancellation.
- Resources are released in finally blocks or completion callbacks.
- No further downstream calls start after the context is cancelled.

For JDBC, use query timeouts or cancel statements if the driver supports it. For HTTP/gRPC downstream calls, keep the call handle so it can be cancelled when the parent request ends. For streams, stop the producer and release buffers. Do not hold locks or permits after a task is cancelled.

## 8. Deadline Expiration Does Not Mean the Transaction Rolled Back

A dangerous scenario:

1. Server receives a create-payment command.
2. Database commit succeeds.
3. Response is delayed on the return path or the client hits its deadline.
4. Client receives DEADLINE_EXCEEDED and does not know whether the operation committed.

Therefore, do not automatically resend create/update commands just because a deadline expired. For operations with side effects, use an idempotency key or operation ID. Callers can query the operation status with the same key to determine the outcome rather than creating duplicate transactions.

Tests should simulate both cases: deadline expiring before side effects begin and deadline expiring after side effects committed but before the response arrived. The business outcome must have a clear query/reconciliation path.

## 9. Distinguish DEADLINE_EXCEEDED from Server-Returned Errors

A handler may proactively return Status.DEADLINE_EXCEEDED based on its own rules. To test runtime deadlines, tests must:

- Set a finite deadline on the client stub.
- Make the handler wait longer than the deadline.
- Verify the cancellation callback is invoked.
- Verify the server-side task does not emit a response.

Merely asserting the DEADLINE_EXCEEDED code does not prove the deadline runtime cancelled the call. For production diagnostics, record the remaining deadline when the handler started, processing duration, cancellation signal, and pending dependency; do not log sensitive request data.

## 10. Do Not Blindly Retry on Deadline Expiration

Retries can be helpful for transient errors, but every attempt must share the budget of the logical operation. Do not call withDeadlineAfter with the full initial timeout at the start of each attempt, or total time can exceed the caller's SLA.

Before retrying:

1. Check whether the status belongs to the retryable group per policy.
2. Check whether enough overall deadline remains for backoff and a new attempt.
3. Determine whether the operation is idempotent or carries an idempotency key.
4. Limit the number of attempts and total elapsed time.
5. Do not retry INVALID_ARGUMENT, UNAUTHENTICATED, or PERMISSION_DENIED as transient errors.

DEADLINE_EXCEEDED usually indicates the budget is exhausted; immediately retrying with a fresh budget can mask slow downstream services and amplify load. If the caller can try again, start a new logical operation per business policy and preserve idempotency.

## 11. Recommended Test Matrix

| Scenario | Client-Side Assertion | Server-Side Assertion |
| --- | --- | --- |
| Deadline shorter than processing time | DEADLINE_EXCEEDED | Cancellation received, task cancelled |
| Sufficient deadline | Success | Response emitted exactly once |
| Caller explicitly cancels before deadline | CANCELLED | Cancellation handler runs |
| Parent deadline expires during downstream call | Child call bounded by parent | No further work continues after cancellation |
| Server commits then response is delayed | Client may receive DEADLINE_EXCEEDED | Operation ID/idempotency allows querying result |
| Slow queue before handler | Deadline may expire before handling | Handler performs no work if call is already cancelled |
| Retry policy triggered | Total time does not exceed logical call budget | No duplicate side effects created |

In-process tests verify gRPC deadlines/cancellation inside the JVM. Add integration tests over Netty/TLS or a proxy if you need to test timeouts at load balancers, gateways, networks, and production-like servers.

## 12. Takeaways and Self-Check

**Testing DEADLINE_EXCEEDED** must verify that a finite deadline causes the client to receive the expected status, the server observes cancellation, and stoppable work is safely cancelled. Use a generated stub with withDeadlineAfter, an in-process server with a delayed task, and assertions on both client and server sides. Preserve parent deadlines for downstream calls, manage resources on cancellation, and use idempotency for commands with side effects.

Self-check:

1. Why does a deadline include waiting time before the handler executes?
2. How does DEADLINE_EXCEEDED differ from CANCELLED?
3. Why does asserting only the status fail to prove the server stopped working?
4. How do you bound a child call's deadline by the parent request?
5. Why can a client not conclude that a transaction rolled back upon receiving DEADLINE_EXCEEDED?
6. What must be checked before retrying a logical operation whose deadline expired?

Thorough deadline testing helps Spring gRPC bound latency, release resources after cancellation, and protect the system from runaway work or duplicate side effects after callers time out.
