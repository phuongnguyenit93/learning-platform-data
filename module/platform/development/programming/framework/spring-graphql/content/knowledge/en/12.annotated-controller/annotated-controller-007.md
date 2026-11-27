# Default `typeName` from Source Type in Annotated Controllers

## Objectives

After this lesson, you can:

- Explain the role of the source object in a Spring for GraphQL field mapping.
- Understand how Spring infers `typeName` from the Java type of the source parameter.
- Distinguish between `typeName` inferred from the source type and field names inferred from method names.
- Write `@SchemaMapping` without declaring `typeName` when the Java type name and GraphQL type name match.
- Use `@Source` to explicitly indicate the source parameter in a method signature.
- Place `@SchemaMapping` at the class level to provide a default `typeName` for methods.
- Override `typeName` at the method level when one controller handles multiple GraphQL types.
- Recognize cases where DTOs, interfaces, or base classes cause `typeName` inference to behave unexpectedly.
- Understand how source types are inferred in `@BatchMapping`.
- Test and diagnose mapping errors between Java source types and GraphQL object types.

## 1. What Is a Source Type in an Annotated Controller?

When GraphQL executes a nested field, that field is typically resolved based on the parent object currently being processed. That parent object is called the **source object**.

Example schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
    displayLabel: String!
}

type Author {
    id: ID!
    name: String!
}

type Query {
    book(id: ID!): Book
}
~~~

The client sends an operation:

~~~graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
~~~

Processing can proceed as follows:

1. The `Query.book` field is resolved and returns a Java object representing the book.
2. The GraphQL runtime uses that object as the source when resolving the child field `Book.author`.
3. The controller method mapped to `Book.author` receives the book source object.
4. The method returns the author so GraphQL can continue resolving `Author.name`.

In Spring for GraphQL, the source parameter of a `@SchemaMapping` method is typically the parent object:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return bookService.findAuthor(book.id());
    }
}
~~~

The method receives `Book` as the source object and returns `Author`. Spring needs to determine which field on which GraphQL type this method handles. If not declared explicitly, the framework can infer those two pieces of information from the method signature and method name.

## 2. How Spring Infers Default `typeName` from the Source Parameter

`@SchemaMapping` has two key attributes:

- `typeName`: name of the GraphQL object type containing the field to resolve.
- `field`: name of the GraphQL field to map to the method.

When `typeName` is omitted, Spring for GraphQL infers the type name from the Java type of the source parameter in the method. For example:

~~~java
@SchemaMapping
public Author author(Book book) {
    return bookService.findAuthor(book.id());
}
~~~

With a source parameter of Java type `Book`, Spring infers:

| Component | Inferred Value |
| --- | --- |
| Source parameter type | `Book` |
| GraphQL `typeName` | `Book` |
| Method name | `author` |
| GraphQL `field` | `author` |

The method is treated as equivalent to the explicit mapping:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return bookService.findAuthor(book.id());
}
~~~

Therefore, if the simple class name of the source type matches the GraphQL object type name, you can omit `typeName` to keep the code concise.

Keep in mind that `typeName` is inferred from **the Java type declared for the source parameter**, not from the service name, repository name, or return type.

## 3. Distinguishing `typeName` Inference from `field` Inference

Spring can infer both `typeName` and `field`, but they come from two different sources:

- The default `typeName` comes from the source parameter type.
- The default `field` comes from the method name.

Example:

~~~java
@SchemaMapping
public Author primaryAuthor(Book book) {
    return bookService.findPrimaryAuthor(book.id());
}
~~~

Spring infers the mapping `Book.primaryAuthor`, because the source parameter is `Book` and the method name is `primaryAuthor`.

If the SDL declares the field as `Book.author`, the method must specify `field` explicitly:

~~~java
@SchemaMapping(field = "author")
public Author primaryAuthor(Book book) {
    return bookService.findPrimaryAuthor(book.id());
}
~~~

Here, `typeName` is still inferred as `Book`, while `field` is overridden to `author`.

Conversely, if the method name is `author` but the source parameter is `BookView`, the framework infers `BookView.author`. Having the method name match the field in the SDL is not enough to identify the parent type.

## 4. Complete Example When Java Type Name Matches GraphQL Type

Suppose the application uses Java records `Book` and `Author`:

~~~java
public record Book(
        String id,
        String title,
        String authorId) {
}

public record Author(
        String id,
        String name) {
}
~~~

SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
    displayLabel: String!
}

type Author {
    id: ID!
    name: String!
}

type Query {
    book(id: ID!): Book
}
~~~

Root resolver returning `Book`:

~~~java
@Controller
class CatalogQueryController {

    private final BookService bookService;

    CatalogQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

Resolver for nested field:

~~~java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

With the method `author(Book book)`, Spring infers:

- Source type `Book` corresponds to GraphQL type `Book`.
- Method name `author` corresponds to GraphQL field `author`.

Thus there is no need to write `@SchemaMapping(typeName = "Book", field = "author")`.

This is the ideal situation for default inference: the Java type is named closely to the GraphQL model and the source parameter has a concrete, unambiguous type.

## 5. Using `@Source` to Explicitly Mark the Source Parameter

In a method with multiple parameters, you can use `@Source` to explicitly mark which parameter is the source object.

~~~java
@Controller
class BookController {

    private final ReviewService reviewService;

    BookController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public List<Review> reviews(
            @Source Book book,
            @Argument("first") Integer first) {

        return reviewService.findByBookId(book.id(), first);
    }
}
~~~

In this example:

- `@Source Book book` is the source object of the `Book.reviews` field.
- `@Argument("first")` receives the `first` argument declared on the `reviews` field.
- The method name `reviews` is used to infer the field name.
- The `Book` type of the source parameter is used to infer `typeName`.

`@Source` makes the role of parameters explicit in the method signature. When there is a single simple source parameter, Spring can often recognize the source without this annotation. Using the explicit annotation can improve readability, especially when the method also accepts arguments, context, or parameters resolved by other annotations.

Corresponding example schema:

~~~graphql
type Review {
    id: ID!
    rating: Int!
    comment: String
}

type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}
~~~

## 6. Setting a Default `typeName` at the Controller Class Level

If multiple methods in the same controller handle fields of one GraphQL object type, you can place `@SchemaMapping(typeName = "...")` on the class.

~~~java
@Controller
@SchemaMapping(typeName = "Book")
class BookFieldsController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    BookFieldsController(AuthorService authorService, ReviewService reviewService) {
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

    @SchemaMapping
    public String displayLabel(Book book) {
        return book.title() + " (" + book.id() + ")";
    }
}
~~~

In this example, class-level `typeName = "Book"` supplies the default type for mapping methods inside the controller. The method name is used as the field name if the method does not declare `field`.

The mappings can be read as:

| Method | GraphQL Mapping |
| --- | --- |
| `author(Book book)` | `Book.author` |
| `reviews(Book book)` | `Book.reviews` |
| `displayLabel(Book book)` | `Book.displayLabel` |

Class-level placement is useful when a controller focuses on one GraphQL type and has several nested field resolvers. It reduces repeating `typeName = "Book"` on every method.

Avoid setting a broad class-level `typeName` if the controller handles unrelated object types. In that case, declaring it per method is usually easier to read and less error-prone.

## 7. Overriding `typeName` at the Method Level

One controller can handle fields for multiple GraphQL types. In that case, declaring `typeName` on the method keeps the mapping accurate.

~~~java
@Controller
class CatalogFieldController {

    private final AuthorService authorService;
    private final BookService bookService;

    CatalogFieldController(AuthorService authorService, BookService bookService) {
        this.authorService = authorService;
        this.bookService = bookService;
    }

    @SchemaMapping(typeName = "Book")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(typeName = "Author")
    public List<Book> books(Author author) {
        return bookService.findByAuthorId(author.id());
    }
}
~~~

Corresponding mappings:

- `author(Book book)` handles `Book.author`.
- `books(Author author)` handles `Author.books`.

If a class-level annotation sets a default `typeName`, a method-level `typeName` can specify a different type for that method.

Example:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
class CatalogFieldControllerWithDefault {

    private final AuthorService authorService;
    private final BookService bookService;

    CatalogFieldControllerWithDefault(
            AuthorService authorService, BookService bookService) {
        this.authorService = authorService;
        this.bookService = bookService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(typeName = "Author")
    public List<Book> books(Author author) {
        return bookService.findByAuthorId(author.id());
    }
}
~~~

On the `author` method, the class-level `typeName` is `Book`. On the `books` method, `typeName` is declared directly as `Author`.

When reading code, check both the class-level annotation and the method-level annotation to determine the effective mapping. If a mapping is important or potentially confusing, declaring it explicitly on the method is a clear choice.

## 8. When the Java Source Type Differs from the GraphQL Type Name

In real applications, the Java source object is often a DTO, projection, or view model rather than a class with the same name as the GraphQL type.

Java example:

~~~java
public record BookView(
        String id,
        String title,
        String authorId) {
}
~~~

The SDL still exposes type `Book`:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
}
~~~

If you write:

~~~java
@SchemaMapping
public Author author(BookView book) {
    return authorService.findById(book.authorId());
}
~~~

Spring infers `typeName` from `BookView`, resulting in the mapping `BookView.author`. Since the schema only has `Book.author`, the mapping does not match.

The fix is to specify the GraphQL type explicitly:

~~~java
@SchemaMapping(typeName = "Book")
public Author author(BookView book) {
    return authorService.findById(book.authorId());
}
~~~

Or specify both the type and the field:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(BookView book) {
    return authorService.findById(book.authorId());
}
~~~

Practical rule:

- If the Java class and GraphQL type share the same name, default inference can be used.
- If the Java class has suffixes like `View`, `Dto`, `Projection`, or `Entity`, check the GraphQL type name the framework will infer.
- If the names differ, use an explicit `typeName` or an appropriate class-level mapping.
- Do not rename the GraphQL schema just to match persistence class names if doing so makes the API less clear.

## 9. Source Parameter Declared as an Interface or Base Class

A common source of confusion is a source parameter with a general type:

~~~java
public interface CatalogItem {
    String id();
}
~~~

~~~java
public record BookView(
        String id,
        String title,
        String authorId) implements CatalogItem {
}
~~~

Method:

~~~java
@SchemaMapping
public Author author(CatalogItem item) {
    return authorService.findByBookId(item.id());
}
~~~

The declared source parameter type is `CatalogItem`, so you should not assume Spring will infer `typeName` as `Book` simply because the runtime object happens to be `BookView`.

If the field belongs to the GraphQL type `Book`, specify it explicitly:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(CatalogItem item) {
    return authorService.findByBookId(item.id());
}
~~~

This is especially important when one Java interface serves as the source for multiple GraphQL object types. A single source interface can represent multiple runtime types; an interface name alone is not enough to identify the field mapping for each GraphQL type.

If each GraphQL object type has different field mappings, declare separate resolvers or design specific source parameters for each mapping. Use a base class only when the field contract genuinely applies to all related types.

## 10. Inferring Source Type in `@BatchMapping`

`@BatchMapping` also maps a field on a source type, except the method usually receives a collection of source objects to process in a batch.

Example:

~~~java
@Controller
class BookBatchController {

    private final AuthorService authorService;

    BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsByBooks(books);
    }
}
~~~

The method is named `author` and the source parameter is `List<Book>`. Spring can infer:

- `typeName` is `Book`, based on the source element type.
- `field` is `author`, based on the method name.

If the source is `List<BookView>` while the GraphQL type is still `Book`, declare it explicitly:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<BookView, Author> author(List<BookView> books) {
    return authorService.findAuthorsByBooks(books);
}
~~~

`@BatchMapping` follows the same source-type determination idea as `@SchemaMapping`, except you must pay attention to the element type inside the collection. Check the generic type of the source parameter when the method receives `List<T>` or a similar collection.

Do not confuse `typeName` with the return value type of the batch method. In the example, `Map<Book, Author>` returns the relationship between source `Book` and result `Author`; `typeName` is still the GraphQL type of the source, namely `Book`.

## 11. `@QueryMapping` and Root Mappings Do Not Infer `typeName` from a Source

`@QueryMapping`, `@MutationMapping`, and `@SubscriptionMapping` are specialized annotations for root operation types.

Example:

~~~java
@Controller
class BookQueryController {

    private final BookService bookService;

    BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

`@QueryMapping` maps the method to a field on the `Query` root type. The `typeName` of a root mapping is not inferred from a source parameter like nested `@SchemaMapping`, because the method handles a root operation rather than a field of a parent object.

Similarly:

- `@MutationMapping` maps to the `Mutation` root type.
- `@SubscriptionMapping` maps to the `Subscription` root type.

Only after `Query` returns a `Book` object can nested fields of that object use `@SchemaMapping` and infer the source type from the `Book` parameter.

Do not apply the `@SchemaMapping` source-type inference rules to explain root mappings. The two annotation groups have different purposes.

## 12. Common Errors When Inferring `typeName`

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Method is not called for the expected field | Source class is `BookView` while SDL uses `Book` | Declare `@SchemaMapping(typeName = "Book")` |
| Mapping points to a nonexistent type | Java source type infers a name not present in schema | Check source parameter and GraphQL type name |
| Right type but wrong field | Method name differs from field name in SDL | Use `@SchemaMapping(field = "...")` |
| Controller has many methods with same source type but mapping is hard to read | Missing class-level or method-level convention | Group controller by type or declare explicitly |
| Field mapping on interface does not match object type | Source parameter declared as base interface | Specify `typeName` or use a concrete source type |
| Batch mapping does not infer expected type | Generic element type differs from GraphQL type | Check `List<T>` and set `typeName` explicitly |
| Query mapping mistaken for nested mapping | Confusing root operation with object field | Use `@QueryMapping` for Query root and `@SchemaMapping` for nested fields |
| Field exists in SDL but resolver does not run | Annotation mapping mismatch or controller not managed by Spring | Check type/field names and component registration |

A useful diagnostic habit is writing down the resulting mapping in the form:

~~~text
GraphQL type + field = Java handler method
Book + author = BookController.author(BookView)
~~~

Then verify the source parameter, `typeName`, `field`, and schema in order. This usually reveals inference errors faster than looking at the method name alone.

## 13. Testing Default `typeName` and Explicit Mappings

You should test actual operations to confirm mappings are registered properly. For example, with the `Book.author` schema, the client queries:

~~~graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
~~~

A test can use `GraphQlTester`:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                title
                author {
                    name
                }
            }
        }
        """)
        .execute()
        .path("book.author.name")
        .entity(String.class)
        .isEqualTo("An Nguyen");
~~~

Test cases to include:

- Source class `Book` matches GraphQL type `Book`, default mapping works.
- Source class `BookView` differs from GraphQL type `Book`, explicit mapping works.
- Method name matches default field.
- Method name differs from field while `field` is explicitly declared.
- Class-level `typeName` is applied to methods.
- Method-level `typeName` overrides the class-level default.
- `@BatchMapping` infers from the generic source element type.
- Source parameter is an interface or base class and mapping is explicitly declared.

When a mapping fails, check schema startup errors or handler registration logs first. Then run a minimal operation requesting only the field under verification, avoiding failures in other nested fields that obscure the root cause.

## 14. Design Guidelines for Readable Mappings

A few rules keep annotated controller code clear:

1. Use concrete source parameter types whenever possible.
2. Name Java source classes close to GraphQL object types if the architecture permits.
3. If using DTOs or projections with different names, declare `typeName` explicitly.
4. Organize controllers by GraphQL type groups when there are many nested field mappings.
5. Use class-level `@SchemaMapping(typeName = "...")` when most methods in the controller handle one type.
6. Use method-level `typeName` when a method handles another type or needs clarity.
7. Specify `field` when the method name does not match the SDL field.
8. Use `@Source` when you want to make the source parameter explicit in methods with multiple parameters.
9. With `@BatchMapping`, check the generic element type of the source collection.
10. Test operations via `GraphQlTester` to verify the actual mappings.

Do not overuse default inference if type names are unclear. Explicit mappings are a good choice whenever they let readers immediately identify which GraphQL field is being handled.

## 15. Summary

In Spring for GraphQL, `@SchemaMapping` can infer the default `typeName` from the Java type of the source parameter. The default field name is inferred from the method name. Thus, `author(Book book)` typically maps to `Book.author` without needing to declare those two attributes in the annotation.

This rule works most cleanly when the Java source type name matches the GraphQL object type name. If the source is a DTO, projection, interface, or base class with a different name, declare `typeName` explicitly. Class-level `@SchemaMapping` can supply a default type for multiple methods, while method-level annotations can override it when needed. With `@BatchMapping`, pay attention to the generic element type of the source collection. Understanding the inference rules keeps controllers concise while keeping mappings accurate and maintainable.
