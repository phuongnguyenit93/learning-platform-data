# Differences Between Synchronous and Reactive Callbacks

Spring Data Elasticsearch provides callbacks to intervene in the entity lifecycle when the application reads, writes, and converts data. Callbacks can normalize entities before saving, populate metadata, modify a `Document` after mapping, or process entities after reading.

When using the imperative stack, a callback returns the processed value directly. When using the reactive stack, a callback returns a `Publisher` so its work is composed into the Reactor pipeline. Both callback styles serve similar goals but differ in return contracts, execution timing, error handling, and how request context is accessed.

Understanding these differences helps avoid bugs such as blocking the event loop with synchronous operations, calling `subscribe` inside a callback, losing user identity across thread switches, or unintentionally repeating side effects when a reactive sequence is retried or re-subscribed.

## 1. What Are Callbacks in Spring Data Elasticsearch?

### 1.1. Callbacks Intervene in the Entity Lifecycle

Spring Data Elasticsearch maps Java entities to `Document` instances to send to Elasticsearch and converts `Document` instances back to entities when reading. Callbacks allow the application to execute logic at defined points in that process.

Common use cases:

- Normalizing data before conversion.
- Generating slugs, canonical codes, or search values.
- Populating audit information such as created date, modified date, and auditor.
- Adjusting the `Document` after mapping.
- Populating defaults upon reading.
- Recording metrics or traces for lifecycle operations.

Callbacks are part of the Spring Data mapping/operations lifecycle. They are not a general mechanism for intercepting every Elasticsearch request.

If the application calls the Elasticsearch Java API Client directly, bypassing Spring Data `ElasticsearchOperations`/repositories, Spring Data's entity lifecycle callbacks are not invoked automatically.

### 1.2. Two Execution Models

Spring Data provides imperative and reactive APIs:

| Stack | Common Operations API | Callback Model | Callback Result |
|---|---|---|---|
| Imperative | `ElasticsearchOperations`, `ElasticsearchTemplate`, `ElasticsearchRepository` | `EntityCallbacks` and synchronous callbacks | Returns entity/`Document` directly |
| Reactive | `ReactiveElasticsearchOperations`, `ReactiveElasticsearchTemplate`, `ReactiveElasticsearchRepository` | `ReactiveEntityCallbacks` and reactive callbacks | Returns `Publisher` |

With the imperative stack, methods typically finish their work before returning a result. Callbacks run on the synchronous execution flow of that operation.

With the reactive stack, methods typically return `Mono` or `Flux`. The pipeline executes upon subscription. Reactive callbacks return a `Publisher`, allowing Spring Data to chain callback logic into the same pipeline.

### 1.3. Do Not Confuse Entity Callbacks with HTTP Client Callbacks

An application may contain several kinds of callbacks:

- Spring Data entity lifecycle callbacks.
- Bulk response listeners.
- Elasticsearch Java API Client callbacks.
- Reactor operators like `doOnNext` and `doOnError`.
- Spring Application Event listeners.

They differ in position and semantics. This lesson focuses on callbacks tied to the entity lifecycle in Spring Data Elasticsearch. Bulk API listeners or Reactor operators do not automatically replace those callbacks.

## 2. Callback Points in the Lifecycle

### 2.1. Entity Write Flow

A typical write flow includes these checkpoints:

~~~mermaid
flowchart TD
    A[Application submits entity] --> B[BeforeConvert callback]
    B --> C[Convert entity to Document]
    C --> D[BeforeSave callback]
    D --> E[Send write request to Elasticsearch]
    E --> F[AfterSave callback]
    F --> G[Return result]
~~~

Concrete callbacks can be provided for either the imperative or reactive stack. The lifecycle meaning corresponds directly:

| Callback | Timing | Purpose |
|---|---|---|
| `BeforeConvertCallback` | Before the entity is converted into a `Document` | Normalize entity, populate values before mapping |
| `BeforeSaveCallback` | After mapping, before sending the write request | Adjust the entity or generated `Document` |
| `AfterSaveCallback` | After the save operation | Process post-write result, record metrics, or prepare returned result |

`BeforeConvert` suits changes belonging to the entity model. `BeforeSave` suits inspecting or altering the generated `Document`. `AfterSave` runs after the write operation, so side effects here must be designed carefully.

### 2.2. Entity Read Flow

The read flow can include these checkpoints:

~~~mermaid
flowchart TD
    A[Search/get request] --> B[Elasticsearch returns Document]
    B --> C[AfterLoad callback]
    C --> D[Convert Document to entity]
    D --> E[AfterConvert callback]
    E --> F[Return entity]
~~~

| Callback | Timing | Purpose |
|---|---|---|
| `AfterLoadCallback` | After `Document` is loaded, before converting | Adjust `Document` data prior to mapping |
| `AfterConvertCallback` | After `Document` is converted into an entity | Enrich entity or apply post-mapping logic |

Read callbacks are not an appropriate place to write back to Elasticsearch for every entity. Doing so easily creates loops or generates unexpected request volume.

### 2.3. Callback Order and Effective Order

Callbacks are invoked at their respective lifecycle checkpoints. If there are multiple callbacks of the same kind, order can be controlled using the ordering mechanism supported by your Spring Data version, such as `Ordered` or `@Order`.

Do not rely on arbitrary bean scan order. If callback B needs data produced by callback A, declare the order explicitly and test that order.

A callback can also return a new entity instead of mutating the existing object. When using immutable objects, make sure to return the modified instance so the pipeline continues with that data.

## 3. Synchronous Callbacks

### 3.1. Direct Return Contract

An imperative callback processes the entity and returns the result immediately inside the method. Example `BeforeConvertCallback`:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductBeforeConvert
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        if (entity.getName() != null) {
            entity.setNormalizedName(
                entity.getName().trim().toLowerCase()
            );
        }

        return entity;
    }
}
~~~

This is a synchronous callback: the method takes an entity, processes it, and returns an entity. There is no `Mono`, `Flux`, or `Publisher` in the contract.

Verify exact package names and interface signatures against your Spring Data Elasticsearch version. The example above illustrates common imperative lifecycle callback APIs.

### 3.2. Synchronous Callbacks Run on the Current Call Path

When the application calls an imperative operation, the callback executes as part of that operation. A slow callback slows down the calling save/read operation itself.

~~~java
Product saved = operations.save(product);
~~~

Before `save` returns, the corresponding imperative callbacks execute according to the lifecycle. If a callback makes a blocking HTTP call taking 2 seconds, the application's `save` operation also waits 2 seconds.

Avoid placing slow network calls or heavy I/O inside synchronous callbacks if they belong in a more appropriate service layer.

### 3.3. Suited for Fast, Deterministic Logic

Synchronous callbacks are well suited for:

- String normalization.
- Computing lightweight derived values.
- Simple invariant checks.
- Populating metadata from data already present on the entity.
- Mapping or adjusting `Document`.
- Recording lightweight metrics.

If a callback needs to query another database, call a remote service, or wait on an asynchronous resource, reconsider where that logic lives. A synchronous callback does not become non-blocking simply by being declared as a Spring bean.

### 3.4. Errors in Synchronous Callbacks

If a callback throws an exception, the Spring Data operation may fail and propagate the exception to the caller. For pre-save callbacks, the write request may not have been sent yet. For post-save callbacks, data may already have been written successfully before the callback threw.

This creates an important distinction:

- `BeforeConvert`/`BeforeSave` errors: typically occur before the write.
- `AfterSave` errors: the write may have completed, yet the caller still receives an exception.

Do not assume every exception from `save()` guarantees Elasticsearch did not persist the document. For post-write errors, design retries around idempotency and verify actual state when business logic requires it.

## 4. Reactive Callbacks

### 4.1. Publisher Return Contract

A reactive callback does not return an entity directly. It returns a `Publisher` so Spring Data can compose it into the reactive pipeline.

~~~java
import org.reactivestreams.Publisher;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveProductBeforeConvert
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Publisher<Product> onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        return Mono.fromSupplier(() -> {
            if (entity.getName() != null) {
                entity.setNormalizedName(
                    entity.getName().trim().toLowerCase()
                );
            }

            return entity;
        });
    }
}
~~~

The callback returns `Publisher<Product>`. You can return `Mono<Product>` because `Mono` implements Reactive Streams `Publisher`.

Exact interface names, packages, and signatures can change across release trains. Confirm your dependency version before copying code into a project.

### 4.2. Reactive Callbacks Execute on Subscription

Reactive sequences are usually lazy. Calling a method that builds a `Mono` does not mean the callback has already executed.

~~~java
Mono<Product> result = reactiveOperations.save(product);
~~~

At this point, the application holds a pipeline describing the work. Execution is triggered when subscribed. In reactive web applications, the framework typically manages subscriptions. Services and controllers should return `Mono` or `Flux` to the calling layer rather than subscribing internally.

If a callback performs side effects eagerly when the method is called instead of inside the `Publisher`, those side effects may execute before subscription and violate the expected reactive lifecycle.

### 4.3. Use Mono.defer When Deferring Publisher Creation or Reading Context

`Mono.defer` creates a fresh `Publisher` upon subscription:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    return Mono.defer(() -> {
        normalize(entity);
        return Mono.just(entity);
    });
}
~~~

This is useful when logic must execute at subscription time. If only computing a synchronous value, `Mono.fromSupplier` can also work well.

There is no need to wrap every trivial calculation in its own scheduler. Keep the pipeline simple and only switch schedulers for a clear reason.

### 4.4. Do Not Call block or subscribe Inside a Reactive Callback

Anti-patterns:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    // Avoid: blocks the reactive pipeline.
    Product normalized = remoteService.normalize(entity).block();

    return Mono.just(normalized);
}
~~~

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    // Avoid: creates a subscription detached from the lifecycle.
    remoteService.audit(entity).subscribe();

    return Mono.just(entity);
}
~~~

`block()` can block the thread running the pipeline and fail when executed on a non-blocking Reactor thread. Calling `subscribe()` inside a callback creates a detached execution flow: errors, cancellation, and completion timing of the side effect are disconnected from the save operation.

Compose the `Publisher` instead:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    return remoteService.normalize(entity)
        .map(normalized -> {
            entity.setNormalizedName(normalized);
            return entity;
        });
}
~~~

When the `Publisher` is composed, errors and cancellation propagate cleanly through the same pipeline.

### 4.5. Reactive Does Not Automatically Mean Running on a Background Thread

A reactive callback may run on the subscribing thread or on a thread determined by upstream/downstream schedulers. Reactor does not automatically spawn a new thread for each callback.

- `subscribeOn` affects the scheduler where subscription/upstream executes.
- `publishOn` switches processing for subsequent downstream operators to the chosen scheduler.
- Without scheduler switches, the pipeline may continue on the current thread.

Do not assume reactive callbacks always execute on a dedicated thread. Also do not use `publishOn(boundedElastic())` to hide blocking operations everywhere; choose schedulers based on the nature of the work and prefer non-blocking APIs.

## 5. Comparing Synchronous and Reactive

### 5.1. Comparison Table

| Criterion | Synchronous Callback | Reactive Callback |
|---|---|---|
| Interface | `BeforeConvertCallback<T>` and corresponding imperative callbacks | `ReactiveBeforeConvertCallback<T>` and corresponding reactive callbacks |
| Return Value | Entity or `Document` directly | `Publisher<T>`/`Publisher<Document>` |
| Execution Timing | During the imperative operations call | When the reactive pipeline is subscribed and passes through the callback |
| Thread | Execution thread of the imperative operation | Thread determined by pipeline subscription and schedulers |
| Asynchronous I/O | No async composition in the contract | Can compose `Mono`/`Flux` |
| Blocking | Can block, though it slows the operation | Should not block event-loop or pipeline threads |
| Error | Exceptions propagate via imperative calls | Error signals propagate through the `Publisher` |
| Cancellation | Typically no Reactive Streams cancellation signal | Can propagate cancellation through the pipeline |
| Context | Usually relies on call context/`ThreadLocal` | Can use Reactor Context; `ThreadLocal` is not inherently safe across thread switches |
| Testing | Call callback and assert result/exception | Use `StepVerifier` and verify subscription/context |

### 5.2. Choose Callbacks Matching Your Application Stack

If the application uses `ElasticsearchOperations` and imperative repositories, use imperative callbacks. If the application uses `ReactiveElasticsearchOperations` or reactive repositories, use the corresponding reactive callbacks.

Do not force synchronous callbacks into a reactive pipeline just because the code looks simpler, especially when callbacks perform I/O. Conversely, do not rewrite an entire application as reactive merely to use one callback; choose your stack based on overall architecture.

### 5.3. Do Not Mix Both Models Accidentally

A single class should not try to implement both imperative and reactive callbacks with the same logical name if doing so could cause an operation to run twice or make ordering ambiguous.

If an application genuinely uses both stacks, separate adapters or implementations per model. Shared pure business logic can be extracted into a small helper service, while each adapter translates to the appropriate return contract.

## 6. Common Lifecycle Callbacks

### 6.1. Pre-Conversion Callbacks

`BeforeConvertCallback` and its reactive counterpart are suited for modifying entities before Spring Data constructs a `Document`.

Examples:

- Trimming and normalizing names.
- Generating slugs.
- Populating default values.
- Attaching source metadata.
- Preparing fields used for search.

Do not use this callback to call `save` on the same entity through the same repository. That can cause a callback loop.

### 6.2. Pre-Save Callbacks

`BeforeSaveCallback` runs after the entity has been converted into a `Document` and before data is written. This callback fits when logic needs both the entity and the mapped representation.

For example, adding a technical field to the `Document` or checking mapped output. When modifying `Document`, ensure changes remain compatible with the mapping and do not accidentally overwrite fields created by the converter.

### 6.3. Post-Save Callbacks

`AfterSaveCallback` runs after the save operation completes. It can be used to record metrics or prepare returned data.

If the callback calls an external system, remember that the Elasticsearch write may already have succeeded even if the callback fails. For critical side effects such as sending messages or mandatory audit records, consider an outbox or durable process instead of relying on a single post-save callback.

### 6.4. Post-Load and Post-Convert Callbacks

`AfterLoadCallback` receives the `Document` after loading. `AfterConvertCallback` receives the entity after conversion.

Use them for essential, deterministic read logic. Avoid making network calls per entity inside a large `Flux` when you can batch or load data in the service layer; per-entity calls can cause N+1 requests and degrade read throughput.

### 6.5. Corresponding Reactive Callbacks

The reactive stack provides corresponding lifecycle callbacks, typically prefixed with `Reactive`, such as:

- `ReactiveBeforeConvertCallback<T>`.
- `ReactiveBeforeSaveCallback<T>`.
- `ReactiveAfterSaveCallback<T>`.
- `ReactiveAfterLoadCallback<T>`.
- `ReactiveAfterConvertCallback<T>`.

Confirm the interface list and signatures for your release train. Callbacks accepting entities usually return a `Publisher` of the entity; callbacks operating on `Document` return a `Publisher` of `Document`.

## 7. Auditing and Callbacks

### 7.1. Auditing Is a Lifecycle Callback Use Case

Auditing automatically populates creation and modification timestamps and actors on an entity. Common annotations:

~~~java
@CreatedDate
private Instant createdDate;

@LastModifiedDate
private Instant lastModifiedDate;

@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
~~~

Auditing executes at the appropriate lifecycle checkpoint before the entity is converted/saved. Thus, the application does not need to repeat timestamp and user assignment across every service method.

### 7.2. AuditorAware for the Imperative Stack

In an imperative application, `AuditorAware<T>` supplies the current user:

~~~java
@Component
public class SpringSecurityAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.ofNullable(
            SecurityContextHolder.getContext()
                .getAuthentication()
        )
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
    }
}
~~~

This example uses imperative Spring Security. If the application has no authentication or runs background jobs, explicitly define a system auditor or return `Optional.empty()` according to business rules.

Enabling configuration and referencing `AuditorAware` depend on the Spring Data Elasticsearch version. Use the annotations/configuration supported by your release train's documentation.

### 7.3. ReactiveAuditorAware for the Reactive Stack

Reactive applications should retrieve the auditor from the reactive security context or Reactor Context rather than relying on `ThreadLocal`-based `SecurityContextHolder`.

Conceptual example with reactive Spring Security:

~~~java
@Component
public class ReactiveSecurityAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
    }
}
~~~

`ReactiveAuditorAware<T>` returns `Mono<T>`. When no auditor exists, the `Publisher` can complete empty per the contract. Do not call `block()` to turn it into an `Optional` in a reactive path.

Reactive auditing configuration must match the Spring Data Elasticsearch version in use. Some releases use a shared auditing configuration that detects `ReactiveAuditorAware`; verify the documentation rather than assuming annotations are identical across all releases.

### 7.4. Why Can ThreadLocal Lose the Auditor in Reactive Flows?

Reactive pipelines can switch threads when using schedulers. `ThreadLocal` binds data to the current thread, not to the subscription. When a pipeline hops to another thread, `SecurityContextHolder` or `MDC` may no longer hold the expected data unless proper context propagation is configured.

Reactor Context travels with the subscription and is the right place to carry contextual data in reactive flows. With reactive Spring Security, use `ReactiveSecurityContextHolder`.

Do not copy user IDs from requests into a static field or shared `ThreadLocal`; doing so can leak auditors across concurrent requests.

### 7.5. Distinguishing Created and Modified Metadata

Normally:

- `CreatedDate` and `CreatedBy` describe initial creation.
- `LastModifiedDate` and `LastModifiedBy` describe the most recent update.

Do not overwrite created metadata on each update if you want to retain original creation history. Test auditing behavior in your version and for your persistence patterns, especially when the application pre-populates values or uses direct update scripts.

Auditing entity callbacks only apply when operations flow through Spring Data's callback-triggering mechanisms. Low-level client updates or direct scripts may bypass the auditing lifecycle.

## 8. Side Effects, Transactions, and Repeatability

### 8.1. Callbacks Are Not Transaction Boundaries

Do not assume entity callbacks establish a transaction spanning Elasticsearch and external systems. Elasticsearch does not join an ACID distributed transaction with a database or message broker merely because a callback runs during `save`.

If a callback writes to another database and the Elasticsearch save subsequently fails—or vice versa—the application can be left in a partial state.

For workflows needing cross-system consistency, use an outbox, saga, or reconcilable process instead of relying on callbacks for cross-service transactions.

### 8.2. Callbacks Can Run More Than Once

Reactive `Publisher` instances can be re-subscribed. Retry operators can also re-execute parts of a pipeline. Applications or frameworks may re-run operations after errors.

Therefore, callbacks should:

- Prefer pure, deterministic logic.
- Avoid generating new random IDs on every invocation if IDs must be stable.
- Make side effects idempotent.
- Never assume a callback executes strictly once.
- Include a correlation ID or operation ID when deduplication is needed.

In particular, `AfterSaveCallback` may run after a successful write; if the callback sends a notification and fails, retrying the entire save may send the notification again.

### 8.3. Avoid Recursive Repository Calls

For instance, a `BeforeSave` callback calling a repository to update the same entity can trigger that same callback again. This easily causes recursion, extra requests, or logical deadlocks.

If other data must be synchronized, move orchestration into the service layer or intentionally use a lower-level API with explicit lifecycle control.

### 8.4. Do Not Use Callbacks to Replace the Service Layer

Callbacks should hold logic directly tied to the mapping/persistence lifecycle. Coarse business rules, multi-aggregate calls, authorization checks, orchestration, or multi-message publishing belong in application services.

Putting too much logic inside callbacks gives repository calls hidden side effects and makes testing harder.

## 9. Error Handling in Both Models

### 9.1. Imperative Callbacks

With synchronous callbacks, exceptions normally propagate directly out of the operation method:

~~~java
try {
    operations.save(product);
} catch (RuntimeException error) {
    // Log and handle the error at the service layer.
    throw error;
}
~~~

Do not swallow exceptions in a callback and return the entity as if nothing went wrong when data failed to normalize or an invariant was violated.

### 9.2. Reactive Callbacks

With reactive callbacks, errors are represented as error signals:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    return validateAsync(entity)
        .thenReturn(entity);
}
~~~

Errors can be handled in the service layer with `onErrorMap`, `onErrorResume`, or conditional retries. Do not turn every error into `Mono.empty()` if that silently skips the save operation or drops data.

### 9.3. Distinguishing Pre-Persistence and Post-Persistence Errors

| Error Point | Has the Write Possibly Happened? | How to Handle |
|---|---|---|
| `BeforeConvert` | Usually not yet | Fix data or callback logic |
| `BeforeSave` | Usually not yet | Check `Document` and mapping |
| Elasticsearch request | Possibly not yet, partial, or processed with lost response | Handle timeout/retry using idempotency |
| `AfterSave` | May already have succeeded | Inspect write state; deduplicate side effects |
| `AfterLoad`/`AfterConvert` | Read already occurred | Handle conversion errors or input data |

This is a mental model; exact exceptions and commit timing depend on the operation, client, and version. Do not deduce persistence state solely from the exception class.

## 10. Registering Callbacks and Ordering

### 10.1. Registering Callbacks as Spring Beans

A callback is typically discovered via bean registration:

~~~java
@Component
public class ProductBeforeConvert
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {
        // Lifecycle logic.
        return entity;
    }
}
~~~

You can declare them with `@Bean` in configuration if explicit dependency wiring is needed. Avoid instantiating callbacks with `new` inside repository methods, as Spring then cannot manage dependency injection or ordering.

### 10.2. Ordering When Multiple Callbacks Exist

If multiple callbacks of the same type exist, implement `Ordered` or use `@Order` as supported by your Spring Data version.

~~~java
@Component
@Order(100)
public class NormalizeProductCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

~~~java
@Component
@Order(200)
public class EnrichProductCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

This example expresses the intent to normalize before enriching. Lower order values usually have higher priority in Spring's ordering mechanism, though you should confirm the semantics of your callback registry and test actual order.

Reactive callback registries also need their ordering verified; do not infer order from bean names.

### 10.3. Separating Shared Logic from Callback Adapters

If the same normalization rules are needed across both imperative and reactive stacks:

~~~java
public class ProductNormalizer {

    public Product normalize(Product product) {
        if (product.getName() != null) {
            product.setNormalizedName(
                product.getName().trim().toLowerCase()
            );
        }
        return product;
    }
}
~~~

The imperative callback invokes the normalizer directly. The reactive callback can invoke the normalizer inside `Mono.fromSupplier` or `Mono.fromCallable` when appropriate.

If shared logic requires reactive I/O, do not force it into a synchronous method. Build a service returning a `Publisher` and let the imperative adapter integrate appropriately or design two clear implementations.

## 11. Testing Synchronous Callbacks

### 11.1. Unit Testing Callbacks

Because imperative callbacks return values directly, unit tests can invoke the method and assert on the result:

~~~java
@Test
void normalizesNameBeforeConvert() {
    Product product = new Product();
    product.setName("  Wireless Keyboard  ");

    Product result = callback.onBeforeConvert(
        product,
        IndexCoordinates.of("products")
    );

    assertThat(result.getNormalizedName())
        .isEqualTo("wireless keyboard");
}
~~~

This test verifies callback logic; it does not verify that Spring Data registered or invokes the callback at the proper lifecycle point.

### 11.2. Integration Testing with Elasticsearch

Use a compatible test instance to confirm:

- Callbacks are invoked when saving via `ElasticsearchOperations`.
- Callbacks run before conversion or before save at the right point.
- The actual document contains added fields.
- Post-save callbacks receive the expected result.
- Callbacks are not invoked when code goes directly through the low-level client.

### 11.3. Testing Ordering

Create two callbacks with distinct orders and record an execution sequence in the test. Do not check only the final outcome if a later callback could accidentally mask a mistake in an earlier callback.

## 12. Testing Reactive Callbacks

### 12.1. Using StepVerifier

Reactive callbacks return a `Publisher`, so they can be tested with Reactor `StepVerifier`:

~~~java
@Test
void normalizesNameReactively() {
    Product product = new Product();
    product.setName("  Wireless Keyboard  ");

    Mono<Product> result = Mono.from(
        callback.onBeforeConvert(
            product,
            IndexCoordinates.of("products")
        )
    );

    StepVerifier.create(result)
        .assertNext(saved -> assertThat(
            saved.getNormalizedName()
        ).isEqualTo("wireless keyboard"))
        .verifyComplete();
}
~~~

This test subscribes to the `Publisher` and asserts the output. There is no need to call `subscribe` manually with a latch when `StepVerifier` can drive the subscription.

### 12.2. Verifying Lazy Execution

You can verify that the callback does not run before subscription and only executes when the `Publisher` is subscribed:

~~~java
AtomicBoolean executed = new AtomicBoolean();

Mono<Product> result = Mono.defer(() -> {
    executed.set(true);
    return Mono.just(product);
});

assertThat(executed).isFalse();

StepVerifier.create(result)
    .expectNext(product)
    .verifyComplete();

assertThat(executed).isTrue();
~~~

This example tests the semantics of `Mono.defer`. In integration tests, apply the same idea to verify the actual callback participates in the reactive pipeline.

### 12.3. Testing Errors and Cancellation

Verify:

- When the callback returns `Mono.error`, the reactive operation emits an error signal.
- Cancellation does not leave unmanaged side effects behind.
- Retries do not multiply side effects unexpectedly.
- The callback does not call `block` or nested `subscribe`.
- The `Publisher` completes with exactly one entity per the contract.

### 12.4. Testing Reactor Context

If a callback reads the auditor or tenant from Reactor Context, supply the context in the test:

~~~java
StepVerifier.create(
    Mono.from(callback.onBeforeConvert(product, index))
        .contextWrite(ctx -> ctx.put("tenantId", "tenant-7"))
)
.assertNext(result -> assertThat(result).isNotNull())
.verifyComplete();
~~~

For the test to be meaningful, the callback must actually use `deferContextual` or the corresponding context API to read the key. `contextWrite` does not automatically copy values into `ThreadLocal`.

### 12.5. Integration Testing via ReactiveElasticsearchOperations

Callback unit tests do not prove the reactive template discovered the callback. Run integration tests through `ReactiveElasticsearchOperations` or a reactive repository and confirm:

- Callbacks execute when subscription runs.
- Post-callback entities/`Document` instances are written accurately.
- Error signals propagate to subscribers.
- No blocking calls occur on the event loop.
- Auditing reads the right auditor from reactive context.

## 13. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Imperative callback does not run in reactive save | Registered wrong callback registry/interface | Use the reactive callback contract matching your version |
| Reactive callback runs but changes are absent | Did not return transformed entity or `Publisher` emitted nothing | Return `Mono<T>`/`Publisher<T>` per contract |
| Reactive logic runs before subscribing | Side effect executed while constructing the `Publisher` | Put logic inside `defer`, `fromSupplier`, or proper operators |
| Event loop is blocked | Calling `block`, `sleep`, or blocking I/O | Compose non-blocking `Publisher` |
| Callback issues request but save does not wait | Calling `subscribe` internally | Return and compose the `Publisher` |
| Cannot retrieve auditor in reactive request | Using imperative `ThreadLocal`/`SecurityContextHolder` | Use `ReactiveAuditorAware` and Reactor/Security Context |
| Callback runs multiple times | Multiple subscriptions, retries, or multiple lifecycle operations | Design idempotent callbacks and control retries |
| Save reports error yet document exists | Exception thrown in `AfterSave` or response lost | Inspect state and use stable IDs/operation IDs |
| Callback not called via direct client | Bypassing Spring Data operations | Use Spring Data or invoke shared logic explicitly |
| Unstable callback order | Order not declared | Use `Ordered`/`@Order` and integration tests |
| Save unusually slow | Synchronous callback performs I/O or reactive callback uses blocking operators | Move I/O to proper services and measure callback latency |
| Auditing records wrong user | Auditor provider reads wrong context or job lacks principal | Define system auditor and test both requests and jobs |
| Save callback calls repository recursively | Persistence logic placed inside callback | Move orchestration to the service layer |

## 14. Process for Choosing a Callback Model

When adding lifecycle logic to Spring Data Elasticsearch:

1. Determine whether the application uses `ElasticsearchOperations` or `ReactiveElasticsearchOperations`.
2. Pick the matching imperative or reactive callback interface.
3. Choose the lifecycle checkpoint: before convert, before save, after save, after load, or after convert.
4. Keep callbacks short and tightly tied to the mapping/persistence lifecycle.
5. If I/O is needed, prefer an appropriate service; in the reactive stack, compose `Publisher`.
6. Never call `block` or `subscribe` inside reactive callbacks.
7. Return the modified entity/`Document`.
8. Register the callback as a Spring bean and declare order when required.
9. Configure auditing with `AuditorAware` or `ReactiveAuditorAware` matching the stack.
10. Ensure side effects are idempotent and never assume strictly once execution.
11. Write unit tests for callbacks and integration tests through the exact operations/template.
12. Monitor callback latency, error rates, and side effects in production.

## 15. Key Takeaways

- Synchronous callbacks return entities or `Document` directly; reactive callbacks return `Publisher`.
- Imperative callbacks run on the execution flow of the imperative operation.
- Reactive callbacks are part of a pipeline and execute when a subscription passes through the callback.
- Reactive does not automatically spawn background threads; schedulers determine thread switches.
- Do not call `block` or `subscribe` inside reactive callbacks; compose `Publisher`.
- Choose the right lifecycle callback: `BeforeConvert`, `BeforeSave`, `AfterSave`, `AfterLoad`, or `AfterConvert`.
- Register callbacks as Spring beans and declare ordering when multiple callbacks depend on one another.
- Auditing uses created/modified annotations and an auditor provider fitting imperative or reactive context.
- Reactive auditing requires `ReactiveAuditorAware`; do not rely on `ThreadLocal` to fetch users in reactive pipelines.
- Callbacks do not create distributed transactions and do not guarantee exactly-once side effects.
- `AfterSave` can fail after a write has already succeeded; retries must account for idempotency.
- Callbacks should keep logic short, clear, and lifecycle-focused; business orchestration belongs in the service layer.
- Test reactive callbacks with `StepVerifier`, alongside integration tests through the exact reactive template/repository.
- Low-level Elasticsearch clients do not automatically trigger Spring Data entity callbacks.

By choosing the right callback contract and execution model, an application can reuse lifecycle logic while preserving the synchronous or non-blocking properties of the stack in use. That is especially vital for auditing, where creator and modifier identity must follow each request's context without getting lost when a reactive pipeline switches threads.
