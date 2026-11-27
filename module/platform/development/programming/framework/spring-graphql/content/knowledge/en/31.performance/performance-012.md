# Reactive resolvers and backpressure

In Spring for GraphQL, resolvers can return synchronous values, a CompletionStage, or reactive types such as Mono and Flux. When used properly, reactive resolvers connect GraphQL cleanly to R2DBC, WebClient, message streams, and asynchronous services. Backpressure regulates how much data is emitted from a source to its subscriber, which is especially important for Subscriptions and continuous streaming pipelines.

## Objectives

After this lesson, you will be able to:

- Explain how Spring for GraphQL adapts Mono and Flux into GraphQL results.
- Choose Mono or Flux appropriately for a field's return type.
- Distinguish Flux in Query/Mutation from Flux in Subscription.
- Understand backpressure, demand, requests, and cancellation in Reactive Streams.
- Regulate concurrency, prefetch, and buffering in Reactor.
- Combine reactive resolvers with R2DBC, WebClient, and DataLoader.
- Handle errors, timeouts, and cancellation in reactive pipelines.
- Test reactive resolvers and Subscriptions using StepVerifier and GraphQlTester.
- Avoid common mistakes such as block(), manual subscribe(), and unbounded buffers.

## 1. Reactive resolvers in Spring for GraphQL

GraphQL Java executes each field through a DataFetcher. Spring for GraphQL allows controller methods and DataFetchers to return reactive types such as Mono and Flux.

Example controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public Flux<Book> latestBooks(@Argument int first) {
        return bookService.findLatest(first);
    }
}
~~~

Spring for GraphQL registers methods annotated with @QueryMapping, @MutationMapping, @SubscriptionMapping, and @SchemaMapping as DataFetchers. These methods can return direct values, Mono, Flux, or other supported asynchronous types.

Reactive resolvers are useful when data comes from:

- R2DBC or a reactive repository.
- WebClient calling another service.
- A reactive Redis client.
- A message source or event publisher.
- A Reactor pipeline combining multiple data sources.

Being reactive does not automatically make a blocking operation non-blocking. If an underlying service uses JDBC or blocking HTTP calls, merely wrapping the result in a Mono does not free the blocked thread.

## 2. How do Mono and Flux differ?

Reactor provides two commonly used publisher types:

| Type | Element count | Common meaning |
|---|---:|---|
| Mono<T> | 0 or 1 | A single object, lookup result, or single async operation |
| Flux<T> | 0 to N | A list, event stream, or multiple results |

Example:

~~~java
Mono<Book> book = bookRepository.findById("b-01");

Flux<Book> books = bookRepository.findLatest();
~~~

Mono can complete empty without emitting any element, emit one element and complete, or terminate with an error. Flux can emit multiple elements over time and complete, or terminate with an error.

These types represent results in Java. The GraphQL SDL still declares standard GraphQL types:

~~~graphql
type Query {
  bookById(id: ID!): Book
  latestBooks(first: Int!): [Book!]!
}
~~~

Field bookById returns a Book or null. Field latestBooks returns a list of Books. SDL has no Mono or Flux types.

## 3. How does Spring for GraphQL adapt reactive DataFetchers?

Spring for GraphQL's default GraphQlSource builder supports DataFetchers returning Mono and Flux.

Behavior depends on the operation type:

- For regular Queries and Mutations, Mono is adapted into a CompletableFuture for GraphQL Java.
- For Queries and Mutations, Flux is collected into a List and then adapted into a CompletableFuture.
- For Subscriptions, the publisher is preserved as a Reactive Streams Publisher to emit multiple GraphQL responses over time.

This distinction is crucial. A Query resolver returning Flux<Book> does not mean the HTTP response streams each Book as soon as it is emitted. Spring for GraphQL collects the elements of Flux into a List to build the field result, and then GraphQL returns the operation response.

Example:

~~~java
@QueryMapping
public Flux<Book> latestBooks(@Argument int first) {
    return bookService.findLatest(first);
}
~~~

With SDL:

~~~graphql
type Query {
  latestBooks(first: Int!): [Book!]!
}
~~~

Spring for GraphQL waits for the Flux to complete and aggregates the Books into a List inside the GraphQL result. The client receives a single response containing the list, not a series of separate responses for each Book.

Therefore, to bound memory, limit element counts with pagination or take(). Never return an infinite Flux from a Query or Mutation because GraphQL will wait forever for the publisher to complete in order to build a List.

## 4. Using Mono for single-result Queries and Mutations

Mono fits when a field returns at most one object or scalar.

Example service:

~~~java
@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Mono<Book> findById(String id) {
        return repository.findById(id);
    }
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> bookById(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

For a Mutation, Mono also fits when a create or update operation returns a single result:

~~~java
@MutationMapping
public Mono<Book> addBook(@Argument BookInput input) {
    return bookService.addBook(input);
}
~~~

There is no need to call block() to unwrap the Book before returning. The GraphQL runtime awaits the CompletionStage created from Mono and continues assembling the response once data is ready.

If Mono completes empty, a nullable field receives null. If the SDL declares the field non-null, returning null triggers a GraphQL execution error and null propagation per schema rules.

## 5. Using Flux for list fields in Queries

Flux fits list fields when data is supplied as a reactive stream.

~~~graphql
type Query {
  latestBooks(first: Int!): [Book!]!
}
~~~

~~~java
@QueryMapping
public Flux<Book> latestBooks(@Argument int first) {
    int pageSize = Math.min(Math.max(first, 1), 100);

    return bookService.findLatest(pageSize)
            .take(pageSize);
}
~~~

take(pageSize) limits how many elements the pipeline emits. Once enough elements arrive, the downstream publisher cancels the upstream subscription.

Even though the data source is a Flux, Spring for GraphQL still collects the elements into a List for a normal Query. This means:

- Flux can read data incrementally from upstream.
- Reactive operators can throttle data requests.
- The GraphQL response still retains the collected list in memory before serializing.
- Memory still scales with the number of returned elements.

Do not use Flux as a replacement for pagination. For large datasets, enforce page size limits directly in the repository/database rather than loading everything and calling take().

## 6. Subscription is the streaming case

Subscriptions differ from Queries and Mutations. A subscription registers to receive events over time, so its publisher does not need to complete after one element.

Schema:

~~~graphql
type Subscription {
  bookAdded: BookEvent!
}

type BookEvent {
  id: ID!
  book: Book!
  occurredAt: String!
}
~~~

Controller:

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<BookEvent> bookAdded() {
        return eventService.events();
    }
}
~~~

When a client subscribes to bookAdded, Spring for GraphQL keeps the publisher open, and each emitted event goes through GraphQL execution to resolve selected fields.

Subscriptions require a streaming-capable transport, such as WebSocket or HTTP Server-Sent Events (SSE). Standard HTTP POST request-response cannot return a continuous stream of events.

Flux in a Subscription is a true Reactive Streams Publisher. It can continue emitting events until the source completes, errors, or the subscription is cancelled.

## 7. What is backpressure?

Backpressure is the mechanism by which a subscriber informs upstream how many elements it is ready to receive.

In Reactive Streams, a subscriber requests data by calling request(n) on its Subscription:

- request(1): requests one element.
- request(10): requests up to ten elements.
- request(Long.MAX_VALUE): requests unlimited elements, commonly called unbounded demand.
- cancel(): cancels the subscription and asks upstream to stop emitting data.

Backpressure keeps a producer from emitting data faster than a consumer can process it when every stage in the pipeline supports demand signaling.

Example of a source emitting 1,000 events while the consumer requests elements incrementally:

~~~java
Flux<Integer> numbers = Flux.range(1, 1_000)
        .doOnRequest(n ->
                log.debug("Upstream received demand: {}", n));
~~~

When the subscriber requests 5 elements, upstream can emit 5 elements and wait for the next demand signal.

Backpressure is not a fixed rate limiter. It is a demand signal propagated through the publisher/subscriber chain. Each operator can alter how data is requested, buffered, or prefetched.

## 8. Backpressure in Queries differs from Subscriptions

Distinguish the two cases:

**Queries and Mutations**

Spring for GraphQL collects Flux into a List before finishing the GraphQL response. The client receives a single complete JSON response for the operation. An HTTP client cannot ask the server to send just 5 more items of the same list after receiving part of the response.

If a Query returns a huge Flux, collecting it into a List can consume substantial memory. Backpressure inside the Reactor pipeline can throttle upstream, but it does not turn a GraphQL Query into a response stream.

**Subscriptions**

A Subscription's publisher is kept alive to emit multiple GraphQL responses. As the transport consumes events, demand and cancellation can propagate through the Reactive Streams publisher.

However, actual throttling also depends on the transport, event source, and operators in the pipeline. A message broker or hot source may not be able to slow down emissions to match subscriber demand. In those cases, configure buffering, dropping, latest-only, or rate-limiting policies suited to business requirements.

## 9. How does backpressure flow through the pipeline?

A reactive pipeline typically involves multiple components:

~~~text
Database / Event source
        |
        v
Repository Publisher
        |
        v
Service operators
        |
        v
GraphQL DataFetcher
        |
        v
GraphQL execution
        |
        v
HTTP streaming transport
        |
        v
Client subscriber
~~~

When the client or transport requests fewer events, demand signals can propagate backward through the publishers to the data source, provided every layer supports Reactive Streams.

Example with a Subscription:

1. The event source creates a publisher.
2. GraphQL subscribes to the publisher.
3. Each event is resolved into a GraphQL result.
4. The transport sends the result to the client.
5. The subscriber requests more events or cancels the subscription.
6. Demand/cancellation propagates back through the pipeline when layers support it.

If any layer crosses into a blocking API or subscribes independently on its own, demand signals can be lost at that boundary.

## 10. Regulating concurrency with flatMap and concatMap

flatMap allows processing multiple elements concurrently. This is helpful when each element needs an asynchronous service call, but unbounded concurrency can overwhelm connection pools or downstream services.

Example capping concurrency at 8 simultaneous calls:

~~~java
Flux<BookDetails> details = bookRepository.findLatest()
        .flatMap(bookService::loadDetails, 8);
~~~

The concurrency parameter bounds how many inner publishers run simultaneously. When downstream slows down, Reactor also adjusts demand along the pipeline, though you should still pay attention to operator prefetch and buffering.

If sequential processing is needed, use concatMap:

~~~java
Flux<BookResult> results = bookRepository.findPending()
        .concatMap(bookService::process);
~~~

concatMap processes inner publishers one at a time in order, limiting concurrency and preserving emission order. In trade-off, throughput may be lower than flatMap.

| Operator | Characteristics | When to use |
|---|---|---|
| flatMap(mapper, concurrency) | Processes multiple inner publishers concurrently | Calling independent services |
| concatMap(mapper) | Processes sequentially, preserves order | Order-dependent tasks |
| flatMapSequential(mapper, concurrency) | Processes concurrently while emitting in source order | Needs concurrency and preserved ordering |

Do not raise concurrency merely to chase throughput. Measure limits of your database pool, HTTP connection pool, and downstream services.

## 11. Regulating demand with limitRate

limitRate splits downstream demand into smaller request batches sent upstream.

Example:

~~~java
Flux<Book> books = bookRepository.findAll()
        .limitRate(64);
~~~

This operator helps prevent requesting an overly large chunk of data from upstream all at once. However, it does not limit the total number of elements in the Flux, nor does it perform database pagination.

If you need to cap total element count, use take(n):

~~~java
Flux<Book> firstHundred = bookRepository.findAll()
        .take(100);
~~~

Distinguish:

- limitRate(64): regulates how data is requested in batches.
- take(100): lets at most 100 elements pass downstream.
- Pagination: instructs the data source to load only a bounded page.

In GraphQL Queries, pagination in the repository/database is usually the primary mechanism for bounding the final List size.

## 12. Buffering and strategies when producers outpace consumers

Some data sources are hot publishers or event sources that cannot wait for subscriber demand. Examples include devices streaming telemetry continuously or systems consuming broker events.

When the producer outpaces the consumer, choose an overflow policy:

| Strategy | Behavior | Best fit |
|---|---|---|
| Bounded buffer | Holds events in a queue up to a limit | Short bursts where events must be kept |
| Drop | Discards events when downstream is not ready | Metrics or telemetry where loss is acceptable |
| Latest | Keeps only the newest value | Current state, live dashboards |
| Error on overflow | Signals an error and cancels source when buffer fills | Detecting overload explicitly |

Example bounded buffer:

~~~java
Flux<BookEvent> events = eventSource.events()
        .onBackpressureBuffer(
                256,
                overflowEvent -> log.warn(
                        "Event buffer overflow: {}", overflowEvent));
~~~

The overload with maxSize requests unbounded demand from upstream and buffers up to 256 events at the operator boundary when downstream is not ready. Once capacity is exceeded, the overflow callback runs and upstream is cancelled with an overflow error. Thus, a bounded buffer protects memory without slowing down the producer; it only absorbs bursts within the configured bound. Never use an unbounded buffer for long-lived event streams because memory can grow without limit.

Example dropping events:

~~~java
Flux<MetricEvent> metrics = metricSource.events()
        .onBackpressureDrop(event ->
                log.debug("Dropping metric event {}", event.id()));
~~~

The drop operator also requests unbounded demand from upstream and discards items when downstream has no demand. Use drop only if business logic tolerates lost events. For orders, payments, or audit events, dropping items can corrupt business state.

## 13. Avoiding accidental unbounded demand

Several common subscription patterns immediately request unbounded demand, for example:

- subscribe() and many of its lambda overloads.
- block(), blockFirst(), and blockLast().
- Iterating via toIterable() or toStream().

Therefore, avoid calling these methods carelessly inside reactive resolvers.

Example of what NOT to do:

~~~java
@QueryMapping
public Book bookById(@Argument String id) {
    return bookService.findById(id).block();
}
~~~

This blocks the thread handling the GraphQL request, defeats non-blocking execution, and can exhaust threads under load.

Also avoid subscribing manually inside a controller:

~~~java
@QueryMapping
public String refresh() {
    bookService.refresh().subscribe();
    return "started";
}
~~~

The GraphQL engine loses control over this publisher's lifecycle. It cannot await the result, manage errors, or propagate request cancellation.

Return the publisher directly:

~~~java
@MutationMapping
public Mono<Book> refreshBook(@Argument String id) {
    return bookService.refresh(id);
}
~~~

The framework subscribes and awaits it according to the GraphQL operation lifecycle.

## 14. Combining reactive resolvers with R2DBC

R2DBC provides reactive access to relational databases. Repositories can return Mono or Flux.

Example:

~~~java
public interface BookRepository
        extends ReactiveCrudRepository<Book, String> {

    Flux<Book> findByPublishedYearGreaterThan(int year);
}
~~~

Service:

~~~java
@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Flux<Book> findRecentBooks(int year) {
        return repository.findByPublishedYearGreaterThan(year)
                .limitRate(32);
    }
}
~~~

Controller:

~~~java
@QueryMapping
public Flux<Book> recentBooks(@Argument int year) {
    return bookService.findRecentBooks(year);
}
~~~

R2DBC supports demand at the driver and publisher layers. However, if a GraphQL Query collects Flux into a List, the full final result is still buffered in memory to serialize the response.

For large datasets, pair R2DBC with pagination and maximum page size limits. Never expose findAll() on a public GraphQL field if row counts are unbounded.

## 15. Combining reactive resolvers with WebClient

WebClient returns Mono or Flux and fits when a resolver calls another HTTP service.

Example:

~~~java
@Service
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<Inventory> findInventory(String bookId) {
        return webClient.get()
                .uri("/inventory/{bookId}", bookId)
                .retrieve()
                .bodyToMono(Inventory.class);
    }
}
~~~

Resolver:

~~~java
@Controller
public class BookInventoryController {

    private final InventoryClient inventoryClient;

    public BookInventoryController(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @SchemaMapping(typeName = "Book", field = "inventory")
    public Mono<Inventory> inventory(Book book) {
        return inventoryClient.findInventory(book.id());
    }
}
~~~

The GraphQL engine waits for Mono to complete to populate the inventory field. No block() call is needed to fetch the WebClient response.

If a query returns many Books and each Book calls the inventory service individually, it can trigger many HTTP requests. Consider batch endpoints, DataLoader, caching, or concurrency caps to avoid overloading downstream services.

## 16. Combining DataLoader and reactive batch mapping

Spring for GraphQL supports reactive return types in @BatchMapping. Methods can return Mono<Map<K,V>> or Flux<V>.

Example:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::authorId)
                .distinct()
                .toList();

        return authorService.findAllByIds(authorIds)
                .map(authors -> mapAuthors(books, authors));
    }
}
~~~

Batch mapping groups multiple parent Books into a single call. The publisher returns a Map associating each Book with its corresponding Author.

If the method returns Flux<V>, emitted values must match the exact order of parent objects passed into the batch method. If order does not match, Authors can be assigned to the wrong Books.

Reactive DataLoaders avoid blocking threads while waiting for batch queries, while DataLoader batching reduces backend calls. The two goals complement each other.

## 17. Cancellation and timeouts

Cancellation occurs when the consumer no longer needs data. For example:

- The client closes the Subscription connection.
- The GraphQL request times out.
- A pipeline using take(n) has received enough elements.
- Downstream cancels the subscription.

A reactive pipeline should propagate cancellation back to the data source to stop unneeded work.

Example:

~~~java
Flux<BookEvent> events = eventService.events()
        .doOnCancel(() ->
                log.info("Book subscription cancelled"));
~~~

Spring for GraphQL provides TimeoutWebGraphQlInterceptor for web transports. When a request exceeds the configured duration, the interceptor sends a cancellation signal up the chain and reactive DataFetchers can automatically cancel ongoing work.

Spring Boot configuration:

~~~java
@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(
                Duration.ofSeconds(5));
    }
}
~~~

Request timeouts and Subscription timeouts do not necessarily share the same semantics. A valid Subscription may stay open long-term, so configure timeouts aligned with the transport and connection policy rather than applying a short request timeout to the entire stream.

Cancellation is only effective when publishers and data sources react to cancel signals. A blocking operation cannot be halted safely merely because downstream cancelled its publisher.

## 18. Error handling in reactive pipelines

Errors in Mono or Flux propagate as error signals. Spring for GraphQL translates DataFetcher errors into GraphQL errors via DataFetcherExceptionResolver.

You can map domain errors before returning the publisher:

~~~java
@QueryMapping
public Mono<Book> bookById(@Argument String id) {
    return bookService.findById(id)
            .switchIfEmpty(Mono.error(
                    new BookNotFoundException(id)));
}
~~~

You can use onErrorMap to translate technical errors into domain exceptions:

~~~java
public Mono<Book> findBook(String id) {
    return repository.findById(id)
            .onErrorMap(
                    DataAccessException.class,
                    ex -> new BookServiceException(
                            "Unable to load book", ex));
}
~~~

Use onErrorResume when a valid fallback exists:

~~~java
public Mono<BookRecommendation> recommendations(String bookId) {
    return recommendationClient.find(bookId)
            .onErrorResume(
                    RecommendationUnavailableException.class,
                    ex -> Mono.just(BookRecommendation.empty()));
}
~~~

Never use onErrorResume to silently turn every error into empty data. Doing so hides system failures and misleads clients about results.

For Subscriptions, errors can happen after the publisher is created and the client has subscribed. DataFetcherExceptionResolver cannot handle error signals emitted after the DataFetcher returned the publisher. Spring for GraphQL provides SubscriptionExceptionResolver to map subscription publisher errors into GraphQL errors sent over the transport.

## 19. Keeping pipelines non-blocking and managing Schedulers

A reactive pipeline is truly non-blocking only when operations inside it do not block threads.

When using R2DBC or WebClient, you typically do not need to switch schedulers per request. Those libraries already use non-blocking I/O.

If calling a blocking library is unavoidable, isolate the work on boundedElastic:

~~~java
Mono<Book> book = Mono.fromCallable(
                () -> legacyBookService.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Never run blocking JDBC or file I/O directly on the WebFlux event loop. At the same time, do not use boundedElastic to hide an unbounded blocking design; monitor queues and thread counts.

Key guidelines:

- Do not call block() in resolvers.
- Do not call subscribe() to detach work from the GraphQL lifecycle.
- Do not sprinkle publishOn or subscribeOn arbitrarily across every pipeline.
- Bound concurrency when calling downstream services.
- Configure timeouts for I/O that could hang.
- Ensure context propagation when switching schedulers.
- If an imperative application uses JDBC, consider a synchronous model with an executor or virtual threads rather than faking reactive by wrapping blocking calls.

## 20. Context propagation in reactive resolvers

With WebFlux, Spring for GraphQL supports propagating Reactor Context from the transport layer to reactive DataFetchers. Context can carry security context, tracing context, or metadata added by a WebGraphQlInterceptor.

Example reading context inside a Reactor pipeline:

~~~java
public Mono<Book> currentBook(String id) {
    return Mono.deferContextual(contextView -> {
        String tenantId = contextView.get("tenantId");

        return bookService.findByTenantAndId(tenantId, id);
    });
}
~~~

The context key must be populated in an interceptor or appropriate component before the resolver reads it.

Never pass user ID or tenant ID via GraphQL variables and treat them as trusted identity. Authentication context must come from the request's security mechanism.

If using publishOn or subscribeOn, verify context propagation with your current library versions and configuration. Reactor Context is bound to the subscription, not standard ThreadLocal.

## 21. Subscriptions can emit events out of order

In a GraphQL Subscription, each event is resolved into a GraphQL response. Fields within an event can be fetched asynchronously. Therefore, when multiple events are in flight, responses may be sent over the transport out of original event order.

Spring for GraphQL allows enabling:

~~~java
SubscriptionExecutionStrategy.KEEP_SUBSCRIPTION_EVENTS_ORDERED
~~~

to buffer events and preserve upstream order.

You can set this flag in GraphQLContext using a custom Instrumentation:

~~~java
public class SubscriptionOrderInstrumentation
        extends SimplePerformantInstrumentation {

    @Override
    public InstrumentationContext<ExecutionResult> beginExecution(
            InstrumentationExecutionParameters parameters,
            InstrumentationState state) {

        parameters.getGraphQLContext().put(
                SubscriptionExecutionStrategy.KEEP_SUBSCRIPTION_EVENTS_ORDERED,
                true);

        return SimpleInstrumentationContext.noOp();
    }
}
~~~

Preserving order may require buffering events whose fields have finished resolving while waiting on an earlier event. This increases latency and memory when one event processes slowly. Enable it only when event ordering is a business requirement.

If events are independent and clients do not require strict ordering, letting GraphQL send results as they complete can reduce latency.

## 22. Testing backpressure with StepVerifier

StepVerifier lets you test publishers without writing a custom Subscriber.

Example verifying demand:

~~~java
@Test
void shouldRespectRequestedDemand() {
    Flux<Integer> source = Flux.range(1, 5)
            .doOnRequest(n ->
                    log.info("Requested: {}", n));

    StepVerifier.create(source, 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .thenCancel()
            .verify();
}
~~~

The test starts with zero demand, then requests 2 elements and cancels the subscription. This checks how the publisher responds to request and cancel signals.

You can also test a resolver returning Mono:

~~~java
@Test
void shouldReturnBookAsynchronously() {
    StepVerifier.create(bookService.findById("b-01"))
            .assertNext(book ->
                    assertThat(book.id()).isEqualTo("b-01"))
            .verifyComplete();
}
~~~

StepVerifier is great for testing service publishers, cancellation, timeouts, errors, and demand. It does not prove a GraphQL HTTP transport streams Query responses; test transports separately.

## 23. Testing GraphQL Subscriptions

GraphQlTester supports executing Subscriptions via executeSubscription(). The result can be converted to a Flux for use with StepVerifier.

Example:

~~~java
@Test
void shouldReceiveBookEvents() {
    Flux<BookEvent> events = graphQlTester.document("""
            subscription {
                bookAdded {
                    id
                    book {
                        id
                        title
                    }
                }
            }
            """)
            .executeSubscription()
            .toFlux("bookAdded", BookEvent.class);

    StepVerifier.create(events)
            .expectNextMatches(event ->
                    event.book().id().equals("b-01"))
            .thenCancel()
            .verify();
}
~~~

The test requires a controllable Subscription source in the fixture. After emitting a test event, StepVerifier asserts the event is received; thenCancel() verifies stream cancellation.

For transport integration tests, configure WebSocket or SSE accordingly. ExecutionGraphQlServiceTester can also help test GraphQL execution without network transport overhead.

## 24. Common pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Query never completes | Resolver returns a Flux that never completes | Keep Queries finite; reserve infinite publishers for Subscriptions |
| Query returns an oversized list | Flux is aggregated into a List | Paginate and cap page size |
| Thread gets blocked | Calling block() or using JDBC directly | Return publishers directly or isolate blocking work |
| Resolver keeps running after client cancels | Manual subscribe() in controller or source ignores cancel | Return publisher directly and verify cancellation |
| Memory grows on slow Subscription | Unbounded buffer or producer faster than consumer | Use bounded buffers and overflow policies |
| Events dropped | Inappropriate use of onBackpressureDrop | Choose buffering, retries, or a durable broker per business needs |
| Too many concurrent downstream calls | Unbounded concurrency in flatMap | Use flatMap with an explicit concurrency cap |
| List results arrive out of order | Using flatMap or unordered batch Flux | Use concatMap, flatMapSequential, or key-based mapping |
| Subscription events arrive out of order | Nested fields complete asynchronously | Enable KEEP_SUBSCRIPTION_EVENTS_ORDERED when needed |
| Subscription errors are not mapped | Error occurs after publisher was returned | Configure SubscriptionExceptionResolver |
| Context is lost | Switching schedulers or using ThreadLocal in reactive chains | Use Reactor Context and verify context propagation |
| Backpressure does not reach the source | Blocking layer or non-compliant publisher in chain | Inspect each boundary and upstream source |

## 25. Reactive resolver implementation checklist

Before taking reactive resolvers to production:

- [ ] Use Mono for 0..1 results and Flux for 0..N results.
- [ ] SDL declares real GraphQL types, never Mono/Flux in the schema.
- [ ] Understand Flux in Query/Mutation is aggregated into a List.
- [ ] Never return an infinite Flux from a Query or Mutation.
- [ ] Use Subscription for continuous event streams.
- [ ] Subscription transport supports WebSocket or SSE.
- [ ] Bound page sizes and element counts on Queries.
- [ ] Control concurrency and prefetch in pipelines.
- [ ] Never use unbounded buffers for continuous sources.
- [ ] Choose an overflow policy aligned with business requirements.
- [ ] Never call block() or manual subscribe() inside resolvers.
- [ ] Isolate blocking I/O if it cannot be replaced with a reactive driver.
- [ ] Configure timeouts and handle cancellation.
- [ ] Handle errors for both DataFetchers and Subscription publishers.
- [ ] Verify context propagation.
- [ ] Test demand, cancellation, and event streams with StepVerifier.
- [ ] Measure memory, latency, and event emission rates under increasing load.

## Conclusion

Reactive resolvers allow Spring for GraphQL to work seamlessly with Mono, Flux, and asynchronous data sources. Mono fits single results; Flux fits multiple results or event streams. However, Flux in Queries and Mutations is collected into a List by Spring for GraphQL, whereas Flux in Subscriptions stays a Reactive Streams Publisher streaming multiple GraphQL responses.

Backpressure regulates demand between subscribers and upstream. To benefit from it, control concurrency, prefetch, buffering, and cancellation across the entire pipeline. Combine reactive resolvers with pagination, DataLoader, timeouts, and appropriate overflow policies. Avoid block(), manual subscribe(), and unbounded sources to keep GraphQL execution stable under load.

## References

- [Spring for GraphQL — Request Execution, Reactive DataFetcher](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Subscriptions](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Reactive Streams — Specification](https://www.reactive-streams.org/)
