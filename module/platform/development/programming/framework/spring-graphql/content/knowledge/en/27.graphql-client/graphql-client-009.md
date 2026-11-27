# Client variables

In GraphQL, a **variable** allows the client to pass data into an operation without concatenating values directly into the query string. The client declares the variable's name and type in the operation header, then uses that variable in a field argument or input object. The actual values are sent separately in the request payload.

Spring for GraphQL provides the **GraphQlClient** abstraction to send queries, mutations, and subscriptions over different transports. The client's request API allows passing individual variables with `variable(name, value)` or passing an entire map with `variables(map)`. This lesson focuses on how to declare, pass, and manage variables, represent complex inputs, handle default/null/omitted values, and verify responses.

## 1. Why are GraphQL variables needed?

Suppose the client needs to look up a book by ID. You could write the value directly inside the document:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

This ties the query to a specific value. Whenever the ID changes, the client must generate a different document. If built by concatenating user data, the code is also prone to escaping bugs and risks injecting untrusted data into the GraphQL structure.

Using a variable separates the document from the data:

~~~graphql
query BookById($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Values are sent separately:

~~~json
{
    "query": "query BookById($id: ID!) { book(id: $id) { id title } }",
    "operationName": "BookById",
    "variables": {
        "id": "book-42"
    }
}
~~~

The same document can run with many different IDs. Key benefits:

- The document remains stable and readable.
- Input data is serialized separately as JSON.
- Avoids concatenating user values into GraphQL syntax.
- Easy to test with multiple datasets.
- Operations can be reused and support document-based caching at appropriate layers.

Variables do not replace authentication, authorization, or validation. The server must still check whether the user is allowed to access the resource passed in.

## 2. Declaring variables in a GraphQL operation

Variable declarations are placed inside parentheses after the operation type and operation name:

~~~graphql
query OperationName($variableName: GraphQLType) {
    field(argument: $variableName) {
        id
    }
}
~~~

Example:

~~~graphql
query SearchBooks($keyword: String!, $limit: Int) {
    searchBooks(keyword: $keyword, limit: $limit) {
        id
        title
    }
}
~~~

Where:

- `$keyword` is the variable name.
- `String!` is the GraphQL type, and `!` means non-null.
- `$limit` is a nullable variable of type `Int`.
- `keyword: $keyword` passes the variable to the field's argument of the same name.

Variable names start with the `$` character, followed by a valid GraphQL Name. A variable is only in scope within the operation where it is declared.

A document can contain multiple operations:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}

query FindAuthor($id: ID!) {
    author(id: $id) {
        id
        name
    }
}
~~~

When a document contains multiple operations, the client must specify the operation name so the server knows which operation to execute. Declaring a variable in one operation does not make it usable in another operation.

## 3. Variable types and nullability

A variable must be compatible with the argument type declared in the schema.

Common GraphQL scalars:

| Type | Typical JSON representation | Notes |
| --- | --- | --- |
| `String` | JSON string | Used for text |
| `Int` | Integer | GraphQL Int is a signed 32-bit integer |
| `Float` | JSON number | Used for floating-point numbers |
| `Boolean` | `true` or `false` | Do not send the string `"true"` |
| `ID` | Typically sent as a string | Used for identifiers; avoid relying on numeric representation |

Required variable example:

~~~graphql
query BookById($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

`ID!` requires the variable to be provided and non-null, unless a valid default value is present in the declaration. If the client omits the variable or sends null, GraphQL rejects the request during input coercion; the resolver is not invoked.

Nullable variable:

~~~graphql
query Books($category: String) {
    books(category: $category) {
        id
        title
    }
}
~~~

If `category` is not provided and has no default, it is treated as having no value. If the client sends an explicit null, the variable has a null value. This distinction can affect whether an argument is considered provided and the semantics of input objects.

Lists and non-null can be combined:

~~~graphql
query BooksByIds($ids: [ID!]!) {
    booksByIds(ids: $ids) {
        id
        title
    }
}
~~~

`[ID!]!` means the list must have a non-null value, and each element inside the list must also be non-null. The list may be empty unless prohibited by the schema or business rules.

## 4. Passing variables with GraphQlClient

`GraphQlClient` is Spring for GraphQL's unified API for sending GraphQL requests. Transport implementations such as `HttpGraphQlClient`, `WebSocketGraphQlClient`, and `RSocketGraphQlClient` handle their respective connections, while the variable-passing API is used consistently.

Example creating an HTTP client from `WebClient`:

~~~java
import org.springframework.graphql.client.GraphQlClient;
import org.springframework.graphql.client.HttpGraphQlClient;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
        .baseUrl("http://localhost:8080/graphql")
        .build();

GraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

Sending a query and passing a variable:

~~~java
Mono<Book> bookMono = graphQlClient
        .document("""
                query BookById($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """)
        .operationName("BookById")
        .variable("id", "book-42")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Key steps:

1. `document(...)` supplies the GraphQL document.
2. `operationName(...)` sets the name of the operation to execute.
3. `variable("id", value)` binds a value to the `$id` variable.
4. `retrieve("book")` selects the field to read in the response.
5. `toEntity(Book.class)` converts the field data into a Java object.

The example above returns `Mono<Book>` because GraphQlClient is a reactive API. The application can compose further with Reactor or subscribe at the appropriate layer. Avoid calling `block()` on a WebFlux event-loop.

## 5. Passing multiple variables

You can declare multiple variables in an operation and call `variable(...)` multiple times:

~~~graphql
query SearchBooks(
    $keyword: String!
    $page: Int!
    $size: Int!
) {
    searchBooks(keyword: $keyword, page: $page, size: $size) {
        content {
            id
            title
        }
        totalElements
    }
}
~~~

Java:

~~~java
Mono<BookPage> result = graphQlClient
        .document("""
                query SearchBooks(
                    $keyword: String!
                    $page: Int!
                    $size: Int!
                ) {
                    searchBooks(keyword: $keyword, page: $page, size: $size) {
                        content {
                            id
                            title
                        }
                        totalElements
                    }
                }
                """)
        .operationName("SearchBooks")
        .variable("keyword", keyword)
        .variable("page", page)
        .variable("size", size)
        .retrieve("searchBooks")
        .toEntity(BookPage.class);
~~~

When there are many variables, you can pass a map:

~~~java
Map<String, Object> variables = Map.of(
        "keyword", keyword,
        "page", 0,
        "size", 20
);

Mono<BookPage> result = graphQlClient
        .document(searchBooksDocument)
        .operationName("SearchBooks")
        .variables(variables)
        .retrieve("searchBooks")
        .toEntity(BookPage.class);
~~~

Key names in the map must match the variable names declared in the operation, without the leading `$` character. For example, the key is `id`, not `$id`.

Use `variable(...)` when only a few values need to be bound individually. Use `variables(...)` when data is already organized as a map, such as from a DTO or mapping layer. Avoid passing both a map and overlapping variable keys in multiple ways in the same request, as that makes the code harder to follow.

## 6. Passing input objects

Mutations often accept an input object instead of multiple scalar arguments.

SDL:

~~~graphql
input CreateBookInput {
    title: String!
    isbn: String!
    pageCount: Int
    description: String
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

Operation:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        isbn
    }
}
~~~

Client passing the object in a variable:

~~~java
Map<String, Object> input = Map.of(
        "title", "Spring for GraphQL",
        "isbn", "9780132350884",
        "pageCount", 420,
        "description", "Practical GraphQL API"
);

Mono<Book> created = graphQlClient
        .document(createBookDocument)
        .operationName("CreateBook")
        .variable("input", input)
        .retrieve("createBook")
        .toEntity(Book.class);
~~~

The structure of the object sent in the variable must match the schema's input type. Fields that do not exist in the input type will cause coercion errors; required fields that are missing or null are also rejected before the resolver runs.

When input is multi-level, maps can be nested:

~~~java
Map<String, Object> input = Map.of(
        "title", "Spring for GraphQL",
        "author", Map.of(
                "name", "Lan Nguyen",
                "email", "lan@example.test"
        )
);
~~~

Another approach is using a Java record/class as a DTO, as long as the client's JSON codec serializes the object into a JSON structure matching the GraphQL input type.

## 7. Using DTOs to represent variables

For inputs with a stable structure, DTOs provide stronger type safety than maps:

~~~java
public record AuthorInput(
        String name,
        String email
) {
}

public record CreateBookInput(
        String title,
        String isbn,
        Integer pageCount,
        AuthorInput author
) {
}
~~~

Passing a DTO:

~~~java
CreateBookInput input = new CreateBookInput(
        "Spring for GraphQL",
        "9780132350884",
        420,
        new AuthorInput("Lan Nguyen", "lan@example.test")
);

Mono<Book> created = graphQlClient
        .document(createBookDocument)
        .variable("input", input)
        .retrieve("createBook")
        .toEntity(Book.class);
~~~

The DTO must have property names and types compatible with the input type in the schema. The JSON codec is responsible for serializing the DTO. With `HttpGraphQlClient`, codecs come from `WebClient`; Jackson or other codecs can be configured via `WebClient.Builder`.

DTOs do not automatically guarantee schema-level validity. The client can validate data at the UI/domain layer for better UX, but the server remains the authoritative place for validation.


## 8. List, enum, and custom scalar variables

A variable can hold a list value:

~~~graphql
query BooksByIds($ids: [ID!]!) {
    booksByIds(ids: $ids) {
        id
        title
    }
}
~~~

Java:

~~~java
List<String> ids = List.of("book-1", "book-2", "book-3");

Mono<List<Book>> books = graphQlClient
        .document(booksByIdsDocument)
        .variable("ids", ids)
        .retrieve("booksByIds")
        .toEntityList(Book.class);
~~~

For enums, the JSON payload sends the enum name as a string:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

query BooksByStatus($status: BookStatus!) {
    booksByStatus(status: $status) {
        id
        title
    }
}
~~~

~~~java
.variable("status", "PUBLISHED")
~~~

If Java has a matching enum, the JSON codec typically serializes the enum by name. Ensure symbol names match the GraphQL enum values; a Java enum name is not automatically translated into a different symbol without a custom serializer.

Custom scalars like `Date`, `DateTime`, `UUID`, or `Money` have formats defined by the schema and scalar implementation. For example, if the server defines `Date` accepting ISO-8601 strings, the client can pass:

~~~java
.variable("publishedAfter", "2026-01-01")
~~~

Do not assume the GraphQL server and client serialize Java objects the exact same way. The client only sends JSON; the custom scalar on the server decides which JSON values are accepted. If you want to pass `LocalDate` directly, configure the JSON codec to serialize in the exact format expected by the server scalar.

## 9. Default values, omitted, and explicit null

GraphQL supports default values directly in variable declarations:

~~~graphql
query SearchBooks(
    $keyword: String!
    $page: Int = 0
    $size: Int = 20
) {
    searchBooks(keyword: $keyword, page: $page, size: $size) {
        id
        title
    }
}
~~~

If the client does not send `page` or `size`, GraphQL uses their corresponding defaults. If the client sends a specific value, that value is used instead of the default.

For nullable variables without defaults, distinguish three cases:

| Client sends | Meaning |
| --- | --- |
| Key absent in `variables` | Variable is not provided; if a default exists, the default is used |
| Key present with value `null` | Variable is provided with a null value |
| Key present with non-null value | Variable receives the sent value |

Explicit null does not trigger default values. For example, with `$page: Int = 0`, if the client sends `"page": null`, the value remains null rather than falling back to 0.

To omit a variable, do not add that key to the map. To send an explicit null, the map must contain the key with a null value. Java's `Map.of(...)` does not allow null, so use `HashMap` or `LinkedHashMap`:

~~~java
import java.util.LinkedHashMap;

Map<String, Object> variables = new LinkedHashMap<>();
variables.put("keyword", "spring");
variables.put("page", null);

graphQlClient.document(searchBooksDocument)
        .variables(variables)
        .retrieve("searchBooks")
        .toEntity(BookPage.class);
~~~

In this example, `page` is sent as an explicit null. If you want to use the default page 0, omit the `page` key altogether.

For input objects, omitted fields and explicit nulls can also carry different semantics. This is particularly important for partial update mutations: omitted usually means keep the old value, whereas explicit null can mean clear the value. The server must use a binding type capable of preserving that distinction if business logic requires it.

## 10. Operation name and stable documents

The operation name helps the server, logs, and tracing identify the running operation. When a document has only one operation, the name may be omitted; when a document contains multiple operations, the client must specify the appropriate operation name.

~~~java
graphQlClient.document(searchBooksDocument)
        .operationName("SearchBooks")
        .variable("keyword", "spring")
        .variable("page", 0)
        .variable("size", 20)
        .retrieve("searchBooks")
        .toEntity(BookPage.class);
~~~

Keep GraphQL documents stable and only vary variables across requests. Store documents in `.graphql` files or constants for easier management, review, and testing. Do not construct documents by concatenating user input values into the query string.

The operation name is the name of the operation inside the GraphQL document. It is neither the resolver field name nor a variable name. Keep these names consistent so logs and telemetry are easy to read.

## 11. Variables and JSON codecs

`GraphQlClient` passes variables as a key/value map; the transport client is responsible for encoding them into the request payload.

With `HttpGraphQlClient`, HTTP encoding/decoding is performed via `WebClient` and its configured codecs. If the client uses DTOs, verify that Jackson or the corresponding codec serializes records, enums, dates/times, and nested objects accurately.

Example customizing `WebClient` before creating the GraphQL client:

~~~java
ObjectMapper objectMapper = new ObjectMapper()
        .findAndRegisterModules();

WebClient webClient = WebClient.builder()
        .baseUrl("http://localhost:8080/graphql")
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .jackson2JsonEncoder(
                                new Jackson2JsonEncoder(objectMapper)
                        )
                        .jackson2JsonDecoder(
                                new Jackson2JsonDecoder(objectMapper)
                        )
        )
        .build();

GraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

Exact codec configuration can differ depending on the Spring Framework version and how the application already configured `WebClient`. If using a Spring Boot-provided `WebClient.Builder`, consider reusing the application's shared codec configuration rather than creating an inconsistent ObjectMapper.

You do not need to manually convert variables into a JSON string. Pass a `Map`, list, or DTO to `GraphQlClient`; the codec encodes the payload. Only when a scalar has a special format should you configure a serializer or convert the value into the JSON representation matching the scalar contract.

## 12. Reusing clients and transport-specific configuration

`GraphQlClient` is a shared abstraction across multiple transports. HTTP, WebSocket, and RSocket clients differ in connectivity and connection lifecycle, but declaring documents and passing variables follows the same request model.

HTTP client example:

~~~java
GraphQlClient httpClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

Example WebSocket client created from a WebSocket URI and a matching WebSocket client implementation:

~~~java
import java.net.URI;

import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

URI uri = URI.create("ws://localhost:8080/graphql");

// webSocketClient is a configured WebSocketClient instance.
WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(uri, webSocketClient).build();
~~~

An RSocket client can be created from a configured `RSocketRequester`:

~~~java
import org.springframework.graphql.client.RSocketGraphQlClient;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketGraphQlClient rsocketClient =
        RSocketGraphQlClient.builder(rSocketRequester).build();
~~~

Exact builder names and transport types depend on the Spring implementation in use, but the request portion can be written similarly:

~~~java
Mono<Book> book = graphQlClient
        .document(bookByIdDocument)
        .variable("id", bookId)
        .retrieve("book")
        .toEntity(Book.class);
~~~

Do not create a new client for each operation. Usually configure and reuse a client bean to share connection pools, codecs, authentication, and interceptors consistently. With WebSocket, manage the connection lifecycle; do not open a new connection for every call if the application can reuse the existing session.

## 13. Reading results and handling GraphQL errors

There are two ways to read responses:

- `retrieve(path)` is a concise way when only a single specific field is needed.
- `execute()` returns `ClientGraphQlResponse` to inspect the entire response, including `data`, `errors`, and `extensions`.

Example retrieving a single field:

~~~java
Mono<Book> book = graphQlClient
        .document(bookByIdDocument)
        .variable("id", bookId)
        .retrieve("book")
        .toEntity(Book.class);
~~~

If the selected field has an error or cannot be accessed, the retrieve API may throw `FieldAccessException`. This can be handled at the service/client adapter layer to translate it into an appropriate application error type.

When explicit error checking is needed:

~~~java
Mono<ClientGraphQlResponse> responseMono = graphQlClient
        .document(bookByIdDocument)
        .variable("id", bookId)
        .execute();

Mono<Book> result = responseMono.map(response -> {
    if (!response.isValid()) {
        throw new IllegalStateException(
                "GraphQL request returned errors: " + response.getErrors()
        );
    }

    return response.field("book").toEntity(Book.class);
});
~~~

The example above illustrates checking the response; production applications should use custom exceptions and avoid logging full variable values if they contain sensitive data. A GraphQL response can contain both `data` and `errors`, so not every error means the entire operation has no data.

When using `retrieve(path)`, the client focuses on the field to extract. When decisions depend on multiple fields, partial data, or extension metadata, use `execute()` and inspect the full response.

## 14. Do not concatenate user input into GraphQL documents

Do not construct queries by string concatenation:

~~~java
// Not recommended: userInput is concatenated directly into GraphQL syntax.
String document = "query { book(id: \"" + userInput + "\") { id title } }";
~~~

This approach easily breaks when values contain quotes, backslashes, or special characters. Worse, if input alters the document structure, the client could unintentionally send a different operation than intended.

Use variables:

~~~java
graphQlClient.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", userInput)
        .retrieve("book")
        .toEntity(Book.class);
~~~

The GraphQL document keeps its structure fixed, while the value is serialized as data. This is the proper GraphQL way to pass inputs and reduces injection risks from dynamic query construction.

If fields or operations must be chosen dynamically, you cannot swap field names via variables because GraphQL variables only pass values, not syntax or identifiers. Use an allowlist to choose among pre-defined documents/operations.


## 15. Testing variables with GraphQlTester

`GraphQlTester` tests the GraphQL server and allows sending variables in a way close to real requests. This verifies whether the schema accepts the variable types, coercion works, and resolvers receive the expected values.

Query test example:

~~~java
@Test
void findsBookByVariableId() {
    graphQlTester.document("""
            query BookById($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
            .operationName("BookById")
            .variable("id", "book-42")
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-42");
}
~~~

Nested input objects can be tested:

~~~java
@Test
void createsBookWithInputVariable() {
    Map<String, Object> input = Map.of(
            "title", "Spring for GraphQL",
            "isbn", "9780132350884",
            "pageCount", 420
    );

    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    title
                    isbn
                }
            }
            """)
            .variable("input", input)
            .execute()
            .path("createBook.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");
}
~~~

Cases that should be covered in tests:

- Missing non-null variable.
- Non-null variable receiving explicit null.
- Variable with wrong type, e.g. passing a string for `Int`.
- List variable containing a null element when declared as `[ID!]!`.
- Input object missing a non-null field.
- Omitted variable to test default values.
- Explicit null not being mistaken for default.
- Multiple operations in one document with an explicit operation name.
- Resolver not invoked when input coercion fails.

`GraphQlTester` verifies the server contract. If you need to verify that the HTTP client itself serializes variables accurately, write integration tests with a mock HTTP server or test server and assert on the JSON request body. Do not rely solely on unit testing mapping methods while skipping JSON codec tests when the client uses DTOs or custom scalars.

## 16. Mapping variable names to Java properties

Variable names in the operation and keys in the map must match exactly, while Java property names inside a DTO must serialize to the GraphQL input type's field names.

Schema example:

~~~graphql
input CreateBookInput {
    pageCount: Int
}

type Mutation {
    createBook(input: CreateBookInput!): Book
}
~~~

Java DTO:

~~~java
public record CreateBookInput(
        Integer pageCount
) {
}
~~~

If the DTO uses a different property name, such as `pages`, configure appropriate JSON naming or mapping to send the right `pageCount` key. Do not expect the GraphQL server to guess Java property names.

The same applies to enums, custom scalars, and dates/times: the serialized JSON representation must match the schema contract. Verify the actual payload in integration tests when using naming strategies, Jackson annotations, or custom serializers.

## 17. Common issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `Variable "$id" was not provided` | Missing `id` key in variables map | Pass the required variable or declare a suitable default |
| `Variable "$id" of non-null type ... must not be null` | Client sent explicit null for non-null variable | Validate data before sending or change schema if null is allowed |
| `Variable "$page" got invalid value` | JSON value incompatible with scalar/list/enum | Check Java types and JSON payload |
| Input field does not receive value | Key in map/DTO differs from SDL field name | Align JSON property name with input type |
| Nested input is null | DTO does not serialize expected structure or missing nested property | Check DTO and JSON codec |
| Default value not used | Client sent explicit null key instead of omitting key | Omit key from variables map if default should apply |
| `Map.of` throws NullPointerException | Java immutable map factory does not allow null | Use `HashMap` or `LinkedHashMap` |
| Query document breaks when value has quotes | Direct concatenation of user input into GraphQL string | Use variables and let the codec serialize |
| `retrieve(path)` throws `FieldAccessException` | Field path has errors or no accessible data | Check response errors and choose the right path |
| DTO receives wrong date/time format | JSON codec and custom scalar disagree | Standardize serializer according to scalar contract |
| Wrong operation runs or none selected | Document has multiple operations but missing/wrong operationName | Set an exact matching operation name |
| Tests pass but real requests fail | Only resolvers tested, variable payloads unverified | Add GraphQlTester and client integration tests |

## 18. Workflow for building requests with variables

When writing an operation that uses variables, follow this sequence:

1. Identify the field or mutation to invoke and its arguments.
2. Declare variables in the operation with exact GraphQL types.
3. Choose nullability according to the API contract; use non-null for truly required data.
4. Wire variables into arguments or input objects where needed.
5. Pass values via `variable(name, value)` or `variables(map)`.
6. Use DTOs when input structure is stable; use maps when flexible payloads are needed.
7. Check omitted, explicit null, and default values.
8. Set operation name when the document has multiple operations.
9. Let the JSON codec serialize data; never concatenate values into the GraphQL document.
10. Use `retrieve(path)` when one field is needed, or `execute()` when inspecting the entire response.
11. Test variable coercion, input objects, and serialization using GraphQlTester/integration tests.
12. Do not log full variables if they contain personal data or secrets.

## 19. Key points to remember

- GraphQL variables separate input data from the document.
- Variables are declared by name and GraphQL type in the operation header.
- `!` denotes non-null; lists can combine nullability at both list and element levels.
- `GraphQlClient` passes single values with `variable(...)` or an entire map with `variables(...)`.
- Keys in the variables map do not have `$` and must match variable names in the document.
- Input objects can be passed via nested maps or DTOs serialized by the JSON codec.
- Custom scalars depend on the JSON representation accepted by the server scalar.
- Omitted differs from explicit null; explicit null does not trigger default values.
- `operationName` identifies which operation to run when a document contains multiple operations.
- Using variables avoids building queries by concatenating user input into GraphQL syntax.
- `retrieve(path)` is convenient for a single field; `execute()` fits when inspecting full data/errors/extensions.
- Test both server variable coercion and client JSON serialization.

GraphQL variables are the standard mechanism for passing data into operations. By declaring accurate types, keeping documents stable, distinguishing omitted from null, and letting the client codec serialize payloads, requests become easier to reuse, test, and maintain.

## References

- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — GraphQlClient](https://docs.spring.io/spring-graphql/reference/client.html#client.graphqlclient)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL Specification — Variables](https://spec.graphql.org/October2021/#sec-Language.Variables)
- [GraphQL Specification — Input Objects](https://spec.graphql.org/October2021/#sec-Input-Objects)
