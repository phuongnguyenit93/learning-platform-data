# Synchronous and Asynchronous Clients in the Azure Java SDK

## 1. One Problem, Two Ways to Call Azure

A Java application serving documents to employees has three tasks:

1. Read a file in **Azure Blob Storage** when a user loads a page.
2. Upload multiple PDF files concurrently from a queue.
3. Record latency, error, storage capacity, and cost metrics to **Azure Monitor**.

A developer can choose an **Azure SDK synchronous client** or an **asynchronous client**. Both interact with the same Azure service, but they differ in how they manage execution threads, responses, resources, and load pressure.

This lesson belongs to the **Azure SDK for Java** chapter in the **CLOUD_PROVIDERS_AZURE** module, connecting client usage to the broader learning path covering subscriptions, resource groups, Microsoft Entra ID, networking, compute, storage, data, monitoring, security, and cost control on Azure. The lesson uses **Azure Storage Blobs Java SDK v12** as a concrete example, then generalizes the principles to Azure Service Bus, Cosmos DB, and other Java SDKs. **Class names, return APIs, and retry options vary by service; do not assume every client shares the same signature.**

### Running Scenario

Suppose the **documents-api** service runs on Azure App Service or AKS, reading and writing files in Blob Storage. Initially an endpoint downloads one file per request; later it scales up to batch-processing thousands of files. Choosing sync vs. async affects thread counts, memory usage, latency, error handling, cancellation, backpressure, and maintainability.

## 2. Learning Objectives

Upon completion, you will be able to:

1. Distinguish between blocking, nonblocking, concurrency, parallelism, and asynchronous operations.
2. Explain sync/async client pairs in the Azure SDK for Java.
3. Understand the roles of Java Azure SDK v2 libraries, builders, the HTTP pipeline, TokenCredential, transports, and Reactor.
4. Create **BlobServiceClient** and **BlobServiceAsyncClient** using the same authentication setup.
5. Perform upload/download/list operations using both the sync API and async API.
6. Explain **Mono**, **Flux**, **PagedFlux**, and lazy execution.
7. Use **flatMap concurrency**, timeouts, cancellation, and error handling properly.
8. Avoid blocking the event loop, subscribe-and-forget, and unbounded concurrency.
9. Distinguish wrapping blocking code in a Mono from true nonblocking I/O.
10. Design retry/backoff strategies aligned with 429/503/timeouts and idempotency.
11. Choose sync vs. async for Spring MVC, Spring WebFlux, batch jobs, Azure Functions, or virtual threads.
12. Manage lifecycles, credentials, network connection pools, and memory when transferring files.
13. Measure p95/p99 latency, throughput, errors, thread usage, costs, and quotas.
14. Write controlled unit/integration tests and a lab comparing both client styles.

## 3. Synchronous, Asynchronous, Blocking, and Nonblocking

### 3.1. Synchronous in Common Calling Style

The caller waits for the result before executing the next line.

~~~java
String content = readBlobSynchronously();
System.out.println(content);
~~~

If the call takes 300 ms, the current thread is usually held waiting until it receives a result or an error. This is easy to follow in imperative programs.

### 3.2. Asynchronous

The call may return a handle representing a future result, while the actual operation is triggered or scheduled according to the API.

~~~java
Mono<String> pending = readBlobAsynchronously();
Mono<String> processed = pending.map(String::trim);
~~~

If **pending** is a cold publisher—as is common in Azure SDK Reactor APIs—merely building the pipeline does not necessarily send a request. The publisher is triggered when subscribed to by the framework or your code.

### 3.3. Four Non-Synonymous Concepts

| Concept | Meaning | Example |
|---|---|---|
| **Synchronous** | Caller waits for completion before proceeding | BlobClient.downloadContent() |
| **Asynchronous** | Caller receives a future/publisher and handles the result later | BlobAsyncClient.downloadContent() returning Mono |
| **Blocking** | Thread is held waiting for the operation to finish | Socket read or Mono.block() |
| **Nonblocking** | Thread does not wait on I/O while data is not yet available | Reactor + async HTTP transport |
| **Concurrency** | Multiple tasks making progress overlapping in time | 50 in-flight requests |
| **Parallelism** | Multiple tasks executing simultaneously on multiple cores | Multiple CPU tasks on a worker pool |

A method that **returns a Mono** yet internally calls a sync client and waits on the event loop is still disguised blocking I/O.

### 3.4. Comparison Diagrams

~~~mermaid
sequenceDiagram
    participant A as Application thread
    participant S as Azure SDK
    participant B as Azure Blob Storage
    A->>S: Sync download
    S->>B: HTTP request
    B-->>S: Response
    S-->>A: BinaryData
    Note over A: Caller waits for result
~~~

~~~mermaid
sequenceDiagram
    participant A as Application thread
    participant S as Async SDK/HTTP
    participant B as Azure Blob Storage
    A->>S: Build Mono pipeline
    Note over A: HTTP not necessarily sent yet
    A->>S: Subscribe
    S->>B: HTTP request
    Note over A: Can handle other work
    B-->>S: Response event
    S-->>A: onNext/onComplete
~~~

## 4. How the Azure SDK for Java Organizes Clients

Modern Azure Java libraries generally follow this model:

~~~text
Your Java application
       |
    Service Client
       |
 Azure SDK policies / retry / authentication / diagnostics
       |
  HTTP transport + Azure service
~~~

For Storage Blobs:

- **BlobServiceClient**: service-level sync client.
- **BlobServiceAsyncClient**: service-level async client.
- **BlobContainerClient** / **BlobContainerAsyncClient**: container-level clients.
- **BlobClient** / **BlobAsyncClient**: blob-level clients.
- **BlobServiceClientBuilder**: configures endpoint, credential, and transport, and builds either client type.

Not every library has an exact one-to-one `AsyncClient` suffix; always check the API of the **actual service and SDK version**. The Azure SDK for Java also includes ARM management and data-plane libraries; their API models are not completely identical.

### 4.1. What Is Azure SDK v2?

In this context, "Azure SDK for Java" refers to the modern family of libraries whose artifacts generally start with **com.azure** (such as **azure-storage-blob**, **azure-identity**, **azure-core**), distinct from older/legacy SDKs. Do not confuse this generational label with version **12.x** of the Storage Blob library.

### 4.2. Does a Sync Client Always Use Dedicated Blocking HTTP?

Under the hood, implementations may use different transports and mechanisms; the **important contract at the caller layer** is that a sync method returns only after completion. You do not need to assume every sync client uses a single dedicated socket/thread under the exact same implementation.

### 4.3. Do Not Pick a Client Out of Habit

If an application only runs a job once per minute to upload a few files, sync is usually simpler. If there are thousands of I/O-bound operations inside a reactive HTTP pipeline, async can save threads **when used properly**.

## 5. Azure Architecture Around documents-api

~~~mermaid
flowchart LR
    U[Users / Internal apps] --> API[Java documents-api]
    ID[Microsoft Entra ID / Managed identity] --> API
    API --> SDK[Azure Blob Client]
    SDK --> NET[HTTPS / VNet / Private Endpoint]
    NET --> BLOB[(Azure Blob Storage)]
    API --> MON[Azure Monitor / Application Insights]
    BLOB --> MON
~~~

- Resource groups and subscriptions organize and govern resources.
- Microsoft Entra ID authenticates the Java workload's identity.
- Azure data-plane RBAC governs permissions on blobs.
- VNet/private endpoints determine allowed network paths.
- App Service/AKS/Functions manage compute and lifecycle.
- Azure Monitor/Cost Management measure performance and request, storage, and compute costs.

**An async client does not automatically increase Storage account throughput or add network/compute quota.**

## 6. Ask the Right Questions Before Choosing Sync vs. Async

Measure and determine:

1. How many Azure operations does a single request perform?
2. What is the ratio of I/O wait time to CPU processing time?
3. How many concurrent requests arrive?
4. Is the request-handling framework blocking (Servlet/MVC) or reactive (WebFlux)?
5. Is streaming of large payloads required?
6. What request, throughput, or partition limits does the service impose?
7. What cancellation and deadline guarantees are needed?
8. Does the team have experience with Reactor and reactive debugging?
9. What are the JVM thread, CPU, memory, and file-descriptor/connection limits?
10. What do actual benchmarks on the same SKU and network show?

Never claim async is always faster for a single request. For the same REST operation under low contention, latency is typically dominated by the network and the service, not by how Java represents the result.

## 7. Maven Dependencies for the Hands-On Lab

Example Java 17 project with the modern Azure Blob SDK:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-blob</artifactId>
    <version>YOUR_APPROVED_12_X_VERSION</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>YOUR_APPROVED_IDENTITY_VERSION</version>
  </dependency>
</dependencies>
~~~

The versions are **placeholders** and must be replaced with organization-approved releases compatible with your Java version and security scans. You can use the **Azure SDK BOM** to align Azure library versions where it fits your dependency management; do not arbitrarily mix versions of `azure-core`, `azure-storage-blob`, and `azure-identity`.

### 7.1. Reactor Dependency

Async Azure SDK clients typically use **Project Reactor**: **Mono<T>**, **Flux<T>**, and Azure's paging types. Related dependencies may be pulled transitively, but production projects must inspect the dependency tree/BOM and avoid version conflicts.

### 7.2. HTTP Transport

The Azure SDK relies on a supported HTTP client/transport (for example, the Netty transport in many configurations). In enterprise environments, review proxy settings, TLS, connection pooling, observability, and native transports if customized.

### 7.3. Do Not Mix Legacy and Modern Libraries Just for Samples

A codebase using Storage Blob SDK v12 should stay consistent with the modern API; examples using **CloudBlobClient** from the legacy SDK are not drop-in replacements for **BlobServiceClient**.

## 8. Authentication: Prefer TokenCredential/Managed Identity

In supported environments, use Microsoft Entra ID and **DefaultAzureCredential** instead of static account keys. For Azure Blob Storage, the managed identity or developer principal needs data-plane roles such as **Storage Blob Data Reader** to read, or **Storage Blob Data Contributor** to write/modify/delete within the granted scope.

**Azure ARM Contributor/Reader does not implicitly grant Blob data-plane permissions.**

### 8.1. Environment

~~~text
AZURE_STORAGE_BLOB_ENDPOINT=https://<storage-account>.blob.core.windows.net
AZURE_STORAGE_CONTAINER=documents
~~~

The endpoint is trusted configuration; never accept arbitrary URLs from user input (SSRF). When using a private endpoint, ensure DNS and network routes are configured properly.

### 8.2. DefaultAzureCredential Locally and in the Cloud

- Local: can use the signed-in Azure CLI or developer identity.
- App Service/Functions: managed identity.
- AKS: Microsoft Entra Workload Identity or an organization-approved method.
- CI/CD: federation/workload identity where feasible.

An application that has a managed identity without **Storage Blob Data Reader/Contributor** will fail with authorization errors.

### 8.3. Least Privilege

If an endpoint only reads from one container, do not grant account-wide write/delete permissions. Separate credentials for uploaders, readers, and administrators. Never print OAuth access tokens, storage keys, or SAS tokens into logs.

## 9. One Builder, Building Both Sync and Async Clients

The factory example below uses **BlobServiceClientBuilder** for the same Storage account and TokenCredential:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceAsyncClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class BlobClients {
    private BlobClients() { }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing " + key);
        }
        return value;
    }

    public static TokenCredential credential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    public static BlobServiceClient syncClient() {
        return new BlobServiceClientBuilder()
            .endpoint(required("AZURE_STORAGE_BLOB_ENDPOINT"))
            .credential(credential())
            .buildClient();
    }

    public static BlobServiceAsyncClient asyncClient() {
        return new BlobServiceClientBuilder()
            .endpoint(required("AZURE_STORAGE_BLOB_ENDPOINT"))
            .credential(credential())
            .buildAsyncClient();
    }
}
~~~

### 9.1. Why Share the Builder Concept?

The builder standardizes the endpoint, credential, retry/transport settings, and client construction style. The example builds two separate objects for comparison; in a production service, **choose and reuse the appropriate client**, rather than creating a new client per request.

### 9.2. Thread Safety and Reuse

Standard Azure service clients are designed to be reused across the application; they manage the HTTP pipeline, credentials, connection resources, and internal policies. Retain the client as a singleton or managed DI bean according to library guidance.

### 9.3. Credentials Also Need Lifecycle Management

Share a single credential instance via dependency injection where appropriate, rather than repeatedly instantiating `DefaultAzureCredential`. Credentials may cache tokens and hold resources; check the actual implementation's API for lifecycle and closeability rules.

## 10. Sync Upload and Download of a Small File

For a small text blob:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;

import java.nio.charset.StandardCharsets;

BlobServiceClient service = BlobClients.syncClient();
BlobContainerClient container =
    service.getBlobContainerClient("documents");

BlobClient blob = container.getBlobClient("sample/hello.txt");

blob.upload(
    BinaryData.fromString("Hello Azure SDK for Java!"),
    true // overwrite=true: only use when business logic permits.
);

byte[] bytes = blob.downloadContent().toBytes();
String result = new String(bytes, StandardCharsets.UTF_8);
System.out.println(result);
~~~

### 10.1. Which Calls Hold the Thread Waiting?

**upload** and **downloadContent** are sync operations. When the server or network is slow, the calling thread does not return until the operation finishes or fails.

### 10.2. Be Careful with overwrite

**overwrite=true** is inappropriate when every upload must create a unique record or must never overwrite existing data. For duplicates/retries, you may need conditional requests, ETags, or deterministic blob names tied to an operation ID.

### 10.3. BinaryData.toBytes Uses Memory

**downloadContent()** is convenient for small files, but it can materialize the entire payload. For large files or high concurrency, use streaming download/transfer methods from the API to avoid holding hundreds of MB per request.

## 11. Async Upload and Download of the Same Blob

With the async client, the standard API returns a **Mono**:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobAsyncClient;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobServiceAsyncClient;
import reactor.core.publisher.Mono;

import java.nio.charset.StandardCharsets;

BlobServiceAsyncClient service = BlobClients.asyncClient();
BlobContainerAsyncClient container =
    service.getBlobContainerAsyncClient("documents");

BlobAsyncClient blob =
    container.getBlobAsyncClient("sample/hello.txt");

Mono<String> operation = blob.upload(
    BinaryData.fromString("Hello async Azure SDK!"),
    true
).then(
    blob.downloadContent()
        .map(data ->
            new String(data.toBytes(), StandardCharsets.UTF_8))
);

// A Spring WebFlux handler can return the operation;
// only use block with a timeout at the CLI/demo boundary.
String result = operation.block(java.time.Duration.ofSeconds(30));
System.out.println(result);
~~~

### 11.1. Not Executed Immediately When Creating the Mono

**Mono<String> operation** represents a pipeline that will execute when subscribed. With cold publishers in the Azure async SDK, constructing the pipeline typically does not send any HTTP request prior to subscription.

### 11.2. Ordering Guaranteed by then

**upload(...).then(download...)** subscribes to the download only after the upload succeeds. This is reactive orchestration. If the upload fails, the Mono terminates with an error and the download never happens.

### 11.3. Block Only at Imperative Boundaries

In the CLI example, **block(Duration)** makes the main thread wait for the result to print it. Inside a WebFlux event loop, **never call block()**; return the Mono for the framework to subscribe and manage backpressure and cancellation.

### 11.4. Async Does Not Reduce Request Charges

Both sync and async call the same Storage service. Pricing, transactions, transferred bytes, and bandwidth depend on the workload and service, and do not drop simply by using Mono.

## 12. What to Understand About Mono, Flux, and PagedFlux

| Type | Represents | Example |
|---|---|---|
| **Mono<T>** | 0 or 1 value then complete/error | Downloading a blob or upload response |
| **Flux<T>** | 0 to many elements | Stream of chunks/events |
| **PagedFlux<T>** | Paginated results from the Azure async SDK | Listing blobs |
| **PagedIterable<T>** | Paginated iterable on the sync side | Listing blobs |
| **Publisher** | Contract for emitting data upon subscription | Foundation of Reactive Streams |

### 12.1. Signal Model

A Mono/Flux can emit:

- **onNext(value)**: delivers a value.
- **onComplete()**: completes normally.
- **onError(error)**: error terminating the pipeline.
- **cancel**: subscriber cancels the subscription, e.g., when an HTTP client disconnects.

A publisher must not emit `onNext` after a terminal event.

### 12.2. A Flux Does Not Necessarily Equal One Network Request

A **PagedFlux** may call the service multiple times to fetch subsequent pages. A **Flux<ByteBuffer>** may represent multiple chunks from a single download. Counting `onNext` events does not equal counting HTTP requests.

### 12.3. Cold vs. Hot Publishers

Azure SDK async APIs generally return cold publishers: each subscription can trigger a new operation. If you subscribe twice to an upload/submit Mono, the side effect may execute twice. Never assume a publisher caches results automatically.

## 13. Sync List Blobs: PagedIterable

A listing operation returns multiple items and can fetch pages lazily:

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobItem;

BlobContainerClient container =
    BlobClients.syncClient().getBlobContainerClient("documents");

for (BlobItem item : container.listBlobs()) {
    System.out.println(item.getName());
}
~~~

### 13.1. Listing Can Cost Many Service Requests

If a container has millions of blobs, the loop can run for a long time, fire many requests, and incur transaction charges. Restrict listings with prefixes, filters, and paging as required—never list the whole container on every HTTP request.

### 13.2. Why Does the Code Look So Simple?

**PagedIterable** hides fetching the next page; the caller iterates sequentially, and the thread may block whenever a new page is needed.

### 13.3. Avoid Holding the Entire List in RAM

Do not routinely convert `listBlobs` into a `List` containing every blob. If you only need a few names or want to process page by page, preserve the paginated flow and cap the result count.

## 14. Async List Blobs: PagedFlux

~~~java
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.models.BlobItem;
import reactor.core.publisher.Flux;

BlobContainerAsyncClient container =
    BlobClients.asyncClient()
        .getBlobContainerAsyncClient("documents");

Flux<String> names = container.listBlobs()
    .map(BlobItem::getName)
    .take(100);

// Example in Spring WebFlux: return names;
// The Reactor framework subscribes when a request arrives.
~~~

### 14.1. What Does take(100) Do?

It limits downstream emissions to at most 100 items; the service may still have returned a page larger than needed depending on page size and buffering. If you need a service-side limit, use list options and the paging API for your SDK version.

### 14.2. PagedFlux and Backpressure

The publisher receives request demand from the subscriber per Reactive Streams, though how the SDK fetches and prefetches pages depends on the implementation. Do not treat Reactor backpressure as a global Azure service rate limiter.

### 14.3. Do Not subscribe() and Discard the Result

A broken handler:

~~~java
public Mono<String> badHandler() {
    container.listBlobs()
        .take(10)
        .subscribe(item -> System.out.println(item.getName()));
    return Mono.just("Done");
}
~~~

The handler may return `"Done"` before listing finishes; exceptions may never reach the request pipeline, and cancellation is unmanaged. Always **return the publisher** or **compose** it into the pipeline the caller awaits.

## 15. Choosing Sync or Async for an HTTP API

| Scenario | Typically Reasonable Choice | Reason |
|---|---|---|
| Spring MVC servlet endpoint, few I/O calls | Sync client | Simple code, framework uses worker threads |
| Spring WebFlux reactive endpoint | Async client | Does not block the event loop |
| Sequential CLI/script | Sync client | Easy to read, control, and debug |
| Worker ingesting many blobs concurrently | Async or sync with bounded executor | Needs concurrency limits and failure tracking |
| Large files needing unmaterialized streaming | Streaming API matching the model | Avoids memory pressure |
| Java virtual threads | Sync client may fit well | Virtual threads cut I/O wait cost, do not raise quotas |
| Many I/O-bound operations | Async is worth evaluating | Saves platform threads when nonblocking end-to-end |

**There is no absolute winner**: test with realistic request rates, payload sizes, and network conditions, while weighing complexity and how your team handles incidents.
## 16. Spring MVC: When Sync Client Is the Natural Choice

A Spring MVC/Servlet endpoint can call `BlobClient` on a worker thread:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobContainerClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;

@RestController
public final class DocumentMvcController {
    private final BlobContainerClient container;

    public DocumentMvcController(BlobContainerClient container) {
        this.container = container;
    }

    @GetMapping("/api/documents/{name}")
    public ResponseEntity<String> get(@PathVariable String name) {
        if (name == null || !name.matches("[a-zA-Z0-9_-]{1,80}")) {
            throw new IllegalArgumentException("Invalid document name");
        }

        BinaryData data = container.getBlobClient(name + ".txt")
            .downloadContent();

        return ResponseEntity.ok(
            new String(data.toBytes(), StandardCharsets.UTF_8));
    }
}
~~~

This is strictly a **small-text read** example: it lacks authentication/authorization, size caps, content type, and exception mapping; do not use it verbatim as a production API.

### 16.1. Worker Threads Are a Finite Resource

Several concurrent requests, each waiting seconds on Azure Storage, can exhaust servlet threads and increase queue latency. Measure the real workload before enlarging thread pools or switching to async.

### 16.2. Why Is Sync Often Easier to Maintain?

Familiar stack traces, intuitive try/catch blocks, and straightforward integration with imperative/JDBC libraries. For sequential batch jobs or low-load services, this simplicity is valuable.

### 16.3. Keep the SDK Out of Controllers

Wrap Blob operations inside a **BlobGateway/DocumentService**. The controller handles authorization and HTTP status codes; the gateway manages the SDK, timeouts, metrics, and exceptions.

## 17. Spring WebFlux: Returning Mono to the Framework

In a reactive controller, return the publisher so the framework subscribes and manages responses and cancellation:

~~~java
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobAsyncClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public final class DocumentReactiveController {
    private final BlobContainerAsyncClient container;

    public DocumentReactiveController(
            BlobContainerAsyncClient container) {
        this.container = container;
    }

    @GetMapping("/api/documents/{name}")
    public Mono<ResponseEntity<String>> get(
            @PathVariable String name) {

        if (!name.matches("[a-zA-Z0-9_-]{1,80}")) {
            return Mono.error(
                new IllegalArgumentException("Invalid document name"));
        }

        BlobAsyncClient blob =
            container.getBlobAsyncClient(name + ".txt");

        return blob.downloadContent()
            .map(data ->
                ResponseEntity.ok(data.toString()));
    }
}
~~~

### 17.1. Never Block on the Event Loop

~~~java
// Anti-pattern on the WebFlux event loop:
return Mono.just(syncBlob.downloadContent().toString());
~~~

**`syncBlob.downloadContent()` has already run and blocked the thread** before `Mono.just` is even constructed. In a reactive framework, use an async client or isolate blocking code.

### 17.2. Async Does Not Guarantee Every Stage Is Nonblocking

If a lambda inside `map` calls synchronous JDBC, reads a large file, or invokes a blocking HTTP library, the event loop is still blocked. Inspect the entire pipeline, not just the return type.

### 17.3. Reading Large Files Is Not Like Reading Small Text

Both examples materialize the payload. For large files, streaming content via a bounded response body with proper Content-Type/Content-Length handling and backpressure is a much better design.

## 18. Mono.just vs. Mono.fromCallable

An anti-pattern:

~~~java
// getBlobTextSync() runs immediately when creating the Mono:
Mono<String> wrong = Mono.just(getBlobTextSync());
~~~

If you must call a legacy synchronous client from a reactive service, isolate the blocking call:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> wrapped = Mono
    .fromCallable(() -> getBlobTextSync())
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 18.1. Wrapping in Mono Does Not Make I/O Nonblocking

`getBlobTextSync` is still blocking, merely running on a scheduler dedicated to blocking work. This protects the event loop, yet still consumes worker threads.

### 18.2. boundedElastic Is Not Infinite

Both the pool and its queue are bounded; if arrival rate consistently exceeds service rate, queue backlog and latency grow. Enforce concurrency/rate limits and an overload policy.

### 18.3. When to Switch to the True Async SDK?

When the workload is dominated by Azure I/O, involves high concurrency, and the framework is already reactive, the async Azure client is usually worth testing instead of wrapping sync clients across many threads.

## 19. Reactor Operators for Orchestrating Operations

| Operator | Role | Notes |
|---|---|---|
| **map** | Synchronous, fast value transformation | Never block inside the lambda |
| **flatMap** | Transforms a value into another publisher | May run concurrently |
| **concatMap** | Preserves order and processes sequentially | Reduces concurrency |
| **flatMapSequential** | Subscribes concurrently, emits in order | May buffer results |
| **then** | Discards prior result, waits for completion | Good for upload then read |
| **zip** | Combines two Monos | Can run concurrently |
| **onErrorResume** | Fallback on exception | Do not swallow errors |
| **doOnNext** | Brief metrics/logging side effects | Do not use as business pipeline |
| **timeout** | Caps stage duration | Does not guarantee rollback |
| **retryWhen** | Conditional retries | Avoid double-retry |

Example of uploading then reading while preserving dependency order:

~~~java
import com.azure.core.util.BinaryData;
import reactor.core.publisher.Mono;

Mono<String> savedThenRead =
    asyncBlob.upload(BinaryData.fromString("hello"), true)
        .then(asyncBlob.downloadContent())
        .map(BinaryData::toString);
~~~

If you need the ETag from the upload, use `flatMap`/compose to retain metadata rather than `then` which drops the value. Never use `map` returning a `Mono` and forget to flatten it.

## 20. Synchronous and Asynchronous Exception Handling

In sync code:

~~~java
import com.azure.storage.blob.models.BlobStorageException;

try {
    String text = syncBlob.downloadContent().toString();
    processText(text);
} catch (BlobStorageException e) {
    if (e.getStatusCode() == 404) {
        handleMissingDocument();
    } else {
        throw e;
    }
}
~~~

In reactive code:

~~~java
import com.azure.storage.blob.models.BlobStorageException;
import reactor.core.publisher.Mono;

Mono<String> result = asyncBlob.downloadContent()
    .map(BinaryData::toString)
    .onErrorResume(BlobStorageException.class, e -> {
        if (e.getStatusCode() == 404) {
            return Mono.empty();
        }
        return Mono.error(e);
    });
~~~

### 20.1. Mono.empty Does Not Automatically Mean HTTP 404

`Mono.empty` simply emits no value. In a WebFlux endpoint, map 404 explicitly with a response or error handler; do not let the request ambiguously return HTTP 200 with an empty body.

### 20.2. Transport Exceptions Differ from Service Exceptions

DNS, TLS, and timeout failures may surface as exceptions other than `BlobStorageException`. Classify errors by origin before retrying or reporting failure.

### 20.3. Never Log Payloads or Credentials

Log status, sanitized error code, request ID, duration, and operation; never log Blob SAS URLs, account keys, or sensitive file contents.

## 21. Lazy Execution and Subscribe-and-Forget

Example of an unexecuted publisher:

~~~java
Mono<?> planned =
    asyncBlob.upload(BinaryData.fromString("hello"), true);

// Neither returned nor subscribed: the operation may not have run yet.
~~~

In WebFlux, always **return the publisher**:

~~~java
@PostMapping("/api/hello")
public Mono<ResponseEntity<Void>> uploadHello() {
    return asyncBlob
        .upload(BinaryData.fromString("hello"), true)
        .thenReturn(ResponseEntity.ok().build());
}
~~~

This is a fragment inside a controller with `asyncBlob` injected and proper Spring imports, illustrating completion behavior only.

### 21.1. Fire-and-Forget Anti-Pattern

~~~java
asyncBlob.upload(BinaryData.fromString("hello"), true)
    .subscribe();
return Mono.just("Done");
~~~

The caller may see `"Done"` before the upload succeeds; cancellation and errors are detached from the HTTP request, making monitoring and retries difficult.

### 21.2. When to Subscribe Manually?

A CLI, batch coordinator, or worker with an explicit subscription lifecycle can subscribe with error and completion handlers. In reactive frameworks, usually let the framework subscribe.

### 21.3. Double Subscription and Duplicate Side Effects

Publishers from Azure async clients are typically cold; subscribing twice may execute two calls. For write operations, design for idempotency instead of assuming the publisher caches results.

## 22. flatMap Concurrency for Batches

A service needs to read multiple blobs without firing all calls simultaneously:

~~~java
import com.azure.storage.blob.BlobContainerAsyncClient;
import reactor.core.publisher.Flux;

import java.util.List;

BlobContainerAsyncClient container =
    BlobClients.asyncClient()
        .getBlobContainerAsyncClient("documents");

List<String> names = List.of(
    "a.txt", "b.txt", "c.txt");

Flux<String> results = Flux.fromIterable(names)
    .flatMap(name ->
        container.getBlobAsyncClient(name)
            .downloadContent()
            .map(body -> name + ": " + body.toString()),
        4 // Limit concurrent operations in this stage.
    );

// WebFlux: return results.
// Batch main: wait with a timeout and inspect errors.
~~~

### 22.1. Concurrency Does Not Equal Requests per Second

If each request completes quickly, even low concurrency can generate thousands of requests per second. Rate limiting by requests, bytes, or transaction budgets is a separate layer.

### 22.2. Multiply by Total Pods

20 Pods, each with `flatMap` concurrency of 16, can generate **320 in-flight operations**, not counting SDK multipart transfers. Set limits across the entire cluster/workload when sharing Azure service quotas.

### 22.3. Do Not Blindly Raise Concurrency

`downloadContent` materializes payloads; for instance, 100 in-flight downloads × 50 MB can exceed several GB of heap. Use streaming/range APIs for large files and enforce byte/memory budgets.

## 23. Preserving Order with concatMap and flatMapSequential

For order-dependent operations:

~~~java
Flux<String> ordered = Flux.fromIterable(names)
    .concatMap(name ->
        container.getBlobAsyncClient(name)
            .downloadContent()
            .map(BinaryData::toString));
~~~

**concatMap** executes each publisher sequentially in order. **flatMap** may emit results in completion order. **flatMapSequential** subscribes concurrently but buffers emissions to preserve order, which consumes memory if an earlier item is very slow.

### 23.1. Do Not Force Ordering on Independent Workloads

Independent uploads should generally use bounded parallelism. Events updating the same customer with version/ordering constraints should enforce domain-level ordering rather than relying solely on operators.

### 23.2. Slow First Item

`flatMapSequential` may wait a long time for the first item while buffering subsequent results; enforce timeouts and memory caps to avoid head-of-line blocking.

### 23.3. Error Isolation

If one item fails, a default `Flux` terminates the pipeline. Design per-item outcomes or proper quarantine semantics rather than blindly using `onErrorContinue`.
## 24. Backpressure vs. Azure Service Rate Limits

**Backpressure** controls demand inside a Reactive Streams pipeline. **Rate limiting** controls the requests, bytes, or transactions sent to an Azure service over time. The two complement each other; one does not replace the other.

~~~text
Message source / file queue
       |
   Demand / bounded queue
       |
   Global rate limit
       |
   Max in-flight semaphore
       |
   Azure Blob Async Client
       |
   Azure Storage throughput constraints
~~~

### 24.1. limitRate Does Not Know Azure Quotas

Reactor's **limitRate** shapes request demand between operators, but a single item might translate to 1, 10, or more network requests (paging, block uploads). Do not treat `limitRate` as an Azure transactions/sec limiter.

### 24.2. When the Producer Consistently Outpaces the Consumer

An in-JVM queue will grow continuously, leading to memory pressure or out-of-memory crashes. Use bounded queues, delay/reject policies, durable queuing in Service Bus/Storage Queue when needed, and scale to real capacity.

### 24.3. Fairness Across Tenants

If multiple tenants share a Storage account, enforce per-tenant budgets so one heavy tenant does not degrade latency for everyone else. Rely on verified authorization and tenant identity, never a user-supplied `tenantId`.

### 24.4. Retry Layers Multiply

A message worker retrying the outer task, an async client retrying HTTP, plus an upstream queue retry can multiply total attempts. Measure total attempts and configure backoff to avoid overload amplification.

## 25. Large File Transfers: Streaming Instead of Materializing

**downloadContent()** and **BinaryData.toBytes()** are convenient for small files, but consume excessive memory for large files.

### 25.1. Synchronous Stream Download

Example with the sync `BlobClient`:

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("report-copy.pdf");
try (OutputStream out = Files.newOutputStream(file)) {
    blob.downloadStream(out);
}
~~~

Control file paths, disk quotas, permissions, and idempotency. The path in the example is for lab demonstration only; never accept raw user-supplied paths to prevent path traversal.

### 25.2. Async Streaming

Depending on the SDK version, **BlobAsyncClient** provides methods supporting streaming/range downloads and publishers emitting data chunks. A sound design:

~~~text
Azure Blob Storage
      |
  network chunks
      |
Flux<ByteBuffer> or compatible streaming API
      |
bounded buffer + backpressure
      |
HTTP response or file sink
~~~

Never collect all chunks into a `List` just to assemble a multi-GB `byte[]`. Use streaming APIs and an HTTP framework that enforces end-to-end demand and cancellation.

### 25.3. Multipart Transfers Have Their Own Concurrency

A single upload call may split into multiple blocks and send them in parallel per SDK configuration. Total network concurrency is the combination of **application-level operations** and **internal requests/chunks per operation**. Never estimate total requests solely from the `flatMap` count.

### 25.4. Large File Transfers Involve More Than I/O

Account for content scanning, MIME validation, maximum upload sizes, storage lifecycle rules, access control, encryption, retry/integrity checks, and network/storage transaction costs.

## 26. Retries in the Azure SDK: Service Errors and Transient Failures

Azure Java clients typically include retry policies provided by the service SDK library and HTTP pipeline. **Default settings and status handling depend on the service and version**. Do not assume one universal default table across all of Azure.

| Scenario | Typical Meaning | Action |
|---|---|---|
| **400** | Malformed request, unsupported options | Fix the request |
| **401/403** | Credential, RBAC, SAS, or network policy | Check identity and permissions |
| **404** | Blob/container does not exist | Return Not Found or handle in business logic |
| **409** | Conflict | Check duplicate/lease/state |
| **412** | ETag/precondition failed | Resolve optimistic concurrency |
| **429** | One form of throttling if returned by the service | Backoff and capacity review |
| **503 Server Busy** | Storage may be temporarily overloaded | Backoff, shed load, scale based on evidence |
| **Other 5xx** | Transient service/transport error | Bounded retry via SDK |
| **Timeout/TLS/DNS** | Network or configuration issue | Classify and diagnose |

### 26.1. 429 Is Not the Only Sign of Throttling

Azure Storage may use other status codes or subcodes (especially **503 Server Busy**) when capacity is exceeded or throttling occurs. Do not monitor only 429 and conclude Storage is never throttled.

### 26.2. Double-Retry

If the SDK already retries, and then Reactor `retryWhen` and a job scheduler replay as well, total attempts can far exceed expectations. Define retry ownership and a workflow-wide retry budget.

### 26.3. Write Retries and Uncertain Outcomes

After a timeout, the server may have finished writing while the client never received the response. Replays must use deterministic blob names, ETags/conditions, or a proper business idempotency key—never generate a new name and call it a safe retry.

## 27. Conditional retryWhen for Idempotent Reads

If you need **an outer retry layer** for a read request after the SDK's built-in policy finishes, you can use:

~~~java
import com.azure.storage.blob.models.BlobStorageException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

import java.time.Duration;

Mono<byte[]> readWithBudget = asyncBlob.downloadContent()
    .map(data -> data.toBytes())
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(300))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.3)
            .filter(error -> {
                if (!(error instanceof BlobStorageException ex)) {
                    return false;
                }
                return ex.getStatusCode() == 429
                    || ex.getStatusCode() == 503;
            }))
    .timeout(Duration.ofSeconds(10));
~~~

### 27.1. Counting Retries Accurately

**Retry.backoff(2, ...)** allows up to 2 retries beyond the initial attempt. Because the SDK already performs internal retries, total latency can exceed expectations; measure both total deadlines and transport timeouts.

### 27.2. Transport Errors Differ from BlobStorageException

The snippet above only illustrates retrying service HTTP statuses. For transient network exceptions, build an appropriate classifier and never treat every `Throwable` as retryable.

### 27.3. Retry-After and Jitter

When an Azure service returns `Retry-After` or delay guidance, prefer the SDK policy or a configuration that honors that delay before adding outer retries. Reactor's outer `Retry` does not automatically extract `Retry-After` from all headers.

### 27.4. Never Use Infinite retryWhen in Batches

Infinite retries hang jobs, inflate operation costs, and mask configuration bugs. Enforce max attempts, alerts, and dead-letter/quarantine handling for unprocessable items.

## 28. Timeouts, Deadlines, and Cancellation

Several distinct concepts exist:

- **Connect timeout**: time allowed to establish a connection.
- **Network/read timeout**: depends on the HTTP transport and SDK.
- **Azure SDK per-call timeout**: via options/HTTP policies where supported.
- **Reactor timeout**: time limit waiting for a signal at a pipeline stage.
- **HTTP request deadline**: SLA commitment for responding to the user.
- **Job deadline**: time limit for the entire workflow, including retries.

### 28.1. Reactor Timeout

~~~java
Mono<String> response = asyncBlob.downloadContent()
    .map(BinaryData::toString)
    .timeout(Duration.ofSeconds(5));
~~~

On timeout, the reactive subscription is canceled and downstream receives a Reactor timeout error. However, **client-side cancellation does not guarantee the server rolled back a request it already received**.

### 28.2. Client Disconnect

When a browser closes a tab, WebFlux can cancel the subscription. Depending on the SDK and transport, the network request may be aborted or may still finish partially; never treat cancellation as a transaction rollback mechanism.

### 28.3. Multi-Layer Deadlines Must Align

If the frontend waits 3 seconds while the Java SDK has a 60-second timeout plus retries, workers remain busy long after the caller stopped waiting. Set deadlines consistent with SLOs and total retry budgets.

### 28.4. Never Swallow InterruptedException in Sync Executors

When using platform or virtual threads with interruptible blocking operations, honor cancellation/interruption contracts and do not keep retrying indefinitely during shutdown.

## 29. Do Java 21 Virtual Threads Replace the Async Client?

**Virtual threads** let Java run blocking-style code with much lower I/O wait overhead than traditional platform threads under suitable conditions.

Java 21 example:

~~~java
import java.util.List;
import java.util.concurrent.Executors;

List<String> names =
    List.of("a.txt", "b.txt", "c.txt");

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    var tasks = names.stream().map(name ->
        executor.submit(() ->
            container.getBlobClient(name)
                .downloadContent()
                .toString())
    ).toList();

    for (var task : tasks) {
        System.out.println(task.get());
    }
}
~~~

In this Java 21 example, **container** is a pre-configured sync `BlobContainerClient`, and the code omits exception classification, timeouts, and quota controls.

### 29.1. Virtual Threads Still Call the Sync API

The code remains blocking-style at the caller level; the runtime simply handles I/O waiting more efficiently. It does not share the same semantics as Reactor cancellation and backpressure.

### 29.2. Virtual Threads Do Not Create Azure Quota

Spawning 10,000 virtual threads does not guarantee the Storage account or HTTP transport can handle 10,000 concurrent requests gracefully. You still need semaphores, rate limits, connection/memory budgets, and benchmarks.

### 29.3. When Are Virtual Threads a Practical Choice?

An MVC-style Java service with imperative/JDBC logic that needs high request concurrency without rewriting the entire codebase to Reactor can evaluate virtual threads on a supported JDK/runtime. Check library compatibility, thread pinning, CPU-bound tasks, tracing, and `ThreadLocal` behavior.

### 29.4. Neither Virtual Threads Nor Async Is an Absolute Winner

- Virtual threads: sequential code, easier debugging, fits imperative migrations.
- Async Reactor: nonblocking pipelines, compositional streams, built-in backpressure/cancellation.
- Both: require controls at external service boundaries and can coexist depending on architecture.

## 30. Bridging Async Mono to CompletableFuture

If another Java library uses `CompletableFuture`, a Reactor `Mono` can be converted to a `Future`:

~~~java
import java.util.concurrent.CompletableFuture;
import reactor.core.publisher.Mono;

Mono<String> mono =
    asyncBlob.downloadContent()
        .map(BinaryData::toString);

CompletableFuture<String> future = mono.toFuture();

future.thenAccept(System.out::println)
      .exceptionally(error -> {
          System.err.println("Operation failed");
          return null;
      });
~~~

### 30.1. A Future Is Only a Bridge

Using `toFuture` bridges two abstractions; it does not magically spawn background worker threads—execution depends on the publisher and transport.

### 30.2. Lifecycle and Error Propagation

Ensure the caller retains the future reference, attaches timeout/cancellation/exception handlers, and never drops errors. Creating a future and ignoring it carries risks similar to fire-and-forget.

### 30.3. Do Not Bridge Everything Only to Call block()

If the system is already reactive, converting a `Mono` to a `Future` and calling **join/get** on the event loop reintroduces blocking. Only bridge at genuine architectural boundaries.

## 31. Context Propagation and Distributed Tracing

Applications need correlation between inbound HTTP requests and outbound Azure SDK calls.

~~~text
Incoming HTTP request
   -> correlationId / tenant / auth context
   -> DocumentService
   -> Azure Blob Async Client
   -> HTTP dependency span
   -> Storage response / request ID
~~~

### 31.1. ThreadLocal and Reactive Pipelines

Reactor operations can hop across threads and schedulers. **ThreadLocal/MDC is not automatically guaranteed to follow every asynchronous boundary**. Use Reactor Context or framework-supported context propagation and instrumentation.

Conceptual Reactor Context example:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> op = Mono.deferContextual(ctx -> {
    String requestId = ctx.getOrDefault(
        "correlationId", "none");

    return asyncBlob.downloadContent()
        .map(body -> {
            recordSafeMetric(requestId);
            return body.toString();
        });
}).contextWrite(
    Context.of("correlationId", "req-123"));
~~~

**recordSafeMetric** is an illustrative application function, not an Azure SDK method. In production, use proper OpenTelemetry/Application Insights tracing; never store credentials or tenant-sensitive payloads inside baggage or traces.

### 31.2. Track Retries and Attempts

One logical operation can produce multiple HTTP attempts. If you only time the controller without measuring SDK retries and transport latency, diagnosing p99 spikes becomes difficult.

### 31.3. Diagnostics Volume

Do not enable body/request-level wire logging for every production request. It adds overhead, increases ingestion costs, and risks leaking headers or query strings containing SAS tokens.

## 32. Reusing Clients, HTTP Pools, and Identity Lifecycles

| Component | Best Practice | Anti-Pattern |
|---|---|---|
| **BlobServiceClient** | Reuse across the application | Creating inside each HTTP handler |
| **BlobServiceAsyncClient** | Reuse with shared transport | Creating per Flux item |
| **TokenCredential** | Manage via DI | Manually refreshing keys/tokens per call |
| **HTTP client/transport** | Reuse, tune based on metrics | Creating thousands of pools |
| **Executor/Scheduler** | Bounded and closed on lifecycle | Unbounded new thread per blob |
| **Context** | Request-local context | Mutable static map shared across all users |

### 32.1. Client Construction Is Not Free

Repeatedly instantiating builders, clients, and transports increases memory usage, TLS handshakes, connection churn, and latency. Design them as application-scoped singletons or DI beans.

### 32.2. One Account Does Not Require One Client for Everything

Different services and libraries have distinct options for secondary endpoints, retries, transports, and scopes. You may need multiple clients for distinct purposes, but configure them intentionally and monitor their pools.

### 32.3. Shutdown

If the application creates custom HTTP clients, schedulers, or closeable resources, close them on shutdown per the API contract. Do not prematurely dispose of shared resources still used by other clients.

## 33. Security for Sync and Async Is the Same Responsibility

Sync and async differ in execution model; the security requirements remain identical:

- Authenticate with Entra managed identity where supported.
- Least-privilege data RBAC on Storage.
- Private endpoints, firewalls, VNets, and DNS per policy.
- TLS certificate validation.
- Never log account keys or SAS tokens.
- Never take arbitrary hosts or paths from untrusted input.
- Enforce blob ownership authorization at the application layer.
- Scan uploaded files when required.
- Enforce file size, request size, and content-type limits.
- Encryption and retention per compliance requirements.
- Never create public containers or long-lived SAS tokens as a "quick fix" for 403 errors.

### 33.1. Async Error Callbacks Easily Leak Data

When `subscribe`/`onError` callbacks log **exception.toString()** or raw HTTP requests, they may expose URLs containing SAS tokens. Use structured, sanitized logs and correlation IDs.

### 33.2. Managed Identity Does Not Replace Business Authorization

The Java service's identity may have permission to read the container, but the end user still needs authorization for a specific document. Never return any blob merely because the service principal has access.

### 33.3. ETag and Optimistic Concurrency

When overwriting user data concurrently, use conditional requests/ETags or versioning as supported by the API. Async does not automatically prevent lost updates.

## 34. Observability and Metrics to Measure

| Group | Metric | Purpose |
|---|---|---|
| **API** | p50/p95/p99 latency | User experience |
| **Throughput** | Successful operations/second | Effective capacity |
| **Service errors** | 403/404/409/412/429/503 | Permissions, business logic, throttling |
| **Retries** | Attempts, backoff, final error | Detect retry storms |
| **JVM** | CPU, heap, GC pauses, threads | Client overload |
| **Concurrency** | In-flight/queued jobs | Detect backpressure |
| **Network** | DNS/TLS latency, connections | Transport bottlenecks |
| **Storage** | Request count, bytes, service latency | Account capacity |
| **Cost** | Transactions, egress, storage, compute | Stay within budget |

### 34.1. Measure Throughput and Latency Together

An async approach can increase operations/sec while degrading p99 latency if concurrency is set too high. Always compare **successful throughput alongside SLOs**, not just outbound requests fired.

### 34.2. App Insights / Azure Monitor

Instrument inbound HTTP, Azure SDK dependency spans, exception classification, and custom metrics. Auto-instrumentation capabilities and field names depend on OpenTelemetry/Application Insights/SDK versions; always verify at runtime.

### 34.3. Avoid High-Cardinality Labels

Do not put full blob paths, raw user IDs, or request IDs into metric labels. Use low-cardinality tags such as operation, SDK mode, status category, and service environment; keep correlation IDs in traces and logs with proper retention.

## 35. Illustrative Performance Comparison Table

Lab example, **not a published benchmark**:

| Approach | Configured Concurrency | Thread Behavior | What to Observe |
|---|---:|---|---|
| Sync, 1 worker | 1 | Caller waits per operation | Easy to understand, low throughput |
| Sync, bounded executor | 8 | Up to 8 blocking workers | Thread/memory overhead |
| Async, flatMap | 8 | Nonblocking I/O per transport | p95, requests, memory |
| Async, flatMap | 64 | High in-flight operations | Throttling, retries, memory |
| Java 21 virtual threads | Semaphore 8 | Many virtual threads can exist | External capacity remains bounded |

**A comparison is unfair if one variant runs at concurrency 1 and another at 64.** For benchmarks, keep the dataset, endpoint, payload, warmup, network, and concurrency consistent; change only one variable at a time.

### 35.1. Lower Latency Does Not Mean Lower Cost

An async pipeline driving higher requests/sec can increase Storage transactions, network egress, and compute/logging costs. Size capacity to business goals.

### 35.2. A Single Request May Have Identical Latency

When downloading just 1 small blob with a 50 ms network RTT, sync and async will show nearly identical latency. Async shines when many operations are in flight and thread efficiency matters.

### 35.3. Async Code Carries Development Cost

Reactor debugging, context propagation, cancellation, and error handling add complexity. Performance gains must be large enough to justify the operational cost.
## 36. Testing Sync and Async Azure Clients

An application using external Azure services needs **three levels of testing**:

1. **Unit tests:** business service/gateway logic without network access.
2. **Integration tests:** connecting to an emulator or Azure lab environment for relevant features.
3. **Load/failure tests:** measuring concurrency, retries, quotas, timeouts, and policy-driven recovery.

### 36.1. Decouple the SDK from Business Logic in Tests

Define an interface:

~~~java
public interface DocumentGateway {
    String readSmallTextSync(String blobName);

    reactor.core.publisher.Mono<String> readSmallTextAsync(
        String blobName);
}
~~~

In unit tests, mocking or faking `DocumentGateway` lets you verify authorization, fallbacks, and error mapping without calling Azure.

### 36.2. StepVerifier for Reactive Results

With the appropriate `reactor-test` dependency:

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<String> result = Mono.just("hello");

StepVerifier.create(result)
    .expectNext("hello")
    .verifyComplete();
~~~

This is a basic Reactor test and does not prove real Azure behavior. Using a `Mono` from a fake gateway, you can verify completion, errors, and some context propagation behaviors.

### 36.3. Testing an Unsubscribed Publisher

If code constructs a `Mono` without returning or subscribing to it, a fake can record that no real operation executed. Write tests verifying that business handlers **properly return the publisher** or that batch runners await completion.

### 36.4. Checking Duplicate Subscriptions

If a cold write publisher is subscribed to twice, a mock should record two attempts; test idempotency policies or duplicate-error handling per business rules.

### 36.5. Testing Cancellation

Use a delayed publisher with a test scheduler or simulate an HTTP client disconnect; observe cancellation callbacks and resource cleanup. Never assume the server rolled back an in-progress upload.

## 37. Azurite and Azure Lab Testing

**Azurite** is an Azure Storage emulator supporting a subset of Blob/Queue/Table APIs for local development. Use it to test basic `BlobClient`/`BlobAsyncClient` operations without provisioning real Azure resources.

### 37.1. What Can Azurite Help With?

- Testing create/read/delete blob operations and supported request behaviors.
- Verifying serialization and container/blob naming.
- Exercising sync/async code paths against a local endpoint.
- Generating test data to learn paging and listing.

### 37.2. Azurite Is Not Azure Production

Do not expect the emulator to match:

- Full Microsoft Entra RBAC/managed identity enforcement.
- Azure Private Endpoints, network topology, and zones/regions.
- Real-world throttling, quotas, and latency.
- Every Blob SDK feature and version.
- Real Azure Storage billing and observability.

### 37.3. Two Distinct Test Types

- **Local emulator:** validates basic behavior quickly and at low cost.
- **Azure lab account:** validates identity, TLS/private networking, SDK compatibility, service-side pagination/retries, metrics, and real request limits.

### 37.4. Never Treat Lab Account Keys Like Production

Azurite uses dedicated development credentials/connection strings. Never commit production keys into tests, and never reuse real account credentials against an emulator.

## 38. When Multiple Operations Partially Succeed

Suppose a batch needs to upload 100 blobs. After 60 successes, the 61st request receives 503 and the pipeline terminates.

### 38.1. Both Sync and Async Have Partial Success

A failing `Flux` does not automatically roll back the previous 60 uploads. A synchronous `for` loop throwing an exception on item 61 does not roll back the prior 60 items either.

### 38.2. Track Per-Item Outcomes

Conceptual example:

~~~java
record UploadOutcome(
    String blobName,
    boolean success,
    String errorCode
) {}
~~~

In a reactive batch, instead of letting one failure abort everything, you can map **expected per-item errors** into an outcome for checkpointing:

~~~java
Flux<UploadOutcome> outcomes =
    Flux.fromIterable(names)
        .flatMap(name ->
            container.getBlobAsyncClient(name)
                .upload(BinaryData.fromString("demo"), true)
                .map(result ->
                    new UploadOutcome(name, true, ""))
                .onErrorResume(error ->
                    Mono.just(
                        new UploadOutcome(
                            name, false, "UPLOAD_FAILED"))),
            4);
~~~

This is a demo—**never swallow all exceptions in production**: log sanitized exception classifications/metrics, retry per policy, route failures to dead-letter/quarantine, and define a replay procedure. Consider a batch successful only when all outcomes meet criteria.

### 38.3. Retries and Checksums

For real files, use deterministic blob names, checksum/integrity validation, and conditional writes where needed so retries neither create duplicates nor overwrite newer data.

### 38.4. Choosing Checkpoints

Checkpoints must reflect durably completed uploads, not merely the last name pushed into the `Flux`. When processing out of order, checkpoint by contiguous completed offsets or per-item status to avoid skipping failures.

## 39. Cost, Quotas, and Application Architecture

Sync and async **do not have separate pricing tiers** in Azure Storage. Costs depend on:

- Storage capacity and tier.
- Number of read/write/list operations.
- Data transfer volume and egress.
- Replication, snapshots, and lifecycle features.
- Azure compute for App Service/AKS/Functions.
- Network gateways and private endpoint/egress where applicable.
- Azure Monitor/Log Analytics ingestion and retention.

### 39.1. When Async Saves Resources

With many concurrent I/O-bound operations, nonblocking async can reduce the number of platform threads needed in Java. That *may* lower compute overhead when confirmed by benchmarks, though you must factor in added complexity and transport/pooling overhead.

### 39.2. When Async Increases Costs

If switching to async sharply raises operations/sec, Storage transactions, egress, and logging can climb; overloading the service triggers retries, higher charges, and worse p99 latency. Optimize for **cost per useful successful operation**, not raw requests sent.

### 39.3. More Clients Create More Pools

Repeatedly creating HTTP/SDK clients increases memory, sockets, DNS/TLS overhead, and cloud compute. Reuse clients for efficient management.

### 39.4. Scaling Compute Does Not Scale Service Quotas

Adding Pods via HPA or increasing thread counts does not give a Storage account infinite capacity. Monitor account throughput/throttling, request patterns, and partition hot spots before increasing load.

## 40. Runbook When Async Workloads Slow Down or Fail

A scenario:

~~~text
10:00  App p95 = 150 ms, healthy success rate
10:05  Batch ingestion starts
10:07  In-flight = 2,000, JVM memory climbs
10:08  Azure Storage 503s and retries spike
10:10  API p99 = 8 seconds, download failures rise
~~~

### Step 1 — Isolate the Scope

Were Pods or `flatMap` concurrency just increased, multipart transfer enabled, or a new batch job started? Is it affecting one storage account/container or the entire system?

### Step 2 — Classify Errors

Inspect 403, 404, 409/412, 429/503, and network exceptions separately. Never adjust capacity to fix an RBAC error or a missing blob.

### Step 3 — Read Telemetry

Successful throughput, in-flight count, queue depth, heap/GC, thread count, retry attempts, p95/p99 latency, account service latency, and Azure request IDs.

### Step 4 — Locate the Bottleneck

- Are app threads blocked inside WebFlux?
- Are there too many concurrent `downloadContent` calls?
- Is Storage being throttled or is one blob/key a hot spot?
- Are network/NAT/proxy connection limits being hit?
- Are SDK clients being recreated continuously?
- Are large files exhausting the JVM heap?

### Step 5 — Protect the System

Reduce concurrency, throttle incoming jobs, pause low-priority batches, prioritize interactive APIs, and switch to streaming and bounded queues.

### Step 6 — Fix the Root Cause

Optimize request patterns, payload sizes, transport/pool tuning, timeout/retry policies, or throughput architecture. Scale capacity only with supporting evidence; keep a rollback plan ready.

### Step 7 — Reconcile and Replay

Verify partial uploads, idempotency, and per-item statuses. Replay failed items without creating duplicate side effects.

## 41. Lab 1: Running the Same Operation with Sync and Async Clients

**Use only an authorized Azure lab subscription/resource group.** Never write to production accounts and never print keys or tokens.

### A. Preparation

1. Create or use a lab Storage account supporting Blob service.
2. Create a container named **documents**.
3. Use a managed identity or developer identity and grant appropriate Blob data-plane permissions.
4. Configure the endpoint via the **AZURE_STORAGE_BLOB_ENDPOINT** variable.
5. Verify HTTPS, DNS, and firewall/private network access from the Java runtime host.
6. Create a Java 17 project with approved dependency versions.

### B. Sync

1. Create `BlobServiceClient` via `BlobClients.syncClient()`.
2. Upload a small blob using `BinaryData`.
3. Download it with `downloadContent()`.
4. Print non-sensitive sample content.
5. Catch 404 errors using `BlobStorageException`.
6. Measure start/end timestamps and request latency.

### C. Async

1. Create `BlobServiceAsyncClient` via `BlobClients.asyncClient()`.
2. Construct a `Mono` with `upload().then(downloadContent())`.
3. Confirm no side effect occurs before subscribing if the SDK uses cold semantics.
4. In a CLI app, block with a timeout at the `main` boundary.
5. In WebFlux, return the `Mono` without blocking.
6. Measure the same workload as sync.

### D. Comparison

| Criterion | Sync | Async |
|---|---|---|
| API return type | Direct BinaryData/response | Mono/Flux/PagedFlux |
| Caller thread | Waits for completion | Nonblocking when composed properly |
| Errors | Exception | onError signal |
| Concurrency | Bounded threads/virtual threads | Bounded flatMap/subscriptions |
| Cancellation | Via thread/transport APIs | Via subscription/transport APIs |
| Memory | Depends on payload and usage | Depends on payload/buffers/concurrency |

**The lab does not need to prove async is always faster.** It should explain the mechanics and measure the actual differences.

## 42. Lab 2: Downloading Multiple Blobs with Controlled Concurrency

Use **50–100 small blobs** created in the lab container and a separate Java runner for each approach.

### A. Sync Baseline

1. Use a `for` loop with concurrency = 1.
2. Record successful operations/sec, p95, and memory.
3. Use a bounded `ExecutorService` with 4/8 concurrent tasks.
4. Keep the same dataset and payload.

### B. Async Baseline

1. Use `Flux.fromIterable(names)`.
2. Use `flatMap(downloadContent(), concurrency=4)`.
3. Increase concurrency to 8 if the environment permits.
4. Compare p95/p99, success rate, threads, and memory.

### C. Inject Controlled Failures

1. Request a non-existent blob.
2. Verify 404 is not retried infinitely.
3. Use a mock HTTP backend to simulate 503/`Retry-After` without stressing shared Azure resources.
4. Test timeouts/cancellation and observe final outcomes.
5. Never log sensitive raw blob contents.

### D. Recording Table

| Metric | Sync 1 | Sync 8 | Async 4 | Async 8 |
|---|---|---|---|---|
| Successful operations/s | Measure | Measure | Measure | Measure |
| p95 latency | Measure | Measure | Measure | Measure |
| p99 latency | Measure | Measure | Measure | Measure |
| JVM peak threads | Measure | Measure | Measure | Measure |
| JVM heap/GC | Measure | Measure | Measure | Measure |
| Service 429/503 | Measure | Measure | Measure | Measure |
| Retry attempts | Measure | Measure | Measure | Measure |
| Egress/transaction estimate | Measure | Measure | Measure | Measure |

### E. Completion Criteria

Explain why one configuration achieved higher operations/sec or fewer threads; what happened to memory and p99 when raising concurrency; and when sync should be kept for simplicity while still meeting SLOs.

## 43. Lab 3: Framework Integration, Identity Verification, and Cleanup

### A. MVC

1. Create a GET endpoint that reads a small text blob.
2. Use the sync `BlobClient` via a DI-managed service.
3. Map 404 to HTTP 404.
4. Verify authorization for the user's blob.
5. Measure thread pool utilization.

### B. WebFlux

1. Create a GET endpoint returning a `Mono`.
2. Use `BlobAsyncClient` inside the service.
3. Do not block or subscribe in the controller.
4. Test cancellation when the HTTP client disconnects.
5. Simulate a blocking call to observe why it should never run on the event loop; never test this in production.

### C. Security

1. Create a test principal with read-only permissions on the container.
2. Verify reads succeed and writes are properly denied.
3. Confirm no account keys or SAS tokens appear in logs.
4. Verify private DNS/networking if the lab uses a private endpoint.
5. Never open the firewall to allow-all to bypass a 403.

### D. Cleanup

1. Stop lab batch jobs and HTTP apps.
2. Delete blobs, containers, or resource groups **only after confirming they belong solely to the lab**.
3. Revoke lab role assignments/keys if needed.
4. Check Cost Management to ensure no unnecessary compute or storage remains.

## 44. Production Checklist

- [ ] Analyzed workload and chose sync/async matching the framework.
- [ ] SDK versions compatible, dependencies pinned/BOM-managed, and CVE-scanned.
- [ ] Storage account endpoint sourced from trusted configuration.
- [ ] Using Entra/managed identity and least-privilege data RBAC.
- [ ] Networking, private DNS, and TLS tested from the actual runtime.
- [ ] Clients, credentials, and HTTP transports are reused.
- [ ] Clients are never created per request or per Flux item.
- [ ] Never using `Mono.just` to wrap a blocking call.
- [ ] Never blocking inside the Reactor event loop.
- [ ] Never using subscribe-and-forget inside HTTP handlers.
- [ ] Max in-flight limits and rate limits configured for actual capacity.
- [ ] Bounded queues, timeouts/deadlines, and overload responses in place.
- [ ] Large files are never collected into unbounded `byte[]` arrays.
- [ ] `PagedFlux` listings are bounded/paginated.
- [ ] Batches handle per-item errors and checkpoint accurately.
- [ ] Idempotency/ETags enforced for writes and replays.
- [ ] SDK internal retries understood and double-retry avoided.
- [ ] Never blindly retrying 400/403/404 responses.
- [ ] Monitoring both 429 and 503 Storage throttling.
- [ ] Cancellation is never treated as server-side rollback.
- [ ] Context propagation and tracing work across async boundaries.
- [ ] Logs never contain SAS tokens, keys, access tokens, or raw blob data.
- [ ] Metrics track p95/p99, successful throughput, queues, GC, and retries.
- [ ] Runbooks exist for 403, 404, 409, 412, 429/503, and timeouts.
- [ ] Benchmarks compare sync and async at equal concurrency and dataset.
- [ ] Tested virtual threads if using Java 21 instead of Reactor.
- [ ] Cost budget covers Storage, compute, network, and logs.
- [ ] Mock/integration tests and lab cleanup process established.

## 45. Self-Check Questions

1. How do synchronous and asynchronous differ at the caller layer?
2. How does blocking I/O differ from nonblocking I/O?
3. Is concurrency synonymous with parallelism?
4. How does `BlobServiceClient` differ from `BlobServiceAsyncClient`?
5. How does `BlobClient.upload` differ from `BlobAsyncClient.upload` in its return value?
6. Why does an Azure SDK builder require an endpoint and credential?
7. Does a managed identity automatically have Blob data-plane permissions?
8. Does Azure ARM Contributor implicitly allow reading blobs?
9. Why should you not create an Azure client on every HTTP request?
10. How do `Mono` and `Flux` differ in number of emissions?
11. How many HTTP requests can a `PagedFlux` issue?
12. Can a cold publisher cause duplicate writes if subscribed to twice?
13. If you create a `Mono` without returning or subscribing to it, does the operation run?
14. Why must you not call `block()` on the WebFlux event loop?
15. Is `Mono.just(getSyncResult())` truly nonblocking?
16. Does `boundedElastic` turn blocking I/O into true nonblocking I/O?
17. Does `flatMap` with concurrency 8 guarantee at most 8 requests across the entire cluster?
18. Does `flatMap` preserve input order?
19. What trade-offs do `concatMap` and `flatMapSequential` make?
20. Why does `limitRate` not replace Azure request rate limiting?
21. What is the risk of calling `downloadContent` on a 1 GB blob?
22. How do SDK multipart transfers affect total operation counts?
23. Why is Storage throttling not limited to HTTP 429?
24. What happens when both SDK retries and outer retries are active?
25. Does a timeout or cancel guarantee an upload was rolled back?
26. For write timeouts, why are idempotency/ETags needed?
27. How do Java 21 virtual threads differ from Reactor in programming model?
28. Do virtual threads increase Azure Storage quotas?
29. Do `ThreadLocal`/MDC always follow Reactor schedulers?
30. Why are correlation IDs needed and why must SAS tokens never be logged?
31. When a 100-file batch fails after 60 files, is there automatic rollback?
32. Can Azurite replace testing Entra RBAC on real Azure?
33. Which metrics should be used to compare sync and async fairly?
34. Why can higher throughput lead to higher costs?
35. When should sync be preferred for simplicity and SLO compliance?

## 46. Summary

**Synchronous and asynchronous Azure Java clients** are two ways to use the same Azure service with different execution contracts. **Sync** returns a value or throws an exception after completion, fitting imperative code, MVC, and simple batch jobs. **Async** returns **Mono/Flux/PagedFlux**, enabling efficient nonblocking pipelines for heavy I/O workloads when supported by the framework and all dependencies.

The **BlobServiceClient/BlobServiceAsyncClient** examples show how to build clients via builders and managed identities, and how to upload, download, and list using sync or reactive methods. Using async properly requires understanding **lazy subscription, flatMap/concatMap/then, error propagation, cancellation, and backpressure**—while avoiding event-loop blocking, `Mono.just` wrapping sync calls, and subscribe-and-forget.

Sustainable performance depends on **bounded concurrency, rate limiting, streaming large files, client reuse, timeouts, idempotent writes, SDK retry policies, tracing, and real benchmarks**. Java 21 virtual threads offer a strong option for certain imperative applications, yet they cannot bypass quotas or replace external backpressure design.

Combining this Java knowledge with **Microsoft Entra ID, Azure Blob Storage, App Service/AKS/Functions, Azure networking, Azure Monitor, and Cost Management** helps you choose the right client model: accurate data, reliable applications, strong security, and controlled costs.




