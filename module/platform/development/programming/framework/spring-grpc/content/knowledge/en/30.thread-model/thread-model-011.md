# Shutting Down Executors Alongside the Server

## 1. Why Does Shutdown Order Matter?

In **Spring gRPC**, the server accepts RPCs, dispatches callbacks onto executors, and may hand off work to business workers, database clients, or downstream gRPC channels. When the application stops, these components have dependency relationships. If an executor is shut down before the server, an active RPC may have no threads left to run callbacks or finish sending its response. If the server stops too late, the application keeps accepting requests while dependencies and workers have already started closing.

Graceful shutdown must ensure:

- Stop accepting new RPCs.
- Give in-flight RPCs a bounded period of time to finish.
- Keep callback executors and dependencies alive during draining.
- Cancel still-hanging calls once the grace period expires.
- Close outbound channels and worker executors only after no RPCs need them anymore.
- Leave no threads, queues, or background tasks running beyond the application lifecycle.

The key principle is to close outer entry points first, then close the resources that in-flight requests depend on.

## 2. Recommended Shutdown Sequence

For a Spring gRPC service with a server, outbound channels, and executors, the typical sequence is:

1. **Drain from traffic:** mark the instance unready and wait for the load balancer or service discovery to stop sending new requests.
2. **Stop accepting RPCs:** call gRPC Server.shutdown() to begin graceful shutdown.
3. **Drain in-flight RPCs:** wait up to the configured grace period; existing calls are allowed to complete.
4. **Force if timed out:** call Server.shutdownNow() to cancel still-active calls, then wait a short interval.
5. **Close outbound channels:** only after handlers no longer need to call downstream services; wait for channels to terminate before closing the callback executor those channels use.
6. **Close business executors:** stop accepting new tasks and wait for accepted tasks to finish; if timed out, call shutdownNow and record tasks left in the queue.
7. **Verify termination:** log/emit metrics if the server, channels, or executors failed to terminate on time.

~~~mermaid
flowchart TD
    A[Mark instance not ready] --> B[Wait for traffic drain]
    B --> C[Server.shutdown]
    C --> D{In-flight RPCs drained?}
    D -->|Yes| E[Shutdown outbound channels]
    D -->|No, grace period expired| F[Server.shutdownNow]
    F --> G[Wait short forced-stop period]
    G --> E
    E --> H[Shutdown callback and worker executors]
    H --> I[Await termination / report leftovers]
~~~

The duration of each step must fit within the platform's total shutdown budget. If Kubernetes or a process supervisor only gives the application a short window before sending SIGKILL, the sum of internal grace periods must be smaller than that window and leave margin for final cleanup.

## 3. Server.shutdown and Server.shutdownNow

These two methods have different semantics:

| API | Behavior | When to Use |
| --- | --- | --- |
| Server.shutdown() | Initiates an orderly server stop; rejects new calls while giving active calls a chance to finish | First step of graceful shutdown |
| Server.awaitTermination(timeout, unit) | Waits up to the specified time for the server to terminate | Bounded draining |
| Server.shutdownNow() | Requests an immediate stop and cancels active calls | Fallback when drain times out |
| Server.isTerminated() | Indicates whether the server has finished terminating | Lifecycle verification |

shutdownNow does not guarantee that every piece of application code stops immediately. The server sends cancellation signals to calls; handlers, database operations, and background tasks must cooperatively check cancellation or enforce their own timeouts. A blocked JDBC call or a library that ignores interrupts may continue running after the RPC is cancelled.

Do not call shutdownNow immediately upon receiving SIGTERM if you want in-flight requests to finish. Nor should you wait indefinitely: one hung RPC could prevent the process from ever shutting down.

## 4. Why Must Executors Stay Alive During Draining?

The server needs its executor to dispatch listener callbacks and continue processing active RPCs. Handlers may also need business workers to finish already-accepted queries or tasks. If an executor is shut down before the server drains:

- Completion callbacks may be rejected because the executor no longer accepts tasks.
- Final responses may never be sent.
- Cancellation handlers may fail to run on time.
- Tasks already sitting in the queue may never execute.
- Final logs and metrics may fail to flush.

Therefore, call Server.shutdown first, wait for the server to finish, and only then shut down the executor serving the server. If an executor is shared across multiple components, close it only after all dependent components have stopped.

Do not confuse the gRPC callback executor with the business worker executor. They can be two separate pools with separate lifecycles. Keep the callback executor active until the server/channel has finished; the business executor must keep serving tasks still needed by draining RPCs.

## 5. Configuring Bounded Executors

Spring example creating separate callback and worker executors:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class GrpcExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor grpcServerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(128);
        executor.setThreadNamePrefix("grpc-server-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Bean
    ThreadPoolTaskExecutor grpcBusinessExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(12);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(96);
        executor.setThreadNamePrefix("grpc-business-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

The values above are illustrative only. Production pools must be sized according to CPU, database connection counts, downstream capacity, latency, and replica count. Queues must be finite so backlogs do not grow without bound; under overload, the service returns an appropriate status rather than silently dropping tasks.

Do not use CallerRunsPolicy casually on a callback executor. When the queue is full, this policy can execute business tasks on the submitting gRPC callback thread, blocking processing of other RPCs.

## 6. Creating a Server with a Spring-Managed Executor

If the application manages the Netty gRPC server directly, attach the executor to the builder:

~~~java
import io.grpc.Server;
import io.grpc.netty.NettyServerBuilder;
import java.io.IOException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class GrpcServerConfiguration {

    @Bean(destroyMethod = "")
    Server catalogGrpcServer(
            @Qualifier("grpcServerExecutor")
            ThreadPoolTaskExecutor grpcServerExecutor,
            CatalogServiceImpl catalogService) throws IOException {
        return NettyServerBuilder.forPort(9090)
                .executor(grpcServerExecutor)
                .addService(catalogService)
                .build()
                .start();
    }
}
~~~

Here destroyMethod is left empty because a lifecycle coordinator owns the server's shutdown sequence. Avoid letting multiple beans shut down the same resource in an unclear order.

If your project's Spring gRPC version creates and manages the server automatically, do not create an extra Netty server. Attach the executor and graceful shutdown via the server builder/customizer or lifecycle extension supported by that version. Property names and integration APIs can vary across versions.

## 7. A Coordinator Managing Graceful Shutdown

A single component can orchestrate both the server and executors in one place. Example using a Spring lifecycle callback:

~~~java
import jakarta.annotation.PreDestroy;
import io.grpc.Server;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Component
public final class GrpcShutdownCoordinator {

    private static final Logger log =
            LoggerFactory.getLogger(GrpcShutdownCoordinator.class);

    private final Server server;
    private final ThreadPoolTaskExecutor grpcServerExecutor;
    private final ThreadPoolTaskExecutor grpcBusinessExecutor;

    public GrpcShutdownCoordinator(
            Server server,
            @Qualifier("grpcServerExecutor")
            ThreadPoolTaskExecutor grpcServerExecutor,
            @Qualifier("grpcBusinessExecutor")
            ThreadPoolTaskExecutor grpcBusinessExecutor) {
        this.server = server;
        this.grpcServerExecutor = grpcServerExecutor;
        this.grpcBusinessExecutor = grpcBusinessExecutor;
    }

    @PreDestroy
    public void shutdown() {
        log.info("Starting graceful gRPC shutdown");
        server.shutdown();

        boolean terminated = awaitServer(25, TimeUnit.SECONDS);
        if (!terminated) {
            log.warn("gRPC server drain timed out; forcing shutdown");
            server.shutdownNow();
            terminated = awaitServer(5, TimeUnit.SECONDS);
        }

        if (!terminated) {
            log.error("gRPC server did not terminate within shutdown budget");
        }

        // Do not shut down the callback executor before the server has drained.
        shutdownExecutor("grpc-server", grpcServerExecutor, 10);
        shutdownExecutor("grpc-business", grpcBusinessExecutor, 15);
    }

    private boolean awaitServer(long timeout, TimeUnit unit) {
        try {
            return server.awaitTermination(timeout, unit);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    private void shutdownExecutor(
            String name,
            ThreadPoolTaskExecutor executor,
            long timeoutSeconds) {
        executor.shutdown();
        ThreadPoolExecutor pool = executor.getThreadPoolExecutor();
        try {
            if (!pool.awaitTermination(timeoutSeconds, TimeUnit.SECONDS)) {
                int queued = pool.shutdownNow().size();
                log.warn("{} executor forced to stop; {} queued tasks returned",
                        name, queued);
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    log.error("{} executor still has active workers", name);
                }
            }
        } catch (InterruptedException error) {
            int queued = pool.shutdownNow().size();
            log.warn("{} executor interrupted during shutdown; {} queued tasks returned",
                    name, queued);
            Thread.currentThread().interrupt();
        }
    }
}
~~~

This is a minimal coordinator example for one server and two executors. In a real system, add readiness/traffic draining and outbound channel lifecycle management; the 25/5/10/15-second timeouts must be tuned to match your platform's shutdown budget.

The example uses jakarta.annotation.PreDestroy for Spring Boot 3/Jakarta. For older Spring applications still using the Java EE namespace, import the corresponding annotation for that version. If your project manages the server via SmartLifecycle or a Spring gRPC lifecycle extension, place the same drain sequence into that lifecycle instead of adding a second hook.

Spring destroys dependent beans before the beans they depend on. A coordinator injecting the server and executors should be destroyed before those dependencies. Disabling automatic destroyMethod on Server in the example prevents two places from owning shutdown. Spring may still invoke destroy on the executors again when those beans are destroyed; calling shutdown a second time on an already-stopped executor is safe, though having one clear lifecycle owner keeps logs and timeouts centralized.

If shutdown is interrupted, the example falls back to force-stop and restores the interrupt flag. In production, you can use a time-bounded await-uninterruptibly helper so part of the budget still goes to cleaning up remaining components before restoring the interrupt flag.

## 8. Closing Outbound ManagedChannels at the Right Time

A server handler may be calling downstream services over a ManagedChannel. If the channel closes before inbound RPCs finish draining, in-flight requests may fail to call dependencies needed to complete.

Order for outbound channels:

1. Stop accepting new inbound RPCs.
2. Drain the inbound server so current handlers finish their downstream calls.
3. Call ManagedChannel.shutdown() on each channel.
4. Wait for channels to terminate within a time limit.
5. If timed out, call shutdownNow() and wait a short interval.
6. Only after the channels terminate, close the executor dedicated to channel callbacks.

Example:

~~~java
private boolean shutdownChannel(
        String name,
        ManagedChannel channel,
        long graceSeconds) {
    channel.shutdown();
    try {
        if (channel.awaitTermination(graceSeconds, TimeUnit.SECONDS)) {
            return true;
        }
        log.warn("{} channel drain timed out", name);
        channel.shutdownNow();
        return channel.awaitTermination(5, TimeUnit.SECONDS);
    } catch (InterruptedException error) {
        channel.shutdownNow();
        Thread.currentThread().interrupt();
        return false;
    }
}
~~~

If a channel shares an executor with the server, shut down the executor only after both the server and the channel have terminated. Never shut down a callback executor while a channel can still emit callbacks.

## 9. Readiness, Load Balancers, and Grace Periods

Server.shutdown() prevents the server from accepting new calls at the gRPC layer, but infrastructure in front of it still needs to know the instance is leaving traffic. In environments with service discovery or Kubernetes:

- Set readiness to false before starting to drain.
- Wait for the endpoint controller or load balancer to update and stop routing new traffic.
- Allow a small window for open connections and requests already in transit to the instance.
- Only then call Server.shutdown().

Readiness draining and gRPC graceful shutdown cover two different scopes: readiness stops new routing at the infrastructure level; Server.shutdown stops new calls at the server. Using both reduces UNAVAILABLE errors during rollouts.

The total time must fit within the platform's termination grace period:

| Phase | Example Budget |
| --- | ---: |
| Readiness propagation / load balancer drain | 5 seconds |
| Graceful RPC drain | 25 seconds |
| Force-stop and server wait | 5 seconds |
| Channel/executor cleanup | 15 seconds |
| Total | 50 seconds |

This is only an example. Leave safety margin before the platform sends SIGKILL. If the platform only grants 30 seconds, you cannot configure internal steps totaling 50 seconds.

## 10. Background Tasks and Work Detached from RPCs

Server termination does not automatically prove every task ever started by an RPC has finished. A handler might submit fire-and-forget work and return a response immediately; that task is no longer tied to the RPC lifecycle.

For work that must be guaranteed to finish:

- Track tasks using a registry or job system with its own lifecycle.
- Do not keep critical tasks only in an in-memory queue if the process can stop at any time.
- Use a durable queue or outbox when work must survive restarts.
- During shutdown, stop accepting new tasks and drain running tasks within a dedicated budget.
- Tasks must have deadlines, cancellation tokens, or dependency timeouts.
- Never wait indefinitely on a task that has no stopping mechanism.

If the business executor only serves RPCs and handlers wait for tasks to finish before closing the response, server draining will usually keep the required executor alive until calls end. If tasks outlive RPCs, give them an independent lifecycle and durability; do not rely on Server.awaitTermination to manage them.

## 11. Handling Queued Tasks During Forced Shutdown

ThreadPoolExecutor.shutdown() stops accepting new tasks while letting already-submitted tasks finish. shutdownNow() requests running tasks to stop and returns the list of unstarted tasks from the queue.

Points to note:

- shutdownNow does not guarantee a thread blocked in an external library will stop immediately.
- Tasks returned from the queue never ran; log their count and decide whether they can be dropped or must be persisted.
- Never silently discard critical business tasks.
- If a task can be retried after restart, persist it to a durable queue before acknowledging the RPC.
- If a task is merely a callback for an already-cancelled RPC, cancellation and terminal guards must prevent it from emitting a late response.

For running tasks, configure explicit timeouts on database/HTTP clients and check cancellation between steps. Interrupts only take effect on code and libraries that support interruption.

## 12. Observing Shutdown

Emit logs and metrics for each stage:

| Signal | Meaning |
| --- | --- |
| grpc.shutdown.started | Coordinator started shutdown |
| grpc.readiness.disabled | Instance removed from traffic |
| grpc.server.drain.duration | Time spent draining the server |
| grpc.server.inflight_at_shutdown | Active RPCs when draining began |
| grpc.server.force_shutdown | Number of times shutdownNow had to be used |
| grpc.channel.shutdown.duration | Time for outbound channels to terminate |
| executor.active_at_shutdown | Workers running at shutdown |
| executor.queue_at_shutdown | Tasks remaining in queue |
| executor.rejected | Tasks rejected because pool was full or stopping |
| grpc.shutdown.incomplete | Components that did not terminate within budget |

Logs should include component name, wait duration, remaining queued task count, and termination status. Never put request IDs or tenant IDs in metric labels; use logs or traces when investigating a specific request.

A successful shutdown is not merely that the process exited. You need to know whether the server drained cleanly or had to be forced, whether executors left tasks behind, and whether dependency channels terminated before the platform deadline.

## 13. Testing Graceful and Forced Shutdown

Integration tests should use a real server/channel or in-process transport depending on the goal. With transport tests, use latches to hold an RPC open and then trigger shutdown:

~~~java
CountDownLatch handlerStarted = new CountDownLatch(1);
CountDownLatch releaseHandler = new CountDownLatch(1);

// In the test service:
handlerStarted.countDown();
releaseHandler.await();
responseObserver.onNext(response);
responseObserver.onCompleted();

// In the test:
assertTrue(handlerStarted.await(2, TimeUnit.SECONDS));
server.shutdown();
assertFalse(server.awaitTermination(100, TimeUnit.MILLISECONDS));
releaseHandler.countDown();
assertTrue(server.awaitTermination(2, TimeUnit.SECONDS));
~~~

This is pseudocode for latch-coordinated testing; place awaits inside try/finally so latches are always released if an assertion fails. Never use fixed sleeps to guess when a handler has started.

Scenarios to test:

| Scenario | Expected Result |
| --- | --- |
| No active RPCs | Server terminates quickly after shutdown |
| In-flight unary RPC | RPC completes within grace period |
| Open streaming RPC | Stream is allowed to drain or cancelled when grace period expires |
| RPC hung past grace period | shutdownNow is called and cancellation reaches handler |
| Executor has running tasks | Tasks drain or are forced on timeout |
| Executor queue full | New tasks are explicitly rejected, not silently dropped |
| Outbound call in flight | Channel stays alive until inbound handler finishes |
| Readiness set to false | Instance receives no new traffic from load balancer |
| RPC-independent background task | Dedicated lifecycle drains or persists tasks per contract |
| Shutdown interrupted | Force path triggers and interrupt flag is restored |

Also check for thread leaks after the test suite. A terminated server with an executor still holding non-daemon workers can stop the test process from exiting.

## 14. Common Mistakes

1. **Shutting down the executor before the server.** Callbacks for running RPCs may have no threads left to complete.
2. **Calling shutdownNow immediately.** Valid requests are aborted even when drain time is available.
3. **Waiting on the server indefinitely.** One hung call can keep the process alive forever.
4. **Closing downstream channels before the inbound server.** Draining handlers lose dependencies they still need.
5. **Assuming server termination means all background tasks finished.** Fire-and-forget tasks have their own lifecycle.
6. **Skipping readiness/load balancer draining.** New requests can still be routed to a shutting-down instance.
7. **Not controlling the total grace period.** The platform may send SIGKILL before internal cleanup finishes.
8. **Ignoring tasks returned by shutdownNow.** Accepted work can be lost.
9. **Having multiple beans own shutdown.** Resource closing order becomes unpredictable and logs duplicate.
10. **Not testing forced shutdown and thread leaks.** Bugs only show up during real rollouts or process termination.

## 15. Applied Exercises

For a Spring gRPC service with a server, a downstream channel, and two executors:

1. Create separate callback and business executors with bounded queues.
2. Build a lifecycle coordinator to set readiness false, call Server.shutdown, and wait for draining.
3. When the grace period expires, call Server.shutdownNow and verify cancellation reaches the handler.
4. Only after the server drains, shut down the outbound ManagedChannel and wait for channel termination.
5. Shut down executors last; on timeout, call shutdownNow and log remaining queued tasks.
6. Create an RPC with a latch to prove an in-flight request is allowed to finish during the grace period.
7. Create a hung RPC to test forced shutdown.
8. Verify total shutdown duration does not exceed the runtime environment's termination grace period.
9. Collect metrics for drain duration, forced shutdowns, active workers, and queue leftovers.

**Completion criteria:** learners can explain shutdown ordering across server, channels, and executors; implement time-bounded draining; handle forced stops and leftover queued tasks; coordinate readiness with the platform termination grace period; and test both graceful and forced shutdowns.

### References

- [gRPC Java Server API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Server.html): shutdown, shutdownNow, and awaitTermination.
- [gRPC Java ManagedChannel API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannel.html): graceful shutdown of client channels.
- [Java ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/): shutdown, shutdownNow, and awaitTermination.
- [Spring ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): executor lifecycle in Spring.
- [Spring Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): destroy callbacks and bean lifecycles.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC server/client integration in Spring.
