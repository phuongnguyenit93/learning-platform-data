# Parent source object

## Objectives

After this lesson, you will be able to:

- Explain what a source object is during GraphQL field execution.
- Trace how a value returned from a parent field becomes the source for child fields.
- Receive the source object in a Spring for GraphQL `@SchemaMapping` method.
- Distinguish the source object from arguments, `GraphQLContext`, and local context.
- Know when GraphQL can read a property directly and when a separate resolver is needed.
- Map a source object when the Java class name differs from the GraphQL type.
- Handle null parent sources and avoid relying on shared mutable state.

## 1. What is a parent source object?

GraphQL queries typically have a nested structure. A field can return an object, and the client then selects child fields on that object.

For example, a client requests a book along with its author:

~~~graphql
query {
  book(id: "b-01") {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

The server executes the query following the field tree:

- The `Query.book` field finds and returns a `Book` object.
- The `Book.author` field uses the received `Book` object to find the `Author`.
- The `Author.name` field reads the name from the returned `Author` object.

In GraphQL Java, the object value passed from a parent field to the resolution of its child fields is called the *source object* or *parent source*. It is the input data for the current resolver, typically the exact value returned by the parent field's resolver.

You can visualize the data flow:

~~~mermaid
flowchart TD
    A[Query.book id=b-01] -->|returns Book| B[Source for Book fields]
    B --> C[Book.id]
    B --> D[Book.title]
    B --> E[Book.author]
    E -->|returns Author| F[Source for Author fields]
    F --> G[Author.id]
    F --> H[Author.name]
~~~

Key point to remember: the source object of `Book.author` is the `Book` object, while the source object of `Author.name` is the `Author` object. Each level in the query tree receives the source corresponding to the parent object of that level.

## 2. Where does the source object come from?

The source object typically comes from the value returned by the parent field's DataFetcher.

Example schema:

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

public class Author {

    private final String id;
    private final String name;

    public Author(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Resolver for Query:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

When `bookService.findById(id)` returns a `Book` object, GraphQL uses that object as the source for the fields selected inside `book`, such as `id`, `title`, and `author`.

If the client only selects `id` and `title`, the server does not need to resolve the `author` field. If the client also selects `author.name`, execution continues deeper into the `Book` and `Author` objects.

The source object is the actual runtime value, not the type name in the SDL and not the ID string passed in by the client.

## 3. Receiving the source object with `@SchemaMapping`

In Spring for GraphQL, a `@SchemaMapping` method can receive the parent source through a regular Java parameter.

Example:

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

In this method:

- `Book book` is the source object of the field being resolved.
- `book.getAuthorId()` reads the link information from the parent object.
- `authorService.findById(...)` loads the related `Author`.
- The returned `Author` object becomes the source object for child fields such as `Author.id` and `Author.name`.

With default naming, Spring infers the mapping from the method name `author` and the source parameter type `Book`, corresponding to `Book.author`.

You can declare the mapping explicitly:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author resolveAuthor(Book source) {
    return authorService.findById(source.getAuthorId());
}
~~~

Here, `typeName` specifies the GraphQL type that owns the field; `field` specifies the mapped field. The parameter name `source` or `book` does not affect the mapping, because the parameter type is what matters.

## 4. Source object vs. argument

A source object and an argument can appear together in the same resolver, but they have different origins:

- The source object comes from the result of the parent field.
- An argument comes from the value sent by the client for the current field.

Example SDL:

~~~graphql
type Book {
  id: ID!
  reviews(first: Int = 10, minRating: Int): [Review!]!
}
~~~

Client:

~~~graphql
query {
  book(id: "b-01") {
    reviews(first: 5, minRating: 4) {
      id
      rating
    }
  }
}
~~~

Controller:

~~~java
@Controller
public class BookReviewController {

    private final ReviewService reviewService;

    public BookReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public List<Review> reviews(
            Book book,
            @Argument Integer first,
            @Argument Integer minRating) {

        return reviewService.findByBook(
                book.getId(), first, minRating);
    }
}
~~~

In the method above:

| Parameter | Data source | Meaning |
|---|---|---|
| `Book book` | Parent field `Query.book` | Parent source object |
| `@Argument Integer first` | Argument of `Book.reviews` | Maximum number of reviews |
| `@Argument Integer minRating` | Argument of `Book.reviews` | Rating filter condition |

`book.getId()` reads the identifier from the source object. `first` and `minRating` come from the `reviews` field itself that the client is calling.

Do not confuse the parent field's `id` argument with the source object. Once `Query.book` has returned a `Book`, the child resolver receives the `Book` object; it does not automatically receive the parent field's argument as a source parameter.

If a child field needs a value from the parent field that the object does not yet contain, consider including the needed data in the source DTO, using local context, or querying the service again using an available key.

## 5. Source object vs. `GraphQLContext`

`GraphQLContext` is a shared context scoped to a single GraphQL request, typically holding information populated by the authentication layer or an interceptor.

The source object is the data of the parent field in the query tree. The two concepts serve two different purposes:

| Component | Scope | Example |
|---|---|---|
| Source object | A field branch in the execution tree | The `Book` currently being resolved |
| Field argument | A specific field | `first = 5` |
| `GraphQLContext` | The entire GraphQL request | Current user, correlation ID |
| Local context | A parent-child branch passed forward intentionally | Dedicated metadata for child fields |

You can receive a value from `GraphQLContext` using `@ContextValue`:

~~~java
@SchemaMapping
public List<Review> reviews(
        Book book,
        @ContextValue("currentUserId") String currentUserId) {

    return reviewService.findVisibleReviews(
            book.getId(), currentUserId);
}
~~~

`currentUserId` must be placed into `GraphQLContext` by a trusted authentication layer or interceptor. Do not take security identity from an arbitrary client-supplied argument.

A method can receive a source object, arguments, and context at the same time. Use the right mechanism for each kind of data so the method signature clearly expresses where each parameter comes from.

## 6. Receiving the source via `DataFetchingEnvironment`

If you need access to low-level GraphQL Java information, a method can accept `DataFetchingEnvironment` and read the source using `getSource()`.

Example:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(DataFetchingEnvironment environment) {
    Book book = environment.getSource();
    String locale = environment.getArgument("locale");

    return authorService.findById(book.getAuthorId(), locale);
}
~~~

Related APIs:

| API | Data |
|---|---|
| `getSource()` | Source object of the current field |
| `getArgument(name)` | Argument of the current field |
| `getGraphQlContext()` | Context of the GraphQL request |
| `getLocalContext()` | Local context passed from the parent field |
| `getField()` | Information about the field being executed |
| `getSelectionSet()` | Child fields requested by the client |

When using `DataFetchingEnvironment` instead of a typed source parameter, declare `typeName` explicitly because Spring no longer has a Java source type from which to infer the GraphQL parent type.

For typical controllers, a typed source parameter is usually easier to read and more type-safe. Use `DataFetchingEnvironment` when you genuinely need access to execution metadata.

## 7. How does `PropertyDataFetcher` use the source object?

Not every child field needs a `@SchemaMapping` method. GraphQL Java can use the default `PropertyDataFetcher` to read the matching property from the source object.

Example Java class:

~~~java
public class Book {

    private final String id;
    private final String title;
    private final Author author;

    public Book(String id, String title, Author author) {
        this.id = id;
        this.title = title;
        this.author = author;
    }

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

If the Query returns `Book` and the client requests:

~~~graphql
query {
  book(id: "b-01") {
    title
    author {
      name
    }
  }
}
~~~

GraphQL can:

1. Read `Book.title` from the `getTitle()` getter.
2. Read `Book.author` from the `getAuthor()` getter.
3. Use the returned `Author` object as the source for the `Author.name` field.
4. Read `Author.name` from the corresponding getter.

In this case, there is no need to write a separate resolver for `Book.author` if the `Author` relationship is already present on the `Book` object and the property mapping matches the schema.

`PropertyDataFetcher` is generally useful for POJOs with appropriate getters or properties. If the source is a `Map`, values can be retrieved by the corresponding key. The exact access mechanism depends on the structure of the source object and GraphQL Java's property access capabilities.

## 8. When is a separate resolver needed for a child field?

Use `@SchemaMapping` when a field is not already present on the source object or requires custom retrieval, computation, or verification logic.

For example, `Book` only stores `authorId` and does not hold the full `Author` object:

~~~java
public class Book {

    private final String id;
    private final String title;
    private final String authorId;

    // Constructor and getters
}
~~~

Resolver that loads `Author` from the service:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Some situations where a separate resolver is needed:

- The relationship needs to be loaded from a database or external service.
- The field is a value computed from multiple properties.
- The field depends on client arguments.
- The field requires authorization or custom business rules.
- The field needs batch loading to avoid N+1.
- The GraphQL field name differs from the Java property and needs explicit mapping.

Avoid creating resolvers for every field just to repeat getters. Doing so increases the number of methods and makes the mapping structure harder to follow.

## 9. The source object can be a DTO, projection, or entity

GraphQL does not require the source object to be a JPA entity. It can be any Java object returned by the parent field's DataFetcher that child resolvers can use.

For example, the public GraphQL type is `Book`, while the service returns a DTO:

~~~java
public record BookView(
        String id,
        String title,
        String authorId) {
}
~~~

Resolver:

~~~java
@QueryMapping
public BookView book(@Argument String id) {
    return bookService.findViewById(id);
}

@SchemaMapping(typeName = "Book", field = "author")
public Author author(BookView source) {
    return authorService.findById(source.authorId());
}
~~~

In this example:

- The GraphQL type is `Book`.
- The Java source object is `BookView`.
- `typeName = "Book"` specifies that the field belongs to the `Book` GraphQL type.
- The `BookView source` parameter receives the actual object returned from the Query.

This approach keeps the API schema independent of the persistence model. Entities, DTOs, and projections can change without forcing a rename of the GraphQL type.

When the source class differs from the GraphQL type, declare `typeName` explicitly to avoid relying on name inference conventions.

## 10. Multiple child fields can share the same parent source

One parent object can serve as the source for multiple child fields in the same query.

Example:

~~~graphql
query {
  book(id: "b-01") {
    title
    author {
      name
    }
    reviews(first: 5) {
      rating
    }
    relatedBooks {
      id
      title
    }
  }
}
~~~

The `Book.author`, `Book.reviews`, and `Book.relatedBooks` resolvers all receive the same `Book` source object as input data. Each resolver can use different properties to load its corresponding data.

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}

@SchemaMapping
public List<Review> reviews(
        Book book,
        @Argument Integer first) {
    return reviewService.findFirstByBookId(book.getId(), first);
}

@SchemaMapping
public List<Book> relatedBooks(Book book) {
    return bookService.findRelated(book.getId());
}
~~~

Child fields are separate branches of the execution tree. Do not assume the `author` resolver always runs before `reviews`, or that one resolver can mutate the source object for another resolver to read.

If multiple fields need to share auxiliary data, consider DataLoader, batch mapping, or a DTO containing pre-prepared data. Avoid using mutable controller fields to hold temporary results between resolvers.

## 11. Source object and `@BatchMapping`

When a Query returns many `Book` items and the client requests the `Author` for each `Book`, each `Book.author` field may need to load related data. If each resolver queries the database individually, the number of queries can grow with the number of books.

`@BatchMapping` receives a list of source objects instead of a single source object:

~~~java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Mono<Map<Book, Author>> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();

        return authorService.findAllByIds(authorIds)
                .collectMap(
                        Author::getId,
                        Function.identity()
                )
                .map(authorsById -> {
                    Map<Book, Author> result = new HashMap<>();

                    for (Book book : books) {
                        result.put(
                                book,
                                authorsById.get(book.getAuthorId()));
                    }

                    return result;
                });
    }
}
~~~

Spring uses the list of `Book` objects as the source object set for the `Book.author` batch field. The resulting `Map` associates each `Book` source with its corresponding `Author`.

When using a `Map`, keys must have stable equality and `hashCode` so objects are matched properly. If returning an ordered list or `Flux`, the results must correspond to the order of the input sources according to the batch mapping contract.

The source object is still `Book`; the difference is that a batch resolver receives multiple source objects at once to load data in batches.

## 12. Null parent source and null propagation

If the parent field returns `null`, GraphQL has no source object to continue resolving the child fields of that object.

Example SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

If the `book` Query finds no data and returns `null`, the response may be:

~~~json
{
  "data": {
    "book": null
  }
}
~~~

Child resolvers such as `Book.id` and `Book.title` are not invoked for a nonexistent parent object.

If the parent field is declared non-null:

~~~graphql
type Query {
  book(id: ID!): Book!
}
~~~

and the resolver still returns `null` or completes empty, GraphQL generates an execution error and applies null propagation up to the nearest nullable parent. If the root field is also non-null, the `null` value can propagate to the `data` of the entire operation.

Therefore, keep three factors aligned:

- The return type of the parent resolver.
- Nullability in the SDL.
- How missing data is handled in the service.

Do not return an empty or dummy source object just to avoid `null` if doing so distorts the business meaning.

## 13. The source object is not where request state belongs

Spring controllers are typically singleton beans. Multiple GraphQL requests can be processed concurrently, so you should never store the current source object in a mutable controller field.

Unsafe example:

~~~java
@Controller
public class BookController {

    private Book currentBook;

    @SchemaMapping
    public Author author(Book book) {
        this.currentBook = book;
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Two concurrent requests can overwrite each other's `currentBook`. Another resolver reading this field may receive the wrong data.

Use each method's source parameter instead:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

If you need to pass metadata from a parent field down to child fields, use local context or a supported context mechanism instead of shared mutable state. If data is needed across the entire request, use `GraphQLContext` at the appropriate scope.

## 14. Testing source mapping

An integration test should verify that the source object returned by the parent resolver is passed properly to the child resolver.

Example schema:

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

Controller:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        return new Book("b-01", "GraphQL in Practice", "a-01");
    }

    @SchemaMapping
    public Author author(Book source) {
        return new Author(
                source.getAuthorId(),
                "Nguyen An");
    }
}
~~~

Testing with `GraphQlTester`:

~~~java
@Test
void shouldPassParentBookAsSourceToAuthorResolver() {
    graphQlTester.document("""
            query {
                book(id: "b-01") {
                    id
                    author {
                        id
                        name
                    }
                }
            }
            """)
            .execute()
            .path("book.author.id")
            .entity(String.class)
            .isEqualTo("a-01");
}
~~~

Scenarios that should be tested:

1. Parent resolver returns an object and the child field receives the expected source.
2. Child field uses default property mapping when the property is already available.
3. Child field loads data using `@SchemaMapping`.
4. Java source class differs from the GraphQL type and is mapped with `typeName`.
5. Source combined with arguments and `GraphQLContext`.
6. Parent resolver returns `null` and the child field is not resolved.
7. Parent and child nullability produce responses conforming to the schema.
8. Batch mapping associates results properly with each source object.

## 15. Design principles for parent source objects

When designing resolvers and models returned from parent fields:

- Return an object containing sufficient data for the required child fields to operate.
- Use a DTO or projection if you do not want to expose persistence entities directly.
- Use default property mapping for fields already present on the source object.
- Use `@SchemaMapping` when a field needs custom retrieval or computation.
- Distinguish the source parameter from `@Argument`, `@ContextValue`, and `@LocalContextValue`.
- Declare `typeName` when the Java source type differs from the GraphQL type name.
- Never store the source object in mutable state on a singleton controller.
- Use `@BatchMapping` or DataLoader when multiple parent objects need to load related data.
- Keep nullability consistent across the parent resolver, child fields, and SDL.
- Test cases where the parent exists, the parent is null, and related data is missing.

## Conclusion

The parent source object is the value returned by a parent field and passed into the resolution of its child fields. In Spring for GraphQL, the source is typically received as a Java parameter in a `@SchemaMapping` method. The source type helps Spring infer the GraphQL type that owns the field; use `typeName` when the Java name differs from the schema name.

Understanding the source object properly helps distinguish parent data from arguments and request context, leverage `PropertyDataFetcher` when properties already exist, and use dedicated resolvers or `@BatchMapping` when related data needs to be loaded. Designing clear sources, avoiding shared mutable state, and handling nullability consistently will keep your GraphQL execution tree easy to control and scale.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Schema Mapping](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java — DataFetchingEnvironment API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetchingEnvironment.html)
- [GraphQL Java — PropertyDataFetcher API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/PropertyDataFetcher.html)
