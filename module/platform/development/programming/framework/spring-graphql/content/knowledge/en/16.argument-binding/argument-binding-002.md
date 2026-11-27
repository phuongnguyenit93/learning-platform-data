# @Arguments

In Spring for GraphQL annotated controllers, `@Arguments` is used to bind **all arguments of the current GraphQL field** into a single method parameter. That parameter can be a DTO/record that groups the arguments or a `Map<String, Object>` when flexible handling is needed.

For example, a search field might accept `keyword`, `categoryId`, `minRating`, `page`, and `size`. Instead of declaring five separate Java parameters, the controller can receive a single `SearchBooksArguments` object using `@Arguments`. Spring for GraphQL reads the arguments resolved by GraphQL, converts them into the appropriate Java types, and invokes the controller method.

`@Arguments` is especially useful when a field has multiple arguments belonging to the same use case. It does not retrieve all operation variables or the entire query content; it only binds the arguments belonging to the field that the resolver is currently handling.

## 1. Distinguishing @Arguments and @Argument

The two annotations have similar names but different purposes:

| Annotation | Binding scope | Example |
| --- | --- | --- |
| `@Argument("filter")` | A specific named argument of the field | Bind the `filter` argument into `BookFilter` |
| `@Arguments` | All arguments of the current field | Bind `keyword`, `page`, `size` into `SearchBooksArguments` |

Suppose the schema is:

```graphql
type Query {
    searchBooks(
        keyword: String!
        categoryId: ID
        minRating: Int
        page: Int = 0
        size: Int = 20
    ): [Book!]!
}
```

If you want to receive `keyword` and `page` individually, use `@Argument`:

```java
@QueryMapping
public List<Book> searchBooks(
        @Argument("keyword") String keyword,
        @Argument("page") Integer page) {
    return bookService.search(keyword, page);
}
```

If you want to group all arguments into a single object, use `@Arguments`:

```java
public record SearchBooksArguments(
        String keyword,
        String categoryId,
        Integer minRating,
        Integer page,
        Integer size) {
}

@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookService.search(arguments);
}
```

With `@Arguments`, the object's properties correspond to the argument names in the SDL. `keyword` maps to `keyword`, `categoryId` maps to `categoryId`, and so on for the remaining fields.

## 2. Binding all arguments into a DTO or record

This is the common approach when a field has multiple parameters that together describe search criteria, pagination, or a business command.

Schema:

```graphql
type Query {
    searchBooks(
        keyword: String!
        categoryId: ID
        minRating: Int
        page: Int = 0
        size: Int = 20
    ): [Book!]!
}
```

Java record:

```java
public record SearchBooksArguments(
        String keyword,
        String categoryId,
        Integer minRating,
        Integer page,
        Integer size) {
}
```

Controller:

```java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
        return bookService.search(arguments);
    }
}
```

The client can pass a subset of the arguments:

```graphql
query {
    searchBooks(keyword: "Spring", minRating: 4) {
        id
        title
    }
}
```

Default values in the SDL are applied according to GraphQL rules. In the example, if the client does not pass `page` and `size`, the default values `0` and `20` are used. Nullable arguments without defaults may have no value; therefore, the DTO should usually use nullable Java types such as `Integer` instead of primitive `int` if you need to distinguish an absent value from `0`.

Records are a good fit because their components have clear names, short constructors, and immutable data. For regular Java classes, Spring can bind via constructor or property binding. If using constructor binding, ensure constructor parameter names can be discovered at runtime; configure compilation to retain parameter name metadata (`-parameters`) when needed. With property binding, the class needs an appropriate constructor along with setters or writable properties.

## 3. Binding into Map<String, Object>

When the argument structure changes dynamically or needs to be processed by name at runtime, you can receive all arguments as a Map:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments Map<String, Object> arguments) {
    String keyword = (String) arguments.get("keyword");
    String categoryId = (String) arguments.get("categoryId");
    Integer minRating = (Integer) arguments.get("minRating");
    Integer page = (Integer) arguments.get("page");
    Integer size = (Integer) arguments.get("size");

    return bookService.search(keyword, categoryId, minRating, page, size);
}
```

A Map allows checking keys, handling a dynamic set of arguments, or forwarding data to another component. In return, the code loses some type safety: an incorrect cast can cause a `ClassCastException`, and key name typos are only detected at runtime.

Values in the Map are the result of GraphQL coercion and the binding process. Scalars may appear as `String`, `Integer`, `Boolean`, `ID`, or the Java type configured by the scalar/coercing implementation. Input objects typically have a nested Map structure, and lists become corresponding collections. If you use a Map, validate types and values before calling the service; avoid direct casts when data comes from the client.

For most stable use cases, a DTO/record is easier to read, easier to test, and supports Bean Validation. Use a Map when you genuinely need a dynamic structure or low-level manipulation.

## 4. Binding arguments with nested input objects

`@Arguments` receives all field-level arguments. If an argument is an input object, that object is bound as a nested property inside the DTO.

Schema:

```graphql
input BookFilter {
    categoryIds: [ID!]
    minRating: Int
    publishedAfter: String
}

type Query {
    searchBooks(filter: BookFilter, page: Int = 0, size: Int = 20): [Book!]!
}
```

Java DTO:

```java
public record BookFilterArguments(
        List<String> categoryIds,
        Integer minRating,
        String publishedAfter) {
}

public record SearchBooksArguments(
        BookFilterArguments filter,
        Integer page,
        Integer size) {
}
```

Controller:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookService.search(
        arguments.filter(),
        arguments.page(),
        arguments.size());
}
```

Client:

```graphql
query {
    searchBooks(
        filter: {
            categoryIds: ["backend", "java"]
            minRating: 4
        }
        page: 0
        size: 10
    ) {
        id
        title
    }
}
```

In this example, the `filter` object is bound into the `filter` property of `SearchBooksArguments`; its inner fields are further bound into `BookFilterArguments`. This organization keeps field-level arguments and input objects separate while producing a readable DTO.

If the schema only has a single `filter: BookFilter!` argument and you want to receive that input object directly, `@Argument("filter") BookFilterArguments filter` is usually clearer. When using `@Arguments`, the target DTO must describe all arguments of the field, meaning it has a `filter` property containing the input object.

## 5. How binding and data conversion work

Spring for GraphQL uses `GraphQlArgumentBinder` to bind argument values from `DataFetchingEnvironment` into the Java type of the controller parameter. The binder supports constructor binding and property binding, including nested objects, collections, arrays, and Maps.

High-level flow:

1. GraphQL parses the operation and validates arguments against the schema.
2. GraphQL applies variable coercion and default values according to the SDL.
3. Spring retrieves all arguments of the current field.
4. `GraphQlArgumentBinder` converts the values to the target Java types and binds them into a DTO/record or Map.
5. If binding succeeds, Spring invokes the controller method with the bound object.

Diagram:

```mermaid
flowchart TD
    A[GraphQL operation] --> B[Validate schema and coerce arguments]
    B --> C[DataFetchingEnvironment]
    C --> D[@Arguments resolver]
    D --> E[GraphQlArgumentBinder]
    E --> F[Constructor/property binding]
    F --> G[DTO, record or Map]
    G --> H[Annotated controller method]
    H --> I[Application service]
```

Binding does not replace business validation. For instance, `size` can bind to an `Integer`, but ensuring `size` falls between 1 and 100 is an application rule. Validate such limits before querying the database.

## 6. Argument names and Java property names

For a DTO or record, component/property names must match the argument names in GraphQL. GraphQL is case-sensitive, so `categoryId` and `categoryID` are two distinct names.

SDL example:

```graphql
type Query {
    booksByAuthor(authorId: ID!, includeDrafts: Boolean = false): [Book!]!
}
```

Corresponding DTO:

```java
public record BooksByAuthorArguments(
        String authorId,
        Boolean includeDrafts) {
}
```

```java
@QueryMapping
public List<Book> booksByAuthor(@Arguments BooksByAuthorArguments arguments) {
    return bookService.findByAuthor(
        arguments.authorId(),
        Boolean.TRUE.equals(arguments.includeDrafts()));
}
```

Do not use an arbitrary property name like `author` to receive the `authorId` argument without a corresponding mapping mechanism. If you need a Java name that differs from the GraphQL name, consider receiving a Map and converting explicitly, or designing the DTO/properties to align with the schema contract.

## 7. Distinguishing omitted arguments from null values

GraphQL distinguishes between an argument that is not passed and an argument explicitly passed as `null`. This matters for partial-update mutations. For example:

```graphql
type Mutation {
    updateBook(id: ID!, subtitle: String): Book!
}
```

The client may send:

```graphql
mutation {
    updateBook(id: "book-01") {
        id
        subtitle
    }
}
```

Here `subtitle` is omitted; the application can keep the existing subtitle. If the client sends `subtitle: null`, the application can interpret that as clearing the subtitle. A DTO using a regular `String subtitle` receives `null` in both cases, losing information about whether the argument was provided.

Spring for GraphQL provides `ArgumentValue<T>` to represent both the value and the omitted state:

```java
public record UpdateBookArguments(
        String id,
        ArgumentValue<String> subtitle) {
}

@MutationMapping
public Book updateBook(@Arguments UpdateBookArguments arguments) {
    if (arguments.subtitle().isOmitted()) {
        return bookService.updateWithoutChangingSubtitle(arguments.id());
    }

    return bookService.updateSubtitle(
        arguments.id(), arguments.subtitle().value());
}
```

When the argument is omitted, `ArgumentValue` indicates the omitted state. When the argument is passed with a string, `value()` holds that string; when passed as explicit `null`, the argument is considered provided with a value of `null`. Thus the service can distinguish preserving the value from clearing it.

If the schema declares a non-null argument (`String!`), the client cannot validly pass `null`. `ArgumentValue` remains useful for nullable arguments where business logic needs to distinguish omitted from explicit null.

## 8. Combining @Arguments with the source object and other parameters

`@Arguments` can be used alongside the source object in a nested field resolver. For example, a `Book.reviews` field accepts filtering criteria:

```graphql
type Book {
    reviews(minRating: Int, limit: Int = 10): [Review!]!
}
```

```java
public record ReviewArguments(Integer minRating, Integer limit) {
}

@Controller
public class BookFieldController {

    private final ReviewService reviewService;

    public BookFieldController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(
            Book book,
            @Arguments ReviewArguments arguments) {
        return reviewService.findByBook(
            book.id(), arguments.minRating(), arguments.limit());
    }
}
```

`Book book` is the source object for the `reviews` field; `ReviewArguments` receives all arguments of that field itself. The two parameters serve different roles and can coexist in the same mapping method.

The resolver can also accept other special parameters supported by Spring, such as `DataFetchingEnvironment`, `Principal`, `GraphQLContext`, or context values. Those parameters are not part of the data bound by `@Arguments`; they are resolved from the request execution context.

## 9. Validation for bound objects

A DTO that groups arguments is an appropriate place to apply validation. For example:

```java
public record SearchBooksArguments(
        @NotBlank String keyword,
        @Min(1) @Max(100) Integer size,
        @Min(0) Integer page) {
}
```

The controller can mark the parameter to validate:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments @Valid SearchBooksArguments arguments) {
    return bookService.search(arguments);
}
```

The application needs a Bean Validation implementation and appropriate Spring validation configuration. Annotations like `@NotBlank`, `@Min`, and `@Max` verify data constraints before the service executes. You should also check cross-field limits in the service or a custom validator—for example, ensuring `page * size` does not exceed the allowed query limit.

GraphQL schema validation and Bean Validation address two different layers:

- GraphQL validates types, required arguments, enums, scalar coercion, and default values according to the SDL.
- Bean Validation enforces application data constraints such as non-empty strings, numbers within a range, or valid field combinations.
- The service/domain layer must still protect business invariants and access permissions, even when the same logic is called from another entry point.

## 10. Handling binding errors

If argument names do not match, a Java type cannot accept a value, or a nested object structure fails to bind, the controller method may not be called. `GraphQlArgumentBinder` collects binding errors and reports them instead of silently creating a DTO with incorrect data.

For example, the SDL declares `size: Int`, but the client passes a value that cannot be coerced into an integer. The error may be detected immediately at the GraphQL input coercion step. If GraphQL accepts the value but the Java DTO cannot bind to the target type, the error occurs at the argument binding step.

Spring for GraphQL allows handling exceptions from data fetchers using `DataFetcherExceptionResolver` or `DataFetcherExceptionResolverAdapter`. You can map binding errors to safe messages and appropriate error codes in `extensions`, while logging technical details on the server. Do not return stack traces, internal class names, or sensitive input data to the client.

When debugging, check in order:

1. Does the argument name in the SDL match the property/record component name?
2. Is the argument nullable or non-null, and does it have a default value?
3. Does the value sent by the client match the GraphQL input type?
4. Can the target Java type accept the value after coercion?
5. For nested objects, can the properties and constructors be bound?
6. If binding succeeds, does the service reject the data according to business rules?

## 11. Testing @Arguments with GraphQlTester

`GraphQlTester` allows sending operations with multiple arguments and variables, then asserting the resolver's result.

Example:

```java
graphQlTester.document("""
        query SearchBooks(
            $keyword: String!
            $minRating: Int
            $size: Int
        ) {
            searchBooks(
                keyword: $keyword
                minRating: $minRating
                size: $size
            ) {
                id
                title
            }
        }
        """)
    .variable("keyword", "Spring")
    .variable("minRating", 4)
    .variable("size", 10)
    .execute()
    .path("searchBooks")
    .entityList(Book.class)
    .hasSize(3);
```

Your tests should cover:

- All arguments bound accurately into the record/DTO.
- Omitted arguments using default values from the SDL.
- Nullable arguments bound when the client sends `null`.
- Nested input objects and lists bound with the expected structure.
- Wrong argument names or invalid data types producing appropriate GraphQL errors.
- `ArgumentValue` distinguishing omitted from explicit null in update mutations.
- Bean Validation rejecting out-of-range values.
- `@SchemaMapping` resolvers receiving both the source object and `@Arguments` with correct data.

In addition to checking the response, you can mock the service and verify it receives the expected bound arguments object. For error cases, verify both `errors` and that the resolver/service is not invoked when the error occurs prior to invocation.

## 12. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| DTO receives all `null`s | Property name does not match argument name or constructor binding lacks metadata | Check names and parameter name configuration; consider using a record |
| Only some arguments received | DTO is missing properties or binding types are incompatible | Add missing components/properties and verify types |
| Confusing `@Arguments` with input object | `@Arguments` binds all field-level arguments | Use `@Argument("filter")` if you only want one input object |
| `Map` causes `ClassCastException` | Runtime value is not the expected cast type | Check types or use a strongly typed DTO |
| Optional number unexpectedly becomes `0` | Using a primitive for an argument that can be omitted/null | Use a wrapper like `Integer` or `ArgumentValue<Integer>` |
| Cannot distinguish omitted and null | DTO only uses regular nullable fields | Use `ArgumentValue<T>` |
| Binding fails before entering controller | SDL, coercion, or Java target is incompatible | Inspect schema, input, and binder errors |
| Using `@Arguments` to read variables | Confusing field arguments with operation variables | Bind the argument referenced by the variable; do not use `@Arguments` to read global variables |

## 13. Guidelines for using @Arguments

Use `@Arguments` when a field has multiple arguments that together form a set of criteria or a command. Prefer strongly typed records/DTOs to leverage constructor binding, validation, and safe refactoring. Choose a Map when you need to handle genuinely dynamic structures and are willing to perform manual type checks.

If there is only one argument, `@Argument` usually expresses intent more clearly. If a field has a single input object and you want to receive that object directly, bind it with `@Argument("input")`. Use `@Arguments` when you need to receive all field-level arguments, including both individual arguments and nested input objects.

Pay attention to default values, nullability, and the difference between omitted and explicit null. Place data constraints as validation on the DTO, while invariants and authorization remain in the service/domain layer. In Spring for GraphQL, `@Arguments` lets controllers receive a structured set of parameters, avoiding long method signatures and keeping query/mutation handling logic clear.
