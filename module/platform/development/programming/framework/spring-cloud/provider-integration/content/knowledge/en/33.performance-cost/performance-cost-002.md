# Bounding Threads, Connections, and Buffers in Asynchronous Flows

A Spring Boot application can receive requests faster than a database, Redis, object storage, or message consumer can process them. In an asynchronous model, threads do not block while waiting for I/O, yet work still consumes connections, buffers, memory, CPU, and service quotas. Without bounds, requests accumulate in queues, buffers swell, connection pools exhaust, and latency climbs until the application or downstream becomes unstable.

A safe design independently bounds four resources: **execution threads**, **in-flight operations**, **connections/channels to services**, and **data waiting in buffers/queues**. These limits must work together. Adding threads does not fix an undersized connection pool; growing the pool does not fix an unbounded message buffer; enabling reactive backpressure does not automatically protect an async API returning `CompletableFuture` if the application submits them without limit.

This lesson belongs to the **Performance and Cost** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries, including identity/permissions configuration, storage, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on resource limits and flow control in async/reactive pipelines when calling cloud services.

## 1. Learning outcomes

After this lesson, you will be able to:

- Distinguish between event-loop threads, worker/executor threads, connections, in-flight requests, and buffers.
- Explain why async I/O still requires concurrency and memory limits.
- Design Reactor pipelines with `flatMap`, `limitRate`, prefetch, and bounded buffers.
- Configure AWS SDK async Netty concurrency and future-completion executors.
- Bound connections and pending acquires on the Azure Netty HTTP transport.
- Configure Google Cloud Pub/Sub subscriber flow control by message count and byte count.
- Configure an R2DBC pool and calculate total connections across pods.
- Estimate buffer memory from payload size, concurrency, and queue layers.
- Set up timeouts, cancellation, retries, graceful shutdown, and metrics.
- Test overload behavior to prove the system has finite bounds when downstream is slow.

## 2. Async does not mean infinite resources

A request may traverse multiple layers:

~~~mermaid
flowchart LR
    A[HTTP request] --> B[WebFlux event loop]
    B --> C[Reactor pipeline]
    C --> D[Application worker / callback executor]
    C --> E[SDK client]
    E --> F[Connection pool / HTTP concurrency]
    F --> G[Cloud service]
    C --> H[Operator buffers / queues]
~~~

Each layer holds a distinct kind of resource:

| Resource | What is being bounded? | Under overload |
| --- | --- | --- |
| Event-loop threads | Threads coordinating I/O and callbacks | A single blocking section can stall many requests |
| Worker/executor threads | Concurrent CPU tasks or blocking callbacks | Queues grow, tasks are delayed or rejected |
| In-flight concurrency | Requests/operations currently in progress | New requests wait or are rejected |
| HTTP connections/channels | Active network connections or streams | Pool acquisition slows down or times out |
| Buffers/queues | Items/bytes received but not yet processed | Heap/direct memory grows, GC spikes and OOM |
| Downstream quota | Actual processing capacity of the cloud service | Throttling, 429s, retries, and higher latency |

Do not use a single number to represent everything. For example, `maxConnections=50` does not mean the application handles only 50 requests if HTTP/2 multiplexes multiple streams; `flatMap(concurrency=100)` also does not mean 100 TCP connections because the client may queue requests in a pending queue.

## 3. Distinguishing threads, concurrency, connections, and buffers

### 3.1. Threads

A thread is the unit of code execution. In an async pipeline, a thread may initiate a request and then return to the event loop; the completion callback may run on a different thread. Thus, the number of requests waiting on I/O can far exceed the number of threads.

### 3.2. In-flight concurrency

Concurrency is the number of operations started but not yet finished. For instance, `flatMap(..., 16)` allows at most 16 inner publishers active simultaneously. This is an application-pipeline limit; it is independent of the SDK's connection limit.

### 3.3. Connections or HTTP/2 streams

A connection is a TCP/TLS channel to an endpoint. With HTTP/1.1, a connection typically handles one request at a time; with HTTP/2, multiple streams can share one connection. gRPC also uses HTTP/2 channels/streams. Read the exact meaning of `maxConnections`, `maxConcurrency`, or channel pools for the client in use.

### 3.4. Buffers and queues

Buffers hold data that has been received but not yet processed or forwarded. Buffers can live inside Reactor operators, Netty, SDK executors, R2DBC pools, message clients, or the application itself. A pipeline has multiple buffer layers; bounding one layer does not automatically bound the remaining layers.

### 3.5. Backpressure

Backpressure is the mechanism by which downstream signals to upstream the rate at which it can accept items. Reactive Streams represents demand via `request(n)`. If the producer cannot slow down, the system must explicitly choose one of three strategies: **buffer**, **drop**, or **fail**. None of these strategies is free.

Spring WebFlux uses a small number of event-loop threads and assumes non-blocking code. Reactive Streams lets subscribers control publisher rate, but only works when the publishers/operators in the pipeline honor demand.

## 4. Finding unbounded points in a pipeline

A pipeline can look reactive while still accumulating work:

~~~java
ids.flatMap(id -> remoteClient.fetch(id));
~~~

If the source emits quickly, default `flatMap` can allow many inner publishers to run concurrently according to the Reactor version's defaults. When downstream slows down, many already-submitted requests can still wait inside the SDK/HTTP client. If code eagerly turns each item into a `CompletableFuture` and stores them in a list, the application creates an unbounded queue before Reactor can control demand.

Check the following points:

1. Can the data source emit faster than the consumer processes?
2. Do operators have finite `concurrency`, `prefetch`, or buffer bounds?
3. Does the SDK client bound in-flight requests and pending acquires?
4. Does the executor have a bounded queue?
5. Does the message consumer cap outstanding messages/bytes?
6. Does the connection pool have an acquisition timeout?
7. When a caller times out or cancels, is downstream work canceled/released?

## 5. Reactor: bounding demand, concurrency, and prefetch

### 5.1. Bounding inner operations with flatMap

Example reading multiple items from a reactive repository:

~~~java
import reactor.core.publisher.Flux;

public Flux<Product> loadProducts(Flux<String> productIds) {
    return productIds.flatMap(
        id -> productRepository.findById(id),
        16,
        8
    );
}
~~~

- `concurrency=16`: at most 16 inner publishers subscribed concurrently.
- `prefetch=8`: number of items requested upfront from each inner publisher in this operator.

Prefetch is neither a connection count nor a byte limit. If each item is large, a prefetch of 8 can consume substantial memory. For a `Mono` returning one small result, prefetch matters less; for a multi-item `Flux`, measure carefully.

### 5.2. Shaping upstream requests in batches with limitRate

~~~java
Flux<Order> orders = orderRepository.findAll()
    .limitRate(64);
~~~

`limitRate` splits upstream demand into small batches rather than requesting all data at once. It helps pace demand, but does not replace connection pool limits, SDK concurrency, or driver buffers.

### 5.3. Bounded buffers and overflow policies

If upstream cannot slow down, use a finite buffer and define behavior when full:

~~~java
import reactor.core.publisher.BufferOverflowStrategy;

Flux<Event> safeEvents = eventSource
    .onBackpressureBuffer(
        256,
        dropped -> metrics.incrementBufferOverflow(),
        BufferOverflowStrategy.ERROR
    );
~~~

When the buffer is full, the pipeline emits an error instead of retaining data indefinitely. For telemetry where sampling loss is acceptable, pick a suitable drop policy; for business commands or guaranteed messages, never drop silently. Use a durable broker/queue and acknowledgments when persistence, replay, or retries are required.

Options:

| Strategy | When buffer is full | Suitable for |
| --- | --- | --- |
| Bounded buffer + ERROR | Terminates pipeline with an error | Detecting overload when silent data loss is unacceptable |
| DROP_OLDEST | Drops oldest item to accept the newest | Telemetry/state snapshots where fresher data matters more |
| DROP_LATEST | Drops the incoming item | Preserving order/recency of existing backlog |
| LATEST | Keeps only the latest value | UI state or metric snapshots |
| Unbounded buffer | Keeps accepting until memory runs out | Avoid in production flows without bounded inputs |

### 5.4. Batching with buffers

~~~java
import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;

Flux<List<Event>> batches = eventSource.bufferTimeout(
    100,
    Duration.ofMillis(200)
);
~~~

Batches up to 100 events or emits after 200 ms. Batching reduces per-request overhead but holds items in memory longer. If payloads vary in size, add a byte limit at the producer/consumer or check total batch size before sending.

## 6. Schedulers and thread limits in Reactor

### 6.1. Choosing the right scheduler for the work

| Scheduler | Purpose | Do not use for |
| --- | --- | --- |
| `Schedulers.parallel()` | Short CPU-bound work, non-blocking | JDBC or blocking file/network I/O |
| `Schedulers.single()` | Intentional sequential/low-latency tasks | Long blocking work or high load |
| `Schedulers.boundedElastic()` | Bridge for blocking APIs | Replacing non-blocking drivers across the whole app |
| Event loop | Coordinating I/O and callbacks | `Thread.sleep`, JDBC, or heavy CPU work |

Example isolating a legacy JDBC call:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Customer> customer = Mono.fromCallable(
        () -> jdbcRepository.findById(id)
            .orElseThrow(CustomerNotFoundException::new))
    .subscribeOn(Schedulers.boundedElastic());
~~~

This is a temporary bridge; JDBC still blocks a worker thread. The `boundedElastic` limit does not replace the connection pool and does not increase database throughput.

### 6.2. boundedElastic also has a queue

Reactor 3.8 defaults global `boundedElastic()` to roughly 10 times the number of available CPUs and a default queue cap of 100,000 tasks per backing thread. These are defaults subject to version/system properties, not production targets. When a queue is too large, tasks can wait a long time before running; when the limit is exceeded, the scheduler rejects tasks.

For isolated blocking workloads, you can create a scheduler with explicit bounds:

~~~java
import org.springframework.context.annotation.Bean;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Bean(destroyMethod = "dispose")
Scheduler legacyIoScheduler() {
    return Schedulers.newBoundedElastic(
        24,
        200,
        "legacy-io"
    );
}
~~~

Here there are at most 24 backing threads and a queue of at most 200 tasks per backing thread. Pick values based on blocking duration, database connections, and SLAs. Do not grow the queue to tens of thousands to mask a slow downstream.

### 6.3. Do not use the parallel scheduler for blocking calls

`parallel()` is tuned for short CPU-bound tasks. If a JDBC task occupies a parallel thread, other CPU tasks on the same scheduler can starve. Move blocking work to `boundedElastic` or use a non-blocking driver.

## 7. AWS SDK for Java 2.x: Netty concurrency and future executors

### 7.1. Two different thread groups

The AWS async client uses Netty for I/O and an `ExecutorService` to complete `CompletableFuture`s. These serve two distinct roles:

- Netty I/O threads handle sockets and events.
- The future-completion executor runs completion callbacks and future-finishing tasks.

By default, the AWS SDK creates a thread pool per async client based on processor count and manages queued tasks. Async clients use non-blocking I/O, yet do not guarantee the entire call path is non-blocking: credential retrieval, SigV4 signing, or endpoint discovery may execute blocking calls.

### 7.2. Bounding concurrency and pending connection acquires

~~~java
import java.time.Duration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.services.s3.S3AsyncClient;

S3AsyncClient s3 = S3AsyncClient.builder()
    .region(Region.US_EAST_1)
    .httpClientBuilder(NettyNioAsyncHttpClient.builder()
        .maxConcurrency(128)
        .maxPendingConnectionAcquires(256)
        .connectionAcquisitionTimeout(Duration.ofSeconds(2)))
    .build();
~~~

- `maxConcurrency` bounds how many concurrent requests the HTTP client supports.
- `maxPendingConnectionAcquires` bounds requests waiting for a connection/concurrency slot.
- `connectionAcquisitionTimeout` bounds how long a request waits for a slot.

The meaning of `maxConcurrency` depends on transport and protocol. AWS SDK metrics scope it per HTTP client instance; Apache applies it across the entire HTTP client, whereas Netty/CRT apply it per endpoint. With HTTP/2, concurrency represents streams rather than necessarily TCP connections.

### 7.3. Bounding the future-completion executor

When callbacks perform heavy mapping or response serialization, configure a dedicated executor with a bounded queue:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.core.client.config.SdkAdvancedAsyncClientOption;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

@Configuration(proxyBeanMethods = false)
class AwsAsyncConfiguration {
    @Bean(destroyMethod = "shutdown")
    ExecutorService awsCompletionExecutor() {
        AtomicInteger sequence = new AtomicInteger();
        ThreadFactory threadFactory = task -> {
            Thread thread = new Thread(
                task, "aws-future-" + sequence.incrementAndGet());
            thread.setDaemon(true);
            return thread;
        };
        return new ThreadPoolExecutor(
            16, 16, 30, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(400),
            threadFactory,
            new ThreadPoolExecutor.AbortPolicy());
    }

    @Bean(destroyMethod = "close")
    S3AsyncClient s3AsyncClient(ExecutorService awsCompletionExecutor) {
        return S3AsyncClient.builder()
            .region(Region.US_EAST_1)
            .httpClientBuilder(NettyNioAsyncHttpClient.builder()
                .maxConcurrency(128)
                .maxPendingConnectionAcquires(256))
            .asyncConfiguration(config -> config.advancedOption(
                SdkAdvancedAsyncClientOption.FUTURE_COMPLETION_EXECUTOR,
                awsCompletionExecutor))
            .build();
    }
}
~~~

This example registers the executor and S3 client as Spring beans. On shutdown, Spring closes the dependent service client before the executor. A bounded queue surfaces overload via rejections; because this is an internal SDK executor, only customize it after testing how the SDK reports errors when the queue fills and ensuring you have rejection metrics. Never use `CallerRunsPolicy` carelessly, as callbacks could run on I/O threads and block Netty.

An application-created executor must be shut down in the Spring lifecycle after the SDK client has stopped submitting completion tasks. Using `Executors.newFixedThreadPool` with an unbounded queue caps threads while still allowing unbounded task and memory growth.

### 7.4. CompletableFuture lacks Reactive Streams backpressure

AWS async APIs return `CompletableFuture`. A future signals completion of a single operation, but has no demand protocol like `Flux.request(n)`. If a loop invokes the SDK a million times and stores a million futures, the pipeline has already created a million operations/objects before results arrive. You must bound active futures at the application layer with a semaphore, bounded executor, or Reactor `flatMap` concurrency.

When integrating with Reactor, create the future inside the mapper so concurrency is enforced before sending requests:

~~~java
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.core.async.AsyncResponseTransformer;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<ResponseBytes<GetObjectResponse>> download(String bucket, String key) {
    return Mono.defer(() -> Mono.fromFuture(s3.getObject(
            GetObjectRequest.builder().bucket(bucket).key(key).build(),
            AsyncResponseTransformer.toBytes())));
}

Flux<ResponseBytes<GetObjectResponse>> downloads =
    Flux.fromIterable(keys).flatMap(
        key -> download(bucket, key),
        32);
~~~

Concurrency of 32 bounds how many futures are created simultaneously in this pipeline. Never call `download(...).subscribe()` inside a loop.

## 8. Azure SDK for Java: Netty connection provider

Azure SDK for Java uses the `HttpClient` abstraction; Netty is the default HTTP client across Azure SDK libraries when the corresponding dependency is present. The Netty transport can be configured via `ConnectionProvider`.

### 8.1. Bounding connections and pending acquires

~~~java
import java.time.Duration;
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
class AzureAsyncTransportConfiguration {
    @Bean(destroyMethod = "dispose")
    ConnectionProvider azureConnectionProvider() {
        return ConnectionProvider.builder("azure-data")
            .maxConnections(80)
            .pendingAcquireMaxCount(160)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(30))
            .build();
    }

    @Bean
    HttpClient azureHttpClient(ConnectionProvider azureConnectionProvider) {
        return new NettyAsyncHttpClientBuilder()
            .connectionProvider(azureConnectionProvider)
            .build();
    }
}
~~~

- `maxConnections`: maximum connections in the pool per remote address.
- `pendingAcquireMaxCount`: maximum requests waiting to acquire a connection.
- `pendingAcquireTimeout`: maximum wait time.
- `maxIdleTime`: duration a connection may stay idle before closing.

A custom `ConnectionProvider` is an application-owned resource; dispose of it when the ApplicationContext shuts down. Do not create a provider per service request. These transport limits do not replace concurrency limits in the Reactor pipeline.

### 8.2. Setting limits at two layers

~~~java
import java.nio.ByteBuffer;
import reactor.core.publisher.Flux;

Flux<ByteBuffer> chunks = blobAsyncClient
    .downloadStream()
    .limitRate(32);
~~~

Azure Blob `BlobAsyncClientBase.downloadStream()` returns `Flux<ByteBuffer>`; `download()` in some older client APIs is deprecated or returns a response wrapper. `limitRate(32)` paces demand for a single download; if running multiple downloads concurrently, also bound the number of publishers via `flatMap(..., concurrency)`. When reading large streams, bound both concurrent downloads and retained buffer bytes; setting max connections alone is insufficient if the application opens thousands of publishers at once.

The Azure Netty builder offers `disableBufferCopy(true)` to avoid deep-copying response `ByteBuffer`s onto the heap, but Microsoft warns against enabling it if downstream retains buffers after the callback returns: Netty may reclaim/reuse direct buffer memory and corrupt data. Only optimize copies after measuring memory and ensuring consumers process `ByteBuffer` within the permitted lifecycle.

## 9. Spring R2DBC: bounding database connections

With R2DBC, each active connection is a database resource. Reactive code can generate high request concurrency, yet the database still has session, CPU, lock, and I/O limits. Spring Boot exposes R2DBC pool properties when `r2dbc-pool` is on the classpath; the default `max-size` is 10, and `max-acquire-time` has no timeout unless configured.

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      initial-size: 4
      min-idle: 2
      max-size: 24
      max-acquire-time: 2s
      max-create-connection-time: 3s
      max-idle-time: 10m
      max-life-time: 30m
      max-validation-time: 1s
~~~

These numbers are starting points for measurement. With 5 pods and `max-size=24`, total connections opened by the application can reach 120, before counting migrations, admin, monitoring, or other workers. The total limit must stay below the connection budget the database allocates to the application.

### 9.1. Pool acquisition is a queue

Once all 24 connections in the pool are busy, the 25th request can wait for a connection to be returned. If transactions hold connections too long, pending acquires grow. Set `max-acquire-time` so requests do not wait indefinitely; on expiry, return a controlled overload error and let callers retry with backoff if appropriate.

Do not increase pool size to fix slow queries or transactions holding connections during HTTP/Blob calls. Growing the pool can increase query contention on the database and worsen latency. First measure connection hold time, query duration, and lock waits.

### 9.2. Keep transactions short

Never hold a database connection/transaction while:

- Waiting on another HTTP API.
- Downloading/uploading object storage.
- Waiting for a message broker acknowledgment.
- Performing long CPU processing.
- Waiting on user input or timers.

Perform external I/O before/after the transaction if semantics allow; for side effects requiring consistency, use an outbox/saga instead of holding a database connection across the whole workflow.

## 10. Google Cloud Pub/Sub: flow control by messages and bytes

A Pub/Sub subscriber pulls messages from the server and invokes a handler. If the handler processes slower than messages arrive, unacknowledged messages accumulate. Google Cloud Pub/Sub flow control allows capping outstanding message count and total outstanding bytes; when either limit is exceeded, the subscriber pauses pulling until messages are acked/nacked.

### 10.1. Configuring a Java subscriber

~~~java
import com.google.api.gax.batching.FlowControlSettings;
import com.google.api.gax.core.ExecutorProvider;
import com.google.api.gax.core.InstantiatingExecutorProvider;
import com.google.cloud.pubsub.v1.MessageReceiver;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;

FlowControlSettings flowControl = FlowControlSettings.newBuilder()
    .setMaxOutstandingElementCount(500L)
    .setMaxOutstandingRequestBytes(32L * 1024L * 1024L)
    .build();

ExecutorProvider executorProvider =
    InstantiatingExecutorProvider.newBuilder()
        .setExecutorThreadCount(4)
        .build();

MessageReceiver receiver = (message, consumer) -> {
    try {
        processMessage(message);
        consumer.ack();
    } catch (RetryableException ex) {
        consumer.nack();
    }
};

Subscriber subscriber = Subscriber.newBuilder(
        ProjectSubscriptionName.of(projectId, subscriptionId),
        receiver)
    .setFlowControlSettings(flowControl)
    .setParallelPullCount(2)
    .setExecutorProvider(executorProvider)
    .build();

subscriber.startAsync().awaitRunning();
// On application shutdown: subscriber.stopAsync().awaitTerminated();
~~~

500 is the outstanding message limit and 32 MiB is the total outstanding payload limit in this example. Choose based on memory budget and processing duration. Ack only after business processing finishes; acking immediately upon receipt releases flow-control slots too early and risks losing redelivery when a worker fails.

`projectId`, `subscriptionId`, `processMessage`, and `RetryableException` are application-defined values/types. Calling nack can trigger message redelivery; non-retryable errors should follow business policy, such as routing to a dead-letter topic or recording the failure and acking, avoiding infinite redelivery loops.

### 10.2. Thread count and message count are separate limits

The example opens 2 StreamingPull streams and uses a 4-thread executor per stream, yielding up to roughly 8 callback-processing threads under this setup. `setParallelPullCount` sets the stream count; `setExecutorProvider` controls the message-processing executor. These are separate from the 500 outstanding messages and 32 MiB flow-control limits. Raising streams/threads can increase throughput, yet also increases CPU, memory, and database pressure.

If the handler is blocking, do not run it on a WebFlux event-loop thread. If the handler calls a database, handler concurrency should not exceed the connection pool and database capacity. With a 200 ms message processing time and 20 concurrent handlers, theoretical completion is around 100 messages/second before accounting for network, retries, and downstream limits.

### 10.3. Broker backlog vs. client backlog

Flow control bounds messages pulled by the client that are not yet acked. Messages remaining in the Pub/Sub subscription backlog do not occupy application heap. When the backlog grows steadily even though the client is already at its flow-control cap, consumer capacity has fallen behind publish rate over time; scale subscribers or optimize handlers rather than raising outstanding limits indefinitely.

## 11. Calculating buffer memory in bytes

Item-count bounds can mislead when payloads vary in size. 500 messages × 1 KB is completely different from 500 messages × 2 MB.

Rough estimate:

**M ≈ N × S × K**

Where:

- **N:** number of items held concurrently.
- **S:** average or p95 payload size (bytes).
- **K:** copy/buffer multiplier across layers.

For example, 200 payloads × 256 KiB × 2 copies:

**M ≈ 200 × 256 KiB × 2 = 100 MiB**

This estimates payloads only; it excludes object headers, collections, ByteBuf allocators, TLS buffers, decompression, JSON trees, and JVM overhead. Use p95/p99 payload sizes when sizing, not only averages.

### 11.1. Heap and direct memory

Netty can use direct `ByteBuf`s outside the Java heap. Therefore, stable heap usage does not prove total memory is safe. Monitor:

- JVM heap used/committed and GC pauses.
- Direct buffer memory and Netty allocator metrics if enabled.
- Container RSS/cgroup memory.
- Buffer/queue depth and payload bytes.
- Number of requests currently reading/writing streams.

Container limits must accommodate heap, direct memory, metaspace, thread stacks, and native library memory.

### 11.2. Do not multiply buffers unnecessarily

Operations like `collectList()`, `buffer()`, `cache()`, `replay()`, or full-payload serialization can keep extra copies in memory. For large responses, stream chunk by chunk or paginate data instead of accumulating everything into a list. Read bodies and release buffers according to the SDK contract.

## 12. Estimating concurrency and pool size

### 12.1. Little's Law

Average in-flight operations can be estimated with:

**L = λ × W**

Where **λ** is throughput (operations/second), **W** is average resource hold duration (seconds), and **L** is average in-flight operations.

For example, a service handles 80 requests/second and each request holds a database connection for an average of 0.15 seconds:

**L = 80 × 0.15 = 12 connections**

12 is the average, not the pool max. Add headroom for bursts/p95, without exceeding the database's total connection budget.

### 12.2. Identify the bottleneck before adding threads

| Observation | Likely bottleneck | Action |
| --- | --- | --- |
| Event loop busy, high CPU | CPU work or blocking on event loop | Profile, move CPU work to proper scheduler, remove blocking |
| Worker queue growing, threads all busy | Slow blocking dependency | Cap queue, scale capacity carefully, or swap driver |
| Pool active at max, pending growing | Insufficient downstream pool or long hold times | Measure connection hold time, optimize queries, resize pool |
| Pool has idle connections yet requests pend | Concurrency/queue limit at another layer | Check SDK pending acquires, executors, and operator buffers |
| Direct memory climbing | Unreleased ByteBuf/response buffers/streams | Check body lifecycle, cancellation, and buffer sizes |
| 429s/throttling increasing | Cloud quota or provisioned throughput | Reduce concurrency, retry with backoff, raise quota if warranted |

Adding threads when downstream is already saturated usually makes things worse by sending more requests to fight over the same connections/CPU/IOPS.

## 13. Timeouts, cancellation, and retries

Each layer should have its own timeout:

| Timeout | Goal |
| --- | --- |
| Pool acquire timeout | Avoid waiting forever for a connection |
| Connect/TLS timeout | Bound socket open and handshake |
| Request/attempt timeout | Bound a single service attempt |
| Overall API timeout | Bound entire operation including retries |
| Queue wait timeout | Bound time a task sits in a queue |
| Business deadline | Bound end-to-end request/message duration |

When a caller cancels a subscription or times out, check whether the SDK/driver propagates cancellation to the underlying request. Some clients stop waiting for the response while the already-sent request continues on the server. Release buffers/connections and do not assume cancellation rolled back side effects.

Retries:

- Retry only transient errors such as connection resets, throttling, or service unavailable.
- Use exponential backoff and jitter.
- Bound retry count and total deadline.
- Do not retry authentication, authorization, validation, or schema errors.
- Write operations need idempotency keys/conditional writes or state verification before retrying.

Do not retry at every layer simultaneously. SDK, application, gateway, and message broker retries can compound, pushing actual request volume far above incoming traffic.

## 14. Graceful shutdown and in-flight messages

When the application shuts down:

1. Stop accepting new requests or messages.
2. Stop pulling/ingress so backlog stops entering memory.
3. Wait for in-flight operations within a deadline.
4. Ack messages only on successful processing; for unprocessed messages, nack or let the ack deadline expire per policy.
5. Cancel any active publishers/subscriptions.
6. Close application-owned SDK clients, connection pools, executors, and schedulers.

Do not shut down executors before the SDK finishes callbacks; do not dispose of Netty resources while response bodies are still being read. For Pub/Sub, stop the subscriber cleanly in the lifecycle and let handlers finish within the allowed grace period.

## 15. Observing overload and flow control

Monitor these metrics:

| Layer | Metrics |
| --- | --- |
| Reactor | Active subscriptions, requested demand, buffer overflows, scheduler queued/rejected tasks |
| JVM | Live threads, blocked threads, CPU, heap, direct memory, GC pauses |
| AWS SDK | MaxConcurrency, PendingConcurrencyAcquires, concurrency acquire duration, API attempt latency |
| Azure Netty | Active/idle connections, pending acquire count, pending acquire latency, connect timeouts |
| R2DBC | Acquired/allocated/idle connections, pending acquires, acquire latency, query duration |
| Google Pub/Sub | Outstanding message count/bytes, ack latency, backlog age, redeliveries, subscriber throughput |
| Cloud service | 429/throttling, quotas, service latency, connection resets |

Alert on trends and saturation ratios—for example, steadily growing pending queues, active pools pinned at max, buffer overflows, or direct memory approaching container limits. Do not alert only when CPU hits 100%; an async pipeline can exhaust connections or memory while CPU stays low.

## 16. Testing overload and backpressure

### 16.1. Controlled testing

Create a mock downstream with fixed latency, such as 500 ms, and ramp producer rate step by step. Record:

- In-flight operation count.
- Queue/buffer depth and total bytes.
- Active/pending connections.
- Thread count, CPU, heap/direct memory.
- p95/p99 latency, timeouts, and error rates.

Verify that beyond capacity, the application slows down, rejects cleanly, or pushes backlog back to the broker rather than growing memory without bound.

### 16.2. Testing Reactor demand

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(
        Flux.range(1, 100)
            .limitRate(8),
        0)
    .thenRequest(8)
    .expectNextCount(8)
    .thenCancel()
    .verify();
~~~

Example verifying that the publisher is only requested in chunks by the subscriber. For operators with prefetch, upstream demand can exceed items consumed downstream; test actual pipeline behavior rather than looking only at final output.

### 16.3. Testing Pub/Sub

Create a publisher faster than the subscriber, and configure low max outstanding messages and bytes in a test environment. Observe the subscriber pausing pulls when hitting limits, then resuming as handlers ack/nack. Verify message redelivery when a handler fails.

## 17. Common pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Assuming async means no limits needed | Futures/requests/queues pile up | Set finite concurrency and queue bounds |
| Calling `subscribe()` directly in a loop | Unbounded submission, loss of backpressure | Compose publishers or use semaphores/bounded executors |
| Bounding threads only with unbounded queue | Queued tasks pile up and memory grows | Bounded queue + timeout + rejection policy |
| Increasing maxConnections to fix slow queries | More contention on the database | Optimize queries/transactions and calculate connection budget |
| Bounding connections only without bounding publishers | Requests pile up in pending queues | Bound `flatMap` concurrency and SDK pending acquires |
| Buffering by item count only | Large payloads cause OOM | Bound both item count and bytes |
| Using unbounded `onBackpressureBuffer` | Heap/direct memory grows indefinitely | Bounded buffer with explicit overflow policy |
| Blocking event loop with JDBC or `block()` | All requests on that loop stall | Non-blocking driver or `boundedElastic` bridge |
| Acking Pub/Sub before processing finishes | Failed messages are never redelivered | Ack after business processing succeeds |
| Simultaneous retries without jitter | Retry storm, exhausted queues and connections | Backoff, jitter, retry budgets |
| Failing to close response streams | Connections/buffers never freed | Close/cancel streams on all paths |
| Shutting down executors too early | Lost callbacks or failed requests | Drain in-flight work before closing resources |

## 18. Limit design workflow

~~~mermaid
flowchart TD
    A[Measure throughput and payload size] --> B[Measure resource hold time]
    B --> C[Estimate in-flight concurrency]
    C --> D[Choose connection and worker limits]
    D --> E[Set buffer count + bytes + queue timeouts]
    E --> F[Set deadlines, cancellation, and retries]
    F --> G[Load test with slow downstream]
    G --> H{Are queues and memory bounded?}
    H -->|No| I[Lower concurrency or add flow control]
    I --> G
    H -->|Yes| J[Monitor metrics and finalize alerts]
~~~

Before releasing, answer:

1. How many event-loop, worker, and completion threads exist?
2. How many requests can be in flight per instance?
3. Do SDK/HTTP clients bound connections and pending acquires?
4. Do total connections across all pods fit within database/API budgets?
5. Does every buffer have item-count and byte bounds?
6. Will queue overflow block, drop, fail, or offload to a durable broker?
7. Are there timeouts for pool acquire, queue wait, and request deadlines?
8. Does cancellation release downstream resources?
9. Are retries idempotent and budgeted?
10. Can metrics distinguish pool saturation, scheduler saturation, and cloud throttling?

## 19. Hands-on exercises

**Exercise 1 — Reactor concurrency.** Create a Flux of 10,000 IDs calling a mock API with 200 ms latency. Run `flatMap` with concurrency 4, 16, and 64; measure throughput, in-flight count, p95, and memory.

**Exercise 2 — Bounded buffer.** Build a producer emitting 1,000 events/second and a consumer processing 100 events/second. Test a 200-item bounded buffer with ERROR, DROP_OLDEST, and DROP_LATEST; observe dropped events and latency.

**Exercise 3 — AWS async.** Configure S3AsyncClient with `maxConcurrency=32`, 64 pending acquires, and a completion executor with a 100-item queue. Ramp requests until acquire timeouts/rejections occur; explain the corresponding metrics.

**Exercise 4 — Azure Netty.** Use a ConnectionProvider with maxConnections 20, pendingAcquireMaxCount 40, and a 1-second timeout. Trigger many parallel downloads; observe pending acquires and direct memory.

**Exercise 5 — R2DBC pool.** Configure max-size 12 per pod, run 4 pods, and compute maximum total connections. Create transactions holding connections for 1 second and measure pending acquires when load exceeds the pool.

**Exercise 6 — Pub/Sub flow control.** Configure a subscriber for at most 200 messages and 16 MiB outstanding. Slow the handler to 500 ms; observe pull pauses, ack latency, and backlog.

**Exercise 7 — Byte budget.** Compare 500 messages of 1 KiB vs. 500 messages of 1 MiB. Compute minimum payload memory and add serialization/buffer copy multipliers.

**Exercise 8 — Retry storm.** Have downstream return 429 for 5 seconds. Compare immediate retries against exponential backoff + jitter; measure pending queues, request amplification, and p99.

**Exercise 9 — Shutdown.** Stop the application while 50 messages are still processing. Verify ingress stops, handlers finish within the deadline, unacked messages are redelivered, and resources close in the proper order.

## 20. Key takeaways

- Async frees threads while waiting on I/O but does not remove CPU, connection, memory, quota, or processing-time limits.
- Bound **threads**, **in-flight concurrency**, **connections/channels**, and **buffers/queues** separately; never rely on one number to stand in for all.
- Reactor backpressure propagates demand via Reactive Streams; if producers cannot slow down, choose finite buffers, dropping, or failing.
- `flatMap(concurrency, prefetch)` and `limitRate` pace pipelines; `subscribe()` and `block()` can create unbounded demand.
- AWS async uses Netty I/O threads and a separate future-completion executor; configure maxConcurrency, pending acquires, and a bounded executor.
- Azure Netty ConnectionProvider bounds maxConnections, pendingAcquireMaxCount, and pendingAcquireTimeout; you still need publisher limits at the application layer.
- Spring R2DBC pools need explicit max-size and max-acquire-time; sum connections across all pods.
- Google Pub/Sub flow control caps both outstanding message count and bytes; ack only after successful processing.
- Buffer memory depends on item count, payload size, and copies across layers; monitor both heap and direct memory.
- Timeouts, cancellation, retry budgets, and graceful shutdown are integral parts of flow control, not afterthoughts.

## 21. References

- [Spring Framework — WebFlux concurrency model and Reactive Streams backpressure](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html)
- [Project Reactor — Mono.fromFuture and lazy CompletableFuture integration](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Schedulers API and boundedElastic limits](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html)
- [AWS SDK for Java 2.x — Asynchronous programming and executor options](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/asynchronous.html)
- [AWS SDK for Java 2.x — Metrics reference](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/metrics-list.html)
- [Azure SDK for Java — HTTP clients and pipelines](https://learn.microsoft.com/en-us/azure/developer/java/sdk/http-client-pipeline)
- [Azure SDK for Java — Netty HTTP client and connection pool](https://learn.microsoft.com/en-us/java/api/com.azure.core.http.netty.nettyasynchttpclientbuilder?view=azure-java-stable)
- [Azure Storage Blob Java — BlobAsyncClientBase streaming methods](https://learn.microsoft.com/en-us/java/api/com.azure.storage.blob.specialized.blobasyncclientbase?view=azure-java-stable)
- [Spring Boot 3.5 — R2DBC pool properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [R2DBC Pool — Configuration and lifecycle](https://github.com/r2dbc/r2dbc-pool)
- [Google Cloud Pub/Sub — Flow control for subscribers](https://docs.cloud.google.com/pubsub/docs/flow-control)
- [Google Cloud Pub/Sub — Concurrency control for subscribers](https://docs.cloud.google.com/pubsub/docs/concurrency-control)
- [Google Cloud Pub/Sub Java — Subscriber API](https://cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.cloud.pubsub.v1.Subscriber)
