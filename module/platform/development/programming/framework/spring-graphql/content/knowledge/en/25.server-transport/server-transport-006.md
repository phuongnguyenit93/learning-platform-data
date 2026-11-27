# GraphQL HTTP request in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Describe the structure of a GraphQL request sent over HTTP.
- Distinguish the `query`, `operationName`, `variables`, and `extensions` components.
- Send Queries and Mutations using HTTP POST with a JSON body.
- Understand how to use HTTP GET for Queries and its caching and URL limitations.
- Set `Content-Type`, `Accept`, and required headers.
- Connect to the default HTTP endpoint of Spring for GraphQL.
- Understand how variables are converted into resolver arguments.
- Distinguish HTTP status codes from GraphQL errors in responses.
- Apply authentication, CORS, and request size limits.
- Test HTTP requests using `HttpGraphQlTester`.

## 1. What is a GraphQL HTTP request?

GraphQL defines a query language and a response format. When exposing an API over HTTP, clients send a GraphQL document along with the required data to the server endpoint.

A single endpoint typically serves multiple operations:

- Query to read data.
- Mutation to modify data.
- Subscriptions usually use a streaming-capable transport like WebSocket rather than a standard HTTP request/response.

In Spring for GraphQL, the HTTP request is received by the GraphQL HTTP handler, converted into a GraphQL request to execute the schema and resolvers, and the result is then converted into an HTTP response.

Example of a client fetching book information:

~~~graphql
query FindBook {
    book(id: "book-42") {
        id
        title
    }
}
~~~

The GraphQL document above is not the entire HTTP request. When sent over HTTP, the document is placed inside a JSON object along with required metadata such as the operation name and variables.

## 2. Structure of a GraphQL request over HTTP

For a standard JSON request, the body has the following fields:

| Field | Required? | Meaning |
| --- | --- | --- |
| `query` | Yes in standard requests | GraphQL document containing the operation |
| `operationName` | No, if the document has only one operation | Name of the operation to execute when the document contains multiple operations |
| `variables` | No | JSON object containing values for the variables in the document |
| `extensions` | No | Extension metadata agreed upon between client and server |

Example POST body:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
    "operationName": "FindBook",
    "variables": {
        "id": "book-42"
    }
}
~~~

The server uses `query` to parse and validate the GraphQL document. `operationName` selects which operation to execute. `variables` supplies runtime values for the variables declared in the document.

`extensions` is intended for extension metadata such as the persisted query protocol if implemented by the application. Do not put arbitrary custom fields in `extensions` and assume Spring for GraphQL or every GraphQL server understands them.

A request typically only needs `query` if the document has one operation and uses no variables. However, in real-world applications, you should name operations and pass dynamic data using variables.

## 3. Sending requests via HTTP POST

HTTP POST is the standard way to send GraphQL Queries and Mutations. The body contains JSON with `Content-Type: application/json`.

You can use a request file in IntelliJ HTTP Client:

~~~http
POST http://localhost:8080/graphql
Content-Type: application/json
Accept: application/json

{
  "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
  "operationName": "FindBook",
  "variables": {
    "id": "book-42"
  }
}
~~~

Or send a Mutation:

~~~http
POST http://localhost:8080/graphql
Content-Type: application/json
Accept: application/json

{
  "query": "mutation RenameBook($id: ID!, $title: String!) { renameBook(id: $id, title: $title) { id title } }",
  "operationName": "RenameBook",
  "variables": {
    "id": "book-42",
    "title": "Spring for GraphQL"
  }
}
~~~

POST is suitable when documents are long, variables are large, or operations contain data that should not appear in the URL. POST is also the clear choice for Mutations.

Do not send passwords, tokens, or sensitive data as inline literals inside the query document. Use variables to separate the document from runtime data, while ensuring transport and logging are configured securely.

## 4. Separating the GraphQL document and variables

Variables allow reusing the same document with different datasets.

GraphQL document:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

HTTP JSON body:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
    "operationName": "FindBook",
    "variables": {
        "id": "book-42"
    }
}
~~~

In the document, `$id` is a variable of type `ID!`. In the JSON, `variables.id` provides the value `"book-42"`.

With an input object:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
    }
}
~~~

Body:

~~~json
{
    "query": "mutation CreateBook($input: CreateBookInput!) { createBook(input: $input) { id title } }",
    "operationName": "CreateBook",
    "variables": {
        "input": {
            "title": "Spring GraphQL",
            "isbn": "9780000000000"
        }
    }
}
~~~

The JSON object inside `variables` must match the input type declared in the schema. GraphQL performs coercion and validation before calling the resolver. If a required field is missing or an incorrect type is passed, the operation can be rejected before the business resolver runs.

## 5. operationName when a document has multiple operations

A document can declare multiple operations:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}

query FindBooks {
    books {
        id
        title
    }
}
~~~

When sending this document, the client must specify which operation to run using `operationName`:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title } } query FindBooks { books { id title } }",
    "operationName": "FindBooks",
    "variables": {}
}
~~~

If the document contains only one operation, `operationName` can be omitted. If the document has multiple operations without specifying an operation name, the server cannot determine which operation to execute and will return a GraphQL error.

Operation names are case-sensitive and must match the name declared in the document. Do not confuse `operationName` with field names or controller method names.

Giving operations meaningful names such as `FindBook`, `SearchBooks`, and `CreateBook` makes logging, tracing, and performance monitoring easier.

## 6. HTTP GET for GraphQL Queries

GraphQL over HTTP allows sending Queries via HTTP GET if supported by the server. Request parameters are passed in the query string, for example:

~~~http
GET /graphql?query=query%20FindBook%28%24id%3A%20ID%21%29%7Bbook%28id%3A%24id%29%7Bid%20title%7D%7D&operationName=FindBook&variables=%7B%22id%22%3A%22book-42%22%7D
Accept: application/json
~~~

The `query`, `operationName`, `variables`, and `extensions` values are URL-encoded. `variables` and `extensions` are JSON encoded as query parameter strings.

GET is only suitable for read-only Queries. Do not send Mutations via GET because intermediaries, browsers, or caches may treat GET as a safe operation and cache or prefetch the request. Subscriptions require a streaming-capable transport.

There are practical limitations:

- URLs have length limits depending on browsers, proxies, and web servers.
- Query strings can appear in access logs, browser history, and monitoring systems.
- Sensitive variables in URLs can be stored unintentionally.
- Caching GET requests requires appropriate cache keys and invalidation policies.

Even when the server supports GET, POST is still usually better for requests with complex variables or sensitive data. Do not treat using POST as a substitute for authentication, authorization, or TLS encryption.

## 7. Content-Type and Accept

These two headers serve different roles:

| Header | Meaning |
| --- | --- |
| `Content-Type` | Describes the format of the body the client sends |
| `Accept` | Indicates which response formats the client accepts |

For a JSON POST request:

~~~http
Content-Type: application/json
Accept: application/json
~~~

`Content-Type: application/json` indicates the body is JSON containing a GraphQL request. `Accept: application/json` requests the response in JSON format.

If the body is sent with the wrong content type or invalid JSON, the request may be rejected at the HTTP layer before the GraphQL operation executes.

GraphQL over HTTP also defines a dedicated response media type convention. Exact support and content negotiation depend on the Spring for GraphQL version, Spring Boot version, and transport configuration. When integrating clients, use a media type supported by the server and verify behavior with your project's library version.

## 8. Default HTTP endpoint in Spring Boot

Spring Boot auto-configures an HTTP GraphQL endpoint when the application has the appropriate starter and a schema is provided. The default path is typically `/graphql`.

You can reconfigure the path:

~~~yaml
spring:
  graphql:
    path: /api/graphql
~~~

After configuring it, clients send requests to:

~~~http
POST http://localhost:8080/api/graphql
Content-Type: application/json
Accept: application/json
~~~

In Spring for GraphQL, the HTTP handler converts the request into a `WebGraphQlRequest`, then forwards it through the web GraphQL chain to execute the operation. Once a `WebGraphQlResponse` is produced, the transport converts the result into an HTTP response.

This can be visualized as:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Servlet or WebFlux server"]
    B --> C["GraphQL HTTP handler"]
    C --> D["WebGraphQlRequest"]
    D --> E["WebGraphQlInterceptor chain"]
    E --> F["GraphQL execution"]
    F --> G["DataFetcher / Controller resolver"]
    G --> H["WebGraphQlResponse"]
    H --> I["HTTP JSON response"]
~~~

The HTTP endpoint serves Queries and Mutations in a request/response model. If the application has Subscriptions, configure an appropriate streaming transport, usually WebSocket.

Do not confuse `spring.graphql.path` with the WebSocket endpoint path or paths of other REST routes in the application.

## 9. How do variables reach the resolver?

After GraphQL parses and validates the document, variables are applied to the operation. The resolver receives arguments matching the field parameter names in the schema.

SDL:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Controller:

~~~java
@Controller
class BookQueryController {

    private final BookService bookService;

    BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") UUID id) {
        return bookService.findById(id);
    }
}
~~~

HTTP body:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
    "operationName": "FindBook",
    "variables": {
        "id": "book-42"
    }
}
~~~

GraphQL takes the value of variable `$id`, assigns it to argument `id` of field `book`, and Spring for GraphQL then binds the argument to the `@Argument("id")` parameter.

Converting from the GraphQL scalar `ID` to Java `UUID` depends on scalar configuration and the application's conversion mechanism. If the schema uses custom scalars, register scalar coercing and test the corresponding input data.

For input objects, they can be bound into DTOs or Java records:

~~~java
public record CreateBookInput(
        String title,
        String isbn) {
}

@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

The HTTP request does not need to know the Java class. The client simply sends JSON matching the GraphQL input type; Spring handles binding on the server.

## 10. HTTP response and GraphQL response

The HTTP response typically has a JSON body containing `data`, `errors`, or both.

Successful response:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring GraphQL"
        }
    }
}
~~~

Response with a field error:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": null
        }
    },
    "errors": [
        {
            "message": "Unable to load book title.",
            "path": [
                "book",
                "title"
            ],
            "extensions": {
                "code": "BOOK_TITLE_UNAVAILABLE"
            }
        }
    ]
}
~~~

GraphQL can return partial data when one field fails while other fields succeed. Clients need to check `errors` rather than only checking whether `data` is present.

Not every GraphQL error corresponds to HTTP 4xx or 5xx. Parse, validation, and field execution errors are represented in the GraphQL response; the specific HTTP status also depends on media type, transport, and server configuration. Therefore, clients should read both the HTTP status and the GraphQL response body.

## 11. Authentication and HTTP headers

Authentication is typically passed via HTTP headers, such as a Bearer token:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/json
Authorization: Bearer <access-token>
~~~

Spring Security can authenticate requests in the web security filter chain before the GraphQL handler executes. The authenticated principal can be used in resolvers or added to the GraphQL context depending on application configuration.

Key principles:

- Do not pass access tokens via GraphQL variables.
- Do not place tokens in query strings.
- Do not log `Authorization`, `Cookie`, or tokens.
- Enforce permissions on the server; do not trust client-supplied arguments.
- Define clear security policies for each field or operation.
- Use HTTPS in environments with authentication credentials or private data.

The GraphQL request body and HTTP headers have distinct roles: the body describes the operation and inputs; headers carry transport metadata and authentication credentials. Maintaining this boundary keeps the API maintainable and reduces data-exposure risks.

## 12. CORS and browser requests

When the frontend runs on a different origin than the backend, browsers enforce Cross-Origin Resource Sharing (CORS). CORS is a browser and HTTP mechanism, not part of the GraphQL schema.

A JSON POST can trigger a preflight `OPTIONS` request, especially when the request uses `Content-Type: application/json` or an `Authorization` header.

The server must allow the exact origins, methods, and headers used by the frontend. Conceptual configuration example:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class GraphQlCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        configuration.setAllowedHeaders(
                List.of("Content-Type", "Authorization")
        );

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/graphql", configuration);
        return source;
    }
}
~~~

This example needs to be integrated with the application's Spring Security configuration. Do not use wildcard origins for APIs with credentials unless security policy allows it. Open only the origins, methods, and headers that are actually needed.

CORS does not replace authentication or authorization. A non-browser client can still call the endpoint directly; the server must independently verify identity and access permissions.

## 13. Limiting requests and protecting the server

GraphQL allows clients to select many fields and nested relations in a single operation. Consequently, a small HTTP request can still generate a large amount of work on the server.

Apply appropriate limits:

- Limit HTTP request body size.
- Limit the number of variables and input object sizes.
- Limit query depth or operation complexity if supported by the system.
- Limit list item counts and pagination size.
- Set timeouts for databases and downstream services.
- Limit request rates and concurrent requests.
- Enforce persisted queries or an allowlist if the API needs to restrict allowed documents.

Do not rely solely on request body size limits. A short query document can still trigger many nested resolvers or large data queries. Combine transport limits with controls at the GraphQL and service layers.

## 14. Extensions and persisted queries

`extensions` is an optional field in a GraphQL HTTP request for extended metadata. Some systems use it for persisted queries, tracing metadata, or agreed-upon protocol extensions.

Conceptual structure example of a persisted query extension:

~~~json
{
    "query": "",
    "operationName": "FindBook",
    "variables": {
        "id": "book-42"
    },
    "extensions": {
        "persistedQuery": {
            "version": 1,
            "sha256Hash": "<query-hash>"
        }
    }
}
~~~

This is only an example of the shape of an extension protocol. The server must implement and enable the corresponding persisted query mechanism to understand that extension. Spring for GraphQL does not automatically support every extension simply because a request includes an `extensions` field.

Persisted queries can reduce query document size over the wire and support operation allowlists. However, hashes, versions, caches, and document update workflows must be managed. Do not treat a client-supplied hash as proof of authorization; the server must still authenticate and verify permissions.

## 15. Testing HTTP requests with HttpGraphQlTester

`HttpGraphQlTester` sends operations through a real HTTP transport or test web client, verifying both request binding and responses.

Example creating a tester using `WebTestClient`:

~~~java
WebTestClient webTestClient = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.create(webTestClient);
~~~

Sending a Query with a variable:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("book-42");
~~~

Testing a Mutation with an input object:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
        .variable("input", Map.of(
                "title", "Spring GraphQL",
                "isbn", "9780000000000"
        ))
        .execute()
        .path("createBook.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

Scenarios to test:

- Valid POST request with a JSON body.
- Document with multiple operations and `operationName` selected properly.
- Variables bind properly to `@Argument` and input DTOs.
- Missing required variables or wrong types return GraphQL errors.
- Authentication headers are applied properly.
- Unauthorized requests are rejected per security policy.
- CORS preflight is configured appropriately if browser clients exist.
- Oversized request bodies are rejected.
- Responses with partial data and errors are handled properly by clients.

Use `HttpGraphQlTester` when you want to test the HTTP transport. If you only want to test GraphQL execution without HTTP, you can use `ExecutionGraphQlServiceTester`; the two testers serve different scopes.

## 16. Common errors

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Server reports missing query | Body lacks the `query` field or JSON structure is invalid | Check the JSON request |
| Wrong operation executes | Document has multiple operations, and `operationName` is wrong or missing | Specify the exact `operationName` |
| Resolver receives null argument | Variable name, argument name, or key in `variables` does not match | Cross-check SDL, document, and JSON `variables` |
| Input object fails to bind | JSON does not match the GraphQL input type structure | Check schema and field types |
| HTTP 415 Unsupported Media Type | `Content-Type` is not supported by the server | Send `application/json` for JSON bodies |
| Browser hits CORS error | Origin, method, or header not allowed | Configure CORS at the web/security layer |
| GET query URL is too long | Document or variables are large | Use POST |
| Client checks only HTTP 200 and ignores errors | GraphQL errors are inside the response body | Inspect both `data` and `errors` |
| Token appears in logs | Logging full headers or query strings | Redact `Authorization` and avoid tokens in URLs |
| Simple request overloads the server | Query has high depth/complexity or large list size | Limit operations and pagination |
| `extensions` is ignored | Server has not implemented the corresponding extension protocol | Configure the extension properly or omit the field |

## 17. Workflow for sending GraphQL HTTP requests

When integrating a client with Spring for GraphQL, follow this sequence:

1. **Identify the operation.** Choose Query or Mutation; use a separate subscription transport for Subscriptions.
2. **Write the GraphQL document.** Declare fields, arguments, and variables.
3. **Set the operation name.** Especially when the document contains multiple operations.
4. **Prepare variables.** Send a JSON object matching the scalars and input types in the schema.
5. **Choose the HTTP method.** Use POST for most requests; only use GET for Queries when the server supports it and the data is safe for URLs.
6. **Set headers.** Send `Content-Type`, `Accept`, and `Authorization` when needed.
7. **Send to the endpoint.** Use the configured Spring GraphQL path, usually `/graphql` by default.
8. **Read the response.** Check `data`, `errors`, HTTP status, and response headers.
9. **Protect the request.** Never place tokens or sensitive data in URLs, query documents, or logs.
10. **Test and limit load.** Use `HttpGraphQlTester`, and verify validation, authorization, CORS, and request size limits.

## 18. Summary

A GraphQL HTTP request is how clients send a GraphQL document to the server over HTTP. For JSON requests, the key fields are `query`, `operationName`, `variables`, and `extensions`. HTTP POST is the standard choice for Queries and Mutations; GET can be used for Queries when supported by the server, though URL limits, caching, and sensitive data require care.

In Spring for GraphQL, Spring Boot typically exposes `/graphql` and converts HTTP requests into GraphQL execution. Variables are validated against the schema and bound to `@Argument` parameters or input DTOs on resolvers. HTTP responses can contain `data`, `errors`, or both, so clients must inspect GraphQL errors rather than relying solely on the HTTP status. Combining proper headers, authentication, CORS, request limits, and `HttpGraphQlTester` helps build a clear, secure, and testable HTTP GraphQL flow.
