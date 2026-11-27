# Timeouts, Retries, Cancellation, and Resource Cleanup

In reactive applications using Spring Data Elasticsearch, read and write operations are typically expressed as `Mono` or `Flux`. A pipeline may span multiple asynchronous steps, yet it still needs wait-time limits, handling for transient failures, stopping work when no consumer remains, and releasing opened resources.

These four mechanisms are related but do not replace one another:

- **Timeout** caps how long a single operation or an entire pipeline is allowed to run.
- **Retry** resubscribes to the source Publisher after a recoverable failure.
- **Cancellation** signals that the subscriber is no longer interested in results and asks upstream to stop work.
- **Resource cleanup** closes or returns resources when the pipeline completes, fails, or is canceled.

Proper design considers timeout placement, error classification, idempotency of Elasticsearch operations, transport-level request cancellation, and resource lifecycles such as connections, schedulers, scroll contexts, or Point in Time (PIT). Reactivity does not automatically make an operation safe to retry or guarantee the server halts immediately when a subscriber cancels.

## 1. Lifecycle of a Reactive Operation

### 1.1. Publishers Describe Work; Subscriptions Trigger Execution

Spring Data Elasticsearch reactive APIs typically return `Mono<T>` or `Flux<T>`. Example:

~~~java
Mono<Product> saved = reactiveOperations.save(product);

Flux<Product> products = reactiveOperations.search(
    query,
    Product.class
);
~~~

Creating `saved` or `products` usually only creates a Publisher. Work is triggered when a subscription occurs.

In WebFlux, the framework subscribes to the Publisher returned by the controller. At the service layer, return the Publisher to the caller rather than calling `subscribe()` manually.

### 1.2. A Pipeline Can Have Multiple Termination States

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Subscribed
    Subscribed --> Running
    Running --> Completed
    Running --> Error
    Running --> Cancelled
    Completed --> Cleanup
    Error --> Cleanup
    Cancelled --> Cleanup
    Cleanup --> [*]
~~~

A subscription can terminate via three primary signals:

- `onComplete`: the Publisher finishes normally.
- `onError`: the Publisher encounters an error.
- `cancel`: the subscriber requests stopping the subscription.

Cancellation is not an `onError`. Therefore, `onErrorResume` does not handle cancellation, and `retryWhen` does not retry simply because a subscriber canceled.

### 1.3. Why Manage the Entire Lifecycle?

Adding timeouts without understanding retries can cause the application to send more requests than intended. Retrying without considering cancellation can keep scheduling new attempts after a client has already disconnected. Opening a PIT or custom resource without cleaning up across all three termination paths can leak resources.

A well-designed pipeline should answer:

- How long may a single request run at most?
- How long may the entire retry chain span?
- Which errors are retryable?
- Is the operation safe to repeat?
- Who owns the subscription and has authority to cancel?
- Which resources must close on complete, error, or cancel?

## 2. Timeout Layers to Distinguish

### 2.1. Connect Timeout

Connect timeout limits the time spent establishing a connection to Elasticsearch or a proxy. Depending on the transport, it may cover part of the network handshake.

If the endpoint is unreachable, DNS/network fails, or the server refuses connections, connect timeout fails fast instead of waiting indefinitely.

Connect timeout belongs to HTTP transport/client configuration. Reactor `timeout` does not replace transport-level connection timeouts.

### 2.2. Connection Acquisition Timeout

When a client uses a connection pool, requests may wait for an available connection. Acquisition timeout caps how long a request waits in the pool.

This differs from a slow server: Elasticsearch may be healthy while the application has exhausted the connection pool due to too many in-flight requests or responses not being consumed/closed properly.

If acquisition timeouts spike, review concurrency, connection pool sizing, and response lifecycle before blindly raising pool size.

### 2.3. Response/Socket Timeout

Response timeout limits how long the client waits for a server response after sending the request. Exact property names depend on the HTTP client/transport and Spring Data Elasticsearch version.

Response timeout protects the network layer. It generally governs the request/response exchange, whereas Reactor timeout can cover application-level steps before or after the request as well.

Do not assume socket timeout and Reactor timeout share identical semantics or starting points.

### 2.4. Elasticsearch Search Timeout

The Search API accepts a server-side timeout to limit search execution across shards. When reached, search may return partial results with the `timed_out` flag set, depending on request parameters and partial-result settings.

This is a server-side search execution limit. It does not mean the client stopped waiting for the response.

If reports require complete results, check metadata such as `timed_out` and shard status rather than treating every valid response as complete.

### 2.5. Reactor Timeout

Reactor provides the `timeout` operator to bound how long a Publisher may take to emit a signal:

~~~java
Mono<Product> result = reactiveOperations.findById(id, Product.class)
    .timeout(Duration.ofSeconds(3));
~~~

If the Publisher emits no signal within the configured duration, downstream receives a `TimeoutException` (or configured fallback/exception), and Reactor cancels the upstream subscription.

This timeout covers request wait time plus preceding operators up to where it is placed. Operator placement in the chain determines exactly which work is timed.

### 2.6. Per-Attempt Timeout vs. Overall Deadline

An operation may perform multiple retries. Distinguish:

- **Per-attempt timeout**: caps duration for a single call to Elasticsearch.
- **Overall deadline**: caps total elapsed time from the first attempt until completion or retry exhaustion.

For instance, each attempt may be allowed at most 3 seconds, with up to 3 retries, while the overall operation must finish within 10 seconds.

If you only set a per-attempt timeout without an overall deadline, cumulative attempts and backoff delays can exceed the API SLA.

## 3. Placing Timeouts in a Reactor Pipeline

### 3.1. Timeout for a Single Call

~~~java
Mono<Product> findProduct(String id) {
    return reactiveOperations.findById(id, Product.class)
        .timeout(Duration.ofSeconds(3));
}
~~~

This is a straightforward way to bound read wait time. On timeout, the error propagates downstream.

If a valid fallback exists, handle it at the service layer:

~~~java
Mono<Product> findProductOrEmpty(String id) {
    return reactiveOperations.findById(id, Product.class)
        .timeout(Duration.ofSeconds(3))
        .onErrorResume(
            TimeoutException.class,
            error -> Mono.empty()
        );
}
~~~

Only use an empty fallback when business semantics equate timeout with no result or permit missing results. Never turn timeouts into empty globally, as that hides infrastructure failures.

### 3.2. Per-Attempt Timeout, Retry, and Overall Deadline

~~~java
Mono<Product> saveWithRetry(Product product) {
    return Mono.defer(() -> reactiveOperations.save(product))
        .timeout(Duration.ofSeconds(3))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(this::isRetryable)
        )
        .timeout(Duration.ofSeconds(10));
}
~~~

In this example:

1. `Mono.defer` creates the operation on subscription.
2. The inner timeout bounds each attempt.
3. `retryWhen` retries only errors accepted by `isRetryable`.
4. The outer timeout bounds total duration across the entire chain.

The `3` in `Retry.backoff` is the number of retries after the initial attempt, not the total number of executions. Verify how attempts are counted in your application's configuration.

### 3.3. Timeout Placement Changes Semantics

~~~java
source.timeout(perAttempt)
    .retryWhen(retryPolicy);
~~~

Timeout precedes retry, so an attempt timeout counts as an error eligible for retry.

~~~java
source.retryWhen(retryPolicy)
    .timeout(overallDeadline);
~~~

Timeout follows retry, so it bounds the entire chain. When the outer timeout fires, the inner retry pipeline is canceled.

With only an outer timeout, a single attempt can consume nearly the whole deadline. With only an inner timeout, total time can stretch across multiple retries.

### 3.4. Timeout for Flux

For `Flux`, `timeout(Duration)` usually limits the gap between consecutive signals rather than total duration of the entire stream.

~~~java
Flux<SearchHit<Product>> hits =
    reactiveOperations.search(query, Product.class)
        .timeout(Duration.ofSeconds(5));
~~~

If each hit arrives less than 5 seconds apart, the stream can run longer than 5 seconds overall. To cap total stream duration, apply an outer deadline:

~~~java
Flux<SearchHit<Product>> hits =
    reactiveOperations.search(query, Product.class)
        .timeout(Duration.ofSeconds(5))
        .take(Duration.ofSeconds(30));
~~~

`take(Duration)` completes the stream after the specified duration. If you want an error on deadline expiration instead of normal completion, apply an overall timeout pattern compatible with your Publisher structure and scheduler.

Read operator semantics carefully for Mono vs. Flux; never specify a timeout duration without confirming whether it measures inter-signal intervals or total elapsed time.

### 3.5. Timeout with a Fallback Publisher

You can supply an alternative Publisher on timeout:

~~~java
Mono<Product> result =
    reactiveOperations.findById(id, Product.class)
        .timeout(
            Duration.ofSeconds(2),
            Mono.defer(() -> cache.findById(id))
        );
~~~

When the primary source emits no signal within the deadline, Reactor switches to the fallback Publisher. The primary source is canceled.

Fallbacks should have clear time bounds and semantics. If the cache can also be slow, give the cache its own timeout or apply an overall deadline across the chain.

## 4. Retries in Reactor

### 4.1. Retry Means Resubscribe

Retry does not resume from the exact failed instruction. Reactor resubscribes to the source Publisher according to the retry policy.

~~~java
Mono<Product> result =
    reactiveOperations.findById(id, Product.class)
        .retry(2);
~~~

If the source is a cold Publisher whose work executes on subscription, retrying re-executes the read operation. This often suits transient network failures.

For write operations, retrying can resend the same command. Always evaluate idempotency before enabling retries.

### 4.2. Unconditional Retries

`retry(n)` retries after every error up to the limit. While simple, this is usually too broad for production applications.

Errors like mapping exceptions, validation failures, or authorization errors will not resolve on resend. Retrying them only adds load and delays reporting the real failure.

Prefer `retryWhen` with an error-classifying predicate.

### 4.3. Exponential Backoff and Jitter

~~~java
Retry retryPolicy = Retry.backoff(
        3,
        Duration.ofMillis(200)
    )
    .maxBackoff(Duration.ofSeconds(3))
    .jitter(0.5)
    .filter(this::isRetryable);
~~~

`Retry.backoff` increases the wait interval across retries. Jitter adds randomness so multiple clients do not retry in lockstep.

You can add a hook to observe retries:

~~~java
Retry retryPolicy = Retry.backoff(
        3,
        Duration.ofMillis(200)
    )
    .maxBackoff(Duration.ofSeconds(3))
    .jitter(0.5)
    .filter(this::isRetryable)
    .doBeforeRetry(signal -> {
        log.warn(
            "Retrying Elasticsearch operation, attempt={}, cause={}",
            signal.totalRetries() + 1,
            signal.failure().toString()
        );
    });
~~~

Do not log full payloads if they contain sensitive data. Metrics should count retries by error category rather than high-cardinality labels like document IDs.

### 4.4. Classifying Retryable Errors

A predicate can match error categories:

~~~java
private boolean isRetryable(Throwable error) {
    return error instanceof TimeoutException
        || error instanceof ConnectException
        || isTooManyRequests(error)
        || isTransientServerError(error);
}
~~~

This is a conceptual example. Concrete exception types depend on the transport and client version. In real code, unwrap relevant wrapper exceptions before classifying.

Errors that normally should not be retried automatically:

- Document mapping or parsing errors.
- Validation errors.
- 401/403 authentication or permission failures.
- Missing index/mapping due to misconfiguration.
- Invalid Query DSL.
- Business errors that waiting will not fix.

429s, certain 502/503/504 errors, connection resets, and timeouts may be transient, yet still require bounded retries and idempotency analysis.

### 4.5. Retry Exhausted

When the retry budget runs out, Reactor emits a retry-exhausted exception or the last failure depending on configuration. You can map the final error at the service layer for a cleaner contract:

~~~java
.retryWhen(
    Retry.backoff(3, Duration.ofMillis(200))
        .filter(this::isRetryable)
        .onRetryExhaustedThrow((spec, signal) ->
            new ElasticsearchUnavailableException(
                "Elasticsearch operation exhausted retry budget",
                signal.failure()
            )
        )
)
~~~

Do not convert every error into "service unavailable" if the root cause was mapping or validation. Preserve the underlying cause and keep error classification meaningful.

## 5. Retries Must Account for Idempotency

### 5.1. Timeouts Do Not Reveal What the Server Did

A common scenario:

1. Client sends a write request.
2. Elasticsearch receives and executes the write.
3. The response is lost or arrives after the client's timeout.
4. Client observes a timeout and does not know whether the write succeeded.
5. Client retries.

A timeout only indicates the client did not receive a timely response. It does not prove the server never processed the request.

Therefore, retrying writes must be designed to be safe on re-execution or able to verify completion state.

### 5.2. Using Stable IDs for Save Operations

If the same entity always uses the same document ID and unchanged retry payload, index/save operations usually yield an idempotent final state: the document with that ID is written again.

~~~java
Mono<Product> save(Product product) {
    return Mono.defer(() -> reactiveOperations.save(product));
}
~~~

Crucially, the ID must remain stable across subscriptions. If a new ID is generated on each retry, retrying can create duplicate documents.

### 5.3. Non-Idempotent Operations

Be careful with:

- Update scripts incrementing a counter.
- Appending elements to an array.
- Creating documents with random IDs.
- Emitting events or sending notifications inside the same pipeline.
- Calling external services with side effects.

If retried after a timeout, these operations may run twice. Use event IDs for deduplication, versioning, optimistic concurrency, or a reconciliation process.

### 5.4. create and Conflicts on Retry

If a `create` with a fixed ID succeeded on the first attempt yet the response was lost, a retry may fail with a version conflict because the document already exists.

Do not blindly treat this conflict as a permanent failure. You may need to read the document by ID and compare state/payload to verify whether the prior attempt succeeded or a genuine conflict occurred.

### 5.5. Retrying Individual Items in the Bulk API

A bulk response can have an HTTP 200 success while individual items fail. That situation does not necessarily emit `onError` in the reactive pipeline; the application receives a normal response containing `errors` metadata and per-item statuses.

Therefore:

- Inspect the bulk response.
- Identify succeeded items.
- Classify each failed item.
- Build retry batches containing only retryable items.
- Route permanently failed items to a dead-letter queue.
- Never blindly retry the entire bulk batch.

`retryWhen` only reacts to a Publisher's error signal. It does not automatically inspect the `errors` flag inside a normal bulk response.

## 6. Retries and Timeouts: Operator Ordering

### 6.1. Per-Attempt Timeout Before Retry

~~~java
Mono<Product> operation =
    Mono.defer(() -> reactiveOperations.save(product))
        .timeout(Duration.ofSeconds(2))
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .filter(this::isRetryable)
        );
~~~

Each subscription to the source has a 2-second timeout. If an attempt times out and the predicate accepts the error, the retry policy resubscribes.

### 6.2. Overall Timeout Wrapping Retry

~~~java
Mono<Product> operation =
    Mono.defer(() -> reactiveOperations.save(product))
        .timeout(Duration.ofSeconds(2))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(1))
                .filter(this::isRetryable)
        )
        .timeout(Duration.ofSeconds(6));
~~~

The outer timeout covers all attempts and backoff delays. When the overall deadline expires, the inner retry chain is canceled.

### 6.3. Avoid Accidentally Retrying the Overall Timeout

If the overall timeout sits inside an outer retry operator, the deadline error itself can be retried and breach the SLA.

Keep the overall timeout outermost or exclude deadline exceptions from the retry predicate. Define clearly which retry policy owns timeout errors.

### 6.4. Fallback Before or After Retry?

If `onErrorResume` turns a retryable error into a fallback before `retryWhen`, the retry operator never sees that error.

~~~java
source
    .onErrorResume(error -> Mono.empty())
    .retryWhen(retryPolicy);
~~~

Here the error becomes an empty completion, so retries never run.

Normally, retry transient errors first and apply fallback only to the final failure:

~~~java
source
    .retryWhen(retryPolicy)
    .onErrorResume(
        ElasticsearchUnavailableException.class,
        error -> fallback()
    );
~~~

Fallbacks must align with business semantics; never mask data errors.

## 7. Cancellation in Reactive Streams

### 7.1. Cancellation Is a Request to Stop a Subscription

A subscriber may cancel when:

- The user closes the HTTP connection.
- A request times out.
- An operator such as `take` receives enough elements.
- The service no longer needs the result.
- A job stops or the application shuts down.
- A downstream Publisher stops demanding data.

Cancellation travels upstream from downstream along the subscription chain.

### 7.2. Cancellation Is Not Rollback

Canceling a subscription does not guarantee Elasticsearch rolls back an operation already received.

If a write request has reached the server, Elasticsearch may still finish the write even after the client stops waiting. The transport may try to close the request/connection, yet it cannot turn cancellation into a transactional rollback.

For critical writes:

- Use stable document IDs.
- Design idempotent updates.
- Record operation IDs.
- Re-read state to verify if needed.
- Use a durable queue or outbox when work must finish regardless of client disconnects.

### 7.3. Cancellation Does Not Trigger Retries

`retryWhen` reacts to error signals. Cancellation is not an error signal, so it is not retried automatically.

Likewise, `onErrorResume` does not run on cancellation. To clean up on cancel, use `doOnCancel`, `doFinally`, or a resource-scoping operator.

### 7.4. Cancellation May Only Stop the Client Side

If upstream wraps a blocking API that ignores interrupts, cancellation may not stop the blocking work right away.

Similarly, if code called `subscribe()` to create a detached subscription, canceling the original request will not automatically cancel that detached subscription.

This is why detached subscriptions should not be created in controllers or services without an explicit lifecycle owner.

## 8. Managing Subscriptions and Avoiding Detached Work

### 8.1. Return Publishers to Callers

In WebFlux, controllers should return Publishers:

~~~java
@GetMapping("/{id}")
public Mono<Product> getProduct(@PathVariable String id) {
    return productService.findById(id);
}
~~~

When the client disconnects or a server-level request timeout triggers, the framework cancels the subscription and propagates the signal down the pipeline.

### 8.2. Avoid Subscribing Inside Services

Anti-pattern:

~~~java
public Mono<Product> save(Product product) {
    reactiveOperations.save(product).subscribe();
    return Mono.just(product);
}
~~~

The method returns before the save finishes. The caller cannot observe errors, wait for completion, or cancel the operation properly.

Correct approach:

~~~java
public Mono<Product> save(Product product) {
    return reactiveOperations.save(product);
}
~~~

If another step is needed after save:

~~~java
public Mono<Product> save(Product product) {
    return reactiveOperations.save(product)
        .flatMap(saved ->
            auditService.record(saved)
                .thenReturn(saved)
        );
}
~~~

All work stays within the same Publisher.

### 8.3. When Is Managing a Disposable Manually Appropriate?

An application-owned background subscription, such as a long-lived worker, may hold a `Disposable` to cancel during component shutdown.

In that case:

- Assign a clear owner.
- Store the subscription handle.
- Dispose when the owner's lifecycle ends.
- Monitor errors.
- Never spawn an untracked subscription per HTTP request.
- Never use `subscribe()` as a shortcut to avoid reactive composition.

Background workers should be managed by proper lifecycle components, schedulers, and durable queues.

## 9. Releasing Resources with doFinally

### 9.1. doFinally Receives Every Termination Type

`doFinally` runs when a sequence completes, errors, or is canceled:

~~~java
Mono<Product> result =
    reactiveOperations.findById(id, Product.class)
        .doFinally(signalType -> {
            metrics.recordTermination(signalType.name());
        });
~~~

`SignalType` can be `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`.

This is appropriate for lightweight synchronous cleanup such as recording metrics, releasing a permit, or updating counters.

### 9.2. doOnCancel Runs Only on Cancellation

~~~java
Flux<SearchHit<Product>> hits =
    reactiveOperations.search(query, Product.class)
        .doOnCancel(() ->
            log.debug("Search subscription cancelled")
        );
~~~

`doOnCancel` does not run on complete or error. If cleanup is required across all exit paths, use `doFinally`.

### 9.3. Cleanup Must Be Idempotent

Multiple code paths might attempt to release the same resource. Design cleanup so closing or releasing twice never throws errors or corrupts pools.

For example, with permits, guarantee each acquire pairs with exactly one release. When using `doFinally`, place it right after permit ownership begins and ensure the permit is not also released in another branch.

### 9.4. Do Not Use doFinally to Await Async Cleanup

`doFinally` accepts a synchronous callback and does not compose a cleanup Publisher. If you must call an asynchronous API to close a PIT, delete remote resources, or return a resource via a Publisher, `doFinally` will not wait for that work to complete.

Use `usingWhen` whenever asynchronous cleanup is a required part of the lifecycle.

## 10. Managing Resources with using and usingWhen

### 10.1. using for Synchronous Resources

`Mono.using`/`Flux.using` manages resources with synchronous cleanup:

~~~java
Mono<Result> result = Mono.using(
    resourceSupplier,
    resource -> performOperation(resource),
    resource -> resource.close()
);
~~~

The resource is created on subscription, passed into the closure, and cleaned up on termination or cancellation per operator semantics.

Use `using` for resources with synchronous `close()`, such as local handles. Never run heavy blocking cleanup on the event loop.

### 10.2. usingWhen for Asynchronous Cleanup

For resources opened and closed via Publishers, use `usingWhen`:

~~~java
Mono<SearchResult> result = Mono.usingWhen(
    openPointInTime(),
    pit -> searchWithPointInTime(pit),
    pit -> closePointInTime(pit),
    (pit, error) -> closePointInTime(pit),
    pit -> closePointInTime(pit)
);
~~~

The arguments handle, in order:

1. Resource supplier.
2. Work using the resource.
3. Cleanup on completion.
4. Cleanup on error.
5. Cleanup on cancellation.

`usingWhen` awaits the corresponding cleanup Publisher per lifecycle event. It is the right choice over `doFinally` when cleanup requires asynchronous I/O.

### 10.3. Cleanup Failures Must Also Be Observed

If the cleanup Publisher fails, the failure can affect the pipeline's terminal signal or mask the original error depending on operator behavior and termination path.

Decide:

- Should a cleanup failure fail the request?
- Should closing the resource be retried?
- Should metrics/alerts be emitted and resource IDs recorded for later cleanup?
- Can cleanup errors be ignored in certain scenarios?

If using `onErrorResume` inside cleanup to avoid masking the primary error, log and meter the cleanup failure before completing. Never silently swallow all close errors.

### 10.4. Resource Suppliers Must Create Resources per Subscription

Use cold Publishers to open resources upon subscription. Never open a resource eagerly while assembling a pipeline and share it across a Publisher that might be subscribed to multiple times.

~~~java
Mono<Result> operation =
    Mono.defer(() ->
        Mono.usingWhen(
            openResource(),
            resource -> useResource(resource),
            this::closeResource,
            (resource, error) -> closeResource(resource),
            this::closeResource
        )
    );
~~~

`Mono.defer` ensures each subscription creates a fresh lifecycle. This is especially critical when retrying or subscribing multiple times.

## 11. Examples with Elasticsearch Point in Time and Scroll

### 11.1. PIT Is a Resource That Must Be Closed

Point in Time (PIT) preserves a stable view of an index for multi-request pagination/searching. PIT has a keep-alive duration and consumes cluster resources.

When an application opens a PIT, runs paginated searches with it, and finishes, it should close the PIT once no longer needed.

~~~mermaid
flowchart TD
    A[Subscribe] --> B[Open PIT]
    B --> C[Search pages using PIT]
    C --> D{Complete, error or cancel}
    D -->|Complete| E[Close PIT]
    D -->|Error| E
    D -->|Cancel| E
    E --> F[Finish]
~~~

### 11.2. Wrapping PIT in usingWhen

Conceptual example:

~~~java
Mono<List<SearchHit<Product>>> searchAllPages() {
    return Mono.usingWhen(
        openPit(),
        pit -> fetchPages(pit).collectList(),
        this::closePit,
        (pit, error) -> closePit(pit),
        this::closePit
    );
}
~~~

`openPit`, `fetchPages`, and `closePit` here are Publisher-returning adapters around your Elasticsearch client's PIT API. Exact signatures depend on your Java API Client and Spring Data Elasticsearch versions.

If paging times out or the subscriber cancels, the cleanup path still executes to close the PIT. Keep-alive should still be set appropriately because a process can crash before cleanup runs.

### 11.3. Scroll Contexts Must Also Be Released

The Scroll API retains a search context across page fetches. When finished or when data is no longer needed, the application must clear the scroll context via the corresponding API.

Never leave scroll contexts open indefinitely just because a client stopped reading. Bind the scroll lifecycle to a resource-scoped Publisher and provide cleanup if the process crashes or requests are canceled.

### 11.4. Do Not Open PIT/Scroll for Small Queries

PIT/scroll is useful when scanning large datasets or needing snapshot semantics. For ordinary queries returning a single page of results, avoid creating unnecessary server-side state.

Use PIT/scroll with bounded keep-alive, concurrency caps on active sessions, and explicit cleanup.

### 11.5. Cleanup Does Not Replace Keep-Alive

`usingWhen` handles cleanup when the pipeline terminates normally, fails, or is canceled. It cannot run if the process is killed, power fails, or the JVM crashes.

Keep-alive serves as a safety net allowing the server to reclaim resources after a period of inactivity. Choose a keep-alive long enough for gaps between pages, yet short enough not to hold resources unnecessarily.

## 12. Schedulers and Blocking Operations

### 12.1. Do Not Block the Event Loop

Reactive Elasticsearch clients generally rely on asynchronous I/O. Callbacks or operators running on an event loop must finish quickly.

Never invoke:

- `Thread.sleep`.
- `block()`.
- Blocking file I/O.
- Blocking JDBC.
- Blocking HTTP clients.
- Long-held locks.

A single blocking call can stall many requests sharing the same event loop.

### 12.2. Wrapping Unavoidable Blocking Work

If calling a blocking library is unavoidable, isolate it on the bounded elastic scheduler:

~~~java
Mono<LegacyResult> result =
    Mono.fromCallable(() -> legacyBlockingClient.call())
        .subscribeOn(Schedulers.boundedElastic());
~~~

This is a compatibility measure for specific blocking segments. Prefer reactive/non-blocking APIs whenever available.

Do not shift an entire Elasticsearch pipeline onto boundedElastic merely to hide one blocking callback. That reduces observability and can bottleneck the scheduler itself.

### 12.3. Never Create a New Scheduler per Request

Schedulers are shared resources. Creating a scheduler per request without disposing it leaks threads and resources.

Use Reactor's standard schedulers or an application-managed scheduler with a clear lifecycle. If creating custom schedulers, dispose them on component/application shutdown.

## 13. Retries and Cancellation in Multi-Step Pipelines

### 13.1. Retry Placement Determines What Re-Executes

~~~java
Mono<Product> result =
    loadProduct(id)
        .flatMap(this::enrich)
        .flatMap(reactiveOperations::save)
        .retryWhen(retryPolicy);
~~~

Placing retry at the end of the chain resubscribes to the entire chain, meaning `loadProduct`, `enrich`, and `save` all re-run.

To retry only the save call, place retry tightly around save:

~~~java
Mono<Product> result =
    loadProduct(id)
        .flatMap(this::enrich)
        .flatMap(product ->
            Mono.defer(() -> reactiveOperations.save(product))
                .retryWhen(retryPolicy)
        );
~~~

However, if save fails due to stale data or a conflict, retrying save alone with the same entity may be wrong. Retry boundaries must match units of work that are safe to re-execute.

### 13.2. Cancellation Stops Pending Retries

If a subscriber cancels while `retryWhen` is waiting in backoff, the retry sequence stops and schedules no further attempts.

Never spawn detached scheduler tasks for retries outside the subscription lifecycle. Keep retry policies inside the Publisher or manage dedicated tasks with a disposable owner.

### 13.3. Side Effects Before Retry Can Execute Multiple Times

~~~java
source
    .doOnNext(this::sendNotification)
    .retryWhen(retryPolicy);
~~~

If an error occurs after `sendNotification`, resubscribing can trigger the notification again.

Move side effects outside the retry boundary, make them idempotent, or use event IDs/outbox patterns to deduplicate.

### 13.4. Retries and Timeouts Can Amplify Load

Timeouts tell the client an attempt took too long. If the server is still processing it, retrying can send duplicate requests while earlier ones remain running.

This creates overlapping attempts. Apply these safeguards:

- Set per-attempt timeouts aligned with realistic latency.
- Enforce concurrency limits.
- Make writes idempotent.
- Monitor in-flight request counts.
- Curb retries when the cluster is overloaded.

## 14. Error Handling and Fallbacks

### 14.1. onErrorMap to Standardize Errors

~~~java
Mono<Product> result =
    reactiveOperations.findById(id, Product.class)
        .onErrorMap(
            error -> isTransportFailure(error),
            error -> new ElasticsearchUnavailableException(
                "Could not read product",
                error
            )
        );
~~~

Map only appropriate error categories. Preserve the original cause for logging and diagnostics.

### 14.2. onErrorResume for Intentional Fallbacks

~~~java
Mono<Product> result =
    reactiveOperations.findById(id, Product.class)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(
            ElasticsearchUnavailableException.class,
            error -> cache.findById(id)
        );
~~~

A fallback may serve cached data, provided freshness and business semantics allow it. Never serve stale cache entries for workflows requiring strict consistency.

### 14.3. Empty Differs from Error

`Mono.empty()` signifies no element; it does not mean timeout or Elasticsearch unavailable.

Distinguish:

- Document not found: may be empty.
- Timeout: error.
- Connection failure: error.
- Subscriber cancel: cancellation.
- Partial search response: response containing metadata to inspect.

Turning every failure into empty prevents callers from distinguishing missing data from outages.

## 15. Integrating Timeouts and Retries with Spring Data Elasticsearch

### 15.1. ReactiveElasticsearchOperations

A service can wrap Spring Data operations with policies:

~~~java
@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Mono<Product> findById(String id) {
        return operations.get(id, Product.class)
            .timeout(Duration.ofSeconds(2))
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                    .maxBackoff(Duration.ofSeconds(1))
                    .jitter(0.5)
                    .filter(this::isRetryable)
            );
    }

    private boolean isRetryable(Throwable error) {
        return error instanceof TimeoutException
            || isTransientElasticsearchFailure(error);
    }
}
~~~

Method names and overloads on `ReactiveElasticsearchOperations` can vary across releases. Use the APIs matching your project's dependencies. This example highlights Reactor operator placement.

### 15.2. Reactive Repositories

The same principles apply to reactive repositories:

~~~java
public Mono<Product> load(String id) {
    return repository.findById(id)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(retryPolicy);
}
~~~

Share retry policies in a controlled manner instead of duplicating divergent predicates and retry counts across methods.

### 15.3. Transport/Client Timeouts Still Need Separate Configuration

Reactor timeouts do not replace:

- Connect timeout.
- Connection pool acquisition timeout.
- Response/socket timeout.
- TLS/network timeouts.
- Elasticsearch search timeout.

Transport configuration depends on the reactive client implementation and version. Inspect how Spring Data Elasticsearch builds its reactive client in your project version and configure the underlying HTTP transport accordingly.

Never set every timeout to the exact same value without considering their relationships. Usually, application-level request timeouts should accommodate necessary child timeouts, and overall deadlines must cover retries/backoff within the SLA.

### 15.4. Do Not Close the Client After Each Operation

The reactive Elasticsearch client, connection pool, and template are normally application-scoped beans. Spring manages their lifecycles.

Never call close/dispose on the client after each search or save. Only close per-operation resources such as PIT/scroll, or custom schedulers/clients owned by a specific component.

## 16. Testing Timeouts and Retries

### 16.1. Using StepVerifier with Virtual Time

You do not need to wait real seconds to test backoff delays. Reactor Test supports virtual time:

~~~java
@Test
void retriesTransientFailureWithBackoff() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> operation = Mono.defer(() -> {
        if (attempts.incrementAndGet() < 3) {
            return Mono.error(new TransientFailure());
        }
        return Mono.just("ok");
    }).retryWhen(
        Retry.backoff(2, Duration.ofSeconds(1))
            .jitter(0d)
    );

    StepVerifier.withVirtualTime(() -> operation)
        .thenAwait(Duration.ofSeconds(3))
        .expectNext("ok")
        .verifyComplete();

    assertThat(attempts).hasValue(3);
}
~~~

With virtual time, construct the Publisher inside the `withVirtualTime` supplier in complex tests so operators pick up the virtual scheduler rather than an eagerly captured real scheduler.

### 16.2. Testing Timeouts

~~~java
@Test
void timesOutSlowPublisher() {
    StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(5))
    )
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
}
~~~

This test verifies the timeout signal. Separate integration tests should confirm whether real requests cancel at the transport layer as supported by the client.

### 16.3. Testing Cancellation

~~~java
@Test
void observesCancellation() {
    AtomicReference<SignalType> termination =
        new AtomicReference<>();

    Flux<Long> source = Flux.interval(Duration.ofSeconds(1))
        .doFinally(termination::set);

    StepVerifier.withVirtualTime(() -> source)
        .thenAwait(Duration.ofSeconds(2))
        .thenCancel()
        .verify();

    assertThat(termination.get()).isEqualTo(SignalType.CANCEL);
}
~~~

This test verifies `doFinally` observes cancellation. It does not prove Elasticsearch canceled an in-flight write on the server.

### 16.4. Testing Cleanup for Asynchronous Resources

Use `usingWhen` and a mock resource tracking its close signal:

~~~java
@Test
void closesResourceOnCancellation() {
    AtomicBoolean closed = new AtomicBoolean();

    Mono<String> operation = Mono.usingWhen(
        Mono.just("pit-id"),
        pit -> Mono.<String>never(),
        pit -> Mono.fromRunnable(() -> closed.set(true)),
        (pit, error) -> Mono.fromRunnable(() -> closed.set(true)),
        pit -> Mono.fromRunnable(() -> closed.set(true))
    );

    StepVerifier.create(operation)
        .thenCancel()
        .verify();

    assertThat(closed).isTrue();
}
~~~

In real tests, if cleanup is asynchronous, assert completion of the cleanup Publisher and verify cleanup error handling separately.

### 16.5. Testing That Retries Do Not Repeat Side Effects

Create counters for call attempts and side effects. Force the first attempt to fail after the side effect, and verify retries do not emit duplicate notifications or that deduplication works.

This test is crucial for notifications, audit events, and update scripts.

### 16.6. Integration Testing with Real Elasticsearch

Use a compatible Elasticsearch test instance to verify:

- Slow requests or transport disconnects.
- Reactor-layer timeouts.
- Controlled retries for transient errors.
- Bulk partial failures.
- Cancellation of search streams.
- PIT/scroll cleanup.
- Client shutdown.
- Partial responses or `timed_out`.

Do not rely solely on mocking `Mono.error`; mocks do not exercise connection pools, transport cancellation, or server-side request processing.

## 17. Monitoring and Operations

### 17.1. Key Metrics to Track

Monitor:

- Request counts and success/error rates.
- Timeout counts by layer.
- Retry counts by error type.
- Average attempts per operation.
- Actual retry delays.
- Cancellation counts.
- In-flight request counts.
- Connection pool active/pending/idle counts.
- Search latency p50/p95/p99.
- Bulk latency and rejected items.
- Open PIT/scroll contexts and their ages.
- Cleanup successes and failures.
- Scheduler queues and thread utilization.

Use low-cardinality labels. Never attach arbitrary document IDs or request IDs as metric tags.

### 17.2. Distinguishing Application Timeouts from Elasticsearch Timeouts

Logs should clearly distinguish timeouts originating from:

- Transport connect/acquisition/response timeouts.
- Elasticsearch server-side search execution timeout.
- Reactor per-attempt timeout.
- Overall application deadline.
- Upstream HTTP request timeout.

Simply logging "Elasticsearch timeout" makes it hard to identify which layer needs tuning.

### 17.3. Alerting on Resource Leaks

Watch for:

- Unclosed PIT/scroll contexts.
- Rising connection pool pending counts.
- Active connections failing to drop after load subsides.
- Scheduler thread counts growing over time.
- Backlogged retry queues.
- Cleanup failures.
- Requests continuing after caller cancellation.

A single cleanup failure might be noise; an upward trend signals a leak worth investigating.

## 18. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| API breaches SLA despite per-attempt timeouts | Bounded only per attempt without an overall deadline | Add an outer timeout wrapping the retry chain |
| Retries do not fire after timeout | Timeout placed outside retry or predicate excludes TimeoutException | Check operator order and retry predicate |
| Retries run on mapping errors | Unconditional retry configured | Classify error types |
| Write executes twice | Timeout fired after server already received request | Use idempotent operations and stable document IDs |
| Client disconnects yet work continues | Detached subscribe or upstream lacks cancellation support | Compose Publishers and manage subscriptions |
| onErrorResume skips on client cancel | Cancellation is not an error | Use doOnCancel/doFinally or usingWhen |
| PIT lingers after search stops | Missing cleanup on cancel/error | Manage via usingWhen and keep-alive |
| Cleanup unfinished when method returns | Used doFinally for async cleanup | Use usingWhen |
| Event loop stalls | block, sleep, or blocking I/O | Use non-blocking APIs or isolate blocking work |
| Connection pool pending rises | Too many in-flight requests or unclosed responses/resources | Cap concurrency and inspect lifecycles |
| Retries keep running after overall deadline | Timeout placed inside the wrong retry boundary | Put overall timeout outermost |
| Fallbacks hide infrastructure outages | Converted every error to empty | Fall back only on approved error categories |
| Auditing/side effects run multiple times | Retries or multiple subscriptions | Design idempotency and control subscriptions |
| Resources leak on JVM crash | Reactive cleanup cannot run when process dies | Keep-alive, TTLs, and reconciliation jobs |

## 19. Workflow for Designing a Reactive Operation

When building a reactive operation with Spring Data Elasticsearch:

1. Choose `ReactiveElasticsearchOperations` or a reactive repository and preserve Publishers across the service flow.
2. Define transport timeouts, server-side timeouts, and Reactor timeouts separately.
3. Set a per-attempt timeout on the request.
4. Set an overall deadline wrapping the retry/fallback chain.
5. Retry only classified transient failures.
6. Use backoff, jitter, and a cap on attempts.
7. Confirm whether writes are idempotent before enabling retries.
8. For bulk operations, handle partial failures per item.
9. Return Publishers for the framework/caller to manage; avoid detached subscribes.
10. Allow cancellation to propagate upstream and never treat cancellation as rollback.
11. Use doFinally for lightweight synchronous cleanup and usingWhen for asynchronous cleanup.
12. Close PIT/scroll or custom resources across complete, error, and cancel paths.
13. Never close Spring-managed clients or pools after individual requests.
14. Test timeouts, retries, cancellation, cleanup, and side effects using StepVerifier.
15. Integration test transport/server behavior and monitor metrics in production.

## 20. Key Takeaways

- Timeouts span multiple layers: connect, connection pool acquisition, response/socket, Elasticsearch search timeout, and Reactor timeout.
- `Mono.timeout` emits a timeout error and cancels upstream; it does not roll back operations already received by Elasticsearch.
- For `Flux`, inter-signal timeout differs from an overall stream deadline.
- Place timeout before retry to bound individual attempts; place timeout outermost to bound the whole operation.
- `retryWhen` resubscribes to the source Publisher; every step inside the retry boundary can run again.
- Retry only transient failures; mapping, validation, and authorization errors require fixing the root cause.
- Retrying writes requires idempotency, stable IDs, or deduplication.
- Bulk responses can report failed items while the Publisher completes normally; inspect individual item statuses.
- Cancellation is a distinct signal, neither an error nor a rollback.
- Never call `subscribe()` or `block()` inside reactive services or callbacks.
- `doFinally` suits lightweight synchronous cleanup across complete/error/cancel.
- `usingWhen` suits resources requiring asynchronous, composed cleanup.
- PIT and scroll contexts must be closed; keep-alive limits exposure if the process crashes before cleanup.
- Never close Spring-managed reactive clients or connection pools after each operation.
- Use StepVerifier/virtual time to test timeouts, retries, and cancellation; use integration tests to verify real transport behavior.
- Monitor per-layer timeouts, retries, cancellations, connection pools, and resource cleanup.

Timeouts, retries, cancellation, and cleanup form a unified lifecycle for reactive operations. By placing retry boundaries carefully, enforcing overall deadlines, propagating cancellation through pipelines, and tying resources to `usingWhen`, Spring Data Elasticsearch applications can handle transient failures while controlling load and releasing resources cleanly when work ends.
