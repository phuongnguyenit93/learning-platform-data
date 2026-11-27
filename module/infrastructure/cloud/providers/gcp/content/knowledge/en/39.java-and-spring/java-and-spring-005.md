# Managing the Lifecycle of Clients, Channels, and Thread Pools

A Java/Spring application running on Google Cloud typically calls multiple services: reading secrets from Secret Manager, downloading Cloud Storage files, querying BigQuery, publishing Pub/Sub messages, and calling internal gRPC services. If every HTTP request creates a new Google Cloud client or gRPC channel, the application wastes startup time, opens extra connections, and spawns unnecessary background threads. Conversely, if a shared client is closed prematurely or a thread pool is unbounded, in-flight requests can fail, memory can grow, and shutdown can lose unfinished work.

Lifecycle management means defining **when a resource is created, who owns it, how it is shared, and when it must be stopped**. In Spring systems on GCP, these decisions directly affect latency, concurrency, cost, reliability, and recovery behavior when Cloud Run, GKE, or Compute Engine starts and terminates instances.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish Google Cloud clients, gRPC channels, stubs, executors, and network connections.
- Choose the appropriate lifetime scope: per-request, singleton bean, or per-process.
- Create shared clients using Spring Dependency Injection and close them properly on application shutdown.
- Manage gRPC `ManagedChannel`, deadlines, and shutdown ordering across stubs, clients, and executors.
- Configure bounded thread pools, queues, and task rejection policies.
- Organize the lifecycle of Pub/Sub Publishers and Subscribers, including flushing and stopping message intake.
- Design graceful shutdown tailored for Cloud Run and GKE.
- Monitor threads, queues, connections, latency, and signs of resource leaks.
- Handle overload situations using backpressure, timeouts, and concurrency limits.

## 1. Which Java Resources Have a Lifecycle?

A seemingly simple API call can traverse multiple layers:

~~~text
Spring Controller / Service
          |
          v
Google Cloud client or gRPC stub
          |
          v
Transport / ManagedChannel
          |
          +--> TLS, HTTP/2, connections, keepalive
          |
          +--> callback executor, retry executor
          |
          +--> background threads
          |
          v
Google Cloud API or internal service
~~~

Not every library shares the same structure. Some clients use gRPC and Google API Client Libraries (GAPIC/GAX), while others use HTTP/REST with their own transport. Always verify the lifecycle contract of the exact library and version you use.

| Resource | Role | Typical lifecycle |
|---|---|---|
| Google Cloud API client | Wraps APIs and transport | Shared across the application or per explicit configuration |
| ManagedChannel | Manages gRPC connections | Shared across multiple RPCs and stubs |
| gRPC stub | Interface for calling RPCs, carrying options like deadlines | Usually cheap to create and derived from a shared channel |
| ExecutorService | Runs Java tasks and callbacks | Shared, bounded, closed by its owner |
| ScheduledExecutorService | Retries, timeouts, scheduled tasks | Shared as needed and closed on shutdown |
| Pub/Sub Publisher | Batches, retries, and publishes messages | Shared per topic/configuration |
| Pub/Sub Subscriber | Streaming pull, dispatch, and message acks | Worker with an explicit start/stop lifecycle |
| HTTP connection pool | Reuses HTTP connections | Managed by the HTTP client or framework |
| ThreadLocal / MDC | Holds per-thread context | Must be cleared after tasks to prevent context leaks |

The most important distinction is **ownership**: whichever object creates a resource or is assigned lifecycle management is responsible for closing it. Code consuming a Spring-injected client must not close that client after every request.

## 2. Distinguishing Client, Channel, and Stub

### Client

A client is a high-level object providing methods to call an API. For example, `SecretManagerServiceClient` exposes operations such as accessing a secret version. A client may create transport channels and executors internally upon initialization.

Many GAPIC clients are designed for reuse and provide a `close` method to release background resources. For example, `SecretManagerServiceClient` documentation instructs calling `close` because the client can hold background threads. Never create a client inside individual business methods and forget to close it.

### gRPC ManagedChannel

`ManagedChannel` represents the gRPC communication infrastructure. It manages underlying connections and shutdown state. `ManagedChannel` is thread-safe and can serve many concurrent RPC calls.

One channel does not necessarily correspond to exactly one TCP connection: resolvers, load balancing, transport, and library settings determine the actual connection count. Do not infer connection counts solely from channel counts.

### Stub

A stub is the interface class used to invoke a specific gRPC service. Stubs are typically generated from protobuf, such as blocking, async, or future stubs.

A stub can be configured with derived methods such as `withDeadlineAfter` or `withCallCredentials`. These methods return a stub configured for the call; they do not create a new `ManagedChannel` per RPC.

~~~java
ManagedChannel channel =
    ManagedChannelBuilder.forTarget("api.example.internal:443")
        .useTransportSecurity()
        .build();

// MyServiceGrpc is generated from the application's protobuf definitions.
MyServiceGrpc.MyServiceBlockingStub stub =
    MyServiceGrpc.newBlockingStub(channel);

// Deadline applies to calls made through the derived stub.
MyServiceGrpc.MyServiceBlockingStub timedStub =
    stub.withDeadlineAfter(2, TimeUnit.SECONDS);
~~~

This example illustrates sharing a channel across multiple stubs and setting deadlines. You must import the gRPC classes, protobuf-generated message types, and configure TLS/authentication matching the real service. If a high-level library already owns the channel, do not create a duplicate channel for the same purpose.

### Rules for Choosing Lifetime Scope

- Initialize shared channels/clients at application startup or on first feature use.
- Reuse them across concurrent requests when permitted by the client's thread-safety contract.
- Keep per-request data in request objects, contexts, or derived stubs; avoid mutating shared state arbitrarily.
- Close clients/channels when the Spring context terminates or the owner is destroyed.
- Separate clients by endpoint, credentials, tenant, or quota project when those configurations actually differ.

## 3. Why Not Create a New Client per HTTP Request?

Suppose a Cloud Run API receives 300 requests/second, and every request creates a `SecretManagerServiceClient`, calls the API, and discards the object without closing it.

Consequences may include:

- Frequent transport and TLS initialization, increasing latency.
- Accumulating executors and background threads that outlive request processing.
- File descriptors and memory growing over time.
- Connection churn putting pressure on the client, server, and network.
- Unstable benchmark results when instances scale out.
- Prolonged shutdowns due to unreleased background resources.

The standard solution is creating one client for the application lifecycle, injecting it into services that need it, and letting the container close it at shutdown. However, using a singleton does not mean unlimited concurrency; you must regulate request volume to dependencies based on quotas and actual capacity.

## 4. Creating and Closing Google Cloud Clients in Spring

Spring manages lifecycles for singleton beans. On `@Bean` methods, Spring can auto-detect public `close` or `shutdown` methods, though declaring `destroyMethod` explicitly makes the intent unmistakable.

### Example: Secret Manager Singleton Client

~~~java
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GcpClientConfig {

    @Bean(destroyMethod = "close")
    SecretManagerServiceClient secretManagerClient() throws IOException {
        return SecretManagerServiceClient.create();
    }
}
~~~

This bean is created once per Spring application context under the default singleton scope. Services inject the same instance. When the Spring context closes normally, Spring invokes `close` on the bean.

Service using the client:

~~~java
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;
import org.springframework.stereotype.Service;

@Service
public class SecretReader {
    private final SecretManagerServiceClient client;

    public SecretReader(SecretManagerServiceClient client) {
        this.client = client;
    }

    public String readUtf8(String project, String secret, String version) {
        String name = SecretVersionName.of(project, secret, version).toString();
        return client.accessSecretVersion(name)
                     .getPayload()
                     .getData()
                     .toStringUtf8();
    }
}
~~~

This example demonstrates lifecycle management. The application must still control IAM, version selection, and API error handling. Do not log secrets or return plaintext secrets to unauthorized callers. If the secret payload is binary data, use `byte[]` instead of coercing to UTF-8.

**Pitfall to avoid:** never wrap an injected client in `try-with-resources` inside a method. Doing so closes the singleton after the first request, breaking subsequent requests.

### Single-Use Clients in Command-Line Utilities

For short-lived programs that own the client directly, `try-with-resources` is the right choice:

~~~java
try (SecretManagerServiceClient client =
         SecretManagerServiceClient.create()) {
    // Perform one or a few API calls.
}
// close() is invoked when exiting the block.
~~~

The difference lies in ownership: a short-lived CLI owns its client; in a Spring application, the container owns singleton beans.

### Different Libraries Close Differently

Do not apply a single `close` pattern blindly to every object. Some clients implement `AutoCloseable`, some expose `shutdown` and `awaitTermination`, and some use transport owned by a builder or another framework. Check the JavaDoc for the exact client and verify behavior when passing custom channels/transports.

For example, the BigQuery client currently exposes a `close` method contracted to release background resources if the implementation owns any; implementations without owned resources may perform a no-op. Never generalize one Google Cloud client's behavior to all others.

## 5. Managing ManagedChannel and Transport Ownership

When manually creating a channel for a gRPC service, manage both initialization and shutdown. Do not create a new channel per request, and do not close a channel while RPCs are still in flight.

### Example: Timed Channel Shutdown

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.concurrent.TimeUnit;

public final class ChannelExample {
    public static void main(String[] args) {
        ManagedChannel channel = ManagedChannelBuilder
            .forTarget("api.example.internal:443")
            .useTransportSecurity()
            .build();

        try {
            // Create and use stubs from the channel.
        } finally {
            channel.shutdown();
            try {
                if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
                    channel.shutdownNow();
                }
            } catch (InterruptedException interrupted) {
                channel.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

`shutdown` stops accepting new RPCs; existing calls can continue during termination depending on state. `shutdownNow` forcefully cancels remaining calls; even so, it does not guarantee resources vanish instantaneously. In real servers, stop generating new requests and wait for in-flight requests before closing the channel.

### Wrapping a Channel in a Bean with Clear Ownership

When customizing channel configuration and shutdown timeouts, you can use an `AutoCloseable` wrapper:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.concurrent.TimeUnit;

public final class GrpcChannelOwner implements AutoCloseable {
    private final ManagedChannel channel;

    public GrpcChannelOwner(String target) {
        this.channel = ManagedChannelBuilder
            .forTarget(target)
            .useTransportSecurity()
            .build();
    }

    public ManagedChannel channel() {
        return channel;
    }

    @Override
    public void close() {
        channel.shutdown();
        try {
            if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
                channel.shutdownNow();
            }
        } catch (InterruptedException interrupted) {
            channel.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Spring configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class GrpcConfig {
    @Bean(destroyMethod = "close")
    GrpcChannelOwner grpcChannelOwner() {
        return new GrpcChannelOwner("api.example.internal:443");
    }
}
~~~

Services can inject `GrpcChannelOwner` to create stubs, but must not call `close` during request handling. For applications targeting multiple endpoints, keep an independent owner per required endpoint/configuration.

### When Library Clients Receive a Custom Transport

GAX provides transport channel providers and builders to configure endpoints, credentials, or transport. A provider may create a new channel or return a fixed channel; APIs indicate whether the client holding the provider automatically closes the channel.

When supplying a channel manually:

1. Identify who creates the channel and who holds authority to close it.
2. Read the `shouldAutoClose` contract and provider behavior for your library version.
3. Avoid having both the client and a wrapper assume ownership.
4. Never close a shared channel while any client is still using it.
5. Maintain shutdown order: stop new requests, wait for in-flight work, close clients, and then close the channel if your owner actually owns it.

## 6. Thread Pools: Bounded Resources

Thread pools execute concurrent work: `@Async` tasks, callbacks, message handling, and certain blocking operations. Never create a new executor per request, as thread counts will grow unchecked.

Executor configuration includes:

| Property | Meaning | Risk if misconfigured |
|---|---|---|
| Core pool size | Baseline worker count | Too high causes context switching |
| Max pool size | Ceiling on worker count | Too high consumes RAM and stresses dependencies |
| Queue capacity | Number of queued tasks | Unbounded queues hide overload and inflate latency |
| Keep-alive | Idle retention time for extra workers | Too long wastes resources; too short causes churn |
| Rejection policy | Behavior when full | Silently drops tasks or stalls callers |
| Thread naming | Aids thread dump debugging | Cannot identify which pool owns a task |
| Shutdown wait | Waits for running tasks | Stopping too early loses work; waiting too long risks kills |

A huge executor will not speed up an external API with fixed quotas or latency. For blocking I/O, worker counts can exceed CPU cores, but must remain bounded by memory, downstream capacity, and deadlines.

### Spring ThreadPoolTaskExecutor

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfig {

    @Bean(name = "gcpIoExecutor")
    ThreadPoolTaskExecutor gcpIoExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(12);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("gcp-io-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(8);
        return pool;
    }
}
~~~

Spring manages initialization and destruction of `ThreadPoolTaskExecutor` when declared as a bean. You do not need to call `pool.initialize()` manually inside the `@Bean` method. The values 4, 12, 100, and 8 seconds are only examples; tune them against real workloads and platform shutdown limits.

In a `ThreadPoolExecutor` with a bounded queue, once core threads are busy, tasks are queued before the pool scales up to max threads. Thus queue capacity and max pool size must be chosen together; an excessively large queue can keep max threads almost unused.

### Using @Async Properly

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncLookupService {
    private final SecretReader secretReader;

    public AsyncLookupService(SecretReader secretReader) {
        this.secretReader = secretReader;
    }

    @Async("gcpIoExecutor")
    public CompletableFuture<String> loadValue(
            String project, String secret, String version) {
        String result = secretReader.readUtf8(project, secret, version);
        return CompletableFuture.completedFuture(result);
    }
}
~~~

`@Async` only shifts execution onto an executor; it does not turn a blocking RPC into a non-blocking one. You must handle timeouts, failures, and pool rejections. In Spring proxy mode, calling an `@Async` method from another method within the same object bypasses the proxy and will not trigger asynchronous execution as expected.

When handling sensitive data, avoid passing plaintext secrets across unnecessary async layers. This example merely illustrates thread pool mechanics and DI.

## 7. Backpressure and Thread Pool Overload

When incoming request rates exceed processing rates, tasks pile up. With an unbounded queue, latency climbs and the application can run out of memory before CPU alerts even fire.

A simple model:

~~~text
HTTP requests / Pub/Sub messages
             |
             v
     Bounded work queue
             |
        +----+----+
        |         |
        v         v
     Worker 1   Worker N
        |         |
        +----+----+
             |
             v
      Google Cloud API
      (quota / latency)
~~~

When the queue fills, respond deliberately:

- Reject excess work early with appropriate status codes and retry guidance.
- Reduce in-flight messages using Pub/Sub flow control.
- Lower request concurrency or apply semaphores/bulkheads around dependencies.
- Use Cloud Tasks or Pub/Sub for asynchronous work requiring durability and retries.
- Enforce end-to-end timeouts so requests never wait indefinitely.

### Avoid Using CallerRunsPolicy Lightly

`CallerRunsPolicy` runs tasks on the caller's thread when the pool is full. It can create natural backpressure, yet if the caller is an HTTP request thread or gRPC event loop, blocking work can stall critical threads and trigger cascading failures.

`AbortPolicy` or explicit rejection mechanisms are often easier to operate when the app can return errors and apply bounded retries. Choose a rejection policy based on task semantics; no single policy fits every system.

### Avoiding Deadlocks from Nested Futures

If a task running in a small pool submits another task to the same pool and blocks waiting for its result, workers can become fully occupied with no free thread left to run the child task. Avoid nested blocking, separate pools by responsibility, or use non-blocking future composition.

## 8. Pub/Sub Publisher: Batching and Flushing on Shutdown

`Publisher` batches messages, handles retries, and maintains background resources. Create one shared `Publisher` per topic/configuration rather than instantiating one per message.

Java example:

~~~java
import com.google.api.core.ApiFuture;
import com.google.cloud.pubsub.v1.Publisher;
import com.google.pubsub.v1.PubsubMessage;
import com.google.pubsub.v1.TopicName;
import com.google.protobuf.ByteString;
import java.util.concurrent.TimeUnit;

public final class PublishExample {
    public static void send(String project, String topic) throws Exception {
        Publisher publisher = Publisher
            .newBuilder(TopicName.of(project, topic))
            .build();

        try {
            PubsubMessage message = PubsubMessage.newBuilder()
                .setData(ByteString.copyFromUtf8("order-created"))
                .build();

            ApiFuture<String> messageId = publisher.publish(message);
            System.out.println("Published: " + messageId.get(10, TimeUnit.SECONDS));
        } finally {
            publisher.shutdown();
            try {
                publisher.awaitTermination(10, TimeUnit.SECONDS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

This example shows a short-lived program owning its `Publisher`. In a Spring app, `Publisher` should be a singleton or managed through a closeable wrapper: stop accepting new tasks, flush batched messages, call `shutdown`, and wait for termination within a bounded timeout.

Key notes:

- Publish results complete asynchronously; inspect the future to confirm message acceptance.
- Never ignore publish errors; decide whether to retry, persist durably, or fail according to business rules.
- Tune batching, flow control, and retries to fit throughput and memory budgets.
- On shutdown, allow enough time for pending messages; if killed mid-flight, work held only in RAM can be lost.
- For workflows requiring guaranteed message delivery after database writes, consider a transactional outbox or durable mechanism instead of relying solely on shutdown flushes.

## 9. Pub/Sub Subscriber: Start/Stop Lifecycle and Concurrency

`Subscriber` uses StreamingPull to receive messages and dispatch them to callbacks. It has a different lifecycle from synchronous RPC clients:

~~~text
CREATED
   |
   v
STARTING -> RUNNING -> STOPPING -> TERMINATED
                 |
                 +--> FAILED
~~~

The application must call `startAsync` and observe `awaitRunning` or listeners; on shutdown, call `stopAsync` and then wait on `awaitTerminated` within an appropriate timeout.

### Configuring Thread Counts and Flow Control

~~~java
import com.google.api.gax.batching.FlowControlSettings;
import com.google.api.gax.core.ExecutorProvider;
import com.google.api.gax.core.InstantiatingExecutorProvider;
import com.google.cloud.pubsub.v1.Subscriber;

// subscriptionName and messageReceiver are created elsewhere.
ExecutorProvider executorProvider =
    InstantiatingExecutorProvider.newBuilder()
        .setExecutorThreadCount(4)
        .build();

FlowControlSettings flowControl =
    FlowControlSettings.newBuilder()
        .setMaxOutstandingElementCount(200L)
        .setMaxOutstandingRequestBytes(20L * 1024 * 1024)
        .build();

Subscriber subscriber =
    Subscriber.newBuilder(subscriptionName, messageReceiver)
        .setParallelPullCount(2)
        .setExecutorProvider(executorProvider)
        .setFlowControlSettings(flowControl)
        .build();

subscriber.startAsync().awaitRunning();
~~~

This example illustrates bounding in-flight message counts and bytes. Because configuration methods vary across client versions, check the corresponding JavaDoc. With Pub/Sub Java, `parallelPullCount` tunes the number of pull streams, while `executorProvider` controls workers serving callbacks. Do not increase thread counts while ignoring flow control, as in-flight messages and payload sizes also drive memory consumption.

### Stopping the Subscriber

~~~java
subscriber.stopAsync();
try {
    subscriber.awaitTerminated(8, TimeUnit.SECONDS);
} catch (java.util.concurrent.TimeoutException timeout) {
    // Record the timeout and let the shutdown orchestrator proceed.
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
}
~~~

Stop accepting new messages first, then wait for running callbacks to finish within the shutdown budget. Ack only once processing is durably complete per business rules; never ack early for unfinished work just to shut down faster. Unacked messages can be redelivered, so consumers must be idempotent.

On Cloud Run services, Google recommends Pub/Sub push subscriptions for HTTP message-receiving workloads because push triggers autoscaling. A background streaming pull subscriber requires an explicit CPU, minimum instances, and lifecycle strategy; for continuous workloads, consider GKE, Compute Engine, or a better-suited runtime.

## 10. Proper Shutdown Ordering in Spring Applications

Shutdown is more than calling `close` on objects in random order. Closing a channel while callbacks are still sending RPCs causes those calls to fail.

A reference sequence:

1. Receive shutdown signal and stop accepting new requests or jobs.
2. Stop schedulers and subscribers from pulling new messages.
3. Wait for in-flight HTTP requests, async tasks, and message handlers up to a deadline.
4. Flush Publishers or remaining batched outputs.
5. Close Google Cloud API clients and the HTTP/gRPC resources they own.
6. Close application-managed `ManagedChannel` instances.
7. Shut down application-owned executors, waiting up to the remaining time budget.
8. Log any incomplete tasks and exit the process.

Exact ordering depends on the dependency graph: an executor used to complete publish callbacks must not close before the `Publisher`. A shared channel used by multiple clients must close only after all clients stop sending RPCs.

### Spring Lifecycle Hooks

| Hook | When to use | Notes |
|---|---|---|
| `@Bean(destroyMethod = "close")` | `AutoCloseable` singleton clients | Simple, managed by context |
| `@PreDestroy` | Cleaning up resources inside a specific component | Avoid long blocking or unnecessary API calls |
| `DisposableBean` | Integrating resource cleanup with Spring | Couples code directly to Spring |
| `SmartLifecycle` | Phased start/stop needed, e.g., Subscriber | Can coordinate ordered shutdown |
| `ThreadPoolTaskExecutor` bean | Spring-managed `@Async` pool | Configure wait and shutdown timeout |
| JVM shutdown hook | Java mechanism outside DI container | Does not replace Spring lifecycle |

When beans depend on each other, Spring uses dependency relationships to order destruction. For complex resources, use `SmartLifecycle` with deliberate phases and verify via integration tests. Never rely on class names or arbitrary declaration order.

### Spring Boot Graceful Shutdown

Example `application.yml`:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 8s
~~~

Spring Boot attempts to finish in-flight requests within the shutdown phase budget. The 8-second figure is only an example; the total shutdown budget must be shared across the web server, subscribers, publishers, clients, and executors. Configuring 8 seconds on multiple components does not guarantee everything finishes within 8 seconds total.

## 11. Specifics for Cloud Run, GKE, and Compute Engine

### Cloud Run

Cloud Run services can scale in, swap revisions, or terminate instances. During shutdown, an instance receives `SIGTERM` for cleanup within a short grace period—typically around 10 seconds before termination. Do not design shutdowns that rely on waiting minutes to drain tasks.

With request-based billing, CPU outside active request handling can be throttled or unavailable. Therefore, it is unsuitable to spawn a background thread, return an HTTP response, and expect the work to always finish.

For work that must finish after an HTTP response:

- Use Pub/Sub push or Cloud Tasks for retryable tasks.
- Use Cloud Run jobs for finite batch processing with task timeouts and configuration.
- If background processing on live instances is truly required, evaluate instance-based billing and minimum instances, while still handling sudden instance termination.
- Persist state or checkpoints durably rather than keeping critical data only in RAM.

Cloud Run autoscaling depends on concurrency and CPU. The number of Cloud Run instances multiplied by clients/channels/connections per instance can place heavy load on dependencies. Never size resources for only one instance.

### GKE

Pods have `terminationGracePeriodSeconds`, readiness probes, and container lifecycles. When a pod prepares to stop, it must stop receiving new traffic and allow in-flight requests time to complete before the container is killed.

Ingress/load balancer draining, web server graceful shutdown, and client closing must all fit within the configured grace period. If `terminationGracePeriodSeconds` is too short, `Publisher` may not finish flushing. If too long, rollouts can slow down.

Monitor pod restarts, memory, CPU, open file descriptors, thread counts, and connection counts. Oversized thread pools combined with low memory limits can trigger `OOMKilled` even when the Java heap is not full, because native thread stacks and buffers also consume memory.

### Compute Engine

JVM processes on VMs receive shutdown signals when VMs stop or instance groups resize. Use `systemd` or a process supervisor to forward signals, set timeouts, and log shutdown behavior.

Do not rely on shutdown hooks to finish long-running jobs or critical state transitions. Build persistence, checkpoints, and retries into the business layer.

## 12. Calculating Concurrency and Downstream Capacity

Suppose a Cloud Run service has:

- Up to 20 instances at peak load.
- Each instance has a pool of up to 12 workers calling APIs.
- Each worker can open or hold one database connection while executing work.

Without separate limits, maximum concurrent database demand can reach roughly 20 × 12 = 240 connections—excluding connections from background components and other services. If Cloud SQL only supports a lower threshold, enlarging thread pools can spike error rates.

A core design principle is defining a **concurrency budget** per dependency:

~~~text
Total concurrent demand
  ≈ active instance count
    × allowed requests/concurrency per instance
    × concurrent operations per dependency
~~~

This formula is a rough estimate. Requests can fan out, retry, or batch; therefore account for peaks, retry amplification, and background workloads.

### Per-Dependency Limits

You can use semaphores, bulkheads, or separate bounded executors for resource-intensive calls. You do not need a separate thread pool for every minor API, though dependencies with vastly different limits may warrant independent concurrency boundaries.

Examples:

- Secret Manager: cache results briefly in a controlled way when appropriate; bound requests by quota.
- Cloud SQL: coordinate connection pool sizes with maximum instance counts.
- Pub/Sub: use flow control and batching.
- Internal gRPC: enforce deadlines, cap in-flight RPCs, and apply backoff on retries.
- Cloud Storage: bound concurrent uploads/downloads according to bandwidth and memory.

## 13. Deadlines, Retries, and Cancellation

A thread stuck in an RPC indefinitely keeps occupying a worker and queue slot. Lifecycle management must therefore incorporate timeouts and deadlines.

### gRPC Deadlines

~~~java
MyServiceGrpc.MyServiceBlockingStub timed =
    stub.withDeadlineAfter(1500, TimeUnit.MILLISECONDS);

// RPCs via timed carry a time limit.
~~~

A deadline is the RPC's processing time limit; upon expiration, the RPC is typically cancelled and returns `DEADLINE_EXCEEDED`. In multi-hop pipelines, propagate deadlines or compute remaining budgets so hops do not accumulate unbounded wait times.

### Bounded Retries

Apply retries only to transient errors and operations compatible with idempotency. Use exponential backoff, jitter, overall deadlines, and retry budgets. When an executor is already saturated, uncontrolled retries can worsen overload.

### Cancellation

When an HTTP client disconnects, tasks may keep running unless the application propagates cancellation. With `CompletableFuture` and async APIs, verify client cancellation support and interruption semantics. Do not assume `Future.cancel` automatically aborts a network RPC if the library does not support it.

## 14. Virtual Threads in Java 21 and Spring Boot

Virtual threads lower the per-thread cost of Java threads for many blocking I/O workloads. In supported Spring Boot versions, enable them with:

~~~properties
spring.threads.virtual.enabled=true
~~~

When enabled on Java 21+, several Spring Boot auto-configured executors/schedulers can switch to virtual threads instead of traditional platform thread pools.

Virtual threads **do not increase API quotas, database connections, or network bandwidth**. If 10,000 virtual threads simultaneously call a dependency limited to 100 concurrent requests, the dependency is still overwhelmed. Use semaphores, rate limits, or in-flight work caps.

Things to verify:

- Do libraries use `synchronized` blocks or native calls that pin carrier threads in specific scenarios?
- Are MDC, trace context, and security context propagated properly?
- How do Spring Boot auto-configured executors behave once virtual threads are enabled?
- Is blocking I/O truly the primary bottleneck, or is the system CPU-bound?
- Are concurrent RPC and queue limits still enforced?

Do not turn on virtual threads as a replacement for backpressure mechanisms. Benchmark on realistic workloads and monitor latency, memory, thread states, and throughput.

## 15. Monitoring and Detecting Resource Leaks

Metrics, logs, and thread dumps help verify whether clients, channels, and executors are managed properly.

| Signal | Possible meaning | Next check |
|---|---|---|
| Thread count rises after each request | Repeatedly creating executors/clients | Check creation sites and thread names |
| Open file descriptors climb | Connections/sockets not released | Check channel and HTTP client ownership |
| Queue depth grows continuously | Work arrives faster than processed | Measure arrival rate, worker utilization, downstream latency |
| Active threads constantly hit max | Pool saturated or tasks blocking | Thread dumps, timeouts, dependency metrics |
| RPC latency rises while CPU is low | Waiting on network/dependency or pool queue | Traces and client metrics |
| High Pub/Sub outstanding messages | Slow callbacks or misconfigured flow control | Ack latency, subscriber concurrency |
| Prolonged or timed-out shutdown | Producer not stopped, wrong drain order | Lifecycle logs and remaining in-flight tasks |
| Memory grows despite stable heap | Native thread stacks, direct buffers, transport | JVM native memory and connection metrics |

### Thread Dumps

When suspecting thread leaks or deadlocks, safely capture thread dumps using appropriate JVM tooling and analyze:

- Thread counts grouped by prefix.
- Thread states: `RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED`.
- Repeated stack traces stuck on the same blocking operation.
- Whether executor workers are idle waiting for tasks or stuck in RPCs.
- Whether gRPC/Netty and client library threads grow with request count rather than instance/client count.

Do not judge solely by absolute thread count. Some libraries legitimately create background threads; what matters is whether thread counts grow without returning to baseline or scale with request count instead of designed instance/client counts.

### Micrometer and Cloud Monitoring

Spring Boot Actuator and Micrometer can expose JVM, executor, and custom application metrics. Export metrics to Cloud Monitoring or Managed Service for Prometheus depending on your architecture.

Dashboards should include:

- JVM live/daemon threads and memory.
- Executor active count, queue size, completed/rejected tasks.
- RPC latency, deadline exceeded counts, retries, and error rates per dependency.
- Pub/Sub publish latency, pending messages, and subscriber ack/nack counts.
- HTTP request latency, 5xx errors, and Cloud Run/GKE saturation.
- Instance/pod counts and downstream connection counts.

Metric labels should never contain user IDs, emails, or request IDs due to cardinality explosion and security risks.

## 16. Real-World Scenario: Spring Boot API on Cloud Run

A checkout service on Cloud Run receives HTTP requests, reads configuration from Secret Manager, writes to a database, and publishes Pub/Sub events.

### Poorly Suited Design

Inside every request, the controller creates a new `SecretManagerServiceClient`, `Publisher`, and `ExecutorService`, then returns the HTTP response right after submitting the task to the executor.

Problems:

- New clients and executors continuously consume connections and threads.
- `Publisher` may not flush before the response returns and CPU gets throttled.
- When Cloud Run scales in, tasks queued only in RAM can disappear.
- No limits exist on tasks or Cloud SQL connections.
- Unclear shutdown ownership prevents safe draining.

### Improved Design

~~~text
Spring ApplicationContext (per Cloud Run instance)
           |
           +--> SecretManagerServiceClient singleton
           |
           +--> Pub/Sub Publisher singleton
           |
           +--> Bounded Executor / semaphore
           |
           +--> Database connection pool
           |
           +--> HTTP request handlers
                      |
                      v
              Checkout service
                      |
                      +--> Read configuration via shared client
                      +--> Execute transaction with deadline
                      +--> Write durable outbox/event
                      +--> Return confirmed result
~~~

In this design:

1. Spring creates one instance per shared client configuration.
2. Request handlers never close clients themselves.
3. Pool and connection limits are sized across the maximum Cloud Run instance count.
4. Critical events are published via a durable mechanism (e.g., outbox + publisher worker or Pub/Sub push/Cloud Tasks depending on business needs).
5. On shutdown, the app stops accepting work, drains within budget, and then closes Publishers, clients, and executors.
6. Telemetry tracks latency, queue depth, active connections, failed publishes, and shutdown duration.

### Verification Approach

- Load test near production concurrency levels.
- Check thread counts before and after thousands of requests.
- Trigger a new rollout to exercise shutdown/restart and inspect in-flight messages.
- Verify Pub/Sub loses no business events and consumers handle duplicates.
- Verify queues are bounded and requests reject cleanly under overload.
- Confirm the service stays healthy when a dependency slows down or returns transient errors.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Creating GAPIC clients per request | Thread/connection churn, higher latency | Create singleton beans and close on context stop |
| Closing a singleton client in a service method | Subsequent requests fail with closed client | Let Spring/owner manage `close` |
| Creating a `ManagedChannel` per RPC | Extra connections and TLS overhead | Reuse channels; create stubs as needed |
| Unclear channel ownership | Double close or resource leaks | Specify which client/provider/wrapper owns it |
| Executor with an unbounded queue | Latency and memory spike under overload | Bounded queue, rejection/backpressure |
| Enlarging thread pools to fix a slow API | Downstream overload and retry storms | Bound concurrency, timeouts, and analyze dependency |
| Closing executor before draining Publisher | Callbacks/flushes fail | Stop producers and wait for in-flight work before closing executor |
| Acking Pub/Sub before durable processing | Work lost if instance is killed | Ack only after durable completion |
| Running background threads after HTTP response on Cloud Run | Tasks can freeze or disappear on instance stop | Use Pub/Sub/Cloud Tasks/Jobs appropriately |
| Relying only on `@PreDestroy` for multi-minute work | Exceeds platform grace period | Budgeted shutdown, checkpoints, and retries |
| Enabling virtual threads and removing all limits | Dependencies still overload | Semaphores, rate limits, and quota-aware design |

## 18. Pre-Deployment Checklist for Java Services on GCP

- [ ] Every client has a defined owner and lifetime scope.
- [ ] Shared clients are created once per distinct configuration.
- [ ] Google Cloud client `close`/`shutdown` is managed by Spring or an explicit owner.
- [ ] Shared `ManagedChannel` instances are never closed inside individual RPCs.
- [ ] Custom channels/providers have clear ownership and close-order contracts.
- [ ] `ThreadPoolTaskExecutor` has bounded core/max/queue sizes and a rejection policy.
- [ ] No long blocking tasks run on gRPC event loops or critical request threads.
- [ ] Each dependency has appropriate deadlines, retry budgets, and concurrency limits.
- [ ] Pub/Sub `Publisher` is flushed and awaited via `awaitTermination` on shutdown.
- [ ] `Subscriber` has explicit start/stop, flow control, and timely acks.
- [ ] Spring graceful shutdown and platform grace periods share a realistic time budget.
- [ ] Cloud Run does not rely on in-RAM tasks after HTTP responses for mandatory work.
- [ ] Connection/pool totals are sized across all instances/pods.
- [ ] Metrics cover thread counts, active/queued/rejected tasks, RPC latency, and shutdown errors.
- [ ] Load tests and scale-in/restart tests confirm no loss of critical work.

## Conclusion

Resource lifecycle management in Java/Spring on GCP starts with three questions: **who creates, who uses, and who closes**. Google Cloud clients and gRPC channels should generally be reused across the application lifecycle; thread pools require bounds and backpressure policies; Publishers and Subscribers require explicit draining and stop routines. Spring helps coordinate bean lifecycles, yet applications must still account for deadlines, shutdown order, instance counts, quotas, and termination windows on Cloud Run or GKE. Designing ownership, concurrency, and telemetry from the beginning reduces resource leaks, handles load steadily, and ensures reliable recovery when instances change.

## References

- [SecretManagerServiceClient Java reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-secretmanager/latest/com.google.cloud.secretmanager.v1.SecretManagerServiceClient)
- [Google Cloud Java client configuration](https://docs.cloud.google.com/java/docs/common-configuration-options)
- [GAX TransportChannelProvider reference](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.rpc.TransportChannelProvider)
- [Pub/Sub Java Publisher reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.cloud.pubsub.v1.Publisher)
- [Pub/Sub Java Subscriber reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.cloud.pubsub.v1.Subscriber)
- [Pub/Sub concurrency control](https://docs.cloud.google.com/pubsub/docs/concurrency-control)
- [gRPC Java ManagedChannel](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannel.html)
- [Spring Framework: Bean lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Boot: Task execution and scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Spring Boot: Graceful shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Cloud Run: Instance autoscaling](https://docs.cloud.google.com/run/docs/about-instance-autoscaling)
- [Cloud Run: Billing settings and background CPU](https://docs.cloud.google.com/run/docs/configuring/billing-settings)
- [Cloud Run: Container shutdown](https://docs.cloud.google.com/run/docs/configuring/execution-environments)
