# Resource Update Mutations

In Spring for GraphQL, mutations are the group of operations used to modify server-side data state. A resource update operation typically receives the target object's identifier along with the data to be changed, checks permissions and business rules, persists changes inside a transaction, and returns the updated resource.

Spring for GraphQL maps fields belonging to the `Mutation` root type to Java methods using **@MutationMapping**. Designing an update mutation requires clarifying whether the operation is a full replacement or a partial update, how omitted or null fields are handled, how errors are reported, and how data consistency is preserved when multiple requests update concurrently.

## 1. What is a Resource Update Mutation?

GraphQL distinguishes three root operation types:

- **Query** is used for reading data.
- **Mutation** is used for modifying data state.
- **Subscription** is used for receiving events or results emitted over time.

A resource update mutation typically follows these steps:

1. Receive the ID or identifier key of the resource.
2. Receive input data describing the changes.
3. Authenticate the user and check permissions on the resource.
4. Load the current resource from the repository.
5. Validate input data and business rules.
6. Apply changes and persist within a transaction.
7. Return the updated resource or a GraphQL error per the API contract.

For example, a `Book` resource has `id`, `title`, and `description` attributes. A client wants to change a book's title:

~~~graphql
type Book {
    id: ID!
    title: String!
    description: String
}

type Mutation {
    updateBook(id: ID!, title: String!): Book!
}
~~~

Operation:

~~~graphql
mutation RenameBook($id: ID!, $title: String!) {
    updateBook(id: $id, title: $title) {
        id
        title
        description
    }
}
~~~

Variables:

~~~json
{
    "id": "book-42",
    "title": "Spring for GraphQL"
}
~~~

A mutation does not merely return a success notice. The client can immediately select fields of the updated resource, keeping the UI synchronized with server state.

## 2. Designing the Schema for Update Mutations

When a resource has multiple attributes, group the update data into an input object instead of creating separate arguments for every attribute.

The SDL snippets in this lesson focus on `Mutation` declarations; a complete application schema still requires a query root, typically `type Query`.

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

input UpdateBookInput {
    title: String
    description: String
    status: BookStatus
}

type Book {
    id: ID!
    title: String!
    description: String
    status: BookStatus!
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

Here:

- `id` identifies the resource to update.
- `input` groups the modifiable attributes.
- `title`, `description`, and `status` are nullable so the client can omit fields or pass null depending on update rules.
- `updateBook` returns the updated `Book`.

Making input fields nullable does not mean the application must accept every null value. The schema allows expressing the input state; the service decides which fields may be cleared, which fields must have a value, and which fields cannot be modified.

### Why separate ID from input?

You could put `id` inside `UpdateBookInput`, but separating `id` into its own argument usually clarifies intent:

~~~graphql
type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

`id` is the identifier of the target resource, while `input` describes the changes. This separation also lets you reuse input objects across operations with similar semantics without forcing every input to contain an ID.

If the API requires a version, tenant, or an additional update condition, add it deliberately to the schema and verify it against a trustworthy source. Never treat a client-sent ID as proof of resource ownership.

## 3. Full Update vs. Partial Update

GraphQL does not intrinsically define a mutation as PUT or PATCH. The operation's semantics depend on the schema and business rules implemented by the server.

A **full update** requires the client to supply all required attributes for the new version of the resource. Mandatory fields can be declared non-null:

~~~graphql
input ReplaceBookInput {
    title: String!
    description: String
    status: BookStatus!
}

type Mutation {
    replaceBook(id: ID!, input: ReplaceBookInput!): Book!
}
~~~

With this style, the client must send `title` and `status`. The server can replace the entire portion of data represented by the input.

A **partial update** changes only the fields sent by the client. Omitted fields retain their current values; fields explicitly sent as null may mean clearing the value if business rules permit.

~~~graphql
input UpdateBookInput {
    title: String
    description: String
    status: BookStatus
}
~~~

For example, changing only the title:

~~~json
{
    "title": "New title"
}
~~~

Sending:

~~~json
{
    "description": null
}
~~~

can be interpreted as clearing `description`. This convention must be documented and tested. Never leave clients guessing what `null` means.

For partial-update inputs, avoid setting default values on fields where the server must know exactly whether the client supplied them. Defaults can turn an omitted field into a default value during GraphQL input processing, preventing the application from distinguishing client intent.

## 4. Distinguishing Omitted Fields from Null Fields

This is the most critical detail when implementing partial updates.

Consider this input:

~~~graphql
input UpdateBookInput {
    title: String
    description: String
}
~~~

The following two requests carry different meanings:

Omitting `description`:

~~~json
{
    "title": "New title"
}
~~~

Sending `description` as `null`:

~~~json
{
    "title": "New title",
    "description": null
}
~~~

Common convention:

| Input state | Meaning in partial update |
| --- | --- |
| Field omitted | Keep the current value. |
| Field has a value | Update to the new value. |
| Field sent as `null` | Clear the value if the field allows null; otherwise reject. |

If you bind the input into a Java record with plain `String` properties, both an omitted field and a field sent as `null` become Java `null`. The service then cannot tell whether the client wants to keep or clear the data.

Spring for GraphQL provides **ArgumentValue<T>** to preserve this distinction. This wrapper indicates whether an argument or input field was omitted or explicitly provided.

~~~java
import org.springframework.graphql.data.ArgumentValue;

public record UpdateBookInput(
        ArgumentValue<String> title,
        ArgumentValue<String> description,
        ArgumentValue<BookStatus> status
) {
}
~~~

In the service or controller, check the presence state before reading `value()`:

~~~java
if (!input.title().isOmitted()) {
    String title = input.title().value();

    if (title == null || title.isBlank()) {
        throw new InvalidBookInputException("Title must not be blank");
    }

    book.rename(title);
}

if (!input.description().isOmitted()) {
    book.changeDescription(input.description().value());
}
~~~

In this example:

- If `title` is omitted, it does not change.
- If `title` has a valid string, the title is updated.
- If `title` is explicitly `null`, it is rejected by business rules.
- If `description` is omitted, it remains unchanged.
- If `description` is explicitly `null`, `description` is cleared.

`ArgumentValue` is also useful for fields inside nested input objects. Test binding with your project's Spring for GraphQL version to ensure the DTO accurately reflects input structure.

## 5. Mapping Mutations with @MutationMapping

Spring for GraphQL uses `@MutationMapping` to connect a Java method to a matching field on the `Mutation` root type.

Schema:

~~~graphql
type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

Controller:

~~~java
package com.example.catalog.graphql;

import com.example.catalog.book.Book;
import com.example.catalog.book.BookService;
import com.example.catalog.book.UpdateBookInput;
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
    public Book updateBook(
            @Argument("id") String id,
            @Argument("input") UpdateBookInput input) {
        return bookService.update(id, input);
    }
}
~~~

Key points:

- `@Controller` registers the class with Spring.
- `@MutationMapping` maps the `updateBook` method to `Mutation.updateBook`.
- `@Argument("id")` extracts the resource ID.
- `@Argument("input")` binds the input object into the Java DTO.
- The returned value is completed by the GraphQL engine according to the client's selection set.

If the method name differs from the SDL field name, specify it explicitly with `name`:

~~~java
@MutationMapping(name = "updateBook")
public Book applyBookChanges(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {
    return bookService.update(id, input);
}
~~~

`@MutationMapping` is a specialized shorthand for fields on the root `Mutation` type. If the schema uses a custom root mutation type name, use `@SchemaMapping` with the corresponding `typeName`.

## 6. Implementing Updates in Services and Transactions

Controllers should accept input and pass it to services. Services load the current resource, validate business rules, apply changes, and persist them.

Service example:

~~~java
package com.example.catalog.book;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    public Book update(String id, UpdateBookInput input) {
        BookEntity entity = bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));

        if (!input.title().isOmitted()) {
            String title = input.title().value();

            if (title == null || title.isBlank()) {
                throw new InvalidBookInputException(
                        "Title must not be blank");
            }

            entity.setTitle(title);
        }

        if (!input.description().isOmitted()) {
            entity.setDescription(input.description().value());
        }

        if (!input.status().isOmitted()) {
            BookStatus status = input.status().value();

            if (status == null) {
                throw new InvalidBookInputException(
                        "Status must not be null");
            }

            entity.setStatus(status);
        }

        BookEntity saved = bookRepository.save(entity);
        return BookMapper.toModel(saved);
    }
}
~~~

This is an illustrative example; `BookEntity`, repository, mapper, and exceptions should be defined according to your application's model.

Placing `@Transactional` on the service ensures loading, validating, and saving the resource run within the same transaction. If a step fails and an exception rolls back the transaction per configuration, partial changes will not be committed.

Key notes:

- Do not open a transaction just to wrap GraphQL document parsing; transactions should enclose the business operation requiring atomicity.
- Choose an appropriate rollback policy if the application uses checked exceptions.
- Do not hold transactions open while waiting on slow remote calls unless necessary.
- Do not return JPA entities directly if doing so exposes internal relationships or data; map them to DTOs/output models.
- When updating multiple related resources, define clear transaction boundaries and update ordering.

## 7. Input Validation and Business Rules

GraphQL validates data types and input structure before calling the resolver. However, the schema cannot replace business validation.

For example, SDL may declare:

~~~graphql
input UpdateBookInput {
    title: String
    description: String
}
~~~

GraphQL verifies that `title` is a `String` or `null`, but it does not know whether `title` is allowed to be blank or exceed 200 characters.

The service must validate:

~~~java
private void validateTitle(String title) {
    if (title == null || title.isBlank()) {
        throw new InvalidBookInputException("Title must not be blank");
    }

    if (title.length() > 200) {
        throw new InvalidBookInputException("Title is too long");
    }
}
~~~

Common rules to check when updating:

- Does the resource exist?
- Does the user have permission to update the resource?
- Did at least one field change?
- Is a field sent as null allowed to be cleared?
- Are strings blank or exceeding length limits?
- Is the new status transition valid from the current status?
- Is the resource locked or already finalized?
- Do referenced values like `authorId` exist and are they permitted for use?

You can combine Jakarta Bean Validation with constraints like `@NotBlank`, `@Size`, `@Min`, and `@Max`. With partial updates, note that constraints apply only to fields actually provided; validation on regular DTOs may not express omitted/null semantics adequately. Final rules still need to be enforced in the service.

## 8. Handling Missing Resources and Update Errors

When an ID does not exist, the service can throw a business exception:

~~~java
BookEntity entity = bookRepository.findById(id)
        .orElseThrow(() -> new BookNotFoundException(id));
~~~

Spring for GraphQL allows translating exceptions into GraphQL errors using `@GraphQlExceptionHandler`.

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Book not found")
                .errorType(ErrorType.NOT_FOUND)
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleInvalidInput(
            InvalidBookInputException exception) {
        return GraphqlErrorBuilder.newError()
                .message(exception.getMessage())
                .errorType(ErrorType.BAD_REQUEST)
                .build();
    }
}
~~~

Clients receive a response containing `errors` when an update fails. If the mutation field is declared non-null, execution errors can propagate null up to the root `data`. Therefore, design nullability and error contracts consistently.

Never return stack traces, SQL, table names, or internal details in error messages. Log full details on the server; responses should contain only what clients need to handle the situation.

Distinguishing scenarios:

| Scenario | Common handling |
| --- | --- |
| ID does not exist | `NOT_FOUND` or nullable result per API contract. |
| Input violates rules | `BAD_REQUEST` or validation error with a clear code. |
| Insufficient permission to update | `FORBIDDEN` or `UNAUTHORIZED` depending on context. |
| Version conflict | `CONFLICT` or corresponding business error code. |
| Database or service outage | `INTERNAL_ERROR` with a safe message. |

Do not convert every exception into `BAD_REQUEST` or `NOT_FOUND`. Accurate categorization helps clients decide whether to fix input, re-authenticate, request access, or retry later.

## 9. Securing Resource Update Mutations

Mutations can alter critical data, so authorization must be enforced on the server. Never trust an `id`, `ownerId`, or `tenantId` sent by the client as proof of ownership.

You can use Spring Security method security:

~~~java
@MutationMapping
@PreAuthorize("hasAuthority('BOOK_UPDATE')")
public Book updateBook(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {
    return bookService.updateForCurrentUser(id, input);
}
~~~

In addition to the general `BOOK_UPDATE` authority, the service must verify whether the current user is allowed to edit that specific book. For example, a user may only edit books belonging to their tenant or managed group.

Key principles:

- Retrieve user identity from the server-side security context.
- Verify permissions on the resource after loading it.
- Allow modifying only fields permitted by business rules.
- Never bind all entity fields directly from client input.
- Never let clients set roles, owners, or internal states without authorization.
- Never let error messages leak sensitive data.

In particular, input objects should not mirror the entire persistence entity. Creating an `UpdateBookInput` with only updatable fields reduces mass-assignment risks.

## 10. Handling Concurrent Updates and Optimistic Locking

Two clients might read the same resource and send update mutations nearly simultaneously. Without server control, the second write can silently overwrite the first write's changes.

One approach is optimistic locking. With JPA, an entity can declare a version field:

~~~java
@Entity
public class BookEntity {

    @Id
    private String id;

    @Version
    private Integer version;

    private String title;
}
~~~

The schema can require clients to send the version they read:

~~~graphql
input UpdateBookInput {
    title: String
    expectedVersion: Int!
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

The mutation DTO needs a matching `expectedVersion` property corresponding to the input schema. The service compares the client's version against the current version before applying changes:

~~~java
if (!Objects.equals(entity.getVersion(), input.expectedVersion())) {
    throw new BookVersionConflictException(id);
}
~~~

This comparison catches clients updating against stale data. JPA's `@Version` annotation is still essential to handle races that occur after the check but before writing to the database. If the resource was already updated by another request, saving fails with an optimistic locking exception.

The application should translate that conflict into a meaningful GraphQL error, such as code `RESOURCE_VERSION_CONFLICT`. The client can reload the resource and decide how to apply its changes on top of the latest version.

Do not rely solely on reading and comparing the version in Java if reads and writes are not protected by a proper concurrency mechanism; two requests can still pass the comparison concurrently. Use database optimistic locking or an equivalent synchronization mechanism to guarantee correctness.

Top-level fields in a single mutation operation are executed serially by GraphQL within that operation. That does not prevent two independent HTTP requests from updating the same resource concurrently. Transactions and concurrency control are still required.

## 11. Mutation Responses and What Clients Receive

A mutation typically returns the updated resource so clients can refresh caches or the UI.

~~~graphql
mutation UpdateBook($id: ID!, $input: UpdateBookInput!) {
    updateBook(id: $id, input: $input) {
        id
        title
        description
        status
    }
}
~~~

Clients receive only selected fields. If the response needs extra metadata such as update timestamp or the new version, you can extend the output type or return a dedicated payload:

~~~graphql
type UpdateBookPayload {
    book: Book!
    updatedAt: String!
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): UpdateBookPayload!
}
~~~

Payloads are useful when mutations need to return extra details beyond the resource, such as version, warnings, or secondary outcomes. There is no need to create a separate payload if returning a single object suffices.

Mutation responses do not automatically update client-side caches. Clients must use the returned data to update their cache or issue follow-up queries according to their framework's strategy.

## 12. Testing Update Mutations with GraphQlTester

Spring for GraphQL provides `GraphQlTester` to test operations and responses.

Example test for updating a title:

~~~java
@Test
void updatesBookTitle() {
    graphQlTester.document("""
            mutation UpdateBook($id: ID!, $input: UpdateBookInput!) {
                updateBook(id: $id, input: $input) {
                    id
                    title
                }
            }
            """)
        .variable("id", "book-42")
        .variable("input", Map.of("title", "New title"))
        .execute()
        .path("updateBook.title")
        .entity(String.class)
        .isEqualTo("New title");
}
~~~

Beyond the success case, test scenarios such as:

- Non-existent ID.
- Input with no fields sent.
- Omitted fields preserve existing data.
- Nullable fields sent as `null` clear values per convention.
- Non-nullable fields sent as `null` are rejected.
- Blank or overly long titles.
- Invalid enums or state transitions.
- Users lacking permission to update the resource.
- Two concurrent requests updating the same version trigger a conflict properly.
- Persistence errors do not leave partial updates saved.

### Testing omitted and null separately

Case where `description` is omitted:

~~~java
Map<String, Object> input = new HashMap<>();
input.put("title", "New title");
~~~

Case where `description` is explicitly `null`:

~~~java
Map<String, Object> input = new HashMap<>();
input.put("description", null);
~~~

These two maps have different structures. Use them in separate tests to verify that `ArgumentValue` distinguishes omitted from explicit null, and that the service preserves or clears data as specified.

Test slices can use `@GraphQlTest` with mock services or test beans. For integration testing, use `@SpringBootTest` with a test database to verify transactions, rollbacks, and optimistic locking.

## 13. Common Pitfalls When Implementing Update Mutations

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Mutation not found | Schema does not declare the field or method is mapped incorrectly. | Check `type Mutation` and `@MutationMapping`. |
| Input argument fails to bind | DTO names or types do not match SDL. | Cross-check `@Argument`, input object, and Java record/class. |
| Omitted field gets overwritten with null | DTO does not distinguish omitted from explicit null. | Use `ArgumentValue<T>` or a binding mechanism that tracks presence. |
| Cannot clear a nullable value | Service ignores explicit null too. | Check `isOmitted()` then treat `value() == null` as clearing. |
| Required field gets cleared | Schema allows null but service lacks validation. | Enforce business rules before saving. |
| Missing resource returns generic error | Exceptions are not categorized. | Use business exceptions and a GraphQL exception handler. |
| Update overwrites another request's changes | Missing concurrency control. | Use optimistic locking or an appropriate locking mechanism. |
| Partial changes saved when operation fails | Transaction does not cover the full update. | Place transaction on the service and configure rollback policy. |
| Client sends internal fields to modify | Input mirrors entity too broadly. | Create an input DTO with only updatable fields. |
| Mutation succeeds but UI stays stale | Client did not update cache from response. | Select returned fields and update cache or refetch resource. |

When debugging, inspect the schema first, then argument binding and omitted/null states. Next, verify validation, access permissions, transactions, and persistence outcomes. If bugs only appear when multiple users update concurrently, check versioning and concurrency control.

## 14. Workflow for Designing an Update Mutation

When adding a resource update operation, follow this sequence:

1. Identify the resource and which fields may be modified.
2. Choose between full replacement or partial update semantics.
3. Declare `UpdateInput` with appropriate nullability and defaults.
4. Clearly define what omitted, explicit null, and new values mean.
5. Map the field with `@MutationMapping` and bind arguments with `@Argument`.
6. Use `ArgumentValue` if you need to distinguish omitted from null.
7. Load the current resource, check permissions, and validate in the service.
8. Perform the update inside a transaction.
9. Use optimistic locking or an equivalent mechanism if concurrent updates occur.
10. Return the resource or payload per the GraphQL contract.
11. Map exceptions to safe GraphQL errors.
12. Test success, errors, omitted/null handling, authorization, and concurrency.

## 15. Key Takeaways

- Mutations are operations that modify data state; `@MutationMapping` maps Java methods to fields on the `Mutation` root type.
- Input objects group updatable fields; IDs identify the target resource.
- GraphQL does not automatically decide whether an update is a full replacement or partial update; schema and business logic must define it clearly.
- For partial updates, omitted fields usually keep existing values, whereas explicit nulls can clear values if permitted.
- `ArgumentValue<T>` helps distinguish omitted from null during input binding in Spring for GraphQL.
- Services should verify the resource, validation, authorization, and persist changes inside a transaction.
- Optimistic locking detects concurrent updates and prevents silent overwrites.
- Exceptions should be translated into GraphQL errors with appropriate codes and safe messages.
- Input DTOs should contain only fields clients are allowed to update.
- `GraphQlTester` can verify both responses and the distinction between omitted and null fields.

Resource update mutations are where the GraphQL schema directly meets business rules and data consistency. By clearly defining update semantics, preserving the difference between omitted and null fields, and enforcing authorization, transactions, and concurrency controls on the server, your Spring for GraphQL application will deliver a predictable and reliable update API.
