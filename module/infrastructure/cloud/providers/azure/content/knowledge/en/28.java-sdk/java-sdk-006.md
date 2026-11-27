# Pagination, Long-Running Operations, and Client Resource Management

A Java application on **Azure Container Apps** needs to list more than two million blobs in Azure Storage, update Azure resources via the management SDK, and run provisioning jobs that take several minutes. A prototype works fine with a few dozen objects, yet in production three problems emerge: **loading the entire result set into RAM**, **HTTP requests waiting too long for cloud operations to finish**, and **creating a new Azure SDK client on every request**, driving up connection churn, authentication overhead, and latency. These are three distinct issues, yet they frequently appear together in applications using the Azure SDK for Java.

This lesson explains how to use **pagination** to read large result sets page by page, handle **long-running operations (LROs)** via polling rather than confusing an accepted response with completion, and **manage client, HTTP transport, and credential lifecycles** to avoid resource exhaustion. The goal is designing Java programs that are both functionally correct and tuned for throughput, latency, security, and cost on Azure.

This content belongs to the **Azure SDK for Java** chapter in the **CLOUD_PROVIDERS_AZURE** module: progressing from Azure subscriptions, resource groups, and Microsoft Entra ID through virtual networking, compute, storage, and data; deploying, monitoring, securing, and controlling system costs. Examples use the modern Azure SDK for Java (`com.azure.*` packages), Azure Blob Storage, and polling patterns used across service and management SDKs. Note that **not every Azure service client shares the same paging/LRO APIs or resource-closing requirements**.

> **Versions and Compatibility:** The Azure SDK for Java, Maven BOM, `PagedIterable`/`PagedFlux` overloads, status classes, HTTP providers, and long-running operation pollers can change across libraries and versions. Blob Storage code serves as a concrete example for one SDK; the LRO pattern uses a **hypothetical method** `beginOperation(...)` to illustrate general logic rather than a method present on every Azure service. Before deploying to production, check the API reference and capabilities of the pinned library version in your project. Listing or mutating resources may incur charges.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **large collections**, **pages**, **page size**, **continuation tokens**, **offsets**, and **cursors**.
2. Use **`PagedIterable<T>`** in the Azure SDK for Java to iterate synchronously item by item or page by page.
3. Use **`PagedFlux<T>`** for asynchronous processing with Reactor, enforcing concurrency limits and backpressure.
4. Design safe resume/checkpoint flows when enumerating millions of objects, avoiding skipped items or duplicate processing on retries.
5. Identify operations returning incomplete states, distinguishing HTTP **202 Accepted** from final completion.
6. Apply **`SyncPoller<P,T>`** and **`PollerFlux<P,T>`** concepts, understanding status, final results, timeouts, and cancellation limits.
7. Design idempotency and operation tracking for Java APIs that start an Azure LRO.
8. Know when Azure clients should be reused and when to dispose of **resources the application actually owns**.
9. Configure identity/RBAC, HTTP transports, retries/timeouts, and observability safely.
10. Choose appropriate designs for web, batch, multi-tenant, or Azure management workloads.

## 2. Three Problems and Three Solutions

| Problem | Symptom | Primary Mechanism |
|---|---|---|
| Result list too large | Rising RAM, slow APIs, listing timeouts | **Pagination + streaming/checkpoints** |
| Azure operation takes too long | HTTP 202, status still `InProgress`, requests wait minutes | **Long-running operations + polling/status tracking** |
| Clients recreated continuously | Connection churn, token fetching, thread/pool pressure | **Client reuse + lifecycle ownership** |

These are related yet non-interchangeable. An API may use a singleton client to iterate pages while starting an LRO for each discovered item. **Pagination does not guarantee LRO completion**, and **polling does not fix connection leaks**.

~~~mermaid
flowchart LR
  APP["Java application"] --> CLIENT["Reusable Azure SDK client"]
  CLIENT --> LIST["Paged listing"]
  LIST --> PAGE["Items in bounded pages"]
  PAGE --> WORK["Idempotent task workers"]
  WORK --> LRO["Start LRO"]
  LRO --> POLL["Poll status / final result"]
  POLL --> STORE["Checkpoint + observability"]
  CLIENT -.-> RES["Shared HTTP pipeline / credential / connection pool"]
~~~

## 3. Azure SDK for Java Architecture: Client, Pipeline, Transport

Common concepts:

- **Service client:** `BlobServiceClient`, `BlobContainerClient`, `BlobContainerAsyncClient`, or other service clients providing business operations.
- **Builder:** `BlobServiceClientBuilder` configures endpoint, credential, client options, and constructs the client.
- **HTTP pipeline:** chain of policies such as authentication, retry, diagnostics, and transport.
- **HTTP transport:** implementation executing HTTP requests, connections/TLS/connection pooling.
- **TokenCredential:** e.g., `DefaultAzureCredential`; acquires tokens via Microsoft Entra ID.
- **PagedIterable/PagedFlux:** abstractions for multi-page listings.
- **SyncPoller/PollerFlux:** abstractions for long-running operations on supporting clients.

Azure SDK clients are generally designed to be **thread-safe and reusable**. A single client serves many operations and threads; there is no need to create a new client after every `listBlobs()` call or per incoming HTTP request.

However, verify **which resources are owned by the client vs. the application**. Not every Azure SDK client implements `AutoCloseable` or exposes `close()`. Avoid calling `client.close()` out of habit when the client type does not support it.

## 4. What Is Pagination?

A cloud service may store millions of objects. Rather than returning everything in one HTTP response, the service returns a **page** along with an optional **continuation token** to query the next page.

~~~text
Request: list(prefix="invoices/", maxPageSize=100)
Response page 1:
  100 items
  continuation = "opaque-token-1"

Request: list(prefix="invoices/", token="opaque-token-1")
Response page 2:
  100 items
  continuation = "opaque-token-2"

...
Response page N:
  37 items
  continuation = null (completed)
~~~

**Page size** is a desired size, usually a **hint/cap enforced by the service** rather than a guarantee that every page contains exactly N items. A page can even be empty while still carrying a continuation token on some services, so never conclude enumeration ended solely because `items.size() == 0`.

### Offsets Differ from Continuation Tokens

- **Offset pagination:** asks to "skip 10,000 rows, take the next 100." Becomes costly at large offsets and drifts when datasets mutate.
- **Continuation token/cursor:** an opaque value issued by the service to resume from a valid position per service semantics.
- **Snapshot pagination:** the result set is frozen at a point in time; **not guaranteed by default** on all Azure listing APIs.

In the Azure SDK, never assume a token is a page number, last blob name, or an ID you can increment manually.

## 5. Continuation Tokens Must Be Treated as Opaque

A continuation token:

1. Is generated by the service with no format contract the app may rely on.
2. May encode server-side pagination state and filters.
3. May expire, be rejected, or become invalid across schema/API/version changes depending on the service.
4. May be bound to the same resource, query, prefix, region, and request options.
5. Should be protected as **potentially sensitive application state** and never logged publicly.
6. Must never substitute for authentication or authorization.
7. When resuming, must reuse the **same listing scope and request options** if required by the service.

### Checkpoint Example

~~~json
{
  "jobId": "blob-audit-20261120",
  "account": "storage-lab",
  "container": "invoices",
  "prefix": "2026/11/",
  "continuationToken": "<OPAQUE_TOKEN>",
  "processedItems": 7400,
  "schemaVersion": 1,
  "status": "RUNNING"
}
~~~

Never print real tokens to public logs or telemetry. If checkpoints live in a database, restrict read/write permissions and update atomically by **job ID/generation** so two workers never overwrite each other's state.

## 6. Maven: Managing Dependencies with the Azure SDK BOM

With Maven, use a BOM to keep Azure SDK versions aligned per project recommendations:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-sdk-bom</artifactId>
      <version>${azure.sdk.bom.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-blob</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
  </dependency>
</dependencies>
~~~

This is a **POM snippet**. Define `azure.sdk.bom.version` in your project or substitute an organization-approved BOM version; never use uncontrolled "latest" versions. When combining with Spring Boot or other framework BOMs, check dependency resolution for conflicts.

### Key Packages to Recognize

| Package/Class | Role |
|---|---|
| `com.azure.storage.blob.*` | Azure Blob Storage clients |
| `com.azure.storage.blob.models.*` | `BlobItem`, `ListBlobsOptions` |
| `com.azure.core.http.rest.PagedIterable` | Synchronous pagination |
| `com.azure.core.http.rest.PagedFlux` | Asynchronous pagination |
| `com.azure.core.http.rest.PagedResponse` | Page, values, continuation token |
| `com.azure.core.util.polling.SyncPoller` | Synchronous LRO polling |
| `com.azure.core.util.polling.PollerFlux` | Reactive LRO polling |
| `com.azure.identity.DefaultAzureCredentialBuilder` | `TokenCredential` for Azure |

Exact overload names depend on the SDK package and version. Verify imports and API references before compiling snippets.

## 7. Creating and Reusing the Azure Blob Client

Java 17 example using Microsoft Entra authentication:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import com.azure.storage.blob.BlobContainerClient;

public final class BlobClients {
    private final TokenCredential credential;
    private final BlobServiceClient serviceClient;

    public BlobClients(String endpoint) {
        this.credential = new DefaultAzureCredentialBuilder().build();
        this.serviceClient = new BlobServiceClientBuilder()
            .endpoint(endpoint)
            .credential(credential)
            .buildClient();
    }

    public BlobContainerClient container(String name) {
        return serviceClient.getBlobContainerClient(name);
    }
}
~~~

The application constructs `BlobClients` **once at startup** (or as a DI singleton) and reuses it. The endpoint looks like `https://<account>.blob.core.windows.net` with no account key. Never instantiate `DefaultAzureCredential` or `BlobServiceClient` inside each loop over blobs.

### Permissions Needed to List

The identity needs the corresponding data-plane permission—such as **Storage Blob Data Reader** at the right scope—and the storage account firewall or private network must allow the path. Resource Group `Contributor` **does not automatically** grant blob read access.

Locally, `DefaultAzureCredential` can use a developer login; on Azure Container Apps, AKS, or VMs, it needs managed identity or workload identity configured properly. Never log access tokens or connection strings.

## 8. PagedIterable: Iterating Items Synchronously

Azure Blob Storage returns `PagedIterable<BlobItem>` when listing blobs.

~~~java
import com.azure.core.http.rest.PagedIterable;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;

import java.time.Duration;

public final class BlobListing {
    public static long count(BlobContainerClient container) {
        ListBlobsOptions options = new ListBlobsOptions()
            .setPrefix("invoices/");

        PagedIterable<BlobItem> blobs =
            container.listBlobs(options, Duration.ofSeconds(30));

        long count = 0;
        for (BlobItem blob : blobs) {
            // Each iteration step may trigger a network call when a new page is needed.
            if (blob.getName() != null) {
                count++;
            }
        }
        return count;
    }
}
~~~

### Not All Data Is Loaded Up Front

`PagedIterable` looks like a standard Java `Iterable`, yet pages are fetched **lazily / on demand**. When iteration reaches the end of the current page, the SDK sends the next HTTP request. Therefore:

- Constructing the `PagedIterable` object does not fetch everything immediately.
- A `for` loop across millions of items can run for a long time and issue many API calls.
- The iterator can throw an exception mid-loop if fetching a subsequent page fails.
- Passing a `timeout` to the list API does not guarantee the **entire loop** finishes within 30 seconds; check the exact overload's timeout semantics.
- Never run a massive listing inside a short-timeout HTTP request handler.

### Danger of Materializing Lists

~~~java
// Illustrative anti-pattern:
List<BlobItem> all = new ArrayList<>();
for (BlobItem item : container.listBlobs()) {
    all.add(item); // Can hold millions of objects in RAM.
}
~~~

With streaming, **process each item or page and release references**, retaining only minimal state. If full aggregation is truly needed, use external storage or a database rather than the JVM heap.

## 9. Iterating by Page and Bounding Batches

`PagedIterable` exposes individual pages. A practical pattern:

~~~java
import com.azure.core.http.rest.PagedIterable;
import com.azure.core.http.rest.PagedResponse;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;

import java.time.Duration;

public final class PageProcessing {
    public static void scan(BlobContainerClient container) {
        PagedIterable<BlobItem> listing = container.listBlobs(
            new ListBlobsOptions().setPrefix("invoices/"),
            Duration.ofSeconds(30)
        );

        for (PagedResponse<BlobItem> page : listing.iterableByPage(200)) {
            for (BlobItem item : page.getValue()) {
                processOne(item);
            }
            String nextToken = page.getContinuationToken();
            System.out.println("Page complete; hasNext="
                + (nextToken != null));
        }
    }

    private static void processOne(BlobItem item) {
        // Read required metadata or enqueue a job with an idempotency key.
        System.out.println(item.getName());
    }
}
~~~

`iterableByPage(200)` sets a **preferred page size**; the service may return fewer items. When iterating pages, never assume `page.getValue()` always has 200 items or that page numbers start at 1.

### Why Process by Page?

- Enables checkpointing after each completed page.
- Simplifies batch metrics, memory bounds, and downstream concurrency control.
- Cuts database overhead compared to committing every single item individually.
- Makes resuming after a worker crash straightforward.
- Allows per-page transactional commits if downstream storage supports them.

**Never checkpoint too early.** If you save the next page's token after processing only 80 of 200 items, a crash will **skip the remaining 120 items**.

## 10. Resuming a Listing from a Continuation Token

When a long job runs for hours, an Azure VM may reboot or a Container Apps replica may restart. You should not restart from scratch if the service supports resuming.

Pattern:

~~~java
import com.azure.core.http.rest.PagedIterable;
import com.azure.core.http.rest.PagedResponse;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;

import java.time.Duration;

public final class ResumeBlobScan {
    public static void run(
            BlobContainerClient container,
            String savedNextPageToken) {

        PagedIterable<BlobItem> listing = container.listBlobs(
            new ListBlobsOptions().setPrefix("2026/11/"),
            Duration.ofSeconds(30)
        );

        for (PagedResponse<BlobItem> page :
                listing.iterableByPage(savedNextPageToken, 200)) {

            for (BlobItem item : page.getValue()) {
                processIdempotently(item);
            }

            // In practice: commit checkpoint atomically after processing the page.
            persistCheckpoint(page.getContinuationToken());
        }
    }

    private static void processIdempotently(BlobItem item) {
        // Example: upsert (account, container, name, etag)
        // into a table with a unique key/idempotency key.
    }

    private static void persistCheckpoint(String token) {
        // Persist to a durable store with scope/prefix/job generation.
        // token == null means listing finished at the time reported by the service.
    }
}
~~~

This is an **illustrative skeleton**: `persistCheckpoint` and `processIdempotently` omit storage implementation. Verify the `iterableByPage(token, size)` overload on your exact `azure-core` version.

### Checkpointing Properly

- Store the token representing the **next page**, never before the current page finishes processing.
- Write the checkpoint **after** downstream commits succeed.
- If items within a page run in parallel, wait for **all** items in the page to succeed before committing.
- If any item fails, apply retries or quarantine before marking the page done.
- Use unique keys/upserts so **replays produce no duplicate side effects**.
- Persist the prefix/filter and account/container alongside the token.
- When a token expires or becomes invalid, have a runbook to restart from an earlier checkpoint or re-scan with deduplication.

### Is Exactly-Once Guaranteed?

No. If downstream commits succeed yet the worker crashes **before** saving the checkpoint, the page will be replayed. If the checkpoint commits before downstream, items can be lost. Because there is no automatic distributed transaction spanning Azure Blob listing and a downstream database, systems typically rely on **at-least-once delivery + idempotency**.

## 11. Listing While Data Is Changing

During a listing scan, blobs may be created, deleted, or have metadata updated. Many listing APIs **do not guarantee a consistent point-in-time snapshot** across pages. Consequences include:

- Newly created objects may or may not appear in the active run.
- Deleted objects may vanish before your worker reads them.
- Metadata/ETags may change between listing and reading.
- Re-running with the same prefix can yield different item sets.

### Business-Aligned Solutions

1. **Approximate inventory audit:** accept eventual consistency and run periodically.
2. **Snapshots / immutable inputs:** use manifests or versioned datasets when reproducibility is required.
3. **Change feeds / events:** track continuous mutations where supported by the service/architecture.
4. **ETag/version-aware processing:** record exactly which version of an object was processed.
5. **Watermarks + dedup:** combine periodic scans with reliable change timestamps.
6. **Stable partitioning:** split work by container/prefix/date to avoid unbounded single runs.

`ContinuationToken` simply **resumes pagination per service semantics**—it does not turn listing into a transactional snapshot.

## 12. PagedFlux: Asynchronous Pagination

The Azure SDK for Java provides both **sync** and **async** clients. Async listing returns `PagedFlux<BlobItem>`, integrated with **Project Reactor**.

~~~java
import com.azure.core.http.rest.PagedFlux;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;

import reactor.core.publisher.Mono;

public final class AsyncBlobListing {
    public static Mono<Long> count(
            BlobContainerAsyncClient container) {

        PagedFlux<BlobItem> blobs = container.listBlobs(
            new ListBlobsOptions().setPrefix("invoices/")
        );

        return blobs
            .filter(item -> item.getName() != null)
            .count();
    }
}
~~~

`count()` returns a `Mono<Long>`, executing only **upon subscription**. Across millions of items, the pipeline avoids holding all items simultaneously in memory, yet it **still traverses every page** and holds request/response resources per Reactor/SDK behavior.

### Never Use Unbounded `collectList()`

~~~java
// Anti-pattern: collectList() gathers all items into one list in RAM.
// Mono<List<BlobItem>> all = container.listBlobs().collectList();
~~~

Instead, stream with `doOnNext`/`concatMap`/`flatMap` using bounded concurrency, or iterate page by page with checkpoints.

## 13. Reactive Page Processing, Concurrency, and Backpressure

Processing page by page enables async execution without flooding downstream services.

~~~java
import com.azure.core.http.rest.PagedFlux;
import com.azure.core.http.rest.PagedResponse;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class AsyncPageWorkflow {

    // Implement processAsync and checkpointAsync before use.
    public static Mono<Void> scan(BlobContainerAsyncClient container) {
        PagedFlux<BlobItem> pages = container.listBlobs(
            new ListBlobsOptions().setPrefix("invoices/")
        );

        return pages.byPage(200)
            .concatMap(page ->
                Flux.fromIterable(page.getValue())
                    .flatMap(AsyncPageWorkflow::processAsync, 8)
                    .then(checkpointAsync(page.getContinuationToken()))
            )
            .then();
    }

    private static Mono<Void> processAsync(BlobItem item) {
        // Production: async upsert with a unique idempotency key.
        return Mono.empty();
    }

    private static Mono<Void> checkpointAsync(String nextToken) {
        // Production: async durable write; token == null => completed.
        return Mono.empty();
    }
}
~~~

**Analysis:**

- `byPage(200)` processes page responses without collecting an entire container into one massive list.
- `concatMap` enforces sequential ordering **across pages**, enabling safe per-page checkpointing.
- `flatMap(..., 8)` runs up to roughly 8 concurrent item operations **within each page** per Reactor semantics.
- `then(checkpointAsync(...))` runs only after item publishers succeed; unhandled errors prevent advancing the checkpoint.
- `processAsync`/`checkpointAsync` **are intentional placeholders** providing no DB persistence yet.
- `Mono.empty()` simulates success here and must be replaced with real implementations before deployment.

### What Is Backpressure?

A subscriber requests only as much data as it can handle, preventing local floods. However, **backpressure alone does not prevent request queues, cap global concurrency across tasks, or eliminate HTTP 429s**. Beyond Reactor demand, bound:

- Concurrent page scans per job.
- Active jobs per pod.
- Downstream DB and Storage request concurrency.
- Rate limits per account or tenant.
- Concurrent active LROs.

### Never Block on the Reactive Event Loop

Avoid calling blocking JDBC or `Thread.sleep()` inside `flatMap` on event-loop threads. If blocking APIs are unavoidable, offload them onto a bounded scheduler (`Schedulers.boundedElastic()`) within a concurrency budget, or adopt truly async clients/drivers.

## 14. Partial Enumeration and Canceling Listing

An application does not always need the full list. For example, a UI might show only the first 20 objects:

~~~java
Mono<java.util.List<BlobItem>> firstTwenty =
    containerAsync.listBlobs().take(20).collectList();
~~~

`take(20)` **cancels the upstream subscription** once 20 items arrive per Reactor behavior, though the service may still have returned more than 20 items or prefetched a page depending on pagination granularity and SDK implementation.

For HTTP APIs, never return two million items in one response; return **one page + an opaque next-page cursor** with a maximum page size cap. If exposing cursors to external clients, validate scope, sign/encrypt per security policy, and prevent users from replaying another tenant's cursor.

### Resume Tokens in REST APIs

Never expose raw Azure continuation tokens as if they were "access credentials." Example REST wrapper:

~~~json
{
  "items": [
    {"name": "2026/11/invoice-001.json"},
    {"name": "2026/11/invoice-002.json"}
  ],
  "nextCursor": "<OPAQUE_APPLICATION_CURSOR>",
  "count": 2
}
~~~

An application cursor should bind tenant, resource, prefix, page size, or a server-side checkpoint reference per policy; upon decoding/lookup, always verify the user's authorization before reading. Never trust a client-supplied prefix alongside a cursor.

## 15. Retrying When a Page Fails

Paged listing issues multiple HTTP requests, so page 42 may encounter:

- `429 Too Many Requests` (throttling).
- `503 Service Unavailable` or transient network timeouts.
- `401/403` due to token, identity, role, or network changes.
- `404` if the container or resource was deleted.
- Invalid continuation tokens or service-side query mismatches.
- Connection pool exhaustion or proxy/TLS errors.

**Do not retry all errors identically.**

### Retry Policy

The Azure SDK typically provides retry policies for transient errors per implementation and configuration. Know:

- Does it retry automatically? For which errors and how many times?
- Does it honor `Retry-After` / server delays?
- Is the operation **idempotent**?
- What are the per-request deadline and total job timeout?
- Do SDK retries and business worker retries **multiply**?

For instance: SDK retries 3 times, worker retries 5 times, and queue redelivers 4 times → one transient blip multiplies attempts dramatically. Combine **bounded exponential backoff + jitter + retry budgets** and measure actual retry counts.

### Error Classification

| HTTP/Status | Action |
|---|---|
| 429 | Honor retry hints, reduce concurrency/rate, inspect service quotas |
| 503 / transient 5xx | Retry within budget, monitor availability |
| 401 | Inspect credential/token and authentication; never loop infinitely |
| 403 | Check RBAC, data-plane ACLs, and network firewalls; misconfigurations rarely self-heal |
| 404 | Determine whether resource was deleted or tenant/scope is wrong |
| Invalid cursor | Verify checkpoint and query scope; restart safely if needed |
| Timeout | Unknown whether server committed; enforce idempotency |

## 16. What Is a Long-Running Operation (LRO)?

Many Azure management and data-plane operations take seconds to minutes: creating/updating/deleting resources, starting copies/restores, provisioning compute/networking, or background job processing. The server **accepts** the request and processes it asynchronously.

~~~mermaid
sequenceDiagram
  participant A as Java client
  participant S as Azure service
  A->>S: Begin operation
  S-->>A: 202 Accepted + operation/status URL
  loop Poll per Retry-After/backoff
    A->>S: GET status URL
    S-->>A: Running / InProgress
  end
  A->>S: GET status URL
  S-->>A: Succeeded / Failed / Canceled
  A->>S: GET final resource/result if required by API
  S-->>A: Final result or terminal metadata
~~~

**Note:** this is a common Azure REST pattern, **not an identical fixed contract across every service**. Some LROs start with HTTP 200/201 or 202 and return `Azure-AsyncOperation`, `Operation-Location`, `Location`, or service-specific status URLs. The SDK hides many of these protocol details behind poller abstractions.

### HTTP 202 Does Not Mean Job Succeeded

`202 Accepted` means the service **accepted the request for processing**, not that the resource is ready. If a Java API receives 202 and immediately returns "created," downstream calls against the provisioning resource will race and fail.

## 17. LRO States to Understand

An LRO typically transitions through:

~~~text
NOT_STARTED → IN_PROGRESS → SUCCESSFULLY_COMPLETED
                          ↘ FAILED
                          ↘ USER_CANCELLED (if supported by service)
~~~

Exact status names vary by service and poller: you may see `Accepted`, `Running`, `Succeeded`, `Failed`, `Canceled`, `Updating`, or custom states.

### Handling Rules

1. **In progress:** continue polling per interval/hint; do not read final result prematurely.
2. **Succeeded:** fetch final resource/result if required by the API and verify postconditions.
3. **Failed:** record error codes and correlation IDs; never mark business workflows successful.
4. **Canceled:** confirm actual server state, not just client-side cancellation.
5. **Client-side timeout:** **never assume the server operation failed or canceled automatically**.

### Do Not Equate an LRO with a Thread

An LRO runs inside the Azure service; a Java thread does not need to stay alive the whole time. Clients can persist operation references/statuses and check back later, provided the service supports resumption and status URLs/tokens remain valid.

## 18. SyncPoller<P, T>: Synchronous Pattern

The Azure Core SDK provides **`SyncPoller<P,T>`** for synchronous long-running operations. `P` is the **intermediate polling value** type, and `T` is the **final result** type; never assume both are the same type.

Structural pattern (the `beginSomeSupportedOperation` method is a **pseudocode adapter** representing a real service SDK, not a method on every client):

~~~java
import com.azure.core.util.polling.LongRunningOperationStatus;
import com.azure.core.util.polling.PollResponse;
import com.azure.core.util.polling.SyncPoller;

import java.time.Duration;

public final class LroWaiter {

    public static <P, T> T await(
            SyncPoller<P, T> poller,
            Duration maximumWait) {

        PollResponse<P> finalPoll =
            poller.waitForCompletion(maximumWait);

        if (!LongRunningOperationStatus.SUCCESSFULLY_COMPLETED
                .equals(finalPoll.getStatus())) {
            throw new IllegalStateException(
                "LRO did not complete successfully: "
                + finalPoll.getStatus()
            );
        }

        return poller.getFinalResult();
    }
}
~~~

This assumes your SDK version provides `waitForCompletion(Duration)`, `PollResponse.getStatus()`, and `getFinalResult()`. Some APIs/pollers differ in timeout or exception semantics; verify the API reference. If a poller throws on failure or timeout, handle exceptions around it rather than expecting a terminal `PollResponse` every time.

### Never Start the Operation Twice

~~~java
// Conceptual pseudocode:
SyncPoller<ProvisioningInfo, ResourceInfo> poller =
    serviceClient.beginSomeSupportedOperation(request);

// Poller is created from a single operation start.
ResourceInfo result = LroWaiter.await(
    poller, Duration.ofMinutes(15)
);
~~~

`beginSomeSupportedOperation`, `ProvisioningInfo`, and `ResourceInfo` **are placeholder names**. With Azure Resource Manager, SDKs may provide fluent create/update methods that wait for completion or `begin...` methods—never assume every resource manager client returns `SyncPoller`.

### PollResponse and Final Result

- `PollResponse<P>` holds status and intermediate metadata for that poll attempt.
- `getFinalResult()` retrieves the final result once the operation finishes per contract.
- Some LROs **have no final response body**: the final result may be `Void` or status metadata.
- Never treat an intermediate `response.getValue()` as the final resource state.

## 19. PollerFlux<P, T>: Asynchronous Pattern

With Reactor-based async SDKs, `PollerFlux<P,T>` handles LROs without blocking HTTP request threads.

~~~java
import com.azure.core.util.polling.PollerFlux;
import reactor.core.publisher.Mono;

import java.time.Duration;

public final class AsyncLroWaiter {

    public static <P, T> Mono<T> await(
            PollerFlux<P, T> poller) {

        return poller.getFinalResult()
            .timeout(Duration.ofMinutes(20));
    }
}
~~~

Here, the **specific client** must return a `PollerFlux<P,T>` from a supported `begin...` method. `getFinalResult()` emits the final result per the `PollerFlux` contract; verify exact behavior and subscription semantics for your version.

### Key Points

- Reactive publishers execute only **when subscribed**.
- Never call `block()` on Reactor event loops or WebFlux request handlers.
- Handle timeouts, service failures, and cancellations explicitly.
- Use `doOnNext`/`doOnError`/tracing for safe metadata logging—never log request secrets.
- Client-side `timeout(Duration)` **does not guarantee server-side cancellation**.
- Never re-subscribe repeatedly to a `begin` LRO publisher without knowing its side effects; persist the operation identity/reference.
- For multi-hour jobs, expose a **status endpoint + durable operation tracker** rather than holding an HTTP connection open.

### Async Does Not Mean Infinite Concurrency

A service receiving 5,000 concurrent LROs will hit throttling or quota limits. Enforce bounded concurrency, rate limits, queues, and retry policies for both **begin requests** and **poll requests**.

## 20. Poll Intervals, Retry-After, and Thundering Herds

Polling too frequently inflates HTTP costs, triggers 429s, and stresses the control plane. Polling too slowly leaves callers waiting long after the job finished.

### Strategy

1. Prefer the **polling interval/hint provided by the service and SDK**.
2. If polling manually, honor `Retry-After` headers when present.
3. Enforce min/max interval bounds plus **jitter** when many jobs wait concurrently.
4. Never use `while(true)` + `Thread.sleep(100)` across jobs.
5. Track poll counts, duration, 429s, and estimated completion time.
6. Enforce an overall SLO deadline with a background tracker on timeout.

Example:

~~~text
Job A created at 10:00:00
Poll hint: retry after 10 seconds
Poll 1 at 10:00:10 -> Running
Poll 2 at 10:00:20 -> Running
Poll 3 at 10:00:30 -> Succeeded
Fetch final resource and verify readiness
~~~

Do not parse every `Retry-After` identically: standard HTTP uses integer seconds or HTTP dates, while some Azure APIs use millisecond-specific headers. Azure SDK pollers handle these protocol details; avoid overriding them arbitrarily.

## 21. Request, LRO, and Job Timeouts Differ

There are at least three distinct deadlines:

| Timeout/Deadline | Example | Meaning |
|---|---|---|
| HTTP per-call | 20–30 seconds | Single request to service / fetch page / status poll |
| Polling wait deadline | 10–20 minutes | Client waiting for LRO terminal state |
| Business job deadline | Before 06:00 | End-to-end business workflow deadline |

### Critical Warnings

- An HTTP timeout on **begin** can happen **after the server already accepted the request**: retrying `begin` without idempotency creates duplicate operations.
- A timeout while polling **does not** mean the server operation failed.
- A 30-second API gateway timeout cannot hold a synchronous request for a 20-minute LRO.
- An LRO reporting `Succeeded` may still have unverified downstream postconditions (resource health, DNS propagation, etc.).
- SDK cancellation must distinguish **canceling a local subscription** from canceling the operation on the server.

### Recommended HTTP API Pattern

~~~text
POST /provisioning-jobs
  -> validate request
  -> create durable job record + idempotency key
  -> start one Azure operation
  -> return HTTP 202 with application jobId/status URL

GET /provisioning-jobs/{jobId}
  -> return local job state + Azure operation state
  -> optionally refresh state with rate limits

Background worker
  -> poll Azure LRO
  -> update terminal status and final resource ID
  -> notify business workflow
~~~

Never return `201 Created` and claim a resource is "ready for use" before the operation reaches terminal success and postconditions pass.

## 22. Resuming LROs and Persisting Durable State

An LRO can outlive a Java process. Persist:

~~~json
{
  "jobId": "provision-20261120-001",
  "operationType": "CreateOrUpdateResource",
  "resourceId": "/subscriptions/.../resourceGroups/.../providers/...",
  "idempotencyKey": "<APPROVED_REQUEST_ID>",
  "trackingReference": "<SERVICE_OPERATION_REFERENCE>",
  "status": "IN_PROGRESS",
  "attempt": 1,
  "createdAtUtc": "2026-11-20T10:00:00Z",
  "nextPollAfterUtc": "2026-11-20T10:00:10Z"
}
~~~

**Subtlety:** not every `SyncPoller/PollerFlux` supports exporting a **resume token** across processes to reconstruct the poller, or tokens may expire. In Azure REST/SDKs, some services offer operation IDs/status URLs and reattach hooks while others do not. Never claim a `getResumeToken()` method exists or works universally.

### Safe Strategy

1. If the SDK/service officially supports resume tokens, persist the designated reference/token.
2. Otherwise, persist the resource ID and reconcile via supported **GET status/resource** APIs after restarts.
3. If state is unknown after a timeout: **reconcile before retrying `begin`**.
4. Use idempotency keys and unique request records so only one worker owns `begin`.
5. Guard poll trackers with leases/locks and handle lease expiration/failover cleanly.
6. Have a fallback to resource-state inspection or manual review if a status URL expires.
7. Never store bearer tokens or access keys in tracking records.
8. Enforce TTL/retention on operation history to prevent unbounded DB/log growth.

### Is Cancel Rollback?

No. Even if a service supports server-side cancel and transitions to `Canceled`, **partially completed side effects can remain**. Build explicit compensation/cleanup logic—never assume stopping polling rolls back provisioning.

## 23. Idempotency and Retries When Managing Azure Resources

Azure VM management example:

1. Application calls begin create VM named `batch-worker-01`.
2. Client times out before receiving the response.
3. Server actually received the request and is creating the VM.
4. App retries `begin` without checking resource state.
5. Result: conflicts, duplicate side effects, or unintended configuration drift.

### Design

- Use **deterministic** resource names/IDs where possible.
- Assign each business request a durably persisted **idempotency key**.
- Before retrying `begin`, check operation/resource status per service contract.
- Use optimistic concurrency / ETag / `If-Match` where supported.
- Verify real outcomes after terminal state.
- Bound `begin` retries and poll retries separately.
- If a job times out while the server is still running, mark `IN_PROGRESS/UNKNOWN` rather than falsely reporting `FAILED`.
- Implement rollback/cleanup for partial resources.

**Never assume every Azure PUT is strictly idempotent in all cases** if request bodies, conditional headers, secrets, or server-side defaults differ across attempts. Check the resource provider's contract.

## 24. Client Lifecycle Management: How Long Should a Client Live?

Azure SDK clients are generally designed for long-lived reuse. Compare:

~~~java
// Anti-pattern: create credential + client per request.
public void listOnce(String endpoint) {
    var credential = new DefaultAzureCredentialBuilder().build();
    var client = new BlobServiceClientBuilder()
        .endpoint(endpoint)
        .credential(credential)
        .buildClient();
    client.getBlobContainerClient("invoices").listBlobs()
        .iterator().hasNext();
}
~~~

Consequences include:

- Excessive object and pipeline allocations.
- Repeated token discovery and authentication overhead.
- Fragmented connection pools and threads when creating separate transports.
- Higher cold-start latency.
- Harder to enforce uniform telemetry, timeouts, and retry policies.
- Messy resource cleanup at shutdown.

### Proper Pattern

Instantiate `TokenCredential` and clients at application startup—or per **tenant-specific endpoint/config** backed by a bounded cache with eviction. Reuse clients across requests, keep configuration immutable/stable, and cap total client instances.

**A thread-safe client** does not make every surrounding object thread-safe: request builders/options, mutable maps, and collections must obey their contracts—never share one `ListBlobsOptions` instance while another thread mutates it.

## 25. When Should You Close/Dispose?

There is no single `try-with-resources` rule for all Azure SDK Java clients.

| Resource | Management Approach |
|---|---|
| `BlobServiceClient` or similar service clients | Reuse; do not force `close()` if the class does not implement it |
| Credentials with dedicated resources | Check API/docs; do not assume `TokenCredential` is always `AutoCloseable` |
| Custom HTTP transport / connection pool | If created and owned by the app, close per the implementation's official API |
| Reactor subscription | Cancel/dispose when job stops; does not cancel server LROs |
| `InputStream`/`OutputStream`/`FileChannel` | Close with `try-with-resources` whenever opened by the app |
| App-created `ExecutorService`/`Scheduler` | Shut down cleanly on application exit |
| SDK service client exposing `close()` | Close only when required/permitted by the specific API and ownership model |

### Common Mistake

~~~java
// Do not do this by default if BlobServiceClient does not implement AutoCloseable:
// try (BlobServiceClient client = builder.buildClient()) { ... }
~~~

Instead:

~~~text
Application startup:
  create shared credential
  create service client(s)
  configure telemetry/retries/timeouts

Application lifetime:
  reuse clients for concurrent operations

Application shutdown:
  stop accepting new jobs
  drain/cancel outstanding publishers as needed
  flush checkpoint/logs
  close only resources explicitly owned and closable
~~~

**Client reuse does not mean keeping unbounded instances forever**. If a multi-tenant system creates one client per storage account, maintain a cache keyed by endpoint/auth scope with TTL/eviction and lifecycle bounds so client counts cannot grow without limit.

## 26. HTTP Transport, Connection Pools, and Threads

The Azure SDK for Java supports different HTTP transport implementations (such as Netty or OkHttp) depending on dependencies and configuration. Applications must monitor:

- Concurrent in-flight HTTP request count.
- TCP/TLS connection reuse and keepalive.
- Connection pool size and pending-acquire queues.
- Event-loop threads vs. blocking worker threads.
- DNS, proxies, and Private Endpoint routing.
- Connect/read/response timeout semantics.
- Resource ownership when supplying a custom transport.

### Why Is a Shared Transport Helpful?

A properly managed HTTP pipeline/transport reuses network connections and shares metrics, cutting TLS handshake overhead. However, **never inflate connection pools unboundedly** to "fix" 429s: server throughput/quotas and client backpressure still govern capacity.

### Danger of Mixing Reactive + Blocking

A WebFlux handler like:

~~~java
// Anti-pattern on a reactive event loop:
return Mono.fromCallable(() -> syncClient.listBlobs().iterator().hasNext());
~~~

Executing blocking I/O on an event-loop thread can stall the server. If you must use a sync SDK:

~~~java
return Mono.fromCallable(
        () -> syncClient.listBlobs().iterator().hasNext())
    .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

This **only offloads blocking work to `boundedElastic`**—it does not make the I/O non-blocking or increase concurrency budgets. Prefer the async SDK when building an end-to-end Reactor pipeline.

## 27. Spring Boot: Managing Clients with Dependency Injection

Singleton bean example for the Azure Blob SDK:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AzureBlobConfiguration {

    @Bean
    TokenCredential azureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    BlobServiceClient blobServiceClient(
            TokenCredential credential,
            @Value("${azure.storage.blob.endpoint}") String endpoint) {

        return new BlobServiceClientBuilder()
            .endpoint(endpoint)
            .credential(credential)
            .buildClient();
    }
}
~~~

Usage in a service:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobContainerClient;

import org.springframework.stereotype.Service;

@Service
public final class InvoiceStorageService {
    private final BlobContainerClient container;

    public InvoiceStorageService(BlobServiceClient client) {
        this.container = client.getBlobContainerClient("invoices");
    }

    public long countInvoices() {
        long result = 0;
        for (var item : container.listBlobs()) {
            result++;
        }
        return result;
    }
}
~~~

### Example Limitations

- `countInvoices()` can run for a long time; never wire it directly to a low-SLA HTTP endpoint.
- The `BlobServiceClient` bean **does not assume a destroy method**; Spring lifecycle hooks must match the exact client API and transport ownership.
- Endpoint comes from externalized config with no account key.
- Across multiple storage accounts, define named clients/configurations rather than routing incompatible endpoints through one client.
- Never store mutable per-enumeration state in a singleton field shared across requests.
- For long-running listings, use background jobs/queues and checkpoints.

## 28. Timeouts and Cancellation at the Application Layer

A GET `/blob-inventory` endpoint returning full results might take 15 minutes while ingress times out at 30 seconds. Instead, use:

~~~text
POST /inventory-jobs
  -> 202 Accepted, jobId
GET /inventory-jobs/{jobId}
  -> status, processed, lastCheckpoint, errors
GET /inventory-jobs/{jobId}/results
  -> bounded page of processed results
~~~

### When a Request Is Canceled

- Canceling a `Flux` subscription stops future HTTP page requests, yet an in-flight server request may still finish.
- Killing a Java process before persisting a checkpoint causes the page to replay.
- Interrupting a `SyncPoller` waiting thread does not necessarily cancel the server-side LRO.
- `Future.cancel(true)` is a local signal, not proof the backend rolled back.
- For writes, reconcile server state before retrying or canceling.

### Deadline Propagation

If the end-to-end deadline is 30 seconds, never stack three retry layers of 30 seconds each. Allocate budgets:

~~~text
API request budget:       30s
Identity/token:           bounded
Per-page/request timeout: bounded
Retries:                 budget-aware
Fallback:                fail fast or async job
Background run deadline: independent from HTTP client timeout
~~~

All timeouts above are architectural choices, not Azure SDK defaults.

## 29. Observability: What Should You Measure?

To avoid "the service is slow for unknown reasons," monitor:

| Signal | Unit/Dimension | Purpose |
|---|---|---|
| Pages fetched | pages/job | Enumeration progress |
| Items processed | items/job | Business throughput |
| Preferred/actual page size | items/page | Inspect paging behavior |
| Time per page | ms | Detect network/throttling issues |
| Continuation checkpoint age | min | Resume health |
| 429/503/retry counts | attempts | Throttling and transient errors |
| Active LRO count | operations | Capacity management |
| LRO status/duration | state, s | Provisioning reliability |
| Poll attempts | polls/operation | Prevent excessive polling |
| Connection pool pending/timeouts | count/ms | Client transport pressure |
| JVM heap/GC/threads | MiB/ms/count | Catch `collectList` or client churn |
| Authentication failures | 401/403 | RBAC, token, or network issues |
| Application p95/p99 | ms | UX and SLO compliance |
| Storage/management API request cost | per operation | FinOps and quotas |
| Replayed/duplicate items | count | Idempotency quality |

### Correlation IDs

Track `jobId`, `tenantId` (pseudonymized per policy), Azure `x-ms-request-id`, or SDK/service correlation fields. **Never log continuation tokens, SAS tokens, access tokens, connection strings, or customer data**.

### OpenTelemetry / Application Insights

The Azure SDK participates in tracing and diagnostics when configured properly. Attach custom spans:

~~~text
HTTP POST /inventory-jobs
  -> schedule job
     -> list blobs page 12
        -> process 200 items
        -> save checkpoint
        -> begin Azure LRO
           -> status polls
           -> final resource validation
~~~

Never treat a single request trace as a multi-hour distributed transaction; link stages with durable job records and event/correlation IDs.

## 30. Security and Access Boundaries

### Client Credentials

- Prefer `DefaultAzureCredential` and managed identity/workload identity where supported.
- Local development uses controlled signed-in credentials, never hard-coded account keys.
- Grant **data-plane RBAC** for Blob listing (`Storage Blob Data Reader`), adding write permissions only if the job genuinely mutates blobs.
- Grant separate **management-plane RBAC** for LROs creating/deleting resources.
- Never grant an inventory worker subscription-wide `Owner` unnecessarily.
- Separate identities and permission scopes per tenant and environment.
- Keep required secrets in Key Vault with rotation and auditing.

### Networking

- Storage firewalls, Private Endpoints, VNets, Private DNS, and outbound routes must all align.
- Endpoint authentication and network reachability are **two distinct requirements**.
- If using proxies, verify service client transports and TLS truststores.
- Never disable certificate verification to "fix" TLS errors.
- With async SDKs, verify DNS and endpoint routing for the HTTP provider.
- Never substitute raw private endpoint IPs for hostnames when TLS hostname verification depends on the FQDN.

### Preventing Continuation Token Exposure

Continuation tokens can contain internal state or resource identifiers. Never place them directly into public URL query logs; when exposing cursors to frontends, wrap them in opaque application cursors or signed references with scope, expiry, and authorization checks.

## 31. Cost and Quotas

A seemingly "read-only listing" still incurs costs:

- Azure Storage **List operations** billed per request/transaction meter.
- Cross-region or on-prem network egress depending on architecture.
- JVM / Container Apps / AKS / VM compute running the job.
- Checkpoint database storage and Log Analytics ingestion.
- Azure management API quotas and polling requests.
- Retries and duplicate processing multiplying API calls.
- Connection and memory pressure forcing compute scale-up.

### Page Count Example

~~~text
Total blobs:      1,200,000
Preferred page:   200 items
Theoretical pages: 1,200,000 / 200 = 6,000 pages
Actual pages:     may vary by service-side behavior
~~~

If actual pages average only 100 items, the scan takes roughly 12,000 page requests. Each request carries latency overhead, rate limits, and billing meters. **Never estimate exact pricing solely from this formula**; consult Azure pricing meters and actual telemetry.

### Time Estimate

~~~text
Average page fetch: 80 ms
Pages: 6,000
Sequential fetch lower bound ~480,000 ms = 8 minutes

Total job also adds:
  item processing, retries, storage writes, checkpoint commits,
  throttling, network variance, and startup.
~~~

If pages yield items quickly yet downstream processing is slow, network fetching is no longer the bottleneck. Increasing page size raises RAM usage and crash replay time; balance **latency, checkpoint frequency, and memory**.

## 32. Common Anti-Patterns

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| `collectList()` on millions of items | Heap/GC/OOM | Stream pages |
| Full list inside HTTP GET | Timeouts and memory spikes | Async job + paginated results |
| Assuming fixed page sizes | Missed items or index bugs | Iterate response values/tokens |
| Parsing continuation tokens | Breaks on service format changes | Treat token as opaque, persist verbatim |
| Checkpointing before processing page | Data loss on crash | Commit page then checkpoint |
| No idempotency | Replays cause duplicate side effects | Unique keys / upserts |
| Treating listing as a snapshot | Misses/duplicates under mutations | Reconciliation / versioning |
| Retrying `begin` LRO on client timeout | Duplicates / conflicts | Reconcile resource/operation status |
| Treating HTTP 202 as Succeeded | Using unready resources | Poll terminal state + postconditions |
| Polling every 100ms for hours | 429s / quotas / costs | Honor `Retry-After`, bounded intervals |
| Assuming client timeout = server cancel | Wrong business state | Durable tracking |
| Creating credentials/clients per request | Connection/auth churn | Singletons / client caches |
| Calling `close()` on unsupported clients | Compile errors / broken ownership | Follow exact client API |
| Calling `block()` on WebFlux event loop | Thread starvation | Async SDK or `boundedElastic` |
| Infinite retries | Throttling / storms | Retry budgets + jitter |
| Logging tokens and SAS strings | Credential/data leakage | Redaction and access controls |

## 33. Troubleshooting by Symptom

### Blob Listing Is Slow or Fails Mid-Scan

1. Verify endpoint, account, container, and prefix.
2. Check SDK version, preferred page size, and actual items/page.
3. Inspect HTTP status codes, `x-ms-request-id`, `Retry-After`, and retry counts.
4. Verify `Data Reader` role and Storage firewall/networking.
5. Check JVM heap, GC pauses, client allocations, thread pools, and HTTP connections.
6. Locate the last checkpoint; resume with identical scope and prefix.
7. If the token is invalid, restart the scan with idempotent deduplication.
8. Check whether data mutated heavily during the scan.

### LRO Stuck InProgress

1. Confirm `begin` was sent once or whether retries fired.
2. Record operation/resource ID, poll attempts, status, and age.
3. Read service-specific provisioning states/errors and activity logs.
4. Check quotas, dependencies, networking, and resource permissions.
5. Honor `Retry-After`; stop spamming polls.
6. Compare client timeout against server operation state.
7. If status is unknown, reconcile before retrying or cleaning up.
8. Escalate with redacted `x-ms-request-id` / correlation IDs.

### Excessive Client Connections or Token Requests

1. Search for `new ClientBuilder` inside per-request paths.
2. Check whether custom HTTP transports/pools are instantiated per request.
3. Count distinct client instances per endpoint/tenant.
4. Inspect connection pool limits/queues and HTTP provider metrics.
5. Check whether `DefaultAzureCredential` is built repeatedly.
6. Check for unreleased Reactor subscriptions or blocking operations.
7. Switch to DI singletons/cached clients and bounded concurrency.
8. Load-test before and after—do not rely on reading source code alone.

## 34. Case Study: Blob Inventory and Provisioning Job

### Context

A SaaS platform stores over 5 million blobs across many tenants. Every day it inventories metadata and, for new containers, triggers Azure resource-configuration operations. The Java app runs on AKS with 8 replicas, any of which may be rescheduled.

**Requirements:**

- Never load the full inventory into RAM.
- Never allow two pods to run the same job simultaneously.
- Resume from checkpoints if a worker restarts.
- Never create duplicate resources if `begin` LRO times out.
- Long jobs must never block HTTP requests.
- Separate Storage read permissions from management write permissions.
- Provide dashboards for progress, retries, and cost.

### Architecture

~~~mermaid
flowchart LR
  API["Java API / AKS"] --> QUEUE["Job queue"]
  QUEUE --> WORK["Bounded workers"]
  WORK --> BLOB["Blob listing PagedFlux/PagedIterable"]
  BLOB --> CKPT["Durable checkpoint DB"]
  WORK --> LRO["Azure management LRO"]
  LRO --> TRACK["Operation tracker"]
  TRACK --> CKPT
  CKPT --> STATUS["Job status API"]
  WORK --> MON["Azure Monitor"]
  LRO --> MON
~~~

### Execution Plan

1. API validates the request, creates `inventory-job-id`, checks identity/tenant scope, and enqueues the job.
2. Worker acquires a lease/job ownership lock from a durable store.
3. Uses a shared configured `BlobServiceClient` or `BlobContainerAsyncClient`.
4. Lists by prefix/container in pages of 200–500 items tuned via benchmarks.
5. Upserts metadata using unique keys `(tenant, container, blob name, ETag/version)`.
6. Saves the continuation token only after the page completes.
7. For resource provisioning, persists an idempotency key and starts a single LRO.
8. Polls the LRO at bounded intervals and records terminal status and final resource ID.
9. If a worker dies, a replacement recovers the checkpoint and reconciles active LROs.
10. Dashboards track progress, 429s, heap, LRO duration, duplicate counts, and cost.

### Incident Analysis

When the team previously used `collectList()`, all 8 pods hit memory spikes, crashed with OOM, and restarted from page 1, leaving duplicate rows in the downstream database. After switching to paging + checkpoints + idempotent upserts, peak memory dropped and retries stopped duplicating rows. For LROs, the team stopped calling `begin` a second time immediately on client timeout and began reconciling operation/resource state first.

This is a reference architecture, not benchmark numbers for a specific Azure environment. Always load-test against your own quotas, network, and data distribution.

## 35. Comprehensive Hands-On Lab

> **Safety:** run only on an authorized **lab** Azure Storage container and subscription/resource group. Listing, creating resources, LROs, and logging incur charges; avoid deleting or modifying production resources. Do not create extra files in the repo outside the lesson scope per worker contract; learners create their own source files when practicing.

### Part A — Setup

1. Pick a lab storage account/container containing 1,000–5,000 test blobs.
2. Grant `Storage Blob Data Reader` to your managed/developer identity.
3. Set `AZURE_STORAGE_BLOB_ENDPOINT` via environment variable.
4. Create a Java 17/Maven project with the Azure SDK BOM and dependencies.
5. Create a shared `BlobServiceClient` using `DefaultAzureCredential`.
6. Verify networking/Private Endpoints/DNS if the account disables public access.
7. Estimate List operation costs, request limits, and budget.

### Part B — Pagination

1. Use `listBlobs()` and `PagedIterable` to count items.
2. Use `iterableByPage(200)` and log item counts per page (never log continuation tokens).
3. Measure page count, duration, and peak heap.
4. Intentionally stop after 3 pages and save the checkpoint to a test DB.
5. Resume using the exact same prefix, options, and token.
6. Replay 1 page to verify idempotent upserts.
7. Mutate data mid-scan and observe why listing is not a snapshot.
8. Compare `collectList()` (on a tiny dataset only) against streaming **without intentionally causing OOM**.

### Part C — Async and Backpressure

1. Create a reusable `BlobContainerAsyncClient`.
2. Use `PagedFlux` and `byPage(200)`.
3. Implement `processAsync` writing to a lab datastore.
4. Cap `flatMap` concurrency around 4–8 based on benchmarks.
5. Use `concatMap` to checkpoint pages in order.
6. Inject a failure on one item in a page and verify the checkpoint does not advance.
7. Confirm the Reactor pipeline never calls blocking JDBC on event-loop threads.
8. Measure throughput, 429s, and memory as concurrency varies.

### Part D — Long-Running Operations

1. Pick a real **LRO-supporting Azure operation** permitted in your lab resource group.
2. Identify the actual `begin...` method and `SyncPoller`/`PollerFlux` types on that service SDK; if unavailable, use documented REST operation status APIs.
3. Start one operation and record its operation ID and timestamp.
4. Track `InProgress` through terminal state using bounded intervals.
5. Verify `Succeeded`/`Failed` and final resource postconditions.
6. Set a client polling deadline shorter than server completion time; confirm server state is not lost.
7. Build a durable tracker/status API with an idempotency key.
8. Restart the worker and reconcile server state before retrying `begin`.
9. Never use production resources or perform unapproved destructive operations.

### Part E — Client Management and Monitoring

1. Compare per-request client creation against a singleton bean.
2. Measure connection counts, latency, and token acquisitions in the lab.
3. Tune retries and timeouts for the workload per SDK/version.
4. Instrument metrics for pages, items, retries, LRO duration, and heap.
5. Enable secret-free tracing and diagnostics.
6. Verify subscription management RBAC is separate from Storage data-plane roles.
7. Write shutdown routines releasing only streams, executors, and custom transports actually owned by the app.
8. Calculate cost per inventory job and cost per successful provisioning operation.
9. Write runbooks for 429s, invalid continuation tokens, LRO timeouts, and stale operation states.
10. Clean up lab resources and document operational takeaways.

## 36. Self-Check Questions

**Q1.** Why should listing two million blobs never return a full Java `List<BlobItem>`?

**Q2.** How do `PagedIterable` and `PagedFlux` differ in execution and thread handling?

**Q3.** Does `iterableByPage(200)` guarantee every page contains exactly 200 items?

**Q4.** How does a continuation token differ from an offset or page number?

**Q5.** Why must you keep the exact same token and listing scope when resuming?

**Q6.** Why must checkpoints be saved **after** a page finishes processing successfully?

**Q7.** How can you minimize duplicate side effects if a worker crashes after committing to the DB but before saving the checkpoint?

**Q8.** Does listing guarantee a consistent snapshot if blobs change between pages?

**Q9.** Why is `collectList()` dangerous on large datasets?

**Q10.** How do `concatMap` and `flatMap(..., 8)` serve two different purposes in async page processing?

**Q11.** Does backpressure alone guarantee you will never hit Azure Storage 429s?

**Q12.** Why is HTTP 202 insufficient to conclude an Azure resource finished provisioning?

**Q13.** How does `SyncPoller<P,T>` distinguish polling values from the final result?

**Q14.** When polling fails due to a client timeout, can you conclude the server operation `FAILED`?

**Q15.** How does `PollerFlux` differ from `SyncPoller` in a WebFlux application?

**Q16.** Why must you honor `Retry-After` rather than polling every 100ms indefinitely?

**Q17.** Does canceling a `PollerFlux` subscription always cancel the server-side operation?

**Q18.** If `begin` LRO was received yet the response timed out, what should you do before retrying `begin`?

**Q19.** Why can some LROs not be resumed via a token in every SDK?

**Q20.** When do you need a durable operation tracker and background worker instead of holding an HTTP request open?

**Q21.** Should Azure SDK clients be instantiated per servlet request?

**Q22.** Does `BlobServiceClient` require calling `close()` by default?

**Q23.** If an app creates a custom HTTP connection pool, who is responsible for disposing of it?

**Q24.** Why can calling synchronous `listBlobs()` on a Reactor event loop cause starvation?

**Q25.** Do `DefaultAzureCredential` and RBAC automatically create a network route to a Private Endpoint?

**Q26.** Does Resource Group `Contributor` automatically grant `Storage Blob Data Reader`?

**Q27.** Which metrics distinguish service throttling, connection pool pressure, and Java heap OOM?

**Q28.** Why might an LRO marked `Succeeded` still require verifying resource postconditions?

**Q29.** Why is pagination cost more than just memory and CPU?

**Q30.** What are the three most critical safeguards when a job both scans millions of blobs and triggers Azure LROs?

**Completion Criteria:** learners accurately explain Azure SDK for Java abstractions, write memory-bounded listing code, use continuation tokens/checkpoints, understand LRO polling alongside timeouts/cancellation/idempotency, manage clients/credentials/HTTP transports properly, and incorporate observability and cost control.

## Conclusion

**Pagination, long-running operations, and client resource management** are three foundational skills for Java applications calling Azure at scale. **`PagedIterable`/`PagedFlux`** let you traverse millions of objects without loading everything onto the heap—provided you treat continuation tokens as opaque, checkpoint only after downstream commits, and enforce idempotency because retries can replay pages. **`SyncPoller`/`PollerFlux`** manage multi-minute operations, yet you must distinguish accepted requests from terminal states; client timeouts or stopped polling never guarantee Azure canceled the operation.

Operationally, **reuse Azure SDK clients, credentials, and HTTP pipelines**, avoid creating clients per request, bound concurrency, and close only resources you explicitly own. Combined with **Microsoft Entra RBAC, network security, `Retry-After`/backoff, tracing, Azure Monitor, durable job tracking, and FinOps**, Java systems on Azure stay resilient under transient failures, massive datasets, and long-running resource operations.
