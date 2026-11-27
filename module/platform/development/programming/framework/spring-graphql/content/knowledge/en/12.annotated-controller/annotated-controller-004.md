# `@MutationMapping` in Spring for GraphQL

A mutation is an operation used to change the state of a system, such as creating a book, updating a profile, or canceling an order. In Spring for GraphQL, the `@MutationMapping` annotation binds a controller method to the corresponding field on the `Mutation` root type of the GraphQL schema.

`@MutationMapping` lets you write mutation resolvers in a natural Spring style: receiving input via `@Argument`, calling a service to execute business logic, and returning the result so GraphQL can build the response. To implement mutations safely, you need clear input/output design, data validation, authorization, and transaction management at the proper layer.

## 1. What Are Mutations Used For?

GraphQL has three main operation groups:

- `Query`: reads data and should not cause side effects.
- `Mutation`: changes state or performs actions with side effects.
- `Subscription`: receives events emitted by the server over time.

Example in a book management application:

| Need | Appropriate Operation |
| --- | --- |
| View details of a book | Query |
| Create a new book | Mutation |
| Rename a book title | Mutation |
| Delete a book | Mutation |
| Receive notifications when a new book is added | Subscription |

Mutations are declared on the root object type named `Mutation`. If the schema has multiple mutation fields, the client can select the fields to execute in one operation. According to GraphQL rules, top-level fields in a single mutation operation are executed sequentially within that operation; this does not mean independent HTTP requests are processed globally sequentially by the server.

## 2. Declaring Mutations in GraphQL SDL

First, declare the object types, input types, and `Mutation` root in the schema file, for example `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    book(id: ID!): Book
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
    renameBook(id: ID!, title: String!): Book!
    deleteBook(id: ID!): Boolean!
}

input CreateBookInput {
    title: String!
    isbn: String!
}

type Book {
    id: ID!
    title: String!
    isbn: String!
}
```

The schema defines three mutations:

- `createBook` accepts an input object and returns the newly created book.
- `renameBook` accepts an ID and a new title, then returns the updated book.
- `deleteBook` accepts an ID and returns the deletion result as a Boolean.

`CreateBookInput` is an input object because the client sends data into the server. `Book` is an object type used for output. GraphQL distinguishes input types from output types; you cannot use a regular object type directly as an input argument.

## 3. Writing Resolvers with `@MutationMapping`

Create a Spring controller and mark mutation handler methods with `@MutationMapping`:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

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

    @MutationMapping
    public Book renameBook(
            @Argument("id") String id,
            @Argument("title") String title) {
        return bookService.rename(id, title);
    }

    @MutationMapping
    public Boolean deleteBook(@Argument("id") String id) {
        return bookService.delete(id);
    }
}
```

Spring for GraphQL discovers the controller and registers these methods as data fetchers for the `Mutation` root type. The method name is used by default to determine the field name. Thus `createBook` maps to `Mutation.createBook`, `renameBook` maps to `Mutation.renameBook`, and `deleteBook` maps to `Mutation.deleteBook`.

`@Argument("input")` extracts the value of the argument named `input` from the GraphQL request. Specifying the argument name explicitly as shown ensures the mapping does not depend on whether the Java compiler retains parameter name metadata.

`@MutationMapping` is a specialized annotation for fields on the `Mutation` root, similar to how `@QueryMapping` is used for the `Query` root. Essentially, it is a shorthand form of `@SchemaMapping(typeName = "Mutation")`.

## 4. Mapping Input Objects to Java Records

An input object in the SDL can be bound to a Java record or class with matching properties:

```java
public record CreateBookInput(String title, String isbn) {
}
```

When the client sends:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        isbn
    }
}
```

Variables JSON:

```json
{
  "input": {
    "title": "Spring for GraphQL",
    "isbn": "9780000000001"
  }
}
```

Spring for GraphQL converts the input into `CreateBookInput` and passes it to the controller method. Field names and data types in the input object must be compatible with the Java properties. For nested inputs, you can use nested records or corresponding classes to keep the data structure clear.

Use an input object when a mutation has multiple related parameters. This keeps the schema readable, extensible, and avoids having a mutation field with too many separate arguments. When adding new fields, consider nullability and defaults so you do not accidentally break existing clients.

## 5. Designing Return Types for Mutations

A mutation can return the created or updated object directly:

```graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

This is a simple approach when a successful operation always returns a `Book`. For larger APIs, you can use a payload type to hold the object along with metadata or predictable business errors:

```graphql
type CreateBookPayload {
    book: Book
    userErrors: [UserError!]!
}

type UserError {
    field: String
    message: String!
    code: String
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
```

A payload allows the API to represent business outcomes in a consistent structure, such as returning a list of validation errors that the client can display next to a form. When using this pattern, the controller must return `CreateBookPayload` instead of `Book` directly.

Distinguish expected business errors from system errors. For example, a duplicate title might be a business error returned in the payload's `userErrors`; an unavailable database or programming bug typically needs to be handled as a GraphQL execution error according to server policy.

## 6. Sending Mutations over HTTP

Clients typically send mutations via HTTP POST to the GraphQL endpoint. For example, the default endpoint is `/graphql`:

```bash
curl http://localhost:8080/graphql \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{
    "query": "mutation CreateBook($input: CreateBookInput!) { createBook(input: $input) { id title isbn } }",
    "variables": {
      "input": {
        "title": "Spring for GraphQL",
        "isbn": "9780000000001"
      }
    },
    "operationName": "CreateBook"
  }'
```

Sample response when created successfully:

```json
{
  "data": {
    "createBook": {
      "id": "book-101",
      "title": "Spring for GraphQL",
      "isbn": "9780000000001"
    }
  }
}
```

Using GraphQL variables lets clients reuse documents and pass data separately via JSON. Do not concatenate user-supplied strings directly into the query document, as that easily causes escaping errors and makes data types harder to control.

GraphQL over HTTP does not allow executing mutations using HTTP GET. Use POST for mutations and configure the client to match the application's endpoint.

## 7. Validation for Mutation Data

The SDL validates GraphQL types, but it does not automatically validate all business rules. For example, `title: String!` rejects null, yet still accepts an empty string. You can use Jakarta Bean Validation to validate inputs before calling the service.

Declare the input record:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record CreateBookInput(
        @NotBlank String title,
        @NotBlank
        @Pattern(regexp = "[0-9Xx-]{10,17}") String isbn) {
}
```

Apply `@Valid` to the resolver parameter:

```java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(@Valid @Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
```

For Bean Validation to work, the application needs a corresponding implementation, usually `spring-boot-starter-validation`. The regex rule in the example is only a basic format check and does not replace an ISBN checksum algorithm or full domain rules.

Validation should be performed at the appropriate layer. Input format checks can use Bean Validation; ISBN uniqueness or data ownership checks must be enforced in the service/domain layer and the database. Do not rely on the client to enforce these conditions on its own.

## 8. Error Handling in Mutations

When a mutation fails, the GraphQL response may contain both `data` and `errors`. If an error occurs in a mutation field, GraphQL may return null for that field and put error details in the `errors` array; the final result also depends on SDL nullability and where the error occurred.

Illustrative response example:

```json
{
  "data": {
    "createBook": null
  },
  "errors": [
    {
      "message": "ISBN already exists",
      "path": ["createBook"]
    }
  ]
}
```

This is an example of the structure, not a fixed Spring message. If `createBook` is declared as `Book!`, an error that prevents the field from completing can propagate null up to the parent level according to Non-Null rules. If you want to return business errors without nulling out the entire field, consider a payload type with `userErrors`.

Spring for GraphQL supports exception handling with `@GraphQlExceptionHandler` in controllers or `@ControllerAdvice`, as well as `DataFetcherExceptionResolver` at the GraphQL execution layer. General example:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlErrorAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .build();
    }
}
```

In a real application, build a `GraphQLError` with a message and classification appropriate for the API; the example above uses `@ControllerAdvice` to handle exceptions across related controllers. You can add extension codes if the client needs to categorize errors. Do not include stack traces, SQL, tokens, or internal data in responses sent to clients.

## 9. Transactions and Data Consistency

Mutations typically write data, so transactions should be managed in the service or appropriate domain layer. Example:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    public Book create(CreateBookInput input) {
        if (bookRepository.existsByIsbn(input.isbn())) {
            throw new DuplicateIsbnException(input.isbn());
        }

        BookEntity entity = new BookEntity(input.title(), input.isbn());
        BookEntity saved = bookRepository.save(entity);
        return new Book(saved.getId().toString(), saved.getTitle(), saved.getIsbn());
    }
}
```

This example assumes `BookRepository`, `BookEntity`, `Book`, and `DuplicateIsbnException` are application types. Checking for duplicates before writing helps produce an understandable error, but a unique constraint in the database is still required to handle two concurrent requests creating the same ISBN. Transactions do not replace data integrity constraints on their own.

Placing `@Transactional` on the service allows the transaction to span the entire business operation and be reused from other entry points. Do not rely on transactions only at the controller if the service is also called elsewhere.

## 10. Securing Mutations

Mutations can create, modify, or delete data, so they require explicit authorization:

- Authenticate the caller's identity using the application's security mechanism.
- Verify whether the user has permission to perform the action.
- Check permissions on the specific resource, for example ensuring a user can only edit books within their scope of management.
- Do not trust `userId`, `ownerId`, or roles self-reported by the client in the input; obtain identity from the authenticated security context.
- Record audit logs for important actions according to business requirements.
- For sensitive mutations, consider an idempotency key to avoid repeating side effects when a client retries a request.

You can use Spring Security method security such as `@PreAuthorize` on controllers or services. Example:

```java
@PreAuthorize("hasAuthority('BOOK_WRITE')")
@Transactional
public Book create(CreateBookInput input) {
    // Perform domain checks and save data.
}
```

This snippet assumes method security is enabled and authorities are granted via security configuration. Checking resource ownership must still be done in the service/domain layer because a general `BOOK_WRITE` authority may not be sufficient to allow editing every record.

## 11. Mutations and Idempotency

A creation mutation is usually not idempotent: sending the same request twice may create two records. A client might retry after a timeout without knowing whether the server committed the previous operation.

For operations that risk causing duplicate side effects, such as creating an order or processing a payment, you can design an `idempotencyKey` in the input:

```graphql
input CreateOrderInput {
    idempotencyKey: String!
    productId: ID!
    quantity: Int!
}

type Mutation {
    createOrder(input: CreateOrderInput!): Order!
}
```

The service must store the key alongside the operation result and enforce a unique constraint on the key within the appropriate scope. If the same key is received again, the service returns the recorded result instead of creating new side effects. Add this mechanism only when the business logic needs protection against retries or duplicate requests; GraphQL does not provide idempotency for mutations automatically.

## 12. Testing `@MutationMapping` with GraphQlTester

`GraphQlTester` lets you send GraphQL documents in tests and inspect responses. Example test for creating a book:

```java
@Test
void createBookReturnsSavedBook() {
    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                    isbn
                }
            }
            """)
        .variable("input", java.util.Map.of(
                "title", "Spring for GraphQL",
                "isbn", "9780000000001"))
        .execute()
        .path("createBook.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
}
```

This test assumes `graphQlTester` is configured in the test context and the service/repository returns predictable data. Isolate the database or use fixtures so tests can run repeatably.

In addition to the happy path, you should test:

1. Input missing a Non-Null field or passing null is rejected by GraphQL before invoking the resolver.
2. Malformed input or Bean Validation violations produce appropriate errors.
3. Duplicate ISBNs are handled according to business rules.
4. Unauthorized users cannot create, edit, or delete books.
5. Missing IDs during rename/delete are returned according to the chosen contract.
6. Failures inside a transaction do not leave partially written data.
7. Mutations return the expected payload, `data`, and `errors` matching the schema.
8. When an idempotency key is present, retried requests do not trigger a second side effect.

If you also need to verify the HTTP transport, use `HttpGraphQlTester` or `WebTestClient` to send requests through the actual endpoint. `GraphQlTester` at the execution layer is well suited for testing the schema and resolvers, though it does not necessarily exercise the entire HTTP stack.

## 13. Common Errors

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Mutation is not invoked | Method name does not match field in `Mutation` root or annotation is misplaced | Check SDL field name and `@MutationMapping`. |
| Argument receives null | Name in `@Argument` does not match argument or input field name | Specify `@Argument("...")` explicitly and check SDL. |
| Cannot bind input object | Java record/class has incompatible fields or types | Align field names and types between SDL and Java input. |
| Mutation returns Non-Null error | Resolver returns null while field is declared with `!` | Adjust service or design appropriate nullability/payload. |
| Validation does not run | Missing Bean Validation implementation or missing `@Valid` | Add validation starter and check method argument. |
| Partial data written | Transaction does not span entire operation or side effects happen outside transaction | Place transaction on service and design side-effect handling appropriately. |
| Duplicate records created on retry | Mutation lacks an idempotency mechanism | Use an idempotency key for operations needing duplicate protection. |
| Users can modify others' data | Only authentication is checked without resource authorization | Check permissions and ownership in service/domain. |

## 14. Mutation Implementation Checklist

1. Declare fields on the `Mutation` root and use input objects for structured data.
2. Create controller methods with `@MutationMapping` and map arguments with `@Argument`.
3. Keep controllers thin; move business logic into services.
4. Choose direct return types or payloads based on how clients need to handle business errors.
5. Use Bean Validation and check domain rules before writing data.
6. Manage transactions in services and use database constraints for integrity.
7. Apply authentication, authorization, and per-resource permission checks.
8. Consider idempotency for operations with critical side effects.
9. Test happy paths, invalid inputs, business errors, access permissions, and retries.
10. Use HTTP POST for mutations and have clients read both `data` and `errors`.

`@MutationMapping` connects a Spring controller method to a data-modifying action in a GraphQL schema. When inputs, outputs, validation, transactions, and authorization are clearly designed, mutations provide a client-friendly API while preserving system consistency.
