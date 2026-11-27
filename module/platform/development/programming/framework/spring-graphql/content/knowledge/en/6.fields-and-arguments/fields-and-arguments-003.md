# Default Arguments

A GraphQL field often takes arguments for filtering, pagination, or controlling how data is fetched. Clients can pass all arguments in every request, but many APIs have sensible default behavior: returning 20 items in a list, sorting by most recent, or returning only published books.

GraphQL SDL allows declaring a **default value** directly on an argument. When a client omits the argument, GraphQL applies the default value before calling the resolver. A similar mechanism also exists for operation variables and fields inside input objects. Understanding the difference between omitting a value and passing `null` is important when building an API with Spring for GraphQL, especially with filters and partial update mutations.

This lesson explains how to declare default values, the order of precedence between variable defaults and argument defaults, behavior with `null`, how Spring binds values into `@Argument`, and how to test those scenarios.

## 1. Declaring default values for field arguments

A default value is declared after the argument type using `=`. Example:

```graphql
type Query {
  books(
    first: Int = 20
    offset: Int = 0
  ): [Book!]!
}
```

The client can call the field without passing arguments:

```graphql
query {
  books {
    id
    title
  }
}
```

GraphQL applies `first = 20` and `offset = 0` when preparing arguments for the resolver. The client can also override the default values:

```graphql
query {
  books(first: 5, offset: 10) {
    id
    title
  }
}
```

In the second request, the resolver receives `first = 5` and `offset = 10`. A default value is only used when the argument is omitted; it does not force every request to use the default value.

A more complete schema can declare defaults for several scalars and enums:

```graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Query {
  books(
    first: Int = 20
    offset: Int = 0
    status: BookStatus = PUBLISHED
    includeSummary: Boolean = false
  ): [Book!]!
}
```

The default values above are part of the schema. Clients can inspect them via introspection, and GraphQL developer tools can display them in API documentation.

## 2. Valid forms of default values

A default value in SDL is a GraphQL constant value. You can use literal forms matching the declared type:

| Data type | Example default value |
| --- | --- |
| `Int` | `first: Int = 20` |
| `Float` | `minimumScore: Float = 4.5` |
| `String` | `keyword: String = "GraphQL"` |
| `Boolean` | `includeArchived: Boolean = false` |
| `ID` | `ownerId: ID = "user-100"` |
| Enum | `status: BookStatus = PUBLISHED` |
| List | `statuses: [BookStatus!] = [PUBLISHED, ARCHIVED]` |
| Input object | `filter: BookFilter = { status: PUBLISHED }` |

Combined example:

```graphql
input BookFilter {
  keyword: String
  status: BookStatus
  includeArchived: Boolean
}

type Query {
  searchBooks(
    filter: BookFilter = {
      status: PUBLISHED
      includeArchived: false
    }
    first: Int = 20
  ): [Book!]!
}
```

The default value must be compatible with the type of the argument or input field. If you declare `first: Int = "twenty"`, the schema is invalid because a string cannot be used as a default value for `Int`.

A default value in SDL is not a Java expression. You cannot call methods, read environment variables, reference other fields, or compute values based on time. The following example is invalid:

```graphql
type Query {
  # Invalid: GraphQL SDL does not execute expressions.
  books(first: Int = calculateDefaultPageSize()): [Book!]!
}
```

If a default value depends on the tenant, current user, deployment configuration, or request time, handle it in the application layer rather than trying to put dynamic logic into SDL.

## 3. Distinguishing omitted arguments from arguments receiving null

This is the most important rule when working with default values:

- If the client **does not send the argument**, GraphQL uses the default value if one exists.
- If the client **sends the argument with a value of `null`**, the `null` value is preserved for nullable arguments; the default value is not applied.
- If the argument has a non-null type, the client cannot validly pass `null`.

Example:

```graphql
type Query {
  books(first: Int = 20): [Book!]!
}
```

| Request | Value received by resolver |
| --- | --- |
| `{ books { id } }` | `first = 20` |
| `{ books(first: 5) { id } }` | `first = 5` |
| `{ books(first: null) { id } }` | `first = null` |

If the resolver or service requires an integer for pagination, it must clearly decide how to handle `null`. Do not assume that `Int = 20` means every case will receive 20.

### Non-null arguments with default values

GraphQL allows declaring a non-null argument with a default value:

```graphql
type Query {
  books(first: Int! = 20): [Book!]!
}
```

The client can omit `first` because the schema supplies a default value. However, if the client passes `null`, the request is invalid because `Int!` does not accept null. Thus, the resolver receives a non-null value whenever the field executes validly.

This distinction is useful when the API always needs a value, yet wants to allow clients to omit the argument in the common case. A non-null argument without a default value is a required argument:

```graphql
type Query {
  book(id: ID!): Book
}
```

## 4. Variable default values in operations

A GraphQL operation can also declare a default value for a variable. The syntax places the default after the variable type:

```graphql
query BookList($first: Int = 10) {
  books(first: $first) {
    id
    title
  }
}
```

If the client does not send the `first` variable, GraphQL uses the value `10` declared in the operation. The client can still pass a different value in the variables payload:

```json
{
  "first": 5
}
```

In that case, the query fetches 5 books. A variable default belongs to the client's operation, whereas an argument default belongs to the server's schema. These two places serve two different purposes:

| Default kind | Where declared? | Who controls it? | Purpose |
| --- | --- | --- | --- |
| Argument default | Server SDL | API/schema owner | Default field behavior for all clients |
| Variable default | GraphQL operation | Client/query author | Default value specific to that operation |

### Order of precedence when both defaults exist

Suppose the schema declares:

```graphql
type Query {
  books(first: Int = 20): [Book!]!
}
```

The operation declares a variable default:

```graphql
query BookList($first: Int = 5) {
  books(first: $first) {
    id
    title
  }
}
```

If the client omits the `first` variable, the operation uses `5`. That value is passed into the `books(first:)` argument, so the default `20` in the schema is no longer used.

If the operation does not declare a variable default:

```graphql
query BookList($first: Int) {
  books(first: $first) {
    id
    title
  }
}
```

When the client omits the `first` variable, the argument is treated as not provided and the schema default of `20` is applied. If the client sends `{"first": null}`, null is passed to the nullable argument and overrides both defaults.

You can remember the order as follows:

1. If the client supplies the variable, use that value, including `null` if the type allows it.
2. If the variable is omitted but the operation has a variable default, use the variable default.
3. If the argument is still not provided, use the argument default in the schema if one exists.
4. If no default exists, a nullable argument receives `null`; a non-null argument without a default makes the request invalid.

## 5. Default values for fields in input objects

Input fields can also have default values. This is often useful for filters or input objects with many optional properties:

```graphql
input BookFilter {
  keyword: String
  status: BookStatus = PUBLISHED
  includeArchived: Boolean = false
}

type Query {
  searchBooks(filter: BookFilter = {}): [Book!]!
}
```

With the schema above, different requests behave differently:

```graphql
# filter omitted: the argument default {} is used.
query {
  searchBooks {
    id
  }
}

# filter passed an empty object: each input field's default is applied.
query {
  searchBooks(filter: {}) {
    id
  }
}

# status passed explicitly: this value overrides the input field default.
query {
  searchBooks(filter: { status: ARCHIVED }) {
    id
  }
}

# status passed null: the PUBLISHED default is not applied.
query {
  searchBooks(filter: { status: null }) {
    id
  }
}
```

In this example, omitting `filter` results in the default object `{}`. Input coercion then applies the default `PUBLISHED` to `status` and `false` to `includeArchived`. If `filter` is passed as `null`, the entire input object is null; defaults inside the object are not applied.

Argument-level defaults and input-field-level defaults can be used together, but must be clearly documented so clients understand the behavior. Avoid large default objects if they make it hard for clients to tell which filter conditions the server is applying.

## 6. Default values and partial updates

Partial update mutations often need to distinguish three states of an input field:

1. Client omits the field: keep the existing value.
2. Client sends the field with `null`: clear the value if business rules allow.
3. Client sends a specific value: update with that value.

If you put a default value on an input field in a partial-update mutation, the omitted case may be replaced with the default before the resolver receives the input. The server then loses the information that the client did not send the field.

Example unsuitable for partial updates:

```graphql
input UpdateBookInput {
  title: String = "Untitled"
  summary: String
}
```

If the client sends `{ summary: "New description" }`, input coercion may fill in `title = "Untitled"`. The resolver has difficulty telling whether the client wanted to change the title to the default value or only wanted to update the summary. For inputs used in partial updates, generally avoid defaults on fields that should remain unchanged when omitted.

### Distinguishing omitted and null in Spring for GraphQL

Spring for GraphQL provides `ArgumentValue<T>` to distinguish omitted values from explicit null values during argument binding:

```java
import org.springframework.graphql.data.ArgumentValue;

@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("summary") ArgumentValue<String> summary) {

    if (summary.isOmitted()) {
        return bookService.updateWithoutChangingSummary(id);
    }

    if (summary.value() == null) {
        return bookService.clearSummary(id);
    }

    return bookService.updateSummary(id, summary.value());
}
```

`ArgumentValue` is useful when an API has partial-update semantics. For an argument with a default value, GraphQL has already applied the default before the resolver receives the value; therefore, do not set a default if the goal is to preserve the omitted state to distinguish it in a mutation.

## 7. Spring for GraphQL receives default values via @Argument

In Spring for GraphQL, GraphQL Java performs coercion and applies defaults according to the schema/operation before Spring binds arguments to the handler method. Therefore, the controller typically receives the value with defaults already applied.

Schema:

```graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Query {
  books(
    first: Int = 20
    offset: Int = 0
    status: BookStatus = PUBLISHED
  ): [Book!]!
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
    public List<Book> books(
            @Argument("first") Integer first,
            @Argument("offset") Integer offset,
            @Argument("status") BookStatus status) {

        return bookService.findBooks(first, offset, status);
    }
}
```

For the query `{ books { id title } }`, the method receives `20`, `0`, and `BookStatus.PUBLISHED`. If the client sends `first: null`, the `Integer first` parameter can receive null because the argument is declared nullable. Use the wrapper `Integer` instead of the primitive `int` when the schema allows null.

### Defaults in SDL vs. defaults in Java

Do not confuse a schema default value with a fallback in a Java method:

```java
@QueryMapping
public List<Book> books(@Argument("first") Integer first) {
    int effectiveFirst = first == null ? 20 : first;
    return bookService.findBooks(effectiveFirst);
}
```

The Java snippet above sets a fallback when the resolver receives null. It does not make the schema advertise `20` as a default in introspection and does not change GraphQL validation. If you want the default to be part of the public contract, declare it in SDL:

```graphql
type Query {
  books(first: Int = 20): [Book!]!
}
```

A Java fallback may still be needed for internal logic, but avoid letting the schema default and the code default contradict each other. When those two places have different values, clients see one contract while the server may process requests under another rule.

### Kotlin and default parameter values

Kotlin allows declaring default parameters on methods:

```kotlin
@QueryMapping
fun books(@Argument first: Int = 20): List<Book> =
    bookService.findBooks(first)
```

Kotlin default parameters are a server-side language feature. They do not automatically become default values in the GraphQL schema and do not appear in introspection. If you want clients to see the default in API documentation, still declare `first: Int = 20` in SDL. Also check how Spring binds arguments to Kotlin methods for your specific Spring GraphQL and Kotlin versions.

## 8. Testing default values

When testing, cover omitted, explicit value, and null cases. `GraphQlTester` can send documents and variables just like a real client.

Example testing argument defaults:

```java
@GraphQlTest(BookQueryController.class)
class BookQueryControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    BookService bookService;

    @Test
    void appliesSchemaDefaultsWhenArgumentsAreOmitted() {
        given(bookService.findBooks(20, 0, BookStatus.PUBLISHED))
                .willReturn(List.of());

        graphQlTester.document("""
                query {
                    books {
                        id
                        title
                    }
                }
                """)
                .execute()
                .path("books")
                .entityList(Book.class)
                .hasSize(0);

        then(bookService).should()
                .findBooks(20, 0, BookStatus.PUBLISHED);
    }
}
```

This abbreviated example assumes the project's service and `Book` type have matching signatures. You can add tests for:

- Sending `first: 5` to confirm the client value overrides the default.
- Sending `first: null` to confirm a nullable argument receives null.
- Omitting a variable that has a default in the operation to confirm the variable default is used.
- Omitting a variable without a default to confirm the schema argument default is used.
- Sending an empty input object to confirm input field defaults.
- Sending a null input field to confirm explicit null is not replaced by the default.
- Omitting an input field in a partial-update mutation to confirm the omitted state is preserved when there is no default.

If you want to verify the default values published in the schema, use introspection:

```graphql
query BooksArgumentDefaults {
  __type(name: "Query") {
    fields {
      name
      args {
        name
        defaultValue
      }
    }
  }
}
```

`defaultValue` in introspection is represented as a GraphQL literal in string form, for example `20`, `PUBLISHED`, or `{status: PUBLISHED}`. It is not the JSON value received by the resolver.

## 9. Common mistakes when using default values

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Resolver receives null despite a declared default | Client passed `null` explicitly | Inspect the request and distinguish omitted from null |
| Schema default is not used | A variable default in the operation already supplied a value | Check the variable declaration and variables payload |
| Schema fails to start | Default literal is incompatible with the argument/input field type | Check the type and GraphQL constant value syntax |
| Resolver receives an unexpected value | Defaults exist at multiple layers: variable, argument, input field, and Java | Determine which layer supplied the value before the resolver ran |
| Partial update mutation accidentally overwrites a field | Input field has a default causing omitted to become the default value | Remove the default on fields that must keep omitted/null/value semantics |
| Introspection does not show the default | Default not declared in SDL or checking the wrong argument | Query `__type`, `fields`, `args`, and `defaultValue` |
| Using `int` causes an error on a nullable argument | Java primitives cannot represent null | Use `Integer` or an appropriate nullable type |

## 10. Principles for designing default values

- Put defaults in SDL when they represent public, stable behavior with the same meaning for all clients.
- Use variable defaults when the default value belongs only to a specific client operation.
- Use defaults for pagination, sorting, or filtering when there is a reasonable and predictable default choice.
- Only place a default on a non-null argument when the server can always supply that value if the client omits the argument.
- Understand clearly that `null` differs from omitted. For nullable arguments, explicit `null` overrides the default.
- Avoid defaults on input fields of partial-update mutations if you need to distinguish a client omitting the field from a client wanting to update it to a specific value.
- Do not put dynamic logic such as current tenant, current user, current date, or environment configuration in SDL defaults.
- Do not maintain two conflicting default values between SDL, Java/Kotlin, and the service layer.
- Write descriptions for defaults with business significance so clients understand when the value is applied.
- Test omitted, explicit value, explicit null, and variable default separately.

## 11. Practice exercise

Given the book management schema:

```graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input BookFilter {
  keyword: String
  status: BookStatus = PUBLISHED
  includeArchived: Boolean = false
}

type Query {
  books(
    filter: BookFilter = {}
    first: Int = 20
    offset: Int = 0
  ): [Book!]!
}
```

Answer and verify:

1. What values does the resolver receive when the client calls `{ books { id } }`?
2. If the client calls `books(filter: {})`, how are input field defaults applied?
3. If the client calls `books(filter: { status: null })`, what `status` value does the resolver receive?
4. If the operation declares `$first: Int = 5` and the schema declares `first: Int = 20`, which value is used when the client does not send the variable?
5. If the client sends `first: null`, what happens?
6. Why should you avoid setting a default `title: String = "Untitled"` in the input of a partial-update mutation?

Then write `GraphQlTester` tests verifying the omitted, explicit value, and explicit null cases. Finally, use introspection to verify the default values that the schema exposes to clients.

Upon completion, you should be able to distinguish the three places where a default can be set: operation variables, field arguments, and input object fields. GraphQL applies defaults according to coercion rules before the Spring for GraphQL resolver receives the data; understanding omitted vs. null will keep your API behavior predictable, especially when handling filters and partial-update mutations.
