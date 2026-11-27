# Custom-Named Query Mappings in Spring for GraphQL

In Spring for GraphQL, `@QueryMapping` connects a Java controller method to a field on the root `Query` of a GraphQL schema. By default, the field name is derived from the method name. When the Java name needs to differ from the public API name, you can specify the field name directly on the annotation using `name` or `value`.

Custom naming keeps Java method names clear according to codebase conventions while preserving stable GraphQL names per the API contract. It is important to distinguish the field name from the argument name: `@QueryMapping` changes the mapped field name, whereas `@Argument` specifies which argument is bound to the Java parameter.

## 1. Default Name Mapping

Consider the SDL schema:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

With the controller:

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

Spring infers the GraphQL field from the method name `bookById`, so the method is mapped to `Query.bookById`. The parent type `Query` is predefined by `@QueryMapping`; you do not need to declare it again.

If the Java method name matches the SDL field name, you do not need to pass the name attribute. This is concise and easy to read when both sides share the same naming convention.

## 2. Renaming the Field with `name`

Suppose the schema exposes a `book` field, while in Java you want an action-descriptive method name such as `findBookById`:

```graphql
type Query {
    book(id: ID!): Book
}
```

Declare the field name explicitly in the annotation:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping(name = "book")
    Book findBookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

In this case:

- The Java method name is `findBookById`.
- The field name in the GraphQL schema is `book`.
- `@QueryMapping` still maps to the root `Query` type.
- `@Argument("id")` binds the `id` argument of the `book` field to the Java parameter `id`.

Clients call the field by its schema name:

```graphql
query {
    book(id: "book-01") {
        id
        title
    }
}
```

Clients neither know nor need to know that the Java method is named `findBookById`. The method name is a server-side implementation detail; the GraphQL field name is part of the public API contract.

## 3. Using `value` Instead of `name`

`@QueryMapping` provides both `name` and `value` attributes. They are aliases that both specify the `field` name of `@SchemaMapping`.

The following two styles have the exact same meaning:

```java
@QueryMapping(name = "book")
Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

```java
@QueryMapping(value = "book")
Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Java also allows passing the value directly when an annotation has only a single attribute assigned via `value`:

```java
@QueryMapping("book")
Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Within a codebase, pick one consistent style. Using `name = "..."` is often easier to read when reviewers need to recognize immediately that it is the GraphQL field name. You do not need to specify both `name` and `value` on the same mapping.

## 4. Renaming the Field Does Not Rename Arguments

Field names and argument names are two separate naming levels in GraphQL.

Schema:

```graphql
type Query {
    lookupBook(bookId: ID!, includeReviews: Boolean): Book
}
```

The controller can use different Java method and parameter names:

```java
@QueryMapping(name = "lookupBook")
Book findBook(
        @Argument("bookId") String id,
        @Argument("includeReviews") Boolean withReviews) {

    return bookService.findById(id, withReviews);
}
```

Here:

- `name = "lookupBook"` maps the method to the `Query.lookupBook` field.
- `@Argument("bookId")` extracts the GraphQL argument `bookId` and assigns it to the Java parameter `id`.
- `@Argument("includeReviews")` extracts the argument `includeReviews` and assigns it to the Java parameter `withReviews`.

Corresponding query:

```graphql
query {
    lookupBook(bookId: "book-01", includeReviews: true) {
        id
        title
    }
}
```

If you only rename the field with `@QueryMapping(name = "lookupBook")` while the schema still declares the argument `bookId`, the Java parameter must bind the exact name `bookId`. `@QueryMapping` does not rename arguments, does not set default values, and does not override SDL nullability rules.

## 5. When Should You Use a Custom Name?

Custom names are useful in several scenarios:

| Scenario | Java Method Name | GraphQL Field Name |
|---|---|---|
| Want the Java name to clearly express the action | `findBookById` | `book` |
| Keep legacy API while refactoring code | `loadLegacyBook` | `bookById` |
| GraphQL name follows domain conventions | `searchCatalogEntries` | `catalogSearch` |
| Java name avoids internal abbreviations | `findCustomerAccount` | `account` |

Do not rename a field just to make Java code look shorter if doing so makes the API inconsistent. GraphQL field names should follow domain language, be clear to clients, and remain stable across releases.

If the API is already used by clients, renaming a GraphQL field is a breaking contract change. Custom naming lets you rename a Java method without changing the API, whereas changing `name` requires clients to migrate to the new field. During a migration, you can keep the old field in the schema, mark it deprecated, and route both resolvers to the same service until clients finish upgrading.

Example keeping the legacy API and exposing the new field:

```graphql
type Query {
    bookById(id: ID!): Book @deprecated(reason: "Use book instead")
    book(id: ID!): Book
}
```

```java
@QueryMapping(name = "book")
Book findBook(@Argument("id") String id) {
    return bookService.findById(id);
}

@QueryMapping(name = "bookById")
Book findBookLegacy(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Both public fields can call the same service method. Once clients stop using the old field, the team can remove the deprecated field according to the API versioning process.

## 6. `@QueryMapping` Is a Shortcut for `@SchemaMapping`

`@QueryMapping` is a composed annotation of `@SchemaMapping` with `typeName = "Query"`. Its `name` and `value` attributes are aliases for the `field` attribute of `@SchemaMapping`.

Therefore, this example:

```java
@QueryMapping(name = "book")
Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

has the same mapping intent as:

```java
@SchemaMapping(typeName = "Query", field = "book")
Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Use `@QueryMapping` when handling fields on the query root to clearly express the operation type. Use `@SchemaMapping` when mapping fields belonging to another object type, such as `Book.author`. `@QueryMapping` is not meant to route a method to `Mutation` or `Subscription`; those roots have their own annotations.

## 7. Combining Custom Names with Input Objects

Custom field names place no restrictions on argument types. If a query takes an input object, still use `@Argument` to bind the input as usual.

SDL:

```graphql
input BookSearchInput {
    keyword: String
    authorId: ID
    page: Int
}

type Query {
    searchBooks(criteria: BookSearchInput!): [Book!]!
}
```

Java:

```java
public record BookSearchInput(
    String keyword,
    String authorId,
    Integer page
) {}
```

```java
@QueryMapping(name = "searchBooks")
List<Book> findBooks(@Argument("criteria") BookSearchInput input) {
    return bookService.search(input);
}
```

`searchBooks` is the GraphQL field name, `findBooks` is the Java method name, and `criteria` is the argument name in the SDL. These three names can differ because they serve three distinct roles.

## 8. Testing Custom-Named Mappings

When using custom names, verify that clients can call the field by its exact SDL name and that the mapping does not accidentally depend on the Java method name.

Controller example:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping(name = "book")
    Book findBookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

Test with `GraphQlTester`:

```java
@GraphQlTest(BookController.class)
class BookQueryMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void mapsCustomGraphQlFieldName() {
        given(bookService.findById("book-01"))
            .willReturn(new Book("book-01", "GraphQL Basics"));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    book(id: "book-01") {
                        id
                        title
                    }
                }
                """)
            .execute();

        response.path("book.id").entity(String.class).isEqualTo("book-01");
        response.path("book.title").entity(String.class).isEqualTo("GraphQL Basics");
    }
}
```

This is an illustrative example; imports, the static import `given`, the `Book` class, `BookService`, and the SDL with `Query.book` must be provided in the test context. Depending on the Spring Boot version, the mock bean annotation may be `@MockitoBean` or `@MockBean`. The key point of the test is that the document invokes `book`, even though the Java method is named `findBookById`.

### Cases to Test

- Field is invoked by its custom SDL name and returns the right data.
- Arguments are bound by GraphQL name even when Java parameter names differ.
- Both legacy and new fields work together during API migration.
- A query calling the Java method name instead of the GraphQL field name must be rejected by GraphQL if the schema does not declare that field.
- Nullable fields, non-null fields, and resolver errors still follow the SDL contract.

## 9. Common Errors

**Using the method name instead of the configured field name.** When the annotation specifies `name = "book"`, clients must call `book`, not `findBookById`, unless the schema separately declares that field.

**Confusing the field name with the argument name.** `@QueryMapping(name = "lookupBook")` changes the field; `@Argument("bookId")` selects the argument. Check both against the SDL.

**Forgetting to declare the corresponding field in the SDL.** The annotation only registers a handler for a field; it does not add new fields to the schema automatically. Ensure the SDL declares the mapped field.

**Registering multiple handlers for the same field.** A field should not have multiple competing handlers in runtime wiring. Check controllers and mapping configurations to prevent duplicate registration.

**Using `@QueryMapping` for a non-Query-root field.** This annotation always maps to `Query`. For object type fields, use `@SchemaMapping`; for mutation or subscription roots, use the corresponding annotations.

**Renaming the API without evaluating clients.** Field names are a public contract. If a rename is needed, consider keeping the old field, marking it deprecated, and setting a clear removal plan.

## Conclusion

`@QueryMapping(name = "...")` or `@QueryMapping(value = "...")` lets you map a Java method to a custom field name on the root `Query`. If omitted, Spring uses the method name. Field name, argument name, and method name are three separate concepts: use `@QueryMapping` to select the field, `@Argument` to bind arguments, and choose method names according to Java conventions. Test with queries using the exact public names in the SDL to ensure mappings behave as expected.
