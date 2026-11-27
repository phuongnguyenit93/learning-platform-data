# Starter for Spring WebFlux

In a Spring for GraphQL application, the GraphQL starter provides the GraphQL integration, while the web starter determines the HTTP platform the application uses. When you want to serve GraphQL on a reactive web stack, the application can use **spring-boot-starter-webflux**. This starter brings Spring WebFlux into a Spring Boot application and typically uses Reactor Netty as the default web server.

Spring WebFlux fits applications with high I/O concurrency, non-blocking request processing requirements, or services and data-access layers that already use Reactor. When combined with Spring for GraphQL, resolvers can return reactive types such as **Mono** and **Flux**, allowing results from asynchronous services to flow end-to-end through the GraphQL layer.

Keep in mind that GraphQL and WebFlux solve two different problems. GraphQL defines how clients request data and how the server resolves fields. WebFlux is the reactive web foundation for receiving and processing requests. Choosing WebFlux does not change the GraphQL schema or how clients write queries; it changes the web runtime and how the application handles I/O.

## Role of spring-boot-starter-webflux

Spring Boot provides starters to group dependencies by purpose. **spring-boot-starter-webflux** enables an application to use Spring WebFlux without manually declaring each underlying library. The starter typically brings in:

- Spring WebFlux for building web applications using the reactive model.
- Project Reactor with publisher types such as Mono and Flux.
- Default reactive web server configuration, usually Reactor Netty.
- The Spring Boot integrations needed to auto-configure a WebFlux application.

In a GraphQL application, two starters are commonly used together:

| Dependency | Responsibility |
| --- | --- |
| **spring-boot-starter-graphql** | Integrates GraphQL Java with Spring, reads schemas, maps resolvers, executes operations, and produces GraphQL results |
| **spring-boot-starter-webflux** | Provides the reactive web runtime to accept GraphQL requests over HTTP and process them using the WebFlux model |

The GraphQL starter does not decide by itself whether the application runs on Spring MVC or Spring WebFlux. The web starter placed on the classpath influences the web application type that Spring Boot selects. Therefore, when intentionally building a reactive server, use the WebFlux starter alongside the GraphQL starter.

## Declaring Dependencies

With Gradle, a minimal configuration might look like this:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

With Maven, declare both dependencies in the dependencies section:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-graphql</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
~~~

When the project uses Spring Boot dependency management or the Spring Boot parent, there is no need to specify separate versions for each starter. Let Spring Boot manage compatible versions of Spring Framework, Spring for GraphQL, Reactor, and related libraries.

Do not add **spring-boot-starter-web** if your goal is to run a WebFlux server. When both the MVC and WebFlux starters are present, Spring Boot typically prefers configuring Spring MVC for the web application. Needing `WebClient` inside an MVC application is a different scenario: `WebClient` can be used standalone without switching the web server to WebFlux.

## Application Structure and the GraphQL Endpoint

After adding the dependencies, a Spring Boot application can keep a simple structure:

~~~text
src/main/
├── java/
│   └── com/example/catalog/
│       ├── CatalogApplication.java
│       ├── graphql/
│       │   └── BookGraphQlController.java
│       └── service/
│           └── BookService.java
└── resources/
    ├── application.yml
    └── graphql/
        └── schema.graphqls
~~~

The schema can declare the fields to expose:

~~~graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Spring Boot automatically discovers schemas in **src/main/resources/graphql** and configures the default HTTP GraphQL endpoint at **/graphql**. You can change the path using the **spring.graphql.path** property:

~~~yaml
spring:
  graphql:
    path: /graphql
~~~

Clients still send GraphQL operations to that endpoint just as with Spring MVC. The difference lies on the server side: requests are received by the WebFlux reactive web stack.

## Resolvers Returning Mono and Flux

Project Reactor provides two common publisher types:

- **Mono<T>** represents an asynchronous result that may emit zero or one value.
- **Flux<T>** represents a sequence of zero to many elements emitted over time.

Spring for GraphQL supports controller methods returning reactive types. For example:

~~~java
@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public Flux<Book> books() {
        return bookService.findAll();
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Mono<Author> author(Book book) {
        return bookService.findAuthor(book.authorId());
    }
}
~~~

The **book** field resolver returns a Mono because one ID corresponds to at most one book. The **books** resolver returns a Flux because there can be multiple books. The **author** field also returns a Mono because a book links to at most one author in this example.

A reactive service can define its contract as follows:

~~~java
public interface BookService {

    Mono<Book> findById(String id);

    Flux<Book> findAll();

    Mono<Author> findAuthor(String authorId);
}
~~~

These return types allow resolvers to pass through publishers from services without manually waiting for results. Spring for GraphQL coordinates with GraphQL Java to handle asynchronous results during field execution.

Note that **Flux<Book>** in a Query is typically collected to form a list value for the GraphQL response. It does not mean the HTTP response automatically streams each list item as a continuous data stream. If the business case requires receiving new events continuously, design a GraphQL Subscription and configure the appropriate transport.

## Request Processing Flow with WebFlux

When a client sends an HTTP request to **/graphql**, WebFlux accepts the request using the reactive HTTP runtime. Spring for GraphQL passes the operation, variables, and context into the GraphQL execution service. GraphQL Java validates the operation against the schema and invokes resolvers for the requested fields. Resolvers return synchronous or asynchronous results; reactive publishers are coordinated to produce the GraphQL response.

~~~mermaid
flowchart TD
    A["GraphQL client"] -->|"HTTP request"| B["Reactor Netty"]
    B --> C["Spring WebFlux"]
    C --> D["Spring for GraphQL"]
    D --> E["GraphQL Java"]
    E --> F["@QueryMapping / @SchemaMapping"]
    F --> G["Reactive service"]
    G --> H["Reactive repository / WebClient"]
    H --> G
    G --> F
    F --> E
    E --> I["GraphQL response"]
    I --> A
~~~

This model is useful when I/O waiting operations can happen in a non-blocking manner, such as querying with R2DBC, calling another service with WebClient, or reading data from a reactive message source. While waiting on I/O, the runtime can use thread resources more efficiently than holding a blocked thread per request.

## End-to-End Reactivity Requires Compatible Layers

Simply adding the WebFlux starter and changing controller return types to Mono or Flux is not enough to make the system non-blocking. If a resolver calls a blocking service, and that service uses synchronous JDBC or JPA, processing threads can still get blocked.

A reactive flow should preserve publishers across all layers:

~~~text
WebFlux request
    -> GraphQL resolver returns Mono / Flux
        -> service returns Mono / Flux
            -> reactive repository or WebClient
                -> non-blocking I/O
~~~

For example, Spring Data R2DBC provides reactive repositories. The R2DBC dependency only needs to be added when the application actually accesses a database via R2DBC; it is not a mandatory dependency of WebFlux or GraphQL:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("io.r2dbc:r2dbc-postgresql")
}
~~~

A repository can return publishers:

~~~java
public interface BookRepository
        extends ReactiveCrudRepository<BookEntity, String> {
}
~~~

A corresponding repository can be used for authors:

~~~
public interface AuthorRepository
        extends ReactiveCrudRepository<AuthorEntity, String> {
}
~~~

The service can transform entities into GraphQL models without blocking threads:

~~~java
@Service
public class ReactiveBookService implements BookService {

    private final BookRepository repository;
    private final AuthorRepository authorRepository;

    public ReactiveBookService(
            BookRepository repository,
            AuthorRepository authorRepository) {
        this.repository = repository;
        this.authorRepository = authorRepository;
    }

    @Override
    public Mono<Book> findById(String id) {
        return repository.findById(id)
                .map(this::toBook);
    }

    @Override
    public Flux<Book> findAll() {
        return repository.findAll()
                .map(this::toBook);
    }

    @Override
    public Mono<Author> findAuthor(String authorId) {
        return authorRepository.findById(authorId)
                .map(this::toAuthor);
    }

    private Book toBook(BookEntity entity) {
        return new Book(entity.getId(), entity.getTitle());
    }

    private Author toAuthor(AuthorEntity entity) {
        return new Author(entity.getId(), entity.getName());
    }
}
~~~

This is an illustrative example of preserving reactive types through the repository and service layers; real-world applications need to add mappings, data relationships, and error handling tailored to their domain.

If you must integrate a blocking library that cannot yet be replaced, isolate the blocking operation on an appropriate scheduler, such as **Schedulers.boundedElastic()**, rather than executing it directly on an event-loop thread. Never call **block()** inside a resolver or on the WebFlux request-processing thread to wait for a publisher to complete. Blocking the event loop can degrade throughput across many concurrent requests.

## Calling External Services with WebClient

WebClient is Spring's reactive HTTP client. When a GraphQL resolver needs to fetch information from another service, WebClient can return a Mono or Flux so the service continues processing asynchronously:

~~~java
@Service
public class AuthorClient {

    private final WebClient webClient;

    public AuthorClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://author-service")
                .build();
    }

    public Mono<Author> findById(String authorId) {
        return webClient.get()
                .uri("/authors/{id}", authorId)
                .retrieve()
                .bodyToMono(Author.class);
    }
}
~~~

The resolver can return the result directly from the client:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Mono<Author> author(Book book) {
    return authorClient.findById(book.authorId());
}
~~~

In a real application, configure timeouts, bounded retries when appropriate, HTTP status handling, and error observability for external services. Avoid unconditionally retrying every error because doing so can amplify load when the target system is already experiencing an outage.

## Subscriptions and Event Streams

Queries and Mutations typically produce a single response per operation. Subscriptions are used when clients need to receive multiple events over time. In Spring for GraphQL, subscription resolvers typically return **Flux<T>**:

~~~graphql
type Subscription {
  bookCreated: Book!
}
~~~

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<Book> bookCreated() {
        return eventService.bookCreated();
    }
}
~~~

WebFlux supports the reactive model, but declaring a Subscription in the schema and returning a Flux does not automatically establish client connections. The application also needs to enable and configure a transport that supports subscriptions, usually WebSocket or another compatible transport. With Spring Boot, the WebSocket endpoint can be configured via **spring.graphql.websocket.path** when the application uses a supported WebSocket transport.

## DataLoader, @BatchMapping, and Performance

Reactivity does not automatically eliminate the N+1 problem. If a query retrieves a list of books and each author field triggers a separate request to the author service, the server can still issue many I/O calls. Those calls may be non-blocking, yet the total call volume remains high and causes unnecessary load.

Spring for GraphQL provides **@BatchMapping** and DataLoader support to batch field resolution. Instead of loading an author individually for each book, a batch resolver receives multiple source objects and loads data in batches. When the data source supports batch APIs, this approach can reduce the number of database queries or external service calls.

In a reactive design, a batch loader can return a reactive type appropriate for the data source. Ensure results are matched accurately to each key or source object, handle missing data cases, and avoid sharing caches across requests from different users. DataLoaders are normally scoped per request execution to prevent leaking data or access permissions between requests.

Beyond batching, consider pagination, list size limits, operation depth or complexity limits, timeouts, and concurrency limits. A GraphQL operation can request many data branches; non-blocking execution helps manage I/O resources better, but it does not make expensive queries free.

## Configuration and Testing

Minimal endpoint configuration can stay in **application.yml**:

~~~yaml
spring:
  graphql:
    path: /graphql
~~~

Other properties such as CORS, WebSocket, schema locations, or enabling GraphiQL should be configured according to the environment and deployment requirements. Do not enable public developer UI tools in production environments without proper access controls.

You can test the HTTP GraphQL endpoint using **WebTestClient** together with **HttpGraphQlTester**. This testing approach verifies both the WebFlux HTTP path and the operation result:

In the test scope, add the **spring-graphql-test** library to use GraphQlTester:

~~~groovy
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

~~~java
WebTestClient webTestClient = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.create(webTestClient);

graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring in Action");
~~~

You should also test cases for missing data, external service failures, timeouts, invalid input, unauthorized users, and queries with deeply nested fields. For Subscriptions, test both the event-emitting publisher and the transport used by clients.

## When Should You Choose WebFlux for GraphQL?

WebFlux is a fitting choice when the application handles many concurrent I/O-bound requests, services and repositories already support reactive APIs, or multiple asynchronous calls must be coordinated within a single GraphQL operation. It also suits applications using Reactor or building reactive event streams.

Spring MVC remains a sensible choice for applications using blocking libraries such as JDBC/JPA, handling moderate traffic, and not needing an end-to-end reactive model. WebFlux increases demands on code organization, error handling, context propagation, debugging, and scheduler management. Choosing a reactive stack solely because GraphQL has Subscriptions is usually not reason enough; evaluate the entire workload and dependency ecosystem.

When choosing **spring-boot-starter-webflux**, clearly define your I/O layers, avoid uncontrolled mixing of blocking and non-blocking code, and measure latency and resource usage under realistic load. Combining the right GraphQL starter, WebFlux starter, reactive resolvers, and compatible data sources enables your application to serve GraphQL APIs consistently in a non-blocking model.
