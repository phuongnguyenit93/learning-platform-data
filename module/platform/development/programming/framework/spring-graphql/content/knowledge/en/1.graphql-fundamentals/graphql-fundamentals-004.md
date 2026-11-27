# Query, Mutation, and Subscription in Spring for GraphQL

GraphQL provides three main operation types for clients to exchange data with the server: **query** to read data, **mutation** to modify data, and **subscription** to receive real-time data. Spring for GraphQL maps these operations to Java methods using annotations such as `@QueryMapping`, `@MutationMapping`, and `@SubscriptionMapping`.

This lesson builds a small book management API to illustrate how to declare a schema, write resolvers, pass variables, handle results, and test each type of operation.

## 1. Roles of the three operation types

Every GraphQL request executes an operation declared in the schema. The schema defines the fields clients can invoke, input data types, and return types.

| Operation | Purpose | Example in the book API |
| --- | --- | --- |
| Query | Read data, without side effects | Find a book by ID, fetch the book list |
| Mutation | Create, update, or delete data | Create a new book |
| Subscription | Receive a stream of results when events occur | Receive a notification when a new book is created |

GraphQL defines three conventional root types named `Query`, `Mutation`, and `Subscription`. `Query` is the required root type; the other two only need to be declared when the API supports mutations or subscriptions.

Operations are sent by clients to the same GraphQL endpoint. With Spring Boot auto-configuration, the HTTP endpoint is typically `/graphql` and can be changed via configuration. The operation name, input variables, and selected fields are placed inside the request payload, so the server does not need to create a separate URL for each query.

## 2. Declaring the schema with SDL

Before writing Java resolvers, you need to describe the API using Schema Definition Language (SDL). The example below defines fields for reading books, creating a book, and watching for new books:

~~~graphql
type Query {
    book(id: ID!): Book
    books: [Book!]!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}

type Subscription {
    bookCreated: Book!
}

type Book {
    id: ID!
    title: String!
    authorId: ID!
}

input CreateBookInput {
    title: String!
    authorId: ID!
}
~~~

Key points to note:

- `ID!` means the client must pass an ID and that value cannot be `null`.
- `book(id: ID!): Book` allows the result to be `null` if no book is found. This fits the case where a syntactically valid ID does not exist in the system.
- `[Book!]!` means the list cannot be `null`, and each element in the list cannot be `null` either. An empty list is still valid.
- `CreateBookInput` is an input object used to group the mutation's input fields. Input objects make the API easier to extend when the create-book operation needs additional attributes.
- `Book` is an output object; `CreateBookInput` is an input object. GraphQL distinguishes these two because an input object is only for input data and cannot substitute for an output object in a return type.
- `bookCreated` returns a `Book` for each emitted event. When implementing the subscription, the Java method will return a publisher emitting multiple values over time.

The schema is the contract between client and server. If a field is not declared in the schema, clients cannot request it even if the Java object has a matching property.

## 3. Query: reading data

### 3.1. Writing a query operation

The client specifies which fields it wants to receive. For example, querying a book by ID:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
        authorId
    }
}
~~~

`FindBook` is the operation name, and `$id` is a variable of type `ID!`. The variable value is sent separately in the `variables` section:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title authorId } }",
    "operationName": "FindBook",
    "variables": {
        "id": "book-101"
    }
}
~~~

Separating variables from the query string lets you reuse the same operation with different values while avoiding direct concatenation of user input into the GraphQL query string.

Clients can also fetch a list:

~~~graphql
query ListBooks {
    books {
        id
        title
    }
}
~~~

The server only needs to return data for the selected fields. If the client does not request `authorId`, the response omits that field. This field-selection mechanism lets clients specify the exact shape of data they need.

### 3.2. Mapping queries in Spring for GraphQL

Spring for GraphQL uses `@QueryMapping` to map a controller method to a field on the `Query` root type. For example, the model and input object can be represented as Java records:

~~~java
public record Book(
        String id,
        String title,
        String authorId
) {}

public record CreateBookInput(
        String title,
        String authorId
) {}
~~~

The controller handles the two query fields as follows:

~~~java
@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
~~~

In this example:

- `@Controller` registers the class as a controller for Spring for GraphQL.
- `@QueryMapping` maps the method by method name to the same-named field on the `Query` root type. You can pass the field name to the annotation if the method name differs from the field name.
- `@Argument("id")` extracts the `id` argument value from the query and converts it to the corresponding Java type.
- `bookService` holds responsibility for data access and business logic. Resolvers should delegate calls to services rather than keeping persistence logic inside the controller.

`@QueryMapping` is a shorthand for `@SchemaMapping` with type name `Query`. When you need to map a field belonging to another object type, such as `Book`'s `author` field, you can use `@SchemaMapping(typeName = "Book", field = "author")`.

### 3.3. Results and nullability

For the `book` query, the schema allows returning `Book` or `null`. Therefore, when an ID is not found, the resolver can return `null` and the response looks like:

~~~json
{
    "data": {
        "book": null
    }
}
~~~

If the schema changes to `book(id: ID!): Book!`, a `null` result violates the non-null contract. GraphQL will produce an execution error and propagate `null` up to the nearest nullable parent field. This behavior is commonly called **null propagation** or **null bubbling**.

Therefore, choose `!` according to the API's actual guarantees. Only declare non-null when the server can guarantee a value in every valid case; otherwise, use a nullable type and define clearly how clients handle missing data.

Queries should only serve for reading data. Do not use queries to create orders, update state, or perform actions with side effects. Query fields may be executed in parallel, so placing state changes inside a query can lead to unpredictable behavior.

## 4. Mutation: modifying data

### 4.1. Designing inputs and mutations

Mutations are used for operations that change system state. With the book API, creating a book accepts an input object and returns the newly created book:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        authorId
    }
}
~~~

Input variables:

~~~json
{
    "input": {
        "title": "Practical GraphQL",
        "authorId": "author-12"
    }
}
~~~

Using an input object instead of several loose arguments keeps the mutation signature more stable. When new properties like `description` or `publishedAt` are needed, the input can be extended according to the API's compatibility policy.

### 4.2. Mapping mutations in Spring

`@MutationMapping` maps a method to a field on the `Mutation` root type. You can continue using the controller from the query section:

~~~java
@MutationMapping
public Book createBook(
        @Argument("input") @Valid CreateBookInput input
) {
    return bookService.create(input.title(), input.authorId());
}
~~~

`@Argument("input")` instructs Spring to convert the GraphQL input object into `CreateBookInput`. `@Valid` triggers Bean Validation if the application has Jakarta Bean Validation configured and the input carries appropriate constraints. For example, you can declare `@NotBlank` on `title` to reject empty or whitespace-only strings.

Example input with validation:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String authorId
) {}
~~~

Validation at the input layer catches malformed data early. The service still needs to verify business rules such as whether the author exists or whether the current user has permission to create a book. Client-side validation should never be treated as a data protection boundary.

### 4.3. Mutation execution characteristics

Top-level fields in the same mutation operation are executed by GraphQL sequentially in order of appearance. This is useful when a single request needs to perform multiple write operations with an ordering dependency. However, GraphQL's sequential execution does not automatically create a database transaction. If multiple changes must succeed or fail together, use transactions at the service or repository layer.

A mutation should return enough data for the client to update the UI after the operation. For example, `createBook` returns the newly created `Book` so the client receives the server-assigned ID and normalized values.

A mutation can fail due to invalid input, missing resources, business rule violations, or infrastructure errors. Distinguish between validation errors, business errors, and system errors; do not expose stack traces or sensitive internal details in client responses. You can use Spring for GraphQL's exception handling mechanisms, such as `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`, to standardize errors.

## 5. Subscription: receiving real-time data

### 5.1. How does a subscription operation work?

Queries and mutations typically return one result for one execution. A subscription creates a stream of results: the server emits a response whenever a matching event occurs, until the client unsubscribes or the connection closes.

A client can subscribe to new books:

~~~graphql
subscription WatchNewBooks {
    bookCreated {
        id
        title
        authorId
    }
}
~~~

Each time the server emits a `bookCreated` event, the client receives a payload matching the requested selection set. A subscription operation has only one top-level field to identify the event stream to monitor.

GraphQL defines how subscriptions are described, without mandating a single transport protocol. Spring for GraphQL applications commonly use WebSocket for long-lived bidirectional connections; Spring for GraphQL also supports other transport options such as RSocket when configured accordingly. With WebSocket, the client and server must agree on a GraphQL WebSocket subprotocol, commonly `graphql-transport-ws`.

### 5.2. Mapping subscriptions with `@SubscriptionMapping`

Spring for GraphQL supports reactive return types such as `Flux<T>` to represent an event stream. A resolver can be written as follows:

~~~java
@SubscriptionMapping
public Flux<Book> bookCreated() {
    return bookService.bookCreatedEvents();
}
~~~

`bookCreatedEvents()` needs to return a publisher emitting each newly created book. The publisher can be built using Reactor Sinks, a message broker, or another event source. Example service contract:

~~~java
public interface BookService {

    Optional<Book> findById(String id);

    List<Book> findAll();

    Book create(String title, String authorId);

    Flux<Book> bookCreatedEvents();
}
~~~

When `create()` successfully creates a book, the service layer can emit the corresponding event into the publisher or send it to a broker. The subscription resolver simply supplies that stream to the GraphQL engine; it should not perform data writes itself.

### 5.3. Transport configuration and operations

For clients to actually receive subscriptions, the application must enable and configure a transport that supports subscriptions. With WebSocket in Spring Boot, you can configure the endpoint using the property:

~~~properties
spring.graphql.websocket.path=/graphql
~~~

At the same time, you need WebSocket support compatible with the Servlet or WebFlux stack in use. The HTTP endpoint and WebSocket endpoint can share the same path or be configured separately depending on the deployment architecture. Always verify the application's actual configuration and the URL used by clients.

Several issues need to be addressed when taking subscriptions to production:

- **Lifecycle management:** when a client disconnects or cancels a subscription, the publisher and associated resources must be released appropriately.
- **Backpressure and emission rate:** if the server emits faster than the client can consume, choose an appropriate buffering, limiting, or dropping strategy. Never let buffers grow unboundedly.
- **Multiple application instances:** an in-memory event stream in one instance is not automatically shared with other instances. Multi-instance deployments usually require a message broker or shared pub/sub infrastructure.
- **Authentication and authorization:** authenticate connections and check permissions for each event stream. Users should only receive events they are authorized to access.
- **Reconnection resilience:** clients may lose network connectivity or have their WebSocket connection closed. If missed events need to be recovered, the design must include event IDs, cursors, or a replay mechanism at the event layer; basic subscriptions do not guarantee replay of past events on their own.

Subscriptions are well suited for status notifications, processing progress, dashboard updates, or business events pushed to clients. For data that does not require continuous updates, polling queries are simpler and often easier to operate.

## 6. Processing flow in Spring for GraphQL

All operations go through the schema and the GraphQL engine. After validating the operation, the engine invokes the corresponding resolver; the resolver delegates to the service and returns the result to the engine to build the response.

~~~mermaid
sequenceDiagram
    participant Client
    participant GraphQL as Spring for GraphQL
    participant Resolver as Controller method
    participant Service
    participant Store as Data store / Event source

    Client->>GraphQL: Send operation and variables
    GraphQL->>GraphQL: Parse and validate against schema
    GraphQL->>Resolver: Invoke @QueryMapping or @MutationMapping
    Resolver->>Service: Call business logic
    Service->>Store: Read or modify data
    Store-->>Service: Return result
    Service-->>Resolver: Return domain result
    Resolver-->>GraphQL: Return field result
    GraphQL-->>Client: Response matching selection set
~~~

For subscriptions, execution after registration differs in that the resolver returns a publisher. The GraphQL engine continues converting each item from the publisher into a response sent over the transport until the stream completes or is canceled.

In Spring for GraphQL, common annotations have the following roles:

| Annotation | Role |
| --- | --- |
| `@QueryMapping` | Maps a method to a field on the `Query` root type |
| `@MutationMapping` | Maps a method to a field on the `Mutation` root type |
| `@SubscriptionMapping` | Maps a method to a field on the `Subscription` root type |
| `@Argument` | Reads a GraphQL field argument and binds it to a Java parameter |
| `@SchemaMapping` | Maps a method to a field on any object type |

The mapping annotations are convenient shorthands built on top of `@SchemaMapping`. You can use `@SchemaMapping` directly when you want to specify the type or field name explicitly.

## 7. Testing queries and mutations

You should not test Java methods in isolation alone. You need to test the schema, argument binding, and the actual GraphQL response seen by clients. Spring for GraphQL provides `GraphQlTester` and variants suited to different test styles.

Example of testing a query with `GraphQlTester`:

~~~java
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
    .isEqualTo("Practical GraphQL");
~~~

Example of testing a mutation:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
    .variable("input", Map.of(
        "title", "Practical GraphQL",
        "authorId", "author-12"
    ))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("Practical GraphQL");
~~~

Tests should cover both valid and error cases:

1. Queries that find data and queries that find no data.
2. Queries returning empty lists and populated lists.
3. Mutations receiving valid input, missing required fields, or failing validation.
4. Mutations encountering business errors, such as a non-existent author or a user lacking permission to create a book.
5. Schema rejecting non-existent fields or arguments.
6. Subscriptions emitting events, completing streams, and unsubscribing cleanly.

For subscriptions, test over the WebSocket transport using an appropriate tester such as `WebSocketGraphQlTester` to verify subscribing, receiving events, and unsubscribing. A unit test for a method returning `Flux` is not enough to confirm the WebSocket endpoint and protocol are configured properly.

## 8. Designing a safe and maintainable API

A good GraphQL API pays attention to both the schema and execution cost:

- **Query limits:** cap list sizes, support pagination, and consider query depth or complexity limits. Do not return an unbounded list just because clients can select fields.
- **Avoid N+1:** when a query fetches multiple objects and each needs related data loaded, use batching or DataLoader to group data access calls. Selecting fewer fields does not automatically eliminate N+1.
- **Data-level authorization:** authenticate requests and check permissions at the appropriate layer. Just because a client omits a field does not mean it is permitted to access that data; resolvers and services still must protect resources.
- **Validate inputs on the server:** use appropriate scalar types, constraint validation, and business rule checks. Do not trust client-submitted data.
- **Keep the schema stable:** prefer adding nullable fields or new input fields in a backwards-compatible way. When removing fields, follow a deprecation path and monitor active client usage.
- **Observe errors and performance:** log responsibly, track resolver durations, data access counts, and per-operation errors. Avoid logging tokens, personal data, or sensitive payloads.
- **Protect subscriptions:** limit connection counts and subscriptions per user, check permissions on every stream, and set appropriate buffer limits.

## 9. Workflow for implementing an operation

When adding a new GraphQL feature, you can follow this sequence:

1. Determine whether the feature reads data, modifies state, or monitors events to choose query, mutation, or subscription.
2. Declare fields, arguments, input objects, and return types in SDL; choose nullability based on real-world possible outcomes.
3. Write the resolver in a controller using the appropriate mapping annotation and bind arguments with `@Argument`.
4. Delegate business processing to a service; add validation, transactions, and authorization as needed.
5. For subscriptions, provide a publisher and configure the matching transport; check lifecycle, backpressure, and access permissions.
6. Use `GraphQlTester` or a transport-specific tester to verify responses, errors, and edge cases.

Once you understand the three operation types and how they map into Spring for GraphQL, you can design an API with a clear schema where clients proactively choose the data they receive and the server keeps business logic controlled in the proper layer.
