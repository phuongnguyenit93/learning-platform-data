# Kotlin suspend, Flow, and the Conversion Boundary with Reactor in Spring WebFlux

## 1. The big picture

Spring WebFlux is built on Reactive Streams and Reactor, typically using `Mono<T>` (0..1 element) and `Flux<T>` (0..N elements). Kotlin provides a different way to write asynchronous code: **coroutines**, `suspend fun`, and `Flow<T>`. Spring Framework supports both models, so an application can use Reactor APIs in repositories/WebClient while exposing service/controller APIs with Kotlin coroutines.

What matters is not merely changing syntax, but **preserving execution semantics** across the boundary:

- Do not block threads with `block()`, `runBlocking`, or `Future.get()` inside HTTP requests.
- Do not manually call `subscribe()` or launch coroutines that outlive the request lifecycle.
- Preserve empty, error, and cancellation semantics accurately.
- Preserve demand/backpressure when converting `Flux` ↔ `Flow`, understanding where buffers can appear.
- Preserve Reactor Context, security/trace context, and reactive transaction context when integrating.
- Do not accidentally materialize a multi-element stream into a memory-heavy collection.

Example of a valid flow:

~~~text
HTTP GET /api/catalog/42
          |
          v
suspend Controller.get(id)
          |
          v
suspend CatalogService.find(id)
          |
          v
ReactorRepository.findById(id): Mono<Item>
          |
          v
Mono<Item>.awaitSingleOrNull(): Item?
          |
          v
Kotlin nullable result / HTTP 200 or 404
~~~

With multiple elements:

~~~text
HTTP GET /api/catalog/stream
          |
          v
Controller.stream(): Flow<Item>
          |
          v
Service.list(): Flow<Item>
          |
          v
Repository.findAll(): Flux<Item>
          |
          v
Publisher.asFlow()
          |
          v
WebFlux adapts Flow -> Reactive Streams -> NDJSON response
~~~

In both examples, Spring WebFlux and the adapters coordinate subscription/collection. Business code does not need to spawn a separate “background job” of its own.

## 2. Mapping Mono/Flux to suspend/Flow

Per Spring Framework's Kotlin Coroutines documentation, the standard mapping is:

| Reactor API | Kotlin coroutines API | Meaning |
| --- | --- | --- |
| `Mono<T>` with a value | `suspend fun f(): T` | Awaits one value without blocking a thread |
| `Mono<T>` that can complete empty | `suspend fun f(): T?` | Absence represented via nullable type |
| `Mono<Void>` / `Mono<Unit>` by task contract | `suspend fun f()` | Awaits completion, may throw an error |
| `Flux<T>` | `fun f(): Flow<T>` | Asynchronous sequence of 0..N elements collected incrementally |
| `Mono<List<T>>` | `suspend fun f(): List<T>` | An already-materialized collection |
| `Flux<T>` from a stream source | `Flow<T>` from a stream source | Does not necessarily buffer all data |

Distinguish clearly: `suspend fun f(): T` is not a publisher. It is a function that can **suspend the coroutine** while waiting for I/O. Conversely, `Mono<T>` is an object describing work that can be subscribed to.

`Flow<T>` is also not directly an `org.reactivestreams.Publisher<T>`. When a Java API requires a Publisher, an adapter such as `flow.asFlux()` or `flow.asPublisher()` is needed. When Kotlin code needs a Flow from a Flux, use `flux.asFlow()`.

### Differences in API and style

Reactor:

~~~kotlin
fun find(id: Long): Mono<ItemView> =
    repository.findById(id)
        .map { ItemView(it.id, it.name) }
~~~

Coroutines:

~~~kotlin
suspend fun find(id: Long): ItemView? =
    repository.findById(id)
        .awaitSingleOrNull()
        ?.let { ItemView(it.id, it.name) }
~~~

Both approaches can be non-blocking when the repository uses a reactive driver. Choose the API matching each module's contract rather than converting back and forth merely because one syntax looks shorter.

## 3. Integration libraries to know

| Dependency | Purpose |
| --- | --- |
| `kotlinx-coroutines-core` | Coroutines, `suspend`, `Flow`, `coroutineScope`, `async` |
| `kotlinx-coroutines-reactive` | Reactive Streams adapters: `Publisher.asFlow`, `Flow.asPublisher`, `Publisher.await...` helpers |
| `kotlinx-coroutines-reactor` | Reactor adapters: `Mono.awaitSingle`, `Mono.awaitSingleOrNull`, `Flow.asFlux`, `mono`, `flux`, `ReactorContext` |
| `spring-boot-starter-webflux` | WebFlux + Reactor + WebClient |
| `jackson-module-kotlin` | Decode/encode Kotlin data classes with Jackson |
| `kotlin-reflect` | Kotlin reflection support used by many Spring components |
| `kotlin("plugin.spring")` | Allows Spring to proxy suitably annotated Kotlin classes |

With Spring Framework 6.2, the documentation requires `kotlinx-coroutines-core` and `kotlinx-coroutines-reactor` on the classpath for coroutine support. For Spring Data coroutine repositories, also include `kotlinx-coroutines-reactive` because they are built on reactive repositories.

Spring Boot 3.5 manages Kotlin/Coroutines versions via dependency management. With Gradle, the Boot plugin aligns Kotlin dependency versions with the Kotlin Gradle plugin. Avoid manually mixing incompatible `kotlinx-coroutines-*` versions.

A dependency only adapts APIs; it does **not** make blocking JDBC/JPA non-blocking.

## 4. From Mono to suspend with awaitSingle and awaitSingleOrNull

Common extensions from `kotlinx.coroutines.reactor`:

~~~kotlin
import kotlinx.coroutines.reactor.awaitSingle
import kotlinx.coroutines.reactor.awaitSingleOrNull

suspend fun getRequired(id: Long): Item =
    repository.findById(id).awaitSingle()

suspend fun getOptional(id: Long): Item? =
    repository.findById(id).awaitSingleOrNull()
~~~

Both functions suspend asynchronously without holding a thread just to wait for the result.

### When Mono emits one element

- `awaitSingle()` returns the element.
- `awaitSingleOrNull()` returns the element.
- If the Mono emits an error, both throw the corresponding exception into the awaiting coroutine.

### When Mono completes empty

- `awaitSingle()` throws `NoSuchElementException`.
- `awaitSingleOrNull()` returns `null`.

Therefore, for reactive repository `findById`, `awaitSingleOrNull()` expresses “not found” more cleanly.

~~~kotlin
suspend fun findOr404(id: Long): Item =
    repository.findById(id).awaitSingleOrNull()
        ?: throw ResponseStatusException(HttpStatus.NOT_FOUND)
~~~

### When Mono only carries a completion signal

A `Mono<Void>` from a delete operation emits no element; do not use `awaitSingle()` because it will fail as empty. You can use:

~~~kotlin
suspend fun delete(id: Long) {
    repository.deleteById(id).awaitSingleOrNull()
}
~~~

Or when calling WebClient for a response without a body, use the `awaitBodilessEntity()` Kotlin extension on the response spec. The goal is to await completion or error, not demand a dummy value.

## 5. From Flux to Flow with asFlow()

`Publisher.asFlow()` lives in the `kotlinx.coroutines.reactive` package:

~~~kotlin
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.reactive.asFlow

fun names(): Flow<String> =
    repository.findAll()
        .asFlow()
        .map { it.name }
~~~

Key points to remember:

1. `Flux<T>` can emit 0..N items, complete, or error.
2. `asFlow()` creates an adapter so a coroutine can collect them.
3. `Flow` is cold by default for standard flow builders; a new collection usually restarts the work. However, if the source Publisher is hot, the adapter does **not** automatically make it replayable.
4. Errors from the Publisher surface in the collecting coroutine.
5. Cancelling coroutine collection cancels the Publisher subscription within the adapter's capabilities.
6. `Flow.map { ... }` takes a suspending lambda, so the transformation can call another suspending function.

Example with a suspend operation inside `Flow.map`:

~~~kotlin
fun enriched(): Flow<EnrichedItem> =
    repository.findAll()
        .asFlow()
        .map { item ->
            val score = scoringService.getScore(item.id) // suspend fun
            EnrichedItem(item.id, item.name, score)
        }
~~~

Because Flow `map` processes sequentially by default, it awaits scoring for each item before moving to the next. If parallel processing is needed, design bounded concurrency explicitly and account for output ordering.

### When is a Flow created and when does it run?

~~~kotlin
val flow = repository.findAll().asFlow()
~~~

This line creates the `Flow` object. Data is only consumed when a collector runs, such as `collect` or when Spring WebFlux adapts the Flow to write the HTTP response.

Do not collect a Flow with `toList()` when the goal is streaming large/infinite data, as it must keep every item in memory and wait for the source to complete.

## 6. From Flow to Flux or Publisher

When you need to pass a Flow to a Java API expecting a Reactor Flux:

~~~kotlin
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.reactor.asFlux
import reactor.core.publisher.Flux

fun sendToReactor(flow: Flow<Item>): Flux<Item> =
    flow.asFlux()
~~~

`Flow.asFlux()` turns a Flow into a Reactive Streams-compliant Flux. The new Flux is a cold adapter: each subscription collects the source Flow; when the subscriber cancels, the corresponding collection is cancelled.

When only `Publisher<T>` is needed:

~~~kotlin
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.reactive.asPublisher
import org.reactivestreams.Publisher

fun asPublisher(items: Flow<Item>): Publisher<Item> =
    items.asPublisher()
~~~

If the system already uses Reactor, prefer `asFlux()` to leverage Reactor APIs.

### Note that Flow<T?> can contain null

Reactive Streams forbids `onNext(null)`. Adapter APIs like `asFlux` constrain `T : Any`, meaning non-nullable elements.

Therefore:

~~~kotlin
val values: Flow<String?> = flowOf("a", null, "b")
~~~

cannot be adapted as-is into `Flux<String?>` via `asFlux()`. Handle nulls according to your business contract:

~~~kotlin
val nonNull: Flow<String> = values.filterNotNull()
val reactorFlux: Flux<String> = nonNull.asFlux()
~~~

If null carries meaning as a distinct record, replace it with a DTO representing the absent state instead of emitting null.

## 7. From suspend blocks to Mono and Flux builders

When a Java/Reactor API expects a Mono while the logic is written as a `suspend fun`, use `mono { ... }`:

~~~kotlin
import kotlinx.coroutines.reactor.mono
import reactor.core.publisher.Mono

fun loadAsMono(id: Long): Mono<Item> = mono {
    suspendItemService.load(id) // suspend fun load(): Item
}
~~~

The `mono` builder creates a **cold Mono**: the coroutine block only starts on subscription. If the block returns `null`, the Mono completes empty.

~~~kotlin
fun lookupAsMono(id: Long): Mono<Item> = mono {
    suspendItemService.find(id) // returns Item?
}
~~~

When you want to build a Flux with coroutine logic:

~~~kotlin
import kotlinx.coroutines.reactor.flux
import reactor.core.publisher.Flux

fun countdown(): Flux<Int> = flux {
    send(3)
    send(2)
    send(1)
}
~~~

`send` coordinates with demand and can suspend when downstream is not yet ready for more items. This is the proper bridge for a coroutine producer, rather than manually subscribing to an existing Flux.

### Never use runBlocking to turn suspend into Mono

Wrong in a request pipeline:

~~~kotlin
fun lookup(id: Long): Mono<Item> {
    val item = runBlocking { suspendItemService.load(id) }
    return Mono.just(item)
}
~~~

`runBlocking` blocks the current thread until the coroutine finishes. If that thread is a Netty event loop, throughput can plummet or deadlocks/timeouts can occur.

Right:

~~~kotlin
fun lookup(id: Long): Mono<Item> = mono {
    suspendItemService.load(id)
}
~~~

For single-value operations from Reactor to suspend, do the inverse with `awaitSingle()` or `awaitSingleOrNull()`; never call `block()`.

## 8. Conversion boundaries: choosing adapters by cardinality

| Source | Target | API | Notes |
| --- | --- | --- | --- |
| `Mono<T>` | `T` in suspend | `awaitSingle()` | Empty throws NoSuchElementException |
| `Mono<T>` | `T?` in suspend | `awaitSingleOrNull()` | Empty becomes null |
| `Flux<T>` | `Flow<T>` | `asFlow()` | Data is collected on demand |
| `Flow<T : Any>` | `Flux<T>` | `asFlux()` | Reactive Streams forbids null |
| `Flow<T : Any>` | `Publisher<T>` | `asPublisher()` | Does not require Reactor API at caller |
| Suspend lambda returning `T?` | `Mono<T>` | `mono { ... }` | Cold; null becomes empty |
| Coroutine producer | `Flux<T>` | `flux { send(...) }` | Cold, demand-aware |
| Reactor `Scheduler` | CoroutineDispatcher | `asCoroutineDispatcher()` | Dispatcher can be closed when no longer needed |
| Reactor Context | Coroutine context | `ReactorContext` | Must stay within the same subscription/context |

Do not convert `Flux<T>` to `Mono<List<T>>` just because you need to call a suspending function. If you want to process items incrementally, `Flux.asFlow()` and Flow operators are the more direct conversion path.

## 9. Backpressure in Reactor and Flow

Reactor/Reactive Streams uses `Subscription.request(n)`: downstream signals upstream how many elements it is requesting. Flow is a push-based API with **suspending emissions**: the producer can suspend when the consumer is not ready.

During `Flux.asFlow()`, the adapter uses a channel/buffer to bridge between Reactive Streams and the coroutine collector.

Per `kotlinx.coroutines.reactive` documentation, `buffer` placed on the Flow after `asFlow()` affects the prefetch/backpressure request size:

~~~kotlin
import kotlinx.coroutines.flow.buffer
import kotlinx.coroutines.reactive.asFlow

fun rows(): Flow<Row> =
    repository.streamRows()
        .asFlow()
        .buffer(16)
~~~

`buffer(16)` does not mean “the entire system holds strictly 16 items”; drivers, codecs, and other operators can buffer as well. However, it provides a controlled throttling point in the adapter.

In the reverse direction:

~~~kotlin
val flux: Flux<Item> = itemFlow.asFlux()
~~~

`asFlux()` bridges subscriber demand to collecting the Flow. If the subscriber is slow or cancels, the coroutine inside the adapter coordinates with those signals.

### Operations that lose streaming benefits

~~~kotlin
val all: List<Item> = repository.findAll()
    .asFlow()
    .toList()
~~~

`toList()` must hold the entire finite result in memory. Use it only when business logic requires the full collection. On an infinite source, `toList()` never completes.

When returning HTTP responses, media types matter too:

- `application/json` usually produces a finite JSON array.
- `application/x-ndjson` fits consecutive JSON records.
- `text/event-stream` fits SSE.

Do not treat returning a Flow as a guarantee that every proxy or client will display each item immediately; check encoders, flushing, and buffering end-to-end.

## 10. Cancellation and error propagation

In coroutines, cancellation is normally represented by `CancellationException` and a cancelled `Job`. In Reactor, subscribers call `cancel()`. The official adapters connect these two concepts:

- When a coroutine is cancelled while awaiting `Mono.awaitSingle()`, the adapter cancels the awaited Reactor subscription.
- When a Flux subscriber cancels `Flow.asFlux()`, the coroutine collecting the underlying Flow is cancelled.
- When the collector stops `Publisher.asFlow()`, the Publisher subscription is cancelled via the adapter.
- When Reactor emits `onError`, the suspending await or collector receives the corresponding exception.
- When a coroutine throws an exception (other than cancellation), `mono` or `flux` emits `onError`.

Example of not swallowing cancellation:

~~~kotlin
suspend fun findSafe(id: Long): Item? {
    return try {
        repository.findById(id).awaitSingleOrNull()
    } catch (e: CancellationException) {
        throw e
    } catch (e: DataAccessException) {
        logger.warn("Database request failed", e)
        throw e
    }
}
~~~

This is an illustrative snippet requiring the appropriate exception and logger imports in a real project. Do not turn every error into null, as that misrepresents database failures as “not found”.

### Using timeouts properly

~~~kotlin
suspend fun getWithDeadline(id: Long): Item? =
    withTimeout(2_000) {
        repository.findById(id).awaitSingleOrNull()
    }
~~~

`withTimeout` cancels the coroutine when time expires; the adapter requests cancellation of the awaited subscription. Application-level timeouts do not replace driver connection/pool timeouts.

Do not catch broad `Exception` and return a default value when that includes cancellation. If resource cleanup is needed, use `try/finally`, and understand that `withContext(NonCancellable)` should only be used for very brief, controlled cleanup.

## 11. Structured concurrency instead of GlobalScope

One advantage of Kotlin coroutines is `coroutineScope` and `supervisorScope` for managing child tasks. Inside an HTTP request, child tasks should have lifecycles bound to the request:

~~~kotlin
suspend fun dashboard(userId: Long): Dashboard = coroutineScope {
    val profile = async { profileClient.load(userId) }
    val permissions = async { permissionClient.load(userId) }

    Dashboard(
        profile = profile.await(),
        permissions = permissions.await()
    )
}
~~~

When one child fails in a standard `coroutineScope`, the scope cancels the remaining children and propagates the error to the caller. When the parent request/coroutine is cancelled, its children are cancelled too.

Avoid:

~~~kotlin
GlobalScope.launch {
    auditService.writeAudit()
}
~~~

This is a fire-and-forget task outside the request lifecycle; cancellation, errors, transactions, and tracing context can all be detached. If business logic genuinely needs a background job, use a queue/message broker or an application-level `CoroutineScope` with managed lifecycle, error handling, and a clear shutdown policy.

### When is concurrency needed?

`Flow.map { suspendOperation(it) }` processes elements sequentially by default. To raise concurrency, use Flow operators with explicit bounds or group tasks inside `coroutineScope` and await them. Do not launch thousands of unbounded `async` calls when the DB pool or downstream service cannot handle the load.

## 12. Reactor Context and CoroutineContext

Reactor tracks request/subscription metadata via `reactor.util.context.Context`. Kotlin coroutines use `CoroutineContext`. `kotlinx-coroutines-reactor` provides `ReactorContext` to bridge them.

Illustrative example:

~~~kotlin
import kotlin.coroutines.coroutineContext
import kotlinx.coroutines.reactor.ReactorContext
import kotlinx.coroutines.reactor.mono
import reactor.util.context.Context

val result: Mono<String> = mono {
    val reactorContext = coroutineContext[ReactorContext]?.context
    reactorContext?.getOrDefault("traceId", "missing") ?: "missing"
}.contextWrite(Context.of("traceId", "req-42"))
~~~

When `result` is subscribed to, the Mono emits:

~~~text
req-42
~~~

Per `kotlinx.coroutines` documentation, the `mono`, `flux`, `asFlow`, `asFlux`, and `await` adapters integrate `ReactorContext`, though how far MDC/ThreadLocal, security context, and observations propagate still depends on framework configuration, Micrometer Context Propagation, and how coroutines are launched.

Do not automatically assume a ThreadLocal on an event-loop thread follows every coroutine/scheduler. To obtain the security principal, use Spring Security's reactive/coroutine-aware mechanisms; for tracing, configure context propagation suited to your Spring/Micrometer version and test end-to-end.

## 13. WebFlux controllers support suspend and Flow directly

Spring WebFlux annotated controllers can declare:

~~~kotlin
@RestController
@RequestMapping("/api/users")
class UserController(private val service: UserService) {

    @GetMapping("/{id}")
    suspend fun get(@PathVariable id: Long): UserView =
        service.find(id)
            ?: throw ResponseStatusException(HttpStatus.NOT_FOUND)

    @GetMapping
    fun all(): Flow<UserView> = service.findAll()
}
~~~

There is no need to convert `Flow` to `Flux` just to return it from an annotated controller: Spring Framework includes adapters for coroutine return types.

For functional endpoints, Spring WebFlux also provides the `coRouter { }` DSL and suspending handlers. Do not mix annotated controllers and `coRouter` in the same example unnecessarily; pick one style matching your application structure.

### Mono/Flux remain valid APIs in Kotlin

~~~kotlin
@GetMapping("/reactor")
fun reactorEndpoint(): Flux<UserView> = service.findAll().asFlux()
~~~

Spring WebFlux accepts both Reactor types and coroutine types. There is no requirement to rewrite all Kotlin code to Flow; libraries/teams with stable Reactor pipelines can continue using Reactor at appropriate boundaries.

## 14. WebClient: awaitBody, awaitBodyOrNull, and bodyToFlow

Spring WebFlux's Kotlin extensions let clients call APIs in coroutine style:

~~~kotlin
import org.springframework.web.reactive.function.client.awaitBody
import org.springframework.web.reactive.function.client.awaitBodyOrNull
import org.springframework.web.reactive.function.client.bodyToFlow

class CatalogRemoteClient(private val webClient: WebClient) {

    suspend fun get(id: Long): RemoteItem =
        webClient.get()
            .uri("/items/{id}", id)
            .retrieve()
            .awaitBody<RemoteItem>()

    suspend fun optionalResponse(): RemoteItem? =
        webClient.get()
            .uri("/optional")
            .retrieve()
            .awaitBodyOrNull<RemoteItem>()

    fun stream(): Flow<RemoteItem> =
        webClient.get()
            .uri("/stream")
            .accept(MediaType.APPLICATION_NDJSON)
            .retrieve()
            .bodyToFlow<RemoteItem>()
}
~~~

This snippet is intended for a WebClient already configured with a base URL and corresponding `RemoteItem` DTO types, not a standalone project.

Important note: `awaitBodyOrNull()` handles an **empty body**; it does not automatically convert HTTP 404 into null. `retrieve()` treats 4xx/5xx responses as errors by default. If an endpoint contract uses 404 for “no record”, handle HTTP status explicitly instead of confusing an empty response with HTTP 404.

### Sending a Flow as a request body

WebClient `RequestBodySpec` has an overload accepting a Publisher. Since Flow does not directly implement Publisher, a bridge is needed:

~~~kotlin
fun send(events: Flow<Event>): Mono<Void> =
    webClient.post()
        .uri("/events")
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(events.asFlux(), Event::class.java)
        .retrieve()
        .bodyToMono(Void::class.java)
~~~

If the caller is in a suspend context, you can use `awaitBodilessEntity()` or `awaitSingleOrNull()` on `Mono<Void>`, depending on the response contract.

### Do not subscribe to the request body manually

Wrong:

~~~kotlin
events.asFlux().subscribe()
return webClient.post().uri("/events").retrieve().bodyToMono(Void::class.java)
~~~

The Publisher is consumed independently; the HTTP request is unlikely to contain the body and errors are no longer wired into the pipeline. The right way is passing the Publisher into `body(...)` and returning/awaiting the response.

## 15. Spring Data CoroutineCrudRepository and reactive databases

Spring Data R2DBC provides coroutine repositories built on top of reactive repositories. You can declare:

~~~kotlin
import kotlinx.coroutines.flow.Flow
import org.springframework.data.repository.kotlin.CoroutineCrudRepository

interface BookRepository : CoroutineCrudRepository<BookEntity, Long> {
    fun findByAuthor(author: String): Flow<BookEntity>
}
~~~

Typical methods:

- `suspend fun findById(id): BookEntity?`: one record or null.
- `fun findAll(): Flow<BookEntity>`: multiple records.
- `suspend fun save(entity): BookEntity`: saves one record.
- `suspend fun deleteById(id)`: awaits the delete operation.

Exact method names and nullability follow the Spring Data API/version in use. For custom query methods, declare `suspend` or return `Flow` to preserve CoroutineContext; plain methods like `fun getUser(): User` in a coroutine repository can run blocking without context propagation and should be avoided.

This is an implementation snippet outside the demo project in section 18: it requires `spring-boot-starter-data-r2dbc`, an R2DBC driver, and properly mapped entities. You cannot merely add `CoroutineCrudRepository`, continue using JPA/JDBC, and claim the system is non-blocking.

### From legacy ReactiveCrudRepository to a suspend service

If you already have a stable Reactor repository:

~~~kotlin
class BookService(private val repository: ReactiveCrudRepository<Book, Long>) {

    suspend fun find(id: Long): Book? =
        repository.findById(id).awaitSingleOrNull()

    fun all(): Flow<Book> = repository.findAll().asFlow()
}
~~~

This is a valid conversion boundary; there is no need to rewrite repositories simply because the controller is written with Kotlin coroutines.

## 16. Reactive transactions when using coroutines

A reactive transaction binds to a reactive transaction manager and Reactor Context, not merely a ThreadLocal on the running thread.

Spring Framework 6.2 explicitly documents transaction support for coroutines via the **programmatic reactive transaction management** API:

- `TransactionalOperator.executeAndAwait { ... }` for suspending blocks.
- `Flow<T>.transactional(operator)` for Flow chains.

Illustrative example:

~~~kotlin
import org.springframework.transaction.reactive.TransactionalOperator
import org.springframework.transaction.reactive.executeAndAwait

class PaymentService(
    private val operator: TransactionalOperator,
    private val payments: CoroutinePaymentRepository,
    private val ledger: CoroutineLedgerRepository
) {
    suspend fun create(input: NewPayment): Payment =
        operator.executeAndAwait {
            val payment = payments.save(input.toEntity())
            ledger.save(LedgerEntry(paymentId = payment.id))
            payment
        } ?: error("Transaction completed without a value")
}
~~~

This example depicts two coroutine repositories and entities from a payment module, outside the demo project. `executeAndAwait` is a suspending extension returning a nullable value per the API contract; handle the no-value case explicitly.

With Flow:

~~~kotlin
import org.springframework.transaction.reactive.transactional

fun updateAll(): Flow<BookEntity> =
    repository.findAll()
        .map { item -> repository.save(item.copy(active = true)) }
        .transactional(operator)
~~~

The `Flow.map` operator here can call suspending `save`.

Things to avoid:

- Calling `runBlocking` inside a reactive transaction.
- Manually subscribing to a Publisher inside a transaction and creating a separate subscription.
- Using Spring JDBC/JPA while assuming the reactive transaction manager will manage it.
- Placing an infinite Flow inside an endlessly running transaction, holding DB connections.
- Treating an HTTP call to another service as part of a DB transaction that will roll back automatically.

Cancelling a reactive transaction can cause rollback; do not accidentally cut short a transactional Flux with `take(1)` or `first()` if all side effects must complete. Test rollback on both exceptions and cancellation.

## 17. Blocking code, context switches, and conversion errors

### Blocking is not fixed by the suspend modifier

Wrong:

~~~kotlin
suspend fun load(): User = jdbcDao.findUser()
~~~

The function is declared `suspend`, yet the JDBC call remains blocking.

If the system has not migrated to a reactive driver yet, blocking code can be isolated as a transitional step:

~~~kotlin
suspend fun loadLegacy(): User = withContext(Dispatchers.IO) {
    jdbcDao.findUser()
}
~~~

This workaround still consumes a thread during blocking I/O and must be measured and concurrency-limited. There is no real reactive backpressure to the JDBC library, and imperative transactions do not automatically synchronize with R2DBC transactions.

### Do not call await on a Flux when you need the whole stream

If you only call `awaitFirst()` on a Flux, the coroutine takes the first element and may cancel the rest. That is valid when the goal is genuinely “first”, but wrong if you need to process all results or transactional side effects.

Use `asFlow()` and appropriate `collect`/operators for 0..N; if a finite collection is truly needed, use `toList()` intentionally and bound its size.

### Do not call Flow.collect in a controller just to send a response

Wrong:

~~~kotlin
@GetMapping("/stream")
suspend fun stream(): List<Event> =
    eventService.events().toList()
~~~

This loses streaming and buffers the entire result. The right approach is:

~~~kotlin
@GetMapping("/stream", produces = [MediaType.APPLICATION_NDJSON_VALUE])
fun stream(): Flow<Event> = eventService.events()
~~~

## 18. Complete example: Spring Boot 3.5 + Kotlin 2.1 + Java 17

The following project demonstrates **both sides of the boundary** without needing an external database or API:

- The source layer is written in Reactor (`Mono`/`Flux`) holding an immutable sample list.
- The coroutine service calls `awaitSingleOrNull()`, `awaitSingle()`, and `asFlow()`.
- The controller uses `suspend fun` and `Flow<T>` directly.
- Two Reactor-compatible endpoints use `mono { ... }` and `Flow.asFlux()`.
- WebTestClient tests mappings, null/404, JSON arrays, and NDJSON content types; StepVerifier tests adapter signals.

### 18.1. Project structure

~~~text
kotlin-reactor-bridge/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/kotlin/com/example/bridge/
    │   └── BridgeApplication.kt
    └── test/kotlin/com/example/bridge/
        └── BridgeApplicationTests.kt
~~~

### 18.2. settings.gradle.kts

~~~kotlin
rootProject.name = "kotlin-reactor-bridge"
~~~

### 18.3. build.gradle.kts

~~~kotlin
plugins {
    kotlin("jvm") version "2.1.20"
    kotlin("plugin.spring") version "2.1.20"
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("com.fasterxml.jackson.module:jackson-module-kotlin")
    implementation("org.jetbrains.kotlin:kotlin-reflect")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-reactive")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-reactor")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
~~~

Use JDK 17+ and a Gradle version compatible with Kotlin Gradle plugin 2.1.20; Gradle 8.12 is a suitable choice. In real projects, commit the Gradle Wrapper (`gradlew`, `gradlew.bat`, and wrapper files) to standardize versions across the team.

Do not pin individual Kotlin/Coroutines dependency versions manually when using Spring Boot's BOM. The `kotlin("plugin.spring")` plugin allows Spring to generate proxies for Kotlin classes requiring proxying.

### 18.4. BridgeApplication.kt

~~~kotlin
package com.example.bridge

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.reactive.asFlow
import kotlinx.coroutines.reactor.asFlux
import kotlinx.coroutines.reactor.awaitSingle
import kotlinx.coroutines.reactor.awaitSingleOrNull
import kotlinx.coroutines.reactor.mono

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.http.MediaType
import org.springframework.http.ResponseEntity
import org.springframework.stereotype.Component
import org.springframework.stereotype.Service
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

import reactor.core.publisher.Flux
import reactor.core.publisher.Mono

@SpringBootApplication
class BridgeApplication

fun main(args: Array<String>) {
    runApplication<BridgeApplication>(*args)
}

data class CatalogItem(
    val id: Long,
    val name: String
)

// This layer intentionally uses the Reactor API to illustrate interop.
// Data is an in-memory example only; not an R2DBC repository.
@Component
class ReactorCatalog {
    private val items = listOf(
        CatalogItem(1, "Kotlin"),
        CatalogItem(2, "Reactor"),
        CatalogItem(3, "WebFlux")
    )

    fun find(id: Long): Mono<CatalogItem> = Mono.defer {
        Mono.justOrEmpty(items.firstOrNull { it.id == id })
    }

    fun all(): Flux<CatalogItem> = Flux.defer {
        Flux.fromIterable(items)
    }

    fun count(): Mono<Long> = all().count()
}

@Service
class CatalogService(private val source: ReactorCatalog) {
    suspend fun find(id: Long): CatalogItem? =
        source.find(id).awaitSingleOrNull()

    fun list(): Flow<CatalogItem> = source.all().asFlow()

    suspend fun count(): Long =
        source.count().awaitSingle()
}

@RestController
@RequestMapping("/api/catalog")
class CatalogController(private val service: CatalogService) {

    // Mono<T> -> suspend T? -> HTTP 200 or 404
    @GetMapping("/{id}")
    suspend fun get(@PathVariable id: Long): ResponseEntity<CatalogItem> {
        val item = service.find(id)
        return if (item == null) {
            ResponseEntity.notFound().build()
        } else {
            ResponseEntity.ok(item)
        }
    }

    // Flux<T> -> Flow<T> -> JSON array
    @GetMapping(produces = [MediaType.APPLICATION_JSON_VALUE])
    fun list(): Flow<CatalogItem> = service.list()

    // Flux<T> -> Flow<T> -> NDJSON stream
    @GetMapping(
        "/stream",
        produces = [MediaType.APPLICATION_NDJSON_VALUE]
    )
    fun stream(): Flow<CatalogItem> = service.list()

    // Mono<Long> -> suspend Long -> JSON object
    @GetMapping("/count")
    suspend fun count(): Map<String, Long> =
        mapOf("count" to service.count())

    // suspend call -> Mono<ResponseEntity<T>> for Reactor callers
    @GetMapping("/bridge/mono/{id}")
    fun bridgeMono(
        @PathVariable id: Long
    ): Mono<ResponseEntity<CatalogItem>> = mono {
        val item = service.find(id)
        if (item == null) {
            ResponseEntity.notFound().build<CatalogItem>()
        } else {
            ResponseEntity.ok(item)
        }
    }

    // Flow<T> -> Flux<T> for Reactor callers
    @GetMapping(
        "/bridge/flux",
        produces = [MediaType.APPLICATION_NDJSON_VALUE]
    )
    fun bridgeFlux(): Flux<CatalogItem> =
        service.list().asFlux()
}
~~~

Explanation:

- `Mono.defer` and `Flux.defer` clarify the cold/lazy aspect of the Reactor source.
- `find` uses `awaitSingleOrNull` because the record may not exist.
- `count` uses `awaitSingle` because `Flux.count()` always emits a Long if the source completes normally.
- The `list` endpoint returns a Flow; WebFlux adapts it automatically when encoding the response.
- The `bridgeMono` endpoint shows `mono { }` converting suspend logic back to Reactor APIs without blocking.
- The `bridgeFlux` endpoint shows `Flow.asFlux()`.
- Neither `subscribe()` nor `runBlocking` is called.
- The list is read-only, making tests deterministic without needing a DB.

### 18.5. BridgeApplicationTests.kt

~~~kotlin
package com.example.bridge

import kotlinx.coroutines.reactor.asFlux

import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.http.MediaType
import org.springframework.test.web.reactive.server.WebTestClient

import reactor.test.StepVerifier

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class BridgeApplicationTests {

    @Autowired
    lateinit var client: WebTestClient

    @Autowired
    lateinit var service: CatalogService

    @Test
    fun suspendEndpointReturnsItem() {
        client.get()
            .uri("/api/catalog/2")
            .exchange()
            .expectStatus().isOk
            .expectBody()
            .jsonPath("$.name").isEqualTo("Reactor")
    }

    @Test
    fun monoEmptyMapsTo404() {
        client.get()
            .uri("/api/catalog/999")
            .exchange()
            .expectStatus().isNotFound
    }

    @Test
    fun countAwaitsMono() {
        client.get()
            .uri("/api/catalog/count")
            .exchange()
            .expectStatus().isOk
            .expectBody()
            .jsonPath("$.count").isEqualTo(3)
    }

    @Test
    fun flowReturnsJsonArray() {
        client.get()
            .uri("/api/catalog")
            .exchange()
            .expectStatus().isOk
            .expectBody()
            .jsonPath("$[0].name").isEqualTo("Kotlin")
            .jsonPath("$[2].name").isEqualTo("WebFlux")
    }

    @Test
    fun bridgeMonoKeepsNotFoundSemantics() {
        client.get()
            .uri("/api/catalog/bridge/mono/999")
            .exchange()
            .expectStatus().isNotFound
    }

    @Test
    fun fluxEndpointUsesNdjsonMediaType() {
        client.get()
            .uri("/api/catalog/bridge/flux")
            .accept(MediaType.APPLICATION_NDJSON)
            .exchange()
            .expectStatus().isOk
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
    }

    @Test
    fun flowToFluxPreservesSignals() {
        StepVerifier.create(service.list().asFlux().map { it.name })
            .expectNext("Kotlin", "Reactor", "WebFlux")
            .verifyComplete()
    }
}
~~~

Run:

~~~bash
gradle test
gradle bootRun
~~~

Or use `./gradlew test` and `./gradlew bootRun` once a Gradle Wrapper is created.

After starting the server, try:

~~~bash
curl -i http://localhost:8080/api/catalog/2
curl -i http://localhost:8080/api/catalog/999
curl -i http://localhost:8080/api/catalog/count
curl -i http://localhost:8080/api/catalog
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/api/catalog/stream
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/api/catalog/bridge/flux
~~~

GET `/api/catalog/2` response:

~~~json
{"id":2,"name":"Reactor"}
~~~

GET `/api/catalog/count` response:

~~~json
{"count":3}
~~~

GET `/api/catalog/999` returns HTTP 404.

GET `/api/catalog` returns a JSON array:

~~~json
[
  {"id":1,"name":"Kotlin"},
  {"id":2,"name":"Reactor"},
  {"id":3,"name":"WebFlux"}
]
~~~

GET `/api/catalog/stream` returns NDJSON records (each line is a separate JSON object):

~~~text
{"id":1,"name":"Kotlin"}
{"id":2,"name":"Reactor"}
{"id":3,"name":"WebFlux"}
~~~

JSON serializers may vary whitespace/formatting, but field values and item counts match the above. The example runs in an environment with Gradle dependencies downloaded and port 8080 available.

## 19. Practical workflow for integrating Kotlin and Java Reactor libraries

When given a Java module returning `Mono`/`Flux`, do not rewrite the entire codebase immediately. Use clear boundaries:

1. **Determine cardinality:** one item or many items? Is an empty Mono a valid outcome?
2. **Choose the public API:** Kotlin service returning `suspend T`/`T?` or `Flow<T>`, or keep Reactor types because Java callers need them?
3. **Convert once at the boundary:** `awaitSingle`/`awaitSingleOrNull` or `asFlow`/`asFlux` of the right kind.
4. **Preserve lifecycle:** no detached subscriptions, no `GlobalScope.launch` for request work.
5. **Handle errors explicitly:** not-found differs from backend failures, and cancellation is not a business error.
6. **Control backpressure:** buffers, concurrency, data size, and HTTP media types.
7. **Determine transaction context:** reactive transactions/`CoroutineContext` must be preserved across adapters.
8. **Test both sides:** StepVerifier for Reactor signals, coroutine tests for suspending logic, WebTestClient for HTTP.
9. **Measure in production:** memory, thread counts, database pools, request timeouts, cancellations, and downstream latency.
10. **Limit bridge hops:** avoid unnecessary `asFlow` → `asFlux` → `asFlow` chains that obscure code.

## 20. Common mistakes

1. **Using `Mono.block()` inside a suspend function:** still blocking. Use `awaitSingle()`.
2. **Using `runBlocking` in a WebFlux controller:** blocks the HTTP processing thread. Use `suspend fun`.
3. **Using `awaitSingle()` on a Mono that can be empty:** can throw NoSuchElementException. Use `awaitSingleOrNull()`.
4. **Turning every HTTP 404 into null assuming awaitBodyOrNull handles 404:** wrong; handle response status explicitly.
5. **Treating Flow as a Publisher:** Flow does not directly implement Reactive Streams Publisher; use `asFlux()`/`asPublisher()`.
6. **Using `Flux.asFlow()` without kotlinx-coroutines-reactive:** the import will not work.
7. **Using `Flow.asFlux()` without kotlinx-coroutines-reactor:** the corresponding adapter is missing.
8. **Trying to emit `Flow<T?>` through Flux:** Reactive Streams forbids null. Filter or encode null.
9. **Losing empty/error during bridging:** always verify null, exceptions, and completion.
10. **Calling subscribe separately in a service:** creates a separate subscription, breaking coupling with the HTTP request and transaction.
11. **Calling collect/toList on an infinite Flow:** never completes and can use unbounded memory.
12. **Assuming Flow streams HTTP in every media type:** JSON arrays may buffer; use NDJSON/SSE appropriately.
13. **Assuming suspend makes JDBC/JPA non-blocking:** JDBC remains blocking.
14. **Using `withContext(Dispatchers.IO)` for every R2DBC call:** unnecessary, adding context/thread switches without clear benefit.
15. **Calling `GlobalScope.launch` in a controller:** side effects run outside the request lifecycle.
16. **Catching Exception and swallowing CancellationException:** delays or hides cancellation.
17. **Calling `awaitFirst` on a Flux when all elements are needed:** remaining elements may be cancelled.
18. **Using `Flow.map` with a suspend call expecting parallel execution:** `map` is sequential by default.
19. **Overly high `flatMapMerge` concurrency:** can overload downstream/DB pools.
20. **Not propagating `ReactorContext` in manual integrations:** transaction/security/tracing metadata may be lost.
21. **Using imperative transactions for R2DBC coroutines:** reactive manager/context is required.
22. **Holding a transaction across a long or infinite Flow:** risks holding connections and locks too long.
23. **Auto-retrying non-idempotent writes after cancellation:** can cause duplicate side effects.
24. **Tests checking only single-item values:** miss empty/error/cancel/ordering/media-type bugs.
25. **Running Kotlin and Reactor adapters across modules with mismatched coroutines versions:** prone to runtime errors or unexpected behavior; align via BOM.

## 21. Checklist for inspecting a Kotlin ↔ Reactor boundary

- Is it clear whether the input is a Mono, Flux, Flow, or suspending function?
- Is the conversion chosen appropriately for 0..1 or 0..N?
- Can the Mono complete empty? Is a nullable type used if needed?
- Does the Flow emit nullable items? Are they handled before `asFlux`?
- Are official adapters from `kotlinx-coroutines-reactive`/`reactor` used?
- Are `block`, `runBlocking`, `join`, or `subscribe` called inside HTTP requests?
- Can the caller cancel the request and stop upstream work?
- Are errors propagated or mapped with the right semantics?
- Are buffer/prefetch/concurrency settings appropriate?
- Is a stream being converted to a List unintentionally?
- Does the WebFlux response media type match JSON/NDJSON/SSE?
- Is `CoroutineCrudRepository` or a truly reactive driver used?
- Do reactive transactions share the same context across operations?
- Are `ReactorContext` and needed context propagation preserved?
- Are suspend endpoints, Flow endpoints, Mono/Flux adapters, and empty/cancel cases tested?
- Are logging/tracing/security verified when the pipeline switches schedulers?

## 22. Self-check questions

**1.** Which Kotlin API corresponds to `Mono<T>`? Usually a `suspend fun` returning `T`, or `T?` when it can be empty.

**2.** Which Kotlin API corresponds to `Flux<T>`? `Flow<T>` for a multi-element sequence.

**3.** What does `Mono.empty()` with `awaitSingle()` cause? `NoSuchElementException`.

**4.** What does `Mono.empty()` with `awaitSingleOrNull()` return? `null`.

**5.** Which module contains `Flux.asFlow()`? `kotlinx-coroutines-reactive`.

**6.** Which module contains `Flow.asFlux()`? `kotlinx-coroutines-reactor`.

**7.** Can `Flow.asFlux()` be used directly with `Flow<String?>`? No, because Reactive Streams forbids `onNext(null)`.

**8.** Does `mono { ... }` run immediately when created? No, it creates a cold Mono that starts the coroutine upon subscription.

**9.** What happens when a subscriber cancels a Flux from `Flow.asFlux`? The coroutine collecting the source is cancelled via the adapter.

**10.** Can `Flow.map` call a suspend function? Yes, though it processes sequentially by default.

**11.** What is `Flow.asFlow().buffer(16)` for? Tuning the buffer/prefetch size of the Publisher → Flow bridge.

**12.** Does WebFlux accept suspend controllers and Flow return types directly? Yes, when the appropriate coroutine dependencies are present.

**13.** Does `awaitBodyOrNull` automatically turn HTTP 404 into null? No; `retrieve()` still treats 4xx/5xx as errors by default.

**14.** When is `TransactionalOperator.executeAndAwait` needed? When you want a reactive transaction wrapping a suspending block.

**15.** Why is `GlobalScope.launch` inappropriate in a controller? It detaches lifecycle, cancellation, and context from the HTTP request.

**16.** Does a `suspend fun` calling JDBC directly become non-blocking? No, JDBC remains blocking.

**17.** Does every returning Flow stream each JSON record immediately? No, it depends on media type, codec, and buffering.

**18.** Which signals should be tested at a bridge? Value, empty, error, complete, cancellation, and demand/backpressure when streaming.

**Key takeaway:** Kotlin coroutines and Reactor can work together safely as long as boundaries are clearly defined. Use `awaitSingle`/`awaitSingleOrNull` for Mono, `asFlow` for Flux, `asFlux`/`asPublisher` for Flow, and `mono`/`flux` builders when Java APIs require Reactor. Preserve cardinality, nullability, cancellation, backpressure, and Reactor Context. Spring WebFlux supports `suspend`/`Flow` directly; there is no need to manually subscribe or block in controllers/services. For databases and transactions, use reactive drivers together with Spring-supported coroutine/reactive transaction mechanisms.

**Official documentation:**
- [Spring Framework 6.2 — Kotlin Coroutines](https://docs.spring.io/spring-framework/reference/6.2/languages/kotlin/coroutines.html)
- [Spring Boot 3.5 — Kotlin Support](https://docs.spring.io/spring-boot/3.5/reference/features/kotlin.html)
- [Spring Data Relational — Coroutine repositories](https://docs.spring.io/spring-data/relational/reference/kotlin/coroutines.html)
- [kotlinx.coroutines — Reactor integration](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactor/)
- [kotlinx.coroutines — Reactive Streams integration](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactive/)
- [kotlinx.coroutines — awaitSingle](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactor/kotlinx.coroutines.reactor/await-single.html)
- [kotlinx.coroutines — awaitSingleOrNull](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactor/kotlinx.coroutines.reactor/await-single-or-null.html)
- [kotlinx.coroutines — ReactorContext](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactor/kotlinx.coroutines.reactor/-reactor-context/)
- [Spring Framework 6.2 — WebClient Kotlin extension reference](https://docs.spring.io/spring-framework/reference/6.2/languages/kotlin/extensions.html).