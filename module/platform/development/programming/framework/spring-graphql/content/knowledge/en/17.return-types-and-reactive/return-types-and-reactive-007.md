# Kotlin suspend functions in Spring for GraphQL

Spring for GraphQL supports Kotlin coroutines in annotated controllers. As a result, a `suspend` function can handle a Query, Mutation, or field mapping and return a single result without needing to manually wrap it in `CompletableFuture` or `Mono`.

`suspend` does not automatically make every call non-blocking. A coroutine only yields execution when calling a genuinely suspending function or switching to an appropriate dispatcher. If the method still invokes synchronous JDBC/JPA on the current thread, that thread remains blocked. Distinguish coroutine APIs, reactive APIs, and blocking libraries when designing resolvers.

## Where are coroutines used in GraphQL?

In Kotlin, a `suspend` function can pause and resume after an asynchronous task completes. Spring for GraphQL recognizes suspend functions in annotated controllers and integrates them with GraphQL execution.

Common scenarios:

- Queries returning an object, scalar, or collection after calling a suspending service.
- Mutations performing an asynchronous write operation and returning a result.
- Field resolvers using `@SchemaMapping` calling a suspending service to fetch related data.
- Subscriptions returning `Flow<T>` to emit multiple events over time.

For example, a Query can use `suspend fun` instead of a synchronous method or `CompletableFuture`:

```graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
```

```kotlin
@Controller
class BookController(
    private val bookService: BookService
) {
    @QueryMapping
    suspend fun book(@Argument("id") id: String): Book? {
        return bookService.findById(id)
    }
}
```

When GraphQL executes the `Query.book` field, Spring invokes the suspend function and awaits the result using coroutine support. The `Book?` value can be a `Book` or `null`; SDL schema still determines whether the field is allowed to be null.

## Adding coroutine dependencies

To integrate coroutines with Spring for GraphQL, a Kotlin application needs the coroutine library and Reactor bridge. Example Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-reactor")
}
```

In a project using Spring Boot dependency management, let the BOM manage compatible versions instead of manually picking standalone coroutine versions. Kotlin applications with Spring typically also use the Kotlin Spring plugin and Kotlin reflection according to the project's base configuration.

`kotlinx-coroutines-reactor` provides integration between coroutines and Reactor, required for converting and coordinating with reactive APIs used by Spring. You do not need to use WebFlux just to declare `suspend`; coroutine support in annotated controllers does not mean the whole application must switch to WebFlux.

## Queries with suspend functions

A service can declare suspending APIs so the controller does not have to know how data is fetched:

```kotlin
interface BookService {
    suspend fun findById(id: String): Book?
}
```

The controller calls the service directly:

```kotlin
@Controller
class BookQueryController(
    private val bookService: BookService
) {
    @QueryMapping
    suspend fun book(@Argument("id") id: String): Book? =
        bookService.findById(id)
}
```

The function return type is `Book?`, not `Mono<Book>` or `CompletableFuture<Book>`. Spring for GraphQL recognizes suspend functions and coordinates results through coroutine integration.

Kotlin nullability should stay consistent with SDL. If the schema declares `book(id: ID!): Book!`, the controller must return a non-null `Book` or raise an appropriate error. If the schema declares `Book`, the controller can return `null` when not found. The Kotlin type system helps express intent in code, but the schema is the GraphQL contract seen by clients.

## Mutations with suspend functions

Mutations can also be suspend functions. Example schema accepting input and returning the updated book:

```graphql
input RenameBookInput {
  id: ID!
  title: String!
}

type Mutation {
  renameBook(input: RenameBookInput!): Book!
}
```

Kotlin input model and controller:

```kotlin
data class RenameBookInput(
    val id: String,
    val title: String
)

@Controller
class BookMutationController(
    private val bookService: BookService
) {
    @MutationMapping
    suspend fun renameBook(
        @Argument("input") input: RenameBookInput
    ): Book {
        return bookService.rename(input.id, input.title)
    }
}
```

Using `suspend` does not change GraphQL Mutation semantics. Top-level fields within the same mutation operation are still executed sequentially per GraphQL rules. Business transactions and atomicity still need to be implemented in the service or persistence layer.

## Field resolvers with suspend and `@SchemaMapping`

Coroutines are also helpful when a nested field needs to call an asynchronous service. Suppose `Book` holds `authorId`, while `Author` details are loaded separately:

```graphql
type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
```

```kotlin
@Controller
class BookFieldController(
    private val authorService: AuthorService
) {
    @SchemaMapping(typeName = "Book", field = "author")
    suspend fun author(@Source book: Book): Author? {
        return authorService.findById(book.authorId)
    }
}
```

`@Source` marks the parent object already resolved by GraphQL; `Book` is the source of the `Book.author` field. If the field has arguments, `@Argument` can be combined with the source parameter:

```graphql
type Book {
  translatedTitle(locale: String!): String
}
```

```kotlin
@SchemaMapping(typeName = "Book", field = "translatedTitle")
suspend fun translatedTitle(
    @Source book: Book,
    @Argument("locale") locale: String
): String? {
    return translationService.title(book.id, locale)
}
```

As with Java controllers, there is no need to write `@SchemaMapping` for fields that are simply read from existing properties/getters. Use dedicated resolvers when you need to call a service, compute values, transform data, or check permissions.

## Combining coroutines with reactive APIs

A service might currently use Reactor and return `Mono` or `Flux`. When you want to write the controller in coroutine style, you can convert `Mono` to a suspending result using extensions from `kotlinx-coroutines-reactor`.

```kotlin
import kotlinx.coroutines.reactor.awaitSingleOrNull

@Controller
class BookController(
    private val bookService: ReactiveBookService
) {
    @QueryMapping
    suspend fun book(@Argument("id") id: String): Book? {
        return bookService.findById(id).awaitSingleOrNull()
    }
}
```

`awaitSingleOrNull()` suspends the coroutine until the Mono emits a value, completes empty, or errors. If the Mono emits an error, the exception is propagated into the coroutine so Spring for GraphQL handles it as a field execution error.

For a `Mono` guaranteed to have a value, you can use `awaitSingle()`. Pick the await function matching the publisher's contract: do not use a function requiring an item if the source can complete empty.

When a service already exposes suspending APIs, calling those APIs directly is usually simpler than converting back and forth between `Mono` and coroutines. Avoid creating unnecessary conversion layers because they make execution flow and context harder to follow.

## Using coroutines to coordinate multiple calls

When a field needs data from multiple independent services, you can use `coroutineScope` and `async` to run suspending tasks concurrently:

```kotlin
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope

@QueryMapping
suspend fun bookDashboard(@Argument("id") id: String): BookDashboard =
    coroutineScope {
        val book = async { bookService.findByIdRequired(id) }
        val recommendations = async { recommendationService.forBook(id) }

        BookDashboard(
            book = book.await(),
            recommendations = recommendations.await()
        )
    }
```

`async` only achieves effective concurrency when the called functions genuinely suspend on asynchronous I/O or switch to an appropriate dispatcher. If both functions invoke synchronous JDBC on the same coroutine context, they can still block threads and will not magically become non-blocking.

`coroutineScope` ensures child coroutines belong to the operation's lifecycle. When one child fails, the scope applies structured concurrency and cancels remaining children per coroutine rules. Do not use `GlobalScope` to launch work tied to a GraphQL request because that work can outlive the request and be difficult to cancel on time.

## Subscriptions with Kotlin Flow

For Subscriptions, the server needs to emit multiple results over time. Kotlin `Flow<T>` is a fitting type to represent an asynchronous data stream. A controller can return `Flow` directly:

```graphql
type OrderStatusUpdate {
  orderId: ID!
  status: String!
}

type Subscription {
  orderStatusChanged(orderId: ID!): OrderStatusUpdate!
}
```

```kotlin
import kotlinx.coroutines.flow.Flow

@Controller
class OrderSubscriptionController(
    private val orderEventService: OrderEventService
) {
    @SubscriptionMapping
    fun orderStatusChanged(
        @Argument("orderId") orderId: String
    ): Flow<OrderStatusUpdate> {
        return orderEventService.watch(orderId)
    }
}
```

`Flow` is not the same as a `suspend fun` returning a single value. A suspend function produces one result per invocation; a `Flow` represents a sequence of values and is collected over the subscription's lifetime. Spring for GraphQL integrates `Flow` with Reactive Streams to turn each element into an execution result.

Flow is typically a cold stream: each collection may create a new subscription to the event source. If the source is a callback API, you can turn it into a Flow using `callbackFlow` and release the listener when the collector is cancelled:

```kotlin
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow

fun watchOrder(orderId: String): Flow<OrderStatusUpdate> = callbackFlow {
    val registration = eventSource.subscribe(orderId) { event ->
        trySend(event)
    }

    awaitClose {
        registration.close()
    }
}
```

`awaitClose` keeps the Flow open while there is a collector and runs cleanup when the subscription finishes or is cancelled. `eventSource` and the `registration` type are illustrative application APIs; check the result of `trySend` to handle closed channels or full buffers, and choose a buffer/overflow policy according to business requirements.

## Blocking I/O does not automatically become non-blocking

This is the most common misconception when migrating Java controllers to Kotlin coroutines. The `suspend` keyword does not make a blocking JDBC, JPA, or HTTP client call non-blocking.

Inappropriate example in a reactive application:

```kotlin
@QueryMapping
suspend fun book(@Argument("id") id: String): Book? {
    return blockingJpaRepository.findById(id).orElse(null)
}
```

The repository call still blocks the thread executing the coroutine until the database returns. If you need to keep a blocking library, offload that specific part to a dispatcher meant for blocking I/O:

```kotlin
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@QueryMapping
suspend fun book(@Argument("id") id: String): Book? =
    withContext(Dispatchers.IO) {
        blockingJpaRepository.findById(id).orElse(null)
    }
```

`Dispatchers.IO` is intended for blocking I/O and avoids occupying event-loop threads. For high-load systems, you can use a dedicated dispatcher backed by a bounded executor to isolate work and align limits with the connection pool. Do not move all code to `Dispatchers.IO` if the service is already non-blocking.

With Spring MVC and JPA, synchronous implementation can be appropriate if load is controlled. There is no need to add coroutines just for syntax. With WebFlux, prefer WebClient, R2DBC, or other non-blocking APIs; if JDBC/JPA is unavoidable, offload blocking calls and design transactions carefully.

## Transactions, security context, and cancellation

A coroutine can suspend and resume on a different thread. Therefore, do not assume every piece of `ThreadLocal`-bound data persists unchanged across a `suspend` function.

- **Transactions:** Traditional JDBC/JPA transactions are typically thread-bound. When using `withContext` to switch dispatchers, ensure the transaction wraps the right block of blocking work. With reactive transaction managers, use Spring's corresponding coroutine/reactive transaction support and test it thoroughly.
- **Security context:** If a resolver needs a principal or authorities, read them from the context established by Spring Security and use compatible context propagation. Never trust permissions passed via client-supplied arguments.
- **Reactor context:** When integrating Reactor and coroutines via `kotlinx-coroutines-reactor`, Reactor context can be carried into the coroutine context. Test propagation of trace IDs, security context, or tenants under your actual application setup.
- **Cancellation:** When a client cancels an operation or a connection drops, coroutines and Flows should cancel along with the execution lifecycle. Child work should be structured child coroutines; callback sources should be cleaned up with `finally` or `awaitClose`.

For write operations, do not launch a background coroutine and return the response before knowing the outcome if business logic requires the mutation to complete synchronously with the response. Background work needs its own queue, retry, and monitoring mechanisms.

## Error handling in suspend functions

Exceptions thrown from a suspend function enter GraphQL's error handling flow. You can use `DataFetcherExceptionResolver` in Spring for GraphQL to map business exceptions to public messages, error codes, and metadata.

Example controller throwing an error when a book is not found:

```kotlin
@QueryMapping
suspend fun book(@Argument("id") id: String): Book =
    bookService.findById(id)
        ?: throw BookNotFoundException(id)
```

Do not return stack traces, SQL statements, or infrastructure details in error messages. If the field is nullable, an error can turn that field into `null` while other fields still return data. If the field is Non-Null, null can propagate to parent fields according to GraphQL rules.

For Flow subscriptions, errors can occur after the client has already received some events. When the source emits an error, the Flow terminates and GraphQL sends error/operation-completion information over the transport. If the service retries internally, enforce limits and ensure no unintended duplicate events are emitted.

## Testing coroutine controllers

You can use `GraphQlTester` just as when testing Java controllers. Making a method `suspend` does not change how clients send GraphQL documents:

```kotlin
@Test
fun `book query returns requested book`() {
    graphQlTester.document("""
        query {
          book(id: "book-10") {
            id
            title
          }
        }
    """)
        .execute()
        .path("book.id")
        .entity(String::class.java)
        .isEqualTo("book-10")
}
```

For suspending services, you can use `kotlinx-coroutines-test` and `runTest` to test suspend logic deterministically. Integration controller tests should still run through `GraphQlTester` to verify Spring detects suspend functions, binds arguments, and processes results properly.

For Flow subscriptions, test multiple events, emission order, errors, completion, and cancellation. If the Flow wraps callbacks, verify `awaitClose` actually releases the listener when the client cancels the subscription.

Scenarios worth testing:

- Suspending Queries and Mutations return results matching SDL.
- Nullable and Non-Null mapping is consistent between Kotlin and schema.
- Arguments bind properly, including input objects.
- Exceptions map to GraphQL errors according to policy.
- Blocking I/O is offloaded away from the event loop when using WebFlux.
- Transactions, security context, and tracing propagate properly across dispatcher switches.
- Subscription Flows emit multiple events and clean up on cancellation.
- Child coroutines do not continue running past the operation's lifecycle.

## Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Spring does not recognize suspend function | Missing required coroutine integration or incompatible dependencies. | Check `kotlinx-coroutines-reactor` and Spring/Kotlin versions in use. |
| `suspend` function still slows down WebFlux | Calling blocking JDBC/JPA on the event loop inside. | Use non-blocking APIs or `withContext(Dispatchers.IO)` / a dedicated dispatcher. |
| `Mono` returned instead of expected value | Publisher not awaited in coroutine or wrong service API return type. | Use appropriate `await...` extension or stay consistent with reactive style. |
| Flow emits only one event | Flow source completes after first event or service emits only one value. | Inspect event source and collector lifecycle. |
| Listener remains alive after client leaves | Callback-backed Flow does not clean up on cancellation. | Use `callbackFlow` and `awaitClose` to unregister the listener. |
| Transaction lost when coroutine switches threads | Relying on ThreadLocal transaction from initial thread. | Place transaction at proper boundary or use appropriate reactive transaction integration. |
| Principal/trace ID missing | Context not propagated across dispatchers or Reactor bridge. | Configure context propagation and test with real security/tracing. |
| Work keeps running after request ends | Using detached coroutines like `GlobalScope` or ignoring cancellation. | Use structured concurrency and manage child coroutine lifecycles. |

## Key takeaways

Spring for GraphQL supports `suspend` functions in annotated controllers for Queries, Mutations, and field mappings. A suspend function returns a single result; Kotlin `Flow<T>` fits Subscriptions emitting multiple events. `@Argument`, `@Source`, `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` continue to be used in the familiar way.

Coroutines make asynchronous flows concise and provide structured concurrency, but they do not automatically make JDBC/JPA non-blocking. Use truly suspending/reactive APIs whenever possible; when blocking I/O is required, switch to an appropriate dispatcher. Manage transactions, security context, cancellation, errors, and Flow cleanup so resolvers behave reliably throughout the entire GraphQL operation lifecycle.
