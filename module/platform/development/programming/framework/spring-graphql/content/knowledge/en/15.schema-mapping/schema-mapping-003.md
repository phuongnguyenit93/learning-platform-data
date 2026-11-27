# Mapping fields of nested types

## Objectives

After this lesson, you will be able to:

- Explain how GraphQL executes nested fields on a parent object.
- Distinguish the default property-reading mechanism from a resolver declared with `@SchemaMapping`.
- Map a nested field with `@SchemaMapping` and specify `typeName` and `field` properly.
- Receive the source object using a regular Java parameter or `@Source`.
- Bind arguments of a nested field using `@Argument`.
- Resolve fields returning an object, a list, or a computed value.
- Handle differences between a Java DTO and a GraphQL object type.
- Recognize when `@BatchMapping` or DataLoader is needed to avoid N+1.
- Test nested mapping with `GraphQlTester` and diagnose common issues.

## 1. What is a nested field in GraphQL?

GraphQL allows a field to return an object or a list of objects. The client can continue selecting child fields on the returned object. Those child fields are called nested fields.

Example schema:

~~~graphql
type Author {
    id: ID!
    name: String!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}

type Book {
    id: ID!
    title: String!
    author: Author
    reviews: [Review!]!
}

type Query {
    book(id: ID!): Book
}
~~~

A client can fetch a book, its author, and its reviews in the same operation:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
        author {
            id
            name
        }
        reviews {
            id
            rating
            comment
        }
    }
}
~~~

The operation has one root field, `Query.book`. The result of this field is a `Book` object. GraphQL continues resolving the selected fields inside that object:

- `Book.id` and `Book.title` read data from the book object.
- `Book.author` returns an `Author` object.
- `Author.id` and `Author.name` are resolved on the author object.
- `Book.reviews` returns a list of `Review` objects.
- `Review.id`, `Review.rating`, and `Review.comment` are resolved on each review.

GraphQL does not require the client to call a separate endpoint for each nested field. The runtime follows the operation's selection set and resolves each field on its corresponding parent object.

## 2. Source object and nested field resolution

When GraphQL resolves a field on an object, the runtime has a source value called the **source object**. For a nested field, the source object is typically the parent object on which the field is selected.

For example, after `Query.book` returns a Java `Book` object, the runtime uses that object as the source when resolving `Book.author`.

You can visualize the processing flow:

~~~mermaid
flowchart TD
    A["Query.book(id)"] --> B["Book source object"]
    B --> C["Resolve Book.title"]
    B --> D["Resolve Book.author"]
    B --> E["Resolve Book.reviews"]
    D --> F["Author source object"]
    F --> G["Resolve Author.name"]
    E --> H["Review source objects"]
    H --> I["Resolve Review.rating / comment"]
~~~

A `@SchemaMapping` method for a nested field receives the corresponding source object. For example, a method handling `Book.author` receives a `Book` and returns an `Author`.

~~~java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Here:

- `Book` is the source object.
- `author` is the field being resolved.
- `Author` is the return value for that field.

The source object does not have to be a database entity. It can be a DTO, projection, record, `Map`, or another Java type returned by the preceding resolver.

## 3. Default property mapping and when `@SchemaMapping` is needed

Not every nested field needs a controller method. GraphQL Java can read values from the source object via the default property data fetching mechanism.

Example Java bean:

~~~java
public class Book {

    private String id;
    private String title;
    private Author author;

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Author getAuthor() {
        return author;
    }
}
~~~

With the schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

If the `Query.book` resolver returns a `Book` that has an `author` property, GraphQL can retrieve that value through the property accessor without a separate `@SchemaMapping` method.

Property mapping is appropriate when:

- The field value is already available on the source object.
- Reading the data is simply a matter of accessing a property.
- No separate service or repository call is needed.
- No additional logic needs to be applied for the field.

Use `@SchemaMapping` when the field needs custom behavior, such as:

- Loading a relationship from a service or repository.
- Computing a value based on multiple properties.
- Applying business rules.
- Receiving client-supplied arguments.
- Calling another data source or returning an asynchronous result.

A mapping method registered for a field provides the `DataFetcher` that handles that field. Avoid having both property logic and a separate resolver backed by two different data sources without a clear intention.

## 4. Mapping a nested field with `@SchemaMapping`

`@SchemaMapping` is the Spring for GraphQL annotation used to bind a controller method to a field of a GraphQL object type.

You can specify both the type and the field explicitly:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

The two main attributes:

| Attribute | Meaning |
| --- | --- |
| `typeName` | Name of the GraphQL object type containing the field |
| `field` | Name of the field within that object type |

In the example above, the resulting mapping is `Book.author`.

The names in the annotation must match the SDL. `Book` here is the GraphQL type name, whereas `Book` in the Java parameter is the source class. The two names may be identical, but they belong to two different naming systems.

### 4.1. Inferring `field` from the method name

If the method name matches the field name, you can omit `field`:

~~~java
@SchemaMapping(typeName = "Book")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Spring infers the field as `author` from the method name. If the method name differs from the field name in the SDL, specify it explicitly:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author loadBookAuthor(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

### 4.2. Inferring `typeName` from the source parameter

When `typeName` is omitted, Spring for GraphQL can infer the GraphQL type name from the Java type of the source parameter.

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

If the source parameter is Java `Book`, Spring infers `typeName` as `Book` by default. The method name `author` is used as the field name.

This shorthand is concise when the Java source class and the GraphQL object type share the same name. If you use a DTO such as `BookView` while the GraphQL type is still named `Book`, you must declare `typeName` explicitly. Inferring `typeName` from the source type is covered in detail in its dedicated lesson in the Annotated Controller chapter.

## 5. Receiving the source object with `@Source`

In an annotated controller, the source parameter is usually received directly by its Java type:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

You can use `@Source` to explicitly mark the source parameter:

~~~java
import org.springframework.graphql.data.method.annotation.Source;

@SchemaMapping(typeName = "Book", field = "author")
public Author author(@Source Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

`@Source` is useful when a method has multiple parameters and you want to clarify which parameter represents the parent object. Other parameters can be bound from arguments or retrieved from the GraphQL context.

For example, a nested field accepts an additional `locale` argument:

~~~graphql
type Book {
    id: ID!
    title: String!
    localizedTitle(locale: String!): String
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book")
public String localizedTitle(
        @Source Book book,
        @Argument("locale") String locale) {

    return translationService.translate(book.getTitle(), locale);
}
~~~

In this example, `book` is the source object and `locale` is the argument of the `localizedTitle` field. Do not confuse an argument with a property of the parent object: `locale` is passed by the client in the operation, whereas `book` is provided by the GraphQL runtime as the source.

## 6. Mapping a field returning a related object

A common nested field represents a relationship between two objects, such as a book having an author.

SDL:

~~~graphql
type Author {
    id: ID!
    name: String!
}

type Book {
    id: ID!
    title: String!
    author: Author!
}

type Query {
    book(id: ID!): Book
}
~~~

Java model:

~~~java
public class Book {

    private final String id;
    private final String title;
    private final String authorId;

    public Book(String id, String title, String authorId) {
        this.id = id;
        this.title = title;
        this.authorId = authorId;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getAuthorId() {
        return authorId;
    }
}
~~~

Controller:

~~~java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

When the client selects `author`, GraphQL passes the corresponding `Book` into the method. The method reads `authorId`, calls the service, and returns an `Author`. GraphQL then continues resolving the child fields of `Author`, such as `id` and `name`.

You do not need to manually build a JSON response for the nested object. Simply return the Java object; the GraphQL runtime will continue processing that object's selection set.

## 7. Mapping a field returning a list of objects

A nested field can return a list, such as the reviews of a book:

~~~graphql
type Review {
    id: ID!
    rating: Int!
    comment: String
}

type Book {
    id: ID!
    title: String!
    reviews: [Review!]!
}
~~~

Resolver:

~~~java
@Controller
class BookReviewController {

    private final ReviewService reviewService;

    BookReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.getId());
    }
}
~~~

GraphQL invokes the resolver for each `Book` source present in the selection set. Each invocation returns the list of `Review` items for the corresponding book.

The client can select fields on each review:

~~~graphql
query {
    book(id: "book-42") {
        title
        reviews {
            rating
            comment
        }
    }
}
~~~

The Java return type must be compatible with the GraphQL field type. If the SDL declares `[Review!]!`, the resolver should return a non-null list containing no null elements. When there are no reviews, returning an empty list is usually more appropriate than returning `null`.

## 8. Mapping computed fields

A nested field does not have to map directly to a database column or property. You can use a resolver to compute a value from the source object.

Example SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    displayLabel: String!
    isLongTitle: Boolean!
}
~~~

Resolver:

~~~java
@Controller
class BookComputedFieldController {

    @SchemaMapping(typeName = "Book")
    public String displayLabel(Book book) {
        return book.getTitle() + " (" + book.getId() + ")";
    }

    @SchemaMapping(typeName = "Book")
    public boolean isLongTitle(Book book) {
        return book.getTitle().length() > 40;
    }
}
~~~

The method name determines the default field name. If you want to make the mapping explicit, you can declare `field`:

~~~java
@SchemaMapping(typeName = "Book", field = "isLongTitle")
public boolean calculateLongTitle(Book book) {
    return book.getTitle().length() > 40;
}
~~~

+## 9. Arguments of nested fields

A nested field can accept arguments just like a root field. For example, a book query can request a limited number of reviews:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}
~~~

Client:

~~~graphql
query {
    book(id: "book-42") {
        reviews(first: 5) {
            id
            rating
        }
    }
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        @Source Book book,
        @Argument("first") Integer first) {

    int limit = first != null ? first : 10;
    return reviewService.findByBookId(book.getId(), limit);
}
~~~

`@Argument("first")` binds the `first` argument value of the `Book.reviews` field. `@Source` provides the `Book` object being resolved.

If the SDL declares a default value, GraphQL applies the default when the client omits the argument. In the Java example, the fallback value simply illustrates defensive handling at the application layer; keep defaults consistent between the schema and the service to avoid having two different rules.

For nullable arguments, define clearly what omitting the argument versus passing `null` means. If you need to distinguish those two states in a mutation or filter, use the binding type supported by your version of Spring for GraphQL.

## 10. Using a DTO or projection for the nested source

The Java class representing the source object does not have to match the GraphQL type name or a database entity.

Example DTO:

~~~java
public record BookView(
        String id,
        String title,
        String authorId) {
}
~~~

SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
}
~~~

If the resolver uses `BookView` as its source, specify the GraphQL type explicitly:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(BookView book) {
    return authorService.findById(book.authorId());
}
~~~

If you omit `typeName`, Spring may infer it from the Java source class name `BookView`, while the schema uses `Book`. As a result, the mapping will not match.

Using DTOs helps decouple the GraphQL contract from persistence entities. However, keep type and field mappings consistent, especially when a single DTO is used across multiple GraphQL types or multiple nested fields.

## 11. Multiple nested fields in the same controller

A controller can contain multiple resolvers for the same GraphQL type. You can place `@SchemaMapping(typeName = "...")` at the class level to set a default type:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
class BookFieldsController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    BookFieldsController(
            AuthorService authorService,
            ReviewService reviewService) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.getId());
    }

    @SchemaMapping
    public String displayLabel(Book book) {
        return book.getTitle() + " (" + book.getId() + ")";
    }
}
~~~

The methods map respectively to:

- `Book.author`
- `Book.reviews`
- `Book.displayLabel`

If a method handles a different type, you can override it at the method level:

~~~java
@SchemaMapping(typeName = "Author", field = "books")
public List<Book> books(Author author) {
    return bookService.findByAuthorId(author.getId());
}
~~~

Organize controllers by GraphQL type groups so readers can easily identify the source and fields. When a controller handles several different types, declaring `typeName` explicitly on the method helps avoid confusion.

## 12. Nested fields and the N+1 risk

A nested resolver can be invoked many times within a single operation. If each invocation calls a repository individually, the application may generate N+1 queries.

For example, a client requests a list of books and the author of each book:

~~~graphql
query {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

If `Query.books` returns 50 books, the `Book.author` resolver may be called 50 times. If each `authorService.findById` call executes a database query, the application may run one query to fetch the list of books plus 50 queries for authors.

You can start with a simple resolver when data volume is small or relationships are already loaded. When the number of sources grows, use batch loading.

### 12.1. Using `@BatchMapping` for same-type relationships

Example:

~~~java
@Controller
class BookBatchController {

    private final AuthorService authorService;

    BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsByBooks(books);
    }
}
~~~

Instead of loading the author separately for each book, Spring groups the `Book` sources into a batch. The service can query authors by the list of `authorId` values and return a map from each source book to its author.

`@BatchMapping` is one way to declare a batch resolver for a nested field. For a field already handled by `@BatchMapping`, do not register another `@SchemaMapping` for that same field without a clear reason.

### 12.2. When to use DataLoader?

DataLoader is suitable when you need explicit control over batching and per-request caching, or when multiple fields need to load the same kind of data.

Whether using `@SchemaMapping`, `@BatchMapping`, or DataLoader, follow these principles:

- Batch queries by a set of IDs instead of querying repeatedly per source.
- Preserve order or map results accurately to their corresponding keys.
- Handle keys with no matching data.
- Scope caching appropriately, typically to the request.
- Measure query counts and execution time to identify actual bottlenecks.

Do not add batch loading just because a field is nested. Determine whether repeated queries actually occur, then choose the appropriate optimization.

## 13. Nullability and errors when resolving nested fields

The return type in the SDL determines how GraphQL handles `null`.

Example:

~~~graphql
type Book {
    author: Author
    reviews: [Review!]!
}
~~~

- `author: Author` can return `null` if the book has no author or the resolver finds no relationship according to business rules.
- `reviews: [Review!]!` requires a non-null list with no null elements. When there are no reviews, return `[]`.
- If a non-null field returns `null` or raises an execution error, GraphQL applies null propagation up to the nearest nullable parent field.

A resolver should have clear rules:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findOptionalById(book.getAuthorId())
            .orElse(null);
}
~~~

This example is only appropriate if the schema allows `author` to be nullable. If the schema declares `author: Author!`, returning `null` will produce an execution error and may cause parent-level data to be lost.

When a service throws an exception, use `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler` to map the error to an appropriate GraphQL error. Do not hide infrastructure errors by returning `null` if that misleads the client into thinking the data simply does not exist.

## 14. Testing nested field mapping

Test through real GraphQL operations to verify that the schema, root resolver, and nested resolvers work together.

Example operation:

~~~graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
        reviews {
            rating
        }
    }
}
~~~

With `GraphQlTester`:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                title
                author {
                    name
                }
                reviews {
                    rating
                }
            }
        }
        """)
        .execute();

response.path("book.author.name")
        .entity(String.class)
        .isEqualTo("An Nguyen");

response.path("book.reviews[0].rating")
        .entity(Integer.class)
        .isEqualTo(5);
~~~

Tests should cover:

- Nested fields read directly from default properties.
- Nested fields resolved via `@SchemaMapping`.
- Source object passed properly into the method.
- Arguments of nested fields bound properly.
- Fields returning objects or lists conforming to the SDL.
- Source objects that are DTOs with names different from the GraphQL type.
- Missing relationships handled according to nullability.
- Batch resolvers returning correct results for multiple source objects.
- Service errors translated into GraphQL errors according to application policy.

If you only test Java methods with unit tests, you may miss errors in `typeName`, field names, or runtime wiring. At least one integration test using `GraphQlTester` should verify the mapping at the GraphQL level.

## 15. Common issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Nested field returns null even though the service has data | Incorrect type or field mapping, or property is not read properly | Check the SDL, `typeName`, `field`, and source object |
| `@SchemaMapping` method is never called | Type/field name mismatch or controller is not managed by Spring | Check the annotation and `@Controller` |
| Field is read from an old property instead of the service | Method mapping not registered properly or checking the wrong field | Confirm the actual `DataFetcher` bound to the field |
| Source parameter receives the wrong object | Method signature or source mapping does not match | Check Java types and use `@Source` explicitly |
| Nested field argument is always null | Argument not declared in the SDL or `@Argument` name is wrong | Cross-check the schema and operation |
| DTO fails to map to the GraphQL type | DTO name differs from the object type name | Declare `typeName` explicitly |
| List of nested fields triggers many queries | Resolver calls the service individually per source | Use `@BatchMapping` or DataLoader |
| Resolver returning null causes the entire parent object to disappear | Field is declared non-null | Adjust nullability or handle errors properly |
| Field exists in the schema but has no data | Missing matching property or `DataFetcher` | Add a property resolver or `@SchemaMapping` |

## 16. Workflow for implementing nested field mapping

When adding a nested field, you can follow this sequence:

1. **Identify the GraphQL parent type.** Which object type owns the field?
2. **Identify the field and return type.** Does the field return a scalar, object, or list?
3. **Inspect the source object.** What Java type does the root resolver return?
4. **Check default property mapping.** If the data is already present, can the property fetcher satisfy it?
5. **Write `@SchemaMapping` when custom logic is needed.** Specify `typeName` and `field` explicitly if Java names differ from the SDL.
6. **Receive source and arguments.** Use a source parameter or `@Source`, and bind arguments with `@Argument`.
7. **Handle nullability.** Ensure the return value aligns with `!` markers in the SDL.
8. **Evaluate query count.** If the resolver is called repeatedly per source, consider `@BatchMapping` or DataLoader.
9. **Test the operation.** Use `GraphQlTester` to verify fields, arguments, objects, and lists.
10. **Monitor performance and errors.** Measure database queries, resolver duration, and GraphQL error paths.

## 17. Summary

A nested field is a field selected inside an object returned by a parent field. The GraphQL runtime uses the parent object as the source to resolve child fields. When the value already exists on a Java bean or `Map`, the default property mapping mechanism can satisfy it without a dedicated controller method.

When you need to call a service, compute values, or accept arguments, use `@SchemaMapping` to map a method to a field of a GraphQL object type. The source parameter represents the parent object; `@Source` can make that role clearer, while `@Argument` binds data sent by the client to the nested field. For DTOs whose names differ from the GraphQL type, declare `typeName` explicitly. If a nested resolver causes repeated queries, use `@BatchMapping` or DataLoader. Testing with actual GraphQL operations confirms that all mappings work properly against the schema and data.

