# Queries with Arguments

In GraphQL, a field can accept **arguments** so clients can pass filter criteria, identifiers, sort orders, or data limits. Thanks to arguments, a single field can serve many query scenarios without creating a separate Query field for every variation. For example, the `books` field can return a list of books filtered by keyword, author, publication status, and pagination details.

In Spring for GraphQL, a Query handler method receives argument values using the **@Argument** annotation. Spring reads the data from the GraphQL operation, converts it to the corresponding Java type, and passes it into the controller method. Therefore, design arguments clearly in the SDL and ensure Java types are compatible with that contract.

## What Is an Argument in GraphQL?

An argument is a parameter declared immediately after the field name in the schema. Each argument has a name, a data type, and optionally a default value:

~~~graphql
enum BookSort {
  TITLE_ASC
  PUBLISHED_DESC
  RATING_DESC
}

type Query {
  book(id: ID!): Book
  books(authorId: ID, limit: Int = 20, sort: BookSort = TITLE_ASC): [Book!]!
}

type Book {
  id: ID!
  title: String!
}
~~~

In the example:

- The `book` field takes an `id` argument of type `ID!`; clients must pass a book ID.
- The `books` field takes an optional `authorId` to filter by author.
- The `limit` argument has a default value of `20` when the client omits the value.
- Argument values are used to determine the data returned by the resolver.

Arguments belong to each field. Clients can pass different values when calling the same field at different positions within a single operation. If you need to call the same field multiple times in the same selection set, use aliases to assign a distinct name to each result:

~~~graphql
query {
  newest: books(limit: 5, sort: PUBLISHED_DESC) {
    id
    title
  }
  popular: books(limit: 5, sort: RATING_DESC) {
    id
    title
  }
}
~~~

Both calls use the same `books` field with different arguments and aliases. The response will have two keys, `newest` and `popular`.

## Choosing Data Types for Arguments

Arguments can use valid GraphQL input types, such as scalars, enums, input objects, or lists of those types. Object types, interfaces, and unions are output types and cannot be used directly as argument types.

Common types:

| Type | Example | Meaning |
| --- | --- | --- |
| Scalar | id: ID!, keyword: String | A single value such as a string, number, or boolean |
| Enum | status: BookStatus | One value from a predefined set of choices |
| Input object | filter: BookFilterInput | A group of structured criteria |
| List | ids: [ID!]! | A list of input values |

Example declaring an enum and an input object:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

enum BookSort {
  TITLE_ASC
  PUBLISHED_DESC
  RATING_DESC
}

input BookFilterInput {
  keyword: String
  authorId: ID
  status: BookStatus
  publishedFrom: Int
  publishedTo: Int
}

type Query {
  books(
    filter: BookFilterInput
    sort: BookSort = TITLE_ASC
    page: Int = 0
    size: Int = 20
  ): [Book!]!
}
~~~

Input objects group related criteria into a single parameter. When the API needs a new criterion, `BookFilterInput` can be extended without creating a long list of arguments on the `books` field. However, an input object is still part of the public contract; only include fields that clients are genuinely permitted to use.

## Nullability and Default Values

The exclamation mark in the SDL defines whether an argument is required:

~~~graphql
type Query {
  book(id: ID!): Book
  books(keyword: String, limit: Int = 20): [Book!]!
}
~~~

- `ID!` means the client must supply `id` and the value cannot be null.
- `String` means `keyword` can be omitted or passed as null.
- `limit: Int = 20` means when the client omits the argument, GraphQL uses the default value `20`.
- If the client explicitly passes `null` for `limit`, the default value is not applied; because the argument is nullable `Int`, `null` may be accepted.

Distinguish three cases:

| How it is sent | Meaning |
| --- | --- |
| Argument omitted | Argument is absent; GraphQL uses the default if defined |
| Argument sent with null | Client explicitly passed null; default does not replace it |
| Specific value sent | GraphQL validates the type and passes the value to the resolver |

For a non-null argument without a default, if the client omits it or passes null, the operation fails validation/coercion before the resolver is invoked. This rule saves the server from having to process a missing required value.

Default values declared in the SDL are part of the API contract. Choose defaults with clear business meaning and avoid defaults that cause clients to accidentally load too much data.

## Passing Arguments with GraphQL Variables

Clients can write values inline inside the operation:

~~~graphql
query {
  book(id: "book-101") {
    id
    title
  }
}
~~~

However, the more common practice is declaring variables to separate the query document from input data:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
~~~

Variables are sent separately in the JSON request:

~~~json
{
  "operationName": "FindBook",
  "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
  "variables": {
    "id": "book-101"
  }
}
~~~

GraphQL checks the variable's type against the argument type in the schema. For example, a variable of type `ID!` is compatible with an argument `id: ID!`. If the client sends an incompatible type, the operation is rejected before the resolver runs.

Variables enable operation reuse, avoid string concatenation to build queries, and make operation caching easier on clients or gateways. Input values still need business-rule validation on the server.

## Receiving Arguments in Spring for GraphQL with @Argument

Spring for GraphQL provides the **@Argument** annotation in the annotated controller package to bind a GraphQL field argument to a Java parameter:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String bookId) {
        return bookService.findById(bookId);
    }
}
~~~

The argument in the SDL is named `id`, while the Java parameter is named `bookId`. Specifying `@Argument("id")` explicitly identifies the name to bind. If the Java parameter name matches the argument name and parameter name metadata is preserved during compilation, you can shorten it to `@Argument String id`.

Argument names must match the schema. If the SDL declares `bookId` while Java binds `id`, Spring does not guess that the two names mean the same thing. When names differ, specify the name explicitly in the annotation to avoid receiving null or binding errors.

## Binding Multiple Arguments to One Method

A resolver can accept multiple separate arguments:

~~~graphql
type Query {
  searchBooks(
    keyword: String!
    limit: Int = 20
    status: BookStatus
  ): [Book!]!
}
~~~

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument String keyword,
        @Argument Integer limit,
        @Argument BookStatus status) {
    return bookService.search(keyword, limit, status);
}
~~~

Spring converts each argument to its corresponding Java type. Use wrapper types such as `Integer` when an argument can be null; the primitive type `int` cannot represent null. Even when the SDL guarantees an argument always has a value via `!` or a default value, the service should still enforce clear bounds and input validation rules.

When a field has many related parameters, an input object is usually easier to manage than adding numerous standalone arguments. This is especially useful for search filters, report configurations, or pagination criteria.

## Binding Input Objects to Java Records or DTOs

With an input object in the SDL:

~~~graphql
input BookFilterInput {
  keyword: String
  authorId: ID
  status: BookStatus
  publishedFrom: Int
  publishedTo: Int
}

type Query {
  books(filter: BookFilterInput): [Book!]!
}
~~~

You can declare a corresponding Java record:

~~~java
public record BookFilterInput(
        String keyword,
        String authorId,
        BookStatus status,
        Integer publishedFrom,
        Integer publishedTo) {
}
~~~

The resolver receives the entire input object:

~~~java
@QueryMapping
public List<Book> books(@Argument BookFilterInput filter) {
    return bookService.findBooks(filter);
}
~~~

Spring for GraphQL uses argument binding to convert the input data map into a Java object. The record or DTO needs constructors/properties matching the input structure. For nested inputs, the corresponding Java types must also reflect that nested structure.

If you need to handle flexible inputs or evolving structures, you can accept a `Map`:

~~~java
@QueryMapping
public List<Book> books(@Argument Map<String, Object> filter) {
    return bookService.findBooks(filter);
}
~~~

`Map` is flexible, but it forfeits compile-time type checking and makes manual validation more complex. For stable APIs, a DTO or record generally keeps the Java contract clear and easier to test.

## Distinguishing Between Omitted and Null Arguments

For certain update or search operations, omitting an argument and passing null have different meanings. For example, a client wants to filter by `status`:

- Omitting `status`: do not apply a status filter.
- Passing `status: null`: may request finding records with no status yet, if the business logic defines it that way.
- Passing `status: PUBLISHED`: retrieve only published books.

If the Java parameter is simply `BookStatus`, both omitted and explicit null may bind as null. Spring for GraphQL provides **ArgumentValue<T>** to preserve whether the argument was omitted:

~~~java
import org.springframework.graphql.data.ArgumentValue;

@QueryMapping
public List<Book> books(
        @Argument("status") ArgumentValue<BookStatus> status) {

    if (status.isOmitted()) {
        return bookService.findWithoutStatusFilter();
    }

    if (status.value() == null) {
        return bookService.findBooksWithNullStatus();
    }

    return bookService.findByStatus(status.value());
}
~~~

`ArgumentValue` helps the resolver distinguish an argument absent from the operation from an argument explicitly sent as null. Only use this mechanism when the distinction has business meaning; for many ordinary queries, a nullable parameter is enough.

## Argument Validation

GraphQL validates data types, nullability, and input structure against the schema. However, the schema cannot express every business rule. For example, `size` may be `Int` while the application needs it bounded between 1 and 100; `publishedFrom` must not exceed `publishedTo`; `keyword` must not consist solely of whitespace.

You can use Jakarta Bean Validation on input DTOs when the project has validation configured:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;

public record BookSearchInput(
        @Size(max = 100) String keyword,
        @Min(1) @Max(100) Integer size) {
}
~~~

~~~graphql
input BookSearchInput {
  keyword: String
  size: Int
}

type Query {
  searchBooks(input: BookSearchInput!): [Book!]!
}
~~~

The resolver can annotate the input parameter with `@Valid`:

~~~java
@QueryMapping
public List<Book> searchBooks(@Argument @Valid BookSearchInput input) {
    return bookService.search(input);
}
~~~

Validation requires appropriate dependencies and configuration, such as the Spring Boot validation starter. Check how your project's Spring for GraphQL version activates validation on method arguments and standardizes validation failures into GraphQL errors with useful information for clients.

Never rely solely on client-side validation. Every value from a request must be validated on the server before being used in a service or repository.

## Using Arguments for Filtering, Sorting, and Pagination

A practical Query field often combines filtering, sorting, and pagination:

~~~graphql
enum BookSort {
  TITLE_ASC
  PUBLISHED_DESC
}

input BookFilterInput {
  keyword: String
  authorId: ID
  status: BookStatus
}

type Query {
  books(
    filter: BookFilterInput
    sort: BookSort = TITLE_ASC
    page: Int = 0
    size: Int = 20
  ): [Book!]!
}
~~~

Java resolver:

~~~java
@QueryMapping
public List<Book> books(
        @Argument BookFilterInput filter,
        @Argument BookSort sort,
        @Argument Integer page,
        @Argument Integer size) {

    int safePage = Math.max(page == null ? 0 : page, 0);
    int safeSize = Math.min(Math.max(size == null ? 20 : size, 1), 100);

    return bookService.findBooks(filter, sort, safePage, safeSize);
}
~~~

The resolver normalizes `page` and `size` to protect the data layer from negative values or excessive sizes. In a real application, extract this validation and normalization into a shared component or service so endpoints apply it consistently.

For very large lists or frequently changing data, cursor pagination may fit better than offset pagination. Whichever approach is used, the schema should clearly document page units, size limits, sort order, and how invalid cursors are handled.

## Arguments and Safe Data Querying

Arguments are typically passed down to services and repositories to construct query conditions. Never concatenate `keyword`, `sort`, or `filter` strings directly into SQL using string concatenation. Use repository parameter binding or parameterized query builders to prevent SQL injection.

For sort fields, never accept arbitrary column names from clients and interpolate them into SQL. Use an enum such as `BookSort` to restrict valid choices, then map each enum value to an allowed sort property.

Arguments can also contain sensitive data. Do not log full variables or input objects if they contain tokens, personal data, or confidential information. Verify access permissions and tenant scope in the service/repository, even when arguments are valid according to the schema.

## Testing Queries with Arguments

Spring for GraphQL provides `GraphQlTester` to test operations and variables. Example:

~~~java
graphQlTester.document("""
        query Books($filter: BookFilterInput, $size: Int) {
            books(filter: $filter, size: $size) {
                id
                title
            }
        }
        """)
    .variable("filter", Map.of(
            "keyword", "Spring",
            "status", "PUBLISHED"))
    .variable("size", 10)
    .execute()
    .path("books")
    .entityList(Book.class)
    .hasSize(2);
~~~

Cases to test:

- Valid arguments returning the expected data.
- Omitting an argument with a default and verifying the default is applied.
- Passing null to a nullable argument.
- Omitting or passing null to a non-null argument and verifying the error occurs before the resolver runs.
- Passing an invalid scalar or enum value.
- Input object missing required fields or containing values invalid under business rules.
- Pagination with negative `page`, `size` equal to 0, or `size` exceeding the maximum.
- Filter arguments not being allowed to access data belonging to another tenant.

When testing input object variables, you can use a `Map` or a DTO compatible with the tester and schema structure. Tests should assert both results and GraphQL errors, not merely confirm that the HTTP request succeeded.

## Common Errors When Binding Arguments

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Java parameter receives null | `@Argument` name does not match SDL or client did not send a value | Compare argument name, variables, and annotation |
| Input object fails to bind | Record/DTO has incompatible fields or types | Check constructors, properties, and Java types |
| Wrong argument type | Client sent a string for `Int` or an unknown enum value | Fix variable type and value |
| Default value is not used | Client explicitly passed null | Distinguish between omitted and null |
| Cannot distinguish omitted from null | Plain nullable Java parameter | Use `ArgumentValue` when business logic needs the distinction |
| Query returns too much data | Missing pagination bounds or `size` is unchecked | Enforce default and maximum on the server |
| Query fails before resolver runs | Non-null argument is missing or has the wrong type | Check schema and variables |

## Principles for Designing Arguments

When designing arguments for Query fields, apply these principles:

1. **Name according to business meaning.** Use clear and consistent names such as `id`, `keyword`, `filter`, or `pageSize`.
2. **Choose types that fit the data.** Use enums for fixed sets of choices and input objects for structured groups of criteria.
3. **Specify nullability intentionally.** Only use `!` when the client must supply a value and the server requires it.
4. **Set sensible defaults.** Defaults shorten operations, but must not cause unexpectedly large data loads.
5. **Use variables for dynamic data.** Separate the operation from input values and avoid building queries by string concatenation.
6. **Bind to DTOs or records.** Explicit Java types make services easier to validate and maintain.
7. **Validate on the server.** Check bounds, cross-field relationships, and access permissions before querying data.
8. **Cap pagination.** Never let clients request an unbounded number of records.
9. **Use ArgumentValue when needed.** Distinguish omitted from null if the two cases have different meanings.

Query arguments are the mechanism clients use to control how data is fetched through a strongly typed contract. In Spring for GraphQL, the SDL defines names, types, nullability, and defaults; `@Argument` transfers values into Java; input DTOs/records group criteria; and services and repositories enforce validation, authorization, and safe querying. Good design enables a single Query field to serve many needs while remaining easy to understand, test, and control in query cost.
