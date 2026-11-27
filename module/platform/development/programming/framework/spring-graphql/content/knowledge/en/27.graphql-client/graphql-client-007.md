# Retrieving a field with Spring GraphQL Client

A GraphQL client sends an operation describing the fields to fetch, then reads data from the response according to the selection set structure. Spring for GraphQL provides the `GraphQlClient` API to do this in a transport-agnostic way. When only a single field from the response is needed, `retrieve(path)` selects that field and converts it into the desired Java type without having to manually read the entire response envelope.

For example, the client can request `book.title` and directly receive a `String`, or request `book` with several subfields and map it to a DTO. `retrieve` is the step that reads data from the response; the selection set in the GraphQL document determines which fields the server is asked to return. These two steps must match.

After this lesson, you will be able to:

- Create a `GraphQlClient` for the HTTP transport.
- Write GraphQL documents that select only the necessary fields.
- Use variables instead of string-concatenating into queries.
- Read a scalar or nested field using `retrieve(path)`.
- Map objects and lists into Java DTOs.
- Understand paths when using aliases, nested objects, and lists.
- Handle null fields, field errors, and partial data.
- Know when to use `execute()` instead of `retrieve()`.
- Test the client with Reactor Test.

## 1. GraphQL fields and selection sets

GraphQL does not send a separate `SELECT` statement per column. The client sends an operation with a selection set describing the fields to fetch. The server returns the exact selected field structure, which may include nested fields.

Schema example:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    subtitle: String
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

If the client only needs the book title, the operation selects only `title`:

```graphql
query BookTitle($id: ID!) {
    book(id: $id) {
        title
    }
}
```

Response structure:

```json
{
  "data": {
    "book": {
      "title": "Spring GraphQL in Practice"
    }
  }
}
```

If the author is also needed, the client must declare a selection set inside the `author` object:

```graphql
query BookDetails($id: ID!) {
    book(id: $id) {
        id
        title
        author {
            name
        }
    }
}
```

Object fields require a selection set; scalar fields like `title` do not have a sub-block. Selecting only the fields needed reduces network payload size and avoids asking the server to resolve unused fields.

## 2. GraphQlClient as the shared client API

`GraphQlClient` is Spring for GraphQL's client API. It provides a way to build requests, attach documents/variables, execute operations, and read responses. Transport clients can implement this API, for example:

- `HttpGraphQlClient` sends requests over HTTP.
- `WebSocketGraphQlClient` uses WebSocket for GraphQL messages, typically suited for subscriptions.
- `RSocketGraphQlClient` uses RSocket when the application deploys that transport.

The `document(...)`, `variable(...)`, `retrieve(...)`, and `execute()` steps are used consistently at the `GraphQlClient` level, while connection configuration depends on the transport.

In this lesson, examples use HTTP because queries retrieving a single field are typically standard request/response calls.

## 3. Creating HttpGraphQlClient

Create a `WebClient` pointing to the GraphQL endpoint and use it to build `HttpGraphQlClient`:

```java
WebClient webClient = WebClient.builder()
        .baseUrl("http://localhost:8080/graphql")
        .build();

HttpGraphQlClient graphQlClient = HttpGraphQlClient.builder(webClient)
        .build();
```

`HttpGraphQlClient` uses `WebClient` to send GraphQL requests over HTTP. Timeouts, TLS, proxies, authentication, and filters can be configured on `WebClient` as required by the application.

If the application already has a commonly configured `WebClient`, reuse that builder/client instead of creating an inconsistent connection configuration. For endpoints requiring a bearer token, attach credentials from a trusted source using an appropriate application mechanism; do not hard-code tokens into source code or GraphQL documents.

## 4. Retrieving a scalar field

When an operation fetches only one scalar field, `retrieve(path)` selects that field in the response and `toEntity(...)` converts the value to a Java type:

```java
Mono<String> title = graphQlClient.document("""
        query BookTitle($id: ID!) {
            book(id: $id) {
                title
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book.title")
    .toEntity(String.class);
```

Here:

- `document(...)` supplies the GraphQL operation.
- `variable("id", "book-42")` binds a value to `$id`.
- `retrieve("book.title")` selects the `title` field inside the `book` response key.
- `toEntity(String.class)` requests converting the field value into a `String`.

The result is `Mono<String>` because `GraphQlClient` uses a reactive model. The client can subscribe to receive the result or compose it into a Reactor pipeline.

There is no need to deserialize the entire response into a class just to read a single string. `retrieve` is a concise option when the caller only cares about one field and does not need to inspect other parts of the GraphQL response.

## 5. Retrieving a nested object into a DTO

If multiple subfields are needed, select the object at the corresponding path and map it into a DTO:

```java
public record BookSummary(
        String id,
        String title) {
}
```

Operation:

```java
Mono<BookSummary> book = graphQlClient.document("""
        query BookSummary($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book")
    .toEntity(BookSummary.class);
```

The selection set in the document must provide the properties the DTO needs to map. If the DTO has a `subtitle` field but the query does not select `subtitle`, the client cannot expect the server to return that field automatically.

Property names and data types in the DTO should be compatible with the JSON response. You can define dedicated DTOs per use case rather than mapping the entire domain entity into the client response.

## 6. Retrieving a field from a multi-level object

Paths can traverse multiple object levels:

```graphql
query BookAuthor($id: ID!) {
    book(id: $id) {
        author {
            name
        }
    }
}
```

Retrieving only the author's name:

```java
Mono<String> authorName = graphQlClient.document("""
        query BookAuthor($id: ID!) {
            book(id: $id) {
                author {
                    name
                }
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book.author.name")
    .toEntity(String.class);
```

The path `book.author.name` reflects the JSON response structure. Each string segment is a response key at the corresponding level. You cannot request `book.author.name` if the document only selects `book { id }`; the path must point to a field actually selected by the operation.

If a parent object is null, nested fields beneath it have no value to read. For nullable fields, the client must define the appropriate semantics: missing data, non-existent resource, or field error. When distinguishing these situations is necessary, read the full response instead of relying only on the `retrieve` shortcut.

## 7. Retrieving an aliased field

An alias changes the response key without changing the field name in the schema. Because `retrieve(path)` reads the response tree, the path must use the alias.

Operation:

```graphql
query {
    featuredBook: book(id: "book-42") {
        displayTitle: title
    }
}
```

Path to use:

```java
Mono<String> title = graphQlClient.document("""
        query {
            featuredBook: book(id: "book-42") {
                displayTitle: title
            }
        }
        """)
    .retrieve("featuredBook.displayTitle")
    .toEntity(String.class);
```

Do not use `book.title` in this case because the response does not contain the `book` or `title` keys; the response keys are `featuredBook` and `displayTitle`.

Aliases are particularly useful when an operation queries the same field multiple times with different arguments:

```graphql
query Compare {
    newest: books(sort: NEWEST) {
        title
    }
    popular: books(sort: POPULAR) {
        title
    }
}
```

The client can retrieve `newest` or `popular` individually, or use `execute()` to read both branches.

## 8. Retrieving a field with arguments

Arguments are input data for a field, whereas the path is the response location to read. Use variables to pass arguments:

```java
Mono<BookSummary> book = graphQlClient.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", bookId)
    .retrieve("book")
    .toEntity(BookSummary.class);
```

Do not concatenate `bookId` directly into the GraphQL document via string concatenation. Variables keep the document stable, help avoid string-escaping bugs, reduce injection risks caused by malformed document construction, and make requests easier to cache and observe.

If a field takes multiple arguments, each argument can be passed via `.variable(...)` provided the operation declares the corresponding variable:

```graphql
query SearchBooks($keyword: String!, $limit: Int!) {
    searchBooks(keyword: $keyword, limit: $limit) {
        id
        title
    }
}
```

```java
Mono<List<BookSummary>> books = graphQlClient.document("""
        query SearchBooks($keyword: String!, $limit: Int!) {
            searchBooks(keyword: $keyword, limit: $limit) {
                id
                title
            }
        }
        """)
    .variable("keyword", "spring")
    .variable("limit", 10)
    .retrieve("searchBooks")
    .toEntityList(BookSummary.class);
```

## 9. Retrieving an element or a list

If a path points to a list, you can map the elements to a list of DTOs:

```java
Mono<List<BookSummary>> books = graphQlClient.document("""
        query {
            books {
                id
                title
            }
        }
        """)
    .retrieve("books")
    .toEntityList(BookSummary.class);
```

`toEntityList(BookSummary.class)` maps each element in the list. If the response list is empty, the result is an empty list according to collection mapping semantics; there is no need to invent a dummy DTO to represent the absence of elements.

If you only want the element at a specific position, the path can use element-access syntax supported by Spring GraphQL field paths, though it is generally better to retrieve the whole list and select the element in Java for clarity and to avoid relying on indices that might shift.

Example retrieving the list and selecting the first element:

```java
Mono<BookSummary> firstBook = books
        .flatMapMany(Flux::fromIterable)
        .next();
```

Or processing the list in a pipeline:

```java
Mono<List<String>> titles = books.map(items ->
        items.stream().map(BookSummary::title).toList());
```

## 10. A path is a response path, not a schema coordinate

`retrieve(path)` selects a field according to the response structure. The path is affected by aliases and nested selection sets, similar to `errors[].path` in a GraphQL response.

| GraphQL document | Retrieve path |
| --- | --- |
| `book { title }` | `book.title` |
| `featured: book { title }` | `featured.title` |
| `book { writer: author { name } }` | `book.writer.name` |
| `books { id title }` | `books` |
| `newest: books { title }` | `newest` |

Do not use Java resolver method names or class names as paths. The path is not `Book.author` or `Query.book`; it is the key path inside the JSON response.

If a query uses aliases, read using the exact alias in the path. If you change an alias in the document and forget to update the path, the client may fail to find the field even though the server returned the right data.

## 11. Retrieve and GraphQL errors

`retrieve(path)` is a shortcut for cases where the caller needs one specific field. If that field has an associated GraphQL error, converting the field into an entity may throw `FieldAccessException`. The exception provides details about the response field and the associated GraphQL errors.

Example handling field errors:

```java
Mono<String> title = graphQlClient.document("""
        query {
            book(id: "missing") {
                title
            }
        }
        """)
    .retrieve("book.title")
    .toEntity(String.class)
    .onErrorMap(FieldAccessException.class, exception ->
            new BookQueryException("Could not retrieve book title", exception));
```

Do not assume every GraphQL error causes every field to fail. An operation can return partial data: the `book.title` field succeeds while another field has an error. `retrieve("book.title")` focuses on the selected field; if you need to make decisions based on all `errors`, use `execute()`.

Do not catch a generic `RuntimeException` and convert it into a default value without distinguishing transport errors, GraphQL errors, and mapping errors. Doing so can mask server outages or data contract bugs.

## 12. When to use execute() instead of retrieve()?

`retrieve(path)` fits when the caller needs a single field and wants direct mapping. `execute()` fits when full control over the entire GraphQL response is required:

```java
Mono<ClientGraphQlResponse> responseMono = graphQlClient.document("""
        query BookAndRecommendations($id: ID!) {
            book(id: $id) {
                id
                title
            }
            recommendations {
                id
                title
            }
        }
        """)
    .variable("id", "book-42")
    .execute();
```

You can read multiple fields and inspect errors:

```java
public record BookDashboard(
        BookSummary book,
        List<BookSummary> recommendations,
        List<?> errors) {
}

Mono<BookDashboard> dashboard = responseMono.map(response -> {
    ClientResponseField bookField = response.field("book");
    ClientResponseField recommendationsField = response.field("recommendations");

    BookSummary book = bookField.hasErrors()
            ? null
            : bookField.toEntity(BookSummary.class);
    List<BookSummary> recommendations = recommendationsField.hasErrors()
            ? List.of()
            : recommendationsField.toEntityList(BookSummary.class);

    return new BookDashboard(book, recommendations, response.getErrors());
});
```

This snippet illustrates reading fields independently while keeping the response-level error list. Real applications can choose a dedicated result type for each failing field; the key point is checking `hasErrors()` before calling `toEntity` if partial data should be preserved. You can check `response.getErrors()` to see all errors for the operation.

Choose `execute()` when:

- You need to read multiple fields from the same response.
- You need to inspect all `errors` or `extensions`.
- You need to preserve partial data when another branch fails.
- You need to distinguish omitted, null, and errored fields.
- You need to access response metadata or write custom error-handling logic.

## 13. Distinguishing null, omitted, and field errors

A field can lack a value for several reasons:

- The server returns `null` according to the schema and domain data.
- A parent object is null, so nested fields do not appear.
- The field was omitted due to a directive or because the selection set did not request it.
- The field raised an execution error and GraphQL applied null propagation.

With `execute()`, you can inspect the state of a response field:

```java
Mono<Void> inspect = graphQlClient.document("""
        query {
            book(id: "book-42") {
                subtitle
            }
        }
        """)
    .execute()
    .doOnNext(response -> {
        ClientResponseField subtitle = response.field("book.subtitle");

        if (subtitle.isOmitted()) {
            // Field is not present in the response selection/result.
        }
        else if (subtitle.hasErrors()) {
            // Field has associated GraphQL errors.
        }
        else if (subtitle.getValue() == null) {
            // Field was returned with a null value.
        }
        else {
            String value = subtitle.toEntity(String.class);
        }
    })
    .then();
```

These states should be interpreted against the actual response. If a field was not selected in the document, that is not a data request rejected by the server; if a nullable field returns null, the client should not infer that an error occurred. If the field has errors, read the error path and code rather than looking only at null.

## 14. Retrieving a nullable field

Suppose the schema declares:

```graphql
type Book {
    subtitle: String
}
```

`subtitle` can be null. With the reactive API, `Mono` cannot emit a Java null value. Depending on the mapping API, a null value may be represented by `Mono.empty()` or must be checked directly via the response field.

If the application needs to distinguish "subtitle is absent" from "the field errored", use `execute()` and inspect `ClientResponseField` instead of relying solely on whether `Mono` emits an element. If you only need an optional value, you can convert the result to `Optional` at the application boundary after defining the semantics.

Example checking directly:

```java
Mono<Optional<String>> subtitle = graphQlClient.document("""
        query {
            book(id: "book-42") {
                subtitle
            }
        }
        """)
    .execute()
    .map(response -> {
        ClientResponseField field = response.field("book.subtitle");
        if (field.hasErrors()) {
            throw new IllegalStateException("Could not retrieve book subtitle");
        }
        return Optional.ofNullable((String) field.getValue());
    });
```

The example above demonstrates converting a nullable field into an `Optional`. In production code, replace `IllegalStateException` with a domain-specific exception and attach errors from `field.getErrors()` to preserve essential diagnostic information.

## 15. Inline documents and named documents

You can pass a GraphQL document inline using `.document(...)`, which works well for short queries or simple examples:

```java
graphQlClient.document("""
        query BookTitle($id: ID!) {
            book(id: $id) {
                title
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book.title")
    .toEntity(String.class);
```

For operations reused frequently, you can store the document in resources and call `.documentName(...)`:

```java
graphQlClient.documentName("book-title")
        .variable("id", "book-42")
        .retrieve("book.title")
        .toEntity(String.class);
```

Named documents separate queries from Java code, making them easier to review and reuse. Ensure the resource is placed where the `GraphQlClient` configuration can find it and that the document name matches the resource. Whether the document is inline or named, the retrieve path must still match the operation's response keys.

## 16. Combining retrieve with a Reactor pipeline

Because the client returns `Mono` or `Flux`, field retrieval can be combined with Reactor operators:

```java
Mono<String> normalizedTitle = graphQlClient.document("""
        query BookTitle($id: ID!) {
            book(id: $id) {
                title
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book.title")
    .toEntity(String.class)
    .map(String::trim)
    .filter(title -> !title.isBlank());
```

Do not call `.block()` inside a WebFlux controller or inside a reactive service handling requests. Return the `Mono` to the caller or continue composing the pipeline. In command-line tools, synchronous tests, or imperative boundaries, `block()` can be used intentionally with an appropriate timeout.

If multiple independent operations need to be called, you can combine them with `Mono.zip`, but account for concurrent load and request limits toward the server. Do not fire hundreds of parallel queries just because the client API returns reactive types.

## 17. Client authentication and headers

An HTTP GraphQL client often needs to send credentials so the server can authenticate the caller. Headers can be configured on `WebClient`:

```java
WebClient webClient = WebClient.builder()
        .baseUrl("https://api.example.test/graphql")
        .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
        .build();

HttpGraphQlClient graphQlClient = HttpGraphQlClient.builder(webClient)
        .build();
```

This example only illustrates the header mechanism; in real applications, tokens should come from an OAuth2 client, token relay, or appropriate credential provider. Do not use `defaultHeader` with a per-request user token on a shared singleton client, because requests from other users could inadvertently send the wrong credentials. When tokens vary by caller, use a per-request header mechanism or create appropriately scoped clients.

Do not pass access tokens in GraphQL variables or query strings. HTTP authorization headers and secret-protection mechanisms should be managed separately from GraphQL documents.

## 18. Testing field retrieval

An integration test can call `GraphQlClient` against a test server and verify that the field is mapped properly:

```java
@Test
void retrievesBookTitle() {
    StepVerifier.create(graphQlClient.document("""
            query BookTitle($id: ID!) {
                book(id: $id) {
                    title
                }
            }
            """)
        .variable("id", "book-42")
        .retrieve("book.title")
        .toEntity(String.class))
        .expectNext("Spring GraphQL in Practice")
        .verifyComplete();
}
```

This test assumes `graphQlClient` is configured to point to the test application and the fixture has book `book-42`. `StepVerifier` verifies reactive results without calling `.block()`.

Scenarios that should be tested:

1. Retrieving a scalar field.
2. Retrieving a nested object into a DTO.
3. Retrieving an alias using the renamed response key.
4. Retrieving a list using `toEntityList`.
5. Passing arguments via variables.
6. A nullable field returning null.
7. A field producing a GraphQL error and the client receiving `FieldAccessException` or the designed error handling.
8. Other fields having partial data while one branch errors; use `execute()` to verify.
9. Invalid requests and response errors.
10. Authorization headers sent accurately per request/caller.

If the goal is to test server resolvers, use `GraphQlTester` appropriate for server tests. If the goal is to test `GraphQlClient`, invoke through the actual client transport or an HTTP test server to verify both request serialization and response mapping.

## 19. Common issues

- **Selecting a field in retrieve but forgetting to select it in the document:** the server does not return fields not requested in the selection set.
- **Using the schema field name instead of the alias:** the path does not match the response key.
- **Confusing retrieve path with Java property path:** the path follows the GraphQL JSON response structure.
- **Using `toEntity` for a list:** use `toEntityList` when the path returns an array.
- **Using a DTO object when the query selects only a few fields:** unselected properties will have no data.
- **Concatenating arguments into the query string:** prone to escaping bugs; use variables.
- **Ignoring field errors:** null may be due to absent data or an execution error.
- **Using `retrieve` when multiple branches/partial data are needed:** use `execute()` to inspect the entire response.
- **Calling `.block()` inside a reactive request flow:** can block threads and negate reactive benefits.
- **Using a fixed token on a singleton WebClient for multiple callers:** risks leaking credentials between users.
- **Testing the server with the client API or vice versa:** choose the tester matching the layer under verification.
- **Assuming HTTP 200 means every field succeeded:** GraphQL errors still must be read when handling the full response.

## 20. Workflow for retrieving a field

When reading a field from a GraphQL server using Spring GraphQL Client, follow these steps:

1. Identify the field and required arguments in the schema.
2. Write an operation with a selection set containing only the needed field and subfields to map.
3. Declare variables for arguments instead of concatenating values into the document.
4. Determine the response keys; if using aliases, the path must use the aliases.
5. Use `retrieve(path)` to select the field in the response.
6. Use `toEntity(...)` for scalars/objects or `toEntityList(...)` for lists.
7. If you need to handle partial data, multiple fields, null/omitted values, or all errors, use `execute()`.
8. Handle field errors with `FieldAccessException` or a dedicated policy; do not swallow all exceptions.
9. Compose `Mono`/`Flux` without blocking inside reactive flows.
10. Test requests, variables, paths, DTO mapping, errors, and authentication over an actual transport.

`retrieve(path)` is a concise way to extract a specific field from a GraphQL response with Spring GraphQL Client. The selection set dictates which fields the server returns, while the path chooses the response key to map into a Java scalar, object, or list. By passing arguments via variables, accounting for aliases in paths, and switching to `execute()` when partial data or errors must be controlled, the client can read data accurately while preserving GraphQL response semantics.

## References

- [Spring for GraphQL — GraphQL Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — GraphQlClient API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.html)
- [Spring for GraphQL — HttpGraphQlClient API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/HttpGraphQlClient.html)
- [Spring for GraphQL — ClientGraphQlResponse API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/ClientGraphQlResponse.html)
- [Project Reactor — Reactor Core Reference](https://projectreactor.io/docs/core/release/reference/)
