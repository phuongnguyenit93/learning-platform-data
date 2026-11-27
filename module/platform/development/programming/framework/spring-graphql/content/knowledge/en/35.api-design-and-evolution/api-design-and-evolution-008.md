# Separate Input Types and Output Types

When designing a GraphQL schema, the data clients send and the data the server returns typically have different shapes. A client may send `authorId` to create a `Book`, while the response returns the full `Author` object with `id`, `name`, and other fields. A client may update `title` and `description`, yet must not be allowed to set `createdAt`, `owner`, `permissions`, or server-managed fields.

GraphQL reflects this distinction directly in its type system: input types describe the values clients are allowed to provide; output types describe the values the server can return. Certain named types such as scalars and enums can be used on both sides, whereas Input Objects and Objects/Interfaces/Unions serve distinct roles and are not interchangeable.

Separating input types from output types lets the schema express business intent accurately, restrict which data clients can mutate, support validation, and allow the API to evolve independently in both directions.

## Input type and output type rules

GraphQL classifies types by where they can be used:

| Type category | Can be used as input | Can be used as output |
| --- | --- | --- |
| Scalar (`String`, `Int`, `ID`, custom scalars...) | Yes | Yes |
| Enum | Yes | Yes |
| Input Object (`input`) | Yes | No |
| Object (`type`) | No | Yes |
| Interface | No | Yes |
| Union | No | Yes |
| List and Non-Null | Follows wrapped type | Follows wrapped type |

A field on an Object or Interface returns an output type. That field's arguments must use input types. An Input Object can contain only scalars, enums, other input objects, or list/non-null wrappers around those types.

An Input Object cannot declare arguments on its fields. The SDL snippets in this article are standalone per-use-case examples; when assembling a complete schema, declare each type and scalar once.

Valid example:

~~~graphql
type Query {
  book(id: ID!): Book
  books(filter: BookFilterInput): [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}

input BookFilterInput {
  keyword: String
  authorId: ID
}
~~~

Types like `DateTime` and `BookStatus` are declared elsewhere in a complete schema; this example focuses on the `Book` output structure.

In the example:

- `Book` and `Author` are output object types.
- `BookFilterInput` is an input object type.
- `ID` and `String` are scalars, usable in both input and output.
- `books` accepts `BookFilterInput` yet returns a list of `Book`.

## Why not share a single type?

Consider the `Book` output type:

~~~graphql
scalar DateTime

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Author {
  id: ID!
  name: String!
}

type Book {
  id: ID!
  title: String!
  description: String
  author: Author!
  status: BookStatus!
  createdAt: DateTime!
  updatedAt: DateTime!
  averageRating: Float
  canEdit: Boolean!
}
~~~

This is a read model. Some fields are relationships to other objects (`author`), some are computed by the server (`averageRating`, `canEdit`), and some are managed by the server (`createdAt`, `updatedAt`).

GraphQL forbids using `Book` directly as an input. Even so, if you design an overly broad input that copies server-managed fields, clients can submit values they should never be allowed to write:

~~~graphql
scalar DateTime

type Book {
  id: ID!
  title: String!
}

input UnsafeBookInput {
  id: ID
  title: String
  createdAt: DateTime
  canEdit: Boolean
}

type Mutation {
  updateBook(input: UnsafeBookInput!): Book!
}
~~~

Client request:

~~~graphql
mutation {
  updateBook(input: {
    id: "book-42"
    title: "New title"
    createdAt: "2000-01-01T00:00:00Z"
    canEdit: true
  }) { id title }
}
~~~

A properly designed schema rejects fields not declared on the input object. Do not widen an input to accept every output field and rely on the service to ignore dangerous fields.

Separating types provides several benefits:

1. **Restrict write permissions.** Inputs only contain business fields that clients are allowed to modify.
2. **Express intent.** Create, update, filter, and sort are distinct operations and should have distinct inputs.
3. **Prevent mass assignment.** Avoid binding an entire request directly onto an entity and accidentally overwriting internal fields.
4. **Keep responses rich.** Outputs can include relationships, computed fields, statuses, and metadata that do not belong in inputs.
5. **Independent evolution.** You can add read fields to outputs without altering the write contract; you can extend inputs without exposing additional returned data.
6. **Clear validation.** Rules for creation typically differ from rules for updating or searching.

Java DTOs and GraphQL types do not need a one-to-one correspondence either. You can use a Java command as an intermediary object for services while SDL defines the public contract separately.

The Java snippets below are standalone per-section examples; `BookService`, `BookView`, and related domain types are assumed to exist in the application.

## Common invalid schemas

Do not use an Object type as an argument:

~~~graphql
type Author {
  id: ID!
  name: String!
}

type Mutation {
  # Invalid: Author is an output object type.
  createBook(author: Author!): Book!
}
~~~

Do not use an Input Object as a return type:

~~~graphql
input BookInput {
  title: String!
}

type Mutation {
  # Invalid: BookInput can only be used in input positions.
  createBook(input: BookInput!): BookInput!
}
~~~

Do not place an output object or interface inside an input object:

~~~graphql
input CreateBookInput {
  title: String!
  # Invalid: Author is an output object type.
  author: Author
}
~~~

Use an `ID` or a dedicated reference input object instead:

~~~graphql
input AuthorReferenceInput {
  id: ID!
}

input CreateBookInput {
  title: String!
  author: AuthorReferenceInput!
}
~~~

Or more simply:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

Choose the representation that fits the business domain. If you only need to select an existing Author, `authorId` is usually clear enough. If the reference carries extra rules such as an identifier source or tenant, a dedicated input object may express it better.

## Designing inputs per operation

Do not create one generic `BookInput` and reuse it for create, update, filter, and sort. Each operation has different requirements:

| Input type | Purpose | Example fields |
| --- | --- | --- |
| CreateBookInput | Create a new Book | title!, authorId!, tags |
| UpdateBookInput | Partially update a Book | title, description, status |
| BookFilterInput | Filter a list of Books | keyword, statuses, authorIds |
| BookSortInput | Choose sort order | field, direction |
| BookPageInput | Control pagination | first, after |

### Create input

Creation typically requires the minimum data needed to construct a valid entity:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  description: String
  tags: [String!]! = []
}
~~~

`title` and `authorId` are required. `description` can be omitted or sent as null. `tags` has a default value of an empty list, so clients do not have to supply it; if provided, the list cannot be null and each element cannot be null.

Do not put `id`, `createdAt`, `updatedAt`, `ownerId`, `averageRating`, or `canEdit` into the input if the server is responsible for generating or determining those values.

### Update input

Updates typically allow modifying a subset of fields:

~~~graphql
input UpdateBookInput {
  title: String
  description: String
  status: BookStatus
}

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}
~~~

Java can use an enum of the same name to bind values:

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
~~~

Nullable fields without defaults can be omitted. If a client sends a field, the server processes it according to the update policy. Do not add default values to update fields if the intended meaning is "keep existing value when omitted."

Mutations can accept the ID as a separate argument and the input for the changes:

~~~graphql
type Mutation {
  updateBook(id: ID!, input: UpdateBookInput!): UpdateBookPayload!
}
~~~

Placing `id` separately separates resource identity from the payload of changes. Another API might put ID inside the input object if that is a consistent convention across the whole schema.

### Filter input

Filters express search criteria, not a partial `Book`:

~~~graphql
scalar DateTime

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input BookFilterInput {
  keyword: String
  statuses: [BookStatus!]
  authorIds: [ID!]
  createdFrom: DateTime
  createdTo: DateTime
}
~~~

Do not accept a full `Book` object just for filtering. Filters should describe search conditions and can include multiple options and explicit operators matching business needs.

### Sort and pagination inputs

Use enums to constrain sort fields and sort directions:

~~~graphql
enum BookSortField {
  TITLE
  CREATED_AT
  UPDATED_AT
}

enum SortDirection {
  ASC
  DESC
}

input BookSortInput {
  field: BookSortField! = CREATED_AT
  direction: SortDirection! = DESC
}

input BookPageInput {
  first: Int! = 20
  after: String
}
~~~

Enums ensure clients only choose fields published by the schema. Never accept raw SQL strings, arbitrary column names, or client-supplied sort expressions concatenated directly into database queries.

Query schema:

~~~graphql
type Query {
  books(
    filter: BookFilterInput
    sort: BookSortInput
    page: BookPageInput
  ): BookConnection!
}

type BookConnection {
  edges: [BookEdge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}

type BookEdge {
  cursor: String!
  node: Book!
}

type PageInfo {
  hasNextPage: Boolean!
  endCursor: String
}
~~~

`BookFilterInput`, `BookSortInput`, and `BookPageInput` are input types. `BookConnection`, `BookEdge`, `PageInfo`, and `Book` are output types. Output connections can contain nested objects and pagination metadata for read-only client consumption.

The server must still enforce business bounds—for example, `first` between 1 and 100. `Int!` only guarantees a non-null integer value; it does not automatically ensure a positive number or an allowed range.

## Output types for mutation results

Mutations should return an output type representing the business outcome rather than returning the input object:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
  updateBook(id: ID!, input: UpdateBookInput!): UpdateBookPayload!
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type UpdateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type UserError {
  field: [String!]!
  code: String!
  message: String!
}
~~~

A payload is an output object. It can return the persisted `Book`, structured business errors, or extra metadata. `book` is nullable because a mutation can fail due to invalid input, in which case no `Book` is created/updated. `userErrors` always returns a list, including an empty list on success.

Example success response:

~~~json
{
  "data": {
    "createBook": {
      "book": {
        "id": "book-42",
        "title": "Spring GraphQL",
        "status": "DRAFT",
        "createdAt": "2026-11-20T10:00:00Z"
      },
      "userErrors": []
    }
  }
}
~~~

Example business error represented as data:

~~~json
{
  "data": {
    "createBook": {
      "book": null,
      "userErrors": [
        {
          "field": ["authorId"],
          "code": "AUTHOR_NOT_FOUND",
          "message": "Author not found."
        }
      ]
    }
  }
}
~~~

This is a design choice. For system errors or failures that cannot be handled as normal business outcomes, the application can still return top-level GraphQL errors. Keep error representation consistent across mutations.

## Nullability, optionality, and default values

GraphQL uses an exclamation mark (`!`) to declare Non-Null. In inputs, Non-Null not only forbids null values, it also makes the field/argument required unless a default value exists.

In outputs, Non-Null promises the field never returns null. If a resolver returns null or errors at a Non-Null position, the error propagates up to the nearest nullable parent.

| Declaration | Meaning as input | Meaning as output |
| --- | --- | --- |
| String | Can be omitted or passed as null | Can return null |
| String! | Must have a value, cannot be null | When selected, cannot return null |
| [ID!] | Can be omitted or passed as null; if list is present, items are non-null | List can be null; items are non-null |
| [ID]! | List is required non-null; items can be null | List is non-null; items can be null |
| [ID!]! | List is required non-null and items are non-null | List and all items are non-null |

Example:

~~~graphql
type Book {
  tags: [String!]!
  relatedBooks: [Book!]
}

input CreateBookInput {
  title: String!
  tags: [String!]! = []
}
~~~

`tags: [String!]!` does not mean the list must contain at least one element. An empty list is still valid. If business rules require at least one tag, additional validation is needed.

Default values also affect requiredness. `tags: [String!]! = []` can be omitted because the server uses an empty list; if the client sends `tags: null`, the request is still invalid.

## Distinguishing omitted vs. explicit null in updates

Input objects have an important distinction:

- Omitted field: no corresponding entry exists in the coerced input.
- Field sent with `null`: the entry exists and has a `null` value.

With `UpdateBookInput`, the following two requests mean different things:

~~~graphql
mutation {
  updateBook(
    id: "book-42"
    input: { title: "New title" }
  ) {
    book { id title description }
  }
}
~~~

`description` is omitted, so the existing description is preserved.

~~~graphql
mutation {
  updateBook(
    id: "book-42"
    input: {
      title: "New title"
      description: null
    }
  ) {
    book { id title description }
  }
}
~~~

`description` is explicitly passed as null, which can be interpreted as clearing the description.

If you only bind to a regular nullable Java field, both cases become null, preventing the service from knowing whether the client intentionally cleared the field or simply omitted it.

### Using ArgumentValue in Spring for GraphQL

Spring for GraphQL provides `ArgumentValue<T>` to retain whether a field was omitted or sent (including sent as null). It can be used inside input objects bound by `@Argument`:

~~~java
import org.springframework.graphql.data.ArgumentValue;

public record UpdateBookInput(
        ArgumentValue<String> title,
        ArgumentValue<String> description,
        ArgumentValue<BookStatus> status) {
}
~~~

Resolver:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

record UserError(
        List<String> field,
        String code,
        String message) {
}

record UpdateBookPayload(
        BookView book,
        List<UserError> userErrors) {

    public static UpdateBookPayload invalid(String field, String code) {
        return new UpdateBookPayload(
                null,
                List.of(new UserError(
                        List.of(field),
                        code,
                        "Invalid input value.")));
    }
}

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public UpdateBookPayload updateBook(
            @Argument("id") String id,
            @Argument("input") UpdateBookInput input) {

        if (!input.title().isOmitted()) {
            if (input.title().value() == null) {
                return UpdateBookPayload.invalid(
                        "title", "TITLE_REQUIRED");
            }
        }

        return bookService.update(id, input);
    }
}
~~~

In the service, each state can be handled explicitly:

~~~java
if (!input.description().isOmitted()) {
    // if value() is null, clear the description;
    // if present, replace the description.
    book.changeDescription(input.description().value());
}

if (!input.status().isOmitted()) {
    if (input.status().value() == null) {
        throw new InvalidBookStatusException();
    }
    book.changeStatus(input.status().value());
}
~~~

`ArgumentValue.isOmitted()` returns true when the client did not send the field. If the client sent the field with null, `isOmitted()` returns false and `value()` returns null. Spring also supports `ArgumentValue` inside nested fields of bound objects.

If you only need to know whether a method-level argument was omitted, you can use `ArgumentValue<T>` directly instead of `@Argument`. Do not use `Optional<T>` to distinguish omitted from explicit null because `Optional` cannot preserve both states.

## Creating Java input DTOs and binding in Spring

An input DTO is a Java type dedicated to client-supplied data. It can differ from both JPA entities and output DTOs:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.List;

public record CreateBookInput(
        @NotBlank
        @Size(max = 200)
        String title,

        @NotNull
        String authorId,

        List<@NotBlank String> tags) {
}
~~~

Controller:

~~~java
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
    public CreateBookPayload createBook(
            @Argument("input") @Valid CreateBookInput input) {

        return bookService.create(input);
    }
}
~~~

Spring for GraphQL uses `GraphQlArgumentBinder` to bind arguments into Java objects. The binder can use the primary constructor (including a record's canonical constructor), or a default constructor and setters. For complex inputs, nested objects are bound recursively.

When a Bean Validation `Validator` is present, annotated controllers support `@Valid` and `@Validated`. Constraints such as `@NotBlank` and `@Size` are checked before invoking the method. The GraphQL schema remains the first layer validating types, required fields, and nullability; Bean Validation adds detailed application-level rules.

Do not bind requests directly onto JPA entities. Translate input DTOs into commands or domain service calls so only permitted fields participate in write operations.

## Input validation has multiple layers

Not all rules belong in the same layer:

| Layer | Example | Mechanism |
| --- | --- | --- |
| GraphQL schema validation | Missing `title: String!`, passing an Object into input, nonexistent field | GraphQL parser, validator, and input coercion |
| Binding | Value cannot be converted to the Java target type | `GraphQlArgumentBinder`, `BindException` |
| Bean Validation | Blank title, overly long string, list exceeds limit | `@Valid`, `@Validated`, Jakarta Validation |
| Domain/business validation | Author does not belong to tenant, disallowed state transition | Domain service or application service |
| Authorization | User lacks permission to edit Book | Spring Security and permission checks in service |

For example, `authorId: ID!` only ensures the client supplied an ID. It does not ensure that Author exists, belongs to the right tenant, or that the user is allowed to link that Author to a Book.

Checks depending on data and business state must happen in the service/domain layer. Do not rely on GraphQL input types as a substitute for authorization or business validation.

## Filter inputs are not output objects

A filter can have many criteria without mirroring the full structure of the searched object:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  title: String!
}

input BookFilterInput {
  keyword: String
  statuses: [BookStatus!]
  authorIds: [ID!]
  hasDescription: Boolean
}

type Query {
  books(filter: BookFilterInput): [Book!]!
}
~~~

`BookFilterInput` only exposes supported criteria. Clients cannot pass `averageRating`, `createdAt`, or `canEdit` as filters if the schema does not declare them.

When complex operators are needed, design dedicated input objects:

~~~graphql
scalar DateTime

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input StringFilterInput {
  eq: String
  contains: String
  startsWith: String
}

input DateTimeRangeInput {
  from: DateTime
  to: DateTime
}

input AdvancedBookFilterInput {
  title: StringFilterInput
  createdAt: DateTimeRangeInput
  status: BookStatus
}
~~~

Do not create a generic input object capable of expressing arbitrary database predicates if the API only needs a few filters. The broader the filter schema, the harder validation, query optimization, and execution cost protection become.

## Enums and custom scalars work on both sides

Scalars and enums can be used in both inputs and outputs:

~~~graphql
scalar DateTime
scalar UUID

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  status: BookStatus!
  createdAt: DateTime!
}

input BookFilterInput {
  id: UUID
  status: BookStatus
  createdAfter: DateTime
}
~~~

Scalars define input parsing and output serialization rules. For custom scalars, clearly specify format, value domain, and coercion rules. You can use `@specifiedBy` to link to the scalar's specification:

~~~graphql
scalar UUID @specifiedBy(url: "https://www.rfc-editor.org/rfc/rfc9562")
~~~

Do not create a custom scalar just to bypass the type system. If data is structured with multiple fields, use an Input Object for inputs or an Object type for outputs.

## OneOf Input Objects for mutually exclusive choices

Some mutations or queries allow looking up an object by exactly one of several identifiers, such as ID or ISBN:

~~~graphql
input BookLookupInput @oneOf {
  id: ID
  isbn: String
}

type Query {
  bookBy(input: BookLookupInput!): Book
}
~~~

With a OneOf Input Object, the client must supply exactly one field and that field's value must be non-null. Its inner fields must be nullable with no default values; the `@oneOf` rule itself enforces choosing exactly one branch.

`@oneOf` is defined in the current GraphQL specification, but verify that your application's GraphQL Java version and tooling support it before using it. If the implementation does not support it yet, use explicit arguments or an input with a discriminator and service-side validation.

Example of a broadly compatible alternative:

~~~graphql
enum BookLookupKind {
  ID
  ISBN
}

input BookLookupInput {
  kind: BookLookupKind!
  id: ID
  isbn: String
}
~~~

The service must verify that only the field matching `kind` is supplied. If the flexibility of a unified input is unnecessary, two separate queries `book(id: ID!)` and `bookByIsbn(isbn: String!)` may be simpler.

## Evolving input and output types

Inputs and outputs evolve along different axes. Keeping them separate therefore helps schema changes avoid unintended side effects.

### Output changes

GraphQL clients only receive fields requested in their selection set. Adding a new output field is usually a backward-compatible change:

~~~graphql
type Book {
  id: ID!
  title: String!
  subtitle: String
}
~~~

Older clients do not request `subtitle`, so legacy responses keep the same shape as before. Newer clients can select the additional field.

To replace an old field, add the new field and mark the old field deprecated:

~~~graphql
type Book {
  title: String!
  name: String @deprecated(reason: "Use title instead.")
}
~~~

Do not remove a field while clients still use it. Track usage, announce migration, and remove only after an appropriate compatibility plan.

### Input changes

Adding a nullable input field generally lets older clients keep sending requests:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  subtitle: String
}
~~~

However, adding a Non-Null field without a default makes existing requests missing that field invalid:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  publisherId: ID!
}
~~~

Before adding a required field, plan a migration strategy. You can add a nullable/defaulted field first, update clients, and only later tighten it to required once the contract and data are ready.

Input fields and enum values can also be deprecated. A Non-Null input field without a default cannot be deprecated directly; first convert it to optional or give it a default value. Then apply `@deprecated` and monitor client usage.

### Change matrix

| Change | Typical impact |
| --- | --- |
| Add nullable output field | Usually backward-compatible |
| Add Non-Null output field | Older clients are not forced to query the new field, though contract and implementation must be guaranteed |
| Remove active output field | Breaking change |
| Change nullable output field to Non-Null | May alter codegen/client contract and error propagation |
| Add nullable input field without default | Usually compatible with existing requests |
| Add Non-Null input field without default | Breaking change because existing requests omit the field |
| Remove input field clients are sending | Breaking change |
| Add output enum value | Clients using closed enums may need to update unknown-value handling |
| Add input enum value | Server accepts a new choice; older clients do not need to send it |
| Remove enum value | Can break clients sending or handling that value |

You cannot look solely at a field's name to conclude a change is safe. Evaluate input/output position, nullability, default values, and how clients generate code.

## Testing input/output contracts

Test both the schema and how Spring binds data:

| Scenario | Expected verification |
| --- | --- |
| Pass an output Object in an argument | Schema validation rejects it |
| Use an Input Object as a return type | Schema is invalid |
| Omit a Non-Null field without default | Request is rejected before calling the resolver |
| Send null for a Non-Null field | Request is rejected |
| Send an undeclared field in input | Input coercion rejects it |
| Send valid CreateBookInput | Controller receives the expected DTO |
| Send blank title | Bean Validation catches it |
| Send nonexistent authorId | Domain service returns business error |
| Update omitting description | Existing description is preserved |
| Update sending description: null | Description is cleared per policy |
| Update sending new description | Description is updated |
| Client queries new output field | Response returns the new field |
| Old client does not query new field | Response contains only the old fields |

You can use `GraphQlTester` or `HttpGraphQlTester` to send mutations/queries and verify responses. When testing input validation, verify that the resolver/service is not invoked if the request is structurally or type-invalid.

Example test for a create mutation:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                book {
                    id
                    title
                    status
                }
                userErrors {
                    code
                }
            }
        }
        """)
    .variable("input", Map.of(
            "title", "Spring GraphQL",
            "authorId", "author-10"))
    .execute()
    .path("createBook.book.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL");
~~~

This test verifies that the input contract binds and the output payload is returned. Seed a valid Author or mock the corresponding service so the test runs independently of a database.

## Common pitfalls

| Symptom | Possible cause | How to address |
| --- | --- | --- |
| Schema fails to initialize | Using an Object type in an input position | Create a dedicated Input Object |
| Mutation does not accept nested object | Input field references an output type | Use an ID or nested input type |
| Cannot return input object from resolver | Input Object used as an output return type | Create an output Object/Payload type |
| Clients can modify internal fields | Input reuses an overly broad output/entity | Expose only writable fields |
| Update always writes null to omitted fields | Nullable DTO loses omitted vs. null distinction | Use `ArgumentValue` or raw argument map |
| Update cannot clear nullable field | Input field declared Non-Null | Allow nullable if business rules support clearing |
| Create lacks required data | Input field lacks required constraint | Use Non-Null or Bean Validation depending on rules |
| `String!` still accepts empty string | Non-Null only forbids null/omission | Use `@NotBlank` or domain validation |
| Sort accepts arbitrary column names | Using free-form `String` as sort field | Use an enum whitelist |
| Filter is overly complex | Reusing output objects or overly broad generic input | Design filter inputs per use case |
| Adding new input field breaks old clients | New field is Non-Null without default | Add nullable/default first, migrate clients, tighten later |
| Mutation returns entity with unintended fields | Directly exposing persistence entity | Return an output DTO and control public fields |

## Workflow for designing inputs and outputs

When designing a GraphQL operation:

1. **Determine what data clients may send.** List only the fields needed for the use case, rather than copying the entire output object.
2. **Determine what data the server returns.** Create an output object with relationships, computed fields, and statuses needed by clients.
3. **Separate inputs by action.** Create, update, filter, sort, and pagination usually need distinct types.
4. **Choose ID vs. nested input.** Use ID when referencing an existing resource; use nested input when the operation genuinely requires nested data.
5. **Set nullability intentionally.** Distinguish required, optional, nullable, and default values.
6. **Design patch semantics.** Clearly specify whether omitted means keep existing vs. use default, and whether explicit null means clear vs. invalid.
7. **Bind into input DTOs.** Use `@Argument`, `GraphQlArgumentBinder`, `@Valid`, and `ArgumentValue` where appropriate.
8. **Validate domain rules and authorization.** A type-valid ID does not mean the client is authorized to access that resource.
9. **Return an appropriate payload.** Use an output object/payload to express outcomes and business errors.
10. **Assess schema impact.** Adding nullable/defaulted fields is usually easier to evolve than adding required input fields.
11. **Test both directions.** Verify valid/invalid requests and responses against selection sets.

Input types and output types are two separate contracts in GraphQL. Scalars and enums work on both sides, whereas Input Objects are solely for receiving data, and Objects, Interfaces, and Unions are solely for returning data. Separating `CreateBookInput`, `UpdateBookInput`, and filter/sort inputs from output objects helps control write permissions, validation, and API evolution. For partial updates, preserve the distinction between an omitted field and a field sent as null; in Spring for GraphQL, `ArgumentValue<T>` supports this exact case. Let the schema validate structure, Bean Validation validate input values, domain services enforce business rules and authorization, and then return output DTOs/payloads tailored to clients.

## References

- [GraphQL Specification - Input and Output Types](https://spec.graphql.org/September2026/#sec-Input-and-Output-Types)
- [GraphQL Specification - Input Objects](https://spec.graphql.org/September2026/#sec-Input-Objects)
- [GraphQL Specification - Non-Null and List Types](https://spec.graphql.org/September2026/#sec-Non-Null)
- [GraphQL - Schemas and Types](https://graphql.org/learn/schema/)
- [GraphQL - Schema Design and Evolution](https://graphql.org/learn/schema-design/)
- [Spring for GraphQL - Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - ArgumentValue API](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/data/ArgumentValue.html)
