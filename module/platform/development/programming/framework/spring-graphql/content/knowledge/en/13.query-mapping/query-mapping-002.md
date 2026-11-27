# Queries Returning an Object

In GraphQL, a query field can return an object type instead of only returning a scalar such as `String`, `Int`, or `Boolean`. This design allows clients to fetch an object along with the required child fields in a single operation, such as retrieving a book together with its author, genre, and publication details.

With Spring for GraphQL, a method annotated with `@QueryMapping` can return a Java object. The GraphQL runtime then processes that object's selection set: simple fields can be read from the object's properties, while fields requiring custom logic can be mapped with `@SchemaMapping` or a batch loading mechanism.

## 1. Declaring an Object Type and Query Field in SDL

Suppose a library application needs to look up a book by ID. The schema can declare:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    description: String
    publishedYear: Int
}
```

Here:

- `Query.book` is a field on the root query type that takes an `id` argument and returns a `Book`.
- `Book` is an object type describing the fields that clients can select.
- `Book` has no `!` on the return type, so the `book` field is allowed to return `null`, for example when no book is found.
- `id` and `title` are non-null, meaning a valid `Book` object must provide both fields.
- `description` and `publishedYear` may be null.

An object type is an output type. It is used to describe data returned by the server, not as an argument type or a field type inside an input object. If clients need to send object-shaped data, declare a separate `input` type.

## 2. Clients Must Select Object Fields

Unlike scalars, object types require a selection set specifying which child fields to retrieve. The following query is invalid because `book` returns a `Book` without a selection set:

```graphql
query {
    book(id: "book-42")
}
```

Valid query:

```graphql
query {
    book(id: "book-42") {
        id
        title
        publishedYear
    }
}
```

Clients can select fewer or more fields depending on their needs. If a screen only needs the title, the query can be shorter:

```graphql
query {
    book(id: "book-42") {
        title
    }
}
```

The schema stays the same. Clients adjust the selection set without requiring the server to create a separate endpoint response for each screen.

## 3. Mapping a Query Returning an Object with @QueryMapping

Spring for GraphQL uses `@QueryMapping` to map a controller method to a field of the same name on the root `Query` type. For example, with the SDL above:

```java
package com.example.graphql.book;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

The `book` method is mapped to `Query.book`. The `@Argument("id")` annotation extracts the `id` argument value from the GraphQL field. The method returns a Java `Book` object; Spring for GraphQL passes that result to GraphQL execution to continue resolving the fields selected by the client.

If the method name differs from the field name in the SDL, specify the name explicitly:

```java
@QueryMapping(name = "book")
public Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Argument names must match the schema. Explicitly specifying the name in `@Argument` is good practice when you do not want the code to depend on parameter name metadata being preserved by the compiler.

## 4. Defining a Java Object Matching the GraphQL Type

A Java object can supply the data for a GraphQL object type. For example, using a Java record:

```java
public record Book(
    String id,
    String title,
    String description,
    Integer publishedYear
) {}
```

GraphQL Java can read properties from the source object through the default property data fetcher. For records, accessors such as `id()` and `title()` provide the corresponding values; for JavaBeans, getters such as `getId()` and `getTitle()` are typically used.

Source property names should correspond to the GraphQL field names or be mapped with a dedicated resolver. For example, `publishedYear` in the SDL can be read from the `publishedYear` property of a record or the `getPublishedYear()` getter of a JavaBean.

The Java class name does not have to match the GraphQL type name, though consistent naming makes the code easier to read. If the persistence model differs in structure from the API contract, map it to an appropriate DTO or projection rather than coupling the GraphQL schema directly to database entities.

## 5. How Does GraphQL Process the Returned Object?

When `@QueryMapping` returns a `Book` object, the GraphQL runtime does not automatically turn the object into JSON by serializing every property. Instead, the runtime executes the selection set requested by the client.

For example, the client sends:

```graphql
query BookDetail($id: ID!) {
    book(id: $id) {
        id
        title
        description
    }
}
```

Variables:

```json
{
  "id": "book-42"
}
```

High-level processing flow:

```mermaid
flowchart TD
    A[Client sends query and variables] --> B[GraphQL selects Query.book]
    B --> C[@QueryMapping invokes BookController.book]
    C --> D[BookService finds Book]
    D --> E[Return Book object]
    E --> F[Resolve id field]
    E --> G[Resolve title field]
    E --> H[Resolve description field]
    F --> I[Assemble response per selection set]
    G --> I
    H --> I
    I --> J[Return GraphQL response]
```

Example response:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL in Practice",
      "description": "Building GraphQL APIs with Spring."
    }
  }
}
```

If the client selects only `id` and `title`, GraphQL includes only those two fields in the response. However, returning only a subset of fields does not guarantee that the repository queries only those columns; optimizing database queries based on the selection set requires designing dedicated projections or data access logic.

## 6. Queries Returning Objects with Nested Fields

An object type can contain fields that are other object types. For example, a book has an author:

```graphql
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
    biography: String
}
```

The client can fetch the book and author in the same operation:

```graphql
query BookDetail($id: ID!) {
    book(id: $id) {
        id
        title
        author {
            id
            name
        }
    }
}
```

If the returned `Book` object already has an `author` property containing an `Author` object, the default property data fetcher can read that property. You do not need to write a resolver for every field if the data is already present and property access is sufficient.

When a field needs custom logic—for example, `Book` only has `authorId` and must call a service to load the author—use `@SchemaMapping`:

```java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
```

The `Book book` parameter is the source object returned by the parent resolver. `@SchemaMapping` registers how to resolve the `Book.author` field from that object.

## 7. Queries Returning Objects with a List of Child Objects

An object can contain a list of other objects. For example, an author has many books:

```graphql
type Query {
    author(id: ID!): Author
}

type Author {
    id: ID!
    name: String!
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
}
```

Query:

```graphql
query AuthorDetail($id: ID!) {
    author(id: $id) {
        id
        name
        books {
            id
            title
        }
    }
}
```

The `[Book!]!` type means the `books` field always returns a non-null list and every element in the list is also non-null. An empty list `[]` is valid if the author has no books yet.

If the number of elements can be large, design pagination using arguments or connection types. Returning an entire unbounded collection can produce oversized responses and increase query time and memory usage.

## 8. Nullability and Object-Not-Found Cases

Nullability in the SDL defines what the server guarantees to the client.

| SDL | Meaning |
| --- | --- |
| `book: Book` | Field may return a Book or null |
| `book: Book!` | Field must return a non-null Book |
| `books: [Book]` | List may be null and elements may also be null |
| `books: [Book!]` | List may be null, elements cannot be null |
| `books: [Book!]!` | List and every element cannot be null |

For lookup-by-ID queries, there are usually two contract options:

1. Declare `book: Book` and return null when not found. The client checks `data.book`.
2. Declare `book: Book!` and throw a business exception when not found, then map the error to an appropriate GraphQL error.

Do not declare a field as non-null and then silently return null. If a non-null field returns null or throws an error, GraphQL produces an execution error and propagates null up to the nearest nullable parent field. If the error propagates to root `data`, the entire `data` may become null.

Example with `book: Book`:

```json
{
  "data": {
    "book": null
  }
}
```

If the service throws an exception, the response may contain `errors` alongside partial `data` depending on the error location and nullability. Standardize how not-found cases, validation failures, and system errors are represented so clients do not have to guess.

## 9. Using Optional and Asynchronous Return Types

Resolvers can return objects synchronously. Spring for GraphQL also supports many asynchronous and reactive result types.

Example using `CompletableFuture`:

```java
@QueryMapping
public CompletableFuture<Book> book(@Argument("id") String id) {
    return bookService.findByIdAsync(id);
}
```

In a reactive application, you can return `Mono<Book>` when using the corresponding stack and dependencies. Choose the return type according to how the service actually performs its work; wrapping a blocking call in `CompletableFuture` does not automatically turn it into non-blocking I/O.

If the service returns `Optional<Book>`, explicitly convert it at the controller or service boundary according to the nullability contract the API intends to offer—for example, `orElse(null)` for a nullable field or throwing a business exception to produce a standardized GraphQL error. Do not rely on a wrapper type without confirming it is supported by the adapter in use, and do not use `Optional` to mask system errors.

## 10. Distinguishing Query Resolvers and Field Resolvers

A single operation can trigger multiple resolvers:

- `@QueryMapping` resolves fields on the root `Query` type, such as `Query.book`.
- `@SchemaMapping` resolves fields on an object type, such as `Book.author`.
- The default property data fetcher reads fields from the source object when no matching custom resolver is registered.

Example query:

```graphql
query {
    book(id: "book-42") {
        id
        title
        author {
            name
        }
    }
}
```

`BookController.book` loads the book object. GraphQL then resolves `id`, `title`, and `author` on the `Book` object. If `author` requires separate service access, `BookFieldController.author` handles that field; `Author.name` continues to be resolved from the `Author` object or its corresponding resolver.

Separating resolvers per field keeps each part of the schema responsible for its own data. However, if each child field issues a separate database call for every parent object, the query can suffer from the N+1 problem.

## 11. Avoiding N+1 When Objects Have Data Relationships

Suppose a query returns 30 books and each book has an `author` field. If `@SchemaMapping` calls `authorService.findById()` once per book, the server may execute 30 author queries after loading the book list.

You can use `@BatchMapping` to group requests in batches:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findByBooks(books);
}
```

Or use `BatchLoaderRegistry`/DataLoader when finer-grained control over batch loading is required. A batch loader should return results mapped accurately to each key/source and handle missing related data explicitly.

One GraphQL HTTP request does not equate to one database query. When optimizing queries that return objects, measure the number of resolvers, database queries, service calls, response size, and overall latency.

## 12. Testing Queries Returning Objects with GraphQlTester

`GraphQlTester` lets you execute queries and inspect each path in the response. Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookController.class)
class BookControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void returnsBookObject() {
        graphQlTester.document("""
                query BookDetail($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """)
            .variable("id", "book-42")
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-42");
    }
}
```

This example assumes the test context provides a mock or test bean for `BookService` returning the book with ID `book-42`. You can also assert `book.title`, nested fields, not-found cases, and GraphQL errors.

Cases to test:

- Queries with valid and invalid selection sets.
- Valid, invalid, or non-existent ID arguments.
- Clients selecting different small and large sets of fields.
- Objects with child fields resolved by default and child fields using `@SchemaMapping`.
- Nullability of objects and nested fields.
- Empty object lists, populated lists, and pagination.
- Service exceptions and how errors propagate according to nullability.
- Batch loading when returning multiple related objects.

Slice tests focus on the GraphQL controller. When you need to verify that schema resources, auto-configuration, security, the database, and HTTP transport work together, add integration tests with the appropriate application context.

## 13. Common Errors When Queries Return Objects

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Query rejected for missing selection set | Field returns an object but the client did not select child fields | Add `{ ... }` with the required fields |
| `Unknown type` or schema mismatch | Object type is undeclared or type name is wrong | Check SDL and schema resources |
| Controller is not invoked | Method is not mapped or controller is not a Spring bean | Check `@Controller`, component scan, and `@QueryMapping` |
| Argument receives null | Argument name does not match SDL | Use explicit `@Argument("id")` |
| Child field returns null | Property does not exist, getter/accessor does not match, or resolver is wrong | Check the source object and field mapping |
| Non-null error propagates to parent object | Resolver returns null or throws an error on a non-null field | Adjust the nullability contract or handle errors properly |
| Slow query when fetching relationships | N+1 problem or loading too much data | Use batch loading, pagination, and query profiling |
| Response contains extra fields or sensitive data | Resolver returns an object with uncontrolled fields | Design appropriate schema, authorization, and DTOs |

## 14. Design Checklist for Queries Returning Objects

- Does the Query field return the right object type per the API contract?
- Does the client have a selection set matching the screen's needs?
- Do arguments and `@Argument` match in name, type, and nullability?
- Does the Java object/DTO expose properties matching the GraphQL fields?
- Is it clear whether nested fields use the property fetcher or `@SchemaMapping`?
- Is there an explicit null/error contract for when an object is not found?
- Does nullability of the object, child fields, and lists reflect actual data possibilities?
- Have data relationships been checked for N+1 risks?
- Do large lists have appropriate pagination and limits?
- Do tests cover object results, nested fields, nullability, and errors?

Queries returning objects are how GraphQL represents structured and relational data. `@QueryMapping` in Spring for GraphQL retrieves the root object, and then the runtime resolves each field in the selection set using the default property fetcher or registered resolvers. Good design aligns the SDL with DTOs, defines nullability clearly, handles nested fields intentionally, and keeps query costs under control. When done well, clients can fetch the exact data structure they need in a single operation while the server retains clean business logic and independent optimization capability.
