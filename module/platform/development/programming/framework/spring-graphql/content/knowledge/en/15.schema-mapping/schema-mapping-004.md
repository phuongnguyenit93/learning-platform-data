# `typeName` and `field` in `@SchemaMapping`

In Spring for GraphQL, a schema mapping specifies **which field of which GraphQL type** will be handled by a handler method. The two core pieces of information are `typeName` and `field`: `typeName` is the name of the parent type in the SDL, and `field` is the name of the field belonging to that type.

For example, `Book.author` means the `author` field belonging to the `Book` GraphQL object type. A mapping can declare both names explicitly using `@SchemaMapping(typeName = "Book", field = "author")`. When the Java names match, Spring for GraphQL can also infer `typeName` from the source parameter and infer `field` from the method name.

## 1. The `typeName.field` pair in a GraphQL schema

A GraphQL schema organizes data by types and fields. Example:

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
    comment: String
}
~~~

Fields can be identified by the `typeName.field` pair:

| Mapping pair | Meaning |
| --- | --- |
| `Query.book` | Field `book` belonging to root type `Query` |
| `Book.author` | Field `author` belonging to type `Book` |
| `Book.reviews` | Field `reviews` belonging to type `Book` |
| `Author.name` | Field `name` belonging to type `Author` |

In GraphQL Java, a data fetcher is registered for a specific field of a type. `@SchemaMapping` lets Spring for GraphQL create that registration from a controller method.

## 2. Explicitly declaring `typeName` and `field`

Example mapping `Book.author`:

~~~java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author loadAuthor(Book source) {
        return authorService.findById(source.authorId());
    }
}
~~~

The annotation explicitly states that handler method `loadAuthor` handles the `author` field of the `Book` GraphQL type. The method name does not need to match the field name because `field` is specified.

In this example, `Book source` is the source/parent object currently being resolved by GraphQL. Spring passes the current `Book` object into the source parameter. The resolver uses the book's `authorId` to fetch the corresponding `Author`.

`typeName` and `field` must match the SDL exactly, including case sensitivity. `Book.author` is different from `Book.Author`, and `Book.author` is also different from `Author.book`.

## 3. Inferring `field` from the method name

If the method name matches the field name in the SDL, you can omit the `field` attribute:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(typeName = "Book")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}
~~~

Spring for GraphQL uses the method name as the field name when neither `field` nor its alias `value` is declared. The two methods above map to `Book.author` and `Book.reviews` respectively.

This is a concise and readable style when the Java method name can stay identical to the GraphQL field name. If the method name needs to express an action or follow a different naming convention, declare `field` explicitly instead of forcing the method to carry the GraphQL name.

## 4. Using `field` or `value` to specify the field name

`value` is an alias for the `field` attribute in `@SchemaMapping`. The following two declarations have the same meaning:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author loadAuthor(Book book) {
    return authorService.findById(book.authorId());
}
~~~

~~~java
@SchemaMapping(typeName = "Book", value = "author")
public Author loadAuthor(Book book) {
    return authorService.findById(book.authorId());
}
~~~

You can also use the shorthand form:

~~~java
@SchemaMapping("author")
public Author loadAuthor(Book book) {
    return authorService.findById(book.authorId());
}
~~~

In the shorthand form, the first string is assigned to `value`, which is the alias of `field`. The parent type is inferred from the `Book` source parameter if no `typeName` is set on the method or class.

Choose one consistent style across your codebase. `field = "author"` is often easier to read when readers need to distinguish the GraphQL field name from the Java method name; `@SchemaMapping("author")` is shorter for simple mappings.

## 5. Inferring `typeName` from the source parameter

If `typeName` is not declared, Spring for GraphQL can infer the parent type from the Java type of the source parameter in the handler method.

~~~java
@Controller
public class BookController {

    @SchemaMapping(field = "author")
    public Author resolveAuthor(Book source) {
        return authorService.findById(source.authorId());
    }
}
~~~

The source parameter has type `Book`, so the default parent type is inferred from the Java class name as `Book`. The resulting mapping is `Book.author`.

This inference is convenient when the Java class name matches the GraphQL object type name. If the application uses a DTO, projection, or entity whose name differs from the SDL, declare `typeName` explicitly to avoid a wrong mapping.

For example, the Java class is named `BookView`, while the schema still calls the type `Book`:

~~~java
public record BookView(
        String id,
        String title,
        String authorId
) {}

@Controller
public class BookViewController {

    @SchemaMapping(typeName = "Book", field = "author")
    public Author resolveAuthor(BookView source) {
        return authorService.findById(source.authorId());
    }
}
~~~

When the Java and GraphQL names differ, `typeName = "Book"` clarifies the mapping without renaming the Java class.

If a method has no source parameter from which Spring can infer the parent type, specify `typeName` explicitly. For root resolvers, you should normally use `@QueryMapping`, `@MutationMapping`, or `@SubscriptionMapping` to express the operation type clearly.

## 6. Combining inference and explicit declaration

It is not mandatory to declare both attributes in every handler. You can choose a style based on naming conventions:

| Annotation | Source parameter | Resolved mapping |
| --- | --- | --- |
| `@SchemaMapping(typeName = "Book", field = "author")` | `Book source` | `Book.author` |
| `@SchemaMapping(typeName = "Book")` | `Book source` | `Book.<method name>` |
| `@SchemaMapping(field = "author")` | `Book source` | `Book.author` if type inference succeeds |
| `@SchemaMapping("author")` | `Book source` | `Book.author` if type inference succeeds |
| `@SchemaMapping` | `Book source` | `Book.<method name>` if type inference succeeds |

When reading code, identify the two final values Spring uses: parent type and field. The annotation can supply one value, while the other is inferred from the method or source parameter.

## 7. Class-level `typeName` and method-level override

If multiple handlers in the same controller belong to the same parent type, you can place `typeName` at the class level:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(field = "reviews")
    public List<Review> findReviews(Book book) {
        return reviewService.findByBookId(book.id());
    }

    @SchemaMapping(typeName = "Author", field = "featuredBook")
    public Book featuredBook(Author author) {
        return bookService.findFeaturedByAuthor(author.id());
    }
}
~~~

The first two methods inherit `typeName = "Book"` from the class. The `featuredBook` method overrides the default type with `typeName = "Author"`. The `field` of the second method is set explicitly because the method name `findReviews` differs from the `reviews` field.

A class-level annotation only provides a default parent type for handler methods; each method still needs `@SchemaMapping` or the corresponding mapping annotation. If a controller has many methods overriding the type repeatedly, consider splitting controllers by parent type so mappings stay easy to follow.

## 8. Distinguishing field mapping from field arguments

`field` in `@SchemaMapping` is the **GraphQL field name** that the method handles. It is not the name of a field argument.

For example, the schema has the field `Book.localizedTitle(locale: String!)`:

~~~graphql
type Book {
    id: ID!
    title: String!
    localizedTitle(locale: String!): String!
}
~~~

Handler method:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "localizedTitle")
    public String resolveLocalizedTitle(
            Book source,
            @Argument("locale") String locale
    ) {
        return translationService.translate(source.title(), locale);
    }
}
~~~

Here:

- `typeName = "Book"` is the parent type.
- `field = "localizedTitle"` is the mapped field name.
- `@Argument("locale")` reads the `locale` argument from the field call.
- `Book source` is the current parent object.

Do not write `field = "locale"` just because the method accepts a `locale` parameter; doing so would require the schema to have a `Book.locale` field, which is a completely different mapping.

## 9. Mapping root fields: Query, Mutation, and Subscription

Fields on root types are also identified by type and field pairs. With the default schema, the root types are `Query`, `Mutation`, and `Subscription`.

~~~graphql
type Query {
    book(id: ID!): Book
}

type Mutation {
    renameBook(id: ID!, title: String!): Book
}

type Subscription {
    bookUpdated(id: ID!): Book!
}
~~~

You can use `@SchemaMapping` to specify root mappings explicitly:

~~~java
@Controller
public class BookRootController {

    @SchemaMapping(typeName = "Query", field = "book")
    public Book findBook(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Mutation", field = "renameBook")
    public Book renameBook(
            @Argument("id") String id,
            @Argument("title") String title
    ) {
        return bookService.rename(id, title);
    }
}
~~~

However, Spring for GraphQL provides specialized annotations to express the root operation type clearly:

~~~java
@Controller
public class BookRootController {

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @MutationMapping
    public Book renameBook(
            @Argument("id") String id,
            @Argument("title") String title
    ) {
        return bookService.rename(id, title);
    }
}
~~~

`@QueryMapping`, `@MutationMapping`, and `@SubscriptionMapping` are specialized annotations for root fields. For child fields like `Book.author`, use `@SchemaMapping` to indicate the parent type clearly.

## 10. Combining with `@BatchMapping`

`@BatchMapping` also registers a data fetcher for a parent type and field pair. It supports `typeName` and `field` attributes similar to `@SchemaMapping`, and can likewise use the method name to infer the field.

Example SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews: [Review!]!
}
~~~

Batch handler mapped to `Book.reviews`:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BookReviewController {

    @BatchMapping(typeName = "Book", field = "reviews")
    public Mono<Map<Book, List<Review>>> loadReviews(List<Book> books) {
        return reviewService.findByBooks(books);
    }
}
~~~

In the example, the method name `loadReviews` differs from the `reviews` field, so the annotation declares `field` explicitly. The service returns a map from each `Book` to its corresponding list of reviews. Spring for GraphQL uses the batch result to supply the field result for each parent object.

If the method were named `reviews`, you could omit `field` and let the framework infer it. Whether using `@BatchMapping` or `@SchemaMapping`, the final `typeName.field` pair must still match the schema.

## 11. Testing type and field mappings

Tests should verify that the field is registered at the correct position in the schema and that the handler returns the expected data. Example:

Minimal types used in the test example:

~~~java
public record Book(String id, String title, String authorId) {}

public record Author(String id, String name) {}

public interface BookService {
    Book findById(String id);
    Book rename(String id, String title);
}

public interface AuthorService {
    Author findById(String id);
}
~~~

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@GraphQlTest({BookRootController.class, BookController.class})
class BookFieldMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void resolvesAuthorFieldOfBook() {
        given(bookService.findById("book-1"))
                .willReturn(new Book("book-1", "GraphQL in Practice", "author-1"));
        given(authorService.findById("author-1"))
                .willReturn(new Author("author-1", "Nguyen An"));

        graphQlTester.document("""
                query {
                    book(id: "book-1") {
                        id
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

`BookService` and `AuthorService` are mocked with `@MockitoBean`; the test supplies a `Book` with `authorId` set to `author-1` and a corresponding `Author`. The `Book` and `Author` records must have `id()`, `title()`/`name()`, and `authorId()` accessors as in the preceding examples.

You should also test:

1. The method name is used as the field when `field` is omitted.
2. `field` and its alias `value` map to the same field.
3. `typeName` is inferred from the source parameter when the Java and GraphQL names match.
4. Explicit `typeName` handles cases where a Java DTO differs from the GraphQL type name.
5. Class-level defaults and method-level overrides produce the expected type/field pair.
6. Arguments bound with `@Argument` are independent of the mapped field name.
7. No two handlers register the same `typeName.field` pair.

## 12. Common issues when configuring `typeName` and `field`

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Field has no data fetcher | `field` does not match the SDL or the method lacks a mapping annotation | Check the `typeName.field` pair and method annotation |
| Mapping is registered on the wrong type | Inference from source parameter does not match the GraphQL type name | Declare `typeName` explicitly |
| Incorrect field name | Method name differs from the SDL field but `field` is omitted | Use `field = "..."` or the `value` alias |
| Confusing field with argument | Using an argument name as `field` in the annotation | Keep `field` as the GraphQL field name; bind arguments with `@Argument` |
| Method-level override does not behave as expected | `typeName` on the method mismatches or the field has duplicate mappings | Check annotation values on both the class and method |
| Two methods handle the same field | Duplicate `typeName.field` pair across multiple controllers | Let only one handler own each field or redesign the mapping |
| Root query is not invoked | Wrong root type or mapping annotation used | Use `@QueryMapping` or `typeName = "Query"` with the default schema |
| Batch field is not resolved | `@BatchMapping` uses wrong field/type or batch results fail to match sources | Check the annotation, source list, and result map |

When debugging, write down the exact type/field pair exposed by the SDL, then compare it against the annotation. Do not look only at the Java method name: the method name can be overridden by `field`, and the parent type can come from `typeName`, a class-level default, or the source parameter.

## 13. Naming and mapping organization rules

- Keep method names identical to field names unless there is a good reason for a different name.
- Use explicit `typeName` when the Java class does not match the GraphQL type or when the mapping cannot be clearly inferred.
- Use `field`/`value` when the method name differs from the field name; pick one consistent convention across the whole project.
- Group handlers by parent type for easy lookup, such as `BookController` and `AuthorController`.
- Never register the same field through both an annotated controller and manual runtime wiring.
- Keep resolver methods thin; data access and business rules belong in services.
- For relational fields resolved across many parent objects, consider `@BatchMapping` or DataLoader to avoid N+1.

`typeName` and `field` pinpoint the exact location of a resolver in the GraphQL schema. Once you understand explicit declaration, source/method inference, and specialized annotations for root operations, wiring SDL to controllers in Spring for GraphQL becomes clear and less error-prone.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — SchemaMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/SchemaMapping.html)
- [Spring for GraphQL — BatchMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/BatchMapping.html)
