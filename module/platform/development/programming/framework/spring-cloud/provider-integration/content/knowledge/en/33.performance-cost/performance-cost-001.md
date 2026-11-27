# Client Reuse, Connection Pools, and HTTP Transports

A Spring Boot application can send thousands of requests per minute to S3, Azure Blob Storage, Cosmos DB, PostgreSQL, Pub/Sub, or REST APIs. If every request creates a new SDK client or HTTP client, the application repeatedly initializes credentials, DNS lookups, TCP/TLS handshakes, and connection pools. The result is higher latency, wasted CPU and memory, rapidly growing socket counts, and a high risk of connection exhaustion or ephemeral port exhaustion.

The standard design for server workloads is to **create a long-lived client per connection configuration, reuse that client across requests, and manage connection pools along the application lifecycle**. AWS SDK for Java 2.x, Azure SDK for Java, Google Cloud Java libraries, and Spring Boot all support this pattern. However, each SDK has its own transport-sharing boundaries and resource-closing rules; you should not apply one identical recipe across all three clouds.

This lesson belongs to the **Performance and Cost** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries, including identity/permissions configuration, storage, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on client reuse, HTTP transports, connection pools, and resource lifecycles in production.

## 1. Learning outcomes

After this lesson, you will be able to:

- Distinguish between service clients, HTTP transports, connection pools, sockets, and credential providers.
- Explain why SDK clients should be long-lived and are typically shared across multiple threads.
- Register AWS, Azure, and Google Cloud clients as Spring singleton beans.
- Distinguish whether a pool lives inside the service client or in a shared HTTP transport.
- Configure Apache 5, Netty, Azure HTTP pipelines, and Google gRPC channels for your workload.
- Choose pool size, concurrency, pending queue, and timeout settings based on real traffic.
- Manage response streams, connection reuse, DNS, keepalive, and shutdown.
- Measure connection acquisition latency, pool saturation, request latency, and resource cost.

## 2. Resource layers in a request

When calling a cloud service through an SDK, an application typically goes through multiple layers:

~~~mermaid
flowchart TD
    A[Spring service / application request] --> B[Cloud SDK service client]
    B --> C[Credential provider]
    B --> D[HTTP pipeline / policies]
    D --> E[HTTP transport]
    E --> F[Connection pool]
    F --> G[TCP socket / TLS session]
    G --> H[Managed cloud endpoint]
~~~

- **Service client:** High-level API such as `S3Client`, `BlobServiceClient`, `Storage`, or `KeyManagementServiceClient`. It knows the endpoint, region/project, credentials, and how to invoke the API.
- **Credential provider:** Obtains or refreshes tokens/credentials. Instantiating multiple providers can multiply file reads, metadata endpoint calls, or token exchanges.
- **HTTP pipeline:** Executes authentication, retry, logging, tracing, telemetry, and pre/post-request policies.
- **HTTP transport:** Performs network I/O, such as Apache HttpClient, Netty, OkHttp, or JDK HttpClient.
- **Connection pool/channel:** Holds open connections for reuse by subsequent requests; with gRPC, the corresponding resource is a channel and its HTTP/2 streams.
- **TCP/TLS:** Creates sockets, resolves DNS, performs TCP handshakes, and negotiates TLS. This cost is substantial if repeated per request.

A service client may own its own transport or use a transport shared by the application. Therefore, read the SDK's model carefully before deciding on the number of clients and pools. Creating an extra service client does not always create an extra socket pool; conversely, two separate clients might be creating two pools even when calling the same host.

## 3. Why reuse clients?

### 3.1. The cost of client-per-request

An implementation that is easy to write but expensive in resources:

~~~java
public BlobClient createBlobClient(String container, String blob) {
    return new BlobClientBuilder()
        .endpoint(endpoint)
        .credential(credential)
        .containerName(container)
        .blobName(blob)
        .buildClient();
}

public byte[] download(String container, String blob) {
    BlobClient client = createBlobClient(container, blob);
    return client.downloadContent().toBytes();
}
~~~

If this method is called continuously, the application may repeatedly create pipelines, transports, pools, background threads, or credential caches. Some SDKs use global resources so not every client creation opens a new socket; however, creating clients continuously still repeats initialization overhead and makes lifecycle management difficult.

### 3.2. Using long-lived clients

Create the client once at application startup and inject it into services:

~~~java
@Service
public class BlobDownloadService {
    private final BlobContainerClient container;

    public BlobDownloadService(BlobContainerClient container) {
        this.container = container;
    }

    public byte[] download(String blobName) {
        return container.getBlobClient(blobName)
            .downloadContent()
            .toBytes();
    }
}
~~~

Child objects like `BlobClient` are often just wrappers for an endpoint/container/blob; creating a wrapper per operation can be much lighter than recreating the transport. Check the SDK API to see which builders allocate network resources and which only construct resource-descriptor objects.

Key benefits of reuse:

- Reduces repeated DNS lookups, TCP connects, and TLS handshakes.
- Reduces the number of pools, sockets, event loops, and background threads.
- Takes advantage of credential/token caches and initialized pipeline policies.
- Lowers tail and first-byte request latency as well as OS/NAT pressure.
- Provides a single centralized place to configure timeouts, proxies, TLS, retries, and metrics.

### 3.3. Which clients can be shared?

Do not use a single client for every endpoint or every identity. A client is typically bound to an immutable configuration tuple:

`(service type, endpoint, region/project, credential, transport, policy)`

If any of these factors changes, create a separate client for that configuration. For example, an application calling two AWS regions, two Azure storage accounts, or two Google Cloud projects may need separate clients. For multi-tenant applications with dynamic endpoints/credentials, use a bounded registry with an eviction policy; do not retain an unbounded number of clients per user.

## 4. Managing clients as Spring singleton beans

Spring beans default to singleton scope within an ApplicationContext. This is the right place to construct shared SDK clients:

~~~java
@Configuration(proxyBeanMethods = false)
public class CloudClientConfiguration {

    @Bean
    SomeCloudClient someCloudClient() {
        return SomeCloudClient.builder()
            .endpoint(System.getenv("SERVICE_ENDPOINT"))
            .build();
    }
}
~~~

This is a structural example; the exact builder and shutdown rules depend on the SDK. Services only receive the client via constructor injection. Do not call the builder inside controllers, repository methods, or per-message processing loops.

### 4.1. Singleton does not mean one client for all configurations

You can declare multiple singleton beans for different endpoints/regions:

~~~java
@Bean("primaryStorage")
StorageClient primaryStorage() {
    return buildStorageClient(primaryEndpoint);
}

@Bean("archiveStorage")
StorageClient archiveStorage() {
    return buildStorageClient(archiveEndpoint);
}
~~~

The snippet illustrates bean structure; `buildStorageClient`, `primaryEndpoint`, and `archiveEndpoint` are application helper methods/configuration values.

Each bean represents one stable configuration. Name beans clearly and inject with `@Qualifier` when needed. Never mutate the endpoint or credentials shared inside a client that is serving concurrent requests.

### 4.2. Builders and clients have different lifecycles

Builders are typically temporary configuration objects and should not be shared across threads unless the API guarantees thread safety. Create the builder in bean configuration, call `build()` once, and then share the client. With Spring Boot's `WebClient.Builder` and `RestClient.Builder`, the builder is auto-configured and can hold mutable state; clone it when you need different configuration variants.

## 5. AWS SDK for Java 2.x

### 5.1. Service clients are thread-safe

AWS SDK for Java 2.x guarantees that service clients are thread-safe and recommends creating one instance per service configuration and reusing it across the application. By default, each service client owns its own HTTP connection pool. Creating multiple clients for the same service/configuration can create multiple underutilized pools, wasting connections and resources.

If you need to share a pool across multiple service clients, the SDK allows passing the same HTTP client instance into multiple builders. When doing so, the application is responsible for closing the shared HTTP client after all service clients have stopped.

### 5.2. Configuring a synchronous client with Apache 5

AWS SDK 2.x includes synchronous HTTP transports such as Apache 5. The Apache 4-based `ApacheHttpClient` is deprecated because Apache HttpClient 4.x is in maintenance mode; for new configurations, prefer `Apache5HttpClient`.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>${aws.sdk.version}</version>
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
        <artifactId>apache5-client</artifactId>
    </dependency>
</dependencies>
~~~

Register the HTTP client and S3 client as beans:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.http.SdkHttpClient;
import software.amazon.awssdk.http.apache5.Apache5HttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
public class AwsClientConfiguration {

    @Bean(destroyMethod = "close")
    SdkHttpClient awsSyncHttpClient() {
        return Apache5HttpClient.builder()
            .maxConnections(80)
            .connectionTimeout(Duration.ofSeconds(3))
            .connectionAcquisitionTimeout(Duration.ofSeconds(2))
            .connectionMaxIdleTime(Duration.ofSeconds(45))
            .build();
    }

    @Bean(destroyMethod = "close")
    S3Client s3Client(SdkHttpClient awsSyncHttpClient) {
        return S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .httpClient(awsSyncHttpClient)
            .overrideConfiguration(config -> config
                .apiCallAttemptTimeout(Duration.ofSeconds(10))
                .apiCallTimeout(Duration.ofSeconds(25)))
            .build();
    }
}
~~~

These numbers are initial benchmark examples, not universal defaults for every application. `maxConnections` is the HTTP client's connection limit; `connectionAcquisitionTimeout` is the wait time to borrow a connection; `apiCallAttemptTimeout` bounds a single attempt; `apiCallTimeout` bounds the entire API call including retries.

If you add `DynamoDbClient` or another service client and pass the same `SdkHttpClient`, they can share the compatible pool:

~~~java
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Bean(destroyMethod = "close")
DynamoDbClient dynamoDbClient(SdkHttpClient awsSyncHttpClient) {
    return DynamoDbClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .httpClient(awsSyncHttpClient)
        .build();
}
~~~

Both the service client and HTTP client are beans. On shutdown, Spring closes dependent beans before the dependencies they use; verify bean ordering if using a custom lifecycle. AWS service clients are closed first, and then the shared HTTP transport is closed. Never close the transport inside a business method.

### 5.3. Configuring an asynchronous client with Netty

For async clients, the AWS SDK uses Netty or AWS CRT. Netty exposes concurrency limits and a pending connection acquisition queue:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

@Configuration(proxyBeanMethods = false)
public class AwsAsyncClientConfiguration {

    @Bean(destroyMethod = "close")
    S3AsyncClient s3AsyncClient() {
        return S3AsyncClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .httpClientBuilder(NettyNioAsyncHttpClient.builder()
                .maxConcurrency(128)
                .maxPendingConnectionAcquires(256)
                .connectionTimeout(Duration.ofSeconds(3))
                .connectionAcquisitionTimeout(Duration.ofSeconds(2))
                .readTimeout(Duration.ofSeconds(20))
                .writeTimeout(Duration.ofSeconds(20)))
            .overrideConfiguration(config -> config
                .apiCallAttemptTimeout(Duration.ofSeconds(15))
                .apiCallTimeout(Duration.ofSeconds(35)))
            .build();
    }
}
~~~

With HTTP/1.1, concurrency typically maps to active connections; with HTTP/2, multiple streams can share a single connection. If `maxConcurrency` is exceeded, requests can wait in the pending queue; when the queue is full or waits too long, requests are rejected/timed out. Set a finite pending limit to create client-side backpressure instead of accumulating requests without bound.

If you use multiple async service clients and want to share a Netty transport, create an `SdkAsyncHttpClient` bean and pass it to each builder. When sharing an instance, close each service client first and close the transport afterward. If you use `httpClientBuilder(...)`, the SDK manages the lifecycle of the transport created alongside the service client.

### 5.4. Closing streams to return connections to the pool

With S3 `getObject` returning a `ResponseInputStream`, the connection may not be reusable until the response body has been fully read and the stream closed. Use try-with-resources:

~~~java
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

GetObjectRequest request = GetObjectRequest.builder()
    .bucket(bucket)
    .key(key)
    .build();

// outputStream was created earlier.
try (ResponseInputStream<GetObjectResponse> input =
        s3Client.getObject(request)) {
    input.transferTo(outputStream);
}
~~~

If a caller reads only a few bytes and abandons the stream without closing it, the connection can remain held and gradually exhaust the pool. The same rule applies to streaming/download APIs in other SDKs: read or cancel the stream according to its contract and close the response resource.

## 6. Azure SDK for Java

### 6.1. Immutable clients and HTTP pipelines

Azure SDK for Java uses builders to construct service clients. Clients are designed to be immutable; once created, their endpoint, credentials, and client options do not change. Using one long-lived client per configuration is the recommended pattern.

Azure SDK uses the `com.azure.core.http.HttpClient` abstraction. Netty is the default transport; the SDK also supports OkHttp and JDK HttpClient. Each service client's HTTP pipeline contains the transport and policies such as authentication, retry, logging, telemetry, and request ID.

Key distinctions:

- You can share a single `HttpClient` instance across multiple Azure service clients.
- Each service client's pipeline/policies and specific options can still differ.
- The Azure Core `HttpClient` interface does not have a `close()` method; do not attach `destroyMethod = "close"` to a bean of this type.
- If you create a Reactor Netty `ConnectionProvider` or event-loop resource yourself, the application owns that resource and must dispose of it along the appropriate lifecycle.

### 6.2. Sharing an Azure HTTP transport

Example using one Netty transport for Blob Storage and Queue Storage:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-blob</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-queue</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-core-http-netty</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import com.azure.storage.queue.QueueServiceClient;
import com.azure.storage.queue.QueueServiceClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AzureStorageClientConfiguration {

    @Bean
    TokenCredential azureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    HttpClient azureHttpClient() {
        return new NettyAsyncHttpClientBuilder().build();
    }

    @Bean
    BlobServiceClient blobServiceClient(
            TokenCredential credential,
            HttpClient azureHttpClient) {
        return new BlobServiceClientBuilder()
            .endpoint(System.getenv("AZURE_STORAGE_BLOB_ENDPOINT"))
            .credential(credential)
            .httpClient(azureHttpClient)
            .buildClient();
    }

    @Bean
    QueueServiceClient queueServiceClient(
            TokenCredential credential,
            HttpClient azureHttpClient) {
        return new QueueServiceClientBuilder()
            .endpoint(System.getenv("AZURE_STORAGE_QUEUE_ENDPOINT"))
            .credential(credential)
            .httpClient(azureHttpClient)
            .buildClient();
    }
}
~~~

This example shows two service clients sharing credentials and a transport. The Azure SDK service clients in the example do not require calling `close()`; if replaced with a custom transport that owns dedicated resources such as a Reactor Netty `ConnectionProvider`, register that resource as its own bean and dispose of it on application shutdown. Use the Azure SDK BOM to align versions across `azure-core`, transports, and service libraries.

### 6.3. Configuring a connection provider when truly needed

If the workload requires limiting connection count, pending acquires, or idle time, you can provide a Reactor Netty `ConnectionProvider`:

~~~java
import java.time.Duration;
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class AzureTransportConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider azureConnectionProvider() {
        return ConnectionProvider.builder("azure-cloud-services")
            .maxConnections(100)
            .pendingAcquireMaxCount(200)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(45))
            .maxLifeTime(Duration.ofMinutes(10))
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

Values must be sized based on instance count, endpoint count, traffic, and service timeouts. If the pool provider is created by the application, the application manages its disposal; do not dispose of it immediately after creating the service client. When using default Netty/global resources, avoid creating a new event loop or provider for every service.

## 7. Google Cloud Java client libraries

### 7.1. Long-lived clients, credential caches, and gRPC channels

Google Cloud Java client libraries recommend reusing client objects instead of creating a client per request. A session client can share a credential instance and access token cache; the first request may incur extra time for authentication and token generation, while subsequent requests reuse the valid token. Creating too many clients in a short period can increase authentication calls and hit rate limits in certain authentication strategies.

Google Cloud clients can use REST/HTTP JSON or gRPC depending on the service and library. With gRPC, the client typically manages channels, executors, and background resources. Close the client when the ApplicationContext shuts down; with gRPC clients, call `awaitTermination` after `close()` if you need to wait for in-flight RPCs to finish.

### 7.2. Spring bean for Cloud Storage

Example creating a Google Cloud Storage client:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-storage</artifactId>
</dependency>
~~~

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GoogleCloudClientConfiguration {

    @Bean(destroyMethod = "close")
    Storage storageClient() {
        return StorageOptions.newBuilder()
            .setProjectId(System.getenv("GOOGLE_CLOUD_PROJECT"))
            .build()
            .getService();
    }
}
~~~

Services inject `Storage` via constructor injection and invoke operations repeatedly on the same client. The client obtains Application Default Credentials from the environment; production should use an appropriate workload identity/service account rather than baking key files into the image.

### 7.3. gRPC clients and graceful shutdown

Example of a Google KMS client:

~~~java
import com.google.cloud.kms.v1.KeyManagementServiceClient;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GoogleKmsConfiguration {

    @Bean(destroyMethod = "close")
    KeyManagementServiceClient kmsClient() throws IOException {
        return KeyManagementServiceClient.create();
    }
}
~~~

With gRPC clients in production, allow in-flight requests time to complete before the process exits. Google Cloud client lifecycle docs recommend calling `close()`, followed by `awaitTermination(timeout, unit)`; only use `shutdownNow()` when you must urgently terminate hanging tasks. If the Spring shutdown timeout is too short, the client may be closed while requests are still in flight.

### 7.4. When is a channel pool needed?

Not every Google Cloud client needs multiple gRPC channels. GAX provides `ChannelPoolSettings` to distribute RPCs across multiple channels for certain high-throughput workloads; this API is currently marked Beta, and oversizing the pool can leave channels idle and increase tail latency. Only enable a channel pool when the service/client documentation supports it, metrics show a single channel is a bottleneck, and benchmarks confirm a benefit.

## 8. Spring Boot RestClient and WebClient

Cloud SDKs are not the only HTTP path. Applications often also call internal APIs or partner REST APIs. Spring Boot provides `RestClient` for imperative applications and `WebClient` for reactive applications.

### 8.1. WebClient

Spring Boot auto-configures `WebClient.Builder` and shares HTTP resources with the server when using Reactor Netty or Jetty respectively. Inject the builder and build `WebClient` once in the service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class PartnerApiClient {
    private final WebClient webClient;

    public PartnerApiClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("https://partner.example")
            .build();
    }

    public Mono<PartnerResponse> getStatus(String id) {
        return webClient.get()
            .uri("/v1/status/{id}", id)
            .retrieve()
            .bodyToMono(PartnerResponse.class);
    }
}
~~~

Do not call `WebClient.create()` per request if you want to reuse resources/pools and auto-configuration. `WebClient.Builder` is stateful; if creating multiple clients with different configurations, use `builder.clone()` before changing the base URL/filters so configuration does not accidentally leak into clients built later.

### 8.2. RestClient

For imperative applications, inject `RestClient.Builder` and build a client in the constructor or bean configuration. Spring Boot auto-detects the HTTP client from the classpath; it can use Apache HttpClient, Jetty, Reactor Netty, or JDK HttpClient. Do not create a new request factory and pool for every method call.

### 8.3. Do not mistakenly share transports between reactive and blocking

A synchronous HTTP client and an asynchronous HTTP client can have different APIs, event loops, and lifecycles. Do not force a blocking transport onto the WebFlux event loop. Choose a connector matching your programming model; only share resources when Spring/the transport officially supports it and shares the same lifecycle.

## 9. Connection pools and concurrency

### 9.1. Pool size is not the application-wide maximum request count

A pool typically belongs to an HTTP client instance. If every service client creates its own transport, each pool has its own limit. If multiple service clients share a transport, that limit may be shared across all service clients using the transport.

With HTTP/1.1, one connection typically serves one active request at a time. With HTTP/2, multiple streams can multiplex over the same connection. Therefore:

- `maxConnections` usually refers to the number of TCP connections in the pool.
- `maxConcurrency` can mean the number of concurrent requests/streams allowed in flight.
- The number of physical connections does not necessarily equal the number of concurrent requests.
- GAX gRPC channel pools have their own semantics; do not use HTTP/1.1 connection counts to infer channel counts.

The scope of limits also depends on the implementation:

| Implementation | Common parameter | Scope to understand |
| --- | --- | --- |
| AWS Apache5 | `maxConnections` | Connection limit of the created HTTP client/pool |
| AWS Netty async | `maxConcurrency` | Concurrent request limit; with HTTP/2 this does not mean TCP connections and is applied per endpoint |
| Azure Reactor Netty | `ConnectionProvider.maxConnections` | Pool limit per remote address; multiple hosts can create multiple pools |
| Google GAX/gRPC | Channel pool settings | Channel count and RPCs/streams per channel are two separate concepts |

When one transport serves multiple endpoints, read the semantics of that exact implementation. Do not multiply or sum limits without confirming whether they are global, per-host, or per-endpoint.

### 9.2. Using Little's Law for an initial estimate

A simple estimate for the number of in-flight requests:

**L = λ × W**

Where:

- **L:** average number of waiting/in-flight requests.
- **λ:** average throughput (requests/second).
- **W:** average resource hold duration (seconds).

For example, an instance sends 120 requests/second, with each request holding a connection for an average of 0.25 seconds:

**L = 120 × 0.25 = 30**

Roughly 30 requests may be in flight on average. This is not yet the `maxConnections` value: you must account for bursts, p95/p99, HTTP/2, response body duration, retries, and endpoint count. Size the pool to handle reasonable peaks while keeping a cap to protect downstream services.

### 9.3. Calculating the total across the entire deployment

Suppose an application runs 6 pods and each pod has a pool with a maximum of 80 connections to a service:

[
**6 × 80 = 480 connections**
]

If the application has three additional HTTP clients, each with its own pool, the total potential connection count will be higher. Account for:

- Number of replicas/pods/VMs and processes per host.
- Number of service client/transport instances per process.
- Number of endpoints/regions managed by the pool.
- Retries, streaming, and long-held connections.
- Database, API gateway, NAT/SNAT limits, and service quotas.

Never look only at `maxConnections` in one pod and conclude the system is safe.

## 10. Choosing timeouts by stage

Different timeouts have different meanings:

| Timeout | Bounds | When expired |
| --- | --- | --- |
| DNS resolution | Hostname resolution | Endpoint cannot be resolved within deadline |
| Connection timeout | Establishing TCP connection | Connection cannot be opened |
| TLS handshake timeout | TLS negotiation | Handshake does not complete |
| Pool acquisition timeout | Waiting for a free connection/slot | Pool is busy or queue is overloaded |
| Read/write timeout | Sending request or receiving response | Network I/O is too slow |
| Attempt timeout | One SDK call attempt | May trigger a retry if policy permits |
| API/call timeout | Entire operation including retries | Terminates the operation at the deadline |
| Caller/request deadline | End-to-end request duration | Cancels or returns a timeout to the caller |

Order timeouts sensibly: pool wait and connect times must fit inside the overall deadline; attempt timeout must not exceed API timeout; API timeout should not vastly exceed the upstream HTTP request deadline. If retries occur at multiple layers, total duration can multiply unexpectedly.

Do not raise timeouts when the real root cause is pool exhaustion. If pool acquisition timeouts increase, inspect active connections, pending queue depth, and response body duration before loosening limits.

## 11. DNS, keepalive, and connection lifetime

Connection reuse reduces handshakes, but connections should not be kept forever regardless of the environment:

- DNS records can change during service failover, scaling, or endpoint migration.
- Load balancers/NAT/firewalls may close idle connections.
- Certificates or TLS policies may rotate.
- Long-lived connections can stay pinned to stale routes or become unhealthy.

HTTP clients typically provide connection TTL, max idle time, and keepalive settings. Choose values based on DNS TTL, network idle timeouts, service behavior, and request processing times. Do not set TTL so short that the application constantly performs TLS handshakes; nor set it to infinite when endpoints undergo failover/DNS rotation.

HTTP/2 and gRPC have their own keepalive pings and channel health checks. Only enable them per service guidance; pinging too frequently can be rate-limited by servers/proxies or create unnecessary overhead.

## 12. Streaming and releasing responses

A pool can only reuse a connection once the response body has been consumed or properly closed. Operations prone to holding connections for a long time:

- Downloading files from S3/Blob/GCS.
- Reading large streams or processing responses slowly.
- Holding response objects in caches or passing them across multiple layers before closing.
- Failing to cancel subscriptions when callers no longer need the data.

Example with AWS:

~~~java
try (ResponseInputStream<GetObjectResponse> stream =
        s3Client.getObject(request)) {
    stream.transferTo(destination);
}
~~~

With Azure, use the download/stream APIs and close the response/stream according to the method contract. With Google Cloud Storage, close the returned `ReadChannel` or stream once reading finishes. If an API returns a publisher, handle cancellation and consume the body; do not ignore the response body and expect the pool to reclaim the connection immediately.

## 13. How retries and idempotency affect pools

Retries increase request volume passing through the transport. When a service slows down, concurrent retries can overload the pool and downstream even further:

1. Many initial requests hold connections for a long time.
2. Callers time out and begin retrying.
3. New retries line up in the pending queue.
4. The queue fills up, latency spikes, and more timeouts occur.

This is a retry storm. Use retries with exponential backoff and jitter, bound retry attempts/total deadlines, and apply circuit breakers or concurrency limits where appropriate. Do not retry authentication/authorization or validation errors as if they were transient network errors.

For write operations, you must define idempotency semantics. A timeout after sending a request does not prove the server did not process it; retrying a counter increment, resource creation, or payment charge can cause duplicate side effects. Use idempotency keys, conditional writes, or state reconciliation before retrying.

## 14. Credentials and client configuration

Clients typically hold a credential provider or a reference to one. Creating clients continuously can repeat:

- Reading profile/credential files.
- Calling the VM/container metadata service.
- Initializing token caches.
- Exchanging tokens with the identity provider.
- Creating gRPC channels or HTTP authentication pipelines.

Reuse credential providers when the SDK permits it. Azure Identity for Java documents that credential implementations are thread-safe and a single credential instance can be used to create multiple service clients. Google client libraries recommend reusing session clients to share credential caches and token refreshes. The AWS SDK credential provider chain should also be configured at the client lifecycle level rather than creating a new provider on every request.

Do not share a client across tenants/identities if doing so violates security boundaries. If credentials, endpoints, regions, or policies differ, create separate clients per configuration and bound their count.

## 15. Observing pools and transports

Metrics to monitor at both the application and client levels:

| Group | Metric | Meaning |
| --- | --- | --- |
| Connection pool | Active/in-use connections | Number of connections currently serving requests |
| Connection pool | Idle/available connections | Capacity to accept new requests |
| Connection pool | Pending acquire / waiters | Number of requests waiting on the pool |
| Connection pool | Acquire latency/timeouts | Wait time to borrow a connection |
| Transport | Connect/TLS handshake duration | Cost of opening new connections |
| Transport | Connection creation/close rate | Whether the pool is churning excessively |
| Request | p50/p95/p99 latency | End-to-end latency |
| Request | In-flight, success/error, retry | Load level and stability |
| Resource | File descriptors/sockets, threads, event loops | Risk of resource exhaustion |
| Cloud | 429/throttling, quotas, service latency | Whether downstream is overloaded |

With the AWS SDK, inspect metrics such as available concurrency, pending concurrency acquires, and concurrency acquire duration. With Azure, combine SDK diagnostics, Reactor Netty metrics, and Azure Monitor. With Google gRPC, monitor channel state, RPC latency, outstanding calls, and executor saturation.

Do not log access tokens, secrets, signed URLs, or sensitive data in HTTP wire logs. Only enable wire-level logging selectively in investigation environments.

## 16. Lifecycle and graceful shutdown

When the Spring ApplicationContext shuts down:

1. Stop accepting new traffic and mark the instance unready.
2. Wait for in-flight requests/messages to finish within the shutdown deadline.
3. Close service clients or client wrappers according to the SDK contract.
4. Close shared HTTP transports after all dependent service clients.
5. Dispose of custom connection providers/event loops owned by the application.
6. For gRPC clients, call `close()` and wait via `awaitTermination` within a bounded timeout.

Do not close transports while requests are still using them. Do not rely solely on garbage collection to release sockets/threads. For shared transports, document clearly which bean owns the resource and which beans merely borrow it.

| SDK/resource | Typical lifecycle |
| --- | --- |
| AWS service client | Singleton bean; call `close()` on shutdown |
| Shared AWS HTTP client | Separate bean; close after service clients |
| Azure service client | Immutable client, reused; follow the service/client library lifecycle |
| Azure `HttpClient` abstraction | Shareable; interface has no `close()` |
| Azure custom Reactor `ConnectionProvider` | If owned by the application, call `dispose()` on shutdown |
| Google Cloud client | Long-lived bean; call `close()`; gRPC may require `awaitTermination` |
| Spring WebClient/RestClient | Create once and let Spring/transport resources manage lifecycle with ApplicationContext |

## 17. Common pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Creating an SDK client per request | Repeated init, credentials, pools, and sockets | Singleton bean per configuration |
| Creating multiple clients for the same endpoint/credential | Multiple underutilized pools, higher file descriptor count | Share service client/transport when compatible |
| Sharing one client across two different regions or identities | Calls wrong endpoint or breaks security boundary | Separate client per stable configuration |
| Sharing an AWS HTTP client without closing it | Pool, thread, and socket leaks | Close service clients then close the shared transport |
| Assuming Azure HttpClient has `close()` | Incorrect bean lifecycle | Manage custom ConnectionProvider; do not call close on unsupported interface |
| Creating a custom Netty provider without disposing | Event-loop/connection resources linger | Dispose of application-owned resources |
| Pool too small | Pending queue and acquire timeouts grow | Measure concurrency, latency, and scale up carefully |
| Pool too large on every pod | Too many connections to databases/APIs/NAT | Sum across replicas and downstream limits |
| No pending queue limit | Requests accumulate, memory grows | Set a bounded queue and acquire timeout |
| Not closing download streams | Connections never return to the pool | Close streams/responses with try-with-resources |
| Retrying every error | Retry storms and duplicate side effects | Retry transient errors only, with idempotency and deadlines |
| Disabling keepalive/TTL without understanding network | Stale connections or repeated handshakes | Tune for DNS/load balancer/idle timeouts |
| Closing clients before requests finish | In-flight requests fail | Drain traffic and perform graceful shutdown |

## 18. Testing and benchmarking

### 18.1. Lifecycle testing

Write integration tests or smoke tests to verify:

- Spring creates exactly one client bean per configuration.
- Multiple service requests use the same client/transport.
- Application shutdown invokes close/dispose in the correct order.
- A shared transport is not closed when an individual service client finishes.
- Streaming responses are closed on both success and exception paths.
- Credential refresh does not reinitialize the entire client.

### 18.2. Comparative benchmarks

Compare two versions:

- **A:** creating a client/transport per request.
- **B:** reusing a singleton client and pool.

Use the same endpoint, region, payload, concurrency, and credentials. Measure:

| Metric | Purpose |
| --- | --- |
| p50/p95/p99 latency | Observe impact of connection reuse and queueing |
| Throughput | Operations completed per second |
| TCP/TLS connection creation | Measure avoided handshakes |
| Active/idle/pending pool | Determine pool size and queue sizing |
| CPU/memory/thread count | Measure client/transport overhead |
| Socket/file descriptors | Detect client churn or leaks |
| Retry/error/timeout | Detect overload or misconfigured timeouts |
| Cloud API request count/data transfer | Separate transport cost from service cost |

Warm up before capturing numbers because initial requests may initialize DNS, TLS, credential caches, or gRPC channels. Run long enough to see steady-state pooling and peak phases. Do not draw conclusions from a single request or a short run.

### 18.3. Do not confuse transport savings with lower API bills

Client reuse lowers compute cost, TLS handshakes, sockets, threads, and application-side latency. It **does not automatically reduce billable API requests** if business operations stay constant. Cloud bills also depend on request counts, data transfer, storage, database throughput, egress, and service SKUs. To reduce the bill, you must also optimize batching, caching, payloads, queries, transfers, and service tiers based on measurements.

## 19. Implementation workflow

~~~mermaid
flowchart TD
    A[List service endpoints and identities] --> B[Choose SDK clients and transports]
    B --> C[Define client/pool ownership]
    C --> D[Register Spring singleton beans]
    D --> E[Set pool limits and timeouts]
    E --> F[Close streams and define shutdown]
    F --> G[Load test and observe metrics]
    G --> H{Is pool congested or over-provisioned?}
    H -->|Congested| I[Tune concurrency, queue, timeouts]
    H -->|Over-provisioned| J[Shrink pool or consolidate transports]
    I --> G
    J --> G
    H -->|Balanced| K[Finalize configuration and alerts]
~~~

Before releasing, answer:

1. Where are clients created, and how many instances exist per pod?
2. Are the clients thread-safe according to SDK documentation?
3. Does the pool live in the service client or in the HTTP transport?
4. Which service clients share the transport?
5. Who owns and closes the transport/connection provider?
6. What is the total potential connection count across all pods?
7. Does the pending queue have a cap and a timeout?
8. Are streaming responses closed on all branches?
9. Are there metrics to distinguish pool exhaustion from downstream throttling?
10. Do retries and shutdown keep in-flight requests safe?

## 20. Hands-on exercises

**Exercise 1 — AWS singleton.** Create an S3Client bean using Apache5HttpClient. Call `headBucket` and `listObjectsV2` across many requests; compare client initialization counts, connection counts, and p95 before and after reuse.

**Exercise 2 — AWS shared transport.** Use the same `SdkHttpClient` for S3Client and DynamoDbClient. Verify both share the pool, service clients close before the transport, and no threads/sockets remain after shutdown.

**Exercise 3 — AWS async.** Configure `S3AsyncClient` with `maxConcurrency`, pending acquires, and timeouts. Gradually increase load to observe when the queue grows and requests begin timing out.

**Exercise 4 — Azure transport.** Create one Netty `HttpClient` and use it for BlobServiceClient and QueueServiceClient. Then replace it with a custom ConnectionProvider, cap maxConnections/pendingAcquire, and verify disposal when ApplicationContext stops.

**Exercise 5 — Google client lifecycle.** Register a Storage or KMS client as a singleton bean. Send multiple requests, inspect credential caching, then shut down and verify the client/gRPC channel was closed.

**Exercise 6 — Spring WebClient.** Build a WebClient in a constructor using Spring Boot's WebClient.Builder. Compare against calling `WebClient.create()` per request; measure connection reuse and TLS handshake counts.

**Exercise 7 — Pool sizing.** A pod handles 150 RPS to service A with an average connection hold time of 120 ms; calculate the average number of in-flight requests. With 8 pods and a max pool of 40 per pod, calculate the maximum connections and evaluate against downstream quotas.

**Exercise 8 — Streaming leak.** Write an S3 download endpoint that intentionally omits closing ResponseInputStream. Observe pool pending/acquire timeouts; fix it with try-with-resources and verify connections are reused.

**Exercise 9 — Retry storm.** Simulate a slow downstream service. Observe the pending queue, retries, and p99. Add exponential backoff, jitter, deadlines, and concurrency limits; compare recovery behavior.

## 21. Key takeaways

- **Creating long-lived clients and reusing them** is the default for shareable SDK clients; per-request client creation repeats credential setup, pipelines, pools, sockets, and TLS handshakes.
- AWS SDK for Java 2.x service clients are thread-safe; each client defaults to its own pool. Compatible HTTP clients can be shared, but the transport must be closed after the service clients.
- Azure SDK for Java uses a pluggable HTTP pipeline defaulting to Netty; the same `HttpClient` instance can be passed to multiple service clients. Custom Reactor resources created by the application must be disposed of.
- Google Cloud Java clients are designed to be long-lived; reuse shares credential caches. Close clients and await gRPC channel termination on shutdown.
- Spring singleton beans are the right place to manage SDK clients. Separate clients by differing endpoints, regions, credentials, or configurations.
- Pool sizing must account for concurrency, hold time, pod count, endpoints, and quotas. Calculate total connections across the whole deployment, not just per process.
- Connection acquisition timeout, connect/TLS timeout, read/write timeout, and API deadline are distinct limits.
- Close streams/responses so connections return to the pool; bound pending queues to avoid unbounded request accumulation.
- Retries require backoff, jitter, deadlines, and idempotency. A timeout does not prove an operation was not executed.
- Client reuse reduces application-side resource cost and latency; it does not by itself reduce billable cloud service API requests.

## 22. References

- [AWS SDK for Java 2.x — Best practices](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html)
- [AWS SDK for Java 2.x — Singleton service clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/singleton-service-clients.html)
- [AWS SDK for Java 2.x — Configure the Apache 5 HTTP client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-apache5.html)
- [AWS SDK for Java 2.x — Configure the Netty async HTTP client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-netty.html)
- [AWS SDK for Java 2.x — Client configuration and shared HTTP clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/client-configuration.html)
- [AWS SDK for Java 2.x — Timeouts](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html)
- [Azure SDK for Java — Use the Azure SDK for Java](https://learn.microsoft.com/en-us/azure/developer/java/sdk/overview)
- [Azure SDK for Java — HTTP clients and pipelines](https://learn.microsoft.com/en-us/azure/developer/java/sdk/http-client-pipeline)
- [Azure SDK for Java — Netty HTTP client and ConnectionProvider](https://learn.microsoft.com/en-us/java/api/com.azure.core.http.netty.nettyasynchttpclientbuilder?view=azure-java-stable)
- [Azure SDK for Java — Azure Identity](https://learn.microsoft.com/en-us/java/api/overview/azure/identity-readme?view=azure-java-stable)
- [Google Cloud Java — Manage client lifecycles](https://docs.cloud.google.com/java/docs/client-lifecycle)
- [Google Cloud — Client libraries best practices](https://docs.cloud.google.com/apis/docs/client-libraries-best-practices)
- [Google Cloud GAX — ChannelPoolSettings](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.grpc.ChannelPoolSettings)
- [Spring Boot — Calling REST services](https://docs.spring.io/spring-boot/reference/io/rest-client.html)
