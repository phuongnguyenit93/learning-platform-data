# Resource Creation Mutations in Spring for GraphQL

A mutation is an operation used to change system state. In a resource management API, mutations frequently create a new resource such as a book, customer, order, or product. With Spring for GraphQL, we declare the creation field in the `Mutation` root type and implement it using a method annotated with `@MutationMapping`.

A resource creation mutation must clearly define what data clients are allowed to send, how inputs are validated, where IDs are generated, business rules, transactions, and returned data. The GraphQL controller receives the input and invokes the application service; the service executes the creation use case and coordinates repositories; GraphQL serializes the result according to the selection set requested by the client.

After this lesson, you will be able to:

- Design SDL for resource creation mutations with appropriate input and output types.
- Implement `@MutationMapping` and bind inputs using `@Argument`.
- Structure the resource creation flow across controller, service, and repository.
- Generate IDs on the server, validate relationships, and return the newly created resource.
- Handle validation, authorization, transactions, and business errors.
- Design response payloads and understand nullability when creation fails.
- Test mutations with `GraphQlTester`.
- Account for duplicate requests, idempotency, and concurrency when APIs are called repeatedly.

## 1. What is a Resource Creation Mutation?

GraphQL has three root operation types: `Query` for reading data, `Mutation` for changing state, and `Subscription` for receiving event streams. When a client wants to create a new resource, it calls a field on the `Mutation` root type.

For example, a library API allows creating a new book. The client sends the title, author ID, and publication year; the server validates the input, generates an ID, persists the book, and returns the newly created resource.

```graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}

input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
}

type Book {
    id: ID!
    title: String!
    publishedYear: Int
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

The `createBook` field accepts a required input object and returns a `Book`. The client can select the fields it needs after creation succeeds:

```graphql
mutation {
    createBook(input: {
        title: "Spring GraphQL in Practice"
        authorId: "author-42"
        publishedYear: 2026
    }) {
        id
        title
        publishedYear
    }
}
```

Resource creation mutations usually return the newly created data so the client does not need to send another query just to retrieve the ID or initial attributes. The server still returns only the fields selected by the client in the selection set.

According to GraphQL execution rules, top-level fields of a mutation operation execute serially in the order they appear in the document. This allows clients to perform multiple ordered changes in one operation. However, GraphQL does not automatically open a database transaction spanning all those fields; if multiple changes require atomicity, create a single mutation/use case and manage the transaction in the service. Independent mutation requests can still run concurrently.

## 2. Designing the Input Type for Creation

Related input fields should be grouped into an input object:

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
    tags: [String!]
}
```

Input types separate data clients are allowed to submit from server-managed data. For instance, `id`, `createdAt`, `createdBy`, and initial moderation status are typically generated or enforced by business rules on the server, so they do not belong in `CreateBookInput`.

Do not reuse an output object type as an input. GraphQL distinguishes input types from output types: input objects can only contain scalars, enums, or other input objects; output objects can contain nested object fields and their own resolvers.

### Why use an input object?

- Input fields are grouped into a named, extensible structure.
- Inputs can be reused across mutations if their semantics are truly identical.
- Validation can be applied on the corresponding DTO/record.
- Prevents accidentally letting clients supply internal fields such as IDs, audit metadata, or system states.
- Makes it easy to distinguish a creation operation from a partial update operation.

If a mutation only accepts a single simple value, a direct argument can be used. When an operation has multiple fields or may evolve, an input object is generally easier to maintain.

## 3. Choosing the Return Type: Resource or Payload?

A mutation can return the newly created resource directly:

```graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

This is a concise design, ideal when the client only needs the resource. If the outcome requires extra metadata such as a message, processing status, warnings, or per-field errors, you can use a payload type:

```graphql
type CreateBookPayload {
    book: Book
    message: String!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
```

A payload makes the contract more expressive when the operation produces multiple pieces of outcome data. Do not wrap a single object in a payload if it adds no extra meaning.

For bulk operations or partial-success scenarios, the payload can hold per-item results:

```graphql
type CreateBookItemResult {
    index: Int!
    book: Book
    errorCode: String
    message: String
}

type CreateBooksPayload {
    results: [CreateBookItemResult!]!
}

type Mutation {
    createBooks(inputs: [CreateBookInput!]!): CreateBooksPayload!
}
```

Choose a payload based on use-case semantics, not merely out of formal convention. For a simple resource, returning `Book!` directly is sufficient.

## 4. Implementing with @MutationMapping

Spring for GraphQL provides `@MutationMapping` to link a controller method with a matching field on the `Mutation` root type:

```java
public record CreateBookInput(
        String title,
        String authorId,
        Integer publishedYear) {
}

@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public BookView createBook(@Argument("input") CreateBookInput input) {
        CreateBookCommand command = new CreateBookCommand(
                input.title(),
                input.authorId(),
                input.publishedYear());

        return bookService.create(command);
    }
}
```

`@Argument("input")` binds the `input` argument from the GraphQL document to the `CreateBookInput` record. `@MutationMapping` defaults to using the method name as the field name; therefore, `createBook` maps to `Mutation.createBook`.

If the method name differs from the field name, specify the mapping name explicitly:

```java
@MutationMapping(name = "createBook")
public BookView create(@Argument("input") CreateBookInput input) {
    return bookService.create(toCommand(input));
}
```

The controller method should focus on receiving input, converting it to a command, and invoking the service. Generating IDs, checking whether the author exists, setting initial state, and persisting data belong to the book creation use case.

## 5. Resource Creation Flow Through Service and Repository

A typical creation flow:

```mermaid
flowchart TD
    A[Client sends mutation] --> B[GraphQL validates operation]
    B --> C[@MutationMapping receives input]
    C --> D[Bind and validate DTO]
    D --> E[BookService.create command]
    E --> F[Check author and business rules]
    F --> G[Generate ID and create entity]
    G --> H[Repository saves resource]
    H --> I[Map to BookView]
    I --> J[GraphQL resolves selection set]
    J --> K[Return response]
```

The service can be implemented as follows:

```java
public record CreateBookCommand(
        String title,
        String authorId,
        Integer publishedYear) {
}

@Service
public class BookService {

    private final BookRepository bookRepository;
    private final AuthorRepository authorRepository;
    private final BookMapper bookMapper;

    public BookService(
            BookRepository bookRepository,
            AuthorRepository authorRepository,
            BookMapper bookMapper) {
        this.bookRepository = bookRepository;
        this.authorRepository = authorRepository;
        this.bookMapper = bookMapper;
    }

    @Transactional
    public BookView create(CreateBookCommand command) {
        AuthorEntity author = authorRepository.findById(command.authorId())
                .orElseThrow(() -> new AuthorNotFoundException(command.authorId()));

        BookEntity book = new BookEntity();
        book.setId(UUID.randomUUID().toString());
        book.setTitle(command.title().trim());
        book.setPublishedYear(command.publishedYear());
        book.setAuthor(author);

        BookEntity saved = bookRepository.save(book);
        return bookMapper.toView(saved);
    }
}
```

This is a JPA-style illustrative example. In systems using database-generated IDs, the service can let the repository/database generate the ID and read it from the saved entity. In systems using UUID, ULID, or IDs from another service, ID generation should live in the appropriate application/domain layer.

## 6. IDs and Server-Managed Fields

When creating a resource, determine which fields are decided by the client and which are controlled by the server.

| Field | Common source | Reason |
| --- | --- | --- |
| `title` | Client | Business data entered by the user |
| `authorId` | Client | Reference to an existing resource |
| `id` | Server/database | Unique identifier managed by the system |
| `createdAt` | Server | Trustworthy creation timestamp |
| `createdBy` | Security context | Authenticated user identity |
| `status` | Business rules | Initial status must follow application policy |

Never trust `createdBy` or `createdAt` sent by the client when those fields carry audit significance. If clients are allowed to pass arbitrary IDs, the service must validate permissions and ID conflicts; for most resource creation operations, server-side ID generation avoids spoofing or unintended collisions.

The ID should be returned in the response so the client can reference the new resource. If the database generates the ID on insert, ensure the mapper reads the post-save value rather than a pre-insert value that might still be null.

## 7. Validating Inputs Before Creation

The GraphQL schema validates types and nullability. For example, `title: String!` requires clients to provide a non-null value, but it does not guarantee a non-blank string or compliance with business length limits.

Bean Validation can be applied on the record:

```java
public record CreateBookInput(
        @NotBlank(message = "Title must not be blank")
        @Size(max = 200, message = "Title must be at most 200 characters")
        String title,

        @NotBlank(message = "Author ID is required")
        String authorId,

        @Min(1450)
        @Max(2100)
        Integer publishedYear) {
}
```

The controller requests validation on the argument:

```java
@MutationMapping
public BookView createBook(
        @Argument("input") @Valid CreateBookInput input) {
    return bookService.create(toCommand(input));
}
```

The application needs a Bean Validation provider and proper configuration. DTO validation fits format, length, and local input constraints. Rules depending on existing data—such as verifying that the author exists, the title is unique within the catalog, or the user has permission to create books—must be checked in the service/domain layer.

Do not rely exclusively on controller validation. Services may be invoked from REST endpoints, jobs, or message consumers, so critical invariants must be enforced at the application/domain boundary.

## 8. Validating Relationships and Creation Permissions

Inputs may contain IDs of related resources, such as `authorId`. GraphQL confirming an argument has type `ID` only validates the scalar; it does not ensure the author exists or that the user is allowed to associate a book with that author.

The service should verify:

- Whether the referenced resource exists.
- Whether that resource is in a state that permits linking.
- Whether the caller has permission to create the resource within the corresponding tenant or data scope.
- Whether relationships form circular references or violate business constraints.

Spring Method Security can be used to restrict the use case:

```java
@PreAuthorize("hasAuthority('BOOK_CREATE')")
@Transactional
public BookView create(CreateBookCommand command) {
    // Check author, tenant, and invariants before saving.
    // ...
}
```

The application must have method security enabled. If permissions depend on the current user, the actor or tenant must be obtained from a trustworthy security context and passed into the use case as application data; never take an identity from client input and treat it as authenticated.

## 9. Transactions and When Results Are Returned

Creating a resource often requires a transaction to ensure related write operations succeed together. For instance, creating a book and writing an audit event to the same database can be done in a single `@Transactional` service method.

```java
@Transactional
public BookView create(CreateBookCommand command) {
    AuthorEntity author = authorRepository.findById(command.authorId())
            .orElseThrow(() -> new AuthorNotFoundException(command.authorId()));

    BookEntity book = bookRepository.save(BookEntity.create(command, author));
    auditRepository.save(AuditEntry.bookCreated(book.getId()));

    return bookMapper.toView(book);
}
```

If writing the audit entry fails and both repositories share the same transaction manager, the transaction rolls back the book creation. If you also need to publish an event to a broker or call an external system, a database transaction alone does not provide cross-system atomicity; consider a transactional outbox or an appropriate coordination workflow.

Controllers should not hold transactions open while waiting on clients. Transactions should wrap the synchronous use case or a reactive transaction boundary matching your data-access technology.

## 10. Returning the Created Resource and Resolving the Selection Set

After the service saves the resource, the controller returns `BookView`. GraphQL then resolves the fields requested by the client:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        author {
            id
            name
        }
    }
}
```

The service does not need to eagerly load every nested relationship if `BookView` only holds `authorId`. The `author` field can be resolved by `@SchemaMapping` or `@BatchMapping` from the source object. This keeps the mutation service focused on creating the book while GraphQL handles the selection set.

If the response needs computed fields such as `displayLabel`, provide a corresponding field resolver. Do not manually build a JSON response inside the mutation method; return a typed object so GraphQL enforces serialization and nullability against the schema.

## 11. Choosing Nullability and Representing Errors

The following schema:

```graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

commits that when the mutation succeeds, the field returns a non-null `Book`. If the service throws an exception, GraphQL returns an error in `errors`; because the field is non-null, null bubbles up to the nearest nullable parent. The root response may have `data: null` depending on error location and parent nullability.

If you want to represent business errors in a payload, you can design a stateful result:

```graphql
type UserError {
    field: String
    code: String!
    message: String!
}

type CreateBookPayload {
    book: Book
    userErrors: [UserError!]!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
```

Then validation errors can be returned inside `userErrors` while the response remains a valid payload. This is an API design choice; there is no need for payload errors if the application prefers representing errors with standard GraphQL errors.

Never return `Book!` with a dummy object or placeholder data when creation fails. Pick one consistent strategy: GraphQL errors, payloads with business errors, or a union result type if the API has a clear reason.

## 12. Mapping Exceptions to GraphQL Errors

Services should throw meaningful business exceptions such as `AuthorNotFoundException`, `DuplicateBookException`, or `BookCreationNotAllowedException`. The GraphQL layer can translate them into appropriate errors using `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`.

Handler example in controller advice:

```java
@ControllerAdvice
public class GraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleAuthorNotFound(AuthorNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.NOT_FOUND)
                .message("Author not found")
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleDuplicateBook(DuplicateBookException exception) {
        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.BAD_REQUEST)
                .message("A book with the same title already exists")
                .build();
    }
}
```

Messages sent to clients should provide enough context to handle the issue without exposing SQL, stack traces, or internal data. Server-side logs can preserve the full exception and diagnostic details.

## 13. Handling Duplicate Requests and Idempotency

If a client sends a creation mutation twice, the server may create two distinct resources. This is not necessarily a bug: a typical `create` mutation creates one resource per execution. However, retries caused by timeouts or dropped connections can leave the client unsure whether the first attempt committed.

If the use case needs to prevent duplicates when clients retry, you can introduce an idempotency key:

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    idempotencyKey: String!
}
```

The service stores the key alongside the result or created resource. Upon receiving the same key again within the defined user/operation scope, the service returns the previous result instead of creating a new resource. A database unique constraint or atomic key-storage mechanism is required to handle two concurrent requests.

Do not use the title or business fields alone as an idempotency key if they do not uniquely identify a single request intent. Creating two books with the same title twice may be two valid actions depending on the domain.

## 14. Concurrency and Data Constraints

Two clients can simultaneously create resources with identical data. Checking for duplicates before inserting is vulnerable to race conditions:

1. Request A checks that no book with title X exists.
2. Request B also checks that no book with title X exists.
3. Both insert.

If business rules require uniqueness, enforce a unique constraint in the database and translate constraint violations into an appropriate business error. Service checks provide early feedback, while persistence constraints protect correctness under contention.

For relationships like `authorId`, handle cases where the author is deleted or changes state while the book is being created. Foreign keys, transaction isolation, and domain rules must work together to safeguard data. Do not rely on a single existence check in the controller as the final guarantee.

## 15. Resource Creation Mutations with Reactive Return Types

In Spring WebFlux applications using reactive repositories, the resolver can return `Mono<BookView>`:

```java
@MutationMapping
public Mono<BookView> createBook(
        @Argument("input") CreateBookInput input) {

    CreateBookCommand command = toCommand(input);
    return reactiveBookService.create(command);
}
```

The service performs operations via non-blocking repositories and returns a publisher. When using R2DBC, transactions require a reactive transaction manager and keeping operations inside the same reactive pipeline. Never call `.block()` inside a resolver.

With Spring MVC and JPA/JDBC, synchronous methods are normally appropriate:

```java
@MutationMapping
public BookView createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(toCommand(input));
}
```

Do not wrap a blocking call in `Mono.just(bookService.create(...))` assuming it becomes non-blocking; the service call still executes eagerly before the publisher is created. If you must call a blocking library in WebFlux, isolate the call on a bounded scheduler/executor or replace it with a non-blocking API.

## 16. Testing Mutations with GraphQlTester

`GraphQlTester` tests mutations from the client's perspective, covering schema, argument binding, resolver execution, and response selection:

```java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
                publishedYear
            }
        }
        """)
    .variable("input", Map.of(
            "title", "Spring GraphQL in Practice",
            "authorId", "author-42",
            "publishedYear", 2026))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL in Practice");
```

You should also test:

1. Valid mutation creates the resource and returns a non-null ID.
2. The newly created resource can be queried back using the returned ID.
3. Missing non-null fields or wrong types are rejected by GraphQL before calling the service.
4. Inputs violating Bean Validation are mapped to errors according to configuration.
5. Non-existent referenced resources produce the expected business error.
6. Unauthorized users cannot create resources.
7. Duplicate requests or idempotency keys are handled properly.
8. Unique constraints handle two concurrent competing requests.
9. Errors when writing audit records or secondary relationships roll back the transaction as required.
10. Payloads or GraphQL errors match the response shape defined in the schema.

With `@GraphQlTest`, you can mock `BookService` to verify mapping and argument binding. Separate service tests verify transactions, repositories, and domain rules. Integration tests against a test database confirm ID generation, constraints, and real rollbacks.

## 17. Common Pitfalls

- **Placing creation fields in `Query`:** operations that modify state must belong to `Mutation`.
- **Accepting an entire entity from the client:** may let clients control IDs, audit fields, or internal state. Use purposeful input models.
- **Using an output type as input:** GraphQL separates input objects from object types.
- **Generating an ID before saving without syncing with the database:** responses may return the wrong ID or null. Use the ID from the persisted resource.
- **Validating relationships only in the controller:** the service/use case must still protect invariants and access permissions.
- **Omitting transactions across related writes:** can leave partially created resources or inconsistent audit logs.
- **Returning null for a non-null mutation on failure:** triggers null propagation and confusing responses. Choose clear error or payload semantics.
- **Ignoring retries:** clients can create duplicate resources after timeouts. Use idempotency if the use case requires it.
- **Checking duplicates only with a pre-insert query:** remains vulnerable to race conditions. Use unique constraints as the final safeguard.
- **Calling blocking services in WebFlux:** blocks reactive event-loop threads.
- **Mutation controller accessing multiple repositories directly:** scatters business logic and transactions. Move the use case into a service.

## 18. Workflow for Implementing a Resource Creation Mutation

When adding a creation mutation, follow this sequence:

1. Identify the resource and the fields clients are allowed to supply.
2. Declare the input type; let the server manage IDs, audit metadata, and system state where appropriate.
3. Choose between returning the resource directly or a payload with metadata/errors based on API needs.
4. Write the `@MutationMapping` method and bind input with `@Argument`.
5. Convert input into a command and call the application service.
6. In the service, check relationships, permissions, invariants, and duplicates; generate an ID or obtain it from persistence.
7. Persist the resource and related changes inside an appropriate transaction.
8. Return the saved DTO/resource so GraphQL resolves the selection set.
9. Map business errors to GraphQL errors or payloads per contract.
10. Test success, validation, authorization, rollback, retries, and concurrency.

A resource creation mutation is the entry point for a state-changing use case. Spring for GraphQL provides `@MutationMapping` to connect the SDL field to a controller; the service is responsible for creating the resource according to business rules, and the repository persists the data. When inputs are tightly scoped, IDs and metadata are server-managed, and transactions and errors are intentionally designed, clients receive the new resource with a stable GraphQL contract.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Argument Binding and Validation](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.arguments)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.exception-handling)
- [GraphQL Specification — Mutation](https://spec.graphql.org/October2021/#sec-Mutation)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
