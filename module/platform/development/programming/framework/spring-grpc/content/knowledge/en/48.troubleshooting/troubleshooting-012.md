# Server Shutdown Causes RPC Failures

In a `SPRING_GRPC` service, the server receives RPC calls based on a Protocol Buffers contract compiled into Java code. A call can be unary, server streaming, client streaming, or bidirectional streaming. Consequently, when the Spring application stops for a new deployment, pod scaling, or process termination, shutting down the gRPC server directly affects both in-flight RPCs and newly arriving RPCs.

Failures occurring right during shutdown do not necessarily mean business logic is buggy. Usually the cause lies in when the server stops accepting requests, an insufficient drain window, long-lived streams, bean shutdown ordering, or how clients handle dropped connections. You must distinguish a controlled shutdown from an abrupt process termination, then correlate logs on both sides to find the exact break point.

## 1. What Happens When a Spring gRPC Server Shuts Down?

In a Spring application, the gRPC server is typically created and managed within the application context lifecycle or by a lifecycle component provided by the starter. When Spring receives a request to close the context, the server management component stops the server according to its policy. A stop request can originate from:

- An operator stopping the application or container.
- Kubernetes replacing a pod during a rolling update, scale-down, or reschedule.
- The process receiving a `SIGTERM` signal.
- The application closing `ApplicationContext` during tests or after a startup failure.
- A server management component being instructed to stop directly.

A safe shutdown sequence typically includes: stopping new traffic from reaching the instance, starting the gRPC server shutdown, waiting for in-flight RPCs to complete, closing resources used by handlers, and only then terminating the process. Skipping a step or setting too short a timeout can cause client errors even when handlers and business data normally work fine.

### 1.1. Graceful Shutdown vs. Forceful Shutdown

The grpc-java `io.grpc.Server` API distinguishes two ways of stopping:

| API | Behavior | Typical Impact |
|---|---|---|
| `server.shutdown()` | Initiates an orderly shutdown. The server stops accepting new RPCs; already-accepted RPCs have a chance to finish. | Short RPCs usually complete if enough drain time remains. New RPCs or RPCs arriving right during the transition may not be handled by this instance. |
| `server.shutdownNow()` | Requests immediate termination and cancels active RPCs. | Running RPCs may be cancelled or lose their connection; clients typically receive transport- or cancellation-related statuses. |
| `server.awaitTermination(...)` | Waits for the server to terminate within the specified timeout. | This is a waiting operation; it does not create a graceful shutdown policy by itself. |

`shutdown()` does not guarantee every RPC will succeed. An RPC may have already exceeded its deadline, been cancelled by the client, or not yet been received by the server before it stopped accepting new requests. If the timeout expires before the server finishes, the management layer may escalate to `shutdownNow()`, or the OS/container may forcibly kill the process.

### 1.2. Unary and Streaming Have Different Drain Characteristics

- **Unary RPCs** usually have short processing times and a single response. If the server still has enough drain time, an in-flight request can return its response normally.
- **Server streaming** may keep sending many messages after the initial request was received. The server needs time to finish the stream or send a terminal status.
- **Client streaming** and **bidirectional streaming** can stay open for long periods. They may wait for the next message from the client or maintain a continuous exchange session.

Therefore, a drain timeout suitable for unary RPCs is not necessarily suitable for streaming RPCs. For long-lived streams, define a maximum session duration, a mechanism to announce cessation of new sessions, and how clients reconnect.

## 2. Why Do RPCs Fail During Shutdown?

### 2.1. Process Killed Before RPC Completes

The container or OS sends `SIGTERM`, the application begins closing the context, yet the termination wait ends too soon. Once the grace period expires, the runtime can send a forced kill signal. Running RPCs lose their serving process before sending a response.

This scenario commonly happens during deployments or pod scaling. If logs show shutdown starting just before transport closes, inspect the actual drain time and the runtime environment's grace period.

### 2.2. Server Stopped Forcefully

The application calls `shutdownNow()` immediately upon receiving a stop signal, or cleanup code tears down the server before running RPCs finish. This is appropriate for emergency stops, not as the default choice for rolling deployments.

### 2.3. Traffic Still Routed to an Instance Leaving the Cluster

The load balancer, service discovery, or Kubernetes endpoints have not yet propagated the instance's state change. During the transition window, clients still select the shutting-down instance. New RPCs may encounter connection errors or `UNAVAILABLE`.

Marking readiness as not ready must happen early enough for the state to propagate to traffic distribution layers. Flipping readiness only at the exact moment the process has already closed its listener may not leave sufficient buffer.

### 2.4. Streaming RPCs Do Not Finish Within Drain Time

A stream can wait indefinitely if the application protocol does not bound session duration or the client does not close the send stream. When the server shuts down, the stream remains active until the grace period expires; afterward, it gets cancelled or loses transport.

For long-lived streams, establish an application-layer convention, such as notifying clients of server maintenance, stopping new stream creation, giving clients a window to move to a new connection, and closing old streams cleanly.

### 2.5. Dependent Beans Shut Down Too Early

Handlers may use databases, executors, caches, tracing exporters, or clients calling other services. If these resources close before the gRPC server finishes draining, RPCs are still running without the dependencies needed to finish. The result can be handler exceptions, `INTERNAL` responses, or other errors depending on how exceptions map to gRPC statuses.

In Spring, inspect the shutdown order of lifecycle components. The server must stop accepting RPCs and drain before resources required by handlers are destroyed. If a starter manages the gRPC server, use the lifecycle mechanisms and shutdown settings supported by your exact starter version.

### 2.6. Client Closes Channel or Retries Improperly

Errors can also originate on the client side: the client application closes `ManagedChannel` while requests are still running, reuses an already-shutdown channel, or retries an unsafe RPC. A channel should be reused across the application lifecycle and closed only after the client stops issuing new requests and waits for necessary calls to finish.

Retries also do not guarantee success. If the server already executed the business action yet the response was lost during shutdown, the client cannot tell from a transport error alone whether the operation committed. For write operations, design idempotency or use idempotency keys to avoid executing business logic twice.

## 3. Read gRPC Statuses to Narrow Down the Cause

The following statuses commonly appear when connections are impacted by shutdown:

| Status | Possible Meaning During Shutdown | Direction to Check |
|---|---|---|
| `UNAVAILABLE` | Server or transport unavailable at call time; instance may be stopping or connection closed. | Check server logs, deploy events, load balancer, endpoints, and retry policy. |
| `CANCELLED` | RPC cancelled by client, server, or transport layer. | Identify which side requested cancellation and its timing relative to shutdown. |
| `DEADLINE_EXCEEDED` | RPC deadline expired before a result returned. | Compare processing time, drain time, and client deadline. |
| `INTERNAL` | Handler or processing layer hit an internal error; possibly due to dependencies closing while RPC was running. | Inspect server-side exceptions and resource shutdown order. |
| `UNKNOWN` | Unmapped error or transport provided incomplete error info. | Correlate client/server logs by timestamp, method, and request ID. |

You cannot conclude the cause from a single status alone. During the same shutdown, different clients or call timings can observe different statuses. Use the status as a starting signal for investigation, then confirm using logs and lifecycle events.

Example of recording status on the client:

```java
try {
    GetOrderResponse response = blockingStub
            .withDeadlineAfter(3, TimeUnit.SECONDS)
            .getOrder(request);
    return response;
} catch (StatusRuntimeException ex) {
    Status status = ex.getStatus();
    log.warn("gRPC call failed: method={}, code={}, description={}",
            "GetOrder", status.getCode(), status.getDescription());
    throw ex;
}
```

The deadline in this example is illustrative. Choose a deadline based on SLA and actual method processing time. Never log sensitive data from requests or metadata solely for troubleshooting.

## 4. Diagnostic Workflow

### Step 1: Determine Whether Errors Happen Only When Instances Stop or Also During Normal Operation

Correlate error timestamps with events such as rolling updates, scale-downs, restarts, Spring context closure, or manual shutdown actions. If errors cluster around when a pod leaves the cluster, prioritize lifecycle and routing checks. If errors occur continuously while instances are healthy, broaden investigation to networking, TLS, channel configuration, and handlers.

### Step 2: Build a Unified Client and Server Timeline

Gather at least these timestamps:

1. Client starts the RPC, with method, deadline, and request/correlation ID.
2. Server receives the RPC and begins processing.
3. Process receives the stop signal or Spring starts closing the context.
4. gRPC server begins shutting down.
5. Handler completes, is cancelled, or throws an exception.
6. Transport closes and process exits.

If the server has no record of the RPC while the client logged sending it, check routing and connectivity. If the server received the request yet recorded no handler completion before process exit, check drain time and dependencies.

### Step 3: Inspect Active RPC Counts and Long-Lived Streams

Track active RPC count, per-method duration, open streams, cancellation counts, and errors by gRPC status. Use existing interceptors or instrumentation to record method, start/end timestamps, and final status. Avoid logging full payloads as they may contain sensitive data and increase logging cost.

If active RPC counts fail to drop during shutdown, look for methods or streams holding resources for a long time. Check whether handlers are waiting for the next message, waiting on unbounded I/O, holding locks, or blocking executors.

### Step 4: Inspect Deadlines and Cancellation

Every RPC needs an appropriate deadline. When a deadline expires, the client can cancel the RPC and the server receives a cancellation signal. Handlers should stop background work once an RPC is cancelled, especially for streaming RPCs or expensive tasks.

Overly short deadlines cause valid requests to fail while the system is busy draining. Overly long deadlines can hold resources past shutdown time. Set deadlines based on SLA, server processing caps, and business retryability.

### Step 5: Inspect Resource Shutdown Order

Read lifecycle logs to see when the gRPC server stops relative to database pools, executors, caches, tracing, and downstream clients. If dependencies close before handlers complete, adjust lifecycle phases or shutdown coordination so the server drains first.

### Step 6: Inspect the Deployment Environment

With container orchestrators, compare readiness propagation time, `preStop` duration if any, `terminationGracePeriodSeconds`, and the actual time the application needs to drain. Total drain plus cleanup time must fit inside the environment's grace period. If the grace period expires first, the runtime may still kill a process that is serving RPCs.

## 5. Implement Graceful Shutdown

### 5.1. Let One Component Own the gRPC Server Lifecycle

In Spring applications using a starter that manages the gRPC server, let the starter's lifecycle component handle starting and stopping the server. Check the documentation for your exact dependency version to learn how to configure wait timeouts and timeout-expiration behavior. Do not add a separate independent shutdown hook to stop the server if the starter already owns the lifecycle; two competing shutdown mechanisms make cleanup order unpredictable.

Configuring graceful shutdown for Spring Boot's embedded HTTP server does not automatically prove the gRPC server is drained as well. Verify whether the gRPC server integrates with that lifecycle in your version and verify actual behavior with an integration test.

If the application creates and owns `io.grpc.Server` directly, you can implement a basic stop sequence like this:

```java
import io.grpc.Server;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class GrpcShutdown {

    private GrpcShutdown() {
    }

    public static void stop(Server server, Duration gracePeriod) {
        server.shutdown();

        try {
            boolean terminated = server.awaitTermination(
                    gracePeriod.toMillis(), TimeUnit.MILLISECONDS);

            if (!terminated) {
                server.shutdownNow();
                if (!server.awaitTermination(5, TimeUnit.SECONDS)) {
                    // Log: server did not terminate even after the forceful shutdown phase.
                }
            }
        } catch (InterruptedException ex) {
            server.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

This snippet illustrates the grpc-java API sequence, not a universal configuration bean for every Spring gRPC starter. In real applications, invoke it from the lifecycle hook of the component owning the server. Do not call it concurrently from multiple hooks. When the thread is interrupted, the snippet requests an immediate stop and restores the interrupt flag so callers can handle the interrupted state.

Choose the wait timeout based on RPC SLAs, maximum stream duration, and the platform's grace period. If the server still has not terminated after `shutdownNow()`, log the event to investigate handlers or transports still holding resources.

### 5.2. Coordinate with Readiness and Load Balancers

When draining starts, the instance must be marked as no longer accepting new traffic. Then leave sufficient time for readiness state to propagate to service discovery or the load balancer before closing the server. How this is implemented depends on the deployment platform and the system's health-checking mechanism.

With Kubernetes, `terminationGracePeriodSeconds` sets the overall limit before the container is forcibly terminated. The value must cover any `preStop` hook execution, routing updates, RPC drain time, and final cleanup. The example below merely illustrates reserving a grace period; the application must still coordinate readiness and the gRPC lifecycle itself:

```yaml
spec:
  terminationGracePeriodSeconds: 60
```

Do not pick a number based solely on average unary RPC duration. Measure long-tail RPC durations, especially streaming, then determine a sensible bound. If a stream can live longer than the grace period, design a reconnect protocol or cap stream age.

### 5.3. Keep Dependencies Alive Until Server Drain Completes

While RPCs are running, handlers may still need access to databases, executors, caches, or other services. Shutdown order should ensure:

1. Stop accepting new requests and begin draining the gRPC server.
2. Wait for active handlers and streams to complete within the allowed timeout.
3. Close executors and dependencies used by handlers.
4. Finish application cleanup and terminate the process.

If using the Spring lifecycle, review bean phases and dependency relationships. The server should stop before resources that handlers depend on. Do not let a handler hang indefinitely during cleanup; all I/O operations and downstream calls also need timeouts.

## 6. Design Clients and RPCs to Tolerate Shutdown

### 6.1. Set a Deadline per RPC

Clients should set deadlines tailored to each method's characteristics. Deadlines keep requests from waiting forever when a server leaves the cluster or the network drops. Across multi-service call chains, propagate remaining time budget rather than granting an overly long fresh deadline at every hop.

### 6.2. Conditional Retries

Retry only recoverable errors—typically specific `UNAVAILABLE` cases—and only when the client's retry policy permits. Use bounded exponential backoff with jitter to avoid many clients hammering remaining instances simultaneously.

Before retrying, evaluate method idempotency:

- Read RPCs are generally easier to retry, though consistency and deadlines still matter.
- Write or transaction-creating RPCs may have already been executed by the server before the response was lost. Blind retries can duplicate data or execute business logic twice.
- For write operations, use idempotency keys or unique request IDs persisted and checked by the server within the same transaction boundary.

Do not retry indefinitely, do not retry every status, and do not exceed the request's overall deadline. A transport-level retry succeeding does not imply business logic executed exactly once.

### 6.3. Manage ManagedChannel Lifecycle on the Client

Clients should use long-lived channels shared across corresponding stubs rather than creating a channel per RPC. During client shutdown, first stop accepting new work, wait for critical calls to finish, and only then call `ManagedChannel.shutdown()` and await channel termination. Use `shutdownNow()` only when remaining calls must be cancelled after a defined timeout.

### 6.4. Design Streaming RPCs to Support Reconnect

For long-lived streams:

- Define an application-layer message or status informing the client that the server is draining.
- Use sequence numbers, cursors, or offsets so the client resumes from its processed position upon reconnecting.
- Cap stream lifetime and provide a mechanism for clients to open a new stream before the old one closes.
- Handle cancellation to release subscriptions, queues, executor tasks, and related resources.
- Never assume a stream will survive across a server deployment or shutdown.

If using `ServerCallStreamObserver`, the handler can register a cancellation callback to stop background work when the RPC is cancelled. The callback must be safe when running concurrently with message-sending logic and must never send further responses after the stream has ended.

## 7. Test Shutdown and Drain

An integration test should use a real server on a dynamic port and a real client rather than only mocking stubs. Design tests with latches or barriers to control when handlers are executing; avoid relying on `Thread.sleep()` because CI machine timing is unstable.

Scenarios to cover:

| Scenario | How to Test | Expected Outcome |
|---|---|---|
| Unary RPC in progress when `shutdown()` is called | Hold the handler with a latch, start shutdown, then release the handler to complete. | Already-accepted RPC completes if within the grace period. |
| New RPC sent after shutdown begins | Start shutdown then attempt to send a new RPC to that server. | Server rejects/does not accept the new RPC; client handles the error or fails over per configuration. |
| Running RPC when `shutdownNow()` is called | Hold a running handler then trigger forceful shutdown. | Call is cancelled or transport closes; handler resources are released. |
| Streaming RPC open during deploy | Keep a stream alive, emit drain signal, and observe client reconnect. | Client recognizes the old session ended and resumes from checkpoint per protocol. |
| Spring `ApplicationContext` closes | Boot context and gRPC server, close context while an RPC is active. | Lifecycle stops server per configured policy; dependencies stay alive until drain finishes. |
| Insufficient grace period | Intentionally hold the handler longer than drain time. | System transitions to timeout/forceful shutdown branch with clear logs and no infinite hang. |

In deployment environments, add rolling-update or scale-down tests under continuous traffic. Monitor rates of `UNAVAILABLE`, `CANCELLED`, `DEADLINE_EXCEEDED`, active RPC counts, and drain duration. A single successful deployment does not prove all RPC types are protected; include both unary and streaming RPCs in the test suite.

## 8. Troubleshooting Checklist

When RPCs fail right as the server shuts down, check in this order:

- [ ] Does the error coincide with `SIGTERM`, a deploy, a scale-down, or closing the Spring context?
- [ ] Do logs show the server starting graceful shutdown or stopping forcefully?
- [ ] How many RPCs and streams were still active when shutdown began?
- [ ] Does actual drain time fit within the container or platform grace period?
- [ ] Do readiness and routing stop sending new requests early enough?
- [ ] Are databases, executors, caches, and downstream clients closed before handlers?
- [ ] Does the client have deadlines, bounded retries, and proper channel lifecycle?
- [ ] Do write RPCs use idempotency to prevent duplicate processing when responses are lost?
- [ ] Do integration tests cover unary, streaming, graceful shutdown, and forceful shutdown?

Once the root cause is identified, fix the right layer: lifecycle if the server stops out of order, readiness/routing if traffic hits a leaving pod, grace period if draining lacks time, or RPC/client contracts if streams and retries lack recovery rules. After making changes, verify with logs from both sides and controlled shutdown tests to ensure RPCs are handled properly throughout the Spring gRPC service lifecycle.
