# Class-Level Schema Mapping in Spring for GraphQL

`@SchemaMapping` maps a handler method in a controller to become a data fetcher for a field of a GraphQL schema. When multiple methods handle fields belonging to the same parent type, you can place `@SchemaMapping(typeName = "...")` at the class level to declare a default parent type for the handler methods in that class.

This organization keeps a controller focused on one GraphQL object type. Methods only need to declare the fields to handle; field names default to the method names, while `typeName` is inherited from the class. If a method handles a different parent type, you can override `typeName` at the method level.

## 1. What Is Schema Mapping?

In GraphQL, an object type can contain fields that need to be loaded or computed from other data. Example library schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
    reviews: [Review!]!
}

type Author {
    id: ID!
    name: String!
}

type Review {
    id: ID!
    rating: Int!
    comment: String!
}
~~~

The `book` field lives under the `Query` root type. The `author` and `reviews` fields live under the `Book` object type. Spring for GraphQL can map each of these fields to a Java method using `@QueryMapping`, `@SchemaMapping`, or `@BatchMapping`.

Example method handling the `Book.author` field:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public Author getAuthor(Book book) {
        // Load the author for this book.
    }
}
~~~

Here:

- `typeName = "Book"` specifies the field's parent type.
- `field = "author"` specifies the field name in the SDL.
- The `Book book` parameter is the current source/parent object that GraphQL is resolving.
- The return value `Author` becomes the result of the `Book.author` field.

`AnnotatedControllerConfigurer` detects controller beans and registers annotated handler methods as `DataFetcher` instances in the GraphQL runtime wiring. With the Spring Boot starter, this configuration is typically set up by auto-configuration.

## 2. Placing `@SchemaMapping` at the Class Level

When multiple handler methods map fields of `Book`, you can move `typeName` up to the class:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        // Load the author for this book.
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        // Load reviews for this book.
    }
}
~~~

The class-level annotation sets the default parent type to `Book` for the handler methods in the class. Thus the two methods above are equivalent to:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) { ... }

@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(Book book) { ... }
~~~

Class-level `@SchemaMapping` only provides a default `typeName` value. Each method still must be declared as a handler, for example with `@SchemaMapping` or `@BatchMapping`. Placing the annotation on the class alone does not turn every Java method in the class into a data fetcher.

## 3. Rules for Determining `typeName` and Field Name

Spring for GraphQL determines the mapping from annotations, method names, and source parameters. When using a class-level annotation, the rules can be read in the following order:

| Component | How It Is Determined |
| --- | --- |
| Parent type (`typeName`) | Method-level `typeName` if declared; otherwise class-level `typeName`; if neither is present, inferred from the simple class name of the source/parent parameter |
| Field name | Method-level `field` or its alias `value` if declared; otherwise the method name |
| Source object | Handler parameter typed as the parent object, such as `Book book` |

Example where the method name differs from the field name:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping(field = "primaryAuthor")
    public Author resolveMainAuthor(Book source) {
        // Maps to Book.primaryAuthor.
    }
}
~~~

The `resolveMainAuthor` method is mapped to the `primaryAuthor` field via `field`. The parent type remains `Book`, supplied by the class-level annotation.

`value` is an alias for the `field` attribute, so you can write `@SchemaMapping("primaryAuthor")`. Across a codebase, stick to one consistent style so readers can immediately tell it refers to the GraphQL field name.

## 4. Method-Level `typeName` Overrides Class-Level Default

A controller might handle most fields of `Book`, yet have one method handling a field belonging to another parent type. In that case, method-level `typeName` takes precedence:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class CatalogMappingController {

    @SchemaMapping
    public Author author(Book book) {
        // Maps to Book.author.
    }

    @SchemaMapping(typeName = "Author", field = "featuredBook")
    public Book featuredBook(Author author) {
        // Maps to Author.featuredBook.
    }
}
~~~

In this example:

- `author` inherits `typeName = "Book"` from the class.
- `featuredBook` declares `typeName = "Author"`, overriding the class-level default.
- The field name of `featuredBook` is explicitly specified using `field`.

If a controller has too many methods overriding the default type, it may be a sign that the handlers belong to different domains. Splitting controllers by parent type usually makes mappings easier to read and avoids scattered annotation overrides.

## 5. When Is Class-Level Mapping Useful?

Class-level `@SchemaMapping` is especially suitable in the following cases:

**Multiple fields belonging to the same parent type.** A `BookController` may handle `author`, `reviews`, `publisher`, `categories`, and other fields of `Book`. Declaring the type name once keeps methods short and consistent.

**Java source name differs from GraphQL type name.** For example, the application uses `BookEntity`, `BookView`, or `BookDto`, while the schema exposes type `Book`. Class-level `@SchemaMapping(typeName = "Book")` avoids inferring `typeName` from the Java class name.

**Grouping resolvers by domain.** The controller serves as the gathering place for data fetchers of one object type, while dedicated services handle business logic and data access.

Example Java source named `BookView`:

~~~java
public record BookView(
        String id,
        String title,
        String authorId
) {}

@Controller
@SchemaMapping(typeName = "Book")
public class BookViewController {

    @SchemaMapping
    public Author author(BookView source) {
        // The GraphQL parent type is Book, although the Java type is BookView.
    }
}
~~~

There is no requirement for the Java class name to match the GraphQL type name once `typeName` is specified explicitly. What matters is that the method receives the actual source object for the field being resolved.

## 6. Complete Example: Mapping Fields of `Book`

Suppose the application has the following models and services:

~~~java
public record Book(
        String id,
        String title,
        String authorId
) {}

public record Author(
        String id,
        String name
) {}

public record Review(
        String id,
        int rating,
        String comment
) {}
~~~

Services responsible for fetching data:

~~~java
public interface AuthorService {
    Author findById(String id);
}

public interface ReviewService {
    List<Review> findByBookId(String bookId);
}
~~~

Controller with class-level mapping:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookController(
            AuthorService authorService,
            ReviewService reviewService
    ) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}
~~~

In a version using batch mapping, the service also needs a corresponding method:

~~~java
import java.util.List;
import java.util.Map;
import reactor.core.publisher.Mono;

public interface ReviewService {
    Mono<Map<Book, List<Review>>> findByBooks(List<Book> books);
}
~~~

Because the class declares `@SchemaMapping(typeName = "Book")`, the two methods map to `Book.author` and `Book.reviews`. The default method names match the field names in the SDL, so `field` does not need to be specified.

Query:

~~~graphql
query BookDetails($id: ID!) {
    book(id: $id) {
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

GraphQL executes the `book` resolver on the `Query` root type to retrieve `Book`. Selected fields on that object then invoke their corresponding data fetchers: `author` invokes `BookController.author`, and `reviews` invokes `BookController.reviews`. Each method receives the resolved `Book` object itself as its source parameter.

## 7. Class-Level `@SchemaMapping` Combined with `@BatchMapping`

`@BatchMapping` declares a batch data fetcher for an associated field. It can inherit the default `typeName` from class-level `@SchemaMapping`, so a controller handling fields of the same parent type can place both regular schema mappings and batch mappings in one class.

Example replacing the per-book `reviews` resolver with a batch mapping:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookController(
            AuthorService authorService,
            ReviewService reviewService
    ) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @BatchMapping
    public Mono<Map<Book, List<Review>>> reviews(List<Book> books) {
        return reviewService.findByBooks(books);
    }
}
~~~

In this example, `ReviewService.findByBooks(...)` returns a map keyed by each `Book` source with the corresponding list of reviews as the value. Spring for GraphQL uses the batch result to supply `Book.reviews` for each parent object. `@BatchMapping` takes the field name from the method name by default, while the type name can be inherited from class-level `@SchemaMapping`.

A batch mapping can also return an ordered `Flux<V>` matching the order of the source objects, or appropriate synchronous variants. When using a map, keys must accurately identify each parent object; if objects are used as keys, ensure `equals` and `hashCode` reflect the intended identity.

Batch mapping can reduce N+1 queries when a query fetches many `Book` items and each needs `reviews`. Class-level mapping only shares the parent type; it does not batch data automatically. Grouping queries is handled by the batch loader mechanism registered by `@BatchMapping`.

## 8. Distinguishing Class-Level Mapping from Root Mappings

`@QueryMapping`, `@MutationMapping`, and `@SubscriptionMapping` are specialized annotations meta-annotated with `@SchemaMapping`, with fixed parent types of `Query`, `Mutation`, and `Subscription`, respectively.

Example root controller:

~~~java
@Controller
public class BookQueryController {

    @QueryMapping
    public Book book(@Argument("id") String id) {
        // Load the root Book object.
    }
}
~~~

This controller handles the `Query.book` field. Child fields of `Book` can be placed in another controller using class-level `@SchemaMapping(typeName = "Book")`.

Separate root operations and field mappings by parent type when that makes the code easier to read. Do not put class-level `@SchemaMapping(typeName = "Book")` on a controller that mixes many root handlers and child field handlers if doing so makes the actual mappings harder for readers to follow. Specialized annotations have fixed type names for root operations; class-level defaults are primarily meant for object type field handlers.

## 9. Method Arguments and Source Parameters

Handler methods can receive the source object alongside other supporting arguments. With class-level schema mapping, inheriting `typeName` does not alter method parameter binding rules.

| Parameter | Purpose |
| --- | --- |
| `Book book` | Source/parent object whose field is being resolved |
| `@Argument("locale") String locale` | Retrieves the GraphQL field argument `locale` |
| `@ContextValue("tenantId") String tenantId` | Retrieves a value from `GraphQLContext` |
| `GraphQLContext context` | Accesses the current GraphQL context |
| `DataFetchingEnvironment environment` | Accesses execution metadata and source/arguments at the GraphQL Java level |
| `Principal principal` | Retrieves the principal if provided by Spring Security integration |

Example field `Book.localizedTitle(locale: String!)`:

~~~graphql
type Book {
    id: ID!
    title: String!
    localizedTitle(locale: String!): String!
}
~~~

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public String localizedTitle(
            Book book,
            @Argument("locale") String locale
    ) {
        return translationService.translate(book.title(), locale);
    }
}
~~~

The `Book book` parameter is the source object; `@Argument` extracts the value from the field argument. Class-level mapping simply supplies the default parent type `Book`.

## 10. Organizing Controllers by Parent Type

A common organization is having each controller focus on a single GraphQL object type or a related group of fields:

~~~text
graphql/
├── BookQueryController.java       # Query.book, Query.books
├── BookController.java            # Book.author, Book.reviews, Book.publisher
├── AuthorController.java          # Author.books, Author.featuredBook
└── ReviewController.java          # Review.reviewer, Review.reactions
~~~

Example `AuthorController`:

~~~java
@Controller
@SchemaMapping(typeName = "Author")
public class AuthorController {

    private final BookService bookService;

    public AuthorController(BookService bookService) {
        this.bookService = bookService;
    }

    @SchemaMapping
    public List<Book> books(Author author) {
        return bookService.findByAuthorId(author.id());
    }
}
~~~

Class-level `typeName = "Author"` makes it clear that this controller owns fields of the GraphQL type `Author`. When a schema spans multiple domains, this grouping makes finding resolvers by type faster and avoids repeating `typeName` on every method.

You do not need a separate controller for every type when the schema is small. Choose boundaries based on business cohesion and handler count, avoiding over-splitting that makes dependency injection and code navigation cumbersome.

## 11. Testing Class-Level Schema Mapping

Tests should confirm that the class-level default actually maps methods to the right fields and that method-level overrides are applied properly. You can use `@GraphQlTest` together with `GraphQlTester`.

Example schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author!
}

type Author {
    id: ID!
    name: String!
}
~~~

Root controller:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return new Book("book-1", "GraphQL in Practice", "author-1");
    }
}
~~~

Field-mapping controller:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        return new Author(book.authorId(), "Nguyen An");
    }
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest({BookQueryController.class, BookController.class})
class BookSchemaMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void mapsAuthorUsingClassLevelTypeName() {
        graphQlTester.document("""
                query {
                    book(id: "book-1") {
                        title
                        author {
                            id
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("book.author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
~~~

This test assumes `Book` has an `authorId()` accessor and `Author` has matching accessors. It confirms that `author(Book)` maps to `Book.author` through class-level `typeName` even though the method does not repeat `typeName`.

You should also add tests for:

1. Field name inferred from method name.
2. Custom field name via `@SchemaMapping(field = "...")`.
3. Method-level `typeName` overriding class-level default.
4. Java source type differing from GraphQL type name while class-level mapping remains accurate.
5. `@BatchMapping` inheriting the parent type and returning the right results for each source object.
6. No two handler methods registering the same parent type/field pair.

## 12. Common Errors and Troubleshooting

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Field has no data fetcher | Method is not annotated with `@SchemaMapping` or `@BatchMapping` | Class-level annotation only sets default type name; annotate the handler method |
| Mapping points to wrong parent type | `typeName` does not match object type name in SDL | Check GraphQL type name and method-level overrides |
| Field name mismatch | Method name differs from field name without `field` declared | Add `@SchemaMapping(field = "fieldName")` |
| Method does not receive source object | Source parameter type does not match actual parent object | Check source parameter and object type returned by parent resolver |
| Method-level override has no effect | Method annotation declares wrong `typeName` or mapping collides | Check annotations at both levels and the effective type/field pair |
| Batch mapping is not invoked | Method lacks `@BatchMapping`, or type/field mapping mismatches | Check annotation, source list, and field name |
| Two handlers register the same field | Duplicate mapping across controllers or between annotations and manual wiring | Keep only one data fetcher per parent type/field pair |
| Resolver runs but returns null | Service finds no data or source object lacks link identifier | Check service, source object, and SDL nullability |

When debugging, first identify the `typeName.fieldName` pair the method should handle. Then check the class-level default, method-level override, inferred field name, and source parameter. This quickly reveals annotation mistakes instead of confusing them with data-access bugs.

## 13. Security and Performance Notes

Class-level `@SchemaMapping` is purely a mapping declaration. It does not automatically add authentication or authorization to fields. If `Book.internalNotes` is restricted to authorized users, the resolver or service must check the principal and permissions before returning data.

Similarly, grouping resolvers for one parent type into one controller does not reduce database accesses. If a query fetches a list of many `Book` objects and resolves `author` or `reviews` per item, N+1 queries can occur. Use `@BatchMapping`, DataLoader, or batch services to consolidate queries; measure and test with datasets containing many parent objects.

Keep handler methods thin: accept the source and arguments, call a service, and return the result. Do not put all business logic, transactions, or infrastructure access inside annotations/controllers merely because the fields belong to the same GraphQL type.

## 14. Workflow for Applying Class-Level Schema Mapping

When creating a controller for a GraphQL object type:

1. Identify the parent type in the SDL that the controller will handle.
2. Place `@Controller` and `@SchemaMapping(typeName = "ParentType")` at the class level.
3. Annotate each handler method with `@SchemaMapping` or `@BatchMapping`.
4. Match method names to field names when possible; otherwise declare `field` explicitly.
5. Use method-level `typeName` when a method needs to map to a different parent type.
6. Accept the source object via an appropriately typed parameter; receive arguments with `@Argument` when needed.
7. Keep business logic in services and use batching for related fields prone to N+1 queries.
8. Test parent type/field pairs with `GraphQlTester` and check for duplicate mappings.

Class-level `@SchemaMapping` helps a controller clearly express the parent type it serves, reduces repetitive annotations, and supports organizing resolvers by domain. Understanding `typeName` inheritance rules, field name inference, and method-level overrides makes annotated controllers in Spring for GraphQL easier to read and maintain.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL 1.4 — SchemaMapping API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/SchemaMapping.html)
- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batch-loading)
