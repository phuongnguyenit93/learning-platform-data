# Mapping Null Results

## Objectives

After this lesson, you will be able to:

- Explain the meaning of a null result when GraphQL resolves a field.
- Distinguish nullable and non-null fields in SDL schemas.
- Understand how GraphQL propagates null when a resolver violates nullability.
- Distinguish missing data results from GraphQL execution errors.
- Handle `null`, `Mono.empty()`, and empty collections in Spring for GraphQL.
- Choose the appropriate representation when data is not found.
- Test null results and error propagation using `GraphQlTester`.

## What is mapping a null result?

When GraphQL executes a field, the resolver can return a value, an object, a list, or no value. For a nullable field, having no value is represented by `null` in the response.

Example schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

The resolver can return null if the book is not found:

~~~java
@QueryMapping
public Book bookById(@Argument("id") String id) {
    return bookService.findById(id).orElse(null);
}
~~~

If the book does not exist, the response may be:

~~~json
{
  "data": {
    "bookById": null
  }
}
~~~

This is a valid result because the `bookById` field has type `Book`, without `!`. GraphQL allows this field to return an object or `null`. If the resolver intentionally returns `null` and raises no error, the response does not need an `errors` entry.

`null` is part of the GraphQL contract. It does not automatically mean the server encountered an error. The meaning of `null` must be defined according to the schema and business logic: resource not found, optional data not provided, non-existent relationship, or value cannot be displayed.

## Nullability in SDL determines valid results

The `!` mark in SDL denotes a non-null type. Without this mark, the type is allowed to accept `null`.

~~~graphql
type Query {
  optionalBook(id: ID!): Book
  requiredBook(id: ID!): Book!
}
~~~

`optionalBook` can return a `Book` or `null`. `requiredBook` must return a non-null object. If `requiredBook`'s resolver returns `null`, GraphQL cannot construct a response conforming to the schema and must raise an execution error.

Nullability applies to scalars, objects, and lists alike. For lists, distinguish list nullability from element nullability:

| SDL | Can the list be null? | Can an element be null? |
| --- | --- | --- |
| [Book] | Yes | Yes |
| [Book!] | Yes | No |
| [Book]! | No | Yes |
| [Book!]! | No | No |

Example:

~~~graphql
type Query {
  books: [Book!]!
}
~~~

The `books` field must return a non-null list, and every element in the list must also be non-null. An empty list `[]` is still valid because the list exists and no element violates nullability.

## Distinguishing null, empty list, and empty object

These three results have different meanings:

~~~json
{
  "data": {
    "books": null
  }
}
~~~

`books: null` means the field has no value. This is only valid if the field's list type is nullable or `null` occurs due to error propagation reaching a nullable boundary.

~~~json
{
  "data": {
    "books": []
  }
}
~~~

`books: []` means the query succeeded and there are zero elements. This is usually the right result for a collection query that finds no records.

~~~json
{
  "data": {
    "books": [
      {
        "id": "book-101",
        "title": "Spring GraphQL"
      }
    ]
  }
}
~~~

An object containing data is a normal result. An object whose nullable fields are all null is still different from the object itself being null: the object exists, even though the selected properties have no values.

In Java, standardize empty collection results to an empty list:

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

If a service could return null for a collection, fix the service or normalize at the resolver boundary to avoid accidentally returning null for a `[Book!]!` field. Do not use null in place of an empty collection when the API's semantics are "zero elements".

## Null propagation when a non-null field returns null

GraphQL cannot keep `null` in a field declared non-null. When a resolver returns `null` for such a field, GraphQL produces an execution error and propagates `null` up to the nearest nullable parent field.

Example:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

If the `Book.title` resolver returns `null`, the `title` field violates `String!`. Because `Book` is nullable in `Query.book`, the entire `book` object becomes `null`. Other fields of that object are no longer returned as a complete object.

The response may look like:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Cannot return null for non-nullable field Book.title.",
      "path": ["book", "title"]
    }
  ]
}
~~~

If `Query.book` is also declared `Book!`, the error continues propagating up to root `data`:

~~~graphql
type Query {
  book(id: ID!): Book!
}
~~~

Then the response may be:

~~~json
{
  "data": null,
  "errors": [
    {
      "message": "Cannot return null for non-nullable field Book.title.",
      "path": ["book", "title"]
    }
  ]
}
~~~

This rule is called null propagation or error propagation. It guarantees the response never contains `null` where the schema promises non-null. An error in a child field can wipe out the entire parent object or an even larger branch if parent fields are also non-null.

### Null propagation with lists

Consider these declarations:

~~~graphql
type Query {
  nullableItems: [Book!]
  requiredItems: [Book!]!
}
~~~

If one element of the list is `null`, that element violates `Book!`. GraphQL cannot retain a single `null` element inside the list. The result of the entire list becomes `null`.

- For `nullableItems: [Book!]`, the list is allowed to be null, so the error stops at the `nullableItems` field.
- For `requiredItems: [Book!]!`, the list is also non-null, so the error continues propagating to the parent field.

Conversely, for `[Book]`, elements can be null. A null element does not automatically trigger a nullability error.

Choose nullability based on what the data can guarantee. If an element in a collection can validly be missing, `[Book]` may accurately reflect the contract. If every element is required, `[Book!]` is more appropriate and the server must handle missing data before returning the list.

## Null result vs. execution error

A resolver may return `null` intentionally or throw an exception. These two situations produce different responses:

| Scenario | Nullable field | errors |
| --- | --- | --- |
| Resolver returns null directly | Field value is null | No error unless another error occurred |
| Resolver returns null for a non-null field | null propagates to nullable boundary | Execution error present |
| Resolver throws an exception | Field usually becomes null, then null propagation applies per schema | Execution error present |
| Invalid input before resolver runs | Operation is rejected or corresponding part does not execute | Validation/coercion error present |

For example, not finding a book can be a normal outcome of a lookup query. If the schema allows `Book` to be nullable, returning `null` can be the right choice.

On the other hand, an unavailable database is an infrastructure error. Do not silently turn this error into `null` if the client needs to know the request failed. Throw an exception and map it to a GraphQL error per the API's policy.

Do not use `null` to hide all errors. If the server returns `null` for a nullable field during an outage, the client cannot tell "no data exists" apart from "could not fetch data" unless the API provides additional error information.

## Choosing semantics when data is not found

There is no mandatory rule that every not-found query must return `null` or an error. Choose based on the field's meaning:

| Use case | Typically appropriate representation |
| --- | --- |
| Looking up a single resource that may not exist | Nullable object field; return `null` when not found |
| Querying a list with no matching items | Return an empty list `[]` |
| Reading an optional field with no value yet | Nullable field; return `null` |
| Resource required by invariant but missing due to corrupted data | Raise an error so the violation is not hidden |
| User lacks access permission | Apply authorization policy; may return an error or hide existence per security requirements |
| Dependent service temporarily unavailable | Return a GraphQL error per error policy; do not pretend the data is simply absent |

Example book lookup queries:

~~~graphql
type Query {
  bookById(id: ID!): Book
  booksByAuthor(authorId: ID!): [Book!]!
}
~~~

With `bookById`, not finding a book can return `null`. With `booksByAuthor`, finding no books for that author should normally return `[]`. The two fields have different semantics even though both read from the same business domain.

## Mapping null in annotated controllers

For methods returning synchronous objects, Java `null` becomes a `null` field result:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }
}
~~~

The schema must allow null:

~~~graphql
type Query {
  bookById(id: ID!): Book
}
~~~

If you want the field to always have a result, do not merely change the schema to `Book!` while leaving `orElse(null)` intact. Ensure the service always returns an object or throws a meaningful exception:

~~~java
@QueryMapping
public Book requiredBook(@Argument("id") String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

The exception can be handled by `DataFetcherExceptionResolver` or Spring for GraphQL's exception handler mechanism. Error mapping should align with the API's error contract. Even when the field is non-null, the exception still creates a GraphQL error; null propagation proceeds according to the schema.

## Mapping null with Mono and Flux

Spring for GraphQL supports reactive return types. When a resolver returns `Mono<T>`, the result can emit one value or complete without emitting a value.

### `Mono.empty()` corresponds to no value

Example service returning `Mono<Book>`:

~~~java
@QueryMapping
public Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

If the service returns `Mono.empty()`, the resolver has no object to provide. The field result is treated as `null`, so the schema should declare the field nullable if not found is a valid outcome:

~~~graphql
type Query {
  bookById(id: ID!): Book
}
~~~

If the schema declares `Book!`, `Mono.empty()` leads to a non-null violation when GraphQL processes the result. Do not use an empty publisher for a non-null field unless there is a valid replacement value.

If you need to distinguish not found from data access failures, let the service emit an error signal for genuine failures. Do not convert every exception into `Mono.empty()` because that loses error information.

### `Flux.empty()` and empty lists

For regular queries returning a collection, `Flux<T>` is collected into a list of results. A `Flux.empty()` therefore corresponds to an empty list, not a null list:

~~~java
@QueryMapping
public Flux<Book> booksByAuthor(
        @Argument("authorId") String authorId) {
    return bookService.findByAuthorId(authorId);
}
~~~

Schema:

~~~graphql
type Query {
  booksByAuthor(authorId: ID!): [Book!]!
}
~~~

If there are no books, the `Flux` completes without emitting elements and the collection result is `[]`, which satisfies `[Book!]!`.

Do not confuse this case with `Mono.empty()` for a single object. `Mono.empty()` represents the absence of a single value; `Flux.empty()` in a collection query represents a result set with zero elements.

### Flux in subscriptions

For subscriptions, `Flux<T>` is a stream of events emitted over time. If the stream completes, the subscription ends; it does not mean a list query returned `null`.

~~~graphql
type Subscription {
  bookAdded: Book!
}
~~~

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded() {
    return bookEventService.bookAdded();
}
~~~

Each emitted item is an individual subscription payload. If the event source emits a null value for a `Book!` field, that result violates non-null. The event source should only emit valid payloads and handle stream errors according to defined policy.

## Null in nested fields

Nullability of nested fields determines the scope of affected data:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

If `Book.author` is nullable and the resolver returns `null`, the response can still preserve the `Book` object:

~~~json
{
  "data": {
    "book": {
      "id": "book-101",
      "title": "Spring GraphQL",
      "author": null
    }
  }
}
~~~

If the field is changed to `author: Author!`, a `null` from the resolver turns the entire `Book` into `null` because `book` is nullable. If `book: Book!`, the error continues propagating up to `data`.

This is especially important when a nested field calls another service. A non-existent author can be a valid state if the relationship is optional; if the schema marks `Author!`, the server must guarantee the relationship always exists and the resolver cannot return `null`.

## Null and security

There are cases where an API intentionally avoids revealing whether a resource exists. For example, a user does not have permission to view an order. Depending on security policy, the server may return `null` for a nullable field so non-existence and unauthorized access look indistinguishable, or return a GraphQL error with an appropriate code.

This decision must be consistent and enforced across every access path. Never rely solely on returning `null` to protect data: resolvers must still verify permissions before returning sensitive objects or fields. A client could query the same object through another field if the server does not enforce authorization everywhere.

If you choose to return `null` to hide existence, consider server-side logging and monitoring so operations teams can still distinguish denied access from non-existent resources. Never include sensitive details in GraphQL error messages.

## Testing null results with GraphQlTester

`GraphQlTester` lets you assert that a field returns `null` without errors:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
            }
        }
        """)
    .variable("id", "missing-book")
    .execute()
    .path("bookById")
    .valueIsNull();
~~~

To test a non-null field violating nullability, verify both the GraphQL error and the field path:

~~~java
graphQlTester.document("""
        query {
            requiredBook(id: "missing-book") {
                id
            }
        }
        """)
    .execute()
    .errors()
    .satisfy(errors -> {
        // Verify there is an execution error at the requiredBook field.
    });
~~~

In a complete test, also assert the response path or error classification matching how the API maps exceptions. Do not merely assert that some error exists, because syntax errors or setup mistakes could also make such a test pass for the wrong reason.

Tests should cover:

1. Nullable object resolver returning `null` and response having a `null` field with no errors.
2. Non-null object resolver returning `null` and response containing an execution error.
3. Nullable child field returning `null` while the parent object remains present.
4. Non-null child field returning `null` and the error propagating up to the nullable boundary.
5. Empty list returning `[]`.
6. List with a `null` element violating `[Book!]` and triggering null propagation.
7. `Mono.empty()` with both nullable and non-null fields.
8. `Flux.empty()` with list fields.
9. Service exceptions mapped to errors matching the contract.
10. Sensitive fields still checking permissions even when the response may return `null`.

## Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Field returns null and client thinks server failed | Contract does not clearly describe the meaning of null | Define semantics and document nullable fields |
| Cannot return null for non-nullable field | Resolver or data source returns null for a field marked `!` | Fix data/logic or change nullability if the contract permits |
| Entire parent object turns into null | Non-null child field returns null and null propagation bubbles up | Review nullability at each level and error paths |
| Collection query returns null when no records exist | Service returns null instead of an empty collection | Return `List.of()` or `Flux.empty()` as appropriate |
| `Mono.empty()` causes an error | Schema field is non-null yet publisher emits no value | Use a nullable field or emit a valid value |
| All service errors turn into null | Exceptions converted to empty/null too early | Preserve error signals and map GraphQL errors |
| List with a null element breaks the entire list | Element violates `Book!` inside the list | Clean up data or adjust nullability to match semantics |
| Sensitive data exposed via another field | Only hiding field on the client or in one resolver | Enforce server-side authorization across every access path |

## Comprehensive practice

Build a library API with these fields:

1. `bookById(id: ID!): Book` returns `null` when the book is not found.
2. `requiredBook(id: ID!): Book!` raises a business error when not found.
3. `booksByAuthor(authorId: ID!): [Book!]!` returns an empty list if there are no books.
4. `Book.author: Author` is an optional relationship and can return `null`.
5. Try changing `Book.author` to `Author!` to observe null propagation.
6. Convert `bookById` to `Mono<Book>` and test `Mono.empty()`.
7. Convert `booksByAuthor` to `Flux<Book>` and test `Flux.empty()`.
8. Write `GraphQlTester` tests for null results, execution errors, empty lists, and non-null child fields.

After the exercise, describe the response for each case and identify the null boundary where the error stops. Explain why database errors should not be converted to `Mono.empty()` and why lists with zero elements should normally return `[]`.

## Key takeaways

Null results are part of the GraphQL contract. Nullable fields can return `null` without producing errors; non-null fields returning `null` produce execution errors and propagate `null` up to the nearest nullable boundary. For lists, distinguish a null list, an empty list, and null elements. In Spring for GraphQL, Java `null` and `Mono.empty()` represent the absence of a single value; `Flux.empty()` in a collection query yields an empty list, while a subscription `Flux` is an event stream. Choose nullability based on data invariants, distinguish not found from system errors, enforce field authorization on the server, and test both responses and errors with `GraphQlTester`.
