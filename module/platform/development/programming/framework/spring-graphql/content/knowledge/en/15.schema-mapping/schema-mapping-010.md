# Class-level `@SchemaMapping`

In Spring for GraphQL, `@SchemaMapping` is usually placed on methods to map a Java method to a field of a GraphQL object type. When a controller contains multiple resolvers that all handle fields of the same GraphQL type, you can place `@SchemaMapping(typeName = "...")` at the class level to declare a shared default type for the mapping methods inside the controller.

This organization groups resolvers by GraphQL type. For example, a `BookController` can handle `Book.author`, `Book.publisher`, and `Book.reviews`; the type name `Book` only needs to be declared once on the class. Methods still need their own mapping annotation to indicate which field they handle.

## 1. What is class-level `@SchemaMapping`?

`@SchemaMapping` can be used at two levels:

- **Method level**: identifies the specific field to map and can optionally specify the GraphQL type owning that field.
- **Class level**: provides a default `typeName` for handler methods inside the controller.

Example:

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        // Resolve Book.author
    }

    @SchemaMapping
    public Publisher publisher(Book book) {
        // Resolve Book.publisher
    }
}
```

Both methods are mapped to fields of the `Book` GraphQL type. Here, `typeName = "Book"` on the class acts as the default; `field` is inferred from each method name (`author` and `publisher`).

Important: placing the annotation at the class level does not automatically turn every method in the class into a resolver. Each handler method still needs an appropriate mapping annotation, such as `@SchemaMapping` or `@BatchMapping`. The class-level annotation only shares the type configuration; it does not declare fields and does not replace method-level mappings.

## 2. Preparing the GraphQL schema

Suppose a library application has this schema:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
    publisher: Publisher
    reviewCount: Int!
}

type Author {
    id: ID!
    name: String!
}

type Publisher {
    id: ID!
    name: String!
}
```

`Book` has three fields that require custom data-fetching logic: `author`, `publisher`, and `reviewCount`. Fields like `id` and `title` can be read directly from the source object by the default property data fetcher if the Java object provides matching accessors.

Example Java record for the source object:

```java
public record Book(
    String id,
    String title,
    String authorId,
    String publisherId
) {}
```

You do not need to write `@SchemaMapping` for every field. Only create resolvers when a field needs to query another data source, compute a value, check permissions, or run custom logic.

## 3. Declaring the default type on the controller

The controller is registered as a Spring bean with `@Controller`. `@SchemaMapping(typeName = "Book")` at the class level declares the default GraphQL type for eligible handler methods:

```java
package com.example.graphql.book;

import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    private final AuthorService authorService;
    private final PublisherService publisherService;

    public BookController(
            AuthorService authorService,
            PublisherService publisherService) {
        this.authorService = authorService;
        this.publisherService = publisherService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping
    public Publisher publisher(Book book) {
        return publisherService.findById(book.publisherId());
    }
}
```

Spring for GraphQL reads the class-level annotation and then uses `Book` as the default type when registering `@SchemaMapping` methods in the controller. Each method receives `Book` as its source/parent object and returns data for the corresponding field.

`@Controller` and `@SchemaMapping` serve different roles. `@Controller` registers the class into the Spring application context; `@SchemaMapping` supplies metadata for Spring for GraphQL to register handler methods. If the class is not component-scanned or registered as a bean, the configurer cannot discover its mappings.

## 4. Inferring the field name from the method vs. explicit declaration

When a method-level `@SchemaMapping` omits `field`, Spring uses the method name as the GraphQL field name.

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book source) {
        return authorService.findById(source.authorId());
    }
}
```

The `author` method maps to `Book.author`. The parameter name `source` does not affect the field name; the parameter type `Book` represents the source object.

If the method name differs from the field name in the SDL, specify `field` on the method:

```java
@SchemaMapping(field = "reviewCount")
public Integer countReviews(Book book) {
    return reviewService.countByBookId(book.id());
}
```

The class-level annotation supplies `typeName = "Book"`, while the method-level annotation specifies the `reviewCount` field. Separating the two values allows Java method names to express intent in code while still mapping accurately to the GraphQL contract.

You can declare both type and field on the method when you want an explicit mapping or need to override the default type:

```java
@SchemaMapping(typeName = "Magazine", field = "reviewCount")
public Integer countMagazineReviews(Magazine magazine) {
    return reviewService.countByMagazineId(magazine.id());
}
```

In this case, the method-level `typeName` specifies the exact type for that mapping. Only override when the method truly belongs to a different GraphQL type; if a controller holds unrelated type groups, consider splitting controllers to keep boundaries clear.

## 5. Passing arguments to a field mapping

Fields on an object type can accept arguments just like fields on root types. `@Argument` reads values from the arguments of the field currently being resolved.

SDL:

```graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
```

Resolver:

```java
@SchemaMapping
public List<Review> reviews(
        Book book,
        @Argument("first") Integer first) {
    return reviewService.findFirstByBookId(book.id(), first);
}
```

Because the class-level `typeName` is `Book`, this method maps to `Book.reviews`. `Book book` is the source object; `@Argument("first")` receives the `first` argument passed by the client. Specify the argument name explicitly if you do not want to rely on Java parameter name metadata.

Clients can query:

```graphql
query {
    book(id: "book-42") {
        title
        reviews(first: 5) {
            id
            rating
            comment
        }
    }
}
```

Class-level `@SchemaMapping` does not change how arguments are passed. It only supplies the default type; handler methods still receive the source object and arguments via Spring for GraphQL's parameter resolution mechanism.

## 6. Splitting resolvers by GraphQL type

Class-level mapping is most effective when methods in a controller handle the same GraphQL type and belong to the same business area. Avoid cramming all resolvers across the entire API into one class merely to reduce file count.

For example, you can organize files as:

```text
graphql/
└── book/
    ├── BookQueryController.java
    ├── BookController.java
    ├── AuthorController.java
    └── ReviewController.java
```

- `BookQueryController` handles root fields such as `Query.book`.
- `BookController` uses `@SchemaMapping(typeName = "Book")` for `Book` fields.
- `AuthorController` uses `@SchemaMapping(typeName = "Author")` for `Author` fields.
- `ReviewController` handles fields belonging to `Review` when custom logic is needed.

Example of a dedicated controller for `Author`:

```java
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
```

The `books` method maps to `Author.books`, because the controller's default type is `Author`. Each controller thus focuses on the fields of one type and is easy to inspect when the schema evolves.

## 7. Distinguishing class-level `@SchemaMapping` from `@QueryMapping`

Class-level `@SchemaMapping` is typically used to share the owning type across resolvers of an object type, such as `Book.author` or `Author.books`. Root operations have dedicated annotations:

- `@QueryMapping` maps to the `Query` root type.
- `@MutationMapping` maps to the `Mutation` root type.
- `@SubscriptionMapping` maps to the `Subscription` root type.

For example, place root queries in a separate controller:

```java
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
```

Do not put `@SchemaMapping(typeName = "Book")` on a controller dedicated to root queries. Root mappings already have specialized annotations and their own root type; separating controllers avoids mixing scopes between `Query.book` and `Book.author`.

## 8. Combining class-level mapping with `@BatchMapping`

When a `Book` field needs to be resolved for multiple parent objects, you can use `@BatchMapping` to batch data-loading requests.

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> authors(List<Book> books) {
        return authorService.findAuthorsByBooks(books);
    }
}
```

In this example, `@BatchMapping` explicitly declares both `typeName` and `field` to express the full `Book.author` mapping. The method accepts multiple source objects and returns a result mapping each `Book` to its corresponding `Author`. For regular `@SchemaMapping` methods in the controller, `typeName` can be shared from the class-level annotation.

With batch methods, ensure results are mapped accurately for every source object, including cases where no author exists. When using a `Map`, keys must be consistent with source objects; when using a `List`, result order must match input order according to the batch loader contract. When you need finer control over keys, caching, or complex loading, use `BatchLoaderRegistry` and `DataLoader`.

Class-level `@SchemaMapping` avoids repeating the type name across mappings in the same controller; it does not solve N+1 on its own. Request batching is handled by batch mapping/`DataLoader` and should be verified by checking repository or service invocation counts.

## 9. Avoid duplicate mappings

Every GraphQL type and field pair must have one clear resolution path. Avoid declaring the same field on multiple methods or registering both an annotated mapping and a custom `DataFetcher` for that exact field in custom runtime wiring.

For example, do not have two methods mapping `Book.author`:

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(field = "author")
    public Author loadAuthor(Book book) {
        return anotherService.load(book.authorId());
    }
}
```

Both methods declare a resolver for `Book.author`; registration can cause errors or conflicts when building the runtime. Keep a single mapping or remove the old one once responsibilities are clearly defined.

If the class-level type is `Book` while a method-level annotation overrides it to `Magazine`, make sure that method genuinely handles a `Magazine` field. Overrides should not be used to mask unclear controller boundaries.

## 10. Testing class-level mappings with `GraphQlTester`

`GraphQlTester` can test operations flowing through the schema and controller mappings. Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest({BookQueryController.class, BookController.class})
class BookSchemaMappingTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void resolvesBookAuthor() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
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
```

The example assumes the test context has mocks or test beans for `BookService` and `AuthorService` returning data matching the ID in the query. The test verifies that the root query returns `Book` and that the class-level mapping routes `Book.author` to the right handler method.

You should also test:

- Two or more methods in the same controller sharing the default type.
- A method with an explicit `field` differing from the method name.
- A method-level `typeName` override when genuinely required.
- Nested field arguments and source objects being passed properly.
- Batch mapping with multiple source objects and missing related data.
- No duplicate mappings between controllers and custom runtime wiring.

Slice tests may need to declare the relevant controllers explicitly and supply mocks for their dependencies. To test full auto-configuration, schema resources, and HTTP transport, use an appropriate integration test rather than relying solely on `@GraphQlTest`.

## 11. Common issues when using class-level `@SchemaMapping`

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Method is not registered | Method lacks a mapping annotation | Add `@SchemaMapping` or the appropriate handler annotation on the method |
| Field is mapped to the wrong type | Class-level `typeName` does not match the SDL | Verify the GraphQL object type name |
| Field name does not match | Method name differs from the field in the SDL | Declare `field` explicitly |
| Controller is not discovered | Missing `@Controller` or outside component scan | Check Spring beans and package scanning |
| Argument receives `null` | Incorrect argument name or binding type | Use `@Argument("...")` and check the SDL |
| Two methods handle the same field | Duplicate mapping declared | Keep one handler per type/field |
| Root query field does not execute | Mistakenly using object type mapping for a root operation | Use `@QueryMapping` in an appropriate controller |
| Query still has N+1 | Class-level mapping only shares the type name | Use `@BatchMapping` or `DataLoader` |

When debugging, trace three things: the GraphQL type owning the field, the field name in the SDL, and the registered Java method. Then check the class-level default type, whether the field is inferred from the method name or explicitly declared, and whether the controller is actually present in the application context.

## 12. Checklist before using class-level `@SchemaMapping`

- Do the handlers in the controller share the same GraphQL object type?
- Does `@Controller` register the class as a Spring bean?
- Does `typeName` on the class match the type name in the SDL?
- Does every handler method have an appropriate mapping annotation?
- Can the field be inferred from the method name, or is an explicit `field` needed?
- Is any method-level override genuinely necessary and targeting the right type?
- Are source objects and arguments declared properly?
- Are root operations placed in controllers using `@QueryMapping`, `@MutationMapping`, or `@SubscriptionMapping` appropriately?
- Are there any duplicate resolvers or conflicting custom data fetchers?
- Have fields at risk of N+1 been evaluated for batch mapping/`DataLoader`?
- Do tests cover multiple mappings within the same controller?

Class-level `@SchemaMapping` helps group resolvers by GraphQL object type and avoids repeating `typeName` on every method. The class-level annotation only supplies the default type; each method still requires a mapping annotation, and field names must match the SDL contract. When a controller focuses on a single type, mappings are clearly named, and tests cover the critical fields, Spring for GraphQL code stays easy to read, debug, and extend alongside the schema.
