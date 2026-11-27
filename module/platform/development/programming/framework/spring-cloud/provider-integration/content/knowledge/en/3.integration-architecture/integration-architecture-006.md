# Client Lifecycle, Reusability, and Resource Cleanup

A Spring Boot application may make thousands of calls to Amazon S3, Azure Blob Storage, or Google Cloud Storage over its uptime. If a new SDK client is created on every call, the application repeatedly configures credentials, initializes transports, opens or acquires connections, and eventually deals with unreleased network resources. Conversely, if a client shared across concurrent requests is closed too early, in-flight requests can fail. Therefore, deciding **who creates the client, who can share it, and who is responsible for closing it** is part of integration architecture—not merely a cleanup step at program exit.

This lesson belongs to the **Integration Architecture** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. Its practical scope is integrating Spring Boot with managed services on **AWS, Azure, and Google Cloud** through the corresponding Spring Cloud libraries: identity and permission configuration, storage, messaging, data, secrets, integration testing, and provider comparison. This lesson focuses on the lifecycle of **SDK clients, connections, and I/O resources** inside the Spring application context, including synchronous clients, asynchronous clients, and background listeners.

## 1. Learning Outcomes

After this lesson, you can:

- Distinguish the lifecycles of a **Spring bean**, **SDK client**, **HTTP/gRPC transport**, **connection pool**, **credential provider**, and per-request resources.
- Explain why **clients are typically reused** across requests, while identifying the conditions under which sharing a client is genuinely safe.
- Configure a Spring-owned AWS SDK v2 client and close it cleanly when the application context shuts down.
- Distinguish between cases where the SDK owns its transport and where the application passes in a pre-built transport.
- Recognize resource-cleanup differences across AWS SDK, Azure SDK, Google Cloud client libraries, messaging listeners, and database pools.
- Design graceful shutdown, test client closure, and diagnose connection, thread, buffer, or resource-handle leaks.

## 2. Lifecycle from Startup to Shutdown

In an application using Spring Cloud starters, a client typically goes through four phases:

1. **Creation and configuration:** Spring Boot reads properties, evaluates auto-configuration, creates SDK client/template beans, and wires region/project/account, credential providers, and transports.
2. **Ready to serve:** Beans are injected into adapters/services. Some SDKs fetch credentials and initialize connections **when executing the first call**; Spring starting up successfully does not prove endpoints or cloud permissions are valid.
3. **Runtime reuse:** Multiple requests/workers share the same client under its thread-safety contract, while connection pools, executors, credential providers, or gRPC channels operate underneath.
4. **Stop and release:** The system stops accepting new work, drains or halts in-flight work within a time limit, and then closes the components the application owns.

~~~mermaid
flowchart LR
    A[Boot: read config] --> B[Auto-config / @Bean]
    B --> C[SDK client bean]
    D[Credential provider] --> C
    T[HTTP / gRPC transport] --> C
    C --> E[Spring service / adapter]
    E --> R[Many requests and background workers]
    R --> CLOUD[Managed service]
    Z[ApplicationContext shutdown] --> STOP[Stop accepting new work]
    STOP --> DRAIN[Wait for in-flight tasks with timeout]
    DRAIN --> CLOSE[Close owned clients]
    CLOSE --> TRANS[Release owned transports]
~~~

**Closing order** matters: a listener still receiving messages should not lose its client before finishing ack/cleanup; an SDK client actively calling the cloud should not have its transport closed underneath it. At runtime, the actual call path still goes **service → adapter → SDK → cloud**, while Spring is responsible for creating and managing the beans.

## 3. Resources Commonly Mistaken as One

| Component | Role | Typical Owner | When to Close |
| --- | --- | --- | --- |
| **Spring bean** | Object managed by ApplicationContext | Spring context | When the context closes, via valid destruction callbacks |
| **SDK service client** | API calling a cloud service | Spring bean or direct creator | Per SDK contract; many AWS SDK v2 clients have **close()** |
| **HTTP client / connection pool** | Connections, sockets, TLS, keep-alive, concurrent I/O limits | SDK or whoever passed the transport in | When the **owner** shuts down, after all sharing clients stop |
| **gRPC channel / executor** | Connection and background thread management for certain SDKs | Client library or app config | Per the library's specific shutdown/close API |
| **Credential provider** | Locates, acquires, and refreshes identities/tokens | SDK or application | If the provider actually owns closeable resources, per its contract |
| **Listener container / subscriber** | Polls/receives messages and invokes handlers | Spring Cloud or application | Stop receiving messages and finish acks before closing the client |
| **Response stream / file handle** | Holds data for **a single operation** | Code invoking the operation | Close as soon as reading/writing finishes, typically with try-with-resources |

Never equate **GC reclaiming Java objects** with **releasing bounded network resources**. Even when an object has no remaining references, threads, sockets, connection pools, or native buffers can outlive expectations. Likewise, not every provider client implements the same closing interface: always check the API and guidance for the **exact library and version**.

## 4. Reusability: Clients Differ from Request Builders and Response Streams

Core service clients in **AWS SDK for Java v2** are designed for reuse and support many concurrent calls; for example, **S3Client** does not need to be recreated for every upload. Many clients provided by **Azure SDK for Java** are also designed to be reusable/thread-safe. For **Google Cloud Java client libraries**, check the thread-safety and resource-management behavior of the exact client and transport in your project.

The safety of an SDK client **does not imply** every companion object is thread-safe:

- **Request builders** are mutable configuration objects: create a fresh builder per operation rather than sharing and mutating one across threads.
- **Request/response streams**, iterators, upload sessions, and per-request stateful objects have their own lifecycles and generally must not be shared concurrently.
- **Clients** can be reused, yet **pools** still bound connections, streams, or concurrent calls. Thread-safe does not mean infinite capacity.
- **Credential providers** typically have their own caching/refresh strategies. You do not need to recreate the client every time a token expires if the SDK/provider is designed to refresh automatically.
- **Clients are bound to specific regions, endpoints, accounts, and identities**. Never share a client across distinct security boundaries if sharing could mix permissions or data.

Simple example of two adapters sharing a single Spring-managed **S3Client**:

~~~java
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.s3.S3Client;

@Component
public class InvoiceObjectAdapter {
    private final S3Client s3;

    public InvoiceObjectAdapter(S3Client s3) {
        this.s3 = s3;
    }
}

@Component
public class ReportObjectAdapter {
    private final S3Client s3;

    public ReportObjectAdapter(S3Client s3) {
        this.s3 = s3;
    }
}
~~~

Both adapters receive the **exact same singleton bean** when the context has a single matching **S3Client** bean. The snippet above only illustrates injection; business methods invoke different APIs through the **s3** field. **Singleton** is the default Spring bean scope, but the SDK does not magically become a singleton if code manually calls **S3Client.builder().build()** on every request.

## 5. Letting a Spring Cloud Starter Own the SDK Client When No Customization Is Needed

With **Spring Boot 3 + Spring Cloud AWS 3.x**, the S3 starter can provide SDK client beans through auto-configuration when matching conditions are met. Illustrative Maven declaration, with version managed by a compatible BOM:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
app:
  storage:
    bucket: ${APP_STORAGE_BUCKET}
~~~

In this configuration, **spring.cloud.aws.region.static** serves the starter's AWS configuration; **app.storage.bucket** is an application-defined property. The bucket is not a credential; prefer IAM roles/workload identity and least-privilege permissions when running on the cloud. When the starter-created client meets your needs, **inject the bean** rather than declaring another bean solely to access the SDK.

Spring Boot manages the lifecycle of beans created by configuration. However, **which client types a starter creates, which resources it closes automatically, and whether a default client can be replaced by a user-defined bean depend on the version**. Always inspect the condition report, bean graph, and the exact starter's documentation. A bean present at startup does not prove credentials or IAM/RBAC have been validated.

## 6. Defining an AWS SDK Client Manually and Delegating Closure to Spring

If you need builder control or settings unsupported by the starter, you can register **S3Client** as a singleton bean yourself:

~~~java
// AwsClientConfiguration.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
public class AwsClientConfiguration {

    @Bean(destroyMethod = "close")
    S3Client s3Client(@Value("${app.aws.region}") String region) {
        return S3Client.builder()
            .region(Region.of(region))
            .build();
    }
}
~~~

~~~yaml
app:
  aws:
    region: ap-southeast-1
~~~

**@Bean(destroyMethod = "close")** instructs Spring to call **S3Client.close()** when the bean is destroyed, normally as the application context closes. Spring can also infer **close/shutdown** methods for many **@Bean** declarations, yet explicit declaration makes lifecycle ownership immediately visible to readers. The bean is instantiated once in singleton scope, reused repeatedly, and closed only when the context terminates. Spring does not call **close** after every adapter method call.

The example **does not hard-code access keys**. When no credential provider is specified, the AWS SDK uses its default environment-based credential lookup mechanism. You must grant specific read/write permissions to the workload. If a Spring Cloud AWS starter is also present, register a custom client only after verifying **@ConditionalOnMissingBean** or equivalent conditions: do not assume every starter version backs off automatically.

**Common pitfall:** Using **try-with-resources** to create and close an S3Client makes sense in a CLI tool or standalone short-lived job:

~~~java
try (S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build()) {
    // Perform operations for a short-lived task.
}
~~~

In a continuously serving REST controller or message handler, creating a client inside a **try** block per request causes connection/resource churn and loses pooling benefits. Once a bean is owned by Spring, **never call s3.close() inside a handler**: other requests may still be using that bean.

## 7. Transport Ownership: Builder vs. Pre-Built Client Instance

The SDK client is not the only resource. AWS SDK v2 can use an HTTP transport **created by the SDK from a builder** or an **HTTP client instance supplied by the application**. These two styles carry different closing responsibilities.

### 7.1. SDK Manages the Builder-Created HTTP Client

~~~java
// An alternative to the S3Client configuration in section 6.
@Bean(destroyMethod = "close")
S3Client s3Client(@Value("${app.aws.region}") String region) {
    return S3Client.builder()
        .region(Region.of(region))
        .httpClientBuilder(
            ApacheHttpClient.builder().maxConnections(64))
        .build();
}
~~~

This snippet requires imports for **ApacheHttpClient**, **S3Client**, **Region**, **@Bean**, **@Value**, and the transport dependency **software.amazon.awssdk:apache-client** (version aligned via AWS SDK BOM). When passing **httpClientBuilder(...)**, the SDK creates and owns the internal HTTP client; closing **S3Client** closes the transport it owns per the AWS SDK v2 contract.

You do not necessarily need to configure the connection count as shown. Proper values depend on request concurrency, I/O latency, payload sizes, quotas, and application capacity. If defaults suffice, letting the SDK pick an HTTP transport via compatible dependencies/config is usually simpler.

### 7.2. Application Owns a Shared HTTP Client

If multiple SDK clients need to share the same HTTP transport, the application can expose it as a **separate bean**:

~~~java
// AwsSharedTransportConfiguration.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.http.SdkHttpClient;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sqs.SqsClient;

@Configuration(proxyBeanMethods = false)
public class AwsSharedTransportConfiguration {

    @Bean(destroyMethod = "close")
    SdkHttpClient sharedAwsHttpClient() {
        return ApacheHttpClient.builder()
            .maxConnections(80)
            .build();
    }

    @Bean(destroyMethod = "close")
    S3Client s3Client(
            SdkHttpClient sharedAwsHttpClient,
            @Value("${app.aws.region}") String region) {
        return S3Client.builder()
            .region(Region.of(region))
            .httpClient(sharedAwsHttpClient)
            .build();
    }

    @Bean(destroyMethod = "close")
    SqsClient sqsClient(
            SdkHttpClient sharedAwsHttpClient,
            @Value("${app.aws.region}") String region) {
        return SqsClient.builder()
            .region(Region.of(region))
            .httpClient(sharedAwsHttpClient)
            .build();
    }
}
~~~

This configuration **replaces** the configuration in section 6; do not define **S3Client** in both classes simultaneously. It requires AWS SDK **s3**, **sqs**, and **apache-client** dependencies with matching SDK versions; **spring-cloud-aws-starter-s3** or **-sqs** may pull in related dependencies, so verify the actual build. Both S3Client and SqsClient receive the same **SdkHttpClient instance**. When passing **httpClient(instance)**, **the AWS SDK is not responsible for closing the caller-managed instance**. Therefore Spring is instructed to close all three beans; when the context destroys beans, dependent clients must stop before the transport bean is closed.

<u>Ownership rule:</u> **Whoever creates and owns a resource closes it, after every consumer of that resource has stopped.** Spring normally tracks dependencies between beans, so injecting the transport into client beans establishes the proper destruction order. If you use a static singleton or pass a transport from outside the context, establish a clear owner; never close it from one adapter while other adapters still use it.

| How HTTP Client Is Passed in AWS SDK v2 | Typical Owner | Closing Action |
| --- | --- | --- |
| No manual HTTP client configured | SDK client | Close SDK client; SDK manages internal transport |
| **httpClientBuilder(builder)** | SDK client | Close SDK client so SDK closes the created transport |
| **httpClient(instance)** | Caller / Spring bean creating transport | Close SDK clients first, then close the caller-owned transport instance |

If a shared transport closes before S3Client, any requests still waiting on I/O can fail. If a shared transport is never closed, connections and executors can remain alive after the application context exits.

## 8. Asynchronous Clients: Managing Netty, Tasks, and Completion Too

Asynchronous clients like **S3AsyncClient** do not hold calling threads while awaiting responses the way sync SDKs do, yet they still hold real resources: event loops, connections, executors, buffers, wait queues, and callbacks. They must be reused and closed by the proper owner just like sync clients.

~~~java
// Standalone configuration for async S3.
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

@Configuration(proxyBeanMethods = false)
public class AsyncAwsClientConfiguration {

    @Bean(destroyMethod = "close")
    S3AsyncClient s3AsyncClient(
            @Value("${app.aws.region}") String region) {
        return S3AsyncClient.builder()
            .region(Region.of(region))
            .httpClientBuilder(
                NettyNioAsyncHttpClient.builder().maxConcurrency(64))
            .build();
    }
}
~~~

This sample requires the **software.amazon.awssdk:netty-nio-client** module at the matching SDK version. Because a **builder** is passed, the SDK client owns the transport and releases it when **S3AsyncClient.close()** runs. Distinguish Netty async transport's **maxConcurrency** from Apache sync transport's **maxConnections**; never copy a single default across all workloads. If you instantiate an **SdkAsyncHttpClient instance** yourself and pass it via **httpClient(instance)**, the caller again owns closing that transport.

**Closing an async client is not proof that all futures have completed.** An async request may already be sent to the cloud without a response back yet; if the app shuts down, the future may complete exceptionally, be cancelled, or lose its result consumer. Before closing the client, stop accepting new work, await critical operations up to a deadline, and record operation IDs so safe retry/reconciliation can run after restart.

Example logical procedure:

~~~text
Shutdown signal
  -> Stop creating/uploading new work
  -> Track and await critical futures (with total timeout)
  -> Mark unfinished work for recovery after restart
  -> Close S3AsyncClient
  -> SDK releases the Netty transport it owns
~~~

Never call **join()** just to “wait for everything” indefinitely in a shutdown hook. Enforce timeouts and rules for handling incomplete items. With Reactor, **cancelling a subscription** also does not guarantee an already-sent request is rolled back in the cloud; idempotency must still be designed at the business layer.

## 9. Azure and Google Cloud: Do Not Apply AWS close() Rules to Every Client

Provider-published libraries **are not uniform** in resource-closing interfaces and transport ownership levels.

| Topic | AWS SDK for Java v2 | Azure SDK for Java | Google Cloud Java libraries |
| --- | --- | --- | --- |
| Typical storage client | **S3Client / S3AsyncClient** | **BlobServiceClient / BlobServiceAsyncClient** | Cloud Storage **Storage** |
| Reusability | SDK service clients are designed to be shared across requests | Azure SDK clients are generally designed to be shared | Verify API and thread-safety for the exact client/version |
| Closing interface | Many SDK clients have **close()** | Not all Blob clients have **close()** by default | Varies by library; storage, gRPC/GAX clients, and transports have different APIs |
| Components that may need shutdown | Apache/Netty HTTP transport, async clients | HTTP transport, Reactor resources, credential resources if owned separately | gRPC channels, background executors, streams/readers/writers, created clients |
| When using Spring Cloud | Spring Cloud AWS auto-config may create clients/templates/listeners | Spring Cloud Azure may create client and credential beans | Spring Cloud GCP may create client/template/subscriber beans |

**Azure Blob Storage:** typically inject the client from the starter or application Spring config and reuse it across operations. Do not write **BlobServiceClient.close()** if that exact class/version does not provide the method. If the application manages its own HTTP client/transport or separate Reactor resources, close **those** according to the library's contract. The same applies to credential providers that may manage connections/token caches; do not assume every `TokenCredential` is `AutoCloseable`.

**Google Cloud:** some storage clients use HTTP/REST, whereas gRPC/GAX-based libraries provide clients and background resources with corresponding **close/shutdown** methods. For instance, a **SecretManagerServiceClient** created via the Google Cloud Java library has a different lifecycle and closing API than **Storage**. When manually creating a channel/provider/executor and passing it into a builder, determine who owns those components. Never assume one universal **close** method exists across every SDK client just because class names end in `Client`.

**Consistent advice:** if a starter creates a bean, verify which resources it already manages; if the application creates custom clients or transports, declare explicit owners and cleanup callbacks matching the API. Test shutdown in a test environment to confirm the process leaves no application-owned threads/connections behind. Where a library does not expose `close` on the client, do not invent fake methods; check which transport or background resource actually requires cleanup.

## 10. Per-Request Resources Must Still Be Closed Early

Reusing an **SDK client** does not mean holding **response streams** forever. When streaming an object from S3, the SDK returns a stream that may hold a network connection open until fully read or closed. Close the stream after every operation:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

public void copyObjectTo(
        S3Client s3, String bucket, String key, OutputStream output)
        throws IOException {
    GetObjectRequest request = GetObjectRequest.builder()
        .bucket(bucket)
        .key(key)
        .build();

    try (ResponseInputStream<GetObjectResponse> input =
            s3.getObject(request)) {
        input.transferTo(output);
    }
}
~~~

In this example, **input** is opened by the method so it is closed via **try-with-resources**. **output** is passed in by the caller, so the method does not close it unless the contract transfers ownership. **S3Client** remains alive to serve other requests. Closing response streams too late can exhaust the connection pool even when the client bean is properly managed.

Similar cases:

- Azure Blob has APIs opening input streams; those streams must be read/closed per Azure SDK guidance.
- Google Cloud Storage may use **ReadChannel/WriteChannel** or streams depending on the client API; channels and streams have their own lifecycles.
- JDBC connections, result sets, and statements must be closed/returned to the pool promptly; Spring Data/JdbcTemplate manages many cases, yet you must never hold a borrowed connection for the entire application lifetime.
- Multipart/resumable uploads and streaming publishers/subscribers require handling cancellation, buffer release, timeouts, and cleanup per the SDK; never assume “singleton client” solves all resource leaks.

## 11. Messaging Listeners and Subscribers Must Stop Before Clients

With **Amazon SQS**, **Azure Service Bus**, or **Google Pub/Sub**, a listener/subscriber typically maintains polling, subscriptions, connections, threads, or background executors. Therefore, the lifecycle does not end merely by closing an SDK client:

~~~mermaid
sequenceDiagram
    participant O as Orchestrator / Spring
    participant L as Listener / subscriber
    participant H as Business handler
    participant C as Messaging client
    participant Q as Cloud queue / topic
    O->>L: Stop accepting new work
    L-->>O: Stop polling/receiving
    L->>H: Await running handlers (bounded)
    H-->>L: Success or retry needed
    L->>Q: Appropriate ack/delete/complete
    O->>L: Stop/close container
    O->>C: Close/shutdown owned client and transport
~~~

These steps illustrate the **desired order**; there is no single unified stop/ack API across all providers. Spring Cloud AWS listeners, Service Bus processors, and Pub/Sub subscribers differ in lifecycles, auto-ack, manual-ack, locks, and visibility timeouts. Verify whether the framework genuinely awaits **async** handler completion before acking.

During shutdown, a message already received but not yet acked may be redelivered once visibility/lock/ack deadlines expire. This is normal under many at-least-once mechanisms. Handlers need **idempotency** by message/event ID rather than trying to stretch shutdown indefinitely. When writing to a database and emitting messages together, **transactional outbox** helps reduce risk across the two systems.

## 12. Database Pools, Secret Clients, and Credential Lifecycles

Not every “cloud client” is a pure HTTP client:

**Managed relational databases:** Spring Boot typically creates a **DataSource** backed by a connection pool such as HikariCP, and Spring Data JPA/JDBC uses that pool. The pool should live as long as the application context, while a connection borrowed from the pool lives only for the transaction/operation. **HikariDataSource.close()** at application shutdown closes the pool; calling **connection.close()** on a borrowed connection normally returns it to the pool via a proxy wrapper rather than closing the DataSource. Never create a new Hikari pool per repository or request.

**Secret managers:** AWS **SecretsManagerClient** has `close` per AWS SDK v2. Azure Key Vault **SecretClient** follows the lifecycle of the Azure SDK and its HTTP transport; do not assume it requires a direct `close` call. Google Cloud **SecretManagerServiceClient** and some GAX/gRPC clients support close/shutdown to release background resources. Pick the right cleanup API for each bean type.

**Credential/token refresh:** service clients can use credential providers that locate and refresh identities automatically. An expiring token does not require closing and recreating the entire SDK client. Truly changing **identity, tenant, endpoint, region, or connection settings** may require a new client; when rotating clients, track callers still using the old client and close it only after they finish. Never log access keys, secrets, tokens, SAS tokens, or connection strings during startup or shutdown.

## 13. Share One Client or Create Multiple Clients?

**One shared client** is usually the first choice when sharing the same provider, region/endpoint, transport configuration, and trust boundary. Yet having strictly one client is not always right:

| Scenario | Option to Consider | Rationale |
| --- | --- | --- |
| Thousands of S3 requests in same region, same identity | One singleton **S3Client** with properly sized pool | Reuses connections and avoids repeated initialization |
| App accesses two AWS regions or accounts concurrently | Two named clients with explicit **@Qualifier** | Region/credentials may differ; avoid implicit bean selection |
| Multiple tenants with distinct identities | Clients scoped per identity/trust boundary, bounded router/cache | Prevents one tenant's permissions from being used for another |
| Multiple SDK clients sharing Apache HTTP transport | Shared **SdkHttpClient** bean if beneficial and supported | Shares pool, but must close by owner and avoid capacity contention |
| One-off CLI job without a long-lived Spring context | Create SDK client for job scope with try-with-resources | Short lifecycle, clear owner |
| Async SDK serving long-running tasks | Managed async client with drain mechanism | Avoids closing while futures or uploads remain incomplete |

With **multi-tenancy**, the biggest hazard is not bean count, but **mixing up identities and data**. If clients are cached per tenant, enforce size limits/TTL/eviction, and close an evicted entry only once no operations still use it. Never issue credentials based solely on a caller-supplied tenant ID without authorization checks. Sharing a single connection pool across disparate workloads can also trigger **noisy neighbor** contention; measure throughput and latency before optimizing.

## 14. From Spring Shutdown to SIGTERM and Kubernetes

Spring Boot provides bean lifecycles and, for supported web servers, HTTP **graceful shutdown**. You can configure:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

**server.shutdown=graceful** asks the web server to stop accepting new requests and let in-flight requests finish within the configured limit. **spring.lifecycle.timeout-per-shutdown-phase** bounds wait time per lifecycle phase; it does **not** automatically track every custom future, message listener, or upload created in the app.

A practical shutdown plan should:

1. Transition the application to not-ready for new traffic (coordinating readiness probes/ingress/load balancers).
2. Stop schedulers and listeners from starting new work; stop polling or subscribing to additional messages.
3. Wait for running tasks **with a bounded timeout**, completing or persisting state for recovery.
4. Handle ack/nack, checkpoints, outbox, or job states per provider semantics.
5. Close listeners/clients and application-owned transports, pools, and executors in dependency order.
6. Exit the process once cleaned up or when the configured deadline expires; never let shutdown hooks hang indefinitely.

On **Kubernetes**, balance **terminationGracePeriodSeconds**, traffic drain time, request drain time, and bean shutdown deadlines. If the orchestrator sends **SIGKILL** before shutdown finishes, resources are terminated forcibly and incomplete messages/operations may require recovery. Graceful shutdown does not replace **idempotency, durable checkpoints, or outbox patterns**.

For Spring beans with custom lifecycles, use **SmartLifecycle**, **@PreDestroy**, or starter callbacks per contract to stop listeners and workers. Avoid writing a custom **@PreDestroy** calling **client.close()** if the client bean is already configured with **@Bean(destroyMethod="close")** and a dedicated owner; closing the same resource in two places obscures ownership.

## 15. Performance Issues and Resource Leak Symptoms

Reusing clients reduces overhead, yet performance still depends on pools and load:

- **Sync HTTP:** waiting threads, acquired/available connections, connection acquisition wait time, timeouts, sockets/TLS.
- **Async HTTP:** event-loop saturation, concurrent requests, pending acquires, in-flight futures, queued callbacks, heap/direct memory.
- **gRPC/GAX:** channel state, in-flight RPCs, executor threads, shutdown timeouts, and background resource state.
- **Database:** active/idle/pending connections, connection wait time, slow queries, and transactions holding connections too long.
- **Messaging:** active consumers, outstanding messages, ack/lock deadlines, redeliveries, dead-letters, and backlog.

Common operational signals:

| Symptom | First Suspect | What to Inspect |
| --- | --- | --- |
| Threads/sockets grow with requests and never drop | Creating SDK/HTTP clients per request or unclosed streams | Bean scope, builder call sites, thread dumps, response streams |
| Connection acquisition timeouts while cloud is healthy | Pool too small, unclosed streams, or concurrency exceeding limits | Acquired/pending pool metrics, connection hold duration |
| Failures right after one task finishes | Some branch called **close()** on a shared client | Ownership, bean destroy settings, task lifecycle |
| Threads remain alive after Spring context closes | Unclosed shared transport/executor/gRPC resource | Bean destroy callbacks, resource creator, shutdown logs |
| Pod stops mid-flight and messages reprocess | Shutdown drain/ack unfinished before SIGKILL | Termination grace period, handler idempotency, consumer stop order |
| Every request creates fresh credentials and runs abnormally slow | Frequent client/provider instantiation | Singleton bean config, credential caching/refresh |
| 403 occurs only for one tenant or region | Client/cache routed to wrong identity/resource | Principal, tenant binding, region, endpoint, resource scope |

Do not try to solve every problem by increasing pool sizes or timeouts. If streams are leaking, enlarging the pool only delays failure. If cloud quotas cap concurrency, raising client/pool limits can worsen throttling. If the error is IAM/RBAC, recreating clients repeatedly grants no extra permissions.

## 16. Testing Lifecycle and Ownership

### 16.1. Testing That Spring Closes Resources on Time

You can test the lifecycle of a custom bean using a fake resource without connecting to AWS/Azure/GCP:

~~~java
// SpringClientLifecycleTest.java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

class SpringClientLifecycleTest {

    static class TrackedResource implements AutoCloseable {
        private final AtomicBoolean closed = new AtomicBoolean();

        boolean isClosed() {
            return closed.get();
        }

        @Override
        public void close() {
            closed.set(true);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ResourceConfig {
        @Bean(destroyMethod = "close")
        TrackedResource trackedResource() {
            return new TrackedResource();
        }
    }

    @Test
    void closesOwnedResourceWhenContextStops() {
        TrackedResource resource;
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(ResourceConfig.class)) {
            resource = context.getBean(TrackedResource.class);
            assertFalse(resource.isClosed());
            assertTrue(resource == context.getBean(TrackedResource.class));
        }

        assertTrue(resource.isClosed());
    }
}
~~~

This test proves Spring invokes the destroy callback on an owned bean when the context closes and returns the same singleton instance within that context. It **does not prove a real SDK manages all HTTP transports properly**; that requires testing with the corresponding beans/configurations and SDK. For multi-client transports, you can use fake/tracked close callbacks to confirm clients stop before the transport, and verify close does not happen between two tasks actively using the resource.

### 16.2. Adapter and Integration Testing

| Level | Verify | Do Not Infer |
| --- | --- | --- |
| Application service unit test | Multiple use cases use injected port/client beans without creating SDKs | Real SDK is connected to the cloud |
| Context test | Correct bean count, singleton scope, qualifiers, destroy methods | IAM/RBAC is valid |
| SDK/adapter test | Request mapping, closed streams, error/timeout handling | Emulator mirrors the cloud completely |
| Integration test | Connectivity to LocalStack/Azurite/test project, body/response handling | Production IAM and networking are identical |
| Cloud smoke + shutdown test | Real identity, least privilege, stopping listeners, closing pools/transports, restart recovery | Redeliveries or duplicate requests will never happen |

With real clouds, use dedicated test buckets/containers/topics, no production secrets, and never enable logs containing credentials. For cleanup, verify SDK clients close only when the Spring context terminates, response streams close after each operation, and listeners process no further messages once stop completes. For async SDKs, also test in-flight futures at shutdown time.

## 17. Practice Exercises

**Exercise 1 — Find the lifecycle bug.** A REST controller calls **S3Client.builder().build()** on every request without closing it. Describe the connection/credential overhead of this approach. Refactor it to an injected Spring singleton bean, specifying where the client is closed and how to monitor the pool.

**Exercise 2 — Who closes the shared transport?** An application creates an **SdkHttpClient** shared between S3Client and SqsClient via **httpClient(instance)**. During shutdown, the S3 adapter calls **sharedHttpClient.close()** before the SQS worker finishes. Identify the ownership error and propose a safe bean graph and shutdown order.

**Exercise 3 — Unclosed stream.** A service calls **s3.getObject** to obtain a **ResponseInputStream**, reads a few bytes, and discards the stream. Explain why connection acquisition timeouts can happen a few dozen requests later even though the SDK client is a singleton. Rewrite it with try-with-resources and state who owns the output stream.

**Exercise 4 — Async shutdown.** A WebFlux service uses **S3AsyncClient**; the pod receives SIGTERM while 50 futures are still in flight. Design the sequence to stop receiving requests, apply a deadline, persist unfinished operation IDs, close the client, and recover after restart. Explain why cancelling a future does not guarantee S3 rolled back.

**Exercise 5 — Provider comparison.** For an application storing objects on AWS, Azure, and GCP, build a table listing which clients have direct **close** methods, which transports have separate owners, and which per-request resources must be closed. Base conclusions strictly on **exact-version** APIs/docs; never assume `BlobServiceClient` or `Storage` share `S3Client`'s `close` method.

**Exercise 6 — Multi-tenant and identity.** Two tenants use distinct credentials and buckets. A singleton **S3Client** is bound to tenant A's role, yet a router reuses it for tenant B. Identify the security risks and propose client selection, bounded caching, closing evicted entries, and permission-isolation tests.

**Exercise 7 — Listeners and transactions.** A Pub/Sub or SQS consumer is processing a message during shutdown. Why must you stop receiving new messages, await/record handler state, and manage acks before closing the SDK? Design idempotency so redelivered messages do not create duplicate business side effects.

## 18. Key Takeaways

- **SDK clients are typically long-lived and reused; request builders, response streams, and borrowed pool connections are short-lived.** Thread-safe does not mean every companion object or arbitrary load can be shared infinitely.
- **Spring beans have explicit owners.** With AWS SDK v2, close Spring-owned `S3Client` via a destroy callback when the context terminates; never close a singleton at the end of each request.
- **With an HTTP client builder**, the SDK normally owns the created transport; **with a pre-built HTTP client instance**, the caller owns it and must close it once no SDK client uses it. Verify the exact SDK and version contract.
- **Azure and Google Cloud have different lifecycle APIs than AWS.** Never assume every client provides `close()`; identify the exact HTTP/gRPC transports, executors, streams, and resources created by your application.
- **Graceful shutdown is an ordered sequence: stop intake, drain, ack/checkpoint, then close clients and pools.** SIGTERM, timeouts, or cancellation do not mean the cloud rolled back an in-flight operation.
- Test **bean creation, instance sharing, closing order, stream cleanup, in-flight operations, and restart recovery**; always protect credentials and enforce IAM/RBAC bounds when sharing clients.
