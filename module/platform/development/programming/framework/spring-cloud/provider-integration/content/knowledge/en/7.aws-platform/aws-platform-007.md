# Customizing Clients by Service, HTTP Transport, and Endpoint

## 1. Context: One Application, Yet Each AWS Service Needs Tailored Configuration

A single Spring Boot application may simultaneously **upload documents to Amazon S3**, **send events to Amazon SQS**, **read data from DynamoDB**, and **fetch secrets from AWS Secrets Manager**. All of them use the AWS SDK for Java, yet each client has distinct needs:

- S3 may require large file transfers, streaming, custom connection pools, and bucket addressing modes.
- SQS often involves many small requests, long polling, and continuously running consumers.
- DynamoDB is sensitive to latency, retries, throttling, and concurrent traffic.
- Secrets Manager sees low request frequency but requires tight timeouts, IAM controls, and zero data leakage.
- Integration tests may need to switch endpoints from real AWS to LocalStack or a service emulator; production must ensure the standard endpoint is restored.

The lesson **"Customizing Clients by Service, HTTP Transport, and Endpoint"** belongs to the **AWS Platform** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module's scope is practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud via the respective Spring Cloud libraries—from identity and storage/messaging/data permissions to secret protection, testing, and evaluating differences across cloud providers.

This lesson examines **AWS SDK for Java 2.x** and how to use the SDK alongside **Spring Cloud AWS by AWSpring**. The goal is knowing **what to configure globally**, **what to customize per service**, and **what to verify** before operating the application in production.

**After this lesson, you will be able to:**

1. Choose synchronous or asynchronous clients suited to your Spring Boot execution model.
2. Distinguish service client APIs, HTTP transport, endpoints, regions, credentials, and signing.
3. Configure timeouts, connection pools, retries, and client lifecycles without creating new clients per request.
4. Set up safe endpoint overrides for testing and understand S3 and SQS specifics.
5. Declare service-specific client beans while intentionally managing interactions with AWSpring auto-configuration.
6. Diagnose network, endpoint, region, IAM, and runtime dependency errors at the right layer.

> **Version scope:** Examples use **AWS SDK for Java 2.x**, with AWSpring starters from a version set **verified compatible** with the project's Spring Boot and Java versions. AWSpring property names and extension points can vary by release; check the documentation for the exact version deployed. Hosts, buckets, queues, and regions in examples are illustrative only.

## 2. Layered Client Configuration Model

To understand how an `S3Client.putObject(...)` call executes, distinguish the layers below:

~~~mermaid
flowchart TD
    A["Service / Adapter in Spring Boot"] --> B["AWSpring template or SDK client"]
    B --> C["S3Client / SqsAsyncClient / DynamoDbClient"]
    C --> D["Client configuration: timeout, retry, interceptors"]
    D --> E["Endpoint resolution + region + signing"]
    E --> F["HTTP transport: Apache / URLConnection / Netty / CRT"]
    F --> G["DNS, proxy, TLS, VPC/network"]
    G --> H["AWS service or test emulator"]
    I["Credentials provider / IAM role"] -. "Supplies credentials to sign request" .-> E
~~~

When adding an AWSpring starter dependency, Spring Boot can auto-create clients/abstractions based on auto-configuration conditions. Even so, **real calls still pass through the AWS SDK client** and underlying HTTP transport.

| Layer | Key decision | Examples |
| --- | --- | --- |
| Business API | Which service, which operation? | `PutObject`, `SendMessage`, `GetItem` |
| AWSpring | Are `S3Template`, `SqsTemplate`, or `@SqsListener` needed? | S3/SQS starters |
| AWS SDK client | Sync or async? Region? Which service client? | `S3Client`, `SqsAsyncClient` |
| Request execution | Timeouts, retries, interceptors, and client-level overrides | `ClientOverrideConfiguration` |
| Endpoint | Which URL receives requests; how are hostnames resolved by region/bucket? | Standard AWS endpoint or LocalStack |
| HTTP transport | Library handling network I/O, TLS, pooling, and proxies | Apache, URLConnection, Netty |
| Identity | Which principal/role signs requests? | `DefaultCredentialsProvider` or explicit provider |
| AWS service | IAM/resource policies and service semantics | S3 bucket policy, SQS queue policy |

**A valid endpoint does not grant IAM permissions**, and a valid role does not guarantee the URL, network, or HTTP client is configured properly. These failures must be investigated separately.

## 3. Choosing the Right SDK Client per Service

AWS SDK v2 organizes libraries into **service modules**. Within the same application, you can use separate clients:

| Service | Blocking client | Asynchronous client | Common operations |
| --- | --- | --- | --- |
| Amazon S3 | `S3Client` | `S3AsyncClient` | `PutObject`, `GetObject`, `HeadObject` |
| Amazon SQS | `SqsClient` | `SqsAsyncClient` | `SendMessage`, `ReceiveMessage`, `DeleteMessage` |
| Amazon DynamoDB | `DynamoDbClient` | `DynamoDbAsyncClient` | `GetItem`, `PutItem`, `Query` |
| AWS Secrets Manager | `SecretsManagerClient` | `SecretsManagerAsyncClient` | `GetSecretValue` |
| AWS STS | `StsClient` | `StsAsyncClient` | `AssumeRole`, `GetCallerIdentity` |

SDK v2 package examples:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
~~~

These clients are **not** `AmazonS3` or `AmazonSQS` from AWS SDK for Java 1.x (under `com.amazonaws.*`). When a project uses modern Spring Cloud AWS, do not copy SDK v1 examples while ignoring API and dependency differences.

### 3.1. When to Use Synchronous Clients?

`S3Client` and `SqsClient` are synchronous clients: the call completes or throws an exception before the thread continues. They fit:

- Spring MVC applications using a blocking request model with clearly bounded concurrent I/O.
- Moderate batch tasks with linear, easy-to-read code and straightforward error handling.
- Adapters with infrequent AWS operations where simplicity outweighs extreme throughput.

Example:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;

public class FileMetadataGateway {
    private final S3Client s3Client;

    public FileMetadataGateway(S3Client s3Client) {
        this.s3Client = s3Client;
    }

    public long contentLength(String bucket, String key) {
        return s3Client.headObject(
                HeadObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .build())
                .contentLength();
    }
}
~~~

**Blocking** here is a property of the SDK call. Calling `S3Client` directly on a reactive event loop can stall the event loop; offload blocking work to an appropriate scheduler or choose a suitable async client/adapter.

### 3.2. When to Use Asynchronous Clients?

`SqsAsyncClient` or `S3AsyncClient` returns `CompletableFuture` or an equivalent asynchronous abstraction, avoiding tying up the caller's thread while waiting on network I/O.

~~~java
import java.util.concurrent.CompletableFuture;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;
import software.amazon.awssdk.services.sqs.model.SendMessageResponse;

public class OrderEventGateway {
    private final SqsAsyncClient sqs;
    private final String queueUrl;

    public OrderEventGateway(SqsAsyncClient sqs, String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public CompletableFuture<SendMessageResponse> publish(String json) {
        return sqs.sendMessage(request -> request
                .queueUrl(queueUrl)
                .messageBody(json));
    }
}
~~~

Async clients are appropriate when an application has high concurrent I/O, long-lived queue processing, or integrates with a genuinely non-blocking reactive pipeline.

However, **async is not automatically better** in every case. You must manage concurrency limits, internal queues, future exceptions, timeouts, memory pressure, and client lifecycle. In Spring MVC handlers, calling `future.join()` immediately still blocks the thread, diminishing async benefits.

**Specifically for AWSpring SQS:** Spring Cloud AWS 3.x typically uses `SqsAsyncClient` underneath for listener containers and SQS abstractions. When customizing HTTP transport, inspect which SDK client is **actually used by the container** rather than customizing an unused synchronous `SqsClient`.

## 4. HTTP Transport in AWS SDK for Java v2

The AWS SDK separates the **service client** from the **HTTP client**. The service client builds AWS-semantic requests; the HTTP transport handles connections, TLS, pooling, network-level timeouts, and other I/O characteristics.

### 4.1. Common Transports

| HTTP transport | Maven module | Used with | Characteristics and selection |
| --- | --- | --- | --- |
| Apache HTTP client | `software.amazon.awssdk:apache-client` | Synchronous SDK clients | Connection pooling, proxies, and rich HTTP options |
| JDK URLConnection | `software.amazon.awssdk:url-connection-client` | Synchronous SDK clients | Lightweight, few dependencies; pooling/tuning differs from Apache |
| Netty NIO HTTP client | `software.amazon.awssdk:netty-nio-client` | Asynchronous SDK clients | Event-loop, connection pooling, and async concurrency |
| AWS CRT HTTP client | `software.amazon.awssdk:aws-crt-client` | Corresponding SDK clients, per release | Transport based on AWS Common Runtime; check support and native runtime |
| S3 CRT client / transfer-specific option | Depends on SDK module/support | Specific S3 async/transfer workloads | Useful for optimized S3 data transfer; evaluate load and environment |

AWS SDK v2 generally selects a default transport based on classpath and client type. **Do not rely on "the default is always X" when tuning or debugging production**: explicitly specify the HTTP client builder and declare the corresponding module to control the outcome.

### 4.2. Intentional Maven Dependency Declarations

Assuming the project manages versions via an appropriate AWSpring BOM and/or AWS SDK BOM:

~~~xml
<dependencies>
    <!-- Add only service SDKs directly used by application source code. -->
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sqs</artifactId>
    </dependency>

    <!-- Apache for synchronous clients. -->
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>apache-client</artifactId>
    </dependency>

    <!-- Netty for asynchronous clients. -->
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>netty-nio-client</artifactId>
    </dependency>
</dependencies>
~~~

Each project only needs the dependencies it actually uses. An AWSpring starter may pull in some SDK dependencies **transitively**, yet if application code directly imports HTTP builders or service clients, declaring those modules directly aligns with sound dependency hygiene.

**Never assign mismatched SDK v2 versions** across `s3`, `sqs`, `apache-client`, and `netty-nio-client`. Inspect the resolved dependency graph to ensure aligned modules. If both `com.amazonaws` (SDK 1.x) and `software.amazon.awssdk` (SDK 2.x) appear, locate which legacy library pulls SDK 1.x instead of assuming both generations share clients.

## 5. Configuring Synchronous HTTP Clients with Apache

Suppose a service reads metadata or uploads S3 objects synchronously. You can configure an `S3Client` using the Apache HTTP transport:

~~~java
import java.time.Duration;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

public final class S3ClientFactory {
    public static S3Client create() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .httpClientBuilder(ApacheHttpClient.builder()
                        .maxConnections(80)
                        .connectionTimeout(Duration.ofSeconds(3))
                        .socketTimeout(Duration.ofSeconds(15)))
                .overrideConfiguration(ClientOverrideConfiguration.builder()
                        .apiCallAttemptTimeout(Duration.ofSeconds(20))
                        .apiCallTimeout(Duration.ofSeconds(45))
                        .build())
                .build();
    }
}
~~~

In the example above:

- `maxConnections(80)` bounds the HTTP transport's connection pool and must balance against real concurrency.
- `connectionTimeout` limits HTTP connection establishment time, not total upload duration.
- `socketTimeout` governs socket I/O waits in this transport; it is not the entire API call deadline.
- `apiCallAttemptTimeout` bounds **a single attempt** of a request.
- `apiCallTimeout` bounds **the entire SDK call**, including attempts and retries per client mechanics.

These numbers are **illustrative for learning**, not universal recommendations. On large file upload workloads, low socket/API timeouts can abort valid transfers. On small metadata calls, overly long timeouts make callers wait unnecessarily.

### 5.1. Do Not Create a New HTTP Client per Business Request

**Anti-pattern:**

~~~java
// Anti-pattern: creating a client on every API call.
// void getMetadata(...) {
//     S3Client s3 = S3Client.builder().build();
//     s3.headObject(...);
//     // Does not reuse connections; prone to resource leaks if not closed.
// }
~~~

SDK v2 service clients are designed to be **reused** when configuration does not change. In Spring Boot applications, typically define singleton beans or lifecycle-managed factories/caches and close clients on `ApplicationContext` shutdown. This leverages connection pooling, cuts TLS/DNS overhead, and keeps resources bounded.

**Watch transport ownership:** if you pass a **pre-built** HTTP client via `.httpClient(existingClient)` into multiple service clients, you must manage and close that transport separately with proper lifecycle handling; service clients do not automatically close a shared HTTP transport. With `.httpClientBuilder(...)`, the SDK constructs and manages the transport per SDK contract. Never spawn hundreds of async clients/transports with separate event loops when configuration can be shared.

### 5.2. Layered Timeouts

~~~mermaid
flowchart TD
    CALL["An SDK call"] --> TOTAL["apiCallTimeout: entire call"]
    TOTAL --> TRY["apiCallAttemptTimeout: each attempt"]
    TRY --> CONN["connectionTimeout: connection establishment"]
    TRY --> IO["socket/read/write timeout: transport I/O"]
    TRY --> RETRY["Retry/backoff if retry strategy permits"]
    RETRY --> TRY
~~~

Actual timeouts are also influenced by network conditions, DNS, TLS, retry policies, streaming, connection pool queuing, and client libraries. Do not interpret `socketTimeout(15s)` as "every upload finishes within 15 seconds" or `apiCallTimeout(45s)` as the full business SLA if the service also queries a DB, transforms payloads, signs files, and sends events.

## 6. Configuring Asynchronous HTTP Clients with Netty

For a service publishing high volumes of events to SQS, an `SqsAsyncClient` can use Netty NIO:

~~~java
import java.time.Duration;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

public final class SqsAsyncClientFactory {
    public static SqsAsyncClient create() {
        return SqsAsyncClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .httpClientBuilder(NettyNioAsyncHttpClient.builder()
                        .maxConcurrency(64)
                        .connectionTimeout(Duration.ofSeconds(3))
                        .connectionAcquisitionTimeout(Duration.ofSeconds(5))
                        .readTimeout(Duration.ofSeconds(30))
                        .writeTimeout(Duration.ofSeconds(15)))
                .overrideConfiguration(ClientOverrideConfiguration.builder()
                        .apiCallTimeout(Duration.ofSeconds(45))
                        .build())
                .build();
    }
}
~~~

Key parameters:

| Parameter | What to understand |
| --- | --- |
| `maxConcurrency` | Caps concurrent requests handled by the transport, not business-level SQS message processing count |
| `connectionAcquisitionTimeout` | Time waiting to borrow a connection from the pool; errors spike when the pool saturates |
| `readTimeout` / `writeTimeout` | I/O limits in Netty transport; do not automatically span all retries |
| `apiCallTimeout` | Overall SDK call time limit across retries |
| Event-loop threads | Tied to runtime environment and transport; measure under load |

**SQS long polling example:** if a consumer calls `ReceiveMessage` with a large `WaitTimeSeconds`, the HTTP read timeout and API timeout must accommodate the long-poll wait **plus network overhead**. A read timeout shorter than `WaitTimeSeconds` causes repeated timeouts even when the queue is healthy.

With AWSpring's `@SqsListener`, listener container counts, concurrency, handler speed, visibility timeout, and acknowledgement also govern throughput. Raising Netty's `maxConcurrency` alone **will not** clear a backlog if the business handler is slow.

### 6.1. Async Does Not Mean Infinite Concurrency

If a producer receives 50,000 messages/second yet fires thousands of unbounded `CompletableFuture` calls without backpressure, batching, or concurrency caps, memory and pools will saturate. Coordinate:

- Backpressure or rate limiting at the business layer.
- SQS batching where semantics and API size limits permit.
- Bounded retries with jitter to avoid synchronized retry storms.
- Metrics for connection acquisition timeouts, latency, and SQS throttling.
- Idempotency for side effects, since requests can succeed on AWS even when the client misses the response.

## 7. Retries, Timeouts, and Network Errors: Design by Operation Type

AWS SDK v2 supports configurable client retry strategies and timeouts. Default retry behavior can differ by version and mode; do not hard-code assumptions about retry counts without checking actual configuration.

### 7.1. Why the SDK Retries

Within its retry strategy and service semantics, the SDK can retry transient errors such as throttling or eligible network/server faults. However:

- **Not every error is retryable.** `AccessDenied` from missing IAM permissions is usually not fixed by retrying.
- **Not every payload replays safely.** With streaming uploads, ensure the request body/stream supports replay under your SDK and transport.
- **Not every operation is idempotent.** If a mutating request succeeds and the response is lost, retrying can duplicate side effects; design APIs and service idempotency keys accordingly.
- **Retries increase latency and load.** Long timeouts combined with multiple retries can breach business SLAs.

### 7.2. Do Not Confuse Timeout Levels

| Level | Configured where? | Example failures |
| --- | --- | --- |
| TCP/TLS handshake | HTTP transport | Unreachable endpoint, proxy/firewall, handshake error |
| Pool wait | HTTP transport, especially async | `connectionAcquisitionTimeout` |
| Read/write | HTTP transport | Slow server, long polling, streaming |
| Single request attempt | SDK client override | One API attempt exceeds limit |
| Entire SDK API call | SDK client override | Overall deadline exceeded including retries |
| Full user HTTP request | Spring MVC/WebFlux or gateway | Controller/gateway times out while AWS SDK still runs |
| Message processing | SQS listener/queue | Visibility timeout, redelivery, DLQ |

Define business SLAs first, then budget timeouts across each layer. End-to-end budgets must also cover database access, payload serialization, local I/O, S3/SQS calls, and post-processing.

### 7.3. Never Use Retries to Mask Misconfiguration

If `S3Client` targets the wrong endpoint, hits an invalid TLS certificate, or points at the wrong region, raising retry counts merely delays failure detection. For HTTP 403 IAM errors or SQS `QueueDoesNotExist`, inspect identity, region, ARN, queue URL, and resource policies first.

## 8. Region, Endpoint, and AWS Request Signing Are Three Separate Concepts

### 8.1. Region

`Region` is the AWS region targeted by the client, e.g., `ap-southeast-1`. When omitted on the builder, the SDK can use the region provider chain (Java system property `aws.region`, `AWS_REGION`, shared profile, and environment metadata per SDK v2 order).

### 8.2. Endpoint

An endpoint is the network address receiving requests. By default, the SDK resolves the service endpoint from the region and other rules. SQS, STS, DynamoDB, and S3 endpoints can follow distinct construction rules.

`endpointOverride(URI)` instructs the SDK to target a specific URL, commonly used in tests or when a controlled endpoint is needed. **Endpoint override does not set the region, create credentials, or skip request signing.**

### 8.3. Signing

The AWS SDK typically signs requests using AWS Signature Version 4 or the service-appropriate signing scheme. Region and endpoint can participate in signing scope and request routing. If an endpoint override points to the wrong region while the client signs for another region, real AWS requests risk signature mismatches, redirects, or service-specific errors.

**Example:** setting `region(Region.US_EAST_1)` on `S3Client` while the bucket actually lives in Singapore. Even with valid credentials and DNS resolution, requests risk errors or redirects due to bucket region mismatch. Identify the resource's region rather than picking the developer's local timezone.

~~~mermaid
flowchart LR
    I["Credentials provider: role"] --> S["Request signing"]
    R["Client region"] --> E["Endpoint resolver"]
    R --> S
    E --> H["URL / Host"]
    H --> S
    S --> T["HTTP transport"]
    T --> A["AWS service / test endpoint"]
~~~

## 9. Default Endpoints, Endpoint Overrides, and Private DNS

### 9.1. Prefer Standard AWS Mechanisms in Production

In production, normally set the **right region** and let the SDK use standard AWS endpoints:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

SqsAsyncClient sqs = SqsAsyncClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();
~~~

If infrastructure uses **VPC endpoints/private DNS**, the SDK often keeps using standard hostnames while VPC DNS/routing steers traffic across the private endpoint. Therefore, **do not assume `endpointOverride(...)` is required solely because a VPC endpoint exists**. Check endpoint type, private DNS, routes, security groups, and VPC endpoint policies for the service.

### 9.2. Endpoint Override for Local Testing

A test client against an S3 emulator:

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

S3Client localS3 = S3Client.builder()
        .region(Region.US_EAST_1)
        .endpointOverride(URI.create("http://localhost:4566"))
        .credentialsProvider(StaticCredentialsProvider.create(
                AwsBasicCredentials.create("test", "test")))
        .serviceConfiguration(S3Configuration.builder()
                .pathStyleAccessEnabled(true)
                .build())
        .build();
~~~

The `test/test` credentials are **fake and test-only**; they cannot replace production IAM roles. In real tests, obtain the URL from the launched container/emulator; `localhost:4566` works only when the client runs in the same network namespace/host as the listening emulator.

### 9.3. An Endpoint Override Is Not a Business Resource URL

`SqsAsyncClient.endpointOverride(...)` targets the **SQS service endpoint**, whereas `SendMessageRequest.queueUrl(...)` specifies the **target queue**. Likewise, `S3Client.endpointOverride(...)` does not replace `bucket(...)` and `key(...)`.

Common mistakes:

- Passing a specific queue's URL as the SQS client's base endpoint.
- Leaving a LocalStack endpoint override active in production.
- Setting an arbitrary region and expecting an endpoint override to fix signing errors.
- Disabling TLS certificate/hostname verification to "fix" endpoint errors.
- Building a separate endpoint per request instead of environment-configured clients.

### 9.4. HTTP and HTTPS

When calling real AWS, **HTTPS/TLS** is the baseline to protect. An `http://...` endpoint in LocalStack examples suits only local emulators or isolated test environments. Never disable TLS validation or bypass certificate verification to connect to production.

For private endpoints or corporate TLS proxies, manage certificate trust chains, hostnames, and proxy settings via approved security configuration. Never deploy a `TrustAllCertificates` configuration into production.

## 10. S3 Specifics: Virtual-Hosted vs. Path-Style Access

S3 supports multiple ways to encode the bucket in HTTP requests. Two common styles:

| Style | Illustrative URL example | Meaning |
| --- | --- | --- |
| Virtual-hosted style | `https://example-bucket.s3.ap-southeast-1.amazonaws.com/key` | Bucket name is part of the hostname |
| Path-style | `https://s3.ap-southeast-1.amazonaws.com/example-bucket/key` | Bucket name is part of the URL path |

The S3 SDK applies endpoint and addressing rules per service, bucket, and configuration. **Never enable path-style across all production environments merely because LocalStack requires it.**

### 10.1. When Is Path-Style Needed?

With many S3 emulators or test endpoints like `http://localhost:4566`, virtual-hosted style generates hostnames like `bucket.localhost` that DNS may fail to resolve. In that case, configure:

~~~java
S3Configuration s3Configuration = S3Configuration.builder()
        .pathStyleAccessEnabled(true)
        .build();
~~~

and pass it to the builder:

~~~java
S3Client client = S3Client.builder()
        .region(Region.US_EAST_1)
        .endpointOverride(URI.create("http://localhost:4566"))
        .serviceConfiguration(s3Configuration)
        .build();
~~~

The second snippet assumes the client already has test-appropriate credentials; a complete test example should configure explicit static **dummy** credentials.

### 10.2. S3 Features with Special Endpoint Rules

When using features such as access points, S3 Transfer Acceleration, dual-stack, Multi-Region Access Points, S3 Express One Zone, or special ARN formats, endpoint resolution and signing follow dedicated rules and require corresponding client/SDK support.

Therefore, a **global `endpointOverride`** can break S3's built-in endpoint resolution behavior. Before setting a custom endpoint, read the documentation for that feature and SDK release, and test each target operation rather than extrapolating from a simple `PutObject`.

### 10.3. S3 Bucket Region

Bucket names are unique within a partition under service rules, yet S3 operations still depend on the bucket's region and endpoint. If an application accesses buckets across multiple regions, manage clients by **resource region** or supported SDK mechanisms; never mutate process-wide `AWS_REGION` expecting existing clients to switch regions.

## 11. SQS Specifics: Client Endpoint, Queue URL, and Long Polling

An SQS queue URL typically encodes region, account ID, and queue name. Illustrative example:

~~~text
https://sqs.ap-southeast-1.amazonaws.com/111122223333/order-events-dev
~~~

When calling SQS:

~~~java
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

public class OrderQueueSender {
    private final SqsAsyncClient sqs;
    private final String queueUrl;

    public OrderQueueSender(SqsAsyncClient sqs, String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public void send(String payload) {
        sqs.sendMessage(request -> request
                .queueUrl(queueUrl)
                .messageBody(payload))
            .join();
    }
}
~~~

`join()` only illustrates waiting for completion in a short sample; in real async code, return futures or handle completion non-blockingly per service architecture.

If `SqsAsyncClient`'s region mismatches the queue's region, the SDK or service may return endpoint, queue, or authorization errors depending on the call. **Never point a client at one region and a queue URL in another region without verifying the behavior.**

### 11.1. Long Polling and HTTP Timeouts

When calling `ReceiveMessage` with `waitTimeSeconds(20)`, the server may wait up to roughly 20 seconds before returning messages or an empty response per SQS behavior. Read timeout and API attempt timeout must be **greater than this wait time plus network overhead**. If too short, consumers repeatedly time out, retry, and generate unnecessary load.

In Spring Cloud AWS SQS listeners, polling, concurrency, acknowledgement, visibility timeout, and DLQ settings must be evaluated alongside HTTP transport settings. Increasing Netty `maxConcurrency` alone does not increase business handler parallelism or queue limits.

### 11.2. LocalStack SQS: Queue URLs Must Match the Test Endpoint

With an emulator, `CreateQueue`/`GetQueueUrl` can return a queue URL shaped by how the emulator builds hostnames and networking. Ensure the URL used by the client matches the test endpoint and runtime environment (host vs. container); never copy production queue URLs into tests or vice versa.

A reliable test pattern is creating the queue during test setup, obtaining the queue URL directly from the test endpoint, and injecting it into the test context's handlers and publishers.

## 12. Integrating with Spring Boot and Spring Cloud AWS

### 12.1. When to Let AWSpring Auto-Configure?

If an application targets **one region** and uses a standard set of credentials and endpoints per service, letting AWSpring create beans reduces boilerplate:

- Add the required AWSpring starters (e.g., S3/SQS).
- Supply region/credentials via appropriate environment sources.
- Inject `S3Template`, `SqsTemplate`, or auto-configured SDK clients depending on release.
- Let the SDK default credential chain pick up ECS/EKS/EC2 roles or dev profiles.
- Consult AWSpring's auto-configuration documentation for supported properties, client beans, and customization hooks.

Example region configuration in common AWSpring 3.x releases:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION}

app:
  aws:
    s3:
      bucket: ${APP_S3_BUCKET}
    sqs:
      queue-url: ${APP_SQS_QUEUE_URL}
~~~

This is **illustrative configuration**, containing no static access keys. `AWS_REGION`, bucket, and queue URL must be supplied by the deployment environment. Spring Cloud AWS settings and custom client code can partially override default SDK behavior; inspect the actual beans before drawing conclusions.

### 12.2. Why Not Use One Endpoint for Every Service?

S3, SQS, DynamoDB, and STS have distinct endpoint resolution, API operations, and network characteristics. If S3 tests target an emulator while SQS targets real AWS staging, applying a global endpoint override across all clients can misroute requests, causing network errors or wrong-environment side effects.

Depending on the release, AWSpring may provide **per-service endpoint properties** or specific client builder customizers. Check exact property names and precedence in the reference guide for your version; never assume `spring.cloud.aws.endpoint` or any arbitrary property name works for every starter.

Application-level configuration can cleanly separate concerns:

~~~yaml
app:
  aws:
    archive:
      region: ${APP_ARCHIVE_REGION:ap-southeast-1}
      bucket: ${APP_ARCHIVE_BUCKET}
    events:
      region: ${APP_EVENTS_REGION:ap-southeast-1}
      queue-url: ${APP_EVENTS_QUEUE_URL}
~~~

This layout isolates regions and resources by use case. Adapters select the right client and reduce the risk of mixing buckets or queues across environments.

### 12.3. Declaring Named Service Client Beans

When you need a **dedicated** S3 client for an archive bucket, declare a named bean:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
public class ArchiveS3Configuration {

    @Bean(name = "archiveS3Client", destroyMethod = "close")
    S3Client archiveS3Client(
            @Value("${app.aws.archive.region}") String region) {

        return S3Client.builder()
                .region(Region.of(region))
                .httpClientBuilder(ApacheHttpClient.builder()
                        .maxConnections(40)
                        .connectionTimeout(Duration.ofSeconds(3)))
                .overrideConfiguration(ClientOverrideConfiguration.builder()
                        .apiCallTimeout(Duration.ofSeconds(40))
                        .build())
                .build();
    }
}
~~~

In the adapter, inject with a qualifier to guarantee the exact client used:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.s3.S3Client;

@Service
public class ArchiveMetadataReader {

    private final S3Client archiveS3;

    public ArchiveMetadataReader(
            @Qualifier("archiveS3Client") S3Client archiveS3) {
        this.archiveS3 = archiveS3;
    }

    public long getSize(String bucket, String key) {
        return archiveS3.headObject(request -> request
                .bucket(bucket)
                .key(key))
            .contentLength();
    }
}
~~~

**Interaction with auto-configuration matters:** declaring your own `S3Client` bean can cause AWSpring auto-configuration to **back off** or wire differently depending on version and conditions. If the application needs both a default client for `S3Template` and a separate `archiveS3Client`, explicitly configure which client/template uses which bean and test context startup; do not assume giving a bean a different name preserves the default bean.

Problems involving multiple regions, roles, or endpoints should use adapters/factories with explicit ownership rather than letting an implicit global bean serve all resources.

### 12.4. Settings to Separate by Environment

| Item | Local test | Staging/production |
| --- | --- | --- |
| Credentials | Fake credentials with emulator; AWS profile when calling real sandbox | IAM role/workload identity |
| Region | Explicitly specified test region | Real resource region |
| Endpoint | Emulator/test endpoint supplied by test runtime | Default AWS endpoint or intentionally configured private endpoint |
| HTTP transport | Reproducible setup without extreme throughput demands | Tuned after load/latency measurement |
| Timeout/retry | Shorter and easier to diagnose in tests | Aligned with SLA, long polling, side effects, and throughput |
| Resource | Isolated test buckets/queues | Environment-specific ARNs, resource names, and accounts/regions |

## 13. HTTP Proxies, TLS, and VPC Endpoints

In enterprise environments, egress traffic may traverse a proxy or VPC endpoint. Distinguish the **AWS service URL** from the **network path reaching that URL**.

### 13.1. When Is a Proxy Needed?

If a developer workstation or container inside a corporate network must route through an HTTP proxy, configure proxy settings on the active transport (Apache, Netty, or equivalent HTTP client mechanism), along with appropriate no-proxy rules.

Several transports provide dedicated `ProxyConfiguration`; host, scheme, user/password, and TLS settings must follow your SDK version's documentation. Never put proxy usernames/passwords in source code or logs.

When proxy errors happen, inspect:

1. DNS and reachability from the exact process/container.
2. Proxy URL and no-proxy domains.
3. TLS root CA/hostname verification along the active path.
4. Client region/endpoint/signing.
5. IAM permissions, only after confirming requests actually reach the AWS service.

### 13.2. VPC Endpoints

A **VPC Gateway Endpoint** for supported services (such as S3/DynamoDB in supported setups) and an **Interface Endpoint/PrivateLink** for applicable services provide private network paths to AWS services.

Having a VPC endpoint does not automatically allow every service request: security groups, route tables, endpoint policies, DNS/private DNS, and IAM all still apply. Never work around an endpoint policy `AccessDenied` by swapping in static credentials.

If private DNS already routes standard service hostnames to the endpoint, SDK clients can continue using default regions and endpoints. Use `endpointOverride(...)` only when network/endpoint requirements explicitly demand it.

### 13.3. TLS and Certificate Controls

Never disable TLS verification in production. When using internal certificates or TLS-terminating proxies, provide the proper trust store and verify hostname/certificate chains. Sensitive data such as secrets, credentials, and personal payloads must not be written to wire logs.

## 14. Testing Client and Endpoint Configuration

Effective testing separates **business logic tests**, **HTTP wiring tests**, and **real AWS behavior tests**.

### 14.1. Unit Tests: Mock/Fake at the Adapter Boundary

Business services depend on an interface like `DocumentStore` or `EventPublisher`. Unit tests use fake adapters to verify business logic, response/exception handling, and idempotency without needing AWS credentials or networking.

### 14.2. Integration Tests: LocalStack and Test-Scoped Endpoints

With Testcontainers/LocalStack or an appropriate emulator:

1. Obtain the test endpoint once the container starts, using the runtime's mapped host and port.
2. Build test clients with the endpoint override, explicit region, and **test-only fake credentials**.
3. For S3 emulators, enable path-style if the emulator hostname does not support virtual-hosted style.
4. Create test buckets/queues, run Put/Get or Send/Receive, and clean up test data.
5. Verify Spring beans/templates/listeners are using **the test client itself**.

A compact test factory:

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

public final class TestS3ClientFactory {
    public static S3Client create(URI endpoint) {
        return S3Client.builder()
                .endpointOverride(endpoint)
                .region(Region.US_EAST_1)
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
                .serviceConfiguration(S3Configuration.builder()
                        .pathStyleAccessEnabled(true)
                        .build())
                .build();
    }
}
~~~

**Limitation:** LocalStack cannot fully represent IAM role trust, SCP/KMS policies, all endpoint features, VPC networking, or real AWS quotas/throttling. Do not extrapolate from emulator tests that "production IAM is right."

### 14.3. Integration/Smoke Tests on a Sandbox AWS Account

On a restricted test AWS account:

- Use the **workload's actual role** running the test (ECS task role, EKS Pod Identity/IRSA, EC2 instance profile, CI OIDC).
- Confirm account and principal via STS `GetCallerIdentity` where possible; cross-check region/endpoint/resources.
- Execute small S3/SQS requests and inspect responses, latency, and retry/throttling behavior.
- Observe connectivity with proxies, VPC endpoints, or custom trust stores enabled.
- For SQS, verify long polling and visibility timeouts; for S3, verify object size, metadata, encryption/KMS, and streaming if used.
- Block production writes via IAM/resource policies and check account/region allowlists.

A smoke test run with a laptop profile **does not prove** ECS/EKS runtime is using the intended role.

## 15. Troubleshooting by Symptom

| Symptom | Layer to inspect first | Verification step |
| --- | --- | --- |
| `NoClassDefFoundError` for Apache/Netty transport | Dependencies/runtime classpath | BOM, SDK modules, `runtimeClasspath` |
| Client builds but cannot find credentials | Identity provider | ECS/EKS/EC2 role, local profile, provider chain |
| `Unable to load region` | Region | `aws.region`, `AWS_REGION`, profile, builder, AWSpring properties |
| DNS fails resolving emulator bucket hostname | S3 endpoint resolution | Path-style, host mapping, endpoint override |
| `UnknownHostException` / connection refused | Network/endpoint | URL, host/port, container networking, DNS, proxy |
| TLS handshake/certificate failure | TLS/HTTP transport | Trust store, endpoint hostname, proxy, CA |
| `SignatureDoesNotMatch` | Signing/region/endpoint/clock/credentials | Signing region, endpoint, system clock, credential type |
| `AccessDenied` from S3/SQS | IAM/resource/KMS policy | STS principal, action, ARN, policy/conditions |
| SQS `QueueDoesNotExist` | Queue URL/region/account | Real queue, client region, queue URL, and IAM |
| SQS long polling repeatedly times out | Read/API timeout | `waitTimeSeconds`, Netty read timeout, API call attempt |
| Connection pool timeout | HTTP transport/concurrency | Pool capacity, `maxConcurrency`, backpressure, connection acquisition |
| Large S3 upload aborts | Streaming/timeout/memory | API call timeout, body replay, HTTP transport, multipart strategy |
| LocalStack passes, production fails | Emulator/AWS differences | IAM, KMS, VPC endpoint, real region/service behavior |

Do not change timeout, proxy, region, and credential parameters simultaneously while debugging: changing multiple variables at once prevents isolating the root cause.

### 15.1. Operational Observability

Track:

- Latency by service operation, status/error codes, and retry counts.
- Connection pool wait times, concurrent request counts, and timeout rates.
- SQS backlog, processing duration, visibility timeouts, and DLQ depth.
- S3 upload/download throughput, payload sizes, streaming errors, and KMS errors.
- Region/endpoint **environment category** (without logging secrets, session tokens, or sensitive payloads).
- Correlation between user requests, AWS request IDs, and trace/correlation IDs.

The AWS SDK and HTTP clients can expose metrics/diagnostics depending on version. Integrate with Micrometer/observability intentionally, avoiding body logging that captures sensitive payloads.

## 16. Practice: Designing Clients for a Multi-Service Application

**Scenario:** A Spring Boot service `document-api`:

- Uploads documents to an S3 bucket in `ap-southeast-1`.
- Publishes events to an SQS queue in the same region.
- Reads secrets from Secrets Manager at startup or on demand.
- Runs locally with LocalStack for S3/SQS, while staging/production call real AWS using IAM roles.
- Has two workloads: a synchronous API with moderate request volume and a high-throughput queue worker.

### Task A — Choose Clients and Transports

1. Choose `S3Client` or `S3AsyncClient` for uploads based on file size, server model, and concurrency; explain trade-offs.
2. Choose `SqsAsyncClient` for publisher/worker if appropriate; propose an initial `maxConcurrency` and **how to benchmark it** rather than claiming a fixed magic number.
3. Choose Apache or URLConnection for sync clients and Netty for async clients; explain dependency and lifecycle impacts.
4. List the minimum metrics to monitor: connection timeout, read timeout, API call attempt/total, and retry count.

### Task B — Spring and Endpoint Configuration

1. Define properties `app.aws.s3.region`, `app.aws.s3.bucket`, `app.aws.sqs.region`, `app.aws.sqs.queue-url`.
2. For production, set the real region and let the SDK use standard endpoints unless a VPC endpoint/custom URL explicitly requires otherwise.
3. For LocalStack, override endpoints per service within test scope; set fake credentials and S3 path-style.
4. Ensure the Spring context injects the right client beans into the S3 adapter and SQS listener; check how custom beans affect AWSpring auto-configuration.

### Task C — Real-World Incidents

| Incident | Analysis required |
| --- | --- |
| S3 test fails DNS on bucket hostname | Which host is virtual-hosted style targeting? Are path-style and host mapping needed? |
| SQS receive long polling times out after 5 seconds | Do `WaitTimeSeconds` and HTTP read/API timeouts conflict? |
| Application gets `AccessDenied` despite reaching endpoint | Which IAM principal signs requests; which action/ARN/resource policy/KMS applies? |
| Inside ECS, client calls `localhost:4566` | How did test endpoint configuration leak into production? |
| Raising pool from 50 to 500 fails to increase throughput | Where is the bottleneck: handlers/CPU/DB/SQS throttling/backpressure? |
| 200 MB upload fails while small `PutObject` works | How are request body, streaming, multipart, timeouts, and memory footprint handled? |

### Task D — Testing

- Unit tests for adapters, mocking AWS SDK errors.
- Integration tests via LocalStack for S3/SQS with test-only endpoints and credentials.
- Sandbox smoke test with the right role, region, and resource ARNs.
- Controlled load test measuring pooling, concurrency, timeouts, retries, and memory.
- Tests for TLS/proxy/network failures ensuring logs contain zero keys or tokens.

**Passing criteria:** Your design separates service clients from HTTP transport, specifies endpoints/regions/credentials clearly, distinguishes blocking vs. async, explains Spring bean wiring, and grounds timeout/pool sizing in measurement. Most importantly, local tests must never mutate production resources.

## 17. Conceptual Comparison with Azure and Google Cloud

In the multi-cloud integration module, AWS, Azure, and Google Cloud all provide SDK clients connecting to managed services, though endpoint resolution and HTTP pipelines differ.

| Need | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| SDK clients | `S3Client`, `SqsAsyncClient`, `DynamoDbClient` | Azure SDK clients such as Blob/Queue/Service Bus clients by service | Google Cloud Java clients such as Storage, Pub/Sub by service |
| Default credentials | `DefaultCredentialsProvider` and IAM roles/STS | Azure credential chains/Managed Identity depending on client | Application Default Credentials and service account/workload identity |
| HTTP transport | Apache, URLConnection, Netty, CRT depending on SDK client type | Azure SDK pipeline/HTTP client options | HTTP/gRPC transports depending on service library |
| Resource endpoint | Region and service endpoint; S3 has addressing rules | Resource URL, service endpoint, and region by service | Project/location and service endpoints by service |
| Test emulator | LocalStack or appropriate emulator | Azurite or appropriate service emulator | Per-service emulators (e.g., Pub/Sub emulator) where available |

The shared principle is managing **identity, endpoints, transport, timeouts, and retries**. You cannot copy AWS `endpointOverride(...)` verbatim to Azure/GCP clients; you must follow each SDK's API, auth model, and semantics.

## 18. Key Takeaways

When integrating Spring Boot with AWS, configure in sequence:

1. Identify the **service and client type** (blocking or async).
2. Choose the **region**, **credential provider**, and environment-appropriate IAM mechanism.
3. Let the **SDK's standard endpoint resolver** handle production, overriding only for verified requirements.
4. Select **HTTP transport**, timeouts, pools, and retries based on request patterns and measurements.
5. Manage **client lifecycle** in Spring without accidentally displacing AWSpring auto-configured beans.
6. Separately test **wiring/endpoints**, **real IAM/KMS/networking**, and **performance**.

**AWSpring** supports the Spring programming model; **AWS SDK for Java 2.x** provides service clients and HTTP transports; **AWS** enforces routing, authentication, IAM, quotas, and service behavior. Customizing clients per service—rather than applying one configuration to every request—keeps applications stable and diagnosable as you scale across S3, SQS, data stores, secrets, and multi-cloud architectures.
