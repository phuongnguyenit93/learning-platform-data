# type Query

In GraphQL SDL, **type Query** declares the root object type for read operations in the API. The fields defined inside this type are the entry points clients can invoke when sending a query operation. Each field describes the operation name, its input arguments, and its return data type.

In Spring for GraphQL, the SDL schema serves as the API contract, while Java methods are mapped to Query fields using annotations such as `@QueryMapping`. Understanding how to design `type Query` makes the API easy to discover, strongly typed, easy to test, and allows server-side query cost control.

## 1. Role of the root Query type

A GraphQL schema has three root operation types:

- **Query** is used to read data.
- **Mutation** is used to modify data state.
- **Subscription** is used to receive events or results emitted over time.

In SDL, the root query type is typically named `Query`:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Here:

- `type` declares an object type.
- `Query` is the object type name serving as the root for query operations.
- `book` is a field that clients can request.
- `id: ID!` is a required argument of the field.
- `Book` is the result type. Because there is no `!`, the field can return `null`.

When no `schema` block is declared, GraphQL uses the object type named `Query` as the query root. Therefore, with this common naming convention, a separate `schema` block is not needed.

The name `Query` is GraphQL's default convention, not a mandatory keyword in every schema. If you want to use a different name, you must declare the root operation explicitly:

~~~graphql
schema {
    query: CatalogQuery
}

type CatalogQuery {
    book(id: ID!): Book
}
~~~

The root query type must be an object type. It cannot be a scalar, enum, input object, or list. The object type must also have at least one valid field that clients can query.

### Distinguishing between type Query and a query operation

These two concepts are related but belong to different parts of GraphQL:

| Concept | Meaning |
| --- | --- |
| `type Query` | Defines the fields that the server provides as entry points for read operations. |
| `query` | Keyword used in an operation document sent by the client to request execution of a read operation. |

Schema example:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Client operation example:

~~~graphql
query BookDetail($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

The schema defines the capabilities of the API. The operation selects a subset of those capabilities and specifies the fields the client wants to receive.

## 2. Declaring fields in type Query

A field in an object type has the general structure:

~~~graphql
fieldName(argumentName: ArgumentType): ReturnType
~~~

Example:

~~~graphql
type Query {
    book(id: ID!): Book
    books: [Book!]!
    totalBooks: Int!
}
~~~

`type Query` can contain multiple fields. Each field is an independent entry point in the schema:

- `book` finds a book by ID.
- `books` returns a list of books.
- `totalBooks` returns the number of books.

Field names typically use lower camelCase, such as `bookById`, `recentBooks`, `totalBooks`. Type names use PascalCase, such as `Book`, `Author`, `BookFilter`. Consistent naming makes the schema easier to read and use in GraphQL tools.

A field can return a scalar, enum, object, interface, union, or a list of valid types. If a field returns an object, the client must specify a selection set for that object. If a field returns a scalar or enum, the client does not add a nested selection set.

Example:

~~~graphql
type Query {
    bookTitle(id: ID!): String
    book(id: ID!): Book
}
~~~

Operation:

~~~graphql
query {
    bookTitle(id: "book-42")
    book(id: "book-42") {
        id
        title
    }
}
~~~

The `bookTitle` field returns the `String` scalar, whereas the `book` field returns the `Book` object, so the operation must select subfields of `Book`.

## 3. Return types and nullability

The return type defines the shape of data a field can provide. GraphQL has built-in scalars:

| Scalar | Meaning |
| --- | --- |
| `Int` | Signed 32-bit integer. |
| `Float` | Floating-point number. |
| `String` | Character string. |
| `Boolean` | True or false value. |
| `ID` | Identifier; typically serialized as a string. |

Besides scalars, a field can return application-defined object types:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
}
~~~

### What does the ! mark mean?

By default, fields and list elements can hold `null`. Adding `!` after a data type means the value at that position is not allowed to be `null`.

For a single field:

~~~graphql
type Query {
    book(id: ID!): Book
    requiredBook(id: ID!): Book!
}
~~~

- `Book` allows the resolver to return `null`, for example when a book is not found.
- `Book!` guarantees the resolver must return a valid `Book`. If the result is `null`, GraphQL raises an execution error and applies null propagation rules.

The `!` mark on an argument has the same meaning, applied to input:

~~~graphql
type Query {
    book(id: ID!): Book
    books(keyword: String): [Book!]!
}
~~~

`id: ID!` requires the client to supply a non-`null` value. `keyword: String` is optional and may be omitted or receive `null`.

### List nullability

There are four common declarations:

| SDL Type | Meaning |
| --- | --- |
| `[Book]` | The list may be `null`; individual elements may also be `null`. |
| `[Book!]` | The list may be `null`; elements cannot be `null`. |
| `[Book]!` | The list cannot be `null`; individual elements may be `null`. |
| `[Book!]!` | The list cannot be `null`; no elements can be `null`. |

Example:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

The `books` field guarantees it will always return a list. The list may be empty, but it cannot be `null` and cannot contain `null` elements.

Choose nullability based on the business contract. If failing to find a book by ID is a normal case, `book(id: ID!): Book` may be appropriate. If a list endpoint always returns a collection, even an empty one, `[Book!]!` usually expresses that intent more clearly.

When a non-null field fails and cannot produce a value, GraphQL cannot substitute `null` for that field itself. The `null` propagates up to the nearest nullable parent field; if all fields along the propagation path are non-null, `data` at the root can become `null`. Therefore, do not add `!` just to make the schema look stricter if the actual data cannot uphold that guarantee.

## 4. Declaring arguments for Query fields

Arguments allow clients to pass criteria to a field. Example:

~~~graphql
type Query {
    book(id: ID!): Book
    booksByAuthor(authorId: ID!): [Book!]!
}
~~~

A client can call:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }

    booksByAuthor(authorId: "author-7") {
        id
        title
    }
}
~~~

Arguments are declared inside parentheses after the field name. Each argument has a name and a data type. A field can have multiple arguments:

~~~graphql
type Query {
    books(
        keyword: String
        genre: BookGenre
        limit: Int = 20
        offset: Int = 0
    ): [Book!]!
}
~~~

In this example:

- `keyword` and `genre` are optional.
- `limit` defaults to 20 if omitted by the client.
- `offset` defaults to 0.
- The client can pass some or all arguments.

Default values in SDL are only used when the argument is not provided. If the client sends an explicit `null` for a nullable argument, that value remains `null` and does not automatically fall back to the default. This is an important distinction to keep in mind when designing APIs.

### Using input objects for filters

When a field has many search criteria, you can group them into an input object to keep requests readable and the schema extensible:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input BookFilter {
    keyword: String
    genre: BookGenre
    authorId: ID
}

type Query {
    books(filter: BookFilter, limit: Int = 20, offset: Int = 0): [Book!]!
}
~~~

Operation:

~~~graphql
query SearchBooks($filter: BookFilter, $limit: Int, $offset: Int) {
    books(filter: $filter, limit: $limit, offset: $offset) {
        id
        title
        genre
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "keyword": "Spring",
        "genre": "TECHNOLOGY"
    },
    "limit": 10,
    "offset": 0
}
~~~

Input objects avoid cluttering a field with too many separate arguments. They also create a reusable input type across fields. Note that an input object can only contain valid input types such as scalars, enums, and other input objects; do not use an output object like `Book` as the type of an input field.

## 5. A complete Query schema

The following example combines single fields, lists, filters, enums, and nested objects:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input BookFilter {
    keyword: String
    genre: BookGenre
    authorId: ID
}

type Author {
    id: ID!
    name: String!
}

type Book {
    id: ID!
    title: String!
    genre: BookGenre!
    author: Author
}

type Query {
    book(id: ID!): Book
    books(
        filter: BookFilter
        limit: Int = 20
        offset: Int = 0
    ): [Book!]!
    totalBooks(filter: BookFilter): Int!
}
~~~

You can read the schema by group:

- `BookGenre` restricts book genres to the published values.
- `BookFilter` describes search criteria.
- `Author` and `Book` are output object types.
- `Query.book` finds a book by ID.
- `Query.books` finds a list of books with filtering and pagination.
- `Query.totalBooks` returns the total number of books matching the filter.

Clients can invoke multiple fields in the same query:

~~~graphql
query CatalogOverview($filter: BookFilter) {
    books(filter: $filter, limit: 5) {
        id
        title
        author {
            id
            name
        }
    }

    totalBooks(filter: $filter)
}
~~~

The response structure mirrors the selected fields:

~~~json
{
    "data": {
        "books": [
            {
                "id": "book-42",
                "title": "Spring in Action",
                "author": {
                    "id": "author-7",
                    "name": "Lan"
                }
            }
        ],
        "totalBooks": 1
    }
}
~~~

Keys in `data` correspond to the field names or aliases chosen by the client. Clients can select only the fields they need without receiving every property of an object.

### Aliases when calling the same field multiple times

If you need to call the same field with different arguments within one operation, use aliases to name the results:

~~~graphql
query CompareBooks {
    first: book(id: "book-42") {
        id
        title
    }

    second: book(id: "book-99") {
        id
        title
    }
}
~~~

The response will contain two keys, `first` and `second`. Aliases avoid field name collisions in the result and clearly express the intent of each call.

## 6. Mapping type Query in Spring for GraphQL

After defining the schema, the application must provide resolvers for fields on the root `Query`. Spring for GraphQL supports `@QueryMapping` to map a controller method to a `Query` field of the same name.

With the schema:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Controller:

~~~java
package com.example.catalog.graphql;

import com.example.catalog.book.Book;
import com.example.catalog.book.BookService;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

Key points:

- `@Controller` registers the class with the Spring container.
- `@QueryMapping` defaults to mapping the `book` method to the `Query.book` field.
- `@Argument("id")` retrieves the argument named `id` in the schema.
- The method's return value is used by the GraphQL engine to populate the field in the response.

The GraphQL `ID` scalar is commonly received in Java as a `String`. For other scalar types, Spring converts input values to the corresponding Java types according to the configured conversion mechanism.

If the Java method name differs from the field name in the schema, specify the mapping name explicitly:

~~~java
@QueryMapping(name = "books")
public List<Book> findCatalogBooks() {
    return bookService.findAll();
}
~~~

If the Java parameter name differs from the argument name, specify the argument name in the annotation:

~~~java
@QueryMapping
public Book bookById(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

Explicitly specifying names makes mappings easier to read and avoids relying on parameter names being preserved during Java compilation.

### Mapping multiple arguments and input objects

For a field with multiple arguments:

~~~graphql
type Query {
    books(keyword: String, limit: Int = 20): [Book!]!
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("keyword") String keyword,
        @Argument("limit") Integer limit) {
    return bookService.search(keyword, limit);
}
~~~

For an input object, you can map it to an appropriate Java class or record:

~~~java
public record BookFilter(String keyword, BookGenre genre, String authorId) {
}
~~~

~~~java
@QueryMapping
public List<Book> books(
        @Argument("filter") BookFilter filter,
        @Argument("limit") Integer limit,
        @Argument("offset") Integer offset) {
    return bookService.search(filter, limit, offset);
}
~~~

The names and types of input properties must be compatible with the input object in SDL. In larger systems, verify how enums, IDs, dates/times, and project custom types are converted.

## 7. Resolving nested fields from Query results

Fields on `Query` often return an object or a list of objects. When a client selects subfields, GraphQL continues resolving fields on those objects.

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
~~~

If the returned `Book` object already has `id` and `title` properties, GraphQL can read those values via property access. If the author needs to be queried separately, you can use `@SchemaMapping`:

~~~java
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
~~~

Here `@QueryMapping` handles the root field `Query.book`, while `@SchemaMapping` handles `Book.author`. Separating these two responsibilities lets the `Query` resolver focus on finding the book, while the `Book` resolver handles fetching the author.

If a `Query` returns a list of many `Book` items and each `author` resolver queries the database individually, the application can suffer from the N+1 problem. You can use `DataLoader` or `@BatchMapping` to batch author lookups together. `Query` design should consider how child fields are resolved, because a single operation can trigger many server-side data accesses.

## 8. Extending Query when a schema is split across multiple files

In large modules, a schema can be split into multiple files by domain or feature. Once the root type is declared, other files can add fields using `extend type Query`:

File `catalog.graphqls`:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

File `author.graphqls`:

~~~graphql
extend type Query {
    author(id: ID!): Author
}
~~~

`extend type Query` extends an existing object type. It does not create a second root `Query` type. Therefore, the schema must have a base definition before extensions are merged. All schema resources must also be loaded into the same GraphQL schema runtime.

In Spring Boot, SDL files are typically placed under `src/main/resources/graphql/`. They can be organized into subdirectories, and `spring.graphql.schema.locations` can be configured if you need to change search locations. On startup, check schema parsing logs if a new field does not appear in the API.

Do not declare duplicate fields with the same name across multiple schema parts. If two modules need the same field name with different meanings, unify the API contract or use domain-specific names.

## 9. Designing an easy-to-use and safe Query

A good `type Query` clearly communicates each field's purpose and bounds how clients can query data.

**Name fields by behavior and domain.** Use `book`, `books`, `booksByAuthor`, or `searchBooks` when they accurately express the functionality. Avoid overly generic names like `getData` or names tied to repository implementation details.

**Use strongly typed arguments.** Use `ID` for identifiers, enums for finite value sets, and input objects for multi-attribute filters. Only mark inputs non-null when they are genuinely required.

**Design nullability around real data.** If a record might not exist, a nullable return field is usually appropriate. If a list always exists, return an empty list rather than `null`.

**Set limits on list queries.** SDL can declare `limit` and `offset`, yet resolvers must still enforce maximum bounds, reject negative values, and bound query cost. Never blindly trust values sent by clients.

**Keep Query free of side effects.** `Query` is for reading data. Operations that mutate state should be declared on the root `Mutation` type so clients, caches, and infrastructure understand the operation's semantics.

**Control query depth and cost.** A query can request deeply nested fields or invoke expensive fields. In production environments, consider depth limits, complexity limits, timeouts, list size bounds, and field-level access control.

## 10. Common errors when declaring type Query

| Symptom | Common cause | How to check |
| --- | --- | --- |
| Schema has no query root | Missing `type Query` or missing `schema { query: ... }` when using a custom root name. | Inspect root operation types in SDL. |
| Query reports field not found | The field name in the operation does not exist in `Query`, or the extension schema was not loaded. | Cross-check field names and `extend type Query` files. |
| Object field reports missing selection set | Client requested an object without selecting any subfields. | Add a selection set for the object field. |
| Scalar reports selection set not allowed | Client added curly braces after a scalar or enum. | Select scalar and enum fields directly without braces. |
| Missing required argument | Argument is declared non-null, but the client omitted a value. | Check `!` modifiers, operation variables, and request variables. |
| Resolver receives `null` | Argument name mismatch or the input value is actually null. | Check `@Argument`, SDL argument names, and variables. |
| Field unexpectedly returns `null` | Resolver found no data or the return type is nullable. | Check service results and field nullability. |
| List query is too slow | Unbounded results, repeated queries for nested fields, or missing indexes. | Check pagination, DataLoader, query counts, and database execution plans. |

When debugging in Spring for GraphQL, first verify the loaded schema, then verify `@QueryMapping` mappings, argument names, and service return values. If the root field works correctly but child fields are slow or failing, inspect `@SchemaMapping` resolvers and the corresponding DataLoader strategy.

## 11. Testing Query

You can use `GraphQlTester` to test the schema and resolvers without sending real HTTP requests:

~~~java
@Test
void returnsBookById() {
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
~~~

You should test key scenarios:

- Queries with valid arguments return the expected data.
- Missing records return nullable results as specified by the contract.
- Missing non-null arguments are rejected before resolver execution.
- Filters and pagination handle boundary values properly.
- Nested fields return accurate data without generating unexpected numbers of queries.
- Unauthorized users cannot read protected fields.

Schema tests catch contract errors early. Resolver tests verify data access logic. Integration tests verify the entire flow from request to response.

## 12. Key takeaways

- `type Query` is the root object type for read operations in GraphQL.
- Each field declares arguments and a return type; object fields require a selection set when queried by clients.
- The `!` mark enforces non-nullability, applied independently to arguments, fields, and list elements.
- Input objects and enums help model structured filters.
- Spring for GraphQL maps root fields with `@QueryMapping`; nested fields can use `@SchemaMapping` or `@BatchMapping`.
- You can extend the root `Query` across multiple SDL files using `extend type Query`.
- `Query` design must account for pagination, nullability, access control, and server-side query cost.

`type Query` is the entry point for reading data in a GraphQL API. When fields, arguments, and return types are properly designed, clients can fetch the exact data they need, while the Spring for GraphQL application gains a clear contract for implementing, testing, and optimizing resolvers.
