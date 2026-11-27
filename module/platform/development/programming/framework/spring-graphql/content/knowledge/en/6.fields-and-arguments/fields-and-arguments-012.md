# Field Resolvers and Parent Source in Spring for GraphQL

In GraphQL, every field selected in a query must be resolved to a value. A **field resolver** is the component that provides that value. When GraphQL traverses from a parent object down to a child field, the parent object is passed to the child field's resolver under the name **source** or **parent source**.

In Spring for GraphQL, `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` methods connect schema fields to Java methods. Understanding parent source helps you see where a child field's data comes from, when you need a dedicated resolver, and when GraphQL can read object properties directly.

## 1. What is a field resolver?

Consider the schema:

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

The client sends a query:

```graphql
query {
    bookById(id: "book-01") {
        id
        title
        author {
            id
            name
        }
    }
}
```

GraphQL does not treat the entire query as a single function call. It resolves each selected field:

1. The root field `Query.bookById` looks up a book by the `id` argument.
2. From the returned `Book` object, GraphQL resolves `id`, `title`, and `author`.
3. When resolving `author`, GraphQL uses the `Book` object as the source for that field.
4. Once it has the `Author` object, GraphQL proceeds to resolve `Author.id` and `Author.name`.

Each field can use the default data fetcher or an application-provided resolver. A resolver is typically needed when the field must call a service, compute a value, check context, or load a relationship not already present on the parent object.

## 2. What is parent source?

The **parent source** is the object on which GraphQL is currently resolving a child field. It is the result returned by the parent field in the query execution tree.

For example, when the `Query.bookById` resolver returns a `Book` object, that object becomes the source when GraphQL resolves `Book.id`, `Book.title`, and `Book.author`. If `Book.author` returns an `Author` object, that `Author` object in turn becomes the source for `Author.id` and `Author.name`.

You can visualize the data flow like this:

```text
Query.bookById(id)
        |
        | returns Book
        v
  source = Book
    |       |       |
    id    title   author
                    |
                    | returns Author
                    v
              source = Author
                  |    |
                  id  name
```

The source does not have to be a JPA entity or an object fetched directly from a database. It can be a Java record, POJO, DTO, projection, or `Map`, as long as it is returned by the parent resolver and can supply data for child fields.

The key point is that the child field resolver receives the exact parent object at the location being resolved. If a query returns a list of books, a field resolver on `Book` runs for each item, receiving the corresponding `Book` as its source each time.

## 3. Default field resolver and PropertyDataFetcher

Not every field requires writing a `@SchemaMapping` method. GraphQL Java includes a default data fetcher to read properties from the source object. This mechanism is commonly called `PropertyDataFetcher`.

Example Java record:

```java
public record Book(
    String id,
    String title,
    String authorName
) {}
```

With schema:

```graphql
type Book {
    id: ID!
    title: String!
    authorName: String!
}
```

If the parent resolver returns `Book`, GraphQL can retrieve `id`, `title`, and `authorName` from the record's matching accessors. There is no need to create three separate resolver methods just to return properties already present on the object.

For JavaBeans, getters like `getTitle()` or `isAvailable()` are commonly used to read properties. For `Map`, the data fetcher can read values by key. Make sure GraphQL field names match property names accessible to the data fetcher.

Example controller handling only the root field:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book bookById(@Argument String id) {
        return bookService.findById(id);
    }
}
```

When `BookService` returns a record or POJO with matching properties, GraphQL resolves simple fields automatically. You only need to write custom resolvers for fields requiring additional logic.

## 4. Writing a field resolver with `@SchemaMapping`

Suppose the `Book` object only stores `authorId`, while author details are managed by `AuthorService`:

```java
public record Book(String id, String title, String authorId) {}

public record Author(String id, String name) {}
```

Schema:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    authorId: ID!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

`author` is not an existing property on the `Book` record. We need a resolver to look up the author from `authorId`:

```java
@Controller
class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    BookController(BookService bookService, AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    Book bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    Author author(Book source) {
        return authorService.findById(source.authorId());
    }
}
```

In the `author(Book source)` method, the `source` parameter is the `Book` object returned by the parent field `bookById`. The resolver reads `source.authorId()` to load the `Author` object, and GraphQL then continues resolving the child fields of `Author`.

### Name mapping rules

`@SchemaMapping` lets you explicitly declare `typeName` and `field`:

```java
@SchemaMapping(typeName = "Book", field = "author")
Author author(Book source) {
    // ...
}
```

In the typical case, Spring can infer the type from the source parameter type and the field from the method name. Thus, the following example can also map to `Book.author`:

```java
@SchemaMapping
Author author(Book book) {
    return authorService.findById(book.authorId());
}
```

When Java names differ from GraphQL names or when you want to make intent explicit, declare `typeName` and `field` explicitly. `@SchemaMapping` can be placed on controller methods; Spring uses that metadata to register a data fetcher for the corresponding field.

## 5. Distinguishing parent source from `@Argument`

Both parent source and arguments can appear in a resolver method's signature, but they represent two different data sources:

| Component | Where does the data come from? | Example |
|---|---|---|
| Parent source | Already-resolved parent object | `Book source` in the `Book.author` resolver |
| `@Argument` | Argument on the current field passed by the client | `@Argument String id` in `Query.bookById` |

Query example:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    reviews(minRating: Int): [Review!]!
}
```

The root resolver receives the `id` argument:

```java
@QueryMapping
Book bookById(@Argument String id) {
    return bookService.findById(id);
}
```

The child field resolver receives both the `Book` source and the `minRating` argument of the `reviews` field:

```java
@SchemaMapping(typeName = "Book", field = "reviews")
List<Review> reviews(Book source, @Argument Integer minRating) {
    return reviewService.findByBookId(source.id(), minRating);
}
```

Here `source.id()` identifies the book being resolved; `minRating` is the filter condition sent by the client for the `reviews` field. Do not confuse the root query's `id` with the child field's argument: each resolver receives the arguments belonging to the field it handles.

## 6. Execution flow across multiple object levels

With the query:

```graphql
query {
    bookById(id: "book-01") {
        title
        author {
            name
        }
    }
}
```

The execution flow breaks down into steps:

1. Spring invokes the `Query.bookById` resolver, passing `id` from `@Argument`.
2. The resolver returns the `Book` object.
3. GraphQL uses `Book` as the source to retrieve `title` via the default property fetcher.
4. GraphQL invokes the `Book.author` resolver, passing the same `Book` object as the source.
5. The resolver returns `Author`.
6. GraphQL uses `Author` as the source to retrieve `name`.

If the client requests only `title` and not `author`, the `Book.author` resolver does not need to run. GraphQL resolves only the fields remaining in the selection set after applying selection-control directives such as `@skip` and `@include`.

This allows the API to fetch data tailored to the query structure. However, it also means a field resolver can be invoked multiple times when the field appears on many parent objects in a list or nested branch.

## 7. Parent source, null, and resolution errors

If a parent resolver returns `null` for a nullable field, GraphQL has no source object to continue resolving that object's child fields. The value of the corresponding branch will be `null`.

If the parent field is declared Non-null yet the resolver returns `null`, GraphQL raises an execution error and applies null propagation rules. The error may bubble up to the nearest nullable field, depending on the schema's Non-null structure.

Example:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    author: Author
}
```

If no book is found, `bookById` can return `null` and the client receives `bookById: null`. If a book is found without an author, the `author` resolver can return `null` because this field is nullable. Choose nullability that aligns with business rules and actual data availability.

If a service throws an exception inside a resolver, the error is handled by Spring for GraphQL / GraphQL Java's exception handling mechanism. Translate business errors into appropriate client-facing information using `DataFetcherExceptionResolver` or a configured error handler, while avoiding exposing sensitive internal details in the response.

## 8. Parent source and query performance

A resolver typically works well when handling a single parent object. However, when a query returns a large list, relationship resolvers can create an N+1 problem.

Example query:

```graphql
query {
    books {
        id
        title
        author {
            name
        }
    }
}
```

If `books` returns 100 books and the `Book.author` resolver calls the database once per book, the application may execute 1 query for books plus 100 queries for authors. This is the N+1 problem.

The parent source is still necessary to know which book each `author` field belongs to, but data loading can be grouped. Spring for GraphQL supports `@BatchMapping` and integrates with DataLoader to batch-load data, reducing database or service calls. For example, a batch resolver receives a list of `Book` instances and returns a mapping from each book to its corresponding author.

Not every field resolver needs batching. For objects that already contain all needed data, the default property fetcher is usually simple and efficient. Add resolvers only when logic is needed, and consider batching when a resolver loads relationships repeatedly across many source objects.

## 9. Testing field resolvers and parent source

You can use `GraphQlTester` to test the full flow from query to field resolvers. Scenarios to cover include:

- Root query field receives the expected argument and returns the expected parent object.
- Fields whose properties already exist on the source are resolved properly by the default property fetcher.
- Relationship fields using `@SchemaMapping` receive the expected parent source and return the child object.
- Child fields receive their own arguments alongside the source parameter.
- When the parent object or relationship does not exist, the response obeys the nullability in SDL.
- When a resolver throws an error, the response contains appropriate `errors` without leaking internal details.
- When a query returns multiple parent objects, check repository or service call counts to detect N+1 issues.

Example testing with `GraphQlTester`:

```java
@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void resolvesAuthorFromParentBook() {
        Book book = new Book("book-01", "GraphQL Basics", "author-01");
        Author author = new Author("author-01", "An Nguyen");
        given(bookService.findById("book-01")).willReturn(book);
        given(authorService.findById("author-01")).willReturn(author);

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    bookById(id: "book-01") {
                        title
                        author {
                            name
                        }
                    }
                }
                """)
            .execute();
        response.path("bookById.title").entity(String.class).isEqualTo("GraphQL Basics");
        response.path("bookById.author.name").entity(String.class).isEqualTo("An Nguyen");
    }
}
```

This is an illustrative example of the test structure; imports and the static import for `given` are omitted, and the matching SDL schema must be present in the test context. Depending on the Spring Boot version, the mock bean annotation may be `@MockitoBean` or `@MockBean`. You can also verify that `authorService.findById("author-01")` was called with the ID taken from the parent source.

## 10. Common mistakes

**Confusing parent source with arguments.** `Book source` is the parent object; `@Argument` extracts the current field's argument value. Be clear about whether data comes from the parent field's result or from the query sent by the client.

**Writing resolvers for every field.** If a field already corresponds to an accessible property on a record, POJO, or Map, the default property fetcher can handle it. Manual resolvers are only needed when extra logic is required.

**Field name not matching the property.** A GraphQL field `authorName` will not automatically read a property `author_name` or a different name without corresponding configuration or a converter resolver.

**Source lacking the expected type or data.** Inspect the object that the parent resolver actually returns. The child resolver receives that object as its source; it does not automatically receive another entity just because the schema has a matching type name.

**Querying relationships inside each resolver without watching for N+1.** For lists with many parent objects, count service/repository calls and consider `@BatchMapping` or DataLoader.

**Failing to handle missing parents or relationships.** Choose appropriate nullability in SDL and ensure resolvers return values or errors according to the contract.

## Conclusion

Field resolvers provide the value for each GraphQL field. The parent source is the object returned by the parent field and passed down to child field resolvers. In Spring for GraphQL, `@QueryMapping` handles root fields while `@SchemaMapping` handles fields on objects; `@Argument` provides client-supplied inputs for the current field. Leverage the default property fetcher for existing properties, write resolvers for relationships or needed logic, and use batching when multiple parent objects must load related data.
