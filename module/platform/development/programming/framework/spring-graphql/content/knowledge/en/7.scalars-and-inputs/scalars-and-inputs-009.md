# List Input in GraphQL and Spring for GraphQL

List inputs allow clients to send multiple values in a single argument or input object. Instead of calling a mutation multiple times to create one record at a time, a client can send a list of elements; instead of filtering by a single code, a query can accept a list of IDs, statuses, or labels. GraphQL SDL describes the element type, whether the list itself can be null, and whether each element can be null.

In Spring for GraphQL, list inputs bind to Java collection types such as `List<T>`. When combined with input objects, records, or DTOs, resolvers can receive structured data and pass it to services for validation, batch processing, or persistence. Designing lists requires paying attention to null semantics, ordering, duplicate elements, and input size limits.

After this lesson, you will be able to:

- Declare list arguments and list fields in input objects using SDL.
- Correctly interpret `[T]`, `[T!]`, `[T]!`, and `[T!]!`.
- Pass lists in GraphQL documents and JSON variables.
- Understand how GraphQL coerces a single value into a single-element list.
- Bind list inputs into `List<T>` and DTOs/records in Spring for GraphQL.
- Distinguish omitted fields, empty lists, and `null` values.
- Validate, bound, and safely process list inputs in queries and mutations.

## 1. What Is a List Input?

In GraphQL, a list type is declared by wrapping the element type in square brackets. For example, `[ID]` is a list of ID values; `[String!]!` is a non-null list in which every string is also non-null.

Example API for looking up multiple books by ID:

```graphql
type Query {
    booksByIds(ids: [ID!]!): [Book!]!
}

type Book {
    id: ID!
    title: String!
}
```

The client sends multiple IDs in a single operation:

```graphql
query {
    booksByIds(ids: ["book-10", "book-20", "book-30"]) {
        id
        title
    }
}
```

The resolver receives a list of IDs, and the service can query multiple records in one call or use a batch API of the storage layer. GraphQL only guarantees that incoming data matches the declared types; batching queries, preserving order, or deduplicating IDs is up to the application.

Lists can also appear inside input objects:

```graphql
input BookSearchInput {
    ids: [ID!]
    statuses: [BookStatus!]
    tags: [String!]
}

type Query {
    searchBooks(input: BookSearchInput!): [Book!]!
}
```

This is useful when an operation accepts several related groups of criteria. Input objects gather parameters into a structured contract that is easier to extend when a feature needs additional filters.

## 2. Reading List Nullability Correctly

Lists can combine with non-null modifiers in two independent positions: the list itself and each element. The four basic forms are:

| SDL Type | List Nullable? | Element Nullable? | Meaning |
| --- | --- | --- | --- |
| `[String]` | Yes | Yes | List may be null; elements may be null |
| `[String!]` | Yes | No | List may be null; every element must be non-null |
| `[String]!` | No | Yes | List must be present; elements may be null |
| `[String!]!` | No | No | Both the list and every element must be non-null |

Example:

```graphql
input ImportBooksInput {
    optionalTitles: [String]
    titles: [String!]!
    externalCodes: [String]!
}
```

- `optionalTitles` can be omitted, sent as `null`, sent as an empty list, or sent as a list containing null elements.
- `titles` must be a non-null list and must not contain null elements. An empty list is still valid because SDL does not specify a minimum element count.
- `externalCodes` requires a list to be present, while individual elements may be null.

`!` does not mean the list must contain at least one element. If business rules require at least one ID or at most 100 elements, add validation at the application layer.

### Nested Lists

GraphQL supports multi-level nested lists:

```graphql
input MatrixInput {
    values: [[Int!]!]!
}
```

`[[Int!]!]!` requires the outer list to be non-null, every inner list to be non-null, and every integer to be non-null. Both the outer list and inner lists can still be empty. If you need to limit row count, column count, or total elements, enforce those checks in the application.

## 3. Passing Lists in GraphQL Documents

In a GraphQL document, list literals are written with square brackets and elements separated by commas:

```graphql
query SearchBooks {
    booksByIds(ids: ["book-10", "book-20"]) {
        id
        title
    }
}
```

Lists can contain scalars, enums, or input objects. Example of a mutation accepting a list of input objects:

```graphql
mutation {
    createBooks(inputs: [
        { title: "GraphQL Basics", authorId: "author-1" }
        { title: "Spring APIs", authorId: "author-2" }
    ]) {
        id
        title
    }
}
```

Each element must conform to `CreateBookInput`. If an element omits a non-null field or has a value of the wrong type, GraphQL rejects the input before executing the resolver.

Lists preserve the element order sent by the client. If an API returns results in the exact input order, the service must actively preserve that order; SQL queries using `WHERE id IN (...)` generally do not guarantee result ordering matching the input ID list.

## 4. Passing Lists via JSON Variables

In real applications, clients typically use variables to separate data from the GraphQL document:

```graphql
query FindBooks($ids: [ID!]!) {
    booksByIds(ids: $ids) {
        id
        title
    }
}
```

Variables are sent as a JSON array:

```json
{
  "ids": ["book-10", "book-20", "book-30"]
}
```

For an input object with a list field, the schema can declare:

```graphql
input ImportedBookInput {
    title: String!
    authorId: ID!
}

input ImportBooksInput {
    books: [ImportedBookInput!]!
    dryRun: Boolean = false
}

type ImportBooksResult {
    acceptedCount: Int!
    books: [Book!]!
}

type Mutation {
    importBooks(input: ImportBooksInput!): ImportBooksResult!
}
```

Corresponding operation and variables:

```graphql
mutation ImportBooks($input: ImportBooksInput!) {
    importBooks(input: $input) {
        acceptedCount
        books {
            id
            title
        }
    }
}
```

```json
{
  "input": {
    "books": [
      { "title": "GraphQL Basics", "authorId": "author-1" },
      { "title": "Spring APIs", "authorId": "author-2" }
    ],
    "dryRun": false
  }
}
```

JSON has no GraphQL-specific list type; it uses arrays. GraphQL validates variable types against declarations in the operation and schema. Prefer variables for large lists or per-request varying data so documents are easier to cache, read, and test.

## 5. Coercion: A Single Value Can Be Accepted as a Single-Element List

Under GraphQL input coercion rules, when a position expects a list but the client supplies a single non-list value, GraphQL can coerce that value into a one-element list if the single value is valid for the element type.

With the schema:

```graphql
type Query {
    booksByIds(ids: [ID!]!): [Book!]!
}
```

Both of the following forms can be coerced into a single-element list:

```graphql
query {
    booksByIds(ids: "book-10") {
        id
    }
}
```

```graphql
query FindOne($ids: [ID!]!) {
    booksByIds(ids: $ids) {
        id
    }
}
```

```json
{
  "ids": "book-10"
}
```

On the resolver side, the value binds as a one-element list. Even so, clients should always send arrays when the schema declares a list. Consistent formatting avoids confusion between single and multi-element inputs, especially if data later expands from one ID to many.

Coercion does not make an invalidly typed value valid. For example, an object cannot automatically turn into an `ID`, and a null element is still rejected if the element type is `ID!`.

## 6. Distinguishing Omitted, Null, and Empty Lists

These are three distinct states that often carry different business meanings:

| Input | Data Meaning |
| --- | --- |
| Field omitted | Client did not provide the field |
| Field has value `null` | Client provided the field and explicitly set null, if allowed by the schema |
| Field has value `[]` | Client provided an empty list |
| Field has value `["a", "b"]` | Client provided two elements in order |

Example partial-update input:

```graphql
input UpdateBookInput {
    title: String
    tags: [String!]
}
```

For `tags`, the application can define:

- Omit `tags`: keep existing tags unchanged.
- Send `tags: null`: clear or unset tags, if business rules allow.
- Send `tags: []`: remove all tags and store an empty list.
- Send `tags: ["graphql", "spring"]`: replace tags with the two new values.

GraphQL preserves the distinction between an absent field and a field with value null in the input map. However, if bound directly into a DTO with ordinary nullable Java fields, both situations can collapse to `null`. If you need to distinguish them, use `ArgumentValue<T>` on the resolver parameter or an input model that retains field presence state.

Example with a resolver argument:

```java
@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("tags") ArgumentValue<List<String>> tags) {

    if (!tags.isOmitted()) {
        return bookService.updateTags(id, tags.value());
    }
    return bookService.findById(id);
}
```

In this example, `isOmitted()` checks whether the client omitted the argument; `value()` returns the supplied value, which may be null if permitted by the schema. With nested input objects, design your DTO/binding so omitted state is preserved if business logic needs to tell them apart.

## 7. Binding List Inputs to Java List

Spring for GraphQL binds arguments into method parameters through `@Argument`. For scalar lists, you can accept `List<T>` directly:

```graphql
type Query {
    booksByIds(ids: [ID!]!): [Book!]!
}
```

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> booksByIds(@Argument("ids") List<String> ids) {
        return bookService.findAllByIds(ids);
    }
}
```

Spring for GraphQL uses `GraphQlArgumentBinder` to bind GraphQL data into Java targets. Collections such as `List`, `Set`, and compatible collection types can be bound when the element type is convertible. For GraphQL `ID`, using `String` is usually simple and clear; if you want to receive `UUID`, ensure the application's conversion service has an appropriate converter and test malformed inputs.

Do not use a raw `List` without a generic type when the resolver needs to know the element type. Declaring `List<String>`, `List<BookStatus>`, or `List<CreateBookInput>` makes the code clear and supports more accurate conversion and binding.

## 8. Binding List Objects to Records or DTOs

When each element has multiple fields, use an input object instead of a list of manually concatenated strings:

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    tags: [String!]!
}

type Mutation {
    createBooks(inputs: [CreateBookInput!]!): [Book!]!
}
```

Corresponding Java record:

```java
public record CreateBookInput(
        String title,
        String authorId,
        List<String> tags) {}
```

The resolver receives a list of records:

```java
@MutationMapping
public List<Book> createBooks(
        @Argument("inputs") List<CreateBookInput> inputs) {
    return bookService.createAll(inputs);
}
```

`GraphQlArgumentBinder` can bind input objects to record constructors or suitable DTO constructors/properties. Field names in SDL must match the bound property or constructor parameter names. If a DTO has a complex structure, test binding via GraphQL tests rather than testing only the Java constructor in isolation.

An input object can also contain a list of nested objects:

```graphql
input OrderLineInput {
    productId: ID!
    quantity: Int!
}

input CreateOrderInput {
    customerId: ID!
    lines: [OrderLineInput!]!
}
```

```java
public record OrderLineInput(String productId, Integer quantity) {}

public record CreateOrderInput(
        String customerId,
        List<OrderLineInput> lines) {}
```

Nested types let the input contract reflect the domain structure accurately and prevent resolvers from manually parsing untyped maps.

## 9. Validating List Inputs

SDL validates data types and nullability, but cannot express every business rule. For example, `[ID!]!` does not limit the number of IDs, prevent duplicate IDs, or guarantee that IDs exist.

With Bean Validation, you can place constraints on the collection and on each element:

```java
public record BulkBookRequest(
        @NotEmpty
        @Size(max = 100)
        List<@NotBlank String> ids) {}
```

When using validation in an annotated controller, mark the appropriate parameter with `@Valid` or `@Validated` and ensure the application has Bean Validation configured:

```java
@QueryMapping
public List<Book> booksByIds(
        @Argument("input") @Valid BulkBookRequest input) {
    return bookService.findAllByIds(input.ids());
}
```

Depending on your Spring for GraphQL version and validation configuration, errors can be handled through Spring for GraphQL's validation exception mechanism. Test how errors are translated into GraphQL responses and provide appropriate messages to clients.

Checks that are commonly needed:

- Non-empty list when business logic requires at least one element.
- Maximum element count to control load and request size.
- No null elements or blank strings.
- No duplicate elements if the list represents a set of unique IDs.
- Element values match expected formats, such as UUIDs or business codes.
- All IDs exist and the caller has permission to act on each record.

Syntax validation and access control are two separate concerns. GraphQL can confirm that an `ID` is valid according to the scalar, yet the server must still verify that the ID exists and belongs within the user's authorized scope.

## 10. Batch Processing Lists in Services

List inputs are often an opportunity to reduce the number of calls to repositories or external services. For example, a resolver receives multiple IDs and passes them to the repository in one call:

```java
public List<Book> findAllByIds(List<String> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }
    return bookRepository.findAllById(ids);
}
```

However, clearly define the API semantics:

- **Ordering:** repositories may return results in an arbitrary order. If input order must be preserved, index results into a map by ID and rebuild the list following `ids`.
- **Non-existent IDs:** skip missing IDs, return placeholders, or reject the entire request? The contract must state this clearly.
- **Duplicate IDs:** return each result once or repeat per input position? If duplicates must be preserved, do not blindly convert the list to a `Set`.
- **Atomicity:** does a bulk mutation succeed all-or-nothing or allow partial element failures? Transaction rules must be defined.
- **Batch limits:** databases impose bind-parameter limits; very large lists may need to be split into batches or use another loading strategy.

If you need to preserve both ordering and duplicate IDs, you can rebuild the result from a map:

```java
public List<Book> findInRequestedOrder(List<String> ids) {
    Iterable<Book> foundBooks = bookRepository.findAllById(ids);
    Map<String, Book> byId = StreamSupport.stream(foundBooks.spliterator(), false)
            .collect(Collectors.toMap(Book::id, Function.identity()));

    return ids.stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .toList();
}
```

This snippet skips non-existent IDs while preserving the order and multiplicity of existing IDs. If the API must raise an error whenever any ID is missing, check the set of found IDs before returning the result.

## 11. Bulk Mutations and Per-Element Error Handling

A mutation can accept a list input to create or update multiple objects:

```graphql
type Mutation {
    createBooks(inputs: [CreateBookInput!]!): [Book!]!
}
```

Before implementing, decide clearly:

1. If one element is invalid, does the entire batch roll back?
2. If one element fails due to a business rule, do the remaining elements continue?
3. Does the response need to return per-element errors or just a single overall error?
4. Does response ordering match input ordering?

If per-element results are required, you can design an explicit output type:

```graphql
type CreateBookResult {
    index: Int!
    book: Book
    errorCode: String
    message: String
}

type Mutation {
    createBooks(inputs: [CreateBookInput!]!): [CreateBookResult!]!
}
```

This result type lets you return processing status per position without turning one element's failure into an undifferentiated error for the entire operation. If you choose an all-or-nothing transaction, the service should execute within one transaction and let failures roll back according to the defined policy. If you choose partial success, the service must process each element in a controlled manner rather than assuming a single transaction will naturally surface per-element outcomes.

## 12. Size Limits and API Protection

A large list input can inflate HTTP request size, bind parameter counts, memory usage, processing time, and database load. Therefore, do not treat declaring a list in SDL as sufficient for resource control.

Apply multiple layers of limits:

- Limit the element count using Bean Validation or service checks.
- Limit request size at the web server or gateway.
- Use pagination for querying large lists instead of accepting tens of thousands of IDs in a single argument.
- Split into batches aligned with driver/database limits when needed.
- Configure timeouts, concurrency limits, and slow-query monitoring.
- Verify access permissions on every ID before returning data or mutating state.

Do not use list inputs as a way to bypass pagination or query complexity limits. A request containing a huge list of IDs can still cause load comparable to a heavy query. Calculate cost based on element count, operation type, and resources consumed by the service.

## 13. Testing List Inputs with GraphQlTester

`GraphQlTester` lets you send operations and inspect bound, processed, and returned data:

```java
graphQlTester.document("""
        query FindBooks($ids: [ID!]!) {
            booksByIds(ids: $ids) {
                id
                title
            }
        }
        """)
    .variable("ids", List.of("book-10", "book-20"))
    .execute()
    .path("booksByIds")
    .entityList(BookView.class)
    .hasSize(2);
```

With a list of input objects:

```java
graphQlTester.document("""
        mutation CreateBooks($inputs: [CreateBookInput!]!) {
            createBooks(inputs: $inputs) {
                id
                title
            }
        }
        """)
    .variable("inputs", List.of(
            Map.of("title", "GraphQL Basics", "authorId", "author-1", "tags", List.of("graphql")),
            Map.of("title", "Spring APIs", "authorId", "author-2", "tags", List.of("spring"))))
    .execute()
    .path("createBooks")
    .entityList(BookView.class)
    .hasSize(2);
```

Include tests for:

1. Multi-element lists bound in the exact order.
2. Empty lists handled per the contract.
3. Null list values and null elements rejected when the schema requires non-null.
4. Omitted fields and explicit null fields behaving properly under patch semantics.
5. Singleton coercion understood correctly; official clients still send arrays consistently.
6. Wrongly typed elements or invalid enum values rejected before the resolver.
7. Lists exceeding size limits rejected by validation.
8. Duplicate IDs, missing IDs, and result ordering following the chosen rules.
9. Bulk mutations performing transactions or partial success as designed.

## 14. Common Pitfalls

- **Confusing `[T]!` with `[T!]`:** one requires the list to be non-null, while the other requires every element to be non-null.
- **Assuming `!` requires the list to have elements:** an empty list is still valid without additional validation.
- **Conflating omitted, null, and `[]`:** can cause partial-update mutations to alter data unexpectedly.
- **Using raw `List`:** loses element type information and makes binding harder to control.
- **Assuming repositories preserve input order:** many `IN` queries do not guarantee ordering.
- **Converting lists to `Set` too early:** loses both order and duplicate elements.
- **Failing to limit element counts:** oversized requests can exhaust memory or exceed database limits.
- **Assuming GraphQL automatically checks ID existence and access permissions:** the `ID` scalar only checks type, not record existence or authorization.
- **Assuming bulk mutations are always atomic:** transactions and partial-success policies must be explicitly defined by the application.

## 15. Process for Designing List Inputs

When adding a list input in Spring for GraphQL, follow this order:

1. Determine whether the list contains scalars, enums, or input objects; choose the appropriate element type.
2. Decide nullability separately for the list and for each element.
3. Define the meaning of omitted fields, `null`, and empty lists.
4. Declare an input object when each element has multiple related attributes.
5. Bind to `List<T>` or a DTO/record with an explicit generic type.
6. Add validation for element count, formatting, duplicates, and business constraints.
7. Define rules for ordering, missing elements, transactions, and partial success.
8. Set resource limits and pagination appropriate to data scale.
9. Use `GraphQlTester` to verify coercion, binding, errors, and actual responses.

List inputs help GraphQL APIs process multiple values in a single operation with a clear type contract. When you design nullability properly, preserve list semantics, and bind to typed collections/DTOs, Spring for GraphQL resolvers can handle batch data cleanly. Combine validation, size limits, and business rules so list inputs are both convenient for clients and safe for the server.

## References

- [GraphQL Specification — List](https://spec.graphql.org/October2021/#sec-List)
- [GraphQL Specification — Input Coercion](https://spec.graphql.org/October2021/#sec-Input-Coercion)
- [Spring for GraphQL — Argument Binding](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.arguments)
- [Spring for GraphQL — Validation](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.validation)
- [Spring for GraphQL — GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
