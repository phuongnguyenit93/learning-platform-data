# Distinguishing Synchronous, Asynchronous, and Reactive Client Models

When a Spring Boot service calls object storage, sends a message, or queries a managed database, the application must decide **how to wait for I/O results**. You can invoke the SDK **synchronously (blocking)**, use an **asynchronous** client returning a future/callback, or organize a **reactive** processing pipeline using `Mono`, `Flux`, and Reactive Streams components. All three approaches can talk to the same cloud service, yet they differ significantly in thread usage, when the operation starts, error handling, load limiting, and testing.

This lesson belongs to the **Integration Architecture** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services on **AWS, Azure, and Google Cloud** via the corresponding Spring Cloud libraries, from identity and permissions to storage, messaging, data, secrets, integration testing, and provider comparisons. Here, the focus is choosing the right execution model for calls from business logic through Spring/SDK to the cloud while preserving each provider's guarantees.

## 1. Learning Objectives

After this lesson, you can:

- Describe the lifecycle of a cloud call in blocking, `CompletableFuture`, and Reactor styles, from request to response or error.
- Explain the differences between **asynchronous**, **non-blocking threads**, **reactive**, **streaming**, and **parallel processing**.
- Use AWS SDK for Java v2 `S3Client` and `S3AsyncClient` properly in examples; understand how to compare them with Azure and Google Cloud clients.
- Integrate `CompletableFuture` into `Mono` without triggering operations too early or blocking the event loop.
- Choose a model for REST APIs, large uploads, message queues, managed databases, and secret access.
- Design timeouts, retries, idempotency, observability, and tests suited to the execution model.

## 2. Synchronous, Asynchronous, Reactive: Distinct Concepts

| Characteristic | Synchronous Client | Asynchronous Client | Reactive Pipeline |
| --- | --- | --- | --- |
| Common API return type | Direct result or thrown exception | `CompletableFuture<T>`, `CompletionStage<T>`, callback, or other future | `Mono<T>`, `Flux<T>` / `Publisher<T>` |
| Calling thread | Typically waits for I/O to complete | Typically returns before I/O completes | Depends on scheduler/operators; can be non-blocking if underlying source supports it |
| Operation start | During the method call | Many SDKs **start immediately upon calling** the async method | Publishers can be **lazy**, typically starting upon subscription; depends on source |
| Receiving results | Next statement after call or `catch` | Callback/continuation/completion | `onNext`, `onComplete`, `onError` signals |
| Handling multiple results | Iterator/stream depending on API | Single-result future or dedicated callback/stream API | `Flux` supports 0..N data signals |
| Reactive Streams backpressure | None by default | None merely because an API returns a future | Demand mechanism between compliant components; impact on SDK/network depends on adapter |
| Typical fit | Simple use cases, JDBC, low-concurrency batches | Many independent I/O calls, freeing calling threads | WebFlux/R2DBC pipelines, streaming, or throttled data processing |

**Synchronous does not mean whole-system sequential processing**: many requests can still run concurrently across multiple threads. **Asynchronous does not automatically mean parallel**: a future represents future completion; how many tasks run concurrently depends on executors, connection pools, and the SDK. **Reactive does not mean the SDK has become non-blocking**: a `Mono` wrapping a blocking JDBC/S3 call still contains a blocking operation unless isolated onto a suitable scheduler.

Additionally, a `Future` typically represents **a single final result**. A `Flux` represents **a stream of signals** with subscription, demand, and cancellation. You cannot conclude a client supports streaming file uploads just because it has a `putObjectAsync` method; true byte-stream uploading is a separate requirement.

## 3. Visualizing the Path of the Three Models

Suppose an HTTP handler needs to save a document to object storage:

~~~mermaid
flowchart TD
    R[HTTP handler / application service] --> M{I/O invocation style}
    M -->|Synchronous| S[S3Client.putObject]
    S --> W[Thread waits for response]
    W --> X[Return result / throw exception]
    M -->|Asynchronous| A[S3AsyncClient.putObject]
    A --> F[CompletableFuture]
    F --> C[Completion callback]
    M -->|Reactive| P[Mono or Flux]
    P --> SUB[Subscribe and demand]
    SUB --> N[Non-blocking SDK / reactive driver]
    N --> SIG[onNext / onComplete / onError]
    S --> CLOUD[Managed cloud service]
    A --> CLOUD
    N --> CLOUD
~~~

In the **reactive** branch, the `Mono`/`Flux` layer coordinates signals; underneath, you need an **async SDK** or **reactive driver** if true non-blocking execution is the goal. A publisher can be constructed without making any network call yet. However, if a future is created **before** the publisher, the network call may already start before anyone subscribes.

### 3.1. Simple Timeline

~~~text
Sync:
thread A: validate -> call SDK ===================> response -> continue
                       (wait I/O)

Async future:
thread A: validate -> call async SDK -> return future -> continue
                                  ... I/O ...
SDK/executor:                              complete future -> continuation

Reactive with lazy source:
thread A: create Mono -> return Mono
subscriber: subscribe -> start async I/O -> receive signals -> complete
~~~

This illustrates the conceptual flow. Actual SDK and operator threads depend on the implementation; `CompletableFuture.thenApply` sometimes runs on the thread that completes the future, whereas `thenApplyAsync` uses the common or a specified executor.

## 4. Synchronous Client: Easy to Follow, Thread May Be Held

With **AWS SDK for Java v2**, `S3Client` provides a synchronous API. The following example assumes the Spring Cloud AWS starter configured the `S3Client` bean, the bucket is supplied by the environment, and the workload has the corresponding `s3:PutObject` permission:

~~~java
// S3BlockingStorage.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
public class S3BlockingStorage {
    private final S3Client s3;
    private final String bucket;

    public S3BlockingStorage(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public void put(String key, byte[] bytes) {
        PutObjectRequest request = PutObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .build();

        s3.putObject(request, RequestBody.fromBytes(bytes));
        // Only reaches here after the SDK returns successfully.
    }
}
~~~

The flow `controller → service → S3BlockingStorage.put → S3Client.putObject → HTTPS → S3` is easy to read, debug, and well-suited for moderate concurrency. The SDK can manage connection pools, timeouts, and retries according to its configuration; **blocking** simply describes that the calling thread waits until the call finishes.

When using **Spring MVC**, requests are usually handled by a servlet container thread. That thread waits while the service calls S3 synchronously. With many long I/O requests, thread limits, connection pools, and timeouts can become bottlenecks. Java virtual threads can reduce the cost of holding platform threads in some blocking apps, but they **do not turn a synchronous SDK into a reactive one**, nor do they eliminate connection limits, quotas, or bandwidth caps.

### 4.1. Errors in Synchronous Calls

~~~java
try {
    blockingStorage.put(key, data);
} catch (software.amazon.awssdk.services.s3.model.S3Exception ex) {
    // Translate S3 error code into an application-appropriate error.
    throw ex;
} catch (software.amazon.awssdk.core.exception.SdkClientException ex) {
    // May be a client/transport/credential error.
    throw ex;
}
~~~

This example only distinguishes where errors originate and is not a production exception-handling strategy. A `403` error requires inspecting identity/IAM/bucket policies and should not be retried blindly; timeouts, `429`, throttling, and transient errors can be candidates for bounded retries. Avoid writing access keys, tokens, and document contents into logs.

## 5. Asynchronous Client: Future Represents a Later Result

AWS SDK v2's `S3AsyncClient` returns `CompletableFuture` for corresponding operations. The example uses `AsyncRequestBody.fromBytes` to stay concise; this approach still **holds the entire payload in memory**, even though I/O is executed asynchronously.

~~~java
// AsyncDocumentStorage.java
import java.util.concurrent.CompletableFuture;

public interface AsyncDocumentStorage {
    CompletableFuture<Void> put(String key, byte[] bytes);
}
~~~

~~~java
// S3AsyncDocumentStorage.java
import java.util.concurrent.CompletableFuture;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.async.AsyncRequestBody;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
public class S3AsyncDocumentStorage implements AsyncDocumentStorage {
    private final S3AsyncClient s3;
    private final String bucket;

    public S3AsyncDocumentStorage(
            S3AsyncClient s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    @Override
    public CompletableFuture<Void> put(String key, byte[] bytes) {
        PutObjectRequest request = PutObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .build();

        return s3.putObject(request, AsyncRequestBody.fromBytes(bytes))
            .thenAccept(response -> {
                // SDK received a successful response; no blocking work here.
            });
    }
}
~~~

**Spring note:** The `S3AsyncClient` bean must actually exist. Depending on version/configuration, the starter may auto-configure an async bean or you may need to declare a separate bean yourself. Never assume that having `S3Client` means `S3AsyncClient` is always present. Check conditional auto-configuration, the bean list, and the Spring Cloud AWS BOM in use.

A service can return the future outward without calling `join()` or `get()` on the request thread:

~~~java
// AsyncDocumentService.java
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

public class AsyncDocumentService {
    private final AsyncDocumentStorage storage;

    public AsyncDocumentService(AsyncDocumentStorage storage) {
        this.storage = storage;
    }

    public CompletableFuture<String> save(byte[] bytes) {
        if (bytes == null || bytes.length == 0) {
            return CompletableFuture.failedFuture(
                new IllegalArgumentException("Document is empty"));
        }

        String key = "documents/" + UUID.randomUUID();
        return storage.put(key, bytes).thenApply(ignored -> key);
    }
}
~~~

**Start time:** `storage.put(...)` has already been invoked when `save(...)` returns the future; the save may already be in flight. `thenApply` runs only if the first future succeeds. On failure, the future completes exceptionally; calling `save()` does not necessarily throw an exception immediately at that line.

**Do not** call `future.join()` inside the Spring WebFlux event loop because that turns the calling path blocking. For Spring MVC, an application can integrate future results using the framework's async request processing support; use the model appropriate for your controller and stack.

### 5.1. Callbacks, Continuations, and Executors

~~~java
storage.put(key, bytes)
    .whenComplete((ignored, error) -> {
        if (error != null) {
            // Record error and complete workflow per policy.
        } else {
            // Record success.
        }
    });
~~~

Callbacks should be **fast and non-blocking** because they may execute on the thread that completed the task. If heavy CPU processing or blocking work is needed, offload it to a managed, appropriately bounded executor. Using `thenApplyAsync` moves the continuation to an executor, yet **does not make the initial network call any faster**.

When chaining two independent operations, futures can be combined via `thenCombine` or `allOf`, but concurrent request counts must be bounded. Firing tens of thousands of futures simultaneously can exhaust connection pools, consume memory, or hit cloud quotas. Async APIs do not automatically provide Reactive Streams backpressure.

## 6. Reactive: Coordinating Data, Signals, and Demand

In the Spring ecosystem, the reactive model typically uses **Project Reactor**: `Mono<T>` emits at most one value, while `Flux<T>` emits multiple values. Spring WebFlux, Spring Data R2DBC, and certain reactive clients/integrations can build non-blocking pipelines if underlying I/O sources genuinely support it.

A `Mono` is typically a description of work: it is **subscribed to** by a consumer such as Spring WebFlux. A publisher can emit `onNext`, `onComplete`, or `onError`. Reactive Streams adds **demand** so subscribers communicate how many items they wish to receive. However, a `Mono` simply wrapping a future usually does not provide meaningful streaming/backpressure benefits for **a single response**.

### 6.1. Wrapping an Async SDK in Mono at the Right Time

Suppose we use `AsyncDocumentStorage` from section 5:

~~~java
// ReactiveDocumentService.java
import java.util.UUID;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveDocumentService {
    private final AsyncDocumentStorage storage;

    public ReactiveDocumentService(AsyncDocumentStorage storage) {
        this.storage = storage;
    }

    public Mono<String> save(byte[] bytes) {
        return Mono.defer(() -> {
            if (bytes == null || bytes.length == 0) {
                return Mono.error(
                    new IllegalArgumentException("Document is empty"));
            }

            String key = "documents/" + UUID.randomUUID();
            return Mono.fromFuture(storage.put(key, bytes))
                .thenReturn(key);
        });
    }
}
~~~

`Mono.defer` defers both key generation and the SDK call until **subscription**; each subscription creates a new key and may cause **a new object write**. Watch out when using `retry`, `repeat`, or subscribing multiple times: those operators can repeat the write operation. If business rules require idempotency, keys and request identifiers must be managed outside per-attempt random generation, or designed so retries share a single business identifier.

Conversely, the following code can trigger I/O **too early**:

~~~java
// Unsuitable if you want the request to start only on subscription:
var future = storage.put(key, bytes); // Async SDK may start immediately.
Mono<Void> publisher = Mono.fromFuture(future);
~~~

`Mono.fromFuture(future)` represents signals from an already-created future; it does not make an already-running future lazy. For APIs with supplier/lazy adapters, still verify actual invocation timing for the Reactor and SDK versions in use.

### 6.2. Spring WebFlux Controller

~~~java
// DocumentController.java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/documents")
public class DocumentController {
    private final ReactiveDocumentService documents;

    public DocumentController(ReactiveDocumentService documents) {
        this.documents = documents;
    }

    @PostMapping(consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public Mono<ResponseEntity<Map<String, String>>> upload(
            @RequestBody Mono<byte[]> body) {
        return body.flatMap(documents::save)
            .map(key -> ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("key", key)));
    }
}
~~~

Spring WebFlux subscribes to and coordinates the publisher during response processing. **Never call `subscribe()` inside a controller or service** just to “run” a pipeline and return `200`: doing so creates untracked work, loses error handling, and returns a response before the save completes.

The `Mono<byte[]>` pattern only illustrates a single-payload flow. For large files, use `Flux<DataBuffer>`, supported streaming uploads, or permission-scoped direct-to-cloud uploads; reading the entire body into `byte[]` can exhaust memory even though the outer API is reactive. Converting `DataBuffer` to a cloud SDK request body must follow streaming contracts, buffer lifecycles, and memory limits; never assume two publishers can be wired directly without an adapter.

## 7. Wrapping a Blocking SDK in Mono: When Is It Acceptable?

Sometimes a project uses Spring WebFlux, yet a service or SDK only provides a synchronous API. If you must keep a blocking SDK, **isolate I/O** from the event loop using a managed scheduler:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<String> saveWithBlockingClient(
        S3BlockingStorage storage, String key, byte[] bytes) {
    return Mono.fromCallable(() -> {
            storage.put(key, bytes);
            return key;
        })
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`Mono.fromCallable` defers the call until subscription; `subscribeOn(boundedElastic())` runs the blocking task on a pool more appropriate than the event loop. Even so, **the SDK is still blocking**; scheduler threads and queues also have limits. This is a pragmatic integration workaround for a bounded blocking section; it **does not create non-blocking I/O** and does not replace real load testing.

Common mistake:

~~~java
// DO NOT do this on the WebFlux event loop:
Mono<String> result = Mono.just(blockingOperation());
// blockingOperation() runs immediately when constructing Mono.
~~~

If the entire path uses JDBC, sync SDKs, and blocking request handling, **Spring MVC** can be simpler and easier to operate than a WebFlux app that must offload every call to `boundedElastic`. Choose the stack based on load profile, streaming needs, and dependency non-blocking support—not framework branding.

## 8. Comparing Support Across AWS, Azure, and Google Cloud

There is no common “`CloudAsyncClient`” API shared across all three providers. Spring Cloud libraries often help configure beans, templates, or listeners, but **return types depend on the specific SDK and service**.

| Provider / service | Typical synchronous API | Typical async / reactive API | Things to remember |
| --- | --- | --- | --- |
| **AWS S3** | AWS SDK v2 `S3Client` | `S3AsyncClient` returning `CompletableFuture`; async bodies per SDK API | `AsyncRequestBody.fromBytes` still buffers payload in memory; streaming requires appropriate APIs |
| **AWS SQS** | `SqsClient` | `SqsAsyncClient`; Spring Cloud AWS SQS template/listener per version | Queue consumers involve poll/ack/visibility; listeners are not Reactive Streams pipelines by default |
| **Azure Blob Storage** | `BlobClient`, `BlobServiceClient` | `BlobAsyncClient`, `BlobServiceAsyncClient`; many Azure SDK async APIs return `Mono`/`Flux` | Verify read/write flows and auth/transport config when using starters |
| **Azure Service Bus** | Sync sender/receiver clients if provided by SDK version | Async clients/processors/callbacks per Azure SDK | Complete/abandon/dead-letter, locks, and sessions affect outcomes |
| **Google Cloud Storage** | `Storage` in Java client typically provides blocking calls | Some features/versions offer dedicated async or streaming APIs; check exact client/version | Do not assume every GCS call returns a future or Reactor publisher |
| **Google Cloud Pub/Sub** | SDK/abstraction offers corresponding operations | Java Publisher typically returns `ApiFuture`; Subscriber uses callbacks | `ApiFuture` differs from `CompletableFuture` and `Mono`; an adapter is needed for integration |
| **Managed PostgreSQL** across all three clouds | JDBC / Spring Data JPA | R2DBC with a supported driver if reactive is needed | Cloud hosting does not turn JDBC into non-blocking automatically |

In Spring Cloud Azure, several async SDKs **already use Reactor** in their client APIs. In Spring Cloud AWS, many async SDKs use **`CompletableFuture`**. In Google Cloud Java libraries, `ApiFuture` and callback-based APIs are also common. Consequently, choosing reactive at the **Spring layer** does not guarantee all cloud-specific adapters behave identically regarding cancellation, demand, streaming, or retries.

When deploying the same business logic across multiple clouds, define a stable contract (for example `CompletionStage<StorageResult>` or `Mono<StorageResult>`) at the application boundary; inside each **provider adapter**, translate SDK results to that contract and explicitly document provider-specific capabilities that must be preserved. Do not force a blocking SDK API into a `Mono` and declare the system end-to-end non-blocking.

## 9. Which Model Fits Each Scenario?

| Scenario | First Option to Evaluate | Rationale / Limits |
| --- | --- | --- |
| Spring MVC REST API, moderate load, single small save | Sync SDK with explicit timeouts | Readable code, low coordination overhead; monitor waiting threads and connections |
| HTTP endpoint with many independent I/O calls, high concurrency | Async SDK or WebFlux + async SDK | Avoids holding request threads during I/O; must bound concurrent in-flight requests |
| WebFlux streaming data reads/writes | Reactive/async driver supporting true streaming | Avoids buffering full payloads; verify demand across every boundary |
| Predominantly Spring Data JPA / JDBC | Blocking model or isolated blocking execution | Changing a controller to return `Mono` does not make JDBC transactions reactive |
| Database queried reactively with suitable R2DBC driver | Spring Data R2DBC / Reactive Streams | Verify driver transaction and SQL support; do not mechanically replace all of JPA |
| Queue worker with custom ack/retry | Listener + appropriate SDK/template API | Choose concurrency, idempotency, and ack semantics per provider |
| Very large uploads | SDK streaming/multipart/resumable upload | Async does not equal streaming; bound memory and test chunk retries |
| Secrets read at startup or rarely changing | Config integration or cached sync client | Simplicity may outweigh async; review TTL/rotation |
| Fetching tokens/secrets repeatedly across requests | Credential/secret client with caching and refresh | Keep least privilege; avoid redundant network calls or logging secrets |

A sound decision weighs **latency, throughput, concurrency, footprint, streaming, transactions, and operational experience**, while verifying actual SDK capabilities. No model is universally faster: callbacks and publishers add overhead, and bottlenecks may lie in cloud quotas, bandwidth, queries, or serialization.

## 10. Errors, Timeouts, Retries, and Cancellation

### 10.1. How Do Errors Propagate?

| API Style | Error Reporting Mechanism | Where to Handle |
| --- | --- | --- |
| **Sync** | Exception thrown from call | `try/catch`, exception handlers, adapter boundary |
| **Async future** | Future completes exceptionally | `exceptionally`, `handle`, `whenComplete`, completion chains |
| **Reactive** | `onError` signal | `onErrorMap`, `onErrorResume`, `retryWhen`, WebFlux handlers |

With `CompletableFuture`, errors may arrive wrapped in `CompletionException`; adapter code must preserve the **root cause** to classify provider errors accurately. With Reactor, only turn an error into an “empty success” response when business rules truly permit it; unconditional `onErrorResume` can mask cloud outages.

### 10.2. Timeouts Need a Shared Budget

A request may be subject to multiple limits: inbound HTTP timeout, SDK API timeout, socket/connect timeout, token acquisition timeout, `CompletableFuture.orTimeout`, Reactor `timeout`, and gateway deadlines. These timeouts **do not automatically synchronize with one another**.

If a gateway stops waiting after 5 seconds while the SDK keeps retrying cloud calls for 30 seconds, the system produces wasted I/O and extra resource pressure. Design an **overall deadline**, configure sensible connect/read/API timeouts, bound retry counts, and instrument telemetry at every layer.

### 10.3. Retries Can Execute Operations Multiple Times

For example, `Mono.defer(() -> Mono.fromFuture(storage.put(...)))` can be **resubscribed** by `retryWhen`; each attempt issues a fresh SDK call. Retries are only safe if the operation tolerates repetition or uses an **idempotency key**, write precondition, or proper deduplication mechanism. A timed-out request **may already have succeeded on the cloud**, so never blindly retry with a newly generated object key.

Combining retries from the SDK, Spring Retry, Reactor, and a message broker without coordination can multiply total attempts severalfold. Only retry transient errors according to error details and provider guidance, using backoff, jitter, deadlines, and concurrency limits. A `403` from missing permissions generally requires fixing identity/IAM/RBAC rather than retrying.

### 10.4. Cancellation Is Not Rollback

When an HTTP client disconnects, a Reactor subscription may be cancelled. A future can also be cancelled. **There is no general guarantee that the underlying network operation stopped or that an object/message was reverted**. Cancelling a `Mono` only changes subscriber lifecycle; the cloud service may already have received the request.

For uploads or publishes, use traceable object keys/operation IDs, idempotency, and status checks when needed. Database transactions do not automatically roll back an object already written or a message already published to the cloud.

## 11. Messaging: Listeners, Consumers, and Reactive Are Three Different Things

A system receiving messages from SQS, Azure Service Bus, or Google Pub/Sub typically operates as follows:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as Queue / topic
    participant L as Listener / subscriber
    participant U as Business handler
    P->>Q: Publish message
    Q-->>P: Message acceptance result
    Q->>L: Deliver / poll message
    L->>U: Business processing
    alt Success
        U-->>L: Success
        L->>Q: Ack / delete / complete
    else Error or timeout
        U-->>L: Error
        Note over Q,L: May redeliver / dead-letter
    end
~~~

Running a listener under a framework/broker **event-driven** mechanism does not mean the handler itself is reactive. A handler may block, return a future, or return a publisher; the listener library must **genuinely wait for the right completion signal** before acking if the contract requires it. Acking before async work finishes risks losing messages from a business standpoint if downstream processing fails.

With many services, messages may be **redelivered at least once** in certain situations. Handlers therefore need idempotency, concurrency control, retry/DLQ handling, and ack-state observability. SQS visibility timeouts, Service Bus locks, and Pub/Sub ack deadlines each follow distinct rules; do not apply one timeout setting across all providers without verification.

## 12. Transactions and Context Propagation Across Thread Switches

### 12.1. Database Transactions

With Spring Data JPA/JDBC, traditional `@Transactional` binds to the executing thread's transaction context. If you return a future and run a database write inside a callback after the method returns, **never assume** the original transaction remains active on the callback thread.

In pipelines using true reactive drivers and transaction managers (such as an appropriate Spring Data R2DBC setup), you can use **reactive transactions**/`TransactionalOperator` per Spring's contract. Reactive transaction contexts are not automatically equivalent to blocking JDBC transactions.

Whether sync, future, or reactive, database transactions **do not automatically cover** S3, Azure Blob, Google Cloud Storage, SQS, Service Bus, or Pub/Sub. When updating a database and emitting an event together, a **transactional outbox** helps store business state and the event in the same database transaction and publish the event afterward.

### 12.2. Logging, Tracing, and Security Context

Code that switches threads or schedulers may lose **ThreadLocal** values used by MDC, tracing, or request/security contexts. Use the **context propagation** mechanisms supported by Spring/Micrometer/Reactor and the exact SDK version in use; never pass sensitive identifiers into logs or rely on a `ThreadLocal` implicitly surviving onto callback threads.

Track **operation ID, request ID, API name, provider, duration, errors, retry count, and in-flight request count**. For async/reactive code, measure both **time waiting to complete** and **active execution time**, rather than only timing how fast a method returns a future or publisher.

## 13. Testing Each Model

| Testing Level | What to Prove | Suggestions |
| --- | --- | --- |
| **Sync** unit test | Service calls the right port, handles exceptions | Fake/mock storage, `assertThrows`, no cloud needed |
| **Future** unit test | Pending/completed/exceptional futures compose properly; no `join()` | Test-controlled `CompletableFuture` |
| **Reactive** unit test | No I/O before subscribe; completion and errors emit properly | Reactor `StepVerifier`, mocked async port |
| **Spring context test** | Correct sync/async client beans, injection wiring | `ApplicationContextRunner`, context tests |
| **Integration test** | SDK actually sends payloads and receives responses; timeouts/retries/permissions | Emulator or isolated cloud test environment |
| **Load test** | Event loop never blocked, memory/concurrency bounded | Measure latency, threads, pools, pending requests, quotas |

Example unit test verifying the service in section 6 is **truly lazy** and completes through the port:

~~~java
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.same;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveDocumentServiceTest {
    @Test
    void startsOnSubscriptionAndReturnsObjectKey() {
        AsyncDocumentStorage storage = mock(AsyncDocumentStorage.class);
        byte[] bytes = {1, 2, 3};
        when(storage.put(anyString(), same(bytes)))
            .thenReturn(CompletableFuture.completedFuture(null));

        ReactiveDocumentService service =
            new ReactiveDocumentService(storage);
        Mono<String> result = service.save(bytes);

        verifyNoInteractions(storage);

        StepVerifier.create(result)
            .expectNextMatches(key -> key.startsWith("documents/"))
            .verifyComplete();

        verify(storage).put(anyString(), same(bytes));
    }
}
~~~

This test verifies the **service** does not call the cloud adapter when only constructing the publisher, and invokes it upon subscription. It does not prove non-blocking networking, since the port is mocked. Add tests for failed futures, cancellation/timeouts, retrying with the same operation ID, and observability with the real SDK in a test environment.

A worthwhile integration test must verify **identity, IAM/RBAC, networking, endpoint/project/region, the selected client bean, and cloud behavior**. LocalStack, Azurite, or other emulators are helpful but do not fully simulate real cloud identity/permission, quota, reliability, or streaming behavior. Test resources should use least-privilege permissions and cleanup.

## 14. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `join()`, `get()`, or `block()` on the WebFlux event loop | Blocks the event loop, increases latency across many requests | Return the publisher/future to the framework, or isolate blocking work onto an appropriate scheduler |
| Using `Mono.just(blockingCall())` | Blocking call runs immediately when building the publisher | Use `Mono.fromCallable` with `boundedElastic` if no async API exists |
| Creating a future before `Mono.fromFuture` when laziness is desired | SDK starts before subscription | Use `Mono.defer` or a corresponding lazy factory API |
| Using `AsyncRequestBody.fromBytes` for very large files | Buffers the entire payload on the heap | Use SDK-supported streaming/multipart/resumable uploads |
| Spawning thousands of unbounded futures | Exhausts connection pools, quotas, memory | Bound concurrency, queues, and backpressure at boundaries |
| Wrapping any SDK in `Flux` and assuming it is reactive | Blocking SDK still blocks threads | Classify clients and transports accurately, verify end-to-end |
| Retrying a side-effecting publisher that changes keys per attempt | Can create duplicate objects or business records | Use idempotency keys, preconditions, and explicit retry design |
| Acking a message before its future/Mono finishes | Business message loss when callback fails | Listener must wait for the result per contract before acking |
| Relying on JDBC `@Transactional` across callbacks | Transaction may close before the callback executes | Choose proper transaction boundaries; use outbox for cloud side effects |
| Timing only how fast `saveAsync()` returns | Reports artificially low latency even when cloud is slow | Measure from I/O start through completion/ack, including retries |

## 15. Practice Exercises

**Exercise 1 — Choosing a model.** A Spring MVC REST API saves 100 KB images to S3 at under 20 requests/second. The team considers rewriting it to WebFlux solely for speed. List the metrics to measure first, the pros/cons of sync vs. async, and why switching frameworks might not raise throughput.

**Exercise 2 — Fixing a blocking flow.** A WebFlux controller calls `Mono.just(s3Client.putObject(...))`. Explain the exact moment the SDK is invoked and propose two fixes: using `S3AsyncClient` with `Mono.defer`, or isolating the blocking SDK with `Mono.fromCallable(...).subscribeOn(boundedElastic())`.

**Exercise 3 — Retry hazard.** A `Mono.defer` generates a new UUID and writes an object; `retryWhen` retries after a timeout. The cloud may already have succeeded before the response was lost. Design a stable object key derived from an operation ID and describe a status-verification mechanism when the outcome is uncertain.

**Exercise 4 — Comparing three providers.** For an application that writes large objects and emits events, sketch adapters for AWS S3/SQS, Azure Blob/Service Bus, and Google Cloud Storage/Pub/Sub. Specify the sync/async client, return signal type, payload streaming approach, message ack behavior, and workload permissions.

**Exercise 5 — Testing completion.** Write a fake `AsyncDocumentStorage` returning an incomplete future. Build the `Mono` from the service, verify the port is not called before subscription, complete the future successfully and verify the output; repeat with an exceptional future and cancellation.

**Exercise 6 — Transactions.** A service uses JPA `@Transactional` to save an order and then calls an async Pub/Sub Publisher. Identify the failure windows if publish succeeds but the database rolls back, or if the database commits and publish fails; then describe how a transactional outbox reduces that risk.

## 16. Key Takeaways

- **Sync SDK:** results or exceptions appear directly; the calling thread typically waits during I/O. **Async SDK:** returns a future/callback with completion later. **Reactive:** a model of signals, subscriptions, and demand; requires non-blocking underlying sources for true non-blocking efficiency.
- `Mono.fromFuture(future)` does not make an already-running future lazy; use `Mono.defer` when cloud calls must start strictly on subscription.
- **Never block the WebFlux event loop** with `join()`, `get()`, `block()`, or blocking SDKs. `boundedElastic` is a bounded isolation workaround for blocking calls; it does not make blocking I/O genuinely async.
- **Futures, reactive pipelines, and streaming are three separate concerns**. A `byte[]` request body can still consume excessive memory even if the SDK returns a future or the service returns a `Mono`.
- AWS, Azure, and Google Cloud differ in SDKs, reactive support, messaging acks, quotas, and permissions. Select clients by **service and version**, then run real load tests and verify identity, networking, retries, and cancellation.
- A cancelled or timed-out request **does not mean the cloud rolled back**. Idempotency, budgeted retries, observability, and explicit transaction boundaries are mandatory for reliable operation.
