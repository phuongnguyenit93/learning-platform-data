# @MutationMapping for Mutation Fields

In GraphQL, a **mutation** is an operation used to modify data state, such as creating a book, updating author information, or deleting a record. The schema declares these operations in the `Mutation` root type; Spring for GraphQL uses the `@MutationMapping` annotation to bind a Java method to each field of that root type.

`@MutationMapping` helps controllers clearly express method intent and leverage Spring's argument binding, dependency injection, and exception handling mechanisms. When designing mutations, beyond mapping the field correctly, you need to consider input objects, return results, transactions, validation, authorization, and testing.

This lesson covers how to declare mutations in SDL, implement `@MutationMapping`, receive arguments using `@Argument`, build create/update/delete operations, and handle common scenarios in Spring for GraphQL.

## 1. What is a Mutation in GraphQL?

GraphQL defines three commonly used operation types:

| Operation | Purpose | Default root type |
| --- | --- | --- |
| Query | Reading data | `Query` |
| Mutation | Modifying data | `Mutation` |
| Subscription | Receiving events or data over time | `Subscription` |

Mutations are typically used for actions with side effects:

- Creating a new book.
- Renaming or updating an author's description.
- Placing or canceling an order.
- Marking a notification as read.
- Deleting a resource.

Client-side operation example:

```graphql
mutation {
  createBook(title: "Spring for GraphQL") {
    id
    title
  }
}
```

The `mutation` keyword specifies the operation type. The `createBook` field is the specific operation invoked on the root mutation type. The client can select fields of the returned object, just like querying data with Query.

A mutation is not a separate HTTP route. With Spring for GraphQL, Query and Mutation typically go through the same GraphQL endpoint; the GraphQL engine distinguishes the operation type based on the document sent by the client.

## 2. Declaring Mutation Fields in SDL

The root mutation type is typically declared using `type Mutation`:

```graphql
type Mutation {
  createBook(title: String!): Book!
}

type Book {
  id: ID!
  title: String!
}
```

The `createBook` field accepts a `title` argument and returns a non-null `Book`. The `!` in `String!` means the client must pass a non-null value. The `!` in `Book!` means the field must return a non-null object if execution succeeds.

When a schema has multiple operations, each operation is a field on the `Mutation` root type:

```graphql
type Mutation {
  createBook(input: CreateBookInput!): Book!
  updateBook(id: ID!, input: UpdateBookInput!): Book
  deleteBook(id: ID!): Boolean!
}
```

In real-world applications, input objects are usually easier to extend and manage than adding many arguments directly to a field. The following sections use input objects for illustration.

## 3. @MutationMapping Connects Java Methods to Mutation Fields

`@MutationMapping` is located in the package:

```java
org.springframework.graphql.data.method.annotation.MutationMapping
```

This annotation marks a method in a `@Controller` class as a handler for a field on the `Mutation` root type.

SDL:

```graphql
type Mutation {
  createBook(title: String!): Book!
}
```

Controller:

```java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(@Argument String title) {
        return bookService.create(title);
    }
}
```

Spring for GraphQL detects controller beans, reads mapping annotations, and registers data fetchers for the corresponding fields. When a client invokes `Mutation.createBook`, the `createBook` method is executed.

`@MutationMapping` is a shorthand for `@SchemaMapping` on the `Mutation` type. Both approaches below map to the `Mutation.createBook` field:

```java
@MutationMapping
public Book createBook(@Argument String title) {
    return bookService.create(title);
}
```

```java
@SchemaMapping(typeName = "Mutation", field = "createBook")
public Book createBook(@Argument String title) {
    return bookService.create(title);
}
```

Normally, `@MutationMapping` should be used because it clearly expresses the method's intent. `@SchemaMapping` is useful when mapping a field belonging to another type or when you need to explicitly specify the parent type.

## 4. Field Naming Rules

If no name is specified, Spring derives the field name from the method name. For example:

```java
@MutationMapping
public Book createBook(@Argument String title) {
    // ...
}
```

The method above maps to the `Mutation.createBook` field by default.

If the Java method name differs from the field name in SDL, specify `name`:

```java
@MutationMapping(name = "createBook")
public Book save(@Argument String title) {
    return bookService.create(title);
}
```

The field name must match the SDL exactly, including case sensitivity. If the schema declares `createBook` but the method accidentally maps to `save`, clients will not invoke the intended handler.

Avoid registering two methods that handle the same mutation field within the same application context. Each field should have a clear handler; if multiple business operations need coordination, the controller method can call an orchestrating service.

## 5. Receiving Data with @Argument

`@Argument` extracts values from a GraphQL field's arguments and converts them to the corresponding Java types.

### Receiving simple arguments

SDL:

```graphql
type Mutation {
  renameBook(id: ID!, title: String!): Book!
}
```

Controller:

```java
@MutationMapping
public Book renameBook(
        @Argument("id") String id,
        @Argument("title") String title) {
    return bookService.rename(id, title);
}
```

Client:

```graphql
mutation RenameBook {
  renameBook(id: "book-1", title: "Spring GraphQL in Practice") {
    id
    title
  }
}
```

You can specify the argument name in `@Argument("id")` to avoid relying on Java parameter names or compiler configuration to retain parameter names.

### Receiving an input object

When a mutation needs multiple pieces of data, group them into an input type:

```graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  publishedYear: Int
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
```

Java input model:

```java
public record CreateBookInput(
        String title,
        String authorId,
        Integer publishedYear) {
}
```

Controller:

```java
@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
```

The client sends the input using variables:

```graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
    publishedYear
  }
}
```

```json
{
  "input": {
    "title": "Spring for GraphQL",
    "authorId": "author-1",
    "publishedYear": 2026
  }
}
```

GraphQL validates types and nullability before invoking the resolver. Spring for GraphQL then binds the input map to the Java input object. Using a separate DTO or record for input prevents the API from coupling directly to persistence entities.

## 6. Building a Create Mutation

A create mutation typically takes an input object and returns the newly created object:

```graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  publishedYear: Int
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  author: Author
  publishedYear: Int
}
```

Controller:

```java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(@Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
```

The service performs business logic and persistence:

```java
@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    public Book create(CreateBookInput input) {
        Book book = new Book(
                UUID.randomUUID().toString(),
                input.title().trim(),
                input.authorId(),
                input.publishedYear());

        return bookRepository.save(book);
    }
}
```

This snippet illustrates the processing flow; the model and repository should be adapted to the application's persistence technology. The key point is that the controller receives the input and delegates business logic to the service. Transactions are typically placed on the service method so commit/rollback boundaries align with the use case.

## 7. Building an Update Mutation

An update mutation must clearly define the semantics of each field: replacing the entire resource or performing a partial update.

Example of updating a title:

```graphql
input UpdateBookInput {
  title: String!
  publishedYear: Int
}

type Mutation {
  updateBook(id: ID!, input: UpdateBookInput!): Book
}
```

Controller:

```java
@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {
    return bookService.update(id, input);
}
```

If the book does not exist, the schema allows returning `null` because the result is a nullable `Book`. The application can also choose to throw a domain exception and translate it into a GraphQL error, or return a payload containing a business error field.

### Distinguishing omitted and null in partial updates

In a partial update, three states often carry different meanings:

| Value sent by client | Common meaning |
| --- | --- |
| Field omitted | Keep the existing value |
| Field sent as `null` | Clear the value if business rules allow |
| Specific value sent | Update to that value |

Schema example:

```graphql
type Mutation {
  updateBookSummary(id: ID!, summary: String): Book
}
```

In Spring for GraphQL, you can use `ArgumentValue<T>` to distinguish an omitted argument from an argument explicitly sent as null:

```java
import org.springframework.graphql.data.ArgumentValue;

@MutationMapping
public Book updateBookSummary(
        @Argument("id") String id,
        @Argument("summary") ArgumentValue<String> summary) {

    if (summary.isOmitted()) {
        return bookService.keepSummary(id);
    }
    if (summary.value() == null) {
        return bookService.clearSummary(id);
    }
    return bookService.updateSummary(id, summary.value());
}
```

Do not define a default value for the argument if you need to preserve the omitted state. When GraphQL applies a default, the resolver receives the default value instead of indicating that the client omitted the argument.

## 8. Building a Delete Mutation

A delete mutation can return a boolean:

```graphql
type Mutation {
  deleteBook(id: ID!): Boolean!
}
```

```java
@MutationMapping
public boolean deleteBook(@Argument("id") String id) {
    return bookService.delete(id);
}
```

However, a boolean does not indicate which record was deleted or provide additional metadata to the client. For larger APIs, you can return a payload:

```graphql
type DeleteBookPayload {
  deletedBookId: ID!
  deleted: Boolean!
}

type Mutation {
  deleteBook(id: ID!): DeleteBookPayload!
}
```

A payload allows adding information in the future without changing the return type from a scalar to another type. Choose the return type based on client requirements and the API contract.

## 9. Designing a Mutation Payload

Returning a domain object directly works well for simple operations. When clients need metadata, warnings, or structured validation errors, a payload is usually more flexible.

```graphql
type UserError {
  code: String!
  field: String
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

The controller can return the payload:

```java
@MutationMapping
public CreateBookPayload createBook(
        @Argument("input") CreateBookInput input) {
    return bookService.createWithPayload(input);
}
```

You should distinguish between two categories of situations:

- **Predictable business errors:** for example, the title is already in use, or the current state does not allow updates. You can return `userErrors` or an explicit result type so the client can display and handle it.
- **Execution or infrastructure errors:** for example, database unavailable, programming bugs, or dependency timeouts. These errors typically go through GraphQL error handling and are returned in the `errors` array.

Do not return HTTP/GraphQL success with an empty payload for every error. The client needs to know whether the operation succeeded, failed due to validation, or failed due to a system error.

## 10. Mutations and Transactions

GraphQL specifies that top-level fields in a mutation operation are executed serially in the order they appear. This ensures mutation fields within the same operation do not run in parallel like regular Query fields.

Example:

```graphql
mutation {
  createDraft(title: "GraphQL") {
    id
  }
  publishDraft(id: "draft-1") {
    id
    status
  }
}
```

The `publishDraft` field executes after `createDraft` within the same mutation operation. However, serial execution **does not automatically create a database transaction spanning the entire operation**. If the first field succeeds and the second fails, GraphQL does not automatically roll back side effects from the earlier field.

Place transactions on the service method:

```java
@Service
public class BookService {

    @Transactional
    public Book create(CreateBookInput input) {
        // Validate and persist data within a transaction.
    }
}
```

If a use case involves multiple changes requiring atomicity, implement them inside a single service method and transaction rather than relying on multiple top-level mutation fields. Transaction boundaries should reflect the business invariants the system must guarantee.

## 11. Validating Mutation Input

GraphQL validates the structure and data types of inputs. For example, `title: String!` prevents the client from omitting the field or passing null, but it does not prevent empty strings, whitespace-only strings, or titles exceeding business limits.

Business validation should be performed on the server. You can use Bean Validation on the input DTO:

```java
public record CreateBookInput(
        @NotBlank
        @Size(max = 200)
        String title,

        @NotBlank
        String authorId,

        @Min(1)
        Integer publishedYear) {
}
```

The controller can trigger argument validation using `@Valid` if Jakarta Bean Validation is configured in the application:

```java
@MutationMapping
public Book createBook(
        @Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
```

Service-level validation is still necessary for rules that depend on database state, such as verifying that the author exists, the book is not a duplicate, or the user has permission to create a book in that library. Never rely on client-side validation because clients can send requests directly.

## 12. Handling Errors from Mutations

Mutations can fail for many reasons:

- Invalid input.
- Resource not found.
- Business rule violation.
- User lacks permission to perform the action.
- Database or downstream service error.

Spring for GraphQL supports exception handling mechanisms for GraphQL, including `DataFetcherExceptionResolver` and `@GraphQlExceptionHandler` in controllers/advice. You can translate domain exceptions into GraphQL errors with appropriate messages, classifications, or extensions.

Categorization examples:

| Scenario | Appropriate representation |
| --- | --- |
| Missing required title | GraphQL input coercion error or validation error |
| Book does not exist | Nullable result, typed user error, or domain error per contract |
| User lacks sufficient permission | Authorization error without leaking sensitive details |
| Database outage | Safely logged and mapped execution error |
| Version conflict during update | Conflict result/error with a code for the client to handle |

Do not return stack traces, SQL, connection strings, or internal data in error messages sent to clients. Log details on the server and return a safe message, including a correlation ID if needed.

## 13. Securing Mutations

Mutations modify data and therefore require explicit authorization. Knowing a resource's ID does not mean the client has permission to modify or delete that resource.

You can protect methods with Spring Security:

```java
@MutationMapping
@PreAuthorize("hasAuthority('BOOK_WRITE')")
public Book archiveBook(@Argument("id") String id) {
    return bookService.archive(id);
}
```

Depending on application design, authorization can also be placed in the service layer to ensure non-GraphQL call paths are protected as well. For resource-dependent permissions, verify ownership or tenant access within service/domain logic rather than checking only a coarse-grained role.

Key principles:

- Authenticate the caller before processing sensitive operations.
- Verify permissions on the actual resource being updated or deleted.
- Never trust `ownerId`, `tenantId`, or roles sent by the client in the input.
- Do not return sensitive data in payloads or errors.
- Record audit events for critical operations.
- Consider rate limiting and idempotency for operations that may be retried.

## 14. Idempotency and Concurrent Updates

Clients may resend a mutation after a timeout or connection drop even when the server already executed the side effect. If the operation is not idempotent, retries can create duplicate data or execute a transaction multiple times.

For order creation, payments, or critical resource creation, consider an idempotency key:

```graphql
input CreateOrderInput {
  idempotencyKey: ID!
  productId: ID!
  quantity: Int!
}
```

The server stores the key alongside the operation result and returns the previous result when receiving a duplicate key according to business rules. Idempotency must be enforced at the server/database level; simply adding a field to the SDL is not enough.

For concurrent updates, you can use a version number or optimistic locking:

```graphql
input UpdateBookInput {
  title: String
  expectedVersion: Int!
}
```

The service checks the current version before writing. If the data has been updated by someone else, return a conflict so the client can reload the latest state and decide how to proceed.

## 15. Mutations and the DataLoader Cache

Within a single GraphQL request, DataLoader may cache loaded results. If a mutation updates an entity and the response continues reading that entity or its relationships through DataLoader, the cache might still hold stale values.

After writing data, consider clearing or priming the affected keys:

```java
Book updated = bookService.update(id, input);

dataLoader.clear(id).prime(id, updated);
return updated;
```

This snippet only illustrates the concept; how the DataLoader is injected and the key/value types must match the application's actual loader. Invalidate only relevant keys and keep the cache scoped to the request. DataLoader does not replace a shared cache or system-wide data synchronization mechanism.

## 16. Testing @MutationMapping with GraphQlTester

`GraphQlTester` lets you test mutations without sending real HTTP requests. For a controller test slice, you can use `@GraphQlTest` and a mock service:

```java
@GraphQlTest(BookMutationController.class)
class BookMutationControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    BookService bookService;

    @Test
    void createsBookFromInput() {
        Book created = new Book(
                "book-1",
                "Spring for GraphQL");

        given(bookService.create(any(CreateBookInput.class)))
                .willReturn(created);

        graphQlTester.document("""
                mutation CreateBook($input: CreateBookInput!) {
                    createBook(input: $input) {
                        id
                        title
                    }
                }
                """)
                .variable("input", Map.of(
                        "title", "Spring for GraphQL",
                        "authorId", "author-1"))
                .execute()
                .path("createBook.id")
                .entity(String.class)
                .isEqualTo("book-1");

        then(bookService).should()
                .create(any(CreateBookInput.class));
    }
}
```

This is an illustrative example; add constructors, fields, and data types matching your project's models. Depending on the Spring Boot version, the mock bean annotation may be `@MockBean` or `@MockitoBean`.

Tests should cover scenarios such as:

- Valid input and the mutation returns the expected result.
- Missing non-null argument or incorrect input type.
- Input violating business validation rules.
- Resource not found.
- User lacking sufficient permissions.
- Version conflict or duplicate idempotency key.
- Service errors translated into GraphQL errors or typed payloads matching the contract.
- DataLoader cache updated if the mutation modifies data cached within the same request.

`@GraphQlTest` is suitable for verifying controller mapping and responses. Use integration tests with a real database or Testcontainers when you need to verify transactions, constraints, optimistic locking, and data integrity.

## 17. Common Pitfalls When Using @MutationMapping

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Mutation field does not invoke the method | Controller is not scanned or method lacks annotation | Check `@Controller`, component scanning, and `@MutationMapping` |
| Field does not exist | SDL has not declared the field in root `Mutation` | Add the field to the SDL |
| Method does not receive the right input | Argument name or Java type mismatch | Use `@Argument("input")` and a compatible DTO |
| Resolver is not mapped by the right name | Method name differs from SDL field name | Specify `@MutationMapping(name = "...")` |
| Argument is null despite expecting a default | Client explicitly passed null | Distinguish omitted from null and check operation variables |
| Partial update unintentionally clears data | Not distinguishing omitted fields from null | Use `ArgumentValue<T>` or an input model that explicitly represents state |
| Mutation partially succeeds | Relying on serial execution without an enclosing transaction | Put the atomic use case into a single service transaction |
| Retries create duplicate data | Mutation lacks an idempotency strategy | Use an idempotency key and appropriate unique constraints |
| Response returns stale data | DataLoader cache was not invalidated | Clear or prime relevant keys after the mutation |
| Test cannot find controller/configuration | Test slice is missing controller or dependent beans | Specify the controller, import configurers, and mock services |

## 18. Mutation Design Principles

- Place data-modifying operations in the `Mutation` root type.
- Use `@MutationMapping` for mutation fields and `@Argument` to bind inputs.
- Use input objects for mutations with multiple fields or room to grow.
- Use dedicated input DTOs and avoid binding persistence entities directly from clients.
- Return domain objects or structured payloads tailored to client needs.
- Distinguish predictable business errors from execution errors.
- Place transaction boundaries at the service/use case layer.
- Do not assume serial execution equals a database transaction.
- Distinguish omitted, null, and concrete values in partial updates.
- Enforce authorization on actual resources and tenants.
- Design idempotency for mutations that may be retried.
- Handle optimistic locking when multiple clients can update the same data.
- Update the DataLoader cache within the same request if a mutation alters already-loaded data.
- Test success paths, validation, authorization, and persistence failures.

## 19. Hands-On Exercise

Build a mutation API for a library application:

1. Declare `CreateBookInput`, `UpdateBookInput`, and the `Mutation` root type.
2. Write `BookMutationController` with `@MutationMapping` for `createBook`, `updateBook`, and `deleteBook`.
3. Use `@Argument` to bind input objects to Java records.
4. Move persistence logic into `BookService` and define transactions per use case.
5. Design `CreateBookPayload` with `book` and `userErrors`.
6. Add validation for title and author ID.
7. Add authorization for archive or delete operations.
8. Write `GraphQlTester` tests for create, update, delete, and validation failures.
9. Try sending two mutation fields in a single operation and observe the execution order.
10. Explain why mutation ordering does not automatically guarantee rollback for the entire operation.

When finished, you should know how to map a Mutation field to a Java method, bind inputs, choose payloads, manage transactions, and secure data-modifying operations in Spring for GraphQL.

## 20. References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Specification — Execution](https://spec.graphql.org/October2021/#sec-Normal-and-Serial-Execution)

Method argument signatures, validation integration, and supported annotations may vary across Spring for GraphQL/Spring Boot versions. When upgrading dependencies, check the reference documentation and Javadoc for the exact version used by your project.
