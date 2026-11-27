# @SchemaMapping

In Spring for GraphQL, `@SchemaMapping` binds a method in a controller to a field in a GraphQL schema. When GraphQL Java needs to resolve that field, Spring invokes the corresponding method, passes the source object, arguments, and appropriate execution information, and then uses the returned value to continue building the response.

This annotation is especially useful for nested fields, such as `Book.author`, `Order.items`, or `Customer.address`. Root fields of `Query` are typically declared using `@QueryMapping`, whereas `@SchemaMapping` lets you handle fields on any appropriate object type or interface in the schema.

## 1. Role of @SchemaMapping

Suppose the schema declares:

```graphql
type Query {
    bookById(id: ID!): Book
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
```

The `Query.bookById` field fetches a single book. When a client also requests `Book.author`, the application needs to provide a way to retrieve the corresponding author. You can write the controller as follows:

```java
@Controller
public class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
```

`@QueryMapping` handles the root field `Query.bookById`. `@SchemaMapping` handles the `author` field on type `Book`. The `Book book` parameter is the source object returned by the parent field. From that object, the resolver obtains `authorId` and calls the service to find the author.

When the client sends:

```graphql
query {
    bookById(id: "book-01") {
        id
        title
        author {
            name
        }
    }
}
```

GraphQL executes `bookById`, then continues resolving `id`, `title`, and `author` according to the selection set. The `author` method is invoked only when the `author` field is selected in the operation.

## 2. How Spring Determines Type and Field

`@SchemaMapping` has two commonly used attributes:

| Attribute | Meaning |
| --- | --- |
| `typeName` | Name of the GraphQL parent type containing the field to map |
| `field` | Name of the GraphQL field to map |

If not specified explicitly, Spring can infer the field name from the method name and the parent type from the source parameter type. This convention keeps mappings concise:

```java
@Controller
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        // Spring infers the parent type is Book and the field is author.
        return authorService.findById(book.authorId());
    }
}
```

In this example:

- The method name `author` is used as the field name.
- The source parameter type `Book` is used to infer the parent type.
- `Book` is the Java object providing data for the child field.

When the Java class name differs from the GraphQL type name or you want an explicit mapping, specify the attributes:

```java
@SchemaMapping(typeName = "CatalogEntry", field = "primaryAuthor")
public Author resolvePrimaryAuthor(Book book) {
    return authorService.findById(book.authorId());
}
```

The `resolvePrimaryAuthor` method is mapped to the `CatalogEntry.primaryAuthor` field; the method name no longer determines the field name because `field` is explicitly declared. The source parameter is still `Book`, while the parent GraphQL type is specified as `CatalogEntry`.

Use the exact GraphQL type and field names as defined in the SDL. A mapping does not automatically create a new field in the schema. If `CatalogEntry.primaryAuthor` is not declared, writing the annotation will not allow queries to select that field.

## 3. Placing @SchemaMapping at the Class Level

When a controller contains multiple resolvers for the same parent type, you can place `@SchemaMapping(typeName = "Book")` at the class level. Methods inside only need to declare the field:

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookFieldController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookFieldController(
            AuthorService authorService,
            ReviewService reviewService) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}
```

Class-level mapping provides the default parent type for method mappings in the controller. Method-level `field` can override the field name inferred from the method name. This organization helps group resolvers by domain type and reduces repetition of `typeName`.

If a controller handles multiple parent types, you can specify `typeName` on individual methods rather than setting a shared value at the class level. Avoid creating multiple mapping methods for the same parent type and field pair, because Spring cannot unambiguously select a resolver when mappings conflict.

## 4. What Is a Source Object?

In GraphQL, a nested field is resolved based on the result of its parent field. That parent value is called the **source object**. For example, when `Query.bookById` returns a `Book`, the source object of `Book.author` is that `Book` instance.

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book source) {
    return authorService.findById(source.authorId());
}
```

Whether the variable is named `source` or `book` does not affect the mapping. Spring identifies the source parameter based on the parameter type and the argument resolution mechanism of annotated controllers. The source object is typically an unannotated parameter whose type corresponds to the object returned by the parent field.

A source object does not have to be a JPA entity. It can be a record, DTO, projection, domain object, or `Map`, as long as the data type fits the resolver and how GraphQL Java reads properties. You should return a clearly structured DTO or projection if persistence entities contain lots of internal data or hard-to-control lazy-loading relationships.

When no service is needed to retrieve a child field, GraphQL Java can use the default `PropertyDataFetcher` to read properties from the source object. Therefore, not every field needs `@SchemaMapping`.

## 5. Retrieving Arguments with @Argument

GraphQL fields can accept arguments. In a mapping method, use `@Argument` to retrieve the corresponding value:

```graphql
type Book {
    relatedBooks(limit: Int = 5): [Book!]!
}
```

```java
@SchemaMapping(typeName = "Book", field = "relatedBooks")
public List<Book> relatedBooks(
        Book book,
        @Argument("limit") Integer limit) {
    return bookService.findRelated(book.id(), limit);
}
```

`Book` is the source object; `limit` is the argument passed by the client. When the client omits `limit`, GraphQL applies the default value `5` from the schema before Spring passes the value to the method.

You can use `@Argument` with a DTO to receive an input object:

```graphql
input ReviewFilter {
    minRating: Int
    language: String
}

type Book {
    reviews(filter: ReviewFilter): [Review!]!
}
```

```java
public record ReviewFilter(Integer minRating, String language) {
}

@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("filter") ReviewFilter filter) {
    return reviewService.findByBook(book.id(), filter);
}
```

Spring converts arguments from GraphQL input into the corresponding Java types. The DTO type must fit the input structure and the application's binding/conversion capabilities. For simple arguments, you can bind directly to `String`, `Integer`, `Boolean`, `UUID`, or configured scalar types.

Specify the name explicitly in `@Argument("...")` when you want to avoid relying on preserving Java parameter name metadata during compilation. If you omit the name, Spring relies on parameter names discovered from bytecode or build configuration.

## 6. Additional Parameters in Resolvers

In addition to the source object and `@Argument`, annotated controllers can receive parameters supporting execution. For example, `DataFetchingEnvironment` allows reading field information, the selection set, context, and DataLoaders:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book, DataFetchingEnvironment environment) {
    boolean requestsName = environment.getSelectionSet().contains("name");
    return authorService.findById(book.authorId(), requestsName);
}
```

In this example, the resolver inspects the selection set to see whether the client requested the `name` field. This technique can help optimize projections at the data layer, but aliases, fragments, and nested fields must be handled properly; do not manually parse query strings with naive checks when you can use the selection set API.

Resolvers can also receive context or principal information via the argument resolvers supported by Spring for GraphQL. For example, when current user information is needed, you can receive `Principal` or use the corresponding context annotation. Regardless of how context is obtained, access permissions must still be enforced on the server for each protected field or service.

## 7. @SchemaMapping and Root Mapping Annotations

Spring for GraphQL provides specialized annotations for root operation types:

| Annotation | Equivalent Mapping | Used For |
| --- | --- | --- |
| `@QueryMapping` | `@SchemaMapping(typeName = "Query")` | Root fields of Query |
| `@MutationMapping` | `@SchemaMapping(typeName = "Mutation")` | Root fields of Mutation |
| `@SubscriptionMapping` | Field mapping for `Subscription` | Root fields of Subscription |
| `@SchemaMapping` | Inferred or specified parent type | Fields on any object/interface type |

Example:

```java
@Controller
public class BookRootController {

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @MutationMapping
    public Book renameBook(
            @Argument("id") String id,
            @Argument("title") String title) {
        return bookService.rename(id, title);
    }
}
```

Normally you should use the corresponding root annotation because it clearly expresses intent. Use `@SchemaMapping(typeName = "Query")` when you want a generic mapping configuration or need a uniform way of organizing resolvers.

## 8. Returning Synchronous, Asynchronous, and Reactive Results

A `@SchemaMapping` method can return a regular object:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
```

If the service runs asynchronously, it can return a `CompletableFuture` or `CompletionStage`:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(Book book) {
    return authorService.findByIdAsync(book.authorId());
}
```

For reactive applications, it can return `Mono` or `Flux`:

```java
@SchemaMapping(typeName = "Book", field = "reviews")
public Flux<Review> reviews(Book book) {
    return reviewService.streamByBookId(book.id());
}
```

Spring for GraphQL integrates asynchronous and Reactive Streams types so that GraphQL Java processes results appropriately for the operation. Choose the return type based on the processing model of your service and application stack. Do not wrap a blocking call in `Mono` and assume it automatically becomes non-blocking; ensure the underlying operations truly fit the reactive model or are scheduled on an appropriate scheduler.

If a resolver throws an exception or a future/reactive publisher emits an error, the error is routed into the application's GraphQL error-handling mechanism, such as `DataFetcherExceptionResolver`. Avoid returning internal details or sensitive stack traces in the response.

## 9. When Is @SchemaMapping Not Needed?

Suppose the source object has matching properties:

```java
public record Book(String id, String title, String subtitle) {
}
```

Schema:

```graphql
type Book {
    id: ID!
    title: String!
    subtitle: String
}
```

GraphQL Java can read `id`, `title`, and `subtitle` directly from the source object via `PropertyDataFetcher`. There is no need to write three `@SchemaMapping` methods just to return properties that already exist.

Write a dedicated mapping when a field needs to call a service/repository, compute a value, apply business logic, check permissions, combine multiple data sources, or use a DataLoader. If a mapping only returns `book.title()` with no additional logic, the default property fetcher is usually sufficient.

## 10. @SchemaMapping and the N+1 Problem

A nested field resolver can trigger many data queries. For example, a client fetches a list of 50 books along with `author`; if `Book.author` queries the database once per book, the request can generate one list query and 50 author queries.

`@SchemaMapping` does not automatically batch invocations. When optimization is needed, use `@BatchMapping` or DataLoader to group source objects and load data in batches. `@BatchMapping` fits common cases, while DataLoader allows fine-grained control over caching and batch keys.

Example:

```java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> authors(List<Book> books) {
        Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        Map<String, Author> byId = authorService.findAllByIds(authorIds);
        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            result.put(book, byId.get(book.authorId()));
        }
        return result;
    }
}
```

`@BatchMapping` replaces a single-item resolver for the corresponding field with a resolver that receives a list of source objects. If a field needs special per-source processing or has multiple batch keys, you can register a DataLoader via `BatchLoaderRegistry` and use it from the resolver. Always keep caches scoped per request to avoid sharing data across user requests.

## 11. Testing @SchemaMapping

`GraphQlTester` allows testing from a GraphQL client's perspective: sending an operation, passing variables, and asserting fields in the response. Example:

```java
graphQlTester.document("""
        query($id: ID!) {
            bookById(id: $id) {
                title
                author {
                    name
                }
            }
        }
        """)
    .variable("id", "book-01")
    .execute()
    .path("bookById.author.name")
    .entity(String.class)
    .isEqualTo("Ada Lovelace");
```

This test verifies the entire flow: the root query fetches `Book`, `@SchemaMapping` resolves `author`, and GraphQL reads the `name` field of `Author`.

You should add tests for the following cases:

- Source object is not found or the parent field returns `null`.
- Arguments have default values, are missing, or are invalid.
- The service throws an exception and the error is mapped to an appropriate GraphQL error.
- When a field is not selected, the resolver does not need to execute.
- Mappings for multiple parent types do not collide.
- Asynchronous or reactive resolvers handle errors and cancellation properly.

## 12. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Method is not invoked | `typeName` or `field` does not match SDL | Verify the exact parent type and field names |
| Spring reports duplicate mapping | Multiple methods registered for the same parent type/field | Merge resolvers or change mappings so each field has one clear handler |
| Incorrect source parameter | Parameter type does not correspond to the source object | Check the object returned by the parent field and the Java parameter type |
| `@Argument` unexpectedly receives null | Wrong argument name or client did not pass a value | Specify `@Argument("name")` explicitly and check defaults/nullability in SDL |
| Query selects field but response is null | Resolver returns null, source lacks property, or mapping is wrong | Check service, source object, and default property fetcher |
| Non-null propagation error | Resolver returns null for a field typed with `!` | Adjust data/resolver or SDL contract to match business rules |
| Too many queries for child field | Single-item resolver causes N+1 | Use `@BatchMapping` or DataLoader |
| Blocking resolver in reactive flow | Service performs blocking I/O on an inappropriate thread | Use a true reactive API or offload blocking work to an appropriate scheduler |

When diagnosing, check in order: does the field exist in the SDL, is the mapping registered under the right parent type and field, is the source object the right type, are arguments bound properly, and finally check the service and data. This approach helps distinguish schema mapping errors from business logic errors.

## 13. Principles for Organizing Annotated Controllers

Group resolvers by domain or parent type to keep controllers readable. Use class-level `@SchemaMapping` when multiple methods handle the same GraphQL type; use method-level `typeName` and `field` when explicit mapping is needed or the parent type differs from the Java class name. Keep resolvers thin, move business logic into services, and use `DataFetchingEnvironment` only when selection or context information is genuinely needed.

Do not create resolvers for every property that can already be read directly from the source object. When child fields access data across multiple sources or repeat queries, consider DataLoader. For sensitive fields, enforce permissions on the server and do not rely on whether the client selects the field.

`@SchemaMapping` is the bridge between fields in a GraphQL schema and Java methods. Understanding parent types, field names, source objects, argument binding, and data-fetching mechanics helps you build annotated controllers that are cleanly structured, easy to test, and well suited to Spring for GraphQL performance.
