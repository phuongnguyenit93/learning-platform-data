# Designing SDK Client Lifecycles and Connection Reuse

A Java service on Amazon ECS may call Amazon S3 to download documents, DynamoDB to read state, and Amazon SQS to enqueue work. If the application creates a new AWS SDK client for every HTTP request, the system repeatedly initializes HTTP transports, DNS/TLS connections, connection pools, and background resources. The consequences can include **high latency, connection churn, socket/file descriptor exhaustion, elevated CPU usage, and hard-to-control shutdowns**.

AWS SDK for Java 2.x is designed to **create a service client once per required configuration, reuse the client across requests, and close it when the application exits**. Service clients are thread-safe when invoked concurrently from multiple threads; each client holds its Region, credentials provider, endpoint, retry settings, and HTTP transport. Proper lifecycle reuse leverages connection pooling, credential refresh, and internal SDK optimizations.

This lesson belongs to the **AWS SDK for Java** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects Java application design with IAM, Regions/AZs, VPC, compute, storage, databases, integration, and serverless, focusing on availability, observability, resilience, and operational cost.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the lifecycle of an **AWS SDK for Java 2.x service client**, HTTP client, and credentials provider.
2. Distinguish between **thread-safe service clients**, builders, and request/response objects.
3. Design client reuse around the application lifecycle in Java SE, Spring Boot, ECS, EKS, EC2, and Lambda.
4. Choose synchronous **Apache HTTP client** or asynchronous **Netty NIO** transports, understanding resource ownership and closing rules.
5. Reuse HTTP connection pools and configure max connections/concurrency, acquisition timeouts, and idle/TTL settings.
6. Distinguish **API call timeout**, **attempt timeout**, **connection timeout**, **socket/read timeout**, and retries.
7. Use Region/credentials provider chains properly, avoiding static credentials and client-per-request patterns.
8. Distinguish AWS API HTTP connection pools from **JDBC connection pools** to RDS/Aurora.
9. Manage response streams, futures, shutdowns, and errors so connections are not held open too long.
10. Test, monitor, troubleshoot connection leaks/throttling, and optimize total cost.

## 2. Architecture of an AWS SDK Client

A service client such as **S3Client**, **DynamoDbClient**, or **SqsClient** is more than a simple object holding an endpoint. It coordinates several components:

~~~mermaid
flowchart TD
    APP["Java application / request handlers"] --> CLIENT["AWS SDK service client<br/>S3Client / DynamoDbClient"]
    CLIENT --> CONFIG["Region + endpoint + retry<br/>API call timeouts"]
    CLIENT --> CRED["Credentials provider<br/>IAM role / profile / web identity"]
    CLIENT --> SIGN["AWS SigV4 signer"]
    CLIENT --> HTTP["HTTP transport + connection pool"]
    HTTP --> DNS["DNS / TCP / TLS"]
    DNS --> AWS["AWS service endpoint"]
    AWS --> RESP["HTTP response"]
    RESP --> CLIENT
    CLIENT --> APP
~~~

| Component | Responsibility | Lifecycle |
|---|---|---|
| **Service client** | Calls an AWS service API, signs requests, parses responses | Typically lives with the application/container/runtime |
| **HTTP client/transport** | Manages sockets, TLS, connection pools, async event loops | Lives at least as long as the service clients using it |
| **Credentials provider** | Supplies and optionally refreshes AWS credentials | Managed per provider configuration and owner |
| **Region/endpoint configuration** | Selects the AWS Region and request target | Immutable per client after building |
| **Request/response model** | Represents parameters and data for one API call | Per operation |
| **Response stream** | Reads response body, e.g., an S3 object | Must be consumed and closed properly |

**The client is an API coordinator.** A single `S3Client` does not maintain a connection to just one bucket or object; it uses the HTTP transport to send many requests to the corresponding endpoint. The connection pool reuses open TCP/TLS connections whenever the service, endpoint, and transport permit.

### 2.1. Service Clients Are Thread-Safe and Immutable Once Built

Service clients in AWS SDK for Java 2.x are designed to be **thread-safe**. Once built, client configuration does not change; multiple request threads can safely call the same client. This fits Java servers handling many concurrent HTTP requests.

- Create clients at application startup or runtime/container initialization.
- Reuse the same instance for requests sharing the same Region, credentials, and endpoint configuration.
- Do not create a new client inside a controller, repository method, or on every AWS API call.
- Do not share a builder across threads to mutate and rebuild arbitrarily.
- Do not close the client after each request; close it when the application owner shuts down.

**Thread-safe does not mean everything around the client is thread-safe.** Custom caches, mutable request payloads, streams, database connections, or stateful objects inside callbacks must still follow their own concurrency rules.

### 2.2. One Client for Everything or Multiple Clients?

A service client is normally reused for **one stable configuration**. Create separate clients when there is a real reason:

- **Different Regions:** clients are configured per Region; you may need one client per Region.
- **Different AWS accounts/roles:** each credentials provider/assumed role needs an explicit configuration.
- **Different endpoints:** e.g., production AWS endpoint vs. LocalStack test endpoint.
- **Traffic isolation:** a heavy workload should not exhaust a shared pool used by another critical API.
- **Different HTTP/TLS/timeout policies:** distinct latency/SLO targets may call for separate transports.

Never create a client per user or per request just because an object key or table name differs. Those values are **request parameters**, not client configuration.

## 3. Client Lifecycle Aligned with Application Lifecycle

~~~mermaid
flowchart TD
    START["Application startup"] --> CRED["Initialize credentials/Region config"]
    CRED --> HTTP["Create HTTP transport if needed"]
    HTTP --> CLIENTS["Build service clients"]
    CLIENTS --> READY["Application ready"]
    READY --> REQUESTS["Multiple requests reuse client"]
    REQUESTS --> READY
    READY --> STOP["Graceful shutdown"]
    STOP --> DRAIN["Stop accepting new work<br/>wait for in-flight requests/streams"]
    DRAIN --> CLOSE["Close service clients"]
    CLOSE --> TRANSPORT["Close shared HTTP transport<br/>and owned resources"]
~~~

Typical lifecycle:

1. **Startup:** load Region, endpoint, credentials provider, and HTTP transport configurations.
2. **Build:** construct service clients once configuration is ready.
3. **Operate:** share clients across request handlers, workers, and scheduled jobs.
4. **Drain:** on shutdown, stop accepting new work and wait for in-flight operations within a bounded grace period.
5. **Close:** close service clients, shared HTTP clients, and application-owned providers/STS clients in the proper order.

### 3.1. Java SE: try-with-resources for Short-Lived Jobs

For a command-line job or batch process, the client can live within `main`:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.ListBucketsResponse;

public final class ListBucketsJob {
    public static void main(String[] args) {
        Region region = Region.AP_SOUTHEAST_1;

        try (S3Client s3 = S3Client.builder()
                .region(region)
                .build()) {

            ListBucketsResponse response = s3.listBuckets();
            response.buckets().forEach(
                bucket -> System.out.println(bucket.name())
            );
        }
    }
}
~~~

`try-with-resources` closes the client when the job finishes, even on exception. This pattern fits a **single batch run**; never put this block inside a method invoked per HTTP request on a long-running server.

### 3.2. Spring Boot: Managed via Dependency Injection

In Spring Boot, register each client as a **singleton bean** managed by the container:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Configuration
public class AwsClientsConfiguration {

    @Bean(destroyMethod = "close")
    public S3Client s3Client() {
        return S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }

    @Bean(destroyMethod = "close")
    public DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }
}
~~~

Spring singleton beans are shared across components. When the application context shuts down, `destroyMethod = "close"` invokes `close()` on the client. If Region/endpoint/credentials differ across profiles, externalize them via application properties/environment and validate on startup.

### 3.3. AWS Lambda: Initialize Outside the Handler

Lambda can reuse an execution environment across multiple invocations. Place the service client in a **static field** or an object initialized outside the handler:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;

public class ObjectMetadataHandler
        implements RequestHandler<ObjectRequest, ObjectMetadataResult> {

    private static final S3Client S3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();

    @Override
    public ObjectMetadataResult handleRequest(
            ObjectRequest request, Context context) {

        var result = S3.headObject(HeadObjectRequest.builder()
            .bucket(request.bucket())
            .key(request.key())
            .build());

        return new ObjectMetadataResult(
            result.contentLength(),
            result.contentType()
        );
    }
}
~~~

The Lambda execution role is used by the SDK credentials provider chain to fetch temporary credentials. **Do not close `S3Client` after every invocation**, because subsequent invocations in the same execution environment can reuse the client and connection pool. Do not store request- or user-specific data in static fields; client configuration is shared, while request state must remain isolated.

**`ObjectRequest`** and **`ObjectMetadataResult`** in this example are application DTOs, not classes provided by the AWS SDK.

### 3.4. ECS, EKS, and EC2

For long-running applications:

- **ECS/Fargate:** build clients during application startup; the SDK retrieves credentials from the task role provider. Do not use the task execution role in place of the application task role.
- **EKS:** use EKS Pod Identity or IRSA to provide credentials for the Kubernetes service account; keep clients alive for the Pod's lifetime.
- **EC2:** use an instance profile role; the SDK default chain fetches credentials via instance metadata. Enforce IMDSv2 and never hardcode keys.
- **Rolling deployments:** each new container creates its own pool; total connection sizing must account for all replicas/Pods running concurrently during rollouts.

## 4. HTTP Transports in AWS SDK for Java 2.x

Service clients send AWS API requests through an **HTTP implementation**. AWS SDK for Java 2.x provides synchronous and asynchronous options; your choice of transport impacts connection pooling, concurrency, memory, thread usage, and timeout behavior.

| HTTP Implementation | Type | Commonly Used For | Notes |
|---|---|---|---|
| **Apache HTTP client** | Synchronous | `S3Client`, `DynamoDbClient`, `SqsClient`, and sync clients | Connection pool, max connections, socket/connection timeouts |
| **URLConnection HTTP client** | Synchronous | Apps needing simple transport and lightweight dependencies | Lacks Apache-style connection pooling; evaluate carefully for high reuse/concurrency |
| **Netty NIO async HTTP client** | Asynchronous | `S3AsyncClient`, `DynamoDbAsyncClient`, and async clients | Event loops, max concurrency, pending acquires, async read/write |

The SDK can automatically choose a default HTTP implementation matching the service client and classpath dependencies. For production control, **explicitly declare the dependency and transport**, check your exact SDK version, and inspect startup logs/config rather than relying on incidental classpath order.

### 4.1. Apache HTTP Client for Synchronous SDK Clients

Add the Maven dependency matching your AWS SDK version:

~~~xml
<dependency>
  <groupId>software.amazon.awssdk</groupId>
  <artifactId>apache-client</artifactId>
</dependency>
~~~

Example creating a shared transport for S3 and DynamoDB:

~~~java
import java.time.Duration;
import software.amazon.awssdk.http.SdkHttpClient;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class SharedSyncClients implements AutoCloseable {
    private final SdkHttpClient transport;
    private final S3Client s3;
    private final DynamoDbClient dynamoDb;

    public SharedSyncClients() {
        transport = ApacheHttpClient.builder()
            .maxConnections(100)
            .connectionTimeout(Duration.ofSeconds(2))
            .connectionAcquisitionTimeout(Duration.ofSeconds(3))
            .socketTimeout(Duration.ofSeconds(15))
            .connectionMaxIdleTime(Duration.ofSeconds(45))
            .build();

        s3 = S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .httpClient(transport)
            .build();

        dynamoDb = DynamoDbClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .httpClient(transport)
            .build();
    }

    public S3Client s3() {
        return s3;
    }

    public DynamoDbClient dynamoDb() {
        return dynamoDb;
    }

    @Override
    public void close() {
        // Close service clients first, then shared transport.
        dynamoDb.close();
        s3.close();
        transport.close();
    }
}
~~~

In this example, **the transport is built separately and passed via `httpClient(...)`**; the application owns the transport and must close it. Both service clients share one pool; `100` is illustrative and must be sized for actual concurrency and API latency.

### 4.2. Letting the Service Client Manage Its Own HTTP Client

If you only have one service client and do not need to share the transport, use **`httpClientBuilder(...)`**:

~~~java
S3Client s3 = S3Client.builder()
    .region(Region.AP_SOUTHEAST_1)
    .httpClientBuilder(
        ApacheHttpClient.builder()
            .maxConnections(80)
            .connectionTimeout(Duration.ofSeconds(2))
            .socketTimeout(Duration.ofSeconds(15))
    )
    .build();
~~~

With this approach, the service client owns the HTTP implementation built from the builder and manages its lifecycle; closing **`S3Client`** closes the internal resource per SDK ownership rules. This is the simplest option when an HTTP pool does not need to be shared across multiple clients.

**Never pass the same HTTP client instance to multiple owners and let each owner close it.** Decide clearly who owns the transport. When using `httpClientBuilder`, the SDK owns that transport; when passing an instance via **`httpClient(...)`**, the application must manage the shared transport.

### 4.3. Resource Closing Rules When Sharing an HTTP Client

| Configuration Method | Who Owns the HTTP Transport? | How to Close? |
|---|---|---|
| **`httpClientBuilder(builder)`** | SDK service client creates and manages transport | Close the service client |
| **`httpClient(existingInstance)`** | Application supplies an existing transport | Close all service clients first, then close the transport |
| Multiple clients sharing one instance | Application is the shared owner | Close each client on shutdown, close transport exactly once |

In Spring, you can declare the transport as its own bean and inject it into service client beans; Spring manages the dependency graph and destruction order so clients close before the transport. In plain Java, use a single lifecycle owner rather than letting multiple classes call `close` on a shared transport arbitrarily.

## 5. Async Clients and Netty Event Loops

For I/O-heavy workloads where you want to avoid blocking request threads while waiting on AWS, use an async service client. **Netty NIO** uses event loops to manage socket operations; the application receives a **`CompletableFuture`** instead of blocking for a synchronous response.

### 5.1. Configuring the Netty Async Transport

Maven dependency:

~~~xml
<dependency>
  <groupId>software.amazon.awssdk</groupId>
  <artifactId>netty-nio-client</artifactId>
</dependency>
~~~

Example creating a transport and `S3AsyncClient`:

~~~java
import java.time.Duration;
import software.amazon.awssdk.http.async.SdkAsyncHttpClient;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

SdkAsyncHttpClient asyncTransport = NettyNioAsyncHttpClient.builder()
    .maxConcurrency(200)
    .maxPendingConnectionAcquires(1000)
    .connectionTimeout(Duration.ofSeconds(2))
    .readTimeout(Duration.ofSeconds(30))
    .writeTimeout(Duration.ofSeconds(30))
    .build();

S3AsyncClient s3Async = S3AsyncClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .httpClient(asyncTransport)
    .build();
~~~

**`maxConcurrency`** caps concurrent HTTP requests through the client; **`maxPendingConnectionAcquires`** caps how many requests can wait for a connection per Netty configuration. Neither parameter equals Java thread count, Lambda concurrency, or object count. Tune values by measuring throughput, memory, downstream quotas, and latency.

### 5.2. Calling Async APIs Without Blocking the Event Loop

~~~java
import java.util.concurrent.CompletableFuture;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;

public CompletableFuture<Long> getObjectSize(
        S3AsyncClient client, String bucket, String key) {

    return client.headObject(HeadObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .build())
        .thenApply(response -> response.contentLength());
}
~~~

Never call **`join()`** or **`get()`** inside a Netty event loop or callback unnecessarily; doing so blocks the I/O thread. In Spring MVC or blocking frameworks, async APIs only help when the full pipeline is managed appropriately; immediately blocking for the result adds complexity without improving throughput.

### 5.3. Async Clients Also Need a Clear Lifecycle

When an application uses **`httpClient(asyncTransport)`** to share a transport, it must close the async service clients and then close the transport after in-flight operations have drained. Never shut down Netty event loops while futures are still running. If using **`httpClientBuilder(...)`**, the SDK manages the internal transport alongside the service client lifecycle.

**Async does not mean unbounded.** Creating millions of futures concurrently can grow the pending acquire queue and heap memory. Apply backpressure, bounded concurrency, batching/windowing, and cancellation when request deadlines expire.

## 6. Connection Pool Reuse: Why Per-Request Clients Are Expensive

An AWS HTTP request typically resolves DNS, establishes TCP/TLS if no pooled connection exists, computes the SigV4 signature, sends the payload, receives the response, and returns the connection to the pool. With **persistent HTTP connections**, multiple requests reuse open TCP/TLS connections instead of performing fresh handshakes.

~~~mermaid
flowchart LR
    A["Request A"] --> POOL["HTTP connection pool"]
    B["Request B"] --> POOL
    C["Request C"] --> POOL
    POOL --> CONN1["Keep-alive connection 1"]
    POOL --> CONN2["Keep-alive connection 2"]
    CONN1 --> AWS["AWS endpoint"]
    CONN2 --> AWS
    AWS --> POOL
~~~

### 6.1. Two Implementation Approaches

| Approach | Behavior | Consequence |
|---|---|---|
| **Client per request** | Every request builds a service client and usually a new HTTP transport/pool | Connection churn, TLS handshakes, thread/resource overhead, hard to close |
| **Application-scoped client** | Multiple requests share one service client and pool | Reuses connections, stabilizes resource usage, easier to monitor |

**Connection pooling only works when responses are consumed or closed properly.** An unclosed response body or stream keeps the connection busy, forcing other requests to wait on the pool. This is a common reason a small `maxConnections` pool becomes exhausted even under modest traffic.

### 6.2. Share One Pool Across Service Clients or Keep Separate Pools?

You can share a single **`SdkHttpClient`** across compatible synchronous service clients. The upside is fewer pools, threads, and sockets. However, a shared pool introduces **resource contention**: a large S3 download can occupy connections and starve critical DynamoDB or SQS requests.

Separate pools when:

- One service has large payloads/long streams, high traffic, or distinct latency characteristics.
- A lower-priority workload could exhaust the pool needed by a critical API.
- Services require different HTTP, TLS, proxy, or timeout settings.
- You want to isolate blast radius when a transport hits errors or throttling.

Never share a pool merely to save a few lines of code. **Share when workloads are compatible and metrics support it**; otherwise, giving each service client its own transport is a clean, valid design.

## 7. Sizing the Connection Pool and Avoiding Pool Exhaustion

A pool must accommodate real concurrency without growing unbounded. For the sync Apache transport, **`maxConnections`** limits how many connections the pool can allocate. For the Netty async transport, **`maxConcurrency`** limits concurrent requests; requests beyond that threshold wait in the pending acquire queue or fail when limits/timeouts are reached.

### 7.1. Key Parameters to Understand

| Parameter | Meaning | Effect of Too High / Too Low |
|---|---|---|
| **`maxConnections`** (Apache) | Maximum HTTP connections in the pool | Too low: pool waits; too high: excessive sockets/file descriptors and memory |
| **`maxConcurrency`** (Netty) | Maximum concurrent in-flight HTTP requests | Too low: capped throughput; too high: downstream pressure and memory growth |
| **`maxPendingConnectionAcquires`** (Netty) | Maximum requests allowed to queue for a connection | Too high: large wait queues; too low: early rejections during bursts |
| **`connectionAcquisitionTimeout`** | Wait time to lease a connection from the pool | Too short: errors under bursts; too long: request threads stall |
| **`connectionTimeout`** | Time to establish a TCP/TLS connection | Too short: errors on slow networks; too long: startup/requests hang |
| **`socketTimeout / readTimeout`** | Time waiting for data from the server per transport | Too short: aborts valid responses; too long: holds resources on hung servers |
| **`writeTimeout`** (async) | Time waiting to write request data per transport | Too short for slow uploads; too long when client/network stalls |
| **`connectionMaxIdleTime`** | Maximum idle age before a connection is evicted per config | Too short: frequent reconnects; too long: stale connections |
| **`connectionTimeToLive`** | Maximum lifetime of a connection before replacement | Too short: extra TLS handshakes; too long: holds aged connections |

Method names, defaults, and availability depend on the **HTTP implementation and SDK version**. Check the exact API docs for **`ApacheHttpClient.Builder`** or **`NettyNioAsyncHttpClient.Builder`**; never copy Netty settings to Apache assuming identical semantics.

### 7.2. Estimating Concurrency from Throughput

An initial estimate uses Little's Law:

\[
L \approx \lambda \times W
\]

Where:

- **L:** average number of in-flight requests.
- **λ:** throughput in requests/second.
- **W:** average response time in seconds.

For example, with an AWS API throughput of **80 requests/second** and average latency of **0.25 seconds**:

\[
L \approx 80 \times 0.25 = 20
\]

`20` is only the average in-flight count; the actual pool needs headroom for bursts, p95/p99 latency, retries, and multiple service clients. Do not take `L` directly as your final `maxConnections`. Benchmark with realistic workloads and measure **pending acquires, acquisition latency, in-flight requests, and socket usage**.

### 7.3. Aggregate Pool Size Across Scaled Containers

If each ECS task uses an Apache pool of **100 connections** and autoscales to **20 tasks**, the potential ceiling is:

\[
20 \times 100 = 2,000\ \text{HTTP connections}
\]

This is the configured maximum, not necessarily active connections at all times. Still, factor in rolling deployments, autoscaling overlap, and additional clients. AWS services enforce their own throttling and quotas; enlarging client pools does not raise service quotas.

### 7.4. Do Not Hold Response Streams Open Too Long

In S3, response bodies are often consumed via streams. If the application leaves a stream open while performing long CPU or database work, the HTTP connection cannot return to the pool during that window. Read/write in chunks, close streams immediately when finished, and never retain response streams inside long-lived objects.

## 8. Timeouts, Retries, and Deadlines Must Work Together

An API call can fail at multiple layers. Distinguish:

| Timeout | Scope |
|---|---|
| **`connectionAcquisitionTimeout`** | Waiting for a connection from the HTTP pool |
| **`connectionTimeout`** | Establishing the TCP/TLS connection |
| **`socketTimeout/readTimeout`** | Waiting for response data on an established connection |
| **`apiCallAttemptTimeout`** | Bounding total duration of a single SDK attempt |
| **`apiCallTimeout`** | Bounding total duration of the entire API call, including retries |
| **Application/request deadline** | End-to-end deadline by which the application HTTP request or job must finish |

### 8.1. Example API Call Timeout Configuration

~~~java
import java.time.Duration;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

DynamoDbClient dynamoDb = DynamoDbClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .overrideConfiguration(ClientOverrideConfiguration.builder()
        .apiCallTimeout(Duration.ofSeconds(25))
        .apiCallAttemptTimeout(Duration.ofSeconds(8))
        .build())
    .build();
~~~

In this example, **a single attempt** is capped at 8 seconds and the entire API call has at most 25 seconds. Retries and backoff must fit inside the overall deadline; the SDK should not keep retrying after the outer HTTP request has already timed out. In practice, also budget for queueing, serialization, and response processing.

### 8.2. Retries Are Not a Fix for Every Error

The AWS SDK retry strategy can retry transient or throttling errors according to configured retry mode, attempt count, and backoff. However:

- **`AccessDenied`, invalid parameters, and validation errors** require fixing configuration or permissions, not relentless retries.
- **Throttling** calls for exponential backoff and jitter; increasing concurrency usually makes throttling worse.
- **Network timeouts** do not prove the server never executed the request. A write may have succeeded on AWS while the response was lost.
- **Non-idempotent operations** can produce duplicate side effects on retry. Use idempotency tokens/client tokens or application-level deduplication when supported by the API/workflow.
- **Retries consume time and request budget**; size max attempts and API call timeouts to match application deadlines.

### 8.3. Configuring Retries by Workload

| Workload | Design Guidance |
|---|---|
| **Read-only GetItem/HeadObject** | Safe to retry transient errors; use tight deadlines matching SLOs |
| **S3 multipart upload** | Use Transfer Manager/SDK retries and handle abort/cleanup on failure |
| **Create resource** | Use client tokens/idempotency support when provided by the API |
| **SendMessage/payment side effects** | Implement deduplication/application idempotency; never assume timeout means unexecuted |
| **Batch jobs** | Longer deadlines with bounded retries; persist checkpoints and failed items |
| **Interactive HTTP requests** | Never let retries/backoff exceed the client deadline; surface retryable errors cleanly |

Do not give every client a high retry count just to "improve reliability". A downstream outage can amplify into a **retry storm**. Cap concurrency, use backoff with jitter, add application circuit breakers, and alert on retry rates.

## 9. Credentials Providers and Region: Also Part of the Lifecycle

Service clients need **AWS credentials** for SigV4 signing and a **Region** for endpoint selection and signing scope. Never pass static access keys into constructors on every request.

### 9.1. Default Credentials Provider Chain

AWS SDK for Java 2.x supports **`DefaultCredentialsProvider`** to resolve credentials from environment-configured sources, such as:

- Java system properties or environment variables when present.
- Web identity tokens/roles for supported Kubernetes and identity federation setups.
- Shared AWS profiles/credentials files.
- ECS container credentials.
- EC2 instance profile credentials via instance metadata.

Exact order and sources depend on SDK version and configuration. In AWS production, prefer **IAM role credentials** provided by Lambda/ECS/EKS/EC2. Suitable providers cache and automatically refresh temporary credentials; static credentials do not rotate automatically.

### 9.2. Creating a Client Using the Default Chain

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

SqsClient sqs = SqsClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .credentialsProvider(DefaultCredentialsProvider.create())
    .build();
~~~

When running on Lambda or ECS, the provider chain selects credentials from the execution or task role. Ensure the IAM role grants the needed service API permissions; if `AccessDenied` occurs, verify caller identity and policies instead of copying developer access keys into the container.

### 9.3. AssumeRole Credentials Provider

For cross-account access, applications can use **STS AssumeRole** with a credentials provider that refreshes temporary credentials. The provider lives for the application lifecycle; if the application creates its own **`StsClient`** or provider, it must close them according to ownership and never close a shared provider while clients still depend on it.

**Never manually assume a role on every API call.** Use a caching/refreshing provider to avoid unnecessary STS traffic and mid-request credential expiration. Target role trust policies, source principals, external IDs when required, and session durations must all be configured explicitly.

### 9.4. Regions and Multi-Region Clients

A client's Region is fixed once built:

- Use **`Region.AP_SOUTHEAST_1`** or **`Region.of(...)`** from configuration.
- For multiple Regions, create **one client per Region** or a bounded registry with clear lifecycle management.
- Never swap endpoints or Regions arbitrarily per request on the same client.
- Verify the **signing Region** and endpoint when using custom endpoints, FIPS, or dual-stack.
- Never hardcode the wrong environment's Region; inject via configuration and validate at startup.

### 9.5. Custom Endpoints Only for Intentional Purposes

LocalStack or integration tests can use **`endpointOverride(...)`**. In production, an unintended endpoint override can route signed requests to the wrong destination. Isolate test profiles/configs and never construct an SDK client from arbitrary user-supplied URLs.

## 10. AWS SDK HTTP Pool vs. RDS JDBC Pool

These are two completely separate connection pools:

~~~mermaid
flowchart TD
    APP["Java application"]
    APP --> AWSCLIENT["AWS SDK service client"]
    AWSCLIENT --> HTTPPOOL["HTTP connection pool<br/>Apache / Netty"]
    HTTPPOOL --> S3["S3 / DynamoDB / SQS / STS APIs"]
    APP --> JDBC["JDBC DataSource<br/>HikariCP"]
    JDBC --> DBPOOL["Database connection pool"]
    DBPOOL --> RDS["RDS / Aurora TCP sessions"]
    APP --> PROXY["RDS Proxy (optional)"]
    PROXY --> RDS
~~~

| Connection Pool | Connects To | Common Settings | Does Not Replace |
|---|---|---|---|
| **AWS SDK HTTP pool** | AWS service HTTPS endpoints | Apache `maxConnections`, Netty `maxConcurrency` | JDBC pool |
| **JDBC pool (HikariCP)** | RDS/Aurora database TCP endpoint | `maximumPoolSize`, `connectionTimeout`, `idleTimeout`, `maxLifetime` | AWS SDK HTTP pool |
| **RDS Proxy** | Proxies sessions between application and DB | Proxy target group, `maxConnectionsPercent`, idle client timeout | Not an AWS SDK HTTP transport |

An application calling DynamoDB and RDS may simultaneously run an **Apache HTTP pool** for DynamoDB APIs and **HikariCP** for JDBC. Increasing Apache `maxConnections` does not add SQL connections. Increasing Hikari `maximumPoolSize` does not raise S3 throughput.

**Connection leaks** must be diagnosed against the right pool: if Hikari active connections never return to idle, inspect JDBC `Connection`/`ResultSet`/transactions; if Apache pending acquisitions climb, inspect AWS response streams and HTTP pool metrics.

## 11. Managing Response Bodies, Streams, and Futures

An HTTP connection can only be reused after the response is handled according to the transport's semantics. For APIs returning streaming bodies, forgetting to close the stream holds the connection open and gradually exhausts the pool even when the service client itself is reused.

### 11.1. Synchronous S3: Always Close ResponseInputStream

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

public void download(
        S3Client s3, String bucket, String key, Path destination)
        throws IOException {

    GetObjectRequest request = GetObjectRequest.builder()
        .bucket(bucket)
        .key(key)
        .build();

    try (ResponseInputStream<GetObjectResponse> input = s3.getObject(request);
         var output = Files.newOutputStream(destination)) {
        input.transferTo(output);
    }
}
~~~

**`ResponseInputStream`** must be closed even if writing the file fails. Never return a raw stream across layers without clear ownership; if a streaming API must cross layers, explicitly document that the caller owns closing it. For very large files, stream in chunks rather than reading everything into a byte array.

### 11.2. Asynchronous S3: Use Response Transformers

~~~java
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.core.async.AsyncResponseTransformer;

public CompletableFuture<GetObjectResponse> downloadAsync(
        S3AsyncClient s3, String bucket, String key, Path destination) {

    return s3.getObject(
        GetObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .build(),
        AsyncResponseTransformer.toFile(destination)
    );
}
~~~

Response transformers handle file writing and stream completion. With custom **`Publisher`/`Subscriber`** implementations, obey Reactive Streams backpressure, consume or cancel properly, and handle exceptions and cancellation; never abandon a subscriber mid-stream expecting the connection to be freed immediately.

### 11.3. Never Hold Connections Open During Long Business Processing

Common mistake: opening a stream to an object and keeping it open while querying a database or waiting on user input; the HTTP connection remains pinned the entire time. Instead, read in chunks and close the stream before slow tasks if size/design allows, or use **S3 Transfer Manager** for large uploads/downloads with managed concurrency and lifecycle.

### 11.4. Do Not Read Every Object Into Memory

`ResponseTransformer.toBytes()` or reading an entire `InputStream` into a byte array is convenient for small payloads. For large objects, memory allocation and GC pressure can trigger latency spikes or `OutOfMemoryError`. Choose streaming/file transformers and multipart transfers, and bound concurrency to disk, network, and memory capacity.

## 12. Graceful Shutdown and Resource Closing Order

Closing a client while requests are still in flight causes operations to fail. Shutdown should **stop accepting new work, drain in-flight work, and close resources by ownership**.

### 12.1. Reference Shutdown Order

1. Flip readiness to **not ready**, stop accepting new HTTP requests.
2. Stop scheduled jobs, queue polling, and producers generating new AWS requests.
3. Wait for in-flight synchronous calls, futures, streams, and transfers within the termination grace period.
4. Close higher-level components such as Transfer Manager or worker services.
5. Close **service clients**.
6. Close application-owned **shared HTTP transports**.
7. Close application-created credentials providers/STS clients and executor resources according to dependency ownership.

**Close shared resources exactly once.** If multiple clients share a provider or HTTP transport, never let one bean or request handler close it while other consumers are still active.

### 12.2. Spring Boot Bean Dependency Order

When Spring manages a shared HTTP transport and service clients:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.http.SdkHttpClient;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.regions.Region;

@Configuration
public class SharedAwsTransportConfiguration {

    @Bean(destroyMethod = "close")
    SdkHttpClient awsHttpTransport() {
        return ApacheHttpClient.builder()
            .maxConnections(80)
            .build();
    }

    @Bean(destroyMethod = "close")
    S3Client s3Client(SdkHttpClient awsHttpTransport) {
        return S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .httpClient(awsHttpTransport)
            .build();
    }
}
~~~

The service client depends on the transport bean; Spring tracks dependency destruction order so the service client closes before its transport dependency. Because the transport was passed via **`httpClient(...)`**, the application context must manage and close the transport bean as well. If clients are built with **`httpClientBuilder(...)`**, the service client manages its internal transport lifecycle.

### 12.3. Lambda Should Not Rely on Shutdown Hooks to Persist Data

Lambda execution environments can be reused or terminated by the platform. Static clients for reuse are great, but never rely on JVM shutdown hooks to flush critical transactions or guarantee an async future completes. Finish required work before returning from the handler, or use queues/workflows for long-running processing.

## 13. Observability: Knowing Whether Pools Are Healthy or Congested

Seeing HTTP 200 responses is not enough to know a connection pool is sized properly. Monitor both **application-level latency** and **SDK/HTTP-level behavior**.

### 13.1. Essential Metrics

| Metric/Signal | Question Answered | Bad Symptom |
|---|---|---|
| **API call duration p50/p95/p99** | How slow are AWS operations? | p99 rises while app CPU stays low |
| **API attempt duration** | How long does a single attempt take? | Network or service timeouts |
| **Retry count / throttling count** | How often is the SDK retrying? | Retry storm or quota exhaustion |
| **Connection acquisition latency** | How long do requests wait for the pool? | Undersized pool or unclosed response streams |
| **Pending connection acquires** | How many requests are queued? | Excessive bursts or concurrency |
| **Connection timeout/socket timeout** | Are there network/endpoint/slow-response errors? | DNS/TLS/routing/service latency |
| **In-flight requests / max concurrency** | Is the pool frequently hitting its ceiling? | Saturation |
| **Response stream duration** | How long are bodies held open? | Streams pinning connections too long |
| **HTTP status/service exceptions** | What errors is AWS returning? | `AccessDenied`, throttling, 5xx |
| **Credential refresh failures** | Can the provider fetch temporary credentials? | Expired credentials or metadata issues |

### 13.2. AWS SDK Metrics and Application Metrics

AWS SDK for Java 2.x provides a **metrics publishing SPI** and execution interceptors to observe API calls depending on SDK capabilities and version. You can integrate a metrics publisher or bridge into your existing observability stack. Applications should also measure:

- Duration from when the handler calls the client until a response returns.
- Pool wait/queueing time when exposed by transport metrics.
- Concurrent operations per service.
- Retry/error counts by operation and AWS error code.
- Payload sizes and streaming durations by bucket/service without recording sensitive contents.

Never log AWS `Authorization` headers, SigV4 signatures, access keys, session tokens, sensitive request bodies, or privileged presigned URLs. On errors, record the **AWS request ID**/extended request ID from response metadata alongside a redacted correlation ID.

### 13.3. Correlating Application and AWS Service Metrics

If DynamoDB API latency spikes, compare:

1. Application p95/p99 and SDK attempts/retries.
2. HTTP connection acquisition times and pending counts.
3. DynamoDB throttling, consumed capacity, and service latency metrics.
4. VPC DNS/TLS/network paths if clients run in private subnets.

If pool acquisition latency is high while DynamoDB service latency is normal, the bottleneck is likely in the client pool or a stream leak. If the pool has spare capacity while the service returns throttling, adjust workload patterns, partitions, or table capacity rather than simply raising `maxConnections`.

## 14. Dependency Management and Version Consistency

AWS SDK for Java 2.x consists of many service modules and HTTP implementations. Use the **AWS SDK BOM** to keep modules on the same version and prevent mixing mismatched artifacts that cause class-loading failures or inconsistent behavior.

### 14.1. Illustrative Maven BOM

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>software.amazon.awssdk</groupId>
      <artifactId>bom</artifactId>
      <version>REPLACE_WITH_AWS_SDK_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>apache-client</artifactId>
  </dependency>
</dependencies>
~~~

Replace **`REPLACE_WITH_AWS_SDK_VERSION`** with an SDK v2 version tested and managed by your organization. For async clients, add **`netty-nio-client`**; for the STS assume-role provider, add **`sts`**. Never add unused service modules "just in case we need them later".

### 14.2. Never Mix AWS SDK v1 and v2

SDK v1 uses package **`com.amazonaws...`**; SDK v2 uses **`software.amazon.awssdk...`**. An application undergoing migration may temporarily contain both, but keep their dependencies, credentials providers, client lifecycles, and logging strictly separated. Never pass SDK v1 objects, requests, or credentials providers into v2 APIs or assume compatibility.

### 14.3. Tracking Versions and Security Updates

- Use a centralized BOM or dependency management.
- Update SDK v2 on a tested schedule, especially for security fixes and retry/HTTP behavior changes.
- Verify Java runtime compatibility, driver/transport versions, and dependency conflicts.
- Do not force versions of **netty** or **Apache HTTP components** away from what the corresponding SDK module requires without compatibility testing.
- Record the SDK version in build artifacts/SBOMs for incident traceability.

## 15. Testing Lifecycle and Connection Reuse

Client reuse is a runtime behavior that must be verified through **application architecture and load tests**, not merely by asserting a field is `static`.

### 15.1. Unit Tests: Inject the Service Client

Let business services accept **`S3Client`** or **`DynamoDbClient`** via constructor injection so tests can mock the client interface. Avoid constructing real AWS clients in every unit test unnecessarily. Constructor injection also exposes code that tries to instantiate clients deep inside business methods instead of using managed dependencies.

~~~java
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;

class ObjectServiceTest {
    @Test
    void readsMetadataFromInjectedClient() {
        S3Client s3 = mock(S3Client.class);
        when(s3.headObject(any(HeadObjectRequest.class)))
            .thenReturn(HeadObjectResponse.builder()
                .contentLength(42L)
                .contentType("text/plain")
                .build());

        ObjectService service = new ObjectService(s3);
        var result = service.getMetadata("docs", "guide.txt");

        // Assert result against application DTO.
        verify(s3, times(1)).headObject(any(HeadObjectRequest.class));
    }
}
~~~

**`ObjectService`** and its DTO are illustrative application classes. Unit tests focus on business behavior; do not try to test Apache's internal connection pool using a mocked service client.

### 15.2. Integration Tests: LocalStack or an AWS Test Account

Integration tests can use **LocalStack** or a dedicated AWS account with disposable resources. LocalStack example:

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client localS3 = S3Client.builder()
    .region(Region.US_EAST_1)
    .endpointOverride(URI.create("http://localhost:4566"))
    .credentialsProvider(
        StaticCredentialsProvider.create(
            AwsBasicCredentials.create("test", "test")
        )
    )
    .build();
~~~

Static test credentials and localhost endpoints are **strictly for test environments**. Never reuse this snippet in production. When testing against real AWS, create uniquely named buckets/tables/queues, clean up resources, and control costs.

### 15.3. Meaningful Connection Reuse Tests

To prove pooling works:

1. Build **one service client** and execute many API calls to the same AWS endpoint.
2. Measure client initialization time, p50/p95/p99 latency, connection acquisitions, and retries.
3. Compare against a client-per-request baseline inside a **separate test harness**, never as a production pattern.
4. Test concurrency bursts, response streaming, and request cancellation.
5. Inspect open sockets/threads, pool saturation, idle connections, and memory.
6. Test shutdown while requests and futures are still in flight.

Do not declare reuse successful simply because API call count exceeds client count. Verify that the underlying transport is actually shared and response bodies are closed.

### 15.4. Testing Failure Scenarios

- AWS API returning throttling or 5xx errors.
- DNS lookup or TLS handshake failures.
- Expired credentials or denied `AssumeRole` calls.
- HTTP pool exhaustion or pending acquire timeouts.
- S3 streams cancelled mid-transfer by clients.
- Async futures completing after application shutdown begins.
- ECS rolling deployments creating multiple concurrent pools.
- Differences in latency between Lambda cold starts and warm invocations.

## 16. Security Across the Client Lifecycle

### 16.1. Use IAM Roles and Credentials Providers

- Prefer **Lambda execution roles, ECS task roles, EKS Pod Identity/IRSA, and EC2 instance profiles**.
- Never commit access keys or secret keys into Git, Docker images, Java properties, or CI logs.
- Avoid static credentials providers in production unless governed by a strictly controlled exception.
- For `AssumeRole`, use a refreshing credentials provider; control trust policies, session durations, and external IDs as required.
- Grant IAM permissions scoped to minimal **service actions and resource ARNs**.

### 16.2. Protect TLS and Endpoints

- Use default HTTPS AWS endpoints and keep certificate verification enabled.
- Never disable hostname verification or trust all certificates to bypass transient errors.
- Never let user requests control **`endpointOverride`**.
- For VPC endpoints and private networking, verify DNS and endpoint policies instead of opening public access.
- Never retain presigned URLs longer than necessary; they act as bearer credentials during their validity window.

### 16.3. Logging and Request Metadata

Never log:

- Access key IDs, secret access keys, or session tokens.
- `Authorization` headers, SigV4 signatures, IAM database tokens, or secrets.
- Sensitive payloads, full presigned URLs, or request bodies with PII.
- Response stream contents solely for debugging.

You may log **AWS request IDs**, service operations, durations, retry counts, error codes, and redacted correlation IDs. If enabling wire-level logging for diagnostics, restrict it to test/staging, keep it brief, and protect the logs.

### 16.4. Client Lifecycle Is a Security Concern

A client or transport kept alive long after credentials or role configurations change may continue using stale providers or settings unexpectedly. Conversely, recreating clients constantly expands configuration surface area and causes resource leaks. Centralized lifecycle management keeps **credential refreshes, endpoint policies, TLS, and auditing** consistent.

## 17. Anti-Patterns and Fixes

| Anti-Pattern | Harm | Fix |
|---|---|---|
| Creating `S3Client` inside every controller method | Client and pool churn | Inject an application-scoped singleton |
| Calling `close()` after every API call | Breaks concurrent requests using the client | Close only at application shutdown |
| Never closing a shared HTTP transport | Threads and sockets linger after shutdown | Have one owner close it after service clients |
| Sharing a transport across mismatched workloads | One service monopolizes the pool | Split pools by SLO and traffic profile |
| Setting `maxConnections` astronomically high | Exhausts sockets and increases downstream pressure | Load test and size around in-flight requests |
| Unbounded `maxConcurrency` on Netty workloads | Pending futures and heap memory grow unchecked | Add backpressure and bounded concurrency |
| Forgetting to close S3 response streams | Pins pool connections indefinitely | Use `try-with-resources` or transformers |
| Calling `join()` inside event loops | Blocks I/O threads | Compose `CompletableFuture` without blocking |
| Using static access keys | Leaks credentials and lacks automatic refresh | Use IAM roles and default provider chain |
| Manually generating tokens/credentials per request | STS/API overhead and race conditions | Use caching/refreshing credentials providers |
| Using one client across all Regions/roles | Wrong signing Region or permissions | Dedicated client per stable configuration |
| Retrying all errors infinitely | Retry storms and duplicate writes | Bounded retries, backoff, idempotency |
| Confusing SDK HTTP pool with HikariCP | Mismatched tuning across two connection types | Manage AWS HTTP and JDBC pools separately |
| Logging full requests/responses | Exposes secrets and PII | Log redacted metadata |
| Closing clients before draining futures | Fails in-flight requests | Graceful shutdown with draining |

## 18. Runbook for Client and Connection Pool Failures

~~~mermaid
flowchart TD
    A["AWS API call slow or failing"] --> B{"At which step did it fail?"}
    B -->|"Pool acquire"| POOL["maxConnections/maxConcurrency<br/>pending acquires, stream close"]
    B -->|"TCP/TLS connect"| NET["DNS, route, proxy, SG/NACL,<br/>connectionTimeout, CA"]
    B -->|"Credentials/signing"| CRED["Credentials provider refresh,<br/>Region, clock, SigV4"]
    B -->|"Service response"| SVC["AWS error code, IAM policy,<br/>quota, retry strategy"]
    POOL --> FIX["Fix root cause<br/>and re-test"]
    NET --> FIX
    CRED --> FIX
    SVC --> FIX
    FIX --> VERIFY["Measure p95/p99, retry rate,<br/>pool usage, and shutdown"]
~~~

### 18.1. Common Symptoms

| Symptom | Likely Cause | Check |
|---|---|---|
| **`SdkClientException: Unable to execute HTTP request`** | HTTP transport wrapper around DNS/TLS/socket/pool error | Inspect the full cause chain instead of stopping at the outer exception |
| **`Timeout waiting for connection from pool`** | Exhausted pool, unclosed streams, low `maxConnections`, or bursts | Pending acquires, active connections, response stream lifecycle |
| **`Connection pool shut down`** | Client/transport closed while code still uses it | Ownership, shutdown order, per-request `close()` calls |
| **`Too many open files / sockets`** | Clients/transports created repeatedly or never closed | Client instance counts, threads, sockets, and OS process limits |
| **`Connection reset / stale connection`** | Network idle timeouts, endpoint closed connection, TTL too long | Keep-alive, idle time, connection TTL, retries |
| **`UnknownHostException`** | Wrong DNS resolver, endpoint, Region, or VPC DNS | Endpoint hostname, VPC DNS, resolver/routes |
| **`SSLHandshakeException`** | Truststore/CA, TLS config, proxy, or clock skew | Certificate chain, hostname, TLS interception |
| **`ExpiredToken / InvalidToken`** | Temporary credentials expired, non-refreshing provider, stale static creds | Caller identity, provider chain, STS/role session |
| **`SignatureDoesNotMatch`** | Inconsistent Region, endpoint, clock, headers, or signed payload | Region, custom endpoint, system time, request signing |
| **`AccessDeniedException`** | IAM identity/resource policy, SCP, or endpoint policy | Caller ARN, action, resource, explicit `Deny` |
| **`ThrottlingException / 429`** | Exceeded service quotas or burst limits | Retry counts, service metrics, concurrency, quotas |
| **Async pending acquires keep growing** | Producer generates futures faster than consumer/service handles them | Backpressure, `maxConcurrency`, pending queue, cancellation |
| **Lambda warm invocations get progressively slower** | Unreleased pools/streams or growing static state | Memory, connection reuse, stream closure, background tasks |
| **Shutdown hangs** | In-flight requests/futures or threads not terminating | Drain timeout, executors, transport ownership |

### 18.2. Investigation Order

1. Capture **service operation, AWS request ID, Region, caller role, timestamp, and error code**; redact credentials and payloads.
2. Read the entire **cause chain** to separate the SDK wrapper from underlying HTTP/TLS/DNS errors.
3. For pool acquisition timeouts, inspect response streams, in-flight calls, `maxConnections`/`maxConcurrency`, and pending acquires.
4. For connect timeouts, inspect DNS, VPC routes, proxies, security groups, TLS handshakes, and endpoints.
5. For signature/credential errors, verify the credentials provider, refresh behavior, Region, and clock sync.
6. If the service returns `AccessDenied` or throttling, examine IAM/resource policies/quotas; never enlarge the pool to fix permissions.
7. Reproduce and fix in staging, testing normal traffic, bursts, retries, and shutdown.

### 18.3. Connection Pool Exhausted While the Service Is Fast

A telltale sign is **rising application acquisition latency** while AWS service latency stays low and API request counts remain flat. Look for:

- Unclosed S3 response streams.
- Requests awaiting futures that the caller never consumes.
- A shared pool monopolized by one heavy service workload.
- Per-request clients creating unclosed pools.
- `maxConnections` set far below actual concurrency.

Raising `maxConnections` may relieve queueing briefly, but if the root cause is a stream leak, a larger pool only delays the outage.

## 19. Cost and Efficiency of Connection Reuse

**AWS SDK clients and connection pools do not incur a separate AWS billing line item just for existing.** Actual AWS costs come from API requests, service capacity/storage, data transfer, retries, logs/metrics, and the compute/networking your application consumes. Optimizing client lifecycle reduces application overhead and can lower retries/churn, but **does not make valid API requests free**.

| Component | Cost Impact |
|---|---|
| **Client per request** | Increases CPU, TLS handshakes, memory, threads, and autoscaling pressure; indirectly raises compute cost |
| **Connection reuse** | Cuts handshakes/churn and latency; API requests and service usage still bill normally |
| **Retries** | Generate extra API attempts, potentially increasing request charges and downstream load |
| **Oversized pool** | Consumes extra sockets/memory, potentially driving higher compute/scaling costs |
| **Undersized pool** | Causes queueing, timeouts, and retries, reducing throughput |
| **Logging/metrics** | CloudWatch ingestion, storage, and queries incur charges under current pricing |
| **VPC endpoints/NAT** | May incur hourly, data processing, or NAT charges depending on architecture |
| **Lambda cold starts** | Building clients per execution environment adds init time; reuse trims work across warm invocations |

### 19.1. Measuring Before and After

Hold workload, Region/service quotas, payload size, and concurrency constant; compare:

- p50/p95/p99 latency for API operations and end-to-end handlers.
- Client initialization time and open socket/thread counts.
- HTTP pool acquisition latency and pending queue depth.
- TLS connection churn, retries, throttling, and error rates.
- Java process CPU/memory, GC pauses, and container scaling.
- AWS request counts and per-service cost allocation.

Do not claim client reuse directly cuts AWS API request charges if the number of logical API calls stays unchanged. The primary gains are **lower latency, lower app resource footprint, fewer churn-induced errors, and more predictable scaling**.

## 20. Production Design Patterns

### 20.1. Lifecycle Selection Checklist

| Environment | Recommended Starting Pattern | Points to Verify |
|---|---|---|
| **One-shot CLI/batch** | `try-with-resources` around service client | Closes when job exits |
| **Spring Boot/ECS/EKS/EC2** | Singleton bean / application-scoped client | Graceful shutdown and pool sizing |
| **AWS Lambda** | Static/application-level client outside handler | Never close per invocation; bound concurrency |
| **Async high-throughput** | Async client + shared/owned Netty transport | Backpressure, `maxConcurrency`, event loop lifecycle |
| **Multi-Region** | Dedicated client per Region | Endpoint/signing Region and failover |
| **Cross-account** | Client with appropriate credentials provider/assumed role | STS refresh, trust policy, lifecycle |
| **S3 large objects** | S3 client/Transfer Manager and streaming | Multipart concurrency, stream cleanup, memory/disk |
| **AWS APIs + RDS** | Separate SDK HTTP pool and JDBC pool | Never confuse `maxConnections` with DB pool size |

### 20.2. Example Property-Driven Configuration

You do not need to hardcode numbers inside Java classes. Inject configuration such as:

~~~yaml
app:
  aws:
    region: ap-southeast-1
    http:
      max-connections: 80
      connection-timeout-ms: 2000
      acquisition-timeout-ms: 3000
      socket-timeout-ms: 15000
    api:
      call-timeout-ms: 25000
      attempt-timeout-ms: 8000
~~~

This is an **illustrative application config**, not a built-in property schema automatically read by the AWS SDK. The application must bind and validate these values and pass them into SDK builders. Enforce min/max bounds so environment overrides cannot size pools beyond infrastructure limits.

### 20.3. Implementation Rules

1. **One service client per stable configuration**; never build inside the hot path.
2. **Thread-safe clients are shared**, while request data and streams are managed individually.
3. **HTTP transports have explicit owners**; close shared instances exactly once.
4. **Connection pools are bounded** and sized to real concurrency.
5. **Overall timeouts encompass retries**, aligned with application deadlines.
6. **Credentials providers support refresh** and rely on IAM roles on AWS.
7. **Response streams and futures must be completed, cancelled, or closed.**
8. **Drain before closing on shutdown**; never close a transport with active requests.
9. **HTTP pools and JDBC pools are distinct**; measure and tune them separately.
10. **Observability captures request IDs, retries, pool waits, and p95/p99** without logging secrets.

## 21. Scenario Exercises

### Scenario A — S3Client Built Inside Every REST Request

A Spring Boot controller calls S3. A developer runs **`S3Client.builder().build()`** on every upload and closes it afterward. As traffic grows, latency and TCP/TLS connection counts surge.

**Question:** How should the lifecycle change?

**Hint:** Inject a singleton **`S3Client` bean** and let Spring close it on application shutdown. Measure connection reuse, pool sizing, and upload concurrency. For large uploads, evaluate Transfer Manager and multipart concurrency.

### Scenario B — Shared HTTP Transport Closed Too Early

`S3Client` and `DynamoDbClient` share one Apache HTTP client. A repository calls **`s3.close()`** after a request, and DynamoDB starts failing with **`Connection pool shut down`**.

**Question:** Where does ownership belong?

**Hint:** The transport is a shared application resource; request handlers do not own it. Never close service clients or transports on the hot path. Let the application lifecycle owner close service clients and the transport in order at shutdown.

### Scenario C — S3 Downloads Starve the Pool

A method returns **`ResponseInputStream`** to a controller. The controller writes response headers and slowly streams bytes to internet clients while the AWS HTTP pool only allows 20 connections.

**Question:** Why are other S3 requests waiting?

**Hint:** The response stream is not consumed and closed quickly, keeping connections pinned. Stream downloads with appropriate backpressure and capacity, or stage files/objects before serving from a delivery layer; always close streams when clients cancel or disconnect.

### Scenario D — Async Client Has Tens of Thousands of Pending Futures

A worker submits 50,000 futures concurrently while Netty `maxConcurrency` is 100. Pending acquires climb, heap usage spikes, and shutdown hangs.

**Question:** Should `maxConcurrency` be raised to 50,000?

**Hint:** First apply **bounded concurrency/backpressure**, batching/windowing, and cancellation. Size `maxConcurrency` around service quotas, memory, event loops, and downstream limits. Blindly raising the cap can overwhelm the service and does not fix an unbounded future producer.

### Scenario E — SDK Client Succeeds Then Fails After One Hour

An application uses static AWS access/secret keys that expire or rotate inside a `StaticCredentialsProvider`.

**Question:** Why does reusing the client not refresh credentials?

**Hint:** Client reuse does not replace credential lifecycle management. Static providers hold fixed credentials; use IAM roles with `DefaultCredentialsProvider` or a refreshing STS assume-role provider. Verify caller identity and trust policies.

### Scenario F — Raising Pool Size Does Not Stop Throttling

DynamoDB returns `ThrottlingException`. A developer increases Apache `maxConnections` from 50 to 500, and errors worsen.

**Question:** What was misunderstood?

**Hint:** The HTTP pool only controls client concurrency—it does not raise DynamoDB table or partition quotas. Smooth bursts, retry with backoff/jitter, and investigate hot partitions, provisioned/On-Demand capacity, and access patterns.

### Scenario G — API Timeouts Despite Fast Service Responses

The application sees 5-second p99 latency while CloudWatch shows low AWS service latency. SDK pool pending acquires climb and S3 streams are processed by a slow worker.

**Question:** Where is the bottleneck?

**Hint:** Measure connection acquisition latency, active/pending pool counts, stream lifetimes, and shared pool contention. Split pools or adjust streaming and concurrency; never raise timeouts to hide pool starvation.

### Scenario H — Lambda Client Closed After Every Invocation

A handler creates a client inside the method and closes it in a `finally` block. Back-to-back warm invocations keep reinitializing the transport.

**Question:** What is the proper lifecycle for Lambda?

**Hint:** Construct the client outside the handler in a static field to reuse across invocations. Never store request-specific state in static fields; finish async work before returning; never rely on shutdown hooks for critical persistence.

### Scenario I — Confusing AWS HTTP Pool with RDS Connection Pool

An application calls both S3 and Aurora. The team raises Apache `maxConnections` to fix HikariCP **`Connection is not available`** errors.

**Question:** Why does this not help?

**Hint:** The Apache pool serves AWS service HTTPS requests; HikariCP manages JDBC database sessions. Investigate DB `max_connections`, transaction leaks, JDBC pool sizing, and RDS Proxy separately.

### Scenario J — Shutdown Drops In-Flight Requests

A container receives `SIGTERM` and immediately closes `S3Client` and the Netty transport while upload futures are still pending.

**Question:** What shutdown order is safer?

**Hint:** Mark readiness not ready, stop producers/consumers, drain in-flight requests/futures/transfers within the grace period, close higher-level components and service clients, and finally close application-owned shared HTTP transports and providers.

## 22. Production Checklist

- [ ] Adopted **AWS SDK for Java 2.x** with modules aligned via a unified BOM/version.
- [ ] Service clients are instantiated per application lifecycle, never per request.
- [ ] Client configs are defined cleanly per Region, credentials provider, endpoint, and role.
- [ ] Service clients are shared thread-safely; request-specific state is kept out of shared mutable fields.
- [ ] Transport choice (sync Apache/URLConnection vs. async Netty) matches workload and compatibility.
- [ ] HTTP transport ownership is explicit: SDK-owned via builder or application-owned via shared instance.
- [ ] Shared HTTP transports are closed exactly once after all dependent service clients close.
- [ ] `maxConnections`/`maxConcurrency`, pending acquires, and pool acquisition timeouts are sized appropriately.
- [ ] Connection/read/socket/write timeouts, idle time, and connection TTL are configured per transport.
- [ ] API call/attempt timeouts fit deadlines; retries are bounded with backoff and idempotency.
- [ ] IAM roles and the credentials provider chain are used; no hardcoded access keys exist.
- [ ] Credentials providers and STS clients have proper lifecycles and refresh behavior.
- [ ] Region/endpoint are configured per environment; `endpointOverride` is strictly limited to intentional test setups.
- [ ] S3 response streams, async futures, and transfer managers are consumed, closed, or cancelled properly.
- [ ] AWS SDK HTTP pools and JDBC/HikariCP/RDS Proxy pools are sized and monitored independently.
- [ ] Graceful shutdown stops new work, drains in-flight work, and closes resources in dependency order.
- [ ] Metrics cover p95/p99 latency, retries/throttling, pool acquisition, pending requests, and credential errors.
- [ ] Logs capture AWS request IDs/correlation IDs while redacting tokens, signatures, credentials, and sensitive payloads.
- [ ] Load tests validate bursts, long streams, throttling, failover, credential refresh, and shutdown.
- [ ] Integration tests run against LocalStack/AWS test accounts with test endpoints/credentials isolated from production.
- [ ] Compute, network, logging, API request costs, and retry amplification have been evaluated.

## 23. Key Takeaways

**AWS SDK for Java 2.x service clients are thread-safe and meant to be reused across the application lifecycle**: build during startup/runtime initialization, share across requests, and close when the owner shuts down. **Client per request** creates connection churn and resource overhead; **client per application/configuration** enables HTTP connection pooling, credential refreshes, and clean shutdowns.

HTTP transports require clear ownership: use **`httpClientBuilder(...)`** when the SDK service client manages its internal transport; use **`httpClient(existingInstance)`** when the application shares a transport and closes it after the service clients. Size **`maxConnections`/`maxConcurrency`, pending acquires, connection/read timeouts, API call timeouts, and retries** to match workload, deadlines, and quotas. Always close **S3 response streams**, manage async futures/backpressure, and drain before closing.

Finally, keep **AWS SDK HTTP connection pools** distinct from **JDBC pools to RDS/Aurora**; use IAM roles and credentials providers instead of static keys, preserve TLS verification, monitor pool metrics, and never log secrets. Client reuse is a cornerstone of reliability and performance, though it does not raise service quotas or replace idempotency, IAM least privilege, and database connection management.

### Official AWS Reference Documentation

- [AWS SDK for Java 2.x best practices](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html) — reusing clients, connection pools, and resource management.
- [HTTP configuration](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration.html) — choosing an HTTP implementation.
- [Apache HTTP client configuration](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-apache.html) — sync connection pools and timeouts.
- [Netty NIO async HTTP client configuration](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-netty.html) — concurrency, pending acquires, and async transport.
- [AWS credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — credentials resolution.
- [AWS Region selection](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/region-selection.html) — Region provider chain and explicit Region.
- [Configure service client settings](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/client-configuration.html) — retries, API call timeouts, and overrides.
- [Retry strategies](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html) — retry modes and strategy configuration.
- [Asynchronous programming](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/asynchronous.html) — CompletableFuture and Netty.
- [SDK metrics](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/metrics.html) — metrics publishing SPI.
- [Using the SDK with AWS Lambda](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/lambda.html) — client initialization and runtime reuse.
- [AWS SDK for Java 2.x GitHub](https://github.com/aws/aws-sdk-java-v2) — releases, source, and compatibility.



