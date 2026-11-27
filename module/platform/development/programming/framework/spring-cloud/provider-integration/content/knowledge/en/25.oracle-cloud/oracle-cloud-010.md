# Using the OCI Java SDK for Capabilities Beyond Starter Scope

Spring Cloud OCI provides starters to bring Oracle Cloud Infrastructure (OCI) managed services into Spring Boot via familiar APIs. In many cases, abstractions like `Storage`, `Queue`, `Streaming`, `VaultTemplate`, or Spring `Resource` cover business needs. However, some requirements demand operations, request options, or SDK capabilities not yet exposed by a starter.

The OCI Java SDK is the official client layer for OCI service APIs. A Spring application can use the SDK directly in those cases while continuing to rely on Spring Cloud OCI's authentication configuration, region setup, and dependency management. The goal is to extend only the missing piece without leaking OCI SDK types across the entire business domain or creating unmanaged credentials and clients.

This lesson covers when to use the SDK directly, how to obtain clients/credentials from Spring Cloud OCI, how to create dedicated SDK clients for services without a starter, and essential techniques for pagination, waiters, multipart uploads, async clients, retries, timeouts, response streams, error handling, and testing.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish Spring Cloud OCI starters, service abstractions, and the OCI Java SDK.
2. Identify operations not exposed by starters or requiring advanced request options.
3. Choose the right OCI SDK module for each target service.
4. Reuse the authentication provider configured by Spring Cloud OCI.
5. Retrieve raw SDK clients from service beans when supported by the starter.
6. Register additional SDK clients as Spring beans when no matching starter client exists.
7. Configure region, endpoint, timeouts, and HTTP clients.
8. Use request/response builders, paginators, and waiters.
9. Handle large objects with multipart uploads.
10. Choose synchronous or asynchronous SDK clients.
11. Manage retries, idempotency, request streams, and unknown outcomes.
12. Close response streams and clients according to proper lifecycles.
13. Handle `BmcException` and record OCI request IDs.
14. Place the SDK behind an adapter boundary and test independently.
15. Protect IAM, credentials, logs, and data when calling APIs directly.

## 2. Starters and the OCI Java SDK Play Different Roles

Spring Cloud OCI is the Spring Boot integration layer. Starters provide auto-configuration, property binding, beans, and abstractions so applications work with services idiomatically in Spring.

The OCI Java SDK provides clients, request/response models, and operations closer to raw OCI APIs. Several starters also expose their raw SDK client so applications can call operations absent from the abstraction.

| Layer | Responsibility | Examples |
| --- | --- | --- |
| Spring Cloud OCI starter | Configures authentication, region, and service beans | `spring-cloud-oci-starter-storage` |
| Spring abstraction / service bean | Simplified API for common use cases | `Storage`, `Queue`, `Streaming`, `VaultTemplate` |
| OCI Java SDK | Fuller API, detailed request/response models | `ObjectStorage`, `Identity`, `Compute`, `QueueClient` |
| OCI REST API | Underlying HTTP protocol | Used when the SDK lacks an operation or needs custom endpoints |

Not every advanced feature requires dropping down to the SDK. First check whether the existing abstraction suffices. If a service bean already exposes a raw SDK client, prefer reusing that client.

### 2.1. When Should You Stay on the Starter Abstraction?

Use the starter abstraction when:

- The operation already has a clear method.
- No special request options are needed.
- You do not need APIs newer than the SDK version managed by the starter.
- You want simpler, easy-to-mock code.
- You do not need access to service-specific models or response metadata.

For instance, if `Storage` already provides upload/download as needed, do not rewrite the same operation using `PutObjectRequest` and `GetObjectRequest`.

### 2.2. When Should You Use the SDK Directly?

Use the OCI Java SDK when:

- The starter does not expose a required operation.
- You need specific metadata or response headers.
- You need to list object versions, retention rules, replication policies, or pre-authenticated requests.
- You need fine-grained control over conditional requests, ETags, request IDs, or service options.
- You need paginators, waiters, or async clients.
- You need advanced multipart uploads.
- You need to call an OCI service without a corresponding starter.
- You need a capability newer than the Spring abstraction wrapper, after verifying version compatibility.

### 2.3. When Do You Need Raw REST Requests?

Consider raw requests only when an API is not yet exposed by the SDK or requires calling a specialized endpoint not exposed by the SDK client. Even when making raw requests, still use the OCI SDK's request signer. Never hand-roll OCI request signatures via string concatenation.

## 3. API Layer Selection Workflow

~~~mermaid
flowchart TD
    A[Use case needs OCI call] --> B{Starter has suitable API?}
    B -->|Yes| C[Use Spring abstraction]
    B -->|Missing options| D{Starter exposes raw SDK client?}
    D -->|Yes| E[Reuse raw client]
    D -->|No| F{OCI Java SDK has service client?}
    F -->|Yes| G[Create SDK client Spring bean]
    F -->|No| H[Evaluate raw signed request]
    E --> I[Place behind adapter boundary]
    G --> I
    H --> I
    C --> I
    I --> J[Test auth, IAM, retry, and lifecycle]
~~~

A sound decision documents which operation was missing from the starter, why direct SDK usage is necessary, which SDK module is used, and who owns operating that client.

## 4. Choosing OCI SDK Modules and Dependencies

The OCI Java SDK is modularized by service. Examples:

| Service | Common SDK Artifact |
| --- | --- |
| Common/authentication | `oci-java-sdk-common` |
| Identity | `oci-java-sdk-identity` |
| Object Storage | `oci-java-sdk-objectstorage` |
| Compute | `oci-java-sdk-compute` |
| Vault/Secrets | `oci-java-sdk-vault` or corresponding service module per SDK release |
| Streaming | `oci-java-sdk-streaming` |
| Queue | `oci-java-sdk-queue` |
| Logging | `oci-java-sdk-logging` |
| Notifications | `oci-java-sdk-ons` |

Module names can change as OCI adds or splits services. Check Maven Central and Javadocs for your exact SDK release before declaring dependencies.

### 4.1. Dependencies When a Service Starter Is Already Present

If the application already declares a service starter, the corresponding SDK module is usually already in the dependency graph. You can reference SDK types on the compile classpath without adding a separate SDK version.

Example where the application already has the Object Storage starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-storage</artifactId>
</dependency>
~~~

The starter already brings in the necessary modules at the version managed by the Spring Cloud OCI release line. When using `ObjectStorage` directly, do not add a newer OCI SDK dependency solely for classpath visibility.

### 4.2. Dependencies When a Service Has No Starter

If the application needs a service not yet supported by Spring Cloud OCI, declare the matching SDK module:

~~~xml
<dependency>
    <groupId>com.oracle.oci.sdk</groupId>
    <artifactId>oci-java-sdk-identity</artifactId>
</dependency>
~~~

The version is omitted here to illustrate that versions must be governed by the project's dependency management. With the OCI SDK, pick a version compatible with your active Spring Cloud OCI release and other SDK modules in the graph.

If the project has no starter managing the OCI SDK, use the official OCI SDK BOM or version catalog to keep SDK modules aligned.

### 4.3. Do Not Mix OCI SDK Versions

SDK modules share many classes across common runtime, authentication, HTTP clients, and models. Mixing 3.x modules across different patch versions can trigger `NoSuchMethodError`, `NoClassDefFoundError`, or serialization failures at runtime.

Inspect the graph:

~~~bash
mvn dependency:tree -Dincludes=com.oracle.oci.sdk
~~~

Or Gradle:

~~~bash
./gradlew dependencyInsight --dependency oci-java-sdk-common --configuration runtimeClasspath
~~~

Do not force a single SDK module onto a newer version without verifying compatibility with the starter and remaining SDK modules.

## 5. Reusing Authentication from Spring Cloud OCI

The OCI Java SDK requires an authentication provider. The Spring Cloud OCI core starter already auto-configures authentication based on active properties—such as `FILE`, `SIMPLE`, `INSTANCE_PRINCIPAL`, `RESOURCE_PRINCIPAL`, `SESSION_TOKEN`, or `WORKLOAD_IDENTITY`.

When using the SDK directly in an app that includes the core starter, reuse the provider managed by Spring Cloud OCI. That ensures direct clients share the exact same identity as other service beans.

### 5.1. `CredentialsProvider`

Spring Cloud OCI provides a `CredentialsProvider` wrapper in package:

~~~java
import com.oracle.cloud.spring.autoconfigure.core.CredentialsProvider;
~~~

The wrapper exposes the `AuthenticationDetailsProvider` created by the core starter. Spring Cloud Oracle Javadocs describe `getAuthenticationDetailsProvider()` for obtaining the provider to pass to the OCI SDK.

Example creating a client for a service without a starter:

~~~java
@Configuration
public class OciAdvancedClientConfiguration {

    @Bean(destroyMethod = "close")
    ObjectStorageClient advancedObjectStorageClient(
            CredentialsProvider credentialsProvider,
            OciSdkProperties properties) {

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(properties.region()))
                .build(credentialsProvider.getAuthenticationDetailsProvider());
    }
}
~~~

This example assumes `OciSdkProperties` provides a region aligned with `spring.cloud.oci.region.static`. If the application reads region from the auth config file, reuse the application's region resolution strategy rather than hardcoding a separate region.

### 5.2. Do Not Recreate a Second Credential Provider

Avoid these patterns in an application already using Spring Cloud OCI:

- Reading `~/.oci/config` again inside individual services.
- Creating a new API key provider for the SDK while the starter uses Instance Principal.
- Using a `FILE` profile in direct SDK code while production starters use Resource Principal.
- Embedding private keys in code to construct an auxiliary client.
- Creating a new provider on every request.

If the starter uses Instance Principal, additional SDK clients must use the starter's provider too. If the starter uses Workload Identity, never switch an auxiliary client over to an API key.

### 5.3. When a Separate Provider Is Warranted

Create a separate provider only for an intentional identity boundary, such as an integration calling a different tenancy with different credentials. In that case, manage separately:

- Credential source.
- Rotation and refresh.
- IAM policies.
- Region/endpoint.
- Provider lifecycle.
- Audit identity.
- Testing and revocation procedures.

Never introduce a second identity simply because an internet SDK snippet used the `DEFAULT` profile.

## 6. Reusing Raw Clients from Starters

Several Spring Cloud OCI service beans expose the underlying OCI Java SDK client directly. This helps when the abstraction lacks a required method, yet the starter already configured authentication, region, and client settings.

Examples published in Spring Cloud Oracle Javadocs include:

| Spring Bean | Raw SDK Client |
| --- | --- |
| `Storage` | `ObjectStorage` |
| `Streaming` | `Streaming` |
| `LogService` | `Logging` |
| `Queue` | `QueueClient` and `QueueAdminClient` |
| `Notification` | `NotificationDataPlane` and `NotificationControlPlane` clients |
| `Function` | `FunctionsInvokeClient` |
| `AutonomousDb` | `DatabaseClient` |

Example using the raw Object Storage client:

~~~java
@Service
public class ObjectVersionInspector {

    private final Storage storage;

    public ObjectVersionInspector(Storage storage) {
        this.storage = storage;
    }

    public String getObjectEtag(
            String namespace,
            String bucket,
            String objectName) {

        HeadObjectResponse response = storage.getClient().headObject(
                HeadObjectRequest.builder()
                        .namespaceName(namespace)
                        .bucketName(bucket)
                        .objectName(objectName)
                        .build());

        return response.getEtag();
    }
}
~~~

`Storage` remains responsible for routine operations; only `headObject` drops down to the SDK directly. No second `ObjectStorageClient` is needed.

Raw client method names and return types must match the Javadocs of your active Spring Cloud OCI release. If a release changes public APIs, update the adapter in one single place.

## 7. Creating Custom SDK Clients as Spring Beans

When no service bean exposes the needed raw client, register the client as a singleton bean. Configure region, authentication, and HTTP options before putting it into use.

### 7.1. Configuring Timeouts

Client configuration example:

~~~java
@Configuration
public class OciSdkHttpConfiguration {

    @Bean
    ClientConfiguration ociSdkClientConfiguration() {
        return ClientConfiguration.builder()
                .connectionTimeoutMillis(3000)
                .readTimeoutMillis(60000)
                .build();
    }
}
~~~

These numbers are illustrative starting points. Choose timeouts based on latency SLOs, payload sizes, service processing times, and upstream request timeouts.

### 7.2. Initializing the Client

Example using a dedicated property for the SDK client so the chosen region is explicit. This value must match Spring Cloud OCI's default region in the deployment:

~~~yaml
app:
  oci:
    sdk:
      region: ap-singapore-1
~~~

Declare the properties class:

~~~java
@ConfigurationProperties(prefix = "app.oci.sdk")
public record OciSdkProperties(String region) {
}
~~~

Register the properties class via `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`.

~~~java
@Configuration
@EnableConfigurationProperties(OciSdkProperties.class)
public class OciIdentityClientConfiguration {

    @Bean(destroyMethod = "close")
    IdentityClient identityClient(
            CredentialsProvider credentialsProvider,
            ClientConfiguration clientConfiguration,
            OciSdkProperties properties) {

        return IdentityClient.builder()
                .region(Region.fromRegionId(properties.region()))
                .configuration(clientConfiguration)
                .build(credentialsProvider.getAuthenticationDetailsProvider());
    }
}
~~~

The client is created once at Spring context startup and closed when the context shuts down. Never invoke builders inside every service method.

### 7.3. Region and Endpoint

A service client is bound to one region/endpoint. If the application must call multiple regions, create a separate client per region under distinct bean names/qualifiers.

Never mutate the region of a single shared client while concurrent requests are running. That can send requests to the wrong endpoint.

Prefer region resolution from Spring Cloud OCI. Configure custom endpoints only when explicitly required—such as new realms/regions, private endpoints, or specialized API endpoints.

### 7.4. When to Use Client Configurators?

The OCI SDK lets you customize HTTP clients, TLS, truststores, proxies, connection managers, and related properties via builders/client configurators. Change these options only for concrete operational requirements.

Before plugging in a custom HTTP client:

- Check which HTTP implementation the SDK release uses.
- Verify thread safety.
- Measure connection pooling and TLS handshakes.
- Verify proxy/network routes.
- Test shutdown and resource cleanup.
- Avoid creating two independent connection pools unnecessarily.

## 8. Request and Response Builders

The OCI SDK uses request models and builders to construct requests. Each operation returns a response model carrying data and metadata such as request IDs, ETags, or pagination tokens.

Bucket read example:

~~~java
GetBucketResponse response = objectStorage.getBucket(
        GetBucketRequest.builder()
                .namespaceName(namespace)
                .bucketName(bucketName)
                .build());

String requestId = response.getOpcRequestId();
Bucket bucket = response.getBucket();
~~~

Object read example:

~~~java
GetObjectResponse response = objectStorage.getObject(
        GetObjectRequest.builder()
                .namespaceName(namespace)
                .bucketName(bucketName)
                .objectName(objectName)
                .build());

try (InputStream input = response.getInputStream()) {
    Files.copy(input, targetPath, StandardCopyOption.REPLACE_EXISTING);
}
~~~

You must close the `InputStream` returned by `GetObjectResponse`. Failing to close the stream can prevent HTTP connections from returning to the pool and exhaust connections/resources.

### 8.1. Using Response Metadata

Responses may contain:

- `opc-request-id` for tracing requests in OCI Support/Audit.
- ETag for verifying object versions/content state.
- Pagination tokens.
- Service-specific metadata.
- Work request IDs when operations run asynchronously server-side.

Do not discard metadata when workflows need reconciliation or operational support.

### 8.2. Conditional Requests

Several operations support `If-Match` or `If-None-Match`. Use conditions to avoid overwriting objects whose state has changed.

Conceptual example:

~~~java
PutObjectRequest request = PutObjectRequest.builder()
        .namespaceName(namespace)
        .bucketName(bucket)
        .objectName(objectName)
        .ifMatch(expectedEtag)
        .putObjectBody(content)
        .build();
~~~

Verify which conditional headers a given operation supports and the semantics of HTTP 412/409. Never assume every service API supports identical conditions.

## 9. Pagination: Never Assume List Calls Return Everything

Many OCI list operations return paginated results. Reading only the first page can silently skip resources without throwing an exception.

There are two approaches:

1. Use the paginator provided by the service client.
2. Read the page token manually and issue follow-up requests.

General example with `ListBuckets`:

~~~java
String pageToken = null;

do {
    ListBucketsResponse response = objectStorage.listBuckets(
            ListBucketsRequest.builder()
                    .namespaceName(namespace)
                    .compartmentId(compartmentId)
                    .page(pageToken)
                    .build());

    processBuckets(response.getItems());
    pageToken = response.getOpcNextPage();

} while (pageToken != null);
~~~

Across different APIs, token field names can differ. For instance, Object Storage `ListObjects` uses `start`/`nextStartWith`. Read the operation's Javadoc rather than copying pagination fields from another service.

### 9.1. Using Paginators

Service clients typically expose `getPaginators()`. A paginator can provide:

- Response iterators: iterate over each response page.
- Record iterators: iterate over individual items across pages.

Paginators save you from writing token loops, yet they do not make large lists free. You still need rate control, memory bounds, and mid-iteration error handling.

### 9.2. Pagination and Mutating Data

If resources change while iterating across pages, results can reflect states across multiple points in time. Do not treat pagination as a snapshot transaction unless the API explicitly guarantees it.

When synchronizing data, persist checkpoints/page tokens durably and design reconciliation for resources modified during scans.

## 10. Waiters: Waiting for Resources to Reach Desired State

Certain OCI operations create resources or launch work and return before the resource reaches its terminal state.

SDK waiters encapsulate polling:

- Calling the status-check API.
- Sleeping per a delay strategy.
- Stopping when the target state is reached.
- Stopping when a timeout or termination strategy expires.

Conceptual example:

~~~java
ComputeWaiters waiters = computeClient.getWaiters();

GetInstanceResponse response = waiters.forInstance(
        GetInstanceRequest.builder()
                .instanceId(instanceId)
                .build(),
        Instance.LifecycleState.Running)
    .execute();
~~~

Use waiters instead of writing custom polling loops whenever the SDK provides waiters for that resource. Pick sensible termination timeouts and never block user HTTP requests indefinitely.

If a waiter times out, the resource may still be provisioning. Record the OCID and state to continue reconciliation rather than creating duplicate resources.

## 11. Multipart Uploads for Large Objects

`PutObject` fits standard uploads. For large files, multipart uploads split objects into parts that can be uploaded in parallel and retried individually.

The OCI Java SDK provides low-level multipart APIs and high-level `UploadManager`. `UploadManager` can:

- Split files into parts.
- Upload parts in parallel.
- Collect ETags/part metadata.
- Commit parts into a complete object.
- Reduce the cost of retrying an entire file when a single part fails.

Oracle recommends multipart uploads for objects larger than roughly 100 MiB. Choose part sizes and concurrency based on bandwidth, memory, CPU, and workload quotas.

### 11.1. Raw Multipart API

Use the raw multipart API when you need control over:

- When the upload is initiated.
- Part numbers.
- Uploading individual parts.
- Persisting upload IDs and ETags.
- Committing the upload.
- Aborting the upload if the workflow fails.

This suits pause/resume workflows or distributing uploads across multiple workers. In return, the application must manage state and full cleanup.

### 11.2. `UploadManager`

Use `UploadManager` when you want the SDK to manage splitting and parallel uploads. Check constructor/builder APIs for your exact OCI SDK version and cap concurrency to avoid firing excessive simultaneous requests.

### 11.3. Cleaning Up Uncommitted Uploads

Abandoned multipart uploads leave uncommitted parts behind that can accrue storage charges. Design:

- Explicit abort when the application knows a workflow failed.
- Lifecycle rules to purge uncommitted multipart uploads.
- Persisting upload IDs if resume is needed.
- Monitoring uploads open for too long.
- Never committing an object before verifying all parts and ETags.

## 12. Retries and Idempotency

The OCI Java SDK supports retry configuration at multiple levels:

- SDK/global.
- Client.
- Request.

Request-level retry takes precedence over client-level; client-level overrides global defaults for that client.

Current SDKs include default retries for certain transient operations/errors such as throttling, selected 5xx errors, timeouts, and connection errors. Not every operation enables retries by default; inspect the Javadocs for your operation and SDK release.

### 12.1. Retries Do Not Mean Exactly-Once

If a client times out after the server already executed the operation, a retry can duplicate side effects. Determine whether each operation is idempotent.

| Operation | Risk on Retry | Design |
| --- | --- | --- |
| `GET` metadata | Low | Transient retries per SDK policy |
| List resources | Low, though data may shift between pages | Checkpoints/pagination |
| `PutObject` on same object key | May overwrite | Conditional writes, versioning, or idempotent object keys |
| Create resource | May create duplicates or hit conflicts | Deterministic naming/idempotency if API supports it; reconcile after timeouts |
| Delete resource | May return not found on retry | Treat not found as desired state if appropriate |
| Publish message | May publish duplicates | Business event IDs and consumer deduplication |

### 12.2. Stream Bodies and Retries

`PutObject` consumes an `InputStream`. If the stream supports `mark`/`reset`, the SDK can rewind it on retry. Otherwise, the SDK may wrap/buffer the stream in memory.

For large or non-repeatable streams:

- Do not rely on default retries without checking stream behavior.
- Use `FileInputStream` or reopenable sources when appropriate.
- Use multipart uploads for large files.
- Consider disabling retries on specific requests when retrying is unsafe.
- Check unknown outcomes via `HeadObject` or metadata before re-uploading.

### 12.3. Retry Budgets

Total retry duration must fit inside the caller's timeout budget. If an HTTP API has a 10-second timeout while the SDK retries 8 times with long read timeouts, requests can tie up threads far too long.

Configure retry termination by attempt count or total elapsed time. Avoid uncoordinated simultaneous retries across the SDK, service adapter, queue worker, and API gateway without a shared budget.

## 13. Timeouts, Circuit Breakers, and Async Clients

### 13.1. Timeouts

`ClientConfiguration` configures connect timeouts and read timeouts. Choose timeouts by operation class:

- Metadata requests: generally need short timeouts.
- File downloads: timeouts depend on size and network throughput.
- Control-plane provisioning: use waiters with longer overall wait limits.
- Streaming or long-running operations: use service-specific APIs and timeouts.

Do not set a massive global timeout across the entire client merely to avoid timeout errors.

### 13.2. Circuit Breakers

Several OCI SDK service clients support a default circuit breaker. Circuit breakers prevent applications from hammering a failing service with continuous requests.

Before adding Resilience4j or another custom circuit breaker, check whether the SDK client already has a default breaker. When layering multiple breakers, explicitly define:

- Which errors count as failures.
- Timeouts at each layer.
- Open/half-open durations.
- Whether retries execute inside or outside the breaker.
- How metrics and alerts are emitted.

### 13.3. Async Clients

The OCI Java SDK offers asynchronous clients for several services. Async APIs generally accept an `AsyncHandler` or return a `Future`. Choose async when:

- Running many independent I/O operations.
- Avoiding blocking request threads.
- The application has clear executors and backpressure.
- Callbacks and error paths can be handled cleanly.

Async does not automatically make an application faster. If callbacks invoke blocking databases or heavy CPU work, an appropriate executor is still required.

Current OCI Java SDK documentation notes that default retries and circuit breakers are not supported on asynchronous clients. Design matching retry/error handling yourself and verify behavior in your exact SDK version.

### 13.4. `InputStream` with Async Object Storage

With async `getObject` using `AsyncHandler`, if the response contains an `InputStream`, consume it inside the callback. The SDK may close the stream as soon as the callback returns.

When using a Java `Future`, the caller must read and close the stream after retrieving the response. Never retain a response stream for later use outside the callback once the SDK has closed it.

## 14. Raw Signed Requests When the SDK Lacks an Operation

Raw requests are a last resort when an OCI API is not yet exposed by the SDK or requires calling a specialized endpoint via another HTTP client.

The OCI Java SDK provides `DefaultRequestSigner` to build a `RequestSigner` for requests outside standard service clients.

General workflow:

1. Use the configured authentication provider.
2. Construct a request signer per SDK documentation.
3. Build the HTTP request with exact method, path, query, and headers.
4. Sign the request per OCI signing rules.
5. Send via an HTTP client configured with TLS/proxy.
6. Log the request ID and handle response/errors.

Never construct `Authorization` headers by hand with string concatenation. Request signing depends on method, host, path, date, body, and signed headers. Getting one component wrong causes 401 or invalid signature errors.

Raw requests require thorough testing against real endpoints and belong inside a dedicated adapter. Once a newer SDK release supports the operation, migrate back to the service client.

## 15. Client Lifecycle and Thread Safety

OCI SDK clients hold connection pools, HTTP clients, and associated executors/resources. Never instantiate a new client on every service call.

With the default Jersey implementation, SDK clients are thread-safe after initialization and endpoint configuration. They can be reused across multiple requests and threads. With alternative HTTP implementations, verify thread safety explicitly.

In Spring:

- Declare clients as singleton beans.
- Set `destroyMethod = "close"` so they close on context shutdown.
- Never close a shared client after individual requests.
- Never mutate region/endpoint on a client shared across threads.
- Create separate clients when different endpoints/regions are required.
- Close custom providers/schedulers if created and owned by the application.

Example:

~~~java
@Bean(destroyMethod = "close")
ObjectStorageClient objectStorageClient(...) {
    // Create one client for a fixed region/identity
}
~~~

If a client is obtained from a service starter, do not close the starter-owned client yourself unless API ownership explicitly states so. Let Spring Cloud OCI manage its bean lifecycles.

## 16. Handling `BmcException`

The OCI SDK throws `BmcException` as an unchecked exception. It can carry:

- HTTP status code.
- Service error code.
- Message.
- OCI request ID.
- Cause/timeout details.

Example:

~~~java
try {
    objectStorage.headObject(request);
} catch (BmcException ex) {
    log.warn(
            "OCI request failed: status={}, serviceCode={}, requestId={}",
            ex.getStatusCode(),
            ex.getServiceCode(),
            ex.getOpcRequestId());

    throw new OciStorageException(
            "Unable to inspect object",
            ex);
}
~~~

Never log credentials, `Authorization` headers, secret contents, or full sensitive payloads.

### 16.1. Error Classification

| Category | Behavior |
| --- | --- |
| `400` validation | Fix the request; do not retry indefinitely |
| `401` authentication | Check provider, token, signature, and clock |
| `403` authorization | Check IAM policies, resource scope, and principal |
| `404` not found | Check OCID, region, namespace, and lifecycle |
| `409` conflict | Read service error code; reconcile state |
| `429` throttling | Backoff, reduce concurrency, and honor retry policies |
| `5xx` | Bounded retries if the operation is safe |
| Timeout | Check whether the operation may already have succeeded before retrying |

Do not classify solely by HTTP status. A 409 status may indicate an already-existing resource or a state conflict handled differently per service error code.

### 16.2. Recording Request IDs

When contacting OCI Support or investigating Audit logs, the request ID pinpoints the exact call. Log the request ID alongside operation, service, region, and application correlation ID.

## 17. Placing the SDK Behind an Adapter Boundary

The business domain should never depend directly on OCI request/response classes.

Interface example:

~~~java
public interface ObjectVersionReader {
    List<StoredObjectVersion> listVersions(
            String bucketName,
            String objectNamePrefix);
}
~~~

OCI adapter:

~~~java
@Component
public class OciObjectVersionReader implements ObjectVersionReader {

    private final ObjectStorage objectStorage;
    private final String namespace;

    public OciObjectVersionReader(
            Storage storage,
            ObjectStorageProperties properties) {
        this.objectStorage = storage.getClient();
        this.namespace = properties.namespace();
    }

    @Override
    public List<StoredObjectVersion> listVersions(
            String bucketName,
            String objectNamePrefix) {

        // Uses OCI SDK ListObjectVersionsRequest.
        // Maps SDK responses to application StoredObjectVersion records.
        return loadAndMapVersions(bucketName, objectNamePrefix);
    }
}
~~~

This adapter shows the structure; implement `loadAndMapVersions` using the request/response models of your active SDK release.

Benefits:

- Business code has zero dependency on the OCI SDK.
- Unit tests can mock internal interfaces.
- Implementations or services can be swapped without touching domain logic.
- OCI-specific errors map cleanly to application exceptions.
- Permissions, retries, and telemetry are centralized in the adapter.

## 18. Testing Direct SDK Usage

### 18.1. Unit Tests

Mock the OCI SDK interface or adapter interface to verify:

- Requests are built accurately.
- Responses map accurately.
- Errors translate into application exceptions.
- Retries run only for eligible failures.
- `InputStream` instances are closed.
- Idempotency and unknown outcomes are handled properly.

Pure business logic does not need real OCI calls.

### 18.2. Context Tests

Verify Spring creates SDK client beans and closes them when the context stops. Use test configurations for providers/clients when avoiding live OCI access.

### 18.3. Integration Tests

Use a dedicated test compartment and test identity:

- Call a resource-read operation.
- Call an advanced operation not exposed by the starter.
- Verify IAM positive/negative cases.
- Test pagination.
- Test bounded retries/timeouts.
- Test multipart uploads and cleanup.
- Test multi-region setups if required by the use case.
- Verify Audit logs/request IDs.

Never run integration tests against a production tenancy or resources containing real data.

### 18.4. Client Lifecycle Tests

- Application context creates the client once.
- Multiple requests reuse the same bean.
- Context shutdown calls `close`.
- No unexpected threads/executors linger after shutdown.
- A client configured for region A is never used for region B.

## 19. Security When Using the SDK Directly

Using the SDK directly does not relax IAM requirements. The identity still needs permissions for each specific operation.

Principles:

- Reuse the configured workload identity.
- Never hardcode API keys/private keys.
- Never log request signers or tokens.
- Grant least-privilege permissions per service operation.
- Restrict regions and compartments.
- Never grant tenancy admin rights to an adapter that only reads objects.
- Never create pre-authenticated requests or public endpoints without explicit requirements.
- Keep TLS validation enabled.
- Manage proxies/truststores according to policy.
- Control what enters logs and traces.

When direct SDK code adds a new operation, IAM policies may need updates. Review policies alongside code changes; never assume starter abstraction permissions cover every SDK operation.

## 20. Performance and Cost

Direct SDK usage unlocks performance tuning options while increasing operational responsibility.

Evaluate:

| Area | Consideration |
| --- | --- |
| Client reuse | Avoid creating new HTTP pools per request |
| Connection timeout | Do not wait excessively to connect |
| Read timeout | Match payload size and latency |
| Pagination | Bound processed items and memory |
| Multipart | Choose part size/concurrency to fit bandwidth |
| Async | Ensure executors, backpressure, and callback lifecycles |
| Retries | Avoid excessive retries or duplicated side effects |
| Multi-region | Separate clients/endpoints per region |
| Logging | Never log large payloads or secrets |
| Cost | Request volume, transfer, storage, and retries |

Never optimize before measuring. Capture baseline latency, throughput, memory, and error rates before changing HTTP clients, concurrency, or retries.

## 21. Lab Exercise: Using the SDK to List Object Versions

**Context:** Invoice Service uses the Spring Cloud OCI Storage starter to upload/download PDFs. An audit feature must list object versions in a bucket, yet the `Storage` abstraction currently does not expose a `listObjectVersions` operation matching requirements.

### Part A — Analysis

1. Confirm the Storage starter is declared.
2. Check the `Storage` bean Javadocs and identify the accessible raw SDK client.
3. Identify the `ListObjectVersions` request/response models.
4. Identify required IAM permissions for the operation.
5. Define the pagination strategy.

### Part B — Implementing the Adapter

1. Inject the `Storage` bean.
2. Obtain the `ObjectStorage` SDK client from the bean.
3. Build `ListObjectVersionsRequest`.
4. Read all pages.
5. Map SDK responses into `StoredObjectVersion`.
6. Log the request ID for every operation.
7. Keep OCI models out of the domain layer.

### Part C — Extending a Service SDK Without a Starter

1. Choose another OCI service client not exposed by a starter.
2. Inject `CredentialsProvider` from Spring Cloud OCI core.
3. Build the client via its SDK builder and configured region.
4. Register the client as a singleton Spring bean.
5. Configure timeouts.
6. Close the client on Spring context shutdown.

### Part D — Testing

1. Unit test the adapter with a mocked SDK client.
2. Integration test against a versioned test bucket.
3. Verify multi-page pagination.
4. Test 403 and 404 errors.
5. Test timeouts/unknown outcomes.
6. Verify client closure on shutdown.
7. Record the dependency tree and OCI SDK version.

### Deliverables

- Comparison table between starter abstractions and SDK operations.
- OCI SDK dependency graph.
- Spring configuration creating the client.
- Object version listing adapter.
- Unit and integration tests.
- IAM policies for the workload.
- Evidence of pagination and request IDs.
- Runbook for handling 401/403, throttling, and timeouts.

## 22. Self-Check Questions

1. When do you need to use the OCI Java SDK directly?
2. Why should you check a starter's raw SDK client before creating a new client?
3. What role does `CredentialsProvider` play in Spring Cloud OCI?
4. Why should an SDK client be a singleton bean?
5. Can a single service client serve multiple regions concurrently?
6. How are pagination tokens handled?
7. What problem do waiters solve?
8. When should you use multipart uploads?
9. Why must uncommitted multipart uploads be aborted/cleaned up?
10. How do `AsyncHandler` and `Future` differ when responses contain an `InputStream`?
11. Why must default retries on async clients be verified separately?
12. Why might retrying `PutObject` require a replayable stream?
13. Where does `BmcException` expose the request ID?
14. Why shouldn't full requests/responses be logged?
15. Why should SDK-specific types stay behind an adapter boundary?
16. When should raw signed requests be used?
17. What should be tested before deploying direct SDK client code?

## 23. Key Takeaways

- Spring Cloud OCI starters provide abstractions and auto-configuration; the OCI Java SDK provides fuller service clients and request/response models.
- Drop down to the SDK directly only when starters lack the needed operation or option.
- Prefer reusing raw SDK clients exposed by starters before creating new clients.
- Use `CredentialsProvider` from Spring Cloud OCI to reuse configured authentication.
- Never create providers/clients per request; manage SDK clients as Spring singleton beans.
- Each service client binds to one region/endpoint; create separate clients per target region.
- Use paginators, waiters, and multipart uploads instead of reimplementing them when the SDK already provides them.
- Read and close `GetObjectResponse` `InputStream` instances; handle stream lifecycles carefully with async APIs.
- Align retries with operation semantics, request body replayability, and idempotency; timeouts do not prove operations failed to occur.
- Log request IDs, classify `BmcException`, and never log secrets or sensitive payloads.
- Keep the SDK behind an adapter boundary, test in a test compartment, and grant least-privilege IAM policies.
- Inspect the dependency graph to keep OCI SDK modules aligned with your starter release.

## References

- [Spring Cloud OCI 2.0.4 — Core starter and authentication](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud OCI 2.0.4 — Configuration properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration-properties/)
- [Spring Cloud Oracle 2.0.0 Javadocs — API index](https://oracle.github.io/spring-cloud-oracle/2.0.0/javadocs/index-all.html)
- [OCI Java SDK — Concepts](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkconcepts.htm)
- [OCI Java SDK — Getting started](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkgettingstarted.htm)
- [OCI Java SDK — ObjectStorageClient Javadoc](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/ObjectStorageClient.html)
- [OCI Java SDK — Troubleshooting](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdktroubleshooting.htm)
- [OCI Object Storage — Multipart uploads](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingmultipartuploads.htm)
- [OCI Java SDK — GitHub repository](https://github.com/oracle/oci-java-sdk)
- [Maven Central — OCI Java SDK Object Storage module](https://central.sonatype.com/artifact/com.oracle.oci.sdk/oci-java-sdk-objectstorage)
