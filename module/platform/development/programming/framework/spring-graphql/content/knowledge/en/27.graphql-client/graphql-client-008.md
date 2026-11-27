# Decoding responses in Spring for GraphQL Client

Spring for GraphQL provides **GraphQlClient** to send GraphQL requests and decode responses over HTTP, WebSocket, or RSocket. After sending a document, the client can choose to decode a single field directly with **retrieve(path)** or receive the entire **ClientGraphQlResponse** via **execute()** to inspect data, errors, and metadata itself.

Choosing the right decoding approach is important because GraphQL allows returning partial data. A response can contain valid **data** alongside **errors** for certain fields. If the client treats any presence of **errors** as a failed request, the application may discard usable data. Conversely, if it only decodes a field without checking associated errors, the client may confuse **null** caused by an error with a valid **null**.

## 1. GraphQlClient and transports

**GraphQlClient** defines a unified, transport-independent workflow. Common implementations include:

| Client | Transport | Characteristics |
| --- | --- | --- |
| **HttpGraphQlClient** | HTTP via **WebClient** | Non-blocking, suited for reactive applications. |
| **HttpSyncGraphQlClient** | HTTP via **RestClient** | Blocking, suited for synchronous flows. |
| **WebSocketGraphQlClient** | WebSocket | Long-lived connection, supports subscription streaming. |
| **RSocketGraphQlClient** | RSocket | Request-response and streaming over RSocket. |

Example creating an HTTP client:

~~~java
import org.springframework.graphql.client.HttpGraphQlClient;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
        .baseUrl("https://api.example.com/graphql")
        .build();

HttpGraphQlClient graphQlClient = HttpGraphQlClient.create(webClient);
~~~

How requests are sent and responses decoded after creating the client is similar across transports. Differences mainly lie in connection setup, authentication, timeouts, and streaming capabilities.

## 2. GraphQL response structure

A GraphQL response typically has three parts:

- **data**: the operation's result, which can be an object, list, or **null**.
- **errors**: a list of errors if any; can coexist with **data**.
- **extensions**: additional metadata provided by the server or implementation.

Example successful response:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring for GraphQL"
    }
  }
}
~~~

Example response with partial data:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring for GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Unable to load author details",
      "path": ["book", "author"],
      "extensions": {
        "code": "AUTHOR_SERVICE_UNAVAILABLE"
      }
    }
  ],
  "extensions": {
    "traceId": "trace-abc-123"
  }
}
~~~

In the second example, the **author** field failed, but **book.id** and **book.title** remain usable. The client must read both **data** and **errors** to decide how to proceed.

## 3. Two decoding approaches: retrieve and execute

**GraphQlClient.RequestSpec** provides two main approaches:

| Call | Result | When to use |
| --- | --- | --- |
| **retrieve(path)** | **RetrieveSpec**, decodes a specific field | Only one field is needed and concise code is desired. |
| **execute()** | **Mono<ClientGraphQlResponse>** | Need to inspect full response, partial data, errors, or extensions. |
| **retrieveSync(path)** | Decodes a single field in blocking style | Used with the synchronous client. |
| **executeSync()** | Direct **ClientGraphQlResponse** | Need full response in a blocking flow. |

**retrieve** is a shortcut for **execute**: it extracts the field at the path beneath the **data** key and then decodes that field to the desired Java type. If you need to make decisions per error or preserve partial data, use **execute**.

## 4. Decoding a single field with retrieve

Suppose the schema is:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    isbn: String
}
~~~

Java DTO:

~~~java
public record Book(
        String id,
        String title,
        String isbn) {
}
~~~

Sending the query and decoding the **book** field:

~~~java
String document = """
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
                isbn
            }
        }
        """;

Mono<Book> bookMono = graphQlClient.document(document)
        .variable("id", "book-10")
        .retrieve("book")
        .toEntity(Book.class);
~~~

**retrieve("book")** specifies the path relative to the **data** key in the response. **toEntity(Book.class)** decodes the value at that path into **Book**.

You can extract the request into a variable for reuse:

~~~java
var request = graphQlClient.document(document)
        .variable("id", "book-10");

Mono<Book> result = request
        .retrieve("book")
        .toEntity(Book.class);
~~~

If the document has multiple operations, use **operationName(...)** to choose which operation to run:

~~~java
Mono<Book> result = graphQlClient.document(documentWithMultipleOperations)
        .operationName("FindBook")
        .variable("id", "book-10")
        .retrieve("book")
        .toEntity(Book.class);
~~~

## 5. Field paths and aliases

Paths in **retrieve** are evaluated from **data**, using dots to traverse nested fields and optionally array indices:

~~~java
.retrieve("book")
.retrieve("book.author")
.retrieve("book.reviews[0]")
.retrieve("book.reviews[0].rating")
~~~

Example response:

~~~json
{
  "data": {
    "catalog": {
      "featured": {
        "id": "book-10",
        "title": "Spring for GraphQL"
      }
    }
  }
}
~~~

The path to use is **catalog.featured**.

If a query uses an alias, the path must use the alias appearing in the response:

~~~graphql
query {
    featuredBook: book(id: "book-10") {
        id
        title
    }
}
~~~

Decode using:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .retrieve("featuredBook")
        .toEntity(Book.class);
~~~

The path is not the schema field name if an alias renamed the field in the response. When handling errors, **errors.path** also uses the alias because it points to the position in the response.

## 6. Decoding lists with toEntityList

When a field returns a list, use **toEntityList** to decode each element:

~~~graphql
type Query {
    booksByAuthor(authorId: ID!): [Book!]!
}
~~~

~~~java
Mono<List<Book>> books = graphQlClient.document("""
        query BooksByAuthor($authorId: ID!) {
            booksByAuthor(authorId: $authorId) {
                id
                title
                isbn
            }
        }
        """)
        .variable("authorId", "author-7")
        .retrieve("booksByAuthor")
        .toEntityList(Book.class);
~~~

**toEntityList(Book.class)** returns **Mono<List<Book>>**, not **Flux<Book>**. The server returns a single GraphQL response containing a list; the client decodes that list into a Java **List**.

If the field has value **null** with no associated errors, **toEntityList** returns an empty list. If the field is missing from the response or has associated errors, accessing it may emit **FieldAccessException**.

## 7. Decoding generic types with ParameterizedTypeReference

When the target type contains nested generics, **Class<T>** does not retain sufficient type information at runtime. Use **ParameterizedTypeReference<T>**:

~~~java
import java.util.Map;
import org.springframework.core.ParameterizedTypeReference;

Mono<Map<String, Object>> bookMap = graphQlClient.document(document)
        .retrieve("book")
        .toEntity(new ParameterizedTypeReference<Map<String, Object>>() {});
~~~

You can use generic types for lists or wrappers:

~~~java
public record PageResult<T>(
        List<T> content,
        int page,
        int totalPages) {
}
~~~

~~~java
Mono<PageResult<Book>> page = graphQlClient.document(pageDocument)
        .retrieve("bookPage")
        .toEntity(new ParameterizedTypeReference<PageResult<Book>>() {});
~~~

The Java structure must be compatible with the JSON data returned by GraphQL. If a DTO has incompatible constructors, record components, or properties, decoding may fail even though the GraphQL response is valid.

## 8. Synchronous decoding

With **HttpSyncGraphQlClient**, you can use **retrieveSync**:

~~~java
import org.springframework.graphql.client.HttpSyncGraphQlClient;
import org.springframework.web.client.RestClient;

RestClient restClient = RestClient.builder()
        .baseUrl("https://api.example.com/graphql")
        .build();

HttpSyncGraphQlClient syncClient =
        HttpSyncGraphQlClient.create(restClient);

Book book = syncClient.document(document)
        .variable("id", "book-10")
        .retrieveSync("book")
        .toEntity(Book.class);
~~~

**retrieveSync** returns the result directly and can throw an exception immediately if the field cannot be accessed or decoded.

With **HttpGraphQlClient**, **retrieve(...).toEntity(...)** returns **Mono<T>**. Do not call **block()** inside a WebFlux event-loop or inside a reactive pipeline just to get a synchronous value. Keep composing using Reactor operators.

## 9. When is execute() needed?

**retrieve** is convenient when only one field is needed. However, it provides no way to inspect the entire response before decoding. Use **execute()** when you need to:

- Check whether the request was valid.
- Distinguish request errors from field errors.
- Retain partial data when a subfield fails.
- Read **extensions** or multiple distinct fields in the same response.
- Decide independently which fields can fall back and which must fail.
- Handle intentional **null** differently from error-induced **null**.

Example:

~~~java
Mono<ClientGraphQlResponse> responseMono = graphQlClient.document(document)
        .variable("id", "book-10")
        .execute();
~~~

**execute()** returns **Mono<ClientGraphQlResponse>**. With the synchronous client, use **executeSync()** to obtain the response directly.

## 10. Checking isValid()

**ClientGraphQlResponse** extends **GraphQlResponse**, which provides **isValid()**.

A response is considered invalid if:

- The **data** key is absent, typically due to pre-execution errors such as parse or validation errors.
- The **data** key is present but its value is **null**, for example when an execution error causes all data to become null via null propagation.

A valid response has a non-null **data** key. The response may still contain **errors** and some fields with null values due to failed field resolvers.

| Response | isValid() | Meaning |
| --- | --- | --- |
| No **data**, only **errors** | **false** | Request error before any data result was produced. |
| **data: null** with errors | **false** | Execution failed to produce valid data. |
| **data** is object/list, no errors | **true** | Result has no GraphQL errors. |
| **data** is object/list, with field errors | **true** | Partial data present alongside errors on one or more fields. |

**Do not use isValid() as a "no errors" flag.** If you need to know whether the response has any errors, also check **getErrors()**.

Example:

~~~java
Mono<String> title = graphQlClient.document(document)
        .variable("id", "book-10")
        .execute()
        .map(response -> {
            if (!response.isValid()) {
                throw new IllegalStateException(
                        "GraphQL request produced no valid data: "
                                + response.getErrors());
            }

            if (!response.getErrors().isEmpty()) {
                // Response has partial data and field errors.
                // Error codes can be logged or handled by path.
            }

            // Decode only title; errors in other fields do not lose title.
            return response.field("book.title").toEntity(String.class);
        });
~~~

This snippet illustrates checking status. In real applications, use custom domain exceptions or return a result containing both data and errors rather than throwing **IllegalStateException** for all cases.

## 11. Distinguishing request errors and field errors

**getErrors()** returns a list of **ResponseError**. They can be distinguished by **path**:

- Request errors apply to the entire operation and typically have an empty path.
- Field errors are attached to a specific location in the response; path contains field names and potentially list indices.

Request error example:

~~~json
{
  "errors": [
    {
      "message": "Cannot query field 'unknownField' on type 'Query'."
    }
  ]
}
~~~

There is no **data**, so the response is invalid.

Field error example:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring for GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["book", "author"],
      "extensions": {
        "code": "AUTHOR_SERVICE_UNAVAILABLE"
      }
    }
  ]
}
~~~

Because **data** is non-null, the response remains valid. The error is scoped only to **book.author**; other fields remain usable.

Error metadata can be read:

~~~java
import java.util.Map;

response.getErrors().forEach(error -> {
    String message = error.getMessage();
    String path = error.getPath();
    Map<String, Object> extensions = error.getExtensions();

    log.warn("GraphQL field error path={} message={} extensions={}",
            path, message, extensions);
});
~~~

**ResponseError.getParsedPath()** returns the path segments, including field names and integer list indices. **getLocations()** returns positions in the GraphQL document if present. **getExtensions()** holds metadata specific to the server or GraphQL implementation; do not assume every server returns the exact same structure.

## 12. Distinguishing valid null fields from error-induced null fields

A nullable field can validly return **null** with no errors. For instance, a book without an assigned author:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "author": null
    }
  }
}
~~~

In another case, a resolver failure causes the field to become null:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["book", "author"]
    }
  ]
}
~~~

If the client only checks **getValue() == null**, it cannot distinguish the two cases. Check **getErrors()** as well:

~~~java
ClientResponseField authorField = response.field("book.author");

if (authorField.getValue() == null) {
    if (authorField.getErrors().isEmpty()) {
        // Null is a valid result per schema/business logic.
    }
    else {
        // Field is null due to an error; handle error or fallback.
    }
}
else {
    Author author = authorField.toEntity(Author.class);
}
~~~

This is one of the primary reasons to use **execute()** when an application needs fine-grained control over partial responses.

## 13. ClientResponseField and partial decoding

**response.field(path)** returns a **ClientResponseField**, allowing you to inspect and decode a specific field.

Useful methods:

| Method | Purpose |
| --- | --- |
| **getValue()** | Gets the raw field value. |
| **getPath()** | Gets the path as a string. |
| **getParsedPath()** | Gets the path as segments. |
| **getErrors()** | Gets errors associated with the field. |
| **toEntity(Class<T>)** | Decodes the field into a single object. |
| **toEntity(ParameterizedTypeReference<T>)** | Decodes the field into a generic type. |
| **toEntityList(Class<T>)** | Decodes the field into a list of objects. |

Example reading multiple fields from one response:

~~~java
public record BookSummary(String id, String title) {
}
~~~

~~~java
Mono<BookSummary> summary = graphQlClient.document("""
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
        .map(response -> {
            if (!response.isValid()) {
                throw new IllegalStateException("GraphQL request failed");
            }

            String id = response.field("book.id").toEntity(String.class);
            String title = response.field("book.title").toEntity(String.class);

            return new BookSummary(id, title);
        });
~~~

This example reads only the required fields. Even if a subfield had an error, as long as **book.id** and **book.title** are unaffected, the client can still use them. If you want to decode the entire **book** object, examine errors attached to **book** or its subfields.

## 14. Decoding the entire response

**ClientGraphQlResponse.toEntity(...)** decodes the entire response map into the target type. This is useful when you want to retain the full **data**, **errors**, or **extensions** wrapper.

Example retrieving the response as a map:

~~~java
import java.util.Map;
import org.springframework.core.ParameterizedTypeReference;

Mono<Map<String, Object>> rawResponse = graphQlClient.document(document)
        .variable("id", "book-10")
        .execute()
        .map(response -> response.toEntity(
                new ParameterizedTypeReference<Map<String, Object>>() {}));
~~~

If you only need the **data** portion, use **getData()**:

~~~java
Mono<Map<String, Object>> data = graphQlClient.document(document)
        .variable("id", "book-10")
        .execute()
        .map(ClientGraphQlResponse::getData);
~~~

**getData()** returns null when the response is invalid as defined by **isValid()**. When error handling is needed, do not ignore **getErrors()** before reading data.

## 15. Reading response extensions

A GraphQL response can contain response-level **extensions**, such as trace ID, query cost, or server-specific metadata:

~~~json
{
  "data": {
    "books": []
  },
  "extensions": {
    "traceId": "trace-123",
    "queryCost": 18
  }
}
~~~

Read using:

~~~java
Mono<Map<Object, Object>> extensions = graphQlClient.document(document)
        .execute()
        .map(ClientGraphQlResponse::getExtensions);
~~~

Distinguish between:

- **response.getExtensions()**: response-level metadata.
- **response.getErrors().get(i).getExtensions()**: metadata belonging to a specific error.

Extensions depend on the server and protocol. Check that keys exist, verify data types, and avoid coupling core business logic to custom extensions if the client must work across multiple GraphQL servers.

## 16. Exceptions when decoding responses

Not all errors have the same root cause. **GraphQlClient** defines these main exceptions:

| Exception | When it occurs | How to handle |
| --- | --- | --- |
| **FieldAccessException** | Path missing in response, invalid response, or field path has associated errors | Read **getResponse()** and **getField()** to inspect the exact response/errors. |
| **GraphQlClientException** | General client error, including decoding failure into the target type | Check DTO, JSON shape, and data types. |
| **GraphQlTransportException** | Transport error or error encoding/decoding request/response at transport layer | Check network, HTTP status, media type, and payload. |

If the field is present but cannot be decoded into the requested Java type, Spring for GraphQL throws **GraphQlClientException** rather than **FieldAccessException**.

Example handling **FieldAccessException** in a reactive pipeline:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .variable("id", "book-10")
        .retrieve("book")
        .toEntity(Book.class)
        .onErrorResume(FieldAccessException.class, exception -> {
            ClientGraphQlResponse response = exception.getResponse();
            ClientResponseField field = exception.getField();

            log.warn("Cannot decode field path={} errors={}",
                    field.getPath(), field.getErrors());

            return Mono.empty();
        });
~~~

This example chooses to return **Mono.empty()** when the field cannot be accessed. In real applications, only fall back when the error is acceptable; do not turn every error into an empty result, as that makes it hard for the client to tell "no data" apart from "server returned an error".

With **execute()**, GraphQL errors inside **ClientGraphQlResponse** do not automatically become reactive exceptions. However, transport errors can still terminate the **Mono** with **GraphQlTransportException**.

## 17. Retaining partial data instead of discarding the whole response

A valid response can contain useful data alongside field errors. If you use **retrieve("book")** and the **book** path has an error on a subfield, **FieldAccessException** may be thrown because the error lies beneath the accessed path.

When you need to preserve partial data, use **execute()** and read each error-free field individually:

~~~java
public record BookView(String id, String title, String authorName) {
}
~~~

~~~java
Mono<BookView> loadBookView(GraphQlClient client) {
    return client.document("""
            query {
                book(id: "book-10") {
                    id
                    title
                    author {
                        name
                    }
                }
            }
            """)
            .execute()
            .map(response -> {
                if (!response.isValid()) {
                    throw new IllegalStateException(
                            "GraphQL request has no valid data");
                }

                String id = response.field("book.id").toEntity(String.class);
                String title = response.field("book.title").toEntity(String.class);

                ClientResponseField authorField =
                        response.field("book.author.name");

                String authorName = null;
                if (authorField.getValue() != null
                        && authorField.getErrors().isEmpty()) {
                    authorName = authorField.toEntity(String.class);
                }

                return new BookView(id, title, authorName);
            });
}
~~~

Here, an error on **book.author.name** does not cause **book.id** and **book.title** to be lost. The client actively constructs the view from readable fields.

This example assumes **book** exists and both **id** and **title** succeeded. If **book** itself can validly be null, check **response.field("book")** before reading its child fields.

Do not ignore errors indiscriminately. If the failing field is mandatory for business logic, throw a domain error or trigger a retry rather than constructing an apparently valid object missing critical information.

## 18. Subscription responses can also be decoded

Subscriptions return multiple GraphQL responses over time. With streaming-capable client transports, use **retrieveSubscription(path)** to decode a field from each response:

~~~java
Flux<BookEvent> events = webSocketGraphQlClient.document("""
        subscription {
            bookAdded {
                id
                title
            }
        }
        """)
        .retrieveSubscription("bookAdded")
        .toEntity(BookEvent.class);
~~~

If you need to inspect errors and partial data on each event, use **executeSubscription()**:

~~~java
Flux<ClientGraphQlResponse> responses = webSocketGraphQlClient.document("""
        subscription {
            bookAdded {
                id
                title
            }
        }
        """)
        .executeSubscription();
~~~

Each element of **Flux<ClientGraphQlResponse>** is an event response that can be inspected using **isValid()**, **getErrors()**, and **field(path)**.

The subscription stream can terminate with **SubscriptionErrorException** if the server sends a terminal error message, or **WebSocketDisconnectedException** if the connection drops. These are stream/transport lifecycle errors, distinct from an event response containing field errors.

## 19. Common issues when decoding responses

| Symptom | Cause | Resolution |
| --- | --- | --- |
| **retrieve("book")** cannot find field | Wrong path or query did not select that field | Compare path against response data and aliases. |
| **toEntity(Book.class)** throws **FieldAccessException** | Field has errors, is null due to error, or response is invalid | Use **execute()** to inspect response and field errors. |
| Field is null without errors | Null is a valid value or resolver returned null | Check **getErrors()** before treating null as an error. |
| DTO fails to decode | Incompatible JSON shape or property types | Check DTO, constructors, generic types, and scalar representations. |
| HTTP response received but client throws **GraphQlTransportException** | Transport/HTTP/encode/decode error | Check status, Content-Type, and transport logs. |
| **isValid()** is true yet errors exist | Response has partial data and field errors | Check **getErrors()** separately; do not treat **isValid** as "error-free". |
| **toEntityList** returns empty list | Field is null without errors or list is genuinely empty | Distinguish null vs. empty per API contract if needed. |
| One failing field drops the whole object when using retrieve | Error lies at, above, or below the accessed path | Use **execute()** and decode each field independently. |
| Subscription stops abruptly | Server terminal error or transport disconnect | Distinguish **SubscriptionErrorException** and **WebSocketDisconnectedException**. |

## 20. Testing response decoding

Test at least the following categories:

1. Object fields decode properly into DTOs with **retrieve(...).toEntity(...)**.
2. Lists decode properly with **toEntityList(...)**.
3. Generic DTOs decode properly with **ParameterizedTypeReference**.
4. Aliases and nested paths are accessed using response paths.
5. Error-free null fields are distinguished from null fields with errors.
6. Request errors cause **isValid()** to return false.
7. Partial data alongside field errors is preserved.
8. **FieldAccessException** provides the response and field for investigation.
9. Type decoding mismatches are distinguished from transport failures.
10. Response extensions are read without assuming they are always present.
11. Each subscription event decodes properly and terminal errors are handled separately.

When testing via a mock HTTP server or integration environment, construct sample responses with complete **data**, partial **data**, **errors** without **data**, null fields with/without errors, and mismatched payload types. This verifies both decoder behavior and how the application handles each outcome.

## 21. Checklist for choosing how to decode

1. Need only one field and no full-response inspection: use **retrieve(path)**.
2. Need a list: use **toEntityList(elementType)**.
3. Need a generic type: use **ParameterizedTypeReference**.
4. Need response metadata, multiple fields, or partial data: use **execute()**.
5. Need blocking: use **retrieveSync** or **executeSync** with the synchronous client.
6. Use **isValid()** to identify responses without valid data, not as an error-free flag.
7. Check **getErrors()** to distinguish request errors from field errors.
8. Check **ClientResponseField.getErrors()** when a field's value is null.
9. Use **FieldAccessException.getResponse()** and **getField()** to handle field access failures.
10. Distinguish **GraphQlClientException** from decoding versus **GraphQlTransportException** from transport.
11. For subscriptions, use **retrieveSubscription** or **executeSubscription**.
12. Only fall back when missing data is acceptable to business logic; do not mask mandatory errors.

**retrieve** enables quick decoding of a single field by path; **execute** gives control over the entire response. Understanding **isValid**, **errors**, **extensions**, field paths, and client exceptions helps the application handle both complete results and partial data accurately. By selecting the decoding method that fits the need and checking errors at the right scope, the Spring for GraphQL client can leverage valid data without overlooking real errors.

References:
- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [GraphQlClient.RequestSpec API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RequestSpec.html)
- [GraphQlClient.RetrieveSpec API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RetrieveSpec.html)
- [ClientGraphQlResponse API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/ClientGraphQlResponse.html)
- [ClientResponseField API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/ClientResponseField.html)
- [GraphQlResponse API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/GraphQlResponse.html)
