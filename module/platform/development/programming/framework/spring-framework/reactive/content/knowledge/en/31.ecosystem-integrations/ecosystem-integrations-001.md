# Keeping the Publisher Contract Across Controllers, Services, and Data Access in Spring WebFlux

## 1. Goal: an end-to-end reactive chain

In a Spring WebFlux application, the controller, service, and data access layer should not be three separate execution worlds. They should **return and compose Publishers** within the same processing flow, from the HTTP request to the database and from the database back to the HTTP response.

Architecture example:

~~~text
HTTP GET /api/books/42
           |
           v
BookController.get(id)
           | Mono<BookView>
           v
BookService.findById(id)
           | Mono<Book>
           v
BookRepository.findById(id)
           | Mono<Book>
           v
R2DBC driver + database
           |
           +--- 1 Book -------> map(BookView::from) ---> HTTP 200 + JSON
           +--- empty --------> switchIfEmpty(...) ---> HTTP 404
           +--- onError ------> error handling -------> appropriate HTTP error
~~~

Each layer **describes a pipeline**; WebFlux's HTTP runtime subscribes when it needs to execute the request/response. No layer should call `subscribe()` on its own to trigger the next layer, and no layer should call `block()` to turn reactive data into a synchronous value.

The phrase “keeping the Publisher contract” has two meanings:

1. **Type contract:** methods return `Mono<T>`, `Flux<T>`, or `Publisher<T>` with the right cardinality, without pretending to be synchronous via an object extracted with `block()`.
2. **Execution contract:** preserve `onNext`, `onError`, `onComplete` signals, demand requests, cancellation, and the Reactor Context within the same subscription, without creating a “dangling” subscription in the middle.

Using a reactive API in the controller while running blocking JDBC/JPA on the event-loop will **not** produce a truly non-blocking chain. You need to look at all layers and the libraries they call.

## 2. What are Publisher, Mono, and Flux?

Reactive Streams defines the protocol between a Publisher and a Subscriber. The Publisher emits data according to the Subscriber's demand through a Subscription; the key signals are:

- `onSubscribe(subscription)`: the Subscriber receives the Subscription.
- `request(n)`: the Subscriber requests at most n next elements.
- `onNext(item)`: emits a valid element.
- `onError(error)`: terminates abnormally.
- `onComplete()`: terminates normally.
- `cancel()`: stops consuming and requests pipeline cancellation.

Project Reactor provides two primary types:

| Type | Number of elements | Suitable use cases |
| --- | --- | --- |
| `Mono<T>` | 0 or 1 | Finding a record, saving an entity, returning a DTO |
| `Flux<T>` | 0 to N | Listing records, streaming changes, reading multiple rows |
| `Mono<Void>` | Emits no value | Operations that only need a completion or error signal |
| `Publisher<T>` | General interface | Abstract boundary between reactive libraries |

Example:

~~~java
Mono<Book> one = repository.findById(42L);
Flux<Book> all = repository.findAll();
Mono<Void> completed = repository.deleteById(42L);
~~~

`Mono.empty()` does not mean `null`. A Mono must not emit a null element; an absent value is expressed by a complete signal without `onNext`.

In an API:

- An existing record: `Mono<Book>` emits one Book and then completes.
- Not found: `Mono<Book>` completes empty; the service/controller must decide whether to turn it into 404, 204, or another result.
- Multiple records: `Flux<Book>` emits the records one by one.
- Database error: the Publisher emits `onError`; it does not automatically become empty or 404.

## 3. The contract across each layer

### Repository layer

The repository uses Spring Data R2DBC:

~~~java
public interface BookRepository
        extends ReactiveCrudRepository<Book, Long> {

    Flux<Book> findByPriceCentsLessThanEqual(int maxPriceCents);
}
~~~

`findById(id)` returns `Mono<Book>`, `findAll()` returns `Flux<Book>`, `save(book)` returns `Mono<Book>`. When calling these methods, we receive a Publisher describing the data access; this is not a Java record already fetched immediately.

### Service layer

The service composes Publishers and maps entities to DTOs:

~~~java
public Mono<BookView> findById(long id) {
    return repository.findById(id)
        .map(BookView::from);
}

public Flux<BookView> findAll() {
    return repository.findAll()
        .map(BookView::from);
}
~~~

`map` is a short, non-blocking synchronous transformation on each element. It preserves the number of data signals, the same lifecycle, and the same error flow of the Publisher.

### Controller layer

The controller returns the Publisher to Spring WebFlux:

~~~java
@GetMapping("/{id}")
public Mono<BookView> get(@PathVariable long id) {
    return service.findById(id)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND, "Book not found")
        ));
}

@GetMapping
public Flux<BookView> list() {
    return service.findAll();
}
~~~

The controller does not need to serialize JSON manually with Jackson. WebFlux uses HTTP message codecs to encode the values emitted by the Publisher, with the appropriate media type. The controller does not call `block()` to obtain a BookView and then return a synchronous value.

## 4. Lazy execution: who subscribes?

When the service returns:

~~~java
Mono<BookView> result = repository.findById(42L)
    .map(BookView::from);
~~~

it is returning a description of work. For a typical cold R2DBC/Reactor Publisher, the query is executed when the pipeline is subscribed to.

With a WebFlux annotation controller:

~~~java
@GetMapping("/{id}")
public Mono<BookView> get(@PathVariable long id) {
    return service.findById(id);
}
~~~

Spring WebFlux accepts the Publisher, connects it with the HTTP response writer, and subscribes according to the request lifecycle. You should not write:

~~~java
service.findById(id).subscribe();
return Mono.empty();
~~~

This is a serious bug:

- The controller returns an empty Mono, detached from the running task.
- Errors in the separate subscription are no longer converted into the desired HTTP response.
- Cancellation when the client disconnects does not control the separate subscription.
- The Reactor Context, security context, and transaction may no longer be properly associated.
- The request may finish before the query completes.

**Rule:** compose and **return** the Publisher. Only subscribe at the edges of the application: the HTTP runtime, a scheduled job, or a consumer designed to own the subscription lifecycle.

## 5. Choosing the right operator so you do not break the pipeline

| Need | Operator | Example return type |
| --- | --- | --- |
| Transform one Book into a DTO | `map` | `Mono<BookView>` |
| Call an async task depending on Book | `flatMap` | `Mono<Details>` |
| Emit multiple values from one value | `flatMapMany` | `Flux<Item>` |
| Transform each item into a Publisher and preserve order | `concatMap` | `Flux<Result>` |
| Filter elements | `filter` | `Flux<T>` |
| Replace an empty Publisher with another choice | `switchIfEmpty` | `Mono<T>` |
| Transform an error into another error | `onErrorMap` | `Mono<T>` or `Flux<T>` |
| Fallback when an error is genuinely acceptable | `onErrorResume` | `Mono<T>` or `Flux<T>` |
| Record an observation side-effect | `doOnNext`, `doOnError` | Preserves type and signals |
| Wait for an operation then keep a value | `thenReturn` | `Mono<T>` |
| Only care about completion | `then` | `Mono<Void>` |
| Combine independent single operations | `Mono.zip` | `Mono<Tuple2<...>>` |

Synchronous transformation example:

~~~java
return repository.findById(id)
    .map(book -> new BookView(
        book.id(),
        book.title(),
        book.priceCents()
    ));
~~~

Example of calling another Publisher based on the value just read:

~~~java
return repository.findById(id)
    .flatMap(book -> inventoryClient.get()
        .uri("/stock/{id}", book.id())
        .retrieve()
        .bodyToMono(Stock.class)
        .map(stock -> new BookWithStock(book, stock)));
~~~

Key differences:

- `map` is used when the lambda returns a concrete value, not a Publisher.
- `flatMap` is used when the lambda returns a `Mono<R>`.
- `flatMapMany` is useful when a Mono expands into multiple Flux elements.
- Using `map(book -> repository.save(book))` produces `Mono<Mono<Book>>`; the inner Publisher is not automatically executed as expected.
- Using `flatMap(book -> repository.save(book))` produces a flat `Mono<Book>` and executes the save upon subscription.

## 6. Empty, 404, errors, and HTTP status codes

You must distinguish three cases:

~~~text
findById(42)
  |
  +-- onNext(Book) + onComplete --> HTTP 200
  |
  +-- onComplete() with no item --> HTTP 404 per API policy
  |
  +-- onError(databaseFailure) --> HTTP 5xx or appropriately mapped error
~~~

Having the repository return `Mono.empty()` for “not found” is reasonable. The controller can turn this case into 404:

~~~java
return service.findById(id)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND, "Book not found")
    ));
~~~

Do not apply a blanket `onErrorResume(e -> Mono.empty())` to all database errors. It turns “database connection lost” into “no data”, distorting semantics and hiding operational incidents.

If you need to vary the status and headers after an async operation, WebFlux supports:

~~~java
public Mono<ResponseEntity<BookView>> get(long id) {
    return service.findById(id)
        .map(ResponseEntity::ok)
        .switchIfEmpty(Mono.just(ResponseEntity.notFound().build()));
}
~~~

This snippet illustrates the response style; the complete program below uses `ResponseStatusException` for simplicity and ease of testing.

### Null values must not be emitted through a Publisher

Wrong:

~~~java
Mono.just(null);
~~~

Right when a value can be null:

~~~java
Mono.justOrEmpty(nullableValue);
~~~

Or from the database, preserve `Mono.empty()` and handle it at the appropriate layer. Do not use an “empty DTO” to fake a not-found value if the API contract specifies HTTP 404.

## 7. Avoiding block() and subscribe() in application layers

### Wrong: block() in the service

~~~java
public BookView findById(long id) {
    Book book = repository.findById(id).block();
    return BookView.from(book);
}
~~~

When called on a Netty event-loop, `block()` may be rejected by Reactor or stall I/O processing. Even if it runs on another thread, it still defeats the non-blocking design and complicates timeout, cancellation, context, and transactions.

Right approach:

~~~java
public Mono<BookView> findById(long id) {
    return repository.findById(id).map(BookView::from);
}
~~~

### Wrong: manually subscribing to a write operation

~~~java
public Mono<Void> create(Book book) {
    repository.save(book).subscribe();
    return Mono.empty();
}
~~~

The HTTP request may finish before the save operation; write errors are not propagated to the caller. If the request is cancelled, the save may still run in a separate subscription.

Right approach:

~~~java
public Mono<Book> create(Book book) {
    return repository.save(book);
}
~~~

### Wrong: nested Future/Publisher not flattened

~~~java
Mono<Mono<Book>> nested = Mono.just(id)
    .map(repository::findById);
~~~

Right approach:

~~~java
Mono<Book> flat = Mono.just(id)
    .flatMap(repository::findById);
~~~

Do not call `toFuture().join()` or `Future.get()` just to extract data and wrap it back with `Mono.just(...)`.

## 8. R2DBC is truly reactive; JDBC and JPA are blocking

Spring Data R2DBC uses an R2DBC `ConnectionFactory` and a reactive-compatible driver. Repositories like `ReactiveCrudRepository` create Publishers to interact with the database.

Conversely, standard Spring Data JPA/JDBC are blocking APIs. Changing:

~~~java
Book book = jpaRepository.findById(id).orElseThrow();
return Mono.just(book);
~~~

into a method returning `Mono<Book>` does **not** make the JPA call non-blocking. The DB statement has already executed synchronously before the Mono is created.

Even:

~~~java
Mono.fromCallable(() -> jpaRepository.findById(id).orElse(null))
~~~

still runs synchronous code on the subscriber's thread if no scheduler switch is made. If you must temporarily integrate a blocking library, isolate it:

~~~java
Mono<Book> legacyResult = Mono.fromCallable(
        () -> legacyDao.findById(id)
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

This moves blocking work to bounded elastic threads; it does not turn JDBC into R2DBC and does not guarantee imperative transactions propagate across schedulers. You must limit concurrency, timeouts, and the connection pool for the blocking source. For an end-to-end non-blocking flow, prefer truly reactive drivers and clients.

## 9. A request may need multiple Publisher sources

Services often combine DB and downstream HTTP calls:

~~~java
public Mono<BookDetails> details(long id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND)
        ))
        .flatMap(book -> webClient.get()
            .uri("/stock/{id}", book.id())
            .retrieve()
            .bodyToMono(Stock.class)
            .map(stock -> new BookDetails(
                book.id(),
                book.title(),
                stock.available()
            )));
}
~~~

Thus:

- There is no need to manually subscribe to the repository result.
- The downstream HTTP call is only executed when the Book is found.
- If the repository is empty, the WebClient branch does not run.
- If WebClient errors, the error is emitted in the same pipeline.
- If the caller cancels the request, cancellation is forwarded to the active publishers within the capabilities of each adapter.

For two independent sources, you can use `Mono.zip`:

~~~java
Mono<Profile> profile = profileClient.find(userId);
Mono<Settings> settings = settingsRepository.findByUserId(userId);

Mono<UserView> view = Mono.zip(profile, settings)
    .map(tuple -> new UserView(tuple.getT1(), tuple.getT2()));
~~~

Note: if one Mono source completes empty, `zip` may complete without emitting a value; it does not automatically convert to an “empty data row”. If you want to provide a default, handle it on each Publisher before zipping.

## 10. Reactive transactions must reside in the same Reactor Context

When performing multiple R2DBC operations that require atomicity, Spring can use `R2dbcTransactionManager` and `@Transactional` on methods returning a Publisher.

Example illustrating two reactive repositories in a service:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final AuditRepository audits;

    public OrderService(
            OrderRepository orders,
            AuditRepository audits) {
        this.orders = orders;
        this.audits = audits;
    }

    @Transactional
    public Mono<Order> place(Order order) {
        return orders.save(order)
            .flatMap(saved -> audits
                .save(new Audit(null, saved.id(), "CREATED"))
                .thenReturn(saved));
    }
}
~~~

In this example, `OrderRepository`, `AuditRepository`, `Order`, and `Audit` are illustrative types from a larger application, not part of the runnable project in section 13.

Key points:

- The method must return a Publisher for the reactive transaction interceptor to apply.
- `ReactiveTransactionManager` uses the **Reactor Context**, rather than relying on ThreadLocal like typical imperative transactions.
- Related R2DBC operations must run within the same reactive pipeline and the same transaction context.
- Do not call a separate `subscribe()` inside the method: the new subscription does not necessarily participate in the configured transaction.
- When the reactive transaction publisher emits an error, the manager rolls back according to transaction rules.
- Since Spring Framework 5.3, cancellation triggers rollback in a reactive transaction; be cautious with `take()`, `next()`, and timeouts that cause a transaction Flux to be cancelled early.
- Do not include an HTTP call to another system inside a database transaction and assume it will roll back along with the database. HTTP and DB do not share an atomic boundary without a dedicated coordination mechanism.

If a programmatic transaction is needed:

~~~java
Mono<Order> saved = orders.save(order)
    .flatMap(savedOrder -> audits
        .save(new Audit(null, savedOrder.id(), "CREATED"))
        .thenReturn(savedOrder))
    .as(transactionalOperator::transactional);
~~~

`TransactionalOperator` applies a transaction to a publisher. It does not replace configuring a reactive transaction manager and does not make non-DB side effects transactional.

## 11. Both request body and response body are Publishers

WebFlux can receive an async request body:

~~~java
@PostMapping("/books")
public Mono<BookView> create(
        @RequestBody Mono<CreateBookRequest> body) {

    return body.flatMap(service::create);
}
~~~

Here the client sends JSON; WebFlux decodes it into `Mono<CreateBookRequest>`. The service only runs when the request body emits a value.

For a multi-element body, `Flux<T>` can be used when the protocol and codecs support it. Streaming example:

~~~java
@PostMapping(
    path = "/books/import",
    consumes = MediaType.APPLICATION_NDJSON_VALUE
)
public Mono<Long> importMany(
        @RequestBody Flux<CreateBookRequest> body) {

    return body
        .concatMap(service::create)
        .count();
}
~~~

This is an example of a sequential processing and counting pattern; it is **not** an atomic transaction for the entire import. If the third item fails after the first two have been saved, the first two may already be committed. For all-or-nothing, you need a properly scoped reactive transaction and to test rollback behavior.

On the response side:

~~~java
@GetMapping(
    path = "/books/stream",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
public Flux<BookView> stream() {
    return service.list(null);
}
~~~

For a normal finite JSON response, `Flux<T>` may be buffered by the codec into a JSON array; for NDJSON, each JSON record is encoded according to the streaming media type. Do not confuse “returning Flux” with a guarantee that the response always flushes every record across every media type and every proxy.

## 12. Backpressure, cancellation, and errors across layers

### Backpressure

Reactive Streams allows a Subscriber to request the number of elements it can process via `request(n)`. When an API flows through controller → service → repository without blocking or out-of-band subscriptions, demand can propagate through operators and adapters.

However, one cannot claim that every driver, network transport, and database keeps strictly n elements in memory. Buffering, fetch-size, and the R2DBC driver's mechanisms still need to be verified when streaming large datasets.

Avoid:

~~~java
return repository.findAll().collectList()
    .flatMapMany(Flux::fromIterable);
~~~

This collects the entire result into a list, losing the benefit of emitting items as they arrive. Only use `collectList()` when business logic truly needs the entire finite collection.

### Cancellation

If the client disconnects or the request times out, the HTTP runtime may cancel the response publisher. Cancellation propagates through operators, helping stop ongoing work and release resources depending on the capabilities of the repository/driver.

Do not create a separate subscription in the service because request cancellation will no longer control the detached work.

### Error propagation

If the repository emits a connection error, the pipeline continues with `onError` until handled. For an API, errors should be mapped meaningfully:

- Invalid input: HTTP 400.
- Entity does not exist: HTTP 404.
- Duplicate key or business constraint violation: HTTP 409 if the API policy defines it that way.
- Database loss or downstream failure: appropriate HTTP 5xx, with logging and observability.
- Client cancel: should not trigger new side effects when the request no longer needs the result.

Do not expose SQL details, connection strings, or sensitive stack traces in public response bodies.

## 13. Runnable project: Spring Boot 3.5 + Java 17 + WebFlux + R2DBC H2

This example creates a book management API:

- `GET /api/books` returns `Flux<BookView>`.
- `GET /api/books/{id}` returns `Mono<BookView>` or HTTP 404.
- `GET /api/books/stream` streams NDJSON.
- `POST /api/books` accepts `Mono<CreateBookRequest>`, saves via `ReactiveCrudRepository.save`, and returns HTTP 201.
- Data is stored in in-memory H2 via the R2DBC driver, without using JPA/JDBC in the request pipeline.

Structure:

~~~text
reactive-books/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/books/
    │   │   ├── ReactiveBooksApplication.java
    │   │   ├── Book.java
    │   │   ├── BookRepository.java
    │   │   ├── BookView.java
    │   │   ├── CreateBookRequest.java
    │   │   ├── BookService.java
    │   │   └── BookController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/com/example/books/
        └── BookApiTest.java
~~~

### 13.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactive-books</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-r2dbc</artifactId>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 13.2. ReactiveBooksApplication.java

~~~java
package com.example.books;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveBooksApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveBooksApplication.class, args);
    }
}
~~~

### 13.3. application.properties

~~~properties
spring.r2dbc.url=r2dbc:h2:mem:///bookdb?options=DB_CLOSE_DELAY=-1
spring.r2dbc.username=sa
spring.r2dbc.password=
spring.sql.init.mode=always
~~~

Here `spring.r2dbc.*` configures the ConnectionFactory, **not** `spring.datasource.*`. Spring Boot auto-configures R2DBC and reads the `schema.sql` and `data.sql` scripts. The in-memory database is for demo purposes only; production requires an appropriate driver and migration strategy.

### 13.4. schema.sql and data.sql

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(160) NOT NULL,
    price_cents INTEGER NOT NULL
);
~~~

`src/main/resources/data.sql`:

~~~sql
INSERT INTO books (title, price_cents)
VALUES ('Reactor nhập môn', 15000);

INSERT INTO books (title, price_cents)
VALUES ('WebFlux thực hành', 22000);
~~~

The seed records create IDs 1 and 2 in a fresh in-memory database. The sample tests use ID 1. If run against a shared DB reused across multiple contexts, IDs and data may differ; large production/test suites should create an isolated database per test.

### 13.5. Book.java — Entity

~~~java
package com.example.books;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public record Book(
    @Id Long id,
    String title,
    int priceCents
) {}
~~~

Spring Data R2DBC maps the Java field `priceCents` to the `price_cents` column using the default naming strategy. New records have `id = null` so the database assigns the identity.

Entities belong to the persistence layer and should not be used directly to dictate the HTTP response structure in large systems.

### 13.6. BookRepository.java — Data access

~~~java
package com.example.books;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import reactor.core.publisher.Flux;

public interface BookRepository
        extends ReactiveCrudRepository<Book, Long> {

    Flux<Book> findByPriceCentsLessThanEqual(int maxPriceCents);
}
~~~

Spring Data generates the implementation from the interface. `findAll` and query methods return Flux; `findById` and `save` return Mono.

### 13.7. CreateBookRequest.java — Request DTO

~~~java
package com.example.books;

public record CreateBookRequest(
    String title,
    int priceCents
) {}
~~~

The input DTO is separate from the DB entity. In this example, validation is performed in the service to avoid adding the validation starter.

### 13.8. BookView.java — Response DTO

~~~java
package com.example.books;

public record BookView(
    long id,
    String title,
    int priceCents
) {

    public static BookView from(Book book) {
        return new BookView(
            book.id(),
            book.title(),
            book.priceCents()
        );
    }
}
~~~

`BookView.from` is a pure synchronous mapper, so use `map(BookView::from)` without creating an extra Mono.

### 13.9. BookService.java — Composition

~~~java
package com.example.books;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Mono<BookView> findById(long id) {
        return repository.findById(id)
            .map(BookView::from);
    }

    public Flux<BookView> list(Integer maxPriceCents) {
        if (maxPriceCents != null && maxPriceCents < 0) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "maxPriceCents must be >= 0"
            ));
        }

        Flux<Book> source = maxPriceCents == null
            ? repository.findAll()
            : repository.findByPriceCentsLessThanEqual(maxPriceCents);

        return source.map(BookView::from);
    }

    public Mono<BookView> create(CreateBookRequest input) {
        if (input.title() == null
                || input.title().isBlank()
                || input.priceCents() <= 0) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "title and positive priceCents are required"
            ));
        }

        Book newBook = new Book(
            null,
            input.title().trim(),
            input.priceCents()
        );

        return repository.save(newBook)
            .map(BookView::from);
    }
}
~~~

Notable points:

- `findById` returns Mono, without blocking.
- `list` returns Flux for both the full list and filtered queries.
- `create` returns a Mono representing the save operation, without subscribing.
- Validation returns `Mono.error` / `Flux.error` when invalid; errors are propagated to the HTTP layer.
- The DTO mapper runs inside the pipeline; no extra scheduler is needed since it is lightweight and synchronous.

### 13.10. BookController.java — HTTP boundary

~~~java
package com.example.books;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<BookView> list(
            @RequestParam(required = false) Integer maxPriceCents) {
        return service.list(maxPriceCents);
    }

    @GetMapping(
        path = "/stream",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<BookView> stream() {
        return service.list(null);
    }

    @GetMapping("/{id}")
    public Mono<BookView> get(@PathVariable long id) {
        return service.findById(id)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Book not found"
            )));
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<BookView>> create(
            @RequestBody Mono<CreateBookRequest> request) {

        return request
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Request body required"
            )))
            .flatMap(service::create)
            .map(book -> ResponseEntity
                .created(URI.create("/api/books/" + book.id()))
                .body(book));
    }
}
~~~

In POST, `request.flatMap(service::create)` preserves the publisher chain from JSON decoding until the database save finishes. HTTP 201 and Location are only created after the Mono from the repository emits the saved entity.

In GET for a single book, `switchIfEmpty` turns absence into HTTP 404; database connection errors are not turned into 404.

### 13.11. Running the application

In the directory containing pom.xml, with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Read an existing book:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

Expected HTTP 200 and JSON body in a fresh DB:

~~~json
{"id":1,"title":"Reactor nhập môn","priceCents":15000}
~~~

Finite list:

~~~bash
curl -i http://localhost:8080/api/books
~~~

The body is a JSON array containing the two seed books. Do not rely on return order if the query has no ORDER BY; when a stable order is required, declare sorting explicitly.

Filter books with a maximum price of 20,000:

~~~bash
curl -i "http://localhost:8080/api/books?maxPriceCents=20000"
~~~

Create a new book:

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -d "{\"title\":\"Java Reactive\",\"priceCents\":32000}"
~~~

HTTP 201 response, Location header pointing to `/api/books/{id}`, and body containing the newly saved book. The ID is assigned by the database, so do not hard-code the ID in the result.

Not found:

~~~bash
curl -i http://localhost:8080/api/books/999999
~~~

HTTP 404 response.

Read NDJSON:

~~~bash
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/api/books/stream
~~~

Each line is an independent JSON object; the demo endpoint uses a finite DB source. For high traffic, measure actual memory, driver fetch behavior, and backpressure instead of assuming changing Content-Type alone is sufficient.

### 13.12. BookApiTest.java — HTTP integration test

~~~java
package com.example.books;

import java.util.Map;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class BookApiTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsOneSeedBookThroughAllLayers() {
        client.get()
            .uri("/api/books/1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Reactor nhập môn")
            .jsonPath("$.priceCents").isEqualTo(15000);
    }

    @Test
    void missingBookBecomes404() {
        client.get()
            .uri("/api/books/999999")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void createsBookViaPublisher() {
        client.post()
            .uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of(
                "title", "R2DBC cơ bản",
                "priceCents", 27000
            ))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody()
            .jsonPath("$.title").isEqualTo("R2DBC cơ bản")
            .jsonPath("$.id").isNumber();
    }

    @Test
    void rejectsInvalidPrice() {
        client.post()
            .uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of(
                "title", "Invalid",
                "priceCents", 0
            ))
            .exchange()
            .expectStatus().isBadRequest();
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

Tests run through the controller, service, repository, and H2 database. They verify not only DTO values but also HTTP mappings: 200, 201, 400, and 404.

The demo omits security to focus on the Publisher. In a real application, add Spring Security, enforce read/write permissions, and do not return SQL errors directly in responses.

## 14. Testing Publisher signals and cancellation

Besides WebTestClient, Reactor Test provides `StepVerifier` to verify publishers:

~~~java
StepVerifier.create(service.findById(1L))
    .expectNextMatches(book -> book.title().equals("Reactor nhập môn"))
    .verifyComplete();
~~~

This snippet requires the `reactor-test` dependency in test scope, an ApplicationContext/test fixture with a database and service bean, and importing `reactor.test.StepVerifier`. This is an additional snippet, not part of the BookApiTest file above.

To test an empty publisher:

~~~java
StepVerifier.create(service.findById(999999L))
    .verifyComplete();
~~~

Because the service method intentionally keeps `Mono.empty()` when not found; the controller turns it into HTTP 404.

For long-running services, test cancellation:

~~~java
StepVerifier.create(Flux.interval(Duration.ofMillis(10)))
    .expectNextCount(3)
    .thenCancel()
    .verify();
~~~

The snippet above illustrates the cancel signal; it does not prove that a specific database driver has cancelled the query. To verify real cleanup, you need integration tests or metrics at the driver/connection pool.

## 15. Keeping the Reactor Context instead of relying on ThreadLocal

Request information such as a trace ID, principal, or transaction context may need to travel along an asynchronous chain. Reactor Context is propagated **per subscription**, unlike ThreadLocal bound to a fixed thread.

Example:

~~~java
Mono<String> traced = Mono.deferContextual(ctx ->
    Mono.just("trace=" + ctx.getOrDefault("traceId", "missing"))
).contextWrite(ctx -> ctx.put("traceId", "req-42"));
~~~

When subscribed, the Publisher emits:

~~~text
trace=req-42
~~~

In systems with Spring Security reactive, you can use `ReactiveSecurityContextHolder` or dependency-injection/controller principal mechanisms as supported by the API. Do not assume an imperative ThreadLocal `SecurityContextHolder` always holds the same value after the pipeline switches schedulers.

Do not create a separate subscription in the service and expect the request's transaction, security, or tracing context to automatically follow into that subscription. When integrating MDC/logging, use an intentional context-propagation mechanism configured for the framework version.

## 16. Practical limitations of end-to-end reactive

Keeping Publishers across layers is an important condition, but not an absolute guarantee that every operation is non-blocking:

- `map` may contain time-consuming CPU tasks or blocking calls.
- An adapter may buffer all data internally.
- R2DBC drivers have their own limitations regarding fetch-size, cursors, and cancellation.
- Unbounded `flatMap` concurrency can overload the DB pool or downstream services.
- Using `collectList` on an infinite data stream will never complete.
- A long transaction wrapping a streaming Flux can hold a database connection for a long time.
- Non-idempotent DB write retries can create duplicate records if the previous attempt committed but the response failed.
- HTTP clients/servers may buffer and flush differently depending on media type and proxies.
- JDBC/JPA calls do not become non-blocking simply by being wrapped in a Mono.

To verify, monitor event-loop blocking, latency, memory/buffers, DB pool utilization, pending connections, error rate, cancellation, and request throughput under realistic load.

## 17. Common mistakes and how to fix them

1. **Controller returns DTO after blocking:** switch to returning Mono/Flux from the service.
2. **Service calls subscribe then returns Mono.empty():** replace with returning the directly chained Publisher.
3. **Repository is JPA but service returns Mono.just(result):** data has already been read blocking; switch to R2DBC if true non-blocking is needed.
4. **Using map when the lambda returns Mono:** causes a nested Publisher; use flatMap.
5. **Using flatMap for a simple synchronous mapper:** unnecessary; use map.
6. **Swallowing all errors with onErrorResume(...Mono.empty()):** distinguish not-found from database failure.
7. **Returning null from a mapper:** Reactor does not accept null; handle optional/empty properly.
8. **Using Mono.just(null):** wrong; use Mono.justOrEmpty(value).
9. **Returning Flux when business logic always expects a single record:** use Mono to express cardinality.
10. **Collecting all DB rows with collectList unnecessarily:** keep Flux or use pagination.
11. **Creating a subscription inside @Transactional:** may run outside the transaction Reactor Context.
12. **Declaring @Transactional on a void method for R2DBC:** reactive transactions require a Publisher pipeline and an appropriate manager.
13. **Using an imperative transaction manager for an R2DBC pipeline:** configure ReactiveTransactionManager.
14. **Timeouts causing cancellation mid-transaction Flux:** understand rollback-on-cancel and manage transaction scope.
15. **Holding a transaction across an external HTTP call:** increases DB connection hold time and does not create an automatic distributed transaction.
16. **Assuming returning Flux always streams each JSON object:** media type and encoder determine aggregation/flush behavior.
17. **Backpressure limits bypassed by driver buffering:** must measure driver and downstream behavior.
18. **Unbounded flatMap concurrency:** choose appropriate concurrency and connection pool sizing.
19. **Declaring a service returning a Publisher while executing eager side effects before return:** use defer when needing to delay until subscription.
20. **Using ThreadLocal for trace/security in a reactive chain:** prefer Reactor Context and reactive APIs.
21. **Tests only call the service without subscribing:** no guarantee the publisher executed; use StepVerifier/WebTestClient.
22. **Not testing Mono.empty():** easily turns “not found” into an unintended empty HTTP 200.
23. **Not handling client cancellation:** sources may keep consuming resources if a separate subscription was created.
24. **Non-idempotent retries:** may create side effects twice.
25. **Mixing multiple reactive libraries without understanding adapters:** verify the Publisher bridge preserves demand, error, context, and cancellation.

## 18. Checklist for designing a new use case

- Does the controller return Mono/Flux or is it blocking?
- Does the service describe the work as a Publisher and return it?
- Is the repository truly reactive or just wrapping JDBC/JPA?
- Does the Mono/Flux type reflect the actual number of elements?
- At which layer is empty distinguished from error?
- Are map, flatMap, flatMapMany, and concatMap used for the right purpose?
- Is there any manual subscribe in the service/repository?
- Is there any unnecessary collectList, toFuture().join(), or block step?
- Is reactive transaction configured and kept in the same Reactor Context?
- Is rollback-on-cancel handled in long transactions?
- Is concurrency bounded and the DB connection pool monitored?
- When combining WebClient and DB, are cancellation and timeout propagated?
- Is the right Content-Type chosen for JSON batch vs. NDJSON stream?
- Does DTO mapping separate the DB entity from the HTTP contract?
- Are 200/201/400/404, empty, error, and cancellation tested at the appropriate layers?
- Is end-to-end performance measured under load rather than just looking at Mono/Flux types?

## 19. Self-check questions

**1.** Why must the service return Mono/Flux from the repository? So that async/lazy execution, error propagation, and cancellation are not lost across the same subscription.

**2.** Who subscribes to the Publisher returned by a WebFlux controller? WebFlux's HTTP runtime/message writer within the request lifecycle.

**3.** What does Mono.empty() mean? Completing without emitting an element, distinct from null and distinct from onError.

**4.** When should map be used? When each value is transformed synchronously into another value.

**5.** When should flatMap be used? When the transformation returns a Mono/Publisher that needs to be flattened.

**6.** What is Mono<Mono<Book>> usually a sign of? Using map with a function that already returns Mono; consider flatMap.

**7.** Should Mono.just(jpaRepository.findById(...)) be used on the event-loop? No; the blocking JPA call has already executed immediately before the Mono is created.

**8.** What should be done if calling a blocking library is unavoidable? Isolate it onto boundedElastic with fromCallable/subscribeOn and control resources, treating it as a transitional solution.

**9.** Where do reactive transactions store their state? In the Reactor Context; they do not rely completely on ThreadLocal.

**10.** Why is manually calling subscribe inside @Transactional dangerous? Creating a new subscription may not share the same transaction context.

**11.** What can cancelling a reactive transaction lead to? Rollback according to Spring Framework's reactive transaction policy.

**12.** Does returning Flux<BookView> with application/json always flush every item? No; it may serialize into a JSON array. To stream records, use appropriate NDJSON/SSE.

**13.** Why shouldn't onErrorResume be used to turn all errors into empty? Because infrastructure failures differ from “no data”.

**14.** When should collectList be used? When business logic needs a finite collection; do not use it unconditionally for large/infinite data.

**15.** Which test verifies HTTP mapping and status? WebTestClient integration tests; StepVerifier verifies Publisher signals in reactive layer tests.

**Key takeaway:** The Publisher contract in Spring WebFlux must be preserved across controllers, services, and data access. The repository layer returns Mono/Flux, the service composes with operators, and the controller returns the Publisher for WebFlux to subscribe. Keep empty/error/cancel/context in the same pipeline, do not insert block() or subscribe() midway, and do not confuse blocking JDBC/JPA with reactive R2DBC. Reactive transactions are only consistent when data and operations share the same Reactor Context; test both API behavior and Publisher signals.

**Official documentation:**
- [Spring Framework 6.2 — WebFlux @ResponseBody and reactive return types](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html)
- [Spring Framework 6.2 — ResponseEntity and Mono/Flux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responseentity.html)
- [Spring Data Relational — R2DBC Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html)
- [Spring Boot 3.5 — Using R2DBC](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/3.5/reference/how-to/data-initialization.html)
- [Spring Framework 6.2 — Reactive @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — TransactionalOperator](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/).