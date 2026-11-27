# Field mapping with `@SchemaMapping`

In Spring for GraphQL, `@SchemaMapping` is used to map a method in an annotated controller to a field of a GraphQL object type. The method receives the parent object as its source, can read additional field arguments, and returns the value that GraphQL needs to include in the response.

For example, a `Book` has an `author` field. If the Java `Book` object only contains `authorId`, retrieving author information requires calling a service or repository. `@SchemaMapping` lets you write a dedicated resolver for the `Book.author` field, while the schema still describes that field as a natural part of the `Book` object.

## What problem does field mapping solve?

GraphQL allows clients to select nested fields within a single operation. Given the schema:

```graphql
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
```

A client can fetch a book along with its author in a single request:

```graphql
query BookDetail($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      id
      name
    }
  }
}
```

The `Query.book` resolver looks up the book by ID. After receiving the `Book` object, GraphQL continues resolving the `id`, `title`, and `author` fields. If `author` is not a property already present on the Java object or requires calling business logic to fetch data, you need a field resolver.

`@SchemaMapping` is how Spring for GraphQL registers that field resolver from a Java method.

## Basic example with `@SchemaMapping`

Suppose the Java model has `authorId` but does not have a preloaded `Author` object:

```java
public class Book {
    private String id;
    private String title;
    private String authorId;

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getAuthorId() { return authorId; }
}

public class Author {
    private String id;
    private String name;

    public String getId() { return id; }
    public String getName() { return name; }
}
```

A controller can map the `Book.author` field as follows:

```java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId()).orElse(null);
    }
}
```

In this example, `typeName = "Book"` specifies the object type in the SDL, and `field = "author"` specifies the field to resolve. The `Book book` parameter is the source object passed down by GraphQL from the parent resolver. The method reads `authorId` from the source, calls `AuthorService`, and returns `Author`.

When the client selects `author`, GraphQL executes this method. The engine then continues resolving `Author.id` and `Author.name` according to the selection set.

## How Spring infers type and field

It is not always necessary to declare both `typeName` and `field`. Spring for GraphQL supports inference by convention:

- The field name is inferred by default from the method name.
- The object type name is inferred by default from the source parameter type.

For example, if the method has a source parameter of type `Book` and the method name is `author`, you can write it concisely:

```java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId()).orElse(null);
}
```

Spring understands this as a mapping for the `Book.author` field. The shorthand works well when Java class names and GraphQL types align. When the GraphQL type has a different name, the source is a base class, or you want to make the intent explicit, declare `typeName` and `field` explicitly.

You can change the mapped field name using the `field` attribute without renaming the Java method:

```java
@SchemaMapping(typeName = "Book", field = "primaryAuthor")
public Author loadAuthor(Book book) {
    return authorService.findById(book.getAuthorId()).orElse(null);
}
```

The `loadAuthor` method now handles the `Book.primaryAuthor` field in the schema.

## Source object and `@Source`

The source is the parent object that GraphQL already resolved at the previous field level. For `Book.author`, the source is a `Book` instance. A source is different from an argument: the source comes from the parent field's result, whereas an argument is data sent by the client for the current field.

You can explicitly mark the source parameter with `@Source` when you need to clarify the parameter's role:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.graphql.data.method.annotation.Source;

@SchemaMapping(typeName = "Book", field = "authorByLocale")
public Author authorByLocale(
        @Source Book book,
        @Argument String locale) {
    return authorService.findByBookAndLocale(book.getAuthorId(), locale);
}
```

In this example, `@Source` identifies the current `Book` object; `@Argument` reads the `locale` value from the field argument in the SDL:

```graphql
type Book {
  id: ID!
  title: String!
  authorByLocale(locale: String!): Author
}
```

When a method has a single clear source parameter, Spring can usually infer the source role by convention. The `@Source` annotation is useful when a method has multiple parameters or when you want to make the code easier to read.

## Reading arguments with `@Argument`

Nested fields can accept arguments just like top-level fields. For example, a client wants to choose a specific language version of a book's description:

```graphql
type Book {
  id: ID!
  title: String!
  description(locale: String!): String
}
```

The controller reads the argument with `@Argument`:

```java
@SchemaMapping(typeName = "Book", field = "description")
public String description(Book book, @Argument String locale) {
    return descriptionService.findText(book.getId(), locale);
}
```

`book` is the source object; `locale` is the argument passed by the client. If the Java parameter name differs from the SDL argument name, you can specify the argument name in the annotation using the syntax supported by Spring for GraphQL.

For an input object, you can accept a corresponding DTO or record:

```graphql
input ReviewFilter {
  minimumRating: Int
  language: String
}

type Book {
  reviews(filter: ReviewFilter): [Review!]!
}
```

```java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(Book book, @Argument ReviewFilter filter) {
    return reviewService.findByBook(book.getId(), filter);
}
```

The input Java type must be compatible with how Spring converts arguments. For complex inputs, use a clearly structured DTO or record and perform validation at the API boundary.

## Mapping multiple fields in the same controller

You can place `@SchemaMapping(typeName = "Book")` at the class level to share the GraphQL type across the mapping methods inside. Then each method only needs `@SchemaMapping`, and the field name can be inferred from the method name:

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookController(
            AuthorService authorService,
            ReviewService reviewService) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId()).orElse(null);
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.getId());
    }
}
```

Here both methods are mapped to the `Book` object type; the method names correspond to the `author` and `reviews` fields respectively. This grouping is useful when one controller is responsible for multiple fields of the same GraphQL type.

Avoid putting every resolver for the entire schema into one large controller. You can split controllers by domain or GraphQL type to keep dependencies and responsibilities clear.

## `@SchemaMapping` and the default PropertyDataFetcher

GraphQL Java has a default `PropertyDataFetcher` mechanism to retrieve values from a source object. If the Java object already has a getter or property matching the SDL field, Spring for GraphQL generally does not need a separate `@SchemaMapping` method.

For example:

```java
public class Book {
    private String id;
    private String title;

    public String getId() { return id; }
    public String getTitle() { return title; }
}
```

With the SDL:

```graphql
type Book {
  id: ID!
  title: String!
}
```

When the `Query.book` resolver returns `Book`, GraphQL can read `id` and `title` directly from the object. There is no need to create a mapping just to return the exact getter value.

Use `@SchemaMapping` when a field needs to:

- Call a service or repository to fetch related data.
- Compute a value from multiple properties of the source.
- Convert data into an appropriate GraphQL type.
- Apply business rules or check access permissions.
- Return an asynchronous result from another service.

Do not create unnecessary resolvers for fields that merely reflect existing properties. Fewer mappings make the schema and Java models easier to maintain.

## Distinguishing `@SchemaMapping` from `@QueryMapping` and `@MutationMapping`

All three annotations register a DataFetcher from an annotated controller, but they target different positions:

| Annotation | Mapping target | Example |
| --- | --- | --- |
| `@QueryMapping` | Field on the Query root type. | `Query.book` |
| `@MutationMapping` | Field on the Mutation root type. | `Mutation.createBook` |
| `@SchemaMapping` | Field of a GraphQL object type, typically a nested field. | `Book.author` |

Query root example:

```java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id).orElse(null);
}
```

Nested field example:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId()).orElse(null);
}
```

`@QueryMapping` is a shortcut for a field on the Query root. There is no need to write `@SchemaMapping(typeName = "Query", field = "book")` when implementing a standard Query field. Using the annotation that matches the operation type makes the code easier to read.

## Asynchronous mapping

A field resolver can call an asynchronous service and return a type supported by GraphQL Java, such as `CompletableFuture` or Reactor `Mono` in a Spring for GraphQL application.

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(Book book) {
    return authorService.findByIdAsync(book.getAuthorId());
}
```

Or with a reactive service:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Mono<Author> author(Book book) {
    return authorService.findByIdReactive(book.getAuthorId());
}
```

These examples assume the service genuinely provides an asynchronous/non-blocking API. If the service calls synchronous JDBC/JPA and only then wraps the result with `Mono.just`, the call is still blocking. For blocking I/O in WebFlux, offload to an appropriate scheduler/executor or use a non-blocking driver.

## Field-level security

`@SchemaMapping` is a convenient place to check access permissions for nested field data. For example, users can view a book, but only editors can read the moderation note:

```graphql
type Book {
  id: ID!
  title: String!
  moderationNote: String
}
```

```java
@SchemaMapping(typeName = "Book", field = "moderationNote")
public String moderationNote(Book book, Principal principal) {
    authorizationService.checkCanViewModerationNote(principal, book.getId());
    return bookService.getModerationNote(book.getId());
}
```

Do not rely on the client not knowing the field name. If a field exists in the schema, a client can attempt to query it directly. The resolver or service must authenticate the user and check permissions for the specific resource.

In multi-tenant applications, the check must include tenant scope. Never trust a tenant value from a client-supplied argument as proof of authorization.

## N+1 when resolving relational fields

`@SchemaMapping` can cause an N+1 problem if each parent object calls a repository individually to load related data.

Example query:

```graphql
query Books {
  books {
    id
    title
    author {
      id
      name
    }
  }
}
```

If the `books` Query returns 100 books and the `Book.author` resolver executes one database query per book, the system may run 1 query to fetch books and 100 queries to fetch authors.

There are two common approaches in Spring for GraphQL:

- **DataLoader:** the resolver calls `load(authorId)` to collect keys within the same request; the batch loader queries multiple authors at once and returns results by key.
- **`@BatchMapping`:** declare a method that receives a list of source objects and returns related data in a batch. Spring for GraphQL registers the DataLoader batching mechanism for that field.

Example of `@BatchMapping` for the author field:

```java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> authors(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();

        Map<String, Author> authorsById = authorService.findAllByIds(authorIds);

        return books.stream().collect(Collectors.toMap(
                book -> book,
                book -> authorsById.get(book.getAuthorId())));
    }
}
```

The example assumes the service returns a map keyed by author ID and each Book has one Author. For one-to-many or many-to-many relationships, the return type and matching logic will differ. `@BatchMapping` is one way to register a batch resolver for a field; you should not simultaneously write a separate `@SchemaMapping` for that same field without a clear reason.

Batching reduces the number of data calls, but you still need pagination and list size limits. Do not load thousands of objects at once just because you have a DataLoader.

## Testing `@SchemaMapping`

You can use `GraphQlTester` to verify an operation that goes through the Query root and resolves nested fields:

```java
@Test
void bookQueryResolvesAuthor() {
    graphQlTester.document("""
        query {
          book(id: "book-10") {
            id
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
```

In addition to success cases, you should verify:

- The field and type in the annotation match the SDL.
- The source object is passed correctly from the parent field.
- Arguments are bound properly, including input objects and null cases.
- When related data does not exist, the result conforms to nullability.
- Exceptions are mapped to appropriate GraphQL errors.
- Users lacking permission cannot read sensitive fields.
- Lists of many objects do not trigger unexpected N+1 queries.
- Asynchronous mappings handle success, errors, and timeouts.

When testing batching, you can verify the number of service/repository calls to ensure multiple source objects are processed in a single batch. A unit test that only calls the controller method directly is not sufficient to confirm that the mapping is registered in the GraphQL schema.

## Common issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Field returns null even though the source has related data | `typeName`, `field`, or method name does not match the SDL. | Cross-check the annotation against the schema. |
| Spring fails to infer the GraphQL type properly | Java class name does not match the object type name or the source parameter is ambiguous. | Declare `typeName` explicitly. |
| `@Argument` is always null | Incorrect argument name or the client is not sending variables properly. | Check the SDL, operation, and argument name. |
| Resolver does not receive the parent object | Method signature lacks an appropriate source parameter. | Declare the source parameter or `@Source` explicitly. |
| Resolver runs but the query is slow | Each source object calls the repository individually, causing N+1. | Use DataLoader or `@BatchMapping`. |
| Unexpected handler is invoked | The same field is registered through multiple mapping mechanisms. | Choose one handler per field and inspect the runtime wiring. |
| Users can read internal fields | Resolver lacks resource-level authorization. | Verify the principal, permissions, and tenant in the resolver/service. |

## Key takeaways

`@SchemaMapping` registers a field resolver for a GraphQL object type. Spring can infer the field from the method name and the type from the source parameter; when clarity is needed, use `typeName` and `field`. The source object is the value returned by the parent field, while `@Argument` reads data sent by the client to the current field.

GraphQL Java includes a default `PropertyDataFetcher`, so you do not need to create a mapping for fields that simply read existing properties. Use `@SchemaMapping` when you need to call a service, compute values, check permissions, or process related data. For lists of objects, watch out for N+1 and consider DataLoader or `@BatchMapping` to batch queries.
