# Returning Payload Objects from Mutations

A mutation often needs to return multiple pieces of information after the server processes an operation: the newly created or updated resource, recoverable business errors, the operation status, and related details for the client to continue working. If a mutation only returns a domain object, the output contract can become restrictive as the use case evolves.

GraphQL allows mutations to return a custom-designed **payload object**. A payload is an object type describing the outcome of a specific operation. It can contain the modified resource, a list of business errors, metadata, or correlation information. In Spring for GraphQL, the handler is mapped with **@MutationMapping**, receives input via **@Argument**, and returns a DTO/record matching the payload type in the SDL.

This lesson focuses on designing mutation payloads, choosing nullability, representing business errors and distinguishing them from GraphQL execution errors, implementing payloads in Spring for GraphQL, and testing both success and failure responses.

## 1. What Problem Does a Payload Object Solve?

A mutation can return the newly created object directly:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

The client receives `Book` and selects the needed fields:

~~~graphql
mutation {
  createBook(input: {
    title: "Spring GraphQL"
    authorId: "author-01"
  }) {
    id
    title
  }
}
~~~

This design is simple and works well if the operation always succeeds or if errors are expressed entirely through GraphQL errors. However, when the client needs to receive both the object and actionable business errors, returning **Book** alone does not leave room to represent both.

You can define a dedicated payload:

~~~graphql
type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

A payload provides a clear response structure:

- Success: **book** has a value, **userErrors** is empty.
- Failure due to invalid data or business rules: **book** is null, **userErrors** contains errors that can be displayed or handled.

This is an API design pattern, not a GraphQL requirement. For simple operations, returning the object directly remains reasonable. Use a payload when a mutation genuinely needs multiple related outcome fields.

## 2. Defining a Payload in SDL

Example of a book creation mutation:

~~~graphql
type UserError {
  code: String!
  message: String!
  field: [String!]!
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
  clientMutationId: String
}

input CreateBookInput {
  title: String!
  authorId: ID!
  clientMutationId: String
}

type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

Each component has its own responsibility:

| Component | Responsibility |
|---|---|
| **CreateBookInput** | Data sent by the client to create a book |
| **CreateBookPayload** | Outcome of the book creation operation |
| **Book** | The created resource |
| **UserError** | Business error returned as part of the result |
| **clientMutationId** | Correlation value sent by the client and echoed back by the server if the API chooses to support it |

Payload names are usually tied to the mutation, such as **CreateBookPayload**, **UpdateBookPayload**, or **ArchiveBookPayload**. This naming convention helps clients understand which action the outcome object represents.

### Why can a payload contain a nullable Book?

The **book** field is declared as **Book**, which is nullable. If **book** were **Book!**, the server could not return null when the operation fails validation. When the payload pattern uses **userErrors** to describe business failures, the resource field typically needs to be nullable.

Conversely, **userErrors: [UserError!]!** guarantees the server always returns a non-null list of errors where each item is also non-null. On success, the list is **[]**.

This rule helps clients handle responses consistently:

- The payload is always present because the mutation returns **CreateBookPayload!**.
- The error list is always readable.
- The resource only exists when the creation succeeds.

## 3. Responses on Success and Business Errors

Operation:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    book {
      id
      title
      status
    }
    userErrors {
      code
      message
      field
    }
    clientMutationId
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "title": "Spring GraphQL",
    "authorId": "author-01",
    "clientMutationId": "create-book-form-7"
  }
}
~~~

Success response:

~~~json
{
  "data": {
    "createBook": {
      "book": {
        "id": "book-101",
        "title": "Spring GraphQL",
        "status": "DRAFT"
      },
      "userErrors": [],
      "clientMutationId": "create-book-form-7"
    }
  }
}
~~~

Response when the author does not exist:

~~~json
{
  "data": {
    "createBook": {
      "book": null,
      "userErrors": [
        {
          "code": "AUTHOR_NOT_FOUND",
          "message": "Selected author not found",
          "field": ["authorId"]
        }
      ],
      "clientMutationId": "create-book-form-7"
    }
  }
}
~~~

In the second case, the operation still executes successfully at the GraphQL level. The business operation could not create the book, but the client receives a valid payload and can display the error next to the corresponding field.

## 4. Distinguishing userErrors from GraphQL Errors

This is an important design decision when building mutations.

**Payload userErrors** fit predictable business errors that clients can handle as part of the result, for example:

- The book title is already in use.
- The author does not exist or cannot be selected.
- The current state does not allow updates.
- The input does not satisfy business rules.

**GraphQL top-level errors** fit operation-level or execution failures, for example:

- Malformed query/mutation syntax or schema validation failure.
- Missing non-null argument or wrong type passed.
- Scalar/enum variable coercion failure.
- The user is unauthorized to run the operation under security policies.
- Infrastructure or downstream dependencies encounter unexpected errors.
- A resolver throws an exception that is not mapped to a business error in the payload.

For instance, if the client sends a non-existent enum value, GraphQL rejects the variables before invoking the handler. In that case, no payload exists because the mutation resolver never ran.

Do not catch every exception and stuff it into **userErrors**. Doing so turns programming bugs, database failures, or system outages into fake business errors, making it hard for monitoring and clients to distinguish real conditions.

A response can contain both **data** and top-level **errors** depending on error location and nullability. The payload pattern does not replace GraphQL's error propagation rules.

## 5. Designing Useful UserError Types for Clients

An error type should have a stable code, a clear message, and a path to the related field:

~~~graphql
type UserError {
  code: String!
  message: String!
  field: [String!]!
}
~~~

Meaning:

- **code**: machine-readable code allowing the client to decide behavior.
- **message**: text suitable for display or explanatory context.
- **field**: path to the relevant input field; a list allows pinpointing nested fields.

Example error for nested input:

~~~json
{
  "code": "INVALID_QUANTITY",
  "message": "Quantity must be greater than 0",
  "field": ["lines", "1", "quantity"]
}
~~~

Clients can use **field** to attach messages next to the corresponding input control. If an error is not tied to a specific field, return an empty list.

### Using an enum for error codes when the error set is stable

If the API has a finite set of error codes managed in the schema, you can use an enum:

~~~graphql
enum CreateBookErrorCode {
  TITLE_ALREADY_EXISTS
  AUTHOR_NOT_FOUND
  INVALID_STATUS
}

type CreateBookUserError {
  code: CreateBookErrorCode!
  message: String!
  field: [String!]!
}
~~~

Enums allow safer client code generation, though every new error code requires a schema change. If error codes grow independently or span multiple domains, **String!** is more flexible. Choose based on how stable your contract is.

Error messages should not expose SQL, stack traces, tokens, internal details, or other users' data. If investigation details are needed, log them server-side with a correlation ID.

## 6. When to Return an Object Directly vs. Using a Payload?

You do not need a payload for every mutation. Compare the options:

| Criterion | Direct object return | Payload object return |
|---|---|---|
| Structure | Compact, resource only | Can include resource, errors, and metadata |
| Simple use cases | Good fit | May be redundant |
| Structured validation errors | Typically top-level GraphQL error | Can be returned in **userErrors** |
| Operation metadata | No dedicated place | Dedicated fields |
| Contract evolution | Changing return type can break clients | Payload fields can be added compatibly |
| Type naming | Uses domain object | Usually has a mutation-specific payload type |

Direct object return works well when:

- The mutation has a simple outcome.
- The client only needs the created/updated resource.
- There is no need to represent business errors inside response data.
- Top-level GraphQL errors already fit the contract well.

A payload works well when:

- The client needs multiple kinds of outcomes after the operation.
- Predictable business errors need to map back to input fields.
- Metadata such as processing status, warnings, or correlation info is required.
- Multiple clients rely on a clear and stable response contract.

Avoid mechanically adding fields like **success**, **message**, and **data** to every payload. Let the structure reflect the concrete business outcome.

## 7. Implementing Payloads with Spring for GraphQL

Suppose we have this schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  status: String!
}

type UserError {
  code: String!
  message: String!
  field: [String!]!
}

input CreateBookInput {
  title: String!
  authorId: ID!
  clientMutationId: String
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
  clientMutationId: String
}

type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

Java records for input and payload:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        String clientMutationId) {
}

public record UserError(
        String code,
        String message,
        List<String> field) {
}

public record CreateBookPayload(
        Book book,
        List<UserError> userErrors,
        String clientMutationId) {
}
~~~

Handler:

~~~java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public CreateBookPayload createBook(
            @Argument("input") CreateBookInput input) {

        CreateBookResult result = bookService.create(input);

        return new CreateBookPayload(
                result.book(),
                result.userErrors(),
                input.clientMutationId());
    }
}
~~~

**@MutationMapping** maps the method to the **Mutation.createBook** field. **@Argument("input")** binds the input object into **CreateBookInput**. GraphQL Java reads fields of the Java return value according to **CreateBookPayload**.

With Java records, component names should match field names in the SDL so the property data fetcher can read the corresponding values. If using standard DTO classes, follow JavaBean getter conventions.

## 8. Placing Validation and Transactions in the Right Layer

Payloads commonly represent predictable business errors. The service should check conditions before persisting data:

~~~java
public record CreateBookResult(
        Book book,
        List<UserError> userErrors) {
}
~~~

~~~java
@Service
public class BookService {

    private final BookRepository bookRepository;
    private final AuthorRepository authorRepository;

    public BookService(
            BookRepository bookRepository,
            AuthorRepository authorRepository) {
        this.bookRepository = bookRepository;
        this.authorRepository = authorRepository;
    }

    @Transactional
    public CreateBookResult create(CreateBookInput input) {
        List<UserError> errors = new ArrayList<>();

        if (bookRepository.existsByTitleIgnoreCase(input.title())) {
            errors.add(new UserError(
                    "TITLE_ALREADY_EXISTS",
                    "Book title is already in use",
                    List.of("title")));
        }

        if (!authorRepository.existsById(input.authorId())) {
            errors.add(new UserError(
                    "AUTHOR_NOT_FOUND",
                    "Selected author not found",
                    List.of("authorId")));
        }

        if (!errors.isEmpty()) {
            return new CreateBookResult(null, errors);
        }

        Author author = authorRepository.findById(input.authorId())
                .orElseThrow();

        Book book = Book.create(input.title(), author);
        Book saved = bookRepository.save(book);

        return new CreateBookResult(saved, List.of());
    }
}
~~~

In this example, all business checks run before saving the book. If errors occur, the service returns a failure result without creating data. If valid, saving takes place within the transaction.

### Do not swallow persistence errors to return a fake success payload

Pre-write checks do not eliminate all race conditions. For example, two concurrent requests may both pass a non-existence check for a title; a unique database constraint will allow only one request to succeed.

If the database throws an exception during write, do not arbitrarily catch it inside the transaction and return **userErrors** as if the transaction completed normally. The transaction may already be marked rollback-only or be in an unsafe state.

For known data contention errors, design a clear transaction boundary: let the transaction roll back, then translate recognized errors into a business result at an appropriate outer layer if required by the API. For unexpected infrastructure errors, let the exception pass through GraphQL error handling and log it.

### Bean Validation and payload errors

The schema checks types, required fields, and input coercion. Bean Validation can check constraints such as **@NotBlank**, **@Size**, or **@Min**. However, validation errors from **@Valid** may be handled as GraphQL errors depending on configuration and exception handling mechanisms.

If the API wants all recoverable validation errors to appear in **userErrors**, explicitly convert constraint violations into a **UserError** list per the contract. Do not assume that simply adding **@Valid** causes Spring to populate the **userErrors** field automatically.

You can use an application-layer validator that returns a structured error list, which the handler then wraps into the payload. Rules requiring database queries or authorization checks should still live in the service.

## 9. Payloads for Update and Delete Mutations

Payloads are not just for create operations. Updates can return the updated object and business errors:

~~~graphql
input UpdateBookInput {
  id: ID!
  title: String
}

type UpdateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type Mutation {
  updateBook(input: UpdateBookInput!): UpdateBookPayload!
}
~~~

Deletes can return the deleted resource or its identifier and status:

~~~graphql
type DeleteBookPayload {
  deletedBookId: ID
  userErrors: [UserError!]!
}

type Mutation {
  deleteBook(id: ID!): DeleteBookPayload!
}
~~~

For deletes, it is unnecessary to return the entire `Book` if the client only needs the deleted ID. Return enough data for the client to update its cache or UI.

A distinct payload per mutation helps the contract express the exact use case. Avoid sharing a single bloated **MutationPayload** with dozens of nullable fields across all operations when most fields are meaningless to individual mutations.

## 10. Payloads Can Contain Multiple Related Objects

A business operation may modify multiple resources. For example, placing an order can return the order and the created payment details:

~~~graphql
type OrderPayload {
  order: Order
  payment: Payment
  userErrors: [UserError!]!
}

type Mutation {
  placeOrder(input: PlaceOrderInput!): OrderPayload!
}
~~~

Clients can select the exact data they need:

~~~graphql
mutation PlaceOrder($input: PlaceOrderInput!) {
  placeOrder(input: $input) {
    order {
      id
      status
      total
    }
    payment {
      id
      status
    }
    userErrors {
      code
      message
      field
    }
  }
}
~~~

A payload only describes the response shape. It does not guarantee that creating `Order` and `Payment` committed atomically. Consistency must be designed in the application/service layer using transactions or appropriate distributed mechanisms.

If payment is processed asynchronously, the payload should reflect the real status, such as **PENDING**, rather than assuming payment succeeded just because the order was created.

## 11. clientMutationId, Correlation, and Idempotency

Some APIs include **clientMutationId** in inputs and payloads:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  clientMutationId: String
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
  clientMutationId: String
}
~~~

This value allows clients to match responses to sent operations, which is useful when multiple mutations are in flight or the UI needs request correlation.

However, **clientMutationId does not automatically guarantee idempotency**. If a client resends the same mutation after a timeout, the server could create duplicate resources without deduplication logic.

If safe retries are required, design a separate idempotency key:

- The client sends a stable key representing a single business intent.
- The server persists the key along with the result or processing state.
- Duplicate requests with the same key are recognized and do not repeat side effects.
- Keys must be scoped to the appropriate user/tenant and operation boundary.

Correlation IDs help trace requests; idempotency keys control duplicate side effects. Both concepts can coexist, but they should not be used interchangeably.

## 12. Payload Nullability and Schema Evolution

Nullability should reflect valid states:

~~~graphql
type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
  clientMutationId: String
}
~~~

This choice means:

- Payload is non-null because the mutation always returns a result structure when the resolver finishes normally.
- `Book` is nullable because the operation can fail due to business errors.
- **userErrors** is a non-null list so the client always receives a list, even when empty.
- **clientMutationId** is nullable because the client might omit it.

Changing **book** to **Book!** prevents the payload from representing business failures with **book: null**. Making **userErrors** nullable forces clients to handle an extra absent-list state.

When evolving a payload:

- Adding nullable fields is generally more compatible with older clients.
- Adding non-null fields requires the server to always provide a value and can significantly change the contract.
- Renaming or removing fields can break existing operations.
- Changing the **UserError** structure affects every client reading errors.

Add new fields deliberately, keep old fields during transition periods when needed, and use **@deprecated** to signal replacements.

## 13. Security When Returning Payloads

Payloads are data sent to clients. Do not expose raw exceptions, internal entities, or sensitive details in a payload just to make responses richer.

Key principles:

- Return only fields the client is authorized to read.
- Verify permissions on created/updated resources before placing them into the payload.
- Never include SQL, stack traces, internal paths, or credentials in **userErrors**.
- Never trust **ownerId**, **tenantId**, or roles sent by the client if the server must enforce them.
- Use stable error codes instead of forcing clients to parse message text.
- Never place sensitive data into **clientMutationId** or request logs.
- Keep authorization in the service layer so other adapters are protected as well.

If a user is unauthorized to execute a mutation, return a top-level authorization error per the API's security policy. Return that error in the payload only if doing so does not leak the existence of a resource or another user's permissions.

## 14. Testing Payload-Returning Mutations with GraphQlTester

`GraphQlTester` can verify both the success path and the business error path.

Success test:

~~~java
@SpringBootTest
class CreateBookMutationTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldReturnCreatedBookAndNoUserErrors() {
        graphQlTester.document("""
                mutation CreateBook($input: CreateBookInput!) {
                    createBook(input: $input) {
                        book {
                            title
                        }
                        userErrors {
                            code
                        }
                    }
                }
                """)
            .variable("input", Map.of(
                    "title", "Spring GraphQL",
                    "authorId", "author-01"))
            .execute()
            .path("createBook.book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");
    }
}
~~~

A business error test can verify that **book** is null and **userErrors** contains the expected code:

~~~java
graphQlTester.document("""
        mutation {
            createBook(input: {
                title: "Spring GraphQL"
                authorId: "missing-author"
            }) {
                book {
                    id
                }
                userErrors {
                    code
                    field
                }
            }
        }
        """)
    .execute()
    .path("createBook.book")
    .valueIsNull()
    .path("createBook.userErrors[0].code")
    .entity(String.class)
    .isEqualTo("AUTHOR_NOT_FOUND");
~~~

Scenarios to test:

1. Successful mutation returns the payload, resource, and an empty error list.
2. Business validation failure returns **book: null** and appropriate **userErrors**.
3. Errors include accurate field paths, including for nested inputs.
4. **clientMutationId** is echoed accurately when sent by the client.
5. Omitting **clientMutationId** still returns a valid payload.
6. Invalid input types or missing non-null fields are rejected by GraphQL before the resolver runs.
7. System exceptions become top-level GraphQL errors according to policy.
8. No data is persisted when validation fails.
9. Database constraints and race conditions do not produce fake success payloads.
10. Authorization prevents unauthorized users from performing the operation.

Beyond the response, check database state after failed mutations to confirm there are no unintended side effects.

## 15. Common Payload Design Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Making every payload field nullable | Clients struggle to tell which states are valid | Choose nullability per contract |
| Making the resource field non-null when mutation can fail | Cannot return business errors in the payload | Allow the resource field to be nullable |
| Nullable **userErrors** | Clients must add extra null checks | Use a non-null list and return **[]** on success |
| Catching all exceptions as user errors | Hides system failures | Convert only predictable business errors into payload errors |
| Using message text as an error code | Clients depend on changeable prose | Provide stable error codes |
| One giant payload shared across all mutations | Confusing contract with irrelevant fields | Create use-case-specific payloads |
| Confusing `clientMutationId` with idempotency | Retried requests can still duplicate side effects | Use a server-tracked idempotency key |
| Returning internal entities directly | May expose fields not meant for clients | Use public output types/DTOs |
| Returning payload before clear transaction commit | May report success even when data is not committed | Define explicit transaction boundaries |
| Testing only success responses | Misses business errors and rollbacks | Test success, failure, and side effects |

## 16. Mutation Payload Design Workflow

When designing a payload-returning mutation:

1. Identify the data clients need after the operation completes.
2. Create a payload type named after the use case.
3. Choose resource fields and nullability fitting both success and domain failure.
4. Design **userErrors** with stable codes, safe messages, and field paths if needed.
5. Separate business errors from GraphQL validation/execution errors.
6. Declare a dedicated input type for the operation.
7. Bind input and return the payload from a handler using **@MutationMapping**.
8. Run validation before side effects and place transactions in the service.
9. Design correlation or idempotency separately when retries are needed.
10. Review authorization, sensitive data exposure, and schema evolution.
11. Write `GraphQlTester` tests for success, business errors, GraphQL errors, and data state.

Payload objects enable mutations to return a clear outcome contract combining resources, business errors, and related metadata. In Spring for GraphQL, SDL defines the payload type, **@MutationMapping** binds the field to a handler method, **@Argument** binds the input, and the service determines the business outcome. Distinguishing **userErrors** from top-level GraphQL errors, choosing proper nullability, and controlling transactions help clients handle mutations consistently while the server preserves clean boundaries between business rules and system errors.
