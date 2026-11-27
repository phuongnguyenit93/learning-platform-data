# Field Arguments in GraphQL

## Objectives

After this lesson, you will be able to:

- Explain what a field is and how arguments are declared and passed to a field.
- Read field and argument definition syntax in GraphQL SDL.
- Distinguish required, nullable, default-value arguments, and arguments that accept lists or input objects.
- Write Queries and Mutations using arguments with literals and variables.
- Understand how arguments work on both root fields and nested fields.
- Map arguments to Java methods using `@Argument` and `@SchemaMapping` in Spring for GraphQL.
- Handle input objects, omitted values, null values, and input errors.
- Design consistent arguments for filtering, sorting, pagination, and security.

## 1. What are fields and arguments?

A field is a unit of data that a client requests in a GraphQL operation. Each field is declared on a schema type and has a return type. A field can also have arguments so the client can supply input information for resolving that value.

Example:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

In the declaration above:

- `book` is the field name.
- `id` is the field's argument.
- `ID!` is the argument's type. The `!` indicates that the value cannot be null.
- `Book` is the field's return type.

A client uses the field and argument in an operation:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

The client requests the `book` field and passes the `id` argument with the value `"book-42"`. Because `book` returns a `Book` object, the operation continues by selecting the child fields `id` and `title`.

Put simply:

- **The schema defines** which fields exist, which arguments a field accepts, their data types, and what type the field returns.
- **The operation passes** concrete values for the arguments and selects the fields to receive in the response.
- **The Resolver/DataFetcher executes** the field by using the arguments to find, filter, compute, or mutate data.

An argument is not a child field. It is an input to the field being invoked. Child fields can have their own arguments according to the definitions in the schema.

## 2. Syntax for declaring fields and arguments in SDL

A field can be declared in the form:

~~~graphql
fieldName(argumentName: ArgumentType): ReturnType
~~~

A field with multiple arguments:

~~~graphql
fieldName(
    firstArgument: FirstType
    secondArgument: SecondType
): ReturnType
~~~

Example:

~~~graphql
type Query {
    book(id: ID!): Book
    books(authorId: ID!, limit: Int = 20): [Book!]!
}
~~~

The `book` field has one required argument, `id`. The `books` field has two arguments:

- `authorId: ID!` is required and cannot be null.
- `limit: Int = 20` has a default value of 20; the client may omit this argument.

Arguments are declared inside parentheses after the field name. Each argument has a name, a data type, and optionally a default value.

### 2.1. Arguments are named, not positional parameters

GraphQL uses named arguments. The client must specify the argument name when passing a value:

~~~graphql
query {
    books(authorId: "author-12", limit: 10) {
        id
        title
    }
}
~~~

The order in which arguments are passed does not affect the meaning of the operation:

~~~graphql
query {
    books(limit: 10, authorId: "author-12") {
        id
        title
    }
}
~~~

The two operations above are equivalent with respect to arguments. GraphQL does not assign values by position like function calls with positional parameters.

Argument names must match the names declared in the schema. Passing an argument that does not exist will cause the operation to fail validation.

### 2.2. Fields without arguments

Not every field needs an argument:

~~~graphql
type Query {
    currentUser: User
    featuredBooks: [Book!]!
}
~~~

The client can call them directly:

~~~graphql
query {
    currentUser {
        id
        displayName
    }
    featuredBooks {
        id
        title
    }
}
~~~

Only add arguments when the client actually needs to provide input to determine the result or behavior of the field.

### 2.3. Arguments can also appear on nested fields

Arguments are not exclusive to root fields on `Query` or `Mutation`. A field on an object type can also accept arguments:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}
~~~

The client can request a different number of reviews for each book:

~~~graphql
query {
    book(id: "book-42") {
        title
        reviews(first: 5) {
            id
            rating
            comment
        }
    }
}
~~~

Here `first` is an argument of the `reviews` field, not of the `book` field. Each field has its own argument list defined by the schema.

## 3. Data types that can be used for arguments

Arguments use valid GraphQL input types. Common types include scalars, enums, lists, and input objects.

### 3.1. Scalar

Scalars are suitable for simple inputs:

~~~graphql
type Query {
    book(id: ID!): Book
    books(limit: Int, minRating: Float): [Book!]!
    searchBooks(keyword: String!, exactMatch: Boolean = false): [Book!]!
}
~~~

Built-in scalars:

| Scalar | Example value |
| --- | --- |
| `Int` | `10` |
| `Float` | `4.5` |
| `String` | `"Spring GraphQL"` |
| `Boolean` | `true` or `false` |
| `ID` | `"book-42"` |

`ID` is used for identifiers. It is passed as a string or integer according to GraphQL coercion rules, but in responses it is usually serialized as a string. Use `ID` when the argument represents an identifier; use `String` for general text.

### 3.2. Enum

If an argument accepts only a finite set of choices, an enum helps the schema clearly express the valid values:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Query {
    booksByStatus(status: BookStatus!): [Book!]!
}
~~~

The client passes an enum value without quotes:

~~~graphql
query {
    booksByStatus(status: PUBLISHED) {
        id
        title
    }
}
~~~

The value `PUBLISHED` is an enum literal, not the string `"PUBLISHED"`. Passing a string instead of an enum can cause a coercion error due to incompatible types.

### 3.3. List

An argument can accept a list:

~~~graphql
type Query {
    booksByIds(ids: [ID!]!): [Book!]!
}
~~~

The client passes a list literal:

~~~graphql
query {
    booksByIds(ids: ["book-1", "book-2", "book-3"]) {
        id
        title
    }
}
~~~

The declaration `[ID!]!` means:

- The argument value is a list and cannot be null.
- Each element in the list must be a non-null ID.
- An empty list is still a valid value unless business logic imposes its own validation rule.

Distinguish between these forms:

| Declaration | Meaning |
| --- | --- |
| `[ID]` | The list may be null; elements may be null |
| `[ID!]` | The list may be null; elements cannot be null |
| `[ID]!` | The list cannot be null; elements may be null |
| `[ID!]!` | The list and all elements cannot be null |

### 3.4. Input object

When a field needs multiple related conditions, they can be grouped into an input object:

~~~graphql
input BookFilter {
    titleContains: String
    authorId: ID
    status: BookStatus
    minRating: Float
}

type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

The client passes an input object:

~~~graphql
query {
    books(
        filter: {
            titleContains: "GraphQL"
            status: PUBLISHED
            minRating: 4.0
        }
    ) {
        id
        title
    }
}
~~~

Input objects keep field calls cleaner when there are many conditions. They also help the schema express a meaningful group of input data.

An input object can only contain valid input types such as scalars, enums, other input objects, and lists of them. You cannot directly use an output object type like `Book` or `Author` as the type of an input field.

## 4. Required, nullable, and default-value arguments

Designing argument requiredness is an important decision. It affects how clients call the API and how resolvers interpret input data.

### 4.1. Non-null arguments

The `!` symbol marks an argument as non-nullable:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

The client must provide `id` and the value cannot be null:

~~~graphql
query {
    book(id: "book-42") {
        title
    }
}
~~~

Invalid cases:

~~~graphql
query {
    book {
        title
    }
}
~~~

~~~graphql
query {
    book(id: null) {
        title
    }
}
~~~

GraphQL validation/coercion detects a missing or null required argument before the field resolver is executed.

### 4.2. Nullable arguments

Without `!`, an argument can accept null or be omitted:

~~~graphql
type Query {
    books(status: BookStatus): [Book!]!
}
~~~

The client can call:

~~~graphql
query {
    books {
        id
        title
    }
}
~~~

Or pass null:

~~~graphql
query {
    books(status: null) {
        id
        title
    }
}
~~~

The meaning of omitting vs. passing null depends on the business rules applied by the resolver. For example, one application might interpret omitting status as fetching all books and null status as also not filtering. Another application might define these two cases differently.

### 4.3. Default values

An argument can declare a default value in SDL:

~~~graphql
type Query {
    books(limit: Int = 20): [Book!]!
}
~~~

If the client does not pass `limit`, GraphQL uses the default value 20:

~~~graphql
query {
    books {
        id
        title
    }
}
~~~

The client can still override it:

~~~graphql
query {
    books(limit: 5) {
        id
        title
    }
}
~~~

You can declare a non-null argument that still has a default value:

~~~graphql
type Query {
    popularBooks(limit: Int! = 10): [Book!]!
}
~~~

With this declaration, the client can omit the argument because the schema provides a default value. If the client explicitly passes null, the request is invalid because the argument type is non-null.

### 4.4. Omitting an argument and passing null have two different meanings

Consider the declaration:

~~~graphql
type Query {
    books(status: BookStatus): [Book!]!
}
~~~

The following two calls can be interpreted differently by the application:

~~~graphql
query {
    books {
        id
    }
}
~~~

~~~graphql
query {
    books(status: null) {
        id
    }
}
~~~

The first case does not provide the `status` argument. The second case provides the argument with a null value.

This distinction is especially important for update mutations. Omitting an input field usually means "keep the current value unchanged," whereas passing null may mean "clear the current value." If the resolver or binder does not preserve whether the argument was omitted or passed as null, use a representation at the application layer that can distinguish those two states.

## 5. Using variables to pass arguments

Literals are convenient for short examples, but real-world applications usually use variables to separate data from the document.

The operation declares variables at the top:

~~~graphql
query FindBook($id: ID!, $includeReviews: Boolean! = false) {
    book(id: $id) {
        id
        title
        reviews(first: 5) @include(if: $includeReviews) {
            id
            rating
        }
    }
}
~~~

The client passes variables as JSON:

~~~json
{
    "id": "book-42",
    "includeReviews": true
}
~~~

`$id` is passed into the `id` argument of the `book` field. `$includeReviews` is used as the condition for the `@include` directive.

Variables have types and can have default values. A variable's type must be compatible with the argument type where it is used.

Valid example:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Incompatible example:

~~~graphql
query FindBook($id: Int!) {
    book(id: $id) {
        id
        title
    }
}
~~~

If the `book.id` argument requires `ID!`, the variable type `Int!` is not a matching declared type just because the actual value happens to be a number. GraphQL checks type compatibility based on the schema and variable definition.

### 5.1. Variables for input objects

Input objects can also be passed via variables:

~~~graphql
query SearchBooks($filter: BookFilter, $limit: Int = 20) {
    books(filter: $filter, limit: $limit) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "titleContains": "Spring",
        "status": "PUBLISHED",
        "minRating": 4.0
    },
    "limit": 10
}
~~~

In JSON, enum values are represented as strings because JSON does not have a dedicated enum type. The GraphQL runtime coerces that string according to the enum declared in the schema.

### 5.2. Why prefer variables?

Variables provide several benefits:

- Avoids concatenating user data directly into GraphQL query strings.
- Allows the GraphQL runtime to validate input types.
- Reuses one operation across many data sets.
- Makes operations easier to manage on the client and trace in requests.
- Supports better operation caching when the document does not change.

You should not build operations by concatenating user-supplied values into the query string. Pass data through variables to keep documents stable and reduce the risk of syntax errors or injection at the query-building layer.

## 6. Arguments on nested fields and their scope

Arguments belong to the specific field declared in the schema. They are not automatically propagated down to child fields.

Schema example:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    title: String!
    reviews(first: Int = 10): [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
~~~

Operation:

~~~graphql
query {
    book(id: "book-42") {
        title
        reviews(first: 3) {
            rating
            comment
        }
    }
}
~~~

`id` is an argument of `Query.book`. `first` is an argument of `Book.reviews`. The resolver for `reviews` receives `first` according to its field definition.

If the client requests multiple nested fields, each field can have independent arguments:

~~~graphql
query {
    book(id: "book-42") {
        title
        reviews(first: 3) {
            rating
        }
    }
    anotherBook: book(id: "book-99") {
        title
        reviews(first: 8) {
            rating
        }
    }
}
~~~

The two calls to `book` can use different arguments; each call to `reviews` can also receive its own `first` value. GraphQL processes each field occurrence in the selection set according to its own arguments.

If you want to use the same value across multiple fields, you can declare one variable and pass it into each corresponding position.

## 7. Arguments in Spring for GraphQL

In Spring for GraphQL, field arguments are passed into controller methods or DataFetchers. With annotated controllers, `@Argument` binds the argument value to a Java parameter.

Suppose the schema is:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Controller:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book book(@Argument("id") String bookId) {
        return bookService.findById(bookId);
    }
}
~~~

`@QueryMapping` maps the method to the `book` field on the root `Query` type. `@Argument("id")` retrieves the `id` argument value and binds it to the Java parameter `bookId`.

The Java parameter name does not have to match the argument name if you specify the name in the annotation. This keeps the mapping explicit and independent of whether the compiler retains parameter name metadata.

### 7.1. Using @Argument on nested fields

Schema example:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}
~~~

The controller can map the `reviews` field:

~~~java
@Controller
class BookReviewController {

    private final ReviewService reviewService;

    BookReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    List<Review> reviews(
            Book book,
            @Argument("first") Integer first) {

        return reviewService.findByBookId(book.id(), first);
    }
}
~~~

`@SchemaMapping` specifies that the method handles the `reviews` field of the `Book` type. The `Book book` parameter is the parent source object being resolved; `@Argument("first")` receives the field's argument.

If the method name matches the field name and the source type can be inferred from the parameter type, Spring can infer part of the mapping. However, explicitly specifying `typeName` and `field` in the example helps readers clearly see which field is being handled.

### 7.2. Using @Argument with input objects

Schema:

~~~graphql
input BookFilter {
    titleContains: String
    authorId: ID
    status: BookStatus
}

type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

Java record:

~~~java
public record BookFilter(
        String titleContains,
        String authorId,
        BookStatus status) {
}
~~~

Controller:

~~~java
@QueryMapping
List<Book> books(@Argument("filter") BookFilter filter) {
    return bookService.search(filter);
}
~~~

Spring for GraphQL uses argument binding to convert the input map into the corresponding Java object. The Java type must have a constructor or property binding matching the input structure.

For complex input objects, use a dedicated DTO/record for GraphQL input. This prevents the schema from depending directly on persistence entities and makes input validation clearer.

### 7.3. Using explicit argument names

You can write:

~~~java
@QueryMapping
Book book(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

Or when Java parameter names are preserved and used by Spring for inference:

~~~java
@QueryMapping
Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

In code meant for documentation or critical APIs, specifying the argument name explicitly makes the mapping easier to read and avoids relying on compiler configuration.

### 7.4. Java types should reflect nullability

If an argument can be null, use reference types such as `Integer`, `Boolean`, or `String` instead of their primitive counterparts.

Example:

~~~graphql
type Query {
    books(limit: Int): [Book!]!
}
~~~

~~~java
@QueryMapping
List<Book> books(@Argument("limit") Integer limit) {
    int effectiveLimit = limit != null ? limit : 20;
    return bookService.findBooks(effectiveLimit);
}
~~~

If you use `int` for a nullable argument, Java cannot represent a null value. For non-null arguments, you can use primitives when appropriate, though reference types remain useful if you want to validate or process the value before calling the service.

When the schema already defines a default value, the GraphQL runtime applies the default before the resolver uses the argument. Therefore, the resolver should follow a consistent rule and avoid accidentally applying a second default that differs from the schema.

## 8. Distinguishing omitted arguments from null arguments in Java

In some update mutations, the following two states have different meanings:

- The client omits the input field: keep the current value unchanged.
- The client sends the field with a null value: clear the current value if business rules allow it.

Example:

~~~graphql
input UpdateBookInput {
    id: ID!
    subtitle: String
}

type Mutation {
    updateBook(input: UpdateBookInput!): Book!
}
~~~

The following two sets of variables are not equivalent:

~~~json
{
    "input": {
        "id": "book-42"
    }
}
~~~

~~~json
{
    "input": {
        "id": "book-42",
        "subtitle": null
    }
}
~~~

In the first input, `subtitle` is omitted. In the second input, `subtitle` is provided with a null value.

If both cases are bound only to a `String subtitle` Java variable, the received value may be null in both cases. When business logic needs to distinguish them, Spring for GraphQL provides the `ArgumentValue<T>` type to represent both the omitted state and the present state, including null.

Illustrative example:

~~~java
public record UpdateBookInput(
        String id,
        ArgumentValue<String> subtitle) {
}
~~~

The service can inspect the state of `ArgumentValue` to decide whether to update the field. The exact API usage should follow your project's Spring for GraphQL version; check the current package and methods when implementing.

Not every input needs to distinguish these two states. Only use this mechanism when business logic has a clear distinction between omitting a value and clearing it.

## 9. Designing arguments for filtering, sorting, and pagination

Queries that return lists often need arguments for filtering, sorting, and pagination. You should design them with consistent conventions.

### 9.1. Filter

Example:

~~~graphql
input BookFilter {
    titleContains: String
    authorId: ID
    status: BookStatus
}

type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

The client can pass only a subset of conditions:

~~~graphql
query {
    books(filter: { status: PUBLISHED }) {
        id
        title
    }
}
~~~

The resolver needs to clearly define how multiple conditions are combined: AND, OR, exact match, or partial match. Clients should not have to guess the meaning of each filter field.

### 9.2. Sort

Enums can be used to restrict sortable fields and sort directions:

~~~graphql
enum BookSortField {
    TITLE
    PUBLISHED_AT
}

enum SortDirection {
    ASC
    DESC
}

input BookSort {
    field: BookSortField!
    direction: SortDirection! = ASC
}

type Query {
    books(sort: BookSort): [Book!]!
}
~~~

Client:

~~~graphql
query {
    books(sort: { field: PUBLISHED_AT, direction: DESC }) {
        id
        title
    }
}
~~~

Enums prevent clients from passing arbitrary database column names. The server still needs to map the enum to allowed sort fields in the application.

### 9.3. Offset pagination

A simple pagination approach:

~~~graphql
type Query {
    books(page: Int = 0, size: Int = 20): [Book!]!
}
~~~

Client:

~~~graphql
query {
    books(page: 2, size: 10) {
        id
        title
    }
}
~~~

You must clearly define whether `page` starts at 0 or 1, what the maximum `size` is, and how negative values are handled. Do not rely solely on the client to protect server resources.

### 9.4. Cursor pagination

For frequently changing data or large lists, cursor pagination can be a better fit:

~~~graphql
type Query {
    books(first: Int = 20, after: String): BookConnection!
}

type BookConnection {
    edges: [BookEdge!]!
    pageInfo: PageInfo!
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

The client passes `first` and `after` to request the next page. Cursors should be generated from a stable position in the data ordering; do not allow clients to pass an arbitrary SQL expression or column name as a cursor.

Whether using offset or cursor pagination, keep argument names consistent across list fields with the same behavior.

## 10. Argument validation and error handling

GraphQL checks argument types and structure before calling the resolver. Common errors include:

- Missing a non-null argument.
- Passing null for a non-null argument.
- Passing a literal of the wrong type.
- A variable incompatible with the argument type.
- Passing a non-existent enum value.
- An input object containing a field not declared in the schema.

Schema example:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Operation missing a required argument:

~~~graphql
query {
    book {
        id
    }
}
~~~

Operation passing the wrong type:

~~~graphql
query {
    book(id: 123.45) {
        id
    }
}
~~~

The GraphQL runtime detects parse, validation, or coercion errors and does not execute the field as a valid request. This serves as a contract check layer, but it does not replace business validation.

For example, a `limit` argument might have a valid `Int` type yet still be invalid under business rules if the client passes a negative number or an excessively large value. The resolver or service needs to validate those bounds:

~~~java
@QueryMapping
List<Book> books(@Argument("limit") Integer limit) {
    int effectiveLimit = limit == null ? 20 : limit;

    if (effectiveLimit < 1 || effectiveLimit > 100) {
        throw new IllegalArgumentException("limit must be between 1 and 100");
    }

    return bookService.findBooks(effectiveLimit);
}
~~~

In a real application, business errors should be translated into GraphQL errors with appropriate messages without exposing internal details. You can use Spring for GraphQL's exception handling mechanisms such as `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`.

## 11. Security when designing arguments

Arguments are client-supplied data. Do not treat a type-valid argument as trustworthy for access control.

For example, you should not design a Query that lets the client pass an arbitrary tenant:

~~~graphql
type Query {
    books(tenantId: ID!): [Book!]!
}
~~~

If users can change `tenantId`, they could attempt to access another tenant's data if the server does not check permissions.

In a multi-tenant system, the tenant should be determined from the authenticated identity or a trusted security context. If the schema needs to accept a tenant identifier for a special business case, the server must still verify that the user has permission to access that tenant.

Some principles:

- Check object access permissions in the service or resolver.
- Never use `userId`, `role`, or `tenantId` from the client as proof of identity/authorization.
- Limit page size, the number of IDs in a list, and filter complexity.
- Allow only predefined sort fields; never concatenate field names from input directly into SQL.
- Use parameter binding in repositories/queries instead of string concatenation of input data.
- Do not log full arguments if they might contain sensitive data.

Arguments are part of the API contract; authorization and business validation remain the server's responsibility.

## 12. Common mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `Unknown argument` | Argument name does not exist on the field | Check SDL and the argument name in the operation |
| Missing required argument | Argument has `!` but the client omitted it | Pass a value or redesign nullability if truly optional |
| `Expected type ...` | Literal or variable has the wrong type | Align the type with the schema |
| Invalid enum value | Value is not in the enum or was passed as a string literal | Use the declared enum value |
| Resolver receives null | Argument was omitted, explicit null, or mapped incorrectly | Check schema, variables, and Java type |
| Input object fails to bind | DTO is incompatible with the input structure | Check constructor, record, and property binding |
| Updates do not distinguish omitted vs. null | Java type only represents a single null value | Consider `ArgumentValue<T>` |
| Query returns too much data | Missing pagination or filter limits | Set defaults, maximums, and server-side validation |
| Users access out-of-scope data | Trusting client-sent identifier arguments | Enforce permissions on the server and security context |

## 13. Workflow for designing a field with arguments

When adding a new field to the schema, you can follow this sequence:

1. **Define the field result.** Does the field return a scalar, an object, or a list?
2. **Identify input data.** What information does the client need to provide to select or transform the result?
3. **Choose argument types.** Use scalars, enums, lists, or input objects according to the business structure.
4. **Decide nullability.** Which values are required? Which cases may be omitted or passed as null?
5. **Set defaults if applicable.** Default values should have a stable, business-appropriate meaning.
6. **Write sample operations.** Test literals, variables, missing values, and nulls.
7. **Map to the resolver.** Use `@Argument` and compatible Java types.
8. **Validate business rules and permissions.** Enforce bounds, access control, and data consistency.
9. **Test invalid inputs.** Include wrong types, missing arguments, invalid enums, and invalid input objects.
10. **Monitor performance.** Especially with nested fields and large lists.

## 14. Summary

A field is the unit of data a client requests in GraphQL; an argument is a named input passed to that field. The schema defines the name, type, nullability, and default value of each argument. Operations supply literals or variables to execute the field. Arguments can use scalars, enums, lists, or input objects and can appear on both root fields and nested fields.

In Spring for GraphQL, `@Argument` binds input values to Java parameters of a controller or DataFetcher; `@SchemaMapping` handles arguments on nested fields. Good design clarifies required, nullable, default, omitted, and explicit null cases. When combined with server-side validation, authorization, and resource limits, arguments provide a clear and safe way for clients to control the data an API delivers.
