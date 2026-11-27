# `@QueryMapping` in Spring for GraphQL

`@QueryMapping` is a Spring for GraphQL annotation used to map a method in a Java controller to a field on the `Query` root of a GraphQL schema. When a client sends a query that selects that field, Spring invokes the corresponding method, retrieves the returned value, and lets GraphQL complete the response according to the client's selection set.

In a Spring for GraphQL API, the SDL defines the contract that clients are allowed to query; `@QueryMapping` connects a query field to the Java logic that executes it. This annotation lets you write resolvers in a controller style that integrates cleanly with services, dependency injection, argument handling, and testing.

## 1. What Does `@QueryMapping` Solve?

Consider the SDL schema:

```graphql
type Query {
    greeting: String!
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

The schema declares two fields on the query root:

- `greeting` takes no arguments and returns a non-`null` string.
- `bookById` takes a required `id` argument and returns a `Book` or `null`.

In Spring, you can write the controller:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    String greeting() {
        return "Hello from Spring for GraphQL";
    }

    @QueryMapping
    Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

`@QueryMapping` marks a method as a data fetcher for a field on the query root. The `greeting` method is mapped to `Query.greeting`, and `bookById` is mapped to `Query.bookById`.

When the client sends:

```graphql
query {
    bookById(id: "book-01") {
        id
        title
    }
}
```

Spring invokes `bookById`, passes the `id` argument value, and GraphQL uses the returned `Book` object to resolve `id` and `title`. Simple fields that already have properties on the object can be handled by the default property fetcher without writing additional resolvers.

## 2. Relationship Between `@QueryMapping` and SDL

`@QueryMapping` does not automatically create fields in the schema. The field must be declared in the SDL and the mapped name must match that field name.

For example, if the SDL declares:

```graphql
type Query {
    findBook(id: ID!): Book
}
```

then the Java method needs to map to `Query.findBook`. If you only write:

```java
@QueryMapping
Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Spring looks for the field using the method name `bookById`. Since the schema only has `findBook`, the mapping does not match. You can rename the method or specify the field name explicitly:

```java
@QueryMapping(name = "findBook")
Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

When no name is specified, Spring uses the method name as the field name. Use the `name` attribute when you want the Java method name to differ from the GraphQL name or when you want to declare the mapping explicitly.

`@QueryMapping` is a shorthand form of `@SchemaMapping(typeName = "Query")`. The two forms below serve the same purpose:

```java
@QueryMapping
Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

```java
@SchemaMapping(typeName = "Query", field = "bookById")
Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Normally you should use `@QueryMapping` for query root fields to clearly express intent. `@SchemaMapping` is more flexible when you need to map fields belonging to other object types, such as `Book.author`.

## 3. Receiving Arguments with `@Argument`

A query field can declare arguments in the SDL. Spring uses `@Argument` to extract the corresponding values from the request and convert them into suitable Java types.

SDL:

```graphql
type Query {
    booksByAuthor(authorId: ID!, limit: Int): [Book!]!
}
```

Controller:

```java
@QueryMapping
List<Book> booksByAuthor(
        @Argument("authorId") String authorId,
        @Argument("limit") Integer limit) {

    return bookService.findByAuthor(authorId, limit);
}
```

`authorId` is a required argument in the SDL, whereas `limit` may be omitted. Using `Integer` for an optional argument allows representing `null`; if the schema declares `Int!`, you can use a primitive Java type or wrapper depending on how your application handles default values.

### Using Explicit Argument Names

The argument name in the SDL does not have to match the Java parameter name. Pass the GraphQL name into `@Argument` to avoid relying on parameter names being retained in bytecode:

```java
@QueryMapping
Book book(@Argument("bookId") String id) {
    return bookService.findById(id);
}
```

With the schema:

```graphql
type Query {
    book(bookId: ID!): Book
}
```

Spring extracts the `bookId` argument and binds it to the Java parameter `id`.

### Receiving Input Objects

When a query has multiple filter conditions, you can group them into an input object:

```graphql
input BookFilter {
    keyword: String
    authorId: ID
    publishedAfter: String
}

type Query {
    searchBooks(filter: BookFilter!): [Book!]!
}
```

Java can use a record as the input type:

```java
public record BookFilter(
    String keyword,
    String authorId,
    String publishedAfter
) {}
```

```java
@QueryMapping
List<Book> searchBooks(@Argument("filter") BookFilter filter) {
    return bookService.search(filter);
}
```

Spring for GraphQL uses a binding mechanism to convert the input map into a Java object. Fields in the input object must have types compatible with the SDL. For complex input data, add validation for business rules such as keyword length limits or valid date ranges.

## 4. Return Types of Query Methods

The Java return type must be compatible with the type declared in the SDL. Some common examples:

| SDL | Common Java Type | Meaning |
|---|---|---|
| `greeting: String!` | `String` | Returns a string, must not be `null` upon successful execution. |
| `book: Book` | `Book` | Returns an object or `null`. |
| `books: [Book!]!` | `List<Book>` | Returns a list; elements must not be `null`. |
| `count: Int!` | `Integer` or `int` | Returns an integer. |

Example returning a list:

```java
@QueryMapping
List<Book> books() {
    return bookService.findAll();
}
```

If the SDL declares `[Book!]!`, the service should return an empty list when there are no books, rather than `null`. Returning `null` for a Non-null field causes GraphQL to emit an execution error and apply null propagation rules.

### Returning Asynchronous Results

Spring for GraphQL supports asynchronous return types such as `CompletableFuture` and Reactor `Mono`. This is useful when a service calls external systems or uses non-blocking APIs:

```java
@QueryMapping
CompletableFuture<Book> bookById(@Argument("id") String id) {
    return bookService.findByIdAsync(id);
}
```

Or with Reactor:

```java
@QueryMapping
Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findByIdReactive(id);
}
```

Asynchronous types allow GraphQL to wait for results without blocking the request thread while I/O is in progress. Choose return types consistently with the service's programming model and avoid calling blocking operations on schedulers meant for non-blocking tasks.

## 5. Separating Controllers and Services

Controllers should focus on receiving GraphQL requests, extracting arguments, and delegating to services. Business rules, repository access, and transactions should live in the appropriate layers.

Example:

```java
@Service
class BookService {

    private final BookRepository bookRepository;

    BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    Book findById(String id) {
        return bookRepository.findById(id).orElse(null);
    }
}
```

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

In this example, the `bookById` field is declared nullable (`Book` without `!`), so when a book is not found it can return `null`. If the SDL is changed to `Book!`, you must adjust the contract for missing data, such as throwing a business exception and mapping it to an appropriate GraphQL error.

## 6. Error Handling in `@QueryMapping`

When a resolver throws an exception, GraphQL returns a response containing an `errors` section. How exceptions are translated into information suitable for clients should be managed centrally, for example via `DataFetcherExceptionResolver` or the error-handling mechanism configured in Spring for GraphQL.

Do not return stack traces, SQL queries, connection details, or internal information in error messages. Distinguish business errors such as data not found from system errors such as an unavailable database, and map them to appropriate codes and messages.

Illustrative example where a resolver can throw a business exception:

```java
@QueryMapping
Book requiredBook(@Argument("id") String id) {
    Book book = bookService.findById(id);
    if (book == null) {
        throw new BookNotFoundException(id);
    }
    return book;
}
```

In this case, `BookNotFoundException` should be handled by an exception resolver to produce an appropriate `GraphQLError`. If the schema declares the field as Non-null, the error can also cause `null` to propagate up to parent fields according to the schema structure.

## 7. Security for Query Fields

Queries can return private data or data that only a specific group of users may view. You can combine Spring Security method security with controller methods:

```java
@Controller
class AccountController {

    @QueryMapping
    @PreAuthorize("hasRole('ADMIN')")
    List<Account> allAccounts() {
        return accountService.findAll();
    }
}
```

For `@PreAuthorize` to work, the application must enable method security with the appropriate configuration, such as `@EnableMethodSecurity`, and ensure the Spring Security dependency is configured. Checking permissions at the service layer can also be appropriate if the same business logic is invoked from multiple entry points.

Do not treat hiding fields from documentation or disabling introspection as a security measure. The server must enforce permissions on actual requests and avoid returning sensitive data to unauthorized users.

## 8. Distinguishing `@QueryMapping` from Other Mapping Annotations

Spring for GraphQL provides several annotations with different purposes:

| Annotation | Mapped Field | When to Use |
|---|---|---|
| `@QueryMapping` | Field on the query root | Reading data or executing queries. |
| `@MutationMapping` | Field on the mutation root | Creating, updating, or deleting data. |
| `@SubscriptionMapping` | Field on the subscription root | Providing a stream of events to clients. |
| `@SchemaMapping` | Field of any object type | Resolving nested fields, such as `Book.author`. |

Query root example:

```java
@QueryMapping
Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Mutation root example:

```java
@MutationMapping
Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
```

Nested field example:

```java
@SchemaMapping(typeName = "Book", field = "author")
Author author(Book book) {
    return authorService.findById(book.authorId());
}
```

Choose the annotation based on the field's position in the schema. `@QueryMapping` is not used to map `Book.author`, because that field belongs to the `Book` object type, not the query root.

## 9. Testing `@QueryMapping` with `GraphQlTester`

`@GraphQlTest` creates a test slice for Spring for GraphQL components, while `GraphQlTester` sends GraphQL documents and inspects responses. Services can be mocked to focus on testing the mapping and returned data.

```java
@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsBookById() {
        given(bookService.findById("book-01"))
            .willReturn(new Book("book-01", "GraphQL Basics"));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    bookById(id: "book-01") {
                        id
                        title
                    }
                }
                """)
            .execute();

        response.path("bookById.id").entity(String.class).isEqualTo("book-01");
        response.path("bookById.title").entity(String.class).isEqualTo("GraphQL Basics");
    }
}
```

This is an illustrative example; the imports, static import `given`, `Book` class, `BookService`, and SDL declaring `Query.bookById` and `Book` must be present in the test context. Depending on the Spring Boot version, the mock bean annotation may be `@MockitoBean` or `@MockBean`. The example checks both `id` and `title`; you can add verification to confirm the service was called with the expected ID.

### Cases Worth Testing

- Valid query field with valid arguments returning the expected data.
- Required argument missing or wrong type; GraphQL rejects the request before invoking the resolver.
- Nullable field when data is not found returns `null` according to contract.
- Non-null field encountering `null` or an exception; response contains `errors` and proper null propagation.
- Field name in `@QueryMapping` does not match SDL; check errors when building the schema or registering mappings.
- Unauthorized user access; verify sensitive data is not returned.

## 10. Common Mistakes

**Forgetting to declare the field in SDL.** `@QueryMapping` only registers a resolver for the field; it does not add the field to the schema. Declare the field in the query root.

**Method name does not match field name.** By default Spring uses the method name. If the names differ, rename the method or specify `@QueryMapping(name = "...")`.

**Binding the wrong argument.** The argument name in the SDL differs from the Java variable name. Use `@Argument("graphqlName")` to explicitly specify the name to bind.

**Using `@QueryMapping` for nested fields.** Use this annotation only for the query root. For fields belonging to an object type like `Book.author`, use `@SchemaMapping` or `@BatchMapping`.

**Mismatched nullability.** If the SDL declares `Book!` but the service can return `null`, the response will contain an execution error. Choose nullable or handle missing data according to the contract.

**Placing data access and complex business logic directly in controllers.** Moving logic into services improves testability, reuse, and transaction management.

**Skipping access checks.** Queries are data entry points; apply authorization per user and per business requirement.

## Conclusion

`@QueryMapping` connects Java controller methods to fields on the `Query` root of a GraphQL schema. Spring uses the method name as the field name by default, allows specifying a different name via `name`, and uses `@Argument` to bind data sent by clients. Keep your SDL and mappings consistent, return types aligned with nullability, separate business logic into services, protect queries with authorization, and test operations with `GraphQlTester`.
