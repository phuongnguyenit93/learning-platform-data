# Shutting Down Executors Alongside the Server

## 1. Shutdown Is a Coordinated Process

In **Spring gRPC**, the server receives RPCs and dispatches listener callbacks onto an executor. Handlers may then rely on business workers, database pools, and outbound ManagedChannels to finish requests. When the Spring ApplicationContext closes, these components cannot stop arbitrarily in independent order.

If an executor stops before the server, callbacks for active RPCs may have no threads left to finish. If outbound channels close before handlers finish draining, valid requests can lose access to dependencies. If the server keeps accepting traffic while workers are already closing, callers will experience inconsistent failures.

A controlled shutdown process must:

- Stop sending new traffic to the instance.
- Stop accepting new RPCs on the gRPC server.
- Keep callback executors and required dependencies alive while active RPCs drain.
- Cancel still-hanging calls when the grace period ends.
- Close outbound channels after handlers no longer need them.
- Shut down executors in dependency order and await termination within a bounded duration.
- Record any tasks left in queues or workers that failed to stop.

The rule is **stop the sources of new work first, then stop the resources executing that work**.

## 2. Establishing Lifecycle Ownership

Before writing a shutdown hook, establish who owns each resource:

| Component | Lifecycle Owner | Coordination Needed |
| --- | --- | --- |
| Spring gRPC server | Spring gRPC auto-configuration or application-managed | Only one place invokes shutdown |
| Server callback executor | Spring bean or server factory | Stays alive until the server finishes draining |
| Business worker executor | Application configuration | Stays alive while handlers still need workers |
| Outbound ManagedChannel | Client configuration/component | Stays alive until inbound handlers finish downstream calls |
| Client callback executor | Client channel configuration | Stays alive until the channel terminates |
| Background job executor | Dedicated job subsystem | Has its own lifecycle and durability if jobs outlive RPCs |

Do not create an extra Netty server if Spring gRPC already creates and manages the server. When using auto-configuration, integrate with the lifecycle extension/customizer supported by your project version. If the application creates the server manually, disable automatic destroy callbacks on the server bean and assign shutdown to a single coordinator.

Avoid letting a Spring bean destroy method, a gRPC server factory, and a custom @PreDestroy all invoke shutdown without coordination. Multiple owners can stack timeouts, duplicate logs, or close an executor before the server has drained.

## 3. Shutdown Order and Dependencies

For an instance with a gRPC server, outbound channels, and two executors, the general sequence is:

1. **Readiness false:** inform service discovery/load balancers that the instance is no longer accepting new traffic.
2. **Traffic drain:** wait briefly for endpoint propagation and in-flight requests already en route to the instance.
3. **Server shutdown:** call Server.shutdown() to stop accepting new calls while letting existing calls finish.
4. **Server drain:** wait for the server to terminate within the grace period.
5. **Force stop:** if timed out, call Server.shutdownNow() and wait a short interval.
6. **Outbound channels:** once inbound handlers have drained, shut down the ManagedChannels they use.
7. **Executors:** close the client callback executor after client channels; close business worker and server callback executors once dependent components have stopped.
8. **Verify:** record any un-terminated components, leftover queued tasks, and total shutdown duration.

~~~mermaid
flowchart TD
    A[Mark instance not ready] --> B[Wait for routing drain]
    B --> C[Server.shutdown]
    C --> D{Server terminated?}
    D -->|No, grace period expired| E[Server.shutdownNow]
    E --> F[Wait forced-stop interval]
    D -->|Yes| G[Shutdown outbound channels]
    F --> G
    G --> H[Await channel termination]
    H --> I[Shutdown client callback executor]
    I --> J[Shutdown business and server executors]
    J --> K[Verify termination and leftovers]
~~~

The diagram assumes background jobs do not share outbound channels or the business executor after the server drains. If independent jobs exist, drain the job subsystem before closing resources those jobs still need.

## 4. Server.shutdown and shutdownNow

| API | Behavior | Place in the Sequence |
| --- | --- | --- |
| Server.shutdown() | Begins graceful shutdown, rejects new calls, and lets current calls finish | First step in stopping the server |
| Server.awaitTermination(timeout, unit) | Waits up to the specified time for the server to terminate | Bounded draining |
| Server.shutdownNow() | Requests cancellation of active calls and stops the server immediately | Fallback when grace period expires |
| Server.isTerminated() | Checks whether the server has terminated | Result verification |

shutdownNow does not forcibly halt every piece of Java code. It asks gRPC to cancel calls; services must observe cancellation and stop cancellable work. JDBC drivers, HTTP clients, or blocking libraries may keep running without matching timeouts or interruption support.

Never wait on the server indefinitely. A stream that never ends or a hung dependency can keep the process from exiting. Every await step needs a timeout smaller than the platform's shutdown budget.

## 5. Keeping Executors Alive During Draining

The server callback executor must remain active until the server has terminated. Business workers must also keep running if handlers are waiting on worker results before sending final responses.

If an executor is shut down too early:

- Callbacks can be rejected because the executor no longer accepts new tasks.
- Final responses or terminal callbacks may never be sent.
- Cancellation handlers and cleanup callbacks can be delayed.
- Already-accepted tasks sitting in the queue may never run.

Do not confuse the server callback executor with the business worker executor. They can be two distinct pools. The client callback executor for outbound channels has yet another lifecycle; close it only after the channel has terminated.

## 6. Configuring Separate Executors in Spring

Example declaring a callback executor and a business worker executor with bounded queues:

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

These numbers are illustrative only. Sizing must reflect CPU, database connection counts, downstream capacity, latency, and replica count. Finite queues keep backlogs from growing unbounded; under overload, the service must return an explicit status rather than silently dropping requests.

## 7. Creating the Server and Assigning Shutdown to One Coordinator

If the application manages the Netty gRPC server directly, attach the callback executor to the builder:

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

destroyMethod is left empty because the coordinator owns the shutdown sequence. If Spring gRPC auto-creates the server, do not use this manual server configuration; integrate the executor and shutdown into the Spring-managed server lifecycle.

## 8. Shutdown Coordinator in Spring

A coordinator can orchestrate both the server and executors. The following example uses @PreDestroy for an application managing its own server:

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
    private final ReadinessController readiness;

    public GrpcShutdownCoordinator(
            Server server,
            @Qualifier("grpcServerExecutor")
            ThreadPoolTaskExecutor grpcServerExecutor,
            @Qualifier("grpcBusinessExecutor")
            ThreadPoolTaskExecutor grpcBusinessExecutor,
            ReadinessController readiness) {
        this.server = server;
        this.grpcServerExecutor = grpcServerExecutor;
        this.grpcBusinessExecutor = grpcBusinessExecutor;
        this.readiness = readiness;
    }

    @PreDestroy
    public void shutdown() {
        log.info("Starting gRPC shutdown");
        readiness.markNotReady();
        readiness.awaitRoutingDrain(5, TimeUnit.SECONDS);

        server.shutdown();
        boolean drained = awaitServer(20, TimeUnit.SECONDS);
        if (!drained) {
            log.warn("gRPC drain timed out; forcing server shutdown");
            server.shutdownNow();
            drained = awaitServer(5, TimeUnit.SECONDS);
        }

        if (!drained) {
            log.error("gRPC server did not terminate in the shutdown budget");
        }

        shutdownExecutor("grpc-business", grpcBusinessExecutor, 10);
        shutdownExecutor("grpc-server", grpcServerExecutor, 5);
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
                log.warn("{} executor forced to stop; {} queued tasks remain",
                        name, queued);
                if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                    log.error("{} executor still has active workers", name);
                }
            }
        } catch (InterruptedException error) {
            int queued = pool.shutdownNow().size();
            log.warn("{} executor interrupted; {} queued tasks returned",
                    name, queued);
            Thread.currentThread().interrupt();
        }
    }
}
~~~

ReadinessController is an application abstraction for removing the instance from traffic and waiting for propagation; it is not a gRPC API. In this example, outbound channels are omitted from the coordinator to keep responsibilities clear; in production, shut down channels after the server drains and before the executor those channels use.

Spring destroys dependent beans before the beans they depend on. Because the coordinator injects the server, executors, and readiness controller, it can orchestrate them before those dependencies are destroyed. For Spring Boot 3, the example uses jakarta.annotation.PreDestroy; older versions may require a different annotation namespace.

If your project uses SmartLifecycle or a Spring gRPC lifecycle extension, place the procedure into the proper lifecycle owner rather than adding a second hook. Do not let Spring auto-shutdown the server concurrently with the coordinator unless intentional and clearly ordered.

## 9. Closing Outbound ManagedChannels After the Server

Handlers may need an outbound ManagedChannel to finish downstream calls. Therefore, never close the channel before the inbound server finishes draining.

Once the server has terminated:

1. Call ManagedChannel.shutdown() to stop new calls.
2. Wait within a bounded time for in-flight calls to complete.
3. If timed out, call shutdownNow().
4. Wait a short interval for channel termination.
5. Close the client callback executor after the channel if that executor is managed separately.

~~~java
import io.grpc.ManagedChannel;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;

static boolean shutdownChannel(
        String name,
        ManagedChannel channel,
        Logger log) {
    channel.shutdown();
    try {
        if (channel.awaitTermination(5, TimeUnit.SECONDS)) {
            return true;
        }
        log.warn("{} channel drain timed out", name);
        channel.shutdownNow();
        return channel.awaitTermination(3, TimeUnit.SECONDS);
    } catch (InterruptedException error) {
        channel.shutdownNow();
        Thread.currentThread().interrupt();
        return false;
    }
}
~~~

If a channel is shared with background jobs, server draining does not mean the channel has no remaining consumers. Drain the job subsystem or isolate channels with independent lifecycles. Never shut down an executor shared with another channel that is still active.

## 10. Readiness and Termination Grace Periods

Server.shutdown() stops accepting new calls at the gRPC server, but the load balancer/service discovery needs time to update endpoints. Therefore, set readiness false first, wait for traffic to drain, and only then shut down the server.

The total internal budget must be smaller than the platform's termination grace period:

| Phase | Illustrative Budget |
| --- | ---: |
| Readiness propagation | 5 seconds |
| Server graceful drain | 20 seconds |
| Server force-stop wait | 5 seconds |
| Channel and executor cleanup | 15 seconds |
| Total | 45 seconds |

If the platform only grants 30 seconds before SIGKILL, you cannot configure internal steps totaling 45 seconds. Reduce individual timeouts and reserve part of the budget for final shutdown hooks.

Readiness draining and gRPC server shutdown address two different layers: readiness prevents new routing from the infrastructure; Server.shutdown prevents new calls at the server. Using both produces fewer errors during rollouts.

## 11. Background Tasks and Work Outliving the RPC Lifecycle

Server termination does not prove every task ever created by an RPC has finished. A handler can submit a fire-and-forget task and return a response immediately; that task has its own lifecycle.

For work that must continue across restarts:

- Use a durable queue, job store, or transactional outbox.
- Acknowledge the RPC only after the work is durably persisted per contract.
- During shutdown, stop accepting new jobs and drain running jobs within a dedicated budget.
- Keep required dependencies and executors alive until the job subsystem stops.
- Do not rely on Server.awaitTermination() to manage tasks no longer tied to an RPC.

If a task only serves an RPC and the handler waits for completion before responding, server draining usually keeps the required executor alive until the call finishes. If a task outlives the RPC, treat it as an independent background job.

## 12. Handling Tasks Remaining in the Queue

ThreadPoolExecutor.shutdown() stops accepting new tasks while letting submitted tasks continue running. shutdownNow() requests interrupting running workers and returns the list of unstarted tasks from the queue.

- Record the number of tasks returned by shutdownNow().
- Decide which tasks can be dropped and which must be persisted/retried.
- Never silently drop business work that the caller already considers accepted.
- Running tasks need database/HTTP timeouts and cancellation checks between steps.
- Interrupts only stop code or libraries that support interruption.

If an executor holds a callback for an already-cancelled RPC, terminal guards must prevent the callback from sending a late response. If critical tasks must run after a restart, persist them to a durable queue before acknowledging acceptance.

## 13. Observing Shutdown

Track each phase with logs and metrics:

| Signal | Meaning |
| --- | --- |
| grpc.shutdown.started | Coordinator started shutdown |
| grpc.readiness.disabled | Instance removed from traffic |
| grpc.server.drain.duration | Time spent draining the server |
| grpc.server.inflight_at_shutdown | Active RPCs when draining started |
| grpc.server.force_shutdown | Number of times shutdownNow had to be used |
| grpc.channel.shutdown.duration | Time for outbound channels to terminate |
| executor.active_at_shutdown | Workers running at shutdown |
| executor.queue_at_shutdown | Tasks waiting in queue |
| executor.rejected | Tasks rejected because pool was full or stopping |
| grpc.shutdown.incomplete | Components that did not terminate within budget |

Logs should include component name, wait duration, remaining queued tasks, and termination status. Do not use request IDs or tenant IDs as metric labels due to high cardinality; use logs or traces when investigating a specific request.

A successful shutdown should indicate whether the server drained normally or had to be forced, whether channels terminated, and whether any workers/tasks remained in executors after the deadline.

## 14. Testing Graceful and Forced Shutdown

Integration tests should hold an RPC in flight using a latch and then initiate shutdown:

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

This is latch-coordinated pseudocode. Put releaseHandler.countDown() in a finally block so a failed assertion does not hang the test. Never use fixed sleeps to guess whether the handler has started.

Scenarios to verify:

| Scenario | Expected Result |
| --- | --- |
| No active RPCs | Server terminates promptly after shutdown |
| In-flight unary RPC | RPC finishes within grace period |
| Open streaming RPC | Stream drains or is cancelled when grace period expires |
| RPC hung past grace period | shutdownNow is called and cancellation reaches handler |
| Executor has running tasks | Tasks drain or are forced on timeout |
| Executor queue full | New tasks are explicitly rejected |
| Outbound call in flight | Channel stays alive until inbound handler finishes |
| Readiness set to false | Instance receives no new traffic from load balancer |
| RPC-independent background job | Job subsystem drains/persists per contract |
| Shutdown interrupted | Force path triggers and interrupt flag is restored |

Check for thread leaks after the test suite. A terminated server with an executor still holding non-daemon workers can still keep the process from exiting.

## 15. Common Mistakes

1. **Shutting down the executor before the server.** Callbacks for running RPCs may have no threads left to finish.
2. **Calling shutdownNow immediately.** Valid requests are aborted even though drain time is available.
3. **Waiting on the server indefinitely.** One hung call can keep the process alive forever.
4. **Closing downstream channels before the inbound server.** Draining handlers lose dependencies they need.
5. **Assuming server termination means background tasks finished.** Fire-and-forget tasks have their own lifecycle.
6. **Skipping readiness/load balancer draining.** New requests can still be routed to a shutting-down instance.
7. **Not controlling the total grace period.** The platform may send SIGKILL before cleanup finishes.
8. **Ignoring tasks returned by shutdownNow.** Accepted work can be lost.
9. **Having multiple beans own shutdown.** Resource closing order becomes unpredictable.
10. **Not testing forced shutdown and thread leaks.** Bugs appear only during real rollouts or process termination.

## 16. Applied Exercises

For a Spring gRPC service with a server, a downstream channel, and two executors:

1. Create separate callback and business executors with bounded queues.
2. Build a lifecycle coordinator to set readiness false, call Server.shutdown(), and await draining.
3. When the grace period expires, call Server.shutdownNow() and verify cancellation reaches the handler.
4. Only after the server drains, shut down the outbound ManagedChannel and await channel termination.
5. Shut down executors last; on timeout, call shutdownNow() and log remaining queued tasks.
6. Create an RPC with a latch to prove an in-flight request is allowed to finish during the graceful period.
7. Create a hung RPC to test forced shutdown.
8. Verify total shutdown duration does not exceed the runtime environment's termination grace period.
9. Collect metrics for drain duration, forced shutdowns, active workers, and queue leftovers.

**Completion criteria:** learners can explain shutdown ordering across server, channels, and executors; implement time-bounded draining; handle forced stops and leftover queued tasks; coordinate readiness with the termination grace period; and test both graceful and forced shutdowns.

### References

- [gRPC Java Server API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Server.html): shutdown, shutdownNow, and awaitTermination.
- [gRPC Java ManagedChannel API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannel.html): graceful shutdown of client channels.
- [Java ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/): shutdown, shutdownNow, and awaitTermination.
- [Spring ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): executor lifecycle in Spring.
- [Spring Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): destroy callbacks and bean lifecycles.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC server/client integration in Spring.
