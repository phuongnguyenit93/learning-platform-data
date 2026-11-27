# Testing Slow Servers and Client Timeouts

A timeout bug is only thoroughly tested when both sides of the RPC are verified: **the client receives the right status when the server takes too long**, and **the server stops work or releases resources after the call is cancelled**. Checking only that the client receives DEADLINE_EXCEEDED does not prove the server stopped its queries, workers, or downstream calls.

In **Spring gRPC**, you can test this behavior with gRPC Java, JUnit, and in-process transport. A test server that intentionally waits on a latch until the client's deadline expires provides deterministic timing and avoids relying on Thread.sleep. The test then verifies the client-side status, cancellation in the server context, and task cleanup.

## 1. Test scenarios to verify

Suppose a client calls GenerateReport with a 150 ms deadline while the server waits for a completion signal that is never sent. The test must prove:

1. The server started processing the request.
2. The client terminates the call with DEADLINE_EXCEEDED.
3. The server-side context is marked cancelled.
4. The cancellation listener triggers and unblocks the waiting worker.
5. The server does not send a response after the call has been cancelled.
6. Resources are cleaned up even when completion and cancellation occur close together.

~~~mermaid
sequenceDiagram
    participant T as JUnit test
    participant C as gRPC client
    participant S as Slow test server
    T->>C: Call GenerateReport, 150 ms deadline
    C->>S: Request
    S-->>T: started latch
    Note over C,S: Server waits on release latch
    C-->>C: DEADLINE_EXCEEDED
    S->>S: Context.isCancelled() = true
    S->>S: Cancellation listener opens release latch
    S-->>T: stopped / cleanup latch
~~~

You do not need to assert that the timeout occurs at exactly 150 ms on the test clock. Schedulers, the JVM, and CI can cause observed durations to vary. Tests should assert statuses and synchronization events within a wait limit wider than the configured deadline.

## 2. Why use latches instead of Thread.sleep?

A test server using Thread.sleep(1_000) can trigger a timeout, yet test timing depends on the scheduler and does not tell the test whether the server even started processing. If the client times out before the handler runs, the test can pass falsely without exercising cancellation on the server.

Use two latches:

- **started:** the server signals that the handler received the request.
- **releaseWork:** the server awaits this latch; the cancellation listener opens it.

The test awaits started before checking the client outcome. When the deadline expires, the listener opens releaseWork, letting the handler exit its wait point and confirm the context was cancelled. This establishes a deterministic event order without guessing timings with sleep.

## 3. Building a controllable slow service

The service example below assumes Protobuf has generated ReportServiceGrpc, ReportRequest, and ReportResponse:

~~~java
import io.grpc.Context;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public final class SlowReportService
        extends ReportServiceGrpc.ReportServiceImplBase {

    final CountDownLatch started = new CountDownLatch(1);
    final CountDownLatch releaseWork = new CountDownLatch(1);
    final CountDownLatch cancelled = new CountDownLatch(1);
    final CountDownLatch stopped = new CountDownLatch(1);
    final AtomicBoolean responseSent = new AtomicBoolean(false);

    @Override
    public void generate(
            ReportRequest request,
            StreamObserver<ReportResponse> responseObserver) {

        Context rpcContext = Context.current();
        rpcContext.addListener(ignored -> {
            cancelled.countDown();
            releaseWork.countDown();
        }, Runnable::run);

        started.countDown();

        try {
            releaseWork.await();

            if (rpcContext.isCancelled()) {
                return;
            }

            responseObserver.onNext(
                ReportResponse.newBuilder()
                    .setReportId(request.getReportId())
                    .build());
            responseObserver.onCompleted();
            responseSent.set(true);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } finally {
            stopped.countDown();
        }
    }
}
~~~

The handler keeps the RPC waiting until either the test or the cancellation listener opens the latch. In the deadline-expiration scenario, the listener opens the latch, the handler checks the context, and exits without emitting a response. The responseSent flag allows the test to verify the server did not send a result after cancellation.

This is a test fixture, not a production request-handling pattern. In production, work must be wired to real database, HTTP client, Future, or producer cancellation APIs.

## 4. Testing with an in-process server and blocking stub

gRPC Java provides InProcessServerBuilder and InProcessChannelBuilder to test services without opening TCP ports. You need the test dependency matching your gRPC Java version, typically grpc-inprocess, along with JUnit 5.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Status;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.Server;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class ReportDeadlineTest {

    @Test
    void slowServerIsCancelledWhenClientDeadlineExpires()
            throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        SlowReportService service = new SlowReportService();

        Server server = InProcessServerBuilder.forName(serverName)
            .addService(service)
            .build()
            .start();

        ManagedChannel channel = InProcessChannelBuilder
            .forName(serverName)
            .build();

        ExecutorService caller = Executors.newSingleThreadExecutor();

        try {
            var stub = ReportServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(150, TimeUnit.MILLISECONDS);

            ReportRequest request = ReportRequest.newBuilder()
                .setReportId("report-17")
                .build();

            Future<ReportResponse> result =
                caller.submit(() -> stub.generate(request));

            assertTrue(
                service.started.await(2, TimeUnit.SECONDS),
                "server handler did not start");

            ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> result.get(2, TimeUnit.SECONDS));

            assertEquals(
                Status.Code.DEADLINE_EXCEEDED,
                Status.fromThrowable(failure.getCause()).getCode());

            assertTrue(
                service.cancelled.await(2, TimeUnit.SECONDS),
                "server context was not cancelled");
            assertTrue(
                service.stopped.await(2, TimeUnit.SECONDS),
                "server handler did not stop");
            assertFalse(service.responseSent.get());
        } finally {
            service.releaseWork.countDown();
            caller.shutdownNow();
            channel.shutdownNow();
            server.shutdownNow();
            caller.awaitTermination(2, TimeUnit.SECONDS);
            channel.awaitTermination(2, TimeUnit.SECONDS);
            server.awaitTermination(2, TimeUnit.SECONDS);
        }
    }
}
~~~

The blocking stub runs on a separate executor so the test thread can await the started latch while the RPC waits for a response. When the deadline expires, Future.get throws ExecutionException; the test extracts the status from the gRPC cause to verify DEADLINE_EXCEEDED.

Do not use directExecutor() for a fixture awaiting a latch inside the handler if that causes the call to run synchronously on the test thread. The handler must run independently so the deadline timer and the test can make progress.

## 5. Testing an async stub

With an async stub, the status is delivered to the onError callback. This approach fits when production code already uses callbacks:

~~~java
CountDownLatch completed = new CountDownLatch(1);
AtomicReference<Status> failureStatus = new AtomicReference<>();
AtomicBoolean responseReceived = new AtomicBoolean(false);

ReportServiceGrpc.newStub(channel)
    .withDeadlineAfter(150, TimeUnit.MILLISECONDS)
    .generate(request, new StreamObserver<ReportResponse>() {
        @Override
        public void onNext(ReportResponse response) {
            responseReceived.set(true);
        }

        @Override
        public void onError(Throwable error) {
            failureStatus.set(Status.fromThrowable(error));
            completed.countDown();
        }

        @Override
        public void onCompleted() {
            completed.countDown();
        }
    });

assertTrue(completed.await(2, TimeUnit.SECONDS));
assertNotNull(failureStatus.get());
assertEquals(
    Status.Code.DEADLINE_EXCEEDED,
    failureStatus.get().getCode());
assertFalse(responseReceived.get());
~~~

This example requires importing AtomicReference and AtomicBoolean. It focuses on the client callback; in a complete test, still keep a reference to the service fixture to verify cancelled, stopped, and server-side cleanup. Do not merely count completion callbacks, because both onCompleted and onError terminate an RPC yet carry different meanings.

## 6. Distinguishing deadline timeout from server-returned errors

A server can explicitly return a DEADLINE_EXCEEDED status, which is not the same as the client's deadline expiring. Tests need to distinguish the source of the status:

| Scenario | Client Outcome | What to Verify |
| --- | --- | --- |
| Client deadline expires before response | Usually DEADLINE_EXCEEDED | Server context is cancelled and worker stops |
| Server explicitly returns DEADLINE_EXCEEDED status | DEADLINE_EXCEEDED | Server may not have been cancelled by the client before returning the error |
| Client actively cancels | Usually CANCELLED | Server receives cancellation and cleans up |
| Server handles business error | Appropriate status such as FAILED_PRECONDITION | Do not confuse business errors with timeouts |

Therefore, asserting only the final status on the client is insufficient to prove deadline propagation. You must verify remaining time/context and cancellation signals on the server.

## 7. Testing that the server actually stops work

The latch fixture proves the handler reacts to context cancellation. For real code, test each resource adapter:

- **Executor/Future:** listener calls cancel(true) and the task terminates within the allowed bound.
- **JDBC:** query timeout or Statement.cancel() stops the query according to driver capabilities.
- **HTTP client:** request handle receives cancel and stops holding the connection.
- **Downstream gRPC:** child call receives deadline/cancellation from the parent context.
- **Streaming producer:** subscription closes, queues are released, and no further onNext calls occur.

Do not conclude the database stopped merely because the server handler returned. A driver may continue running the query on the database server even after the client thread was interrupted; observe or explicitly test the driver's behavior.

## 8. Testing deadline propagation across multiple layers

If the topology includes a gateway or proxy, in-process tests cannot verify that infrastructure's behavior. Add integration tests over the real path:

1. Client sets a short deadline and sends a request through the proxy.
2. Proxy forwards the remaining timeout to the Spring gRPC server.
3. Server records the remaining deadline when the request reaches the handler.
4. Server calls downstream and keeps the budget within the parent deadline.
5. When the client expires, verify the proxy cancels upstream and the server receives cancellation.
6. Correlate trace IDs, timestamps, and backend execution counts.

Tests through a proxy must use a real HTTP/2/gRPC configuration. A mock HTTP endpoint or raw TCP test usually cannot fully verify gRPC trailers, grpc-timeout, and stream cancellation.

## 9. Avoiding flaky timeout tests

Common mistakes that make tests flaky:

- Using Thread.sleep to simulate a slow server.
- Setting a deadline too close to JVM warmup or channel creation time.
- Not waiting to confirm the server started processing before asserting a timeout.
- Using a direct executor that makes the handler block the test thread.
- Failing to shut down channels, servers, or executors in finally.
- Checking only client status while ignoring server cancellation/cleanup.

Use latches to control server state, set deadlines short enough for fast tests yet with generous assertion wait bounds, and always clean up in finally. Do not assert exact millisecond timeout timings; assert statuses and event ordering.

## 10. Observing timeouts in production

Track by full method name and trace ID:

- Number of RPCs ending with DEADLINE_EXCEEDED.
- Server latency compared to the deadline granted by the client.
- Duration from cancellation until the worker stops.
- Number of tasks/queries/downstream calls still running after client timeout.
- Number of responses or messages attempted after cancellation.
- Cleanup duration and errors while releasing resources.

If clients frequently time out while the server keeps running long afterward, cancellation is not wired to real resources. If the server finishes quickly yet clients still time out, inspect the network, proxy, queues, or return path for responses/trailers.

## 11. Summary and self-check

Testing slow servers and client timeouts must verify both **the client-side status** and **server-side cancellation/cleanup**. Use in-process transport with latches to create deterministic scenarios; do not rely on sleep or exact timeout timestamps. Then add integration tests for databases, downstream services, proxies, and streaming to prove resources are genuinely released.

Self-check:

1. Why must the test await the started latch before verifying client timeout?
2. What does DEADLINE_EXCEEDED on the client prove, and what does it not prove?
3. Why must the server check Context.isCancelled() or a listener after the client's deadline expires?
4. When is an in-process test insufficient to verify timeouts through a proxy?
5. What additional checks are needed to prove a JDBC query or downstream call actually stopped?

A reliable timeout test must demonstrate the entire lifecycle: the client exhausts its budget, gRPC cancels the call, the server receives cancellation, work stops at a safe point, and resources are released.
