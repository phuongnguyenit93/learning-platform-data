# @QueryMapping for Query Fields

In Spring for GraphQL, **@QueryMapping** connects a Java method in a controller to a field on the root object type Query of a GraphQL schema. When a client calls that field in a query operation, Spring routes the field resolution to the corresponding method, binds the arguments, and uses the method's return value to build the response.

This annotation lets you write GraphQL controllers in a familiar Spring style while keeping the SDL schema as the API contract. This lesson covers how to declare mappings, accept arguments, return objects or lists, handle asynchronous results, organize services, handle errors, and test Query fields.

## 1. What is @QueryMapping?

A GraphQL schema declares the root type Query for data-reading operations:

~~~graphql
type Query {
    book(id: ID!): Book
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
}
~~~

The schema describes two fields that clients can call:

- `book` takes an `id` argument and returns a Book or null.
- `books` takes no arguments and returns a non-null list of Book, where each element is also non-null.

In Spring for GraphQL, you can write the controller as:

~~~java
@Controller
public class BookQueryController {

    @QueryMapping
    public Book book(@Argument("id") String id) {
        // Find book by id
        return bookService.findById(id);
    }

    @QueryMapping
    public List<Book> books() {
        // Get list of books
        return bookService.findAll();
    }
}
~~~

`@QueryMapping` is a specialized annotation for fields on the root Query. At its core, it is a shorthand for `@SchemaMapping(typeName = "Query")`.

When Spring discovers the method, Spring registers it as a DataFetcher for the corresponding field. GraphQL Java invokes the DataFetcher when executing an operation that selects this field.

### Distinguishing Between Schema and Mapping

Both parts must be declared in sync:

| Component | Role |
| --- | --- |
| SDL `type Query` | Exposes the field, arguments, and return type to clients. |
| `@QueryMapping` | Connects a Query field to the Java method that handles it. |
| `@Argument` | Extracts the field argument and binds it to the method parameter. |
| Service | Executes business logic and accesses data. |

`@QueryMapping` does not automatically create a new field in the schema. If a controller has a `@QueryMapping` method named `book` but the schema does not declare `Query.book`, the application may fail when building the GraphQL runtime or the mapping will not be bound to a valid field. Declare the SDL and the controller against the same contract.

## 2. Creating a Complete Query Field

Suppose an application manages a book catalog. SDL schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    description: String
}
~~~

A Java record representing the data:

~~~java
package com.example.catalog.book;

public record Book(
        String id,
        String title,
        String description
) {
}
~~~

Service:

~~~java
package com.example.catalog.book;

import org.springframework.stereotype.Service;

@Service
public class BookService {

    public Book findById(String id) {
        // Replace with repository query in a real application.
        if ("book-42".equals(id)) {
            return new Book(
                    "book-42",
                    "Spring in Action",
                    "A practical guide to Spring"
            );
        }
        return null;
    }
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

Client sends the operation:

~~~graphql
query BookDetail($id: ID!) {
    book(id: $id) {
        id
        title
        description
    }
}
~~~

Variables:

~~~json
{
    "id": "book-42"
}
~~~

Response:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring in Action",
            "description": "A practical guide to Spring"
        }
    }
}
~~~

The processing flow occurs as follows:

1. The client sends the query document and variables to the GraphQL endpoint.
2. GraphQL Java validates the operation against the schema.
3. The GraphQL engine executes the `Query.book` field.
4. Spring invokes the `book` method annotated with `@QueryMapping`.
5. `@Argument("id")` provides the value `book-42` to the Java parameter.
6. The controller calls the service and returns the Book.
7. The GraphQL engine resolves the `id`, `title`, and `description` fields selected by the client.
8. The transport returns the GraphQL response to the client.

## 3. Field and Method Naming Conventions

By default, Spring uses the method name as the field name if the annotation does not specify a different name.

~~~graphql
type Query {
    recentBooks: [Book!]!
}
~~~

~~~java
@QueryMapping
public List<Book> recentBooks() {
    return bookService.findRecent();
}
~~~

The `recentBooks` method is mapped to `Query.recentBooks`.

If the Java method name differs from the SDL field name, use the `name` attribute:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

~~~java
@QueryMapping(name = "book")
public Book findBookById(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

In this example, the method name is `findBookById`, while the GraphQL field is `book`. The `name` attribute makes the mapping explicit.

GraphQL field names typically use lower camelCase. Keep field names consistent across the SDL, client operations, and controllers. GraphQL is case-sensitive, so `recentBooks` and `recentbooks` are two different names.

### When the Root Query Has a Different Name

By default convention, the root query type is named `Query`. `@QueryMapping` is designed to map to this type.

If the schema intentionally names the root type differently, for example:

~~~graphql
schema {
    query: CatalogQuery
}

type CatalogQuery {
    book(id: ID!): Book
}
~~~

you can use `@SchemaMapping` with the custom type name:

~~~java
@SchemaMapping(typeName = "CatalogQuery", field = "book")
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

For standard schemas, keep the root type named Query and use `@QueryMapping` so the controller clearly expresses that it handles a root read operation.

## 4. Receiving Arguments with @Argument

Arguments are declared in the SDL and bound to method parameters using `@Argument`.

Schema:

~~~graphql
type Query {
    book(id: ID!): Book
    booksByAuthor(authorId: ID!): [Book!]!
}
~~~

Controller:

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}

@QueryMapping
public List<Book> booksByAuthor(
        @Argument("authorId") String authorId) {
    return bookService.findByAuthorId(authorId);
}
~~~

The name passed to `@Argument` must match the argument in the SDL. Explicitly specifying the argument name prevents the code from depending on whether Java parameter names are preserved at compile time.

You can omit the name in the annotation when the application's parameter name discovery mechanism is properly configured:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

In code for large projects or when explicit mapping is preferred, writing `@Argument("id")` is usually easier to read.

### Multiple Arguments on a Field

Schema:

~~~graphql
type Query {
    books(
        keyword: String
        limit: Int = 20
        offset: Int = 0
    ): [Book!]!
}
~~~

Controller:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("keyword") String keyword,
        @Argument("limit") Integer limit,
        @Argument("offset") Integer offset) {
    return bookService.search(keyword, limit, offset);
}
~~~

Default values in the SDL are applied by GraphQL when an argument is omitted. However, `limit` and `offset` still need to be validated in the business layer. The `Int` type does not automatically enforce positive values or a maximum result count.

For example, the service can normalize the bounds:

~~~java
public List<Book> search(String keyword, Integer limit, Integer offset) {
    int safeLimit = limit == null ? 20 : Math.min(Math.max(limit, 1), 100);
    int safeOffset = offset == null ? 0 : Math.max(offset, 0);

    return bookRepository.search(keyword, safeLimit, safeOffset);
}
~~~

Specific limits depend on application requirements. Never trust that the client will always pass valid values just because the argument has an integer type.

## 5. Binding Input Objects to Method Parameters

When a Query has multiple filter criteria, use an input object to group the input data.

SDL:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input BookFilterInput {
    keyword: String
    genre: BookGenre
    authorId: ID
}

type Query {
    books(filter: BookFilterInput): [Book!]!
}
~~~

Java DTO:

~~~java
package com.example.catalog.book;

public record BookFilterInput(
        String keyword,
        BookGenre genre,
        String authorId
) {
}
~~~

Controller:

~~~java
@QueryMapping
public List<Book> books(@Argument("filter") BookFilterInput filter) {
    return bookService.search(filter);
}
~~~

Client sends:

~~~graphql
query SearchBooks($filter: BookFilterInput) {
    books(filter: $filter) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "keyword": "Spring",
        "genre": "TECHNOLOGY"
    }
}
~~~

Spring for GraphQL binds the input object according to the schema structure to the corresponding Java class or record. The field names and data types of the DTO must be compatible with the SDL. If the schema uses an enum, a corresponding Java enum keeps business code from having to handle arbitrary strings.

For input objects with nested fields, declare nested DTOs following the same structure. Test binding when fields are omitted, passed as null, or use a default value, especially for update operations.

## 6. Return Values of @QueryMapping

A `@QueryMapping` method can return many forms of data, as long as it matches the field type in the schema and is supported by Spring for GraphQL.

### Returning an Object

SDL:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Java:

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

If the book is not found, the method can return null because the `Book` return type is nullable.

If the schema declares `Book!`, the resolver must return a non-null object. If the method returns null or throws an error, GraphQL applies non-null propagation rules and may cause the parent field to become null.

### Returning a List

SDL:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

Java:

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

The schema `[Book!]!` makes two guarantees:

- The list field cannot be null.
- Each element in the list cannot be null.

An empty list is still valid. If there are no books, return an empty collection instead of null to uphold the contract.

### Returning a Scalar or Enum

Not every Query field returns an object:

~~~graphql
type Query {
    totalBooks: Int!
    isCatalogEmpty: Boolean!
    currentGenre: BookGenre
}
~~~

~~~java
@QueryMapping
public Integer totalBooks() {
    return bookService.count();
}

@QueryMapping
public Boolean isCatalogEmpty() {
    return bookService.count() == 0;
}

@QueryMapping
public BookGenre currentGenre() {
    return BookGenre.TECHNOLOGY;
}
~~~

Scalars and enums are leaf types, so the client selects them directly without a child selection set.

### Returning Asynchronous Types

Spring for GraphQL supports asynchronous result types such as `CompletionStage` and supported reactive types.

Example with `CompletableFuture`:

~~~java
@QueryMapping
public CompletableFuture<Book> book(@Argument("id") String id) {
    return CompletableFuture.supplyAsync(
            () -> bookService.findById(id),
            bookExecutor
    );
}
~~~

Reactive example with `Mono`:

~~~java
@QueryMapping
public Mono<Book> book(@Argument("id") String id) {
    return bookService.findByIdReactive(id);
}
~~~

The return type should fit the application's architecture. Avoid creating ad-hoc thread pools or using the default `supplyAsync` for every resolver without managing executors, resource limits, and task lifecycles. If the service already supports reactive programming, keeping the reactive pipeline end-to-end is generally easier to control.

## 7. Separating Controllers and Services

A GraphQL controller should focus on receiving arguments, invoking business logic, and returning results. The service is responsible for business rules and data access.

Example:

~~~java
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

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
~~~

Some organizational principles:

- Use constructor injection to declare dependencies explicitly.
- Do not put SQL queries or lengthy business logic in controllers.
- Use DTOs/input objects when arguments are structured.
- Return objects matching the schema's output types.
- Keep method and field names meaningful.
- Reuse services between GraphQL controllers and other adapters if the business logic is the same.

This organization allows testing controllers and services independently. When changing transports or adding another API adapter, the business logic remains intact in the service.

## 8. Query Fields Should Preserve Read Semantics

The root Query is used for reading data. A query may be called multiple times, cached, or executed in parallel depending on the client and server. Therefore, a Query resolver should not produce side effects such as creating orders, updating state, or deleting data.

For example, renaming a book should be a Mutation:

~~~graphql
type Mutation {
    renameBook(id: ID!, title: String!): Book!
}
~~~

Do not place write operations into Query just for the convenience of calling the method. Separating Query and Mutation helps clients, caches, and security systems understand the exact intent of an operation.

A Query may write logs, record metrics, or read data from external sources. However, these activities should not alter business state in ways the client does not expect.

## 9. Handling Not-Found Data

With the schema:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

the `book` field is nullable. If the service provides a method returning `Optional<Book>`, the resolver can convert a not-found result to null:

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findOptionalById(id).orElse(null);
}
~~~

In this example, `findOptionalById` has return type `Optional<Book>`. If the service directly returns `Book` as in the earlier example, the controller can return that result without calling `orElse`.

Response when not found:

~~~json
{
    "data": {
        "book": null
    }
}
~~~

If the schema declares `Book!`, you cannot normally return null. When not found, choose a representation that fits the API contract, such as returning a GraphQL error via an exception handler or designing a result type with an explicit status.

Do not arbitrarily change schema nullability just to mask a data error. The decision between nullable and non-null must be based on business semantics and how clients need to handle missing results.

## 10. Handling Exceptions from Query Resolvers

When a service or repository throws an exception, the GraphQL engine records the error in the `errors` section of the response. You can use Spring for GraphQL's exception resolver mechanism to translate exceptions into GraphQL errors with appropriate details.

Example using `@GraphQlExceptionHandler` in a controller advice:

~~~java
@ControllerAdvice
public class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Book not found")
                .errorType(ErrorType.NOT_FOUND)
                .build();
    }
}
~~~

This example illustrates mapping a business exception to a GraphQL error. In a real project, import the corresponding GraphQL/Spring APIs and choose error types, extensions, or error codes according to your application conventions.

Do not expose stack traces, SQL, table names, or internal details in the message sent to clients. Log full details on the server with an appropriate correlation ID; the response should only contain information the client needs to handle the error.

Also distinguish between data-not-found errors and system errors. Do not convert every exception into NOT_FOUND because doing so hides database connection errors, timeouts, or bugs in resolvers.

## 11. Securing Query Fields

Just because a client can call a field in the schema does not mean every user is authorized to read the data that field returns.

You can protect Queries with Spring Security method security if the application has enabled the corresponding configuration:

~~~java
@QueryMapping
@PreAuthorize("hasAuthority('BOOK_READ')")
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

In addition to general access permissions on the field, the service needs to check permissions on specific resources. For example, a user may have permission to read books but only be allowed to view books belonging to their own tenant.

Some principles:

- Authenticate users before executing operations according to application policy.
- Check permissions at the field or service level when data has access control.
- Do not trust a `userId`, `tenantId`, or owner ID passed by the client to decide their own permissions.
- Do not rely on hiding fields in the UI as a security measure.
- Avoid leaking sensitive information through GraphQL errors.

Authorization should rely on a trusted server-side security context. If a Query returns an object with sensitive child fields, protect those child fields as well, even when calling the root Query is already permitted.

## 12. Testing @QueryMapping with GraphQlTester

Spring for GraphQL provides `GraphQlTester` to test operations without manually sending HTTP requests.

Test example:

~~~java
@GraphQlTest(BookQueryController.class)
class BookQueryControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

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
}
~~~

This is an example of a test slice structure. If the controller depends on BookService, provide a mock or test bean for that dependency according to your project's Spring Boot version. With `@GraphQlTest`, the goal is to verify the GraphQL schema and mappings without starting the full HTTP server.

You should test the following cases:

- Valid queries return the expected data.
- Arguments are bound with the right name and type.
- Input objects are bound with the right structure.
- Missing data returns null or an error per the contract.
- Non-null fields do not accept null.
- Exceptions are converted into GraphQL errors following conventions.
- Unauthorized users are denied access.
- Queries do not invoke services unnecessarily when a field is not selected.

For HTTP integration tests, use `@SpringBootTest` and a GraphQL tester bound to an HTTP client to additionally verify the endpoint, serialization, security filters, and transport.

## 13. Common Errors When Using @QueryMapping

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Field is not mapped | Method name or `name` attribute does not match SDL field. | Check `@QueryMapping(name = "...")` and `type Query`. |
| Method is not detected by Spring | Class lacks `@Controller` or is outside component scan. | Register the controller in a scanned package. |
| Argument receives null | `@Argument` name does not match SDL or client did not pass a value. | Verify argument name, type, and variables. |
| Input object fails to bind | DTO is incompatible with the SDL input structure. | Check field names, Java types, and nested objects. |
| Resolver returning null causes error | SDL declares a non-null field but the method returns null. | Adjust the contract or handle missing data properly. |
| Query returns empty response | Operation does not select fields, mapping is wrong, or resolver returns null. | Check the operation, schema, and service result. |
| Application reports conflicting mappings | The same field is registered across multiple controllers or runtime wirings. | Assign a single resolver per field. |
| Slow query | Service queries data inefficiently or nested resolvers cause N+1. | Measure timing and query counts, and consider DataLoader/batching. |
| Internal error leaked to client | Exception message is returned directly. | Use an exception resolver and safe messages. |

When debugging, check in order: does the SDL have the Query field, is the controller scanned by Spring, does the method map to the right name, do arguments bind properly, and then check the service and return value. If the root field runs properly but the response is wrong in child fields, check the mappings of the child types separately.

## 14. Workflow for Implementing a Query Field

When adding a new Query field, you can follow this sequence:

1. Identify the data to read and the business rules.
2. Declare the field in `type Query` with the appropriate arguments and return type.
3. Choose nullability based on the case where data does not exist.
4. Create or use a service to access the data.
5. Write a `@Controller` and a `@QueryMapping` method.
6. Bind arguments with `@Argument`, preferring explicit names when needed.
7. Check input bounds, access permissions, and exception handling.
8. Write `GraphQlTester` tests for both success and error cases.
9. Verify the operation through the HTTP endpoint in integration tests when needed.
10. Measure queries if the field returns a list or triggers nested resolvers.

## 15. Key Takeaways

- `@QueryMapping` maps a Java method to a field of the root Query type.
- This annotation is a shorthand for `@SchemaMapping(typeName = "Query")`.
- The method name defaults to the field name; use `name` if the two names differ.
- `@Argument` binds an argument from the SDL to a Java parameter; the name must match the schema.
- It can accept scalars, enums, and input objects, and return objects, lists, scalars, or supported asynchronous results.
- Nullability in the SDL must match the values the method can return.
- Controllers should call services rather than containing complex data access logic.
- Queries are for reading data and should avoid business side effects.
- Exceptions, authorization, and query limits must be handled on the server.
- Use `GraphQlTester` to verify the schema, mappings, arguments, and responses.

`@QueryMapping` is the direct bridge between the root Query in a GraphQL schema and the data-reading logic of a Spring application. When the schema is clearly designed, arguments are bound accurately, and controllers coordinate cleanly with services, Query fields become easy to develop, test, and maintain.
